"""Messages on the bus. Every message is keyed by `site_id` where one exists, so
all events for a site stay ordered within a Kafka partition."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .api import HazardAlert, HazardDriver, HazardFactor, LightningHold
from .common import Contract, UtcDatetime


class RawObservation(Contract):
    """raw.weather: one site's payload exactly as the source returned it."""
    source: str
    site_id: int
    fetched_at: UtcDatetime
    payload: dict[str, Any]


class RawNwsAlert(Contract):
    """raw.nws.alerts: one active NWS alert (not yet matched to sites)."""
    alert_id: str
    event: str
    severity: str
    headline: str
    description: str = ""
    onset: UtcDatetime | None = None
    expires: UtcDatetime | None = None
    # Sites the source already knows are affected (dummy source), or a GeoJSON
    # polygon the transformer matches against site coordinates (real NWS).
    site_ids: list[int] = Field(default_factory=list)
    geometry: dict[str, Any] | None = None


class RawLightningStrike(Contract):
    """raw.lightning: a single cloud-to-ground strike."""
    strike_id: str
    latitude: float
    longitude: float
    occurred_at: UtcDatetime
    source: str


class Forecast(Contract):
    """Next-day outlook derived by the transformer, scored for the 6 PM briefing."""
    max_temp_f: float
    max_heat_index_f: float
    precip_in: float
    precip_probability: float
    max_cape: float
    max_wind_gust_mph: float


class CleanConditions(Contract):
    """clean.conditions: validated, normalized, feature-enriched observation."""
    site_id: int
    obs_time: UtcDatetime
    source: str
    temperature_f: float
    humidity_pct: float
    heat_index_f: float
    wind_mph: float
    wind_gust_mph: float
    precip_1h_in: float
    rain_24h_in: float
    rain_3d_in: float
    rain_7d_in: float
    cape: float
    soil_moisture_pct: float
    drought_index: float
    river_stage_ft_above_flood: float | None = None
    tide_ft_above_mhhw: float | None = None
    nearest_strike_miles: float | None = None
    data_stale: bool = False
    forecast: Forecast | None = None


class SiteNwsAlert(Contract):
    """clean.nws.alerts: an NWS alert matched to one site."""
    site_id: int
    alert_id: str
    event: str
    severity: str
    headline: str
    description: str
    onset: UtcDatetime | None = None
    expires: UtcDatetime | None = None


class HazardScore(Contract):
    """hazard.scores: one scoring run for one site."""
    site_id: int
    computed_at: UtcDatetime
    hazard_index: float
    factors: list[HazardFactor]
    drivers: dict[str, list[HazardDriver]] = Field(default_factory=dict)
    report_adjustments: list[str] = Field(default_factory=list)
    model_version: str
    data_stale: bool = False
    forecast_index: float | None = None
    forecast_headline: str | None = None
    # Backfilled scores fill the chart but must not page anyone.
    backfill: bool = False


class CrewReportEvent(Contract):
    """crew.reports: a crew report, after the API stored it."""
    id: str
    site_id: int | None = None
    type: str
    notes: str
    reporter: str
    created_at: UtcDatetime
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None


class SiteStrike(Contract):
    """lightning.site_strikes: a strike within the watch radius of a site."""
    site_id: int
    strike_id: str
    distance_miles: float
    direction: str
    occurred_at: UtcDatetime
    inside_stop_work_radius: bool


class HoldEvent(Contract):
    """lightning.holds: a stop-work hold started, was extended, or cleared."""
    site_id: int
    event: str  # started | extended | cleared
    hold: LightningHold
    at: UtcDatetime


class AlertIssued(HazardAlert):
    """alerts.issued: an alert the alert service decided to send."""
