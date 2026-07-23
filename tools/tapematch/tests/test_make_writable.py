"""Tests for _make_writable, the read-only-example-folder guard.

Regression for the crawl wedge of 2026-07-21/22 (BUG-272): some source folders
on the archive volumes are mode 0o555, and shutil.copytree preserves that mode
on the copy it drops in EXAMPLES_DIR. A read-only directory's entries cannot be
unlinked, so the next clean_examples() died with PermissionError -- before doing
any work -- for every subsequent date. run_crawl.sh skip-listed six innocent
dates and then aborted with "10 consecutive failures overall", leaving the
crawl dead for ~20 hours with 436 dates outstanding.

_make_writable must restore the owner write bit on a directory tree so that
rmtree succeeds, and must be a harmless no-op on paths that do not exist.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def _read_only_tree(root: Path) -> Path:
    """Build a copytree-style folder whose directories are mode 0o555."""
    (root / "disc 1").mkdir(parents=True)
    (root / "disc 1" / "t01.flac").write_text("x")
    (root / "disc 1").chmod(0o555)
    root.chmod(0o555)
    return root


def test_read_only_tree_blocks_rmtree(tmp_path: Path) -> None:
    tree = _read_only_tree(tmp_path / "1974-01-30 Somewhere (LB-03652)")
    with pytest.raises(PermissionError):
        shutil.rmtree(tree)
    sess._make_writable(tree)  # leave tmp_path removable for the fixture teardown


def test_make_writable_allows_rmtree(tmp_path: Path) -> None:
    tree = _read_only_tree(tmp_path / "1974-01-30 Somewhere (LB-03652)")
    sess._make_writable(tree)
    shutil.rmtree(tree)
    assert not tree.exists()


def test_make_writable_ignores_missing_path(tmp_path: Path) -> None:
    sess._make_writable(tmp_path / "does-not-exist")
