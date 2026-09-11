"""Cross-source setlist corroboration (TODO-342 Phase 3a, audit Q1-a, plan R-O4).

Compares Olof's parsed setlist for a date against three sources independent of
Olof and of each other: ``setlistfm_setlist``, ``bobdylan_setlist`` and
``tuit_song_performances``. Titles are aligned song by song with the C13
matcher (:mod:`backend.dossier_fields`), not by raw count, per the trust model
in ``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md`` (lines 43-58) and Phase 3
row (a) (lines 406-421).

:func:`setlist_quorum` is the single-date entry point (used by the dossier and
by ad hoc checks); :func:`corroborate_all` is the fast corpus-wide path used
by R-O4 (:func:`backend.qc.rules.rule_o4`) — it preloads each source table by
date in one query apiece instead of querying per date, then shares
:func:`quorum_verdict` with :func:`setlist_quorum` so the two never drift.

TUIT ordering note: ``tuit_song_performances.id`` is an autoincrement surrogate
key populated in alphabetical-by-song order (verified against 1986-02-24: ids
584/994/5237/... line up with "A Hard Rain's...", "Across the Borderline",
"Ballad Of A Thin Man", ... rather than the show's actual running order), and
the table has no other position column. TUIT therefore only ever corroborates
on song set + count, never on order (``order_agrees`` is always ``None`` for
it).
"""
from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import TypedDict

from backend.dossier_fields import (
    SetlistIndex,
    build_setlist_index,
    clean_track_title,
    is_non_song,
    match_track,
)

_log = logging.getLogger(__name__)

# Local copy of backend.dossier.py's _CONCERT_TYPE_FILTER / _primary_event picking
# rule (repo convention: duplicate small private feature-detect helpers rather
# than cross-import — see gap_analysis.py's docstring on this).
_CONCERT_TYPE_FILTER = (
    "((event_type = 'concert' OR event_type LIKE 'concert - %') "
    "AND tour_name NOT LIKE '%ehearsal%')"
)

# setlist.fm and bobdylan.com spell the "Talkin' ... Blues" titles with the
# apostrophe-g contraction ("Talkin' John Birch Paranoid Blues"); Olof and TUIT
# spell them out ("Talking John Birch Paranoid Blues"). The D-01 matcher's
# containment tier needs a literal substring match, and the missing "g" breaks
# that, so on the live corpus this alone drove setlist.fm+bobdylan.com to
# "agree with each other against Olof" on ~16 early-1960s dates — a source
# spelling convention (audit D15), not a real disagreement. Folded here rather
# than in backend.dossier_fields so the change stays scoped to corroboration.
# Every side uses every form — "Talkin' New York", "Talkin’ …", Olof's spacing
# artifact "Talkin ' New York" and the spelled-out "Talking …" — so the fold runs
# on Olof's titles as well as the sources'.
_TALKIN_RE = re.compile(r"\bTalkin(?:\s*['’]|(?=\s|$))", re.IGNORECASE)
# Olof placeholders for unnamed material ("Unidentified Instrumental", "Harmonica
# Riffs", "Guitar/Vocal riffs"): no source lists them, so they aren't songs here.
_PLACEHOLDER_RE = re.compile(r"^\s*unidentified\b|\briffs?\s*$", re.IGNORECASE)


def _fold_source_conventions(title: str) -> str:
    """Fold known source-spelling conventions that aren't a real disagreement."""
    return _TALKIN_RE.sub("Talking", title)


def _is_placeholder(title: str) -> bool:
    """Whether *title* is a placeholder for unnamed material rather than a song."""
    return bool(_PLACEHOLDER_RE.search(title))


# A source's disagreement with Olof is tolerated up to this many extra/missing
# songs on each side before it counts against "agrees". Set to 1: the matcher
# already resolves spelling/punctuation variants (base/alias/contains tiers),
# so the residual off-by-ones seen on real dates are single stray tracks (an
# encore listed once more on one side, a single misfiled cover) rather than a
# systematic gap — a real truncation or mis-dating produces many more than 1.
_SLACK = 1


class SourceComparison(TypedDict):
    """One source's comparison against a reference setlist.

    Attributes:
        n_songs: Song tracks on the source side (non-songs/tape excluded).
        matched: How many of the reference's songs this source's tracks hit.
        olof_only: Reference songs no source track matched.
        source_only: Source tracks (cleaned) that matched no reference song.
        order_agrees: Whether matched tracks appear in the same relative
            order on both sides, or ``None`` when the source has no usable
            position/order data (TUIT).
        agrees: Same song set after normalisation (:data:`_SLACK` slack) and
            in order where order is known.
    """

    n_songs: int
    matched: int
    olof_only: list[str]
    source_only: list[str]
    order_agrees: bool | None
    agrees: bool


class Quorum(TypedDict, total=False):
    """Result of :func:`setlist_quorum` / one date's :func:`corroborate_all` yield.

    Attributes:
        verdict: 'corroborated' | 'disputed' | 'stated' | 'unavailable'.
        sources: Per-source name -> :class:`SourceComparison`, or ``None``
            when that source has no data for the date.
        disputed_sources: Present only when ``verdict == 'disputed'``: the
            two source names that agree with each other against Olof.
        disputed_song_count: Present only when disputed: the agreeing
            sources' shared song count.
    """

    verdict: str
    sources: dict[str, SourceComparison | None]
    disputed_sources: list[str]
    disputed_song_count: int


def _is_concert_row(event_type: str | None, tour_name: str | None) -> bool:
    """Whether an olof_events row is a concert per ``_CONCERT_TYPE_FILTER``."""
    et = event_type or ""
    is_concert = et == "concert" or et.startswith("concert - ")
    return is_concert and "ehearsal" not in (tour_name or "")


def load_canonical_map(conn: sqlite3.Connection) -> dict[str, str]:
    """Best-effort ``song_canonical`` alias map; ``{}`` if the table is missing."""
    from backend.song_index import _load_song_canonical_map

    try:
        return _load_song_canonical_map(conn)
    except sqlite3.OperationalError:
        return {}


def _clean_song_titles(raw_titles: Iterable[str]) -> list[str]:
    """Clean a list of raw titles, dropping non-songs; keep original when unrecognised."""
    out = []
    for raw in raw_titles:
        title = clean_track_title(raw)
        if title is None:
            title = (raw or "").strip()
            if not title or is_non_song(title):
                continue
        if _is_placeholder(title):
            continue
        out.append(_fold_source_conventions(title))
    return out


def _compare(
    reference_titles: list[str],
    reference_index: SetlistIndex,
    candidate_titles: list[str],
    order_known: bool,
    canonical_map: dict[str, str],
) -> SourceComparison:
    """Compare *candidate_titles* against a reference setlist and its index.

    Args:
        reference_titles: The reference's song titles, in order.
        reference_index: :func:`build_setlist_index` over ``reference_titles``.
        candidate_titles: The other side's raw track titles, in source order.
        order_known: Whether ``candidate_titles`` carries a real running order
            (False for TUIT — see the module docstring).
        canonical_map: ``song_canonical`` alias map.

    Returns:
        A :class:`SourceComparison`.
    """
    idx_of = {cand: i for i, cand in enumerate(reference_index.titles)}
    matched_positions: list[int] = []
    source_only: list[str] = []
    hit: set[int] = set()
    song_titles = _clean_song_titles(candidate_titles)
    for title in song_titles:
        m = match_track(title, reference_index, canonical_map)
        if m is None:
            source_only.append(title)
            continue
        i = idx_of[m["candidate"]]
        matched_positions.append(i)
        hit.add(i)
    olof_only = [reference_titles[i] for i in range(len(reference_titles)) if i not in hit]
    order_agrees = matched_positions == sorted(matched_positions) if order_known else None
    agrees = (
        len(olof_only) <= _SLACK
        and len(source_only) <= _SLACK
        and order_agrees is not False
    )
    return SourceComparison(
        n_songs=len(song_titles),
        matched=len(hit),
        olof_only=olof_only,
        source_only=source_only,
        order_agrees=order_agrees,
        agrees=agrees,
    )


def _best_group(
    groups: dict[str, list[str]], reference_index: SetlistIndex, canonical_map: dict[str, str],
) -> list[str]:
    """Pick the group (setlistfm_id / bobdylan_url / tuit show_id) that best fits Olof.

    A date with several documented shows (early/late) leaves more than one group;
    the one with the most tracks matching the reference setlist is used, ties
    broken by sort order of the key for determinism.

    Args:
        groups: ``{source key: [raw track titles]}`` for one date.
        reference_index: The Olof setlist index to score against.
        canonical_map: ``song_canonical`` alias map.

    Returns:
        The winning group's track titles.
    """
    if len(groups) == 1:
        return next(iter(groups.values()))
    best_titles: list[str] = []
    best_score = -1
    for key in sorted(groups):
        titles = groups[key]
        score = sum(
            1 for t in _clean_song_titles(titles)
            if match_track(t, reference_index, canonical_map) is not None
        )
        if score > best_score:
            best_titles, best_score = titles, score
    return best_titles


def _sources_agree(
    titles_a: list[str], order_known_a: bool,
    titles_b: list[str], order_known_b: bool,
    canonical_map: dict[str, str],
) -> bool:
    """Whether two external sources' setlists agree with each other (order/set)."""
    clean_a = _clean_song_titles(titles_a)
    if not clean_a:
        return False
    index_a = build_setlist_index(clean_a, canonical_map)
    order_known = order_known_a and order_known_b
    return _compare(clean_a, index_a, titles_b, order_known, canonical_map)["agrees"]


def quorum_verdict(
    olof_titles: list[str],
    sources: dict[str, tuple[dict[str, list[str]], bool]],
    canonical_map: dict[str, str],
) -> Quorum:
    """Core corroboration logic shared by :func:`setlist_quorum` and :func:`corroborate_all`.

    Args:
        olof_titles: Olof's ordered song titles for the date's primary event
            (already non-song-filtered), or ``[]`` when Olof has none.
        sources: ``{source name: (groups, order_known)}``; ``groups`` is
            ``{group key: [raw track titles]}`` (empty dict when the source
            has no rows for the date).
        canonical_map: ``song_canonical`` alias map.

    Returns:
        A :class:`Quorum`. Verdict priority is 'disputed' (independent
        sources contradicting Olof but agreeing with each other) over
        'corroborated' (>=1 source agrees with Olof) over 'stated' (Olof has
        songs and neither condition holds) over 'unavailable' (nobody —
        neither Olof nor any source — has a setlist for the date). An Olof
        page with zero songs still runs the full comparison when a source
        has data: if two sources agree on a setlist Olof doesn't have, that's
        'disputed', not 'unavailable' (plan Phase 3 acceptance note — a
        0-song pre-Phase-1 Olof page reads 'disputed' against a 22-song
        bobdylan.com/TUIT agreement on 1975-12-08, proving the check works).
    """
    olof_titles = [_fold_source_conventions(t) for t in olof_titles if not _is_placeholder(t)]
    if not olof_titles and not any(groups for groups, _ in sources.values()):
        return Quorum(verdict="unavailable", sources={name: None for name in sources})

    olof_index = build_setlist_index(olof_titles, canonical_map)
    detail: dict[str, SourceComparison | None] = {}
    titles_by_source: dict[str, tuple[list[str], bool]] = {}
    for name, (groups, order_known) in sources.items():
        if not groups:
            detail[name] = None
            continue
        titles = _best_group(groups, olof_index, canonical_map)
        titles_by_source[name] = (titles, order_known)
        detail[name] = _compare(olof_titles, olof_index, titles, order_known, canonical_map)

    agreeing = [n for n in titles_by_source if detail[n] and detail[n]["agrees"]]
    disagreeing = [n for n in titles_by_source if not (detail[n] and detail[n]["agrees"])]

    disputed_pair: tuple[str, str] | None = None
    for i in range(len(disagreeing)):
        for j in range(i + 1, len(disagreeing)):
            a, b = disagreeing[i], disagreeing[j]
            ta, oa = titles_by_source[a]
            tb, ob = titles_by_source[b]
            if _sources_agree(ta, oa, tb, ob, canonical_map):
                disputed_pair = (a, b)
                break
        if disputed_pair:
            break

    result: Quorum
    if disputed_pair:
        a, _b = disputed_pair
        result = Quorum(
            verdict="disputed", sources=detail,
            disputed_sources=list(disputed_pair),
            disputed_song_count=len(_clean_song_titles(titles_by_source[a][0])),
        )
    elif agreeing:
        result = Quorum(verdict="corroborated", sources=detail)
    else:
        result = Quorum(verdict="stated", sources=detail)
    return result


def is_order_only_dispute(quorum: Quorum) -> bool:
    """Whether a 'disputed' verdict rests on running order alone, not on content.

    True when both disputing sources hold Olof's song set within :data:`_SLACK`
    on each side — so the disagreement is a reordering (e.g. 1979-11-09's
    Slow Train / Precious Angel swap), not missing or extra songs.

    Args:
        quorum: A :class:`Quorum`.

    Returns:
        False for any verdict other than 'disputed'.
    """
    if quorum.get("verdict") != "disputed":
        return False
    for name in quorum["disputed_sources"]:
        comp = quorum["sources"].get(name)
        if not comp or len(comp["olof_only"]) > _SLACK or len(comp["source_only"]) > _SLACK:
            return False
    return True


def primary_event_id(conn: sqlite3.Connection, date_iso: str) -> int | None:
    """The ``olof_events.event_id`` :func:`setlist_quorum` used for *date_iso*.

    Mirrors ``backend.dossier._primary_event``'s no-``prefer_venue`` path: a
    concert-type event (excluding rehearsals) if one exists for the date, else
    any event for the date, the lowest ``event_id`` breaking ties. Public so
    R-O4 (:func:`backend.qc.rules.rule_o4`) can key its findings the way R-O1
    does, without re-deriving the pick.

    Args:
        conn: Open SQLite connection.
        date_iso: ISO ``YYYY-MM-DD`` date.

    Returns:
        The event id, or ``None`` if the date has no ``olof_events`` row.
    """
    rows = conn.execute(
        "SELECT event_id, event_type, tour_name FROM olof_events WHERE date_str = ?",
        (date_iso,),
    ).fetchall()
    if not rows:
        return None
    concerts = [r for r in rows if _is_concert_row(r["event_type"], r["tour_name"])]
    pool = concerts or rows
    return min(pool, key=lambda r: r["event_id"])["event_id"]


def _primary_event_titles(conn: sqlite3.Connection, date_iso: str) -> list[str]:
    """Olof's non-song-filtered song titles for *date_iso*'s primary concert event."""
    event_id = primary_event_id(conn, date_iso)
    if event_id is None:
        return []
    songs = conn.execute(
        "SELECT song_title FROM olof_songs WHERE event_id = ? ORDER BY position", (event_id,),
    ).fetchall()
    titles = [(r["song_title"] or "").strip() for r in songs]
    return [t for t in titles if t and not is_non_song(t)]


def setlist_quorum(
    conn: sqlite3.Connection, date_iso: str, canonical_map: dict[str, str] | None = None,
) -> Quorum:
    """Cross-source setlist corroboration for one date (plan Phase 3 row (a)).

    Args:
        conn: Open SQLite connection.
        date_iso: ISO ``YYYY-MM-DD`` date.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map (saves
            a query when called in a loop); loaded from *conn* if omitted.

    Returns:
        A :class:`Quorum` — see :func:`quorum_verdict`.
    """
    cmap = canonical_map if canonical_map is not None else load_canonical_map(conn)
    olof_titles = _primary_event_titles(conn, date_iso)

    sfm_rows = conn.execute(
        "SELECT l.setlistfm_id, l.track_name FROM setlistfm_setlist l"
        " JOIN setlistfm_shows s USING (setlistfm_id)"
        " WHERE s.date_str = ? AND COALESCE(l.is_tape, 0) = 0"
        " ORDER BY l.setlistfm_id, l.set_index, l.position",
        (date_iso,),
    ).fetchall()
    sfm_groups: dict[str, list[str]] = defaultdict(list)
    for r in sfm_rows:
        sfm_groups[r["setlistfm_id"]].append(r["track_name"])

    bd_rows = conn.execute(
        "SELECT l.bobdylan_url, l.track_name FROM bobdylan_setlist l"
        " JOIN bobdylan_shows s USING (bobdylan_url)"
        " WHERE s.date_str = ? ORDER BY l.bobdylan_url, l.position",
        (date_iso,),
    ).fetchall()
    bd_groups: dict[str, list[str]] = defaultdict(list)
    for r in bd_rows:
        bd_groups[r["bobdylan_url"]].append(r["track_name"])

    tuit_rows = conn.execute(
        "SELECT show_id, song FROM tuit_song_performances WHERE date_str = ? ORDER BY id",
        (date_iso,),
    ).fetchall()
    tuit_groups: dict[str, list[str]] = defaultdict(list)
    for r in tuit_rows:
        tuit_groups[str(r["show_id"])].append(r["song"])

    sources = {
        "setlistfm": (dict(sfm_groups), True),
        "bobdylan": (dict(bd_groups), True),
        "tuit": (dict(tuit_groups), False),
    }
    return quorum_verdict(olof_titles, sources, cmap)


def corroborate_all(conn: sqlite3.Connection) -> Iterator[tuple[str, Quorum]]:
    """Corpus-wide setlist corroboration, one preload pass per source table.

    Used by R-O4 (:func:`backend.qc.rules.rule_o4`) so a full corpus run stays
    fast: each of ``olof_events``/``olof_songs``, ``setlistfm_setlist``,
    ``bobdylan_setlist`` and ``tuit_song_performances`` is read once and
    grouped by date in Python, instead of :func:`setlist_quorum`'s per-date
    queries. Shares :func:`quorum_verdict` with :func:`setlist_quorum` so the
    two never drift apart.

    Args:
        conn: Open SQLite connection.

    Yields:
        ``(date_iso, Quorum)`` for every date with an Olof setlist.
    """
    cmap = load_canonical_map(conn)

    ev_rows = conn.execute(
        "SELECT event_id, date_str, event_type, tour_name FROM olof_events"
        " WHERE date_str != ''"
    ).fetchall()
    events_by_date: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in ev_rows:
        events_by_date[r["date_str"]].append(r)
    primary_event_id_by_date: dict[str, int] = {}
    for date_str, rows in events_by_date.items():
        concerts = [r for r in rows if _is_concert_row(r["event_type"], r["tour_name"])]
        pool = concerts or rows
        primary_event_id_by_date[date_str] = min(pool, key=lambda r: r["event_id"])["event_id"]

    song_rows = conn.execute(
        "SELECT event_id, song_title FROM olof_songs ORDER BY event_id, position"
    ).fetchall()
    songs_by_event: dict[int, list[str]] = defaultdict(list)
    for r in song_rows:
        title = (r["song_title"] or "").strip()
        if title:
            songs_by_event[r["event_id"]].append(title)

    olof_by_date: dict[str, list[str]] = {}
    for date_str, event_id in primary_event_id_by_date.items():
        titles = [t for t in songs_by_event.get(event_id, []) if not is_non_song(t)]
        olof_by_date[date_str] = titles

    sfm_rows = conn.execute(
        "SELECT s.date_str, l.setlistfm_id, l.track_name FROM setlistfm_setlist l"
        " JOIN setlistfm_shows s USING (setlistfm_id)"
        " WHERE COALESCE(l.is_tape, 0) = 0"
        " ORDER BY s.date_str, l.setlistfm_id, l.set_index, l.position"
    ).fetchall()
    sfm_by_date: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in sfm_rows:
        sfm_by_date[r["date_str"]][r["setlistfm_id"]].append(r["track_name"])

    bd_rows = conn.execute(
        "SELECT s.date_str, l.bobdylan_url, l.track_name FROM bobdylan_setlist l"
        " JOIN bobdylan_shows s USING (bobdylan_url)"
        " ORDER BY s.date_str, l.bobdylan_url, l.position"
    ).fetchall()
    bd_by_date: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in bd_rows:
        bd_by_date[r["date_str"]][r["bobdylan_url"]].append(r["track_name"])

    tuit_rows = conn.execute(
        "SELECT date_str, show_id, song FROM tuit_song_performances ORDER BY date_str, id"
    ).fetchall()
    tuit_by_date: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in tuit_rows:
        tuit_by_date[r["date_str"]][str(r["show_id"])].append(r["song"])

    for date_str, olof_titles in olof_by_date.items():
        sources = {
            "setlistfm": (dict(sfm_by_date.get(date_str, {})), True),
            "bobdylan": (dict(bd_by_date.get(date_str, {})), True),
            "tuit": (dict(tuit_by_date.get(date_str, {})), False),
        }
        yield date_str, quorum_verdict(olof_titles, sources, cmap)
