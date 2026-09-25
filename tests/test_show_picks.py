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
    _seed_entry(conn, 1, "1/1/75", rating="A+")
    _seed_entry(conn, 2, "1/1/75", rating="C")
    _seed_entry(conn, 3, "1/1/75", rating=None)

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1/1/75")
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
    _seed_entry(conn, 10, "1/1/76", rating="B")
    _seed_entry(conn, 11, "1/1/76", rating="B")
    _seed_curated_list(conn, "carbonbit", [10])

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/76")}
    assert rows[10]["pick_rank"] == 1
    assert "curated_list" in _evidence_kinds(rows[10])
    weight = picks.PICK_WEIGHTS["curated_list_weights"]["carbonbit"]
    assert abs(rows[10]["pick_score"] - rows[11]["pick_score"] - weight) < 0.01


# ── Term 3: supersession (better_than_lb) ──────────────────────────────────────

def test_supersession_claim_bonus_and_penalty():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 20, "1/1/77", rating="B")
    _seed_entry(conn, 21, "1/1/77", rating="B")
    _seed_lineage(conn, 20, better_than=[21])

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/77")}
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
    _seed_entry(conn, 30, "1/1/78", rating="B")
    _seed_entry(conn, 31, "1/1/78", rating="B")
    _seed_lineage(conn, 31, derived_from=[30])

    # Case B: child outrates parent -> no penalty.
    _seed_entry(conn, 40, "1/1/79", rating="C")
    _seed_entry(conn, 41, "1/1/79", rating="A")
    _seed_lineage(conn, 41, derived_from=[40])

    picks.recompute(db_path=db_path)

    rows_a = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/78")}
    assert "derived_from" in _evidence_kinds(rows_a[31])
    penalty = picks.PICK_WEIGHTS["derived_from_penalty"]
    assert abs((rows_a[31]["pick_score"] - rows_a[30]["pick_score"]) - penalty) < 0.01

    rows_b = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/79")}
    assert "derived_from" not in _evidence_kinds(rows_b[41])
    assert rows_b[41]["pick_rank"] == 1


# ── Term 4: family dedup / best-transfer / vetoed + EAC match ──────────────────

def test_family_best_transfer_inferior_and_vetoed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 50, "1/1/80", rating="B")
    _seed_entry(conn, 51, "1/1/80", rating="B")
    _seed_entry(conn, 52, "1/1/80", rating="B")
    _seed_quality(conn, 50, rank_in_family=1)
    _seed_quality(conn, 51, rank_in_family=2)
    _seed_quality(conn, 52, vetoed=1)

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/80")}
    assert "best_transfer" in _evidence_kinds(rows[50])
    assert "inferior_transfer" in _evidence_kinds(rows[51])
    assert "vetoed" in _evidence_kinds(rows[52])
    assert rows[50]["pick_score"] > rows[51]["pick_score"] > rows[52]["pick_score"]
    assert rows[50]["pick_rank"] == 1


def test_eac_match_penalty():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 60, "1/1/81", rating="B", description="Plain copy.")
    _seed_entry(conn, 61, "1/1/81", rating="B",
                description="Close EAC match to LB-60, nothing new here.")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/81")}
    assert "eac_match" in _evidence_kinds(rows[61])
    penalty = picks.PICK_WEIGHTS["eac_match_penalty"]
    assert abs((rows[61]["pick_score"] - rows[60]["pick_score"]) - penalty) < 0.01
    assert rows[60]["pick_rank"] == 1


# ── Term 5: audio quality blend ────────────────────────────────────────────────

def test_audio_quality_absolute_vs_corpus_median_and_clamp():
    """C32 D4a: 0.25 * (scan - corpus median scan), clamped +/-10."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 70, "1/1/82", rating="B")  # base ~ (9-1)/12*100 = 66.67
    _seed_quality(conn, 70, abs_score=90.0)
    _seed_entry(conn, 80, "1/1/83", rating="F")  # base 0
    _seed_quality(conn, 80, abs_score=100.0)
    _seed_entry(conn, 90, "1/1/84", rating="F")  # base 0
    _seed_quality(conn, 90, abs_score=20.0)  # 0.25 * (20 - 90) = -17.5 -> clamp -10

    picks.recompute(db_path=db_path)

    weight = picks.PICK_WEIGHTS["audio_quality_relative_weight"]
    clamp = picks.PICK_WEIGHTS["audio_quality_clamp"]
    corpus_median = 90.0  # median of 90, 100, 20
    row70 = _picks_for_date(conn, "1/1/82")[0]
    assert "audio_quality" in _evidence_kinds(row70)
    base70 = (9 - 1) / 12 * 100  # rating "B" -> RATING_RANK 9
    assert abs(row70["pick_score"] - (base70 + weight * (90.0 - corpus_median))) < 0.01

    row80 = _picks_for_date(conn, "1/1/83")[0]
    assert abs(row80["pick_score"] - weight * (100.0 - corpus_median)) < 0.01  # +2.5

    row90 = _picks_for_date(conn, "1/1/84")[0]
    assert abs(row90["pick_score"] + clamp) < 0.01  # base 0 + clamped -10


def test_vetoed_source_gets_no_audio_term_and_never_ranks_first():
    """C32 D4e/D2: no audio term for a vetoed source; it ranks below unvetoed ones."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 95, "2/2/82", rating="A+")
    _seed_quality(conn, 95, vetoed=1, abs_score=99.0)
    _seed_entry(conn, 96, "2/2/82", rating="D")
    _seed_quality(conn, 96, abs_score=10.0)

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "2/2/82")}
    assert "audio_quality" not in _evidence_kinds(rows[95])
    assert "vetoed" in _evidence_kinds(rows[95])
    assert rows[96]["pick_rank"] == 1


def test_lossy_lineage_is_vetoed():
    """C32 D1: a stream capture stated in the lineage is vetoed; "no mp3" is not."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 97, "3/3/82", rating="A",
                description="SOURCE: Streaming Audio 320kbps > Soundforge > FLAC")
    _seed_entry(conn, 98, "3/3/82", rating="B",
                description="DAT master > WAV > FLAC. No buy, no sell, no mp3.")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "3/3/82")}
    ev97 = json.loads(rows[97]["evidence_json"])
    assert any(e["kind"] == "vetoed" and "lineage" in e["detail"] for e in ev97)
    assert "vetoed" not in _evidence_kinds(rows[98])
    assert rows[98]["pick_rank"] == 1


def test_unrated_baseline_label():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 99, "4/4/82")

    picks.recompute(db_path=db_path)

    ev = json.loads(_picks_for_date(conn, "4/4/82")[0]["evidence_json"])
    assert ev[0]["kind"] == "unrated" and ev[0]["detail"] == "no LB rating (baseline 40)"


def test_two_show_day_is_ranked_per_show():
    """C32 D3: Olof's LB lists split a two-show day; unassigned sources rank in both."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    conn.execute("INSERT INTO olof_pages (filename) VALUES ('p.htm')")
    conn.execute(
        "INSERT INTO olof_events (event_id, page_filename, date_str, date_raw, venue, notes)"
        " VALUES (1, 'p.htm', '1974-01-06', '6 January 1974 – Afternoon', 'The Spectrum',"
        " 'LB-numbers for this concert: LB-501 .')")
    conn.execute(
        "INSERT INTO olof_events (event_id, page_filename, date_str, date_raw, venue, notes)"
        " VALUES (2, 'p.htm', '1974-01-06', '6 January 1974 – Evening', 'The Spectrum',"
        " 'LB-numbers for this concert: LB-502 .')")
    conn.commit()
    _seed_entry(conn, 501, "1/6/74", rating="B")
    _seed_entry(conn, 502, "1/6/74", rating="A")
    _seed_entry(conn, 503, "1/6/74", rating="B+", description="late show, reel > DAT")
    _seed_entry(conn, 504, "1/6/74", rating="C")

    picks.recompute(db_path=db_path)

    rows = conn.execute(
        "SELECT lb_number, event_id, pick_rank FROM show_picks WHERE concert_date = '1/6/74'"
    ).fetchall()
    by_event: dict = {}
    for r in rows:
        by_event.setdefault(r["event_id"], {})[r["lb_number"]] = r["pick_rank"]
    assert set(by_event[1]) == {501, 504}          # afternoon list + unassigned
    assert set(by_event[2]) == {502, 503, 504}     # evening list + "late" + unassigned
    assert by_event[1][501] == 1 and by_event[2][502] == 1


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
    _seed_entry(conn, 910, "1/1/91", rating="B")
    _seed_entry(conn, 911, "1/1/91", rating="B")
    _seed_taper_attribution(conn, 910, "reputable_taper", confidence="confirmed")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/91")}
    assert "taper_reputation" in _evidence_kinds(rows[910])
    assert "taper_reputation" not in _evidence_kinds(rows[911])
    bonus = picks.PICK_WEIGHTS["taper_reputation_bonus"]
    assert abs((rows[910]["pick_score"] - rows[911]["pick_score"]) - bonus) < 0.01


def test_taper_reputation_skipped_when_table_missing_data():
    """Feature-detection: an empty taper_attributions table contributes nothing
    (no crash), matching a fresh install before TAPER phase 1 has run."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 920, "1/1/92", rating="B")

    stats = picks.recompute(db_path=db_path)
    assert stats["total"] == 1


# ── TODO-344/C27: fragments never outrank complete sources ────────────────────

def _seed_timing(conn, lb, timing):
    conn.execute("UPDATE entries SET timing = ? WHERE lb_number = ?", (timing, lb))
    conn.commit()


def test_fragment_never_outranks_complete_source_on_runtime():
    """A short-runtime fragment must not beat full-length sources into rank 1,
    even with a much higher rating (TODO-344: compute_show_picks previously
    scored every source with no completeness signal at all)."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 2000, "10/26/63", rating="A+")   # would win on score alone
    _seed_entry(conn, 2001, "10/26/63", rating="C")
    _seed_entry(conn, 2002, "10/26/63", rating="C")
    _seed_timing(conn, 2000, "20min")   # fragment: well under 60% of the median
    _seed_timing(conn, 2001, "70min")
    _seed_timing(conn, 2002, "68min")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "10/26/63")}
    assert rows[2000]["pick_score"] > rows[2001]["pick_score"]  # score alone favors it
    assert rows[2000]["pick_rank"] > rows[2001]["pick_rank"]    # but rank does not
    assert rows[2001]["pick_rank"] == 1
    assert "fragment" in _evidence_kinds(rows[2000])
    assert "fragment" not in _evidence_kinds(rows[2001])


def test_no_fragment_penalty_without_runtime_spread():
    """Sources with similar runtimes (no outlier) all stay non-fragments — the
    rule only fires on a real runtime gap vs. the date's median."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 2100, "1/1/64", rating="A")
    _seed_entry(conn, 2101, "1/1/64", rating="B")
    _seed_timing(conn, 2100, "65min")
    _seed_timing(conn, 2101, "60min")

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "1/1/64")}
    assert "fragment" not in _evidence_kinds(rows[2100])
    assert "fragment" not in _evidence_kinds(rows[2101])
    assert rows[2100]["pick_rank"] == 1


# ── TODO-349: tracklist fragments demoted only vs. a materially longer source ──

def _seed_event(conn, event_id, date_iso, event_type="concert", page_filename="p1"):
    conn.execute(
        "INSERT OR IGNORE INTO olof_pages (filename, url, corpus) VALUES (?, 'http://x', 'dsn')",
        (page_filename,),
    )
    conn.execute(
        "INSERT INTO olof_events (event_id, page_filename, event_type, date_str) "
        "VALUES (?, ?, ?, ?)",
        (event_id, page_filename, event_type, date_iso),
    )
    conn.commit()


def _seed_songs(conn, event_id, titles):
    conn.executemany(
        "INSERT INTO olof_songs (event_id, position, song_title, is_encore) VALUES (?, ?, ?, 0)",
        [(event_id, i, t) for i, t in enumerate(titles, start=1)],
    )
    conn.commit()


def _seed_setlist_text(conn, lb, setlist_text):
    conn.execute("UPDATE entries SET setlist = ? WHERE lb_number = ?", (setlist_text, lb))
    conn.commit()


def test_tracklist_fragment_1964_05_14_stays_rank_1_without_materially_longer_source():
    """1964-05-14 (.debug/todo344_rank1_diff.md): LB-01254 tracklists 1/3 songs
    (a completeness fragment under FRAGMENT_THRESHOLD) but is the same 4min
    length as LB-03015's no-tracklist source. TODO-349: without a non-fragment
    source at least TRACKLIST_FRAGMENT_DEMOTION_RATIO times longer, the
    tracklisted source is not demoted and keeps rank 1."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 1, "1964-05-14")
    _seed_songs(conn, 1, ["Song A", "Song B", "Song C"])
    _seed_entry(conn, 1254, "5/14/64", rating="B")
    _seed_entry(conn, 3015, "5/14/64", rating="B")
    _seed_setlist_text(conn, 1254, "1. Song A")  # 1/3 songs -> fragment (tracklist basis)
    _seed_timing(conn, 1254, "4min")
    _seed_timing(conn, 3015, "4min")  # no setlist text -> runtime basis, not a fragment

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "5/14/64")}
    assert "fragment" not in _evidence_kinds(rows[1254])
    assert rows[1254]["pick_rank"] == 1


def test_tracklist_fragment_demoted_when_non_fragment_materially_longer():
    """Same completeness shortfall as above, but this time a non-fragment
    source is >= 1.5x the tracklisted fragment's runtime -- it is demoted."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_event(conn, 2, "1964-05-15")
    _seed_songs(conn, 2, ["Song A", "Song B", "Song C"])
    _seed_entry(conn, 1300, "5/15/64", rating="B")
    _seed_entry(conn, 1301, "5/15/64", rating="B")
    _seed_setlist_text(conn, 1300, "1. Song A")  # 1/3 songs -> fragment (tracklist basis)
    _seed_timing(conn, 1300, "4min")
    _seed_timing(conn, 1301, "10min")  # >= 1.5 * 4min -> materially longer, no tracklist

    picks.recompute(db_path=db_path)

    rows = {r["lb_number"]: r for r in _picks_for_date(conn, "5/15/64")}
    assert "fragment" in _evidence_kinds(rows[1300])
    assert rows[1301]["pick_rank"] == 1


# ── Degraded case (spec §7 phase 2) ────────────────────────────────────────────

def test_degraded_single_candidate_no_metrics():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 999, "1/1/93", rating=None)

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1/1/93")
    assert len(rows) == 1
    assert rows[0]["pick_rank"] == 1
    kinds = _evidence_kinds(rows[0])
    assert "unrated" in kinds
    assert "solo" in kinds


# ── Tie-breaking ─────────────────────────────────────────────────────────────

def test_tie_breaks_toward_lower_lb_number():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1002, "1/1/94", rating="B")
    _seed_entry(conn, 1001, "1/1/94", rating="B")

    picks.recompute(db_path=db_path)

    rows = _picks_for_date(conn, "1/1/94")
    assert rows[0]["lb_number"] == 1001
    assert rows[0]["pick_rank"] == 1
    assert rows[1]["lb_number"] == 1002
    assert rows[1]["pick_rank"] == 2


# ── Idempotency / dry-run (spec §8) ────────────────────────────────────────────

def test_idempotent_rerun():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1100, "1/1/95", rating="A")
    _seed_entry(conn, 1101, "1/1/95", rating="C")
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
    _seed_entry(conn, 1200, "1/1/96", rating="A")

    stats = picks.recompute(db_path=db_path, dry_run=True)

    assert stats["total"] == 1
    count = conn.execute("SELECT COUNT(*) FROM show_picks").fetchone()[0]
    assert count == 0


# ── Wholesale-write guards (BUG-246) ───────────────────────────────────────────

def test_empty_recompute_keeps_existing_picks():
    """Zero computed picks must not commit the wholesale DELETE (BUG-246)."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1300, "1/1/97", rating="A")
    picks.recompute(db_path=db_path)
    assert conn.execute("SELECT COUNT(*) FROM show_picks").fetchone()[0] == 1

    conn.execute("DELETE FROM entries")
    conn.commit()
    stats = picks.recompute(db_path=db_path)

    assert stats["total"] == 0
    kept = conn.execute("SELECT COUNT(*) FROM show_picks").fetchone()[0]
    assert kept == 1  # old rows preserved, not wiped


def test_write_targets_db_path_not_queue_binding():
    """When the singleton queue is bound to another DB, writes must still land
    in the recompute's db_path (BUG-246: first-init-wins queue caused reads and
    writes to split across databases)."""
    import backend.db_queue as db_queue

    db_path_a, _ = _make_db()  # binds the queue (if this test runs first)
    db.init_db(db_path_a)
    queue_db = db_queue.get_write_queue().db_path

    db_path_b, _ = _make_db()
    assert str(queue_db) != str(db_path_b)  # queue still bound to its first DB
    conn_b = db.get_connection(db_path_b)
    _seed_entry(conn_b, 1400, "1/1/98", rating="B")

    picks.recompute(db_path=db_path_b)

    in_b = conn_b.execute("SELECT COUNT(*) FROM show_picks").fetchone()[0]
    assert in_b == 1  # landed in the DB that was read from
    conn_q = db.get_connection(queue_db)
    in_q = conn_q.execute(
        "SELECT COUNT(*) FROM show_picks WHERE lb_number = 1400").fetchone()[0]
    assert in_q == 0  # and NOT in the queue's DB


# ── POST /api/derived/recompute (F1 chained endpoint) ──────────────────────────

def test_derived_recompute_endpoint_event_sequence():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 5000, "1/1/97", rating="A",
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


# ── C09: NULL-date skip and scored-scan choice (BUG-346 / BUG-345) ─────────────

def test_partial_dates_get_no_pick():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1, "7/28/00", rating="A")
    _seed_entry(conn, 2, "xx/xx/61", rating="A")
    _seed_entry(conn, 3, "5/xx/87", rating="A")

    picks.recompute(db_path=db_path)

    rows = conn.execute("SELECT lb_number, concert_date_iso FROM show_picks").fetchall()
    assert [(r["lb_number"], r["concert_date_iso"]) for r in rows] == [(1, "2000-07-28")]
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_quality_reads_largest_scored_scan_not_newest():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    for lb in (10, 11, 12):
        _seed_entry(conn, lb, "7/28/00")
        _seed_quality(conn, lb, scan_id=5, rank_in_family=1, abs_score=70.0)
    _seed_quality(conn, 10, scan_id=9, rank_in_family=2, abs_score=40.0)  # small calibration

    quality = picks._load_latest_quality(conn)

    assert set(quality) == {10, 11, 12}
    assert quality[10]["abs_score"] == 70.0
    shutil.rmtree(tmp_dir, ignore_errors=True)
