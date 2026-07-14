"""Setlist fingerprinting — TODO-225: identify entries whose date/location
metadata is unusable ('various', 'vsrious', '4 rare tracks from 1966',
empty/xx dates, or a location the TODO-221 geocoder filter parked in
``location_geocoded.source='skipped_not_concert'``) by scoring the entry's
folder tracklist against every Olof Björner setlist (``olof_songs``).

This is a targeted tool for the unknown/junk-metadata tail, NOT bulk
re-dating — entries with a clean, already-matched date are never candidates
(see :func:`_find_candidate_entries`). Reuses the same title-normalisation
and matching rule as ``backend.db.compare_olof_setlist`` (containment-
tolerant, cp1252/curly-quote folded) so a folder title like "Blowin' In The
Wind (acoustic)" still matches Olof's "Blowin' in the Wind".

Scoring blends three signals per candidate event: what fraction of the
entry's tracklist matched (``entry_coverage``), how much of the matched
subsequence preserves Olof's song order (``order_score``, via longest
increasing subsequence of matched positions — tolerates a partial/audience
tape missing songs, but rewards a run that isn't shuffled), and how much of
the *full* show the tape covers (``olof_coverage``, informational — partial
tapes are expected and not penalized beyond this small weight). Setlists are
near-unique per show (FABLE_OLOF_FILES.md §5.1), so a handful of matched
songs in the right relative order is a strong identification signal even for
a short excerpt.

OUTPUT is suggestions only, written to ``setlist_fingerprint_suggestions``
(top few candidate events per entry) — never auto-applied to
``entries.date_str``/``location``. A curator reviews a suggestion and either
hand-edits the entry (which drops it out of the candidate set on the next
scan, since it then has a clean date) or dismisses it
(:func:`dismiss_suggestion`, status sticky across rescans).

Entry points: :func:`run_fingerprint_scan` (the scan/recompute, called by
``POST /api/fingerprint/scan``), :func:`get_suggestions` and
:func:`dismiss_suggestion` (backing ``GET /api/fingerprint/suggestions`` and
``POST /api/fingerprint/suggestions/dismiss``).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

from backend.db import (
    get_connection,
    get_write_queue,
    init_db,
    normalize_title_for_match,
    parse_entry_setlist_titles,
    titles_match,
)
from backend.geocoder import (
    _entry_date_to_iso,  # reused: same "clean date?" test as the geocoder filter
)

log = logging.getLogger(__name__)

# An event needs at least this many matched songs to be worth surfacing —
# a single shared song (e.g. "Like A Rolling Stone", played almost every
# show) is not an identification, just noise.
_MIN_MATCHED_SONGS = 2

# Top N candidate events kept per entry, best score first.
_TOP_N = 3

# Score weights: entry_coverage (how much of the tape is identified) matters
# most, order_score (does the matched run preserve Olof's song order) next,
# olof_coverage (how much of the full show this tape has) least — partial
# tapes are the norm and shouldn't be penalized much for it.
_W_ENTRY_COVERAGE = 0.5
_W_ORDER = 0.3
_W_OLOF_COVERAGE = 0.2


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _run_write(fn, db_path: str | None):
    """Route a write callable through the write queue, matching the BUG-246
    guard used elsewhere (song_index.py, taper_attribution.py): the write
    queue singleton is first-caller-wins, so under pytest (each test its own
    temp DB) it may be bound to a different DB than *db_path*.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        log.warning(
            "setlist_fingerprint: write queue bound to %s but this write targets %s"
            " — writing directly", queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _find_candidate_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Entries needing fingerprint identification.

    A candidate has a tracklist (``entries.setlist``) and either no clean,
    single, parseable date (empty/'xx'/free text like 'various') or a
    location the TODO-221 geocoder filter parked in
    ``location_geocoded.source='skipped_not_concert'`` — entries with a
    clean date already matched to a documented show are never re-scored
    (this tool is not bulk re-dating).

    Args:
        conn: Read connection.

    Returns:
        Rows with ``lb_number``, ``date_str``, ``location``, ``setlist``.
    """
    rows = conn.execute(
        "SELECT lb_number, date_str, location, setlist FROM entries"
        " WHERE setlist IS NOT NULL AND setlist != ''"
    ).fetchall()

    skipped_locations: set[str] = set()
    if _table_exists(conn, "location_geocoded"):
        skipped_locations = {
            r["location_text"] for r in conn.execute(
                "SELECT location_text FROM location_geocoded WHERE source='skipped_not_concert'"
            ).fetchall()
        }

    candidates = []
    for r in rows:
        has_clean_date = _entry_date_to_iso(r["date_str"] or "") is not None
        if has_clean_date and (r["location"] or "") not in skipped_locations:
            continue
        candidates.append(r)
    return candidates


def _load_song_index(
    conn: sqlite3.Connection,
) -> tuple[dict[int, list[tuple[int, str, str]]], dict[str, set[int]]]:
    """Load ``olof_songs`` once per scan into an in-memory scoring index.

    Args:
        conn: Read connection.

    Returns:
        ``(events_songs, title_index)``: ``events_songs[event_id]`` is an
        ordered list of ``(position, song_title, normalized_title)``;
        ``title_index[normalized_title]`` is the set of event_ids whose
        setlist contains that exact normalized title — used to cheaply
        narrow ~4,500 events down to a handful of real candidates per entry
        before running the (more expensive, containment-tolerant) full
        scoring pass.
    """
    rows = conn.execute(
        "SELECT event_id, position, song_title FROM olof_songs ORDER BY event_id, position"
    ).fetchall()
    events_songs: dict[int, list[tuple[int, str, str]]] = defaultdict(list)
    title_index: dict[str, set[int]] = defaultdict(set)
    for r in rows:
        norm = normalize_title_for_match(r["song_title"])
        events_songs[r["event_id"]].append((r["position"], r["song_title"], norm))
        if norm:
            title_index[norm].add(r["event_id"])
    return events_songs, title_index


def _lis_length(seq: list[int]) -> int:
    """Length of the longest strictly-increasing subsequence of *seq*.

    Standard patience-sorting O(n log n) algorithm. Used to measure how much
    of a matched-songs run preserves Olof's setlist order: positions are
    unique per event, so a longer increasing run means the entry's track
    order agrees with the real setlist order rather than being shuffled.
    """
    tails: list[int] = []
    for x in seq:
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if tails[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        if lo == len(tails):
            tails.append(x)
        else:
            tails[lo] = x
    return len(tails)


def _score_event(
    entry_norms: list[str], olof_songs: list[tuple[int, str, str]]
) -> dict | None:
    """Score one candidate event against one entry's normalized tracklist.

    Matches each entry title against the event's setlist greedily (same
    algorithm as ``compare_olof_setlist``: first not-yet-claimed olof
    position it satisfies :func:`titles_match` against), order-independent
    on the entry side.

    Args:
        entry_norms: Normalized entry track titles, in folder order. Blank
            entries (unparseable titles) are ignored.
        olof_songs: This event's ``(position, song_title, normalized_title)``
            list, from :func:`_load_song_index`.

    Returns:
        None if nothing matched. Otherwise a dict: ``score`` (0-1),
        ``matched_count``, ``entry_coverage``, ``order_score``,
        ``olof_coverage``, ``matches`` (list of ``{entry_index, position,
        matched_title}``), ``missing`` (olof song titles no entry title
        matched).
    """
    matched_positions: set[int] = set()
    pairs: list[tuple[int, int]] = []
    matches_out: list[dict] = []
    for i, norm_in in enumerate(entry_norms):
        if not norm_in:
            continue
        found = None
        for pos, title, norm_o in olof_songs:
            if pos in matched_positions:
                continue
            if titles_match(norm_in, norm_o):
                found = (pos, title)
                break
        if found:
            matched_positions.add(found[0])
            pairs.append((i, found[0]))
            matches_out.append({
                "entry_index": i, "position": found[0], "matched_title": found[1],
            })

    matched_count = len(pairs)
    if matched_count == 0:
        return None

    entry_title_count = sum(1 for n in entry_norms if n)
    entry_coverage = matched_count / entry_title_count if entry_title_count else 0.0
    olof_coverage = matched_count / len(olof_songs) if olof_songs else 0.0
    order_score = _lis_length([p for _, p in pairs]) / matched_count

    score = round(
        _W_ENTRY_COVERAGE * entry_coverage
        + _W_ORDER * order_score
        + _W_OLOF_COVERAGE * min(olof_coverage, 1.0),
        4,
    )
    missing = [title for pos, title, _ in olof_songs if pos not in matched_positions]

    return {
        "score": score,
        "matched_count": matched_count,
        "entry_coverage": round(entry_coverage, 4),
        "order_score": round(order_score, 4),
        "olof_coverage": round(olof_coverage, 4),
        "matches": matches_out,
        "missing": missing,
    }


def _candidate_event_ids(entry_norms: list[str], title_index: dict[str, set[int]]) -> set[int]:
    """Events sharing at least one exact normalized title with the entry.

    Cheap pre-filter before the full (containment-tolerant) scoring pass —
    without it, scoring every entry against all ~4,500 olof_events would be
    prohibitively slow. An event that shares zero exact-normalized titles
    with the entry cannot score above 0 anyway, so this never drops a real
    match — it can only miss the rare case where every shared song differs
    only by a containment-matchable suffix (e.g. an appended "(acoustic)"),
    which is an accepted tradeoff for keeping a scan fast.
    """
    ids: set[int] = set()
    for norm in entry_norms:
        if norm:
            ids |= title_index.get(norm, set())
    return ids


def run_fingerprint_scan(limit: int | None = None, dry_run: bool = False, db_path: str | None = None) -> dict:
    """Scan candidate entries and wholesale-recompute the suggestion queue.

    Idempotent given unchanged ``entries``/``olof_songs`` input. Curator
    ``status`` (e.g. 'dismissed') is preserved across rescans for any
    (lb_number, event_id) pair that recurs — a rescan doesn't resurface an
    already-dismissed suggestion unless the candidate set itself changes.

    Args:
        limit: Optional cap on the number of candidate entries scanned
            (newest-added-metadata-tail entries aren't in any particular
            priority order, so this is a smoke-test knob, not a curated
            "first N" — omit for a full scan).
        dry_run: Compute but do not write to the database.
        db_path: Optional database path override.

    Returns:
        Summary dict: ``candidates_scanned``, ``candidates_matched`` (had
        >=1 event scoring >= ``_MIN_MATCHED_SONGS``), ``suggestions_written``,
        ``skipped_no_titles`` (candidate had a setlist string that parsed to
        zero titles).
    """
    init_db(db_path)
    conn = get_connection(db_path)

    if not _table_exists(conn, "olof_songs"):
        return {
            "candidates_scanned": 0, "candidates_matched": 0,
            "suggestions_written": 0, "skipped_no_titles": 0,
        }

    candidates = _find_candidate_entries(conn)
    if limit is not None:
        candidates = candidates[:limit]

    events_songs, title_index = _load_song_index(conn)

    rows_to_write: list[tuple] = []
    candidates_matched = 0
    skipped_no_titles = 0

    for entry in candidates:
        titles = parse_entry_setlist_titles(entry["setlist"] or "")
        if not titles:
            skipped_no_titles += 1
            continue
        entry_norms = [normalize_title_for_match(t) for t in titles]

        scored: list[tuple[int, dict]] = []
        for event_id in _candidate_event_ids(entry_norms, title_index):
            result = _score_event(entry_norms, events_songs[event_id])
            if result and result["matched_count"] >= _MIN_MATCHED_SONGS:
                scored.append((event_id, result))
        if not scored:
            continue

        scored.sort(key=lambda kv: kv[1]["score"], reverse=True)
        candidates_matched += 1
        for rank, (event_id, result) in enumerate(scored[:_TOP_N], start=1):
            rows_to_write.append((
                entry["lb_number"], rank, event_id, result["score"], result["matched_count"],
                len(entry_norms), len(events_songs[event_id]),
                json.dumps(result["matches"]), json.dumps(result["missing"]),
            ))

    if not dry_run:
        _write_suggestions(rows_to_write, db_path)

    return {
        "candidates_scanned": len(candidates),
        "candidates_matched": candidates_matched,
        "suggestions_written": len(rows_to_write),
        "skipped_no_titles": skipped_no_titles,
    }


def _write_suggestions(rows: list[tuple], db_path: str | None) -> None:
    """Wholesale-replace ``setlist_fingerprint_suggestions``, preserving status.

    Unlike ``song_performances``/``show_picks``, an empty *rows* is a
    legitimate outcome here (every candidate entry already dated, or none
    matched) — no BUG-246-style empty-replace guard.
    """
    def _do(conn: sqlite3.Connection) -> None:
        existing_status = {
            (r["lb_number"], r["event_id"]): r["status"]
            for r in conn.execute(
                "SELECT lb_number, event_id, status FROM setlist_fingerprint_suggestions"
            ).fetchall()
        }
        conn.execute("DELETE FROM setlist_fingerprint_suggestions")
        conn.executemany(
            "INSERT INTO setlist_fingerprint_suggestions"
            " (lb_number, rank, event_id, score, matched_count, entry_song_count,"
            "  olof_song_count, matches_json, missing_json, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (*row, existing_status.get((row[0], row[2]), "pending"))
                for row in rows
            ],
        )

    _run_write(_do, db_path)


def get_suggestions(status: str = "pending", db_path: str | None = None) -> list[dict]:
    """List the current suggestion queue, joined to entry + Olof event context.

    Args:
        status: 'pending' (default), 'dismissed', or 'all'.
        db_path: Optional database path override.

    Returns:
        List of dicts ordered by lb_number then rank: ``lb_number``, ``rank``,
        ``event_id``, ``score``, ``matched_count``, ``entry_song_count``,
        ``olof_song_count``, ``matched`` (parsed matches_json), ``missing``
        (parsed missing_json), ``status``, ``computed_at``, ``entry_date_str``,
        ``entry_location``, ``event_date``, ``venue``, ``city``, ``region``,
        ``country``, ``event_type``.
    """
    conn = get_connection(db_path)
    if not _table_exists(conn, "setlist_fingerprint_suggestions"):
        return []

    where = ""
    params: list = []
    if status and status != "all":
        where = "WHERE s.status = ?"
        params = [status]

    rows = conn.execute(
        f"""
        SELECT s.lb_number, s.rank, s.event_id, s.score, s.matched_count,
               s.entry_song_count, s.olof_song_count, s.matches_json, s.missing_json,
               s.status, s.computed_at,
               e.date_str AS entry_date_str, e.location AS entry_location,
               oe.date_str AS event_date, oe.venue, oe.city, oe.region, oe.country,
               oe.event_type
        FROM setlist_fingerprint_suggestions s
        JOIN entries e ON e.lb_number = s.lb_number
        JOIN olof_events oe ON oe.event_id = s.event_id
        {where}
        ORDER BY s.lb_number ASC, s.rank ASC
        """,
        params,
    ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["matched"] = json.loads(d.pop("matches_json") or "[]")
        d["missing"] = json.loads(d.pop("missing_json") or "[]")
        out.append(d)
    return out


def dismiss_suggestion(lb_number: int, event_id: int, db_path: str | None = None) -> bool:
    """Mark one suggestion dismissed — sticky across future rescans.

    Args:
        lb_number: Catalog entry number.
        event_id: The suggested Olof event to dismiss for this entry.
        db_path: Optional database path override.

    Returns:
        True if a matching row was updated, False if none existed.
    """
    def _do(conn: sqlite3.Connection) -> int:
        cur = conn.execute(
            "UPDATE setlist_fingerprint_suggestions SET status='dismissed'"
            " WHERE lb_number=? AND event_id=?",
            (lb_number, event_id),
        )
        return cur.rowcount

    rowcount = _run_write(_do, db_path)
    return bool(rowcount)
