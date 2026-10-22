"""Turn a validated signal + your daily goal into a concrete, sized trade plan."""
import math

from .options import pick_contract
from .strategy import levels


def size_position(contract, cfg, goal_remaining):
    """How many contracts: enough to reach the goal at target, but never more than
    the risk and premium limits allow."""
    account = cfg["account_size"]
    entry = contract["entry_limit"]
    risk_pc = max((entry - contract["est_at_stop"]) * 100, 1.0)
    profit_pc = (contract["est_at_target"] - entry) * 100
    max_risk = account * cfg["max_risk_pct_per_trade"] / 100
    by_risk = math.floor(max_risk / risk_pc)
    by_premium = math.floor(account * cfg["max_premium_pct_per_trade"] / 100 / (entry * 100))
    by_goal = math.ceil(goal_remaining / profit_pc) if profit_pc > 0 and goal_remaining > 0 else 1
    qty = max(min(by_goal, by_risk, by_premium), 0)
    warnings = []
    if qty == 0:
        warnings.append(f"Even 1 contract risks ${risk_pc:,.0f} / costs ${entry * 100:,.0f}, "
                        f"over your limits (risk ${max_risk:,.0f}). SKIP.")
    elif by_goal > qty:
        warnings.append(f"Hitting your full goal would need {by_goal} contracts, but your risk rules allow "
                        f"{qty}. This trade can make ~${qty * profit_pc:,.0f} at target. Don't force size.")
    return {
        "contracts": qty, "risk_per_contract": round(risk_pc, 2), "profit_per_contract": round(profit_pc, 2),
        "total_cost": round(qty * entry * 100, 2), "max_loss": round(qty * risk_pc, 2),
        "profit_at_target": round(qty * profit_pc, 2), "warnings": warnings,
    }


def build_plan(provider, ticker, sig_df, validation, cfg, goal_remaining, today):
    """Plan for the latest closed candle, or (None, reason)."""
    last = sig_df.iloc[-1]
    direction = int(last["signal"])
    if direction == 0:
        return None, "no signal"
    spot = float(last["Close"])
    stop, target = levels(spot, float(last["atr"]), direction, cfg["strategy"])
    contract, why = pick_contract(provider, ticker, direction, spot, stop, target, cfg, today)
    if contract is None:
        return None, why
    sizing = size_position(contract, cfg, goal_remaining)
    if sizing["contracts"] == 0:
        return None, sizing["warnings"][0]
    risk_dollars = sizing["max_loss"]
    return {
        "ticker": ticker,
        "direction": direction,
        "action": "BUY CALLS" if direction > 0 else "BUY PUTS",
        "signal_time": str(sig_df.index[-1]),
        "reason": last["reason"],
        "stock_price": round(spot, 2),
        "stock_stop": stop,
        "stock_target": target,
        "contract": contract,
        "sizing": sizing,
        "backtest": validation.summary(),
        "expected_value": round(validation.expectancy_r * risk_dollars, 2),
    }, ""


def format_plan(plan, alert_id):
    c, z = plan["contract"], plan["sizing"]
    stop_pct = (c["est_at_stop"] / c["entry_limit"] - 1) * 100
    tgt_pct = (c["est_at_target"] / c["entry_limit"] - 1) * 100
    lines = [
        f"{plan['action']} on {plan['ticker']} (stock ${plan['stock_price']:.2f})",
        f"Why: {plan['reason']}",
        "",
        f"BUY:    {z['contracts']}x {plan['ticker']} {c['expiry']} ${c['strike']:g} {c['kind'].upper()}",
        f"        limit ${c['entry_limit']:.2f} (bid {c['bid']:.2f} / ask {c['ask']:.2f}, delta {c['delta']}, {c['dte']} days)",
        f"        total cost ~${z['total_cost']:,.0f}",
        f"TARGET: sell when stock hits ${plan['stock_target']:.2f}  -> option ~${c['est_at_target']:.2f} ({tgt_pct:+.0f}%)",
        f"STOP:   sell if stock hits ${plan['stock_stop']:.2f}   -> option ~${c['est_at_stop']:.2f} ({stop_pct:+.0f}%)",
        f"        (or set an option stop near ${c['est_at_stop']:.2f})",
        f"Max loss ~${z['max_loss']:,.0f} | profit at target ~${z['profit_at_target']:,.0f}",
        f"Tested: {plan['backtest']}",
        f"Average expected result for this size: ${plan['expected_value']:+,.0f}",
    ]
    for w in z["warnings"]:
        lines.append(f"NOTE: {w}")
    lines += ["", f"Bought it? Tell the app:  python -m optionsbot enter {alert_id} --fill <price you paid>"]
    return "\n".join(lines)
