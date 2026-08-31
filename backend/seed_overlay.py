"""Assemble a seedable copy of a recording without touching the collection.

A tracker's torrent usually contains the LosslessBob ``LBF-*`` sidecars
(checksum lists, info text, DigiFlawFinder reports) that the curated collection
folder does not keep alongside the audio. The folder therefore verifies at
99-point-something, and handing that to a BitTorrent client makes it *download*
the remainder into the collection folder.

This module builds a third location — the overlay — that contains:

* the audio, **hardlinked** from the collection (no extra disk space, and the
  bytes are literally the same inode, so the client seeds the real files);
* the sidecars, **copied** from ``data/site/files/`` where the site crawl
  already stored them;
* nothing at all for files no local source can satisfy — the client fetches
  those, into the overlay, never into the collection.

The one sharp edge is piece alignment: a piece can straddle a file boundary, so
a file adjacent to a missing one may be written to while the client completes
that piece. Any collection file sharing a piece with an unresolved file is
therefore **copied instead of hardlinked**, so a write can never reach the
collection's inode.

Nothing here ever opens a file inside the source collection folder for writing.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from backend.torrent_verify import TorrentInfo, VerifyResult, verify_folder

logger = logging.getLogger(__name__)

# Actions the plan can assign to a torrent file.
LINK = "link"        # hardlink from the collection — free, shares the inode
COPY = "copy"        # byte copy — sidecars, and anything a client might write to
REFETCH = "refetch"  # re-download the pristine original from losslessbob.com
FETCH = "fetch"      # no local source; the BitTorrent client downloads it


@dataclass
class PlanEntry:
    """One torrent file and how the overlay will satisfy it."""

    rel_path: str
    action: str
    size: int
    source: str = ""
    reason: str = ""


@dataclass
class OverlayPlan:
    """What building the overlay would do."""

    target_dir: Path
    entries: list[PlanEntry] = field(default_factory=list)
    note: str = ""

    def _bytes(self, action: str) -> int:
        return sum(e.size for e in self.entries if e.action == action)

    @property
    def link_bytes(self) -> int:
        """Bytes satisfied by hardlink (costing no additional space)."""
        return self._bytes(LINK)

    @property
    def copy_bytes(self) -> int:
        """Bytes that will be duplicated on disk."""
        return self._bytes(COPY)

    @property
    def refetch_bytes(self) -> int:
        """Bytes to be re-downloaded from losslessbob.com."""
        return self._bytes(REFETCH)

    @property
    def fetch_bytes(self) -> int:
        """Bytes the BitTorrent client will have to download."""
        return self._bytes(FETCH)

    def count(self, action: str) -> int:
        """Return how many files carry the given action."""
        return sum(1 for e in self.entries if e.action == action)

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        return (
            f"{self.count(LINK)} linked ({self.link_bytes / 1e6:.1f} MB free), "
            f"{self.count(COPY)} copied ({self.copy_bytes / 1e6:.1f} MB), "
            f"{self.count(REFETCH)} re-fetched ({self.refetch_bytes / 1e6:.1f} MB), "
            f"{self.count(FETCH)} left to the swarm ({self.fetch_bytes / 1e6:.1f} MB)"
        )


def _index_sources(dirs: list[Path]) -> dict[str, list[Path]]:
    """Index every file under the given directories by path suffix.

    A tracker's torrent is often nested — ``<root>/<show>/cd-1/01 Track01.flac``
    — while the collection files the same audio under its own layout. Indexing
    only basenames both misses everything below the top level and collides
    (``cd-1/01 Track01.flac`` and ``cd-2/01 Track01.flac`` share a basename), so
    each file is registered under **every** suffix of its relative path:
    ``01 Track01.flac``, ``cd-1/01 Track01.flac``, and so on. The resolver can
    then ask for the most specific match first.

    Directories are walked recursively and earlier ones win, so the caller
    controls precedence.

    Args:
        dirs: Directories to index, most-preferred first.

    Returns:
        A suffix→paths mapping; each list is in directory-preference order.
    """
    found: dict[str, list[Path]] = {}
    for directory in dirs:
        try:
            paths = sorted(directory.rglob("*"))
        except OSError:
            continue
        for path in paths:
            try:
                if not path.is_file():
                    continue
                parts = path.relative_to(directory).parts
            except (OSError, ValueError):
                continue
            for depth in range(1, len(parts) + 1):
                found.setdefault("/".join(parts[-depth:]), []).append(path)
    return found


def _resolve_source(
    index: dict[str, list[Path]], rel_path: str, size: int
) -> Path | None:
    """Find the indexed file that satisfies one torrent entry.

    Suffixes are tried longest-first, so ``cd-1/01 Track01.flac`` is preferred
    over the ambiguous bare ``01 Track01.flac``, and only files of exactly the
    right size are accepted. Where several equally specific candidates share
    that size they are interchangeable by definition — the piece hashes are
    checked afterwards regardless, and a wrong pick fails verification rather
    than being seeded.

    The torrent's own root segment is dropped before matching, since the
    collection never repeats the uploader's name for it.

    Args:
        index: Mapping from :func:`_index_sources`.
        rel_path: The torrent's path for this file, root segment included.
        size: The exact byte size the torrent expects.

    Returns:
        The best local file, or None when nothing of that size matches.
    """
    parts = Path(rel_path).parts
    if len(parts) > 1:
        parts = parts[1:]        # drop the torrent's root directory
    for depth in range(len(parts), 0, -1):
        for candidate in index.get("/".join(parts[-depth:]), []):
            try:
                if candidate.stat().st_size == size:
                    return candidate
            except OSError:
                continue
    return None


def resolvable_files(info: TorrentInfo, dirs: list[str | Path]) -> int:
    """Count how many of a torrent's files the given folders can supply.

    Uses exactly the matching rule :func:`plan_overlay` will use — recursive,
    path-suffix keyed, exact size — so the number is a truthful preview of how
    much of the torrent those folders would satisfy, not a basename guess.

    Args:
        info: Parsed torrent metadata.
        dirs: Collection folders to score, most-preferred first.

    Returns:
        The number of torrent files with a local source in ``dirs``.
    """
    index = _index_sources([Path(d) for d in dirs])
    return sum(
        1 for rel_path, size in info.files
        if _resolve_source(index, rel_path, size) is not None
    )


def plan_overlay(
    info: TorrentInfo,
    source_folder: str | Path,
    overlay_root: str | Path,
    sidecar_dirs: list[str | Path] | None = None,
    site_urls: dict[str, str] | None = None,
    link_dirs: list[str | Path] | None = None,
) -> OverlayPlan:
    """Decide how each torrent file will be satisfied, without touching disk.

    Sources are tried in order: the collection folder (hardlink), any further
    collection folders in ``link_dirs`` (hardlink), the sidecar store (copy),
    the original URL on losslessbob.com (re-fetch), and finally the BitTorrent
    swarm.

    Args:
        info: Parsed torrent metadata.
        source_folder: The collection folder holding the audio.
        overlay_root: Directory the overlay folder is created inside. Should be
            on the same filesystem as ``source_folder`` so hardlinks work.
        sidecar_dirs: Extra read-only directories to source missing files from,
            typically ``data/site/files``. Files found here are **copied**.
        site_urls: {filename: url} from :func:`db.get_site_file_urls`, used
            when the stored sidecar is the wrong size (link-rewritten HTML).
        link_dirs: Further collection folders, most-preferred first, whose
            files are **hardlinked** like ``source_folder``'s. A tracker's
            torrent can span more than one LB entry — a two-CD boot posted as
            one ``.torrent`` covering LB-14777 and LB-14778, say — and each
            entry is filed in its own collection folder. Passing the others
            here assembles the whole torrent at no extra disk cost. Must be on
            the same filesystem as ``overlay_root`` for the link to succeed.

    Returns:
        An OverlayPlan. Building it is a separate call.
    """
    source_folder = Path(source_folder)
    target_dir = Path(overlay_root) / info.name
    plan = OverlayPlan(target_dir=target_dir)

    sidecars = _index_sources([Path(d) for d in (sidecar_dirs or [])])
    # The primary folder and any siblings are all curated collection folders,
    # so all of them are hardlink sources, the primary taking precedence.
    collection = _index_sources(
        [source_folder] + [Path(d) for d in (link_dirs or [])]
    )
    ranges = info.file_piece_ranges()

    # Pass 1 — resolve a local source for each file, by exact size match.
    resolved: list[tuple[PlanEntry, Path | None]] = []
    for (rel_path, size), _rng in zip(info.files, ranges, strict=True):
        name = Path(rel_path).name
        entry = PlanEntry(rel_path=rel_path, action=FETCH, size=size)

        in_collection = _resolve_source(collection, rel_path, size)
        if in_collection is not None:
            entry.action = LINK
            entry.source = str(in_collection)
            entry.reason = (
                "collection" if in_collection.is_relative_to(source_folder)
                else f"collection ({in_collection.parent.name})"
            )
            resolved.append((entry, in_collection))
            plan.entries.append(entry)
            continue

        candidate = _resolve_source(sidecars, rel_path, size)
        local_size: int | None = None
        if candidate is None:
            # Fall back to any same-named sidecar so a size mismatch can be
            # reported (and re-fetched) rather than silently left to the swarm.
            same_named = sidecars.get(name) or []
            candidate = same_named[0] if same_named else None
        if candidate is not None:
            try:
                local_size = candidate.stat().st_size
            except OSError:
                local_size = None
        if local_size == size:
            entry.action = COPY
            entry.source = str(candidate)
            entry.reason = "sidecar store"
            resolved.append((entry, candidate))
            plan.entries.append(entry)
            continue

        # The crawl rewrote links inside saved HTML, so its copy is the wrong
        # size; the site still serves the original the torrent was built from.
        url = (site_urls or {}).get(name)
        if url:
            entry.action = REFETCH
            entry.source = url
            entry.reason = (
                f"sidecar store has it at {local_size} B, torrent wants {size} B"
                if local_size is not None else "re-fetch original from the site"
            )
            resolved.append((entry, None))
            plan.entries.append(entry)
            continue

        if local_size is not None:
            entry.reason = (
                f"sidecar store has it at {local_size} B, torrent wants {size} B"
            )
        elif (source_folder / name).exists():
            entry.reason = "present locally but the wrong size"
        else:
            entry.reason = "no local source"

        resolved.append((entry, None))
        plan.entries.append(entry)

    # Pass 2 — pieces still unsatisfied are the only ones a client can write.
    unresolved_pieces: set[int] = set()
    for (entry, _src), (first, last) in zip(resolved, ranges, strict=True):
        if entry.action == FETCH:
            unresolved_pieces.update(range(first, last + 1))

    # Pass 3 — demote any hardlink that shares a piece with unresolved data.
    for (entry, _src), (first, last) in zip(resolved, ranges, strict=True):
        if entry.action != LINK:
            continue
        if any(p in unresolved_pieces for p in range(first, last + 1)):
            entry.action = COPY
            entry.reason = "collection (copied — shares a piece with missing data)"

    if not unresolved_pieces:
        plan.note = "every piece is locally satisfiable — no download needed"
    return plan


def http_fetch(url: str, dest: Path, timeout: int = 60) -> int:
    """Download a URL to a path, returning the byte count written.

    Args:
        url: Source URL.
        dest: Destination path; its parent must exist.
        timeout: Per-request timeout in seconds.

    Returns:
        Bytes written.

    Raises:
        OSError: On any transport or write failure.
    """
    import requests

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OSError(f"fetch failed: {exc}") from exc
    dest.write_bytes(resp.content)
    return len(resp.content)


def build_overlay(plan: OverlayPlan, dry_run: bool = False, fetcher=None) -> dict:
    """Create the overlay directory described by a plan.

    Hardlinks fall back to a copy when the target is on another filesystem.
    Files marked REFETCH are downloaded with ``fetcher``; if none is given they
    are left for the BitTorrent client instead.

    Args:
        plan: The plan from :func:`plan_overlay`.
        dry_run: Report what would happen without creating anything.
        fetcher: Callable ``(url, dest) -> int`` used for REFETCH entries.
            Defaults to :func:`http_fetch` being skipped entirely when None.

    Returns:
        Dict with ``ok``, ``linked``, ``copied``, ``refetched``, ``skipped``,
        ``errors`` (list of strings) and ``target_dir``.
    """
    result = {
        "ok": True, "linked": 0, "copied": 0, "refetched": 0, "skipped": 0,
        "errors": [], "target_dir": str(plan.target_dir),
    }
    if dry_run:
        result["linked"] = plan.count(LINK)
        result["copied"] = plan.count(COPY)
        result["refetched"] = plan.count(REFETCH) if fetcher else 0
        result["skipped"] = plan.count(FETCH) + (0 if fetcher else plan.count(REFETCH))
        return result

    for entry in plan.entries:
        if entry.action == FETCH or (entry.action == REFETCH and fetcher is None):
            result["skipped"] += 1
            continue

        dest = plan.target_dir / Path(entry.rel_path).relative_to(
            Path(entry.rel_path).parts[0]
        )
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()

            if entry.action == REFETCH:
                written = fetcher(entry.source, dest)
                if written != entry.size:
                    dest.unlink(missing_ok=True)
                    result["skipped"] += 1
                    result["errors"].append(
                        f"{entry.rel_path}: re-fetch gave {written} B, "
                        f"torrent wants {entry.size} B"
                    )
                    continue
                result["refetched"] += 1
                continue

            if entry.action == LINK:
                try:
                    os.link(entry.source, dest)
                    result["linked"] += 1
                    continue
                except OSError as exc:
                    logger.info(
                        "hardlink failed for %s (%s) — copying instead",
                        entry.rel_path, exc,
                    )
            shutil.copy2(entry.source, dest)
            result["copied"] += 1
        except OSError as exc:
            result["ok"] = False
            result["errors"].append(f"{entry.rel_path}: {exc}")

    return result


def verify_overlay(info: TorrentInfo, plan: OverlayPlan) -> VerifyResult:
    """Hash the built overlay against the torrent.

    Args:
        info: Parsed torrent metadata.
        plan: The plan whose ``target_dir`` was built.

    Returns:
        A VerifyResult for the overlay directory.
    """
    return verify_folder(info, plan.target_dir)


def collection_is_untouched(
    source_folder: str | Path, before: dict[str, tuple[int, int]]
) -> list[str]:
    """Compare a folder against a snapshot, returning names that changed.

    A cheap post-condition check for the promise that the collection is never
    written to.

    Args:
        source_folder: Folder to re-inspect.
        before: Snapshot from :func:`snapshot_folder`.

    Returns:
        Names that were added, removed, resized or re-dated. Empty when clean.
    """
    after = snapshot_folder(source_folder)
    changed = [n for n in before if n not in after or after[n] != before[n]]
    changed += [n for n in after if n not in before]
    return sorted(set(changed))


@dataclass
class OverlayStatus:
    """How an existing overlay relates to the collection right now."""

    path: Path
    exists: bool = False
    n_files: int = 0
    shared_bytes: int = 0   # files whose inode has another name (the collection)
    pinned_bytes: int = 0   # files the overlay is the sole holder of

    @property
    def orphaned(self) -> bool:
        """True when the overlay holds audio nothing else references.

        After a same-volume rename the overlay is untouched and still shares
        every inode. After a delete or a cross-volume move (copy + rmtree) the
        link count drops to 1 and the overlay silently keeps those bytes alive,
        so the space is never reclaimed.
        """
        return self.exists and self.pinned_bytes > self.shared_bytes

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        if not self.exists:
            return "overlay directory is gone"
        return (
            f"{self.n_files} files, {self.shared_bytes / 1e6:.1f} MB shared with "
            f"the collection, {self.pinned_bytes / 1e6:.1f} MB held only here"
        )


def overlay_status(overlay_dir: str | Path) -> OverlayStatus:
    """Report whether an overlay still shares its bytes with the collection.

    Uses link counts rather than paths, so it stays correct after the
    collection folder is renamed or moved within its volume.

    Args:
        overlay_dir: The overlay folder to inspect.

    Returns:
        An OverlayStatus.
    """
    path = Path(overlay_dir)
    status = OverlayStatus(path=path)
    try:
        entries = [p for p in path.iterdir() if p.is_file()]
    except OSError:
        return status

    status.exists = True
    for item in entries:
        stat = item.stat()
        status.n_files += 1
        if stat.st_nlink > 1:
            status.shared_bytes += stat.st_size
        else:
            status.pinned_bytes += stat.st_size
    return status


def find_overlays_for_lb(lb_number: int, db_path=None) -> list[Path]:
    """Return recorded overlay/seed folders for an LB number.

    Reads ``tuit_downloads.seed_folder``, so it only knows about seeds this
    tool created.

    Args:
        lb_number: LB number to look up.
        db_path: Optional DB path override.

    Returns:
        Distinct seed folder paths, newest attempt first.
    """
    from backend import db  # imported here to keep module import cheap

    with db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT seed_folder FROM tuit_downloads "
            " WHERE lb_number=? AND seed_folder IS NOT NULL AND seed_folder <> ''"
            " ORDER BY attempted_at DESC",
            (lb_number,),
        ).fetchall()
    return [Path(r[0]) for r in rows]


def warn_if_seeded(lb_number: int, action: str, db_path=None) -> list[str]:
    """Log a warning when an LB about to be moved or deleted has live seeds.

    A same-volume rename is harmless — hardlinks follow the inode. A delete or
    cross-volume move is not: the overlay keeps the old bytes alive, so the
    space is never reclaimed and the seed silently stops shadowing the
    collection copy.

    Args:
        lb_number: LB number being operated on.
        action: Short description used in the log line.
        db_path: Optional DB path override.

    Returns:
        The overlay paths that were warned about (empty when there are none).
    """
    try:
        overlays = find_overlays_for_lb(lb_number, db_path)
    except Exception as exc:  # never let bookkeeping block a file operation
        logger.debug("warn_if_seeded: lookup failed for LB-%s: %s", lb_number, exc)
        return []

    warned: list[str] = []
    for overlay in overlays:
        status = overlay_status(overlay)
        if not status.exists:
            continue
        warned.append(str(overlay))
        logger.warning(
            "LB-%05d is being %s but is seeded from %s (%s). After a delete or "
            "cross-volume move that overlay holds the only copy of those bytes, "
            "so the space is not reclaimed — run "
            "'tools/tuit_sync.py --check-overlays' afterwards.",
            lb_number, action, overlay, status.summary(),
        )
    return warned


def snapshot_folder(folder: str | Path) -> dict[str, tuple[int, int]]:
    """Return {relative path: (size, mtime_ns)} for every file under a folder.

    Walks the whole tree, not just the top level: a collection folder holding
    ``cd-1/``/``cd-2/`` subdirectories would otherwise let a write below the
    root pass the :func:`collection_is_untouched` guard unnoticed.

    Args:
        folder: Directory to snapshot.

    Returns:
        A mapping usable with :func:`collection_is_untouched`.
    """
    root = Path(folder)
    out: dict[str, tuple[int, int]] = {}
    try:
        paths = list(root.rglob("*"))
    except OSError:
        return out
    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
            out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
        except (OSError, ValueError):
            continue
    return out
