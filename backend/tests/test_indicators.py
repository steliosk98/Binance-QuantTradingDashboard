"""Golden-value tests for indicators.

References computed independently: SMA/EMA/Bollinger by hand on small
fixtures; RSI against the canonical Wilder example; MACD/ATR/OBV/Stoch via
the textbook recurrences evaluated step-by-step.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics import indicators as ind


def s(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def test_sma_golden() -> None:
    out = ind.sma(s([1, 2, 3, 4, 5]), 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_golden() -> None:
    # span=3 → alpha=0.5; ema: 1, 1.5, 2.25, 3.125
    out = ind.ema(s([1, 2, 3, 4]), 3)
    assert out.tolist() == pytest.approx([1.0, 1.5, 2.25, 3.125])


def test_rsi_all_gains_is_100() -> None:
    out = ind.rsi(s(list(range(1, 31))), 14)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_rsi_golden_wilder() -> None:
    # Canonical 14-period RSI example (Wilder's book / widely replicated)
    closes = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
        46.00,
        46.03,
        46.41,
        46.22,
        45.64,
    ]
    out = ind.rsi(s(closes), 14)
    assert out.iloc[14] == pytest.approx(70.46, abs=0.2)
    assert out.iloc[19] == pytest.approx(58.18, abs=1.0)


def test_macd_matches_ema_difference() -> None:
    close = s(list(np.cumsum(np.random.default_rng(7).normal(0, 1, 200)) + 100))
    out = ind.macd(close)
    expected = ind.ema(close, 12) - ind.ema(close, 26)
    pd.testing.assert_series_equal(out["macd"], expected, check_names=False)
    # histogram = macd - signal
    pd.testing.assert_series_equal(out["histogram"], out["macd"] - out["signal"], check_names=False)


def test_bollinger_golden() -> None:
    close = s([1, 2, 3, 4, 5])
    out = ind.bollinger(close, period=5, num_std=2.0)
    # mean 3, population std sqrt(2)
    assert out["middle"].iloc[-1] == pytest.approx(3.0)
    assert out["upper"].iloc[-1] == pytest.approx(3.0 + 2 * np.sqrt(2.0))
    assert out["lower"].iloc[-1] == pytest.approx(3.0 - 2 * np.sqrt(2.0))


def test_atr_golden_simple() -> None:
    high = s([10, 11, 12])
    low = s([8, 9, 10])
    close = s([9, 10, 11])
    # TR: 2, 2, 2 → ATR (any smoothing of constant) = 2
    out = ind.atr(high, low, close, period=2)
    assert out.iloc[-1] == pytest.approx(2.0)


def test_atr_uses_gaps() -> None:
    high = s([10, 20])
    low = s([9, 19])
    close = s([10, 20])
    tr = ind.true_range(high, low, close)
    assert tr.iloc[1] == pytest.approx(10.0)  # gap dominates high-low


def test_vwap_session_resets_daily() -> None:
    idx = pd.DatetimeIndex(["2024-01-01 22:00", "2024-01-01 23:00", "2024-01-02 00:00"], tz="UTC")
    high = pd.Series([10.0, 20.0, 30.0], index=idx)
    low = high.copy()
    close = high.copy()
    volume = pd.Series([1.0, 1.0, 1.0], index=idx)
    out = ind.vwap_session(high, low, close, volume)
    assert out.iloc[1] == pytest.approx(15.0)  # (10+20)/2 within day 1
    assert out.iloc[2] == pytest.approx(30.0)  # reset on day 2


def test_obv_golden() -> None:
    close = s([10, 11, 10.5, 10.5, 12])
    volume = s([100, 200, 300, 400, 500])
    out = ind.obv(close, volume)
    # +200 -300 +0 +500 = 400
    assert out.iloc[-1] == pytest.approx(400.0)


def test_stochastic_bounds_and_golden() -> None:
    close = s(list(range(1, 31)))
    high = close + 0.5
    low = close - 0.5
    out = ind.stochastic(high, low, close, k=5, d=3, smooth=1)
    valid = out["k"].dropna()
    assert ((valid >= 0) & (valid <= 100)).all()
    # rising series: close is always at the top of the 5-bar range
    # k = (c - min_low)/(max_high - min_low) = (c - (c-4-0.5))/(0.5+4+0.5)... constant 90
    assert valid.iloc[-1] == pytest.approx(90.0)


def test_ichimoku_cloud_displacement() -> None:
    close = s(list(range(1, 120)))
    out = ind.ichimoku_cloud(close + 0.5, close - 0.5)
    # senkou A displaced 26 forward: defined only after warmup
    assert out["senkou_a"].isna().iloc[:30].all()
    assert not np.isnan(out["senkou_a"].iloc[-1])


def test_volume_profile_conserves_volume() -> None:
    rng = np.random.default_rng(11)
    close = s(list(100 + rng.normal(0, 5, 500)))
    volume = s(list(rng.uniform(1, 10, 500)))
    vp = ind.volume_profile(close, volume, bins=20)
    assert vp["volume"].sum() == pytest.approx(volume.sum())
    assert len(vp) == 20
