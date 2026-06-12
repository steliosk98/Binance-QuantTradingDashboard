"""Alert rule engine.

Runs inside the ingestion worker: subscribes to live Redis topics and
evaluates enabled rules. Fired alerts are persisted, published on the
``alerts`` topic for the UI bell, and optionally delivered to Telegram.

Rule kinds and params:
- price_cross   {level: float, direction: "above"|"below"}   (per symbol)
- whale_trade   {min_usd: float}                             (symbol optional)
- liquidation   {min_usd: float}                             (symbol optional)
- funding_abs   {min_abs_rate: float}                        (symbol optional)
- regime_change {}                                           (per symbol, trend label change)
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.alerts import AlertEvent, AlertRule

logger = logging.getLogger("alerts")

RULE_KINDS = ("price_cross", "whale_trade", "liquidation", "funding_abs", "regime_change")


@dataclass
class Fired:
    rule: AlertRule
    message: str
    payload: dict[str, Any]


def _fmt_usd(v: float) -> str:
    return f"{v:,.0f}"


def evaluate_rule(
    rule: AlertRule, topic: str, data: dict[str, Any], state: dict[str, Any]
) -> str | None:
    """Pure evaluation: returns the alert message when the rule fires.

    ``state`` is the rule's mutable memory (last price side, last regime…).
    """
    p = rule.params_json
    kind = rule.kind

    if kind == "price_cross" and topic == "tickers":
        for t in data.get("tickers", []):
            if t["symbol"] != rule.symbol:
                continue
            level = float(p["level"])
            above = float(t["last"]) >= level
            prev = state.get("above")
            state["above"] = above
            if prev is None:
                return None
            direction = p.get("direction", "above")
            if direction == "above" and not prev and above:
                return f"{rule.symbol} crossed above {_fmt_usd(level)} (last {t['last']})"
            if direction == "below" and prev and not above:
                return f"{rule.symbol} crossed below {_fmt_usd(level)} (last {t['last']})"
        return None

    if kind == "whale_trade" and topic == "whales":
        if rule.symbol and data.get("symbol") != rule.symbol:
            return None
        if float(data.get("value", 0)) >= float(p.get("min_usd", 0)):
            side = "SELL" if data.get("is_buyer_maker") else "BUY"
            return f"Whale {side} {data['symbol']} ${_fmt_usd(float(data['value']))}"
        return None

    if kind == "liquidation" and topic == "liqs":
        if rule.symbol and data.get("symbol") != rule.symbol:
            return None
        if float(data.get("value", 0)) >= float(p.get("min_usd", 0)):
            return (
                f"{str(data.get('side', '')).upper()} liquidation {data['symbol']} "
                f"${_fmt_usd(float(data['value']))}"
            )
        return None

    if kind == "funding_abs" and topic == "marks":
        for m in data.get("marks", []):
            if rule.symbol and m["symbol"] != rule.symbol:
                continue
            rate = m.get("funding_rate")
            if rate is not None and abs(float(rate)) >= float(p.get("min_abs_rate", 1)):
                return f"{m['symbol']} funding {float(rate) * 100:+.4f}% (extreme)"
        return None

    if kind == "regime_change" and topic == "regimes":
        regime = data.get("regimes", {}).get(rule.symbol or "")
        if not regime:
            return None
        trend = regime.get("trend")
        prev = state.get("trend")
        state["trend"] = trend
        if prev is not None and trend != prev and trend != "Unknown":
            return f"{rule.symbol} regime: {prev} → {trend}"
        return None

    return None


async def send_telegram(message: str) -> bool:
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": f"🔔 {message}"},
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        logger.warning("telegram delivery failed")
        return False


class AlertEngine:
    """Holds rules in memory, refreshed periodically; evaluates topic messages."""

    def __init__(self, redis: Redis, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.rules: list[AlertRule] = []
        self.last_fired: dict[str, float] = {}
        self._last_refresh = 0.0

    async def refresh_rules(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_refresh < 10:
            return
        self._last_refresh = now
        async with self.session_factory() as session:
            result = await session.execute(select(AlertRule).where(AlertRule.enabled))
            self.rules = list(result.scalars())
            session.expunge_all()

    async def handle(self, topic: str, data: dict[str, Any]) -> list[Fired]:
        await self.refresh_rules()
        fired: list[Fired] = []
        now = time.time()
        for rule in self.rules:
            if now - self.last_fired.get(rule.id, 0) < rule.cooldown_s:
                continue
            state = dict(rule.state_json or {})
            message = evaluate_rule(rule, topic, data, state)
            if state != (rule.state_json or {}):
                rule.state_json = state
                await self._persist_state(rule)
            if message:
                self.last_fired[rule.id] = now
                fired.append(Fired(rule, message, {"topic": topic}))
        for f in fired:
            await self._deliver(f)
        return fired

    async def _persist_state(self, rule: AlertRule) -> None:
        async with self.session_factory() as session:
            db_rule = await session.get(AlertRule, rule.id)
            if db_rule is not None:
                db_rule.state_json = rule.state_json
                await session.commit()

    async def _deliver(self, fired: Fired) -> None:
        event = AlertEvent(
            id=str(uuid.uuid4()),
            rule_id=fired.rule.id,
            ts=datetime.now(UTC),
            message=fired.message,
            payload_json=fired.payload,
        )
        async with self.session_factory() as session:
            session.add(event)
            await session.commit()
        await self.redis.publish(
            "alerts",
            json.dumps(
                {
                    "type": "alert",
                    "rule_id": fired.rule.id,
                    "rule_name": fired.rule.name,
                    "message": fired.message,
                    "ts": int(time.time() * 1000),
                }
            ),
        )
        await send_telegram(fired.message)
        logger.info("alert fired: %s", fired.message)
