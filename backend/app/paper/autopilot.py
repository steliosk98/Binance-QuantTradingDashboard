"""Autopilot: periodic walk-forward re-optimization of paper instances (V3).

Every `retrain_hours`, grid-search the strategy's declared parameter grid on
the older 70% of recent data and adopt the winner ONLY if it also beats the
instance's current parameters on the held-out 30% validation tail — the same
overfitting guard the walk-forward backtester makes visible.
"""

import logging
import time
from typing import Any

import pandas as pd

from app.backtest.engine import run_backtest
from app.backtest.strategies import StrategySpec
from app.backtest.walkforward import param_grid

logger = logging.getLogger("autopilot")

TRAIN_FRAC = 0.7
MIN_BARS = 300


def _val_sharpe(
    df: pd.DataFrame, spec: StrategySpec, params: dict[str, float], interval: str
) -> float:
    split = int(len(df) * TRAIN_FRAC)
    val = df.iloc[split:]
    result = run_backtest(val, spec.generate(val, params), interval)
    sharpe = result.metrics.get("sharpe")
    return float(sharpe) if sharpe is not None else float("-inf")


def retrain(
    df: pd.DataFrame,
    spec: StrategySpec,
    current_params: dict[str, float],
    interval: str,
) -> dict[str, Any] | None:
    """Returns {'params': …, 'train_sharpe': …, 'val_sharpe': …} when a
    grid candidate beats the current params out-of-sample, else None."""
    if len(df) < MIN_BARS or spec.needs_pair:
        return None
    split = int(len(df) * TRAIN_FRAC)
    train = df.iloc[:split]

    best_params: dict[str, float] | None = None
    best_train = float("-inf")
    for candidate in param_grid(spec):
        params = {**current_params, **candidate}
        result = run_backtest(train, spec.generate(train, params), interval)
        sharpe = result.metrics.get("sharpe")
        score = float(sharpe) if sharpe is not None else float("-inf")
        if score > best_train:
            best_train, best_params = score, params
    if best_params is None:
        return None

    current_val = _val_sharpe(df, spec, current_params, interval)
    candidate_val = _val_sharpe(df, spec, best_params, interval)
    if candidate_val <= current_val:
        logger.info(
            "autopilot: keeping current params (val %.2f >= candidate %.2f)",
            current_val,
            candidate_val,
        )
        return None
    return {
        "params": best_params,
        "train_sharpe": best_train,
        "val_sharpe": candidate_val,
        "previous_val_sharpe": current_val,
        "ts": int(time.time()),
    }
