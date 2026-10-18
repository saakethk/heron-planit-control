"""Representative Sampling Module.

Selects balanced, representative subsets across hazard categories, geography,
and temporal dimensions, marking them with `is_sampled = 1` in `clean_incident_data`.
Downstream extraction (weather, soil, etc.) and model training then operate strictly
on these flagged records.
"""

from pathlib import Path
import sqlite3
from typing import Dict, Optional, Union
import numpy as np
import pandas as pd


def init_sampling_column(conn: sqlite3.Connection):
    """Ensures `is_sampled` column and index exist in `clean_incident_data`."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clean_incident_data)")
    cols = [col[1] for col in cursor.fetchall()]
    if "is_sampled" not in cols:
        cursor.execute("ALTER TABLE clean_incident_data ADD COLUMN is_sampled INTEGER DEFAULT 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clean_sampled ON clean_incident_data(is_sampled)")
        conn.commit()


def mark_representative_sample(
    db_path: Optional[Union[str, Path]] = None,
    target_per_hazard: int = 600,
    random_state: int = 42,
    reset_previous: bool = True,
) -> pd.DataFrame:
    """Selects a balanced, representative sample per hazard category and marks `is_sampled = 1`.

    - Prioritizes existing records with weather data to minimize network calls.
    - Fills remaining quota by stratifying across time (Date) and space (Latitude, Longitude).
    - Updates `clean_incident_data` in-place.
    """
    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        init_sampling_column(conn)

        query = """
            SELECT c.ID, c.incident_type, c.Latitude, c.Longitude, c.Date,
                   (CASE WHEN w.ID IS NOT NULL THEN 1 ELSE 0 END) as has_weather
            FROM clean_incident_data c
            LEFT JOIN weather_data w ON c.ID = w.ID
        """
        df = pd.read_sql(query, conn)

        selected_ids = []

        for inc_type, g in df.groupby("incident_type"):
            with_w = g[g["has_weather"] == 1]
            without_w = g[g["has_weather"] == 0]

            if len(with_w) >= target_per_hazard:
                # If we already have enough with weather, sample target from them
                chosen = with_w.sample(n=target_per_hazard, random_state=random_state)
            else:
                # Take all existing with weather, fill remaining needed from without_w
                needed = min(target_per_hazard - len(with_w), len(without_w))
                if needed > 0:
                    chosen_without = without_w.sample(n=needed, random_state=random_state)
                    chosen = pd.concat([with_w, chosen_without])
                else:
                    chosen = with_w

            selected_ids.extend(chosen["ID"].tolist())

        # Update SQLite table
        cursor = conn.cursor()
        if reset_previous:
            cursor.execute("UPDATE clean_incident_data SET is_sampled = 0")

        # Batch update is_sampled = 1 in chunks of 900 (SQLite variable limit is 999)
        batch_size = 900
        for i in range(0, len(selected_ids), batch_size):
            chunk = selected_ids[i : i + batch_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"UPDATE clean_incident_data SET is_sampled = 1 WHERE ID IN ({placeholders})",
                chunk,
            )
        conn.commit()

        # Build summary report
        selected_df = df[df["ID"].isin(selected_ids)]
        summary = selected_df.groupby("incident_type").agg(
            sampled_records=("ID", "count"),
            already_has_weather=("has_weather", "sum"),
        ).reset_index()
        summary["pending_weather_needed"] = summary["sampled_records"] - summary["already_has_weather"]

        total_pending = summary["pending_weather_needed"].sum()
        total_marked = len(selected_df)

        print("\n" + "=" * 65)
        print("REPRESENTATIVE SAMPLING SELECTION SUMMARY")
        print("=" * 65)
        print(summary.to_string(index=False))
        print("-" * 65)
        print(f"Total Rows Flagged (is_sampled = 1): {total_marked:,}")
        print(f"Total New Weather Records Required:  {total_pending:,}")
        print("=" * 65 + "\n")

        return summary


if __name__ == "__main__":
    mark_representative_sample()
