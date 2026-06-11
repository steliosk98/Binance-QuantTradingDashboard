"""Technical indicators (spec §4.1) — pandas/numpy implementations.

All functions take/return pandas Series/DataFrames indexed like the input.
Formulas follow the standard definitions used by TradingView:
- RSI / ATR use Wilder smoothing (RMA).
- MACD uses EMA(fast) − EMA(slow) with EMA(signal).
"""

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seeded with the SMA of the first `period` values,
    then avg[i] = (avg[i-1]*(period-1) + x[i]) / period. Matches TradingView.
    """
    arr = series.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    # Find the first window of `period` consecutive non-NaN values.
    valid = ~np.isnan(arr)
    start = -1
    run = 0
    for i, ok in enumerate(valid):
        run = run + 1 if ok else 0
        if run == period:
            start = i
            break
    if start >= 0:
        out[start] = arr[start - period + 1 : start + 1].mean()
        for i in range(start + 1, len(arr)):
            x = arr[i] if valid[i] else 0.0
            out[i] = (out[i - 1] * (period - 1) + x) / period
    return pd.Series(out, index=series.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss != 0, 100.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": macd_line - signal_line}
    )


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period).std(ddof=0)
    return pd.DataFrame({"middle": mid, "upper": mid + num_std * std, "lower": mid - num_std * std})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return rma(true_range(high, low, close), period)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0).fillna(0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0).fillna(0.0)
    tr = true_range(high, low, close)
    atr_ = rma(tr, period)
    plus_di = 100 * rma(plus_dm, period) / atr_
    minus_di = 100 * rma(minus_dm, period) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return rma(dx, period)


def vwap_session(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Session VWAP, resetting at each UTC day boundary."""
    typical = (high + low + close) / 3
    day = pd.Series(pd.DatetimeIndex(close.index).normalize(), index=close.index)
    pv = (typical * volume).groupby(day).cumsum()
    vv = volume.groupby(day).cumsum()
    return pv / vv


def vwap_rolling(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20
) -> pd.Series:
    typical = (high + low + close) / 3
    pv = (typical * volume).rolling(period).sum()
    vv = volume.rolling(period).sum()
    return pv / vv


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = pd.Series(np.sign(close.diff().to_numpy()), index=close.index).fillna(0.0)
    out: pd.Series = (direction * volume).cumsum()
    return out


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3, smooth: int = 3
) -> pd.DataFrame:
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    raw_k = 100 * (close - lowest) / (highest - lowest)
    k_line = raw_k.rolling(smooth).mean()
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


def ichimoku_cloud(
    high: pd.Series,
    low: pd.Series,
    conversion: int = 9,
    base: int = 26,
    span_b: int = 52,
    displacement: int = 26,
) -> pd.DataFrame:
    """Cloud only (senkou span A/B, displaced forward)."""

    def midline(period: int) -> pd.Series:
        return (high.rolling(period).max() + low.rolling(period).min()) / 2

    tenkan = midline(conversion)
    kijun = midline(base)
    senkou_a = ((tenkan + kijun) / 2).shift(displacement)
    senkou_b = midline(span_b).shift(displacement)
    return pd.DataFrame({"senkou_a": senkou_a, "senkou_b": senkou_b})


def volume_profile(close: pd.Series, volume: pd.Series, bins: int = 24) -> pd.DataFrame:
    """Price-bucketed volume histogram over the given window."""
    lo, hi = float(close.min()), float(close.max())
    if lo == hi:
        return pd.DataFrame({"price": [lo], "volume": [float(volume.sum())]})
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.digitize(close.to_numpy(), edges) - 1, 0, bins - 1)
    vols = np.zeros(bins)
    np.add.at(vols, idx, volume.to_numpy())
    centers = (edges[:-1] + edges[1:]) / 2
    return pd.DataFrame({"price": centers, "volume": vols})
