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


def rule_o4(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-O4: Olof's setlist disagrees with >=2 independent sources that agree with each other.

    Runs :func:`backend.qc.corroborate.corroborate_all` (Phase 3 row (a), audit
    Q1-a) over every dated Olof concert and fires on every ``disputed``
    verdict: setlist.fm, bobdylan.com and TUIT are independent of Olof and of
    each other, and when at least two of them agree with each other on a
    setlist that isn't Olof's, Olof's page is the outlier. Keyed the same way
    as R-O1 (``entity_kind='olof_event'``, the date's primary event id) since
    both flag the same ``olof_events`` row from different angles.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per date whose corroboration verdict is 'disputed'.
    """
    from backend.qc.corroborate import corroborate_all, is_order_only_dispute, primary_event_id

    for date_str, quorum in corroborate_all(conn):
        if quorum["verdict"] != "disputed":
            continue
        event_id = primary_event_id(conn, date_str)
        if event_id is None:
            continue
        a, b = quorum["disputed_sources"]
        n = quorum["disputed_song_count"]
        # A reordering alone doesn't withhold the whole setlist: warn, not error.
        order_only = is_order_only_dispute(quorum)
        yield Finding(
            entity_kind="olof_event",
            entity_key=str(event_id),
            severity="warn" if order_only else "error",
            detail=(
                f"{date_str}: {a} and {b} agree with each other on a {n}-song setlist "
                + ("in a different order from Olof's" if order_only
                   else "that disagrees with Olof")
            ),
            evidence={"date": date_str, "quorum": quorum},
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


# R-E2's fit test is the dossier's G2 test (backend.dossier_fields.fits_show); its
# thresholds live there as the FIT_* constants.
_E2_MAX_UNMATCHED = 8


def _olof_candidates_by_date(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Map ISO date -> every Olof song title (and 'title (subtitle)') on that date.

    Unions the songs of every ``olof_events`` row sharing the date (concert,
    broadcast, session...), since an entry dated to a day may be any of them.
    A 'title (subtitle)' form always directly follows its plain title.
    """
    by_date: dict[str, list[str]] = {}
    rows = conn.execute(
        "SELECT oe.date_str, os.song_title, os.subtitle FROM olof_songs os"
        " JOIN olof_events oe ON oe.event_id = os.event_id"
        " WHERE oe.date_str IS NOT NULL AND oe.date_str != ''"
        " ORDER BY oe.date_str, oe.event_id, os.position"
    ).fetchall()
    for r in rows:
        title = (r["song_title"] or "").strip()
        if not title:
            continue
        bucket = by_date.setdefault(r["date_str"], [])
        bucket.append(title)
        subtitle = (r["subtitle"] or "").strip()
        if subtitle:
            bucket.append(f"{title} ({subtitle})")
    return by_date


def entry_setlist_fit(conn: sqlite3.Connection) -> Iterable[dict]:
    """Score every dated entry's tracklist against its date's Olof setlist.

    One pass over ``entries``; Olof songs are indexed by date once and each
    date's :class:`backend.dossier_fields.SetlistIndex` is built on first use.
    Entries with no clean ISO date, no parsed song tracks, or a date with no
    Olof songs are skipped. Tracks tagged ``missing`` don't count (they aren't
    on the recording); partial tracks do.

    Args:
        conn: Open SQLite connection.

    Yields:
        ``{lb_number, date, song_tracks, matched, share, unmatched, olof_songs,
        olof_matched, glued}`` per scored entry: ``unmatched`` holds every
        unmatched cleaned title in order, ``olof_songs``/``olof_matched`` are the
        date's distinct Olof songs and how many of them the entry hit, and
        ``glued`` says a title still holds several track markers (unsplit text).
    """
    from backend.dossier_fields import (
        build_setlist_index,
        is_glued_tracklist,
        match_track,
        parse_entry_tracklist,
    )
    from backend.geocoder import entry_date_to_iso
    from backend.song_index import _load_song_canonical_map

    try:
        canonical_map = _load_song_canonical_map(conn)
    except sqlite3.OperationalError:
        canonical_map = {}
    candidates_by_date = _olof_candidates_by_date(conn)
    indexes: dict = {}

    rows = conn.execute(
        "SELECT lb_number, date_str, setlist FROM entries"
        " WHERE setlist IS NOT NULL AND setlist != '' AND date_str IS NOT NULL"
    ).fetchall()
    for r in rows:
        date_iso = entry_date_to_iso(r["date_str"] or "")
        if not date_iso or date_iso not in candidates_by_date:
            continue
        songs = [
            t["title"] for t in parse_entry_tracklist(r["setlist"])
            if t["is_song"] and not t["missing"]
        ]
        if not songs:
            continue
        index = indexes.get(date_iso)
        if index is None:
            index = build_setlist_index(candidates_by_date[date_iso], canonical_map)
            indexes[date_iso] = index
        unmatched: list[str] = []
        hit: set[str] = set()
        for song in songs:
            m = match_track(song, index, canonical_map)
            if m is None:
                unmatched.append(song)
            else:
                hit.add(m["candidate"].split(" (", 1)[0])
        matched = len(songs) - len(unmatched)
        olof_titles = {c.split(" (", 1)[0] for c in candidates_by_date[date_iso]}
        yield {
            "lb_number": r["lb_number"],
            "date": date_iso,
            "song_tracks": len(songs),
            "matched": matched,
            "share": matched / len(songs),
            "unmatched": unmatched,
            "olof_songs": len(olof_titles),
            "olof_matched": len(hit & olof_titles),
            "glued": is_glued_tracklist(songs),
        }


def rule_e2(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-E2: an entry's tracklist doesn't fit its dated show (plan G2, audit S11).

    The metric is the share of the *entry's* song tracks (non-songs and
    ``missing`` tracks excluded) that match the union of Olof's songs on the
    entry's date — so a short excerpt that is all on the setlist passes, while
    a mis-dated compilation (LB-06654, 25 studio "Mono Mixes" tracks dated
    1965-06-01) fires. The test is the dossier's G2
    (:func:`backend.dossier_fields.fits_show`), run against the union of the
    date's Olof songs: fires below ``FIT_MIN_SHARE``; skips entries with fewer
    than ``FIT_MIN_SONG_TRACKS`` song tracks, entries covering at least
    ``FIT_MAX_SETLIST_COVER`` of the date's Olof songs (Olof lists a subset),
    tracklists the splitter left glued, and dates with no Olof songs.

    Args:
        conn: Open SQLite connection.

    Yields:
        One error Finding per entry whose tracklist mostly misses its dated setlist.
    """
    from backend.dossier_fields import fits_show

    for fit in entry_setlist_fit(conn):
        if fits_show(fit["song_tracks"], fit["matched"], fit["olof_songs"],
                     fit["olof_matched"], fit["glued"]):
            continue
        lb = fit["lb_number"]
        yield Finding(
            entity_kind="entry",
            entity_key=str(lb),
            severity="error",
            detail=(
                f"LB-{lb}: {fit['matched']}/{fit['song_tracks']} song tracks match the"
                f" {fit['date']} setlist ({fit['share']:.0%}) — mis-dated or a compilation?"
            ),
            evidence={
                "date": fit["date"],
                "song_tracks": fit["song_tracks"],
                "matched": fit["matched"],
                "share": round(fit["share"], 3),
                "olof_songs": fit["olof_songs"],
                "olof_matched": fit["olof_matched"],
                "unmatched": fit["unmatched"][:_E2_MAX_UNMATCHED],
            },
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


def rule_t4(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-T4: our taper disagrees with TUIT's uploader-declared taper.

    Both sides go through the live alias tables (``user_taper_aliases``
    included), and a TUIT field naming several tapers or a handle plus a gloss
    agrees when any part matches (``taper_curation.tuit_taper_parts``, via the
    shared :func:`backend.qc.corroborate.taper_agreement` — C16 factors this
    rule's verdict logic out so ``backend.qc.corroborate.taper_check`` /
    ``taper_corpus_agreement`` (Phase 3e) can never drift from it). LBs with
    no TUIT taper, only a placeholder ("unknown"), or a conflict attribution
    are skipped. Feeds Phase 3e as ``disputed`` (audit D8).

    Args:
        conn: Open SQLite connection.

    Yields:
        One warn Finding per LB whose TUIT tapers all differ from ours.
    """
    if not (_table_exists_local(conn, "tuit_recordings")
            and _table_exists_local(conn, "taper_attributions")):
        return
    from backend import db as _db
    from backend.qc.corroborate import taper_agreement

    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    _db.reload_taper_aliases(db_file or None)

    by_lb: dict[int, tuple[str, list[str]]] = {}
    for lb_number, ours, raw in conn.execute(
        "SELECT a.lb_number, a.taper_normalised, t.taper FROM taper_attributions a"
        " JOIN tuit_recordings t ON t.lb_number = a.lb_number"
        " WHERE a.conflict = 0 AND TRIM(COALESCE(t.taper,'')) <> ''"
        " ORDER BY a.lb_number, t.rec_id"
    ):
        by_lb.setdefault(lb_number, (ours, []))[1].append(raw)
    for lb_number, (ours, raws) in by_lb.items():
        verdict, theirs = taper_agreement(ours, raws)
        if verdict != "disputed":
            continue
        yield Finding(
            entity_kind="lb",
            entity_key=str(lb_number),
            severity="warn",
            detail=f"LB-{lb_number}: taper '{ours}', TUIT says {' / '.join(raws)}",
            evidence={"taper": ours, "tuit": raws, "tuit_canonical": theirs},
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
    - Per LB: measured in the ranker's main scan after the last rerank
      (:func:`_stale_quality_scores`).
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

    if _table_exists_local(conn, "quality_recording_metrics"):
        yield from _stale_quality_scores(conn)

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


def _stale_quality_scores(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-S1's per-LB check: quality metrics measured after the last rerank.

    Only the ranker's main scan counts — the one holding the most metric rows,
    which backlog scans append to (``repo.reusable_scan_id``). Calibration runs
    re-measure LBs into their own scan_ids and are never reranked into the
    library's grades, so their newer metrics are not staleness (C09: all 114 of
    the audit's "unscored" LBs were calibration re-measurements).

    Stale = a main-scan metrics row whose ``scored_at`` is newer than the last
    successful ``ranker_rerank`` step run. With no rerank ever recorded, every
    main-scan LB is stale only when that scan has no scores at all.

    Args:
        conn: Open SQLite connection.

    Yields:
        One per-LB error Finding per stale metrics row.
    """
    row = conn.execute(
        "SELECT scan_id FROM quality_recording_metrics GROUP BY scan_id"
        " ORDER BY COUNT(*) DESC, scan_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return
    main_scan = row[0]
    last_rerank = None
    if _table_exists_local(conn, "refresh_step_runs"):
        last_rerank = _norm_ts(_max_scalar(
            conn,
            "SELECT MAX(finished_at) FROM refresh_step_runs"
            " WHERE step_id='ranker_rerank' AND status='ok'",
        ))
    if last_rerank is None and _table_exists_local(conn, "quality_recording_scores"):
        n_scores = conn.execute(
            "SELECT COUNT(*) FROM quality_recording_scores WHERE scan_id=?", (main_scan,)
        ).fetchone()[0]
        if n_scores:
            return
    rows = conn.execute(
        "SELECT lb_number, scored_at FROM quality_recording_metrics WHERE scan_id=?",
        (main_scan,),
    ).fetchall()
    for lb_number, scored_at in rows:
        measured = _norm_ts(scored_at)
        if last_rerank is not None and (measured is None or measured <= last_rerank):
            continue
        yield Finding(
            entity_kind="lb",
            entity_key=str(lb_number),
            severity="error",
            detail=(
                f"LB-{lb_number}: measured in scan {main_scan} at {measured}, after the "
                f"last rerank ({last_rerank or 'never'})"
            ),
            evidence={"scan_id": main_scan, "scored_at": measured, "last_rerank": last_rerank},
        )


_R1_MAX_DATES = 5


def rule_r1(conn: sqlite3.Connection) -> Iterable[Finding]:
    """R-R1: an Olof release string matches neither the D-03 allowlist nor a curator override.

    Scans every whole-show line in ``olof_events.releases_raw`` (a line with
    no leading position-list digit) and every per-position token in
    ``olof_songs.released_on`` (``(part)``/``(uncertain)`` prefix stripped),
    classifying each with :func:`backend.dossier_fields.classify_release_string`.
    Findings group by :func:`backend.dossier_fields.normalize_title_key`, so
    trivial spelling/whitespace variants of one raw string share a finding;
    distinct catalogue-number/date variants of the same release stay separate
    findings until the allowlist grows a pattern that collapses them — by
    design, so the allowlist grows deliberately (plan D-03).

    Args:
        conn: Open SQLite connection.

    Yields:
        One warn Finding per unclassified ``title_key``, entity_kind 'release'.
    """
    from backend.dossier_fields import (
        classify_release_string,
        load_official_releases,
        normalize_title_key,
        release_overrides,
        split_release_tokens,
        strip_release_prefix,
    )

    allow = load_official_releases()
    overrides = release_overrides(conn)
    groups: dict[str, dict] = {}

    def _consider(raw_text: str, date: str | None) -> None:
        raw_text = raw_text.strip()
        if not raw_text:
            return
        title_key = normalize_title_key(raw_text)
        if title_key in overrides:
            return
        _, title, _official = classify_release_string(raw_text, allow, overrides)
        if title is not None:
            return
        g = groups.setdefault(title_key, {"example": raw_text, "count": 0, "dates": []})
        g["count"] += 1
        if date and date not in g["dates"]:
            g["dates"].append(date)

    for ev in conn.execute("SELECT date_str, releases_raw FROM olof_events"):
        for line in (ev["releases_raw"] or "").splitlines():
            line = line.strip().rstrip(".")
            if not line or line[0].isdigit():
                continue
            _consider(line, ev["date_str"])

    for row in conn.execute(
        "SELECT oe.date_str, os.released_on FROM olof_songs os"
        " JOIN olof_events oe ON oe.event_id = os.event_id WHERE os.released_on != ''"
    ):
        for token in split_release_tokens(row["released_on"]):
            text, _is_part, _is_uncertain = strip_release_prefix(token)
            _consider(text, row["date_str"])

    for title_key, g in groups.items():
        dates = sorted(d for d in g["dates"] if d)[:_R1_MAX_DATES]
        yield Finding(
            entity_kind="release",
            entity_key=title_key,
            severity="warn",
            detail=f"unclassified release string ({g['count']}x): {g['example'][:140]}",
            evidence={"raw": g["example"], "count": g["count"], "dates": dates},
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
    "R-O4": RuleDef(
        rule_id="R-O4",
        description="Olof setlist disagrees with >=2 agreeing independent sources",
        severity="error",
        func=rule_o4,
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
    "R-E2": RuleDef(
        rule_id="R-E2",
        description="Entry tracklist matches <20% of its dated Olof setlist",
        severity="error",
        func=rule_e2,
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
    "R-T4": RuleDef(
        rule_id="R-T4",
        description="Taper disagrees with TUIT after alias mapping",
        severity="warn",
        func=rule_t4,
    ),
    "R-S1": RuleDef(
        rule_id="R-S1",
        description="Derived table older than its inputs",
        severity="error",
        func=rule_s1,
    ),
    "R-R1": RuleDef(
        rule_id="R-R1",
        description="Release string matches no official_releases.json entry or curator override",
        severity="warn",
        func=rule_r1,
    ),
}
