"""Extracts verified historical nationwide lightning strikes from NOAA NCEI Storm Events database (2015-2025)."""

import gzip
import io
import re
from typing import List, Optional
import pandas as pd
import requests

NCEI_BASE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"


def list_storm_event_files(
    start_year: int = 2015,
    end_year: int = 2025,
) -> List[str]:
    """Finds all StormEvents_details-ftp_v1.0_d{YYYY}_*.csv.gz files on NCEI server."""
    resp = requests.get(NCEI_BASE_URL, timeout=25)
    resp.raise_for_status()

    pattern = re.compile(r'href=[\"\'](StormEvents_details-ftp_v1\.0_d(\d{4})_[^\"\']+\.csv\.gz)[\"\']')
    matches = pattern.findall(resp.text)

    # Filter for target year range
    selected_files = []
    for filename, year_str in matches:
        year = int(year_str)
        if start_year <= year <= end_year:
            selected_files.append((year, filename))

    # Keep latest file per year if duplicates exist
    latest_by_year = {}
    for year, fname in sorted(selected_files):
        latest_by_year[year] = fname

    return [latest_by_year[y] for y in sorted(latest_by_year.keys())]


def fetch_lightning_from_file(filename: str) -> pd.DataFrame:
    """Streams and extracts lightning records from a single NCEI gzip CSV."""
    file_url = f"{NCEI_BASE_URL}{filename}"
    resp = requests.get(file_url, stream=True, timeout=60)
    resp.raise_for_status()

    with gzip.open(io.BytesIO(resp.content)) as gz:
        # Load only necessary columns to minimize memory
        usecols = ["EVENT_ID", "BEGIN_DATE_TIME", "BEGIN_LAT", "BEGIN_LON", "EVENT_TYPE", "STATE"]
        df = pd.read_csv(gz, usecols=usecols, low_memory=False)

    # Filter for lightning events
    ltg = df[df["EVENT_TYPE"].astype(str).str.lower() == "lightning"].copy()

    # Drop records with missing coordinates or dates
    ltg = ltg.dropna(subset=["BEGIN_LAT", "BEGIN_LON", "BEGIN_DATE_TIME"]).reset_index(drop=True)

    # Parse date to YYYY-MM-DD
    ltg["Date"] = pd.to_datetime(ltg["BEGIN_DATE_TIME"], errors="coerce").dt.strftime("%Y-%m-%d")
    ltg = ltg.dropna(subset=["Date"])

    # Standardize schema
    clean_df = pd.DataFrame(
        {
            "ID": "NOAA_LTG_" + ltg["EVENT_ID"].astype(str),
            "Latitude": ltg["BEGIN_LAT"].astype(float).round(4),
            "Longitude": ltg["BEGIN_LON"].astype(float).round(4),
            "Date": ltg["Date"],
            "incident_type": "Lightning",
            "is_incident": True,
        }
    )

    return clean_df


def extract_noaa_lightning(
    start_year: int = 2015,
    end_year: int = 2025,
) -> pd.DataFrame:
    """Extracts all nationwide lightning strike records across 2015-2025."""
    print(f"[NOAA:LIGHTNING] Scanning NCEI server for years {start_year}-{end_year}...")
    files = list_storm_event_files(start_year=start_year, end_year=end_year)
    print(f"[NOAA:LIGHTNING] Found {len(files)} yearly storm events archives to process.")

    yearly_dfs = []
    for fname in files:
        year_match = re.search(r"_d(\d{4})_", fname)
        year_label = year_match.group(1) if year_match else fname
        print(f"[NOAA:LIGHTNING] Downloading & extracting {year_label} ({fname})...")
        try:
            df = fetch_lightning_from_file(fname)
            print(f"[NOAA:LIGHTNING] {year_label}: {len(df):,} verified lightning strikes")
            yearly_dfs.append(df)
        except Exception as exc:
            print(f"[NOAA:LIGHTNING:WARN] Failed processing {fname}: {exc}")

    if not yearly_dfs:
        return pd.DataFrame()

    combined = pd.concat(yearly_dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset=["ID"]).reset_index(drop=True)
    print(f"[NOAA:LIGHTNING] Nationwide extraction complete: {len(combined):,} total strikes (2015-2025).")
    return combined


if __name__ == "__main__":
    df = extract_noaa_lightning(2023, 2024)
    print(df.head())
