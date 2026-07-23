"""
Tests for the site-mirror integrity tool (preservation stack B1).

Covers tools/verify_site_mirror.py:
  - baseline populates local_sha256 for rewritten HTML and verbatim files
  - a verbatim file whose bytes disagree with body_sha256 is flagged, NOT baselined
  - rewritten HTML never reports false drift (the hash-provenance trap)
  - tamper → drift + non-zero exit; delete → missing; stray file → orphan
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import verify_site_mirror as vsm  # noqa: E402

BASE = "http://www.losslessbob.wonderingwhattochoose.com"


# ── Fixture: a tiny mirror + inventory ────────────────────────────────────────

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def mirror(tmp_path: Path):
    """Build a temp mirror + inventory DB.

    Three downloaded rows:
      index.html   — rewritten HTML; on-disk bytes deliberately differ from
                     body_sha256, exactly as the real crawler leaves them
      detail/LB-00001.html — same, under a subdirectory
      files/a.txt  — verbatim; on-disk bytes match body_sha256

    Returns (db_path, site_dir).
    """
    site_dir = tmp_path / "site"
    (site_dir / "detail").mkdir(parents=True)
    (site_dir / "files").mkdir(parents=True)

    raw_index = b"<html><a href='http://www.losslessbob.wonderingwhattochoose.com/x'>x</a></html>"
    disk_index = b"<html><a href='x'>x</a></html>"          # link-rewritten on save
    raw_detail = b"<html>detail raw</html>"
    disk_detail = b"<html>detail rewritten</html>"
    blob = b"verbatim attachment bytes"

    (site_dir / "index.html").write_bytes(disk_index)
    (site_dir / "detail" / "LB-00001.html").write_bytes(disk_detail)
    (site_dir / "files" / "a.txt").write_bytes(blob)

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE site_inventory (
        url TEXT PRIMARY KEY, relative_path TEXT, content_type TEXT,
        status TEXT NOT NULL DEFAULT 'pending', body_sha256 TEXT,
        local_sha256 TEXT, size_bytes INTEGER
    )""")
    conn.executemany(
        "INSERT INTO site_inventory(url, relative_path, status, body_sha256) VALUES (?,?,?,?)",
        [
            (f"{BASE}/index.html", "index.html", "downloaded", _sha(raw_index)),
            (f"{BASE}/detail/LB-00001.html", os.path.join("detail", "LB-00001.html"),
             "downloaded", _sha(raw_detail)),
            (f"{BASE}/files/a.txt", os.path.join("files", "a.txt"), "downloaded", _sha(blob)),
        ],
    )
    conn.commit()
    conn.close()
    return db_path, site_dir


def _local_shas(db_path: Path) -> dict[str, str | None]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT url, local_sha256 FROM site_inventory").fetchall()
    conn.close()
    return {u: s for u, s in rows}


# ── Baseline ──────────────────────────────────────────────────────────────────

def test_baseline_records_on_disk_hashes(mirror):
    """--baseline hashes what is on disk, for both HTML and verbatim rows."""
    db_path, site_dir = mirror
    res = vsm.baseline(db_path, site_dir)

    assert res.baselined == 3
    assert res.unbaselined == 0
    assert not res.issues

    shas = _local_shas(db_path)
    assert shas[f"{BASE}/index.html"] == _sha((site_dir / "index.html").read_bytes())
    assert shas[f"{BASE}/files/a.txt"] == _sha((site_dir / "files" / "a.txt").read_bytes())
    # The HTML baseline is deliberately NOT the raw-body hash.
    conn = sqlite3.connect(db_path)
    body = conn.execute(
        "SELECT body_sha256 FROM site_inventory WHERE url=?", (f"{BASE}/index.html",)
    ).fetchone()[0]
    conn.close()
    assert shas[f"{BASE}/index.html"] != body


def test_baseline_flags_corrupt_verbatim_file_and_skips_it(mirror):
    """A verbatim file that disagrees with body_sha256 is rot — flag, never bless."""
    db_path, site_dir = mirror
    (site_dir / "files" / "a.txt").write_bytes(b"rotted bytes")

    res = vsm.baseline(db_path, site_dir)

    assert res.count(vsm.KIND_PREHASH) == 1
    assert res.failed
    assert res.baselined == 2
    # Left unbaselined so it keeps surfacing on every later verify run.
    assert _local_shas(db_path)[f"{BASE}/files/a.txt"] is None
    assert res.unbaselined == 1


def test_baseline_reports_missing_file(mirror):
    """A row marked downloaded whose file is gone is reported, not hashed."""
    db_path, site_dir = mirror
    (site_dir / "index.html").unlink()

    res = vsm.baseline(db_path, site_dir)

    assert res.count(vsm.KIND_MISSING) == 1
    assert res.baselined == 2


def test_baseline_limit_is_partial_and_resumable(mirror):
    """--limit processes a slice; a second run picks up the rest."""
    db_path, site_dir = mirror
    first = vsm.baseline(db_path, site_dir, limit=1)
    assert first.baselined == 1
    assert first.unbaselined == 2

    second = vsm.baseline(db_path, site_dir)
    assert second.baselined == 2
    assert second.unbaselined == 0


# ── Verify ────────────────────────────────────────────────────────────────────

def test_verify_clean_after_baseline_no_false_html_drift(mirror):
    """The core trap: rewritten HTML must not report drift against body_sha256."""
    db_path, site_dir = mirror
    vsm.baseline(db_path, site_dir)

    res = vsm.verify(db_path, site_dir)

    assert res.ok == 3
    assert res.issues == []
    assert not res.failed
    assert res.unbaselined == 0


def test_verify_unbaselined_html_is_not_compared(mirror):
    """Without a baseline, HTML is counted unbaselined — never drifted."""
    db_path, site_dir = mirror
    res = vsm.verify(db_path, site_dir)

    assert res.unbaselined == 2          # the two HTML rows
    assert res.count(vsm.KIND_DRIFT) == 0
    assert res.ok == 1                   # verbatim row falls back to body_sha256
    assert not res.failed


def test_verify_detects_tampering(mirror):
    """Changing a mirrored file after baseline is drift, and fails the run."""
    db_path, site_dir = mirror
    vsm.baseline(db_path, site_dir)
    (site_dir / "detail" / "LB-00001.html").write_bytes(b"<html>tampered</html>")

    res = vsm.verify(db_path, site_dir)

    assert res.count(vsm.KIND_DRIFT) == 1
    assert res.failed
    assert res.issues[0].target == f"{BASE}/detail/LB-00001.html"


def test_verify_detects_missing_file(mirror):
    """A deleted file is reported as missing."""
    db_path, site_dir = mirror
    vsm.baseline(db_path, site_dir)
    (site_dir / "files" / "a.txt").unlink()

    res = vsm.verify(db_path, site_dir)

    assert res.count(vsm.KIND_MISSING) == 1
    assert res.failed


def test_verify_detects_orphan(mirror):
    """A file with no inventory row is reported, but does not fail the run."""
    db_path, site_dir = mirror
    vsm.baseline(db_path, site_dir)
    (site_dir / "stray.html").write_bytes(b"<html>stray</html>")

    res = vsm.verify(db_path, site_dir)

    assert res.count(vsm.KIND_ORPHAN) == 1
    assert res.issues[0].target == "stray.html"
    assert not res.failed


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_exit_codes_and_report(mirror, tmp_path):
    """main() exits 0 when clean, 1 on drift, and can write a report file."""
    db_path, site_dir = mirror
    argv = ["--db", str(db_path), "--site-dir", str(site_dir)]

    assert vsm.main(argv + ["--baseline"]) == 0
    assert vsm.main(argv) == 0

    (site_dir / "index.html").write_bytes(b"<html>tampered</html>")
    assert vsm.main(argv) == 1

    exports = tmp_path / "exports"
    res = vsm.verify(db_path, site_dir)
    report = vsm.write_report(res, exports)
    text = report.read_text(encoding="utf-8")
    assert vsm.KIND_DRIFT in text
    assert "verify:" in text


def test_report_lands_in_exports_dir(tmp_path, mirror):
    """Report filename is dated and mode-tagged."""
    db_path, site_dir = mirror
    res = vsm.verify(db_path, site_dir)
    report = vsm.write_report(res, tmp_path / "exports")
    assert report.name.startswith("site_mirror_verify_")
    assert report.parent.name == "exports"


# ── Crawler contract ──────────────────────────────────────────────────────────

def test_save_returns_hash_of_written_bytes(tmp_path, monkeypatch):
    """_save's returned digest must match the file it wrote, for HTML and binary."""
    import backend.site_crawler as sc

    monkeypatch.setattr(sc, "SITE_DIR", tmp_path)
    raw = f"<html><a href='{BASE}/detail/LB-00001.html'>x</a></html>".encode()

    path, digest = sc._save(f"{BASE}/index.html", raw)
    assert digest == _sha(path.read_bytes())
    assert digest != _sha(raw), "rewritten HTML must differ from the raw body"

    path, digest = sc._save(f"{BASE}/files/a.txt", b"binary bytes")
    assert digest == _sha(path.read_bytes())
    assert digest == _sha(b"binary bytes"), "verbatim files must match the raw body"


def test_is_rewritten_html_matches_save_behaviour():
    """The helper is the single source of truth for hash provenance."""
    from backend.site_crawler import is_rewritten_html

    assert is_rewritten_html(f"{BASE}/index.html")
    assert is_rewritten_html(f"{BASE}/bynumber/")      # directory index
    assert not is_rewritten_html(f"{BASE}/files/a.txt")
    assert not is_rewritten_html(f"{BASE}/files/x.flac")


def test_local_sha256_column_exists_after_init(tmp_path):
    """init_db creates local_sha256 on a fresh DB (and the migration is idempotent)."""
    import backend.db as _db
    import backend.paths as _paths

    monkey_db = tmp_path / "fresh.db"
    _paths.DATA_DIR = tmp_path
    _db.init_db(str(monkey_db))
    _db.init_db(str(monkey_db))          # idempotent second run

    conn = sqlite3.connect(monkey_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(site_inventory)")]
    conn.close()
    assert "local_sha256" in cols
