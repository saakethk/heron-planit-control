"""Open-Meteo forecast API (free, no key). One request covers up to ~100 sites.

Fields requested here are what `processing/transformer.py::normalize_open_meteo`
reads. Keep the two in sync.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from ...contracts.common import utcnow
from ...contracts.events import RawObservation
from ...storage.models import SiteRecord

URL = "https://api.open-meteo.com/v1/forecast"
BATCH = 100
PARAMS = {
    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation",
    "hourly": "precipitation,cape,soil_moisture_0_to_1cm",
    "daily": "temperature_2m_max,apparent_temperature_max,precipitation_sum,"
             "precipitation_probability_max,wind_gusts_10m_max",
    "past_hours": 24,
    "forecast_hours": 24,
    "past_days": 7,
    "forecast_days": 2,
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
    "timezone": "GMT",
}


class OpenMeteoSource:
    name = "open-meteo"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def fetch(self, sites: list[SiteRecord], at: datetime | None = None) -> list[RawObservation]:
        fetched_at = utcnow()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            batches = [sites[i:i + BATCH] for i in range(0, len(sites), BATCH)]
            results = await asyncio.gather(*(self._batch(client, b) for b in batches))
        return [RawObservation(source=self.name, site_id=site.id, fetched_at=fetched_at, payload=payload)
                for batch in results for site, payload in batch]

    async def _batch(self, client: httpx.AsyncClient, sites: list[SiteRecord]) -> list[tuple[SiteRecord, dict]]:
        params = dict(PARAMS,
                      latitude=",".join(f"{s.latitude:.4f}" for s in sites),
                      longitude=",".join(f"{s.longitude:.4f}" for s in sites))
        response = await client.get(URL, params=params)
        response.raise_for_status()
        body = response.json()
        payloads = body if isinstance(body, list) else [body]
        return list(zip(sites, payloads))
