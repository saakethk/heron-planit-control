from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...contracts.api import DecisionLogEntry
from ...storage.repository import Repository
from ..deps import get_repo, require_supervisor

router = APIRouter(tags=["audit"], dependencies=[Depends(require_supervisor)])


@router.get("/decision-log", response_model=list[DecisionLogEntry])
async def decision_log(site_id: int | None = Query(None), limit: int = Query(100, ge=1, le=1000),
                       repo: Repository = Depends(get_repo)) -> list[DecisionLogEntry]:
    """Why each alert was sent or suppressed (supervisors only)."""
    return [DecisionLogEntry(**d.model_dump()) for d in await repo.list_decisions(site_id, limit)]
