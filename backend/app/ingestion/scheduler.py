"""Periodic top-up scheduler for funding / open interest / long-short ratio.

Run with: python -m app.ingestion.scheduler
Candle freshness is handled by the WS layer (Stage 3) + gap repair on backfill
re-runs; this process keeps the slower futures series current.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import session_scope
from app.ingestion.backfill import (
    backfill_candles,
    backfill_funding,
    backfill_long_short_ratio,
    backfill_open_interest,
)
from app.ingestion.binance_client import BinanceClient

logger = logging.getLogger("scheduler")


async def top_up_futures_data() -> None:
    symbols = get_settings().watchlist_symbols
    async with BinanceClient() as client:
        for symbol in symbols:
            try:
                async with session_scope() as session:
                    await backfill_funding(client, session, symbol)
                async with session_scope() as session:
                    await backfill_open_interest(client, session, symbol)
                async with session_scope() as session:
                    await backfill_long_short_ratio(client, session, symbol)
            except Exception:
                logger.exception("futures top-up failed for %s", symbol)


async def top_up_candles() -> None:
    symbols = get_settings().watchlist_symbols
    async with BinanceClient() as client:
        for symbol in symbols:
            for interval in ("1m", "5m", "15m", "1h", "4h", "1d"):
                try:
                    async with session_scope() as session:
                        await backfill_candles(client, session, symbol, interval)
                except Exception:
                    logger.exception("candle top-up failed for %s %s", symbol, interval)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(top_up_futures_data, "interval", minutes=5, max_instances=1)
    scheduler.add_job(top_up_candles, "interval", minutes=15, max_instances=1)
    scheduler.start()
    logger.info("Scheduler started (futures top-up: 5m, candle top-up: 15m)")
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
