"""TODO-356: stated-rig conflicts flag a family for review (R-F2, auto_triage R8)."""
from __future__ import annotations

import json
import shutil

import pytest

import backend.db as db
from backend import dossier_fields as df
from backend.qc import rules
from backend.qc.review import _build_context
from backend.tapematch_autoflag import RIG_RULE
from backend.tapematch_sync import sync_tapematch_families
from tests.test_tapematch_sync import _make_app_db, _make_family_obs_db

_RUN = "20260101_000000"
_DATE = "1991-01-01"


@pytest.fixture()
def app():
    db_path, tmp_dir = _make_app_db()
    conn = db.get_connection(db_path)
    yield db_path, conn, tmp_dir
    db.close_connection(db_path)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _entry(conn, lb, chain):
    conn.execute("INSERT OR REPLACE INTO entries (lb_number, source_chain, status) "
                 "VALUES (?, ?, 'ok')", (lb, chain))


def _family(conn, fam_id, lbs, conf=0.9):
    for lb in lbs:
        conn.execute("INSERT INTO recording_families (lb_number, fam_id, concert_date) "
                     "VALUES (?, ?, ?)", (lb, fam_id, _DATE))
    conn.execute("INSERT INTO tapematch_family_meta (fam_id, concert_date, member_count, conf) "
                 "VALUES (?, ?, ?, ?)", (fam_id, _DATE, len(lbs), conf))


def test_stated_rigs_groups_members_by_brand(app):
    _, conn, _ = app
    _entry(conn, 1, "Schoeps MK4 > DAT")
    _entry(conn, 2, "Neumann KM140 > DAT")
    _entry(conn, 3, "mics > DAT")  # no brand: omitted
    assert df.stated_rigs(conn, [1, 2, 3]) == {"schoeps": [1], "neumann": [2]}


def test_family_rig_conflicts_only_reports_multi_brand_families(app):
    _, conn, _ = app
    _entry(conn, 1, "Schoeps MK4 > DAT")
    _entry(conn, 2, "Neumann KM140 > DAT")
    _entry(conn, 3, "Schoeps MK41 > DAT")
    _entry(conn, 4, "Schoeps MK4 > MD")
    _family(conn, "F-mixed", [1, 2])
    _family(conn, "F-same", [3, 4])
    assert df.family_rig_conflicts(conn) == {"F-mixed": {"schoeps": [1], "neumann": [2]}}


def test_members_rig_conflict_names_mics_and_tapers(app):
    _, conn, _ = app
    _entry(conn, 1, "Schoeps MK4 > DAT")
    _entry(conn, 2, "Neumann KM140 > DAT")
    for lb, taper in ((1, "spot"), (2, "ltf")):
        conn.execute("INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                     " evidence_json, conflict) VALUES (?, ?, 'confirmed', '[]', 0)", (lb, taper))
    assert df.members_rig_conflict(conn, [1, 2]) == ["mics: neumann, schoeps",
                                                     "tapers: ltf, spot"]
    assert df.members_rig_conflict(conn, [1]) == []


def test_rule_f2_fires_per_family_with_context(app):
    _, conn, _ = app
    _entry(conn, 1, "Schoeps MK4 > DAT")
    _entry(conn, 2, "Neumann KM140 > DAT")
    _family(conn, "F-mixed", [1, 2], conf=0.42)
    findings = list(rules.RULES["R-F2"].func(conn))
    assert len(findings) == 1
    f = findings[0]
    assert (f.entity_kind, f.entity_key, f.severity) == ("family", "F-mixed", "warn")
    assert f.evidence["mics"] == {"neumann": [2], "schoeps": [1]}
    assert "conf 0.42" in f.detail
    ctx = _build_context(conn, "R-F2", "family", "F-mixed", f.evidence)
    assert [r["mic"] for r in ctx["member_rigs"]] == ["schoeps", "neumann"]


def test_rule_f2_quiet_without_conflict(app):
    _, conn, _ = app
    _entry(conn, 1, "Schoeps MK4 > DAT")
    _entry(conn, 2, "no lineage")
    _family(conn, "F-one", [1, 2])
    assert list(rules.RULES["R-F2"].func(conn)) == []


def _sync(db_path, tmp_dir):
    obs = _make_family_obs_db(
        tmp_dir, "observations.db",
        run=(_RUN, _DATE, 2, None),
        sources=[(_RUN, _DATE, 10, 1), (_RUN, _DATE, 20, 1)],
        pairs=[(_RUN, _DATE, 10, 20, 0.9, "same_family", 1, 1, None)],
    )
    stats = sync_tapematch_families(db_path=db_path, observations_db_path=obs)
    assert stats["errors"] == []


def test_sync_marks_a_mixed_rig_date_for_attention(app):
    db_path, conn, tmp_dir = app
    _entry(conn, 10, "Schoeps MK4 > DAT")
    _entry(conn, 20, "AKG C460 > DAT")
    conn.commit()
    _sync(db_path, tmp_dir)
    row = conn.execute("SELECT auto_triage, auto_triage_reasons FROM tapematch_family_meta "
                       "WHERE concert_date = ? AND member_count = 2", (_DATE,)).fetchone()
    assert row["auto_triage"] == "attention"
    assert RIG_RULE in json.loads(row["auto_triage_reasons"])
    # Flagged, not split: both LBs stay in one family.
    fams = {r[0] for r in conn.execute("SELECT fam_id FROM recording_families")}
    assert fams == {f"{_DATE}#10-20"}


def test_sync_leaves_a_same_rig_date_clear(app):
    db_path, conn, tmp_dir = app
    _entry(conn, 10, "Schoeps MK4 > DAT")
    _entry(conn, 20, "Schoeps MK41 > MD")
    conn.commit()
    _sync(db_path, tmp_dir)
    row = conn.execute("SELECT auto_triage, auto_triage_reasons FROM tapematch_family_meta "
                       "WHERE concert_date = ?", (_DATE,)).fetchone()
    assert row["auto_triage"] == "clear" and row["auto_triage_reasons"] == "[]"
