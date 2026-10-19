"""Tests for backend/wtrf_discovery.py (TODO-135). All HTTP is mocked."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from backend import wtrf_discovery as wd


def _row(tid: int, title: str, sub: str = "") -> str:
    d = f'<small id="topicdesc_{tid}">{sub}</small>' if sub else ""
    return (f'<tr><td class="subject"><a href="index.php?topic={tid}.0">{title}</a>{d}'
            f'<p>Started by <a href="index.php?action=profile;u=1">tapist</a></p></td></tr>')


def _page(*rows: str) -> str:
    return f'<div class="topic_table"><table>{"".join(rows)}</table></div>'


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    wd.ensure_schema(c)
    return c


@pytest.mark.parametrize("title,sub,atts,expected", [
    ("1965-05-07 Manchester LB-8862", "", [], {8862}),
    ("Show LB-8", "", [], {8}),
    ("Show lb 0042", "", [], {42}),
    ("1964-11-27 SF LB-5876 + LB-5877", "", [], {5876, 5877}),
    ("Tokyo 1978", "LB-1237", [], {1237}),
    ("Detroit 1994", "", ["Detroit 1994-08-29 NTA-LB-9209.torrent"], {9209}),
    ("x", "", ["1965 various (LB-09924).torrent"], {9924}),
    ("Mansfield No LB.torrent", "", [], set()),
    ("Blackburn 1234", "", [], set()),
    ("LB-123456", "", [], set()),
])
def test_parse(title, sub, atts, expected):
    assert {n for n, _ in wd.parse_lb_numbers(title, sub, atts)} == expected


def test_schema_idempotent(conn):
    wd.ensure_schema(conn)
    wd.ensure_schema(conn)


def test_import_archive(conn, tmp_path):
    ap = tmp_path / "a.db"
    a = sqlite3.connect(ap)
    a.executescript("""
    CREATE TABLE wtrf_topics(topic_id INTEGER, board_id INT, url TEXT, title TEXT,
      subtitle TEXT, poster TEXT, posted_at TEXT);
    CREATE TABLE wtrf_attachments(topic_id INT, filename TEXT);
    INSERT INTO wtrf_topics VALUES (1,16,'u1','Foo LB-8','','p','2026-01-01T00:00:00');
    INSERT INTO wtrf_topics VALUES (2,16,'u2','Bar','','p',NULL);
    INSERT INTO wtrf_attachments VALUES (2,'Bar LB-77.torrent');
    """)
    a.commit()
    a.close()
    r = wd.import_from_archive(conn, ap)
    assert r == {"topics": 2, "lb_links": 2}
    wd.import_from_archive(conn, ap)  # idempotent
    assert conn.execute("select count(*) from scraped_topic_lbs").fetchone()[0] == 2
    got = wd.lookup_for_lb(conn, 77)
    assert got[0]["matched_in"] == "attachment" and got[0]["source"] == wd.SOURCE_ARCHIVE


class FakeSession:
    def __init__(self, pages: dict[str, str]):
        self.pages, self.calls = pages, []

    def get(self, url, timeout=0):
        self.calls.append(url)
        return SimpleNamespace(url=url, status_code=200, text=self.pages.get(url, _page()),
                               raise_for_status=lambda: None)


def test_sync_live_paced_and_incremental(conn):
    b = wd.FORUM_BASE_URL
    pages = {
        f"{b}/index.php?board=16.0": _page(_row(10, "A LB-100"), _row(11, "B no number")),
        f"{b}/index.php?board=16.20": _page(_row(9, "C LB-5", "x")),
        f"{b}/index.php?topic=11.0":
            '<a href="index.php?action=dlattach;attach=1">B show LB-222.torrent</a>',
    }
    sleeps: list[float] = []
    s = FakeSession(pages)
    st = wd.sync_from_board(s, conn, 16, sleep=sleeps.append, page_delay=3, topic_delay=4)
    assert st["new_topics"] == 3 and st["stopped"] == "end_of_board"
    assert st["topic_fetches"] == 1
    assert [x["topic_id"] for x in wd.lookup_for_lb(conn, 222)] == [11]
    assert 3 in sleeps
    # second run: page 0 fully known -> stops, no topic refetch
    s2 = FakeSession(pages)
    st2 = wd.sync_from_board(s2, conn, 16, sleep=lambda _x: None)
    assert st2["stopped"] == "caught_up" and st2["pages"] == 1 and st2["topic_fetches"] == 0


def test_sync_session_expired(conn):
    class S:
        def get(self, url, timeout=0):
            return SimpleNamespace(url="x?action=login", text="", status_code=200)

    with pytest.raises(RuntimeError):
        wd.sync_from_board(S(), conn, 16, sleep=lambda _x: None)


def test_forum_posts_for_lb_merges_scraped(tmp_path):
    from backend import db
    p = tmp_path / "t.db"
    db.init_db(p)
    c = db.get_connection(p)
    c.execute("INSERT INTO entries(lb_number) VALUES (8)")
    c.execute("INSERT INTO forum_posts(lb_number, subject, topic_url) VALUES "
              "(8,'mine','https://x/index.php?topic=50.0')")
    wd.store_topic(c, topic_id=50, board_id=16, subject="dup LB-8", source="board_index")
    wd.store_topic(c, topic_id=51, board_id=16, subject="other LB-8", source="board_index",
                   topic_url="https://x/index.php?topic=51.0")
    c.commit()
    rows = db.get_forum_posts_for_lb(8, p)
    assert [(r["source"], r["subject"]) for r in rows] == [
        ("local", "mine"), ("wtrf_scrape", "other LB-8")]
