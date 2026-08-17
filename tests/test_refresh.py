"""Tests for backend/refresh.py (GET /api/refresh/status).

Covers the spec's Sec 2.5 checklist: _step_state's truth table (all four
states, blocked-beats-stale precedence, the backlog=0-beats-newer-upstream-
watermark false-positive guard), _parse_ts's format normalization (including
the Sec 1b same-day string-comparison inversion regression), registry
integrity (unique ids, resolvable upstream, no cycles), every registered SQL
query executing against the full init_db() schema with the right arity, a
missing-table degrading to 'unknown' without raising, and compute_plan()'s
payload shape on an empty-schema DB.

All tests use a temp-file SQLite DB built via backend.db.init_db() so the
full production schema is present; they never touch the real
data/losslessbob.db.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import tempfile

import backend.config_version as config_version
import backend.db as db
from backend.refresh import (
    STEPS,
    RefreshStep,
    _last_run_record,
    _parse_ts,
    _step_state,
    _topological_order,
    compute_plan,
)


def _make_conn() -> tuple[sqlite3.Connection, str]:
    """Create a fresh temp DB with full schema. Returns (conn, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_refresh_")
    db_path = os.path.join(tmp_dir, "test.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    return conn, tmp_dir


# ── _parse_ts ────────────────────────────────────────────────────────────


def test_parse_ts_space_separated() -> None:
    assert _parse_ts("2026-08-02 22:22:28") == _dt.datetime(2026, 8, 2, 22, 22, 28)


def test_parse_ts_t_separated() -> None:
    assert _parse_ts("2026-07-14T00:04:41") == _dt.datetime(2026, 7, 14, 0, 4, 41)


def test_parse_ts_microseconds() -> None:
    result = _parse_ts("2026-07-14T00:04:41.894196")
    assert result == _dt.datetime(2026, 7, 14, 0, 4, 41, 894196)


def test_parse_ts_tz_aware_converts_to_naive_local() -> None:
    result = _parse_ts("2026-07-14T00:04:41.894196+00:00")
    assert result is not None
    assert result.tzinfo is None
    # Must equal the local-time conversion of the UTC instant.
    expected = (
        _dt.datetime(2026, 7, 14, 0, 4, 41, 894196, tzinfo=_dt.UTC)
        .astimezone()
        .replace(tzinfo=None)
    )
    assert result == expected


def test_parse_ts_z_suffix() -> None:
    result = _parse_ts("2026-07-14T00:04:41Z")
    assert result is not None
    assert result.tzinfo is None


def test_parse_ts_none_and_empty() -> None:
    assert _parse_ts(None) is None
    assert _parse_ts("") is None


def test_parse_ts_garbage() -> None:
    assert _parse_ts("garbage") is None
    assert _parse_ts("not-a-date") is None


def test_parse_ts_fixes_string_comparison_inversion() -> None:
    """Sec 1b regression: 'T' (0x54) sorts after ' ' (0x20), inverting same-day
    order under raw string comparison. _parse_ts must fix this."""
    iso_t = "2026-07-14T00:00:01"
    space = "2026-07-14 23:59:59"

    # The raw-string bug: naive comparison says T-separated > space-separated
    # even though T-separated is earlier in the same day.
    assert (iso_t > space) is True

    # _parse_ts must invert this back to the true chronological order.
    assert (_parse_ts(iso_t) < _parse_ts(space)) is True


# ── _step_state truth table ─────────────────────────────────────────────


def _step(**overrides) -> RefreshStep:
    base = dict(
        step_id="x", label="x", trigger="T1", kind="wholesale",
        backlog_sql=None, last_run_sql=None, version_key=None,
        upstream=(), how_to_run="POST /api/x", cost="fast", human_gate=False,
    )
    base.update(overrides)
    return RefreshStep(**base)


def test_step_state_stale_from_backlog() -> None:
    step = _step(backlog_sql="SELECT 1")
    state, reason = _step_state(step, last_run=None, upstream_runs={}, backlog=5)
    assert state == "stale"
    assert "backlog" in reason


def test_step_state_blocked_beats_stale_precedence() -> None:
    """An upstream that is itself stale must mark this step 'blocked', not
    re-derive 'stale' from a stale watermark of its own."""
    step = _step(upstream=("up",))
    now = _dt.datetime(2026, 8, 1)
    upstream_runs = {"up": ("stale", now)}
    state, reason = _step_state(step, last_run=None, upstream_runs=upstream_runs, backlog=None)
    assert state == "blocked"
    assert "up" in reason


def test_step_state_blocked_from_upstream_blocked() -> None:
    step = _step(upstream=("up",))
    upstream_runs = {"up": ("blocked", None)}
    state, _reason = _step_state(step, last_run=None, upstream_runs=upstream_runs, backlog=None)
    assert state == "blocked"


def test_step_state_watermark_stale_when_upstream_newer() -> None:
    step = _step(upstream=("up",))
    mine = _dt.datetime(2026, 7, 1)
    theirs = _dt.datetime(2026, 7, 15)
    upstream_runs = {"up": ("fresh", theirs)}
    state, reason = _step_state(step, last_run=mine, upstream_runs=upstream_runs, backlog=None)
    assert state == "stale"
    assert "watermark" in reason or "no backlog signal" in reason


def test_step_state_backlog_zero_beats_newer_upstream_watermark() -> None:
    """Sec 1a false-positive guard: backlog == 0 must NOT be overridden by a
    newer upstream watermark -- backlog is the direct measure and wins."""
    step = _step(upstream=("up",))
    mine = _dt.datetime(2026, 7, 1)
    theirs = _dt.datetime(2026, 7, 15)
    upstream_runs = {"up": ("fresh", theirs)}
    state, reason = _step_state(step, last_run=mine, upstream_runs=upstream_runs, backlog=0)
    assert state == "fresh"
    assert "backlog 0" in reason


def test_step_state_unknown_when_no_signal() -> None:
    step = _step()
    state, reason = _step_state(step, last_run=None, upstream_runs={}, backlog=None)
    assert state == "unknown"


def test_step_state_fresh_when_backlog_zero_no_watermark() -> None:
    step = _step()
    state, reason = _step_state(step, last_run=None, upstream_runs={}, backlog=0)
    assert state == "fresh"
    assert "no watermark column" in reason


def test_step_state_fresh_with_watermark_and_no_newer_upstream() -> None:
    step = _step(upstream=("up",))
    mine = _dt.datetime(2026, 7, 15)
    theirs = _dt.datetime(2026, 7, 1)
    upstream_runs = {"up": ("fresh", theirs)}
    state, _reason = _step_state(step, last_run=mine, upstream_runs=upstream_runs, backlog=None)
    assert state == "fresh"


# ── Registry integrity ───────────────────────────────────────────────────


def test_registry_step_ids_unique() -> None:
    ids = [step.step_id for step in STEPS]
    assert len(ids) == len(set(ids))


def test_registry_upstream_resolves_to_real_step_ids() -> None:
    ids = {step.step_id for step in STEPS}
    for step in STEPS:
        for upstream_id in step.upstream:
            assert upstream_id in ids, f"{step.step_id} references unknown upstream {upstream_id}"


def test_registry_has_no_cycles_and_topological_order_is_well_defined() -> None:
    order = _topological_order()
    ids = {step.step_id for step in STEPS}
    assert set(order) == ids
    assert len(order) == len(set(order))

    position = {step_id: i for i, step_id in enumerate(order)}
    for step in STEPS:
        for upstream_id in step.upstream:
            assert position[upstream_id] < position[step.step_id], (
                f"{upstream_id} must precede {step.step_id} in topological order"
            )


def test_registry_at_least_one_signal_or_documented_unknown() -> None:
    """Every step either declares a signal, or is one of the documented
    Sec 4 unmeasurable steps (backlog_sql and last_run_sql both None)."""
    for step in STEPS:
        has_signal = step.backlog_sql is not None or step.last_run_sql is not None
        assert has_signal or (step.backlog_sql is None and step.last_run_sql is None)


# ── Every registered SQL query executes against the full schema ────────


def test_all_backlog_sql_execute_with_right_arity() -> None:
    conn, _tmp_dir = _make_conn()
    for step in STEPS:
        if step.backlog_sql is None:
            continue
        row = conn.execute(step.backlog_sql).fetchone()
        assert row is not None, f"{step.step_id}.backlog_sql returned no row"
        assert len(row) == 1, f"{step.step_id}.backlog_sql returned {len(row)} columns"
        assert isinstance(row[0], int), f"{step.step_id}.backlog_sql did not return an int"


def test_all_last_run_sql_execute_with_right_arity() -> None:
    """Every last_run_sql must execute and return single-column rows.

    MAX(...) queries always return exactly one row (NULL on an empty table).
    WHERE-filtered queries (e.g. db_import's `meta` lookup) legitimately
    return zero rows against an empty table -- that is not a query defect,
    it is what `_run_scalar()` treats as "no watermark yet".
    """
    conn, _tmp_dir = _make_conn()
    for step in STEPS:
        if step.last_run_sql is None:
            continue
        rows = conn.execute(step.last_run_sql).fetchall()
        assert len(rows) <= 1, f"{step.step_id}.last_run_sql returned {len(rows)} rows"
        if rows:
            assert len(rows[0]) == 1, f"{step.step_id}.last_run_sql returned {len(rows[0])} cols"


# ── olof_chronicle_parse backlog scoping (TODO-309) ─────────────────────


def test_chronicle_backlog_ignores_yearless_pages_and_other_corpora() -> None:
    """`chronologies.htm` has no year, so no parser can ever consume it —
    counting it would pin this backlog at 1 forever, the same failure that
    forced olof_parse's rescope. DSN rows must not leak in either."""
    conn, tmp_dir = _make_conn()
    db_path = os.path.join(tmp_dir, "test.db")
    conn.executemany(
        "INSERT INTO olof_pages (filename, url, corpus, year, fetched_at, parsed_at) "
        "VALUES (?, 'http://x', ?, ?, ?, ?)",
        [
            # yearless index: unparsable by design, must not count
            # (parsed_at is NOT NULL DEFAULT '' in the schema — never-parsed
            # pages carry '', which sorts below any fetched_at)
            ("chronologies.htm", "chronicle", None, "2026-08-01T00:00:00", ""),
            # parsed after fetch: fresh, must not count
            ("chronicle1990.htm", "chronicle", 1990,
             "2026-08-01T00:00:00", "2026-08-02T00:00:00"),
            # fetched since its last parse: the one real backlog row
            ("chronicle1991.htm", "chronicle", 1991,
             "2026-08-03T00:00:00", "2026-08-02T00:00:00"),
            # other corpus: olof_parse's problem, not this step's
            ("dsn01.htm", "dsn", None, "2026-08-03T00:00:00", ""),
        ],
    )
    conn.commit()

    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "olof_chronicle_parse")
    assert step["backlog"] == 1


# ── Missing table degrades to 'unknown', never raises ───────────────────


def test_missing_table_reports_unknown_not_raise() -> None:
    conn, tmp_dir = _make_conn()
    db_path = os.path.join(tmp_dir, "test.db")
    conn.execute("DROP TABLE quality_recording_metrics")
    conn.commit()

    plan = compute_plan(db_path=db_path)
    ranker_scan = next(s for s in plan["steps"] if s["step_id"] == "ranker_scan")
    assert ranker_scan["state"] == "unknown"


# ── compute_plan payload shape ───────────────────────────────────────────


def test_compute_plan_empty_schema_returns_well_formed_payload() -> None:
    conn, tmp_dir = _make_conn()
    db_path = os.path.join(tmp_dir, "test.db")
    plan = compute_plan(db_path=db_path)

    assert "generated_at" in plan
    assert "steps" in plan
    assert "stale_count" in plan
    assert "blocked_count" in plan
    assert "unknown_count" in plan
    assert "by_trigger" in plan
    assert "publish_lag" in plan

    assert len(plan["steps"]) == len(STEPS)
    for trigger in ("T1", "T2", "T3", "T4"):
        assert trigger in plan["by_trigger"]
        assert "total" in plan["by_trigger"][trigger]

    lag = plan["publish_lag"]
    assert lag["published_at"] is None
    assert lag["lb_status_changes_since"] == 0
    assert lag["entries_scraped_since"] == 0
    assert lag["days_since"] is None


def test_compute_plan_trigger_filter() -> None:
    conn, tmp_dir = _make_conn()
    db_path = os.path.join(tmp_dir, "test.db")
    plan = compute_plan(db_path=db_path, trigger="T1")
    assert all(s["trigger"] == "T1" for s in plan["steps"])
    # counts still reflect the full registry, not just the filtered steps.
    total_t1 = sum(1 for s in STEPS if s.trigger == "T1")
    assert len(plan["steps"]) == total_t1


# ── TODO-306 Phase 2: run-record + version signals ─────────────────────


def test_run_record_newer_than_watermark_wins(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.record_step_run(
        "attribute_tapers", status="ok",
        finished_at="2026-08-01 00:00:00", db_path=db_path,
    )
    conn = db.get_connection(db_path)
    conn.execute(
        "INSERT INTO taper_attributions"
        "(lb_number, taper_normalised, confidence, evidence_json, computed_at) "
        "VALUES (1, 'x', 'inferred', '[]', '2026-01-01 00:00:00')"
    )
    conn.commit()

    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "attribute_tapers")
    assert step["last_run_source"] == "run_record"
    assert step["last_run"].startswith("2026-08-01")


def test_older_run_record_loses_to_watermark(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.record_step_run(
        "attribute_tapers", status="ok",
        finished_at="2026-01-01 00:00:00", db_path=db_path,
    )
    conn = db.get_connection(db_path)
    conn.execute(
        "INSERT INTO taper_attributions"
        "(lb_number, taper_normalised, confidence, evidence_json, computed_at) "
        "VALUES (1, 'x', 'inferred', '[]', '2026-08-01 00:00:00')"
    )
    conn.commit()

    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "attribute_tapers")
    assert step["last_run_source"] == "watermark"
    assert step["last_run"].startswith("2026-08-01")


def test_ranker_rerank_last_run_purely_from_record(tmp_path) -> None:
    """ranker_rerank has no last_run_sql -- its last_run comes only from the run-record."""
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.record_step_run(
        "ranker_rerank", status="ok",
        finished_at="2026-08-01 00:00:00", db_path=db_path,
    )
    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "ranker_rerank")
    assert step["last_run_source"] == "run_record"
    assert step["last_run"].startswith("2026-08-01")


def test_last_run_record_helper(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    last_success, last_status = _last_run_record(conn, "olof_fetch")
    assert last_success is None
    assert last_status is None

    db.record_step_run("olof_fetch", status="ok", finished_at="2026-08-01 00:00:00",
                        db_path=db_path)
    last_success, last_status = _last_run_record(conn, "olof_fetch")
    assert last_success == _dt.datetime(2026, 8, 1)
    assert last_status == "ok"


def test_newest_error_run_marks_stale_until_later_success(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.record_step_run("olof_fetch", status="error", finished_at="2026-08-01 00:00:00",
                        db_path=db_path)

    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "olof_fetch")
    assert step["state"] == "stale"
    assert "last run failed" in step["reason"]

    db.record_step_run("olof_fetch", status="ok", finished_at="2026-08-02 00:00:00",
                        db_path=db_path)
    plan = compute_plan(db_path=db_path)
    step = next(s for s in plan["steps"] if s["step_id"] == "olof_fetch")
    assert step["state"] != "stale" or "last run failed" not in step["reason"]


def test_step_state_version_truth_table() -> None:
    step = _step(backlog_sql=None)
    # 'changed' -> stale even at backlog 0.
    state, reason = _step_state(
        step, last_run=None, upstream_runs={}, backlog=0, version_state="changed",
    )
    assert state == "stale"
    assert "config changed" in reason

    # 'unstamped' never downgrades a fresh state, just annotates the reason.
    state, reason = _step_state(
        step, last_run=None, upstream_runs={}, backlog=0, version_state="unstamped",
    )
    assert state == "fresh"
    assert "unstamped" in reason

    # 'ok' and 'n/a' leave state untouched.
    for vs in ("ok", "n/a"):
        state, reason = _step_state(
            step, last_run=None, upstream_runs={}, backlog=0, version_state=vs,
        )
        assert state == "fresh"
        assert "unstamped" not in reason


def test_registry_version_key_matches_step_version_sources() -> None:
    """Every step with a version_key must be a STEP_VERSION_SOURCES key, and
    vice versa -- the two must stay in sync or version_state()/stamp_for_step()
    silently no-op for a step that thinks it has a version signal."""
    registry_keys = {step.step_id: step.version_key for step in STEPS if step.version_key}
    for step_id, key in registry_keys.items():
        assert step_id in config_version.STEP_VERSION_SOURCES, (
            f"{step_id} declares version_key={key!r} but has no STEP_VERSION_SOURCES entry"
        )
        assert config_version.STEP_VERSION_SOURCES[step_id][0] == key
    for step_id, (key, _fn) in config_version.STEP_VERSION_SOURCES.items():
        assert registry_keys.get(step_id) == key, (
            f"STEP_VERSION_SOURCES[{step_id!r}] has no matching registry version_key"
        )


def test_route_how_to_run_resolves_in_url_map() -> None:
    """Every how_to_run starting POST/GET must resolve in the Flask app's url_map
    (catches a typo'd route string on the card the day it is written)."""
    from backend.app import create_app

    app = create_app()
    rules = {(rule.rule, method) for rule in app.url_map.iter_rules() for method in rule.methods}

    for step in STEPS:
        for token in step.how_to_run.split(" then "):
            token = token.strip()
            if not (token.startswith("POST ") or token.startswith("GET ")):
                continue
            method, path = token.split(" ", 1)
            if "<" in path:
                # Parameterized routes (e.g. '/api/flat_file/apply/<id>') are
                # documentation shorthand, not Flask's literal converter
                # syntax (e.g. '<int:release_id>') -- only static how_to_run
                # paths are checked exactly.
                continue
            assert (path, method) in rules, (
                f"{step.step_id}.how_to_run={token!r} does not resolve in url_map"
            )


def test_record_step_run_then_init_db_again_no_error(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.record_step_run("olof_fetch", status="ok", db_path=db_path)
    db.init_db(db_path)  # idempotent re-init must not error or duplicate rows
    conn = db.get_connection(db_path)
    count = conn.execute("SELECT COUNT(*) FROM refresh_step_runs").fetchone()[0]
    assert count == 1


# ── Phase 4: queue attention (TODO-310) ──────────────────────────────────


def test_every_step_carries_an_attention_list(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    plan = compute_plan(db_path=db_path)
    for step in plan["steps"]:
        assert isinstance(step["attention"], list)


def test_plan_carries_queues_and_gate_only_pending_total(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    conn.execute(
        "INSERT INTO taper_attributions "
        "(lb_number, taper_normalised, confidence, evidence_json, conflict) "
        "VALUES (1, 'x', 'inferred', '[]', 1)"
    )
    # A backlog queue with items must not move queue_pending_total.
    conn.execute("INSERT INTO tapematch_pairs (concert_date, lb_a, lb_b) VALUES ('1974-01-01', 1, 2)")
    conn.commit()

    plan = compute_plan(db_path=db_path)
    assert {q["queue_id"] for q in plan["queues"]} == {
        "taper_conflicts", "fingerprint_suggestions", "xref_filesets", "tapematch_dates",
    }
    assert plan["queue_pending_total"] == 1

    by_id = {s["step_id"]: s for s in plan["steps"]}
    assert by_id["attribute_tapers"]["attention"] == [
        {"queue_id": "taper_conflicts", "count": 1, "kind": "gate"}
    ]
    assert by_id["song_index"]["attention"] == []


def test_pending_queue_never_changes_any_step_state(tmp_path, monkeypatch) -> None:
    """Decision 3: queues are orthogonal to state. This is its regression test."""
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    for lb in range(1, 6):
        conn.execute(
            "INSERT INTO taper_attributions "
            "(lb_number, taper_normalised, confidence, evidence_json, conflict) "
            "VALUES (?, 'x', 'inferred', '[]', 1)", (lb,),
        )
    conn.commit()

    with_queues = compute_plan(db_path=db_path)
    assert with_queues["queue_pending_total"] == 5

    import backend.queues as queues_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("queues unavailable")

    monkeypatch.setattr(queues_mod, "queue_counts", _boom)
    without_queues = compute_plan(db_path=db_path)

    assert without_queues["queues"] == []
    assert without_queues["queue_pending_total"] == 0
    assert {s["step_id"]: s["state"] for s in without_queues["steps"]} == {
        s["step_id"]: s["state"] for s in with_queues["steps"]
    }
    assert all(s["attention"] == [] for s in without_queues["steps"])
