"""Alert rule CRUD + event log."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.engine import RULE_KINDS
from app.api.deps import get_db
from app.models import AlertEvent, AlertRule

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class CreateRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str
    symbol: str | None = Field(default=None, min_length=5, max_length=20)
    params: dict[str, float | str] = Field(default_factory=dict)
    cooldown_s: int = Field(default=300, ge=10, le=86_400)


def _rule_out(r: AlertRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "name": r.name,
        "kind": r.kind,
        "symbol": r.symbol,
        "params": r.params_json,
        "enabled": r.enabled,
        "cooldown_s": r.cooldown_s,
    }


@router.get("/rules")
async def list_rules(db: DbSession) -> dict[str, Any]:
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))
    return {"rules": [_rule_out(r) for r in result.scalars()]}


@router.post("/rules", status_code=201)
async def create_rule(req: CreateRuleRequest, db: DbSession) -> dict[str, Any]:
    if req.kind not in RULE_KINDS:
        raise HTTPException(status_code=422, detail=f"unknown kind; one of {RULE_KINDS}")
    if req.kind in ("price_cross", "regime_change") and not req.symbol:
        raise HTTPException(status_code=422, detail=f"{req.kind} requires a symbol")
    rule = AlertRule(
        id=str(uuid.uuid4()),
        name=req.name,
        kind=req.kind,
        symbol=req.symbol.upper() if req.symbol else None,
        params_json=dict(req.params),
        enabled=True,
        cooldown_s=req.cooldown_s,
        state_json={},
    )
    db.add(rule)
    await db.commit()
    return _rule_out(rule)


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, db: DbSession) -> dict[str, Any]:
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    rule.enabled = not rule.enabled
    await db.commit()
    return _rule_out(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db: DbSession) -> dict[str, str]:
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    await db.execute(delete(AlertEvent).where(AlertEvent.rule_id == rule_id))
    await db.delete(rule)
    await db.commit()
    return {"status": "deleted"}


@router.get("/events")
async def list_events(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> dict[str, Any]:
    result = await db.execute(select(AlertEvent).order_by(AlertEvent.ts.desc()).limit(limit))
    return {
        "events": [
            {"id": e.id, "rule_id": e.rule_id, "ts": e.ts.isoformat(), "message": e.message}
            for e in result.scalars()
        ]
    }
