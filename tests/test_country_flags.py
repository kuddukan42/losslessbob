"""Tests for :mod:`backend.country_flags` and the flag prefix on forum subjects.

The date-resolving tests seed a temp DB with ``olof_events`` rows, following
tests/test_olof_bobtalk_search.py's ``_make_db``/``_seed_event`` pattern.
"""
import os
import shutil
import tempfile

import pytest

import backend.db as db
import backend.paths as _paths
from backend.country_flags import flag_for_date, flag_for_location, flag_for_name
from backend.forum_poster import _build_subject

US = "\U0001f1fa\U0001f1f8"
FR = "\U0001f1eb\U0001f1f7"
DE = "\U0001f1e9\U0001f1ea"
SCOTLAND = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_country_flags_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


@pytest.fixture
def temp_db():
    """Point db.DB_PATH at a fresh temp DB, and put it back afterwards.

    flag_for_date() resolves through db.get_connection() with no path argument,
    so the module-level DB_PATH is what a test has to swap — and must restore,
    or every later test in the run inherits a deleted database.
    """
    db_path, tmp_dir = _make_db()
    original = db.DB_PATH
    db.DB_PATH = db_path
    try:
        yield db.get_connection(db_path)
    finally:
        db.DB_PATH = original
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _seed_event(conn, event_id, date_str, country="", region="", city="X"):
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus)"
        " VALUES ('p1', 'http://x', 'dsn')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO olof_events"
        " (event_id, page_filename, event_type, date_str, venue, city, region, country)"
        " VALUES (?, 'p1', 'concert', ?, 'Venue', ?, ?, ?)",
        (event_id, date_str, city, region, country),
    )


# ── flag_for_name ───────────────────────────────────────────────────────────


def test_country_name_maps_to_regional_indicator_pair():
    assert flag_for_name("France") == FR
    assert flag_for_name("  gErMaNy ") == DE


def test_us_state_maps_to_us():
    assert flag_for_name("Tennessee") == US
    assert flag_for_name("District Of Columbia") == US


def test_canadian_province_and_australian_state_map_to_their_country():
    assert flag_for_name("British Columbia") == "\U0001f1e8\U0001f1e6"
    assert flag_for_name("South Australia") == "\U0001f1e6\U0001f1fa"


def test_uk_nations_use_subdivision_flags():
    assert flag_for_name("Scotland") == SCOTLAND
    assert flag_for_name("England").startswith("\U0001f3f4")
    # Northern Ireland has no subdivision flag emoji — it falls back to the UK.
    assert flag_for_name("Northern Ireland") == "\U0001f1ec\U0001f1e7"


def test_olof_spelling_variants_and_parser_typos_resolve():
    nl = "\U0001f1f3\U0001f1f1"
    assert flag_for_name("Holland") == nl
    assert flag_for_name("The Netherlands") == nl
    assert flag_for_name("Irelandw") == "\U0001f1ee\U0001f1ea"


def test_historical_states_with_one_successor_resolve():
    assert flag_for_name("West Germany") == DE
    assert flag_for_name("East Germany") == DE


def test_ambiguous_and_empty_values_yield_no_flag():
    # A wrong flag is worse than no flag — these must stay None.
    for name in ("Yugoslavia", "Unknown State/Province", "Wood",
                 "Australia/Los Angeles", "", None, "Atlantis"):
        assert flag_for_name(name) is None, name


# ── flag_for_date ───────────────────────────────────────────────────────────


def test_date_resolves_via_country_column(temp_db):
    _seed_event(temp_db, 1, "1994-07-03", country="France")
    temp_db.commit()
    assert flag_for_date("1994-07-03") == FR
    # The entries table's own m/d/yy format resolves to the same event.
    assert flag_for_date("7/3/94") == FR


def test_date_falls_back_to_region_when_country_is_blank(temp_db):
    _seed_event(temp_db, 1, "1987-07-18", country="", region="Michigan")
    temp_db.commit()
    assert flag_for_date("1987-07-18") == US


def test_unknown_date_and_unresolvable_event_yield_no_flag(temp_db):
    _seed_event(temp_db, 1, "1991-06-11", country="Yugoslavia")
    temp_db.commit()
    assert flag_for_date("1991-06-11") is None   # no single successor state
    assert flag_for_date("1975-11-15") is None   # no event on that date
    assert flag_for_date("") is None
    assert flag_for_date("not a date") is None


# ── _build_subject ──────────────────────────────────────────────────────────


def test_subject_gets_the_flag_prefix(temp_db):
    _seed_event(temp_db, 1, "1994-07-03", country="France")
    temp_db.commit()
    subject = _build_subject(10876, {"date_str": "7/3/94", "location": "Paris"})
    assert subject == f"{FR} 1994-07-03 Paris (LB-10876)"


def test_bootleg_subject_never_gets_a_flag(temp_db):
    _seed_event(temp_db, 1, "1994-07-03", country="France")
    temp_db.commit()
    subject = _build_subject(
        999, {"date_str": "7/3/94", "location": "Paris", "bootleg_title": "Comp"}
    )
    assert subject == "1994-07-03 BOOTLEG: Comp (LB-00999)"


def test_subject_is_unchanged_when_the_location_does_not_resolve(temp_db):
    subject = _build_subject(9093, {"date_str": "11/15/75",
                                    "location": "Niagara Falls"})
    assert subject == "1975-11-15 Niagara Falls (LB-09093)"


# ── flag_for_location ───────────────────────────────────────────────────────


def test_location_resolves_from_a_state_or_country_part():
    assert flag_for_location("New Haven, Connecticut, Veterans Memorial Coliseum") == US
    assert flag_for_location("Columbia Studio A. Nashville, Tennessee, USA") == US
    assert flag_for_location("Olympia, Paris (France)") == FR


def test_location_with_disagreeing_parts_yields_no_flag():
    # A city that shares a country's name names two places, so it names none.
    assert flag_for_location("Mexico, Missouri") is None


def test_location_that_names_nothing_yields_no_flag():
    for loc in ("", None, "various", "Niagara Falls", "Big Pink house basement"):
        assert flag_for_location(loc) is None, loc


def test_two_letter_abbreviations_are_not_recognised():
    # "DE" is Delaware or Germany; "IN" Indiana or India. No flag beats a wrong one.
    assert flag_for_location("Clearwater, FL") is None
    assert flag_for_location("Bonn, DE") is None


def test_subject_falls_back_to_location_when_olof_has_no_event(temp_db):
    # 1975-11-13 New Haven is a real hole in Olof's corpus (LB-02804).
    subject = _build_subject(
        2804,
        {"date_str": "11/13/75",
         "location": "New Haven, Connecticut, Veterans Memorial Coliseum"},
    )
    assert subject.startswith(f"{US} 1975-11-13 New Haven")
