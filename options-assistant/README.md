# Options Assistant

A command-line helper for intraday options trading. It:

1. **Asks how much you want to make today**, then sizes trades to aim for that goal, but never
   above your risk limits. If the goal isn't realistic, it says so.
2. **Tests its strategy before suggesting anything.** Each ticker's last 60 days of 5-minute candles
   are backtested, then the result is checked two ways:
   - **Walk-forward:** history is split into 5 separate periods, and the strategy must make money in most of them.
   - **Bootstrap:** the trades are reshuffled 2,000 times to estimate whether the edge is real or just luck.
   A ticker that fails gets no suggestions that day.
3. **Watches the market and alerts you when to buy**, with calls for up-moves and **puts** for
   down-moves: the exact contract (expiry, strike), limit price, number of contracts,
   **stop loss**, **stock target price** and option target price.
4. **Monitors your trade once you tell it you're in.** On every new candle it checks your stop and target,
   trend breaks (VWAP / EMA21), reversal candlesticks (engulfing, shooting star, hammer,
   three crows/soldiers), extreme RSI and time of day. It alerts you **when to sell**, and tells you
   to move your stop to breakeven once the trade is up.

> **Not financial advice.** This is a rules-based tool, not a crystal ball. Options can lose 100% of
> what you pay. Backtests can't guarantee future results, and the market doesn't care about your daily goal.
> Paper trade it first.

## Install

Needs Python 3.10+.

```bash
cd options-assistant
pip install -r requirements.txt
python -m optionsbot setup          # account size, risk %, watchlist, phone alerts
```

## Try it right now (simulated market)

`--demo` uses a fake market that runs fast and works nights/weekends:

```bash
python -m optionsbot --demo start --goal 200 --poll 1 --auto-enter
```

`--auto-enter` paper-trades every alert so you can watch the whole cycle: buy alert → monitoring → sell alert.
(The demo market has built-in trends, so most tickers pass testing there. Real markets are harder.)

## Daily use (real market)

```bash
python -m optionsbot start            # asks "How much do you want to make today?"
```

Leave it running during market hours. When a setup appears you get an alert like:

```
#3 BUY CALLS AAPL - BUY NOW
BUY:    1x AAPL 2026-10-24 $250 CALL
        limit $3.92 (bid 3.82 / ask 3.98, delta 0.47, 2 days)
TARGET: sell when stock hits $252.91  -> option ~$5.97 (+52%)
STOP:   sell if stock hits $247.01   -> option ~$2.97 (-24%)
Max loss ~$95 | profit at target ~$205
Tested: AAPL: PASSED | 155 trades, win 51%, avg +0.20R/trade, profitable in 4/5 periods ...
Bought it? Tell the app:  python -m optionsbot enter 3 --fill <price you paid>
```

In a **second terminal**, tell the app what you did:

```bash
python -m optionsbot enter 3 --fill 3.95      # you bought alert #3 at $3.95
python -m optionsbot status                   # goal progress, open trades
python -m optionsbot close 4 --fill 5.80      # you sold position #4 at $5.80
```

The running `start` loop picks up your position and sends **SELL** alerts when the stop, target,
a trend break or a bad candle shows up. Once you hit your daily goal it stops suggesting new trades.

Other commands:

```bash
python -m optionsbot backtest SPY NVDA --trades 10   # see the test results and recent simulated trades
python -m optionsbot test-notify                     # check your phone alerts work
```

## Alerts on your phone

The easiest option is **ntfy** (free, no account): install the ntfy app, subscribe to a hard-to-guess
topic name (e.g. `jelani-options-8x2k`), and enter that topic in `setup`. Telegram and email are also
supported in `config.json` (`notify` section).

## Settings (`config.json`)

`setup` writes the common ones. Everything else falls back to `config.example.json`:

| Setting | Default | Meaning |
|---|---|---|
| `max_risk_pct_per_trade` | 2 | Max % of account you can lose on one trade |
| `max_premium_pct_per_trade` | 20 | Max % of account spent on one trade's premium |
| `max_open_positions` | 2 | Max trades open at once |
| `strategy.stop_atr_mult` / `target_atr_mult` | 1.5 / 3.0 | Stop and target distance (target = 2× risk) |
| `strategy.no_new_entries_after` | 15:15 | No new trades late in the day (ET) |
| `validation.*` | | How strict the testing is |
| `options.min/max_days_to_expiry` | 2 / 14 | Which expirations to use |
| `options.target_delta` | 0.45 | Slightly out-of-the-money contracts |

## Limitations

- **Data:** uses free Yahoo Finance data through `yfinance`. It's delayed and occasionally flaky. Always
  check the live quote in your broker before you click buy.
- **It doesn't place orders.** You trade in your broker, then tell the app with `enter` / `close`.
- Option prices at the stop and target are **estimates** (Black-Scholes using the contract's implied volatility).
- The backtest tests the stock moves the rules call for, not historical option prices, which aren't available for free.
- The strategy will often find **no** validated setups. That's the system working, not broken.

## How it works (files)

| File | Purpose |
|---|---|
| `optionsbot/strategy.py` | Entry rules (breakout + VWAP + EMA + MACD + RSI + volume) and exit rules |
| `optionsbot/patterns.py` | Candlestick pattern detection |
| `optionsbot/backtest.py` | Backtest, walk-forward and bootstrap validation |
| `optionsbot/options.py` | Black-Scholes pricing and contract selection |
| `optionsbot/planner.py` | Daily goal → position size, stop, target |
| `optionsbot/app.py` | Live watch loop: entry alerts + position monitoring |
| `optionsbot/notify.py` | Console / ntfy / Telegram / email alerts |

Run tests: `python -m pytest tests`
