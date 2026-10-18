"""Pipeline stage for extracting NOAA historical coastal flood data and loading into incidents.db."""

from pathlib import Path
from typing import Optional
from pipeline.steps.noaa_flood_data.extract import extract_noaa_floods
from pipeline.steps.noaa_flood_data.load import build_noaa_dataset, load_floods_to_sqlite


def run(state_filter: Optional[str] = None):
    """Runs extraction and loading of NOAA high tide flood events."""
    print("[PIPELINE:NOAA_FLOOD] Starting extraction of historical flood records (2015-2025)...")
    flood_df = extract_noaa_floods(state_filter=state_filter)

    if flood_df.empty:
        print("[PIPELINE:NOAA_FLOOD] No flood records found.")
        return

    print(f"[PIPELINE:NOAA_FLOOD] Processing {len(flood_df):,} flood incidents with paired controls...")
    combined_df = build_noaa_dataset(flood_df)

    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    load_floods_to_sqlite(combined_df, db_path=db_path)
    print("[PIPELINE:NOAA_FLOOD] Completed successfully.")


if __name__ == "__main__":
    run()
