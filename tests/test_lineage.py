"""Tests for entry_lineage: extract_lb_references, parse_confidence, taper_normalised,
and batch-parse idempotency.
"""
import hashlib
import json
import os
import tempfile

import backend.db as db
import backend.paths as _paths
from backend.db import (
    _compute_parse_confidence,
    _normalise_taper,
    extract_lb_references,
    extract_taper_and_source,
    get_lineage,
    upsert_entry_lineage,
)


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_lineage_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


# ── Test 1: same_as_lb ────────────────────────────────────────────────────────

def test_extract_lb_refs_same_as():
    desc = "This is the same as LB-1234 in all respects — fingerprints match exactly."
    result = extract_lb_references(desc)
    assert 1234 in result["same_as_lb"], f"Expected 1234 in same_as_lb, got {result}"
    lb_nums = [m[0] for m in result["mentions_lb"]]
    assert 1234 in lb_nums


# ── Test 2: derived_from_lb ───────────────────────────────────────────────────

def test_extract_lb_refs_derived_from():
    desc = "Transferred from LB-5678 master tape; no further processing."
    result = extract_lb_references(desc)
    assert 5678 in result["derived_from_lb"], f"Expected 5678 in derived_from_lb, got {result}"
    lb_nums = [m[0] for m in result["mentions_lb"]]
    assert 5678 in lb_nums


# ── Test 3: no LB refs ────────────────────────────────────────────────────────

def test_extract_lb_refs_none():
    desc = "Audience recording taped by John Smith. Great show. DAT > FLAC."
    result = extract_lb_references(desc)
    assert result["mentions_lb"] == []
    assert result["same_as_lb"] == []
    assert result["derived_from_lb"] == []
    assert result["better_than_lb"] == []


# ── Test 4: multiple LB numbers ───────────────────────────────────────────────

def test_extract_lb_refs_multiple():
    desc = (
        "Same recording as LB-100. "
        "Better than LB-200 (this is an upgrade). "
        "Also derived from LB-300 master."
    )
    result = extract_lb_references(desc)
    lb_nums = [m[0] for m in result["mentions_lb"]]
    assert 100 in lb_nums
    assert 200 in lb_nums
    assert 300 in lb_nums
    assert 100 in result["same_as_lb"]
    assert 200 in result["better_than_lb"]
    assert 300 in result["derived_from_lb"]


# ── Test 5: parse_confidence 'high' ──────────────────────────────────────────

def test_parse_confidence_high():
    desc = "Taper: John Smith\nSource: AKG 460 > Sony TCD-D8 DAT > FLAC"
    taper_name, source_chain = extract_taper_and_source(desc)
    assert taper_name is not None, "Expected taper_name to be parsed"
    assert source_chain is not None, "Expected source_chain to be parsed"
    confidence = _compute_parse_confidence(desc, taper_name, source_chain)
    assert confidence == "high", f"Expected 'high', got '{confidence}'"


# ── Test 6: parse_confidence 'none' ──────────────────────────────────────────

def test_parse_confidence_none():
    confidence = _compute_parse_confidence("", None, None)
    assert confidence == "none"
    confidence2 = _compute_parse_confidence("Great show!", None, None)
    assert confidence2 == "none"


# ── Test 7: taper_normalised ──────────────────────────────────────────────────

def test_taper_normalised():
    assert _normalise_taper("J. Smith") == "j smith"
    assert _normalise_taper("john_smith-taper") == "john smith taper"
    assert _normalise_taper("JOHN SMITH") == "john smith"
    assert _normalise_taper("Smith, Jr.") == "smith jr"
    assert _normalise_taper(None) is None
    assert _normalise_taper("") is None


# ── Test 8: idempotency ───────────────────────────────────────────────────────

def test_idempotency():
    db_path, _tmp = _make_db()
    conn = db.get_connection(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entries(lb_number, description) VALUES(?,?)",
        (9999, "Taper: Bob Jones\nSource: Neumann KM84 > DAT > FLAC"),
    )
    conn.commit()

    desc = "Taper: Bob Jones\nSource: Neumann KM84 > DAT > FLAC"
    text_hash = hashlib.sha256(desc.encode()).hexdigest()
    taper_name, source_chain = extract_taper_and_source(desc)
    refs = extract_lb_references(desc)
    taper_norm = _normalise_taper(taper_name)
    confidence = _compute_parse_confidence(desc, taper_name, source_chain)

    row = {
        "lb_number": 9999,
        "taper_name": taper_name,
        "source_chain": source_chain,
        "taper_normalised": taper_norm,
        "mentions_lb": json.dumps(refs["mentions_lb"]),
        "same_as_lb": json.dumps(refs["same_as_lb"]),
        "derived_from_lb": json.dumps(refs["derived_from_lb"]),
        "better_than_lb": json.dumps(refs["better_than_lb"]),
        "parse_confidence": confidence,
        "source_text_hash": text_hash,
    }

    upsert_entry_lineage(row, db_path)
    first = get_lineage(9999, db_path)
    assert first is not None
    assert first["source_text_hash"] == text_hash

    upsert_entry_lineage(row, db_path)
    second = get_lineage(9999, db_path)

    for key in ("taper_name", "source_chain", "taper_normalised",
                "parse_confidence", "source_text_hash"):
        assert first[key] == second[key], f"Mismatch on {key}: {first[key]!r} vs {second[key]!r}"


def test_alternate_to_chain_is_neither_same_as_nor_derived_from():
    """Golden review 3 (LB-14054): "Alternate to LB-a/LB-b, which appear to be derived
    from same recording" says this entry is a *different* recording from all of them."""
    from backend.db import extract_lb_references

    refs = extract_lb_references(
        'version "e", Alternate to LB-2470/LB-2478/LB-6445/LB-7214/LB-10916, which appear'
        " to be derived from same recording., Not a good recording.")
    assert refs["same_as_lb"] == [] and refs["derived_from_lb"] == []
    refs = extract_lb_references("This is the same recording as LB-7214, a copy of LB-2478.")
    assert refs["same_as_lb"] == [7214, 2478]


def test_same_phrase_binds_to_the_refs_in_its_own_sentence():
    """Silver review (LB-13981): a comparison listing LB-1116/LB-13219 is not a same_as
    claim just because "LB-14078 is same recording" sits within 200 chars."""
    from backend.db import extract_lb_references

    refs = extract_lb_references(
        "of the other 3 LB-1116 is most distant and echoey, LB-13219 is next distant and"
        " boomy, and this sounded best; excellent sound [A]; LB-14078 is same recording as"
        " this based on same clapping wavs at end of d1t2")
    assert refs["same_as_lb"] == [14078]


def test_different_recording_than_list_is_not_same_as():
    """Silver review: "different recording than LB-a, LB-b (which are all the same
    recording)" was stored as same_as for every ref in the list."""
    from backend.db import extract_lb_references

    refs = extract_lb_references(
        "levels are low;  different recording than LB-837, LB-972, and LB-1920 (which are"
        " all the same recording) based on different crowd; same recording as LB-5000")
    assert refs["same_as_lb"] == [5000]
    refs = extract_lb_references(
        "This is the same recording as LB-0991 but is a recent transfer from my DAT clone")
    assert refs["same_as_lb"] == [991]


def test_fix_of_and_own_entry_refs_are_same_as():
    """"Fixed LB-x" / "LosslessBob entry: LB-x" name this set's own recording."""
    from backend.db import extract_lb_references

    assert extract_lb_references("version \"a\"; Fixed LB-5048: only circulating")[
        "same_as_lb"] == [5048]
    assert extract_lb_references(
        "Low gen tape > CDR > EAC > Flac [lk aud set], LosslessBob entry: LB-2710. very"
        " similar to previous version")["same_as_lb"] == [2710]
