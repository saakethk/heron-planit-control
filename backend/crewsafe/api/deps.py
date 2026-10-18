from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

from ..config import Settings
from ..contracts.common import Role
from ..runtime import Pipeline
from ..storage.repository import Repository
from ..storage.seed import DEMO_USER_ID
from .auth import decode_token


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    display_name: str


def get_pipeline(request: Request) -> Pipeline:
    return request.app.state.pipeline


def get_repo(request: Request) -> Repository:
    return request.app.state.pipeline.repo


def get_settings(request: Request) -> Settings:
    return request.app.state.pipeline.settings


def principal_from_token(settings: Settings, token: str | None) -> Principal | None:
    if not token:
        return None
    try:
        claims = decode_token(settings, token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, f"invalid token: {exc}") from exc
    return Principal(user_id=claims["sub"], role=Role(claims["role"]), display_name=claims["sub"])


async def current_user(request: Request, settings: Settings = Depends(get_settings)) -> Principal:
    """Bearer JWT. With AUTH_REQUIRED=false (default, the app doesn't log in yet)
    requests without a token act as the shared demo user."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    principal = principal_from_token(settings, token)
    if principal:
        return principal
    if settings.auth_required:
        raise HTTPException(401, "missing bearer token")
    return Principal(user_id=DEMO_USER_ID, role=Role.supervisor, display_name="Demo Crew")


async def require_supervisor(user: Principal = Depends(current_user)) -> Principal:
    if user.role != Role.supervisor:
        raise HTTPException(403, "supervisor role required")
    return user


def parse_ids(value: str | None) -> list[int] | None:
    """`site_ids=664,617` -> [664, 617]."""
    if value is None or value == "":
        return None
    try:
        return [int(v) for v in value.split(",") if v.strip()]
    except ValueError as exc:
        raise HTTPException(422, "site_ids must be comma-separated integers") from exc
