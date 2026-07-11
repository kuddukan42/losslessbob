"""Parser for Olof Björner's Still On The Road session pages (DSN corpus) —
reads pages already mirrored by backend/olof_fetcher.py into
data/olof/pages/, decodes windows-1252, and emits one olof_events row per
`<a name=DSNnnnnn>` event block (see instructions/FABLE_OLOF_FILES.md §2-§4,
§6 phase P2).

Scope (P2): header fields, trailer fields (concert #, recording info, notes,
BobTalk, releases/references blobs, "Session info updated"), and the full
block raw_text. Song/take rows (olof_songs) are P3; chronicle parsing is P4.

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
    parse_page(path, filename, tour_name) -> (list[EventRecord], stats dict)
    run_parse(file, db_path, pages_dir) -> coverage summary dict

CLI:
    .venv/bin/python3 -m backend.olof_parser [--file <path-or-filename>]

Schema: olof_events (see db.py). Idempotent upsert (INSERT OR REPLACE) on
event_id; updates olof_pages.parsed_at/parse_status/event_count per page.
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
# Per-event assembly
# ---------------------------------------------------------------------------

def _parse_event(lines: list[str], event_id: int, page_filename: str,
                  tour_name: str) -> EventRecord:
    """Build one EventRecord from an event block's clean paragraph lines."""
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
    return rec


def parse_page(path: Path, filename: str, tour_name: str) -> tuple[list[EventRecord], dict]:
    """Parse one local DSN page into EventRecords.

    Args:
        path: On-disk path to the mirrored (or sample) HTML file.
        filename: olof_pages.filename key this page is recorded under.
        tour_name: Segment title (olof_pages.segment_title), copied onto
            every event's tour_name.

    Returns:
        (events, stats) — stats has 'anchors' (DSN anchors found) and
        'events' (records successfully emitted).
    """
    raw = path.read_bytes()
    text = raw.decode("windows-1252", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    para_elements, anchors = _locate_events(soup)

    events: list[EventRecord] = []
    for idx, (para_idx, event_id) in enumerate(anchors):
        end_idx = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(para_elements)
        block_elements = para_elements[para_idx:end_idx]
        lines = [t for t in (_clean_para_text(el) for el in block_elements) if t]
        if not lines:
            _log.warning("olof_parser: %s DSN%d — empty block, skipped", filename, event_id)
            continue
        events.append(_parse_event(lines, event_id, filename, tour_name))

    return events, {"anchors": len(anchors), "events": len(events)}


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _ensure_page_row(conn, filename: str, path: Path, segment_title: str) -> None:
    """Register a minimal olof_pages row if *filename* isn't tracked yet.

    olof_events.page_filename is a foreign key (PRAGMA foreign_keys=ON, see
    db.py get_connection) so ad-hoc `--file` reparses of untracked pages
    (e.g. data/olof/samples/ dev fixtures) need a parent row first.

    Args:
        conn: Open connection (see run_parse — written to directly, not via
            the shared write-queue singleton, per BUG-246: this parser
            always knows its own db_path and must not risk a
            first-caller-wins queue bound elsewhere).
        filename: olof_pages.filename key.
        path: On-disk file, hashed if a row must be created.
        segment_title: Used as segment_title if a row must be created.
    """
    if conn.execute("SELECT 1 FROM olof_pages WHERE filename = ?", (filename,)).fetchone():
        return
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    conn.execute(
        """INSERT INTO olof_pages (filename, url, corpus, segment_title, sha256, fetched_at)
           VALUES (?, '', 'dsn', ?, ?, ?)""",
        (filename, segment_title, sha256, time.strftime("%Y-%m-%dT%H:%M:%S")),
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
        pct_venue, pct_recording_info, event_type_counts.
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
    total_anchors = total_events = 0
    events_with_date = events_with_venue = events_with_recording = 0
    type_counts: dict[str, int] = {}

    for path, filename, tour_name in tasks:
        parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            events, stats = parse_page(path, filename, tour_name)
        except Exception as exc:  # noqa: BLE001 — page-level isolation (spec §3 robustness rule)
            _log.error("olof_parser: failed to parse %s: %s", filename, exc)
            _update_page_status(conn, filename, parsed_at, f"error:{exc}"[:200], 0)
            pages_error += 1
            continue

        anchors = stats["anchors"]
        total_anchors += anchors
        total_events += len(events)
        if anchors == 0 or len(events) == anchors:
            status = "ok"
            pages_ok += 1
        else:
            status = "partial"
            pages_partial += 1

        _upsert_events(conn, events)
        _update_page_status(conn, filename, parsed_at, status, len(events))

        for rec in events:
            if rec.date_str:
                events_with_date += 1
            if rec.venue:
                events_with_venue += 1
            if rec.recording_info:
                events_with_recording += 1
            type_counts[rec.event_type] = type_counts.get(rec.event_type, 0) + 1

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
    }
    _log.info(
        "olof_parser: coverage — pages=%d (ok=%d partial=%d error=%d) anchors=%d "
        "events=%d date=%.1f%% venue=%.1f%% recording=%.1f%% types=%s",
        summary["pages_parsed"], pages_ok, pages_partial, pages_error,
        total_anchors, total_events, summary["pct_iso_date"],
        summary["pct_venue"], summary["pct_recording_info"], type_counts,
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
