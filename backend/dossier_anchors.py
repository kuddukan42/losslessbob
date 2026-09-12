"""Show dossier view-model registry (TODO-342 dossier redesign, Phase 5, C25).

Defines :class:`Field`, the exhaustive spec-`SS6` ``ANCHORS`` registry, and
:func:`build_view`, which turns a :func:`backend.dossier.build_dossier` D1
payload plus the live database into the page's view model:
``{"fields": {key: Field}, "rows": {prefix: [{"sub": Field, ...}, ...]}}``.

Every key in :data:`ANCHORS` appears in the returned view, either with a real
derived value or with its registered fallback -- an anchor whose derivation
fails or finds no data degrades to the fallback, it never raises (spec S:1,
audited by :func:`build_view`'s own safety-net pass). This module is
read-only: it never writes to the database and never invents comparative or
positional wording -- :func:`backend.dossier_claims.attach_claims` (C26) adds
``view["claims"]`` and fills the T4 anchors; the selection rules are C27 (see
the docstring of :func:`build_view`).

Key convention (plan lines 93-125):

- ``prefix[]`` -- one Field with a list value, in ``view["fields"]``.
- ``prefix[].sub`` -- a per-row Field under ``sub``, in
  ``view["rows"][prefix]`` (a list of ``{sub: Field}`` dicts, one per row).
- Anything else -- a scalar Field in ``view["fields"]``.
"""
from __future__ import annotations

import logging
import sqlite3
import statistics
from dataclasses import dataclass
from typing import Literal, TypedDict

from backend import dossier_fields as df

log = logging.getLogger(__name__)

Confidence = Literal[
    "corroborated", "stated", "inferred", "disputed", "withheld", "unavailable",
]


class Field(TypedDict):
    """One rendered anchor value (plan line 108-109: the ``Field`` shape).

    Keys:
        value: The rendered value (any JSON-safe shape -- scalar, list, dict),
            or the anchor's fallback value when unavailable.
        tier: The anchor's tier, 1-4 (T1 hardest fact .. T4 generated prose).
        source: Free text naming where the value came from, or ``None`` for a
            fallback.
        confidence: One of :data:`Confidence`.
        derived_from: Keys/tables this value traces to, for the provenance
            footer (``prov.local_fields`` / ``prov.withheld``).
    """

    value: object
    tier: int
    source: str | None
    confidence: Confidence
    derived_from: list[str]


def build_field(
    value: object, tier: int, source: str, confidence: Confidence,
    derived_from: list[str] | None = None,
) -> Field:
    """Build a populated :class:`Field`.

    Args:
        value: The rendered value.
        tier: 1-4.
        source: Free text describing the derivation.
        confidence: One of :data:`Confidence`.
        derived_from: Traced keys/tables; defaults to ``[source]``.

    Returns:
        A :class:`Field`.
    """
    return Field(
        value=value, tier=tier, source=source, confidence=confidence,
        derived_from=list(derived_from) if derived_from is not None else [source],
    )


def build_fallback_field(anchor: Anchor) -> Field:
    """Build the fallback :class:`Field` for *anchor* -- confidence ``unavailable``.

    Args:
        anchor: The registry row.

    Returns:
        A :class:`Field` whose value is the anchor's registered fallback
        value (``None`` for an ``"omit"``/``"suppress"`` fallback kind).
    """
    value = anchor.fallback_value if anchor.fallback_kind in ("value", "required") else None
    return Field(value=value, tier=anchor.tier, source=None, confidence="unavailable",
                 derived_from=[])


@dataclass(frozen=True)
class Anchor:
    """One row of the spec S:6 anchor map.

    Keys:
        key: The dotted/bracketed anchor key, exactly as spec'd (individual
            keys only -- "a . b" / "a / b" table rows are pre-split, one
            :class:`Anchor` each).
        tier: 1 (hardest fact) .. 4 (generated prose).
        section: ``'header'`` / ``'setlist'`` / ``'sources'`` / ``'context'``.
        source: Free text, the spec's "source / computation" column.
        fallback_kind: ``'required'`` (must render, no null fallback --
            tests assert presence, not a value), ``'omit'`` (renders nothing),
            ``'suppress'`` (a larger block/section is hidden), or ``'value'``
            (a specific literal fallback, e.g. ``"Venue unknown"``).
        fallback_value: The literal fallback value for ``fallback_kind ==
            "value"`` (and, informationally, for ``"required"``); ``None``
            otherwise.
        local_analysis: True for a verdict/ledger/scan-grade/family-confidence/
            T4/claim-backed anchor -- stripped by
            :func:`backend.dossier.filter_dossier_sections`
            ``local_analysis=False`` (plan line 788-789).
    """

    key: str
    tier: int
    section: str
    source: str
    fallback_kind: str = "omit"
    fallback_value: object = None
    local_analysis: bool = False


def _a(key: str, tier: int, section: str, source: str, fallback_kind: str = "omit",
       fallback_value: object = None, local_analysis: bool = False) -> Anchor:
    return Anchor(key, tier, section, source, fallback_kind, fallback_value, local_analysis)


# ---------------------------------------------------------------------------
# The exhaustive anchor map (plan lines 666-790).
# ---------------------------------------------------------------------------

_ANCHOR_ROWS: list[Anchor] = [
    # -- Header and verdict --------------------------------------------------
    _a("show.date.long", 1, "header", "date_iso long", "required"),
    _a("show.date.dow", 1, "header", "date_iso %A", "required"),
    _a("show.venue", 1, "header", "_build_show cascade", "value", "Venue unknown"),
    _a("show.city", 1, "header", "city", "omit"),
    _a("show.country", 1, "header", "country", "omit"),
    _a("show.tour", 1, "header", "D-07 tour object (Olof leg)", "omit"),
    _a("show.net_number", 1, "header", "concert_no_net", "omit"),
    _a("show.year_index", 1, "header", "concert_no_year", "omit"),
    _a("show.band_index", 2, "header", "lineup regex", "omit"),
    _a("run.label", 3, "header", "D-07 (completeness guard)", "suppress"),
    _a("run.position", 3, "header", "D-07 (completeness guard)", "suppress"),
    _a("run.dates[]", 3, "header", "D-07 (completeness guard)", "suppress"),
    _a("run.dates[].url", 3, "header", "D-07 (completeness guard)", "omit"),
    _a("pick.lb_id", 1, "header", "verdict pick", "suppress", local_analysis=True),
    _a("pick.url", 1, "header", "detail_url", "value", local_analysis=True),
    _a("pick.taper.name", 1, "header", "taper_render (R-T1..3 blocked, R-T4 notice)", "omit",
       local_analysis=True),
    _a("pick.taper.confidence", 1, "header", "taper_render", "omit", local_analysis=True),
    _a("pick.medium", 3, "header", "D-13", "value", "audio", local_analysis=True),
    _a("pick.type", 1, "header", "source_type", "omit", local_analysis=True),
    _a("pick.lb_rating", 1, "header", "rating", "value", "—", local_analysis=True),
    _a("pick.scan_grade", 1, "header", "per-LB latest scored scan", "omit", local_analysis=True),
    _a("pick.lineage_short", 1, "header", "parser", "omit", local_analysis=True),
    _a("pick.resolution", 2, "header", "D-11 (basis-labelled)", "omit", local_analysis=True),
    _a("pick.runtime", 2, "header", "runtime", "omit", local_analysis=True),
    _a("pick.generation", 3, "header", "D-05", "omit", local_analysis=True),
    _a("pick.completeness", 3, "header", "D-01", "omit", local_analysis=True),
    _a("pick.curated_in[]", 1, "header", "curated_lists", "omit", local_analysis=True),
    _a("show.official_release", 3, "header", "D-03", "omit"),
    _a("verdict.why", 4, "header", "claim-engine slot template (verdict_why)", "omit",
       local_analysis=True),
    _a("verdict.vs_runner_up", 2, "header", "D-08 + claim engine", "omit",
       local_analysis=True),
    _a("verdict.alternates[]", 2, "header", "D-08 + claim engine", "omit",
       local_analysis=True),
    _a("ledger[]", 1, "header", "evidence_json (G5/G6)", "suppress", local_analysis=True),
    _a("ledger.total", 1, "header", "pick_score (G5/G6)", "suppress", local_analysis=True),
    # -- Setlist --------------------------------------------------------------
    _a("setlist.count", 1, "setlist", "post-fix olof_songs", "omit"),
    # Fallback is omit: "complete" may only be assumed from a stated/corroborated D-09 result.
    _a("show.setlist_confidence", 3, "setlist", "D-09 (Phase 3a quorum)", "omit"),
    _a("set[].label", 1, "setlist", "encore + broadcast bands", "value"),
    _a("song[].position", 1, "setlist", "olof_songs", "required"),
    _a("song[].title", 1, "setlist", "olof_songs title + subtitle", "required"),
    _a("song[].writers", 2, "setlist", "parser", "omit"),
    _a("song[].instruments[]", 2, "setlist", "parser", "omit"),
    _a("song[].premiere", 3, "setlist", "D-02 (three-part gate)", "omit"),
    _a("song[].gap", 3, "setlist", "D-02 (three-part gate)", "omit"),
    _a("song[].bobtalk", 2, "setlist", "D-10", "omit"),
    _a("song[].official_release", 3, "setlist", "D-03", "omit"),
    _a("stats.rotation", 1, "setlist", "olof_events rotation columns", "omit"),
    _a("stats.premiere_count", 1, "setlist", "D-02 (P1d)", "omit"),
    _a("stats.rotation_rank", 3, "setlist", "D-04 claim", "omit", local_analysis=True),
    _a("stats.premiere_titles", 3, "setlist", "D-02 (gated)", "omit"),
    _a("stats.instrument_tally", 2, "setlist", "counts only", "omit"),
    _a("band.members[]", 2, "setlist", "lineup parser", "omit"),
    _a("band.label", 2, "setlist", "lineup parser", "value", "Personnel"),
    # -- Sources ----------------------------------------------------------------
    _a("sources.count", 1, "sources", "visible sources", "required"),
    _a("sources.tape_count", 1, "sources", "tapematch families", "omit"),
    _a("sources.visible_n", 2, "sources", "S8.3 (C27)", "required"),
    _a("source[].lb_id", 1, "sources", "existing", "required"),
    _a("source[].url", 1, "sources", "existing", "required"),
    _a("source[].taper", 1, "sources", "taper_render (R-T1..3 blocked, R-T4 notice)", "omit"),
    _a("source[].generation", 3, "sources", "D-05", "omit"),
    _a("source[].medium", 3, "sources", "D-13", "value", "audio"),
    _a("source[].completeness", 3, "sources", "D-01", "omit"),
    _a("source[].type", 1, "sources", "existing", "omit"),
    _a("source[].scan_grade", 1, "sources", "per-LB latest scored scan", "omit",
       local_analysis=True),
    _a("source[].lb_rating", 1, "sources", "existing", "value", "—"),
    _a("source[].runtime", 2, "sources", "runtime", "value", "—"),
    _a("source[].resolution", 2, "sources", "D-11", "value", "—"),
    _a("source[].character", 1, "sources", "parser", "omit"),
    _a("source[].flags[]", 1, "sources", "parser", "omit"),
    _a("source[].lineage", 1, "sources", "parser (footnote)", "omit"),
    _a("source[].curated_in[]", 1, "sources", "existing", "omit"),
    _a("source[].rank", 1, "sources", "show_picks (C27)", "omit", local_analysis=True),
    _a("source[].group", 2, "sources", "S8.2 fragment/G2 classification (C27)", "value",
       "primary"),
    _a("family[].id", 1, "sources", "families", "omit"),
    _a("family[].label", 1, "sources", "families + S8.4 rules (C27)", "value", "no band"),
    _a("family[].size", 1, "sources", "families", "omit"),
    _a("family[].confidence", 1, "sources", "families + S8.5 rules (C27)", "omit",
       local_analysis=True),
    _a("family[].basis", 3, "sources", "family_basis", "omit", local_analysis=True),
    _a("source[].added", 3, "sources", "D-12 (null stub)", "suppress"),
    _a("source[].filesize", 3, "sources", "D-11", "value", "—"),
    _a("source[].disc_count", 3, "sources", "D-11", "value", "—"),
    _a("source[].filecount", 3, "sources", "D-11", "value", "—"),
    # -- Context, related and provenance ----------------------------------------
    _a("context.chronicle", 4, "context", "slot template (run/tour claims + Olof chronicle)",
       "value"),
    _a("context.bobtalk", 1, "context", "bobtalk minus anchored lines", "value",
       "No bobtalk recorded"),
    _a("context.session_notes", 1, "context", "post-fix notes + recording notes", "omit"),
    _a("venue.name", 1, "context", "show fields", "omit"),
    _a("venue.city", 1, "context", "show fields", "omit"),
    _a("venue.coords", 1, "context", "venue_geocoded / setlist.fm city centre", "omit"),
    _a("venue.map", 1, "context", "compact _render_locator_svg", "value", "no map"),
    _a("venue.district", 3, "context", "D-06 (null stub)", "omit"),
    _a("venue.run_nights", 3, "context", "D-07", "omit"),
    _a("venue.city_total", 3, "context", "D-07", "omit"),
    _a("city_history[]", 3, "context", "D-07", "suppress"),
    _a("xrefs[]", 1, "context", "_build_xref", "required"),
    _a("prov.credits", 1, "context", "footer", "required"),
    _a("prov.stamps", 1, "context", "footer (inputs)", "required"),
    _a("prov.local_fields[]", 3, "context", "registry scan", "value"),
    _a("prov.withheld[]", 3, "context", "gate output (C28)", "omit"),
    _a("show.newest_source_date", 3, "context", "D-12 (null stub)", "suppress"),
]

ANCHORS: dict[str, Anchor] = {a.key: a for a in _ANCHOR_ROWS}

# "prefix[].sub" row anchors, grouped by prefix.
_ROW_PREFIXES: dict[str, list[str]] = {}
for _k in ANCHORS:
    if "[]." in _k:
        _prefix, _sub = _k.split("[].", 1)
        _ROW_PREFIXES.setdefault(_prefix, []).append(_sub)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,),
    ).fetchone()
    return row is not None


def _safe(fn, *args, default=None):
    """Call *fn*; on a missing-data DB error, log at debug and return *default*."""
    try:
        return fn(*args)
    except sqlite3.OperationalError as exc:
        log.debug("dossier_anchors: %s degraded (%s)", getattr(fn, "__name__", fn), exc)
        return default


class _ViewBuilder:
    """Accumulates ``fields``/``rows`` while tracking which anchors were set."""

    def __init__(self) -> None:
        self.fields: dict[str, Field] = {}
        self.rows: dict[str, list[dict]] = {}
        self._row_index: dict[str, dict[object, dict]] = {}
        # Intermediate derivations the claim engine reuses (dossier_claims.attach_claims).
        self.ctx: dict = {}

    def set_field(self, key: str, f: Field) -> None:
        self.fields[key] = f

    def row(self, prefix: str, row_key: object) -> dict:
        """Get (or create) the per-row dict for *prefix* keyed by *row_key*."""
        index = self._row_index.setdefault(prefix, {})
        if row_key not in index:
            d: dict = {}
            index[row_key] = d
            self.rows.setdefault(prefix, []).append(d)
        return index[row_key]

    def finalize(self) -> dict:
        for key, anchor in ANCHORS.items():
            if "[]." in key:
                continue  # handled per-row; the safety net below covers empty prefixes.
            if key not in self.fields:
                self.fields[key] = build_fallback_field(anchor)
        for prefix, subs in _ROW_PREFIXES.items():
            self.rows.setdefault(prefix, [])
            for row in self.rows[prefix]:
                for sub in subs:
                    if sub not in row:
                        row[sub] = build_fallback_field(ANCHORS[f"{prefix}[].{sub}"])
        return {"fields": self.fields, "rows": self.rows}


def build_view(
    d1: dict,
    conn: sqlite3.Connection,
    link_mode: str = "file",
    *,
    event_id: int | None = None,
    visible_lbs: list[int] | None = None,
    channel: str = "public",
) -> dict:
    """Build the dossier page's view model from a D1 payload plus the database.

    Never mutates *d1*. Every anchor in :data:`ANCHORS` appears in the
    returned view (a value or its fallback) -- a derivation that fails or
    finds no data silently falls back, it never raises (spec S:1).

    Comparative/positional wording comes only from the claim engine
    (:mod:`backend.dossier_claims`, C26): ``view["claims"]`` lists every
    verified Claim by anchor, and ``verdict.why`` / ``context.chronicle`` are
    its T4 slot templates. S8 selection rules (C27): each visible source gets
    a ``source[].group`` (``"primary"`` / ``"fragment"`` / ``"no_match"`` --
    :func:`_classify_sources`); the header ``pick``/``verdict.*`` anchors and
    ``verdict.why``'s claims are drawn from the best ``pick_rank`` among
    ``"primary"`` sources only (:func:`backend.dossier_fields.compare_sources`
    scoped to that set in :func:`_build_header`) -- dossier-only, D-01 into
    ``concert_ranker/picks.py`` stays a follow-up TODO; ``family[].label`` is
    a taper's name only when :func:`backend.dossier_fields.family_taper_label`
    says every member's credit is confirmed and the family clears the S8.5
    confidence floor, else "Family A/B/..." by bucket order;
    ``sources.visible_n`` is the S8.3 collapse count (C26/C27:
    :mod:`backend.dossier_claims` finishes it once D-08 axes exist). Scope
    limit (C28 owns this): the QC gate and ``prov.withheld[]`` population.
    Raw D-04/D-08 data with no comparative word is still surfaced where noted
    (``stats.rotation``, ``stats.rotation_rank``'s bare percentage,
    ``verdict.vs_runner_up``'s per-field diffs) -- those are facts, not claims.

    Args:
        d1: The dict returned by :func:`backend.dossier.build_dossier`
            (non-ambiguous shape).
        conn: Open SQLite connection (``row_factory = sqlite3.Row``).
        link_mode: ``'file'`` (default) links sibling nights to
            ``dossier-YYYY-MM-DD.html``; ``'inline'`` links to
            ``/api/dossier/html?date=...&inline=1`` (plan Decisions line 38).
        event_id: The primary ``olof_events.event_id`` :func:`build_dossier`
            resolved for this date, if any.
        visible_lbs: The channel-visible LB numbers (matches
            :func:`build_dossier`'s own visibility filter); defaults to every
            LB with a public member in ``d1["sources"]``.
        channel: ``'public'`` or ``'full'`` (only used to select the default
            *visible_lbs*).

    Returns:
        ``{"fields": {key: Field}, "rows": {prefix: [{sub: Field, ...}]},
        "claims": [{anchor, row, claim}]}``.
    """
    vb = _ViewBuilder()
    show = d1.get("show", {})
    context = d1.get("context", {})
    setlist = d1.get("setlist", [])
    sources = d1.get("sources", [])
    date_iso = show.get("date_iso")
    lineup = context.get("lineup")

    if visible_lbs is None:
        visible_lbs = [
            int(m["lb"][3:]) for bucket in sources for m in bucket["members"]
            if not m.get("private")
        ]

    visible_members = _visible_members(sources)
    classes = _classify_sources(conn, event_id, visible_members) if event_id is not None else {}
    vb.ctx["source_classes"] = classes

    # -- Header -----------------------------------------------------------
    _build_header(vb, d1, conn, event_id, date_iso, lineup, link_mode, visible_members, classes)
    # -- Setlist ------------------------------------------------------------
    _build_setlist(vb, d1, conn, event_id, date_iso, lineup, setlist, visible_lbs)
    # -- Sources ------------------------------------------------------------
    _build_sources(vb, d1, conn, event_id, date_iso, sources, visible_members, classes)
    # -- Context / provenance ------------------------------------------------
    _build_context(vb, d1, conn, event_id, date_iso)

    view = vb.finalize()
    vb.ctx.update(event_id=event_id, visible_lbs=visible_lbs)
    from backend.dossier_claims import attach_claims

    try:
        attach_claims(view, d1, conn, vb.ctx)
    except Exception:  # noqa: BLE001 -- a claim failure must never cost the page its view
        log.exception("dossier_anchors: claim engine failed for %s; no claims", date_iso)
        view["claims"] = []
    _fill_prov_local_fields(view)
    return view


# ---------------------------------------------------------------------------
# Header + verdict
# ---------------------------------------------------------------------------

def _visible_members(sources: list[dict]) -> list[tuple[int, dict, dict]]:
    """Every non-private ``(lb, member, bucket)`` triple across *sources*, in D1 order."""
    return [
        (int(m["lb"][3:]), m, bucket) for bucket in sources for m in bucket["members"]
        if not m.get("private")
    ]


def _classify_sources(
    conn: sqlite3.Connection, event_id: int | None,
    visible_members: list[tuple[int, dict, dict]],
) -> dict[int, dict]:
    """§8.2 (C27): classify every visible source into a selection group.

    Args:
        conn: Open SQLite connection.
        event_id: The show's ``olof_events.event_id``, or ``None`` (no
            setlist to score against -- every source classifies "primary").
        visible_members: :func:`_visible_members`'s result.

    Returns:
        ``{lb: {"group": "primary" | "fragment" | "no_match",
        "completeness": Completeness | None, "runtime": float | None}}``.
        ``"no_match"`` (G2 :func:`df.fits_show` failed) takes priority over
        ``"fragment"`` (§8.2) when a source is both.
    """
    out: dict[int, dict] = {}
    lbs = [lb for lb, _, _ in visible_members]
    if event_id is None or not lbs:
        return {lb: {"group": "primary", "completeness": None, "runtime": None} for lb in lbs}

    comp_map = _safe(df.completeness, conn, event_id, lbs, default={}) or {}
    runtimes: dict[int, float | None] = {}
    for lb, member, _bucket in visible_members:
        rt = _safe(df.parse_runtime, member.get("timing"))
        runtimes[lb] = rt["total_minutes"] if rt else None
    rt_values = [v for v in runtimes.values() if v is not None]
    median_runtime = statistics.median(rt_values) if rt_values else None

    for lb in lbs:
        comp = comp_map.get(lb)
        fits = comp.get("fits_show", True) if comp else True
        fragment = df.is_fragment(comp, runtimes.get(lb), median_runtime)
        group = "no_match" if not fits else "fragment" if fragment else "primary"
        out[lb] = {"group": group, "completeness": comp, "runtime": runtimes.get(lb)}
    return out


def _find_pick_member(d1: dict) -> tuple[int, dict] | None:
    rec = d1.get("recommendation")
    if not rec:
        return None
    lb_str = rec["lb"]
    try:
        lb = int(lb_str[3:])
    except (ValueError, IndexError):
        return None
    for bucket in d1.get("sources", []):
        for m in bucket["members"]:
            if m.get("lb") == lb_str:
                return lb, m
    return None


def _find_member_by_lb(d1: dict, lb: int) -> dict | None:
    """The D1 member dict for *lb*, or ``None`` if it isn't in ``d1["sources"]``."""
    lb_str = f"LB-{lb:05d}"
    for bucket in d1.get("sources", []):
        for m in bucket["members"]:
            if m.get("lb") == lb_str:
                return m
    return None


def _select_verdict_pick(
    d1: dict, cmp_src: dict | None, classes: dict[int, dict] | None = None,
) -> tuple[int, dict] | None:
    """C27 verdict pick: the best ``pick_rank`` among ``"primary"`` (non-fragment,
    G2-passing) visible sources.

    Dossier-only (plan S8): this never touches ``show_picks``/``concert_ranker`` --
    feeding it back into D-01 picks is a follow-up TODO. Falls back to the D1
    payload's own ``recommendation`` when there is no event, no primary source has
    a ``show_picks`` row, or the primary source can't be resolved back to a D1
    member (should not happen -- ``visible_members`` is built from the same
    ``d1["sources"]``).

    Args:
        d1: The D1 payload.
        cmp_src: :func:`df.compare_sources` already computed over the show's
            "primary" sources (shared with ``verdict.vs_runner_up``/
            ``verdict.alternates[]`` -- computed once, not twice).
        classes: :func:`_classify_sources`'s result. When given, the fallback
            recommendation is used only if it is itself ``"primary"`` -- a
            fragment or no-match source is never the verdict.

    Returns:
        ``(lb, member)``, or ``None``.
    """
    if cmp_src and cmp_src.get("pick") is not None:
        member = _find_member_by_lb(d1, cmp_src["pick"])
        if member is not None:
            return cmp_src["pick"], member
    fallback = _find_pick_member(d1)
    if fallback is not None and classes and \
            classes.get(fallback[0], {}).get("group", "primary") != "primary":
        return None
    return fallback


def _build_header(vb, d1, conn, event_id, date_iso, lineup, link_mode, visible_members,
                   classes) -> None:
    show = d1.get("show", {})
    if show.get("date_disp"):
        vb.set_field("show.date.long", build_field(
            show["date_disp"], 1, "d1.show.date_disp", "stated"))
    if show.get("dow"):
        vb.set_field("show.date.dow", build_field(show["dow"], 1, "d1.show.dow", "stated"))
    if show.get("venue"):
        vb.set_field("show.venue", build_field(show["venue"], 1, "d1.show.venue", "stated"))
    if show.get("city"):
        vb.set_field("show.city", build_field(show["city"], 1, "d1.show.city", "stated"))
    if show.get("country"):
        vb.set_field("show.country", build_field(show["country"], 1, "d1.show.country",
                                                   "stated"))
    if show.get("tour"):
        vb.set_field("show.tour", build_field(show["tour"], 1, "d1.show.tour", "stated"))
    if show.get("net_number") is not None:
        vb.set_field("show.net_number", build_field(
            show["net_number"], 1, "d1.show.net_number", "stated"))
    if show.get("year_concert_number") is not None:
        vb.set_field("show.year_index", build_field(
            show["year_concert_number"], 1, "d1.show.year_concert_number", "stated"))

    lineup_parsed = _safe(df.parse_band_lineup, lineup) if lineup else None
    if lineup_parsed and lineup_parsed.get("band_index") is not None:
        vb.set_field("show.band_index", build_field(
            lineup_parsed["band_index"], 2, "lineup regex", "stated"))

    run_ctx = _safe(df.run_context, conn, event_id) if event_id is not None else None
    vb.ctx["run_ctx"] = run_ctx
    venue_run = run_ctx["venue_run"] if run_ctx else None
    if venue_run and venue_run["claims_ok"]:
        vb.set_field("run.label", build_field(
            venue_run["venue"], 3, "D-07 venue_run", "stated"))
        vb.set_field("run.position", build_field(
            venue_run["position"], 3, "D-07 venue_run", "stated"))
        vb.set_field("run.dates[]", build_field(
            venue_run["dates"], 3, "D-07 venue_run", "stated"))
        entry_dates = _entries_iso_dates(conn)
        rows = []
        for d in venue_run["dates"]:
            if d == date_iso or d not in entry_dates:
                url = None
            elif link_mode == "inline":
                url = f"/api/dossier/html?date={d}&inline=1"
            else:
                url = f"dossier-{d}.html"
            rows.append({"url": build_field(url, 3, "D-07 venue_run", "stated" if url else
                                             "unavailable") if url else
                          build_fallback_field(ANCHORS["run.dates[].url"])})
        vb.rows["run.dates"] = rows

    # C27: scoped to "primary" sources (non-fragment, G2-passing) -- computed once and
    # reused for both the verdict pick and verdict.vs_runner_up/alternates below.
    # No fallback to every visible source: with no primary source there is no verdict.
    primary_lbs = [lb for lb in classes if classes[lb]["group"] == "primary"]
    cmp_src = (_safe(df.compare_sources, conn, event_id, date_iso, primary_lbs)
               if event_id is not None and date_iso and primary_lbs else None)
    pick = _select_verdict_pick(d1, cmp_src, classes)
    if pick is not None:
        lb, member = pick
        vb.ctx["pick_lb"] = lb
        vb.set_field("pick.lb_id", build_field(member["lb"], 1, "verdict pick", "stated"))
        if member.get("url"):
            vb.set_field("pick.url", build_field(member["url"], 1, "detail_url", "stated"))
        tr = _taper_field(conn, lb)
        if tr is not None:
            vb.set_field("pick.taper.name", tr)
            vb.set_field("pick.taper.confidence", build_field(
                tr["value"]["confidence"], 1, "taper_render", "stated"))
        medium = _safe(df.classify_medium, conn, lb)
        if medium and medium.get("evidence"):
            vb.set_field("pick.medium", build_field(
                medium["medium"], 3, "D-13 classify_medium", "stated"))
        if member.get("source_type"):
            vb.set_field("pick.type", build_field(
                member["source_type"], 1, "entries.source_type", "stated"))
        if member.get("rating"):
            vb.set_field("pick.lb_rating", build_field(
                member["rating"], 1, "entries.rating", "stated"))
        quality = member.get("quality") or {}
        if quality.get("grade"):
            vb.set_field("pick.scan_grade", build_field(
                quality["grade"], 1, "per-LB latest scored scan", "stated"))
        lin = _safe(df.lineage_short, member.get("source_chain"))
        if lin:
            vb.set_field("pick.lineage_short", build_field(lin, 1, "lineage_short parser",
                                                             "stated"))
        fmeta = _safe(df.file_meta, conn, lb)
        if fmeta and fmeta.get("resolution") and fmeta["resolution"] != "—":
            vb.set_field("pick.resolution", build_field(
                fmeta["resolution"], 2, "D-11 file_meta", "stated"))
        runtime = _safe(df.parse_runtime, member.get("timing"))
        if runtime:
            vb.set_field("pick.runtime", build_field(
                runtime["total_minutes"], 2, "parse_runtime", "stated"))
        gen = _safe(df.classify_generation, conn, lb)
        if gen and gen.get("generation") and gen["generation"] != "unknown":
            vb.set_field("pick.generation", build_field(
                gen["generation"], 3, "D-05 classify_generation",
                "inferred" if gen.get("basis") == "inferred" else "stated"))
        if event_id is not None:
            c = classes.get(lb, {}).get("completeness")
            if c and c.get("basis") == "tracklist" and c.get("songs_total"):
                pct = round(100 * c["songs_present"] / c["songs_total"])
                vb.set_field("pick.completeness", build_field(
                    pct, 3, "D-01 completeness",
                    "corroborated" if c.get("confidence") == "corroborated" else "stated"))
        curated = member.get("curated") or []
        if curated:
            vb.set_field("pick.curated_in[]", build_field(
                curated, 1, "curated_lists", "stated"))

    if event_id is not None:
        official = _safe(df.official_release, conn, event_id)
        if official and official.get("status") and official["status"] != "none":
            vb.set_field("show.official_release", build_field(
                official["status"], 3, "D-03 official_release", "stated"))

        # cmp_src is already scoped to "primary" sources and computed above, shared
        # with the verdict pick -- the runner-up/alternates a fragment/no_match source
        # would introduce aren't verdict-worthy.
        vb.ctx["cmp_src"] = cmp_src
        if cmp_src and not cmp_src.get("collapsed"):
            if cmp_src.get("diffs"):
                vb.set_field("verdict.vs_runner_up", build_field(
                    cmp_src["diffs"], 2, "D-08 compare_sources", "stated"))
            if cmp_src.get("alternates"):
                vb.set_field("verdict.alternates[]", build_field(
                    cmp_src["alternates"], 2, "D-08 compare_sources", "stated"))

    if pick is not None:
        lb, member = pick
        pick_data = member.get("pick")
        if pick_data:
            if pick_data.get("evidence"):
                vb.set_field("ledger[]", build_field(
                    pick_data["evidence"], 1, "show_picks.evidence_json", "stated"))
            if pick_data.get("score") is not None:
                vb.set_field("ledger.total", build_field(
                    pick_data["score"], 1, "show_picks.pick_score", "stated"))


def visible_lbs_hint(d1: dict) -> list[int]:
    """Best-effort visible LB list straight from a D1 payload's ``sources``."""
    return [
        int(m["lb"][3:]) for bucket in d1.get("sources", []) for m in bucket["members"]
        if not m.get("private")
    ]


def _taper_field(conn: sqlite3.Connection, lb: int) -> Field | None:
    """The QC-gated taper credit for *lb* as a Field, or None when nothing may render.

    Value is ``{name, confidence, marker, notice}`` from :func:`df.taper_render`. Aliases
    are not reloaded per source: the backend loads them at startup, and a standalone
    caller must call ``db.reload_taper_aliases()`` once before building dossiers.
    """
    tr = _safe(df.taper_render, conn, lb, False)
    if not tr or not tr["name"]:
        return None
    confidence: Confidence = (
        "disputed" if tr["notice"] else "inferred" if tr["marker"] else "stated")
    return build_field(
        {k: tr[k] for k in ("name", "confidence", "marker", "notice")}, 1, "taper_render",
        confidence, ["taper_attributions", "qc_findings", "tuit_recordings"])


def _entries_iso_dates(conn: sqlite3.Connection) -> set[str]:
    """Every distinct ISO date with at least one ``entries`` row (computed per call)."""
    from backend.geocoder import entry_date_to_iso

    out: set[str] = set()
    for (date_str,) in _safe(
        lambda c: c.execute(
            "SELECT DISTINCT date_str FROM entries WHERE date_str IS NOT NULL AND date_str != ''"
        ).fetchall(), conn, default=[],
    ):
        iso = entry_date_to_iso(date_str)
        if iso:
            out.add(iso)
    return out


# ---------------------------------------------------------------------------
# Setlist
# ---------------------------------------------------------------------------

def _build_setlist(vb, d1, conn, event_id, date_iso, lineup, setlist, visible_lbs) -> None:
    if setlist:
        vb.set_field("setlist.count", build_field(
            len(setlist), 1, "olof_songs", "stated"))

    if event_id is not None:
        conf = _safe(df.setlist_confidence, conn, event_id, visible_lbs)
        if conf:
            vb.set_field("show.setlist_confidence", build_field(
                conf["status"], 3, "D-09 setlist_confidence",
                "corroborated" if conf.get("verdict") == "corroborated" else
                "disputed" if conf.get("verdict") == "disputed" else "stated"))

        labels_notes = _safe(df.broadcast_set_labels, conn, event_id)
        if labels_notes:
            labels, session_notes = labels_notes
            for lbl in labels:
                row = vb.row("set", tuple(lbl["positions"]))
                row["label"] = build_field(lbl, 1, "broadcast_set_labels", "stated")

        song_hist = _safe(df.song_history, conn, event_id)
        vb.ctx["song_hist"] = song_hist
        songs_by_pos = {s["position"]: s for s in song_hist["songs"]} if song_hist else {}

        bobtalk = _safe(df.anchor_bobtalk, conn, event_id)
        bobtalk_by_pos: dict[int, list[str]] = {}
        if bobtalk:
            for a in bobtalk["anchored"]:
                bobtalk_by_pos.setdefault(a["position"], []).append(a["text"])

        official = _safe(df.official_release, conn, event_id)
        official_by_pos = {s["position"]: s for s in official["songs"]} if official else {}

        for s in setlist:
            pos = s["position"]
            row = vb.row("song", pos)
            row["position"] = build_field(pos, 1, "olof_songs.position", "stated")
            title = s["title"]
            if s.get("annotations"):
                title = f"{title} ({s['annotations']})"
            row["title"] = build_field(title, 1, "olof_songs.song_title", "stated")

            writers = _safe(df.song_writers, conn, event_id, pos)
            if writers and writers.get("value"):
                row["writers"] = build_field(
                    writers["value"], 2, "song_writers parser",
                    "inferred" if writers.get("corrected") else "stated")

            instruments = _safe(df.song_instruments, lineup, pos) if lineup else None
            if instruments:
                tokens = sorted(df._instrument_tokens(instruments))
                if tokens:
                    row["instruments[]"] = build_field(tokens, 2, "song_instruments parser",
                                                         "stated")

            sh = songs_by_pos.get(pos)
            if sh and song_hist and song_hist.get("gate_passed"):
                if sh.get("premiere_badge"):
                    row["premiere"] = build_field(True, 3, "D-02 song_history", "stated")
                if sh.get("gap_badge") and sh.get("gap_shows") is not None:
                    row["gap"] = build_field(sh["gap_shows"], 3, "D-02 song_history", "stated")

            if pos in bobtalk_by_pos:
                row["bobtalk"] = build_field(bobtalk_by_pos[pos], 2, "D-10 anchor_bobtalk",
                                              "stated")

            orel = official_by_pos.get(pos)
            if orel and orel.get("official"):
                row["official_release"] = build_field(True, 3, "D-03 official_release",
                                                        "stated")

        from backend.qc.corroborate import rotation_check

        rc = _safe(rotation_check, conn, event_id) if event_id is not None else None
        if rc and rc.get("olof_pct") is not None:
            vb.set_field("stats.rotation", build_field(
                rc["olof_pct"], 1, "olof_events.rotation_pct",
                "corroborated" if rc.get("agrees") else "stated"))
            vb.set_field("stats.rotation_rank", build_field(
                rc["olof_pct"], 3, "D-04 rotation_check (percentage only)", "stated"))

        if song_hist:
            vb.set_field("stats.premiere_count", build_field(
                song_hist["premiere_count"], 1, "D-02 song_history", "stated"))
            if song_hist.get("gate_passed"):
                titles = [s["song"] for s in song_hist["songs"] if s.get("premiere_badge")]
                if titles:
                    vb.set_field("stats.premiere_titles", build_field(
                        titles, 3, "D-02 song_history (gated)", "stated"))
            elif song_hist.get("premiere_count"):
                vb.set_field("stats.premiere_titles", build_field(
                    song_hist["premiere_count"], 3, "D-02 song_history (ungated count)",
                    "stated"))

        if lineup and setlist:
            tally = _safe(df.instrument_tally, lineup, len(setlist))
            if tally:
                vb.set_field("stats.instrument_tally", build_field(
                    dict(tally), 2, "instrument_tally parser", "stated"))

    if lineup:
        parsed = _safe(df.parse_band_lineup, lineup)
        if parsed:
            if parsed.get("members"):
                vb.set_field("band.members[]", build_field(
                    parsed["members"], 2, "parse_band_lineup", "stated"))
            if parsed.get("band_label"):
                vb.set_field("band.label", build_field(
                    parsed["band_label"], 2, "parse_band_lineup", "stated"))


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

_GENERATION_SORT_ORDER = ("master", "low_gen", "vinyl", "broadcast", "silver", "unknown")


def _sort_within_families(
    visible_members: list[tuple[int, dict, dict]], conn: sqlite3.Connection,
) -> list[tuple[int, dict, dict]]:
    """§8.4 last bullet: order a family's own members by generation, then by rank.

    Non-family (singleton) members, and the relative order between families,
    are left exactly as *visible_members* had them -- only the members that
    share one named ``fam_id`` get reordered, in place of their first member's
    original slot.

    Args:
        visible_members: :func:`_visible_members`'s result.
        conn: Open SQLite connection (for :func:`df.classify_generation`).

    Returns:
        The reordered list, same length and contents as *visible_members*.
    """
    families: dict[str, list[tuple[int, dict, dict]]] = {}
    for entry in visible_members:
        fam_id = entry[2].get("fam_id")
        if fam_id and not fam_id.startswith("__singleton_"):
            families.setdefault(fam_id, []).append(entry)

    def sort_key(entry: tuple[int, dict, dict]) -> tuple[int, float]:
        lb, member, _bucket = entry
        gen = _safe(df.classify_generation, conn, lb)
        gen_name = gen["generation"] if gen and gen.get("generation") else "unknown"
        gen_rank = (_GENERATION_SORT_ORDER.index(gen_name)
                    if gen_name in _GENERATION_SORT_ORDER else len(_GENERATION_SORT_ORDER))
        pick_rank = (member.get("pick") or {}).get("rank")
        return gen_rank, pick_rank if pick_rank is not None else float("inf")

    sorted_families = {fam_id: sorted(members, key=sort_key)
                        for fam_id, members in families.items() if len(members) >= 2}

    seen: set[str] = set()
    ordered: list[tuple[int, dict, dict]] = []
    for entry in visible_members:
        fam_id = entry[2].get("fam_id")
        if fam_id in sorted_families:
            if fam_id in seen:
                continue
            seen.add(fam_id)
            ordered.extend(sorted_families[fam_id])
        else:
            ordered.append(entry)
    return ordered


def _build_sources(vb, d1, conn, event_id, date_iso, sources, visible_members,
                    classes) -> None:
    visible_members = _sort_within_families(visible_members, conn)

    vb.set_field("sources.count", build_field(
        len(visible_members), 1, "d1.sources visible members", "stated"))

    # A one-visible-member tapematch family is still a tape group; only the family
    # band (S8.4) needs >=2 members.
    analysed_buckets = [
        b for b in sources
        if b.get("fam_id") and not b["fam_id"].startswith("__singleton_")
        and any(not m.get("private") for m in b["members"])
    ]
    named_buckets = [
        b for b in analysed_buckets
        if len([m for m in b["members"] if not m.get("private")]) >= 2
    ]
    all_visible_in_family = bool(visible_members) and all(
        b.get("fam_id") and not b["fam_id"].startswith("__singleton_") for b in sources
        for m in b["members"] if not m.get("private")
    )
    if all_visible_in_family and analysed_buckets:
        vb.set_field("sources.tape_count", build_field(
            f"{len(analysed_buckets)} tape groups", 1,
            "recording_families (every visible source analysed)", "stated"))

    for lb, member, _bucket in visible_members:
        row = vb.row("source", lb)
        row["lb_id"] = build_field(member["lb"], 1, "entries.lb_number", "stated")
        if member.get("url"):
            row["url"] = build_field(member["url"], 1, "detail_url", "stated")
        tr = _taper_field(conn, lb)
        if tr is not None:
            row["taper"] = tr

        gen = _safe(df.classify_generation, conn, lb)
        if gen and gen.get("generation") and gen["generation"] != "unknown":
            row["generation"] = build_field(
                gen["generation"], 3, "D-05 classify_generation",
                "inferred" if gen.get("basis") == "inferred" else "stated")

        medium = _safe(df.classify_medium, conn, lb)
        if medium and medium.get("evidence"):
            row["medium"] = build_field(medium["medium"], 3, "D-13 classify_medium", "stated")

        cls = classes.get(lb, {"group": "primary"})
        row["group"] = build_field(cls["group"], 2, "S8.2 fragment/G2 classification", "stated")

        if event_id is not None:
            c = cls.get("completeness")
            if c and c.get("basis") == "tracklist" and c.get("songs_total"):
                pct = round(100 * c["songs_present"] / c["songs_total"])
                row["completeness"] = build_field(
                    pct, 3, "D-01 completeness",
                    "corroborated" if c.get("confidence") == "corroborated" else "stated")

        if member.get("source_type"):
            row["type"] = build_field(member["source_type"], 1, "entries.source_type", "stated")
        quality = member.get("quality") or {}
        if quality.get("grade"):
            row["scan_grade"] = build_field(
                quality["grade"], 1, "per-LB latest scored scan", "stated")
        if member.get("rating"):
            row["lb_rating"] = build_field(member["rating"], 1, "entries.rating", "stated")

        runtime = _safe(df.parse_runtime, member.get("timing"))
        if runtime:
            row["runtime"] = build_field(runtime["total_minutes"], 2, "parse_runtime", "stated")

        fmeta = _safe(df.file_meta, conn, lb)
        if fmeta:
            if fmeta.get("resolution") and fmeta["resolution"] != "—":
                row["resolution"] = build_field(fmeta["resolution"], 2, "D-11 file_meta",
                                                 "stated")
            if fmeta.get("filesize") is not None:
                row["filesize"] = build_field(fmeta["filesize"], 3, "D-11 file_meta (TUIT)",
                                               "stated")
            if fmeta.get("disc_count") is not None:
                row["disc_count"] = build_field(fmeta["disc_count"], 3, "entries.cdr", "stated")
            if fmeta.get("filecount") is not None:
                row["filecount"] = build_field(fmeta["filecount"], 3, "D-11 file_meta", "stated")

        char = _safe(df.source_character, conn, lb)
        if char:
            if char.get("character"):
                row["character"] = build_field(char["character"], 1, "source_character parser",
                                                 "stated")
            if char.get("flags"):
                row["flags[]"] = build_field(char["flags"], 1, "source_character parser",
                                              "stated")

        lin = _safe(df.lineage_short, member.get("source_chain"))
        if lin:
            row["lineage"] = build_field(lin, 1, "lineage_short parser", "stated")

        curated = member.get("curated") or []
        if curated:
            row["curated_in[]"] = build_field(curated, 1, "curated_lists", "stated")

        pick_data = member.get("pick")
        if pick_data and pick_data.get("rank") is not None:
            row["rank"] = build_field(pick_data["rank"], 1, "show_picks.pick_rank (raw)",
                                       "stated")

        # D-12 null stub -- always the fallback.
        row["added"] = build_fallback_field(ANCHORS["source[].added"])

    for idx, bucket in enumerate(named_buckets):
        row = vb.row("family", bucket["fam_id"])
        row["id"] = build_field(bucket["fam_id"], 1, "recording_families", "stated")
        visible_lbs_in_fam = [
            int(m["lb"][3:]) for m in bucket["members"] if not m.get("private")
        ]
        taper_label = _safe(
            df.family_taper_label, conn, visible_lbs_in_fam, bucket.get("fam_conf"))
        # fam_label is tapematch's own "Family A/B" letter -- always set, so it must not
        # shadow the S8.4 taper label.
        label = taper_label or bucket.get("fam_label") or f"Family {chr(ord('A') + idx)}"
        row["label"] = build_field(
            label, 1, "recording_families + S8.4 taper-label rule", "stated")
        row["size"] = build_field(len(bucket["members"]), 1, "recording_families", "stated")
        if "fam_conf" in bucket:
            row["confidence"] = build_field(bucket["fam_conf"], 1, "tapematch_family_meta.conf",
                                             "stated")
        basis = _safe(df.family_basis, conn, bucket["fam_id"])
        if basis and basis.get("notes"):
            row["basis"] = build_field(basis["notes"], 3, "family_basis", "stated")


# ---------------------------------------------------------------------------
# Context / provenance
# ---------------------------------------------------------------------------

def _build_context(vb, d1, conn, event_id, date_iso) -> None:
    context = d1.get("context", {})
    show = d1.get("show", {})

    if context.get("chronicle"):
        vb.set_field("context.chronicle", build_field(
            context["chronicle"], 4, "olof_chronicle (verbatim)",
            "stated"))

    bobtalk_ctx = _safe(df.anchor_bobtalk, conn, event_id) if event_id is not None else None
    if bobtalk_ctx and bobtalk_ctx.get("context"):
        vb.set_field("context.bobtalk", build_field(
            bobtalk_ctx["context"], 1, "D-10 anchor_bobtalk (unanchored)", "stated"))

    session_notes: list[str] = []
    if context.get("notes"):
        session_notes.append(context["notes"])
    labels_notes = _safe(df.broadcast_set_labels, conn, event_id) if event_id is not None \
        else None
    if labels_notes and labels_notes[1]:
        session_notes.extend(labels_notes[1])
    if session_notes:
        vb.set_field("context.session_notes", build_field(
            session_notes, 1, "olof_events.notes + broadcast_set_labels", "stated"))

    if show.get("venue"):
        vb.set_field("venue.name", build_field(show["venue"], 1, "d1.show.venue", "stated"))
    if show.get("city"):
        vb.set_field("venue.city", build_field(show["city"], 1, "d1.show.city", "stated"))

    _build_venue_geo(vb, conn, show)

    if event_id is not None:
        run_ctx = _safe(df.run_context, conn, event_id)
        venue_run = run_ctx["venue_run"] if run_ctx else None
        city_hist = run_ctx["city_history"] if run_ctx else None
        if venue_run and venue_run["claims_ok"]:
            vb.set_field("venue.run_nights", build_field(
                venue_run["size"], 3, "D-07 venue_run", "stated"))
        if city_hist and city_hist.get("invariant_ok"):
            vb.set_field("venue.city_total", build_field(
                city_hist["total"], 3, "D-07 city_history", "stated"))
            vb.set_field("city_history[]", build_field(
                city_hist["rows"], 3, "D-07 city_history", "stated"))

    if d1.get("xref"):
        vb.set_field("xrefs[]", build_field(d1["xref"], 1, "_build_xref", "stated"))

    credits = [x["name"] for x in d1.get("xref", []) if x.get("is_source")]
    vb.set_field("prov.credits", build_field(
        credits or [x["name"] for x in d1.get("xref", [])], 1, "xref footer", "stated"))
    prov = d1.get("provenance", {})
    vb.set_field("prov.stamps", build_field(prov, 1, "d1.provenance", "stated"))


def _build_venue_geo(vb, conn, show) -> None:
    from backend.qc.store import quarantined
    from backend.venue_gazetteer import _norm_city, _norm_venue

    venue, city = show.get("venue"), show.get("city")
    if venue and _table_exists(conn, "venue_geocoded"):
        vnorm, cnorm = _norm_venue(venue), _norm_city(city or "")
        row = _safe(
            lambda c: c.execute(
                "SELECT * FROM venue_geocoded WHERE venue_norm = ? AND city_norm = ?",
                (vnorm, cnorm),
            ).fetchone(), conn,
        )
        if row is not None and row["lat"] is not None and row["lon"] is not None:
            quarantined_ = quarantined(conn, "venue", f"{vnorm}:{cnorm}")
            open_g1 = any(r == "R-G1" for r in quarantined_)
            if row["confidence"] in ("high", "medium") and not open_g1:
                vb.set_field("venue.coords", build_field(
                    {"lat": row["lat"], "lng": row["lon"], "basis": "venue"},
                    1, "venue_geocoded (verified)", "stated"))
                vb.set_field("venue.map", build_field(
                    "venue", 1, "compact locator (solid pin)", "stated"))
                return

    if "lat" in show and "lng" in show:
        vb.set_field("venue.coords", build_field(
            {"lat": show["lat"], "lng": show["lng"], "basis": "city_centre",
             "label": "city centre (setlist.fm)"},
            1, "setlist.fm city centroid", "stated"))
        vb.set_field("venue.map", build_field(
            "city_centre", 1, "compact locator (hollow ring)", "stated"))


def _fill_prov_local_fields(view: dict) -> None:
    keys: list[str] = []
    for key, f in view["fields"].items():
        anchor = ANCHORS.get(key)
        if anchor and anchor.tier >= 3 and f["confidence"] != "unavailable":
            keys.append(key)
    for prefix, rows in view["rows"].items():
        for row in rows:
            for sub, f in row.items():
                anchor = ANCHORS.get(f"{prefix}[].{sub}")
                if anchor and anchor.tier >= 3 and f["confidence"] != "unavailable":
                    keys.append(f"{prefix}[].{sub}")
    if keys:
        view["fields"]["prov.local_fields[]"] = build_field(
            sorted(set(keys)), 3, "registry scan", "stated")


def filter_view(view: dict, sections: set[str] | None = None,
                 local_analysis: bool = True) -> dict:
    """Presentation-layer filter for a :func:`build_view` result (D4 sibling).

    Mirrors :func:`backend.dossier.filter_dossier_sections`'s D1 filtering,
    applied to the anchor view instead. Never mutates *view*.

    Args:
        view: A dict from :func:`build_view`.
        sections: If given, drop every ``'setlist'``/``'context'``-section
            anchor whose section isn't in this set (``'header'``/``'sources'``
            anchors are never section-filtered).
        local_analysis: When False, strips every anchor marked
            ``local_analysis=True`` in :data:`ANCHORS` (plan line 788-789:
            verdict, ledger, scan grades, family confidence/basis, T4
            sentences, claim-backed anchors).

    Returns:
        A new ``{"fields": ..., "rows": ...}`` dict, plus the kept ``claims`` (a claim
        goes with its anchor; ``local_analysis=False`` also drops local-analysis claims).
    """
    def keep(key: str) -> bool:
        anchor = ANCHORS.get(key)
        if anchor is None:
            return True
        if not local_analysis and anchor.local_analysis:
            return False
        if sections is not None and anchor.section in ("setlist", "context") \
                and anchor.section not in sections:
            return False
        return True

    fields = {k: v for k, v in view.get("fields", {}).items() if keep(k)}
    rows: dict[str, list[dict]] = {}
    for prefix, prow in view.get("rows", {}).items():
        kept_subs = [sub for sub in _ROW_PREFIXES.get(prefix, []) if keep(f"{prefix}[].{sub}")]
        if not kept_subs:
            continue
        new_rows = []
        for row in prow:
            new_rows.append({sub: row[sub] for sub in kept_subs if sub in row})
        rows[prefix] = new_rows

    out = {"fields": fields, "rows": rows}
    if "claims" in view:
        out["claims"] = [
            c for c in view["claims"]
            if keep(c["anchor"]) and (local_analysis or not c["claim"]["local_analysis"])
        ]
    return out
