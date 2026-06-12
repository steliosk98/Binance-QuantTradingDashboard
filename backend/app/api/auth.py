"""Single-user auth: password login → JWT; dependency protecting all routes.

When SECRET_KEY/APP_PASSWORD_HASH are unset (bare dev checkout) auth is
disabled and every request passes — the login endpoint then refuses to issue
tokens so the state is explicit, never half-configured. In production
(ENVIRONMENT=production) the app refuses to start without auth configured
(fail closed).
"""

import logging
import time

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import create_token, verify_password, verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

#: Brute-force throttle: max failed attempts per client IP per window.
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60.0
_failed_logins: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    """Client IP, honoring the first X-Forwarded-For hop behind our proxy."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str, now: float | None = None) -> None:
    now = now if now is not None else time.time()
    window = [t for t in _failed_logins.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _failed_logins[ip] = window
    if len(window) >= LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed attempts; try again in a minute",
            headers={"Retry-After": "60"},
        )


def _record_failure(ip: str, now: float | None = None) -> None:
    _failed_logins.setdefault(ip, []).append(now if now is not None else time.time())


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request) -> dict[str, str]:
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=503, detail="auth not configured on this server")
    ip = client_ip(request)
    _check_rate_limit(ip)
    if not verify_password(req.password, settings.app_password_hash):
        _record_failure(ip)
        logger.warning("failed login attempt", extra={"extra_fields": {"ip": ip}})
        raise HTTPException(status_code=401, detail="invalid password")
    _failed_logins.pop(ip, None)
    return {"token": create_token(), "token_type": "bearer"}


@router.get("/status")
async def auth_status() -> dict[str, bool]:
    return {"auth_enabled": get_settings().auth_enabled}


def enforce_production_auth() -> None:
    """Fail closed: refuse to boot an unauthenticated production deployment."""
    settings = get_settings()
    if settings.environment == "production" and not settings.auth_enabled:
        raise RuntimeError(
            "ENVIRONMENT=production requires SECRET_KEY and APP_PASSWORD_HASH — "
            "refusing to start with auth disabled"
        )


async def require_auth(request: Request) -> None:
    """FastAPI dependency: enforce a valid bearer token when auth is enabled."""
    if not get_settings().auth_enabled:
        return
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    try:
        verify_token(token)
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc
