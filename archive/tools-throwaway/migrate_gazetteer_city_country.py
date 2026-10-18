"""Rekey venue_geocoded.city_norm on city+country (TODO-352).

Dry-run by default (rolls back); ``--apply`` commits. Back up the DB first.

    .venv/bin/python3 tools/migrate_gazetteer_city_country.py --db PATH [--apply]
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.venue_gazetteer import migrate_city_norm_with_country_stats  # noqa: E402

logger = logging.getLogger("migrate_gazetteer_city_country")


def main() -> int:
    """Run the migration against ``--db`` and log the stats."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="SQLite DB path")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = sqlite3.connect(args.db)
    try:
        stats = migrate_city_norm_with_country_stats(conn)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        logger.info("%s: %s", "APPLIED" if args.apply else "DRY-RUN (rolled back)", stats)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
