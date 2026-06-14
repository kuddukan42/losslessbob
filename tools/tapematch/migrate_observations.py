#!/usr/bin/env python3
"""migrate_observations.py — one-shot, idempotent migration for observations.db.

Implements Task 2 of instructions/CC_TAPEMATCH_FIXES.md:

1. Confirms run versioning columns exist (``run_id`` + ``run_at``; the latter
   already fills the role the spec calls ``run_timestamp`` — no new column
   is added).
2. Normalizes pair-key ordering so ``lb_a < lb_b`` always holds, swapping the
   ``*_a``/``*_b`` columns on any row that violates it. This guarantees
   (A, B) and (B, A) never coexist as distinct keys.
3. Creates an index and the ``latest_pairs`` view, which returns one row per
   normalized (concert_date, lb_a, lb_b) key — the most recent verdict by
   ``run_at`` (ties broken by ``id``).

Usage:
    .venv/bin/python3 tools/tapematch/migrate_observations.py            # dry run
    .venv/bin/python3 tools/tapematch/migrate_observations.py --apply    # write changes

Dry run prints intended changes without writing. ``--apply`` first backs up
observations.db to ``observations.db.bak-YYYYMMDD_HHMMSS``.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

OBS_DB_PATH = Path(__file__).parent / "observations.db"

# (a_column, b_column) pairs to swap when normalizing lb_a/lb_b ordering.
# corr, tapematch_verdict, lb_says_same, lb_relation_text, human_judgment and
# human_notes are symmetric/pair-level fields and are left untouched.
SWAP_COLUMN_PAIRS = [
    ("lb_a", "lb_b"),
    ("folder_a", "folder_b"),
    ("family_id_a", "family_id_b"),
    ("speed_ppm_a", "speed_ppm_b"),
    ("speed_kind_a", "speed_kind_b"),
    ("hf_ceiling_hz_a", "hf_ceiling_hz_b"),
    ("noise_floor_db_a", "noise_floor_db_b"),
    ("dc_asymmetry_a", "dc_asymmetry_b"),
    ("perf_dur_sec_a", "perf_dur_sec_b"),
    ("track_count_a", "track_count_b"),
    ("dominant_ext_a", "dominant_ext_b"),
]

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_pairs_latest "
    "ON pairs(concert_date, lb_a, lb_b, run_at)"
)

LATEST_PAIRS_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS latest_pairs AS
SELECT p.*
FROM pairs p
WHERE p.id = (
    SELECT p2.id FROM pairs p2
    WHERE p2.concert_date = p.concert_date
      AND p2.lb_a = p.lb_a
      AND p2.lb_b = p.lb_b
    ORDER BY p2.run_at DESC, p2.id DESC
    LIMIT 1
)
"""


def inspect_schema(conn: sqlite3.Connection) -> None:
    """Print run-versioning column status for the pairs table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pairs)")}
    print(f"pairs.run_id present: {'run_id' in cols}")
    print(f"pairs.run_at present: {'run_at' in cols}")
    print(f"pairs.run_timestamp present: {'run_timestamp' in cols}")
    if "run_id" in cols and "run_at" in cols and "run_timestamp" not in cols:
        print(
            "Note: run_id + run_at already cover the spec's run_id/run_timestamp "
            "requirement (run_at is ISO 8601). No new columns added; "
            "latest_pairs orders on run_at."
        )


def find_unordered_rows(conn: sqlite3.Connection) -> list[int]:
    """Return ids of rows where lb_a > lb_b (both non-NULL)."""
    rows = conn.execute(
        "SELECT id FROM pairs WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL AND lb_a > lb_b"
    ).fetchall()
    return [r[0] for r in rows]


def normalize_row(conn: sqlite3.Connection, row_id: int) -> None:
    """Swap the *_a/*_b columns for a single row so lb_a < lb_b."""
    cols = [c for pair in SWAP_COLUMN_PAIRS for c in pair]
    row = conn.execute(
        f"SELECT {','.join(cols)} FROM pairs WHERE id = ?", (row_id,)
    ).fetchone()
    values = dict(zip(cols, row))

    set_clauses = []
    params: list = []
    for a_col, b_col in SWAP_COLUMN_PAIRS:
        set_clauses.append(f"{a_col} = ?")
        set_clauses.append(f"{b_col} = ?")
        params.append(values[b_col])
        params.append(values[a_col])
    params.append(row_id)

    conn.execute(
        f"UPDATE pairs SET {', '.join(set_clauses)} WHERE id = ?", params
    )


def backup_db() -> Path:
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = OBS_DB_PATH.with_name(OBS_DB_PATH.name + f".bak-{suffix}")
    shutil.copy2(OBS_DB_PATH, backup_path)
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write changes (default is dry-run, no writes)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(str(OBS_DB_PATH))
    inspect_schema(conn)

    unordered = find_unordered_rows(conn)
    print(f"\nRows with lb_a > lb_b: {len(unordered)}")

    has_view = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='latest_pairs'"
    ).fetchone() is not None
    has_index = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pairs_latest'"
    ).fetchone() is not None
    print(f"latest_pairs view present: {has_view}")
    print(f"idx_pairs_latest index present: {has_index}")

    if not args.apply:
        print("\nDRY RUN — no changes written. Re-run with --apply to write changes.")
        if unordered:
            preview = unordered[:10]
            print(f"  would normalize {len(unordered)} row(s), e.g. ids: {preview}")
        if not has_index:
            print(f"  would create index: {INDEX_SQL}")
        if not has_view:
            print("  would create view: latest_pairs")
        conn.close()
        return

    if unordered or not has_view or not has_index:
        backup_path = backup_db()
        print(f"\nBacked up observations.db to {backup_path}")

    for row_id in unordered:
        normalize_row(conn, row_id)
    conn.commit()
    print(f"Normalized {len(unordered)} row(s)")

    conn.execute(INDEX_SQL)
    conn.execute(LATEST_PAIRS_VIEW_SQL)
    conn.commit()
    print("Ensured idx_pairs_latest index and latest_pairs view exist")

    # Verify: one latest_pairs row per normalized (concert_date, lb_a, lb_b) key.
    distinct_keys = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT concert_date, lb_a, lb_b FROM pairs "
        "WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL)"
    ).fetchone()[0]
    latest_rows = conn.execute(
        "SELECT COUNT(*) FROM latest_pairs WHERE lb_a IS NOT NULL AND lb_b IS NOT NULL"
    ).fetchone()[0]
    print(f"\nDistinct (concert_date, lb_a, lb_b) keys: {distinct_keys}")
    print(f"latest_pairs rows for those keys: {latest_rows}")
    if distinct_keys != latest_rows:
        print("WARNING: latest_pairs row count does not match distinct key count.")

    remaining_unordered = len(find_unordered_rows(conn))
    print(f"Remaining lb_a > lb_b rows: {remaining_unordered}")

    conn.close()


if __name__ == "__main__":
    main()
