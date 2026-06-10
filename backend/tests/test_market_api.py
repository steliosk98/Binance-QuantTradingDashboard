"""Contract tests for the market REST API against the test database."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.ingestion.binance_client import Kline
from app.ingestion.upserts import upsert_candles, upsert_funding_rates
from app.main import app

H = 3_600_000


def synth_klines(start_ms: int, count: int) -> list[Kline]:
    return [
        Kline(
            open_time=start_ms + i * H,
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=10.0,
            close_time=start_ms + (i + 1) * H - 1,
            quote_volume=1000.0,
            trades=5,
            taker_buy_volume=4.0,
        )
        for i in range(count)
    ]


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
async def test_candles_returns_ascending_and_capped(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    now_ms = int(datetime.now(UTC).timestamp() * 1000) // H * H
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(now_ms - 50 * H, 50))
    await db_session.commit()

    resp = await client.get("/api/v1/candles", params={"symbol": "BTCUSDT", "limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"
    candles = body["candles"]
    assert len(candles) == 10
    times = [c["open_time"] for c in candles]
    assert times == sorted(times)
    # Most recent 10 of the 50
    assert candles[-1]["close"] == 100.5 + 49


@pytest.mark.asyncio
async def test_candles_start_end_window(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    base_ms = int(base.timestamp() * 1000)
    await upsert_candles(db_session, "ETHUSDT", "1h", synth_klines(base_ms, 24))
    await db_session.commit()

    resp = await client.get(
        "/api/v1/candles",
        params={
            "symbol": "ETHUSDT",
            "interval": "1h",
            "start": (base + timedelta(hours=5)).isoformat(),
            "end": (base + timedelta(hours=9)).isoformat(),
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["candles"]) == 5


@pytest.mark.asyncio
async def test_candles_empty_range_is_empty_list(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/candles", params={"symbol": "NOPEUSDT"})
    assert resp.status_code == 200
    assert resp.json()["candles"] == []


@pytest.mark.asyncio
async def test_candles_validation(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/candles")).status_code == 422  # symbol required
    assert (
        await client.get("/api/v1/candles", params={"symbol": "BTCUSDT", "interval": "3m"})
    ).status_code == 422
    assert (
        await client.get("/api/v1/candles", params={"symbol": "BTCUSDT", "limit": 5000})
    ).status_code == 422
    assert (
        await client.get("/api/v1/candles", params={"symbol": "BTCUSDT", "limit": 0})
    ).status_code == 422


@pytest.mark.asyncio
async def test_symbols_lists_available(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(0, 1))
    await db_session.commit()
    resp = await client.get("/api/v1/symbols")
    assert resp.status_code == 200
    body = resp.json()
    assert "BTCUSDT" in body["available"]
    assert "BTCUSDT" in body["watchlist"]


@pytest.mark.asyncio
async def test_funding_endpoint(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    entries = [{"fundingTime": now_ms - i * 8 * H, "fundingRate": "0.0001"} for i in range(5)]
    await upsert_funding_rates(db_session, "BTCUSDT", entries)
    await db_session.commit()
    resp = await client.get("/api/v1/funding", params={"symbol": "BTCUSDT", "limit": 3})
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 3


@pytest.mark.asyncio
async def test_ticker_summary_shape(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    now_ms = int(datetime.now(UTC).timestamp() * 1000) // H * H
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(now_ms - 24 * H, 24))
    await db_session.commit()
    resp = await client.get("/api/v1/ticker-summary")
    assert resp.status_code == 200
    tickers = {t["symbol"]: t for t in resp.json()["tickers"]}
    btc = tickers["BTCUSDT"]
    assert btc["last_price"] is not None
    assert btc["change_24h_pct"] is not None
    # Symbol with no data degrades to nulls, not an error
    assert tickers["DOGEUSDT"]["last_price"] is None
