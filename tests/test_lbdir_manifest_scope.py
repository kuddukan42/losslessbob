"""Tests for BUG-315 — the folder's lbdir manifest is scoped to its LB.

`_find_lbdir_in_folder` is module-level in `backend.app`, so these drive the
real selector used by the pipeline LBDIR stage and the /api/lbdir/* endpoints.
After an "Override LB#" the folder still holds the manifest copied in for the
previously-matched LB; the selector must ignore it so callers retrieve the
right one instead of verifying against the wrong archive entry.
"""

from pathlib import Path

from backend.app import _find_lbdir_in_folder, _lbdir_file_lb


def _touch(folder: Path, name: str) -> Path:
    p = folder / name
    p.write_text("md5 section\n")
    return p


def test_lbdir_file_lb_parses_lbf_prefix(tmp_path):
    assert _lbdir_file_lb(tmp_path / "LBF-01234-lbdir.txt") == 1234
    assert _lbdir_file_lb(tmp_path / "LBF-01234-xref-00002-lbdir.txt") == 1234
    assert _lbdir_file_lb(tmp_path / "lbdir.txt") is None


def test_unscoped_call_keeps_legacy_behaviour(tmp_path):
    f = _touch(tmp_path, "LBF-01234-lbdir.txt")
    assert _find_lbdir_in_folder(tmp_path) == f


def test_matching_lb_manifest_is_returned(tmp_path):
    f = _touch(tmp_path, "LBF-01234-lbdir.txt")
    assert _find_lbdir_in_folder(tmp_path, 1234) == f


def test_stale_manifest_from_another_lb_is_ignored(tmp_path):
    """The override case: folder still holds the old LB's manifest."""
    _touch(tmp_path, "LBF-01234-lbdir.txt")
    assert _find_lbdir_in_folder(tmp_path, 9999) is None


def test_correct_manifest_wins_when_both_present(tmp_path):
    _touch(tmp_path, "LBF-01234-lbdir.txt")
    right = _touch(tmp_path, "LBF-09999-lbdir.txt")
    assert _find_lbdir_in_folder(tmp_path, 9999) == right


def test_untagged_manifest_is_accepted_for_any_lb(tmp_path):
    """A folder-supplied lbdir.txt carries no attribution — never reject it."""
    f = _touch(tmp_path, "lbdir.txt")
    assert _find_lbdir_in_folder(tmp_path, 9999) == f


def test_canonical_manifest_accepted_for_alias_lb(tmp_path, monkeypatch):
    """Alias LBs legitimately carry their canonical's manifest."""
    f = _touch(tmp_path, "LBF-01234-lbdir.txt")
    monkeypatch.setattr(
        "backend.app.database.resolve_aliases", lambda lbs: [1234],
    )
    assert _find_lbdir_in_folder(tmp_path, 9999) == f


def test_empty_and_missing_folder(tmp_path):
    assert _find_lbdir_in_folder(tmp_path, 1234) is None
    assert _find_lbdir_in_folder(tmp_path / "nope", 1234) is None
