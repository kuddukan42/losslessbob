"""Calibration orchestration (Task 6) — the step that makes thresholds trustworthy.

The provisional ``# CALIBRATE`` thresholds in :mod:`concert_ranker.config` are
first-principles guesses. This module runs the scan over a stratified sample of
the user's *real* audio (with known A–F ratings + source class + mined human
commentary) and feeds the results to the calibration harness
(:mod:`concert_ranker.calibrate`) to:

1. report which metrics actually track the human rating (``score_separation``);
2. fit band cutoffs per metric per source class (``fit_thresholds``);
3. validate algorithmic labels against mined commentary (``validate_labels``).

Fitted cutoffs are returned as a *report* and the config snapshot is recorded in
``quality_scans.config_json``; they are NOT auto-written into ``config.py``.
Rewriting thresholds is a human-reviewed step — a thin/biased sample can produce
nonsense cutoffs, and silently mutating the scoring config would be worse than
leaving the guesses in place. The report gives the user exactly what to paste.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict

from concert_ranker import calibrate as C
from concert_ranker.config import SOURCE_CLASSES, default_config
from concert_ranker.lb import commentary, repo, source_type
from concert_ranker.scoring import all_bands

log = logging.getLogger("concert_ranker.calibration")

# Metrics worth fitting cutoffs for (the banded/severity ones).
_FIT_METRICS = ("mud_ratio_db", "harsh_ratio_db", "sibilance_ratio_db",
                "hiss_floor_db", "crowd_snr_db", "presence_ratio_db",
                "bass_ratio_db", "air_ratio_db")


def stratified_sample(conn: sqlite3.Connection, per_cell: int = 5) -> list[dict]:
    """Pull a sample stratified by rating × source_class, on-disk only.

    Returns ``[{lb, disk_path, rating, source_class}, ...]`` with up to
    ``per_cell`` recordings per (rating, source_class) cell. Only LBs present in
    ``my_collection`` (i.e. on disk) are eligible.
    """
    rows = conn.execute(
        "SELECT e.lb_number AS lb, e.rating AS rating, e.description AS description,"
        "       e.source_chain AS source_chain, e.source_type AS source_type,"
        "       c.disk_path AS disk_path "
        "FROM entries e JOIN my_collection c ON e.lb_number = c.lb_number "
        "WHERE e.rating IS NOT NULL AND e.rating != ''"
    ).fetchall()

    cells: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        cls = source_type.derive_source_class(
            r["description"], r["source_chain"], r["source_type"])
        cell = (r["rating"], cls)
        if len(cells[cell]) < per_cell:
            cells[cell].append({
                "lb": int(r["lb"]), "disk_path": r["disk_path"],
                "rating": r["rating"], "source_class": cls,
                "description": r["description"] or "",
            })
    return [item for items in cells.values() for item in items]


_GOOD_TIER = frozenset({"A+", "A", "A-"})
_BAD_TIER = frozenset({"D+", "D", "D-", "F"})


def _entry_year(date_str: str | None) -> int | None:
    """Parse a 4-digit year from a LosslessBob ``date_str`` (``M/D/YY`` form).

    Two-digit years map to 19xx for 31-99 and 20xx for 00-30 (Dylan's circulating
    span is ~1960-2026). Returns None if no year is parseable.
    """
    if not date_str:
        return None
    tail = date_str.strip().split("/")[-1].strip()
    if re.fullmatch(r"\d{4}", tail):
        return int(tail)
    if re.fullmatch(r"\d{2}", tail):
        yy = int(tail)
        return 2000 + yy if yy <= 30 else 1900 + yy
    return None


def _tier(rating: str) -> str:
    return "GOOD" if rating in _GOOD_TIER else "BAD" if rating in _BAD_TIER else "MID"


def decade_stratified_sample(conn: sqlite3.Connection, per_cell: int = 18,
                             classes: tuple | None = None,
                             ratings: tuple | None = None) -> list[dict]:
    """Decade × rating-tier × source_class stratified sample, on-disk only.

    Designed for a large era-balanced calibration run: every decade is
    represented, and ALL bad-tier (D/F) recordings are included regardless of
    ``per_cell`` because they are scarce (~100 across the whole archive) yet
    essential for fitting good-vs-bad cutoffs. Good/mid cells are capped at
    ``per_cell``.

    When ``ratings`` is given (e.g. ``("C+", "C", "C-")``), the sample is
    restricted to those exact ratings and stratified by decade × EXACT rating ×
    class (each cell capped at ``per_cell``) — used to fill in an under-sampled
    band like the C tier. Otherwise it stratifies by decade × tier × class with
    all bad-tier included.

    Returns ``[{lb, disk_path, rating, source_class, year}, ...]``.
    """
    rating_set = set(ratings) if ratings else None
    rows = conn.execute(
        "SELECT e.lb_number AS lb, e.date_str AS date_str, e.rating AS rating,"
        "       e.description AS description, e.source_chain AS source_chain,"
        "       e.source_type AS source_type, c.disk_path AS disk_path "
        "FROM entries e JOIN my_collection c ON e.lb_number = c.lb_number "
        "WHERE e.rating IS NOT NULL AND e.rating != ''"
    ).fetchall()

    cells: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        year = _entry_year(r["date_str"])
        if year is None or year < 1960:
            continue
        if rating_set is not None and r["rating"] not in rating_set:
            continue
        cls = source_type.derive_source_class(
            r["description"], r["source_chain"], r["source_type"])
        if classes and cls not in classes:
            continue
        if rating_set is not None:
            cell = ((year // 10) * 10, r["rating"], cls)  # fine-rating cells
            cap = per_cell
        else:
            tier = _tier(r["rating"])
            cell = ((year // 10) * 10, tier, cls)
            cap = 10 ** 9 if tier == "BAD" else per_cell  # take ALL bad-tier
        if len(cells[cell]) < cap:
            cells[cell].append({
                "lb": int(r["lb"]), "disk_path": r["disk_path"],
                "rating": r["rating"], "source_class": cls, "year": year,
                "description": r["description"] or "",
            })
    return [item for items in cells.values() for item in items]


def build_samples(conn: sqlite3.Connection, scan_id: int,
                  sample: list[dict]) -> list[dict]:
    """Join stored scan metrics with rating/source_class/commentary per LB."""
    import math

    from .features import extract_text
    lbs = [s["lb"] for s in sample]
    stored = repo.load_metrics(conn, scan_id, lbs)
    text = commentary.commentary_for(conn, lbs)
    meta = {s["lb"]: s for s in sample}

    # Inject dff_vert_occ = log1p(vert_occ) from dff_reports where available.
    try:
        placeholders = ",".join("?" * len(lbs))
        dff_rows = conn.execute(
            "SELECT lb_number, vert_occ FROM dff_reports "
            f"WHERE xref = 0 AND lb_number IN ({placeholders})",
            lbs,
        ).fetchall()
        dff_map = {row[0]: row[1] for row in dff_rows}
    except Exception:
        dff_map = {}

    out = []
    for lb, data in stored.items():
        m = meta.get(lb, {})
        metrics = data["metrics"]
        if lb in dff_map and dff_map[lb] is not None:
            metrics["dff_vert_occ"] = math.log1p(float(dff_map[lb]))
        # Inject text features from the curator description (DB-side; no rescan)
        description = m.get("description", "")
        if description is None:
            description = ""
        metrics.update(extract_text(description))
        out.append({
            "lb": lb,
            "rating": m.get("rating"),
            "source_class": data.get("source_class") or m.get("source_class") or "UNKNOWN",
            "metrics": metrics,
            "commentary": text.get(lb, ""),
        })
    return out


def analyse(samples: list[dict]) -> dict:
    """Run the three calibration analyses over scanned samples.

    Returns ``{"separation", "thresholds", "labels"}``.
    """
    separation = C.score_separation(samples)

    thresholds: dict[str, dict] = {}
    for cls in SOURCE_CLASSES:
        for metric in _FIT_METRICS:
            res = C.fit_thresholds(samples, metric, cls)
            if "threshold" in res:
                thresholds.setdefault(cls, {})[metric] = res

    banded = {s["lb"]: all_bands(s["metrics"]) for s in samples}
    labels = C.validate_labels(samples, banded)
    return {"separation": separation, "thresholds": thresholds, "labels": labels}


def run_calibration(conn: sqlite3.Connection, *, db_path: str | None,
                    per_cell: int = 5, workers: int = 8,
                    classes: tuple | None = None,
                    staging_dir: str | None = None,
                    by_decade: bool = False,
                    ratings: tuple | None = None) -> dict:
    """Full calibration: sample → scan → analyse. Returns a report dict.

    The scan's config snapshot is written to ``quality_scans.config_json`` for
    reproducibility. Fitted thresholds are returned, not applied.

    Args:
        per_cell: Max recordings per (rating, source_class) stratum.
        workers: Worker processes for the in-place (non-staged) path.
        classes: Restrict the sample to these source classes (e.g.
            ``("AUD", "SBD")``); None = all.
        staging_dir: If set, copy each folder here (fast scratch) before
            decoding instead of reading the HDDs in place — one producer per
            physical drive, ``workers`` consumers.
        by_decade: Use the large decade × tier × class stratified sample (all
            decades represented, all bad-tier included) instead of the plain
            rating × class one.
    """
    if by_decade or ratings:
        sample = decade_stratified_sample(conn, per_cell=per_cell, classes=classes,
                                          ratings=ratings)
    else:
        sample = stratified_sample(conn, per_cell=per_cell)
        if classes:
            sample = [s for s in sample if s["source_class"] in classes]
    if not sample:
        return {"error": "no on-disk rated recordings to sample"}

    cfg = vars(default_config())
    scan_id = repo.create_scan(
        conn, config=cfg,
        notes=f"calibration sample (per_cell={per_cell}, classes={classes or 'all'}, "
              f"by_decade={by_decade}, ratings={ratings or 'all'}, n={len(sample)})")

    worklist = [(s["lb"], s["disk_path"], s["source_class"]) for s in sample]
    log.info("calibration scanning %d recordings (scan_id=%s, staging=%s)",
             len(worklist), scan_id, bool(staging_dir))
    if staging_dir:
        from concert_ranker.runner import group_by_device, run_staged
        run_staged(group_by_device(worklist), staging_dir, scan_id,
                   db_path=db_path, n_consumers=workers)
    else:
        from concert_ranker.runner import scan_folders
        scan_folders(worklist, scan_id, db_path=db_path, workers=workers)

    samples = build_samples(conn, scan_id, sample)
    report = analyse(samples)
    report["scan_id"] = scan_id
    report["n_sampled"] = len(sample)
    report["n_scanned"] = len(samples)
    return report
