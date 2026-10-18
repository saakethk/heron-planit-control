from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...contracts.api import DeviceIn, SiteSubscription
from ...contracts.common import utcnow
from ...storage.models import DeviceRecord
from ...storage.repository import Repository
from ..deps import Principal, current_user, get_repo

router = APIRouter(tags=["devices"])


@router.post("/devices", status_code=201)
async def register_device(body: DeviceIn, repo: Repository = Depends(get_repo),
                          user: Principal = Depends(current_user)) -> dict:
    """APNs token for push alerts. Re-registering the same token is a no-op."""
    await repo.register_device(DeviceRecord(user_id=user.user_id, apns_token=body.apns_token,
                                            platform=body.platform, registered_at=utcnow()))
    return {"status": "registered"}


@router.put("/me/subscription", status_code=204)
async def update_subscription(body: SiteSubscription, repo: Repository = Depends(get_repo),
                              user: Principal = Depends(current_user)) -> Response:
    """The user's location and followed sites (home + nearest 25). Decides which
    sites' alerts are pushed to this user's devices."""
    known = {s.id for s in await repo.list_sites()}
    body = body.model_copy(update={"site_ids": [i for i in dict.fromkeys(body.site_ids) if i in known]})
    await repo.save_subscription(user.user_id, body)
    return Response(status_code=204)
