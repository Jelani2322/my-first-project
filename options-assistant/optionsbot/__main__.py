"""Command line:  python -m optionsbot <command>   (add --demo to use the fake market)"""
import argparse
import json
from datetime import date

from .app import Assistant, close_position, enter_from_alert, run_validation
from .backtest import simulate
from .config import CONFIG, load_config
from .data import make_provider
from .notify import Notifier
from .store import Store

DISCLAIMER = ("This tool gives educational, rules-based suggestions - not financial advice. "
              "Options can lose 100% of what you pay. Past/backtested results do not guarantee future results.")


def ask_float(prompt, default=None):
    while True:
        raw = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip().replace("$", "").replace(",", "")
        if not raw and default is not None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number.")


def cmd_setup(args, cfg):
    cfg["account_size"] = ask_float("Trading account size in $", cfg["account_size"])
    cfg["max_risk_pct_per_trade"] = ask_float("Max % of account to risk on one trade", cfg["max_risk_pct_per_trade"])
    wl = input(f"Watchlist (comma separated) [{','.join(cfg['watchlist'])}]: ").strip()
    if wl:
        cfg["watchlist"] = [t.strip().upper() for t in wl.split(",") if t.strip()]
    topic = input("ntfy.sh topic for phone alerts (blank = console only): ").strip()
    if topic:
        cfg["notify"]["ntfy_topic"] = topic
    CONFIG.write_text(json.dumps(cfg, indent=2))
    print(f"Saved {CONFIG}")


def cmd_start(args, cfg):
    print(DISCLAIMER + "\n")
    store = Store(args.demo)
    st = store.load()
    today = date.today().isoformat()
    if st.get("goal_day") != today or args.goal is not None:
        goal = args.goal if args.goal is not None else ask_float("How much do you want to make today? $")
        max_risk = cfg["account_size"] * cfg["max_risk_pct_per_trade"] / 100
        pct = goal / cfg["account_size"] * 100
        print(f"\nGoal ${goal:,.0f} = {pct:.1f}% of your ${cfg['account_size']:,.0f} account. "
              f"Max risk per trade is ${max_risk:,.0f}.")
        if pct > 5:
            print("Heads up: more than 5%/day is very aggressive. The app will NOT raise your risk to chase it;"
                  " it will size within your limits and tell you what's realistic.")
        st["goal"], st["goal_day"] = goal, today
        store.save(st)
    provider = make_provider(cfg, args.demo)
    a = Assistant(cfg, provider, demo=args.demo, auto_enter=args.auto_enter)
    if not a.validate_watchlist():
        print("No ticker passed testing today - the right trade is no trade.")
        return
    poll = cfg["poll_seconds"] if args.poll is None else args.poll
    print(f"\nWatching for entries (checks every {poll:g}s). Ctrl+C to stop.\n")
    try:
        a.run(poll, max_cycles=args.cycles)
    except KeyboardInterrupt:
        print("\nStopped.")


def cmd_backtest(args, cfg):
    provider = make_provider(cfg, args.demo)
    tickers = [t.upper() for t in args.tickers] or cfg["watchlist"]
    results = run_validation(provider, cfg, tickers)
    if args.trades:
        for t in results:
            for tr in simulate(provider.bars(t), cfg["strategy"])[-args.trades:]:
                side = "CALL" if tr.direction > 0 else "PUT "
                print(f"  {t} {side} {tr.entry_time.tz_convert("America/New_York"):%m-%d %H:%M} ET {tr.entry:.2f} -> {tr.exit:.2f}  {tr.r:+.2f}R  ({tr.reason})")


def cmd_enter(args, cfg):
    store = Store(args.demo)
    st = store.load()
    plan = next((x for x in st["alerts"] if x["id"] == args.alert_id), None)
    if plan is None:
        raise SystemExit(f"No alert #{args.alert_id}. Run `status` to see alerts.")
    contracts = args.contracts or plan["sizing"]["contracts"]
    pos = enter_from_alert(st, plan, args.fill, contracts)
    store.save(st)
    print(f"Tracking position #{pos['id']}: {contracts}x {pos['ticker']} {pos['expiry']} ${pos['strike']:g} "
          f"{pos['kind']} @ ${args.fill:.2f}\n  stock stop ${pos['stock_stop']:.2f} | stock target ${pos['stock_target']:.2f}"
          f" | option stop ~${pos['option_stop']:.2f} | option target ~${pos['option_target']:.2f}\n"
          "The running `start` loop will now watch it and tell you when to sell.")


def cmd_close(args, cfg):
    store = Store(args.demo)
    st = store.load()
    pos = close_position(st, args.position_id, args.fill)
    store.save(st)
    print(f"Closed #{pos['id']} {pos['ticker']}: P/L ${pos['pnl']:+,.2f}. "
          f"Today: ${Store.realized_today(st):+,.2f} of ${st.get('goal', 0):,.0f} goal.")


def cmd_status(args, cfg):
    st = Store(args.demo).load()
    print(f"Goal today: ${st.get('goal', 0):,.0f} | realized today: ${Store.realized_today(st):+,.2f}")
    print("\nOpen positions:" if st["positions"] else "\nNo open positions.")
    for p in st["positions"]:
        print(f"  #{p['id']} {p['contracts']}x {p['ticker']} {p['expiry']} ${p['strike']:g} {p['kind']} @ {p['fill']:.2f}"
              f" | last ~{p.get('last_mark', '?')} | stop ${p['stock_stop']:.2f} target ${p['stock_target']:.2f}")
    print("\nRecent alerts:")
    for a in st["alerts"][-5:]:
        c = a["contract"]
        print(f"  #{a['id']} {a['action']} {a['ticker']} {c['expiry']} ${c['strike']:g} x{a['sizing']['contracts']}"
              f" @ {c['entry_limit']:.2f} ({a['created']})")
    for c in st["closed"][-5:]:
        print(f"  closed #{c['id']} {c['ticker']} {c['kind']} P/L ${c['pnl']:+,.2f}")


def cmd_test_notify(args, cfg):
    sent = Notifier(cfg).send("Options assistant test", "If you can read this, alerts work.")
    print(f"Sent via: {', '.join(sent)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="optionsbot", description=DISCLAIMER)
    p.add_argument("--demo", action="store_true", help="use a simulated market (works any time)")
    p.add_argument("--config", help="path to config.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="set account size, risk and alert settings")
    s = sub.add_parser("start", help="ask today's goal, test strategies, then watch for trades")
    s.add_argument("--goal", type=float, help="today's profit goal in $ (skips the question)")
    s.add_argument("--poll", type=float, help="seconds between checks")
    s.add_argument("--cycles", type=int, help="stop after N checks (default: run until Ctrl+C)")
    s.add_argument("--auto-enter", action="store_true", help="paper-trade: auto enter/exit every alert")
    b = sub.add_parser("backtest", help="test the strategy on tickers")
    b.add_argument("tickers", nargs="*")
    b.add_argument("--trades", type=int, default=0, help="also list the last N simulated trades")
    e = sub.add_parser("enter", help="tell the app you bought an alerted option")
    e.add_argument("alert_id", type=int)
    e.add_argument("--fill", type=float, required=True, help="price you paid per option")
    e.add_argument("--contracts", type=int, help="if different from the suggestion")
    c = sub.add_parser("close", help="tell the app you sold a position")
    c.add_argument("position_id", type=int)
    c.add_argument("--fill", type=float, required=True, help="price you sold at per option")
    sub.add_parser("status", help="goal progress, open positions, recent alerts")
    sub.add_parser("test-notify", help="send a test alert")

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    {"setup": cmd_setup, "start": cmd_start, "backtest": cmd_backtest, "enter": cmd_enter,
     "close": cmd_close, "status": cmd_status, "test-notify": cmd_test_notify}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
