"""Tests for tools/checksum_dispute_report.py (TODO-302).

Covers the pairing of the two references into one finding per track and the
retag-vs-damage split that pairing makes possible.
"""

import sqlite3

import pytest

from backend import checksum_provenance as prov
from tools import checksum_dispute_report as report


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE checksums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checksum TEXT NOT NULL, filename TEXT NOT NULL,
            chk_type TEXT NOT NULL, lb_number INTEGER NOT NULL,
            xref INTEGER DEFAULT 0, UNIQUE(checksum, lb_number)
        )
    """)
    conn.execute("""
        CREATE TABLE entries (
            lb_number INTEGER PRIMARY KEY, date_str TEXT, location TEXT,
            taper_name TEXT, source_type TEXT, lb_category TEXT,
            timing TEXT, rating TEXT
        )
    """)
    prov.ensure_schema(conn)
    return conn


def _dispute(**kw):
    """A dispute row with sane defaults, overridden by kw."""
    base = {
        "lb_number": 900, "filename": "track01.flac", "chk_type": "m",
        "reference_kind": "db", "reference_checksum": "a" * 32,
        "reference_file": None, "source_checksum": "b" * 32,
        "source_file": "LBF-00900-up.md5.txt", "source_kind": "uploader",
        "source_scope": "self", "source_suspect": 0, "displaced_to": None,
        "kind": "isolated_mismatch", "confidence": "high",
        "rows_agree": 19, "rows_disagree": 1,
    }
    base.update(kw)
    return base


def _findings(conn):
    return report.split_receipt_verdicts(conn, report.merge_by_track(report.load_rows(conn)))


def test_db_only_disagreement_is_a_db_error():
    conn = _conn()
    prov.record_disputes(conn, [_dispute()])
    found = _findings(conn)
    assert len(found) == 1
    assert found[0]["verdict"] == "db_error"


def test_both_references_holding_the_same_value_is_a_receipt_finding():
    """DB and lbdir agreeing against the uploader means Jeff's copy is the outlier."""
    conn = _conn()
    prov.record_disputes(conn, [
        _dispute(reference_kind="db"),
        _dispute(reference_kind="lbdir", reference_file="LBF-00900-lbdir.txt"),
    ])
    found = _findings(conn)
    assert len(found) == 1  # the two rows pair into one finding
    assert found[0]["verdict"] in ("retag", "audio_differs", "receipt_unknown")
    assert set(found[0]["refs"]) == {"db", "lbdir"}


def test_references_disagreeing_with_each_other_is_still_a_db_error():
    """If the DB does not even match the lbdir, the DB is the thing that is wrong."""
    conn = _conn()
    prov.record_disputes(conn, [
        _dispute(reference_kind="db", reference_checksum="a" * 32),
        _dispute(reference_kind="lbdir", reference_checksum="c" * 32,
                 reference_file="LBF-00900-lbdir.txt"),
    ])
    assert _findings(conn)[0]["verdict"] == "db_error"


def test_md5_only_disagreement_with_an_agreeing_ffp_is_a_retag():
    """FFP hashes the decoded audio; MD5 hashes the container. Only MD5 moved."""
    conn = _conn()
    conn.execute(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        ("f" * 32, "track01.flac", "f", 900),
    )
    conn.commit()
    prov.record_disputes(conn, [
        _dispute(reference_kind="db"),
        _dispute(reference_kind="lbdir", reference_file="LBF-00900-lbdir.txt"),
    ])
    assert _findings(conn)[0]["verdict"] == "retag"


def test_a_disputed_ffp_means_the_audio_itself_differs():
    conn = _conn()
    prov.record_disputes(conn, [
        _dispute(reference_kind="db", chk_type="f"),
        _dispute(reference_kind="lbdir", chk_type="f",
                 reference_file="LBF-00900-lbdir.txt"),
    ])
    assert _findings(conn)[0]["verdict"] == "audio_differs"


def test_md5_dispute_is_audio_differs_when_the_ffp_is_disputed_too():
    """A retag cannot explain it when the audio hash moved as well."""
    conn = _conn()
    conn.execute(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        ("f" * 32, "track01.flac", "f", 900),
    )
    conn.commit()
    rows = []
    for chk_type in ("m", "f"):
        for ref in ("db", "lbdir"):
            rows.append(_dispute(
                chk_type=chk_type, reference_kind=ref,
                source_checksum=("b" if chk_type == "m" else "d") * 32,
                reference_file="LBF-00900-lbdir.txt" if ref == "lbdir" else None,
            ))
    prov.record_disputes(conn, rows)
    assert {f["verdict"] for f in _findings(conn)} == {"audio_differs"}


def test_md5_only_with_no_ffp_anywhere_is_undecidable():
    conn = _conn()
    prov.record_disputes(conn, [
        _dispute(reference_kind="db"),
        _dispute(reference_kind="lbdir", reference_file="LBF-00900-lbdir.txt"),
    ])
    assert _findings(conn)[0]["verdict"] == "receipt_unknown"


def test_lbdir_only_disagreement_is_its_own_verdict():
    conn = _conn()
    prov.record_disputes(conn, [
        _dispute(reference_kind="lbdir", reference_file="LBF-00900-lbdir.txt"),
    ])
    assert _findings(conn)[0]["verdict"] == "lbdir_only"


def test_orphan_flag_marks_a_source_value_absent_from_checksums():
    conn = _conn()
    conn.execute(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        ("e" * 32, "track02.flac", "m", 900),
    )
    conn.commit()
    prov.record_disputes(conn, [_dispute(), _dispute(filename="track02.flac",
                                                     source_checksum="e" * 32)])
    by_name = {f["filename"]: f for f in _findings(conn)}
    assert by_name["track01.flac"]["source_orphan"]
    assert not by_name["track02.flac"]["source_orphan"]


def test_set_divergences_are_excluded_unless_asked():
    conn = _conn()
    prov.record_disputes(conn, [_dispute(kind="set_divergence", confidence="low")])
    assert report.load_rows(conn) == []
    assert len(report.load_rows(conn, include_divergence=True)) == 1


def test_render_produces_a_self_contained_document():
    conn = _conn()
    conn.execute("INSERT INTO entries (lb_number, date_str, location) VALUES (?,?,?)",
                 (900, "4/9/95", "Glasgow"))
    conn.commit()
    prov.record_disputes(conn, [_dispute()])
    html = report.render(_findings(conn), divergence_count=7)
    assert "<!doctype html>" in html
    assert "LB-00900" in html and "Glasgow" in html
    assert "http://" not in html.split("<style>")[0].replace(
        'href="http://www.losslessbob', "")  # no external asset hosts in the head
    assert "7" in html  # the excluded-divergence count is stated


@pytest.mark.parametrize("verdict", report._VERDICT_ORDER)
def test_every_verdict_has_a_label_and_a_blurb(verdict):
    assert report._VERDICT_LABEL[verdict]
    assert report._VERDICT_BLURB[verdict]
