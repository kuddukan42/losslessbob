#!/usr/bin/env python3
"""verify_site_mirror.py — integrity check for the losslessbob.com site mirror.

Preservation stack B1 (instructions/FABLE_PRESERVATION_STACK.md §D1). An
unverified backup is a hope: this re-hashes every mirrored file and reports
missing files, hash drift, orphaned files and rows that have no baseline yet.

**Hash provenance — the trap this tool exists to avoid.** ``site_inventory.
body_sha256`` is the sha256 of the RAW HTTP body, but HTML pages are saved
link-rewritten and re-encoded (``backend/site_crawler.py`` ``_save``), so their
on-disk bytes can NEVER match it. Re-hashing HTML against ``body_sha256`` would
report ~100k false drift errors. ``local_sha256`` records the bytes as saved and
is the only sound baseline for HTML.

Usage::

    # One-time: record an on-disk baseline for rows that lack one.
    python tools/verify_site_mirror.py --baseline

    # Routine: verify the mirror against the baseline (read-only).
    python tools/verify_site_mirror.py
    python tools/verify_site_mirror.py --report

Exit code is non-zero if any missing file, drift or verbatim-hash mismatch was
found. Safe to run while the app is up: read-only apart from the ``--baseline``
column write.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so ``from backend...`` works when this
# script is run directly (e.g. python tools/verify_site_mirror.py).
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.paths import DATA_DIR, DB_PATH, SITE_DIR  # noqa: E402
from backend.site_crawler import is_rewritten_html  # noqa: E402

log = logging.getLogger("verify_site_mirror")

# ── Constants ─────────────────────────────────────────────────────────────────

EXPORTS_DIR = DATA_DIR / "exports"
HASH_CHUNK_BYTES = 1024 * 1024
WRITE_CHUNK_ROWS = 1000
PROGRESS_EVERY = 10000
BUSY_TIMEOUT_MS = 30000

# Issue kinds
KIND_MISSING = "missing"
KIND_DRIFT = "drift"
KIND_ORPHAN = "orphan"
KIND_PREHASH = "prehash-mismatch"

# Kinds that make the run fail
FAILING_KINDS = (KIND_MISSING, KIND_DRIFT, KIND_PREHASH)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class Issue:
    """A single problem found with the mirror.

    Attributes:
        kind: One of the ``KIND_*`` constants.
        target: URL for inventory-row issues, relative path for orphans.
        detail: Human-readable explanation, already single-line.
    """

    kind: str
    target: str
    detail: str

    def line(self) -> str:
        """Return the single-line report representation of this issue."""
        return f"{self.kind:<16} {self.target}  {self.detail}"


@dataclass
class Result:
    """Outcome of a verify or baseline run.

    Attributes:
        mode: ``"verify"`` or ``"baseline"``.
        rows: Number of inventory rows considered.
        checked: Number of files actually hashed.
        ok: Number of files whose hash matched the expected baseline.
        baselined: Number of rows given a ``local_sha256`` (baseline mode only).
        unbaselined: Rows still without a usable baseline after the run.
        issues: Every problem found, in discovery order.
        seconds: Wall-clock duration.
    """

    mode: str
    rows: int = 0
    checked: int = 0
    ok: int = 0
    baselined: int = 0
    unbaselined: int = 0
    issues: list[Issue] = field(default_factory=list)
    seconds: float = 0.0

    def count(self, kind: str) -> int:
        """Return the number of issues of *kind*."""
        return sum(1 for i in self.issues if i.kind == kind)

    @property
    def failed(self) -> bool:
        """True if the run found a problem that should fail the exit code."""
        return any(i.kind in FAILING_KINDS for i in self.issues)

    def summary(self) -> str:
        """Return the single-line summary for the CLI and report file."""
        parts = [
            f"{self.mode}: {self.rows} rows",
            f"hashed {self.checked}",
        ]
        if self.mode == "baseline":
            parts.append(f"baselined {self.baselined}")
        else:
            parts.append(f"ok {self.ok}")
        parts += [
            f"missing {self.count(KIND_MISSING)}",
            f"drift {self.count(KIND_DRIFT)}",
            f"prehash-mismatch {self.count(KIND_PREHASH)}",
            f"orphans {self.count(KIND_ORPHAN)}",
            f"unbaselined {self.unbaselined}",
            f"{self.seconds:.1f}s",
        ]
        return " | ".join(parts)


# ── Hashing / DB helpers ──────────────────────────────────────────────────────

def hash_file(path: Path) -> str:
    """Return the sha256 hex digest of *path*, read in chunks.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the DB with a busy timeout so the running app can hold the writer.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        Connection with ``sqlite3.Row`` row factory.
    """
    conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def _downloaded_rows(conn: sqlite3.Connection, only_unbaselined: bool = False,
                     limit: int | None = None) -> list[sqlite3.Row]:
    """Fetch ``status='downloaded'`` inventory rows.

    Args:
        conn: Open connection.
        only_unbaselined: Restrict to rows whose ``local_sha256`` is NULL.
        limit: Optional row cap (useful for partial baseline runs).

    Returns:
        List of rows ordered by URL for stable, resumable output.
    """
    sql = ("SELECT url, relative_path, body_sha256, local_sha256 "
           "FROM site_inventory WHERE status='downloaded'")
    if only_unbaselined:
        sql += " AND local_sha256 IS NULL"
    sql += " ORDER BY url"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _resolve(site_dir: Path, row: sqlite3.Row) -> Path | None:
    """Return the on-disk path for an inventory row, or None if it has none."""
    rel = row["relative_path"]
    if not rel:
        return None
    return site_dir / rel


def _apply_baseline(db_path: Path | str, updates: list[tuple[str, str]]) -> None:
    """Write ``local_sha256`` values, committing in chunks.

    Chunked so a 110k-row baseline never holds the single SQLite writer for the
    whole run while the app is live.

    Args:
        db_path: Path to the SQLite database.
        updates: ``(local_sha256, url)`` pairs.
    """
    if not updates:
        return
    conn = _connect(db_path)
    try:
        for start in range(0, len(updates), WRITE_CHUNK_ROWS):
            chunk = updates[start:start + WRITE_CHUNK_ROWS]
            conn.executemany(
                "UPDATE site_inventory SET local_sha256=? WHERE url=?", chunk
            )
            conn.commit()
    finally:
        conn.close()


# ── Core passes ───────────────────────────────────────────────────────────────

def find_orphans(conn: sqlite3.Connection, site_dir: Path) -> list[Issue]:
    """Return files under *site_dir* that no inventory row claims.

    Args:
        conn: Open connection.
        site_dir: Root of the mirror.

    Returns:
        One :class:`Issue` per orphaned file, sorted by path.
    """
    if not site_dir.exists():
        return []
    known = {
        r["relative_path"]
        for r in conn.execute(
            "SELECT relative_path FROM site_inventory WHERE relative_path IS NOT NULL"
        )
    }
    issues: list[Issue] = []
    for path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(site_dir))
        if rel not in known:
            issues.append(Issue(KIND_ORPHAN, rel, "file on disk with no inventory row"))
    return issues


def baseline(db_path: Path | str | None = None, site_dir: Path | None = None,
             limit: int | None = None) -> Result:
    """Record an on-disk ``local_sha256`` for downloaded rows that lack one.

    This TRUSTS the current mirror state — for already-rewritten HTML nothing
    better exists. For verbatim (non-HTML) files the on-disk hash *must* equal
    ``body_sha256``; mismatches are pre-existing rot candidates, so they are
    reported and deliberately NOT baselined, which keeps them surfacing as drift
    on every later verify run instead of blessing the damaged bytes.

    Args:
        db_path: Database path; defaults to the app DB.
        site_dir: Mirror root; defaults to ``data/site/``.
        limit: Optional cap on rows processed, for partial runs.

    Returns:
        A :class:`Result` in ``"baseline"`` mode.
    """
    db_path = Path(db_path or DB_PATH)
    site_dir = Path(site_dir or SITE_DIR)
    started = time.time()
    res = Result(mode="baseline")

    conn = _connect(db_path)
    try:
        rows = _downloaded_rows(conn, only_unbaselined=True, limit=limit)
        res.rows = len(rows)
        updates: list[tuple[str, str]] = []
        for idx, row in enumerate(rows, 1):
            if idx % PROGRESS_EVERY == 0:
                log.info("baseline: %d/%d rows hashed…", idx, res.rows)
            path = _resolve(site_dir, row)
            if path is None:
                res.issues.append(Issue(KIND_MISSING, row["url"], "no relative_path recorded"))
                continue
            if not path.exists():
                res.issues.append(
                    Issue(KIND_MISSING, row["url"], f"file absent: {row['relative_path']}")
                )
                continue
            actual = hash_file(path)
            res.checked += 1
            if not is_rewritten_html(row["url"]) and row["body_sha256"] \
                    and actual != row["body_sha256"]:
                res.issues.append(Issue(
                    KIND_PREHASH, row["url"],
                    f"verbatim file != body_sha256 (raw {row['body_sha256'][:12]}, "
                    f"disk {actual[:12]}) — not baselined",
                ))
                continue
            updates.append((actual, row["url"]))
        _apply_baseline(db_path, updates)
        res.baselined = len(updates)
        res.unbaselined = _count_unbaselined(conn)
    finally:
        conn.close()

    res.seconds = time.time() - started
    return res


def verify(db_path: Path | str | None = None, site_dir: Path | None = None) -> Result:
    """Re-hash the mirror and report missing files, drift and orphans.

    Read-only. Each downloaded row is compared against ``local_sha256``; rows
    with no baseline yet fall back to ``body_sha256`` but ONLY when the file is
    stored verbatim — HTML without a baseline is counted as unbaselined rather
    than compared, because its on-disk bytes legitimately differ from the raw
    body (see module docstring).

    Args:
        db_path: Database path; defaults to the app DB.
        site_dir: Mirror root; defaults to ``data/site/``.

    Returns:
        A :class:`Result` in ``"verify"`` mode.
    """
    db_path = Path(db_path or DB_PATH)
    site_dir = Path(site_dir or SITE_DIR)
    started = time.time()
    res = Result(mode="verify")

    conn = _connect(db_path)
    try:
        rows = _downloaded_rows(conn)
        res.rows = len(rows)
        for idx, row in enumerate(rows, 1):
            if idx % PROGRESS_EVERY == 0:
                log.info("verify: %d/%d rows checked…", idx, res.rows)
            path = _resolve(site_dir, row)
            if path is None:
                res.issues.append(Issue(KIND_MISSING, row["url"], "no relative_path recorded"))
                continue
            if not path.exists():
                res.issues.append(
                    Issue(KIND_MISSING, row["url"], f"file absent: {row['relative_path']}")
                )
                continue
            expected = row["local_sha256"]
            source = "local_sha256"
            if not expected:
                if is_rewritten_html(row["url"]):
                    res.unbaselined += 1
                    continue
                expected = row["body_sha256"]
                source = "body_sha256"
            if not expected:
                res.unbaselined += 1
                continue
            actual = hash_file(path)
            res.checked += 1
            if actual == expected:
                res.ok += 1
            else:
                res.issues.append(Issue(
                    KIND_DRIFT, row["url"],
                    f"{source} {expected[:12]} != disk {actual[:12]} ({row['relative_path']})",
                ))
        res.issues.extend(find_orphans(conn, site_dir))
    finally:
        conn.close()

    res.seconds = time.time() - started
    return res


def _count_unbaselined(conn: sqlite3.Connection) -> int:
    """Return how many downloaded rows still have no ``local_sha256``."""
    return conn.execute(
        "SELECT COUNT(*) FROM site_inventory "
        "WHERE status='downloaded' AND local_sha256 IS NULL"
    ).fetchone()[0]


# ── Reporting / CLI ───────────────────────────────────────────────────────────

def write_report(res: Result, exports_dir: Path | None = None) -> Path:
    """Write the issue lines plus summary to a dated file.

    Args:
        res: Completed run result.
        exports_dir: Destination directory; defaults to ``data/exports/``.

    Returns:
        Path of the written report.
    """
    exports_dir = Path(exports_dir or EXPORTS_DIR)
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = exports_dir / f"site_mirror_{res.mode}_{stamp}.txt"
    lines = [f"# site mirror {res.mode} — {datetime.now().isoformat(timespec='seconds')}"]
    lines += [i.line() for i in res.issues]
    lines.append(res.summary())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Verify the losslessbob.com site mirror against recorded hashes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--baseline", action="store_true",
                        help="record local_sha256 for downloaded rows that lack one")
    parser.add_argument("--report", action="store_true",
                        help="also write the report to data/exports/")
    parser.add_argument("--db", default=None, help="database path (default: the app DB)")
    parser.add_argument("--site-dir", default=None,
                        help="mirror root (default: data/site/)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap rows processed (baseline mode only)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code — non-zero if missing files or drift were found.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db_path = Path(args.db) if args.db else Path(DB_PATH)
    site_dir = Path(args.site_dir) if args.site_dir else Path(SITE_DIR)

    if args.baseline:
        res = baseline(db_path, site_dir, limit=args.limit)
    else:
        res = verify(db_path, site_dir)

    for issue in res.issues:
        log.info("%s", issue.line())
    log.info("%s", res.summary())
    if args.report:
        log.info("report: %s", write_report(res))
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
