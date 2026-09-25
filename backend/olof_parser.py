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
      Lines inside a BobTalk or References section are never scanned (P1g).
    - Guest/interlude sets (a `Name:` header plus unnumbered titles between
      numbered songs, e.g. 1975-12-08, 1986-02-24) are skipped and the walk
      resumes at the next numbered song; guest songs are not stored (P1a).
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
       (interview includes 'press conference'; 'soundcheck' counts as rehearsal)
       -> 'rehearsal' / 'broadcast' / 'interview' respectively. Restricted to session_title (not the
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

from bs4 import BeautifulSoup, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction

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
# An optional "– Afternoon" / "— Evening" suffix marks a two-show day (1974); date_raw keeps it.
_DATE_LINE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s*[-–—]\s*[A-Za-z][A-Za-z ]*)?$")
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
_LINEUP_RE = re.compile(r"Bob Dylan(?:\s+solo)?\s*\(")
# B1 (golden-dossier plan, phase B): shares the instrument vocabulary
# dossier_fields._INSTRUMENT_RE uses for the same purpose downstream (kept as
# a local copy — olof_parser must not import the field-rendering module).
_INSTRUMENT_WORD_RE = re.compile(
    r"\b(harmonica|harp|piano|organ|keyboards?|guitar|bass|drums?|violin|fiddle|"
    r"banjo|mandolin|vocals?|percussion|slide|pedal steel|accordion)\b",
    re.IGNORECASE,
)
# B1: a "Name (instrument words)" clause, standing alone or comma-joined with
# others ("Doug Sahm (vocal & piano), Bob Dylan (guitar), George Rains
# (drums)") — a personnel-credit trailer line reusing the 'N. text' markup a
# song title uses, not an actual song. Deliberately does NOT require the whole
# candidate text to be covered: it only needs to find 2+ such clauses.
_PERSONNEL_CLAUSE_RE = re.compile(
    r"[A-Z][\w.’'\-]*(?:\s+[A-Z][\w.’'\-]*){0,4}\s*\(([^()]*)\)"
)


def _is_personnel_line(text: str) -> bool:
    """True when *text* reads as a multi-person credits roster, not a title.

    B1: replaces the old ``title_text.count("(") > 1`` guard, which also
    tripped on legitimate double-parenthetical titles — "I Walk The Line
    ( John ny Cash) / Blue Moon Of Kentucky (Bill Monroe)" (1999-06-11) and
    "Hey La La (Hey La La) (McBride)" (1989-06-13), neither of which has any
    instrument word in either parenthetical. Requires 2+ "Name (...)" clauses
    where every parenthetical names an instrument.

    Args:
        text: A song-position candidate title (the text after 'N.').

    Returns:
        Whether every "Name (...)" clause found names an instrument, and
        there are at least two of them.
    """
    clauses = list(_PERSONNEL_CLAUSE_RE.finditer(text))
    if len(clauses) < 2:
        return False
    # Not "every clause" — a real roster names instruments _INSTRUMENT_WORD_RE
    # doesn't cover (dobro, sax, trumpet, ...), and requiring 100% coverage
    # missed DSN2073's 9-person line (4/9 matched). 2+ hits is still nothing a
    # song title's own credits/subtitle parens produce (see the "I Walk The
    # Line"/"Hey La La" cases above, both 0 hits).
    return sum(1 for c in clauses if _INSTRUMENT_WORD_RE.search(c.group(1))) >= 2
_TAKE_NOTATION_RE = re.compile(r"\btake\s+\d+\s*:", re.IGNORECASE)
# Setlist position markers appear in two layouts across export eras: combined
# "1. Title" (single cell, e.g. DSN11050/1990) and split-cell "1." alone
# followed by the title in a separate paragraph (e.g. DSN1330/1966, and the
# take-status table shared with studio sessions) — both must be recognized.
_SETLIST_LINE_RE = re.compile(r"^\d+\.(\s+\S.*)?$")
_TOP_LINE_RE = re.compile(r"^\[\s*TOP\s*\]$", re.IGNORECASE)
_ORDINAL_SUP_RE = re.compile(r"\b(\d+) (st|nd|rd|th)\b")
# BUG-337: block-level elements are the only place a separator belongs — every
# other tag in Word's export is an inline formatting run whose boundary a
# browser renders with no space at all. See _extract_text.
_BLOCK_LEVEL_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1",
    "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
    "p", "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead",
    "tr", "ul",
})
# Elements whose text content is never document text.
_NON_TEXT_TAGS = frozenset({"script", "style", "title", "head"})
_REHEARSAL_RE = re.compile(r"\brehearsal\b", re.IGNORECASE)
_BROADCAST_RE = re.compile(r"\b(broadcast|radio|television|tv)\b", re.IGNORECASE)
_INTERVIEW_RE = re.compile(r"\b(interview|press conference)\b", re.IGNORECASE)

# --- P3: song/take parsing -------------------------------------------------
# Combined-layout song line: "14. No More One More Time (Troy Seals-Dave Kirby)".
_SONG_LINE_RE = re.compile(r"^\d+\.\s+(\S.*)$")
# Bare position marker, split-cell layout: "16." with title on the next line.
_BARE_POSITION_RE = re.compile(r"^(\d+)\.$")
# Longest unnumbered in-set block (The Band's 1974 sets run 4-6 songs) skipped
# without a guest header; a longer run is trailer prose, so the walk stops.
_MAX_UNNUMBERED_BLOCK = 12
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
# B3 (golden-dossier plan, phase B): a period followed by a FRESH position
# list marks a second, unrelated clause riding on the same physical line
# ("11, 23, 25 Bob Dylan and Tom Petty (shared vocals). 17 Howie Epstein
# (slide guitar), Tom Petty (bass).", 1986-02-24) — without this split, "17
# Howie Epstein ..." was swallowed into positions 11/23/25's annotation text
# instead of resolving onto position 17. Not applied to a release line's
# remainder (see _apply_position_clause) — a release title can itself
# contain "vol. 5 -" and similar false triggers.
_CLAUSE_SPLIT_RE = re.compile(r"\.\s+(?=\d+[\s,–-])")
# P1a: a guest/interlude header ("Bob Neuwirth:", "Tom Petty & The Heartbreakers:")
# is a short line ending in ':' — see _is_guest_header.
_GUEST_HEADER_MAX_CHARS = 60
# A bootleg-listing header, optionally naming the media ("CD bootlegs", "DVD
# bootleg", "LP bootlegs", "Vinyl bootleg") — the silver-dossier review found
# BobTalk running on into these (event 1135, 1965-09-03: "CD bootlegs";
# 6 events, all 1965/66, carry a media-prefixed header inside bobtalk).
_BOOTLEG_HEADER_RE = re.compile(
    r"^(?:(?:cd|dvd|lp|vinyl|video)\s+)?bootlegs?$", re.IGNORECASE
)
# P1g: labels that close a BobTalk/References section in the trailer scan. Wider
# than _classify_special_line on purpose ("Official release" singular, "Unauthorized
# releases", "Bootlegs") — the section fields themselves are unchanged.
_SECTION_END_RE = re.compile(
    r"^(?:(?:(?:cd|dvd|lp|vinyl|video)\s+)?bootlegs?|references?|notes?|"
    r"(?:(?:official|unauthori[sz]ed)\s+)?releases?)[.:]?$", re.IGNORECASE
)
# B2 (golden-dossier plan, phase B): "Bootlegs"/"References" as a standalone
# label are caught by _SECTION_END_RE above via _classify_special_line's exact
# `key ==` checks; this catches the inline form the corpus also uses — content
# on the SAME line as the label ("Reference. Les Kokay: Bob Dylan/The Band
# (a collector's guide to the 74 Tour). Private publication 2000, page 9.",
# DSN2260) — so it still opens a boundary and doesn't leak into the open
# BobTalk/Notes section (~224 events; previously the Reference/Bootlegs text
# ran straight into `bobtalk`).
_TRAILER_INLINE_RE = re.compile(r"^(bootlegs?|references?)[.:]?\s+(\S.*)$", re.IGNORECASE)
# P1g: a single-position line inside that prose is still scanned when it reads as
# release/recording trailer data ("17 released in mono ...", "1 stereo audience recording").
_PROSE_KEEP_RE = re.compile(r"\b(released|available|recording)\b", re.IGNORECASE)
# P1f: "released on/in/as", "available on/as/from" all mark a release line ("5 released in
# remastered version on ...", "7 available as a download"). B4 (golden-dossier plan, phase
# B) widens this with "released both as" ("7 released both as audio on the bonus CD...",
# 1975-12-04) and "included in" ("5, 19 and parts of 3, 12 are included in the film ...",
# same event).
_RELEASE_KEYWORD_RE = re.compile(
    r"\b(?:released\s+(?:on|in|as|both\s+as)|available\s+(?:on|as|from)|included\s+in)\b",
    re.IGNORECASE)
# Only the plain "released on X" / "available on X" wording is cut down to the title X;
# "partly" / "fragment(s)" mark every position on the line as a partial release.
_RELEASE_TITLE_RE = re.compile(
    r"^(?:(partly|fragments?)\s+)?(?:released|available)\s+on\s+(.+)$", re.IGNORECASE)
# P1f: one item of a release line's position list, "4", "6-8", ", and part of 22", "or 3"
# ("4, 9, 16 and part of 22 released on ...", "1 or 2, 10 or 11, 12 released on ..."). B4
# (golden-dossier plan, phase B) widens "part of" to also accept plural "parts of" ("5, 19
# and parts of 3, 12 are included in the film ...", 1975-12-04) and lets a "( ... )" aside
# after the number ride along without breaking the chain ("5, 6, 7 (first verse exluded),
# 11, 19, 20 released in the movie ...", same event) — otherwise the item scan stopped dead
# at the aside and positions 11/19/20 were lost off the end of the line.
_RELEASE_ITEM_RE = re.compile(
    r"\s*(,\s*(?:and|or)?|and|or)?\s*(parts?\s+of\s+)?(\d+)(?:\s*-\s*(\d+))?"
    r"(?:\s*\([^()]*\))?(?=[\s,]|$)",
    re.IGNORECASE,
)
# Prefixes on a released_on token: the song is only partly on the release, or Olof names two
# positions with "or" and the release holds one of them.
RELEASE_PART_TAG = "(part) "
RELEASE_UNCERTAIN_TAG = "(uncertain) "

# P1d: Olof's rotation stat, "13 new songs (72%) compared to previous concert. 2 new songs
# for this tour." The halves also sit on separate lines, and the corpus has typos
# ("conc ert"), "Only", "(additional)", "out of N" and "!!" variants. Text after the stat on
# the same line ("Same setlist as ...", a recording line) is kept.
ROTATION_PREV_RE = re.compile(
    r"(?:\bonly\s+)?(?:\b(\d+|no|one)\s+)?new\s+(?:\(additional\)\s+)?songs?\s*"
    r"(?:\(\s*(\d+)\s*%[\s!]*\)\s*)?(?:out\s+of\s+\d+\s+)?"
    r"compared\s+to\s+previous\s+conc\s*ert\s*(?:\(!\))?(?:\s*[.!])*",
    re.IGNORECASE,
)
ROTATION_TOUR_RE = re.compile(
    r"(?:\b(probably)\s+)?\b(\d+|no|one)\s+(possible\s+)?new\s*(?:\([^)]*\)\.?\s*)?songs?\s*"
    r"(?:\(\s*\d+\s*%\s*\)\s*)?for\s+this\s+tour(?:\s*[.!])*",
    re.IGNORECASE,
)
ROTATION_LESS_RE = re.compile(
    r"\bone\s+song\s+less\s+compared\s+to\s+previous\s+concert(?:\s*[.!])*", re.IGNORECASE
)
_COUNT_WORDS = {"no": 0, "one": 1}
# P1b/P1c: the "Other Bob Dylan concerts in <city>:" list — a header, then entries of a
# date line ("1 March 1978", "12-13 May 1995", "Late September 1961", "8 maj 1984"; the
# month is matched on its first three letters, which also covers "Noveber" and Swedish)
# followed by a venue line, or both on one line ("23 May 1992 Civic Centre").
VENUE_HISTORY_HEADER_RE = re.compile(
    r"\bBob Dylan\s+(?:shows|concerts)\s+in\b|\b(?:other|previous|next)\s+(?:shows|concerts)\b",
    re.IGNORECASE,
)
_MONTH_WORD = r"(?:jan|feb|mar|apr|ma[yj]|jun|jul|aug|sep|o[ck]t|nov|dec)[a-z]{0,7}\.?"
_HISTORY_DATE_HEAD = (
    r"^(?:(?:early|mid|late)[\s-]+)?(?:\d{1,2}(?:\s*(?:[-–,&]|or|and)\s*\d{1,2})*\s+)?"
    + _MONTH_WORD + r"(?:\s*[-–]\s*\d{1,2}\s+" + _MONTH_WORD + r")?(?:\s+\d{1,2},)?\s+\d{4}\b"
)
_HISTORY_ENTRY_RE = re.compile(_HISTORY_DATE_HEAD, re.IGNORECASE)
# A date line with nothing after it but "(2 shows)", "- Afternoon" or a stray digit.
HISTORY_DATE_RE = re.compile(
    _HISTORY_DATE_HEAD + r"(?:\s*\([^)]{1,20}\)|\s*[-–]\s*[A-Za-z ]{1,15}|\s+\d{1,2})?\s*\.?$",
    re.IGNORECASE,
)

_SONG_COLUMNS = [
    "event_id", "position", "song_title", "credits", "is_encore",
    "take_number", "take_status", "annotations", "released_on", "subtitle",
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
    "rotation_new", "rotation_pct", "tour_new_count", "venue_history_raw",
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
    # Show-dossier redesign Phase 1 (TODO-342, fixes P1c/P1d). bobserve rows
    # never carry these trailer lines, so they stay NULL / '' there.
    rotation_new: int | None = None
    rotation_pct: int | None = None
    tour_new_count: int | None = None
    venue_history_raw: str = ""


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
    subtitle: str = ""  # parenthetical alternate title, not a credit (TODO-342 P1e)


# ---------------------------------------------------------------------------
# HTML -> per-paragraph clean text
# ---------------------------------------------------------------------------

def _extract_text(el) -> str:
    """Concatenate an element's text the way a browser lays it out.

    BUG-337: the previous implementation joined *every* descendant string
    with a ``" "`` separator, which put a space at every inline tag boundary.
    Word's exports break words across inline runs constantly — smart tags
    (``Born In <st1:PersonName>Tim</st1:PersonName>e``), spell-check spans
    (``<span class=SpellE>Blowin</span>' In The Wind``) and plain formatting
    spans (``<span>Blowin</span><span>' In The Wind</span>``) — so the
    separator landed mid-word and split one song into several titles.

    Inline boundaries carry no whitespace in CSS, so inline runs are
    concatenated with nothing between them: every genuine word space is
    already inside the text nodes. A separator is emitted only where a
    block-level element starts or ends, which is where a browser would break
    the line.

    Args:
        el: A BeautifulSoup Tag to extract text from.

    Returns:
        The element's text, separators inserted at block boundaries only.
        Not yet whitespace-collapsed.
    """
    parts: list[str] = []
    for node in el.descendants:
        if isinstance(node, NavigableString):
            # Comment/Doctype/PI are NavigableString subclasses — never text.
            if isinstance(node, (Comment, Doctype, ProcessingInstruction, Declaration)):
                continue
            if node.parent is not None and node.parent.name in _NON_TEXT_TAGS:
                continue
            parts.append(str(node))
        elif node.name in _BLOCK_LEVEL_TAGS:
            parts.append(" ")
    return "".join(parts)


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
    text = " ".join(_extract_text(dup).split())
    # Ordinal suffixes are commonly wrapped in <sup> ('3<sup>rd</sup>'). That is
    # an inline tag, so block-level extraction no longer splits it; the rejoin
    # stays as a safety net for a source that puts real whitespace there.
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
            layout described above. A letterless ``lines[0]`` is treated as the
            numeral too, even when it isn't ``str(event_id)`` (BUG-350).

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

    # The numeral line isn't always str(event_id): Word exports split it ("4 0450") or
    # print a different number ("1495" on DSN01490). No venue is letterless, so skip any.
    first = lines[0].strip()
    header_start = 1 if first == str(event_id) or (
        first and not any(c.isalpha() for c in first)) else 0
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
    if key in ("reference", "references"):
        return "references"
    if _BOOTLEG_HEADER_RE.match(key):
        return "bootlegs"
    if _RECORDING_RE.search(line):
        return "recording"
    if _SESSION_UPDATED_RE.match(line):
        return "updated"
    if _TOP_LINE_RE.match(line.strip()):
        return "top"
    # B2: the inline "Reference. <content>" / "Bootlegs. <content>" form —
    # a label followed by content on the same physical line.
    if m := _TRAILER_INLINE_RE.match(line.strip()):
        label = m.group(1).lower()
        return "bootlegs" if label.startswith("bootleg") else "references"
    return None


_SECTION_FIELD = {
    "notes": "notes",
    "bobtalk": "bobtalk",
    "releases": "releases_raw",
    "references": "references_raw",
}


def _count(word: str | None) -> int | None:
    if word is None:
        return None
    return _COUNT_WORDS.get(word.lower(), int(word) if word.isdigit() else None)


def _strip_rotation_stat(line: str, rec: EventRecord) -> str:
    """P1d: record the first rotation stat on *rec*; return *line* without it.

    'No new songs compared to previous concert' implies 0%. A hedged tour count
    ('Probably 1 new song', '1 possible new song') leaves tour_new_count NULL.
    """
    m = ROTATION_PREV_RE.search(line)
    if m and rec.rotation_new is None and rec.rotation_pct is None:
        rec.rotation_new = _count(m.group(1))
        rec.rotation_pct = int(m.group(2)) if m.group(2) else (
            0 if rec.rotation_new == 0 else None)
    t = ROTATION_TOUR_RE.search(line)
    if t and rec.tour_new_count is None and not (t.group(1) or t.group(3)):
        rec.tour_new_count = _count(t.group(2))
    if not (m or t or ROTATION_LESS_RE.search(line)):
        return line
    for rx in (ROTATION_PREV_RE, ROTATION_TOUR_RE, ROTATION_LESS_RE):
        line = rx.sub(" ", line)
    line = " ".join(line.split())
    return line if re.search(r"\w", line) else ""


def _is_history_venue(line: str) -> bool:
    return bool(line) and not (
        _HISTORY_ENTRY_RE.match(line) or VENUE_HISTORY_HEADER_RE.search(line)
        or _classify_special_line(line) or _SECTION_END_RE.match(line.strip()))


def _clean_trailer_lines(lines: list[str], rec: EventRecord) -> list[str]:
    """P1c/P1d: lift the venue-history lists and the rotation stat out of the block.

    Fills rec.rotation_* / tour_new_count and rec.venue_history_raw, and returns a copy
    of *lines* (same length, so indices still line up) with the stat text cut and every
    venue-history line blanked. Section content and the annotation scan read this copy.

    Args:
        lines: Clean paragraph text for the whole event block.
        rec: EventRecord to fill in place.

    Returns:
        The cleaned lines; a blanked line is ''.
    """
    cleaned = [_strip_rotation_stat(ln, rec) for ln in lines]
    blobs: list[str] = []
    i, n = 0, len(cleaned)
    while i < n:
        if not VENUE_HISTORY_HEADER_RE.search(cleaned[i]):
            i += 1
            continue
        j = i + 1
        while j < n and cleaned[j] and _HISTORY_ENTRY_RE.match(cleaned[j]):
            pure_date = HISTORY_DATE_RE.match(cleaned[j])
            j += 1
            if pure_date and j < n and _is_history_venue(cleaned[j]):
                j += 1
        if j == i + 1:  # a header with no dated entries is prose ("First Bob Dylan ...")
            i += 1
            continue
        blobs.append("\n".join(cleaned[i:j]))
        cleaned[i:j] = [""] * (j - i)
        i = j
    rec.venue_history_raw = "\n\n".join(blobs)
    return cleaned


def _extract_sections(lines: list[str], rec: EventRecord,
                      text_lines: list[str] | None = None) -> None:
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
        text_lines: Same-length copy of *lines* that section content is taken
            from (_clean_trailer_lines output); boundaries still come from *lines*.
    """
    text_lines = lines if text_lines is None else text_lines
    specials = [(i, kind) for i, line in enumerate(lines)
                if (kind := _classify_special_line(line))]
    collected: dict[str, list[str]] = {}
    for idx, (pos, kind) in enumerate(specials):
        end = specials[idx + 1][0] if idx + 1 < len(specials) else len(lines)
        if kind in _SECTION_FIELD:
            body_lines = list(text_lines[pos + 1:end])
            # B2: the inline "Reference. <content>" form carries its own first
            # line of content on the label line itself, which pos+1 skips.
            inline = _TRAILER_INLINE_RE.match(lines[pos].strip())
            if inline:
                body_lines = [inline.group(2)] + body_lines
            content = "\n".join(ln for ln in body_lines if ln).strip()
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
    if _REHEARSAL_RE.search(title) or "soundcheck" in title:
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


# P1e: a trailing parenthetical that names the song's writers. Single-writer credits
# ("Hank Snow") carry no marker, so they still fall back to the word-count rule.
_CREDIT_MARKER_RE = re.compile(
    r"[/&,?]|\btrad\b|\barr\b|\badapted from\b|[A-Za-z.]\s*[-–—]\s*[A-Z]", re.IGNORECASE)
# P1e: Olof's alternate titles, as they appear in the corpus (casefolded, straight
# apostrophes). Everything else in parentheses is a writer credit or part of the title.
_KNOWN_SUBTITLES = frozenset({
    "and i'll go mine", "do unto others", "down in the flood", "for charley patton",
    "for charlie patton", "hallelujah", "has anybody seen my love", "i'm only bleeding",
    "journey through dark heat", "philosopher pirate", "sooner or later",
    "tales of yankee power", "the cough song", "the mighty quinn", "too much to ask",
    "valley below",
})


# BUG-347: Olof's page drops the next song's writer credit into the middle of a word
# ("Like A Rolling St (Bob Dylan-Robert Hunter/Bob Dylan) one"). The word is re-joined and
# the stray credit dropped — it belongs to the following song, which carries its own.
SPLICED_CREDIT_RE = re.compile(r"^(.*[A-Za-z])\s+\(([^()]+)\)\s+([a-z]{1,4})\s*$")


def _split_title_parts(text: str) -> tuple[str, str, str]:
    """P1e: split a DSN song title line into (title, credits, subtitle).

    A known alternate title goes to subtitle ('Most Likely You Go Your Way (And I'll Go
    Mine)'). A parenthetical with a composer marker is credits whatever its length
    ('Melancholy Mood (Walter Schumann & Vick R. Knight Sr.)'); a short one without a
    marker is still credits ('I'm Moving On (Hank Snow)'). A long one without a marker
    stays in the title ('I Don't Believe You (She Acts Like We Never Have Met)'). Text is
    kept exactly as Olof spells it.

    Args:
        text: The title portion of a song line, parens included if present.

    Returns:
        (title, credits, subtitle); credits and subtitle are '' when absent.
    """
    parts = text.split(" / ")
    if len(parts) > 1 and any(_CREDITS_SUFFIX_RE.match(p) for p in parts[:-1]):
        # Golden review 2: a medley credits each part ("I Walk The Line (Johnny Cash) /
        # Blue Moon Of Kentucky (Bill Monroe)") -- split per part, rejoin with " / ".
        split = [_split_title_parts(p) for p in parts]
        return (" / ".join(t for t, _, _ in split),
                " / ".join(c for _, c, _ in split if c),
                " / ".join(sub for _, _, sub in split if sub))
    spliced = SPLICED_CREDIT_RE.match(text)
    if spliced and _CREDIT_MARKER_RE.search(spliced.group(2)):
        text = spliced.group(1) + spliced.group(3)
    m = _CREDITS_SUFFIX_RE.match(text)
    if not m:
        return text.strip(), "", ""
    title, paren = m.group(1).strip(), m.group(2).strip()
    if " ".join(paren.replace("’", "'").casefold().split()) in _KNOWN_SUBTITLES:
        return title, "", paren
    if _CREDIT_MARKER_RE.search(paren) or len(paren.split()) <= _MAX_CREDIT_WORDS:
        return title, paren, ""
    return text.strip(), "", ""


# BUG-337 (ENCODING): apostrophe stand-ins Olof's Word exports use
# interchangeably — curly quotes, modifier letter apostrophe, prime, and the
# acute/grave accents typed as apostrophes ("´Til I Fell In Love With You").
# Folded to a straight ASCII apostrophe so the title is one spelling at rest;
# this matches what ``db.normalize_title_for_match`` and
# ``song_index.normalize_song_title`` already do for matching only.
_APOSTROPHE_STANDINS = "‘’ʼ′´`"
_APOSTROPHE_STANDIN_RE = re.compile("[" + _APOSTROPHE_STANDINS + "]")

# BUG-337: literal typos in the source pages themselves — verified against the
# raw windows-1252 bytes, so these are upstream authoring slips, not a decode
# or text-extraction artifact on our side. Each is a single-performance
# spelling that would otherwise strand its row in its own song group.
# Keyed on the exact title text Olof publishes.
_SOURCE_TITLE_TYPOS = {
    "Things Hav,e Changed": "Things Have Changed",   # DSN37470, stray comma
    "Diseaseof Conceit": "Disease Of Conceit",       # DSN13230, missing space
    "Blowin' InThe Wind": "Blowin' In The Wind",     # DSN39660, missing space
    "Se or": "Señor",                           # DSN24280, n-tilde dropped
    # DSN03245/03250 spell the same session's two takes both ways, one each.
    "Ride'Em Jewboy": "Ride 'Em Jewboy",
}


def _normalize_song_title(title: str) -> str:
    """Normalise one parsed song title for storage in ``olof_songs``.

    Folds apostrophe stand-ins to a straight apostrophe and repairs the
    handful of verified literal typos in the source pages (BUG-337), so the
    table is a single spelling per song at rest rather than only after the
    derived ``song_index`` fold.

    Args:
        title: Title text as extracted from the page.

    Returns:
        The normalised title (whitespace-collapsed).
    """
    cleaned = " ".join(_APOSTROPHE_STANDIN_RE.sub("'", title).split())
    return _SOURCE_TITLE_TYPOS.get(cleaned, cleaned)


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


def _release_entries(spec: str, remainder: str) -> list[tuple[int, str]]:
    """P1f: resolve one release trailer line into (position, released_on token) pairs.

    Args:
        spec: The leading position list ('4, 9, 12').
        remainder: The rest of the line, which may continue the list with
            'and N', 'and part of N' or 'or N' before the release wording.

    Returns:
        One pair per position. A partial position's token starts with
        RELEASE_PART_TAG; a position on either side of an 'or' starts with
        RELEASE_UNCERTAIN_TAG.
    """
    text_in = f"{spec} {remainder}"
    items: list[tuple[list[int], str, bool]] = []  # (positions, separator before, partial)
    pos = 0
    # B4: "parts of" applies to every comma-continued number that follows it,
    # not just the one right after it ("and parts of 3, 12" partials both 3
    # and 12); a fresh "and" (not just a comma) closes that run.
    partial_run = False
    while im := _RELEASE_ITEM_RE.match(text_in, pos):
        sep = (im.group(1) or "").replace(",", "").strip().lower()
        if items and not im.group(1):
            break  # two numbers with no separator: the second belongs to the release text
        if sep == "and":
            partial_run = False
        if im.group(2):
            partial_run = True
        lo = int(im.group(3))
        hi = int(im.group(4)) if im.group(4) else lo
        items.append((list(range(lo, hi + 1)), sep, partial_run))
        pos = im.end()
    rest = text_in[pos:].strip()
    rm = _RELEASE_TITLE_RE.match(rest)
    text = (rm.group(2) if rm else rest).rstrip(".").strip()
    if not text:
        return []
    whole_line_partial = bool(rm and rm.group(1))
    out: list[tuple[int, str]] = []
    for i, (positions, sep, partial) in enumerate(items):
        uncertain = sep == "or" or (i + 1 < len(items) and items[i + 1][1] == "or")
        tag = (RELEASE_UNCERTAIN_TAG if uncertain else "") + (
            RELEASE_PART_TAG if partial or whole_line_partial else "")
        out += [(p, tag + text) for p in positions]
    return out


def _is_guest_header(line: str) -> bool:
    """True for a guest/interlude set header inside a setlist (plan P1a).

    Olof lists a revue's or co-bill's guest sets between Dylan's numbered
    songs, each under a 'Name:' header (1975-12-08 'Bob Neuwirth:', 1986-02-24
    'Tom Petty & The Heartbreakers:'). Section labels ('BobTalk:') and lineup
    credits ('Bob Dylan (vocal & guitar) with ...:') are not headers.

    Args:
        line: One clean paragraph line.

    Returns:
        Whether the line reads as a guest-set header.
    """
    text = line.strip()
    return (len(text) <= _GUEST_HEADER_MAX_CHARS and text.endswith(":")
            and _classify_special_line(text) is None
            and not _LINEUP_RE.search(text)
            and not _SETLIST_LINE_RE.match(text))


def _skip_guest_block(lines: list[str], header_idx: int, max_position: int,
                      max_lines: int | None = None) -> tuple[int, bool] | None:
    """Find where Dylan's numbered set resumes after a guest block (plan P1a).

    Skips the header and the unnumbered guest titles after it, including
    further headers and encore separators. The set resumes only at a song
    marker for the next position (max_position + 1, or max_position again —
    the numbering slip _parse_song_lines renumbers). A section label, a lineup
    credit, a position-list trailer line, an out-of-sequence marker or the end
    of the block means the 'header' opened trailer text, not a guest set.

    Args:
        lines: Clean paragraph text for the whole event block.
        header_idx: Index of the guest header line.
        max_position: Highest song position parsed so far (0 before any).
        max_lines: Give up (None) after this many lines past the header without
            reaching the next song; unbounded when None.

    Returns:
        (index of the resuming marker, whether an encore separator was
        crossed), or None when the walk should stop at the header.
    """
    crossed_encore = False
    for j in range(header_idx + 1, len(lines)):
        if max_lines is not None and j - header_idx > max_lines:
            return None
        line = lines[j]
        if _ENCORE_SEP_RE.match(line):
            crossed_encore = True
            continue
        if _BARE_POSITION_RE.match(line) or _SONG_LINE_RE.match(line):
            position = int(line.split(".", 1)[0])
            if position >= 1 and position in (max_position, max_position + 1):
                return j, crossed_encore
            return None
        if (_classify_special_line(line) or _LINEUP_RE.search(line)
                or _POSITION_LIST_LINE_RE.match(line)):
            return None
    return None


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
      _POSITION_LIST_LINE_RE expects. 2+ "Name (instrument)" clauses in the
      candidate title text (_is_personnel_line, B1) marks it as a personnel
      line instead, so the walk stops there (that line is left for the
      whole-block _LINEUP_RE scan in _parse_event, same as the
      space-separated case) — a plain double-cover-credit title like "I Walk
      The Line ( John ny Cash) / Blue Moon Of Kentucky (Bill Monroe)"
      (1999-06-11) is not mistaken for one, since neither parenthetical
      names an instrument.
    - Olof's own numbering occasionally repeats a position it already used
      (e.g. DSN618: the encore song is mislabeled '15.' again instead of
      '16.'). Since olof_songs' primary key is (event_id, position), a
      repeat is renumbered to one past the highest position seen so far —
      preserving the extra song instead of dropping it or crashing.
    - Guest/interlude sets sit between numbered songs under a 'Name:'
      header (1975-12-08, 1986-02-24). The walk skips such a block and
      resumes at the next numbered song (_skip_guest_block); guest songs are
      not stored. A header that isn't followed by the next song stops the
      walk at the header.

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
        if _is_guest_header(line):
            resume = _skip_guest_block(lines, i, max(seen_positions, default=0))
            if resume is None:
                break
            i, crossed_encore = resume
            is_encore = is_encore or crossed_encore
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
        elif seen_positions and (resume := _skip_guest_block(
                lines, i - 1, max(seen_positions), max_lines=_MAX_UNNUMBERED_BLOCK)):
            # An unnumbered block between numbered songs with no 'Name:' header --
            # 1974 Tour sets by The Band ("Songs without numbers are performed by The
            # Band without Bob Dylan"). Skipped like a guest set; not stored.
            i, crossed_encore = resume
            is_encore = is_encore or crossed_encore
            continue
        else:
            break
        if _is_personnel_line(title_text):
            break  # personnel-credit trailer line, not a song (see above)
        i = next_i
        # Silver review: a medley (or a long credit) Olof wraps onto the next line
        # ends in "/" -- "That'll Be The Day (…) /" + "The Wanderer (E. Maresca)",
        # 1999 Paul Simon shows. Join the continuation or the second song is lost.
        while (title_text.rstrip().endswith("/") and i < n and lines[i].strip()
               and not re.match(r"^\s*\d+\.", lines[i])):
            title_text = f"{title_text.rstrip()} {lines[i].strip()}"
            i += 1
        if position in seen_positions:
            renumbered = max(seen_positions) + 1
            _log.warning(
                "olof_parser: DSN%d position %d reused for %r — "
                "renumbered to %d (source numbering slip)",
                event_id, position, title_text, renumbered,
            )
            position = renumbered
        seen_positions.add(position)
        title, credits, subtitle = _split_title_parts(title_text)
        title = _normalize_song_title(title)
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
            credits=credits, subtitle=subtitle, is_encore=int(is_encore),
            take_number=take_number, take_status=take_status,
        ))
    return songs, i


def _apply_position_clause(clause: str, by_position: dict[int, SongRecord],
                            annotations: dict[int, list[str]],
                            releases: dict[int, list[str]]) -> None:
    """Resolve one '<position-list> <text>' clause onto *annotations*/*releases*.

    B3 (golden-dossier plan, phase B): a clause's own tail can hold a second,
    unrelated position-list clause riding the same physical line ("11, 23, 25
    Bob Dylan and Tom Petty (shared vocals). 17 Howie Epstein (slide guitar),
    Tom Petty (bass).", 1986-02-24) — split on a period followed by a fresh
    position list (_CLAUSE_SPLIT_RE) and resolve each piece independently,
    recursively, so "17 Howie Epstein ..." lands on position 17 instead of
    being swallowed into positions 11/23/25's annotation text. Not applied to
    a release line (_RELEASE_KEYWORD_RE match) — a release title's own prose
    ("vol. 5 - Bob Dylan Live 1975 ...") can trip the same period+digit
    pattern with no second clause intended.

    Args:
        clause: One '<position-list> <text>' candidate line/sub-line.
        by_position: This event's SongRecords keyed by position.
        annotations: Accumulator, position -> annotation text pieces.
        releases: Accumulator, position -> released_on text pieces.
    """
    m = _POSITION_LIST_LINE_RE.match(clause)
    if not m or _LINEUP_RE.search(clause) or HISTORY_DATE_RE.match(clause):
        return
    remainder = m.group(2).strip()
    if _RELEASE_KEYWORD_RE.search(remainder):
        for pos, text in _release_entries(m.group(1), remainder):
            if pos in by_position:
                releases.setdefault(pos, []).append(text)
        return
    pieces = _CLAUSE_SPLIT_RE.split(remainder)
    positions = [p for p in _expand_position_list(m.group(1)) if p in by_position]
    text = pieces[0].rstrip(".").strip()
    if positions and text:
        for pos in positions:
            annotations.setdefault(pos, []).append(text)
    for extra in pieces[1:]:
        _apply_position_clause(extra, by_position, annotations, releases)


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
    digits elsewhere in the trailer prose) is dropped. A single physical
    line can hold two unrelated clauses (B3, see _apply_position_clause).

    Args:
        lines: Clean paragraph text for the whole event block.
        consumed_end: Index returned by _parse_song_lines — where the
            song/take region ended.
        songs: SongRecords to update in place (matched by .position).
    """
    by_position = {s.position: s for s in songs}
    annotations: dict[int, list[str]] = {}
    releases: dict[int, list[str]] = {}
    in_prose = False  # P1g: inside a BobTalk/References section
    for line in lines[consumed_end:]:
        kind = _classify_special_line(line)
        if kind:
            in_prose = kind in ("bobtalk", "references")
        elif _SECTION_END_RE.match(line.strip()):
            in_prose = False
        m = _POSITION_LIST_LINE_RE.match(line)
        if not m or _LINEUP_RE.search(line) or HISTORY_DATE_RE.match(line):
            continue  # a date line ("1 March 1978") is never a position list (P1b)
        # Prose that starts with a number ("14 years ago ...") is not a position list;
        # an unlabelled range/list, release or recording line inside the section still is.
        if in_prose and not (re.search(r"[-,]", m.group(1))
                             or _PROSE_KEEP_RE.search(m.group(2))):
            continue
        _apply_position_clause(line, by_position, annotations, releases)
    for pos, song in by_position.items():
        if pos in annotations:
            song.annotations = "; ".join(annotations[pos])
        if pos in releases:
            song.released_on = "; ".join(releases[pos])


def _parse_event_songs(lines: list[str], date_idx: int, session_title: str,
                        event_id: int,
                        trailer_lines: list[str] | None = None) -> list[SongRecord]:
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
        trailer_lines: Same-length copy of *lines* the annotation/release
            scan reads (_clean_trailer_lines output); defaults to *lines*.

    Returns:
        SongRecords in position order, with annotations/released_on
        resolved from the trailer lines following the last song/take row.
    """
    if date_idx < 0:
        return []
    start = date_idx + 1
    # A guest header right after the date is taken as session_title; the walk
    # must still see it so it can skip the guest block (P1a).
    if session_title and not _is_guest_header(session_title):
        start += 1
    songs, consumed_end = _parse_song_lines(lines, start, event_id)
    if songs:
        _resolve_annotations_and_releases(
            lines if trailer_lines is None else trailer_lines, consumed_end, songs)
    return songs


def _collect_lineup_text(lines: list[str]) -> str:
    """Build the event's lineup field, extending a header that ends in ':'.

    B5 (golden-dossier plan, phase B): a lineup line can introduce a guest
    band with a colon and list its members on following lines that carry no
    'Bob Dylan(' substring of their own ("Bob Dylan (vocal & guitar) with Tom
    Petty & The Heartbreakers:" / "Tom Petty (guitar), Mike Campbell
    (guitar), ..." / "and The Queens Of Rhythm: Debra Byrd, ...",
    1986-02-24) — the plain ``_LINEUP_RE.search`` scan this replaces only
    keeps the header line, dropping the band it introduces. Continuation
    stops at the next special/position-list/song-marker line or at another
    _LINEUP_RE line (a fresh, independent lineup entry).

    Args:
        lines: Clean paragraph text for the whole event block.

    Returns:
        '; '-joined lineup entries, each entry's own lines joined by a space.
    """
    parts: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not _LINEUP_RE.search(line):
            i += 1
            continue
        group = [line]
        j = i + 1
        if line.rstrip().endswith(":"):
            while j < n:
                cont = lines[j]
                if (_classify_special_line(cont) or _POSITION_LIST_LINE_RE.match(cont)
                        or _BARE_POSITION_RE.match(cont) or _SONG_LINE_RE.match(cont)
                        or _LINEUP_RE.search(cont)):
                    break
                group.append(cont)
                j += 1
        parts.append(" ".join(group))
        i = j
    return "; ".join(parts)


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
    rec.lineup = _collect_lineup_text(lines)

    cleaned = _clean_trailer_lines(lines, rec)
    _extract_sections(lines, rec, cleaned)
    rec.event_type = _classify_event_type(rec, lines)
    songs = _parse_event_songs(lines, date_idx, rec.session_title, event_id, cleaned)
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
