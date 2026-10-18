from pipeline.steps.osha_incident_data.__main__ import run as run_osha_pipeline
from pipeline.steps.noaa_flood_data.__main__ import run as run_noaa_flood_pipeline
from pipeline.steps.noaa_lightning_data.__main__ import run as run_noaa_lightning_pipeline
from pipeline.steps.nifc_wildfire_data.__main__ import run as run_nifc_wildfire_pipeline
from pipeline.steps.weather_data.__main__ import run as run_weather_pipeline


def main():
    print("[PIPELINE] Initializing run")

    print("\n--- Stage 1: OSHA Incidents & Control Sampling ---")
    run_osha_pipeline()

    print("\n--- Stage 2: NOAA Nationwide Coastal Flood Ingestion ---")
    run_noaa_flood_pipeline()

    print("\n--- Stage 3: NOAA Nationwide Lightning Strike Ingestion ---")
    run_noaa_lightning_pipeline()

    print("\n--- Stage 4: NIFC Nationwide Wildfire Incident Ingestion ---")
    run_nifc_wildfire_pipeline()

    print("\n--- Stage 5: Weather Feature Extraction ---")
    run_weather_pipeline()

    print("\n[PIPELINE] Run completed successfully")


if __name__ == "__main__":
    main()
