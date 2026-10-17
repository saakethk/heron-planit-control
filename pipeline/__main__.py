from pathlib import Path
from pipeline.sources.osha_incident_data.__main__ import run as run_osha_pipeline
from pipeline.utility.random_sample import generate_control_samples


def main():
    print("[PIPELINE] Initializing run")

    print("\n--- Phase 1: OSHA Incident Data Extraction & Filtering ---")
    run_osha_pipeline()

    print("\n--- Phase 2: Generating Pseudo-Absence Control Samples ---")
    data_dir = Path(__file__).resolve().parent / "data"
    generate_control_samples(
        input_csv_path=data_dir / "environmental_incidents.csv",
        output_csv_path=data_dir / "control_samples.csv",
    )

    print("\n[PIPELINE] Run completed successfully")


if __name__ == "__main__":
    main()
