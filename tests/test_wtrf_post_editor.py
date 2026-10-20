"""Tests for backend/wtrf_post_editor.py — SMF edit-post flow (TODO-136).

Every HTTP exchange is mocked with SMF 2.x HTML fixtures in
tests/fixtures/wtrf_edit/; nothing touches the network.
"""
from pathlib import Path

import pytest

from backend import wtrf_post_editor as ed
from backend.forum_poster import FORUM_BASE

FIX = Path(__file__).parent / "fixtures" / "wtrf_edit"
TOPIC_URL = f"{FORUM_BASE}/index.php?topic=555.msg9001#msg9001"
EDIT_URL = f"{FORUM_BASE}/index.php?action=post;msg=9001;topic=555.0"


def _html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text="", url="", status=200, headers=None):
        self.text, self.url, self.status_code = text, url, status
        self.headers = headers or {}


class _Session:
    """Routes GETs by URL to fixture pages and records every POST."""

    def __init__(self, pages: dict[str, _Resp], post_resp: _Resp | None = None):
        self.pages, self.post_resp = pages, post_resp
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []

    def get(self, url, timeout=None, headers=None):
        self.gets.append(url)
        return self.pages[url]

    def post(self, url, data=None, timeout=None, headers=None, allow_redirects=True):
        self.posts.append((url, data))
        return self.post_resp


def _session(edit_page="edit_form.html", post_resp=None) -> _Session:
    page = f"{FORUM_BASE}/index.php?topic=555.0"
    return _Session({
        page: _Resp(_html("topic_page.html"), page),
        EDIT_URL: _Resp(_html(edit_page), EDIT_URL),
    }, post_resp)


class TestFetch:
    def test_reads_current_subject_body_and_tokens(self):
        s = _session()
        got = ed.fetch_post_for_edit(s, TOPIC_URL)
        assert got["ok"], got
        assert (got["topic_id"], got["msg_id"]) == (555, 9001)
        assert got["subject"] == "1978-11-01 Madison, WI (LB-01234)"
        assert got["body"] == "[b]PLEASE DO NOT SHARE[/b]\nOld body text"
        assert got["description"] == "LB-01234"
        # The random-named session token and seqnum are carried.
        assert got["fields"]["a1b2c3d4"] == "0f9e8d7c6b5a"
        assert got["fields"]["seqnum"] == "42"
        assert "action=post2" in got["form_action"] and "msg=9001" in got["form_action"]
        # A .msgNNNN link is reduced to the topic's first page.
        assert s.gets[0] == f"{FORUM_BASE}/index.php?topic=555.0"
        assert s.gets[1] == EDIT_URL

    def test_modify_link_for_msg_with_shared_prefix_is_not_picked(self):
        topic_id, msg_id, modify = ed._find_opening_post(_html("topic_page.html"))
        assert (topic_id, msg_id) == (555, 9001)
        assert modify == EDIT_URL

    def test_no_modify_link_falls_back_to_built_url(self):
        html = _html("topic_page.html").replace("action=post;msg=9001", "action=nope")
        topic_id, msg_id, modify = ed._find_opening_post(html)
        assert (msg_id, modify) == (9001, "")
        assert ed._edit_url(555, 9001) == EDIT_URL

    def test_permission_error_is_reported(self):
        got = ed.fetch_post_for_edit(_session("edit_denied.html"), TOPIC_URL)
        assert not got["ok"]
        assert "not allowed to edit" in got["error"]

    def test_login_wall_is_reported(self):
        s = _session()
        login = f"{FORUM_BASE}/index.php?action=login"
        s.pages[f"{FORUM_BASE}/index.php?topic=555.0"] = _Resp("", login)
        got = ed.fetch_post_for_edit(s, TOPIC_URL)
        assert not got["ok"] and "login" in got["error"]


class TestEdit:
    def test_dry_run_default_never_posts(self):
        s = _session()
        got = ed.edit_post(s, TOPIC_URL, "New subject", "New body")
        assert got["ok"] and got["dry_run"]
        assert got["changed"] == ["subject", "body"]
        assert got["current"]["subject"].startswith("1978-11-01")
        assert got["proposed"] == {"subject": "New subject", "body": "New body"}
        assert s.posts == []

    def test_unchanged_text_is_not_a_change(self):
        s = _session()
        got = ed.edit_post(s, TOPIC_URL, "1978-11-01 Madison, WI (LB-01234)",
                           "[b]PLEASE DO NOT SHARE[/b]\r\nOld body text\n", dry_run=False)
        assert got["ok"] and got["changed"] == []
        assert s.posts == []

    def test_save_posts_tokens_and_crlf_body(self):
        loc = f"{FORUM_BASE}/index.php?topic=555.msg9001#msg9001"
        s = _session(post_resp=_Resp(status=302, headers={"Location": loc}))
        got = ed.edit_post(s, TOPIC_URL, "", "line 1\nline 2", dry_run=False)
        assert got["ok"] and got["saved"] and got["changed"] == ["body"]
        url, data = s.posts[0]
        assert "action=post2" in url and "msg=9001" in url
        assert data["a1b2c3d4"] == "0f9e8d7c6b5a"
        assert data["seqnum"] == "42" and data["msg"] == "9001" and data["topic"] == "555"
        assert data["subject"] == "1978-11-01 Madison, WI (LB-01234)"  # blank keeps current
        assert data["message"] == "line 1\r\nline 2"
        assert data["description"] == "LB-01234"
        assert data["post"] == "Save"

    def test_smf_error_page_is_surfaced(self):
        s = _session(post_resp=_Resp(_html("save_error.html"), status=200))
        got = ed.edit_post(s, TOPIC_URL, "New", "", dry_run=False)
        assert not got["ok"]
        assert "message body was left empty" in got["error"]

    def test_redirect_elsewhere_is_a_failure(self):
        loc = f"{FORUM_BASE}/index.php?action=login"
        s = _session(post_resp=_Resp(status=302, headers={"Location": loc}))
        got = ed.edit_post(s, TOPIC_URL, "New", "", dry_run=False)
        assert not got["ok"] and "Unexpected redirect" in got["error"]


# ── Flask routes ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    import backend.paths as _p
    from backend import db as database
    db_path = str(tmp_path / "t.db")
    monkeypatch.setattr(_p, "DATA_DIR", tmp_path)
    database.init_db(db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _patch_login(monkeypatch, session):
    import backend.credentials as cred
    import backend.forum_poster as fp
    monkeypatch.setattr(cred, "get_credentials", lambda _svc: ("user", "pw"))
    monkeypatch.setattr(fp, "_get_session", lambda _u, _p: session)


class TestRoutes:
    def test_edit_form_route(self, client, monkeypatch):
        _patch_login(monkeypatch, _session())
        r = client.get("/api/forum_post/edit_form", query_string={"topic_url": TOPIC_URL})
        d = r.get_json()
        assert d["ok"] and d["msg_id"] == 9001
        assert d["body"].endswith("Old body text")
        assert "fields" not in d  # tokens never leave the backend

    def test_edit_route_is_dry_run_without_confirm(self, client, monkeypatch):
        s = _session()
        _patch_login(monkeypatch, s)
        r = client.post("/api/forum_post/edit",
                        json={"topic_url": TOPIC_URL, "subject": "X", "body": "Y"})
        d = r.get_json()
        assert d["ok"] and d["dry_run"] and s.posts == []

    def test_edit_route_confirm_saves(self, client, monkeypatch):
        loc = f"{FORUM_BASE}/index.php?topic=555.msg9001#msg9001"
        s = _session(post_resp=_Resp(status=302, headers={"Location": loc}))
        _patch_login(monkeypatch, s)
        from backend import db as database
        seen = {}
        monkeypatch.setattr(database, "update_forum_post_subject",
                            lambda url, subj: seen.update(url=url, subj=subj) or 1)
        r = client.post("/api/forum_post/edit",
                        json={"topic_url": TOPIC_URL, "subject": "X", "body": "Y",
                              "confirm": True})
        d = r.get_json()
        assert d["ok"] and d["saved"] and len(s.posts) == 1
        assert seen == {"url": f"{FORUM_BASE}/index.php?topic=555.0", "subj": "X"}

    def test_confirm_must_be_literal_true(self, client, monkeypatch):
        s = _session()
        _patch_login(monkeypatch, s)
        r = client.post("/api/forum_post/edit",
                        json={"topic_url": TOPIC_URL, "subject": "X", "confirm": "yes"})
        assert r.get_json()["dry_run"] and s.posts == []

    def test_non_wtrf_url_rejected(self, client, monkeypatch):
        _patch_login(monkeypatch, _session())
        r = client.post("/api/forum_post/edit",
                        json={"topic_url": "https://example.com/index.php?topic=1.0"})
        assert r.status_code == 400


def test_update_forum_post_subject_matches_topic_id_only(client):
    from backend import db as database
    with database.get_connection() as conn:
        conn.executemany("INSERT INTO entries(lb_number, status) VALUES(?, 'ok')", [(1,), (2,)])
        conn.commit()
    database.add_forum_post(1, "old", f"{FORUM_BASE}/index.php?topic=555.0", 16)
    database.add_forum_post(2, "keep", f"{FORUM_BASE}/index.php?topic=5550.0", 16)
    n = database.update_forum_post_subject(TOPIC_URL, "new")
    assert n == 1
    with database.get_connection() as conn:
        subs = dict(conn.execute("SELECT lb_number, subject FROM forum_posts").fetchall())
    assert subs == {1: "new", 2: "keep"}
