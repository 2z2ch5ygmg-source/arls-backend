from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from .config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(value: str) -> str:
    return pwd_ctx.hash(value)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def encode_token(payload: dict, *, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = dict(payload)
    payload["iat"] = now
    payload["exp"] = now + timedelta(minutes=expires_minutes or settings.jwt_expires_minutes)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def encode_refresh_token(payload: dict) -> str:
    next_payload = dict(payload)
    next_payload["token_use"] = "refresh"
    return encode_token(next_payload, expires_minutes=settings.jwt_refresh_expires_minutes)


def decode_refresh_token(token: str) -> dict:
    payload = decode_token(token)
    if str(payload.get("token_use") or "").strip().lower() != "refresh":
        raise ValueError("invalid refresh token")
    return payload


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
