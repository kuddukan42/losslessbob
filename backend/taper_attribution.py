"""Taper attribution engine — Phase 1: schema seeding via Layer 0 (direct
extraction) and Layer 1 (same-source propagation).

See ``instructions/complete/FABLE_TAPER_ATTRIBUTION.md`` for the design and
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
    inferred   — vocabulary fingerprints (Layer 2, ``backend.taper_fingerprints``).
                 Implemented but gated OFF in :func:`recompute` via
                 ``taper_fingerprints.LAYER2_ENABLED`` (2026-07-15 calibration
                 verdict — see that flag's comment); no rows are produced
                 until it is flipped after sign-off.

Entry point is :func:`recompute`.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from backend.db import (
    _EXPLICIT_TAPER_LABEL_RE,
    _KNOWN_TAPER_ALIASES,
    _TAPER_UNIVERSE,
    _normalise_taper,
    get_connection,
    get_write_queue,
    init_db,
)

log = logging.getLogger(__name__)

# NOTE: taper_fingerprints (Layer 2) is imported further down this file,
# after _DSU / _evidence / _row are defined, not here alongside the other
# imports. taper_fingerprints imports *this* module back (as a module object,
# not specific names) to reuse those helpers, so importing it before they
# exist would break at import time; see taper_fingerprints.py's module
# docstring for the full explanation.

# _TAPER_UNIVERSE (locked decision, defined in backend.db so the Library grid's
# is_known_taper() check shares the exact same set): canonical values of
# _KNOWN_TAPER_ALIASES, excluding anything in _NOT_TAPER (e.g. dolphinsmile —
# an uploader/curator, not a taper; mentions of him are uploader credit, not
# taper evidence).

# Legendary Taper (lta..ltz) / Net Taper (net taper a..z) series codes, in the
# canonical form _normalise_taper() produces. These are unambiguous formal
# designations, so Layer 0 always treats them as 'confirmed' regardless of
# whether an explicit "Taper:" label is also present.
_SERIES_CODE_RE = re.compile(r'^(?:lt[a-z]|net taper [a-z])$')

# Pulls the candidate taper name out of a conflict evidence record's detail
# string, e.g. "component candidate taper 'net taper j' via LB-6083" -> "net
# taper j". Used to classify a conflict as series-vs-series (§ list_attributions).
_CONFLICT_CAND_RE = re.compile(r"candidate taper '([^']+)'")

# Reverse index: canonical taper -> raw alias keys, used to find a snippet of
# description text around a bare handle mention for Layer-0 'mention' evidence.
_ALIAS_KEYS_BY_CANONICAL: dict[str, list[str]] = defaultdict(list)
for _key, _canonical in _KNOWN_TAPER_ALIASES.items():
    _ALIAS_KEYS_BY_CANONICAL[_canonical].append(_key)
# Longest keys first so multi-word phrases are preferred over short substrings.
for _canonical in _ALIAS_KEYS_BY_CANONICAL:
    _ALIAS_KEYS_BY_CANONICAL[_canonical].sort(key=len, reverse=True)


# ── Small helpers ─────────────────────────────────────────────────────────────

def _run_write(fn, db_path: str | None):
    """Route a write callable through the write queue, matching the BUG-246
    guard used elsewhere (song_index.py, setlist_fingerprint.py): the write
    queue singleton is first-caller-wins, so under pytest (each test its own
    temp DB) it may be bound to a different DB than *db_path*.
    """
    queue = get_write_queue()
    if db_path is not None and str(Path(db_path).resolve()) != str(Path(queue.db_path).resolve()):
        log.warning(
            "taper_attribution: write queue bound to %s but this write targets %s"
            " — writing directly", queue.db_path, db_path,
        )
        conn = get_connection(db_path)
        with conn:
            return fn(conn)
    return queue.execute(fn)


def _evidence(kind: str, detail: str, **extras) -> dict:
    """Build one evidence record: common core + optional non-None extras (F3)."""
    rec: dict = {"kind": kind, "detail": detail}
    for k, v in extras.items():
        if v is not None:
            rec[k] = v
    return rec


def _is_series_vs_series(taper_normalised: str, evidence: list[dict]) -> bool:
    """Whether a conflict pits only formal taper *series* against each other.

    Series-vs-series conflicts (e.g. ``net taper f`` vs ``net taper i``, ``ltg``
    vs ``net taper a``) are two *legitimate* tapers landing on one over-merged
    ``recording_families`` family — a TapeMatch family-split problem (TODO-234),
    not something the curator can resolve in the hand-review queue (rejecting
    either candidate discards a real taper). The mention-vs-mention conflicts are
    the genuine hand queue. Classification: the row's own taper plus every
    contesting candidate parsed from the conflict evidence all match
    :data:`_SERIES_CODE_RE`.

    Args:
        taper_normalised: The row's canonical taper (one candidate in the contest).
        evidence: Parsed evidence records; conflict details name the others.

    Returns:
        True if every candidate in the conflict is a series code.
    """
    candidates = {taper_normalised}
    for rec in evidence:
        if rec.get("kind") == "conflict":
            m = _CONFLICT_CAND_RE.search(rec.get("detail", ""))
            if m:
                candidates.add(m.group(1))
    return bool(candidates) and all(_SERIES_CODE_RE.match(c) for c in candidates)


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


# Layer 2 (vocabulary fingerprints, TODO-214). Placed here — after _DSU,
# _evidence, _row exist — rather than with the other top-of-file imports; see
# the NOTE near those imports.
from backend import taper_fingerprints  # noqa: E402

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

def _confirmed_row(taper: str, decided_at) -> dict:
    """Build the in-memory attrs entry for a sticky curator 'confirm' decision.

    Shared by the bulk :func:`recompute` pass (via :func:`_apply_confirmations`)
    and the Phase 2 confirm/reject API's :func:`confirm`, so both paths produce
    byte-identical evidence/tier shapes for the same decision.
    """
    return {
        "taper": taper,
        "tier": "confirmed",
        "conflict": 0,
        "evidence": [_evidence("confirmation", "curator confirmed")],
        "confirmed_at": decided_at,
    }


def _apply_confirmations(
    attrs: dict[int, dict], confirmations: dict[int, sqlite3.Row]
) -> tuple[dict[int, str], set[int]]:
    """Apply sticky 'confirm' rows in place; collect deferred suppressions.

    Returns:
        ``(rejects, unresolved)`` where *rejects* maps ``{lb: rejected_taper}``
        (a curator 'reject' of one taper) and *unresolved* is the set of lbs a
        curator marked 'unresolved' — a "can't determine" verdict that suppresses
        *any* taper for that lb (a genuine historical two-taper conflict with no
        ground truth; §_apply_unresolved). Both are applied after propagation so
        a re-derived attribution cannot resurrect them.
    """
    rejects: dict[int, str] = {}
    unresolved: set[int] = set()
    for lb, row in confirmations.items():
        action = row["action"]
        taper = row["taper_normalised"]
        if action == "confirm":
            attrs[lb] = _confirmed_row(taper, row["decided_at"])
        elif action == "reject":
            rejects[lb] = taper
        elif action == "unresolved":
            unresolved.add(lb)
        else:
            log.warning(
                "taper_confirmations: unrecognised action %r for LB-%s (ignored)", action, lb
            )
    return rejects, unresolved


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


def _apply_unresolved(attrs: dict[int, dict], unresolved: set[int]) -> None:
    """Drop any attribution for lbs a curator marked 'unresolved', in place.

    Unlike a reject (which suppresses one named taper), an 'unresolved' verdict
    means the curator judged the conflict undecidable — a genuine historical
    error where the same recording carries two different documented tapers and
    there is no ground truth to pick. The honest outcome is *no* attribution
    (no pill, per spec §3/§6) rather than a guessed one, so every taper is
    suppressed for the lb regardless of tier.
    """
    for lb in unresolved:
        attrs.pop(lb, None)


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
        # A member that disagrees with the single confirmed taper can only be a
        # bare *mention* here — Layer 0's sole non-'confirmed' tier (a passing
        # name-drop, the weakest evidence). Per spec §4.2 ("weak edges lose to
        # strong edges instead of raising a conflict"), a mention must never
        # contest a confirmed series-code/explicit taper: the strong evidence
        # wins silently. Demote such members to unattributed so the flood-fill
        # below re-assigns them `target` rather than flagging a conflict
        # (TODO-213 mention-downgrade, 2026-07-13). A genuine strong-vs-strong
        # disagreement is the len(confirmed_tapers) >= 2 case handled above.
        for lb in members:
            row = attrs.get(lb)
            if row and row["tier"] != "confirmed" and row["taper"] != target:
                del attrs[lb]

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

    _run_write(_do, db_path)


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


def _compute_layers01(
    conn: sqlite3.Connection,
) -> tuple[dict[int, dict], dict[str, list[int]], dict[int, list[int]], dict[int, list[int]],
           dict[int, str], set[int]]:
    """Run Layer 0 (direct extraction) + Layer 1 (same-source propagation).

    Factored out of :func:`recompute` so both it and
    ``tools/attribute_tapers.py --calibrate-fingerprints`` can obtain the
    exact intermediate state Layer 2 fingerprinting sees, without a full
    recompute-and-write. Behavior-identical refactor: :func:`recompute` calls
    this and then continues exactly as it did before.

    Args:
        conn: Database connection.

    Returns:
        ``(attrs, fam_members, same_as_adj, derived_from_adj, rejects,
        unresolved)`` — attrs after Layer 0 seeding, curator 'confirm' rows,
        one pass of reject suppression, and both propagation passes (strong
        then weak). Rejects have not yet been re-applied a second time and
        'unresolved' rows have not yet been stripped — :func:`recompute` does
        both after Layer 2 runs, so Layer 2's own poisoning check (which takes
        *unresolved* directly) sees the same state.
    """
    confirmations = _load_taper_confirmations(conn)
    lineage_rows = _load_lineage_rows(conn)
    fam_members, fam_review = _load_families(conn)
    same_as_adj, derived_from_adj = _build_adjacency(lineage_rows)

    attrs = _layer0_seed(lineage_rows, _TAPER_UNIVERSE)
    rejects, unresolved = _apply_confirmations(attrs, confirmations)
    _apply_rejects(attrs, rejects)

    _propagate_strong(attrs, fam_members, fam_review, same_as_adj, derived_from_adj)
    _propagate_weak(attrs, fam_members, fam_review)

    return attrs, fam_members, same_as_adj, derived_from_adj, rejects, unresolved


def recompute(db_path: str | None = None, dry_run: bool = False) -> dict:
    """Recompute taper_attributions wholesale: Layers 0 + 1 + 2.

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

    attrs, fam_members, same_as_adj, derived_from_adj, rejects, unresolved = (
        _compute_layers01(conn))

    # Layer 2 (vocabulary fingerprints, TODO-214): runs after Layer 1 and
    # before the reject/unresolved re-apply below, so curator decisions also
    # suppress inferred rows, and Layer 2 output can never feed back into
    # Layer 1 propagation (spec §4.3). Gated OFF pending precision sign-off —
    # see taper_fingerprints.LAYER2_ENABLED for the calibration verdict.
    if taper_fingerprints.LAYER2_ENABLED:
        taper_fingerprints.infer(attrs, conn, fam_members, same_as_adj,
                                 derived_from_adj, unresolved)

    # Re-apply rejects/unresolved: propagation (and now Layer 2) may have
    # re-derived exactly what a curator rejected (or marked undecidable) via a
    # different edge. A reject suppresses that lb/taper pair; an unresolved
    # suppresses every taper for the lb — both act on recompute *output*,
    # regardless of how it was (re-)derived.
    _apply_rejects(attrs, rejects)
    _apply_unresolved(attrs, unresolved)

    stats = _summarize(attrs)
    if not dry_run:
        _write_attributions(attrs, db_path)
    return stats


# ── Phase 2 curator API — confirm/reject (spec §5/§6, F2) ─────────────────────
#
# These apply a single curator decision immediately (no full recompute wait):
# they write the sticky taper_confirmations row exactly as a full recompute
# would read it, and reuse _confirmed_row / the same reject-matching rule as
# _apply_rejects so the taper_attributions row they leave behind is byte-
# identical to what the next full recompute() would produce for this lb.

def get_attribution_for_lb(lb: int, db_path: str | None = None) -> dict | None:
    """Return one LB's taper_attributions row, evidence_json parsed to a list.

    Args:
        lb: LB number to look up.
        db_path: Optional database path override.

    Returns:
        Dict with lb_number, taper_normalised, confidence, evidence (parsed
        list of {kind, detail, ...} records per F3), conflict, confirmed_at,
        computed_at — or None if this lb has no taper_attributions row.
    """
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT lb_number, taper_normalised, confidence, evidence_json, conflict,
                  confirmed_at, computed_at
           FROM taper_attributions WHERE lb_number=?""",
        (lb,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["evidence"] = json.loads(result.pop("evidence_json"))
    return result


def list_attributions(
    confidence: str | None = None,
    taper: str | None = None,
    conflict: bool | None = None,
    conflict_kind: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """Return taper_attributions rows matching optional filters (Phase 2 API, spec §5).

    Args:
        confidence: Restrict to this confidence tier ('confirmed' / 'propagated' /
            'inferred'), if given.
        taper: Restrict to this taper (raw or canonical; normalised via
            ``_normalise_taper`` before matching ``taper_normalised``), if given.
        conflict: True restricts to conflict=1 rows, False to conflict=0 rows,
            None applies no filter.
        conflict_kind: Sub-classify conflict rows (see :func:`_is_series_vs_series`).
            'mention' excludes series-vs-series conflicts (the genuine hand-review
            queue — the /taper-review page uses this); 'series' keeps only them
            (TODO-234 family-split leads). None applies no sub-filter. Ignored
            unless the row is a conflict.
        db_path: Optional database path override.

    Returns:
        List of dicts (lb_number, taper_normalised, confidence, evidence — parsed
        list of {kind, detail, ...} records per F3 — conflict, confirmed_at,
        computed_at), ordered by lb_number.
    """
    conn = get_connection(db_path)
    clauses: list[str] = []
    params: list = []
    if confidence:
        clauses.append("confidence = ?")
        params.append(confidence)
    if taper:
        clauses.append("taper_normalised = ?")
        params.append(_normalise_taper(taper) or taper)
    if conflict is not None:
        clauses.append("conflict = ?")
        params.append(1 if conflict else 0)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT lb_number, taper_normalised, confidence, evidence_json, conflict,
                   confirmed_at, computed_at
            FROM taper_attributions{where} ORDER BY lb_number""",
        params,
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["evidence"] = json.loads(d.pop("evidence_json"))
        if conflict_kind and d["conflict"]:
            is_series = _is_series_vs_series(d["taper_normalised"], d["evidence"])
            if conflict_kind == "mention" and is_series:
                continue
            if conflict_kind == "series" and not is_series:
                continue
        result.append(d)
    return result


def _resolve_taper(conn: sqlite3.Connection, lb: int, taper: str | None) -> str:
    """Normalise *taper* if given, else source it from lb's existing attribution row.

    Args:
        conn: A connection to read the existing taper_attributions row from.
        lb: LB number the decision applies to.
        taper: Raw or canonical taper name supplied by the caller, or None.

    Returns:
        Canonical taper_normalised value.

    Raises:
        ValueError: *taper* is None/blank and lb has no existing attribution
            row to source one from.
    """
    resolved = _normalise_taper(taper) if taper else None
    if not resolved:
        existing = conn.execute(
            "SELECT taper_normalised FROM taper_attributions WHERE lb_number=?", (lb,)
        ).fetchone()
        if existing is None:
            raise ValueError(
                f"LB-{lb} has no existing attribution and no taper was supplied"
            )
        resolved = existing["taper_normalised"]
    return resolved


def confirm(lb: int, taper: str | None = None, db_path: str | None = None) -> dict:
    """Curator-confirm one LB's taper attribution immediately (Phase 2 API).

    Writes a sticky 'confirm' row to the MASTER-tier taper_confirmations
    table, overwriting any prior decision for this lb (PK is lb_number), then
    immediately upserts taper_attributions to confidence='confirmed' using
    _confirmed_row's evidence shape — the same shape a full recompute()
    produces for a 'confirm' row via _apply_confirmations — so a later
    recompute is a no-op for this lb.

    Args:
        lb: LB number to confirm.
        taper: Raw or canonical taper name. Normalised via _normalise_taper.
            If omitted, taken from this lb's existing taper_attributions row.
        db_path: Optional database path override.

    Returns:
        The updated taper_attributions row (see get_attribution_for_lb).

    Raises:
        ValueError: No taper was supplied and no existing attribution row
            exists to source one from, or the resolved taper is not in the
            known-taper universe (_TAPER_UNIVERSE).
    """
    init_db(db_path)
    conn = get_connection(db_path)
    taper_norm = _resolve_taper(conn, lb, taper)
    if taper_norm not in _TAPER_UNIVERSE:
        raise ValueError(f"{taper_norm!r} is not in the known-taper universe")

    def _do(c: sqlite3.Connection) -> None:
        c.execute(
            """INSERT INTO taper_confirmations (lb_number, taper_normalised, action, decided_at)
               VALUES (?, ?, 'confirm', CURRENT_TIMESTAMP)
               ON CONFLICT(lb_number) DO UPDATE SET
                   taper_normalised = excluded.taper_normalised,
                   action = 'confirm',
                   decided_at = CURRENT_TIMESTAMP""",
            (lb, taper_norm),
        )
        decided_at = c.execute(
            "SELECT decided_at FROM taper_confirmations WHERE lb_number=?", (lb,)
        ).fetchone()["decided_at"]
        confirmed = _confirmed_row(taper_norm, decided_at)
        c.execute(
            """INSERT INTO taper_attributions
                   (lb_number, taper_normalised, confidence, evidence_json, conflict, confirmed_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(lb_number) DO UPDATE SET
                   taper_normalised = excluded.taper_normalised,
                   confidence = excluded.confidence,
                   evidence_json = excluded.evidence_json,
                   conflict = excluded.conflict,
                   confirmed_at = excluded.confirmed_at""",
            (lb, taper_norm, confirmed["tier"], json.dumps(confirmed["evidence"]),
             confirmed["conflict"], confirmed["confirmed_at"]),
        )

    _run_write(_do, db_path)
    return get_attribution_for_lb(lb, db_path)


def reject(lb: int, taper: str | None = None, db_path: str | None = None) -> dict | None:
    """Curator-reject one LB's taper attribution immediately (Phase 2 API).

    Writes a sticky 'reject' row to the MASTER-tier taper_confirmations
    table, overwriting any prior decision for this lb, and deletes the
    taper_attributions row for (lb, taper_norm) if it currently matches —
    the same same-pair check _apply_rejects uses during a full recompute, so
    rejecting a taper this entry doesn't currently carry still records the
    suppression (for the next recompute) without touching an unrelated,
    currently-correct attribution.

    Args:
        lb: LB number to reject.
        taper: Raw or canonical taper name being rejected. Normalised via
            _normalise_taper. If omitted, taken from this lb's existing
            taper_attributions row.
        db_path: Optional database path override.

    Returns:
        The updated taper_attributions row, or None if it was deleted (or
        never existed).

    Raises:
        ValueError: No taper was supplied and no existing attribution row
            exists to source one from.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    taper_norm = _resolve_taper(conn, lb, taper)

    def _do(c: sqlite3.Connection) -> None:
        c.execute(
            """INSERT INTO taper_confirmations (lb_number, taper_normalised, action, decided_at)
               VALUES (?, ?, 'reject', CURRENT_TIMESTAMP)
               ON CONFLICT(lb_number) DO UPDATE SET
                   taper_normalised = excluded.taper_normalised,
                   action = 'reject',
                   decided_at = CURRENT_TIMESTAMP""",
            (lb, taper_norm),
        )
        c.execute(
            "DELETE FROM taper_attributions WHERE lb_number=? AND taper_normalised=?",
            (lb, taper_norm),
        )

    _run_write(_do, db_path)
    return get_attribution_for_lb(lb, db_path)


def mark_unresolved(lb: int, db_path: str | None = None) -> dict | None:
    """Curator verdict: this taper conflict is undecidable — attribute nothing.

    For a genuine historical conflict (the same recording documented with two
    different tapers), there is no ground truth to pick, so the honest outcome is
    no attribution at all rather than a guessed pill. Writes a sticky
    'unresolved' row to the MASTER-tier ``taper_confirmations`` table (overwriting
    any prior decision for this lb) and deletes the current ``taper_attributions``
    row immediately, so the entry leaves both the review queue and the display
    without ever showing a taper. Future ``recompute`` runs stay suppressed via
    :func:`_apply_unresolved`. Reversible: a later confirm/reject overwrites the
    'unresolved' row (``taper_confirmations`` PK is lb_number alone).

    Args:
        lb: LB number whose conflict is being parked as undecidable.
        db_path: Optional database path override.

    Returns:
        The updated ``taper_attributions`` row (None, since it is deleted).
    """
    init_db(db_path)
    conn = get_connection(db_path)
    # Record the contested taper for provenance (which value was on display when
    # parked); the apply logic suppresses every taper regardless of it.
    existing = conn.execute(
        "SELECT taper_normalised FROM taper_attributions WHERE lb_number=?", (lb,)
    ).fetchone()
    taper_norm = existing["taper_normalised"] if existing else "?"

    def _do(c: sqlite3.Connection) -> None:
        c.execute(
            """INSERT INTO taper_confirmations (lb_number, taper_normalised, action, decided_at)
               VALUES (?, ?, 'unresolved', CURRENT_TIMESTAMP)
               ON CONFLICT(lb_number) DO UPDATE SET
                   taper_normalised = excluded.taper_normalised,
                   action = 'unresolved',
                   decided_at = CURRENT_TIMESTAMP""",
            (lb, taper_norm),
        )
        c.execute("DELETE FROM taper_attributions WHERE lb_number=?", (lb,))

    _run_write(_do, db_path)
    return get_attribution_for_lb(lb, db_path)
