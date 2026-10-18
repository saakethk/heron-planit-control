from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...contracts.api import HazardAlert
from ...storage.repository import Repository
from ..deps import Principal, current_user, get_repo, parse_ids

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[HazardAlert])
async def list_alerts(
    since: datetime | None = Query(None, description="ISO-8601; only alerts issued at or after this time"),
    site_ids: str | None = Query(None, description="Comma-separated plant IDs (the app sends its followed sites)"),
    limit: int = Query(150, ge=1, le=500),
    repo: Repository = Depends(get_repo),
    user: Principal = Depends(current_user),
) -> list[HazardAlert]:
    """Newest first. `acknowledged` is per user."""
    return await repo.list_alerts(user.user_id, parse_ids(site_ids), since, limit)


@router.post("/{alert_id}/ack", status_code=204)
async def acknowledge(alert_id: str, repo: Repository = Depends(get_repo),
                      user: Principal = Depends(current_user)) -> Response:
    if not await repo.acknowledge_alert(alert_id, user.user_id):
        raise HTTPException(404, f"alert {alert_id} not found")
    return Response(status_code=204)
