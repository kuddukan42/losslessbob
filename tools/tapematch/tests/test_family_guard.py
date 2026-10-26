"""TODO-319 — family_guard: weak legs may not chain families together."""
from __future__ import annotations

import copy
import itertools
import random
import sys
from pathlib import Path

import yaml

SESSION_DIR = Path(__file__).resolve().parents[1]
if str(SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR))

from tapematch import verdict as V  # noqa: E402
from tapematch.calibration import (  # noqa: E402
    VERDICT_ONLY_KEYS,
    calibration_hash,
    calibration_view,
)

CONFIG_PATH = SESSION_DIR / "config.yaml"

BASE = {
    "match": {"cluster_threshold": 0.45},
    "fingerprint": {"cluster_threshold": 0.50, "cluster_threshold_staircase": 0.40},
}


def _guard(density: float = 0.5, strong=("primary",)) -> dict:
    cfg = copy.deepcopy(BASE)
    cfg["family_guard"] = {"enabled": True, "strong_legs": list(strong),
                           "min_link_density": density}
    return cfg


def _strong(a: int, b: int) -> dict:
    return {"lb_a": a, "lb_b": b, "corr": 0.9}


def _weak(a: int, b: int) -> dict:
    """Links only via the staircase-relaxed fingerprint leg."""
    return {"lb_a": a, "lb_b": b, "corr": 0.1, "fp_score": 0.42,
            "speed_kind_a": "staircase/splice", "speed_kind_b": "aligned"}


def _none(a: int, b: int) -> dict:
    return {"lb_a": a, "lb_b": b, "corr": 0.05}


def _components(nodes, edges):
    fam = {n: {n} for n in nodes}
    for a, b in edges:
        if fam[a] is not fam[b]:
            merged = fam[a] | fam[b]
            for m in merged:
                fam[m] = merged
    return sorted(sorted(s) for s in {frozenset(s) for s in fam.values()})


def test_guard_off_is_single_linkage():
    rng = random.Random(319)
    for _ in range(200):
        nodes = list(range(rng.randint(1, 9)))
        edges = {(a, b): rng.choice(["primary", "fingerprint_staircase"])
                 for a, b in itertools.combinations(nodes, 2) if rng.random() < 0.3}
        got = sorted(sorted(f) for f in V.form_families(nodes, edges, BASE))
        assert got == _components(nodes, edges)


def test_disabled_block_is_single_linkage():
    cfg = _guard()
    cfg["family_guard"]["enabled"] = False
    pairs = [_strong(1, 2), _strong(2, 3), _weak(3, 4), _none(1, 4), _none(2, 4)]
    v = V.cluster_verdicts(pairs, cfg)
    assert v[(1, 4)] == V.SAME_FAMILY


def test_single_weak_edge_cannot_chain_into_family():
    # {1,2,3} strong; 4 touches the family through one weak edge (density 1/3).
    pairs = [_strong(1, 2), _strong(2, 3), _strong(1, 3),
             _weak(3, 4), _none(1, 4), _none(2, 4)]
    v = V.cluster_verdicts(pairs, _guard(0.5))
    assert v[(1, 2)] == V.SAME_FAMILY
    assert v[(3, 4)] == V.DIFFERENT_FAMILY
    assert v[(1, 4)] == V.DIFFERENT_FAMILY


def test_dense_weak_edges_still_merge():
    pairs = [_strong(1, 2), _weak(1, 3), _weak(2, 3)]
    v = V.cluster_verdicts(pairs, _guard(0.5))
    assert v[(1, 3)] == V.SAME_FAMILY and v[(2, 3)] == V.SAME_FAMILY


def test_weak_path_without_direct_leg_is_split():
    # 1-2-3 weak path: pair (1, 3) has no direct leg and density stays below 1.
    pairs = [_weak(1, 2), _weak(2, 3), _none(1, 3)]
    assert V.cluster_verdicts(pairs, _guard(0.67))[(1, 3)] == V.DIFFERENT_FAMILY
    # At 0.5 the 1/2 cross density admits the chain — the knob is the cut.
    assert V.cluster_verdicts(pairs, _guard(0.5))[(1, 3)] == V.SAME_FAMILY


def test_strong_legs_union_freely():
    pairs = [_weak(1, 2), _weak(2, 3), _none(1, 3)]
    cfg = _guard(1.0, strong=("primary", "fingerprint_staircase"))
    assert V.cluster_verdicts(pairs, cfg)[(1, 3)] == V.SAME_FAMILY


def test_tiny_density_reduces_to_single_linkage():
    pairs = [_strong(1, 2), _strong(2, 3), _weak(3, 4), _none(1, 4), _none(2, 4)]
    assert V.cluster_verdicts(pairs, _guard(0.01))[(1, 4)] == V.SAME_FAMILY


def test_self_pair_is_ignored():
    pairs = [_strong(1, 1), _weak(1, 2)]
    v = V.cluster_verdicts(pairs, _guard(0.5))
    assert v[(1, 1)] == V.SAME_FAMILY and v[(1, 2)] == V.SAME_FAMILY


def test_shipped_config_guard_is_on():
    # tj enabled it 2026-10-26 (TODO-319); replay_writeback applied it to stored runs.
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    assert V.family_guard_cfg(cfg) is not None


def _guard_off(cfg: dict) -> dict:
    off = copy.deepcopy(cfg)
    off["family_guard"]["enabled"] = False
    return off


def test_disabled_guard_does_not_change_calibration_hash():
    off = _guard_off(yaml.safe_load(CONFIG_PATH.read_text()))
    stripped = copy.deepcopy(off)
    stripped.pop("family_guard")
    assert calibration_hash(off) == calibration_hash(stripped)
    assert not any(k.startswith("family_guard") for k in calibration_view(off))


def test_enabled_guard_changes_hash_and_is_replayable():
    cfg = _guard_off(yaml.safe_load(CONFIG_PATH.read_text()))
    on = copy.deepcopy(cfg)
    on["family_guard"]["enabled"] = True
    assert calibration_hash(on) != calibration_hash(cfg)
    keys = {k for k in calibration_view(on) if k.startswith("family_guard")}
    assert keys and keys <= VERDICT_ONLY_KEYS
