"""Same-venue two-show days (TODO-345): show key from date_raw, selector, no guessing.

Built against the committed golden fixture (real rows cut from live data), using
1974-01-06 at The Spectrum: DSN02250 "6 January 1974 – Afternoon" and DSN02260
"6 January 1974 – Evening".
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.dossier import build_dossier, show_part_key
from tools.dossier_golden import load_fixture

DATE = "1974-01-06"


@pytest.fixture(scope="module")
def fixture_db():
    import backend.db as _db
    import backend.paths as _paths

    saved = (_db.DB_PATH, _paths.DATA_DIR, _paths.DB_PATH)
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_two_show_")
    db_path = os.path.join(tmp_dir, "golden.db")
    load_fixture(db_path)
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = _paths.DB_PATH = Path(db_path)
    yield db_path
    _db.close_connection(db_path)
    _db.DB_PATH, _paths.DATA_DIR, _paths.DB_PATH = saved
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.parametrize("date_raw, session_title, key", [
    ("6 January 1974 – Afternoon", None, "afternoon"),
    ("14 January 1974 — Evening", None, "evening"),
    ("25 October 2010", "Early show", "early"),
    ("25 October 2010", "Late Show", "late"),
    ("1 August 1971", "Afternoon concert.", "afternoon"),
    ("20 January 1968", "The Woody Guthrie Memorial Concert. Evening show.", "evening"),
    ("6 January 1974", None, None),
    ("Early September 2023", None, None),
    ("1 July 1965", "Private afternoon concert", None),
    ("24 July 1965", "Newport Folk Festival. Evening.", None),
    ("1 August 1971", "Rehearsals before the Bangla Desh Concert.", None),
])
def test_show_part_key(date_raw, session_title, key):
    assert show_part_key(date_raw, session_title) == key


def test_two_show_day_without_show_is_ambiguous(fixture_db):
    res = build_dossier(DATE, db_path=fixture_db)
    assert res["ambiguous"] is True and res["reason"] == "show"
    assert [(c["show"], c["label"], c["location"]) for c in res["candidates"]] == [
        ("afternoon", "Afternoon", "The Spectrum"), ("evening", "Evening", "The Spectrum")]


def test_unknown_show_key_is_not_guessed(fixture_db):
    res = build_dossier(DATE, show="late", db_path=fixture_db)
    assert res.get("ambiguous") is True and res["reason"] == "show"


@pytest.mark.parametrize("show, dsn, opener", [
    ("afternoon", 2250, "Ballad Of Hollis Brown"),
    ("evening", 2260, "Rainy Day Women # 12 & 35"),
])
def test_each_show_gets_its_own_event(fixture_db, show, dsn, opener):
    d = build_dossier(DATE, location="The Spectrum", show=show, db_path=fixture_db)
    assert not d.get("ambiguous")
    assert d["show"]["show_part"] == show
    assert d["setlist"][0]["title"] == opener
    assert [(o["show"], o["selected"]) for o in d["show_options"]] == [
        ("afternoon", show == "afternoon"), ("evening", show == "evening")]
    xref = {x["key"]: x for x in d["xref"]}
    assert xref["olof"]["url"].endswith(f"#DSN{dsn:05d}")
    # bobdylan.com has two same-venue pages for the day and nothing says which is which.
    assert xref["bobdylan"]["unavailable"] is True


def test_single_show_day_ignores_show_param(fixture_db):
    d = build_dossier("1975-12-08", show="evening", db_path=fixture_db)
    assert not d.get("ambiguous")
    assert "show_options" not in d and "show_part" not in d["show"]


def test_colliding_keys_withhold_the_event(fixture_db, tmp_path):
    copy = str(tmp_path / "collide.db")
    shutil.copyfile(fixture_db, copy)
    conn = sqlite3.connect(copy)
    conn.execute("UPDATE olof_events SET date_raw = '6 January 1974 – Afternoon' "
                 "WHERE event_id = 2260")
    conn.commit()
    conn.close()
    import backend.db as _db
    try:
        d = build_dossier(DATE, db_path=copy)
        assert not d.get("ambiguous")
        assert "setlist" not in d and "show_options" not in d
        assert d["qc"]["refused"] is True
        assert any(r.startswith("G1") for r in d["qc"]["reasons"])
    finally:
        _db.close_connection(copy)


def test_routes_offer_a_selector(fixture_db):
    from backend.app import create_app

    client = create_app().test_client()
    assert client.get(f"/api/dossier?date={DATE}").status_code == 300

    chooser = client.get(f"/api/dossier/html?date={DATE}&chooser=1&inline=1")
    assert chooser.status_code == 300 and chooser.mimetype == "text/html"
    body = chooser.get_data(as_text=True)
    assert "show=afternoon" in body and "show=evening" in body

    page = client.get(f"/api/dossier/html?date={DATE}&show=evening&inline=1")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'aria-current="page">Evening<' in html
    assert "show=afternoon" in html

    bb = client.get(f"/api/dossier/bbcode?date={DATE}&show=afternoon")
    assert bb.status_code == 200 and "(Afternoon)" in bb.get_json()["text"]


# ---------------------------------------------------------------------------
# C32 D3: per-show source split
# ---------------------------------------------------------------------------

def test_olof_lb_list_parses_every_shape():
    from backend.dossier_fields import olof_lb_list

    assert olof_lb_list("x.\nLB-numbers for this concert: LB-2637 , LB-3602 , LB-9309 .\nOther") \
        == {2637, 3602, 9309}
    assert olof_lb_list("LB-number for this show: LB-11 .") == {11}
    assert olof_lb_list("LB-number s for this gig: LB-7") == {7}
    assert olof_lb_list("No list here, LB-5 mentioned elsewhere.") == set()


@pytest.mark.parametrize("texts, side", [
    (("Philadelphia", "Afternoon, low gen reel", ""), "a"),
    (("", "", "aft low gen reel ... same recording as evening"), "a"),
    (("", "late jt ys pitched", ""), "b"),
    (("Evening Show, Philadelphia", None, None), "b"),
    (("", "version \"a\"; Early Show", ""), "a"),
    (("Philadelphia", "Master tape > CD", "later generation"), None),
])
def test_lineage_show_side(texts, side):
    from backend.dossier_fields import lineage_show_side

    assert lineage_show_side(*texts) == side


def test_split_keeps_the_other_shows_sources_off_the_page(fixture_db):
    """Olof's LB lists and lineage words put each source on one show; the rest on both."""
    import backend.db as _db
    from backend.dossier_fields import (
        SPLIT_OTHER,
        SPLIT_SHOW,
        SPLIT_UNASSIGNED,
        show_source_split,
    )

    conn = _db.get_connection(fixture_db)
    events = {r["event_id"]: r for r in conn.execute(
        "SELECT * FROM olof_events WHERE event_id IN (2250, 2260)")}
    entries = [
        {"lb_number": 2637, "location": "", "source_chain": "", "description": ""},
        {"lb_number": 2638, "location": "", "source_chain": "", "description": ""},
        {"lb_number": 11476, "location": "", "source_chain": "Evening, low gen reel",
         "description": ""},
        {"lb_number": 99999, "location": "Philadelphia", "source_chain": "cd > flac",
         "description": ""},
    ]
    aft = show_source_split(conn, events[2250], entries)
    eve = show_source_split(conn, events[2260], entries)
    assert aft == {2637: SPLIT_SHOW, 2638: SPLIT_OTHER, 11476: SPLIT_OTHER,
                   99999: SPLIT_UNASSIGNED}
    assert eve == {2637: SPLIT_OTHER, 2638: SPLIT_SHOW, 11476: SPLIT_SHOW,
                   99999: SPLIT_UNASSIGNED}


def test_each_show_page_lists_only_its_sources(fixture_db):
    aft = build_dossier(DATE, location="The Spectrum", show="afternoon", db_path=fixture_db)
    eve = build_dossier(DATE, location="The Spectrum", show="evening", db_path=fixture_db)

    def lbs(d):
        return {m["lb"] for b in d.get("sources", []) for m in b["members"]}

    assert "LB-02637" in lbs(aft) and "LB-02637" not in lbs(eve)
    assert "LB-02638" in lbs(eve) and "LB-02638" not in lbs(aft)
