"""Tests for paced qBittorrent seeding (TODO-330). qBt is fully mocked."""
from unittest.mock import MagicMock

from backend import qbt_seeding as qs


class FakeSession:
    """Minimal qBt WebUI stand-in recording POSTs."""

    def __init__(self, announces=10, trackers=None, resume_status=200):
        self.announces = announces
        self.trackers = trackers or [{"url": "http://t/announce", "status": 2, "msg": ""}]
        self.resume_status = resume_status
        self.posts = []

    def get(self, url, params=None, timeout=None):
        r = MagicMock()
        if url.endswith("/app/preferences"):
            r.json.return_value = {"max_concurrent_http_announces": self.announces}
        else:
            r.json.return_value = [{"url": "** [DHT] **", "status": 2}, *self.trackers]
        return r

    def post(self, url, data=None, timeout=None, **kw):
        self.posts.append((url, data))
        r = MagicMock()
        r.status_code = self.resume_status
        return r


def _patch(monkeypatch, sess):
    monkeypatch.setattr(qs.qbt, "_make_session", lambda base, key="": sess)
    monkeypatch.setattr(qs.qbt, "_login", lambda *a, **k: None)


def test_preflight_ok_and_refuse(monkeypatch):
    _patch(monkeypatch, FakeSession(announces=10))
    assert qs.preflight("h", 1, max_announces=20)["ok"]
    _patch(monkeypatch, FakeSession(announces=50))
    pf = qs.preflight("h", 1, max_announces=20)
    assert not pf["ok"] and pf["value"] == 50


def test_release_paced_batches_and_sleeps(monkeypatch):
    sess = FakeSession()
    _patch(monkeypatch, sess)
    sleeps = []
    res = qs.release_paced([f"h{i}" for i in range(7)], "h", 1, batch_size=3,
                           interval_s=45, sleep=sleeps.append)
    resumes = [d["hashes"] for u, d in sess.posts if u.endswith("/resume")]
    assert resumes == ["h0|h1|h2", "h3|h4|h5", "h6"]
    assert sleeps == [45, 45]
    assert len(res["released"]) == 7 and res["tracker"]["h0"]["state"] == "working"


def test_release_falls_back_to_start_on_404(monkeypatch):
    sess = FakeSession(resume_status=404)
    _patch(monkeypatch, sess)
    qs.release_paced(["a"], "h", 1, sleep=lambda s: None)
    assert any(u.endswith("/start") for u, _ in sess.posts)


def test_tracker_status_flags_not_working(monkeypatch):
    sess = FakeSession(trackers=[{"url": "http://t", "status": 4, "msg": "timed out"}])
    _patch(monkeypatch, sess)
    st = qs.tracker_status(["a"], "h", 1)["a"]
    assert st["state"] == "not_working" and st["trackers"][0]["msg"] == "timed out"


def test_add_paused_cap_and_refusal(monkeypatch):
    _patch(monkeypatch, FakeSession(announces=5))
    calls = []

    def fake_add(tid, *a, **k):
        calls.append((tid, k["paused"]))
        return {"ok": True, "infohash": f"ih{tid}"}

    monkeypatch.setattr(qs.qbt, "add_torrent_from_db", fake_add)
    res = qs.add_paused([1, 2, 3, 4], "h", 1, max_adds=2)
    assert [c[0] for c in calls] == [1, 2] and all(c[1] for c in calls)
    assert res["skipped"] == [3, 4]

    _patch(monkeypatch, FakeSession(announces=99))
    calls.clear()
    res = qs.add_paused([1], "h", 1, max_announces=20)
    assert not res["ok"] and not calls


# ── Flask endpoint wiring ────────────────────────────────────────────────────

import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from backend import credentials, db  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    from backend import scheduler
    from tests.test_library_picks_api import _AppClient
    for name in ("start_file_watcher", "start_collection_watcher",
                 "start_integrity_scan_scheduler", "start_file_verify_scheduler"):
        monkeypatch.setattr(scheduler, name, lambda *a, **k: None)
    tmp = Path(tempfile.mkdtemp(prefix="qbt_ep_"))
    monkeypatch.setattr(db, "get_meta", lambda k, db_path=None: {"qbt_host": "h"}.get(k))
    monkeypatch.setattr(db, "get_torrents_for_lb", lambda lb, **k: [{"id": int(lb) * 10}])
    monkeypatch.setattr(credentials, "get_credentials", lambda svc: ("", "key"))
    with _AppClient(tmp / "t.db") as c:
        yield c


def test_endpoint_bulk_paced(client, monkeypatch):
    released = []
    monkeypatch.setattr(qs, "preflight", lambda *a, **k: {"ok": True, "warning": "w"})
    monkeypatch.setattr(qs.qbt, "add_torrent_from_db",
                        lambda tid, *a, **k: {"ok": True, "infohash": f"ih{tid}"})
    monkeypatch.setattr(qs, "release_paced", lambda *a, **k: released.append(a[0]))
    r = client.post("/api/qbt/add", json={"lb_numbers": [1, 2, 3], "max_adds": 2}).get_json()
    assert r["paced"] and r["added"] == 2 and r["skipped"] == [30]
    assert r["warning"] == "w" and r["release"]["pending"] == 2
    for _ in range(50):
        if released:
            break
        time.sleep(0.02)
    assert released == [["ih10", "ih20"]]


def test_endpoint_bulk_preflight_409(client, monkeypatch):
    monkeypatch.setattr(qs, "preflight", lambda *a, **k: {"ok": False, "error": "too many"})
    resp = client.post("/api/qbt/add", json={"lb_numbers": [1, 2]})
    assert resp.status_code == 409 and resp.get_json()["error"] == "too many"


def test_endpoint_single_unchanged(client, monkeypatch):
    seen = {}

    def fake(tid, *a, **k):
        seen["paused"] = k.get("paused")
        return {"ok": True}

    monkeypatch.setattr(qs.qbt, "add_torrent_from_db", fake)
    monkeypatch.setattr(qs, "preflight", lambda *a, **k: pytest.fail("no preflight"))
    r = client.post("/api/qbt/add", json={"lb_numbers": [5]}).get_json()
    assert r["added"] == 1 and "paced" not in r and seen["paused"] is None
    r = client.post("/api/qbt/add", json={"torrent_id": 7}).get_json()
    assert r["added"] == 1


def test_endpoint_tracker_status(client, monkeypatch):
    monkeypatch.setattr(qs, "tracker_status",
                        lambda hashes, *a, **k: {h: {"state": "working"} for h in hashes})
    r = client.post("/api/qbt/tracker_status", json={"hashes": ["AB"]}).get_json()
    assert r["status"] == {"ab": {"state": "working"}}
