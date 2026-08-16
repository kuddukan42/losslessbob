"""Registry-integrity tests for backend/refresh_exec.py (TODO-306 Phase 3).

This bite only ships the executor registry (StepExecutor, EXECUTORS) -- no
plan_chain, no run_chain_claimed. These tests cover exactly the registry
slice of spec §5 (PIPELINE_REFRESH_PHASE3.md): STEPS<->EXECUTORS bijection,
every manual reason non-empty, and every inproc/job entry's underlying
module+attribute actually resolving (import only, never called -- a call
would hit the network, audio decode, or the write queue).
"""

from __future__ import annotations

import importlib
import os
import tempfile

import backend.db as db
import backend.job_progress as job_progress
import backend.refresh as refresh_mod
import backend.refresh_exec as refresh_exec_mod
from backend.refresh import STEPS, RefreshStep, _topological_order, compute_plan
from backend.refresh_exec import EXECUTORS, StepExecutor, plan_chain

# step_id -> (module path, [attribute names]) the wrapper functions in
# refresh_exec.py resolve lazily. Kept independent of refresh_exec's own
# wrapper bodies so the test verifies the real target, not the wrapper.
_INPROC_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "olof_parse": ("backend.olof_parser", ("run_parse",)),
    "bobserve_parse": ("backend.bobserve_parser", ("run_parse",)),
    "parse_lineage": ("tools.parse_lineage", ("run",)),
    "attribute_tapers": ("tools.attribute_tapers", ("run",)),
    "compute_show_picks": ("tools.compute_show_picks", ("run",)),
    "song_index": ("backend.song_index", ("run",)),
    "ranker_rerank": ("backend.ranker_jobs", ("run_rerank",)),
}

_JOB_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "olof_fetch": ("backend.olof_fetcher", ("try_begin", "run_fetch_claimed", "get_status", "stop")),
    "bobserve_fetch": (
        "backend.bobserve_fetcher", ("try_begin", "run_fetch_claimed", "get_status", "stop"),
    ),
    "ranker_scan": (
        "backend.ranker_jobs",
        ("try_begin", "plan_scan", "run_scan_claimed", "finish", "get_status", "stop"),
    ),
    "geocode": ("backend.geocoder", ("run_batch", "get_progress", "stop")),
    "scrape_entries": ("backend.scraper", ("plan_range", "scrape_range", "get_scrape_status", "stop_scrape")),
}


def test_every_step_has_exactly_one_executor() -> None:
    step_ids = [s.step_id for s in STEPS]
    assert len(step_ids) == len(set(step_ids)), "duplicate step_id in STEPS"
    assert set(step_ids) == set(EXECUTORS.keys())


def test_every_executor_key_is_a_real_step_id() -> None:
    step_ids = {s.step_id for s in STEPS}
    for key in EXECUTORS:
        assert key in step_ids


def test_executor_step_id_field_matches_its_key() -> None:
    for key, executor in EXECUTORS.items():
        assert executor.step_id == key


def test_every_manual_entry_has_a_nonempty_reason() -> None:
    for step_id, executor in EXECUTORS.items():
        if executor.mode == "manual":
            assert executor.reason and executor.reason.strip(), step_id
            assert executor.run is None
            assert executor.start is None
            assert executor.status is None
            assert executor.stop is None


def test_every_inproc_entry_has_only_run_populated() -> None:
    for step_id, executor in EXECUTORS.items():
        if executor.mode == "inproc":
            assert executor.run is not None, step_id
            assert executor.start is None
            assert executor.status is None
            assert executor.stop is None
            assert executor.reason is None


def test_every_job_entry_has_start_status_stop_populated() -> None:
    for step_id, executor in EXECUTORS.items():
        if executor.mode == "job":
            assert executor.start is not None, step_id
            assert executor.status is not None, step_id
            assert executor.stop is not None, step_id
            assert executor.run is None
            assert executor.reason is None


def test_inproc_targets_cover_every_inproc_executor() -> None:
    inproc_ids = {sid for sid, ex in EXECUTORS.items() if ex.mode == "inproc"}
    assert inproc_ids == set(_INPROC_TARGETS.keys())


def test_job_targets_cover_every_job_executor() -> None:
    job_ids = {sid for sid, ex in EXECUTORS.items() if ex.mode == "job"}
    assert job_ids == set(_JOB_TARGETS.keys())


def test_inproc_targets_resolve() -> None:
    """Import each inproc target module and confirm the attribute exists.

    Import only -- never calls the resolved callable (a real call would parse
    real mirror data, recompute the DB wholesale, or hit the write queue).
    """
    for step_id, (module_path, attrs) in _INPROC_TARGETS.items():
        module = importlib.import_module(module_path)
        for attr in attrs:
            assert hasattr(module, attr), f"{step_id}: {module_path}.{attr} missing"
            assert callable(getattr(module, attr)), f"{step_id}: {module_path}.{attr} not callable"


def test_job_targets_resolve() -> None:
    """Import each job target module and confirm its worker surface exists.

    Import only -- never calls try_begin/start/etc (a real call would claim
    a JobState, spawn a thread, or hit the network).
    """
    for step_id, (module_path, attrs) in _JOB_TARGETS.items():
        module = importlib.import_module(module_path)
        for attr in attrs:
            assert hasattr(module, attr), f"{step_id}: {module_path}.{attr} missing"
            assert callable(getattr(module, attr)), f"{step_id}: {module_path}.{attr} not callable"


def test_manual_count_matches_spec_tiering() -> None:
    """27 STEPS total (spec §3.1): 7 inproc + 5 job + 15 manual."""
    modes = [ex.mode for ex in EXECUTORS.values()]
    assert modes.count("inproc") == 7
    assert modes.count("job") == 5
    assert modes.count("manual") == 15
    assert len(modes) == 27


# ── plan_chain ───────────────────────────────────────────────────────────
# Synthetic DBs built the way tests/test_refresh.py does: db.init_db() gives
# the full (empty) schema, then db.record_step_run(..., status="error")
# forces a specific step 'stale' ("last run failed") without needing to
# reverse-engineer each step's backlog_sql table. This is enough to build
# every scope/ordering/exclusion case in spec §5 against the real STEPS DAG.

def _make_db_path() -> str:
    """Create a fresh temp DB with full schema and return its path."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_refresh_exec_")
    db_path = os.path.join(tmp_dir, "test.db")
    db.init_db(db_path)
    return db_path


def _all_work_ids(plan: dict) -> list[str]:
    return (
        [s["step_id"] for s in plan["runnable"]]
        + [s["step_id"] for s in plan["excluded"]]
        + [s["step_id"] for s in plan["manual"]]
    )


def test_plan_chain_requires_exactly_one_scope_arg() -> None:
    db_path = _make_db_path()
    try:
        plan_chain(db_path=db_path)
        assert False, "expected ValueError for neither step_id nor trigger"
    except ValueError:
        pass
    try:
        plan_chain(step_id="olof_parse", trigger="T3", db_path=db_path)
        assert False, "expected ValueError for both step_id and trigger"
    except ValueError:
        pass


def _assert_buckets_are_topological_subsequences(plan: dict) -> None:
    """Each of runnable/excluded/manual must individually be topo-ordered.

    (The three buckets are a *partition* of the frozen topo-ordered work
    list, not concatenated into one ordering -- a manual/excluded step in
    the middle of the topo order does not appear between runnable steps.)
    """
    order = _topological_order()
    order_index = {sid: i for i, sid in enumerate(order)}
    for bucket_ids in (
        [s["step_id"] for s in plan["runnable"]],
        [s["step_id"] for s in plan["excluded"]],
        [s["step_id"] for s in plan["manual"]],
    ):
        indices = [order_index[sid] for sid in bucket_ids]
        assert indices == sorted(indices), bucket_ids


def test_plan_chain_ordering_is_topological_subsequence_step_scope() -> None:
    db_path = _make_db_path()
    db.record_step_run("db_import", status="error", db_path=db_path)
    plan = plan_chain(step_id="parse_lineage", db_path=db_path)
    _assert_buckets_are_topological_subsequences(plan)


def test_plan_chain_ordering_is_topological_subsequence_trigger_scope() -> None:
    db_path = _make_db_path()
    db.record_step_run("scrape_entries", status="error", db_path=db_path)
    plan = plan_chain(trigger="T3", db_path=db_path)
    _assert_buckets_are_topological_subsequences(plan)


def test_plan_chain_step_scope_pulls_stale_ancestor_not_fresh_one() -> None:
    """geocode upstream=(scrape_entries[T1], olof_parse[T3]).

    scrape_entries forced stale; olof_parse stays fresh (backlog 0, no run
    rows). The plan must include scrape_entries and must not include
    olof_parse.
    """
    db_path = _make_db_path()
    db.record_step_run("scrape_entries", status="error", db_path=db_path)
    plan = plan_chain(step_id="geocode", db_path=db_path)
    ids = set(_all_work_ids(plan))
    assert ids == {"geocode", "scrape_entries"}


def test_plan_chain_blocked_ancestor_contributes_its_ancestors_not_itself() -> None:
    """db_import forced stale -> scrape_entries becomes blocked (not stale).

    parse_lineage's only upstream is scrape_entries. Per spec, a blocked
    ancestor contributes its own ancestors (db_import) rather than itself.
    """
    db_path = _make_db_path()
    db.record_step_run("db_import", status="error", db_path=db_path)

    plan_snapshot = compute_plan(db_path=db_path)
    by_id = {s["step_id"]: s for s in plan_snapshot["steps"]}
    assert by_id["db_import"]["state"] == "stale"
    assert by_id["scrape_entries"]["state"] == "blocked"

    plan = plan_chain(step_id="parse_lineage", db_path=db_path)
    ids = set(_all_work_ids(plan))
    assert ids == {"parse_lineage", "db_import"}
    assert "scrape_entries" not in ids


def test_plan_chain_trigger_scope_crosses_trigger_boundary() -> None:
    """T3 trigger scope must pull in a stale T1 prerequisite (geocode's case)."""
    db_path = _make_db_path()
    db.record_step_run("scrape_entries", status="error", db_path=db_path)

    plan_snapshot = compute_plan(db_path=db_path)
    by_id = {s["step_id"]: s for s in plan_snapshot["steps"]}
    assert by_id["geocode"]["state"] == "blocked"
    assert by_id["scrape_entries"]["trigger"] == "T1"

    plan = plan_chain(trigger="T3", db_path=db_path)
    ids = set(_all_work_ids(plan))
    assert "geocode" in ids
    assert "scrape_entries" in ids, "T1 stale prerequisite must cross into the T3 plan"


def test_plan_chain_include_expensive_moves_very_slow_between_buckets() -> None:
    db_path = _make_db_path()
    db.record_step_run("ranker_scan", status="error", db_path=db_path)

    excluded_plan = plan_chain(trigger="T2", include_expensive=False, db_path=db_path)
    excluded_ids = {s["step_id"] for s in excluded_plan["excluded"]}
    runnable_ids = {s["step_id"] for s in excluded_plan["runnable"]}
    assert "ranker_scan" in excluded_ids
    assert "ranker_scan" not in runnable_ids
    assert next(
        s["why"] for s in excluded_plan["excluded"] if s["step_id"] == "ranker_scan"
    ) == "very_slow"

    included_plan = plan_chain(trigger="T2", include_expensive=True, db_path=db_path)
    included_runnable_ids = {s["step_id"] for s in included_plan["runnable"]}
    included_excluded_ids = {s["step_id"] for s in included_plan["excluded"]}
    assert "ranker_scan" in included_runnable_ids
    assert "ranker_scan" not in included_excluded_ids


def test_plan_chain_blocked_by_running_populated_from_job_status(monkeypatch) -> None:
    db_path = _make_db_path()
    db.record_step_run("ranker_scan", status="error", db_path=db_path)

    import backend.refresh_exec as refresh_exec

    fake_executor = StepExecutor(
        "ranker_scan", "job", None,
        lambda **kw: False, lambda: {"running": True}, lambda: None, None,
    )
    monkeypatch.setitem(refresh_exec.EXECUTORS, "ranker_scan", fake_executor)

    plan = refresh_exec.plan_chain(
        step_id="ranker_scan", include_expensive=True, db_path=db_path,
    )
    assert "ranker_scan" in plan["blocked_by_running"]


# ── run_chain_claimed ────────────────────────────────────────────────────
# Three synthetic steps, monkeypatched entirely into refresh._STEPS_BY_ID and
# refresh_exec.EXECUTORS -- zero network, zero audio, no real worker. Fake
# run/start/status/stop callables record their calls in a plain list so
# ordering and invoke-vs-skip are directly assertable.

def _fake_step(step_id: str) -> RefreshStep:
    return RefreshStep(
        step_id=step_id, label=step_id, trigger="T1", kind="incremental",
        backlog_sql=None, last_run_sql=None, version_key=None,
        upstream=(), how_to_run="test", cost="fast", human_gate=False,
    )


def _install_fake_steps(monkeypatch, step_ids) -> None:
    for sid in step_ids:
        monkeypatch.setitem(refresh_mod._STEPS_BY_ID, sid, _fake_step(sid))


def _frozen_plan(step_ids: list[str], scope_step_id: str = "fake_a") -> dict:
    return {
        "scope": {"step_id": scope_step_id, "trigger": None, "include_expensive": False},
        "runnable": [
            {"step_id": sid, "mode": "inproc", "cost": "fast",
             "state": "stale", "reason": "test"}
            for sid in step_ids
        ],
        "excluded": [], "manual": [], "blocked_by_running": [],
        "planned_at": "2026-01-01T00:00:00",
    }


def test_run_chain_claimed_order_preserved_and_records_rows(monkeypatch) -> None:
    db_path = _make_db_path()
    calls: list[str] = []
    _install_fake_steps(monkeypatch, ["fake_a", "fake_b", "fake_c"])
    for sid in ("fake_a", "fake_b", "fake_c"):
        executor = StepExecutor(
            sid, "inproc",
            (lambda sid=sid: (calls.append(sid), {"n": 1})[1]),
            None, None, None, None,
        )
        monkeypatch.setitem(refresh_exec_mod.EXECUTORS, sid, executor)

    plan = _frozen_plan(["fake_a", "fake_b", "fake_c"])
    result = refresh_exec_mod.run_chain_claimed(plan, db_path=db_path)

    assert calls == ["fake_a", "fake_b", "fake_c"]
    assert result["status"] == "ok"
    assert [r["step_id"] for r in result["ran"]] == ["fake_a", "fake_b", "fake_c"]

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, trigger_source FROM refresh_step_runs ORDER BY id"
    ).fetchall()
    assert [(r["step_id"], r["trigger_source"]) for r in rows] == [
        ("fake_a", "chain"), ("fake_b", "chain"), ("fake_c", "chain"),
    ]
    chain_rows = conn.execute("SELECT status FROM refresh_chain_runs").fetchall()
    assert len(chain_rows) == 1
    assert chain_rows[0]["status"] == "ok"


def test_run_chain_claimed_failure_halts_chain(monkeypatch) -> None:
    db_path = _make_db_path()
    calls: list[str] = []
    _install_fake_steps(monkeypatch, ["fake_a", "fake_b", "fake_c"])

    def _ok(sid: str) -> dict:
        calls.append(sid)
        return {"n": 1}

    def _boom(sid: str) -> dict:
        calls.append(sid)
        raise RuntimeError("boom")

    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_a",
        StepExecutor("fake_a", "inproc", lambda: _ok("fake_a"), None, None, None, None),
    )
    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_b",
        StepExecutor("fake_b", "inproc", lambda: _boom("fake_b"), None, None, None, None),
    )
    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_c",
        StepExecutor("fake_c", "inproc", lambda: _ok("fake_c"), None, None, None, None),
    )

    plan = _frozen_plan(["fake_a", "fake_b", "fake_c"])
    result = refresh_exec_mod.run_chain_claimed(plan, db_path=db_path)

    assert calls == ["fake_a", "fake_b"], "fake_c must never be called after fake_b fails"
    assert result["status"] == "partial"
    assert len(result["errors"]) == 1
    assert result["errors"][0]["step_id"] == "fake_b"

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, status FROM refresh_step_runs ORDER BY id"
    ).fetchall()
    assert [(r["step_id"], r["status"]) for r in rows] == [
        ("fake_a", "ok"), ("fake_b", "error"),
    ]
    chain_rows = conn.execute("SELECT status FROM refresh_chain_runs").fetchall()
    assert chain_rows[0]["status"] == "partial"


def test_run_chain_claimed_stop_between_steps(monkeypatch) -> None:
    db_path = _make_db_path()
    calls: list[str] = []
    _install_fake_steps(monkeypatch, ["fake_a", "fake_b"])

    def _run_a() -> dict:
        calls.append("fake_a")
        refresh_exec_mod.stop()
        return {"n": 1}

    def _run_b() -> dict:
        calls.append("fake_b")
        return {"n": 1}

    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_a",
        StepExecutor("fake_a", "inproc", _run_a, None, None, None, None),
    )
    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_b",
        StepExecutor("fake_b", "inproc", _run_b, None, None, None, None),
    )

    assert refresh_exec_mod.try_begin(stage="queued") is True
    plan = _frozen_plan(["fake_a", "fake_b"])
    result = refresh_exec_mod.run_chain_claimed(plan, db_path=db_path)

    assert calls == ["fake_a"], "fake_b must never run once a stop lands between steps"
    assert result["status"] == "stopped"
    status = refresh_exec_mod.get_status()
    assert status["running"] is False, "finish() must clear the claim"
    assert status["stop_requested"] is False, "finish() must clear the stop flag"


def test_run_chain_claimed_noop_skip_and_changed_override(monkeypatch) -> None:
    """Backlog 0 + version not 'changed' => noop, callable never invoked;
    backlog 0 + version 'changed' => invoked anyway (spec Sec 3.1 step 2)."""
    db_path = _make_db_path()
    calls: list[str] = []
    _install_fake_steps(monkeypatch, ["fake_a", "fake_b"])

    monkeypatch.setattr(refresh_mod, "_run_scalar", lambda conn, sql: 0)

    def _fake_version_signal(conn, step):
        if step.step_id == "fake_b":
            return {"key": "k", "state": "changed", "expected": "x", "stored": "y"}
        return {"key": None, "state": "n/a", "expected": None, "stored": None}

    monkeypatch.setattr(refresh_mod, "_version_signal", _fake_version_signal)

    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_a",
        StepExecutor(
            "fake_a", "inproc", lambda: (calls.append("fake_a"), {"n": 1})[1],
            None, None, None, None,
        ),
    )
    monkeypatch.setitem(
        refresh_exec_mod.EXECUTORS, "fake_b",
        StepExecutor(
            "fake_b", "inproc", lambda: (calls.append("fake_b"), {"n": 1})[1],
            None, None, None, None,
        ),
    )

    plan = _frozen_plan(["fake_a", "fake_b"])
    result = refresh_exec_mod.run_chain_claimed(plan, db_path=db_path)

    assert calls == ["fake_b"], "fake_a is noop-skipped; fake_b runs despite backlog 0"
    assert [s["step_id"] for s in result["skipped"]] == ["fake_a"]
    assert [s["step_id"] for s in result["ran"]] == ["fake_b"]
    assert result["status"] == "ok"

    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT step_id, status FROM refresh_step_runs ORDER BY id"
    ).fetchall()
    assert [(r["step_id"], r["status"]) for r in rows] == [
        ("fake_a", "noop"), ("fake_b", "ok"),
    ]


def test_run_chain_claimed_job_mode_wait_loop_mirrors_sub_progress(monkeypatch) -> None:
    db_path = _make_db_path()
    monkeypatch.setattr(job_progress.time, "sleep", lambda s: None)
    _install_fake_steps(monkeypatch, ["fake_job"])

    status_sequence = [
        {"running": True, "done": 1, "total": 3},
        {"running": True, "done": 2, "total": 3},
        {"running": False, "done": 3, "total": 3},
    ]
    calls = {"start": 0, "status": 0}

    def fake_start(**kwargs) -> bool:
        calls["start"] += 1
        return True

    def fake_status() -> dict:
        idx = min(calls["status"], len(status_sequence) - 1)
        calls["status"] += 1
        return status_sequence[idx]

    executor = StepExecutor(
        "fake_job", "job", None, fake_start, fake_status, lambda: None, None,
    )
    monkeypatch.setitem(refresh_exec_mod.EXECUTORS, "fake_job", executor)

    plan = _frozen_plan(["fake_job"], scope_step_id="fake_job")
    result = refresh_exec_mod.run_chain_claimed(plan, db_path=db_path)

    assert calls["start"] == 1
    assert calls["status"] == 3, "loop must terminate once running flips false"
    assert result["status"] == "ok"
    assert [r["step_id"] for r in result["ran"]] == ["fake_job"]

    final_status = refresh_exec_mod.get_status()
    assert final_status["sub_progress"] == {"done": 3, "total": 3}
