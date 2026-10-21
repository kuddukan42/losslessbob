"""tools/tuit_reconcile.py — TUIT vs entries reconciliation (TODO-332/339) on a fixture DB."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tuit_reconcile as tr  # noqa: E402

_SCHEMA = """
CREATE TABLE tuit_recordings (rec_id INTEGER PRIMARY KEY, lb_number INTEGER, title TEXT,
    date_str TEXT, venue TEXT, location TEXT, source_type TEXT, lineage TEXT,
    info_text TEXT, setlist_json TEXT, uploader TEXT);
CREATE TABLE entries (lb_number INTEGER PRIMARY KEY, date_str TEXT, location TEXT,
    description TEXT, setlist TEXT, source_chain TEXT, source_type TEXT);
CREATE TABLE lb_master (lb_number INTEGER PRIMARY KEY, lb_status TEXT);
CREATE TABLE corrections (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_kind TEXT NOT NULL,
    entity_key TEXT NOT NULL, field TEXT NOT NULL, original TEXT, corrected TEXT,
    reason TEXT, decided_by TEXT, decided_at TEXT);
CREATE TABLE olof_events (event_id INTEGER PRIMARY KEY, date_str TEXT, venue TEXT, city TEXT);
CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, song_title TEXT);
"""

_SL = json.dumps([{"track": "1", "song": "Maggie's Farm"}, {"track": "2", "song": "Jokerman"}])


def _rec(rec_id, lb, date, venue="Civic Center", location="Providence, RI, United States",
         src="AUD", lineage="", setlist=_SL, title=""):
    return (rec_id, lb, title, date, venue, location, src, lineage, "", setlist, "u")


def _entry(lb, date, location="Providence, RI", setlist="", chain="", src="Audience",
           desc=""):
    return (lb, date, location, desc, setlist, chain, src)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "fx.db"
    c = sqlite3.connect(path)
    c.executescript(_SCHEMA)
    recs = [
        _rec(1, 100, "1978-10-07", lineage="aud > cass > flac"),        # all fills
        _rec(2, 101, "1978-10-08", venue="Garden"),                     # LB names it
        _rec(3, 102, "1994-05-22", venue="Todaiji Temple", location="Nara, Japan"),
        _rec(4, 103, "1961-11-04", title="Early Recordings Vol. III"),  # compilation
        _rec(5, 104, "2013-06-30"),                                     # year mismatch
        _rec(6, 105, "1993-09-19", venue="Walnut Creek"),               # date conflict
        _rec(7, 106, "1999-01-01", src="AUD"),                          # LB Soundboard
        _rec(8, 107, "1999-01-02", src="SBD", lineage="dpa 4061 mics > d8"),
        _rec(9, 108, "1999-01-03", src="AUD"),                          # two recs, two values
        _rec(10, 108, "1999-01-03", src="SBD"),
        _rec(11, 109, "1999-01-04", src="SBD"),                         # existing correction
    ]
    c.executemany("INSERT INTO tuit_recordings VALUES (?,?,?,?,?,?,?,?,?,?,?)", recs)
    ents = [
        _entry(100, "10/7/78", src=""),
        _entry(101, "10/8/78", location="Boston Garden, Boston MA", setlist="1. A",
               chain="x"),
        _entry(102, "5/xx/94", location="Todaiji Temple, Nara", setlist="1. A", chain="x"),
        _entry(103, "xx/xx/61", location="Early Recordings Vol. III", setlist="1. A",
               chain="x"),
        _entry(104, "5/xx/61", location="Minnesota", setlist="1. A", chain="x"),
        _entry(105, "10/9/93", location="Shoreline", setlist="1. Jokerman 2. Senor",
               chain="x"),
        _entry(106, "1/1/99", src="Soundboard", chain="mics at the soundboard > dat",
               setlist="1. A"),
        _entry(107, "1/2/99", setlist="1. A", chain="x"),
        _entry(108, "1/3/99", src="", setlist="1. A", chain="x"),
        _entry(109, "1/4/99", src="", setlist="1. A", chain="x"),
    ]
    c.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?)", ents)
    c.executemany("INSERT INTO lb_master VALUES (?, 'public')", [(e[0],) for e in ents])
    c.executemany("INSERT INTO olof_events VALUES (?,?,?,?)",
                  [(1, "1993-10-09", "Shoreline Amphitheatre", "Mountain View"),
                   (2, "1993-09-19", "Walnut Creek", "Raleigh")])
    c.executemany("INSERT INTO olof_songs VALUES (?,?,?)",
                  [(1, 1, "Jokerman"), (1, 2, "Senor (Tales Of Yankee Power)"),
                   (2, 1, "Jokerman")])
    c.execute("INSERT INTO corrections (entity_kind, entity_key, field, corrected, decided_by)"
              " VALUES ('entry', '109', 'source_type', 'Audience', 'tj')")
    c.commit()
    c.close()
    return path


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def test_lb_date_parts():
    assert tr.lb_date_parts("6/3/78") == (1978, 6, 3)
    assert tr.lb_date_parts("5/xx/94") == (1994, 5, None)
    assert tr.lb_date_parts("xx/xx/61") == (1961, None, None)
    assert tr.lb_date_parts("4/17/17") == (2017, 4, 17)
    assert tr.lb_date_parts("") is None and tr.lb_date_parts("1978") is None


def test_classify_venue():
    assert tr.classify_venue("Civic Center", "Providence, RI", "Providence, RI") == "city_only"
    assert tr.classify_venue("Boston Garden", "Boston, MA", "Boston Garden, Boston") == "agree"
    assert tr.classify_venue("Fox Theatre", "Atlanta, GA", "Atlanta, Omni") == "differs"
    assert tr.classify_venue("X", "", "") == "lb_blank"


def test_lb_setlist_parse():
    assert tr.lb_setlist("1. A Song 2 B Song, 3 C") == ["A Song", "B Song", "C"]


def test_dates_classified(db):
    res = tr.compute(_ro(db))
    s = res["stats"]
    assert s["date_agree"] == 7 and s["date_conflict"] == 1
    assert s["date_circa_refine"] == 2 and s["date_circa_mismatch"] == 1
    circa = {r["lb_number"]: r["class"] for r in res["circa"]}
    assert circa == {102: "single_show", 103: "compilation", 104: "misattribution"}
    (dc,) = res["date_conflicts"]
    assert dc["lb_number"] == 105 and dc["class"] == "tuit_lb_wrong"
    assert dc["setlist_fit_lb"] == "2/2" and dc["setlist_fit_tuit"] == "1/2"


def test_source_conflicts(db):
    res = tr.compute(_ro(db))
    by_lb = {r["lb_number"]: r for r in res["source_conflicts"]}
    assert by_lb[106]["class"] == "lb_aud_at_sbd" and by_lb[106]["target"] == "Audience"
    assert by_lb[107]["class"] == "tuit_wrong"
    assert res["stats"]["source_tuit_fill"] == 4  # 100, 108 x2, 109
    assert {r["lb_number"] for r in res["source_fills"]} == {100, 108, 109}


def test_fill_plan_is_additive_and_date_gated(db):
    fills = {(f["lb_number"], f["field"]) for f in tr.compute(_ro(db))["fills"]}
    assert (100, "source_type") in fills and (100, "venue") in fills
    assert (100, "source_chain") in fills and (100, "setlist") in fills
    assert (101, "venue") not in fills                      # LB already names a venue
    assert not any(lb in (102, 103, 104, 105) for lb, _ in fills)  # date not agreed
    assert (108, "source_type") not in fills                # two TUIT values — ambiguous
    assert (106, "source_type") not in fills                # never overwrites a value


def test_apply_dry_run_writes_nothing(db, tmp_path):
    audit = tmp_path / "audit.jsonl"
    assert tr.main(["--db", str(db), "--fill", "--audit", str(audit)]) == 0
    c = sqlite3.connect(db)
    assert c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == 1
    assert not audit.exists() and not (db.parent / "backups").exists()


def test_apply_writes_corrections_backup_audit_and_reverts(db, tmp_path):
    audit = tmp_path / "audit.jsonl"
    tr.main(["--db", str(db), "--fill", "--apply", "--audit", str(audit)])
    c = sqlite3.connect(db)
    rows = c.execute("SELECT entity_key, field, original, corrected FROM corrections"
                     " WHERE decided_by='tuit_reconcile' ORDER BY entity_key, field").fetchall()
    assert ("100", "source_type", "", "Audience") in rows
    assert ("100", "setlist", "", "1. Maggie's Farm 2. Jokerman") in rows
    assert not any(r[0] == "109" and r[1] == "source_type" for r in rows)  # curated kept
    assert c.execute("SELECT source_type FROM entries WHERE lb_number=100").fetchone()[0] == ""
    assert len(audit.read_text().splitlines()) == len(rows)
    assert list((db.parent / "backups").glob("*_pre_tuit_reconcile_*.db"))
    # idempotent: a second apply writes nothing new
    tr.main(["--db", str(db), "--fill", "--apply", "--audit", str(audit)])
    assert c.execute("SELECT COUNT(*) FROM corrections WHERE decided_by='tuit_reconcile'"
                     ).fetchone()[0] == len(rows)
    tr.main(["--db", str(db), "--revert", "--apply", "--audit", str(audit)])
    assert c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == 1  # tj's row stays


def test_fields_filter(db):
    c = sqlite3.connect(db)
    plan = [f for f in tr.compute(c)["fills"] if f["field"] == "venue"]
    counts = tr.apply_fills(c, plan, apply=True)
    assert counts["written"] == len(plan)
    assert {r[0] for r in c.execute("SELECT DISTINCT field FROM corrections"
                                    " WHERE decided_by='tuit_reconcile'")} == {"venue"}


def test_report_renders(db, tmp_path):
    out = tmp_path / "r.md"
    assert tr.main(["--db", str(db), "--out", str(out)]) == 0
    md = out.read_text()
    assert "### Full-date conflicts" in md and "| 105 |" in md
    assert "Circa-date refinements" in md and "compilation" in md
