#!/usr/bin/env python3
"""Live acceptance checks for the show-dossier redesign (TODO-342).

Prints one PASS/FAIL line per criterion in instructions/SHOW_DOSSIER_REDESIGN_PLAN.md
for the mode asked. Modes arrive chunk by chunk; today there is one:

    --parser   Phase 1: Olof parser corpus counts, then the checks — the two
               song-count cases (1986-02-24 = 25, 1975-12-08 = 22, shown beside
               bobdylan.com / setlist.fm / TUIT) and each defect count at its target.

Usage::

    .venv/bin/python3 tools/dossier_acceptance.py --parser
    .venv/bin/python3 tools/dossier_acceptance.py --parser --before .debug/olof_before.db
    .venv/bin/python3 tools/dossier_acceptance.py --parser --residuals

``--before`` reads the same counts from a tools/olof_reparse_diff.py snapshot and
prints them beside the live ones. ``--residuals`` lists every zero-song and
truncated concert. Exit status is 1 when any check fails. Run from the project root.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.paths import DB_PATH  # noqa: E402
from tools.olof_reparse_diff import MONTH_YEAR_RE, ROTATION_FRAGMENT_RE  # noqa: E402

_log = logging.getLogger(__name__)

_NUMBERED_LINE_RE = re.compile(r"^(\d+)\.(?:\s|$)", re.MULTILINE)
_COMPOSER_PAREN_RE = re.compile(r"\([^()]*[/&][^()]*\)\s*$")
_SONG_COUNT_CASES = (("1986-02-24", 25), ("1975-12-08", 22))
# A "... Bob Dylan concerts in <city>:" header followed by a dated entry line.
_VENUE_LIST_RE = re.compile(
    r"(?:Bob Dylan\s+(?:shows|concerts)\s+in|\b(?:other|previous|next)\s+(?:shows|concerts))\b"
    r"[^\n]*\n(?:(?:early|mid|late)\b|\d{1,2}\b)",
    re.IGNORECASE,
)

# (key, label). Counts cover DSN/chronicle rows only — bobserve rows are out of Phase 1.
PARSER_METRICS = (
    ("concerts", "concert events"),
    ("zero_song_concerts", "concerts with 0 parsed songs"),
    ("zero_song_but_numbered", "  … whose page has numbered songs"),
    ("truncated_concerts", "concerts parsed short of the page"),
    ("date_line_annotation_rows", "songs with a date-line annotation"),
    ("rotation_stat_song_rows", "songs with a rotation-stat annotation"),
    ("rotation_stat_in_event_text", "events with the stat in notes/releases"),
    ("rotation_stat_on_page", "events whose page states the stat"),
    ("rotation_populated", "events with rotation_new set"),
    ("venue_history_in_notes", "events with the venue blob in notes"),
    ("venue_history_raw_populated", "events with venue_history_raw set"),
    ("and_ill_go_mine_credits", "'And I'll Go Mine' stored as credits"),
    ("composer_credits_in_title", "titles ending in a composer credit"),
    ("subtitle_populated", "songs with subtitle set"),
    ("release_part_of_prefix", "songs with an 'and part of' release"),
)


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _tokens(text) -> list[str]:
    return [t.strip() for t in str(text or "").split(";") if t.strip()]


def parser_metrics(conn: sqlite3.Connection) -> tuple[dict[str, int | None], list[str]]:
    """Count Phase 1 parser defects and their fixed-state columns.

    Args:
        conn: A DB holding olof_events / olof_songs — live, or a snapshot.

    Returns:
        (metric → count, or None where the column does not exist yet;
        residual lines 'kind event_id date parsed/page' for every zero-song
        or truncated concert).
    """
    ev_cols, song_cols = _columns(conn, "olof_events"), _columns(conn, "olof_songs")
    song_counts = dict(conn.execute("SELECT event_id, COUNT(*) FROM olof_songs GROUP BY event_id"))
    m: Counter = Counter()
    residuals: list[str] = []
    for ev in conn.execute(
        "SELECT event_id, date_str, event_type, notes, releases_raw, raw_text"
        " FROM olof_events WHERE source != 'bobserve'"
    ):
        raw = ev["raw_text"] or ""
        if ev["event_type"] == "concert":
            m["concerts"] += 1
            parsed = song_counts.get(ev["event_id"], 0)
            numbered = len(set(_NUMBERED_LINE_RE.findall(raw)))
            if parsed == 0:
                m["zero_song_concerts"] += 1
                if numbered:
                    m["zero_song_but_numbered"] += 1
                residuals.append(f"zero      {ev['event_id']:>8} {ev['date_str'] or '?':10} "
                                 f"0/{numbered}")
            elif parsed < numbered:
                m["truncated_concerts"] += 1
                residuals.append(f"truncated {ev['event_id']:>8} {ev['date_str'] or '?':10} "
                                 f"{parsed}/{numbered}")
        if ROTATION_FRAGMENT_RE.search(raw):
            m["rotation_stat_on_page"] += 1
        if ROTATION_FRAGMENT_RE.search(f"{ev['notes'] or ''}\n{ev['releases_raw'] or ''}"):
            m["rotation_stat_in_event_text"] += 1
        if _VENUE_LIST_RE.search(f"{ev['notes'] or ''}\n{ev['releases_raw'] or ''}"):
            m["venue_history_in_notes"] += 1

    subtitle_sql = ", s.subtitle" if "subtitle" in song_cols else ""
    for s in conn.execute(
        f"SELECT s.song_title, s.credits, s.annotations, s.released_on{subtitle_sql}"
        " FROM olof_songs s JOIN olof_events e USING (event_id) WHERE e.source != 'bobserve'"
    ):
        ann = _tokens(s["annotations"])
        if any(MONTH_YEAR_RE.match(t) for t in ann):
            m["date_line_annotation_rows"] += 1
        if any(ROTATION_FRAGMENT_RE.search(t) for t in ann):
            m["rotation_stat_song_rows"] += 1
        if (s["credits"] or "").replace("’", "'").casefold() == "and i'll go mine":
            m["and_ill_go_mine_credits"] += 1
        if _COMPOSER_PAREN_RE.search(s["song_title"] or ""):
            m["composer_credits_in_title"] += 1
        if any(t.casefold().startswith("and part of") for t in _tokens(s["released_on"])):
            m["release_part_of_prefix"] += 1
        if subtitle_sql and s["subtitle"]:
            m["subtitle_populated"] += 1

    out: dict[str, int | None] = {k: m[k] for k, _ in PARSER_METRICS}
    if "rotation_new" not in ev_cols:
        out["rotation_populated"] = out["venue_history_raw_populated"] = None
    else:
        out["rotation_populated"] = conn.execute(
            "SELECT COUNT(*) FROM olof_events WHERE source != 'bobserve'"
            " AND COALESCE(rotation_new, rotation_pct, tour_new_count) IS NOT NULL").fetchone()[0]
        out["venue_history_raw_populated"] = conn.execute(
            "SELECT COUNT(*) FROM olof_events WHERE source != 'bobserve'"
            " AND venue_history_raw != ''").fetchone()[0]
    if not subtitle_sql:
        out["subtitle_populated"] = None
    return out, residuals


def _count(conn: sqlite3.Connection, sql: str, params: tuple) -> str:
    try:
        return str(conn.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError:
        return "n/a"


def parser_checks(conn: sqlite3.Connection, metrics: dict[str, int | None]) -> list[tuple[bool, str]]:
    """Phase 1 acceptance: the two song-count cases, then each defect count at target."""
    checks: list[tuple[bool, str]] = []
    for date, want in _SONG_COUNT_CASES:
        got = conn.execute(
            "SELECT COUNT(*) FROM olof_songs s JOIN olof_events e USING (event_id)"
            " WHERE e.date_str = ? AND e.event_type = 'concert'", (date,)).fetchone()[0]
        bd = _count(conn, "SELECT COUNT(*) FROM bobdylan_setlist l JOIN bobdylan_shows s"
                          " USING (bobdylan_url) WHERE s.date_str = ?", (date,))
        sfm = _count(conn, "SELECT COUNT(*) FROM setlistfm_setlist l JOIN setlistfm_shows s"
                           " USING (setlistfm_id) WHERE s.date_str = ?"
                           " AND COALESCE(l.is_tape, 0) = 0", (date,))
        tuit = _count(conn, "SELECT COUNT(*) FROM tuit_song_performances WHERE date_str = ?",
                      (date,))
        checks.append((got == want, f"{date} Olof songs {got} = {want}"
                                    f"   (bobdylan.com {bd}, setlist.fm {sfm}, TUIT {tuit})"))
    for key in ("date_line_annotation_rows", "rotation_stat_song_rows",
                "rotation_stat_in_event_text", "venue_history_in_notes",
                "and_ill_go_mine_credits", "release_part_of_prefix"):
        checks.append((metrics[key] == 0, f"{key} {metrics[key]} = 0"))
    pop, page = metrics["rotation_populated"], metrics["rotation_stat_on_page"]
    checks.append((pop == page, f"rotation_populated {pop if pop is not None else 'n/a'}"
                                f" = rotation_stat_on_page {page}"))
    return checks


def run_parser(db_path: Path, before: Path | None, residuals: bool) -> int:
    """Print the Phase 1 counts (and a before column), then the checks; return exit code."""
    live = _open_ro(db_path)
    try:
        after_m, after_res = parser_metrics(live)
        before_m = parser_metrics(_open_ro(before))[0] if before else None
        fmt = lambda v: "—" if v is None else f"{v:,}"  # noqa: E731
        if before_m is not None:
            _log.info("%-42s %10s %10s", "metric", "before", "after")
            for key, label in PARSER_METRICS:
                _log.info("%-42s %10s %10s", label, fmt(before_m[key]), fmt(after_m[key]))
        else:
            _log.info("%-42s %10s", "metric", "value")
            for key, label in PARSER_METRICS:
                _log.info("%-42s %10s", label, fmt(after_m[key]))
        _log.info("")
        checks = parser_checks(live, after_m)
    finally:
        live.close()
    for ok, text in checks:
        _log.info("%s  %s", "PASS" if ok else "FAIL", text)
    if residuals:
        _log.info("")
        for line in after_res:
            _log.info("%s", line)
    failed = sum(1 for ok, _ in checks if not ok)
    _log.info("%d/%d checks pass", len(checks) - failed, len(checks))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--parser", action="store_true", help="Phase 1 Olof parser checks.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Live DB (default: data/).")
    parser.add_argument("--before", type=Path, default=None,
                        help="olof_reparse_diff snapshot to print beside the live counts.")
    parser.add_argument("--residuals", action="store_true",
                        help="List every zero-song and truncated concert.")
    args = parser.parse_args(argv)
    return run_parser(args.db, args.before, args.residuals)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
