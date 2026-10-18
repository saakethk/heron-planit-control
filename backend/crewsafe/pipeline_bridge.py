"""Read-only bridge to the data/ML pipeline at the repo root (`pipeline/`).

The pipeline owns the historical ETL, the EIA-860M site registry with FEMA NFHL
flood zones (`data/incidents.db`), and the trained hazard classifier
(`model/artifacts/best_hazard_model.joblib`). The backend reads those and imports
the pipeline's feature list so serving uses exactly the columns the model was
trained on.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from .config import Settings


def pipeline_dir(settings: Settings) -> Path:
    return Path(settings.pipeline_dir)


def database_path(settings: Settings) -> Path:
    return pipeline_dir(settings) / "data" / "incidents.db"


def model_path(settings: Settings) -> Path:
    return Path(settings.model_path) if settings.model_path else \
        pipeline_dir(settings) / "model" / "artifacts" / "best_hazard_model.joblib"


def scaler_path(settings: Settings) -> Path:
    return model_path(settings).with_name("hazard_scaler.joblib")


def import_pipeline(settings: Settings) -> None:
    """Make `import pipeline...` work from the backend process."""
    root = str(pipeline_dir(settings).parent)
    if root not in sys.path:
        sys.path.append(root)


def load_sites(settings: Settings) -> list[dict] | None:
    """Monitored sites joined with their FEMA flood zone, or None if the pipeline
    database isn't present (the seed falls back to the bundled plant list)."""
    path = database_path(settings)
    if not path.exists():
        return None
    query = """
        SELECT m.plant_id, m.plant_name, m.county, m.latitude, m.longitude, m.capacity_mw,
               f.fld_zone, COALESCE(f.is_sfha, 0), COALESCE(f.is_coastal_hazard, 0),
               COALESCE(f.fema_flood_risk_score, 0.05)
        FROM monitored_sites m
        LEFT JOIN fema_flood_risk f
          ON round(m.latitude, 4) = f.Latitude AND round(m.longitude, 4) = f.Longitude
        GROUP BY m.plant_id
        ORDER BY m.capacity_mw DESC
    """
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        rows = conn.execute(query).fetchall()
    return [dict(id=int(pid), name=name, county=county, latitude=lat, longitude=lon, capacity_mw=round(mw or 0.0, 1),
                 flood_zone=zone, fema_sfha=bool(sfha), fema_coastal=bool(coastal), fema_score=float(score))
            for pid, name, county, lat, lon, mw, zone, sfha, coastal, score in rows]
