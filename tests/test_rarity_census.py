"""Tests for tools/tapematch/rarity_census.py (TODO-335)."""
import json
import sqlite3
import sys
from pathlib import Path

import backend.db as db

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "tapematch"))
import rarity_census as rc  # noqa: E402


def _obs(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, concert_date TEXT, run_at TEXT,"
        " n_sources_ran INTEGER);"
        "CREATE TABLE sources (id INTEGER PRIMARY KEY, run_id TEXT, concert_date TEXT,"
        " lb_number INTEGER, family_id INTEGER, dominant_ext TEXT);"
    )
    conn.executemany("INSERT INTO runs VALUES (?,?,?,?)", [
        ("old", "1978-07-08", "2026-06-01", 3),
        ("new", "1978-07-08", "2026-07-01", 3),
        ("r66", "1966-05-01", "2026-07-01", 2),
    ])
    conn.executemany(
        "INSERT INTO sources (run_id, concert_date, lb_number, family_id, dominant_ext)"
        " VALUES (?,?,?,?,?)", [
            # superseded run: all three distinct — must be ignored
            ("old", "1978-07-08", 1, 1, ".flac"), ("old", "1978-07-08", 2, 2, ".flac"),
            ("old", "1978-07-08", 3, 3, ".shn"),
            ("new", "1978-07-08", 1, 1, ".flac"), ("new", "1978-07-08", 2, 1, ".flac"),
            ("new", "1978-07-08", 3, 2, ".shn"),
            ("r66", "1966-05-01", 6, 1, ".flac"), ("r66", "1966-05-01", 7, 1, ".flac"),
        ])
    conn.commit()
    conn.close()


def _app(path):
    db.init_db(str(path))
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO entries (lb_number, date_str, lb_category) VALUES (?,?,?)", [
            (1, "7/8/78", "concert"), (2, "7/8/78", "concert"), (3, "7/8/78", "concert"),
            (6, "5/1/66", "concert"), (7, "5/1/66", "concert"),
        ])
    conn.executemany(
        "INSERT INTO recording_families (lb_number, fam_id, concert_date) VALUES (?,?,?)", [
            (1, "1978-07-08#1", "1978-07-08"), (2, "1978-07-08#1", "1978-07-08"),
            (3, "1978-07-08#2", "1978-07-08"),
            (6, "1966-05-01#1", "1966-05-01"), (7, "1966-05-01#1", "1966-05-01"),
        ])
    conn.execute(
        "INSERT INTO olof_events (event_id, page_filename, event_type, date_str, tour_name) "
        "VALUES (1, 'p.htm', 'concert', '1978-07-08', '1978 World Tour: Europe')")
    conn.commit()
    conn.close()


def _gap(path, private_on=None):
    dates = [{"date": "1978-07-08", "present": [], "private": [], "absent": [],
              "unranked": []}]
    if private_on:
        dates[0]["private"] = [{"lb": 9, "category": "concert", "path": ""}]
    path.write_text(json.dumps({"generated_at": "2026-09-03", "dates": dates}))


def test_census_latest_run_and_singletons(tmp_path):
    _obs(tmp_path / "obs.db")
    _app(tmp_path / "app.db")
    _gap(tmp_path / "gap.json")
    c = rc.build_census(tmp_path / "obs.db", tmp_path / "app.db", tmp_path / "gap.json")
    # latest run per date only: {1,2} + {3} on 1978, {6,7} on 1966
    assert c["obs"]["distribution"] == {1: 1, 2: 2}
    assert c["app"]["families"] == 3 and c["app"]["sources"] == 5
    assert [s["lb"] for s in c["singletons"]] == [3]
    assert c["singletons"][0]["ext"] == ".shn"
    assert rc.classify_singleton(c["singletons"][0]) == "complete"
    # 1966: two recordings, one tape
    assert c["collapsed_dates"] == ["1966-05-01"]


def test_singleton_with_private_sibling_is_not_complete(tmp_path):
    _obs(tmp_path / "obs.db")
    _app(tmp_path / "app.db")
    _gap(tmp_path / "gap.json", private_on=True)
    c = rc.build_census(tmp_path / "obs.db", tmp_path / "app.db", tmp_path / "gap.json")
    assert rc.classify_singleton(c["singletons"][0]) == "private"


def test_main_writes_md_and_json(tmp_path):
    _obs(tmp_path / "obs.db")
    _app(tmp_path / "app.db")
    md, js = tmp_path / "out.md", tmp_path / "out.json"
    rc.main(["--obs", str(tmp_path / "obs.db"), "--db", str(tmp_path / "app.db"),
             "--gap-list", str(tmp_path / "missing.json"), "--md", str(md),
             "--json", str(js)])
    text = md.read_text()
    assert "LB-00003" in text and "1978 World Tour: Europe" not in text  # < 20 families
    assert "(missing)" in text
    assert json.loads(js.read_text())["singletons"][0]["lb"] == 3
