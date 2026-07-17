"""Tests for the staircase fp-relaxation mitigations (2026-07-16).

Covers verdict._is_staircase scope handling, the corroboration gate
(_staircase_corroborated + its wiring in pair_links), and the
absent-config-keys == historical-behaviour guarantee.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import verdict  # noqa: E402


def _cfg(**fp_extra):
    fp = {"cluster_threshold": 0.50, "cluster_threshold_staircase": 0.40}
    fp.update(fp_extra)
    return {"match": {"cluster_threshold": 0.45},
            "secondary_match": {"coverage_threshold": 0.35,
                                "hiss_merge_frac": 0.75, "hiss_merge_median": 0.65},
            "fingerprint": fp}


def _pair(**kw):
    p = {"corr": 0.01, "windowed_frac": 0.0, "hiss_frac": 0.0, "hiss_median": 0.0,
         "fp_score": None, "speed_kind_a": None, "speed_kind_b": None,
         "lb_a": 1, "lb_b": 2}
    p.update(kw)
    return p


# ── staircase scope ────────────────────────────────────────────────────────────

def test_scope_default_source_either_side():
    p = _pair(speed_kind_a="staircase/splice")
    assert verdict._is_staircase(p, {}) is True
    assert verdict._is_staircase(p, {"staircase_scope": "source"}) is True


def test_scope_pair_requires_both_sides():
    one = _pair(speed_kind_a="staircase/splice")
    both = _pair(speed_kind_a="staircase/splice", speed_kind_b="staircase/splice")
    fp_cfg = {"staircase_scope": "pair"}
    assert verdict._is_staircase(one, fp_cfg) is False
    assert verdict._is_staircase(both, fp_cfg) is True


# ── corroboration gate ─────────────────────────────────────────────────────────

def test_gate_off_by_default():
    assert verdict._staircase_corroborated(_pair(), {}) is True
    assert verdict._staircase_corroborated(
        _pair(), {"staircase_corroboration": {"enabled": False}}) is True


def _gate_cfg():
    return {"staircase_corroboration":
            {"enabled": True, "min_windowed_frac": 0.05, "min_hiss_frac": 0.05}}


def test_gate_blocks_zero_corroboration():
    p = _pair(windowed_frac=0.0, hiss_frac=0.0)
    assert verdict._staircase_corroborated(p, _gate_cfg()) is False


def test_gate_none_signals_count_as_no_corroboration():
    p = _pair(windowed_frac=None, hiss_frac=None)
    assert verdict._staircase_corroborated(p, _gate_cfg()) is False


def test_gate_passes_on_either_floor():
    assert verdict._staircase_corroborated(
        _pair(windowed_frac=0.06, hiss_frac=0.0), _gate_cfg()) is True
    assert verdict._staircase_corroborated(
        _pair(windowed_frac=0.0, hiss_frac=0.06), _gate_cfg()) is True


# ── pair_links wiring ──────────────────────────────────────────────────────────

def _stair_pair(fp, wf=0.0, hf=0.0):
    return _pair(fp_score=fp, windowed_frac=wf, hiss_frac=hf,
                 speed_kind_a="staircase/splice")


def test_relaxed_merge_blocked_without_corroboration():
    # The 1997-11-11 LB-01126 signature: fp at the same-show floor, staircase-
    # relaxed bar, zero windowed/hiss.
    cfg = _cfg(staircase_corroboration={"enabled": True,
                                        "min_windowed_frac": 0.05,
                                        "min_hiss_frac": 0.05})
    assert verdict.pair_links(_stair_pair(0.41), cfg) is False


def test_relaxed_merge_allowed_with_corroboration():
    cfg = _cfg(staircase_corroboration={"enabled": True,
                                        "min_windowed_frac": 0.05,
                                        "min_hiss_frac": 0.05})
    assert verdict.pair_links(_stair_pair(0.41, hf=0.06), cfg) is True


def test_full_bar_merge_never_gated():
    # fp above the un-relaxed base threshold does not rely on the relaxation.
    cfg = _cfg(staircase_corroboration={"enabled": True,
                                        "min_windowed_frac": 0.05,
                                        "min_hiss_frac": 0.05})
    assert verdict.pair_links(_stair_pair(0.55), cfg) is True


def test_curator_relaxed_merge_not_gated():
    # A merge clearing the curator bar (0.43) without the staircase relaxation
    # is a lineage-prior decision, not a staircase one — the gate must not block.
    cfg = _cfg(cluster_threshold_curator=0.43,
               staircase_corroboration={"enabled": True,
                                        "min_windowed_frac": 0.05,
                                        "min_hiss_frac": 0.05})
    p = _stair_pair(0.44)
    assert verdict.pair_links(p, cfg, lineage={(1, 2)}) is True


def test_absent_keys_keep_historical_behaviour():
    # No scope/corroboration keys: staircase-relaxed fp merge fires as before.
    assert verdict.pair_links(_stair_pair(0.41), _cfg()) is True
