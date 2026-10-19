"""TODO-339 part 4: TUIT-only tapers as reviewable, additive candidate evidence."""
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def cur():
    """Yield (module, db_path, conn) on a throwaway DB."""
    tmp_dir = tempfile.mkdtemp(prefix="lbcand_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend import taper_curation as tc
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        # LB-1 already names a taper in entries; LB-3/4/5 are blank.
        conn.execute("INSERT INTO entries (lb_number, date_str, location, description,"
                     " taper_name, status) VALUES (1, '1/1/80', 'X', 'x', 'spot', 'ok')")
        for lb in (3, 4, 5):
            conn.execute("INSERT INTO entries (lb_number, date_str, location, description,"
                         " taper_name, status) VALUES (?, '1/1/80', 'X', 'x', '', 'ok')",
                         (lb,))
        conn.execute("INSERT INTO tuit_recordings (rec_id, lb_number, taper)"
                     " VALUES (10, 1, 'spot')")
        conn.execute("INSERT INTO tuit_recordings (rec_id, lb_number, taper, uploader)"
                     " VALUES (30, 3, 'spot', 'upl')")
        conn.execute("INSERT INTO tuit_recordings (rec_id, lb_number, taper)"
                     " VALUES (40, 4, 'unknown')")
        conn.execute("INSERT INTO tuit_recordings (rec_id, lb_number, taper)"
                     " VALUES (50, 5, 'spot')")
        conn.execute("INSERT INTO taper_confirmations (lb_number, action, taper_normalised)"
                     " VALUES (5, 'confirm', 'spot')")
    try:
        yield tc, db_path, conn
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_lists_only_undecided_tuit_named_blank_entries(cur):
    tc, db_path, _ = cur
    res = tc.tuit_candidates(db_path=db_path)
    assert [r["lb_number"] for r in res["rows"]] == [3]
    row = res["rows"][0]
    assert row["candidates"][0] == "spot"
    assert row["provenance"] == {
        "source": "tuit", "taper_text": "spot", "rec_id": 30, "uploader": "upl"}


def test_include_decided_and_nothing_written(cur):
    tc, db_path, conn = cur
    res = tc.tuit_candidates(include_decided=True, db_path=db_path)
    assert [r["lb_number"] for r in res["rows"]] == [3, 5]
    assert conn.execute(
        "SELECT COUNT(*) FROM entries WHERE lb_number IN (3,5) AND taper_name != ''"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM taper_attributions WHERE lb_number IN (3,5)"
    ).fetchone()[0] == 0


def test_entries_with_taper_excluded_and_counted(cur):
    tc, db_path, _ = cur
    assert 1 not in [r["lb_number"] for r in tc.tuit_candidates(db_path=db_path)["rows"]]
    assert tc.counts(db_path=db_path)["tuit_candidates"] == 1
