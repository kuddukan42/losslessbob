"""Plan Phase E (GOLDEN_DOSSIER_FIX_PLAN) taper-attribution guards, E1-E6.

Each case is the live-DB text that exposed the bug, trimmed to the part that matters.
"""
import json
import os
import tempfile

import backend.db as db
import backend.paths as _paths
import backend.taper_attribution as taper_attribution
from backend import dossier_fields
from backend.qc import rules


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_taper_guard_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path


def _seed_entry(conn, lb, description, taper_normalised=None, taper_name=None,
                same_as=None, source_type="Audience"):
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, description, source_type) VALUES (?, ?, ?)",
        (lb, description, source_type),
    )
    conn.execute(
        """INSERT OR REPLACE INTO entry_lineage
           (lb_number, taper_name, source_chain, taper_normalised, mentions_lb,
            same_as_lb, derived_from_lb, better_than_lb, parse_confidence, source_text_hash)
           VALUES (?, ?, NULL, ?, '[]', ?, '[]', '[]', 'medium', 'test')""",
        (lb, taper_name or taper_normalised, taper_normalised, json.dumps(same_as or [])),
    )
    conn.commit()


def _seed_family(conn, fam_id, members, conf=0.9):
    conn.executemany(
        "INSERT OR REPLACE INTO recording_families(lb_number, fam_id, concert_date)"
        " VALUES (?, ?, '1995-03-16')",
        [(lb, fam_id) for lb in members],
    )
    conn.execute(
        "INSERT OR REPLACE INTO tapematch_family_meta"
        " (fam_id, concert_date, member_count, review_flag, conf)"
        " VALUES (?, '1995-03-16', ?, 0, ?)",
        (fam_id, len(members), conf),
    )
    conn.commit()


def _attr(conn, lb):
    row = conn.execute("SELECT * FROM taper_attributions WHERE lb_number = ?", (lb,)).fetchone()
    return dict(row) if row else None


# ── E1: negation guard in extract_lb_references ────────────────────────────────

def test_e1_negated_reference_is_not_same_as():
    desc = ("version \"d\", I wasn't able to identify this upload ..., (it has none of the "
            "flaws/pops described in LB-0301/LB-4356/LB-5531/LB-9064). Sound like a B+\n\n"
            "bittorrent download 10/17; this is a sort of close eac match on t1 to")
    refs = db.extract_lb_references(desc)
    assert refs["same_as_lb"] == []
    assert [m[0] for m in refs["mentions_lb"]] == [301, 4356, 5531, 9064]


def test_e1_plain_same_as_still_links():
    refs = db.extract_lb_references("this is the same recording as LB-4356; no flaws")
    assert refs["same_as_lb"] == [4356]


# ── E2: no propagation onto board / ALD / broadcast / matrix sources ───────────

def test_e2_no_propagation_onto_soundboard_ald_or_matrix():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 100, "Taper: Spot\nSource: Schoeps > DAT", "spot")
    _seed_entry(conn, 101, "ALD sbd", same_as=[100], source_type="ALD")
    _seed_entry(conn, 102, "monitor soundboard", same_as=[100], source_type="Soundboard")
    _seed_entry(conn, 103, "matrix of aud + sbd", same_as=[100], source_type="Mixed")
    _seed_entry(conn, 104, "Audience copy", same_as=[100])

    taper_attribution.recompute(db_path=db_path)

    for lb in (101, 102, 103):
        assert _attr(conn, lb) is None, f"LB-{lb} must not inherit a taper"
    assert _attr(conn, 104)["taper_normalised"] == "spot"


# ── E3: family taper conflict → disputed + R-T6 ────────────────────────────────

def test_e3_weak_family_conflict_renders_disputed_and_fires_rt6():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 556, "NTF, DAT > CD", "net taper f")
    _seed_entry(conn, 3491, "Taper: Spot\nSource: X", "spot")
    _seed_entry(conn, 5768, "Net Taper: I, Lineage: OKM", "net taper i")
    _seed_entry(conn, 9000, "no info")
    _seed_family(conn, "F-A", [556, 3491, 5768, 9000], conf=0.221)

    taper_attribution.recompute(db_path=db_path)

    # A weak family never floods, but its unattributed member gets a conflict row.
    row = _attr(conn, 9000)
    assert row is not None and row["conflict"] == 1
    for lb in (556, 3491, 5768):
        tr = dossier_fields.taper_render(conn, lb, reload_aliases=False)
        assert tr["confidence"] == "disputed" and tr["name"]
        assert tr["notice"].startswith("disputed: same family also credits")

    findings = list(rules.RULES["R-T6"].func(conn))
    assert {f.entity_key for f in findings} == {"556", "3491", "5768"}
    assert all(f.severity == "warn" for f in findings)


def test_e3_single_taper_family_is_not_disputed():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, "Taper: Spot\nSource: X", "spot")
    _seed_entry(conn, 2, "Taper: Spot\nSource: Y", "spot")
    _seed_family(conn, "F-B", [1, 2])

    taper_attribution.recompute(db_path=db_path)

    assert dossier_fields.taper_render(conn, 1, reload_aliases=False)["confidence"] == "confirmed"
    assert list(rules.RULES["R-T6"].func(conn)) == []


# ── E4: series codes must be bound ─────────────────────────────────────────────

def test_e4_comparison_series_code_is_not_a_credit():
    desc = ("lodec, local taper DE C, Sony 155 t -> Sony TCD3\n\nbittorrent download 09/12; "
            "they all have full sound; this is not as warm as nti\n\nand")
    assert db._normalise_taper(db.extract_taper_and_source(desc)[0]) != "net taper i"


def test_e4_bound_series_codes_still_parse():
    cases = {
        "LTB, DAT > FLAC, no further info.": "ltb",
        "version \"b\"; 02/13 Carsten reports this to be LTJ;": "ltj",
        "Net Taper: I, Lineage: OKM II R -> Sony DAT": "net taper i",
        "Off DAT clone(s), LTF, Source/Lineage:": "ltf",
        "bittorrent download; this is same recording as LTD\n": "ltd",
    }
    for desc, want in cases.items():
        assert db._normalise_taper(db.extract_taper_and_source(desc)[0]) == want, desc


def test_e4_different_recording_than_series_code_ignored():
    desc = "version \"b\"\n\nbittorrent download 03/10; different recording than LTD\n"
    assert db._normalise_taper(db.extract_taper_and_source(desc)[0]) != "ltd"


# ── E5: "recorded by" / "a <x> recording" are explicit when bound ──────────────

def test_e5_recorded_by_is_explicit_confirmed():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 16029, "sway mixed, 106.49 mins, recorded by sway (44-16 resolution), "
                             "mixed by audiowhore", "sway")
    _seed_entry(conn, 1323, "a Spot recording\n\n(a bittorrent from 06/12)", "spot")

    taper_attribution.recompute(db_path=db_path)

    for lb in (16029, 1323):
        row = _attr(conn, lb)
        assert row["confidence"] == "confirmed"
        assert any(e["kind"] == "explicit" for e in json.loads(row["evidence_json"]))


def test_e5_unbound_recorded_by_does_not_confirm():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, "recorded by an unknown fan; thanks to spot for the tape", "spot")
    _seed_entry(conn, 2, "most likely a Spot recording", "spot")

    taper_attribution.recompute(db_path=db_path)

    assert _attr(conn, 1) is None
    assert _attr(conn, 2) is None


# ── E6: stated taper with no attribution ───────────────────────────────────────

def test_e6_stated_taper_renders_when_unattributed():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 16026, "badpainter 24, Sony PCM M10 recorder, Recorded by badpainter, "
                             "edited and mastered by subtr83", "badpainter")
    _seed_entry(conn, 2, "badpainter 24, a fine night", "badpainter")

    taper_attribution.recompute(db_path=db_path)

    tr = dossier_fields.taper_render(conn, 16026, reload_aliases=False)
    assert tr["name"] == "badpainter" and tr["confidence"] == "stated"
    assert dossier_fields.taper_render(conn, 2, reload_aliases=False)["name"] is None


def test_e6_curator_decision_suppresses_stated():
    db_path = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 3, "Recorded by badpainter", "badpainter")
    conn.execute("INSERT INTO taper_confirmations (lb_number, taper_normalised, action)"
                 " VALUES (3, 'badpainter', 'unresolved')")
    conn.commit()

    assert dossier_fields.taper_render(conn, 3, reload_aliases=False)["name"] is None
