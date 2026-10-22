import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df, n=14):
    prev = df["Close"].shift()
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def macd_hist(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, signal)


def vwap(df):
    """Session VWAP, reset each trading day."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    pv = typical * df["Volume"]
    day = df.index.date
    return pv.groupby(day).cumsum() / df["Volume"].groupby(day).cumsum().replace(0, np.nan)


def add_indicators(df, s):
    df = df.copy()
    df["ema_fast"] = ema(df["Close"], s["ema_fast"])
    df["ema_slow"] = ema(df["Close"], s["ema_slow"])
    df["rsi"] = rsi(df["Close"], s["rsi_len"])
    df["atr"] = atr(df, s["atr_len"])
    df["macd_hist"] = macd_hist(df["Close"])
    df["vwap"] = vwap(df).fillna(df["Close"])
    lb = s["breakout_lookback"]
    df["range_high"] = df["High"].shift(1).rolling(lb).max()
    df["range_low"] = df["Low"].shift(1).rolling(lb).min()
    df["vol_avg"] = df["Volume"].rolling(20).mean()
    return df
