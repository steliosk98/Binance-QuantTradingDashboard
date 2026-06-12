"""Pairs trading: target logic, backtest profitability on synthetic
cointegrated data, API integration, paper two-leg evaluation."""

import uuid
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.pairs import pairs_target_positions, run_pairs_backtest
from app.backtest.strategies import STRATEGIES
from app.models import PaperInstance, PaperOrder
from app.paper.engine import default_state, evaluate_instance
from app.paper.executor import SimExecutor

RNG = np.random.default_rng(21)


def make_pair(n: int = 1500) -> tuple[pd.DataFrame, pd.DataFrame]:
    """B is a random walk; A = 2*B + strongly mean-reverting noise."""
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    b = 200 + np.cumsum(RNG.normal(0, 2.0, n))
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.9 * noise[i - 1] + RNG.normal(0, 2.5)
    a = 2 * b + noise + 50

    def df(closes: np.ndarray) -> pd.DataFrame:
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

    return df(a), df(b)


def test_target_positions_enter_and_exit() -> None:
    df_a, df_b = make_pair()
    pos, beta, z = pairs_target_positions(df_a["close"], df_b["close"], 100, 2.0, 0.5)
    assert set(pos.unique()) <= {-1.0, 0.0, 1.0}
    assert (pos != 0).sum() > 10  # actually trades
    # Hedge ratio should recover ~2 (median over rolling windows)
    assert float(beta.dropna().median()) == pytest.approx(2.0, abs=0.3)
    # Entries only occur at |z| >= entry threshold
    entries = pos[(pos != 0) & (pos.shift(1) == 0)]
    assert (z.loc[entries.index].abs() >= 2.0).all()


def test_pairs_backtest_profits_on_cointegrated_pair() -> None:
    df_a, df_b = make_pair()
    result, z = run_pairs_backtest(
        df_a, df_b, "1h", {"lookback": 100, "entry_z": 2.0, "exit_z": 0.5}, 5, 2
    )
    assert result.metrics["n_trades"] > 5
    assert result.metrics["total_return"] > 0  # textbook stat-arb conditions
    assert result.metrics["sharpe"] is not None and result.metrics["sharpe"] > 1
    assert len(z) == len(result.equity)


def test_pairs_backtest_deterministic() -> None:
    df_a, df_b = make_pair()
    p = {"lookback": 100, "entry_z": 2.0, "exit_z": 0.5}
    r1, _ = run_pairs_backtest(df_a, df_b, "1h", p)
    r2, _ = run_pairs_backtest(df_a, df_b, "1h", p)
    pd.testing.assert_series_equal(r1.equity, r2.equity)


def test_strategy_registered_with_needs_pair() -> None:
    spec = STRATEGIES["pairs_trading"]
    assert spec.needs_pair is True
    with pytest.raises(NotImplementedError):
        spec.generate(pd.DataFrame({"close": [1.0]}), {})


@pytest.mark.asyncio
async def test_paper_pairs_two_leg_orders(db_session: AsyncSession) -> None:
    from app.ingestion.upserts import upsert_candles
    from tests.test_backtests_api import synth_klines

    base = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    await upsert_candles(db_session, "ETHUSDT", "1h", synth_klines(base, 400, seed=7))
    await db_session.commit()

    # Spike the A-leg so the spread z-score demands a short-spread position.
    df_a, df_b = make_pair(400)
    df_a.iloc[-1, df_a.columns.get_loc("close")] = float(df_a["close"].iloc[-1]) * 3.0

    instance = PaperInstance(
        id=str(uuid.uuid4()),
        name="pairs-test",
        strategy="pairs_trading",
        symbol="BTCUSDT",
        interval="1h",
        qty_usd=10_000,
        status="running",
        params_json={"lookback": 100, "entry_z": 1.0, "exit_z": 0.2, "symbol_b": "ETHUSDT"},
        guards_json={"max_position_usd": 20_000, "max_daily_loss_usd": 1e9},
        state_json=default_state(),
    )
    db_session.add(instance)
    await db_session.commit()

    # evaluate_instance loads df_b from the DB (ETHUSDT seeded above); pass
    # our synthetic A-leg frame directly.
    await evaluate_instance(db_session, instance, df_a, SimExecutor())
    orders = (await db_session.execute(select(PaperOrder))).scalars().all()
    # Both legs traded (sides depend on the estimated hedge ratio's sign)
    assert len(orders) == 2
    assert {o.symbol for o in orders} == {"BTCUSDT", "ETHUSDT"}
    a_leg = next(o for o in orders if o.symbol == "BTCUSDT")
    assert a_leg.side == "SELL"  # short the spiked leg
    assert instance.state_json["position_qty"] != 0.0
    assert instance.state_json["qty_b"] != 0.0
