"""Flat-file apply: new LBs come back flagged for scraping and stay 'public'.

Uses a temp database; never touches data/losslessbob.db.
"""

import os
import tempfile

import backend.paths as _paths


def _make_db() -> tuple[str, object]:
    tmp_dir = tempfile.mkdtemp()
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    import backend.db as db
    db_path = os.path.join(tmp_dir, "test.db")
    db.init_db(db_path)
    return db_path, db.get_connection(db_path)


def _seed_release(conn) -> int:
    cur = conn.execute(
        "INSERT INTO flat_file_releases(source_page_url, zip_url, zip_filename, status) "
        "VALUES ('p', 'z', 'Checksum_Lookup_flat_file_LastLB_3.zip', 'downloaded')"
    )
    conn.commit()
    return cur.lastrowid


def test_apply_returns_never_scraped_lbs(monkeypatch):
    """LB 1 already has a scraped entry; LBs 2 and 3 are new and unscraped."""
    import backend.db as db
    from backend import flat_file

    db_path, conn = _make_db()
    # Non-empty lb_master: init_db's background migrate_lb_master stays a no-op.
    conn.execute("INSERT INTO lb_master(lb_number, lb_status) VALUES (1, 'public')")
    conn.execute(
        "INSERT INTO checksums(checksum, filename, chk_type, lb_number) "
        "VALUES ('a1', 'f1', 'md5', 1)"
    )
    conn.execute("INSERT INTO entries(lb_number, status) VALUES (1, 'ok')")
    conn.commit()
    release_id = _seed_release(conn)

    monkeypatch.setattr(flat_file, "_load_txt_from_zip", lambda _p: [
        ("a1", "f1", "md5", 1, 0),
        ("a2", "f1b", "md5", 1, 0),
        ("b1", "f2", "md5", 2, 0),
        ("c1", "f3", "md5", 3, 0),
    ])
    monkeypatch.setattr(db, "backup_database", lambda *a, **k: None)

    result = flat_file.apply_flat_file_release(release_id, db_path=db_path)

    assert result["rows_added"] == 3
    assert result["new_lb_numbers"] == [2, 3]
    statuses = dict(conn.execute(
        "SELECT lb_number, lb_status FROM lb_master WHERE lb_number IN (2, 3)"
    ).fetchall())
    assert statuses == {2: "public", 3: "public"}

    # Reconcile before the scrape must not demote them (the 2026-10-13 trap).
    db.reconcile_all_lb_master(db_path)
    statuses = dict(conn.execute(
        "SELECT lb_number, lb_status FROM lb_master WHERE lb_number IN (2, 3)"
    ).fetchall())
    assert statuses == {2: "public", 3: "public"}


def test_scrape_backlog_counts_unscraped_checksum_lbs():
    """The Updates card's scrape backlog sees LBs with checksums but no entry."""
    from backend import refresh

    db_path, conn = _make_db()
    conn.executemany(
        "INSERT INTO checksums(checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        [("a", "f", "md5", 1), ("b", "f", "md5", 2), ("c", "f", "md5", 3)],
    )
    conn.execute("INSERT INTO entries(lb_number, status) VALUES (1, 'ok')")
    conn.execute("INSERT INTO lb_missing(lb_number) VALUES (3)")
    conn.commit()

    step = next(s for s in refresh.STEPS if s.step_id == "scrape_entries")
    assert conn.execute(step.backlog_sql).fetchone()[0] == 1
