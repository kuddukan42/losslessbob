"""Song-centric index — LISTENING spec §3 (TODO-230), amended by
``instructions/WORK_PACKAGE_NEXT.md`` slot 2: ``olof_songs`` is the spine
(61,708 normalised per-performance rows, ~97.8% concert coverage per Olof
Bjorner's DSN chronology), NOT setlist.fm + free-text parsing as the original
spec draft assumed.

Two tables, both USER-tier (never exported in master data — see
``backend.db.USER_TABLES``):

- ``song_canonical`` — a normalised-alias -> display-spelling table, seeded
  automatically from ``olof_songs.song_title`` norm-groups but curator-
  editable (``source='curator'`` rows are sticky and never overwritten by
  re-seeding). This is the "song-title canonicalisation table" the spec
  calls out as needing to be a real table, not code constants — it directly
  feeds TODO-225 (setlist fingerprinting).
- ``song_performances`` — a derived table, wholesale-recomputed (like
  ``show_picks``/``concert_ranker/picks.py``) from
  ``olof_songs JOIN olof_events``, one row per performed song/take.

Entry points: :func:`normalize_song_title` (the grouping-key normaliser),
:func:`run` (seed + wholesale recompute, called by the
``POST /api/derived/recompute`` chain and ``tools/compute_song_performances.py``),
:func:`upsert_alias` (curator alias edit), :func:`get_songs` and
:func:`get_song_performances` (the two read routes' backing queries).
"""
from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

from backend.db import get_connection, get_write_queue, init_db

log = logging.getLogger(__name__)

# Curly/smart single-quote variants (left/right quotation marks, modifier
# apostrophe, acute/grave accents sometimes used as apostrophe stand-ins) —
# unified to a straight apostrophe before normalisation so "Don't" and
# "Don't" (curly) land in the same norm group. Kept as a real character
# (not stripped to a space) so contractions stay distinguishable from their
# run-together spelling.
_APOSTROPHE_VARIANTS = "‘’ʼ′´`"
_APOSTROPHE_RE = re.compile("[" + _APOSTROPHE_VARIANTS + "]")

# Everything that is not a word character and not the (already-unified)
# apostrophe becomes a single space; runs of whitespace collapse to one.
_PUNCT_TO_SPACE_RE = re.compile(r"[^\w']+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_song_title(text: str | None) -> str:
    """Normalise a song title into a stable grouping key.

    Pipeline: NFKD decompose + strip combining accent marks, casefold,
    unify curly/straight apostrophe variants, replace remaining punctuation
    with spaces, collapse whitespace.

    Args:
        text: Raw song title (e.g. from ``olof_songs.song_title`` or a
            curator-submitted alias). May be None or blank.

    Returns:
        The normalised key, or ``""`` if *text* is None/blank/all-punctuation.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = no_accents.casefold()
    unified = _APOSTROPHE_RE.sub("'", folded)
    spaced = _PUNCT_TO_SPACE_RE.sub(" ", unified)
    return _WHITESPACE_RE.sub(" ", spaced).strip()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _run_write(fn, db_path: str | None) -> None:
    """Route a write callable through the write queue, matching the BUG-246
    guard in ``concert_ranker/picks.py:_write_picks``: ``init_write_queue`` is
    first-caller-wins, so the singleton queue may be bound to a different DB
    than the one this recompute is targeting (e.g. under pytest, where each
    test uses its own temp DB). Only route through the queue when the paths
    agree; otherwise write directly on a connection to *db_path*.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        log.warning(
            "song_index: write queue bound to %s but this write targets %s — "
            "writing directly", queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _seed_song_canonical(conn: sqlite3.Connection) -> dict:
    """Seed/refresh ``song_canonical`` 'auto' rows from ``olof_songs``.

    Groups every non-blank ``olof_songs.song_title`` by its normalised key,
    picks the most-frequent raw spelling as the canonical display form
    (ties broken alphabetically, for determinism), and upserts. The upsert's
    ``WHERE song_canonical.source != 'curator'`` clause means a curator's
    hand edit is never clobbered by re-seeding, even if the raw-spelling
    frequencies would otherwise pick something else.

    Args:
        conn: Open write connection (called inside a write-queue txn).

    Returns:
        Dict with ``distinct_norms`` (song groups seen) and ``skipped_blank``
        (olof_songs rows whose title normalised to "").
    """
    rows = conn.execute("SELECT song_title FROM olof_songs").fetchall()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    skipped_blank = 0
    for r in rows:
        raw = (r["song_title"] or "").strip()
        norm = normalize_song_title(raw)
        if not norm:
            skipped_blank += 1
            continue
        counts[norm][raw] += 1

    for norm, raw_counts in counts.items():
        canonical = sorted(raw_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        conn.execute(
            "INSERT INTO song_canonical (alias_norm, canonical, source, updated_at)"
            " VALUES (?, ?, 'auto', CURRENT_TIMESTAMP)"
            " ON CONFLICT(alias_norm) DO UPDATE SET"
            " canonical=excluded.canonical, updated_at=excluded.updated_at"
            " WHERE song_canonical.source != 'curator'",
            (norm, canonical),
        )

    return {"distinct_norms": len(counts), "skipped_blank": skipped_blank}


def _load_song_canonical_map(conn: sqlite3.Connection) -> dict[str, str]:
    """Return ``{alias_norm: canonical}`` for every seeded/curated song."""
    rows = conn.execute("SELECT alias_norm, canonical FROM song_canonical").fetchall()
    return {r["alias_norm"]: r["canonical"] for r in rows}


def _build_performance_rows(conn: sqlite3.Connection, canonical_map: dict[str, str]) -> tuple[
    list[tuple], dict
]:
    """Read ``olof_songs JOIN olof_events`` and build ``song_performances`` rows.

    Args:
        conn: Read connection.
        canonical_map: ``{alias_norm: canonical}`` from :func:`_load_song_canonical_map`
            (already includes this run's fresh auto-seed, so every norm here
            resolves).

    Returns:
        ``(rows, stats)`` where *rows* are ready-to-insert tuples and *stats*
        has ``skipped_blank`` (olof_songs rows with no usable title).
    """
    src = conn.execute(
        """
        SELECT os.event_id, os.position, os.song_title, os.is_encore, os.take_status,
               oe.date_str, oe.event_type
        FROM olof_songs os
        JOIN olof_events oe ON oe.event_id = os.event_id
        """
    ).fetchall()

    rows: list[tuple] = []
    skipped_blank = 0
    for r in src:
        norm = normalize_song_title(r["song_title"])
        if not norm:
            skipped_blank += 1
            continue
        canonical = canonical_map.get(norm, (r["song_title"] or "").strip())
        date_iso = r["date_str"] or None  # olof_events.date_str is '' when unparsed
        rows.append((
            r["event_id"],
            r["position"],
            norm,
            canonical,
            date_iso,
            r["is_encore"],
            r["take_status"] or "",
            r["event_type"] or "",
        ))
    return rows, {"skipped_blank": skipped_blank}


def _write_song_performances(rows: list[tuple], db_path: str | None) -> None:
    """Wholesale-replace ``song_performances`` (DELETE + reinsert, one txn).

    Refuses an empty replace, mirroring ``concert_ranker/picks.py``'s
    BUG-246 guard: zero computed rows almost always means the read side saw
    an empty/wrong DB (e.g. ``olof_songs`` not yet scraped), not that the
    real song index shrank to nothing — committing DELETE + nothing would
    silently wipe already-computed data.
    """
    if not rows:
        log.error(
            "song_index recompute produced 0 performance rows — refusing "
            "wholesale replace, existing song_performances rows kept"
        )
        return

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM song_performances")
        conn.executemany(
            "INSERT INTO song_performances"
            " (event_id, position, song_norm, song_canonical, concert_date_iso,"
            " is_encore, take_status, event_type)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    _run_write(_do, db_path)


def run(dry_run: bool = False, db_path: str | None = None) -> dict:
    """Seed ``song_canonical`` and wholesale-recompute ``song_performances``.

    Idempotent: re-running with unchanged ``olof_songs``/``olof_events`` and
    no new curator aliases produces an identical ``song_performances`` table,
    because it is deterministically rebuilt from that input every time.
    Curator-edited ``song_canonical`` rows (``source='curator'``) are never
    touched by the seeding step, so a curator's spelling choice sticks across
    every future recompute.

    Args:
        dry_run: Compute but do not write to the database.
        db_path: Optional database path override.

    Returns:
        Summary dict: ``performances_written``, ``distinct_songs``,
        ``distinct_events``, ``canonical_distinct_norms``,
        ``skipped_blank_title``.
    """
    init_db(db_path)  # idempotent; ensures song_canonical/song_performances exist
    conn = get_connection(db_path)

    # Seeding is itself a write (upserts 'auto' rows) — skipped entirely on
    # dry_run so a preview run never mutates song_canonical. The preview then
    # falls back to whatever song_canonical already has (plus the raw-title
    # fallback in _build_performance_rows for norms not seeded yet).
    if not dry_run:
        _run_write(_seed_song_canonical, db_path)

    canonical_map = _load_song_canonical_map(conn)
    seed_stats = {"distinct_norms": len(canonical_map)}
    rows, build_stats = _build_performance_rows(conn, canonical_map)

    distinct_songs = len({r[2] for r in rows})
    distinct_events = len({r[0] for r in rows})

    if not dry_run:
        _write_song_performances(rows, db_path)

    return {
        "performances_written": len(rows),
        "distinct_songs": distinct_songs,
        "distinct_events": distinct_events,
        "canonical_distinct_norms": seed_stats.get("distinct_norms", 0),
        "skipped_blank_title": build_stats["skipped_blank"],
    }


def upsert_alias(alias: str, canonical: str, db_path: str | None = None) -> dict:
    """Curator write: map *alias* to *canonical*, then re-run the recompute.

    Args:
        alias: Raw alias text (any spelling/casing); normalised here.
        canonical: The display spelling the curator wants shown for this song.
        db_path: Optional database path override.

    Returns:
        The :func:`run` stats dict for the recompute triggered by this edit.

    Raises:
        ValueError: If *alias* or *canonical* is blank, or *alias* normalises
            to "" (nothing to key on).
    """
    if not isinstance(alias, str) or not alias.strip():
        raise ValueError("alias is required")
    if not isinstance(canonical, str) or not canonical.strip():
        raise ValueError("canonical is required")
    alias_norm = normalize_song_title(alias)
    if not alias_norm:
        raise ValueError("alias normalises to empty — nothing to key on")
    canonical = canonical.strip()

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO song_canonical (alias_norm, canonical, source, updated_at)"
            " VALUES (?, ?, 'curator', CURRENT_TIMESTAMP)"
            " ON CONFLICT(alias_norm) DO UPDATE SET"
            " canonical=excluded.canonical, source='curator', updated_at=excluded.updated_at",
            (alias_norm, canonical),
        )

    _run_write(_do, db_path)
    return run(dry_run=False, db_path=db_path)


# ── Read queries backing the GET routes ───────────────────────────────────────

def get_songs(q: str | None = None, db_path: str | None = None) -> list[dict]:
    """List distinct songs from ``song_performances``, most-performed first.

    Args:
        q: Optional substring filter, matched case-insensitively against the
            canonical display spelling and against the normalised key (so a
            punctuation/casing-agnostic search also works).
        db_path: Optional database path override.

    Returns:
        List of dicts: ``song_norm``, ``canonical``, ``n_performances``,
        ``n_concerts`` (distinct events), ``first_date``, ``last_date``
        (ISO, may be None), ``n_dates_with_recordings`` (distinct
        performance dates that also have >=1 ``show_picks`` row, i.e. a
        circulating recording is catalogued for that date). Ordered by
        ``n_performances`` descending, then canonical ascending.
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "song_performances"):
        return []

    where = ""
    params: list = []
    if q and q.strip():
        where = "WHERE (LOWER(song_canonical) LIKE ? OR song_norm LIKE ?)"
        params = [f"%{q.strip().lower()}%", f"%{normalize_song_title(q)}%"]

    rows = conn.execute(
        f"""
        SELECT song_norm,
               MIN(song_canonical) AS canonical,
               COUNT(*) AS n_performances,
               COUNT(DISTINCT event_id) AS n_concerts,
               MIN(concert_date_iso) AS first_date,
               MAX(concert_date_iso) AS last_date,
               COUNT(DISTINCT CASE
                   WHEN concert_date_iso IN (SELECT DISTINCT concert_date_iso FROM show_picks)
                   THEN concert_date_iso
               END) AS n_dates_with_recordings
        FROM song_performances
        {where}
        GROUP BY song_norm
        ORDER BY n_performances DESC, canonical ASC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _load_latest_abs_grades(conn: sqlite3.Connection) -> dict[int, str]:
    """Return ``{lb_number: abs_grade}`` from the newest scored scan.

    Mirrors ``backend.db._load_latest_abs_grades`` / ``concert_ranker/picks.py:
    _load_latest_quality`` — duplicated locally rather than imported to avoid
    a db.py <-> song_index.py import cycle risk; feature-detected the same
    way (``abs_grade`` is a later ``concert_ranker/lb/repo.py`` migration
    column, absent on a DB that has never run Concert Ranker).
    """
    scan_row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_recording_scores").fetchone()
    scan_id = scan_row["m"] if scan_row else None
    if scan_id is None:
        return {}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    if "abs_grade" not in cols:
        return {}
    rows = conn.execute(
        "SELECT lb_number, abs_grade FROM quality_recording_scores"
        " WHERE scan_id=? AND abs_grade IS NOT NULL",
        (scan_id,),
    ).fetchall()
    return {r["lb_number"]: r["abs_grade"] for r in rows}


def get_song_performances(song_norm: str, db_path: str | None = None) -> dict | None:
    """Every performance of one song, joined to venue and circulating recordings.

    Args:
        song_norm: The normalised song key (as returned by :func:`get_songs`).
        db_path: Optional database path override.

    Returns:
        None if *song_norm* has no rows in ``song_performances`` (unknown
        song -> caller should 404). Otherwise a dict: ``song_norm``,
        ``canonical``, and ``performances`` (list of dicts: ``date_iso``,
        ``event_id``, ``event_type``, ``venue``, ``city``, ``is_encore``,
        ``take_status``, ``recordings`` — a list of ``{lb_number, pick_rank,
        abs_grade}`` sourced from ``show_picks`` for that date, ``pick_rank``
        ascending, ``abs_grade`` from the latest Concert Ranker scan or
        None if never scanned). Ordered chronologically (undated performances
        last).
    """
    conn = get_connection(db_path)
    perf_rows = conn.execute(
        """
        SELECT sp.event_id, sp.position, sp.song_canonical, sp.concert_date_iso,
               sp.is_encore, sp.take_status, sp.event_type,
               oe.venue, oe.city
        FROM song_performances sp
        JOIN olof_events oe ON oe.event_id = sp.event_id
        WHERE sp.song_norm = ?
        ORDER BY (sp.concert_date_iso IS NULL), sp.concert_date_iso ASC, sp.event_id ASC
        """,
        (song_norm,),
    ).fetchall()
    if not perf_rows:
        return None

    canonical = perf_rows[0]["song_canonical"]
    dates = {r["concert_date_iso"] for r in perf_rows if r["concert_date_iso"]}
    picks_by_date: dict[str, list[dict]] = defaultdict(list)
    if dates:
        placeholders = ",".join("?" * len(dates))
        pick_rows = conn.execute(
            f"SELECT concert_date_iso, lb_number, pick_rank FROM show_picks"
            f" WHERE concert_date_iso IN ({placeholders}) ORDER BY pick_rank ASC",
            tuple(dates),
        ).fetchall()
        for pr in pick_rows:
            picks_by_date[pr["concert_date_iso"]].append(
                {"lb_number": pr["lb_number"], "pick_rank": pr["pick_rank"]}
            )
    abs_grades = _load_latest_abs_grades(conn)

    performances = []
    for r in perf_rows:
        recordings = []
        for p in picks_by_date.get(r["concert_date_iso"], []):
            recordings.append({
                "lb_number": p["lb_number"],
                "pick_rank": p["pick_rank"],
                "abs_grade": abs_grades.get(p["lb_number"]),
            })
        performances.append({
            "date_iso": r["concert_date_iso"],
            "event_id": r["event_id"],
            "event_type": r["event_type"],
            "venue": r["venue"],
            "city": r["city"],
            "is_encore": bool(r["is_encore"]),
            "take_status": r["take_status"],
            "recordings": recordings,
        })

    return {"song_norm": song_norm, "canonical": canonical, "performances": performances}
