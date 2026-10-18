from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...contracts.api import HazardDetail, NearbySite, Site, SiteBriefing
from ...contracts.common import RiskLevel
from ...geo import miles_between
from ...processing.briefings import site_briefing
from ...storage.repository import Repository
from ..deps import current_user, get_repo, parse_ids
from ..views import history_since, site_view

router = APIRouter(prefix="/sites", tags=["sites"], dependencies=[Depends(current_user)])


async def _all_sites(repo: Repository, detail: bool, only: list[int] | None = None) -> list[Site]:
    records = await repo.list_sites()
    if only is not None:
        wanted = set(only)
        records = [r for r in records if r.id in wanted]
    scores = await repo.latest_scores()
    holds = {h.site_id: h for h in await repo.list_holds()}
    conditions = await repo.all_latest_conditions() if detail else {}
    history = await repo.all_score_history(history_since()) if detail else {}
    return [site_view(r, scores.get(r.id), conditions.get(r.id), history.get(r.id), holds.get(r.id), detail)
            for r in records]


@router.get("", response_model=list[Site], response_model_exclude_none=True)
async def list_sites(
    request: Request,
    response: Response,
    view: str = Query("full", pattern="^(full|summary)$",
                      description="`summary` omits conditions and history (smaller payload)"),
    site_ids: str | None = Query(None, description="Comma-separated plant IDs"),
    repo: Repository = Depends(get_repo),
):
    """Every site with its current Hazard Index. Supports ETag / If-None-Match."""
    scores = await repo.latest_scores()
    newest = max((s.computed_at.timestamp() for s in scores.values()), default=0)
    holds = len(await repo.list_holds())
    etag = 'W/"' + hashlib.sha1(f"{newest}-{len(scores)}-{holds}-{view}-{site_ids}".encode()).hexdigest()[:16] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return await _all_sites(repo, detail=view == "full", only=parse_ids(site_ids))


@router.get("/nearby", response_model=list[NearbySite], response_model_exclude_none=True)
async def nearby_sites(
    response: Response,
    lat: float = Query(..., ge=24, le=31.5),
    lon: float = Query(..., ge=-88, le=-79.5),
    limit: int = Query(25, ge=1, le=400),
    offset: int = Query(0, ge=0),
    repo: Repository = Depends(get_repo),
):
    """Sites sorted by great-circle distance from a point. `X-Total-Count` has the total."""
    sites = await _all_sites(repo, detail=False)
    ranked = sorted(((miles_between(lat, lon, s.latitude, s.longitude), s) for s in sites), key=lambda x: x[0])
    response.headers["X-Total-Count"] = str(len(ranked))
    return [NearbySite(**s.model_dump(), distance_miles=round(d, 1)) for d, s in ranked[offset:offset + limit]]


@router.get("/{site_id}", response_model=Site, response_model_exclude_none=True)
async def get_site(site_id: int, repo: Repository = Depends(get_repo)):
    record = await repo.get_site(site_id)
    if record is None:
        raise HTTPException(404, f"site {site_id} not found")
    return site_view(record, await repo.latest_score(site_id), await repo.latest_conditions(site_id),
                     await repo.score_history(site_id, history_since()), await repo.get_hold(site_id), detail=True)


@router.get("/{site_id}/briefing", response_model=SiteBriefing)
async def get_site_briefing(site_id: int, repo: Repository = Depends(get_repo)):
    briefing = await site_briefing(repo, site_id)
    if briefing is None:
        raise HTTPException(404, f"site {site_id} not found")
    return briefing


@router.get("/{site_id}/hazard", response_model=HazardDetail)
async def get_site_hazard(site_id: int, repo: Repository = Depends(get_repo)):
    """Full scoring output with model drivers, for supervisors and debugging."""
    score = await repo.latest_score(site_id)
    if score is None:
        raise HTTPException(404, f"no score for site {site_id}")
    return HazardDetail(site_id=site_id, hazard_index=score.hazard_index,
                        risk_level=RiskLevel.from_index(score.hazard_index).value, factors=score.factors,
                        drivers=score.drivers, report_adjustments=score.report_adjustments,
                        model_version=score.model_version, data_stale=score.data_stale,
                        computed_at=score.computed_at, forecast_index=score.forecast_index)
