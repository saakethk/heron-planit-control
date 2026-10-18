"""Unified dataset preparation for model training and benchmarking.

Loads clean_incident_data and weather_data from incidents.db, performs
deterministic feature engineering, and exports a stratified train/test split.
"""

from pathlib import Path
import sqlite3
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURE_COLS = [
    # Meteorological temperature metrics
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    # Moisture & precipitation
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "relative_humidity_2m_mean",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    # Wind & radiation
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    # Soil metrics
    "soil_moisture_0_to_100cm_mean",
    "soil_temperature_0_to_100cm_mean",
    "weather_code",
    # Spatial & temporal engineered features
    "month_sin",
    "month_cos",
    "Latitude",
    "Longitude",
]

CORE_METEOROLOGICAL_CLASSES = [
    "None",
    "Extreme Heat",
    "Flood",
    "Lightning",
    "Wildfire",
]

ALL_CLASSES = [
    "None",
    "Extreme Heat",
    "Flood",
    "Lightning",
    "Wildfire",
    "Wildlife",
    "Soil Saturation",
]

CLASS_NAMES = CORE_METEOROLOGICAL_CLASSES
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASS_NAMES)}
IDX_TO_CLASS = {i: name for i, name in enumerate(CLASS_NAMES)}


def load_raw_dataset(db_path: Path, only_sampled: bool = True) -> pd.DataFrame:
    """Queries and joins incident labels with weather metrics on ID.
    
    If `only_sampled=True` and rows with `is_sampled = 1` exist, restricts loading
    strictly to those representative marked rows.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clean_incident_data)")
        cols = [c[1] for c in cursor.fetchall()]

        where_clause = ""
        if only_sampled and "is_sampled" in cols:
            cursor.execute("SELECT COUNT(*) FROM clean_incident_data WHERE is_sampled = 1")
            cnt = cursor.fetchone()[0]
            if cnt > 0:
                where_clause = "WHERE c.is_sampled = 1"

        query = f"""
            SELECT 
                c.ID,
                c.Latitude,
                c.Longitude,
                c.Date,
                c.incident_type,
                c.is_incident,
                w.weather_code,
                w.temperature_2m_mean,
                w.temperature_2m_max,
                w.temperature_2m_min,
                w.apparent_temperature_mean,
                w.apparent_temperature_max,
                w.apparent_temperature_min,
                w.precipitation_sum,
                w.rain_sum,
                w.snowfall_sum,
                w.precipitation_hours,
                w.wind_speed_10m_max,
                w.wind_gusts_10m_max,
                w.shortwave_radiation_sum,
                w.et0_fao_evapotranspiration,
                w.relative_humidity_2m_mean,
                w.relative_humidity_2m_max,
                w.relative_humidity_2m_min,
                w.soil_moisture_0_to_100cm_mean,
                w.soil_temperature_0_to_100cm_mean
            FROM clean_incident_data c
            INNER JOIN weather_data w ON c.ID = w.ID
            {where_clause}
        """
        df = pd.read_sql(query, conn)
    return df


def sample_balanced_per_category(
    df: pd.DataFrame,
    max_samples_per_class: int = 600,
    random_state: int = 42,
) -> pd.DataFrame:
    """Downsamples over-represented categories so each category has a similar number of records."""
    sampled_groups = [
        g.sample(n=min(len(g), max_samples_per_class), random_state=random_state)
        for _, g in df.groupby("incident_type")
    ]
    return pd.concat(sampled_groups).sample(frac=1.0, random_state=random_state).reset_index(drop=True)


def engineer_features(
    df: pd.DataFrame,
    class_to_idx: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Adds cyclical month seasonality and cleans numerical values."""
    if class_to_idx is None:
        class_to_idx = CLASS_TO_IDX

    df = df.copy()
    dt = pd.to_datetime(df["Date"], errors="coerce")
    month = dt.dt.month.fillna(6).astype(int)

    # Cyclical sin/cos encoding for calendar month (1 to 12)
    df["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * month / 12.0)

    # Target indices
    df["target_class"] = df["incident_type"].map(class_to_idx)
    df["target_binary"] = df["is_incident"].astype(int)

    # Clean missing values if any
    for col in FEATURE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def get_stratified_dataset(
    db_path: Path,
    test_size: float = 0.2,
    random_state: int = 42,
    max_samples_per_class: Optional[int] = 600,
    only_sampled: bool = True,
    exclude_classes: Optional[Union[List[str], Tuple[str, ...]]] = ("Soil Saturation", "Wildlife"),
) -> Dict:
    """Creates a uniform, stratified train/test split across all candidate models.
    
    - exclude_classes: Defaults to ('Soil Saturation', 'Wildlife') to focus purely
      on the 5 core meteorological hazards (None, Heat, Flood, Lightning, Wildfire).
    - max_samples_per_class: Caps each category to a similar amount (default 600).
    - only_sampled: If True, reads from rows marked `is_sampled = 1`.
    """
    raw_df = load_raw_dataset(db_path, only_sampled=only_sampled)

    active_classes = list(CORE_METEOROLOGICAL_CLASSES)
    if exclude_classes:
        raw_df = raw_df[~raw_df["incident_type"].isin(exclude_classes)].copy()
        active_classes = [c for c in ALL_CLASSES if c not in exclude_classes]

    active_c2i = {c: i for i, c in enumerate(active_classes)}
    active_i2c = {i: c for i, c in enumerate(active_classes)}

    if max_samples_per_class is not None:
        raw_df = sample_balanced_per_category(
            raw_df,
            max_samples_per_class=max_samples_per_class,
            random_state=random_state,
        )

    df = engineer_features(raw_df, class_to_idx=active_c2i)

    X = df[FEATURE_COLS].values
    y_multi = df["target_class"].values
    y_binary = df["target_binary"].values

    # Stratified split preserving exact category proportions
    indices = np.arange(len(df))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=test_size,
        random_state=random_state,
        stratify=y_multi,
    )

    X_train, X_test = X[train_idx], X[test_idx]
    y_multi_train, y_multi_test = y_multi[train_idx], y_multi[test_idx]
    y_bin_train, y_bin_test = y_binary[train_idx], y_binary[test_idx]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    return {
        "X_train": X_train,
        "X_test": X_test,
        "X_train_scaled": X_train_scaled,
        "X_test_scaled": X_test_scaled,
        "y_multi_train": y_multi_train,
        "y_multi_test": y_multi_test,
        "y_bin_train": y_bin_train,
        "y_bin_test": y_bin_test,
        "scaler": scaler,
        "feature_names": FEATURE_COLS,
        "class_names": CLASS_NAMES,
        "train_df": df.iloc[train_idx].reset_index(drop=True),
        "test_df": df.iloc[test_idx].reset_index(drop=True),
    }


if __name__ == "__main__":
    db = Path(__file__).resolve().parent.parent / "data" / "incidents.db"
    data = get_stratified_dataset(db)
    print("Train set size:", len(data["X_train"]))
    print("Test set size:", len(data["X_test"]))
    print("Features count:", len(data["feature_names"]))
    print("Class distribution in Test Set:")
    test_series = pd.Series(data["y_multi_test"]).map(IDX_TO_CLASS)
    print(test_series.value_counts())
