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
