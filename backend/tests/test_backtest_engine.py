"""Engine correctness on synthetic data + metric formulas vs hand-computed."""

import math

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import compute_metrics, max_drawdown, run_backtest
from app.backtest.strategies import STRATEGIES
from app.backtest.walkforward import param_grid, run_walk_forward, split_windows


def make_df(closes: list[float] | np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="h", tz="UTC")
    closes = np.asarray(closes, dtype=float)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.001,
            "low": np.minimum(opens, closes) * 0.999,
            "close": closes,
            "volume": 1.0,
        },
        index=idx,
    )


def test_buy_and_hold_matches_price_ratio_net_of_fees() -> None:
    closes = [100, 110, 105, 120, 130]
    df = make_df(closes)
    positions = pd.Series(1.0, index=df.index)
    result = run_backtest(df, positions, "1h", fee_bps=10, slippage_bps=5)
    # Held from bar 1 (shift). Entry cost (15bps) is charged additively on the
    # entry bar's return; afterwards equity compounds with the price ratio.
    expected = (110 / 100 - 0.0015) * (130 / 110)
    assert result.equity.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_flat_positions_no_pnl_no_costs() -> None:
    df = make_df(list(100 + np.random.default_rng(3).normal(0, 5, 100)))
    result = run_backtest(df, pd.Series(0.0, index=df.index), "1h")
    assert result.equity.iloc[-1] == pytest.approx(1.0)
    assert result.metrics["n_trades"] == 0
    assert result.metrics["exposure"] == 0.0


def test_perfect_foresight_on_sine_wave_profits() -> None:
    t = np.linspace(0, 8 * np.pi, 400)
    closes = 100 + 10 * np.sin(t)
    df = make_df(closes)
    # Cheating strategy: target at bar t = sign of bar t+1's return; the
    # engine shifts by one, so the position is held exactly during the bar
    # we peeked at.
    next_ret = df["close"].shift(-1) / df["close"] - 1
    positions = pd.Series(np.sign(next_ret.to_numpy()), index=df.index).fillna(0.0)
    result = run_backtest(df, positions, "1h", fee_bps=0, slippage_bps=0)
    assert result.equity.iloc[-1] > 4.0  # massively profitable
    assert result.metrics["sharpe"] is not None and result.metrics["sharpe"] > 5


def test_no_lookahead_shift() -> None:
    # A strategy that goes long on the bar BEFORE a known jump must not
    # capture the jump if it only decides on that bar's close... it should
    # capture it (decided at t, held during t+1). Decided AT the jump bar
    # captures nothing.
    closes = [100.0, 100.0, 200.0, 200.0]
    df = make_df(closes)
    # Decide long at bar index 2 (the jump bar) — too late, no profit.
    late = pd.Series([0.0, 0.0, 1.0, 1.0], index=df.index)
    result_late = run_backtest(df, late, "1h", fee_bps=0, slippage_bps=0)
    assert result_late.equity.iloc[-1] == pytest.approx(1.0)
    # Decide long at bar 1 → holds during bar 2 → captures the 2x.
    early = pd.Series([0.0, 1.0, 1.0, 1.0], index=df.index)
    result_early = run_backtest(df, early, "1h", fee_bps=0, slippage_bps=0)
    assert result_early.equity.iloc[-1] == pytest.approx(2.0)


def test_short_position_profits_from_decline() -> None:
    closes = [100, 90, 81]
    df = make_df(closes)
    positions = pd.Series(-1.0, index=df.index)
    result = run_backtest(df, positions, "1h", fee_bps=0, slippage_bps=0)
    # short from bar1: -1 * (-10%) then -1 * (-10%) = 1.1 * 1.1
    assert result.equity.iloc[-1] == pytest.approx(1.21)


def test_costs_charged_on_position_changes() -> None:
    closes = [100.0] * 10  # flat prices: only costs matter
    df = make_df(closes)
    pos = pd.Series([0, 1, 1, 0, -1, -1, 0, 1, 0, 0], index=df.index, dtype=float)
    result = run_backtest(df, pos, "1h", fee_bps=10, slippage_bps=0)
    turnover = result.metrics["turnover"]
    assert turnover == pytest.approx(6.0)  # |Δpos| summed: 1+1+1+1+1+1
    assert result.equity.iloc[-1] == pytest.approx((1 - 0.001) ** 6, rel=1e-6)


def test_trade_extraction() -> None:
    closes = [100, 100, 110, 110, 105, 105]
    df = make_df(closes)
    pos = pd.Series([1, 1, 0, -1, -1, 0], index=df.index, dtype=float)
    result = run_backtest(df, pos, "1h", fee_bps=0, slippage_bps=0)
    assert len(result.trades) == 2
    t1, t2 = result.trades
    assert t1.direction == "long" and t1.pnl_pct == pytest.approx(0.10)
    # Short entered at 105 (bar 4 close, after shift) and closed at the final
    # bar at 105 → flat.
    assert t2.direction == "short" and t2.pnl_pct == pytest.approx(0.0, abs=1e-9)


def test_metrics_hand_computed() -> None:
    rets = pd.Series(
        [0.01, -0.005, 0.02, 0.0],
        index=pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC"),
    )
    equity = (1 + rets).cumprod()
    positions = pd.Series([1.0, 1.0, 1.0, 0.0], index=rets.index)
    m = compute_metrics(rets, equity, positions, [], "1d")
    assert m["total_return"] == pytest.approx(float(equity.iloc[-1] - 1))
    expected_sharpe = rets.mean() / rets.std(ddof=1) * math.sqrt(365)
    assert m["sharpe"] == pytest.approx(float(expected_sharpe))
    assert m["exposure"] == pytest.approx(0.75)


def test_max_drawdown_known() -> None:
    equity = pd.Series([1.0, 1.2, 0.9, 1.1, 1.3])
    _, mdd = max_drawdown(equity)
    assert mdd == pytest.approx(0.9 / 1.2 - 1)


def test_determinism() -> None:
    rng = np.random.default_rng(99)
    df = make_df(list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 500)))))
    spec = STRATEGIES["sma_crossover"]
    params = {"fast": 10.0, "slow": 30.0}
    r1 = run_backtest(df, spec.generate(df, params), "1h")
    r2 = run_backtest(df, spec.generate(df, params), "1h")
    pd.testing.assert_series_equal(r1.equity, r2.equity)
    assert r1.metrics == r2.metrics


def test_sma_crossover_signals() -> None:
    # Down then up: fast crosses above slow during the recovery
    closes = list(np.linspace(100, 80, 50)) + list(np.linspace(80, 130, 100))
    df = make_df(closes)
    pos = STRATEGIES["sma_crossover"].generate(df, {"fast": 5, "slow": 20})
    assert pos.iloc[-1] == 1.0  # long in the uptrend
    assert (pos.iloc[25:45] == -1.0).any()  # short during the decline
    assert pos.iloc[0] == 0.0  # flat during warmup


def test_zscore_strategy_enters_against_extremes() -> None:
    rng = np.random.default_rng(4)
    base = 100 + rng.normal(0, 0.5, 300)
    base[200] = 110  # massive spike up → z > entry → short
    df = make_df(list(base))
    pos = STRATEGIES["zscore_mr"].generate(df, {"lookback": 50, "entry_z": 2.0, "exit_z": 0.5})
    assert pos.iloc[200] == -1.0


def test_walk_forward_window_split() -> None:
    windows = split_windows(1000, 4, train_frac=0.7)
    assert len(windows) == 4
    # Test segments tile the data with no gaps/overlaps after first train
    for w in windows:
        assert w.train_start < w.train_end == w.test_start < w.test_end
    assert windows[-1].test_end == 1000
    # Segments are contiguous: each window starts where the previous ended.
    for prev, nxt in zip(windows, windows[1:], strict=False):
        assert nxt.train_start == prev.test_end


def test_walk_forward_split_rejects_tiny_data() -> None:
    with pytest.raises(ValueError):
        split_windows(30, 4)


def test_param_grid_product() -> None:
    grid = param_grid(STRATEGIES["sma_crossover"])
    assert len(grid) == 9  # 3 fast x 3 slow
    assert {"fast": 10.0, "slow": 200.0} in [{k: float(v) for k, v in g.items()} for g in grid]


def test_walk_forward_runs_and_reports_is_vs_oos() -> None:
    rng = np.random.default_rng(7)
    df = make_df(list(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 1200)))))
    spec = STRATEGIES["sma_crossover"]
    result = run_walk_forward(df, spec, {"fast": 20.0, "slow": 50.0}, "1h", n_windows=3)
    assert len(result["windows"]) == 3
    for w in result["windows"]:
        assert "in_sample" in w and "out_of_sample" in w and "best_params" in w
    assert len(result["oos_equity"]) > 0
    assert "sharpe" in result["oos_metrics"]
