from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends

from ...contracts.api import LightningHold
from ...contracts.common import utcnow
from ...storage.repository import Repository
from ..deps import current_user, get_repo

router = APIRouter(prefix="/lightning", tags=["lightning"], dependencies=[Depends(current_user)])


@router.get("/holds", response_model=list[LightningHold])
async def active_holds(repo: Repository = Depends(get_repo)) -> list[LightningHold]:
    """Active stop-work holds. The 30-minute timer runs on the server; each hold's
    end time is `last_strike_at + all_clear_interval`."""
    now = utcnow()
    holds = [h for h in await repo.list_holds()
             if h.last_strike_at + timedelta(seconds=h.all_clear_interval) > now]
    return sorted(holds, key=lambda h: h.last_strike_at, reverse=True)
