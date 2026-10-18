"""National Weather Service active alerts for Florida (api.weather.gov, no key,
but a descriptive User-Agent is required). Most alerts are zone/county based and
carry SAME county codes instead of a polygon; the transformer matches either one
to site coordinates or counties."""

from __future__ import annotations

from datetime import datetime

import httpx

from ...contracts.events import RawNwsAlert

URL = "https://api.weather.gov/alerts/active"
# Beach and marine products don't apply to crews at inland or waterfront plants.
IGNORED_EVENTS = ("rip current", "high surf", "beach hazard", "small craft", "marine", "gale", "hazardous seas",
                  "brisk wind", "low water")


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class NwsAlertSource:
    name = "nws"

    def __init__(self, user_agent: str, area: str = "FL") -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/geo+json"}
        self._area = area

    async def fetch(self) -> list[RawNwsAlert]:
        async with httpx.AsyncClient(timeout=20.0, headers=self._headers) as client:
            response = await client.get(URL, params={"area": self._area, "status": "actual"})
            response.raise_for_status()
        alerts = []
        for feature in response.json().get("features", []):
            p = feature.get("properties", {})
            event = p.get("event", "Alert")
            if any(word in event.lower() for word in IGNORED_EVENTS):
                continue
            alerts.append(RawNwsAlert(
                alert_id=p.get("id") or feature.get("id"),
                event=event,
                severity=p.get("severity", "Unknown"),
                headline=p.get("headline") or event,
                description=(p.get("description") or "")[:2000],
                onset=_time(p.get("onset") or p.get("effective")),
                expires=_time(p.get("ends") or p.get("expires")),
                geometry=feature.get("geometry"),
                same_codes=(p.get("geocode") or {}).get("SAME") or [],
            ))
        return alerts
