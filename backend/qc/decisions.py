"""Write model for the QC review console (``/qc-review``, TODO-342 Phase 2b C12).

Companion to :mod:`backend.qc.review` (read-only, C11): everything here
mutates ``qc_findings`` and appends to ``qc_decision_log``/``corrections``.
Routes in ``backend/app.py`` gate every entry point here on
``database.is_curator()`` before calling in — this module trusts its callers
and does not re-check the flag itself.

Decision vocabulary (see ``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md``
"Decision vocabulary"): a curator may move a finding to ``confirmed`` or
``false_positive`` from ``open``, ``confirmed`` or ``false_positive`` itself
(re-deciding is allowed); ``fixed`` and ``corrected`` are not curator
transitions from here — ``fixed`` is rule-run-only and ``corrected`` only
happens via :func:`add_correction`. ``false_positive`` binds to the finding's
*current* ``evidence_hash``; :func:`backend.qc.store.run_rule` already
reopens a sticky decision whose evidence changed underneath it.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

_DECIDABLE_STATUSES = ("open", "confirmed", "false_positive")
_TARGET_STATUSES = ("confirmed", "false_positive")


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _get_finding(conn: sqlite3.Connection, finding_id: int) -> sqlite3.Row | None:
    """Fetch one ``qc_findings`` row by id, or None."""
    return conn.execute("SELECT * FROM qc_findings WHERE id = ?", (finding_id,)).fetchone()


def _decide_no_commit(
    conn: sqlite3.Connection,
    finding_id: int,
    status: str,
    note: str | None,
    decided_by: str,
) -> None:
    """Apply one decision's writes without opening/closing a transaction.

    Callers wrap this in their own ``with conn:`` block so a batch of these
    can commit (or roll back) together.

    Raises:
        ValueError: *status* is not a legal target, the finding does not
            exist, or its current status cannot transition.
    """
    if status not in _TARGET_STATUSES:
        raise ValueError(f"status must be one of {_TARGET_STATUSES}, got {status!r}")

    row = _get_finding(conn, finding_id)
    if row is None:
        raise ValueError(f"no such finding: {finding_id}")
    if row["status"] not in _DECIDABLE_STATUSES:
        raise ValueError(
            f"finding {finding_id} is {row['status']!r}, cannot transition to {status!r}"
        )

    now = _now()
    conn.execute(
        "UPDATE qc_findings SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?",
        (status, decided_by, now, note, finding_id),
    )
    conn.execute(
        "INSERT INTO qc_decision_log (finding_id, rule_id, entity_key, prev_status,"
        " new_status, note, decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (finding_id, row["rule_id"], row["entity_key"], row["status"], status, note,
         decided_by, now),
    )


def decide(
    conn: sqlite3.Connection,
    finding_id: int,
    status: str,
    note: str | None = None,
    decided_by: str = "ui",
) -> dict:
    """Record a curator decision on one finding.

    Args:
        conn: Open SQLite connection.
        finding_id: ``qc_findings.id``.
        status: Target status, one of ``confirmed`` or ``false_positive``.
        note: Optional free-text curator note.
        decided_by: Origin recorded in the log row (``'ui'``/``'bulk'``).

    Returns:
        The updated ``qc_findings`` row as a dict.

    Raises:
        ValueError: *status* is not a legal target, the finding does not
            exist, or its current status cannot transition (e.g. ``fixed``
            or ``corrected``).
    """
    with conn:
        _decide_no_commit(conn, finding_id, status, note, decided_by)
    updated = _get_finding(conn, finding_id)
    return dict(updated)


def bulk_decide(
    conn: sqlite3.Connection,
    ids: list[int],
    status: str,
    note: str | None = None,
) -> list[dict]:
    """Apply :func:`decide` to many findings from one rule, all-or-nothing.

    Args:
        conn: Open SQLite connection.
        ids: Finding IDs to decide. Must all share one ``rule_id``.
        status: Target status, one of ``confirmed`` or ``false_positive``.
        note: Optional free-text curator note, applied to every finding.

    Returns:
        The updated ``qc_findings`` rows, one per id, in the given order.

    Raises:
        ValueError: *ids* is empty, the ids don't all share one ``rule_id``,
            or any single decision would be illegal (in which case nothing
            is written).
    """
    if not ids:
        raise ValueError("ids must not be empty")

    rows = {
        r["id"]: r for r in conn.execute(
            f"SELECT * FROM qc_findings WHERE id IN ({','.join('?' * len(ids))})", ids
        )
    }
    missing = [i for i in ids if i not in rows]
    if missing:
        raise ValueError(f"no such finding(s): {missing}")

    rule_ids = {rows[i]["rule_id"] for i in ids}
    if len(rule_ids) != 1:
        raise ValueError(f"bulk decisions must share one rule_id, got {sorted(rule_ids)}")

    with conn:
        for i in ids:
            _decide_no_commit(conn, i, status, note, "bulk")
    return [dict(_get_finding(conn, i)) for i in ids]


def add_correction(
    conn: sqlite3.Connection,
    finding_id: int,
    field: str,
    corrected: str,
    reason: str | None = None,
    original: str | None = None,
    decided_by: str = "ui",
) -> dict:
    """Record a curator field override and move its finding to ``corrected``.

    Args:
        conn: Open SQLite connection.
        finding_id: ``qc_findings.id`` the correction resolves.
        field: The corrected field name.
        corrected: The corrected value.
        reason: Optional free-text reason.
        original: The pre-correction value; taken from the finding's evidence
            when not supplied and present there, else left ``None``.
        decided_by: Origin recorded in the log row.

    Returns:
        ``{"correction": {...}, "finding": {...}}``.

    Raises:
        ValueError: The finding does not exist, or its current status cannot
            transition (``fixed``, already ``corrected``).
    """
    row = _get_finding(conn, finding_id)
    if row is None:
        raise ValueError(f"no such finding: {finding_id}")
    if row["status"] not in _DECIDABLE_STATUSES:
        raise ValueError(
            f"finding {finding_id} is {row['status']!r}, cannot be corrected"
        )

    now = _now()
    with conn:
        cur = conn.execute(
            "INSERT INTO corrections (entity_kind, entity_key, field, original, corrected,"
            " reason, decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["entity_kind"], row["entity_key"], field, original, corrected, reason,
             decided_by, now),
        )
        correction_id = cur.lastrowid

        conn.execute(
            "UPDATE qc_findings SET status='corrected', decided_by=?, decided_at=?, note=?"
            " WHERE id=?",
            (decided_by, now, reason, finding_id),
        )
        conn.execute(
            "INSERT INTO qc_decision_log (finding_id, rule_id, entity_key, prev_status,"
            " new_status, note, decided_by, decided_at) VALUES (?, ?, ?, ?, 'corrected', ?, ?, ?)",
            (finding_id, row["rule_id"], row["entity_key"], row["status"], reason, decided_by,
             now),
        )
        correction = conn.execute(
            "SELECT * FROM corrections WHERE id = ?", (correction_id,)
        ).fetchone()

    finding = _get_finding(conn, finding_id)
    return {"correction": dict(correction), "finding": dict(finding)}


def classify_release(
    conn: sqlite3.Connection,
    title_key: str,
    official: bool,
    note: str | None = None,
    decided_by: str = "ui",
) -> dict:
    """Record a curator verdict on one release title (D-03, R-R1).

    Upserts ``release_classifications`` (it wins over the packaged
    ``backend/assets/official_releases.json`` allowlist for this
    ``title_key`` from here on) and immediately closes any open/confirmed/
    false_positive R-R1 finding for it — unlike a taper rejection, there is
    nothing further to re-derive: the classification itself is the fix.

    Args:
        conn: Open SQLite connection.
        title_key: :func:`backend.dossier_fields.normalize_title_key` of the
            raw release string (also the R-R1 finding's ``entity_key``).
        official: The curator's verdict.
        note: Optional free-text note.
        decided_by: Origin recorded in the log row.

    Returns:
        ``{"classification": {...}, "finding": {...} | None}`` — *finding*
        is ``None`` when no matching R-R1 finding exists (a title classified
        ahead of its first rule run).
    """
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO release_classifications (title_key, official, decided_by, decided_at,"
            " note) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(title_key) DO UPDATE SET official=excluded.official,"
            " decided_by=excluded.decided_by, decided_at=excluded.decided_at, note=excluded.note",
            (title_key, int(official), decided_by, now, note),
        )
        classification = conn.execute(
            "SELECT * FROM release_classifications WHERE title_key = ?", (title_key,)
        ).fetchone()

        finding_row = conn.execute(
            "SELECT * FROM qc_findings WHERE rule_id = 'R-R1' AND entity_kind = 'release'"
            " AND entity_key = ? AND status IN (?, ?, ?)",
            (title_key, *_DECIDABLE_STATUSES),
        ).fetchone()
        finding = None
        if finding_row is not None:
            conn.execute(
                "UPDATE qc_findings SET status='fixed', decided_by=?, decided_at=?, note=?"
                " WHERE id=?",
                (decided_by, now, note, finding_row["id"]),
            )
            conn.execute(
                "INSERT INTO qc_decision_log (finding_id, rule_id, entity_key, prev_status,"
                " new_status, note, decided_by, decided_at) VALUES (?, 'R-R1', ?, ?, 'fixed',"
                " ?, ?, ?)",
                (finding_row["id"], title_key, finding_row["status"], note, decided_by, now),
            )
            finding = dict(_get_finding(conn, finding_row["id"]))

    return {"classification": dict(classification), "finding": finding}
