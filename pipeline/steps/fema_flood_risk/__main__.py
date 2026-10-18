import argparse
from pipeline.steps.fema_flood_risk.extract import sync_fema_flood_data


def main():
    parser = argparse.ArgumentParser(description="Synchronizes FEMA NFHL Flood Hazard Zones into SQLite.")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent query workers (default: 4)")
    parser.add_argument("--all", action="store_true", help="Sync all coordinates rather than only is_sampled = 1")
    args = parser.parse_args()

    sync_fema_flood_data(only_sampled=not args.all, max_workers=args.workers)


if __name__ == "__main__":
    main()
