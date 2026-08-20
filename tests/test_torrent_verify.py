"""Tests for backend.torrent_verify — bencode reading and read-only folder checks.

Torrents are built here from real bytes so the piece hashes are genuine; the
verifier is never handed a hand-waved fixture.
"""
import hashlib

import pytest

from backend.torrent_verify import (
    BencodeError,
    bdecode,
    read_torrent,
    verify_folder,
    verify_torrent_against_folder,
)

PIECE_LEN = 1024


def _bencode(value) -> bytes:
    """Minimal bencoder, used only to build test torrents."""
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return _bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(_bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        out = b"d"
        for key in sorted(value):
            out += _bencode(key) + _bencode(value[key])
        return out + b"e"
    raise TypeError(type(value))


def _pieces_for(blobs: list[bytes], piece_len: int = PIECE_LEN) -> bytes:
    """Return concatenated SHA1 piece hashes over a contiguous byte stream."""
    stream = b"".join(blobs)
    out = b""
    for i in range(0, len(stream), piece_len):
        out += hashlib.sha1(stream[i:i + piece_len]).digest()
    return out


def _make_multi(tmp_path, files: dict[str, bytes], root="Show (LB-00001)"):
    """Write a folder plus a matching multi-file .torrent. Returns (path, folder)."""
    folder = tmp_path / root
    folder.mkdir()
    for name, blob in files.items():
        (folder / name).write_bytes(blob)
    meta = {
        b"info": {
            b"name": root.encode(),
            b"piece length": PIECE_LEN,
            b"pieces": _pieces_for(list(files.values())),
            b"files": [
                {b"path": [name.encode()], b"length": len(blob)}
                for name, blob in files.items()
            ],
        }
    }
    torrent = tmp_path / "t.torrent"
    torrent.write_bytes(_bencode(meta))
    return torrent, folder


@pytest.fixture
def sample(tmp_path):
    """A 3-file torrent spanning several pieces, matching its folder exactly."""
    files = {
        "a.flac": b"A" * 2500,
        "b.flac": b"B" * 1700,
        "info.txt": b"notes\n",
    }
    torrent, folder = _make_multi(tmp_path, files)
    return torrent, folder, files


class TestBdecode:
    def test_integer(self):
        assert bdecode(b"i42e") == 42
        assert bdecode(b"i-7e") == -7

    def test_string_and_list(self):
        assert bdecode(b"4:spam") == b"spam"
        assert bdecode(b"l4:spami3ee") == [b"spam", 3]

    def test_nested_dict(self):
        assert bdecode(b"d3:food3:bari1eee") == {b"foo": {b"bar": 1}}

    def test_empty_containers(self):
        assert bdecode(b"le") == []
        assert bdecode(b"de") == {}

    @pytest.mark.parametrize("raw", [
        b"", b"i42", b"x", b"5:abc", b"d3:fooe", b"l4:spam",
    ])
    def test_malformed_raises(self, raw):
        with pytest.raises(BencodeError):
            bdecode(raw)


class TestReadTorrent:
    def test_multi_file(self, sample):
        torrent, _folder, files = sample
        info = read_torrent(torrent)
        assert info.name == "Show (LB-00001)"
        assert info.piece_length == PIECE_LEN
        assert info.single_file is False
        assert len(info.files) == 3
        assert info.total_size == sum(len(b) for b in files.values())
        assert info.piece_count == len(info.pieces) // 20

    def test_paths_are_prefixed_with_the_root(self, sample):
        info = read_torrent(sample[0])
        assert all(p.startswith("Show (LB-00001)/") for p, _s in info.files)

    def test_single_file(self, tmp_path):
        blob = b"Z" * 3000
        meta = {b"info": {
            b"name": b"solo.flac", b"piece length": PIECE_LEN,
            b"pieces": _pieces_for([blob]), b"length": len(blob),
        }}
        path = tmp_path / "s.torrent"
        path.write_bytes(_bencode(meta))
        info = read_torrent(path)
        assert info.single_file is True
        assert info.files == [("solo.flac", 3000)]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(BencodeError):
            read_torrent(tmp_path / "nope.torrent")

    def test_not_a_torrent_raises(self, tmp_path):
        path = tmp_path / "x.torrent"
        path.write_bytes(b"just some bytes")
        with pytest.raises(BencodeError):
            read_torrent(path)

    def test_info_without_pieces_raises(self, tmp_path):
        path = tmp_path / "x.torrent"
        path.write_bytes(_bencode({b"info": {b"name": b"n", b"piece length": 16}}))
        with pytest.raises(BencodeError):
            read_torrent(path)

    def test_ragged_pieces_blob_raises(self, tmp_path):
        path = tmp_path / "x.torrent"
        path.write_bytes(_bencode({b"info": {
            b"name": b"n", b"piece length": 16, b"pieces": b"short", b"length": 1,
        }}))
        with pytest.raises(BencodeError):
            read_torrent(path)


class TestVerifyFolder:
    def test_complete_folder_passes(self, sample):
        torrent, folder, _files = sample
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is True
        assert result.good_pieces == result.piece_count
        assert result.percent == 100.0
        assert result.missing_files == []
        assert "100%" in result.summary()

    def test_missing_file_fails(self, sample):
        torrent, folder, _files = sample
        (folder / "info.txt").unlink()
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is False
        assert result.missing_files == ["Show (LB-00001)/info.txt"]
        assert result.percent < 100.0

    def test_missing_sidecar_still_blocks_a_near_complete_folder(self, sample):
        # The real LB-00707 case: all audio present, text sidecars absent.
        torrent, folder, _files = sample
        (folder / "info.txt").unlink()
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is False
        assert result.good_pieces >= result.piece_count - 1

    def test_wrong_size_fails(self, sample):
        torrent, folder, _files = sample
        (folder / "b.flac").write_bytes(b"B" * 1699)
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is False
        assert any("b.flac" in m for m in result.size_mismatches)

    def test_corrupted_byte_fails_even_at_the_right_size(self, sample):
        torrent, folder, _files = sample
        blob = bytearray((folder / "a.flac").read_bytes())
        blob[0] ^= 0xFF
        (folder / "a.flac").write_bytes(bytes(blob))
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is False
        assert result.size_mismatches == []      # size is fine, content is not
        assert result.good_pieces < result.piece_count

    def test_folder_name_mismatch_is_refused(self, sample, tmp_path):
        torrent, folder, _files = sample
        renamed = tmp_path / "Different Name"
        folder.rename(renamed)
        result = verify_folder(read_torrent(torrent), renamed)
        assert result.complete is False
        assert "!=" in result.extra_note

    def test_extra_local_files_are_ignored(self, sample):
        torrent, folder, _files = sample
        (folder / "my_notes.txt").write_bytes(b"not in the torrent")
        assert verify_folder(read_torrent(torrent), folder).complete is True

    def test_stop_at_first_bad_returns_early(self, sample):
        torrent, folder, _files = sample
        (folder / "a.flac").write_bytes(b"X" * 2500)
        result = verify_folder(read_torrent(torrent), folder, stop_at_first_bad=True)
        assert result.complete is False

    def test_verification_does_not_modify_the_folder(self, sample):
        torrent, folder, _files = sample
        before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                  for p in folder.iterdir()}
        verify_folder(read_torrent(torrent), folder)
        after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                 for p in folder.iterdir()}
        assert before == after

    def test_verification_creates_no_files_for_an_incomplete_folder(self, sample):
        torrent, folder, _files = sample
        (folder / "info.txt").unlink()
        names_before = sorted(p.name for p in folder.iterdir())
        verify_folder(read_torrent(torrent), folder)
        assert sorted(p.name for p in folder.iterdir()) == names_before

    def test_empty_folder_scores_zero(self, sample, tmp_path):
        torrent, folder, _files = sample
        for p in folder.iterdir():
            p.unlink()
        result = verify_folder(read_torrent(torrent), folder)
        assert result.complete is False
        assert result.good_pieces == 0
        assert result.percent == 0.0


class TestVerifyTorrentAgainstFolder:
    def test_wrapper_happy_path(self, sample):
        torrent, folder, _files = sample
        assert verify_torrent_against_folder(torrent, folder).complete is True

    def test_unreadable_torrent_reports_instead_of_raising(self, tmp_path):
        bad = tmp_path / "bad.torrent"
        bad.write_bytes(b"nope")
        result = verify_torrent_against_folder(bad, tmp_path)
        assert result.complete is False
        assert result.extra_note
