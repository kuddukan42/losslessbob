"""Tests for backend.checksum_provenance (TODO-296).

Covers source classification, the isolated-mismatch vs whole-set-divergence
split, both references (DB and lbdir), verdict persistence across re-runs, and
the lookup rescue index.
"""

import sqlite3

import pytest

from backend import checksum_provenance as prov

# --------------------------------------------------------------------------- helpers

def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE checksums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checksum TEXT NOT NULL,
            filename TEXT NOT NULL,
            chk_type TEXT NOT NULL,
            lb_number INTEGER NOT NULL,
            xref INTEGER DEFAULT 0,
            UNIQUE(checksum, lb_number)
        )
    """)
    prov.ensure_schema(conn)
    return conn


def _hash(n):
    """Deterministic distinct 32-hex value for track n."""
    return f"{n:032x}"


def _seed_db(conn, lb, count, chk_type="m", ext=".flac"):
    """Insert `count` well-formed DB checksum rows for one LB."""
    conn.executemany(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        [(_hash(i), f"track{i:02d}{ext}", chk_type, lb) for i in range(1, count + 1)],
    )
    conn.commit()


def _write_md5(tmp_path, name, rows):
    """Write a flat uploader-style md5 manifest and return its path."""
    p = tmp_path / name
    p.write_text("\n".join(f"{h} *{f}" for f, h in rows) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- classify

@pytest.mark.parametrize("name,expected", [
    ("LBF-15933-dylan.ffp.txt", {"lb_number": 15933, "kind": "uploader",
                                 "scope": "self", "suspect": False}),
    ("LBF-00047-bd00-09-23bad.md5.txt", {"lb_number": 47, "kind": "uploader",
                                         "scope": "self", "suspect": True}),
    ("LBF-01497-lbdir-bd74-01-14aft.txt", {"lb_number": 1497, "kind": "lbdir",
                                           "scope": "self", "suspect": False}),
    ("LBF-00156-xref-01595-text.txt", {"lb_number": 156, "kind": "uploader",
                                       "scope": "xref", "suspect": False}),
])
def test_classify_source_variants(name, expected):
    info = prov.classify_source(name)
    assert info is not None
    for key, value in expected.items():
        assert info[key] == value, key


def test_classify_source_skips_non_checksum_files():
    assert prov.classify_source("LBF-07775-DigiFlawFinder-bd01.wavf.html") is None
    assert prov.classify_source("LBF-00001-page.html") is None
    assert prov.classify_source("index.html") is None


def test_classify_source_xref_records_the_other_lb():
    assert prov.classify_source("LBF-00156-xref-01595-text.txt")["xref_lb"] == 1595


# ------------------------------------------------------------------- audit_attachment

def test_isolated_mismatch_is_flagged_high_confidence(tmp_path):
    """One bad row among many good ones is the corrupted-DB-value signature."""
    conn = _conn()
    _seed_db(conn, 500, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[13] = ("track14.flac", _hash(999))  # uploader disagrees on exactly one track
    path = _write_md5(tmp_path, "LBF-00500-uploader.md5.txt", rows)

    found = prov.audit_attachment(path, prov.load_db_reference(conn))

    assert len(found) == 1
    d = found[0]
    assert d["filename"] == "track14.flac"
    assert d["kind"] == "isolated_mismatch"
    assert d["confidence"] == "high"
    assert d["reference_checksum"] == _hash(14)
    assert d["reference_kind"] == "db"
    assert d["source_checksum"] == _hash(999)
    assert (d["rows_agree"], d["rows_disagree"]) == (19, 1)


def test_whole_set_divergence_is_not_a_db_error(tmp_path):
    """A different version filed under the same LB must not be reported as DB-bad."""
    conn = _conn()
    _seed_db(conn, 501, 20)
    rows = [(f"track{i:02d}.flac", _hash(1000 + i)) for i in range(1, 21)]
    path = _write_md5(tmp_path, "LBF-00501-remaster.md5.txt", rows)

    found = prov.audit_attachment(path, prov.load_db_reference(conn))

    assert len(found) == 20
    assert {d["kind"] for d in found} == {"set_divergence"}
    assert {d["confidence"] for d in found} == {"low"}


def test_agreement_alone_yields_no_disputes(tmp_path):
    conn = _conn()
    _seed_db(conn, 502, 10)
    path = _write_md5(tmp_path, "LBF-00502-uploader.md5.txt",
                      [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 11)])
    assert prov.audit_attachment(path, prov.load_db_reference(conn)) == []


def test_too_few_agreeing_rows_is_not_isolated(tmp_path):
    """Below MIN_AGREE there is no evidence the file describes the same fileset."""
    conn = _conn()
    _seed_db(conn, 503, 2)
    path = _write_md5(tmp_path, "LBF-00503-uploader.md5.txt", [
        ("track01.flac", _hash(1)),
        ("track02.flac", _hash(888)),
    ])
    found = prov.audit_attachment(path, prov.load_db_reference(conn))
    assert [d["kind"] for d in found] == ["set_divergence"]


def test_suspect_and_xref_sources_are_downgraded_to_medium(tmp_path):
    conn = _conn()
    _seed_db(conn, 504, 20)
    _seed_db(conn, 505, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(777))

    suspect = _write_md5(tmp_path, "LBF-00504-set-old.md5.txt", rows)
    xref = _write_md5(tmp_path, "LBF-00505-xref-00123-text.txt", rows)
    db_ref = prov.load_db_reference(conn)

    assert prov.audit_attachment(suspect, db_ref)[0]["confidence"] == "medium"
    assert prov.audit_attachment(xref, db_ref)[0]["confidence"] == "medium"


def test_filenames_absent_from_db_are_ignored(tmp_path):
    """Bonus tracks and never-ingested filesets are not evidence either way."""
    conn = _conn()
    _seed_db(conn, 506, 10)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 11)]
    rows.append(("bonus99.flac", _hash(4242)))
    path = _write_md5(tmp_path, "LBF-00506-uploader.md5.txt", rows)
    assert prov.audit_attachment(path, prov.load_db_reference(conn)) == []


def test_db_filename_with_directory_prefix_still_matches(tmp_path):
    """checksums.filename may carry a Windows subdirectory prefix; compare basenames."""
    conn = _conn()
    conn.executemany(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number) VALUES (?,?,?,?)",
        [(_hash(i), f"Disc 1\\track{i:02d}.flac", "m", 507) for i in range(1, 11)],
    )
    conn.commit()
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 11)]
    rows[5] = ("track06.flac", _hash(606))
    path = _write_md5(tmp_path, "LBF-00507-uploader.md5.txt", rows)

    found = prov.audit_attachment(path, prov.load_db_reference(conn))
    assert len(found) == 1
    assert found[0]["filename"] == "Disc 1\\track06.flac"  # reported as the DB stores it


def test_several_db_values_for_one_track_means_no_mismatch(tmp_path):
    """An LB carrying two filesets legitimately holds two hashes for a filename."""
    conn = _conn()
    _seed_db(conn, 508, 10)
    conn.execute(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref) VALUES (?,?,?,?,?)",
        (_hash(3003), "track03.flac", "m", 508, 1),
    )
    conn.commit()
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 11)]
    rows[2] = ("track03.flac", _hash(3003))
    path = _write_md5(tmp_path, "LBF-00508-uploader.md5.txt", rows)
    assert prov.audit_attachment(path, prov.load_db_reference(conn)) == []


# ---------------------------------------------------------------- lbdir reference

def test_lbdir_reference_catches_a_file_that_did_not_arrive_intact(tmp_path):
    """Jeff hashes what he downloaded, so lbdir vs uploader is a transfer check.

    The DB faithfully records the lbdir here — only the uploader disagrees — so
    the same track raises one dispute against each reference.
    """
    conn = _conn()
    _seed_db(conn, 700, 20)
    good = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    _write_md5(tmp_path, "LBF-00700-lbdir-set.txt", good)
    bad = list(good)
    bad[0] = ("track01.flac", _hash(7007))
    _write_md5(tmp_path, "LBF-00700-uploader.md5.txt", bad)

    summary = prov.run_audit(conn, tmp_path)

    assert (summary["ref_db"], summary["ref_lbdir"]) == (1, 1)
    by_ref = {d["reference_kind"]: d for d in prov.get_disputes(conn)}
    assert set(by_ref) == {"db", "lbdir"}
    assert by_ref["lbdir"]["reference_file"] == "LBF-00700-lbdir-set.txt"
    assert by_ref["lbdir"]["reference_checksum"] == _hash(1)
    assert by_ref["db"]["reference_file"] is None


def test_lbdir_is_never_checked_against_itself(tmp_path):
    conn = _conn()
    _seed_db(conn, 701, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    path = _write_md5(tmp_path, "LBF-00701-lbdir-set.txt", rows)
    ref = prov.load_lbdir_reference(tmp_path)
    assert ref.by_file[(701, "track01.flac", "m")] == {_hash(1): "track01.flac"}
    assert prov.audit_attachment(path, ref) == []


def test_an_xref_manifest_does_not_become_the_lbdir_reference(tmp_path):
    """An xref lbdir describes another entry's fileset and would poison the ref."""
    _write_md5(tmp_path, "LBF-00702-xref-01595-lbdir.txt",
               [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 11)])
    assert prov.load_lbdir_reference(tmp_path).by_file == {}


def test_db_only_skips_the_lbdir_reference(tmp_path):
    conn = _conn()
    _seed_db(conn, 703, 20)
    good = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    _write_md5(tmp_path, "LBF-00703-lbdir-set.txt", good)
    bad = list(good)
    bad[0] = ("track01.flac", _hash(7373))
    _write_md5(tmp_path, "LBF-00703-uploader.md5.txt", bad)

    summary = prov.run_audit(conn, tmp_path, lbdir_reference=False)
    assert (summary["ref_db"], summary["ref_lbdir"]) == (1, 0)


def test_displaced_value_names_the_track_that_holds_it(tmp_path):
    """Two swapped tracks are the same audio under different names, not damage."""
    conn = _conn()
    _seed_db(conn, 704, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(2))
    rows[1] = ("track02.flac", _hash(1))
    path = _write_md5(tmp_path, "LBF-00704-uploader.md5.txt", rows)

    found = {d["filename"]: d for d in prov.audit_attachment(path, prov.load_db_reference(conn))}
    assert found["track01.flac"]["displaced_to"] == "track02.flac"
    assert found["track02.flac"]["displaced_to"] == "track01.flac"


def test_a_plain_mismatch_has_no_displacement(tmp_path):
    conn = _conn()
    _seed_db(conn, 705, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(9999))
    path = _write_md5(tmp_path, "LBF-00705-uploader.md5.txt", rows)
    found = prov.audit_attachment(path, prov.load_db_reference(conn))
    assert found[0]["displaced_to"] is None


# --------------------------------------------------------------------------- run_audit

def test_run_audit_skips_lbdir_unless_asked(tmp_path):
    conn = _conn()
    _seed_db(conn, 600, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(111))
    _write_md5(tmp_path, "LBF-00600-lbdir-set.txt", rows)

    assert prov.run_audit(conn, tmp_path)["disputes"] == 0
    assert prov.run_audit(conn, tmp_path, include_lbdir=True)["disputes"] == 1


def test_run_audit_summary_and_lb_filter(tmp_path):
    conn = _conn()
    _seed_db(conn, 601, 20)
    _seed_db(conn, 602, 20)
    for lb in (601, 602):
        rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
        rows[0] = ("track01.flac", _hash(lb))
        _write_md5(tmp_path, f"LBF-00{lb}-uploader.md5.txt", rows)

    summary = prov.run_audit(conn, tmp_path)
    assert summary["disputes"] == 2
    assert summary["isolated_mismatch"] == 2
    assert summary["high"] == 2
    assert summary["lb_numbers"] == 2

    conn.execute("DELETE FROM checksum_disputes")
    assert prov.run_audit(conn, tmp_path, lb_numbers=[601])["disputes"] == 1


def test_rerun_is_idempotent_and_keeps_the_human_verdict(tmp_path):
    conn = _conn()
    _seed_db(conn, 603, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(333))
    _write_md5(tmp_path, "LBF-00603-uploader.md5.txt", rows)

    prov.run_audit(conn, tmp_path)
    dispute_id = prov.get_disputes(conn)[0]["id"]
    assert prov.set_dispute_status(conn, dispute_id, "confirmed", note="mistyped in DB")

    prov.run_audit(conn, tmp_path)
    stored = conn.execute("SELECT * FROM checksum_disputes").fetchall()
    assert len(stored) == 1
    assert stored[0]["status"] == "confirmed"
    assert stored[0]["note"] == "mistyped in DB"


def test_run_audit_tolerates_a_missing_mirror(tmp_path):
    conn = _conn()
    assert prov.run_audit(conn, tmp_path / "nope")["disputes"] == 0


def test_ensure_schema_rebuilds_a_pre_reference_kind_table():
    """The v1 shape is dropped, not migrated — every row is re-derivable."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE checksum_disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lb_number INTEGER NOT NULL,
            db_checksum TEXT NOT NULL
        )
    """)
    conn.execute("INSERT INTO checksum_disputes (lb_number, db_checksum) VALUES (1, 'x')")
    conn.commit()

    prov.ensure_schema(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(checksum_disputes)")}
    assert "reference_kind" in cols and "db_checksum" not in cols
    assert conn.execute("SELECT COUNT(*) FROM checksum_disputes").fetchone()[0] == 0
    prov.ensure_schema(conn)  # second call is a no-op


def test_set_dispute_status_rejects_unknown_status(tmp_path):
    conn = _conn()
    with pytest.raises(ValueError):
        prov.set_dispute_status(conn, 1, "maybe")


# ----------------------------------------------------------------------- get_disputes

def test_get_disputes_hides_low_confidence_noise_by_default(tmp_path):
    conn = _conn()
    _seed_db(conn, 604, 20)
    _seed_db(conn, 605, 20)
    good = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    good[0] = ("track01.flac", _hash(444))
    _write_md5(tmp_path, "LBF-00604-uploader.md5.txt", good)
    _write_md5(tmp_path, "LBF-00605-remaster.md5.txt",
               [(f"track{i:02d}.flac", _hash(2000 + i)) for i in range(1, 21)])

    prov.run_audit(conn, tmp_path)
    assert [d["lb_number"] for d in prov.get_disputes(conn)] == [604]
    assert len(prov.get_disputes(conn, kind=None, confidence=None)) == 21
    assert prov.get_disputes(conn, lb_number=605) == []


# ------------------------------------------------------------- lookup_disputed_checksums

def test_lookup_rescue_returns_the_uploader_vouched_checksum(tmp_path):
    conn = _conn()
    _seed_db(conn, 606, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(555))
    _write_md5(tmp_path, "LBF-00606-uploader.md5.txt", rows)
    prov.run_audit(conn, tmp_path)

    hit = prov.lookup_disputed_checksums(conn, [_hash(555)])
    assert hit[_hash(555)]["lb_number"] == 606
    assert hit[_hash(555)]["reference_checksum"] == _hash(1)
    # The DB's own (wrong) value is not a rescue key.
    assert prov.lookup_disputed_checksums(conn, [_hash(1)]) == {}
    assert prov.lookup_disputed_checksums(conn, []) == {}


def test_lookup_rescue_ignores_dismissed_and_divergent(tmp_path):
    conn = _conn()
    _seed_db(conn, 607, 20)
    _seed_db(conn, 608, 20)
    rows = [(f"track{i:02d}.flac", _hash(i)) for i in range(1, 21)]
    rows[0] = ("track01.flac", _hash(666))
    _write_md5(tmp_path, "LBF-00607-uploader.md5.txt", rows)
    _write_md5(tmp_path, "LBF-00608-remaster.md5.txt",
               [(f"track{i:02d}.flac", _hash(3000 + i)) for i in range(1, 21)])
    prov.run_audit(conn, tmp_path)

    assert prov.lookup_disputed_checksums(conn, [_hash(3001)]) == {}  # set_divergence
    prov.set_dispute_status(conn, prov.get_disputes(conn)[0]["id"], "dismissed")
    assert prov.lookup_disputed_checksums(conn, [_hash(666)]) == {}
