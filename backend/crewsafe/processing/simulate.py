"""Scripted events for the live pipeline (Settings → Simulate, or the server
prompt: `python -m crewsafe.prompt`).

Each kind is published onto the same topics the real feeds use, so scoring,
holds, alerts, the WebSocket, and notifications all run as they would for
an Open-Meteo / NWS / GLM observation. Simulated lightning holds last 60
seconds so the all-clear is visible in a demo.
"""

from __future__ import annotations

import re
from datetime import timedelta

from ..contracts.api import HazardAlert, SimulateIn, SimulateOut
from ..contracts.common import AlertSeverity, HazardType, utcnow
from ..contracts.events import RawLightningStrike, SiteNwsAlert
from ..geo import COMPASS_BEARING, offset
from ..messaging import topics
from ..runtime import Pipeline
from ..storage.models import SiteRecord

SIM_HOLD_SECONDS = 60.0
HEAT_TEMP_F = 108.0
HEAT_INDEX_F = 113.0
FLOOD_RAIN_IN = 3.5
DEFAULT_SITE_ID = 664  # John R Kelly, Gainesville

KINDS = ("lightning", "heat", "flood", "briefing", "clear")
KIND_WORDS = {
    "lightning": "lightning", "strike": "lightning", "storm": "lightning", "glm": "lightning",
    "flood": "flood", "flooding": "flood", "rain": "flood",
    "heat": "heat", "temperature": "heat", "hot": "heat",
    "briefing": "briefing", "brief": "briefing", "tomorrow": "briefing", "outlook": "briefing",
    "clear": "clear", "allclear": "clear",
}

_MILES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mi|miles?)\b", re.I)
_SITE_ID = re.compile(r"\b(?:site\s*)?(\d{3,6})\b")
_AT = re.compile(r"\b(?:at|for|near|on)\s+(.+)$", re.I)


def parse_prompt(text: str, sites: list[SiteRecord] | None = None,
                 default_site_id: int = DEFAULT_SITE_ID) -> SimulateIn:
    """Turn a line like 'lightning 4 miles from Turkey Point' into a SimulateIn."""
    raw = " ".join((text or "").strip().split())
    if not raw:
        raise ValueError("empty prompt")
    lowered = raw.lower().replace("next-day", "briefing").replace("next day", "briefing")
    lowered = lowered.replace("6 pm", "briefing").replace("6pm", "briefing").replace("all-clear", "clear")
    kind = next((kind for word, kind in KIND_WORDS.items() if re.search(rf"\b{word}\b", lowered)), None)
    if kind is None:
        raise ValueError(f"could not tell what to simulate in {text!r}; try lightning, flood, or briefing")
    miles = 4.0
    if m := _MILES.search(raw):
        miles = max(0.1, min(30.0, float(m.group(1))))
    site_id = default_site_id if kind != "clear" else None
    if m := _SITE_ID.search(raw):
        site_id = int(m.group(1))
    elif sites and (at := _AT.search(raw)):
        site_id = _match_site(at.group(1), sites) or site_id
    elif sites and kind != "clear":
        leftover = re.sub(r"\b(simulate|send|trigger|please|a|an|the|to|from)\b", " ", lowered, flags=re.I)
        leftover = re.sub(r"\b(" + "|".join(KIND_WORDS) + r")\b", " ", leftover)
        leftover = _MILES.sub(" ", leftover)
        leftover = " ".join(leftover.split())
        if leftover:
            site_id = _match_site(leftover, sites) or site_id
    return SimulateIn(kind=kind, site_id=site_id, miles=miles, prompt=text)


def _match_site(query: str, sites: list[SiteRecord]) -> int | None:
    key = "".join(ch for ch in query.lower() if ch.isalnum() or ch.isspace()).strip()
    if not key:
        return None
    compact = key.replace(" ", "")
    hits = [s for s in sites if compact in "".join(ch for ch in s.name.lower() if ch.isalnum())
            or compact in "".join(ch for ch in s.county.lower() if ch.isalnum())]
    if not hits:
        return None
    hits.sort(key=lambda s: (s.name.lower() != key, len(s.name)))
    return hits[0].id


async def run(p: Pipeline, body: SimulateIn) -> SimulateOut:
    if body.prompt:
        parsed = parse_prompt(body.prompt, await p.repo.list_sites(), DEFAULT_SITE_ID)
        body = SimulateIn(kind=body.kind or parsed.kind,
                          site_id=parsed.site_id if body.site_id is None else body.site_id,
                          miles=parsed.miles if _MILES.search(body.prompt) else body.miles,
                          prompt=body.prompt)
    kind = body.kind.lower().strip()
    if kind == "clear":
        return await _clear(p, body.site_id)
    if kind == "briefing":
        return await _briefing(p, body.site_id)
    if body.site_id is None:
        raise ValueError("site_id is required")
    site = await p.repo.get_site(body.site_id)
    if site is None:
        raise KeyError(body.site_id)
    if kind == "lightning":
        return await _lightning(p, site.id, site.latitude, site.longitude, body.miles)
    if kind == "heat":
        return await _weather(p, site.id, heat=True)
    if kind == "flood":
        return await _weather(p, site.id, flood=True)
    raise ValueError(f"unknown kind {body.kind!r}; use lightning, heat, flood, briefing, or clear")


async def _lightning(p: Pipeline, site_id: int, lat: float, lon: float, miles: float) -> SimulateOut:
    now = utcnow()
    bearing = COMPASS_BEARING["SW"]
    strike_lat, strike_lon = offset(lat, lon, miles, bearing)
    await p.bus.publish(topics.RAW_LIGHTNING, RawLightningStrike(
        strike_id=f"sim-{site_id}-{int(now.timestamp())}",
        latitude=strike_lat, longitude=strike_lon, occurred_at=now, source="simulate"),
        key=str(site_id))
    await p.drain()
    hold = await p.repo.get_hold(site_id)
    if hold and hold.all_clear_interval != SIM_HOLD_SECONDS:
        hold = hold.model_copy(update={"all_clear_interval": SIM_HOLD_SECONDS})
        await p.repo.upsert_hold(hold)
    score = await p.repo.latest_score(site_id)
    return SimulateOut(
        kind="lightning", site_id=site_id, active_hold=hold is not None,
        hazard_index=score.hazard_index if score else None,
        detail=f"Lightning {miles:.1f} mi SW of the site. Stop-work hold started (all-clear in 60 s).")


async def _weather(p: Pipeline, site_id: int, heat: bool = False, flood: bool = False) -> SimulateOut:
    current = await p.repo.latest_conditions(site_id)
    if current is None:
        raise RuntimeError("no weather for this site yet; wait for the first Open-Meteo poll")
    now = utcnow()
    inputs = dict(current.model_inputs or {})
    updates: dict = {"obs_time": now, "source": "simulate", "data_stale": False, "forecast": current.forecast}
    if heat:
        updates.update(temperature_f=HEAT_TEMP_F, heat_index_f=HEAT_INDEX_F, humidity_pct=max(current.humidity_pct, 55))
        inputs.update(temperature_2m_max=45.0, temperature_2m_mean=42.0,
                      apparent_temperature_max=45.0, apparent_temperature_mean=43.0)
    if flood:
        updates.update(rain_24h_in=FLOOD_RAIN_IN, rain_3d_in=max(current.rain_3d_in, FLOOD_RAIN_IN),
                       rain_7d_in=max(current.rain_7d_in, FLOOD_RAIN_IN), precip_1h_in=0.4,
                       weather_code=63)
        inputs.update(precipitation_sum=FLOOD_RAIN_IN * 25.4, rain_sum=FLOOD_RAIN_IN * 25.4,
                      precipitation_hours=8.0, weather_code=63.0)
    updates["model_inputs"] = inputs
    first = current.model_copy(update=updates)
    await p.repo.save_conditions(first)
    await p.bus.publish(topics.CLEAN_CONDITIONS, first, key=site_id)
    await p.drain()
    # Score alerts use hysteresis (2 consecutive readings over the threshold).
    second = first.model_copy(update={"obs_time": now + timedelta(seconds=1)})
    await p.repo.save_conditions(second)
    await p.bus.publish(topics.CLEAN_CONDITIONS, second, key=site_id)
    await p.drain()
    if flood:
        await p.bus.publish(topics.CLEAN_NWS_ALERTS, SiteNwsAlert(
            site_id=site_id, alert_id=f"sim-flood-{site_id}-{int(now.timestamp())}",
            event="Flood Warning", severity="Severe",
            headline="Simulated flood warning after heavy rain",
            description=f"{FLOOD_RAIN_IN:.1f} in. of rain in 12 hours. Low-lying access roads may be impassable.",
            onset=now, expires=now + timedelta(hours=6)), key=site_id)
        await p.drain()
    score = await p.repo.latest_score(site_id)
    latest = await p.repo.latest_conditions(site_id)
    if heat:
        detail = f"Heat index raised to {HEAT_INDEX_F:.0f}°F. Hazard index is now {score.hazard_index if score else '?'}."
    else:
        detail = f"Rain raised to {FLOOD_RAIN_IN:.1f} in. and a Flood Warning was issued."
    return SimulateOut(
        kind="heat" if heat else "flood", site_id=site_id, detail=detail,
        hazard_index=score.hazard_index if score else None,
        heat_index_f=latest.heat_index_f if latest else None,
        rain24h_in=latest.rain_24h_in if latest else None)


async def _briefing(p: Pipeline, site_id: int | None) -> SimulateOut:
    """Push tomorrow's 6 PM briefing as an alert so the app notifies."""
    from .briefings import next_day_briefing

    ids = [site_id] if site_id is not None else None
    briefing = await next_day_briefing(p.repo, ids)
    target = site_id or (briefing.items[0].site_id if briefing.items else DEFAULT_SITE_ID)
    if await p.repo.get_site(target) is None:
        raise KeyError(target)
    await p.alerts.issue(HazardAlert(
        id=f"briefing-{target}-{int(utcnow().timestamp())}", site_id=target, type=HazardType.other,
        severity=AlertSeverity.warning, title="Tomorrow's safety briefing",
        message=briefing.summary, issued_at=utcnow(), source="Briefing"),
        reason="simulated next-day briefing")
    await p.drain()
    return SimulateOut(kind="briefing", site_id=target, detail=briefing.summary)


async def _clear(p: Pipeline, site_id: int | None) -> SimulateOut:
    holds = await p.repo.list_holds()
    if site_id is not None:
        holds = [h for h in holds if h.site_id == site_id]
    for hold in holds:
        await p.lightning._clear(hold, utcnow())
    await p.drain()
    who = f"site {site_id}" if site_id is not None else f"{len(holds)} site(s)"
    return SimulateOut(kind="clear", site_id=site_id, detail=f"Cleared lightning holds for {who}.")
