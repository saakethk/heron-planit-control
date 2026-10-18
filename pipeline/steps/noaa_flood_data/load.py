"""Loads NOAA flood events and balanced pseudo-absence controls into incidents.db."""

from pathlib import Path
import sqlite3
from typing import Optional, Union
import pandas as pd

from pipeline.steps.osha_incident_data.helpers.load_helper import generate_control_samples


def build_noaa_dataset(flood_df: pd.DataFrame, random_state: int = 42) -> pd.DataFrame:
    """Pairs NOAA flood events with deterministic 1:1 control dates."""
    if flood_df.empty:
        return pd.DataFrame()

    print("[NOAA] Generating paired pseudo-absence controls for flood events...")
    # Generate 1:1 control dates using the same 30-day temporal buffer
    control_df = generate_control_samples(
        input_data=flood_df,
        buffer_days=30,
        random_state=random_state,
    )

    # Standardize positive flood incidents
    positives = pd.DataFrame(
        {
            "ID": flood_df["ID"],
            "Latitude": flood_df["Latitude"],
            "Longitude": flood_df["Longitude"],
            "Date": pd.to_datetime(flood_df["Date"]).dt.date,
            "incident_type": "Flood",
            "is_incident": True,
        }
    )

    # Standardize negative control records
    negatives = pd.DataFrame(
        {
            "ID": control_df["ID"].astype(str) + "_ctrl",
            "Latitude": control_df["Latitude"],
            "Longitude": control_df["Longitude"],
            "Date": pd.to_datetime(control_df["Date"]).dt.date,
            "incident_type": "None",
            "is_incident": False,
        }
    )

    combined = pd.concat([positives, negatives], ignore_index=True)
    return combined


def load_floods_to_sqlite(
    flood_and_controls_df: pd.DataFrame,
    db_path: Optional[Union[str, Path]] = None,
    table_name: str = "clean_incident_data",
) -> int:
    """Upserts NOAA flood events and controls into clean_incident_data."""
    if flood_and_controls_df.empty:
        return 0

    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"

    dest_db = Path(db_path)
    with sqlite3.connect(dest_db) as conn:
        flood_and_controls_df.to_sql("temp_noaa_batch", conn, if_exists="replace", index=False)
        cursor = conn.cursor()
        cols = ", ".join(flood_and_controls_df.columns)
        cursor.execute(
            f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_noaa_batch
            """
        )
        cursor.execute("DROP TABLE IF EXISTS temp_noaa_batch")
        conn.commit()

    print(f"[SQL] Added {len(flood_and_controls_df):,} NOAA flood & control records into '{table_name}'")
    return len(flood_and_controls_df)
