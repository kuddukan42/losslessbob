"""Dossier field requirements (TODO-342 Phase 4) — starting with the D-01 track matcher.

``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md`` "D-01 Per-source completeness" needs a
per-track reading of ``entries.setlist`` (free text, split by
:func:`backend.db.parse_entry_setlist_titles`) and a matcher against Olof's setlist.
This module holds those pieces; ``completeness()`` itself lands with Phase 4.

- :func:`clean_track_title` strips durations, credit/performance suffixes and
  header fragments the splitter glues onto a title, and returns ``None`` for
  non-songs (intro, applause, band introductions, encore break, tuning, crowd).
- :func:`parse_entry_tracklist` returns one :class:`EntryTrack` per split title,
  flagging partial (``incomplete``/``cut``/``fade``) and missing tracks.
- :func:`match_track` matches one cleaned title against a setlist: exact
  normalized title, then without the subtitle/parenthetical, then via
  ``song_canonical`` aliases, then :func:`backend.db.titles_match` containment.

QC rule R-E2 (``backend/qc/rules.py``) is the first consumer.
"""
from __future__ import annotations

import logging
import re
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
    r"|[\-(]*\s*(?:intermission|encores?)\s*[\-)]*\s*(?=,|$)"
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
    "track", "in", "out",
})

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


def _base(title: str) -> str:
    """Title without parentheticals or a ':'/' - ' subtitle, normalized for matching."""
    text = _PAREN_RE.sub(" ", title)
    text = re.split(r"\s*:\s+|\s+-\s+", text, maxsplit=1)[0]
    return _NUMBER_WORD_RE.sub("", normalize_title_for_match(text)).strip()


def _full(title: str) -> str:
    """Normalized title with number words ('Nos.') dropped."""
    return _NUMBER_WORD_RE.sub("", normalize_title_for_match(title)).strip()


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
    for i, cand in enumerate(index.full):
        if full == cand:
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
