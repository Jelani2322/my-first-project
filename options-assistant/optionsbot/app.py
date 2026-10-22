"""The live loop: scan validated tickers for entries, and watch open trades for exits."""
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .backtest import validate
from .notify import Notifier
from .options import bs_price, years_to
from .planner import build_plan, format_plan
from .store import Store
from .strategy import compute_signals, exit_reasons

ET = ZoneInfo("America/New_York")


def market_open(now=None):
    now = now or datetime.now(ET)
    mins = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 30 <= mins < 16 * 60


def run_validation(provider, cfg, tickers, log=print):
    results = {}
    for t in tickers:
        try:
            v = validate(t, provider.bars(t), cfg)
        except Exception as e:
            log(f"  {t}: could not test ({e})")
            continue
        results[t] = v
        log("  " + v.summary())
        for note in v.notes:
            log(f"      - {note}")
    return results


def option_mark(provider, pos, spot, today):
    """Current option price: live quote if available, otherwise a Black-Scholes estimate."""
    expiry = date.fromisoformat(pos["expiry"])
    try:
        chain = provider.chain(pos["ticker"], expiry, pos["kind"])
        row = chain[chain["contractSymbol"] == pos["symbol"]]
        if not row.empty and row["bid"].iat[0] > 0:
            return round((row["bid"].iat[0] + row["ask"].iat[0]) / 2, 2)
    except Exception:
        pass
    return round(bs_price(spot, pos["strike"], years_to(expiry, today), 0.04, pos["iv"], pos["kind"]), 2)


class Assistant:
    def __init__(self, cfg, provider, demo=False, auto_enter=False, log=print):
        self.cfg, self.provider, self.demo = cfg, provider, demo
        self.auto_enter = auto_enter
        self.store = Store(demo)
        self.notifier = Notifier(cfg)
        self.log = log
        self.validations = {}
        self.last_bar = {}

    def today(self):
        return getattr(self.provider, "today", None) or date.today()

    def validate_watchlist(self):
        self.log("Testing the strategy on each ticker's history before trusting it...")
        self.validations = run_validation(self.provider, self.cfg, self.cfg["watchlist"], self.log)
        passed = [t for t, v in self.validations.items() if v.passed]
        self.log(f"\nCleared for trading today: {', '.join(passed) or 'NONE'}")
        return passed

    def cycle(self):
        st = self.store.load()
        goal = st.get("goal", 0)
        realized = Store.realized_today(st)
        self._monitor_positions(st)
        open_tickers = {p["ticker"] for p in st["positions"]}
        if goal and realized >= goal:
            self.log(f"Goal reached (${realized:,.0f} of ${goal:,.0f}). No new entries - protect the day.")
        else:
            for t, v in self.validations.items():
                if len(st["positions"]) >= self.cfg["max_open_positions"]:
                    break
                if v.passed and t not in open_tickers:
                    self._scan(st, t, v, goal - realized)
        self.store.save(st)

    def _new_candle(self, key, df):
        ts = df.index[-1]
        if self.last_bar.get(key) == ts:
            return False
        self.last_bar[key] = ts
        return True

    def _scan(self, st, ticker, v, goal_remaining):
        try:
            df = self.provider.bars(ticker)
        except Exception as e:
            self.log(f"[warn] {ticker}: {e}")
            return
        if not self._new_candle(("scan", ticker), df):
            return
        sig = compute_signals(df, self.cfg["strategy"])
        if sig["signal"].iat[-1] == 0:
            return
        plan, why = build_plan(self.provider, ticker, sig, v, self.cfg, max(goal_remaining, 0), self.today())
        if plan is None:
            self.log(f"{ticker}: signal skipped - {why}")
            return
        alert_id = Store.new_id(st)
        plan["id"] = alert_id
        plan["created"] = datetime.now().isoformat(timespec="seconds")
        st["alerts"].append(plan)
        self.notifier.send(f"#{alert_id} {plan['action']} {ticker} - BUY NOW", format_plan(plan, alert_id), urgent=True)
        if self.auto_enter:
            enter_from_alert(st, plan, plan["contract"]["entry_limit"], plan["sizing"]["contracts"])

    def _monitor_positions(self, st):
        for pos in list(st["positions"]):
            try:
                df = self.provider.bars(pos["ticker"])
            except Exception as e:
                self.log(f"[warn] {pos['ticker']}: {e}")
                continue
            if not self._new_candle(("pos", pos["id"]), df):
                continue
            sig = compute_signals(df, self.cfg["strategy"])
            d = pos["direction"]
            spot = float(sig["Close"].iat[-1])
            reasons = exit_reasons(sig, len(sig) - 1, d, pos["stock_stop"], pos["stock_target"], self.cfg["strategy"])
            mark = option_mark(self.provider, pos, spot, self.today())
            pnl = (mark - pos["fill"]) * 100 * pos["contracts"]
            pos["last_mark"], pos["last_spot"] = mark, round(spot, 2)

            # once the trade is up 1x its risk, move the stop to breakeven
            risk = abs(pos["stock_entry"] - pos["stock_stop_initial"])
            if not pos.get("breakeven") and d * (spot - pos["stock_entry"]) >= risk:
                pos["stock_stop"] = pos["stock_entry"]
                pos["breakeven"] = True
                self.notifier.send(f"#{pos['id']} {pos['ticker']}: move stop to breakeven",
                                   f"Stock ${spot:.2f} is up 1R. Raise your stop to stock ${pos['stock_entry']:.2f} "
                                   f"(option ~${pos['fill']:.2f}) so this can't turn into a loss.\n"
                                   f"Option now ~${mark:.2f}, P/L ${pnl:+,.0f}")

            if reasons:
                # these are exactly the exit rules the backtest used, so treat each as a sell signal
                body = "\n".join(
                    [f"Stock ${spot:.2f} | option ~${mark:.2f} (paid ${pos['fill']:.2f}) | P/L ${pnl:+,.0f}", ""]
                    + [f"- {r}" for r in reasons]
                    + ["", "Action: SELL NOW.",
                       f"Sold it? Tell the app:  python -m optionsbot close {pos['id']} --fill <price>"])
                self.notifier.send(f"#{pos['id']} SELL {pos['ticker']} {pos['kind'].upper()}S", body, urgent=True)
                if self.auto_enter:
                    close_position(st, pos["id"], mark)
            else:
                self.log(f"#{pos['id']} {pos['ticker']} holding: stock ${spot:.2f}, option ~${mark:.2f}, "
                         f"P/L ${pnl:+,.0f} (stop ${pos['stock_stop']:.2f}, target ${pos['stock_target']:.2f})")

    def run(self, poll_seconds, max_cycles=None):
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            if self.demo or market_open():
                self.cycle()
            else:
                self.log(f"{datetime.now(ET):%H:%M} ET - market closed, waiting...")
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                time.sleep(poll_seconds)


def enter_from_alert(st, plan, fill, contracts):
    c = plan["contract"]
    pos = {
        "id": Store.new_id(st), "alert_id": plan.get("id"), "ticker": plan["ticker"],
        "direction": plan["direction"], "kind": c["kind"], "symbol": c["symbol"],
        "expiry": c["expiry"], "strike": c["strike"], "iv": c["iv"],
        "fill": fill, "contracts": contracts,
        "stock_entry": plan["stock_price"], "stock_stop": plan["stock_stop"],
        "stock_stop_initial": plan["stock_stop"], "stock_target": plan["stock_target"],
        "option_stop": c["est_at_stop"], "option_target": c["est_at_target"],
        "opened_at": datetime.now().isoformat(timespec="seconds"),
    }
    st["positions"].append(pos)
    return pos


def close_position(st, pos_id, fill):
    pos = next((p for p in st["positions"] if p["id"] == pos_id), None)
    if pos is None:
        raise KeyError(f"no open position #{pos_id}")
    st["positions"].remove(pos)
    pos["exit_fill"] = fill
    pos["pnl"] = round((fill - pos["fill"]) * 100 * pos["contracts"], 2)
    pos["closed_at"] = datetime.now().isoformat(timespec="seconds")
    st["closed"].append(pos)
    return pos
