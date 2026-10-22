"""Market data providers.

YahooProvider  - real delayed market data + option chains via yfinance (free).
DemoProvider   - synthetic market so you can try the app any time (nights, weekends).
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .options import bs_price


class YahooProvider:
    name = "yahoo"

    def __init__(self, interval="5m", period="60d"):
        import yfinance as yf
        self.yf = yf
        self.interval, self.period = interval, period

    def bars(self, ticker):
        df = self.yf.Ticker(ticker).history(period=self.period, interval=self.interval, prepost=False)
        if df is None or df.empty:
            raise RuntimeError(f"no price data for {ticker}")
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        # the newest bar is still forming during market hours; only act on closed candles
        return df.iloc[:-1] if len(df) > 1 else df

    def expiries(self, ticker):
        return [date.fromisoformat(e) for e in self.yf.Ticker(ticker).options]

    def chain(self, ticker, expiry, kind):
        oc = self.yf.Ticker(ticker).option_chain(expiry.isoformat())
        df = (oc.calls if kind == "call" else oc.puts).copy()
        return df[["contractSymbol", "strike", "bid", "ask", "lastPrice", "impliedVolatility",
                   "openInterest", "volume"]].fillna(0)


class DemoProvider:
    """Random-walk market with trending regimes. Each call to bars() reveals one
    more candle, so the watch loop behaves like a live session."""
    name = "demo"

    def __init__(self, tickers=("SPY", "QQQ", "AAPL", "NVDA", "TSLA"), days=60, seed=11, start_live_at=None):
        self.data, self.cursor = {}, {}
        rng = np.random.default_rng(seed)
        for t in tickers:
            self.data[t] = self._make(rng, days, start_price=float(rng.uniform(80, 500)))
            per_day = 78
            self.cursor[t] = start_live_at if start_live_at is not None else len(self.data[t]) - per_day + 12
        self.today = self.data[tickers[0]].index[-1].tz_convert("America/New_York").date()

    @staticmethod
    def _make(rng, days, start_price):
        idx = []
        d = pd.Timestamp("2026-07-01")
        while len(idx) < days * 78:
            if d.weekday() < 5:
                idx.extend(pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=78, freq="5min",
                                         tz="America/New_York"))
            d += pd.Timedelta(days=1)
        n = len(idx)
        drift = np.zeros(n)
        regime = 0.0
        for i in range(n):
            if i % 26 == 0:
                regime = rng.choice([-1, 0, 0, 1]) * 0.0006
            drift[i] = regime
        rets = drift + rng.normal(0, 0.0018, n)
        close = start_price * np.exp(np.cumsum(rets))
        open_ = np.concatenate([[start_price], close[:-1]]) * (1 + rng.normal(0, 0.0003, n))
        wick = np.abs(rng.normal(0, 0.0012, n)) * close
        high = np.maximum(open_, close) + wick
        low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.0012, n)) * close
        vol = rng.integers(50_000, 400_000, n) * (1 + 3 * np.abs(rets) / 0.0018)
        return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
                            index=pd.DatetimeIndex(idx).tz_convert("UTC"))

    def bars(self, ticker):
        if ticker not in self.data:
            raise RuntimeError(f"demo has no data for {ticker}")
        c = self.cursor[ticker] = min(self.cursor[ticker] + 1, len(self.data[ticker]))
        return self.data[ticker].iloc[:c]

    def expiries(self, ticker):
        return [self.today + timedelta(days=k) for k in (1, 3, 7, 10, 14, 21, 30)]

    def chain(self, ticker, expiry, kind, iv=0.30, r=0.04):
        spot = float(self.data[ticker]["Close"].iat[self.cursor[ticker] - 1])
        step = 1 if spot < 150 else 5
        strikes = np.arange(round(spot * 0.9 / step) * step, spot * 1.1, step)
        t = max((expiry - self.today).days, 0.5) / 365
        rows = []
        for k in strikes:
            mid = bs_price(spot, k, t, r, iv, kind)
            spread = max(0.02, mid * 0.04)
            rows.append({"contractSymbol": f"{ticker}{expiry:%y%m%d}{kind[0].upper()}{int(k * 1000):08d}",
                         "strike": float(k), "bid": round(max(mid - spread / 2, 0.01), 2),
                         "ask": round(mid + spread / 2, 2), "lastPrice": round(mid, 2),
                         "impliedVolatility": iv, "openInterest": 1500, "volume": 400})
        return pd.DataFrame(rows)


def make_provider(cfg, demo=False):
    if demo:
        return DemoProvider(tickers=tuple(cfg["watchlist"]))
    return YahooProvider(cfg["bar_interval"], cfg["history_period"])
