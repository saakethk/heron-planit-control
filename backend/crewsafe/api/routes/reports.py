from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...config import Settings
from ...contracts.api import CrewReport, HazardReportIn, ReportReceipt
from ...contracts.events import CrewReportEvent
from ...geo import miles_between
from ...messaging import topics
from ...runtime import Pipeline
from ...storage.models import StoredReport
from ...storage.repository import Repository
from ..deps import Principal, current_user, get_pipeline, get_repo, get_settings, parse_ids
from ..views import report_view

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_PHOTO_BYTES = 8 * 1024 * 1024
NEAREST_SITE_MILES = 5.0
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@router.get("", response_model=list[CrewReport], response_model_exclude_none=True)
async def list_reports(
    site_ids: str | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    repo: Repository = Depends(get_repo),
    user: Principal = Depends(current_user),
):
    return [report_view(r) for r in await repo.list_reports(parse_ids(site_ids), since, limit)]


@router.post("", response_model=ReportReceipt, status_code=201)
async def submit_report(
    body: HazardReportIn,
    request: Request,
    response: Response,
    p: Pipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
    user: Principal = Depends(current_user),
) -> ReportReceipt:
    """JSON body with an optional base64 JPEG (`photo_jpeg`). The report ID comes
    from the app, so a retried upload is stored once."""
    if not SAFE_ID.match(body.id):
        raise HTTPException(422, "id may only contain letters, digits, '-', '_' and '.'")
    site_id = body.site_id
    if site_id is None and body.latitude is not None and body.longitude is not None:
        site_id = await _nearest_site(p.repo, body.latitude, body.longitude)
    elif site_id is not None and await p.repo.get_site(site_id) is None:
        raise HTTPException(422, f"unknown site {site_id}")

    photo_url = None
    if body.photo_jpeg:
        photo_url = _save_photo(settings, request, body.id, body.photo_jpeg)

    report = StoredReport(id=body.id, site_id=site_id, type=body.type, notes=body.notes.strip()[:2000],
                          reporter=user.display_name, created_at=body.created_at, latitude=body.latitude,
                          longitude=body.longitude, photo_url=photo_url)
    if await p.repo.save_report(report):
        await p.bus.publish(topics.CREW_REPORTS, CrewReportEvent(**report.model_dump()), key=site_id)
    else:
        response.status_code = 200
    return ReportReceipt(id=report.id, created_at=report.created_at)


async def _nearest_site(repo: Repository, lat: float, lon: float) -> int | None:
    best = min(((miles_between(lat, lon, s.latitude, s.longitude), s.id) for s in await repo.list_sites()),
               default=None)
    return best[1] if best and best[0] <= NEAREST_SITE_MILES else None


def _save_photo(settings: Settings, request: Request, report_id: str, encoded: str) -> str:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "photo_jpeg must be base64") from exc
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo larger than 8 MB")
    if not data.startswith(b"\xff\xd8"):
        raise HTTPException(422, "photo_jpeg must be a JPEG")
    # Swap for object storage (S3 / GCS pre-signed uploads) in production.
    folder = Path(settings.photo_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{report_id}.jpg").write_bytes(data)
    return str(request.url_for("photos", path=f"{report_id}.jpg"))
