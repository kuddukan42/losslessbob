"""Cross TUIT's show spine against olof_events (TODO-338 parts 1-2). Read-only.

Two reports, one run:

Part 1 — DATE RESIDUE. Every ``tuit_shows`` row whose date has no olof concert,
and every olof concert date with no ``tuit_shows`` row, gets one class:

``olof_nonconcert``      olof has the date, typed session/broadcast/other.
``date_offset``          the other corpus has the SAME venue within +-10 days and
                         nothing on this date — one side's date is probably off.
``multi_night``          same venue within +-10 days, and both corpora have that
                         other night — this corpus lacks one night of a run.
``circa``                a 1950s/60s date one side pins to a day the other can't
                         (TUIT 1st-of-month, olof 'circa'/'?' date_raw).
``non_show``             a studio/TV/radio/home/rehearsal venue olof types concert.
``after_crawl``          olof date later than the last TUIT crawl.
``corroborated``         setlist.fm and/or bobdylan.com list the date — a real
                         show the other calendar lacks.
``unverified``           nothing else knows the date.

Part 2 — VENUE JOIN KEYS. Ground truth is the shared dates where both corpora
name exactly one venue (TUIT Early/Late rows at one venue count as one). Each
candidate key is scored against those pairs:

``exact``      normalised venue + normalised city equal.
``fuzzy``      same city; token containment either way or difflib ratio >= 0.85.
``geo<N>``     the fuzzy name rule, city replaced by city centroids within N km
               (centroids from ``venue_geocoded`` + setlist.fm city coords).
``crosswalk``  TUIT register venue -> olof venue learned from shared dates,
               scored leave-one-date-out (no date-free evidence).

Match rate = date pairs the key links. Suspected false match = the key links a
TUIT venue to an olof venue that only ever co-occurs (by date) with OTHER TUIT
venues. Residue = TUIT venues the key links to nothing.

Usage:
    .venv/bin/python3 tools/tuit_olof_spine.py [--db PATH] [--out docs/TUIT_OLOF_SPINE.md]

``--out`` rewrites only the block between the GENERATED markers of that file
(creating it if missing), so hand-written prose around it survives a re-run.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import random
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger("tuit_olof_spine")

_project_root = Path(__file__).resolve().parent.parent
_app_root = Path(os.environ.get("LOSSLESSBOB_APP_ROOT", _project_root))
DEFAULT_DB = _app_root / "data" / "losslessbob.db"
DEFAULT_OUT = _project_root / "docs" / "TUIT_OLOF_SPINE.md"

GEN_START = "<!-- GENERATED:tuit_olof_spine START -->"
GEN_END = "<!-- GENERATED:tuit_olof_spine END -->"

NEAR_DAYS = 10
FUZZY_RATIO = 0.85
GEO_KM = (10.0, 25.0, 50.0)
HYBRID_BASE = "geo25"
_SAMPLES = 15
_LABEL_SAMPLE = 40  # seeded sample of links the hybrid base adds over exact

# Hand triage of 2026-10-14 (TODO-338 UPDATE) — attached as a note, never as the class.
KNOWN_NOTES = {
    "1976-05-10": "olof files as non-concert",
    "1986-02-17": "olof files as non-concert (Perth)",
    "1986-02-18": "olof files as non-concert (Perth)",
    "1997-05-21": "TV/awards appearance",
    "2012-01-12": "TV/awards appearance",
    "2014-11-25": "DSN36360 header has no number line — olof parser gap",
    "2019-11-12": "DSN40330 has no bookmark — olof parser gap",
    "1981-11-16": "real show olof's pages lack or don't parse",
    "1988-08-18": "real show olof's pages lack or don't parse",
    "1996-04-18": "real show olof's pages lack or don't parse",
    "2004-10-18": "real show olof's pages lack or don't parse",
}

_SESSION_RE = re.compile(r"\s*[·•]\s*(early|late|evening|afternoon|matinee|night|"
                         r"\d+(st|nd|rd|th)? show|show \d+)\s*$", re.I)
_NONWORD_RE = re.compile(r"[^\w]+")
_STOP = {"the", "of", "and", "at", "de", "la", "le", "der", "die", "das"}
_FOLD = {"theatre": "theater", "centre": "center", "st": "saint", "ctr": "center",
         "amphitheatre": "amphitheater", "mt": "mount", "univ": "university"}
_CITY_ALIAS = {"new york city": "new york", "nyc": "new york", "washington dc": "washington",
               "washington d c": "washington", "st paul": "saint paul",
               "st louis": "saint louis", "ft lauderdale": "fort lauderdale"}
_NON_SHOW_RE = re.compile(
    r"\b(studio|studios|tv|television|radio(?! city)|wfmt|wbai|cbc|bbc|nbc|cbs|abc|pbs|"
    r"rehearsal|home|apartment|house of|hotel room|recording|session|office|"
    r"unidentified venue|private|party|backstage|club 47 sound|airport|arrival area|grave|"
    r"gas station|motel|warehouse|parlor|reservation|stage \d+|east room)\b", re.I)
_CIRCA_RE = re.compile(r"circa|\?|early|late|mid|spring|summer|autumn|fall|winter|"
                       r"unknown|or ", re.I)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

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


def load_other_dates(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    """Return (setlist.fm dates, bobdylan.com dates); empty sets if a table is absent."""
    sfm = ({r[0] for r in conn.execute("SELECT DISTINCT date_str FROM setlistfm_shows")}
           if _has(conn, "setlistfm_shows") else set())
    bd = ({r[0] for r in conn.execute("SELECT DISTINCT date_str FROM bobdylan_shows")}
          if _has(conn, "bobdylan_shows") else set())
    return sfm, bd


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


# ---------------------------------------------------------------------------
# Part 1 — date residue
# ---------------------------------------------------------------------------

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def _near(dt: str, vn: str, cn: str, by_city: dict[str, list[tuple[str, str, str]]],
          exclude: set[str]) -> tuple[str, str] | None:
    """Closest (date, venue) in *by_city* within NEAR_DAYS whose name fuzzy-matches."""
    best = None
    for d2, vn2, raw in by_city.get(cn, []):
        if d2 in exclude or not fuzzy_name(vn, vn2):
            continue
        try:
            gap = abs(_days(dt, d2))
        except ValueError:
            continue
        if 0 < gap <= NEAR_DAYS and (best is None or gap < best[0]):
            best = (gap, d2, raw)
    return (best[1], best[2]) if best else None


def classify_tuit_only(tuit: list[dict], olof: list[dict], sfm: set[str],
                       bd: set[str]) -> list[dict]:
    """Classify each TUIT row whose date has no olof concert (see module doc)."""
    concert_dates = {e["date"] for e in olof if e["type"] == "concert"}
    other_by_date: dict[str, list[dict]] = defaultdict(list)
    for e in olof:
        if e["type"] != "concert":
            other_by_date[e["date"]].append(e)
    olof_by_city: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for e in olof:
        if e["type"] == "concert":
            olof_by_city[e["cn"]].append((e["date"], e["vn"], e["venue"]))
    circa_months = {e["date"][:7] for e in olof if _CIRCA_RE.search(e["date_raw"] or "")}
    tuit_dates = {t["date"] for t in tuit}
    rows = []
    for t in tuit:
        d = t["date"]
        if d in concert_dates:
            continue
        near = _near(d, t["vn"], t["cn"], olof_by_city, set())
        corro = "+".join(n for n, s in (("setlist.fm", sfm), ("bobdylan.com", bd)) if d in s)
        if other_by_date.get(d):
            e = other_by_date[d][0]
            cls, ev = "olof_nonconcert", f"olof {e['type']}: {e['venue']}, {e['city']}"
        elif near and near[0] in tuit_dates:
            cls, ev = "multi_night", (f"olof has {near[0]} at {near[1]} too — olof lacks "
                                      "this night of the run")
        elif near:
            cls, ev = "date_offset", (f"olof {near[0]} at {near[1]} ({_days(d, near[0]):+d}d), "
                                      "TUIT has no row that day — one side's date is off")
        elif d[:4] <= "1966" and (d.endswith("-01") or d[:7] in circa_months):
            cls, ev = "circa", "TUIT pins a 1960s day olof can't"
        elif _NON_SHOW_RE.search(t["venue"]) or re.search(r"award|grammy|tv", t["venue"], re.I):
            cls, ev = "non_show", "TV/awards/studio venue"
        elif corro:
            cls, ev = "corroborated", f"{corro} lists the date — olof gap"
        else:
            cls, ev = "unverified", ""
        rows.append({"date": d, "venue": t["venue"], "location": t["location"],
                     "circulating": t["circulating"], "class": cls, "evidence": ev,
                     "also": corro, "note": KNOWN_NOTES.get(d, "")})
    return rows


def classify_olof_only(tuit: list[dict], olof: list[dict], sfm: set[str], bd: set[str],
                       crawl_date: str | None) -> list[dict]:
    """Classify each olof concert date with no ``tuit_shows`` row (see module doc)."""
    tuit_dates = {t["date"] for t in tuit}
    olof_concert_dates = {e["date"] for e in olof if e["type"] == "concert"}
    tuit_by_city: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for t in tuit:
        tuit_by_city[t["cn"]].append((t["date"], t["vn"], t["venue"]))
    rows, seen = [], set()
    for e in olof:
        d = e["date"]
        if e["type"] != "concert" or d in tuit_dates or d in seen:
            continue
        seen.add(d)
        near = _near(d, e["vn"], e["cn"], tuit_by_city, set())
        in_sfm, in_bd = d in sfm, d in bd
        corro = "+".join(n for n, s in (("setlist.fm", in_sfm), ("bobdylan.com", in_bd)) if s)
        if crawl_date and d > crawl_date:
            cls, ev = "after_crawl", f"after TUIT crawl {crawl_date}"
        elif near and near[0] in olof_concert_dates:
            cls, ev = "multi_night", (f"TUIT has {near[0]} at {near[1]} too — TUIT lacks "
                                      "this night of the run")
        elif near:
            cls, ev = "date_offset", (f"TUIT {near[0]} at {near[1]} ({_days(d, near[0]):+d}d), "
                                      "olof has no concert that day — one side's date is off")
        elif _NON_SHOW_RE.search(f"{e['venue']}"):
            cls, ev = "non_show", "studio/TV/radio/home/rehearsal venue"
        elif _CIRCA_RE.search(e["date_raw"] or "") and not re.fullmatch(
                r"\d{1,2} \w+ \d{4}", (e["date_raw"] or "").strip()):
            cls, ev = "circa", f"olof date_raw '{e['date_raw']}'"
        elif in_bd:
            cls, ev = "corroborated", f"{corro} — TUIT calendar gap"
        elif in_sfm:
            cls, ev = "corroborated_sfm", "setlist.fm only — weaker"
        else:
            cls, ev = "unverified", "no other source has the date"
        rows.append({"date": d, "venue": e["venue"], "city": e["city"],
                     "country": e["country"], "event_id": e["event_id"], "class": cls,
                     "evidence": ev, "also": corro})
    return rows


# ---------------------------------------------------------------------------
# Part 2 — venue join keys
# ---------------------------------------------------------------------------

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


def _key_preds(coords: dict[str, tuple[float, float]]) -> dict[str, object]:
    def exact(t: dict, o: dict) -> bool:
        return t["vn"] == o["vn"] and t["cn"] == o["cn"]

    def fuzzy(t: dict, o: dict) -> bool:
        return t["cn"] == o["cn"] and fuzzy_name(t["vn"], o["vn"])

    def geo(km: float):
        def pred(t: dict, o: dict) -> bool:
            if not fuzzy_name(t["vn"], o["vn"]):
                return False
            if t["cn"] == o["cn"]:
                return True
            a, b = coords.get(t["cn"]), coords.get(o["cn"])
            return bool(a and b and haversine_km(a, b) <= km)
        return pred

    preds: dict[str, object] = {"exact": exact, "fuzzy": fuzzy}
    for km in GEO_KM:
        preds[f"geo{int(km)}"] = geo(km)
    return preds


def evaluate_keys(tuit: list[dict], olof: list[dict],
                  coords: dict[str, tuple[float, float]]) -> dict:
    """Score every candidate key against the shared-date ground truth.

    Returns:
        ``{"n_pairs", "relation": Counter, "keys": {name: stats}}`` where stats
        carry ``matched``, ``rate``, ``false`` (count), ``false_samples``,
        ``miss_samples``, ``tuit_venues``, ``linked_venues``, ``residue`` and
        ``residue_samples``.
    """
    pairs = date_pairs(tuit, olof)
    tuit_ents: dict[tuple, dict] = {}
    for t in tuit:
        tuit_ents.setdefault(t["key"], t)
    olof_ents: dict[tuple, dict] = {}
    for e in olof:
        if e["type"] == "concert" and e["vn"]:
            olof_ents.setdefault(e["key"], e)
    # Evidence is keyed on the normalised (venue, city) of both sides, so TUIT
    # register rows that only differ by city spelling pool their dates.
    evid_t: dict[tuple, set] = defaultdict(set)   # (tuit vn, cn) -> olof vns co-dated
    evid_o: dict[tuple, set] = defaultdict(set)   # (olof vn, cn) -> tuit vns co-dated
    for p in pairs:
        evid_t[(p["t"]["vn"], p["t"]["cn"])].add(p["o"]["vn"])
        evid_o[p["o"]["key"]].add(p["t"]["vn"])
    rel = Counter(relation(p["t"]["vn"], p["o"]["vn"]) for p in pairs)

    # Candidate olof venues per TUIT venue: same city or within the widest geo radius.
    max_km = max(GEO_KM)
    olof_by_city: dict[str, list[dict]] = defaultdict(list)
    for o in olof_ents.values():
        olof_by_city[o["cn"]].append(o)
    city_pts = [(c, coords[c]) for c in olof_by_city if c in coords]

    def candidates(t: dict) -> list[dict]:
        cands = list(olof_by_city.get(t["cn"], []))
        a = coords.get(t["cn"])
        if a:
            for c, b in city_pts:
                if c != t["cn"] and haversine_km(a, b) <= max_km:
                    cands.extend(olof_by_city[c])
        return cands

    cand_map = {k: candidates(t) for k, t in tuit_ents.items()}

    def contradicted(t: dict, o: dict) -> bool:
        # Both sides have dated evidence and it points elsewhere on both sides:
        # t's dates name other olof venues, o's dates name other TUIT venues.
        et, eo = evid_t.get((t["vn"], t["cn"])), evid_o.get(o["key"])
        if not et or not eo:
            return False
        return (not any(near_same(x, o["vn"]) for x in et)
                and not any(near_same(x, t["vn"]) for x in eo))
    results: dict[str, dict] = {}
    preds = _key_preds(coords)
    exact, base = preds["exact"], preds[HYBRID_BASE]
    added = sorted({(t["venue"], t["city"], o["venue"], o["city"])
                    for k, t in tuit_ents.items() for o in cand_map[k]
                    if base(t, o) and not exact(t, o)})
    added_sample = random.Random(338).sample(added, min(_LABEL_SAMPLE, len(added)))
    for name, pred in preds.items():
        matched = [p for p in pairs if pred(p["t"], p["o"])]
        missed = [p for p in pairs if not pred(p["t"], p["o"])]
        false, linked = [], 0
        for k, t in tuit_ents.items():
            hits = [o for o in cand_map[k] if pred(t, o)]
            if hits:
                linked += 1
            false.extend((t, o) for o in hits if contradicted(t, o))
        residue = [t for k, t in tuit_ents.items()
                   if not any(pred(t, o) for o in cand_map[k])]
        results[name] = _stats(pairs, matched, missed, false, len(tuit_ents), linked, residue)

    # crosswalk: register venue -> majority olof venue, leave-one-date-out.
    by_t: dict[tuple, Counter] = defaultdict(Counter)
    for p in pairs:
        by_t[p["t"]["key"]][p["o"]["key"]] += 1
    matched, missed, false = [], [], []
    cw_false_dates: dict[str, tuple] = {}
    for p in pairs:
        c = by_t[p["t"]["key"]].copy()
        c[p["o"]["key"]] -= 1
        c += Counter()
        if not c:
            missed.append(p)
            continue
        pred_o = c.most_common(1)[0][0]
        if pred_o == p["o"]["key"] or (pred_o[1] == p["o"]["cn"]
                                       and near_same(pred_o[0], p["o"]["vn"])):
            matched.append(p)
        else:
            missed.append(p)
            cw_false_dates[p["date"]] = pred_o
            false.append((p["t"], olof_ents.get(pred_o, {"venue": pred_o[0], "city": pred_o[1]})))
    no_evid = [t for k, t in tuit_ents.items() if k not in by_t]
    results["crosswalk"] = _stats(pairs, matched, missed, false, len(tuit_ents),
                                  len(tuit_ents) - len(no_evid), no_evid)

    # hybrid: the geo25 name rule, falling back to the leave-one-out crosswalk.
    geo = base
    cw_ok = {p["date"] for p in matched}
    h_matched = [p for p in pairs if geo(p["t"], p["o"]) or p["date"] in cw_ok]
    h_missed = [p for p in pairs if not (geo(p["t"], p["o"]) or p["date"] in cw_ok)]
    h_resid = [t for k, t in tuit_ents.items()
               if k not in by_t and not any(geo(t, o) for o in cand_map[k])]
    h_false = [(t, o) for k, t in tuit_ents.items() for o in cand_map[k]
               if geo(t, o) and contradicted(t, o)]
    h_false += [(p["t"], olof_ents.get(cw_false_dates[p["date"]], p["o"])) for p in pairs
                if p["date"] in cw_false_dates and not geo(p["t"], p["o"])]
    results[f"{HYBRID_BASE}+crosswalk"] = _stats(
        pairs, h_matched, h_missed, h_false, len(tuit_ents),
        len(tuit_ents) - len(h_resid), h_resid)
    return {"n_pairs": len(pairs), "relation": rel, "keys": results,
            "n_added": len(added), "added_sample": sorted(added_sample),
            "n_tuit_venues": len(tuit_ents), "n_olof_venues": len(olof_ents)}


def _stats(pairs, matched, missed, false, n_ents, linked, residue) -> dict:
    n = len(pairs) or 1
    return {
        "matched": len(matched), "rate": len(matched) / n, "false": len(false),
        "false_samples": [(t["venue"], t.get("city", ""), o["venue"], o.get("city", ""))
                          for t, o in false[:_SAMPLES]],
        "miss_samples": [(p["date"], p["t"]["venue"], p["t"]["city"], p["o"]["venue"],
                          p["o"]["city"]) for p in missed[:: max(1, len(missed) // _SAMPLES)]
                         ][:_SAMPLES],
        "tuit_venues": n_ents, "linked_venues": linked, "residue": len(residue),
        "residue_samples": [(t["venue"], t["city"]) for t in residue[:_SAMPLES]],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def compute(conn: sqlite3.Connection) -> dict:
    """Run both parts against an open connection (read-only usage)."""
    tuit, olof = load_tuit(conn), load_olof(conn)
    sfm, bd = load_other_dates(conn)
    crawl = conn.execute("SELECT MAX(substr(last_seen_at,1,10)) FROM tuit_shows").fetchone()[0]
    return {
        "n_tuit_rows": len(tuit), "n_tuit_dates": len({t["date"] for t in tuit}),
        "n_tuit_unresolved": sum(1 for t in tuit if t["reg_id"] is None),
        "crawl_date": crawl,
        "tuit_only": classify_tuit_only(tuit, olof, sfm, bd),
        "olof_only": classify_olof_only(tuit, olof, sfm, bd, crawl),
        "keys": evaluate_keys(tuit, olof, load_city_coords(conn)),
    }


def _cell(v) -> str:
    return str(v if v is not None else "").replace("|", "/").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def render_markdown(res: dict, generated: str | None = None) -> str:
    """Render the generated block (counts, per-row tables, key scores)."""
    gen = generated or datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [GEN_START, f"_Generated {gen} by `tools/tuit_olof_spine.py` — re-run to refresh._", ""]
    to, oo, k = res["tuit_only"], res["olof_only"], res["keys"]
    L += [f"TUIT: {res['n_tuit_rows']:,} show rows on {res['n_tuit_dates']:,} dates "
          f"({res['n_tuit_unresolved']} rows don't resolve to a register venue); "
          f"last crawl {res['crawl_date']}.", ""]

    L += ["### Part 1a — TUIT rows with no olof concert", ""]
    L += _table(["class", "rows"], [[c, n] for c, n in Counter(r["class"] for r in to)
                                    .most_common()]) + [""]
    L += _table(["date", "TUIT venue", "location", "circ", "class", "evidence", "2026-10-14 note"],
                [[r["date"], r["venue"], r["location"], r["circulating"], r["class"],
                  r["evidence"], r["note"]] for r in to]) + [""]

    L += ["### Part 1b — olof concert dates with no TUIT row", ""]
    L += _table(["class", "dates"], [[c, n] for c, n in Counter(r["class"] for r in oo)
                                     .most_common()]) + [""]
    L += _table(["date", "olof venue", "city", "country", "DSN", "class", "evidence"],
                [[r["date"], r["venue"], r["city"], r["country"], r["event_id"], r["class"],
                  r["evidence"]] for r in oo]) + [""]

    L += ["### Part 2 — venue join keys", "",
          f"Ground truth: {k['n_pairs']:,} shared dates where each side names one venue. "
          f"{k['n_tuit_venues']:,} TUIT venue entities, {k['n_olof_venues']:,} olof venue "
          "strings (venue+city).", ""]
    L += _table(["key", "date pairs linked", "rate", "conflicting-evidence links",
                 "TUIT venues linked", "TUIT residue"],
                [[n, s["matched"], f"{s['rate']:.1%}", s["false"],
                  f"{s['linked_venues']}/{s['tuit_venues']}", s["residue"]]
                 for n, s in k["keys"].items()]) + [""]
    L += [f"#### Links `{HYBRID_BASE}` adds over `exact` — seeded sample of "
          f"{len(k['added_sample'])} / {k['n_added']:,} (hand-labelled in the prose above)", ""]
    L += _table(["#", "TUIT venue", "TUIT city", "olof venue", "olof city"],
                [[i + 1, *x] for i, x in enumerate(k["added_sample"])]) + [""]
    rel = k["relation"]
    L += ["Which side is longer on the shared dates:", ""]
    L += _table(["relation", "pairs"], [[r, n] for r, n in rel.most_common()]) + [""]
    for n, s in k["keys"].items():
        L += [f"#### `{n}` samples", "", "Suspected false links:", ""]
        L += _table(["TUIT venue", "TUIT city", "olof venue", "olof city"],
                    [list(x) for x in s["false_samples"]]) or ["(none)"]
        L += ["", "Missed date pairs (spread sample):", ""]
        L += _table(["date", "TUIT venue", "TUIT city", "olof venue", "olof city"],
                    [list(x) for x in s["miss_samples"]])
        L += ["", "Unlinked TUIT venues:", ""]
        L += _table(["TUIT venue", "city"], [list(x) for x in s["residue_samples"]]) + [""]
    L.append(GEN_END)
    return "\n".join(L) + "\n"


def write_block(path: Path, block: str) -> None:
    """Replace the generated block in *path* (append it if the markers are absent)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if GEN_START in text and GEN_END in text:
        head, rest = text.split(GEN_START, 1)
        tail = rest.split(GEN_END, 1)[1]
        text = head + block.rstrip("\n") + tail
    else:
        text = (text.rstrip("\n") + "\n\n" if text else "") + block
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (read-only)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        res = compute(conn)
    finally:
        conn.close()
    write_block(args.out, render_markdown(res))
    for n, s in res["keys"]["keys"].items():
        logger.info("%-10s linked %5d/%d (%.1f%%)  false %4d  residue %4d", n, s["matched"],
                    res["keys"]["n_pairs"], 100 * s["rate"], s["false"], s["residue"])
    logger.info("tuit-only rows %d, olof-only dates %d -> %s", len(res["tuit_only"]),
                len(res["olof_only"]), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
