"""Tests for backend/config_version.py (TODO-306 Phase 2).

Covers hash stability, monkeypatch sensitivity (each hash only reacts to its
own constant list), the rename guard against concert_ranker.config, and
version_state()'s classification.
"""

from __future__ import annotations

import backend.config_version as config_version
import backend.db as db
import concert_ranker.config as cr_config


def test_taper_hash_stable_across_calls():
    assert config_version.taper_config_hash() == config_version.taper_config_hash()


def test_taper_hash_insensitive_to_dict_order():
    original = dict(db._KNOWN_TAPER_ALIASES)
    h1 = config_version.taper_config_hash()
    reordered = dict(reversed(list(original.items())))
    db._KNOWN_TAPER_ALIASES.clear()
    db._KNOWN_TAPER_ALIASES.update(reordered)
    try:
        h2 = config_version.taper_config_hash()
    finally:
        db._KNOWN_TAPER_ALIASES.clear()
        db._KNOWN_TAPER_ALIASES.update(original)
    assert h1 == h2


def test_taper_hash_changes_on_alias_edit():
    original = dict(db._KNOWN_TAPER_ALIASES)
    h1 = config_version.taper_config_hash()
    db._KNOWN_TAPER_ALIASES["zzz_test_alias"] = "zzz_test_canonical"
    try:
        h2 = config_version.taper_config_hash()
    finally:
        db._KNOWN_TAPER_ALIASES.clear()
        db._KNOWN_TAPER_ALIASES.update(original)
    assert h1 != h2


def test_taper_hash_changes_on_not_taper_edit():
    original = db._NOT_TAPER
    h1 = config_version.taper_config_hash()
    db._NOT_TAPER = original | {"zzz_test_not_taper"}
    try:
        h2 = config_version.taper_config_hash()
    finally:
        db._NOT_TAPER = original
    assert h1 != h2


def test_rank_hash_changes_on_quality_bands_scan_hash_does_not(monkeypatch):
    scan_before = config_version.ranker_scan_config_hash()
    rank_before = config_version.ranker_rank_config_hash()

    monkeypatch.setattr(cr_config, "QUALITY_BANDS", {**cr_config.QUALITY_BANDS, "_test": 1})

    assert config_version.ranker_rank_config_hash() != rank_before
    assert config_version.ranker_scan_config_hash() == scan_before


def test_scan_hash_changes_on_bulk_sr_rank_hash_does_not(monkeypatch):
    scan_before = config_version.ranker_scan_config_hash()
    rank_before = config_version.ranker_rank_config_hash()

    monkeypatch.setattr(cr_config, "BULK_SR", cr_config.BULK_SR + 1)

    assert config_version.ranker_scan_config_hash() != scan_before
    assert config_version.ranker_rank_config_hash() == rank_before


def test_constant_names_exist_in_concert_ranker_config():
    for name in (*config_version._SCAN_CONFIG_NAMES, *config_version._RANK_CONFIG_NAMES):
        assert hasattr(cr_config, name), f"{name} missing from concert_ranker.config"


def test_disqualifiers_serialises():
    h = config_version.ranker_scan_config_hash()
    assert isinstance(h, str) and len(h) == 16


def test_version_state_unstamped_for_none():
    assert config_version.version_state("attribute_tapers", None) == "unstamped"


def test_version_state_na_for_unversioned_step():
    assert config_version.version_state("olof_fetch", "anything") == "n/a"


def test_version_state_ok_when_matching():
    current = config_version.ranker_scan_config_hash()
    assert config_version.version_state("ranker_scan", current) == "ok"


def test_version_state_changed_when_mismatched():
    assert config_version.version_state("ranker_scan", "not-a-real-hash") == "changed"


def test_stamp_for_step_writes_meta(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    value = config_version.stamp_for_step("ranker_rerank", db_path)
    assert value is not None
    assert db.get_meta("refresh_version_ranker_rank_config", db_path) == value


def test_stamp_for_step_noop_for_unversioned_step(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    assert config_version.stamp_for_step("olof_fetch", db_path) is None
