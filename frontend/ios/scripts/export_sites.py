"""Export Florida plants from the EIA-860M generator workbook into the app's bundled site list.

Mirrors the plant grouping in model/development/eda/visualize_sites_and_incidents.py so the
mock data uses the same sites the model scores.

    pip install openpyxl
    python3 scripts/export_sites.py
"""

import json
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[4]
WORKBOOK = ROOT / "swamphacks-project/model/data/power_plant_data/august_generator2026.xlsx"
# The app's mock data and the backend seed must list the same plants.
OUTPUTS = [
    Path(__file__).resolve().parents[1] / "CrewSafe/Resources/florida_sites.json",
    ROOT / "swamphacks-project/backend/crewsafe/storage/seed/florida_sites.json",
]


def main() -> None:
    sheet = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    for _ in range(2):
        next(rows)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    col = {name: i for i, name in enumerate(header)}

    plants: dict[int, dict] = {}
    capacity: dict[int, float] = defaultdict(float)
    for row in rows:
        if row[col["Plant State"]] != "FL":
            continue
        try:
            plant_id = int(row[col["Plant ID"]])
            lat = float(row[col["Latitude"]])
            lon = float(row[col["Longitude"]])
        except (TypeError, ValueError):
            continue
        capacity[plant_id] += float(row[col["Nameplate Capacity (MW)"]] or 0)
        plants.setdefault(plant_id, {
            "id": plant_id,
            "name": str(row[col["Plant Name"]]).strip(),
            "county": str(row[col["County"]] or "").strip(),
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
        })

    sites = []
    for plant_id, plant in sorted(plants.items()):
        plant["capacity_mw"] = round(capacity[plant_id], 1)
        sites.append(plant)

    for output in OUTPUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(sites, separators=(",", ":")))
        print(f"Wrote {len(sites)} sites to {output}")


if __name__ == "__main__":
    main()
