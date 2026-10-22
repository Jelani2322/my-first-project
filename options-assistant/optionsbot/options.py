"""Option pricing (Black-Scholes) and contract selection."""
import math
from datetime import date

SQRT2 = math.sqrt(2)


def _cdf(x):
    return 0.5 * (1 + math.erf(x / SQRT2))


def _d1d2(s, k, t, r, iv):
    t = max(t, 1e-6)
    iv = max(iv, 1e-4)
    d1 = (math.log(s / k) + (r + iv * iv / 2) * t) / (iv * math.sqrt(t))
    return d1, d1 - iv * math.sqrt(t)


def bs_price(s, k, t, r, iv, kind):
    d1, d2 = _d1d2(s, k, t, r, iv)
    if kind == "call":
        return s * _cdf(d1) - k * math.exp(-r * t) * _cdf(d2)
    return k * math.exp(-r * t) * _cdf(-d2) - s * _cdf(-d1)


def bs_delta(s, k, t, r, iv, kind):
    d1, _ = _d1d2(s, k, t, r, iv)
    return _cdf(d1) if kind == "call" else _cdf(d1) - 1


def years_to(expiry, today):
    """Calendar time to expiry; same-day expiries still get a few hours of value."""
    return max((expiry - today).days, 0.25) / 365


def pick_contract(provider, ticker, direction, spot, stock_stop, stock_target, cfg, today=None,
                  hold_days=0.1):
    """Choose the expiry/strike to trade and estimate its value at the stock stop and target."""
    o = cfg["options"]
    today = today or date.today()
    kind = "call" if direction > 0 else "put"
    exps = [e for e in provider.expiries(ticker)
            if o["min_days_to_expiry"] <= (e - today).days <= o["max_days_to_expiry"]]
    if not exps:
        return None, f"no expiry between {o['min_days_to_expiry']} and {o['max_days_to_expiry']} days"
    r = o["risk_free_rate"]
    for expiry in sorted(exps):
        chain = provider.chain(ticker, expiry, kind)
        t = years_to(expiry, today)
        best = None
        for row in chain.itertuples():
            bid, ask = float(row.bid), float(row.ask)
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.lastPrice)
            if mid < 0.05 or row.openInterest < o["min_open_interest"]:
                continue
            spread_pct = (ask - bid) / mid * 100 if bid > 0 else 100.0
            if spread_pct > o["max_spread_pct"]:
                continue
            iv = float(row.impliedVolatility) if row.impliedVolatility > 0.01 else 0.30
            delta = bs_delta(spot, row.strike, t, r, iv, kind)
            score = abs(abs(delta) - o["target_delta"])
            if best is None or score < best[0]:
                best = (score, row, mid, iv, delta, spread_pct, bid, ask)
        if best is None:
            continue
        _, row, mid, iv, delta, spread_pct, bid, ask = best
        t_later = max(t - hold_days / 365, 1e-4)
        # pay a little above mid so the limit order actually fills
        entry = round(min(ask, mid + 0.25 * (ask - mid)) if ask > 0 else mid, 2)
        return {
            "kind": kind,
            "symbol": row.contractSymbol,
            "expiry": expiry.isoformat(),
            "dte": (expiry - today).days,
            "strike": float(row.strike),
            "bid": bid, "ask": ask, "entry_limit": entry,
            "iv": iv, "delta": round(delta, 2), "spread_pct": round(spread_pct, 1),
            "open_interest": int(row.openInterest),
            "est_at_stop": round(bs_price(stock_stop, row.strike, t_later, r, iv, kind), 2),
            "est_at_target": round(bs_price(stock_target, row.strike, t_later, r, iv, kind), 2),
        }, ""
    return None, "no liquid contract (open interest / bid-ask spread filters)"
