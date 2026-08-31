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
    _absolutise,
    _canonical_topic_url,
    _lb_numbers_in,
    expand_lb_shorthand,
    is_wtrf_topic_url,
    parse_seed_targets,
    parse_topic_links,
    pick_by_content,
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
    # Scheme-less — what the address bar displays, so what a paste yields.
    "www.watchingtheriverflow.org/index.php?topic=1234.0",
    "watchingtheriverflow.org/index.php?topic=1234.0",
])
def test_is_wtrf_topic_url_accepts(url):
    assert is_wtrf_topic_url(url)


def test_a_scheme_less_paste_is_not_glued_onto_the_forum_base():
    """The bug this guards: _resolve_url reads a bare host as a relative path
    and produces FORUM_BASE + "/www.watchingtheriverflow.org/…"."""
    out = _absolutise("www.watchingtheriverflow.org/index.php?topic=1234.0")
    assert out == "http://www.watchingtheriverflow.org/index.php?topic=1234.0"
    assert out.count("watchingtheriverflow.org") == 1


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


@pytest.mark.parametrize("line", [
    "www.watchingtheriverflow.org/index.php?topic=29688.msg103317#msg103317",
    "watchingtheriverflow.org/index.php?topic=29688.msg103317",
    "index.php?topic=29688.0",
    "http://www.watchingtheriverflow.org/index.php?topic=29688.msg103317#msg103317",
    "see www.watchingtheriverflow.org/index.php?topic=29688.0, then stop.",
])
def test_every_paste_shape_reaches_the_same_topic(line):
    """A scheme-less copy is the common case, not the exception — dropping it
    reported "no WTRF topic links found" on a perfectly good link."""
    specs = parse_topic_links(line)
    assert len(specs) == 1
    assert specs[0].url == f"{FORUM_BASE}/index.php?topic=29688.0"


def test_a_scheme_less_link_can_still_be_pinned():
    specs = parse_topic_links(
        "LB-00707 www.watchingtheriverflow.org/index.php?topic=42.0")
    assert specs[0].lb_number == 707


def test_mixed_paste_shapes_dedupe_to_one_topic():
    specs = parse_topic_links(
        "www.watchingtheriverflow.org/index.php?topic=1234.msg99#msg99\n"
        "https://watchingtheriverflow.org/index.php?topic=1234.15\n"
        "index.php?topic=1234.0\n"
    )
    assert [s.url for s in specs] == [f"{FORUM_BASE}/index.php?topic=1234.0"]


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


def test_resolve_defers_several_lb_numbers_to_a_content_check(stub_topic):
    """Prose cannot tell a cross-reference from a two-entry torrent, so the
    post only nominates and the torrent's contents settle it later."""
    stub_topic(_post(topic_title="LB-00099 / LB-00100 pair",
                     torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, None, TOPIC))
    assert out["lb_candidates"] == [99, 100]
    assert out["lb_number"] == 99          # primary = first in the field
    assert out["confidence"] == "ambiguous"
    assert out["needs_content_check"] is True
    assert out["error"] == ""              # not an error — a deferred decision


def test_a_single_lb_needs_no_content_check(stub_topic):
    stub_topic(_post(topic_title="LB-00099 Sydney", torrent_url="http://x/a"))
    assert resolve_link(None, LinkSpec(TOPIC, None, TOPIC))["needs_content_check"] is False


def test_an_explicit_pin_beats_an_ambiguous_post(stub_topic):
    stub_topic(_post(topic_title="LB-00099 / LB-00100 pair",
                     torrent_url="http://x/a"))
    out = resolve_link(None, LinkSpec(TOPIC, 707, TOPIC))
    assert (out["lb_number"], out["confidence"]) == (707, "definitive")
    assert out["needs_content_check"] is False
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


# ── pick_by_content: bytes settle what the prose cannot ──────────────────────

PIECE_LEN = 512


def _bencode(value) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return _bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(_bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(
            _bencode(k) + _bencode(value[k]) for k in sorted(value)
        ) + b"e"
    raise TypeError(type(value))


def _write_torrent(path: Path, name: str, files: dict[str, bytes]) -> str:
    """Write a minimal multi-file torrent; pieces are irrelevant to scoring."""
    meta = {b"info": {
        b"name": name.encode(),
        b"piece length": PIECE_LEN,
        b"pieces": b"\x00" * 20,
        b"files": [{b"path": [n.encode()], b"length": len(b)}
                   for n, b in files.items()],
    }}
    path.write_bytes(_bencode(meta))
    return str(path)


@pytest.fixture
def two_entry_rig(tmp_path, monkeypatch):
    """A torrent spanning two LB entries, plus a cross-referenced third.

    Mirrors the real "84 Revisited LB-14777+ LB-14778.torrent": one file
    covering two catalogue entries, each filed in its own folder. LB-11880 is
    the cross-reference shape — nominated by the prose, holds none of the bytes.
    """
    disc1 = {"d1t01.flac": b"\x11" * 900, "d1t02.flac": b"\x12" * 800}
    disc2 = {"d2t01.flac": b"\x21" * 700, "d2t02.flac": b"\x22" * 600}
    torrent = _write_torrent(tmp_path / "t.torrent", "84 Revisited",
                             {**disc1, **disc2})

    folders = {}
    for lb, blobs in ((14777, disc1), (14778, disc2), (11880, {})):
        d = tmp_path / f"LB-{lb:05d}"
        d.mkdir()
        for n, b in blobs.items():
            (d / n).write_bytes(b)
        folders[lb] = [str(d)]

    monkeypatch.setattr("backend.wtrf_seed.database.is_seedable_to_tracker",
                        lambda lb, db_path=None: (True, None))
    monkeypatch.setattr("backend.wtrf_seed.database.get_folders_for_lb",
                        lambda lb, db_path=None: folders.get(lb, []))
    return torrent, folders


def test_content_keeps_both_halves_of_a_multi_entry_torrent(two_entry_rig):
    torrent, folders = two_entry_rig
    out = pick_by_content([14777, 14778, 11880], torrent)
    assert out["winner"] == 14777
    assert out["matched"] == [14777, 14778]
    # The other half's folder is offered up for hardlinking into one overlay.
    assert out["link_dirs"] == folders[14778]


def test_content_drops_a_cross_referenced_entry(two_entry_rig):
    """LB-11880 is named in the prose but holds none of the torrent's files."""
    torrent, _ = two_entry_rig
    out = pick_by_content([11880, 14777], torrent)
    assert out["winner"] == 14777
    assert 11880 not in out["matched"]
    assert out["scores"][11880] == 0


def test_content_prefers_the_candidate_supplying_the_most(tmp_path, monkeypatch):
    """Three of the torrent's four files come from LB-1, so LB-1 wins the
    overlay's source slot however the post ordered its nominations."""
    files = {f"t{i}.flac": bytes([i]) * (900 + i) for i in range(4)}
    torrent = _write_torrent(tmp_path / "t.torrent", "Show", files)
    big, small = tmp_path / "big", tmp_path / "small"
    for d in (big, small):
        d.mkdir()
    for n in ("t0.flac", "t1.flac", "t2.flac"):
        (big / n).write_bytes(files[n])
    (small / "t3.flac").write_bytes(files["t3.flac"])

    monkeypatch.setattr("backend.wtrf_seed.database.is_seedable_to_tracker",
                        lambda lb, db_path=None: (True, None))
    monkeypatch.setattr("backend.wtrf_seed.database.get_folders_for_lb",
                        lambda lb, db_path=None: [str(small if lb == 2 else big)])
    out = pick_by_content([2, 1], torrent)          # 2 nominated first
    assert out["winner"] == 1                       # ...but 1 supplies more
    assert out["scores"] == {1: 3, 2: 1}
    assert out["link_dirs"] == [str(small)]


def test_content_breaks_a_tie_by_nomination_order(two_entry_rig):
    """Equal halves of one torrent: the post's own ordering decides which
    folder is the overlay's source. Both are hardlinked either way."""
    torrent, folders = two_entry_rig
    assert pick_by_content([14778, 14777], torrent)["winner"] == 14778
    assert pick_by_content([14777, 14778], torrent)["winner"] == 14777


def test_content_refuses_when_no_candidate_holds_anything(two_entry_rig):
    torrent, _ = two_entry_rig
    out = pick_by_content([11880], torrent)
    assert out["winner"] is None
    assert "holds any of the torrent's files" in out["reason"]


def test_content_excludes_a_non_public_candidate(two_entry_rig, monkeypatch):
    """An entry that may not be published can never win, however well it matches."""
    torrent, _ = two_entry_rig
    monkeypatch.setattr("backend.wtrf_seed.database.is_seedable_to_tracker",
                        lambda lb, db_path=None: (lb != 14777, "not public"))
    out = pick_by_content([14777, 14778], torrent)
    assert out["winner"] == 14778
    assert 14777 not in out["scores"]


def test_content_ignores_a_same_named_file_of_the_wrong_size(tmp_path, monkeypatch):
    """Basename alone is not identity — a different recording's d1t01.flac
    must not be counted as supplying the torrent's."""
    torrent = _write_torrent(tmp_path / "t.torrent", "Show",
                             {"d1t01.flac": b"\x11" * 900})
    d = tmp_path / "wrong"
    d.mkdir()
    (d / "d1t01.flac").write_bytes(b"\x11" * 400)   # same name, wrong size
    monkeypatch.setattr("backend.wtrf_seed.database.is_seedable_to_tracker",
                        lambda lb, db_path=None: (True, None))
    monkeypatch.setattr("backend.wtrf_seed.database.get_folders_for_lb",
                        lambda lb, db_path=None: [str(d)])
    out = pick_by_content([42], torrent)
    assert out["winner"] is None


# ── LB-only pastes: a forum round-up copied as plain text ────────────────────
# The links in such a post are hyperlinks whose href does not survive a
# plain-text copy — every one collapses to the bare "www.watchingtheriverflow.org"
# display text. Only the LB numbers make it across, and they are enough.

ROUNDUP = """shows. Many thanks to everyone's help once again!

1974-01-31 New York
LB-11486/88 (LTE)
www.watchingtheriverflow.org
www.watchingtheriverflow.org
LB-11612 (SM)
www.watchingtheriverflow.org

1978-06-27 Dortmund
LB-12653 (NTB)
www.watchingtheriverflow.org
LB-12654 (LTB)
www.watchingtheriverflow.org
"""


@pytest.fixture
def catalogue(monkeypatch):
    """Stub the entry dates the shorthand expansion verifies against."""
    dates = {11486: "1/31/74", 11488: "1/31/74", 11487: "1/23/76",
             11612: "1/31/74", 12653: "6/27/78", 12654: "6/27/78"}
    monkeypatch.setattr("backend.wtrf_seed._entry_date", dates.get)
    return dates


def test_a_roundup_paste_yields_no_links_at_all(catalogue):
    """The premise: there is no URL in this paste to walk."""
    assert parse_topic_links(ROUNDUP) == []


def test_a_roundup_paste_still_yields_every_lb(catalogue):
    targets = parse_seed_targets(ROUNDUP)
    assert [t.lb_number for t in targets] == [11486, 11488, 11612, 12653, 12654]
    assert all(not t.by_link for t in targets)


def test_a_bare_host_line_contributes_nothing_but_suppresses_nothing(catalogue):
    """"www.watchingtheriverflow.org" has no topic= and is not a target, but it
    must not stop the LB numbers on neighbouring lines being picked up."""
    targets = parse_seed_targets(
        "LB-11612 (SM)\nwww.watchingtheriverflow.org\nLB-12653 (NTB)\n")
    assert [t.lb_number for t in targets] == [11612, 12653]


def test_shorthand_expands_only_to_a_same_date_sibling(catalogue):
    """LB-11486/88 is 11486 and 11488 — not the range through 11487, which is
    a different show two years later."""
    assert expand_lb_shorthand(11486, "/88") == [11486, 11488]
    assert expand_lb_shorthand(11486, "/87") == [11486]      # 1/23/76, refused


def test_shorthand_refuses_an_unknown_entry(catalogue):
    assert expand_lb_shorthand(11486, "/99") == [11486]


def test_shorthand_ignores_a_suffix_longer_than_the_base(catalogue):
    assert expand_lb_shorthand(11486, "/123456") == [11486]


def test_a_mixed_paste_yields_both_kinds(catalogue):
    targets = parse_seed_targets(
        f"{TOPIC}\nLB-12653 (NTB)\nwww.watchingtheriverflow.org\n")
    assert [(t.by_link, t.lb_number) for t in targets] == [
        (True, None), (False, 12653)]


def test_an_lb_pinned_to_a_link_is_not_repeated_as_its_own_target(catalogue):
    targets = parse_seed_targets(f"LB-12653 {TOPIC}\nLB-12653 (NTB)\n")
    assert len(targets) == 1
    assert targets[0].by_link and targets[0].lb_number == 12653


def test_date_headers_and_source_tags_are_not_lb_numbers(catalogue):
    assert parse_seed_targets("1974-01-31 New York\n(LTE) (SM) (NTB)\n") == []
