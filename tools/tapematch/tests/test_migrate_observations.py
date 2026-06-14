"""Tests for migrate_observations.py (Task 2 of CC_TAPEMATCH_FIXES.md).

Covers:
- lb_a/lb_b pair-key normalization (swap *_a/*_b columns when lb_a > lb_b)
- idempotency (a second pass finds nothing left to normalize)
- the latest_pairs view returning the most recent verdict per
  (concert_date, lb_a, lb_b) key
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_observations as mig  # noqa: E402

# Minimal pairs schema: id/run_id/concert_date/run_at plus every column
# referenced by SWAP_COLUMN_PAIRS, which is all migrate_observations.py touches.
PAIRS_SCHEMA = """
CREATE TABLE pairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    concert_date    TEXT NOT NULL,
    lb_a            INTEGER,
    lb_b            INTEGER,
    folder_a        TEXT,
    folder_b        TEXT,
    corr            REAL,
    tapematch_verdict TEXT,
    family_id_a     INTEGER,
    family_id_b     INTEGER,
    speed_ppm_a     REAL,
    speed_ppm_b     REAL,
    speed_kind_a    TEXT,
    speed_kind_b    TEXT,
    hf_ceiling_hz_a REAL,
    hf_ceiling_hz_b REAL,
    noise_floor_db_a REAL,
    noise_floor_db_b REAL,
    dc_asymmetry_a  REAL,
    dc_asymmetry_b  REAL,
    perf_dur_sec_a  REAL,
    perf_dur_sec_b  REAL,
    track_count_a   INTEGER,
    track_count_b   INTEGER,
    dominant_ext_a  TEXT,
    dominant_ext_b  TEXT,
    run_at          TEXT
);
"""


def make_db(tmp_path):
    db_path = tmp_path / "observations.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(PAIRS_SCHEMA)
    conn.commit()
    return db_path, conn


def insert_row(conn, **cols):
    fields = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO pairs ({fields}) VALUES ({placeholders})", list(cols.values()))
    conn.commit()


def test_normalize_row_swaps_a_b_columns(tmp_path):
    _, conn = make_db(tmp_path)
    insert_row(
        conn,
        run_id="20260101_000000", concert_date="2001-01-01",
        lb_a=20, lb_b=10, folder_a="folder-20", folder_b="folder-10",
        family_id_a=2, family_id_b=1,
        dominant_ext_a=".wav", dominant_ext_b=".flac",
        run_at="2026-01-01T00:00:00",
    )
    row_id = conn.execute("SELECT id FROM pairs").fetchone()[0]

    assert mig.find_unordered_rows(conn) == [row_id]
    mig.normalize_row(conn, row_id)
    conn.commit()

    row = conn.execute(
        "SELECT lb_a, lb_b, folder_a, folder_b, family_id_a, family_id_b, "
        "dominant_ext_a, dominant_ext_b FROM pairs WHERE id = ?", (row_id,)
    ).fetchone()
    assert row == (10, 20, "folder-10", "folder-20", 1, 2, ".flac", ".wav")
    assert mig.find_unordered_rows(conn) == []


def test_already_ordered_row_untouched(tmp_path):
    _, conn = make_db(tmp_path)
    insert_row(
        conn,
        run_id="20260101_000000", concert_date="2001-01-01",
        lb_a=10, lb_b=20, folder_a="folder-10", folder_b="folder-20",
        run_at="2026-01-01T00:00:00",
    )
    assert mig.find_unordered_rows(conn) == []


def test_latest_pairs_view_picks_most_recent_run(tmp_path):
    _, conn = make_db(tmp_path)
    insert_row(
        conn,
        run_id="20260101_000000", concert_date="2001-01-01",
        lb_a=10, lb_b=20, corr=0.01, tapematch_verdict="different_family",
        run_at="2026-01-01T00:00:00",
    )
    insert_row(
        conn,
        run_id="20260102_000000", concert_date="2001-01-01",
        lb_a=10, lb_b=20, corr=0.55, tapematch_verdict="same_family",
        run_at="2026-01-02T00:00:00",
    )
    conn.execute(mig.INDEX_SQL)
    conn.execute(mig.LATEST_PAIRS_VIEW_SQL)
    conn.commit()

    rows = conn.execute(
        "SELECT run_id, corr, tapematch_verdict FROM latest_pairs "
        "WHERE concert_date='2001-01-01' AND lb_a=10 AND lb_b=20"
    ).fetchall()
    assert rows == [("20260102_000000", 0.55, "same_family")]


def test_migration_is_idempotent(tmp_path):
    db_path, conn = make_db(tmp_path)
    insert_row(
        conn,
        run_id="20260101_000000", concert_date="2001-01-01",
        lb_a=20, lb_b=10, folder_a="folder-20", folder_b="folder-10",
        run_at="2026-01-01T00:00:00",
    )
    conn.close()

    mig.OBS_DB_PATH = db_path
    for _ in range(2):
        conn = sqlite3.connect(str(db_path))
        for row_id in mig.find_unordered_rows(conn):
            mig.normalize_row(conn, row_id)
        conn.execute(mig.INDEX_SQL)
        conn.execute(mig.LATEST_PAIRS_VIEW_SQL)
        conn.commit()
        assert mig.find_unordered_rows(conn) == []
        conn.close()
