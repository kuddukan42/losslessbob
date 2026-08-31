"""Tests for backend.wtrf_seed — pasted WTRF links to a seeded recording.

The parsing half is pure and covered exhaustively here; the fetching half is
exercised against a stub session, since the real board is a small hobbyist
forum that must not be hit by a test run.
"""
from pathlib import Path

import pytest

from backend.forum_poster import FORUM_BASE
from backend.tracker_seed import SeedOptions, overlay_root_for
from backend.wtrf_seed import (
    LinkSpec,
    _canonical_topic_url,
    _lb_numbers_in,
    is_wtrf_topic_url,
    parse_topic_links,
    resolve_link,
)

TOPIC = f"{FORUM_BASE}/index.php?topic=1234.0"


# ── LB tag extraction ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("LB-00008.torrent", [8]),
    ("LB 707 and LB_808", [707, 808]),
    ("lb-00707 lb-707", [707]),          # same number, padded and not
    ("no tag here", []),
    ("LB-123456", []),                    # six digits is not an LB number
    ("LB-00707 vs LB-00808 vs LB-00707", [707, 808]),
])
def test_lb_numbers_in(text, expected):
    assert _lb_numbers_in(text) == expected


# ── Link recognition and canonicalisation ────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.watchingtheriverflow.org/index.php?topic=1234.0",
    "http://watchingtheriverflow.org/index.php?topic=1234.msg99#msg99",
    "index.php?topic=1234.0",
])
def test_is_wtrf_topic_url_accepts(url):
    assert is_wtrf_topic_url(url)


@pytest.mark.parametrize("url", [
    "https://example.com/index.php?topic=1234.0",
    "https://www.watchingtheriverflow.org/index.php?action=profile",
    "https://losslessbob.com/lb/00707",
])
def test_is_wtrf_topic_url_rejects(url):
    assert not is_wtrf_topic_url(url)


def test_canonical_collapses_scheme_www_anchor_and_offset():
    """Every way of naming topic 1234 reduces to one URL on FORUM_BASE."""
    variants = [
        "https://www.watchingtheriverflow.org/index.php?topic=1234.0",
        "http://watchingtheriverflow.org/index.php?topic=1234.15",
        "https://www.watchingtheriverflow.org/index.php?topic=1234.msg99#msg99",
    ]
    assert {_canonical_topic_url(u) for u in variants} == {TOPIC}


def test_parse_dedupes_and_preserves_order():
    text = (
        "https://www.watchingtheriverflow.org/index.php?topic=1234.msg99#msg99\n"
        "https://example.com/ignored\n"
        "http://watchingtheriverflow.org/index.php?topic=999.0\n"
        "http://www.watchingtheriverflow.org/index.php?topic=1234.15\n"
    )
    specs = parse_topic_links(text)
    assert [s.url for s in specs] == [TOPIC, f"{FORUM_BASE}/index.php?topic=999.0"]


def test_parse_pins_an_lb_written_before_the_link():
    specs = parse_topic_links(f"LB-00707 {TOPIC}")
    assert specs[0].lb_number == 707


def test_parse_refuses_to_pin_when_the_line_names_several_lbs():
    """Two numbers on one line is not a pin — the post decides instead."""
    specs = parse_topic_links(f"LB-707 or maybe LB-808 {TOPIC}")
    assert specs[0].lb_number is None


def test_parse_ignores_digits_inside_the_url_itself():
    specs = parse_topic_links(f"{FORUM_BASE}/index.php?topic=707.0")
    assert specs[0].lb_number is None


def test_parse_of_empty_text_is_empty():
    assert parse_topic_links("") == []
    assert parse_topic_links("just some notes, no links") == []


# ── resolve_link ─────────────────────────────────────────────────────────────

def _post(**kw) -> dict:
    base = {"body_text": "", "torrent_url": None, "topic_title": "",
            "attachment_text": "", "post_date": None}
    base.update(kw)
    return base


@pytest.fixture
def stub_topic(monkeypatch):
    """Make _fetch_topic return a canned post instead of hitting the forum."""
    def _install(post: dict):
        monkeypatch.setattr("backend.wtrf_seed._fetch_topic",
                            lambda session, url, delay: post)
    return _install


def test_resolve_prefers_the_attachment_filename(stub_topic):
    stub_topic(_post(
        attachment_text="LB-00008.torrent",
        topic_title="Dylan 1966 — LB-00099 discussion",
        body_text="see also LB-00123",
        torrent_url="http://x/dlattach?attach=5",
    ))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert (out["lb_number"], out["lb_source"], out["confidence"]) == (
        8, "attachment", "definitive")
    assert out["error"] == ""


def test_resolve_falls_back_to_the_title_then_the_body(stub_topic):
    stub_topic(_post(topic_title="LB-00099 Sydney", body_text="LB-00123",
                     torrent_url="http://x/dlattach?attach=5"))
    assert resolve_link(None, LinkSpec(TOPIC, None, TOPIC))["lb_number"] == 99

    stub_topic(_post(body_text="LB-00123 only", torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert (out["lb_number"], out["confidence"]) == (123, "medium")


def test_resolve_refuses_to_guess_between_several_lb_numbers(stub_topic):
    """Seeding the wrong recording under someone's post is unrecoverable."""
    stub_topic(_post(topic_title="LB-00099 / LB-00100 pair",
                     torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert out["lb_number"] is None
    assert out["confidence"] == "ambiguous"
    assert "pin one" in out["error"]


def test_an_explicit_pin_beats_an_ambiguous_post(stub_topic):
    stub_topic(_post(topic_title="LB-00099 / LB-00100 pair",
                     torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, 707, TOPIC))
    assert (out["lb_number"], out["confidence"]) == (707, "definitive")
    assert out["error"] == ""


def test_resolve_reports_a_post_with_no_torrent(stub_topic):
    stub_topic(_post(topic_title="LB-00099", body_text="no attachment here"))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert out["torrent_url"] is None
    assert "no .torrent attachment" in out["error"]


def test_resolve_reports_an_unreadable_topic(stub_topic):
    stub_topic(_post())
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert "unreadable" in out["error"]


def test_resolve_reports_a_post_with_no_lb_tag(stub_topic):
    stub_topic(_post(topic_title="Sydney 1966", body_text="great show",
                     torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert out["lb_number"] is None
    assert "no LB number" in out["error"]


# ── The overlay is per-tracker ───────────────────────────────────────────────

def test_wtrf_and_tuit_overlays_never_share_a_directory():
    """A WTRF torrent and a TUIT torrent of the same show differ in their
    sidecars, so each tracker gets its own overlay root."""
    source = Path("/mnt/DATA0/Concerts/1966/some show")
    wtrf = overlay_root_for(source, SeedOptions("wtrf"))
    tuit = overlay_root_for(source, SeedOptions("tuit"))
    assert wtrf.name == "WTRF Seeds"
    assert tuit.name == "TUIT Seeds"
    assert wtrf.parent == tuit.parent


def test_overlay_root_override_wins():
    opts = SeedOptions("wtrf", overlay_root="/mnt/DATA1/elsewhere")
    assert overlay_root_for(Path("/mnt/DATA0/Concerts/x"), opts) == Path(
        "/mnt/DATA1/elsewhere")
