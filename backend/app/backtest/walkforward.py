"""Walk-forward mode (spec §5.1): rolling train/test windows, grid-search on
train, out-of-sample stitched equity. Overfitting made visible by reporting
in-sample vs out-of-sample metrics side by side.
"""

import itertools
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.backtest.engine import compute_metrics, run_backtest
from app.backtest.strategies import StrategySpec


@dataclass(frozen=True)
class Window:
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive


def split_windows(n_bars: int, n_windows: int, train_frac: float = 0.7) -> list[Window]:
    """Split [0, n_bars) into n_windows equal segments; within each, the first
    train_frac is train and the rest is test. Test segments are contiguous and
    non-overlapping so the stitched OOS curve covers them exactly once.
    """
    if n_windows < 1 or n_bars < n_windows * 10:
        raise ValueError("not enough data for the requested windows")
    seg = n_bars // n_windows
    windows = []
    for w in range(n_windows):
        start = w * seg
        end = n_bars if w == n_windows - 1 else (w + 1) * seg
        split = start + int((end - start) * train_frac)
        windows.append(Window(start, split, split, end))
    return windows


def param_grid(spec: StrategySpec) -> list[dict[str, float]]:
    names, value_lists = [], []
    for p in spec.params:
        names.append(p.name)
        value_lists.append(list(p.grid) if p.grid else [p.default])
    return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*value_lists)]


def run_walk_forward(
    df: pd.DataFrame,
    spec: StrategySpec,
    base_params: dict[str, float],
    interval: str,
    n_windows: int = 4,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    windows = split_windows(len(df), n_windows)
    grid = param_grid(spec)
    oos_returns: list[pd.Series] = []
    per_window: list[dict[str, Any]] = []

    for w in windows:
        train_df = df.iloc[w.train_start : w.train_end]
        test_df = df.iloc[w.test_start : w.test_end]
        best_params: dict[str, float] | None = None
        best_score = float("-inf")
        best_is_metrics: dict[str, Any] = {}
        for candidate in grid:
            params = {**base_params, **candidate}
            result = run_backtest(
                train_df, spec.generate(train_df, params), interval, fee_bps, slippage_bps
            )
            score = result.metrics.get("sharpe") or float("-inf")
            if score > best_score:
                best_score = score
                best_params = params
                best_is_metrics = result.metrics
        assert best_params is not None
        test_result = run_backtest(
            test_df, spec.generate(test_df, best_params), interval, fee_bps, slippage_bps
        )
        oos_returns.append(test_result.returns)
        per_window.append(
            {
                "train": [str(df.index[w.train_start]), str(df.index[w.train_end - 1])],
                "test": [str(df.index[w.test_start]), str(df.index[w.test_end - 1])],
                "best_params": best_params,
                "in_sample": best_is_metrics,
                "out_of_sample": test_result.metrics,
            }
        )

    stitched = pd.concat(oos_returns)
    equity = (1.0 + stitched).cumprod()
    positions = pd.Series(1.0, index=stitched.index)  # exposure unknown post-stitch
    oos_metrics = compute_metrics(stitched, equity, positions, [], interval)
    return {
        "windows": per_window,
        "oos_equity": [[str(t), float(v)] for t, v in equity.items()],
        "oos_metrics": oos_metrics,
    }
