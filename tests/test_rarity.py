"""Tests for backend/rarity.py and GET /api/tapematch/rarity (TODO-335)."""
import shutil

import backend.db as db
from backend import rarity
from tests.test_tapematch_routes import _AppClient, _make_db


def _seed(db_path):
    conn = db.get_connection(db_path)
    conn.executemany(
        "INSERT INTO entries (lb_number, date_str, lb_category) VALUES (?, ?, ?)",
        [
            (1, "7/8/78", "concert"), (2, "7/8/78", "concert"), (3, "7/8/78", "concert"),
            (4, "7/8/78", "concert"),       # never analysed -> unanalysed sibling
            (5, "7/8/78", "compilation"),   # compilation -> never a sibling
            (6, "5/1/66", "concert"),
            (7, "6/2/90", "concert"),       # date tapematch never ran
        ],
    )
    conn.executemany(
        "INSERT INTO recording_families (lb_number, fam_id, concert_date) VALUES (?, ?, ?)",
        [
            (1, "1978-07-08#1", "1978-07-08"), (2, "1978-07-08#1", "1978-07-08"),
            (3, "1978-07-08#2", "1978-07-08"),
            (6, "1966-05-01#1", "1966-05-01"),
        ],
    )
    conn.commit()
    return conn


def test_lb_rarity_counts_copies_and_unanalysed_siblings():
    db_path, tmp_dir = _make_db()
    try:
        rows = {r["lb_number"]: r for r in rarity.lb_rarity(_seed(db_path))}
        assert set(rows) == {1, 2, 3, 6}
        assert rows[1]["copies"] == 2 and not rows[1]["only_known_copy"]
        assert rows[3]["copies"] == 1 and rows[3]["only_known_copy"]
        # LB 4 is unanalysed; LB 5 is a compilation and does not count.
        assert rows[3]["unanalysed_on_date"] == 1
        # 1966 century floor: 5/1/66 resolves to 1966, not 2066.
        assert rows[6]["only_known_copy"] and rows[6]["unanalysed_on_date"] == 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_lb_rarity_empty_db():
    db_path, tmp_dir = _make_db()
    try:
        assert rarity.lb_rarity(db.get_connection(db_path)) == []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_rarity_route_returns_flat_list():
    db_path, tmp_dir = _make_db()
    try:
        _seed(db_path)
        with _AppClient(db_path) as client:
            resp = client.get("/api/tapematch/rarity")
            assert resp.status_code == 200
            body = resp.get_json()
        assert [r["lb_number"] for r in body] == [1, 2, 3, 6]
        assert body[2] == {
            "lb_number": 3, "fam_id": "1978-07-08#2", "concert_date": "1978-07-08",
            "copies": 1, "only_known_copy": True, "unanalysed_on_date": 1,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
