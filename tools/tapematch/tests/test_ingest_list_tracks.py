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


def test_dual_format_folder_keeps_one_copy_per_track(tmp_path):
    """BUG-326: LB-10250's shape — 17 .wav + 17 .flac with identical basenames.

    Both extensions are in config audio_exts, so every track matched twice and
    _natural_key sorted each .flac immediately before its .wav, making the
    concatenated stream repeat every track back to back.
    """
    source = tmp_path / "2012-07-03 Dresden (LB-10250)"
    source.mkdir()
    for i in range(1, 18):
        (source / f"Dylan_2012_07_03_Dresden_TM_{i:02d}.flac").write_bytes(b"flac")
        (source / f"Dylan_2012_07_03_Dresden_TM_{i:02d}.wav").write_bytes(b"wavdata")

    tracks = ingest.list_tracks(source, {".flac", ".wav"})

    assert len(tracks) == 17
    assert all(p.suffix == ".flac" for p in tracks), "lossless copy must win"
    # Concert order preserved, and no track repeated.
    assert [p.stem[-2:] for p in tracks] == [f"{i:02d}" for i in range(1, 18)]


def test_format_preference_falls_back_when_lossless_absent(tmp_path):
    source = tmp_path / "lossy only (LB-00002)"
    source.mkdir()
    (source / "01 Track.mp3").write_bytes(b"mp3")
    (source / "02 Track.wav").write_bytes(b"wav")

    tracks = ingest.list_tracks(source, {".flac", ".wav", ".mp3"})

    assert {p.name for p in tracks} == {"01 Track.mp3", "02 Track.wav"}


def test_duplicated_subtree_is_dropped(tmp_path):
    """BUG-326: LB-03685's shape — 'CD 1'..'CD 4' duplicating 'D1'..'D4'."""
    source = tmp_path / "1975-12-01 Toronto (LB-03685)"
    source.mkdir()
    for n in range(1, 5):
        # Each disc holds different audio; CD n and D n are byte-identical copies
        # of each other, which is exactly LB-03685's on-disk shape.
        for label in (f"CD {n}", f"D{n}"):
            sub = source / label
            sub.mkdir()
            for t in range(1, 4):
                (sub / f"TRACK{t:02d}.FLAC").write_bytes(b"x" * (100 * n + t))

    tracks = ingest.list_tracks(source, {".flac"})

    assert len(tracks) == 12, "one of each duplicated CD/D pair should survive"
    kept_dirs = {p.parent.name for p in tracks}
    assert kept_dirs == {"CD 1", "CD 2", "CD 3", "CD 4"}


def test_distinct_subtrees_are_both_kept(tmp_path):
    """A real multi-disc show must not be mistaken for a duplicated subtree."""
    source = tmp_path / "real two-disc (LB-00003)"
    source.mkdir()
    for n, sizes in ((1, (10, 20, 30)), (2, (40, 50, 60))):
        sub = source / f"D{n}"
        sub.mkdir()
        for t, size in enumerate(sizes, start=1):
            (sub / f"TRACK{t:02d}.FLAC").write_bytes(b"x" * size)

    tracks = ingest.list_tracks(source, {".flac"})

    assert len(tracks) == 6
    assert {p.parent.name for p in tracks} == {"D1", "D2"}


def test_fix_sibling_directory_replaces_matching_tracks(tmp_path):
    """BUG-335: LB-07173's shape — d1/fix + a top-level *d1.fix sibling.

    The release (d1/d2, 11 tracks) is nested a level deeper here to mirror the
    real folder ('...REMASTERED)_fixed/d1', '.../d1/fix', plus a top-level
    'bd1993-08-28d1.fix' sibling of that folder) but the shape that matters is
    the same: small sibling directories of '.fix' tracks whose names match
    tracks already present, which must replace — not inflate — the count.
    """
    source = tmp_path / "bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed"
    source.mkdir()
    d1 = source / "d1"
    d1.mkdir()
    for t in range(1, 9):
        (d1 / f"Track{t:02d}.flac").write_bytes(b"orig" * t)
    d2 = source / "d2"
    d2.mkdir()
    for t in range(1, 4):
        (d2 / f"Track{t:02d}.flac").write_bytes(b"origd2" * t)

    # Nested fix sibling: replaces d1/Track08.
    nested_fix = d1 / "fix"
    nested_fix.mkdir()
    (nested_fix / "Track08.fix.flac").write_bytes(b"fixed-08")

    # Top-level fix sibling: replaces d1/Track09... but there is no Track09,
    # so mirror the bug report with a second genuinely-replaced track instead.
    top_fix = source / "bd1993-08-28d1.fix"
    top_fix.mkdir()
    (top_fix / "Track07.fix.flac").write_bytes(b"fixed-07")

    tracks = ingest.list_tracks(source, {".flac"})

    assert len(tracks) == 11, "fix siblings must replace, not add, tracks"
    names = {p.name for p in tracks}
    assert "Track08.fix.flac" in names
    assert "Track07.fix.flac" in names
    assert "Track08.flac" not in names
    assert "Track07.flac" not in names
    # Concert order preserved: the fix track sits where Track07 used to.
    stems = [p.stem.split(".")[0] for p in tracks if p.parent != d2]
    assert stems == [f"Track{t:02d}" for t in range(1, 9)]


def test_fix_marker_without_unique_match_is_left_alone(tmp_path):
    """A marked directory that doesn't uniquely match an outside track is kept as-is."""
    source = tmp_path / "ambiguous (LB-00004)"
    source.mkdir()
    d1 = source / "D1"
    d1.mkdir()
    (d1 / "Track01.flac").write_bytes(b"a")
    d2 = source / "D2"
    d2.mkdir()
    (d2 / "Track01.flac").write_bytes(b"bb")  # different size: a real distinct disc
    # "Track01.fix" matches BOTH D1 and D2's Track01 — ambiguous, must not replace.
    fixdir = source / "fix"
    fixdir.mkdir()
    (fixdir / "Track01.fix.flac").write_bytes(b"c")

    tracks = ingest.list_tracks(source, {".flac"})

    assert len(tracks) == 3, "ambiguous match must be appended, not silently dropped"


def test_directory_without_marker_is_not_treated_as_fix_sibling(tmp_path):
    """A same-named sibling directory with no edit marker is a real duplicate

    concern for other checks, not this predicate — it must not be folded in
    just because its directory name happens to overlap by track name alone.
    """
    source = tmp_path / "no marker (LB-00005)"
    source.mkdir()
    d1 = source / "D1"
    d1.mkdir()
    (d1 / "Track01.flac").write_bytes(b"a" * 10)
    other = source / "extra"
    other.mkdir()
    (other / "Track01.flac").write_bytes(b"b" * 20)

    tracks = ingest.list_tracks(source, {".flac"})

    assert len(tracks) == 2, "no marker means no replacement predicate applies"
