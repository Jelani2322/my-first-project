"""Candlestick pattern detection. Each function returns a boolean Series."""


def _parts(df):
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, 1e-9)
    upper = h - c.where(c > o, o)
    lower = c.where(c < o, o) - l
    return o, h, l, c, body, rng, upper, lower


def bullish_engulfing(df):
    o, h, l, c, *_ = _parts(df)
    return (c.shift() < o.shift()) & (c > o) & (c >= o.shift()) & (o <= c.shift())


def bearish_engulfing(df):
    o, h, l, c, *_ = _parts(df)
    return (c.shift() > o.shift()) & (c < o) & (c <= o.shift()) & (o >= c.shift())


def hammer(df):
    *_, body, rng, upper, lower = _parts(df)
    return (lower >= 2 * body) & (upper <= 0.25 * rng) & (body > 0.05 * rng)


def shooting_star(df):
    *_, body, rng, upper, lower = _parts(df)
    return (upper >= 2 * body) & (lower <= 0.25 * rng) & (body > 0.05 * rng)


def doji(df):
    *_, body, rng, _, _ = _parts(df)
    return body <= 0.1 * rng


def three_black_crows(df):
    o, h, l, c, *_ = _parts(df)
    down = c < o
    return down & down.shift(1, fill_value=False) & down.shift(2, fill_value=False) & (c < c.shift()) & (c.shift() < c.shift(2))


def three_white_soldiers(df):
    o, h, l, c, *_ = _parts(df)
    up = c > o
    return up & up.shift(1, fill_value=False) & up.shift(2, fill_value=False) & (c > c.shift()) & (c.shift() > c.shift(2))


def reversal_labels(df):
    """Per-bar comma-joined names of reversal candles that warn against calls / puts."""
    def join(pairs):
        out = None
        for name, series in pairs:
            col = series.fillna(False).map({True: name, False: ""})
            out = col if out is None else out.str.cat(col, sep=",")
        return out.str.strip(",").str.replace(",,+", ",", regex=True)

    against_calls = join([("bearish engulfing", bearish_engulfing(df)),
                          ("shooting star", shooting_star(df)),
                          ("three black crows", three_black_crows(df))])
    against_puts = join([("bullish engulfing", bullish_engulfing(df)),
                         ("hammer", hammer(df)),
                         ("three white soldiers", three_white_soldiers(df))])
    return against_calls, against_puts
