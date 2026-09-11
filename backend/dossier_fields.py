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
import unicodedata
from bisect import bisect_left, bisect_right
from collections import defaultdict
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
