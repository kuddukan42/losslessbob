"""Reconcile TUIT recording metadata against ``entries`` (TODO-332, TODO-339 parts 1-2).

Report mode (the default) is read-only: it opens the DB with ``mode=ro`` and
compares every ``tuit_recordings`` row that claims an LB number against that
entry, field by field:

``date``         agree / conflict / circa (LB has 'xx', TUIT exact) / blank sides.
                 Every circa row and every full-date conflict is classified and
                 given a recommended action.
``source_type``  TUIT's AUD/SBD/FM/MTX/ALD/TV mapped onto our vocabulary; every
                 conflict is classified from the lineage text on both sides.
``venue``        TUIT's structured venue vs our free-text ``entries.location``.
``lineage``      TUIT ``lineage`` vs ``entries.source_chain`` (presence only).
``setlist``      TUIT ``setlist_json`` vs ``entries.setlist`` (presence only).

``--fill`` is the one write path, and it only stages *additive* values: a field
where our side is empty and TUIT is unambiguous, on an LB whose full date agrees
with TUIT (a date-disagreeing LB may be a TUIT misattribution, so nothing from it
is trusted). Values go to the USER-tier ``corrections`` table (entity_kind
``entry``, ``decided_by='tuit_reconcile'``) — never into ``entries``, whose rows
the scraper rewrites with INSERT OR REPLACE and whose ``metadata_source`` column
the public master export treats as private-import. Nothing reads entry
corrections yet, so a fill is a staged, attributable, reversible record that a
future consumer can render. A field that already has a correction is skipped.

``--fill`` and ``--revert`` are dry runs unless ``--apply`` is given. ``--apply``
backs the DB up to ``<db dir>/backups/`` first (``PRAGMA quick_check`` on the
copy) and appends one JSON line per written/deleted row to ``--audit``.

Usage:
    .venv/bin/python3 tools/tuit_reconcile.py [--db PATH] [--out FILE.md] [--json FILE]
    .venv/bin/python3 tools/tuit_reconcile.py --fill [--fields source_type,venue] [--apply]
    .venv/bin/python3 tools/tuit_reconcile.py --revert [--apply]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logger = logging.getLogger("tuit_reconcile")

DEFAULT_DB = _project_root / "data" / "losslessbob.db"
DEFAULT_OUT = _project_root / "docs" / "tuit_reconcile.md"
DEFAULT_AUDIT = _project_root / "data" / "logs" / "tuit_reconcile_audit.jsonl"

DECIDED_BY = "tuit_reconcile"
FILL_FIELDS = ("source_type", "source_chain", "setlist", "venue")
_LB_SELF_REF_RE = re.compile(r"LB-?\s*\d+", re.IGNORECASE)
_SHOWN = 40  # sample rows per bulk class in the markdown (full set goes to --json)

# TUIT pill -> entries.source_type vocabulary. TV is a broadcast like FM.
TUIT_SRC_MAP = {
    "AUD": "Audience", "SBD": "Soundboard", "FM": "FM/Pre-FM", "TV": "FM/Pre-FM",
    "MTX": "Mixed", "ALD": "ALD",
}

# Adjudicated by hand 2026-10-14 (TODO-339 UPDATE notes) — these override the
# heuristic so the report carries the decision already made.
KNOWN_DATE = {
    13920: ("tuit_lb_wrong", "Fix TUIT's lb_number (tracker side); LB date stands — "
            "setlist matches LB date 13/13 vs 5/13"),
    12610: ("tuit_lb_wrong", "Fix TUIT's lb_number (tracker side); LB date stands — "
            "setlist matches LB date 21/21 vs 14/21"),
    13944: ("multi_night", "Leave — 97-song multi-night Universal Amphitheatre set fits "
            "both 6/1 and 6/3/78"),
}
KNOWN_CIRCA = {
    2852: ("single_show", "Refine to 1961-11-04 (Carnegie Chapter Hall) — needs an "
           "entry date_str consumer for corrections first"),
    558: ("single_show", "Arguably refine to 1994-05-22 (Nara, Great Music Experience) — "
          "same consumer gap"),
}
_KNOWN_SRC_GROUPS = (
    ((448, 692, 733, 3678, 10433, 10753), "lb_aud_at_sbd", "Audience",
     "Curator edit LB -> Audience: mic recorded AT the soundboard"),
    ((7200, 1608), "lb_aud_at_sbd", "Mixed",
     "Curator edit LB -> Mixed: SBD/AUD matrix"),
    ((2558, 10706, 5970, 7847, 9875, 11087, 7909), "broadcast", "FM/Pre-FM",
     "Curator edit LB -> FM/Pre-FM: radio/TV broadcast"),
    ((7160, 16253, 2860, 9648, 9649), "tuit_wrong", None,
     "Keep LB: mic chain in lineage, TUIT label wrong"),
)
KNOWN_SRC = {lb: (cls, target, action)
             for lbs, cls, target, action in _KNOWN_SRC_GROUPS for lb in lbs}

_COMPILATION_RE = re.compile(
    r"\b(various|vol(ume)?\.?\s*[ivx\d]+|masters|collection|compilation|"
    r"rarities|outtakes|sessions|tour\s+(19|20)\d\d|\d{4}\s+tour|box|"
    r"anthology|best of|chronicles?|bootleg series|bootleg|assorted|misc|"
    r"all known versions|odds and ends|several dates|dvd|tapes|acetates?|"
    r"(19|20)?\d\d\s*-\s*(19|20)?\d\d)\b",
    re.IGNORECASE,
)
_POSITIONAL_SBD_RE = re.compile(
    r"\b(at|behind|near|by|beside|next to|in front of|front of|right of|left of|"
    r"right center|left center)\s+(the\s+)?(sbd|soundboard|board|mixing desk|desk)\b",
    re.IGNORECASE,
)
_MIC_RE = re.compile(
    r"\b(mics?|microphones?|dpa|schoeps|akg|neumann|ecm-?\s?\d+|core ?sound|cs ?heb|"
    r"cshe?b|binaural|sennheiser|mkh|at-?8\d\d|nakamichi cm|cm-?300|church|"
    r"lavalier|omni|cardioid|walkman|wm-?d6c?|d-?5|sony d[5-8]|audience)\b",
    re.IGNORECASE,
)
_BROADCAST_RE = re.compile(
    r"(?i:\b(pre-?fm|fm|radio|broadcast|simulcast|webcast|satellite|television|"
    r"bbc|vh1|mtv|cbs|nbc|pbs)\b(?!\s+band))|\b[WK][A-Z]{2,3}\b",  # call letters: case-sensitive
)
_SBD_RE = re.compile(
    r"\b(soundboard|sbd|board tape|direct feed|line feed|line out|multitrack|"
    r"desk tape|monitor mix)\b",
    re.IGNORECASE,
)
_MATRIX_RE = re.compile(r"\bmatrix\b(?!\s*[:#]|\s+\d)|\baud\s*\+\s*sbd\b", re.IGNORECASE)

_STOP = {"the", "and", "of", "at", "de", "la", "le", "der", "die", "das"}
_GEO_WORDS = {
    "usa", "us", "united", "states", "america", "uk", "england", "scotland", "wales",
    "ireland", "canada", "germany", "france", "italy", "spain", "japan", "australia",
    "netherlands", "holland", "sweden", "norway", "denmark", "switzerland", "austria",
    "belgium", "city", "new", "north", "south", "east", "west", "nyc", "dc", "bc",
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "hampshire",
    "jersey", "mexico", "york", "carolina", "dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode", "island", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "wisconsin", "wyoming", "ontario", "quebec", "columbia",
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
    "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
    "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
    "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "on", "qc",
}


# ── Normalisation helpers ─────────────────────────────────────────────────────

def lb_date_parts(date_str: str | None) -> tuple[int | None, int | None, int | None] | None:
    """Parse an ``entries.date_str`` (M/D/YY, 'xx' allowed) into (year, month, day).

    Args:
        date_str: e.g. ``'6/3/78'``, ``'5/xx/94'``, ``'xx/xx/61'``.

    Returns:
        ``(year, month, day)`` with ``None`` for an 'xx' part, or ``None`` when
        the string is blank or unparseable (or the year itself is unknown).
    """
    if not date_str:
        return None
    parts = [p.strip().lower() for p in date_str.split("/")]
    if len(parts) != 3:
        return None
    vals: list[int | None] = []
    for p in parts:
        if not p or "x" in p:
            vals.append(None)
            continue
        try:
            vals.append(int(p))
        except ValueError:
            return None
    month, day, year = vals
    if year is None:
        return None
    if year < 100:
        year = 1900 + year if year >= 49 else 2000 + year
    return year, month, day


def iso_parts(iso: str | None) -> tuple[int, int, int] | None:
    """Parse a TUIT ISO ``YYYY-MM-DD`` date; ``None`` when blank/invalid."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (iso or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def norm_text(s: str | None) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("’", "'").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def _tokens(s: str | None) -> set[str]:
    return {t for t in norm_text(s).split() if t not in _STOP}


def song_key(title: str | None) -> str:
    """Normalise a song title for setlist overlap (drops parentheticals)."""
    return norm_text(re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title or ""))


def tuit_setlist(setlist_json: str | None) -> list[str]:
    """Song titles from TUIT's ``setlist_json`` (empty list when absent/bad)."""
    try:
        rows = json.loads(setlist_json or "[]")
    except (TypeError, ValueError):
        return []
    return [str(r.get("song", "")).strip() for r in rows
            if isinstance(r, dict) and str(r.get("song", "")).strip()]


def lb_setlist(setlist: str | None) -> list[str]:
    """Song titles from a free-text ``entries.setlist`` ('1. A 2 B, 3 C')."""
    parts = re.split(r"(?:^|[\s,;])\d{1,3}[.)]?\s+", setlist or "")
    return [p.strip(" ,;") for p in parts if p.strip(" ,;")]


def render_setlist(songs: list[str]) -> str:
    """Render TUIT songs in the ``entries.setlist`` style: ``'1. A 2. B'``."""
    return " ".join(f"{i}. {s}" for i, s in enumerate(songs, 1))


def classify_venue(tuit_venue: str | None, tuit_location: str | None,
                   lb_location: str | None) -> str:
    """Compare TUIT's structured venue with our free-text location.

    Returns:
        ``agree`` (venue named in location), ``partial`` (some venue words),
        ``city_only`` (location holds only place names — TUIT adds the venue),
        ``lb_blank``, ``tuit_blank`` or ``differs`` (location names something else).
    """
    if not (tuit_venue or "").strip():
        return "tuit_blank"
    if not (lb_location or "").strip():
        return "lb_blank"
    nv, nl = norm_text(tuit_venue), norm_text(lb_location)
    if nv and nv in nl:
        return "agree"
    vt = {t for t in _tokens(tuit_venue) if len(t) >= 3}
    lt = _tokens(lb_location)
    if vt and len(vt & lt) / len(vt) >= 0.6:
        return "agree"
    rest = lt - _tokens(tuit_location) - _GEO_WORDS
    rest = {t for t in rest if not t.isdigit()}
    if not rest:
        return "city_only"
    if vt & rest:
        return "partial"
    return "differs"


def _evidence(text: str) -> dict[str, bool]:
    return {
        "positional_sbd": bool(_POSITIONAL_SBD_RE.search(text)),
        "mic": bool(_MIC_RE.search(text)),
        "broadcast": bool(_BROADCAST_RE.search(text)),
        "sbd": bool(_SBD_RE.search(_POSITIONAL_SBD_RE.sub(" ", text))),
        "matrix": bool(_MATRIX_RE.search(text)),
    }


def classify_source_conflict(lb_number: int, lb_src: str, tuit_src: str,
                             text: str) -> tuple[str, str | None, str]:
    """Classify one source-type disagreement from the lineage text.

    Args:
        lb_number: The LB (checked against the hand-adjudicated table first).
        lb_src: ``entries.source_type``.
        tuit_src: TUIT's source mapped into our vocabulary.
        text: LB description + source_chain + TUIT lineage/info text.

    Returns:
        ``(class, target_source_type_or_None, recommended_action)``.
    """
    if lb_number in KNOWN_SRC:
        return KNOWN_SRC[lb_number]
    if "ALD" in (lb_src, tuit_src):
        return ("vocab_overlap", None,
                "Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB")
    ev = _evidence(text)
    if lb_src == "Soundboard" and ev["positional_sbd"] and ev["mic"]:
        return ("lb_aud_at_sbd", "Audience",
                "Curator edit LB -> Audience: 'at the soundboard' is a mic position")
    if ev["broadcast"] and "FM/Pre-FM" in (lb_src, tuit_src):
        return ("broadcast", "FM/Pre-FM", "Review: broadcast wording in lineage")
    if ev["matrix"] and "Mixed" in (lb_src, tuit_src):
        return ("matrix", "Mixed", "Review: matrix wording in lineage")
    if tuit_src == "Soundboard" and ev["mic"] and not ev["sbd"]:
        return ("tuit_wrong", None, "Keep LB: mic chain in lineage, no soundboard wording")
    if lb_src == "Soundboard" and ev["mic"] and not ev["sbd"]:
        return ("lb_wrong", tuit_src, f"Review: mic chain, no soundboard wording -> {tuit_src}")
    if lb_src == "Audience" and tuit_src == "Soundboard" and ev["sbd"] and not ev["mic"]:
        return ("lb_wrong", "Soundboard", "Review: soundboard wording, no mic chain")
    if "Mixed" in (lb_src, tuit_src):
        return ("vocab_overlap", None, "Leave: Mixed includes the other side's source")
    return ("no_evidence", None, "Leave: lineage carries no source evidence (advisory)")


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_pairs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT t.rec_id, t.lb_number, t.date_str AS t_date, t.venue AS t_venue,
                  t.location AS t_location, t.source_type AS t_src, t.lineage AS t_lineage,
                  t.info_text AS t_info, t.setlist_json AS t_setlist, t.title AS t_title,
                  t.uploader AS t_uploader,
                  e.date_str AS e_date, e.location AS e_location, e.source_type AS e_src,
                  e.source_chain AS e_chain, e.setlist AS e_setlist,
                  e.description AS e_desc,
                  lm.lb_status
             FROM tuit_recordings t
             JOIN entries e ON e.lb_number = t.lb_number
             LEFT JOIN lb_master lm ON lm.lb_number = t.lb_number
            ORDER BY t.lb_number, t.rec_id"""
    ).fetchall()


def _olof_by_date(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    try:
        events = conn.execute(
            "SELECT event_id, date_str, venue, city FROM olof_events WHERE date_str != ''"
        ).fetchall()
        songs: dict[int, set[str]] = defaultdict(set)
        for r in conn.execute("SELECT event_id, song_title FROM olof_songs"):
            songs[r[0]].add(song_key(r[1]))
    except sqlite3.OperationalError:  # olof_* absent (fixture / fresh DB)
        return out
    for e in events:
        out[e[1]].append({"event_id": e[0], "venue": e[2], "city": e[3],
                          "songs": songs.get(e[0], set())})
    return out


def _setlist_overlap(songs: list[str], events: list[dict]) -> tuple[int, int]:
    """Best (matched, total) of TUIT songs against any olof event on one date."""
    keys = {song_key(s) for s in songs if song_key(s)}
    if not keys:
        return (0, 0)
    best = max((len(keys & e["songs"]) for e in events), default=0)
    return (best, len(keys))


def _iso(p: tuple[int | None, int | None, int | None] | None) -> str:
    if not p:
        return ""
    y, m, d = p
    return f"{y:04d}-{m or 0:02d}-{d or 0:02d}".replace("-00", "-xx")


# ── Comparison ────────────────────────────────────────────────────────────────

def compute(conn: sqlite3.Connection) -> dict:
    """Build every reconciliation finding (read-only).

    Args:
        conn: Connection to a DB holding tuit_recordings, entries and lb_master
            (olof_events/olof_songs optional — used as date evidence).

    Returns:
        Dict with ``stats`` plus per-field row lists: ``date_conflicts``,
        ``circa``, ``source_conflicts``, ``source_fills``, ``venue``,
        ``lineage_fills``, ``setlist_fills`` and ``fills`` (the --fill plan).
    """
    conn.row_factory = sqlite3.Row
    pairs = _load_pairs(conn)
    olof = _olof_by_date(conn)
    stats: Counter = Counter()
    stats["tuit_recordings"] = conn.execute("SELECT COUNT(*) FROM tuit_recordings").fetchone()[0]
    stats["tuit_with_lb"] = conn.execute(
        "SELECT COUNT(*) FROM tuit_recordings WHERE lb_number IS NOT NULL").fetchone()[0]
    stats["pairs"] = len(pairs)
    stats["pair_lbs"] = len({p["lb_number"] for p in pairs})

    date_conflicts, circa, src_conflicts, src_fills = [], [], [], []
    venue_rows, lineage_fills, setlist_fills = [], [], []
    date_class: dict[int, set[str]] = defaultdict(set)

    for p in pairs:
        lb = p["lb_number"]
        base = {"lb_number": lb, "rec_id": p["rec_id"], "lb_date": p["e_date"],
                "tuit_date": p["t_date"], "lb_location": p["e_location"],
                "tuit_venue": p["t_venue"], "tuit_location": p["t_location"],
                "lb_status": p["lb_status"]}
        # DATE
        lbp, tp = lb_date_parts(p["e_date"]), iso_parts(p["t_date"])
        if not tp:
            dcls = "tuit_blank"
        elif not lbp:
            dcls = "lb_blank"
        elif None not in lbp:
            dcls = "agree" if lbp == tp else "conflict"
        else:
            y, m, _ = lbp
            dcls = "circa_refine" if y == tp[0] and m in (None, tp[1]) else "circa_mismatch"
        stats[f"date_{dcls}"] += 1
        date_class[lb].add(dcls)
        songs = tuit_setlist(p["t_setlist"])
        text = " ".join(x or "" for x in (p["e_desc"], p["e_chain"], p["t_lineage"],
                                          p["t_info"]))
        if dcls == "conflict":
            lb_songs = lb_setlist(p["e_setlist"])
            lb_ov = _setlist_overlap(lb_songs, olof.get(_iso(lbp), []))
            t_ov = _setlist_overlap(lb_songs, olof.get(p["t_date"], []))
            if lb in KNOWN_DATE:
                cls, action = KNOWN_DATE[lb]
            elif lb_ov[0] > t_ov[0]:
                cls, action = "tuit_lb_wrong", "Fix TUIT's lb_number; setlist fits LB date"
            elif t_ov[0] > lb_ov[0]:
                cls, action = "lb_date_suspect", "Review LB date; setlist fits TUIT date"
            else:
                cls, action = "unresolved", "Review by hand"
            date_conflicts.append({**base, "class": cls, "action": action,
                                   "setlist_fit_lb": f"{lb_ov[0]}/{lb_ov[1]}",
                                   "setlist_fit_tuit": f"{t_ov[0]}/{t_ov[1]}"})
        elif dcls.startswith("circa"):
            label = " ".join(x or "" for x in (p["e_location"], p["t_title"]))
            events = olof.get(p["t_date"], [])
            venue_hit = any(_tokens(e["venue"]) & _tokens(p["e_location"]) for e in events
                            if e["venue"])
            if lb in KNOWN_CIRCA:
                cls, action = KNOWN_CIRCA[lb]
            elif _COMPILATION_RE.search(label):
                cls, action = ("compilation",
                               "Leave: multi-show compilation; TUIT files it under one date")
            elif dcls == "circa_mismatch":
                cls, action = ("misattribution",
                               "Leave LB; TUIT date/lb_number likely wrong (year/month differ)")
            elif venue_hit or classify_venue(p["t_venue"], p["t_location"],
                                             p["e_location"]) == "agree":
                cls, action = ("single_show",
                               "Refine date once an entry date_str correction consumer exists")
            else:
                cls, action = "unverified", "Review: no olof venue match on TUIT date"
            circa.append({**base, "date_class": dcls, "class": cls, "action": action,
                          "olof_events_on_tuit_date": len(events)})

        # SOURCE TYPE
        t_src = TUIT_SRC_MAP.get((p["t_src"] or "").upper())
        e_src = (p["e_src"] or "").strip()
        if not t_src:
            scls = "tuit_blank"
        elif not e_src:
            scls = "tuit_fill"
            src_fills.append({**base, "tuit_source": t_src})
        elif e_src == t_src:
            scls = "agree"
        else:
            scls = "conflict"
            cls, target, action = classify_source_conflict(lb, e_src, t_src, text)
            src_conflicts.append({**base, "lb_source": e_src, "tuit_source": t_src,
                                  "class": cls, "target": target or "", "action": action,
                                  "uploader": p["t_uploader"]})
        stats[f"source_{scls}"] += 1

        # VENUE
        vcls = classify_venue(p["t_venue"], p["t_location"], p["e_location"])
        stats[f"venue_{vcls}"] += 1
        venue_rows.append({**base, "class": vcls})

        # LINEAGE / SETLIST (presence)
        has_t_lin = bool((p["t_lineage"] or "").strip())
        has_e_lin = bool((p["e_chain"] or "").strip())
        lcls = {(True, True): "both", (True, False): "tuit_only",
                (False, True): "lb_only", (False, False): "neither"}[(has_t_lin, has_e_lin)]
        stats[f"lineage_{lcls}"] += 1
        # A bare "LB-4" is TUIT echoing the LB number, not lineage (2026-10-26: 993 of 2,335).
        if lcls == "tuit_only" and not _LB_SELF_REF_RE.fullmatch(p["t_lineage"].strip()):
            lineage_fills.append({**base, "tuit_lineage": p["t_lineage"].strip()})
        has_e_set = bool((p["e_setlist"] or "").strip())
        tcls = {(True, True): "both", (True, False): "tuit_only",
                (False, True): "lb_only", (False, False): "neither"}[(bool(songs), has_e_set)]
        stats[f"setlist_{tcls}"] += 1
        if tcls == "tuit_only":
            setlist_fills.append({**base, "tuit_setlist": render_setlist(songs),
                                  "n_songs": len(songs)})

    for r in src_conflicts:
        stats[f"source_conflict_{r['class']}"] += 1
    for r in circa:
        stats[f"circa_{r['class']}"] += 1

    fills = plan_fills(date_class, src_fills, venue_rows, lineage_fills, setlist_fills)
    for f in fills:
        stats[f"fill_{f['field']}"] += 1
    return {"stats": dict(stats), "date_conflicts": date_conflicts, "circa": circa,
            "source_conflicts": src_conflicts, "source_fills": src_fills,
            "venue": venue_rows, "lineage_fills": lineage_fills,
            "setlist_fills": setlist_fills, "fills": fills}


def plan_fills(date_class: dict[int, set[str]], src_fills: list[dict],
               venue_rows: list[dict], lineage_fills: list[dict],
               setlist_fills: list[dict]) -> list[dict]:
    """The additive-only fill plan: one value per (LB, field), date-agreeing LBs only.

    An LB qualifies only when every TUIT recording claiming it has a full date
    that agrees with ours. A field is filled only when every candidate TUIT
    recording for that LB offers the same value (otherwise it is ambiguous —
    two different TUIT torrents for one LB — and left for review).

    Returns:
        List of ``{lb_number, field, value, rec_ids, class}`` dicts.
    """
    trusted = {lb for lb, cls in date_class.items() if cls == {"agree"}}
    cands: dict[tuple[int, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for r in src_fills:
        cands[(r["lb_number"], "source_type")][r["tuit_source"]].append(r["rec_id"])
    for r in venue_rows:
        if r["class"] in ("city_only", "lb_blank"):
            cands[(r["lb_number"], "venue")][r["tuit_venue"].strip()].append(r["rec_id"])
    for r in lineage_fills:
        cands[(r["lb_number"], "source_chain")][r["tuit_lineage"]].append(r["rec_id"])
    for r in setlist_fills:
        cands[(r["lb_number"], "setlist")][r["tuit_setlist"]].append(r["rec_id"])
    out = []
    for (lb, field), values in sorted(cands.items()):
        if lb not in trusted or len(values) != 1:
            continue
        (value, rec_ids), = values.items()
        out.append({"lb_number": lb, "field": field, "value": value,
                    "rec_ids": sorted(rec_ids), "class": "empty_lb_field"})
    return out


# ── Write paths (dry-run unless --apply) ──────────────────────────────────────

_ENTRY_COL = {"source_type": "source_type", "source_chain": "source_chain",
              "setlist": "setlist", "venue": None}


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = db_path.parent / "backups" / f"{db_path.stem}_pre_tuit_reconcile_{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
        ok = dst.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if ok != "ok":
        raise RuntimeError(f"backup quick_check failed: {ok}")
    return dest


def _audit(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def apply_fills(conn: sqlite3.Connection, fills: list[dict], *, apply: bool,
                audit_path: Path | None = None) -> dict[str, int]:
    """Stage fills into ``corrections`` (dry run unless ``apply``).

    Each fill is re-checked against the live row at write time: the entry's
    field must still be empty and no ``corrections`` row may exist for that
    (entry, field). All inserts commit in one transaction.

    Args:
        conn: Writable connection.
        fills: Output of :func:`plan_fills` (optionally filtered by field).
        apply: Write when True; otherwise only count.
        audit_path: JSONL file receiving one line per inserted correction.

    Returns:
        Counts: ``planned``, ``written`` (or ``would_write``), ``skipped_existing``,
        ``skipped_now_filled``.
    """
    counts: Counter = Counter(planned=len(fills))
    now = datetime.now(UTC).isoformat(timespec="seconds")
    audit_rows = []
    for f in fills:
        lb, field = f["lb_number"], f["field"]
        if conn.execute(
            "SELECT 1 FROM corrections WHERE entity_kind='entry' AND entity_key=? AND field=?",
            (str(lb), field),
        ).fetchone():
            counts["skipped_existing"] += 1
            continue
        col = _ENTRY_COL[field]
        if col:
            cur = conn.execute(f"SELECT {col} FROM entries WHERE lb_number=?", (lb,)).fetchone()
            if cur is None or (cur[0] or "").strip():
                counts["skipped_now_filled"] += 1
                continue
        if not apply:
            counts["would_write"] += 1
            continue
        reason = (f"TUIT fill from rec {','.join(map(str, f['rec_ids']))} "
                  f"({f['class']}; TODO-332)")
        cid = conn.execute(
            "INSERT INTO corrections (entity_kind, entity_key, field, original, corrected,"
            " reason, decided_by, decided_at) VALUES ('entry', ?, ?, '', ?, ?, ?, ?)",
            (str(lb), field, f["value"], reason, DECIDED_BY, now),
        ).lastrowid
        counts["written"] += 1
        audit_rows.append({"op": "fill", "correction_id": cid, "lb_number": lb,
                           "field": field, "value": f["value"], "rec_ids": f["rec_ids"],
                           "at": now})
    if apply:
        conn.commit()
        if audit_path and audit_rows:
            _audit(audit_path, audit_rows)
    return dict(counts)


def revert_fills(conn: sqlite3.Connection, *, apply: bool,
                 audit_path: Path | None = None) -> int:
    """Delete every correction this tool wrote (dry run unless ``apply``).

    Returns:
        Number of rows deleted (or that would be).
    """
    rows = conn.execute(
        "SELECT id, entity_key, field, corrected FROM corrections WHERE decided_by=?",
        (DECIDED_BY,),
    ).fetchall()
    if apply and rows:
        conn.execute("DELETE FROM corrections WHERE decided_by=?", (DECIDED_BY,))
        conn.commit()
        if audit_path:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            _audit(audit_path, [{"op": "revert", "correction_id": r[0], "lb_number": r[1],
                                 "field": r[2], "value": r[3], "at": now} for r in rows])
    return len(rows)


# ── Markdown ──────────────────────────────────────────────────────────────────

def _cell(v) -> str:
    s = "" if v is None else str(v)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 70 else s[:67] + "..."


def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def _count_table(stats: dict, prefix: str) -> list[str]:
    rows = [[k[len(prefix):], v] for k, v in sorted(stats.items()) if k.startswith(prefix)]
    return _table(["class", "rows"], rows)


def render_markdown(res: dict, generated: str | None = None) -> str:
    """Render the report as markdown (every adjudication row; samples of bulk fills)."""
    s = res["stats"]
    generated = generated or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    dc_mix = ", ".join(f"{k} {v}" for k, v in
                       sorted(Counter(r["class"] for r in res["date_conflicts"]).items()))
    out = [
        "# TUIT ↔ entries reconciliation (TODO-332, TODO-339 parts 1–2)", "",
        f"Generated {generated} by `tools/tuit_reconcile.py` (read-only). "
        f"{s.get('tuit_recordings', 0)} TUIT recordings, {s.get('tuit_with_lb', 0)} claim an "
        f"LB number; {s.get('pairs', 0)} pairs over {s.get('pair_lbs', 0)} LBs join an entry.",
        "",
        "## Headline", "",
        f"- Dates: {s.get('date_agree', 0)} agree, {s.get('date_conflict', 0)} full-date "
        f"conflict rows ({dc_mix}), "
        f"{s.get('date_circa_refine', 0) + s.get('date_circa_mismatch', 0)} circa rows of "
        f"which {s.get('circa_single_show', 0)} are single-show refinements.",
        f"- Source type: {s.get('source_agree', 0)} agree, {s.get('source_conflict', 0)} "
        f"conflicts, {s.get('source_tuit_fill', 0)} rows where only TUIT has one.",
        f"- Fill plan: {sum(v for k, v in s.items() if k.startswith('fill_'))} additive values "
        f"({', '.join(f'{k[5:]} {v}' for k, v in sorted(s.items()) if k.startswith('fill_'))}).",
        "",
        "Stage the fills (dry run first; `--apply` backs the DB up to `data/backups/` and "
        "audit-logs to `data/logs/tuit_reconcile_audit.jsonl`; `--revert --apply` undoes):",
        "", "```",
        ".venv/bin/python3 tools/tuit_reconcile.py --fill",
        ".venv/bin/python3 tools/tuit_reconcile.py --fill --apply",
        "```", "",
        "## Per-field policy", "",
        *_table(["field", "TUIT is", "why"], [
            ["date", "advisory", "99.9% agree; the residue is TUIT misattribution or "
             "compilations, never a bulk overwrite"],
            ["source_type", "additive (fill blank) / advisory on conflict",
             "entries.source_type is curator-edited; conflicts need the lineage text"],
            ["venue", "additive", "entries has no venue column; TUIT's is structured"],
            ["lineage", "additive", "fills an empty source_chain only"],
            ["setlist", "additive", "fills an empty setlist only"],
            ["taper", "advisory", "handled by the taper curation console (TODO-213/339 (4))"],
        ]), "",
        "Fills are staged in `corrections` (`entity_kind='entry'`, "
        "`decided_by='tuit_reconcile'`), never written into `entries`: the scraper "
        "rewrites entries rows with INSERT OR REPLACE, and a non-NULL "
        "`entries.metadata_source` makes the public master export strip the row. "
        "No reader consumes entry corrections yet — rendering them is follow-up work.", "",
        "## Dates", "", *_count_table(s, "date_"), "",
        "### Full-date conflicts", "",
        *_table(["LB", "rec", "LB date", "TUIT date", "TUIT venue", "LB setlist ~ LB date",
                 "~ TUIT date",
                 "class", "action"],
                [[r["lb_number"], r["rec_id"], r["lb_date"], r["tuit_date"], r["tuit_venue"],
                  r["setlist_fit_lb"], r["setlist_fit_tuit"], r["class"], r["action"]]
                 for r in res["date_conflicts"]]), "",
        "### Circa-date refinements (TODO-339 part 1)", "",
        *_count_table(s, "circa_"), "",
        *_table(["LB", "rec", "LB date", "TUIT date", "LB location", "TUIT venue", "class",
                 "action"],
                [[r["lb_number"], r["rec_id"], r["lb_date"], r["tuit_date"], r["lb_location"],
                  r["tuit_venue"], r["class"], r["action"]] for r in res["circa"]]), "",
        "## Source type", "", *_count_table(s, "source_"), "",
        "### Conflicts (TODO-339 part 2)", "",
        "`target` is the source type the evidence points to; blank = keep LB. Every "
        "change is a curator edit on our side (entries.source_type is curator-only); "
        "`tuit_wrong` rows are a tracker-side note.", "",
        *_table(["LB", "rec", "LB", "TUIT", "class", "target", "action"],
                [[r["lb_number"], r["rec_id"], r["lb_source"], r["tuit_source"], r["class"],
                  r["target"], r["action"]] for r in res["source_conflicts"]]), "",
        "## Venue", "", *_count_table(s, "venue_"), "",
        "`city_only`/`lb_blank` are fill candidates; `differs`/`partial` need a human "
        "(location may name a different venue or a sub-room).", "",
    ]
    differs = [r for r in res["venue"] if r["class"] == "differs"]
    out += [f"### Venue `differs` (first {_SHOWN} of {len(differs)})", "",
            *_table(["LB", "rec", "LB location", "TUIT venue", "TUIT location"],
                    [[r["lb_number"], r["rec_id"], r["lb_location"], r["tuit_venue"],
                      r["tuit_location"]] for r in differs[:_SHOWN]]), ""]
    out += ["## Lineage", "", *_count_table(s, "lineage_"), "",
            "## Setlist", "", *_count_table(s, "setlist_"), "",
            "## Fill plan (`--fill`)", "",
            "Only LBs whose every TUIT recording agrees on the full date; only fields "
            "empty on our side; only when all TUIT recordings for the LB offer the same "
            "value.", "", *_count_table(s, "fill_"), ""]
    for field in FILL_FIELDS:
        rows = [f for f in res["fills"] if f["field"] == field]
        out += [f"### `{field}` (first {_SHOWN} of {len(rows)})", "",
                *_table(["LB", "rec", "value"],
                        [[f["lb_number"], ",".join(map(str, f["rec_ids"])), f["value"]]
                         for f in rows[:_SHOWN]]), ""]
    return "\n".join(out).rstrip() + "\n"


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Markdown report path.")
    ap.add_argument("--json", default="", help="Also write every row as JSON.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fill", action="store_true", help="Stage additive fills.")
    mode.add_argument("--revert", action="store_true", help="Remove this tool's fills.")
    ap.add_argument("--fields", default=",".join(FILL_FIELDS),
                    help="Comma list of fields for --fill.")
    ap.add_argument("--apply", action="store_true", help="Actually write (with backup).")
    ap.add_argument("--audit", default=str(DEFAULT_AUDIT), help="Audit JSONL path.")
    args = ap.parse_args(argv)
    db_path = Path(args.db)

    if not (args.fill or args.revert):
        if args.apply:
            ap.error("--apply needs --fill or --revert")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        res = compute(conn)
        conn.close()
        Path(args.out).write_text(render_markdown(res), encoding="utf-8")
        if args.json:
            Path(args.json).write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                       encoding="utf-8")
        logger.info("report -> %s  %s", args.out,
                    " ".join(f"{k}={v}" for k, v in sorted(res["stats"].items())))
        return 0

    fields = {f.strip() for f in args.fields.split(",") if f.strip()}
    bad = fields - set(FILL_FIELDS)
    if bad:
        ap.error(f"unknown --fields: {sorted(bad)}")
    if args.apply:
        logger.info("backup -> %s", _backup(db_path))
    conn = sqlite3.connect(str(db_path) if args.apply else f"file:{db_path}?mode=ro",
                           uri=not args.apply, timeout=30)
    try:
        if args.revert:
            n = revert_fills(conn, apply=args.apply, audit_path=Path(args.audit))
            logger.info("%s %d tuit_reconcile corrections", "deleted" if args.apply
                        else "would delete", n)
            return 0
        res = compute(conn)
        fills = [f for f in res["fills"] if f["field"] in fields]
        counts = apply_fills(conn, fills, apply=args.apply, audit_path=Path(args.audit))
        logger.info("%s fill: %s", "APPLIED" if args.apply else "DRY RUN",
                    " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
