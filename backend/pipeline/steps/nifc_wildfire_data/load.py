"""Loads NIFC wildfire events and balanced pseudo-absence controls into incidents.db."""

from pathlib import Path
import sqlite3
from typing import Optional, Union
import pandas as pd

from pipeline.steps.osha_incident_data.helpers.load_helper import generate_control_samples


def build_wildfire_dataset(wildfire_df: pd.DataFrame, random_state: int = 42) -> pd.DataFrame:
    """Pairs NIFC wildfire events with deterministic 1:1 control dates."""
    if wildfire_df.empty:
        return pd.DataFrame()

    print("[NIFC:WILDFIRE] Generating paired pseudo-absence controls for wildfire events...")
    control_df = generate_control_samples(
        input_data=wildfire_df,
        buffer_days=30,
        random_state=random_state,
    )

    positives = pd.DataFrame(
        {
            "ID": wildfire_df["ID"],
            "Latitude": wildfire_df["Latitude"],
            "Longitude": wildfire_df["Longitude"],
            "Date": pd.to_datetime(wildfire_df["Date"]).dt.date,
            "incident_type": "Wildfire",
            "is_incident": True,
        }
    )

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


def load_wildfires_to_sqlite(
    wildfire_and_controls_df: pd.DataFrame,
    db_path: Optional[Union[str, Path]] = None,
    table_name: str = "clean_incident_data",
) -> int:
    """Upserts NIFC wildfire events and controls into clean_incident_data."""
    if wildfire_and_controls_df.empty:
        return 0

    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"

    dest_db = Path(db_path)
    with sqlite3.connect(dest_db) as conn:
        wildfire_and_controls_df.to_sql("temp_wf_batch", conn, if_exists="replace", index=False)
        cursor = conn.cursor()
        cols = ", ".join(wildfire_and_controls_df.columns)
        cursor.execute(
            f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_wf_batch
            """
        )
        cursor.execute("DROP TABLE IF EXISTS temp_wf_batch")
        conn.commit()

    print(f"[SQL] Added {len(wildfire_and_controls_df):,} NIFC wildfire & control records into '{table_name}'")
    return len(wildfire_and_controls_df)
