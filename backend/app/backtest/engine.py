"""Vectorized candle-based backtest engine (spec §5.1).

Hand-rolled instead of vectorbt (spec-sanctioned fallback): positions are a
target series in [-1, 0, 1]; fills happen on the *next* bar's close-to-close
return (no look-ahead); fees + slippage are charged on position changes
proportionally to turnover.
"""

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.stats import ANNUALIZATION


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    direction: str  # "long" | "short"
    entry_price: float
    exit_price: float
    pnl_pct: float
    bars: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BacktestResult:
    equity: pd.Series
    drawdown: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: list[Trade] = field(default_factory=list)
    metrics: dict[str, float | int | None] = field(default_factory=dict)


def max_drawdown(equity: pd.Series) -> tuple[pd.Series, float]:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return dd, float(dd.min())


def compute_metrics(
    returns: pd.Series, equity: pd.Series, positions: pd.Series, trades: list[Trade], interval: str
) -> dict[str, float | int | None]:
    ann = ANNUALIZATION[interval]
    n = len(returns)
    if n == 0 or equity.empty:
        return {}
    total_return = float(equity.iloc[-1] - 1.0)
    years = n / ann
    cagr = (
        float((equity.iloc[-1]) ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else None
    )
    mean, std = float(returns.mean()), float(returns.std(ddof=1))
    sharpe = float(mean / std * math.sqrt(ann)) if std > 0 else None
    downside = returns[returns < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = float(mean / dstd * math.sqrt(ann)) if dstd > 0 else None
    _, mdd = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if cagr is not None and mdd < 0 else None
    wins = [t for t in trades if t.pnl_pct > 0]
    gross_profit = sum(t.pnl_pct for t in wins)
    gross_loss = -sum(t.pnl_pct for t in trades if t.pnl_pct < 0)
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else None
    exposure = float((positions != 0).mean())
    turnover = float(positions.diff().abs().sum())
    return {
        "total_return": total_return,
        "annualized_return": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": mdd,
        "win_rate": float(len(wins) / len(trades)) if trades else None,
        "profit_factor": profit_factor,
        "exposure": exposure,
        "turnover": turnover,
        "n_trades": len(trades),
        "avg_trade_pnl_pct": float(np.mean([t.pnl_pct for t in trades])) if trades else None,
        "bars": n,
    }


def extract_trades(positions: pd.Series, close: pd.Series, cost_per_side: float) -> list[Trade]:
    """Round-trip trades from the held-position series (already shifted)."""
    trades: list[Trade] = []
    pos = positions.to_numpy()
    idx = positions.index
    closes = close.to_numpy()
    current: dict[str, Any] | None = None
    for i in range(len(pos)):
        p = pos[i]
        prev = pos[i - 1] if i > 0 else 0.0
        if p != prev:
            if current is not None:
                entry_p, exit_p = current["entry_price"], closes[i]
                direction = current["direction"]
                raw = (exit_p / entry_p - 1.0) * (1 if direction == "long" else -1)
                trades.append(
                    Trade(
                        entry_time=str(current["entry_time"]),
                        exit_time=str(idx[i]),
                        direction=direction,
                        entry_price=float(entry_p),
                        exit_price=float(exit_p),
                        pnl_pct=float(raw - 2 * cost_per_side),
                        bars=i - current["entry_i"],
                    )
                )
                current = None
            if p != 0:
                current = {
                    "entry_time": idx[i],
                    "entry_i": i,
                    "entry_price": closes[i],
                    "direction": "long" if p > 0 else "short",
                }
    if current is not None:
        entry_p, exit_p = current["entry_price"], closes[-1]
        direction = current["direction"]
        raw = (exit_p / entry_p - 1.0) * (1 if direction == "long" else -1)
        trades.append(
            Trade(
                entry_time=str(current["entry_time"]),
                exit_time=str(idx[-1]),
                direction=direction,
                entry_price=float(entry_p),
                exit_price=float(exit_p),
                pnl_pct=float(raw - 2 * cost_per_side),
                bars=len(pos) - 1 - current["entry_i"],
            )
        )
    return trades


def run_backtest(
    df: pd.DataFrame,
    target_positions: pd.Series,
    interval: str,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> BacktestResult:
    """Run a vectorized backtest.

    ``target_positions`` is the desired position decided on each bar's close;
    it takes effect from the next bar (shift inside, so strategies cannot
    look ahead).
    """
    close = df["close"]
    held = target_positions.reindex(close.index).fillna(0.0).clip(-1, 1).shift(1).fillna(0.0)
    bar_returns = close.pct_change().fillna(0.0)
    cost_per_side = (fee_bps + slippage_bps) / 10_000
    costs = held.diff().abs().fillna(held.abs()) * cost_per_side
    strat_returns = held * bar_returns - costs
    equity = (1.0 + strat_returns).cumprod()
    drawdown, _ = max_drawdown(equity)
    trades = extract_trades(held, close, cost_per_side)
    metrics = compute_metrics(strat_returns, equity, held, trades, interval)
    return BacktestResult(
        equity=equity,
        drawdown=drawdown,
        returns=strat_returns,
        positions=held,
        trades=trades,
        metrics=metrics,
    )
