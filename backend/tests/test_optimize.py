"""Optimizer grid endpoint."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.ingestion.upserts import upsert_candles
from app.main import app
from tests.test_backtests_api import synth_klines


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
async def test_optimize_grid(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    base = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(base, 900, seed=5))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/optimize",
        json={
            "strategy": "sma_crossover",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "param_x": "fast",
            "param_y": "slow",
            "x_values": [5, 10, 20],
            "y_values": [30, 50],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sharpe"]) == 2 and len(body["sharpe"][0]) == 3
    assert len(body["total_return"]) == 2
    best = body["best"]
    assert best["params"]["fast"] in (5, 10, 20)
    assert best["params"]["slow"] in (30, 50)
    # Best cell's sharpe matches its grid entry
    xi = body["x_values"].index(best["params"]["fast"])
    yi = body["y_values"].index(best["params"]["slow"])
    assert body["sharpe"][yi][xi] == pytest.approx(best["sharpe"])


@pytest.mark.asyncio
async def test_optimize_validation(client: httpx.AsyncClient) -> None:
    bad_param = await client.post(
        "/api/v1/optimize",
        json={
            "strategy": "sma_crossover",
            "symbol": "BTCUSDT",
            "param_x": "nope",
            "param_y": "slow",
            "x_values": [1, 2],
            "y_values": [3, 4],
        },
    )
    assert bad_param.status_code == 422
    pairs = await client.post(
        "/api/v1/optimize",
        json={
            "strategy": "pairs_trading",
            "symbol": "BTCUSDT",
            "param_x": "entry_z",
            "param_y": "exit_z",
            "x_values": [1, 2],
            "y_values": [0, 0.5],
        },
    )
    assert pairs.status_code == 422
