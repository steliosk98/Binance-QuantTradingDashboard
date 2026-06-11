"""Order book maintainer: snapshot + diff sync, state in Redis.

Any sequence gap triggers a full resync from a fresh snapshot (spec Known
Risks: never patch over gaps).
"""

import asyncio
import json
import logging
from typing import Any

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.ingestion.orderbook import DepthDiff, OrderBook, SequenceGap
from app.ingestion.ws_streams import BackoffPolicy, consume_stream

logger = logging.getLogger(__name__)

SPOT_BASE = "https://api.binance.com"
SNAPSHOT_LIMIT = 1000


class BookMaintainer:
    def __init__(self, symbol: str, redis: Redis, http: httpx.AsyncClient) -> None:
        self.symbol = symbol.upper()
        self.redis = redis
        self.http = http
        self.book = OrderBook(self.symbol)
        self.buffer: list[DepthDiff] = []
        self.syncing = True

    async def fetch_snapshot(self) -> dict[str, Any]:
        resp = await self.http.get(
            f"{SPOT_BASE}/api/v3/depth",
            params={"symbol": self.symbol, "limit": SNAPSHOT_LIMIT},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def resync(self) -> None:
        self.syncing = True
        self.buffer.clear()
        await asyncio.sleep(0.5)  # let a few diffs buffer
        snapshot = await self.fetch_snapshot()
        self.book.apply_snapshot(snapshot)
        applied = 0
        for diff in self.buffer:
            try:
                if self.book.apply_diff(diff):
                    applied += 1
            except SequenceGap:
                logger.warning("%s: gap during resync replay, retrying", self.symbol)
                await self.resync()
                return
        self.buffer.clear()
        self.syncing = False
        logger.info(
            "%s: book synced (lastUpdateId=%d, %d buffered diffs applied)",
            self.symbol,
            self.book.last_update_id,
            applied,
        )

    async def handle_diff_msg(self, msg: dict[str, Any]) -> None:
        data = msg.get("data", msg)
        if "U" not in data:
            return
        diff = DepthDiff.from_ws(data)
        if self.syncing:
            self.buffer.append(diff)
            return
        try:
            self.book.apply_diff(diff)
        except SequenceGap:
            logger.warning("%s: sequence gap, full resync", self.symbol)
            await self.resync()
            return
        await self.publish()

    async def publish(self) -> None:
        levels = self.book.top_levels(get_settings().orderbook_depth_levels)
        payload = json.dumps({"type": "book", **levels})
        await self.redis.set(f"book:{self.symbol}", payload, ex=30)
        await self.redis.publish(f"book:{self.symbol}", payload)


async def run_book_maintainer(
    symbol: str, redis: Redis, stop_event: asyncio.Event | None = None
) -> None:
    async with httpx.AsyncClient(timeout=15.0) as http:
        maintainer = BookMaintainer(symbol, redis, http)
        url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth@100ms"

        started = asyncio.Event()

        async def handler(msg: dict[str, Any]) -> None:
            if not started.is_set():
                started.set()
                asyncio.get_running_loop().create_task(maintainer.resync())
            await maintainer.handle_diff_msg(msg)

        await consume_stream(
            url,
            handler,
            name=f"book:{symbol}",
            backoff=BackoffPolicy(),
            stop_event=stop_event,
        )
