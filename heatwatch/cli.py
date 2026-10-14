"""Terminal entry point. Day 1 only wires up --baseline; the agent loop is Day 2."""
import argparse
import sys

from heatwatch import baseline


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m heatwatch.cli")
    parser.add_argument("question", help="A question about NYC heat and hot water complaints")
    parser.add_argument(
        "--baseline", action="store_true",
        help="Run the fixed, no-model pipeline instead of the agent loop (agent loop lands Day 2)",
    )
    args = parser.parse_args()

    if not args.baseline:
        print("Agent mode isn't built yet (Day 2). Run with --baseline for now.", file=sys.stderr)
        sys.exit(1)

    print(baseline.run_baseline(args.question))


if __name__ == "__main__":
    main()
