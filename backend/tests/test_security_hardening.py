"""V2 security hardening: login throttling, fail-closed prod, WS first-message auth."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import auth as auth_module
from app.api.auth import enforce_production_auth
from app.api.deps import get_db
from app.core import security
from app.core.config import get_settings
from app.main import app

PW = "hardening-test-pw"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "secret_key", "hardening-secret")
    monkeypatch.setattr(settings, "app_password_hash", security.hash_password(PW))
    auth_module._failed_logins.clear()


@pytest.fixture
async def client(db_session: AsyncSession, auth_env: None) -> AsyncIterator[httpx.AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_rate_limited_after_failures(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        resp = await client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401
    blocked = await client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"
    # Even the CORRECT password is throttled while blocked
    still = await client.post("/api/v1/auth/login", json={"password": PW})
    assert still.status_code == 429


@pytest.mark.asyncio
async def test_successful_login_resets_counter(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        await client.post("/api/v1/auth/login", json={"password": "wrong"})
    ok = await client.post("/api/v1/auth/login", json={"password": PW})
    assert ok.status_code == 200
    assert auth_module._failed_logins == {}


def test_rate_limit_window_expires() -> None:
    auth_module._failed_logins.clear()
    for i in range(5):
        auth_module._record_failure("1.2.3.4", now=100.0 + i)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        auth_module._check_rate_limit("1.2.3.4", now=110.0)
    # 61s later the window has rolled
    auth_module._check_rate_limit("1.2.3.4", now=165.0)


def test_production_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "")
    monkeypatch.setattr(settings, "app_password_hash", "")
    with pytest.raises(RuntimeError, match="refusing to start"):
        enforce_production_auth()
    # Configured production boots fine
    monkeypatch.setattr(settings, "secret_key", "x")
    monkeypatch.setattr(settings, "app_password_hash", "y")
    enforce_production_auth()


def test_ws_requires_first_message_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "secret_key", "hardening-secret")
    monkeypatch.setattr(settings, "app_password_hash", security.hash_password(PW))

    token = security.create_token()
    with TestClient(app) as client:
        # Valid token in first frame → authenticated + functional
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"op": "auth", "token": token}))
            assert json.loads(ws.receive_text()) == {"op": "authenticated"}
            ws.send_text(json.dumps({"op": "ping"}))
            assert json.loads(ws.receive_text()) == {"op": "pong"}

        # Bad token → closed 4401
        with (
            pytest.raises((WebSocketDisconnect, RuntimeError)),
            client.websocket_connect("/ws") as ws,
        ):
            ws.send_text(json.dumps({"op": "auth", "token": "garbage"}))
            ws.receive_text()

        # Non-auth first frame → closed
        with (
            pytest.raises((WebSocketDisconnect, RuntimeError)),
            client.websocket_connect("/ws") as ws,
        ):
            ws.send_text(json.dumps({"op": "subscribe", "topics": ["tickers"]}))
            ws.receive_text()
