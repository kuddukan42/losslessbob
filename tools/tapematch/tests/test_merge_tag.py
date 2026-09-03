"""BUG-329: the SECONDARY MATCH display tag must be derived from the same
predicate (verdict.pair_links) that match.cluster uses for the actual merge
decision -- not a separately hand-rolled threshold expression that can (and
did) disagree with it.

Pins the case from the bug report: hiss_median fails hiss_merge_median (so a
hand-rolled hiss-only check reports "below merge threshold"), but the pair
still links via another path (here: fingerprint cluster_threshold) -- the tag
must say SECONDARY LINK because that is what actually gets merged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch.cli import _merge_tag  # noqa: E402
from tapematch import verdict  # noqa: E402

CFG = {
    "match": {"cluster_threshold": 0.45},
    "secondary_match": {
        "coverage_threshold": 0.35,
        "hiss_frac_threshold": 0.30,
        "hiss_merge_frac": 0.60,
        "hiss_merge_median": 0.65,
    },
    "fingerprint": {"match_threshold": 0.50, "cluster_threshold": 0.50},
}


def test_merge_tag_links_via_fingerprint_despite_failing_hiss_median():
    """Reproduces BUG-329: hiss_median (0.222) fails hiss_merge_median (0.65),
    but fp_score clears fingerprint.cluster_threshold -- the pair DOES link,
    so the tag must be SECONDARY LINK, not "below merge threshold".
    """
    pair = {
        "corr": 0.074,
        "windowed_frac": 0.10,
        "hiss_frac": 0.58,
        "hiss_median": 0.222,
        "fp_score": 0.60,
        "speed_kind_a": None, "speed_kind_b": None,
        "lb_a": None, "lb_b": None,
    }
    assert verdict.pair_links(pair, CFG, lineage=None) is True
    assert _merge_tag(pair, CFG, lineage=None) == "→ SECONDARY LINK"


def test_merge_tag_below_threshold_when_no_path_links():
    """Same failing hiss_median, but no other signal clears its bar either --
    pair_links is False and the tag must say so.
    """
    pair = {
        "corr": 0.074,
        "windowed_frac": 0.10,
        "hiss_frac": 0.58,
        "hiss_median": 0.222,
        "fp_score": 0.10,
        "speed_kind_a": None, "speed_kind_b": None,
        "lb_a": None, "lb_b": None,
    }
    assert verdict.pair_links(pair, CFG, lineage=None) is False
    assert _merge_tag(pair, CFG, lineage=None) == "→ below merge threshold"


def test_merge_tag_agrees_with_pair_links_always():
    """The tag is a pure function of pair_links -- assert the equivalence
    directly so the helper can never drift from the clustering predicate again.
    """
    for pair, expect_link in (
        ({"corr": 0.60, "speed_kind_a": None, "speed_kind_b": None,
          "lb_a": None, "lb_b": None}, True),   # primary corr alone clears m_thr
        ({"corr": 0.01, "speed_kind_a": None, "speed_kind_b": None,
          "lb_a": None, "lb_b": None}, False),  # nothing clears any bar
    ):
        linked = verdict.pair_links(pair, CFG, lineage=None)
        assert linked is expect_link
        tag = _merge_tag(pair, CFG, lineage=None)
        assert tag == ("→ SECONDARY LINK" if linked else "→ below merge threshold")
