"""Torrents, forum posts, WTRF downloads, folder lookups, rename history.

Split from backend.db (TODO-369 S2).
"""

import json
import re

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── Torrents ──────────────────────────────────────────────────────────────────

def get_torrents_for_lb(lb_number: int, db_path=None) -> list:
    """Return all torrent records for an LB entry, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM torrents WHERE lb_number=? ORDER BY created_at DESC",
            (lb_number,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_forum_post(lb_number: int, subject: str, topic_url: str,
                   board_id: int | None = None, db_path=None) -> int:
    """Record a successful forum post and return its new row id."""
    _lb, _s, _tu, _bid = lb_number, subject, topic_url, board_id

    def _run(c):
        cur = c.execute(
            "INSERT INTO forum_posts(lb_number, subject, topic_url, board_id) "
            "VALUES (?, ?, ?, ?)",
            (_lb, _s, _tu, _bid),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def get_forum_posts_for_lb(lb_number: int, db_path=None) -> list:
    """Return all forum post records for an LB entry, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM forum_posts WHERE lb_number=? ORDER BY posted_at DESC",
            (lb_number,),
        ).fetchall()
        out = [dict(r, source="local") for r in rows]
        # TODO-135: topics discovered on the WTRF board, not posted via this app.
        # Skip any already covered by a local log row (same topic id in the URL).
        from backend import wtrf_discovery
        local_ids = {
            int(m.group(1)) for r in out
            if (m := wtrf_discovery._TOPIC_ID_RE.search(r.get("topic_url") or ""))
        }
        for s in wtrf_discovery.lookup_for_lb(conn, lb_number):
            if s["topic_id"] in local_ids:
                continue
            out.append({
                "id": -s["topic_id"], "lb_number": lb_number, "subject": s["subject"],
                "topic_url": s["topic_url"], "board_id": s["board_id"],
                "posted_at": s["posted_at"] or "", "source": "wtrf_scrape",
                "poster": s["poster"], "matched_in": s["matched_in"],
            })
    return out


def update_forum_post_subject(topic_url: str, subject: str) -> int:
    """Rewrite the logged subject of every local post for a topic (TODO-136).

    Rows match on the ``topic=<id>`` in their stored URL, so a ``.msgNNNN``
    or ``#msg`` variant of the same topic is updated too.

    Args:
        topic_url: Any link into the edited topic.
        subject: The subject now live on the forum.

    Returns:
        Number of rows updated (0 when the topic was never posted from here).
    """
    m = re.search(r"topic=(\d+)", topic_url or "")
    if not m:
        return 0
    _tid, _s = m.group(1), subject

    def _run(c):
        rows = c.execute(
            "SELECT id, topic_url FROM forum_posts WHERE topic_url LIKE ?",
            (f"%topic={_tid}%",),
        ).fetchall()
        ids = [r[0] for r in rows
               if (mm := re.search(r"topic=(\d+)", r[1] or "")) and mm.group(1) == _tid]
        c.executemany("UPDATE forum_posts SET subject=? WHERE id=?", [(_s, i) for i in ids])
        return len(ids)

    return get_write_queue().execute(_run)


def delete_forum_post(post_id: int, db_path=None) -> None:
    """Delete a forum post record by id."""
    _id = post_id
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM forum_posts WHERE id=?", (_id,))
    )


def add_wtrf_download(
    lb_number: int,
    topic_url: str | None,
    torrent_path: str | None,
    confidence: str,
    signals_json: str,
    status: str,
    error: str | None = None,
    seed_folder: str | None = None,
    db_path=None,
) -> int:
    """Insert a wtrf_downloads row and return its new id.

    Args:
        lb_number: LB entry being fetched.
        topic_url: Matched WTRF topic URL (None if not found).
        torrent_path: Local path of downloaded .torrent (None until downloaded).
        confidence: One of definitive/high/medium/needs_review/ambiguous/not_found.
        signals_json: JSON string of scoring detail dict.
        status: One of pending/downloaded/qbt_added/failed/skipped.
        error: Error message string if status=failed.
        seed_folder: Folder handed to qBittorrent (collection or overlay), if any.
        db_path: Optional DB path override.

    Returns:
        New row id.
    """
    _lb, _tu, _tp, _conf, _sj, _st, _err, _sf = (
        lb_number, topic_url, torrent_path, confidence, signals_json, status,
        error, seed_folder,
    )

    def _run(c):
        cur = c.execute(
            "INSERT INTO wtrf_downloads"
            "(lb_number, topic_url, torrent_path, confidence, signals_json, status,"
            " error, seed_folder)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_lb, _tu, _tp, _conf, _sj, _st, _err, _sf),
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_wtrf_download(download_id: int, fields: dict, db_path=None) -> None:
    """Update one or more columns on a wtrf_downloads row.

    Args:
        download_id: Primary key of the row to update.
        fields: Dict of column→value pairs to set.
        db_path: Optional DB path override.
    """
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [download_id]
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE wtrf_downloads SET {set_clause} WHERE id=?", values
        )
    )


def get_wtrf_downloads(lb_number: int | None = None, db_path=None) -> list[dict]:
    """Return wtrf_downloads rows, optionally filtered by lb_number.

    Args:
        lb_number: If given, return only rows for this LB.
        db_path: Optional DB path override.

    Returns:
        List of row dicts, newest first.
    """
    with get_connection(db_path) as conn:
        if lb_number is not None:
            rows = conn.execute(
                "SELECT * FROM wtrf_downloads WHERE lb_number=? ORDER BY attempted_at DESC",
                (lb_number,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM wtrf_downloads ORDER BY attempted_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_wtrf_pending_lb_numbers(db_path=None) -> list[int]:
    """Return lb_numbers that are public, not in my_collection, and not yet
    successfully fetched (no downloaded/qbt_added row), ordered desc.

    Used by the batch crawl to build the work queue.

    Args:
        db_path: Optional DB path override.

    Returns:
        List of lb_numbers descending.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT lm.lb_number
              FROM lb_master lm
             WHERE lm.lb_status = 'public'
               AND lm.lb_number NOT IN (SELECT lb_number FROM my_collection)
               AND lm.lb_number NOT IN (
                   SELECT lb_number FROM wtrf_downloads
                    WHERE status IN ('downloaded', 'qbt_added')
               )
             ORDER BY lm.lb_number DESC
            """
        ).fetchall()
    return [r[0] for r in rows]


def get_wtrf_rejected_topics(lb_number: int, db_path=None) -> set[str]:
    """Return topic URLs a curator rejected for one LB (row topic + tied candidates).

    Args:
        lb_number: The LB number.
        db_path: Optional DB path override.

    Returns:
        Set of topic URLs the crawler must not offer again for this LB.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT topic_url, signals_json FROM wtrf_downloads "
            "WHERE lb_number = ? AND status = 'rejected'",
            (lb_number,),
        ).fetchall()
    out: set[str] = set()
    for topic_url, signals_json in rows:
        if topic_url:
            out.add(topic_url)
        try:
            out.update(json.loads(signals_json or "{}").get("tied_candidates") or [])
        except (ValueError, AttributeError):
            pass
    return out


def get_wtrf_attempted_topics(db_path=None) -> dict[str, str]:
    """Return the latest attempt status for every WTRF topic already tried.

    The board walk (``backend.wtrf_board``) uses this to resume: a topic that
    has been resolved once — seeded, refused or found to hold no torrent — is
    not fetched again unless the caller asks for a rescan.

    Only the *seeding* paths count. The fetch path (``wtrf_fetch_missing.py``
    and ``/api/wtrf/fetch_torrent``) writes rows for topics it downloaded a
    torrent from without ever asking whether the recording could be seeded, and
    those must not stop the walk from seeding the same post later.

    Args:
        db_path: Optional DB path override.

    Returns:
        Mapping of topic_url to the newest seeding attempt's status.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT topic_url, status
              FROM wtrf_downloads
             WHERE topic_url IS NOT NULL AND topic_url != ''
               AND (seed_folder IS NOT NULL
                    OR signals_json LIKE '%"via": "pasted_link"%'
                    OR signals_json LIKE '%"via": "board_walk"%')
             ORDER BY attempted_at ASC
            """
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_folders_for_lb(lb_number: int, db_path=None) -> list[str]:
    """Return every on-disk folder known to hold an LB number's files.

    Checks ``my_collection.disk_path`` first — the confirmed collection — then
    ``folder_lb_link``, which the pipeline populates for freshly downloaded
    folders that are not filed into the collection yet. Used to point a
    scraped torrent at files that already exist locally.

    Args:
        lb_number: LB number to look up.
        db_path: Optional DB path override.

    Returns:
        Absolute folder paths, collection entries first, de-duplicated.
    """
    paths: list[str] = []
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT disk_path FROM my_collection "
            " WHERE lb_number=? AND disk_path IS NOT NULL AND disk_path <> ''",
            (lb_number,),
        ).fetchall()
        paths.extend(r[0] for r in rows)
        rows = conn.execute(
            "SELECT folder_path FROM folder_lb_link WHERE lb_number=? "
            "ORDER BY linked_at DESC",
            (lb_number,),
        ).fetchall()
        paths.extend(r[0] for r in rows)
    return list(dict.fromkeys(paths))


def get_folders_for_same_date(lb_number: int, db_path=None) -> dict[int, list[str]]:
    """Return on-disk folders of the *other* LB entries sharing a date.

    A tracker's LB attribution can simply be wrong (TODO-348: LB-11813 named
    for audio that is LB-11801; LB-12243 for LB-12242), and ranking only the
    claimed number's folders can never find the right one. Same-date siblings
    are the natural candidate pool: the piece-hash pick then decides by
    content, not by what the tracker said.

    Args:
        lb_number: The LB number the tracker claims.
        db_path: Optional DB path override.

    Returns:
        ``{other lb_number: [folders]}`` for every same-date entry that has at
        least one folder, in the same order :func:`get_folders_for_lb` uses.
        Empty when the claimed entry is unknown or has no parseable date.
    """
    out: dict[int, list[str]] = {}
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT date_str FROM entries WHERE lb_number=?", (lb_number,)
        ).fetchone()
        if not row or not row[0]:
            return out
        siblings = [
            r[0] for r in conn.execute(
                "SELECT lb_number FROM entries WHERE date_str=? AND lb_number<>?"
                " ORDER BY lb_number", (row[0], lb_number),
            ).fetchall()
        ]
    for sibling in siblings:
        folders = get_folders_for_lb(sibling, db_path)
        if folders:
            out[sibling] = folders
    return out


def get_site_file_urls(filenames: list[str], db_path=None) -> dict[str, str]:
    """Map LBF sidecar filenames to their original losslessbob.com URLs.

    ``data/site/files/`` holds the crawl's copies, but HTML files there were
    link-rewritten on save and no longer match the bytes the site served — the
    row's ``local_sha256`` differs from ``body_sha256`` in that case. Re-fetching
    the URL yields the pristine original, which is what a torrent's piece hashes
    were computed over.

    Args:
        filenames: Basenames to look up, e.g. ``LBF-00707-bd1978-11-01.txt``.
        db_path: Optional DB path override.

    Returns:
        {filename: url} for those found in ``site_inventory``.
    """
    if not filenames:
        return {}
    out: dict[str, str] = {}
    with get_connection(db_path) as conn:
        for chunk_start in range(0, len(filenames), 400):
            chunk = filenames[chunk_start:chunk_start + 400]
            rows = conn.execute(
                "SELECT relative_path, url FROM site_inventory "
                " WHERE relative_path IN ({})".format(",".join("?" * len(chunk))),
                [f"files/{n}" for n in chunk],
            ).fetchall()
            for rel, url in rows:
                out[rel.split("/", 1)[-1]] = url
    return out


def get_all_forum_posts(db_path=None) -> list:
    """Return all forum posts across all LB entries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT fp.id, fp.lb_number, fp.subject, fp.topic_url,
                      fp.board_id, fp.posted_at,
                      e.date_str, e.location
               FROM forum_posts fp
               LEFT JOIN entries e ON e.lb_number = fp.lb_number
               ORDER BY fp.posted_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_torrents(db_path=None) -> list:
    """Return all torrent records across all LB entries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT t.id, t.lb_number, t.torrent_path, t.source_folder,
                      t.created_at, t.infohash, t.added_to_qbt, t.added_to_qbt_at,
                      t.qbt_infohash_confirmed, t.last_seen_at, t.excluded_files,
                      e.date_str, e.location
               FROM torrents t
               LEFT JOIN entries e ON e.lb_number = t.lb_number
               ORDER BY t.created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def add_torrent_record(lb_number: int, torrent_path: str, source_folder: str,
                       infohash: str, excluded_files: list | None = None,
                       db_path=None) -> int:
    """Insert a new torrent record. Returns the new row id."""
    import json as _json
    excl = _json.dumps(excluded_files or [])
    _lb, _tp, _sf, _ih, _ex = lb_number, torrent_path, source_folder, infohash, excl

    def _run(c):
        cur = c.execute(
            """INSERT INTO torrents(lb_number, torrent_path, source_folder, infohash, excluded_files)
               VALUES(?,?,?,?,?)""",
            (_lb, _tp, _sf, _ih, _ex)
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_torrent_record(torrent_id: int, fields: dict, db_path=None) -> None:
    """Update fields on a torrents row by id."""
    allowed = {
        "torrent_path", "source_folder", "infohash", "added_to_qbt",
        "added_to_qbt_at", "qbt_infohash_confirmed", "last_seen_at", "excluded_files",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    set_clause = ", ".join(f"{k}=?" for k in clean)
    _sql = f"UPDATE torrents SET {set_clause} WHERE id=?"
    _params = list(clean.values()) + [torrent_id]
    get_write_queue().execute(lambda c: c.execute(_sql, _params))


def delete_torrent_record(torrent_id: int, db_path=None) -> None:
    """Delete a torrents row by id."""
    get_write_queue().execute(
        lambda c: c.execute("DELETE FROM torrents WHERE id=?", (torrent_id,))
    )


def clear_superseded_torrent_paths(lb_number: int, new_id: int, new_path: str,
                                   db_path=None) -> None:
    """Null out torrent_path on older records for the same LB that share new_path.

    Called after a regen so stale records no longer falsely report
    torrent_file_exists=True when the new file was created at the same path as
    a previously-deleted one.
    """
    def _run(c: object) -> None:
        c.execute(  # type: ignore[attr-defined]
            "UPDATE torrents SET torrent_path=NULL WHERE lb_number=? AND id!=? AND torrent_path=?",
            (lb_number, new_id, new_path),
        )
    get_write_queue().execute(_run)


# ── Rename History ─────────────────────────────────────────────────────────────

def add_rename_history(lb_number: int | None, old_path: str, new_path: str,
                       source: str, notes: str = "", db_path=None) -> None:
    """Insert a rename_history row with a local-time timestamp."""
    from datetime import datetime as _dt
    _lb, _op, _np, _src, _nt = lb_number, old_path, new_path, source, notes
    _ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    get_write_queue().execute(
        lambda c: c.execute(
            """INSERT INTO rename_history(lb_number, old_path, new_path, source, notes, renamed_at)
               VALUES(?,?,?,?,?,?)""",
            (_lb, _op, _np, _src, _nt, _ts)
        )
    )
