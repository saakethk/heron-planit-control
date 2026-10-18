import argparse
from pipeline.steps.representative_sampling.sample import mark_representative_sample


def main():
    parser = argparse.ArgumentParser(description="Marks balanced representative rows with is_sampled = 1.")
    parser.add_argument(
        "--target-per-hazard",
        type=int,
        default=600,
        help="Number of samples to select per hazard category (default: 600)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducible selection (default: 42)",
    )
    args = parser.parse_args()

    mark_representative_sample(
        target_per_hazard=args.target_per_hazard,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
