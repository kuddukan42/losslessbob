"""Tests for the TODO-325 secondary-corroboration gate (BUG-331).

Covers verdict._secondary_corroborated + its wiring across the windowed,
hiss, fingerprint (base/staircase/curator), and triplet OR-legs in
pair_links — and the absent-config-key == historical-behaviour guarantee.
Deliberately does NOT cover addon_links (Rules A-D): the gate is scoped to
exclude them (see verdict.py module docstring, CALIBRATION_PROGRESS.md
"2026-09-02 TODO-325").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import verdict  # noqa: E402


def _cfg(floor=None, **extra_match):
    match = {"cluster_threshold": 0.45}
    if floor is not None:
        match["secondary_primary_floor"] = floor
    match.update(extra_match)
    cfg = {
        "match": match,
        "secondary_match": {"coverage_threshold": 0.35,
                            "hiss_merge_frac": 0.60, "hiss_merge_median": 0.65},
        "fingerprint": {"cluster_threshold": 0.50,
                        "cluster_threshold_staircase": 0.40,
                        "cluster_threshold_curator": 0.43,
                        "staircase_corroboration": {"enabled": False}},
    }
    return cfg


def _pair(**kw):
    p = {"corr": 0.02, "windowed_frac": 0.0, "hiss_frac": 0.0, "hiss_median": 0.0,
         "fp_score": None, "fp_triplet_score": None,
         "speed_kind_a": None, "speed_kind_b": None,
         "lb_a": 1, "lb_b": 2}
    p.update(kw)
    return p


# ── _secondary_corroborated ─────────────────────────────────────────────────

def test_gate_off_by_default():
    assert verdict._secondary_corroborated(_pair(), {"match": {}}) is True
    assert verdict._secondary_corroborated(
        _pair(), {"match": {"secondary_primary_floor": 0.0}}) is True


def test_gate_blocks_below_floor():
    cfg = {"match": {"secondary_primary_floor": 0.10}}
    assert verdict._secondary_corroborated(_pair(corr=0.05), cfg) is False


def test_gate_passes_at_or_above_floor():
    cfg = {"match": {"secondary_primary_floor": 0.10}}
    assert verdict._secondary_corroborated(_pair(corr=0.10), cfg) is True
    assert verdict._secondary_corroborated(_pair(corr=0.20), cfg) is True


def test_gate_none_corr_fails_closed():
    cfg = {"match": {"secondary_primary_floor": 0.10}}
    assert verdict._secondary_corroborated(_pair(corr=None), cfg) is False


# ── pair_links wiring: absent key => byte-identical behaviour ─────────────

def test_absent_floor_keeps_windowed_link():
    p = _pair(corr=0.01, windowed_frac=0.9)
    assert verdict.pair_links(p, _cfg(floor=None)) is True


def test_absent_floor_keeps_hiss_link():
    p = _pair(corr=0.01, hiss_frac=0.8, hiss_median=0.8)
    assert verdict.pair_links(p, _cfg(floor=None)) is True


def test_absent_floor_keeps_fp_link():
    p = _pair(corr=0.01, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=None)) is True


def test_zero_floor_keeps_same_behaviour_as_absent():
    p = _pair(corr=0.01, windowed_frac=0.9)
    assert verdict.pair_links(p, _cfg(floor=0.0)) is True


# ── pair_links wiring: floor set blocks a weak-corr secondary-only link ────

def test_floor_blocks_weak_windowed_link():
    p = _pair(corr=0.02, windowed_frac=0.9)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_hiss_link():
    p = _pair(corr=0.02, hiss_frac=0.8, hiss_median=0.8)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_fp_link_base_bar():
    p = _pair(corr=0.02, fp_score=0.55)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_fp_link_staircase_bar():
    # BUG-331 shape: staircase-relaxed fp bar, weak corr.
    p = _pair(corr=0.03, fp_score=0.42, speed_kind_a="staircase/splice")
    assert verdict.pair_links(p, _cfg(floor=0.10)) is False


def test_floor_blocks_weak_fp_link_curator_bar():
    p = _pair(corr=0.02, fp_score=0.44)
    assert verdict.pair_links(p, _cfg(floor=0.10), lineage={(1, 2)}) is False


def test_floor_blocks_weak_triplet_link():
    cfg = _cfg(floor=0.10)
    cfg["fingerprint"]["triplet"] = {"enabled": True, "cluster_threshold": 0.45}
    p = _pair(corr=0.02, fp_triplet_score=0.60)
    assert verdict.pair_links(p, cfg) is False


def test_floor_passes_secondary_link_with_enough_corr():
    p = _pair(corr=0.12, windowed_frac=0.9)
    assert verdict.pair_links(p, _cfg(floor=0.10)) is True


# ── pair_links wiring: primary-corr link is never gated by the floor ───────

def test_primary_link_above_cluster_threshold_unaffected_by_floor():
    # corr alone clears match.cluster_threshold — the floor is irrelevant,
    # even set far above the pair's own corr (which IS the primary signal).
    p = _pair(corr=0.90)
    assert verdict.pair_links(p, _cfg(floor=0.99)) is True


def test_addon_links_not_gated_by_floor():
    # TODO-325 scoping decision: addon_links (Rule D shown here) is
    # independently calibrated and deliberately excluded from this gate.
    cfg = _cfg(floor=0.99)
    cfg["addon_links"] = {"rule_d": {"enabled": True, "t_emb": 0.75}}
    p = _pair(corr=0.02, lb_a=1, lb_b=2,
              **{"emb_score": 0.9, "emb_score_global": 0.9})
    assert verdict.pair_links(p, cfg) is True
