"""Load candles from the DB into pandas frames for analytics."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candle


async def load_candles_df(
    session: AsyncSession, symbol: str, interval: str, limit: int = 2000
) -> pd.DataFrame:
    """Most recent `limit` candles as a DataFrame indexed by open_time (asc)."""
    result = await session.execute(
        select(
            Candle.open_time,
            Candle.open,
            Candle.high,
            Candle.low,
            Candle.close,
            Candle.volume,
        )
        .where(Candle.symbol == symbol, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    rows = result.all()
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
    df = df.iloc[::-1].set_index("open_time")
    return df


async def load_close_matrix(
    session: AsyncSession, symbols: list[str], interval: str = "1d", limit: int = 400
) -> pd.DataFrame:
    """Aligned close prices for multiple symbols (columns = symbols)."""
    frames: dict[str, pd.Series] = {}
    for symbol in symbols:
        df = await load_candles_df(session, symbol, interval, limit)
        if not df.empty:
            frames[symbol] = df["close"]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).dropna(how="all")
