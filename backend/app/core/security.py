"""Security primitives: Fernet encryption at rest, argon2 password check,
JWT issuance/verification. SECRET_KEY (env) drives both Fernet and JWT.
"""

import base64
import hashlib
import time
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 24 * 3600

_hasher = PasswordHasher()


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("could not decrypt stored secret (SECRET_KEY changed?)") from exc


def hash_password(password: str) -> str:
    """Helper for generating APP_PASSWORD_HASH (used by ops, not at runtime)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_token(ttl_seconds: int = JWT_TTL_SECONDS) -> str:
    secret = get_settings().secret_key
    now = int(time.time())
    return jwt.encode({"sub": "owner", "iat": now, "exp": now + ttl_seconds}, secret, JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any]:
    """Returns the payload or raises jwt.InvalidTokenError (incl. expiry)."""
    secret = get_settings().secret_key
    result: dict[str, Any] = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    return result
