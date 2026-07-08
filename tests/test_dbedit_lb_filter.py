"""
Tests for TODO-175: DB Editor LB filter accepting multiple comma/space-separated
LB numbers via /api/dbedit/table/<name>/rows.

Uses a temp-file SQLite database seeded through the real schema (db.init_db) so
tests never touch the real data/losslessbob.db.
"""

import pytest


def _seed_entries(conn, lb_numbers: list[int]) -> None:
    """Insert one bare entries row per LB number, status 'ok'."""
    conn.executemany(
        "INSERT OR IGNORE INTO entries(lb_number, status) VALUES(?, 'ok')",
        [(n,) for n in lb_numbers],
    )
    conn.commit()


@pytest.fixture
def flask_client(tmp_path):
    """Spin up a Flask test client backed by a seeded temp DB."""
    import backend.db as db
    import backend.paths as _p

    db_path = str(tmp_path / "test.db")
    _p.DATA_DIR = tmp_path
    (tmp_path / "attachments").mkdir(exist_ok=True)
    (tmp_path / "backups").mkdir(exist_ok=True)

    db.init_db(db_path)
    conn = db.get_connection(db_path)
    _seed_entries(conn, [4929, 5683, 9627, 1234])

    orig_dbpath = db.DB_PATH
    db.DB_PATH = db_path

    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True

    yield app.test_client()

    db.DB_PATH = orig_dbpath


def _lb_numbers(resp_json: dict) -> set[int]:
    cols = resp_json["columns"]
    idx = cols.index("lb_number")
    return {row[idx] for row in resp_json["rows"]}


class TestDbEditLbFilter:
    def test_single_number_unchanged(self, flask_client):
        resp = flask_client.get("/api/dbedit/table/entries/rows?lb_number=4929")
        assert resp.status_code == 200
        data = resp.get_json()
        assert _lb_numbers(data) == {4929}
        assert data["total"] == 1

    def test_multiple_comma_separated(self, flask_client):
        resp = flask_client.get(
            "/api/dbedit/table/entries/rows?lb_number=4929,5683,9627"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert _lb_numbers(data) == {4929, 5683, 9627}
        assert data["total"] == 3

    def test_multiple_space_separated(self, flask_client):
        resp = flask_client.get(
            "/api/dbedit/table/entries/rows?lb_number=4929 5683 9627"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert _lb_numbers(data) == {4929, 5683, 9627}
        assert data["total"] == 3

    def test_mixed_separators_with_extra_whitespace(self, flask_client):
        resp = flask_client.get(
            "/api/dbedit/table/entries/rows?lb_number=4929,  5683   9627"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert _lb_numbers(data) == {4929, 5683, 9627}
        assert data["total"] == 3

    def test_invalid_token_falls_back_to_unfiltered(self, flask_client):
        """An invalid token (e.g. non-numeric) should keep the prior reject
        behavior: the filter is silently skipped, returning all rows."""
        resp = flask_client.get("/api/dbedit/table/entries/rows?lb_number=4929,abc")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 4
        assert _lb_numbers(data) == {4929, 5683, 9627, 1234}

    def test_invalid_single_value_unchanged(self, flask_client):
        resp = flask_client.get("/api/dbedit/table/entries/rows?lb_number=abc")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 4

    def test_no_filter_returns_all(self, flask_client):
        resp = flask_client.get("/api/dbedit/table/entries/rows")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 4
