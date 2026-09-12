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
                    LB-vs-TUIT tracklist agreement rates (C15), plus the Phase 3
                    rows (d)/(e)/(f) corpus-wide file-format, taper and venue
                    corroboration rates (C16).
    --premieres     Phase 3 row (b) / D-02 gate item 2: backend.qc.corroborate.tour_premieres
                    on 2010-03-29 — which positions are premieres per our corpus vs
                    setlist.fm, and the count vs olof_events.tour_new_count (C15).
    --d01           D-01 accept cases: backend.dossier_fields.completeness on 2010-03-29
                    (every source basis tracklist) and 1965-06-01 (LB-10364/12222 1/12,
                    LB-08855's missing positions, LB-06654 fails G2) (C17).
    --d02           D-02: backend.dossier_fields.song_history — 2010-03-29 badges songs 4
                    and 14 only, then the premiere-gate pass rate over 200 sampled concerts
                    (seeded) with the failing gate items tallied (C18).
    --d03           D-03 accept cases: backend.dossier_fields.official_release —
                    1965-06-01 full, 1986-02-24 partial, 1975-12-08 partial (C19; the
                    plan's "none" predates allowlisting the 2019 Rolling Thunder box).
    --d07           D-07 / D-04 accept cases on 2010-03-29: Zepp Tokyo night 7 of 7, is_last
                    false, Tokyo city_total = 50 with the sum invariant, and the verified
                    rotation superlative (C20; unblocked by the BUG-347 parser repair).
    --d05           D-05 / D-13 accept cases (LB-15005 / 09493 / 06654 / 08637 generation,
                    LB-08493 no "low gen", every 1965-06-01 source audio_from_video), corpus
                    tallies, then a seeded 100-row generation audit table for sign-off (C21).
    --d09           D-09 / D-11 accept cases: backend.dossier_fields.setlist_confidence on
                    1986-02-24 (complete, 25 songs, corroborated) and a synthetic 7-song
                    fixture (partial), backend.dossier_fields.file_meta on LB-08485
                    ("16/44 file · recorded 24/96"), then the corpus scan of every remaining
                    'partial' setlist for review (C22).
    --d23           Supporting-parser accept cases (C23): band/members on 1988-06-07
                    (1st NET Band) and 1965-04-09 (solo), writers on event 2, lineage_short
                    cutting LB-6 before "eac", runtime split-sums-total on LB-1, set[].label
                    banding on 1965-06-01 (BBC TV-1 band + markers), a QC-blocked vs
                    disputed vs confirmed taper render, family.basis on a waveform+LB+quality
                    family, then corpus-wide runtime/band/taper tallies.
    --d24           D-08 / D-10 accept cases: backend.dossier_fields.compare_sources on
                    2010-03-29 (LB-08637 best-scan alternate 90 vs 84, no resolution
                    alternate, no "smaller file set" claim) and 1965-06-01 (runtime alt),
                    backend.dossier_fields.anchor_bobtalk on 1986-02-24 (>=3 anchored
                    lines) and 2010-03-29 (collapses, no empty container), then corpus
                    tallies for both (C24).

Usage::

    .venv/bin/python3 tools/dossier_acceptance.py --parser
    .venv/bin/python3 tools/dossier_acceptance.py --parser --before .debug/olof_before.db
    .venv/bin/python3 tools/dossier_acceptance.py --parser --residuals
    .venv/bin/python3 tools/dossier_acceptance.py --corroborate --before .debug/olof_before.db
    .venv/bin/python3 tools/dossier_acceptance.py --premieres
    .venv/bin/python3 tools/dossier_acceptance.py --d01
    .venv/bin/python3 tools/dossier_acceptance.py --d02
    .venv/bin/python3 tools/dossier_acceptance.py --d03
    .venv/bin/python3 tools/dossier_acceptance.py --d09
    .venv/bin/python3 tools/dossier_acceptance.py --d23
    .venv/bin/python3 tools/dossier_acceptance.py --d24

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
    :func:`corroborate.tracklist_corpus_agreement`) — C15 — and the Phase 3
    rows (d)/(e)/(f) rates (:func:`corroborate.file_format_corpus_agreement`,
    :func:`corroborate.taper_corpus_agreement`,
    :func:`corroborate.venue_corpus_agreement`) — C16.
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

        fmt = corroborate.file_format_corpus_agreement(live)
        _log.info(
            "corpus-wide file-vs-lineage resolution agreement: %d/%d (%.1f%%)",
            fmt["agree"], fmt["total"], fmt["rate"] * 100,
        )

        tpr = corroborate.taper_corpus_agreement(live)
        _log.info(
            "corpus-wide taper corroboration: %d/%d corroborated (%.1f%%), %d disputed",
            tpr["corroborated"], tpr["total"], tpr["rate"] * 100, tpr["disputed"],
        )

        ven = corroborate.venue_corpus_agreement(live)
        _log.info(
            "corpus-wide venue corroboration: %d/%d corroborated (%.1f%%), %d disputed",
            ven["corroborated"], ven["total"], ven["rate"] * 100, ven["disputed"],
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


def run_d01(db_path: Path) -> int:
    """D-01 accept cases (C17): per-source completeness on 2010-03-29 and 1965-06-01."""
    from backend.dossier_fields import completeness
    from backend.geocoder import entry_date_to_iso

    live = _open_ro(db_path)
    try:
        lbs_by_date: dict[str, list[int]] = {"2010-03-29": [], "1965-06-01": []}
        for r in live.execute("SELECT lb_number, date_str FROM entries"):
            iso = entry_date_to_iso(r["date_str"] or "")
            if iso in lbs_by_date:
                lbs_by_date[iso].append(r["lb_number"])
        results = {}
        for date_iso, lbs in lbs_by_date.items():
            event_id = corroborate.primary_event_id(live, date_iso)
            results[date_iso] = completeness(live, event_id, lbs) if event_id else {}
            for lb, c in sorted(results[date_iso].items()):
                _log.info(
                    "%s LB-%05d %-9s %s/%s %-12s fit=%s missing=%s", date_iso, lb,
                    c["basis"], c["songs_present"], c["songs_total"], c["confidence"],
                    c["fits_show"], [m["position"] for m in c["missing"]],
                )
    finally:
        live.close()

    tokyo, bbc = results["2010-03-29"], results["1965-06-01"]
    excerpts = [bbc.get(lb) for lb in (10364, 12222)]
    checks = [
        (len(tokyo) == 9 and all(c["basis"] == "tracklist" for c in tokyo.values()),
         "2010-03-29: all 9 sources basis tracklist"),
        (all(c and (c["songs_present"], c["songs_total"]) == (1, 12) for c in excerpts),
         "1965-06-01: LB-10364 and LB-12222 read 1/12"),
        (bool(bbc.get(8855) and bbc[8855]["missing"]),
         "1965-06-01: LB-08855 lists its missing positions"),
        (bool(bbc.get(6654)) and not bbc[6654]["fits_show"],
         "1965-06-01: LB-06654 fails G2 (tracklist doesn't match this show)"),
    ]
    _log.info("")
    for ok, label in checks:
        _log.info("%s  %s", "PASS" if ok else "FAIL", label)
    return 0 if all(ok for ok, _ in checks) else 1


_D02_SAMPLE = 200
_D02_SEED = 342


def run_d02(db_path: Path) -> int:
    """D-02 accept case (C18) plus the premiere-gate pass rate over a seeded sample."""
    import random
    import re
    from collections import Counter

    from backend.dossier_fields import song_history

    live = _open_ro(db_path)
    try:
        event_id = corroborate.primary_event_id(live, "2010-03-29")
        hist = song_history(live, event_id) if event_id else None
        badged = [s["position"] for s in hist["songs"] if s["premiere_badge"]] if hist else []
        ok = bool(hist) and hist["gate_passed"] and badged == [4, 14]
        _log.info(
            "%s  2010-03-29 premiere badges %s = [4, 14] (gate %s)",
            "PASS" if ok else "FAIL", badged, hist["gate_reasons"] if hist else "no event",
        )

        cmap = corroborate.load_canonical_map(live)
        ids = [
            r["event_id"] for r in live.execute(
                "SELECT DISTINCT sp.event_id, oe.event_type, oe.tour_name"
                " FROM song_performances sp JOIN olof_events oe USING (event_id)"
                " ORDER BY sp.event_id"
            ) if corroborate.is_concert_row(r["event_type"], r["tour_name"])
        ]
        sample = random.Random(_D02_SEED).sample(ids, min(_D02_SAMPLE, len(ids)))
        passed = badges = gap_badges = 0
        reasons: Counter[str] = Counter()
        for eid in sample:
            h = song_history(live, eid, cmap)
            passed += h["gate_passed"]
            badges += sum(s["premiere_badge"] for s in h["songs"])
            gap_badges += sum(s["gap_badge"] for s in h["songs"])
            reasons.update(re.sub(r"\[.*\]|\d+", "N", r) for r in h["gate_reasons"])
    finally:
        live.close()

    _log.info("")
    _log.info(
        "premiere gate passed on %d/%d sampled concerts (%.1f%%): %d premiere badges,"
        " %d gap badges", passed, len(sample), 100 * passed / len(sample), badges, gap_badges,
    )
    for reason, n in reasons.most_common():
        _log.info("  %4d  %s", n, reason)
    return 0 if ok else 1


_D03_CASES = (
    ("1965-06-01", "full"),
    ("1986-02-24", "partial"),
    # Song 5 is on CD 14 of The Rolling Thunder Revue: The 1975 Live Recordings (2019).
    ("1975-12-08", "partial"),
)


def run_d03(db_path: Path) -> int:
    """D-03 accept cases (C19): backend.dossier_fields.official_release on three dates."""
    from backend.dossier_fields import official_release

    live = _open_ro(db_path)
    checks = []
    try:
        for date_iso, expected in _D03_CASES:
            event_id = corroborate.primary_event_id(live, date_iso)
            result = official_release(live, event_id) if event_id else None
            status = result["status"] if result else None
            ok = status == expected
            checks.append((ok, f"{date_iso} -> {status} (expected {expected})"))
            if result:
                _log.info(
                    "%s  %-12s status=%-8s whole_show=%s %s", "PASS" if ok else "FAIL",
                    date_iso, status, result["whole_show"], result["whole_show_title"] or "",
                )
                for s in result["songs"]:
                    if s["matches"]:
                        _log.info(
                            "         pos %2d %-30s official=%s partial=%s",
                            s["position"], s["song_title"][:30], s["official"], s["partial"],
                        )
    finally:
        live.close()

    _log.info("")
    for ok, label in checks:
        _log.info("%s  %s", "PASS" if ok else "FAIL", label)
    return 0 if all(ok for ok, _ in checks) else 1


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


def run_d07(db_path: Path) -> int:
    """D-07 / D-04 accept cases (C20) on 2010-03-29."""
    from backend.dossier_fields import rotation_rank, run_context

    live = _open_ro(db_path)
    try:
        event_id = corroborate.primary_event_id(live, "2010-03-29")
        rc = run_context(live, event_id) if event_id else None
        run = rc["venue_run"] if rc else None
        rank = rotation_rank(live, event_id, run) if run else None
    finally:
        live.close()

    tour = rc["tour"] if rc else None
    city = rc["city_history"] if rc else None
    if tour:
        _log.info("tour %r: concert %d of %d (is_last=%s, claims_ok=%s)", tour["name"],
                  tour["position"], tour["size"], tour["is_last"], tour["claims_ok"])
    if city:
        _log.info("city %s, %s (%s): %d concerts", city["city"], city["country"],
                  city["basis"], city["total"])
    if rank:
        _log.info("rotation %d%%: rank %d of %d, median %s, tie=%s — nights %s", rank["pct"],
                  rank["rank_in_run"], rank["run_size"], rank["run_median_pct"], rank["tie"],
                  [(s["pct"], "ok" if s["verified"] else "UNVERIFIED") for s in rank["siblings"]])
    checks = [
        (bool(run) and (run["venue"], run["position"], run["size"]) == ("Zepp Tokyo", 7, 7),
         "2010-03-29: Zepp Tokyo run, night 7 of 7"),
        (bool(tour) and tour["is_last"] is False,
         "is_last false (the tour continues to Seoul): no closing claim"),
        (bool(city) and city["total"] == 50, "Tokyo city_total = 50"),
        (bool(city) and city["invariant_ok"], "city history rows sum to city_total"),
        (bool(rank) and rank["rank_in_run"] == 1 and not rank["tie"] and rank["superlative_ok"],
         "72% is the run's verified maximum, so the superlative renders"),
    ]
    _log.info("")
    for ok, label in checks:
        _log.info("%s  %s", "PASS" if ok else "FAIL", label)
    return 0 if all(ok for ok, _ in checks) else 1


_D05_CASES = (
    (15005, "silver"),
    (9493, "vinyl"),
    (6654, "silver"),
    # The plan said unknown; tj ruled (2026-09-11) that its bootleg_titles row makes it silver.
    (8637, "silver"),
)
_D05_AUDIT_ROWS = 100
_D05_SEED = 342


def run_d05(db_path: Path) -> int:
    """D-05 / D-13 accept cases (C21), corpus tallies, then a seeded audit table."""
    import random

    from backend.dossier_fields import classify_generation, classify_medium
    from backend.geocoder import entry_date_to_iso

    live = _open_ro(db_path)
    try:
        checks: list[tuple[bool, str]] = []
        for lb, want in _D05_CASES:
            g = classify_generation(live, lb)
            checks.append((g["generation"] == want,
                           f"LB-{lb:05d} {want} (got {g['generation']}: {g['evidence']})"))
        g = classify_generation(live, 8493)
        checks.append((g["generation"] != "low_gen",
                       f"LB-08493 shows no 'low gen' (got {g['generation']})"))
        bbc = [r["lb_number"] for r in live.execute("SELECT lb_number, date_str FROM entries")
               if entry_date_to_iso(r["date_str"] or "") == "1965-06-01"]
        media = [classify_medium(live, lb) for lb in bbc]
        checks.append((
            bool(media) and all(m["medium"] == "audio_from_video" and m["broadcast"]
                                for m in media),
            f"1965-06-01: all {len(media)} sources audio_from_video, broadcast (no taper lines)",
        ))

        generations: Counter[str] = Counter()
        mediums: Counter[str] = Counter()
        for (lb,) in live.execute("SELECT lb_number FROM entries").fetchall():
            gen = classify_generation(live, lb)
            generations[f"{gen['generation']}/{gen['basis'] or '-'}"] += 1
            med = classify_medium(live, lb)
            mediums[f"{med['medium']}{' broadcast' if med['broadcast'] else ''}"] += 1
        _log.info("generation: %s", dict(generations.most_common()))
        _log.info("medium: %s", dict(mediums.most_common()))

        with_chain = [r[0] for r in live.execute(
            "SELECT lb_number FROM entries WHERE COALESCE(source_chain, '') != ''"
            " ORDER BY lb_number"
        )]
        sample = random.Random(_D05_SEED).sample(with_chain, min(_D05_AUDIT_ROWS, len(with_chain)))
        _log.info("")
        _log.info("generation audit — %d random LBs with a lineage (seed %d):",
                  len(sample), _D05_SEED)
        for lb in sorted(sample):
            gen = classify_generation(live, lb)
            chain = live.execute(
                "SELECT source_chain FROM entries WHERE lb_number = ?", (lb,),
            ).fetchone()[0]
            _log.info("LB-%05d %-9s %-8s %-30s | %s", lb, gen["generation"], gen["basis"] or "",
                      (gen["evidence"] or "")[:30], chain[:80])
    finally:
        live.close()

    _log.info("")
    for ok, label in checks:
        _log.info("%s  %s", "PASS" if ok else "FAIL", label)
    return 0 if all(ok for ok, _ in checks) else 1


def run_d09(db_path: Path) -> int:
    """D-09 / D-11 accept cases (C22), then a corpus scan of every remaining 'partial'."""
    from backend.dossier_fields import file_meta, setlist_confidence
    from backend.geocoder import entry_date_to_iso

    live = _open_ro(db_path)
    try:
        entries_by_date: dict[str, list[int]] = {}
        for r in live.execute("SELECT lb_number, date_str FROM entries"):
            iso = entry_date_to_iso(r["date_str"] or "")
            if iso:
                entries_by_date.setdefault(iso, []).append(r["lb_number"])

        event_id = corroborate.primary_event_id(live, "1986-02-24")
        sc = setlist_confidence(live, event_id, entries_by_date.get("1986-02-24", [])) \
            if event_id else None
        fm = file_meta(live, 8485)
        checks = [
            (bool(sc) and (sc["status"], sc["songs_listed"], sc["verdict"])
             == ("complete", 25, "corroborated"),
             "1986-02-24 -> "
             f"{sc['status'] if sc else None}, {sc['songs_listed'] if sc else '?'} songs,"
             f" {sc['verdict'] if sc else '?'} (expected complete, 25, corroborated)"),
            (fm["resolution"] == "16/44 file · recorded 24/96",
             f"LB-08485 file_meta resolution = {fm['resolution']!r}"),
        ]
        _log.info("")
        for ok, label in checks:
            _log.info("%s  %s", "PASS" if ok else "FAIL", label)
        _log.info("")
        _log.info("synthetic 7-song fixture (no real show belongs in the live corpus scan):"
                  " see tests/test_setlist_confidence_file_meta.py"
                  "::test_synthetic_short_fixture_reads_partial_from_runtime (-> partial)")

        _log.info("")
        _log.info("corpus scan: every remaining 'partial' setlist (for review)")
        cmap = corroborate.load_canonical_map(live)
        n_partial = n_complete = n_unavailable = 0
        for date_iso, _quorum in corroborate.corroborate_all(live):
            eid = corroborate.primary_event_id(live, date_iso)
            if eid is None:
                continue
            result = setlist_confidence(live, eid, entries_by_date.get(date_iso, []), cmap)
            if result["status"] == "partial":
                n_partial += 1
                _log.info("  %-11s basis=%-16s notice=%s", date_iso, result["basis"],
                          result["notice"])
            elif result["status"] == "complete":
                n_complete += 1
            else:
                n_unavailable += 1
        _log.info("")
        _log.info("%d complete, %d partial, %d unavailable (%d dated concerts)",
                  n_complete, n_partial, n_unavailable, n_complete + n_partial + n_unavailable)
    finally:
        live.close()
    return 0 if all(ok for ok, _ in checks) else 1


def run_d23(db_path: Path) -> int:
    """C23 supporting-parser accept cases, then corpus-wide tallies."""
    from backend.dossier_fields import (
        broadcast_set_labels, family_basis, lineage_short, parse_band_lineup,
        parse_runtime, song_writers, taper_render,
    )

    live = _open_ro(db_path)
    try:
        checks: list[tuple[bool, str]] = []

        lineup = live.execute(
            "SELECT lineup FROM olof_events WHERE event_id = 9100"
        ).fetchone()[0]
        band = parse_band_lineup(lineup)
        checks.append((
            band["band_index"] == 1 and band["band_label"] == "First Never-Ending Tour Band"
            and band["members"] and band["members"][0]["name"] == "Bob Dylan",
            f"1988-06-07 (event 9100) band_index=1, 'First Never-Ending Tour Band',"
            f" Dylan first (got {band['band_index']!r}, {band['band_label']!r},"
            f" {band['members'][:1]})",
        ))

        lineup2 = live.execute(
            "SELECT lineup FROM olof_events WHERE event_id = 845"
        ).fetchone()[0]
        solo = parse_band_lineup(lineup2)
        checks.append((
            solo["band_label"] == "Solo" and len(solo["members"]) == 1,
            f"1965-04-09 (event 845) band.label = 'Solo', one member (got {solo!r})",
        ))

        w = song_writers(live, 2, 1)
        checks.append((
            w["value"] == "Shirley Goodman & Leonard Lee" and not w["corrected"],
            f"event 2 song 1 writers = 'Shirley Goodman & Leonard Lee' (got {w!r})",
        ))
        w_dylan = song_writers(live, 2, 99)
        checks.append((
            w_dylan["value"] is None,
            f"event 2 song 99 (nonexistent -> solely Dylan's / no credit) omits (got {w_dylan!r})",
        ))

        chain = live.execute(
            "SELECT source_chain FROM entries WHERE lb_number = 6"
        ).fetchone()[0]
        short = lineage_short(chain)
        checks.append((
            short == "CSHEB w/ bass roll-off active > M1, trade cdr",
            f"LB-6 lineage_short cuts before 'eac' (got {short!r} from {chain!r})",
        ))

        timing = live.execute("SELECT timing FROM entries WHERE lb_number = 1").fetchone()[0]
        rt = parse_runtime(timing)
        checks.append((
            bool(rt) and rt["total_minutes"] == sum(rt["parts"]) and rt["total_minutes"] == 233.0,
            f"LB-1 runtime split sums to total (G5) (got {rt!r})",
        ))

        event_1965 = corroborate.primary_event_id(live, "1965-06-01")
        labels, notes = broadcast_set_labels(live, event_1965) if event_1965 else ([], [])
        bands = [lbl for lbl in labels if lbl["kind"] == "band"]
        markers = [lbl for lbl in labels if lbl["kind"] == "marker"]
        checks.append((
            any(lbl["positions"] == [7, 8, 9, 10, 11, 12] for lbl in bands) and markers
            and not notes,
            "1965-06-01 BBC TV-1 26 June contiguous 7-12 bands, other broadcast notes stay"
            f" per-song markers (got {len(bands)} bands, {len(markers)} markers,"
            f" {len(notes)} session notes)",
        ))

        blocked = taper_render(live, 3762)  # open R-T3 error
        checks.append((
            blocked["name"] is None,
            f"LB-3762 (open R-T3 error) renders no taper (got {blocked!r})",
        ))
        disputed = taper_render(live, 10041)  # open R-T4 warn, disputed vs TUIT
        checks.append((
            disputed["name"] is not None and disputed["notice"] is not None,
            f"LB-10041 (R-T4 disputed) renders name + notice (got {disputed!r})",
        ))
        confirmed = taper_render(live, 45)
        checks.append((
            confirmed["name"] == "clay c brennecke" and confirmed["marker"] is None,
            f"LB-45 confirmed taper renders plainly (got {confirmed!r})",
        ))

        fam_row = live.execute(
            "SELECT fam_id FROM tapematch_family_meta WHERE conf IS NOT NULL"
            " AND by = 'ai+lb' ORDER BY fam_id LIMIT 1"
        ).fetchone()
        if fam_row:
            fb = family_basis(live, fam_row[0])
            checks.append((
                fb["conf"] is not None and any("LB page" in n for n in fb["notes"]),
                f"family {fam_row[0]} basis includes the correlation mean + LB-page note"
                f" (got {fb!r})",
            ))

        _log.info("")
        for ok, label in checks:
            _log.info("%s  %s", "PASS" if ok else "FAIL", label)

        _log.info("")
        _log.info("corpus tallies:")
        n_runtime = n_no_runtime = 0
        for (timing,) in live.execute("SELECT timing FROM entries"):
            if parse_runtime(timing) is not None:
                n_runtime += 1
            else:
                n_no_runtime += 1
        _log.info("  runtime parses: %d, no timing/no minute token: %d", n_runtime, n_no_runtime)

        band_counts: Counter[str] = Counter()
        for (lineup,) in live.execute("SELECT lineup FROM olof_events WHERE lineup != ''"):
            b = parse_band_lineup(lineup)
            band_counts["band_index" if b["band_index"] else
                        ("solo" if b["band_label"] == "Solo" else "unrecognised")] += 1
        _log.info("  band lineups: %s", dict(band_counts.most_common()))

        # Inlined rather than calling taper_render per LB: that would call
        # corroborate.taper_check (which rebuilds the taper-alias tables on
        # every call) tens of thousands of times -- fine for one accept-case
        # LB, far too slow over the whole corpus. The disputed/notice branch
        # never flips a "rendered" LB to "nothing", so it's safe to skip here.
        blocked_lbs = {
            int(r[0]) for r in live.execute(
                "SELECT DISTINCT entity_key FROM qc_findings WHERE entity_kind = 'lb'"
                " AND rule_id IN ('R-T1', 'R-T2', 'R-T3') AND status IN ('open', 'reopened')"
            )
            if str(r[0]).isdigit()
        }
        renderable = {
            r["lb_number"] for r in live.execute(
                "SELECT lb_number FROM taper_attributions WHERE conflict = 0"
            )
        } - blocked_lbs
        n_total = live.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        taper_counts = Counter(rendered=len(renderable), nothing=n_total - len(renderable))
        _log.info("  taper render: %s", dict(taper_counts.most_common()))
    finally:
        live.close()
    return 0 if all(ok for ok, _ in checks) else 1


def run_d24(db_path: Path) -> int:
    """D-08 / D-10 accept cases (C24), then corpus tallies."""
    from backend.dossier_fields import anchor_bobtalk, compare_sources
    from backend.geocoder import entry_date_to_iso

    live = _open_ro(db_path)
    try:
        checks: list[tuple[bool, str]] = []

        date_2010 = "2010-03-29"
        event_2010 = corroborate.primary_event_id(live, date_2010)
        visible_2010 = [
            r[0] for r in live.execute(
                "SELECT lb_number FROM entries WHERE date_str = ? AND status = 'ok'", ("3/29/10",),
            )
        ]
        cs_2010 = compare_sources(live, event_2010, date_2010, visible_2010)
        scan_alt = next((a for a in cs_2010["alternates"] if a["axis"] == "scan"), None)
        checks.append((
            bool(scan_alt) and scan_alt["lb_number"] == 8637
            and round(scan_alt["alt_value"]) == 90 and round(scan_alt["pick_value"]) == 84,
            f"2010-03-29: LB-08637 is the best-scan alternate, 90 vs 84 (got {scan_alt!r})",
        ))
        res_alt = next((a for a in cs_2010["alternates"] if a["axis"] == "resolution"), None)
        checks.append((
            res_alt is None,
            f"2010-03-29: no resolution alternate (LB-08476 ties at 16/44 file,"
            f" LB-08493 is lineage-only) (got {res_alt!r})",
        ))
        checks.append((
            not any(a["axis"] == "filecount" for a in cs_2010["alternates"]),
            "2010-03-29: no 'smaller file set' claim (audit M17)",
        ))

        date_1965 = "1965-06-01"
        event_1965 = corroborate.primary_event_id(live, date_1965)
        visible_1965 = [
            r[0] for r in live.execute(
                "SELECT lb_number FROM entries WHERE date_str = ? AND status = 'ok'", ("6/1/65",),
            )
        ]
        cs_1965 = compare_sources(live, event_1965, date_1965, visible_1965)
        # Amended 2026-09-12 (tj): the runtime floor is the 2-minute rounding floor, so the
        # +4 min source renders as a "longest runtime" alternate instead of collapsing.
        rt_1965 = [a for a in cs_1965["alternates"] if a["axis"] == "runtime"]
        checks.append((
            not cs_1965["collapsed"] and len(rt_1965) == 1
            and rt_1965[0]["alt_value"] - rt_1965[0]["pick_value"] >= 2.0,
            f"1965-06-01: a 'longest runtime' alternate, >= 2 min (got collapsed="
            f"{cs_1965['collapsed']}, diffs={cs_1965['diffs']}, alternates={cs_1965['alternates']})",
        ))

        event_1986 = corroborate.primary_event_id(live, "1986-02-24")
        bt_1986 = anchor_bobtalk(live, event_1986)
        checks.append((
            len(bt_1986["anchored"]) >= 3,
            f"1986-02-24: anchors >= 3 bobtalk lines (got {len(bt_1986['anchored'])})",
        ))

        bt_2010 = anchor_bobtalk(live, event_2010)
        checks.append((
            bt_2010["anchored"] == [] and bt_2010["context"] == [],
            f"2010-03-29: bobtalk collapses with no empty container (got {bt_2010!r})",
        ))

        _log.info("")
        for ok, label in checks:
            _log.info("%s  %s", "PASS" if ok else "FAIL", label)

        entries_by_date: dict[str, list[int]] = {}
        for r in live.execute("SELECT lb_number, date_str, status FROM entries"):
            if r["status"] != "ok":
                continue
            iso = entry_date_to_iso(r["date_str"] or "")
            if iso:
                entries_by_date.setdefault(iso, []).append(r["lb_number"])

        _log.info("")
        _log.info("corpus tallies: D-08 compare_sources over every dated show with a pick")
        n_collapsed = n_open = n_no_pick = 0
        n_alternates: Counter[str] = Counter()
        for date_iso, lb_numbers in entries_by_date.items():
            eid = corroborate.primary_event_id(live, date_iso)
            if eid is None:
                continue
            cs = compare_sources(live, eid, date_iso, lb_numbers)
            if cs["pick"] is None:
                n_no_pick += 1
                continue
            if cs["collapsed"]:
                n_collapsed += 1
            else:
                n_open += 1
                for alt in cs["alternates"]:
                    n_alternates[alt["axis"]] += 1
        _log.info("  %d collapsed, %d with a comparison to show, %d no show_picks row",
                  n_collapsed, n_open, n_no_pick)
        _log.info("  alternates by axis: %s", dict(n_alternates.most_common()))

        _log.info("")
        _log.info("corpus tallies: D-10 anchor_bobtalk over every event with a bobtalk block")
        n_events_anchored = n_events_no_anchor = 0
        n_anchor_lines = n_context_lines = 0
        for (eid,) in live.execute(
            "SELECT event_id FROM olof_events WHERE bobtalk IS NOT NULL AND bobtalk != ''"
        ):
            bt = anchor_bobtalk(live, eid)
            if bt["anchored"]:
                n_events_anchored += 1
            elif bt["context"]:
                n_events_no_anchor += 1
            n_anchor_lines += len(bt["anchored"])
            n_context_lines += len(bt["context"])
        _log.info(
            "  %d events with >=1 anchored line, %d with bobtalk but no anchor,"
            " %d anchored lines total, %d leftover context lines",
            n_events_anchored, n_events_no_anchor, n_anchor_lines, n_context_lines,
        )
    finally:
        live.close()
    return 0 if all(ok for ok, _ in checks) else 1


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
    mode.add_argument("--d01", action="store_true",
                      help="D-01 accept cases: per-source completeness + G2 (C17).")
    mode.add_argument("--d02", action="store_true",
                      help="D-02 accept case + premiere-gate rate over 200 concerts (C18).")
    mode.add_argument("--d03", action="store_true",
                      help="D-03 accept cases: official_release status on three dates (C19).")
    mode.add_argument("--d07", action="store_true",
                      help="D-07 / D-04 accept cases: run, tour, city, rotation rank (C20).")
    mode.add_argument("--d05", action="store_true",
                      help="D-05 / D-13 accept cases, tallies and a 100-row audit table (C21).")
    mode.add_argument("--d09", action="store_true",
                      help="D-09 / D-11 accept cases + corpus 'partial' setlist scan (C22).")
    mode.add_argument("--d23", action="store_true",
                      help="Supporting-parser accept cases + corpus tallies (C23).")
    mode.add_argument("--d24", action="store_true",
                      help="D-08 compare_sources / D-10 anchor_bobtalk accept cases +"
                           " corpus tallies (C24).")
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
    if args.d01:
        return run_d01(args.db)
    if args.d02:
        return run_d02(args.db)
    if args.d03:
        return run_d03(args.db)
    if args.d07:
        return run_d07(args.db)
    if args.d05:
        return run_d05(args.db)
    if args.d09:
        return run_d09(args.db)
    if args.d23:
        return run_d23(args.db)
    if args.d24:
        return run_d24(args.db)
    return run_parser(args.db, args.before, args.residuals)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
