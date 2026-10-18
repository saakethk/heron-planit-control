"""Loads processed incident and control data into a SQLite database."""

from pathlib import Path
import sqlite3
from typing import Optional, Union
import pandas as pd


def load_to_sqlite(
    data: Optional[Union[pd.DataFrame, str, Path]] = None,
    db_path: Optional[Union[str, Path]] = None,
    table_name: str = "clean_incident_data",
) -> Path:
    """Loads a DataFrame or CSV file into a SQLite database table.

    Args:
        data: DataFrame or path to CSV (defaults to pipeline/data/clean_incident_data.csv).
        db_path: Path to target SQLite database (defaults to pipeline/data/incidents.db).
        table_name: Destination SQL table name.

    Returns:
        Path to the SQLite database file.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"

    if db_path is None:
        db_path = data_dir / "incidents.db"

    dest_db = Path(db_path)
    dest_db.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, pd.DataFrame):
        df = data
    else:
        if data is None:
            data = data_dir / "clean_incident_data.csv"
        csv_path = Path(data)
        if not csv_path.exists():
            raise FileNotFoundError(f"Source file not found at: {csv_path}")
        df = pd.read_csv(csv_path)

    print(f"[SQL] Writing {len(df):,} records into '{table_name}' table at {dest_db.name}...")
    with sqlite3.connect(dest_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                ID TEXT PRIMARY KEY,
                Latitude REAL,
                Longitude REAL,
                Date TEXT,
                incident_type TEXT,
                is_incident INTEGER
            )
            """
        )
        df.to_sql("temp_osha_batch", conn, if_exists="replace", index=False)
        cols = ", ".join(df.columns)
        cursor.execute(
            f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_osha_batch
            """
        )
        cursor.execute("DROP TABLE IF EXISTS temp_osha_batch")

        # Create indexes for fast geospatial and temporal queries
        cursor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_id ON {table_name} (ID)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_coords ON {table_name} (Latitude, Longitude)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name} (Date)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_is_incident ON {table_name} (is_incident)")
        conn.commit()

    print(f"[SQL] Successfully loaded and indexed {dest_db.name} ({dest_db.stat().st_size / (1024 * 1024):.2f} MB)")
    return dest_db


if __name__ == "__main__":
    load_to_sqlite()
