"""TapeMatch families/pairs/runs/dates/crawl, A/B clip, bobtalk and Library performance/badge
routes (TODO-369)."""

import logging
import os
import re
import sqlite3
from datetime import UTC
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    send_from_directory,
)

from backend import db as database
from backend.paths import TAPEMATCH_DB_PATH, TAPEMATCH_RUNS_DIR

_log = logging.getLogger(__name__)

bp = Blueprint("tapematch", __name__)


# TODO-215 sub-feature 1 (curator match feedback): authoritative human_judgment
# vocabulary for tools/tapematch/observations.db's pairs table. regression.py
# reads confirmed_same/confirmed_different as calibration truth — do not change.
_TAPEMATCH_JUDGMENTS = frozenset(
    {"confirmed_same", "confirmed_different", "uncertain", "lb_wrong"}
)

# Columns GET /api/tapematch/pairs copies from observations.db's pairs table
# onto each returned pair. Every one of them post-dates that table's first
# schema, so the route probes for them with PRAGMA table_info and nulls only
# the absent ones — a hard SELECT would raise on an older DB and collapse the
# whole enrichment (judgments included) to nulls.
_PAIR_ENRICH_COLS = (
    "human_judgment", "human_notes", "lb_says_same", "lb_relation_text",
    "windowed_frac", "hiss_median",
)

# observations.db ``sources`` columns GET /api/tapematch/sources returns
# alongside lb_number, for the curation screen's speed & lag strip (README §6).
# Probed the same way as _PAIR_ENRICH_COLS: speed_ppm/speed_kind and the lag
# columns all post-date the first sources schema.
_SOURCE_SPEED_COLS = (
    "speed_kind", "speed_ppm", "family_id", "folder_name", "lag_ref_lb",
)

# observations.db ``runs`` columns GET /api/tapematch/runs returns per run, and
# GET /api/tapematch/run_snapshot echoes for the run it snapshots (curation
# §12's run pickers + run bar). Probed with PRAGMA table_info like the two sets
# above — n_families and duration_sec post-date the first runs schema.
_RUN_LIST_COLS = (
    "run_at", "n_sources_db", "n_sources_found", "n_sources_ran", "n_families",
    "duration_sec",
)

# The two per-run tables GET /api/tapematch/run_snapshot returns for the §12
# diff. Deliberately narrower than the tables themselves: the diff reads
# family membership, the three evidence values §12.3/§12.4 chart, the run's own
# call, and the pair's human judgment — not the 20-odd lineage/format columns,
# which no section of the diff renders.
_SNAPSHOT_SOURCE_COLS = ("family_id", "folder_name", "speed_kind", "speed_ppm")
_SNAPSHOT_PAIR_COLS = (
    "corr", "emb_score", "windowed_frac", "hiss_median", "fp_score",
    "family_id_a", "family_id_b", "tapematch_verdict", "human_judgment",
)


def get_tapematch_crawl_status() -> dict:
    """Read-only status for the detached TapeMatch library crawl.

    Module-level helper (TODO-262) so ``backend/activity.py`` can read this
    worker's status without app.py depending on it — mirrors the
    ``/api/tapematch/crawl/status`` route body. Replicates
    ``tools/tapematch/crawl_status.sh``: is run_crawl.sh running (via pgrep,
    no shell=True), how many run dirs exist on disk / how many distinct
    dates they cover, and the crawl log's last 5 lines. No start/stop here —
    this is observation only.

    Returns:
        Dict with keys: running (bool), pid (int|None), runs_on_disk (int),
        distinct_dates (int), log_tail (list[str]). On failure, a dict with
        an "error" key instead (the route maps that to a 500).
    """
    import subprocess

    try:
        pid = None
        try:
            proc = subprocess.run(
                ["pgrep", "-o", "-f", "run_crawl.sh"],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                pid = int(proc.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pid = None

        runs_dir = TAPEMATCH_RUNS_DIR
        dir_names = (
            [d.name for d in runs_dir.iterdir() if d.is_dir()]
            if runs_dir.exists() else []
        )
        runs_on_disk = len(dir_names)
        date_re = re.compile(r"(\d{4}-\d{2}-\d{2})$")
        distinct_dates = len(
            {m.group(1) for name in dir_names if (m := date_re.search(name))}
        )

        log_path = runs_dir.parent / "crawl.log"
        log_tail: list = []
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                log_tail = lines[-5:]
            except OSError:
                log_tail = []

        return {
            "running": pid is not None,
            "pid": pid,
            "runs_on_disk": runs_on_disk,
            "distinct_dates": distinct_dates,
            "log_tail": log_tail,
        }
    except Exception as exc:
        _log.exception("tapematch_crawl_status failed")
        return {"error": "internal_error", "message": str(exc)}


@bp.route("/api/tapematch/families", methods=["GET"])
def tapematch_families() -> Response:
    """Flat list of recordings with their TapeMatch family assignment.

    No pagination — a couple thousand rows max at full catalog scale.
    Merge client-side by lb_number; not joined into /api/search.

    TODO-333(4): also carries each family's calibration provenance —
    ``calibration_hash`` (which tapematch calibration produced this
    family's verdict, from ``tapematch_family_meta``, via
    ``tools/tapematch/tapematch/calibration.py``) and
    ``current_calibration_hash``, the hash of the *shipped* config.yaml
    right now, computed server-side once per request so the client can
    flag a family's ``calibration_hash`` stale without duplicating the
    hashing rules; None when it couldn't be computed (missing/unparseable
    config.yaml).

    TODO-295: also carries the machine triage (``auto_triage``/
    ``auto_triage_reasons``, from ``backend.tapematch_autoflag`` — see
    its module docstring for why it is kept subordinate to
    ``fam_needs_review`` in the GUI).
    """
    from backend import tapematch_sync as _tapematch_sync

    conn = database.get_connection()
    rows = conn.execute(
        """
            SELECT rf.lb_number, rf.fam_id, rf.concert_date,
                   COALESCE(m.label_override, m.label) AS fam_label,
                   m.conf AS fam_conf, m.by AS fam_by,
                   m.review_flag AS fam_needs_review, m.review_reason AS fam_review_reason,
                   m.auto_triage AS fam_auto_triage,
                   m.auto_triage_reasons AS fam_auto_triage_reasons,
                   m.calibration_hash AS fam_calibration_hash
            FROM recording_families rf
            JOIN tapematch_family_meta m ON m.fam_id = rf.fam_id
            """
    ).fetchall()
    current_hash = _tapematch_sync.current_calibration_hash()
    out = []
    for r in rows:
        d = dict(r)
        d["current_calibration_hash"] = current_hash
        out.append(d)
    return jsonify(out)


@bp.route("/api/tapematch/rarity", methods=["GET"])
def tapematch_rarity() -> Response:
    """Per-LB source-tape copy count + "only known copy" flag (TODO-335).

    Read-only, over the synced ``recording_families``; see
    ``backend.rarity`` for the over-merge and unanalysed-sibling caveats
    each row carries (``unanalysed_on_date``). Same flat-list shape as
    /api/tapematch/families — merge client-side by ``lb_number``.
    """
    from backend import rarity as _rarity

    try:
        return jsonify(_rarity.lb_rarity(database.get_connection()))
    except Exception as exc:
        _log.exception("tapematch_rarity failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/dup_encodes", methods=["GET"])
def tapematch_dup_encodes() -> Response:
    """Likely-duplicate-encode candidates (TODO-210b).

    Read-only curation leads — same-date recording pairs whose
    ``quality_recording_metrics.metric_json`` is byte-identical within
    one scan_id. Never auto-merges or mutates any family data; see
    ``backend.tapematch_sync.duplicate_encode_candidates`` for the full
    signal rationale.
    """
    from backend import tapematch_sync as _tapematch_sync

    try:
        conn = database.get_connection()
        candidates = _tapematch_sync.duplicate_encode_candidates(conn)
        return jsonify({"candidates": candidates})
    except Exception as exc:
        _log.exception("tapematch_dup_encodes failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/pairs", methods=["GET"])
def tapematch_pairs_for_date() -> Response:
    """Pairwise similarity matrix for one concert date (LISTENING §1).

    Query param: date=YYYY-MM-DD (required). 200 with pairs: [] when the
    date has no synced tapematch_pairs rows — an un-synced or unknown
    date is not an error, same style as /api/tapematch/families.

    Each pair is enriched with ``human_judgment``/``human_notes`` read
    LIVE from observations.db's ``pairs`` table (TODO-215 sub-feature 1:
    curator match feedback) so the matrix reflects edits made moments
    ago without waiting for a sync. ``ab_eligible`` (TODO-231) is
    computed per pair via ``ab_clips.get_pair_source_info`` — each
    pair's own latest common tapematch run, not the (possibly stale)
    run_id synced into ``tapematch_pairs`` — so it always agrees with
    what POST /api/ab_clip will actually accept. Enrichment is
    best-effort: if observations.db is missing, locked, or errors,
    every pair falls back to ``human_judgment``/``human_notes`` = null
    and ``ab_eligible`` = null rather than failing the whole request.

    The same live read also carries ``lb_says_same``/``lb_relation_text``
    (the LB page's own claim about the pair) and the two secondary-evidence
    metrics ``windowed_frac``/``hiss_median``. None of these are in the app
    DB's ``tapematch_pairs``: the curation matrix's conflict marker
    (README §5) is ``lb_says_same and not same_family``, so it needs the
    claim alongside the algorithm's verdict, and the curation dossier's
    evidence bars (README §8d) show windowed coverage and quiet-segment
    hiss correlation against their thresholds. Null on enrichment failure,
    like the rest.

    Every enriched column post-dates observations.db's first schema, so
    the whole set (``_PAIR_ENRICH_COLS``) is probed with ``PRAGMA
    table_info`` — an older DB yields nulls for exactly the columns it
    lacks, rather than throwing and collapsing the whole enrichment block
    (``ab_eligible`` included) to nulls.
    """
    from backend import ab_clips as _ab_clips
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    if not concert_date:
        return jsonify({"error": "missing_date"}), 400
    try:
        conn = database.get_connection()
        rows = conn.execute(
            """
                SELECT lb_a, lb_b, corr, emb_score, fp_score, same_family,
                       similarity_pct, run_id
                FROM tapematch_pairs
                WHERE concert_date = ?
                ORDER BY lb_a, lb_b
                """,
            (concert_date,),
        ).fetchall()
        run_id = rows[0]["run_id"] if rows else None
        pairs = [
            {
                "lb_a": r["lb_a"],
                "lb_b": r["lb_b"],
                "corr": r["corr"],
                "emb_score": r["emb_score"],
                "fp_score": r["fp_score"],
                "same_family": bool(r["same_family"]),
                "similarity_pct": r["similarity_pct"],
                "human_judgment": None,
                "human_notes": None,
                "ab_eligible": None,
                "lb_says_same": None,
                "lb_relation_text": None,
                "windowed_frac": None,
                "hiss_median": None,
            }
            for r in rows
        ]

        try:
            obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
            if pairs and Path(obs_path).exists():
                obs_conn = _tapematch_sync._open_observations_db(obs_path)
                try:
                    obs_cols = {
                        c["name"] for c in obs_conn.execute("PRAGMA table_info(pairs)")
                    }
                    opt_cols = [c for c in _PAIR_ENRICH_COLS if c in obs_cols]
                    feedback: dict[tuple[int, int], dict] = {}
                    for r in obs_conn.execute(
                        """
                            SELECT lb_a, lb_b{extra}
                            FROM pairs
                            WHERE concert_date = ? AND run_id = ?
                              AND lb_a IS NOT NULL AND lb_b IS NOT NULL
                            """.format(
                            extra="".join(f", {c}" for c in opt_cols)
                        ),
                        (concert_date, run_id),
                    ):
                        key = tuple(sorted((r["lb_a"], r["lb_b"])))
                        row = {c: r[c] for c in opt_cols}
                        if row.get("lb_says_same") is not None:
                            row["lb_says_same"] = bool(row["lb_says_same"])
                        feedback[key] = row
                    # Per-pair, not a single global eligible_lb_set(): an LB's
                    # speed_kind can differ across tapematch runs (e.g. a
                    # staircase-relaxed rerun after the last synced run), and
                    # eligibility requires both members' rows to come from the
                    # SAME run — exactly what generate_ab_clips checks via
                    # get_pair_source_info. Using the synced tapematch_pairs
                    # run_id here (rather than each pair's latest common run)
                    # under-reports eligibility once a newer un-synced run
                    # exists in observations.db.
                    ab_eligible: dict[tuple[int, int], bool] = {}
                    for pair in pairs:
                        key = tuple(sorted((pair["lb_a"], pair["lb_b"])))
                        if key in ab_eligible:
                            continue
                        pair_info = _ab_clips.get_pair_source_info(
                            obs_conn, concert_date, pair["lb_a"], pair["lb_b"]
                        )
                        ab_eligible[key] = bool(pair_info) and (
                            _ab_clips.is_run_eligible(pair_info[0]["run_id"])
                            and _ab_clips.is_eligible_speed(pair_info[0]["speed_kind"])
                            and _ab_clips.is_eligible_speed(pair_info[1]["speed_kind"])
                        )
                finally:
                    obs_conn.close()
                for pair in pairs:
                    key = tuple(sorted((pair["lb_a"], pair["lb_b"])))
                    row = feedback.get(key, {})
                    for col in _PAIR_ENRICH_COLS:
                        pair[col] = row.get(col)
                    pair["ab_eligible"] = ab_eligible.get(key, False)
        except Exception:
            _log.warning(
                "tapematch_pairs_for_date: human feedback enrichment failed "
                    "for date=%s; leaving human_judgment/human_notes null",
                concert_date, exc_info=True,
            )

        return jsonify({"date": concert_date, "run_id": run_id, "pairs": pairs})
    except Exception as exc:
        _log.exception("tapematch_pairs_for_date failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/sources", methods=["GET"])
def tapematch_sources_for_date() -> Response:
    """Per-recording speed/lag facts for one concert date (README §6).

    Query param: date=YYYY-MM-DD (required). The curation screen's speed &
    lag strip plots every recording on a ppm axis, which is source-shaped
    data (``observations.db``'s ``sources`` table) rather than the
    pair-shaped data /api/tapematch/pairs returns — hence its own route.
    It is also the only tapematch view that has something to show on a
    single-recording date, where there are no pairs at all.

    Rows come from the LATEST run that has sources for the date, matching
    :func:`ab_clips.get_source_info`'s ``ORDER BY run_id DESC`` rather than
    the (possibly stale) run_id synced into ``tapematch_pairs``: a rerun
    can change a source's ``speed_kind``, and the strip should show what
    the current analysis believes.

    ``speed_ppm``/``speed_kind`` are probed with ``PRAGMA table_info`` —
    an observations.db predating either column yields nulls for it instead
    of failing the request. A missing/locked DB, or a date with no run,
    returns ``sources: []`` with a null ``run_id``; an un-analysed date is
    not an error.

    Returns:
        200 ``{date, run_id, sources: [{lb_number, speed_kind, speed_ppm,
        family_id, folder_name, lag_ref_lb}]}``; 400 when date is missing;
        500 on unexpected failure.
    """
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    if not concert_date:
        return jsonify({"error": "missing_date"}), 400
    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify({"date": concert_date, "run_id": None, "sources": []})
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            cols = {c["name"] for c in obs_conn.execute("PRAGMA table_info(sources)")}
            opt = [c for c in _SOURCE_SPEED_COLS if c in cols]
            run_row = obs_conn.execute(
                "SELECT MAX(run_id) AS run_id FROM sources WHERE concert_date = ?",
                (concert_date,),
            ).fetchone()
            run_id = run_row["run_id"] if run_row else None
            if not run_id:
                return jsonify(
                    {"date": concert_date, "run_id": None, "sources": []}
                )
            rows = obs_conn.execute(
                """
                    SELECT lb_number{extra}
                    FROM sources
                    WHERE concert_date = ? AND run_id = ? AND lb_number IS NOT NULL
                    ORDER BY lb_number
                    """.format(extra="".join(f", {c}" for c in opt)),
                (concert_date, run_id),
            ).fetchall()
        finally:
            obs_conn.close()
        sources = [
            {"lb_number": r["lb_number"]}
            | {c: (r[c] if c in opt else None) for c in _SOURCE_SPEED_COLS}
            for r in rows
        ]
        return jsonify({"date": concert_date, "run_id": run_id, "sources": sources})
    except Exception as exc:
        # A locked observations.db (mid-run) raises RuntimeError from
        # _open_observations_db. The strip degrades to its empty state
        # rather than breaking the whole curation screen.
        _log.warning(
            "tapematch_sources_for_date: could not read sources for date=%s",
            concert_date, exc_info=True,
        )
        if isinstance(exc, RuntimeError):
            return jsonify({"date": concert_date, "run_id": None, "sources": []})
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/runs", methods=["GET"])
def tapematch_runs_for_date() -> Response:
    """Every TapeMatch run recorded for one concert date (curation §12).

    Query param: date=YYYY-MM-DD (required). Newest first, straight off
    ``observations.db``'s ``runs`` table — the run-diff view's two pickers
    need the whole list (1989-06-04 has 17 runs), not just the best one
    ``_pick_best_run`` would choose.

    Returns:
        200 ``{date, runs: [{run_id, run_at, n_sources_db, n_sources_found,
        n_sources_ran, n_families, duration_sec}]}``; ``runs: []`` for an
        unknown date or an absent/locked DB (not an error); 400 when date
        is missing.
    """
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    if not concert_date:
        return jsonify({"error": "missing_date"}), 400
    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify({"date": concert_date, "runs": []})
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            cols = {c["name"] for c in obs_conn.execute("PRAGMA table_info(runs)")}
            opt = [c for c in _RUN_LIST_COLS if c in cols]
            rows = obs_conn.execute(
                """
                    SELECT run_id{extra}
                    FROM runs
                    WHERE concert_date = ?
                    ORDER BY run_id DESC
                    """.format(extra="".join(f", {c}" for c in opt)),
                (concert_date,),
            ).fetchall()
        finally:
            obs_conn.close()
        runs = [
            {"run_id": r["run_id"]}
            | {c: (r[c] if c in opt else None) for c in _RUN_LIST_COLS}
            for r in rows
        ]
        return jsonify({"date": concert_date, "runs": runs})
    except RuntimeError:
        # Locked mid-run — the picker degrades to empty, same as §6's strip.
        _log.warning("tapematch_runs_for_date: observations.db locked (date=%s)",
                     concert_date)
        return jsonify({"date": concert_date, "runs": []})
    except Exception as exc:
        _log.exception("tapematch_runs_for_date failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/run_snapshot", methods=["GET"])
def tapematch_run_snapshot() -> Response:
    """One run's own pairs + sources, for the §12 run diff.

    Query params: date=YYYY-MM-DD and run_id (both required). The diff
    itself is a pure function of two of these snapshots and is computed in
    the renderer (README §12 "diffing is computed client-side; neither run
    is mutated by viewing") — this route only reads.

    ``human_judgment`` rides along on the pairs even though it belongs to
    the pair rather than to the run: §12's last section reconciles the
    curator's judgments against the two runs' calls, and it is the same
    column /api/tapematch/pairs already returns.

    Returns:
        200 ``{date, run_id, run: {...}|null, sources: [...], pairs: [...]}``;
        400 when a param is missing; ``run`` null with empty lists for an
        unknown run or an absent/locked DB.
    """
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    run_id = request.args.get("run_id")
    if not concert_date or not run_id:
        return jsonify({"error": "missing_fields"}), 400
    empty = {"date": concert_date, "run_id": run_id, "run": None,
             "sources": [], "pairs": []}
    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify(empty)
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            run_cols = {c["name"] for c in obs_conn.execute("PRAGMA table_info(runs)")}
            run_opt = [c for c in _RUN_LIST_COLS if c in run_cols]
            run_row = obs_conn.execute(
                "SELECT run_id{extra} FROM runs WHERE run_id = ? AND concert_date = ?"
                .format(extra="".join(f", {c}" for c in run_opt)),
                (run_id, concert_date),
            ).fetchone()
            if run_row is None:
                return jsonify(empty)
            run = (
                {"run_id": run_row["run_id"]}
                | {c: (run_row[c] if c in run_opt else None) for c in _RUN_LIST_COLS}
            )

            src_cols = {c["name"] for c in obs_conn.execute("PRAGMA table_info(sources)")}
            src_opt = [c for c in _SNAPSHOT_SOURCE_COLS if c in src_cols]
            src_rows = obs_conn.execute(
                """
                    SELECT lb_number{extra}
                    FROM sources
                    WHERE run_id = ? AND concert_date = ? AND lb_number IS NOT NULL
                    ORDER BY lb_number
                    """.format(extra="".join(f", {c}" for c in src_opt)),
                (run_id, concert_date),
            ).fetchall()

            pair_cols = {c["name"] for c in obs_conn.execute("PRAGMA table_info(pairs)")}
            pair_opt = [c for c in _SNAPSHOT_PAIR_COLS if c in pair_cols]
            pair_rows = obs_conn.execute(
                """
                    SELECT lb_a, lb_b{extra}
                    FROM pairs
                    WHERE run_id = ? AND concert_date = ?
                    ORDER BY lb_a, lb_b
                    """.format(extra="".join(f", {c}" for c in pair_opt)),
                (run_id, concert_date),
            ).fetchall()
        finally:
            obs_conn.close()

        sources = [
            {"lb_number": r["lb_number"]}
            | {c: (r[c] if c in src_opt else None) for c in _SNAPSHOT_SOURCE_COLS}
            for r in src_rows
        ]
        pairs = [
            {"lb_a": r["lb_a"], "lb_b": r["lb_b"]}
            | {c: (r[c] if c in pair_opt else None) for c in _SNAPSHOT_PAIR_COLS}
            for r in pair_rows
        ]
        return jsonify({"date": concert_date, "run_id": run_id, "run": run,
                        "sources": sources, "pairs": pairs})
    except RuntimeError:
        _log.warning("tapematch_run_snapshot: observations.db locked (run=%s)", run_id)
        return jsonify(empty)
    except Exception as exc:
        _log.exception("tapematch_run_snapshot failed for run=%s", run_id)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/ab_clip", methods=["POST"])
def ab_clip_create() -> Response:
    """Build two performance-time-aligned A/B clips for a TapeMatch pair.

    LISTENING §2 (TODO-231 + TODO-233): both sources must have an eligible
    ``speed_kind`` (``reference``/``aligned``, or ``constant-speed-offset``
    which is resampled to reference speed) from a run on/after the
    2026-07-06 confidence gate. JSON body::

        {"date": "YYYY-MM-DD", "lb_a": int, "lb_b": int,
         "t_sec": float (>=0, optional), "dur_sec": int (5..60, default 20)}

    ``t_sec`` is optional (TODO-232 part 2): when omitted, the backend
    auto-picks a quiet-vocal-passage start point (:func:`ab_clips.
    auto_pick_t_sec`) and returns the picked value in the response's
    ``t_sec`` field so the caller can display/override it.

    Resolves each LB's folder via ``my_collection.disk_path``, maps the
    performance time to each source's local audio offset via
    ``trim_head_sec`` (from observations.db), extracts WAV clips into
    ``data/ab_clips/`` and returns their ``/api/ab_clip/<name>`` URLs.

    Returns:
        200 with clip URLs and the resolved ``t_sec``; 400 for bad
        params/position; 409 ``not_eligible`` (wrong speed_kind) or
        ``locked`` (observations.db busy); 404 ``pair_not_found``
        (unknown pair/date) or ``folder_missing`` (unresolvable/unmounted
        disk path).
    """
    from backend import ab_clips as _ab_clips
    from backend import tapematch_sync as _tapematch_sync

    body = request.get_json(force=True) or {}
    concert_date = body.get("date")
    lb_a = body.get("lb_a")
    lb_b = body.get("lb_b")
    t_sec = body.get("t_sec")
    if not concert_date or lb_a is None or lb_b is None:
        return jsonify({"error": "missing_fields"}), 400
    t_val: float | None = None
    if t_sec is not None:
        try:
            t_val = float(t_sec)
        except (TypeError, ValueError):
            return jsonify({"error": "bad_t_sec"}), 400
    dur_val = _ab_clips.clamp_dur(body.get("dur_sec"))

    try:
        conn = database.get_connection()
        result = _ab_clips.generate_ab_clips(
            conn, _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH,
            concert_date, int(lb_a), int(lb_b), t_val, dur_val,
        )
        return jsonify(result)
    except _ab_clips.AbClipError as exc:
        return jsonify(exc.payload), exc.status
    except Exception as exc:
        _log.exception("ab_clip_create failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/ab_clip/<path:filename>", methods=["GET"])
def ab_clip_serve(filename: str) -> Response:
    """Serve a cached A/B WAV clip from ``data/ab_clips/`` (TODO-231).

    ``send_from_directory`` rejects path-traversal, so only files inside
    the cache directory are reachable. 404 if the named clip is absent
    (e.g. pruned from the LRU cache).
    """
    from werkzeug.exceptions import NotFound

    from backend import ab_clips as _ab_clips

    try:
        return send_from_directory(
            str(_ab_clips.AB_CLIPS_DIR), filename,
            mimetype="audio/wav", conditional=True,
        )
    except NotFound:
        return jsonify({"error": "clip_not_found"}), 404


@bp.route("/api/bobtalk/<int:lb>", methods=["GET"])
def bobtalk_locations(lb: int) -> Response:
    """Return Olof's bobtalk quotes located inside one recording (TODO-303).

    Query params:
        all: ``1`` to include low-confidence matches. They are excluded by
            default — an unresolved match must degrade to "no play button",
            never to a play button that jumps to the wrong moment.

    Returns:
        ``{"lb": <n>, "locations": [{quote_index, text, t_start, dice,
        runner_up, confident}, ...]}`` ordered by timestamp.
    """
    from backend import bobtalk as _bobtalk

    include_all = request.args.get("all") in ("1", "true", "yes")
    try:
        conn = database.get_connection()
        rows = _bobtalk.get_locations(conn, lb, confident_only=not include_all)
        return jsonify({"lb": lb, "locations": rows})
    except Exception as exc:
        _log.exception("bobtalk_locations failed for lb=%s", lb)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/bobtalk/clip", methods=["POST"])
def bobtalk_clip() -> Response:
    """Build a playable clip at a located bobtalk quote (TODO-303).

    Body:
        ``lb``: LB number of the recording.
        ``t_start``: source-local offset in seconds, from a location row.
        ``dur_sec``: optional clip length (defaults to 30).

    Returns:
        ``{"filename": ..., "url": "/api/ab_clip/<filename>"}``, reusing the
        existing A/B clip cache and its range-capable serving route.
    """
    from backend import bobtalk as _bobtalk

    body = request.get_json(force=True) or {}
    lb = body.get("lb")
    t_start = body.get("t_start")
    if lb is None or t_start is None:
        return jsonify({"error": "missing_fields"}), 400
    try:
        t_val = float(t_start)
        dur = int(body.get("dur_sec") or 30)
    except (TypeError, ValueError):
        return jsonify({"error": "bad_params"}), 400

    try:
        conn = database.get_connection()
        from backend import ab_clips as _ab

        disk_path = _ab.resolve_disk_path(conn, int(lb))
        if not disk_path or not os.path.isdir(disk_path):
            return jsonify({"error": "folder_missing"}), 404
        name = _bobtalk.build_quote_clip(disk_path, t_val, dur)
        return jsonify({"filename": name, "url": f"/api/ab_clip/{name}"})
    except ValueError as exc:
        return jsonify({"error": "bad_position", "message": str(exc)}), 400
    except Exception as exc:
        _log.exception("bobtalk_clip failed for lb=%s t=%s", lb, t_start)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/pairs/judgment", methods=["POST"])
def tapematch_pairs_judgment() -> Response:
    """Write a curator's human judgment/notes for one TapeMatch pair.

    TODO-215 sub-feature 1 (curator match feedback). JSON body::

        {"date": "YYYY-MM-DD", "lb_a": int, "lb_b": int,
         "run_id": str (optional), "judgment": str | null,
         "notes": str | null (optional)}

    ``judgment`` must be one of ``confirmed_same``, ``confirmed_different``,
    ``uncertain``, ``lb_wrong``, or null/absent to clear it. This
    vocabulary is authoritative — tools/tapematch/regression.py reads
    ``confirmed_same``/``confirmed_different`` as calibration truth.

    Writes straight to tools/tapematch/observations.db's ``pairs`` table
    (read-write, unlike the read-only helper used elsewhere in this
    file), matching on run_id + concert_date + either lb ordering.

    Returns:
        200 ``{"ok": true, "rows_updated": n, "judgment": ..., "notes": ...}``
        on success; 400 ``bad_judgment``/``missing_fields``; 404
        ``no_run``/``pair_not_found``; 409 ``locked`` if observations.db
        is write-locked by an in-progress tapematch run.
    """
    from backend import tapematch_sync as _tapematch_sync

    body = request.get_json(force=True) or {}
    concert_date = body.get("date")
    lb_a = body.get("lb_a")
    lb_b = body.get("lb_b")
    run_id = body.get("run_id")
    judgment = body.get("judgment")
    notes = body.get("notes")

    if not concert_date or lb_a is None or lb_b is None:
        return jsonify({"error": "missing_fields"}), 400
    if judgment is not None and judgment not in _TAPEMATCH_JUDGMENTS:
        return jsonify({"error": "bad_judgment"}), 400

    try:
        if not run_id:
            obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
            if not Path(obs_path).exists():
                return jsonify({"error": "no_run"}), 404
            obs_conn_ro = _tapematch_sync._open_observations_db(obs_path)
            try:
                run_id = _tapematch_sync._pick_best_run(obs_conn_ro).get(concert_date)
            finally:
                obs_conn_ro.close()
            if run_id is None:
                return jsonify({"error": "no_run"}), 404

        conn = sqlite3.connect(str(TAPEMATCH_DB_PATH))
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                    UPDATE pairs
                    SET human_judgment = ?, human_notes = ?
                    WHERE run_id = ? AND concert_date = ?
                      AND ((lb_a = ? AND lb_b = ?) OR (lb_a = ? AND lb_b = ?))
                    """,
                (judgment, notes, run_id, concert_date, lb_a, lb_b, lb_b, lb_a),
            )
            rows_updated = cur.rowcount
            if rows_updated == 0:
                conn.rollback()
                return jsonify({"error": "pair_not_found"}), 404
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            msg = str(exc)
            if "locked" in msg.lower() or "busy" in msg.lower():
                return jsonify({"error": "locked", "message": msg}), 409
            raise
        finally:
            conn.close()

        return jsonify(
            {
                "ok": True,
                "rows_updated": rows_updated,
                "judgment": judgment,
                "notes": notes,
            }
        )
    except RuntimeError as exc:
        # _open_observations_db (run_id resolution) raises RuntimeError when
        # observations.db stays locked past its retry budget — same 409
        # shape as /api/tapematch/analysis.
        return jsonify({"error": "locked", "message": str(exc)}), 409
    except Exception as exc:
        _log.exception(
            "tapematch_pairs_judgment failed for date=%s lb_a=%s lb_b=%s",
            concert_date, lb_a, lb_b,
        )
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/dates/accept", methods=["POST"])
def tapematch_accept_families() -> Response:
    """Record a curator's acceptance of one date's TapeMatch families.

    Curation screen §3 ``Accept families`` (design handoff Q4): the record
    of a curator having signed off on one date's families, which gives the
    triage rail's fourth state (``curated``) its only path in.

    The record lands in the **app DB**'s ``tapematch_date_curation``
    (USER table), not in tools/tapematch/observations.db next to the
    pair-level ``human_judgment`` writes it summarises. Nothing in the
    tapematch pipeline reads an accept, and observations.db is write-locked
    for hours at a time by the nightly analysis runs — an accept must not
    fail because a batch is mid-flight. observations.db is still *read*
    here (read-only) to resolve the run and count its judged pairs.

    JSON body::

        {"date": "YYYY-MM-DD", "run_id": str (optional),
         "note": str | null (optional)}

    ``n_judged`` is counted server-side from ``pairs.human_judgment`` for
    the accepted run rather than taken from the client, so the stored
    record reflects what is actually in the DB at accept time. Re-accepting
    a date replaces its row (the run may have changed under it).

    Returns:
        200 ``{"ok": true, "date", "run_id", "accepted_at", "n_judged",
        "n_families"}``; 400 ``missing_fields``; 404 ``no_run``; 409
        ``locked`` if observations.db can't be read for the run resolution.
    """
    from backend import tapematch_sync as _tapematch_sync

    body = request.get_json(force=True) or {}
    concert_date = body.get("date")
    run_id = body.get("run_id")
    note = body.get("note")

    if not concert_date:
        return jsonify({"error": "missing_fields"}), 400

    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify({"error": "no_run"}), 404

        # One read-only pass over observations.db: resolve the run if the
        # client didn't name one, then take the two provenance counts.
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            if not run_id:
                run_id = _tapematch_sync._pick_best_run(obs_conn).get(concert_date)
                if run_id is None:
                    return jsonify({"error": "no_run"}), 404
            n_judged = obs_conn.execute(
                "SELECT COUNT(*) FROM pairs WHERE run_id = ? AND concert_date = ? "
                    "AND human_judgment IS NOT NULL",
                (run_id, concert_date),
            ).fetchone()[0]
            # Probe for n_families rather than assuming it — same defensive
            # shape as the pairs route's secondary-metric enrichment.
            run_cols = {
                r[1] for r in obs_conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            n_families = None
            if "n_families" in run_cols:
                fam_row = obs_conn.execute(
                    "SELECT n_families FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                n_families = fam_row[0] if fam_row else None
        finally:
            obs_conn.close()

        from datetime import datetime as _datetime

        accepted_at = _datetime.now(UTC).isoformat(timespec="seconds")

        conn = database.get_connection()
        with conn:
            conn.execute(
                """
                    INSERT INTO tapematch_date_curation
                        (concert_date, run_id, accepted_at, n_judged, n_families, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(concert_date) DO UPDATE SET
                        run_id      = excluded.run_id,
                        accepted_at = excluded.accepted_at,
                        n_judged    = excluded.n_judged,
                        n_families  = excluded.n_families,
                        note        = excluded.note
                    """,
                (concert_date, run_id, accepted_at, n_judged, n_families, note),
            )

        return jsonify(
            {
                "ok": True,
                "date": concert_date,
                "run_id": run_id,
                "accepted_at": accepted_at,
                "n_judged": n_judged,
                "n_families": n_families,
            }
        )
    except RuntimeError as exc:
        return jsonify({"error": "locked", "message": str(exc)}), 409
    except Exception as exc:
        _log.exception("tapematch_accept_families failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/analysis", methods=["GET"])
def tapematch_analysis_for_date() -> Response:
    """The chosen TapeMatch run's analysis.md verdict for one concert date.

    Query param: date=YYYY-MM-DD (required). Reads observations.db only
    to resolve the best run + its archive dir (_pick_best_run,
    _resolve_run_dir) then reads analysis.md straight off disk — never
    writes. 200 with run_id/verdict/analysis_md all null when the date
    has no run yet, and analysis_md null (verdict still populated as
    null) when the run exists but hasn't had its analysis.md written.
    """
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    if not concert_date:
        return jsonify({"error": "missing_date"}), 400
    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify(
                {"date": concert_date, "run_id": None, "verdict": None,
                 "analysis_md": None}
            )
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            run_id = _tapematch_sync._pick_best_run(obs_conn).get(concert_date)
            if run_id is None:
                return jsonify(
                    {"date": concert_date, "run_id": None, "verdict": None,
                     "analysis_md": None}
                )
            run_dir = _tapematch_sync._resolve_run_dir(obs_conn, run_id, concert_date)
        finally:
            obs_conn.close()

        analysis_path = run_dir / "analysis.md"
        if not analysis_path.exists():
            return jsonify(
                {"date": concert_date, "run_id": run_id, "verdict": None,
                 "analysis_md": None}
            )
        text = analysis_path.read_text(encoding="utf-8")
        needs_review, reason = _tapematch_sync._parse_verdict(text)
        verdict = {"needs_review": needs_review, "reason": reason}
        return jsonify(
            {"date": concert_date, "run_id": run_id, "verdict": verdict,
             "analysis_md": text}
        )
    except RuntimeError as exc:
        return jsonify({"error": "locked", "message": str(exc)}), 409
    except Exception as exc:
        _log.exception("tapematch_analysis_for_date failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/report", methods=["GET"])
def tapematch_report_for_date() -> Response:
    """The chosen TapeMatch run's report.md for one concert date (§11).

    Query param: date=YYYY-MM-DD (required). Same run resolution and
    read-only disk read as /api/tapematch/analysis — the two documents
    are siblings in the run's archive dir — plus ``run_dir``, which §11's
    sheet header prints so a curator can find the file on disk. 200 with
    run_id/run_dir/report_md all null when the date has no run yet, and
    report_md null (run_id/run_dir populated) when the run predates
    report.md or never wrote one.
    """
    from backend import tapematch_sync as _tapematch_sync

    concert_date = request.args.get("date")
    if not concert_date:
        return jsonify({"error": "missing_date"}), 400
    empty = {"date": concert_date, "run_id": None, "run_dir": None, "report_md": None}
    try:
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if not Path(obs_path).exists():
            return jsonify(empty)
        obs_conn = _tapematch_sync._open_observations_db(obs_path)
        try:
            run_id = _tapematch_sync._pick_best_run(obs_conn).get(concert_date)
            if run_id is None:
                return jsonify(empty)
            run_dir = _tapematch_sync._resolve_run_dir(obs_conn, run_id, concert_date)
        finally:
            obs_conn.close()

        report_path = run_dir / "report.md"
        text = (
            report_path.read_text(encoding="utf-8") if report_path.exists() else None
        )
        return jsonify(
            {"date": concert_date, "run_id": run_id, "run_dir": str(run_dir),
             "report_md": text}
        )
    except RuntimeError as exc:
        return jsonify({"error": "locked", "message": str(exc)}), 409
    except Exception as exc:
        _log.exception("tapematch_report_for_date failed for date=%s", concert_date)
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/dates", methods=["GET"])
def tapematch_dates() -> Response:
    """Per-date summary of synced TapeMatch pairs, for the screen's left
    rail (LISTENING §1 / TODO-170).

    One row per concert_date in tapematch_pairs, sorted date DESC:
    run_id (the date's single synced run), n_lbs (distinct LBs across
    lb_a/lb_b), n_pairs (row count), location (first non-empty
    entries.location for the date; null if none), has_analysis /
    needs_review (does the chosen run's dir hold an analysis.md, and
    does its verdict flag review — via _resolve_run_dir/_parse_verdict).
    If observations.db is missing or locked, has_analysis/needs_review
    are null for every row rather than failing the endpoint.

    Also carries curated/curated_at from the app DB's
    ``tapematch_date_curation`` (written by POST
    /api/tapematch/dates/accept) — the curation screen's fourth triage
    state. Unlike has_analysis/needs_review these survive a locked
    observations.db, because they are app-DB state.
    """
    from backend import tapematch_sync as _tapematch_sync

    try:
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT concert_date, lb_a, lb_b, run_id FROM tapematch_pairs"
        ).fetchall()

        by_date: dict[str, dict] = {}
        for r in rows:
            agg = by_date.setdefault(
                r["concert_date"],
                {"run_id": r["run_id"], "lbs": set(), "n_pairs": 0},
            )
            agg["lbs"].add(r["lb_a"])
            agg["lbs"].add(r["lb_b"])
            agg["n_pairs"] += 1

        # First non-empty entries.location per date, one query. Joined via
        # lb_number, not date: entries.date_str is US-format ("7/28/00",
        # "xx/xx/87") and can never equal tapematch's ISO concert_date.
        locations: dict[str, str | None] = {}
        if by_date:
            all_lbs = sorted({lb for agg in by_date.values() for lb in agg["lbs"]})
            placeholders = ",".join("?" * len(all_lbs))
            loc_rows = conn.execute(
                f"SELECT lb_number, location FROM entries "
                    f"WHERE lb_number IN ({placeholders}) "
                    f"AND location IS NOT NULL AND location != ''",
                all_lbs,
            ).fetchall()
            loc_by_lb = {r["lb_number"]: r["location"] for r in loc_rows}
            for date, agg in by_date.items():
                locations[date] = next(
                    (loc_by_lb[lb] for lb in sorted(agg["lbs"]) if lb in loc_by_lb),
                    None,
                )

        # One read-only observations.db pass to resolve each date's run
        # dir; one stat per date, file read only when parsing a verdict.
        analysis_by_date: dict[str, tuple] = {}
        obs_ok = False

        # Curation accepts live in the app DB (POST
        # /api/tapematch/dates/accept), so they are readable even while a
        # tapematch run holds observations.db — unlike has_analysis below.
        accepted_at_by_date = {
            r["concert_date"]: r["accepted_at"]
            for r in conn.execute(
                "SELECT concert_date, accepted_at FROM tapematch_date_curation"
            )
        }
        obs_path = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH
        if Path(obs_path).exists():
            try:
                obs_conn = _tapematch_sync._open_observations_db(obs_path)
            except RuntimeError:
                _log.warning(
                    "tapematch_dates: observations.db locked; "
                        "has_analysis/needs_review omitted"
                )
            else:
                try:
                    for date, agg in by_date.items():
                        run_dir = _tapematch_sync._resolve_run_dir(
                            obs_conn, agg["run_id"], date
                        )
                        analysis_path = run_dir / "analysis.md"
                        if not analysis_path.exists():
                            analysis_by_date[date] = (False, None)
                            continue
                        try:
                            text = analysis_path.read_text(encoding="utf-8")
                        except OSError:
                            analysis_by_date[date] = (True, None)
                            continue
                        flagged, _reason = _tapematch_sync._parse_verdict(text)
                        analysis_by_date[date] = (True, flagged)
                    obs_ok = True
                finally:
                    obs_conn.close()

        dates = []
        for date in sorted(by_date, reverse=True):
            agg = by_date[date]
            has_analysis, needs_review = (
                analysis_by_date.get(date, (False, None)) if obs_ok else (None, None)
            )
            dates.append(
                {
                    "date": date,
                    "run_id": agg["run_id"],
                    "n_lbs": len(agg["lbs"]),
                    "n_pairs": agg["n_pairs"],
                    "has_analysis": has_analysis,
                    "needs_review": needs_review,
                    "location": locations.get(date),
                    "curated_at": accepted_at_by_date.get(date),
                    "curated": date in accepted_at_by_date,
                }
            )
        return jsonify({"dates": dates})
    except Exception as exc:
        _log.exception("tapematch_dates failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/crawl/status", methods=["GET"])
def tapematch_crawl_status() -> Response:
    """Read-only status for the detached TapeMatch library crawl.

    Replicates tools/tapematch/crawl_status.sh: is run_crawl.sh running
    (via pgrep, no shell=True), how many run dirs exist on disk / how
    many distinct dates they cover, and the crawl log's last 5 lines.
    No start/stop controls here — this is observation only.
    """
    result = get_tapematch_crawl_status()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@bp.route("/api/tapematch/crawl/start", methods=["POST"])
def tapematch_crawl_start() -> Response:
    """Start the detached TapeMatch library crawl via crawl_start.sh.

    The script is the single-instance authority (pgrep-guards against a
    second crawl or a live tapematch_session.py) — no Python-side lock is
    added here. Optional JSON body: ``min_entries`` (int) and
    ``allow_missing`` (bool) map to the script's ``--min-entries`` and
    ``--allow-missing`` flags.

    Returns:
        200 with ``{ok, message}`` on successful launch; 409
        ``{error: "already_running", message}`` if the script's guard
        refused to start; 400 for a malformed body; 500 on unexpected
        failure to invoke the script.
    """
    import subprocess

    body = request.get_json(silent=True) or {}
    min_entries = body.get("min_entries")
    allow_missing = body.get("allow_missing")
    if min_entries is not None and not isinstance(min_entries, int):
        return jsonify({"error": "bad_request", "message": "min_entries must be an int"}), 400
    if allow_missing is not None and not isinstance(allow_missing, bool):
        return jsonify({"error": "bad_request", "message": "allow_missing must be a bool"}), 400

    args: list[str] = []
    if min_entries is not None:
        args.extend(["--min-entries", str(min_entries)])
    if allow_missing:
        args.append("--allow-missing")

    try:
        from backend import tapematch_sync as _tapematch_sync

        script_dir = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH.parent
        script = script_dir / "crawl_start.sh"
        proc = subprocess.run(
            [str(script), *args], capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            message = (proc.stdout + proc.stderr).strip()
            return jsonify({"error": "already_running", "message": message}), 409
        return jsonify({"ok": True, "message": proc.stdout.strip()})
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _log.exception("tapematch_crawl_start failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/crawl/stop", methods=["POST"])
def tapematch_crawl_stop() -> Response:
    """Stop the detached TapeMatch library crawl via crawl_stop.sh.

    The script always exits 0 — it sends SIGINT to the running session (or
    run_crawl.sh between dates) and is a no-op if nothing is running.

    Returns:
        200 with ``{ok, message}`` on success; 500 on unexpected failure
        to invoke the script.
    """
    import subprocess

    try:
        from backend import tapematch_sync as _tapematch_sync

        script_dir = _tapematch_sync.DEFAULT_OBSERVATIONS_DB_PATH.parent
        script = script_dir / "crawl_stop.sh"
        proc = subprocess.run(
            [str(script)], capture_output=True, text=True, timeout=15,
        )
        return jsonify({"ok": True, "message": proc.stdout.strip()})
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _log.exception("tapematch_crawl_stop failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/library/performances", methods=["GET"])
def library_performances() -> Response:
    """Shows (date+location groups) with their recordings, for the Library
    screen's performance lens (TODO-150 step 5).

    Not merged with TapeMatch family data — the GUI fetches
    /api/tapematch/families separately, same pattern as /api/collection/prefetch.
    """
    try:
        return jsonify(database.get_performances())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/library/badges", methods=["GET"])
def library_badges() -> Response:
    """Flat pick/quality/curated/taper badge fields keyed by LB number, for
    the Library recording lens's client-side merge (SPEC_INTEGRATION_NOTES.md
    F4, TODO-186 remainder). Same signals the performance lens gets inline
    from /api/library/performances; empty on a fresh install pre-recompute.
    """
    try:
        return jsonify(database.get_pick_badges())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
