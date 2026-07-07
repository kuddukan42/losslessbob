"""Prove verdict.pair_links reproduces match.cluster's built-in threshold logic
exactly, across randomized signal matrices — so the cli.py refactor to route
clustering through verdict.py (Task 1.3) is behaviour-preserving without needing
an audio re-run to confirm it.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import match, verdict  # noqa: E402

# Thresholds mirror the committed config.yaml.
CFG = {
    "match": {"cluster_threshold": 0.45},
    "secondary_match": {
        "coverage_threshold": 0.35,
        "hiss_merge_frac": 0.60,
        "hiss_merge_median": 0.65,
    },
    "fingerprint": {"cluster_threshold": 0.50},
}
M_THR = CFG["match"]["cluster_threshold"]
WC = CFG["secondary_match"]["coverage_threshold"]
HMF = CFG["secondary_match"]["hiss_merge_frac"]
HMM = CFG["secondary_match"]["hiss_merge_median"]
FPC = CFG["fingerprint"]["cluster_threshold"]


def _groups_as_sets(groups):
    return {frozenset(g) for g in groups}


def _random_matrices(n, rng):
    def sym(lo=0.0, hi=1.0):
        A = rng.uniform(lo, hi, (n, n))
        A = (A + A.T) / 2
        np.fill_diagonal(A, 1.0)
        return A
    return sym(), sym(), sym(), sym(), sym()


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("sec_results,fp_active",
                         [(True, True), (True, False), (False, True), (False, False)])
def test_link_fn_matches_builtin(seed, sec_results, fp_active):
    rng = np.random.default_rng(seed)
    n = rng.integers(2, 8)
    names = [f"src{i}" for i in range(n)]
    M, W, H, H_med, FP = _random_matrices(n, rng)
    # Randomly flag some sources as staircase (must NOT change behaviour with the
    # committed config, which has no staircase override key).
    staircase = {names[i] for i in range(n) if rng.random() < 0.3}

    fp_cluster_thr = FPC if fp_active else 0.0

    old = match.cluster(
        names, M, M_THR,
        W=W if sec_results else None, w_threshold=WC,
        H=H if sec_results else None, h_threshold=HMF,
        H_med=H_med if sec_results else None, h_med_threshold=HMM,
        F=FP if fp_cluster_thr > 0.0 else None, f_threshold=fp_cluster_thr)

    def metrics(i, j):
        return {
            "corr": float(M[i, j]),
            "windowed_frac": float(W[i, j]) if sec_results else None,
            "hiss_frac": float(H[i, j]) if sec_results else None,
            "hiss_median": float(H_med[i, j]) if sec_results else None,
            "fp_score": float(FP[i, j]) if fp_cluster_thr > 0.0 else None,
            "speed_kind_a": "staircase/splice" if names[i] in staircase else None,
            "speed_kind_b": "staircase/splice" if names[j] in staircase else None,
            "lb_a": None, "lb_b": None,
        }

    new = match.cluster(
        names, M, M_THR,
        link_fn=lambda i, j: verdict.pair_links(metrics(i, j), CFG, lineage=None))

    assert _groups_as_sets(old) == _groups_as_sets(new)


def test_fp_threshold_staircase_lowers_bar():
    cfg = {"fingerprint": {"cluster_threshold": 0.50,
                           "cluster_threshold_staircase": 0.40}}
    plain = {"speed_kind_a": "constant-speed-offset", "speed_kind_b": "reference"}
    stair = {"speed_kind_a": "staircase/splice", "speed_kind_b": "reference"}
    assert verdict.fp_threshold(plain, cfg) == 0.50
    assert verdict.fp_threshold(stair, cfg) == 0.40
    # A staircase pair with fp_score between the two thresholds now links.
    p = {"corr": 0.0, "fp_score": 0.45, **stair, "lb_a": 1, "lb_b": 2}
    assert verdict.pair_links(p, cfg)
    p_plain = {"corr": 0.0, "fp_score": 0.45, **plain, "lb_a": 1, "lb_b": 2}
    assert not verdict.pair_links(p_plain, cfg)


def test_fp_threshold_curator_is_prior_not_label():
    cfg = {"fingerprint": {"cluster_threshold": 0.50,
                           "cluster_threshold_curator": 0.43}}
    lineage = {(10, 20)}
    pair = {"lb_a": 20, "lb_b": 10, "speed_kind_a": None, "speed_kind_b": None}
    assert verdict.fp_threshold(pair, cfg, lineage) == 0.43
    # Text claim + weak audio (0.10) still stays different — text is a prior.
    weak = {"corr": 0.0, "fp_score": 0.10, "lb_a": 20, "lb_b": 10}
    assert not verdict.pair_links(weak, cfg, lineage)
    # Text claim + audio over the relaxed bar links.
    ok = {"corr": 0.0, "fp_score": 0.45, "lb_a": 20, "lb_b": 10}
    assert verdict.pair_links(ok, cfg, lineage)


def test_lofi_hiss_median_relaxation():
    cfg = {"match": {"cluster_threshold": 0.45},
           "secondary_match": {"coverage_threshold": 0.35,
                               "hiss_merge_frac": 0.60,
                               "hiss_merge_median": 0.65,
                               "hiss_merge_median_lofi": 0.40,
                               "hiss_lofi_ceiling_hz": 12000},
           "fingerprint": {"cluster_threshold": 0.50}}
    # hiss_frac clears 0.60; hiss_median 0.50 is below the 0.65 std bar but above
    # the 0.40 lo-fi bar. corr/windowed/fp all absent so hiss is the only path.
    base = {"corr": 0.0, "windowed_frac": 0.0, "fp_score": 0.0,
            "hiss_frac": 0.70, "hiss_median": 0.50, "lb_a": 1, "lb_b": 2}
    lofi = {**base, "hf_ceiling_hz_a": 5000, "hf_ceiling_hz_b": 6000}
    assert verdict.pair_links(lofi, cfg)                       # both lo-fi -> relaxed bar
    hifi = {**base, "hf_ceiling_hz_a": 5000, "hf_ceiling_hz_b": 15000}
    assert not verdict.pair_links(hifi, cfg)                   # one side hi-fi -> std bar
    capped = {**lofi, "nyquist_capped_a": 1}
    assert not verdict.pair_links(capped, cfg)                 # capped ceiling is unknown
    # Without the lofi config keys, the std 0.65 bar applies and the pair fails.
    cfg_std = {**cfg, "secondary_match": {k: v for k, v in cfg["secondary_match"].items()
                                          if k not in ("hiss_merge_median_lofi",
                                                       "hiss_lofi_ceiling_hz")}}
    assert not verdict.pair_links(lofi, cfg_std)


def test_flaw_fingerprint_inert_when_disabled():
    """CC_TAPEMATCH_ADDON.md Task 2: enabled: false (the config default, and
    every historical row's implicit state before the column existed) must
    leave pair_links byte-identical to pre-Task-2 behaviour, even when a
    flaw_match_score happens to be present and well above the merge bar."""
    cfg_no_ff = CFG   # committed config: no flaw_fingerprint key at all
    cfg_ff_off = {**CFG, "flaw_fingerprint": {
        "enabled": False, "merge_threshold": 0.6, "min_events_merge": 8}}
    pair = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
            "flaw_match_score": 0.95, "flaw_n_events_a": 20, "flaw_n_events_b": 20}
    assert not verdict.pair_links(pair, cfg_no_ff)
    assert not verdict.pair_links(pair, cfg_ff_off)


def test_flaw_fingerprint_enabled_alone_no_longer_merges():
    """CC_TAPEMATCH_ADDON.md Task 5.1 reconciliation: the standalone flaw
    OR-path that used to live directly in pair_links, gated solely on
    ``flaw_fingerprint.enabled``, was folded into ``addon_links.rule_a`` and
    removed. ``flaw_fingerprint.enabled: true`` now ONLY gates metric
    computation (cli.py) — it must NOT merge on its own without
    ``addon_links.rule_a.enabled`` also set. Proves there is exactly one
    canonical flaw merge path, not two."""
    cfg_ff_on_no_addon = {**CFG, "flaw_fingerprint": {
        "enabled": True, "merge_threshold": 0.6, "min_events_merge": 8}}
    good = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
            "flaw_match_score": 0.95, "flaw_n_events_a": 20, "flaw_n_events_b": 20}
    assert not verdict.pair_links(good, cfg_ff_on_no_addon)


def test_addon_links_rule_a_null_column_is_inert_on_historical_rows():
    """A historical row (column added via ALTER, never populated) carries
    flaw_match_score/flaw_n_events_a/b == None. Even with Rule A enabled, a
    None signal must never fire the link (same NULL-safety as every other
    OR-path leg)."""
    cfg_rule_a_on = {**CFG, "addon_links": {
        "rule_a": {"enabled": True, "t_flaw": 0.6, "min_events": 8}}}
    historical_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                      "flaw_match_score": None, "flaw_n_events_a": None,
                      "flaw_n_events_b": None}
    assert not verdict.pair_links(historical_row, cfg_rule_a_on)


def test_addon_links_rule_a_fires_when_enabled_and_gated():
    """Rule A (CC_TAPEMATCH_ADDON.md Task 5.1) is the sole canonical flaw
    merge path, replacing the Task 2.3 standalone OR-leg."""
    cfg_rule_a_on = {**CFG, "addon_links": {
        "rule_a": {"enabled": True, "t_flaw": 0.6, "min_events": 8}}}
    # Above threshold, both sides meet the event-count floor -> links.
    good = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
            "flaw_match_score": 0.7, "flaw_n_events_a": 10, "flaw_n_events_b": 9}
    assert verdict.pair_links(good, cfg_rule_a_on)
    # Above threshold but one side under the event-count floor -> abstains.
    thin = {**good, "flaw_n_events_b": 3}
    assert not verdict.pair_links(thin, cfg_rule_a_on)
    # Below threshold -> abstains regardless of event counts.
    weak = {**good, "flaw_match_score": 0.4}
    assert not verdict.pair_links(weak, cfg_rule_a_on)
    # Rule present but disabled -> abstains even with a perfect score.
    cfg_rule_a_off = {**CFG, "addon_links": {
        "rule_a": {"enabled": False, "t_flaw": 0.6, "min_events": 8}}}
    assert not verdict.pair_links(good, cfg_rule_a_off)


def test_addon_links_rule_b_two_leg_conjunctive():
    """Rule B (Task 5.1): spec_stationarity AND env_corr, both required —
    conjunctive by construction, the only route either signal has into a
    verdict."""
    cfg_rule_b_on = {**CFG, "addon_links": {
        "rule_b": {"enabled": True, "t_stat": 0.7, "t_env": 0.90}}}
    both_pass = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                "spec_stationarity": 0.9, "env_corr": 0.95}
    assert verdict.pair_links(both_pass, cfg_rule_b_on)
    # Only one leg passing -> abstains (never a lone-merge path for either signal).
    only_stat = {**both_pass, "env_corr": 0.5}
    assert not verdict.pair_links(only_stat, cfg_rule_b_on)
    only_env = {**both_pass, "spec_stationarity": 0.1}
    assert not verdict.pair_links(only_env, cfg_rule_b_on)
    # NULL on either leg -> abstains.
    null_env = {**both_pass, "env_corr": None}
    assert not verdict.pair_links(null_env, cfg_rule_b_on)
    null_stat = {**both_pass, "spec_stationarity": None}
    assert not verdict.pair_links(null_stat, cfg_rule_b_on)
    # Disabled -> abstains even with both legs maximal.
    cfg_rule_b_off = {**CFG, "addon_links": {
        "rule_b": {"enabled": False, "t_stat": 0.7, "t_env": 0.90}}}
    assert not verdict.pair_links(both_pass, cfg_rule_b_off)


def test_addon_links_rule_c_abstains_when_emb_score_absent():
    """Rule C (Task 5.1): emb_score has no persisted column yet (Task 6), so
    it is absent/None on every real pair today. Rule C must defensively
    abstain rather than crash, whether the key is entirely missing from the
    mapping or explicitly None."""
    cfg_rule_c_on = {**CFG, "addon_links": {
        "rule_c": {"enabled": True, "t_emb": 0.70, "t_flaw_weak": 0.4, "t_stat": 0.7}}}
    key_missing = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                   "flaw_match_score": 0.9, "spec_stationarity": 0.9}
    assert not verdict.pair_links(key_missing, cfg_rule_c_on)
    key_none = {**key_missing, "emb_score": None}
    assert not verdict.pair_links(key_none, cfg_rule_c_on)


def test_addon_links_rule_c_fires_when_enabled_and_gated():
    """Rule C: emb_score AND (flaw_match_score weak OR spec_stationarity)."""
    cfg_rule_c_on = {**CFG, "addon_links": {
        "rule_c": {"enabled": True, "t_emb": 0.70, "t_flaw_weak": 0.4, "t_stat": 0.7}}}
    via_flaw = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
               "emb_score": 0.9, "flaw_match_score": 0.5, "spec_stationarity": None}
    assert verdict.pair_links(via_flaw, cfg_rule_c_on)
    via_stat = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
               "emb_score": 0.9, "flaw_match_score": None, "spec_stationarity": 0.8}
    assert verdict.pair_links(via_stat, cfg_rule_c_on)
    # emb_score below t_emb -> abstains even if both weak legs would pass.
    weak_emb = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
               "emb_score": 0.5, "flaw_match_score": 0.9, "spec_stationarity": 0.9}
    assert not verdict.pair_links(weak_emb, cfg_rule_c_on)
    # emb_score passes but neither weak leg does -> abstains.
    no_legs = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
              "emb_score": 0.9, "flaw_match_score": 0.1, "spec_stationarity": 0.1}
    assert not verdict.pair_links(no_legs, cfg_rule_c_on)
    # Disabled -> abstains even with everything passing.
    cfg_rule_c_off = {**CFG, "addon_links": {
        "rule_c": {"enabled": False, "t_emb": 0.70, "t_flaw_weak": 0.4, "t_stat": 0.7}}}
    assert not verdict.pair_links(via_flaw, cfg_rule_c_off)


def test_addon_links_all_disabled_is_byte_identical_to_no_addon_links():
    """CC_TAPEMATCH_ADDON.md Task 5.1: with an addon_links block present but
    every rule enabled:false, historical verdicts must be byte-identical to
    a config with no addon_links block at all — the block's mere presence
    (with thresholds populated) must not change any outcome."""
    cfg_all_off = {**CFG, "addon_links": {
        "rule_a": {"enabled": False, "t_flaw": 0.6, "min_events": 8},
        "rule_b": {"enabled": False, "t_stat": 0.7, "t_env": 0.90},
        "rule_c": {"enabled": False, "t_emb": 0.70, "t_flaw_weak": 0.4, "t_stat": 0.7},
    }}
    rows = [
        {"corr": 0.0, "lb_a": 1, "lb_b": 2,
         "flaw_match_score": 0.95, "flaw_n_events_a": 20, "flaw_n_events_b": 20},
        {"corr": 0.0, "lb_a": 1, "lb_b": 2,
         "spec_stationarity": 0.99, "env_corr": 0.99},
        {"corr": 0.0, "lb_a": 1, "lb_b": 2,
         "emb_score": 0.99, "flaw_match_score": 0.99, "spec_stationarity": 0.99},
        {"corr": 0.45, "lb_a": 1, "lb_b": 2},  # a path that DOES link, unaffected
    ]
    for row in rows:
        assert verdict.pair_links(row, CFG) == verdict.pair_links(row, cfg_all_off)


def test_spec_stationarity_null_column_is_inert():
    """CC_TAPEMATCH_ADDON.md Task 3: spec_stationarity is registered in
    verdict.METRIC_KEYS for cached-scoring round-tripping, but has NO OR-path
    (conjunctive-only signal, combination rules deferred to Task 5). Adding
    the nullable column must leave pair_links byte-identical whether the
    value is NULL (historical row) or populated-and-high (a live run with the
    feature enabled) -- nothing may read the key yet."""
    assert "spec_stationarity" in verdict.METRIC_KEYS

    historical_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2, "spec_stationarity": None}
    assert not verdict.pair_links(historical_row, CFG)

    # Even a maximal value, with the feature "enabled" in config (no addon_links
    # section exists yet -- Task 5), must not fire a link on its own.
    cfg_with_block = {**CFG, "spectral_stationarity": {"enabled": True}}
    high_value_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2, "spec_stationarity": 1.0}
    assert not verdict.pair_links(high_value_row, CFG)
    assert not verdict.pair_links(high_value_row, cfg_with_block)

    # Presence/absence of the key must not change any other leg's outcome.
    base = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
            "flaw_match_score": 0.7, "flaw_n_events_a": 10, "flaw_n_events_b": 9}
    cfg_ff_on = {**CFG, "flaw_fingerprint": {
        "enabled": True, "merge_threshold": 0.6, "min_events_merge": 8}}
    without_stat = verdict.pair_links(base, cfg_ff_on)
    with_stat = verdict.pair_links({**base, "spec_stationarity": 0.99}, cfg_ff_on)
    assert without_stat == with_stat


def test_env_corr_null_column_is_inert():
    """CC_TAPEMATCH_ADDON.md Task 4: env_corr is registered in
    verdict.METRIC_KEYS for cached-scoring round-tripping, but has NO OR-path
    (conjunctive-only, high same-show collision risk -- banned from a
    lone-merge path even after calibration per spec 4.2; combination rules
    are deferred to Task 5). Adding the nullable column must leave
    pair_links byte-identical whether the value is NULL (historical row) or
    populated-and-maximal (a live run with the feature enabled) -- nothing
    may read the key yet."""
    assert "env_corr" in verdict.METRIC_KEYS

    historical_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2, "env_corr": None}
    assert not verdict.pair_links(historical_row, CFG)

    # Even a maximal value, with the feature "enabled" in config (no
    # addon_links section exists yet -- Task 5), must not fire a link alone.
    cfg_with_block = {**CFG, "envelope_corr": {"enabled": True}}
    high_value_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2, "env_corr": 1.0}
    assert not verdict.pair_links(high_value_row, CFG)
    assert not verdict.pair_links(high_value_row, cfg_with_block)

    # Presence/absence of the key must not change any other leg's outcome,
    # including alongside spec_stationarity (both dormant, both conjunctive-only).
    base = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
            "flaw_match_score": 0.7, "flaw_n_events_a": 10, "flaw_n_events_b": 9,
            "spec_stationarity": 0.99}
    cfg_ff_on = {**CFG, "flaw_fingerprint": {
        "enabled": True, "merge_threshold": 0.6, "min_events_merge": 8}}
    without_env = verdict.pair_links(base, cfg_ff_on)
    with_env = verdict.pair_links({**base, "env_corr": 0.99}, cfg_ff_on)
    assert without_env == with_env


def test_addon_links_rule_d_disabled_is_byte_identical_on_historical_rows():
    """Rule D (embedding both-convention, CC_TAPEMATCH_ADDON.md Task 6
    follow-on): with rule_d absent/disabled, a historical row (emb columns
    NULL, the implicit state before the columns existed) must verdict
    byte-identically to a config with no addon_links.rule_d key at all —
    same guarantee as rules A/B/C."""
    cfg_no_rule_d = CFG  # committed config: no addon_links.rule_d key
    cfg_rule_d_off = {**CFG, "addon_links": {
        "rule_d": {"enabled": False, "t_emb": 0.75}}}
    historical_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                      "emb_score": None, "emb_score_global": None}
    assert not verdict.pair_links(historical_row, cfg_no_rule_d)
    assert not verdict.pair_links(historical_row, cfg_rule_d_off)
    # Even with maximal (but well-formed) values, disabled never fires.
    maximal_row = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                   "emb_score": 1.0, "emb_score_global": 1.0}
    assert not verdict.pair_links(maximal_row, cfg_rule_d_off)


def test_addon_links_rule_d_enabled_but_emb_null_abstains():
    """Rule D enabled but the emb columns are NULL (not yet populated by
    persist_emb_scores.py on this row) must abstain — byte-identical to
    rule_d being disabled, never coerced to 0.0."""
    cfg_rule_d_on = {**CFG, "addon_links": {
        "rule_d": {"enabled": True, "t_emb": 0.75}}}
    both_null = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                "emb_score": None, "emb_score_global": None}
    assert not verdict.pair_links(both_null, cfg_rule_d_on)
    key_missing = {"corr": 0.0, "lb_a": 1, "lb_b": 2}
    assert not verdict.pair_links(key_missing, cfg_rule_d_on)
    cfg_rule_d_off = {**CFG, "addon_links": {
        "rule_d": {"enabled": False, "t_emb": 0.75}}}
    assert verdict.pair_links(both_null, cfg_rule_d_on) == \
        verdict.pair_links(both_null, cfg_rule_d_off)


def test_addon_links_rule_d_fires_only_on_both_convention_cross_source():
    """Rule D: emb_score AND emb_score_global both required, cross-source
    pairs only. One leg NULL or below t_emb abstains; a self-pair
    (lb_a == lb_b) never fires even with both legs maximal."""
    cfg_rule_d_on = {**CFG, "addon_links": {
        "rule_d": {"enabled": True, "t_emb": 0.75}}}
    both_pass = {"corr": 0.0, "lb_a": 1, "lb_b": 2,
                "emb_score": 0.80, "emb_score_global": 0.90}
    assert verdict.pair_links(both_pass, cfg_rule_d_on)
    # One leg below t_emb -> abstains.
    weak_local = {**both_pass, "emb_score": 0.50}
    assert not verdict.pair_links(weak_local, cfg_rule_d_on)
    weak_global = {**both_pass, "emb_score_global": 0.50}
    assert not verdict.pair_links(weak_global, cfg_rule_d_on)
    # NULL on either leg -> abstains.
    null_local = {**both_pass, "emb_score": None}
    assert not verdict.pair_links(null_local, cfg_rule_d_on)
    null_global = {**both_pass, "emb_score_global": None}
    assert not verdict.pair_links(null_global, cfg_rule_d_on)
    # Self-pair (two versions of the same LB#) never fires, even maximal.
    self_pair = {"corr": 0.0, "lb_a": 5, "lb_b": 5,
                "emb_score": 1.0, "emb_score_global": 1.0}
    assert not verdict.pair_links(self_pair, cfg_rule_d_on)
    # Disabled -> abstains even with everything passing.
    cfg_rule_d_off = {**CFG, "addon_links": {
        "rule_d": {"enabled": False, "t_emb": 0.75}}}
    assert not verdict.pair_links(both_pass, cfg_rule_d_off)


def test_cluster_verdicts_is_transitive():
    # A-B strong, B-C strong, A-C weak -> all three in one family.
    pairs = [
        {"lb_a": 1, "lb_b": 2, "corr": 0.9},
        {"lb_a": 2, "lb_b": 3, "corr": 0.9},
        {"lb_a": 1, "lb_b": 3, "corr": 0.0},
    ]
    v = verdict.cluster_verdicts(pairs, CFG)
    assert v[(1, 2)] == verdict.SAME_FAMILY
    assert v[(2, 3)] == verdict.SAME_FAMILY
    assert v[(1, 3)] == verdict.SAME_FAMILY  # linked transitively through 2

    # An independent pair stays different.
    pairs2 = [{"lb_a": 4, "lb_b": 5, "corr": 0.1}]
    assert verdict.cluster_verdicts(pairs2, CFG)[(4, 5)] == verdict.DIFFERENT_FAMILY
