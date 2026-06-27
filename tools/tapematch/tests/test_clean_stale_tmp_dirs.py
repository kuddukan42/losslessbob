"""Tests for _clean_stale_tmp_dirs's liveness check.

Regression for the temp-dir race: _clean_stale_tmp_dirs() used to rmtree every
tapematch_* dir under TMP_BASE unconditionally before each new subprocess
launch, with no check for whether another tapematch.cli subprocess (this
session or a concurrent one) was still using it -- corrupting its in-flight
memmaps mid-run (FileNotFoundError cascade seen 2026-06-25 across several
validate_polarity.py batch dates).

_tmp_dir_in_use should report a dir as in-use if a file inside it was
modified recently, or if a live process holds an open fd inside it; an old,
untouched, fd-free dir should be reported as not in-use (safe to clean).
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def test_recently_modified_dir_is_in_use(tmp_path: Path) -> None:
    d = tmp_path / "tapematch_abc123"
    d.mkdir()
    (d / "memmap.dat").write_bytes(b"x")
    assert sess._tmp_dir_in_use(d) is True


def test_old_untouched_dir_is_not_in_use(tmp_path: Path) -> None:
    d = tmp_path / "tapematch_old"
    d.mkdir()
    f = d / "memmap.dat"
    f.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(f, (old, old))
    assert sess._tmp_dir_in_use(d, recent_sec=600.0) is False


def test_open_fd_marks_dir_in_use_even_if_old(tmp_path: Path) -> None:
    d = tmp_path / "tapematch_held_open"
    d.mkdir()
    f = d / "memmap.dat"
    f.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(f, (old, old))
    handle = open(f, "rb")
    try:
        assert sess._tmp_dir_in_use(d, recent_sec=600.0) is True
    finally:
        handle.close()


def test_clean_stale_tmp_dirs_skips_in_use_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sess, "TMP_BASE", tmp_path)
    live = tmp_path / "tapematch_live"
    live.mkdir()
    (live / "memmap.dat").write_bytes(b"x")
    stale = tmp_path / "tapematch_stale"
    stale.mkdir()
    f = stale / "memmap.dat"
    f.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(f, (old, old))

    sess._clean_stale_tmp_dirs()

    assert live.exists()
    assert not stale.exists()
