"""Read-only pipeline freshness planner (GET /api/refresh/status).

Phase 1 of the pipeline-refresh spec (`instructions/PIPELINE_REFRESH_PHASE1.md`).
This module answers *"what is not up to date, and how do I run it?"* by reading
the staleness signals that already live in the schema -- `computed_at`,
`parsed_at`, `imported_at`, `fetched_at`, `geocoded_at` columns written today by
existing workers but read by nothing. It adds no schema, issues zero writes, and
changes no existing code path.

Connection choice: this module uses ``backend.db.get_connection(db_path)`` (the
house pattern also used by ``gap_analysis.py`` and ``lb_coverage.py``) rather
than a literal ``file:...?mode=ro`` URI. The spec's "read-only connection"
wording is aspirational -- ``get_connection`` returns a normal read/write handle,
but every statement this module issues is a ``SELECT``, so no write ever reaches
the DB through it. Using the same connection helper as the rest of the backend
keeps pooling/WAL/pragma behaviour consistent instead of opening a second,
differently-configured handle to the same file.

Three signal types (spec Sec 1a), most severe wins:
  - ``backlog``  -- COUNT(*) of unprocessed rows. Direct measure, preferred.
  - ``watermark`` -- MAX(timestamp) compared against upstream MAX(timestamp).
    A proxy: false positives are possible (re-touching one upstream row bumps
    every downstream wholesale step), so it is only consulted when no backlog
    signal exists, and never when backlog == 0 (spec Sec 2.5 false-positive
    guard).
  - ``version`` -- a hash of a config input. Not implemented in Phase 1 (no
    stamp exists yet); ``version_key`` is always ``None`` on every step below.

Steps with genuinely no queryable signal (spec Sec 4) declare
``backlog_sql=None`` and ``last_run_sql=None`` and report state ``unknown``:
  - ``xref_ingest``, ``attachments_reconcile`` -- no run-record of any kind
    exists for these routes today.
  - ``mirror_crawl``, ``wtrf_crawl``, ``bootleg_scrape`` -- crawler workers
    write files/DB rows opportunistically with no watermark column and no
    well-defined "unprocessed" predicate.
  - ``sitedata_publish``, ``preservation``, ``archive_org`` -- external
    publish/upload actions with no local completion signal at all.

Config-only inputs (spec Sec 1c: taper alias table, ranker config, TapeMatch
thresholds) have zero rows that move when they change. Phase 1 does not invent
a stamp for these; they are simply absent from every step's signal set, and the
gap is recorded here rather than silently forgotten.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
import sqlite3
from typing import NamedTuple

from backend import config_version
from backend.db import get_connection

logger = logging.getLogger(__name__)

_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)

_TS_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<frac>\.\d+)?(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)


class RefreshStep(NamedTuple):
    """One node in the pipeline freshness DAG.

    Attributes:
        step_id: Stable identifier, e.g. ``'attribute_tapers'``.
        label: i18n key suffix (Phase 1 reuses ``step_id`` verbatim).
        trigger: One of ``'T1'``, ``'T2'``, ``'T3'``, ``'T4'``.
        kind: ``'wholesale'`` | ``'incremental'`` | ``'manual'``.
        backlog_sql: SQL returning one row, one int -- rows still unprocessed,
            or ``None`` if no backlog predicate exists.
        last_run_sql: SQL returning one row, one scalar timestamp (or a
            ``meta`` value string), or ``None`` if no watermark exists.
        version_key: ``meta`` key holding a config hash. Always ``None`` in
            Phase 1 -- no version signal is implemented yet (spec Sec 1c).
        upstream: step_ids this step depends on (DAG edges).
        how_to_run: Route or exact CLI command, for display only.
        cost: ``'fast'`` | ``'slow'`` | ``'very_slow'``.
        human_gate: True if a human must approve/trigger this step manually
            even once its inputs are ready (e.g. publish steps).
    """

    step_id: str
    label: str
    trigger: str
    kind: str
    backlog_sql: str | None
    last_run_sql: str | None
    version_key: str | None
    upstream: tuple[str, ...]
    how_to_run: str
    cost: str
    human_gate: bool


STEPS: tuple[RefreshStep, ...] = (
    # ── T1 ────────────────────────────────────────────────────────────────
    RefreshStep(
        step_id="flat_file_apply",
        label="flat_file_apply",
        trigger="T1",
        kind="manual",
        # 'status' lifecycle is detected -> downloaded -> applied (or deferred).
        # Only 'downloaded' rows are apply-ready backlog; 'detected' has not
        # even been fetched yet and 'deferred' was deliberately held off, so
        # neither belongs in this count (verified against the live status
        # column: {'applied', 'applied_legacy', 'detected'} today).
        backlog_sql="SELECT COUNT(*) FROM flat_file_releases WHERE status='downloaded'",
        last_run_sql="SELECT MAX(applied_at) FROM flat_file_releases",
        version_key=None,
        upstream=(),
        how_to_run="POST /api/flat_file/apply/<id>",
        cost="fast",
        human_gate=False,
    ),
    RefreshStep(
        step_id="db_import",
        label="db_import",
        trigger="T1",
        kind="manual",
        backlog_sql=None,
        last_run_sql="SELECT value FROM meta WHERE key='last_import_date'",
        version_key=None,
        upstream=("flat_file_apply",),
        how_to_run="POST /api/db/import",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="scrape_entries",
        label="scrape_entries",
        trigger="T1",
        kind="incremental",
        backlog_sql="SELECT COUNT(*) FROM entries WHERE scraped_at IS NULL",
        last_run_sql="SELECT MAX(scraped_at) FROM entries",
        version_key=None,
        upstream=("db_import",),
        how_to_run="POST /api/scrape/start",
        cost="very_slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="lb_master_reconcile",
        label="lb_master_reconcile",
        trigger="T1",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(last_status_at) FROM lb_master",
        version_key=None,
        upstream=("flat_file_apply", "db_import", "scrape_entries"),
        how_to_run="POST /api/lb_master/reconcile",
        cost="slow",
        human_gate=False,
    ),
    # ── T3: content corpora ─────────────────────────────────────────────
    RefreshStep(
        step_id="olof_fetch",
        label="olof_fetch",
        trigger="T3",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(fetched_at) FROM olof_pages WHERE corpus IN ('dsn','chronicle')",
        version_key=None,
        upstream=(),
        how_to_run="POST /api/olof/fetch",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="olof_parse",
        label="olof_parse",
        trigger="T3",
        kind="wholesale",
        # parsed_at vs fetched_at is the ONE sanctioned same-table SQL timestamp
        # comparison (spec Sec 1b exception): both columns live in olof_pages
        # and are written by the same ISO-'T' writer, so the string format is
        # identical and the comparison is safe without going through
        # _parse_ts(). Every cross-table comparison in this module still goes
        # through _parse_ts() in Python.
        backlog_sql=(
            "SELECT COUNT(*) FROM olof_pages WHERE corpus IN ('dsn','chronicle') "
            "AND (parsed_at IS NULL OR parsed_at < fetched_at)"
        ),
        last_run_sql="SELECT MAX(parsed_at) FROM olof_pages WHERE corpus IN ('dsn','chronicle')",
        version_key=None,
        upstream=("olof_fetch",),
        how_to_run=".venv/bin/python3 -m backend.olof_parser",
        cost="fast",
        human_gate=False,
    ),
    RefreshStep(
        step_id="bobserve_fetch",
        label="bobserve_fetch",
        trigger="T3",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(fetched_at) FROM olof_pages WHERE corpus='bobserve'",
        version_key=None,
        upstream=(),
        how_to_run="POST /api/bobserve/fetch",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="bobserve_parse",
        label="bobserve_parse",
        trigger="T3",
        kind="wholesale",
        # Same sanctioned same-table exception as olof_parse above, scoped to
        # corpus='bobserve'.
        backlog_sql=(
            "SELECT COUNT(*) FROM olof_pages WHERE corpus='bobserve' "
            "AND (parsed_at IS NULL OR parsed_at < fetched_at)"
        ),
        last_run_sql="SELECT MAX(parsed_at) FROM olof_pages WHERE corpus='bobserve'",
        version_key=None,
        upstream=("bobserve_fetch",),
        how_to_run=".venv/bin/python3 -m backend.bobserve_parser",
        cost="fast",
        human_gate=False,
    ),
    # ── Derived chain ────────────────────────────────────────────────────
    RefreshStep(
        step_id="parse_lineage",
        label="parse_lineage",
        trigger="T1",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(parsed_at) FROM entry_lineage",
        version_key=None,
        upstream=("scrape_entries",),
        how_to_run="POST /api/derived/recompute",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="attribute_tapers",
        label="attribute_tapers",
        trigger="T1",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(computed_at) FROM taper_attributions",
        version_key="refresh_version_taper_aliases",
        upstream=("parse_lineage",),
        how_to_run="POST /api/derived/recompute",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="compute_show_picks",
        label="compute_show_picks",
        trigger="T1",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(computed_at) FROM show_picks",
        version_key=None,
        upstream=("attribute_tapers", "ranker_rerank"),
        how_to_run="POST /api/derived/recompute",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="song_index",
        label="song_index",
        trigger="T3",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(computed_at) FROM song_performances",
        version_key=None,
        upstream=("olof_parse", "bobserve_parse"),
        how_to_run="POST /api/derived/recompute",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="setlist_fingerprint",
        label="setlist_fingerprint",
        trigger="T3",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(computed_at) FROM setlist_fingerprint_suggestions",
        version_key=None,
        upstream=("song_index",),
        how_to_run="POST /api/fingerprint/scan",
        cost="slow",
        human_gate=False,
    ),
    # ── T2: local pipeline / ranking ────────────────────────────────────
    RefreshStep(
        step_id="pipeline_run",
        label="pipeline_run",
        trigger="T2",
        kind="incremental",
        backlog_sql=None,
        last_run_sql="SELECT MAX(updated_at) FROM pipeline_folder_state",
        version_key=None,
        upstream=(),
        how_to_run="POST /api/pipeline/run/start",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="tapematch_sync",
        label="tapematch_sync",
        trigger="T2",
        kind="wholesale",
        backlog_sql=None,
        last_run_sql="SELECT MAX(imported_at) FROM recording_families",
        version_key=None,
        upstream=(),
        how_to_run="POST /api/tapematch/sync",
        cost="fast",
        human_gate=False,
    ),
    RefreshStep(
        step_id="ranker_scan",
        label="ranker_scan",
        trigger="T2",
        kind="incremental",
        # Rescoped to the latest scan_id (TODO-306 Phase 2 decision 5) so this
        # count equals POST /api/ranker/scan's own `planned` -- unscoped, it
        # would count every my_collection LB missing metrics under ANY scan,
        # which is not what a "backlog" scan run actually plans to touch.
        backlog_sql=(
            "SELECT COUNT(*) FROM my_collection mc WHERE NOT EXISTS "
            "(SELECT 1 FROM quality_recording_metrics m WHERE m.lb_number = mc.lb_number "
            "AND m.scan_id = (SELECT MAX(scan_id) FROM quality_scans))"
        ),
        last_run_sql="SELECT MAX(started_at) FROM quality_scans",
        version_key="refresh_version_ranker_scan_config",
        upstream=("pipeline_run", "tapematch_sync"),
        how_to_run="POST /api/ranker/scan",
        cost="very_slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="ranker_rerank",
        label="ranker_rerank",
        trigger="T2",
        kind="wholesale",
        backlog_sql=(
            "SELECT COUNT(DISTINCT m.lb_number) FROM quality_recording_metrics m "
            "WHERE NOT EXISTS "
            "(SELECT 1 FROM quality_recording_scores s WHERE s.lb_number = m.lb_number)"
        ),
        # quality_recording_scores has NO timestamp column -- do not invent one.
        # The run-record supplies last_run instead (see _last_run_record) --
        # only the backlog signal above is used for this step's watermark.
        last_run_sql=None,
        version_key="refresh_version_ranker_rank_config",
        upstream=("ranker_scan",),
        how_to_run="POST /api/ranker/rerank",
        cost="fast",
        human_gate=False,
    ),
    # ── Geocode ──────────────────────────────────────────────────────────
    RefreshStep(
        step_id="geocode",
        label="geocode",
        trigger="T3",
        kind="incremental",
        # Lifted verbatim from backend/geocoder.py's non-retry_failed branch
        # (Sec ~1009-1018 as of this writing) -- keep this in sync if that
        # query changes.
        backlog_sql=(
            "SELECT COUNT(*) FROM ("
            "SELECT DISTINCT e.location FROM entries e "
            "LEFT JOIN location_geocoded geo ON e.location = geo.location_text "
            "WHERE e.location IS NOT NULL AND e.location != '' "
            "AND geo.location_text IS NULL)"
        ),
        last_run_sql="SELECT MAX(geocoded_at) FROM location_geocoded",
        version_key=None,
        upstream=("scrape_entries", "olof_parse"),
        how_to_run="POST /api/geocode/run",
        cost="slow",
        human_gate=False,
    ),
    # ── T4: publish ──────────────────────────────────────────────────────
    RefreshStep(
        step_id="master_publish",
        label="master_publish",
        trigger="T4",
        kind="manual",
        backlog_sql=None,
        last_run_sql="SELECT value FROM meta WHERE key='master_published_at'",
        version_key=None,
        upstream=("lb_master_reconcile", "compute_show_picks", "tapematch_sync"),
        how_to_run="POST /api/master/export then POST /api/master/github_release",
        cost="slow",
        human_gate=True,
    ),
    # ── Unmeasurable (spec Sec 4): no queryable local signal ────────────
    RefreshStep(
        step_id="xref_ingest",
        label="xref_ingest",
        trigger="T1",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/xref_ingest/scan",
        cost="fast",
        human_gate=False,
    ),
    RefreshStep(
        step_id="attachments_reconcile",
        label="attachments_reconcile",
        trigger="T1",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/attachments/reconcile",
        cost="fast",
        human_gate=False,
    ),
    RefreshStep(
        step_id="mirror_crawl",
        label="mirror_crawl",
        trigger="T3",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/crawler/start",
        cost="very_slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="wtrf_crawl",
        label="wtrf_crawl",
        trigger="T3",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/wtrf/crawl_missing",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="bootleg_scrape",
        label="bootleg_scrape",
        trigger="T3",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/bootlegs/scrape",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="sitedata_publish",
        label="sitedata_publish",
        trigger="T4",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/package/scrape_data then POST /api/sitedata/github_release",
        cost="slow",
        human_gate=True,
    ),
    RefreshStep(
        step_id="preservation",
        label="preservation",
        trigger="T4",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/preservation/start",
        cost="slow",
        human_gate=False,
    ),
    RefreshStep(
        step_id="archive_org",
        label="archive_org",
        trigger="T4",
        kind="manual",
        backlog_sql=None,
        last_run_sql=None,
        version_key=None,
        upstream=(),
        how_to_run="POST /api/archive_org/upload",
        cost="slow",
        human_gate=False,
    ),
)

_STEPS_BY_ID: dict[str, RefreshStep] = {step.step_id: step for step in STEPS}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """Return True if `name` exists as a table in the connected DB."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _required_tables(sql: str) -> set[str]:
    """Return the table names referenced by *sql*'s FROM/JOIN clauses."""
    return {match.group(1) for match in _TABLE_RE.finditer(sql)}


def _run_scalar(conn: sqlite3.Connection, sql: str | None):
    """Run *sql* and return its single scalar value, or None on any failure.

    Guards with `_table_exists()` for every table the query references so a
    missing table degrades to None instead of raising. Never raises.
    """
    if not sql:
        return None
    try:
        for table in _required_tables(sql):
            if not _table_exists(conn, table):
                return None
        row = conn.execute(sql).fetchone()
    except sqlite3.Error:
        logger.exception("refresh: query failed: %s", sql)
        return None
    if row is None:
        return None
    return row[0]


def _parse_ts(value) -> _dt.datetime | None:
    """Normalize a timestamp string to a naive local `datetime`.

    Accepts `'YYYY-MM-DD HH:MM:SS'` and `'YYYY-MM-DDTHH:MM:SS'`, optional
    fractional seconds, and an optional timezone offset or trailing `'Z'`.
    Tz-aware inputs (e.g. `meta.master_published_at`, which is UTC) are
    converted to local time and then stripped of tzinfo so they compare
    directly against the naive-local values every other column stores.
    Returns None for None, '', or unparseable input. Never raises.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _TS_RE.match(text):
        return None
    normalized = text.replace(" ", "T", 1)
    try:
        parsed = _dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _step_state(
    step: RefreshStep,
    last_run: _dt.datetime | None,
    upstream_runs: dict[str, tuple[str, _dt.datetime | None]],
    backlog: int | None,
    *,
    version_state: str = "n/a",
    last_run_status: str | None = None,
    last_run_source: str | None = None,
) -> tuple[str, str]:
    """Return (state, reason) for one step. Pure function, no DB access.

    Evaluation order (spec Sec 2.5, extended by TODO-306 Phase 2 Sec 3.7):
      1. version_state == 'changed' -> 'stale' (a config change invalidates
         output even at backlog 0, so it is checked before the backlog
         signal).
      2. backlog > 0 -> 'stale' (direct measure).
      3. newest refresh_step_runs row for this step has status='error' with
         no later success -> 'stale', "last run failed".
      4. any upstream step is itself stale/blocked -> 'blocked'.
      5. backlog is None and an upstream last_run is newer than mine (after
         `_parse_ts` normalization) -> 'stale' (watermark proxy; only
         consulted when no backlog signal exists, so backlog == 0 can never
         be overridden by a newer upstream watermark -- spec Sec 1a's
         false-positive guard).
      6. no signal at all available -> 'unknown'.
      7. otherwise -> 'fresh'; version_state == 'unstamped' is appended to
         the reason but never changes the state (TODO-306 Phase 2 decision 6).

    Args:
        step: The step being evaluated.
        last_run: This step's own last-run timestamp -- the newer of its
            watermark and its newest successful run-record (see
            `_last_run_record` / `compute_plan`), or None if unavailable.
        upstream_runs: Mapping step_id -> (state, last_run) for each entry in
            `step.upstream`, already computed (topological order).
        backlog: This step's own backlog count, or None if no backlog_sql.
        version_state: One of 'ok' | 'changed' | 'unstamped' | 'n/a', from
            `config_version.version_state`.
        last_run_status: Status of the newest `refresh_step_runs` row for
            this step (any status, not just successful), or None if no rows
            exist.
        last_run_source: 'run_record' | 'watermark' | None -- unused in the
            state logic itself, accepted only so callers can pass the same
            kwargs they already computed for `last_run` (documentation only).

    Returns:
        (state, reason) where state is one of
        'stale' | 'blocked' | 'unknown' | 'fresh'.
    """
    if version_state == "changed":
        return "stale", "config changed since last run"

    if backlog is not None and backlog > 0:
        return "stale", f"backlog {backlog} unprocessed"

    if last_run_status == "error":
        return "stale", "last run failed"

    for upstream_id in step.upstream:
        upstream_state, _upstream_last_run = upstream_runs.get(upstream_id, ("unknown", None))
        if upstream_state in ("stale", "blocked"):
            return "blocked", f"upstream {upstream_id} is {upstream_state}"

    if backlog is None:
        newest_upstream_id: str | None = None
        newest_upstream_run: _dt.datetime | None = None
        for upstream_id in step.upstream:
            _upstream_state, upstream_last_run = upstream_runs.get(upstream_id, ("unknown", None))
            if upstream_last_run is None:
                continue
            if last_run is None or upstream_last_run > last_run:
                if newest_upstream_run is None or upstream_last_run > newest_upstream_run:
                    newest_upstream_id = upstream_id
                    newest_upstream_run = upstream_last_run
        if newest_upstream_id is not None:
            return "stale", (
                f"no backlog signal; upstream {newest_upstream_id} ran "
                f"{newest_upstream_run.date()} after mine "
                f"{last_run.date() if last_run else 'never'}"
            )

    if backlog is None and last_run is None:
        if not step.upstream:
            state, reason = "unknown", "no backlog or watermark signal for this step"
        else:
            state, reason = "unknown", "no backlog or watermark signal; upstream all fresh/unknown"
    elif backlog == 0 and last_run is None:
        state, reason = "fresh", "no watermark column; backlog 0"
    elif backlog == 0:
        state, reason = "fresh", "backlog 0"
    else:
        state, reason = (
            "fresh",
            f"watermark {last_run.date()}, no newer upstream" if last_run else "fresh",
        )

    # Config-version gap noted but never downgrades state (decision 6) --
    # 'changed' already returned 'stale' above; only 'unstamped' reaches here.
    if version_state == "unstamped":
        reason = f"{reason} (version unstamped)"
    return state, reason


def _last_run_record(
    conn: sqlite3.Connection, step_id: str,
) -> tuple[_dt.datetime | None, str | None]:
    """Return (newest successful finished_at, status of the newest row overall).

    Closes the Phase 1 gap for steps like `ranker_rerank` whose output table
    has no timestamp column at all (`quality_recording_scores`) -- Phase 2's
    `refresh_step_runs` is the first run-record any step here can rely on.

    Args:
        conn: Live connection.
        step_id: `refresh.STEPS` step id.

    Returns:
        (last_success, last_status) -- both None if the table is absent or
        no rows exist for this step_id. Never raises.
    """
    if not _table_exists(conn, "refresh_step_runs"):
        return None, None
    try:
        newest_ok_row = conn.execute(
            "SELECT finished_at FROM refresh_step_runs "
            "WHERE step_id = ? AND status IN ('ok', 'noop') "
            "ORDER BY finished_at DESC, id DESC LIMIT 1",
            (step_id,),
        ).fetchone()
        newest_any_row = conn.execute(
            "SELECT status FROM refresh_step_runs WHERE step_id = ? "
            "ORDER BY finished_at DESC, id DESC LIMIT 1",
            (step_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.exception("refresh: failed reading refresh_step_runs for %s", step_id)
        return None, None
    last_success = _parse_ts(newest_ok_row[0]) if newest_ok_row else None
    last_status = newest_any_row[0] if newest_any_row else None
    return last_success, last_status


def _version_signal(conn: sqlite3.Connection, step: RefreshStep) -> dict:
    """Return the {key, state, expected, stored} version block for one step.

    Args:
        conn: Live connection.
        step: The step being evaluated.

    Returns:
        A dict with `key` (None if unversioned), `state` (see
        `config_version.version_state`), `expected`, and `stored`.
    """
    if not step.version_key:
        return {"key": None, "state": "n/a", "expected": None, "stored": None}
    stored = None
    if _table_exists(conn, "meta"):
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (step.version_key,)
            ).fetchone()
            stored = row[0] if row else None
        except sqlite3.Error:
            logger.exception("refresh: failed reading meta key %s", step.version_key)
    expected = config_version.compute_expected(step.step_id)
    state = config_version.version_state(step.step_id, stored)
    return {"key": step.version_key, "state": state, "expected": expected, "stored": stored}


def _topological_order() -> list[str]:
    """Return STEPS' step_ids ordered so every step follows its upstream deps.

    Raises:
        ValueError: if the registry contains an unresolved upstream id or a
            dependency cycle.
    """
    visited: dict[str, int] = {}  # 0=visiting, 1=done
    order: list[str] = []

    def visit(step_id: str, path: tuple[str, ...]) -> None:
        if step_id not in _STEPS_BY_ID:
            raise ValueError(f"refresh: unresolved upstream step_id {step_id!r} in {path}")
        state = visited.get(step_id)
        if state == 1:
            return
        if state == 0:
            raise ValueError(f"refresh: dependency cycle involving {step_id!r}: {path}")
        visited[step_id] = 0
        for upstream_id in _STEPS_BY_ID[step_id].upstream:
            visit(upstream_id, path + (upstream_id,))
        visited[step_id] = 1
        order.append(step_id)

    for step in STEPS:
        visit(step.step_id, (step.step_id,))
    return order


def _publish_lag(conn: sqlite3.Connection) -> dict:
    """Return the D7 publish-lag block: how much has changed since publish.

    Computed in Python (never SQL) because it compares `meta`'s ISO-tz-aware
    `master_published_at` against `lb_master.last_status_at` and
    `entries.scraped_at`, which use a different, naive-local format -- exactly
    the cross-format comparison spec Sec 1b warns against doing in SQL.
    """
    published_at = None
    if _table_exists(conn, "meta"):
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='master_published_at'"
            ).fetchone()
            published_at = row[0] if row else None
        except sqlite3.Error:
            logger.exception("refresh: failed reading master_published_at")

    published_dt = _parse_ts(published_at)
    if published_dt is None:
        return {
            "published_at": None,
            "lb_status_changes_since": 0,
            "entries_scraped_since": 0,
            "days_since": None,
        }

    # lb_status_history records actual status *transitions* (637 rows live),
    # whereas lb_master.last_status_at is re-stamped on every row by a
    # full reconcile — which would report the entire catalogue as "changed"
    # the day after any rebuild. Prefer the transition log; fall back to the
    # re-stamp column only when the history table is absent.
    lb_status_changes_since = 0
    if _table_exists(conn, "lb_status_history"):
        try:
            rows = conn.execute("SELECT changed_at FROM lb_status_history").fetchall()
            lb_status_changes_since = sum(
                1 for row in rows if (ts := _parse_ts(row[0])) is not None and ts > published_dt
            )
        except sqlite3.Error:
            logger.exception("refresh: failed scanning lb_status_history.changed_at")
    elif _table_exists(conn, "lb_master"):
        try:
            rows = conn.execute("SELECT last_status_at FROM lb_master").fetchall()
            lb_status_changes_since = sum(
                1 for row in rows if (ts := _parse_ts(row[0])) is not None and ts > published_dt
            )
        except sqlite3.Error:
            logger.exception("refresh: failed scanning lb_master.last_status_at")

    entries_scraped_since = 0
    if _table_exists(conn, "entries"):
        try:
            rows = conn.execute("SELECT scraped_at FROM entries").fetchall()
            entries_scraped_since = sum(
                1 for row in rows if (ts := _parse_ts(row[0])) is not None and ts > published_dt
            )
        except sqlite3.Error:
            logger.exception("refresh: failed scanning entries.scraped_at")

    days_since = max(0, (_dt.datetime.now() - published_dt).days)

    return {
        "published_at": published_at,
        "lb_status_changes_since": lb_status_changes_since,
        "entries_scraped_since": entries_scraped_since,
        "days_since": days_since,
    }


def compute_plan(db_path: str | None = None, trigger: str | None = None) -> dict:
    """Return the full freshness snapshot for GET /api/refresh/status.

    Args:
        db_path: Optional DB path override; defaults to the app's normal DB.
        trigger: Optional filter, e.g. 'T1' -- restricts `steps` and
            `by_trigger` to that trigger only. Registry evaluation still runs
            over all steps so upstream/blocked reasoning stays correct even
            when a downstream step's trigger differs from its upstream's.

    Returns:
        A dict with `generated_at`, `steps`, `stale_count`, `blocked_count`,
        `unknown_count`, `by_trigger`, and `publish_lag` keys. Every field is
        defensively computed; a missing table degrades a step to 'unknown'
        rather than raising.
    """
    conn = get_connection(db_path)
    now = _dt.datetime.now()

    order = _topological_order()
    computed: dict[str, tuple] = {}

    for step_id in order:
        step = _STEPS_BY_ID[step_id]
        watermark_raw = _run_scalar(conn, step.last_run_sql)
        watermark = _parse_ts(watermark_raw)
        run_record_last, last_run_status = _last_run_record(conn, step_id)

        if run_record_last is not None and (watermark is None or run_record_last > watermark):
            last_run, last_run_source = run_record_last, "run_record"
        elif watermark is not None:
            last_run, last_run_source = watermark, "watermark"
        else:
            last_run, last_run_source = None, None

        backlog = _run_scalar(conn, step.backlog_sql)
        if backlog is not None:
            try:
                backlog = int(backlog)
            except (TypeError, ValueError):
                backlog = None

        version = _version_signal(conn, step)

        upstream_runs = {
            upstream_id: (computed[upstream_id][0], computed[upstream_id][2])
            for upstream_id in step.upstream
            if upstream_id in computed
        }
        state, reason = _step_state(
            step, last_run, upstream_runs, backlog,
            version_state=version["state"], last_run_status=last_run_status,
            last_run_source=last_run_source,
        )
        computed[step_id] = (
            state, reason, last_run, backlog, last_run_source, last_run_status, version,
        )

    steps_out = []
    stale_count = blocked_count = unknown_count = 0
    triggers = ("T1", "T2", "T3", "T4") if trigger is None else (trigger,)
    by_trigger: dict[str, dict[str, int]] = {
        t: {"total": 0, "stale": 0, "blocked": 0, "unknown": 0} for t in triggers
    }

    for step in STEPS:
        state, reason, last_run, backlog, last_run_source, last_run_status, version = (
            computed[step.step_id]
        )
        # Clamped at 0: a handful of writers stamp UTC into otherwise
        # naive-local columns (pipeline_folder_state.updated_at is the live
        # example), which can put a "last run" a few hours into the future.
        # Reporting a negative age would read as a bug in this card rather
        # than the mixed-clock write it actually is.
        age_days = max(0, (now - last_run).days) if last_run is not None else None
        blocked_by = None
        if state == "blocked":
            blocked_by = next(
                (
                    upstream_id
                    for upstream_id in step.upstream
                    if computed.get(upstream_id, ("unknown",))[0] in ("stale", "blocked")
                ),
                None,
            )

        if trigger is not None and step.trigger != trigger:
            continue

        by_trigger[step.trigger]["total"] += 1
        if state == "stale":
            stale_count += 1
            by_trigger[step.trigger]["stale"] += 1
        elif state == "blocked":
            blocked_count += 1
            by_trigger[step.trigger]["blocked"] += 1
        elif state == "unknown":
            unknown_count += 1
            by_trigger[step.trigger]["unknown"] += 1

        steps_out.append({
            "step_id": step.step_id,
            "label": step.label,
            "trigger": step.trigger,
            "kind": step.kind,
            "state": state,
            "reason": reason,
            "last_run": last_run.isoformat() if last_run is not None else None,
            "last_run_source": last_run_source,
            "last_run_status": last_run_status,
            "age_days": age_days,
            "backlog": backlog,
            "blocked_by": blocked_by,
            "upstream": list(step.upstream),
            "how_to_run": step.how_to_run,
            "cost": step.cost,
            "human_gate": step.human_gate,
            "version": version,
        })

    return {
        "generated_at": now.isoformat(),
        "steps": steps_out,
        "stale_count": stale_count,
        "blocked_count": blocked_count,
        "unknown_count": unknown_count,
        "by_trigger": by_trigger,
        "publish_lag": _publish_lag(conn),
    }
