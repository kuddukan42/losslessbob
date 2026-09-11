"""JobState-backed QC rules run (TODO-342 Phase 2b C12).

Wraps :func:`backend.qc.store.run_all` behind the same ``JobState`` pattern
``backend/ranker_jobs.py`` uses for the ranker scan, so ``POST /api/qc/run``
can start a background thread and ``GET /api/qc/run`` can poll it. Unlike the
ranker, a rules run is comparatively fast (pure SQL over rows already in the
DB, no audio decode), but is still run off the request thread so a large
rule set can't tie up a Flask worker on a slow request.
"""
from __future__ import annotations

import logging
import threading

from backend.db import close_connection, get_connection
from backend.job_progress import JobState
from backend.qc import store
from backend.qc.rules import RULES
from backend.qc.store import RunStats

logger = logging.getLogger(__name__)

_JOB = JobState("qc-run")


def get_status() -> dict:
    """Return the active/last run's progress snapshot."""
    return _JOB.snapshot()


def _run_thread(rule_id: str | None, db_path: str | None) -> None:
    """Thread target: run one rule or all rules, recording progress per rule."""
    conn = get_connection(db_path)
    rule_ids = [rule_id] if rule_id else sorted(RULES)
    _JOB.update(stage="running", total=len(rule_ids), done=0, current="")
    results: list[RunStats] = []
    try:
        for rid in rule_ids:
            _JOB.update(current=rid)
            stats = store.run_rule(conn, RULES[rid])
            results.append(stats)
            _JOB.update(done=len(results))
        _JOB.finish(
            stage="done", current="",
            result=[
                {
                    "rule_id": s.rule_id, "n_open": s.n_open, "n_new": s.n_new,
                    "n_fixed": s.n_fixed, "n_reopened": s.n_reopened,
                }
                for s in results
            ],
        )
    except Exception as exc:
        logger.exception("qc run failed")
        _JOB.finish(stage="error", error=str(exc))
    finally:
        close_connection(db_path)


def start(rule_id: str | None = None, db_path: str | None = None) -> bool:
    """Atomically claim and start a rules run in a background thread.

    Args:
        rule_id: Restrict the run to one rule, or None to run every
            registered rule (:data:`backend.qc.rules.RULES`, in id order).
        db_path: Optional database path override.

    Returns:
        True if the run was started, False if one was already active.

    Raises:
        KeyError: *rule_id* is not a registered rule.
    """
    if rule_id is not None and rule_id not in RULES:
        raise KeyError(rule_id)
    if not _JOB.try_begin(stage="queued", rule_id=rule_id):
        return False
    thread = threading.Thread(
        target=_run_thread, args=(rule_id, db_path), daemon=True,
    )
    thread.start()
    return True
