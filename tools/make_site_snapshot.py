#!/usr/bin/env python3
"""make_site_snapshot.py — build a sealed, self-verifying archive snapshot.

Preservation stack B2 (instructions/FABLE_PRESERVATION_STACK.md §D2). Produces
``data/exports/snapshots/lbsnap-YYYY-MM-DD[.N]/`` containing the site mirror,
the Olof/bobserve mirrors and a full-channel DB export, plus a BagIt-style
``manifest.txt``, a single ``seal.txt`` hash over that manifest, a ``README.txt``
and a standalone ``verify_snapshot.py`` a recipient can run with stock Python —
no repo, no dependencies.

Staging uses hardlinks when the destination is on the same filesystem, so a
snapshot of a 2.5 GB mirror costs almost no extra disk.

**This tool has no upload path and must never gain one.** The snapshot carries
full-channel data (private-entry metadata, friends-only tier); distribution is a
deliberate human act — copy it to drives and hand them to friends on different
continents. Publishing the mirror would need Jeff's blessing and is a different
decision entirely.

Usage::

    python tools/make_site_snapshot.py
    python tools/make_site_snapshot.py --tar
    python tools/make_site_snapshot.py --no-db          # mirrors only, no DB export

The build refuses to run if ``verify_site_mirror`` reports missing files or
drift — sealing a known-broken mirror would certify damage. ``--no-verify``
overrides that, loudly.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import sys
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so ``from backend...`` works when this
# script is run directly (e.g. python tools/make_site_snapshot.py).
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.paths import DATA_DIR, DB_PATH, SITE_DIR  # noqa: E402
from tools import verify_site_mirror as vsm  # noqa: E402

log = logging.getLogger("make_site_snapshot")

# ── Constants ─────────────────────────────────────────────────────────────────

SNAPSHOT_ROOT = DATA_DIR / "exports" / "snapshots"
OLOF_PAGES_DIR = DATA_DIR / "olof" / "pages"
OLOF_BOBSERVE_DIR = DATA_DIR / "olof" / "bobserve_pages"

MANIFEST_NAME = "manifest.txt"
SEAL_NAME = "seal.txt"
README_NAME = "README.txt"
VERIFIER_NAME = "verify_snapshot.py"

# README carries build timestamps, so it is excluded from the manifest to keep
# two builds of unchanged input byte-identical. manifest/seal cannot list
# themselves.
UNMANIFESTED = frozenset({MANIFEST_NAME, SEAL_NAME, README_NAME})

DB_SUBDIR = "db"
DB_NAME = "losslessbob_master.db"
HASH_CHUNK_BYTES = 1024 * 1024

# The embedded verifier is written verbatim into every snapshot. It must stay
# pure stdlib with zero repo imports — a recipient runs it with nothing else
# installed — and it uses print() deliberately, since it cannot assume any
# logging configuration exists.
VERIFIER_SOURCE = '''#!/usr/bin/env python3
"""verify_snapshot.py — check that this snapshot is intact.

Run it from inside the snapshot directory with any Python 3:

    python3 verify_snapshot.py

It re-hashes every file listed in manifest.txt, checks manifest.txt itself
against seal.txt, and exits non-zero if anything is missing or altered.
Requires nothing but the Python standard library.
"""
import hashlib
import sys
from pathlib import Path

MANIFEST = "manifest.txt"
SEAL = "seal.txt"
CHUNK = 1024 * 1024


def sha256_file(path):
    """Return the sha256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    """Verify the snapshot in this directory. Returns a process exit code."""
    root = Path(__file__).resolve().parent
    manifest = root / MANIFEST
    seal = root / SEAL
    if not manifest.exists():
        print("FAIL  manifest.txt is missing — this is not a complete snapshot")
        return 2

    problems = []
    if not seal.exists():
        problems.append("FAIL  seal.txt is missing — the manifest cannot be trusted")
    else:
        expected = seal.read_text(encoding="utf-8").split()[0].strip()
        actual = sha256_file(manifest)
        if actual != expected:
            problems.append(
                "FAIL  seal mismatch — manifest.txt has been altered "
                "(%s != %s)" % (actual[:12], expected[:12])
            )

    checked = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("  ", 2)
        if len(parts) != 3:
            problems.append("FAIL  unparseable manifest line: %s" % line)
            continue
        want_sha, want_size, rel = parts
        path = root / rel
        if not path.exists():
            problems.append("FAIL  missing   %s" % rel)
            continue
        if str(path.stat().st_size) != want_size:
            problems.append("FAIL  size      %s" % rel)
            continue
        if sha256_file(path) != want_sha:
            problems.append("FAIL  corrupt   %s" % rel)
            continue
        checked += 1

    for problem in problems:
        print(problem)
    print("verify_snapshot: %d file(s) verified, %d problem(s)" % (checked, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
'''

README_TEMPLATE = """LosslessBob archive snapshot
============================

Built:      {built}
Snapshot:   {name}
Contents:   {files} files, {size_h}

  site/                 mirror of losslessbob.com ({site_files} files)
  olof/pages/           Olof Bjorner DSN + chronicle pages ({olof_files} files)
  olof/bobserve_pages/  bobserve.com setlist pages ({bobserve_files} files)
  db/                   {db_line}

WHAT THIS IS
------------
A dated, sealed copy of the LosslessBob data so it cannot be lost. The site
mirror is browsable offline — its links are already rewritten to relative
paths, so serving the directory is enough:

    python3 -m http.server -d site 8080

The database carries the site's field-level change history, not just a copy of
its current state.

HOW TO CHECK IT IS INTACT
-------------------------
    python3 verify_snapshot.py

That re-hashes every file listed in manifest.txt and checks manifest.txt itself
against seal.txt. It needs nothing but a stock Python 3 — no repo, no installs.
A silent success means every byte is as it was on the build date.

PLEASE KEEP THIS PRIVATE
------------------------
This is a preservation copy for a handful of friends, deliberately spread
across different places so no single failure takes the data with it. It
includes private-entry metadata that is not on the public site. Keeping a dark
archive is preservation; publishing it is a different act that is not ours to
take unilaterally. Do not put it on a public URL.

Keeping it useful: a copy that is never checked is a hope, not a backup. Run
verify_snapshot.py occasionally, and ask for a fresher snapshot now and then.
"""


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class SnapshotResult:
    """Outcome of a snapshot build.

    Attributes:
        path: Snapshot directory.
        files: Number of files listed in the manifest.
        size_bytes: Total payload size.
        linked: Files staged as hardlinks.
        copied: Files staged by copying (cross-filesystem fallback).
        seal: sha256 of ``manifest.txt``.
        tar_path: Path of the tarball, if ``--tar`` was used.
        seconds: Wall-clock duration.
        verify: The pre-build mirror verification result, if one ran.
    """

    path: Path
    files: int = 0
    size_bytes: int = 0
    linked: int = 0
    copied: int = 0
    seal: str = ""
    tar_path: Path | None = None
    seconds: float = 0.0
    verify: vsm.Result | None = None
    counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Return the single-line summary for the CLI."""
        parts = [
            f"snapshot: {self.path.name}",
            f"{self.files} files",
            f"{_human(self.size_bytes)}",
            f"linked {self.linked}",
            f"copied {self.copied}",
            f"seal {self.seal[:12]}",
        ]
        if self.tar_path:
            parts.append(f"tar {_human(self.tar_path.stat().st_size)}")
        parts.append(f"{self.seconds:.1f}s")
        return " | ".join(parts)


def _human(size: int) -> str:
    """Return *size* in bytes as a short human-readable string."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}TB"


# ── Staging ───────────────────────────────────────────────────────────────────

def next_snapshot_dir(root: Path, today: str | None = None) -> Path:
    """Return an unused dated snapshot directory path.

    Args:
        root: Directory that holds snapshots.
        today: Date stamp override (``YYYY-MM-DD``); defaults to today.

    Returns:
        ``<root>/lbsnap-<date>`` or the first free ``.N`` variant.
    """
    stamp = today or datetime.now().strftime("%Y-%m-%d")
    candidate = root / f"lbsnap-{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = root / f"lbsnap-{stamp}.{suffix}"
        suffix += 1
    return candidate


def stage_tree(src: Path, dest: Path) -> tuple[int, int]:
    """Stage every file under *src* into *dest*, preferring hardlinks.

    Args:
        src: Source directory (skipped silently if absent).
        dest: Destination directory, created as needed.

    Returns:
        Tuple of (files hardlinked, files copied).
    """
    if not src.exists():
        log.warning("skipping %s — directory does not exist", src)
        return 0, 0
    linked = copied = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dest / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
            linked += 1
        except OSError:
            # Different filesystem (or a filesystem without hardlinks) — copy.
            shutil.copy2(path, target)
            copied += 1
    return linked, copied


def stage_db_export(dest_dir: Path, db_path: Path | str | None = None) -> Path:
    """Export the full-channel master DB and stage it inside the snapshot.

    Calls :func:`backend.db.export_master_db` in-process (never over HTTP) with
    ``include_private=True``, then hardlinks the result and its manifest sidecar
    into ``db/`` under stable names, so snapshot layout does not vary with the
    export timestamp.

    Args:
        dest_dir: Snapshot root.
        db_path: Source database; defaults to the live DB.

    Returns:
        Path of the staged ``.db`` file.
    """
    from backend.db import export_master_db

    out_path, manifest = export_master_db(
        reason="snapshot", db_path=db_path, include_private=True
    )
    db_dir = dest_dir / DB_SUBDIR
    db_dir.mkdir(parents=True, exist_ok=True)
    staged = db_dir / DB_NAME
    for source, target in ((out_path, staged),
                           (Path(str(out_path) + ".manifest.json"),
                            Path(str(staged) + ".manifest.json"))):
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    log.info("staged DB export: channel=%s, %s rows in lb_master",
             manifest.get("channel"), manifest.get("row_counts", {}).get("lb_master"))
    return staged


# ── Manifest / seal / docs ────────────────────────────────────────────────────

def build_manifest(snap_dir: Path) -> list[tuple[str, int, str]]:
    """Hash every manifest-eligible file in the snapshot.

    Args:
        snap_dir: Snapshot root.

    Returns:
        ``(sha256, size, relative_path)`` triples sorted by path, with POSIX
        separators so a manifest built on one platform reads on another.
    """
    entries: list[tuple[str, int, str]] = []
    for path in snap_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(snap_dir)
        if len(rel.parts) == 1 and rel.name in UNMANIFESTED:
            continue
        entries.append((vsm.hash_file(path), path.stat().st_size, rel.as_posix()))
    entries.sort(key=lambda e: e[2])
    return entries


def write_manifest(snap_dir: Path, entries: list[tuple[str, int, str]]) -> Path:
    """Write ``manifest.txt`` as ``sha256␠␠size␠␠relpath`` lines."""
    path = snap_dir / MANIFEST_NAME
    body = "".join(f"{sha}  {size}  {rel}\n" for sha, size, rel in entries)
    path.write_text(body, encoding="utf-8")
    return path


def write_seal(snap_dir: Path, manifest_path: Path) -> str:
    """Write ``seal.txt`` — one sha256 over the manifest — and return it."""
    seal = vsm.hash_file(manifest_path)
    (snap_dir / SEAL_NAME).write_text(f"{seal}  {MANIFEST_NAME}\n", encoding="utf-8")
    return seal


def write_verifier(snap_dir: Path) -> Path:
    """Write the standalone stdlib verifier into the snapshot."""
    path = snap_dir / VERIFIER_NAME
    path.write_text(VERIFIER_SOURCE, encoding="utf-8")
    path.chmod(0o755)
    return path


def write_readme(snap_dir: Path, res: SnapshotResult, with_db: bool) -> Path:
    """Write the recipient-facing ``README.txt``."""
    db_line = (f"full-channel database export + {DB_NAME}.manifest.json"
               if with_db else "(not included in this snapshot)")
    text = README_TEMPLATE.format(
        built=datetime.now().isoformat(timespec="seconds"),
        name=snap_dir.name,
        files=res.files,
        size_h=_human(res.size_bytes),
        site_files=res.counts.get("site", 0),
        olof_files=res.counts.get("olof/pages", 0),
        bobserve_files=res.counts.get("olof/bobserve_pages", 0),
        db_line=db_line,
    )
    path = snap_dir / README_NAME
    path.write_text(text, encoding="utf-8")
    return path


def make_tarball(snap_dir: Path) -> Path:
    """Write ``<snapshot>.tar.gz`` plus a ``.sha256`` sidecar next to it.

    Args:
        snap_dir: Snapshot root.

    Returns:
        Path of the tarball.
    """
    # Not with_suffix(): a ".N" collision suffix would be swallowed as an extension.
    tar_path = snap_dir.parent / (snap_dir.name + ".tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(snap_dir, arcname=snap_dir.name)
    digest = vsm.hash_file(tar_path)
    Path(str(tar_path) + ".sha256").write_text(
        f"{digest}  {tar_path.name}\n", encoding="utf-8"
    )
    return tar_path


# ── Build ─────────────────────────────────────────────────────────────────────

def make_snapshot(root: Path | None = None, payload: list[tuple[Path, str]] | None = None,
                  db_path: Path | str | None = None, site_dir: Path | None = None,
                  with_db: bool = True, verify_first: bool = True,
                  tar: bool = False, today: str | None = None) -> SnapshotResult:
    """Build a sealed snapshot directory.

    Args:
        root: Snapshot root directory; defaults to ``data/exports/snapshots/``.
        payload: ``(source_dir, destination_subpath)`` pairs; defaults to the
            site mirror plus both Olof mirrors.
        db_path: Source database for the export and the pre-build verify.
        site_dir: Mirror root for the pre-build verify.
        with_db: Include a full-channel DB export.
        verify_first: Refuse to build if the mirror has missing files or drift.
        tar: Also produce a ``.tar.gz`` and its ``.sha256`` sidecar.
        today: Date stamp override for the directory name.

    Returns:
        A :class:`SnapshotResult`.

    Raises:
        RuntimeError: If the pre-build mirror verification failed.
    """
    started = time.time()
    root = Path(root or SNAPSHOT_ROOT)
    site_dir = Path(site_dir or SITE_DIR)
    if payload is None:
        payload = [
            (site_dir, "site"),
            (OLOF_PAGES_DIR, "olof/pages"),
            (OLOF_BOBSERVE_DIR, "olof/bobserve_pages"),
        ]

    verify_result = None
    if verify_first:
        verify_result = vsm.verify(db_path, site_dir)
        log.info("pre-build %s", verify_result.summary())
        if verify_result.failed:
            raise RuntimeError(
                f"mirror verification failed ({verify_result.count(vsm.KIND_MISSING)} missing, "
                f"{verify_result.count(vsm.KIND_DRIFT)} drift) — refusing to seal a broken "
                f"mirror; fix it or re-run with --no-verify"
            )
    else:
        log.warning("!!! --no-verify: sealing this mirror WITHOUT checking it is intact; "
                    "the snapshot may certify damaged files as good")

    root.mkdir(parents=True, exist_ok=True)
    snap_dir = next_snapshot_dir(root, today)
    snap_dir.mkdir(parents=True)
    res = SnapshotResult(path=snap_dir, verify=verify_result)

    for src, sub in payload:
        linked, copied = stage_tree(src, snap_dir / sub)
        res.linked += linked
        res.copied += copied
        res.counts[sub] = linked + copied
        log.info("staged %s: %d files", sub, linked + copied)

    if with_db:
        stage_db_export(snap_dir, db_path)

    write_verifier(snap_dir)
    entries = build_manifest(snap_dir)
    res.files = len(entries)
    res.size_bytes = sum(size for _, size, _ in entries)
    write_readme(snap_dir, res, with_db)
    manifest_path = write_manifest(snap_dir, entries)
    res.seal = write_seal(snap_dir, manifest_path)

    if tar:
        res.tar_path = make_tarball(snap_dir)

    res.seconds = time.time() - started
    return res


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Build a sealed, self-verifying snapshot of the LosslessBob archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--tar", action="store_true",
                        help="also write <snapshot>.tar.gz + .sha256 sidecar")
    parser.add_argument("--no-db", action="store_true",
                        help="skip the full-channel database export")
    parser.add_argument("--no-verify", action="store_true",
                        help="build even if the mirror fails verification (logged loudly)")
    parser.add_argument("--root", default=None,
                        help="snapshot root (default: data/exports/snapshots/)")
    parser.add_argument("--db", default=None, help="database path (default: the app DB)")
    parser.add_argument("--site-dir", default=None, help="mirror root (default: data/site/)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code — non-zero if the build refused or failed.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        res = make_snapshot(
            root=Path(args.root) if args.root else None,
            db_path=Path(args.db) if args.db else DB_PATH,
            site_dir=Path(args.site_dir) if args.site_dir else None,
            with_db=not args.no_db,
            verify_first=not args.no_verify,
            tar=args.tar,
        )
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    log.info("%s", res.summary())
    log.info("verify it with: cd %s && python3 %s", res.path, VERIFIER_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
