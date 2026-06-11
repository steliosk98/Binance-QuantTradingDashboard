"""Stage 8: crypto round-trip, auth flow, settings, portfolio, key-leak grep."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core import security
from app.core.config import get_settings
from app.main import app

TEST_PASSWORD = "correct horse battery staple"
FAKE_API_KEY = "AKIAFAKEKEY1234567890"
FAKE_API_SECRET = "SuperSecretValue0987654321"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "secret_key", "unit-test-secret-key")
    monkeypatch.setattr(settings, "app_password_hash", security.hash_password(TEST_PASSWORD))


@pytest.fixture
async def client(db_session: AsyncSession, auth_env: None) -> AsyncIterator[httpx.AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def login(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_encrypt_decrypt_round_trip(auth_env: None) -> None:
    ciphertext = security.encrypt_secret("hello-secret")
    assert ciphertext != "hello-secret"
    assert security.decrypt_secret(ciphertext) == "hello-secret"


def test_password_hash_verify() -> None:
    h = security.hash_password("pw1")
    assert security.verify_password("pw1", h)
    assert not security.verify_password("pw2", h)


def test_token_expiry(auth_env: None) -> None:
    import jwt as pyjwt

    good = security.create_token(ttl_seconds=60)
    assert security.verify_token(good)["sub"] == "owner"
    expired = security.create_token(ttl_seconds=-10)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        security.verify_token(expired)


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/symbols", "/api/v1/settings", "/api/v1/portfolio/status"):
        resp = await client.get(path)
        assert resp.status_code == 401, path
    # Health stays public
    assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_login_flow(client: httpx.AsyncClient) -> None:
    bad = await client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert bad.status_code == 401
    headers = await login(client)
    ok = await client.get("/api/v1/symbols", headers=headers)
    assert ok.status_code == 200
    garbage = await client.get("/api/v1/symbols", headers={"Authorization": "Bearer junk"})
    assert garbage.status_code == 401


@pytest.mark.asyncio
async def test_settings_round_trip(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    put = await client.put(
        "/api/v1/settings",
        json={
            "watchlist": ["btcusdt", "ETHUSDT"],
            "fee_bps": 8,
            "slippage_bps": 3,
            "whale_threshold_usd": 100000,
        },
        headers=headers,
    )
    assert put.status_code == 200
    got = (await client.get("/api/v1/settings", headers=headers)).json()
    assert got["watchlist"] == ["BTCUSDT", "ETHUSDT"]
    assert got["fee_bps"] == 8


@pytest.mark.asyncio
async def test_api_keys_never_returned(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    headers = await login(client)
    save = await client.post(
        "/api/v1/settings/api-keys",
        json={"api_key": FAKE_API_KEY, "api_secret": FAKE_API_SECRET},
        headers=headers,
    )
    assert save.status_code == 200 and save.json() == {"configured": True}

    # Grep every settings/portfolio-ish response for the secret material.
    for path in ("/api/v1/settings", "/api/v1/settings/api-keys", "/api/v1/portfolio/status"):
        body = (await client.get(path, headers=headers)).text
        assert FAKE_API_KEY not in body, path
        assert FAKE_API_SECRET not in body, path

    # Stored encrypted, not plaintext.
    from app.models import AppSetting

    row = await db_session.get(AppSetting, "binance_readonly_keys")
    assert row is not None
    stored = json.dumps(row.value_json)
    assert FAKE_API_KEY not in stored
    assert FAKE_API_SECRET not in stored

    delete = await client.delete("/api/v1/settings/api-keys", headers=headers)
    assert delete.json() == {"configured": False}


@pytest.mark.asyncio
@respx.mock
async def test_portfolio_with_mocked_account(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await login(client)
    await client.post(
        "/api/v1/settings/api-keys",
        json={"api_key": FAKE_API_KEY, "api_secret": FAKE_API_SECRET},
        headers=headers,
    )
    respx.get("https://api.binance.com/api/v3/time").respond(json={"serverTime": 1700000000000})
    respx.get("https://api.binance.com/api/v3/account").respond(
        json={
            "canTrade": False,
            "accountType": "SPOT",
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0"},
                {"asset": "USDT", "free": "1000", "locked": "0"},
                {"asset": "DUST", "free": "0", "locked": "0"},
            ],
        }
    )
    resp = await client.get("/api/v1/portfolio", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assets = {b["asset"] for b in body["balances"]}
    assert assets == {"BTC", "USDT"}
    usdt = next(b for b in body["balances"] if b["asset"] == "USDT")
    assert usdt["usd_value"] == pytest.approx(1000.0)
    assert FAKE_API_SECRET not in resp.text


@pytest.mark.asyncio
async def test_portfolio_404_without_keys(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    status = (await client.get("/api/v1/portfolio/status", headers=headers)).json()
    assert status == {"configured": False}
    resp = await client.get("/api/v1/portfolio", headers=headers)
    assert resp.status_code == 404
