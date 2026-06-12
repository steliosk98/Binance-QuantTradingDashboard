"""Alert engine wiring: psubscribe live topics + 15-minute regime sweep."""

import asyncio
import json
import logging
from typing import Any

from app.alerts.engine import AlertEngine
from app.core.redis import get_redis
from app.db.session import get_session_factory

logger = logging.getLogger("alerts")

LIVE_TOPICS = ("tickers", "whales", "liqs", "marks")
REGIME_SWEEP_SECONDS = 900


async def run_alert_engine() -> None:
    redis = get_redis()
    engine = AlertEngine(redis, get_session_factory())
    pubsub = redis.pubsub()
    await pubsub.subscribe(*LIVE_TOPICS)
    logger.info("Alert engine subscribed to %s", LIVE_TOPICS)

    async def regime_sweep() -> None:
        from app.api.analytics import get_regime

        while True:
            try:
                factory = get_session_factory()
                async with factory() as session:
                    # Reuse the cached regime computation directly.
                    result: dict[str, Any] = await get_regime(session, None, "1h")
                    await engine.handle("regimes", result)
            except Exception:
                logger.exception("regime sweep failed")
            await asyncio.sleep(REGIME_SWEEP_SECONDS)

    sweep_task = asyncio.create_task(regime_sweep(), name="regime-sweep")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                await engine.handle(str(message["channel"]), json.loads(message["data"]))
            except Exception:
                logger.exception("alert evaluation failed")
    finally:
        sweep_task.cancel()
