"""Pipeline stage for extracting NOAA historical lightning strike data and loading into incidents.db."""

from pathlib import Path
from pipeline.steps.noaa_lightning_data.extract import extract_noaa_lightning
from pipeline.steps.noaa_lightning_data.load import build_lightning_dataset, load_lightning_to_sqlite


def run(start_year: int = 2015, end_year: int = 2025):
    """Runs extraction and loading of nationwide NOAA lightning strike events."""
    print(f"[PIPELINE:NOAA_LIGHTNING] Starting nationwide lightning extraction ({start_year}-{end_year})...")
    lightning_df = extract_noaa_lightning(start_year=start_year, end_year=end_year)

    if lightning_df.empty:
        print("[PIPELINE:NOAA_LIGHTNING] No lightning records found.")
        return

    print(f"[PIPELINE:NOAA_LIGHTNING] Processing {len(lightning_df):,} lightning incidents with paired controls...")
    combined_df = build_lightning_dataset(lightning_df)

    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    load_lightning_to_sqlite(combined_df, db_path=db_path)
    print("[PIPELINE:NOAA_LIGHTNING] Completed successfully.")


if __name__ == "__main__":
    run()
