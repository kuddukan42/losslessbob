"""Tests for backend.seed_overlay — assembling a seedable copy safely.

The central promise is that the source collection folder is never written to,
so several tests assert that explicitly rather than only checking the overlay.
"""
import hashlib
import logging
import os
import shutil
from pathlib import Path

import pytest

from backend import tracker_seed
from backend.seed_overlay import (
    COPY,
    FETCH,
    LINK,
    REFETCH,
    bad_pieces,
    build_overlay,
    choose_source_folder,
    collection_is_untouched,
    overlay_status,
    plan_overlay,
    repair_overlay,
    resolvable_files,
    snapshot_folder,
    unique_overlay_name,
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

    def test_overlay_name_overrides_the_torrent_root(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars],
                            overlay_name=f"{ROOT} (LB-00042)")
        assert plan.target_dir == root / f"{ROOT} (LB-00042)"

    def test_absent_sidecar_becomes_fetch(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").unlink()
        plan = plan_overlay(info, collection, root, [sidecars])
        by_name = {e.rel_path.split("/")[-1]: e for e in plan.entries}
        assert by_name["LBF-00042-info.txt"].action == FETCH
        assert plan.note == ""

    def test_sidecar_renamed_by_the_site_is_still_found(self, rig):
        """The mirror holds the file under the LBF name; the torrent wants the
        taper's. Same bytes, and an old post's swarm cannot supply them."""
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").rename(
            sidecars / "LBF-00099-Some-Show-d1-info.txt")

        plan = plan_overlay(info, collection, root, [sidecars])
        entry = {e.rel_path.split("/")[-1]: e for e in plan.entries}["LBF-00042-info.txt"]

        assert entry.action == COPY
        assert "renamed copy" in entry.reason
        assert plan.count(FETCH) == 0

    def test_renamed_sidecar_of_the_wrong_size_is_refused(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00042-info.txt").rename(sidecars / "info-renamed.txt")
        (sidecars / "info-renamed.txt").write_bytes(b"different length entirely")

        plan = plan_overlay(info, collection, root, [sidecars])
        entry = {e.rel_path.split("/")[-1]: e for e in plan.entries}["LBF-00042-info.txt"]

        assert entry.action == FETCH

    def test_exact_name_still_wins_over_a_renamed_candidate(self, rig):
        info, collection, sidecars, root = rig
        (sidecars / "LBF-00099-copy-of-info.txt").write_bytes(
            FILES["LBF-00042-info.txt"])

        plan = plan_overlay(info, collection, root, [sidecars])
        entry = {e.rel_path.split("/")[-1]: e for e in plan.entries}["LBF-00042-info.txt"]

        assert entry.source.endswith("LBF-00042-info.txt")
        assert entry.reason == "sidecar store"

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


# ── Nested torrents: box sets spanning subfolders and several LB entries ─────
# Real WTRF torrents are not flat. "Bob Dylan 84 Revisited LB-14777+ LB-14778"
# nests <root>/artwork/ and <root>/<show>/cd-1|cd-2/, covers two catalogue
# entries filed in separate collection folders, and repeats basenames across
# its discs ("01 Track01.flac" appears four times). A flat, basename-keyed
# index found none of the audio and could not have told those copies apart.

NESTED = {
    "artwork/scan01.jpg": b"\xff\xd8" + b"\x01" * 500,
    "Rome 1984/cd-1/01 Track01.flac": b"\xa1" * 900,
    "Rome 1984/cd-2/01 Track01.flac": b"\xa2" * 800,
    "London 1984/cd-1/01 Track01.flac": b"\xb1" * 700,
    "London 1984/cd-2/01 Track01.flac": b"\xb2" * 600,
}


@pytest.fixture
def nested_rig(tmp_path):
    """A two-show torrent vs two collection folders, each nested cd-1/cd-2."""
    torrent_meta = {b"info": {
        b"name": b"Box Set",
        b"piece length": PIECE_LEN,
        b"pieces": _pieces(list(NESTED.values())),
        b"files": [{b"path": [p.encode() for p in n.split("/")], b"length": len(b)}
                   for n, b in NESTED.items()],
    }}
    torrent = tmp_path / "box.torrent"
    torrent.write_bytes(_bencode(torrent_meta))

    rome = tmp_path / "collection" / "1984-06-19 Rome (LB-14777)"
    london = tmp_path / "collection" / "1984-07-07 London (LB-14778)"
    for folder, prefix in ((rome, "Rome 1984"), (london, "London 1984")):
        for disc in ("cd-1", "cd-2"):
            (folder / disc).mkdir(parents=True)
            key = f"{prefix}/{disc}/01 Track01.flac"
            (folder / disc / "01 Track01.flac").write_bytes(NESTED[key])
    (rome / "artwork").mkdir()
    (rome / "artwork" / "scan01.jpg").write_bytes(NESTED["artwork/scan01.jpg"])

    return read_torrent(torrent), rome, london, tmp_path / "WTRF Seeds"


class TestNestedTorrents:
    def test_audio_below_the_top_level_is_found(self, nested_rig):
        """The whole point: a recursive index sees cd-1/cd-2, a flat one did not."""
        info, rome, london, root = nested_rig
        plan = plan_overlay(info, rome, root, [], None, link_dirs=[str(london)])
        assert plan.count(FETCH) == 0
        assert plan.count(LINK) == len(NESTED)

    def test_colliding_basenames_resolve_to_the_right_disc(self, nested_rig):
        """Four files are named "01 Track01.flac"; each must get its own bytes."""
        info, rome, london, root = nested_rig
        plan = plan_overlay(info, rome, root, [], None, link_dirs=[str(london)])
        sources = {e.rel_path: Path(e.source) for e in plan.entries}
        for rel, blob in NESTED.items():
            picked = sources[f"Box Set/{rel}"]
            assert picked.read_bytes() == blob, f"{rel} sourced from {picked}"

    def test_a_sibling_folder_supplies_its_own_half(self, nested_rig):
        info, rome, london, root = nested_rig
        plan = plan_overlay(info, rome, root, [], None, link_dirs=[str(london)])
        from_london = [e for e in plan.entries
                       if Path(e.source).is_relative_to(london)]
        assert len(from_london) == 2          # London's two discs
        assert all(e.action == LINK for e in from_london)

    def test_without_the_sibling_its_files_are_left_to_the_swarm(self, nested_rig):
        """No silent wrong-file substitution when a half is missing."""
        info, rome, london, root = nested_rig
        plan = plan_overlay(info, rome, root)
        fetched = {e.rel_path for e in plan.entries if e.action == FETCH}
        assert fetched == {"Box Set/London 1984/cd-1/01 Track01.flac",
                           "Box Set/London 1984/cd-2/01 Track01.flac"}

    def test_the_nested_overlay_builds_and_verifies(self, nested_rig):
        info, rome, london, root = nested_rig
        plan = plan_overlay(info, rome, root, [], None, link_dirs=[str(london)])
        before_rome, before_london = snapshot_folder(rome), snapshot_folder(london)
        build_overlay(plan)
        assert verify_overlay(info, plan).complete
        assert collection_is_untouched(rome, before_rome) == []
        assert collection_is_untouched(london, before_london) == []

    def test_resolvable_files_scores_nested_folders(self, nested_rig):
        info, rome, london, _root = nested_rig
        assert resolvable_files(info, [str(rome)]) == 3      # artwork + 2 discs
        assert resolvable_files(info, [str(london)]) == 2
        assert resolvable_files(info, [str(rome), str(london)]) == len(NESTED)


class TestSnapshotIsRecursive:
    def test_a_write_below_the_root_is_caught(self, nested_rig):
        """A nested collection folder must not hide a write from the guard."""
        _info, rome, _london, _root = nested_rig
        before = snapshot_folder(rome)
        (rome / "cd-1" / "01 Track01.flac").write_bytes(b"\x00" * 900)
        assert collection_is_untouched(rome, before) == ["cd-1/01 Track01.flac"]

    def test_a_new_nested_file_is_caught(self, nested_rig):
        _info, rome, _london, _root = nested_rig
        before = snapshot_folder(rome)
        (rome / "cd-2" / "intruder.flac").write_bytes(b"x")
        assert collection_is_untouched(rome, before) == ["cd-2/intruder.flac"]


class TestUniqueOverlayName:
    """Torrent root names recur on a tracker; two LB entries must not share one."""

    def test_free_directory_keeps_the_torrent_name(self, tmp_path):
        assert unique_overlay_name(tmp_path, "track", 12242) == "track"

    def test_no_lb_number_keeps_the_torrent_name(self, tmp_path):
        (tmp_path / "track").mkdir()
        assert unique_overlay_name(tmp_path, "track", None) == "track"

    def test_own_overlay_is_reused_not_renamed(self, tmp_path, monkeypatch):
        (tmp_path / "track").mkdir()
        monkeypatch.setattr(
            "backend.seed_overlay.lbs_for_seed_folder", lambda *a, **k: {12242}
        )
        assert unique_overlay_name(tmp_path, "track", 12242) == "track"

    def test_unrecorded_overlay_is_reused(self, tmp_path, monkeypatch):
        """A hand-made or pre-bookkeeping overlay must not be duplicated."""
        (tmp_path / "track").mkdir()
        monkeypatch.setattr(
            "backend.seed_overlay.lbs_for_seed_folder", lambda *a, **k: set()
        )
        assert unique_overlay_name(tmp_path, "track", 12242) == "track"

    def test_another_lbs_overlay_is_disambiguated(self, tmp_path, monkeypatch):
        (tmp_path / "track").mkdir()
        monkeypatch.setattr(
            "backend.seed_overlay.lbs_for_seed_folder", lambda *a, **k: {12243}
        )
        assert unique_overlay_name(tmp_path, "track", 12242) == "track (LB-12242)"

    def test_lookup_failure_falls_back_to_the_torrent_name(self, tmp_path, monkeypatch):
        (tmp_path / "track").mkdir()

        def boom(*a, **k):
            raise RuntimeError("no db")

        monkeypatch.setattr("backend.seed_overlay.lbs_for_seed_folder", boom)
        assert unique_overlay_name(tmp_path, "track", 12242) == "track"


# ── the private-status gate ──────────────────────────────────────────────────

def test_private_lb_is_refused_by_default(monkeypatch, tmp_path):
    """A private recording never leaves the collection on a default policy."""
    from backend import tracker_seed
    monkeypatch.setattr(tracker_seed.database, "is_seedable_to_tracker",
                        lambda _lb: (False, "lb_private"))

    folder, reason = tracker_seed.find_seedable_folder(
        4154, str(tmp_path / "x.torrent"), tracker_seed.SeedOptions("tuit"))

    assert folder is None
    assert "lb_private" in reason


def test_private_lb_passes_when_the_post_already_exists(monkeypatch, tmp_path):
    """allow_private (the WTRF paths) gets past 'private', nothing else."""
    from backend import tracker_seed
    monkeypatch.setattr(tracker_seed.database, "is_seedable_to_tracker",
                        lambda _lb: (False, "lb_private"))
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_lb",
                        lambda _lb: [])
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_same_date",
                        lambda _lb: {})

    opts = tracker_seed.SeedOptions("wtrf", allow_private=True)
    folder, reason = tracker_seed.find_seedable_folder(
        4154, str(tmp_path / "x.torrent"), opts)

    # Past the status gate — it fails at the next one instead.
    assert folder is None
    assert "no collection folder" in reason


def test_allow_private_does_not_excuse_a_missing_lb(monkeypatch, tmp_path):
    from backend import tracker_seed
    monkeypatch.setattr(tracker_seed.database, "is_seedable_to_tracker",
                        lambda _lb: (False, "lb_missing"))

    opts = tracker_seed.SeedOptions("wtrf", allow_private=True)
    folder, reason = tracker_seed.find_seedable_folder(
        4154, str(tmp_path / "x.torrent"), opts)

    assert folder is None
    assert "lb_missing" in reason


# ── TODO-348: a wrong LB attribution is rescued by same-date siblings ────────

def _patch_seed_db(monkeypatch, tracker_seed, claimed, siblings):
    monkeypatch.setattr(tracker_seed.database, "is_seedable_to_tracker",
                        lambda _lb: (True, "ok"))
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_lb",
                        lambda _lb: list(claimed))
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_same_date",
                        lambda _lb: dict(siblings))


def test_wrong_lb_attribution_is_rescued_by_a_same_date_folder(
    monkeypatch, rig, tmp_path
):
    """The tracker names LB-11813 but the audio is LB-11801's (TODO-348):
    the sibling folder must be a candidate and win on content."""
    from backend import tracker_seed
    info, collection, sidecars, root = rig
    # The claimed LB's folder exists but holds a different recording.
    claimed = tmp_path / "claimed" / ROOT
    claimed.mkdir(parents=True)
    (claimed / "t01.flac").write_bytes(b"not the same audio at all" * 40)
    _patch_seed_db(monkeypatch, tracker_seed, [str(claimed)],
                   {11801: [str(collection)]})
    details: dict = {}
    opts = tracker_seed.SeedOptions("tuit", overlay=True, overlay_root=str(root),
                                    refetch_sidecars=False)
    monkeypatch.setattr(tracker_seed, "SIDECAR_DIR", str(sidecars))

    folder, reason = tracker_seed.find_seedable_folder(
        11813, str(tmp_path / "t.torrent"), opts, details=details)

    assert details.get("source_lb") == 11801
    assert folder is not None and folder.startswith(str(root))
    assert "content matches LB-11801" in reason


def test_same_date_pool_is_not_consulted_without_the_overlay(
    monkeypatch, rig, tmp_path
):
    from backend import tracker_seed
    info, collection, sidecars, root = rig
    called = []
    monkeypatch.setattr(tracker_seed.database, "is_seedable_to_tracker",
                        lambda _lb: (True, "ok"))
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_lb",
                        lambda _lb: [])
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_same_date",
                        lambda _lb: called.append(_lb) or {11801: [str(collection)]})

    folder, reason = tracker_seed.find_seedable_folder(
        11813, str(tmp_path / "t.torrent"),
        tracker_seed.SeedOptions("tuit", overlay=False))

    assert folder is None
    assert "no collection folder" in reason
    assert called == []


def test_same_date_lookup_errors_narrow_to_the_claimed_lb(monkeypatch):
    import sqlite3

    from backend import tracker_seed

    def boom(_lb):
        raise sqlite3.OperationalError("no such table")
    monkeypatch.setattr(tracker_seed.database, "get_folders_for_same_date", boom)
    assert tracker_seed.same_date_folders(1) == {}


# ── alias keys: the LB site's renaming conventions ───────────────────────────

@pytest.mark.parametrize("site_name, taper_name", [
    # The site prefixes every sidecar it publishes with LBF-<lb>-.
    ("LBF-03323-bd00-07-19a-LB-3323.txt", "bd00-07-19a-LB-3323.txt"),
    # …swaps the format marker: .txt.md5 on disk for the torrent's .shnf.md5.
    ("LBF-03323-lbdir-bd00-07-19a.txt.md5", "lbdir-bd00-07-19a.shnf.md5"),
    # …and appends .txt to anything that is not already text.
    ("LBF-00001-bd87-05d1.md5.txt", "bd87-05d1.md5"),
])
def test_alias_keys_match_across_the_sites_renaming(site_name, taper_name):
    from backend.seed_overlay import _alias_keys
    assert _alias_keys(site_name) & _alias_keys(taper_name)


def test_alias_keys_keep_distinct_sidecars_apart():
    from backend.seed_overlay import _alias_keys
    assert not (_alias_keys("LBF-03323-noname.md5.txt")
                & _alias_keys("bd00-07-19a.md5"))


def test_alias_resolution_folds_the_folder_into_the_name(tmp_path):
    """The site flattens <folder>/<file> into one name; a suffix match finds it."""
    from backend.seed_overlay import _alias_candidates, _index_aliases, _index_sources
    store = tmp_path / "files"
    store.mkdir()
    published = store / "LBF-02614-BD---Toads-Place-d5-bd1990-1-12-d5-Toads-LTE.txt"
    published.write_bytes(b"x" * 1875)

    aliases = _index_aliases(_index_sources([store]))
    hits = _alias_candidates(
        aliases, "Bd 1990 LB 2614/Bob Dylan - Toads Place d5/bd1990-1-12-d5-Toads-LTE.txt",
        1875)

    assert hits == [published]
    assert _alias_candidates(aliases, "x/bd1990-1-12-d5-Toads-LTE.txt", 999) == []


# ──────────────────────────────────────────────────────────────────────────────
# TODO-337 — a size match is not a content match
# ──────────────────────────────────────────────────────────────────────────────
#: The torrent entry the two collection folders disagree about. 43 bytes, and
#: it shares its piece with the tail of t02.flac — the shape that left 29 TUIT
#: seeds one 512 KiB piece short.
_AMBIGUOUS = "LBF-00042-check.md5.txt"


@pytest.fixture
def ambiguous_rig(rig):
    """Two collection folders holding same-size, different-bytes sidecars.

    The *wrong* copy sits in the preferred folder, so taking the first
    size match picks it and the covering piece never completes.
    """
    info, collection, sidecars, root = rig
    wrong = collection / _AMBIGUOUS
    wrong.write_bytes(b"W" * len(FILES[_AMBIGUOUS]))

    sibling = collection.parent / "Same show, other LB"
    sibling.mkdir()
    right = sibling / _AMBIGUOUS
    right.write_bytes(FILES[_AMBIGUOUS])

    # The sidecar store keeps only the other sidecar, so the ambiguity is
    # decided between the two collection copies alone.
    (sidecars / _AMBIGUOUS).unlink()
    return info, collection, sidecars, root, sibling, wrong, right


class TestSizeAmbiguity:
    def test_piece_hashes_decide_between_same_size_candidates(self, ambiguous_rig):
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        entry = next(e for e in plan.entries if e.rel_path.endswith(_AMBIGUOUS))

        assert entry.source == str(right), "the wrong same-size copy was kept"
        build_overlay(plan)
        assert verify_overlay(info, plan).complete is True

    def test_the_ambiguity_is_recorded_on_the_plan(self, ambiguous_rig):
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        idx = next(i for i, (p, _s) in enumerate(info.files)
                   if p.endswith(_AMBIGUOUS))
        assert plan.candidates[idx] == [wrong, right]

    def test_an_unambiguous_file_records_no_candidates(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        assert plan.candidates == {}

    def test_undecidable_ambiguity_keeps_the_first_and_says_so(self, ambiguous_rig):
        """With a neighbour in the piece left to the swarm, nothing can be
        hashed — the pick stands, but the plan admits it is a guess."""
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        (sidecars / "LBF-00042-info.txt").unlink()
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        entry = next(e for e in plan.entries if e.rel_path.endswith(_AMBIGUOUS))
        assert entry.source == str(wrong)
        assert "none verified" in entry.note

    def test_the_collection_is_never_written_to(self, ambiguous_rig):
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        before = snapshot_folder(collection)
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        build_overlay(plan)
        assert collection_is_untouched(collection, before) == []


class TestRepairOverlay:
    def _wrongly_built(self, ambiguous_rig):
        """Build an overlay that picked the wrong same-size file."""
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        entry = next(e for e in plan.entries if e.rel_path.endswith(_AMBIGUOUS))
        entry.source = str(wrong)      # undo the piece-hash pick
        build_overlay(plan)
        return info, plan, entry, right

    def test_a_short_overlay_is_repaired_from_the_failing_piece(
        self, ambiguous_rig
    ):
        info, plan, entry, right = self._wrongly_built(ambiguous_rig)
        assert verify_overlay(info, plan).complete is False

        repair = repair_overlay(info, plan)
        assert repair["bad_pieces"] == 1
        assert repair["repaired"] == [entry.rel_path]
        assert repair["ok"] is True
        assert entry.source == str(right)
        assert verify_overlay(info, plan).complete is True

    def test_a_complete_overlay_is_left_alone(self, rig):
        info, collection, sidecars, root = rig
        plan = plan_overlay(info, collection, root, [sidecars])
        build_overlay(plan)
        repair = repair_overlay(info, plan)
        assert repair == {"ok": False, "repaired": [], "bad_pieces": 0,
                          "errors": [], "verify": None}

    def test_a_genuine_shortfall_is_not_a_bad_pick(self, ambiguous_rig):
        """A piece missing bytes is unknown, not wrong — repair must not
        report it and must not touch the overlay."""
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        (sidecars / "LBF-00042-info.txt").unlink()
        plan = plan_overlay(info, collection, root, [sidecars],
                            link_dirs=[str(sibling)])
        build_overlay(plan)
        repair = repair_overlay(info, plan)
        assert repair["bad_pieces"] == 0
        assert repair["repaired"] == []

    def test_bad_pieces_counts_only_locally_complete_mismatches(
        self, ambiguous_rig
    ):
        info, plan, entry, right = self._wrongly_built(ambiguous_rig)
        assert bad_pieces(info, plan.target_dir) == [4]

    def test_repair_never_writes_to_the_collection(self, ambiguous_rig):
        info, collection = ambiguous_rig[0], ambiguous_rig[1]
        before = snapshot_folder(collection)
        info, plan, entry, right = self._wrongly_built(ambiguous_rig)
        repair_overlay(info, plan)
        assert collection_is_untouched(collection, before) == []


class TestChooseSourceFolder:
    def test_content_beats_the_trackers_naming(self, rig):
        """The tracker's LB attribution was wrong twice on 2026-09-06, so the
        folder named after the torrent root wins only on a tie."""
        info, collection, sidecars, root = rig
        thin = collection.parent / "thin"
        thin.mkdir()
        (thin / "t01.flac").write_bytes(FILES["t01.flac"])

        # `collection` is the ROOT-named folder and resolves both flacs.
        assert choose_source_folder(info, [thin, collection], [collection]) == \
            str(collection)
        # Now the named folder is the thin one and loses on content.
        assert choose_source_folder(info, [thin, collection], [thin]) == \
            str(collection)

    def test_a_tie_goes_to_the_named_folder(self, rig):
        info, collection, sidecars, root = rig
        twin = collection.parent / "twin"
        twin.mkdir()
        for name in ("t01.flac", "t02.flac"):
            (twin / name).write_bytes(FILES[name])
        assert choose_source_folder(info, [twin, collection], [collection]) == \
            str(collection)

    def test_no_folder_supplies_anything(self, rig, tmp_path):
        info, collection, sidecars, root = rig
        empty = tmp_path / "empty"
        empty.mkdir()
        assert choose_source_folder(info, [empty], [empty]) is None


class TestUndecidableAmbiguityIsLoud:
    def test_it_warns_the_operator(self, ambiguous_rig, caplog):
        """A pick that could not be settled is a coin toss on a seed that will
        never complete, so it must not pass in silence."""
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        (sidecars / "LBF-00042-info.txt").unlink()
        with caplog.at_level(logging.WARNING, logger="backend.seed_overlay"):
            plan_overlay(info, collection, root, [sidecars],
                         link_dirs=[str(sibling)])
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "may be the wrong copy" in warnings[0].getMessage()

    def test_a_settled_pick_does_not_warn(self, ambiguous_rig, caplog):
        info, collection, sidecars, root, sibling, wrong, right = ambiguous_rig
        with caplog.at_level(logging.WARNING, logger="backend.seed_overlay"):
            plan_overlay(info, collection, root, [sidecars],
                         link_dirs=[str(sibling)])
        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


class _FakeQbt:
    """Stand-in for backend.qbittorrent, recording what it was asked to do."""

    def __init__(self, infohash="ABCDEF0123456789", ok=True):
        self.infohash = infohash
        self.ok = ok
        self.searched: list[str] = []
        self.rechecked: list[str] = []

    def find_torrent_by_path(self, folder, **kwargs):
        self.searched.append(str(folder))
        return {"ok": True, "infohash": self.infohash, "root_name": "x",
                "error": None}

    def recheck_torrent(self, infohash, **kwargs):
        self.rechecked.append(infohash)
        return {"ok": self.ok, "error": "" if self.ok else "HTTP 403"}


@pytest.fixture
def fake_qbt(monkeypatch):
    """Replace tracker_seed's qBittorrent client and its credential lookup."""
    fake = _FakeQbt()
    monkeypatch.setattr(tracker_seed, "qbittorrent", fake)
    monkeypatch.setattr(tracker_seed, "_qbt_connection", lambda: {
        "host": "localhost", "port": 8080, "username": "u", "password": "p",
        "api_key": "",
    })
    return fake


class TestRecheckAfterRepair:
    def test_a_repaired_and_already_present_torrent_is_rechecked(self, fake_qbt):
        details = {"repaired": ["Show/LBF-00042-check.md5.txt"]}
        assert tracker_seed.recheck_repaired_seed(
            "/mnt/X/TUIT Seeds/Show", details, {"ok": True,
                                                "already_present": True}
        ) is True
        assert fake_qbt.searched == ["/mnt/X/TUIT Seeds/Show"]
        assert fake_qbt.rechecked == ["ABCDEF0123456789"]

    def test_nothing_repaired_means_no_recheck(self, fake_qbt):
        assert tracker_seed.recheck_repaired_seed(
            "/mnt/X/TUIT Seeds/Show", {"repaired": []},
            {"ok": True, "already_present": True}
        ) is False
        assert fake_qbt.rechecked == []

    def test_a_freshly_added_torrent_needs_no_recheck(self, fake_qbt):
        """qBittorrent hashes a torrent as it is added, so it already sees the
        repaired files."""
        assert tracker_seed.recheck_repaired_seed(
            "/mnt/X/TUIT Seeds/Show", {"repaired": ["a"]}, {"ok": True}
        ) is False
        assert fake_qbt.searched == []

    def test_missing_details_is_tolerated(self, fake_qbt):
        assert tracker_seed.recheck_repaired_seed(
            "/mnt/X/TUIT Seeds/Show", None, {"ok": True,
                                             "already_present": True}
        ) is False

    def test_a_refused_recheck_warns_loudly(self, fake_qbt, caplog):
        fake_qbt.ok = False
        with caplog.at_level(logging.WARNING, logger="backend.tracker_seed"):
            assert tracker_seed.recheck_repaired_seed(
                "/mnt/X/TUIT Seeds/Show", {"repaired": ["Show/x.md5"]},
                {"ok": True, "already_present": True}
            ) is False
        assert any("recheck FAILED" in r.getMessage() for r in caplog.records)

    def test_an_unfindable_torrent_is_reported_not_rechecked(self, fake_qbt):
        fake_qbt.infohash = ""
        outcome = tracker_seed.recheck_seed("/mnt/X/TUIT Seeds/Show")
        assert outcome["ok"] is False
        assert "nothing to recheck" in outcome["error"]
        assert fake_qbt.rechecked == []
