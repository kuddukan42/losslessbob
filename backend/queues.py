"""Human review queues as first-class, countable blockers.

Phase 4 of the pipeline-refresh spec (`instructions/PIPELINE_REFRESH_PHASE4.md`).
Phases 1-3 made *machine* work visible and runnable. This module makes *human*
work visible: four review queues sit mid-graph, each degrading downstream output
silently because its "N items waiting" count exists nowhere outside its own
screen.

Design rules this module encodes (spec Sec 2, tj's binding decisions):

  - **Separate registry.** A queue is not a `refresh.STEPS` entry: it is not
    runnable, has no upstream, and must never enter a Phase 3 chain plan.
    `refresh.py` does not import this module at import time -- the dependency
    runs one way, exactly as it does for `refresh_exec`.
  - **Two kinds.** `gate` queues are expected to drain to zero and get a count,
    a badge and step attention. `backlog` queues are open-ended by nature and
    get a *ratio* ("3 of 3,060 curated"), never a badge. TapeMatch date curation
    is the only `backlog` today: rendering 3,057 as "items waiting" would train
    the user to ignore every badge the card shows.
  - **A pending queue never changes a step's `state`.** `stale`/`blocked`/
    `fresh`/`unknown` keep their Phase 1 meanings exactly; queues ride on an
    orthogonal `attention` field. A red card and a refusal to run are the wrong
    response to "a human hasn't reviewed 129 rows".
  - **App DB only.** TapeMatch judgments live in
    `tools/tapematch/observations.db`, which the nightly analysis runs hold
    locked for hours; the freshness path must never open it. The app-DB mirror
    (`tapematch_pairs` vs `tapematch_date_curation`) is the sanctioned proxy.
  - **No new tables.** Counts are derived on read -- no snapshot history, no
    snooze, no dismiss-until.

Counting *decision units* rather than rows is deliberate: 691 fingerprint
suggestion rows are 242 decisions (one per LB), and a user shown 691 will read
the queue as three times more work than it is.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import NamedTuple

from backend.db import get_connection
from backend.refresh import _run_scalar

logger = logging.getLogger(__name__)


class RefreshQueue(NamedTuple):
    """One human review queue that gates or informs pipeline output.

    Attributes:
        queue_id: Stable identifier, e.g. ``'taper_conflicts'``.
        label: i18n key suffix (Phase 1 style -- ``queue_id`` verbatim).
        kind: ``'gate'`` (expected to drain to zero) or ``'backlog'``
            (open-ended; reported as a ratio, never as a badge).
        count_sql: SQL returning one row, one int -- items still awaiting a
            human decision.
        total_sql: ``'backlog'`` only -- the denominator for the ratio.
            ``None`` for every ``'gate'`` queue.
        blocks: ``refresh.STEPS`` step_ids whose output this queue degrades.
        screen: GUI route to send the user to, or ``None`` when no screen owns
            this queue.
        action: One line describing what the human actually does there.
    """

    queue_id: str
    label: str
    kind: str
    count_sql: str
    total_sql: str | None
    blocks: tuple[str, ...]
    screen: str | None
    action: str


QUEUES: tuple[RefreshQueue, ...] = (
    RefreshQueue(
        queue_id="taper_conflicts",
        label="taper_conflicts",
        kind="gate",
        # A conflict is "decided" once any confirmation row exists for the LB --
        # confirm, reject and mark-unresolved all write one, so all three
        # verdicts drop the row out of the queue.
        count_sql=(
            "SELECT COUNT(*) FROM taper_attributions ta WHERE ta.conflict=1 "
            "AND NOT EXISTS (SELECT 1 FROM taper_confirmations tc "
            "WHERE tc.lb_number=ta.lb_number)"
        ),
        total_sql=None,
        blocks=("attribute_tapers", "compute_show_picks", "master_publish"),
        screen="/library?view=taperReview",
        action="confirm, reject or mark unresolved",
    ),
    RefreshQueue(
        queue_id="fingerprint_suggestions",
        label="fingerprint_suggestions",
        kind="gate",
        # DISTINCT lb_number, not COUNT(*): 691 pending rows are 242 decisions.
        count_sql=(
            "SELECT COUNT(DISTINCT lb_number) FROM setlist_fingerprint_suggestions "
            "WHERE status='pending'"
        ),
        total_sql=None,
        blocks=("setlist_fingerprint",),
        screen="/fingerprint",
        action="accept or dismiss each suggested setlist match",
    ),
    RefreshQueue(
        queue_id="xref_filesets",
        label="xref_filesets",
        kind="gate",
        # Display-only (decision 7): `checksums` is Jeff's table and this
        # install does not author rows in it. A staged fileset is resolved by a
        # later flat-file drop or a word to Jeff, not by a local Approve button.
        count_sql="SELECT COUNT(*) FROM xref_ingest_filesets WHERE status='staged'",
        total_sql=None,
        blocks=("xref_ingest", "lb_master_reconcile"),
        screen=None,
        action="site-mirror checksum files Jeff's DB drop didn't include — resolved by a later drop",
    ),
    RefreshQueue(
        queue_id="tapematch_dates",
        label="tapematch_dates",
        kind="backlog",
        # App-DB mirror only -- never tools/tapematch/observations.db, which the
        # nightly analysis runs hold locked for hours (decision 5).
        count_sql=(
            "SELECT COUNT(*) FROM (SELECT DISTINCT concert_date AS d FROM tapematch_pairs) x "
            "WHERE NOT EXISTS (SELECT 1 FROM tapematch_date_curation c "
            "WHERE c.concert_date=x.d)"
        ),
        total_sql="SELECT COUNT(DISTINCT concert_date) FROM tapematch_pairs",
        blocks=("tapematch_sync",),
        screen="/tapematch",
        action="accept or reject the candidate pairs for a date",
    ),
)

_QUEUES_BY_ID: dict[str, RefreshQueue] = {q.queue_id: q for q in QUEUES}


def _as_int(value) -> int | None:
    """Coerce a scalar to int, or None if it is absent/uncoercible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def queue_counts(db_path: str | None = None) -> list[dict]:
    """Count every registered queue against the app DB.

    Opens one connection and runs each ``count_sql`` (and ``total_sql``, for
    ``backlog`` queues) through :func:`backend.refresh._run_scalar`, which
    already degrades a missing table to ``None`` -- exactly the "install
    without that feature" case. Never raises.

    Args:
        db_path: Optional DB path override; defaults to the app's normal DB.

    Returns:
        One dict per queue, in registry order, with ``queue_id``, ``kind``,
        ``count``, ``total``, ``blocks``, ``screen``, ``action`` and ``state``.
        ``state`` is:

          - ``'unknown'`` -- the count SQL returned None (table absent). Same
            honesty rule Phase 1 applies to steps with no signal.
          - ``'pending'`` -- a ``gate`` queue with items waiting.
          - ``'open'`` -- a ``backlog`` queue with items left. Never
            ``'pending'``: a backlog is information, not debt (decision 2).
          - ``'clear'`` -- count is zero.
    """
    conn = get_connection(db_path)
    out: list[dict] = []
    for queue in QUEUES:
        count = _as_int(_run_scalar(conn, queue.count_sql))
        total = _as_int(_run_scalar(conn, queue.total_sql)) if queue.total_sql else None

        if count is None:
            state = "unknown"
        elif count == 0:
            state = "clear"
        else:
            state = "pending" if queue.kind == "gate" else "open"

        out.append({
            "queue_id": queue.queue_id,
            "label": queue.label,
            "kind": queue.kind,
            "count": count,
            "total": total,
            "blocks": list(queue.blocks),
            "screen": queue.screen,
            "action": queue.action,
            "state": state,
        })
    return out


def attention_by_step(queues: list[dict]) -> dict[str, list[dict]]:
    """Invert `queue_counts()` output into a step_id -> attention-entries map.

    Only queues with a positive count contribute; steps no queue names are
    absent from the dict entirely (rather than mapping to an empty list), so a
    caller can use a plain ``.get(step_id, [])``.

    Args:
        queues: The list returned by :func:`queue_counts`.

    Returns:
        ``{step_id: [{"queue_id", "count", "kind"}, ...]}``.
    """
    mapping: dict[str, list[dict]] = {}
    for queue in queues:
        if not queue.get("count"):
            continue
        entry = {
            "queue_id": queue["queue_id"],
            "count": queue["count"],
            "kind": queue["kind"],
        }
        for step_id in queue.get("blocks", ()):
            mapping.setdefault(step_id, []).append(entry)
    return mapping


def pending_total(queues: list[dict]) -> int:
    """Sum the counts of `gate` queues only -- the number the nav badge shows.

    ``backlog`` queues contribute nothing (decision 2), and an ``unknown``
    count contributes nothing rather than being guessed at as zero-or-more.

    Args:
        queues: The list returned by :func:`queue_counts`.

    Returns:
        The total number of items awaiting a human across all gate queues.
    """
    return sum(
        q["count"] for q in queues
        if q["kind"] == "gate" and isinstance(q.get("count"), int)
    )


def snapshot(db_path: str | None = None) -> dict:
    """Return the standalone payload for ``GET /api/refresh/queues``.

    Args:
        db_path: Optional DB path override.

    Returns:
        ``{"queues": [...], "pending_total": int, "computed_at": iso8601}``.
    """
    queues = queue_counts(db_path)
    return {
        "queues": queues,
        "pending_total": pending_total(queues),
        "computed_at": _dt.datetime.now().isoformat(),
    }
