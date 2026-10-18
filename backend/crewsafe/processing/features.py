"""Shared feature module: the ONE place features are computed.

Model training (in `model/`) must import `build_features` and `FEATURE_COLUMNS`
from here so training and serving use identical inputs. Adding a feature means
adding it here and retraining.
"""

from __future__ import annotations

import math

from ..contracts.events import CleanConditions, Forecast
from ..storage.models import SiteRecord

FEATURE_COLUMNS = [
    "temperature_f", "humidity_pct", "heat_index_f", "wind_mph", "wind_gust_mph",
    "precip_1h_in", "rain_24h_in", "rain_3d_in", "rain_7d_in", "cape", "soil_moisture_pct",
    "drought_index", "river_stage_ft_above_flood", "tide_ft_above_mhhw",
    "nearest_strike_miles", "strikes_30min",
    "coastal", "near_river", "elevation_ft", "wildlife_habitat",
]

# Values used when an input is missing. Trees handle NaN, but explicit defaults
# keep the dummy model and the real one consistent.
MISSING = {"river_stage_ft_above_flood": -10.0, "tide_ft_above_mhhw": -2.0, "nearest_strike_miles": 99.0}


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


def build_features(c: CleanConditions, site: SiteRecord, nearest_strike_miles: float | None,
                   strikes_30min: int) -> dict[str, float]:
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
    }
    return {k: float(MISSING[k] if v is None else v) for k, v in row.items()}


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
    })
    return row
