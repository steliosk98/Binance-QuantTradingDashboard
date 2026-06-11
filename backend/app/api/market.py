"""Market data REST endpoints (spec Stage 2).

Every list endpoint is capped (ground rule: no unbounded result sets).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.ingestion.binance_client import INTERVAL_MS
from app.models import Candle, FundingRate, OpenInterest
from app.models.schemas import (
    CandleOut,
    CandlesResponse,
    FundingOut,
    FundingResponse,
    OpenInterestOut,
    OpenInterestResponse,
    SymbolsResponse,
    TickerSummary,
    TickerSummaryResponse,
)

router = APIRouter(prefix="/api/v1", tags=["market"])

MAX_CANDLES = 1000
MAX_ENTRIES = 1000

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _validate_interval(interval: str) -> None:
    if interval not in INTERVAL_MS:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported interval {interval!r}; one of {sorted(INTERVAL_MS)}",
        )


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_CANDLES)] = 500,
) -> CandlesResponse:
    """Candles ordered ascending; paginate backwards with ``end`` or forwards with ``start``."""
    _validate_interval(interval)
    symbol = symbol.upper()
    query = select(Candle).where(Candle.symbol == symbol, Candle.interval == interval)
    if start is not None:
        query = query.where(Candle.open_time >= start)
    if end is not None:
        query = query.where(Candle.open_time <= end)
    if start is not None and end is None:
        # Forward pagination: oldest first within window.
        query = query.order_by(Candle.open_time.asc()).limit(limit)
        rows = list((await db.execute(query)).scalars())
    else:
        # Default: most recent `limit` candles, returned ascending.
        query = query.order_by(Candle.open_time.desc()).limit(limit)
        rows = list(reversed(list((await db.execute(query)).scalars())))
    return CandlesResponse(
        symbol=symbol,
        interval=interval,
        candles=[CandleOut.model_validate(r) for r in rows],
    )


@router.get("/symbols", response_model=SymbolsResponse)
async def get_symbols(db: DbSession) -> SymbolsResponse:
    result = await db.execute(select(Candle.symbol).distinct().order_by(Candle.symbol))
    available = [row[0] for row in result]
    return SymbolsResponse(watchlist=get_settings().watchlist_symbols, available=available)


@router.get("/funding", response_model=FundingResponse)
async def get_funding(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ENTRIES)] = 500,
) -> FundingResponse:
    symbol = symbol.upper()
    query = select(FundingRate).where(FundingRate.symbol == symbol)
    if start is not None:
        query = query.where(FundingRate.funding_time >= start)
    if end is not None:
        query = query.where(FundingRate.funding_time <= end)
    query = query.order_by(FundingRate.funding_time.desc()).limit(limit)
    rows = list(reversed(list((await db.execute(query)).scalars())))
    return FundingResponse(symbol=symbol, entries=[FundingOut.model_validate(r) for r in rows])


@router.get("/open-interest", response_model=OpenInterestResponse)
async def get_open_interest(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ENTRIES)] = 500,
) -> OpenInterestResponse:
    symbol = symbol.upper()
    query = select(OpenInterest).where(OpenInterest.symbol == symbol)
    if start is not None:
        query = query.where(OpenInterest.ts >= start)
    if end is not None:
        query = query.where(OpenInterest.ts <= end)
    query = query.order_by(OpenInterest.ts.desc()).limit(limit)
    rows = list(reversed(list((await db.execute(query)).scalars())))
    return OpenInterestResponse(
        symbol=symbol, entries=[OpenInterestOut.model_validate(r) for r in rows]
    )


@router.get("/long-short")
async def get_long_short(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    limit: Annotated[int, Query(ge=1, le=MAX_ENTRIES)] = 500,
) -> dict[str, object]:
    from app.models import LongShortRatio

    symbol = symbol.upper()
    query = (
        select(LongShortRatio)
        .where(LongShortRatio.symbol == symbol)
        .order_by(LongShortRatio.ts.desc())
        .limit(limit)
    )
    rows = list(reversed(list((await db.execute(query)).scalars())))
    return {
        "symbol": symbol,
        "entries": [
            {
                "ts": r.ts.isoformat(),
                "ratio": r.ratio,
                "long_pct": r.long_pct,
                "short_pct": r.short_pct,
            }
            for r in rows
        ],
    }


async def _ticker_for_symbol(db: AsyncSession, symbol: str, now: datetime) -> TickerSummary:
    day_ago = now - timedelta(hours=24)
    result = await db.execute(
        select(Candle)
        .where(Candle.symbol == symbol, Candle.interval == "1h", Candle.open_time >= day_ago)
        .order_by(Candle.open_time.asc())
    )
    candles = list(result.scalars())
    last_price = candles[-1].close if candles else None
    change = None
    if len(candles) >= 2 and candles[0].open:
        change = (candles[-1].close - candles[0].open) / candles[0].open * 100
    volume = sum(c.volume for c in candles) if candles else None
    quote_volume = sum(c.quote_volume for c in candles) if candles else None

    funding_result = await db.execute(
        select(FundingRate.rate)
        .where(FundingRate.symbol == symbol)
        .order_by(FundingRate.funding_time.desc())
        .limit(1)
    )
    funding = funding_result.scalar_one_or_none()

    oi_result = await db.execute(
        select(OpenInterest)
        .where(OpenInterest.symbol == symbol, OpenInterest.ts >= day_ago)
        .order_by(OpenInterest.ts.asc())
    )
    oi_rows = list(oi_result.scalars())
    oi_change = None
    if len(oi_rows) >= 2 and oi_rows[0].oi:
        oi_change = (oi_rows[-1].oi - oi_rows[0].oi) / oi_rows[0].oi * 100

    return TickerSummary(
        symbol=symbol,
        last_price=last_price,
        change_24h_pct=change,
        volume_24h=volume,
        quote_volume_24h=quote_volume,
        funding_rate=funding,
        oi_change_24h_pct=oi_change,
    )


@router.get("/ticker-summary", response_model=TickerSummaryResponse)
async def get_ticker_summary(db: DbSession) -> TickerSummaryResponse:
    now = datetime.now(UTC)
    symbols = get_settings().watchlist_symbols
    tickers = [await _ticker_for_symbol(db, s, now) for s in symbols]
    return TickerSummaryResponse(tickers=tickers)
