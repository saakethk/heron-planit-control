"""
Downloads the full official OSHA Severe Injury Reports CSV dataset from the default archive.
"""

from pathlib import Path
import io
import zipfile
import requests
import pandas as pd

OSHA_ZIP_URL = "https://www.osha.gov/sites/default/files/January2015toNovember2025.zip"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def download_incident_csv(output_path = None) -> Path:
    """
    Downloads the default OSHA zip archive and extracts the CSV directly to disk.
    Contains all 100,000+ severe injury records from 2015 to present.
    """
    if output_path is None:
        output_path = Path(__file__).resolve().parent.parent / "data" / "osha_incident_data.csv"

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading full OSHA dataset from: {OSHA_ZIP_URL}...")
    resp = requests.get(OSHA_ZIP_URL, headers=HEADERS, stream=True, timeout=180)
    resp.raise_for_status()

    # Extract the CSV from the ZIP archive
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_names = [name for name in z.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise FileNotFoundError("No CSV file found inside the OSHA zip archive.")

        target_csv_name = csv_names[0]
        print(f"Extracting '{target_csv_name}' -> {dest}...")
        with z.open(target_csv_name) as source, open(dest, "wb") as target:
            target.write(source.read())

    print(f"Saved full CSV: {dest} ({dest.stat().st_size / (1024 * 1024):.2f} MB)")
    return dest


def get_incident_data() -> pd.DataFrame:
    """
    Loads and returns the complete OSHA dataset as a pandas DataFrame.
    """
    csv_path = download_incident_csv()
    return pd.read_csv(csv_path, on_bad_lines="skip", low_memory=False)


if __name__ == "__main__":
    download_incident_csv()