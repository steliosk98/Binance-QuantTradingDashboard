"""2-parameter grid-search optimizer → Sharpe/return heatmap (V2)."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.data import load_candles_df
from app.api.deps import get_db
from app.backtest.engine import run_backtest
from app.backtest.strategies import STRATEGIES

router = APIRouter(prefix="/api/v1", tags=["optimize"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

MAX_CELLS = 144
MAX_BARS = 10_000


class OptimizeRequest(BaseModel):
    strategy: str
    symbol: str = Field(min_length=5, max_length=20)
    interval: str = "1h"
    param_x: str
    param_y: str
    x_values: list[float] = Field(min_length=2, max_length=12)
    y_values: list[float] = Field(min_length=2, max_length=12)
    base_params: dict[str, float] = Field(default_factory=dict)
    fee_bps: float = Field(default=10.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)


@router.post("/optimize")
async def optimize(req: OptimizeRequest, db: DbSession) -> dict[str, Any]:
    spec = STRATEGIES.get(req.strategy)
    if spec is None or spec.needs_pair:
        raise HTTPException(status_code=422, detail="unknown or unsupported strategy")
    param_names = {p.name for p in spec.params}
    if req.param_x not in param_names or req.param_y not in param_names:
        raise HTTPException(status_code=422, detail=f"params must be in {sorted(param_names)}")
    if req.param_x == req.param_y:
        raise HTTPException(status_code=422, detail="pick two different parameters")
    if len(req.x_values) * len(req.y_values) > MAX_CELLS:
        raise HTTPException(status_code=422, detail=f"grid too large (max {MAX_CELLS} cells)")

    df = await load_candles_df(db, req.symbol.upper(), req.interval, MAX_BARS)
    if len(df) < 200:
        raise HTTPException(status_code=404, detail=f"not enough candles for {req.symbol}")

    defaults = {p.name: req.base_params.get(p.name, p.default) for p in spec.params}

    def run_grid() -> dict[str, Any]:
        sharpe: list[list[float | None]] = []
        total_return: list[list[float | None]] = []
        best: dict[str, Any] = {"sharpe": float("-inf")}
        for y in req.y_values:
            s_row: list[float | None] = []
            r_row: list[float | None] = []
            for x in req.x_values:
                params = {**defaults, req.param_x: x, req.param_y: y}
                result = run_backtest(
                    df, spec.generate(df, params), req.interval, req.fee_bps, req.slippage_bps
                )
                s = result.metrics.get("sharpe")
                s_row.append(s)
                r_row.append(result.metrics.get("total_return"))
                if s is not None and s > best["sharpe"]:
                    best = {
                        "sharpe": s,
                        "total_return": result.metrics.get("total_return"),
                        "params": {req.param_x: x, req.param_y: y},
                    }
            sharpe.append(s_row)
            total_return.append(r_row)
        return {"sharpe": sharpe, "total_return": total_return, "best": best}

    grid = await asyncio.to_thread(run_grid)
    return {
        "strategy": req.strategy,
        "symbol": req.symbol.upper(),
        "interval": req.interval,
        "param_x": req.param_x,
        "param_y": req.param_y,
        "x_values": req.x_values,
        "y_values": req.y_values,
        "bars": len(df),
        **grid,
    }
