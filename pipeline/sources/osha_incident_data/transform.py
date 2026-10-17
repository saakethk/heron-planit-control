"""Reduces all the incidents to just a smaller subset of the relevant data for environmental-caused incidents."""

from pathlib import Path
from typing import Optional, Union
import pandas as pd

from pipeline.sources.osha_incident_data.transform_helper import classify_narrative


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


def transform_incident_data(
    input_csv_path: Optional[Union[str, Path]] = None,
    output_csv_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Reads OSHA incident CSV, filters to environmental categories, and saves the result."""
    base_dir = Path(__file__).resolve().parent.parent.parent

    if input_csv_path is None:
        input_csv_path = base_dir / "data" / "osha_incident_data.csv"

    if output_csv_path is None:
        output_csv_path = base_dir / "data" / "environmental_incidents.csv"

    input_path = Path(input_csv_path)
    output_path = Path(output_csv_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input incident CSV not found at: {input_path}")

    print(f"[TRANSFORM] Ingesting {input_path.name}...")
    df = pd.read_csv(input_path, on_bad_lines="skip", low_memory=False)

    filtered_df = filter_environmental_incidents(df)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered_df.to_csv(output_path, index=False)
    print(f"[TRANSFORM] Retained {len(filtered_df):,} environmental incidents -> {output_path.name}")

    input_path.unlink()
    print(f"[CLEANUP] Removed raw source file: {input_path.name}")

    return filtered_df


if __name__ == "__main__":
    transform_incident_data()
