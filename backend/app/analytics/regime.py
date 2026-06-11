"""Regime classifier (spec §4.5): trend state, volatility percentile,
funding extremity — composed into simple labels per symbol.
"""

import math
from dataclasses import asdict, dataclass

import pandas as pd

from app.analytics.indicators import adx
from app.analytics.stats import hurst_rs, log_returns, realized_vol_c2c

ADX_TRENDING = 25.0
HURST_TRENDING = 0.55
HURST_MEAN_REVERTING = 0.45


@dataclass
class Regime:
    trend: str  # "Trending" | "Ranging" | "Mean-reverting" | "Unknown"
    volatility: str  # "Low Vol" | "Normal Vol" | "High Vol" | "Unknown"
    funding: str  # "Crowded Longs" | "Crowded Shorts" | "Balanced" | "Unknown"
    adx: float | None
    hurst: float | None
    vol_percentile: float | None
    funding_percentile: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_trend(adx_value: float | None, hurst_value: float | None) -> str:
    """Anti-persistent returns trump everything; then ADX (directional
    strength) or persistent returns (Hurst) mark a trend.

    Note: Hurst is computed on *returns*, so a steady drift with uncorrelated
    increments shows H≈0.5 but high ADX — still a trend.
    """
    if adx_value is None or hurst_value is None or math.isnan(adx_value) or math.isnan(hurst_value):
        return "Unknown"
    if hurst_value <= HURST_MEAN_REVERTING:
        return "Mean-reverting"
    if adx_value >= ADX_TRENDING or hurst_value >= HURST_TRENDING:
        return "Trending"
    return "Ranging"


def classify_volatility(percentile: float | None) -> str:
    if percentile is None or math.isnan(percentile):
        return "Unknown"
    if percentile >= 70:
        return "High Vol"
    if percentile <= 30:
        return "Low Vol"
    return "Normal Vol"


def classify_funding(percentile: float | None) -> str:
    """Percentile of the current funding rate within its trailing history."""
    if percentile is None or math.isnan(percentile):
        return "Unknown"
    if percentile >= 85:
        return "Crowded Longs"
    if percentile <= 15:
        return "Crowded Shorts"
    return "Balanced"


def percentile_of_last(series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) < 10:
        return None
    last = s.iloc[-1]
    return float((s < last).mean() * 100)


def classify_regime(
    candles: pd.DataFrame,
    funding_rates: pd.Series | None,
    interval: str = "1h",
    vol_window: int = 30,
) -> Regime:
    """Classify from OHLCV candles (≥ ~300 bars recommended) + funding history."""
    if len(candles) < 100:
        return Regime("Unknown", "Unknown", "Unknown", None, None, None, None)

    high, low, close = candles["high"], candles["low"], candles["close"]
    adx_series = adx(high, low, close).dropna()
    adx_value = float(adx_series.iloc[-1]) if not adx_series.empty else None

    rets = log_returns(close)
    hurst_value = hurst_rs(rets.tail(512))
    if math.isnan(hurst_value):
        hurst_value = None  # type: ignore[assignment]

    vol_series = realized_vol_c2c(close, vol_window, interval)
    vol_pct = percentile_of_last(vol_series)

    funding_pct = percentile_of_last(funding_rates) if funding_rates is not None else None

    return Regime(
        trend=classify_trend(adx_value, hurst_value),
        volatility=classify_volatility(vol_pct),
        funding=classify_funding(funding_pct),
        adx=adx_value,
        hurst=hurst_value,
        vol_percentile=vol_pct,
        funding_percentile=funding_pct,
    )
