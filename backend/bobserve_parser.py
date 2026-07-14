"""Parser for bobserve.com's post-2021 setlist pages (bobserve corpus) —
reads pages already mirrored by backend/bobserve_fetcher.py into
data/olof/bobserve_pages/, and emits one olof_events row (+ olof_songs rows)
per show, extracted from the page's `data-clipboard-text` attribute rather
than the surrounding Tailwind/Flux component markup.

Why data-clipboard-text: bobserve renders a "copy to clipboard" button whose
`data-clipboard-text` attribute already holds a clean, HTML-entity-decoded
plain-text summary of the whole show — confirmed against real 2022 (Oslo,
event=3841) and 2023 (New York, event=4344) pages to be far more stable to
parse than the component tree around it, which is dense utility-class HTML
with no semantic hooks for venue/city/setlist.

Clipboard text shape (blank-line-delimited blocks; confirmed on both real
samples above, one US and one international):
    <Month D, YYYY>
    <City>, <Region or Country>
    <Venue>
    <Event type, e.g. 'Concert'>

    1. <Song title> [(<cover credit>)]
    2. ...
    ...

    <Tour name>
    <Year>
    <Leg — e.g. 'Leg 3 - Europe (Sep-Nov)'>          [optional, tour-dependent]

    Musicians
    <comma-separated musician list>

    Info via bobserve: <url>

Parsing splits on blank lines rather than assuming fixed line positions, and
locates the song block by shape (every line matches 'N. ...') rather than by
position, so a missing leg line or a shorter/longer musicians list degrades
gracefully instead of misaligning every field after it. No encore marker has
been observed in any sampled clipboard text (unlike the DSN corpus's dash
separator) — is_encore is left 0 throughout; revisit if a counter-example
turns up. The page's separate free-text "Note:" field (rendered outside the
clipboard blob, e.g. "Concert opened with curtain rising...") is NOT
captured here — it would need parsing the surrounding HTML, out of scope for
this pass.

event_id scheme: 9,000,000 + bobserve's own `?event=` id. DSN ids top out
around 440620 and chronicle_appendix ids run year*1000+seq (max ~2026999,
see backend/olof_chronicle_parser.py) — the offset leaves comfortable
headroom against both and is stable/deterministic per source id, so a rerun
just overwrites the same row (no year-level aggregation/sequencing needed,
unlike chronicle_appendix).

Public API:
    parse_page(path, filename) -> (EventRecord | None, list[SongRecord], status)
    run_parse(file, db_path, pages_dir) -> coverage summary dict

CLI:
    .venv/bin/python3 -m backend.bobserve_parser [--file <path-or-filename>]

Schema: olof_events (source='bobserve'), olof_songs (see db.py).
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
import time
from pathlib import Path

from backend.bobserve_fetcher import PAGES_DIR
from backend.db import get_connection, init_db
from backend.olof_parser import (
    _MONTHS,
    EventRecord,
    SongRecord,
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

# See module docstring "event_id scheme".
EVENT_ID_OFFSET = 9_000_000

_CLIPBOARD_RE = re.compile(r'data-clipboard-text="(.*?)"', re.S)
_FILENAME_ID_RE = re.compile(r"^bobserve_event_(\d+)\.html$")
_DATE_LINE_RE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$")
_SONG_LINE_RE = re.compile(r"^\d+\.\s*(.+)$")


def _event_id_from_filename(filename: str) -> int:
    """Return bobserve's own numeric event id encoded in *filename*."""
    m = _FILENAME_ID_RE.match(filename)
    if not m:
        raise ValueError(
            f"bobserve_parser: filename {filename!r} doesn't look like a "
            "'bobserve_event_<id>.html' mirrored page"
        )
    return int(m.group(1))


def _extract_clipboard_text(raw_bytes: bytes) -> str | None:
    """Return the decoded data-clipboard-text blob, or None if absent."""
    text = raw_bytes.decode("utf-8", errors="replace")
    m = _CLIPBOARD_RE.search(text)
    if not m:
        return None
    return html.unescape(m.group(1))


def _split_blocks(clipboard_text: str) -> list[list[str]]:
    """Split the clipboard blob into blank-line-delimited line groups."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in clipboard_text.split("\n"):
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_date(line: str) -> tuple[str, str]:
    """Return (date_str, date_raw) from a 'Month D, YYYY' line, or ('', line)."""
    m = _DATE_LINE_RE.match(line)
    if not m:
        return "", line
    month_name, day, year = m.groups()
    month = _MONTHS.get(month_name.lower())
    if not month:
        return "", line
    return f"{int(year):04d}-{month:02d}-{int(day):02d}", line


def _parse_header_block(lines: list[str]) -> dict:
    """Parse the clipboard blob's first block: date / location / venue / type.

    Args:
        lines: The header block's non-blank lines, in order.

    Returns:
        dict with keys date_str/date_raw/venue/city/region/country/
        event_type_raw (each '' if the block was too short to supply it).
    """
    fields = {"date_str": "", "date_raw": "", "venue": "", "city": "",
              "region": "", "country": "", "event_type_raw": ""}
    if not lines:
        return fields
    fields["date_str"], fields["date_raw"] = _parse_date(lines[0])
    if len(lines) >= 2:
        parts = [p.strip() for p in lines[1].split(",") if p.strip()]
        fields.update(_split_city_region_country(parts))
    if len(lines) >= 4:
        fields["venue"] = " ".join(lines[2:-1])
        fields["event_type_raw"] = lines[-1]
    elif len(lines) == 3:
        fields["venue"] = lines[2]
    return fields


def _looks_like_song_block(lines: list[str]) -> bool:
    """True if *lines* opens with a numbered 'N. ...' song line.

    Only the first line is required to match — a medley entry sometimes
    wraps its second song onto its own unnumbered continuation line
    (confirmed: bobserve_event_4801, '8.Medley To Be Alone With You' /
    'Watching The River Flow' with no leading number on the second line).
    Requiring every line to match rejected the whole block and silently
    dropped all songs for that show; _parse_songs folds a non-numbered line
    into the preceding song's title instead.
    """
    return bool(lines) and bool(_SONG_LINE_RE.match(lines[0]))


def _parse_songs(lines: list[str], event_id: int) -> list[SongRecord]:
    """Parse a confirmed song block into position-ordered SongRecords.

    A line not matching 'N. ...' is a medley continuation (see
    _looks_like_song_block) and is folded into the previous song's title
    with ' / ' rather than dropped or mis-parsed as its own entry.
    """
    songs: list[SongRecord] = []
    for line in lines:
        m = _SONG_LINE_RE.match(line)
        if not m:
            if songs:
                songs[-1].song_title = f"{songs[-1].song_title} / {line.strip()}"
            continue
        position = int(line.split(".", 1)[0])
        title, credits = _split_title_credits(m.group(1))
        songs.append(SongRecord(event_id=event_id, position=position,
                                 song_title=title, credits=credits))
    return songs


def parse_page(path: Path, filename: str) -> tuple[EventRecord | None, list[SongRecord], str]:
    """Parse one locally mirrored bobserve setlist page.

    Args:
        path: On-disk path to the mirrored HTML file.
        filename: olof_pages.filename key this page is recorded under — must
            be the 'bobserve_event_<id>.html' shape bobserve_fetcher uses,
            since the numeric event id is read from the filename, not the
            page body.

    Returns:
        (event, songs, status). event is None (status starts 'error:') if no
        data-clipboard-text blob was found at all; otherwise status is 'ok'
        or 'partial' (missing ISO date, missing venue, or a concert with no
        parsed songs).
    """
    bobserve_id = _event_id_from_filename(filename)
    event_id = EVENT_ID_OFFSET + bobserve_id
    clip = _extract_clipboard_text(path.read_bytes())
    if clip is None:
        _log.error("bobserve_parser: no data-clipboard-text found in %s", filename)
        return None, [], "error:no-clipboard-text"

    blocks = _split_blocks(clip)
    if not blocks:
        _log.error("bobserve_parser: empty clipboard text in %s", filename)
        return None, [], "error:empty-clipboard-text"

    header = _parse_header_block(blocks[0])
    event_type_raw = header.pop("event_type_raw", "")

    song_block_idx = None
    for i, block in enumerate(blocks[1:], start=1):
        if _looks_like_song_block(block):
            song_block_idx = i
            break
    songs = _parse_songs(blocks[song_block_idx], event_id) if song_block_idx is not None else []

    tour_name = ""
    if song_block_idx is not None and song_block_idx + 1 < len(blocks):
        tail = [ln for ln in blocks[song_block_idx + 1] if not ln.isdigit()]
        if tail:
            tour_name = tail[0]

    musicians = ""
    for block in blocks:
        if block and block[0].strip().lower() == "musicians":
            musicians = " ".join(block[1:])
            break

    event_type = event_type_raw.strip().lower() or "other"

    rec = EventRecord(
        event_id=event_id, source="bobserve", page_filename=filename,
        event_type=event_type, date_str=header["date_str"], date_raw=header["date_raw"],
        venue=header["venue"], city=header["city"], region=header["region"],
        country=header["country"], tour_name=tour_name, lineup=musicians,
        raw_text=clip,
    )

    status = "ok"
    if not header["date_str"] or not header["venue"]:
        status = "partial"
    elif event_type == "concert" and not songs:
        status = "partial"
    return rec, songs, status


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_parse(file: str | None = None, db_path: str | None = None,
              pages_dir: Path | None = None) -> dict:
    """Parse locally mirrored bobserve pages into olof_events/olof_songs.

    Default mode parses every corpus='bobserve' olof_pages row whose file
    exists under *pages_dir*. `file` reparses a single page instead (must
    resolve to a 'bobserve_event_<id>.html'-shaped filename).

    Args:
        file: Optional single-page override (path or bare filename).
        db_path: Optional DB path override.
        pages_dir: Optional override of the mirror directory (tests).

    Returns:
        Coverage summary dict: pages_parsed/pages_ok/pages_partial/
        pages_error, events/songs counts, pct_iso_date/pct_venue/
        pct_concerts_with_songs.
    """
    resolved_pages_dir = pages_dir or PAGES_DIR
    init_db(db_path)
    conn = get_connection(db_path)

    paths: dict[str, Path] = {}
    if file:
        path = _resolve_file_path(file, resolved_pages_dir)
        _ensure_page_row(conn, path.name, path, segment_title="", corpus="bobserve")
        paths[path.name] = path
    else:
        rows = conn.execute(
            "SELECT filename FROM olof_pages WHERE corpus = 'bobserve'"
        ).fetchall()
        for (fn,) in rows:
            p = resolved_pages_dir / fn
            if p.exists():
                paths[fn] = p

    pages_ok = pages_partial = pages_error = 0
    events: list[EventRecord] = []
    all_songs: list[SongRecord] = []

    for fn, p in paths.items():
        parsed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            rec, songs, status = parse_page(p, fn)
        except Exception as exc:  # noqa: BLE001 — page-level isolation (matches olof_parser)
            _log.error("bobserve_parser: failed to parse %s: %s", fn, exc)
            _update_page_status(conn, fn, parsed_at, f"error:{exc}"[:200], 0)
            pages_error += 1
            continue

        if rec is None:
            _update_page_status(conn, fn, parsed_at, status, 0)
            pages_error += 1
            continue

        _update_page_status(conn, fn, parsed_at, status, 1)
        if status == "partial":
            pages_partial += 1
        else:
            pages_ok += 1
        events.append(rec)
        all_songs.extend(songs)

    _upsert_events(conn, events)
    _upsert_songs(conn, events, all_songs)

    total = len(events)
    with_date = sum(1 for e in events if e.date_str)
    with_venue = sum(1 for e in events if e.venue)
    concerts = [e for e in events if e.event_type == "concert"]
    ids_with_songs = {s.event_id for s in all_songs}
    concerts_with_songs = sum(1 for e in concerts if e.event_id in ids_with_songs)

    summary = {
        "pages_parsed": len(paths),
        "pages_ok": pages_ok,
        "pages_partial": pages_partial,
        "pages_error": pages_error,
        "events": total,
        "songs": len(all_songs),
        "pct_iso_date": _pct(with_date, total),
        "pct_venue": _pct(with_venue, total),
        "pct_concerts_with_songs": _pct(concerts_with_songs, len(concerts)),
    }
    _log.info(
        "bobserve_parser: coverage — pages(ok=%d partial=%d error=%d) events=%d songs=%d "
        "pct_iso_date=%.1f pct_venue=%.1f pct_concerts_with_songs=%.1f",
        pages_ok, pages_partial, pages_error, total, len(all_songs),
        summary["pct_iso_date"], summary["pct_venue"], summary["pct_concerts_with_songs"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse mirrored bobserve.com setlist pages into olof_events/olof_songs."
    )
    parser.add_argument("--file", default=None,
                         help="Reparse a single page (path or bare filename under "
                              "data/olof/bobserve_pages/).")
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
    _log.info("bobserve_parser: summary %s", _summary)
