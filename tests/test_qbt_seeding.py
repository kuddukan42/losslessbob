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
