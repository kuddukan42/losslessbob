"""Preservation-stack service layer — GUI-facing wrapper around the TODO-265 tools.

The preservation stack ships as three standalone CLI tools
(``tools/verify_site_mirror.py``, ``tools/make_site_snapshot.py``,
``tools/check_mirror_links.py``). They are the authority on *what* each
operation does; this module adds only what a GUI needs on top:

* **Single-instance job running.** All four jobs hash or hardlink large parts of
  the mirror, so exactly one may run at a time — process-wide, the same rule the
  site crawler follows.
* **Progress + cancellation.** Jobs run on a daemon thread and report through
  the tools' ``progress_cb``/``should_stop`` hooks, so the frontend can draw a
  real progress bar and offer a Stop button.
* **A pollable status snapshot** shaped like ``site_crawler.get_crawler_status``,
  which the Scraper screen already knows how to diff into log lines.

Every job is read-only against the collection except ``baseline``, which writes
the ``site_inventory.local_sha256`` column, and ``snapshot``, which writes a new
directory under ``data/exports/snapshots/``. Nothing here uploads or publishes:
distribution of a snapshot stays a deliberate human act (see PROJECT.md,
"Preservation stack").
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.paths import DATA_DIR, SITE_DIR
from tools import check_mirror_links as cml
from tools import make_site_snapshot as mss
from tools import verify_site_mirror as vsm

log = logging.getLogger(__name__)

EXPORTS_DIR = DATA_DIR / "exports"
SNAPSHOT_ROOT = EXPORTS_DIR / "snapshots"

#: Jobs this service can run, in the order the UI presents them.
JOBS = ("verify", "baseline", "linkcheck", "snapshot")

#: Manifest lines are ``sha256␠␠size␠␠relpath``; only the size is read back.
_MANIFEST_FIELDS = 3

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_requested = False

_state: dict[str, Any] = {
    "running": False,
    "job": None,
    "stage": "idle",
    "message": "",
    "done": 0,
    "total": 0,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
    "report": None,
}


# ── Status ────────────────────────────────────────────────────────────────────

def get_status() -> dict[str, Any]:
    """Return a snapshot of the current job state.

    Safe to poll frequently; it copies the shared state under the lock and does
    no filesystem work.

    Returns:
        A JSON-serialisable dict with ``running``, ``job``, ``stage``
        (``idle``/``running``/``done``/``error``/``cancelled``), ``message``,
        ``done``/``total`` progress counters, timestamps, and — once a run
        finishes — a job-specific ``result`` dict or an ``error`` string.
    """
    with _lock:
        return dict(_state)


def _set(**fields: Any) -> None:
    """Merge *fields* into the shared state under the lock."""
    with _lock:
        _state.update(fields)


def _should_stop() -> bool:
    """Return True once a stop has been requested for the running job."""
    with _lock:
        return _stop_requested


def request_stop() -> bool:
    """Ask the running job to stop at its next checkpoint.

    Cancellation is cooperative: verify and baseline stop between rows, the link
    check between pages, and a snapshot between build stages (deleting its
    partial directory, since only a sealed snapshot is meaningful).

    Returns:
        True if a job was running and has been asked to stop, False if idle.
    """
    global _stop_requested
    with _lock:
        if not _state["running"]:
            return False
        _stop_requested = True
        _state["message"] = "stopping…"
    log.info("preservation: stop requested for job %s", _state.get("job"))
    return True


# ── Job runners ───────────────────────────────────────────────────────────────

def _progress(done: int, total: int) -> None:
    """Record row/page progress from a tool's ``progress_cb``."""
    _set(done=done, total=total,
         message=f"{done:,} / {total:,}" if total else f"{done:,}")


def _issue_lines(issues: list[vsm.Issue], limit: int) -> list[str]:
    """Return at most *limit* rendered issue lines, worst kinds first."""
    ordered = sorted(issues, key=lambda i: i.kind not in vsm.FAILING_KINDS)
    return [i.line() for i in ordered[:limit]]


def _run_verify(db_path: str | None, site_dir: str | None,
                issue_limit: int, **_: Any) -> dict[str, Any]:
    """Re-hash the mirror against its baselines and report problems."""
    res = vsm.verify(db_path, Path(site_dir) if site_dir else None,
                     progress_cb=_progress, should_stop=_should_stop)
    report = vsm.write_report(res, EXPORTS_DIR)
    _set(report=str(report))
    return {
        "mode": res.mode,
        "summary": res.summary(),
        "rows": res.rows,
        "checked": res.checked,
        "ok": res.ok,
        "unbaselined": res.unbaselined,
        "missing": res.count(vsm.KIND_MISSING),
        "drift": res.count(vsm.KIND_DRIFT),
        "prehash_mismatch": res.count(vsm.KIND_PREHASH),
        "orphans": res.count(vsm.KIND_ORPHAN),
        "issues": _issue_lines(res.issues, issue_limit),
        "issue_total": len(res.issues),
        "failed": res.failed,
        "cancelled": res.cancelled,
        "seconds": round(res.seconds, 1),
    }


def _run_baseline(db_path: str | None, site_dir: str | None,
                  issue_limit: int, limit: int | None = None,
                  **_: Any) -> dict[str, Any]:
    """Record ``local_sha256`` for downloaded rows that lack one."""
    res = vsm.baseline(db_path, Path(site_dir) if site_dir else None, limit=limit,
                       progress_cb=_progress, should_stop=_should_stop)
    report = vsm.write_report(res, EXPORTS_DIR)
    _set(report=str(report))
    return {
        "mode": res.mode,
        "summary": res.summary(),
        "rows": res.rows,
        "checked": res.checked,
        "baselined": res.baselined,
        "unbaselined": res.unbaselined,
        "missing": res.count(vsm.KIND_MISSING),
        "prehash_mismatch": res.count(vsm.KIND_PREHASH),
        "issues": _issue_lines(res.issues, issue_limit),
        "issue_total": len(res.issues),
        "failed": res.failed,
        "cancelled": res.cancelled,
        "seconds": round(res.seconds, 1),
    }


def _run_linkcheck(site_dir: str | None, issue_limit: int, full: bool = False,
                   sample_size: int = cml.SAMPLE_SIZE, **_: Any) -> dict[str, Any]:
    """Resolve internal links against files on disk — the restore test."""
    res = cml.check_links(Path(site_dir) if site_dir else None, full=full,
                          sample_size=sample_size,
                          progress_cb=_progress, should_stop=_should_stop)
    report = cml.write_report(res, EXPORTS_DIR)
    _set(report=str(report))
    return {
        "summary": res.summary(),
        "pages": res.pages,
        "links": res.links,
        "skipped": res.skipped,
        "broken": len(res.broken),
        "seed_broken": len(res.seed_broken),
        "seed_pages_checked": res.seed_pages_checked,
        "seed_pages_total": len(cml.SEED_PAGES),
        "missing_seeds": list(res.missing_seeds),
        "issues": [b.line() for b in (res.seed_broken + res.broken)[:issue_limit]],
        "issue_total": len(res.broken),
        "failed": bool(res.seed_broken or res.missing_seeds),
        "cancelled": res.cancelled,
        "seconds": round(res.seconds, 1),
    }


def _run_snapshot(db_path: str | None, site_dir: str | None, with_db: bool = True,
                  verify_first: bool = True, tar: bool = False,
                  **_: Any) -> dict[str, Any]:
    """Build a sealed, hardlinked snapshot of the mirrors plus a DB export."""
    def stage_cb(name: str) -> None:
        """Surface the current build stage as the status message."""
        _set(message=name)

    res = mss.make_snapshot(db_path=db_path,
                            site_dir=Path(site_dir) if site_dir else None,
                            with_db=with_db, verify_first=verify_first, tar=tar,
                            progress_cb=stage_cb, should_stop=_should_stop)
    return {
        "summary": res.summary(),
        "path": str(res.path),
        "name": res.path.name,
        "files": res.files,
        "size_bytes": res.size_bytes,
        "linked": res.linked,
        "copied": res.copied,
        "seal": res.seal,
        "tar_path": str(res.tar_path) if res.tar_path else None,
        "counts": dict(res.counts),
        "verify_summary": res.verify.summary() if res.verify else None,
        "cancelled": res.cancelled,
        "seconds": round(res.seconds, 1),
    }


_RUNNERS = {
    "verify": _run_verify,
    "baseline": _run_baseline,
    "linkcheck": _run_linkcheck,
    "snapshot": _run_snapshot,
}


def _worker(job: str, opts: dict[str, Any]) -> None:
    """Run *job* to completion and record its outcome in the shared state."""
    global _stop_requested
    try:
        result = _RUNNERS[job](**opts)
        cancelled = bool(result.get("cancelled"))
        _set(stage="cancelled" if cancelled else "done",
             result=result,
             message=result.get("summary", ""))
        log.info("preservation %s finished: %s", job, result.get("summary", ""))
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI, not swallowed
        log.exception("preservation %s failed", job)
        _set(stage="error", error=str(exc), message=f"error: {exc}")
    finally:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _stop_requested = False


def start_job(job: str, db_path: str | None = None, site_dir: str | None = None,
              issue_limit: int = 200, **opts: Any) -> None:
    """Start *job* on a background daemon thread.

    Args:
        job: One of :data:`JOBS`.
        db_path: Database override; defaults to the app DB.
        site_dir: Mirror-root override; defaults to ``data/site/``.
        issue_limit: Max issue lines carried back in the result, so a mirror
            with thousands of problems cannot bloat the status payload.
        **opts: Job-specific options — ``limit`` (baseline), ``full`` /
            ``sample_size`` (linkcheck), ``with_db`` / ``verify_first`` / ``tar``
            (snapshot).

    Raises:
        ValueError: If *job* is not a known job name.
        RuntimeError: If another preservation job is already running.
    """
    global _thread, _stop_requested
    if job not in _RUNNERS:
        raise ValueError(f"unknown preservation job: {job}")

    with _lock:
        if _state["running"]:
            raise RuntimeError(f"preservation job already running: {_state['job']}")
        _stop_requested = False
        _state.update(
            running=True, job=job, stage="running", message="starting…",
            done=0, total=0, result=None, error=None, report=None,
            started_at=datetime.now().isoformat(timespec="seconds"),
            finished_at=None,
        )

    kwargs = {"db_path": db_path, "site_dir": site_dir, "issue_limit": issue_limit, **opts}
    _thread = threading.Thread(target=_worker, args=(job, kwargs),
                               name=f"preservation-{job}", daemon=True)
    _thread.start()
    log.info("preservation %s started (%s)", job, opts or "defaults")


# ── Snapshot inventory ────────────────────────────────────────────────────────

def _read_manifest_stats(snap_dir: Path) -> tuple[int, int]:
    """Return ``(file_count, total_bytes)`` from a snapshot's manifest.

    Args:
        snap_dir: Snapshot directory.

    Returns:
        ``(0, 0)`` if the manifest is absent or unreadable — an unsealed or
        half-built directory should be listed, not crash the listing.
    """
    manifest = snap_dir / mss.MANIFEST_NAME
    files = total = 0
    try:
        with manifest.open("r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("  ", _MANIFEST_FIELDS - 1)
                if len(parts) < _MANIFEST_FIELDS:
                    continue
                files += 1
                try:
                    total += int(parts[1])
                except ValueError:
                    continue
    except OSError:
        return 0, 0
    return files, total


def list_snapshots(root: Path | None = None) -> list[dict[str, Any]]:
    """List sealed snapshots on disk, newest first.

    Reads each snapshot's ``manifest.txt`` and ``seal.txt``; nothing is
    re-hashed, so this stays fast enough for an on-demand UI fetch. Verifying a
    snapshot is the recipient's job, via the ``verify_snapshot.py`` it carries.

    Args:
        root: Snapshot root; defaults to ``data/exports/snapshots/``.

    Returns:
        One dict per snapshot directory with its name, path, mtime, manifest
        stats, seal digest, and whether a tarball sits alongside it.
    """
    root = Path(root or SNAPSHOT_ROOT)
    if not root.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for snap_dir in sorted(root.iterdir(), reverse=True):
        if not snap_dir.is_dir():
            continue
        seal_path = snap_dir / mss.SEAL_NAME
        try:
            seal = seal_path.read_text(encoding="utf-8").strip().split()[0]
        except (OSError, IndexError):
            seal = ""
        files, size_bytes = _read_manifest_stats(snap_dir)
        tar_path = snap_dir.with_suffix(".tar.gz")
        try:
            mtime = snap_dir.stat().st_mtime
        except OSError:
            mtime = 0.0
        out.append({
            "name": snap_dir.name,
            "path": str(snap_dir),
            "created": datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            if mtime else None,
            "files": files,
            "size_bytes": size_bytes,
            "seal": seal,
            "sealed": bool(seal),
            "has_tar": tar_path.exists(),
            "tar_path": str(tar_path) if tar_path.exists() else None,
        })
    return out


def mirror_stats(site_dir: Path | None = None) -> dict[str, Any]:
    """Return at-a-glance mirror figures for the tab header.

    Args:
        site_dir: Mirror root; defaults to ``data/site/``.

    Returns:
        A dict with the mirror path, whether it exists, the snapshot count, and
        the newest snapshot's name — cheap enough to serve on every poll.
    """
    site_dir = Path(site_dir or SITE_DIR)
    snaps = list_snapshots()
    return {
        "site_dir": str(site_dir),
        "site_dir_exists": site_dir.is_dir(),
        "snapshot_root": str(SNAPSHOT_ROOT),
        "snapshots": len(snaps),
        "latest_snapshot": snaps[0]["name"] if snaps else None,
        "latest_snapshot_at": snaps[0]["created"] if snaps else None,
        "serve_command": f"python3 -m http.server -d {site_dir} 8080",
    }


def last_reports(exports_dir: Path | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """List recent preservation report files, newest first.

    Args:
        exports_dir: Report directory; defaults to ``data/exports/``.
        limit: Max reports to return.

    Returns:
        One dict per report with its name, kind (``verify``/``baseline``/
        ``links``), path, size and mtime.
    """
    exports_dir = Path(exports_dir or EXPORTS_DIR)
    if not exports_dir.is_dir():
        return []
    kinds = {"site_mirror_verify_": "verify", "site_mirror_baseline_": "baseline",
             "site_mirror_links_": "links"}
    rows: list[tuple[float, dict[str, Any]]] = []
    for path in exports_dir.glob("site_mirror_*.txt"):
        kind = next((k for prefix, k in kinds.items() if path.name.startswith(prefix)), "other")
        try:
            st = path.stat()
        except OSError:
            continue
        rows.append((st.st_mtime, {
            "name": path.name,
            "kind": kind,
            "path": str(path),
            "size_bytes": st.st_size,
            "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [row for _, row in rows[:limit]]


def read_report(path: str | Path, max_bytes: int = 256_000) -> str:
    """Return the text of a preservation report, truncated if oversized.

    Only files inside ``data/exports/`` are readable — the path is resolved and
    checked, so a caller cannot walk out of the reports directory.

    Args:
        path: Report path, as handed out by :func:`last_reports`.
        max_bytes: Cap on returned characters.

    Returns:
        The report text, with a truncation marker appended if it was cut.

    Raises:
        ValueError: If *path* resolves outside ``data/exports/``.
        FileNotFoundError: If the report does not exist.
    """
    resolved = Path(path).resolve()
    exports = EXPORTS_DIR.resolve()
    if not resolved.is_relative_to(exports):
        raise ValueError("report path outside the exports directory")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_bytes:
        return text[:max_bytes] + f"\n… truncated at {max_bytes:,} characters\n"
    return text
