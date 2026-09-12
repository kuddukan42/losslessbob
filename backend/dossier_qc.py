"""Per-dossier QC gate (TODO-342 dossier redesign, Phase 5, C28; plan lines 794-822).

:func:`run_gate` is called once at the end of :func:`backend.dossier.build_dossier`,
after :func:`backend.dossier_anchors.build_view` has filled ``dossier["view"]``. It
runs checks G1-G8 (G9's lint is a separate pair of pure functions -- see below),
mutates ``dossier["view"]`` in place to withhold anything a check disqualifies, and
returns the ``dossier["qc"]`` dict:

``{checks_run, passed, withheld: [{key, rule}], refused, reasons, notices,
input_fingerprint}``

A gate failure never raises out of :func:`run_gate` -- an internal exception is
logged and the returned ``qc`` reports ``passed=False`` with a reason, exactly like
:func:`build_view`'s own safety net (spec S:1).

Checks implemented:

- **G1 identity**: refuses when the date resolves to no Olof event, or
  :func:`backend.qc.corroborate.venue_check` finds >=1 source with a venue name but
  none of them agree with Olof on venue *or* city. tj decision (2026-09-11, plan
  line 186): venue-or-city agreement with >=1 of setlist.fm/bobdylan_shows passes; a
  city-only match adds a venue-name notice instead of failing. A date where no
  comparable source has any venue data at all ("unavailable") passes with a notice.
- **G2 source-show fit**: already enforced by C27's ``source[].group``
  classification -- this just asserts every visible source row carries a ``group``
  Field, it adds no new behaviour.
- **G3 provenance**: every Field whose confidence isn't ``unavailable`` must carry a
  non-``None`` source; and no anchor's ``derived_from`` may cycle back to an anchor
  key that depends on it. Both conditions are true by construction of every
  :func:`backend.dossier_anchors.build_field` call site today, so this mostly
  guards against a future bug -- a violation withholds the offending Field (via
  :meth:`_Gate.withhold_field`, so it shows up in ``prov.withheld[]`` too).
- **G4 quarantine**: withholds specific anchors sourced from a row with an
  open/confirmed *error* finding, via :data:`_RULE_ANCHOR_MAP` -- a per-(entity
  kind, rule id) table, not a blanket "withhold everything" per entity. A rule id
  this gate doesn't recognise for its entity kind logs a warning and withholds
  nothing (new rules need a row added here, not a silent over-withhold or a silent
  no-op). ``("lb", "R-S1")`` is deliberately excluded -- G6 owns table/per-LB
  staleness, and R-S1 also happens to log under entity kind ``lb``.
- **G5 invariants**: city-history row sum equals ``venue.city_total``;
  ``sources.tape_count``'s stated group count is <= ``sources.count``; the gated
  premiere-titles list length equals ``stats.premiere_count``; the pick's ledger
  evidence points sum to ``ledger.total`` within 0.05; the ledger's
  ``audio_quality`` evidence entry's stated score matches the pick's live scanned
  score (:func:`_run_g5_invariants`'s docstring has the exact substitution --
  ``pick.scan_grade`` is a letter with no numeric form in this codebase, so the
  comparison uses the raw score that grade is derived from). **Deferred** (no
  anchor carries the input): the spec's "runtime split sum" invariant.
- **G6 freshness**: an open/confirmed ``R-S1`` table-level finding on
  ``show_picks`` withholds every ``pick.*``/``ledger.*``/``verdict.*`` anchor and
  each row's ``source[].rank``/``family[].confidence``; one on
  ``song_performances`` withholds ``stats.premiere_count``/``stats.premiere_titles``
  and every ``song[].premiere``/``song[].gap`` row. A per-LB ``R-S1`` finding
  withholds that source's ``source[].scan_grade`` (and ``pick.scan_grade`` when
  it's the pick). Any of the above adds an "analysis stale" notice.
- **G7 claims**: after G3-G6 withholding, drops a claim whose exact (anchor, row)
  instance was withheld, *or* whose comparison set includes an LB whose relevant
  axis sub was withheld (a superlative/comparison over an incomplete scope isn't
  trustworthy even though the withheld LB itself isn't the claim's subject --
  :func:`_claim_touches_withheld` works out each claim kind's comparison set from
  :mod:`backend.dossier_claims`'s own shape, see its docstring for exactly how).
  ``verdict.why``/``context.chronicle`` are rebuilt from the survivors, never left
  stale.
- **G8 channel**: for ``channel == "public"``, refuses if a private LB's data
  leaked anywhere into the view or a surviving claim (rows, claim slots, and claim
  values are all scanned for an ``LB-NNNNN`` string naming a private source), or if
  a claim that survived G7 still touches a withheld/disputed source (a backstop --
  G7 should have already dropped it; this only fires on a G7 bug). Dropping a
  claim is G7's job, not a reason to refuse the whole page -- G8 does not refuse
  merely because G7 dropped something.
- **G9 lint**: :func:`lint_l1` and :func:`lint_data_lb` are pure functions over
  rendered HTML; :func:`run_gate` does not call them (C29 hasn't written the
  ``data-lb``/``data-claim`` template yet). The ``/api/dossier/html`` route runs
  them post-render, only when the rendered HTML actually contains ``data-lb=``,
  and only logs violations.

``input_fingerprint`` is a sha256 over: the primary Olof event's page's
``olof_pages.parsed_at`` (None if there's no event); every quarantine/staleness
finding id and status this gate actually consulted (G4 + G6), sorted; and, when a
verdict pick exists, its ``show_picks.computed_at`` timestamp. It changes exactly
when a subsequent run of this gate could plausibly compute something different.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from typing import TypedDict

from backend.dossier_anchors import ANCHORS, Field, build_fallback_field, build_field

log = logging.getLogger(__name__)

_LB_RE = re.compile(r"LB-(\d{5})")

# ---------------------------------------------------------------------------
# Withholding
# ---------------------------------------------------------------------------


class WithheldEntry(TypedDict):
    """One ``prov.withheld[]`` row."""

    key: str
    rule: str


class _Gate:
    """Mutable state threaded through one :func:`run_gate` call."""

    def __init__(self, view: dict, conn: sqlite3.Connection) -> None:
        self.view = view
        self.conn = conn
        self.withheld: list[WithheldEntry] = []
        # Precise (anchor_key, row_identifier) instances withheld, for G7's use.
        # row_identifier is None for a scalar anchor.
        self.withheld_instances: set[tuple[str, object]] = set()
        # (row sub, lb) pairs withheld on a source row, e.g. ("scan_grade", 101) --
        # what a source-axis superlative/comparison claim's scope check needs.
        self.withheld_source_subs: set[tuple[str, int]] = set()
        self.notices: list[str] = []
        self.reasons: list[str] = []
        self.consulted_findings: list[tuple[int, str]] = []  # (finding id, status)

    def withhold_field(self, key: str, rule: str) -> None:
        anchor = ANCHORS.get(key)
        if anchor is None or key not in self.view["fields"]:
            return
        f = build_fallback_field(anchor)
        f["confidence"] = "withheld"
        self.view["fields"][key] = f
        self.withheld.append(WithheldEntry(key=key, rule=rule))
        self.withheld_instances.add((key, None))

    def withhold_row(self, prefix: str, row: dict, sub: str, rule: str,
                      row_id: object) -> None:
        key = f"{prefix}[].{sub}"
        anchor = ANCHORS.get(key)
        if anchor is None or sub not in row:
            return
        f = build_fallback_field(anchor)
        f["confidence"] = "withheld"
        row[sub] = f
        self.withheld.append(WithheldEntry(key=key, rule=rule))
        self.withheld_instances.add((key, row_id))
        if prefix == "source" and isinstance(row_id, int):
            self.withheld_source_subs.add((sub, row_id))

    def withhold_all_rows(self, prefix: str, sub: str, rule: str,
                           id_field: str = "position") -> None:
        """:meth:`withhold_row` applied to every row of *prefix* (event-wide quarantine)."""
        for row in self.view["rows"].get(prefix, []):
            row_id = row[id_field]["value"] if id_field in row else None
            self.withhold_row(prefix, row, sub, rule, row_id)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _quarantine_details_batch(
    conn: sqlite3.Connection, entity_kind: str, entity_keys: list[str],
) -> dict[str, list[tuple[str, int, str]]]:
    """One query: every open/confirmed error finding for *entity_keys* of *entity_kind*.

    Args:
        conn: Open SQLite connection.
        entity_kind: Entity kind shared by all keys.
        entity_keys: Entity keys to look up.

    Returns:
        ``{entity_key: [(rule_id, finding_id, status), ...]}``, keys with no hit omitted.
    """
    if not entity_keys or not _table_exists(conn, "qc_findings"):
        return {}
    placeholders = ",".join("?" for _ in entity_keys)
    rows = conn.execute(
        f"SELECT entity_key, rule_id, id, status FROM qc_findings WHERE entity_kind=?"
        f" AND entity_key IN ({placeholders})"
        " AND severity='error' AND status IN ('open','confirmed')",
        (entity_kind, *entity_keys),
    ).fetchall()
    out: dict[str, list[tuple[str, int, str]]] = {}
    for r in rows:
        out.setdefault(r["entity_key"], []).append((r["rule_id"], r["id"], r["status"]))
    return out


def _lb_of(field: Field | None) -> int | None:
    if not field or not field.get("value"):
        return None
    value = field["value"]
    if isinstance(value, str) and value.startswith("LB-"):
        try:
            return int(value[3:])
        except ValueError:
            return None
    return None


def _eligible_primary_lbs(view: dict) -> set[int]:
    """Every visible source LB whose ``source[].group`` is ``"primary"``."""
    out: set[int] = set()
    for row in view["rows"].get("source", []):
        if not row.get("lb_id") or not row["lb_id"]["value"]:
            continue
        group = row.get("group")
        if group and group["value"] == "primary":
            out.add(int(row["lb_id"]["value"][3:]))
    return out


# ---------------------------------------------------------------------------
# G1 identity
# ---------------------------------------------------------------------------


def _run_g1_identity(gate: _Gate, date_iso: str, event_id: int | None) -> None:
    from backend.qc.corroborate import places_agree_loose, venue_check

    if event_id is None:
        gate.reasons.append("G1: no Olof event resolved for this date")
        return

    try:
        vc = venue_check(gate.conn, date_iso)
    except sqlite3.OperationalError as exc:
        log.debug("dossier_qc: G1 venue_check degraded (%s)", exc)
        gate.notices.append("venue identity unavailable (venue_check degraded)")
        return

    comparable = [m for m in vc["sources"].values()
                  if m is not None and (m["venue_agrees"] is not None
                                         or m["city_agrees"] is not None)]
    if not comparable:
        gate.notices.append("venue identity unavailable (no corroborating source)")
        return

    # Exact fold first; places_agree_loose absorbs spelling variants ("Stadio Communale" /
    # "Stadio Comunale", "San Remo" / "Sanremo") that exact equality refused 22 of 26 times.
    venue_agrees_any = any(
        m["venue_agrees"] or places_agree_loose(vc["olof_venue"], m["venue"])
        for m in comparable)
    city_agrees_any = any(
        m["city_agrees"] or places_agree_loose(vc["olof_city"], m["city"])
        for m in comparable)
    if venue_agrees_any:
        return
    if city_agrees_any:
        gate.notices.append(
            "venue name unconfirmed -- city agrees with a source, venue name does not")
        return
    gate.reasons.append(
        "G1: sources have a venue for this date but none agree with Olof on venue or city")


# ---------------------------------------------------------------------------
# G2 (assert only)
# ---------------------------------------------------------------------------


def _run_g2_assert(gate: _Gate) -> None:
    for row in gate.view["rows"].get("source", []):
        if "group" not in row:
            log.warning("dossier_qc: G2 -- a source row has no 'group' Field (C27 regression?)")


# ---------------------------------------------------------------------------
# G3 provenance
# ---------------------------------------------------------------------------


def _iter_all_fields(view: dict):
    """Yield ``(key, field)`` for every scalar Field and ``(prefix[].sub, field)`` row Field."""
    for key, f in list(view["fields"].items()):
        yield key, f
    for prefix, rows in view.get("rows", {}).items():
        for row in rows:
            for sub, f in list(row.items()):
                yield f"{prefix}[].{sub}", f


def _run_g3_provenance(gate: _Gate) -> None:
    view = gate.view
    for key, f in _iter_all_fields(view):
        if f["confidence"] != "unavailable" and f["source"] is None:
            log.warning("dossier_qc: G3 -- %s has confidence %r but no source; withholding",
                        key, f["confidence"])
            if "[]." in key:
                prefix, sub = key.split("[].", 1)
                for row in view["rows"].get(prefix, []):
                    if row.get(sub) is f:
                        row_id = row.get("position", row.get("lb_id", row.get("id")))
                        row_id = row_id["value"] if row_id else None
                        gate.withhold_row(prefix, row, sub, "G3", row_id)
                        break
            else:
                gate.withhold_field(key, "G3")

    # derived_from cycle check: only entries that are themselves anchor keys count.
    graph: dict[str, set[str]] = {
        key: {d for d in f["derived_from"] if d in ANCHORS} for key, f in _iter_all_fields(view)
    }

    def _has_cycle(start: str) -> bool:
        stack, visited = [start], set()
        while stack:
            node = stack.pop()
            if node == start and node in visited:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(graph.get(node, ()))
        return False

    for key in list(graph):
        if key in view["fields"] and _has_cycle(key):
            log.warning("dossier_qc: G3 -- derived_from cycle involving %s; withholding", key)
            gate.withhold_field(key, "G3")


# ---------------------------------------------------------------------------
# G4 quarantine -- one small anchor list per (entity kind, rule id).
# ---------------------------------------------------------------------------

# olof_event: a truncated (R-O1) or disputed (R-O4) setlist only discredits the
# setlist-derived facts -- not the show's tour/venue/header identity, and not
# show.setlist_confidence, which is D-09's own (differently-sourced) verdict that
# tells the reader the setlist may be short.
_OLOF_EVENT_RULE_SCALARS: dict[str, tuple[str, ...]] = {
    "R-O1": ("setlist.count", "stats.rotation", "stats.rotation_rank",
             "stats.premiere_count", "stats.premiere_titles"),
    "R-O4": ("setlist.count", "stats.rotation", "stats.rotation_rank",
             "stats.premiere_count", "stats.premiere_titles"),
}
# Same two rules also withhold every song row's premiere/gap badge and every
# broadcast-set label (both read specific song positions off a setlist that may
# be short or reordered).
_OLOF_EVENT_RULE_SONG_SUBS: dict[str, tuple[str, ...]] = {
    "R-O1": ("premiere", "gap"), "R-O4": ("premiere", "gap"),
}
_OLOF_EVENT_RULE_SET_SUBS: dict[str, tuple[str, ...]] = {
    "R-O1": ("label",), "R-O4": ("label",),
}

# venue: R-G1 is a geocode/name mismatch -- it discredits the map, not the venue
# name/city text itself (those come from show fields, not venue_geocoded).
_VENUE_RULE_SCALARS: dict[str, tuple[str, ...]] = {
    "R-G1": ("venue.coords", "venue.map"),
}

# olof_song: a date/stat-shaped annotation (R-O3) taints the parser output riding
# alongside the title (writers/instruments come from the same annotation field;
# bobtalk is anchored per-position) -- not the title or position themselves.
_OLOF_SONG_RULE_SUBS: dict[str, tuple[str, ...]] = {
    "R-O3": ("bobtalk", "writers", "instruments[]"),
}

# lb: a taper-attribution rule only discredits the taper credit.
_LB_RULE_SUBS: dict[str, tuple[str, ...]] = {
    "R-T1": ("taper",), "R-T2": ("taper",), "R-T3": ("taper",),
}
# R-S1 also files under entity_kind 'lb' (per-LB staleness) but is G6's job.
_LB_RULES_OWNED_ELSEWHERE = frozenset({"R-S1"})

# entry: R-E2 (tracklist doesn't fit the dated show) discredits everything this
# source states about itself -- it may be the wrong recording entirely.
_ENTRY_RULE_SUBS: dict[str, tuple[str, ...]] = {
    "R-E2": ("taper", "generation", "medium", "completeness", "type", "scan_grade",
             "lb_rating", "runtime", "resolution", "character", "flags[]", "lineage",
             "curated_in[]", "rank"),
}

_PICK_SCALAR_PREFIX = "pick."
# Rules that, when they hit the pick's own LB, also withhold the taper- or
# whole-source-scoped pick.* anchors (pick.lb_id itself is kept -- it's the
# identity pointer, not a sourced fact).
_LB_RULE_PICK_SCALARS: dict[str, tuple[str, ...]] = {
    "R-T1": ("pick.taper.name", "pick.taper.confidence"),
    "R-T2": ("pick.taper.name", "pick.taper.confidence"),
    "R-T3": ("pick.taper.name", "pick.taper.confidence"),
}
_ENTRY_RULE_PICK_ALL = frozenset({"R-E2"})


def _withhold_pick_scalars(gate: _Gate, keys: tuple[str, ...], rule: str) -> None:
    for key in keys:
        gate.withhold_field(key, rule)


def _run_g4_olof_event(gate: _Gate, event_id: int | None) -> None:
    if event_id is None:
        return
    hits = _quarantine_details_batch(gate.conn, "olof_event", [str(event_id)])
    for rule_id, fid, status in hits.get(str(event_id), []):
        gate.consulted_findings.append((fid, status))
        scalars = _OLOF_EVENT_RULE_SCALARS.get(rule_id)
        if scalars is None:
            log.warning("dossier_qc: G4 -- unrecognised error rule %r for olof_event", rule_id)
            continue
        for key in scalars:
            gate.withhold_field(key, rule_id)
        for sub in _OLOF_EVENT_RULE_SONG_SUBS.get(rule_id, ()):
            gate.withhold_all_rows("song", sub, rule_id, id_field="position")
        for sub in _OLOF_EVENT_RULE_SET_SUBS.get(rule_id, ()):
            gate.withhold_all_rows("set", sub, rule_id, id_field="label")


def _run_g4_venue(gate: _Gate, show_venue: str | None, show_city: str | None) -> None:
    from backend.venue_gazetteer import _norm_city, _norm_venue

    if not show_venue:
        return
    vkey = f"{_norm_venue(show_venue)}:{_norm_city(show_city or '')}"
    hits = _quarantine_details_batch(gate.conn, "venue", [vkey])
    for rule_id, fid, status in hits.get(vkey, []):
        gate.consulted_findings.append((fid, status))
        scalars = _VENUE_RULE_SCALARS.get(rule_id)
        if scalars is None:
            log.warning("dossier_qc: G4 -- unrecognised error rule %r for venue", rule_id)
            continue
        for key in scalars:
            gate.withhold_field(key, rule_id)


def _run_g4_olof_song(gate: _Gate, event_id: int | None) -> None:
    song_rows = gate.view["rows"].get("song", [])
    if event_id is None or not song_rows:
        return
    keys = [f"{event_id}:{r['position']['value']}" for r in song_rows if "position" in r]
    hits = _quarantine_details_batch(gate.conn, "olof_song", keys)
    if not hits:
        return
    by_pos = {row["position"]["value"]: row for row in song_rows if "position" in row}
    for entity_key, findings in hits.items():
        pos = int(entity_key.split(":", 1)[1])
        row = by_pos.get(pos)
        if row is None:
            continue
        for rule_id, fid, status in findings:
            gate.consulted_findings.append((fid, status))
            subs = _OLOF_SONG_RULE_SUBS.get(rule_id)
            if subs is None:
                log.warning("dossier_qc: G4 -- unrecognised error rule %r for olof_song", rule_id)
                continue
            for sub in subs:
                gate.withhold_row("song", row, sub, rule_id, pos)


def _run_g4_sources(gate: _Gate, pick_lb: int | None) -> None:
    source_rows = gate.view["rows"].get("source", [])
    lb_keys = [str(int(r["lb_id"]["value"][3:])) for r in source_rows
               if r.get("lb_id") and r["lb_id"]["value"]]
    if not lb_keys:
        return
    by_lb = {int(r["lb_id"]["value"][3:]): r for r in source_rows
              if r.get("lb_id") and r["lb_id"]["value"]}

    lb_hits = _quarantine_details_batch(gate.conn, "lb", lb_keys)
    for entity_key, findings in lb_hits.items():
        lb = int(entity_key)
        row = by_lb.get(lb)
        if row is None:
            continue
        for rule_id, fid, status in findings:
            if rule_id in _LB_RULES_OWNED_ELSEWHERE:
                continue  # G6's job (R-S1)
            gate.consulted_findings.append((fid, status))
            subs = _LB_RULE_SUBS.get(rule_id)
            if subs is None:
                log.warning("dossier_qc: G4 -- unrecognised error rule %r for lb", rule_id)
                continue
            for sub in subs:
                gate.withhold_row("source", row, sub, rule_id, lb)
            if lb == pick_lb:
                _withhold_pick_scalars(gate, _LB_RULE_PICK_SCALARS.get(rule_id, ()), rule_id)

    entry_hits = _quarantine_details_batch(gate.conn, "entry", lb_keys)
    for entity_key, findings in entry_hits.items():
        lb = int(entity_key)
        row = by_lb.get(lb)
        if row is None:
            continue
        for rule_id, fid, status in findings:
            gate.consulted_findings.append((fid, status))
            subs = _ENTRY_RULE_SUBS.get(rule_id)
            if subs is None:
                log.warning("dossier_qc: G4 -- unrecognised error rule %r for entry", rule_id)
                continue
            for sub in subs:
                gate.withhold_row("source", row, sub, rule_id, lb)
            if lb == pick_lb and rule_id in _ENTRY_RULE_PICK_ALL:
                for key in list(gate.view["fields"]):
                    if key.startswith(_PICK_SCALAR_PREFIX) and key != "pick.lb_id":
                        gate.withhold_field(key, rule_id)


def _run_g4_quarantine(gate: _Gate, event_id: int | None, show_venue: str | None,
                        show_city: str | None, pick_lb: int | None) -> None:
    _run_g4_olof_event(gate, event_id)
    _run_g4_venue(gate, show_venue, show_city)
    _run_g4_olof_song(gate, event_id)
    _run_g4_sources(gate, pick_lb)


# ---------------------------------------------------------------------------
# G5 invariants
# ---------------------------------------------------------------------------

_AUDIO_QUALITY_SCORE_RE = re.compile(r"scanned quality (\d+(?:\.\d+)?)/100")


def _run_g5_invariants(gate: _Gate, d1: dict, pick_lb: int | None) -> None:
    fields = gate.view["fields"]

    # City-history sum.
    city_total = fields.get("venue.city_total")
    city_rows = fields.get("city_history[]")
    if city_total and city_total["source"] and city_rows and city_rows["source"]:
        rows_sum = sum(r.get("count", 0) for r in city_rows["value"] if isinstance(r, dict))
        if rows_sum and rows_sum != city_total["value"]:
            gate.withhold_field("venue.city_total", "G5-city-history")
            gate.withhold_field("city_history[]", "G5-city-history")

    # Tape groups <= sources.
    tape = fields.get("sources.tape_count")
    count = fields.get("sources.count")
    if tape and tape["source"] and count and count["source"]:
        m = re.match(r"(\d+)", str(tape["value"]))
        if m and int(m.group(1)) > count["value"]:
            gate.withhold_field("sources.tape_count", "G5-tape-count")

    # Premiere badge count == stats.premiere_count.
    premiere_count = fields.get("stats.premiere_count")
    premiere_titles = fields.get("stats.premiere_titles")
    if (premiere_count and premiere_count["source"] and premiere_titles
            and premiere_titles["source"] and isinstance(premiere_titles["value"], list)):
        if len(premiere_titles["value"]) != premiere_count["value"]:
            gate.withhold_field("stats.premiere_titles", "G5-premiere-count")

    # Ledger sum ~= ledger.total (+-0.05).
    ledger = fields.get("ledger[]")
    total = fields.get("ledger.total")
    if ledger and ledger["source"] and total and total["source"] and isinstance(
            ledger["value"], list):
        evidence_sum = sum(e.get("points", 0) or 0 for e in ledger["value"]
                            if isinstance(e, dict))
        if abs(evidence_sum - total["value"]) > 0.05:
            gate.withhold_field("ledger[]", "G5-ledger-sum")
            gate.withhold_field("ledger.total", "G5-ledger-sum")

        # Ledger audio evidence vs. the pick's live scanned score. pick.scan_grade
        # is a letter (abs_grade) with no numeric form anywhere in this codebase,
        # so this compares the evidence's stated number against the same pick's
        # live abs_score (backend.dossier._load_quality's "score") -- the number
        # abs_grade is itself derived from, and the only "displayed scan score"
        # this gate can actually read.
        audio_entry = next(
            (e for e in ledger["value"]
             if isinstance(e, dict) and e.get("kind") == "audio_quality"),
            None)
        if audio_entry and pick_lb is not None:
            m2 = _AUDIO_QUALITY_SCORE_RE.search(audio_entry.get("detail", ""))
            live_score = None
            for bucket in d1.get("sources", []):
                for member in bucket["members"]:
                    if member.get("lb") == f"LB-{pick_lb:05d}":
                        live_score = (member.get("quality") or {}).get("score")
            if m2 and live_score is not None and abs(float(m2.group(1)) - live_score) > 0.5:
                gate.withhold_field("ledger[]", "G5-ledger-audio")
                gate.withhold_field("ledger.total", "G5-ledger-audio")


# ---------------------------------------------------------------------------
# G6 freshness
# ---------------------------------------------------------------------------

_SHOW_PICKS_DEPENDENTS = (
    "pick.lb_id", "pick.url", "pick.taper.name", "pick.taper.confidence", "pick.medium",
    "pick.type", "pick.lb_rating", "pick.scan_grade", "pick.lineage_short", "pick.resolution",
    "pick.runtime", "pick.generation", "pick.completeness", "pick.curated_in[]",
    "verdict.why", "verdict.vs_runner_up", "verdict.alternates[]",
    "ledger[]", "ledger.total",
)
_SONG_PERFORMANCES_DEPENDENTS = ("stats.premiere_count", "stats.premiere_titles")


def _run_g6_freshness(gate: _Gate, pick_lb: int | None) -> None:
    if not _table_exists(gate.conn, "qc_findings"):
        return
    rows = gate.conn.execute(
        "SELECT id, entity_kind, entity_key, status FROM qc_findings"
        " WHERE rule_id='R-S1' AND status IN ('open','confirmed')",
    ).fetchall()
    if not rows:
        return

    table_stale = {r["entity_key"] for r in rows if r["entity_kind"] == "table"}
    lb_stale = {r["entity_key"] for r in rows if r["entity_kind"] == "lb"}
    any_hit = False

    if "show_picks" in table_stale:
        any_hit = True
        for key in _SHOW_PICKS_DEPENDENTS:
            gate.withhold_field(key, "R-S1")
        for row in gate.view["rows"].get("source", []):
            gate.withhold_row("source", row, "rank", "R-S1",
                               int(row["lb_id"]["value"][3:]) if row.get("lb_id") else None)
        for row in gate.view["rows"].get("family", []):
            gate.withhold_row("family", row, "confidence", "R-S1",
                               row["id"]["value"] if row.get("id") else None)

    if "song_performances" in table_stale:
        any_hit = True
        for key in _SONG_PERFORMANCES_DEPENDENTS:
            gate.withhold_field(key, "R-S1")
        gate.withhold_all_rows("song", "premiere", "R-S1", id_field="position")
        gate.withhold_all_rows("song", "gap", "R-S1", id_field="position")

    for row in gate.view["rows"].get("source", []):
        if not row.get("lb_id") or not row["lb_id"]["value"]:
            continue
        lb = int(row["lb_id"]["value"][3:])
        if str(lb) not in lb_stale:
            continue
        any_hit = True
        gate.withhold_row("source", row, "scan_grade", "R-S1", lb)
        if lb == pick_lb:
            gate.withhold_field("pick.scan_grade", "R-S1")

    if any_hit:
        gate.notices.append("analysis stale")
    for r in rows:
        gate.consulted_findings.append((r["id"], r["status"]))


# ---------------------------------------------------------------------------
# G7 claims
# ---------------------------------------------------------------------------

# axis (backend.dossier_claims verified_by suffix) -> source[] row sub.
_AXIS_TO_SUB = {
    "lb_rating": "lb_rating", "scan": "scan_grade", "runtime": "runtime",
    "resolution": "resolution", "soundboard": "type", "complete": "completeness",
}


def _axis_of(claim: dict) -> str | None:
    verified_by = claim.get("verified_by", "")
    return verified_by.removeprefix("D-08 ") if verified_by.startswith("D-08 ") else None


def _other_lb_from_claim(claim: dict) -> int | None:
    other = claim.get("slots", {}).get("other")
    if other and isinstance(other.get("value"), str):
        m = _LB_RE.match(other["value"])
        if m:
            return int(m.group(1))
    return None


def _claim_comparison_set(entry: dict, view: dict, pick_lb: int | None) -> set[int]:
    """Every LB whose data this claim's comparison actually depends on.

    Args:
        entry: One ``view["claims"]`` item (``{anchor, row, claim}``).
        view: The view under construction.
        pick_lb: The verdict pick's LB, if any.

    Returns:
        LBs in scope for a source-axis (``verdict.*``) claim; empty for every other
        claim kind (those are handled by anchor/row-specific rules instead, see
        :func:`_claim_touches_withheld`).
    """
    anchor = entry["anchor"]
    claim = entry["claim"]
    if anchor == "verdict.why":
        # A superlative/exclusive over every "primary" visible source.
        return _eligible_primary_lbs(view)
    if anchor == "verdict.alternates[]":
        # row is the alternate's own LB (see backend.dossier_claims.attach_claims);
        # the counterpart is always the pick.
        out = set()
        if isinstance(entry["row"], int):
            out.add(entry["row"])
        if pick_lb is not None:
            out.add(pick_lb)
        return out
    if anchor == "verdict.vs_runner_up":
        # row is the axis name (see attach_claims), not an LB, and when the runner-up
        # led, the "other" slot names the pick -- the runner-up's LB isn't always
        # recoverable from the claim. Scope conservatively to every primary source
        # (the runner-up is always one of them) rather than risk missing it.
        out = _eligible_primary_lbs(view)
        if pick_lb is not None:
            out.add(pick_lb)
        other_lb = _other_lb_from_claim(claim)
        if other_lb is not None:
            out.add(other_lb)
        return out
    return set()


def _claim_touches_withheld(entry: dict, gate: _Gate, view: dict, pick_lb: int | None) -> bool:
    """Whether *entry* should be dropped for touching withheld/unusable data."""
    anchor, row = entry["anchor"], entry["row"]
    claim = entry["claim"]

    if (anchor, row) in gate.withheld_instances:
        return True

    if anchor in ("verdict.why", "verdict.vs_runner_up", "verdict.alternates[]"):
        axis = _axis_of(claim)
        sub = _AXIS_TO_SUB.get(axis) if axis else None
        if sub is None:
            return False
        comparison_set = _claim_comparison_set(entry, view, pick_lb)
        return any((sub, lb) in gate.withheld_source_subs for lb in comparison_set)

    if anchor == "stats.rotation_rank":
        return ("stats.rotation_rank", None) in gate.withheld_instances or \
            ("stats.rotation", None) in gate.withheld_instances

    if anchor == "context.chronicle":
        if claim.get("scope") == "venue_run":
            return ("run.position", None) in gate.withheld_instances or \
                ("run.label", None) in gate.withheld_instances
        if claim.get("scope") == "tour":
            return ("show.tour", None) in gate.withheld_instances

    return False


def _run_g7_claims(gate: _Gate, pick_lb: int | None) -> bool:
    """Drop every claim :func:`_claim_touches_withheld` flags; rebuild the T4 anchors.

    Returns:
        True if at least one claim was dropped -- informational only; G8 does not
        escalate a G7 drop into a refusal (that would defeat the point of G7).
    """
    from backend.dossier_claims import chronicle, verdict_why

    view = gate.view
    claims = view.get("claims", [])
    if not claims:
        return False

    kept, dropped_any = [], False
    for entry in claims:
        if _claim_touches_withheld(entry, gate, view, pick_lb):
            dropped_any = True
            continue
        kept.append(entry)
    view["claims"] = kept

    fields = view["fields"]

    if any(e["anchor"] == "verdict.why" for e in claims):
        pick_claims = {}
        for e in kept:
            if e["anchor"] == "verdict.why":
                axis = _axis_of(e["claim"])
                if axis:
                    pick_claims[axis] = e["claim"]
        why = verdict_why(fields, pick_claims)
        fields["verdict.why"] = (
            build_field(why, 4, "claim-engine slot template (verdict_why)", "stated",
                        ["claim:verdict_why"])
            if why is not None else build_fallback_field(ANCHORS["verdict.why"]))

    if any(e["anchor"] == "context.chronicle" for e in claims):
        run_claim = next((e["claim"] for e in kept if e["anchor"] == "context.chronicle"
                           and e["claim"]["scope"] == "venue_run"), None)
        tour_claim = next((e["claim"] for e in kept if e["anchor"] == "context.chronicle"
                            and e["claim"]["scope"] == "tour"), None)
        chron = chronicle(fields, run_claim, tour_claim)
        if chron is not None:
            fields["context.chronicle"] = build_field(
                chron, 4, "slot template (run/tour claims + Olof chronicle)", "stated",
                ["claim:chronicle"])
        elif ("context.chronicle", None) not in gate.withheld_instances:
            fields["context.chronicle"] = build_fallback_field(ANCHORS["context.chronicle"])

    return dropped_any


# ---------------------------------------------------------------------------
# G8 channel
# ---------------------------------------------------------------------------


def _contains_private_lb(value: object, private_labels: set[str]) -> bool:
    if isinstance(value, str):
        return any(label in value for label in private_labels)
    if isinstance(value, dict):
        return any(_contains_private_lb(v, private_labels) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_private_lb(v, private_labels) for v in value)
    return False


def _run_g8_channel(gate: _Gate, channel: str, d1: dict, pick_lb: int | None) -> None:
    if channel != "public":
        return

    private_lbs = {
        int(m["lb"][3:]) for bucket in d1.get("sources", []) for m in bucket["members"]
        if m.get("private")
    }
    if not private_lbs:
        # Still run the G7 backstop below even with no private sources.
        private_labels: set[str] = set()
    else:
        private_labels = {f"LB-{lb:05d}" for lb in private_lbs}
        for row in gate.view["rows"].get("source", []):
            if row.get("lb_id") and row["lb_id"]["value"]:
                lb = int(row["lb_id"]["value"][3:])
                if lb in private_lbs:
                    gate.reasons.append(
                        f"G8: private source LB-{lb:05d} leaked into a public view")

    if private_labels:
        for key, f in _iter_all_fields(gate.view):
            if key == "prov.withheld[]":
                continue
            if _contains_private_lb(f["value"], private_labels):
                gate.reasons.append(f"G8: private source data leaked into {key}")
        for entry in gate.view.get("claims", []):
            if _contains_private_lb(
                    {k: v["value"] for k, v in entry["claim"]["slots"].items()}, private_labels):
                gate.reasons.append(f"G8: private source data leaked into a claim on "
                                    f"{entry['anchor']}")

    # Backstop: every surviving claim should already be clean after G7 -- if one
    # isn't, that's a G7 bug, and a public reader gets a refusal rather than a
    # silently-wrong claim.
    for entry in gate.view.get("claims", []):
        if _claim_touches_withheld(entry, gate, gate.view, pick_lb):
            gate.reasons.append(
                f"G8: a surviving claim on {entry['anchor']} still touches a withheld/"
                "disputed source (G7 should have dropped this -- backstop fired)")


# ---------------------------------------------------------------------------
# G9 lint (pure functions; not run by build_dossier -- see module docstring)
# ---------------------------------------------------------------------------

_CLAIM_SPAN_RE = re.compile(r"<([a-zA-Z0-9]+)([^>]*\bdata-claim\b[^>]*)>.*?</\1>", re.DOTALL)
_L1_PHRASES = ("taper unknown", "unknown taper", "independent tapes", "none indexed")
_L1_BARE_WORDS = ("only", "highest", "best", "biggest", "first", "last", "closing")
_DATA_LB_RE = re.compile(r'data-lb="([^"]*)"')
_MAP_PIN_RE = re.compile(r'data-map-pin="(solid|hollow)"[^>]*?data-venue-basis="([^"]*)"')


def lint_l1(html: str) -> list[str]:
    """L1: forbidden phrases/bare superlatives outside a ``data-claim`` span.

    Also checks the plan's map-pin invariant: no solid pin unless the same
    element's ``data-venue-basis`` is ``"venue"`` (a hollow ring is fine with
    ``"city_centre"``). This convention (``data-map-pin`` / ``data-venue-basis``
    attributes on the map element) is new with C28 -- C29's template must emit it.

    Args:
        html: Rendered dossier HTML.

    Returns:
        Human-readable violation strings, empty if clean.
    """
    violations: list[str] = []
    stripped = _CLAIM_SPAN_RE.sub("", html)
    lower = stripped.lower()
    for phrase in _L1_PHRASES:
        if phrase in lower:
            violations.append(f"forbidden phrase {phrase!r} found outside a claim span")
    for word in _L1_BARE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lower):
            violations.append(f"bare superlative {word!r} found outside a claim span")
    for m in _MAP_PIN_RE.finditer(html):
        kind, basis = m.group(1), m.group(2)
        if kind == "solid" and basis != "venue":
            violations.append(
                f"solid map pin rendered with venue.coords.basis={basis!r} (must be 'venue')")
    return violations


def lint_data_lb(html: str) -> list[str]:
    """Every ``data-lb="..."`` attribute value must be a registered anchor key.

    Args:
        html: Rendered dossier HTML.

    Returns:
        Human-readable violation strings, empty if clean.
    """
    violations: list[str] = []
    for value in _DATA_LB_RE.findall(html):
        if value not in ANCHORS:
            violations.append(f"data-lb={value!r} is not a registered anchor")
    return violations


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _input_fingerprint(conn: sqlite3.Connection, event_id: int | None,
                        findings: list[tuple[int, str]], pick_lb: int | None) -> str:
    parsed_at = None
    if event_id is not None:
        row = conn.execute(
            "SELECT op.parsed_at FROM olof_events oe JOIN olof_pages op"
            " ON op.filename = oe.page_filename WHERE oe.event_id = ?",
            (event_id,),
        ).fetchone()
        parsed_at = row[0] if row else None

    pick_computed_at = None
    if pick_lb is not None and _table_exists(conn, "show_picks"):
        row = conn.execute(
            "SELECT computed_at FROM show_picks WHERE lb_number = ?", (pick_lb,)
        ).fetchone()
        pick_computed_at = row[0] if row else None

    payload = {
        "olof_parsed_at": parsed_at,
        "findings": sorted(set(findings)),
        "pick_computed_at": pick_computed_at,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_gate(dossier: dict, conn: sqlite3.Connection, *, channel: str,
             event_id: int | None = None, visible_lbs: list[int] | None = None) -> dict:
    """Run the QC gate G1-G8 against a built dossier's view (G9 is a separate, pure lint).

    Mutates ``dossier["view"]`` in place: withheld Fields/rows get the ``withheld``
    fallback, and ``dossier["view"]["fields"]["prov.withheld[]"]`` is set from the
    accumulated list. Never raises -- an internal failure is logged and reported in
    the returned ``qc`` dict instead.

    Args:
        dossier: A dict as built so far by :func:`backend.dossier.build_dossier`
            (``dossier["view"]`` already present).
        conn: Open SQLite connection.
        channel: ``'public'`` or ``'full'`` (only used by G8).
        event_id: The show's ``olof_events.event_id``, if the caller already has it
            (saves recomputing it here); ``None`` when there is no Olof event.
        visible_lbs: The channel-visible LB numbers, if the caller already has them
            (currently unused directly -- kept for callers/future checks that need
            the channel-scoped LB set without recomputing it).

    Returns:
        ``{checks_run, passed, withheld, refused, reasons, notices,
        input_fingerprint}``.
    """
    del visible_lbs  # not needed by any check yet; kept in the signature per spec.
    checks_run = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]
    if "view" not in dossier:
        return {
            "checks_run": [], "passed": False, "withheld": [], "refused": False,
            "reasons": ["no view to gate (build_view failed)"], "notices": [],
            "input_fingerprint": "",
        }

    view = dossier["view"]
    gate = _Gate(view, conn)
    try:
        show = dossier.get("show", {})
        date_iso = show.get("date_iso", "")
        pick_lb = _lb_of(view["fields"].get("pick.lb_id"))

        _run_g1_identity(gate, date_iso, event_id)
        _run_g2_assert(gate)
        _run_g3_provenance(gate)
        _run_g4_quarantine(gate, event_id, show.get("venue"), show.get("city"), pick_lb)
        _run_g5_invariants(gate, dossier, pick_lb)
        _run_g6_freshness(gate, pick_lb)
        _run_g7_claims(gate, pick_lb)
        _run_g8_channel(gate, channel, dossier, pick_lb)

        view["fields"]["prov.withheld[]"] = (
            build_field(gate.withheld, 3, "gate output (C28)", "stated", ["qc_findings"])
            if gate.withheld else build_fallback_field(ANCHORS["prov.withheld[]"]))

        refused = bool(gate.reasons)
        qc = {
            "checks_run": checks_run,
            "passed": not refused,
            "withheld": gate.withheld,
            "refused": refused,
            "reasons": gate.reasons,
            "notices": gate.notices,
            "input_fingerprint": _input_fingerprint(
                conn, event_id, gate.consulted_findings, pick_lb),
        }
    except Exception:  # noqa: BLE001 -- the gate must never break dossier assembly (spec S:1)
        log.exception("dossier_qc: gate failed for %s", dossier.get("show", {}).get("date_iso"))
        qc = {
            "checks_run": [], "passed": False, "withheld": [], "refused": False,
            "reasons": ["QC gate raised an internal error"], "notices": [],
            "input_fingerprint": "",
        }
    return qc
