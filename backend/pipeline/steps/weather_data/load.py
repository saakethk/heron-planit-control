"""Loads extracted weather data into the SQLite database in the 'weather_data' table."""

from pathlib import Path
import sqlite3
from typing import Optional, Union
import pandas as pd


def init_weather_table(conn: sqlite3.Connection, table_name: str = "weather_data"):
    """Ensures weather_data table and its primary key index exist."""
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            ID TEXT PRIMARY KEY,
            weather_code REAL,
            temperature_2m_mean REAL,
            temperature_2m_max REAL,
            temperature_2m_min REAL,
            apparent_temperature_mean REAL,
            apparent_temperature_max REAL,
            apparent_temperature_min REAL,
            precipitation_sum REAL,
            rain_sum REAL,
            snowfall_sum REAL,
            precipitation_hours REAL,
            wind_speed_10m_max REAL,
            wind_gusts_10m_max REAL,
            shortwave_radiation_sum REAL,
            et0_fao_evapotranspiration REAL,
            relative_humidity_2m_mean REAL,
            relative_humidity_2m_max REAL,
            relative_humidity_2m_min REAL,
            soil_moisture_0_to_100cm_mean REAL,
            soil_temperature_0_to_100cm_mean REAL
        )
        """
    )
    cursor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_id ON {table_name} (ID)")
    conn.commit()


def append_weather_batch(
    weather_df: pd.DataFrame,
    db_path: Optional[Union[str, Path]] = None,
    table_name: str = "weather_data",
) -> int:
    """Appends an incremental batch of weather records into SQLite table.

    Uses INSERT OR REPLACE to ensure idempotency without creating duplicates.
    """
    if weather_df.empty:
        return 0

    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"

    dest_db = Path(db_path)
    dest_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(dest_db) as conn:
        init_weather_table(conn, table_name=table_name)
        # Load batch into temp staging then upsert into main table
        weather_df.to_sql("temp_weather_batch", conn, if_exists="replace", index=False)
        cursor = conn.cursor()
        cols = ", ".join(weather_df.columns)
        cursor.execute(
            f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_weather_batch
            """
        )
        cursor.execute("DROP TABLE IF EXISTS temp_weather_batch")
        conn.commit()

    return len(weather_df)
