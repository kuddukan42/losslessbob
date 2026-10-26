"""Search, entry lookups, library performances payload + categories.

Split from backend.db (TODO-369 S2).
"""

import sqlite3

from backend.db import get_connection
from backend.db.taper import classify_source_type, is_known_taper


def search_entries(query, field="all", year=None, limit=None, db_path=None):
    """Search entries using FTS5 when a query is present, falling back to LIKE on FTS syntax errors."""
    conn = get_connection(db_path)

    year_clause = ""
    year_params: list = []
    if year is not None:
        short = str(year)[-2:]
        long_ = str(year)
        year_clause = "AND (e.date_str LIKE ? OR e.date_str LIKE ?)"
        year_params = [f"%/{short}", f"%/{long_}"]

    if query:
        if field == "location":
            fts_query = f"location:{query}"
        elif field == "date":
            fts_query = f"date_str:{query}"
        else:
            fts_query = query

        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status, lm.lb_status, lm.public_no_checksums,
                   e.taper_name, e.source_chain, e.lb_category, e.source_type
            FROM entries_fts
            JOIN entries e ON e.lb_number = entries_fts.rowid
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE entries_fts MATCH ?
            {year_clause}
            ORDER BY rank
            {limit_clause}
        """
        params: list = [fts_query] + year_params
    else:
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        sql = f"""
            SELECT e.lb_number, e.date_str, e.location, e.rating,
                   e.description, e.status, lm.lb_status, lm.public_no_checksums,
                   e.taper_name, e.source_chain, e.lb_category, e.source_type
            FROM entries e
            LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
            WHERE 1=1 {year_clause}
            ORDER BY e.lb_number
            {limit_clause}
        """
        params = year_params

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # FTS5 syntax error fallback — revert to LIKE
        like = f"%{query}%"
        fallback_sql = (
            "SELECT e.lb_number, e.date_str, e.location, e.rating,"
            " e.description, e.status, lm.lb_status, lm.public_no_checksums,"
            " e.taper_name, e.source_chain, e.lb_category, e.source_type"
            " FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
            " WHERE e.description LIKE ? OR e.location LIKE ? OR e.date_str LIKE ?"
            " ORDER BY e.lb_number"
        )
        fallback_params = [like, like, like]
        if limit is not None:
            fallback_sql += " LIMIT ?"
            fallback_params.append(int(limit))
        rows = conn.execute(fallback_sql, fallback_params).fetchall()

    results = [dict(r) for r in rows]

    # When the query is a bare integer, ensure the entry with that lb_number is
    # included even when none of its text fields contain the number (e.g. searching
    # "1797" for LB-01797 whose date/location fields don't contain that token).
    if query:
        try:
            lb_id = int(query)
            if not any(r["lb_number"] == lb_id for r in results):
                direct = conn.execute(
                    "SELECT e.lb_number, e.date_str, e.location, e.rating,"
                    " e.description, e.status, lm.lb_status, lm.public_no_checksums,"
                    " e.taper_name, e.source_chain, e.lb_category, e.source_type"
                    " FROM entries e LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
                    " WHERE e.lb_number = ?",
                    (lb_id,),
                ).fetchone()
                if direct:
                    results.insert(0, dict(direct))
        except ValueError:
            pass

    for r in results:
        if not r.get("source_type"):
            r["source_type"] = classify_source_type(r.get("description"), r.get("source_chain"))
        # taper_known lets consumers distinguish a curated taper (display-worthy,
        # e.g. Library grid pill) from an unvalidated free-text guess (still
        # shown raw in the scrape-preview screen, but not as an authoritative badge).
        r["taper_known"] = is_known_taper(r.get("taper_name"))

    return results


def _year_from_date_str(date_str: str) -> int:
    """Extract a year from entries.date_str (M/D/YY, possibly 'xx' for M/D).

    Mirrors gui_next's extractYear() so server- and client-derived years
    never disagree for the same row.
    """
    if not date_str:
        return 0
    parts = date_str.split("/")
    if len(parts) < 3:
        return 0
    try:
        n = int(parts[-1].strip())
    except ValueError:
        return 0
    if n < 100:
        return 1900 + n if n >= 49 else 2000 + n
    return n


_STATUS_RANK: dict[str, int] = {"public": 0, "private": 1, "missing": 2}
_STATUS_LABEL: dict[str, str] = {"public": "Public", "private": "Private", "missing": "Missing"}


# ── Library payload extension (FABLE_UNIFIED_RANKING phase 3) ───────────────
# Per instructions/SPEC_INTEGRATION_NOTES.md finding F4, ranking phase 3
# defines the payload-extension pattern for get_performances(): flat fields
# merged onto each recording, no N+1 calls — taper phase 2 follows the same
# pattern for confirmed-taper. All three helpers below feature-detect their
# source table/column so a fresh install (or one that hasn't run a Concert
# Ranker scan yet) degrades to "no extra fields" instead of erroring.

def _load_pick_ranks(conn: sqlite3.Connection) -> dict[int, int]:
    """Return ``{lb_number: pick_rank}`` from ``show_picks``.

    Empty on a fresh install (pre ``POST /api/derived/recompute``) — the
    table always exists (``USER_TABLES``/``SCHEMA_SQL``) but starts empty.
    """
    rows = conn.execute("SELECT lb_number, pick_rank FROM show_picks").fetchall()
    return {r["lb_number"]: r["pick_rank"] for r in rows}


def _load_curated_by_lb(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Return ``{lb_number: [curated_list_name, ...]}`` from curated lists.

    A recording can appear in more than one curator's list (e.g. carbonbit
    and 10haaf agreeing), so the value is always a list.
    """
    rows = conn.execute(
        "SELECT cl.name AS name, ce.lb_number AS lb_number"
        " FROM curated_list_entries ce JOIN curated_lists cl ON cl.id = ce.list_id"
    ).fetchall()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["lb_number"], []).append(r["name"])
    return out


def _load_latest_abs_grades(conn: sqlite3.Connection) -> dict[int, str]:
    """Return ``{lb_number: abs_grade}`` from the most recent scan.

    Mirrors ``concert_ranker/picks.py:_load_latest_quality`` — the newest
    scan is the one that actually wrote ``quality_recording_scores`` rows
    (``quality_scans`` also includes small calibration-only runs), and
    ``abs_grade`` is feature-detected via ``PRAGMA table_info`` because it's
    added by ``concert_ranker/lb/repo.py``'s ``ensure_schema`` migration, not
    this module's ``SCHEMA_SQL``, so a DB that has never been scanned via
    Concert Ranker doesn't have the column yet. The scan is
    ``repo.scored_scan_id`` (most score rows), not ``MAX(scan_id)`` (BUG-345).
    """
    from concert_ranker.lb import repo as cr_repo

    scan_id = cr_repo.scored_scan_id(conn)
    if scan_id is None:
        return {}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    if "abs_grade" not in cols:
        return {}
    rows = conn.execute(
        "SELECT lb_number, abs_grade FROM quality_recording_scores"
        " WHERE scan_id=? AND abs_grade IS NOT NULL",
        (scan_id,),
    ).fetchall()
    return {r["lb_number"]: r["abs_grade"] for r in rows}


def _load_taper_attributions(conn: sqlite3.Connection) -> dict[int, dict]:
    """Return ``{lb_number: {"confirmed"?: str, "propagated"?: str, "review": bool}}``.

    `confidence='confirmed'` rows render the solid taper pill (spec §5).
    Conflict-free `propagated` rows also carry the taper name since 2026-07-16
    (TODO-242 decision): they render a visually-distinct outline pill in the
    Library. `inferred`/`conflict` rows (and propagated ones too) still feed
    the "taper: needs review" filter via `review`. Feature-detected like
    `_load_latest_abs_grades` since `taper_attributions` may not exist yet on an
    older DB that hasn't run `tools/attribute_tapers.py`.
    """
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='taper_attributions'"
        ).fetchall()
    }
    if "taper_attributions" not in tables:
        return {}
    rows = conn.execute(
        "SELECT lb_number, taper_normalised, confidence, conflict FROM taper_attributions"
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        entry: dict = {}
        if r["confidence"] == "confirmed":
            entry["confirmed"] = r["taper_normalised"]
        elif r["confidence"] == "propagated" and not r["conflict"]:
            entry["propagated"] = r["taper_normalised"]
        if r["confidence"] in ("propagated", "inferred") or r["conflict"]:
            entry["review"] = True
        if entry:
            out[r["lb_number"]] = entry
    return out


def get_pick_badges(db_path=None) -> dict[int, dict]:
    """Flat pick/quality/curated/taper badge fields keyed by LB number.

    The Library's recording lens is sourced from ``/api/search`` +
    ``/api/collection/prefetch`` — neither joins ``show_picks``,
    ``quality_recording_scores``, ``curated_lists`` or ``taper_attributions`` —
    so it can't surface the badges the performance lens gets inline from
    ``get_performances``. This feeds a client-side merge-by-``lb_number``, the
    same pattern the recording lens already uses for TapeMatch families and
    collection prefetch (``instructions/SPEC_INTEGRATION_NOTES.md`` F4; the
    TODO-186 remainder). Reuses the exact loaders ``get_performances`` uses, so
    the two lenses can never disagree on a badge.

    Only LB numbers carrying at least one signal appear, and each dict omits
    fields that don't exist for that recording — identical to the per-recording
    shape ``get_performances`` merges.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        ``{lb_number: {"pickRank"?, "absGrade"?, "curated"?, "taperConfirmed"?,
        "taperPropagated"?, "taperReview"?}}`` — empty on a fresh install
        before recompute.
    """
    conn = get_connection(db_path)
    pick_ranks = _load_pick_ranks(conn)
    curated_by_lb = _load_curated_by_lb(conn)
    abs_grades = _load_latest_abs_grades(conn)
    taper_attrs = _load_taper_attributions(conn)

    out: dict[int, dict] = {}
    for lb, rank in pick_ranks.items():
        out.setdefault(lb, {})["pickRank"] = rank
    for lb, grade in abs_grades.items():
        if grade:
            out.setdefault(lb, {})["absGrade"] = grade
    for lb, names in curated_by_lb.items():
        if names:
            out.setdefault(lb, {})["curated"] = names
    for lb, attr in taper_attrs.items():
        if "confirmed" in attr:
            out.setdefault(lb, {})["taperConfirmed"] = attr["confirmed"]
        if "propagated" in attr:
            out.setdefault(lb, {})["taperPropagated"] = attr["propagated"]
        if attr.get("review"):
            out.setdefault(lb, {})["taperReview"] = True
    return out


def get_performances(db_path=None) -> list[dict]:
    """Group catalog entries into shows for the Library screen's performance lens.

    Aggregates by raw `(date_str, location)` — the same pair
    `06-gap-analysis.md` §B3 identifies as the grouping key. This lives in the
    backend (per the TODO-150 step 5 decision) rather than as a client-side
    groupBy because building real show metadata means cross-referencing
    `bobdylan_shows`, `setlistfm_shows`, and `bootleg_titles` — none of which
    `/api/search` exposes, and duplicating those joins client-side would mean
    re-fetching/re-indexing three more tables in the GUI for no benefit.

    TapeMatch family data is deliberately NOT joined in here — per
    `07-tapematch-backend-integration.md` §4, the Library's data adapter
    fetches `/api/tapematch/families` separately and merges by `lb_number`,
    same as it already does for `/api/collection/prefetch`.

    `lb_category = 'concert'` entries are grouped into shows as before — this
    now includes dates whose only source is `dylan_performances` with category
    `GUEST` (appearance at another artist's show, e.g. Dire Straits/U2/Tom
    Petty/Grateful Dead sets) or `NET` (a Never Ending Tour-era tag, not
    "internet" — both were missing from `_PERF_CATEGORY_MAP` until the
    TODO-151 audit, 2026-06-18). When `bobdylan_shows` has no row for the date
    (true for nearly all GUEST dates, since they're not Dylan's own shows),
    `venue` falls back to `dylan_performances.venue` instead of staying null.

    `lb_category = 'unknown'` entries are ALSO included, but only when they
    have a fully-specified date (no `xx` placeholder) and a non-blank
    location — i.e. when the raw data is concrete enough to form a real show
    grouping even though nothing matched. These render as a degraded row
    (`confirmed: False` — no venue/setlist/tour, since by definition nothing
    matched). This is the fallback for cases `dylan_performances` doesn't
    cover either (e.g. category `FILM` — concert-like footage shoots such as
    the 1986 Bristol Colston Hall "Hearts of Fire" filming — deliberately left
    unmapped since some FILM rows are non-performance B-roll, not shows).
    radio/tv/interview/studio/rehearsal/soundcheck/compilation/other
    recordings, and 'unknown' ones with no usable date+location, still have no
    real show to group into; they remain visible in the recording lens instead
    (TODO-150 decision, 2026-06-18).

    Per instructions/FABLE_UNIFIED_RANKING.md §6 and finding F4, each
    recording also carries flat, optional `pickRank` (`show_picks.pick_rank`
    for its date — 1 is the recommended copy), `absGrade` (latest Concert
    Ranker `quality_recording_scores.abs_grade` scan), and `curated` (list of
    curated-list names it appears in, e.g. `["carbonbit"]`) fields, following
    the same "merge flat fields onto each recording, no N+1 calls" pattern
    already used for TapeMatch family data (merged client-side instead, since
    it's a different consumer — see the class docstring's TapeMatch note).

    Per `archive/specs/FABLE_TAPER_ATTRIBUTION.md` §5 (TAPER phase 2), each
    recording also carries flat, optional `taperConfirmed` (canonical taper
    name, only when `taper_attributions.confidence='confirmed'`),
    `taperPropagated` (canonical taper name for conflict-free
    `confidence='propagated'` rows — outline pill in the Library, TODO-242
    decision 2026-07-16), and `taperReview` (`true` when confidence is
    `propagated`/`inferred` or the row is flagged `conflict`), following the
    same F4 payload-extension pattern.

    Uncirculated/upcoming olof dates (`backend.gap_analysis.uncirculated_dates`
    — olof concert dates with zero entries coverage, i.e. the Gaps screen's
    `'gap'`/`'future'` classifications) are appended as recording-less rows
    (`recordings: []`, `status: "Missing"`) carrying an explicit `coverage`
    field (`"uncirculated"` or `"upcoming"`) so the Library can render them
    distinctly from ordinary entry-derived rows, which never carry `coverage`.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        List of performance dicts (data contract Entity 2 shape): `id`,
        `date`, `disp`, `year`, `venue`, `city`, `status`, `recordings`
        always present; `dow`, `tour`, `tracks`, `setlist`, `title` omitted
        (not null-faked) when no source data exists for that show; `confirmed`
        omitted (true by default) except `False` on degraded unknown-only rows.
        `tuitCirculating` (bool) is present when TUIT's show spine has the date:
        tracker availability only, never "no tape exists" (TODO-338 part 4).
        Each recording additionally omits `pickRank`/`absGrade`/`curated`/
        `taperConfirmed`/`taperReview` when that signal doesn't exist yet for
        its LB number (pre-recompute, never scanned, in no curated list, or
        no taper attribution row). `coverage` (`"uncirculated"` | `"upcoming"`)
        is present only on appended recording-less olof-only rows; absent on
        ordinary entry-derived rows.
    """
    from datetime import datetime as _dt

    conn = get_connection(db_path)
    pick_ranks = _load_pick_ranks(conn)
    curated_by_lb = _load_curated_by_lb(conn)
    abs_grades = _load_latest_abs_grades(conn)
    taper_attrs = _load_taper_attributions(conn)

    rows = conn.execute(
        """
        SELECT e.lb_number, e.date_str, e.location, e.rating, e.source_type,
               e.description, e.source_chain, e.lb_category, lm.lb_status
        FROM entries e
        LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number
        WHERE e.lb_category IN ('concert', 'unknown')
        """
    ).fetchall()

    bd_shows: dict[str, sqlite3.Row] = {
        r["date_str"]: r
        for r in conn.execute(
            "SELECT date_str, venue, location, bobdylan_url FROM bobdylan_shows"
        ).fetchall()
    }
    # Fallback venue source for shows bobdylan_shows doesn't track (guest spots,
    # tour dates it's missing) — dylan_performances has real venue names for
    # these (TODO-151). Only consulted when bd_shows has no match.
    dp_venues: dict[str, sqlite3.Row] = {}
    for r in conn.execute(
        "SELECT date_str, venue, city, country FROM dylan_performances"
        " WHERE venue NOT IN ('', '?')"
    ).fetchall():
        dp_venues.setdefault(r["date_str"], r)
    setlist_counts: dict[str, int] = {
        r["bobdylan_url"]: r["n"]
        for r in conn.execute(
            "SELECT bobdylan_url, COUNT(*) AS n FROM bobdylan_setlist GROUP BY bobdylan_url"
        ).fetchall()
    }
    tours: dict[str, str] = {}
    for r in conn.execute(
        "SELECT date_str, tour_name FROM setlistfm_shows WHERE tour_name != ''"
    ).fetchall():
        tours.setdefault(r["date_str"], r["tour_name"])
    # Tour-name fallback chain setlistfm -> olof (TODO-290, FABLE_OLOF_FILES.md
    # §5.3): setlistfm's tour_name coverage is thin, olof_events carries the DSN
    # segment title (1956-2021) for nearly every dated event. setdefault() means
    # setlistfm always wins; this only fills dates setlistfm left blank. Ordered
    # so a 'concert' row is tried before session/rehearsal/etc. rows on dates
    # with more than one olof event (e.g. a same-day session write-up).
    for r in conn.execute(
        """SELECT date_str, tour_name FROM olof_events
           WHERE tour_name != '' AND date_str != ''
           ORDER BY (event_type != 'concert'), event_id"""
    ).fetchall():
        tours.setdefault(r["date_str"], r["tour_name"])
    titles: dict[int, str] = {}
    for r in conn.execute(
        "SELECT lb_number, title FROM bootleg_titles WHERE title != ''"
    ).fetchall():
        titles.setdefault(r["lb_number"], r["title"])
    tuit_circ = _load_tuit_circulating(conn)

    # Group key: ISO date when the date is fully parseable (Bob Dylan never
    # plays two venues on the same calendar day), else raw "date_str::location"
    # for entries whose date can't be resolved (ambiguous/incomplete dates).
    # Using ISO date as the primary key collapses the common case where different
    # recordings of the same show have slightly different `location` strings
    # (e.g. "Munich" vs "Munich, West Germany") that previously produced
    # multiple duplicate show rows for the same concert.
    groups: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        date_str = r["date_str"] or ""
        location = r["location"] or ""
        iso = _entry_date_to_iso_local(date_str)
        if r["lb_category"] == "unknown":
            # Only degraded-confirm 'unknown' rows with a real date + location —
            # see TODO-151 audit note above. Skip the rest (blank/'xx' dates,
            # no location) just like before.
            if not location.strip() or not iso:
                continue
        key = iso if iso else f"{date_str}::{location}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "recordings": [], "best_status": "missing", "any_concert": False,
                "date_str": date_str, "location": location, "iso": iso,
            }
            order.append(key)
        if r["lb_category"] == "concert":
            g["any_concert"] = True
        status_raw = r["lb_status"] or "missing"
        if _STATUS_RANK.get(status_raw, 2) < _STATUS_RANK.get(g["best_status"], 2):
            g["best_status"] = status_raw
        rec_out = {
            "lb": f"LB-{r['lb_number']:05d}",
            "lbNumber": r["lb_number"],
            "src": r["source_type"] or classify_source_type(r["description"], r["source_chain"]),
            "rating": r["rating"] or "",
            "status": _STATUS_LABEL.get(status_raw, "Missing"),
        }
        pick_rank = pick_ranks.get(r["lb_number"])
        if pick_rank is not None:
            rec_out["pickRank"] = pick_rank
        abs_grade = abs_grades.get(r["lb_number"])
        if abs_grade:
            rec_out["absGrade"] = abs_grade
        curated_names = curated_by_lb.get(r["lb_number"])
        if curated_names:
            rec_out["curated"] = curated_names
        taper_attr = taper_attrs.get(r["lb_number"])
        if taper_attr:
            if "confirmed" in taper_attr:
                rec_out["taperConfirmed"] = taper_attr["confirmed"]
            if "propagated" in taper_attr:
                rec_out["taperPropagated"] = taper_attr["propagated"]
            if taper_attr.get("review"):
                rec_out["taperReview"] = True
        g["recordings"].append(rec_out)

    performances: list[dict] = []
    for key in order:
        g = groups[key]
        date_str = g["date_str"]
        location = g["location"]
        iso = g["iso"]
        disp = date_str
        dow = None
        if iso:
            try:
                dt = _dt.strptime(iso, "%Y-%m-%d")
                disp = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
                dow = dt.strftime("%a")
            except ValueError:
                iso = None

        bd = bd_shows.get(iso) if iso else None
        dp = dp_venues.get(iso) if (iso and not bd) else None
        perf: dict = {
            "id": iso or f"{date_str}::{location}",
            "date": iso if iso else date_str,
            "disp": disp,
            "year": _year_from_date_str(date_str),
            "venue": bd["venue"] if bd else (dp["venue"] if dp else None),
            "city": (dp["city"] if dp else None) or location or None,
            "status": _STATUS_LABEL.get(g["best_status"], "Missing"),
            "recordings": sorted(g["recordings"], key=lambda x: x["lbNumber"]),
        }
        if dow:
            perf["dow"] = dow
        if not g["any_concert"]:
            perf["confirmed"] = False
        tour = tours.get(iso) if iso else None
        if tour:
            perf["tour"] = tour
        if bd:
            perf["setlist"] = iso
            n = setlist_counts.get(bd["bobdylan_url"])
            if n:
                perf["tracks"] = n
        title = next((titles[rec["lbNumber"]] for rec in g["recordings"]
                       if rec["lbNumber"] in titles), None)
        if title:
            perf["title"] = title
        if iso and iso in tuit_circ:
            perf["tuitCirculating"] = tuit_circ[iso]
        performances.append(perf)

    from backend import gap_analysis

    existing_ids = {p["id"] for p in performances}
    uncirculated = [
        u for u in gap_analysis.uncirculated_dates(db_path) if u["date_iso"] not in existing_ids
    ]
    for u in sorted(uncirculated, key=lambda x: x["date_iso"]):
        date_iso = u["date_iso"]
        dt = _dt.strptime(date_iso, "%Y-%m-%d")
        perf = {
            "id": date_iso,
            "date": date_iso,
            "disp": f"{dt.strftime('%b')} {dt.day}, {dt.year}",
            "dow": dt.strftime("%a"),
            "year": int(date_iso[:4]),
            "venue": u["venue"],
            "city": u["city"],
            "status": "Missing",
            "recordings": [],
            "coverage": u["coverage"],
        }
        if u["tour"]:
            perf["tour"] = u["tour"]
        if date_iso in tuit_circ:
            perf["tuitCirculating"] = tuit_circ[date_iso]
        performances.append(perf)

    return performances


def _load_tuit_circulating(conn: sqlite3.Connection) -> dict[str, bool]:
    """Map ISO date -> whether TUIT's tracker lists a circulating recording.

    ``tuit_shows.circulating = 0`` means the TUIT tracker has no torrent for
    the show, NOT that no tape exists (LB holds recordings for ~1,269 dates
    TUIT calls uncirculated), so callers must label it tracker availability.
    A date with several TUIT rows is True if any row circulates. Dates TUIT
    has no row for are absent; a missing table (older DB) yields ``{}``.

    Args:
        conn: Open SQLite connection.

    Returns:
        ``{iso_date: bool}`` for every date present in ``tuit_shows``.
    """
    try:
        rows = conn.execute(
            "SELECT date_str, MAX(COALESCE(circulating, 0)) AS c "
            "FROM tuit_shows GROUP BY date_str"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["date_str"]: bool(r["c"]) for r in rows}


_PERF_CATEGORY_MAP: dict[str, str] = {
    "MCONCERT":   "concert",
    "NET":        "concert",   # "Never Ending Tour" era tag, not "internet" — real shows
    "GUEST":      "concert",   # guest appearance at another artist's show — still a real show
    "RADIO":      "radio",
    "TV":         "tv",
    "INTERVIEW":  "interview",
    "SESSION":    "studio",
    "SDEMO":      "studio",
    "HOME":       "studio",
    "SIDEMAN":    "studio",    # backing-musician recording session for another artist
    "REHEARSAL":  "rehearsal",
    "SOUNDCHECK": "soundcheck",
    "COMP":       "compilation",
}

# (category, list-of-lowercase-substrings) checked against description + location
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("interview",   ["interview", "press conference", "in conversation with"]),
    ("radio",       ["radio broadcast", "radio show", "radio station", "for radio", "on the radio"]),
    ("tv",          ["television", "tv show", "tv broadcast", "tv appearance", "tv special",
                     "late show", "tonight show", "ed sullivan", "letterman"]),
    ("studio",      ["studio session", "studio recording", "recording session",
                     "demo session", "demo recording"]),
    ("rehearsal",   ["rehearsal"]),
    ("soundcheck",  ["soundcheck", "sound check"]),
    ("compilation", ["compilation", "greatest hits", "best of", "anthology"]),
]


def _entry_date_to_iso_local(date_str: str) -> str | None:
    """Convert entries.date_str (M/D/YY) to YYYY-MM-DD; return None for 'xx' dates."""
    if not date_str or "xx" in date_str.lower():
        return None
    parts = date_str.split("/")
    if len(parts) != 3:
        return None
    try:
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year = 1900 + year if year >= 49 else 2000 + year
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def classify_entry_categories(db_path=None, conn=None) -> dict[str, int]:
    """Classify every entry in the DB and write lb_category.

    Priority:
      1. bobdylan_shows date match → 'concert'
      2. dylan_performances.category → mapped via _PERF_CATEGORY_MAP → known category or 'other'
      3. Keyword search in description + location → non-concert category
      4. Fallback → 'unknown'

    Args:
        db_path: Optional DB path override.
        conn: Optional existing connection (used during init_db backfill to share
              the write-locked connection).

    Returns:
        Dict of counts: {classified, concert, radio, tv, interview, studio,
        rehearsal, soundcheck, compilation, other, unknown}.
    """
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection(db_path)

    # Build a set of all dates present in bobdylan_shows for fast lookup
    bd_dates: set[str] = {
        r[0] for r in conn.execute("SELECT DISTINCT date_str FROM bobdylan_shows").fetchall()
    }
    # Build a dict of ISO date → mapped category from dylan_performances (first match wins)
    perf_map: dict[str, str] = {}
    for row in conn.execute("SELECT date_str, category FROM dylan_performances").fetchall():
        iso = row[0]
        cat = _PERF_CATEGORY_MAP.get((row[1] or "").upper())
        if cat and iso not in perf_map:
            perf_map[iso] = cat

    entries = conn.execute(
        "SELECT lb_number, date_str, description, location FROM entries"
    ).fetchall()

    counts: dict[str, int] = {"classified": 0}
    updates: list[tuple[str, int]] = []

    for row in entries:
        lb       = row[0]
        date_raw = (row[1] or "")
        desc     = (row[2] or "").lower()
        loc      = (row[3] or "").lower()
        text     = desc + " " + loc

        # Tier 0: xx in date_str → multi-date compilation (day/month unknown)
        if "xx" in date_raw.lower():
            category = "compilation"
        else:
            iso = _entry_date_to_iso_local(date_raw)
            # Tier 1: bobdylan.com concert date
            if iso and iso in bd_dates:
                category = "concert"
            # Tier 2: dylan_performances mapping
            elif iso and iso in perf_map:
                category = perf_map[iso]
            # Tier 3: keyword heuristics (non-concert only)
            else:
                category = "unknown"
                for cat, keywords in _KEYWORD_RULES:
                    if any(kw in text for kw in keywords):
                        category = cat
                        break

        updates.append((category, lb))
        counts["classified"] = counts.get("classified", 0) + 1
        counts[category] = counts.get(category, 0) + 1

    conn.executemany("UPDATE entries SET lb_category=? WHERE lb_number=?", updates)
    if _own_conn:
        conn.commit()

    return counts


def classify_one_entry(date_str: str, description: str, location: str, conn) -> str:
    """Return the lb_category for a single entry given its field values and an open connection.

    Uses the same priority order as classify_entry_categories():
      1. bobdylan_shows date match → 'concert'
      2. dylan_performances category map
      3. Keyword heuristics (non-concert)
      4. 'unknown'

    Intended for use inside write-queue closures where the connection is already open.

    Args:
        date_str: Raw entries.date_str value (e.g. '7/28/00').
        description: Entry description text (may be empty).
        location: Entry location text (may be empty).
        conn: Open SQLite connection.

    Returns:
        Category string.
    """
    date_raw = date_str or ""

    # Tier 0: xx in date_str → multi-date compilation (day/month unknown)
    if "xx" in date_raw.lower():
        return "compilation"

    iso = _entry_date_to_iso_local(date_raw)
    if iso:
        if conn.execute("SELECT 1 FROM bobdylan_shows WHERE date_str=? LIMIT 1", (iso,)).fetchone():
            return "concert"
        perf = conn.execute(
            "SELECT category FROM dylan_performances WHERE date_str=? LIMIT 1", (iso,)
        ).fetchone()
        if perf:
            mapped = _PERF_CATEGORY_MAP.get((perf[0] or "").upper())
            if mapped:
                return mapped
            return "other"

    text = (description or "").lower() + " " + (location or "").lower()
    for cat, keywords in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            return cat

    return "unknown"


def lookup_checksum_owners(checksums, db_path=None):
    """Map each checksum to the LB entries that own it in the checksums table.

    Used to detect when a candidate forum post documents a *different*
    recording than the one being matched: a raw hash lifted from the post body
    that resolves to another lb_number means the post belongs to that entry
    (e.g. a different taper of the same show), not the one under consideration.

    Args:
        checksums: Iterable of checksum hash strings (md5/sha1/ffp) to resolve.
        db_path: Optional database path override.

    Returns:
        Dict mapping each matched checksum string to the sorted list of
        lb_numbers that own it. Checksums with no owner are omitted.
    """
    hashes = {h for h in checksums if h}
    if not hashes:
        return {}
    owners: dict[str, set] = {}
    with get_connection(db_path) as conn:
        # Chunk to stay under SQLite's parameter limit on large posts.
        hash_list = list(hashes)
        for start in range(0, len(hash_list), 400):
            chunk = hash_list[start:start + 400]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT checksum, lb_number FROM checksums "
                f"WHERE checksum IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                owners.setdefault(row["checksum"], set()).add(row["lb_number"])
    return {h: sorted(lbs) for h, lbs in owners.items()}


def get_entry(lb_number, db_path=None):
    with get_connection(db_path) as conn:
        entry = conn.execute("SELECT * FROM entries WHERE lb_number=?", (lb_number,)).fetchone()
        checksums = conn.execute("SELECT * FROM checksums WHERE lb_number=?", (lb_number,)).fetchall()
        files = conn.execute("SELECT * FROM entry_files WHERE lb_number=?", (lb_number,)).fetchall()
        corrections = _entry_corrections(conn, lb_number) if entry else []
    if not entry:
        return None
    return {
        "entry": dict(entry),
        "checksums": [dict(r) for r in checksums],
        "files": [dict(r) for r in files],
        "corrections": corrections,
    }


def _entry_corrections(conn: sqlite3.Connection, lb_number: int) -> list[dict]:
    """Latest ``corrections`` row per field for one entry (TODO-332 reader).

    TUIT fills (``decided_by='tuit_reconcile'``) and curator edits both live
    there; the Library detail panel renders them with their provenance.

    Args:
        conn: Database connection.
        lb_number: The entry.

    Returns:
        ``[{field, original, corrected, reason, decided_by, decided_at}]``,
        one per field, newest decision wins; empty when the table is absent.
    """
    try:
        rows = conn.execute(
            "SELECT field, original, corrected, reason, decided_by, decided_at FROM corrections"
            " WHERE entity_kind = 'entry' AND entity_key = ? ORDER BY decided_at, id",
            (str(lb_number),),
        ).fetchall()
    except sqlite3.OperationalError:  # no corrections table yet
        return []
    latest = {r["field"]: dict(r) for r in rows}
    return [latest[f] for f in sorted(latest)]


def get_distinct_years(db_path=None):
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date_str FROM entries WHERE date_str IS NOT NULL AND date_str != ''"
        ).fetchall()
    years = set()
    for row in rows:
        parts = str(row[0]).split('/')
        if len(parts) >= 3:
            try:
                y = int(parts[-1].strip())
                if y < 100:
                    y = 1900 + y if y >= 49 else 2000 + y
                years.add(y)
            except ValueError:
                pass
    return sorted(years, reverse=True)
