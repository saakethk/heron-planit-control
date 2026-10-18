"""Extracts historical daily weather features from Open-Meteo for given coordinates and dates."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

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


def get_openmeteo_client(cache_dir: Optional[Union[str, Path]] = None) -> openmeteo_requests.Client:
    """Initializes cached, retry-enabled Open-Meteo API client."""
    if cache_dir is None:
        cache_path = Path(__file__).resolve().parent.parent.parent / "data" / ".weather_cache"
    else:
        cache_path = Path(cache_dir) / ".weather_cache"

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(str(cache_path), expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.3)
    return openmeteo_requests.Client(session=retry_session)


def fetch_weather_for_record(
    client: openmeteo_requests.Client,
    record_id: Union[str, int],
    latitude: float,
    longitude: float,
    date_str: str,
) -> Optional[Dict]:
    """Fetches weather metrics for a single coordinate and date.

    Returns dict with 'ID' and all 20 weather feature values.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": str(date_str),
        "end_date": str(date_str),
        "daily": DAILY_VARIABLES,
    }

    try:
        responses = client.weather_api(OPEN_METEO_ARCHIVE_URL, params=params)
        if not responses:
            return None

        daily = responses[0].Daily()
        row = {"ID": str(record_id)}

        for i, var_name in enumerate(DAILY_VARIABLES):
            vals = daily.Variables(i).ValuesAsNumpy()
            row[var_name] = float(vals[0]) if len(vals) > 0 else None

        return row
    except Exception as exc:
        print(f"[WEATHER:ERROR] ID {record_id} ({latitude}, {longitude}, {date_str}): {exc}")
        return None


def fetch_weather_batch(
    records_df: pd.DataFrame,
    client: Optional[openmeteo_requests.Client] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """Iterates through records and extracts daily weather features linked by ID."""
    if client is None:
        client = get_openmeteo_client()

    df = records_df.head(limit) if limit else records_df
    results = []
    total = len(df)

    print(f"[WEATHER] Starting extraction for {total:,} locations...")
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        weather_row = fetch_weather_for_record(
            client=client,
            record_id=row["ID"],
            latitude=row["Latitude"],
            longitude=row["Longitude"],
            date_str=row["Date"],
        )
        if weather_row:
            results.append(weather_row)

        if idx % 100 == 0 or idx == total:
            print(f"[WEATHER] Progress: {idx:,} / {total:,} ({idx / total * 100:.1f}%)")

    weather_df = pd.DataFrame(results)
    return weather_df
