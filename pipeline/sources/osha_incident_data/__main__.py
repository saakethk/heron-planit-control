"""Runs the extract and transform pipeline for OSHA incident data."""

from pipeline.sources.osha_incident_data.extract import download_incident_csv
from pipeline.sources.osha_incident_data.transform import transform_incident_data


def run():
    print("[PIPELINE:OSHA] Starting data extraction")
    raw_csv_path = download_incident_csv()

    print("[PIPELINE:OSHA] Starting data transformation and classification")
    transform_incident_data(input_csv_path=raw_csv_path)

    print("[PIPELINE:OSHA] Stage completed successfully")


if __name__ == "__main__":
    run()