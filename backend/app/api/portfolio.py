"""Read-only portfolio from Binance production account (signed GET only).

Never requests trade permissions; never logs or returns key material.
"""

import hashlib
import hmac
import logging
import time
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.settings import load_decrypted_keys
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

SPOT_BASE = "https://api.binance.com"


async def fetch_account(api_key: str, api_secret: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as http:
        server_time = await http.get(f"{SPOT_BASE}/api/v3/time")
        server_time.raise_for_status()
        offset = int(server_time.json()["serverTime"]) - int(time.time() * 1000)
        params: dict[str, Any] = {
            "timestamp": int(time.time() * 1000) + offset,
            "omitZeroBalances": "true",
        }
        signature = hmac.new(
            api_secret.encode(), urlencode(params).encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        resp = await http.get(
            f"{SPOT_BASE}/api/v3/account", params=params, headers={"X-MBX-APIKEY": api_key}
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


@router.get("/status")
async def portfolio_status(db: DbSession) -> dict[str, bool]:
    keys = await load_decrypted_keys(db)
    return {"configured": keys is not None}


@router.get("")
async def get_portfolio(db: DbSession) -> dict[str, Any]:
    keys = await load_decrypted_keys(db)
    if keys is None:
        raise HTTPException(status_code=404, detail="no API keys configured")
    try:
        account = await fetch_account(*keys)
    except httpx.HTTPStatusError as exc:
        logger.warning("portfolio fetch failed with HTTP %d", exc.response.status_code)
        raise HTTPException(
            status_code=502, detail=f"Binance account request failed ({exc.response.status_code})"
        ) from exc

    balances = [
        {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
        for b in account.get("balances", [])
        if float(b["free"]) + float(b["locked"]) > 0
    ]

    # USD valuation via cached tickers where possible.
    redis = get_redis()
    valued: list[dict[str, Any]] = []
    total_usd = 0.0
    for b in balances:
        qty = b["free"] + b["locked"]
        usd: float | None = None
        if b["asset"] in ("USDT", "USDC", "FDUSD", "BUSD"):
            usd = qty
        else:
            raw = await redis.hget("latest_tickers", f"{b['asset']}USDT")
            if raw:
                import json

                usd = qty * float(json.loads(raw)["last"])
        if usd is not None:
            total_usd += usd
        valued.append({**b, "usd_value": usd})

    valued.sort(key=lambda x: -(x["usd_value"] or 0))
    return {
        "balances": valued,
        "total_usd": total_usd,
        "can_trade": account.get("canTrade"),
        "account_type": account.get("accountType"),
    }
