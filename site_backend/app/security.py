from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

ALGORITHM = "HS256"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_admin_ids() -> set[int]:
    out: set[int] = set()
    for raw in (settings.admin_ids or "").split(","):
        raw = raw.strip()
        if raw.isdigit():
            out.add(int(raw))
    return out


def _exp(minutes: int) -> datetime:
    return now_utc() + timedelta(minutes=minutes)


def create_access_token(*, user_id: int, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "adm": bool(is_admin),
        "iat": int(now_utc().timestamp()),
        "exp": int(_exp(settings.access_token_ttl_minutes).timestamp()),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: int) -> tuple[str, datetime]:
    exp = _exp(settings.refresh_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "iat": int(now_utc().timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(24),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, exp


def decode_token(token: str, *, expected_type: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
