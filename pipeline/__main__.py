"""Main pipeline runner."""

from pipeline.sources.osha_incident_data.__main__ import run as run_osha_pipeline


def main():
    print("[PIPELINE] Initializing run")
    run_osha_pipeline()
    print("[PIPELINE] Run completed successfully")


if __name__ == "__main__":
    main()
