from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...config import Settings
from ...contracts.api import LoginIn, TokenOut
from ...contracts.common import Role
from ...security import verify_password
from ...storage.repository import Repository
from ..auth import create_token
from ..deps import get_repo, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, repo: Repository = Depends(get_repo),
                settings: Settings = Depends(get_settings)) -> TokenOut:
    user = await repo.get_user(body.username)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "wrong username or password")
    role = Role(user.role)
    return TokenOut(access_token=create_token(settings, user.username, role), role=role,
                    expires_in=settings.jwt_ttl_seconds)
