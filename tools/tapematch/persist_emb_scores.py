#!/usr/bin/env python3
"""persist_emb_scores.py — write offline-computed embedding scores into
``observations.db`` (CC_TAPEMATCH_ADDON.md Task 6 follow-on, addon_links
rule_d).

Reads ``fullset_pairs_scores.json`` (a flat list of
``{date, lb_a, lb_b, tag, corr, emb_tol2, emb_tol0}`` records, produced
offline by the embedding scorer over the full frozen set) and writes:

    emb_tol2  ->  pairs.emb_score          (aligned +/-2s-window cosine)
    emb_tol0  ->  pairs.emb_score_global   (whole-recording global cosine-max)

onto exactly the ``pairs`` row that the ``latest_pairs`` view resolves to for
each record's ``(concert_date, lb_a, lb_b)`` key — i.e. the row ``latest_pairs``
would return, found via its own id-selection subquery, never a blind
``UPDATE ... WHERE concert_date=? AND lb_a=? AND lb_b=?`` (which could touch a
superseded historical row instead of the current one).

This is a DB-only writer, mirroring ``calibrate_triplet.py``'s read-only
posture but for the write side. It never runs audio and never computes a
score itself — scores are supplied entirely by the input JSON.

Safety rules
------------
* Uses ``tapematch_session.open_obs_db()`` to open the connection, so the
  idempotent ``ALTER TABLE`` that adds ``emb_score``/``emb_score_global`` runs
  first (same schema-bootstrap path every other script relies on) — this is
  the FIRST writer of these two columns, so nothing else has created them yet.
* Never overwrites a non-NULL column value with NULL: a JSON record with
  ``emb_tol2``/``emb_tol0`` == ``null`` is skipped for that column (counted as
  skipped-null), not written as NULL over a previously-populated value.
* A record whose ``(date, lb_a, lb_b)`` has no corresponding ``latest_pairs``
  row is counted as unmatched and left alone (never inserts a new row).
* After writing, re-reads every touched key via ``latest_pairs`` and verifies
  the stored value matches what was written, exiting non-zero on mismatch.

Usage (NOT run automatically — the operator runs this explicitly)::

    .venv/bin/python3 tools/tapematch/persist_emb_scores.py \\
        --scores tools/tapematch/fullset_pairs_scores.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import tapematch_session as TS  # noqa: E402

DEFAULT_SCORES = _HERE / "fullset_pairs_scores.json"

# (json_field, pairs_column)
_FIELD_MAP = (("emb_tol2", "emb_score"), ("emb_tol0", "emb_score_global"))


def _key(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _load_scores(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"error: {path} not found")
    return json.loads(path.read_text())


def _latest_pairs_id(conn: sqlite3.Connection, date: str, lb_lo: int, lb_hi: int) -> int | None:
    """The ``pairs.id`` that ``latest_pairs`` resolves to for this key, or None."""
    row = conn.execute(
        "SELECT id FROM latest_pairs WHERE concert_date = ? AND lb_a = ? AND lb_b = ?",
        (date, lb_lo, lb_hi),
    ).fetchone()
    return row[0] if row is not None else None


def persist(conn: sqlite3.Connection, records: list[dict]) -> dict[str, int]:
    """Write records into ``pairs``; return counters for the summary report."""
    counts = {"updated": 0, "skipped_null": 0, "unmatched": 0, "rows_touched": 0}
    verify: list[tuple[str, int, int, str, float]] = []  # (date, lo, hi, col, expected)

    for rec in records:
        date = rec["date"]
        lb_lo, lb_hi = _key(rec["lb_a"], rec["lb_b"])
        pair_id = _latest_pairs_id(conn, date, lb_lo, lb_hi)
        if pair_id is None:
            counts["unmatched"] += 1
            continue

        row_touched = False
        for json_field, column in _FIELD_MAP:
            value = rec.get(json_field)
            if value is None:
                # Never write NULL over a (possibly already-populated) column.
                counts["skipped_null"] += 1
                continue
            value = float(value)
            existing = conn.execute(
                f"SELECT {column} FROM pairs WHERE id = ?", (pair_id,)).fetchone()[0]
            if existing is not None and existing == value:
                continue  # already correct, no write needed
            conn.execute(f"UPDATE pairs SET {column} = ? WHERE id = ?", (value, pair_id))
            counts["updated"] += 1
            row_touched = True
            verify.append((date, lb_lo, lb_hi, column, value))
        if row_touched:
            counts["rows_touched"] += 1

    conn.commit()

    # Verify: SELECT via latest_pairs must return exactly what we wrote.
    mismatches = []
    for date, lb_lo, lb_hi, column, expected in verify:
        got = conn.execute(
            f"SELECT {column} FROM latest_pairs WHERE concert_date = ? "
            f"AND lb_a = ? AND lb_b = ?", (date, lb_lo, lb_hi)).fetchone()
        if got is None or got[0] != expected:
            mismatches.append((date, lb_lo, lb_hi, column, expected, got))
    if mismatches:
        for m in mismatches[:20]:
            print(f"  MISMATCH: {m}", file=sys.stderr)
        sys.exit(f"error: {len(mismatches)} verification mismatches after write — "
                 "see stderr; DB left in its post-write state for inspection.")

    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", type=Path, default=DEFAULT_SCORES,
                    help="fullset pair-scores JSON (default: %(default)s)")
    args = ap.parse_args(argv)

    records = _load_scores(args.scores)
    conn = TS.open_obs_db()  # idempotent ALTER for emb_score/emb_score_global runs here
    try:
        counts = persist(conn, records)
    finally:
        conn.close()

    print(f"records read:    {len(records)}")
    print(f"column updates:  {counts['updated']}")
    print(f"rows touched:    {counts['rows_touched']}")
    print(f"skipped (null):  {counts['skipped_null']}")
    print(f"unmatched:       {counts['unmatched']}")
    print("verification: OK (every write re-read via latest_pairs matches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
