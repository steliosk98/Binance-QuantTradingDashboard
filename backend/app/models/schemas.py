"""Pydantic response schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CandleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int
    taker_buy_volume: float


class CandlesResponse(BaseModel):
    symbol: str
    interval: str
    candles: list[CandleOut]


class SymbolsResponse(BaseModel):
    watchlist: list[str]
    available: list[str]


class FundingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    funding_time: datetime
    rate: float


class FundingResponse(BaseModel):
    symbol: str
    entries: list[FundingOut]


class OpenInterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    oi: float
    oi_value: float


class OpenInterestResponse(BaseModel):
    symbol: str
    entries: list[OpenInterestOut]


class TickerSummary(BaseModel):
    symbol: str
    last_price: float | None
    change_24h_pct: float | None
    volume_24h: float | None
    quote_volume_24h: float | None
    funding_rate: float | None
    oi_change_24h_pct: float | None


class TickerSummaryResponse(BaseModel):
    tickers: list[TickerSummary]
