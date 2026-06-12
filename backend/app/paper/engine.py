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


async def evaluate_pairs_instance(
    session: "AsyncSession",
    instance: "PaperInstance",
    df: "pd.DataFrame",
    executor: "Executor",
) -> "PaperOrder | None":
    """Dollar-neutral two-leg pairs evaluation (sim fills only — spot testnet
    cannot short the hedge leg)."""
    from app.analytics.data import load_candles_df
    from app.backtest.pairs import pairs_target_positions

    if executor.name == "testnet":
        logger.warning("pairs instance %s requires sim mode; skipping", instance.id)
        return None
    spec = STRATEGIES[instance.strategy]
    raw_params = instance.params_json or {}
    symbol_b = str(raw_params.get("symbol_b", "")).upper()
    if not symbol_b:
        logger.warning("pairs instance %s missing symbol_b", instance.id)
        return None
    params = {p.name: float(raw_params.get(p.name, p.default)) for p in spec.params}
    df_b = await load_candles_df(session, symbol_b, instance.interval, len(df))
    if len(df_b) < 100:
        return None

    close_a = df["close"]
    close_b = df_b["close"].reindex(close_a.index).ffill()
    aligned = pd.concat([close_a, close_b], axis=1, keys=["a", "b"]).dropna()
    target_series, beta, _z = pairs_target_positions(
        aligned["a"], aligned["b"], int(params["lookback"]), params["entry_z"], params["exit_z"]
    )
    target = float(target_series.iloc[-1])
    beta_now = float(beta.iloc[-1]) if not beta.empty else 1.0
    pa, pb = float(aligned["a"].iloc[-1]), float(aligned["b"].iloc[-1])
    now = datetime.now(UTC)

    state = {**default_state(), "qty_b": 0.0, "avg_entry_b": 0.0, **(instance.state_json or {})}
    guards = {**DEFAULT_GUARDS, **(instance.guards_json or {})}
    sized = min(instance.qty_usd, guards["max_position_usd"]) / 2  # per leg
    target_qty_a = target * sized / pa
    target_qty_b = -target * beta_now * sized / (pb * max(abs(beta_now), 1e-9))

    order: PaperOrder | None = None
    for leg, symbol, price, key_q, key_e, tq in (
        ("a", instance.symbol, pa, "position_qty", "avg_entry", target_qty_a),
        ("b", symbol_b, pb, "qty_b", "avg_entry_b", target_qty_b),
    ):
        delta = tq - state[key_q]
        if abs(delta) * price < instance.qty_usd * 0.01:
            continue
        side = "BUY" if delta > 0 else "SELL"
        fill = await executor.market_order(symbol, side, abs(delta), price)
        old = state[key_q]
        new = old + (fill.qty if side == "BUY" else -fill.qty)
        if old * new < 0:
            state["realized_pnl"] += old * (fill.price - state[key_e])
            state[key_e] = fill.price
        elif abs(new) > abs(old):
            total = abs(old) + fill.qty
            state[key_e] = (
                (abs(old) * state[key_e] + fill.qty * fill.price) / total if total else fill.price
            )
        else:
            closed = abs(old) - abs(new)
            sign = 1 if old > 0 else -1
            state["realized_pnl"] += sign * closed * (fill.price - state[key_e])
            if new == 0:
                state[key_e] = 0.0
        state[key_q] = new
        order = PaperOrder(
            id=str(uuid.uuid4()),
            instance_id=instance.id,
            ts=now,
            symbol=symbol,
            side=side,
            type="MARKET",
            qty=fill.qty,
            price=fill.price,
            status="filled",
            signal=f"pairs target={target:+.0f} leg={leg}",
            testnet_order_id=fill.testnet_order_id,
        )
        session.add(order)

    unreal_a = state["position_qty"] * (pa - state["avg_entry"]) if state["position_qty"] else 0.0
    unreal_b = state["qty_b"] * (pb - state["avg_entry_b"]) if state["qty_b"] else 0.0
    equity = float(instance.qty_usd + state["realized_pnl"] + unreal_a + unreal_b)
    instance.state_json = state
    session.add(
        PaperEquity(
            instance_id=instance.id,
            ts=now,
            equity_usd=equity,
            position_qty=state["position_qty"],
            price=pa,
        )
    )
    await session.commit()
    return order


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
    if spec.needs_pair:
        return await evaluate_pairs_instance(session, instance, df, executor)
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
