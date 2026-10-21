"""Curated lists and show-pick lookups (from backend.db, TODO-369 S2)."""

import json

from backend.db import get_connection
from backend.db_queue import get_write_queue


def get_or_create_curated_list(
    name: str, label: str = "", source: str = "", db_path=None
) -> int:
    """Return the id of the curated list named ``name``, creating it if absent.

    Args:
        name: Unique slug for the list (e.g. ``'carbonbit'``, ``'10haaf'``).
        label: Human-readable display name. Only set on first creation.
        source: Free-text note on where the list came from. Only set on
            first creation.
        db_path: Optional database path override.

    Returns:
        The ``id`` of the curated_lists row.
    """
    conn = get_connection(db_path)
    row = conn.execute("SELECT id FROM curated_lists WHERE name=?", (name,)).fetchone()
    if row is not None:
        return row[0]
    _name, _label, _source = name, label, source

    def _run(c):
        cur = c.execute(
            "INSERT INTO curated_lists(name, label, source) VALUES(?,?,?)",
            (_name, _label, _source),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def delete_curated_list(name: str, db_path=None) -> bool:
    """Delete a curated list and all of its entries, by name.

    Args:
        name: The curated list's unique slug (e.g. ``'carbonbit'``).
        db_path: Optional database path override.

    Returns:
        True if a list with that name was deleted, False if none existed.
    """
    conn = get_connection(db_path)
    row = conn.execute("SELECT id FROM curated_lists WHERE name=?", (name,)).fetchone()
    if row is None:
        return False
    list_id = row[0]

    def _run(c):
        c.execute("DELETE FROM curated_list_entries WHERE list_id=?", (list_id,))
        c.execute("DELETE FROM curated_lists WHERE id=?", (list_id,))

    get_write_queue().execute(_run)
    return True


def get_curated_lists(db_path=None) -> list[dict]:
    """Return all curated lists with their entry counts.

    Args:
        db_path: Optional database path override.

    Returns:
        List of dicts with keys: id, name, label, source, created_at, entry_count.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT cl.id, cl.name, cl.label, cl.source, cl.created_at,"
        " COUNT(ce.id) AS entry_count"
        " FROM curated_lists cl LEFT JOIN curated_list_entries ce ON ce.list_id = cl.id"
        " GROUP BY cl.id ORDER BY cl.name"
    ).fetchall()
    return [dict(r) for r in rows]


def add_curated_list_entries(
    list_id: int, entries: list[tuple[int, str]], db_path=None
) -> int:
    """Bulk-insert (lb_number, note) pairs into curated_list_entries.

    Duplicate (list_id, lb_number) pairs are silently skipped via the
    table's UNIQUE constraint, so re-running an import is idempotent.

    Args:
        list_id: The curated_lists row these entries belong to.
        entries: List of (lb_number, note) tuples.
        db_path: Optional database path override.

    Returns:
        The number of entries passed in (not the number actually inserted,
        since duplicates are ignored without raising).
    """
    _list_id = list_id
    _rows = [(_list_id, lb, note) for lb, note in entries]

    def _run(c):
        c.executemany(
            "INSERT OR IGNORE INTO curated_list_entries(list_id, lb_number, note)"
            " VALUES(?,?,?)",
            _rows,
        )

    get_write_queue().execute(_run)
    return len(entries)


# ── Show picks lookup (FABLE_UNIFIED_RANKING §6 — GET /api/picks/for/<lb>) ────

def get_show_pick_for_lb(lb_number: int, db_path=None) -> dict | None:
    """Return one LB's ``show_picks`` row (rank/score/evidence), if computed.

    Args:
        lb_number: The LB number to look up.
        db_path: Optional database path override.

    Returns:
        Dict with ``concert_date``, ``lb_number``, ``pick_score``,
        ``pick_rank``, ``evidence`` (parsed from ``evidence_json`` — a list
        of ``{kind, detail, ...}`` records per F3), and ``computed_at``, or
        None if ``show_picks`` has no row for this LB (pre-recompute, or the
        entry has no usable date so it was never a scoring candidate).
    """

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT concert_date, lb_number, pick_score, pick_rank, evidence_json,"
        " computed_at FROM show_picks WHERE lb_number=?",
        (lb_number,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["evidence"] = json.loads(result.pop("evidence_json"))
    return result


def get_picks_for_date(date_iso: str, db_path=None) -> list[dict]:
    """Return all ``show_picks`` rows for one ISO concert date, rank-ordered.

    Args:
        date_iso: Concert date as ``YYYY-MM-DD``.
        db_path: Optional database path override.

    Returns:
        List of dicts (``concert_date``, ``lb_number``, ``pick_score``,
        ``pick_rank``, ``evidence``, ``concert_date_iso``, ``computed_at``),
        ordered by ``pick_rank`` ascending. Empty list if no picks were
        computed for that date.
    """

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT concert_date, lb_number, pick_score, pick_rank, evidence_json,"
        " concert_date_iso, computed_at FROM show_picks"
        " WHERE concert_date_iso=? ORDER BY pick_rank ASC",
        (date_iso,),
    ).fetchall()
    out = []
    for row in rows:
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        out.append(result)
    return out


def get_tonight_picks(mmdd: str, db_path=None, limit: int = 10) -> list[dict]:
    """Return rank-1 show picks whose concert date falls on this calendar day
    across all years — "this night in Dylan history" (LISTENING spec §9).

    Args:
        mmdd: Calendar day as ``MM-DD`` (e.g. ``"07-28"``).
        db_path: Optional database path override.
        limit: Max candidates to return, ordered by ``pick_score`` desc.

    Returns:
        List of dicts: ``lb_number``, ``concert_date_iso``, ``year``,
        ``location``, ``rating``, ``pick_score``, ``description``
        (truncated to ~200 chars). Empty list if nothing matches.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT sp.lb_number AS lb_number, sp.concert_date_iso AS concert_date_iso,"
        " sp.pick_score AS pick_score, e.location AS location, e.rating AS rating,"
        " e.description AS description"
        " FROM show_picks sp JOIN entries e ON e.lb_number = sp.lb_number"
        " WHERE sp.pick_rank = 1 AND substr(sp.concert_date_iso, 6, 5) = ?"
        " ORDER BY sp.pick_score DESC LIMIT ?",
        (mmdd, limit),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        desc = d.get("description") or ""
        d["description"] = desc[:200]
        d["year"] = int(d["concert_date_iso"][:4]) if d["concert_date_iso"] else None
        out.append(d)
    return out
