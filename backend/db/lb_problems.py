"""lb_problems rows (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── lb_problems ───────────────────────────────────────────────────────────────

def get_lb_problems(lb_number: int | None = None, db_path=None) -> list[dict]:
    """Return lb_problems rows, optionally filtered to a single LB number.

    Args:
        lb_number: When provided, only return rows for that LB number.
        db_path: Optional database path override.

    Returns:
        List of dicts with keys: id, lb_number, notes, added.
    """
    conn = get_connection(db_path)
    if lb_number is not None:
        rows = conn.execute(
            "SELECT id, lb_number, notes, added FROM lb_problems "
            "WHERE lb_number=? ORDER BY added DESC",
            (lb_number,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, lb_number, notes, added FROM lb_problems "
            "ORDER BY lb_number, added DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_lb_problem(lb_number: int, notes: str, added: str | None = None, db_path=None) -> int:
    """Insert an lb_problems row and return the new row id.

    Args:
        lb_number: The LB number this problem applies to.
        notes: Free-text description of the problem.
        added: ISO date string (YYYY-MM-DD); defaults to today.
        db_path: Optional database path override.

    Returns:
        The rowid of the newly-inserted row.
    """
    from datetime import date as _date
    _lb, _n, _d = lb_number, notes, added or _date.today().isoformat()

    def _run(c):
        cur = c.execute(
            "INSERT INTO lb_problems(lb_number, notes, added) VALUES(?,?,?)",
            (_lb, _n, _d),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_lb_problem(problem_id: int, notes: str, db_path=None) -> None:
    """Update the notes field of an lb_problems row by id.

    Args:
        problem_id: The primary key of the row to update.
        notes: Replacement notes text.
        db_path: Optional database path override.
    """
    _id, _n = problem_id, notes
    get_write_queue().execute(
        lambda c: c.execute("UPDATE lb_problems SET notes=? WHERE id=?", (_n, _id))
    )


def delete_lb_problem(problem_id: int, db_path=None) -> None:
    """Delete an lb_problems row by id.

    Args:
        problem_id: The primary key of the row to delete.
        db_path: Optional database path override.
    """
    _id = problem_id
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM lb_problems WHERE id=?", (_id,))
    )
