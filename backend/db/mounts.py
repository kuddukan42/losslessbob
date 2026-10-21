"""Collection mounts and per-year routes (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── Collection Mounts ──────────────────────────────────────────────────────────

def get_collection_mounts(db_path=None) -> list[dict]:
    """Return all mounts; online status is checked by the caller via filer._path_reachable."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, label, root_path, notes, created_at "
            "FROM collection_mounts ORDER BY label"
        ).fetchall()
    return [dict(r) for r in rows]


def add_collection_mount(label: str, root_path: str, notes: str | None = None,
                         db_path=None) -> int:
    """Insert a new mount. Returns the new row id."""
    _l, _r, _n = label, root_path, notes

    def _run(c):
        c.execute(
            "INSERT INTO collection_mounts(label, root_path, notes) VALUES(?,?,?)",
            (_l, _r, _n),
        )
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    return get_write_queue().execute(_run)


def update_collection_mount(mount_id: int, fields: dict, db_path=None) -> None:
    """Update allowed fields on a mount row."""
    allowed = {"label", "root_path", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [mount_id]
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE collection_mounts SET {set_clause} WHERE id=?", params
        )
    )


def delete_collection_mount(mount_id: int, db_path=None) -> dict:
    """Delete a mount. Returns {ok, error} — fails if any routes reference it."""
    _id = mount_id

    def _run(c):
        in_use = c.execute(
            "SELECT COUNT(*) FROM collection_routes WHERE mount_id=?", (_id,)
        ).fetchone()[0]
        if in_use:
            return {"ok": False, "error": f"Mount is referenced by {in_use} route(s)"}
        c.execute("DELETE FROM collection_mounts WHERE id=?", (_id,))
        return {"ok": True, "error": None}

    return get_write_queue().execute(_run)


# ── Collection Routes ──────────────────────────────────────────────────────────

def get_collection_routes(db_path=None) -> list[dict]:
    """Return all routes joined with mount label and root_path, ordered by year."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT r.year, r.mount_id, r.sub_path,
                      m.label AS mount_label, m.root_path
               FROM collection_routes r
               JOIN collection_mounts m ON m.id = r.mount_id
               ORDER BY r.year"""
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_collection_routes(
    year_from: int,
    year_to: int,
    mount_id: int,
    sub_path: str,
    db_path=None,
) -> int:
    """Insert or replace one route row per year in [year_from, year_to] inclusive.

    Returns the number of rows written.
    """
    years = list(range(year_from, year_to + 1))
    _mid, _sp = mount_id, sub_path

    def _run(c):
        c.executemany(
            "INSERT OR REPLACE INTO collection_routes(year, mount_id, sub_path) VALUES(?,?,?)",
            [(y, _mid, _sp) for y in years],
        )
        return len(years)

    return get_write_queue().execute(_run)


def delete_collection_route(year: int, db_path=None) -> None:
    """Remove the route for a single year."""
    _y = year
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM collection_routes WHERE year=?", (_y,))
    )
