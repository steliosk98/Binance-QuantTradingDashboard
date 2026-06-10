"""Idempotent historical backfill CLI.

Usage:
    python -m app.ingestion.backfill --symbols BTCUSDT,ETHUSDT --intervals 1h,1d

Strategy: for each (symbol, interval) compute the expected time grid for the
spec's historical depth, diff it against what is already in the database
(gap detection), and fetch only the missing ranges. Upserts make re-runs
no-ops; permanent exchange-downtime gaps simply return no rows.
"""

import argparse
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.binance_client import (
    FUNDING_MAX_LIMIT,
    FUTURES_DATA_MAX_LIMIT,
    INTERVAL_MS,
    KLINES_MAX_LIMIT,
    BinanceClient,
)
from app.ingestion.gaps import GapRange, align_to_grid, find_gaps
from app.ingestion.upserts import (
    upsert_candles,
    upsert_funding_rates,
    upsert_long_short_ratio,
    upsert_open_interest,
)
from app.models import Candle, FundingRate, LongShortRatio, OpenInterest

logger = logging.getLogger("backfill")

DAY_MS = 86_400_000

#: Historical depth per interval (spec §3.1).
DEPTH_MS: dict[str, int] = {
    "1m": 30 * DAY_MS,
    "5m": 90 * DAY_MS,
    "15m": 90 * DAY_MS,
    "1h": 2 * 365 * DAY_MS,
    "4h": 2 * 365 * DAY_MS,
    "1d": 2 * 365 * DAY_MS,
}


async def _existing_candle_times(
    session: AsyncSession, symbol: str, interval: str, start_ms: int, end_ms: int
) -> list[int]:
    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp(end_ms / 1000, tz=UTC)
    result = await session.execute(
        select(Candle.open_time)
        .where(
            Candle.symbol == symbol,
            Candle.interval == interval,
            Candle.open_time >= start_dt,
            Candle.open_time <= end_dt,
        )
        .order_by(Candle.open_time)
    )
    return [int(row[0].timestamp() * 1000) for row in result]


async def backfill_candles(
    client: BinanceClient,
    session: AsyncSession,
    symbol: str,
    interval: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> int:
    """Fill missing candles for (symbol, interval); returns rows upserted."""
    interval_ms = INTERVAL_MS[interval]
    now_ms = int(time.time() * 1000)
    # Exclude the still-forming candle.
    range_end = align_to_grid(end_ms if end_ms is not None else now_ms, interval_ms) - interval_ms
    range_start = align_to_grid(
        start_ms if start_ms is not None else now_ms - DEPTH_MS[interval], interval_ms
    )

    existing = await _existing_candle_times(session, symbol, interval, range_start, range_end)
    gaps = find_gaps(existing, interval_ms, range_start, range_end)
    if not gaps:
        logger.info("%s %s: complete, no gaps", symbol, interval)
        return 0

    total = 0
    for gap in gaps:
        total += await _fill_gap(client, session, symbol, interval, gap, interval_ms)
    logger.info("%s %s: upserted %d candles across %d gap(s)", symbol, interval, total, len(gaps))
    return total


async def _fill_gap(
    client: BinanceClient,
    session: AsyncSession,
    symbol: str,
    interval: str,
    gap: GapRange,
    interval_ms: int,
) -> int:
    upserted = 0
    cursor = gap.start_ms
    while cursor <= gap.end_ms:
        batch_end = min(gap.end_ms, cursor + (KLINES_MAX_LIMIT - 1) * interval_ms)
        klines = await client.get_klines(
            symbol,
            interval,
            start_time=cursor,
            end_time=batch_end + interval_ms - 1,
            limit=KLINES_MAX_LIMIT,
        )
        if not klines:
            # Exchange has no data here (downtime or pre-listing); move on.
            cursor = batch_end + interval_ms
            continue
        upserted += await upsert_candles(session, symbol, interval, klines)
        await session.commit()
        cursor = klines[-1].open_time + interval_ms
        logger.info(
            "%s %s: %s → %d rows (total %d)",
            symbol,
            interval,
            datetime.fromtimestamp(cursor / 1000, tz=UTC).isoformat(),
            len(klines),
            upserted,
        )
    return upserted


#: Binance futures funding history starts around 2019-09; safe lower bound.
FUNDING_FLOOR_MS = 1_546_300_800_000  # 2019-01-01

#: /futures/data/* endpoints only retain ~30 days of history.
FUTURES_DATA_RETENTION_MS = 30 * DAY_MS

_WindowFetch = Callable[[int, int], Awaitable[list[dict[str, Any]]]]


async def _fetch_windows(
    fetch: _WindowFetch, start_ms: int, window_ms: int
) -> AsyncIterator[list[dict[str, Any]]]:
    """Walk [start, now] in explicit windows.

    The /futures/data/* and fundingRate endpoints return the LATEST ``limit``
    rows when only startTime is sent, so we must always pass both bounds.
    """
    now_ms = int(time.time() * 1000)
    cursor = start_ms
    while cursor <= now_ms:
        window_end = min(cursor + window_ms - 1, now_ms)
        entries = await fetch(cursor, window_end)
        if entries:
            yield entries
        cursor = window_end + 1


async def _latest_ts_ms(
    session: AsyncSession, column: Any, symbol_column: Any, symbol: str
) -> int | None:
    result = await session.execute(
        select(column).where(symbol_column == symbol).order_by(column.desc()).limit(1)
    )
    latest = result.scalar_one_or_none()
    return int(latest.timestamp() * 1000) if latest else None


async def backfill_funding(client: BinanceClient, session: AsyncSession, symbol: str) -> int:
    latest = await _latest_ts_ms(session, FundingRate.funding_time, FundingRate.symbol, symbol)
    start = latest + 1 if latest else FUNDING_FLOOR_MS
    funding_period_ms = 8 * 3_600_000
    window_ms = FUNDING_MAX_LIMIT * funding_period_ms
    total = 0

    async def fetch(s: int, e: int) -> list[dict[str, Any]]:
        return await client.get_funding_rates(symbol, start_time=s, end_time=e)

    async for entries in _fetch_windows(fetch, start, window_ms):
        total += await upsert_funding_rates(session, symbol, entries)
        await session.commit()
    logger.info("%s funding: upserted %d", symbol, total)
    return total


async def backfill_open_interest(client: BinanceClient, session: AsyncSession, symbol: str) -> int:
    latest = await _latest_ts_ms(session, OpenInterest.ts, OpenInterest.symbol, symbol)
    floor = int(time.time() * 1000) - FUTURES_DATA_RETENTION_MS
    start = max(latest + 1 if latest else 0, floor)
    window_ms = FUTURES_DATA_MAX_LIMIT * 300_000  # 500 x 5m
    total = 0

    async def fetch(s: int, e: int) -> list[dict[str, Any]]:
        return await client.get_open_interest_hist(symbol, start_time=s, end_time=e)

    async for entries in _fetch_windows(fetch, start, window_ms):
        total += await upsert_open_interest(session, symbol, entries)
        await session.commit()
    logger.info("%s open interest: upserted %d", symbol, total)
    return total


async def backfill_long_short_ratio(
    client: BinanceClient, session: AsyncSession, symbol: str
) -> int:
    latest = await _latest_ts_ms(session, LongShortRatio.ts, LongShortRatio.symbol, symbol)
    floor = int(time.time() * 1000) - FUTURES_DATA_RETENTION_MS
    start = max(latest + 1 if latest else 0, floor)
    window_ms = FUTURES_DATA_MAX_LIMIT * 300_000
    total = 0

    async def fetch(s: int, e: int) -> list[dict[str, Any]]:
        return await client.get_long_short_ratio(symbol, start_time=s, end_time=e)

    async for entries in _fetch_windows(fetch, start, window_ms):
        total += await upsert_long_short_ratio(session, symbol, entries)
        await session.commit()
    logger.info("%s long/short ratio: upserted %d", symbol, total)
    return total


async def run_backfill(
    symbols: list[str],
    intervals: list[str],
    include_futures: bool,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    from app.db.session import session_scope

    async with BinanceClient() as client:
        for symbol in symbols:
            for interval in intervals:
                async with session_scope() as session:
                    await backfill_candles(client, session, symbol, interval, start_ms, end_ms)
            if include_futures:
                async with session_scope() as session:
                    await backfill_funding(client, session, symbol)
                async with session_scope() as session:
                    await backfill_open_interest(client, session, symbol)
                async with session_scope() as session:
                    await backfill_long_short_ratio(client, session, symbol)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Backfill Binance market data")
    parser.add_argument(
        "--symbols",
        default=settings.watchlist,
        help="Comma-separated symbols (default: WATCHLIST)",
    )
    parser.add_argument(
        "--intervals",
        default="1m,5m,15m,1h,4h,1d",
        help="Comma-separated intervals",
    )
    parser.add_argument("--start", type=int, default=None, help="Range start (epoch ms)")
    parser.add_argument("--end", type=int, default=None, help="Range end (epoch ms)")
    parser.add_argument(
        "--no-futures",
        action="store_true",
        help="Skip funding/OI/long-short ratio backfill",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    for interval in intervals:
        if interval not in INTERVAL_MS:
            parser.error(f"unsupported interval: {interval}")

    asyncio.run(run_backfill(symbols, intervals, not args.no_futures, args.start, args.end))


if __name__ == "__main__":
    main()
