import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from optionsbot.app import Assistant
from optionsbot.backtest import simulate, validate
from optionsbot.config import load_config
from optionsbot.data import DemoProvider
from optionsbot.indicators import rsi, vwap
from optionsbot.options import bs_delta, bs_price, pick_contract
from optionsbot.planner import size_position
from optionsbot.strategy import compute_signals


@pytest.fixture
def cfg():
    return load_config("/nonexistent")  # defaults only


def random_walk(days=60, seed=0):
    rng = np.random.default_rng(seed)
    idx = []
    d = pd.Timestamp("2026-01-05")
    while len(idx) < days * 78:
        if d.weekday() < 5:
            idx.extend(pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=78, freq="5min", tz="America/New_York"))
        d += pd.Timedelta(days=1)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    open_ = np.concatenate([[100], close[:-1]])
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * 1.001,
                         "Low": np.minimum(open_, close) * 0.999, "Close": close,
                         "Volume": rng.integers(1e5, 5e5, len(idx)).astype(float)}, index=pd.DatetimeIndex(idx))


def test_put_call_parity():
    s, k, t, r, iv = 100, 105, 30 / 365, 0.04, 0.3
    c, p = bs_price(s, k, t, r, iv, "call"), bs_price(s, k, t, r, iv, "put")
    assert math.isclose(c - p, s - k * math.exp(-r * t), abs_tol=1e-9)
    assert 0 < bs_delta(s, k, t, r, iv, "call") < 1
    assert -1 < bs_delta(s, k, t, r, iv, "put") < 0


def test_indicators_basic():
    df = random_walk(3)
    assert rsi(df["Close"]).between(0, 100).all()
    vw = vwap(df)
    assert ((vw >= df["Low"].groupby(df.index.date).transform("min") - 1e-9)).all()


def test_signals_only_inside_entry_window(cfg):
    sig = compute_signals(random_walk(), cfg["strategy"])
    minutes = sig.index.hour * 60 + sig.index.minute
    on = sig["signal"] != 0
    assert on.any()
    assert (minutes[on] >= 9 * 60 + 40).all() and (minutes[on] <= 15 * 60 + 15).all()


def test_no_edge_on_pure_random_walk_is_rejected(cfg):
    """The validator must not 'find' an edge in noise for most random markets."""
    passed = sum(validate("RW", random_walk(seed=s), cfg).passed for s in range(6))
    assert passed <= 1


def test_trades_never_overlap_and_risk_is_capped(cfg):
    trades = simulate(random_walk(seed=3), cfg["strategy"])
    assert trades
    for a, b in zip(trades, trades[1:]):
        assert b.entry_time > a.exit_time
    assert min(t.r for t in trades) >= -1.5  # only a gap through the stop can lose more than 1R


def test_sizing_respects_risk_and_premium_limits(cfg):
    contract = {"entry_limit": 2.00, "est_at_stop": 1.50, "est_at_target": 3.00}
    z = size_position(contract, cfg, goal_remaining=10_000)
    max_risk = cfg["account_size"] * cfg["max_risk_pct_per_trade"] / 100
    assert z["max_loss"] <= max_risk
    assert z["total_cost"] <= cfg["account_size"] * cfg["max_premium_pct_per_trade"] / 100
    assert z["warnings"]  # big goal -> told it is unrealistic, not oversized
    small = size_position(contract, cfg, goal_remaining=90)
    assert small["contracts"] == 1


def test_pick_contract_from_demo_chain(cfg):
    prov = DemoProvider(tickers=("SPY",))
    df = prov.bars("SPY")
    spot = float(df["Close"].iat[-1])
    c, why = pick_contract(prov, "SPY", -1, spot, spot * 1.005, spot * 0.99, cfg, prov.today)
    assert c and c["kind"] == "put" and c["est_at_target"] > c["entry_limit"] > c["est_at_stop"]


def test_demo_session_end_to_end(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr("optionsbot.store.ROOT", tmp_path)
    cfg["watchlist"] = ["SPY", "QQQ", "AAPL"]
    a = Assistant(cfg, DemoProvider(tickers=tuple(cfg["watchlist"])), demo=True, auto_enter=True, log=lambda *x: None)
    st = a.store.load(); st["goal"] = 200; a.store.save(st)
    a.validate_watchlist()
    for _ in range(60):
        a.cycle()
    st = a.store.load()
    assert st["alerts"], "expected at least one buy alert in a demo session"
    assert st["closed"], "expected at least one paper trade to be exited"
    assert len(st["positions"]) <= cfg["max_open_positions"]
