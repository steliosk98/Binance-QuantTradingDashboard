from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Candle(Base):
    __tablename__ = "candles"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(4), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    quote_volume: Mapped[float] = mapped_column(Float)
    trades: Mapped[int] = mapped_column(BigInteger)
    taker_buy_volume: Mapped[float] = mapped_column(Float)


class FundingRate(Base):
    __tablename__ = "funding_rates"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    funding_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    rate: Mapped[float] = mapped_column(Float)


class OpenInterest(Base):
    __tablename__ = "open_interest"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    oi: Mapped[float] = mapped_column(Float)
    oi_value: Mapped[float] = mapped_column(Float)


class Liquidation(Base):
    __tablename__ = "liquidations"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    side: Mapped[str] = mapped_column(String(4), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    value_usdt: Mapped[float] = mapped_column(Float)


class LongShortRatio(Base):
    __tablename__ = "long_short_ratio"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    ratio: Mapped[float] = mapped_column(Float)
    long_pct: Mapped[float] = mapped_column(Float)
    short_pct: Mapped[float] = mapped_column(Float)
