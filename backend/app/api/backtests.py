"""Backtest API: submit async runs, poll status, fetch results."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.data import load_candles_df
from app.api.deps import get_db
from app.backtest.engine import run_backtest
from app.backtest.pairs import run_pairs_backtest
from app.backtest.strategies import STRATEGIES
from app.backtest.walkforward import run_walk_forward
from app.db.session import get_session_factory
from app.ingestion.binance_client import INTERVAL_MS
from app.models import Backtest, FundingRate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["backtests"])

MAX_BARS = 20_000

DbSession = Annotated[AsyncSession, Depends(get_db)]


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = Field(min_length=5, max_length=20)
    symbol_b: str | None = Field(default=None, min_length=5, max_length=20)
    interval: str = "1h"
    params: dict[str, float] = Field(default_factory=dict)
    start: datetime | None = None
    end: datetime | None = None
    fee_bps: float = Field(default=10.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)
    walk_forward: bool = False
    n_windows: int = Field(default=4, ge=2, le=10)


@router.get("/strategies")
async def list_strategies() -> dict[str, Any]:
    return {"strategies": [s.to_dict() for s in STRATEGIES.values()]}


async def _load_df(
    session: AsyncSession, req: BacktestRequest, needs_funding: bool
) -> pd.DataFrame:
    df = await load_candles_df(session, req.symbol.upper(), req.interval, MAX_BARS)
    if req.start is not None:
        df = df[df.index >= req.start]
    if req.end is not None:
        df = df[df.index <= req.end]
    if needs_funding and not df.empty:
        result = await session.execute(
            select(FundingRate.funding_time, FundingRate.rate)
            .where(FundingRate.symbol == req.symbol.upper())
            .order_by(FundingRate.funding_time)
        )
        rows = result.all()
        if rows:
            funding = pd.Series([r[1] for r in rows], index=pd.DatetimeIndex([r[0] for r in rows]))
            df["funding"] = funding.reindex(df.index, method="ffill")
        else:
            df["funding"] = 0.0
    return df


async def _execute(backtest_id: str, req: BacktestRequest) -> None:
    factory = get_session_factory()
    spec = STRATEGIES[req.strategy]
    try:
        async with factory() as session:
            row = await session.get(Backtest, backtest_id)
            assert row is not None
            row.status = "running"
            await session.commit()

            df = await _load_df(session, req, spec.needs_funding)
            if len(df) < 100:
                raise ValueError(f"not enough candles for {req.symbol} {req.interval}")

            params = {p.name: req.params.get(p.name, p.default) for p in spec.params}
            if spec.needs_pair:
                assert req.symbol_b is not None
                df_b = await load_candles_df(session, req.symbol_b.upper(), req.interval, MAX_BARS)
                if len(df_b) < 100:
                    raise ValueError(f"not enough candles for {req.symbol_b} {req.interval}")
                result, _z = await asyncio.to_thread(
                    run_pairs_backtest,
                    df,
                    df_b,
                    req.interval,
                    params,
                    req.fee_bps,
                    req.slippage_bps,
                )
                params["symbol_b"] = req.symbol_b.upper()  # type: ignore[assignment]
            else:
                # Heavy compute off the event loop.
                result = await asyncio.to_thread(
                    run_backtest,
                    df,
                    spec.generate(df, params),
                    req.interval,
                    req.fee_bps,
                    req.slippage_bps,
                )
            wf: dict[str, Any] | None = None
            if req.walk_forward:
                wf = await asyncio.to_thread(
                    run_walk_forward,
                    df,
                    spec,
                    params,
                    req.interval,
                    req.n_windows,
                    req.fee_bps,
                    req.slippage_bps,
                )

            row.status = "done"
            row.params_json = params
            row.metrics_json = result.metrics
            row.equity_json = [
                [str(t), float(e), float(d)]
                for t, e, d in zip(result.equity.index, result.equity, result.drawdown, strict=True)
            ]
            row.trades_json = [t.to_dict() for t in result.trades]
            row.walkforward_json = wf
            row.start = df.index[0].to_pydatetime()
            row.end = df.index[-1].to_pydatetime()
            await session.commit()
    except Exception as exc:
        logger.exception("backtest %s failed", backtest_id)
        async with factory() as session:
            row = await session.get(Backtest, backtest_id)
            if row is not None:
                row.status = "error"
                row.error = f"{type(exc).__name__}: {exc}"[:300]
                await session.commit()


@router.post("/backtests", status_code=202)
async def create_backtest(req: BacktestRequest, db: DbSession) -> dict[str, str]:
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail=f"unknown strategy {req.strategy!r}")
    if req.interval not in INTERVAL_MS:
        raise HTTPException(status_code=422, detail=f"unsupported interval {req.interval!r}")
    spec = STRATEGIES[req.strategy]
    if spec.needs_pair:
        if not req.symbol_b or req.symbol_b.upper() == req.symbol.upper():
            raise HTTPException(status_code=422, detail="pairs strategy needs a distinct symbol_b")
        if req.walk_forward:
            raise HTTPException(status_code=422, detail="walk-forward is single-asset only")
    backtest_id = str(uuid.uuid4())
    row = Backtest(
        id=backtest_id,
        strategy=req.strategy,
        symbol=req.symbol.upper(),
        interval=req.interval,
        status="pending",
        params_json=dict(req.params),
    )
    db.add(row)
    await db.commit()
    task = asyncio.create_task(_execute(backtest_id, req))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"id": backtest_id, "status": "pending"}


_background_tasks: set[asyncio.Task[None]] = set()


@router.get("/backtests")
async def list_backtests(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict[str, Any]:
    result = await db.execute(select(Backtest).order_by(Backtest.created_at.desc()).limit(limit))
    rows = list(result.scalars())
    return {
        "backtests": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "strategy": r.strategy,
                "symbol": r.symbol,
                "interval": r.interval,
                "status": r.status,
                "params": r.params_json,
                "metrics": r.metrics_json,
            }
            for r in rows
        ]
    }


@router.get("/backtests/{backtest_id}")
async def get_backtest(backtest_id: str, db: DbSession) -> dict[str, Any]:
    row = await db.get(Backtest, backtest_id)
    if row is None:
        raise HTTPException(status_code=404, detail="backtest not found")
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "strategy": row.strategy,
        "symbol": row.symbol,
        "interval": row.interval,
        "status": row.status,
        "error": row.error,
        "params": row.params_json,
        "metrics": row.metrics_json,
        "equity": row.equity_json,
        "trades": row.trades_json,
        "walk_forward": row.walkforward_json,
        "start": row.start.isoformat() if row.start else None,
        "end": row.end.isoformat() if row.end else None,
    }
