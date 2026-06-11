"""WebSocket relay hub: clients subscribe to topics fanned out from Redis.

Protocol (JSON messages from client):
    {"op": "subscribe", "topics": ["candles:BTCUSDT:1m", "tickers"]}
    {"op": "unsubscribe", "topics": ["tickers"]}

Server forwards every Redis pub/sub message on a subscribed topic verbatim,
wrapped as {"topic": ..., "data": ...}.
"""

import asyncio
import contextlib
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio.client import PubSub

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

TOPIC_RE = re.compile(r"^[a-zA-Z0-9:_\-]{1,64}$")
MAX_TOPICS = 50


def valid_topics(topics: object) -> list[str]:
    if not isinstance(topics, list):
        return []
    return [t for t in topics if isinstance(t, str) and TOPIC_RE.match(t)][:MAX_TOPICS]


async def _relay(pubsub: PubSub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] not in ("message", "pmessage"):
            continue
        topic = message["channel"]
        with contextlib.suppress(json.JSONDecodeError):
            await websocket.send_text(
                json.dumps({"topic": topic, "data": json.loads(message["data"])})
            )


@router.websocket("/ws")
async def ws_hub(websocket: WebSocket) -> None:
    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    relay_task: asyncio.Task[None] | None = None
    subscribed: set[str] = set()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "invalid json"}))
                continue
            op = msg.get("op")
            topics = valid_topics(msg.get("topics"))
            if op == "subscribe" and topics:
                new = [t for t in topics if t not in subscribed]
                if len(subscribed) + len(new) > MAX_TOPICS:
                    await websocket.send_text(json.dumps({"error": "too many topics"}))
                    continue
                if new:
                    await pubsub.subscribe(*new)
                    subscribed.update(new)
                    if relay_task is None:
                        relay_task = asyncio.create_task(_relay(pubsub, websocket))
                await websocket.send_text(
                    json.dumps({"op": "subscribed", "topics": sorted(subscribed)})
                )
            elif op == "unsubscribe" and topics:
                stale = [t for t in topics if t in subscribed]
                if stale:
                    await pubsub.unsubscribe(*stale)
                    subscribed.difference_update(stale)
                await websocket.send_text(
                    json.dumps({"op": "subscribed", "topics": sorted(subscribed)})
                )
            elif op == "ping":
                await websocket.send_text(json.dumps({"op": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        if relay_task is not None:
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task
        await pubsub.aclose()  # type: ignore[no-untyped-call]
