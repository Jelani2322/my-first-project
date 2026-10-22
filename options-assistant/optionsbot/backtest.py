"""Backtest the signal rules and stress-test the result before trusting it.

'Testing the hypothesis several times' means:
  1. Walk-forward folds: history is cut into N separate time windows and the
     strategy must be profitable in most of them, not just on average.
  2. Bootstrap: trades are resampled thousands of times to estimate how likely
     the edge is real rather than luck.
"""
from dataclasses import dataclass, field

import numpy as np

from .strategy import compute_signals, exit_reasons, levels


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    direction: int
    entry: float
    exit: float
    r: float          # result in multiples of risk (stop distance)
    reason: str


@dataclass
class Validation:
    ticker: str
    passed: bool
    trades: int
    win_rate: float
    expectancy_r: float
    folds_profitable: int
    folds: int
    bootstrap_confidence: float
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    notes: list = field(default_factory=list)

    def summary(self):
        verdict = "PASSED" if self.passed else "FAILED"
        return (f"{self.ticker}: {verdict} | {self.trades} trades, win {self.win_rate:.0%}, "
                f"avg {self.expectancy_r:+.2f}R/trade, profitable in {self.folds_profitable}/{self.folds} "
                f"periods, {self.bootstrap_confidence:.0%} confidence edge is real")


def simulate(df, s, direction_filter=None):
    """Run the rules bar-by-bar. Enter at next bar's open; one position at a time."""
    df = compute_signals(df, s)
    trades = []
    i, n = 0, len(df)
    days = df.index.date
    while i < n - 1:
        d = int(df["signal"].iat[i])
        if d == 0 or (direction_filter and d != direction_filter):
            i += 1
            continue
        j = i + 1
        entry = float(df["Open"].iat[j])
        stop, target = levels(entry, float(df["atr"].iat[i]), d, s)
        risk = abs(entry - stop)
        exit_px, why, k = None, "", j
        for k in range(j, n):
            if days[k] != days[j]:
                exit_px, why, k = float(df["Close"].iat[k - 1]), "end of day", k - 1
                break
            reasons = exit_reasons(df, k, d, stop, target, s)
            if not reasons:
                continue
            if reasons[0].startswith("STOP"):
                o = float(df["Open"].iat[k])
                exit_px = min(o, stop) if d > 0 else max(o, stop)  # gapped through the stop -> worse fill
            elif reasons[0].startswith("TARGET"):
                exit_px = target
            else:
                exit_px = float(df["Close"].iat[k])
            why = reasons[0]
            break
        if exit_px is None:
            exit_px, why, k = float(df["Close"].iat[n - 1]), "end of data", n - 1
        r = d * (exit_px - entry) / risk if risk > 0 else 0.0
        trades.append(Trade(df.index[j], df.index[k], d, entry, exit_px, r, why))
        i = k + 1
    return trades


def _stats(rs):
    if len(rs) == 0:
        return 0.0, 0.0
    rs = np.asarray(rs)
    return float((rs > 0).mean()), float(rs.mean())


def validate(ticker, df, cfg, seed=7):
    s, v = cfg["strategy"], cfg["validation"]
    trades = simulate(df, s)
    rs = np.array([t.r for t in trades])
    win, exp_r = _stats(rs)

    # 1. walk-forward: split the history into separate time periods
    folds = v["folds"]
    edges = np.linspace(0, len(df), folds + 1).astype(int)
    profitable = 0
    for a, b in zip(edges[:-1], edges[1:]):
        lo, hi = df.index[a], df.index[min(b, len(df)) - 1]
        fold_r = [t.r for t in trades if lo <= t.entry_time <= hi]
        if fold_r and np.mean(fold_r) > 0:
            profitable += 1

    # 2. bootstrap: how often does a resampled set of these trades still make money?
    conf = 0.0
    if len(rs) > 1:
        rng = np.random.default_rng(seed)
        samples = rng.choice(rs, size=(v["bootstrap_runs"], len(rs)), replace=True)
        conf = float((samples.mean(axis=1) > 0).mean())

    notes = []
    if len(rs) < v["min_trades_total"]:
        notes.append(f"only {len(rs)} trades (< {v['min_trades_total']}) - not enough evidence")
    if profitable < v["min_folds_profitable"]:
        notes.append(f"profitable in only {profitable}/{folds} periods")
    if win < v["min_win_rate"]:
        notes.append(f"win rate {win:.0%} below {v['min_win_rate']:.0%}")
    if exp_r <= 0:
        notes.append("negative expectancy")
    if conf < v["min_bootstrap_confidence"]:
        notes.append(f"bootstrap confidence {conf:.0%} below {v['min_bootstrap_confidence']:.0%}")

    wins, losses = rs[rs > 0], rs[rs <= 0]
    return Validation(
        ticker=ticker, passed=not notes, trades=len(rs), win_rate=win, expectancy_r=exp_r,
        folds_profitable=profitable, folds=folds, bootstrap_confidence=conf,
        avg_win_r=float(wins.mean()) if len(wins) else 0.0,
        avg_loss_r=float(losses.mean()) if len(losses) else 0.0, notes=notes,
    )
