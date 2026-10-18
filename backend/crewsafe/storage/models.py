"""Stored records that are not part of the API contract."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..contracts.common import Contract, Role, UtcDatetime


class SiteRecord(Contract):
    """Static site attributes (the scoring "site layer").

    `id`..`capacity_mw` come from EIA-860M. The rest are placeholders until the
    GIS joins exist (FEMA flood zones, USGS elevation, NLD levees, habitat maps).
    """
    id: int
    name: str
    county: str
    latitude: float
    longitude: float
    capacity_mw: float
    coastal: bool = False
    near_river: bool = False
    elevation_ft: float = 30.0
    wildlife_habitat: float = Field(default=0.3, ge=0, le=1)


class UserRecord(Contract):
    username: str
    display_name: str
    password_hash: str
    role: Role


class DeviceRecord(Contract):
    user_id: str
    apns_token: str
    platform: str
    registered_at: UtcDatetime


class StoredReport(Contract):
    id: str
    site_id: int | None = None
    type: str
    notes: str
    reporter: str
    created_at: UtcDatetime
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None


class Decision(Contract):
    id: int = 0
    created_at: UtcDatetime
    site_id: int | None = None
    kind: str
    decision: str
    reason: str
    data: dict[str, Any] = Field(default_factory=dict)
