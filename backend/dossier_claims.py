"""Show dossier claim engine (TODO-342 dossier redesign, Phase 5, C26; audit C3).

The **only** producer of comparative or positional wording on a dossier page
("only", "highest", "best", "longest", "first", "last", "closing", "new to tour",
"since"). Every such phrase is a :class:`Claim` returned by a comparator here, and a
comparator returns a Claim only when all of these hold (audit appendix C3):

- every candidate has the compared value (no nulls);
- no compared value is ``disputed``, ``withheld`` or ``unavailable``;
- the claimed scope was fully loaded (the D-07 completeness guard for runs/tours);
- ties are reported (``*_tied`` template), never broken silently.

Otherwise the comparator returns ``None`` and the page renders the plain value.

T4 sentences (``verdict.why``, ``context.chronicle``) are slot templates filled only
by Fields and Claims -- :func:`render_segments` turns them into text segments, and a
slot filled by an ``inferred`` Field carries ``inferred=True`` so the template can put
the marker inside the sentence.

:func:`attach_claims` wires the engine into :func:`backend.dossier_anchors.build_view`:
it adds ``view["claims"]`` (``[{anchor, row, claim}]``, the list gate G7 re-checks)
and fills the two T4 anchors. Claim-backed scalar anchors keep their plain value;
the claim sits beside it in ``view["claims"]``.
"""
from __future__ import annotations

import logging
import sqlite3
import string
from collections.abc import Callable, Hashable, Mapping
from typing import Literal, TypedDict

from backend.dossier_anchors import Field, build_field

log = logging.getLogger(__name__)

ClaimKind = Literal["superlative", "exclusive", "position", "premiere", "comparison"]
ClaimScope = Literal["venue_run", "tour", "show", "visible_sources", "career"]

_UNUSABLE = ("disputed", "withheld", "unavailable")


class Claim(TypedDict):
    """One verified comparative/positional statement (audit appendix C3).

    Keys:
        kind: One of :data:`ClaimKind`.
        text_key: Template id in :data:`TEMPLATES`; a tie uses the ``*_tied`` variant.
        slots: Template slot name -> the :class:`Field` that fills it.
        scope: One of :data:`ClaimScope`.
        verified_by: Comparator id.
        ties: Other candidates tied with the subject (0 = sole leader).
        derived_from: Union of every compared Field's ``derived_from``.
        local_analysis: True when the claim compares local analysis (scan scores,
            picks, generation) -- stripped with the other local-analysis anchors.
    """

    kind: ClaimKind
    text_key: str
    slots: dict[str, Field]
    scope: ClaimScope
    verified_by: str
    ties: int
    derived_from: list[str]
    local_analysis: bool


# i18n-free template ids. Only this table may contain the comparative words (lint L2).
TEMPLATES: dict[str, str] = {
    # visible-sources superlatives / exclusives
    "best_scan": "best scanned quality of the {n} sources",
    "best_scan_tied": "tied best scanned quality of the {n} sources",
    "longest_runtime": "longest runtime of the {n} sources",
    "longest_runtime_tied": "tied longest runtime of the {n} sources",
    "highest_resolution": "highest file resolution of the {n} sources",
    "highest_resolution_tied": "tied highest file resolution of the {n} sources",
    "highest_lb_rating": "highest LB rating of the {n} sources",
    "highest_lb_rating_tied": "tied highest LB rating of the {n} sources",
    "only_soundboard": "the only soundboard of the {n} sources",
    "only_complete": "the only complete tracklist of the {n} sources",
    # pairwise (D-08)
    "higher_scan_than": "higher scanned quality than {other} ({subject_value} vs {other_value})",
    "longer_runtime_than": "longer runtime than {other} ({subject_value} vs {other_value} min)",
    "higher_resolution_than": (
        "higher file resolution than {other} ({subject_value} vs {other_value})"),
    # D-04 rotation
    "biggest_rotation": "biggest setlist rotation {scope}",
    "biggest_rotation_tied": "tied biggest setlist rotation {scope}",
    # D-07 positions
    "tour_opening": "first show of the {tour}",
    "tour_closing": "last show of the {tour}",
    "tour_position": "show {position} of {size} on the {tour}",
    "run_opening": "opening night of the {size}-night {venue} run",
    "run_closing": "closing night of the {size}-night {venue} run",
    "run_night": "night {position} of {size} at {venue}",
    # D-02 songs
    "tour_premiere": "new to the {tour}",
    "gap_since": "first performance since {last_played} ({gap} shows)",
}

# LB letter ratings, worst to best; anything else is unrankable (no claim).
_RATING_ORDER = ("F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+")
_RATING_KEY = {r: i for i, r in enumerate(_RATING_ORDER)}

# Same floor as D-08 (dossier_fields._RUNTIME_DIFF_MIN): timings are minute-rounded.
_RUNTIME_TIE_FLOOR = 2.0

_GENERATION_LABEL = {
    "master": "master", "low_gen": "low-generation copy", "silver": "silver CD",
    "vinyl": "vinyl", "broadcast": "broadcast",
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class Segment(TypedDict):
    """One piece of a rendered sentence.

    Keys:
        text: The literal text.
        slot: The slot name this text fills, or ``None`` for template text.
        inferred: The filling Field is ``inferred`` -- render the marker here.
    """

    text: str
    slot: str | None
    inferred: bool


def format_value(value: object) -> str:
    """Render a slot value: whole floats drop ``.0``, lists join with commas."""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(v) for v in value)
    return str(value)


def render_segments(template: str, slots: Mapping[str, Field]) -> list[Segment]:
    """Fill *template* from *slots* as segments.

    Args:
        template: A ``str.format``-style template (plain ``{name}`` fields only).
        slots: Slot name -> Field.

    Returns:
        Segments in order; a Field whose ``value`` is a dict renders its ``name``.

    Raises:
        KeyError: A template field has no slot.
    """
    out: list[Segment] = []
    for literal, name, _spec, _conv in string.Formatter().parse(template):
        if literal:
            out.append(Segment(text=literal, slot=None, inferred=False))
        if name is None:
            continue
        f = slots[name]
        value = f["value"]
        if isinstance(value, dict):
            value = value.get("name", value)
        out.append(Segment(text=format_value(value), slot=name,
                           inferred=f["confidence"] == "inferred"))
    return out


def claim_segments(claim: Claim) -> list[Segment]:
    """Segments for *claim*'s template."""
    return render_segments(TEMPLATES[claim["text_key"]], claim["slots"])


def segments_text(segments: list[Segment]) -> str:
    """Plain text of *segments* (BBcode / tooltips)."""
    return "".join(s["text"] for s in segments)


def claim_text(claim: Claim) -> str:
    """Plain rendered text of *claim*."""
    return segments_text(claim_segments(claim))


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------

def usable(f: Field | None) -> bool:
    """A Field may be compared: it has a value and isn't disputed/withheld/unavailable."""
    return f is not None and f["value"] is not None and f["confidence"] not in _UNUSABLE


def _fact(value: object, source: str, derived_from: list[str] | None = None) -> Field:
    return build_field(value, 3, source, "stated", derived_from)


def _derived(fields: list[Field], verified_by: str) -> list[str]:
    out: list[str] = []
    for f in fields:
        for d in f["derived_from"]:
            if d not in out:
                out.append(d)
    out.append(f"claim:{verified_by}")
    return out


def _make_claim(kind: ClaimKind, text_key: str, slots: dict[str, Field], scope: ClaimScope,
                verified_by: str, ties: int, compared: list[Field],
                local_analysis: bool) -> Claim:
    return Claim(kind=kind, text_key=text_key, slots=slots, scope=scope,
                 verified_by=verified_by, ties=ties, derived_from=_derived(compared, verified_by),
                 local_analysis=local_analysis)


def _beats(a: object, b: object, floor: float) -> bool:
    if floor:
        return a - b >= floor  # type: ignore[operator]
    return a > b  # type: ignore[operator]


def superlative(
    subject: Hashable,
    candidates: Mapping[Hashable, Field | None],
    *,
    text_key: str,
    verified_by: str,
    scope: ClaimScope = "visible_sources",
    key: Callable[[object], object] | None = None,
    tie_floor: float = 0.0,
    local_analysis: bool = True,
) -> Claim | None:
    """"*subject* has the highest value among *candidates*" (ties reported).

    Args:
        subject: The candidate the claim is about.
        candidates: Every candidate in scope (the subject included) -> its Field.
        text_key: Base template id; ``<text_key>_tied`` is used on a tie.
        verified_by: Comparator id recorded on the claim.
        scope: The claim's scope.
        key: Maps a Field value to a sortable key; ``None`` from it = no value.
        tie_floor: Values closer than this tie (0 = exact equality).
        local_analysis: Recorded on the claim.

    Returns:
        A ``superlative`` :class:`Claim` with slots ``subject`` and ``n``, or ``None``
        when there are <2 candidates, any is unusable, another beats the subject, or
        every candidate ties.
    """
    if subject not in candidates or len(candidates) < 2:
        return None
    fields = list(candidates.values())
    if not all(usable(f) for f in fields):
        return None
    keyed = {c: (key(f["value"]) if key else f["value"]) for c, f in candidates.items()}
    if any(v is None for v in keyed.values()):
        return None
    mine = keyed[subject]
    others = [v for c, v in keyed.items() if c != subject]
    if any(_beats(v, mine, tie_floor) for v in others):
        return None
    ties = sum(not _beats(mine, v, tie_floor) for v in others)
    if ties == len(others):
        return None
    slots = {"subject": candidates[subject],
             "n": _fact(len(candidates), verified_by, [f"claim:{verified_by}"])}
    return _make_claim("superlative", f"{text_key}_tied" if ties else text_key, slots, scope,
                       verified_by, ties, fields, local_analysis)  # type: ignore[arg-type]


def exclusive(
    subject: Hashable,
    flags: Mapping[Hashable, Field | None],
    *,
    text_key: str,
    verified_by: str,
    scope: ClaimScope = "visible_sources",
    local_analysis: bool = True,
) -> Claim | None:
    """"*subject* is the only candidate with the property".

    Args:
        subject: The candidate the claim is about.
        flags: Every candidate in scope -> a Field whose value is a bool.
        text_key: Template id.
        verified_by: Comparator id.
        scope: The claim's scope.
        local_analysis: Recorded on the claim.

    Returns:
        An ``exclusive`` :class:`Claim`, or ``None`` unless there are >=2 candidates,
        all usable, the subject's flag is True and every other flag is False.
    """
    if subject not in flags or len(flags) < 2:
        return None
    fields = list(flags.values())
    if not all(usable(f) for f in fields):
        return None
    if flags[subject]["value"] is not True:  # type: ignore[index]
        return None
    others = [f for c, f in flags.items() if c != subject]
    if any(f["value"] is not False for f in others):  # type: ignore[index]
        return None
    slots = {"subject": flags[subject],
             "n": _fact(len(flags), verified_by, [f"claim:{verified_by}"])}
    return _make_claim("exclusive", text_key, slots, scope,  # type: ignore[arg-type]
                       verified_by, 0, fields, local_analysis)


def comparison(
    subject: Field | None,
    other: Field | None,
    *,
    other_label: str,
    text_key: str,
    verified_by: str,
    key: Callable[[object], object] | None = None,
    floor: float = 0.0,
    local_analysis: bool = True,
) -> Claim | None:
    """"*subject* is higher than *other*" for one pair.

    Args:
        subject: The claimed-higher side.
        other: The compared side.
        other_label: How the template names *other* (e.g. ``"LB-08476"``).
        text_key: Template id (slots ``other``, ``subject_value``, ``other_value``).
        verified_by: Comparator id.
        key: Maps a value to a sortable key.
        floor: Minimum lead (0 = strictly greater).
        local_analysis: Recorded on the claim.

    Returns:
        A ``comparison`` :class:`Claim`, or ``None`` when either side is unusable or
        the subject doesn't lead by the floor.
    """
    if not (usable(subject) and usable(other)):
        return None
    a = key(subject["value"]) if key else subject["value"]  # type: ignore[index]
    b = key(other["value"]) if key else other["value"]  # type: ignore[index]
    if a is None or b is None or not _beats(a, b, floor):
        return None
    slots = {"other": _fact(other_label, verified_by, other["derived_from"]),  # type: ignore[index]
             "subject_value": subject, "other_value": other}
    return _make_claim("comparison", text_key, slots, "visible_sources",  # type: ignore[arg-type]
                       verified_by, 0, [subject, other], local_analysis)


def rotation_claim(event_id: int, rotation: Mapping | None,
                   venue_run: Mapping | None) -> Claim | None:
    """D-04: "biggest setlist rotation of the N-night <venue> run".

    Args:
        event_id: The show the claim is about.
        rotation: :func:`backend.dossier_fields.rotation_rank` output for *event_id*.
        venue_run: The matching D-07 ``venue_run``.

    Returns:
        A ``superlative`` Claim, or ``None`` unless the run has >=2 nights, passes the
        completeness guard, every night states a pct that our recompute verified, and
        no night beats this one (a tie renders ``*_tied``; an all-way tie is no claim).
    """
    if not rotation or not venue_run or venue_run["size"] < 2 or not venue_run["claims_ok"]:
        return None
    siblings = rotation["siblings"]
    if len(siblings) != venue_run["size"]:
        return None
    candidates: dict[Hashable, Field | None] = {}
    for s in siblings:
        if s["pct"] is None:
            candidates[s["event_id"]] = None
            continue
        ok = s["verified"] and not s["disputed"]
        candidates[s["event_id"]] = build_field(
            s["pct"], 1, "olof_events.rotation_pct", "corroborated" if ok else "disputed",
            ["olof_events.rotation_pct", "corroborate.rotation_check"])
    claim = superlative(event_id, candidates, text_key="biggest_rotation",
                        verified_by="D-04 rotation_rank", scope="venue_run",
                        local_analysis=False)
    if claim is not None:
        claim["slots"]["scope"] = _fact(rotation["scope"], "D-04 rotation_rank",
                                        ["olof_events"])
    return claim


def tour_position_claim(tour: Mapping | None) -> Claim | None:
    """D-07: first / last / "show N of M" on the tour (completeness-guarded).

    Args:
        tour: :class:`backend.dossier_fields.TourContext`, or ``None``.

    Returns:
        A ``position`` Claim, or ``None`` without a tour, a tour of <2 shows, or a
        failed completeness guard.
    """
    if not tour or tour["size"] < 2 or not tour["claims_ok"]:
        return None
    key = ("tour_opening" if tour["is_first"] else
           "tour_closing" if tour["is_last"] else "tour_position")
    src = "D-07 run_context.tour"
    slots = {"tour": _fact(tour["name"], src, ["olof_events.tour_name"]),
             "position": _fact(tour["position"], src, ["olof_events"]),
             "size": _fact(tour["size"], src, ["olof_events"])}
    return _make_claim("position", key, slots, "tour", src, 0, list(slots.values()), False)


def run_position_claim(venue_run: Mapping | None) -> Claim | None:
    """D-07: opening / closing / "night N of M" of a multi-night venue run.

    Args:
        venue_run: :class:`backend.dossier_fields.VenueRun`, or ``None``.

    Returns:
        A ``position`` Claim, or ``None`` for a single night or a failed guard.
    """
    if not venue_run or venue_run["size"] < 2 or not venue_run["claims_ok"]:
        return None
    pos, size = venue_run["position"], venue_run["size"]
    key = "run_opening" if pos == 1 else "run_closing" if pos == size else "run_night"
    src = "D-07 run_context.venue_run"
    slots = {"venue": _fact(venue_run["venue"], src, ["olof_events.venue"]),
             "position": _fact(pos, src, ["olof_events"]),
             "size": _fact(size, src, ["olof_events"])}
    return _make_claim("position", key, slots, "venue_run", src, 0, list(slots.values()), False)


def song_claims(song_hist: Mapping | None) -> dict[int, list[Claim]]:
    """D-02: per-position "new to the <tour>" and "first performance since" claims.

    Premiere claims need the three-part gate (``gate_passed``); gap claims need the
    ``gap_badge`` (>=100 shows, no open R-O1 in the span). Career debuts produce no
    claim: nothing guarantees every earlier concert parsed completely.

    Args:
        song_hist: :func:`backend.dossier_fields.song_history` output, or ``None``.

    Returns:
        ``{position: [Claim, ...]}`` for positions with at least one claim.
    """
    out: dict[int, list[Claim]] = {}
    if not song_hist:
        return out
    src = "D-02 song_history"
    for s in song_hist["songs"]:
        claims: list[Claim] = []
        if song_hist["gate_passed"] and s["premiere_badge"] and song_hist["tour_name"]:
            slots = {"tour": _fact(song_hist["tour_name"], src, ["olof_events.tour_name"])}
            claims.append(_make_claim("premiere", "tour_premiere", slots, "tour", src, 0,
                                      [_fact(True, src, ["song_performances", "setlistfm"])],
                                      False))
        if s["gap_badge"] and s["last_played"] and s["gap_shows"] is not None:
            slots = {"last_played": _fact(s["last_played"], src, ["song_performances"]),
                     "gap": _fact(s["gap_shows"], src, ["song_performances"])}
            claims.append(_make_claim("position", "gap_since", slots, "career", src, 0,
                                      list(slots.values()), False))
        if claims:
            out[s["position"]] = claims
    return out


# ---------------------------------------------------------------------------
# Visible-source comparisons (D-08 axes)
# ---------------------------------------------------------------------------

def _rating_key(value: object) -> int | None:
    return _RATING_KEY.get(str(value).strip().upper()) if value is not None else None


def _resolution_key(value: object) -> tuple[int, int] | None:
    from backend.dossier_fields import _resolution_key as rk

    return rk(value if isinstance(value, str) else None)


class SourceAxes(TypedDict):
    """Per visible source, one Field per comparable axis (``None`` = no value)."""

    lb_rating: dict[int, Field | None]
    scan: dict[int, Field | None]
    runtime: dict[int, Field | None]
    resolution: dict[int, Field | None]
    soundboard: dict[int, Field | None]
    complete: dict[int, Field | None]


def source_axes(conn: sqlite3.Connection, d1: dict, view: dict,
                visible_lbs: list[int]) -> SourceAxes:
    """Collect the D-08 axis values for every visible source.

    Runtime, LB rating and completeness come from the view's ``source`` rows; scan
    score from the D1 member's per-LB scored scan; resolution from the TUIT file record
    (``file_meta.file_res``), ``disputed`` when :func:`file_format_check` disagrees;
    soundboard from ``entries.source_type`` (a missing type is no value).

    Args:
        conn: Open connection.
        d1: The D1 payload.
        view: The view under construction (``rows["source"]`` filled).
        visible_lbs: The visible source set.

    Returns:
        A :class:`SourceAxes`.
    """
    from backend import dossier_fields as df
    from backend.qc.corroborate import file_format_check

    members = {int(m["lb"][3:]): m for b in d1.get("sources", []) for m in b["members"]}
    rows = {int(r["lb_id"]["value"][3:]): r for r in view["rows"].get("source", [])
            if r.get("lb_id") and r["lb_id"]["value"]}
    axes = SourceAxes(lb_rating={}, scan={}, runtime={}, resolution={}, soundboard={},
                      complete={})
    for lb in visible_lbs:
        row, member = rows.get(lb, {}), members.get(lb, {})
        rating = row.get("lb_rating")
        axes["lb_rating"][lb] = rating if rating and rating["source"] else None
        runtime = row.get("runtime")
        axes["runtime"][lb] = runtime if runtime and runtime["source"] else None
        score = (member.get("quality") or {}).get("score")
        axes["scan"][lb] = (build_field(score, 1, "per-LB latest scored scan", "stated",
                                        ["quality_recording_scores"])
                            if score is not None else None)
        try:
            res = df.file_meta(conn, lb)["file_res"]
            disputed = file_format_check(conn, lb)["agrees"] is False
        except sqlite3.OperationalError:
            res, disputed = None, False
        axes["resolution"][lb] = (build_field(res, 2, "D-11 file_meta.file_res",
                                              "disputed" if disputed else "stated",
                                              ["tuit_recordings"])
                                  if res else None)
        stype = member.get("source_type")
        axes["soundboard"][lb] = (build_field(stype == "Soundboard", 1, "entries.source_type",
                                              "stated", ["entries.source_type"])
                                  if stype else None)
        comp = row.get("completeness")
        axes["complete"][lb] = (build_field(comp["value"] == 100, 3, "D-01 completeness",
                                            comp["confidence"], comp["derived_from"])
                                if comp and comp["source"] else None)
    return axes


_AXIS_SUPERLATIVE: dict[str, dict] = {
    "lb_rating": {"text_key": "highest_lb_rating", "key": _rating_key, "local": False},
    "scan": {"text_key": "best_scan", "local": True},
    "runtime": {"text_key": "longest_runtime", "tie_floor": _RUNTIME_TIE_FLOOR, "local": False},
    "resolution": {"text_key": "highest_resolution", "key": _resolution_key, "local": False},
}
_AXIS_EXCLUSIVE = {"soundboard": "only_soundboard", "complete": "only_complete"}
_PAIR_TEXT = {"scan": "higher_scan_than", "runtime": "longer_runtime_than",
              "resolution": "higher_resolution_than"}


def source_claims(subject: int, axes: SourceAxes) -> dict[str, Claim]:
    """Every visible-sources superlative/exclusive claim *subject* earns, by axis."""
    out: dict[str, Claim] = {}
    for axis, spec in _AXIS_SUPERLATIVE.items():
        values = axes[axis]  # type: ignore[literal-required]
        c = superlative(subject, values, text_key=spec["text_key"],
                        verified_by=f"D-08 {axis}", key=spec.get("key"),
                        tie_floor=spec.get("tie_floor", 0.0), local_analysis=spec["local"])
        if c:
            out[axis] = c
    for axis, text_key in _AXIS_EXCLUSIVE.items():
        c = exclusive(subject, axes[axis], text_key=text_key,  # type: ignore[literal-required]
                      verified_by=f"D-08 {axis}", local_analysis=axis == "complete")
        if c:
            out[axis] = c
    return out


def pair_claim(axis: str, subject: int, other: int, axes: SourceAxes) -> Claim | None:
    """A pairwise "higher/longer than" claim on a directed D-08 axis, or ``None``."""
    if axis not in _PAIR_TEXT:
        return None
    return comparison(
        axes[axis].get(subject), axes[axis].get(other),  # type: ignore[literal-required]
        other_label=f"LB-{other:05d}", text_key=_PAIR_TEXT[axis], verified_by=f"D-08 {axis}",
        key=_resolution_key if axis == "resolution" else None,
        floor=_RUNTIME_TIE_FLOOR if axis == "runtime" else 0.0,
        local_analysis=axis == "scan",
    )


# ---------------------------------------------------------------------------
# T4 slot templates
# ---------------------------------------------------------------------------

def _sentence(clauses: list[list[Segment]], claims: list[Claim]) -> dict:
    segments: list[Segment] = []
    for i, clause in enumerate(clauses):
        if i:
            segments.append(Segment(text="; ", slot=None, inferred=False))
        segments.extend(clause)
    if segments:
        segments.append(Segment(text=".", slot=None, inferred=False))
    return {"segments": segments, "text": segments_text(segments),
            "claims": [c["text_key"] for c in claims]}


def _clause(template: str, **slots: Field) -> list[Segment]:
    return render_segments(template, slots)


def verdict_why(fields: Mapping[str, Field], claims: Mapping[str, Claim]) -> dict | None:
    """``verdict.why``: why the pick is the pick, from pick Fields and its claims only.

    Args:
        fields: ``view["fields"]``.
        claims: The pick's :func:`source_claims` result.

    Returns:
        ``{segments, text, claims}``, or ``None`` when no clause has a usable input.
    """
    clauses: list[list[Segment]] = []
    used: list[Claim] = []

    def with_claim(clause: list[Segment], axis: str) -> list[Segment]:
        if axis in claims:
            used.append(claims[axis])
            return clause + [Segment(text=", ", slot=None, inferred=False)] + claim_segments(
                claims[axis])
        return clause

    rating = fields.get("pick.lb_rating")
    if usable(rating):
        clauses.append(with_claim(_clause("LB rating {rating}", rating=rating), "lb_rating"))
    grade = fields.get("pick.scan_grade")
    if usable(grade):
        clauses.append(with_claim(_clause("scanned quality {grade}", grade=grade), "scan"))
    elif "scan" in claims:
        used.append(claims["scan"])
        clauses.append(claim_segments(claims["scan"]))
    taper = fields.get("pick.taper.name")
    if usable(taper):
        clauses.append(_clause("taped by {taper}", taper=taper))
    gen = fields.get("pick.generation")
    if usable(gen):
        label = dict(gen)  # type: ignore[arg-type]
        raw = gen["value"]  # type: ignore[index]
        label["value"] = _GENERATION_LABEL.get(raw, str(raw))
        clauses.append(_clause("{generation} source", generation=label))  # type: ignore[arg-type]
    for axis in ("runtime", "resolution", "soundboard", "complete"):
        if axis in claims:
            used.append(claims[axis])
            clauses.append(claim_segments(claims[axis]))
    curated = fields.get("pick.curated_in[]")
    if usable(curated):
        names = dict(curated)  # type: ignore[arg-type]
        names["value"] = [c.get("list_label", "") for c in curated["value"]]  # type: ignore[index]
        clauses.append(_clause("in {lists}", lists=names))  # type: ignore[arg-type]
    if not clauses:
        return None
    return _sentence(clauses, used)


def chronicle(fields: Mapping[str, Field], run_claim: Claim | None,
              tour_claim: Claim | None) -> dict | None:
    """``context.chronicle``: run and tour position claims, then Olof's line verbatim.

    Args:
        fields: ``view["fields"]`` (``context.chronicle`` still holds the verbatim line).
        run_claim: :func:`run_position_claim` result.
        tour_claim: :func:`tour_position_claim` result.

    Returns:
        ``{segments, text, claims}``, or ``None`` when there is nothing to say.
    """
    clauses: list[list[Segment]] = []
    used = [c for c in (run_claim, tour_claim) if c]
    for c in used:
        clauses.append(claim_segments(c))
    if clauses:
        first = clauses[0][0]
        clauses[0][0] = Segment(text=first["text"][:1].upper() + first["text"][1:],
                                slot=first["slot"], inferred=first["inferred"])
    sentence = _sentence(clauses, used) if clauses else {"segments": [], "text": "",
                                                        "claims": []}
    line = fields.get("context.chronicle")
    if usable(line) and isinstance(line["value"], str):  # type: ignore[index]
        extra = render_segments("{chronicle}", {"chronicle": line})  # type: ignore[dict-item]
        if sentence["segments"]:
            extra.insert(0, Segment(text=" ", slot=None, inferred=False))
        sentence["segments"].extend(extra)
        sentence["text"] = segments_text(sentence["segments"])
    return sentence if sentence["segments"] else None


# ---------------------------------------------------------------------------
# View integration
# ---------------------------------------------------------------------------

def attach_claims(view: dict, d1: dict, conn: sqlite3.Connection, ctx: Mapping) -> None:
    """Run every comparator for a built view; add ``view["claims"]`` and the T4 anchors.

    Never raises on missing data: a comparator input that fails to load yields no claim.

    Args:
        view: :func:`backend.dossier_anchors.build_view`'s ``{fields, rows}``, mutated.
        d1: The D1 payload.
        conn: Open connection.
        ctx: Intermediate results the builders stashed: ``event_id``, ``visible_lbs``,
            ``run_ctx``, ``song_hist``, ``cmp_src``, ``pick_lb``.
    """
    from backend import dossier_fields as df

    fields = view["fields"]
    claims: list[dict] = []

    def add(anchor: str, claim: Claim | None, row: object = None) -> None:
        if claim is not None:
            claims.append({"anchor": anchor, "row": row, "claim": claim})

    run_ctx = ctx.get("run_ctx") or {}
    venue_run, tour = run_ctx.get("venue_run"), run_ctx.get("tour")
    event_id = ctx.get("event_id")

    if venue_run and event_id is not None and venue_run["size"] >= 2:
        try:
            rot = df.rotation_rank(conn, event_id, venue_run)
        except sqlite3.OperationalError as exc:
            log.debug("dossier_claims: rotation_rank degraded (%s)", exc)
            rot = None
        add("stats.rotation_rank", rotation_claim(event_id, rot, venue_run))

    run_claim, tour_claim = run_position_claim(venue_run), tour_position_claim(tour)
    add("context.chronicle", run_claim)
    add("context.chronicle", tour_claim)

    for pos, song in song_claims(ctx.get("song_hist")).items():
        for c in song:
            add("song[].premiere" if c["kind"] == "premiere" else "song[].gap", c, pos)

    visible = list(ctx.get("visible_lbs") or [])
    pick = ctx.get("pick_lb")
    axes = source_axes(conn, d1, view, visible) if visible else None
    pick_claims: dict[str, Claim] = {}
    if axes and pick in visible:
        pick_claims = source_claims(pick, axes)
        for c in pick_claims.values():
            add("verdict.why", c)

    cmp_src = ctx.get("cmp_src")
    if axes and cmp_src and not cmp_src.get("collapsed") and cmp_src.get("pick") == pick:
        runner = cmp_src.get("runner_up")
        for diff in cmp_src.get("diffs", []):
            if diff["leader"] and runner is not None:
                subj, other = (pick, runner) if diff["leader"] == "pick" else (runner, pick)
                add("verdict.vs_runner_up", pair_claim(diff["field"], subj, other, axes),
                    diff["field"])
        for alt in cmp_src.get("alternates", []):
            lb = alt["lb_number"]
            add("verdict.alternates[]", pair_claim(alt["axis"], lb, pick, axes), lb)
            alt_claim = source_claims(lb, axes).get(alt["axis"])
            add("verdict.alternates[]", alt_claim, lb)

    why = verdict_why(fields, pick_claims)
    if why is not None:
        fields["verdict.why"] = build_field(why, 4, "claim-engine slot template (verdict_why)",
                                            "stated", ["claim:verdict_why"])
    chron = chronicle(fields, run_claim, tour_claim)
    if chron is not None:
        derived = ["claim:chronicle"] + (
            ["olof_chronicle"] if fields.get("context.chronicle", {}).get("source") else [])
        fields["context.chronicle"] = build_field(
            chron, 4, "slot template (run/tour claims + Olof chronicle)", "stated", derived)

    view["claims"] = claims
