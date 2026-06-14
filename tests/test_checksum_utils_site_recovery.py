"""
Tests for find_site_recoverable_files (lbdir reconcile -> data/site/files recovery).

Covers BUG-174: self-referencing lbdir entries (the manifest itself) and
regenerated reports (e.g. DigiFlawFinder) can never match by MD5 across lbdir
revisions, so a filename-based fallback recovers them too.
"""
import hashlib
import tempfile
from pathlib import Path

from backend.checksum_utils import find_site_recoverable_files


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def test_find_site_recoverable_files_md5_and_name_fallback():
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "1992-09-12 Pensacola, Florida (LB-13333)"
    folder.mkdir()
    site_dir = tmp / "site_files"
    site_dir.mkdir()

    # A track that's on disk and in the lbdir -> not missing, no proposal expected.
    track_md5 = _md5(b"track-data")
    (folder / "01.flac").write_bytes(b"track-data")

    # info.txt is missing from disk, but its site/files copy matches exactly (MD5 match).
    info_md5 = _md5(b"info-content")
    (site_dir / "LBF-13333-info.txt").write_bytes(b"info-content")

    # The lbdir manifest's self-entry expects an older revision's hash; the cached
    # site copy is a newer revision with different bytes -> only matches by name.
    lbdir_self_expected_md5 = _md5(b"old-lbdir-bytes")
    (site_dir / "LBF-13333-lbdir-bd92-09-12-pdub-dolphinsmile.flac1648.txt").write_bytes(
        b"new-lbdir-bytes"
    )

    # DigiFlawFinder report: regenerated content, different hash, recoverable by name.
    flaw_expected_md5 = _md5(b"old-flaw-report")
    (site_dir / "LBF-13333-DigiFlawFinder-bd92-09-12-pdub-dolphinsmile.flac1648.wavf.html").write_bytes(
        b"new-flaw-report"
    )

    lbdir_text = "\n".join([
        "=== md5 for: bd92-09-12-pdub-dolphinsmile.flac1648",
        f"{track_md5} *01.flac",
        f"{info_md5} *info.txt",
        f"{lbdir_self_expected_md5} *lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt",
        f"{flaw_expected_md5} *DigiFlawFinder-bd92-09-12-PDub-Dolphinsmile.flac1648.wavf.html",
    ])
    lbdir_path = folder / "LBF-13333-lbdir-bd92-09-12-pdub-dolphinsmile.flac1648.txt"
    lbdir_path.write_text(lbdir_text)

    result = find_site_recoverable_files(folder, lbdir_path, site_dir, 13333)
    proposals = {p["lbdir_rel"]: p for p in result["site_proposals"]}

    assert "01.flac" not in proposals

    assert proposals["info.txt"]["matched_by"] == "md5"
    assert proposals["info.txt"]["md5"] == info_md5
    assert proposals["info.txt"]["expected_md5"] == info_md5

    lbdir_self = proposals["lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt"]
    assert lbdir_self["matched_by"] == "name"
    assert lbdir_self["expected_md5"] == lbdir_self_expected_md5
    assert lbdir_self["md5"] != lbdir_self_expected_md5

    flaw = proposals["DigiFlawFinder-bd92-09-12-PDub-Dolphinsmile.flac1648.wavf.html"]
    assert flaw["matched_by"] == "name"
    assert flaw["expected_md5"] == flaw_expected_md5
    assert flaw["md5"] != flaw_expected_md5


def test_find_site_recoverable_files_no_missing_entries_returns_empty():
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "folder"
    folder.mkdir()
    site_dir = tmp / "site_files"
    site_dir.mkdir()

    track_md5 = _md5(b"track-data")
    (folder / "01.flac").write_bytes(b"track-data")

    lbdir_text = "\n".join([
        "=== md5 for: example",
        f"{track_md5} *01.flac",
    ])
    lbdir_path = folder / "lbdir-example.txt"
    lbdir_path.write_text(lbdir_text)

    result = find_site_recoverable_files(folder, lbdir_path, site_dir, 99999)
    assert result["site_proposals"] == []
