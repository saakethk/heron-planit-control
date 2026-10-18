"""Pipeline stage for extracting NIFC historical wildfire incident data and loading into incidents.db."""

from pathlib import Path
from pipeline.steps.nifc_wildfire_data.extract import extract_nifc_wildfires
from pipeline.steps.nifc_wildfire_data.load import build_wildfire_dataset, load_wildfires_to_sqlite


def run(min_acres: float = 2000.0, start_date: str = "2015-01-01", end_date: str = "2025-12-31"):
    """Runs extraction and loading of nationwide NIFC wildfire events."""
    print(f"[PIPELINE:NIFC_WILDFIRE] Starting nationwide wildfire extraction ({start_date} to {end_date})...")
    wildfire_df = extract_nifc_wildfires(min_acres=min_acres, start_date=start_date, end_date=end_date)

    if wildfire_df.empty:
        print("[PIPELINE:NIFC_WILDFIRE] No wildfire records found.")
        return

    print(f"[PIPELINE:NIFC_WILDFIRE] Processing {len(wildfire_df):,} wildfire incidents with paired controls...")
    combined_df = build_wildfire_dataset(wildfire_df)

    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    load_wildfires_to_sqlite(combined_df, db_path=db_path)
    print("[PIPELINE:NIFC_WILDFIRE] Completed successfully.")


if __name__ == "__main__":
    run()
