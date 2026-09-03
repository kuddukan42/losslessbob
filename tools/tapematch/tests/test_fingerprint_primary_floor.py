"""Tests for the TODO-325 follow-up gate: match.fingerprint_primary_floor.

Same corroboration idea as match.secondary_primary_floor
(test_secondary_primary_floor.py), scoped to ONLY the fingerprint (base/
staircase/curator) and triplet legs — windowed_frac and hiss are left
completely ungated (see verdict._fingerprint_corroborated,
CALIBRATION_PROGRESS.md "2026-09-02 follow-up"). This is the gate that
separates BUG-331 (an fp-staircase link) from 1980-12-04 (a windowed-leg
link) by mechanism rather than by corr magnitude, which a uniform floor
cannot do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import verdict  # noqa: E402


def _cfg(floor=None, **extra_match):
    match = {"cluster_threshold": 0.45}
    if floor is not None:
        match["fingerprint_primary_floor"] = floor
    match.update(extra_match)
    return {
        "match": match,
        "secondary_match": {"coverage_threshold": 0.35,
                            "hiss_merge_frac": 0.60, "hiss_merge_median": 0.65},
        "fingerprint": {"cluster_threshold": 0.50,
                        "cluster_threshold_staircase": 0.40,
                        "cluster_threshold_curator": 0.43,
                        "staircase_corroboration": {"enabled": False}},
    }


def _pair(**kw):
    p = {"corr": 0.02, "windowed_frac": 0.0, "hiss_frac": 0.0, "hiss_median": 0.0,
         "fp_score": None, "fp_triplet_score": None,
         "speed_kind_a": None, "speed_kind_b": None,
         "lb_a": 1, "lb_b": 2}
    p.update(kw)
    return p


# ── _fingerprint_corroborated ───────────────────────────────────────────────

def test_gate_off_by_default():
    assert verdict._fingerprint_corroborated(_pair(), {"match": {}}) is True
    assert verdict._fingerprint_corroborated(
        _pair(), {"match": {"fingerprint_primary_floor": 0.0}}) is True


def test_gate_blocks_below_floor():
    cfg = {"match": {"fingerprint_primary_floor": 0.10}}
    assert verdict._fingerprint_corroborated(_pair(corr=0.05), cfg) is False


def test_gate_passes_at_or_above_floor():
    cfg = {"match": {"fingerprint_primary_floor": 0.10}}
    assert verdict._fingerprint_corroborated(_pair(corr=0.10), cfg) is True


def test_gate_none_corr_fails_closed():
    cfg = {"match": {"fingerprint_primary_floor": 0.10}}
    assert verdict._fingerprint_corroborated(_pair(corr=None), cfg) is False


# ── pair_links wiring: absent key => byte-identical behaviour ─────────────

def test_absent_floor_keeps_fp_link():
    p = _pair(corr=0.01, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=None)) is True


def test_zero_floor_keeps_same_behaviour_as_absent():
    p = _pair(corr=0.01, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=0.0)) is True


# ── pair_links wiring: floor blocks weak-corr FP/triplet links only ────────

def test_floor_blocks_weak_fp_link_base_bar():
    p = _pair(corr=0.02, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_fp_link_staircase_bar():
    # BUG-331 shape: 2008-07-08, fp 0.417, staircase-relaxed bar, corr 0.0295 —
    # corroborated only by noise-floor hiss under the existing staircase gate.
    p = _pair(corr=0.03, fp_score=0.42, speed_kind_a="staircase/splice",
              hiss_frac=0.134, hiss_median=0.079)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_fp_link_curator_bar():
    p = _pair(corr=0.02, fp_score=0.44)
    assert verdict.pair_links(p, _cfg(floor=0.10), lineage={(1, 2)}) is False


def test_floor_blocks_weak_triplet_link():
    cfg = _cfg(floor=0.10)
    cfg["fingerprint"]["triplet"] = {"enabled": True, "cluster_threshold": 0.45}
    p = _pair(corr=0.02, fp_triplet_score=0.60)
    assert verdict.pair_links(p, cfg) is False


def test_floor_passes_fp_link_with_enough_corr():
    p = _pair(corr=0.12, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is True


# ── the whole point: windowed/hiss legs stay ungated at any floor ──────────

def test_floor_never_gates_windowed_link():
    # 1980-12-04 shape: windowed_frac=1.0 (max), corr 0.0215 — far below any
    # floor tested (up to 0.30), yet must still link: this gate must not
    # touch the windowed leg at all.
    p = _pair(corr=0.0215, windowed_frac=1.0)
    assert verdict.pair_links(p, _cfg(floor=0.30)) is True


def test_floor_never_gates_hiss_link():
    p = _pair(corr=0.02, hiss_frac=0.8, hiss_median=0.8)
    assert verdict.pair_links(p, _cfg(floor=0.30)) is True


# ── pair_links wiring: primary-corr link is never gated by the floor ───────

def test_primary_link_above_cluster_threshold_unaffected_by_floor():
    p = _pair(corr=0.90)
    assert verdict.pair_links(p, _cfg(floor=0.99)) is True


def test_addon_links_not_gated_by_floor():
    cfg = _cfg(floor=0.99)
    cfg["addon_links"] = {"rule_d": {"enabled": True, "t_emb": 0.75}}
    p = _pair(corr=0.02, lb_a=1, lb_b=2,
              **{"emb_score": 0.9, "emb_score_global": 0.9})
    assert verdict.pair_links(p, cfg) is True


# ── both floor keys set at once: a leg must clear whichever gate applies ──

def test_both_floors_set_fp_leg_needs_fingerprint_floor():
    cfg = _cfg(floor=0.10)  # fingerprint_primary_floor
    cfg["match"]["secondary_primary_floor"] = 0.01  # trivially easy
    p = _pair(corr=0.02, fp_score=0.55)  # clears secondary floor, not fp floor
    assert verdict.pair_links(p, cfg) is False


def test_both_floors_set_windowed_leg_needs_secondary_floor_only():
    cfg = _cfg(floor=0.99)  # fingerprint_primary_floor — irrelevant to windowed
    cfg["match"]["secondary_primary_floor"] = 0.01
    p = _pair(corr=0.02, windowed_frac=0.9)  # clears secondary floor (0.01)
    assert verdict.pair_links(p, cfg) is True
