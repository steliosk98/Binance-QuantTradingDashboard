"""Paper trading: sim fills, guards, signal→order pipeline, restart recovery."""

import uuid
from datetime import UTC, datetime

import httpx
import numpy as np
import pandas as pd
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperEquity, PaperInstance, PaperOrder
from app.paper.engine import clamp_target_qty, default_state, evaluate_instance
from app.paper.executor import SimExecutor, TestnetExecutor


def make_df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="min", tz="UTC")
    arr = np.asarray(closes, dtype=float)
    opens = np.roll(arr, 1)
    opens[0] = arr[0]
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, arr) * 1.001,
            "low": np.minimum(opens, arr) * 0.999,
            "close": arr,
            "volume": 1.0,
        },
        index=idx,
    )


def make_instance(
    strategy: str = "zscore_mr",
    params: dict | None = None,
    qty_usd: float = 1000.0,
    guards: dict | None = None,
    state: dict | None = None,
    status: str = "running",
) -> PaperInstance:
    return PaperInstance(
        id=str(uuid.uuid4()),
        name="test-instance",
        strategy=strategy,
        symbol="BTCUSDT",
        interval="1m",
        qty_usd=qty_usd,
        status=status,
        params_json=params or {"lookback": 50, "entry_z": 2.0, "exit_z": 0.5},
        guards_json=guards or {"max_position_usd": 10_000.0, "max_daily_loss_usd": 500.0},
        state_json=state or default_state(),
    )


@pytest.mark.asyncio
async def test_sim_executor_applies_slippage() -> None:
    ex = SimExecutor(slippage_bps=10)
    buy = await ex.market_order("BTCUSDT", "BUY", 0.5, 100.0)
    sell = await ex.market_order("BTCUSDT", "SELL", 0.5, 100.0)
    assert buy.price == pytest.approx(100.10)
    assert sell.price == pytest.approx(99.90)
    assert buy.simulated and buy.qty == 0.5


def test_clamp_target_qty_guard() -> None:
    # qty_usd 50k but guard caps at 10k → 10k/100 = 100 units
    assert clamp_target_qty(1.0, 100.0, 50_000.0, 10_000.0) == pytest.approx(100.0)
    assert clamp_target_qty(-1.0, 100.0, 5_000.0, 10_000.0) == pytest.approx(-50.0)
    assert clamp_target_qty(0.0, 100.0, 5_000.0, 10_000.0) == 0.0


def spike_df() -> pd.DataFrame:
    """A series whose final bar is a huge upward spike → z-score short."""
    rng = np.random.default_rng(8)
    closes = list(100 + rng.normal(0, 0.3, 200))
    closes.append(115.0)
    return make_df(closes)


@pytest.mark.asyncio
async def test_signal_to_order_pipeline(db_session: AsyncSession) -> None:
    instance = make_instance()
    db_session.add(instance)
    await db_session.commit()

    order = await evaluate_instance(db_session, instance, spike_df(), SimExecutor())
    assert order is not None
    assert order.side == "SELL"  # short the spike
    assert order.qty > 0
    # State updated + persisted
    assert instance.state_json["position_qty"] < 0
    rows = (await db_session.execute(select(PaperOrder))).scalars().all()
    assert len(rows) == 1
    eq = (await db_session.execute(select(PaperEquity))).scalars().all()
    assert len(eq) == 1 and eq[0].equity_usd == pytest.approx(1000.0, rel=0.01)


@pytest.mark.asyncio
async def test_stopped_instance_is_skipped(db_session: AsyncSession) -> None:
    instance = make_instance(status="stopped")
    db_session.add(instance)
    await db_session.commit()
    order = await evaluate_instance(db_session, instance, spike_df(), SimExecutor())
    assert order is None
    assert (await db_session.execute(select(PaperOrder))).scalars().all() == []


@pytest.mark.asyncio
async def test_max_position_guard_caps_order(db_session: AsyncSession) -> None:
    instance = make_instance(
        qty_usd=100_000.0, guards={"max_position_usd": 1_000.0, "max_daily_loss_usd": 1e9}
    )
    db_session.add(instance)
    await db_session.commit()
    df = spike_df()
    price = float(df["close"].iloc[-1])
    order = await evaluate_instance(db_session, instance, df, SimExecutor())
    assert order is not None
    assert order.qty * price <= 1_100.0  # capped at ~$1k (small slippage tolerance)


@pytest.mark.asyncio
async def test_daily_loss_guard_halts(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date().isoformat()
    # Position with a large unrealized loss vs day_start_equity
    state = {
        **default_state(),
        "position_qty": 10.0,
        "avg_entry": 200.0,  # current price ~100 → -$1000 unrealized
        "day": today,
        "day_start_equity": 1000.0,
    }
    instance = make_instance(
        guards={"max_position_usd": 1e9, "max_daily_loss_usd": 500.0}, state=state
    )
    db_session.add(instance)
    await db_session.commit()
    order = await evaluate_instance(db_session, instance, spike_df(), SimExecutor())
    assert order is None  # halted before trading
    assert instance.state_json["halted_today"] is True


@pytest.mark.asyncio
async def test_restart_recovery_resumes_state(db_session: AsyncSession) -> None:
    instance = make_instance()
    db_session.add(instance)
    await db_session.commit()
    await evaluate_instance(db_session, instance, spike_df(), SimExecutor())
    saved_state = dict(instance.state_json)
    instance_id = instance.id

    # Simulate a fresh process: load the instance from the DB anew.
    db_session.expunge_all()
    reloaded = await db_session.get(PaperInstance, instance_id)
    assert reloaded is not None
    assert reloaded.state_json == saved_state
    assert reloaded.state_json["position_qty"] != 0.0

    # Evaluating again with an unchanged signal makes no new order (idempotent
    # resume), proving the position carried over rather than re-entering.
    order = await evaluate_instance(db_session, reloaded, spike_df(), SimExecutor())
    assert order is None


@pytest.mark.asyncio
@respx.mock
async def test_testnet_executor_signs_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def record(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "orderId": 12345,
                "transactTime": 1700000000000,
                "fills": [
                    {"price": "100.0", "qty": "0.3"},
                    {"price": "101.0", "qty": "0.2"},
                ],
            },
        )

    respx.get("https://testnet.binance.vision/api/v3/time").respond(
        json={"serverTime": 1700000000000}
    )
    respx.post("https://testnet.binance.vision/api/v3/order").mock(side_effect=record)

    ex = TestnetExecutor("test-key", "test-secret", http=httpx.AsyncClient())
    await ex.sync_time()
    fill = await ex.market_order("BTCUSDT", "BUY", 0.5, 100.0)

    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["type"] == "MARKET"
    assert "signature" in captured["params"]
    assert captured["headers"]["x-mbx-apikey"] == "test-key"
    assert fill.testnet_order_id == "12345"
    assert fill.qty == pytest.approx(0.5)
    assert fill.price == pytest.approx((100.0 * 0.3 + 101.0 * 0.2) / 0.5)
    assert fill.simulated is False
