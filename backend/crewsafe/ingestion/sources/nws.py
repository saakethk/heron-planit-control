"""National Weather Service active alerts for Florida (api.weather.gov, no key,
but a descriptive User-Agent is required). Alerts carry a polygon or zone list;
the transformer matches polygons to site coordinates."""

from __future__ import annotations

from datetime import datetime

import httpx

from ...contracts.events import RawNwsAlert

URL = "https://api.weather.gov/alerts/active"


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class NwsAlertSource:
    name = "nws"

    def __init__(self, user_agent: str, area: str = "FL") -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/geo+json"}
        self._area = area

    async def fetch(self) -> list[RawNwsAlert]:
        async with httpx.AsyncClient(timeout=20.0, headers=self._headers) as client:
            response = await client.get(URL, params={"area": self._area})
            response.raise_for_status()
        alerts = []
        for feature in response.json().get("features", []):
            p = feature.get("properties", {})
            alerts.append(RawNwsAlert(
                alert_id=p.get("id") or feature.get("id"),
                event=p.get("event", "Alert"),
                severity=p.get("severity", "Unknown"),
                headline=p.get("headline") or p.get("event", ""),
                description=(p.get("description") or "")[:2000],
                onset=_time(p.get("onset") or p.get("effective")),
                expires=_time(p.get("expires")),
                geometry=feature.get("geometry"),
            ))
        return alerts
