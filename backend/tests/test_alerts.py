"""Alert engine evaluation, cooldowns, delivery, and API CRUD."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import engine as engine_module
from app.alerts.engine import AlertEngine, evaluate_rule, send_telegram
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.models import AlertEvent, AlertRule
from tests.conftest import TEST_DATABASE_URL


def make_rule(kind: str, symbol: str | None = None, **params: Any) -> AlertRule:
    return AlertRule(
        id=str(uuid.uuid4()),
        name=f"test-{kind}",
        kind=kind,
        symbol=symbol,
        params_json=params,
        enabled=True,
        cooldown_s=300,
        state_json={},
    )


def test_price_cross_above_fires_once_per_cross() -> None:
    rule = make_rule("price_cross", "BTCUSDT", level=60000, direction="above")
    state: dict[str, Any] = {}
    below = {"tickers": [{"symbol": "BTCUSDT", "last": 59000}]}
    above = {"tickers": [{"symbol": "BTCUSDT", "last": 61000}]}
    assert evaluate_rule(rule, "tickers", below, state) is None  # establishes side
    msg = evaluate_rule(rule, "tickers", above, state)
    assert msg is not None and "crossed above" in msg
    # Still above → no re-fire (no new cross)
    assert evaluate_rule(rule, "tickers", above, state) is None
    # Dip below then cross again → fires again
    assert evaluate_rule(rule, "tickers", below, state) is None
    assert evaluate_rule(rule, "tickers", above, state) is not None


def test_price_cross_below() -> None:
    rule = make_rule("price_cross", "BTCUSDT", level=60000, direction="below")
    state: dict[str, Any] = {}
    evaluate_rule(rule, "tickers", {"tickers": [{"symbol": "BTCUSDT", "last": 61000}]}, state)
    msg = evaluate_rule(rule, "tickers", {"tickers": [{"symbol": "BTCUSDT", "last": 59000}]}, state)
    assert msg is not None and "crossed below" in msg


def test_whale_and_liquidation_thresholds() -> None:
    whale = make_rule("whale_trade", min_usd=500_000)
    small = {"symbol": "BTCUSDT", "value": 300_000, "is_buyer_maker": False}
    big = {"symbol": "BTCUSDT", "value": 900_000, "is_buyer_maker": False}
    assert evaluate_rule(whale, "whales", small, {}) is None
    assert "Whale BUY" in (evaluate_rule(whale, "whales", big, {}) or "")

    liq = make_rule("liquidation", "ETHUSDT", min_usd=100_000)
    other = {"symbol": "BTCUSDT", "value": 200_000, "side": "long"}
    match = {"symbol": "ETHUSDT", "value": 200_000, "side": "long"}
    assert evaluate_rule(liq, "liqs", other, {}) is None
    assert "LONG liquidation ETHUSDT" in (evaluate_rule(liq, "liqs", match, {}) or "")


def test_funding_abs_and_regime_change() -> None:
    funding = make_rule("funding_abs", min_abs_rate=0.001)
    calm = {"marks": [{"symbol": "BTCUSDT", "funding_rate": 0.0001}]}
    hot = {"marks": [{"symbol": "BTCUSDT", "funding_rate": -0.002}]}
    assert evaluate_rule(funding, "marks", calm, {}) is None
    assert "funding" in (evaluate_rule(funding, "marks", hot, {}) or "")

    regime = make_rule("regime_change", "BTCUSDT")
    state: dict[str, Any] = {}
    first = {"regimes": {"BTCUSDT": {"trend": "Ranging"}}}
    changed = {"regimes": {"BTCUSDT": {"trend": "Trending"}}}
    assert evaluate_rule(regime, "regimes", first, state) is None  # baseline
    msg = evaluate_rule(regime, "regimes", changed, state)
    assert msg == "BTCUSDT regime: Ranging → Trending"
    assert evaluate_rule(regime, "regimes", changed, state) is None  # unchanged


@pytest.mark.asyncio
async def test_engine_cooldown_and_event_persistence(db_session: AsyncSession) -> None:
    get_engine(TEST_DATABASE_URL)  # point global factory at test DB
    rule = make_rule("whale_trade", min_usd=100)
    db_session.add(rule)
    await db_session.commit()

    engine = AlertEngine(get_redis(), get_session_factory())
    await engine.refresh_rules(force=True)
    big = {"symbol": "BTCUSDT", "value": 1_000_000, "is_buyer_maker": True}

    fired1 = await engine.handle("whales", big)
    assert len(fired1) == 1
    # Cooldown suppresses an immediate duplicate
    fired2 = await engine.handle("whales", big)
    assert fired2 == []

    events = (await db_session.execute(select(AlertEvent))).scalars().all()
    assert len(events) == 1
    assert "Whale SELL" in events[0].message


@pytest.mark.asyncio
@respx.mock
async def test_telegram_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    route = respx.post("https://api.telegram.org/botbot-token/sendMessage").respond(
        json={"ok": True}
    )
    assert await send_telegram("hello") is True
    assert route.called
    body = route.calls[0].request.content.decode()
    assert "12345" in body and "hello" in body


@pytest.mark.asyncio
async def test_telegram_skipped_without_config() -> None:
    assert await send_telegram("nope") is False


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rules_crud(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/alerts/rules",
        json={
            "name": "BTC above 70k",
            "kind": "price_cross",
            "symbol": "btcusdt",
            "params": {"level": 70000, "direction": "above"},
        },
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["symbol"] == "BTCUSDT" and rule["enabled"] is True

    listing = (await client.get("/api/v1/alerts/rules")).json()["rules"]
    assert any(r["id"] == rule["id"] for r in listing)

    toggled = (await client.post(f"/api/v1/alerts/rules/{rule['id']}/toggle")).json()
    assert toggled["enabled"] is False

    bad = await client.post("/api/v1/alerts/rules", json={"name": "x", "kind": "nope"})
    assert bad.status_code == 422
    missing_symbol = await client.post(
        "/api/v1/alerts/rules", json={"name": "x", "kind": "price_cross"}
    )
    assert missing_symbol.status_code == 422

    deleted = await client.delete(f"/api/v1/alerts/rules/{rule['id']}")
    assert deleted.json() == {"status": "deleted"}
    assert (await client.get("/api/v1/alerts/events")).status_code == 200


def test_engine_module_has_expected_kinds() -> None:
    assert set(engine_module.RULE_KINDS) == {
        "price_cross",
        "whale_trade",
        "liquidation",
        "funding_abs",
        "regime_change",
    }
