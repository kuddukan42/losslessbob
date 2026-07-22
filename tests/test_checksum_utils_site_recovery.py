"""
Tests for the lbdir reconcile trio (BUG-174 / BUG-252):

- find_site_recoverable_files: MD5 + filename-fallback recovery from
  data/site/files; unreconcilable entries (self-referencing manifests,
  regenerated reports) are excluded from the missing set entirely.
- find_reconcilable_files: same filename fallback for on-disk near-duplicates
  at wrong paths, flagged matched_by='name' with the MD5 mismatch exposed.
- verify_folder_lbdir: unreconcilable entries never count as missing/fail.
"""
import hashlib
import tempfile
from pathlib import Path

from backend.checksum_utils import (
    find_reconcilable_files,
    find_site_recoverable_files,
    verify_folder_lbdir,
)


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

    # notes.txt is missing; the site copy is a different revision (name-only match).
    notes_expected_md5 = _md5(b"old-notes")
    (site_dir / "LBF-13333-notes.txt").write_bytes(b"new-notes")

    # Unreconcilable entries (BUG-252): the manifest's self-entry and a
    # regenerated DigiFlawFinder report. Site copies exist but can never match
    # by MD5 — they must be excluded from the missing set, producing NO proposal.
    lbdir_self_expected_md5 = _md5(b"old-lbdir-bytes")
    (site_dir / "LBF-13333-lbdir-bd92-09-12-pdub-dolphinsmile.flac1648.txt").write_bytes(
        b"new-lbdir-bytes"
    )
    flaw_expected_md5 = _md5(b"old-flaw-report")
    (site_dir / "LBF-13333-DigiFlawFinder-bd92-09-12-pdub-dolphinsmile.flac1648.wavf.html").write_bytes(
        b"new-flaw-report"
    )

    lbdir_text = "\n".join([
        "=== md5 for: bd92-09-12-pdub-dolphinsmile.flac1648",
        f"{track_md5} *01.flac",
        f"{info_md5} *info.txt",
        f"{notes_expected_md5} *notes.txt",
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

    notes = proposals["notes.txt"]
    assert notes["matched_by"] == "name"
    assert notes["expected_md5"] == notes_expected_md5
    assert notes["md5"] != notes_expected_md5

    # BUG-252: unreconcilable entries are excluded, not offered as band-aids.
    assert "lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt" not in proposals
    assert "DigiFlawFinder-bd92-09-12-PDub-Dolphinsmile.flac1648.wavf.html" not in proposals


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


def test_find_reconcilable_files_md5_match_and_name_fallback():
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "folder"
    folder.mkdir()
    (folder / "extras").mkdir()

    # Exact-content file at the wrong path -> classic MD5 rename proposal.
    info_md5 = _md5(b"info-bytes")
    (folder / "extras" / "wrong-name.txt").write_bytes(b"info-bytes")

    # Near-duplicate revision at the wrong path with an LBF- prefix: only the
    # (normalised) basename matches -> matched_by='name' proposal (BUG-252).
    notes_expected_md5 = _md5(b"old-notes")
    (folder / "extras" / "LBF-16216-notes.txt").write_bytes(b"new-notes")

    # A genuinely unrelated disk file stays unmatched.
    (folder / "extras" / "unrelated.jpg").write_bytes(b"jpeg")

    lbdir_text = "\n".join([
        "=== md5 for: example",
        f"{info_md5} *info.txt",
        f"{notes_expected_md5} *notes.txt",
    ])
    lbdir_path = folder / "lbdir-example.txt"
    lbdir_path.write_text(lbdir_text)

    result = find_reconcilable_files(folder, lbdir_path)
    proposals = {p["lbdir_rel"]: p for p in result["proposals"]}

    info = proposals["info.txt"]
    assert info["disk_rel"] == "extras/wrong-name.txt"
    assert info["matched_by"] == "md5"
    assert info["md5"] == info_md5 == info["expected_md5"]

    notes = proposals["notes.txt"]
    assert notes["disk_rel"] == "extras/LBF-16216-notes.txt"
    assert notes["matched_by"] == "name"
    assert notes["expected_md5"] == notes_expected_md5
    assert notes["md5"] == _md5(b"new-notes")

    assert result["unmatched_lbdir"] == []
    assert result["unmatched_disk"] == ["extras/unrelated.jpg"]


def test_find_reconcilable_files_excludes_unreconcilable_entries():
    """Self-referencing manifest + regenerated report entries generate neither
    proposals nor unmatched noise, even when a near-duplicate sits on disk
    (the LB-16216 extras/ case from BUG-252)."""
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "folder"
    folder.mkdir()
    (folder / "extras").mkdir()

    # On-disk near-duplicate of the manifest self-entry (different bytes).
    (folder / "extras" / "LBF-16216-lbdir-bd92-09-12.flac1648.txt").write_bytes(
        b"regenerated-manifest"
    )

    track_md5 = _md5(b"track")
    (folder / "01.flac").write_bytes(b"track")

    lbdir_text = "\n".join([
        "=== md5 for: bd92-09-12",
        f"{track_md5} *01.flac",
        f"{_md5(b'circular')} *lbdir-bd92-09-12.flac1648.txt",
        f"{_md5(b'old-report')} *DigiFlawFinder-bd92-09-12.wavf.html",
    ])
    lbdir_path = folder / "LBF-16216-lbdir-bd92-09-12.flac1648.txt"
    lbdir_path.write_text(lbdir_text)

    result = find_reconcilable_files(folder, lbdir_path)

    assert result["proposals"] == []
    assert result["unmatched_lbdir"] == []
    # The near-duplicate stays a plain disk extra rather than masquerading as
    # a second candidate for the manifest entry.
    assert result["unmatched_disk"] == ["extras/LBF-16216-lbdir-bd92-09-12.flac1648.txt"]


def test_verify_folder_lbdir_unreconcilable_entries_never_fail():
    """Missing or MD5-mismatching self-manifest / regenerated-report entries
    count as pass — they can never be satisfied from any source (BUG-252)."""
    tmp = Path(tempfile.mkdtemp())
    folder = tmp / "folder"
    folder.mkdir()

    info_md5 = _md5(b"info")
    (folder / "info.txt").write_bytes(b"info")

    # On-disk DigiFlawFinder copy whose bytes differ from the recorded hash.
    (folder / "DigiFlawFinder-bd92-09-12.wavf.html").write_bytes(b"regenerated")

    lbdir_text = "\n".join([
        "=== md5 for: bd92-09-12",
        f"{info_md5} *info.txt",
        f"{_md5(b'circular')} *lbdir-bd92-09-12.flac1648.txt",           # missing self-entry
        f"{_md5(b'old-report')} *DigiFlawFinder-bd92-09-12.wavf.html",   # on-disk, mismatched
        f"{_md5(b'never-generated')} *DigiFlawFinder-bd92-09-12-v2.wavf.html",  # missing report
    ])
    lbdir_path = folder / "lbdir-bd92-09-12.flac1648.txt"
    lbdir_path.write_text(lbdir_text)

    result = verify_folder_lbdir(str(folder), str(lbdir_path))

    assert result["status"] == "pass"
    assert result["mismatch"] == 0
    assert result["missing"] == 0
    by_name = {f["filename"]: f for f in result["files"]}
    assert by_name["info.txt"]["overall"] == "pass"
    assert by_name["lbdir-bd92-09-12.flac1648.txt"]["overall"] == "pass"
    assert by_name["DigiFlawFinder-bd92-09-12.wavf.html"]["overall"] == "pass"
    # The mismatch detail stays visible even though it doesn't fail the folder.
    assert by_name["DigiFlawFinder-bd92-09-12.wavf.html"]["md5_status"] == "fail"
    assert by_name["DigiFlawFinder-bd92-09-12-v2.wavf.html"]["overall"] == "pass"
