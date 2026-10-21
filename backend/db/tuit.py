"""TUIT tracker mirror tables (from backend.db, TODO-369 S2)."""

import re

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── TUIT tracker mirror ───────────────────────────────────────────────────────

TUIT_RECORDING_COLUMNS = (
    "rec_id", "show_id", "lb_number", "detail_url", "title", "eyebrow",
    "headline", "date_str", "venue", "location", "tour", "source_type",
    "source_label", "format", "quality", "quality_slug", "info_hash",
    "size_label", "size_bytes", "n_files", "n_sources", "seeders", "leechers",
    "snatched", "freeleech", "lb_verified", "taper", "uploader", "uploader_url",
    "uploaded_label", "added_at", "lineage", "lineage_json", "info_text",
    "setlist_json", "files_json", "siblings_json", "spectrogram_url",
    "preview_url", "torrent_url",
)


def upsert_tuit_recording(row: dict, db_path=None) -> int:
    """Insert or refresh one tuit_recordings row, keyed by rec_id.

    Unknown keys in ``row`` are ignored, so a scraper dict can be passed
    straight through. ``first_seen_at`` is preserved across refreshes;
    ``last_seen_at`` is always bumped.

    Args:
        row: Column→value mapping; must contain ``rec_id``.
        db_path: Optional DB path override.

    Returns:
        The rec_id written.

    Raises:
        ValueError: If ``rec_id`` is missing.
    """
    rec_id = row.get("rec_id")
    if rec_id is None:
        raise ValueError("upsert_tuit_recording requires rec_id")

    data = {k: row[k] for k in TUIT_RECORDING_COLUMNS if k in row}
    for flag in ("freeleech", "lb_verified"):
        if flag in data:
            data[flag] = int(bool(data[flag]))

    cols = list(data)
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "rec_id")
    values = [data[c] for c in cols]

    def _run(c):
        c.execute(
            f"INSERT INTO tuit_recordings ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(rec_id) DO UPDATE SET {updates}, "
            f"last_seen_at=CURRENT_TIMESTAMP",
            values,
        )
        return rec_id

    return get_write_queue().execute(_run)


def get_tuit_recording(rec_id: int, db_path=None) -> dict | None:
    """Return one tuit_recordings row by site recording id, or None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tuit_recordings WHERE rec_id=?", (rec_id,)
        ).fetchone()
    return dict(row) if row else None


def add_tuit_download(
    rec_id: int,
    lb_number: int | None,
    torrent_path: str | None,
    status: str,
    seed_folder: str | None = None,
    error: str | None = None,
    db_path=None,
) -> int:
    """Insert a tuit_downloads row and return its new id.

    Args:
        rec_id: Site recording id being fetched.
        lb_number: LB number the recording claims, if any.
        torrent_path: Local path of the downloaded .torrent, if any.
        status: pending/downloaded/qbt_added/no_local_files/failed.
        seed_folder: Collection folder the torrent was pointed at, if any.
        error: Error message when status is 'failed'.
        db_path: Optional DB path override.

    Returns:
        New row id.
    """
    _args = (rec_id, lb_number, torrent_path, seed_folder, status, error)

    def _run(c):
        cur = c.execute(
            "INSERT INTO tuit_downloads"
            "(rec_id, lb_number, torrent_path, seed_folder, status, error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            _args,
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_tuit_download(download_id: int, fields: dict, db_path=None) -> None:
    """Update one or more columns on a tuit_downloads row.

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
            f"UPDATE tuit_downloads SET {set_clause} WHERE id=?", values
        )
    )


def get_tuit_downloads(rec_id: int | None = None, db_path=None) -> list[dict]:
    """Return tuit_downloads rows, newest first, optionally filtered by rec_id."""
    with get_connection(db_path) as conn:
        if rec_id is not None:
            rows = conn.execute(
                "SELECT * FROM tuit_downloads WHERE rec_id=? "
                "ORDER BY attempted_at DESC",
                (rec_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tuit_downloads ORDER BY attempted_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_tuit_download_rec_ids(db_path=None) -> set[int]:
    """Return the set of rec_ids with at least one tuit_downloads attempt."""
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT rec_id FROM tuit_downloads").fetchall()
    return {r["rec_id"] for r in rows}


def add_tuit_upload(
    lb_number: int,
    status: str,
    info_hash: str | None = None,
    torrent_path: str | None = None,
    show_id: int | None = None,
    source_folder: str | None = None,
    payload_json: str | None = None,
    error: str | None = None,
    db_path=None,
) -> int:
    """Insert a tuit_uploads row and return its new id.

    Args:
        lb_number: LB number being posted to the tracker.
        status: prepared/uploaded/seeded/rejected/failed.
        info_hash: Infohash of the generated .torrent, when one was built.
        torrent_path: Local path of that .torrent.
        show_id: Site show id the upload was attached to, if resolved.
        source_folder: Collection (or overlay) folder the torrent covers.
        payload_json: JSON dump of the exact form fields composed.
        error: Error message when status is 'failed' or 'rejected'.
        db_path: Optional DB path override.

    Returns:
        New row id.
    """
    _args = (lb_number, info_hash, torrent_path, show_id, source_folder,
             payload_json, status, error)

    def _run(c):
        cur = c.execute(
            "INSERT INTO tuit_uploads"
            "(lb_number, info_hash, torrent_path, show_id, source_folder,"
            " payload_json, status, error)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _args,
        )
        return cur.lastrowid

    return get_write_queue().execute(_run)


def update_tuit_upload(upload_id: int, fields: dict, db_path=None) -> None:
    """Update one or more columns on a tuit_uploads row.

    Args:
        upload_id: Primary key of the row to update.
        fields: Dict of column→value pairs to set.
        db_path: Optional DB path override.
    """
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [upload_id]
    get_write_queue().execute(
        lambda c: c.execute(
            f"UPDATE tuit_uploads SET {set_clause} WHERE id=?", values
        )
    )


def get_tuit_uploads(lb_number: int | None = None, db_path=None) -> list[dict]:
    """Return tuit_uploads rows, newest first, optionally filtered by LB number."""
    with get_connection(db_path) as conn:
        if lb_number is not None:
            rows = conn.execute(
                "SELECT * FROM tuit_uploads WHERE lb_number=? "
                "ORDER BY attempted_at DESC",
                (lb_number,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tuit_uploads ORDER BY attempted_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def tuit_has_recording(
    lb_number: int | None = None, info_hash: str = "", db_path=None
) -> dict | None:
    """Return the tracker row already carrying this LB number or infohash.

    The duplicate guard for uploading: TUIT is scraped into ``tuit_recordings``
    already, so a recording we are about to post can be checked against what
    the tracker holds without another request. An infohash match is exact; an
    LB-number match only means *a* version of that entry circulates, which is
    still worth showing a curator before a second copy goes up.

    Args:
        lb_number: LB number to look for.
        info_hash: Infohash to look for; matched case-insensitively.
        db_path: Optional DB path override.

    Returns:
        The matching ``tuit_recordings`` row as a dict (infohash match wins),
        or None when the tracker has neither.
    """
    with get_connection(db_path) as conn:
        if info_hash:
            row = conn.execute(
                "SELECT * FROM tuit_recordings WHERE lower(info_hash)=lower(?)",
                (info_hash,),
            ).fetchone()
            if row:
                return dict(row)
        if lb_number is not None:
            row = conn.execute(
                "SELECT * FROM tuit_recordings WHERE lb_number=? "
                "ORDER BY rec_id LIMIT 1",
                (lb_number,),
            ).fetchone()
            if row:
                return dict(row)
    return None


TUIT_SHOW_COLUMNS = (
    "date_str", "venue", "location", "tour", "row_url", "rec_id", "show_id",
    "circulating", "in_collection", "has_sbd", "has_aud", "seeders",
)

TUIT_VENUE_COLUMNS = (
    "venue", "city", "country", "year_first", "year_last", "n_shows",
    "venue_url", "source",
)


def _upsert_tuit_row(
    table: str, columns: tuple, key: tuple, flags: tuple, rows: list[dict],
    required: tuple = (),
) -> int:
    """Upsert scraped TUIT rows into ``table``, keyed by ``key``.

    Args:
        table: Target table name (trusted, module-internal).
        columns: Columns to accept from each row dict.
        key: The table's UNIQUE columns, used as the conflict target.
        flags: Columns coerced to 0/1.
        rows: Scraper dicts; unknown keys are ignored.
        required: Columns that must be non-empty for a row to be written;
            defaults to every key column. A key column may legitimately be
            blank (a venue with no recorded city), so the two differ.

    Returns:
        Number of rows written.
    """
    written = 0

    def _run(conn):
        nonlocal written
        for row in rows:
            data = {k: row[k] for k in columns if k in row}
            if any(not data.get(k) for k in (required or key)):
                continue
            for flag in flags:
                if flag in data:
                    data[flag] = int(bool(data[flag]))
            cols = list(data)
            updates = [f"{c}=excluded.{c}" for c in cols if c not in key]
            updates.append("last_seen_at=CURRENT_TIMESTAMP")
            conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)}) "
                f"ON CONFLICT({', '.join(key)}) DO UPDATE SET "
                f"{', '.join(updates)}",
                [data[c] for c in cols],
            )
            written += 1
        return written

    return get_write_queue().execute(_run)


def upsert_tuit_shows(rows: list[dict], db_path=None) -> int:
    """Insert or refresh ``tuit_shows`` rows, keyed by (date_str, venue).

    Args:
        rows: Dicts from :class:`backend.tuit_scraper.TourShow.as_dict`.
        db_path: Unused; writes go through the shared write queue.

    Returns:
        Number of rows written.
    """
    return _upsert_tuit_row(
        "tuit_shows", TUIT_SHOW_COLUMNS, ("date_str", "venue"),
        ("circulating", "in_collection", "has_sbd", "has_aud"), rows,
    )


def upsert_tuit_venues(rows: list[dict], db_path=None) -> int:
    """Insert or refresh ``tuit_venues`` rows, keyed by (venue, city, country).

    ``city`` and ``country`` are coerced to '' rather than NULL so the UNIQUE
    constraint actually fires — SQLite treats NULLs as distinct.

    Args:
        rows: Dicts from :class:`backend.tuit_scraper.TuitVenue.as_dict`.
        db_path: Unused; writes go through the shared write queue.

    Returns:
        Number of rows written.
    """
    normalised = []
    for row in rows:
        row = dict(row)
        row["city"] = row.get("city") or ""
        row["country"] = row.get("country") or ""
        normalised.append(row)
    return _upsert_tuit_row(
        "tuit_venues", TUIT_VENUE_COLUMNS, ("venue", "city", "country"),
        (), normalised, required=("venue",),
    )


TUIT_SONG_COLUMNS = (
    "song", "song_url", "n_performances", "n_listed", "year_first",
    "year_last", "scraped_at",
)

TUIT_SONG_PERF_COLUMNS = (
    "song", "date_str", "venue_text", "show_id", "n_sources", "is_encore",
    "note",
)


def upsert_tuit_songs(rows: list[dict], db_path=None) -> int:
    """Insert or refresh ``tuit_songs`` rows, keyed by song title.

    Args:
        rows: Dicts from :class:`backend.tuit_scraper.TuitSong.as_dict`.
        db_path: Unused; writes go through the shared write queue.

    Returns:
        Number of rows written.
    """
    return _upsert_tuit_row(
        "tuit_songs", TUIT_SONG_COLUMNS, ("song",), (), rows,
    )


def upsert_tuit_song_performances(rows: list[dict], db_path=None) -> int:
    """Insert or refresh ``tuit_song_performances`` rows.

    Keyed by (song, date_str, venue_text, show_id). The show id is needed
    because a date can carry two shows at the same venue — an afternoon and an
    evening — whose rendered ``venue_text`` is identical. It is coerced to 0
    rather than left NULL so the UNIQUE constraint actually fires.

    Args:
        rows: Dicts from
            :class:`backend.tuit_scraper.TuitSongPerformance.as_dict`.
        db_path: Unused; writes go through the shared write queue.

    Returns:
        Number of rows written.
    """
    normalised = []
    for row in rows:
        row = dict(row)
        row["venue_text"] = row.get("venue_text") or ""
        row["show_id"] = row.get("show_id") or 0
        normalised.append(row)
    return _upsert_tuit_row(
        "tuit_song_performances", TUIT_SONG_PERF_COLUMNS,
        ("song", "date_str", "venue_text", "show_id"), ("is_encore",),
        normalised, required=("song", "date_str"),
    )


def get_tuit_songs(song: str = "", db_path=None) -> list[dict]:
    """Return ``tuit_songs`` rows, most-performed first.

    Args:
        song: If given, only this exact title.
        db_path: Optional DB path override.

    Returns:
        List of row dicts.
    """
    sql = "SELECT * FROM tuit_songs"
    params: list = []
    if song:
        sql += " WHERE song=?"
        params.append(song)
    sql += " ORDER BY n_performances DESC, song"
    with get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_tuit_scraped_songs(db_path=None) -> set[str]:
    """Return the titles whose own ``/song`` page has already been read.

    Used to resume an interrupted songbook sweep — it runs to ~850 requests, so
    a restart must not re-fetch what already landed.

    Args:
        db_path: Optional DB path override.

    Returns:
        Set of song titles with a non-null ``scraped_at``.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT song FROM tuit_songs WHERE scraped_at IS NOT NULL"
        ).fetchall()
    return {r["song"] for r in rows}


def get_tuit_song_performances(
    song: str = "", date_str: str = "", db_path=None
) -> list[dict]:
    """Return ``tuit_song_performances`` rows, oldest first.

    Args:
        song: If given, only this song.
        date_str: If given, only this ISO date — i.e. one night's setlist.
        db_path: Optional DB path override.

    Returns:
        List of row dicts.
    """
    sql = "SELECT * FROM tuit_song_performances"
    clauses: list[str] = []
    params: list = []
    if song:
        clauses.append("song=?")
        params.append(song)
    if date_str:
        clauses.append("date_str=?")
        params.append(date_str)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date_str, song"
    with get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def backfill_tuit_venues_from_shows(db_path=None) -> int:
    """Add venues seen in ``tuit_shows`` that the /venue register never listed.

    TUIT's venue listing pages an unstable sort (``n_shows`` descending with no
    tiebreak), so a full sweep both repeats rows across page boundaries and
    silently drops others — a 2,744-venue register yields ~1,900 distinct rows
    and misses ~700 real venues. ``tuit_shows`` is complete by construction, so
    the missing venues are recovered from it: the ``· Afternoon``/``· Evening``
    suffix is stripped, and ``location`` is split into city (everything before
    the last comma) and country (after it). Register rows are never overwritten.

    Args:
        db_path: Optional DB path override.

    Returns:
        Number of venues added.
    """
    with get_connection(db_path) as conn:
        known = {
            _normalise_venue_key(r["venue"])
            for r in conn.execute("SELECT venue FROM tuit_venues").fetchall()
        }
        rows = conn.execute(
            "SELECT venue, location, date_str FROM tuit_shows"
        ).fetchall()

    derived: dict[str, dict] = {}
    for row in rows:
        venue = re.sub(r"\s*·.*$", "", row["venue"] or "").strip()
        key = _normalise_venue_key(venue)
        if not key or key in known:
            continue
        parts = [p.strip() for p in (row["location"] or "").split(",") if p.strip()]
        country = parts[-1] if parts else ""
        city = ", ".join(parts[:-1])
        year = _int_or_none_str(row["date_str"][:4])
        entry = derived.setdefault(key, {
            "venue": venue, "city": city, "country": country,
            "year_first": year, "year_last": year, "n_shows": 0,
            "source": "shows",
        })
        entry["n_shows"] += 1
        if year:
            entry["year_first"] = min(entry["year_first"] or year, year)
            entry["year_last"] = max(entry["year_last"] or year, year)

    if not derived:
        return 0
    return upsert_tuit_venues(list(derived.values()))


def _normalise_venue_key(venue: str) -> str:
    """Return a venue name folded to lowercase alphanumerics for matching."""
    return re.sub(r"[^a-z0-9]+", " ", (venue or "").lower()).strip()


def _int_or_none_str(value: str) -> int | None:
    """Return ``value`` as an int, or None when it is not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_tuit_shows(
    date_str: str = "", tour: str = "", circulating: bool | None = None,
    db_path=None,
) -> list[dict]:
    """Return ``tuit_shows`` rows, oldest date first.

    Args:
        date_str: If given, only this ISO date.
        tour: If given, only this tour name.
        circulating: If given, filter on whether TUIT has a tape.
        db_path: Optional DB path override.

    Returns:
        List of row dicts.
    """
    sql = "SELECT * FROM tuit_shows"
    clauses: list[str] = []
    params: list = []
    if date_str:
        clauses.append("date_str=?")
        params.append(date_str)
    if tour:
        clauses.append("tour=?")
        params.append(tour)
    if circulating is not None:
        clauses.append("circulating=?")
        params.append(int(circulating))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date_str, venue"
    with get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_tuit_venues(venue: str = "", db_path=None) -> list[dict]:
    """Return ``tuit_venues`` rows, busiest venue first.

    Args:
        venue: If given, only rows with this exact venue name.
        db_path: Optional DB path override.

    Returns:
        List of row dicts.
    """
    sql = "SELECT * FROM tuit_venues"
    params: list = []
    if venue:
        sql += " WHERE venue=?"
        params.append(venue)
    sql += " ORDER BY n_shows DESC, venue"
    with get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# Statuses a TUIT sync should try again. 'qbt_added' is done; 'not_seeded' is
# usually structural (no LB number, an overlay that will not reach 100%) and is
# only retried on request. 'downloaded' means the torrent was saved but never
# reached qBittorrent — the exact state a run leaves behind when the client dies
# mid-sync — and 'failed' covers a transient refusal.
TUIT_RETRY_STATUSES = ("downloaded", "failed")


def get_tuit_retry_rec_ids(
    include_unseeded: bool = False, limit: int | None = None,
    max_attempts: int = 3, db_path=None
) -> list[int]:
    """Return rec_ids whose most recent sync attempt stopped short of seeding.

    Without this, a partial attempt is worse than no attempt: a recording with
    any ``tuit_downloads`` row is filtered out by
    :func:`get_tuit_download_rec_ids`, so one qBittorrent outage mid-run would
    strand it permanently. A recording that ever reached ``qbt_added`` is never
    returned, even if a later attempt failed.

    Args:
        include_unseeded: Also retry rows whose latest status is
            ``'not_seeded'``. Off by default — the common reasons (no LB
            number, an overlay one piece short) do not change hour to hour.
        limit: Cap the number of ids returned, oldest attempt first, so a
            backlog cannot swamp a scheduled run.
        max_attempts: Give up on a recording after this many attempts that
            never reached ``qbt_added``. Without it a recording deleted from
            the tracker is re-fetched every run forever, since its detail page
            404s before any status can improve. 0 disables the cap.
        db_path: Optional DB path override.

    Returns:
        Recording ids to re-queue, oldest attempt first.
    """
    statuses = list(TUIT_RETRY_STATUSES)
    if include_unseeded:
        statuses.append("not_seeded")

    sql = f"""
        SELECT d.rec_id
          FROM tuit_downloads d
         WHERE d.id = (SELECT MAX(id) FROM tuit_downloads
                        WHERE rec_id = d.rec_id)
           AND d.status IN ({', '.join('?' for _ in statuses)})
           AND NOT EXISTS (SELECT 1 FROM tuit_downloads
                            WHERE rec_id = d.rec_id AND status = 'qbt_added')
           AND (? = 0 OR (SELECT COUNT(*) FROM tuit_downloads
                           WHERE rec_id = d.rec_id) < ?)
         ORDER BY d.attempted_at, d.id
    """
    params: list = [*statuses, max_attempts, max_attempts]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection(db_path) as conn:
        return [r["rec_id"] for r in conn.execute(sql, params).fetchall()]
