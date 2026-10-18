"""Extracts verified historical coastal/tide gauge flood events from NOAA CO-OPS API (2015-2025)."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests
import pandas as pd

NOAA_STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels"
NOAA_HTF_URL = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/htf/htf_daily.json"

DEFAULT_START_DATE = "20150101"
DEFAULT_END_DATE = "20251130"


def get_coastal_stations(state_filter: Optional[str] = None) -> List[Dict]:
    """Retrieves metadata for NOAA tide stations."""
    resp = requests.get(NOAA_STATIONS_URL, timeout=15)
    resp.raise_for_status()
    stations = resp.json().get("stations", [])
    if state_filter:
        stations = [s for s in stations if s.get("state") == state_filter]
    return stations


def fetch_station_floods(
    station_id: str,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> List[Dict]:
    """Fetches days where water levels breached flood thresholds for a station."""
    params = {
        "station": str(station_id),
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        resp = requests.get(NOAA_HTF_URL, params=params, timeout=20)
        if resp.status_code != 200:
            return []

        data = resp.json()
        stn_id = data.get("stnId", str(station_id))
        lat = round(float(data.get("lat", 0.0)), 4)
        lon = round(float(data.get("lon", 0.0)), 4)

        flood_days = []
        for item in data.get("DailyFloodCount", []):
            # Check if minor, moderate, or major flood threshold was breached
            if item.get("minFlag") == 1 or item.get("modFlag") == 1 or item.get("majFlag") == 1:
                dt = datetime.strptime(item["day"], "%m/%d/%Y")
                iso_date = dt.strftime("%Y-%m-%d")
                flood_days.append(
                    {
                        "ID": f"NOAA_FLD_{stn_id}_{dt.strftime('%Y%m%d')}",
                        "Latitude": lat,
                        "Longitude": lon,
                        "Date": iso_date,
                        "incident_type": "Flood",
                        "is_incident": True,
                    }
                )
        return flood_days
    except Exception as exc:
        return []


def extract_noaa_floods(
    state_filter: Optional[str] = None,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    max_workers: int = 12,
) -> pd.DataFrame:
    """Extracts all 2015-2025 flood events across coastal stations nationwide."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    stations = get_coastal_stations(state_filter=state_filter)
    scope_str = state_filter if state_filter else "NATIONWIDE (ALL US COASTS)"
    print(f"[NOAA:FLOOD] Found {len(stations)} coastal water level stations ({scope_str})")

    all_records = []
    completed_stations = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_station = {
            executor.submit(
                fetch_station_floods,
                station_id=s["id"],
                start_date=start_date,
                end_date=end_date,
            ): s
            for s in stations
        }

        for future in as_completed(future_to_station):
            completed_stations += 1
            stn = future_to_station[future]
            try:
                records = future.result()
                if records:
                    all_records.extend(records)
            except Exception:
                pass

            if completed_stations % 50 == 0 or completed_stations == len(stations):
                print(
                    f"[NOAA:FLOOD] Scanned {completed_stations}/{len(stations)} stations "
                    f"({len(all_records):,} flood incidents detected so far)..."
                )

    df = pd.DataFrame(all_records)
    if not df.empty:
        df = df.drop_duplicates(subset=["ID"]).reset_index(drop=True)
    print(f"[NOAA:FLOOD] Nationwide extraction complete: {len(df):,} total flood events collected.")
    return df


if __name__ == "__main__":
    floods = extract_noaa_floods()
    print(floods.head())
