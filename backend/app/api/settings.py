"""App settings: watchlist, defaults, encrypted API key storage.

API keys are encrypted at rest (Fernet) and NEVER returned to the client —
only a boolean `configured` flag is exposed after save.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import AppSetting

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

API_KEYS_SETTING = "binance_readonly_keys"
GENERAL_SETTING = "general"


async def _get_setting(db: AsyncSession, key: str) -> dict[str, Any] | None:
    row = await db.get(AppSetting, key)
    return dict(row.value_json) if row is not None else None


async def _put_setting(db: AsyncSession, key: str, value: dict[str, Any]) -> None:
    stmt = insert(AppSetting).values(key=key, value_json=value)
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value_json": value})
    await db.execute(stmt)
    await db.commit()


class GeneralSettings(BaseModel):
    watchlist: list[str] = Field(default_factory=list, max_length=50)
    fee_bps: float = Field(default=10.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)
    whale_threshold_usd: float = Field(default=250_000.0, gt=0)


class ApiKeysRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=128)
    api_secret: str = Field(min_length=10, max_length=128)


@router.get("")
async def get_general(db: DbSession) -> dict[str, Any]:
    stored = await _get_setting(db, GENERAL_SETTING)
    settings = get_settings()
    defaults = GeneralSettings(
        watchlist=settings.watchlist_symbols,
        whale_threshold_usd=settings.whale_threshold_usd,
    ).model_dump()
    return {**defaults, **(stored or {})}


@router.put("")
async def put_general(req: GeneralSettings, db: DbSession) -> dict[str, str]:
    await _put_setting(
        db, GENERAL_SETTING, {**req.model_dump(), "watchlist": [s.upper() for s in req.watchlist]}
    )
    return {"status": "saved"}


@router.get("/api-keys")
async def api_keys_status(db: DbSession) -> dict[str, bool]:
    stored = await _get_setting(db, API_KEYS_SETTING)
    return {"configured": stored is not None}


@router.post("/api-keys")
async def save_api_keys(req: ApiKeysRequest, db: DbSession) -> dict[str, bool]:
    await _put_setting(
        db,
        API_KEYS_SETTING,
        {"api_key": encrypt_secret(req.api_key), "api_secret": encrypt_secret(req.api_secret)},
    )
    return {"configured": True}


@router.delete("/api-keys")
async def delete_api_keys(db: DbSession) -> dict[str, bool]:
    row = await db.get(AppSetting, API_KEYS_SETTING)
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"configured": False}


async def load_decrypted_keys(db: AsyncSession) -> tuple[str, str] | None:
    """Internal use only (portfolio client) — never exposed over HTTP."""
    stored = await _get_setting(db, API_KEYS_SETTING)
    if stored is None:
        return None
    return decrypt_secret(stored["api_key"]), decrypt_secret(stored["api_secret"])
