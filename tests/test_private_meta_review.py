"""Tests for tools/private_meta_review.py."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import private_meta_review as pmr  # noqa: E402


def test_olof_location_formats() -> None:
    assert pmr.olof_location("Sheffield", "", "England") == "Sheffield, England"
    assert pmr.olof_location("Dallas", "Texas", "") == "Dallas, Texas"
    assert pmr.olof_location("", "Texas", "") == ""


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE entries (lb_number INTEGER, date_str TEXT, location TEXT, status TEXT)")
    c.executemany("INSERT INTO entries VALUES (?,?,?,?)",
                  [(1, "9/22/00", "", "private"), (2, "1/1/01", "Moved, Already", "private")])
    c.commit()
    c.close()
    return db


def test_apply_dry_run_then_write(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path)
    monkeypatch.setattr(pmr, "DB_PATH", db)
    monkeypatch.setattr(pmr, "BACKUP_DIR", tmp_path / "bk")
    dec = tmp_path / "d.json"
    dec.write_text(json.dumps({"decisions": [
        {"lb": 1, "date_str": "9/22/00", "location": "Sheffield, England",
         "before": {"date_str": "9/22/00", "location": ""}},
        {"lb": 2, "date_str": "1/1/01", "location": "X, Y",
         "before": {"date_str": "1/1/01", "location": ""}},   # stale: changed since build
    ]}))
    assert pmr.apply(dec, write=False) == 0
    q = "SELECT location FROM entries WHERE lb_number=?"
    assert sqlite3.connect(db).execute(q, (1,)).fetchone()[0] == ""
    assert pmr.apply(dec, write=True) == 0
    conn = sqlite3.connect(db)
    assert conn.execute(q, (1,)).fetchone()[0] == "Sheffield, England"
    assert conn.execute(q, (2,)).fetchone()[0] == "Moved, Already"
    assert len(list((tmp_path / "bk").glob("pre_private_meta_*.db"))) == 1
