"""Taper attribution engine — Layer 2: vocabulary fingerprints (TODO-214).

See ``instructions/complete/FABLE_TAPER_ATTRIBUTION.md`` §4.3/§4.4 for the design.
Layer 2 is lower precision than Layer 1 propagation (``backend.taper_attribution``)
and is gated behind it: for every taper with enough already-attributed source
entries (confirmed + propagated), this module builds a weighted log-odds
vocabulary profile from those entries' descriptions (Monroe, Wang & Cook 2008,
"Fightin' Words", with an informative Dirichlet prior), then scores every
still-unattributed entry against every profile. Layer 2 output must never feed
back into Layer 1 propagation — :func:`infer` only ever *adds* new attrs
entries, never mutates an existing one.

An ``inferred`` row is written only when THREE gates all pass (calibrated
2026-07-15 against the live DB via 5-fold holdout; raw argmax assignment is
only ~53% precise, these gates bring the written subset to ~96%, clearing the
spec's >=90% bar):

1. score gate — the winning profile's summed matched-token weight clears
   INFERRED_SCORE_THRESHOLD;
2. margin gate — the winner beats the runner-up profile by at least
   INFERRED_MARGIN_THRESHOLD (most misassignments are near-ties between
   vocabulary-similar tapers, e.g. the anonymous lt*/NET-taper series);
3. reliability gate — the winning taper is itself *reliably identifiable*:
   in a deterministic 5-fold cross-validation over the confirmed-tier source
   docs (:func:`_reliable_tapers`), predictions for that taper at the two
   gates above must reach RELIABLE_MIN_PRECISION with at least
   RELIABLE_MIN_ASSIGNED assignments. Recomputed on every run, so the
   reliable set grows as curation (TODO-213) confirms more entries.

Profiles exclude EVERY known taper alias token (not just the profiled taper's
own): matching on handles is Layer 0's job, and "transferred from <handle>'s
master" boilerplate would otherwise leak one taper's name into another
taper's vocabulary profile.

Entry points: :func:`infer` (production scoring) and :func:`calibrate`
(holdout evaluation used to pick the gate values — see
``tools/attribute_tapers.py --calibrate-fingerprints``).

This module imports :mod:`backend.taper_attribution` as a *module object*
(not specific names) so it can be imported from that module's own top level
without a circular-import failure: by the time any function here actually
dereferences ``_ta.<name>``, ``backend.taper_attribution`` has finished
executing (that only happens at call time, never at import time).
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
from collections import Counter, defaultdict

from backend import taper_attribution as _ta
from backend.db import _KNOWN_TAPER_ALIASES

log = logging.getLogger(__name__)

# ── Tunables (spec §4.3; gates calibrated 2026-07-15, see module docstring) ──

# Production kill-switch (2026-07-15 calibration verdict): the pipeline clears
# the spec's >=90% precision bar on the confirmed-tier holdout (96.2% at the
# shipped gates), but spot-checks on the actual unattributed pool found
# systematic misattributions the holdout cannot see — profiles latch onto
# era/setlist vocabulary, description formatting style, and format-spec
# boilerplate, all self-consistent within the confirmed set (docs explicitly
# crediting OTHER tapers were assigned to profile owners). Era-matched
# backgrounds and gear-token-only vocabularies were prototyped and reduce but
# do not eliminate the leakage. recompute() therefore skips Layer 2 until this
# flag is flipped after sign-off; infer()/calibrate() stay fully functional
# for tests and recalibration. Full findings: CHANGELOG 2026-07-15 /
# WORK_PACKAGE_2026-07-14.md Session 6.
LAYER2_ENABLED = False

# A taper needs at least this many source docs (confirmed+propagated,
# unpoisoned) before a profile is built for them at all.
MIN_PROFILE_ENTRIES = 8

# Stopword mechanism: any token appearing in more than this fraction of ALL
# background-corpus descriptions is dropped from every profile's vocabulary —
# no hand-maintained stopword list.
MAX_GLOBAL_DF = 0.10

# Total Dirichlet prior mass distributed across the background vocabulary,
# proportional to each token's global corpus frequency (Monroe et al. 2008).
PRIOR_MASS = 500.0

# Profile size cap: top-K tokens by z-score.
PROFILE_TOP_K = 40

# Minimum z-score (~95% one-sided normal CI) for a token to enter a profile.
Z_THRESHOLD = 1.96

# A candidate assignment needs at least this many *distinct* profile tokens
# present in the doc, regardless of score.
MIN_MATCHED_TOKENS = 3

# Gate 1: minimum winning score (sum of distinct matched profile-token
# weights). Calibrated 2026-07-15 — median correct-assignment score on the
# confirmed holdout was ~216 vs ~130 for wrong ones.
INFERRED_SCORE_THRESHOLD = 150.0

# Gate 2: minimum lead of the winning profile's score over the runner-up's
# (a doc matching only one profile counts its full score as the margin).
INFERRED_MARGIN_THRESHOLD = 80.0

# Gate 3 (reliability, :func:`_reliable_tapers`): deterministic K-fold
# cross-validation partition (lb % RELIABILITY_FOLDS), and the per-taper
# bar its predictions must clear at gates 1+2 for the taper to be eligible
# for inferred rows at all.
RELIABILITY_FOLDS = 5
RELIABLE_MIN_ASSIGNED = 10
RELIABLE_MIN_PRECISION = 0.90

# Tokens: lowercase alnum runs, allowing internal '&+- so "b&o", "co-op",
# "schoeps-cmc" tokenize as one unit; pure-digit and single/short tokens
# dropped (they carry no taper-vocabulary signal).
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['&+-][a-z0-9]+)*")


def _tokenize(text: str) -> list[str]:
    """Lowercase-tokenize *text*, dropping pure-digit and sub-2-char tokens.

    Args:
        text: Raw description text.

    Returns:
        List of tokens in order of appearance (not deduplicated).
    """
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [t for t in tokens if len(t) >= 2 and not t.isdigit()]


def _all_alias_tokens() -> frozenset[str]:
    """Tokens of every known taper alias key and canonical name.

    Excluded from EVERY profile's candidate vocabulary (see module
    docstring — handle matching belongs to Layer 0, and cross-taper handle
    mentions in lineage boilerplate would contaminate profiles).

    Returns:
        Frozen set of alias tokens, built from backend.db._KNOWN_TAPER_ALIASES.
    """
    tokens: set[str] = set()
    for key, canonical in _KNOWN_TAPER_ALIASES.items():
        tokens.update(_tokenize(key))
        tokens.update(_tokenize(canonical))
    return frozenset(tokens)


_ALL_ALIAS_TOKENS = _all_alias_tokens()


# ── Background corpus stats ─────────────────────────────────────────────────

def _load_descriptions(conn: sqlite3.Connection) -> dict[int, str]:
    """Return {lb_number: description} for every non-trivial description.

    Args:
        conn: Database connection.

    Returns:
        Dict of lb_number -> description, restricted to entries with a
        description longer than 50 characters (spec §4.3's background
        corpus — the same floor the Layer-2 source/scoring sets both use).
    """
    rows = conn.execute(
        "SELECT lb_number, description FROM entries "
        "WHERE description IS NOT NULL AND length(description) > 50"
    ).fetchall()
    return {row["lb_number"]: row["description"] for row in rows}


def _global_stats(token_cache: dict[int, list[str]]) -> tuple[Counter, Counter, int, int]:
    """Compute background-corpus term counts and document frequencies.

    Args:
        token_cache: {lb_number: tokens} for every background-corpus doc.

    Returns:
        ``(token_counts, doc_freq, total_docs, total_tokens)``:
        token_counts is total occurrences per token across the whole corpus
        (with repeats — used for the Dirichlet prior and "rest of corpus"
        counts); doc_freq is the number of distinct docs containing each
        token (used for the global document-frequency stopword filter);
        total_docs is len(token_cache); total_tokens is
        sum(token_counts.values()).
    """
    token_counts: Counter = Counter()
    doc_freq: Counter = Counter()
    for tokens in token_cache.values():
        token_counts.update(tokens)
        doc_freq.update(set(tokens))
    return token_counts, doc_freq, len(token_cache), sum(token_counts.values())


def _excluded_by_df(doc_freq: Counter, total_docs: int) -> set[str]:
    """Tokens appearing in more than MAX_GLOBAL_DF of all background docs.

    This is the stopword mechanism (spec §4.3) — no hand-maintained list.

    Args:
        doc_freq: Per-token distinct-document counts (see :func:`_global_stats`).
        total_docs: Total background-corpus document count.

    Returns:
        Set of tokens to exclude from every profile's candidate vocabulary.
    """
    if total_docs == 0:
        return set()
    limit = MAX_GLOBAL_DF * total_docs
    return {tok for tok, df in doc_freq.items() if df > limit}


# ── Profile building (Monroe et al. 2008 weighted log-odds) ────────────────

def _build_profile(
    docs: list[list[str]],
    global_counts: Counter,
    total_background_tokens: int,
    excluded_tokens: set[str],
) -> dict[str, float]:
    """Build one taper's vocabulary-fingerprint profile.

    Weighted log-odds-ratio with an informative Dirichlet prior (Monroe,
    Colaresi & Quinn 2008, "Fightin' Words"): for each candidate token w,
    corpus i is the taper's source docs and corpus j is the rest of the
    background corpus. The prior alpha_w is proportional to w's global
    background frequency, scaled so the total prior mass is PRIOR_MASS.

    Args:
        docs: This taper's source docs, already tokenized.
        global_counts: Background-corpus token counts (see :func:`_global_stats`).
        total_background_tokens: sum(global_counts.values()).
        excluded_tokens: Tokens barred from every profile — the global
            document-frequency stopword set plus _ALL_ALIAS_TOKENS (callers
            pass the union).

    Returns:
        {token: weight} for the top PROFILE_TOP_K tokens with z >= Z_THRESHOLD,
        weight = z-score. Empty dict if no token qualifies.
    """
    if total_background_tokens == 0:
        return {}

    corpus_i: Counter = Counter()
    for doc in docs:
        corpus_i.update(doc)
    n_i = sum(corpus_i.values())
    n_j = total_background_tokens - n_i

    scored: list[tuple[str, float]] = []
    for token, y_i in corpus_i.items():
        if token in excluded_tokens:
            continue
        g_count = global_counts.get(token, 0)
        if g_count <= 0:
            continue
        y_j = max(g_count - y_i, 0)
        alpha_w = PRIOR_MASS * (g_count / total_background_tokens)
        num_i = y_i + alpha_w
        den_i = (n_i + PRIOR_MASS) - num_i
        num_j = y_j + alpha_w
        den_j = (n_j + PRIOR_MASS) - num_j
        if num_i <= 0 or num_j <= 0 or den_i <= 0 or den_j <= 0:
            continue
        delta = math.log(num_i / den_i) - math.log(num_j / den_j)
        variance = 1.0 / num_i + 1.0 / num_j
        if variance <= 0:
            continue
        z = delta / math.sqrt(variance)
        if z >= Z_THRESHOLD:
            scored.append((token, z))

    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return dict(scored[:PROFILE_TOP_K])


def _poisoned_lbs(
    attrs: dict[int, dict],
    fam_members: dict[str, list[int]],
    same_as_adj: dict[int, list[int]],
    derived_from_adj: dict[int, list[int]],
    unresolved: set[int],
) -> set[int]:
    """Return every lb whose same-source component may not contribute source docs.

    Builds a union-find over the same edge set _propagate_strong uses (family
    cliques + same_as + derived_from) — but, unlike _propagate_strong, without
    a review-flag distinction, since this function isn't given fam_review: a
    weak-family-only component is still poisoned the same way, which is the
    conservative direction (it only ever *shrinks* the source-doc pool, never
    admits a bad one). Any connected component containing an lb with
    conflict=1 or an lb in *unresolved* is entirely excluded from
    profile-building (TODO-234: known family over-merges / undecidable
    two-taper recordings must not contaminate a taper's vocabulary profile).

    Args:
        attrs: In-memory attribution rows (Layer 0/1 output).
        fam_members: fam_id -> member lb_numbers.
        same_as_adj: Bidirectional same_as adjacency.
        derived_from_adj: Bidirectional derived_from adjacency.
        unresolved: LBs a curator marked undecidable.

    Returns:
        Set of every lb belonging to a poisoned component.
    """
    dsu = _ta._DSU()
    for fam_id in sorted(fam_members):
        members = fam_members[fam_id]
        if len(members) < 2:
            continue
        first = members[0]
        for m in members[1:]:
            dsu.union(first, m)
    for lb in sorted(same_as_adj):
        for other in same_as_adj[lb]:
            dsu.union(lb, other)
    for lb in sorted(derived_from_adj):
        for other in derived_from_adj[lb]:
            dsu.union(lb, other)

    groups: dict[int, set[int]] = defaultdict(set)
    for lb in dsu.parent:
        groups[dsu.find(lb)].add(lb)

    poisoned: set[int] = set()
    for members in groups.values():
        if any(attrs.get(lb, {}).get("conflict") == 1 for lb in members) or any(
            lb in unresolved for lb in members
        ):
            poisoned.update(members)
    # Edge-less unresolved lbs never enter the DSU, so the component loop
    # above can't see them — but they must not contribute source docs either.
    poisoned.update(unresolved)
    return poisoned


def _source_docs_by_taper(
    attrs: dict[int, dict],
    token_cache: dict[int, list[str]],
    poisoned: set[int],
) -> dict[str, list[tuple[int, list[str]]]]:
    """Group eligible source docs (lb, tokens) by taper, deterministically ordered.

    Eligible: attrs tier in ('confirmed', 'propagated'), conflict == 0, not in
    a poisoned component, and has a background-corpus description.

    Args:
        attrs: In-memory attribution rows.
        token_cache: {lb_number: tokens} for the background corpus.
        poisoned: LBs excluded per :func:`_poisoned_lbs`.

    Returns:
        {taper: [(lb, tokens), ...]}, each list ordered by lb ascending.
    """
    by_taper: dict[str, list[tuple[int, list[str]]]] = defaultdict(list)
    for lb in sorted(attrs):
        row = attrs[lb]
        if row["tier"] not in ("confirmed", "propagated"):
            continue
        if row["conflict"] or lb in poisoned:
            continue
        tokens = token_cache.get(lb)
        if not tokens:
            continue
        by_taper[row["taper"]].append((lb, tokens))
    return dict(by_taper)


def _best_candidate(
    tokens: list[str], profiles: dict[str, dict[str, float]]
) -> tuple[str, float, float, list[str]] | None:
    """Score *tokens* against every profile; return the deterministic winner.

    score = sum of weights of DISTINCT profile tokens present in the doc.
    A taper only qualifies as a candidate if it has >= MIN_MATCHED_TOKENS
    distinct matches. Ties broken by taper name ascending (spec §7
    idempotency — re-runs must be byte-identical).

    Args:
        tokens: Tokenized document.
        profiles: {taper: {token: weight}}.

    Returns:
        ``(winning_taper, score, margin, matched_tokens)`` where margin is the
        winner's lead over the runner-up candidate's score (== score when no
        runner-up qualifies) and matched_tokens is the winner's matched tokens
        sorted by weight descending then token ascending, capped at 10 (the
        evidence-detail cap) — or None if no taper reaches MIN_MATCHED_TOKENS.
    """
    doc_set = set(tokens)
    candidates: dict[str, tuple[float, list[str]]] = {}
    for taper in sorted(profiles):
        profile = profiles[taper]
        matched = [t for t in doc_set if t in profile]
        if len(matched) < MIN_MATCHED_TOKENS:
            continue
        score = sum(profile[t] for t in matched)
        candidates[taper] = (score, matched)

    if not candidates:
        return None

    ranked = sorted(candidates, key=lambda t: (-candidates[t][0], t))
    winner = ranked[0]
    score, matched = candidates[winner]
    margin = score - candidates[ranked[1]][0] if len(ranked) > 1 else score
    matched_sorted = sorted(matched, key=lambda t: (-profiles[winner][t], t))[:10]
    return winner, score, margin, matched_sorted


def _build_all_profiles(
    source_docs: dict[str, list[tuple[int, list[str]]]],
    global_counts: Counter,
    total_background_tokens: int,
    excluded_tokens: set[str],
) -> dict[str, dict[str, float]]:
    """Build profiles for every taper with >= MIN_PROFILE_ENTRIES source docs.

    Args:
        source_docs: {taper: [(lb, tokens), ...]} (see :func:`_source_docs_by_taper`).
        global_counts: Background-corpus token counts.
        total_background_tokens: sum(global_counts.values()).
        excluded_tokens: Union of the document-frequency stopword set and
            _ALL_ALIAS_TOKENS.

    Returns:
        {taper: profile} for every taper whose profile came out non-empty,
        iterated/built in sorted-taper order for determinism.
    """
    profiles: dict[str, dict[str, float]] = {}
    for taper in sorted(source_docs):
        entries = source_docs[taper]
        if len(entries) < MIN_PROFILE_ENTRIES:
            continue
        docs = [tokens for _lb, tokens in entries]
        profile = _build_profile(docs, global_counts, total_background_tokens,
                                 excluded_tokens)
        if profile:
            profiles[taper] = profile
    return profiles


# ── Reliability cross-validation (gate 3) ───────────────────────────────────

def _crossval_predictions(
    source_docs: dict[str, list[tuple[int, list[str]]]],
    global_counts: Counter,
    total_background_tokens: int,
    excluded_tokens: set[str],
    attrs: dict[int, dict],
) -> list[tuple[bool, float, float, str, str]]:
    """K-fold holdout predictions over the confirmed-tier source docs.

    Deterministic partition: fold k holds out every confirmed-tier source lb
    with ``lb % RELIABILITY_FOLDS == k``; profiles are rebuilt WITHOUT that
    fold's docs (propagated-tier docs always stay in the profile pool — they
    have no independent ground truth worth scoring), and each held-out doc is
    scored as if unattributed.

    Args:
        source_docs: {taper: [(lb, tokens), ...]} (see :func:`_source_docs_by_taper`).
        global_counts: Background-corpus token counts.
        total_background_tokens: sum(global_counts.values()).
        excluded_tokens: Union of the DF stopword set and _ALL_ALIAS_TOKENS.
        attrs: In-memory attribution rows (read-only; used for tier lookup).

    Returns:
        One ``(correct, score, margin, true_taper, predicted_taper)`` tuple
        per held-out doc that produced a candidate, ordered by fold then lb.
    """
    predictions: list[tuple[bool, float, float, str, str]] = []
    for fold in range(RELIABILITY_FOLDS):
        holdout: list[tuple[int, str, list[str]]] = []
        profile_docs: dict[str, list[tuple[int, list[str]]]] = {}
        for taper in sorted(source_docs):
            kept: list[tuple[int, list[str]]] = []
            for lb, tokens in source_docs[taper]:
                if attrs[lb]["tier"] == "confirmed" and lb % RELIABILITY_FOLDS == fold:
                    holdout.append((lb, taper, tokens))
                else:
                    kept.append((lb, tokens))
            profile_docs[taper] = kept
        holdout.sort(key=lambda h: h[0])

        profiles = _build_all_profiles(profile_docs, global_counts,
                                       total_background_tokens, excluded_tokens)
        for _lb, true_taper, tokens in holdout:
            cand = _best_candidate(tokens, profiles)
            if cand is None:
                continue
            pred, score, margin, _matched = cand
            predictions.append((pred == true_taper, score, margin, true_taper, pred))
    return predictions


def _reliable_tapers(
    predictions: list[tuple[bool, float, float, str, str]],
    score_threshold: float,
    margin_threshold: float,
) -> dict[str, tuple[int, int]]:
    """Tapers whose gated cross-val predictions clear the reliability bar.

    Args:
        predictions: Output of :func:`_crossval_predictions`.
        score_threshold: Gate-1 value the assignments must clear.
        margin_threshold: Gate-2 value the assignments must clear.

    Returns:
        {taper: (assigned, correct)} for every taper with at least
        RELIABLE_MIN_ASSIGNED gated assignments at RELIABLE_MIN_PRECISION or
        better. Only these tapers may receive inferred rows.
    """
    per_taper: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for correct, score, margin, _true, pred in predictions:
        if score >= score_threshold and margin >= margin_threshold:
            per_taper[pred][0] += 1
            per_taper[pred][1] += int(correct)
    return {
        taper: (assigned, hits)
        for taper, (assigned, hits) in sorted(per_taper.items())
        if assigned >= RELIABLE_MIN_ASSIGNED
        and hits / assigned >= RELIABLE_MIN_PRECISION
    }


# ── Public entry points ─────────────────────────────────────────────────────

def infer(
    attrs: dict[int, dict],
    conn: sqlite3.Connection,
    fam_members: dict[str, list[int]],
    same_as_adj: dict[int, list[int]],
    derived_from_adj: dict[int, list[int]],
    unresolved: set[int],
    threshold: float | None = None,
    margin_threshold: float | None = None,
    reliable_tapers: set[str] | None = None,
) -> dict:
    """Layer 2 — score unattributed entries against vocabulary fingerprints.

    Mutates *attrs* in place: writes an ``inferred`` row for every
    still-unattributed entry that passes all three gates (score, margin,
    winner-reliability — see module docstring). Never overwrites an existing
    attrs entry (Layer 2 output must never feed back into Layer 1 — spec §4.3).

    Args:
        attrs: In-memory attribution rows (Layer 0/1 output), mutated in place.
        conn: Database connection (used to load descriptions).
        fam_members: fam_id -> member lb_numbers.
        same_as_adj: Bidirectional same_as adjacency.
        derived_from_adj: Bidirectional derived_from adjacency.
        unresolved: LBs a curator marked undecidable (poisons their component's
            source docs; the caller applies the actual attrs suppression later).
        threshold: Gate-1 minimum winning score. Defaults to
            INFERRED_SCORE_THRESHOLD.
        margin_threshold: Gate-2 minimum winner-vs-runner-up lead. Defaults to
            INFERRED_MARGIN_THRESHOLD.
        reliable_tapers: Gate-3 override — the set of tapers eligible for
            inferred rows. Defaults to None, which computes the set via
            :func:`_reliable_tapers` cross-validation (production behavior);
            tests pass an explicit set to bypass the data-hungry gate.

    Returns:
        {"profiles": n_profiles_built, "scored": n_candidates_considered,
         "reliable_tapers": n_eligible_tapers, "inferred": n_rows_written}.
    """
    thresh = INFERRED_SCORE_THRESHOLD if threshold is None else threshold
    margin_thresh = (INFERRED_MARGIN_THRESHOLD if margin_threshold is None
                     else margin_threshold)

    descriptions = _load_descriptions(conn)
    if not descriptions:
        return {"profiles": 0, "scored": 0, "reliable_tapers": 0, "inferred": 0}
    token_cache = {lb: _tokenize(desc) for lb, desc in descriptions.items()}

    global_counts, doc_freq, total_docs, total_bg_tokens = _global_stats(token_cache)
    excluded = _excluded_by_df(doc_freq, total_docs) | _ALL_ALIAS_TOKENS
    poisoned = _poisoned_lbs(attrs, fam_members, same_as_adj, derived_from_adj, unresolved)
    source_docs = _source_docs_by_taper(attrs, token_cache, poisoned)
    profiles = _build_all_profiles(source_docs, global_counts, total_bg_tokens, excluded)

    if reliable_tapers is None:
        predictions = _crossval_predictions(source_docs, global_counts, total_bg_tokens,
                                            excluded, attrs)
        reliable_tapers = set(_reliable_tapers(predictions, thresh, margin_thresh))
        log.info("taper_fingerprints.infer: reliable tapers = %s", sorted(reliable_tapers))

    scored = 0
    inferred = 0
    for lb in sorted(descriptions):
        if lb in attrs:
            continue
        scored += 1
        cand = _best_candidate(token_cache[lb], profiles)
        if cand is None:
            continue
        taper, score, margin, matched = cand
        if taper not in reliable_tapers or score < thresh or margin < margin_thresh:
            continue
        detail = "matched tokens: " + ", ".join(matched)
        attrs[lb] = {
            "taper": taper,
            "tier": "inferred",
            "conflict": 0,
            "evidence": [_ta._evidence("fingerprint", detail, score=round(score, 2),
                                       margin=round(margin, 2))],
            "confirmed_at": None,
        }
        inferred += 1

    log.info(
        "taper_fingerprints.infer: profiles=%d scored=%d reliable=%d inferred=%d "
        "(score>=%s, margin>=%s)",
        len(profiles), scored, len(reliable_tapers), inferred, thresh, margin_thresh,
    )
    return {"profiles": len(profiles), "scored": scored,
            "reliable_tapers": len(reliable_tapers), "inferred": inferred}


def calibrate(
    conn: sqlite3.Connection,
    attrs: dict[int, dict],
    fam_members: dict[str, list[int]],
    same_as_adj: dict[int, list[int]],
    derived_from_adj: dict[int, list[int]],
    unresolved: set[int],
    gates: tuple[tuple[float, float], ...] = (
        (0, 0), (100, 50), (150, 80), (200, 100), (250, 120),
    ),
) -> dict:
    """Evaluate candidate (score, margin) gates against the K-fold holdout.

    Runs the same deterministic cross-validation :func:`infer` uses for its
    reliability gate, then reports, for each candidate gate pair, precision
    and coverage BOTH raw and restricted to the reliable-taper set that pair
    induces — the restricted row is what production writes.

    Args:
        conn: Database connection.
        attrs: In-memory attribution rows (Layer 0/1 output; not mutated).
        fam_members: fam_id -> member lb_numbers.
        same_as_adj: Bidirectional same_as adjacency.
        derived_from_adj: Bidirectional derived_from adjacency.
        unresolved: LBs a curator marked undecidable.
        gates: Candidate (score_threshold, margin_threshold) pairs.

    Returns:
        {"holdout": n_docs_evaluated,
         "rows": [{"score_gate", "margin_gate", "assigned", "precision",
                   "coverage", "reliable_assigned", "reliable_precision",
                   "reliable_coverage", "reliable_tapers"}, ...],
         "reliable_tapers": {taper: (assigned, correct)} at the production
         gates (INFERRED_SCORE_THRESHOLD / INFERRED_MARGIN_THRESHOLD)}.
    """
    descriptions = _load_descriptions(conn)
    token_cache = {lb: _tokenize(desc) for lb, desc in descriptions.items()}
    global_counts, doc_freq, total_docs, total_bg_tokens = _global_stats(token_cache)
    excluded = _excluded_by_df(doc_freq, total_docs) | _ALL_ALIAS_TOKENS
    poisoned = _poisoned_lbs(attrs, fam_members, same_as_adj, derived_from_adj, unresolved)
    source_docs = _source_docs_by_taper(attrs, token_cache, poisoned)

    predictions = _crossval_predictions(source_docs, global_counts, total_bg_tokens,
                                        excluded, attrs)
    holdout_count = sum(
        1 for taper in source_docs for lb, _tokens in source_docs[taper]
        if attrs[lb]["tier"] == "confirmed"
    )

    rows: list[dict] = []
    for score_gate, margin_gate in gates:
        gated = [p for p in predictions if p[1] >= score_gate and p[2] >= margin_gate]
        assigned = len(gated)
        correct = sum(1 for p in gated if p[0])
        reliable = _reliable_tapers(predictions, score_gate, margin_gate)
        rel = [p for p in gated if p[4] in reliable]
        rel_assigned = len(rel)
        rel_correct = sum(1 for p in rel if p[0])
        rows.append({
            "score_gate": score_gate,
            "margin_gate": margin_gate,
            "assigned": assigned,
            "precision": round(correct / assigned, 4) if assigned else 0.0,
            "coverage": round(assigned / holdout_count, 4) if holdout_count else 0.0,
            "reliable_assigned": rel_assigned,
            "reliable_precision": (round(rel_correct / rel_assigned, 4)
                                   if rel_assigned else 0.0),
            "reliable_coverage": (round(rel_assigned / holdout_count, 4)
                                  if holdout_count else 0.0),
            "reliable_tapers": len(reliable),
        })
        log.info(
            "taper_fingerprints.calibrate: gate=(%s,%s) raw %d/%d=%.3f | "
            "reliable-only %d/%d=%.3f (%d tapers, holdout=%d)",
            score_gate, margin_gate, correct, assigned,
            correct / assigned if assigned else 0.0,
            rel_correct, rel_assigned,
            rel_correct / rel_assigned if rel_assigned else 0.0,
            len(reliable), holdout_count,
        )

    return {
        "holdout": holdout_count,
        "rows": rows,
        "reliable_tapers": _reliable_tapers(
            predictions, INFERRED_SCORE_THRESHOLD, INFERRED_MARGIN_THRESHOLD),
    }
