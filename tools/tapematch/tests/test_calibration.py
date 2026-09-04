"""Calibration identity (TODO-333): what collapses, what must not, and drift.

The drift test is the load-bearing one: a new config key must be classified as
decision-relevant or not, deliberately, or the hash silently stops representing
the config.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

SESSION_DIR = Path(__file__).resolve().parents[1]
if str(SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(SESSION_DIR))

from tapematch.calibration import (  # noqa: E402
    DECISION_KEYS,
    GATED_BLOCKS,
    NON_DECISION_KEYS,
    VERDICT_ONLY_KEYS,
    calibration_hash,
    calibration_view,
)

CONFIG_PATH = SESSION_DIR / "config.yaml"


def _leaf_keys(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _leaf_keys(v, prefix + k + ".")
        else:
            yield prefix + k


def test_every_shipped_config_key_is_classified():
    """A new config key must be declared decision-relevant or explicitly not."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    unclassified = sorted(
        k for k in _leaf_keys(cfg)
        if k not in DECISION_KEYS and k not in NON_DECISION_KEYS
    )
    assert not unclassified, (
        "unclassified config keys — add each to DECISION_KEYS (with its code "
        f"default) or NON_DECISION_KEYS in calibration.py: {unclassified}"
    )


def test_verdict_only_keys_are_decision_keys():
    assert VERDICT_ONLY_KEYS <= set(DECISION_KEYS)


def test_gated_blocks_declare_their_gate_key():
    for block, gate in GATED_BLOCKS.items():
        assert f"{block}.{gate}" in DECISION_KEYS


def test_absent_key_at_its_default_does_not_change_the_hash():
    """The whole point: a key added later at the value already in use."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    stripped = yaml.safe_load(CONFIG_PATH.read_text())
    del stripped["match"]["cluster_threshold"]
    stripped["match"]["cluster_threshold"] = DECISION_KEYS["match.cluster_threshold"]
    assert calibration_hash(cfg) == calibration_hash(stripped)


def test_disabled_block_ignores_its_thresholds():
    """rule_a at t_flaw 0.45 and 0.60 are one calibration while it is off."""
    a = {"addon_links": {"rule_a": {"enabled": False, "t_flaw": 0.45, "min_events": 8}}}
    b = {"addon_links": {"rule_a": {"enabled": False, "t_flaw": 0.60, "min_events": 3}}}
    assert calibration_hash(a) == calibration_hash(b)
    assert "addon_links.rule_a.t_flaw" not in calibration_view(a)


def test_enabled_block_does_not_ignore_its_thresholds():
    a = {"addon_links": {"rule_a": {"enabled": True, "t_flaw": 0.45, "min_events": 8}}}
    b = {"addon_links": {"rule_a": {"enabled": True, "t_flaw": 0.60, "min_events": 8}}}
    assert calibration_hash(a) != calibration_hash(b)


def test_threshold_change_changes_the_hash():
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    other = yaml.safe_load(CONFIG_PATH.read_text())
    other["match"]["cluster_threshold"] = 0.55
    assert calibration_hash(cfg) != calibration_hash(other)


def test_non_decision_key_does_not_change_the_hash():
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    other = yaml.safe_load(CONFIG_PATH.read_text())
    other["asr"]["device"] = "cuda"
    other["asr"]["cpu_threads"] = 16
    assert calibration_hash(cfg) == calibration_hash(other)


def test_hash_is_stable_across_key_order():
    a = {"match": {"cluster_threshold": 0.45}, "audio": {"analysis_sr": 16000}}
    b = {"audio": {"analysis_sr": 16000}, "match": {"cluster_threshold": 0.45}}
    assert calibration_hash(a) == calibration_hash(b)


def test_empty_config_hashes_to_the_all_defaults_identity():
    """A run with no stored config is 'every default', not an error."""
    assert calibration_hash({}) == calibration_hash({"unrelated": {"key": 1}})
    assert len(calibration_hash({})) == 12
