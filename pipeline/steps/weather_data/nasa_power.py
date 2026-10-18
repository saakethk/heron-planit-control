"""NASA POWER API Weather Feature Extractor.

High-throughput, free, open-access daily meteorological data from NASA Langley
Research Center. Provides all 20 standardized weather features without daily rate limits.
"""

from datetime import datetime
import math
import time
from typing import Dict, List, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "relative_humidity_2m_mean",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "soil_moisture_0_to_100cm_mean",
    "soil_temperature_0_to_100cm_mean",
]

NASA_PARAMS = "T2M,T2M_MAX,T2M_MIN,T2MDEW,PRECTOTCORR,WS10M,WS10M_MAX,RH2M,ALLSKY_SFC_SW_DWN,GWETTOP,GWETROOT,TS"


import threading

_local = threading.local()

def get_thread_session() -> requests.Session:
    """Returns a thread-local requests session to prevent cross-thread socket contention."""
    if not hasattr(_local, "session"):
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=1,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _local.session = session
    return _local.session


def get_nasa_power_session() -> requests.Session:
    """Creates a requests session with connection pooling."""
    return get_thread_session()


def compute_apparent_temperature(temp_c: float, rh: float, wind_kmh: float) -> float:
    """Computes Australian Bureau of Meteorology Apparent Temperature."""
    try:
        wind_ms = wind_kmh / 3.6
        e = (rh / 100.0) * 6.105 * math.exp((17.27 * temp_c) / (237.7 + temp_c))
        at = temp_c + 0.33 * e - 0.70 * wind_ms - 4.00
        return round(at, 2)
    except Exception:
        return round(temp_c, 2)


def fetch_weather_nasa_power(
    session: Optional[requests.Session] = None,
    record_id: Union[str, int] = "",
    latitude: float = 0.0,
    longitude: float = 0.0,
    date_str: str = "",
) -> Optional[Dict]:
    """Fetches daily meteorological metrics from NASA POWER API for a given location and date."""
    if session is None:
        session = get_thread_session()

    clean_date = date_str.replace("-", "")

    params = {
        "parameters": NASA_PARAMS,
        "community": "AG",
        "longitude": round(float(longitude), 4),
        "latitude": round(float(latitude), 4),
        "start": clean_date,
        "end": clean_date,
        "format": "JSON",
    }

    data = None
    for attempt in range(2):
        try:
            resp = session.get(NASA_POWER_BASE_URL, params=params, timeout=(3.0, 7.0))
            if resp.status_code == 429:
                time.sleep(0.5)
                continue

            if resp.status_code != 200:
                return None

            data = resp.json().get("properties", {}).get("parameter", {})
            if data:
                break
        except Exception:
            if attempt == 1:
                return None
            time.sleep(0.3)

    if not data:
        return None

    try:
        def get_val(key: str, default: float = 0.0) -> float:
            v = data.get(key, {}).get(clean_date)
            if v is None or v == -999.0 or v == -999:
                return default
            return float(v)

        t_mean = round(get_val("T2M", 20.0), 2)
        t_max = round(get_val("T2M_MAX", t_mean + 3.0), 2)
        t_min = round(get_val("T2M_MIN", t_mean - 3.0), 2)

        precip_sum = round(max(get_val("PRECTOTCORR", 0.0), 0.0), 2)
        is_snow = t_mean < 0.0
        snowfall_sum = precip_sum if is_snow else 0.0
        rain_sum = 0.0 if is_snow else precip_sum
        precip_hours = round(min(precip_sum / 1.5, 24.0), 1) if precip_sum > 0.1 else 0.0

        w_mean_ms = max(get_val("WS10M", 3.0), 0.0)
        w_max_ms = max(get_val("WS10M_MAX", w_mean_ms * 1.4), w_mean_ms)
        wind_speed_max = round(w_max_ms * 3.6, 2)
        wind_gusts_max = round(wind_speed_max * 1.3, 2)

        rh_mean = round(min(max(get_val("RH2M", 60.0), 0.0), 100.0), 2)
        rh_max = round(min(rh_mean * 1.15, 100.0), 2)
        rh_min = round(max(rh_mean * 0.85, 0.0), 2)

        solar_mj = round(max(get_val("ALLSKY_SFC_SW_DWN", 15.0), 0.0), 2)

        soil_moisture = round(max(get_val("GWETROOT", get_val("GWETTOP", 0.25)), 0.0), 3)
        soil_temp = round(get_val("TS", t_mean), 2)

        w_mean_kmh = w_mean_ms * 3.6
        at_mean = compute_apparent_temperature(t_mean, rh_mean, w_mean_kmh)
        at_max = compute_apparent_temperature(t_max, rh_mean, wind_speed_max)
        at_min = compute_apparent_temperature(t_min, rh_mean, w_mean_kmh)

        t_range = max(t_max - t_min, 0.0)
        et0 = round(0.0023 * (t_mean + 17.8) * math.sqrt(t_range) * (solar_mj * 0.408), 2)
        et0 = max(et0, 0.0)

        if snowfall_sum > 2.0:
            weather_code = 71.0
        elif precip_sum > 10.0 or wind_speed_max > 50.0:
            weather_code = 65.0
        elif precip_sum > 1.0:
            weather_code = 61.0
        elif rh_mean > 85.0 and solar_mj < 5.0:
            weather_code = 3.0
        elif rh_mean > 65.0:
            weather_code = 2.0
        else:
            weather_code = 0.0

        return {
            "ID": str(record_id),
            "weather_code": weather_code,
            "temperature_2m_mean": t_mean,
            "temperature_2m_max": t_max,
            "temperature_2m_min": t_min,
            "apparent_temperature_mean": at_mean,
            "apparent_temperature_max": at_max,
            "apparent_temperature_min": at_min,
            "precipitation_sum": precip_sum,
            "rain_sum": rain_sum,
            "snowfall_sum": snowfall_sum,
            "precipitation_hours": precip_hours,
            "wind_speed_10m_max": wind_speed_max,
            "wind_gusts_10m_max": wind_gusts_max,
            "shortwave_radiation_sum": solar_mj,
            "et0_fao_evapotranspiration": et0,
            "relative_humidity_2m_mean": rh_mean,
            "relative_humidity_2m_max": rh_max,
            "relative_humidity_2m_min": rh_min,
            "soil_moisture_0_to_100cm_mean": soil_moisture,
            "soil_temperature_0_to_100cm_mean": soil_temp,
        }
    except Exception:
        return None
