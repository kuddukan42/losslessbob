"""Tests for backend.overlay_rehome (TODO-376).

Most of these assert the collection-safety rules directly: the collection folder
must come out byte-identical whatever happens to the overlay.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from backend import overlay_rehome as rh
from backend import qbittorrent, tracker_seed

PIECE_LEN = 512
ROOT = "Show (LB-00042)"
LB = 42
AUDIO = {"t01.flac": b"\x11" * 1300, "t02.flac": b"\x22" * 1100}
SIDECARS = {"LBF-00042-info.txt": b"info text\n" * 5}
FILES = {**AUDIO, **SIDECARS}
INFOHASH = "ab" * 20


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
        return b"d" + b"".join(_bencode(k) + _bencode(value[k]) for k in sorted(value)) + b"e"
    raise TypeError(type(value))


def _pieces(blob: bytes) -> bytes:
    return b"".join(hashlib.sha1(blob[i:i + PIECE_LEN]).digest()
                    for i in range(0, len(blob), PIECE_LEN))


def _tree_digest(folder: Path) -> dict:
    return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*")) if p.is_file()}


class FakeQbt:
    """Records qBittorrent calls and tracks where the torrent lives."""

    def __init__(self, save_path: Path, take_new: bool = True):
        self.save_path = str(save_path)
        self.present = True
        self.take_new = take_new
        self.calls: list[tuple] = []

    def layout(self, infohash, **_k):
        return {"ok": True, "present": self.present, "save_path": self.save_path,
                "state": "stalledUP", "piece_states": [2] * 5, "files": []}

    def remove(self, infohash, **_k):
        self.calls.append(("remove", infohash))
        self.present = False
        return {"ok": True}

    def seed(self, torrent_path, folder, opts):
        self.calls.append(("seed", folder, opts.tracker, opts.paused))
        if self.take_new or not self.calls[-1][1].startswith(self.new_root):
            self.present = True
            self.save_path = str(Path(folder).parent)
            return {"ok": True}
        return {"ok": False, "error": "refused"}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """Old drive A holds an orphaned overlay; drive B holds the moved collection."""
    import backend.db as db
    import backend.paths as _p

    _p.DATA_DIR = tmp_path
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    orig = db.DB_PATH
    db.DB_PATH = db_path

    torrent = tmp_path / "t.torrent"
    torrent.write_bytes(_bencode({b"info": {
        b"name": ROOT.encode(), b"piece length": PIECE_LEN,
        b"pieces": _pieces(b"".join(FILES.values())),
        b"files": [{b"path": [n.encode()], b"length": len(b)} for n, b in FILES.items()],
    }}))

    drive_a, drive_b = tmp_path / "A", tmp_path / "B"
    overlay = drive_a / "TUIT Seeds" / ROOT
    overlay.mkdir(parents=True)
    for name, data in FILES.items():          # copies: nlink 1, as after a move
        (overlay / name).write_bytes(data)
    collection = drive_b / "Concerts" / "1990" / "1990-01-01 Somewhere (LB-00042)"
    collection.mkdir(parents=True)
    for name, data in AUDIO.items():
        (collection / name).write_bytes(data)
    (collection / "LB-00042.md5").write_bytes(b"checksums\n")

    conn = db.get_connection(db_path)
    conn.execute("INSERT INTO entries(lb_number, status, date_str, location) "
                 "VALUES(?, 'ok', '1990-01-01', 'Somewhere')", (LB,))
    conn.execute("INSERT INTO my_collection(lb_number, folder_name, disk_path) VALUES(?,?,?)",
                 (LB, collection.name, str(collection)))
    conn.execute("INSERT INTO collection_mounts(label, root_path) VALUES('B', ?)",
                 (str(drive_b / "Concerts"),))
    conn.execute("INSERT INTO tuit_downloads(rec_id, lb_number, torrent_path, seed_folder, "
                 "status) VALUES(1, ?, ?, ?, 'qbt_added')", (LB, str(torrent), str(overlay)))
    conn.commit()

    def drive(p):
        return Path(p).resolve().relative_to(tmp_path).parts[0]

    monkeypatch.setattr(rh, "same_volume", lambda a, b: drive(a) == drive(b))
    monkeypatch.setattr(tracker_seed, "overlay_root_for",
                        lambda src, opts: drive_b / opts.overlay_dirname)
    monkeypatch.setattr(tracker_seed, "_free_bytes", lambda _p: None)
    monkeypatch.setattr(tracker_seed, "_qbt_connection", lambda: {})
    monkeypatch.setattr(qbittorrent, "torrent_file_infohash", lambda _p: INFOHASH)

    def forbidden(*_a, **_k):
        raise AssertionError("set_location must never be called")
    monkeypatch.setattr(qbittorrent, "set_location", forbidden)

    qbt = FakeQbt(overlay.parent)
    qbt.new_root = str(drive_b)
    monkeypatch.setattr(qbittorrent, "get_torrent_layout", qbt.layout)
    monkeypatch.setattr(qbittorrent, "remove_torrent", qbt.remove)
    monkeypatch.setattr(tracker_seed, "qbt_seed", qbt.seed)

    yield {"db": db, "overlay": overlay, "collection": collection, "qbt": qbt,
           "new": drive_b / "TUIT Seeds" / ROOT, "tmp": tmp_path}
    db.DB_PATH = orig


def _plan(rig):
    plans = rh.find_candidates([LB])
    assert len(plans) == 1
    return plans[0]


# ── Guard ────────────────────────────────────────────────────────────────────

class TestGuard:
    @pytest.fixture
    def setup(self, tmp_path):
        coll = tmp_path / "D" / "Concerts" / "1990" / "Show"
        coll.mkdir(parents=True)
        seeds = tmp_path / "D" / "TUIT Seeds"
        seeds.mkdir()
        return rh.Protected([coll, tmp_path / "D" / "Concerts"]), coll, seeds

    def test_allows_a_path_below_a_seeds_dir(self, setup):
        prot, _coll, seeds = setup
        assert rh.guard_path(seeds / "X" / "a.flac", prot) == seeds / "X" / "a.flac"

    @pytest.mark.parametrize("make", [
        lambda c, s: c,                              # the collection folder itself
        lambda c, s: c / "t01.flac",                 # inside it
        lambda c, s: c.parent,                       # a parent of it
        lambda c, s: c.parents[1],                   # the mount root
        lambda c, s: s,                              # the Seeds root itself
        lambda c, s: s.parent / "Other" / "x",       # not under a Seeds dir
        lambda c, s: Path(str(s) + "/../Concerts/1990/Show/t01.flac"),  # traversal
        lambda c, s: Path("relative/TUIT Seeds/x"),  # not absolute
    ])
    def test_refuses_forbidden_shapes(self, setup, make):
        prot, coll, seeds = setup
        with pytest.raises(rh.GuardError):
            rh.guard_path(make(coll, seeds), prot)

    def test_refuses_a_symlink_into_the_collection(self, setup):
        prot, coll, seeds = setup
        (coll / "t01.flac").write_bytes(b"x")
        link = seeds / "link.flac"
        link.symlink_to(coll / "t01.flac")
        with pytest.raises(rh.GuardError):
            rh.guard_path(link, prot)

    def test_refuses_a_seeds_dir_symlinked_into_the_collection(self, setup, tmp_path):
        prot, coll, _seeds = setup
        sneaky = tmp_path / "D" / "WTRF Seeds"
        sneaky.symlink_to(coll)
        with pytest.raises(rh.GuardError):
            rh.guard_path(sneaky / "t01.flac", prot)

    def test_refuses_a_seeds_dir_inside_the_collection(self, setup):
        prot, coll, _seeds = setup
        with pytest.raises(rh.GuardError):
            rh.guard_path(coll / "TUIT Seeds" / "x", prot)


# ── Planning ─────────────────────────────────────────────────────────────────

class TestPlan:
    def test_audio_links_and_sidecars_copy(self, rig):
        plan = _plan(rig)
        assert not plan.skip
        assert set(plan.links) == set(AUDIO)
        assert set(plan.copies) == set(SIDECARS)
        assert plan.new_overlay == rig["new"]

    def test_same_drive_is_not_a_candidate(self, rig, monkeypatch):
        monkeypatch.setattr(rh, "same_volume", lambda a, b: True)
        assert rh.find_candidates([LB]) == []

    def test_a_still_linked_overlay_file_is_skipped(self, rig, tmp_path):
        os.link(rig["overlay"] / "t01.flac", tmp_path / "A" / "elsewhere.flac")
        assert "still hardlinked" in _plan(rig).skip

    def test_wtrf_seeds_are_found(self, rig):
        db = rig["db"]
        conn = db.get_connection()
        conn.execute("UPDATE tuit_downloads SET seed_folder='x'")
        wtrf = rig["overlay"].parent.parent / "WTRF Seeds" / ROOT
        rig["overlay"].parent.rename(wtrf.parent)
        conn.execute("INSERT INTO wtrf_downloads(lb_number, torrent_path, seed_folder, status)"
                     " VALUES(?,?,?, 'qbt_added')",
                     (LB, str(rig["tmp"] / "t.torrent"), str(wtrf)))
        conn.commit()
        plan = _plan(rig)
        assert plan.record.tracker == "wtrf" and not plan.skip

    def test_manifest_from_the_filer_is_used(self, rig, tmp_path):
        source = tmp_path / "A" / "Concerts" / "src"
        source.mkdir(parents=True)
        # Rebuild the overlay as hardlinks of a source folder, as before a move.
        for name in AUDIO:
            (rig["overlay"] / name).unlink()
            (source / name).write_bytes(AUDIO[name])
            os.link(source / name, rig["overlay"] / name)
        assert rh.record_pending(LB, source, rig["collection"]) == 1
        row = rig["db"].get_connection().execute(
            "SELECT state, manifest_json FROM overlay_moves").fetchone()
        assert row[0] == "pending"
        assert json.loads(row[1]) == {n: n for n in AUDIO}


# ── Re-homing ────────────────────────────────────────────────────────────────

class TestRehome:
    def test_success(self, rig):
        before = _tree_digest(rig["collection"])
        res = rh.rehome(_plan(rig), rh.load_protected())
        assert res["ok"], res["error"]
        new, coll = rig["new"], rig["collection"]
        for name in AUDIO:
            assert (new / name).stat().st_ino == (coll / name).stat().st_ino
        for name in SIDECARS:
            assert (new / name).read_bytes() == SIDECARS[name]
            assert (new / name).stat().st_nlink == 1
        assert not rig["overlay"].exists()
        assert not (new.parent / rh.BUILD_DIRNAME).exists()
        assert _tree_digest(coll) == before
        assert rig["qbt"].calls[0] == ("remove", INFOHASH)
        assert rig["qbt"].calls[1][1] == str(new)
        seed = rig["db"].get_connection().execute(
            "SELECT seed_folder FROM tuit_downloads").fetchone()[0]
        assert seed == str(new)
        state = rig["db"].get_connection().execute(
            "SELECT state FROM overlay_moves").fetchone()[0]
        assert state == "done"

    def test_a_failed_verify_leaves_everything_as_it_was(self, rig):
        (rig["overlay"] / "LBF-00042-info.txt").write_bytes(b"X" * 50)
        before = _tree_digest(rig["collection"])
        old = _tree_digest(rig["overlay"])
        res = rh.rehome(_plan(rig), rh.load_protected())
        assert not res["ok"] and "does not verify" in res["error"]
        assert _tree_digest(rig["collection"]) == before
        assert _tree_digest(rig["overlay"]) == old
        assert not rig["new"].exists()
        assert not (rig["new"].parent / rh.BUILD_DIRNAME).exists()
        assert rig["qbt"].calls == []

    def test_qbittorrent_refusal_rolls_back(self, rig):
        rig["qbt"].take_new = False
        before = _tree_digest(rig["collection"])
        old = _tree_digest(rig["overlay"])
        res = rh.rehome(_plan(rig), rh.load_protected())
        assert not res["ok"] and "put back on the old overlay" in res["error"]
        assert _tree_digest(rig["overlay"]) == old
        assert _tree_digest(rig["collection"]) == before
        assert not rig["new"].exists()
        assert rig["qbt"].save_path == str(rig["overlay"].parent)

    def test_existing_destination_is_refused(self, rig):
        rig["new"].mkdir(parents=True)
        res = rh.rehome(_plan(rig), rh.load_protected())
        assert not res["ok"] and "already exists" in res["error"]
        assert rig["overlay"].exists()

    def test_collection_change_latches_disabled(self, rig, monkeypatch):
        monkeypatch.setattr(rh, "collection_is_untouched", lambda *_a: ["t01.flac"])
        with pytest.raises(rh.RehomeError):
            rh.rehome(_plan(rig), rh.load_protected())
        assert rig["db"].get_meta(rh.DISABLED_META)
        again = rh.rehome(_plan(rig), rh.load_protected())
        assert not again["ok"] and again["error"].startswith("disabled")

    def test_an_overlay_registered_as_a_collection_folder_is_refused(self, rig):
        conn = rig["db"].get_connection()
        conn.execute("INSERT INTO entries(lb_number, status) VALUES(7, 'ok')")
        conn.execute("INSERT INTO my_collection(lb_number, folder_name, disk_path) "
                     "VALUES(7, 'x', ?)", (str(rig["new"] / "sub"),))
        conn.commit()
        res = rh.rehome(_plan(rig), rh.load_protected())
        assert not res["ok"] and "collection path" in res["error"]


class TestPairedOverlays:
    """A TUIT and a WTRF overlay of the same LB hardlink each other."""

    @pytest.fixture
    def pair(self, rig):
        wtrf = rig["overlay"].parent.parent / "WTRF Seeds" / ROOT
        wtrf.mkdir(parents=True)
        for name in FILES:
            os.link(rig["overlay"] / name, wtrf / name)
        conn = rig["db"].get_connection()
        conn.execute("INSERT INTO wtrf_downloads(lb_number, torrent_path, seed_folder, status)"
                     " VALUES(?,?,?, 'qbt_added')",
                     (LB, str(rig["tmp"] / "t.torrent"), str(wtrf)))
        conn.commit()
        return wtrf

    def test_both_are_planned_as_one_group(self, rig, pair):
        plans = rh.find_candidates([LB])
        assert len(plans) == 2 and not any(p.skip for p in plans)
        assert all(set(p.group) == {rig["overlay"], pair} for p in plans)

    def test_both_rehome_and_both_old_overlays_go(self, rig, pair):
        before = _tree_digest(rig["collection"])
        # One infohash for both: qBittorrent holds a single torrent, moved by
        # whichever overlay goes first; the second leaves it alone.
        protected = rh.load_protected()
        for plan in rh.find_candidates([LB]):
            res = rh.rehome(plan, protected)
            assert res["ok"], res["error"]
            assert res["leftover"] == []
        assert not rig["overlay"].exists() and not pair.exists()
        assert _tree_digest(rig["collection"]) == before
        for name in AUDIO:
            ino = (rig["collection"] / name).stat().st_ino
            assert (rig["new"] / name).stat().st_ino == ino
            assert (rig["new"].parent.parent / "WTRF Seeds" / ROOT / name).stat().st_ino == ino
        assert [c[0] for c in rig["qbt"].calls] == ["remove", "seed"]

    def test_a_link_outside_the_pair_skips_both(self, rig, pair, tmp_path):
        os.link(pair / "t01.flac", tmp_path / "A" / "stray.flac")
        plans = rh.find_candidates([LB])
        assert len(plans) == 2 and all("besides this LB" in p.skip for p in plans)

    def test_group_inodes_counts_fresh(self, rig, pair, tmp_path):
        assert len(rh.group_inodes([rig["overlay"], pair])) == len(FILES)
        os.link(pair / "t01.flac", tmp_path / "A" / "stray.flac")
        assert len(rh.group_inodes([rig["overlay"], pair])) == len(FILES) - 1


class TestRemoveTree:
    def test_refuses_a_file_still_sharing_its_inode(self, tmp_path):
        coll = tmp_path / "Concerts" / "Show"
        coll.mkdir(parents=True)
        (coll / "a.flac").write_bytes(b"audio")
        overlay = tmp_path / "TUIT Seeds" / "Show"
        overlay.mkdir(parents=True)
        os.link(coll / "a.flac", overlay / "a.flac")
        left = rh._remove_tree(overlay, rh.Protected([coll]), allow_shared=False)
        assert left and "links" in left[0]
        assert (coll / "a.flac").read_bytes() == b"audio"
        assert (overlay / "a.flac").exists()

    def test_never_follows_a_symlinked_dir(self, tmp_path):
        coll = tmp_path / "Concerts" / "Show"
        coll.mkdir(parents=True)
        (coll / "a.flac").write_bytes(b"audio")
        overlay = tmp_path / "TUIT Seeds" / "Show"
        overlay.mkdir(parents=True)
        (overlay / "cd1").symlink_to(coll)
        left = rh._remove_tree(overlay, rh.Protected([coll]), allow_shared=True)
        assert left
        assert (coll / "a.flac").read_bytes() == b"audio"


def test_module_never_moves_or_deletes_through_qbittorrent():
    src = Path(rh.__file__).read_text()
    assert "set_location(" not in src and "/setLocation" not in src
    assert "deleteFiles\": \"true" not in src and "torrents/delete" not in src
    assert "rmtree(" not in src
