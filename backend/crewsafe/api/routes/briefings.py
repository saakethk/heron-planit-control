from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...contracts.api import DailyBriefing
from ...processing.briefings import next_day_briefing
from ...storage.repository import Repository
from ..deps import Principal, current_user, get_repo, parse_ids

router = APIRouter(prefix="/briefings", tags=["briefings"])


@router.get("/next-day", response_model=DailyBriefing)
async def next_day(
    site_id: int | None = Query(None, description="Rank this site's forecast (with site_ids, if given)"),
    site_ids: str | None = Query(None, description="Comma-separated; defaults to the caller's followed sites"),
    repo: Repository = Depends(get_repo),
    user: Principal = Depends(current_user),
) -> DailyBriefing:
    """Tomorrow's outlook, highest forecast index first (the 6 PM briefing)."""
    ids = parse_ids(site_ids) or []
    if site_id is not None:
        ids.append(site_id)
    if not ids:
        subscription = await repo.get_subscription(user.user_id)
        ids = subscription.site_ids if subscription else []
    return await next_day_briefing(repo, ids or None)
