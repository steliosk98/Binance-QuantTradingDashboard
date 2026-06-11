"""Analytics endpoint contract + cache invalidation tests."""

from collections.abc import AsyncIterator

import httpx
import pytest
import redis as redis_sync
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.ingestion.binance_client import Kline
from app.ingestion.upserts import upsert_candles
from app.main import app

H = 3_600_000


def synth_klines(start_ms: int, count: int, seed: int = 1) -> list[Kline]:
    import numpy as np

    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, count)))
    klines = []
    for i in range(count):
        c = float(closes[i])
        o = float(closes[i - 1]) if i else c
        klines.append(
            Kline(
                open_time=start_ms + i * H,
                open=o,
                high=max(o, c) * 1.005,
                low=min(o, c) * 0.995,
                close=c,
                volume=10.0,
                close_time=start_ms + (i + 1) * H - 1,
                quote_volume=1000.0,
                trades=5,
                taker_buy_volume=4.0,
            )
        )
    return klines


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_analytics_cache() -> None:
    r = redis_sync.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("analytics:*"):
        r.delete(key)
    r.close()


async def seed(
    db: AsyncSession, symbol: str, count: int = 400, start_ms: int = 1700000000000, seed_n: int = 1
):
    aligned = start_ms - start_ms % H
    await upsert_candles(db, symbol, "1h", synth_klines(aligned, count, seed=seed_n))
    await db.commit()
    return aligned


@pytest.mark.asyncio
async def test_indicators_endpoint_shape(client: httpx.AsyncClient, db_session: AsyncSession):
    await seed(db_session, "BTCUSDT")
    resp = await client.get(
        "/api/v1/analytics/indicators", params={"symbol": "BTCUSDT", "interval": "1h"}
    )
    assert resp.status_code == 200
    body = resp.json()
    for field in ("sma_20", "rsi_14", "macd", "bb_upper", "atr_14", "stoch_k", "volume_profile"):
        assert field in body
    # RSI values within bounds
    rsi_vals = [v for _, v in body["rsi_14"] if v is not None]
    assert rsi_vals and all(0 <= v <= 100 for v in rsi_vals)


@pytest.mark.asyncio
async def test_indicators_404_when_no_data(client: httpx.AsyncClient):
    resp = await client.get("/api/v1/analytics/indicators", params={"symbol": "NOPEUSDT"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_returns_and_volatility_endpoints(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    await seed(db_session, "ETHUSDT", count=600)
    r1 = await client.get("/api/v1/analytics/stats/returns", params={"symbol": "ETHUSDT"})
    assert r1.status_code == 200
    assert r1.json()["count"] >= 500
    r2 = await client.get(
        "/api/v1/analytics/stats/volatility", params={"symbol": "ETHUSDT", "window": 30}
    )
    assert r2.status_code == 200
    assert len(r2.json()["close_to_close"]) >= 500


@pytest.mark.asyncio
async def test_pairs_endpoint(client: httpx.AsyncClient, db_session: AsyncSession):
    await seed(db_session, "BTCUSDT", count=400, start_ms=1700000000000, seed_n=1)
    await seed(db_session, "ETHUSDT", count=400, start_ms=1700000000000, seed_n=2)
    resp = await client.get(
        "/api/v1/analytics/stats/pairs",
        params={"symbol_a": "BTCUSDT", "symbol_b": "ETHUSDT", "interval": "1h"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "pvalue" in body and "hedge_ratio" in body and "spread_z" in body
    same = await client.get(
        "/api/v1/analytics/stats/pairs", params={"symbol_a": "BTCUSDT", "symbol_b": "btcusdt"}
    )
    assert same.status_code == 422


@pytest.mark.asyncio
async def test_cache_hit_and_invalidation_on_new_candle(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    start = await seed(db_session, "BTCUSDT", count=300)

    r1 = await client.get("/api/v1/analytics/stats/returns", params={"symbol": "BTCUSDT"})
    count1 = r1.json()["count"]

    # Cached: same response object even though we could recompute
    r2 = await client.get("/api/v1/analytics/stats/returns", params={"symbol": "BTCUSDT"})
    assert r2.json() == r1.json()

    # New closed candle arrives → key changes → recompute with more data
    await upsert_candles(db_session, "BTCUSDT", "1h", synth_klines(start + 300 * H, 1, seed=9))
    await db_session.commit()
    r3 = await client.get("/api/v1/analytics/stats/returns", params={"symbol": "BTCUSDT"})
    assert r3.json()["count"] == count1 + 1
