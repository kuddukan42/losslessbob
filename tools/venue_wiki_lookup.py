#!/usr/bin/env python3
"""Fill the ``venue_wiki_links`` cache: one English Wikipedia article per venue (TODO-346).

The dossier's venue card links the venue's article (e.g. The Spectrum, Philadelphia ->
``https://en.wikipedia.org/wiki/Spectrum_(arena)``) through
``backend.dossier_fields.venue_wiki_link``, which only ever reads this table. This tool
is the only writer besides curator overrides.

Work list: every ``venue_geocoded`` row with a coordinate, keyed identically
(``venue_norm``, ``city_norm``), so the dossier finds a link wherever it finds a pin.

Lookup, one Wikidata SPARQL call per venue (politely: sequential, ``--delay`` seconds
apart, the project's geocoder User-Agent): entity search on the venue name, keeping
items that have an English Wikipedia article. A candidate is judged by name (its
English label or an alias normalizes to the venue's key, with a leading "the"
ignored) and by distance from the gazetteer coordinate:

* ``high``   -- name matches and the item's P625 lies within 2 km of a venue-level
  coordinate (gazetteer confidence high/medium).
* ``medium`` -- name matches and the item lies within 25 km of whatever coordinate
  the gazetteer has (a city centre counts).
* ``low``    -- anything weaker, or two different items tie for the best grade.
  Cached for review, never rendered.

A venue with no candidate gets a row with ``wiki_url`` NULL so re-runs skip it
(``--refresh`` re-checks those and all other Wikidata rows). Curator overrides
(``source='override'``) are never touched by a lookup run:

    --set-override VENUE CITY URL   pin a link (URL must be a *.wikipedia.org/wiki/ page)
    --no-link VENUE CITY            pin "no link" for a venue Wikidata gets wrong

Usage::

    .venv/bin/python3 tools/venue_wiki_lookup.py --limit 20          # dry run, report only
    .venv/bin/python3 tools/venue_wiki_lookup.py --apply             # write data/losslessbob.db
    .venv/bin/python3 tools/venue_wiki_lookup.py --no-link "Spectrum" "Philadelphia" --apply

The lookups finish before anything is written; rows then go in as one transaction,
so an interrupted run leaves the table untouched.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from backend.dossier_fields import WIKI_URL_RE  # noqa: E402
from backend.geocoder import _USER_AGENT  # noqa: E402
from backend.venue_gazetteer import _haversine_km, _norm_city, _norm_venue  # noqa: E402

log = logging.getLogger("venue_wiki_lookup")

_SPARQL_URL = "https://query.wikidata.org/sparql"
_ENWIKI = "https://en.wikipedia.org/"
_TIMEOUT = 30
_MAX_429_RETRIES = 3
_HIGH_KM = 2.0
_MEDIUM_KM = 25.0
_VENUE_LEVEL = ("high", "medium")
_CITY_SOURCES = ("setlistfm_city", "city_geocode")
_GRADES = {"high": 2, "medium": 1}


@dataclass(frozen=True)
class Candidate:
    """One Wikidata item with an English article, as returned by the query."""

    qid: str
    title: str
    url: str
    names: frozenset[str]
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class Verdict:
    """The lookup outcome for one venue row."""

    wiki_title: str | None
    wiki_url: str | None
    confidence: str | None
    note: str


def _strip_the(key: str) -> str:
    return key[4:] if key.startswith("the ") else key


def _name_matches(venue_norm: str, names: frozenset[str]) -> bool:
    target = _strip_the(venue_norm)
    return any(_strip_the(n) == target for n in names if n)


def _sparql_query(venue: str) -> str:
    """Build the entity-search query for *venue*, escaped for a SPARQL string literal."""
    lit = venue.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "SELECT ?place ?coord ?article ?title ?label ?alt WHERE { "
        "SERVICE wikibase:mwapi { "
        'bd:serviceParam wikibase:api "EntitySearch" ; '
        'wikibase:endpoint "www.wikidata.org" ; '
        f'mwapi:search "{lit}" ; mwapi:language "en" . '
        "?place wikibase:apiOutputItem mwapi:item . } "
        f"?article schema:about ?place ; schema:isPartOf <{_ENWIKI}> ; schema:name ?title . "
        "OPTIONAL { ?place wdt:P625 ?coord . } "
        'OPTIONAL { ?place rdfs:label ?label . FILTER(lang(?label) = "en") } '
        'OPTIONAL { ?place skos:altLabel ?alt . FILTER(lang(?alt) = "en") } '
        "} LIMIT 200"
    )


def _parse_point(wkt: str | None) -> tuple[float | None, float | None]:
    """Parse a WKT ``Point(lon lat)`` literal into ``(lat, lon)``."""
    if not wkt or not wkt.startswith("Point("):
        return None, None
    try:
        lon, lat = wkt[6:].rstrip(")").split()
        return float(lat), float(lon)
    except ValueError:
        return None, None


def parse_bindings(bindings: list[dict]) -> list[Candidate]:
    """Fold SPARQL result rows (one per label/alias/coord combination) into candidates.

    Args:
        bindings: ``results.bindings`` from the Wikidata Query Service JSON.

    Returns:
        One :class:`Candidate` per item, in first-seen (search-rank) order.
    """
    acc: dict[str, dict] = {}
    for b in bindings:
        qid = b.get("place", {}).get("value", "").rsplit("/", 1)[-1]
        url = b.get("article", {}).get("value", "")
        if not qid or not url:
            continue
        c = acc.setdefault(qid, {"title": b.get("title", {}).get("value", ""), "url": url,
                                 "names": set(), "lat": None, "lon": None})
        for k in ("label", "alt", "title"):
            if k in b:
                c["names"].add(_norm_venue(b[k]["value"]))
        if c["lat"] is None and "coord" in b:
            c["lat"], c["lon"] = _parse_point(b["coord"]["value"])
    return [Candidate(qid, c["title"], c["url"], frozenset(c["names"]), c["lat"], c["lon"])
            for qid, c in acc.items()]


def judge(row: sqlite3.Row | dict, candidates: list[Candidate]) -> Verdict:
    """Grade *candidates* against one ``venue_geocoded`` row.

    Args:
        row: Needs ``venue_norm``, ``lat``, ``lon``, ``source``, ``confidence``.
        candidates: Parsed search results.

    Returns:
        The best :class:`Verdict`; ``wiki_url`` is ``None`` when no candidate
        names this venue at all.
    """
    venue_level = row["confidence"] in _VENUE_LEVEL and row["source"] not in _CITY_SOURCES
    graded: list[tuple[int, float, Candidate]] = []
    named: list[Candidate] = []
    for c in candidates:
        if not _name_matches(row["venue_norm"], c.names):
            continue
        named.append(c)
        if c.lat is None or row["lat"] is None:
            continue
        km = _haversine_km(row["lat"], row["lon"], c.lat, c.lon)
        if venue_level and km <= _HIGH_KM:
            graded.append((_GRADES["high"], km, c))
        elif km <= _MEDIUM_KM:
            graded.append((_GRADES["medium"], km, c))
    if graded:
        top = max(g for g, _, _ in graded)
        best = sorted((km, c.qid, c) for g, km, c in graded if g == top)
        if len({c.url for _, _, c in best}) > 1:
            km, qid, c = best[0]
            others = ", ".join(x.qid for _, _, x in best[1:])
            return Verdict(c.title, c.url, "low", f"{qid} ties with {others}")
        km, qid, c = best[0]
        grade = "high" if top == _GRADES["high"] else "medium"
        return Verdict(c.title, c.url, grade, f"{qid}, {km:.1f} km from gazetteer pin")
    if named:
        c = named[0]
        why = "no coordinate" if c.lat is None else "too far from gazetteer pin"
        return Verdict(c.title, c.url, "low", f"{c.qid} name match, {why}")
    return Verdict(None, None, None, f"no named match among {len(candidates)} result(s)")


def _fetch(venue: str) -> list[dict] | None:
    """Run the query for *venue*; ``None`` on a network/parse failure."""
    url = f"{_SPARQL_URL}?{urllib.parse.urlencode({'query': _sparql_query(venue), 'format': 'json'})}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               "Accept": "application/sparql-results+json"})
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _MAX_429_RETRIES:
                wait = int(e.headers.get("Retry-After") or 60)
                log.warning("Wikidata 429 on %r; sleeping %ds", venue, wait)
                time.sleep(wait)
                continue
            log.warning("Wikidata HTTP %s on %r", e.code, venue)
            return None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
            log.warning("Wikidata query failed for %r: %s", venue, e)
            return None
    return None


def _work_list(conn: sqlite3.Connection, refresh: bool, limit: int | None) -> list[sqlite3.Row]:
    sql = (
        "SELECT g.venue_norm, g.city_norm, g.venue, g.city, g.lat, g.lon, g.source, g.confidence "
        "FROM venue_geocoded g LEFT JOIN venue_wiki_links w "
        "ON w.venue_norm = g.venue_norm AND w.city_norm = g.city_norm "
        "WHERE g.lat IS NOT NULL AND TRIM(COALESCE(g.venue, '')) <> '' "
        "AND (w.venue_norm IS NULL OR (? AND w.source <> 'override')) "
        "ORDER BY g.venue_norm, g.city_norm"
    )
    rows = conn.execute(sql, (1 if refresh else 0,)).fetchall()
    return rows[:limit] if limit else rows


_UPSERT = (
    "INSERT INTO venue_wiki_links (venue_norm, city_norm, venue, city, wiki_title, wiki_url, "
    "source, confidence, note, looked_up_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
    "ON CONFLICT(venue_norm, city_norm) DO UPDATE SET venue=excluded.venue, city=excluded.city, "
    "wiki_title=excluded.wiki_title, wiki_url=excluded.wiki_url, source=excluded.source, "
    "confidence=excluded.confidence, note=excluded.note, looked_up_at=CURRENT_TIMESTAMP"
)


def _override_key(conn: sqlite3.Connection, venue: str, city: str,
                  country: str | None) -> tuple[str, str]:
    """Key an override like the gazetteer row it shadows, when there is one."""
    vnorm = _norm_venue(venue)
    for cnorm in dict.fromkeys([_norm_city(city, country), _norm_city(city)]):
        if conn.execute("SELECT 1 FROM venue_geocoded WHERE venue_norm=? AND city_norm=?",
                        (vnorm, cnorm)).fetchone():
            return vnorm, cnorm
    return vnorm, _norm_city(city, country)


def run_override(conn: sqlite3.Connection, venue: str, city: str, country: str | None,
                 url: str | None, apply: bool) -> int:
    """Write one curator override (``url=None`` pins "no link").

    Returns:
        Process exit code.
    """
    if url is not None and not WIKI_URL_RE.match(url):
        log.error("refusing %r: not a https://<lang>.wikipedia.org/wiki/ URL", url)
        return 2
    vnorm, cnorm = _override_key(conn, venue, city, country)
    title = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ") if url else None
    log.info("override %s | %s -> %s", vnorm, cnorm, url or "NO LINK")
    if apply:
        with conn:
            conn.execute(_UPSERT, (vnorm, cnorm, venue, city, title, url, "override", None,
                                   "curator override"))
    else:
        log.info("dry run: re-run with --apply to write")
    return 0


def run_lookup(conn: sqlite3.Connection, apply: bool, refresh: bool, limit: int | None,
               delay: float) -> int:
    """Look up every pending venue, report, and (with *apply*) write the results.

    Returns:
        Process exit code.
    """
    rows = _work_list(conn, refresh, limit)
    log.info("%d venue(s) to look up", len(rows))
    results: list[tuple[sqlite3.Row, Verdict]] = []
    failed = 0
    for i, row in enumerate(rows, 1):
        bindings = _fetch(row["venue"])
        time.sleep(delay)
        if bindings is None:
            failed += 1
            continue
        verdict = judge(row, parse_bindings(bindings))
        results.append((row, verdict))
        log.info("%5d/%d  %-7s %s | %s -> %s  (%s)", i, len(rows), verdict.confidence or "none",
                 row["venue"], row["city"], verdict.wiki_url or "-", verdict.note)
    tally = Counter(v.confidence or "none" for _, v in results)
    log.info("done: high=%d medium=%d low=%d none=%d failed=%d (failed rows are not cached)",
             tally["high"], tally["medium"], tally["low"], tally["none"], failed)
    if not apply:
        log.info("dry run: re-run with --apply to write")
        return 0
    with conn:
        conn.executemany(_UPSERT, [
            (r["venue_norm"], r["city_norm"], r["venue"], r["city"], v.wiki_title, v.wiki_url,
             "wikidata", v.confidence, v.note) for r, v in results])
    log.info("wrote %d row(s)", len(results))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(_project_root / "data" / "losslessbob.db"))
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-check venues already cached from Wikidata (overrides are kept)")
    ap.add_argument("--limit", type=int, help="look up at most N venues")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    ap.add_argument("--country", help="country for --set-override / --no-link keying")
    ap.add_argument("--set-override", nargs=3, metavar=("VENUE", "CITY", "URL"))
    ap.add_argument("--no-link", nargs=2, metavar=("VENUE", "CITY"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        for table in ("venue_geocoded", "venue_wiki_links"):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (table,)).fetchone() is None:
                log.error("%s has no %s table -- start the backend once to migrate it",
                          args.db, table)
                return 2
        if args.set_override:
            venue, city, url = args.set_override
            return run_override(conn, venue, city, args.country, url, args.apply)
        if args.no_link:
            venue, city = args.no_link
            return run_override(conn, venue, city, args.country, None, args.apply)
        return run_lookup(conn, args.apply, args.refresh, args.limit, args.delay)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
