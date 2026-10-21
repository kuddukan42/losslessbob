"""Bootleg-CD catalog (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.paths import SITE_BASE_URL

# ── Bootleg-CD Catalog ────────────────────────────────────────────────────────

_BOOTLEG_SOURCE_URL = SITE_BASE_URL + "/detail/LB-bootleg-by-title.html"


def get_bootlegs_for_lb(lb_number: int, db_path=None) -> list[dict]:
    """Return all bootleg_titles rows for one LB, ordered by date_iso NULLS LAST."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bootleg_titles WHERE lb_number=? "
            "ORDER BY date_iso NULLS LAST, title COLLATE NOCASE",
            (lb_number,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_bootleg_stats(db_path=None) -> dict:
    """Return summary counts and most-recent scrape info."""
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM bootleg_titles").fetchone()[0]
        last_scrape = conn.execute(
            "SELECT scraped_at, status, rows_added, rows_changed, rows_removed "
            "FROM bootleg_scrapes ORDER BY scraped_at DESC LIMIT 1"
        ).fetchone()
    result: dict = {"total": total}
    if last_scrape:
        result["last_scraped_at"] = last_scrape["scraped_at"]
        result["last_status"] = last_scrape["status"]
    return result


def get_bootlegs(
    q: str = "",
    year_min: int | None = None,
    year_max: int | None = None,
    cd_min: int | None = None,
    cd_max: int | None = None,
    lb_status: str | None = None,
    owned: bool | None = None,
    has_lbbcd: bool | None = None,
    sort_col: str = "lb_number",
    sort_dir: str = "ASC",
    limit: int = 200,
    offset: int = 0,
    db_path=None,
) -> tuple[list[dict], int]:
    """Paginated, filtered bootleg list joined with lb_master and my_collection.

    Returns (rows, total_count).
    """
    _SORT_COLS = {
        "lb_number": "bt.lb_number",
        "title":     "bt.title COLLATE NOCASE",
        "date_iso":  "bt.date_iso NULLS LAST",
        "year":      "bt.year NULLS LAST",
        "location":  "bt.location COLLATE NOCASE",
        "cd_count":  "bt.cd_count",
        "lbbcd_id":  "bt.lbbcd_id NULLS LAST",
        "lb_status": "lm.lb_status",
    }
    order_expr = _SORT_COLS.get(sort_col, "bt.lb_number")
    direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"

    conditions: list[str] = []
    params: list = []

    if q:
        conditions.append("(bt.title LIKE ? OR bt.location LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    if year_min is not None:
        conditions.append("bt.year >= ?")
        params.append(year_min)
    if year_max is not None:
        conditions.append("bt.year <= ?")
        params.append(year_max)
    if cd_min is not None:
        conditions.append("bt.cd_count >= ?")
        params.append(cd_min)
    if cd_max is not None:
        conditions.append("bt.cd_count <= ?")
        params.append(cd_max)
    if lb_status:
        conditions.append("lm.lb_status = ?")
        params.append(lb_status)
    if owned is True:
        conditions.append("mc.lb_number IS NOT NULL")
    elif owned is False:
        conditions.append("mc.lb_number IS NULL")
    if has_lbbcd is True:
        conditions.append("bt.lbbcd_id IS NOT NULL")
    elif has_lbbcd is False:
        conditions.append("bt.lbbcd_id IS NULL")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    base_sql = f"""
        FROM bootleg_titles bt
        LEFT JOIN lb_master lm ON lm.lb_number = bt.lb_number
        LEFT JOIN my_collection mc ON mc.lb_number = bt.lb_number
        {where}
    """
    conn = get_connection(db_path)
    total = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT bt.*, lm.lb_status, mc.lb_number IS NOT NULL AS owned {base_sql} "
        f"ORDER BY {order_expr} {direction} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def get_bootleg_scrape_history(limit: int = 20, db_path=None) -> list[dict]:
    """Return recent bootleg_scrapes rows, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bootleg_scrapes ORDER BY scraped_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
