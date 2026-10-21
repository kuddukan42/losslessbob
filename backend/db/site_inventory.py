"""Site-crawler scrape sessions + site_inventory (from backend.db, TODO-369 S2)."""

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── Site crawler sessions + inventory ─────────────────────────────────────────

def create_scrape_session(scope: str, start_url: str = "", db_path=None) -> int:
    """Insert a new scrape_sessions row and return its id."""
    _scope, _url = scope, start_url

    def _run(conn) -> int:
        cur = conn.execute(
            "INSERT INTO scrape_sessions(scope, start_url, status) VALUES(?,?,'running')",
            (_scope, _url),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def finish_scrape_session(
    session_id: int,
    status: str = "done",
    pages_fetched: int = 0,
    pages_304: int = 0,
    pages_skipped: int = 0,
    pages_failed: int = 0,
    files_fetched: int = 0,
    notes: str = "",
    db_path=None,
) -> None:
    """Close a scrape session with final counts."""
    _sid = session_id
    _st, _pf, _p304, _ps, _pfail, _ff, _notes = (
        status, pages_fetched, pages_304, pages_skipped,
        pages_failed, files_fetched, notes,
    )
    get_write_queue().execute(
        lambda c: c.execute(
            """UPDATE scrape_sessions
               SET finished_at=CURRENT_TIMESTAMP, status=?,
                   pages_fetched=?, pages_304=?, pages_skipped=?,
                   pages_failed=?, files_fetched=?, notes=?
               WHERE id=?""",
            (_st, _pf, _p304, _ps, _pfail, _ff, _notes, _sid),
        )
    )


def get_scrape_sessions(limit: int = 50, db_path=None) -> list[dict]:
    """Return recent scrape_sessions rows, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_sessions ORDER BY started_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_inventory(url: str, db_path=None, **fields) -> None:
    """Insert or update a site_inventory row for *url*.

    Keyword args map directly to column names.  Only the supplied keys are
    updated on conflict — unsupplied columns are left unchanged.  A value of
    the string ``"CURRENT_TIMESTAMP"`` is emitted as the SQL expression, not
    bound as text.
    """
    _url = url
    _fields = dict(fields)

    def _run(conn) -> None:
        # Ensure row exists first (INSERT OR IGNORE so discovered_at stays)
        conn.execute(
            "INSERT OR IGNORE INTO site_inventory(url) VALUES(?)", (_url,)
        )
        if _fields:
            sql_now = {k for k, v in _fields.items() if v == "CURRENT_TIMESTAMP"}
            set_clause = ", ".join(
                f"{k}=CURRENT_TIMESTAMP" if k in sql_now else f"{k}=?" for k in _fields
            )
            params = [v for k, v in _fields.items() if k not in sql_now]
            conn.execute(
                f"UPDATE site_inventory SET {set_clause} WHERE url=?",
                params + [_url],
            )

    get_write_queue().execute(_run)


def get_inventory_stats(db_path=None) -> dict:
    """Return counts grouped by status plus total discovered."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM site_inventory GROUP BY status"
    ).fetchall()
    stats: dict = {r["status"]: r["n"] for r in rows}
    stats["total"] = sum(stats.values())
    return stats


def get_inventory_page(
    status: str | None = None,
    content_type: str | None = None,
    path_prefix: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db_path=None,
) -> tuple[list[dict], int]:
    """Paginated, filtered site_inventory list. Returns (rows, total)."""
    conditions: list[str] = []
    params: list = []
    if status:
        conditions.append("status=?")
        params.append(status)
    if content_type:
        conditions.append("content_type LIKE ?")
        params.append(f"%{content_type}%")
    if path_prefix:
        conditions.append("relative_path LIKE ?")
        params.append(f"{path_prefix}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    conn = get_connection(db_path)
    total = conn.execute(
        f"SELECT COUNT(*) FROM site_inventory {where}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM site_inventory {where} "
        f"ORDER BY url LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows], total


def get_pending_urls(db_path=None) -> list[dict]:
    """Return all URLs with status pending or failed, with last_modified."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT url, last_modified FROM site_inventory "
            "WHERE status IN ('pending', 'failed') ORDER BY url"
        ).fetchall()
    return [dict(r) for r in rows]


def get_missing_attachment_urls(db_path=None) -> list[str]:
    """Return ``entry_files`` URLs not yet mirrored (``downloaded=0``).

    Used by the site crawler to seed attachment URLs (xref attachments
    included) that no crawled HTML page links to, so the mirror converges
    on every attachment the scraper knows about.

    ``downloaded`` is tri-state: 0 = missing (returned here), 1 = mirrored,
    2 = dead (URL 404s permanently — stale seed from an older page version
    or source-mangled href, BUG-255 — excluded from seeding).

    Args:
        db_path: Override DB path (tests).

    Returns:
        Attachment URLs ordered by URL.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT file_url FROM entry_files WHERE downloaded=0 ORDER BY file_url"
        ).fetchall()
    return [r["file_url"] for r in rows]


def get_downloaded_urls(db_path=None) -> set[str]:
    """Return the set of URLs already downloaded or confirmed not found."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT url FROM site_inventory "
            "WHERE status IN ('downloaded', 'not_found', 'skipped')"
        ).fetchall()
    return {r["url"] for r in rows}


def get_inventory_last_modified(urls: list[str], db_path=None) -> dict[str, str | None]:
    """Return ``{url: last_modified}`` for the given URLs from site_inventory.

    Args:
        urls:    List of absolute URL strings to look up.
        db_path: Optional DB path override.

    Returns:
        Dict mapping each URL to its stored ``Last-Modified`` header value, or
        ``None`` when the row exists but has no ``last_modified`` stored.  URLs
        not present in ``site_inventory`` are omitted from the result.
    """
    if not urls:
        return {}
    placeholders = ",".join("?" * len(urls))
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT url, last_modified FROM site_inventory WHERE url IN ({placeholders})",
            urls,
        ).fetchall()
    return {r["url"]: r["last_modified"] for r in rows}
