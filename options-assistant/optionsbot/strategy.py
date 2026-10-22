"""Entry signals for calls (+1) and puts (-1) on intraday candles.

The rules are fixed in advance (not curve-fit) and are validated per ticker by
backtest.validate() before anything is ever suggested.
"""
from datetime import time

import numpy as np
import pandas as pd

from . import patterns
from .indicators import add_indicators

ET = "America/New_York"


def _to_et(index):
    if index.tz is None:
        return index.tz_localize("UTC").tz_convert(ET)
    return index.tz_convert(ET)


def _hhmm(s):
    h, m = s.split(":")
    return time(int(h), int(m))


def et_minutes(index):
    et = _to_et(index)
    return et.hour * 60 + et.minute


def entry_window(df, s):
    """True for bars where opening a new trade is allowed."""
    start_min = 9 * 60 + 30 + s["skip_first_minutes"]
    stop = _hhmm(s["no_new_entries_after"])
    minutes = et_minutes(df.index)
    return pd.Series((minutes >= start_min) & (minutes <= stop.hour * 60 + stop.minute), index=df.index)


def compute_signals(df, s):
    """Adds indicator columns plus `signal` (+1 call / -1 put / 0) and a human `reason`."""
    df = add_indicators(df, s)
    vol_ok = df["Volume"] >= 0.8 * df["vol_avg"].fillna(0)

    long_ = (
        (df["Close"] > df["vwap"])
        & (df["ema_fast"] > df["ema_slow"])
        & (df["macd_hist"] > 0) & (df["macd_hist"] > df["macd_hist"].shift())
        & df["rsi"].between(52, 72)
        & (df["Close"] > df["range_high"])
        & vol_ok
        & ~patterns.shooting_star(df)
    )
    short = (
        (df["Close"] < df["vwap"])
        & (df["ema_fast"] < df["ema_slow"])
        & (df["macd_hist"] < 0) & (df["macd_hist"] < df["macd_hist"].shift())
        & df["rsi"].between(28, 48)
        & (df["Close"] < df["range_low"])
        & vol_ok
        & ~patterns.hammer(df)
    )
    df["et_minute"] = et_minutes(df.index)
    df["rev_call"], df["rev_put"] = patterns.reversal_labels(df)
    window = entry_window(df, s)
    sig = np.where(long_ & window, 1, np.where(short & window, -1, 0))
    df["signal"] = sig
    df["reason"] = np.where(
        sig == 1, "Breakout above recent high, above VWAP, EMA9>EMA21, MACD rising, RSI healthy",
        np.where(sig == -1, "Breakdown below recent low, below VWAP, EMA9<EMA21, MACD falling, RSI weak", ""),
    )
    return df


def levels(entry, atr_value, direction, s):
    """Stock stop and target for a trade (target is 2x the stop distance by default)."""
    stop = entry - direction * s["stop_atr_mult"] * atr_value
    target = entry + direction * s["target_atr_mult"] * atr_value
    return round(stop, 2), round(target, 2)


def exit_reasons(df, i, direction, stop, target, s):
    """Why an open position should be sold at bar i (empty list = hold).

    Hard exits (stop/target) plus 'looks bad' candle/indicator checks."""
    row = df.iloc[i]
    reasons = []
    if direction > 0:
        if row["Low"] <= stop:
            reasons.append(f"STOP hit: stock traded at/below ${stop:.2f}")
        if row["High"] >= target:
            reasons.append(f"TARGET hit: stock reached ${target:.2f}")
        if row["Close"] < row["vwap"] and row["Close"] < row["ema_slow"]:
            reasons.append("Closed below VWAP and EMA21 - uptrend broken")
    else:
        if row["High"] >= stop:
            reasons.append(f"STOP hit: stock traded at/above ${stop:.2f}")
        if row["Low"] <= target:
            reasons.append(f"TARGET hit: stock reached ${target:.2f}")
        if row["Close"] > row["vwap"] and row["Close"] > row["ema_slow"]:
            reasons.append("Closed above VWAP and EMA21 - downtrend broken")

    rev = row["rev_call"] if direction > 0 else row["rev_put"]
    if rev:
        reasons.append(f"Reversal candle: {rev.replace(',', ', ')}")

    if (direction > 0 and row["rsi"] > 80) or (direction < 0 and row["rsi"] < 20):
        reasons.append(f"RSI extreme ({row['rsi']:.0f}) - consider taking profit")

    if row["et_minute"] >= 15 * 60 + 45:
        reasons.append("15 minutes to close - don't hold short-dated options overnight")
    return reasons
