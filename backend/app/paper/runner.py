"""Paper trading runner process: python -m app.paper.runner

Subscribes to closed candles on Redis pub/sub and evaluates every running
instance for that (symbol, interval). Instances resume from DB state on
restart. The kill switch is just `status != "running"` in the DB — checked
on every evaluation cycle, so a stop takes effect within one cycle.

V3: instances with `autopilot` enabled are periodically re-optimized via
walk-forward grid search with an out-of-sample adoption guard.
"""

import asyncio
import json
import logging
import time
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.data import load_candles_df
from app.core.redis import get_redis
from app.db.session import get_session_factory
from app.models import PaperInstance
from app.paper.autopilot import retrain
from app.paper.engine import evaluate_instance
from app.paper.executor import build_executor

logger = logging.getLogger("paper")

LOOKBACK_BARS = 600


async def maybe_autopilot(session: AsyncSession, instance: PaperInstance, df: pd.DataFrame) -> None:
    """Re-optimize params when the instance opted in and the interval elapsed."""
    from app.backtest.strategies import STRATEGIES

    guards = instance.guards_json or {}
    if not guards.get("autopilot"):
        return
    state = dict(instance.state_json or {})
    interval_s = float(guards.get("retrain_hours", 24)) * 3600
    if time.time() - float(state.get("last_retrain_ts", 0)) < interval_s:
        return
    spec = STRATEGIES[instance.strategy]
    raw = instance.params_json or {}
    current = {p.name: float(raw.get(p.name, p.default)) for p in spec.params}
    outcome = await asyncio.to_thread(retrain, df, spec, current, instance.interval)
    state["last_retrain_ts"] = time.time()
    if outcome is not None:
        history = list(state.get("retrain_history", []))[-19:]
        history.append(outcome)
        state["retrain_history"] = history
        instance.params_json = {**raw, **outcome["params"]}
        logger.info(
            "[%s] autopilot adopted %s (val sharpe %.2f > %.2f)",
            instance.name,
            outcome["params"],
            outcome["val_sharpe"],
            outcome["previous_val_sharpe"],
        )
    instance.state_json = state
    await session.commit()


async def evaluate_for_candle(symbol: str, interval: str) -> None:
    factory = get_session_factory()
    executor = build_executor()
    async with factory() as session:
        result = await session.execute(
            select(PaperInstance).where(
                PaperInstance.symbol == symbol,
                PaperInstance.interval == interval,
                PaperInstance.status == "running",
            )
        )
        instances = list(result.scalars())
        if not instances:
            return
        df = await load_candles_df(session, symbol, interval, LOOKBACK_BARS)
        if len(df) < 100:
            logger.warning("not enough candles for %s %s", symbol, interval)
            return
        for instance in instances:
            try:
                await maybe_autopilot(session, instance, df)
                order = await evaluate_instance(session, instance, df, executor)
                if order is not None:
                    logger.info(
                        "[%s] %s %s %.6f @ %.2f (%s)",
                        instance.name,
                        order.side,
                        order.symbol,
                        order.qty,
                        order.price,
                        order.signal,
                    )
            except Exception:
                logger.exception("evaluation failed for instance %s", instance.id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.psubscribe("candles:*")
    executor = build_executor()
    logger.info("Paper runner started (executor=%s)", executor.name)
    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        try:
            data: dict[str, Any] = json.loads(message["data"])
            if not data.get("closed"):
                continue
            await evaluate_for_candle(str(data["symbol"]), str(data["interval"]))
        except Exception:
            logger.exception("failed handling candle message")


if __name__ == "__main__":
    asyncio.run(main())
