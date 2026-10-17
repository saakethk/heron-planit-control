"""
Florida Power Generation Sites & Incident Visualizer (1km Radius)
==================================================================
This script loads power plant data and OSHA incident reports for Florida,
identifies incidents located within a 1km (1,000 meter) radius of any power plant,
and generates an interactive, full-featured Leaflet visualization and data export.
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path

# Dynamically find workspace root (where .venv or .git resides)
def _find_workspace_root():
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / ".venv").exists() or (curr / ".git").exists():
            return curr
        curr = curr.parent
    return Path.cwd()

WORKSPACE_ROOT = _find_workspace_root()

# Automatically inject workspace venv site-packages if needed
_venv_site = WORKSPACE_ROOT / ".venv" / "lib" / "python3.13" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(0, str(_venv_site))

def resolve_data_file(file_path):
    """Resolve data file path dynamically across different working directories."""
    p = Path(file_path)
    if p.is_file():
        return p.resolve()

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / file_path,
        script_dir.parent.parent / "data" / p.name,
        script_dir.parent.parent / "data" / p.parent.name / p.name,
        script_dir.parent.parent / file_path,
        WORKSPACE_ROOT / file_path,
        WORKSPACE_ROOT / "model" / file_path,
        WORKSPACE_ROOT / "model" / "data" / file_path,
        WORKSPACE_ROOT / "model" / "data" / p.parent.name / p.name,
        WORKSPACE_ROOT / "model" / "data" / p.name,
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return p.resolve()

import numpy as np
import pandas as pd


# ---------------------------------------------------------
# Haversine Distance (vectorized)
# ---------------------------------------------------------
def haversine_vectorized(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two sets of points in meters.
    Accepts numpy arrays or scalars.
    """
    R = 6371000.0  # Earth radius in meters
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)

    a = np.sin(delta_phi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0)**2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return R * c


# ---------------------------------------------------------
# Hazard Classifier from OIICS Codes (from model/development/eda.ipynb)
# ---------------------------------------------------------
class HazardClassifier:
    COLS = {"Event": "Event", "Source": "Source",
            "SecondarySource": "Secondary_Source", "Nature": "Nature"}
    FIELD_FOR = {"Event": "Event", "Source": "Source",
                 "SecondarySource": "Source", "Nature": "Nature"}
    PRIORITY = ["Event", "Source", "SecondarySource", "Nature"]
    V3_START_YEAR = 2024

    NARRATIVE_KW = {
        "Lightning": r"lightning",
        "Falling tree/landslide": r"\b(trees?|limbs?|branch(es)?|logs?)\b|landslide|mudslide|rockslide",
        "Wildlife": r"\b(bit|bitten|stung?|snakes?|spiders?|scorpions?|bees?|wasps?|hornets?|ticks?|animals?|deer|alligators?|gators?|rodents?|rats?|birds?|boar|hogs?|dogs?)\b",
        "Soil/Mud": r"\b(mud|muddy|soil|dirt)\b",
        "Sun/UV": r"\bsun(burn)?\b",
        "Flooding/Landslide": r"flood|mudslide|landslide|avalanche",
    }

    def __init__(self, codes_csv_path):
        self.lookup = {}
        if os.path.exists(codes_csv_path):
            codes = pd.read_csv(codes_csv_path, dtype=str, keep_default_na=False)
            for r in codes.itertuples():
                notes = r.Notes if isinstance(r.Notes, str) else ""
                self.lookup.setdefault((r.OIICS_Version, r.Field), {})[r.Code] = (r.Hazard_Type, bool(notes.strip()))

    @staticmethod
    def normalize_code(x):
        if pd.isna(x):
            return None
        s = str(x).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return s or None

    def lookup_code(self, table, code):
        while len(code) >= 2:
            if code in table:
                return table[code]
            code = code[:-1]
        return None

    def classify_row(self, row, exclude_hazards=("Other environmental",)):
        date = pd.to_datetime(row.get("EventDate"), errors="coerce")
        if pd.isna(date) or date.year < 2015:
            return {"is_environmental_hazard": False, "hazard_category": "General Incident"}

        version = "3.03" if date.year >= self.V3_START_YEAR else "2.01"
        narrative = str(row.get("FinalNarrative", ""))

        hits = []
        for k in self.PRIORITY:
            code = self.normalize_code(row.get(self.COLS[k]))
            if code is None:
                continue
            found = self.lookup_code(self.lookup.get((version, self.FIELD_FOR[k]), {}), code)
            if found is None:
                continue
            hazard, weak = found
            if hazard in exclude_hazards:
                continue
            if weak:
                kw = self.NARRATIVE_KW.get(hazard)
                if not (kw and re.search(kw, narrative, flags=re.I)):
                    continue
            hits.append((k, code, hazard))

        if not hits:
            return {"is_environmental_hazard": False, "hazard_category": "General Workplace Incident"}
        return {"is_environmental_hazard": True, "hazard_category": hits[0][2]}


# ---------------------------------------------------------
# Data Loader & Matcher
# ---------------------------------------------------------
def load_florida_plants(excel_path):
    """Loads and aggregates Florida power generation sites from August 2026 generator data."""
    print(f"Loading power plants from: {excel_path}")
    df = pd.read_excel(excel_path, skiprows=2)
    
    # Filter for Florida
    fl_df = df[df["Plant State"] == "FL"].copy()
    fl_df = fl_df.dropna(subset=["Latitude", "Longitude"])
    fl_df["Latitude"] = pd.to_numeric(fl_df["Latitude"], errors="coerce")
    fl_df["Longitude"] = pd.to_numeric(fl_df["Longitude"], errors="coerce")
    fl_df = fl_df.dropna(subset=["Latitude", "Longitude"])

    # Aggregate units by Plant site (Plant ID + Location)
    grouped = fl_df.groupby(["Plant ID", "Plant Name", "County", "Plant State", "Latitude", "Longitude"], as_index=False).agg({
        "Entity Name": lambda s: " / ".join(sorted(s.dropna().unique())),
        "Nameplate Capacity (MW)": lambda s: round(float(s.dropna().sum()), 2),
        "Technology": lambda s: ", ".join(sorted(s.dropna().unique())),
        "Energy Source Code": lambda s: ", ".join(sorted(s.dropna().unique())),
        "Generator ID": "count"
    }).rename(columns={"Generator ID": "Generator Units Count"})

    print(f"-> Loaded {len(grouped)} unique Florida power generation sites (from {len(fl_df)} generator units).")
    return grouped


def load_incidents(csv_path, codes_csv_path=None):
    """Loads OSHA Florida incident reports and optionally tags hazard types."""
    print(f"Loading OSHA incidents from: {csv_path}")
    ir = pd.read_csv(csv_path, on_bad_lines="skip", low_memory=False)
    ir["Latitude"] = pd.to_numeric(ir["Latitude"], errors="coerce")
    ir["Longitude"] = pd.to_numeric(ir["Longitude"], errors="coerce")
    ir = ir.dropna(subset=["Latitude", "Longitude"]).copy()

    # Fill default strings
    for col in ["Employer", "city", "EventTitle", "FinalNarrative", "NatureTitle", "sourceTitle"]:
        if col in ir.columns:
            ir[col] = ir[col].fillna("Unknown").astype(str).str.strip()

    # Apply hazard classification if codes CSV provided
    if codes_csv_path and os.path.exists(codes_csv_path):
        print(f"Classifying hazards using: {codes_csv_path}")
        classifier = HazardClassifier(codes_csv_path)
        classifications = ir.apply(classifier.classify_row, axis=1, result_type="expand")
        ir = ir.join(classifications)
    else:
        ir["is_environmental_hazard"] = False
        ir["hazard_category"] = "General Workplace Incident"

    print(f"-> Loaded {len(ir)} valid incident records.")
    return ir


def find_incidents_within_radius(plants_df, incidents_df, radius_meters=1000.0):
    """
    Finds all incidents within radius_meters of any power plant site.
    Returns:
      matched_incidents_df: DataFrame of incidents with distance and closest plant info
      plants_with_counts_df: DataFrame of plants with incident counts
      all_pairs_df: Full pairing list (plant_id, incident_id, distance_m)
    """
    print(f"\nComputing geodesic distances (threshold = {radius_meters:,.0f} meters / {radius_meters/1000.0:.2f} km)...")
    
    p_lats = plants_df["Latitude"].values[:, None]
    p_lons = plants_df["Longitude"].values[:, None]
    i_lats = incidents_df["Latitude"].values[None, :]
    i_lons = incidents_df["Longitude"].values[None, :]

    # Distance matrix (N_plants x M_incidents) in meters
    dists = haversine_vectorized(p_lats, p_lons, i_lats, i_lons)
    within_radius_mask = dists <= radius_meters

    p_indices, i_indices = np.where(within_radius_mask)
    matched_distances = dists[p_indices, i_indices]

    print(f"-> Found {len(p_indices)} plant-incident pairings within {radius_meters:.0f}m.")
    print(f"-> Distinct incidents within {radius_meters:.0f}m: {len(np.unique(i_indices))}")
    print(f"-> Plants with at least one nearby incident: {len(np.unique(p_indices))}")

    # Build pairings DataFrame
    pairings = []
    for p_idx, i_idx, dist in zip(p_indices, i_indices, matched_distances):
        p_row = plants_df.iloc[p_idx]
        i_row = incidents_df.iloc[i_idx]
        pairings.append({
            "Plant ID": p_row["Plant ID"],
            "Plant Name": p_row["Plant Name"],
            "Plant County": p_row["County"],
            "Plant Latitude": p_row["Latitude"],
            "Plant Longitude": p_row["Longitude"],
            "Plant Capacity (MW)": p_row["Nameplate Capacity (MW)"],
            "Incident ID": i_row["ID"],
            "Incident Date": i_row["EventDate"],
            "Employer": i_row["Employer"],
            "Incident City": i_row["city"],
            "Incident Latitude": i_row["Latitude"],
            "Incident Longitude": i_row["Longitude"],
            "Distance (m)": round(dist, 1),
            "Hazard Category": i_row["hazard_category"],
            "Is Environmental Hazard": i_row["is_environmental_hazard"],
            "Hospitalized": i_row.get("Hospitalized", 0),
            "Amputation": i_row.get("Amputation", 0),
            "Event Title": i_row.get("EventTitle", ""),
            "Narrative": i_row.get("FinalNarrative", "")
        })
    pairs_df = pd.DataFrame(pairings)

    # Calculate incident count per plant
    if len(pairs_df) > 0:
        plant_incident_counts = pairs_df.groupby("Plant ID")["Incident ID"].nunique().to_dict()
        plants_df["Nearby Incidents Count"] = plants_df["Plant ID"].map(plant_incident_counts).fillna(0).astype(int)
    else:
        plants_df["Nearby Incidents Count"] = 0

    # For unique matched incidents, assign closest plant info
    if len(np.unique(i_indices)) > 0:
        unique_i_indices = np.unique(i_indices)
        matched_ir = incidents_df.iloc[unique_i_indices].copy()
        
        # Closest plant calculation
        min_dist_to_plant = dists[:, unique_i_indices].min(axis=0)
        closest_plant_idx = dists[:, unique_i_indices].argmin(axis=0)
        matched_ir["Distance to Nearest Plant (m)"] = np.round(min_dist_to_plant, 1)
        matched_ir["Nearest Plant ID"] = plants_df.iloc[closest_plant_idx]["Plant ID"].values
        matched_ir["Nearest Plant Name"] = plants_df.iloc[closest_plant_idx]["Plant Name"].values
    else:
        matched_ir = pd.DataFrame()

    return matched_ir, plants_df, pairs_df


# ---------------------------------------------------------
# HTML / Leaflet Map Generator
# ---------------------------------------------------------
def generate_leaflet_map_html(plants_df, matched_incidents_df, output_html_path, radius_meters=1000.0):
    """
    Renders a standalone interactive HTML map with:
    - Base layer switcher (CartoDB Positron, OSM, Satellite)
    - Florida Power Plants markers
    - 1km radius buffer circles around every plant site
    - Color-coded nearby OSHA incident markers
    - Search bar, filter drawer, statistics counters
    - Detailed popups with narrative, employer, distance, capacity, etc.
    """
    # Prepare plants JSON
    plants_records = []
    for _, row in plants_df.iterrows():
        plants_records.append({
            "id": int(row["Plant ID"]) if pd.notna(row["Plant ID"]) else str(row["Plant Name"]),
            "name": str(row["Plant Name"]).replace('"', '&quot;'),
            "county": str(row["County"]).replace('"', '&quot;'),
            "entity": str(row["Entity Name"]).replace('"', '&quot;'),
            "lat": float(row["Latitude"]),
            "lon": float(row["Longitude"]),
            "capacity_mw": float(row["Nameplate Capacity (MW)"]),
            "tech": str(row["Technology"]).replace('"', '&quot;'),
            "units": int(row["Generator Units Count"]),
            "incident_count": int(row.get("Nearby Incidents Count", 0))
        })

    # Prepare incidents JSON
    incidents_records = []
    if not matched_incidents_df.empty:
        for _, row in matched_incidents_df.iterrows():
            narrative = str(row.get("FinalNarrative", ""))[:350]
            if len(str(row.get("FinalNarrative", ""))) > 350:
                narrative += "..."
            narrative = narrative.replace('"', '&quot;').replace("'", "&#39;")
            
            incidents_records.append({
                "id": str(row["ID"]),
                "date": str(row.get("EventDate", "Unknown")),
                "employer": str(row.get("Employer", "Unknown")).replace('"', '&quot;'),
                "city": str(row.get("city", "Unknown")).replace('"', '&quot;'),
                "lat": float(row["Latitude"]),
                "lon": float(row["Longitude"]),
                "dist_m": float(row.get("Distance to Nearest Plant (m)", 0.0)),
                "plant_name": str(row.get("Nearest Plant Name", "")).replace('"', '&quot;'),
                "hazard": str(row.get("hazard_category", "General Incident")),
                "is_env": bool(row.get("is_environmental_hazard", False)),
                "hospitalized": int(row.get("Hospitalized", 0)) if pd.notna(row.get("Hospitalized")) else 0,
                "amputation": int(row.get("Amputation", 0)) if pd.notna(row.get("Amputation")) else 0,
                "title": str(row.get("EventTitle", "")).replace('"', '&quot;'),
                "narrative": narrative
            })

    total_plants = len(plants_records)
    plants_with_incidents = sum(1 for p in plants_records if p["incident_count"] > 0)
    total_incidents = len(incidents_records)
    env_incidents = sum(1 for i in incidents_records if i["is_env"])

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!-- Leaflet CSS & JS (Core only, no brittle external plugin dependencies) -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

  <!-- Google Fonts & Font Awesome Icons -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>

  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    body, html {{
      height: 100%;
      width: 100%;
      overflow: hidden;
      background: #0f172a;
      color: #f1f5f9;
    }}
    #app {{
      display: flex;
      flex-direction: column;
      height: 100vh;
      width: 100vw;
    }}
    /* Header Navbar */
    header {{
      background: #1e293b;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #334155;
      z-index: 1000;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }}
    .title-area {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .title-area i {{
      font-size: 24px;
      color: #38bdf8;
    }}
    h1 {{
      font-size: 1.15rem;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.01em;
    }}
    .subtitle {{
      font-size: 0.78rem;
      color: #94a3b8;
    }}
    .stats-bar {{
      display: flex;
      gap: 16px;
    }}
    .stat-badge {{
      background: #0f172a;
      border: 1px solid #334155;
      padding: 6px 14px;
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    .stat-badge .num {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #38bdf8;
    }}
    .stat-badge.alert .num {{
      color: #f87171;
    }}
    .stat-badge.warn .num {{
      color: #fbbf24;
    }}
    .stat-badge .lbl {{
      font-size: 0.65rem;
      text-transform: uppercase;
      color: #94a3b8;
      letter-spacing: 0.05em;
    }}
    /* Main Layout */
    .content-area {{
      display: flex;
      flex: 1;
      height: calc(100vh - 65px);
      position: relative;
    }}
    #map {{
      flex: 1;
      height: 100%;
      background: #1e293b;
    }}
    /* Sidebar Drawer */
    #sidebar {{
      width: 380px;
      background: #1e293b;
      border-left: 1px solid #334155;
      display: flex;
      flex-direction: column;
      z-index: 999;
      box-shadow: -4px 0 10px rgba(0, 0, 0, 0.3);
      transition: transform 0.3s ease;
    }}
    #sidebar.hidden {{
      transform: translateX(380px);
      margin-right: -380px;
    }}
    .sidebar-header {{
      padding: 16px;
      border-bottom: 1px solid #334155;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .sidebar-header h2 {{
      font-size: 1rem;
      font-weight: 600;
      color: #e2e8f0;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .controls-panel {{
      padding: 16px;
      border-bottom: 1px solid #334155;
      background: #0f172a80;
    }}
    .filter-group {{
      margin-bottom: 12px;
    }}
    .filter-group label {{
      display: block;
      font-size: 0.72rem;
      text-transform: uppercase;
      font-weight: 600;
      color: #94a3b8;
      margin-bottom: 6px;
    }}
    .filter-group input, .filter-group select {{
      width: 100%;
      padding: 8px 12px;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      color: #f1f5f9;
      font-size: 0.82rem;
      outline: none;
    }}
    .filter-group input:focus, .filter-group select:focus {{
      border-color: #38bdf8;
    }}
    .toggles-row {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 10px;
    }}
    .toggle-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: #cbd5e1;
      cursor: pointer;
    }}
    .toggle-item input[type="checkbox"] {{
      accent-color: #38bdf8;
      width: 16px;
      height: 16px;
      cursor: pointer;
    }}
    .list-container {{
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }}
    .list-item {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 10px;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
    }}
    .list-item:hover {{
      border-color: #38bdf8;
      background: #1e293b;
    }}
    .list-item .item-title {{
      font-weight: 600;
      font-size: 0.85rem;
      color: #f8fafc;
      margin-bottom: 4px;
      display: flex;
      justify-content: space-between;
    }}
    .list-item .item-sub {{
      font-size: 0.75rem;
      color: #94a3b8;
      margin-bottom: 6px;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.7rem;
      font-weight: 600;
    }}
    .badge-env {{
      background: rgba(239, 68, 68, 0.2);
      color: #fca5a5;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }}
    .badge-gen {{
      background: rgba(148, 163, 184, 0.2);
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.4);
    }}
    .badge-dist {{
      background: rgba(56, 189, 248, 0.2);
      color: #7dd3fc;
      border: 1px solid rgba(56, 189, 248, 0.4);
    }}
    /* Custom Popup Styles */
    .leaflet-popup-content-wrapper {{
      background: #1e293b;
      color: #f1f5f9;
      border-radius: 10px;
      border: 1px solid #475569;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .leaflet-popup-tip {{
      background: #1e293b;
    }}
    .popup-box {{
      font-size: 0.82rem;
      line-height: 1.45;
    }}
    .popup-box h3 {{
      font-size: 0.95rem;
      font-weight: 700;
      color: #38bdf8;
      margin-bottom: 6px;
      border-bottom: 1px solid #334155;
      padding-bottom: 4px;
    }}
    .popup-box h3.incident-title {{
      color: #f87171;
    }}
    .popup-box .meta-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
      color: #cbd5e1;
    }}
    .popup-box .meta-label {{
      color: #94a3b8;
      font-weight: 500;
    }}
    .popup-box .narrative-text {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 8px;
      margin-top: 8px;
      font-size: 0.75rem;
      color: #cbd5e1;
      max-height: 120px;
      overflow-y: auto;
    }}
    /* Legend */
    .legend-box {{
      background: rgba(30, 41, 59, 0.92);
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 10px 14px;
      color: #f8fafc;
      font-size: 0.75rem;
      line-height: 1.6;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .legend-color {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      display: inline-block;
    }}
    .legend-ring {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 2px dashed #38bdf8;
      background: rgba(56, 189, 248, 0.15);
    }}
    /* Toggle Button */
    .sidebar-toggle-btn {{
      position: absolute;
      top: 12px;
      right: 12px;
      z-index: 1000;
      background: #1e293b;
      border: 1px solid #475569;
      color: #f8fafc;
      padding: 8px 12px;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.8rem;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    .sidebar-toggle-btn:hover {{
      background: #334155;
    }}
  </style>
</head>
<body>
<div id="app">
  <header>
    <div class="title-area">
      <i class="fa-solid fa-bolt-lightning"></i>
      <div>
        <h1>Florida Power Generation & Safety Incident Map</h1>
        <div class="subtitle">EIA Power Plant Locations & OSHA Incidents within 1km Buffer Zone ({radius_meters:,.0f}m)</div>
      </div>
    </div>
    <div class="stats-bar">
      <div class="stat-badge">
        <span class="num">{total_plants}</span>
        <span class="lbl">FL Plants</span>
      </div>
      <div class="stat-badge warn">
        <span class="num">{plants_with_incidents}</span>
        <span class="lbl">Plants w/ Incidents &le;1km</span>
      </div>
      <div class="stat-badge alert">
        <span class="num">{total_incidents}</span>
        <span class="lbl">Incidents &le;1km</span>
      </div>
      <div class="stat-badge">
        <span class="num">{env_incidents}</span>
        <span class="lbl">Env / Wildlife</span>
      </div>
    </div>
  </header>

  <div class="content-area">
    <div id="map"></div>
    <button class="sidebar-toggle-btn" id="toggleSidebarBtn" onclick="toggleSidebar()">
      <i class="fa-solid fa-bars"></i> Filter & Sites
    </button>

    <div id="sidebar">
      <div class="sidebar-header">
        <h2><i class="fa-solid fa-sliders"></i> Filters & Inspections</h2>
        <span style="font-size:0.75rem; color:#94a3b8;" id="filteredCountText">Showing {total_incidents} incidents</span>
      </div>
      <div class="controls-panel">
        <div class="filter-group">
          <label><i class="fa-solid fa-magnifying-glass"></i> Search Plant or Employer</label>
          <input type="text" id="searchInput" placeholder="Search plant name, county, employer..." oninput="applyFilters()">
        </div>
        <div class="filter-group">
          <label><i class="fa-solid fa-triangle-exclamation"></i> Hazard Type</label>
          <select id="hazardFilter" onchange="applyFilters()">
            <option value="ALL">All Incidents ({total_incidents})</option>
            <option value="ENV_ONLY">Environmental / Wildlife Only ({env_incidents})</option>
            <option value="Wildlife">Wildlife (Stings, Bites, Reptiles)</option>
            <option value="Heat">Heat / Temperature Extremes</option>
            <option value="Falling tree/landslide">Falling Trees / Landslide</option>
            <option value="Lightning">Lightning</option>
            <option value="Soil/Mud">Soil / Mud Hazards</option>
            <option value="General Workplace Incident">General Workplace Incident</option>
          </select>
        </div>
        <div class="toggles-row">
          <label class="toggle-item">
            <input type="checkbox" id="chkBuffer" checked onchange="toggleLayer('buffer')">
            <span>Show 1km Radius Circles</span>
          </label>
          <label class="toggle-item">
            <input type="checkbox" id="chkPlants" checked onchange="toggleLayer('plants')">
            <span>Show Power Plants</span>
          </label>
          <label class="toggle-item">
            <input type="checkbox" id="chkIncidents" checked onchange="toggleLayer('incidents')">
            <span>Show Incidents</span>
          </label>
          <label class="toggle-item">
            <input type="checkbox" id="chkOnlyAffectedPlants" onchange="applyFilters()">
            <span>Only Plants with Nearby Incidents ({plants_with_incidents})</span>
          </label>
        </div>
      </div>

      <div class="list-container" id="cardsList">
        <!-- Dynamically populated incident and plant cards -->
      </div>
    </div>
  </div>
</div>

<script>
  // Data passed from Python
  const PLANTS = {json.dumps(plants_records)};
  const INCIDENTS = {json.dumps(incidents_records)};
  const RADIUS_METERS = {radius_meters};

  // Base Map Setup
  const map = L.map('map', {{
    center: [28.0, -82.4],
    zoom: 7,
    zoomControl: true
  }});

  // Free Base Maps (No API Key Required)
  const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }}).addTo(map);

  const esriDark = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    maxZoom: 16,
    attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
  }});

  const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    maxZoom: 19,
    attribution: 'Tiles &copy; Esri'
  }});

  L.control.layers({{
    "OpenStreetMap (Standard)": osm,
    "Esri Dark Canvas": esriDark,
    "Satellite Imagery": satellite
  }}, null, {{ position: 'bottomleft' }}).addTo(map);

  // Custom Panes for optimal layer stacking
  map.createPane('bufferPane');
  map.getPane('bufferPane').style.zIndex = 350;

  map.createPane('plantPane');
  map.getPane('plantPane').style.zIndex = 450;

  map.createPane('incidentPane');
  map.getPane('incidentPane').style.zIndex = 550;

  // Layer Groups
  const plantsLayer = L.layerGroup().addTo(map);
  const bufferLayer = L.layerGroup().addTo(map);
  const incidentsLayer = L.layerGroup().addTo(map);

  // Markers Cache
  let plantMarkerMap = new Map();
  let plantCircleMap = new Map();
  let incidentMarkerMap = new Map();

  // Helper color for hazard category
  function getHazardColor(hazard, isEnv) {{
    if (hazard === 'Wildlife') return '#10b981'; // Green
    if (hazard === 'Heat') return '#f97316'; // Orange
    if (hazard === 'Lightning') return '#eab308'; // Yellow
    if (hazard === 'Falling tree/landslide') return '#84cc16'; // Lime
    if (isEnv) return '#ef4444'; // Red for other environmental
    return '#f43f5e'; // Pink/Rose for general OSHA incident
  }}

  // Initialize Power Plants
  PLANTS.forEach(p => {{
    // 1km Buffer Circle
    const circle = L.circle([p.lat, p.lon], {{
      pane: 'bufferPane',
      radius: RADIUS_METERS,
      color: '#0284c7',
      weight: 1.5,
      dashArray: '4, 4',
      fillColor: '#38bdf8',
      fillOpacity: p.incident_count > 0 ? 0.25 : 0.09
    }});
    circle.bindTooltip(`1km Zone: ${{p.name}} (${{p.incident_count}} incidents)`, {{ sticky: true }});
    bufferLayer.addLayer(circle);
    plantCircleMap.set(p.id, circle);

    // Plant Icon Marker
    const markerColor = p.incident_count > 0 ? '#fbbf24' : '#38bdf8';
    const marker = L.circleMarker([p.lat, p.lon], {{
      pane: 'plantPane',
      radius: p.incident_count > 0 ? 8 : 6,
      fillColor: markerColor,
      color: '#ffffff',
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.95
    }});

    const popupHtml = `
      <div class="popup-box">
        <h3><i class="fa-solid fa-bolt"></i> ${{p.name}}</h3>
        <div class="meta-row"><span class="meta-label">Plant ID:</span> <span>${{p.id}}</span></div>
        <div class="meta-row"><span class="meta-label">County:</span> <span>${{p.county}}</span></div>
        <div class="meta-row"><span class="meta-label">Capacity:</span> <span>${{p.capacity_mw.toLocaleString()}} MW</span></div>
        <div class="meta-row"><span class="meta-label">Technology:</span> <span>${{p.tech || 'N/A'}}</span></div>
        <div class="meta-row"><span class="meta-label">Operator:</span> <span>${{p.entity || 'N/A'}}</span></div>
        <div class="meta-row"><span class="meta-label">Generator Units:</span> <span>${{p.units}}</span></div>
        <div class="meta-row" style="margin-top:6px; font-weight:700;">
          <span class="meta-label">Incidents &le;1km:</span> 
          <span style="color:${{p.incident_count > 0 ? '#f87171' : '#38bdf8'}}">${{p.incident_count}} incident(s)</span>
        </div>
      </div>
    `;
    marker.bindPopup(popupHtml);
    plantsLayer.addLayer(marker);
    plantMarkerMap.set(p.id, marker);
  }});

  // Initialize Incidents
  INCIDENTS.forEach(inc => {{
    const color = getHazardColor(inc.hazard, inc.is_env);
    const marker = L.circleMarker([inc.lat, inc.lon], {{
      pane: 'incidentPane',
      radius: 6,
      fillColor: color,
      color: '#ffffff',
      weight: 1.2,
      opacity: 1,
      fillOpacity: 0.9
    }});

    const popupHtml = `
      <div class="popup-box">
        <h3 class="incident-title"><i class="fa-solid fa-triangle-exclamation"></i> ${{inc.hazard}}</h3>
        <div class="meta-row"><span class="meta-label">Employer:</span> <span>${{inc.employer}}</span></div>
        <div class="meta-row"><span class="meta-label">Date:</span> <span>${{inc.date}}</span></div>
        <div class="meta-row"><span class="meta-label">Location:</span> <span>${{inc.city}}, FL</span></div>
        <div class="meta-row"><span class="meta-label">Nearest Plant:</span> <span>${{inc.plant_name}}</span></div>
        <div class="meta-row"><span class="meta-label">Distance to Plant:</span> <span class="badge badge-dist">${{inc.dist_m.toFixed(0)}} m</span></div>
        <div class="meta-row"><span class="meta-label">Hospitalized / Amp:</span> <span>${{inc.hospitalized}} hosp / ${{inc.amputation}} amp</span></div>
        <div class="narrative-text"><strong>Narrative:</strong> ${{inc.narrative}}</div>
      </div>
    `;
    marker.bindPopup(popupHtml);
    incidentsLayer.addLayer(marker);
    incidentMarkerMap.set(inc.id, marker);
  }});

  // Add Legend
  const legend = L.control({{ position: 'bottomright' }});
  legend.onAdd = function() {{
    const div = L.DomUtil.create('div', 'legend-box');
    div.innerHTML = `
      <div style="font-weight:700; margin-bottom:4px; color:#38bdf8;">Map Legend</div>
      <div class="legend-item"><span class="legend-color" style="background:#38bdf8;"></span> Power Plant (0 nearby incidents)</div>
      <div class="legend-item"><span class="legend-color" style="background:#fbbf24;"></span> Power Plant (&ge;1 nearby incident)</div>
      <div class="legend-item"><span class="legend-ring"></span> 1km Buffer Zone (1,000m)</div>
      <hr style="border:0; border-top:1px solid #334155; margin:6px 0;">
      <div style="font-weight:600; color:#cbd5e1; margin-bottom:2px;">Incident Types (&le;1km):</div>
      <div class="legend-item"><span class="legend-color" style="background:#10b981;"></span> Wildlife Hazard</div>
      <div class="legend-item"><span class="legend-color" style="background:#f97316;"></span> Heat / Extreme Temp</div>
      <div class="legend-item"><span class="legend-color" style="background:#eab308;"></span> Lightning Hazard</div>
      <div class="legend-item"><span class="legend-color" style="background:#84cc16;"></span> Falling Tree / Landslide</div>
      <div class="legend-item"><span class="legend-color" style="background:#f43f5e;"></span> General OSHA Incident</div>
    `;
    return div;
  }};
  legend.addTo(map);

  // Sidebar Toggling & Filters
  function toggleSidebar() {{
    const sb = document.getElementById('sidebar');
    sb.classList.toggle('hidden');
  }}

  function toggleLayer(type) {{
    if (type === 'buffer') {{
      const on = document.getElementById('chkBuffer').checked;
      on ? map.addLayer(bufferLayer) : map.removeLayer(bufferLayer);
    }} else if (type === 'plants') {{
      const on = document.getElementById('chkPlants').checked;
      on ? map.addLayer(plantsLayer) : map.removeLayer(plantsLayer);
    }} else if (type === 'incidents') {{
      const on = document.getElementById('chkIncidents').checked;
      on ? map.addLayer(incidentsLayer) : map.removeLayer(incidentsLayer);
    }}
  }}

  function applyFilters() {{
    const search = document.getElementById('searchInput').value.toLowerCase().trim();
    const hazard = document.getElementById('hazardFilter').value;
    const onlyAffected = document.getElementById('chkOnlyAffectedPlants').checked;

    // Filter plants visibility
    PLANTS.forEach(p => {{
      const matchSearch = !search || 
        p.name.toLowerCase().includes(search) || 
        p.county.toLowerCase().includes(search) ||
        p.entity.toLowerCase().includes(search);
      const matchAffected = !onlyAffected || p.incident_count > 0;

      const marker = plantMarkerMap.get(p.id);
      const circle = plantCircleMap.get(p.id);

      if (matchSearch && matchAffected) {{
        if (!plantsLayer.hasLayer(marker)) plantsLayer.addLayer(marker);
        if (!bufferLayer.hasLayer(circle)) bufferLayer.addLayer(circle);
      }} else {{
        if (plantsLayer.hasLayer(marker)) plantsLayer.removeLayer(marker);
        if (bufferLayer.hasLayer(circle)) bufferLayer.removeLayer(circle);
      }}
    }});

    // Filter incidents
    incidentsLayer.clearLayers();
    let visibleIncidents = [];

    INCIDENTS.forEach(inc => {{
      const matchSearch = !search || 
        inc.employer.toLowerCase().includes(search) || 
        inc.city.toLowerCase().includes(search) || 
        inc.plant_name.toLowerCase().includes(search) ||
        inc.narrative.toLowerCase().includes(search);

      let matchHazard = true;
      if (hazard === 'ENV_ONLY') {{
        matchHazard = inc.is_env;
      }} else if (hazard !== 'ALL') {{
        matchHazard = inc.hazard === hazard;
      }}

      if (matchSearch && matchHazard) {{
        const m = incidentMarkerMap.get(inc.id);
        incidentsLayer.addLayer(m);
        visibleIncidents.push(inc);
      }}
    }});

    document.getElementById('filteredCountText').innerText = `Showing ${{visibleIncidents.length}} incident(s)`;
    renderIncidentCards(visibleIncidents.slice(0, 50));
  }}

  function renderIncidentCards(incList) {{
    const container = document.getElementById('cardsList');
    if (incList.length === 0) {{
      container.innerHTML = `<div style="text-align:center; padding:24px; color:#94a3b8; font-size:0.85rem;">No matching incidents found.</div>`;
      return;
    }}

    container.innerHTML = incList.map(inc => `
      <div class="list-item" onclick="zoomToIncident('${{inc.id}}')">
        <div class="item-title">
          <span>${{inc.employer}}</span>
          <span class="badge badge-dist">${{inc.dist_m.toFixed(0)}}m</span>
        </div>
        <div class="item-sub">
          <i class="fa-solid fa-location-dot"></i> Near <strong>${{inc.plant_name}}</strong> (${{inc.city}}, FL)
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span class="badge ${{inc.is_env ? 'badge-env' : 'badge-gen'}}">${{inc.hazard}}</span>
          <span style="font-size:0.7rem; color:#94a3b8;"><i class="fa-regular fa-calendar"></i> ${{inc.date}}</span>
        </div>
      </div>
    `).join('');
  }}

  function zoomToIncident(id) {{
    const inc = INCIDENTS.find(i => i.id === id);
    if (inc) {{
      map.setView([inc.lat, inc.lon], 16);
      const m = incidentMarkerMap.get(id);
      if (m) {{
        setTimeout(() => {{
          m.openPopup();
        }}, 200);
      }}
    }}
  }}

  // Initial Card Render
  renderIncidentCards(INCIDENTS.slice(0, 50));
</script>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"\n-> Interactive map saved successfully to:\n   {os.path.abspath(output_html_path)}")


# ---------------------------------------------------------
# CLI & Execution
# ---------------------------------------------------------
def main():
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Visualize Florida power generation sites & nearby incidents (1km radius).")
    parser.add_argument("--plant-data", default="power_plant_data/august_generator2026.xlsx", help="Path to generator xlsx")
    parser.add_argument("--incident-data", default="incident_data/osha_florida_data.csv", help="Path to OSHA csv")
    parser.add_argument("--codes-data", default="incident_data/oiics_wildlife_environmental_codes_v201_v303.csv", help="Path to OIICS hazard codes csv")
    parser.add_argument("--radius", type=float, default=1000.0, help="Radius in meters (default: 1000m / 1km)")
    parser.add_argument("--output-html", default=str(script_dir / "florida_power_plants_incidents_map.html"), help="Output path for interactive map HTML")
    parser.add_argument("--output-csv", default=str(script_dir / "incidents_within_1km_of_power_plants.csv"), help="Output path for matched incidents CSV")
    args = parser.parse_args()

    # Dynamically resolve files across directories
    plant_path = resolve_data_file(args.plant_data)
    incident_path = resolve_data_file(args.incident_data)
    codes_path = resolve_data_file(args.codes_data)

    # 1. Load Data
    plants_df = load_florida_plants(plant_path)
    incidents_df = load_incidents(incident_path, codes_path)

    # 2. Find Incidents within radius
    matched_incidents_df, plants_with_counts, pairs_df = find_incidents_within_radius(
        plants_df, incidents_df, radius_meters=args.radius
    )

    # 3. Save CSV report of matched pairs
    pairs_df.to_csv(args.output_csv, index=False)
    print(f"-> Matched pairings exported to CSV:\n   {os.path.abspath(args.output_csv)}")

    # 4. Generate Interactive Map HTML
    generate_leaflet_map_html(plants_with_counts, matched_incidents_df, args.output_html, radius_meters=args.radius)

    print("\nVisualization and analysis pipeline complete!")


if __name__ == "__main__":
    main()
