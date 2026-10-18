"""Extracts verified historical nationwide wildfire incidents from NIFC WFIGS FeatureServer (2015-2025)."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd
import requests

NIFC_FEATURE_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query"
)


def extract_nifc_wildfires(
    min_acres: float = 2000.0,
    start_date: str = "2015-01-01",
    end_date: str = "2025-12-31",
    batch_size: int = 2000,
) -> pd.DataFrame:
    """Extracts verified wildfire incidents from NIFC WFIGS service across 2015-2025."""
    where_clause = (
        f"IncidentTypeCategory = 'WF' "
        f"AND IncidentSize >= {min_acres} "
        f"AND FireDiscoveryDateTime >= '{start_date}' "
        f"AND FireDiscoveryDateTime <= '{end_date}'"
    )

    print(f"[NIFC:WILDFIRE] Querying NIFC WFIGS (min_acres >= {min_acres:,}, {start_date} to {end_date})...")

    # Get total count first
    count_params = {"where": where_clause, "returnCountOnly": "true", "f": "json"}
    count_resp = requests.get(NIFC_FEATURE_URL, params=count_params, timeout=30)
    count_resp.raise_for_status()
    total_count = count_resp.json().get("count", 0)
    print(f"[NIFC:WILDFIRE] Found {total_count:,} qualifying wildfire incidents nationwide.")

    if total_count == 0:
        return pd.DataFrame()

    all_records = []
    offset = 0

    while offset < total_count:
        params = {
            "where": where_clause,
            "outFields": "OBJECTID,UniqueFireIdentifier,IrwinID,IncidentName,FireDiscoveryDateTime,IncidentSize,POOState",
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "orderByFields": "FireDiscoveryDateTime ASC",
            "f": "json",
        }

        resp = requests.get(NIFC_FEATURE_URL, params=params, timeout=30)
        resp.raise_for_status()
        features = resp.json().get("features", [])

        if not features:
            break

        for feat in features:
            attrs = feat.get("attributes", {})
            geom = feat.get("geometry", {})
            lat = geom.get("y")
            lon = geom.get("x")
            ms = attrs.get("FireDiscoveryDateTime")

            if lat is None or lon is None or ms is None:
                continue

            # Convert ms epoch to UTC ISO date
            try:
                date_str = datetime.fromtimestamp(ms / 1000.0, timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                continue

            fire_id = attrs.get("UniqueFireIdentifier") or attrs.get("IrwinID") or str(attrs.get("OBJECTID"))
            clean_id = f"NIFC_WF_{fire_id}".replace(" ", "_")

            all_records.append(
                {
                    "ID": clean_id,
                    "Latitude": round(float(lat), 4),
                    "Longitude": round(float(lon), 4),
                    "Date": date_str,
                    "incident_type": "Wildfire",
                    "is_incident": True,
                }
            )

        offset += len(features)
        print(f"[NIFC:WILDFIRE] Retrieved {offset:,}/{total_count:,} records...")

    df = pd.DataFrame(all_records)
    if not df.empty:
        df = df.drop_duplicates(subset=["ID"]).reset_index(drop=True)
    print(f"[NIFC:WILDFIRE] Extraction complete: {len(df):,} unique wildfire events collected.")
    return df


if __name__ == "__main__":
    df = extract_nifc_wildfires(min_acres=2000.0)
    print(df.head())
