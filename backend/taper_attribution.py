"""Taper attribution engine — Phase 1: schema seeding via Layer 0 (direct
extraction) and Layer 1 (same-source propagation).

See ``instructions/FABLE_TAPER_ATTRIBUTION.md`` for the design and
``instructions/SPEC_INTEGRATION_NOTES.md`` findings F2/F3/F5/F6, which amend
and override the spec where noted:

- F2: ``taper_attributions`` is USER-tier (recomputed locally, never exported).
  Curator decisions live in the MASTER-tier ``taper_confirmations`` table
  instead, which :func:`recompute` reads first every run.
- F3: evidence records share a common core ``{"kind": str, "detail": str}``
  plus optional extras (``via_lb``, ``fam_id``, ``score``). ``kind`` is free
  text, no CHECK constraint.
- F5: freshening ``entry_lineage`` (via ``tools/parse_lineage.py``) is the
  caller's responsibility — see ``tools/attribute_tapers.py``, which always
  refreshes lineage before calling :func:`recompute`.
- F6: the same-source graph traversal here is local to this module by design;
  it is intentionally NOT shared with the (differently-semantic) ranking
  spec's derived_from traversal.

Confidence tiers (spec §3):
    confirmed  — curator-approved (``taper_confirmations`` 'confirm' row), or
                 direct evidence from the entry's own text: an explicit
                 "Taper:" label, or a legendary/net-taper series code
                 (lta-ltz, nta-ntz).
    propagated — inherited from a confirmed (or already-propagated) node via
                 a same-source edge (recording_families / entry_lineage
                 same_as_lb / derived_from_lb), or a bare handle mention in an
                 entry's own description (weaker Layer-0 evidence — a mention
                 is not a taping claim).
    inferred   — vocabulary fingerprints (Layer 2). Out of scope for Phase 1;
                 no code here produces this tier yet.

Entry point is :func:`recompute`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict

from backend.db import (
    _EXPLICIT_TAPER_LABEL_RE,
    _KNOWN_TAPER_ALIASES,
    _NOT_TAPER,
    get_connection,
    get_write_queue,
    init_db,
)

log = logging.getLogger(__name__)

# Taper universe (locked decision): canonical values of _KNOWN_TAPER_ALIASES,
# excluding anything in _NOT_TAPER (e.g. dolphinsmile — an uploader/curator,
# not a taper; mentions of him are uploader credit, not taper evidence).
_TAPER_UNIVERSE: frozenset[str] = frozenset(_KNOWN_TAPER_ALIASES.values()) - _NOT_TAPER

# Legendary Taper (lta..ltz) / Net Taper (net taper a..z) series codes, in the
# canonical form _normalise_taper() produces. These are unambiguous formal
# designations, so Layer 0 always treats them as 'confirmed' regardless of
# whether an explicit "Taper:" label is also present.
_SERIES_CODE_RE = re.compile(r'^(?:lt[a-z]|net taper [a-z])$')

# Reverse index: canonical taper -> raw alias keys, used to find a snippet of
# description text around a bare handle mention for Layer-0 'mention' evidence.
_ALIAS_KEYS_BY_CANONICAL: dict[str, list[str]] = defaultdict(list)
for _key, _canonical in _KNOWN_TAPER_ALIASES.items():
    _ALIAS_KEYS_BY_CANONICAL[_canonical].append(_key)
# Longest keys first so multi-word phrases are preferred over short substrings.
for _canonical in _ALIAS_KEYS_BY_CANONICAL:
    _ALIAS_KEYS_BY_CANONICAL[_canonical].sort(key=len, reverse=True)


# ── Small helpers ─────────────────────────────────────────────────────────────

def _evidence(kind: str, detail: str, **extras) -> dict:
    """Build one evidence record: common core + optional non-None extras (F3)."""
    rec: dict = {"kind": kind, "detail": detail}
    for k, v in extras.items():
        if v is not None:
            rec[k] = v
    return rec


def _row(taper: str, tier: str, evidence: list[dict]) -> dict:
    """Build an in-memory attribution row (mirrors the taper_attributions columns)."""
    return {"taper": taper, "tier": tier, "conflict": 0, "evidence": evidence, "confirmed_at": None}


def _mention_snippet(description: str, canonical_taper: str, radius: int = 40) -> str | None:
    """Find a short context snippet around a bare mention of *canonical_taper*.

    Args:
        description: Entry description text.
        canonical_taper: Canonical taper name (a value in _KNOWN_TAPER_ALIASES).
        radius: Characters of context on each side of the match.

    Returns:
        A trimmed snippet, or None if no alias for this taper appears in the
        first 600 chars (the same window extract_taper_and_source scans).
    """
    window = (description or "")[:600]
    for key in _ALIAS_KEYS_BY_CANONICAL.get(canonical_taper, ()):
        pattern = re.compile(r'\b' + re.escape(key) + r'\b', re.IGNORECASE)
        m = pattern.search(window)
        if m:
            start = max(0, m.start() - radius)
            end = min(len(window), m.end() + radius)
            return re.sub(r'\s+', ' ', window[start:end]).strip()
    return None


class _DSU:
    """Minimal union-find with path compression, used for the strong-edge graph."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_taper_confirmations(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Return MASTER-tier curator decisions keyed by lb_number (locked decision, F2)."""
    rows = conn.execute(
        "SELECT lb_number, taper_normalised, action, decided_at FROM taper_confirmations"
    ).fetchall()
    return {row["lb_number"]: row for row in rows}


def _load_lineage_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every entry_lineage row joined to its entries.description."""
    return conn.execute(
        """SELECT el.lb_number, el.taper_name, el.taper_normalised,
                  el.same_as_lb, el.derived_from_lb, e.description
           FROM entry_lineage el
           LEFT JOIN entries e ON e.lb_number = el.lb_number"""
    ).fetchall()


def _load_families(conn: sqlite3.Connection) -> tuple[dict[str, list[int]], dict[str, bool]]:
    """Return (fam_id -> member lb_numbers, fam_id -> is_review_flagged)."""
    fam_members: dict[str, list[int]] = defaultdict(list)
    for row in conn.execute("SELECT lb_number, fam_id FROM recording_families"):
        fam_members[row["fam_id"]].append(row["lb_number"])
    fam_review: dict[str, bool] = {}
    for row in conn.execute("SELECT fam_id, review_flag FROM tapematch_family_meta"):
        fam_review[row["fam_id"]] = bool(row["review_flag"])
    return dict(fam_members), fam_review


def _build_adjacency(rows: list[sqlite3.Row]) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Build bidirectional same_as / derived_from adjacency from entry_lineage rows.

    Both edge types are treated as undirected for graph connectivity: taper
    spec §4.1 lists derived_from_lb as directed parent→child for the "child
    inherits parent's taper" rule, but since Layer 1 only ever propagates a
    single taper value that is already uncontested within its component (see
    _propagate_strong), undirected traversal reaches the identical fixed
    point — everyone in the component ends up with that one taper regardless
    of which direction the edge was declared in.
    """
    same_as_adj: dict[int, list[int]] = defaultdict(list)
    derived_from_adj: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        lb = row["lb_number"]
        for other in json.loads(row["same_as_lb"] or "[]"):
            if other == lb:
                continue
            same_as_adj[lb].append(other)
            same_as_adj[other].append(lb)
        for parent in json.loads(row["derived_from_lb"] or "[]"):
            if parent == lb:
                continue
            derived_from_adj[lb].append(parent)
            derived_from_adj[parent].append(lb)
    return dict(same_as_adj), dict(derived_from_adj)


# ── Layer 0 — direct extraction ────────────────────────────────────────────────

def _layer0_seed(rows: list[sqlite3.Row], universe: frozenset[str]) -> dict[int, dict]:
    """Seed attributions from entry_lineage.taper_normalised (spec §4.0).

    - Series code (lta-ltz, nta-ntz) → confirmed, kind='series_code'.
    - Explicit "Taper:" label in the description → confirmed, kind='explicit'.
    - Otherwise (a known handle appears somewhere in the text via a weaker
      extraction path) → propagated, kind='mention' (mentions are weaker
      evidence than an explicit label — "thanks to spot" != "taped by spot").
    """
    attrs: dict[int, dict] = {}
    for row in rows:
        taper_norm = row["taper_normalised"]
        if not taper_norm or taper_norm not in universe:
            continue
        lb = row["lb_number"]
        description = row["description"] or ""

        if _SERIES_CODE_RE.match(taper_norm):
            attrs[lb] = _row(taper_norm, "confirmed",
                              [_evidence("series_code", f"series code '{taper_norm}'")])
            continue

        if _EXPLICIT_TAPER_LABEL_RE.search(description[:600]):
            detail = f"explicit 'Taper:' label (parsed as {row['taper_name']!r})"
            attrs[lb] = _row(taper_norm, "confirmed", [_evidence("explicit", detail)])
            continue

        snippet = _mention_snippet(description, taper_norm)
        detail = f"bare mention of '{taper_norm}' in description"
        if snippet:
            detail += f": …{snippet}…"
        attrs[lb] = _row(taper_norm, "propagated", [_evidence("mention", detail)])

    return attrs


# ── taper_confirmations (MASTER, curator decisions) — locked decision, F2 ─────

def _apply_confirmations(
    attrs: dict[int, dict], confirmations: dict[int, sqlite3.Row]
) -> dict[int, str]:
    """Apply sticky 'confirm' rows in place; return {lb: rejected_taper} for 'reject' rows."""
    rejects: dict[int, str] = {}
    for lb, row in confirmations.items():
        action = row["action"]
        taper = row["taper_normalised"]
        if action == "confirm":
            attrs[lb] = {
                "taper": taper,
                "tier": "confirmed",
                "conflict": 0,
                "evidence": [_evidence("confirmation", "curator confirmed")],
                "confirmed_at": row["decided_at"],
            }
        elif action == "reject":
            rejects[lb] = taper
        else:
            log.warning(
                "taper_confirmations: unrecognised action %r for LB-%s (ignored)", action, lb
            )
    return rejects


def _apply_rejects(attrs: dict[int, dict], rejects: dict[int, str]) -> None:
    """Suppress (lb_number, taper_normalised) pairs a curator rejected, in place.

    Applies regardless of tier — a curator reject overrides Layer 0's own
    'confirmed' extraction just as much as a propagated guess (a 'confirm' and
    'reject' row can never coexist for the same lb_number since
    taper_confirmations' PK is lb_number alone, so this never fights a sticky
    confirmation for the same entry).
    """
    for lb, rejected_taper in rejects.items():
        row = attrs.get(lb)
        if row and row["taper"] == rejected_taper:
            del attrs[lb]


# ── Layer 1 — same-source propagation ──────────────────────────────────────────

def _mark_conflicts(attrs: dict[int, dict], members, candidates: list[tuple[int, str]]) -> None:
    """Mark every not-yet-attributed lb in *members* as conflict=1.

    *candidates* is a list of (source_lb, taper) pairs whose disagreement
    caused the conflict; all are recorded in evidence so a curator can
    adjudicate without reading code (spec §7 acceptance criterion).
    """
    if not candidates:
        return
    # Deterministic placeholder so re-runs are idempotent (spec §7): NOT NULL
    # taper_normalised needs *some* value even though the row is ambiguous.
    placeholder = sorted({t for _, t in candidates})[0]
    evidence = [
        _evidence("conflict", f"component candidate taper '{t}' via LB-{lb}", via_lb=lb)
        for lb, t in sorted(candidates)
    ]
    for lb in members:
        if lb in attrs:
            continue
        attrs[lb] = {"taper": placeholder, "tier": "propagated", "conflict": 1,
                      "evidence": list(evidence), "confirmed_at": None}


def _propagate_strong(
    attrs: dict[int, dict],
    fam_members: dict[str, list[int]],
    fam_review: dict[str, bool],
    same_as_adj: dict[int, list[int]],
    derived_from_adj: dict[int, list[int]],
) -> None:
    """Layer 1 over strong edges: family cliques (non review-flagged) + same_as + derived_from.

    Per component: exactly one confirmed taper -> flood-fill it (BFS) to every
    unattributed member, tier='propagated' (already-propagated nodes push too,
    per spec §4.2 — the BFS frontier includes them). Zero confirmed tapers ->
    no anchor, skip. Two+ confirmed tapers, or a confirmed taper contradicted
    by an existing (non-confirmed) attribution in the same component -> do not
    propagate into the contested region; mark unattributed members conflict=1
    and leave existing rows untouched (spec §4.2 Conflicts).
    """
    dsu = _DSU()
    lb_fam_strong: dict[int, str] = {}
    for fam_id, members in fam_members.items():
        if fam_review.get(fam_id, False) or len(members) < 2:
            continue
        for lb in members:
            lb_fam_strong[lb] = fam_id
        first = members[0]
        for m in members[1:]:
            dsu.union(first, m)
    for lb, others in same_as_adj.items():
        for other in others:
            dsu.union(lb, other)
    for lb, others in derived_from_adj.items():
        for other in others:
            dsu.union(lb, other)

    groups: dict[int, set[int]] = defaultdict(set)
    for lb in dsu.parent:
        groups[dsu.find(lb)].add(lb)

    for members in groups.values():
        confirmed = [(lb, attrs[lb]["taper"]) for lb in members
                     if lb in attrs and attrs[lb]["tier"] == "confirmed"]
        confirmed_tapers = {t for _, t in confirmed}

        if len(confirmed_tapers) >= 2:
            _mark_conflicts(attrs, members, confirmed)
            continue
        if not confirmed_tapers:
            continue

        target = next(iter(confirmed_tapers))
        disagreeing = [(lb, attrs[lb]["taper"]) for lb in members
                        if lb in attrs and attrs[lb]["tier"] != "confirmed"
                        and attrs[lb]["taper"] != target]
        if disagreeing:
            _mark_conflicts(attrs, members, confirmed + disagreeing)
            for lb, _t in disagreeing:
                attrs[lb]["conflict"] = 1
                attrs[lb]["evidence"].append(
                    _evidence("conflict", f"disagrees with component consensus taper '{target}'")
                )
            continue

        # Single uncontested taper for this component: BFS flood-fill.
        frontier = [lb for lb in members if lb in attrs]
        visited = set(frontier)
        while frontier:
            nxt: list[int] = []
            for u in frontier:
                for v in same_as_adj.get(u, ()):
                    if v in members and v not in visited:
                        visited.add(v)
                        if v not in attrs:
                            attrs[v] = _row(target, "propagated",
                                             [_evidence("same_as", f"same_as LB-{u}", via_lb=u)])
                            nxt.append(v)
                for v in derived_from_adj.get(u, ()):
                    if v in members and v not in visited:
                        visited.add(v)
                        if v not in attrs:
                            ev = _evidence("derived_from", f"derived_from LB-{u}", via_lb=u)
                            attrs[v] = _row(target, "propagated", [ev])
                            nxt.append(v)
                fam = lb_fam_strong.get(u)
                if fam:
                    for v in fam_members[fam]:
                        if v == u or v not in members or v in visited:
                            continue
                        visited.add(v)
                        if v not in attrs:
                            attrs[v] = _row(
                                target, "propagated",
                                [_evidence("family", f"same recording family as LB-{u}",
                                           via_lb=u, fam_id=fam)],
                            )
                            nxt.append(v)
            frontier = nxt


def _propagate_weak(
    attrs: dict[int, dict],
    fam_members: dict[str, list[int]],
    fam_review: dict[str, bool],
) -> None:
    """Second pass over weak (review-flagged) family edges only.

    Runs after _propagate_strong so strong resolutions already occupy `attrs`;
    weak edges only ever fill in nodes strong propagation left untouched, and
    a strong-vs-weak disagreement can't arise here because a node already
    attributed by the strong pass is skipped (spec §4.2: "weak edges lose to
    strong edges instead of raising a conflict").
    """
    for fam_id, members in fam_members.items():
        if not fam_review.get(fam_id, False):
            continue
        for lb in members:
            if lb in attrs:
                continue
            candidates: dict[str, int] = {}
            for other in members:
                if other == lb or other not in attrs:
                    continue
                candidates.setdefault(attrs[other]["taper"], other)
            if len(candidates) == 1:
                taper, src = next(iter(candidates.items()))
                attrs[lb] = _row(
                    taper, "propagated",
                    [_evidence("family", f"weak (review-flagged) same family as LB-{src}",
                               via_lb=src, fam_id=fam_id)],
                )
            elif len(candidates) >= 2:
                _mark_conflicts(attrs, [lb], [(src, t) for t, src in candidates.items()])


# ── Orchestration ──────────────────────────────────────────────────────────────

def _write_attributions(attrs: dict[int, dict], db_path: str | None = None) -> None:
    """Wholesale-replace taper_attributions with the freshly computed rows."""
    payload = [
        (lb, row["taper"], row["tier"], json.dumps(row["evidence"]),
         row["conflict"], row.get("confirmed_at"))
        for lb, row in attrs.items()
    ]

    def _do(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM taper_attributions")
        conn.executemany(
            """INSERT INTO taper_attributions
               (lb_number, taper_normalised, confidence, evidence_json, conflict, confirmed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            payload,
        )

    get_write_queue().execute(_do)


def _summarize(attrs: dict[int, dict]) -> dict:
    """Per-tier counts, conflict count, and top-10 tapers by entry count (spec §6)."""
    tier_counts: dict[str, int] = defaultdict(int)
    taper_counts: dict[str, int] = defaultdict(int)
    conflict_count = 0
    for row in attrs.values():
        tier_counts[row["tier"]] += 1
        taper_counts[row["taper"]] += 1
        if row["conflict"]:
            conflict_count += 1
    top_tapers = sorted(taper_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {
        "total": len(attrs),
        "confirmed": tier_counts.get("confirmed", 0),
        "propagated": tier_counts.get("propagated", 0),
        "inferred": tier_counts.get("inferred", 0),
        "conflict": conflict_count,
        "top_tapers": top_tapers,
    }


def recompute(db_path: str | None = None, dry_run: bool = False) -> dict:
    """Recompute taper_attributions wholesale: Layer 0 seeding + Layer 1 propagation.

    Assumes entry_lineage is already fresh — callers that need the F5
    freshness guarantee should run ``tools/parse_lineage.py``'s ``run()``
    first (``tools/attribute_tapers.py`` does this).

    Idempotent: re-running with unchanged entry_lineage / recording_families /
    taper_confirmations input produces an identical table (spec §7), because
    the whole table is deterministically rebuilt from that input every time —
    there is no dependency on the table's own prior contents.

    Args:
        db_path: Optional database path override.
        dry_run: Compute but do not write to the database.

    Returns:
        Summary dict: total, confirmed, propagated, inferred, conflict counts,
        and top_tapers (list of (taper, count) tuples, top 10).
    """
    init_db(db_path)  # idempotent; ensures taper_attributions/taper_confirmations exist
    conn = get_connection(db_path)

    confirmations = _load_taper_confirmations(conn)
    lineage_rows = _load_lineage_rows(conn)
    fam_members, fam_review = _load_families(conn)
    same_as_adj, derived_from_adj = _build_adjacency(lineage_rows)

    attrs = _layer0_seed(lineage_rows, _TAPER_UNIVERSE)
    rejects = _apply_confirmations(attrs, confirmations)
    _apply_rejects(attrs, rejects)

    _propagate_strong(attrs, fam_members, fam_review, same_as_adj, derived_from_adj)
    _propagate_weak(attrs, fam_members, fam_review)

    # Re-apply rejects: propagation may have re-derived exactly what a curator
    # rejected via a different edge (spec: reject suppresses that lb/taper
    # pair from recompute *output*, regardless of how it was (re-)derived).
    _apply_rejects(attrs, rejects)

    stats = _summarize(attrs)
    if not dry_run:
        _write_attributions(attrs, db_path)
    return stats
