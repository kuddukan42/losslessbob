"""Tests for TODO-193: WTRF review routes (/api/wtrf/review*).

Temp DB via the real schema; qBittorrent and WTRF are monkeypatched — no
network contact.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def client(tmp_path):
    import backend.db as db
    import backend.paths as _p

    db_path = str(tmp_path / "test.db")
    _p.DATA_DIR = tmp_path
    (tmp_path / "attachments").mkdir(exist_ok=True)
    (tmp_path / "backups").mkdir(exist_ok=True)
    db.init_db(db_path)
    orig = db.DB_PATH
    db.DB_PATH = db_path

    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client(), db, tmp_path
    db.DB_PATH = orig


def _add(db, lb, status, conf, topic="http://w/?topic=1.0", signals=None, tp=None):
    return db.add_wtrf_download(
        lb_number=lb, topic_url=topic, torrent_path=tp, confidence=conf,
        signals_json=json.dumps(signals or {}), status=status,
    )


class TestReviewList:
    def test_latest_row_per_lb_and_filters(self, client):
        c, db, _ = client
        _add(db, 16596, "skipped", "ambiguous", "http://w/?topic=60197.0",
             {"tied_candidates": ["http://w/?topic=60197.0", "http://w/?topic=60199.0"]})
        _add(db, 16614, "skipped", "needs_review")
        _add(db, 16614, "qbt_added", "medium")          # supersedes the row above
        _add(db, 16622, "skipped", "not_found")
        body = c.get("/api/wtrf/review?filter=review").get_json()
        assert [r["lb_number"] for r in body["rows"]] == [16596]
        assert body["rows"][0]["candidates"] == [
            "http://w/?topic=60197.0", "http://w/?topic=60199.0"]
        assert body["counts"]["added"] == 1 and body["counts"]["not_found"] == 1
        assert body["counts"]["all"] == 3


class TestReject:
    def test_reject_marks_row(self, client):
        c, db, _ = client
        rid = _add(db, 16596, "skipped", "ambiguous")
        assert c.post(f"/api/wtrf/review/{rid}/reject").status_code == 200
        row = c.get("/api/wtrf/review?filter=rejected").get_json()["rows"][0]
        assert row["status"] == "rejected" and row["signals"]["review"] == "rejected"

    def test_reject_unknown_404(self, client):
        c, _, _ = client
        assert c.post("/api/wtrf/review/999/reject").status_code == 404


class TestConfirm:
    def test_paused_row_is_resumed(self, client, monkeypatch):
        c, db, tmp = client
        import backend.qbittorrent as q
        t = tmp / "a.torrent"
        t.write_bytes(b"x")
        rid = _add(db, 16633, "qbt_added", "medium", tp=str(t))
        seen = {}
        monkeypatch.setattr(q, "torrent_file_infohash", lambda p: "ab" * 20)
        monkeypatch.setattr(q, "resume_torrent",
                            lambda ih, **kw: seen.update(ih=ih) or {"ok": True})
        r = c.post(f"/api/wtrf/review/{rid}/confirm")
        assert r.get_json() == {"ok": True, "action": "resumed"}
        assert seen["ih"] == "ab" * 20

    def test_skipped_row_fetches_chosen_candidate_and_adds(self, client, monkeypatch):
        c, db, tmp = client
        import backend.qbittorrent as q
        import backend.wtrf_scraper as ws
        urls = ["http://w/?topic=1.0", "http://w/?topic=2.0"]
        rid = _add(db, 16596, "skipped", "ambiguous", urls[0], {"tied_candidates": urls})
        got = {}

        def fake_dl(lb, url, dest, delay=2.0):
            got["url"] = url
            return {"ok": True, "torrent_path": str(tmp / "n.torrent"), "error": None}

        (tmp / "n.torrent").write_bytes(b"x")
        monkeypatch.setattr(ws, "download_torrent_from_topic", fake_dl)
        monkeypatch.setattr(q, "add_torrent_for_download",
                            lambda **kw: got.update(paused=kw["paused"]) or {"ok": True})
        r = c.post(f"/api/wtrf/review/{rid}/confirm", json={"topic_url": urls[1]})
        assert r.get_json()["action"] == "added"
        assert got == {"url": urls[1], "paused": False}
        row = db.get_wtrf_downloads(16596)[0]
        assert row["status"] == "qbt_added" and row["topic_url"] == urls[1]

    def test_unknown_candidate_rejected(self, client):
        c, db, _ = client
        rid = _add(db, 16596, "skipped", "ambiguous", "http://w/?topic=1.0")
        r = c.post(f"/api/wtrf/review/{rid}/confirm", json={"topic_url": "http://evil/"})
        assert r.status_code == 400


class TestRejectedTopicsNotReoffered:
    def test_rejected_row_topics_returned(self, client):
        _, db, _ = client
        rid = _add(db, 16596, "skipped", "ambiguous", "http://w/?topic=60197.0",
                   {"tied_candidates": ["http://w/?topic=60197.0", "http://w/?topic=60199.0"]})
        _add(db, 16596, "skipped", "needs_review", "http://w/?topic=70000.0")
        assert db.get_wtrf_rejected_topics(16596) == set()
        db.update_wtrf_download(rid, {"status": "rejected"})
        assert db.get_wtrf_rejected_topics(16596) == {
            "http://w/?topic=60197.0", "http://w/?topic=60199.0"}
        assert db.get_wtrf_rejected_topics(16614) == set()
