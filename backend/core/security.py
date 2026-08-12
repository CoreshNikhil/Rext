"""Password hashing, OTP generation/hashing, and JWT access tokens.

Refresh tokens are deliberately NOT JWTs — they're opaque random secrets,
hashed (SHA-256) before being stored in the RefreshToken table, so
`/auth/logout` and reuse-detection can work against a real DB row rather
than trusting an unrevocable signed token.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from passlib.context import CryptContext

from backend.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"])

TokenScope = Literal["resident", "admin", "resident_signup", "password_reset"]

JWT_ALGORITHM = "HS256"


# --- Passwords -------------------------------------------------------------


def hash_password(raw_password: str) -> str:
    return _pwd_context.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(raw_password, password_hash)


# --- OTP ---------------------------------------------------------------------


def generate_otp_code(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_otp(raw_otp: str) -> str:
    # Same bcrypt context as passwords — OTPs are short-lived low-entropy
    # secrets, but they must never be recoverable from the DB either.
    return _pwd_context.hash(raw_otp)


def verify_otp(raw_otp: str, otp_hash: str) -> bool:
    return _pwd_context.verify(raw_otp, otp_hash)


# --- JWT access tokens ---------------------------------------------------


def create_access_token(subject_id: int, scope: TokenScope, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject_id),
        "scope": scope,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


class TokenError(Exception):
    """Raised for any invalid/expired/malformed JWT."""


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc


# --- Refresh tokens (opaque, not JWTs) --------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
