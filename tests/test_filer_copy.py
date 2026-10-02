"""Tests for filer._copy_verified — the staged, fsynced, hash-verified copy.

Covers: the copy lands under its final name only after verification, the
staging folder never survives (success or failure), a hash mismatch or a
failed flush leaves the source untouched and no destination, and a stale
staging folder from a crashed job is replaced rather than merged into.
"""

from __future__ import annotations

import errno
import os
import time
from pathlib import Path

import pytest

import backend.filer as filer


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A source folder, a destination parent, and a cache-free source digest."""
    src = tmp_path / "src" / "LB-00001 show"
    (src / "sub").mkdir(parents=True)
    (src / "a.flac").write_bytes(b"a" * 4096)
    (src / "sub" / "b.txt").write_bytes(b"notes")
    dest_parent = tmp_path / "dest"
    dest_parent.mkdir()
    monkeypatch.setattr(filer, "_source_tree_digest", filer.hash_tree)
    return src, dest_parent / src.name


def _leftovers(dest: Path) -> list[str]:
    return sorted(p.name for p in dest.parent.iterdir())


def test_copy_lands_verified_and_flushed(tree, monkeypatch):
    src, dest = tree
    synced: list[str] = []
    real_fsync = filer._fsync_path

    def _spy(path, *, required):
        synced.append(os.path.basename(str(path)))
        real_fsync(path, required=required)

    monkeypatch.setattr(filer, "_fsync_path", _spy)
    filer._copy_verified(src, dest)

    assert filer.hash_tree(dest) == filer.hash_tree(src)
    assert _leftovers(dest) == [dest.name]
    assert {"a.flac", "b.txt", "sub", dest.parent.name} <= set(synced)


def test_staging_is_hidden_until_rename(tree, monkeypatch):
    src, dest = tree
    seen: list[tuple[bool, bool]] = []
    real_hash = filer.hash_tree

    def _hash(root):
        seen.append((dest.exists(), filer._staging_path(dest).exists()))
        return real_hash(root)

    monkeypatch.setattr(filer, "hash_tree", _hash)
    filer._copy_verified(src, dest)

    assert seen[0] == (False, True)
    assert filer._staging_path(dest).name.startswith(".")


def test_hash_mismatch_removes_staging_keeps_source(tree, monkeypatch):
    src, dest = tree
    before = filer.hash_tree(src)
    monkeypatch.setattr(filer, "_source_tree_digest", lambda folder: "not-the-digest")

    with pytest.raises(filer._HashVerificationError):
        filer._copy_verified(src, dest)

    assert _leftovers(dest) == []
    assert filer.hash_tree(src) == before


def test_flush_failure_removes_staging_keeps_source(tree, monkeypatch):
    src, dest = tree

    def _eio(fd):
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(filer.os, "fsync", _eio)
    with pytest.raises(OSError):
        filer._copy_verified(src, dest)

    assert _leftovers(dest) == []
    assert (src / "a.flac").exists()


def test_unsupported_fsync_does_not_block(tree, monkeypatch):
    src, dest = tree

    def _einval(fd):
        raise OSError(errno.EINVAL, "fsync not supported")

    monkeypatch.setattr(filer.os, "fsync", _einval)
    filer._copy_verified(src, dest)

    assert filer.hash_tree(dest) == filer.hash_tree(src)


def test_stale_staging_is_replaced(tree):
    src, dest = tree
    stale = filer._staging_path(dest)
    stale.mkdir()
    (stale / "leftover.flac").write_bytes(b"half a file")

    filer._copy_verified(src, dest)

    assert not (dest / "leftover.flac").exists()
    assert _leftovers(dest) == [dest.name]


def test_staging_name_fits_name_max(tmp_path):
    dest = tmp_path / ("x" * 250)
    staging = filer._staging_path(dest)

    assert len(os.fsencode(staging.name)) <= 255
    assert staging.name.startswith(".") and staging.name.endswith(filer.STAGING_SUFFIX)


# ── start_file_job wiring ─────────────────────────────────────────────────────

class _NoRow:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args):
        return self

    def fetchone(self):
        return None


@pytest.fixture
def job(tree, monkeypatch):
    """start_file_job with the DB, routing and qBittorrent layers stubbed out."""
    src, dest = tree
    added: list[tuple] = []
    monkeypatch.setattr(filer, "resolve_destination_for_lb", lambda *a, **k: {
        "ok": True, "dest_parent": str(dest.parent), "dest": str(dest), "mount_label": "M",
    })
    monkeypatch.setattr(filer.database, "get_folder_state", lambda path: None)
    monkeypatch.setattr(filer.database, "get_connection", lambda db_path=None: _NoRow())
    monkeypatch.setattr(
        filer.database, "add_to_collection", lambda *a, **k: added.append(a),
    )
    monkeypatch.setattr(filer, "_sync_qbt_location", lambda *a, **k: (False, None))
    monkeypatch.setattr("backend.seed_overlay.warn_if_seeded", lambda *a, **k: None)

    def _run(file_mode: str) -> dict:
        assert filer.start_file_job(1, str(src), file_mode=file_mode)["ok"]
        deadline = time.monotonic() + 10
        while filer.get_file_job_status()["running"]:
            assert time.monotonic() < deadline, "filing job did not finish"
            time.sleep(0.01)
        return filer.get_file_job_status()["result"]

    return src, dest, added, _run


def _cross_device(monkeypatch, src: Path) -> None:
    real_rename = os.rename

    def _rename(a, b):
        if str(a) == str(src):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        real_rename(a, b)

    monkeypatch.setattr(filer.os, "rename", _rename)


def test_job_copy_keeps_source(job):
    src, dest, added, run = job
    result = run("copy")

    assert result["ok"], result
    assert filer.hash_tree(dest) == filer.hash_tree(src)
    assert _leftovers(dest) == [dest.name]
    assert len(added) == 1


def test_job_cross_device_move_removes_source_after_verify(job, monkeypatch):
    src, dest, added, run = job
    before = filer.hash_tree(src)
    _cross_device(monkeypatch, src)
    result = run("move")

    assert result["ok"], result
    assert not src.exists()
    assert filer.hash_tree(dest) == before
    assert _leftovers(dest) == [dest.name]


def test_job_cross_device_mismatch_keeps_source(job, monkeypatch):
    src, dest, added, run = job
    _cross_device(monkeypatch, src)
    monkeypatch.setattr(filer, "_source_tree_digest", lambda folder: "not-the-digest")
    result = run("move")

    assert result["error_code"] == "hash_mismatch"
    assert src.exists() and (src / "a.flac").exists()
    assert _leftovers(dest) == []
    assert added == []
