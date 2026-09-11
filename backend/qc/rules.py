"""QC rule definitions for the Show Dossier redesign (TODO-342 Phase 2).

Each rule is a pure function ``(conn) -> Iterable[Finding]`` registered in
:data:`RULES`. Rules never write to the database — :mod:`backend.qc.store`
owns all writes to ``qc_findings``/``qc_decision_log``/``qc_runs``.

``MONTH_YEAR_RE`` and ``ROTATION_FRAGMENT_RE`` are defined here (not in
``tools/``) because backend code must not import from ``tools/``; both
``tools/olof_reparse_diff.py`` and ``tools/dossier_acceptance.py`` import them
from this module instead of defining their own copies.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

# 'March 1978' — what a venue-history date line ('1 March 1978') leaves behind
# once its leading day is read as a song position (P1b).
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
MONTH_YEAR_RE = re.compile(rf"^(?:\d{{1,2}}\s+)?(?:{_MONTHS})\s+\d{{4}}\.?$", re.IGNORECASE)

# Any fragment of Olof's rotation-stat line (P1d).
ROTATION_FRAGMENT_RE = re.compile(
    r"compared to previous concert|new songs? for this tour", re.IGNORECASE
)

# A numbered setlist line ('12. Like A Rolling Stone'), used to count how many
# songs Olof's raw page text lists versus how many the parser produced.
_NUMBERED_LINE_RE = re.compile(r"^(\d+)\.(?:\s|$)", re.MULTILINE)


def _tokens(text) -> list[str]:
    """Split a ';'-joined annotations/released_on string into trimmed tokens."""
    return [t.strip() for t in str(text or "").split(";") if t.strip()]


@dataclass
class Finding:
    """One QC finding a rule function emits for a single entity.

    Attributes:
        entity_kind: What kind of row this finding is about (e.g. 'olof_event').
        entity_key: Stable string key identifying the entity within its kind.
        severity: 'error', 'warn', or 'info'.
        detail: Human-readable one-line explanation.
        evidence: JSON-serialisable dict backing the finding, hashed by the
            run engine to detect whether the underlying data changed.
    """

    entity_kind: str
    entity_key: str
    severity: str
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass
class RuleDef:
    """A registered QC rule.

    Attributes:
        rule_id: Stable ID, e.g. 'R-O1'.
        description: One-line description shown in the CLI/console.
        severity: Default severity for findings this rule emits.
        func: ``(conn) -> Iterable[Finding]``.
    """

    rule_id: str
    description: str
    severity: str
    func: Callable[[sqlite3.Connection], Iterable[Finding]]


def rule_o1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O1: an Olof concert's raw numbered-song count exceeds its parsed count.

    Mirrors the truncated-concert count in ``tools/dossier_acceptance.py``
    (``parser_metrics``): counts distinct numbered lines ('12. ...') in
    ``raw_text`` and compares against the row count in ``olof_songs``.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per truncated concert.
    """
    song_counts = dict(conn.execute("SELECT event_id, COUNT(*) FROM olof_songs GROUP BY event_id"))
    rows = conn.execute(
        "SELECT event_id, date_str, raw_text FROM olof_events"
        " WHERE event_type='concert' AND source != 'bobserve'"
    )
    for ev in rows:
        raw = ev["raw_text"] or ""
        numbered = len(set(_NUMBERED_LINE_RE.findall(raw)))
        parsed = song_counts.get(ev["event_id"], 0)
        if parsed < numbered:
            yield Finding(
                entity_kind="olof_event",
                entity_key=str(ev["event_id"]),
                severity="error",
                detail=(
                    f"{ev['date_str'] or '?'}: parsed {parsed} songs but the raw page "
                    f"lists {numbered} numbered lines"
                ),
                evidence={"date": ev["date_str"], "parsed": parsed, "numbered": numbered},
            )


def rule_o3(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O3: a song's annotations contain a date-shaped or stat-shaped fragment.

    Mirrors ``tools/dossier_acceptance.py``'s ``date_line_annotation_rows`` /
    ``rotation_stat_song_rows`` counters: an annotation token matching
    ``MONTH_YEAR_RE`` (a stray venue-history date) or ``ROTATION_FRAGMENT_RE``
    (a stray rotation-stat fragment) means the parser left page furniture in
    the song row instead of stripping it.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per affected song row.
    """
    rows = conn.execute(
        "SELECT s.event_id, s.position, s.song_title, s.annotations, e.date_str"
        " FROM olof_songs s JOIN olof_events e USING (event_id)"
        " WHERE e.source != 'bobserve'"
    )
    for row in rows:
        tokens = _tokens(row["annotations"])
        bad = [
            t for t in tokens
            if MONTH_YEAR_RE.match(t) or ROTATION_FRAGMENT_RE.search(t)
        ]
        if bad:
            yield Finding(
                entity_kind="olof_song",
                entity_key=f"{row['event_id']}:{row['position']}",
                severity="error",
                detail=(
                    f"{row['date_str'] or '?'}: song '{row['song_title']}' annotation "
                    f"looks like a stray date/stat fragment: {bad!r}"
                ),
                evidence={
                    "date": row["date_str"],
                    "song_title": row["song_title"],
                    "tokens": tokens,
                },
            )


def rule_o2(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O2: Olof concert city/country anomalies (audit D14).

    An empty ``country`` alone is *not* a finding: it's a known Olof format
    quirk affecting 2,705 rows, and D-07 uses the setlist.fm key instead of
    this column for show identity. Instead this flags, per concert:

    - a country name embedded in the city text (e.g. ``'London England'`` —
      the country column is a distinct value elsewhere in the corpus, so the
      known-country set is built from ``olof_events.country`` itself);
    - an empty city;
    - a city string that is paired with two or more different non-empty
      countries across the corpus (e.g. 'London' with both 'England' and
      'Canada') — every event sharing that ambiguous city is flagged, since
      the grouping itself (not one row) is unreliable.

    Args:
        conn: Open SQLite connection.

    Yields:
        One warn Finding per affected concert (an event may fire more than
        once if it matches multiple checks; only the first matching detail
        is emitted per event).
    """
    rows = conn.execute(
        "SELECT event_id, date_str, city, country FROM olof_events"
        " WHERE event_type='concert' AND source != 'bobserve'"
    ).fetchall()
    if not rows:
        return

    countries = sorted({r["country"].strip() for r in rows if r["country"] and r["country"].strip()})

    by_city: dict[str, set[str]] = {}
    for r in rows:
        city = (r["city"] or "").strip()
        country = (r["country"] or "").strip()
        if city and country:
            by_city.setdefault(city, set()).add(country)
    ambiguous_cities = {city for city, cs in by_city.items() if len(cs) >= 2}

    for r in rows:
        city = (r["city"] or "").strip()
        country = (r["country"] or "").strip()
        detail = None
        if not city:
            detail = "concert has an empty city"
        elif any(c and city != c and city.endswith(f" {c}") for c in countries):
            detail = f"city {city!r} looks like it embeds a country name"
        elif city in ambiguous_cities:
            detail = (
                f"city {city!r} is paired with multiple countries in the corpus: "
                f"{sorted(by_city[city])}"
            )
        if detail:
            yield Finding(
                entity_kind="olof_event",
                entity_key=str(r["event_id"]),
                severity="warn",
                detail=f"{r['date_str'] or '?'}: {detail}",
                evidence={"city": city, "country": country},
            )


# Building-type / administrative words dropped when comparing a venue name's
# tokens to a geocoder POI name — see rule_g1. Neither list needs a
# spelling-variant map (e.g. theatre/theater): both spellings are listed, and
# because the word is dropped rather than normalised, it's simply never
# required to match either way.
_VENUE_GENERIC_WORDS = {
    "hall", "theatre", "theater", "auditorium", "centre", "center", "coliseum",
    "arena", "stadium", "gymnasium", "temple", "mosque", "room", "park", "club",
    "house", "hotel", "memorial", "county", "state", "municipal", "complex",
    "building",
}
_VENUE_STOPWORDS = {"the", "of", "and", "at", "in", "on", "de", "la", "le", "du", "der", "des", "&"}
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _venue_tokens(name: str) -> list[str]:
    """Split a venue name into lowercase word tokens, dropping stopwords."""
    words = _WORD_RE.findall((name or "").lower())
    return [w for w in words if w not in _VENUE_STOPWORDS and len(w) > 1]


def rule_g1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-G1: a ``venue_geocoded`` row's venue name doesn't match its geocode.

    The known case (audit D9, M11): 'Zepp Tokyo' was geocoded to 'Zepp
    DiverCity' at low confidence — a different venue in the same city. The
    geocoder's POI name is recorded in ``venue_geocoded.note`` for rows that
    got an actual venue-level match (a comma-joined address string, e.g.
    'Zepp Tokyo, ...'); ``note`` is instead a placeholder like 'city-level pin
    (...)' for rows that were only ever pinned to a city centroid (source
    ``setlistfm_city``/``city_geocode``, confidence 'city') — those never
    claimed venue-level precision and are excluded.

    The venue's name is split into tokens; a fixed set of building-type and
    administrative words (hall, arena, county, ...) is dropped first, since
    those routinely differ between an official venue name and a POI name
    without indicating a wrong match. If every token turns out to be generic
    (nothing distinctive left), all tokens are used instead. A row fires when
    any of its required tokens is missing from the POI (the note's first
    comma-separated component) — e.g. 'Zepp Tokyo' keeps both 'zepp' and
    'tokyo' (neither is generic), and 'tokyo' doesn't appear in the Japanese
    POI text for Zepp DiverCity, so it fires.

    This is a lexical heuristic, not a semantic one: renamed venues (a
    concert hall now sponsored under a different name) will often fire too.
    That's judged an acceptable false-positive rate for a warn-adjacent error
    rule feeding a human review queue (audit: 'tune until false positives are
    rare', not zero).

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per venue/city row whose name doesn't cover the
        geocoder's POI text.
    """
    rows = conn.execute(
        "SELECT venue_norm, city_norm, venue, city, source, confidence, note"
        " FROM venue_geocoded WHERE note IS NOT NULL AND note != '' AND note LIKE '%,%'"
        " AND source != 'setlistfm_city' AND confidence != 'city'"
    ).fetchall()
    for r in rows:
        tokens = _venue_tokens(r["venue"])
        if not tokens:
            continue
        distinctive = [t for t in tokens if t not in _VENUE_GENERIC_WORDS] or tokens
        poi = r["note"].split(",")[0].lower()
        missing = [t for t in distinctive if t not in poi]
        if missing:
            yield Finding(
                entity_kind="venue",
                entity_key=f"{r['venue_norm']}:{r['city_norm']}",
                severity="error",
                detail=(
                    f"venue {r['venue']!r} ({r['city']}) geocoded to POI "
                    f"{r['note'].split(',')[0]!r}; missing tokens {missing!r}"
                ),
                evidence={"venue": r["venue"], "note": r["note"], "missing": missing},
            )


# entries.rating letter scale — mirrors backend.timeline._GRADE_ORDER (spec §1:
# no shared backend/frontend ordinal exists; this is the QC-side copy, kept in
# sync by hand like the others already listed in that module's comment).
_VALID_RATINGS = frozenset({
    "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F",
})


def rule_e1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-E1: entry field ranges — junk timing, out-of-range cdr, bad rating (audit D13).

    - ``timing`` is 'junk' when it's non-empty but contains no 'min' unit at
      all (e.g. 'Heinrich', a lone '0') — 2 rows in the audit.
    - ``cdr`` is out of range when, parsed as an integer, it's <= 0 or > 6 — 24
      rows in the audit. Non-numeric/blank cdr values are not flagged here;
      that's a different kind of problem.
    - ``rating`` is out of range when it's non-empty and not one of the
      standard letter grades (:data:`_VALID_RATINGS`). An empty rating is not
      a finding — it means unrated, not invalid.

    Args:
        conn: Open SQLite connection.

    Yields:
        One warn Finding per entry with at least one bad field.
    """
    rows = conn.execute("SELECT lb_number, timing, cdr, rating FROM entries").fetchall()
    for r in rows:
        problems = []
        timing = (r["timing"] or "").strip()
        if timing and "min" not in timing.lower():
            problems.append(f"timing {timing!r} has no 'min' unit")

        cdr = (r["cdr"] or "").strip()
        if cdr:
            try:
                cdr_n = int(cdr)
            except ValueError:
                cdr_n = None
            if cdr_n is not None and (cdr_n <= 0 or cdr_n > 6):
                problems.append(f"cdr {cdr!r} is out of range (expect 1-6)")

        rating = (r["rating"] or "").strip()
        if rating and rating not in _VALID_RATINGS:
            problems.append(f"rating {rating!r} is not a known grade")

        if problems:
            yield Finding(
                entity_kind="entry",
                entity_key=str(r["lb_number"]),
                severity="warn",
                detail=f"LB-{r['lb_number']}: " + "; ".join(problems),
                evidence={"timing": timing, "cdr": cdr, "rating": rating},
            )


def rule_f1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-F1: a recording family merged at very low confidence, or under review.

    Joins ``recording_families`` (the LB -> ``fam_id`` membership synced from
    TapeMatch) to ``tapematch_family_meta`` (the per-family ``conf``/
    ``review_flag``) and flags any family with ``conf < 0.1`` or
    ``review_flag`` set.

    Args:
        conn: Open SQLite connection.

    Yields:
        One warn Finding per affected family (not per member LB).
    """
    rows = conn.execute(
        "SELECT fam_id, conf, review_flag, review_reason FROM tapematch_family_meta"
        " WHERE conf < 0.1 OR review_flag = 1"
    ).fetchall()
    for r in rows:
        reasons = []
        if r["conf"] is not None and r["conf"] < 0.1:
            reasons.append(f"conf {r['conf']:.3f} < 0.1")
        if r["review_flag"]:
            reasons.append(f"review_flag set ({r['review_reason'] or 'no reason'})")
        yield Finding(
            entity_kind="family",
            entity_key=r["fam_id"],
            severity="warn",
            detail=f"family {r['fam_id']}: " + "; ".join(reasons),
            evidence={"conf": r["conf"], "review_flag": r["review_flag"]},
        )


def _attributions_with_text(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every taper_attributions row with its entry's description and date_str."""
    if not _table_exists_local(conn, "taper_attributions"):
        return []
    return conn.execute(
        "SELECT t.lb_number, t.taper_normalised, t.confidence, t.evidence_json, t.conflict,"
        " e.description, e.date_str"
        " FROM taper_attributions t LEFT JOIN entries e ON e.lb_number = t.lb_number"
        " ORDER BY t.lb_number"
    ).fetchall()


def _entry_year(date_str: str | None) -> int | None:
    """Return the year of an entries.date_str ('M/D/YY', 'M/xx/YY'), or None.

    Uses the same two-digit pivot as ``geocoder.entry_date_to_iso`` but keeps
    partial dates, since only the year matters here.
    """
    parts = (date_str or "").split("/")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[2])
    except ValueError:
        return None
    if year < 100:
        year = 1900 + year if year >= 49 else 2000 + year
    return year


def rule_t1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-T1: a taper attribution rests on a bare mention with no taper-context phrase.

    Layer 0 files a handle found anywhere in an entry's text as a 'mention'.
    Only a mention bound to 'taped by' / 'recorded by' / 'master by' / 'taper'
    is taper evidence (audit D5: 'mm' in the gear name 'MM-EBM-1' credited
    LB-08493 to Mike Millard). Curator-confirmed rows are never flagged.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per LB whose attribution is an unbound mention.
    """
    from backend import db as _db
    from backend import taper_attribution

    # Load user_taper_aliases so their handles have alias keys to match against;
    # a standalone QC process otherwise holds only the builtin table.
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    _db.reload_taper_aliases(db_file or None)
    taper_attribution._rebuild_alias_index()

    for r in _attributions_with_text(conn):
        if r["confidence"] == "confirmed":
            continue
        records = json.loads(r["evidence_json"] or "[]")
        mentions = [e for e in records if e.get("kind") == "mention"]
        if not mentions:
            continue
        if taper_attribution.mention_has_taper_context(r["description"], r["taper_normalised"]):
            continue
        yield Finding(
            entity_kind="lb",
            entity_key=str(r["lb_number"]),
            severity="error",
            detail=(
                f"LB-{r['lb_number']}: taper '{r['taper_normalised']}' rests on a bare "
                "mention with no taper-context phrase"
            ),
            evidence={"taper": r["taper_normalised"], "mention": mentions[0].get("detail")},
        )


def rule_t2(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-T2: a taper was propagated through a review-flagged or low-confidence family.

    A family TapeMatch merged below ``FAMILY_MIN_CONF`` (0.5), or flagged for
    review, is not strong enough to carry a taper to its other members (audit D6).

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per LB whose family evidence names a weak family.
    """
    from backend.taper_attribution import FAMILY_MIN_CONF

    if not _table_exists_local(conn, "tapematch_family_meta"):
        return
    meta = {
        r["fam_id"]: (r["conf"], r["review_flag"])
        for r in conn.execute("SELECT fam_id, conf, review_flag FROM tapematch_family_meta")
    }
    for r in _attributions_with_text(conn):
        if r["confidence"] != "propagated":
            continue
        for e in json.loads(r["evidence_json"] or "[]"):
            fam_id = e.get("fam_id")
            if e.get("kind") != "family" or not fam_id:
                continue
            conf, review_flag = meta.get(fam_id, (None, None))
            if not review_flag and conf is not None and conf >= FAMILY_MIN_CONF:
                continue
            if review_flag:
                reason = "review-flagged"
            elif conf is None:
                reason = "no family confidence"
            else:
                reason = f"conf {conf:.3f} < {FAMILY_MIN_CONF}"
            yield Finding(
                entity_kind="lb",
                entity_key=str(r["lb_number"]),
                severity="error",
                detail=(
                    f"LB-{r['lb_number']}: taper '{r['taper_normalised']}' propagated through "
                    f"family {fam_id} ({reason})"
                ),
                evidence={"taper": r["taper_normalised"], "fam_id": fam_id,
                          "conf": conf, "review_flag": review_flag},
            )
            break


# R-T3's tolerance: a propagated credit may sit this many years outside the
# span of the taper's confirmed recordings before it is implausible.
_TAPER_ERA_SLACK_YEARS = 5


def rule_t3(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-T3: a propagated taper sits more than 5 years outside the taper's confirmed years.

    A taper's confirmed years are the span (min..max year) of the LBs where
    that taper is confirmed-tier. A propagated credit dated outside that span
    widened by 5 years each side is implausible (audit D7). Tapers with no
    dated confirmed LB have no era and are skipped, as are conflict rows (their
    taper is only a placeholder) and LBs without a year.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per out-of-era propagated LB.
    """
    rows = _attributions_with_text(conn)
    span: dict[str, list[int]] = {}
    for r in rows:
        year = _entry_year(r["date_str"])
        if r["confidence"] != "confirmed" or year is None:
            continue
        lo_hi = span.setdefault(r["taper_normalised"], [year, year])
        lo_hi[0] = min(lo_hi[0], year)
        lo_hi[1] = max(lo_hi[1], year)
    for r in rows:
        if r["confidence"] != "propagated" or r["conflict"]:
            continue
        year = _entry_year(r["date_str"])
        era = span.get(r["taper_normalised"])
        if year is None or era is None:
            continue
        lo, hi = era
        if lo - _TAPER_ERA_SLACK_YEARS <= year <= hi + _TAPER_ERA_SLACK_YEARS:
            continue
        yield Finding(
            entity_kind="lb",
            entity_key=str(r["lb_number"]),
            severity="error",
            detail=(
                f"LB-{r['lb_number']}: propagated taper '{r['taper_normalised']}' dated "
                f"{year}, outside its confirmed years {lo}–{hi} (±{_TAPER_ERA_SLACK_YEARS})"
            ),
            evidence={"taper": r["taper_normalised"], "year": year,
                      "confirmed_from": lo, "confirmed_to": hi},
        )


def _max_scalar(conn: sqlite3.Connection, sql: str) -> str | None:
    """Return the single scalar result of *sql*, or None if it's NULL/no rows."""
    row = conn.execute(sql).fetchone()
    return row[0] if row else None


def _norm_ts(ts: str | None) -> str | None:
    """Normalise an ISO-ish timestamp for lexicographic comparison.

    Some tables stamp with a 'T' separator, others with a space; both are
    otherwise 'YYYY-MM-DD HH:MM:SS'-shaped, so replacing 'T' with a space
    makes plain string comparison order them correctly.
    """
    return ts.replace("T", " ") if ts else ts


def rule_s1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-S1: a derived table is older than the inputs it was computed from.

    Three independent staleness checks (audit D4/P7/P8, spec S5/G6):

    - ``show_picks`` older than ``recording_families`` — one table-level
      finding (families synced after the last picks recompute).
    - Per ``entries.lb_number``: the latest ``quality_recording_metrics`` scan
      for that LB is newer than the last rerank (the highest scan_id in
      ``quality_recording_scores``) — measured, but no rerank has run since
      (audit P7: 114 LBs in scans 19–22).
    - ``song_performances`` older than the latest Olof ``olof_pages.parsed_at``
      — one table-level finding (a reparse hasn't been followed by a
      song-index recompute).

    Each check is skipped (yields nothing) when either side's table is
    missing or empty, rather than raising.

    Args:
        conn: Open SQLite connection.

    Yields:
        Table-level and per-LB error Findings for each stale derived table.
    """
    if _table_exists_local(conn, "show_picks") and _table_exists_local(conn, "recording_families"):
        picks_at = _norm_ts(_max_scalar(conn, "SELECT MAX(computed_at) FROM show_picks"))
        families_at = _norm_ts(_max_scalar(conn, "SELECT MAX(imported_at) FROM recording_families"))
        if picks_at and families_at and picks_at < families_at:
            yield Finding(
                entity_kind="table",
                entity_key="show_picks",
                severity="error",
                detail=(
                    f"show_picks last computed {picks_at}, but recording_families "
                    f"was imported more recently ({families_at})"
                ),
                evidence={"show_picks_computed_at": picks_at, "families_imported_at": families_at},
            )

    if _table_exists_local(conn, "quality_recording_metrics") and _table_exists_local(
        conn, "quality_recording_scores"
    ):
        metrics_max = dict(
            conn.execute(
                "SELECT lb_number, MAX(scan_id) FROM quality_recording_metrics GROUP BY lb_number"
            )
        )
        scores_max = dict(
            conn.execute(
                "SELECT lb_number, MAX(scan_id) FROM quality_recording_scores GROUP BY lb_number"
            )
        )
        # Stale = measured after the last rerank. An LB that the last rerank saw but left
        # unscored (unscorable metrics) is not stale, and a rerank wouldn't change it.
        last_rerank = max(scores_max.values(), default=None)
        for lb_number, metrics_scan in metrics_max.items():
            score_scan = scores_max.get(lb_number)
            if last_rerank is not None and metrics_scan > last_rerank:
                yield Finding(
                    entity_kind="lb",
                    entity_key=str(lb_number),
                    severity="error",
                    detail=(
                        f"LB-{lb_number}: latest quality metrics are from scan "
                        f"{metrics_scan}, newer than its latest score (scan {score_scan})"
                    ),
                    evidence={"metrics_scan": metrics_scan, "score_scan": score_scan},
                )

    if _table_exists_local(conn, "song_performances") and _table_exists_local(conn, "olof_pages"):
        perf_at = _norm_ts(_max_scalar(conn, "SELECT MAX(computed_at) FROM song_performances"))
        parsed_at = _norm_ts(_max_scalar(conn, "SELECT MAX(parsed_at) FROM olof_pages"))
        if perf_at and parsed_at and perf_at < parsed_at:
            yield Finding(
                entity_kind="table",
                entity_key="song_performances",
                severity="error",
                detail=(
                    f"song_performances last computed {perf_at}, but an Olof page was "
                    f"parsed more recently ({parsed_at})"
                ),
                evidence={"song_performances_computed_at": perf_at, "olof_parsed_at": parsed_at},
            )


def _table_exists_local(conn: sqlite3.Connection, name: str) -> bool:
    """Return whether table *name* exists and has at least one row.

    Local copy (not imported from :mod:`backend.qc.store`) to keep
    :mod:`backend.qc.rules` free of a dependency on the store module, mirroring
    this module's existing style of not raising when input tables are absent.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    if not exists:
        return False
    return conn.execute(f"SELECT 1 FROM {name} LIMIT 1").fetchone() is not None


RULES: dict[str, RuleDef] = {
    "R-O1": RuleDef(
        rule_id="R-O1",
        description="Olof raw numbered-song count exceeds parsed count",
        severity="error",
        func=rule_o1,
    ),
    "R-O2": RuleDef(
        rule_id="R-O2",
        description="Olof city/country anomalies",
        severity="warn",
        func=rule_o2,
    ),
    "R-O3": RuleDef(
        rule_id="R-O3",
        description="Date-shaped or stat-shaped song annotation",
        severity="error",
        func=rule_o3,
    ),
    "R-G1": RuleDef(
        rule_id="R-G1",
        description="venue_geocoded name tokens don't match the geocoder POI",
        severity="error",
        func=rule_g1,
    ),
    "R-E1": RuleDef(
        rule_id="R-E1",
        description="Entry field ranges (timing, cdr, rating vocabulary)",
        severity="warn",
        func=rule_e1,
    ),
    "R-F1": RuleDef(
        rule_id="R-F1",
        description="Family merged at conf < 0.1, or review_flag set",
        severity="warn",
        func=rule_f1,
    ),
    "R-T1": RuleDef(
        rule_id="R-T1",
        description="Taper evidence is a bare mention with no taper-context phrase",
        severity="error",
        func=rule_t1,
    ),
    "R-T2": RuleDef(
        rule_id="R-T2",
        description="Taper propagated through a review-flagged or conf < 0.5 family",
        severity="error",
        func=rule_t2,
    ),
    "R-T3": RuleDef(
        rule_id="R-T3",
        description="Propagated taper more than 5 years outside its confirmed years",
        severity="error",
        func=rule_t3,
    ),
    "R-S1": RuleDef(
        rule_id="R-S1",
        description="Derived table older than its inputs",
        severity="error",
        func=rule_s1,
    ),
}
