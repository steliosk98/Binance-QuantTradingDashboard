"""Autopilot retraining: adopts better params, rejects worse, records history."""

import uuid

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.strategies import STRATEGIES
from app.models import PaperInstance
from app.paper.autopilot import retrain
from app.paper.engine import default_state
from app.paper.runner import maybe_autopilot

RNG = np.random.default_rng(33)


def trending_df(n: int = 1200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    closes = 100 * np.exp(np.cumsum(RNG.normal(0.001, 0.008, n)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.001,
            "low": np.minimum(opens, closes) * 0.999,
            "close": closes,
            "volume": 1.0,
        },
        index=idx,
    )


def test_retrain_adopts_better_params() -> None:
    df = trending_df()
    spec = STRATEGIES["sma_crossover"]
    # Deliberately terrible current params on a trending series: ultra-twitchy
    bad = {"fast": 5.0, "slow": 10.0}
    outcome = retrain(df, spec, bad, "1h")
    assert outcome is not None
    assert outcome["val_sharpe"] > outcome["previous_val_sharpe"]
    assert set(outcome["params"]) == {"fast", "slow"}


def test_retrain_keeps_current_when_not_beaten() -> None:
    df = trending_df()
    spec = STRATEGIES["sma_crossover"]
    # Run once to find the grid's best, then ask again with those params —
    # nothing in the grid can beat itself on validation.
    first = retrain(df, spec, {"fast": 5.0, "slow": 10.0}, "1h")
    assert first is not None
    again = retrain(df, spec, first["params"], "1h")
    assert again is None


def test_retrain_refuses_pairs_and_short_data() -> None:
    df = trending_df(100)
    assert retrain(df, STRATEGIES["sma_crossover"], {"fast": 10.0, "slow": 30.0}, "1h") is None
    assert retrain(trending_df(), STRATEGIES["pairs_trading"], {}, "1h") is None


@pytest.mark.asyncio
async def test_maybe_autopilot_updates_instance(db_session: AsyncSession) -> None:
    instance = PaperInstance(
        id=str(uuid.uuid4()),
        name="auto-test",
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1h",
        qty_usd=1000,
        status="running",
        params_json={"fast": 5, "slow": 10},
        guards_json={"autopilot": True, "retrain_hours": 24},
        state_json=default_state(),
    )
    db_session.add(instance)
    await db_session.commit()

    df = trending_df()
    await maybe_autopilot(db_session, instance, df)
    assert instance.state_json.get("last_retrain_ts", 0) > 0
    history = instance.state_json.get("retrain_history", [])
    assert len(history) == 1
    assert instance.params_json["fast"] == history[0]["params"]["fast"]

    # Within the interval → no second retrain
    before = instance.state_json["last_retrain_ts"]
    await maybe_autopilot(db_session, instance, df)
    assert instance.state_json["last_retrain_ts"] == before
    assert len(instance.state_json.get("retrain_history", [])) == 1


@pytest.mark.asyncio
async def test_maybe_autopilot_skipped_when_disabled(db_session: AsyncSession) -> None:
    instance = PaperInstance(
        id=str(uuid.uuid4()),
        name="manual",
        strategy="sma_crossover",
        symbol="BTCUSDT",
        interval="1h",
        qty_usd=1000,
        status="running",
        params_json={"fast": 5, "slow": 10},
        guards_json={},
        state_json=default_state(),
    )
    db_session.add(instance)
    await db_session.commit()
    await maybe_autopilot(db_session, instance, trending_df())
    assert "last_retrain_ts" not in (instance.state_json or {})
