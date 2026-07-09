"""Tests for concert_ranker.picks: one date fixture per §4 scoring term, the
degraded no-metrics case, idempotency/dry-run, and the chained
POST /api/derived/recompute endpoint.
"""
import json
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import concert_ranker.picks as picks


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_show_picks_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, date_str, rating=None, description=""):
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, date_str, rating, description, status)"
        " VALUES (?, ?, ?, ?, 'ok')",
        (lb, date_str, rating, description),
    )
    conn.commit()


def _seed_lineage(conn, lb, better_than=None, derived_from=None):
    conn.execute(
        """INSERT OR REPLACE INTO entry_lineage
           (lb_number, mentions_lb, same_as_lb, derived_from_lb, better_than_lb,
            parse_confidence, source_text_hash)
           VALUES (?, '[]', '[]', ?, ?, 'medium', 'test')""",
        (lb, json.dumps(derived_from or []), json.dumps(better_than or [])),
    )
    conn.commit()


def _seed_curated_list(conn, name, lb_numbers):
    cur = conn.execute("INSERT INTO curated_lists(name, label) VALUES (?, ?)", (name, name))
    list_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO curated_list_entries(list_id, lb_number) VALUES (?, ?)",
        [(list_id, lb) for lb in lb_numbers],
    )
    conn.commit()


def _seed_quality(conn, lb, scan_id=1, rank_in_family=None, vetoed=0, abs_score=None):
    from concert_ranker.lb import repo as cr_repo
    cr_repo.ensure_schema(conn)  # adds abs_score/abs_grade columns (later migration)
    conn.execute(
        "INSERT OR REPLACE INTO quality_recording_scores"
        " (lb_number, scan_id, rank_in_family, vetoed, abs_score) VALUES (?, ?, ?, ?, ?)",
        (lb, scan_id, rank_in_family, vetoed, abs_score),
    )
    conn.commit()


def _seed_taper_attribution(conn, lb, taper, confidence="confirmed"):
    conn.execute(
        "INSERT OR REPLACE INTO taper_attributions"
        " (lb_number, taper_normalised, confidence, evidence_json, conflict)"
        " VALUES (?, ?, ?, '[]', 0)",
        (lb, taper, confidence),
    )
    conn.commit()


def _picks_for_date(conn, date_str):
    rows = conn.execute(
        "SELECT * FROM show_picks WHERE concert_date = ? ORDER BY pick_rank", (date_str,)
    ).fetchall()
    return [dict(r) | {"evidence": json.loads(r["evidence_json"])} for r in rows]


def _evidence_kinds(row):
    return {e["kind"] for e in row["evidence"]}


# ── Term 1: rating base ────────────────────────────────────────────────────────

def test_rating_base_highest_wins_and_unrated_neutral():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, "1975-01-01", rating="A+")
    _seed_entry(conn, 2, "1975-01-01", rating="C")
    _seed_entry(conn, 3, "1975-01-01", rating=None)

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1975-01-01")
    by_lb = {r["lb_number"]: r for r in rows}
    assert by_lb[1]["pick_rank"] == 1
    assert by_lb[1]["pick_score"] == 100.0  # A+ (rank 13) -> top of the 0-100 scale
    assert "rating" in _evidence_kinds(by_lb[1])

    # C = rank 6 -> (6-1)/12*100 = 41.67
    assert abs(by_lb[2]["pick_score"] - 41.67) < 0.1

    assert by_lb[3]["pick_score"] == picks.PICK_WEIGHTS["rating_unrated_base"]
    assert "unrated" in _evidence_kinds(by_lb[3])


# ── Term 2: curated list bonus ─────────────────────────────────────────────────

def test_curated_list_bonus():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 10, "1976-01-01", rating="B")
    _seed_entry(conn, 11, "1976-01-01", rating="B")
    _seed_curated_list(conn, "carbonbit", [10])

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1976-01-01")}
    assert rows[10]["pick_rank"] == 1
    assert "curated_list" in _evidence_kinds(rows[10])
    weight = picks.PICK_WEIGHTS["curated_list_weights"]["carbonbit"]
    assert abs(rows[10]["pick_score"] - rows[11]["pick_score"] - weight) < 0.01


# ── Term 3: supersession (better_than_lb) ──────────────────────────────────────

def test_supersession_claim_bonus_and_penalty():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 20, "1977-01-01", rating="B")
    _seed_entry(conn, 21, "1977-01-01", rating="B")
    _seed_lineage(conn, 20, better_than=[21])

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1977-01-01")}
    assert "supersession" in _evidence_kinds(rows[20])
    assert "superseded" in _evidence_kinds(rows[21])
    bonus = picks.PICK_WEIGHTS["supersession_claim_bonus"]
    penalty = picks.PICK_WEIGHTS["supersession_claim_penalty"]
    same_base_delta = rows[20]["pick_score"] - rows[21]["pick_score"]
    assert abs(same_base_delta - (bonus - penalty)) < 0.01
    assert rows[20]["pick_rank"] == 1


# ── Term 3b: derived_from ──────────────────────────────────────────────────────

def test_derived_from_penalty_and_higher_rating_override():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    # Case A: child (no override) is penalized vs parent, same rating.
    _seed_entry(conn, 30, "1978-01-01", rating="B")
    _seed_entry(conn, 31, "1978-01-01", rating="B")
    _seed_lineage(conn, 31, derived_from=[30])

    # Case B: child outrates parent -> no penalty.
    _seed_entry(conn, 40, "1979-01-01", rating="C")
    _seed_entry(conn, 41, "1979-01-01", rating="A")
    _seed_lineage(conn, 41, derived_from=[40])

    picks.recompute(db_path=db_path)

    rows_a = {r["lb_number"]: r for r in _picks_for_date(conn, "1978-01-01")}
    assert "derived_from" in _evidence_kinds(rows_a[31])
    penalty = picks.PICK_WEIGHTS["derived_from_penalty"]
    assert abs((rows_a[31]["pick_score"] - rows_a[30]["pick_score"]) - penalty) < 0.01

    rows_b = {r["lb_number"]: r for r in _picks_for_date(conn, "1979-01-01")}
    assert "derived_from" not in _evidence_kinds(rows_b[41])
    assert rows_b[41]["pick_rank"] == 1


# ── Term 4: family dedup / best-transfer / vetoed + EAC match ──────────────────

def test_family_best_transfer_inferior_and_vetoed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 50, "1980-01-01", rating="B")
    _seed_entry(conn, 51, "1980-01-01", rating="B")
    _seed_entry(conn, 52, "1980-01-01", rating="B")
    _seed_quality(conn, 50, rank_in_family=1)
    _seed_quality(conn, 51, rank_in_family=2)
    _seed_quality(conn, 52, vetoed=1)

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1980-01-01")}
    assert "best_transfer" in _evidence_kinds(rows[50])
    assert "inferior_transfer" in _evidence_kinds(rows[51])
    assert "vetoed" in _evidence_kinds(rows[52])
    assert rows[50]["pick_score"] > rows[51]["pick_score"] > rows[52]["pick_score"]
    assert rows[50]["pick_rank"] == 1


def test_eac_match_penalty():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 60, "1981-01-01", rating="B", description="Plain copy.")
    _seed_entry(conn, 61, "1981-01-01", rating="B",
                description="Close EAC match to LB-60, nothing new here.")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1981-01-01")}
    assert "eac_match" in _evidence_kinds(rows[61])
    penalty = picks.PICK_WEIGHTS["eac_match_penalty"]
    assert abs((rows[61]["pick_score"] - rows[60]["pick_score"]) - penalty) < 0.01
    assert rows[60]["pick_rank"] == 1


# ── Term 5: audio quality blend ────────────────────────────────────────────────

def test_audio_quality_blend_and_clamp():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 70, "1982-01-01", rating="B")  # base ~ (9-1)/12*100 = 66.67
    _seed_quality(conn, 70, abs_score=90.0)

    _seed_entry(conn, 80, "1983-01-01", rating="F")  # base 0
    _seed_quality(conn, 80, abs_score=100.0)  # would blend to +25, clamp to +10

    picks.recompute(db_path=db_path)

    row70 = _picks_for_date(conn, "1982-01-01")[0]
    assert "audio_quality" in _evidence_kinds(row70)
    weight = picks.PICK_WEIGHTS["audio_quality_relative_weight"]
    base70 = (9 - 1) / 12 * 100  # rating "B" -> RATING_RANK 9
    expected_delta = weight * (90.0 - base70)
    assert abs(row70["pick_score"] - (base70 + expected_delta)) < 0.5

    row80 = _picks_for_date(conn, "1983-01-01")[0]
    clamp = picks.PICK_WEIGHTS["audio_quality_clamp"]
    assert abs(row80["pick_score"] - clamp) < 0.01  # base 0 + clamped +10


# ── Term 6: taper reputation ────────────────────────────────────────────────────

def test_taper_reputation_bonus_requires_high_median_and_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    # Build a reputable taper: several confirmed entries with high ratings.
    for lb, rating in ((900, "A+"), (901, "A"), (902, "A-")):
        _seed_entry(conn, lb, f"1990-01-{lb - 899:02d}", rating=rating)
        _seed_taper_attribution(conn, lb, "reputable_taper", confidence="confirmed")

    # Candidate date: one entry attributed (confirmed) to the reputable taper,
    # one plain entry with the same rating.
    _seed_entry(conn, 910, "1991-01-01", rating="B")
    _seed_entry(conn, 911, "1991-01-01", rating="B")
    _seed_taper_attribution(conn, 910, "reputable_taper", confidence="confirmed")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1991-01-01")}
    assert "taper_reputation" in _evidence_kinds(rows[910])
    assert "taper_reputation" not in _evidence_kinds(rows[911])
    bonus = picks.PICK_WEIGHTS["taper_reputation_bonus"]
    assert abs((rows[910]["pick_score"] - rows[911]["pick_score"]) - bonus) < 0.01


def test_taper_reputation_skipped_when_table_missing_data():
    """Feature-detection: an empty taper_attributions table contributes nothing
    (no crash), matching a fresh install before TAPER phase 1 has run."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 920, "1992-01-01", rating="B")

    stats = picks.recompute(db_path=db_path)
    assert stats["total"] == 1


# ── Degraded case (spec §7 phase 2) ────────────────────────────────────────────

def test_degraded_single_candidate_no_metrics():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 999, "1993-01-01", rating=None)

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1993-01-01")
    assert len(rows) == 1
    assert rows[0]["pick_rank"] == 1
    kinds = _evidence_kinds(rows[0])
    assert "unrated" in kinds
    assert "solo" in kinds


# ── Tie-breaking ─────────────────────────────────────────────────────────────

def test_tie_breaks_toward_lower_lb_number():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1002, "1994-01-01", rating="B")
    _seed_entry(conn, 1001, "1994-01-01", rating="B")

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1994-01-01")
    assert rows[0]["lb_number"] == 1001
    assert rows[0]["pick_rank"] == 1
    assert rows[1]["lb_number"] == 1002
    assert rows[1]["pick_rank"] == 2


# ── Idempotency / dry-run (spec §8) ────────────────────────────────────────────

def test_idempotent_rerun():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1100, "1995-01-01", rating="A")
    _seed_entry(conn, 1101, "1995-01-01", rating="C")
    _seed_curated_list(conn, "10haaf", [1101])

    stats1 = picks.recompute(db_path=db_path)
    rows1 = {r["lb_number"]: (r["pick_score"], r["pick_rank"], r["evidence_json"])
             for r in conn.execute("SELECT * FROM show_picks")}

    stats2 = picks.recompute(db_path=db_path)
    rows2 = {r["lb_number"]: (r["pick_score"], r["pick_rank"], r["evidence_json"])
             for r in conn.execute("SELECT * FROM show_picks")}

    assert rows1 == rows2
    assert stats1 == stats2


def test_dry_run_does_not_write():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1200, "1996-01-01", rating="A")

    stats = picks.recompute(db_path=db_path, dry_run=True)

    assert stats["total"] == 1
    count = conn.execute("SELECT COUNT(*) FROM show_picks").fetchone()[0]
    assert count == 0


# ── POST /api/derived/recompute (F1 chained endpoint) ──────────────────────────

def test_derived_recompute_endpoint_event_sequence():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 5000, "1997-01-01", rating="A",
                description="Taper: Spot\nSource: Schoeps > DAT > FLAC")
    db.set_curator(False, db_path)

    orig_db_path = _paths.DB_PATH
    orig_module_db_path = getattr(db, "DB_PATH", None)
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    _paths.DB_PATH = db_path
    db.DB_PATH = db_path
    try:
        from backend.app import create_app
        app = create_app()
        client = app.test_client()

        response = client.post("/api/derived/recompute")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
    finally:
        _paths.DB_PATH = orig_db_path
        if orig_module_db_path is not None:
            db.DB_PATH = orig_module_db_path

    events = [
        json.loads(line[len("data: "):])
        for line in body.split("\n\n") if line.startswith("data: ")
    ]
    steps_seen = [(e["event"], e.get("step")) for e in events]

    assert ("start", "parse_lineage") in steps_seen
    assert ("done", "parse_lineage") in steps_seen
    assert ("start", "attribute_tapers") in steps_seen
    assert ("done", "attribute_tapers") in steps_seen
    assert ("start", "compute_show_picks") in steps_seen
    assert ("done", "compute_show_picks") in steps_seen
    assert events[-1]["event"] == "chain_done"
    # No error/skipped events — all three modules exist in this repo.
    assert not any(e["event"] in ("error", "skipped") for e in events)

    picks_done = next(
        e for e in events if e["event"] == "done" and e.get("step") == "compute_show_picks"
    )
    assert picks_done["stats"]["total"] == 1

    shutil.rmtree(tmp_dir, ignore_errors=True)
