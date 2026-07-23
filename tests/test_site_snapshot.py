"""
Tests for the sealed-snapshot builder (preservation stack B2).

Covers tools/make_site_snapshot.py:
  - staging uses hardlinks; manifest/seal/README/verifier are written
  - the embedded verify_snapshot.py runs on stock Python and passes
  - tampering a payload file, or the manifest itself, makes it fail by name
  - two builds of unchanged input produce identical manifest.txt
  - the build refuses to seal a mirror that fails verification
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import make_site_snapshot as mss  # noqa: E402
from tools import verify_site_mirror as vsm  # noqa: E402

BASE = "http://www.losslessbob.wonderingwhattochoose.com"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def archive(tmp_path: Path):
    """Build a tiny archive: site mirror + olof mirror + inventory DB.

    Returns (db_path, site_dir, payload) where payload is the (src, subpath)
    list handed to make_snapshot().
    """
    site_dir = tmp_path / "site"
    (site_dir / "detail").mkdir(parents=True)
    olof_dir = tmp_path / "olof" / "pages"
    olof_dir.mkdir(parents=True)

    disk_index = b"<html><a href='detail/LB-00001.html'>x</a></html>"
    disk_detail = b"<html>detail</html>"
    (site_dir / "index.html").write_bytes(disk_index)
    (site_dir / "detail" / "LB-00001.html").write_bytes(disk_detail)
    (olof_dir / "dsn1966.html").write_bytes(b"<html>olof</html>")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE site_inventory (
        url TEXT PRIMARY KEY, relative_path TEXT, content_type TEXT,
        status TEXT NOT NULL DEFAULT 'pending', body_sha256 TEXT,
        local_sha256 TEXT, size_bytes INTEGER
    )""")
    conn.executemany(
        "INSERT INTO site_inventory(url, relative_path, status, local_sha256) "
        "VALUES (?,?,?,?)",
        [
            (f"{BASE}/index.html", "index.html", "downloaded", _sha(disk_index)),
            (f"{BASE}/detail/LB-00001.html", os.path.join("detail", "LB-00001.html"),
             "downloaded", _sha(disk_detail)),
        ],
    )
    conn.commit()
    conn.close()

    payload = [(site_dir, "site"), (olof_dir, "olof/pages")]
    return db_path, site_dir, payload


def _build(tmp_path: Path, archive, **kwargs):
    db_path, site_dir, payload = archive
    opts = dict(root=tmp_path / "snapshots", payload=payload, db_path=db_path,
                site_dir=site_dir, with_db=False)
    opts.update(kwargs)
    return mss.make_snapshot(**opts)


def _run_verifier(snap_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, mss.VERIFIER_NAME],
        cwd=snap_dir, capture_output=True, text=True,
    )


# ── Structure ─────────────────────────────────────────────────────────────────

def test_snapshot_has_all_parts(tmp_path, archive):
    """A snapshot carries payload, manifest, seal, README and the verifier."""
    res = _build(tmp_path, archive)
    snap = res.path

    assert (snap / "site" / "index.html").exists()
    assert (snap / "site" / "detail" / "LB-00001.html").exists()
    assert (snap / "olof" / "pages" / "dsn1966.html").exists()
    for name in (mss.MANIFEST_NAME, mss.SEAL_NAME, mss.README_NAME, mss.VERIFIER_NAME):
        assert (snap / name).exists(), name

    # 3 payload files + the verifier; README/manifest/seal are not self-listed.
    assert res.files == 4
    manifest = (snap / mss.MANIFEST_NAME).read_text(encoding="utf-8")
    assert "site/index.html" in manifest
    assert mss.README_NAME not in manifest
    assert mss.MANIFEST_NAME not in manifest


def test_staging_uses_hardlinks(tmp_path, archive):
    """Payload is hardlinked, so a snapshot costs almost no extra disk."""
    _db, site_dir, _payload = archive
    res = _build(tmp_path, archive)

    src = site_dir / "index.html"
    staged = res.path / "site" / "index.html"
    assert staged.stat().st_ino == src.stat().st_ino
    assert res.linked == 3
    assert res.copied == 0


def test_readme_documents_verification_and_privacy(tmp_path, archive):
    """The recipient-facing README says how to check it and not to publish it."""
    res = _build(tmp_path, archive)
    text = (res.path / mss.README_NAME).read_text(encoding="utf-8")

    assert "verify_snapshot.py" in text
    assert "http.server" in text
    assert "private" in text.lower()


def test_collision_suffix(tmp_path, archive):
    """Two snapshots on the same day get distinct directories."""
    first = _build(tmp_path, archive, today="2026-07-23")
    second = _build(tmp_path, archive, today="2026-07-23")

    assert first.path.name == "lbsnap-2026-07-23"
    assert second.path.name == "lbsnap-2026-07-23.1"


# ── The embedded verifier ─────────────────────────────────────────────────────

def test_embedded_verifier_passes_on_fresh_snapshot(tmp_path, archive):
    """A friend with stock Python and no repo can confirm the snapshot."""
    res = _build(tmp_path, archive)
    proc = _run_verifier(res.path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "4 file(s) verified, 0 problem(s)" in proc.stdout


def test_embedded_verifier_names_the_tampered_file(tmp_path, archive):
    """Altering a payload file fails the check and identifies it."""
    res = _build(tmp_path, archive)
    # Same byte length as the original, so this exercises the hash check rather
    # than the cheaper size check.
    (res.path / "site" / "detail" / "LB-00001.html").write_bytes(b"<html>TAMPER</html>")

    proc = _run_verifier(res.path)

    assert proc.returncode == 1
    assert "site/detail/LB-00001.html" in proc.stdout
    assert "corrupt" in proc.stdout


def test_embedded_verifier_detects_deletion(tmp_path, archive):
    """A file removed from the snapshot is reported as missing."""
    res = _build(tmp_path, archive)
    (res.path / "olof" / "pages" / "dsn1966.html").unlink()

    proc = _run_verifier(res.path)

    assert proc.returncode == 1
    assert "missing" in proc.stdout
    assert "olof/pages/dsn1966.html" in proc.stdout


def test_seal_detects_manifest_tampering(tmp_path, archive):
    """Rewriting the manifest to cover altered files breaks the seal."""
    res = _build(tmp_path, archive)
    target = res.path / "site" / "index.html"
    target.write_bytes(b"<html>swapped</html>")
    # Forge a manifest that matches the altered file — the seal must still catch it.
    lines = []
    for line in (res.path / mss.MANIFEST_NAME).read_text(encoding="utf-8").splitlines():
        sha, size, rel = line.split("  ", 2)
        if rel == "site/index.html":
            data = target.read_bytes()
            line = f"{_sha(data)}  {len(data)}  {rel}"
        lines.append(line)
    (res.path / mss.MANIFEST_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")

    proc = _run_verifier(res.path)

    assert proc.returncode == 1
    assert "seal mismatch" in proc.stdout


def test_verifier_source_is_stdlib_only(tmp_path, archive):
    """The embedded verifier must not import anything from the repo."""
    res = _build(tmp_path, archive)
    source = (res.path / mss.VERIFIER_NAME).read_text(encoding="utf-8")

    assert "backend" not in source
    assert "tools" not in source
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            module = line.split()[1].split(".")[0]
            assert module in {"hashlib", "sys", "pathlib"}, module


# ── Determinism ───────────────────────────────────────────────────────────────

def test_two_builds_produce_identical_manifest(tmp_path, archive):
    """Unchanged input must seal identically — only the README carries a clock."""
    first = _build(tmp_path, archive, today="2026-07-23")
    second = _build(tmp_path, archive, today="2026-07-23")

    m1 = (first.path / mss.MANIFEST_NAME).read_text(encoding="utf-8")
    m2 = (second.path / mss.MANIFEST_NAME).read_text(encoding="utf-8")
    assert m1 == m2
    assert first.seal == second.seal

    r1 = (first.path / mss.README_NAME).read_text(encoding="utf-8")
    r2 = (second.path / mss.README_NAME).read_text(encoding="utf-8")
    assert r1 != r2, "README should carry the build timestamp"


# ── Refusal to seal a broken mirror ───────────────────────────────────────────

def test_refuses_when_mirror_verification_fails(tmp_path, archive):
    """A drifted mirror must not be sealed — that would certify the damage."""
    _db, site_dir, _payload = archive
    (site_dir / "index.html").write_bytes(b"<html>drifted</html>")

    with pytest.raises(RuntimeError, match="refusing to seal"):
        _build(tmp_path, archive, verify_first=True)


def test_no_verify_escape_hatch(tmp_path, archive, caplog):
    """--no-verify still builds, but says loudly what it skipped."""
    _db, site_dir, _payload = archive
    (site_dir / "index.html").write_bytes(b"<html>drifted</html>")

    res = _build(tmp_path, archive, verify_first=False)

    assert res.path.exists()
    assert any("no-verify" in r.message.lower() for r in caplog.records)


def test_verify_first_runs_and_passes_on_clean_mirror(tmp_path, archive):
    """The pre-build check is recorded on the result."""
    res = _build(tmp_path, archive, verify_first=True)

    assert res.verify is not None
    assert not res.verify.failed
    assert res.verify.ok == 2


# ── Tarball ───────────────────────────────────────────────────────────────────

def test_tar_writes_archive_and_sidecar(tmp_path, archive):
    """--tar produces a tarball plus a matching .sha256 sidecar."""
    res = _build(tmp_path, archive, tar=True)

    assert res.tar_path is not None and res.tar_path.exists()
    sidecar = Path(str(res.tar_path) + ".sha256")
    assert sidecar.exists()
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    assert recorded == vsm.hash_file(res.tar_path)


def test_no_upload_paths_in_tool():
    """The snapshot tool must never gain a network path.

    Checked structurally rather than by keyword: the prose in this file talks
    about uploads precisely in order to forbid them.
    """
    import ast

    tree = ast.parse(Path(mss.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    network = {"requests", "urllib", "http", "socket", "ftplib", "smtplib", "boto3"}
    assert not (imported & network), imported & network
    assert "github_release" not in Path(mss.__file__).read_text(encoding="utf-8")
