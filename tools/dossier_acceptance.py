#!/usr/bin/env python3
"""Live acceptance checks for the show-dossier redesign (TODO-342).

Prints one PASS/FAIL line per criterion in instructions/SHOW_DOSSIER_REDESIGN_PLAN.md
for the mode asked. Modes arrive chunk by chunk; today there are two:

    --parser        Phase 1: Olof parser corpus counts, then the checks — the two
                    song-count cases (1986-02-24 = 25, 1975-12-08 = 22, shown beside
                    bobdylan.com / setlist.fm / TUIT) and each defect count at its target.
    --corroborate   Phase 3 row (a): backend.qc.corroborate.setlist_quorum on
                    1986-02-24 and 1975-12-08 (corroborated live, disputed
                    against ``--before``), then the corpus-wide verdict shares,
                    plus the Phase 3 rows (b)/(c) corpus-wide rotation and
                    LB-vs-TUIT tracklist agreement rates (C15).
    --premieres     Phase 3 row (b) / D-02 gate item 2: backend.qc.corroborate.tour_premieres
                    on 2010-03-29 — which positions are premieres per our corpus vs
                    setlist.fm, and the count vs olof_events.tour_new_count (C15).

Usage::

    .venv/bin/python3 tools/dossier_acceptance.py --parser
    .venv/bin/python3 tools/dossier_acceptance.py --parser --before .debug/olof_before.db
    .venv/bin/python3 tools/dossier_acceptance.py --parser --residuals
    .venv/bin/python3 tools/dossier_acceptance.py --corroborate --before .debug/olof_before.db
    .venv/bin/python3 tools/dossier_acceptance.py --premieres

``--before`` reads the same counts from a tools/olof_reparse_diff.py snapshot and
prints them beside the live ones (``--parser``), or supplies the pre-Phase-1 Olof
setlist for the two ``--corroborate`` acceptance dates — that snapshot holds only
``olof_*`` tables, so setlist.fm/bobdylan.com/TUIT are always read from the live DB
even in the "before" comparison. ``--residuals`` lists every zero-song and
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

from backend.dossier_fields import is_non_song  # noqa: E402
from backend.paths import DB_PATH  # noqa: E402
from backend.qc import corroborate  # noqa: E402
from backend.qc.rules import MONTH_YEAR_RE, ROTATION_FRAGMENT_RE  # noqa: E402

_log = logging.getLogger(__name__)

_NUMBERED_LINE_RE = re.compile(r"^(\d+)\.(?:\s|$)", re.MULTILINE)
_COMPOSER_PAREN_RE = re.compile(r"\([^()]*[/&][^()]*\)\s*$")
_SONG_COUNT_CASES = (("1986-02-24", 25), ("1975-12-08", 22))
# A "... Bob Dylan concerts in <city>:" header followed by a dated entry line ("1 March 1978",
# "12-13 May 1995", "Late September 1961"). A pointer header followed by a release or recording
# line ("Bob Dylan concerts in Chicago .\n4-6 stereo audience recording") is not a list.
_VENUE_LIST_RE = re.compile(
    r"(?:Bob Dylan\s+(?:shows|concerts)\s+in|\b(?:other|previous|next)\s+(?:shows|concerts))\b"
    r"[^\n]*\n(?:(?:early|mid|late)[\s-]+|\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s+)"
    r"(?:jan|feb|mar|apr|ma[yj]|jun|jul|aug|sep|o[ck]t|nov|dec)",
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


def _olof_titles_from(conn: sqlite3.Connection, date_iso: str) -> list[str]:
    """Olof's primary-event song titles for *date_iso*, read from *conn* (live or --before)."""
    event_id = corroborate.primary_event_id(conn, date_iso)
    if event_id is None:
        return []
    rows = conn.execute(
        "SELECT song_title FROM olof_songs WHERE event_id = ? ORDER BY position", (event_id,)
    ).fetchall()
    titles = [(r["song_title"] or "").strip() for r in rows]
    return [t for t in titles if t and not is_non_song(t)]


def _source_groups(
    conn: sqlite3.Connection, date_iso: str,
) -> dict[str, tuple[dict[str, list[str]], bool]]:
    """setlist.fm/bobdylan.com/TUIT track groups for *date_iso*, from the live DB."""
    sfm: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT l.setlistfm_id, l.track_name FROM setlistfm_setlist l"
        " JOIN setlistfm_shows s USING (setlistfm_id)"
        " WHERE s.date_str = ? AND COALESCE(l.is_tape, 0) = 0"
        " ORDER BY l.setlistfm_id, l.set_index, l.position", (date_iso,)
    ):
        sfm.setdefault(r["setlistfm_id"], []).append(r["track_name"])

    bd: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT l.bobdylan_url, l.track_name FROM bobdylan_setlist l"
        " JOIN bobdylan_shows s USING (bobdylan_url)"
        " WHERE s.date_str = ? ORDER BY l.bobdylan_url, l.position", (date_iso,)
    ):
        bd.setdefault(r["bobdylan_url"], []).append(r["track_name"])

    tuit: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT show_id, song FROM tuit_song_performances WHERE date_str = ? ORDER BY id",
        (date_iso,),
    ):
        tuit.setdefault(str(r["show_id"]), []).append(r["song"])

    return {"setlistfm": (sfm, True), "bobdylan": (bd, True), "tuit": (tuit, False)}


def corroborate_quorum(
    live: sqlite3.Connection, date_iso: str, olof_conn: sqlite3.Connection | None = None,
) -> corroborate.Quorum:
    """setlist_quorum for *date_iso*: sources always from *live*, Olof from *olof_conn* if given.

    Args:
        live: Live DB connection — always the source of setlist.fm/bobdylan.com/TUIT rows.
        date_iso: ISO date to check.
        olof_conn: Connection to read Olof's setlist from, e.g. a ``--before`` snapshot
            that holds only ``olof_*`` tables; defaults to *live*.

    Returns:
        The combined :class:`~backend.qc.corroborate.Quorum`.
    """
    olof_titles = _olof_titles_from(olof_conn or live, date_iso)
    sources = _source_groups(live, date_iso)
    cmap = corroborate.load_canonical_map(live)
    return corroborate.quorum_verdict(olof_titles, sources, cmap)


def corroborate_checks(
    live: sqlite3.Connection, before: sqlite3.Connection | None,
) -> list[tuple[bool, str]]:
    """Phase 3 row (a) acceptance: the two dates read 'corroborated' live, 'disputed' before."""
    checks: list[tuple[bool, str]] = []
    for date, _want in _SONG_COUNT_CASES:
        got = corroborate_quorum(live, date)["verdict"]
        checks.append((got == "corroborated", f"{date} live quorum {got} = corroborated"))
        if before is not None:
            got_before = corroborate_quorum(live, date, olof_conn=before)["verdict"]
            checks.append((
                got_before == "disputed", f"{date} --before quorum {got_before} = disputed",
            ))
    return checks


def corroborate_shares(conn: sqlite3.Connection) -> tuple[dict[str, int], int]:
    """Corpus-wide setlist quorum verdict counts (plan Phase 3 acceptance note)."""
    counts: Counter = Counter()
    for _date, q in corroborate.corroborate_all(conn):
        counts[q["verdict"]] += 1
    return dict(counts), sum(counts.values())


def run_corroborate(db_path: Path, before_path: Path | None) -> int:
    """Print the Phase 3 row (a) acceptance checks, then the corpus-wide verdict shares.

    Also folds in the Phase 3 rows (b)/(c) corpus-wide agreement rates
    (:func:`corroborate.rotation_corpus_agreement`,
    :func:`corroborate.tracklist_corpus_agreement`) — C15.
    """
    live = _open_ro(db_path)
    before = _open_ro(before_path) if before_path else None
    try:
        checks = corroborate_checks(live, before)
        for ok, text in checks:
            _log.info("%s  %s", "PASS" if ok else "FAIL", text)
        failed = sum(1 for ok, _ in checks if not ok)
        _log.info("%d/%d checks pass", len(checks) - failed, len(checks))

        counts, total = corroborate_shares(live)
        _log.info("")
        _log.info("corpus-wide setlist quorum (%d dated concerts):", total)
        for key in ("corroborated", "stated", "disputed", "unavailable"):
            n = counts.get(key, 0)
            share = n / total if total else 0.0
            _log.info("  %-14s %6d  %5.1f%%", key, n, share * 100)

        rot = corroborate.rotation_corpus_agreement(live)
        _log.info("")
        _log.info(
            "corpus-wide rotation-stat agreement: %d/%d (%.1f%%)",
            rot["agree"], rot["total"], rot["rate"] * 100,
        )

        trk = corroborate.tracklist_corpus_agreement(live)
        _log.info(
            "corpus-wide LB-vs-TUIT tracklist agreement: %d/%d (%.1f%%)",
            trk["agree"], trk["total"], trk["rate"] * 100,
        )
    finally:
        live.close()
        if before is not None:
            before.close()
    return 1 if failed else 0


def run_premieres(db_path: Path) -> int:
    """Phase 3 row (b) / D-02 accept case: 2010-03-29 tour-premiere agreement."""
    live = _open_ro(db_path)
    try:
        event_id = corroborate.primary_event_id(live, "2010-03-29")
        if event_id is None:
            _log.info("FAIL  no olof_events row for 2010-03-29")
            return 1
        tp = corroborate.tour_premieres(live, event_id)
        _log.info(
            "2010-03-29 (event %d, tour %r): premiere_count=%d tour_new_count=%s%s",
            event_id, tp["tour_name"], tp["premiere_count"], tp["tour_new_count"],
            "  PASS" if tp["premiere_count_matches"] else "  FAIL",
        )
        _log.info("%-4s %-40s %-6s %-10s %-6s", "pos", "song", "ours", "setlistfm", "agrees")
        for s in tp["songs"]:
            _log.info(
                "%-4d %-40s %-6s %-10s %-6s",
                s["position"], s["song"][:40], s["ours"], s["setlistfm"], s["agrees"],
            )
        ours_premiere_positions = [s["position"] for s in tp["songs"] if s["ours"]]
        ok = ours_premiere_positions == [4, 14] and tp["premiere_count_matches"]
        _log.info("")
        _log.info(
            "%s  our premiere positions %s = [4, 14], count matches tour_new_count",
            "PASS" if ok else "FAIL", ours_premiere_positions,
        )
    finally:
        live.close()
    return 0 if ok else 1


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
    mode.add_argument("--corroborate", action="store_true",
                      help="Phase 3 row (a) setlist quorum checks (also prints the Phase 3"
                           " rows (b)/(c) corpus-wide rotation/tracklist agreement rates).")
    mode.add_argument("--premieres", action="store_true",
                      help="Phase 3 row (b) / D-02 accept case: 2010-03-29 tour premieres.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Live DB (default: data/).")
    parser.add_argument("--before", type=Path, default=None,
                        help="--parser: olof_reparse_diff snapshot to print beside the live"
                             " counts. --corroborate: pre-Phase-1 Olof snapshot to read the"
                             " two acceptance dates' Olof setlist from.")
    parser.add_argument("--residuals", action="store_true",
                        help="--parser only: list every zero-song and truncated concert.")
    args = parser.parse_args(argv)
    if args.corroborate:
        return run_corroborate(args.db, args.before)
    if args.premieres:
        return run_premieres(args.db)
    return run_parser(args.db, args.before, args.residuals)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
