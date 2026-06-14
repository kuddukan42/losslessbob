"""Tests for ingest.list_tracks's directory-vs-file filter.

Regression for the 1987-10-05 crash: a top-level source folder contained a
*subdirectory* named "1987-10-05locarno+asm.flac" (holding the real per-track
.flac files). Path.rglob("*") + suffix matching picked up that directory
itself as a "track" because its name ends in ".flac", and
audio.duration_sec() then crashed with LibsndfileError("Format not
recognised") trying to read it as an audio file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import ingest  # noqa: E402


def test_directory_named_like_audio_file_is_excluded(tmp_path):
    source = tmp_path / "1987-10-05 Locarno (LB-10681)"
    source.mkdir()

    # A subdirectory whose *name* ends in ".flac" — must not be treated as a track.
    fake_dir = source / "1987-10-05locarno+asm.flac"
    fake_dir.mkdir()
    (fake_dir / "101 Rainy Day Women.flac").write_bytes(b"fake-flac-data")
    (fake_dir / "102 Like A Rolling Stone.flac").write_bytes(b"fake-flac-data")

    tracks = ingest.list_tracks(source, {".flac"})

    assert fake_dir not in tracks
    assert all(p.is_file() for p in tracks)
    assert {p.name for p in tracks} == {
        "101 Rainy Day Women.flac",
        "102 Like A Rolling Stone.flac",
    }


def test_normal_flat_folder_unaffected(tmp_path):
    source = tmp_path / "normal (LB-00001)"
    source.mkdir()
    (source / "01 Track.flac").write_bytes(b"fake-flac-data")
    (source / "02 Track.flac").write_bytes(b"fake-flac-data")

    tracks = ingest.list_tracks(source, {".flac"})

    assert {p.name for p in tracks} == {"01 Track.flac", "02 Track.flac"}
