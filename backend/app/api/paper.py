"""Paper trading instance lifecycle API."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.backtest.strategies import STRATEGIES
from app.ingestion.binance_client import INTERVAL_MS
from app.models import PaperEquity, PaperInstance, PaperOrder
from app.paper.engine import DEFAULT_GUARDS, default_state

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class CreateInstanceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    strategy: str
    symbol: str = Field(min_length=5, max_length=20)
    symbol_b: str | None = Field(default=None, min_length=5, max_length=20)
    interval: str = "1m"
    qty_usd: float = Field(default=1000.0, gt=0, le=1_000_000)
    params: dict[str, float] = Field(default_factory=dict)
    max_position_usd: float = Field(default=10_000.0, gt=0)
    max_daily_loss_usd: float = Field(default=500.0, gt=0)


def _instance_summary(r: PaperInstance) -> dict[str, Any]:
    state = r.state_json or default_state()
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "name": r.name,
        "strategy": r.strategy,
        "symbol": r.symbol,
        "interval": r.interval,
        "qty_usd": r.qty_usd,
        "status": r.status,
        "params": r.params_json,
        "guards": r.guards_json,
        "position_qty": state.get("position_qty", 0.0),
        "realized_pnl": state.get("realized_pnl", 0.0),
        "halted_today": state.get("halted_today", False),
    }


@router.get("/instances")
async def list_instances(db: DbSession) -> dict[str, Any]:
    result = await db.execute(select(PaperInstance).order_by(PaperInstance.created_at.desc()))
    return {"instances": [_instance_summary(r) for r in result.scalars()]}


@router.post("/instances", status_code=201)
async def create_instance(req: CreateInstanceRequest, db: DbSession) -> dict[str, Any]:
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail=f"unknown strategy {req.strategy!r}")
    if req.interval not in INTERVAL_MS:
        raise HTTPException(status_code=422, detail=f"unsupported interval {req.interval!r}")
    spec = STRATEGIES[req.strategy]
    params: dict[str, object] = dict(req.params)
    if spec.needs_pair:
        if not req.symbol_b or req.symbol_b.upper() == req.symbol.upper():
            raise HTTPException(status_code=422, detail="pairs strategy needs a distinct symbol_b")
        params["symbol_b"] = req.symbol_b.upper()
    row = PaperInstance(
        id=str(uuid.uuid4()),
        name=req.name,
        strategy=req.strategy,
        symbol=req.symbol.upper(),
        interval=req.interval,
        qty_usd=req.qty_usd,
        status="running",
        params_json=params,
        guards_json={
            **DEFAULT_GUARDS,
            "max_position_usd": req.max_position_usd,
            "max_daily_loss_usd": req.max_daily_loss_usd,
        },
        state_json=default_state(),
    )
    db.add(row)
    await db.commit()
    return _instance_summary(row)


async def _get_or_404(db: AsyncSession, instance_id: str) -> PaperInstance:
    row = await db.get(PaperInstance, instance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="instance not found")
    return row


@router.post("/instances/{instance_id}/stop")
async def stop_instance(instance_id: str, db: DbSession) -> dict[str, Any]:
    """Kill switch: takes effect within one evaluation cycle."""
    row = await _get_or_404(db, instance_id)
    row.status = "stopped"
    await db.commit()
    return _instance_summary(row)


@router.post("/instances/{instance_id}/start")
async def start_instance(instance_id: str, db: DbSession) -> dict[str, Any]:
    row = await _get_or_404(db, instance_id)
    row.status = "running"
    await db.commit()
    return _instance_summary(row)


@router.get("/instances/{instance_id}")
async def get_instance(
    instance_id: str,
    db: DbSession,
    orders_limit: Annotated[int, Query(ge=1, le=500)] = 100,
    equity_limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> dict[str, Any]:
    row = await _get_or_404(db, instance_id)
    orders_result = await db.execute(
        select(PaperOrder)
        .where(PaperOrder.instance_id == instance_id)
        .order_by(PaperOrder.ts.desc())
        .limit(orders_limit)
    )
    equity_result = await db.execute(
        select(PaperEquity)
        .where(PaperEquity.instance_id == instance_id)
        .order_by(PaperEquity.ts.desc())
        .limit(equity_limit)
    )
    orders = list(orders_result.scalars())
    equity = list(reversed(list(equity_result.scalars())))
    return {
        **_instance_summary(row),
        "state": row.state_json,
        "orders": [
            {
                "id": o.id,
                "ts": o.ts.isoformat(),
                "symbol": o.symbol,
                "side": o.side,
                "qty": o.qty,
                "price": o.price,
                "status": o.status,
                "signal": o.signal,
                "testnet_order_id": o.testnet_order_id,
            }
            for o in orders
        ],
        "equity": [[e.ts.isoformat(), e.equity_usd, e.position_qty, e.price] for e in equity],
    }
