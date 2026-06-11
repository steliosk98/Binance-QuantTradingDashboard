"""Reconnecting WebSocket stream consumer.

Binance drops connections every 24h — we proactively reconnect before that
and treat any disconnect as a normal event with exponential backoff capped
at 60s (spec Known Risks).
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import websockets

logger = logging.getLogger(__name__)

PROACTIVE_RECONNECT_SECONDS = 23 * 3600
MAX_BACKOFF_SECONDS = 60.0


def backoff_delays(base: float = 1.0, cap: float = MAX_BACKOFF_SECONDS) -> "BackoffPolicy":
    return BackoffPolicy(base=base, cap=cap)


class BackoffPolicy:
    """Exponential backoff that resets after a successful connection."""

    def __init__(self, base: float = 1.0, cap: float = MAX_BACKOFF_SECONDS) -> None:
        self.base = base
        self.cap = cap
        self.attempt = 0

    def next_delay(self) -> float:
        delay: float = min(self.base * (2**self.attempt), self.cap)
        self.attempt += 1
        return delay

    def reset(self) -> None:
        self.attempt = 0


async def consume_stream(
    url: str,
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    *,
    name: str = "ws",
    backoff: BackoffPolicy | None = None,
    reconnect_after: float = PROACTIVE_RECONNECT_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Consume a WS stream forever, reconnecting on any failure."""
    backoff = backoff or BackoffPolicy()
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("[%s] connected", name)
                backoff.reset()
                deadline = asyncio.get_running_loop().time() + reconnect_after
                async for raw in _messages_until(ws, deadline, stop_event):
                    msg = json.loads(raw)
                    await handler(msg)
                if stop_event.is_set():
                    return
                logger.info("[%s] proactive reconnect (24h limit)", name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if stop_event.is_set():
                return
            delay = backoff.next_delay()
            logger.warning("[%s] disconnected (%s); reconnecting in %.1fs", name, exc, delay)
            await asyncio.sleep(delay)


async def _messages_until(
    ws: Any, deadline: float, stop_event: asyncio.Event
) -> AsyncIterator[str | bytes]:
    loop = asyncio.get_running_loop()
    while loop.time() < deadline and not stop_event.is_set():
        timeout = min(deadline - loop.time(), 1.0)
        with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
            yield await asyncio.wait_for(ws.recv(), timeout=timeout)
