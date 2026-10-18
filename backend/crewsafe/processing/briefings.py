"""Briefings, built on request from stored scores, holds, alerts, and reports.

`site_briefing` backs GET /sites/{id}/briefing (Today tab). `next_day_briefing`
backs GET /briefings/next-day and the 6 PM push. Swap the templated text for an
LLM summary here without touching the API.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..contracts.api import (DailyBriefing, DailyBriefingItem, LightningHold, SiteBriefing, SiteBriefingEvent)
from ..contracts.common import HazardType, RiskLevel, utcnow
from ..contracts.events import HazardScore
from ..storage.repository import Repository

FLORIDA = ZoneInfo("America/New_York")

GUIDANCE = {
    HazardType.lightning: "Stop work when strikes are within 10 mi. Shelter in trucks or a building.",
    HazardType.heat: "Rest 15 min in shade every 45 min. Drink water every 15-20 min.",
    HazardType.flood: "Avoid low vaults and trenches. Don't drive through standing water.",
    HazardType.soil_saturation: "Shore excavations deeper than 5 ft. Keep equipment off soft ground.",
    HazardType.wildfire: "No hot work near dry vegetation. Keep extinguishers on trucks.",
    HazardType.wildlife: "Keep 30 ft away and report the location to the crew lead.",
    HazardType.other: "Review with the crew lead before starting work.",
}
NAMES = {
    HazardType.lightning: "lightning", HazardType.heat: "heat", HazardType.flood: "flooding",
    HazardType.soil_saturation: "soil saturation", HazardType.wildfire: "wildfire risk",
    HazardType.wildlife: "wildlife", HazardType.other: "other hazards",
}


def _hold_event(hold: LightningHold, now: datetime) -> SiteBriefingEvent:
    remaining = max(0, round((hold.last_strike_at + timedelta(seconds=hold.all_clear_interval) - now).total_seconds() / 60))
    return SiteBriefingEvent(
        id=f"{hold.site_id}-hold", type=HazardType.lightning,
        title=f"Lightning {hold.last_distance_miles:.1f} mi {hold.last_direction or ''}".strip(),
        detail=f"Work is stopped. Shelter in trucks or a building until the all-clear, about {remaining} min.",
        time=hold.last_strike_at, is_active=True)


async def site_briefing(repo: Repository, site_id: int) -> SiteBriefing | None:
    site = await repo.get_site(site_id)
    if site is None:
        return None
    now = utcnow()
    score = await repo.latest_score(site_id)
    hold = await repo.get_hold(site_id)
    conditions = await repo.latest_conditions(site_id)
    alerts = await repo.list_alerts("system", [site_id], now - timedelta(hours=12), 20)

    # Order: active hold, current factors (highest first), then recent alerts (newest first).
    events: list[SiteBriefingEvent] = []
    if hold:
        events.append(_hold_event(hold, now))
    for factor in (score.factors if score else []):
        if factor.score < 4 or (hold and factor.type == HazardType.lightning):
            continue
        events.append(SiteBriefingEvent(id=f"{site_id}-{factor.type}", type=factor.type, title=factor.detail,
                                        detail=GUIDANCE[HazardType(factor.type)], time=score.computed_at,
                                        is_active=True))
    recent = []
    for alert in alerts:
        if alert.type == HazardType.lightning:
            continue
        recent.append(SiteBriefingEvent(id=f"alert-{alert.id}", type=alert.type, title=alert.title,
                                        detail=alert.message, time=alert.issued_at,
                                        is_active=now - alert.issued_at < timedelta(hours=3)))
    events += sorted(recent, key=lambda e: (not e.is_active, -e.time.timestamp()))

    sources = [f"Hazard model {score.model_version}" if score else "Hazard model"]
    if conditions:
        sources.append("Open-Meteo" if conditions.source in {"open-meteo", "dummy"} else conditions.source)
    if any(a.source == "NWS" for a in alerts):
        sources.append("NWS")
    if hold:
        sources.append("Lightning network")
    if any(a.source == "Crew report" for a in alerts):
        sources.append("Crew reports")

    return SiteBriefing(site_id=site_id, headline=_headline(score, hold), sources=sources,
                        updated_at=score.computed_at if score else now, events=events[:8],
                        tomorrow_outlook=(score.forecast_headline or "similar conditions") if score else "no forecast yet")


def _headline(score: HazardScore | None, hold: LightningHold | None) -> str:
    if score is None:
        return "Waiting for the first readings from this site."
    level = RiskLevel.from_index(score.hazard_index).value.capitalize()
    top = [NAMES[HazardType(f.type)] for f in score.factors[:2] if f.score >= 3]
    driven = f", driven mostly by {' and '.join(top)}" if top else ""
    prefix = "Lightning hold in effect. " if hold else ""
    stale = " Data is delayed; treat the index as approximate." if score.data_stale else ""
    return f"{prefix}{level} risk today{driven}.{stale}"


async def next_day_briefing(repo: Repository, site_ids: list[int] | None, limit: int = 8) -> DailyBriefing:
    scores = await repo.latest_scores()
    sites = {s.id: s for s in await repo.list_sites()}
    pool = [s for sid, s in scores.items() if s.forecast_index is not None and (not site_ids or sid in site_ids)]
    pool.sort(key=lambda s: s.forecast_index, reverse=True)
    items = [DailyBriefingItem(site_id=s.site_id, forecast_index=s.forecast_index,
                               headline=s.forecast_headline or "Similar conditions") for s in pool[:limit]]

    tomorrow = (datetime.now(FLORIDA) + timedelta(days=1)).date()
    for_date = datetime.combine(tomorrow, time(6, 0), FLORIDA).astimezone(UTC)
    high = [s for s in pool if s.forecast_index >= 5.5]
    if pool:
        worst = pool[0]
        name = sites[worst.site_id].name if worst.site_id in sites else f"Site {worst.site_id}"
        summary = (f"{len(high)} of {len(pool)} sites forecast high or severe risk tomorrow. "
                   f"Highest: {name} at {worst.forecast_index:.1f}.")
    else:
        summary = "No forecast available yet."
    return DailyBriefing(for_date=for_date, summary=summary, items=items)
