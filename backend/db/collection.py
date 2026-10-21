"""My Collection, wishlist, duplicates, personal metadata, integrity events.

Split from backend.db (TODO-369 S2).
"""

from backend.db import get_connection
from backend.db.library import _year_from_date_str
from backend.db.pipeline_cache import _norm_folder
from backend.db_queue import get_write_queue


def _mount_label_for_path(disk_path: str, mounts: list[dict]) -> "str | None":
    """Return the label of the mount whose root_path best (longest) matches disk_path.

    Pure prefix match on normalised (forward-slash) paths. Mirrors
    integrity_monitor._mount_for_path but returns the mount label and uses
    _norm_folder instead of filer.normalise_path, so it stays inside backend.db
    without the backend.db ↔ backend.filer / integrity_monitor import cycle.

    Args:
        disk_path: A my_collection.disk_path value.
        mounts: Rows from get_collection_mounts() (need id/label/root_path).

    Returns:
        The matching mount label, or None if disk_path sits under no mount root.
    """
    norm_path = _norm_folder(disk_path)
    best_label = None
    best_len = -1
    for m in mounts:
        norm_root = _norm_folder(m["root_path"]).rstrip("/")
        if norm_path == norm_root or norm_path.startswith(norm_root + "/"):
            if len(norm_root) > best_len:
                best_len = len(norm_root)
                best_label = m["label"]
    return best_label


def get_collection(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT c.id, c.lb_number, c.folder_name, c.disk_path, c.confirmed_at, c.notes,
                   c.lbdir_verified_at, c.xref,
                   e.date_str, e.location, e.description, e.rating, e.cdr, e.lb_category,
                   e.source_type, lm.lb_status
            FROM my_collection c
            LEFT JOIN entries e ON c.lb_number = e.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = c.lb_number
            ORDER BY c.lb_number
        """).fetchall()
        alias_rows = conn.execute(
            "SELECT alias_lb, canonical_lb FROM lb_alias"
        ).fetchall()
        mounts = [dict(m) for m in conn.execute(
            "SELECT id, label, root_path FROM collection_mounts"
        ).fetchall()]
        # year -> expected mount label, from the configured routing table.
        routes_by_year = {
            rr["year"]: rr["mount_label"]
            for rr in conn.execute(
                "SELECT r.year, m.label AS mount_label FROM collection_routes r "
                "JOIN collection_mounts m ON m.id = r.mount_id"
            ).fetchall()
        }

    # Build bidirectional map: lb -> [all linked lbs in either direction]
    linked: dict[int, list[int]] = {}
    for ar in alias_rows:
        a, c = ar["alias_lb"], ar["canonical_lb"]
        linked.setdefault(a, []).append(c)
        linked.setdefault(c, []).append(a)

    result = []
    for r in rows:
        d = dict(r)
        d["linked_lbs"] = sorted(linked.get(d["lb_number"], []))
        d.update(_route_status(d["disk_path"], d.get("date_str"), mounts, routes_by_year))
        result.append(d)
    return result


def _route_status(
    disk_path: str,
    date_str: "str | None",
    mounts: list[dict],
    routes_by_year: dict[int, str],
) -> dict:
    """Classify a folder's disk_path against its year's expected mount routing (TODO-166).

    Compares where the folder actually lives (the mount whose root_path is a
    prefix of disk_path) against where its show-year is configured to route
    (collection_routes). Surfaces folders that drifted to a nonstandard location.

    Args:
        disk_path: Absolute folder path from my_collection.
        date_str: The entry's date_str, used to derive the show year.
        mounts: collection_mounts rows (id/label/root_path).
        routes_by_year: year -> expected mount label, from collection_routes.

    Returns:
        Dict with:
            route_status: one of
                "ok"          — folder is under the year's routed mount;
                "wrong_mount" — folder is under a different mount than the route;
                "no_mount"    — a route exists but the folder is under no mount;
                "no_route"    — no route configured for this year (can't evaluate);
                "no_date"     — no parseable year (can't evaluate).
                Only "wrong_mount"/"no_mount" are genuine drift.
            route_actual_mount: label the disk_path resolves to (or None).
            route_expected_mount: label the year should route to (or None).
            route_year: the derived show year (or None).
    """
    year = _year_from_date_str(date_str or "")
    actual = _mount_label_for_path(disk_path, mounts) if disk_path else None
    expected = routes_by_year.get(year)
    if not year:
        status = "no_date"
    elif expected is None:
        status = "no_route"
    elif actual is None:
        status = "no_mount"
    elif actual != expected:
        status = "wrong_mount"
    else:
        status = "ok"
    return {
        "route_status": status,
        "route_actual_mount": actual,
        "route_expected_mount": expected,
        "route_year": year or None,
    }


def add_to_collection(lb_number, folder_name, disk_path, notes=None, xref: int = 0, db_path=None):
    """Insert a new my_collection row (ignored if lb_number already exists).

    Args:
        lb_number: LB entry number.
        folder_name: Folder name at filing time.
        disk_path: Absolute destination path.
        notes: Optional user note.
        xref: Xref fileset id this copy matches (0 = canonical), carried in
            from the pipeline's ``matched_xref`` (FABLE_XREF_INCORPORATION.md D3).
        db_path: Optional path to the SQLite database file.

    Returns:
        Number of rows inserted (0 or 1).
    """
    _lb, _fn, _dp, _n, _xref = lb_number, folder_name, disk_path, notes, xref

    def _run(c):
        c.execute(
            "INSERT OR IGNORE INTO my_collection(lb_number, folder_name, disk_path, notes, xref)"
            " VALUES(?,?,?,?,?)",
            (_lb, _fn, _dp, _n, _xref)
        )
        return c.execute("SELECT changes()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection(lb_number, fields, db_path=None):
    allowed = {"folder_name", "disk_path", "notes", "xref"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    _params = list(updates.values()) + [lb_number]
    _sql = f"UPDATE my_collection SET {set_clause} WHERE lb_number=?"
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


def delete_from_collection(lb_number, db_path=None):
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM my_collection WHERE lb_number=?", (_lb,))
    )


def reassign_collection(old_lb, new_lb, db_path=None):
    """Move a filed folder from one LB entry to another.

    Repoints the ``my_collection`` row (folder_name/disk_path/notes/xref) from
    ``old_lb`` to ``new_lb`` and carries any ``collection_meta`` (personal
    rating, listen count, tags) across so it survives the move. The folder on
    disk is untouched — use folder rename for that (TODO-259).

    Args:
        old_lb: LB number the folder is currently filed under.
        new_lb: LB number to move it to.
        db_path: Optional path to the SQLite database file.

    Raises:
        ValueError: If ``old_lb`` is not owned, ``new_lb`` is absent from the
            catalog, ``new_lb`` is already owned, or the two are equal.
    """
    _old, _new = int(old_lb), int(new_lb)
    if _old == _new:
        raise ValueError("Source and target LB are the same")

    def _run(c):
        row = c.execute(
            "SELECT folder_name, disk_path, notes, xref FROM my_collection"
            " WHERE lb_number=?",
            (_old,),
        ).fetchone()
        if row is None:
            raise ValueError(f"LB-{_old:05d} is not in your collection")
        if c.execute("SELECT 1 FROM entries WHERE lb_number=?", (_new,)).fetchone() is None:
            raise ValueError(f"LB-{_new:05d} does not exist in the catalog")
        if c.execute(
            "SELECT 1 FROM my_collection WHERE lb_number=?", (_new,)
        ).fetchone() is not None:
            raise ValueError(f"LB-{_new:05d} is already in your collection")
        folder_name, disk_path, notes, xref = row
        meta = c.execute(
            "SELECT personal_rating, listen_count, last_listened, tags"
            " FROM collection_meta WHERE lb_number=?",
            (_old,),
        ).fetchone()
        c.execute(
            "INSERT INTO my_collection(lb_number, folder_name, disk_path, notes, xref)"
            " VALUES(?,?,?,?,?)",
            (_new, folder_name, disk_path, notes, xref),
        )
        if meta is not None:
            c.execute(
                "INSERT OR REPLACE INTO collection_meta"
                "(lb_number, personal_rating, listen_count, last_listened, tags)"
                " VALUES(?,?,?,?,?)",
                (_new, *meta),
            )
        # Explicit old-meta delete keeps this correct regardless of whether the
        # ON DELETE CASCADE fires (PRAGMA foreign_keys may be off).
        c.execute("DELETE FROM collection_meta WHERE lb_number=?", (_old,))
        c.execute("DELETE FROM my_collection WHERE lb_number=?", (_old,))

    get_write_queue().execute(_run)


def set_lbdir_verified(disk_path: str, db_path=None) -> bool:
    """Stamp lbdir_verified_at = now for the my_collection row with the given disk_path.

    Args:
        disk_path: Absolute folder path (must match my_collection.disk_path).

    Returns:
        True if a row was updated, False if disk_path was not found in the collection.
    """
    _dp = disk_path

    def _run(c):
        cur = c.execute(
            "UPDATE my_collection SET lbdir_verified_at=datetime('now') WHERE disk_path=?",
            (_dp,)
        )
        return cur.rowcount

    rows_updated = get_write_queue().execute(_run)
    return bool(rows_updated)


def get_missing_from_collection(db_path=None):
    """Return ``entries`` rows the user does not own, as the Collection screen's
    "Missing LBs" list.

    Rows whose ``lb_master`` status is ``'nonexistent'`` are excluded — the LB
    number was allocated but no release ever existed, so it is not a gap the
    user can fill. ``'missing'`` (the tape exists, the LB page is gone) stays
    listed. Mirrors the same exclusion in ``gap_analysis``, ``timeline`` and
    ``backend.lb_coverage._HELD_EXCLUDED_STATUSES``.

    ``entries.status`` is deliberately *not* filtered: private entries (whose
    metadata is stripped from public master snapshots) and entries with no
    scraped metadata are still real, unfilled gaps, and the screen's
    public/private chips need the private ones to exist.

    Args:
        db_path: Optional database path override.

    Returns:
        List of row dicts (lb_number, date_str, location, rating, description,
        lb_status), ordered by LB number.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT e.lb_number, e.date_str, e.location, e.rating, e.description,
                   lm.lb_status
            FROM entries e
            LEFT JOIN my_collection c ON e.lb_number = c.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE c.lb_number IS NULL
              AND (lm.lb_status IS NULL OR lm.lb_status != 'nonexistent')
              AND NOT EXISTS (
                  SELECT 1 FROM lb_alias la
                  JOIN my_collection mc ON la.canonical_lb = mc.lb_number
                  WHERE la.alias_lb = e.lb_number
              )
              AND NOT EXISTS (
                  SELECT 1 FROM lb_alias la
                  JOIN my_collection mc ON la.alias_lb = mc.lb_number
                  WHERE la.canonical_lb = e.lb_number
              )
            ORDER BY e.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def get_owned_lb_numbers(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT lb_number FROM my_collection").fetchall()
    return [r[0] for r in rows]


# ── FEAT-03: Per-Entry Personal Metadata ─────────────────────────────────────

def get_collection_meta(lb_number: int, db_path=None) -> dict:
    """Return personal metadata for a collection entry, with defaults if absent."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM collection_meta WHERE lb_number=?", (lb_number,)
        ).fetchone()
    return dict(row) if row else {
        "lb_number": lb_number, "personal_rating": None,
        "listen_count": 0, "last_listened": None, "tags": None,
    }


def set_collection_meta(lb_number: int, fields: dict, db_path=None) -> None:
    """Upsert personal metadata. Accepted keys: personal_rating, listen_count, last_listened, tags."""
    allowed = {"personal_rating", "listen_count", "last_listened", "tags"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    set_clause = ", ".join(f"{k}=?" for k in clean)
    _lb = lb_number
    _params = list(clean.values()) + [lb_number]
    _sql = f"UPDATE collection_meta SET {set_clause} WHERE lb_number=?"

    def _run(c):
        c.execute(
            "INSERT INTO collection_meta(lb_number) VALUES(?) ON CONFLICT(lb_number) DO NOTHING",
            (_lb,)
        )
        c.execute(_sql, _params)

    get_write_queue().execute(_run)


def increment_listen_count(lb_number: int, db_path=None) -> None:
    """Increment listen count and update last_listened timestamp."""
    from datetime import UTC, datetime
    _lb = lb_number
    _ts = datetime.now(UTC).isoformat()
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO collection_meta(lb_number, listen_count, last_listened) "
            "VALUES(?, 1, ?) ON CONFLICT(lb_number) DO UPDATE SET "
            "listen_count=listen_count+1, last_listened=excluded.last_listened",
            (_lb, _ts)
        )
    )


# ── FEAT-04: Wishlist ─────────────────────────────────────────────────────────

def get_wishlist(db_path=None) -> list:
    """Return all wishlist items joined with entry metadata."""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT w.id, w.lb_number, w.added_at, w.priority, w.notes,
                   e.date_str, e.location, e.rating, e.description
            FROM my_wishlist w
            LEFT JOIN entries e ON e.lb_number = w.lb_number
            ORDER BY w.priority DESC, w.lb_number
        """).fetchall()
    return [dict(r) for r in rows]


def add_to_wishlist(lb_number: int, priority: int = 3, notes: str = None, db_path=None) -> int:
    """Add an entry to the wishlist. Returns 1 if inserted, 0 if already present."""
    _lb, _p, _n = lb_number, priority, notes

    def _run(c):
        c.execute(
            "INSERT OR IGNORE INTO my_wishlist(lb_number, priority, notes) VALUES(?,?,?)",
            (_lb, _p, _n)
        )
        return c.execute("SELECT changes()").fetchone()[0]

    return get_write_queue().execute(_run)


def remove_from_wishlist(lb_number: int, db_path=None) -> None:
    """Remove an entry from the wishlist."""
    _lb = lb_number
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM my_wishlist WHERE lb_number=?", (_lb,))
    )


def update_wishlist(lb_number: int, fields: dict, db_path=None) -> None:
    """Update priority and/or notes on a wishlist entry.

    Args:
        lb_number: LB number to update.
        fields: Dict with keys 'priority' (int 1-5) and/or 'notes' (str).
    """
    allowed = {"priority", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    _params = list(updates.values()) + [lb_number]
    _sql = f"UPDATE my_wishlist SET {set_clause} WHERE lb_number=?"
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


def get_xref_lb_numbers(db_path=None) -> list:
    """Return distinct lb_numbers that have at least one xref checksum (xref > 0)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lb_number FROM checksums WHERE xref > 0 ORDER BY lb_number"
        ).fetchall()
    return [r[0] for r in rows]


def get_xref_map(db_path=None) -> dict:
    """Return {lb_number: sorted list of distinct xref values} for entries with xref > 0."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lb_number, xref FROM checksums WHERE xref > 0 ORDER BY lb_number, xref"
        ).fetchall()
    result: dict = {}
    for lb, xref_val in rows:
        result.setdefault(lb, []).append(xref_val)
    return result


# ── FEAT-05: Duplicate Concert Detector ──────────────────────────────────────

def get_collection_duplicates(db_path=None) -> list:
    """Find date+location combos where the user owns more than one LB entry.

    Returns a list of groups, each with keys: date_str, location, owned, unowned.
    owned/unowned are lists of dicts with lb_number, rating, description.
    """
    with get_connection(db_path) as conn:
        dupes = conn.execute("""
            SELECT e.date_str, e.location, COUNT(*) as cnt
            FROM entries e
            JOIN my_collection c ON c.lb_number = e.lb_number
            WHERE e.date_str IS NOT NULL AND e.date_str != ''
              AND e.location IS NOT NULL AND e.location != ''
            GROUP BY e.date_str, e.location
            HAVING cnt > 1
            ORDER BY e.date_str
        """).fetchall()

        # One pass over all members of every duplicate group (instead of a
        # per-group query — that N+1 made this call take ~3.5 s on 3,200 groups).
        members = conn.execute("""
            SELECT e.date_str, e.location, e.lb_number, e.rating, e.description,
                   (CASE WHEN c.lb_number IS NOT NULL THEN 1 ELSE 0 END) as owned
            FROM entries e
            LEFT JOIN my_collection c ON c.lb_number = e.lb_number
            WHERE (e.date_str, e.location) IN (
                SELECT e2.date_str, e2.location
                FROM entries e2
                JOIN my_collection c2 ON c2.lb_number = e2.lb_number
                WHERE e2.date_str IS NOT NULL AND e2.date_str != ''
                  AND e2.location IS NOT NULL AND e2.location != ''
                GROUP BY e2.date_str, e2.location
                HAVING COUNT(*) > 1
            )
            ORDER BY owned DESC, e.lb_number
        """).fetchall()

        by_group: dict[tuple, dict] = {}
        for r in members:
            key = (r["date_str"], r["location"])
            grp = by_group.setdefault(key, {"owned": [], "unowned": []})
            entry = {"lb_number": r["lb_number"], "rating": r["rating"],
                     "description": r["description"]}
            grp["owned" if r["owned"] else "unowned"].append(entry)

        results = []
        for row in dupes:
            grp = by_group.get((row["date_str"], row["location"]),
                               {"owned": [], "unowned": []})
            results.append({
                "date_str": row["date_str"],
                "location": row["location"],
                "owned": grp["owned"],
                "unowned": grp["unowned"],
            })
    return results


def audit_collection_checksums(db_path=None) -> dict:
    """Cross-check my_collection lb_numbers against the checksums table.

    Returns:
        Dict with keys:
            total (int): total entries in my_collection.
            missing_checksums (int): count with zero checksum rows.
            entries (list[dict]): lb_number, folder_name, disk_path,
                date_str, location, lb_status for each entry with no checksums.
    """
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM my_collection").fetchone()[0]
        rows = conn.execute("""
            SELECT c.lb_number, c.folder_name, c.disk_path,
                   e.date_str, e.location, lm.lb_status
            FROM my_collection c
            LEFT JOIN entries e ON e.lb_number = c.lb_number
            LEFT JOIN lb_master lm ON lm.lb_number = c.lb_number
            WHERE NOT EXISTS (
                SELECT 1 FROM checksums ch WHERE ch.lb_number = c.lb_number
            )
            ORDER BY c.lb_number
        """).fetchall()
    return {
        "total": total,
        "missing_checksums": len(rows),
        "entries": [dict(r) for r in rows],
    }


# ── FEAT-13: Granular Collection Data Management ──────────────────────────────

def purge_collection(db_path=None) -> None:
    """Delete all rows from collection_meta, integrity_events, and my_collection."""
    def _run(c):
        c.execute("DELETE FROM collection_meta")
        c.execute("DELETE FROM integrity_events")
        c.execute("DELETE FROM my_collection")
    get_write_queue().execute(_run)


def purge_wishlist(db_path=None) -> None:
    """Delete all rows from my_wishlist."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM my_wishlist"))


def purge_collection_meta(db_path=None) -> None:
    """Delete all personal ratings and tags (collection_meta only)."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM collection_meta"))


def log_integrity_event(lb_number: int, disk_path: str, event_type: str, detail: str,
                         mount_id: int | None = None, db_path=None) -> None:
    """Insert a watchdog filesystem or integrity-scan event into integrity_events."""
    get_write_queue().execute(
        lambda c: c.execute(
            "INSERT INTO integrity_events(lb_number, disk_path, event_type, detail, mount_id) "
            "VALUES(?,?,?,?,?)",
            (lb_number, disk_path, event_type, detail, mount_id),
        )
    )


def get_integrity_events(unacked_only: bool = True, limit: int = 100, db_path=None) -> list:
    """Return integrity events, newest first."""
    where = "WHERE acknowledged=0" if unacked_only else ""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM integrity_events {where} ORDER BY occurred_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def ack_integrity_events(ids: list, db_path=None) -> None:
    """Mark the given integrity_events rows as acknowledged."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE integrity_events SET acknowledged=1 WHERE id IN ({placeholders})",
            list(ids),
        )
    )


def purge_integrity_events(db_path=None) -> None:
    """Delete all watchdog integrity events."""
    get_write_queue().execute(lambda c: c.execute("DELETE FROM integrity_events"))
