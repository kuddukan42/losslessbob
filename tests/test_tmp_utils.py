"""Tests for backend.tmp_utils — scratch-base selection for temp audio."""
import os

from backend import tmp_utils


def _reset():
    tmp_utils.reset_cache()


def test_env_override_used_when_writable(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSSLESSBOB_TMPDIR", str(tmp_path / "scratch"))
    _reset()
    assert tmp_utils.audio_tmp_dir() == str(tmp_path / "scratch")
    assert (tmp_path / "scratch").is_dir()
    _reset()


def test_unwritable_override_falls_back_to_system_tmp(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    monkeypatch.setenv("LOSSLESSBOB_TMPDIR", str(blocked / "nested"))
    _reset()
    try:
        assert tmp_utils.audio_tmp_dir() is None  # None → tempfile default
    finally:
        blocked.chmod(0o700)
        _reset()


def test_result_is_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSSLESSBOB_TMPDIR", str(tmp_path / "a"))
    _reset()
    first = tmp_utils.audio_tmp_dir()
    monkeypatch.setenv("LOSSLESSBOB_TMPDIR", str(tmp_path / "b"))
    assert tmp_utils.audio_tmp_dir() == first
    _reset()
    assert tmp_utils.audio_tmp_dir() == str(tmp_path / "b")
    _reset()


def test_no_override_probes_scratch_bases(monkeypatch):
    monkeypatch.delenv("LOSSLESSBOB_TMPDIR", raising=False)
    monkeypatch.setattr(tmp_utils, "_SCRATCH_BASES", ())
    _reset()
    assert tmp_utils.audio_tmp_dir() is None
    _reset()


def test_selected_dir_is_writable_when_present(monkeypatch):
    monkeypatch.delenv("LOSSLESSBOB_TMPDIR", raising=False)
    _reset()
    base = tmp_utils.audio_tmp_dir()
    if base is not None:
        assert os.access(base, os.W_OK)
    _reset()
