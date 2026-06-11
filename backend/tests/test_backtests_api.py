"""Backtest API: submit → poll → results; persistence reload."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session import get_engine
from app.ingestion.binance_client import Kline
from app.ingestion.upserts import upsert_candles
from app.main import app
from tests.conftest import TEST_DATABASE_URL

H = 3_600_000


def synth_klines(start_ms: int, count: int, seed: int = 1) -> list[Kline]:
    import numpy as np

    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, count)))
    out = []
    for i in range(count):
        c = float(closes[i])
        o = float(closes[i - 1]) if i else c
        out.append(
            Kline(
                open_time=start_ms + i * H,
                open=o,
                high=max(o, c) * 1.003,
                low=min(o, c) * 0.997,
                close=c,
                volume=10.0,
                close_time=start_ms + (i + 1) * H - 1,
                quote_volume=1000.0,
                trades=5,
                taker_buy_volume=4.0,
            )
        )
    return out


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    # Point the global engine (used by the background executor) at the test DB.
    get_engine(TEST_DATABASE_URL)

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def wait_done(client: httpx.AsyncClient, backtest_id: str, timeout: float = 30.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        resp = await client.get(f"/api/v1/backtests/{backtest_id}")
        body = resp.json()
        if body["status"] in ("done", "error"):
            return body
        await asyncio.sleep(0.1)
    raise TimeoutError("backtest did not finish")


@pytest.mark.asyncio
async def test_strategies_endpoint(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/strategies")
    assert resp.status_code == 200
    strategies = resp.json()["strategies"]
    keys = {s["key"] for s in strategies}
    assert {"sma_crossover", "rsi_mr", "bollinger_mr", "donchian", "zscore_mr"} <= keys
    sma = next(s for s in strategies if s["key"] == "sma_crossover")
    assert {p["name"] for p in sma["params"]} == {"fast", "slow"}


@pytest.mark.asyncio
async def test_backtest_lifecycle(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    base = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(base, 800))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/backtests",
        json={
            "strategy": "sma_crossover",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "params": {"fast": 10, "slow": 30},
        },
    )
    assert resp.status_code == 202
    backtest_id = resp.json()["id"]

    body = await wait_done(client, backtest_id)
    assert body["status"] == "done", body.get("error")
    assert body["metrics"]["bars"] == 800
    assert len(body["equity"]) == 800
    assert isinstance(body["trades"], list)
    assert body["params"] == {"fast": 10, "slow": 30}

    # Persistence: shows up in the list endpoint with metrics
    listing = await client.get("/api/v1/backtests")
    entries = listing.json()["backtests"]
    assert any(e["id"] == backtest_id and e["status"] == "done" for e in entries)


@pytest.mark.asyncio
async def test_backtest_walk_forward(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    base = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    await upsert_candles(db_session, "ETHUSDT", "1h", synth_klines(base, 1200, seed=3))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/backtests",
        json={
            "strategy": "sma_crossover",
            "symbol": "ETHUSDT",
            "walk_forward": True,
            "n_windows": 3,
        },
    )
    body = await wait_done(client, resp.json()["id"], timeout=60)
    assert body["status"] == "done", body.get("error")
    wf = body["walk_forward"]
    assert len(wf["windows"]) == 3
    assert wf["windows"][0]["in_sample"] and wf["windows"][0]["out_of_sample"]
    assert len(wf["oos_equity"]) > 100


@pytest.mark.asyncio
async def test_backtest_validation_errors(client: httpx.AsyncClient) -> None:
    bad_strategy = await client.post(
        "/api/v1/backtests", json={"strategy": "nope", "symbol": "BTCUSDT"}
    )
    assert bad_strategy.status_code == 422
    bad_interval = await client.post(
        "/api/v1/backtests",
        json={"strategy": "sma_crossover", "symbol": "BTCUSDT", "interval": "3m"},
    )
    assert bad_interval.status_code == 422


@pytest.mark.asyncio
async def test_backtest_error_state_for_missing_data(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/backtests", json={"strategy": "sma_crossover", "symbol": "NOPEUSDT"}
    )
    body = await wait_done(client, resp.json()["id"])
    assert body["status"] == "error"
    assert "not enough candles" in body["error"]


@pytest.mark.asyncio
async def test_get_unknown_backtest_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/backtests/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
