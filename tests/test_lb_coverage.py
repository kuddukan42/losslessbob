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
from backend.lb_coverage import get_coverage, get_ledger, get_snapshots


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


# ── Ledger + snapshot history (TODO-305) ──────────────────────────────────────


def test_ledger_lists_every_countable_entry_with_state() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    page = get_ledger(conn)

    # Same denominator as the coverage payload: lb 4 (nonexistent) is excluded.
    assert page["total"] == 5
    assert [r["lb_number"] for r in page["rows"]] == [1, 2, 3, 5, 6]

    by_lb = {r["lb_number"]: r for r in page["rows"]}
    assert by_lb[1]["held"] is True
    assert by_lb[1]["fam_id"] == "fam-1"
    assert by_lb[1]["state"] == "held"          # held + family, never lbdir-verified
    assert by_lb[1]["filed_at"] == "2026-05-13"
    assert by_lb[1]["location"] == "Forest Hills, NY"
    assert by_lb[2]["held"] is False
    assert by_lb[2]["state"] == "missing"


def test_ledger_verified_state_needs_an_lbdir_stamp() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    conn.execute(
        "UPDATE my_collection SET lbdir_verified_at = '2026-06-02 09:00:00' WHERE lb_number = 1"
    )
    conn.commit()

    by_lb = {r["lb_number"]: r for r in get_ledger(conn)["rows"]}
    assert by_lb[1]["state"] == "verified"
    assert by_lb[1]["verified"] is True
    assert by_lb[3]["state"] == "held"


def test_ledger_filters() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)

    assert [r["lb_number"] for r in get_ledger(conn, filt="held")["rows"]] == [1, 3]
    assert [r["lb_number"] for r in get_ledger(conn, filt="missing")["rows"]] == [2, 5, 6]
    # "unmatched" = in the collection but no recording family yet. Both held
    # entries have one in the seed, so add a third that does not.
    conn.execute("INSERT INTO my_collection(lb_number, folder_name, disk_path) VALUES(6,'lb6','/x/6')")
    conn.commit()
    assert [r["lb_number"] for r in get_ledger(conn, filt="unmatched")["rows"]] == [6]

    conn.execute("UPDATE lb_master SET needs_review = 1 WHERE lb_number = 2")
    conn.commit()
    assert [r["lb_number"] for r in get_ledger(conn, filt="review")["rows"]] == [2]

    # An unknown filter degrades to "all" rather than raising.
    assert get_ledger(conn, filt="bogus")["filter"] == "all"


def test_ledger_pagination_and_search() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)

    p1 = get_ledger(conn, page=1, per_page=2)
    assert p1["pages"] == 3
    assert [r["lb_number"] for r in p1["rows"]] == [1, 2]
    assert [r["lb_number"] for r in get_ledger(conn, page=3, per_page=2)["rows"]] == [6]
    # Past the end clamps to the last page instead of returning nothing.
    assert get_ledger(conn, page=99, per_page=2)["page"] == 3

    hits = get_ledger(conn, q="carnegie")
    assert [r["lb_number"] for r in hits["rows"]] == [2]
    assert get_ledger(conn, q="8/28/65")["total"] == 1


def test_ledger_deep_link_returns_the_page_holding_that_lb() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)

    page = get_ledger(conn, lb=6, per_page=2)
    assert page["page"] == 3
    assert 6 in [r["lb_number"] for r in page["rows"]]


def test_ledger_on_fresh_db_is_empty_not_an_error() -> None:
    conn, _tmp_dir = _make_conn()
    page = get_ledger(conn)
    assert page == {"rows": [], "page": 1, "pages": 0, "per_page": 50,
                    "total": 0, "filter": "all", "q": "", "lb": None}


def test_snapshots_synthesise_current_catalogue_when_history_is_empty() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    result = get_snapshots(conn)

    assert result["total"] == 1
    row = result["snapshots"][0]
    assert row["synthetic"] is True
    assert row["master_version"] == "2026-07-14_000430"
    assert row["label"] == "2026.07"
    assert row["entries_total"] == 5
    assert row["entries_held"] == 2
    assert result["current"]["version"] == "2026-07-14_000430"


def test_snapshots_read_history_newest_first() -> None:
    conn, _tmp_dir = _make_conn()
    _seed(conn)
    conn.executemany(
        "INSERT INTO lb_snapshot_history(master_version, master_published_at, imported_at,"
        " source, entries_total, entries_held, entries_added, lb_status_changes,"
        " status_counts_json, row_counts_json, backup_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-06-01_000000", "2026-06-01T00:00:00+00:00", "2026-06-02 10:00:00",
             "github", 100, 90, 100, 0, '{"public": 100}', '{"lb_master": 100}', "/b/1.db"),
            ("2026-07-14_000430", "2026-07-14T00:04:41+00:00", "2026-07-15 10:00:00",
             "file", 126, 118, 26, 3, '{"public": 126}', '{"lb_master": 126}', "/b/2.db"),
        ],
    )
    conn.commit()

    rows = get_snapshots(conn)["snapshots"]
    assert [r["master_version"] for r in rows] == ["2026-07-14_000430", "2026-06-01_000000"]
    assert rows[0]["synthetic"] is False
    assert rows[0]["label"] == "2026.07"
    assert rows[0]["entries_added"] == 26
    assert rows[0]["source"] == "file"
    assert rows[0]["status_counts"] == {"public": 126}
    assert rows[0]["row_counts"] == {"lb_master": 126}


def test_snapshot_history_row_written_on_master_import() -> None:
    """import_master_db() must append exactly one history row, with the delta."""
    conn, tmp_dir = _make_conn()
    _seed(conn)
    user_path = os.path.join(tmp_dir, "test.db")

    # Keep the snapshot + pre-import backup inside the temp dir.
    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    export_path, _manifest = db.export_master_db(reason="test", db_path=user_path)

    db.import_master_db(export_path, db_path=user_path, source="github")

    rows = get_snapshots(db.get_connection(user_path))["snapshots"]
    assert len(rows) == 1
    assert rows[0]["synthetic"] is False
    assert rows[0]["source"] == "github"
    assert rows[0]["entries_total"] == 6      # every lb_master row, statuses included
    assert rows[0]["entries_added"] == 6      # first import: full size, not 0
    assert rows[0]["entries_held"] == 2
