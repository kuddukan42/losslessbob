"""BUG-327: one LB folder holding two complete passes of a show must not be concatenated.

LB-07173 (1993-08-28 Milwaukee) holds ``d1``/``d2`` at the top level and a
second complete ``d1``/``d2`` inside a "(REMASTERED)_fixed" subfolder. The two
copies are not byte-identical, so ``_dedupe_subtrees`` correctly leaves both
alone — and ``rglob`` then built one stream containing both, giving 3:27:33
against a 1:32:48 date median and an ``[INFLATED]`` flag that made every
correlation for that date unusable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import ingest  # noqa: E402

EXTS = {".flac"}


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _lb07173(tmp_path: Path) -> Path:
    """Recreate LB-07173's layout: an outer pass plus a nested remastered pass."""
    source = tmp_path / "1993-08-28 Milwaukee (LB-07173)"
    for disc, n in (("d1", 9), ("d2", 2)):
        for i in range(1, n + 1):
            _write(source / disc / f"Track{i:02d}.flac", 1000 + i)
    remaster = source / "bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed"
    for disc, n in (("d1", 9), ("d2", 2)):
        for i in range(1, n + 1):
            _write(remaster / disc / f"Track{i:02d}.flac", 2000 + i)
    # Patch directories: these repeat a track rather than adding one.
    _write(remaster / "bd1993-08-28d1.fix" / "Track08.fix.flac", 3008)
    _write(remaster / "bd1993-08-28d1.fix" / "Track09.fix.flac", 3009)
    _write(remaster / "d1" / "fix" / "Track08.fix.flac", 3108)
    return source


def test_nested_second_pass_is_dropped(tmp_path, caplog):
    source = _lb07173(tmp_path)

    with caplog.at_level("WARNING"):
        tracks = ingest.list_tracks(source, EXTS)

    assert len(tracks) == 11
    assert {str(p.relative_to(source)) for p in tracks} == {
        f"d{disc}/Track{i:02d}.flac"
        for disc, n in ((1, 9), (2, 2))
        for i in range(1, n + 1)
    }
    assert "holds the show twice" in caplog.text
    assert "(REMASTERED)_fixed" in caplog.text


def test_outer_pass_is_the_one_kept_even_though_the_nested_one_has_more_files(tmp_path):
    """Patch dirs make the nested pass larger by file count; it is still the copy dropped."""
    source = _lb07173(tmp_path)
    remaster = source / "bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed"

    tracks = ingest.list_tracks(source, EXTS)

    assert not any(remaster in p.parents for p in tracks)


def test_flat_duplicate_copy_beside_the_original_is_detected(tmp_path):
    source = tmp_path / "show (LB-00001)"
    for i in range(1, 8):
        _write(source / f"Track{i:02d}.flac", 1000 + i)
        _write(source / "remaster" / f"Track{i:02d}.flac", 2000 + i)

    tracks = ingest.list_tracks(source, EXTS)

    assert len(tracks) == 7
    assert all(p.parent == source for p in tracks)


def test_multi_disc_show_with_repeated_filenames_is_left_alone(tmp_path):
    """d1/d2 repeat Track01.., but neither disc is a second pass of the other."""
    source = tmp_path / "show (LB-00002)"
    for disc, n in (("d1", 9), ("d2", 5)):
        for i in range(1, n + 1):
            _write(source / disc / f"Track{i:02d}.flac", 1000 + i)

    assert len(ingest.list_tracks(source, EXTS)) == 14


def test_flat_single_directory_source_is_left_alone(tmp_path):
    source = tmp_path / "show (LB-00003)"
    for i in range(1, 12):
        _write(source / f"Track{i:02d}.flac", 1000 + i)

    assert len(ingest.list_tracks(source, EXTS)) == 11


def test_nested_bonus_material_is_not_mistaken_for_a_second_pass(tmp_path):
    """A small extras folder shares no track keys with the show and must survive."""
    source = tmp_path / "show (LB-00004)"
    for i in range(1, 12):
        _write(source / f"Track{i:02d}.flac", 1000 + i)
    for name in ("Soundcheck.flac", "Interview.flac", "Radio spot.flac"):
        _write(source / "bonus" / name, 500)

    assert len(ingest.list_tracks(source, EXTS)) == 14


def test_select_version_reports_the_dropped_pass(tmp_path):
    source = _lb07173(tmp_path)
    tracks = sorted(
        p for p in source.rglob("*") if p.is_file() and p.suffix == ".flac"
    )

    kept, dropped = ingest._select_version(tracks, source)

    assert dropped is not None
    nested_root, n_inside, n_outside = dropped
    assert nested_root.name == "bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed"
    assert (n_inside, n_outside) == (14, 11)
    assert len(kept) == 11
