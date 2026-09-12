"""Dossier field requirements (TODO-342 Phase 4) — starting with the D-01 track matcher.

``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md`` "D-01 Per-source completeness" needs a
per-track reading of ``entries.setlist`` (free text, split by
:func:`backend.db.parse_entry_setlist_titles`) and a matcher against Olof's setlist.
This module holds those pieces and :func:`completeness` itself (C17).

- :func:`clean_track_title` strips durations, credit/performance suffixes and
  header fragments the splitter glues onto a title, and returns ``None`` for
  non-songs (intro, applause, band introductions, encore break, tuning, crowd).
- :func:`parse_entry_tracklist` returns one :class:`EntryTrack` per split title,
  flagging partial (``incomplete``/``cut``/``fade``) and missing tracks.
- :func:`match_track` matches one cleaned title against a setlist: exact
  normalized title, then without the subtitle/parenthetical, then via
  ``song_canonical`` aliases, then :func:`backend.db.titles_match` containment.

- :func:`completeness` (D-01) maps each source's song tracks onto one event's
  setlist positions: present / missing / partial, basis, TUIT-corroborated
  confidence, and the G2 source–show fit flag (:func:`fits_show`, shared with
  QC rule R-E2 in ``backend/qc/rules.py``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import statistics
import unicodedata
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from backend.db import normalize_title_for_match, parse_entry_setlist_titles, titles_match
from backend.song_index import normalize_song_title

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

_NUM_WORD = r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|[a-d])"
_ORDINAL = r"(?:first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|early|late)"

# A header the splitter leaves glued to the tail of the preceding title
# ("Honest With Me, Disc 2:", "God Knows\nCD 2", "It Ain't Me Babe, Second
# Broadcast: June 19th 1965", "Love Sick, intermission, set 2"). Only
# recognized after a comma/newline, so a title's own words never trigger it.
_HEADER_BODY = (
    rf"(?:(?:disc|disk|cd|dvd|side|tape|set|show|part)[\s\-]*{_NUM_WORD}\b"
    rf"|{_ORDINAL}\s+(?:show|set|broadcast|concert|part|disc|cd)\b"
    rf"|[\-(]*\s*(?:intermission|encores?)(?:\s+{_NUM_WORD}\b)?\s*[\-)]*\s*(?=,|$)"
    r"|(?:notes?|total\s+time|tracklist|setlist|likely\s+missing|missing)\s*:"
    r")"
)
_GLUED_HEADER_RE = re.compile(rf"[,\n]\s*{_HEADER_BODY}.*\Z", re.IGNORECASE | re.DOTALL)
# The same header at the very start of a title, ended by a colon ("Second Show: Title").
_LEADING_HEADER_RE = re.compile(rf"\A\s*{_HEADER_BODY}[^:\n]*:\s*(?=\S)", re.IGNORECASE)
# A title that is nothing but a header ("Disc 2:", "DISC TWO [62:11]").
_WHOLE_HEADER_RE = re.compile(
    rf"\A\s*{_HEADER_BODY}\s*[:\-]?\s*(?:[\[(][\d:.\s]*[\])])?\s*\Z", re.IGNORECASE
)

# Durations: "[04:32.44]", "(5:21)", bare "6:07", "04:03, 30:21".
_BRACKETED_DURATION_RE = re.compile(r"[\[(]\s*\d{1,3}:\d{2}(?:[.:]\d{1,2})?\s*[\])]")
_BARE_DURATION_RE = re.compile(r"(?<![\w:])\d{1,3}:\d{2}(?:[.:]\d{1,2})?(?![\w:])")
# Square-bracket suffixes carry no title text: "[Petty]", "[Ls]", "[Fade In]".
_BRACKET_RE = re.compile(r"\[[^\]]*\]?")
# Parentheticals that are performance notes, not part of the title.
_NOISE_PAREN_RE = re.compile(
    r"\(\s*(?:live|acoustic|electric|encore|solo|instrumental|\?|w/?\s*band"
    r"|incomplete[^)]*|cuts?\b[^)]*|[^)]*\bcut\b[^)]*|fades?\b[^)]*|faded[^)]*"
    r"|missing[^)]*|[^)]*\bmissing\b[^)]*)\s*\)?",
    re.IGNORECASE,
)
_EDGE_JUNK_LEAD_RE = re.compile(r"\A[\s*/\-#%+.,;:~]+")
_EDGE_JUNK_TRAIL_RE = re.compile(r"[\s*/\-#%+.,;:~]+\Z")
_WS_RE = re.compile(r"\s+")

# Non-song detection: a cleaned title made only of these words, with at least
# one "core" word among them, is not a song ("band introduction", "encore
# break", "audience", "tuning", "crowd noise").
_NON_SONG_CORE = frozenset({
    "intro", "intros", "introduction", "introductions", "applause", "audience",
    "crowd", "encore", "encores", "tuning", "intermission", "clapping", "cheering",
    "cheers", "interview", "conversation", "announcement", "announcements", "silence",
    "flip", "banter", "chatter", "talk", "speech", "fade",
})
_NON_SONG_FILLER = frozenset({
    "band", "member", "members", "musician", "musicians", "of", "the", "and", "to",
    "break", "noise", "up", "tape", "bob", "dylan", "dylans", "by", "mc", "dj",
    "radio", "announcer", "short", "brief", "before", "after", "end", "start", "stage",
    "track", "in", "out", "first", "second", "third", "last", "1st", "2nd", "3rd",
})
# A title that is one whole parenthetical: "(encore break)", "(2nd encore break)".
_WRAPPED_RE = re.compile(r"\s*\((.*)\)\s*", re.DOTALL)
# An intro glued to a song with a slash: "Intro/ Maggie's Farm", "Jolene / Band Intro".
_INTRO_SEGMENT = r"(?:band\s+)?intro(?:duction)?s?"
_SLASH_INTRO_EDGE_RE = re.compile(
    rf"\A\s*{_INTRO_SEGMENT}\s*/+\s*|\s*/+\s*{_INTRO_SEGMENT}\s*\Z", re.IGNORECASE
)
_SLASH_INTRO_MID_RE = re.compile(rf"\s*/+\s*{_INTRO_SEGMENT}\s*/+\s*", re.IGNORECASE)

# Partial-track tags, only inside brackets/parentheses/asterisks or after a comma
# ("(incomplete)", "(beginning cut)", "[Fade In]", ", fade out") — never the bare
# title words, so "Not Fade Away" / "Clean Cut Kid" stay whole.
_PARTIAL_WORDS = (
    r"\b(?:incomplete|truncated|partial|cuts?|cut\s+(?:in|off|out)|fades?|faded"
    r"|fade[\s\-]*(?:in|out)|missing\s+(?:end|intro|beginning|start|first|last|the)\w*)\b"
)
_PARTIAL_RE = re.compile(
    rf"(?:[(\[][^)\]]*{_PARTIAL_WORDS}|\*[^*]*{_PARTIAL_WORDS}|,\s*[^,]*{_PARTIAL_WORDS})",
    re.IGNORECASE,
)
# The whole track is absent from the recording: "Mr Tambourine Man, missing",
# "Soon After Midnight (missing)".
_MISSING_RE = re.compile(r"(?:,\s*|\(\s*|\s+-\s*)missing\s*\)?\s*\Z", re.IGNORECASE)


def _strip_glued_header(text: str) -> str:
    """Drop a header fragment glued onto the tail (or head) of a split title."""
    text = _GLUED_HEADER_RE.sub("", text)
    return _LEADING_HEADER_RE.sub("", text)


def clean_track_title(raw: str | None) -> str | None:
    """Clean one split ``entries.setlist`` title into a matchable song title.

    Drops glued header fragments (``Disc 2:``, ``CD 2``, ``Second Show:``,
    ``First Broadcast: June 26th 1965``), durations (``[04:32.44]``, ``(5:21)``,
    ``04:03, 30:21``), square-bracket suffixes (``[Petty]``), performance-note
    parentheticals (``(Live)``, ``(acoustic)``, ``(incomplete)``) and edge junk
    (a trailing ``*``, leading ``//``). Credit/subtitle parentheticals such as
    ``(I'm Only Bleeding)`` are kept; :func:`match_track` handles them.

    Args:
        raw: One title as returned by :func:`backend.db.parse_entry_setlist_titles`.

    Returns:
        The cleaned title, or ``None`` when nothing song-like remains (empty
        input, a bare header, or a non-song such as intro/applause/band
        introductions/encore break/tuning/crowd).
    """
    if not raw or _WHOLE_HEADER_RE.match(raw):
        return None
    wrapped = _WRAPPED_RE.fullmatch(raw)
    if wrapped and is_non_song(wrapped.group(1)):
        return None
    text = _strip_glued_header(raw)
    text = _MISSING_RE.sub("", text)
    text = _BRACKETED_DURATION_RE.sub(" ", text)
    text = _BRACKET_RE.sub(" ", text)
    text = _BARE_DURATION_RE.sub(" ", text)
    text = _NOISE_PAREN_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).replace(" /", "/")
    text = _EDGE_JUNK_TRAIL_RE.sub("", _EDGE_JUNK_LEAD_RE.sub("", text))
    # Stripping may expose another trailing duration/header ("Title 4:13, Disc 2").
    text = _EDGE_JUNK_TRAIL_RE.sub("", _BARE_DURATION_RE.sub(" ", text)).strip()
    if not text or not any(ch.isalpha() for ch in text):
        return None
    # "Jolene / Band Intro", "Intro/ Maggie's Farm": drop the intro segment only —
    # "Love Minus Zero/No Limit" and dates like "(7/12/87)" stay whole.
    stripped = _SLASH_INTRO_MID_RE.sub("/", _SLASH_INTRO_EDGE_RE.sub("", text)).strip()
    if stripped:
        text = stripped
    if is_non_song(text):
        return None
    return text


def is_non_song(title: str) -> bool:
    """Whether a (cleaned) title is a non-song track such as an intro or applause.

    Args:
        title: Track title text.

    Returns:
        True when every word outside parentheses is non-song vocabulary and at
        least one is a core non-song word (intro, applause, audience, crowd,
        encore, tuning, ...) — so "Audience (Bob - Minasan Arigato)" is a non-song.
    """
    words = normalize_title_for_match(_PAREN_RE.sub(" ", title)).split()
    if not words:
        return True
    if not any(w in _NON_SONG_CORE for w in words):
        return False
    return all(w in _NON_SONG_CORE or w in _NON_SONG_FILLER for w in words)


# ---------------------------------------------------------------------------
# Structured entry tracklist
# ---------------------------------------------------------------------------


class EntryTrack(TypedDict):
    """One track of an entry's tracklist.

    Keys:
        raw: The title text exactly as split from ``entries.setlist``.
        title: Cleaned title (:func:`clean_track_title`), ``None`` for non-songs.
        is_song: Whether this track is a song (``title is not None``).
        partial: Tagged incomplete/cut/fade — present on the recording, but not whole.
        missing: Tagged missing — listed, but not on the recording at all.
    """

    raw: str
    title: str | None
    is_song: bool
    partial: bool
    missing: bool


def parse_entry_tracklist(setlist_text: str | None) -> list[EntryTrack]:
    """Parse an ``entries.setlist`` value into structured per-track records.

    Args:
        setlist_text: Raw ``entries.setlist`` column value.

    Returns:
        One :class:`EntryTrack` per numbered track, in order; ``[]`` for empty input.
    """
    tracks: list[EntryTrack] = []
    for raw in parse_entry_setlist_titles(setlist_text or ""):
        own = _strip_glued_header(raw)  # flags belong to this track, not a glued header
        missing = bool(_MISSING_RE.search(own))
        partial = not missing and bool(_PARTIAL_RE.search(own))
        title = clean_track_title(raw)
        tracks.append(EntryTrack(
            raw=raw, title=title, is_song=title is not None, partial=partial, missing=missing,
        ))
    return tracks


# ---------------------------------------------------------------------------
# Matching against a setlist
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"\([^)]*\)?")
# "Rainy Day Women Nos. 12 & 35" vs Olof "Rainy Day Women # 12 & 35".
_NUMBER_WORD_RE = re.compile(r"\b(?:nos?|number)\s+(?=\d)")


# "T.V. Talkin' Song" vs "T.V. Talking Song": sources split on the dropped g.
_TALKIN_RE = re.compile(r"\bTalkin(?:\s*['’]|(?=\s|$))", re.IGNORECASE)


def _base(title: str) -> str:
    """Title without parentheticals or a ':'/' - ' subtitle, normalized for matching."""
    text = _PAREN_RE.sub(" ", _TALKIN_RE.sub("Talking", title))
    text = re.split(r"\s*:\s+|\s+-\s+", text, maxsplit=1)[0]
    return _NUMBER_WORD_RE.sub("", normalize_title_for_match(text)).strip()


def _full(title: str) -> str:
    """Normalized title with number words ('Nos.') dropped and Talkin' folded."""
    text = normalize_title_for_match(_TALKIN_RE.sub("Talking", title))
    return _NUMBER_WORD_RE.sub("", text).strip()


def _alias(title: str, canonical_map: dict[str, str]) -> str:
    """Normalized canonical spelling of *title* via ``song_canonical``, or ''."""
    for key in (normalize_song_title(title), normalize_song_title(_PAREN_RE.sub(" ", title))):
        canonical = canonical_map.get(key)
        if canonical:
            return _full(canonical)
    return ""


@dataclass
class SetlistIndex:
    """Precomputed match keys for one setlist, so many tracks match cheaply.

    Build with :func:`build_setlist_index`; :func:`match_track` accepts either
    this or a plain sequence of candidate titles.

    Attributes:
        titles: Candidate titles, in order.
        full: Per candidate, the normalized full title.
        base: Per candidate, the normalized title without subtitle/parenthetical.
        alias: Per candidate, the normalized ``song_canonical`` spelling ('' if none).
    """

    titles: list[str]
    full: list[str] = field(default_factory=list)
    base: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)


def build_setlist_index(
    candidates: Iterable[str], canonical_map: dict[str, str] | None = None
) -> SetlistIndex:
    """Precompute match keys for a setlist's candidate titles.

    Args:
        candidates: Setlist song titles (e.g. Olof ``song_title``, optionally also
            ``"title (subtitle)"`` forms).
        canonical_map: ``{alias_norm: canonical}`` from ``song_canonical``.

    Returns:
        A :class:`SetlistIndex` over the non-blank candidates.
    """
    cmap = canonical_map or {}
    titles = [c for c in candidates if c and c.strip()]
    return SetlistIndex(
        titles=titles,
        full=[_full(t) for t in titles],
        base=[_base(t) for t in titles],
        alias=[_alias(t, cmap) for t in titles],
    )


class TrackMatch(TypedDict):
    """A successful :func:`match_track` result.

    Keys:
        candidate: The setlist title that matched.
        tier: 'exact', 'base' (without subtitle/parenthetical), 'alias'
            (``song_canonical``) or 'contains' (:func:`backend.db.titles_match`).
    """

    candidate: str
    tier: str


def match_track(
    title: str | None,
    candidates: Sequence[str] | SetlistIndex,
    canonical_map: dict[str, str] | None = None,
) -> TrackMatch | None:
    """Match one track title against a setlist, trying the D-01 tiers in order.

    Tiers: exact normalized title; the title without its subtitle/parenthetical
    (either side); the ``song_canonical`` alias spelling; then conservative
    containment via :func:`backend.db.titles_match`.

    Args:
        title: Track title, ideally already cleaned by :func:`clean_track_title`.
        candidates: Setlist titles, or a prebuilt :class:`SetlistIndex`.
        canonical_map: ``{alias_norm: canonical}`` from ``song_canonical``;
            ignored when *candidates* is a prebuilt index that already used one.

    Returns:
        ``{candidate, tier}`` for the first matching candidate, else ``None``.
    """
    if not title:
        return None
    cmap = canonical_map or {}
    index = (
        candidates if isinstance(candidates, SetlistIndex)
        else build_setlist_index(candidates, cmap)
    )
    if not index.titles:
        return None

    full = _full(title)
    if not full:
        return None
    # Spacing-insensitive, so "My Wife's Hometown" = "My Wife's Home Town".
    squashed = full.replace(" ", "")
    for i, cand in enumerate(index.full):
        if full == cand or squashed == cand.replace(" ", ""):
            return TrackMatch(candidate=index.titles[i], tier="exact")

    base = _base(title)
    for i, cand_base in enumerate(index.base):
        if base and (base == cand_base or base == index.full[i] or full == cand_base):
            return TrackMatch(candidate=index.titles[i], tier="base")

    alias = _alias(title, cmap)
    if alias:
        for i, cand_alias in enumerate(index.alias):
            if alias in (cand_alias, index.full[i], index.base[i]):
                return TrackMatch(candidate=index.titles[i], tier="alias")

    for i in range(len(index.titles)):
        if (titles_match(full, index.full[i]) or titles_match(base, index.base[i])
                or titles_match(base, index.full[i])):
            return TrackMatch(candidate=index.titles[i], tier="contains")
    return None


# ---------------------------------------------------------------------------
# D-01 per-source completeness + G2 source–show fit
# ---------------------------------------------------------------------------

# G2 (plan D-01, audit S11): a source fits its show when at least this share of
# its own song tracks match the setlist...
FIT_MIN_SHARE = 0.20
# ...and sources with fewer song tracks than this aren't judged, so a one- or
# two-song excerpt of something Olof doesn't list is never withheld...
FIT_MIN_SONG_TRACKS = 3
# ...nor is one holding at least this share of the setlist's songs: Olof's page
# lists only a subset (1969-02-17 Nashville outtakes, 1976-05-16's 7 Hard Rain
# songs vs a 49-track full show), so the source is a superset, not mis-dated.
FIT_MAX_SETLIST_COVER = 0.5

# A title holding two or more further "N. Title" markers is a tracklist the
# splitter couldn't separate (space-delimited numbering), not a real title.
_GLUED_TRACKS_RE = re.compile(r"\s\d{1,3}[.)]?\s+[A-Z]")


def is_glued_tracklist(songs: Iterable[str]) -> bool:
    """Whether any title in *songs* still holds several unsplit track markers."""
    return any(len(_GLUED_TRACKS_RE.findall(s)) >= 2 for s in songs)


def fits_show(
    song_tracks: int, matched: int, setlist_songs: int, setlist_matched: int, glued: bool,
) -> bool:
    """G2 source–show fit: does a source's tracklist belong to this show?

    The metric is the share of the *source's* song tracks that match the
    setlist — so a short excerpt that is all on the setlist fits, while a
    mis-dated compilation (LB-06654, 25 studio "Mono Mixes" tracks dated
    1965-06-01) doesn't. Sources too short to judge, glued tracklists and
    sources covering most of the setlist always fit (see the ``FIT_*`` constants).

    Args:
        song_tracks: The source's song tracks (non-songs and ``missing`` excluded).
        matched: How many of them match the setlist.
        setlist_songs: Distinct songs on the setlist.
        setlist_matched: How many of those the source hit.
        glued: Whether the tracklist is unsplit (:func:`is_glued_tracklist`).

    Returns:
        ``False`` only when the source should leave the verdict as "tracklist
        doesn't match this show".
    """
    if song_tracks < FIT_MIN_SONG_TRACKS or glued:
        return True
    if matched / song_tracks >= FIT_MIN_SHARE:
        return True
    return setlist_matched >= FIT_MAX_SETLIST_COVER * setlist_songs


class MissingSong(TypedDict):
    """A setlist position a source doesn't have.

    Keys:
        position: ``olof_songs.position``.
        title: Olof's song title at that position.
    """

    position: int
    title: str


class Completeness(TypedDict):
    """One source's D-01 completeness against an event's setlist.

    Keys:
        lb_number: The source.
        basis: ``'tracklist'`` (the entry lists songs), ``'runtime'`` (no song
            tracks, but a runtime — completeness is never inferred from it) or
            ``None`` (neither).
        songs_present: Setlist positions the source has (partial ones included),
            or ``None`` unless ``basis`` is ``'tracklist'``.
        songs_total: Songs on the setlist, or ``None`` unless ``basis`` is ``'tracklist'``.
        missing: Setlist positions the source lacks, in order.
        partial: Positions present only in part (incomplete / cut / fade).
        extra: The source's song tracks that match no setlist song.
        runtime: ``entries.timing`` as stored, or ``None``.
        confidence: ``'corroborated'`` (TUIT's tracklist for the LB gives the
            same present-count), ``'inferred'`` (it gives a different one),
            ``'stated'`` (TUIT has no tracklist), or ``None`` unless ``basis``
            is ``'tracklist'``.
        tuit_present: Positions TUIT's tracklist has, or ``None``.
        fits_show: G2 (:func:`fits_show`); ``False`` withholds the source from
            the verdict.
        show_bar: Whether a completeness bar may render: a tracklist basis, a
            non-empty setlist, the source fits, and TUIT doesn't disagree.
    """

    lb_number: int
    basis: str | None
    songs_present: int | None
    songs_total: int | None
    missing: list[MissingSong]
    partial: list[int]
    extra: list[str]
    runtime: str | None
    confidence: str | None
    tuit_present: int | None
    fits_show: bool
    show_bar: bool


def _event_setlist(conn: sqlite3.Connection, event_id: int) -> list[tuple[int, str, str]]:
    """``(position, song_title, subtitle)`` for the event's songs, in order.

    Non-songs and Olof's placeholders for unnamed material ("Unidentified
    Instrumental", "Harmonica Riffs") are dropped — no source lists them.
    """
    from backend.qc.corroborate import is_placeholder

    rows = conn.execute(
        "SELECT position, song_title, subtitle FROM olof_songs WHERE event_id = ?"
        " ORDER BY position",
        (event_id,),
    ).fetchall()
    out: list[tuple[int, str, str]] = []
    for position, title, subtitle in rows:
        title = (title or "").strip()
        if title and not is_non_song(title) and not is_placeholder(title):
            out.append((position, title, (subtitle or "").strip()))
    return out


class _PositionMatcher:
    """Assigns matched titles to setlist positions, each position at most once.

    A song played twice fills its first free position, then its second.
    """

    def __init__(self, setlist: list[tuple[int, str, str]], canonical_map: dict[str, str]):
        self._cmap = canonical_map
        self._positions: dict[str, list[int]] = {}
        candidates: list[str] = []
        for position, title, subtitle in setlist:
            forms = [title] + ([f"{title} ({subtitle})"] if subtitle else [])
            for form in forms:
                if form not in self._positions:
                    candidates.append(form)
                self._positions.setdefault(form, []).append(position)
        self._index = build_setlist_index(candidates, canonical_map)

    def assign(self, titles: Iterable[str]) -> tuple[dict[str, int], list[str]]:
        """Match *titles* in order.

        Returns:
            ``({title_key: position})`` keyed ``f"{i}:{title}"`` by track index,
            and the titles that matched no setlist song at all.
        """
        taken: set[int] = set()
        hits: dict[str, int] = {}
        unmatched: list[str] = []
        for i, title in enumerate(titles):
            m = match_track(title, self._index, self._cmap)
            if m is None:
                unmatched.append(title)
                continue
            free = [p for p in self._positions[m["candidate"]] if p not in taken]
            if free:
                taken.add(free[0])
                hits[f"{i}:{title}"] = free[0]
        return hits, unmatched


def completeness(
    conn: sqlite3.Connection,
    event_id: int,
    lb_numbers: Iterable[int],
    canonical_map: dict[str, str] | None = None,
) -> dict[int, Completeness]:
    """D-01: each source's completeness against one event's setlist.

    Each source's song tracks (``missing``-tagged ones excluded — they aren't
    on the recording) are matched onto the event's Olof setlist positions with
    :func:`match_track`. TUIT's per-LB tracklist (Phase 3c) is matched the same
    way; a different present-count lowers the confidence to ``'inferred'``.

    Args:
        conn: Open SQLite connection with ``row_factory = sqlite3.Row``.
        event_id: ``olof_events.event_id`` whose setlist is the reference.
        lb_numbers: The sources to score.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map; loaded
            from *conn* if omitted.

    Returns:
        ``{lb_number: Completeness}`` for every requested LB found in ``entries``.
    """
    from backend.qc.corroborate import load_canonical_map, tracklist_check

    cmap = canonical_map if canonical_map is not None else load_canonical_map(conn)
    setlist = _event_setlist(conn, event_id)
    titles_by_position = {p: t for p, t, _ in setlist}
    setlist_songs = len({t for _, t, _ in setlist})
    matcher = _PositionMatcher(setlist, cmap)

    out: dict[int, Completeness] = {}
    for lb in lb_numbers:
        row = conn.execute(
            "SELECT setlist, timing FROM entries WHERE lb_number = ?", (lb,),
        ).fetchone()
        if row is None:
            continue
        runtime = (row["timing"] or "").strip() or None
        tracks = [t for t in parse_entry_tracklist(row["setlist"]) if t["is_song"]]
        if not tracks:
            out[lb] = Completeness(
                lb_number=lb, basis="runtime" if runtime else None, songs_present=None,
                songs_total=None, missing=[], partial=[], extra=[], runtime=runtime,
                confidence=None, tuit_present=None, fits_show=True, show_bar=False,
            )
            continue

        present = [t for t in tracks if not t["missing"]]
        songs = [t["title"] or "" for t in present]
        hits, unmatched = matcher.assign(songs)
        hit_positions = set(hits.values())
        partial = sorted(
            hits[f"{i}:{songs[i]}"] for i, t in enumerate(present)
            if t["partial"] and f"{i}:{songs[i]}" in hits
        )
        missing = [
            MissingSong(position=p, title=t) for p, t in titles_by_position.items()
            if p not in hit_positions
        ]
        hit_songs = {titles_by_position[p] for p in hit_positions}
        fit = fits_show(
            song_tracks=len(songs), matched=len(songs) - len(unmatched),
            setlist_songs=setlist_songs, setlist_matched=len(hit_songs),
            glued=is_glued_tracklist(songs),
        )

        tuit = tracklist_check(conn, lb, cmap)
        tuit_present: int | None = None
        if tuit["tuit_songs"]:  # '[]' in setlist_json means no tracklist, not zero songs
            tuit_hits, _ = matcher.assign(tuit["tuit_songs"])
            tuit_present = len(tuit_hits)
        if tuit_present is None:
            confidence = "stated"
        elif tuit_present == len(hit_positions):
            confidence = "corroborated"
        else:
            confidence = "inferred"

        out[lb] = Completeness(
            lb_number=lb, basis="tracklist", songs_present=len(hit_positions),
            songs_total=len(setlist), missing=missing, partial=partial, extra=unmatched,
            runtime=runtime, confidence=confidence, tuit_present=tuit_present,
            fits_show=fit,
            show_bar=bool(setlist) and fit and confidence != "inferred",
        )
    return out


# ---------------------------------------------------------------------------
# D-02 song-level performance history
# ---------------------------------------------------------------------------

# Gap badge: a song back after at least this many concerts away (plan D-02).
GAP_BADGE_SHOWS = 100
# Open findings of these rules on the tour withhold per-song premiere badges (D-02 gate
# item 3); R-O1 alone withholds a gap badge across its span (a truncated setlist fakes a gap).
_PREMIERE_GATE_RULES = ("R-O1", "R-O4")
_GAP_GATE_RULES = ("R-O1",)


class SongHistory(TypedDict):
    """One setlist position's D-02 history.

    Keys:
        position: ``song_performances.position``.
        song: Display title (``song_canonical``).
        tour_premiere: No earlier performance in the same ``tour_name`` (first
            occurrence in this show only).
        career_debut: No earlier concert performance at all.
        last_played: Date of the previous concert performance, or ``None``.
        gap_shows: Concert events strictly between that performance and this
            show, or ``None`` on a debut.
        times_played: Concert events with this song, up to and including this show.
        premiere_badge: ``tour_premiere`` and the three-part gate passed.
        gap_badge: ``gap_shows >= GAP_BADGE_SHOWS`` with no open R-O1 in the span.
    """

    position: int
    song: str
    tour_premiere: bool
    career_debut: bool
    last_played: str | None
    gap_shows: int | None
    times_played: int
    premiere_badge: bool
    gap_badge: bool


class SongHistoryResult(TypedDict):
    """Result of :func:`song_history`.

    Keys:
        event_id: The event.
        tour_name: ``olof_events.tour_name``.
        premiere_count: Computed tour premieres (renders even when the gate fails).
        tour_new_count: Olof's stated count, or ``None``.
        gate_passed: All three D-02 gate items hold, so per-song badges may render.
        gate_reasons: Why the gate failed, one line per failed item; ``[]`` when passed.
        songs: One :class:`SongHistory` per position, in order.
    """

    event_id: int
    tour_name: str
    premiere_count: int
    tour_new_count: int | None
    gate_passed: bool
    gate_reasons: list[str]
    songs: list[SongHistory]


def _open_finding_events(conn: sqlite3.Connection, rules: tuple[str, ...]) -> set[int]:
    """Event ids with an open or reopened ``olof_event`` finding under *rules*."""
    try:
        rows = conn.execute(
            "SELECT entity_key FROM qc_findings WHERE entity_kind = 'olof_event'"
            f" AND rule_id IN ({','.join('?' * len(rules))})"
            " AND status IN ('open', 'reopened')",
            rules,
        ).fetchall()
    except sqlite3.OperationalError:  # no qc_findings table yet
        return set()
    return {int(r[0]) for r in rows if str(r[0]).isdigit()}


def _concert_keys(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Every dated concert event as ``(date_str, event_id)``, sorted — the D-02 order."""
    from backend.qc.corroborate import is_concert_row

    rows = conn.execute(
        "SELECT event_id, date_str, event_type, tour_name FROM olof_events WHERE date_str != ''"
    ).fetchall()
    return sorted((r[1], r[0]) for r in rows if is_concert_row(r[2], r[3]))


def song_history(
    conn: sqlite3.Connection, event_id: int, canonical_map: dict[str, str] | None = None,
) -> SongHistoryResult:
    """D-02: per-position performance history, the premiere gate and gap badges.

    Tour premieres come from :func:`backend.qc.corroborate.tour_premieres`
    (Phase 3b), which also answers gate item 2 from setlist.fm scoped to the
    tour's date span. A song played twice in one show is a premiere only at
    its first position. Career history is every earlier concert-filtered
    ``song_performances`` row, ordered by ``(date_str, event_id)``.

    Gate (all three, or no per-song premiere badges; the count renders alone):
    the computed premiere count equals ``tour_new_count``; setlist.fm confirms
    every premiere; no open R-O1/R-O4 finding on this event or an earlier
    event of the tour.

    Args:
        conn: Open SQLite connection with ``row_factory = sqlite3.Row``.
        event_id: ``olof_events.event_id``.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map.

    Returns:
        A :class:`SongHistoryResult`; ``songs`` is ``[]`` (gate failed) when the
        event has no ``song_performances`` rows.
    """
    from backend.qc.corroborate import is_concert_row, tour_premieres

    tp = tour_premieres(conn, event_id, canonical_map)
    ev = conn.execute(
        "SELECT date_str, tour_name FROM olof_events WHERE event_id = ?", (event_id,),
    ).fetchone()
    result = SongHistoryResult(
        event_id=event_id, tour_name=tp["tour_name"], premiere_count=0,
        tour_new_count=tp["tour_new_count"], gate_passed=False, gate_reasons=[], songs=[],
    )
    if ev is None or not tp["songs"]:
        result["gate_reasons"].append("no song_performances rows for this event")
        return result
    date_str, tour_name = ev["date_str"], ev["tour_name"] or ""
    here = (date_str, event_id)

    norm_at = {
        r["position"]: r["song_norm"] for r in conn.execute(
            "SELECT position, song_norm FROM song_performances WHERE event_id = ?", (event_id,),
        )
    }
    distinct = sorted(set(norm_at.values()))
    earlier: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for r in conn.execute(
        "SELECT sp.song_norm, oe.event_id, oe.date_str, oe.event_type, oe.tour_name"
        " FROM song_performances sp JOIN olof_events oe ON oe.event_id = sp.event_id"
        f" WHERE sp.song_norm IN ({','.join('?' * len(distinct))}) AND oe.date_str != ''"
        " AND (oe.date_str < ? OR (oe.date_str = ? AND oe.event_id < ?))",
        (*distinct, date_str, date_str, event_id),
    ):
        if is_concert_row(r["event_type"], r["tour_name"]):
            earlier[r["song_norm"]].add((r["date_str"], r["event_id"]))

    keys = _concert_keys(conn)
    gap_blockers = _open_finding_events(conn, _GAP_GATE_RULES)
    seen: set[str] = set()
    songs: list[SongHistory] = []
    for s in tp["songs"]:
        norm = norm_at.get(s["position"], "")
        first = norm not in seen
        seen.add(norm)
        prior = earlier.get(norm, set())
        last = max(prior) if prior else None
        gap: int | None = None
        gap_ok = False
        if last is not None:
            lo, hi = bisect_right(keys, last), bisect_left(keys, here)
            gap = hi - lo
            gap_ok = gap >= GAP_BADGE_SHOWS and not any(
                eid in gap_blockers for _, eid in keys[lo:hi]
            )
        songs.append(SongHistory(
            position=s["position"], song=s["song"], tour_premiere=s["ours"] and first,
            career_debut=not prior and first, last_played=last[0] if last else None,
            gap_shows=gap, times_played=len(prior) + 1, premiere_badge=False, gap_badge=gap_ok,
        ))

    premieres = [s for s in songs if s["tour_premiere"]]
    by_position = {s["position"]: s for s in tp["songs"]}
    reasons: list[str] = []
    if not tour_name:
        reasons.append("event has no tour_name")
    if tp["tour_new_count"] is None:
        reasons.append("Olof states no tour premiere count")
    elif len(premieres) != tp["tour_new_count"]:
        reasons.append(
            f"computed {len(premieres)} premieres, Olof states {tp['tour_new_count']}"
        )
    unconfirmed = [s["position"] for s in premieres
                   if by_position[s["position"]]["setlistfm"] is not True]
    if unconfirmed:
        reasons.append(f"setlist.fm doesn't confirm the premiere at positions {unconfirmed}")
    if tour_name:
        blockers = _open_finding_events(conn, _PREMIERE_GATE_RULES)
        tour_events = [
            r["event_id"] for r in conn.execute(
                "SELECT event_id, date_str FROM olof_events WHERE tour_name = ?", (tour_name,),
            ) if (r["date_str"] or "", r["event_id"]) <= here
        ]
        blocked = sorted(e for e in tour_events if e in blockers)
        if blocked:
            reasons.append(f"open R-O1/R-O4 finding on tour event(s) {blocked[:5]}")

    passed = not reasons
    for s in songs:
        s["premiere_badge"] = passed and s["tour_premiere"]
    result.update(
        premiere_count=len(premieres), gate_passed=passed, gate_reasons=reasons, songs=songs,
    )
    return result


# ---------------------------------------------------------------------------
# D-03 Official release status (TODO-342 C19)
# ---------------------------------------------------------------------------

_OFFICIAL_RELEASES_ASSET = Path(__file__).resolve().parent / "assets" / "official_releases.json"

# Prefixes olof_parser.py puts on a released_on token (P1f): the song is only
# partly on the release, or Olof names two positions with "or" and the
# release holds one of them. Mirrors RELEASE_PART_TAG/RELEASE_UNCERTAIN_TAG
# in backend/olof_parser.py.
_RELEASE_PART_TAG = "(part) "
_RELEASE_UNCERTAIN_TAG = "(uncertain) "

_TITLE_KEY_RE = re.compile(r"[^a-z0-9]+")
_TITLE_KEY_MAX_LEN = 80

_allowlist_cache: list[ReleaseAllowlistEntry] | None = None


def normalize_title_key(raw: str | None) -> str:
    """Normalize a release string into a stable ``release_classifications`` key.

    Shared by :func:`official_release`, ``backend.qc.rules.rule_r1`` and the
    ``POST /api/qc/releases/<title_key>`` route, so all three agree on
    identity. Folds accents, case, punctuation and whitespace so trivial
    spelling variants of one raw string collapse to one key. A truncated
    tail plus an 8-hex digest keeps very long strings usable both as a
    SQLite primary key and as a URL path segment.

    Args:
        raw: The raw Olof release string (a ``released_on`` token, already
            stripped of any ``(part)``/``(uncertain)`` prefix, or a
            whole-show ``releases_raw`` line).

    Returns:
        A lowercase, hyphen-separated slug. Never empty.
    """
    text = unicodedata.normalize("NFKD", str(raw or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    slug = _TITLE_KEY_RE.sub("-", text.lower()).strip("-")
    if len(slug) > _TITLE_KEY_MAX_LEN:
        digest = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:8]
        slug = f"{slug[:_TITLE_KEY_MAX_LEN].rstrip('-')}-{digest}"
    if not slug:
        slug = f"release-{hashlib.sha1(text.encode('utf-8', 'ignore')).hexdigest()[:8]}"
    return slug


@dataclass
class ReleaseAllowlistEntry:
    """One compiled entry of ``backend/assets/official_releases.json``.

    Attributes:
        title: Display title shown in the QC review console and dossier.
        year: Release year, or ``None`` when the entry spans several years
            (e.g. the 50th Anniversary Collections).
        kind: Free-text category ('studio_album', 'bootleg_series', 'video',
            'bootleg', 'radio_syndication', ...).
        official: Whether this is an official Columbia/Legacy/Sony/Bob Dylan
            Archive release, as opposed to a known non-official source
            (Wolfgang's Vault, Westwood One, Crystal Cat, satellite feeds).
        patterns: Compiled case-insensitive regexes; any one matching a raw
            release string classifies it as this entry.
    """

    title: str
    year: int | None
    kind: str
    official: bool
    patterns: tuple[re.Pattern, ...]


def load_official_releases(path: Path | None = None) -> list[ReleaseAllowlistEntry]:
    """Load and compile ``backend/assets/official_releases.json``.

    Cached at module scope after the first call with the default *path*
    (the packaged asset); a non-default *path* (tests) always reloads and
    is never cached.

    Args:
        path: Override for the asset path.

    Returns:
        Compiled entries in file order. When a raw string matches several
        entries (a studio album also sold in a reissue box; "50th ANNIVERSARY
        COLLECTION: 1965 … a gift for purchasers of Bootleg Series Vol. 12"),
        :func:`classify_release_string` takes the one named earliest in the
        string; file order only breaks ties.
    """
    global _allowlist_cache
    if path is None and _allowlist_cache is not None:
        return _allowlist_cache
    asset_path = path or _OFFICIAL_RELEASES_ASSET
    with open(asset_path, encoding="utf-8") as f:
        raw_entries = json.load(f)
    entries = [
        ReleaseAllowlistEntry(
            title=item["title"],
            year=item.get("year"),
            kind=item["kind"],
            official=bool(item["official"]),
            patterns=tuple(re.compile(p, re.IGNORECASE) for p in item["patterns"]),
        )
        for item in raw_entries
    ]
    if path is None:
        _allowlist_cache = entries
    return entries


def strip_release_prefix(token: str) -> tuple[str, bool, bool]:
    """Split a ``released_on`` token's ``(part)``/``(uncertain)`` prefix off.

    Args:
        token: One ``'; '``-split piece of ``olof_songs.released_on``.

    Returns:
        ``(text, is_part, is_uncertain)`` — *text* has the prefix removed.
    """
    if token.startswith(_RELEASE_PART_TAG):
        return token[len(_RELEASE_PART_TAG):], True, False
    if token.startswith(_RELEASE_UNCERTAIN_TAG):
        return token[len(_RELEASE_UNCERTAIN_TAG):], False, True
    return token, False, False


def split_release_tokens(text: str | None) -> list[str]:
    """Split a ``'; '``-joined ``released_on`` string into trimmed tokens."""
    return [t.strip() for t in str(text or "").split(";") if t.strip()]


def release_overrides(conn: sqlite3.Connection) -> dict[str, bool]:
    """Load curator verdicts as ``{title_key: official}`` from ``release_classifications``.

    This table wins over the packaged allowlist for any ``title_key`` it
    covers (plan D-03: "the table wins").

    Args:
        conn: Open SQLite connection.

    Returns:
        ``{}`` if the table doesn't exist yet (fresh DB, pre-migration).
    """
    try:
        return {
            r["title_key"]: bool(r["official"])
            for r in conn.execute("SELECT title_key, official FROM release_classifications")
        }
    except sqlite3.OperationalError:
        return {}


def classify_release_string(
    raw: str, allowlist: list[ReleaseAllowlistEntry], overrides: dict[str, bool],
) -> tuple[str, str | None, bool | None]:
    """Classify one raw release string (a ``(part)``/``(uncertain)`` prefix already stripped).

    Args:
        raw: The raw release string.
        allowlist: Compiled entries from :func:`load_official_releases`.
        overrides: ``{title_key: official}`` from :func:`release_overrides`.

    Returns:
        ``(title_key, title, official)``. *title* and *official* are
        ``None`` when *raw* matches neither an override nor the allowlist
        (unclassified — the R-R1 finding this feeds).
    """
    title_key = normalize_title_key(raw)
    if title_key in overrides:
        return title_key, raw.strip(), overrides[title_key]
    best: tuple[int, int, ReleaseAllowlistEntry] | None = None
    for order, entry in enumerate(allowlist):
        starts = [m.start() for p in entry.patterns if (m := p.search(raw))]
        if starts and (best is None or (min(starts), order) < best[:2]):
            best = (min(starts), order, entry)
    if best is None:
        return title_key, None, None
    return title_key, best[2].title, best[2].official


class ReleaseMatch(TypedDict):
    """One classified release string attached to a song position or the whole show."""

    raw: str
    title_key: str
    title: str | None
    official: bool | None
    part: bool
    uncertain: bool


class SongRelease(TypedDict):
    """D-03 per-position release coverage — feeds the song release markers."""

    position: int
    song_title: str
    official: bool
    partial: bool
    matches: list[ReleaseMatch]


class OfficialRelease(TypedDict):
    """D-03 official release status for one dossier event."""

    status: str  # 'full' | 'partial' | 'none'
    whole_show: bool
    whole_show_title: str | None
    songs: list[SongRelease]


def official_release(
    conn: sqlite3.Connection,
    event_id: int,
    allowlist: list[ReleaseAllowlistEntry] | None = None,
) -> OfficialRelease | None:
    """D-03: official release status for one Olof event.

    Sources: ``olof_events.releases_raw`` for whole-show release lines (a
    line with no leading position-list — e.g. "Released on X..." rather
    than "4, 9 released on X..."), and ``olof_songs.released_on`` for
    per-position coverage. :func:`release_overrides` wins over the packaged
    allowlist for any given ``title_key``.

    Status:
        - ``full``: a whole-show line classifies official, or every song
          position has a non-``(part)``/``(uncertain)`` official match.
        - ``partial``: some (not all) positions have an official match,
          counting ``(part)``/``(uncertain)`` tokens toward partial only
          (never toward full, per plan D-03).
        - ``none``: the event exists in Olof and nothing classified official.

    Args:
        conn: Open SQLite connection with ``row_factory = sqlite3.Row``.
        event_id: ``olof_events.event_id``.
        allowlist: Optional pre-loaded allowlist (tests); defaults to the
            packaged asset via :func:`load_official_releases`.

    Returns:
        ``None`` if there's no such event (the caller omits the row);
        otherwise an :class:`OfficialRelease`.
    """
    ev = conn.execute(
        "SELECT event_id, releases_raw FROM olof_events WHERE event_id = ?", (event_id,),
    ).fetchone()
    if ev is None:
        return None

    allow = allowlist if allowlist is not None else load_official_releases()
    overrides = release_overrides(conn)

    whole_show = False
    whole_show_title: str | None = None
    for line in (ev["releases_raw"] or "").splitlines():
        line = line.strip().rstrip(".")
        if not line or line[0].isdigit():
            continue  # a leading digit targets specific positions, not the whole show
        _, title, official = classify_release_string(line, allow, overrides)
        if official:
            whole_show = True
            whole_show_title = title
            break

    songs: list[SongRelease] = []
    for r in conn.execute(
        "SELECT position, song_title, released_on FROM olof_songs"
        " WHERE event_id = ? ORDER BY position", (event_id,),
    ):
        matches: list[ReleaseMatch] = []
        song_official = False
        song_partial = False
        for token in split_release_tokens(r["released_on"]):
            text, is_part, is_uncertain = strip_release_prefix(token)
            title_key, title, is_official = classify_release_string(text, allow, overrides)
            matches.append(ReleaseMatch(
                raw=token, title_key=title_key, title=title, official=is_official,
                part=is_part, uncertain=is_uncertain,
            ))
            if is_official:
                song_partial = True
                if not is_part and not is_uncertain:
                    song_official = True
        songs.append(SongRelease(
            position=r["position"], song_title=r["song_title"], official=song_official,
            partial=song_partial, matches=matches,
        ))

    if whole_show or (songs and all(s["official"] for s in songs)):
        status = "full"
    elif any(s["partial"] for s in songs):
        status = "partial"
    else:
        status = "none"

    return OfficialRelease(
        status=status, whole_show=whole_show, whole_show_title=whole_show_title, songs=songs,
    )


# ---------------------------------------------------------------------------
# D-07 run, tour & city history
# ---------------------------------------------------------------------------

# Olof's year buckets ("1965 Recording sessions & concerts") aren't tours.
_NOT_A_TOUR = "recording session"


class TourContext(TypedDict):
    """The one tour object a page shows (audit P6).

    Keys:
        name: Olof's ``tour_name`` (the leg); NET # is the umbrella.
        net_number: ``olof_events.concert_no_net``, or ``None``.
        position: 1-based concert position within the tour.
        size: Concerts in the tour.
        is_first: ``position == 1``.
        is_last: ``position == size``.
        claims_ok: Every tour concert has parsed songs and no open R-O1 — the
            completeness guard for "first" / "last" / "N of M" wording.
    """

    name: str
    net_number: int | None
    position: int
    size: int
    is_first: bool
    is_last: bool
    claims_ok: bool


class VenueRun(TypedDict):
    """Consecutive concerts at one exact venue within one tour, nothing between.

    Keys:
        venue: The exact Olof venue name.
        position: This show's night within the run.
        size: Nights in the run.
        dates: Each night's date, in order (the view builds dossier URLs from them).
        event_ids: Each night's event id, in order.
        claims_ok: Every night has parsed songs and no open R-O1.
    """

    venue: str
    position: int
    size: int
    dates: list[str]
    event_ids: list[int]
    claims_ok: bool


class CityHistoryRow(TypedDict):
    """One ``(year, venue)`` row of a city's concert history; venues never merge."""

    year: str
    venue: str
    count: int


class CityHistory(TypedDict):
    """Every concert in this show's city.

    Keys:
        city: Display city (setlist.fm's, else Olof's).
        country: Display country, or ``''``.
        basis: ``'setlistfm'`` or ``'olof'`` — where this show's city came from.
        total: Concerts in the city (``venue.city_total``).
        rows: ``{year, venue, count}`` sorted by year then venue.
        invariant_ok: G5 — ``sum(count) == total``; the panel is suppressed otherwise.
    """

    city: str
    country: str
    basis: str
    total: int
    rows: list[CityHistoryRow]
    invariant_ok: bool


class RunContext(TypedDict):
    """Result of :func:`run_context`; each part is ``None`` when it doesn't apply."""

    event_id: int
    tour: TourContext | None
    venue_run: VenueRun | None
    city_history: CityHistory | None


def _concert_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every dated concert event, in the D-02/D-07 ``(date_str, event_id)`` order."""
    from backend.qc.corroborate import is_concert_row

    rows = conn.execute(
        "SELECT event_id, date_str, venue, city, country, tour_name, event_type, concert_no_net"
        " FROM olof_events WHERE date_str != ''"
    ).fetchall()
    concerts = [r for r in rows if is_concert_row(r["event_type"], r["tour_name"])]
    return sorted(concerts, key=lambda r: (r["date_str"], r["event_id"]))


def _claims_ok(conn: sqlite3.Connection, event_ids: list[int]) -> bool:
    """Completeness guard: every event has parsed songs and no open R-O1 finding."""
    if not event_ids:
        return False
    with_songs = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT event_id FROM song_performances"
            f" WHERE event_id IN ({','.join('?' * len(event_ids))})",
            event_ids,
        )
    }
    truncated = _open_finding_events(conn, ("R-O1",))
    return all(e in with_songs and e not in truncated for e in event_ids)


def _city_history(
    conn: sqlite3.Connection, concerts: list[sqlite3.Row], ev: sqlite3.Row,
) -> CityHistory | None:
    """Concerts grouped by setlist.fm ``(city, country)`` per date, Olof's city as fallback."""
    from backend.qc.corroborate import _fold_city_name, _fold_place_name

    sfm: dict[str, tuple[str, str]] = {}
    for r in conn.execute(
        "SELECT date_str, city, country FROM setlistfm_shows WHERE COALESCE(city, '') != ''"
        " ORDER BY setlistfm_id"
    ):
        sfm.setdefault(r["date_str"], (r["city"], r["country"] or ""))

    def place(r: sqlite3.Row) -> tuple[str, str | None, str, str, str]:
        if r["date_str"] in sfm:
            city, country = sfm[r["date_str"]]
            return _fold_city_name(city), _fold_place_name(country), "setlistfm", city, country
        city, country = r["city"] or "", r["country"] or ""
        return _fold_city_name(city), _fold_place_name(country) or None, "olof", city, country

    city_key, country_key, basis, city, country = place(ev)
    if not city_key:
        return None
    rows: Counter[tuple[str, str]] = Counter()
    total = 0
    for r in concerts:
        other_city, other_country, *_ = place(r)
        if other_city != city_key:
            continue
        if country_key and other_country and other_country != country_key:
            continue
        total += 1
        rows[(r["date_str"][:4], (r["venue"] or "").strip())] += 1
    out_rows = [
        CityHistoryRow(year=y, venue=v, count=n) for (y, v), n in sorted(rows.items())
    ]
    return CityHistory(
        city=city, country=country, basis=basis, total=total, rows=out_rows,
        invariant_ok=sum(r["count"] for r in out_rows) == total,
    )


def run_context(conn: sqlite3.Connection, event_id: int) -> RunContext:
    """D-07: this concert's tour, venue run and city history.

    Args:
        conn: Open SQLite connection with ``row_factory = sqlite3.Row``.
        event_id: ``olof_events.event_id`` (a concert).

    Returns:
        A :class:`RunContext`; every part is ``None`` for a non-concert event. The
        tour is ``None`` too when ``tour_name`` is empty or an Olof year bucket
        ("Recording sessions").
    """
    out = RunContext(event_id=event_id, tour=None, venue_run=None, city_history=None)
    concerts = _concert_rows(conn)
    idx = next((i for i, r in enumerate(concerts) if r["event_id"] == event_id), None)
    if idx is None:
        return out
    ev = concerts[idx]

    tour_name = (ev["tour_name"] or "").strip()
    if tour_name and _NOT_A_TOUR not in tour_name.lower():
        tour_ids = [r["event_id"] for r in concerts if r["tour_name"] == ev["tour_name"]]
        pos = tour_ids.index(event_id) + 1
        out["tour"] = TourContext(
            name=tour_name, net_number=ev["concert_no_net"], position=pos, size=len(tour_ids),
            is_first=pos == 1, is_last=pos == len(tour_ids),
            claims_ok=_claims_ok(conn, tour_ids),
        )

    venue = (ev["venue"] or "").strip()
    if venue:
        def same_run(r: sqlite3.Row) -> bool:
            return r["tour_name"] == ev["tour_name"] and (r["venue"] or "").strip() == venue

        lo = hi = idx
        while lo > 0 and same_run(concerts[lo - 1]):
            lo -= 1
        while hi + 1 < len(concerts) and same_run(concerts[hi + 1]):
            hi += 1
        run = concerts[lo:hi + 1]
        ids = [r["event_id"] for r in run]
        out["venue_run"] = VenueRun(
            venue=venue, position=idx - lo + 1, size=len(run),
            dates=[r["date_str"] for r in run], event_ids=ids, claims_ok=_claims_ok(conn, ids),
        )

    out["city_history"] = _city_history(conn, concerts, ev)
    return out


# ---------------------------------------------------------------------------
# D-04 cross-show rotation
# ---------------------------------------------------------------------------


class RotationSibling(TypedDict):
    """One night of the venue run and whether its Olof rotation stat holds up.

    Keys:
        event_id: The night's event.
        date: Its date.
        pct: Olof's ``rotation_pct``, or ``None``.
        new: Olof's ``rotation_new``, or ``None``.
        verified: Our recompute from the previous concert matches Olof (Phase 3b).
        disputed: The recompute contradicts Olof.
    """

    event_id: int
    date: str
    pct: int | None
    new: int | None
    verified: bool
    disputed: bool


class RotationRank(TypedDict):
    """Result of :func:`rotation_rank`.

    Keys:
        pct: This show's ``rotation_pct``.
        new: This show's ``rotation_new``.
        rank_in_run: 1 + siblings with a higher pct.
        run_size: Nights in the run.
        run_median_pct: Median of the run's stated pcts.
        tie: Another night has the same pct.
        siblings: One :class:`RotationSibling` per night.
        superlative_ok: The claim engine may say "most changed … <scope>": every night
            verified, rank 1 with no tie, a run of 2+ nights passing the completeness guard.
        scope: The named scope, e.g. "of the 7-night Zepp Tokyo run".
    """

    pct: int
    new: int | None
    rank_in_run: int
    run_size: int
    run_median_pct: float
    tie: bool
    siblings: list[RotationSibling]
    superlative_ok: bool
    scope: str


def rotation_rank(
    conn: sqlite3.Connection, event_id: int, venue_run: VenueRun,
) -> RotationRank | None:
    """D-04: rank this show's rotation stat within its venue run.

    Args:
        conn: Open SQLite connection with ``row_factory = sqlite3.Row``.
        event_id: The show.
        venue_run: Its :class:`VenueRun` from :func:`run_context`.

    Returns:
        A :class:`RotationRank`, or ``None`` when Olof states no rotation stat for
        this show.
    """
    from backend.qc.corroborate import rotation_check

    siblings: list[RotationSibling] = []
    for eid, date in zip(venue_run["event_ids"], venue_run["dates"], strict=True):
        rc = rotation_check(conn, eid)
        siblings.append(RotationSibling(
            event_id=eid, date=date, pct=rc["olof_pct"], new=rc["olof_new"],
            verified=rc["agrees"] is True, disputed=rc["agrees"] is False,
        ))
    me = next((s for s in siblings if s["event_id"] == event_id), None)
    if me is None or me["pct"] is None:
        return None
    pcts = [s["pct"] for s in siblings if s["pct"] is not None]
    rank = 1 + sum(p > me["pct"] for p in pcts)
    tie = sum(p == me["pct"] for p in pcts) > 1
    return RotationRank(
        pct=me["pct"], new=me["new"], rank_in_run=rank, run_size=len(siblings),
        run_median_pct=statistics.median(pcts), tie=tie, siblings=siblings,
        superlative_ok=(
            venue_run["size"] >= 2 and venue_run["claims_ok"] and rank == 1 and not tie
            and all(s["verified"] for s in siblings)
        ),
        scope=f"of the {venue_run['size']}-night {venue_run['venue']} run",
    )


# ---------------------------------------------------------------------------
# D-05 generation classification
# ---------------------------------------------------------------------------

_BOOTLEG_RE = re.compile(r"\bBOOTLEG\s*:", re.IGNORECASE)
_SILVER_RE = re.compile(r"\bsilver\s*(?:discs?|cds?|pressings?)\b", re.IGNORECASE)
# A label credit or a catalogue number ("Label:XAVEL", "SCCD 2488", "BDACD103").
_LABEL_RE = re.compile(r"(?i:\blabel\s*:)|\b[A-Z]{2,}[\s-]?\d{2,}\b")
_VINYL_RE = re.compile(r"(?i:\bvinyl\b)|\bLPs?\b")
# "Radio Shack" is an audience microphone brand, not a broadcast.
_BROADCAST_RE = re.compile(
    # Named networks are broadcasts too (tj, 2026-09-11: "vh1 is TV, this is a TV source").
    # CBS/ABC/NBC are deliberately absent — they appear as record labels in these lineages.
    r"\b(?:TV|FM|pre-?FM|radio(?![\s,]*shack)|broadcast|televised|telecast"
    r"|VH-?1|MTV|BBC|Showtime|PBS|HBO)\b", re.IGNORECASE
)
# A separator is required, so a trader handle like 'lowgen' never reads as a generation.
_LOW_GEN_RE = re.compile(
    r"\b(?:1st|first|low|2nd|second|3rd|third|4th|fourth|5th)[\s-]+gen(?:eration)?\b"
    r"|\bclone\s+of\s+(?:the\s+)?master\b",
    re.IGNORECASE,
)
# Closed compounds are the same claim typed without the space (tj, 2026-09-11): "MasterTape",
# "MasterDAT", "MasterCopy". Deliberately NOT widened to "mastered"/"mastering" (a post-transfer
# credit, not a generation), "masterpiece", or "masters" — 8 of the corpus's 36 "masters" are the
# song "Masters Of War" and most of the rest are prose ("two different masters for this date").
_MASTER_RE = re.compile(r"\bmaster(?:tape|dat|copy|cassette|reel)?\b", re.IGNORECASE)
# "cassette master -> DAT - clone -> CDR": a clone after the master makes the source low gen.
# Glued the same way "MasterTape" is ("DATClone", "CDclone"), so the clone hop is still seen —
# without this, widening _MASTER_RE alone would promote "MasterTape > DAT > DATClone" to master.
_CLONE_RE = re.compile(r"\b(?:dat|cdr?|tape)?clone\b", re.IGNORECASE)
# An explicit gap in the chain ("DAT > ??? > Data DVD (FLAC Files"): the hops on either side
# say nothing about what the file descends from, so nothing is inferred (LB-06991, which tj
# reviewed and approved as unknown).
_UNKNOWN_HOP_RE = re.compile(r"\?{2,}|\bunknown\s+(?:source|lineage|origin|provenance)\b",
                             re.IGNORECASE)
_SOUNDBOARD_RE = re.compile(r"\b(?:soundboard|sbd)\b", re.IGNORECASE)
_TRANSFER_RE = re.compile(r"\btransferr?ed\b|\btransfer\b", re.IGNORECASE)
# Rule 6: a first hop naming a microphone, and a later hop naming a recorder.
# Model numbers run straight into the brand in these lineages ("dpa4061", "akg391's",
# "ecm 717", "COS-11PTs", "ca14"), so each brand tolerates an attached number.
_MIC_RE = re.compile(
    r"\b(?:mics?|microphones?|SP-CMC-?\d*|Core\s*Sounds?|ECM[-\s]?\d+|DPA\s*\d*|Schoeps"
    r"|AKG\s*\d*|Neumann|Church|Sennheiser|Audio[\s-]?Technica|Countryman|Oktava"
    r"|Sonic\s*Studios?|CM-?300|COS-?\d+|CA-?\d{2}\b|OKM\w*|Sanken|SKM\s*\d+)",
    re.IGNORECASE,
)
_RECORDER_RE = re.compile(
    r"\b(?:MicroTrack|Zoom|H[124]n?|R-?0[59]|R-?44|Tascam|DR-?\d+|PCM-?[A-Z0-9]+|DAT"
    r"|WM-?D6C|minidisc|MD|cassette|recorder|Marantz|Edirol|TCD-?D?\d+|LS-\d+)\b",
    re.IGNORECASE,
)


class Generation(TypedDict):
    """One source's D-05 generation class.

    Keys:
        lb_number: The source.
        generation: ``silver`` / ``vinyl`` / ``broadcast`` / ``low_gen`` / ``master`` /
            ``unknown`` (the tag is omitted).
        basis: ``'stated'`` (the lineage says so), ``'inferred'`` (rule 6's mic →
            recorder chain with a confirmed taper), or ``None`` for ``unknown``.
        evidence: The substring (or ``bootleg_titles`` title) that fired the rule.
    """

    lb_number: int
    generation: str
    basis: str | None
    evidence: str | None


def _confirmed_taper(conn: sqlite3.Connection, lb_number: int) -> bool:
    """A confirmed (not propagated) attribution that no open R-T error quarantines."""
    from backend.qc.store import quarantined

    row = conn.execute(
        "SELECT confidence FROM taper_attributions WHERE lb_number = ? AND conflict = 0",
        (lb_number,),
    ).fetchone()
    if row is None or row[0] != "confirmed":
        return False
    return not any(r.startswith("R-T") for r in quarantined(conn, "lb", str(lb_number)))


def classify_generation(conn: sqlite3.Connection, lb_number: int) -> Generation:
    """D-05: classify a source's generation from its lineage, first matching rule wins.

    Never guessed from rating or grade. Rules: ``BOOTLEG:`` / a silver disc / a
    ``bootleg_titles`` row → silver; vinyl/LP → vinyl; TV/FM/radio/broadcast →
    broadcast; explicit 1st/low gen or clone of master → low_gen; the word "master"
    → master (stated), or low_gen when a clone follows it; a mic → recorder chain
    with a confirmed, unquarantined taper → master (inferred); otherwise unknown.
    tj's D-05 sign-off (2026-09-11) dropped the plan's label-or-catalogue condition
    on silver discs and added the clone-after-master case.

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number``.

    Returns:
        A :class:`Generation`.
    """
    row = conn.execute(
        "SELECT source_chain FROM entries WHERE lb_number = ?", (lb_number,),
    ).fetchone()
    chain = (row[0] if row else None) or ""

    def hit(generation: str, basis: str, evidence: str) -> Generation:
        return Generation(
            lb_number=lb_number, generation=generation, basis=basis, evidence=evidence,
        )

    m = _BOOTLEG_RE.search(chain)
    if m:
        return hit("silver", "stated", chain[m.start():m.start() + 40].strip())
    silver = _SILVER_RE.search(chain)
    if silver:
        label = _LABEL_RE.search(chain)
        evidence = f"{silver.group(0)} · {label.group(0)}" if label else silver.group(0)
        return hit("silver", "stated", evidence)
    # A lineage that names vinyl outranks a bootleg_titles row: the row says the recording was
    # bootlegged, the lineage says what this file was ripped from (tj, 2026-09-11, on LB-10799
    # "Vinyl Album 'Going, Going Gothenburg' > Technics SL1200"). No lineage in the corpus names
    # vinyl and a BOOTLEG:/silver token together, so the two checks above stay authoritative.
    vinyl_source = _VINYL_RE.search(chain)
    if vinyl_source:
        return hit("vinyl", "stated", vinyl_source.group(0))
    bootleg = conn.execute(
        "SELECT title FROM bootleg_titles WHERE lb_number = ? ORDER BY id LIMIT 1", (lb_number,),
    ).fetchone()
    if bootleg:
        return hit("silver", "stated", f"bootleg title: {bootleg[0]}")
    for generation, pattern in (("vinyl", _VINYL_RE), ("broadcast", _BROADCAST_RE),
                                ("low_gen", _LOW_GEN_RE), ("master", _MASTER_RE)):
        m = pattern.search(chain)
        if m:
            clone = _CLONE_RE.search(chain, m.end()) if generation == "master" else None
            if clone:
                return hit("low_gen", "stated", f"{m.group(0)} … {clone.group(0)}")
            return hit(generation, "stated", m.group(0))
    hops = [h.strip() for h in chain.split(">") if h.strip()]
    if len(hops) >= 2:
        # tj, 2026-09-11, over 21 of the audit's rows: "master inferred (microphone thru flac
        # info given)" — a lineage that walks from the capture device to the circulating file
        # IS the master, whether or not a taper is attributed, and a named recorder counts as
        # the capture device on its own ("Sony PCM-D100 > USB 3.0 > PC > WaveLab").
        capture = None if _UNKNOWN_HOP_RE.search(chain) else next(
            (m for h in hops[:-1] for m in (_MIC_RE.search(h) or _RECORDER_RE.search(h),) if m),
            None,
        )
        if capture:
            return hit("master", "inferred", f"{capture.group(0)} > … > {hops[-1][:24]}")
    elif not _UNKNOWN_HOP_RE.search(chain):
        # Not every taper writes an arrow chain: "rc 631a aud ca14 m10, taped + mastered by: RCM"
        # and "Neumann skm140 / Neumann BS48i-2 / Marantz PMD 661" separate the hops with commas
        # or slashes. Both a mic AND a recorder must be named here — stricter than the arrow
        # rule above, which needs only one, because there is no chain shape to corroborate them.
        mic, recorder = _MIC_RE.search(chain), _RECORDER_RE.search(chain)
        if mic and recorder:
            return hit("master", "inferred", f"{mic.group(0)} + {recorder.group(0)}")
    # A soundboard someone transferred to disc is a hop off that desk tape, not the tape (tj,
    # 2026-09-11, on LB-03470). Last in the order, so a lineage that says "master" outright has
    # already returned above — of the corpus's 6 soundboard-plus-transfer lineages, 2 do.
    sbd = _SOUNDBOARD_RE.search(chain)
    if sbd and _TRANSFER_RE.search(chain):
        return hit("low_gen", "stated", f"{sbd.group(0)} … transferred")
    return Generation(lb_number=lb_number, generation="unknown", basis=None, evidence=None)


# ---------------------------------------------------------------------------
# D-13 medium
# ---------------------------------------------------------------------------

# Video carriers: an audience-shot DVD is video but not a broadcast, so it keeps its taper.
_VIDEO_TOKEN_RE = re.compile(r"\b(?:DVD|VOB|VHS|video|Betamax|laserdisc)\b", re.IGNORECASE)
_TV_TOKEN_RE = re.compile(r"\b(?:TV|televised|telecast)\b", re.IGNORECASE)
_RADIO_TOKEN_RE = re.compile(
    r"\b(?:FM|pre-?FM|AM)\b|(?i:\b(?:radio(?![\s,]*shack)|broadcast)\b)"
)
_VIDEO_EXT_RE = re.compile(r"\.(?:vob|mkv|mp4|avi|m2ts|mpe?g|mov|iso|ifo)$", re.IGNORECASE)


class Medium(TypedDict):
    """One source's D-13 medium.

    Keys:
        lb_number: The source.
        medium: ``'audio'`` (the default) or ``'audio_from_video'``.
        broadcast: TV or radio broadcast-derived: "broadcast copy" wording and no
            taper line, and an attributed taper is a QC finding (R-T5).
        evidence: What fired (``lb_category``, a lineage token, a video file), or ``None``.
    """

    lb_number: int
    medium: str
    broadcast: bool
    evidence: str | None


def classify_medium(conn: sqlite3.Connection, lb_number: int) -> Medium:
    """D-13: whether a source is a plain audio recording or a broadcast/video copy.

    Signals, strongest first: ``entries.lb_category`` tv/radio; TV, video (DVD, VOB,
    VHS) or radio (FM, radio, broadcast) tokens in the lineage; video extensions in
    ``checksums.filename``.

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number``.

    Returns:
        A :class:`Medium`; ``'audio'`` and not broadcast when nothing fires.
    """
    row = conn.execute(
        "SELECT lb_category, source_chain FROM entries WHERE lb_number = ?", (lb_number,),
    ).fetchone()
    category, chain = ((row[0] or "").lower(), row[1] or "") if row else ("", "")

    def medium(kind: str, broadcast: bool, evidence: str) -> Medium:
        return Medium(lb_number=lb_number, medium=kind, broadcast=broadcast, evidence=evidence)

    if category == "tv":
        return medium("audio_from_video", True, "lb_category tv")
    if category == "radio":
        return medium("audio", True, "lb_category radio")
    m = _TV_TOKEN_RE.search(chain)
    if m:
        return medium("audio_from_video", True, m.group(0))
    m = _VIDEO_TOKEN_RE.search(chain)
    if m:
        return medium("audio_from_video", False, m.group(0))
    m = _RADIO_TOKEN_RE.search(chain)
    if m:
        return medium("audio", True, m.group(0))
    for (filename,) in conn.execute(
        "SELECT filename FROM checksums WHERE lb_number = ? AND xref = 0", (lb_number,),
    ):
        if _VIDEO_EXT_RE.search(filename or ""):
            return medium("audio_from_video", False, filename)
    return Medium(lb_number=lb_number, medium="audio", broadcast=False, evidence=None)


def media_available(conn: sqlite3.Connection, lb_numbers: list[int]) -> list[str]:
    """``show.media_available``: the distinct media across a show's sources, sorted."""
    return sorted({classify_medium(conn, lb)["medium"] for lb in lb_numbers})


def broadcast_tapers(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """``(lb_number, taper, evidence)`` for broadcast-derived sources with a taper.

    A broadcast copy has no taper, so each is a QC finding (rule R-T5). An
    audience-shot video keeps its taper.
    """
    out: list[tuple[int, str, str]] = []
    for lb, taper in conn.execute(
        "SELECT lb_number, taper_normalised FROM taper_attributions WHERE conflict = 0"
    ).fetchall():
        m = classify_medium(conn, lb)
        if m["broadcast"]:
            out.append((lb, taper, m["evidence"] or m["medium"]))
    return out


# ---------------------------------------------------------------------------
# D-09 Setlist completeness (C22)
# ---------------------------------------------------------------------------

_MIN_TOKEN_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)

# Calibrated from recording_mins (.debug/dossier_calibration.md, C22): the corpus-wide
# median of recording_mins / song_count over concert events with >= 5 songs (n=3,089).
_MINS_PER_SONG = 6.33

# Secondary-signal gap threshold, same calibration run: expected_count (a source's
# median runtime / _MINS_PER_SONG) minus Olof's listed song count, split by the
# Phase 3a quorum's ground truth -- only 1.7% of 'corroborated' (genuinely complete)
# dates show a gap over 5, while 42% of 'disputed' (genuinely incomplete-vs-sources)
# dates do. A conservative cut that rarely misflags a complete setlist.
_SETLIST_GAP_THRESHOLD = 5

# Olof's own admission that a page's setlist is incomplete ("Incomplete setlist taken
# from memory.", "This listing is incomplete.", "The song listing is probably
# incomplete.") -- 10 corpus hits sampled during calibration.
_INCOMPLETE_SETLIST_RE = re.compile(
    r"incomplete (?:song )?(?:setlist|listing)|(?:setlist|listing) is (?:probably )?incomplete",
    re.IGNORECASE,
)


def _timing_minutes(timing: str | None) -> float | None:
    """Sum every ``Nmin`` token in *timing* (``entries.timing`` free text); ``None`` if none."""
    if not timing:
        return None
    vals = [int(m) for m in _MIN_TOKEN_RE.findall(timing)]
    return float(sum(vals)) if vals else None


class SetlistConfidence(TypedDict):
    """D-09: whether an event's rendered setlist reads complete or partial.

    Keys:
        status: ``'complete'``, ``'partial'`` or ``'unavailable'`` (neither Olof nor
            any source has a setlist for the date -- nothing to judge).
        verdict: The underlying :class:`~backend.qc.corroborate.Quorum` verdict.
        basis: ``'quorum'`` when the Phase 3a cross-source check decided it,
            ``'runtime'`` when the secondary runtime/expected-count signal did,
            ``'incomplete_note'`` when Olof's own "incomplete setlist" phrasing did,
            or ``None`` when nothing beyond Olof's page count was available.
        songs_listed: Olof's non-song-filtered song count for the event.
        expected_songs: The secondary signal's estimate (rounded), or ``None`` when
            no source runtime was available to compute one.
        notice: Human text naming the sources/counts behind a ``disputed`` quorum
            verdict, or explaining a runtime/note-based ``partial``; ``None`` for
            ``complete``/``unavailable``.
    """

    status: str
    verdict: str
    basis: str | None
    songs_listed: int
    expected_songs: int | None
    notice: str | None


def setlist_confidence(
    conn: sqlite3.Connection,
    event_id: int,
    lb_numbers: Iterable[int],
    canonical_map: dict[str, str] | None = None,
) -> SetlistConfidence:
    """D-09: setlist completeness for one event (plan D-09, audit S9).

    Primary is the Phase 3a cross-source quorum
    (:func:`backend.qc.corroborate.setlist_quorum`): ``'disputed'`` reads
    ``'partial'`` with a notice naming the disputing sources and their song
    counts; ``'corroborated'`` reads ``'complete'``. When no external source
    has a setlist for the date (quorum ``'stated'`` -- Olof has one, nobody
    else does), the secondary signal runs instead: *lb_numbers*'s median
    ``entries.timing`` runtime divided by the calibrated corpus
    minutes-per-song (:data:`_MINS_PER_SONG`) gives an expected song count; a
    gap over :data:`_SETLIST_GAP_THRESHOLD` reads ``'partial'``, as does
    Olof's own "incomplete setlist" phrasing in ``olof_events.notes``.
    Quorum ``'unavailable'`` (nobody has a setlist at all) reads
    ``'unavailable'``.

    Args:
        conn: Open SQLite connection.
        event_id: ``olof_events.event_id``.
        lb_numbers: The show's source LB numbers, read for the secondary
            signal's runtime figure. Unused when the primary quorum decides.
        canonical_map: Optional pre-loaded ``song_canonical`` alias map.

    Returns:
        A :class:`SetlistConfidence`.
    """
    from backend.qc import corroborate

    row = conn.execute(
        "SELECT date_str, notes FROM olof_events WHERE event_id = ?", (event_id,),
    ).fetchone()
    date_str, notes = (row["date_str"], row["notes"]) if row else (None, None)
    songs_listed = len(_event_setlist(conn, event_id))

    cmap = canonical_map if canonical_map is not None else corroborate.load_canonical_map(conn)
    quorum = (
        corroborate.setlist_quorum(conn, date_str, cmap) if date_str
        else corroborate.Quorum(verdict="unavailable", sources={})
    )
    verdict = quorum["verdict"]

    if verdict == "corroborated":
        return SetlistConfidence(
            status="complete", verdict=verdict, basis="quorum", songs_listed=songs_listed,
            expected_songs=None, notice=None,
        )
    if verdict == "disputed":
        names = quorum["disputed_sources"]
        pairs = [(n, quorum["sources"][n]["n_songs"]) for n in names if quorum["sources"].get(n)]
        others = ", ".join(f"{n} lists {c}" for n, c in pairs)
        notice = f"disputed: Olof lists {songs_listed}" + (f", {others}" if others else "")
        return SetlistConfidence(
            status="partial", verdict=verdict, basis="quorum", songs_listed=songs_listed,
            expected_songs=None, notice=notice,
        )
    if verdict == "unavailable":
        return SetlistConfidence(
            status="unavailable", verdict=verdict, basis=None, songs_listed=songs_listed,
            expected_songs=None, notice=None,
        )

    # verdict == "stated": no external source has data for this date -- secondary signal.
    if _INCOMPLETE_SETLIST_RE.search(notes or ""):
        return SetlistConfidence(
            status="partial", verdict=verdict, basis="incomplete_note",
            songs_listed=songs_listed, expected_songs=None,
            notice="Olof's page calls its own setlist incomplete",
        )

    lb_list = list(lb_numbers)
    runtimes: list[float] = []
    if lb_list:
        placeholders = ",".join("?" * len(lb_list))
        for (timing,) in conn.execute(
            f"SELECT timing FROM entries WHERE lb_number IN ({placeholders})", lb_list,
        ):
            mins = _timing_minutes(timing)
            if mins is not None:
                runtimes.append(mins)

    expected_songs = None
    if runtimes:
        expected_songs = round(statistics.median(runtimes) / _MINS_PER_SONG)
        if expected_songs - songs_listed > _SETLIST_GAP_THRESHOLD:
            return SetlistConfidence(
                status="partial", verdict=verdict, basis="runtime", songs_listed=songs_listed,
                expected_songs=expected_songs,
                notice=f"expected ~{expected_songs} songs from runtime, {songs_listed} listed",
            )

    return SetlistConfidence(
        status="complete", verdict=verdict, basis="runtime" if runtimes else None,
        songs_listed=songs_listed, expected_songs=expected_songs, notice=None,
    )


# ---------------------------------------------------------------------------
# D-11 Format & file metadata (C22)
# ---------------------------------------------------------------------------

_AUDIO_EXT_RE = re.compile(r"\.(flac|wav|shn|ape|wv|tak|m4a|mp3|ogg|aiff?)$", re.IGNORECASE)


class FileMeta(TypedDict):
    """D-11: one source's file-level metadata, each field independently null-safe.

    Keys:
        lb_number: The source.
        resolution: Rendered label -- ``"16/44 file"`` (a TUIT ``lb_verified`` file
            record), ``"recorded 24/96"`` (lineage only, unverified), both joined
            with " · " when a file record and a differing lineage figure both
            exist (audit M1), or ``"—"`` when neither is known.
        file_res: TUIT's verified file record resolution, or ``None``.
        recorded_res: The lineage's recorder-stage resolution, or ``None``.
        filesize: TUIT ``size_bytes`` from the ``lb_verified`` row, or ``None`` --
            never inferred from anything else.
        filecount: Distinct audio filenames in ``checksums`` (``xref = 0``),
            falling back to TUIT ``n_files``, or ``None``.
        disc_count: ``entries.cdr`` as an int, or ``None`` when blank, ``<= 0`` or
            ``> 6`` (R-E1).
    """

    lb_number: int
    resolution: str
    file_res: str | None
    recorded_res: str | None
    filesize: int | None
    filecount: int | None
    disc_count: int | None


def _disc_count(cdr: str | None) -> int | None:
    """``entries.cdr`` parsed to an in-range disc count, or ``None`` (R-E1)."""
    cdr = (cdr or "").strip()
    if not cdr:
        return None
    try:
        n = int(cdr)
    except ValueError:
        return None
    return n if 0 < n <= 6 else None


def file_meta(conn: sqlite3.Connection, lb_number: int) -> FileMeta:
    """D-11: file-level metadata for one source, TUIT-verified where it exists.

    Reuses :func:`backend.qc.corroborate.file_format_check` (the same D-11/Q1-d
    file-record-vs-lineage logic, so the two never drift) for the resolution
    figures, then renders the label per basis: a TUIT ``lb_verified`` file
    record wins and is labelled "file"; a lineage-only figure is labelled
    "recorded" since it's never confirmed -- see audit M1 (LB-08485's lineage
    states "24bit/96kHz" for the recorder, but the circulating file is 16/44).

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number``.

    Returns:
        A :class:`FileMeta`.
    """
    from backend.qc import corroborate

    fmt = corroborate.file_format_check(conn, lb_number)
    file_res, recorded_res = fmt["file_res"], fmt["recorded_res"]

    parts: list[str] = []
    if file_res:
        parts.append(f"{file_res} file")
        if recorded_res and recorded_res != file_res:
            parts.append(f"recorded {recorded_res}")
    else:
        value = fmt["final_res"] or recorded_res
        if value:
            parts.append(f"recorded {value}")
    resolution = " · ".join(parts) if parts else "—"

    row = conn.execute("SELECT cdr FROM entries WHERE lb_number = ?", (lb_number,)).fetchone()
    disc_count = _disc_count(row[0] if row else None)

    filesize: int | None = None
    filecount: int | None = None
    try:
        trow = conn.execute(
            "SELECT size_bytes, n_files FROM tuit_recordings"
            " WHERE lb_number = ? AND lb_verified = 1 ORDER BY rec_id LIMIT 1",
            (lb_number,),
        ).fetchone()
    except sqlite3.OperationalError:  # no tuit_recordings table yet
        trow = None
    if trow:
        filesize, filecount = trow["size_bytes"], trow["n_files"]

    names = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT filename FROM checksums WHERE lb_number = ? AND xref = 0",
            (lb_number,),
        )
        if _AUDIO_EXT_RE.search(r[0] or "")
    }
    if names:
        filecount = len(names)

    return FileMeta(
        lb_number=lb_number, resolution=resolution, file_res=file_res,
        recorded_res=recorded_res, filesize=filesize, filecount=filecount,
        disc_count=disc_count,
    )


# ---------------------------------------------------------------------------
# C23 Supporting parsers (T2, same module) -- band/members/instruments/tally,
# song writers, set[].label banding, source character/flags, lineage_short,
# runtime, family.basis, taper render rule.
# ---------------------------------------------------------------------------

# Word-form ordinals ("first" .. "thirtieth"); numeric-ordinal lineups ("21st")
# are handled by _NUM_ORDINAL_RE instead.
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "twenty-first": 21, "twenty-second": 22, "twenty-third": 23,
    "twenty-fourth": 24, "twenty-fifth": 25, "twenty-sixth": 26,
    "twenty-seventh": 27, "twenty-eighth": 28, "twenty-ninth": 29,
    "thirtieth": 30,
}
_NUM_ORDINAL_RE = re.compile(r"^(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)

# "First concert with the first Never-Ending Tour Band: ..." / "Concert # 4 with
# third Never-Ending Tour band: ..." -- "the" is optional and casing of "Band"
# varies (audit: 3,117 of 4,185 lineups, plan line 636).
_BAND_RE = re.compile(
    r"\bwith\s+(?:the\s+)?([A-Za-z0-9-]+)\s+Never-?Ending\s+Tour\s+[Bb]and\b",
)
_SOLO_RE = re.compile(r"\bBob\s+Dylan\s*\(\s*solo\b", re.IGNORECASE)
_MEMBER_RE = re.compile(r"([^,;()]+?)\s*\(([^)]*)\)")

# A per-song/range clause opens with one or more comma/"and"-joined position
# tokens ("7-9", "7-10 and 15", "11") followed by the override text.
_RANGE_PREFIX_RE = re.compile(r"^\s*((?:\d+(?:-\d+)?)(?:\s*(?:,|and)\s*\d+(?:-\d+)?)*)\s+(?=\S)")
_RANGE_TOKEN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _ordinal_to_int(token: str) -> int | None:
    """Parse a band-index ordinal ("21st", "first") to its integer, or None."""
    token = token.strip().lower()
    m = _NUM_ORDINAL_RE.match(token)
    if m:
        return int(m.group(1))
    return _ORDINAL_WORDS.get(token)


class BandMember(TypedDict):
    """One lineup personnel entry.

    Keys:
        name: Musician name, as it appears in ``olof_events.lineup``.
        instruments: Their parenthetical instrument text, verbatim.
    """

    name: str
    instruments: str


class BandLineup(TypedDict):
    """``band_index`` / ``band.label`` / ``band.members`` (plan line 636-637).

    Keys:
        band_index: The Never-Ending Tour band's ordinal number, or ``None``
            for a pre-NET / solo lineup or one the regex doesn't recognise.
        band_label: ``"<ordinal> Never-Ending Tour Band"`` (e.g. "21st Never
            -Ending Tour Band"), ``"Solo"`` when Dylan plays alone, or
            ``None``.
        members: The base personnel, Dylan moved first, from the lineup's
            first (un-numbered) clause.
    """

    band_index: int | None
    band_label: str | None
    members: list[BandMember]


def _base_clause(lineup: str) -> str:
    """The lineup's first ``;``-separated clause, header (before ``:``) dropped."""
    clause = lineup.split(";", 1)[0]
    if ":" in clause:
        clause = clause.split(":", 1)[1]
    return clause


def _is_dylan_alone(base_clause: str, members: list[BandMember]) -> bool:
    """True when the base personnel clause names Dylan and nobody else.

    The clause must hold exactly one member, that member must be Dylan, and
    nothing but punctuation may remain once the parsed members are removed --
    so an unparenthesised band name ("... with Tom Petty & The Heartbreakers")
    keeps the lineup out of ``Solo``.

    Args:
        base_clause: The lineup's base personnel clause.
        members: The members parsed out of *base_clause*.

    Returns:
        Whether the lineup is Dylan alone.
    """
    if len(members) != 1 or "dylan" not in members[0]["name"].lower():
        return False
    residue = _MEMBER_RE.sub("", base_clause)
    return not re.search(r"[A-Za-z]", residue)


def parse_band_lineup(lineup: str | None) -> BandLineup:
    """``band_index`` / ``band.label`` / ``band.members`` (C23, plan line 636-637).

    ``band_index`` / ``band.label`` come from a regex on "Concert # N with the
    <ordinal> Never-Ending Tour Band" (the "the" and the "Concert # N with"
    prefix are both optional -- corpus phrasing varies); ``"solo"`` is used
    when the lineup opens with "Bob Dylan (solo, ...)". ``band.members`` reads
    the lineup's first clause -- the base personnel, before any per-song/range
    override clause -- with Dylan moved to the front.

    Args:
        lineup: ``olof_events.lineup`` free text.

    Returns:
        A :class:`BandLineup`.
    """
    lineup = lineup or ""
    band_index: int | None = None
    band_label: str | None = None

    m = _BAND_RE.search(lineup)
    if m:
        band_index = _ordinal_to_int(m.group(1))
        ordinal = m.group(1)
        display = ordinal if _NUM_ORDINAL_RE.match(ordinal) else ordinal.capitalize()
        band_label = f"{display} Never-Ending Tour Band"
    elif _SOLO_RE.search(lineup):
        band_label = "Solo"

    base = _base_clause(lineup)
    members: list[BandMember] = []
    for name, instruments in _MEMBER_RE.findall(base):
        name = re.sub(r"^(?:with)\s+", "", name.strip(), flags=re.IGNORECASE).strip(" .")
        if name:
            members.append(BandMember(name=name, instruments=instruments.strip()))
    members.sort(key=lambda mem: 0 if "dylan" in mem["name"].lower() else 1)

    if band_index is None and band_label is None and _is_dylan_alone(base, members):
        band_label = "Solo"

    return BandLineup(band_index=band_index, band_label=band_label, members=members)


def _expand_ranges(token: str) -> set[int]:
    """``"7-10 and 15"`` -> ``{7, 8, 9, 10, 15}``."""
    positions: set[int] = set()
    for part in re.split(r",|\band\b", token, flags=re.IGNORECASE):
        part = part.strip()
        if not part:
            continue
        m = _RANGE_TOKEN_RE.match(part)
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        positions.update(range(lo, hi + 1))
    return positions


def _lineup_range_clauses(lineup: str | None) -> list[tuple[set[int], str]]:
    """Per-song/range override clauses from *lineup*, each ``(positions, text)``.

    The lineup's first (un-numbered) clause is the base personnel
    (:func:`parse_band_lineup`) and is never generalised onto the other
    songs -- audit M13 found that "otherwise" fallback wrong. Only clauses
    that open with an explicit position/range token are per-song overrides.
    """
    out: list[tuple[set[int], str]] = []
    for clause in (lineup or "").split(";"):
        clause = clause.strip()
        if not clause:
            continue
        m = _RANGE_PREFIX_RE.match(clause)
        if not m:
            continue
        positions = _expand_ranges(m.group(1))
        text = clause[m.end():].strip().rstrip(".").strip()
        if positions and text:
            out.append((positions, text))
    return out


def song_instruments(lineup: str | None, position: int) -> str | None:
    """``song.instruments`` (C23, plan line 638): one song's instrument note.

    Reads only the lineup's per-song/range override clauses and Dylan notes
    -- never the base personnel clause (audit M13's "no otherwise
    generalisation": the base lineup is a whole-show default, not a per-song
    fact). A later clause covering the same position wins.

    Args:
        lineup: ``olof_events.lineup`` free text.
        position: The song's ``olof_songs.position``.

    Returns:
        The covering clause's text, or ``None`` when no clause covers
        *position*.
    """
    text: str | None = None
    for positions, clause_text in _lineup_range_clauses(lineup):
        if position in positions:
            text = clause_text
    return text


# Canonical instrument label per matched token -- "harp" (not "harmonica") and
# "keyboard" (piano/organ/keyboards folded in) match the plan's example
# ("harp 8 . keyboard 15 . guitar 1", line 639).
_INSTRUMENT_RE = re.compile(
    r"\b(harmonica|harp|piano|organ|keyboards?|guitar|bass|drums?|violin|fiddle|"
    r"banjo|mandolin|vocals?|pedal steel|accordion)\b",
    re.IGNORECASE,
)
_INSTRUMENT_CANON = {
    "harmonica": "harp", "harp": "harp",
    "piano": "keyboard", "organ": "keyboard", "keyboard": "keyboard", "keyboards": "keyboard",
    "guitar": "guitar",
    "bass": "bass",
    "drum": "drums", "drums": "drums",
    "violin": "violin", "fiddle": "violin",
    "banjo": "banjo",
    "mandolin": "mandolin",
    "vocal": "vocal", "vocals": "vocal",
    "pedal steel": "pedal steel",
    "accordion": "accordion",
}


def _instrument_tokens(text: str) -> set[str]:
    """Distinct canonical instrument names mentioned in *text* (case-folded)."""
    return {_INSTRUMENT_CANON[m.group(1).lower()] for m in _INSTRUMENT_RE.finditer(text)}


def instrument_tally(lineup: str | None, song_count: int) -> Counter[str]:
    """``stats.instrument_tally`` (C23, plan line 639): per-instrument song counts.

    Counts, per instrument, how many songs its per-song/range override clause
    covers -- one increment per covered song, not per mention (so a clause
    naming "guitar" twice for the same song still counts once). Only reads
    the override clauses (:func:`_lineup_range_clauses`); the base personnel
    is never generalised onto uncovered songs (audit M13).

    Args:
        lineup: ``olof_events.lineup`` free text.
        song_count: The show's total song count, to clip out-of-range
            position tokens (a stray range past the last song is dropped).

    Returns:
        A :class:`collections.Counter` keyed by canonical instrument name.
    """
    resolved: dict[int, str] = {}
    for positions, text in _lineup_range_clauses(lineup):
        for p in positions:
            if 1 <= p <= song_count:
                resolved[p] = text
    tally: Counter[str] = Counter()
    for text in resolved.values():
        for instrument in _instrument_tokens(text):
            tally[instrument] += 1
    return tally


class SongWriters(TypedDict):
    """``song.writers`` (C23, plan line 640).

    Keys:
        value: The rendered writer credit (corrected value when one exists,
            else Olof's ``olof_songs.credits`` as spelled), or ``None`` when
            the song has no cover credit (it's solely Dylan's).
        corrected: Whether *value* came from a curator correction.
        original: Olof's un-corrected credit text, only set when *corrected*
            is True (for the "corrected" tooltip).
    """

    value: str | None
    corrected: bool
    original: str | None


def _latest_correction(
    conn: sqlite3.Connection, entity_kind: str, entity_key: str, field: str,
) -> str | None:
    """The most recent ``corrections.corrected`` value for one field, or None."""
    try:
        row = conn.execute(
            "SELECT corrected FROM corrections WHERE entity_kind = ? AND entity_key = ?"
            " AND field = ? ORDER BY id DESC LIMIT 1",
            (entity_kind, entity_key, field),
        ).fetchone()
    except sqlite3.OperationalError:  # no corrections table yet
        return None
    return row[0] if row else None


def song_writers(conn: sqlite3.Connection, event_id: int, position: int) -> SongWriters:
    """``song.writers`` (C23, plan line 640): one song's writer credit.

    Reads ``olof_songs.credits`` (already populated only for covers -- a
    Dylan original's ``credits`` is blank, which is how "shown only when the
    song isn't solely Dylan's" falls out for free), with any curator
    ``corrections`` row (entity ``olof_song``/``"<event_id>:<position>"``,
    field ``"credits"``) applied in preference.

    Args:
        conn: Open SQLite connection.
        event_id: ``olof_events.event_id``.
        position: ``olof_songs.position``.

    Returns:
        A :class:`SongWriters`.
    """
    row = conn.execute(
        "SELECT credits FROM olof_songs WHERE event_id = ? AND position = ?",
        (event_id, position),
    ).fetchone()
    credits_ = ((row[0] if row else "") or "").strip()
    corrected = _latest_correction(conn, "olof_song", f"{event_id}:{position}", "credits")
    if corrected is not None and corrected.strip() != credits_:
        return SongWriters(
            value=corrected.strip() or None, corrected=True, original=credits_ or None,
        )
    return SongWriters(value=credits_ or None, corrected=False, original=None)


class SetLabel(TypedDict):
    """One ``set[].label`` banding result (C23, plan line 641-644).

    Keys:
        kind: ``"band"`` for a contiguous broadcast range, ``"marker"`` for a
            single/non-contiguous song.
        text: The broadcast note text (``olof_songs.annotations``).
        positions: The song position(s) it covers.
    """

    kind: str
    text: str
    positions: list[int]


def broadcast_set_labels(
    conn: sqlite3.Connection, event_id: int,
) -> tuple[list[SetLabel], list[str]]:
    """``set[].label`` broadcast banding + ``context.session_notes`` (C23, plan 641-644).

    Groups an event's ``olof_songs.annotations`` by identical broadcast note
    text: a note covering every song in the show is a whole-show recording
    note and goes to ``context.session_notes`` instead of a set label; a note
    covering a contiguous run of positions becomes one ``"band"`` label; a
    note on non-contiguous positions (or a single song) becomes one
    ``"marker"`` label per position.

    Args:
        conn: Open SQLite connection.
        event_id: ``olof_events.event_id``.

    Returns:
        ``(labels, session_notes)``.
    """
    rows = conn.execute(
        "SELECT position, annotations FROM olof_songs WHERE event_id = ? ORDER BY position",
        (event_id,),
    ).fetchall()
    total = len(rows)
    groups: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        ann = (r["annotations"] or "").strip()
        if ann and "broadcast" in ann.lower():
            groups[ann].append(r["position"])

    labels: list[SetLabel] = []
    session_notes: list[str] = []
    for text, positions in groups.items():
        positions = sorted(positions)
        if total and len(positions) == total:
            session_notes.append(text)
            continue
        contiguous = positions == list(range(positions[0], positions[-1] + 1))
        if contiguous and len(positions) > 1:
            labels.append(SetLabel(kind="band", text=text, positions=positions))
        else:
            for p in positions:
                labels.append(SetLabel(kind="marker", text=text, positions=[p]))
    return labels, session_notes


# Grade/rank prefix ("Grade B+ (74/100). LB2327: ranked #2 of 2. ") in front of
# the descriptive sentence -- both the grade clause and the ranked clause are
# independently optional (a single-source LB has neither/one of them).
_VERDICT_PREFIX_RE = re.compile(
    r"^(?:Grade\s+\S+\s*\(\d+/100\)\.\s*)?LB\d+:\s*(?:ranked\s+#\d+\s+of\s+\d+\.\s*)?",
)
_VERDICT_FLAGS_RE = re.compile(
    r"Flags:\s*(.*?)\.(?=\s*(?:Best in group|Weakest in group)|\s*$)", re.DOTALL,
)
_SOUNDS_PREFIX_RE = re.compile(r"^Sounds\s+", re.IGNORECASE)


class SourceCharacter(TypedDict):
    """``source.character`` / ``.flags`` (C23, plan line 645-646).

    Keys:
        lb_number: The source.
        character: The descriptive sentence(s) from ``verdict_text`` with the
            grade/LB/rank prefix, the "Sounds " lead-in and any ``Flags:``
            clause stripped; ``None`` when there's no score/verdict.
        flags: The ``Flags:`` clause's items, plus ``"no lineage on file"``
            when ``entries.source_chain`` is empty.
    """

    lb_number: int
    character: str | None
    flags: list[str]


def source_character(conn: sqlite3.Connection, lb_number: int) -> SourceCharacter:
    """``source.character`` / ``.flags`` (C23, plan line 645-646).

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number``.

    Returns:
        A :class:`SourceCharacter`.
    """
    from concert_ranker.lb import repo as cr_repo

    verdict_text = None
    scan_id = cr_repo.scored_scan_id(conn)
    if scan_id is not None:
        row = conn.execute(
            "SELECT verdict_text FROM quality_recording_scores WHERE scan_id = ?"
            " AND lb_number = ?",
            (scan_id, lb_number),
        ).fetchone()
        verdict_text = row[0] if row else None

    flags: list[str] = []
    character: str | None = None
    if verdict_text:
        text = _VERDICT_PREFIX_RE.sub("", verdict_text).strip()
        m = _VERDICT_FLAGS_RE.search(text)
        if m:
            flags = [
                f.strip() for f in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1))
                if f.strip()
            ]
            text = re.sub(r"\s{2,}", " ", text[:m.start()] + text[m.end():]).strip()
        text = _SOUNDS_PREFIX_RE.sub("", text).strip().rstrip(".").strip()
        character = text or None

    chain = conn.execute(
        "SELECT source_chain FROM entries WHERE lb_number = ?", (lb_number,),
    ).fetchone()
    if not ((chain[0] if chain else None) or "").strip():
        flags.append("no lineage on file")

    return SourceCharacter(lb_number=lb_number, character=character, flags=flags)


# DAW/extraction-software and codec/file-format tokens that mark the first
# "no longer analog/hardware" hop in a source_chain -- lineage_short cuts
# there. Not exhaustive of the corpus's software vocabulary, but covers its
# common extraction tools (eac, tlh, cdwave/cd wave, wavelab, cooledit/cool
# edit, audacity, dbpoweramp, md5summer) and every audio codec/file format.
_DAW_CODEC_RE = re.compile(
    r"\b(?:eac|exact\s+audio\s+copy|tlh|trader'?s?\s+little\s+helper|cd\s*wave|"
    r"wavelab|cool\s*edit|audacity|adobe\s+audition|sound\s*forge|nero|"
    r"dbpower\s*amp|md5summer|flac|wave?|shn|ape|wv|tak|mp3|m4a|ogg|aiff?)\b",
    re.IGNORECASE,
)


def lineage_short(source_chain: str | None) -> str | None:
    """``pick.lineage_short`` (C23, plan line 647): the chain before the first hop.

    Cuts ``entries.source_chain`` before its first DAW/extraction-software or
    codec/file-format hop (:data:`_DAW_CODEC_RE`), keeping the analog/hardware
    capture chain. ``None`` for a blank chain; the whole chain when no such
    hop is present.

    Args:
        source_chain: ``entries.source_chain`` free text.

    Returns:
        The truncated lineage, or ``None``.
    """
    if not (source_chain or "").strip():
        return None
    hops = source_chain.split(">")
    for i, hop in enumerate(hops):
        if _DAW_CODEC_RE.search(hop):
            prefix = ">".join(hops[:i]).strip().rstrip(",").strip()
            return prefix or None
    return source_chain.strip()


class Runtime(TypedDict):
    """``runtime`` (C23, plan line 648-649): one source's parsed ``entries.timing``.

    Keys:
        total_minutes: Sum of every ``Nmin`` token (G5: always equal to
            ``sum(parts)`` by construction).
        parts: The individual per-segment minute values, in text order (a
            multi-disc/multi-set source has more than one).
        raw: The original ``entries.timing`` text.
    """

    total_minutes: float
    parts: list[float]
    raw: str


def parse_runtime(timing: str | None) -> Runtime | None:
    """``runtime`` (C23, plan line 648-649): parse ``entries.timing`` into segments + total.

    Args:
        timing: ``entries.timing`` free text (e.g. ``"72min+69min+51min+41min"``).

    Returns:
        A :class:`Runtime`, or ``None`` when *timing* has no ``Nmin`` token
        (12,338 of 16,646 parse per the plan's calibration count).
    """
    if not timing:
        return None
    parts = [float(m) for m in _MIN_TOKEN_RE.findall(timing)]
    if not parts:
        return None
    return Runtime(total_minutes=sum(parts), parts=parts, raw=timing)


class FamilyBasis(TypedDict):
    """``family.basis`` (C23, plan line 650-651), computed at render time.

    Keys:
        fam_id: The family.
        conf: ``tapematch_family_meta.conf`` (the waveform-correlation mean),
            or ``None``.
        notes: Rendered basis notes, in order: the correlation mean, "LB page
            states same source" when ``by`` includes ``'lb'``, and "quality
            score match" when :func:`backend.tapematch_sync._has_quality_match`
            finds one.
    """

    fam_id: str
    conf: float | None
    notes: list[str]


def family_basis(conn: sqlite3.Connection, fam_id: str) -> FamilyBasis:
    """``family.basis`` (C23, plan line 650-651): render-time basis notes for a family.

    Args:
        conn: Open SQLite connection.
        fam_id: ``tapematch_family_meta.fam_id`` / ``recording_families.fam_id``.

    Returns:
        A :class:`FamilyBasis`.
    """
    from backend import tapematch_sync

    row = conn.execute(
        "SELECT conf, by FROM tapematch_family_meta WHERE fam_id = ?", (fam_id,),
    ).fetchone()
    if row is None:
        return FamilyBasis(fam_id=fam_id, conf=None, notes=[])
    conf, by = row["conf"], row["by"]

    notes: list[str] = []
    if conf is not None:
        notes.append(f"waveform correlation mean {conf:.2f}")
    if by and "lb" in by:
        notes.append("LB page states same source")

    lb_numbers = [
        r[0] for r in conn.execute(
            "SELECT lb_number FROM recording_families WHERE fam_id = ?", (fam_id,),
        )
    ]
    abs_scores = tapematch_sync._load_latest_abs_scores(conn)
    if tapematch_sync._has_quality_match(lb_numbers, abs_scores):
        notes.append("quality score match")

    return FamilyBasis(fam_id=fam_id, conf=conf, notes=notes)


# R-T1/R-T2/R-T3 are error-severity (a bare-mention credit, a weak-family
# propagation, an out-of-era propagation); R-T4/R-T5 are warn-severity
# (TUIT disagreement, a broadcast-source credit) and don't block rendering --
# R-T4 becomes the ``disputed`` notice instead.
_TAPER_BLOCKING_RULES = ("R-T1", "R-T2", "R-T3")


class TaperRender(TypedDict):
    """``taper`` render rule (C23, plan line 652-655).

    Keys:
        lb_number: The source.
        name: The taper's canonical name, or ``None`` when it's missing, has
            an unresolved conflict, or an open R-T1/R-T2/R-T3 error blocks it
            -- never ``"unknown"`` (audit M8).
        confidence: ``taper_attributions.confidence`` (``'confirmed'`` /
            ``'propagated'`` / ``'inferred'``), or ``None``.
        marker: ``"inferred"`` for a ``propagated``/``inferred``-confidence
            credit, else ``None``.
        notice: A disputed-vs-TUIT notice (R-T4) when applicable, else
            ``None``.
    """

    lb_number: int
    name: str | None
    confidence: str | None
    marker: str | None
    notice: str | None


def taper_render(conn: sqlite3.Connection, lb_number: int) -> TaperRender:
    """``taper`` render rule (C23, plan line 652-655): QC-gated taper display.

    Renders only when no open R-T1/R-T2/R-T3 error blocks the credit; a
    ``propagated``/``inferred``-confidence credit still renders, with an
    "inferred" marker; a credit that disputes TUIT's declared taper (R-T4)
    renders with a notice; a missing or conflicted attribution renders
    nothing, never "unknown" (audit M8).

    Args:
        conn: Open SQLite connection.
        lb_number: ``entries.lb_number``.

    Returns:
        A :class:`TaperRender`.
    """
    try:
        blocked = conn.execute(
            "SELECT 1 FROM qc_findings WHERE entity_kind = 'lb' AND entity_key = ?"
            f" AND rule_id IN ({','.join('?' * len(_TAPER_BLOCKING_RULES))})"
            " AND status IN ('open', 'reopened') LIMIT 1",
            (str(lb_number), *_TAPER_BLOCKING_RULES),
        ).fetchone()
    except sqlite3.OperationalError:  # no qc_findings table yet
        blocked = None
    if blocked:
        return TaperRender(lb_number=lb_number, name=None, confidence=None, marker=None,
                            notice=None)

    row = conn.execute(
        "SELECT taper_normalised, confidence, conflict FROM taper_attributions"
        " WHERE lb_number = ?",
        (lb_number,),
    ).fetchone()
    if row is None or row["conflict"]:
        return TaperRender(lb_number=lb_number, name=None, confidence=None, marker=None,
                            notice=None)

    name, confidence = row["taper_normalised"], row["confidence"]
    marker = "inferred" if confidence in ("propagated", "inferred") else None

    notice: str | None = None
    try:
        from backend.qc import corroborate

        check = corroborate.taper_check(conn, lb_number)
        if check["verdict"] == "disputed":
            notice = f"disputed: TUIT says {' / '.join(check['tuit_canonical'])}"
    except sqlite3.OperationalError:  # no tuit_recordings table yet
        pass

    return TaperRender(lb_number=lb_number, name=name, confidence=confidence, marker=marker,
                        notice=notice)
