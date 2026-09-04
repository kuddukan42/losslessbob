"""link_mechanism must name the leg pair_links merged on, and never disagree.

``pair_links`` delegates to ``link_mechanism``, so the equivalence below is true
by construction today; the test exists to catch a future edit that re-forks the
two into separate OR-chains (TODO-336's census reads the mechanism and would
silently mis-bucket).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SESSION_DIR = Path(__file__).resolve().parents[1]
if str(SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR))

from tapematch import verdict as V  # noqa: E402

CFG = {
    "match": {"cluster_threshold": 0.45},
    "secondary_match": {"coverage_threshold": 0.35, "hiss_merge_frac": 0.40,
                        "hiss_merge_median": 0.05},
    "fingerprint": {"cluster_threshold": 0.50, "cluster_threshold_staircase": 0.40,
                    "triplet": {"enabled": True, "cluster_threshold": 0.45}},
}

PAIRS = [
    # (name, pair dict, expected mechanism)
    ("primary", {"lb_a": 1, "lb_b": 2, "corr": 0.90}, "primary"),
    ("windowed", {"lb_a": 1, "lb_b": 2, "corr": 0.10, "windowed_frac": 0.60}, "windowed"),
    ("hiss", {"lb_a": 1, "lb_b": 2, "corr": 0.10, "hiss_frac": 0.55,
              "hiss_median": 0.20}, "hiss"),
    ("fingerprint", {"lb_a": 1, "lb_b": 2, "corr": 0.10, "fp_score": 0.80}, "fingerprint"),
    ("fingerprint_staircase", {"lb_a": 1, "lb_b": 2, "corr": 0.10, "fp_score": 0.42,
                               "speed_kind_a": "staircase/splice",
                               "speed_kind_b": "aligned"}, "fingerprint_staircase"),
    ("triplet", {"lb_a": 1, "lb_b": 2, "corr": 0.10,
                 "fp_triplet_score": 0.70}, "triplet"),
    ("nothing", {"lb_a": 1, "lb_b": 2, "corr": 0.10}, None),
    ("all-null", {"lb_a": 1, "lb_b": 2, "corr": None}, None),
]


@pytest.mark.parametrize("name,pair,expected", PAIRS, ids=[p[0] for p in PAIRS])
def test_link_mechanism_names_expected_leg(name, pair, expected):
    assert V.link_mechanism(pair, CFG) == expected


@pytest.mark.parametrize("name,pair,expected", PAIRS, ids=[p[0] for p in PAIRS])
def test_pair_links_agrees_with_link_mechanism(name, pair, expected):
    assert V.pair_links(pair, CFG) is (V.link_mechanism(pair, CFG) is not None)
    assert V.pair_links(pair, CFG) is (expected is not None)


def test_primary_wins_over_every_other_leg():
    """Mechanism order is the clusterer's order — corr is reported first."""
    pair = {"lb_a": 1, "lb_b": 2, "corr": 0.90, "windowed_frac": 0.99,
            "fp_score": 0.99, "fp_triplet_score": 0.99}
    assert V.link_mechanism(pair, CFG) == "primary"


def test_addon_rule_reported_by_name():
    cfg = dict(CFG)
    cfg["addon_links"] = {"rule_d": {"enabled": True, "t_emb": 0.50}}
    pair = {"lb_a": 1, "lb_b": 2, "corr": 0.10, "emb_score": 0.70,
            "emb_score_global": 0.70}
    assert V.link_mechanism(pair, cfg) == "rule_d"


def test_disabled_addon_rule_does_not_fire():
    cfg = dict(CFG)
    cfg["addon_links"] = {"rule_d": {"enabled": False, "t_emb": 0.50}}
    pair = {"lb_a": 1, "lb_b": 2, "corr": 0.10, "emb_score": 0.70,
            "emb_score_global": 0.70}
    assert V.link_mechanism(pair, cfg) is None
