#!/usr/bin/env python3
"""CLI tool to batch-geocode entries.location values via Nominatim.

Usage examples::

    python tools/geocode_locations.py
    python tools/geocode_locations.py --limit 100
    python tools/geocode_locations.py --retry-failed
    python tools/geocode_locations.py --dry-run --limit 10

Must be run from the project root directory (the folder containing
``backend/`` and ``tools/``).
"""

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so ``from backend.geocoder import ...``
# works when this script is run directly (e.g. python tools/geocode_locations.py).
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.geocoder import run_batch  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Batch-geocode entries.location values via the Nominatim API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of locations to geocode in this run (default: all).",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        default=False,
        help="Re-attempt locations whose previous geocoding produced source='failed'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Perform lookups but do not write results to the database."
            "  Useful for previewing before committing."
        ),
    )
    return parser


def main() -> None:
    """Entry point: parse arguments and run the batch geocoder."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = _build_parser()
    args = parser.parse_args()

    run_batch(
        limit=args.limit,
        retry_failed=args.retry_failed,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
