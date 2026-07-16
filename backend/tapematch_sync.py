"""Sync TapeMatch family clustering from tools/tapematch/observations.db.

Ingests the offline TapeMatch CLI's per-show family detection results into
the main app DB (``recording_families`` / ``tapematch_family_meta``) so the
Library screen's recording lens can read ``fam`` / ``fam_label`` / ``fam_conf``
/ ``fam_by`` per recording with no clustering logic of its own. See
instructions/design_handoff_unified_library/07-tapematch-backend-integration.md
for the full design.
"""
import logging
import re
import sqlite3
import time
from pathlib import Path

from backend.db import get_connection, init_db
from backend.paths import TAPEMATCH_RUNS_DIR, TOOLS_DIR

log = logging.getLogger(__name__)

DEFAULT_OBSERVATIONS_DB_PATH = TOOLS_DIR / "tapematch" / "observations.db"

_OPEN_RETRY_ATTEMPTS = 3
_OPEN_RETRY_BACKOFF_SEC = 1.0

_VERDICT_LINE_RE = re.compile(r"^## Verdict:\s*(?P<text>.+)$", re.MULTILINE)

# TODO-210(a): one-time confidence bump when a family's members corroborate
# via matching Concert Ranker quality scores (see _has_quality_match).
_QUALITY_MATCH_BUMP = 0.05
_QUALITY_MATCH_TOL = 0.5


def _resolve_run_dir(obs_conn: sqlite3.Connection, run_id: str, concert_date: str) -> Path:
    """Best-effort path to a tapematch run's archive directory.

    observations.db's stored ``archive_dir`` can be stale for older rows
    (predates a tools/tapematch/runs/ -> data/tapematch/runs/ relocation),
    so fall back to the current ``<run_id>_<concert_date>`` directory-naming
    convention when the stored path doesn't exist on disk.
    """
    row = obs_conn.execute(
        "SELECT archive_dir FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row and row["archive_dir"]:
        candidate = Path(row["archive_dir"])
        if candidate.exists():
            return candidate
    return TAPEMATCH_RUNS_DIR / f"{run_id}_{concert_date}"


def _parse_verdict(analysis_md_text: str) -> "tuple[bool, str | None]":
    """Parse an analysis.md's ``## Verdict:`` line for a needs-review flag + reason.

    Per tools/tapematch/ANALYSIS_WRITER_PROMPT.md the canonical flagged form is
    ``<N> recordings — <M> families — result needs review — <reason>``, but the
    written corpus also contains ``needs review: <reason>`` and
    ``needs review (<reason>)`` variants (the pre-2026-07-16 parser dropped
    those reasons, leaving NULL review_reason — the TODO-242 tooltip gap).
    All three delimiters are accepted; a bare ``needs review`` with no trailing
    reason yields ``(True, None)``. Returns ``(False, None)`` if there's no
    Verdict line or it doesn't flag review (e.g. "result looks correct" /
    "all sources confirmed different").
    """
    m = _VERDICT_LINE_RE.search(analysis_md_text)
    if not m:
        return False, None
    text = m.group("text")
    pos = text.lower().find("needs review")
    if pos < 0:
        return False, None
    rest = text[pos + len("needs review"):].strip()
    reason: str | None = None
    if rest.startswith("—"):
        reason = rest.lstrip("—").strip() or None
    elif rest.startswith(":"):
        reason = rest[1:].strip() or None
    elif rest.startswith("("):
        m2 = re.match(r"\((?P<r>.+)\)\s*$", rest, re.DOTALL)
        reason = (m2.group("r") if m2 else rest.strip("() ")).strip() or None
    return True, reason


def _read_review_flag(run_dir: Path) -> "tuple[bool, str | None]":
    """Read run_dir/analysis.md (if present) and parse its needs-review verdict."""
    analysis_path = run_dir / "analysis.md"
    if not analysis_path.exists():
        return False, None
    try:
        text = analysis_path.read_text(encoding="utf-8")
    except OSError:
        log.warning("Could not read %s for review-flag parsing", analysis_path)
        return False, None
    return _parse_verdict(text)


def _open_observations_db(observations_db_path: "Path | str") -> sqlite3.Connection:
    """Open observations.db read-only, retrying briefly if it's write-locked.

    The tapematch CLI may hold a write lock mid-run; retry a few times before
    failing with a message the caller can surface to the user, rather than
    raising a bare ``sqlite3.OperationalError``.
    """
    uri = f"file:{Path(observations_db_path)}?mode=ro"
    last_err: sqlite3.OperationalError | None = None
    for attempt in range(_OPEN_RETRY_ATTEMPTS):
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            # Force the connection open / readable now, not lazily on first query.
            conn.execute("SELECT 1")
            return conn
        except sqlite3.OperationalError as e:
            last_err = e
            if attempt < _OPEN_RETRY_ATTEMPTS - 1:
                time.sleep(_OPEN_RETRY_BACKOFF_SEC * (attempt + 1))
    raise RuntimeError(
        "Could not open tapematch observations.db (it may be locked by an "
        "in-progress tapematch run). Try the sync again in a moment."
    ) from last_err


def _pick_best_run(obs_conn: sqlite3.Connection) -> dict[str, str]:
    """Return {concert_date: run_id} for the best run per date.

    Best = highest n_sources_ran, ties broken by latest run_id. A later
    timestamp is not always an improvement (a partial rerun can score lower),
    so n_sources_ran is the primary signal.
    """
    best: dict[str, tuple[int, str]] = {}
    for row in obs_conn.execute(
        "SELECT run_id, concert_date, n_sources_ran FROM runs"
    ):
        date = row["concert_date"]
        n_ran = row["n_sources_ran"] or 0
        run_id = row["run_id"]
        current = best.get(date)
        if current is None or (n_ran, run_id) > current:
            best[date] = (n_ran, run_id)
    return {date: run_id for date, (_, run_id) in best.items()}


def sync_tapematch_families(
    db_path=None,
    observations_db_path: "Path | str | None" = None,
) -> dict:
    """Ingest TapeMatch family clusters into the main DB.

    Args:
        db_path: Main app DB path, or None for the default.
        observations_db_path: Path to tapematch's observations.db, or None
            for the default location under tools/tapematch/.

    Returns:
        Stats dict: ``{dates_processed, families_written, recordings_linked,
        errors}``.
    """
    observations_db_path = observations_db_path or DEFAULT_OBSERVATIONS_DB_PATH
    if not Path(observations_db_path).exists():
        raise FileNotFoundError(f"observations.db not found: {observations_db_path}")

    # Standalone CLI runs (no Flask backend up) never go through app.py's
    # startup init_db() call, so the review_flag/review_reason migration
    # (and any other pending schema migration) wouldn't otherwise apply.
    init_db(db_path)

    obs_conn = _open_observations_db(observations_db_path)
    conn = get_connection(db_path)
    abs_scores_by_lb = _load_latest_abs_scores(conn)

    stats = {
        "dates_processed": 0,
        "families_written": 0,
        "recordings_linked": 0,
        "errors": [],
    }

    try:
        best_run_by_date = _pick_best_run(obs_conn)

        for concert_date, run_id in best_run_by_date.items():
            try:
                _sync_one_date(obs_conn, conn, concert_date, run_id, stats, abs_scores_by_lb)
                stats["dates_processed"] += 1
            except Exception as e:  # noqa: BLE001 — one bad date shouldn't abort the rest
                log.exception("tapematch sync failed for %s (run %s)", concert_date, run_id)
                stats["errors"].append(f"{concert_date} ({run_id}): {e}")
    finally:
        obs_conn.close()

    return stats


def _load_latest_abs_scores(conn: sqlite3.Connection) -> "dict[int, tuple[int, float, str]]":
    """Return ``{lb_number: (scan_id, abs_score, abs_grade)}`` from each lb's
    own most recent scored scan.

    ``abs_score``/``abs_grade`` are feature-detected via ``PRAGMA table_info``
    (same idiom as ``backend.db._load_latest_abs_grades``) since they're added
    by Concert Ranker's ``ensure_schema`` migration, not this app's base
    schema — a DB that has never run Concert Ranker doesn't have them yet, so
    the quality-match confidence bump (TODO-210a) degrades silently to a
    no-op when they're absent.

    Unlike ``_load_latest_abs_grades`` (one global ``MAX(scan_id)`` for the
    whole library), this picks each lb_number's own newest scored scan
    independently, since different recordings can have last been scanned in
    different scan runs.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    if "abs_score" not in cols or "abs_grade" not in cols:
        return {}
    rows = conn.execute(
        "SELECT lb_number, scan_id, abs_score, abs_grade FROM quality_recording_scores "
        "WHERE abs_score IS NOT NULL AND abs_grade IS NOT NULL "
        "ORDER BY lb_number, scan_id DESC"
    ).fetchall()
    out: dict[int, tuple[int, float, str]] = {}
    for row in rows:
        lb_number = row["lb_number"]
        if lb_number not in out:
            out[lb_number] = (row["scan_id"], row["abs_score"], row["abs_grade"])
    return out


def _has_quality_match(
    lb_numbers: "list[int]",
    abs_scores_by_lb: "dict[int, tuple[int, float, str]]",
) -> bool:
    """Whether any pair of ``lb_numbers`` corroborates via matching quality scores.

    A match requires both lb_numbers' most-recent-scan rows to come from the
    SAME ``scan_id`` (``abs_score`` isn't comparable across different scan
    configs), an absolute ``abs_score`` difference within
    ``_QUALITY_MATCH_TOL``, and the same leading grade letter (e.g. "B+" and
    "B-" both match on "B"). Per TODO-210's investigation, abs_score equality
    alone is too noisy library-wide to surface brand-new families, but is a
    good corroborating signal for a family TapeMatch has already acoustically
    matched.

    Args:
        lb_numbers: A family's member lb_numbers.
        abs_scores_by_lb: Output of ``_load_latest_abs_scores``.

    Returns:
        True if any member pair matches.
    """
    present = [abs_scores_by_lb[lb] for lb in lb_numbers if lb in abs_scores_by_lb]
    for i in range(len(present)):
        scan_a, score_a, grade_a = present[i]
        for j in range(i + 1, len(present)):
            scan_b, score_b, grade_b = present[j]
            if scan_a != scan_b:
                continue
            if not grade_a or not grade_b:
                continue
            if grade_a[0] != grade_b[0]:
                continue
            if abs(score_a - score_b) <= _QUALITY_MATCH_TOL:
                return True
    return False


def _sync_one_date(
    obs_conn: sqlite3.Connection,
    conn: sqlite3.Connection,
    concert_date: str,
    run_id: str,
    stats: dict,
    abs_scores_by_lb: "dict[int, tuple[int, float, str]]",
) -> None:
    """Compute and upsert families for a single concert_date's chosen run."""
    sources = obs_conn.execute(
        "SELECT lb_number, family_id FROM sources "
        "WHERE run_id = ? AND lb_number IS NOT NULL",
        (run_id,),
    ).fetchall()

    members_by_family: dict[int, list[int]] = {}
    for row in sources:
        members_by_family.setdefault(row["family_id"], []).append(row["lb_number"])

    families = {
        fam_id: sorted(set(lbs))
        for fam_id, lbs in members_by_family.items()
        if len(set(lbs)) >= 2
    }
    # Singletons: TapeMatch processed these but found no acoustic match among
    # siblings on the same date.  Synced as label='Solo' so the Library UI
    # renders them as "Solo LB-XXXXX" rather than a raw orphan "Recording" row.
    singletons: dict[int, int] = {
        fam_id: sorted(set(lbs))[0]
        for fam_id, lbs in members_by_family.items()
        if len(set(lbs)) == 1
    }

    pair_rows = obs_conn.execute(
        "SELECT family_id_a, corr, lb_says_same FROM pairs "
        "WHERE run_id = ? AND tapematch_verdict = 'same_family' "
        "AND family_id_a = family_id_b",
        (run_id,),
    ).fetchall()
    corrs_by_family: dict[int, list[float]] = {}
    lb_says_same_by_family: dict[int, bool] = {}
    for row in pair_rows:
        fam = row["family_id_a"]
        if row["corr"] is not None:
            corrs_by_family.setdefault(fam, []).append(row["corr"])
        if row["lb_says_same"] == 1:
            lb_says_same_by_family[fam] = True

    # Label order: member_count desc, ties broken by lowest tapematch family_id.
    ordered = sorted(families.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    # The needs-review verdict lives in the batch-write analysis.md for this
    # date's chosen run, not in observations.db — applies uniformly to every
    # family on the date since the verdict judges the whole show's identity
    # picture, not one family in isolation.
    run_dir = _resolve_run_dir(obs_conn, run_id, concert_date)
    review_flag, review_reason = _read_review_flag(run_dir)

    fresh_fam_ids: set[str] = set()
    fresh_lb_numbers: set[int] = set()
    family_rows = []
    member_rows = []
    for i, (tm_family_id, lb_numbers) in enumerate(ordered):
        fam_id = f"{concert_date}#" + "-".join(str(lb) for lb in lb_numbers)
        label = f"Family {chr(ord('A') + i)}"
        corrs = corrs_by_family.get(tm_family_id, [])
        conf = sum(corrs) / len(corrs) if corrs else None
        if conf is not None and _has_quality_match(lb_numbers, abs_scores_by_lb):
            bumped = min(1.0, conf + _QUALITY_MATCH_BUMP)
            log.info(
                "tapematch sync: quality-match bump for %s (tapematch family %s): "
                "conf %.4f -> %.4f",
                fam_id, tm_family_id, conf, bumped,
            )
            conf = bumped
        by = "ai+lb" if lb_says_same_by_family.get(tm_family_id) else "ai"
        member_count = len(lb_numbers)

        fresh_fam_ids.add(fam_id)
        family_rows.append(
            (fam_id, concert_date, label, by, conf, member_count, run_id,
             review_flag, review_reason)
        )
        for lb_number in lb_numbers:
            fresh_lb_numbers.add(lb_number)
            member_rows.append((lb_number, fam_id, concert_date, run_id))

    for _tm_fam_id, lb_number in singletons.items():
        fam_id = f"{concert_date}#{lb_number}"
        fresh_fam_ids.add(fam_id)
        family_rows.append(
            (fam_id, concert_date, "Solo", "ai", None, 1, run_id,
             review_flag, review_reason)
        )
        fresh_lb_numbers.add(lb_number)
        member_rows.append((lb_number, fam_id, concert_date, run_id))

    with conn:
        conn.execute("BEGIN IMMEDIATE")
        for fam_id, c_date, label, by, conf, member_count, r_id, rev_flag, rev_reason in family_rows:
            conn.execute(
                """
                INSERT INTO tapematch_family_meta
                    (fam_id, concert_date, label, by, conf, member_count, run_id,
                     review_flag, review_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fam_id) DO UPDATE SET
                    label=excluded.label,
                    by=excluded.by,
                    conf=excluded.conf,
                    member_count=excluded.member_count,
                    run_id=excluded.run_id,
                    review_flag=excluded.review_flag,
                    review_reason=excluded.review_reason,
                    imported_at=CURRENT_TIMESTAMP
                """,
                (fam_id, c_date, label, by, conf, member_count, r_id, rev_flag, rev_reason),
            )
        for lb_number, fam_id, c_date, r_id in member_rows:
            conn.execute(
                """
                INSERT INTO recording_families
                    (lb_number, fam_id, concert_date, run_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lb_number) DO UPDATE SET
                    fam_id=excluded.fam_id,
                    concert_date=excluded.concert_date,
                    run_id=excluded.run_id,
                    imported_at=CURRENT_TIMESTAMP
                """,
                (lb_number, fam_id, c_date, r_id),
            )

        # Cleanup: drop rows for this date whose family dissolved or whose
        # membership changed (and thus produced a different fam_id).
        if fresh_fam_ids:
            placeholders = ",".join("?" * len(fresh_fam_ids))
            conn.execute(
                f"DELETE FROM tapematch_family_meta WHERE concert_date = ? "
                f"AND fam_id NOT IN ({placeholders})",
                (concert_date, *fresh_fam_ids),
            )
        else:
            conn.execute(
                "DELETE FROM tapematch_family_meta WHERE concert_date = ?",
                (concert_date,),
            )
        if fresh_lb_numbers:
            placeholders = ",".join("?" * len(fresh_lb_numbers))
            conn.execute(
                f"DELETE FROM recording_families WHERE concert_date = ? "
                f"AND lb_number NOT IN ({placeholders})",
                (concert_date, *fresh_lb_numbers),
            )
        else:
            conn.execute(
                "DELETE FROM recording_families WHERE concert_date = ?",
                (concert_date,),
            )

    stats["families_written"] += len(family_rows)
    stats["recordings_linked"] += len(member_rows)


def _clamp01(x: float) -> float:
    """Clamp ``x`` to the closed interval [0.0, 1.0]."""
    return max(0.0, min(1.0, x))


def similarity_pct(
    corr: "float | None", emb_score: "float | None", same_family: bool
) -> "int | None":
    """Map raw TapeMatch similarity signals to a presentation-friendly 0-100 %.

    Raw ``corr`` (residual cross-correlation) is not a linear "percent
    similar" — it collapses toward the noise floor for unrelated recordings,
    where e.g. 0.12 vs 0.08 is meaningless. ``emb_score`` (pretrained-embedding
    cosine similarity) tracks perceptual "sounds similar" better for
    cross-family comparisons. This applies a banded, monotone blend
    calibrated against the verdict distribution
    (instructions/FABLE_LISTENING_INSIGHT_IDEAS.md §1.2) so same-family pairs
    render ~85-100 and unrelated pairs render ~0-40, leaving the raw signals
    available separately (e.g. a tooltip) for anyone who wants them.

    Breakpoints measured 2026-07-10 from observations.db (n=10,369 pairs):
    same_family corr p50=0.108/p75=0.883, different_family corr p95=0.041,
    same_family emb p25=0.316/p95=0.987, different_family emb p50=0.208/p95=0.644.

    Args:
        corr: Residual cross-correlation (0-1), or None if not measured.
        emb_score: Pretrained-embedding cosine similarity, or None if not
            scored (addon_links rule_d abstains — see tapematch_session.py).
        same_family: Whether TapeMatch's verdict paired these two LBs as the
            same source family (``tapematch_verdict == 'same_family'``).

    Returns:
        An integer percent 0-100, or None when neither signal is available
        for a different-family pair — "not comparable", which the GUI should
        render as "n/c" rather than implying a real 0% match.
    """
    if same_family:
        corr_term = _clamp01((corr - 0.05) / 0.85) if corr is not None else 0.0
        emb_term = _clamp01((emb_score - 0.30) / 0.65) if emb_score is not None else 0.0
        return 85 + round(15 * max(corr_term, emb_term))

    if emb_score is not None:
        return round(40 * _clamp01(emb_score / 0.65))
    if corr is not None:
        return round(40 * _clamp01(corr / 0.041) * 0.5)
    return None


def sync_tapematch_pairs(
    db_path=None,
    observations_db_path: "Path | str | None" = None,
) -> dict:
    """Ingest TapeMatch pairwise similarity data into the main DB.

    Slim per-pair sync into ``tapematch_pairs`` (concert_date, lb_a, lb_b,
    corr, emb_score, fp_score, same_family, similarity_pct, run_id), mirroring
    ``sync_tapematch_families``'s latest-complete-run-per-date rule
    (``_pick_best_run``) and wholesale replace-per-date semantics — a date's
    rows are always deleted and reinserted together so they never blend two
    different tapematch runs. See
    instructions/FABLE_LISTENING_INSIGHT_IDEAS.md §1.

    Args:
        db_path: Main app DB path, or None for the default.
        observations_db_path: Path to tapematch's observations.db, or None
            for the default location under tools/tapematch/.

    Returns:
        Stats dict: ``{dates_processed, pairs_written, errors}``.
    """
    observations_db_path = observations_db_path or DEFAULT_OBSERVATIONS_DB_PATH
    if not Path(observations_db_path).exists():
        raise FileNotFoundError(f"observations.db not found: {observations_db_path}")

    # Standalone CLI runs never go through app.py's startup init_db() call —
    # see sync_tapematch_families's docstring for the same rationale.
    init_db(db_path)

    obs_conn = _open_observations_db(observations_db_path)
    conn = get_connection(db_path)

    stats = {
        "dates_processed": 0,
        "pairs_written": 0,
        "errors": [],
    }

    try:
        best_run_by_date = _pick_best_run(obs_conn)

        for concert_date, run_id in best_run_by_date.items():
            try:
                _sync_pairs_for_date(obs_conn, conn, concert_date, run_id, stats)
                stats["dates_processed"] += 1
            except Exception as e:  # noqa: BLE001 — one bad date shouldn't abort the rest
                log.exception(
                    "tapematch pairs sync failed for %s (run %s)", concert_date, run_id
                )
                stats["errors"].append(f"{concert_date} ({run_id}): {e}")
    finally:
        obs_conn.close()

    return stats


def _sync_pairs_for_date(
    obs_conn: sqlite3.Connection,
    conn: sqlite3.Connection,
    concert_date: str,
    run_id: str,
    stats: dict,
) -> None:
    """Compute and wholesale-replace pairwise rows for one date's chosen run."""
    rows = obs_conn.execute(
        "SELECT lb_a, lb_b, corr, emb_score, fp_score, tapematch_verdict "
        "FROM pairs WHERE run_id = ? AND lb_a IS NOT NULL AND lb_b IS NOT NULL",
        (run_id,),
    ).fetchall()

    # Key on the normalised (lb_a, lb_b) pair so a source-data duplicate can
    # never collide with tapematch_pairs' PK during insert.
    pairs_by_key: dict[tuple[int, int], tuple] = {}
    for row in rows:
        lb_a, lb_b = row["lb_a"], row["lb_b"]
        if lb_a == lb_b:
            continue
        if lb_a > lb_b:
            lb_a, lb_b = lb_b, lb_a
        same_family = row["tapematch_verdict"] == "same_family"
        pct = similarity_pct(row["corr"], row["emb_score"], same_family)
        pairs_by_key[(lb_a, lb_b)] = (
            concert_date, lb_a, lb_b, row["corr"], row["emb_score"], row["fp_score"],
            int(same_family), pct, run_id,
        )

    pair_rows = list(pairs_by_key.values())

    with conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM tapematch_pairs WHERE concert_date = ?", (concert_date,))
        conn.executemany(
            """
            INSERT INTO tapematch_pairs
                (concert_date, lb_a, lb_b, corr, emb_score, fp_score, same_family,
                 similarity_pct, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pair_rows,
        )

    stats["pairs_written"] += len(pair_rows)


def duplicate_encode_candidates(conn: sqlite3.Connection) -> "list[dict]":
    """Surface same-date recording pairs with byte-identical quality metrics.

    Read-only signal for TODO-210(b): two distinct ``lb_number``s scored in
    the SAME ``quality_recording_metrics.scan_id`` whose ``metric_json`` is a
    byte-for-byte match are near-certainly the same underlying tape with only
    a track-split difference (per TODO-210's investigation, full metric_json
    identity is near-collision-free within one scan config, unlike abs_score
    equality alone, which is too noisy library-wide). Grouped by
    ``entries.date_str`` (the show date as scraped) rather than TapeMatch's
    normalised ``concert_date`` — most of these candidates predate or fall
    outside TapeMatch's clustering coverage entirely (never appear in
    ``recording_families``) and would otherwise be silently dropped by
    joining through it. This function never writes anything; it is purely a
    curation lead for a human to review, never an auto-merge.

    Args:
        conn: Open connection to the main app DB.

    Returns:
        List of dicts sorted by date then lb_a/lb_b, each:
        ``{"date", "lb_a", "lb_b", "scan_id", "same_family", "reason"}``.
        ``same_family`` is True only when both lb_numbers already share a
        ``recording_families.fam_id`` — i.e. this is corroboration of an
        already-known family, not a new lead.
    """
    rows = conn.execute(
        "SELECT e.lb_number AS lb_number, e.date_str AS date_str, "
        "m.scan_id AS scan_id, m.metric_json AS metric_json "
        "FROM quality_recording_metrics m "
        "JOIN entries e ON e.lb_number = m.lb_number "
        "WHERE e.date_str IS NOT NULL AND e.date_str != ''"
    ).fetchall()

    groups: dict[tuple[str, int, str], list[int]] = {}
    for row in rows:
        key = (row["date_str"], row["scan_id"], row["metric_json"])
        groups.setdefault(key, []).append(row["lb_number"])

    fam_by_lb = {
        r["lb_number"]: r["fam_id"]
        for r in conn.execute("SELECT lb_number, fam_id FROM recording_families")
    }

    candidates: list[dict] = []
    for (date_str, scan_id, _metric_json), lb_numbers in groups.items():
        distinct = sorted(set(lb_numbers))
        if len(distinct) < 2:
            continue
        for i in range(len(distinct)):
            for j in range(i + 1, len(distinct)):
                lb_a, lb_b = distinct[i], distinct[j]
                same_family = (
                    fam_by_lb.get(lb_a) is not None
                    and fam_by_lb.get(lb_a) == fam_by_lb.get(lb_b)
                )
                candidates.append(
                    {
                        "date": date_str,
                        "lb_a": lb_a,
                        "lb_b": lb_b,
                        "scan_id": scan_id,
                        "same_family": same_family,
                        "reason": "likely duplicate encode",
                    }
                )

    candidates.sort(key=lambda c: (c["date"], c["lb_a"], c["lb_b"]))
    return candidates


def _main() -> int:
    """CLI entry point: `.venv/bin/python3 -m backend.tapematch_sync`.

    Runs standalone, without the Flask backend — tapematch batch runs happen
    via shell scripts and may not have the app server up. Syncs families
    then pairs, same combined order as the POST /api/tapematch/sync route.
    Pass ``--dup-encodes`` to instead print TODO-210(b)'s duplicate-encode
    candidates (one per line) and skip the sync entirely.
    """
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dup-encodes",
        action="store_true",
        help="Print likely-duplicate-encode candidates (TODO-210b) and exit.",
    )
    args = parser.parse_args()

    if args.dup_encodes:
        conn = get_connection()
        candidates = duplicate_encode_candidates(conn)
        for c in candidates:
            print(
                f"{c['date']} LB-{c['lb_a']} / LB-{c['lb_b']} "
                f"(scan_id={c['scan_id']}, same_family={c['same_family']}): {c['reason']}"
            )
        return 0

    stats = sync_tapematch_families()
    pair_stats = sync_tapematch_pairs()
    stats["pairs_synced"] = pair_stats["pairs_written"]
    stats["pair_dates"] = pair_stats["dates_processed"]
    stats["errors"] = [*stats["errors"], *pair_stats["errors"]]
    print(json.dumps(stats, indent=2))
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())
