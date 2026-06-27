"""Turn stored RAW metrics into ranked verdicts — the scan-once payoff.

Everything here reads ``quality_recording_metrics`` and writes
``quality_recording_scores``; it never touches audio. That is what makes
``rerank`` possible: re-tuning thresholds or re-grouping families re-categorises
the whole corpus with zero rescans.

Two cases (design decision #5 / Task 7):

* **In a family** (same show, different transfers): normalise across siblings
  with MAD-z, fuse, assign ``rank_in_family``.
* **Ungrouped**: score standalone — absolute bands only, no relative rank.
  Family grouping is never a hard dependency of producing a score.
"""
from __future__ import annotations

import logging
import sqlite3

from concert_ranker import quality_score
from concert_ranker import scoring as S

log = logging.getLogger("concert_ranker.families")


def _inject_completeness(group: dict[int, dict]) -> dict[int, dict]:
    """Return ``{lb: raw}`` with ``completeness`` filled in per family.

    Completeness is sibling-relative (this recording's length vs the longest in
    the group), so it can only be computed once the whole family is known — not
    at scan time. Standalone recordings get completeness 1.0.
    """
    raws: dict[int, dict] = {lb: dict(d["metrics"]) for lb, d in group.items()}
    durations = [d.get("duration_sec") for d in group.values() if d.get("duration_sec")]
    max_dur = max(durations) if durations else None
    for lb, d in group.items():
        dur = d.get("duration_sec")
        if "completeness" not in raws[lb] or raws[lb].get("completeness") is None:
            raws[lb]["completeness"] = (dur / max_dur) if (dur and max_dur) else 1.0
    return raws


def rank_group(group: dict[int, dict], family_id: int | None,
               decades: dict[int, int] | None = None) -> list[dict]:
    """Rank one set of sibling recordings (or a single standalone recording).

    Args:
        group: ``{lb_number: {"metrics": raw, "duration_sec": ...}}`` as returned
            by :func:`concert_ranker.lb.repo.load_metrics`.
        family_id: Dense per-scan family id, or None for an ungrouped recording.
        decades: Optional ``{lb_number: decade_int}`` so each recording's absolute
            bands are judged against its own era (see ``config.DECADE_BANDS``).

    Returns:
        Score rows ready for :func:`concert_ranker.lb.repo.write_scores`.
    """
    decades = decades or {}
    if not group:
        return []
    raws = _inject_completeness(group)

    # 1. Hard disqualifiers (veto / demote before any ranking)
    dq = {lb: S.check_disqualifiers(raw) for lb, raw in raws.items()}
    survivors = {lb: raws[lb] for lb in raws if not dq[lb][1]}

    # 2. MAD-z normalise survivors, fuse to a final score
    z_all = S.normalize_siblings(survivors) if survivors else {}
    finals: dict[int, float] = {}
    for lb in survivors:
        fam = S.family_scores(z_all.get(lb, {}))
        ts = S.track_score(fam)
        finals[lb] = S.recording_score([ts])["final"]

    # 3. Rank survivors high→low
    ranking = sorted(finals, key=lambda lb: finals[lb], reverse=True)
    rank_of = {lb: i + 1 for i, lb in enumerate(ranking)}
    n_surv = len(survivors)

    rows: list[dict] = []
    for lb, raw in raws.items():
        labels, vetoed = dq[lb]
        z = z_all.get(lb, {})
        rank = rank_of.get(lb, 0)
        verdict = S.explain_recording(lb, raw, z, rank, n_surv, labels, vetoed,
                                      decade=decades.get(lb),
                                      source_class=group[lb].get("source_class"))
        # absolute quality grade (standalone, from the metrics — see quality_score)
        abs_score, abs_grade, _ = quality_score.grade(raw, group[lb].get("source_class"))
        verdict = f"Grade {abs_grade} ({abs_score:.0f}/100). {verdict}"
        rows.append({
            "lb_number": lb,
            "family_id": family_id,
            "final_score": None if vetoed else finals.get(lb),
            "rank_in_family": None if vetoed else (rank or None),
            "vetoed": vetoed,
            "verdict_text": verdict,
            "abs_score": round(abs_score, 1),
            "abs_grade": abs_grade,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Family membership from recording_families (MASTER table)
# ─────────────────────────────────────────────────────────────────────────────
def load_decade_map(conn: sqlite3.Connection, lb_numbers=None) -> dict[int, int]:
    """Return ``{lb_number: decade_int}`` from ``entries.date_str``.

    Used so each recording's absolute bands are judged against its own era.
    Recordings whose year can't be parsed are omitted (scorer falls back to the
    global bands).
    """
    from concert_ranker.calibration import _entry_year
    from concert_ranker.config import decade_of

    sql = "SELECT lb_number, date_str FROM entries"
    params: list = []
    lbs = list(lb_numbers) if lb_numbers is not None else None
    if lbs:
        sql += " WHERE lb_number IN ({})".format(",".join("?" * len(lbs)))
        params.extend(lbs)
    out: dict[int, int] = {}
    for r in conn.execute(sql, params):
        dec = decade_of(_entry_year(r["date_str"]))
        if dec is not None:
            out[int(r["lb_number"])] = dec
    return out


def load_family_map(conn: sqlite3.Connection,
                    lb_numbers=None) -> dict[int, str]:
    """Return ``{lb_number: fam_id}`` from ``recording_families``.

    Recordings absent from the table are ungrouped (handled as standalone).
    Returns an empty map if the table does not exist yet (Task 7 is optional).
    """
    try:
        sql = "SELECT lb_number, fam_id FROM recording_families"
        params: list = []
        lbs = list(lb_numbers) if lb_numbers is not None else None
        if lbs:
            sql += " WHERE lb_number IN ({})".format(",".join("?" * len(lbs)))
            params.extend(lbs)
        return {int(r["lb_number"]): r["fam_id"] for r in conn.execute(sql, params)}
    except sqlite3.OperationalError:
        return {}


def _dense_family_ids(fam_ids) -> dict[str, int]:
    """Map distinct text ``fam_id`` → a stable dense integer (sorted order).

    ``quality_recording_scores.family_id`` is INTEGER; ``recording_families``
    keys families by a deterministic text ``fam_id``. Sorting the distinct
    fam_ids and indexing them gives a reproducible integer for the same family
    set within a scan.
    """
    return {fid: i + 1 for i, fid in enumerate(sorted(set(fam_ids)))}


def rank_scan(metrics: dict[int, dict], family_map: dict[int, str],
              decades: dict[int, int] | None = None) -> list[dict]:
    """Rank every recording in a scan, grouping by family where one exists.

    Args:
        metrics: ``{lb: {"metrics", "duration_sec", ...}}`` for the whole scan
            (from :func:`concert_ranker.lb.repo.load_metrics`).
        family_map: ``{lb: fam_id}`` (text) from :func:`load_family_map`.
        decades: Optional ``{lb: decade_int}`` from :func:`load_decade_map` for
            per-era banding.

    Returns:
        All score rows across all families + standalone recordings.
    """
    fam_int = _dense_family_ids(v for lb, v in family_map.items() if lb in metrics)

    groups: dict[int, dict[int, dict]] = {}
    standalone: dict[int, dict] = {}
    for lb, data in metrics.items():
        fid = family_map.get(lb)
        if fid is None:
            standalone[lb] = data
        else:
            groups.setdefault(fam_int[fid], {})[lb] = data

    rows: list[dict] = []
    for family_id, group in groups.items():
        if len(group) == 1:
            # A family of one is effectively ungrouped — no relative rank.
            only_lb = next(iter(group))
            standalone[only_lb] = group[only_lb]
            continue
        rows.extend(rank_group(group, family_id, decades))
    for lb, data in standalone.items():
        rows.extend(rank_group({lb: data}, None, decades))
    return rows
