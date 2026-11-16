"""Technical indicators. All functions are causal: the value at row t uses only rows <= t."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    """Exponential moving average with alpha = 2/(n+1), seeded with the first value (adjust=False)."""
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing (alpha = 1/n), seeded with the simple mean of the first n values."""
    arr = s.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(arr))
    if valid.size < n:
        return pd.Series(out, index=s.index)
    start = valid[0]
    seed_end = start + n
    if seed_end > arr.size or np.isnan(arr[start:seed_end]).any():
        return pd.Series(out, index=s.index)
    prev = arr[start:seed_end].mean()
    out[seed_end - 1] = prev
    for i in range(seed_end, arr.size):
        x = arr[i]
        prev = prev if np.isnan(x) else (prev * (n - 1) + x) / n
        out[i] = prev
    return pd.Series(out, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI = 100 - 100/(1+RS), RS = smoothed average gain / smoothed average loss."""
    d = close.diff()
    gain = wilder(d.clip(lower=0).where(d.notna()), n)
    loss = wilder((-d.clip(upper=0)).where(d.notna()), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out = out.where(loss != 0, 100.0).where(gain.notna())
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Bands use the population standard deviation (ddof=0), as in Bollinger's definition."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower,
                         "pct_b": (close - lower) / (upper - lower), "zscore": (close - mid) / sd})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 14) -> pd.Series:
    tp = (high + low + close) / 3.0
    flow = tp * volume
    d = tp.diff()
    pos = flow.where(d > 0, 0.0).rolling(n, min_periods=n).sum()
    neg = flow.where(d < 0, 0.0).rolling(n, min_periods=n).sum()
    out = 100 - 100 / (1 + pos / neg)
    out = out.where(neg != 0, 100.0)
    out.iloc[:n] = np.nan  # the first diff is undefined, so n+1 bars are required
    return out


def rolling_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 20) -> pd.Series:
    """Rolling n-day VWAP on typical price. This is a DAILY-BAR APPROXIMATION, not an intraday session VWAP."""
    tp = (high + low + close) / 3.0
    return (tp * volume).rolling(n, min_periods=n).sum() / volume.rolling(n, min_periods=n).sum()


def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series, conv: int = 9, base: int = 26, span_b: int = 52) -> pd.DataFrame:
    """Ichimoku lines aligned causally: span_a/span_b at row t are the cloud values that APPLY to t
    (i.e. computed `base` bars earlier). The chikou (lagging) span is omitted because plotting it
    requires shifting price backwards, which is not usable as a signal input."""
    tenkan = (high.rolling(conv).max() + low.rolling(conv).min()) / 2
    kijun = (high.rolling(base).max() + low.rolling(base).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(base)
    span_b_line = ((high.rolling(span_b).max() + low.rolling(span_b).min()) / 2).shift(base)
    return pd.DataFrame({"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b_line})


def relative_strength(close: pd.Series, bench: pd.Series) -> pd.Series:
    """Ratio of the stock to the benchmark, rebased to 1.0 at the first common date."""
    b = bench.reindex(close.index).ffill()
    ratio = close / b
    first = ratio.first_valid_index()
    return ratio / ratio.loc[first] if first is not None else ratio


def realized_vol(close: pd.Series, n: int = 21, periods: int = 252) -> pd.Series:
    return np.log(close).diff().rolling(n, min_periods=n).std() * np.sqrt(periods)


def compute_all(df: pd.DataFrame, bench: pd.Series | None = None) -> pd.DataFrame:
    """Indicator frame for one stock (expects open/high/low/close/adj_close/volume)."""
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    out = pd.DataFrame(index=df.index)
    for n in (20, 50, 200):
        out[f"sma_{n}"] = sma(c, n)
    for n in (12, 26, 50):
        out[f"ema_{n}"] = ema(c, n)
    out["rsi_14"] = rsi(c, 14)
    m = macd(c)
    out["macd"], out["macd_signal"], out["macd_hist"] = m["macd"], m["signal"], m["hist"]
    b = bollinger(c)
    out["bb_mid"], out["bb_upper"], out["bb_lower"], out["bb_pct_b"], out["bb_z"] = b["mid"], b["upper"], b["lower"], b["pct_b"], b["zscore"]
    out["atr_14"] = atr(h, l, c, 14)
    out["obv"] = obv(c, v)
    out["mfi_14"] = mfi(h, l, c, v, 14)
    out["vwap_20"] = rolling_vwap(h, l, c, v, 20)
    ich = ichimoku(h, l, c)
    for k in ich.columns:
        out[f"ichi_{k}"] = ich[k]
    out["rvol_21"] = realized_vol(df["adj_close"], 21)
    out["vol_ratio_20"] = v / v.rolling(20, min_periods=20).mean().shift(1)
    out["high_252"] = c.rolling(252, min_periods=120).max()
    out["donchian_high_55"] = h.rolling(55, min_periods=55).max().shift(1)
    out["donchian_low_20"] = l.rolling(20, min_periods=20).min().shift(1)
    if bench is not None:
        out["rel_strength"] = relative_strength(df["adj_close"], bench)
    return out
