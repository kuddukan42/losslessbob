"""Executor registry for the pipeline freshness chain (TODO-306 Phase 3).

Maps every ``backend.refresh.STEPS`` step_id to a :class:`StepExecutor` so
``plan_chain``/``run_chain_claimed`` (a later bite) can drive the DAG without
knowing, per step, whether it is an in-process function call, a
``JobState``-backed background worker, or not chainable at all yet.

Imports ``backend.refresh`` for the DAG; ``refresh.py`` does not import this
module (the planner stays read-only, the property Phase 1 was built around).

All target callables are resolved **lazily inside each wrapper function**,
never at module import time -- ``concert_ranker``/``numpy`` (pulled in by
``backend.ranker_jobs``) and ``bs4``/``lxml`` (pulled in by
``backend.olof_fetcher``/``backend.bobserve_fetcher``/``backend.scraper``)
must not be pulled into backend startup just because ``backend.refresh_exec``
is imported. This mirrors the lazy ``_get_*_status`` wrappers in
``backend/activity.py`` (see the comment above ``_get_olof_fetch_status``
there).
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from collections.abc import Callable
from typing import NamedTuple

from backend import config_version, refresh
from backend import db as database
from backend.job_progress import JobState, JobStopped

logger = logging.getLogger(__name__)


class StepExecutor(NamedTuple):
    """How the chain runs (or does not run) one ``refresh.STEPS`` entry.

    Attributes:
        step_id: Matches a ``backend.refresh.RefreshStep.step_id`` exactly.
        mode: ``'inproc'`` (call and await a dict), ``'job'`` (claim + start
            a background worker, then poll its status), or ``'manual'``
            (never executed by the chain).
        run: ``inproc`` only -- callable that performs the work and returns a
            counters dict.
        start: ``job`` only -- callable that claims and starts the worker,
            returning ``False`` if it is already busy.
        status: ``job`` only -- callable returning a ``JobState``-shaped
            progress dict (``running``/``done``/``total``/...).
        stop: ``job`` only -- callable that requests the worker stop.
        reason: ``manual`` only -- one-line, honest explanation of why this
            step cannot be chained yet, shown verbatim by the GUI.
    """

    step_id: str
    mode: str
    run: Callable[..., dict] | None
    start: Callable[..., bool] | None
    status: Callable[[], dict] | None
    stop: Callable[[], None] | None
    reason: str | None


# ── inproc wrappers ─────────────────────────────────────────────────────────
# Each wrapper imports its target module inside the function body so the
# import cost (and any heavy transitive dependency) is paid only when the
# step actually runs.

def _run_olof_parse(**kwargs) -> dict:
    from backend import olof_parser
    return olof_parser.run_parse(**kwargs)


def _run_bobserve_parse(**kwargs) -> dict:
    from backend import bobserve_parser
    return bobserve_parser.run_parse(**kwargs)


def _run_parse_lineage(**kwargs) -> dict:
    from tools import parse_lineage
    return parse_lineage.run(**kwargs)


def _run_attribute_tapers(**kwargs) -> dict:
    from tools import attribute_tapers
    return attribute_tapers.run(**kwargs)


def _run_compute_show_picks(**kwargs) -> dict:
    from tools import compute_show_picks
    return compute_show_picks.run(**kwargs)


def _run_song_index(**kwargs) -> dict:
    from backend import song_index
    return song_index.run(**kwargs)


def _run_ranker_rerank(**kwargs) -> dict:
    from backend import ranker_jobs
    return ranker_jobs.run_rerank(**kwargs)


# ── job wrappers ─────────────────────────────────────────────────────────
# Each start() mirrors the claim-then-thread sequence its own
# POST /api/.../<start-route> already uses in backend/app.py, so a chained
# run and a direct GUI run behave identically.

def _start_olof_fetch(**kwargs) -> bool:
    from backend import olof_fetcher
    corpus = kwargs.get("corpus", "all")
    if not olof_fetcher.try_begin(stage="queued", corpus=corpus):
        return False
    threading.Thread(
        target=olof_fetcher.run_fetch_claimed,
        kwargs={
            "corpus": corpus,
            "limit": kwargs.get("limit"),
            "refresh": bool(kwargs.get("refresh", False)),
            "dry_run": bool(kwargs.get("dry_run", False)),
        },
        daemon=True, name="olof-fetch",
    ).start()
    return True


def _status_olof_fetch() -> dict:
    from backend import olof_fetcher
    return olof_fetcher.get_status()


def _stop_olof_fetch() -> None:
    from backend import olof_fetcher
    olof_fetcher.stop()


def _start_bobserve_fetch(**kwargs) -> bool:
    from backend import bobserve_fetcher
    if not bobserve_fetcher.try_begin(
        stage="queued", start_year=kwargs.get("start_year"), end_year=kwargs.get("end_year"),
    ):
        return False
    fetch_kwargs = {
        "limit": kwargs.get("limit"),
        "refresh": bool(kwargs.get("refresh", False)),
        "dry_run": bool(kwargs.get("dry_run", False)),
    }
    if kwargs.get("start_year") is not None:
        fetch_kwargs["start_year"] = kwargs["start_year"]
    if kwargs.get("end_year") is not None:
        fetch_kwargs["end_year"] = kwargs["end_year"]
    threading.Thread(
        target=bobserve_fetcher.run_fetch_claimed, kwargs=fetch_kwargs,
        daemon=True, name="bobserve-fetch",
    ).start()
    return True


def _status_bobserve_fetch() -> dict:
    from backend import bobserve_fetcher
    return bobserve_fetcher.get_status()


def _stop_bobserve_fetch() -> None:
    from backend import bobserve_fetcher
    bobserve_fetcher.stop()


def _start_ranker_scan(**kwargs) -> bool:
    from backend import ranker_jobs
    mode = kwargs.get("mode", "backlog")
    if not ranker_jobs.try_begin(stage="queued", mode=mode):
        return False
    try:
        plan = ranker_jobs.plan_scan(mode=mode, lbs=kwargs.get("lb"))
    except Exception:
        ranker_jobs.finish(stage="error")
        raise
    if plan["planned"] == 0:
        ranker_jobs.finish(stage="done")
        return True
    threading.Thread(
        target=ranker_jobs.run_scan_claimed,
        kwargs={
            "worklist": plan["worklist"], "scan_id": plan["scan_id"],
            "workers": kwargs.get("workers"),
        },
        daemon=True, name="ranker-scan",
    ).start()
    return True


def _status_ranker_scan() -> dict:
    from backend import ranker_jobs
    return ranker_jobs.get_status()


def _stop_ranker_scan() -> None:
    from backend import ranker_jobs
    ranker_jobs.stop()


def _start_geocode(**kwargs) -> bool:
    from backend import geocoder
    with geocoder._lock:
        if geocoder._progress.get("running"):
            return False
    threading.Thread(
        target=geocoder.run_batch,
        kwargs={
            "limit": kwargs.get("limit"),
            "retry_failed": bool(kwargs.get("retry_failed", False)),
        },
        daemon=True, name="geocode-batch",
    ).start()
    return True


def _status_geocode() -> dict:
    from backend import geocoder
    return geocoder.get_progress()


def _stop_geocode() -> None:
    from backend import geocoder
    geocoder.stop()


def _start_scrape_entries(**kwargs) -> bool:
    """Start a chained scrape exactly as POST /api/scrape/start would.

    Goes through ``backend.app._start_scrape_thread`` rather than spawning a
    thread onto ``scraper.scrape_range`` directly, for two reasons: it is the
    owner of the module-level ``_scrape_thread`` guard that stops a second
    scrape from starting, and it is where the user's ``scrape_delay_ms`` /
    ``scrape_attachments`` / ``use_local_pages`` settings are applied. A
    chained scrape that ignored the configured politeness delay would hit the
    site harder than the same scrape started from the GUI.

    ``backend.app`` is imported inside the function (the deferred-import
    pattern ``activity.py`` documents): by the time a chain runs, app has
    finished loading, so this is deferred rather than circular.
    """
    from backend import app as _app
    from backend import db as _db
    from backend import scraper
    if scraper.get_scrape_status().get("running"):
        return False
    lb_numbers = scraper.plan_range(kwargs.get("start_lb", 1), kwargs.get("end_lb"))
    _app._start_scrape_thread(
        lb_numbers,
        force=bool(kwargs.get("force", False)),
        delay_ms=int(_db.get_meta("scrape_delay_ms") or 1500),
        download=_db.get_meta("scrape_attachments") != "0",
        use_local_pages=_db.get_meta("use_local_pages") == "1",
    )
    return True


def _status_scrape_entries() -> dict:
    from backend import scraper
    return scraper.get_scrape_status()


def _stop_scrape_entries() -> None:
    from backend import scraper
    scraper.stop_scrape()


# ── the registry ─────────────────────────────────────────────────────────
# Tiering table (spec PIPELINE_REFRESH_PHASE3.md §3.1). `manual` is not a
# permanent verdict -- it is "not wired in Phase 3"; each entry's `reason` is
# what the GUI shows verbatim in the preview dialog's "won't run" section.
EXECUTORS: dict[str, StepExecutor] = {
    # ── inproc ───────────────────────────────────────────────────────────
    "olof_parse": StepExecutor(
        "olof_parse", "inproc", _run_olof_parse, None, None, None, None,
    ),
    "bobserve_parse": StepExecutor(
        "bobserve_parse", "inproc", _run_bobserve_parse, None, None, None, None,
    ),
    "parse_lineage": StepExecutor(
        "parse_lineage", "inproc", _run_parse_lineage, None, None, None, None,
    ),
    "attribute_tapers": StepExecutor(
        "attribute_tapers", "inproc", _run_attribute_tapers, None, None, None, None,
    ),
    "compute_show_picks": StepExecutor(
        "compute_show_picks", "inproc", _run_compute_show_picks, None, None, None, None,
    ),
    "song_index": StepExecutor(
        "song_index", "inproc", _run_song_index, None, None, None, None,
    ),
    "ranker_rerank": StepExecutor(
        "ranker_rerank", "inproc", _run_ranker_rerank, None, None, None, None,
    ),
    # ── job ──────────────────────────────────────────────────────────────
    "olof_fetch": StepExecutor(
        "olof_fetch", "job", None, _start_olof_fetch, _status_olof_fetch,
        _stop_olof_fetch, None,
    ),
    "bobserve_fetch": StepExecutor(
        "bobserve_fetch", "job", None, _start_bobserve_fetch, _status_bobserve_fetch,
        _stop_bobserve_fetch, None,
    ),
    "ranker_scan": StepExecutor(
        "ranker_scan", "job", None, _start_ranker_scan, _status_ranker_scan,
        _stop_ranker_scan, None,
    ),
    "geocode": StepExecutor(
        "geocode", "job", None, _start_geocode, _status_geocode, _stop_geocode, None,
    ),
    "scrape_entries": StepExecutor(
        "scrape_entries", "job", None, _start_scrape_entries, _status_scrape_entries,
        _stop_scrape_entries, None,
    ),
    # ── manual ───────────────────────────────────────────────────────────
    "flat_file_apply": StepExecutor(
        "flat_file_apply", "manual", None, None, None, None,
        "needs a chosen release file",
    ),
    "db_import": StepExecutor(
        "db_import", "manual", None, None, None, None,
        "needs a human-reviewed import diff",
    ),
    "lb_master_reconcile": StepExecutor(
        "lb_master_reconcile", "manual", None, None, None, None,
        "reconciliation decisions need human review",
    ),
    "setlist_fingerprint": StepExecutor(
        "setlist_fingerprint", "manual", None, None, None, None,
        "surfaces suggestions for human triage",
    ),
    "pipeline_run": StepExecutor(
        "pipeline_run", "manual", None, None, None, None,
        "needs a chosen folder scope",
    ),
    "tapematch_sync": StepExecutor(
        "tapematch_sync", "manual", None, None, None, None,
        "manual trigger only, by design",
    ),
    "xref_ingest": StepExecutor(
        "xref_ingest", "manual", None, None, None, None,
        "staged filesets need human approval",
    ),
    "attachments_reconcile": StepExecutor(
        "attachments_reconcile", "manual", None, None, None, None,
        "no completion signal",
    ),
    "mirror_crawl": StepExecutor(
        "mirror_crawl", "manual", None, None, None, None,
        "long-running crawl with no defined completion",
    ),
    "wtrf_crawl": StepExecutor(
        "wtrf_crawl", "manual", None, None, None, None,
        "long-running crawl with no defined completion",
    ),
    "bootleg_scrape": StepExecutor(
        "bootleg_scrape", "manual", None, None, None, None,
        "long-running external scrape",
    ),
    "master_publish": StepExecutor(
        "master_publish", "manual", None, None, None, None,
        "human gate: publishes a public release",
    ),
    "sitedata_publish": StepExecutor(
        "sitedata_publish", "manual", None, None, None, None,
        "human gate: publishes a public release",
    ),
    "preservation": StepExecutor(
        "preservation", "manual", None, None, None, None,
        "long-running external upload with no completion signal",
    ),
    "archive_org": StepExecutor(
        "archive_org", "manual", None, None, None, None,
        "long-running external upload with no completion signal",
    ),
}


def _pull_stale_ancestors(seed_ids, steps_by_id: dict[str, dict]) -> set[str]:
    """Extend ``seed_ids`` with the transitive stale-ancestor closure.

    Walks ``upstream`` from every seed. A ``stale`` ancestor is added to the
    work set and its own upstream is walked in turn (a stale step may itself
    depend on a further stale step). A ``blocked`` ancestor is *not* added --
    it contributes its own ancestors instead, per spec Sec 3.1 ("a blocked
    ancestor contributes its own ancestors, not itself-as-work"). ``fresh``
    and ``unknown`` ancestors stop the walk on that branch.

    Args:
        seed_ids: Iterable of step_ids to walk upstream from. Not itself
            filtered by state -- callers decide which ids seed the walk.
        steps_by_id: step_id -> the step dict from ``compute_plan()["steps"]``.

    Returns:
        The seed ids plus every stale ancestor reached by the walk.
    """
    work: set[str] = set(seed_ids)
    visited: set[str] = set()

    def _walk(step_id: str) -> None:
        if step_id in visited:
            return
        visited.add(step_id)
        info = steps_by_id.get(step_id)
        if info is None:
            return
        for upstream_id in info["upstream"]:
            upstream_info = steps_by_id.get(upstream_id)
            if upstream_info is None:
                continue
            upstream_state = upstream_info["state"]
            if upstream_state == "stale":
                work.add(upstream_id)
                _walk(upstream_id)
            elif upstream_state == "blocked":
                _walk(upstream_id)

    for seed_id in list(seed_ids):
        _walk(seed_id)
    return work


def plan_chain(
    *,
    step_id: str | None = None,
    trigger: str | None = None,
    include_expensive: bool = False,
    db_path: str | None = None,
) -> dict:
    """Plan the ordered chain of steps a "run this" or "run this trigger" needs.

    Read-only: calls ``refresh.compute_plan()`` once and does not execute or
    claim anything. See spec PIPELINE_REFRESH_PHASE3.md Sec 3.1.

    Args:
        step_id: Per-step scope -- plan the target step plus its stale (and
            stale-through-blocked) ancestors. Mutually exclusive with
            ``trigger``.
        trigger: Per-trigger scope (e.g. ``'T1'``) -- plan every stale/blocked
            step of that trigger plus the stale ancestors they depend on,
            even across trigger boundaries. Mutually exclusive with
            ``step_id``.
        include_expensive: When False (the default), ``cost='very_slow'`` and
            ``human_gate=True`` steps are moved from ``runnable`` to
            ``excluded`` rather than executed.
        db_path: Optional DB path override, forwarded to ``compute_plan()``.

    Returns:
        A dict with ``scope``, ``runnable``, ``excluded``, ``manual``,
        ``blocked_by_running``, and ``planned_at`` keys (see spec Sec 3.1 for
        the exact shape).

    Raises:
        ValueError: if neither or both of ``step_id``/``trigger`` are given.
    """
    if (step_id is None) == (trigger is None):
        raise ValueError("plan_chain requires exactly one of step_id or trigger")

    plan = refresh.compute_plan(db_path=db_path)
    steps_by_id = {s["step_id"]: s for s in plan["steps"]}
    order = refresh._topological_order()
    order_index = {sid: i for i, sid in enumerate(order)}

    if step_id is not None:
        if step_id not in steps_by_id:
            raise ValueError(f"plan_chain: unknown step_id {step_id!r}")
        work_ids = _pull_stale_ancestors({step_id}, steps_by_id)
    else:
        seed_ids = {
            sid for sid, info in steps_by_id.items()
            if info["trigger"] == trigger and info["state"] in ("stale", "blocked")
        }
        work_ids = _pull_stale_ancestors(seed_ids, steps_by_id)

    ordered_ids = sorted(work_ids, key=lambda sid: order_index[sid])

    runnable: list[dict] = []
    excluded: list[dict] = []
    manual: list[dict] = []
    blocked_by_running: list[str] = []

    for sid in ordered_ids:
        info = steps_by_id[sid]
        executor = EXECUTORS.get(sid)
        # Forward-compat (Phase 4): a 'needs_you' state is non-runnable, same
        # as 'manual' -- there is nothing else to build for it in Phase 3.
        if executor is None or executor.mode == "manual" or info["state"] == "needs_you":
            if info["state"] == "needs_you":
                why = "waiting on a human review queue"
            elif executor is None:
                why = "no executor registered"
            else:
                why = executor.reason
            manual.append({"step_id": sid, "why": why})
            continue

        if not include_expensive and (info["cost"] == "very_slow" or info["human_gate"]):
            why = "very_slow" if info["cost"] == "very_slow" else "human_gate"
            excluded.append({"step_id": sid, "why": why})
            continue

        # Only a step the chain would actually run can block its start --
        # a busy worker for an *excluded* step is none of this chain's
        # business, and 409ing over it would be a false positive.
        if executor.mode == "job" and executor.status is not None:
            try:
                status = executor.status()
            except Exception:
                status = {}
            if status.get("running"):
                blocked_by_running.append(sid)

        runnable.append({
            "step_id": sid,
            "mode": executor.mode,
            "cost": info["cost"],
            "state": info["state"],
            "reason": info["reason"],
        })

    return {
        "scope": {"step_id": step_id, "trigger": trigger, "include_expensive": include_expensive},
        "runnable": runnable,
        "excluded": excluded,
        "manual": manual,
        "blocked_by_running": blocked_by_running,
        "planned_at": _dt.datetime.now().isoformat(),
    }


# ── the chain job ────────────────────────────────────────────────────────
# One JobState claim covers the whole chain (decision 3, spec §3.1) -- the
# route claims it before spawning the thread, exactly the race-free
# claim-then-thread sequence Phase 2's workers use (see ranker_jobs.py).
_CHAIN = JobState("refresh-chain")


def get_status() -> dict:
    """Return the running chain's progress snapshot."""
    return _CHAIN.snapshot()


def stop() -> None:
    """Request that the active chain stop as soon as possible."""
    _CHAIN.stop()


def try_begin(**fields) -> bool:
    """Atomically claim the chain job. See ``JobState.try_begin``."""
    return _CHAIN.try_begin(**fields)


def finish(**fields) -> None:
    """Release a claim taken by ``try_begin()`` without running a chain.

    Used by the route when ``plan_chain()`` (synchronous, called again inside
    the route to re-plan server-side) finds nothing runnable, so the claim
    doesn't wedge the chain in 'running' state forever -- the normal case (a
    chain thread was actually started) finishes via ``run_chain_claimed``'s
    own call to this instead.
    """
    _CHAIN.finish(**fields)


def run_chain_claimed(plan: dict, db_path: str | None = None) -> dict:
    """Thread target for POST /api/refresh/chain/start -- job already claimed.

    Runs ``plan["runnable"]`` strictly in order (spec Sec 3.1, decisions 3
    and 5). The step list is frozen at preview time: this function never
    calls ``plan_chain()``/``refresh.compute_plan()`` again, only the two
    cheap per-step primitives (``refresh._run_scalar``, ``refresh.
    _version_signal``) to decide whether a step has become fresh since the
    plan was made.

    Per step: ``check_stop()`` first (an in-flight ``job`` step is also
    asked to stop via its own ``stop()``, so a chain stop during a fetch
    behaves as it does today); re-evaluate freshness and skip as ``noop``
    when backlog is 0 and the version signal isn't ``'changed'``; otherwise
    run it (``inproc``: call and await the dict; ``job``: claim + start,
    then poll ``status()`` every 1.0s via ``_CHAIN.sleep(1.0)`` until
    ``running`` is false, mirroring ``done``/``total`` into ``sub_progress``);
    record a ``refresh_step_runs`` row with ``trigger_source='chain'`` and
    stamp the step's config version on success. An exception halts the chain
    (downstream steps would consume a failed step's output) and the chain
    returns ``status='partial'``; a stop between steps halts it too and the
    chain returns ``status='stopped'``. Always writes exactly one
    ``refresh_chain_runs`` row before returning.

    Args:
        plan: The frozen ``plan_chain()`` dict this chain is executing.
        db_path: Optional database path override.

    Returns:
        ``{"status": "ok"|"partial"|"stopped", "ran": [...], "skipped":
        [...], "errors": [{"step_id", "message"}], "started_at",
        "finished_at"}``.
    """
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = refresh.get_connection(db_path)
    scope = plan.get("scope") or {}
    scope_kind = "step" if scope.get("step_id") else "trigger"
    scope_value = scope.get("step_id") or scope.get("trigger") or ""

    runnable = plan.get("runnable") or []
    ran: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    status = "ok"

    _CHAIN.update(stage="running", total=len(runnable), done=0, current="", sub_progress={})

    try:
        for item in runnable:
            step_id = item["step_id"]
            try:
                _CHAIN.check_stop()
            except JobStopped:
                status = "stopped"
                break

            _CHAIN.update(current=step_id, sub_progress={})

            step = refresh._STEPS_BY_ID.get(step_id)
            executor = EXECUTORS.get(step_id)
            if step is None or executor is None or executor.mode not in ("inproc", "job"):
                # Registry-integrity tests guarantee this can't happen for a
                # frozen `runnable` entry, but degrade rather than crash.
                skipped.append({"step_id": step_id, "reason": "no executor"})
                _CHAIN.bump("done")
                continue

            backlog = refresh._run_scalar(conn, step.backlog_sql)
            try:
                backlog = int(backlog) if backlog is not None else None
            except (TypeError, ValueError):
                backlog = None
            version = refresh._version_signal(conn, step)

            if backlog == 0 and version["state"] != "changed":
                step_started = time.strftime("%Y-%m-%d %H:%M:%S")
                database.record_step_run(
                    step_id, status="noop", started_at=step_started,
                    trigger_source="chain", db_path=db_path,
                )
                skipped.append({"step_id": step_id, "status": "noop"})
                _CHAIN.bump("done")
                continue

            step_started = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                if executor.mode == "inproc":
                    counters = executor.run()
                else:
                    if not executor.start():
                        raise RuntimeError(f"{step_id}: worker busy, cannot start")
                    while True:
                        try:
                            _CHAIN.sleep(1.0)
                        except JobStopped:
                            if executor.stop is not None:
                                executor.stop()
                            raise
                        job_status = executor.status() or {}
                        _CHAIN.update(sub_progress={
                            "done": job_status.get("done"),
                            "total": job_status.get("total"),
                        })
                        if not job_status.get("running"):
                            break
                    counters = job_status
            except JobStopped:
                status = "stopped"
                break
            except Exception as exc:
                logger.exception("refresh_exec chain: step %s failed", step_id)
                database.record_step_run(
                    step_id, status="error", started_at=step_started,
                    trigger_source="chain", db_path=db_path,
                )
                errors.append({"step_id": step_id, "message": str(exc)})
                status = "partial"
                break

            database.record_step_run(
                step_id, status="ok", started_at=step_started,
                counters=counters if isinstance(counters, dict) else None,
                trigger_source="chain", db_path=db_path,
            )
            config_version.stamp_for_step(step_id, db_path)
            ran.append({"step_id": step_id, "status": "ok"})
            _CHAIN.bump("done")

        finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        database.record_chain_run(
            scope_kind, scope_value, status=status, started_at=started_at,
            finished_at=finished_at,
            steps={"plan": plan, "ran": ran, "skipped": skipped, "errors": errors},
            db_path=db_path,
        )
        return {
            "status": status, "ran": ran, "skipped": skipped, "errors": errors,
            "started_at": started_at, "finished_at": finished_at,
        }
    finally:
        _CHAIN.finish(stage="done", current="")
