"""Redis result cache for analytics, keyed by (name, symbol, interval,
last_candle_time, params) so any new closed candle invalidates naturally.
"""

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

CACHE_TTL_SECONDS = 6 * 3600


def cache_key(
    name: str, symbol: str, interval: str, last_candle_ms: int, params: dict[str, Any]
) -> str:
    params_hash = hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"analytics:{name}:{symbol}:{interval}:{last_candle_ms}:{params_hash}"


async def get_cached(redis: Redis, key: str) -> Any | None:
    raw = await redis.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached(redis: Redis, key: str, value: Any) -> None:
    await redis.set(key, json.dumps(value), ex=CACHE_TTL_SECONDS)
