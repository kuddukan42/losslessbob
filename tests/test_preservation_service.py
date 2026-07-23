"""
Tests for the preservation service layer (TODO-266) — the GUI-facing wrapper
around the TODO-265 CLI tools.

Covers backend/preservation.py:
  - jobs run on a thread and land in a terminal stage with a result payload
  - the single-instance guard rejects a second concurrent job
  - cooperative cancellation stops a run and reports it as cancelled
  - a failing job surfaces as stage="error" rather than hanging "running"
  - snapshot / report inventory reads manifests without re-hashing
  - read_report refuses paths outside data/exports/
  - the progress + cancel hooks added to the three tools stay back-compatible
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import preservation  # noqa: E402
from tools import check_mirror_links as cml  # noqa: E402
from tools import make_site_snapshot as mss  # noqa: E402
from tools import verify_site_mirror as vsm  # noqa: E402

BASE = "http://www.losslessbob.wonderingwhattochoose.com"
SETTLE_TIMEOUT_S = 30


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mirror(tmp_path: Path):
    """Build a small temp mirror + inventory DB, fully baselined.

    Returns (db_path, site_dir).
    """
    site_dir = tmp_path / "site"
    (site_dir / "files").mkdir(parents=True)

    disk_index = b"<html><a href='files/a.txt'>a</a></html>"
    blob = b"verbatim attachment bytes"
    (site_dir / "index.html").write_bytes(disk_index)
    (site_dir / "files" / "a.txt").write_bytes(blob)

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE site_inventory (
        url TEXT PRIMARY KEY, relative_path TEXT, content_type TEXT,
        status TEXT NOT NULL DEFAULT 'pending', body_sha256 TEXT,
        local_sha256 TEXT, size_bytes INTEGER
    )""")
    conn.executemany(
        "INSERT INTO site_inventory(url, relative_path, status, body_sha256, local_sha256) "
        "VALUES (?,?,?,?,?)",
        [
            (f"{BASE}/index.html", "index.html", "downloaded",
             _sha(b"<html>raw</html>"), _sha(disk_index)),
            (f"{BASE}/files/a.txt", os.path.join("files", "a.txt"), "downloaded",
             _sha(blob), _sha(blob)),
        ],
    )
    conn.commit()
    conn.close()
    return db_path, site_dir


@pytest.fixture(autouse=True)
def _idle_between_tests():
    """Fail loudly if a test leaves a job running, which would poison the next."""
    yield
    _settle()
    assert not preservation.get_status()["running"]


def _settle(timeout: float = SETTLE_TIMEOUT_S) -> dict:
    """Block until no job is running, then return the final status."""
    deadline = time.time() + timeout
    while preservation.get_status()["running"] and time.time() < deadline:
        time.sleep(0.05)
    return preservation.get_status()


# ── Job lifecycle ─────────────────────────────────────────────────────────────

def test_verify_job_runs_and_reports(mirror, tmp_path, monkeypatch):
    """A verify job reaches stage=done with a populated result payload."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")

    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    status = _settle()

    assert status["stage"] == "done"
    assert status["job"] == "verify"
    assert status["result"]["rows"] == 2
    assert status["result"]["ok"] == 2
    assert status["result"]["drift"] == 0
    assert status["result"]["failed"] is False
    assert status["result"]["cancelled"] is False
    assert status["started_at"] and status["finished_at"]
    assert Path(status["report"]).exists()


def test_verify_job_reports_drift(mirror, tmp_path, monkeypatch):
    """A tampered file makes the job's result report drift and failed=True."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")
    (site_dir / "files" / "a.txt").write_bytes(b"tampered")

    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    status = _settle()

    assert status["stage"] == "done"
    assert status["result"]["drift"] == 1
    assert status["result"]["failed"] is True
    assert any("drift" in line for line in status["result"]["issues"])


def test_baseline_job_writes_local_sha(tmp_path, monkeypatch):
    """A baseline job fills local_sha256 for rows that lack one."""
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_bytes(b"<html>on disk</html>")

    db_path = tmp_path / "b.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE site_inventory (
        url TEXT PRIMARY KEY, relative_path TEXT, content_type TEXT,
        status TEXT NOT NULL DEFAULT 'pending', body_sha256 TEXT,
        local_sha256 TEXT, size_bytes INTEGER
    )""")
    conn.execute(
        "INSERT INTO site_inventory(url, relative_path, status, body_sha256) VALUES (?,?,?,?)",
        (f"{BASE}/index.html", "index.html", "downloaded", _sha(b"<html>raw</html>")),
    )
    conn.commit()
    conn.close()

    preservation.start_job("baseline", db_path=str(db_path), site_dir=str(site_dir))
    status = _settle()

    assert status["stage"] == "done"
    assert status["result"]["baselined"] == 1
    conn = sqlite3.connect(db_path)
    stored = conn.execute("SELECT local_sha256 FROM site_inventory").fetchone()[0]
    conn.close()
    assert stored == _sha(b"<html>on disk</html>")


def test_second_job_is_rejected_while_running(mirror, tmp_path, monkeypatch):
    """The single-instance guard raises rather than running two jobs at once."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")

    slow = _slow_verify(rows=400, delay=0.004)
    monkeypatch.setattr(vsm, "verify", slow)

    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    try:
        with pytest.raises(RuntimeError, match="already running"):
            preservation.start_job("linkcheck", site_dir=str(site_dir))
    finally:
        preservation.request_stop()
        _settle()


def test_unknown_job_rejected():
    """An unrecognised job name raises ValueError and leaves the state idle."""
    with pytest.raises(ValueError, match="unknown preservation job"):
        preservation.start_job("nonsense")
    assert preservation.get_status()["running"] is False


def test_job_failure_surfaces_as_error(mirror, tmp_path, monkeypatch):
    """An exception inside a job ends as stage=error, not a stuck 'running'."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")

    def boom(*_a, **_kw):
        raise OSError("disk went away")

    monkeypatch.setattr(vsm, "verify", boom)
    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    status = _settle()

    assert status["stage"] == "error"
    assert "disk went away" in status["error"]
    assert status["running"] is False


# ── Cancellation ──────────────────────────────────────────────────────────────

def _slow_verify(rows: int, delay: float):
    """Return a stand-in vsm.verify that ticks progress slowly and honours stop."""
    def _verify(db_path=None, site_dir=None, progress_cb=None, should_stop=None):
        res = vsm.Result(mode="verify", rows=rows)
        for i in range(1, rows + 1):
            time.sleep(delay)
            if progress_cb is not None:
                progress_cb(i, rows)
            if should_stop is not None and should_stop():
                res.cancelled = True
                res.checked = i
                return res
            res.checked = i
            res.ok = i
        return res
    return _verify


def test_request_stop_cancels_a_running_job(mirror, tmp_path, monkeypatch):
    """request_stop ends the run early and marks the result cancelled."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(vsm, "verify", _slow_verify(rows=2000, delay=0.002))

    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    deadline = time.time() + 5
    while preservation.get_status()["done"] < 5 and time.time() < deadline:
        time.sleep(0.01)

    assert preservation.request_stop() is True
    status = _settle()

    assert status["stage"] == "cancelled"
    assert status["result"]["cancelled"] is True
    assert status["result"]["checked"] < 2000


def test_request_stop_when_idle_is_a_noop():
    """Stopping with nothing running reports False instead of raising."""
    assert preservation.request_stop() is False


def test_progress_is_reported_during_a_run(mirror, tmp_path, monkeypatch):
    """The status carries done/total counters while a job is in flight."""
    db_path, site_dir = mirror
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(vsm, "verify", _slow_verify(rows=500, delay=0.004))

    preservation.start_job("verify", db_path=str(db_path), site_dir=str(site_dir))
    seen_total = 0
    deadline = time.time() + 5
    while time.time() < deadline:
        st = preservation.get_status()
        if st["total"]:
            seen_total = st["total"]
            break
        time.sleep(0.01)
    preservation.request_stop()
    _settle()

    assert seen_total == 500


# ── Tool-level hooks stay back-compatible ─────────────────────────────────────

def test_verify_without_hooks_still_works(mirror):
    """The new keyword args are optional — CLI callers pass none of them."""
    db_path, site_dir = mirror
    res = vsm.verify(db_path, site_dir)
    assert res.rows == 2
    assert res.cancelled is False


def test_check_links_progress_and_cancel(tmp_path):
    """check_links reports per-page progress and honours should_stop."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    for i in range(12):
        (site_dir / f"p{i}.html").write_text("<html><a href='p0.html'>x</a></html>")

    seen: list[tuple[int, int]] = []
    res = cml.check_links(site_dir, full=True, progress_cb=lambda d, t: seen.append((d, t)))
    assert seen and seen[-1][0] == seen[-1][1]
    assert res.cancelled is False

    stop_after = {"n": 0}

    def should_stop() -> bool:
        stop_after["n"] += 1
        return stop_after["n"] >= 3

    cancelled = cml.check_links(site_dir, full=True, should_stop=should_stop)
    assert cancelled.cancelled is True
    assert "CANCELLED" in cancelled.summary()
    assert cancelled.pages < 12


def test_snapshot_cancel_removes_partial_directory(tmp_path):
    """A cancelled snapshot deletes its half-built directory — no unsealed trees."""
    src = tmp_path / "payload"
    src.mkdir()
    (src / "f.txt").write_text("data")
    root = tmp_path / "snapshots"

    res = mss.make_snapshot(root=root, payload=[(src, "site")], with_db=False,
                            verify_first=False, should_stop=lambda: True)

    assert res.cancelled is True
    assert "CANCELLED" in res.summary()
    assert not res.path.exists()
    assert list(root.iterdir()) == []


def test_snapshot_progress_stages_are_announced(tmp_path):
    """make_snapshot names each build stage through progress_cb."""
    src = tmp_path / "payload"
    src.mkdir()
    (src / "f.txt").write_text("data")

    stages: list[str] = []
    res = mss.make_snapshot(root=tmp_path / "snapshots", payload=[(src, "site")],
                            with_db=False, verify_first=False,
                            progress_cb=stages.append)

    assert res.cancelled is False
    assert "stage:site" in stages
    assert "manifest" in stages and "seal" in stages and "done" in stages


# ── Inventory + report reading ────────────────────────────────────────────────

def test_list_snapshots_reads_manifest_without_rehashing(tmp_path):
    """Snapshot listing reports manifest stats and the seal for a built snapshot."""
    src = tmp_path / "payload"
    src.mkdir()
    (src / "a.txt").write_text("aaa")
    (src / "b.txt").write_text("bbbb")
    root = tmp_path / "snapshots"

    built = mss.make_snapshot(root=root, payload=[(src, "site")], with_db=False,
                             verify_first=False)

    rows = preservation.list_snapshots(root)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == built.path.name
    assert row["files"] == built.files
    assert row["size_bytes"] == built.size_bytes
    assert row["seal"] == built.seal
    assert row["sealed"] is True
    assert row["has_tar"] is False


def test_list_snapshots_tolerates_unsealed_directory(tmp_path):
    """A half-built directory is listed as unsealed rather than crashing."""
    root = tmp_path / "snapshots"
    (root / "lbsnap-2026-01-01").mkdir(parents=True)

    rows = preservation.list_snapshots(root)
    assert len(rows) == 1
    assert rows[0]["sealed"] is False
    assert rows[0]["files"] == 0


def test_list_snapshots_on_missing_root(tmp_path):
    """A missing snapshot root lists as empty, not an error."""
    assert preservation.list_snapshots(tmp_path / "nope") == []


def test_last_reports_classifies_and_orders(tmp_path, monkeypatch):
    """Reports are classified by kind and returned newest first."""
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path)
    older = tmp_path / "site_mirror_verify_2026-01-01_000000.txt"
    newer = tmp_path / "site_mirror_links_2026-01-02_000000.txt"
    older.write_text("old")
    newer.write_text("new")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    rows = preservation.last_reports(tmp_path)
    assert [r["kind"] for r in rows] == ["links", "verify"]


def test_read_report_rejects_paths_outside_exports(tmp_path, monkeypatch):
    """A path outside data/exports/ is refused — no directory traversal."""
    monkeypatch.setattr(preservation, "EXPORTS_DIR", tmp_path / "exports")
    (tmp_path / "exports").mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")

    with pytest.raises(ValueError, match="outside the exports directory"):
        preservation.read_report(outside)


def test_read_report_truncates_oversized_reports(tmp_path, monkeypatch):
    """An oversized report comes back truncated with a marker."""
    exports = tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setattr(preservation, "EXPORTS_DIR", exports)
    report = exports / "site_mirror_verify_big.txt"
    report.write_text("x" * 5000)

    text = preservation.read_report(report, max_bytes=1000)
    assert len(text) < 5000
    assert "truncated" in text
