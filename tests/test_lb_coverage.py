"""Tests for backend/lb_coverage.py (GET /api/lb/coverage).

Covers the coverage-award payload contract: snapshot/coverage/stats shape,
entries_total/held/missing math, by_decade bucketing (2-digit-year rule reuse),
ledger_sha256 determinism, and graceful zeroed output on a fresh/empty DB.

All tests use a temp-file SQLite DB built via backend.db.init_db() so the full
production schema is present; they never touch the real data/losslessbob.db.
"""

import hashlib
import os
import sqlite3
import tempfile

import backend.db as db
from backend.lb_coverage import get_coverage


def _make_conn() -> tuple[sqlite3.Connection, str]:
    """Create a fresh temp DB with full schema. Returns (conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_coverage_")
    db_path = os.path.join(tmp_dir, "test.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return conn, tmp_dir


def _seed(conn: sqlite3.Connection) -> None:
    """Seed a small, hand-checkable set of entries/lb_master/my_collection rows."""
    conn.executemany(
        "INSERT INTO entries(lb_number, status, location, date_str) VALUES(?,?,?,?)",
        [
            (1, "ok", "Forest Hills, NY", "8/28/65"),
            (2, "ok", "Carnegie Hall, NY", "11/4/61"),
            (3, "ok", "Fillmore East, NY", "3/15/72"),
            (4, "ok", "Nonexistent Show", "1/1/99"),
            (5, "ok", "Missing Show", "1/1/20"),
            (6, "ok", "Unparseable", "not-a-date"),
        ],
    )
    conn.executemany(
        "INSERT INTO lb_master(lb_number, lb_status) VALUES(?,?)",
        [
            (1, "public"),
            (2, "public"),
            (3, "private"),
            (4, "nonexistent"),
            (5, "missing"),
            (6, "public"),
        ],
    )
    conn.executemany(
        "INSERT INTO my_collection(lb_number, folder_name, disk_path, confirmed_at) "
        "VALUES(?,?,?,?)",
        [
            (1, "lb1", "/x/1", "2026-05-13 10:00:00"),
            (3, "lb3", "/x/3", "2026-06-01 10:00:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO checksums(checksum, filename, chk_type, lb_number) VALUES(?,?,?,?)",
        [
            ("aaa", "f1.flac", "md5", 1),
            ("bbb", "f2.flac", "md5", 3),
        ],
    )
    conn.executemany(
        "INSERT INTO recording_families(lb_number, fam_id, concert_date) VALUES(?,?,?)",
        [
            (1, "fam-1", "1965-08-28"),
            (3, "fam-2", "1972-03-15"),
        ],
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('master_published_at', '2026-07-14T00:04:41.894196+00:00')"
    )
    conn.execute("INSERT INTO meta(key, value) VALUES ('master_version', '2026-07-14_000430')")
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('last_import_date', '2026-08-02 22:22:28')"
    )
    conn.commit()


def test_fresh_db_returns_zeroed_payload() -> None:
    conn, _tmp_dir = _make_conn()
    result = get_coverage(conn)

    assert result["snapshot"]["entry_count"] == 0
    assert result["snapshot"]["label"] is None
    assert result["snapshot"]["version"] is None
    assert result["snapshot"]["published_at"] is None
    assert result["snapshot"]["last_import"] is None

    assert result["coverage"]["entries_total"] == 0
    assert result["coverage"]["entries_held"] == 0
    assert result["coverage"]["entries_missing"] == 0
    assert result["coverage"]["recordings"] == 0
    assert result["coverage"]["families"] == 0
    assert result["coverage"]["coverage_pct"] == 0.0
    assert result["coverage"]["complete"] is True
    assert result["coverage"]["by_decade"] == []
    assert result["coverage"]["ledger_sha256"] == hashlib.sha256(b"").hexdigest()
    assert result["coverage"]["signed_by"].startswith("losslessbob")

    assert result["stats"]["first_entry_filed_at"] is None
    assert result["stats"]["days_active"] == 0


def test_seeded_db_matches_expected_math() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    result = get_coverage(conn)

    # entries_total excludes lb 4 (nonexistent) only -> 5 of 6. lb 5 ('missing'
    # = tape exists, LB page gone) is a fillable gap and stays counted.
    coverage = result["coverage"]
    assert coverage["entries_total"] == 5
    # held: lb 1 and lb 3 are in my_collection.
    assert coverage["entries_held"] == 2
    assert coverage["entries_missing"] == 3
    assert coverage["coverage_pct"] == 0.4
    assert coverage["complete"] is False
    assert coverage["recordings"] == 2
    assert coverage["families"] == 2

    # by_decade: lb1 -> 1965 (60s), lb2 -> 1961 (60s), lb3 -> 1972 (70s),
    # lb6 has an unparseable date_str and is skipped.
    by_decade = {d["decade"]: d for d in coverage["by_decade"]}
    assert set(by_decade) == {1960, 1970, 2020}
    assert by_decade[1960]["label"] == "60s"
    assert by_decade[1960]["total"] == 2
    assert by_decade[1960]["held"] == 1  # only lb1 held
    assert by_decade[1970]["label"] == "70s"
    assert by_decade[1970]["total"] == 1
    assert by_decade[1970]["held"] == 1
    assert by_decade[2020]["total"] == 1   # lb5, 'missing' -> counted, not held
    assert by_decade[2020]["held"] == 0

    # by_decade must be ascending.
    decades = [d["decade"] for d in coverage["by_decade"]]
    assert decades == sorted(decades)

    expected_ledger = hashlib.sha256(b"1|fam-1\n3|fam-2").hexdigest()
    assert coverage["ledger_sha256"] == expected_ledger

    snapshot = result["snapshot"]
    assert snapshot["label"] == "2026.07"
    assert snapshot["version"] == "2026-07-14_000430"
    assert snapshot["published_at"] == "2026-07-14T00:04:41.894196+00:00"
    assert snapshot["last_import"] == "2026-08-02 22:22:28"
    assert snapshot["entry_count"] == 6

    stats = result["stats"]
    assert stats["first_entry_filed_at"] == "2026-05-13"
    assert stats["days_active"] >= 0


def test_alias_owned_lbs_count_as_held() -> None:
    """An LB owned only via an lb_alias twin must count as held, in both directions.

    Regression: coverage counted a direct my_collection join only, so the 57
    alias-folded LBs the Collection screen's "Not in collection" list correctly
    hides were still reported as gaps -- the two screens disagreed.
    """
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    # lb2 (public, unheld) is an alias of held lb1; lb6 (public, unheld) is the
    # canonical for held lb3 -- the reverse direction.
    conn.executemany(
        "INSERT INTO lb_alias(alias_lb, canonical_lb) VALUES(?,?)",
        [(2, 1), (3, 6)],
    )
    conn.commit()

    coverage = get_coverage(conn)["coverage"]
    assert coverage["entries_total"] == 5
    assert coverage["entries_held"] == 4      # lb1, lb3 direct + lb2, lb6 via alias
    assert coverage["entries_missing"] == 1   # only lb5 remains a gap

    by_decade = {d["decade"]: d for d in coverage["by_decade"]}
    assert by_decade[1960]["held"] == 2       # lb2 now folds into lb1's decade


def test_ledger_sha256_is_order_independent() -> None:
    """Insertion order must not change the hash -- pairs are sorted before hashing."""
    conn_a, _tmp_a = _make_conn()
    conn_a.executemany(
        "INSERT INTO recording_families(lb_number, fam_id, concert_date) VALUES(?,?,?)",
        [(5, "fam-z", "2020-01-01"), (1, "fam-a", "1965-01-01")],
    )
    conn_a.commit()

    conn_b, _tmp_b = _make_conn()
    conn_b.executemany(
        "INSERT INTO recording_families(lb_number, fam_id, concert_date) VALUES(?,?,?)",
        [(1, "fam-a", "1965-01-01"), (5, "fam-z", "2020-01-01")],
    )
    conn_b.commit()

    assert get_coverage(conn_a)["coverage"]["ledger_sha256"] == (
        get_coverage(conn_b)["coverage"]["ledger_sha256"]
    )
