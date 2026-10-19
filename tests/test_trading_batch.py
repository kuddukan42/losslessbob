"""Tests for TODO-251: friend entries endpoint and multi-friend batch compare."""

import pytest


@pytest.fixture
def client(tmp_path):
    """Flask test client on a temp DB: I hold 1,2,3; A holds 3,4,5; B holds 1,4."""
    import backend.db as db
    import backend.paths as _p

    db_path = str(tmp_path / "test.db")
    _p.DATA_DIR = tmp_path
    (tmp_path / "attachments").mkdir(exist_ok=True)
    (tmp_path / "backups").mkdir(exist_ok=True)
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    for n in (1, 2, 3):
        conn.execute("INSERT INTO entries(lb_number, status, date_str, location) "
                     "VALUES(?, 'ok', ?, 'Venue')", (n, f"1970-01-0{n}"))
        conn.execute("INSERT INTO my_collection(lb_number, folder_name, disk_path) "
                     "VALUES(?, 'f', '/x')", (n,))
    conn.commit()
    orig = db.DB_PATH
    db.DB_PATH = db_path
    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    ids = {}
    for name, lbs in (("A", (3, 4, 5)), ("B", (1, 4))):
        r = c.post("/api/trading/friends", json={
            "friend_name": name,
            "entries": [{"lb_number": n, "date_str": f"d{n}", "location": f"L{n}"} for n in lbs]})
        ids[name] = r.get_json()["friend_id"]
    c.ids = ids
    yield c
    db.DB_PATH = orig


def test_friend_entries_paginates_and_filters(client):
    fid = client.ids["A"]
    d = client.get(f"/api/trading/friends/{fid}/entries?limit=2&offset=1").get_json()
    assert d["total"] == 3 and [e["lb_number"] for e in d["entries"]] == [4, 5]
    d = client.get(f"/api/trading/friends/{fid}/entries?q=L5").get_json()
    assert [e["lb_number"] for e in d["entries"]] == [5]
    assert client.get("/api/trading/friends/9999/entries").status_code == 404


def test_batch_matrix(client):
    a, b = client.ids["A"], client.ids["B"]
    d = client.post("/api/trading/batch-compare", json={"friend_ids": [a, b]}).get_json()
    rows = {r["lb_number"]: r for r in d["rows"]}
    assert set(rows) == {2, 3, 1, 4, 5}
    assert rows[4]["kind"] == "want" and rows[4]["cells"] == {str(a): True, str(b): True}
    assert rows[2]["kind"] == "offer" and rows[2]["best_friend_id"] in (a, b)
    assert rows[3]["kind"] == "offer" and rows[3]["cells"][str(b)] is False
    assert rows[3]["best_friend_id"] == b
    summ = {f["id"]: f for f in d["friends"]}
    assert summ[a]["they_have_you_dont"] == 2 and summ[a]["you_have_they_dont"] == 2
    assert summ[b]["they_have_you_dont"] == 1 and summ[b]["both_have"] == 1


def test_batch_mode_q_paging(client):
    ids = list(client.ids.values())
    d = client.post("/api/trading/batch-compare",
                    json={"friend_ids": ids, "mode": "want"}).get_json()
    assert [r["lb_number"] for r in d["rows"]] == [4, 5]
    d = client.post("/api/trading/batch-compare",
                    json={"friend_ids": ids, "limit": 2, "offset": 2}).get_json()
    assert d["total"] == 5 and len(d["rows"]) == 2
    d = client.post("/api/trading/batch-compare",
                    json={"friend_ids": ids, "q": "L5"}).get_json()
    assert [r["lb_number"] for r in d["rows"]] == [5]


def test_batch_validation(client):
    assert client.post("/api/trading/batch-compare", json={}).status_code == 400
    assert client.post("/api/trading/batch-compare",
                       json={"friend_ids": [999]}).status_code == 404
    assert client.post("/api/trading/batch-compare",
                       json={"friend_ids": [1], "mode": "x"}).status_code == 400


def test_export_and_compare_use_entries_columns(client):
    """export/compare used to select date_str etc. from my_collection (no such columns)."""
    d = client.get("/api/trading/export")
    assert d.status_code == 200
    ents = d.get_json()["entries"]
    assert [e["lb_number"] for e in ents] == [1, 2, 3]
    assert ents[0]["date_str"] == "1970-01-01" and ents[0]["lb_status"] == "ok"
    c = client.get(f"/api/trading/compare/{client.ids['A']}")
    assert c.status_code == 200
    j = c.get_json()
    assert [e["lb_number"] for e in j["you_have_they_dont"]] == [1, 2]
    assert j["you_have_they_dont"][0]["date_str"] == "1970-01-01"
