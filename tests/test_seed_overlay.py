"""Tests for backend.seed_overlay — assembling a seedable copy safely.

The central promise is that the source collection folder is never written to,
so several tests assert that explicitly rather than only checking the overlay.
"""
import hashlib
import os
import shutil

import pytest

from backend.seed_overlay import (
    COPY,
    FETCH,
    LINK,
    REFETCH,
    build_overlay,
    collection_is_untouched,
    overlay_status,
    plan_overlay,
    snapshot_folder,
    verify_overlay,
)
from backend.torrent_verify import read_torrent

PIECE_LEN = 512


def _bencode(value) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return _bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(_bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(
            _bencode(k) + _bencode(value[k]) for k in sorted(value)
        ) + b"e"
    raise TypeError(type(value))


def _pieces(blobs: list[bytes]) -> bytes:
    stream = b"".join(blobs)
    return b"".join(
        hashlib.sha1(stream[i:i + PIECE_LEN]).digest()
        for i in range(0, len(stream), PIECE_LEN)
    )


ROOT = "Show (LB-00042)"
# Two audio files then two sidecars; audio is big enough to span pieces.
FILES = {
    "t01.flac": b"\x11" * 1300,
    "t02.flac": b"\x22" * 1100,
    "LBF-00042-info.txt": b"info text\n" * 5,
    "LBF-00042-check.md5.txt": b"d41d8cd98f00b204e9800998ecf8427e *t01.flac\n",
}


@pytest.fixture
def rig(tmp_path):
    """Build a torrent, a collection folder with audio only, and a sidecar store."""
    torrent_meta = {b"info": {
        b"name": ROOT.encode(),
        b"piece length": PIECE_LEN,
        b"pieces": _pieces(list(FILES.values())),
        b"files": [{b"path": [n.encode()], b"length": len(b)}
                   for n, b in FILES.items()],
    }}
    torrent = tmp_path / "t.torrent"
    torrent.write_bytes(_bencode(torrent_meta))

    collection = tmp_path / "collection" / ROOT
    collection.mkdir(parents=True)
    for name in ("t01.flac", "t02.flac"):
        (collection / name).write_bytes(FILES[name])

    sidecars = tmp_path / "site_files"
    sidecars.mkdir()
    for name in ("LBF-00042-info.txt", "LBF-00042-check.md5.txt"):
        (sidecars / name).write_bytes(FILES[name])

    overlay_root = tmp_path / "collection" / "TUIT Seeds"
    return read_torrent(torrent), collection, sidecars, overlay_root


class TestPlanOverlay:
    def test_audio_links_and_sidecars_copy(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["t01.flac"].action == LINK
        assert by_name["t02.flac"].action == LINK
        assert by_name["LBF-00042-info.txt"].action == COPY
        assert by_name["LBF-00042-check.md5.txt"].action == COPY
        assert plan.count(FETCH) == 0
        assert "no download needed" in plan.note

    def test_target_dir_is_named_after_the_torrent_root(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        assert plan.target_dir == root / ROOT

    def test_absent_sidecar_becomes_fetch(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").unlink()
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["LBF-00042-info.txt"].action == FETCH
        assert plan.note == ""

    def test_neighbour_of_missing_data_is_copied_not_linked(self, rig):
        # The safety rule: a file sharing a piece with unresolved data must
        # never be hardlinked, or a client write reaches the collection inode.
        info, collection, sidecars, root = rig
        for p in sidecars.iterdir():
            p.unlink()
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["t02.flac"].action == COPY
        assert "shares a piece" in by_name["t02.flac"].reason

    def test_far_from_missing_data_still_links(self, rig):
        info, collection, sidecars, root = rig
        for p in sidecars.iterdir():
            p.unlink()
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["t01.flac"].action == LINK

    def test_wrong_size_sidecar_is_not_used(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").write_bytes(b"rewritten, longer" * 40)
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["LBF-00042-info.txt"].action == FETCH
        assert "torrent wants" in by_name["LBF-00042-info.txt"].reason

    def test_wrong_size_sidecar_becomes_refetch_when_a_url_is_known(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").write_bytes(b"rewritten" * 40)
        plan = plan_overlay(
            info, collection, root, [sidecars],
            {"LBF-00042-info.txt": "http://example.invalid/f.txt"},
        )
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["LBF-00042-info.txt"].action == REFETCH
        assert by_name["LBF-00042-info.txt"].source.startswith("http")

    def test_byte_totals(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        assert plan.link_bytes == 1300 + 1100
        assert plan.copy_bytes == len(FILES["LBF-00042-info.txt"]) + len(
            FILES["LBF-00042-check.md5.txt"])
        assert plan.fetch_bytes == 0


class TestBuildOverlay:
    def test_builds_a_complete_verifiable_overlay(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        result = build_overlay(plan)
        assert result["ok"] is True
        assert result["linked"] == 2
        assert result["copied"] == 2
        assert result["errors"] == []
        assert verify_overlay(info, plan).complete is True

    def test_audio_is_hardlinked_not_duplicated(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        src = collection / "t01.flac"
        dst = plan.target_dir / "t01.flac"
        assert os.stat(src).st_ino == os.stat(dst).st_ino
        assert os.stat(dst).st_nlink == 2

    def test_sidecars_are_real_copies_not_links(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        src = sidecars / "LBF-00042-info.txt"
        dst = plan.target_dir / "LBF-00042-info.txt"
        assert os.stat(src).st_ino != os.stat(dst).st_ino

    def test_collection_is_untouched(self, rig):
        info, collection, sidecars, root = rig
        before = snapshot_folder(collection)
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        assert collection_is_untouched(collection, before) == []

    def test_no_new_files_appear_in_the_collection(self, rig):
        info, collection, sidecars, root = rig
        names_before = sorted(p.name for p in collection.iterdir())
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        assert sorted(p.name for p in collection.iterdir()) == names_before

    def test_fetch_entries_are_skipped_and_leave_no_file(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").unlink()
        plan = plan_overlay(info, collection, root, [sidecars])
        result = build_overlay(plan)
        assert result["skipped"] == 1
        assert not (plan.target_dir / "LBF-00042-info.txt").exists()
        assert verify_overlay(info, plan).complete is False

    def test_dry_run_creates_nothing(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        result = build_overlay(plan, dry_run=True)
        assert result["linked"] == 2
        assert not plan.target_dir.exists()

    def test_rebuild_is_idempotent(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        second = build_overlay(plan)
        assert second["ok"] is True
        assert verify_overlay(info, plan).complete is True

    def test_refetch_uses_the_fetcher_and_completes(self, rig):
        info, collection, sidecars, root = rig
        blob = FILES["LBF-00042-info.txt"]
        (sidecars / "LBF-00042-info.txt").write_bytes(b"rewritten" * 40)
        plan = plan_overlay(
            info, collection, root, [sidecars],
            {"LBF-00042-info.txt": "http://example.invalid/f.txt"},
        )

        def fake_fetch(url, dest):
            dest.write_bytes(blob)
            return len(blob)

        result = build_overlay(plan, fetcher=fake_fetch)
        assert result["refetched"] == 1
        assert verify_overlay(info, plan).complete is True

    def test_refetch_of_the_wrong_size_is_discarded(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").write_bytes(b"rewritten" * 40)
        plan = plan_overlay(
            info, collection, root, [sidecars],
            {"LBF-00042-info.txt": "http://example.invalid/f.txt"},
        )

        def bad_fetch(url, dest):
            dest.write_bytes(b"still wrong")
            return len(b"still wrong")

        result = build_overlay(plan, fetcher=bad_fetch)
        assert result["refetched"] == 0
        assert result["skipped"] == 1
        assert not (plan.target_dir / "LBF-00042-info.txt").exists()
        assert any("torrent wants" in e for e in result["errors"])

    def test_refetch_without_a_fetcher_is_left_to_the_swarm(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").write_bytes(b"rewritten" * 40)
        plan = plan_overlay(
            info, collection, root, [sidecars],
            {"LBF-00042-info.txt": "http://example.invalid/f.txt"},
        )
        result = build_overlay(plan, fetcher=None)
        assert result["skipped"] == 1
        assert result["refetched"] == 0


class TestSourceFolderNamingIsIrrelevant:
    """The overlay is created with the torrent's name and sources by basename,
    so the collection folder may be named anything at all."""

    def test_plans_from_a_differently_named_collection_folder(self, rig, tmp_path):
        info, collection, sidecars, root = rig
        renamed = collection.parent / "1974-01-01 Some Other Naming Scheme"
        collection.rename(renamed)
        plan = plan_overlay(info, renamed, root, [sidecars])
        assert plan.count(FETCH) == 0
        assert plan.count(LINK) == 2

    def test_builds_and_verifies_from_a_differently_named_folder(self, rig):
        info, collection, sidecars, root = rig
        renamed = collection.parent / "Roskilde 29-6-1990-NTB No Torrent LB-13475"
        collection.rename(renamed)
        plan = plan_overlay(info, renamed, root, [sidecars])
        build_overlay(plan)
        # The overlay directory itself must carry the torrent's root name.
        assert plan.target_dir.name == info.name
        assert verify_overlay(info, plan).complete is True

    def test_audio_is_still_hardlinked_from_the_renamed_folder(self, rig):
        info, collection, sidecars, root = rig
        renamed = collection.parent / "totally unrelated name"
        collection.rename(renamed)
        plan = plan_overlay(info, renamed, root, [sidecars])
        build_overlay(plan)
        assert os.stat(renamed / "t01.flac").st_ino == os.stat(
            plan.target_dir / "t01.flac").st_ino


class TestOverlayStatus:
    def test_healthy_overlay_shares_its_audio(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        status = overlay_status(plan.target_dir)
        assert status.exists is True
        assert status.n_files == 4
        assert status.shared_bytes == 1300 + 1100     # the hardlinked audio
        assert status.pinned_bytes > 0                # the copied sidecars
        assert status.orphaned is False

    def test_same_volume_rename_leaves_the_overlay_healthy(self, rig):
        # Hardlinks follow the inode, so renaming the collection folder is a
        # no-op for the overlay — this is why a rename needs no repair.
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        collection.rename(collection.parent / "1974-01-01 Renamed (LB-00042)")
        status = overlay_status(plan.target_dir)
        assert status.orphaned is False
        assert status.shared_bytes == 1300 + 1100
        assert verify_overlay(info, plan).complete is True

    def test_collection_delete_orphans_the_overlay(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        for p in collection.iterdir():
            p.unlink()
        collection.rmdir()
        status = overlay_status(plan.target_dir)
        assert status.orphaned is True
        assert status.shared_bytes == 0
        assert status.pinned_bytes >= 1300 + 1100
        # The data survives — that is exactly why the space is not reclaimed.
        assert verify_overlay(info, plan).complete is True

    def test_cross_volume_move_orphans_the_overlay(self, rig, tmp_path):
        # A cross-device move is copy + rmtree, which is a delete as far as the
        # original inodes are concerned.
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        other_volume = tmp_path / "other" / collection.name
        other_volume.parent.mkdir(parents=True)
        shutil.copytree(collection, other_volume)
        shutil.rmtree(collection)
        assert overlay_status(plan.target_dir).orphaned is True

    def test_missing_overlay_reports_not_exists(self, tmp_path):
        status = overlay_status(tmp_path / "never_built")
        assert status.exists is False
        assert status.orphaned is False
        assert "gone" in status.summary()


class TestSnapshotHelpers:
    def test_detects_a_changed_file(self, tmp_path):
        folder = tmp_path / "f"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"one")
        before = snapshot_folder(folder)
        (folder / "a.txt").write_bytes(b"two!")
        assert collection_is_untouched(folder, before) == ["a.txt"]

    def test_detects_an_added_file(self, tmp_path):
        folder = tmp_path / "f"
        folder.mkdir()
        before = snapshot_folder(folder)
        (folder / "new.txt").write_bytes(b"x")
        assert collection_is_untouched(folder, before) == ["new.txt"]

    def test_detects_a_removed_file(self, tmp_path):
        folder = tmp_path / "f"
        folder.mkdir()
        (folder / "gone.txt").write_bytes(b"x")
        before = snapshot_folder(folder)
        (folder / "gone.txt").unlink()
        assert collection_is_untouched(folder, before) == ["gone.txt"]

    def test_missing_folder_snapshots_empty(self, tmp_path):
        assert snapshot_folder(tmp_path / "nope") == {}
