"""Per-instance evaluation: closed candle → strategy signal → guarded order.

State (persisted in `paper_instances.state_json` so restarts resume cleanly):
    position_qty, avg_entry, realized_pnl, day, day_start_equity, halted_today
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.strategies import STRATEGIES
from app.models import PaperEquity, PaperInstance, PaperOrder
from app.paper.executor import Executor

logger = logging.getLogger(__name__)

DEFAULT_GUARDS = {"max_position_usd": 10_000.0, "max_daily_loss_usd": 500.0}


def default_state() -> dict[str, Any]:
    return {
        "position_qty": 0.0,
        "avg_entry": 0.0,
        "realized_pnl": 0.0,
        "day": None,
        "day_start_equity": None,
        "halted_today": False,
    }


def equity_usd(instance: PaperInstance, state: dict[str, Any], price: float) -> float:
    unrealized = (
        state["position_qty"] * (price - state["avg_entry"]) if state["position_qty"] else 0.0
    )
    return float(instance.qty_usd + state["realized_pnl"] + unrealized)


def clamp_target_qty(
    target_pos: float, price: float, qty_usd: float, max_position_usd: float
) -> float:
    """Desired signed quantity, clamped by the max-position guard."""
    capped_usd = min(qty_usd, max_position_usd)
    return target_pos * capped_usd / price


async def evaluate_instance(
    session: AsyncSession,
    instance: PaperInstance,
    df: pd.DataFrame,
    executor: Executor,
) -> PaperOrder | None:
    """Evaluate one closed candle for one instance. Returns the order if any."""
    if instance.status != "running":
        return None
    spec = STRATEGIES[instance.strategy]
    params = {
        p.name: float((instance.params_json or {}).get(p.name, p.default)) for p in spec.params
    }
    state = {**default_state(), **(instance.state_json or {})}
    guards = {**DEFAULT_GUARDS, **(instance.guards_json or {})}
    price = float(df["close"].iloc[-1])
    now = datetime.now(UTC)

    # Daily-loss guard bookkeeping (UTC day boundaries).
    today = now.date().isoformat()
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = equity_usd(instance, state, price)
        state["halted_today"] = False

    current_equity = equity_usd(instance, state, price)
    if (
        not state["halted_today"]
        and state["day_start_equity"] is not None
        and state["day_start_equity"] - current_equity >= guards["max_daily_loss_usd"]
    ):
        state["halted_today"] = True
        logger.warning("instance %s halted: daily loss guard tripped", instance.id)

    order: PaperOrder | None = None
    if not state["halted_today"]:
        target_pos = float(spec.generate(df, params).iloc[-1])
        if executor.name == "testnet":
            target_pos = max(target_pos, 0.0)  # spot testnet: long-only
        target_qty = clamp_target_qty(
            target_pos, price, instance.qty_usd, guards["max_position_usd"]
        )
        delta = target_qty - state["position_qty"]
        sized_usd = min(instance.qty_usd, guards["max_position_usd"])
        min_qty = (sized_usd * 0.01) / price  # ignore dust rebalances
        if abs(delta) > min_qty:
            side = "BUY" if delta > 0 else "SELL"
            fill = await executor.market_order(instance.symbol, side, abs(delta), price)
            # Position accounting
            old_qty = state["position_qty"]
            new_qty = old_qty + (fill.qty if side == "BUY" else -fill.qty)
            if old_qty * new_qty < 0:  # crossed through zero
                state["realized_pnl"] += old_qty * (fill.price - state["avg_entry"])
                state["avg_entry"] = fill.price
            elif abs(new_qty) > abs(old_qty):  # adding
                total = abs(old_qty) + fill.qty
                state["avg_entry"] = (
                    (abs(old_qty) * state["avg_entry"] + fill.qty * fill.price) / total
                    if total
                    else fill.price
                )
            else:  # reducing
                closed = abs(old_qty) - abs(new_qty)
                sign = 1 if old_qty > 0 else -1
                state["realized_pnl"] += sign * closed * (fill.price - state["avg_entry"])
                if new_qty == 0:
                    state["avg_entry"] = 0.0
            state["position_qty"] = new_qty
            order = PaperOrder(
                id=str(uuid.uuid4()),
                instance_id=instance.id,
                ts=now,
                symbol=instance.symbol,
                side=side,
                type="MARKET",
                qty=fill.qty,
                price=fill.price,
                status="filled",
                signal=f"target={target_pos:+.0f} pos {old_qty:.6f}→{new_qty:.6f}",
                testnet_order_id=fill.testnet_order_id,
            )
            session.add(order)

    instance.state_json = state
    session.add(
        PaperEquity(
            instance_id=instance.id,
            ts=now,
            equity_usd=equity_usd(instance, state, price),
            position_qty=state["position_qty"],
            price=price,
        )
    )
    await session.commit()
    return order
