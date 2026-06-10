"""Weight-aware rate limiting for the Binance REST API.

Binance reports per-minute used request weight in the ``X-MBX-USED-WEIGHT-1M``
response header. We back off once we cross a configurable fraction (default
80%) of the limit, sleeping until the next minute window opens.
"""

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

SPOT_WEIGHT_LIMIT_1M = 6000
FUTURES_WEIGHT_LIMIT_1M = 2400


class WeightLimiter:
    """Tracks server-reported used weight and throttles before the limit."""

    def __init__(
        self,
        max_weight_1m: int,
        backoff_ratio: float = 0.8,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._max_weight = max_weight_1m
        self._threshold = int(max_weight_1m * backoff_ratio)
        self._clock = clock
        self._sleep = sleeper
        self._used_weight = 0
        self._window_minute = int(clock() // 60)
        self._lock = asyncio.Lock()

    @property
    def used_weight(self) -> int:
        return self._used_weight

    def _roll_window(self) -> None:
        minute = int(self._clock() // 60)
        if minute != self._window_minute:
            self._window_minute = minute
            self._used_weight = 0

    async def acquire(self, weight: int) -> None:
        """Wait until ``weight`` can be spent without crossing the threshold."""
        async with self._lock:
            self._roll_window()
            if self._used_weight + weight > self._threshold:
                until_next_minute = 60.0 - (self._clock() % 60.0)
                await self._sleep(until_next_minute)
                self._roll_window()
            # Local pre-accounting; corrected by the server header on response.
            self._used_weight += weight

    def update_from_headers(self, headers: dict[str, str]) -> None:
        """Sync with the authoritative server-side counter when present."""
        for key, value in headers.items():
            if key.lower() == "x-mbx-used-weight-1m":
                with contextlib.suppress(ValueError):
                    self._used_weight = max(self._used_weight, int(value))
                return
