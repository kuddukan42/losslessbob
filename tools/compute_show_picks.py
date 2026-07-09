#!/usr/bin/env python3
"""Recompute show_picks — per-date "best of" ranking (Phase 2 of the unified
ranking spec) — from entries.rating, curated_lists, entry_lineage,
quality_recording_scores, and (if present) taper_attributions.

Usage:
    python tools/compute_show_picks.py [--dry-run] [--skip-lineage-refresh]

Options:
    --dry-run               Recompute but do not write to the DB; print the
                             summary only.
    --skip-lineage-refresh  Skip the entry_lineage freshness pass. Use only
                             when lineage is already known current (e.g.
                             repeated test runs); normal usage always refreshes.

Per instructions/SPEC_INTEGRATION_NOTES.md finding F5, this CLI always
refreshes entry_lineage first via tools/parse_lineage.py's run() — it is
hash-guarded incremental, so repeat runs are cheap — before recomputing picks,
so the supersession/derived_from scoring terms never run on stale lineage
data. See instructions/FABLE_UNIFIED_RANKING.md for the design and
concert_ranker/picks.py for the scoring logic.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from concert_ranker.picks import recompute  # noqa: E402
from tools import parse_lineage  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger(__name__)


def run(
    dry_run: bool = False,
    skip_lineage_refresh: bool = False,
    db_path: str | None = None,
) -> dict:
    """Refresh entry_lineage (F5), then recompute show_picks wholesale.

    Args:
        dry_run: Recompute but do not write to the DB.
        skip_lineage_refresh: Skip the parse_lineage.run() freshness pass.
        db_path: Optional database path override.

    Returns:
        Summary stats dict from concert_ranker.picks.recompute().
    """
    if not skip_lineage_refresh:
        _log.info("Refreshing entry_lineage (parse_lineage, incremental)...")
        parse_lineage.run(db_path=db_path)

    _log.info("Recomputing show_picks...")
    stats = recompute(db_path=db_path, dry_run=dry_run)

    print(
        f"\nDone. Total picks: {stats['total']}  Dates: {stats['dates']}"
        + (
            f"\nScore distribution: min={stats['score_min']}"
            f"  median={stats['score_median']}  max={stats['score_max']}"
            if "score_min" in stats else ""
        )
    )
    return stats


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Recompute show_picks from ratings / curated lists / lineage / quality"
    )
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="Recompute but do not write to DB; print summary only")
    ap.add_argument("--skip-lineage-refresh", dest="skip_lineage_refresh", action="store_true",
                    help="Skip the entry_lineage freshness pass")
    args = ap.parse_args(argv)
    run(dry_run=args.dry_run, skip_lineage_refresh=args.skip_lineage_refresh)


if __name__ == "__main__":
    main()
