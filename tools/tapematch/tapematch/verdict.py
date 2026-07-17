"""verdict.py — single source of truth for pairwise clustering decisions.

Implements Task 1.3 of ``instructions/CC_TAPEMATCH_FIXES.md``: the clustering
verdict is extracted here as pure functions so the identical logic runs against
live session results (``cli.py`` clustering) and against stored ``pairs`` rows
(``regression.py`` cached scoring).

Design
------
The pairwise link predicate mirrors ``match.cluster``'s OR-logic exactly:

    link(pair) if
        corr          >= match.cluster_threshold             (primary residual corr), or
        windowed_frac >= secondary_match.coverage_threshold  (windowed coverage), or
        hiss_frac     >= secondary_match.hiss_merge_frac AND
        hiss_median   >= secondary_match.hiss_merge_median    (hiss frac + median guard), or
        fp_score      >= fp_threshold(pair, cfg, lineage)     (spectral fingerprint Dice), or
        fp_triplet_score >= fingerprint.triplet.cluster_threshold  (ratio-invariant
                          triplet fingerprint — Task 7; the sole surviving signal for
                          Task 5.3 speed-unknown Cat-1 pairs), or
        addon_links.rule_a / rule_b / rule_c   (CC_TAPEMATCH_ADDON.md Task 5,
                          see below)

``addon_links`` (CC_TAPEMATCH_ADDON.md Task 5) is a dedicated evidence-
combination block, evaluated after every path above, gathering the Tier A/B
signals:

  * **Rule A (lone lineage)** — ``flaw_match_score >= addon_links.rule_a.t_flaw``
    AND both-side ``flaw_n_events_{a,b} >= addon_links.rule_a.min_events``.
    This is the **sole canonical flaw-fingerprint merge path**. Task 2.3
    originally wired a standalone ``flaw_fingerprint``-gated OR-path directly
    into this predicate; Task 5 folds it into Rule A and removes the
    standalone leg, so there is exactly one flaw merge path, not two
    competing ones. ``flaw_fingerprint.enabled`` still independently gates
    whether the metric is *computed* at all (``cli.py``); ``addon_links.
    rule_a.enabled`` gates whether it may *merge*.
  * **Rule B (two-leg)** — ``spec_stationarity >= addon_links.rule_b.t_stat``
    AND ``env_corr >= addon_links.rule_b.t_env``. Conjunctive by construction
    (both signals are individually banned from a lone-merge path — Task 3.2 /
    Task 4.2 — so this is their only route into a verdict).
  * **Rule C (belt-and-braces, Tier B/C)** — ``emb_score >=
    addon_links.rule_c.t_emb`` AND (``flaw_match_score >=
    addon_links.rule_c.t_flaw_weak`` OR ``spec_stationarity >=
    addon_links.rule_c.t_stat``). ``emb_score`` (Task 6) has no persisted
    column yet, so it is always absent/``None`` today — the rule reads it via
    plain ``dict.get`` and abstains defensively, the same NULL-safety as
    every other leg.
  * **Rule D (embedding both-convention)** — ``emb_score >=
    addon_links.rule_d.t_emb`` AND ``emb_score_global >=
    addon_links.rule_d.t_emb``, cross-source pairs only (``lb_a != lb_b``).
    Calibrated 2026-07-04 (see ``config.yaml``): requiring BOTH the aligned
    +/-2s-window cosine and the whole-recording global cosine-max is
    zero-new-FP on the frozen sets; the lone/aligned-only variant produced a
    transitive false-positive chain and was rejected.

Every rule is independently gated on its own ``enabled`` flag and NULL on any
leg means that rule abstains (no merge) — it never falls back to 0.0. No rule
reads ``lb_says_same`` or ``entry_lineage`` (keeps the frozen regression set a
valid negative control). All four rules default ``enabled: false`` in the
committed config, so with the committed config every historical/live verdict
is byte-identical to pre-Task-5 behaviour.

The only behavioural difference from the historical scalar ``f_threshold`` is
that the fingerprint threshold is now *per-pair* via :func:`fp_threshold`
(Tasks 3.2 / 4.1): a staircase-flagged or curator-claimed pair may use a lower
fingerprint bar. With the default config (no staircase/curator override keys)
``fp_threshold`` returns ``fingerprint.cluster_threshold`` for every pair, so
behaviour is byte-identical to the pre-refactor code.

Metrics that were never persisted to the ``pairs`` table (``windowed_frac``,
``hiss_frac``, ``hiss_median``, ``fp_score``) arrive as ``None`` when a metrics
dict is built from a stored DB row; the predicate simply skips any ``None``
signal. Only ``corr`` is reproducible from historical DB rows — which is why
Tasks 3/4 require adding + repopulating those columns before their cached gate
is valid (see the spec and CHANGELOG).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

# Verdict string constants — match the values stored in pairs.tapematch_verdict.
SAME_FAMILY = "same_family"
DIFFERENT_FAMILY = "different_family"

# Metric keys a pair dict may carry. Any may be None/absent (signal unavailable).
METRIC_KEYS = (
    "corr",
    "windowed_frac",
    "hiss_frac",
    "hiss_median",
    "fp_score",
    "fp_triplet_score",
    "flaw_match_score",
    "flaw_n_events_a",
    "flaw_n_events_b",
    "spec_stationarity",
    "env_corr",
    # Tier B pretrained-embedding scores (CC_TAPEMATCH_ADDON.md Task 6).
    # ``emb_score`` = aligned +/-2s-window cosine; ``emb_score_global`` =
    # whole-recording global cosine-max. Populated offline by
    # persist_emb_scores.py onto ``pairs.emb_score`` / ``pairs.emb_score_global``;
    # NULL/absent on every row persist_emb_scores.py hasn't reached yet. Registered
    # here so both round-trip through the cached-scoring metrics dict.
    "emb_score",
    "emb_score_global",
    "speed_kind_a",
    "speed_kind_b",
    "hf_ceiling_hz_a",
    "hf_ceiling_hz_b",
    "nyquist_capped_a",
    "nyquist_capped_b",
    "lb_a",
    "lb_b",
)


def _is_staircase(pair: Mapping, fp_cfg: Mapping | None = None) -> bool:
    """True if the pair qualifies for the staircase fingerprint relaxation.

    The substring test matches the historical token 'staircase/splice' and any
    future 'staircase*' variant, mirroring the spec's ``"staircase" in kind``.

    ``fingerprint.staircase_scope`` (2026-07-16, TODO-234/235 mitigation (b) —
    see CALIBRATION_PROGRESS.md "EDGE CASE OBSERVED IN THE WILD 2026-07-11"):

      * ``"source"`` (default, historical) — either side staircase-flagged.
        Hazard: one staircase pair inside a family lowers the fp bar for that
        family's edges to every unrelated source on the date.
      * ``"pair"`` — BOTH sides must carry the flag, so the relaxation stays
        scoped to the re-tracked pair itself.
    """
    a = "staircase" in (pair.get("speed_kind_a") or "")
    b = "staircase" in (pair.get("speed_kind_b") or "")
    scope = (fp_cfg or {}).get("staircase_scope", "source")
    if scope == "pair":
        return a and b
    return a or b


def _staircase_corroborated(pair: Mapping, fp_cfg: Mapping) -> bool:
    """Mitigation (a) for the staircase-relaxed fp false-merge hazard.

    A merge that exists ONLY because the staircase relaxation lowered the
    fingerprint bar must be corroborated by a non-fingerprint signal
    (fingerprint is confirmatory-only per WORKFLOW.md): ``windowed_frac`` or
    ``hiss_frac`` at/above its configured floor. ``None`` (signal never
    computed) counts as no corroboration — precision-safe by construction.

    Gate off (``fingerprint.staircase_corroboration.enabled`` absent/false)
    returns True, preserving historical behaviour.
    """
    sc = fp_cfg.get("staircase_corroboration") or {}
    if not sc.get("enabled"):
        return True
    min_wf = sc.get("min_windowed_frac")
    min_hf = sc.get("min_hiss_frac")
    wf = pair.get("windowed_frac")
    hf = pair.get("hiss_frac")
    if min_wf is not None and wf is not None and wf >= min_wf:
        return True
    if min_hf is not None and hf is not None and hf >= min_hf:
        return True
    return False


def _lineage_key(pair: Mapping) -> tuple[int, int] | None:
    a, b = pair.get("lb_a"), pair.get("lb_b")
    if a is None or b is None:
        return None
    return (min(a, b), max(a, b))


def fp_threshold(pair: Mapping, cfg: Mapping,
                 lineage: Iterable[tuple[int, int]] | None = None, *,
                 staircase: bool = True) -> float:
    """Return the fingerprint Dice threshold that applies to this pair.

    Base = ``fingerprint.cluster_threshold``. Lowered when:
      * the pair qualifies under ``staircase_scope`` ->
        ``cluster_threshold_staircase`` (Task 3.2; scope per :func:`_is_staircase`)
      * the pair is claimed same-source by curator lineage text ->
        ``min(applicable, cluster_threshold_curator)`` (Task 4.1)

    Both overrides default to the base threshold when their config key is
    absent, so an un-augmented ``config.yaml`` yields the historical single
    scalar for every pair.

    ``staircase=False`` skips the staircase relaxation — used by
    :func:`pair_links` to detect whether a merge *relies* on it (mitigation
    (a): such merges must be corroborated by a non-fingerprint signal).
    """
    fp_cfg = cfg.get("fingerprint", {}) or {}
    base = fp_cfg.get("cluster_threshold", 0.0)
    thr = base
    if staircase and _is_staircase(pair, fp_cfg):
        thr = fp_cfg.get("cluster_threshold_staircase", base)
    # Curator lineage claim is a prior, not a label: it only *lowers* the bar,
    # audio must still cross it (a text claim with fp_score 0.10 stays different).
    if lineage is not None:
        key = _lineage_key(pair)
        if key is not None and key in lineage:
            curator = fp_cfg.get("cluster_threshold_curator", thr)
            thr = min(thr, curator)
    return thr


def _effective_hiss_median(pair: Mapping, sec: Mapping) -> float | None:
    """Hiss-median merge threshold for this pair (Task 4.2 lo-fi relaxation).

    Returns ``hiss_merge_median_lofi`` only when BOTH sides have a real
    ``hf_ceiling_hz`` below ``hiss_lofi_ceiling_hz`` AND neither reading is
    nyquist-capped (a capped ceiling is not a real measurement — treat as
    unknown and keep the standard 0.65 guard). Otherwise ``hiss_merge_median``.
    """
    base = sec.get("hiss_merge_median", None)
    lofi = sec.get("hiss_merge_median_lofi", None)
    ceil = sec.get("hiss_lofi_ceiling_hz", None)
    if lofi is None or ceil is None:
        return base
    hca, hcb = pair.get("hf_ceiling_hz_a"), pair.get("hf_ceiling_hz_b")
    if hca is None or hcb is None:
        return base
    if pair.get("nyquist_capped_a") or pair.get("nyquist_capped_b"):
        return base  # capped reading is unknown, not a real low ceiling
    if hca < ceil and hcb < ceil:
        return lofi
    return base


def _rule_a_lone_lineage(pair: Mapping, al_cfg: Mapping) -> bool:
    """Rule A (CC_TAPEMATCH_ADDON.md Task 5.1) — lone shared-flaw lineage merge.

    The sole canonical ``flaw_match_score`` verdict path (see module
    docstring for the Task 2.3 -> Task 5 reconciliation). NULL on either leg
    abstains; never coerces ``None`` to ``0.0``.
    """
    ra = al_cfg.get("rule_a", {}) or {}
    if not ra.get("enabled"):
        return False
    t_flaw = ra.get("t_flaw")
    min_events = ra.get("min_events")
    flaw = pair.get("flaw_match_score")
    na, nb = pair.get("flaw_n_events_a"), pair.get("flaw_n_events_b")
    if t_flaw is None or flaw is None or flaw < t_flaw:
        return False
    if min_events is None or na is None or nb is None:
        return False
    return na >= min_events and nb >= min_events


def _rule_b_two_leg(pair: Mapping, al_cfg: Mapping) -> bool:
    """Rule B (Task 5.1) — spec_stationarity AND env_corr, both required.

    Conjunctive by construction: this is the only route either signal has
    into a verdict (both are individually banned from a lone-merge path —
    spec 3.2 / 4.2). NULL on either leg abstains.
    """
    rb = al_cfg.get("rule_b", {}) or {}
    if not rb.get("enabled"):
        return False
    t_stat = rb.get("t_stat")
    t_env = rb.get("t_env")
    stat = pair.get("spec_stationarity")
    env = pair.get("env_corr")
    if t_stat is None or t_env is None or stat is None or env is None:
        return False
    return stat >= t_stat and env >= t_env


def _rule_c_belt_and_braces(pair: Mapping, al_cfg: Mapping) -> bool:
    """Rule C (Task 5.1) — emb_score AND (flaw_match_score OR spec_stationarity).

    ``emb_score`` (Task 6) has no persisted column yet, so ``pair.get(
    "emb_score")`` returns ``None`` for every pair today regardless of
    whether the key is present in the mapping at all — the rule abstains
    defensively rather than raising. Same NULL-safety once the column exists
    and the metric is merely un-populated on a given row.
    """
    rc = al_cfg.get("rule_c", {}) or {}
    if not rc.get("enabled"):
        return False
    t_emb = rc.get("t_emb")
    emb = pair.get("emb_score")
    if t_emb is None or emb is None or emb < t_emb:
        return False
    t_flaw_weak = rc.get("t_flaw_weak")
    t_stat = rc.get("t_stat")
    flaw = pair.get("flaw_match_score")
    stat = pair.get("spec_stationarity")
    leg_flaw = t_flaw_weak is not None and flaw is not None and flaw >= t_flaw_weak
    leg_stat = t_stat is not None and stat is not None and stat >= t_stat
    return leg_flaw or leg_stat


def _rule_d_emb_both(pair: Mapping, al_cfg: Mapping) -> bool:
    """Rule D (embedding both-convention gate, CC_TAPEMATCH_ADDON.md Task 6
    follow-on) — ``emb_score`` AND ``emb_score_global`` both required.

    CALIBRATED 2026-07-04 full-frozen-set sweep (``emb_fullset_eval.py``,
    2245 pairs / 2465 nmfp-embedded sources): requiring BOTH the aligned
    +/-2s-window cosine (``emb_score``) and the whole-recording global
    cosine-max (``emb_score_global``) to clear ``t_emb`` is zero-new-FP on
    both frozen regression sets. The lone/aligned-only variant (``emb_score``
    alone) was REJECTED — it produced a transitive false-positive chain
    (LB-789/LB-2898) via guard-masking-style clustering at every threshold
    tried. See ``config.yaml``'s ``addon_links.rule_d`` block for the full
    sweep writeup.

    NULL on either leg abstains — never coerced to 0.0. Self-pairs
    (``lb_a == lb_b``, two versions of the same recording) never fire: this
    rule is evidence of a *cross-source* merge, and a recording trivially
    matches itself, which would be meaningless (and precision-unsafe) signal.
    """
    rd = al_cfg.get("rule_d", {}) or {}
    if not rd.get("enabled"):
        return False
    lb_a, lb_b = pair.get("lb_a"), pair.get("lb_b")
    if lb_a is None or lb_b is None or lb_a == lb_b:
        return False
    t_emb = rd.get("t_emb")
    emb = pair.get("emb_score")
    emb_g = pair.get("emb_score_global")
    if t_emb is None or emb is None or emb_g is None:
        return False
    return emb >= t_emb and emb_g >= t_emb


def _addon_links(pair: Mapping, cfg: Mapping) -> bool:
    """Evaluate all Task 5 ``addon_links`` rules; True if any fires.

    Every rule is independently gated on its own ``enabled`` flag (default
    absent/false), so with the committed config (no ``addon_links`` block, or
    a block with every rule ``enabled: false``) this always returns False —
    byte-identical to pre-Task-5 behaviour.
    """
    al_cfg = cfg.get("addon_links", {}) or {}
    return (_rule_a_lone_lineage(pair, al_cfg)
            or _rule_b_two_leg(pair, al_cfg)
            or _rule_c_belt_and_braces(pair, al_cfg)
            or _rule_d_emb_both(pair, al_cfg))


def pair_links(pair: Mapping, cfg: Mapping,
               lineage: Iterable[tuple[int, int]] | None = None) -> bool:
    """Pure pairwise link predicate — mirrors ``match.cluster``'s OR-logic.

    A ``None`` signal is treated as "unavailable" and cannot fire a link; this
    lets the same predicate run against a full live-results dict or a
    corr-only historical DB row.
    """
    m_thr = (cfg.get("match", {}) or {}).get("cluster_threshold", None)
    corr = pair.get("corr")
    if m_thr is not None and corr is not None and corr >= m_thr:
        return True

    sec = cfg.get("secondary_match", {}) or {}
    wc_thr = sec.get("coverage_threshold", 0.0)
    wf = pair.get("windowed_frac")
    if wc_thr and wf is not None and wf >= wc_thr:
        return True

    hm_frac = sec.get("hiss_merge_frac", None)
    hm_med = _effective_hiss_median(pair, sec)
    hf, hmed = pair.get("hiss_frac"), pair.get("hiss_median")
    if (hm_frac is not None and hm_med is not None and hf is not None
            and hmed is not None and hf >= hm_frac and hmed >= hm_med):
        return True

    fp_thr = fp_threshold(pair, cfg, lineage)
    fp = pair.get("fp_score")
    if fp_thr and fp_thr > 0.0 and fp is not None and fp >= fp_thr:
        # Corroboration gate (mitigation (a), 2026-07-16): if the merge clears
        # only the staircase-RELAXED bar (it would fail without the staircase
        # relaxation), a non-fingerprint signal must corroborate — fingerprint
        # is confirmatory-only per WORKFLOW.md, and the ~0.40 same-show musical
        # floor sits exactly at the relaxed bar. A blocked fp leg falls through
        # to the remaining OR-paths rather than returning False.
        if fp >= fp_threshold(pair, cfg, lineage, staircase=False):
            return True
        if _staircase_corroborated(pair, cfg.get("fingerprint", {}) or {}):
            return True

    # Ratio-invariant triplet fingerprint (Task 7). An OR-path with its own
    # threshold, applied to ALL pairs but especially the sole surviving signal for
    # speed-unknown Cat-1 pairs (Task 5.3). Inert on historical rows: the column is
    # NULL there, so ``fp_triplet_score`` is None and cannot fire a link.
    tri_cfg = (cfg.get("fingerprint", {}) or {}).get("triplet", {}) or {}
    if tri_cfg.get("enabled"):
        tri_thr = tri_cfg.get("cluster_threshold", None)
        tri = pair.get("fp_triplet_score")
        if tri_thr is not None and tri_thr > 0.0 and tri is not None and tri >= tri_thr:
            return True

    # Task 5 evidence-combination rules (addon_links: Rule A/B/C). Rule A is
    # the sole canonical flaw-fingerprint merge path (see module docstring —
    # it supersedes the Task 2.3 standalone OR-leg). Inert on historical/
    # dormant rows: every rule defaults enabled:false and abstains on NULL.
    if _addon_links(pair, cfg):
        return True

    return False


def cluster_verdicts(pairs: list[Mapping], cfg: Mapping,
                     lineage: Iterable[tuple[int, int]] | None = None,
                     ) -> dict[tuple, str]:
    """Union-find over a date's pairs; return per-pair family verdict.

    ``pairs`` is every observed pair for one concert date. Returns a mapping
    ``{(lb_a, lb_b): SAME_FAMILY | DIFFERENT_FAMILY}`` where a pair is
    SAME_FAMILY iff its two members land in the same connected component after
    linking every pair for which :func:`pair_links` is true. This makes the
    verdict transitive — identical to the session's family clustering — rather
    than a per-row decision.

    Keys are normalized ``(min, max)`` of the pair's ``lb_a``/``lb_b``.
    """
    # Collect node ids.
    nodes: dict[int, int] = {}

    def node(x: int) -> int:
        if x not in nodes:
            nodes[x] = len(nodes)
        return nodes[x]

    parent: list[int] = []

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    # Register all nodes first so parent[] is sized correctly.
    for p in pairs:
        a, b = p.get("lb_a"), p.get("lb_b")
        if a is None or b is None:
            continue
        node(a)
        node(b)
    parent = list(range(len(nodes)))

    for p in pairs:
        a, b = p.get("lb_a"), p.get("lb_b")
        if a is None or b is None:
            continue
        if pair_links(p, cfg, lineage):
            union(node(a), node(b))

    out: dict[tuple, str] = {}
    for p in pairs:
        a, b = p.get("lb_a"), p.get("lb_b")
        if a is None or b is None:
            continue
        key = (min(a, b), max(a, b))
        same = find(node(a)) == find(node(b))
        out[key] = SAME_FAMILY if same else DIFFERENT_FAMILY
    return out


def load_lineage_pairs(db_path: str | Path) -> set[tuple[int, int]]:
    """Return unordered ``(lb_lo, lb_hi)`` pairs where either side's
    ``same_as_lb`` lists the other (Task 4.1).

    Reads the ``entry_lineage`` table of the LosslessBob DB. Returns an empty
    set if the table is absent (feature simply inactive).
    """
    out: set[tuple[int, int]] = set()
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            cur = conn.execute(
                "SELECT lb_number, same_as_lb FROM entry_lineage "
                "WHERE same_as_lb IS NOT NULL AND same_as_lb != '[]'")
        except sqlite3.OperationalError:
            return out
        for lb, same in cur:
            if not same:
                continue
            try:
                others = json.loads(same)
            except (ValueError, TypeError):
                continue
            for other in others:
                if isinstance(other, int):
                    out.add((min(lb, other), max(lb, other)))
    finally:
        conn.close()
    return out
