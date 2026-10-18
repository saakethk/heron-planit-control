"""Pipeline stage for extracting and loading weather features with incremental writes and auto-resume."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sqlite3
import time
from typing import Optional
import pandas as pd

from pipeline.steps.weather_data.extract import (
    fetch_weather_for_record,
    get_openmeteo_client,
)
from pipeline.steps.weather_data.arco_era5 import (
    fetch_weather_arco_era5,
    get_arco_client,
)
from pipeline.steps.weather_data.nasa_power import (
    fetch_weather_nasa_power,
    get_nasa_power_session,
)
from pipeline.steps.weather_data.load import append_weather_batch, init_weather_table


def get_pending_records(
    conn: sqlite3.Connection,
    limit: Optional[int] = None,
    only_sampled: bool = True,
) -> pd.DataFrame:
    """Retrieves records not yet fetched in weather_data.
    
    If `only_sampled=True` and rows with `is_sampled = 1` exist, restricts
    queries strictly to those representative sampled rows.
    """
    init_weather_table(conn)

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clean_incident_data)")
    cols = [col[1] for col in cursor.fetchall()]

    use_sampled = False
    if only_sampled and "is_sampled" in cols:
        cursor.execute("SELECT COUNT(*) FROM clean_incident_data WHERE is_sampled = 1")
        cnt = cursor.fetchone()[0]
        if cnt > 0:
            use_sampled = True

    where_clause = "WHERE c.is_sampled = 1 AND w.ID IS NULL" if use_sampled else "WHERE w.ID IS NULL"

    query = f"""
        WITH ranked AS (
            SELECT 
                c.ID, c.Latitude, c.Longitude, c.Date, c.incident_type,
                ROW_NUMBER() OVER (PARTITION BY c.incident_type ORDER BY c.Date DESC) as rn
            FROM clean_incident_data c
            LEFT JOIN weather_data w ON c.ID = w.ID
            {where_clause}
        )
        SELECT ID, Latitude, Longitude, Date, incident_type
        FROM ranked
        ORDER BY rn, incident_type
    """
    if limit is not None:
        query += f" LIMIT {limit}"
    return pd.read_sql(query, conn)


def run(
    batch_size: int = 50,
    limit: Optional[int] = None,
    engine: str = "hybrid",
    max_workers: int = 6,
    only_sampled: bool = True,
):
    """Fetches weather metrics with high-throughput concurrent batching and auto-resume.

    - engine:
        'hybrid'     (Default: NASA POWER primary with instantaneous Open-Meteo fallback on throttle/error)
        'nasa_power' (Fast US government NASA Langley API with soil moisture & all 20 features)
        'openmeteo'  (Historical Archive API ~0.2s/record)
        'arco_era5'  (Google Cloud direct zarr array access)
    - Prioritizes Wildfire, Lightning, and Flood first so ML models get balanced training data immediately.
    - Flushes batches to SQLite progressively every 50 records.
    - Automatically resumes from where it left off.
    """
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}. Run incident pipelines first.")

    with sqlite3.connect(db_path) as conn:
        already_done = pd.read_sql("SELECT COUNT(*) FROM weather_data", conn).iloc[0, 0]
        pending_df = get_pending_records(conn, limit=limit)

    total_pending = len(pending_df)
    if total_pending == 0:
        print(f"[PIPELINE:WEATHER] All records already processed ({already_done:,} records in weather_data). Nothing to do.")
        return

    print(f"[PIPELINE:WEATHER] Engine: {engine.upper()} | Workers: {max_workers} | Done: {already_done:,} | Pending: {total_pending:,}")

    om_client = None
    if engine in ("hybrid", "openmeteo"):
        om_client = get_openmeteo_client()

    if engine == "hybrid":
        def fetch_worker(row_dict):
            t0 = time.time()
            # 1. Primary: NASA POWER
            try:
                res = fetch_weather_nasa_power(
                    record_id=row_dict["ID"],
                    latitude=row_dict["Latitude"],
                    longitude=row_dict["Longitude"],
                    date_str=row_dict["Date"],
                )
                if res:
                    return res, time.time() - t0
            except Exception:
                pass

            # 2. Resilient Fallback: Open-Meteo
            try:
                res = fetch_weather_for_record(
                    client=om_client,
                    record_id=row_dict["ID"],
                    latitude=row_dict["Latitude"],
                    longitude=row_dict["Longitude"],
                    date_str=row_dict["Date"],
                )
                if res:
                    return res, time.time() - t0
            except Exception:
                pass

            return None, time.time() - t0

    elif engine == "nasa_power":
        def fetch_worker(row_dict):
            t0 = time.time()
            res = fetch_weather_nasa_power(
                record_id=row_dict["ID"],
                latitude=row_dict["Latitude"],
                longitude=row_dict["Longitude"],
                date_str=row_dict["Date"],
            )
            return res, time.time() - t0

    elif engine == "arco_era5":
        client = get_arco_client()

        def fetch_worker(row_dict):
            t0 = time.time()
            res = fetch_weather_arco_era5(
                client=client,
                record_id=row_dict["ID"],
                latitude=row_dict["Latitude"],
                longitude=row_dict["Longitude"],
                date_str=row_dict["Date"],
            )
            return res, time.time() - t0

    else:
        def fetch_worker(row_dict):
            t0 = time.time()
            res = fetch_weather_for_record(
                client=om_client,
                record_id=row_dict["ID"],
                latitude=row_dict["Latitude"],
                longitude=row_dict["Longitude"],
                date_str=row_dict["Date"],
            )
            return res, time.time() - t0

    records_list = pending_df.to_dict(orient="records")
    processed_count = 0
    total_batches = (len(records_list) + batch_size - 1) // batch_size
    overall_t0 = time.time()

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        for batch_idx in range(total_batches):
            batch_slice = records_list[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            batch_t0 = time.time()
            batch_results = []

            future_to_rec = {executor.submit(fetch_worker, rec): rec for rec in batch_slice}
            for future in as_completed(future_to_rec):
                try:
                    res, elapsed = future.result()
                    if res:
                        batch_results.append(res)
                except Exception:
                    pass

            if batch_results:
                batch_df = pd.DataFrame(batch_results)
                # Keep only valid 20 weather columns + ID
                cols_to_keep = ["ID"] + [c for c in batch_df.columns if c != "ID" and not c.startswith("_")]
                append_weather_batch(batch_df[cols_to_keep], db_path=db_path)
                processed_count += len(batch_df)

            batch_elapsed = time.time() - batch_t0
            cum_elapsed = time.time() - overall_t0

            print(
                f"[WEATHER:{engine.upper()}] Batch {batch_idx + 1}/{total_batches} "
                f"({len(batch_results)} records in {batch_elapsed:.1f}s, {len(batch_results)/max(batch_elapsed, 0.1):.1f} rec/s) | "
                f"Total Synced: {processed_count:,}/{total_pending:,} ({processed_count / total_pending * 100:.1f}%)"
            )
            time.sleep(0.05)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    print(f"[PIPELINE:WEATHER] Successfully extracted and stored {processed_count:,} records in {time.time()-overall_t0:.1f}s.")


if __name__ == "__main__":
    run()
