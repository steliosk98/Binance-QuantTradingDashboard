"""Live ingestion worker: Binance WS → DB (closed candles) + Redis (live).

Run with: python -m app.ingestion.worker

Connections:
- Spot combined stream: klines (watchlist x intervals) + aggTrades + !ticker@arr
- Futures combined stream: !forceOrder@arr + !markPrice@arr@1s
- One depth diff stream per order-book symbol (BTCUSDT, ETHUSDT by default)
"""

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_session_factory
from app.ingestion.book_maintainer import run_book_maintainer
from app.ingestion.handlers import (
    handle_agg_trade,
    handle_force_order,
    handle_kline,
    handle_mark_price_arr,
    handle_ticker_arr,
)
from app.ingestion.ws_streams import consume_stream

logger = logging.getLogger("worker")

SPOT_WS = "wss://stream.binance.com:9443/stream?streams="
FUTURES_WS = "wss://fstream.binance.com/stream?streams="
KLINE_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")


def spot_stream_url(symbols: list[str]) -> str:
    # NOTE: array streams (!ticker@arr) silently deliver nothing inside
    # combined-stream URLs (verified 2026-06-11) — use per-symbol streams.
    streams: list[str] = []
    for s in symbols:
        sl = s.lower()
        streams.extend(f"{sl}@kline_{iv}" for iv in KLINE_INTERVALS)
        streams.append(f"{sl}@aggTrade")
        streams.append(f"{sl}@ticker")
    return SPOT_WS + "/".join(streams)


def futures_stream_url() -> str:
    return FUTURES_WS + "/".join(["!forceOrder@arr", "!markPrice@arr@1s"])


async def poll_premium_index(redis: Any, interval_s: float = 5.0) -> None:
    """REST fallback for mark price / funding when futures WS is unreachable."""
    from app.ingestion.binance_client import BinanceClient

    async with BinanceClient() as client:
        while True:
            try:
                entries = await client.get_premium_index()
                mapped = [
                    {
                        "s": e["symbol"],
                        "p": e["markPrice"],
                        "i": e["indexPrice"],
                        "r": e.get("lastFundingRate", ""),
                        "T": e.get("nextFundingTime", 0),
                    }
                    for e in entries
                ]
                await handle_mark_price_arr(mapped, redis)
            except Exception:
                logger.exception("premium index poll failed")
            await asyncio.sleep(interval_s)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    redis = get_redis()
    session_factory = get_session_factory()
    symbols = settings.watchlist_symbols

    async def spot_handler(msg: dict[str, Any]) -> None:
        stream = msg.get("stream", "")
        data = msg.get("data", msg)
        try:
            if "@kline" in stream:
                if data.get("k", {}).get("x"):
                    async with session_factory() as session:
                        await handle_kline(data, redis, session)
                else:
                    await handle_kline(data, redis, None)
            elif "@aggTrade" in stream:
                await handle_agg_trade(data, redis)
            elif "@ticker" in stream:
                await handle_ticker_arr([data], redis)
        except Exception:
            logger.exception("spot handler failed for stream %s", stream)

    async def futures_handler(msg: dict[str, Any]) -> None:
        stream = msg.get("stream", "")
        data = msg.get("data", msg)
        try:
            if stream.startswith("!forceOrder"):
                async with session_factory() as session:
                    await handle_force_order(data, redis, session)
            elif stream.startswith("!markPrice"):
                await handle_mark_price_arr(data, redis)
        except Exception:
            logger.exception("futures handler failed for stream %s", stream)

    tasks = [
        asyncio.create_task(
            consume_stream(spot_stream_url(symbols), spot_handler, name="spot"),
            name="spot-stream",
        ),
        # Futures WS is blocked on some networks (connects but never delivers);
        # keep it for hosts where it works — REST poller below is the fallback.
        asyncio.create_task(
            consume_stream(futures_stream_url(), futures_handler, name="futures"),
            name="futures-stream",
        ),
        asyncio.create_task(poll_premium_index(redis), name="premium-index-poller"),
    ]
    tasks.extend(
        asyncio.create_task(run_book_maintainer(s, redis), name=f"book-{s}")
        for s in settings.orderbook_symbol_list
    )
    logger.info(
        "Worker started: %d spot symbols, books for %s",
        len(symbols),
        settings.orderbook_symbol_list,
    )
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
