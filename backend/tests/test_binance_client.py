from typing import Any

import httpx
import pytest
import respx

from app.core.ratelimit import WeightLimiter
from app.ingestion.binance_client import SPOT_BASE, BinanceAPIError, BinanceClient

KLINE_ROW: list[Any] = [
    1700000000000,
    "37000.1",
    "37100.5",
    "36900.0",
    "37050.2",
    "123.45",
    1700003599999,
    "4567890.12",
    9876,
    "61.7",
    "2287654.3",
    "0",
]


def make_client(**kwargs: Any) -> BinanceClient:
    return BinanceClient(http=httpx.AsyncClient(timeout=5.0), base_backoff=0.001, **kwargs)


@pytest.mark.asyncio
@respx.mock
async def test_get_klines_parses_rows() -> None:
    respx.get(f"{SPOT_BASE}/api/v3/klines").respond(json=[KLINE_ROW])
    client = make_client()
    klines = await client.get_klines("BTCUSDT", "1h")
    assert len(klines) == 1
    k = klines[0]
    assert k.open_time == 1700000000000
    assert k.open == 37000.1
    assert k.close == 37050.2
    assert k.trades == 9876
    assert k.taker_buy_volume == 61.7
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_429_with_retry_after() -> None:
    route = respx.get(f"{SPOT_BASE}/api/v3/klines")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json=[KLINE_ROW]),
    ]
    client = make_client()
    klines = await client.get_klines("BTCUSDT", "1h")
    assert len(klines) == 1
    assert route.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_5xx_then_fails() -> None:
    respx.get(f"{SPOT_BASE}/api/v3/klines").respond(502)
    client = make_client(max_retries=2)
    with pytest.raises(BinanceAPIError, match="HTTP 502"):
        await client.get_klines("BTCUSDT", "1h")
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_weight_header_feeds_limiter() -> None:
    respx.get(f"{SPOT_BASE}/api/v3/klines").respond(
        json=[KLINE_ROW], headers={"X-MBX-USED-WEIGHT-1M": "4321"}
    )
    limiter = WeightLimiter(6000)
    client = make_client(spot_limiter=limiter)
    await client.get_klines("BTCUSDT", "1h")
    assert limiter.used_weight == 4321
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_4xx_raises_without_retry() -> None:
    route = respx.get(f"{SPOT_BASE}/api/v3/klines").respond(400, json={"msg": "bad"})
    client = make_client()
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_klines("BTCUSDT", "1h")
    assert route.call_count == 1
    await client.aclose()
