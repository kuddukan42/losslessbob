"""Read model for the QC review console (``/qc-review``, TODO-342 Phase 2b).

Mirrors ``backend/taper_curation.py``: everything here is read-only. Writes
(decisions, corrections, rule runs) are C12's job and go through curator-gated
routes that log to ``qc_decision_log`` the same way :mod:`backend.qc.store`
does.

Four entry points back the console:

* :func:`summary` — the header chips: open errors/warnings, per-rule counts
  by severity x status, and each rule's last ``qc_runs`` row.
* :func:`list_findings` — the Findings tab's workbench table, paged and
  filtered.
* :func:`get_finding` — one finding's detail drawer: its evidence, a
  rule-family-specific context panel (the taper_attributions row for
  R-T1-T4, Olof raw text vs parsed songs for R-O1/R-O3, etc.), and the ISO
  dossier dates the entity touches (for "Open dossier" links).
* :func:`list_decisions` — the append-only ``qc_decision_log``, for the
  decisions view / a finding's own history.

Affected-dossier-date resolution (:func:`affected_dates`) is best-effort per
``entity_kind``: it answers "which /qc-review shows have withheld fields
because of this finding", not a guaranteed-complete cross-reference. An
entity kind it doesn't recognise yields an empty list rather than raising.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from backend.db import get_connection
from backend.geocoder import entry_date_to_iso
from backend.qc.rules import RULES

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 200
_QUARANTINE_STATUSES = ("open", "confirmed")


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    """Clamp paging params to sane bounds.

    Args:
        page: Requested 1-based page number.
        page_size: Requested page size.

    Returns:
        ``(page, page_size)`` with page >= 1 and 1 <= page_size <= MAX_PAGE_SIZE.
    """
    return max(1, int(page)), max(1, min(int(page_size), MAX_PAGE_SIZE))


# ── affected dossier dates ──────────────────────────────────────────────────

def _venue_dates_index(conn: sqlite3.Connection, cache: dict | None) -> dict:
    """Return ``{(venue_norm, city_norm): {iso dates}}`` over olof_events, once per cache."""
    if cache is not None and "venue" in cache:
        return cache["venue"]
    from backend.venue_gazetteer import _norm_city, _norm_venue

    index: dict[tuple[str, str], set[str]] = {}
    for venue, city, date_str in conn.execute(
        "SELECT venue, city, date_str FROM olof_events WHERE date_str != ''"
    ):
        index.setdefault((_norm_venue(venue), _norm_city(city)), set()).add(date_str)
    if cache is not None:
        cache["venue"] = index
    return index


def affected_dates(
    conn: sqlite3.Connection, entity_kind: str, entity_key: str, cache: dict | None = None,
) -> list[str]:
    """Return the ISO dossier dates an entity touches.

    Args:
        conn: Open SQLite connection.
        entity_kind: A ``qc_findings.entity_kind`` value ('lb', 'entry',
            'olof_event', 'olof_song', 'venue', 'family', 'table', ...).
        entity_key: The entity's key within its kind.
        cache: Optional per-request dict; venue lookups share one olof_events
            index through it instead of rescanning the table per finding.

    Returns:
        Sorted distinct ISO ``YYYY-MM-DD`` dates, empty when the kind isn't
        date-resolvable (e.g. 'table') or the entity no longer exists.
    """
    try:
        if entity_kind in ("lb", "entry"):
            row = conn.execute(
                "SELECT date_str FROM entries WHERE lb_number = ?", (int(entity_key),)
            ).fetchone()
            if not row:
                return []
            iso = entry_date_to_iso(row["date_str"])
            return [iso] if iso else []

        if entity_kind in ("olof_event", "olof_song"):
            event_id = entity_key.split(":")[0]
            row = conn.execute(
                "SELECT date_str FROM olof_events WHERE event_id = ?", (int(event_id),)
            ).fetchone()
            return [row["date_str"]] if row and row["date_str"] else []

        if entity_kind == "venue":
            venue_norm, _, city_norm = entity_key.partition(":")
            return sorted(_venue_dates_index(conn, cache).get((venue_norm, city_norm), ()))

        if entity_kind == "family":
            rows = conn.execute(
                "SELECT DISTINCT concert_date FROM recording_families WHERE fam_id = ?",
                (entity_key,),
            ).fetchall()
            return sorted({r[0] for r in rows if r[0]})
    except (ValueError, sqlite3.Error):
        logger.exception("affected_dates failed for %s/%s", entity_kind, entity_key)
        return []

    return []


# ── rule-family context panels ──────────────────────────────────────────────

def _taper_context(conn: sqlite3.Connection, lb_number: int) -> dict:
    """Context for R-T1-T4: the attribution row, entry description, TUIT tapers."""
    attr = conn.execute(
        "SELECT * FROM taper_attributions WHERE lb_number = ?", (lb_number,)
    ).fetchone()
    entry = conn.execute(
        "SELECT lb_number, date_str, location, taper_name, description"
        " FROM entries WHERE lb_number = ?", (lb_number,)
    ).fetchone()
    tuit = conn.execute(
        "SELECT rec_id, taper, source_type, quality, uploader"
        " FROM tuit_recordings WHERE lb_number = ? ORDER BY rec_id", (lb_number,)
    ).fetchall()
    return {
        "attribution": dict(attr) if attr else None,
        "entry": dict(entry) if entry else None,
        "tuit_tapers": [dict(r) for r in tuit],
    }


def _olof_context(conn: sqlite3.Connection, entity_kind: str, entity_key: str) -> dict:
    """Context for R-O1/R-O2/R-O3: Olof raw_text vs the parsed olof_songs rows."""
    event_id = int(entity_key.split(":")[0] if entity_kind == "olof_song" else entity_key)
    event = conn.execute(
        "SELECT event_id, date_str, venue, city, event_type, raw_text"
        " FROM olof_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    songs = conn.execute(
        "SELECT position, song_title, annotations FROM olof_songs"
        " WHERE event_id = ? ORDER BY position", (event_id,)
    ).fetchall()
    return {
        "event": dict(event) if event else None,
        "raw_text": event["raw_text"] if event else None,
        "parsed_songs": [dict(s) for s in songs],
    }


def _geocode_context(conn: sqlite3.Connection, entity_key: str) -> dict:
    """Context for R-G1: the venue name plus its venue_geocoded row."""
    venue_norm, _, city_norm = entity_key.partition(":")
    row = conn.execute(
        "SELECT * FROM venue_geocoded WHERE venue_norm = ? AND city_norm = ?",
        (venue_norm, city_norm),
    ).fetchone()
    return {"venue_geocoded": dict(row) if row else None}


def _entry_context(conn: sqlite3.Connection, lb_number: int) -> dict:
    """Context for R-E1/R-E2: the full entries row."""
    row = conn.execute("SELECT * FROM entries WHERE lb_number = ?", (lb_number,)).fetchone()
    return {"entry": dict(row) if row else None}


def _family_context(conn: sqlite3.Connection, fam_id: str) -> dict:
    """Context for R-F1: the family's meta row plus its member LBs."""
    meta = conn.execute(
        "SELECT * FROM tapematch_family_meta WHERE fam_id = ?", (fam_id,)
    ).fetchone()
    members = conn.execute(
        "SELECT lb_number FROM recording_families WHERE fam_id = ? ORDER BY lb_number",
        (fam_id,),
    ).fetchall()
    return {
        "family_meta": dict(meta) if meta else None,
        "members": [r["lb_number"] for r in members],
    }


def _build_context(
    conn: sqlite3.Connection, rule_id: str, entity_kind: str, entity_key: str, evidence: dict
) -> dict:
    """Dispatch to the rule-family context builder for one finding.

    Args:
        conn: Open SQLite connection.
        rule_id: The finding's rule, e.g. 'R-T1'.
        entity_kind: The finding's entity kind.
        entity_key: The finding's entity key.
        evidence: The finding's parsed evidence dict (R-S1's context is just this).

    Returns:
        A rule-family-shaped context dict, empty on any lookup failure.
    """
    try:
        if rule_id.startswith("R-T"):
            return _taper_context(conn, int(entity_key))
        if rule_id in ("R-O1", "R-O2", "R-O3"):
            return _olof_context(conn, entity_kind, entity_key)
        if rule_id == "R-G1":
            return _geocode_context(conn, entity_key)
        if rule_id in ("R-E1", "R-E2"):
            return _entry_context(conn, int(entity_key))
        if rule_id == "R-F1":
            return _family_context(conn, entity_key)
        if rule_id == "R-S1":
            return dict(evidence)
    except (ValueError, sqlite3.Error):
        logger.exception("qc context build failed for %s/%s/%s", rule_id, entity_kind, entity_key)
    return {}


# ── summary ──────────────────────────────────────────────────────────────────

def summary(db_path: str | None = None) -> dict:
    """Header-chip data: per-rule counts by severity x status, last run, totals.

    Args:
        db_path: Optional database path override.

    Returns:
        ``{"rules": {rule_id: {"description", "default_severity", "counts",
        "last_run"}}, "total_open_errors", "total_open_warnings", "last_run_at"}``.
    """
    conn = get_connection(db_path)
    rules_out: dict[str, dict] = {}
    for rule_id, rule in RULES.items():
        counts: dict[str, dict[str, int]] = {}
        for severity, status, n in conn.execute(
            "SELECT severity, status, COUNT(*) FROM qc_findings WHERE rule_id = ?"
            " GROUP BY severity, status",
            (rule_id,),
        ):
            counts.setdefault(severity, {})[status] = n
        last_run = conn.execute(
            "SELECT run_id, started_at, finished_at, n_open, n_new, n_fixed, n_reopened"
            " FROM qc_runs WHERE rule_id = ? ORDER BY run_id DESC LIMIT 1",
            (rule_id,),
        ).fetchone()
        rules_out[rule_id] = {
            "description": rule.description,
            "default_severity": rule.severity,
            "counts": counts,
            "last_run": dict(last_run) if last_run else None,
        }

    total_open_errors = conn.execute(
        "SELECT COUNT(*) FROM qc_findings WHERE severity = 'error'"
        " AND status IN ('open', 'confirmed')"
    ).fetchone()[0]
    total_open_warnings = conn.execute(
        "SELECT COUNT(*) FROM qc_findings WHERE severity = 'warn'"
        " AND status IN ('open', 'confirmed')"
    ).fetchone()[0]
    last_run_at = conn.execute("SELECT MAX(finished_at) FROM qc_runs").fetchone()[0]

    return {
        "rules": rules_out,
        "total_open_errors": total_open_errors,
        "total_open_warnings": total_open_warnings,
        "last_run_at": last_run_at,
    }


# ── findings list ────────────────────────────────────────────────────────────

def _filters(
    rule: str | None, severity: str | None, status: str | None,
    entity_kind: str | None, q: str | None,
) -> tuple[str, list]:
    """Build the shared WHERE clause for the findings list.

    Args:
        rule: Restrict to one rule_id.
        severity: Restrict to one severity.
        status: Restrict to one status.
        entity_kind: Restrict to one entity_kind.
        q: Free-text search over detail and entity_key.

    Returns:
        ``(where_sql, params)``.
    """
    clauses: list[str] = []
    params: list = []
    if rule:
        clauses.append("rule_id = ?")
        params.append(rule)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if entity_kind:
        clauses.append("entity_kind = ?")
        params.append(entity_kind)
    if q:
        like = f"%{q}%"
        clauses.append("(detail LIKE ? OR entity_key LIKE ?)")
        params.extend([like, like])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _row_to_summary(row: sqlite3.Row) -> dict:
    """Shape a qc_findings row for the list view (no evidence_json blob)."""
    d = dict(row)
    d.pop("evidence_json", None)
    return d


def list_findings(
    rule: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    entity_kind: str | None = None,
    date: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db_path: str | None = None,
) -> dict:
    """One page of the Findings workbench table.

    Args:
        rule: Restrict to one rule_id (e.g. 'R-T1').
        severity: Restrict to one severity ('error'/'warn'/'info').
        status: Restrict to one status.
        entity_kind: Restrict to one entity_kind.
        date: Restrict to findings whose entity touches this ISO date. Applied
            in Python (affected dates are computed, not stored), so it filters
            the SQL-matched set before paging rather than the raw table.
        q: Free-text search over detail and entity_key.
        page: 1-based page number.
        page_size: Rows per page, clamped to [1, MAX_PAGE_SIZE].
        db_path: Optional database path override.

    Returns:
        ``{"rows": [...], "total": int, "page": int, "page_size": int}``, each
        row carrying ``affected_dates`` and ``shows_affected``.
    """
    conn = get_connection(db_path)
    page, page_size = _clamp_page(page, page_size)
    where, params = _filters(rule, severity, status, entity_kind, q)
    cache: dict = {}

    if date:
        # Date filtering needs every matched row's affected dates computed
        # before it can page, so it can't use LIMIT/OFFSET in SQL.
        rows = [_row_to_summary(r) for r in conn.execute(
            f"SELECT * FROM qc_findings{where} ORDER BY last_seen DESC, id DESC", params
        )]
        for r in rows:
            r["affected_dates"] = affected_dates(conn, r["entity_kind"], r["entity_key"], cache)
        rows = [r for r in rows if date in r["affected_dates"]]
        total = len(rows)
        page_rows = rows[(page - 1) * page_size: page * page_size]
        for r in page_rows:
            r["shows_affected"] = len(r["affected_dates"])
    else:
        total = conn.execute(
            f"SELECT COUNT(*) FROM qc_findings{where}", params
        ).fetchone()[0]
        page_rows = [_row_to_summary(r) for r in conn.execute(
            f"SELECT * FROM qc_findings{where} ORDER BY last_seen DESC, id DESC"
            " LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        )]
        for r in page_rows:
            dates = affected_dates(conn, r["entity_kind"], r["entity_key"], cache)
            r["affected_dates"] = dates
            r["shows_affected"] = len(dates)

    return {"rows": page_rows, "total": total, "page": page, "page_size": page_size}


def get_finding(finding_id: int, db_path: str | None = None) -> dict | None:
    """One finding with its evidence, rule-family context and affected dates.

    Args:
        finding_id: ``qc_findings.id``.
        db_path: Optional database path override.

    Returns:
        The finding dict, or None when no such finding exists.
    """
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM qc_findings WHERE id = ?", (finding_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
    rule = RULES.get(d["rule_id"])
    d["rule_description"] = rule.description if rule else None
    d["default_severity"] = rule.severity if rule else None
    d["quarantined"] = d["severity"] == "error" and d["status"] in _QUARANTINE_STATUSES
    d["context"] = _build_context(
        conn, d["rule_id"], d["entity_kind"], d["entity_key"], d["evidence"]
    )
    d["affected_dates"] = affected_dates(conn, d["entity_kind"], d["entity_key"])
    return d


# ── decision log ─────────────────────────────────────────────────────────────

def list_decisions(
    page: int = 1,
    page_size: int = 50,
    finding_id: int | None = None,
    db_path: str | None = None,
) -> dict:
    """Paged ``qc_decision_log``, newest first.

    Args:
        page: 1-based page number.
        page_size: Rows per page, clamped to [1, MAX_PAGE_SIZE].
        finding_id: Restrict to one finding's history.
        db_path: Optional database path override.

    Returns:
        ``{"rows": [...], "total": int, "page": int, "page_size": int}``.
    """
    conn = get_connection(db_path)
    page, page_size = _clamp_page(page, page_size)
    where, params = "", []
    if finding_id is not None:
        where = " WHERE finding_id = ?"
        params.append(finding_id)
    total = conn.execute(
        f"SELECT COUNT(*) FROM qc_decision_log{where}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM qc_decision_log{where} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "rows": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
