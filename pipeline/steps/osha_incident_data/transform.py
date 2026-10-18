"""Reduces raw incidents and merges with control samples into a single dataset."""

from pathlib import Path
from typing import Optional, Union
import pandas as pd

from pipeline.steps.osha_incident_data.helpers.transform_helper import classify_narrative
from pipeline.steps.osha_incident_data.helpers.load_helper import generate_control_samples


def filter_environmental_incidents(
    df: pd.DataFrame,
    narrative_col: Optional[str] = None,
) -> pd.DataFrame:
    """Classifies narratives and filters dataframe to only environmental incident categories."""
    if narrative_col is None:
        if "Final Narrative" in df.columns:
            narrative_col = "Final Narrative"
        elif "FinalNarrative" in df.columns:
            narrative_col = "FinalNarrative"
        else:
            raise KeyError("Expected column 'Final Narrative' or 'FinalNarrative' in input DataFrame.")

    df = df.copy()
    df["incident_type"] = df[narrative_col].apply(classify_narrative)
    filtered_df = df[df["incident_type"] != "Other (None of the above)"].reset_index(drop=True)
    return filtered_df


def build_unified_dataset(
    incidents_df: pd.DataFrame,
    control_df: pd.DataFrame,
    date_col: str = "EventDate",
) -> pd.DataFrame:
    """Standardizes and merges positive incident records with control (non-incident) records.

    Keeps only necessary modeling columns:
    ['ID', 'Latitude', 'Longitude', 'Date', 'incident_type', 'is_incident']
    """
    if date_col not in incidents_df.columns and "Event Date" in incidents_df.columns:
        date_col = "Event Date"

    # Standardize positive incident records (original OSHA ID preserved)
    positives = pd.DataFrame(
        {
            "ID": incidents_df["ID"].astype(str),
            "Latitude": incidents_df["Latitude"],
            "Longitude": incidents_df["Longitude"],
            "Date": pd.to_datetime(incidents_df[date_col], errors="coerce").dt.date,
            "incident_type": incidents_df["incident_type"],
            "is_incident": True,
        }
    )

    # Standardize control / non-incident records (suffixed with _ctrl)
    negatives = pd.DataFrame(
        {
            "ID": control_df["ID"].astype(str) + "_ctrl",
            "Latitude": control_df["Latitude"],
            "Longitude": control_df["Longitude"],
            "Date": pd.to_datetime(control_df["Date"], errors="coerce").dt.date,
            "incident_type": "None",
            "is_incident": False,
        }
    )

    unified_df = pd.concat([positives, negatives], ignore_index=True)
    return unified_df


def transform_incident_data(
    input_csv_path: Optional[Union[str, Path]] = None,
    output_csv_path: Optional[Union[str, Path]] = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """Reads raw OSHA incident CSV, filters environmental incidents, generates control

    pseudo-absences, and produces one clean dataset containing both incident and
    non-incident records with essential labels.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"

    if input_csv_path is None:
        input_csv_path = data_dir / "osha_incident_data.csv"

    if output_csv_path is None:
        output_csv_path = data_dir / "clean_incident_data.csv"

    input_path = Path(input_csv_path)
    output_path = Path(output_csv_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input incident CSV not found at: {input_path}")

    print(f"[TRANSFORM] Ingesting {input_path.name}...")
    df = pd.read_csv(input_path, on_bad_lines="skip", low_memory=False)

    filtered_df = filter_environmental_incidents(df)
    print(f"[TRANSFORM] Retained {len(filtered_df):,} environmental incidents")

    # Generate pseudo-absence control samples
    print("[TRANSFORM] Generating deterministic control samples...")
    control_df = generate_control_samples(
        input_data=filtered_df,
        buffer_days=30,
        random_state=random_state,
    )

    # Merge into single clean dataset with essential labels
    print("[TRANSFORM] Compiling unified incident & non-incident dataset...")
    unified_df = build_unified_dataset(filtered_df, control_df)

    input_path.unlink()
    print(f"[CLEANUP] Removed raw source file: {input_path.name}")

    return unified_df


if __name__ == "__main__":
    transform_incident_data()
