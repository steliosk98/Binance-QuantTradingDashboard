"""Rate-limited async Binance REST client (public market data only).

All REST access to Binance goes through this module (spec ground rule 6).
Honors 429/418 with exponential backoff and the Retry-After header, retries
5xx, and throttles via the weight headers.
"""

import asyncio
import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx

from app.core.ratelimit import FUTURES_WEIGHT_LIMIT_1M, SPOT_WEIGHT_LIMIT_1M, WeightLimiter

logger = logging.getLogger(__name__)

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"

KLINES_MAX_LIMIT = 1000
FUNDING_MAX_LIMIT = 1000
FUTURES_DATA_MAX_LIMIT = 500

INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class BinanceAPIError(Exception):
    """Raised when a request fails after all retries."""


@dataclass(frozen=True)
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int
    taker_buy_volume: float

    @classmethod
    def from_row(cls, row: list[Any]) -> "Kline":
        return cls(
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
            quote_volume=float(row[7]),
            trades=int(row[8]),
            taker_buy_volume=float(row[9]),
        )


class BinanceClient:
    """Async client for Binance spot + USD-M futures public endpoints."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        spot_limiter: WeightLimiter | None = None,
        futures_limiter: WeightLimiter | None = None,
        max_retries: int = 5,
        base_backoff: float = 1.0,
    ) -> None:
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None
        self._spot_limiter = spot_limiter or WeightLimiter(SPOT_WEIGHT_LIMIT_1M)
        self._futures_limiter = futures_limiter or WeightLimiter(FUTURES_WEIGHT_LIMIT_1M)
        self._max_retries = max_retries
        self._base_backoff = base_backoff

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _get(self, base: str, path: str, params: dict[str, Any], weight: int) -> Any:
        limiter = self._spot_limiter if base == SPOT_BASE else self._futures_limiter
        url = f"{base}{path}"
        last_error: str = "unknown"
        for attempt in range(self._max_retries + 1):
            await limiter.acquire(weight)
            try:
                resp = await self._http.get(url, params=params)
            except httpx.TransportError as exc:
                last_error = f"transport error: {exc}"
                logger.warning("GET %s failed (%s), attempt %d", url, exc, attempt + 1)
                await asyncio.sleep(self._base_backoff * 2**attempt)
                continue
            limiter.update_from_headers(dict(resp.headers))
            if resp.status_code in (429, 418):
                retry_after = float(
                    resp.headers.get("Retry-After", self._base_backoff * 2**attempt)
                )
                last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "Rate limited (%d) on %s, sleeping %.1fs", resp.status_code, path, retry_after
                )
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                await asyncio.sleep(self._base_backoff * 2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise BinanceAPIError(
            f"GET {path} failed after {self._max_retries + 1} attempts: {last_error}"
        )

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = KLINES_MAX_LIMIT,
    ) -> list[Kline]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        rows = await self._get(SPOT_BASE, "/api/v3/klines", params, weight=5)
        return [Kline.from_row(row) for row in rows]

    async def get_premium_index(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Mark price / index / funding for all (or one) USD-M futures symbols."""
        params: dict[str, Any] = {"symbol": symbol} if symbol else {}
        result = await self._get(FUTURES_BASE, "/fapi/v1/premiumIndex", params, weight=10)
        return list(result) if isinstance(result, list) else [result]

    async def get_funding_rates(
        self,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = FUNDING_MAX_LIMIT,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        result = await self._get(FUTURES_BASE, "/fapi/v1/fundingRate", params, weight=1)
        return list(result)

    async def get_open_interest_hist(
        self,
        symbol: str,
        period: str = "5m",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = FUTURES_DATA_MAX_LIMIT,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        result = await self._get(FUTURES_BASE, "/futures/data/openInterestHist", params, weight=1)
        return list(result)

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = FUTURES_DATA_MAX_LIMIT,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        result = await self._get(
            FUTURES_BASE, "/futures/data/globalLongShortAccountRatio", params, weight=1
        )
        return list(result)
