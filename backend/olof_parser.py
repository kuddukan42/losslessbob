"""Parser for Olof Björner's Still On The Road session pages (DSN corpus) —
reads pages already mirrored by backend/olof_fetcher.py into
data/olof/pages/, decodes windows-1252, and emits one olof_events row per
`<a name=DSNnnnnn>` event block, plus its per-song/take olof_songs rows
(see instructions/FABLE_OLOF_FILES.md §2-§4, §6 phases P2-P3).

Scope (P2): header fields, trailer fields (concert #, recording info, notes,
BobTalk, releases/references blobs, "Session info updated"), and the full
block raw_text.

Scope (P3): olof_songs — one row per numbered song/take. Chronicle parsing
is P4.

Song/take parsing (spec §2.1-§2.2, §6 P3):
    - Numbered song lines come in two layouts (same ambiguity as the
      concert-vs-session setlist marker _SETLIST_LINE_RE already handles):
      combined `N. Title (credits)` (concerts, e.g. DSN11050) and split-cell
      `N.` / `Title` / `take K: status` across separate paragraphs
      (sessions, e.g. DSN01225). A trailing `(...)` on the title line is a
      cover-credit annotation, captured into `credits`.
    - Studio take lines are `take K: status` OR — a source quirk confirmed
      on DSN01225 position 16 — a bare status word with no `take K:` prefix
      at all. Both populate `take_status`; only the former also populates
      `take_number`. Status vocabulary: complete/breakdown/rehearsal/false
      start/incomplete (case-insensitive in the source, normalized to
      lowercase).
    - A bare dash-only line (`—`, `–`, or `-` runs) is the encore
      separator: every song from that point on gets `is_encore=1`. It does
      not consume a position.
    - After the last song/take line, remaining trailer lines are scanned
      for `<position-list> <text>` lines (e.g. `6-10, 18 acoustic with the
      band.`, `1-13 released on CD 10 of ...`) and resolved per matching
      song position: lines containing "released on"/"available on" feed
      `released_on`; everything else feeds `annotations`; multiple hits per
      position are '; '-joined. Two guards keep this from misfiring:
      (a) the position-list line pattern requires a *space* after the last
      digit, which numbered song markers (`N.`, always a period) never
      have, so song lines can't be re-matched here; (b) any line matching
      `_LINEUP_RE` (a `Bob Dylan (...)` lineup line, e.g. `1-16 Bob Dylan
      (guitar...)`) is skipped outright so P2's lineup field is never
      shadowed — this specifically distinguishes lineup lines from the
      superficially similar `<positions> Bob Dylan <instrument>.` annotation
      lines (e.g. `4, 6, 8, 10, 13, 15, 18 Bob Dylan harmonica.`), which
      lack the `(` that makes a line a lineup credit. A resolved position
      that isn't one of the event's actual song positions (stray digits in
      Notes/References prose, catalog numbers, etc.) is silently dropped.
    - `run_parse` deletes and reinserts an event's olof_songs rows whenever
      its olof_events row is upserted, keeping reparse idempotent.

Word-HTML quirks handled (spec §2):
    - Attributes are largely unquoted and lines are hard-wrapped mid-phrase,
      so text is always joined per paragraph (via BeautifulSoup get_text)
      before any line-level regex runs.
    - Word's fake list bullets (Wingdings-font spans wrapping a single glyph,
      e.g. the "Notes." bullet) are stripped before text extraction so they
      don't pollute `notes`/`raw_text`. Genuine numbering (song position
      "1.", not Wingdings-styled) is left intact — it doubles as the "plain
      numbered setlist" signal used by the event_type heuristic below.
    - Word paragraph classes (Kroghead/Krog1/Krog2/Noteslista/Finstilt) vary
      across ~25 years of exports (confirmed: DSN11050 uses
      `<p class=Kroghead>` headers, DSN01225 uses bare `<h1>` headers for
      the same logical role) — segmentation is done by `<a name=DSNnnnnn>`
      anchor position and regex, never by class name alone.

event_type heuristic (documented per spec §6 P2 requirement), checked in
this order against the block's paragraph lines:
    1. Any line matching `take \\d+\\s*:` (take-notation) -> 'session'.
       This is checked first because it is the least ambiguous signal —
       'rehearsal'/'breakdown' etc. as *take statuses* must not leak into
       the rehearsal/broadcast keyword checks below.
    2. 'session' appears in the derived session_title -> 'session'.
    3. session_title contains a rehearsal / broadcast / interview keyword
       (interview includes 'press conference') -> 'rehearsal' / 'broadcast'
       / 'interview' respectively. Restricted to session_title (not the
       whole block) because those words appear incidentally elsewhere
       (e.g. take-status 'rehearsal', notes prose) without the whole event
       being one.
    4. A 'Concert # N of The Never-Ending Tour' trailer was found -> 'concert'.
       (Pre-1988 concerts predate the Never-Ending Tour and never set this.)
    5. Fallback: a venue was parsed AND at least one line looks like a
       numbered setlist entry ("N. Title..." or, in the split-cell table
       layout shared with studio takes, a bare "N." position marker) ->
       'concert'.
    6. Otherwise -> 'other' (observed causes: unparseable date ranges/
       'circa' dates that abort header parsing before venue is set,
       duplicate/collided anchors on one heading, and a handful of
       loosely-titled entries like conversations/soundchecks).

Robustness rule (spec §3): every event's full block text is preserved in
raw_text regardless of how well the structured columns parsed; run_parse()
logs a coverage report (anchors vs events, % ISO date, % venue, % recording
info) so markup drift surfaces as stats, not silent loss.

Public API:
    parse_page(path, filename, tour_name) ->
        (list[EventRecord], list[SongRecord], stats dict)
    run_parse(file, db_path, pages_dir) -> coverage summary dict

CLI:
    .venv/bin/python3 -m backend.olof_parser [--file <path-or-filename>]

Schema: olof_events, olof_songs (see db.py). Idempotent upsert (INSERT OR
REPLACE on event_id; DELETE + INSERT on event_id for that event's song
rows) — updates olof_pages.parsed_at/parse_status/event_count per page.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from backend.db import get_connection, init_db
from backend.olof_fetcher import PAGES_DIR

_log = logging.getLogger(__name__)

_MONTHS = {
    name.lower(): i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

_PARA_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6"]

_DSN_ANCHOR_RE = re.compile(r"^DSN(\d+)$", re.IGNORECASE)
_WINGDINGS_STYLE_RE = re.compile(r"font-family:\s*Wingdings", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")
_CONCERT_NET_RE = re.compile(
    r"Concert\s*#\s*(\d+)\s+of\s+The\s+Never-Ending\s+Tour", re.IGNORECASE
)
_CONCERT_YEAR_RE = re.compile(r"\b(\d{4})\s+concert\s*#\s*(\d+)", re.IGNORECASE)
_RECORDING_RE = re.compile(
    r"\b(?:Mono|Stereo|Multitrack|Unknown)?\s*"
    r"(audience|soundboard|studio|broadcast)\s+recordings?,?\s*(\d+)\s*minutes",
    re.IGNORECASE,
)
_SESSION_UPDATED_RE = re.compile(r"^Session info updated\b", re.IGNORECASE)
_LINEUP_RE = re.compile(r"Bob Dylan\s*\(")
_TAKE_NOTATION_RE = re.compile(r"\btake\s+\d+\s*:", re.IGNORECASE)
# Setlist position markers appear in two layouts across export eras: combined
# "1. Title" (single cell, e.g. DSN11050/1990) and split-cell "1." alone
# followed by the title in a separate paragraph (e.g. DSN1330/1966, and the
# take-status table shared with studio sessions) — both must be recognized.
_SETLIST_LINE_RE = re.compile(r"^\d+\.(\s+\S.*)?$")
_TOP_LINE_RE = re.compile(r"^\[\s*TOP\s*\]$", re.IGNORECASE)
_ORDINAL_SUP_RE = re.compile(r"\b(\d+) (st|nd|rd|th)\b")
_REHEARSAL_RE = re.compile(r"\brehearsal\b", re.IGNORECASE)
_BROADCAST_RE = re.compile(r"\b(broadcast|radio|television|tv)\b", re.IGNORECASE)
_INTERVIEW_RE = re.compile(r"\b(interview|press conference)\b", re.IGNORECASE)

# --- P3: song/take parsing -------------------------------------------------
# Combined-layout song line: "14. No More One More Time (Troy Seals-Dave Kirby)".
_SONG_LINE_RE = re.compile(r"^\d+\.\s+(\S.*)$")
# Bare position marker, split-cell layout: "16." with title on the next line.
_BARE_POSITION_RE = re.compile(r"^(\d+)\.$")
# Trailing "(cover credits)" on a title line.
_CREDITS_SUFFIX_RE = re.compile(r"^(.*\S)\s*\(([^()]*)\)\s*$")
# See _split_title_credits: caps how long a trailing "(...)" can be and
# still be treated as a cover-credit rather than part of the title itself.
_MAX_CREDIT_WORDS = 6
_TAKE_STATUSES = ("complete", "breakdown", "rehearsal", "false start", "incomplete")
# "take 1: breakdown" or a bare status with no "take K:" prefix at all (a
# confirmed source quirk, e.g. DSN01225 position 16 — see module docstring).
_TAKE_LINE_RE = re.compile(
    r"^(?:take\s+(\d+)\s*:\s*)?(" + "|".join(_TAKE_STATUSES) + r")$", re.IGNORECASE
)
_ENCORE_SEP_RE = re.compile(r"^[\-‑‒–—―]+$")
# "<position-list> <text>" trailer lines: annotation ranges
# ("6-10, 18 acoustic with the band.") and release ranges ("1-13 released on
# ..."). Requires a *space* (not a period) after the position list, which is
# what keeps this from ever re-matching a numbered song marker ("N.").
_POSITION_LIST_LINE_RE = re.compile(
    r"^(\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*)\s+(\S.*)$"
)
_RELEASE_KEYWORD_RE = re.compile(r"\b(released on|available on)\b", re.IGNORECASE)
_RELEASE_TITLE_RE = re.compile(r"^(?:released on|available on)\s+(.+)$", re.IGNORECASE)

_SONG_COLUMNS = [
    "event_id", "position", "song_title", "credits", "is_encore",
    "take_number", "take_status", "annotations", "released_on",
]

# Used to disambiguate a 2-part "City, X" header line: is X a region (US
# state, Canadian/Australian province) or a country? Best-effort per spec
# §7 (structured columns are best-effort; raw_text is the safety net).
_KNOWN_COUNTRIES = {
    "usa", "united states", "canada", "england", "scotland", "wales",
    "northern ireland", "ireland", "uk", "united kingdom", "france",
    "germany", "west germany", "east germany", "sweden", "norway",
    "denmark", "finland", "iceland", "netherlands", "belgium",
    "switzerland", "austria", "italy", "spain", "portugal", "japan",
    "australia", "new zealand", "brazil", "argentina", "chile", "colombia",
    "mexico", "israel", "south africa", "poland", "czech republic",
    "czechoslovakia", "hungary", "russia", "ussr", "soviet union", "greece",
    "turkey", "china", "south korea", "india", "singapore", "hong kong",
    "luxembourg", "yugoslavia", "slovenia", "croatia", "romania",
}

_EVENT_COLUMNS = [
    "event_id", "source", "page_filename", "event_type", "date_str",
    "date_raw", "venue", "city", "region", "country", "tour_name",
    "session_title", "concert_no_net", "concert_no_year", "lineup",
    "recording_info", "recording_kind", "recording_mins", "notes",
    "bobtalk", "releases_raw", "references_raw", "updated_raw", "raw_text",
]


@dataclass
class EventRecord:
    """One olof_events row (P2 scope: header + trailers + raw_text)."""

    event_id: int
    source: str = "dsn"
    page_filename: str = ""
    event_type: str = ""
    date_str: str = ""
    date_raw: str = ""
    venue: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    tour_name: str = ""
    session_title: str = ""
    concert_no_net: int | None = None
    concert_no_year: int | None = None
    lineup: str = ""
    recording_info: str = ""
    recording_kind: str = ""
    recording_mins: int | None = None
    notes: str = ""
    bobtalk: str = ""
    releases_raw: str = ""
    references_raw: str = ""
    updated_raw: str = ""
    raw_text: str = ""


@dataclass
class SongRecord:
    """One olof_songs row (P3 scope): a performed song or studio take."""

    event_id: int
    position: int
    song_title: str = ""
    credits: str = ""
    is_encore: int = 0
    take_number: int | None = None
    take_status: str = ""
    annotations: str = ""
    released_on: str = ""


# ---------------------------------------------------------------------------
# HTML -> per-paragraph clean text
# ---------------------------------------------------------------------------

def _clean_para_text(el) -> str:
    """Return whitespace-normalized text for a paragraph/heading element.

    Operates on a deep copy so the source soup tree (and therefore anchor
    lookups elsewhere) is never mutated. Strips Word's Wingdings-font bullet
    glyphs (the fake-list-marker spans used for `Notes.` bullets) while
    leaving genuine digit numbering (song position markers) intact.

    Args:
        el: A BeautifulSoup Tag for one paragraph/heading.

    Returns:
        Single-line, whitespace-collapsed text content.
    """
    dup = copy.deepcopy(el)
    for bad in dup.find_all(style=_WINGDINGS_STYLE_RE):
        bad.decompose()
    text = " ".join(dup.get_text(" ", strip=True).split())
    # Ordinal suffixes are commonly wrapped in <sup> ('3<sup>rd</sup>'), which
    # get_text's separator turns into '3 rd' — rejoin it.
    return _ORDINAL_SUP_RE.sub(r"\1\2", text)


# ---------------------------------------------------------------------------
# Event segmentation
# ---------------------------------------------------------------------------

def _locate_events(soup: BeautifulSoup) -> tuple[list, list[tuple[int, int]]]:
    """Find every DSN event anchor and its position in document order.

    Args:
        soup: Parsed page.

    Returns:
        (para_elements, anchors) where para_elements is every paragraph/
        heading tag in document order, and anchors is a list of
        (para_index, event_id) sorted by para_index — para_index is the
        index into para_elements of the paragraph containing the anchor.
    """
    para_elements = soup.find_all(_PARA_TAGS)
    index_by_id = {id(el): i for i, el in enumerate(para_elements)}
    anchors: list[tuple[int, int]] = []
    for a in soup.find_all("a", attrs={"name": True}):
        m = _DSN_ANCHOR_RE.match(a["name"].strip())
        if not m:
            continue
        container = a.find_parent(_PARA_TAGS)
        if container is None or id(container) not in index_by_id:
            _log.warning("olof_parser: DSN%s anchor has no paragraph container, skipped",
                         m.group(1))
            continue
        anchors.append((index_by_id[id(container)], int(m.group(1))))
    anchors.sort(key=lambda t: t[0])
    return para_elements, anchors


# ---------------------------------------------------------------------------
# Header (date / venue / city / region / country / session_title)
# ---------------------------------------------------------------------------

def _split_city_region_country(parts: list[str]) -> dict:
    """Classify comma-separated location parts into city/region/country.

    Shared by the DSN header parser and the chronicle appendix header
    parser (backend/olof_chronicle_parser.py) — same 'City[, Region]
    [, Country]' comma-split ambiguity applies to both corpora's headers.
    Best-effort per spec §7: a 2-part tail is a country if it matches
    `_KNOWN_COUNTRIES`, otherwise treated as a region (US state, Canadian/
    Australian province, ...).

    Args:
        parts: Already comma-split, stripped, non-empty location tokens
            (venue excluded — this only classifies what follows it).

    Returns:
        dict with keys city/region/country (each '' if not applicable).
    """
    fields = {"city": "", "region": "", "country": ""}
    if len(parts) == 1:
        fields["city"] = parts[0]
    elif len(parts) == 2:
        fields["city"] = parts[0]
        if parts[1].lower() in _KNOWN_COUNTRIES:
            fields["country"] = parts[1]
        else:
            fields["region"] = parts[1]
    elif len(parts) >= 3:
        fields["city"] = parts[0]
        fields["region"] = parts[1]
        fields["country"] = ", ".join(parts[2:])
    return fields


def _parse_header(lines: list[str], event_id: int) -> tuple[dict, int]:
    """Parse the venue/date header from the start of an event block.

    ``lines[0]`` is normally the bare event-id numeral (same paragraph as
    the anchor) and venue/location lines start at ``lines[1]``. One export
    layout (observed on repeat-venue rows, e.g. DSN1330) instead attaches
    the anchor directly to the venue heading, merging the id numeral away —
    detected by ``lines[0] != str(event_id)``, in which case venue/location
    lines start at ``lines[0]`` instead. The date line is searched for in
    the following few lines; everything between id/venue-start and date is
    treated as venue/location lines, and the last of those (immediately
    preceding the date) is split on commas into city/region/country.

    Args:
        lines: Clean paragraph text for the whole event block.
        event_id: This event's DSN number, used to detect the merged-row
            layout described above.

    Returns:
        (fields, date_idx) — fields has keys venue/city/region/country/
        date_str/date_raw; date_idx is the index of the date line in
        `lines`, or -1 if no date line was found in the header window.
    """
    fields = {"venue": "", "city": "", "region": "", "country": "",
              "date_str": "", "date_raw": ""}
    date_idx = -1
    for i, line in enumerate(lines[:8]):
        m = _DATE_LINE_RE.match(line)
        if not m:
            continue
        day, month_name, year = m.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            fields["date_raw"] = line
            fields["date_str"] = f"{int(year):04d}-{month:02d}-{int(day):02d}"
            date_idx = i
        break
    if date_idx < 0:
        return fields, -1

    header_start = 1 if lines[0].strip() == str(event_id) else 0
    loc_lines = [ln for ln in lines[header_start:date_idx] if ln]
    if not loc_lines:
        return fields, date_idx
    fields["venue"] = loc_lines[0]
    parts = [p.strip() for p in loc_lines[-1].split(",") if p.strip()]
    fields.update(_split_city_region_country(parts))
    return fields, date_idx


def _detect_session_title(lines: list[str], date_idx: int) -> str:
    """Return the studio-session title line, or '' for concerts/unknown.

    The paragraph immediately after the date line is a session_title (e.g.
    'The 3rd Blonde On Blonde session, produced by Bob Johnston.') unless
    it is itself the first numbered setlist entry, which marks a concert.

    Args:
        lines: Clean paragraph text for the whole event block.
        date_idx: Index of the date line, or -1 if none was found.

    Returns:
        The session_title text, or '' if not applicable/found.
    """
    if date_idx < 0 or date_idx + 1 >= len(lines):
        return ""
    candidate = lines[date_idx + 1]
    if _SETLIST_LINE_RE.match(candidate):
        return ""
    return candidate


# ---------------------------------------------------------------------------
# Trailer sections (Notes / BobTalk / Official releases / References /
# recording info / Session info updated)
# ---------------------------------------------------------------------------

def _classify_special_line(line: str) -> str | None:
    """Classify a line as a trailer-section boundary marker, if it is one."""
    key = line.strip().rstrip(".").lower()
    if key == "notes":
        return "notes"
    if key in ("bobtalk", "bobtalk:"):
        return "bobtalk"
    if key == "official releases":
        return "releases"
    if key == "references":
        return "references"
    if _RECORDING_RE.search(line):
        return "recording"
    if _SESSION_UPDATED_RE.match(line):
        return "updated"
    if _TOP_LINE_RE.match(line.strip()):
        return "top"
    return None


_SECTION_FIELD = {
    "notes": "notes",
    "bobtalk": "bobtalk",
    "releases": "releases_raw",
    "references": "references_raw",
}


def _extract_sections(lines: list[str], rec: EventRecord) -> None:
    """Fill notes/bobtalk/releases_raw/references_raw/recording_*/updated_raw.

    Walks the block once, marking every "special" line (section label,
    recording-info line, 'Session info updated' line, or the trailing
    '[TOP]' link) as a boundary; each label section's content runs from
    just after its label to the next boundary of any kind, so a following
    recording-info/updated/[TOP] line never leaks into `notes`/`bobtalk`/
    `releases_raw`/`references_raw`.

    Args:
        lines: Clean paragraph text for the whole event block.
        rec: EventRecord to fill in place.
    """
    specials = [(i, kind) for i, line in enumerate(lines)
                if (kind := _classify_special_line(line))]
    collected: dict[str, list[str]] = {}
    for idx, (pos, kind) in enumerate(specials):
        end = specials[idx + 1][0] if idx + 1 < len(specials) else len(lines)
        if kind in _SECTION_FIELD:
            content = "\n".join(ln for ln in lines[pos + 1:end] if ln).strip()
            if content:
                collected.setdefault(_SECTION_FIELD[kind], []).append(content)
        elif kind == "recording" and not rec.recording_info:
            line = lines[pos]
            m = _RECORDING_RE.search(line)
            rec.recording_info = line
            rec.recording_kind = m.group(1).lower()
            rec.recording_mins = int(m.group(2))
        elif kind == "updated" and not rec.updated_raw:
            rec.updated_raw = lines[pos]
    for field_name, parts in collected.items():
        setattr(rec, field_name, "\n\n".join(parts))


# ---------------------------------------------------------------------------
# event_type heuristic (see module docstring for the documented rules)
# ---------------------------------------------------------------------------

def _classify_event_type(rec: EventRecord, lines: list[str]) -> str:
    """Classify an event block into concert|session|rehearsal|broadcast|
    interview|other. Rules are documented in the module docstring."""
    title = rec.session_title.lower()
    if any(_TAKE_NOTATION_RE.search(ln) for ln in lines):
        return "session"
    if "session" in title:
        return "session"
    if _REHEARSAL_RE.search(title):
        return "rehearsal"
    if _BROADCAST_RE.search(title):
        return "broadcast"
    if _INTERVIEW_RE.search(title):
        return "interview"
    if rec.concert_no_net is not None:
        return "concert"
    if rec.venue and any(_SETLIST_LINE_RE.match(ln) for ln in lines):
        return "concert"
    return "other"


# ---------------------------------------------------------------------------
# Song/take parsing (P3 — see module docstring for the classification rules
# and the two false-positive guards the trailer-line scan relies on)
# ---------------------------------------------------------------------------

def _split_title_credits(text: str) -> tuple[str, str]:
    """Split a song title line into (title, credits).

    A trailing '(...)' is a cover-credit annotation (spec §2.1, e.g.
    'No More One More Time (Troy Seals-Dave Kirby)') UNLESS it's actually
    part of the official title itself — confirmed on 'I Don't Believe You
    (She Acts Like We Never Have Met)', which the corpus writes with no
    special marking to distinguish it from a real cover credit. Best-effort
    disambiguation (spec §7: structured columns are best-effort, raw_text
    is the safety net): credit annotations observed in the corpus are short
    composer-name lists (<= 6 words, e.g. 'Troy Seals-Dave Kirby', 'Bob
    Dylan & Robert Hunter'); a longer parenthetical reads as descriptive
    prose and is kept as part of the title instead.

    Args:
        text: The title portion of a song line, parens included if present.

    Returns:
        (title, credits) — credits is '' if there was no trailing '(...)'
        or the parenthetical looked like part of the title (see above).
    """
    m = _CREDITS_SUFFIX_RE.match(text)
    if m and len(m.group(2).split()) <= _MAX_CREDIT_WORDS:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


def _expand_position_list(spec: str) -> list[int]:
    """Expand a comma-separated position-list ('6-10, 18') into positions.

    Args:
        spec: The position-list token captured by _POSITION_LIST_LINE_RE,
            e.g. '6-10, 18' or '4, 6, 8, 10, 13, 15, 18'.

    Returns:
        Positions in the order/multiplicity they appear (ranges expanded).
    """
    positions: list[int] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo, hi = token.split("-", 1)
            positions.extend(range(int(lo.strip()), int(hi.strip()) + 1))
        else:
            positions.append(int(token))
    return positions


def _parse_song_lines(lines: list[str], start: int,
                       event_id: int) -> tuple[list[SongRecord], int]:
    """Walk the numbered song/take region of an event block from *start*.

    Handles both export layouts (module docstring): combined
    'N. Title (credits)' (one paragraph) and split-cell 'N.' / title /
    optional 'take K: status' (up to three separate paragraphs, sessions).
    A bare dash-only line toggles is_encore for every song from there on
    without consuming a position. Stops at the first line that is neither
    a song/take marker nor the encore separator, subject to two corpus
    quirks confirmed by running this over the full mirror:

    - Per-take/per-song personnel-credit trailer lines sometimes reuse the
      exact 'N. text' markup songs use (e.g. DSN2073: '1. Doug Sahm (vocal
      & piano), Bob Dylan (guitar), George Rains (drums), ...' right after
      a 3-song list) rather than the space-separated position-list style
      _POSITION_LIST_LINE_RE expects. A real song title has at most one
      trailing '(credits)' group; 2+ '(' in the candidate title text marks
      it as a personnel line instead, so the walk stops there (that line
      is left for the whole-block _LINEUP_RE scan in _parse_event, same as
      the space-separated case).
    - Olof's own numbering occasionally repeats a position it already used
      (e.g. DSN618: the encore song is mislabeled '15.' again instead of
      '16.'). Since olof_songs' primary key is (event_id, position), a
      repeat is renumbered to one past the highest position seen so far —
      preserving the extra song instead of dropping it or crashing.

    Args:
        lines: Clean paragraph text for the whole event block.
        start: Index of the first line that may be a song/encore marker.
        event_id: Copied onto every SongRecord.

    Returns:
        (songs, consumed_end) — songs in position order; consumed_end is
        the index of the first line not consumed by this walk, i.e. where
        trailer-line (annotation/release) scanning should begin.
    """
    songs: list[SongRecord] = []
    seen_positions: set[int] = set()
    is_encore = False
    i, n = start, len(lines)
    while i < n:
        line = lines[i]
        if _ENCORE_SEP_RE.match(line):
            is_encore = True
            i += 1
            continue
        bare = _BARE_POSITION_RE.match(line)
        combined = _SONG_LINE_RE.match(line)
        if bare:
            if i + 1 >= n:
                break
            position = int(bare.group(1))
            title_text = lines[i + 1]
            next_i = i + 2
        elif combined:
            position = int(line.split(".", 1)[0])
            title_text = combined.group(1)
            next_i = i + 1
        else:
            break
        if title_text.count("(") > 1:
            break  # personnel-credit trailer line, not a song (see above)
        i = next_i
        if position in seen_positions:
            renumbered = max(seen_positions) + 1
            _log.warning(
                "olof_parser: DSN%d position %d reused for %r — "
                "renumbered to %d (source numbering slip)",
                event_id, position, title_text, renumbered,
            )
            position = renumbered
        seen_positions.add(position)
        title, credits = _split_title_credits(title_text)
        take_number: int | None = None
        take_status = ""
        if i < n:
            tm = _TAKE_LINE_RE.match(lines[i])
            if tm:
                take_number = int(tm.group(1)) if tm.group(1) else None
                take_status = tm.group(2).lower()
                i += 1
        songs.append(SongRecord(
            event_id=event_id, position=position, song_title=title,
            credits=credits, is_encore=int(is_encore),
            take_number=take_number, take_status=take_status,
        ))
    return songs, i


def _resolve_annotations_and_releases(lines: list[str], consumed_end: int,
                                       songs: list[SongRecord]) -> None:
    """Apply trailer-line annotations/releases to *songs* in place.

    Scans lines[consumed_end:] for '<position-list> <text>' lines and
    resolves each onto the matching song position(s): a line containing
    'released on'/'available on' feeds released_on, everything else feeds
    annotations; multiple hits per position are '; '-joined. Lines matching
    _LINEUP_RE (a 'Bob Dylan (...)' lineup credit, e.g. '1-16 Bob Dylan
    (guitar...)') are skipped so P2's lineup field is never shadowed —
    see module docstring for why this doesn't also skip the superficially
    similar '<positions> Bob Dylan <instrument>.' annotation lines. A
    resolved position outside the event's actual song positions (stray
    digits elsewhere in the trailer prose) is dropped.

    Args:
        lines: Clean paragraph text for the whole event block.
        consumed_end: Index returned by _parse_song_lines — where the
            song/take region ended.
        songs: SongRecords to update in place (matched by .position).
    """
    by_position = {s.position: s for s in songs}
    annotations: dict[int, list[str]] = {}
    releases: dict[int, list[str]] = {}
    for line in lines[consumed_end:]:
        m = _POSITION_LIST_LINE_RE.match(line)
        if not m or _LINEUP_RE.search(line):
            continue
        positions = [p for p in _expand_position_list(m.group(1)) if p in by_position]
        if not positions:
            continue
        remainder = m.group(2).strip()
        if _RELEASE_KEYWORD_RE.search(remainder):
            rm = _RELEASE_TITLE_RE.match(remainder)
            text = (rm.group(1) if rm else remainder).rstrip(".").strip()
            bucket = releases
        else:
            text = remainder.rstrip(".").strip()
            bucket = annotations
        if not text:
            continue
        for pos in positions:
            bucket.setdefault(pos, []).append(text)
    for pos, song in by_position.items():
        if pos in annotations:
            song.annotations = "; ".join(annotations[pos])
        if pos in releases:
            song.released_on = "; ".join(releases[pos])


def _parse_event_songs(lines: list[str], date_idx: int, session_title: str,
                        event_id: int) -> list[SongRecord]:
    """Parse an event block's numbered song/take rows into SongRecords.

    Args:
        lines: Clean paragraph text for the whole event block.
        date_idx: Index of the header date line (see _parse_header), or -1
            if none was found — without it there's no reliable starting
            point, so no songs are parsed.
        session_title: This event's already-computed session_title; a
            non-empty value means lines[date_idx + 1] is that paragraph,
            not a song line, and must be skipped.
        event_id: This event's DSN number, copied onto every SongRecord.

    Returns:
        SongRecords in position order, with annotations/released_on
        resolved from the trailer lines following the last song/take row.
    """
    if date_idx < 0:
        return []
    start = date_idx + (2 if session_title else 1)
    songs, consumed_end = _parse_song_lines(lines, start, event_id)
    if songs:
        _resolve_annotations_and_releases(lines, consumed_end, songs)
    return songs


# ---------------------------------------------------------------------------
# Per-event assembly
# ---------------------------------------------------------------------------

def _parse_event(lines: list[str], event_id: int, page_filename: str,
                  tour_name: str) -> tuple[EventRecord, list[SongRecord]]:
    """Build one EventRecord and its SongRecords from an event block."""
    rec = EventRecord(event_id=event_id, page_filename=page_filename,
                       tour_name=tour_name, raw_text="\n".join(lines))

    header, date_idx = _parse_header(lines, event_id)
    rec.venue, rec.city = header["venue"], header["city"]
    rec.region, rec.country = header["region"], header["country"]
    rec.date_str, rec.date_raw = header["date_str"], header["date_raw"]
    rec.session_title = _detect_session_title(lines, date_idx)

    joined = " ".join(lines)
    m = _CONCERT_NET_RE.search(joined)
    if m:
        rec.concert_no_net = int(m.group(1))
    m = _CONCERT_YEAR_RE.search(joined)
    if m:
        rec.concert_no_year = int(m.group(2))
    rec.lineup = "; ".join(ln for ln in lines if _LINEUP_RE.search(ln))

    _extract_sections(lines, rec)
    rec.event_type = _classify_event_type(rec, lines)
    songs = _parse_event_songs(lines, date_idx, rec.session_title, event_id)
    return rec, songs


def parse_page(path: Path, filename: str,
                tour_name: str) -> tuple[list[EventRecord], list[SongRecord], dict]:
    """Parse one local DSN page into EventRecords and SongRecords.

    Args:
        path: On-disk path to the mirrored (or sample) HTML file.
        filename: olof_pages.filename key this page is recorded under.
        tour_name: Segment title (olof_pages.segment_title), copied onto
            every event's tour_name.

    Returns:
        (events, songs, stats) — stats has 'anchors' (DSN anchors found)
        and 'events' (records successfully emitted).
    """
    raw = path.read_bytes()
    text = raw.decode("windows-1252", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    para_elements, anchors = _locate_events(soup)

    events: list[EventRecord] = []
    songs: list[SongRecord] = []
    for idx, (para_idx, event_id) in enumerate(anchors):
        end_idx = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(para_elements)
        block_elements = para_elements[para_idx:end_idx]
        lines = [t for t in (_clean_para_text(el) for el in block_elements) if t]
        if not lines:
            _log.warning("olof_parser: %s DSN%d — empty block, skipped", filename, event_id)
            continue
        rec, event_songs = _parse_event(lines, event_id, filename, tour_name)
        events.append(rec)
        songs.extend(event_songs)

    return events, songs, {"anchors": len(anchors), "events": len(events)}


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _ensure_page_row(conn, filename: str, path: Path, segment_title: str,
                      corpus: str = "dsn", year: int | None = None) -> None:
    """Register a minimal olof_pages row if *filename* isn't tracked yet.

    olof_events.page_filename is a foreign key (PRAGMA foreign_keys=ON, see
    db.py get_connection) so ad-hoc `--file` reparses of untracked pages
    (e.g. data/olof/samples/ dev fixtures) need a parent row first. Shared
    with backend.olof_chronicle_parser (corpus='chronicle', year set) —
    *corpus*/*year* default to the original DSN-only behavior so this call
    is unchanged for olof_parser itself.

    Args:
        conn: Open connection (see run_parse — written to directly, not via
            the shared write-queue singleton, per BUG-246: this parser
            always knows its own db_path and must not risk a
            first-caller-wins queue bound elsewhere).
        filename: olof_pages.filename key.
        path: On-disk file, hashed if a row must be created.
        segment_title: Used as segment_title if a row must be created.
        corpus: olof_pages.corpus value ('dsn' or 'chronicle').
        year: olof_pages.year value (chronicle pages only).
    """
    if conn.execute("SELECT 1 FROM olof_pages WHERE filename = ?", (filename,)).fetchone():
        return
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    conn.execute(
        """INSERT INTO olof_pages (filename, url, corpus, segment_title, year, sha256, fetched_at)
           VALUES (?, '', ?, ?, ?, ?, ?)""",
        (filename, corpus, segment_title, year, sha256, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()


def _upsert_events(conn, events: list[EventRecord]) -> None:
    """Idempotently write *events* (INSERT OR REPLACE, keyed on event_id)."""
    if not events:
        return
    columns = ", ".join(_EVENT_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in _EVENT_COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO olof_events ({columns}) VALUES ({placeholders})",
        [asdict(rec) for rec in events],
    )
    conn.commit()


def _upsert_songs(conn, events: list[EventRecord], songs: list[SongRecord]) -> None:
    """Idempotently write *songs* for the events just (re)parsed.

    Deletes each parsed event's existing olof_songs rows first — keyed
    explicitly on event_id rather than relying on the olof_songs -> olof_
    events ON DELETE CASCADE firing on _upsert_events' implicit replace —
    then inserts the freshly parsed set. A page reparsed to zero songs for
    an event (e.g. a markup-drift regression) correctly clears its stale
    rows instead of leaving orphaned ones behind.

    Args:
        conn: Open connection (see _ensure_page_row for why this writes
            directly rather than via the shared write-queue singleton).
        events: The events just upserted — defines which event_ids' song
            rows to clear, including events that now parse to zero songs.
        songs: The freshly parsed SongRecords to insert.
    """
    if not events:
        return
    conn.executemany("DELETE FROM olof_songs WHERE event_id = ?",
                      [(rec.event_id,) for rec in events])
    if songs:
        columns = ", ".join(_SONG_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in _SONG_COLUMNS)
        conn.executemany(
            f"INSERT INTO olof_songs ({columns}) VALUES ({placeholders})",
            [asdict(s) for s in songs],
        )
    conn.commit()


def _update_page_status(conn, filename: str, parsed_at: str, status: str,
                         event_count: int) -> None:
    """Update olof_pages bookkeeping columns for *filename*, if tracked."""
    conn.execute(
        """UPDATE olof_pages SET parsed_at = ?, parse_status = ?, event_count = ?
           WHERE filename = ?""",
        (parsed_at, status, event_count, filename),
    )
    conn.commit()


def _resolve_file_path(file_arg: str, pages_dir: Path) -> Path:
    """Resolve --file to an on-disk path: a direct path, or a bare filename
    under *pages_dir*."""
    p = Path(file_arg)
    if p.exists():
        return p
    candidate = pages_dir / file_arg
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"olof_parser: no such file {file_arg!r} "
                             f"(checked as-is and under {pages_dir})")


def _pct(numerator: int, denominator: int) -> float:
    """Percentage, 1 decimal place, 0.0 for a zero denominator."""
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_parse(file: str | None = None, db_path: str | None = None,
              pages_dir: Path | None = None) -> dict:
    """Parse local DSN pages into olof_events, upsert, and report coverage.

    Default mode parses every corpus='dsn' olof_pages row whose file exists
    under *pages_dir*. `file` reparses a single page instead — a direct
    path (may be outside pages_dir, e.g. a data/olof/samples/ fixture) or a
    bare filename looked up under pages_dir.

    Args:
        file: Optional single-page override (path or bare filename).
        db_path: Optional DB path override.
        pages_dir: Optional override of the mirror directory (tests).

    Returns:
        Coverage summary dict: pages_parsed/pages_ok/pages_partial/
        pages_error, anchors_found, events_emitted, pct_iso_date,
        pct_venue, pct_recording_info, event_type_counts, songs_emitted,
        pct_concert_events_with_songs (P3 coverage: share of event_type=
        'concert' events with >= 1 olof_songs row).
    """
    resolved_pages_dir = pages_dir or PAGES_DIR
    init_db(db_path)
    conn = get_connection(db_path)

    if file:
        path = _resolve_file_path(file, resolved_pages_dir)
        filename = path.name
        row = conn.execute(
            "SELECT segment_title FROM olof_pages WHERE filename = ?", (filename,)
        ).fetchone()
        _ensure_page_row(conn, filename, path, segment_title=row[0] if row else "")
        tasks = [(path, filename, row[0] if row else "")]
    else:
        rows = conn.execute(
            "SELECT filename, segment_title FROM olof_pages WHERE corpus = 'dsn'"
        ).fetchall()
        tasks = [
            (resolved_pages_dir / r[0], r[0], r[1])
            for r in rows if (resolved_pages_dir / r[0]).exists()
        ]

    pages_ok = pages_partial = pages_error = 0
    total_anchors = total_events = total_songs = 0
    events_with_date = events_with_venue = events_with_recording = 0
    concert_events = concert_events_with_songs = 0
    type_counts: dict[str, int] = {}

    for path, filename, tour_name in tasks:
        parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            events, songs, stats = parse_page(path, filename, tour_name)
        except Exception as exc:  # noqa: BLE001 — page-level isolation (spec §3 robustness rule)
            _log.error("olof_parser: failed to parse %s: %s", filename, exc)
            _update_page_status(conn, filename, parsed_at, f"error:{exc}"[:200], 0)
            pages_error += 1
            continue

        anchors = stats["anchors"]
        total_anchors += anchors
        total_events += len(events)
        total_songs += len(songs)
        if anchors == 0 or len(events) == anchors:
            status = "ok"
            pages_ok += 1
        else:
            status = "partial"
            pages_partial += 1

        _upsert_events(conn, events)
        _upsert_songs(conn, events, songs)
        _update_page_status(conn, filename, parsed_at, status, len(events))

        songs_by_event: dict[int, int] = {}
        for song in songs:
            songs_by_event[song.event_id] = songs_by_event.get(song.event_id, 0) + 1
        for rec in events:
            if rec.date_str:
                events_with_date += 1
            if rec.venue:
                events_with_venue += 1
            if rec.recording_info:
                events_with_recording += 1
            type_counts[rec.event_type] = type_counts.get(rec.event_type, 0) + 1
            if rec.event_type == "concert":
                concert_events += 1
                if songs_by_event.get(rec.event_id, 0) > 0:
                    concert_events_with_songs += 1

    summary = {
        "pages_parsed": len(tasks),
        "pages_ok": pages_ok,
        "pages_partial": pages_partial,
        "pages_error": pages_error,
        "anchors_found": total_anchors,
        "events_emitted": total_events,
        "pct_iso_date": _pct(events_with_date, total_events),
        "pct_venue": _pct(events_with_venue, total_events),
        "pct_recording_info": _pct(events_with_recording, total_events),
        "event_type_counts": type_counts,
        "songs_emitted": total_songs,
        "pct_concert_events_with_songs": _pct(concert_events_with_songs, concert_events),
    }
    _log.info(
        "olof_parser: coverage — pages=%d (ok=%d partial=%d error=%d) anchors=%d "
        "events=%d date=%.1f%% venue=%.1f%% recording=%.1f%% types=%s "
        "songs=%d concert_w_songs=%.1f%%",
        summary["pages_parsed"], pages_ok, pages_partial, pages_error,
        total_anchors, total_events, summary["pct_iso_date"],
        summary["pct_venue"], summary["pct_recording_info"], type_counts,
        total_songs, summary["pct_concert_events_with_songs"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Olof Björner DSN session pages into olof_events."
    )
    parser.add_argument("--file", default=None,
                         help="Reparse a single page (path or bare filename "
                              "under data/olof/pages/).")
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    _args = _parse_args()
    _summary = run_parse(file=_args.file)
    _log.info("olof_parser: summary %s", _summary)
