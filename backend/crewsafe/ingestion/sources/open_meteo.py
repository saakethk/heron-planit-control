"""Open-Meteo forecast API (no key needed). The free tier allows 600 calls a
minute and 10,000 a day, where each location counts once per 10 variables.
The defaults (0.1° grid = 223 locations, current conditions every 45 min, model
inputs every 6 h) stay close to the daily limit; with OPEN_METEO_API_KEY, poll
as often as you like. Requests are paced to the per-minute limit.

Two request kinds, refreshed on different schedules:

- **current** (every WEATHER_INTERVAL): current conditions plus hourly rain and
  CAPE, in imperial units for the app. The startup request also includes every
  current variable hourly for the past 24 hours so the index chart can be backfilled.
- **model** (every MODEL_INPUTS_INTERVAL, and when the UTC day rolls over): the
  daily aggregates and soil layers the pipeline's classifier was trained on, in
  the archive API's metric units and UTC days, for today and tomorrow.

Sites within WEATHER_GRID_DEG of each other share one location. If a request
fails (for example 429 rate limiting) the last good payloads are reused and the
transformer marks the readings stale once they age out.

Fields requested here are what `processing/transformer.py::normalize_open_meteo`
reads. Keep the two in sync.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from ...config import Settings
from ...contracts.common import utcnow
from ...contracts.events import RawObservation
from ...storage.models import SiteRecord

log = logging.getLogger(__name__)

FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
BATCH = 100
CURRENT_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation,weather_code"
IMPERIAL = {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch", "timezone": "GMT"}
CURRENT_PARAMS = {**IMPERIAL, "current": CURRENT_VARS, "hourly": "precipitation,cape",
                  "past_hours": 24, "forecast_hours": 48}
STARTUP_PARAMS = {**CURRENT_PARAMS, "hourly": f"{CURRENT_VARS},cape"}
# Snowfall is always 0 in Florida; the transformer fills it in rather than paying for it.
MODEL_DAILY = [
    "weather_code", "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_mean", "apparent_temperature_max", "apparent_temperature_min",
    "precipitation_sum", "rain_sum", "precipitation_hours", "precipitation_probability_max",
    "wind_speed_10m_max", "wind_gusts_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
    "relative_humidity_2m_mean", "relative_humidity_2m_max", "relative_humidity_2m_min",
]
# Layers that approximate the 0-100 cm means the model was trained on, weighted by thickness.
SOIL_MOISTURE_LAYERS = {"soil_moisture_3_to_9cm": 9, "soil_moisture_9_to_27cm": 18, "soil_moisture_27_to_81cm": 54}
SOIL_TEMPERATURE_LAYERS = {"soil_temperature_18cm": 36, "soil_temperature_54cm": 64}
MODEL_PARAMS = {"daily": ",".join(MODEL_DAILY), "hourly": ",".join([*SOIL_MOISTURE_LAYERS, *SOIL_TEMPERATURE_LAYERS]),
                "past_days": 7, "forecast_days": 2, "timezone": "GMT"}
# Open-Meteo counts one call per location per 10 variables; the free tier allows 600 a minute.
CALLS_PER_MINUTE = 500

Cell = tuple[int, int]


def _weight(params: dict, locations: int) -> float:
    variables = sum(len(params[k].split(",")) for k in ("current", "hourly", "daily") if k in params)
    return locations * max(1.0, variables / 10)


class OpenMeteoSource:
    name = "open-meteo"

    def __init__(self, settings: Settings, timeout: float = 30.0) -> None:
        self._grid = settings.weather_grid_deg
        self._model_interval = timedelta(seconds=settings.model_inputs_interval)
        self._url = PAID_URL if settings.open_meteo_api_key else FREE_URL
        self._key = settings.open_meteo_api_key
        self._timeout = timeout
        self._current: dict[Cell, dict] = {}
        self._model: dict[Cell, dict] = {}
        self._current_at: datetime | None = None
        self._model_at: datetime | None = None
        self._spent: list[tuple[float, float]] = []  # (monotonic time, weighted calls)

    async def _pace(self, weight: float) -> None:
        """Wait until `weight` more calls fit in the per-minute budget."""
        while True:
            now = time.monotonic()
            self._spent = [(t, w) for t, w in self._spent if now - t < 60]
            used = sum(w for _, w in self._spent)
            if not self._spent or used + weight <= CALLS_PER_MINUTE:
                self._spent.append((now, weight))
                return
            await asyncio.sleep(60 - (now - self._spent[0][0]) + 0.5)

    def _cells(self, sites: list[SiteRecord]) -> dict[Cell, list[SiteRecord]]:
        cells: dict[Cell, list[SiteRecord]] = {}
        for site in sites:
            cells.setdefault((round(site.latitude / self._grid), round(site.longitude / self._grid)), []).append(site)
        return cells

    async def fetch(self, sites: list[SiteRecord], at: datetime | None = None) -> list[RawObservation]:
        cells = self._cells(sites)
        now = utcnow()
        backfill = at is not None and now - at > timedelta(minutes=10)
        recent = self._current_at is not None and now - self._current_at < timedelta(seconds=60)
        model_due = (self._model_at is None or now - self._model_at >= self._model_interval
                     or self._model_at.date() != now.date())
        current_due = not self._current or (not backfill and not recent)
        keys = list(cells)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Batch by batch, both request kinds, so each group of sites is complete
            # before the rate limiter makes the next group wait.
            for start in range(0, len(keys), BATCH):
                batch = {k: cells[k] for k in keys[start:start + BATCH]}
                if current_due or any(k not in self._current for k in batch):
                    first = any(k not in self._current for k in batch)
                    await self._refresh(client, batch, STARTUP_PARAMS if first else CURRENT_PARAMS, model=False)
                if model_due or any(k not in self._model for k in batch):
                    await self._refresh(client, batch, MODEL_PARAMS, model=True)

        observations = []
        for cell, members in cells.items():
            current, model = self._current.get(cell), self._model.get(cell)
            if current is None or model is None:
                continue
            payload = {"current": current["current"], "hourly": current["hourly"], "model": model}
            if backfill:
                payload = _as_of(payload, at)
                if payload is None:
                    continue
            fetched_at = at if backfill else self._current_at
            observations += [RawObservation(source=self.name, site_id=s.id, fetched_at=fetched_at, payload=payload)
                             for s in members]
        return observations

    async def _refresh(self, client: httpx.AsyncClient, cells: dict[Cell, list[SiteRecord]], params: dict,
                       model: bool) -> None:
        batch = list(cells)
        query = dict(params,
                     latitude=",".join(f"{cells[k][0].latitude:.4f}" for k in batch),
                     longitude=",".join(f"{cells[k][0].longitude:.4f}" for k in batch))
        if self._key:
            query["apikey"] = self._key
        else:
            await self._pace(_weight(params, len(batch)))
        try:
            response = await client.get(self._url, params=query)
            if response.status_code != 200:
                reason = response.json().get("reason", response.text[:200]) if response.content else ""
                raise RuntimeError(f"HTTP {response.status_code}: {reason}")
            body = response.json()
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            kind = "model inputs" if model else "current conditions"
            log.warning("Open-Meteo %s request failed (%s); reusing the last good data", kind, exc)
            return
        fresh = dict(zip(batch, body if isinstance(body, list) else [body]))
        if model:
            self._model.update(fresh)
            self._model_at = utcnow()
        else:
            self._current.update(fresh)
            self._current_at = utcnow()


def _as_of(payload: dict, at: datetime) -> dict | None:
    """Payload as it would have looked at a past hour: "current" comes from the
    hourly series. Only the startup request has every current variable hourly,
    which is when backfill runs."""
    hourly = payload["hourly"]
    key = at.astimezone(UTC).strftime("%Y-%m-%dT%H:00")
    if key not in hourly["time"] or "temperature_2m" not in hourly:
        return None
    i = hourly["time"].index(key)
    names = CURRENT_VARS.split(",")
    current = {"time": key, **{name: hourly[name][i] for name in names}}
    if any(current[name] is None for name in names):
        return None
    return {**payload, "current": current}
