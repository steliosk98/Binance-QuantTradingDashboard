"""Statistical / quant metrics (spec §4.2)."""

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.tsa.stattools import adfuller, coint

#: Bars per year for annualization, per interval.
ANNUALIZATION: dict[str, float] = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}


def _log(series: pd.Series) -> pd.Series:
    return pd.Series(np.log(series.to_numpy(dtype=float)), index=series.index)


def log_returns(close: pd.Series) -> pd.Series:
    return _log(close / close.shift(1)).dropna()


def realized_vol_c2c(close: pd.Series, window: int, interval: str) -> pd.Series:
    """Annualized close-to-close volatility."""
    rets = _log(close / close.shift(1))
    return rets.rolling(window).std(ddof=1) * math.sqrt(ANNUALIZATION[interval])


def realized_vol_parkinson(
    high: pd.Series, low: pd.Series, window: int, interval: str
) -> pd.Series:
    hl2 = _log(high / low) ** 2
    factor = 1.0 / (4.0 * math.log(2.0))
    var = (factor * hl2).rolling(window).mean()
    return var.pow(0.5) * math.sqrt(ANNUALIZATION[interval])


def realized_vol_garman_klass(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int,
    interval: str,
) -> pd.Series:
    hl = 0.5 * _log(high / low) ** 2
    co = (2 * math.log(2) - 1) * _log(close / open_) ** 2
    var = (hl - co).rolling(window).mean().clip(lower=0)
    return var.pow(0.5) * math.sqrt(ANNUALIZATION[interval])


def distribution_summary(returns: pd.Series, bins: int = 50) -> dict[str, Any]:
    arr = returns.dropna().to_numpy()
    if len(arr) < 8:
        return {"count": int(len(arr))}
    counts, edges = np.histogram(arr, bins=bins)
    jb = sps.jarque_bera(arr)
    jb_stat, jb_p = float(jb.statistic), float(jb.pvalue)
    # QQ data vs normal
    osm, osr = sps.probplot(arr, dist="norm")[0]
    return {
        "count": int(len(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)),
        "skew": float(sps.skew(arr)),
        "kurtosis": float(sps.kurtosis(arr)),  # excess
        "jarque_bera_stat": float(jb_stat),
        "jarque_bera_p": float(jb_p),
        "histogram": {
            "counts": counts.tolist(),
            "edges": edges.tolist(),
        },
        "qq": {
            "theoretical": np.asarray(osm).tolist(),
            "sample": np.asarray(osr).tolist(),
        },
    }


def correlation_matrix(returns: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Pearson correlation of the last `window_days` daily log returns."""
    tail = returns.tail(window_days)
    return tail.corr()


def rolling_beta(asset_returns: pd.Series, btc_returns: pd.Series, window: int) -> pd.Series:
    cov = asset_returns.rolling(window).cov(btc_returns)
    var = btc_returns.rolling(window).var()
    return cov / var


def hurst_rs(series: pd.Series, min_chunk: int = 8) -> float:
    """Hurst exponent via rescaled range (R/S) analysis."""
    arr = series.dropna().to_numpy()
    n = len(arr)
    if n < 32:
        return float("nan")
    sizes = []
    size = n
    while size >= min_chunk:
        sizes.append(size)
        size //= 2
    log_sizes, log_rs = [], []
    for s in sizes:
        chunks = n // s
        rs_values = []
        for i in range(chunks):
            chunk = arr[i * s : (i + 1) * s]
            dev = chunk - chunk.mean()
            z = np.cumsum(dev)
            r = z.max() - z.min()
            sd = chunk.std(ddof=1)
            if sd > 0 and r > 0:
                rs_values.append(r / sd)
        if rs_values:
            log_sizes.append(math.log(s))
            log_rs.append(math.log(float(np.mean(rs_values))))
    if len(log_sizes) < 3:
        return float("nan")
    slope = float(np.polyfit(log_sizes, log_rs, 1)[0])
    return slope


def rolling_hurst(returns: pd.Series, window: int = 256, step: int = 16) -> pd.Series:
    """Hurst over a rolling window, evaluated every `step` bars."""
    values: dict[Any, float] = {}
    arr = returns.dropna()
    for end in range(window, len(arr) + 1, step):
        chunk = arr.iloc[end - window : end]
        values[arr.index[end - 1]] = hurst_rs(chunk)
    return pd.Series(values, dtype=float)


def zscore(close: pd.Series, window: int = 50) -> pd.Series:
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=1)
    return (close - mean) / std


def adf_test(series: pd.Series) -> dict[str, float]:
    arr = series.dropna().to_numpy()
    stat, pvalue, usedlag, nobs, *_ = adfuller(arr, autolag="AIC")
    return {"stat": float(stat), "pvalue": float(pvalue), "nobs": float(nobs)}


def engle_granger(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    """Engle-Granger cointegration test + hedge ratio + spread z-score."""
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    stat, pvalue, crit_raw = coint(df["a"], df["b"])
    crit = np.asarray(crit_raw, dtype=float)
    # Hedge ratio via OLS a = beta*b + c
    beta, intercept = np.polyfit(df["b"].to_numpy(), df["a"].to_numpy(), 1)
    spread = df["a"] - (beta * df["b"] + intercept)
    spread_z = (spread - spread.mean()) / spread.std(ddof=1)
    return {
        "stat": float(stat),
        "pvalue": float(pvalue),
        "critical_values": {"1%": float(crit[0]), "5%": float(crit[1]), "10%": float(crit[2])},
        "hedge_ratio": float(beta),
        "spread_z": spread_z,
    }
