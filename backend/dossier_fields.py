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

import logging
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
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
