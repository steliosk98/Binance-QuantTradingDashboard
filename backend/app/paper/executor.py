"""Order executors for paper trading (spec §5.3).

- SimExecutor: internal fills at the reference price ± slippage (paper-paper
  mode, used when no testnet keys are configured).
- TestnetExecutor: real orders on Binance Spot Testnet (testnet.binance.vision)
  — the ONLY exchange target allowed by the spec. Long-only (spot).

No production trading mode exists anywhere in this codebase.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

TESTNET_BASE = "https://testnet.binance.vision"


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str  # "BUY" | "SELL"
    qty: float
    price: float
    ts_ms: int
    testnet_order_id: str | None = None
    simulated: bool = True


class Executor(Protocol):
    name: str

    async def market_order(self, symbol: str, side: str, qty: float, ref_price: float) -> Fill: ...


class SimExecutor:
    """Fills instantly at ref_price moved against you by slippage_bps."""

    name = "sim"

    def __init__(self, slippage_bps: float = 5.0) -> None:
        self.slippage_bps = slippage_bps

    async def market_order(self, symbol: str, side: str, qty: float, ref_price: float) -> Fill:
        slip = ref_price * self.slippage_bps / 10_000
        price = ref_price + slip if side == "BUY" else ref_price - slip
        return Fill(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            ts_ms=int(time.time() * 1000),
            simulated=True,
        )


class TestnetExecutor:
    """Signed market orders against Binance Spot Testnet only."""

    name = "testnet"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        http: httpx.AsyncClient | None = None,
        base_url: str = TESTNET_BASE,
    ) -> None:
        if get_settings().trading_mode != "testnet":
            raise RuntimeError("TRADING_MODE must be 'testnet' — no other mode exists")
        self._key = api_key
        self._secret = api_secret.encode()
        self._http = http or httpx.AsyncClient(timeout=15.0)
        self._base = base_url
        self._time_offset_ms = 0

    async def sync_time(self) -> None:
        """Sync with server time to avoid clock-skew signature rejections."""
        resp = await self._http.get(f"{self._base}/api/v3/time")
        resp.raise_for_status()
        server_ms = int(resp.json()["serverTime"])
        self._time_offset_ms = server_ms - int(time.time() * 1000)

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "timestamp": int(time.time() * 1000) + self._time_offset_ms}
        query = urlencode(params)
        params["signature"] = hmac.new(self._secret, query.encode(), hashlib.sha256).hexdigest()
        return params

    async def market_order(self, symbol: str, side: str, qty: float, ref_price: float) -> Fill:
        params = self._sign(
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": f"{qty:.6f}",
                "newOrderRespType": "FULL",
            }
        )
        resp = await self._http.post(
            f"{self._base}/api/v3/order",
            params=params,
            headers={"X-MBX-APIKEY": self._key},
        )
        resp.raise_for_status()
        data = resp.json()
        fills = data.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            avg_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
        else:
            total_qty, avg_price = qty, ref_price
        return Fill(
            symbol=symbol,
            side=side,
            qty=total_qty,
            price=avg_price,
            ts_ms=int(data.get("transactTime", time.time() * 1000)),
            testnet_order_id=str(data.get("orderId")),
            simulated=False,
        )


def build_executor() -> Executor:
    """Testnet when keys are configured, otherwise internal sim (paper-paper)."""
    settings = get_settings()
    if settings.binance_testnet_api_key and settings.binance_testnet_api_secret:
        return TestnetExecutor(
            settings.binance_testnet_api_key, settings.binance_testnet_api_secret
        )
    return SimExecutor()
