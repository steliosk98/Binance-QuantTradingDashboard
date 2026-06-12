"""CSV export endpoints for research workflows (V3)."""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.ingestion.binance_client import INTERVAL_MS
from app.models import Backtest, Candle

router = APIRouter(prefix="/api/v1/export", tags=["export"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _csv(headers: list[str], rows: list[list[object]], filename: str) -> PlainTextResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/candles.csv")
async def export_candles(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    limit: Annotated[int, Query(ge=1, le=20_000)] = 5000,
) -> PlainTextResponse:
    if interval not in INTERVAL_MS:
        raise HTTPException(status_code=422, detail="unsupported interval")
    result = await db.execute(
        select(Candle)
        .where(Candle.symbol == symbol.upper(), Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = [
        [
            c.open_time.isoformat(),
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.quote_volume,
            c.trades,
        ]
        for c in reversed(list(result.scalars()))
    ]
    return _csv(
        ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "trades"],
        rows,
        f"{symbol.upper()}_{interval}_candles.csv",
    )


@router.get("/backtests/{backtest_id}/trades.csv")
async def export_backtest_trades(backtest_id: str, db: DbSession) -> PlainTextResponse:
    row = await db.get(Backtest, backtest_id)
    if row is None or not row.trades_json:
        raise HTTPException(status_code=404, detail="backtest or trades not found")
    headers = [
        "entry_time",
        "exit_time",
        "direction",
        "entry_price",
        "exit_price",
        "pnl_pct",
        "bars",
    ]
    rows = [[t.get(h) for h in headers] for t in row.trades_json]
    return _csv(headers, rows, f"backtest_{backtest_id[:8]}_trades.csv")


@router.get("/backtests/{backtest_id}/equity.csv")
async def export_backtest_equity(backtest_id: str, db: DbSession) -> PlainTextResponse:
    row = await db.get(Backtest, backtest_id)
    if row is None or not row.equity_json:
        raise HTTPException(status_code=404, detail="backtest or equity not found")
    return _csv(
        ["time", "equity", "drawdown"],
        [list(p) for p in row.equity_json],
        f"backtest_{backtest_id[:8]}_equity.csv",
    )
