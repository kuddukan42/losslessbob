"""Tests for backend.wtrf_repost and forum_poster.post_reply (TODO-376 follow-up)."""
import os
import time
from pathlib import Path

import pytest

from backend import forum_poster, qbittorrent, torrent_maker, tracker_seed
from backend import wtrf_repost as wr
from backend.overlay_rehome import load_protected

LB = 77
TOPIC = "http://www.watchingtheriverflow.org/index.php?topic=4242.0"
OLD = int(time.time()) - 60 * 86400


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import backend.db as db
    import backend.paths as _p

    _p.DATA_DIR = tmp_path
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    orig = db.DB_PATH
    db.DB_PATH = db_path

    coll = tmp_path / "D" / "Concerts" / "1990" / "1990-01-01 Somewhere (LB-00077)"
    coll.mkdir(parents=True)
    (coll / "t01.flac").write_bytes(b"\x01" * 3000)
    (coll / "t02.flac").write_bytes(b"\x02" * 2000)
    overlay = tmp_path / "D" / "WTRF Seeds" / "Somewhere 1990"
    overlay.mkdir(parents=True)
    os.link(coll / "t01.flac", overlay / "t01.flac")         # hardlinked master
    (overlay / "t02.flac").write_bytes(b"\x09" * 2000)        # their retagged copy

    conn = db.get_connection(db_path)
    conn.execute("INSERT INTO entries(lb_number, status, date_str, location) "
                 "VALUES(?, 'ok', '1990-01-01', 'Somewhere')", (LB,))
    conn.execute("INSERT INTO my_collection(lb_number, folder_name, disk_path) VALUES(?,?,?)",
                 (LB, coll.name, str(coll)))
    conn.execute("INSERT INTO collection_mounts(label, root_path) VALUES('D', ?)",
                 (str(tmp_path / "D" / "Concerts"),))
    conn.execute("INSERT INTO lb_master(lb_number, lb_status) VALUES(?, 'public')", (LB,))
    conn.execute("INSERT INTO wtrf_downloads(lb_number, topic_url, confidence, status, "
                 "seed_folder) VALUES(?,?,?,?,?)", (LB, TOPIC, "definitive", "qbt_added",
                                                     str(overlay)))
    conn.commit()

    torrents = [{"hash": "aa" * 20, "name": overlay.name, "save_path": str(overlay.parent),
                 "content_path": str(overlay), "progress": 0.6, "added_on": OLD,
                 "tags": "missing music, wtrf", "state": "stoppedDL"}]
    files = [{"name": f"{overlay.name}/t01.flac", "progress": 1.0, "priority": 0},
             {"name": f"{overlay.name}/t02.flac", "progress": 0.2, "priority": 1}]
    monkeypatch.setattr(wr, "qbt_torrents", lambda: torrents)
    monkeypatch.setattr(wr, "qbt_files", lambda h: files)
    monkeypatch.setattr(tracker_seed, "_qbt_connection", lambda: {})
    calls = []
    monkeypatch.setattr(qbittorrent, "remove_torrent",
                        lambda h, **k: calls.append(("remove", h)) or {"ok": True})
    monkeypatch.setattr(torrent_maker, "TORRENTS_DIR", tmp_path / "torrents")
    monkeypatch.setattr(torrent_maker, "fetch_trackers", lambda *a, **k: [])
    monkeypatch.setattr(tracker_seed, "qbt_seed",
                        lambda t, f, o: calls.append(("seed", f)) or {"ok": True})
    monkeypatch.setattr(qbittorrent, "get_torrent_layout", lambda h, **k: {
        "ok": True, "present": True, "piece_states": [2, 2], "state": "stalledUP"})
    yield {"db": db, "coll": coll, "overlay": overlay, "torrents": torrents, "calls": calls,
           "tmp": tmp_path}
    db.DB_PATH = orig


def _digest(folder: Path) -> dict:
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}


class TestFind:
    def test_old_incomplete_wtrf_torrent_is_found(self, rig):
        [r] = wr.find_retirees()
        assert r.topic_url == TOPIC and r.lb_number == LB
        assert r.shortfall == "audio differs from ours" and r.match == "definitive"

    @pytest.mark.parametrize("change", [
        {"added_on": int(time.time()) - 5 * 86400},   # too young
        {"progress": 1.0},                            # complete
        {"tags": "tuit"},                             # not WTRF
    ])
    def test_left_alone(self, rig, change):
        rig["torrents"][0].update(change)
        assert wr.find_retirees() == []

    def test_match_kinds(self):
        assert wr.match_kind("medium", 0.98, "audio differs from ours") == "content"
        assert wr.match_kind("medium", 0.2, "some audio absent") == "suspect"
        assert wr.match_kind("definitive", 0.0, "no audio found locally") == "definitive"


class TestRetire:
    def test_removes_torrent_and_overlay_and_queues(self, rig):
        before = _digest(rig["coll"])
        [r] = wr.find_retirees()
        res = wr.retire(r, load_protected())
        assert res["ok"] and res["leftover"] == []
        assert not rig["overlay"].exists()
        assert _digest(rig["coll"]) == before
        assert ("remove", "aa" * 20) in rig["calls"]
        conn = rig["db"].get_connection()
        assert conn.execute("SELECT status FROM wtrf_downloads").fetchone()[0] == "retired"
        row = conn.execute("SELECT status, match FROM wtrf_reposts").fetchone()
        assert tuple(row) == ("queued", "definitive")

    def test_suspect_goes_to_review(self, rig):
        conn = rig["db"].get_connection()
        conn.execute("UPDATE wtrf_downloads SET confidence='medium'")
        conn.commit()
        rig["torrents"][0]["progress"] = 0.3
        [r] = wr.find_retirees()
        wr.retire(r, load_protected())
        assert conn.execute("SELECT status FROM wtrf_reposts").fetchone()[0] == "review"

    def test_in_place_seed_files_are_never_deleted(self, rig):
        t = rig["torrents"][0]
        t["content_path"] = str(rig["coll"])
        conn = rig["db"].get_connection()
        conn.execute("UPDATE wtrf_downloads SET seed_folder=?", (str(rig["coll"]),))
        conn.commit()
        before = _digest(rig["coll"])
        [r] = wr.find_retirees()
        assert wr.retire(r, load_protected())["ok"]
        assert _digest(rig["coll"]) == before

    def test_folder_shared_with_live_torrent_is_kept(self, rig):
        """Two topics, same torrent name: the complete twin keeps its files and row."""
        ov = rig["overlay"]
        rig["torrents"].append({"hash": "bb" * 20, "name": ov.name, "save_path": str(ov.parent),
                                "content_path": str(ov), "progress": 1.0, "added_on": OLD,
                                "tags": "wtrf", "state": "stalledUP"})
        conn = rig["db"].get_connection()
        conn.execute("INSERT INTO wtrf_downloads(lb_number, topic_url, confidence, status, "
                     "seed_folder) VALUES(?,?,?,?,?)", (LB, TOPIC + "x", "definitive",
                                                        "qbt_added", str(ov)))
        conn.commit()
        before = _digest(ov)
        [r] = wr.find_retirees()
        res = wr.retire(r, load_protected())
        assert res["ok"] and "bbbbbbbbbb" in res["leftover"][0]
        assert _digest(ov) == before
        statuses = dict(conn.execute("SELECT topic_url, status FROM wtrf_downloads"))
        assert statuses == {TOPIC: "qbt_added", TOPIC + "x": "qbt_added"}  # can't tell whose
        assert conn.execute("SELECT status FROM wtrf_reposts").fetchone()[0] == "review"

    def test_qbittorrent_failure_changes_nothing(self, rig, monkeypatch):
        monkeypatch.setattr(qbittorrent, "remove_torrent", lambda h, **k: {"ok": False,
                                                                           "error": "x"})
        [r] = wr.find_retirees()
        assert not wr.retire(r, load_protected())["ok"]
        assert rig["overlay"].exists()


class TestPost:
    def _queue(self, rig):
        [r] = wr.find_retirees()
        wr.retire(r, load_protected())
        return wr.repost_rows("queued")[0]

    def test_posts_a_torrent_named_after_the_folder(self, rig, monkeypatch):
        sent = {}

        def fake_reply(url, torrent, body, user, pw):
            sent.update(url=url, torrent=torrent, body=body)
            return {"ok": True, "post_url": TOPIC.replace(".0", ".msg9#msg9")}
        monkeypatch.setattr(forum_poster, "post_reply", fake_reply)
        row = self._queue(rig)
        res = wr.post(row, "u", "p")
        assert res["ok"], res["error"]
        from backend.torrent_verify import read_torrent
        assert read_torrent(sent["torrent"]).name == rig["coll"].name
        assert sent["body"] == wr.REPOST_BODY and sent["url"] == TOPIC
        assert ("seed", str(rig["coll"])) in rig["calls"]
        row = wr.repost_rows(topic_url=TOPIC)[0]
        assert row["status"] == "posted" and row["post_url"].endswith("#msg9")

    def test_private_lb_is_held(self, rig, monkeypatch):
        monkeypatch.setattr(forum_poster, "post_reply",
                            lambda *a: pytest.fail("must not post"))
        row = self._queue(rig)
        conn = rig["db"].get_connection()
        conn.execute("UPDATE lb_master SET lb_status='private'")
        conn.commit()
        assert not wr.post(row, "u", "p")["ok"]
        assert wr.repost_rows(topic_url=TOPIC)[0]["status"] == "held_private"

    def test_not_complete_in_qbittorrent_is_not_posted(self, rig, monkeypatch):
        monkeypatch.setattr(forum_poster, "post_reply",
                            lambda *a: pytest.fail("must not post"))
        monkeypatch.setattr(qbittorrent, "get_torrent_layout", lambda h, **k: {
            "ok": True, "present": True, "piece_states": [2, 0], "state": "stoppedDL"})
        row = self._queue(rig)
        assert not wr.post(row, "u", "p")["ok"]
        assert wr.repost_rows(topic_url=TOPIC)[0]["status"] == "failed"


class _Resp:
    def __init__(self, text="", status=200, location=None, url=""):
        self.text, self.status_code, self.url = text, status, url
        self.headers = {"Location": location} if location else {}


class TestPostReply:
    FORM = ('<html><title>Post reply</title><form action="http://www.watchingtheriverflow.org/'
            'index.php?action=post2;start=0" method="post"><input type="hidden" name="topic" '
            'value="4242"><input type="hidden" name="seqnum" value="7"><input type="text" '
            'name="subject" value="Re: 1990-01-01 Somewhere"></form></html>')

    def test_success_returns_the_message_url(self, tmp_path, monkeypatch):
        torrent = tmp_path / "x.torrent"
        torrent.write_bytes(b"d4:infod4:name1:xee")
        posted = {}

        class S:
            def get(self, url, **k):
                posted["compose"] = url
                return _Resp(TestPostReply.FORM)

            def post(self, url, data=None, files=None, **k):
                posted.update(data=data, files=files)
                return _Resp(status=302, location="http://www.watchingtheriverflow.org/"
                             "index.php?topic=4242.msg99#msg99")
        monkeypatch.setattr(forum_poster, "_get_session", lambda u, p: S())
        res = forum_poster.post_reply(TOPIC, torrent, "hello", "u", "p")
        assert res == {"ok": True, "post_url": "http://www.watchingtheriverflow.org/"
                       "index.php?topic=4242.msg99#msg99"}
        assert posted["compose"].endswith("action=post;topic=4242.0")
        assert posted["data"]["subject"] == "Re: 1990-01-01 Somewhere"
        assert posted["data"]["message"] == "hello"
        assert "attachment[]" in posted["files"]

    def test_board_redirect_finds_the_reply_on_the_topic(self, tmp_path, monkeypatch):
        torrent = tmp_path / "x.torrent"
        torrent.write_bytes(b"x")
        topic_page = ('<html><div class="inner" id="msg_5">old post</div>'
                      '<div class="inner" id="msg_110001">hello   there</div></html>')

        class S:
            def get(self, url, **k):
                return _Resp(topic_page if "msg999999999" in url else TestPostReply.FORM)

            def post(self, url, **k):
                return _Resp(status=302, location="http://www.watchingtheriverflow.org/"
                             "index.php?board=16.0")
        monkeypatch.setattr(forum_poster, "_get_session", lambda u, p: S())
        res = forum_poster.post_reply(TOPIC, torrent, "hello there", "u", "p")
        assert res["ok"] and res["post_url"].endswith("topic=4242.msg110001#msg110001")

    def test_board_redirect_without_the_reply_is_unverified(self, tmp_path, monkeypatch):
        torrent = tmp_path / "x.torrent"
        torrent.write_bytes(b"x")

        class S:
            def get(self, url, **k):
                return _Resp("<html></html>" if "msg999999999" in url else TestPostReply.FORM)

            def post(self, url, **k):
                return _Resp(status=302, location="http://www.watchingtheriverflow.org/"
                             "index.php?board=16.0")
        monkeypatch.setattr(forum_poster, "_get_session", lambda u, p: S())
        res = forum_poster.post_reply(TOPIC, torrent, "hello", "u", "p")
        assert not res["ok"] and res["unverified"]

    def test_no_form_is_an_error(self, tmp_path, monkeypatch):
        torrent = tmp_path / "x.torrent"
        torrent.write_bytes(b"x")

        class S:
            def get(self, url, **k):
                return _Resp("<html><title>Error</title></html>")
        monkeypatch.setattr(forum_poster, "_get_session", lambda u, p: S())
        assert not forum_poster.post_reply(TOPIC, torrent, "hi", "u", "p")["ok"]
