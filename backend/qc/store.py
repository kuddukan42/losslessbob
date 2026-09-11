"""QC run engine and quarantine lookups (TODO-342 Phase 2).

Runs registered rules against a connection, reconciling their output against
``qc_findings`` per the status state machine in
``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md`` "Decision vocabulary", and
answers the quarantine question dossier rendering needs: is this entity
covered by an open/confirmed error finding?
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.qc.rules import RULES, RuleDef

_log = logging.getLogger(__name__)

# Statuses that hold the quarantine on an entity.
_QUARANTINE_STATUSES = ("open", "confirmed")
# Statuses a curator has judged; a changed evidence hash reopens them.
_STICKY_STATUSES = ("false_positive", "corrected")


def evidence_hash(evidence: dict) -> str:
    """Return the sha256 hex digest of *evidence* as canonical compact JSON.

    Args:
        evidence: JSON-serialisable evidence dict.

    Returns:
        Hex-encoded sha256 digest, stable across dict key order.
    """
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class RunStats:
    """Per-rule run result, mirroring a ``qc_runs`` row.

    Attributes:
        rule_id: The rule that was run.
        n_open: Open+confirmed finding count after the run.
        n_new: Findings created this run.
        n_fixed: Findings that stopped firing this run.
        n_reopened: Findings reopened this run (sticky decision, changed evidence).
    """

    rule_id: str
    n_open: int = 0
    n_new: int = 0
    n_fixed: int = 0
    n_reopened: int = 0


def run_rule(conn: sqlite3.Connection, rule: RuleDef) -> RunStats:
    """Run one QC rule and reconcile its findings against ``qc_findings``.

    Args:
        conn: Open SQLite connection. The whole reconciliation runs as one
            transaction.
        rule: The rule to run.

    Returns:
        Stats for the run, already recorded as a ``qc_runs`` row.
    """
    started_at = _now()
    stats = RunStats(rule_id=rule.rule_id)

    emitted: dict[tuple[str, str], tuple] = {}
    for finding in rule.func(conn):
        key = (finding.entity_kind, finding.entity_key)
        emitted[key] = (finding, evidence_hash(finding.evidence))

    existing = {
        (row["entity_kind"], row["entity_key"]): row
        for row in conn.execute(
            "SELECT * FROM qc_findings WHERE rule_id = ?", (rule.rule_id,)
        ).fetchall()
    }

    with conn:
        now = _now()
        for key, (finding, ehash) in emitted.items():
            row = existing.get(key)
            evidence_json = json.dumps(finding.evidence, sort_keys=True)
            if row is None:
                conn.execute(
                    "INSERT INTO qc_findings (rule_id, entity_kind, entity_key, severity,"
                    " detail, evidence_json, evidence_hash, first_seen, last_seen, status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                    (rule.rule_id, finding.entity_kind, finding.entity_key, finding.severity,
                     finding.detail, evidence_json, ehash, now, now),
                )
                stats.n_new += 1
                continue

            if row["status"] in ("open", "confirmed"):
                # Severity is per finding (R-O4 grades order-only disputes 'warn'),
                # so a re-run refreshes it along with the evidence.
                conn.execute(
                    "UPDATE qc_findings SET severity=?, detail=?, evidence_json=?,"
                    " evidence_hash=?, last_seen=? WHERE id=?",
                    (finding.severity, finding.detail, evidence_json, ehash, now, row["id"]),
                )
                continue

            if row["status"] in _STICKY_STATUSES:
                if row["evidence_hash"] == ehash:
                    conn.execute(
                        "UPDATE qc_findings SET last_seen=? WHERE id=?", (now, row["id"])
                    )
                    continue
                _transition(
                    conn, row, "open", now, finding.detail, evidence_json, ehash,
                    note="evidence changed since decision", severity=finding.severity,
                )
                stats.n_reopened += 1
                continue

            if row["status"] == "fixed":
                _transition(
                    conn, row, "open", now, finding.detail, evidence_json, ehash,
                    note="rule fired again", severity=finding.severity,
                )
                stats.n_reopened += 1
                continue

        for key, row in existing.items():
            if key in emitted:
                continue
            if row["status"] in ("open", "confirmed"):
                _transition(
                    conn, row, "fixed", now, row["detail"], row["evidence_json"],
                    row["evidence_hash"], note="rule no longer fires",
                )
                stats.n_fixed += 1
            # false_positive / corrected rows that stop firing are left alone.

        stats.n_open = conn.execute(
            "SELECT COUNT(*) FROM qc_findings WHERE rule_id=? AND status IN ('open','confirmed')",
            (rule.rule_id,),
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO qc_runs (rule_id, started_at, finished_at, n_open, n_new,"
            " n_fixed, n_reopened) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rule.rule_id, started_at, now, stats.n_open, stats.n_new, stats.n_fixed,
             stats.n_reopened),
        )

    return stats


def _transition(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    new_status: str,
    now: str,
    detail: str,
    evidence_json: str,
    ehash: str,
    note: str,
    severity: str | None = None,
) -> None:
    """Move a finding to *new_status*, updating its row and appending a log entry.

    *severity* replaces the stored one when given (a reopen re-grades the finding);
    ``None`` keeps it.
    """
    conn.execute(
        "UPDATE qc_findings SET status=?, severity=COALESCE(?, severity), detail=?,"
        " evidence_json=?, evidence_hash=?, last_seen=?, decided_by='qc-run', decided_at=?,"
        " note=? WHERE id=?",
        (new_status, severity, detail, evidence_json, ehash, now, now, note, row["id"]),
    )
    conn.execute(
        "INSERT INTO qc_decision_log (finding_id, rule_id, entity_key, prev_status,"
        " new_status, note, decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, 'qc-run', ?)",
        (row["id"], row["rule_id"], row["entity_key"], row["status"], new_status, note, now),
    )


def run_all(conn: sqlite3.Connection, rule_ids: list[str] | None = None) -> list[RunStats]:
    """Run every registered rule, or only *rule_ids* when given.

    Args:
        conn: Open SQLite connection.
        rule_ids: Optional subset of rule IDs to run; defaults to all of
            :data:`backend.qc.rules.RULES`.

    Returns:
        One :class:`RunStats` per rule run, in rule-id order.

    Raises:
        KeyError: A requested rule ID is not registered.
    """
    ids = rule_ids if rule_ids is not None else sorted(RULES)
    results = []
    for rule_id in ids:
        rule = RULES[rule_id]
        _log.debug("Running QC rule %s", rule_id)
        results.append(run_rule(conn, rule))
    return results


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def quarantined(conn: sqlite3.Connection, entity_kind: str, entity_key: str) -> list[str]:
    """Return rule IDs of open/confirmed error findings against one entity.

    Returns an empty list (rather than raising) when ``qc_findings`` does not
    exist yet, so dossier rendering works before ``init_db`` has run QC.

    Args:
        conn: Open SQLite connection.
        entity_kind: Entity kind, e.g. 'olof_event'.
        entity_key: Entity key within that kind.

    Returns:
        Rule IDs currently quarantining this entity, empty if none.
    """
    if not _table_exists(conn, "qc_findings"):
        return []
    rows = conn.execute(
        "SELECT rule_id FROM qc_findings WHERE entity_kind=? AND entity_key=?"
        " AND severity='error' AND status IN ('open','confirmed')",
        (entity_kind, entity_key),
    ).fetchall()
    return [r[0] for r in rows]


def quarantined_batch(
    conn: sqlite3.Connection, entity_kind: str, entity_keys: list[str]
) -> dict[str, list[str]]:
    """Batch form of :func:`quarantined` over many keys of the same kind.

    Args:
        conn: Open SQLite connection.
        entity_kind: Entity kind shared by all keys.
        entity_keys: Entity keys to look up.

    Returns:
        Map of entity_key -> rule IDs currently quarantining it. Keys with no
        open/confirmed error findings are omitted.
    """
    if not entity_keys or not _table_exists(conn, "qc_findings"):
        return {}
    result: dict[str, list[str]] = {}
    placeholders = ",".join("?" for _ in entity_keys)
    rows = conn.execute(
        f"SELECT entity_key, rule_id FROM qc_findings WHERE entity_kind=?"
        f" AND entity_key IN ({placeholders})"
        " AND severity='error' AND status IN ('open','confirmed')",
        (entity_kind, *entity_keys),
    ).fetchall()
    for entity_key, rule_id in rows:
        result.setdefault(entity_key, []).append(rule_id)
    return result
