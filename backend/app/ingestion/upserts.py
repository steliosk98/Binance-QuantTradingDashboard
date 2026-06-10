"""Idempotent upsert helpers for market data (spec ground rule 7)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.binance_client import Kline
from app.models import Candle, FundingRate, LongShortRatio, OpenInterest


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


async def upsert_candles(
    session: AsyncSession, symbol: str, interval: str, klines: list[Kline]
) -> int:
    if not klines:
        return 0
    rows = [
        {
            "symbol": symbol,
            "interval": interval,
            "open_time": _ms_to_dt(k.open_time),
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
            "quote_volume": k.quote_volume,
            "trades": k.trades,
            "taker_buy_volume": k.taker_buy_volume,
        }
        for k in klines
    ]
    stmt = insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "interval", "open_time"],
        set_={
            col: getattr(stmt.excluded, col)
            for col in (
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trades",
                "taker_buy_volume",
            )
        },
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_funding_rates(
    session: AsyncSession, symbol: str, entries: list[dict[str, Any]]
) -> int:
    if not entries:
        return 0
    rows = [
        {
            "symbol": symbol,
            "funding_time": _ms_to_dt(int(e["fundingTime"])),
            "rate": float(e["fundingRate"]),
        }
        for e in entries
    ]
    stmt = insert(FundingRate).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "funding_time"],
        set_={"rate": stmt.excluded.rate},
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_open_interest(
    session: AsyncSession, symbol: str, entries: list[dict[str, Any]]
) -> int:
    if not entries:
        return 0
    rows = [
        {
            "symbol": symbol,
            "ts": _ms_to_dt(int(e["timestamp"])),
            "oi": float(e["sumOpenInterest"]),
            "oi_value": float(e["sumOpenInterestValue"]),
        }
        for e in entries
    ]
    stmt = insert(OpenInterest).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "ts"],
        set_={"oi": stmt.excluded.oi, "oi_value": stmt.excluded.oi_value},
    )
    await session.execute(stmt)
    return len(rows)


async def upsert_long_short_ratio(
    session: AsyncSession, symbol: str, entries: list[dict[str, Any]]
) -> int:
    if not entries:
        return 0
    rows = [
        {
            "symbol": symbol,
            "ts": _ms_to_dt(int(e["timestamp"])),
            "ratio": float(e["longShortRatio"]),
            "long_pct": float(e["longAccount"]),
            "short_pct": float(e["shortAccount"]),
        }
        for e in entries
    ]
    stmt = insert(LongShortRatio).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "ts"],
        set_={
            "ratio": stmt.excluded.ratio,
            "long_pct": stmt.excluded.long_pct,
            "short_pct": stmt.excluded.short_pct,
        },
    )
    await session.execute(stmt)
    return len(rows)
