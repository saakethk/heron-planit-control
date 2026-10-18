"""REST and WebSocket payloads, field-for-field with the app's Swift models.

JSON keys are snake_case; the app decodes with `convertFromSnakeCase`. Extra fields
(for example `model_version`) are ignored by the app, so they can be added freely.
Removing or renaming a field breaks the app.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import AlertSeverity, Contract, HazardType, Role, UtcDatetime


class HazardFactor(Contract):
    type: HazardType
    score: float = Field(ge=0, le=10, description="Contribution on the same 0-10 scale as the Hazard Index")
    detail: str


class IndexPoint(Contract):
    time: UtcDatetime
    value: float


class SiteConditions(Contract):
    temperature_f: float
    heat_index_f: float
    wind_mph: float
    # Not "rain_24h_in": Swift's convertFromSnakeCase turns that into "rain24HIn",
    # which doesn't match the app's `rain24hIn`. "rain24h_in" round-trips.
    rain24h_in: float
    soil_moisture_pct: float
    nearest_strike_miles: float | None = None


class Site(Contract):
    id: int = Field(description="EIA plant ID")
    name: str
    county: str
    latitude: float
    longitude: float
    capacity_mw: float
    hazard_index: float = Field(ge=0, le=10)
    factors: list[HazardFactor]
    updated_at: UtcDatetime
    conditions: SiteConditions | None = None
    history: list[IndexPoint] | None = Field(default=None, description="Today's index values, oldest first")
    # FEMA NFHL flood zone at the plant (A/AE/AH/AO = 100-year floodplain, VE = coastal wave hazard).
    flood_zone: str | None = None
    # Not read by the app yet.
    risk_level: str | None = None
    model_version: str | None = None
    data_stale: bool = False


class NearbySite(Site):
    distance_miles: float


class HazardDriver(Contract):
    feature: str
    contribution: float
    value: float | None = None


class HazardDetail(Contract):
    """Full scoring output for one site: explainability for supervisors."""
    site_id: int
    hazard_index: float
    risk_level: str
    factors: list[HazardFactor]
    drivers: dict[str, list[HazardDriver]]
    report_adjustments: list[str]
    model_version: str
    data_stale: bool
    computed_at: UtcDatetime
    forecast_index: float | None = None


class HazardAlert(Contract):
    id: str
    site_id: int
    type: HazardType
    severity: AlertSeverity
    title: str
    message: str
    issued_at: UtcDatetime
    acknowledged: bool | None = None
    source: str | None = None


class LightningStrike(Contract):
    site_id: int
    distance_miles: float
    occurred_at: UtcDatetime
    direction: str | None = None


class LightningHold(Contract):
    site_id: int
    started_at: UtcDatetime
    last_strike_at: UtcDatetime
    strike_count: int
    closest_miles: float
    last_distance_miles: float
    last_direction: str | None = None
    all_clear_interval: float = Field(description="Seconds; each strike inside the radius restarts it")


class SiteBriefingEvent(Contract):
    id: str
    type: HazardType
    title: str
    detail: str
    time: UtcDatetime
    is_active: bool


class SiteBriefing(Contract):
    site_id: int
    headline: str
    sources: list[str]
    updated_at: UtcDatetime
    events: list[SiteBriefingEvent]
    tomorrow_outlook: str


class DailyBriefingItem(Contract):
    site_id: int
    forecast_index: float
    headline: str


class DailyBriefing(Contract):
    for_date: UtcDatetime
    summary: str
    items: list[DailyBriefingItem]


class HazardReportIn(Contract):
    """Body of POST /reports (the app's `HazardReport`). `photo_jpeg` is base64."""
    id: str
    site_id: int | None = None
    type: HazardType
    notes: str = ""
    latitude: float | None = None
    longitude: float | None = None
    created_at: UtcDatetime
    photo_jpeg: str | None = None


class CrewReport(Contract):
    id: str
    site_id: int | None = None
    type: HazardType
    notes: str
    reporter: str
    created_at: UtcDatetime
    photo_url: str | None = None


class ReportReceipt(Contract):
    id: str
    status: str = "received"
    created_at: UtcDatetime


class DeviceIn(Contract):
    apns_token: str
    platform: str = "ios"


class SubscriptionLocation(Contract):
    name: str
    latitude: float
    longitude: float


class SiteSubscription(Contract):
    location: SubscriptionLocation
    home_site_id: int
    site_ids: list[int]


class LoginIn(Contract):
    username: str
    password: str


class TokenOut(Contract):
    access_token: str
    token_type: str = "bearer"
    role: Role
    expires_in: int


class Health(Contract):
    status: str
    pipeline_mode: str
    storage: str
    model_version: str
    sites: int
    scored_sites: int
    last_scored_at: UtcDatetime | None = None
    active_holds: int
    # e.g. {"weather": "open-meteo", "alerts": "nws", "lightning": "glm"}
    data_sources: dict[str, str] = Field(default_factory=dict)
    last_weather_at: UtcDatetime | None = None
    stale_sites: int = 0


class DecisionLogEntry(Contract):
    id: int
    created_at: UtcDatetime
    site_id: int | None = None
    kind: str
    decision: str
    reason: str
    data: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(Contract):
    error: str
    detail: Any = None


class SimulateIn(Contract):
    """Inject a scripted event into the live pipeline (Settings → Simulate or
    the server prompt: `python -m crewsafe.prompt "lightning at 664"`)."""
    kind: str = Field(default="", description="lightning | heat | flood | briefing | clear (or set prompt)")
    site_id: int | None = None
    miles: float = Field(default=4.0, ge=0.1, le=30, description="Strike distance for kind=lightning")
    prompt: str | None = Field(default=None, description="Natural-language command, e.g. 'flood at Turkey Point'")


class SimulateOut(Contract):
    kind: str
    site_id: int | None = None
    detail: str
    hazard_index: float | None = None
    heat_index_f: float | None = None
    rain24h_in: float | None = None
    active_hold: bool = False


# --- WebSocket -------------------------------------------------------------

class HazardIndexUpdate(Contract):
    site_id: int
    hazard_index: float
    factors: list[HazardFactor] | None = None


class SubscribePayload(Contract):
    site_ids: list[int] = Field(default_factory=list)
    include_severe_statewide: bool = True
    last_seq: int | None = None


class Envelope(Contract):
    """Server -> app: `{"type", "seq", "payload"}`.

    Types the app handles today: hazard_index_updated, hazard_index_batch, alert,
    lightning_strike. Also sent (ignored by the current app): subscribed,
    lightning_hold_updated, lightning_hold_cleared, report_created, resync_required, pong.
    """
    type: str
    seq: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
