"""Assemble API responses from stored records."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..contracts.api import CrewReport, IndexPoint, LightningHold, Site, SiteConditions
from ..contracts.common import RiskLevel, utcnow
from ..contracts.events import CleanConditions, HazardScore
from ..storage.models import SiteRecord, StoredReport

HISTORY_WINDOW = timedelta(hours=12)
HISTORY_BUCKET = timedelta(minutes=15)


def compress_history(points: list[IndexPoint]) -> list[IndexPoint]:
    """Last value per 15-minute bucket (scores arrive on every strike and report),
    always keeping the newest point. At most ~48 points for 12 hours."""
    buckets: dict[int, IndexPoint] = {}
    size = HISTORY_BUCKET.total_seconds()
    for point in points:
        buckets[int(point.time.timestamp() // size)] = point
    out = list(buckets.values())
    if points and out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def nearest_strike(score: HazardScore | None, hold: LightningHold | None) -> float | None:
    if hold:
        return hold.last_distance_miles
    for driver in (score.drivers.get("lightning", []) if score else []):
        if driver.feature == "nearest_strike_miles" and driver.value is not None and driver.value <= 30:
            return driver.value
    return None


def site_view(record: SiteRecord, score: HazardScore | None, conditions: CleanConditions | None,
              history: list[IndexPoint] | None, hold: LightningHold | None, detail: bool) -> Site:
    index = score.hazard_index if score else 0.0
    site = Site(
        id=record.id, name=record.name, county=record.county, latitude=record.latitude,
        longitude=record.longitude, capacity_mw=record.capacity_mw, hazard_index=index,
        factors=score.factors if score else [],
        updated_at=score.computed_at if score else utcnow(),
        risk_level=RiskLevel.from_index(index).value,
        model_version=score.model_version if score else None,
        data_stale=score.data_stale if score else True,
    )
    if detail:
        if conditions:
            site.conditions = SiteConditions(
                temperature_f=conditions.temperature_f, heat_index_f=conditions.heat_index_f,
                wind_mph=conditions.wind_mph, rain24h_in=conditions.rain_24h_in,
                soil_moisture_pct=conditions.soil_moisture_pct, nearest_strike_miles=nearest_strike(score, hold))
        site.history = compress_history(history or [])
    return site


def history_since() -> datetime:
    return utcnow() - HISTORY_WINDOW


def report_view(report: StoredReport) -> CrewReport:
    return CrewReport(id=report.id, site_id=report.site_id, type=report.type, notes=report.notes,
                      reporter=report.reporter, created_at=report.created_at, photo_url=report.photo_url)
