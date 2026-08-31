"""Read model for the taper curation workbench (``/taper-curation``).

The older ``/taper-review`` console answers "what does the attribution engine
say, and do I agree?". This module answers the wider question a curator
actually faces per entry: *every* source that has an opinion about who taped a
recording, side by side, plus the raw text the opinion was extracted from.

Sources joined per LB number:

* ``entries`` — the LB site's own assignment (``taper_name``, ``source_chain``)
  and the full ``description`` the parser read.
* ``entry_lineage`` — what the parser normalised that text to, and whether the
  result survived the known-taper universe gate.
* ``taper_attributions`` / ``taper_confirmations`` — the derived credit, its
  confidence tier, conflict flag and any sticky curator decision.
* ``tuit_recordings`` — the private tracker's uploader-declared taper handle,
  or ``None`` when that LB was never scraped ("not scraped" in the UI).
* ``recording_families`` / ``tapematch_family_meta`` / ``tapematch_pairs`` —
  the acoustic family a recording landed in, its label and review flag, and
  the strongest measured pair similarity, i.e. *the quality of the matching*
  behind any propagated attribution.

Everything here is read-only. Writes go through the existing curator-gated
routes (``/api/tapers/attributions/*``, ``/api/tapers/vocabulary*``), so a
decision made in this workbench is the same decision, logged the same way.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3

from backend import db as _db
from backend.db import _KNOWN_TAPER_ALIASES, _NOT_TAPER, get_connection

logger = logging.getLogger(__name__)

MAX_LIMIT = 500
DESCRIPTION_CAP = 6000

_SORTS = {
    "lb": "e.lb_number",
    "date": "sort_date",
    "taper": "COALESCE(a.taper_normalised, '')",
    "confidence": "COALESCE(a.confidence, '')",
    "similarity": "COALESCE(m.conf, -1)",
}

# entries.date_str is 'M/D/YY' free text; the review console's own sortable
# expression is reused rather than reformatted, so both surfaces order alike.
_SORTABLE_DATE = (
    "CASE WHEN e.date_str LIKE '%/%/%' THEN"
    " printf('%04d-%02d-%02d',"
    "  CASE WHEN CAST(substr(e.date_str, -2) AS INTEGER) >= 60"
    "       THEN 1900 + CAST(substr(e.date_str, -2) AS INTEGER)"
    "       ELSE 2000 + CAST(substr(e.date_str, -2) AS INTEGER) END,"
    "  CAST(substr(e.date_str, 1, instr(e.date_str, '/') - 1) AS INTEGER),"
    "  CAST(substr(substr(e.date_str, instr(e.date_str, '/') + 1),"
    "       1, instr(substr(e.date_str, instr(e.date_str, '/') + 1), '/') - 1)"
    "       AS INTEGER))"
    " ELSE e.date_str END"
)

_BASE = (
    " FROM entries e"
    " LEFT JOIN taper_attributions a ON a.lb_number = e.lb_number"
    " LEFT JOIN taper_confirmations f ON f.lb_number = e.lb_number"
    " LEFT JOIN entry_lineage g ON g.lb_number = e.lb_number"
    " LEFT JOIN lb_master lm ON lm.lb_number = e.lb_number"
    " LEFT JOIN tuit_recordings t ON t.rec_id = ("
    "     SELECT x.rec_id FROM tuit_recordings x WHERE x.lb_number = e.lb_number"
    "     ORDER BY x.last_seen_at DESC, x.rec_id DESC LIMIT 1)"
    " LEFT JOIN recording_families rf ON rf.lb_number = e.lb_number"
    " LEFT JOIN tapematch_family_meta m ON m.fam_id = rf.fam_id"
)

_SELECT = (
    "SELECT e.lb_number, e.date_str, e.location, e.taper_name, e.source_chain,"
    " e.description, e.lb_category, e.status,"
    f" ({_SORTABLE_DATE}) AS sort_date,"
    " lm.lb_status,"
    " g.taper_normalised AS parsed_taper, g.parse_confidence,"
    " a.taper_normalised AS attr_taper, a.confidence AS attr_confidence,"
    " a.conflict AS attr_conflict, a.evidence_json, a.computed_at,"
    " f.action AS decision, f.taper_normalised AS decision_taper, f.decided_at,"
    " t.rec_id AS tuit_rec_id, t.taper AS tuit_taper, t.source_type AS tuit_source,"
    " t.quality AS tuit_quality, t.uploader AS tuit_uploader,"
    " t.lineage AS tuit_lineage, t.info_text AS tuit_info, t.lb_verified AS tuit_verified,"
    " rf.fam_id, m.label AS fam_label, m.label_override AS fam_label_override,"
    " m.conf AS fam_conf, m.member_count AS fam_members,"
    " m.review_flag AS fam_review_flag, m.review_reason AS fam_review_reason"
)


# ── normalisation helpers ─────────────────────────────────────────────────────

# Placeholder text TUIT uploaders put in the taper field when nobody knows who
# taped it. Treated as "no tag" rather than as a taper called 'unknown'.
_PLACEHOLDER_TAPERS = frozenset({
    "unknown", "unknown taper", "unidentified", "unidentified taper",
    "n/a", "na", "none", "-", "?", "tbd",
})


def is_placeholder(name: str | None) -> bool:
    """Return True when *name* is a stand-in for "nobody knows".

    Args:
        name: Raw taper text from any source.

    Returns:
        True if the text carries no attribution information.
    """
    return (name or "").strip().lower() in _PLACEHOLDER_TAPERS


def canonical(name: str | None) -> str:
    """Return the canonical taper token for *name*, or ''.

    Args:
        name: Raw or already-normalised taper text.

    Returns:
        The alias-resolved lowercase canonical, or '' when *name* is empty.
    """
    if is_placeholder(name):
        return ""
    norm = _db._normalise_taper(name)
    return norm or ""


# Curator not-a-taper calls (user_taper_flags, TODO-313). A flagged canonical is
# usually NOT an alias value — 'bootleg' is plain description text — so it can
# only be recognised by reading the table; without this it would fall through to
# 'unknown_text' and keep contesting the agreement verdict after being ruled out.
_USER_NOT_TAPER: set[str] = set()


def refresh_user_flags(db_path: str | None = None) -> set[str]:
    """Reload the curator's not-a-taper canonicals into module state.

    Called at the top of every read entry point: one tiny indexed query, versus
    a stale exclusion verdict surviving until the process restarts.

    Args:
        db_path: Optional database path override.

    Returns:
        The set of canonicals a curator has flagged not-a-taper.
    """
    global _USER_NOT_TAPER
    try:
        _USER_NOT_TAPER = {
            row[0] for row in get_connection(db_path).execute(
                "SELECT canonical FROM user_taper_flags WHERE action = 'not_taper'")
        }
    except sqlite3.Error:  # table absent on a bare DB — treat as no overrides
        _USER_NOT_TAPER = set()
    return _USER_NOT_TAPER


def exclusion_reason(canon: str) -> str | None:
    """Why a canonical token is barred from being a taper credit, if it is.

    Args:
        canon: Canonical taper token (output of :func:`canonical`).

    Returns:
        'not_taper_builtin', 'not_taper_user', 'unknown_text', or None when the
        token is a member of the live taper universe.
    """
    if not canon:
        return None
    if canon in _db._TAPER_UNIVERSE:
        return None
    if canon in _NOT_TAPER:
        return "not_taper_builtin"
    if canon in _USER_NOT_TAPER or canon in set(_KNOWN_TAPER_ALIASES.values()):
        return "not_taper_user"
    return "unknown_text"


def credible(name: str | None) -> str:
    """Canonical form of *name*, or '' when it can never be a taper credit.

    A name the vocabulary explicitly bars (``jtt``, ``master``, ``bootleg`` once
    flagged) is noise in the taper column, not a competing opinion — counting it
    would fill the "sources disagree" queue with gear and source-type text.
    Names that are merely *unknown* still count: an unrecognised handle is
    exactly what curation is looking for.

    Args:
        name: Raw taper text from any source.

    Returns:
        The canonical token, or '' when the text is barred or empty.
    """
    canon = canonical(name)
    if exclusion_reason(canon) in ("not_taper_builtin", "not_taper_user"):
        return ""
    return canon


def agreement(attr: str, tuit: str, lb_text: str, scraped: bool) -> str:
    """Classify how the sources line up for one entry.

    Args:
        attr: Canonical attribution taper ('' when none).
        tuit: Canonical TUIT taper ('' when none or not scraped).
        lb_text: Canonical LB-site taper text ('' when none).
        scraped: Whether a TUIT recording exists for this LB at all.

    Returns:
        One of 'agree', 'conflict', 'tuit_only', 'lb_only', 'attr_only',
        'not_scraped', 'none'.
    """
    named = {v for v in (attr, tuit, lb_text) if v}
    if len(named) > 1:
        return "conflict"
    if attr and (tuit or lb_text):
        return "agree"
    if tuit:
        return "tuit_only"
    if attr:
        return "attr_only"
    if lb_text:
        return "lb_only"
    return "not_scraped" if not scraped else "none"


def find_candidates(text: str | None, limit: int = 12) -> list[dict]:
    """Find known-alias hits in free text and say what became of each.

    This is the row-level half of "what got isolated from being a taper name":
    every alias the parser could see in the description, with the verdict the
    vocabulary gives it.

    Args:
        text: Entry description or source chain.
        limit: Maximum distinct canonicals to report.

    Returns:
        List of ``{"text", "canonical", "status"}`` where status is 'known',
        'not_taper_builtin', 'not_taper_user' or 'unknown_text'.
    """
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for match in _db._KNOWN_TAPER_RE.finditer(text[:DESCRIPTION_CAP]):
        raw = match.group(1)
        canon = canonical(raw)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        out.append({
            "text": raw,
            "canonical": canon,
            "status": exclusion_reason(canon) or "known",
        })
        if len(out) >= limit:
            break
    return out


_REAL_TUIT_TAPER = (
    "TRIM(COALESCE(t.taper, '')) <> ''"
    " AND LOWER(TRIM(t.taper)) NOT IN (" +
    ", ".join(f"'{p}'" for p in sorted(_PLACEHOLDER_TAPERS)) + ")"
)


# ── filters ───────────────────────────────────────────────────────────────────

def _filters(
    state: str | None,
    confidence: str | None,
    conflict: bool | None,
    taper: str | None,
    q: str | None,
    attributed: bool | None,
    tuit: str | None,
    family: str | None,
) -> tuple[str, list]:
    """Build the shared WHERE clause.

    Args:
        state: 'any' | 'undecided' | 'confirm' | 'reject' | 'unresolved'.
        confidence: Attribution tier, or 'none' for unattributed rows.
        conflict: Restrict to conflict / non-conflict attributions.
        taper: Restrict to one canonical taper (attribution or TUIT side).
        q: Free-text search over LB number, location, taper text, description.
        attributed: True = only attributed, False = only unattributed.
        tuit: 'scraped' | 'not_scraped' | 'has_taper' | 'taper_only'.
        family: 'has' | 'none' | 'review'.

    Returns:
        ``(where_sql, params)``.

    Raises:
        ValueError: An enum-valued filter got an unusable value.
    """
    clauses: list[str] = []
    params: list = []

    if state and state != "any":
        if state == "undecided":
            clauses.append("f.action IS NULL")
        elif state in ("confirm", "reject", "unresolved"):
            clauses.append("f.action = ?")
            params.append(state)
        else:
            raise ValueError(f"unknown state {state!r}")
    if confidence:
        if confidence == "none":
            clauses.append("a.taper_normalised IS NULL")
        else:
            clauses.append("a.confidence = ?")
            params.append(confidence)
    if conflict is not None:
        clauses.append("COALESCE(a.conflict, 0) = ?")
        params.append(1 if conflict else 0)
    if attributed is not None:
        clauses.append(
            "a.taper_normalised IS NOT NULL" if attributed
            else "a.taper_normalised IS NULL"
        )
    if taper:
        clauses.append(
            "(a.taper_normalised = ? OR LOWER(TRIM(COALESCE(t.taper, ''))) = ?)"
        )
        params.extend([taper.lower(), taper.lower()])
    if tuit:
        if tuit == "scraped":
            clauses.append("t.rec_id IS NOT NULL")
        elif tuit == "not_scraped":
            clauses.append("t.rec_id IS NULL")
        elif tuit == "has_taper":
            clauses.append(_REAL_TUIT_TAPER)
        elif tuit == "taper_only":
            clauses.append(f"{_REAL_TUIT_TAPER} AND a.taper_normalised IS NULL")
        else:
            raise ValueError(f"unknown tuit filter {tuit!r}")
    if family:
        if family == "has":
            clauses.append("rf.fam_id IS NOT NULL")
        elif family == "none":
            clauses.append("rf.fam_id IS NULL")
        elif family == "review":
            clauses.append("COALESCE(m.review_flag, 0) = 1")
        else:
            raise ValueError(f"unknown family filter {family!r}")
    if q:
        term = q.strip()
        if term.upper().startswith("LB-"):
            term = term[3:]
        if term.isdigit():
            clauses.append("e.lb_number = ?")
            params.append(int(term))
        else:
            like = f"%{term}%"
            clauses.append(
                "(e.location LIKE ? OR e.taper_name LIKE ? OR e.description LIKE ?"
                " OR a.taper_normalised LIKE ? OR t.taper LIKE ?)"
            )
            params.extend([like] * 5)

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _shape(row: sqlite3.Row) -> dict:
    """Turn one joined DB row into the workbench's per-entry payload.

    Args:
        row: Row from the wide join.

    Returns:
        A nested dict with ``entry``, ``parsed``, ``attribution``, ``decision``,
        ``tuit``, ``tapematch`` and the derived ``agreement`` verdict.
    """
    r = dict(row)
    description = (r.get("description") or "")[:DESCRIPTION_CAP]
    attr = canonical(r.get("attr_taper"))
    tuit_raw = (r.get("tuit_taper") or "").strip()
    tuit_canon = canonical(tuit_raw)
    lb_canon = canonical(r.get("taper_name"))
    scraped = r.get("tuit_rec_id") is not None
    parsed = canonical(r.get("parsed_taper"))

    return {
        "lb_number": r["lb_number"],
        "entry": {
            "date_str": r.get("date_str"),
            "sort_date": r.get("sort_date"),
            "location": r.get("location"),
            "taper_name": r.get("taper_name"),
            "taper_canonical": lb_canon,
            "taper_excluded": exclusion_reason(lb_canon),
            "source_chain": r.get("source_chain"),
            "description": description,
            "description_len": len(r.get("description") or ""),
            "lb_category": r.get("lb_category"),
            "lb_status": r.get("lb_status"),
            "status": r.get("status"),
        },
        "parsed": {
            "taper": r.get("parsed_taper"),
            "canonical": parsed,
            "excluded": exclusion_reason(parsed),
            "parse_confidence": r.get("parse_confidence"),
        },
        "attribution": {
            "taper": r.get("attr_taper"),
            "confidence": r.get("attr_confidence"),
            "conflict": bool(r.get("attr_conflict")),
            "computed_at": r.get("computed_at"),
            "evidence": json.loads(r.get("evidence_json") or "[]"),
        },
        "decision": {
            "action": r.get("decision"),
            "taper": r.get("decision_taper"),
            "decided_at": r.get("decided_at"),
        },
        "tuit": None if not scraped else {
            "rec_id": r.get("tuit_rec_id"),
            "taper": tuit_raw or None,
            "canonical": tuit_canon,
            "placeholder": is_placeholder(tuit_raw),
            "excluded": exclusion_reason(tuit_canon),
            "source_type": r.get("tuit_source"),
            "quality": r.get("tuit_quality"),
            "uploader": r.get("tuit_uploader"),
            "lineage": r.get("tuit_lineage"),
            "info_text": (r.get("tuit_info") or "")[:DESCRIPTION_CAP] or None,
            "lb_verified": bool(r.get("tuit_verified")),
        },
        "tapematch": None if r.get("fam_id") is None else {
            "fam_id": r.get("fam_id"),
            "label": r.get("fam_label_override") or r.get("fam_label"),
            "label_override": r.get("fam_label_override"),
            "conf": r.get("fam_conf"),
            "member_count": r.get("fam_members"),
            "review_flag": bool(r.get("fam_review_flag")),
            "review_reason": r.get("fam_review_reason"),
            "best_similarity": None,
            "pair_count": 0,
        },
        "candidates": find_candidates(description or r.get("source_chain")),
        "agreement": agreement(attr, credible(tuit_raw),
                               credible(r.get("taper_name")), scraped),
    }


def _attach_pair_quality(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Fill each row's ``tapematch.best_similarity`` / ``pair_count`` in place.

    Done as one extra query over just the page's LB numbers: ``tapematch_pairs``
    has no per-LB index, so a correlated subquery in the main statement would
    scan all 24k pairs per row.

    Args:
        conn: Open connection.
        rows: Shaped rows from :func:`_shape`.
    """
    lbs = [r["lb_number"] for r in rows if r["tapematch"]]
    if not lbs:
        return
    marks = ",".join("?" * len(lbs))
    agg: dict[int, tuple[float | None, int]] = {}
    for lb, best, n in conn.execute(
        f"SELECT lb, MAX(similarity_pct), COUNT(*) FROM ("
        f"  SELECT lb_a AS lb, similarity_pct FROM tapematch_pairs"
        f"   WHERE lb_a IN ({marks}) AND same_family = 1"
        f"  UNION ALL"
        f"  SELECT lb_b AS lb, similarity_pct FROM tapematch_pairs"
        f"   WHERE lb_b IN ({marks}) AND same_family = 1"
        f") GROUP BY lb",
        [*lbs, *lbs],
    ):
        agg[lb] = (best, n)
    for row in rows:
        hit = agg.get(row["lb_number"])
        if hit and row["tapematch"]:
            row["tapematch"]["best_similarity"] = hit[0]
            row["tapematch"]["pair_count"] = hit[1]


def list_rows(
    state: str | None = None,
    confidence: str | None = None,
    conflict: bool | None = None,
    taper: str | None = None,
    q: str | None = None,
    attributed: bool | None = None,
    tuit: str | None = None,
    family: str | None = None,
    agreement_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "lb",
    db_path: str | None = None,
) -> dict:
    """Return one page of the curation workbench.

    Args:
        state: Curator-decision state filter.
        confidence: Attribution tier, or 'none'.
        conflict: Restrict to conflict / non-conflict attributions.
        taper: Restrict to one canonical taper (attribution or TUIT side).
        q: Free-text / LB-number search.
        attributed: True = attributed only, False = unattributed only.
        tuit: 'scraped' | 'not_scraped' | 'has_taper' | 'taper_only'.
        family: 'has' | 'none' | 'review'.
        agreement_filter: Post-filter on the derived agreement verdict. Applied
            in Python (it is computed, not stored), so it pages the filtered
            slice rather than the raw one.
        limit: Page size, clamped to [1, :data:`MAX_LIMIT`].
        offset: Page offset.
        sort: Key from :data:`_SORTS`, '-' prefix to descend.
        db_path: Optional database path override.

    Returns:
        ``{"rows": [...], "total": int, "limit": int, "offset": int,
        "counts": {...}}``.

    Raises:
        ValueError: A filter or sort key has an unusable value.
    """
    desc = sort.startswith("-")
    key = sort[1:] if desc else sort
    if key not in _SORTS:
        raise ValueError(f"sort must be one of {', '.join(_SORTS)}")
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    refresh_user_flags(db_path)
    conn = get_connection(db_path)
    where, params = _filters(state, confidence, conflict, taper, q,
                             attributed, tuit, family)
    order = f" ORDER BY {_SORTS[key]}{' DESC' if desc else ''}, e.lb_number"

    if agreement_filter:
        # The verdict is computed, not stored, so it cannot ride in SQL. Resolve
        # it over a cheap projection first (three taper texts per row, no
        # description and no regex), then re-select only the page's LBs with the
        # full row shape — shaping all 16.7k rows to throw most away costs ~12s.
        matched = [
            r["lb_number"] for r in conn.execute(
                f"SELECT e.lb_number, e.taper_name, a.taper_normalised AS attr_taper,"
                f" t.taper AS tuit_taper, t.rec_id AS tuit_rec_id,"
                f" ({_SORTABLE_DATE}) AS sort_date, a.confidence, m.conf{_BASE}{where}{order}",
                params)
            if agreement(canonical(r["attr_taper"]), credible(r["tuit_taper"]),
                         credible(r["taper_name"]),
                         r["tuit_rec_id"] is not None) == agreement_filter
        ]
        total = len(matched)
        window = matched[offset:offset + limit]
        page = []
        if window:
            marks = ",".join("?" * len(window))
            by_lb = {r["lb_number"]: r for r in (
                _shape(x) for x in conn.execute(
                    f"{_SELECT}{_BASE} WHERE e.lb_number IN ({marks})", window))}
            page = [by_lb[lb] for lb in window if lb in by_lb]
    else:
        total = conn.execute(
            f"SELECT COUNT(*){_BASE}{where}", params).fetchone()[0]
        page = [_shape(r) for r in conn.execute(
            f"{_SELECT}{_BASE}{where}{order} LIMIT ? OFFSET ?",
            [*params, limit, offset])]

    _attach_pair_quality(conn, page)
    return {
        "rows": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": counts(db_path=db_path),
    }


def counts(db_path: str | None = None) -> dict:
    """Corpus-wide totals for the workbench header chips.

    Args:
        db_path: Optional database path override.

    Returns:
        Dict of headline counts (entries, attributed, conflicts, decided,
        TUIT coverage, family coverage, excluded-text rows).
    """
    refresh_user_flags(db_path)
    conn = get_connection(db_path)
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    universe = _db._TAPER_UNIVERSE
    unknown = 0
    for (norm,) in conn.execute(
        "SELECT taper_normalised FROM entry_lineage"
        " WHERE TRIM(COALESCE(taper_normalised, '')) <> ''"
    ):
        if canonical(norm) not in universe:
            unknown += 1
    return {
        "entries": one("SELECT COUNT(*) FROM entries"),
        "attributed": one("SELECT COUNT(*) FROM taper_attributions"
                          " WHERE TRIM(COALESCE(taper_normalised,'')) <> ''"),
        "confirmed": one("SELECT COUNT(*) FROM taper_attributions"
                         " WHERE confidence = 'confirmed'"),
        "conflicts": one("SELECT COUNT(*) FROM taper_attributions WHERE conflict = 1"),
        "decided": one("SELECT COUNT(*) FROM taper_confirmations"),
        "tuit_scraped": one("SELECT COUNT(DISTINCT lb_number) FROM tuit_recordings"
                            " WHERE lb_number IS NOT NULL"),
        "tuit_with_taper": one(
            "SELECT COUNT(DISTINCT lb_number) FROM tuit_recordings t"
            " WHERE t.lb_number IS NOT NULL AND " + _REAL_TUIT_TAPER),
        "in_family": one("SELECT COUNT(DISTINCT lb_number) FROM recording_families"),
        "unknown_text": unknown,
        "vocabulary": len(universe),
    }


# Full-corpus description scan for barred aliases. _NOT_TAPER names are dropped
# at parse time, so they never reach entry_lineage — the only place the evidence
# survives is the raw description text, and scanning all 16.7k of those with the
# alias regex costs ~12s. Cached until the vocabulary or the entries table moves.
_EXCLUDED_CACHE: dict[str, tuple[tuple, dict[str, dict]]] = {}


def _corpus_fingerprint(conn: sqlite3.Connection) -> tuple:
    """Cheap cache key: entry count, newest scrape, and vocabulary size.

    Args:
        conn: Open connection.

    Returns:
        A tuple that changes whenever a rescan of the corpus would differ.
    """
    n, newest = conn.execute(
        "SELECT COUNT(*), MAX(COALESCE(scraped_at, '')) FROM entries").fetchone()
    return (n, newest, len(_KNOWN_TAPER_ALIASES), len(_db._TAPER_UNIVERSE),
            tuple(sorted(_USER_NOT_TAPER)))


def excluded_mentions(
    refresh: bool = False, db_path: str | None = None
) -> dict[str, dict]:
    """Group description mentions of tapers the vocabulary bars.

    Args:
        refresh: Force a rescan even when the cache is warm.
        db_path: Optional database path override.

    Returns:
        ``{canonical: {"canonical", "kind", "reason", "count", "variants",
        "sample_lbs"}}``.
    """
    conn = get_connection(db_path)
    key = str(db_path or "default")
    fingerprint = _corpus_fingerprint(conn)
    cached = _EXCLUDED_CACHE.get(key)
    if cached and cached[0] == fingerprint and not refresh:
        return cached[1]

    groups: dict[str, dict] = {}
    for lb, text in conn.execute(
        "SELECT lb_number, description FROM entries WHERE description IS NOT NULL"
    ):
        for hit in find_candidates(text, limit=40):
            if hit["status"] in ("known", "unknown_text"):
                continue
            g = groups.setdefault(hit["canonical"], {
                "canonical": hit["canonical"], "kind": "excluded",
                "reason": hit["status"], "count": 0, "variants": [],
                "sample_lbs": [],
            })
            g["count"] += 1
            if hit["text"] not in g["variants"] and len(g["variants"]) < 8:
                g["variants"].append(hit["text"])
            if len(g["sample_lbs"]) < 12:
                g["sample_lbs"].append(lb)
    _EXCLUDED_CACHE[key] = (fingerprint, groups)
    return groups


def isolated_texts(
    kind: str | None = None,
    q: str | None = None,
    limit: int = 200,
    refresh: bool = False,
    db_path: str | None = None,
) -> dict:
    """Group the taper texts that never became a taper credit.

    Two populations, both invisible in the attribution table itself:

    * **excluded** — the text resolved to a known canonical that the vocabulary
      bars (``_NOT_TAPER`` builtins such as ``jtt``/``dolphinsmile``, or a
      ``user_taper_flags`` ``not_taper`` row).
    * **unknown** — the text normalised to nothing the vocabulary knows, i.e. a
      candidate handle nobody has ever ruled on. This is the pool worth mining
      for new aliases.

    Args:
        kind: 'excluded' | 'unknown' | None for both.
        q: Substring filter on the text.
        limit: Maximum groups returned, ordered by entry count.
        db_path: Optional database path override.

    Returns:
        ``{"groups": [{"canonical", "kind", "reason", "count", "variants",
        "sample_lbs"}], "total_groups": int}``.
    """
    if kind not in (None, "excluded", "unknown"):
        raise ValueError("kind must be 'excluded' or 'unknown'")
    refresh_user_flags(db_path)
    conn = get_connection(db_path)
    groups: dict[str, dict] = {}
    for lb, raw, norm in conn.execute(
        "SELECT lb_number, taper_name, taper_normalised FROM entry_lineage"
        " WHERE TRIM(COALESCE(taper_normalised, '')) <> ''"
    ):
        canon = canonical(norm)
        reason = exclusion_reason(canon)
        if reason is None:
            continue
        this_kind = "unknown" if reason == "unknown_text" else "excluded"
        if kind and this_kind != kind:
            continue
        if q and q.lower() not in canon.lower() and q.lower() not in (raw or "").lower():
            continue
        g = groups.setdefault(canon, {
            "canonical": canon, "kind": this_kind, "reason": reason,
            "count": 0, "variants": [], "sample_lbs": [],
        })
        g["count"] += 1
        if raw and raw not in g["variants"] and len(g["variants"]) < 8:
            g["variants"].append(raw)
        if len(g["sample_lbs"]) < 12:
            g["sample_lbs"].append(lb)

    if kind != "unknown":
        for canon, g in excluded_mentions(refresh=refresh, db_path=db_path).items():
            if q and q.lower() not in canon.lower():
                continue
            groups[canon] = dict(g)

    ordered = sorted(groups.values(), key=lambda g: (-g["count"], g["canonical"]))
    return {
        "groups": ordered[:limit],
        "total_groups": len(ordered),
        "total_entries": sum(g["count"] for g in ordered),
    }


def taper_rollup(db_path: str | None = None) -> list[dict]:
    """Per-canonical rollup across all sources, for the workbench's Tapers tab.

    Args:
        db_path: Optional database path override.

    Returns:
        One dict per canonical taper: attribution counts by tier, curator
        decisions, TUIT-side count, and how many rows still need a call.
    """
    refresh_user_flags(db_path)
    conn = get_connection(db_path)
    out: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return out.setdefault(name, {
            "taper": name, "attributed": 0, "confirmed": 0, "propagated": 0,
            "conflicts": 0, "decided": 0, "undecided": 0, "tuit": 0,
            "in_universe": name in _db._TAPER_UNIVERSE,
            # Why it is out, so the UI can offer the right fix: a barred name
            # needs an is_taper flag, an unknown one needs a vocabulary entry.
            "excluded": exclusion_reason(name),
        })

    for name, conf, conflict, decision in conn.execute(
        "SELECT a.taper_normalised, a.confidence, a.conflict, f.action"
        " FROM taper_attributions a"
        " LEFT JOIN taper_confirmations f ON f.lb_number = a.lb_number"
        " WHERE TRIM(COALESCE(a.taper_normalised,'')) <> ''"
    ):
        row = slot(name)
        row["attributed"] += 1
        if conf in ("confirmed", "propagated"):
            row[conf] += 1
        row["conflicts"] += 1 if conflict else 0
        if decision:
            row["decided"] += 1
        else:
            row["undecided"] += 1

    for (raw,) in conn.execute(
        "SELECT taper FROM tuit_recordings WHERE TRIM(COALESCE(taper,'')) <> ''"
    ):
        canon = canonical(raw)
        if canon:
            slot(canon)["tuit"] += 1

    return sorted(out.values(), key=lambda r: (-r["undecided"], -r["attributed"]))


_SNIPPET_RADIUS = 90


def text_hits(lb: int, needle: str, db_path: str | None = None) -> list[str]:
    """Return description snippets around each occurrence of *needle*.

    Args:
        lb: LB number.
        needle: Text to locate (case-insensitive).
        db_path: Optional database path override.

    Returns:
        Up to five ``…snippet…`` strings.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT description FROM entries WHERE lb_number = ?", (lb,)
    ).fetchone()
    text = (row["description"] if row else "") or ""
    out: list[str] = []
    for m in re.finditer(re.escape(needle), text, re.IGNORECASE):
        start = max(0, m.start() - _SNIPPET_RADIUS)
        out.append(text[start:m.end() + _SNIPPET_RADIUS].replace("\n", " ").strip())
        if len(out) >= 5:
            break
    return out
