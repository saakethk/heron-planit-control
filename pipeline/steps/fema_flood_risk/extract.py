"""FEMA National Flood Hazard Layer (NFHL) Extractor.

Queries official US Government FEMA ArcGIS REST MapServer Layer 28 (Flood Hazard Zones)
to obtain Special Flood Hazard Area (SFHA) determinations and 100-year / 500-year
flood risk probability scores for geographic coordinates.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import requests
from requests.adapters import HTTPAdapter

FEMA_NFHL_LAYER28_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

# High-risk 100-year flood zones (1% annual chance of flood)
HIGH_RISK_SFHA_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
COASTAL_HIGH_HAZARD_ZONES = {"V", "VE"}
MODERATE_RISK_500YR_ZONES = {"B", "X500"}

_tls = threading.local()

def get_fema_session() -> requests.Session:
    """Thread-local session for FEMA REST queries."""
    if not hasattr(_tls, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
        adapter = HTTPAdapter(pool_connections=5, pool_maxsize=5, max_retries=1)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _tls.session = s
    return _tls.session


def init_fema_table(conn: sqlite3.Connection):
    """Initializes `fema_flood_risk` table in SQLite."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fema_flood_risk (
            Latitude REAL,
            Longitude REAL,
            fld_zone TEXT,
            sfha_tf TEXT,
            is_sfha INTEGER,
            is_coastal_hazard INTEGER,
            fema_flood_risk_score REAL,
            PRIMARY KEY (Latitude, Longitude)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fema_lat_lon ON fema_flood_risk(Latitude, Longitude)")
    conn.commit()


def compute_fema_risk_score(fld_zone: Optional[str], sfha_tf: Optional[str]) -> Tuple[int, int, float]:
    """Maps FEMA Flood Zone code to quantitative flood risk probability metrics.

    Returns:
        (is_sfha, is_coastal_hazard, risk_score)
    """
    if not fld_zone:
        return 0, 0, 0.05

    zone = str(fld_zone).strip().upper()
    is_sfha = 1 if (sfha_tf == "T" or zone in HIGH_RISK_SFHA_ZONES) else 0
    is_coastal = 1 if zone in COASTAL_HIGH_HAZARD_ZONES else 0

    if is_coastal:
        score = 1.0  # Velocity wave coastal high hazard
    elif is_sfha:
        score = 0.85 # 100-year base flood zone (1% annual probability)
    elif zone in MODERATE_RISK_500YR_ZONES or "500" in zone:
        score = 0.40 # 500-year moderate flood zone (0.2% annual probability)
    elif zone in {"C", "X"}:
        score = 0.05 # Minimal flood hazard
    else:
        score = 0.10 # Unmapped / Undetermined

    return is_sfha, is_coastal, score


def fetch_fema_flood_zone(
    latitude: float,
    longitude: float,
    session: Optional[requests.Session] = None,
) -> Dict:
    """Queries FEMA NFHL Layer 28 for a specific coordinate."""
    if session is None:
        session = get_fema_session()
    lat = round(float(latitude), 4)
    lon = round(float(longitude), 4)

    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f": "json",
    }

    try:
        resp = session.get(FEMA_NFHL_LAYER28_URL, params=params, timeout=(3.0, 7.0))
        if resp.status_code == 200:
            features = resp.json().get("features", [])
            if features:
                attrs = features[0].get("attributes", {})
                fld_zone = attrs.get("FLD_ZONE")
                zone_subty = attrs.get("ZONE_SUBTY")
                sfha_tf = attrs.get("SFHA_TF", "F")
                
                # Check for 500-year zone subtype in Zone X
                if fld_zone == "X" and zone_subty and "0.2" in str(zone_subty):
                    fld_zone = "X500"

                is_sfha, is_coastal, score = compute_fema_risk_score(fld_zone, sfha_tf)
                return {
                    "Latitude": lat,
                    "Longitude": lon,
                    "fld_zone": str(fld_zone) if fld_zone else "UNMAPPED",
                    "sfha_tf": str(sfha_tf),
                    "is_sfha": is_sfha,
                    "is_coastal_hazard": is_coastal,
                    "fema_flood_risk_score": score,
                }
    except Exception:
        pass

    # Default fallback for unmapped or query failure
    return {
        "Latitude": lat,
        "Longitude": lon,
        "fld_zone": "UNMAPPED",
        "sfha_tf": "F",
        "is_sfha": 0,
        "is_coastal_hazard": 0,
        "fema_flood_risk_score": 0.05,
    }


def sync_fema_flood_data(
    db_path: Optional[Union[str, Path]] = None,
    only_sampled: bool = True,
    max_workers: int = 4,
    batch_size: int = 100,
) -> int:
    """Extracts and caches FEMA NFHL flood zone metrics for all unique locations."""
    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    db_path = Path(db_path)

    with sqlite3.connect(db_path) as conn:
        init_fema_table(conn)

        sampled_filter = "WHERE is_sampled = 1" if only_sampled else ""
        query = f"""
            SELECT DISTINCT round(c.Latitude, 4) as Latitude, round(c.Longitude, 4) as Longitude
            FROM clean_incident_data c
            LEFT JOIN fema_flood_risk f ON round(c.Latitude, 4) = f.Latitude AND round(c.Longitude, 4) = f.Longitude
            {sampled_filter}
            {'AND' if sampled_filter else 'WHERE'} f.Latitude IS NULL
        """
        pending_df = pd.read_sql(query, conn)

    total_pending = len(pending_df)
    if total_pending == 0:
        print("[FEMA:NFHL] All coordinates already synchronized in fema_flood_risk.")
        return 0

    print(f"[FEMA:NFHL] Fetching official FEMA Flood Hazard determinations for {total_pending:,} locations...")

    coords_list = pending_df.to_dict(orient="records")
    total_synced = 0
    t0 = time.time()

    for i in range(0, total_pending, batch_size):
        chunk = coords_list[i : i + batch_size]
        batch_results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(fetch_fema_flood_zone, row["Latitude"], row["Longitude"])
                for row in chunk
            ]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        batch_results.append(res)
                except Exception:
                    pass

        if batch_results:
            b_df = pd.DataFrame(batch_results)
            with sqlite3.connect(db_path) as conn:
                b_df.to_sql("fema_flood_risk", conn, if_exists="append", index=False)
            total_synced += len(batch_results)

        elapsed = time.time() - t0
        rate = total_synced / max(elapsed, 0.1)
        print(f"[FEMA:NFHL] Synced {total_synced:,}/{total_pending:,} locations ({total_synced/total_pending*100:.1f}%) | {rate:.1f} loc/s")
        time.sleep(0.05)

    print(f"[FEMA:NFHL] Completed syncing {total_synced:,} locations in {time.time()-t0:.1f}s.")
    return total_synced
