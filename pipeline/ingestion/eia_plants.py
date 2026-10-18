"""EIA-860M Florida Power Plant Job Sites Ingestion Module.

Downloads and parses the official U.S. Energy Information Administration (EIA) Form EIA-860M
(Monthly Electric Generator Inventory), extracting all operating power plants in the State of Florida.
Saves the coordinates, utility, county, nameplate capacity, and technology into `monitored_sites` in SQLite.
"""

from pathlib import Path
import re
import sqlite3
from typing import Dict, List, Optional, Union
import pandas as pd
import requests

EIA_860M_PAGE_URL = "https://www.eia.gov/electricity/data/eia860m/"
FALLBACK_XLSX_URL = "https://www.eia.gov/electricity/data/eia860m/xls/august_generator2026.xlsx"


def download_eia860m_workbook(dest_path: Path) -> Path:
    """Downloads the latest available EIA-860M Excel workbook."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    xlsx_url = None
    try:
        resp = requests.get(EIA_860M_PAGE_URL, headers=headers, timeout=12)
        if resp.status_code == 200:
            matches = re.findall(r'href=[\"\']([^\"\']+\.(?:xlsx|xls))[\"\']', resp.text, re.IGNORECASE)
            for m in matches:
                if "generator" in m.lower():
                    xlsx_url = "https://www.eia.gov" + m if not m.startswith("http") else m
                    break
    except Exception:
        pass

    if not xlsx_url:
        xlsx_url = FALLBACK_XLSX_URL

    print(f"[EIA-860M] Downloading workbook from: {xlsx_url}")
    r = requests.get(xlsx_url, headers=headers, stream=True, timeout=30)
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    print(f"[EIA-860M] Saved {dest_path.stat().st_size / (1024*1024):.1f} MB to {dest_path.name}")
    return dest_path


def load_florida_power_plants(
    db_path: Optional[Union[str, Path]] = None,
    excel_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Parses Florida operating power plants from EIA-860M and updates `monitored_sites` in SQLite."""
    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
    db_path = Path(db_path)

    if excel_path is None:
        excel_path = db_path.parent / "eia860m.xlsx"
    excel_path = Path(excel_path)

    if not excel_path.exists():
        download_eia860m_workbook(excel_path)

    print(f"[EIA-860M] Parsing Operating sheet from {excel_path.name}...")
    df = pd.read_excel(excel_path, sheet_name="Operating", skiprows=2)

    state_col = "Plant State" if "Plant State" in df.columns else "State"
    fl_df = df[df[state_col] == "FL"].copy()

    # Aggregate by unique plant site
    sites = fl_df.groupby("Plant ID").agg(
        plant_name=("Plant Name", "first"),
        utility_name=("Entity Name", "first"),
        county=("County", "first"),
        latitude=("Latitude", "first"),
        longitude=("Longitude", "first"),
        technology=("Technology", lambda x: ", ".join(x.dropna().unique()[:3])),
        capacity_mw=("Nameplate Capacity (MW)", "sum"),
    ).reset_index()

    sites["plant_id"] = sites["Plant ID"].astype(int)
    sites["state"] = "FL"
    sites = sites.drop(columns=["Plant ID"])

    sites["latitude"] = sites["latitude"].round(4)
    sites["longitude"] = sites["longitude"].round(4)

    # Filter out rows with invalid coordinates
    sites = sites.dropna(subset=["latitude", "longitude"])
    sites = sites[(sites["latitude"] > 24.0) & (sites["latitude"] < 32.0)]
    sites = sites[(sites["longitude"] > -88.0) & (sites["longitude"] < -79.0)]

    cols = [
        "plant_id",
        "plant_name",
        "utility_name",
        "county",
        "state",
        "latitude",
        "longitude",
        "technology",
        "capacity_mw",
    ]
    sites = sites[cols].sort_values(by="capacity_mw", ascending=False).reset_index(drop=True)

    with sqlite3.connect(db_path) as conn:
        sites.to_sql("monitored_sites", conn, if_exists="replace", index=False)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sites_plant_id ON monitored_sites(plant_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sites_lat_lon ON monitored_sites(latitude, longitude)")

    print(f"[EIA-860M] Successfully stored {len(sites)} Florida power plant sites into SQLite (`monitored_sites`).")
    return sites


if __name__ == "__main__":
    load_florida_power_plants()
