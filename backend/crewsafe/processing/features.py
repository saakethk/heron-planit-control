"""Shared feature module: the ONE place serving features are computed.

Two groups of features:

- `FEATURE_COLUMNS`: current-conditions features in app units, used by the rules,
  the factor text, and the dummy/LightGBM models.
- `MODEL_FEATURE_COLUMNS`: the 28 columns the pipeline's classifier was trained on
  (`pipeline/model/dataset.py::FEATURE_COLS`), in the same order and units: daily
  aggregates from Open-Meteo, month harmonics, coordinates, and FEMA flood fields.
  `PipelineHazardModel` checks this list against the pipeline's at load time.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..contracts.events import CleanConditions, Forecast
from ..storage.models import SiteRecord

MM_PER_IN = 25.4
KMH_PER_MPH = 1.609344

# Daily Open-Meteo aggregates (archive API units: °C, mm, km/h, MJ/m², m³/m³).
MODEL_WEATHER_COLUMNS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_mean", "apparent_temperature_max", "apparent_temperature_min",
    "precipitation_sum", "rain_sum", "snowfall_sum", "precipitation_hours",
    "relative_humidity_2m_mean", "relative_humidity_2m_max", "relative_humidity_2m_min",
    "wind_speed_10m_max", "wind_gusts_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
    "soil_moisture_0_to_100cm_mean", "soil_temperature_0_to_100cm_mean", "weather_code",
]
MODEL_FEATURE_COLUMNS = MODEL_WEATHER_COLUMNS + [
    "month_sin", "month_cos", "Latitude", "Longitude",
    "fema_is_sfha", "fema_is_coastal_hazard", "fema_flood_risk_score", "fema_flood_precip_compound",
]
THUNDERSTORM_CODES = {95, 96, 99}

FEATURE_COLUMNS = [
    "temperature_f", "humidity_pct", "heat_index_f", "wind_mph", "wind_gust_mph",
    "precip_1h_in", "rain_24h_in", "rain_3d_in", "rain_7d_in", "cape", "soil_moisture_pct",
    "drought_index", "river_stage_ft_above_flood", "tide_ft_above_mhhw",
    "nearest_strike_miles", "strikes_30min",
    "coastal", "near_river", "elevation_ft", "wildlife_habitat",
]

# Values used when an input is missing. Trees handle NaN, but explicit defaults
# keep the dummy model and the real one consistent.
MISSING = {"river_stage_ft_above_flood": -10.0, "tide_ft_above_mhhw": -2.0, "nearest_strike_miles": 99.0,
           "drought_index": 200.0}


def heat_index_f(temp_f: float, humidity_pct: float) -> float:
    """NWS heat index (Rothfusz regression with the standard adjustments)."""
    t, rh = temp_f, humidity_pct
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        return round(simple, 1)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
          - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round(hi, 1)


def approximate_model_inputs(temperature_f: float, heat_index_f_: float, humidity_pct: float, wind_mph: float,
                             wind_gust_mph: float, rain_24h_in: float, soil_moisture_pct: float,
                             cape: float) -> dict[str, float]:
    """Rough daily aggregates from one reading, for sources without daily data
    (the dummy world). Live Open-Meteo data always supplies the real aggregates."""
    t = (temperature_f - 32) * 5 / 9
    apparent = (heat_index_f_ - 32) * 5 / 9
    rain_mm = rain_24h_in * MM_PER_IN
    return {
        "temperature_2m_mean": t - 2, "temperature_2m_max": t + 1, "temperature_2m_min": t - 6,
        "apparent_temperature_mean": apparent - 2, "apparent_temperature_max": apparent + 1,
        "apparent_temperature_min": apparent - 7,
        "precipitation_sum": rain_mm, "rain_sum": rain_mm, "snowfall_sum": 0.0,
        "precipitation_hours": min(24.0, rain_24h_in * 6),
        "relative_humidity_2m_mean": humidity_pct, "relative_humidity_2m_max": min(100.0, humidity_pct + 15),
        "relative_humidity_2m_min": max(5.0, humidity_pct - 20),
        "wind_speed_10m_max": wind_mph * KMH_PER_MPH * 1.2, "wind_gusts_10m_max": wind_gust_mph * KMH_PER_MPH,
        "shortwave_radiation_sum": 18.0, "et0_fao_evapotranspiration": 4.0,
        "soil_moisture_0_to_100cm_mean": soil_moisture_pct / 100 * 0.45, "soil_temperature_0_to_100cm_mean": t - 2,
        "weather_code": 95.0 if cape > 2500 and rain_24h_in > 0.5 else 61.0 if rain_24h_in > 0.2 else 1.0,
    }


def model_features(inputs: dict[str, float], site: SiteRecord, when: datetime) -> dict[str, float]:
    """The pipeline model's 28 columns for one site and day."""
    row = {name: float(inputs.get(name, 0.0)) for name in MODEL_WEATHER_COLUMNS}
    row.update({
        "month_sin": math.sin(2 * math.pi * when.month / 12.0),
        "month_cos": math.cos(2 * math.pi * when.month / 12.0),
        "Latitude": site.latitude,
        "Longitude": site.longitude,
        "fema_is_sfha": float(site.fema_sfha),
        "fema_is_coastal_hazard": float(site.fema_coastal),
        "fema_flood_risk_score": site.fema_score,
        "fema_flood_precip_compound": site.fema_score * row["precipitation_sum"],
    })
    return row


def build_features(c: CleanConditions, site: SiteRecord, nearest_strike_miles: float | None,
                   strikes_30min: int) -> dict[str, float]:
    inputs = c.model_inputs or approximate_model_inputs(
        c.temperature_f, c.heat_index_f, c.humidity_pct, c.wind_mph, c.wind_gust_mph, c.rain_24h_in,
        c.soil_moisture_pct, c.cape)
    row = {
        "temperature_f": c.temperature_f,
        "humidity_pct": c.humidity_pct,
        "heat_index_f": c.heat_index_f,
        "wind_mph": c.wind_mph,
        "wind_gust_mph": c.wind_gust_mph,
        "precip_1h_in": c.precip_1h_in,
        "rain_24h_in": c.rain_24h_in,
        "rain_3d_in": c.rain_3d_in,
        "rain_7d_in": c.rain_7d_in,
        "cape": c.cape,
        "soil_moisture_pct": c.soil_moisture_pct,
        "drought_index": c.drought_index,
        "river_stage_ft_above_flood": c.river_stage_ft_above_flood,
        "tide_ft_above_mhhw": c.tide_ft_above_mhhw,
        "nearest_strike_miles": nearest_strike_miles,
        "strikes_30min": float(strikes_30min),
        "coastal": float(site.coastal),
        "near_river": float(site.near_river),
        "elevation_ft": site.elevation_ft,
        "wildlife_habitat": site.wildlife_habitat,
        "current_weather_code": c.weather_code,
    }
    row = {k: float(MISSING.get(k, 0.0) if v is None else v) for k, v in row.items()}
    row.update(model_features(inputs, site, c.obs_time))
    return row


def build_forecast_features(f: Forecast, current: CleanConditions, site: SiteRecord) -> dict[str, float]:
    """Tomorrow's features: forecast values where available, today's otherwise."""
    row = build_features(current, site, None, 0)
    row.update({
        "temperature_f": f.max_temp_f,
        "heat_index_f": f.max_heat_index_f,
        "wind_gust_mph": f.max_wind_gust_mph,
        "rain_24h_in": f.precip_in,
        "rain_3d_in": current.rain_24h_in + f.precip_in,
        "cape": f.max_cape * f.precip_probability / 100,
        "current_weather_code": 0.0,
    })
    inputs = f.model_inputs or approximate_model_inputs(
        f.max_temp_f, f.max_heat_index_f, current.humidity_pct, current.wind_mph, f.max_wind_gust_mph, f.precip_in,
        current.soil_moisture_pct, row["cape"])
    row.update(model_features(inputs, site, current.obs_time + timedelta(days=1)))
    return row
