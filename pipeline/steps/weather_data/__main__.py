"""Pipeline stage for extracting and loading Open-Meteo weather features with incremental writes and auto-resume."""

from pathlib import Path
import sqlite3
from typing import Optional
import pandas as pd

from pipeline.steps.weather_data.extract import (
    fetch_weather_for_record,
    get_openmeteo_client,
)
from pipeline.steps.weather_data.load import append_weather_batch, init_weather_table


def get_pending_records(conn: sqlite3.Connection, limit: Optional[int] = None) -> pd.DataFrame:
    """Retrieves only records that have not yet been fetched in weather_data."""
    init_weather_table(conn)
    query = """
        SELECT c.ID, c.Latitude, c.Longitude, c.Date
        FROM clean_incident_data c
        LEFT JOIN weather_data w ON c.ID = w.ID
        WHERE w.ID IS NULL
    """
    if limit is not None:
        query += f" LIMIT {limit}"
    return pd.read_sql(query, conn)


def run(batch_size: int = 50, limit: Optional[int] = None):
    """Fetches weather metrics with progressive batch writing and auto-resume.

    - Reads only pending IDs not already in weather_data.
    - Flushes batches to SQLite every `batch_size` records.
    - If interrupted, restarting automatically resumes from the last written record.
    """
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}. Run OSHA pipeline first.")

    with sqlite3.connect(db_path) as conn:
        already_done = pd.read_sql("SELECT COUNT(*) FROM weather_data", conn).iloc[0, 0]
        pending_df = get_pending_records(conn, limit=limit)

    total_pending = len(pending_df)
    if total_pending == 0:
        print(f"[PIPELINE:WEATHER] All records already processed ({already_done:,} records in weather_data). Nothing to do.")
        return

    print(f"[PIPELINE:WEATHER] Already processed: {already_done:,} | Pending to fetch: {total_pending:,}")
    client = get_openmeteo_client()

    current_batch = []
    processed_count = 0

    for idx, (_, row) in enumerate(pending_df.iterrows(), start=1):
        weather_row = fetch_weather_for_record(
            client=client,
            record_id=row["ID"],
            latitude=row["Latitude"],
            longitude=row["Longitude"],
            date_str=row["Date"],
        )
        if weather_row:
            current_batch.append(weather_row)

        # Flush batch progressively
        if len(current_batch) >= batch_size or idx == total_pending:
            batch_df = pd.DataFrame(current_batch)
            append_weather_batch(batch_df, db_path=db_path)
            processed_count += len(batch_df)
            print(f"[PIPELINE:WEATHER] Flushed {len(batch_df)} records to DB | Progress: {idx:,} / {total_pending:,} ({idx / total_pending * 100:.1f}%)")
            current_batch.clear()

    print(f"[PIPELINE:WEATHER] Completed! Added {processed_count:,} records to weather_data.")


if __name__ == "__main__":
    run()
