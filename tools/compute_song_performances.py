#!/usr/bin/env python3
"""Recompute song_performances — the song-centric index (LISTENING spec §3,
TODO-230) — from olof_songs JOIN olof_events, seeding song_canonical along
the way.

Usage:
    python tools/compute_song_performances.py [--dry-run]

Options:
    --dry-run   Recompute but do not write to the DB (also skips seeding
                song_canonical, which is itself a write); print the summary
                only.

See backend/song_index.py for the normalisation function, seeding logic, and
recompute/wholesale-replace mechanics — this CLI is a thin wrapper around its
run(), mirroring tools/compute_show_picks.py's role for concert_ranker/picks.py.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.song_index import run  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger(__name__)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Recompute song_performances (+ seed song_canonical) from olof_songs"
    )
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="Recompute but do not write to DB; print summary only")
    args = ap.parse_args(argv)

    stats = run(dry_run=args.dry_run)
    print(
        f"\nDone. Performance rows: {stats['performances_written']}"
        f"  Distinct songs: {stats['distinct_songs']}"
        f"  Distinct events: {stats['distinct_events']}"
        f"\nCanonical norms seeded: {stats['canonical_distinct_norms']}"
        f"  Skipped (blank title): {stats['skipped_blank_title']}"
    )


if __name__ == "__main__":
    main()
