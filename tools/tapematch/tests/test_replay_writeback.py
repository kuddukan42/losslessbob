"""Tests for replay_writeback.py (TODO-333 follow-up).

Builds a temp observations.db through the real schema + migration path
(``tapematch_session.open_obs_db``) and replays a threshold-only config change —
``match.fingerprint_primary_floor`` — against stored pair rows.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import replay_writeback as rw  # noqa: E402
import tapematch_session as ts  # noqa: E402
from tapematch.calibration import calibration_hash  # noqa: E402

from backend.tapematch_sync import _pick_best_run  # noqa: E402

DATE = "2008-07-08"
SRC = "20260715_052612"


def _cfg(floor=None, **top):
    match = {"cluster_threshold": 0.45}
    if floor is not None:
        match["fingerprint_primary_floor"] = floor
    cfg = {
        "match": match,
        "secondary_match": {"coverage_threshold": 0.35,
                            "hiss_merge_frac": 0.60, "hiss_merge_median": 0.65},
        "fingerprint": {"cluster_threshold": 0.50,
                        "cluster_threshold_staircase": 0.40,
                        "cluster_threshold_curator": 0.43,
                        "staircase_corroboration": {"enabled": False}},
    }
    cfg.update(top)
    return cfg


ERA = _cfg()
SHIPPED = _cfg(floor=0.05)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Temp obs DB (real schema, pre-replayed_from) + shipped config file."""
    monkeypatch.setattr(ts, "OBS_DB_PATH", tmp_path / "observations.db")
    monkeypatch.setattr(rw, "RUNS_DIR", tmp_path / "runs")
    conn = ts.open_obs_db()
    # Simulate a DB from before the replayed_from migration.
    conn.execute("ALTER TABLE runs DROP COLUMN replayed_from")
    conn.commit()
    conn.close()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(SHIPPED))
    return {"db": tmp_path / "observations.db", "cfg": cfg_path,
            "lb": tmp_path / "no_lb.db"}


def _pair(a, b, verdict, fam_a, fam_b, run_id=SRC, date=DATE, **kw):
    p = {"run_id": run_id, "concert_date": date, "lb_a": a, "lb_b": b,
         "corr": 0.02, "windowed_frac": 0.0, "hiss_frac": 0.0, "hiss_median": 0.0,
         "fp_score": None, "tapematch_verdict": verdict,
         "family_id_a": fam_a, "family_id_b": fam_b, "run_at": "2026-07-15T05:26:12",
         "human_notes": f"note {a}-{b}"}
    p.update(kw)
    return p


def _seed(db: Path, *, cfg=ERA, fp12=0.60, stored12="same_family",
          run_id=SRC, date=DATE, n_ran=3) -> None:
    """One run: LB 1+2 linked by fingerprint alone (fam 1), LB 3 alone (fam 2)."""
    conn = sqlite3.connect(db)
    ts.insert_run(conn, run_id, date, "Somewhere", 3, 3, n_ran, 2, json.dumps(cfg),
                  f"/nonexistent/{run_id}_{date}", "2026-07-15T05:26:12", 100.0,
                  calibration_hash(cfg))
    for lb, fam in ((1, 1), (2, 1), (3, 2)):
        conn.execute("INSERT INTO sources (run_id, concert_date, lb_number, folder_name, "
                     "family_id, speed_kind) VALUES (?,?,?,?,?,?)",
                     (run_id, date, lb, f"lb{lb}", fam, "aligned"))
    for p in (_pair(1, 2, stored12, 1, 1, run_id, date, fp_score=fp12),
              _pair(1, 3, "different_family", 1, 2, run_id, date),
              _pair(2, 3, "different_family", 1, 2, run_id, date)):
        cols = list(p)
        conn.execute(f"INSERT INTO pairs ({','.join(cols)}) VALUES "
                     f"({','.join('?' * len(cols))})", [p[c] for c in cols])
    conn.commit()
    conn.close()


def _run(env, apply, **kw):
    return rw.run(env["db"], env["lb"], env["cfg"], apply, **kw)


def _conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def test_eligible_date_is_written(env):
    _seed(env["db"])
    (r,) = _run(env, apply=True)
    assert r.status == "written" and r.pairs_changed == 1
    assert (r.families_before, r.families_after) == (2, 3)

    c = _conn(env["db"])
    new_id = rw.replay_run_id(SRC, calibration_hash(SHIPPED))
    assert _pick_best_run(c)[DATE] == new_id
    run = dict(c.execute("SELECT * FROM runs WHERE run_id = ?", (new_id,)).fetchone())
    assert run["replayed_from"] == SRC
    assert run["calibration_hash"] == calibration_hash(SHIPPED)
    assert json.loads(run["config_json"]) == SHIPPED
    assert run["n_families"] == 3 and run["duration_sec"] is None
    assert run["archive_dir"] == f"/nonexistent/{SRC}_{DATE}"
    assert run["n_sources_ran"] == 3 and run["location"] == "Somewhere"

    fams = dict(c.execute("SELECT lb_number, family_id FROM sources WHERE run_id = ?",
                          (new_id,)).fetchall())
    # {3} kept its id; the split pair got max+1.. in lb order.
    assert fams == {1: 3, 2: 4, 3: 2}
    pairs = {(p["lb_a"], p["lb_b"]): dict(p) for p in
             c.execute("SELECT * FROM pairs WHERE run_id = ?", (new_id,))}
    assert len(pairs) == 3
    assert {k: p["tapematch_verdict"] for k, p in pairs.items()} == {
        (1, 2): "different_family", (1, 3): "different_family",
        (2, 3): "different_family"}
    assert (pairs[(1, 2)]["family_id_a"], pairs[(1, 2)]["family_id_b"]) == (3, 4)
    assert pairs[(1, 2)]["fp_score"] == 0.60 and pairs[(1, 2)]["human_notes"] == "note 1-2"
    assert pairs[(1, 2)]["run_at"] == run["run_at"]
    # Source run untouched.
    assert c.execute("SELECT COUNT(*) FROM pairs WHERE run_id = ?", (SRC,)).fetchone()[0] == 3
    assert c.execute("SELECT tapematch_verdict FROM pairs WHERE run_id = ? AND lb_b = 2",
                     (SRC,)).fetchone()[0] == "same_family"


def test_stale_archive_dir_resolves_against_source_id(env, tmp_path):
    # Stored path is stale; the <source run_id>_<date> dir exists. The replay
    # must carry that dir, since sync's fallback would build it from the
    # replay id and miss analysis.md.
    (tmp_path / "runs" / f"{SRC}_{DATE}").mkdir(parents=True)
    _seed(env["db"])
    (r,) = _run(env, apply=True)
    c = _conn(env["db"])
    got = c.execute("SELECT archive_dir FROM runs WHERE run_id = ?", (r.new_run_id,)).fetchone()
    assert got[0] == str(tmp_path / "runs" / f"{SRC}_{DATE}")


def test_no_verdict_change_is_skipped(env):
    # fp link with corr above the floor survives the floor: nothing moves.
    _seed(env["db"])
    c = sqlite3.connect(env["db"])
    c.execute("UPDATE pairs SET corr = 0.10 WHERE lb_a = 1 AND lb_b = 2")
    c.commit()
    c.close()
    (r,) = _run(env, apply=True)
    assert (r.status, r.reason) == ("skipped", "no_change")


def test_signal_key_difference_is_not_replayable(env):
    _seed(env["db"], cfg=_cfg(polarity={"enabled": True}))
    (r,) = _run(env, apply=True)
    assert (r.status, r.reason) == ("skipped", "signal_keys_differ")


def test_current_calibration_is_skipped(env):
    _seed(env["db"], cfg=SHIPPED)
    (r,) = _run(env, apply=True)
    assert r.reason == "current_calibration"


def test_fidelity_gate_skips_unreproducible_run(env):
    # Stored says different, but the era config links 1-2 via fingerprint.
    _seed(env["db"], stored12="different_family")
    (r,) = _run(env, apply=True)
    assert (r.status, r.reason) == ("skipped", "fidelity_mismatch")
    c = _conn(env["db"])
    assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_fidelity_gate_checks_partition(env):
    # Verdicts reproduce, but stored family_id puts LB 3 with LB 1+2.
    _seed(env["db"])
    c = sqlite3.connect(env["db"])
    c.execute("UPDATE sources SET family_id = 1 WHERE lb_number = 3")
    c.commit()
    c.close()
    (r,) = _run(env, apply=True)
    assert r.reason == "fidelity_mismatch"


def test_idempotent(env):
    _seed(env["db"])
    _run(env, apply=True)
    results = _run(env, apply=True)
    # The best run is now the replay itself, on the shipped calibration.
    assert [r.reason for r in results] == ["current_calibration"]
    c = _conn(env["db"])
    assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    # Even when the source is forced back to best, the existing replay blocks a rewrite.
    c.execute("UPDATE runs SET n_sources_ran = 99 WHERE run_id = ?", (SRC,))
    c.commit()
    (r,) = _run(env, apply=True)
    assert r.reason == "already_replayed"
    assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2


def test_dry_run_writes_nothing(env):
    _seed(env["db"])
    (r,) = _run(env, apply=False)
    assert r.status == "written"  # would be written
    c = _conn(env["db"])
    assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM pairs").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3
    cols = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
    assert "replayed_from" not in cols


def test_dates_filter_and_limit(env):
    _seed(env["db"])
    _seed(env["db"], run_id="20260716_000000", date="2009-01-01")
    assert [r.concert_date for r in _run(env, apply=False, dates={"2009-01-01"})] == [
        "2009-01-01"]
    assert len(_run(env, apply=False, limit=1)) == 1


def test_replay_id_sorts_between_source_and_next_real_run():
    rid = rw.replay_run_id(SRC, "f786bebf58c8")
    assert SRC < rid < "20260715_052613"
    assert rid.split("_", 2)[:2] == ["20260715", "052612-rf786bebf58c8"]


def test_best_run_choice_follows_sync_not_latest(env):
    # A later partial run (fewer sources) must not displace the source as the
    # replay base, and the replay then beats both.
    _seed(env["db"])
    _seed(env["db"], run_id="20260801_000000", n_ran=2)
    (r,) = _run(env, apply=True)
    assert r.source_run == SRC and r.status == "written"
    assert _pick_best_run(_conn(env["db"]))[DATE] == r.new_run_id


def test_assign_family_ids_keeps_unchanged_ids():
    old = {1: 5, 2: 5, 3: 7, 4: 9, 5: 9}
    new = {frozenset({1}), frozenset({2}), frozenset({3}), frozenset({4, 5})}
    assert rw.assign_family_ids(old, new) == {1: 10, 2: 11, 3: 7, 4: 9, 5: 9}


def test_open_obs_db_adds_replayed_from(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "OBS_DB_PATH", tmp_path / "o.db")
    ts.open_obs_db().close()
    conn = ts.open_obs_db()
    assert "replayed_from" in {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    conn.close()
