"""Single-user auth: password login → JWT; dependency protecting all routes.

When SECRET_KEY/APP_PASSWORD_HASH are unset (bare dev checkout) auth is
disabled and every request passes — the login endpoint then refuses to issue
tokens so the state is explicit, never half-configured.
"""

import logging

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import create_token, verify_password, verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(req: LoginRequest) -> dict[str, str]:
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="auth not configured on this server")
    if not verify_password(req.password, settings.app_password_hash):
        raise HTTPException(status_code=401, detail="invalid password")
    return {"token": create_token(), "token_type": "bearer"}


@router.get("/status")
async def auth_status() -> dict[str, bool]:
    return {"auth_enabled": get_settings().auth_enabled}


async def require_auth(request: Request) -> None:
    """FastAPI dependency: enforce a valid bearer token when auth is enabled."""
    if not get_settings().auth_enabled:
        return
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        # WS upgrade requests can pass ?token=
        token = request.query_params.get("token", "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    try:
        verify_token(token)
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc
