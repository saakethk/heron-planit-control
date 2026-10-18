from __future__ import annotations

from datetime import timedelta

import jwt

from ..config import Settings
from ..contracts.common import Role, utcnow


def create_token(settings: Settings, username: str, role: Role) -> str:
    now = utcnow()
    claims = {"sub": username, "role": role.value, "iat": now,
              "exp": now + timedelta(seconds=settings.jwt_ttl_seconds)}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decode_token(settings: Settings, token: str) -> dict:
    """Raises jwt.InvalidTokenError for a bad or expired token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
