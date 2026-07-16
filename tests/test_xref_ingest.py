"""
Tests for the site-mirror xref checksum ingest module (TODO-252 / B8).

Covers:
  - backend/xref_ingest.py — scan_mirror(), get_filesets(), approve_filesets(),
    reject_filesets()
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_db() -> tuple[str, object, str]:
    """Create a fresh temp DB with full schema. Returns (db_path, conn, tmp_dir).

    Redirects DATA_DIR and DB_PATH so no writes touch the real data/ folder.
    """
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_xref_ingest_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.db as _db
    import backend.paths as _paths
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)

    _db.init_db(db_path)
    conn = _db.get_connection(db_path)
    return db_path, conn, tmp_dir


def _patch_site_files_dir(monkeypatch, tmp_dir: str) -> Path:
    """Redirect SITE_FILES_DIR (in both paths and xref_ingest modules) to a
    subdirectory of tmp_dir, so scan tests never touch data/site/files/.
    """
    import backend.paths as _paths
    import backend.xref_ingest as _xi

    files_dir = Path(tmp_dir) / "site" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_paths, "SITE_FILES_DIR", files_dir)
    monkeypatch.setattr(_xi, "SITE_FILES_DIR", files_dir)
    return files_dir


def _write_checksum_file(files_dir: Path, lb: int, xref: int, lines: list[str]) -> Path:
    """Write a synthetic LBF-*-xref-*-text.txt fixture with the given md5 lines."""
    name = f"LBF-{lb:05d}-xref-{xref:05d}-text.txt"
    path = files_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _md5_line(checksum: str, filename: str = "Track01.flac") -> str:
    """A parseable MD5-style checksum line: '<32-hex> *filename'."""
    return f"{checksum} *{filename}"


CHK_A = "a" * 32
CHK_B = "b" * 32
CHK_C = "c" * 32
CHK_D = "d" * 32


def _insert_checksum(conn, checksum: str, lb_number: int, xref: int = 0,
                      filename: str = "existing.flac") -> None:
    """Directly seed a checksums row (simulating a prior master import)."""
    conn.execute(
        "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref) "
        "VALUES (?,?,?,?,?)",
        (checksum, filename, "m", lb_number, xref),
    )
    conn.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_scan_stages_only_filesets_with_new_rows(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    # LB 1 / xref 100: two brand-new checksums -> should stage.
    _write_checksum_file(files_dir, 1, 100, [_md5_line(CHK_A), _md5_line(CHK_B, "Track02.flac")])
    # LB 2 / xref 200: single checksum already known -> should NOT stage.
    _insert_checksum(conn, CHK_C, lb_number=2)
    _write_checksum_file(files_dir, 2, 200, [_md5_line(CHK_C)])

    summary = xi.scan_mirror(db_path=db_path)

    assert summary["scanned"] == 2
    assert summary["staged_new"] == 1
    assert summary["skipped_no_new"] == 1
    assert summary["unparseable"] == 0

    filesets = xi.get_filesets(db_path=db_path)
    assert len(filesets) == 1
    fs = filesets[0]
    assert fs["lb_number"] == 1
    assert fs["xref"] == 100
    assert fs["status"] == "staged"
    assert fs["row_count"] == 2
    assert fs["new_count"] == 2


def test_rescan_is_idempotent(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    _write_checksum_file(files_dir, 1, 100, [_md5_line(CHK_A), _md5_line(CHK_B, "Track02.flac")])

    first = xi.scan_mirror(db_path=db_path)
    assert first["staged_new"] == 1

    second = xi.scan_mirror(db_path=db_path)
    assert second["staged_new"] == 0
    assert second["updated"] == 1

    filesets = xi.get_filesets(db_path=db_path)
    assert len(filesets) == 1  # no duplicate fileset row
    row_count = conn.execute(
        "SELECT COUNT(*) FROM xref_ingest_rows WHERE fileset_id=?", (filesets[0]["id"],)
    ).fetchone()[0]
    assert row_count == 2  # no duplicate rows from the rescan


def test_rescan_never_touches_approved_or_rejected(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    _write_checksum_file(files_dir, 1, 100, [_md5_line(CHK_A)])
    _write_checksum_file(files_dir, 2, 200, [_md5_line(CHK_B, "Track02.flac")])

    xi.scan_mirror(db_path=db_path)
    filesets = {fs["xref"]: fs for fs in xi.get_filesets(db_path=db_path)}
    approve_id = filesets[100]["id"]
    reject_id = filesets[200]["id"]

    xi.approve_filesets([approve_id], db_path=db_path)
    xi.reject_filesets([reject_id], db_path=db_path)

    # Rewrite the underlying files (simulating new content on disk) and rescan.
    _write_checksum_file(files_dir, 1, 100, [_md5_line(CHK_A), _md5_line(CHK_C, "New.flac")])
    _write_checksum_file(files_dir, 2, 200, [_md5_line(CHK_B, "Track02.flac"), _md5_line(CHK_D, "New2.flac")])

    summary = xi.scan_mirror(db_path=db_path)
    assert summary["skipped_decided"] == 2
    assert summary["staged_new"] == 0
    assert summary["updated"] == 0

    after = {fs["id"]: fs for fs in xi.get_filesets(db_path=db_path)}
    assert after[approve_id]["status"] == "approved"
    assert after[approve_id]["new_count"] == 1  # untouched, original scan value
    assert after[reject_id]["status"] == "rejected"


def test_shared_checksum_lb_pair_not_counted_as_new(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    # CHK_A already known for LB 3 (e.g. from a prior master import).
    _insert_checksum(conn, CHK_A, lb_number=3)

    # Two xref filesets for the same LB, both referencing CHK_A plus one
    # unique new checksum each.
    _write_checksum_file(files_dir, 3, 300, [_md5_line(CHK_A), _md5_line(CHK_B, "Track02.flac")])
    _write_checksum_file(files_dir, 3, 301, [_md5_line(CHK_A), _md5_line(CHK_C, "Track03.flac")])

    summary = xi.scan_mirror(db_path=db_path)
    assert summary["staged_new"] == 2

    filesets = {fs["xref"]: fs for fs in xi.get_filesets(db_path=db_path)}
    assert filesets[300]["row_count"] == 2
    assert filesets[300]["new_count"] == 1  # only CHK_B is new
    assert filesets[301]["row_count"] == 2
    assert filesets[301]["new_count"] == 1  # only CHK_C is new

    rows_300 = conn.execute(
        "SELECT checksum, is_new FROM xref_ingest_rows WHERE fileset_id=?",
        (filesets[300]["id"],),
    ).fetchall()
    is_new_by_chk = {r[0]: r[1] for r in rows_300}
    assert is_new_by_chk[CHK_A] == 0
    assert is_new_by_chk[CHK_B] == 1


def test_approve_writes_exactly_new_rows_with_correct_xref(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    _insert_checksum(conn, CHK_A, lb_number=4)
    _write_checksum_file(files_dir, 4, 400, [_md5_line(CHK_A), _md5_line(CHK_B, "Track02.flac")])

    xi.scan_mirror(db_path=db_path)
    fs = xi.get_filesets(db_path=db_path)[0]
    assert fs["lb_number"] == 4 and fs["xref"] == 400

    result = xi.approve_filesets([fs["id"]], db_path=db_path)
    assert result["approved"] == [fs["id"]]
    assert result["refused"] == []
    assert result["rows_inserted"] == 1  # only CHK_B was new

    rows = conn.execute(
        "SELECT checksum, lb_number, xref FROM checksums WHERE lb_number=4"
    ).fetchall()
    by_chk = {r[0]: (r[1], r[2]) for r in rows}
    assert CHK_A in by_chk  # pre-existing row untouched
    assert by_chk[CHK_B] == (4, 400)  # newly written row carries the fileset's xref

    after = xi.get_filesets(db_path=db_path)[0]
    assert after["status"] == "approved"
    assert after["decided_at"] is not None


def test_approve_refuses_non_staged_ids(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    _write_checksum_file(files_dir, 5, 500, [_md5_line(CHK_A)])
    xi.scan_mirror(db_path=db_path)
    fs_id = xi.get_filesets(db_path=db_path)[0]["id"]

    # Non-existent id.
    result = xi.approve_filesets([99999], db_path=db_path)
    assert result["approved"] == []
    assert result["refused"] == [99999]
    assert result["rows_inserted"] == 0

    # Approve once, then try again -> refused (no longer 'staged').
    xi.approve_filesets([fs_id], db_path=db_path)
    result2 = xi.approve_filesets([fs_id], db_path=db_path)
    assert result2["approved"] == []
    assert result2["refused"] == [fs_id]


def test_reject_marks_status_and_refuses_non_staged(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    _write_checksum_file(files_dir, 6, 600, [_md5_line(CHK_A)])
    xi.scan_mirror(db_path=db_path)
    fs_id = xi.get_filesets(db_path=db_path)[0]["id"]

    result = xi.reject_filesets([fs_id], db_path=db_path)
    assert result["rejected"] == [fs_id]
    assert result["refused"] == []

    fs = xi.get_filesets(db_path=db_path)[0]
    assert fs["status"] == "rejected"
    assert fs["decided_at"] is not None

    # checksums table must remain untouched by a rejection.
    count = conn.execute("SELECT COUNT(*) FROM checksums WHERE lb_number=6").fetchone()[0]
    assert count == 0

    # Rejecting again (no longer 'staged') is refused.
    result2 = xi.reject_filesets([fs_id], db_path=db_path)
    assert result2["rejected"] == []
    assert result2["refused"] == [fs_id]


def test_unparseable_filename_counted_and_skipped(monkeypatch):
    db_path, conn, tmp_dir = _make_db()
    files_dir = _patch_site_files_dir(monkeypatch, tmp_dir)
    import backend.xref_ingest as xi

    # Matches the glob but not the strict LBF-{digits}-xref-{digits}-text.txt
    # filename pattern -> lb/xref cannot be parsed from the name.
    bad_path = files_dir / "LBF-abcde-xref-00100-text.txt"
    bad_path.write_text(_md5_line(CHK_A), encoding="utf-8")

    _write_checksum_file(files_dir, 7, 700, [_md5_line(CHK_B, "Track02.flac")])

    summary = xi.scan_mirror(db_path=db_path)
    assert summary["unparseable"] == 1
    assert bad_path.name in summary["unparseable_files"]
    assert summary["staged_new"] == 1  # the well-formed file still stages

    filesets = xi.get_filesets(db_path=db_path)
    assert len(filesets) == 1
    assert filesets[0]["lb_number"] == 7


def test_scan_missing_site_files_dir_returns_empty_summary(monkeypatch, tmp_path):
    db_path, conn, tmp_dir = _make_db()
    import backend.paths as _paths
    import backend.xref_ingest as xi

    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(_paths, "SITE_FILES_DIR", missing_dir)
    monkeypatch.setattr(xi, "SITE_FILES_DIR", missing_dir)

    summary = xi.scan_mirror(db_path=db_path)
    assert summary["scanned"] == 0
    assert summary["staged_new"] == 0
    assert xi.get_filesets(db_path=db_path) == []
