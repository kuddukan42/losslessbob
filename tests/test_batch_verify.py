"""
Tests for tools/batch_verify.py helper functions.

Covers fixes landed 2026-06-03:
  BUG-127 — _map_verify_status("missing_files") returned api_error (missing key in map)
  BUG-128 — has_lbdir() didn't find LBF-*-lbdir.txt files (glob "lbdir*.txt" is case-sensitive
             and doesn't match the LBF- prefix convention on Linux)

All tests are pure unit tests; no network, no Flask, no real DB.
"""

import sys
from pathlib import Path

import pytest

# Make tools/ importable when running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from batch_verify import (
    STATUS_MISSING_FILES,
    STATUS_API_ERROR,
    STATUS_PASS,
    STATUS_FAIL,
    STATUS_NO_LBDIR,
    STATUS_PARSE_ERROR,
    _map_verify_status,
    has_lbdir,
)


# ---------------------------------------------------------------------------
# BUG-127: _map_verify_status
# ---------------------------------------------------------------------------

class TestMapVerifyStatus:
    """_map_verify_status must map all known API statuses correctly.

    BUG-127: "missing_files" was not in _VERIFY_STATUS_MAP, so it fell
    through to the STATUS_API_ERROR default.  Every folder with a missing
    lbdir entry was misclassified as api_error with notes=None.
    """

    def test_missing_files_returns_missing_files(self):
        assert _map_verify_status("missing_files") == STATUS_MISSING_FILES

    def test_incomplete_returns_missing_files(self):
        # "incomplete" was already mapped before BUG-127; keep it working
        assert _map_verify_status("incomplete") == STATUS_MISSING_FILES

    def test_pass_returns_pass(self):
        assert _map_verify_status("pass") == STATUS_PASS

    def test_fail_returns_fail(self):
        assert _map_verify_status("fail") == STATUS_FAIL

    def test_no_lbdir_returns_no_lbdir(self):
        assert _map_verify_status("no_lbdir") == STATUS_NO_LBDIR

    def test_parse_error_returns_parse_error(self):
        assert _map_verify_status("parse_error") == STATUS_PARSE_ERROR

    def test_unknown_status_falls_to_api_error(self):
        assert _map_verify_status("totally_unknown_status") == STATUS_API_ERROR

    def test_empty_string_falls_to_api_error(self):
        assert _map_verify_status("") == STATUS_API_ERROR


# ---------------------------------------------------------------------------
# BUG-128: has_lbdir
# ---------------------------------------------------------------------------

class TestHasLbdir:
    """has_lbdir must find both lbdir*.txt and LBF-*-lbdir.txt files.

    BUG-128: the original implementation used glob("lbdir*.txt"), which is
    case-sensitive on Linux and never matched LBF-*-lbdir.txt filenames.
    The fix uses iterdir() + str.lower() to match both conventions.
    """

    def test_standard_lbdir_found(self, tmp_path):
        (tmp_path / "lbdir-LB-12345.txt").touch()
        assert has_lbdir(tmp_path) is True

    def test_lbf_prefix_format_found(self, tmp_path):
        # This was the failing case: LBF-*-lbdir.txt wasn't matched by old glob
        (tmp_path / "LBF-12345-lbdir.txt").touch()
        assert has_lbdir(tmp_path) is True

    def test_lbf_lowercase_name_found(self, tmp_path):
        (tmp_path / "lbf-99-lbdir.txt").touch()
        assert has_lbdir(tmp_path) is True

    def test_uppercase_extension_found(self, tmp_path):
        # .TXT extension (Linux filesystems are case-sensitive)
        (tmp_path / "lbdir-LB-99.TXT").touch()
        assert has_lbdir(tmp_path) is True

    def test_empty_folder_returns_false(self, tmp_path):
        assert has_lbdir(tmp_path) is False

    def test_no_lbdir_file_returns_false(self, tmp_path):
        (tmp_path / "checksums.md5").touch()
        (tmp_path / "info.txt").touch()
        assert has_lbdir(tmp_path) is False

    def test_directory_named_lbdir_not_matched(self, tmp_path):
        # A sub-directory whose name contains "lbdir" must not be matched
        (tmp_path / "lbdir-subdir").mkdir()
        assert has_lbdir(tmp_path) is False

    def test_multiple_files_any_match_returns_true(self, tmp_path):
        (tmp_path / "show.md5").touch()
        (tmp_path / "show.ffp").touch()
        (tmp_path / "LBF-777-lbdir.txt").touch()
        assert has_lbdir(tmp_path) is True
