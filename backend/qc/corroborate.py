"""Cross-source setlist corroboration (TODO-342 Phase 3a/3b/3c, audit Q1-a/b/c, plan R-O4).

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

C15 (Phase 3 rows (b) and (c), audit Q1-b/c, P10) extends this module with
three more on-the-fly checks — no new tables, no new QC rule:

- :func:`tour_premieres` — per-song tour-premiere agreement (plan D-02 gate
  item 2) between our corpus (``song_performances`` joined to
  ``olof_events``, the D-02 source) and setlist.fm's own tour grouping.
- :func:`rotation_check` — recomputes "songs not played at the previous
  concert" from our corpus and compares it against Olof's stated
  ``rotation_new``/``rotation_pct`` (plan D-04, audit hole P5). Definition
  learned from the live 2010 Zepp Tokyo run (2010-03-29: stated 13/72%):
  the previous concert is the immediately preceding ``olof_events`` row
  under :data:`_CONCERT_TYPE_FILTER` ordered by ``(date_str, event_id)`` —
  *not* scoped to the same tour or venue run — ``rotation_new`` is this
  show's song count (``song_performances.song_norm``) absent from that
  show's song set, and ``rotation_pct`` is ``floor(rotation_new / n_songs *
  100)``. Verified exactly on the 7-night Zepp Tokyo run (52, 52, 58, 64,
  70, 52, 72) and at 87.3% corpus-wide (close to the audit's cited ~86%;
  the gap is mostly 1974 shows where ``song_performances`` has far fewer
  rows than Olof's stated song count, i.e. thin/placeholder listings, not a
  formula mismatch).
- :func:`tracklist_check` — LB-site ``entries.setlist`` (via
  :func:`backend.dossier_fields.parse_entry_tracklist`) vs TUIT
  ``tuit_recordings.setlist_json`` for the same ``lb_number`` (audit P10).
"""
from __future__ import annotations

import json
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
    parse_entry_tracklist,
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


# ---------------------------------------------------------------------------
# 3b — tour premieres (plan Phase 3 row (b), D-02 gate item 2)
# ---------------------------------------------------------------------------


class PremiereSong(TypedDict):
    """One event position's tour-premiere agreement.

    Attributes:
        position: 1-based position in the event's song list.
        song: Display title (``song_performances.song_canonical``).
        ours: Whether our corpus has no earlier performance of this song in
            the same ``tour_name`` (the D-02 source).
        setlistfm: Same question answered from setlist.fm's own tour
            grouping, or ``None`` when setlist.fm has no data for this show
            or doesn't list this song (source has no data / song unmatched).
        agrees: ``ours == setlistfm``, or ``None`` when ``setlistfm`` is ``None``.
    """

    position: int
    song: str
    ours: bool
    setlistfm: bool | None
    agrees: bool | None


class TourPremieres(TypedDict):
    """Result of :func:`tour_premieres`.

    Attributes:
        event_id: The event checked.
        tour_name: ``olof_events.tour_name`` for the event.
        tour_new_count: Olof's stated premiere count for the event, or ``None``.
        premiere_count: Our computed premiere count (``sum(ours)``).
        premiere_count_matches: Whether ``premiere_count == tour_new_count``,
            or ``None`` when ``tour_new_count`` is ``None``.
        songs: One :class:`PremiereSong` per position.
    """

    event_id: int
    tour_name: str
    tour_new_count: int | None
    premiere_count: int
    premiere_count_matches: bool | None
    songs: list[PremiereSong]


def _event_song_rows(conn: sqlite3.Connection, event_id: int) -> list[sqlite3.Row]:
    """This event's ``song_performances`` rows, in position order."""
    return conn.execute(
        "SELECT position, song_norm, song_canonical FROM song_performances"
        " WHERE event_id = ? ORDER BY position",
        (event_id,),
    ).fetchall()


def _tour_song_history(
    conn: sqlite3.Connection, tour_name: str, before_date: str, before_event_id: int,
) -> set[str]:
    """``song_norm`` set performed earlier in *tour_name*, strictly before this event.

    One query, scoped to the tour — not a whole-corpus scan — so this stays
    cheap for a per-dossier call.
    """
    oe_filter = _CONCERT_TYPE_FILTER.replace("event_type", "oe.event_type").replace(
        "tour_name", "oe.tour_name"
    )
    rows = conn.execute(
        "SELECT DISTINCT sp.song_norm FROM song_performances sp"
        " JOIN olof_events oe ON oe.event_id = sp.event_id"
        f" WHERE oe.tour_name = ? AND {oe_filter} AND oe.date_str != ''"
        " AND (oe.date_str < ? OR (oe.date_str = ? AND sp.event_id < ?))",
        (tour_name, before_date, before_date, before_event_id),
    ).fetchall()
    return {r["song_norm"] for r in rows}


def _setlistfm_groups_for_date(
    conn: sqlite3.Connection, date_iso: str,
) -> dict[str, list[str]]:
    """setlist.fm track groups (``{setlistfm_id: [track_name, ...]}``) for *date_iso*."""
    rows = conn.execute(
        "SELECT l.setlistfm_id, l.track_name FROM setlistfm_setlist l"
        " JOIN setlistfm_shows s USING (setlistfm_id)"
        " WHERE s.date_str = ? AND COALESCE(l.is_tape, 0) = 0"
        " ORDER BY l.setlistfm_id, l.set_index, l.position",
        (date_iso,),
    ).fetchall()
    groups: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        groups[r["setlistfm_id"]].append(r["track_name"])
    return dict(groups)


def _best_setlistfm_id(
    groups: dict[str, list[str]], reference_index: SetlistIndex, canonical_map: dict[str, str],
) -> str | None:
    """The ``setlistfm_id`` whose tracks best match *reference_index* (see :func:`_best_group`)."""
    if not groups:
        return None
    if len(groups) == 1:
        return next(iter(groups))
    best_id: str | None = None
    best_score = -1
    for key in sorted(groups):
        score = sum(
            1 for t in _clean_song_titles(groups[key])
            if match_track(t, reference_index, canonical_map) is not None
        )
        if score > best_score:
            best_id, best_score = key, score
    return best_id


def tour_premieres(
    conn: sqlite3.Connection, event_id: int, canonical_map: dict[str, str] | None = None,
) -> TourPremieres:
    """Per-song tour-premiere agreement between our corpus and setlist.fm.

    Plan Phase 3 row (b) / D-02 gate item 2: a per-song badge needs the
    computed premiere count to equal ``olof_events.tour_new_count`` (gate
    item 1, checked by the caller) *and* each badged song to also read as a
    tour premiere on an independent source — here, setlist.fm, using
    setlist.fm's *own* ``tour_name`` for the show (it rarely matches Olof's),
    not Olof's.

    Args:
        conn: Open SQLite connection.
        event_id: ``olof_events.event_id`` to check.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map (saves
            a query when called in a loop); loaded from *conn* if omitted.

    Returns:
        A :class:`TourPremieres`. ``songs`` is ``[]`` when the event has no
        ``song_performances`` rows (not yet recomputed, or a non-song event).
    """
    ev = conn.execute(
        "SELECT tour_name, date_str, tour_new_count FROM olof_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if ev is None:
        return TourPremieres(
            event_id=event_id, tour_name="", tour_new_count=None,
            premiere_count=0, premiere_count_matches=None, songs=[],
        )
    tour_name, date_str, tour_new_count = ev["tour_name"], ev["date_str"], ev["tour_new_count"]

    song_rows = _event_song_rows(conn, event_id)
    if not song_rows:
        return TourPremieres(
            event_id=event_id, tour_name=tour_name, tour_new_count=tour_new_count,
            premiere_count=0, premiere_count_matches=None, songs=[],
        )

    cmap = canonical_map if canonical_map is not None else load_canonical_map(conn)
    history = _tour_song_history(conn, tour_name, date_str, event_id) if tour_name else set()

    reference_index = build_setlist_index([r["song_canonical"] for r in song_rows], cmap)
    sfm_groups = _setlistfm_groups_for_date(conn, date_str) if date_str else {}
    sfm_id = _best_setlistfm_id(sfm_groups, reference_index, cmap)

    current_index: SetlistIndex | None = None
    earlier_index: SetlistIndex | None = None
    if sfm_id is not None:
        current_titles = _clean_song_titles(sfm_groups[sfm_id])
        current_index = build_setlist_index(current_titles, cmap)
        sfm_tour = conn.execute(
            "SELECT tour_name FROM setlistfm_shows WHERE setlistfm_id = ?", (sfm_id,),
        ).fetchone()
        sfm_tour_name = (sfm_tour["tour_name"] or "") if sfm_tour else ""
        earlier_titles: list[str] = []
        if sfm_tour_name:
            # DISTINCT: a long-running tour (e.g. "Never Ending Tour" spans decades)
            # can carry tens of thousands of prior track rows but only a few hundred
            # distinct titles — dedupe before the Python-side clean/index work.
            earlier_rows = conn.execute(
                "SELECT DISTINCT l.track_name FROM setlistfm_setlist l"
                " JOIN setlistfm_shows s USING (setlistfm_id)"
                " WHERE s.tour_name = ? AND s.date_str != '' AND s.date_str < ?"
                " AND COALESCE(l.is_tape, 0) = 0",
                (sfm_tour_name, date_str),
            ).fetchall()
            earlier_titles = _clean_song_titles(r["track_name"] for r in earlier_rows)
        earlier_index = build_setlist_index(earlier_titles, cmap)

    songs: list[PremiereSong] = []
    premiere_count = 0
    for r in song_rows:
        ours = r["song_norm"] not in history
        if ours:
            premiere_count += 1
        setlistfm: bool | None = None
        if current_index is not None and earlier_index is not None:
            now_match = match_track(r["song_canonical"], current_index, cmap)
            if now_match is not None:
                setlistfm = match_track(r["song_canonical"], earlier_index, cmap) is None
        agrees = None if setlistfm is None else (ours == setlistfm)
        songs.append(PremiereSong(
            position=r["position"], song=r["song_canonical"],
            ours=ours, setlistfm=setlistfm, agrees=agrees,
        ))

    matches = None if tour_new_count is None else (premiere_count == tour_new_count)
    return TourPremieres(
        event_id=event_id, tour_name=tour_name, tour_new_count=tour_new_count,
        premiere_count=premiere_count, premiere_count_matches=matches, songs=songs,
    )


# ---------------------------------------------------------------------------
# 3b — rotation (plan Phase 3 row (b), D-04, audit hole P5)
# ---------------------------------------------------------------------------


class RotationCheck(TypedDict):
    """Result of :func:`rotation_check`.

    Attributes:
        event_id: The event checked.
        previous_event_id: The previous concert event used for the recompute,
            or ``None`` when there isn't one.
        olof_new: Olof's stated ``rotation_new``, or ``None``.
        olof_pct: Olof's stated ``rotation_pct``, or ``None``.
        ours_new: Our recomputed count of songs absent from the previous
            concert, or ``None`` when there's no previous concert or no
            ``song_performances`` rows for this event.
        ours_pct: ``floor(ours_new / n_songs * 100)``, or ``None``.
        agrees: ``(ours_new, ours_pct) == (olof_new, olof_pct)``, or ``None``
            when Olof has no stated stat or we couldn't recompute.
    """

    event_id: int
    previous_event_id: int | None
    olof_new: int | None
    olof_pct: int | None
    ours_new: int | None
    ours_pct: int | None
    agrees: bool | None


def _previous_concert_event_id(
    conn: sqlite3.Connection, event_id: int, date_str: str,
) -> int | None:
    """The immediately preceding concert event by ``(date_str, event_id)`` order."""
    row = conn.execute(
        f"SELECT event_id FROM olof_events WHERE {_CONCERT_TYPE_FILTER} AND date_str != ''"
        " AND (date_str < ? OR (date_str = ? AND event_id < ?))"
        " ORDER BY date_str DESC, event_id DESC LIMIT 1",
        (date_str, date_str, event_id),
    ).fetchone()
    return row["event_id"] if row else None


def _recompute_rotation(
    cur_song_norms: list[str], prev_song_norms: Iterable[str],
) -> tuple[int, int] | tuple[None, None]:
    """``(new_count, pct)`` for *cur_song_norms* against *prev_song_norms*, floor rounding."""
    if not cur_song_norms:
        return None, None
    prev_set = set(prev_song_norms)
    new_count = sum(1 for s in cur_song_norms if s not in prev_set)
    pct = int(new_count / len(cur_song_norms) * 100)
    return new_count, pct


def rotation_check(conn: sqlite3.Connection, event_id: int) -> RotationCheck:
    """Recompute "songs not played at the previous concert" and compare to Olof's stat.

    Definition (learned from the live 2010-03-29 case, see the module
    docstring): the previous concert is the immediately preceding
    ``olof_events`` row under :data:`_CONCERT_TYPE_FILTER`, ordered by
    ``(date_str, event_id)`` — regardless of tour or venue. ``rotation_new``
    is this show's song count absent from that show; ``rotation_pct`` is
    ``floor(rotation_new / n_songs * 100)``.

    Args:
        conn: Open SQLite connection.
        event_id: ``olof_events.event_id`` to check.

    Returns:
        A :class:`RotationCheck`.
    """
    ev = conn.execute(
        "SELECT date_str, rotation_new, rotation_pct FROM olof_events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    if ev is None:
        return RotationCheck(
            event_id=event_id, previous_event_id=None, olof_new=None, olof_pct=None,
            ours_new=None, ours_pct=None, agrees=None,
        )
    olof_new, olof_pct = ev["rotation_new"], ev["rotation_pct"]

    cur_song_norms = [r["song_norm"] for r in _event_song_rows(conn, event_id)]
    prev_event_id = _previous_concert_event_id(conn, event_id, ev["date_str"])
    ours_new: int | None
    ours_pct: int | None
    if prev_event_id is None:
        ours_new = ours_pct = None
    else:
        prev_song_norms = [r["song_norm"] for r in _event_song_rows(conn, prev_event_id)]
        ours_new, ours_pct = _recompute_rotation(cur_song_norms, prev_song_norms)

    agrees = None
    if olof_new is not None and ours_new is not None:
        agrees = (ours_new, ours_pct) == (olof_new, olof_pct)

    return RotationCheck(
        event_id=event_id, previous_event_id=prev_event_id,
        olof_new=olof_new, olof_pct=olof_pct, ours_new=ours_new, ours_pct=ours_pct,
        agrees=agrees,
    )


def rotation_corpus_agreement(conn: sqlite3.Connection) -> dict[str, int | float]:
    """Corpus-wide agreement rate between Olof's stated rotation stat and our recompute.

    One pass over ``olof_events``/``song_performances`` (preloaded, not
    per-event queries) over every concert event with a stated
    ``rotation_new``.

    Args:
        conn: Open SQLite connection.

    Returns:
        ``{"total": stated event count, "agree": agreeing count, "rate": share}``.
    """
    rows = conn.execute(
        f"SELECT event_id, date_str, rotation_new, rotation_pct FROM olof_events"
        f" WHERE date_str != '' AND {_CONCERT_TYPE_FILTER} ORDER BY date_str, event_id"
    ).fetchall()
    song_rows = conn.execute(
        "SELECT event_id, song_norm FROM song_performances ORDER BY event_id, position"
    ).fetchall()
    songs_by_event: dict[int, list[str]] = defaultdict(list)
    for r in song_rows:
        songs_by_event[r["event_id"]].append(r["song_norm"])

    total = 0
    agree = 0
    prev_event_id: int | None = None
    for r in rows:
        cur = songs_by_event.get(r["event_id"], [])
        if prev_event_id is not None and r["rotation_new"] is not None and cur:
            ours_new, ours_pct = _recompute_rotation(cur, songs_by_event.get(prev_event_id, []))
            total += 1
            if (ours_new, ours_pct) == (r["rotation_new"], r["rotation_pct"]):
                agree += 1
        prev_event_id = r["event_id"]

    return {"total": total, "agree": agree, "rate": (agree / total) if total else 0.0}


# ---------------------------------------------------------------------------
# 3c — source tracklist (plan Phase 3 row (c), audit P10, D-01 confidence)
# ---------------------------------------------------------------------------


class TracklistCheck(TypedDict):
    """Result of :func:`tracklist_check`.

    Attributes:
        lb_number: The LB entry checked.
        lb_songs: LB-site song tracks (:func:`~backend.dossier_fields.parse_entry_tracklist`,
            song tracks only, missing excluded).
        tuit_songs: TUIT's ``setlist_json`` song titles, or ``None`` when TUIT
            has no ``setlist_json`` row for this ``lb_number``.
        matched: How many ``lb_songs`` a TUIT track hit (0 when ``tuit_songs`` is ``None``).
        lb_only: ``lb_songs`` no TUIT track matched.
        tuit_only: TUIT tracks (cleaned) that matched no ``lb_songs`` entry.
        agrees: Same present-count (within the C14 :data:`_SLACK`) and set
            agreement, or ``None`` when ``tuit_songs`` is ``None``.
    """

    lb_number: int
    lb_songs: list[str]
    tuit_songs: list[str] | None
    matched: int
    lb_only: list[str]
    tuit_only: list[str]
    agrees: bool | None


def _tuit_setlist_titles(conn: sqlite3.Connection, lb_number: int) -> list[str] | None:
    """Raw song titles from ``tuit_recordings.setlist_json`` for *lb_number*, or ``None``."""
    row = conn.execute(
        "SELECT setlist_json FROM tuit_recordings WHERE lb_number = ?"
        " AND setlist_json IS NOT NULL AND setlist_json != '' LIMIT 1",
        (lb_number,),
    ).fetchone()
    if row is None:
        return None
    try:
        items = json.loads(row["setlist_json"])
    except (TypeError, ValueError):
        _log.warning("tuit_recordings.setlist_json unparsable for lb_number=%s", lb_number)
        return None
    return [x.get("song", "") for x in items if isinstance(x, dict) and x.get("song")]


def _tracklist_compare(
    lb_songs: list[str], tuit_titles_raw: list[str], canonical_map: dict[str, str],
) -> SourceComparison:
    """Compare TUIT's raw titles against *lb_songs* (order not asserted, per audit P10)."""
    reference_index = build_setlist_index(lb_songs, canonical_map)
    return _compare(lb_songs, reference_index, tuit_titles_raw, False, canonical_map)


def tracklist_check(
    conn: sqlite3.Connection, lb_number: int, canonical_map: dict[str, str] | None = None,
) -> TracklistCheck:
    """LB-site tracklist vs TUIT ``setlist_json`` for the same ``lb_number`` (audit P10).

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number`` to check.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map (saves
            a query when called in a loop); loaded from *conn* if omitted.

    Returns:
        A :class:`TracklistCheck`.
    """
    row = conn.execute(
        "SELECT setlist FROM entries WHERE lb_number = ?", (lb_number,),
    ).fetchone()
    entry_setlist = row["setlist"] if row else None
    lb_songs = [
        t["title"] for t in parse_entry_tracklist(entry_setlist)
        if t["is_song"] and not t["missing"]
    ]

    tuit_titles_raw = _tuit_setlist_titles(conn, lb_number)
    if tuit_titles_raw is None:
        return TracklistCheck(
            lb_number=lb_number, lb_songs=lb_songs, tuit_songs=None,
            matched=0, lb_only=list(lb_songs), tuit_only=[], agrees=None,
        )

    cmap = canonical_map if canonical_map is not None else load_canonical_map(conn)
    comp = _tracklist_compare(lb_songs, tuit_titles_raw, cmap)
    return TracklistCheck(
        lb_number=lb_number, lb_songs=lb_songs, tuit_songs=_clean_song_titles(tuit_titles_raw),
        matched=comp["matched"], lb_only=comp["olof_only"], tuit_only=comp["source_only"],
        agrees=comp["agrees"],
    )


def tracklist_corpus_agreement(conn: sqlite3.Connection) -> dict[str, int | float]:
    """Corpus-wide LB-vs-TUIT tracklist agreement rate (audit P10).

    One preload pass over ``entries``/``tuit_recordings`` rather than one
    query pair per LB.

    Args:
        conn: Open SQLite connection.

    Returns:
        ``{"total": LBs with both sources, "agree": agreeing count, "rate": share}``.
    """
    cmap = load_canonical_map(conn)
    entry_rows = conn.execute(
        "SELECT lb_number, setlist FROM entries WHERE setlist IS NOT NULL AND setlist != ''"
    ).fetchall()
    tuit_rows = conn.execute(
        "SELECT lb_number, setlist_json FROM tuit_recordings WHERE lb_number IS NOT NULL"
        " AND setlist_json IS NOT NULL AND setlist_json != ''"
    ).fetchall()
    tuit_by_lb: dict[int, str] = {}
    for r in tuit_rows:
        tuit_by_lb.setdefault(r["lb_number"], r["setlist_json"])

    total = 0
    agree = 0
    for r in entry_rows:
        raw_json = tuit_by_lb.get(r["lb_number"])
        if raw_json is None:
            continue
        lb_songs = [
            t["title"] for t in parse_entry_tracklist(r["setlist"])
            if t["is_song"] and not t["missing"]
        ]
        if not lb_songs:
            continue
        try:
            items = json.loads(raw_json)
        except (TypeError, ValueError):
            continue
        tuit_titles_raw = [x.get("song", "") for x in items if isinstance(x, dict) and x.get("song")]
        if not tuit_titles_raw:
            continue
        total += 1
        if _tracklist_compare(lb_songs, tuit_titles_raw, cmap)["agrees"]:
            agree += 1

    return {"total": total, "agree": agree, "rate": (agree / total) if total else 0.0}
