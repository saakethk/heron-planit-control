"""Seed data: the 346 EIA plants plus demo history (past alerts and crew reports).

Live state (conditions, scores, holds, new alerts) is NOT seeded here: it comes
out of the pipeline, fed by the dummy sources, exactly as it will with real data.
"""

from __future__ import annotations

import json
import os
import random
from datetime import timedelta
from pathlib import Path

from ...contracts.api import HazardAlert
from ...contracts.common import AlertSeverity, HazardType, Role, utcnow
from ...security import hash_password
from ..models import SiteRecord, StoredReport, UserRecord
from ..repository import Repository

COASTAL_COUNTIES = {
    "Bay", "Brevard", "Broward", "Charlotte", "Citrus", "Collier", "Dixie", "Duval", "Escambia", "Flagler",
    "Franklin", "Gulf", "Hernando", "Hillsborough", "Indian River", "Lee", "Levy", "Manatee", "Martin",
    "Miami Dade", "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Palm Beach", "Pasco", "Pinellas", "Santa Rosa",
    "Sarasota", "St Johns", "St. Johns", "St Lucie", "St. Lucie", "Taylor", "Volusia", "Wakulla", "Walton",
}
# Site-layer facts for the demo sites (cooling ponds, waterfront plants).
DEMO_SITE_LAYER = {
    664: dict(wildlife_habitat=0.6, elevation_ft=150),
    617: dict(coastal=True, elevation_ft=8),
    627: dict(coastal=True, near_river=True, elevation_ft=6),
    619: dict(coastal=True, elevation_ft=10),
    56518: dict(wildlife_habitat=0.7),
    50875: dict(coastal=True, elevation_ft=12),
    64546: dict(coastal=True, elevation_ft=7),
}

DEMO_USER_ID = "demo"


def load_plants(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def site_records(plants: list[dict]) -> list[SiteRecord]:
    """Placeholder site layer until GIS joins exist (FEMA flood zones, USGS
    elevation, NLD levees, habitat maps). Seeded by plant ID so it's stable."""
    records = []
    for plant in plants:
        rng = random.Random(plant["id"] * 31)
        coastal = plant["county"] in COASTAL_COUNTIES and rng.random() < 0.6
        attrs = dict(
            coastal=coastal,
            near_river="river" in plant["name"].lower() or rng.random() < 0.18,
            elevation_ft=round(rng.uniform(4, 18) if coastal else rng.uniform(20, 220)),
            wildlife_habitat=round(rng.uniform(0.1, 0.8), 2),
        )
        attrs.update(DEMO_SITE_LAYER.get(plant["id"], {}))
        records.append(SiteRecord(**plant, **attrs))
    return records


def _alerts(now) -> list[tuple[HazardAlert, bool]]:
    def alert(id, site, type, severity, title, message, minutes_ago, source, acked):
        return HazardAlert(id=id, site_id=site, type=type, severity=severity, title=title, message=message,
                           issued_at=now - timedelta(minutes=minutes_ago), source=source), acked

    return [
        alert("seed-gnv-gator", 664, HazardType.wildlife, AlertSeverity.advisory, "Alligator at the cooling pond",
              "About 6 ft alligator on the south bank. Keep 30 ft away and use the north gate.", 55, "Crew report", True),
        alert("seed-flood", 627, HazardType.flood, AlertSeverity.warning, "Flood risk after overnight rain",
              "2.9 in. fell overnight. Check trench walls before entry and avoid the north vault.", 120, "NWS", False),
        alert("seed-heat", 54466, HazardType.heat, AlertSeverity.warning, "Extreme heat: mandatory rest cycles",
              "Heat index reaches 111°F at 2 PM. 15-minute shaded rest every 45 minutes.", 75, "Hazard model", True),
        alert("seed-gator", 56518, HazardType.wildlife, AlertSeverity.advisory, "Alligator sighting",
              "About 7 ft alligator near the retention pond fence. Keep 30 ft away.", 40, "Crew report", True),
        alert("seed-tide", 617, HazardType.flood, AlertSeverity.advisory, "King tide at 11:20 AM",
              "Move equipment off the east dock before high tide. Avoid low vaults.", 192, "NOAA Tides", True),
        alert("seed-cleared", 617, HazardType.lightning, AlertSeverity.advisory, "Lightning hold cleared",
              "No strikes within 10 mi for 30 minutes. Work resumed.", 210, "Lightning network", True),
        alert("seed-soil", 627, HazardType.soil_saturation, AlertSeverity.advisory, "Soil saturation high",
              "Soil moisture is 94%. Shore excavations deeper than 5 ft.", 240, "Open-Meteo", True),
        alert("seed-smoke", 136, HazardType.wildfire, AlertSeverity.advisory, "Smoke advisory",
              "Prescribed burn 8 mi upwind. Expect reduced air quality until evening.", 26 * 60,
              "Florida Forest Service", True),
        alert("seed-riviera-heat", 619, HazardType.heat, AlertSeverity.warning, "Heat advisory",
              "Heat index 104°F expected. Add a water break every 20 minutes.", 28 * 60, "NWS", True),
    ]


def _reports(now) -> list[StoredReport]:
    def report(id, site, type, notes, reporter, minutes_ago):
        return StoredReport(id=id, site_id=site, type=type, notes=notes, reporter=reporter,
                            created_at=now - timedelta(minutes=minutes_ago))

    return [
        report("rep-gnv", 664, "wildlife", "About 6 ft alligator on the south bank of the cooling pond.", "D. Nguyen", 55),
        report("rep-1", 56518, "wildlife", "About 7 ft alligator near the retention pond fence.", "J. Alvarez", 40),
        report("rep-2", 54466, "heat", "Shade tent at the cooling tower blew over. Crew has no shade.", "T. Brooks", 62),
        report("rep-3", 627, "flood", "Standing water about 8 in. deep at the north vault.", "M. Chen", 150),
        report("rep-4", 617, "other", "Fence panel down at the east dock gate.", "R. Patel", 300),
    ]


async def seed(repo: Repository, sites_file: str) -> None:
    await repo.upsert_sites(site_records(load_plants(sites_file)))

    # Local-development accounts only. Real users come from the identity provider.
    password = os.environ.get("DEMO_PASSWORD") or "demo"
    for username, name, role in [("supervisor", "Demo Supervisor", Role.supervisor),
                                 ("crew", "Demo Crew", Role.crew)]:
        await repo.upsert_user(UserRecord(username=username, display_name=name,
                                          password_hash=hash_password(password), role=role))

    now = utcnow()
    for report in _reports(now):
        await repo.save_report(report)
    for alert, acked in _alerts(now):
        await repo.save_alert(alert)
        if acked:
            await repo.acknowledge_alert(alert.id, DEMO_USER_ID)
