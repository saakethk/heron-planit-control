"""Generates deterministic pseudo-absence control dates for incident locations."""

from datetime import date, timedelta
from pathlib import Path
import random
from typing import Optional, Union
import pandas as pd


def generate_control_samples(
    input_data: Optional[Union[str, Path, pd.DataFrame]] = None,
    output_csv_path: Optional[Union[str, Path]] = None,
    start_date: Optional[Union[str, date]] = None,
    end_date: Optional[Union[str, date]] = None,
    buffer_days: int = 30,
    random_state: int = 42,
) -> pd.DataFrame:
    """Samples deterministic non-incident control dates for each coordinate.

    Enforces a +/- buffer_days exclusion window around all recorded incidents
    at that location to prevent temporal leakage. Given the same random_state,
    output dates are completely reproducible.

    Args:
        input_data: Pre-filtered DataFrame or path to source environmental incidents CSV.
        output_csv_path: Path to write generated control samples CSV.
        start_date: Lower bound for sampling range (defaults to dataset minimum).
        end_date: Upper bound for sampling range (defaults to dataset maximum).
        buffer_days: Exclusion window radius around incident dates (default: 30).
        random_state: Fixed seed for deterministic pseudo-random number generator (default: 42).

    Returns:
        DataFrame with columns ['ID', 'Latitude', 'Longitude', 'Date'].
    """
    if isinstance(input_data, pd.DataFrame):
        df = input_data.copy()
    else:
        if input_data is None:
            input_data = Path(__file__).resolve().parent.parent.parent / "data" / "environmental_incidents.csv"

        input_path = Path(input_data)
        if not input_path.exists():
            raise FileNotFoundError(f"Source incidents file not found: {input_path}")

        df = pd.read_csv(input_path, on_bad_lines="skip", low_memory=False)

    if "Date" in df.columns:
        date_col = "Date"
    elif "EventDate" in df.columns:
        date_col = "EventDate"
    elif "Event Date" in df.columns:
        date_col = "Event Date"
    else:
        raise KeyError("Expected Date or EventDate column in input data.")

    df["ParsedDate"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # Define deterministic search interval
    valid_start = pd.to_datetime(start_date).date() if start_date else df["ParsedDate"].min()
    valid_end = pd.to_datetime(end_date).date() if end_date else df["ParsedDate"].max()

    all_dates = [
        valid_start + timedelta(days=i)
        for i in range((valid_end - valid_start).days + 1)
    ]

    # Map each coordinate to its buffered exclusion dates
    incident_dates_by_coord = {}
    for (lat, lon), group in df.groupby(["Latitude", "Longitude"]):
        excluded = set()
        for d in group["ParsedDate"].dropna():
            for offset in range(-buffer_days, buffer_days + 1):
                excluded.add(d + timedelta(days=offset))
        incident_dates_by_coord[(lat, lon)] = excluded

    # Seed isolated generator for deterministic sampling
    rng = random.Random(random_state)

    # Sample a non-incident date for each record
    control_dates = []
    for _, row in df.iterrows():
        coord = (row["Latitude"], row["Longitude"])
        excluded_dates = incident_dates_by_coord.get(coord, set())

        candidates = [d for d in all_dates if d not in excluded_dates]
        if not candidates:
            raw_incident_dates = set(
                df[(df["Latitude"] == coord[0]) & (df["Longitude"] == coord[1])]["ParsedDate"].dropna()
            )
            candidates = [d for d in all_dates if d not in raw_incident_dates]

        control_dates.append(rng.choice(candidates))

    result_df = pd.DataFrame(
        {
            "ID": df["ID"],
            "Latitude": df["Latitude"],
            "Longitude": df["Longitude"],
            "Date": control_dates,
        }
    )

    if output_csv_path is not None:
        out_path = Path(output_csv_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(out_path, index=False)
        print(f"[SAMPLE] Saved {len(result_df):,} control samples to {out_path.name}")

    return result_df


if __name__ == "__main__":
    output_file = Path(__file__).resolve().parent.parent.parent / "data" / "control_samples.csv"
    generate_control_samples(output_csv_path=output_file)
