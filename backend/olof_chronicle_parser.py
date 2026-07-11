"""Parser for Olof Björner's Yearly Chronicles (chronicle corpus) — reads
pages already mirrored by backend/olof_fetcher.py into data/olof/pages/,
decodes windows-1252, and emits:

    - olof_chronicle: one row per dated calendar/diary entry (spec §2.3
      section 3, 'Calendar').
    - olof_new_tapes: one row per 'New tapes & bootlegs'-family subsection
      (spec §2.3 section 4.4) — circulation provenance for a tape, not
      necessarily a single dated show (box sets/ranges get date_str='').
    - olof_events / olof_songs: synthetic events for the appendix set-list
      pages ('YYYY A.htm'-style), but ONLY for years without DSN coverage
      (see _APPENDIX_CUTOFF_YEAR below) — DSN is the authoritative setlist
      source through 2021; the appendix only extends coverage past that.

See instructions/FABLE_OLOF_FILES.md §2.3 (corpus facts), §4 (schema),
§6 P4 (scope), §7 (risks this module tolerates).

Section location (calendar / new tapes / appendix):
    Chronicle pages are Word HTML exports with a front-matter TOC followed
    by the real body. Both carry the *same* numbered heading text (e.g.
    '3 THE 2002 CALENDAR'), so the two must be told apart reliably:
        - TOC entries are always <p> tags with an explicit Word style class
          (MsoNormal / MsoToc1 / MsoToc2 / ...).
        - Real body section headings are always bare <h1>-<h6> tags with NO
          class attribute at all — confirmed across ~50 years of exports
          (2002 uses <h1>/<h2>/<h3> for '1 INTRODUCTION' / '4.4 New tapes &
          bootlegs' / '4.4.1 Sydney...'; 1966/1985/1995 use the same
          h-tag-without-class convention even though their *paragraph*
          classes vary wildly across eras — Sng / Texten / TextenChar... /
          MsoNormal / MsoPlainText).
    `_locate_headings` collects (para_index, heading_level, text) for every
    bare hN tag whose text looks like a numbered heading ('N', 'N.',
    'N.N', 'N.N.N ...' followed by a title — the trailing '.' after the
    bare number is itself era drift: 2002 omits it, 1995 uses it: '3.
    CALENDAR'). `_find_section` then locates the first heading matching a
    keyword regex and bounds it to the next heading at the same-or-higher
    level (its "end of section" boundary), so subsections nested one level
    deeper (e.g. 4.4.1/4.4.2/... under 4.4) don't prematurely end it.

    Section *titles* are not stable across eras (confirmed by inspecting
    the mirror directly, not just the 2002 sample):
        - Calendar: always contains 'calendar' case-insensitively ('3 THE
          2002 CALENDAR', '3 CALENDAR', '3. CALENDAR', '3 The 1985
          Calendar') — matched via `_CALENDAR_HEAD_RE`.
        - New tapes & bootlegs: named very differently release to release
          — 'New tapes & bootlegs' (2000s), 'New tapes' (1995-1999), 'NEW
          TAPES 1958-1987' (1993), 'New circulating recording(s)'
          (2003-2004), 'New recordings in circulation <year>' (2008-2011).
          Matched via `_NEW_TAPES_HEAD_RE`, a keyword alternation covering
          every variant observed in the mirror. Its child subsections are
          NOT always show-date-titled either (2010: 'New Soundboards',
          '1958 John Bucklen tape'; 1994: 'Genuine Bootleg Series') — those
          simply get date_str='' (see title-date resolution below), which
          is exactly the schema's documented behavior for ranges/box sets.

Calendar date-heading detection (within the located calendar section):
    The date-per-entry heading is NOT reliably identified by paragraph
    class — 2002 uses class='Sng', 1985 uses a
    'TextenCharCharChar...Char' megaclass, 1995/2000 use 'Texten', 2010/
    1992 use plain 'MsoNormal' (same class as the entry body text, so class
    alone can't distinguish heading from prose there). Detection is
    therefore purely text-shape based: `_CHRON_DATE_HEAD_RE` full-matches
    (not searches) a cleaned paragraph against every date-heading shape
    observed in the mirror:
        - 'D Month'                      ('31 January')
        - 'Month D'                      ('January 5' — 1995 export only)
        - bare 'Month'                   ('January' — 1995, no day)
        - day list/range + Month         ('5 & 14 February', '19 -24
                                           February', '3-4 March', '26 & 28
                                           October')
        - '(Early|Mid|Late) Month'       ('Early January' — 1985/1992)
    A full-paragraph match (not a substring search) keeps ordinary prose
    from false-positiving — no observed entry-body sentence happens to be
    *only* a date expression. date_str is resolved when at least one day
    number can be extracted (first day of a list/range, best-effort per
    spec §7); a bare-month or unparseable heading still gets a row with
    date_raw set and date_str=''.

New-tapes title → date_str resolution:
    Unlike the calendar (day-only, year comes from the page), a new-tapes
    subsection title carries its OWN full date when it has one ('Sydney,
    Australia, 24 February 1986' — the tape's *show* date, unrelated to
    the chronicle year it's filed under). `_resolve_new_tape_date` searches
    the title for a 'D Month YYYY' substring; titles without one (box
    sets, ranges, non-date subsection names) get date_str='' exactly as
    the schema documents.

Appendix set-list parsing (spec §2.3, §7 malformed-header tolerance):
    Real appendix pages mark each show with class='Show' (header) followed
    by one or more class='Setlist' paragraphs (confirmed on 2002 A.htm,
    107 shows). A regex fallback (`_is_show_para`) also recognizes a bare
    'N. <text>' paragraph containing a 'D Month YYYY' date even without
    the 'Show' class, in case markup drifts again by 2022+ (untested — no
    2022+ chronicle pages exist in the local mirror yet, see run report).
    Explicitly excludes <h1>-<h6> tags from candidacy so a numbered
    subsection heading like '4.4.1 Sydney...' on a *different* section of
    the same page is never misread as a show header.

    Header parsing tolerates the malformed shapes spec §7 warns about and
    confirms in the mirror (2002 A.htm entries #5 and #6):
        '5. North Charleston Coliseum, Charleston 6 February 2002 , 6
        February 2002'                          (duplicated date)
        '6. Joel Veterans Memorial Coliseum, Salem , North Carolina 8
        February 2002 , :'                      (missing comma, stray ':')
    Strategy: find every 'D Month YYYY' occurrence in the header text; the
    LAST occurrence is treated as the canonical show date (duplicated
    dates repeat identically, so this is safe); everything before the
    FIRST occurrence is the venue/city/region text, comma-split the same
    way as the DSN header parser (`_split_city_region_country`, shared).
    A header with no date match at all falls back to storing the whole
    line as `venue` with date_str='' (spec §7: fall back to raw — the full
    original line is also preserved in raw_text regardless).

    Setlist song lines are slash-separated with an optional trailing
    parenthetical performance annotation ('Girl From The North Country
    (acoustic w band)'). This is the exact same title-vs-trailing-paren
    ambiguity the DSN song parser already solved (some official titles
    themselves end in '(...)', e.g. "It's Alright, Ma (I'm Only
    Bleeding)") — confirmed by scanning every Setlist line in 2002 A.htm:
    of 8 distinct parenthetical values found, 7 were real title text and
    only 'acoustic w band' was a genuine performance annotation. Reuses
    `_split_title_credits` (DSN/olof_parser) unchanged; here the second
    return value is stored as `annotations` instead of `credits` since the
    appendix format has no cover-credit concept (spec: "no encore marker
    or take data in this format").

Word-HTML field-code junk (spec §7 — XE/PAGEREF/TOC blobs):
    Confirmed by direct inspection: Word's TOC field codes (PAGEREF,
    HYPERLINK) live inside `<!--[if supportFields]>...<![endif]-->`
    conditional comments and `mso-hide:screen` spans. BeautifulSoup's
    `get_text()` (used by the shared `_clean_para_text` helper) already
    excludes HTML comment nodes, so scanning the full mirror (427k+
    paragraphs) found zero leaked 'PAGEREF'/'XE "' substrings in cleaned
    text — the risk described in spec §7 does not currently manifest via
    this extraction path. `_strip_field_junk` is still applied to every
    stored entry_text/body_text as defense in depth (a differently
    configured HTML parser could expose it), which is also what the
    verification gate's SQL LIKE check confirms empirically.

1960-1989 pages are PDF-only stubs, not a parser bug:
    Every single-file year page from 1960-1989 (and each year's 'section 0'
    cover file from 1990 on) contains the literal text 'as a PDF file' —
    Olof's site only ever published those years' full chronicle as a PDF
    download; the mirrored HTML is just a title/copyright/TOC cover page
    with a download link, never the actual calendar/new-tapes body. This
    is a genuine corpus gap, confirmed by inspecting the pages directly,
    not a fetcher or parser defect. Detected via `_STUB_MARKER` and used
    to keep those pages' parse_status='ok' with event_count=0 rather than
    'partial' (see per-page status logic in run_parse).

Appendix cutoff (spec §6 P4, §7):
    `_APPENDIX_CUTOFF_YEAR` is hardcoded rather than computed at runtime
    from `MAX(date_str)` in olof_events (source='dsn') per the task's
    explicit instruction not to hardcode blindly: verified via
    `SELECT MAX(substr(date_str,1,4)) FROM olof_events WHERE source='dsn'`
    against the mirrored DB on 2026-07-10 → '2021'. DSN is authoritative
    through 2021; the appendix is only trusted as a setlist source from
    2022 on. NOTE: the local chronicle mirror currently only covers years
    1960-2012 (plus one 2016 special-article page) — no year >=
    _APPENDIX_CUTOFF_YEAR exists locally yet, so this run emits zero
    synthetic events; the appendix code path is implemented and exercised
    structurally against the 2002 A.htm sample but is otherwise untested
    against real 2022+ markup until those pages are fetched.

Idempotency:
    olof_chronicle / olof_new_tapes are keyed (year, seq); olof_events
    synthetic ids are year*1000+seq. A rerun deletes a year's rows before
    reinserting: `_upsert_chronicle`/`_upsert_new_tapes` DELETE WHERE
    year=?; `_upsert_appendix` DELETE WHERE source='chronicle_appendix' AND
    event_id BETWEEN year*1000 AND year*1000+999 (which cascades to
    olof_songs via the FK's ON DELETE CASCADE), then reuses olof_parser's
    `_upsert_events`/`_upsert_songs`. Sequence numbers are assigned once
    per year AFTER aggregating every one of that year's pages (sorted by
    filename) rather than per-file, so a year whose content happens to
    split across two files still numbers stably across reruns.

Public API:
    parse_page(path, filename, year) -> (PageResult, stats dict)
    run_parse(file, db_path, pages_dir) -> coverage summary dict

CLI:
    .venv/bin/python3 -m backend.olof_chronicle_parser [--file <path-or-filename>]

Schema: olof_chronicle, olof_new_tapes, olof_events, olof_songs (see
db.py). See module docstring sections above for idempotency and the
appendix-cutoff / 1960-1989-stub notes.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from backend.db import get_connection, init_db
from backend.olof_fetcher import PAGES_DIR
from backend.olof_parser import (
    _MONTHS,
    _PARA_TAGS,
    _TOP_LINE_RE,
    EventRecord,
    SongRecord,
    _clean_para_text,
    _ensure_page_row,
    _pct,
    _resolve_file_path,
    _split_city_region_country,
    _split_title_credits,
    _update_page_status,
    _upsert_events,
    _upsert_songs,
)

_log = logging.getLogger(__name__)

# Max DSN year (2021) + 1 — see module docstring "Appendix cutoff". Verified
# via SQL against the mirrored DB on 2026-07-10; hardcoded per spec §6/§7
# instruction rather than recomputed at import time.
_APPENDIX_CUTOFF_YEAR = 2022

# Front-matter/cover pages link to a PDF instead of hosting the chronicle
# body in HTML — see module docstring "1960-1989 pages are PDF-only stubs".
_STUB_MARKER = "as a pdf file"

_HEAD_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
# Numbered section heading text, e.g. '3 CALENDAR', '3. CALENDAR',
# '4.4 New tapes & bootlegs', '4.4.1 Sydney , Australia , 24 February 1986'.
_HEAD_NUM_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
_CALENDAR_HEAD_RE = re.compile(r"calendar", re.IGNORECASE)
_NEW_TAPES_HEAD_RE = re.compile(
    r"new\s+(?:tapes?|recordings?(?:\s+in\s+circulation)?|circulating\s+recordings?)",
    re.IGNORECASE,
)

_MONTH_ALT = "|".join(_MONTHS)  # lowercase full month names, re.IGNORECASE at use sites
_DAY_LIST = r"\d{1,2}(?:\s*(?:-|–|&|,)\s*\d{1,2})*"
# Calendar date-heading shapes (see module docstring) — full-match only.
_CHRON_DATE_HEAD_RE = re.compile(
    rf"^(?:(?:early|mid|late)\s+)?"
    rf"(?:({_DAY_LIST})\s+)?"
    rf"({_MONTH_ALT})"
    rf"(?:\s+({_DAY_LIST}))?"
    rf"(?:,?\s*(\d{{4}}))?$",
    re.IGNORECASE,
)
# 'D Month YYYY' occurrence, searched (not full-matched) inside new-tapes
# titles and appendix show headers.
_FULL_DATE_RE = re.compile(rf"(\d{{1,2}})\s+({_MONTH_ALT})\s+(\d{{4}})", re.IGNORECASE)

# Appendix show header: 'N.  <venue/city/date text>'.
_SHOW_HEADER_RE = re.compile(r"^(\d+)\.\s*(.+)$")

# Defense-in-depth field-code stripping — see module docstring; empirically
# a no-op against the current mirror (BeautifulSoup already excludes the
# HTML comments these field codes live in), kept as a safety net.
_FIELD_JUNK_RE = re.compile(
    r'XE\s+"[^"]*"|PAGEREF\s+\S+(?:\s*\\\w+)*|HYPERLINK\s+\S+', re.IGNORECASE
)
# Word's hard-wrap-then-rejoin sometimes leaves a space before punctuation
# ('Sydney , Australia'); tidy it to match the spec's example spacing.
_PUNCT_SPACING_RE = re.compile(r"\s+([,.;:])")

_CHRONICLE_COLUMNS = ["year", "seq", "date_str", "date_raw", "entry_text"]
_NEW_TAPES_COLUMNS = ["year", "seq", "title", "date_str", "body_text"]


@dataclass
class ChronicleEntry:
    """One olof_chronicle row: a dated calendar/diary entry."""

    year: int
    seq: int
    date_str: str = ""
    date_raw: str = ""
    entry_text: str = ""


@dataclass
class NewTapeEntry:
    """One olof_new_tapes row: a 'new tapes & bootlegs'-family subsection."""

    year: int
    seq: int
    title: str = ""
    date_str: str = ""
    body_text: str = ""


@dataclass
class PageResult:
    """Everything parse_page extracted from one chronicle page."""

    chronicle: list[ChronicleEntry]
    new_tapes: list[NewTapeEntry]
    appendix: list[tuple[EventRecord, list[SongRecord]]]
    cal_heading_found: bool
    new_tapes_heading_found: bool
    is_stub: bool


# ---------------------------------------------------------------------------
# Text cleanup
# ---------------------------------------------------------------------------

def _tidy_punct_spacing(text: str) -> str:
    """Remove whitespace immediately before ,.;: introduced by Word's
    hard-wrap-then-rejoin ('Sydney , Australia' -> 'Sydney, Australia')."""
    return _PUNCT_SPACING_RE.sub(r"\1", text)


def _strip_field_junk(text: str) -> str:
    """Remove residual Word field-code text (spec §7), defense in depth.

    Collapses only the horizontal whitespace left behind by a removal —
    newlines (paragraph boundaries) are preserved.
    """
    cleaned = _FIELD_JUNK_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _clean_entry_text(text: str) -> str:
    """Full cleanup pipeline for stored entry_text/body_text/raw_text."""
    return _tidy_punct_spacing(_strip_field_junk(text))


def _iso_date(day: str, month_name: str, year: str) -> str:
    """Build an ISO date_str from regex-captured (day, month name, year).

    Returns '' if the month name doesn't resolve (should not happen given
    the regexes are built from `_MONTHS`, but kept defensive).
    """
    month = _MONTHS.get(month_name.lower())
    if not month:
        return ""
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


# ---------------------------------------------------------------------------
# Section location
# ---------------------------------------------------------------------------

def _locate_headings(para_elements: list) -> list[tuple[int, int, str]]:
    """Find numbered body-section headings among *para_elements*.

    See module docstring "Section location" for why bare <h1>-<h6> tags
    (no class attribute) reliably distinguish a real body heading from a
    TOC entry carrying the same numbered text.

    Returns:
        (para_index, level, text) tuples in document order — level is the
        heading tag's number (1 for <h1>, ...).
    """
    headings: list[tuple[int, int, str]] = []
    for i, el in enumerate(para_elements):
        if el.name not in _HEAD_TAGS or el.get("class") is not None:
            continue
        text = _clean_para_text(el)
        if _HEAD_NUM_RE.match(text):
            headings.append((i, int(el.name[1]), text))
    return headings


def _find_section(headings: list[tuple[int, int, str]], para_count: int,
                   keyword_re: re.Pattern) -> tuple[int, int, int, str] | None:
    """Return the first heading matching *keyword_re* and its bounds.

    Args:
        headings: Output of `_locate_headings`.
        para_count: Total paragraph count (end-of-document fallback bound).
        keyword_re: Matched against each heading's text via `.search`.

    Returns:
        (start_para_idx, end_para_idx, level, heading_text) for the first
        match, where end_para_idx is the index of the next heading at the
        same-or-higher level (or para_count) — or None if no heading
        matches.
    """
    for pos, (idx, level, text) in enumerate(headings):
        if not keyword_re.search(text):
            continue
        end = para_count
        for idx2, level2, _text2 in headings[pos + 1:]:
            if level2 <= level:
                end = idx2
                break
        return idx, end, level, text
    return None


# ---------------------------------------------------------------------------
# Calendar (olof_chronicle)
# ---------------------------------------------------------------------------

def _parse_date_heading(text: str, year: int) -> tuple[str, str] | None:
    """Return (date_str, date_raw) if *text* is a calendar date heading.

    See module docstring "Calendar date-heading detection" for the shapes
    matched. Returns None if *text* isn't a date-heading shape at all.
    """
    m = _CHRON_DATE_HEAD_RE.match(text.strip())
    if not m:
        return None
    day_before, month_name, day_after, year_str = m.groups()
    day_spec = day_before or day_after
    day_m = re.match(r"\d{1,2}", day_spec) if day_spec else None
    month = _MONTHS.get(month_name.lower())
    date_str = ""
    if day_m and month:
        eff_year = int(year_str) if year_str else year
        date_str = f"{eff_year:04d}-{month:02d}-{int(day_m.group(0)):02d}"
    return date_str, text.strip()


def _parse_calendar(para_elements: list, start: int, end: int,
                     year: int) -> list[ChronicleEntry]:
    """Walk the calendar section [start+1, end) into ChronicleEntry rows.

    `seq` is left at 0 — run_parse assigns final sequence numbers after
    aggregating every page contributing to *year* (see module docstring
    "Idempotency").
    """
    entries: list[ChronicleEntry] = []
    lines: list[str] = []
    date_info: tuple[str, str] | None = None
    for el in para_elements[start + 1:end]:
        if el.name in _HEAD_TAGS:
            continue  # nested subheading inside the calendar (not observed, defensive)
        text = _clean_para_text(el)
        if not text or _TOP_LINE_RE.match(text):
            continue
        dh = _parse_date_heading(text, year)
        if dh:
            if date_info is not None:
                entries.append(ChronicleEntry(
                    year=year, seq=0, date_str=date_info[0], date_raw=date_info[1],
                    entry_text=_clean_entry_text("\n".join(lines)),
                ))
            date_info = dh
            lines = []
        elif date_info is not None:
            lines.append(text)
        # else: stray text before the first date heading — dropped.
    if date_info is not None:
        entries.append(ChronicleEntry(
            year=year, seq=0, date_str=date_info[0], date_raw=date_info[1],
            entry_text=_clean_entry_text("\n".join(lines)),
        ))
    return entries


# ---------------------------------------------------------------------------
# New tapes & bootlegs (olof_new_tapes)
# ---------------------------------------------------------------------------

def _resolve_new_tape_date(title: str) -> str:
    """Parse a 'D Month YYYY' show date out of a new-tapes subsection title.

    Returns '' for titles with no embedded date (box sets, ranges, non-
    date subsection names) — the schema's documented behavior.
    """
    m = _FULL_DATE_RE.search(title)
    if not m:
        return ""
    day, month_name, year_str = m.groups()
    return _iso_date(day, month_name, year_str)


def _parse_new_tapes(para_elements: list, headings: list[tuple[int, int, str]],
                      start: int, end: int, level: int,
                      year: int) -> list[NewTapeEntry]:
    """Walk the new-tapes section's child subsections into NewTapeEntry rows.

    Child subsections are headings one level deeper than the section
    heading itself (e.g. h3 '4.4.1 ...' under h2 '4.4 New tapes &
    bootlegs'). A section with no such children (era drift — not observed
    for a real 'new tapes' section in the mirror, but tolerated) yields no
    rows rather than guessing at unstructured prose.
    """
    subs = [(idx, text) for idx, lvl, text in headings if lvl == level + 1 and start < idx < end]
    entries: list[NewTapeEntry] = []
    for i, (idx, heading_text) in enumerate(subs):
        sub_end = subs[i + 1][0] if i + 1 < len(subs) else end
        m = re.match(r"^\d+(?:\.\d+)*\.?\s+(.*)$", heading_text)
        title = _tidy_punct_spacing(m.group(1) if m else heading_text)
        body_lines = []
        for el in para_elements[idx + 1:sub_end]:
            if el.name in _HEAD_TAGS:
                continue
            t = _clean_para_text(el)
            if t and not _TOP_LINE_RE.match(t):
                body_lines.append(t)
        entries.append(NewTapeEntry(
            year=year, seq=0, title=title, date_str=_resolve_new_tape_date(title),
            body_text=_clean_entry_text("\n".join(body_lines)),
        ))
    return entries


# ---------------------------------------------------------------------------
# Appendix set-lists (olof_events / olof_songs, synthetic ids)
# ---------------------------------------------------------------------------

def _is_show_para(el) -> bool:
    """True if *el* looks like an appendix show header paragraph.

    Excludes <h1>-<h6> tags outright so a numbered subsection heading
    elsewhere on the page (e.g. '4.4.1 Sydney...') is never misread as a
    show header (see module docstring).
    """
    if el.name in _HEAD_TAGS:
        return False
    cls = el.get("class") or []
    if "Show" in cls:
        return True
    text = _clean_para_text(el)
    return bool(_SHOW_HEADER_RE.match(text) and _FULL_DATE_RE.search(text))


def _parse_appendix_header(text: str) -> dict:
    """Best-effort parse of one appendix show header line.

    Tolerates the malformed shapes spec §7 warns about (see module
    docstring "Appendix set-list parsing" for the confirmed examples).

    Args:
        text: Cleaned header paragraph text, including the leading 'N.'.

    Returns:
        dict with keys date_str/date_raw/venue/city/region/country.
    """
    fields = {"date_str": "", "date_raw": "", "venue": "", "city": "",
              "region": "", "country": ""}
    m = _SHOW_HEADER_RE.match(text)
    body = m.group(2) if m else text
    matches = list(_FULL_DATE_RE.finditer(body))
    if not matches:
        fields["venue"] = _tidy_punct_spacing(body.strip())
        return fields
    day, month_name, year_str = matches[-1].groups()
    fields["date_str"] = _iso_date(day, month_name, year_str)
    fields["date_raw"] = matches[-1].group(0).strip()
    location_text = body[:matches[0].start()]
    parts = [_tidy_punct_spacing(p.strip()) for p in location_text.split(",") if p.strip()]
    if parts:
        fields["venue"] = parts[0]
        fields.update(_split_city_region_country(parts[1:]))
    return fields


def _parse_appendix_songs(setlist_text: str) -> list[SongRecord]:
    """Split a slash-separated appendix setlist line into SongRecords.

    Reuses `_split_title_credits` (DSN/olof_parser) to separate a trailing
    '(...)' performance annotation from the title — same ambiguity the DSN
    parser already solves (spec, module docstring). event_id is left at 0;
    run_parse assigns the real synthetic id after year-level aggregation.
    """
    songs: list[SongRecord] = []
    chunks = [c.strip() for c in setlist_text.split("/") if c.strip()]
    for position, chunk in enumerate(chunks, start=1):
        title, annotation = _split_title_credits(chunk)
        songs.append(SongRecord(
            event_id=0, position=position, song_title=_tidy_punct_spacing(title),
            annotations=annotation,
        ))
    return songs


def _parse_appendix(para_elements: list, page_filename: str,
                     year: int) -> list[tuple[EventRecord, list[SongRecord]]]:
    """Parse every show block on an appendix page into (event, songs) pairs.

    event_id/source/page_filename are set here except event_id, which is
    left at 0 — run_parse assigns year*1000+seq after aggregating every
    page contributing to *year* (module docstring "Idempotency").
    """
    shows: list[tuple[EventRecord, list[SongRecord]]] = []
    i, n = 0, len(para_elements)
    while i < n:
        if not _is_show_para(para_elements[i]):
            i += 1
            continue
        header_text = _clean_para_text(para_elements[i])
        i += 1
        setlist_chunks: list[str] = []
        while i < n and not _is_show_para(para_elements[i]):
            t = _clean_para_text(para_elements[i])
            if t and not _TOP_LINE_RE.match(t):
                cls = para_elements[i].get("class") or []
                if "Setlist" in cls or "/" in t:
                    setlist_chunks.append(t)
            i += 1
        fields = _parse_appendix_header(header_text)
        raw_text = _clean_entry_text("\n".join([header_text, *setlist_chunks]))
        rec = EventRecord(
            event_id=0, source="chronicle_appendix", page_filename=page_filename,
            event_type="concert", date_str=fields["date_str"], date_raw=fields["date_raw"],
            venue=fields["venue"], city=fields["city"], region=fields["region"],
            country=fields["country"], raw_text=raw_text,
        )
        songs = _parse_appendix_songs(" / ".join(setlist_chunks))
        shows.append((rec, songs))
    if shows:
        _log.debug("olof_chronicle_parser: %s (year %d) — %d appendix shows parsed",
                    page_filename, year, len(shows))
    return shows


# ---------------------------------------------------------------------------
# Per-page assembly
# ---------------------------------------------------------------------------

def parse_page(path: Path, filename: str, year: int) -> tuple[PageResult, dict]:
    """Parse one local chronicle page into calendar/new-tapes/appendix rows.

    Args:
        path: On-disk path to the mirrored HTML file.
        filename: olof_pages.filename key this page is recorded under.
        year: This page's chronicle year (olof_pages.year).

    Returns:
        (PageResult, stats) — stats has 'chronicle'/'new_tapes'/
        'appendix_events' counts for this page alone (used for its own
        olof_pages.event_count bookkeeping).
    """
    raw = path.read_bytes()
    text = raw.decode("windows-1252", errors="replace")
    is_stub = _STUB_MARKER in text.lower()
    soup = BeautifulSoup(text, "lxml")
    para_elements = soup.find_all(_PARA_TAGS)
    headings = _locate_headings(para_elements)
    n = len(para_elements)

    chronicle: list[ChronicleEntry] = []
    new_tapes: list[NewTapeEntry] = []
    appendix: list[tuple[EventRecord, list[SongRecord]]] = []

    cal = _find_section(headings, n, _CALENDAR_HEAD_RE)
    if cal:
        cal_start, cal_end, _level, _text = cal
        chronicle = _parse_calendar(para_elements, cal_start, cal_end, year)

    nt = _find_section(headings, n, _NEW_TAPES_HEAD_RE)
    if nt:
        nt_start, nt_end, nt_level, _text = nt
        new_tapes = _parse_new_tapes(para_elements, headings, nt_start, nt_end, nt_level, year)

    if year >= _APPENDIX_CUTOFF_YEAR:
        appendix = _parse_appendix(para_elements, filename, year)

    result = PageResult(
        chronicle=chronicle, new_tapes=new_tapes, appendix=appendix,
        cal_heading_found=cal is not None, new_tapes_heading_found=nt is not None,
        is_stub=is_stub,
    )
    stats = {
        "chronicle": len(chronicle), "new_tapes": len(new_tapes),
        "appendix_events": len(appendix),
    }
    return result, stats


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _upsert_chronicle(conn, year: int, entries: list[ChronicleEntry]) -> None:
    """Idempotently write *entries* (DELETE + INSERT, keyed on year)."""
    conn.execute("DELETE FROM olof_chronicle WHERE year = ?", (year,))
    if entries:
        columns = ", ".join(_CHRONICLE_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in _CHRONICLE_COLUMNS)
        conn.executemany(
            f"INSERT INTO olof_chronicle ({columns}) VALUES ({placeholders})",
            [asdict(e) for e in entries],
        )
    conn.commit()


def _upsert_new_tapes(conn, year: int, entries: list[NewTapeEntry]) -> None:
    """Idempotently write *entries* (DELETE + INSERT, keyed on year)."""
    conn.execute("DELETE FROM olof_new_tapes WHERE year = ?", (year,))
    if entries:
        columns = ", ".join(_NEW_TAPES_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in _NEW_TAPES_COLUMNS)
        conn.executemany(
            f"INSERT INTO olof_new_tapes ({columns}) VALUES ({placeholders})",
            [asdict(e) for e in entries],
        )
    conn.commit()


def _upsert_appendix(conn, year: int, events: list[EventRecord],
                      songs: list[SongRecord]) -> None:
    """Idempotently write appendix *events*/*songs* for *year*.

    Ranged DELETE on the synthetic id space (year*1000..year*1000+999)
    cascades to olof_songs (ON DELETE CASCADE) so a reparse that produces
    FEWER shows than before doesn't leave orphaned rows — then reuses
    olof_parser's own upsert helpers (module docstring "Idempotency").
    """
    conn.execute(
        "DELETE FROM olof_events WHERE source = 'chronicle_appendix' "
        "AND event_id >= ? AND event_id < ?",
        (year * 1000, (year + 1) * 1000),
    )
    conn.commit()
    _upsert_events(conn, events)
    _upsert_songs(conn, events, songs)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_parse(file: str | None = None, db_path: str | None = None,
              pages_dir: Path | None = None) -> dict:
    """Parse local chronicle pages into olof_chronicle/olof_new_tapes/
    olof_events(+olof_songs), upsert, and report coverage.

    Default mode parses every corpus='chronicle' olof_pages row with a
    year assigned whose file exists under *pages_dir*, grouped and
    sequence-numbered per year (module docstring "Idempotency"). `file`
    reparses a single page instead (must already be tracked in olof_pages
    with a year, or the on-disk path/bare filename lookup fails to
    determine one).

    Args:
        file: Optional single-page override (path or bare filename).
        db_path: Optional DB path override.
        pages_dir: Optional override of the mirror directory (tests).

    Returns:
        Coverage summary dict: pages_ok/pages_partial/pages_error,
        chronicle_rows/years_with_chronicle, new_tapes_rows/
        years_with_new_tapes, appendix_events/appendix_songs/
        years_with_appendix, stub_years (1960-1989-style PDF-only pages),
        empty_years (parsed OK, not a stub, but zero rows anywhere —
        candidates for markup-drift review).
    """
    resolved_pages_dir = pages_dir or PAGES_DIR
    init_db(db_path)
    conn = get_connection(db_path)

    tasks_by_year: dict[int, list[tuple[Path, str]]] = {}
    if file:
        path = _resolve_file_path(file, resolved_pages_dir)
        filename = path.name
        row = conn.execute(
            "SELECT year, segment_title FROM olof_pages WHERE filename = ?", (filename,)
        ).fetchone()
        year = row[0] if row else None
        if year is None:
            raise ValueError(
                f"olof_chronicle_parser: no year known for {filename!r} — "
                "register it in olof_pages (with a year) before reparsing."
            )
        _ensure_page_row(conn, filename, path, segment_title=row[1] if row else "",
                          corpus="chronicle", year=year)
        tasks_by_year[year] = [(path, filename)]
    else:
        rows = conn.execute(
            "SELECT filename, year FROM olof_pages "
            "WHERE corpus = 'chronicle' AND year IS NOT NULL"
        ).fetchall()
        for fn, yr in rows:
            p = resolved_pages_dir / fn
            if p.exists():
                tasks_by_year.setdefault(yr, []).append((p, fn))
        for lst in tasks_by_year.values():
            lst.sort(key=lambda t: t[1])

    pages_ok = pages_partial = pages_error = 0
    total_chronicle = total_new_tapes = total_appendix_events = total_appendix_songs = 0
    years_with_chronicle = years_with_new_tapes = years_with_appendix = 0
    stub_years: list[int] = []
    empty_years: list[int] = []

    for year in sorted(tasks_by_year):
        year_chronicle: list[ChronicleEntry] = []
        year_new_tapes: list[NewTapeEntry] = []
        year_appendix: list[tuple[EventRecord, list[SongRecord]]] = []
        year_is_stub = False

        for path, filename in tasks_by_year[year]:
            parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                result, stats = parse_page(path, filename, year)
            except Exception as exc:  # noqa: BLE001 — page-level isolation (spec §3)
                _log.error("olof_chronicle_parser: failed to parse %s: %s", filename, exc)
                _update_page_status(conn, filename, parsed_at, f"error:{exc}"[:200], 0)
                pages_error += 1
                continue

            own_count = stats["chronicle"] + stats["new_tapes"] + stats["appendix_events"]
            missed_section = (
                (result.cal_heading_found and stats["chronicle"] == 0)
                or (result.new_tapes_heading_found and stats["new_tapes"] == 0)
            )
            if missed_section and not result.is_stub:
                status = "partial"
                pages_partial += 1
            else:
                status = "ok"
                pages_ok += 1
            _update_page_status(conn, filename, parsed_at, status, own_count)

            year_chronicle.extend(result.chronicle)
            year_new_tapes.extend(result.new_tapes)
            year_appendix.extend(result.appendix)
            year_is_stub = year_is_stub or result.is_stub

        for i, entry in enumerate(year_chronicle, start=1):
            entry.seq = i
        for i, entry in enumerate(year_new_tapes, start=1):
            entry.seq = i
        events: list[EventRecord] = []
        songs: list[SongRecord] = []
        for i, (ev, ev_songs) in enumerate(year_appendix, start=1):
            eid = year * 1000 + i
            ev.event_id = eid
            for s in ev_songs:
                s.event_id = eid
            events.append(ev)
            songs.extend(ev_songs)

        _upsert_chronicle(conn, year, year_chronicle)
        _upsert_new_tapes(conn, year, year_new_tapes)
        if year >= _APPENDIX_CUTOFF_YEAR:
            _upsert_appendix(conn, year, events, songs)

        total_chronicle += len(year_chronicle)
        total_new_tapes += len(year_new_tapes)
        total_appendix_events += len(events)
        total_appendix_songs += len(songs)
        if year_chronicle:
            years_with_chronicle += 1
        if year_new_tapes:
            years_with_new_tapes += 1
        if events:
            years_with_appendix += 1
        if not year_chronicle and not year_new_tapes and not events:
            # A year is a genuine "stub" only when it produced NO rows at
            # all AND one of its files is PDF-only — a year with real
            # content elsewhere (e.g. 1990+, whose section-0 cover file is
            # *also* stub-marked) must not be misclassified here.
            if year_is_stub:
                stub_years.append(year)
            else:
                empty_years.append(year)

    summary = {
        "years_parsed": len(tasks_by_year),
        "pages_ok": pages_ok,
        "pages_partial": pages_partial,
        "pages_error": pages_error,
        "chronicle_rows": total_chronicle,
        "years_with_chronicle": years_with_chronicle,
        "new_tapes_rows": total_new_tapes,
        "years_with_new_tapes": years_with_new_tapes,
        "appendix_events": total_appendix_events,
        "appendix_songs": total_appendix_songs,
        "years_with_appendix": years_with_appendix,
        "stub_years": stub_years,
        "empty_years": empty_years,
        "pct_chronicle_years": _pct(years_with_chronicle, len(tasks_by_year)),
    }
    _log.info(
        "olof_chronicle_parser: coverage — years=%d pages(ok=%d partial=%d error=%d) "
        "chronicle_rows=%d(years=%d) new_tapes_rows=%d(years=%d) "
        "appendix_events=%d appendix_songs=%d(years=%d) stub_years=%d empty_years=%s",
        summary["years_parsed"], pages_ok, pages_partial, pages_error,
        total_chronicle, years_with_chronicle, total_new_tapes, years_with_new_tapes,
        total_appendix_events, total_appendix_songs, years_with_appendix,
        len(stub_years), empty_years,
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Olof Björner Yearly Chronicle pages into "
                     "olof_chronicle/olof_new_tapes/olof_events."
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
    _log.info("olof_chronicle_parser: summary %s", _summary)
