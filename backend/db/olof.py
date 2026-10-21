"""Olof Björner surfacing + setlist-vs-folder title comparison (from backend.db, TODO-369 S2)."""

import re
import sqlite3

from backend.checksum_utils import _APOSTROPHE_TRANS
from backend.db import get_connection

# --- Olof Björner surfacing (FABLE_OLOF_FILES.md P5a) ----------------------
#
# olof_* tables are local-only (not in MASTER_TABLES) — every reader here must
# degrade to empty results/None when the tables are empty or absent rather
# than raising, since a fresh import may not have run the olof scraper yet.

_OLOF_EVENT_COLUMNS = (
    "event_id, source, page_filename, event_type, date_str, date_raw, venue,"
    " city, region, country, tour_name, session_title, concert_no_net,"
    " concert_no_year, lineup, recording_info, recording_kind, recording_mins,"
    " notes, bobtalk, releases_raw, references_raw, updated_raw, raw_text"
)


def _olof_songs_for_events(conn: sqlite3.Connection, event_ids: list[int]) -> dict[int, list[dict]]:
    """Return ``{event_id: [song dict, ...]}`` ordered by position for *event_ids*."""
    if not event_ids:
        return {}
    placeholders = ",".join("?" * len(event_ids))
    rows = conn.execute(
        f"""SELECT event_id, position, song_title, credits, is_encore, take_number,
                   take_status, annotations, released_on
            FROM olof_songs WHERE event_id IN ({placeholders})
            ORDER BY event_id, position""",
        event_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {eid: [] for eid in event_ids}
    for r in rows:
        out[r["event_id"]].append({
            "position": r["position"],
            "song_title": r["song_title"],
            "credits": r["credits"],
            "is_encore": r["is_encore"],
            "take_number": r["take_number"],
            "take_status": r["take_status"],
            "annotations": r["annotations"],
            "released_on": r["released_on"],
        })
    return out


def get_olof_date(date_str: str, db_path=None) -> dict:
    """Return everything Olof Björner's corpus knows about a show date.

    Args:
        date_str: ISO ``yyyy-mm-dd`` show date.
        db_path: Optional path to the SQLite database file.

    Returns:
        dict with keys ``date_str``, ``events`` (each an olof_events row plus
        a nested ``songs`` list ordered by position), ``chronicle`` (matching
        olof_chronicle rows), and ``new_tapes`` (matching olof_new_tapes rows,
        circulation provenance). Every list is empty (never absent/404) when
        the olof tables have no data for this date.
    """
    conn = get_connection(db_path)
    events = conn.execute(
        f"SELECT {_OLOF_EVENT_COLUMNS} FROM olof_events WHERE date_str=? ORDER BY event_id",
        (date_str,),
    ).fetchall()
    songs_by_event = _olof_songs_for_events(conn, [r["event_id"] for r in events])
    events_out = []
    for r in events:
        d = dict(r)
        d["songs"] = songs_by_event.get(r["event_id"], [])
        events_out.append(d)
    chronicle = conn.execute(
        """SELECT year, seq, date_str, date_raw, entry_text FROM olof_chronicle
           WHERE date_str=? ORDER BY year, seq""",
        (date_str,),
    ).fetchall()
    new_tapes = conn.execute(
        """SELECT year, seq, title, date_str, body_text FROM olof_new_tapes
           WHERE date_str=? ORDER BY year, seq""",
        (date_str,),
    ).fetchall()
    return {
        "date_str": date_str,
        "events": events_out,
        "chronicle": [dict(r) for r in chronicle],
        "new_tapes": [dict(r) for r in new_tapes],
    }


def get_olof_event(event_id: int, db_path=None) -> dict | None:
    """Return one olof_events row with all columns and its ordered song list.

    Args:
        event_id: DSN event id (or synthetic chronicle-appendix id).
        db_path: Optional path to the SQLite database file.

    Returns:
        Event dict (all olof_events columns) with a nested ``songs`` list, or
        ``None`` if no such event exists.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        f"SELECT {_OLOF_EVENT_COLUMNS} FROM olof_events WHERE event_id=?", (event_id,)
    ).fetchone()
    if not row:
        return None
    event = dict(row)
    event["songs"] = _olof_songs_for_events(conn, [event_id]).get(event_id, [])
    return event


def get_olof_chronicle_year(year: int, db_path=None) -> list[dict]:
    """Return one chronicle year's entries in calendar (seq) order.

    Args:
        year: Chronicle year, e.g. 2002.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of olof_chronicle row dicts, ordered by ``seq``; empty if the
        year has no chronicle page parsed.
    """
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT year, seq, date_str, date_raw, entry_text FROM olof_chronicle
           WHERE year=? ORDER BY seq""",
        (year,),
    ).fetchall()
    return [dict(r) for r in rows]


_OLOF_LIKE_ESCAPE = "\\"


def _olof_like_pattern(q: str) -> str:
    """Escape ``%``/``_``/the escape char itself so *q* matches literally in LIKE."""
    escaped = (
        q.replace(_OLOF_LIKE_ESCAPE, _OLOF_LIKE_ESCAPE * 2)
        .replace("%", _OLOF_LIKE_ESCAPE + "%")
        .replace("_", _OLOF_LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


def _olof_snippet(text: str, q: str, context: int = 60) -> str:
    """Return ~*context* chars of *text* on either side of the first hit of *q*.

    Ellipsizes with ``…`` on whichever side(s) were truncated. Case-insensitive
    match; returns an empty string if *q* is not found (should not happen for
    rows the caller already matched via LIKE).
    """
    idx = text.lower().find(q.lower())
    if idx == -1:
        return ""
    start = max(0, idx - context)
    end = min(len(text), idx + len(q) + context)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def get_olof_bobtalk_search(q: str, limit: int = 50, db_path=None) -> list[dict]:
    """Case-insensitive substring search over olof_events.bobtalk and .notes.

    "Bob said something about X — which night was that?": lets the GUI find
    the show whose BobTalk or notes text mentions *q*, without a schema
    change or FTS5 (the table is small — 4,924 rows).

    Args:
        q: Search text. ``%``/``_`` are escaped so they match literally
           rather than as SQL LIKE wildcards.
        limit: Maximum number of hits to return, applied after ordering.
        db_path: Optional path to the SQLite database file.

    Returns:
        List of hit dicts: ``{event_id, date_str, venue, city, country,
        event_type, concert_no_net, field, snippet}`` where ``field`` is
        ``'bobtalk'`` or ``'notes'``. A row that matches in both fields
        yields only the ``'bobtalk'`` hit (dedupe). Ordered with all
        ``'bobtalk'`` hits before ``'notes'`` hits, and ``date_str``
        ascending within each group. Empty list if *q* is blank.
    """
    q = (q or "").strip()
    if not q:
        return []
    like_pat = _olof_like_pattern(q)
    conn = get_connection(db_path)
    rows = conn.execute(
        f"""SELECT event_id, date_str, venue, city, country, event_type,
                   concert_no_net, bobtalk, notes
            FROM olof_events
            WHERE bobtalk LIKE ? ESCAPE '{_OLOF_LIKE_ESCAPE}'
               OR notes LIKE ? ESCAPE '{_OLOF_LIKE_ESCAPE}'
            ORDER BY date_str ASC""",
        (like_pat, like_pat),
    ).fetchall()

    q_lower = q.lower()
    bobtalk_hits: list[dict] = []
    notes_hits: list[dict] = []
    for r in rows:
        base = {
            "event_id": r["event_id"],
            "date_str": r["date_str"],
            "venue": r["venue"],
            "city": r["city"],
            "country": r["country"],
            "event_type": r["event_type"],
            "concert_no_net": r["concert_no_net"],
        }
        bobtalk = r["bobtalk"] or ""
        notes = r["notes"] or ""
        if q_lower in bobtalk.lower():
            bobtalk_hits.append({
                **base, "field": "bobtalk", "snippet": _olof_snippet(bobtalk, q),
            })
        elif q_lower in notes.lower():
            notes_hits.append({
                **base, "field": "notes", "snippet": _olof_snippet(notes, q),
            })
    return (bobtalk_hits + notes_hits)[:limit]


def get_olof_status(db_path=None) -> dict:
    """Return per-table row counts and the max DSN year, for GUI gating.

    The gui_next show-page panel hides Olof sections entirely when this
    reports zero rows, rather than rendering an empty/broken panel.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        dict: {pages, events, songs, chronicle_rows, new_tapes, chronicle_years,
        max_dsn_year}. ``max_dsn_year`` is the latest calendar year seen among
        DSN (non-chronicle-appendix) event dates, or None if olof_events is
        empty.
    """
    conn = get_connection(db_path)

    def _count(table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    max_year_row = conn.execute(
        """SELECT MAX(CAST(substr(date_str, 1, 4) AS INTEGER)) FROM olof_events
           WHERE source='dsn' AND date_str != ''"""
    ).fetchone()
    return {
        "pages": _count("olof_pages"),
        "events": _count("olof_events"),
        "songs": _count("olof_songs"),
        "chronicle_rows": _count("olof_chronicle"),
        "new_tapes": _count("olof_new_tapes"),
        "chronicle_years": conn.execute(
            "SELECT COUNT(DISTINCT year) FROM olof_chronicle"
        ).fetchone()[0] if _count("olof_chronicle") else 0,
        "max_dsn_year": max_year_row[0] if max_year_row else None,
    }


# --- Title normalization + setlist-vs-folder comparison (spec §5.1) --------

_TITLE_LEADING_THE_RE = re.compile(r"^the\s+")
_TITLE_NONWORD_RE = re.compile(r"[^a-z0-9\s]")
_TITLE_WS_RE = re.compile(r"\s+")

# Below this normalized length, a containment match is too easy to hit by
# accident (e.g. a one-word bogus title matching as a substring of many real
# titles) — require an exact match instead.
_TITLE_MIN_CONTAINMENT_LEN = 4
# The shorter normalized title must cover at least this fraction of the
# longer one for a containment match to count (guards against a short title
# trivially matching as a substring of an unrelated long one).
_TITLE_CONTAINMENT_RATIO = 0.6


def normalize_title_for_match(title: str) -> str:
    """Normalize a song title for cross-source matching (Olof vs folder/input).

    Reuses ``checksum_utils._APOSTROPHE_TRANS`` — the existing cp1252/EAC
    typographic-apostrophe fold used for filename matching — rather than
    re-deriving a curly-quote table. Pipeline: fold curly apostrophes to
    straight, lowercase, drop apostrophes outright (``Maggie's`` and
    ``Maggies`` must normalize identically), strip a leading "The ", replace
    remaining non-alphanumeric characters with a space, then collapse
    whitespace.

    Args:
        title: Raw song title text.

    Returns:
        Normalized comparison key; ``''`` for falsy input.
    """
    if not title:
        return ""
    t = title.translate(_APOSTROPHE_TRANS).lower()
    t = t.replace("'", "")
    t = _TITLE_LEADING_THE_RE.sub("", t)
    t = _TITLE_NONWORD_RE.sub(" ", t)
    return _TITLE_WS_RE.sub(" ", t).strip()


def titles_match(norm_a: str, norm_b: str) -> bool:
    """Whether two already-normalized titles should be treated as the same song.

    Exact match, or a conservative containment check (one is a substring of
    the other and covers at least ``_TITLE_CONTAINMENT_RATIO`` of its length)
    — titles are short enough that fuzzy edit-distance matching isn't needed,
    per FABLE_OLOF_FILES.md §5.1.

    Public (not module-private) because ``backend/setlist_fingerprint.py``
    (TODO-225) reuses it to score a folder tracklist against every Olof
    setlist, not just one date's — same matching rule, different caller.
    """
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    if len(shorter) < _TITLE_MIN_CONTAINMENT_LEN:
        return False
    return shorter in longer and len(shorter) >= _TITLE_CONTAINMENT_RATIO * len(longer)


# A track marker: 1-3 digits after a delimiter, then either optional '.'/')' plus
# whitespace ("1. Title", "01 Title"), or a '.'/')' glued straight onto the title
# ("10.When The Deal Goes Down" — TODO-342 C13). The glued form requires a letter
# or opening quote/bracket after the dot so "12.5" or a "10:30" time never splits.
_ENTRY_TRACK_MARKER_RE = re.compile(
    r"(?:^|[,\n])\s*(\d{1,3})(?:[.)]?\s+|[.)](?=[^\W\d_]|[\"'(\[]))(?=\S)"
)


def parse_entry_setlist_titles(setlist_text: str) -> list[str]:
    """Split an ``entries.setlist`` free-text tracklist into ordered titles.

    ``entries.setlist`` is scraped free text: numbered tracks ("1. Title",
    "01 Title") separated by commas or newlines, occasionally grouped under
    "Disc N," headers with per-disc numbering restarting at 1. A track marker
    is only recognized when its digits are preceded by a comma/newline (or
    text start) — this is what keeps a title like "Highway 61 Revisited" from
    being split on the embedded "61" (preceded by a letter, not a delimiter).

    Known limitation: a "Disc N:" / "Disc Two [37:20]" header between two
    tracks has no marker of its own, so it gets appended to the tail of the
    preceding title (e.g. "Honest With Me, Disc 2:"). Left uncorrected — the
    comparison endpoint's containment check still matches these against the
    clean Olof title in practice; callers needing a clean split should not
    rely on this for anything beyond best-effort comparison input.

    Args:
        setlist_text: Raw ``entries.setlist`` column value.

    Returns:
        Ordered list of title strings. May include non-song noise entries
        ("Disc 2:", "-encore break-", "band intro") verbatim; these simply
        won't match a real Olof title.
    """
    if not setlist_text:
        return []
    matches = list(_ENTRY_TRACK_MARKER_RE.finditer(setlist_text))
    titles: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(setlist_text)
        title = setlist_text[start:end].strip().strip(",").strip()
        if title:
            titles.append(title)
    return titles


def compare_olof_setlist(date_str: str, titles: list[str], db_path=None) -> dict:
    """Compare a folder's track titles against Olof's setlist for a date.

    Matches each input title against the date's Olof setlist (preferring a
    'concert' event when a date has more than one olof_events row) using
    :func:`normalize_title_for_match` + :func:`titles_match`. Matching is
    greedy per input title against not-yet-claimed Olof positions, order
    -independent — the folder's track order need not match Olof's.

    Args:
        date_str: ISO ``yyyy-mm-dd`` show date to compare against.
        titles: Input track titles, in any order.
        db_path: Optional path to the SQLite database file.

    Returns:
        dict: {date_str, olof_event_id (None if no Olof event for this date),
        olof_setlist: [{position, song_title}], matches: [{input_title,
        matched_position, matched_title}] (position/title None when unmatched),
        olof_missing: [song_title, ...] (Olof songs no input title matched),
        match_pct: percentage of the Olof setlist covered by a matched input
        title (0.0 when Olof has no event/songs for the date), recording_info,
        recording_kind, recording_mins}.
    """
    conn = get_connection(db_path)
    event = conn.execute(
        """SELECT event_id, recording_info, recording_kind, recording_mins
           FROM olof_events WHERE date_str=?
           ORDER BY (event_type != 'concert'), event_id LIMIT 1""",
        (date_str,),
    ).fetchone()
    if not event:
        return {
            "date_str": date_str,
            "olof_event_id": None,
            "olof_setlist": [],
            "matches": [
                {"input_title": t, "matched_position": None, "matched_title": None}
                for t in titles
            ],
            "olof_missing": [],
            "match_pct": 0.0,
            "recording_info": "",
            "recording_kind": "",
            "recording_mins": None,
        }

    songs = conn.execute(
        "SELECT position, song_title FROM olof_songs WHERE event_id=? ORDER BY position",
        (event["event_id"],),
    ).fetchall()
    olof_setlist = [{"position": s["position"], "song_title": s["song_title"]} for s in songs]
    olof_norm = [
        (s["position"], s["song_title"], normalize_title_for_match(s["song_title"]))
        for s in songs
    ]

    matched_positions: set[int] = set()
    matches = []
    for raw_title in titles:
        norm_in = normalize_title_for_match(raw_title)
        found = None
        for pos, song_title, norm_o in olof_norm:
            if pos in matched_positions:
                continue
            if titles_match(norm_in, norm_o):
                found = (pos, song_title)
                break
        if found:
            matched_positions.add(found[0])
            matches.append({
                "input_title": raw_title,
                "matched_position": found[0],
                "matched_title": found[1],
            })
        else:
            matches.append({
                "input_title": raw_title, "matched_position": None, "matched_title": None,
            })

    olof_missing = [s["song_title"] for s in songs if s["position"] not in matched_positions]
    match_pct = round(100.0 * len(matched_positions) / len(songs), 1) if songs else 0.0

    return {
        "date_str": date_str,
        "olof_event_id": event["event_id"],
        "olof_setlist": olof_setlist,
        "matches": matches,
        "olof_missing": olof_missing,
        "match_pct": match_pct,
        "recording_info": event["recording_info"] or "",
        "recording_kind": event["recording_kind"] or "",
        "recording_mins": event["recording_mins"],
    }


def resolve_lb_number_titles(lb_number: int, db_path=None) -> list[str] | None:
    """Resolve an lb_number's stored tracklist into titles for the compare endpoint.

    ``entries.setlist`` is the only per-entry stored tracklist text in the
    schema (``entry_files`` only has on-disk filenames, not song titles).
    Lets ``POST /api/olof/compare`` accept ``{lb_number}`` as an alternative
    to an explicit ``titles`` list.

    Args:
        lb_number: Catalog entry number.
        db_path: Optional path to the SQLite database file.

    Returns:
        Parsed title list (via :func:`parse_entry_setlist_titles`), or
        ``None`` if the entry doesn't exist or has no stored setlist text.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT setlist FROM entries WHERE lb_number=?", (lb_number,)
    ).fetchone()
    if not row or not row["setlist"]:
        return None
    return parse_entry_setlist_titles(row["setlist"])
