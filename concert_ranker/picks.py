"""Show pick scoring — Phase 2 of the unified ranking spec.

See ``instructions/FABLE_UNIFIED_RANKING.md`` §3/§4 for the design and
``instructions/SPEC_INTEGRATION_NOTES.md`` findings F1/F3/F5/F6, which amend
and override the spec where noted:

- F1: this module is called by ``tools/compute_show_picks.py`` (per-step CLI,
  primary interface) and by the ``POST /api/derived/recompute`` chained
  endpoint in ``backend/app.py`` — there is no standalone
  ``POST /api/picks/recompute``.
- F3: evidence records share a common core ``{"kind": str, "detail": str}``
  plus optional extras (here: ``points``).
- F5: freshening ``entry_lineage`` (via ``tools/parse_lineage.py``) is the
  caller's responsibility — see ``tools/compute_show_picks.py``.
- F6: the ``derived_from_lb`` traversal here is local to this module by
  design; it is intentionally NOT shared with the (differently-semantic)
  taper attribution spec's same-source graph traversal.

Deliberately a hand-weighted linear points model (spec §4) — auditable,
tweakable in one config dict (:data:`PICK_WEIGHTS`), and the evidence list
doubles as the score derivation. No ML: there is no ground truth to train on.

Entry point is :func:`recompute`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from statistics import median

from backend.db import get_connection, get_write_queue, init_db
from concert_ranker.calibrate import RATING_RANK

log = logging.getLogger(__name__)

_RATING_MIN_RANK = min(RATING_RANK.values())   # 1  (F)
_RATING_MAX_RANK = max(RATING_RANK.values())   # 13 (A+)

# Spec §8/§5: "exact eac match" / "close eac match" in a description means
# EAC's wav-compare found this copy identical (or near-identical) to another
# already-circulating copy — it offers nothing new (concert_ranker/LB_KNOWLEDGE.md
# §5/§8). Cheap regex, big precision.
_EAC_MATCH_RE = re.compile(r'exact eac match|close eac match', re.IGNORECASE)

# ── Scoring configuration (spec §4) — one dict, tweakable, self-documenting ──
PICK_WEIGHTS: dict = {
    # Term 1: entries.rating -> 0-100 base, via RATING_RANK (F=1..A+=13) linear
    # interpolation: base = (rank - 1) / (13 - 1) * 100, so F -> 0, A+ -> 100,
    # evenly spaced ~8.33-point steps between tiers. Missing/unrecognised
    # rating -> this neutral base instead, evidence kind 'unrated'.
    "rating_unrated_base": 40.0,

    # Term 2: +N per curated list that includes the LB, evidence names the
    # list. Per-list override; unlisted lists (e.g. a future TODO-182
    # WTRF-thread list) fall back to the default weight.
    "curated_list_weights": {"carbonbit": 8.0, "10haaf": 8.0},
    "curated_list_default_weight": 8.0,

    # Term 3: supersession claims (entry_lineage.better_than_lb), only when
    # both LBs are candidates on the same date.
    "supersession_claim_bonus": 6.0,
    "supersession_claim_penalty": -6.0,

    # Term 3b: derived_from_lb — child vs parent, only when both are
    # candidates on the same date (spec is silent on the cross-date case;
    # resolved here by requiring same-date co-presence, mirroring the
    # better_than_lb caveat — a parent that isn't itself a candidate for this
    # date gives nothing to be "vs"). Skipped when the child outrates the
    # parent (a superior remaster earns its keep via signals, not lineage).
    "derived_from_penalty": -4.0,

    # Term 4: family dedup / best-transfer, read from the latest
    # quality_recording_scores scan (rank_in_family / vetoed are already
    # scoped to one recording_families family by concert_ranker itself).
    "family_best_transfer_bonus": 5.0,
    "family_inferior_transfer_penalty": -3.0,
    "family_vetoed_penalty": -25.0,
    "eac_match_penalty": -10.0,

    # Term 5: audio quality adjustment, only when scanned (abs_score present).
    # 0.25 * (abs_score - rating_base), clamped +/-10 — refines, never
    # overrules, the curator.
    "audio_quality_relative_weight": 0.25,
    "audio_quality_clamp": 10.0,

    # Term 6: taper reputation, only when taper_attributions exists and has
    # confirmed rows. "high median entry rating" threshold: B+ (RATING_RANK
    # 10) — the "mike millard tier" reference from the spec text; a taper
    # whose confirmed-entry median clears this earns the candidate a bonus.
    "taper_reputation_bonus": 3.0,
    "taper_reputation_rating_threshold": RATING_RANK["B+"],
}


def _evidence(kind: str, detail: str, **extras) -> dict:
    """Build one evidence record: common core {kind, detail} + extras (F3)."""
    rec: dict = {"kind": kind, "detail": detail}
    for k, v in extras.items():
        if v is not None:
            rec[k] = v
    return rec


def _rating_rank(rating: str | None) -> int | None:
    return RATING_RANK.get((rating or "").strip())


def _rating_base(rating: str | None) -> tuple[float, dict]:
    """Map entries.rating (A+..F) to a 0-100 base score (spec §4 term 1)."""
    rank = _rating_rank(rating)
    if rank is None:
        base = PICK_WEIGHTS["rating_unrated_base"]
        return base, _evidence("unrated", "no rating on file", points=round(base, 1))
    base = (rank - _RATING_MIN_RANK) / (_RATING_MAX_RANK - _RATING_MIN_RANK) * 100
    return base, _evidence("rating", f"LB rating {rating}", points=round(base, 1))


# ── Data loading ──────────────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _load_candidates(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Group real (status='ok', dated) entries into per-date candidate lists."""
    rows = conn.execute(
        "SELECT lb_number, date_str, rating, description FROM entries"
        " WHERE status='ok' AND date_str IS NOT NULL AND date_str != ''"
    ).fetchall()
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_date[r["date_str"]].append({
            "lb_number": r["lb_number"],
            "rating": r["rating"],
            "description": r["description"] or "",
        })
    return dict(by_date)


def _load_curated_lists(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Return {lb_number: [list_name, ...]} from curated_list_entries."""
    rows = conn.execute(
        "SELECT cl.name AS name, ce.lb_number AS lb_number"
        " FROM curated_list_entries ce JOIN curated_lists cl ON cl.id = ce.list_id"
    ).fetchall()
    out: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        out[r["lb_number"]].append(r["name"])
    return dict(out)


def _load_lineage(conn: sqlite3.Connection) -> dict[int, dict]:
    """Return {lb_number: {better_than_lb: [...], derived_from_lb: [...]}}."""
    rows = conn.execute(
        "SELECT lb_number, better_than_lb, derived_from_lb FROM entry_lineage"
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        out[r["lb_number"]] = {
            "better_than_lb": json.loads(r["better_than_lb"] or "[]"),
            "derived_from_lb": json.loads(r["derived_from_lb"] or "[]"),
        }
    return out


def _load_latest_quality(conn: sqlite3.Connection) -> dict[int, dict]:
    """Return {lb_number: {rank_in_family, vetoed, abs_score}} from the newest
    scan that actually wrote scores (mirrors backend/app.py get_quality: some
    quality_scans rows are small calibration runs that never write
    quality_recording_scores, so MAX(scan_id) is taken over that table, not
    quality_scans). abs_score is None if that migration hasn't run yet on
    this DB (feature-detected via PRAGMA table_info).
    """
    scan_row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_recording_scores").fetchone()
    scan_id = scan_row["m"] if scan_row else None
    if scan_id is None:
        return {}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    select_abs = ", abs_score" if "abs_score" in cols else ""
    rows = conn.execute(
        f"SELECT lb_number, rank_in_family, vetoed{select_abs}"
        " FROM quality_recording_scores WHERE scan_id=?",
        (scan_id,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        out[r["lb_number"]] = {
            "rank_in_family": r["rank_in_family"],
            "vetoed": bool(r["vetoed"]),
            "abs_score": r["abs_score"] if select_abs else None,
        }
    return out


def _load_taper_reputation(conn: sqlite3.Connection) -> tuple[dict[int, str], dict[str, float]]:
    """Return ({lb: taper} for confirmed attributions, {taper: median_rank}
    for confirmed tapers whose median attributed-entry rating clears the
    reputation threshold) — spec §4 term 6. Feature-detects
    taper_attributions: absent/empty on fresh installs or pre-TAPER-phase-1
    databases, in which case this term silently contributes nothing.
    """
    if not _table_exists(conn, "taper_attributions"):
        return {}, {}
    rows = conn.execute(
        "SELECT ta.lb_number AS lb_number, ta.taper_normalised AS taper, e.rating AS rating"
        " FROM taper_attributions ta JOIN entries e ON e.lb_number = ta.lb_number"
        " WHERE ta.confidence = 'confirmed'"
    ).fetchall()
    lb_taper: dict[int, str] = {}
    ranks_by_taper: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        lb_taper[r["lb_number"]] = r["taper"]
        rank = _rating_rank(r["rating"])
        if rank is not None:
            ranks_by_taper[r["taper"]].append(rank)

    threshold = PICK_WEIGHTS["taper_reputation_rating_threshold"]
    reputable = {
        taper: median(ranks) for taper, ranks in ranks_by_taper.items()
        if ranks and median(ranks) >= threshold
    }
    return lb_taper, reputable


# ── Scoring ──────────────────────────────────────────────────────────────────

def _score_date(
    candidates: list[dict],
    curated: dict[int, list[str]],
    lineage: dict[int, dict],
    quality: dict[int, dict],
    lb_taper: dict[int, str],
    reputable_tapers: dict[str, float],
) -> list[tuple[int, float, list[dict]]]:
    """Score every candidate LB on one date. Returns unordered (lb, score, evidence)."""
    lb_set = {c["lb_number"] for c in candidates}
    rating_by_lb = {c["lb_number"]: c["rating"] for c in candidates}
    # score/evidence held in mutable per-lb slots so the supersession /
    # derived_from passes (which need the whole date's candidate set at once)
    # can adjust entries scored by the main per-candidate pass below.
    scored: dict[int, list] = {}

    for c in candidates:
        lb = c["lb_number"]
        score = 0.0
        evidence: list[dict] = []

        base, ev = _rating_base(c["rating"])
        score += base
        evidence.append(ev)

        for list_name in curated.get(lb, ()):
            weight = PICK_WEIGHTS["curated_list_weights"].get(
                list_name, PICK_WEIGHTS["curated_list_default_weight"])
            score += weight
            evidence.append(_evidence("curated_list", f"{list_name}'s picks", points=weight))

        if _EAC_MATCH_RE.search(c["description"]):
            pts = PICK_WEIGHTS["eac_match_penalty"]
            score += pts
            evidence.append(_evidence("eac_match", "offers nothing new (EAC match)", points=pts))

        q = quality.get(lb)
        if q:
            if q["vetoed"]:
                pts = PICK_WEIGHTS["family_vetoed_penalty"]
                score += pts
                evidence.append(_evidence(
                    "vetoed", "vetoed transfer (lossy-sourced etc.)", points=pts))
            elif q["rank_in_family"] == 1:
                pts = PICK_WEIGHTS["family_best_transfer_bonus"]
                score += pts
                evidence.append(_evidence(
                    "best_transfer", "best transfer in its family", points=pts))
            elif q["rank_in_family"] is not None:
                pts = PICK_WEIGHTS["family_inferior_transfer_penalty"]
                score += pts
                evidence.append(_evidence(
                    "inferior_transfer", "inferior transfer within its family", points=pts))
            if q["abs_score"] is not None:
                clamp = PICK_WEIGHTS["audio_quality_clamp"]
                delta = PICK_WEIGHTS["audio_quality_relative_weight"] * (q["abs_score"] - base)
                delta = max(-clamp, min(clamp, delta))
                score += delta
                evidence.append(_evidence(
                    "audio_quality", f"scanned quality {q['abs_score']:.0f}/100",
                    points=round(delta, 2)))

        taper = lb_taper.get(lb)
        if taper and taper in reputable_tapers:
            pts = PICK_WEIGHTS["taper_reputation_bonus"]
            score += pts
            evidence.append(_evidence(
                "taper_reputation", f"confirmed taper '{taper}' (high median rating)",
                points=pts))

        scored[lb] = [score, evidence]

    # Term 3: supersession claims — directional, both must be this date's candidates.
    for lb in lb_set:
        edges = lineage.get(lb)
        if not edges:
            continue
        for claimed in edges["better_than_lb"]:
            if claimed == lb or claimed not in lb_set:
                continue
            bonus = PICK_WEIGHTS["supersession_claim_bonus"]
            penalty = PICK_WEIGHTS["supersession_claim_penalty"]
            scored[lb][0] += bonus
            scored[lb][1].append(_evidence(
                "supersession", f"claims better than LB-{claimed}", points=bonus))
            scored[claimed][0] += penalty
            scored[claimed][1].append(_evidence(
                "superseded", f"claimed superseded by LB-{lb}", points=penalty))

    # Term 3b: derived_from — child penalized vs parent unless higher-rated.
    for lb in lb_set:
        edges = lineage.get(lb)
        if not edges:
            continue
        for parent in edges["derived_from_lb"]:
            if parent == lb or parent not in lb_set:
                continue
            child_rank = _rating_rank(rating_by_lb.get(lb))
            parent_rank = _rating_rank(rating_by_lb.get(parent))
            if child_rank is not None and parent_rank is not None and child_rank > parent_rank:
                continue  # superior remaster earns its keep via signals, not lineage
            penalty = PICK_WEIGHTS["derived_from_penalty"]
            scored[lb][0] += penalty
            scored[lb][1].append(_evidence(
                "derived_from", f"derived from LB-{parent}", points=penalty))

    rows = [(lb, s, ev) for lb, (s, ev) in scored.items()]
    if len(rows) == 1:
        rows[0][2].append(_evidence("solo", "only circulating copy"))
    return rows


def _rank_date(rows: list[tuple[int, float, list[dict]]]) -> list[tuple[int, float, list[dict], int]]:
    """Sort by score desc, ties toward lower LB number; assign pick_rank 1..N."""
    ordered = sorted(rows, key=lambda r: (-r[1], r[0]))
    return [(lb, score, ev, rank) for rank, (lb, score, ev) in enumerate(ordered, start=1)]


# ── Orchestration ──────────────────────────────────────────────────────────────

def _write_picks(all_rows: list[tuple[str, int, float, int, list[dict]]],
                 db_path: str | None) -> None:
    """Wholesale-replace show_picks with the freshly computed rows."""
    payload = [
        (date, lb, round(score, 2), rank, json.dumps(ev))
        for date, lb, score, rank, ev in all_rows
    ]

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM show_picks")
        conn.executemany(
            "INSERT INTO show_picks"
            " (concert_date, lb_number, pick_score, pick_rank, evidence_json)"
            " VALUES (?, ?, ?, ?, ?)",
            payload,
        )

    get_write_queue().execute(_do)


def _summarize(all_rows: list[tuple[str, int, float, int, list[dict]]]) -> dict:
    """Row/date counts + score distribution (spec §7 phase-2 report)."""
    scores = sorted(r[2] for r in all_rows)
    dates = {r[0] for r in all_rows}
    summary = {"total": len(all_rows), "dates": len(dates)}
    if scores:
        n = len(scores)
        summary["score_min"] = round(scores[0], 2)
        summary["score_median"] = round(scores[n // 2], 2)
        summary["score_max"] = round(scores[-1], 2)
    return summary


def recompute(db_path: str | None = None, dry_run: bool = False) -> dict:
    """Recompute show_picks wholesale from ratings, curated lists, lineage,
    quality scans, and (if present) taper attributions.

    Assumes entry_lineage is already fresh — callers that need the F5
    freshness guarantee should run ``tools/parse_lineage.py``'s ``run()``
    first (``tools/compute_show_picks.py`` does this).

    Idempotent: re-running with unchanged inputs (ratings / curated lists /
    entry_lineage / quality scans / taper_attributions) produces an identical
    table (spec §8), because the whole table is deterministically rebuilt
    from that input every time — there is no dependency on the table's own
    prior contents.

    Args:
        db_path: Optional database path override.
        dry_run: Compute but do not write to the database.

    Returns:
        Summary dict: total rows, distinct dates, and score_min/median/max
        (omitted when there are zero candidate entries).
    """
    init_db(db_path)  # idempotent; ensures show_picks and its dependencies exist
    conn = get_connection(db_path)

    by_date = _load_candidates(conn)
    curated = _load_curated_lists(conn)
    lineage = _load_lineage(conn)
    quality = _load_latest_quality(conn)
    lb_taper, reputable_tapers = _load_taper_reputation(conn)

    all_rows: list[tuple[str, int, float, int, list[dict]]] = []
    for date, candidates in by_date.items():
        scored = _score_date(candidates, curated, lineage, quality, lb_taper, reputable_tapers)
        for lb, score, ev, rank in _rank_date(scored):
            all_rows.append((date, lb, score, rank, ev))

    summary = _summarize(all_rows)
    if not dry_run:
        _write_picks(all_rows, db_path)
    return summary
