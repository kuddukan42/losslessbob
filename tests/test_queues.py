"""Tests for backend/queues.py -- human review queues (TODO-310 Phase 4).

Covers spec §5 (PIPELINE_REFRESH_PHASE4.md): registry integrity, each
`count_sql` against a fixture with known rows, the missing-table degradation,
`attention_by_step` inversion, and the `backlog`-kind rules that keep the
TapeMatch curation count out of every badge.

Synthetic DB only, no network.
"""

from __future__ import annotations

import sqlite3

import backend.db as db
from backend.queues import (
    QUEUES,
    RefreshQueue,
    attention_by_step,
    pending_total,
    queue_counts,
    snapshot,
)
from backend.refresh import STEPS


def _make_db(tmp_path) -> str:
    """Create a fresh temp DB with the full schema and return its path."""
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    return db_path


def _by_id(queues: list[dict]) -> dict[str, dict]:
    return {q["queue_id"]: q for q in queues}


# ── registry integrity ───────────────────────────────────────────────────


def test_queue_ids_are_unique() -> None:
    ids = [q.queue_id for q in QUEUES]
    assert len(ids) == len(set(ids))


def test_every_blocks_entry_is_a_real_step_id() -> None:
    step_ids = {s.step_id for s in STEPS}
    for queue in QUEUES:
        assert queue.blocks, f"{queue.queue_id} blocks nothing"
        for step_id in queue.blocks:
            assert step_id in step_ids, f"{queue.queue_id} blocks unknown step {step_id!r}"


def test_kind_is_gate_or_backlog() -> None:
    for queue in QUEUES:
        assert queue.kind in ("gate", "backlog")


def test_backlog_has_total_sql_and_gate_does_not() -> None:
    for queue in QUEUES:
        if queue.kind == "backlog":
            assert queue.total_sql, f"{queue.queue_id} is backlog with no total_sql"
        else:
            assert queue.total_sql is None, f"{queue.queue_id} is a gate with a total_sql"


def test_every_queue_has_an_action_line() -> None:
    for queue in QUEUES:
        assert queue.action.strip()


def test_queue_is_not_a_step_id() -> None:
    """A queue must never collide with a step -- it is a separate registry."""
    step_ids = {s.step_id for s in STEPS}
    for queue in QUEUES:
        assert queue.queue_id not in step_ids


# ── counts ───────────────────────────────────────────────────────────────


def test_empty_db_reports_every_queue_clear(tmp_path) -> None:
    queues = queue_counts(_make_db(tmp_path))
    assert len(queues) == len(QUEUES)
    for queue in queues:
        assert queue["count"] == 0
        assert queue["state"] == "clear"
    assert pending_total(queues) == 0


def test_taper_conflicts_counts_undecided_only(tmp_path) -> None:
    db_path = _make_db(tmp_path)
    conn = db.get_connection(db_path)
    for lb in (1, 2, 3):
        conn.execute(
            "INSERT INTO taper_attributions "
            "(lb_number, taper_normalised, confidence, evidence_json, conflict) "
            "VALUES (?, 'x', 'inferred', '[]', 1)", (lb,),
        )
    # A non-conflicting row never enters the queue.
    conn.execute(
        "INSERT INTO taper_attributions "
        "(lb_number, taper_normalised, confidence, evidence_json, conflict) "
        "VALUES (4, 'x', 'confirmed', '[]', 0)"
    )
    # A decided conflict drops out.
    conn.execute(
        "INSERT INTO taper_confirmations (lb_number, taper_normalised, action) "
        "VALUES (2, 'x', 'confirm')"
    )
    conn.commit()

    queue = _by_id(queue_counts(db_path))["taper_conflicts"]
    assert queue["count"] == 2
    assert queue["state"] == "pending"
    assert queue["kind"] == "gate"


def test_fingerprint_suggestions_counted_per_lb_not_per_row(tmp_path) -> None:
    db_path = _make_db(tmp_path)
    conn = db.get_connection(db_path)
    rows = [
        (100, 1, "pending"), (100, 2, "pending"),   # two rows, one decision
        (200, 1, "pending"),
        (300, 1, "dismissed"),                      # decided -> out
    ]
    for lb, rank, status in rows:
        conn.execute(
            "INSERT INTO setlist_fingerprint_suggestions "
            "(lb_number, rank, event_id, score, matched_count, entry_song_count, "
            " olof_song_count, matches_json, missing_json, status) "
            "VALUES (?, ?, 1, 0.9, 5, 6, 7, '[]', '[]', ?)", (lb, rank, status),
        )
    conn.commit()

    queue = _by_id(queue_counts(db_path))["fingerprint_suggestions"]
    assert queue["count"] == 2
    assert queue["state"] == "pending"


def test_xref_filesets_counts_staged_only(tmp_path) -> None:
    db_path = _make_db(tmp_path)
    conn = db.get_connection(db_path)
    for lb, xref, status in ((1, 10, "staged"), (2, 20, "staged"), (3, 30, "approved")):
        conn.execute(
            "INSERT INTO xref_ingest_filesets "
            "(lb_number, xref, source_file, row_count, new_count, status) "
            "VALUES (?, ?, 'f.md5', 3, 3, ?)", (lb, xref, status),
        )
    conn.commit()

    queue = _by_id(queue_counts(db_path))["xref_filesets"]
    assert queue["count"] == 2
    assert queue["screen"] is None, "xref ingest is display-only (decision 7)"


def test_tapematch_dates_is_a_backlog_ratio(tmp_path) -> None:
    db_path = _make_db(tmp_path)
    conn = db.get_connection(db_path)
    for date in ("1974-01-01", "1975-02-02", "1976-03-03"):
        conn.execute(
            "INSERT INTO tapematch_pairs (concert_date, lb_a, lb_b) VALUES (?, 1, 2)", (date,)
        )
    conn.execute(
        "INSERT INTO tapematch_date_curation (concert_date, accepted_at) "
        "VALUES ('1974-01-01', '2026-08-16T00:00:00Z')"
    )
    conn.commit()

    queue = _by_id(queue_counts(db_path))["tapematch_dates"]
    assert queue["count"] == 2
    assert queue["total"] == 3
    assert queue["kind"] == "backlog"
    assert queue["state"] == "open", "a backlog is never 'pending' (decision 2)"


def test_backlog_never_contributes_to_pending_total(tmp_path) -> None:
    db_path = _make_db(tmp_path)
    conn = db.get_connection(db_path)
    for date in ("1974-01-01", "1975-02-02"):
        conn.execute(
            "INSERT INTO tapematch_pairs (concert_date, lb_a, lb_b) VALUES (?, 1, 2)", (date,)
        )
    conn.execute(
        "INSERT INTO taper_attributions "
        "(lb_number, taper_normalised, confidence, evidence_json, conflict) "
        "VALUES (1, 'x', 'inferred', '[]', 1)"
    )
    conn.commit()

    queues = queue_counts(db_path)
    assert _by_id(queues)["tapematch_dates"]["count"] == 2
    assert pending_total(queues) == 1


# ── missing table ────────────────────────────────────────────────────────


def test_missing_table_yields_unknown_without_raising(tmp_path) -> None:
    db_path = str(tmp_path / "bare.db")
    sqlite3.connect(db_path).close()  # no schema at all

    queues = queue_counts(db_path)
    assert len(queues) == len(QUEUES)
    for queue in queues:
        assert queue["count"] is None
        assert queue["state"] == "unknown"
    assert pending_total(queues) == 0


# ── attention_by_step ────────────────────────────────────────────────────


def test_attention_by_step_maps_onto_every_blocked_step() -> None:
    queues = [{
        "queue_id": "taper_conflicts", "kind": "gate", "count": 129,
        "blocks": ["attribute_tapers", "compute_show_picks", "master_publish"],
    }]
    attention = attention_by_step(queues)
    assert set(attention) == {"attribute_tapers", "compute_show_picks", "master_publish"}
    assert attention["attribute_tapers"] == [
        {"queue_id": "taper_conflicts", "count": 129, "kind": "gate"}
    ]


def test_attention_by_step_omits_unnamed_and_empty_queues() -> None:
    queues = [
        {"queue_id": "a", "kind": "gate", "count": 0, "blocks": ["song_index"]},
        {"queue_id": "b", "kind": "gate", "count": None, "blocks": ["geocode"]},
    ]
    assert attention_by_step(queues) == {}


def test_attention_by_step_merges_multiple_queues_on_one_step() -> None:
    queues = [
        {"queue_id": "a", "kind": "gate", "count": 1, "blocks": ["master_publish"]},
        {"queue_id": "b", "kind": "backlog", "count": 2, "blocks": ["master_publish"]},
    ]
    attention = attention_by_step(queues)
    assert [entry["queue_id"] for entry in attention["master_publish"]] == ["a", "b"]


# ── snapshot ─────────────────────────────────────────────────────────────


def test_snapshot_shape(tmp_path) -> None:
    snap = snapshot(_make_db(tmp_path))
    assert set(snap) == {"queues", "pending_total", "computed_at"}
    assert len(snap["queues"]) == len(QUEUES)
    assert snap["pending_total"] == 0


def test_refresh_queue_is_a_namedtuple() -> None:
    assert issubclass(RefreshQueue, tuple)
