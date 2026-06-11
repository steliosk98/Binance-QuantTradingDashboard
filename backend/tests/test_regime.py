"""Regime classifier on synthetic regimes."""

import numpy as np
import pandas as pd
import pytest

from app.analytics.regime import (
    classify_funding,
    classify_regime,
    classify_trend,
    classify_volatility,
    percentile_of_last,
)

RNG = np.random.default_rng(5)


def make_candles(closes: np.ndarray, intrabar: float = 0.002) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="h", tz="UTC")
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    high = np.maximum(opens, closes) * (1 + intrabar)
    low = np.minimum(opens, closes) * (1 - intrabar)
    return pd.DataFrame(
        {"open": opens, "high": high, "low": low, "close": closes, "volume": 1.0}, index=idx
    )


def test_label_helpers() -> None:
    assert classify_trend(30, 0.6) == "Trending"
    assert classify_trend(30, 0.4) == "Mean-reverting"
    assert classify_trend(10, 0.5) == "Ranging"
    assert classify_trend(None, 0.5) == "Unknown"
    assert classify_volatility(90) == "High Vol"
    assert classify_volatility(10) == "Low Vol"
    assert classify_volatility(50) == "Normal Vol"
    assert classify_funding(95) == "Crowded Longs"
    assert classify_funding(5) == "Crowded Shorts"
    assert classify_funding(50) == "Balanced"


def test_percentile_of_last() -> None:
    s = pd.Series(list(range(100)))
    assert percentile_of_last(s) == pytest.approx(99.0)
    assert percentile_of_last(pd.Series([1.0, 2.0])) is None


def test_trending_regime_detected() -> None:
    # Strong persistent uptrend
    closes = 100 * np.exp(np.cumsum(RNG.normal(0.004, 0.004, 1500)))
    regime = classify_regime(make_candles(closes), None)
    assert regime.trend == "Trending"
    assert regime.adx is not None and regime.adx > 25


def test_mean_reverting_regime_detected() -> None:
    # Strong AR(1) mean reversion around 100
    n = 1500
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = -0.7 * x[i - 1] + RNG.normal(0, 0.01)
    closes = 100 * np.exp(x)
    regime = classify_regime(make_candles(closes), None)
    assert regime.trend == "Mean-reverting"
    assert regime.hurst is not None and regime.hurst < 0.45


def test_funding_extremity() -> None:
    closes = 100 * np.exp(np.cumsum(RNG.normal(0, 0.005, 600)))
    funding = pd.Series([0.0001] * 200 + [0.001])  # last value is extreme high
    regime = classify_regime(make_candles(closes), funding)
    assert regime.funding == "Crowded Longs"


def test_short_history_is_unknown() -> None:
    closes = 100 + RNG.normal(0, 1, 50)
    regime = classify_regime(make_candles(closes), None)
    assert regime.trend == "Unknown"
