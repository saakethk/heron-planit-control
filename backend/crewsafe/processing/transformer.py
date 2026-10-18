"""Transformer service.

raw.weather    -> validate, normalize units/shape, dedupe on (site_id, obs_time),
                  derive features, flag stale data -> store + clean.conditions
raw.nws.alerts -> match alert areas to sites -> clean.nws.alerts (one per site)

Bad payloads go to the dead-letter topic instead of stopping the consumer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from ..contracts.common import utcnow
from ..contracts.events import CleanConditions, Forecast, RawNwsAlert, RawObservation, SiteNwsAlert
from ..geo import fl_county_same_code, point_in_polygon
from ..ingestion.sources.open_meteo import SOIL_MOISTURE_LAYERS, SOIL_TEMPERATURE_LAYERS
from ..messaging import topics
from ..messaging.bus import MessageBus
from ..storage.repository import Repository
from .features import KMH_PER_MPH, MM_PER_IN, MODEL_WEATHER_COLUMNS, heat_index_f

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=45)
VALID_RANGES = {
    "temperature_f": (-20, 130),
    "humidity_pct": (0, 100),
    "wind_mph": (0, 200),
    "wind_gust_mph": (0, 250),
    "precip_1h_in": (0, 15),
    "rain_24h_in": (0, 40),
    "cape": (0, 10000),
    "soil_moisture_pct": (0, 100),
}
# Volumetric water content treated as fully saturated (sandy Florida soils).
SATURATED_M3_M3 = 0.45


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _c_to_f(c: float) -> float:
    return round(c * 9 / 5 + 32, 1)


def _layer_mean(series: dict[str, list], layers: dict[str, float], hours: Iterable[int]) -> float | None:
    """Thickness-weighted mean over soil layers, averaged over the given hours."""
    values = []
    for h in hours:
        row = [(series[name][h], weight) for name, weight in layers.items() if series[name][h] is not None]
        if row:
            values.append(sum(v * w for v, w in row) / sum(w for _, w in row))
    return sum(values) / len(values) if values else None


def _model_inputs(daily: dict[str, list], soil: dict[str, list], d: int) -> dict[str, float]:
    """One UTC day of the trained model's weather columns, in the archive API's units."""
    day = daily["time"][d]
    hours = [h for h, t in enumerate(soil["time"]) if t.startswith(day)]
    row = {"snowfall_sum": 0.0, **{name: daily[name][d] for name in MODEL_WEATHER_COLUMNS if name in daily}}
    row["soil_moisture_0_to_100cm_mean"] = _layer_mean(soil, SOIL_MOISTURE_LAYERS, hours)
    row["soil_temperature_0_to_100cm_mean"] = _layer_mean(soil, SOIL_TEMPERATURE_LAYERS, hours)
    return {k: float(v) for k, v in row.items() if v is not None}


def normalize_open_meteo_live(payload: dict[str, Any]) -> dict[str, Any]:
    """Live Open-Meteo payload (see ingestion/sources/open_meteo.py) -> flat fields:
    imperial current conditions for the app plus the model's daily inputs."""
    current, hourly = payload["current"], payload["hourly"]
    daily, soil = payload["model"]["daily"], payload["model"]["hourly"]
    obs_time = _parse_time(current["time"])

    hour_key = obs_time.strftime("%Y-%m-%dT%H:00")
    times = hourly["time"]
    i = times.index(hour_key) if hour_key in times else min(23, len(times) - 1)
    precip = [p or 0.0 for p in hourly["precipitation"]]
    days = daily["time"]
    today = obs_time.date().isoformat()
    d = days.index(today) if today in days else len(days) - 2
    rain_mm = [p or 0.0 for p in daily["precipitation_sum"]]
    soil_hour = soil["time"].index(hour_key) if hour_key in soil["time"] else None
    # 3-27 cm: the layer trench walls and footings sit in.
    shallow = _layer_mean(soil, dict(list(SOIL_MOISTURE_LAYERS.items())[:2]), [soil_hour]) \
        if soil_hour is not None else None

    forecast = None
    if d + 1 < len(days):
        tomorrow = days[d + 1]
        cape_tomorrow = [c or 0 for t, c in zip(times, hourly["cape"]) if t.startswith(tomorrow)]
        forecast = Forecast(
            max_temp_f=_c_to_f(daily["temperature_2m_max"][d + 1]),
            max_heat_index_f=_c_to_f(daily["apparent_temperature_max"][d + 1]),
            precip_in=round(rain_mm[d + 1] / MM_PER_IN, 2),
            precip_probability=daily["precipitation_probability_max"][d + 1] or 0,
            max_cape=max(cape_tomorrow, default=0),
            max_wind_gust_mph=round(daily["wind_gusts_10m_max"][d + 1] / KMH_PER_MPH, 1),
            model_inputs=_model_inputs(daily, soil, d + 1),
        )

    return {
        "obs_time": obs_time,
        "temperature_f": current["temperature_2m"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_mph": current["wind_speed_10m"],
        "wind_gust_mph": current.get("wind_gusts_10m") or current["wind_speed_10m"],
        "precip_1h_in": current.get("precipitation") or 0.0,
        "rain_24h_in": round(sum(precip[max(0, i - 23):i + 1]), 2),
        "rain_3d_in": round(sum(rain_mm[max(0, d - 2):d + 1]) / MM_PER_IN, 2),
        "rain_7d_in": round(sum(rain_mm[max(0, d - 6):d + 1]) / MM_PER_IN, 2),
        "cape": hourly["cape"][i] or 0.0,
        "soil_moisture_pct": round(min(100.0, (shallow or 0.0) / SATURATED_M3_M3 * 100), 1),
        "weather_code": current.get("weather_code"),
        "forecast": forecast,
        "model_inputs": _model_inputs(daily, soil, d),
    }


def normalize_open_meteo(payload: dict[str, Any]) -> dict[str, Any]:
    """Open-Meteo-shaped response (imperial units, GMT) -> flat fields. The live
    source adds a "model" block; the dummy world's payload doesn't have one."""
    if "model" in payload:
        return normalize_open_meteo_live(payload)
    current, hourly, daily = payload["current"], payload["hourly"], payload["daily"]
    extras = payload.get("extras") or {}
    obs_time = _parse_time(current["time"])

    hour_key = obs_time.strftime("%Y-%m-%dT%H:00")
    times = hourly["time"]
    i = times.index(hour_key) if hour_key in times else min(23, len(times) - 1)
    precip = [p or 0.0 for p in hourly["precipitation"]]
    soil_m3 = hourly["soil_moisture_0_to_1cm"][i] or 0.0

    days = daily["time"]
    today = obs_time.date().isoformat()
    d = days.index(today) if today in days else len(days) - 2
    rain_daily = [p or 0.0 for p in daily["precipitation_sum"]]

    forecast = None
    if d + 1 < len(days):
        future_cape = [c or 0 for c in hourly["cape"][i + 1:]]
        forecast = Forecast(
            max_temp_f=daily["temperature_2m_max"][d + 1],
            max_heat_index_f=daily["apparent_temperature_max"][d + 1],
            precip_in=rain_daily[d + 1],
            precip_probability=daily["precipitation_probability_max"][d + 1] or 0,
            max_cape=extras.get("tomorrow_max_cape", max(future_cape, default=0)),
            max_wind_gust_mph=daily["wind_gusts_10m_max"][d + 1],
        )

    return {
        "obs_time": obs_time,
        "temperature_f": current["temperature_2m"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_mph": current["wind_speed_10m"],
        "wind_gust_mph": current.get("wind_gusts_10m") or current["wind_speed_10m"],
        "precip_1h_in": current.get("precipitation") or 0.0,
        "rain_24h_in": round(sum(precip[max(0, i - 23):i + 1]), 2),
        "rain_3d_in": round(sum(rain_daily[max(0, d - 2):d + 1]), 2),
        "rain_7d_in": round(sum(rain_daily[max(0, d - 6):d + 1]), 2),
        "cape": hourly["cape"][i] or 0.0,
        "soil_moisture_pct": round(min(100.0, soil_m3 / SATURATED_M3_M3 * 100), 1),
        "drought_index": extras.get("kbdi", 200.0),
        "river_stage_ft_above_flood": extras.get("river_stage_ft_above_flood"),
        "tide_ft_above_mhhw": extras.get("tide_ft_above_mhhw"),
        "forecast": forecast,
    }


# One normalizer per source. The dummy source emits Open-Meteo-shaped payloads.
NORMALIZERS = {"open-meteo": normalize_open_meteo, "dummy": normalize_open_meteo}


def validate(fields: dict[str, Any]) -> None:
    for name, (low, high) in VALID_RANGES.items():
        value = fields.get(name)
        if value is None or not (low <= float(value) <= high):
            raise ValueError(f"{name}={value!r} outside {low}..{high}")


class Transformer:
    def __init__(self, bus: MessageBus, repo: Repository) -> None:
        self.bus, self.repo = bus, repo

    def register(self) -> None:
        self.bus.subscribe([topics.RAW_WEATHER, topics.RAW_NWS_ALERTS], "transformer", self.handle)

    async def handle(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if topic == topics.RAW_WEATHER:
            await self.handle_weather(value)
        elif topic == topics.RAW_NWS_ALERTS:
            await self.handle_nws(value)

    async def handle_weather(self, value: dict[str, Any]) -> None:
        raw = RawObservation(**value)
        normalizer = NORMALIZERS.get(raw.source)
        if normalizer is None:
            await self.bus.dead_letter(topics.RAW_WEATHER, value, f"no normalizer for source {raw.source!r}")
            return
        try:
            fields = normalizer(raw.payload)
            validate(fields)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            await self.bus.dead_letter(topics.RAW_WEATHER, value, f"invalid payload: {exc!r}")
            return

        conditions = CleanConditions(
            site_id=raw.site_id,
            source=raw.source,
            heat_index_f=heat_index_f(fields["temperature_f"], fields["humidity_pct"]),
            data_stale=raw.fetched_at - fields["obs_time"] > STALE_AFTER,
            **fields,
        )
        if await self.repo.save_conditions(conditions):
            await self.bus.publish(topics.CLEAN_CONDITIONS, conditions, key=raw.site_id)

    async def handle_nws(self, value: dict[str, Any]) -> None:
        alert = RawNwsAlert(**value)
        site_ids = alert.site_ids
        if not site_ids and alert.geometry:
            site_ids = [s.id for s in await self.repo.list_sites()
                        if point_in_polygon(s.latitude, s.longitude, alert.geometry)]
        elif not site_ids and alert.same_codes:
            codes = set(alert.same_codes)
            site_ids = [s.id for s in await self.repo.list_sites() if fl_county_same_code(s.county) in codes]
        for site_id in site_ids:
            await self.bus.publish(topics.CLEAN_NWS_ALERTS, SiteNwsAlert(
                site_id=site_id, alert_id=alert.alert_id, event=alert.event, severity=alert.severity,
                headline=alert.headline, description=alert.description, onset=alert.onset, expires=alert.expires,
            ), key=site_id)

    async def flag_stale(self) -> int:
        """Re-publish sites whose latest reading is too old, marked stale, so
        scoring and the app show that the index is not current."""
        now = utcnow()
        count = 0
        for site_id, c in (await self.repo.all_latest_conditions()).items():
            if not c.data_stale and now - c.obs_time > STALE_AFTER:
                stale = c.model_copy(update={"data_stale": True, "obs_time": now})
                if await self.repo.save_conditions(stale):
                    await self.bus.publish(topics.CLEAN_CONDITIONS, stale, key=site_id)
                    count += 1
        return count
