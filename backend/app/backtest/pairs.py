"""Pairs trading (statistical arbitrage) — V2.

Dollar-neutral two-leg strategy on a cointegrated pair: rolling hedge ratio
(beta = rolling cov/var), spread z-score entry/exit. Positions decided on a
bar's close take effect next bar (same no-look-ahead convention as the
single-asset engine).
"""

from typing import Any

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestResult, Trade, compute_metrics, max_drawdown


def pairs_target_positions(
    close_a: pd.Series,
    close_b: pd.Series,
    lookback: int,
    entry_z: float,
    exit_z: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (target_position on the spread, rolling beta, spread z-score)."""
    beta = close_a.rolling(lookback).cov(close_b) / close_b.rolling(lookback).var()
    spread = close_a - beta * close_b
    z = (spread - spread.rolling(lookback).mean()) / spread.rolling(lookback).std(ddof=1)

    pos = np.zeros(len(close_a))
    holding = 0.0
    z_arr = z.to_numpy()
    for i in range(len(pos)):
        zi = z_arr[i]
        if np.isnan(zi):
            pos[i] = 0.0
            continue
        if holding == 0:
            if zi <= -entry_z:
                holding = 1.0  # long spread: long A, short B
            elif zi >= entry_z:
                holding = -1.0
        elif (holding > 0 and zi >= -exit_z) or (holding < 0 and zi <= exit_z):
            holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=close_a.index), beta, z


def run_pairs_backtest(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    interval: str,
    params: dict[str, float],
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> tuple[BacktestResult, pd.Series]:
    """Backtest the pair; returns (result, spread z-score series)."""
    close_a = df_a["close"]
    close_b = df_b["close"].reindex(close_a.index).ffill()
    aligned = pd.concat([close_a, close_b], axis=1, keys=["a", "b"]).dropna()
    a, b = aligned["a"], aligned["b"]

    lookback = int(params.get("lookback", 100))
    target, beta, z = pairs_target_positions(
        a, b, lookback, float(params.get("entry_z", 2.0)), float(params.get("exit_z", 0.5))
    )

    held = target.shift(1).fillna(0.0)
    beta_prev = beta.shift(1)
    ret_a = a.pct_change().fillna(0.0)
    ret_b = b.pct_change().fillna(0.0)
    # Dollar-neutral spread return, gross-normalized across both legs.
    gross = 1.0 + beta_prev.abs()
    spread_ret = (ret_a - beta_prev * ret_b) / gross
    spread_ret = spread_ret.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    cost_per_side = (fee_bps + slippage_bps) / 10_000
    # Two legs trade on every position change.
    costs = held.diff().abs().fillna(held.abs()) * cost_per_side * 2
    strat_returns = held * spread_ret - costs
    equity = (1.0 + strat_returns).cumprod()
    drawdown, _ = max_drawdown(equity)

    trades = _extract_spread_trades(held, equity, z)
    metrics = compute_metrics(strat_returns, equity, held, trades, interval)
    result = BacktestResult(
        equity=equity,
        drawdown=drawdown,
        returns=strat_returns,
        positions=held,
        trades=trades,
        metrics=metrics,
    )
    return result, z


def _extract_spread_trades(held: pd.Series, equity: pd.Series, z: pd.Series) -> list[Trade]:
    """Round trips on the spread; PnL measured on strategy equity."""
    trades: list[Trade] = []
    pos = held.to_numpy()
    idx = held.index
    eq = equity.to_numpy()
    z_arr = z.to_numpy()
    entry: dict[str, Any] | None = None
    for i in range(len(pos)):
        prev = pos[i - 1] if i > 0 else 0.0
        if pos[i] != prev:
            if entry is not None:
                trades.append(
                    Trade(
                        entry_time=str(entry["time"]),
                        exit_time=str(idx[i]),
                        direction=entry["direction"],
                        entry_price=float(entry["z"]),
                        exit_price=float(z_arr[i]) if not np.isnan(z_arr[i]) else 0.0,
                        pnl_pct=float(eq[i] / entry["equity"] - 1.0),
                        bars=i - entry["i"],
                    )
                )
                entry = None
            if pos[i] != 0:
                entry = {
                    "time": idx[i],
                    "i": i,
                    "z": z_arr[i] if not np.isnan(z_arr[i]) else 0.0,
                    "equity": eq[i],
                    "direction": "long" if pos[i] > 0 else "short",
                }
    if entry is not None:
        trades.append(
            Trade(
                entry_time=str(entry["time"]),
                exit_time=str(idx[-1]),
                direction=entry["direction"],
                entry_price=float(entry["z"]),
                exit_price=float(z_arr[-1]) if not np.isnan(z_arr[-1]) else 0.0,
                pnl_pct=float(eq[-1] / entry["equity"] - 1.0),
                bars=len(pos) - 1 - entry["i"],
            )
        )
    return trades
