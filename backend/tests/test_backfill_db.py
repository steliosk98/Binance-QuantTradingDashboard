"""Backfill integration tests against a real (dockerized) TimescaleDB.

A fake Binance client serves synthetic klines so no network is involved.
"""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.backfill import backfill_candles
from app.ingestion.binance_client import Kline
from app.ingestion.upserts import upsert_candles
from app.models import Candle

H = 3_600_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H)  # grid-aligned base time


def synth_kline(open_time: int, close: float = 100.0) -> Kline:
    return Kline(
        open_time=open_time,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=10.0,
        close_time=open_time + H - 1,
        quote_volume=1000.0,
        trades=42,
        taker_buy_volume=5.0,
    )


class FakeClient:
    """Serves klines from a fixed universe, honoring start/end/limit."""

    def __init__(self, universe: dict[int, Kline]) -> None:
        self.universe = universe
        self.calls: list[dict[str, Any]] = []

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[Kline]:
        self.calls.append({"start": start_time, "end": end_time})
        times = sorted(
            t
            for t in self.universe
            if (start_time is None or t >= start_time) and (end_time is None or t <= end_time)
        )
        return [self.universe[t] for t in times[:limit]]


async def count_candles(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Candle))).scalar_one()


@pytest.mark.asyncio
async def test_backfill_fills_range_and_is_idempotent(db_session: AsyncSession) -> None:
    universe = {T0 + i * H: synth_kline(T0 + i * H, close=100 + i) for i in range(48)}
    client = FakeClient(universe)

    n1 = await backfill_candles(
        client,  # type: ignore[arg-type]
        db_session,
        "BTCUSDT",
        "1h",
        start_ms=T0,
        end_ms=T0 + 48 * H,  # end is exclusive of the last forming candle
    )
    assert n1 == 48
    assert await count_candles(db_session) == 48

    # Re-run: complete range → no fetches needed, nothing changes.
    client.calls.clear()
    n2 = await backfill_candles(
        client,  # type: ignore[arg-type]
        db_session,
        "BTCUSDT",
        "1h",
        start_ms=T0,
        end_ms=T0 + 48 * H,
    )
    assert n2 == 0
    assert client.calls == []
    assert await count_candles(db_session) == 48


@pytest.mark.asyncio
async def test_gap_repair_fetches_only_missing(db_session: AsyncSession) -> None:
    universe = {T0 + i * H: synth_kline(T0 + i * H) for i in range(24)}
    # Pre-load all but a hole at hours 10..14
    have = [universe[T0 + i * H] for i in range(24) if not 10 <= i <= 14]
    await upsert_candles(db_session, "BTCUSDT", "1h", have)
    await db_session.commit()
    assert await count_candles(db_session) == 19

    client = FakeClient(universe)
    n = await backfill_candles(
        client,  # type: ignore[arg-type]
        db_session,
        "BTCUSDT",
        "1h",
        start_ms=T0,
        end_ms=T0 + 24 * H,
    )
    assert n == 5
    assert await count_candles(db_session) == 24
    # Only the gap range was requested
    assert len(client.calls) == 1
    assert client.calls[0]["start"] == T0 + 10 * H
    assert client.calls[0]["end"] == T0 + 14 * H + H - 1


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(db_session: AsyncSession) -> None:
    k = synth_kline(T0, close=100.0)
    await upsert_candles(db_session, "BTCUSDT", "1h", [k])
    revised = synth_kline(T0, close=999.0)
    await upsert_candles(db_session, "BTCUSDT", "1h", [revised])
    await db_session.commit()
    row = (await db_session.execute(select(Candle))).scalar_one()
    assert row.close == 999.0
