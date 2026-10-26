"""TUIT <-> Olof venue cross-reference (TODO-338 part 2).

``venue_xref`` links a TUIT venue entity (its ``tuit_venues`` register row, or the
normalised venue + city of an unresolved ``tuit_shows`` row) to an Olof venue
(normalised ``olof_events`` venue + city). Rules, as decided by tj on 2026-10-25:

1. **Shared date first.** Every date where both corpora name exactly one venue
   contributes its pair directly (``method='date'``, ``n_dates`` counts them).
2. **Name rule second.** A TUIT venue with no shared date links by the geo25 rule
   (fuzzy name, same city or city centroids within 25 km), and only when exactly
   one Olof venue matches (``method='name'``). Ambiguous hits are skipped.
3. **Pairwise only — no transitive merge.** A union-find closure would chain
   Carnegie Chapter Hall into Carnegie Hall through one bad link.

``olof_events.venue`` stays the dossier's identity string; :func:`tuit_longer_venue`
supplies TUIT's longer string as a secondary header line on strict-superset dates.

The normalisers and loaders are shared with ``tools/tuit_olof_spine.py``, which
measured the keys (``docs/TUIT_OLOF_SPINE.md``).

Usage::

    .venv/bin/python3 -m backend.venue_xref            # dry run: counts only
    .venv/bin/python3 -m backend.venue_xref --apply    # rebuild the table
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

#: Radius (km) of the geo name rule; 25 km was the knee in the TODO-338 measurement.
GEO_KM = 25.0

FUZZY_RATIO = 0.85


_SESSION_RE = re.compile(r"\s*[·•]\s*(early|late|evening|afternoon|matinee|night|"
                         r"\d+(st|nd|rd|th)? show|show \d+)\s*$", re.I)


_NONWORD_RE = re.compile(r"[^\w]+")


_STOP = {"the", "of", "and", "at", "de", "la", "le", "der", "die", "das"}


_FOLD = {"theatre": "theater", "centre": "center", "st": "saint", "ctr": "center",
         "amphitheatre": "amphitheater", "mt": "mount", "univ": "university"}


_CITY_ALIAS = {"new york city": "new york", "nyc": "new york", "washington dc": "washington",
               "washington d c": "washington", "st paul": "saint paul",
               "st louis": "saint louis", "ft lauderdale": "fort lauderdale"}


def _ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_tokens(text: str | None) -> list[str]:
    """Return the folded, stop-word-free token list of a venue or city string.

    Args:
        text: Raw venue/city text.

    Returns:
        Tokens: accent-folded, casefolded, ``&`` -> ``and``, punctuation split,
        theatre/centre/st spellings folded, stop words dropped.
    """
    if not text:
        return []
    s = _ascii_fold(text).casefold().replace("&", " and ").replace("'", "")
    toks = [_FOLD.get(t, t) for t in _NONWORD_RE.sub(" ", s).split()]
    return [t for t in toks if t not in _STOP]


def norm_venue(venue: str | None) -> str:
    """Normalise a venue string (session suffix such as ' · Early' stripped)."""
    return " ".join(norm_tokens(_SESSION_RE.sub("", venue or "")))


def norm_city(city: str | None) -> str:
    """Normalise a city to its first comma segment, with a few alias folds."""
    base = " ".join(norm_tokens((city or "").split(",", 1)[0]))
    return _CITY_ALIAS.get(base, base)


def fuzzy_name(a: str, b: str) -> bool:
    """True when two normalised venue names plausibly denote one venue.

    Token containment either way (``lisner auditorium`` within ``lisner
    auditorium george washington university``), or a difflib ratio of at least
    :data:`FUZZY_RATIO` on the joined strings (``jacobshalle``/``jakobshalle``).
    Containment also tries the concatenated form, so ``salzburgarena`` meets
    ``salzburg arena``.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:
        return True
    ca, cb = a.replace(" ", ""), b.replace(" ", "")
    if len(ca) >= 6 and len(cb) >= 6 and (ca in cb or cb in ca):
        return True
    return SequenceMatcher(None, ca, cb).ratio() >= FUZZY_RATIO


def near_same(a: str, b: str) -> bool:
    """Strict spelling-variant test (ratio >= 0.9) used to judge evidence, not to link."""
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio() >= 0.9


def relation(tuit_norm: str, olof_norm: str) -> str:
    """Classify which side carries the longer (superset) venue string."""
    if tuit_norm == olof_norm:
        return "equal"
    ta, tb = set(tuit_norm.split()), set(olof_norm.split())
    if tb < ta:
        return "tuit_longer"
    if ta < tb:
        return "olof_longer"
    return "different"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def _has(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone() is not None


def load_tuit(conn: sqlite3.Connection) -> list[dict]:
    """Load ``tuit_shows`` rows with a resolved register venue id and city.

    The register join mirrors ``geocoder._get_tuit_venues_location_string``:
    same venue name, register city a prefix of the show's location; busiest
    register row wins. Unresolved rows keep ``reg_id=None`` and take the first
    comma segment of ``location`` as city.
    """
    reg: dict[str, list[dict]] = defaultdict(list)
    if _has(conn, "tuit_venues"):
        for r in conn.execute("SELECT id, venue, city, country, n_shows FROM tuit_venues"):
            reg[r[1]].append({"id": r[0], "city": r[2] or "", "country": r[3] or "",
                              "n": r[4] or 0})
    out = []
    for r in conn.execute("SELECT id, date_str, venue, COALESCE(location,''), "
                          "COALESCE(tour,''), circulating FROM tuit_shows ORDER BY date_str, id"):
        sid, d, venue, loc, tour, circ = r
        cands = [v for v in reg.get(venue, []) if v["city"] and loc.startswith(v["city"])]
        cands.sort(key=lambda v: (-v["n"], v["id"]))
        hit = cands[0] if cands else None
        city = hit["city"] if hit else loc.split(",", 1)[0]
        vn, cn = norm_venue(venue), norm_city(city)
        out.append({"id": sid, "date": d, "venue": venue, "location": loc, "tour": tour,
                    "circulating": circ, "reg_id": hit["id"] if hit else None,
                    "city": city, "vn": vn, "cn": cn,
                    "key": ("reg", hit["id"]) if hit else ("loc", vn, cn)})
    return out


def load_olof(conn: sqlite3.Connection) -> list[dict]:
    """Load every dated ``olof_events`` row (all event types)."""
    out = []
    for r in conn.execute("SELECT event_id, event_type, date_str, date_raw, venue, city, "
                          "region, country, source FROM olof_events WHERE date_str != '' "
                          "ORDER BY date_str, event_id"):
        eid, et, d, raw, venue, city, region, country, src = r
        vn, cn = norm_venue(venue), norm_city(city)
        out.append({"event_id": eid, "type": et, "date": d, "date_raw": raw, "venue": venue,
                    "city": city, "region": region, "country": country, "source": src,
                    "vn": vn, "cn": cn, "key": (vn, cn)})
    return out


def load_city_coords(conn: sqlite3.Connection) -> dict[str, tuple[float, float]]:
    """Build a city-norm -> (lat, lon) centroid table.

    Sources: setlist.fm ``city_lat``/``city_lon`` (preferred: one city-level
    point) then the median of resolved ``venue_geocoded`` pins per bare city.
    Keyed by bare city only, so same-named cities in different countries can
    collide — acceptable for a prototype because the name rule still applies.
    """
    pts: dict[str, list[tuple[float, float]]] = defaultdict(list)
    out: dict[str, tuple[float, float]] = {}
    if _has(conn, "setlistfm_shows"):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(setlistfm_shows)")}
        if "city_lat" in cols:
            for city, lat, lon in conn.execute(
                    "SELECT city, city_lat, city_lon FROM setlistfm_shows "
                    "WHERE city_lat IS NOT NULL"):
                out.setdefault(norm_city(city), (lat, lon))
    if _has(conn, "venue_geocoded"):
        for city, lat, lon in conn.execute(
                "SELECT city, lat, lon FROM venue_geocoded WHERE lat IS NOT NULL"):
            pts[norm_city(city)].append((lat, lon))
    for c, ps in pts.items():
        if c not in out:
            lats, lons = sorted(p[0] for p in ps), sorted(p[1] for p in ps)
            out[c] = (lats[len(lats) // 2], lons[len(lons) // 2])
    return out


def date_pairs(tuit: list[dict], olof: list[dict]) -> list[dict]:
    """Shared dates where each corpus names exactly one venue entity.

    Returns:
        One dict per date: ``date``, the TUIT row (first of its date) and the
        olof concert row.
    """
    tb: dict[str, list[dict]] = defaultdict(list)
    for t in tuit:
        tb[t["date"]].append(t)
    ob: dict[str, list[dict]] = defaultdict(list)
    for e in olof:
        if e["type"] == "concert":
            ob[e["date"]].append(e)
    out = []
    for d in sorted(set(tb) & set(ob)):
        if len({t["key"] for t in tb[d]}) == 1 and len({e["key"] for e in ob[d]}) == 1:
            out.append({"date": d, "t": tb[d][0], "o": ob[d][0]})
    return out


def geo_match(t: dict, o: dict, coords: dict[str, tuple[float, float]],
              km: float = GEO_KM) -> bool:
    """The geo name rule: fuzzy venue name, and same city or centroids within *km*.

    Args:
        t: A TUIT row from :func:`load_tuit`.
        o: An Olof row from :func:`load_olof`.
        coords: City-norm centroids from :func:`load_city_coords`.
        km: Radius for the city test.

    Returns:
        True when the two rows plausibly name one venue.
    """
    if not fuzzy_name(t["vn"], o["vn"]):
        return False
    if t["cn"] == o["cn"]:
        return True
    a, b = coords.get(t["cn"]), coords.get(o["cn"])
    return bool(a and b and haversine_km(a, b) <= km)


@dataclass
class XrefRow:
    """One ``venue_xref`` link between a TUIT venue entity and an Olof venue."""

    tuit_venue: str
    tuit_city: str
    tuit_venue_id: int | None
    tuit_vn: str
    tuit_cn: str
    olof_venue: str
    olof_city: str
    olof_vn: str
    olof_cn: str
    method: str
    n_dates: int
    relation: str


def build(conn: sqlite3.Connection) -> tuple[list[XrefRow], dict[str, int]]:
    """Compute every venue_xref link from the live TUIT and Olof tables.

    Args:
        conn: Open connection to the app DB.

    Returns:
        ``(rows, stats)`` — the links, and counts ``date_links``, ``name_links``,
        ``name_ambiguous`` (TUIT venues with 2+ geo25 candidates, left unlinked),
        ``unlinked`` and ``tuit_venues``.
    """
    if not (_has(conn, "tuit_shows") and _has(conn, "olof_events")):
        return [], {"date_links": 0, "name_links": 0, "name_ambiguous": 0,
                    "unlinked": 0, "tuit_venues": 0}
    tuit, olof = load_tuit(conn), load_olof(conn)
    coords = load_city_coords(conn)

    by_pair: dict[tuple, dict] = {}
    n_dates: Counter = Counter()
    # Keyed on the normalised (venue, city) of both sides -- the table's UNIQUE key --
    # so register rows that differ only by city spelling pool their dates.
    for p in date_pairs(tuit, olof):
        k = ((p["t"]["vn"], p["t"]["cn"]), p["o"]["key"])
        by_pair.setdefault(k, {"t": p["t"], "o": p["o"]})
        n_dates[k] += 1
    rows = [_row(v["t"], v["o"], "date", n_dates[k]) for k, v in by_pair.items()]
    dated_tuit = {k[0] for k in by_pair}

    olof_ents: dict[tuple, dict] = {}
    for e in olof:
        if e["type"] == "concert" and e["vn"]:
            olof_ents.setdefault(e["key"], e)
    olof_by_city: dict[str, list[dict]] = defaultdict(list)
    for o in olof_ents.values():
        olof_by_city[o["cn"]].append(o)
    city_pts = [(c, coords[c]) for c in olof_by_city if c in coords]

    tuit_ents: dict[tuple, dict] = {}
    for t in tuit:
        tuit_ents.setdefault((t["vn"], t["cn"]), t)
    name_links = ambiguous = unlinked = 0
    for key, t in tuit_ents.items():
        if key in dated_tuit:
            continue
        cands = list(olof_by_city.get(t["cn"], []))
        a = coords.get(t["cn"])
        if a:
            cands += [o for c, b in city_pts if c != t["cn"] and haversine_km(a, b) <= GEO_KM
                      for o in olof_by_city[c]]
        hits = {o["key"]: o for o in cands if geo_match(t, o, coords)}
        if len(hits) == 1:
            rows.append(_row(t, next(iter(hits.values())), "name", 0))
            name_links += 1
        elif hits:
            ambiguous += 1
        else:
            unlinked += 1
    stats = {"date_links": len(by_pair), "name_links": name_links,
             "name_ambiguous": ambiguous, "unlinked": unlinked, "tuit_venues": len(tuit_ents)}
    return rows, stats


def _row(t: dict, o: dict, method: str, n: int) -> XrefRow:
    return XrefRow(
        tuit_venue=_SESSION_RE.sub("", t["venue"]), tuit_city=t["city"],
        tuit_venue_id=t["reg_id"], tuit_vn=t["vn"], tuit_cn=t["cn"],
        olof_venue=o["venue"] or "", olof_city=o["city"] or "", olof_vn=o["vn"],
        olof_cn=o["cn"], method=method, n_dates=n, relation=relation(t["vn"], o["vn"]))


def refresh(conn: sqlite3.Connection) -> dict[str, int]:
    """Rebuild ``venue_xref`` from scratch in one transaction.

    Args:
        conn: Open, writable connection to the app DB (schema already applied).

    Returns:
        The :func:`build` stats plus ``written``.
    """
    rows, stats = build(conn)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM venue_xref")
        conn.executemany(
            "INSERT OR IGNORE INTO venue_xref (tuit_venue, tuit_city, tuit_venue_id, tuit_vn,"
            " tuit_cn, olof_venue, olof_city, olof_vn, olof_cn, method, n_dates, relation,"
            " built_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r.tuit_venue, r.tuit_city, r.tuit_venue_id, r.tuit_vn, r.tuit_cn, r.olof_venue,
              r.olof_city, r.olof_vn, r.olof_cn, r.method, r.n_dates, r.relation, now)
             for r in rows])
    stats["written"] = conn.execute("SELECT COUNT(*) FROM venue_xref").fetchone()[0]
    return stats


def tuit_longer_venue(conn: sqlite3.Connection, date_iso: str,
                      olof_venue: str | None) -> str | None:
    """TUIT's venue string for *date_iso* when it strictly extends Olof's.

    Used for the dossier's secondary venue line: Olof's string stays the header,
    TUIT's longer form ("Lisner Auditorium, George Washington University") is
    shown beneath it only when its tokens are a strict superset of Olof's.

    Args:
        conn: Open connection to the app DB.
        date_iso: Show date ``YYYY-MM-DD``.
        olof_venue: The dossier's Olof venue string.

    Returns:
        TUIT's venue text (session suffix stripped), or ``None`` when TUIT has no
        single venue on the date or its string isn't a strict superset.
    """
    if not olof_venue or not _has(conn, "tuit_shows"):
        return None
    venues = {_SESSION_RE.sub("", r[0]).strip() for r in conn.execute(
        "SELECT venue FROM tuit_shows WHERE date_str = ?", (date_iso,))}
    if len(venues) != 1:
        return None
    tv = next(iter(venues))
    return tv if relation(norm_venue(tv), norm_venue(olof_venue)) == "tuit_longer" else None


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    from backend import db

    ap = argparse.ArgumentParser(description="Rebuild the TUIT<->Olof venue_xref table.")
    ap.add_argument("--apply", action="store_true", help="write the table (default: dry run)")
    args = ap.parse_args(argv)
    db.init_db()
    conn = db.get_connection()
    if args.apply:
        stats = refresh(conn)
    else:
        _rows, stats = build(conn)
    logger.info("venue_xref %s: %s", "rebuilt" if args.apply else "dry run", stats)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
