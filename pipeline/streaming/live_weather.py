"""Live Real-Time Meteorological Streaming Client.

Fetches current, live weather observations directly from Open-Meteo's live forecast endpoint:
https://api.open-meteo.com/v1/forecast

Includes:
- Exact ISO-8601 observation timestamp directly from the live feed.
- Instantaneous surface conditions: temperature, apparent temperature (heat index),
  humidity, wind speed, wind gusts, live precipitation rate, and WMO weather codes.
- Zero silent mock data substitution: raises explicit error or failure indicator if feed is unreachable.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import numpy as np
import requests

LIVE_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class LiveWeatherClient:
    """Client for querying real-time instantaneous meteorological conditions."""

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def fetch_current_conditions(self, lat: float, lon: float) -> Dict[str, Any]:
        """Queries the live Open-Meteo API for real-time conditions at a job site.

        Returns a dictionary containing live instantaneous metrics and the exact observation timestamp.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                "apparent_temperature_max,apparent_temperature_min,apparent_temperature_mean,"
                "precipitation_sum,rain_sum,snowfall_sum,precipitation_hours,"
                "wind_speed_10m_max,wind_gusts_10m_max,shortwave_radiation_sum,"
                "et0_fao_evapotranspiration,weather_code"
            ),
            "hourly": (
                "relative_humidity_2m,soil_temperature_0cm,soil_moisture_0_to_1cm"
            ),
            "timezone": "auto",
            "forecast_days": 1,
        }

        resp = requests.get(LIVE_FORECAST_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        if not current:
            raise ValueError(f"No current weather data returned by live API for ({lat}, {lon})")

        # Live instantaneous readings
        obs_time = current.get("time")
        temp_c = current.get("temperature_2m")
        heat_index_c = current.get("apparent_temperature")
        heat_index_f = round(heat_index_c * 9 / 5 + 32, 1) if heat_index_c is not None else None
        humidity = current.get("relative_humidity_2m")
        precip_rate_mm = current.get("precipitation", 0.0)
        wind_speed_kmh = current.get("wind_speed_10m")
        wind_gust_kmh = current.get("wind_gusts_10m")
        wcode = current.get("weather_code", 0)

        # WMO Weather interpretation
        # 95 = Thunderstorm, 96 = Thunderstorm with slight hail, 99 = Severe thunderstorm
        is_thunderstorm = wcode in [95, 96, 99]

        return {
            "observation_timestamp": obs_time,
            "temperature_c": temp_c,
            "apparent_temp_f": heat_index_f,
            "apparent_temp_c": heat_index_c,
            "relative_humidity": humidity,
            "precipitation_rate_mm": precip_rate_mm,
            "wind_speed_kmh": wind_speed_kmh,
            "wind_gusts_kmh": wind_gust_kmh,
            "weather_code": wcode,
            "is_thunderstorm": is_thunderstorm,
            "daily_aggregates": daily,
            "hourly_samples": hourly,
            "elevation_m": data.get("elevation"),
            "timezone": data.get("timezone"),
        }
