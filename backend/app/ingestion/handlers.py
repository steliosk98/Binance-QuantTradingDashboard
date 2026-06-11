"""Pure-ish message handlers for the WS worker: parse → persist/publish.

Separated from connection management so they are unit-testable. All publish
payloads are JSON strings on Redis pub/sub channels:

- ``candles:{symbol}:{interval}`` — forming + closed candles
- ``trades:{symbol}`` — aggTrades (with whale flag)
- ``tickers`` — 24h ticker array snapshot
- ``liqs`` — futures liquidations
- ``marks`` — mark price / funding array
- ``book:{symbol}`` — order book top levels
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.binance_client import Kline
from app.ingestion.upserts import upsert_candles
from app.models import Liquidation

logger = logging.getLogger(__name__)


class SessionRunner(Protocol):
    async def __call__(self, fn: Any) -> Any: ...


def kline_from_ws(k: dict[str, Any]) -> Kline:
    return Kline(
        open_time=int(k["t"]),
        open=float(k["o"]),
        high=float(k["h"]),
        low=float(k["l"]),
        close=float(k["c"]),
        volume=float(k["v"]),
        close_time=int(k["T"]),
        quote_volume=float(k["q"]),
        trades=int(k["n"]),
        taker_buy_volume=float(k["V"]),
    )


def candle_payload(symbol: str, interval: str, k: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "candle",
        "symbol": symbol,
        "interval": interval,
        "open_time": datetime.fromtimestamp(int(k["t"]) / 1000, tz=UTC).isoformat(),
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"]),
        "closed": bool(k["x"]),
    }


async def handle_kline(
    msg: dict[str, Any],
    redis: Redis,
    session: AsyncSession | None,
) -> None:
    """Forming candle → Redis; closed candle → DB upsert too."""
    k = msg["k"]
    symbol = str(msg["s"]).upper()
    interval = str(k["i"])
    payload = candle_payload(symbol, interval, k)
    await redis.set(f"forming:{symbol}:{interval}", json.dumps(payload), ex=120)
    await redis.publish(f"candles:{symbol}:{interval}", json.dumps(payload))
    if k["x"] and session is not None:
        await upsert_candles(session, symbol, interval, [kline_from_ws(k)])
        await session.commit()


async def handle_agg_trade(msg: dict[str, Any], redis: Redis) -> None:
    symbol = str(msg["s"]).upper()
    price = float(msg["p"])
    qty = float(msg["q"])
    value = price * qty
    whale_threshold = get_settings().whale_threshold_usd
    payload = {
        "type": "trade",
        "symbol": symbol,
        "ts": int(msg["T"]),
        "price": price,
        "qty": qty,
        "value": value,
        "is_buyer_maker": bool(msg["m"]),
        "whale": value >= whale_threshold,
    }
    await redis.publish(f"trades:{symbol}", json.dumps(payload))
    if payload["whale"]:
        await redis.publish("whales", json.dumps(payload))
        await redis.lpush("recent_whales", json.dumps(payload))
        await redis.ltrim("recent_whales", 0, 99)


async def handle_ticker_arr(msg: list[dict[str, Any]], redis: Redis) -> None:
    watch = set(get_settings().watchlist_symbols)
    tickers = [
        {
            "symbol": t["s"],
            "last": float(t["c"]),
            "change_pct": float(t["P"]),
            "quote_volume": float(t["q"]),
        }
        for t in msg
        if t["s"] in watch
    ]
    if not tickers:
        return
    payload = {"type": "tickers", "tickers": tickers}
    for t in tickers:
        await redis.hset("latest_tickers", t["symbol"], json.dumps(t))
    await redis.publish("tickers", json.dumps(payload))


async def handle_force_order(
    msg: dict[str, Any], redis: Redis, session: AsyncSession | None
) -> None:
    o = msg["o"]
    symbol = str(o["s"]).upper()
    price = float(o["ap"]) or float(o["p"])
    qty = float(o["q"])
    ts = datetime.fromtimestamp(int(o["T"]) / 1000, tz=UTC)
    # SELL force order = long position liquidated
    side = "long" if o["S"] == "SELL" else "short"
    payload = {
        "type": "liquidation",
        "symbol": symbol,
        "ts": int(o["T"]),
        "side": side,
        "price": price,
        "qty": qty,
        "value": price * qty,
    }
    await redis.publish("liqs", json.dumps(payload))
    await redis.lpush("recent_liqs", json.dumps(payload))
    await redis.ltrim("recent_liqs", 0, 99)
    if session is not None:
        stmt = insert(Liquidation).values(
            symbol=symbol, ts=ts, side=side, price=price, qty=qty, value_usdt=price * qty
        )
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()


async def handle_mark_price_arr(msg: list[dict[str, Any]], redis: Redis) -> None:
    watch = set(get_settings().watchlist_symbols)
    marks = [
        {
            "symbol": m["s"],
            "mark": float(m["p"]),
            "index": float(m["i"]),
            "funding_rate": float(m["r"]) if m.get("r") not in (None, "") else None,
            "next_funding": int(m["T"]),
        }
        for m in msg
        if m["s"] in watch
    ]
    if not marks:
        return
    payload = {"type": "marks", "marks": marks}
    await redis.set("latest_marks", json.dumps(payload), ex=60)
    await redis.publish("marks", json.dumps(payload))
