"""Built-in strategies (spec §5.2) with declared param schemas so the UI can
auto-render forms and the walk-forward optimizer can grid-search.

Each strategy maps OHLCV (+ optional funding) to a target position series in
[-1, 0, 1] decided on each bar's close. The engine shifts by one bar.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.analytics import indicators as ind
from app.analytics.stats import zscore


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    type: str  # "int" | "float"
    default: float
    min: float
    max: float
    step: float
    grid: tuple[float, ...] = ()  # walk-forward search values

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "step": self.step,
        }


@dataclass(frozen=True)
class StrategySpec:
    key: str
    name: str
    description: str
    params: tuple[Param, ...]
    generate: Callable[[pd.DataFrame, dict[str, float]], pd.Series]
    needs_funding: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "needs_funding": self.needs_funding,
            "params": [p.to_dict() for p in self.params],
        }


def _sma_crossover(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    fast = ind.sma(df["close"], int(p["fast"]))
    slow = ind.sma(df["close"], int(p["slow"]))
    pos = pd.Series(np.where(fast > slow, 1.0, -1.0), index=df.index)
    pos[slow.isna()] = 0.0
    return pos


def _rsi_mean_reversion(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    rsi = ind.rsi(df["close"], int(p["period"]))
    entry, exit_ = p["entry"], p["exit"]
    pos = np.zeros(len(df))
    holding = 0.0
    bars_held = 0
    max_hold = int(p["max_hold"])
    rsi_arr = rsi.to_numpy()
    for i in range(len(df)):
        r = rsi_arr[i]
        if holding == 0:
            if not np.isnan(r):
                if r <= entry:
                    holding = 1.0
                    bars_held = 0
                elif r >= 100 - entry:
                    holding = -1.0
                    bars_held = 0
        else:
            bars_held += 1
            crossed = (holding > 0 and r >= exit_) or (holding < 0 and r <= 100 - exit_)
            if crossed or bars_held >= max_hold:
                holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=df.index)


def _bollinger_mr(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    bb = ind.bollinger(df["close"], int(p["period"]), p["num_std"])
    close = df["close"]
    pos = np.zeros(len(df))
    holding = 0.0
    for i in range(len(df)):
        c, lo, mid, hi = (
            close.iloc[i],
            bb["lower"].iloc[i],
            bb["middle"].iloc[i],
            bb["upper"].iloc[i],
        )
        if np.isnan(mid):
            pos[i] = 0.0
            continue
        if holding == 0:
            if c <= lo:
                holding = 1.0
            elif c >= hi:
                holding = -1.0
        elif (holding > 0 and c >= mid) or (holding < 0 and c <= mid):
            holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=df.index)


def _donchian_breakout(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    lookback = int(p["lookback"])
    atr_mult = p["atr_stop"]
    high_band = df["high"].rolling(lookback).max().shift(1)
    low_band = df["low"].rolling(lookback).min().shift(1)
    atr = ind.atr(df["high"], df["low"], df["close"], 14)
    close = df["close"]
    pos = np.zeros(len(df))
    holding = 0.0
    stop = 0.0
    for i in range(len(df)):
        c = close.iloc[i]
        hb, lb, a = high_band.iloc[i], low_band.iloc[i], atr.iloc[i]
        if np.isnan(hb) or np.isnan(a):
            pos[i] = 0.0
            continue
        if holding == 0:
            if c > hb:
                holding, stop = 1.0, c - atr_mult * a
            elif c < lb:
                holding, stop = -1.0, c + atr_mult * a
        elif holding > 0:
            stop = max(stop, c - atr_mult * a)  # trailing
            if c < stop:
                holding = 0.0
        else:
            stop = min(stop, c + atr_mult * a)
            if c > stop:
                holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=df.index)


def _zscore_mr(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    z = zscore(df["close"], int(p["lookback"]))
    entry, exit_ = p["entry_z"], p["exit_z"]
    pos = np.zeros(len(df))
    holding = 0.0
    z_arr = z.to_numpy()
    for i in range(len(df)):
        zi = z_arr[i]
        if np.isnan(zi):
            pos[i] = 0.0
            continue
        if holding == 0:
            if zi <= -entry:
                holding = 1.0
            elif zi >= entry:
                holding = -1.0
        elif (holding > 0 and zi >= -exit_) or (holding < 0 and zi <= exit_):
            holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=df.index)


def _funding_contrarian(df: pd.DataFrame, p: dict[str, float]) -> pd.Series:
    """Enter against extreme funding percentiles (needs `funding` column)."""
    if "funding" not in df.columns:
        return pd.Series(0.0, index=df.index)
    funding = df["funding"]
    window = int(p["lookback"])
    upper = funding.rolling(window).quantile(p["pctile"] / 100)
    lower = funding.rolling(window).quantile(1 - p["pctile"] / 100)
    pos = np.zeros(len(df))
    holding = 0.0
    for i in range(len(df)):
        f, hi, lo = funding.iloc[i], upper.iloc[i], lower.iloc[i]
        if np.isnan(hi):
            pos[i] = 0.0
            continue
        if f >= hi:
            holding = -1.0  # crowded longs → fade short
        elif f <= lo:
            holding = 1.0
        elif abs(f) < funding.rolling(window).median().iloc[i]:
            holding = 0.0
        pos[i] = holding
    return pd.Series(pos, index=df.index)


STRATEGIES: dict[str, StrategySpec] = {
    s.key: s
    for s in [
        StrategySpec(
            key="sma_crossover",
            name="SMA Crossover",
            description="Long when fast SMA above slow, short otherwise.",
            params=(
                Param("fast", "Fast period", "int", 20, 5, 100, 1, grid=(10, 20, 50)),
                Param("slow", "Slow period", "int", 50, 10, 400, 1, grid=(50, 100, 200)),
            ),
            generate=_sma_crossover,
        ),
        StrategySpec(
            key="rsi_mr",
            name="RSI Mean Reversion",
            description="Buy oversold / sell overbought RSI with holding limit.",
            params=(
                Param("period", "RSI period", "int", 14, 2, 50, 1, grid=(7, 14)),
                Param("entry", "Entry threshold", "float", 30, 5, 45, 1, grid=(20, 30)),
                Param("exit", "Exit threshold", "float", 50, 40, 90, 1, grid=(50, 60)),
                Param("max_hold", "Max bars held", "int", 48, 1, 500, 1),
            ),
            generate=_rsi_mean_reversion,
        ),
        StrategySpec(
            key="bollinger_mr",
            name="Bollinger Mean Reversion",
            description="Enter at band touch, exit at mid-band.",
            params=(
                Param("period", "Period", "int", 20, 5, 100, 1, grid=(20, 40)),
                Param("num_std", "Std devs", "float", 2.0, 0.5, 4.0, 0.1, grid=(1.5, 2.0, 2.5)),
            ),
            generate=_bollinger_mr,
        ),
        StrategySpec(
            key="donchian",
            name="Donchian Breakout",
            description="Channel breakout with trailing ATR stop.",
            params=(
                Param("lookback", "Lookback", "int", 20, 5, 200, 1, grid=(20, 55)),
                Param(
                    "atr_stop", "ATR stop multiple", "float", 3.0, 0.5, 10.0, 0.5, grid=(2.0, 3.0)
                ),
            ),
            generate=_donchian_breakout,
        ),
        StrategySpec(
            key="zscore_mr",
            name="Z-Score Mean Reversion",
            description="Fade price z-score extremes vs rolling mean.",
            params=(
                Param("lookback", "Lookback", "int", 50, 10, 500, 1, grid=(50, 100)),
                Param("entry_z", "Entry |z|", "float", 2.0, 0.5, 5.0, 0.1, grid=(1.5, 2.0, 2.5)),
                Param("exit_z", "Exit |z|", "float", 0.5, 0.0, 2.0, 0.1, grid=(0.0, 0.5)),
            ),
            generate=_zscore_mr,
        ),
        StrategySpec(
            key="funding_contrarian",
            name="Funding Contrarian",
            description="Fade extreme funding percentiles (futures data, 1h+).",
            params=(
                Param("lookback", "Funding window (bars)", "int", 180, 30, 1000, 1, grid=(90, 180)),
                Param("pctile", "Extreme percentile", "float", 90, 70, 99, 1, grid=(85, 95)),
            ),
            generate=_funding_contrarian,
            needs_funding=True,
        ),
    ]
}
