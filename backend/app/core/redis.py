import asyncio
import weakref

from redis.asyncio import Redis

from app.core.config import get_settings

# One client per event loop: connections are loop-bound, and tests create a
# fresh loop per test. In production there is a single long-lived loop.
_redis_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Redis]" = (
    weakref.WeakKeyDictionary()
)


def get_redis() -> Redis:
    loop = asyncio.get_running_loop()
    client = _redis_by_loop.get(loop)
    if client is None:
        client = Redis.from_url(get_settings().redis_url, decode_responses=True)
        _redis_by_loop[loop] = client
    return client
