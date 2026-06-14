"""Tests for build_rerun_queue.py (Task 6 of CC_TAPEMATCH_FIXES.md).

Covers:
- queue ordering (miss count desc, date asc tiebreak)
- 0-miss dates are never queued
- --since exclusion of dates already re-run at/after a timestamp
- output line formatting (singular/plural "miss"/"misses")
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_rerun_queue as brq  # noqa: E402

PAIRS_SCHEMA = """
CREATE TABLE pairs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT NOT NULL,
    concert_date      TEXT NOT NULL,
    lb_a              INTEGER,
    lb_b              INTEGER,
    corr              REAL,
    tapematch_verdict TEXT,
    lb_says_same      INTEGER,
    run_at            TEXT
);

CREATE VIEW latest_pairs AS
SELECT p.*
FROM pairs p
WHERE p.id = (
    SELECT p2.id FROM pairs p2
    WHERE p2.concert_date = p.concert_date
      AND p2.lb_a = p.lb_a
      AND p2.lb_b = p.lb_b
    ORDER BY p2.run_at DESC, p2.id DESC
    LIMIT 1
);
"""


def make_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "observations.db"))
    conn.executescript(PAIRS_SCHEMA)
    conn.commit()
    return conn


def insert_row(conn, **cols):
    fields = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO pairs ({fields}) VALUES ({placeholders})", list(cols.values()))
    conn.commit()


def test_queue_ordered_by_miss_count_desc(tmp_path):
    conn = make_db(tmp_path)
    # 1989-06-04: 2 misses
    insert_row(conn, run_id="r1", concert_date="1989-06-04", lb_a=1, lb_b=2,
               tapematch_verdict="different_family", lb_says_same=1, run_at="2026-06-01T00:00:00")
    insert_row(conn, run_id="r1", concert_date="1989-06-04", lb_a=1, lb_b=3,
               tapematch_verdict="different_family", lb_says_same=1, run_at="2026-06-01T00:00:00")
    # 1990-01-12: 1 miss
    insert_row(conn, run_id="r1", concert_date="1990-01-12", lb_a=4, lb_b=5,
               tapematch_verdict="different_family", lb_says_same=1, run_at="2026-06-01T00:00:00")
    # 1996-07-21: 0 misses (lb_says_same=1 but same_family — agrees with commentary)
    insert_row(conn, run_id="r1", concert_date="1996-07-21", lb_a=6, lb_b=7,
               tapematch_verdict="same_family", lb_says_same=1, run_at="2026-06-01T00:00:00")
    # 2001-10-30: lb_says_same is 0/None — not a miss either way
    insert_row(conn, run_id="r1", concert_date="2001-10-30", lb_a=8, lb_b=9,
               tapematch_verdict="different_family", lb_says_same=0, run_at="2026-06-01T00:00:00")
    insert_row(conn, run_id="r1", concert_date="2001-10-30", lb_a=8, lb_b=10,
               tapematch_verdict="different_family", lb_says_same=None, run_at="2026-06-01T00:00:00")

    queue, excluded = brq.build_queue(conn)
    assert queue == [("1989-06-04", 2), ("1990-01-12", 1)]
    assert excluded == []


def test_since_excludes_already_revalidated_dates(tmp_path):
    conn = make_db(tmp_path)
    # Re-run after the fix landed — should be excluded.
    insert_row(conn, run_id="r2", concert_date="1989-06-04", lb_a=1, lb_b=2,
               tapematch_verdict="different_family", lb_says_same=1, run_at="2026-06-14T00:00:00")
    # Still only pre-fix runs — should remain in the queue.
    insert_row(conn, run_id="r1", concert_date="1990-01-12", lb_a=4, lb_b=5,
               tapematch_verdict="different_family", lb_says_same=1, run_at="2026-06-01T00:00:00")

    queue, excluded = brq.build_queue(conn, since="2026-06-13T00:00:00")
    assert queue == [("1990-01-12", 1)]
    assert [(d, m) for d, m, _ in excluded] == [("1989-06-04", 1)]


def test_resolve_since_passes_through_iso_timestamp():
    assert brq.resolve_since("2026-06-13T18:00:00") == "2026-06-13T18:00:00"
    assert brq.resolve_since(None) is None


def test_format_line_singular_plural():
    assert brq.format_line("1990-01-12", 1) == "1990-01-12  # 1 miss"
    assert brq.format_line("1989-06-04", 8) == "1989-06-04  # 8 misses"
