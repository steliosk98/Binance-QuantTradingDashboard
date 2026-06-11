"""Statistical functions vs scipy/statsmodels behavior on synthetic series."""

import math

import numpy as np
import pandas as pd
import pytest

from app.analytics import stats as st


def series(values: np.ndarray, freq: str = "h") -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


RNG = np.random.default_rng(42)


def test_log_returns() -> None:
    s = series(np.array([100.0, 110.0, 99.0]))
    out = st.log_returns(s)
    assert out.iloc[0] == pytest.approx(math.log(1.1))
    assert len(out) == 2


def test_c2c_vol_matches_known_sigma() -> None:
    # Hourly returns with sigma=1%/bar → annualized ≈ 1% * sqrt(8760)
    rets = RNG.normal(0, 0.01, 5000)
    prices = series(100 * np.exp(np.cumsum(rets)))
    vol = st.realized_vol_c2c(prices, window=2000, interval="1h").dropna()
    expected = 0.01 * math.sqrt(8760)
    assert vol.iloc[-1] == pytest.approx(expected, rel=0.1)


def test_parkinson_and_gk_close_to_c2c_on_gbm() -> None:
    # Simulate GBM with intrabar extremes approximated by many sub-steps
    n_bars, sub = 800, 50
    sigma_bar = 0.01
    sub_rets = RNG.normal(0, sigma_bar / math.sqrt(sub), (n_bars, sub))
    log_paths = np.cumsum(sub_rets, axis=1) + np.log(100)
    log_paths += np.concatenate([[0], np.cumsum(sub_rets.sum(axis=1))[:-1]])[:, None]
    opens = series(np.exp(log_paths[:, 0]))
    highs = series(np.exp(log_paths.max(axis=1)))
    lows = series(np.exp(log_paths.min(axis=1)))
    closes = series(np.exp(log_paths[:, -1]))

    c2c = st.realized_vol_c2c(closes, 400, "1h").dropna().iloc[-1]
    park = st.realized_vol_parkinson(highs, lows, 400, "1h").dropna().iloc[-1]
    gk = st.realized_vol_garman_klass(opens, highs, lows, closes, 400, "1h").dropna().iloc[-1]
    assert park == pytest.approx(c2c, rel=0.25)
    assert gk == pytest.approx(c2c, rel=0.25)


def test_distribution_summary_normal_sample() -> None:
    rets = series(RNG.normal(0, 0.01, 4000))
    summary = st.distribution_summary(rets)
    assert abs(summary["skew"]) < 0.15
    assert abs(summary["kurtosis"]) < 0.3
    assert summary["jarque_bera_p"] > 0.01  # normality not rejected
    assert sum(summary["histogram"]["counts"]) == 4000
    assert len(summary["qq"]["theoretical"]) == 4000


def test_hurst_white_noise_near_half() -> None:
    noise = series(RNG.normal(0, 1, 4096))
    h = st.hurst_rs(noise)
    assert 0.4 < h < 0.6


def test_hurst_trending_above_06() -> None:
    # Strong drift → persistent series → high Hurst on the level changes?
    # Per spec: trending random walk with drift should give H > 0.6.
    drift = 0.5
    walk_increments = RNG.normal(drift, 0.1, 4096)  # heavily drifted increments
    h = st.hurst_rs(series(walk_increments).cumsum())
    assert h > 0.6


def test_zscore_properties() -> None:
    s = series(RNG.normal(100, 5, 1000))
    z = st.zscore(s, window=100).dropna()
    assert abs(z.mean()) < 0.3
    assert z.std() == pytest.approx(1.0, abs=0.3)


def test_adf_stationary_vs_random_walk() -> None:
    stationary = series(RNG.normal(0, 1, 1000))
    walk = series(RNG.normal(0, 1, 1000).cumsum())
    assert st.adf_test(stationary)["pvalue"] < 0.01
    assert st.adf_test(walk)["pvalue"] > 0.10


def test_engle_granger_cointegrated_pair() -> None:
    # b is a random walk; a = 2*b + stationary noise → cointegrated
    b = series(np.cumsum(RNG.normal(0, 1, 2000)) + 100)
    a = 2 * b + series(RNG.normal(0, 1, 2000))
    result = st.engle_granger(a, b)
    assert result["pvalue"] < 0.05
    assert result["hedge_ratio"] == pytest.approx(2.0, abs=0.1)
    z = result["spread_z"]
    assert abs(z.mean()) < 0.1


def test_engle_granger_independent_walks_not_cointegrated() -> None:
    a = series(np.cumsum(RNG.normal(0, 1, 2000)))
    b = series(np.cumsum(RNG.normal(0, 1, 2000)))
    result = st.engle_granger(a, b)
    assert result["pvalue"] > 0.05


def test_correlation_matrix_and_beta() -> None:
    base = RNG.normal(0, 0.02, 500)
    btc = series(base, freq="D")
    eth = series(0.9 * base + RNG.normal(0, 0.005, 500), freq="D")
    rets = pd.DataFrame({"BTCUSDT": btc, "ETHUSDT": eth})
    corr = st.correlation_matrix(rets, 90)
    assert corr.loc["BTCUSDT", "ETHUSDT"] > 0.9
    beta = st.rolling_beta(rets["ETHUSDT"], rets["BTCUSDT"], 90).dropna()
    assert beta.iloc[-1] == pytest.approx(0.9, abs=0.1)
