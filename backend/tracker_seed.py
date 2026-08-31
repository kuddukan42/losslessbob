"""Seed a recording to a private tracker without ever writing to the collection.

This is the tracker-agnostic half of what ``tools/tuit_sync.py`` grew for TUIT.
Given an LB number and a ``.torrent`` file from *any* tracker, it decides
whether the recording may be seeded, finds files to seed from, and hands
qBittorrent a folder that hashes to 100 % locally.

Three gates, all of which must pass before qBittorrent is told anything:

1. :func:`backend.db.is_seedable_to_tracker` — ``lb_status`` must be 'public'.
2. A linked collection folder must exist on disk whose name matches the
   torrent's root folder.
3. Every piece must hash correctly against that folder.

Gate 3 is the sharp one: qBittorrent handed a 99 %-complete torrent downloads
the remainder *into* the folder it was pointed at, and curated collection
folders are never written to. An incomplete folder is therefore refused, not
forced. :attr:`SeedOptions.overlay` turns that refusal into a fallback — an
overlay folder is assembled at ``<mount>/<Tracker> Seeds/<torrent root>``
(see :mod:`backend.seed_overlay`) and seeded from instead.

Every tracker-specific detail is carried by :class:`SeedOptions`: the overlay
root's name, the qBittorrent tag, and the fetch/partial tolerances.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend import db as database
from backend import qbittorrent
from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
from backend.seed_overlay import (
    build_overlay,
    collection_is_untouched,
    http_fetch,
    plan_overlay,
    snapshot_folder,
)
from backend.torrent_verify import BencodeError, TorrentInfo, read_torrent, verify_folder

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Where the site crawl already stored the ``LBF-*`` sidecars a tracker's
#: torrent contains but the curated collection folder does not keep.
SIDECAR_DIR = _PROJECT_ROOT / "data" / "site" / "files"

#: Extensions treated as the recording's audio when picking a source folder
#: by content rather than by name.
_AUDIO_SUFFIXES = (".flac", ".shn", ".wav", ".ape")


@dataclass
class SeedOptions:
    """Everything tracker- or run-specific about one seeding attempt.

    Attributes:
        tracker: Short tracker name, e.g. ``"tuit"`` or ``"wtrf"``. Drives the
            default overlay root (``<mount>/<TRACKER> Seeds``) and the
            qBittorrent tag applied to the added torrent.
        overlay: Allow assembling an overlay when the collection folder does
            not verify in place. Without it an incomplete folder is refused.
        overlay_root: Explicit overlay root, overriding the per-mount default.
        refetch_sidecars: Re-download sidecars from losslessbob.com when the
            locally saved copy is the wrong size (link-rewritten crawl HTML).
        max_fetch_mb: Refuse an overlay that would leave more than this many
            megabytes for the swarm to supply.
        allow_partial_overlay: Accept an overlay that still hashes short. The
            remainder downloads into the overlay, never the collection.
        paused: Add the torrent to qBittorrent in a stopped state.
    """

    tracker: str
    overlay: bool = False
    overlay_root: str = ""
    refetch_sidecars: bool = False
    max_fetch_mb: float = 25.0
    allow_partial_overlay: bool = False
    paused: bool = False

    @property
    def overlay_dirname(self) -> str:
        """Name of the per-mount overlay directory, e.g. ``"WTRF Seeds"``."""
        return f"{self.tracker.upper()} Seeds"


def overlay_root_for(source_folder: Path, opts: SeedOptions) -> Path:
    """Choose where the overlay lives — same filesystem as the source.

    Hardlinks cannot cross a mount, and the drives here are separate NTFS
    volumes, so the overlay is placed at ``<mount>/<TRACKER> Seeds`` by
    default. That directory sits outside the ``…/Concerts`` roots in
    ``collection_mounts``, so the disk scanner will not index it as collection.

    Args:
        source_folder: The collection folder being seeded from.
        opts: Seeding options; ``overlay_root`` overrides the default.

    Returns:
        The overlay root directory.
    """
    if opts.overlay_root:
        return Path(opts.overlay_root)
    parts = source_folder.resolve().parts
    # /mnt/<DRIVE>/Concerts/... → /mnt/<DRIVE>/<TRACKER> Seeds
    if len(parts) >= 3 and parts[1] == "mnt":
        return Path(parts[0], parts[1], parts[2], opts.overlay_dirname)
    return source_folder.parent / opts.overlay_dirname


def best_source_folder(info: TorrentInfo, folders: list[str]) -> str | None:
    """Pick the collection folder that supplies the most of a torrent's audio.

    Used when no folder is named after the torrent root — an uploader's naming
    rarely matches the collection's. Selection is by content, not by name.

    Args:
        info: Parsed torrent metadata.
        folders: Candidate collection folders, all known to exist.

    Returns:
        The best-matching folder, or None when none supplies any audio.
    """
    wanted = {
        Path(p).name for p, _s in info.files
        if Path(p).suffix.lower() in _AUDIO_SUFFIXES
    }
    if not wanted:
        wanted = {Path(p).name for p, _s in info.files}

    best_folder, best_hits = None, 0
    for folder in folders:
        try:
            have = {p.name for p in Path(folder).iterdir() if p.is_file()}
        except OSError:
            continue
        hits = len(wanted & have)
        if hits > best_hits:
            best_folder, best_hits = folder, hits
    return best_folder


def build_seed_overlay(
    info: TorrentInfo,
    source_folder: str,
    opts: SeedOptions,
    shortfall: str,
) -> tuple[str | None, str]:
    """Assemble an overlay folder that can seed without touching the collection.

    Audio is hardlinked from the collection (free, same inode); LBF sidecars are
    copied from ``data/site/files`` or re-fetched from losslessbob.com; anything
    still unresolved is left to the swarm and lands in the overlay. Any
    collection file sharing a piece with unresolved data is copied rather than
    linked, so a client write can never reach the collection's inode.

    Args:
        info: Parsed torrent metadata.
        source_folder: The collection folder to source audio from.
        opts: Seeding options.
        shortfall: The collection folder's verify summary, for messages.

    Returns:
        (overlay_path or None, human-readable reason).
    """
    source = Path(source_folder)
    root = overlay_root_for(source, opts)
    names = [Path(p).name for p, _s in info.files]
    site_urls = database.get_site_file_urls(names) if opts.refetch_sidecars else {}

    plan = plan_overlay(info, source, root, [SIDECAR_DIR], site_urls)
    logger.info("  overlay: %s", plan.summary())
    if plan.fetch_bytes > opts.max_fetch_mb * 1_000_000:
        return None, (
            f"overlay would leave {plan.fetch_bytes / 1e6:.1f} MB to download, "
            f"over the {opts.max_fetch_mb} MB limit ({shortfall})"
        )

    before = snapshot_folder(source)
    built = build_overlay(plan, fetcher=http_fetch if opts.refetch_sidecars else None)
    for err in built["errors"]:
        logger.warning("  overlay: %s", err)

    touched = collection_is_untouched(source, before)
    if touched:
        return None, (
            f"ABORTED — building the overlay altered the collection: "
            f"{', '.join(touched[:3])}"
        )

    result = verify_folder(info, plan.target_dir)
    logger.info("  overlay verify: %s", result.summary())
    if not result.complete:
        if not opts.allow_partial_overlay:
            return None, (
                f"overlay still {result.summary()} — qBittorrent would download "
                f"the rest into it; allow a partial overlay to accept"
            )
        return str(plan.target_dir), (
            f"overlay {result.summary()}; remainder will download into the "
            f"overlay, not the collection"
        )
    return str(plan.target_dir), (
        f"overlay assembled 100% locally ({built['linked']} hardlinked, "
        f"{built['copied']} copied, {built['refetched']} re-fetched); "
        f"collection untouched"
    )


def find_seedable_folder(
    lb_number: int | None,
    torrent_path: str,
    opts: SeedOptions,
) -> tuple[str | None, str]:
    """Find a folder that may be seeded for ``lb_number`` and is complete.

    Runs the three gates described in the module docstring. With
    ``opts.overlay`` the third becomes a fallback: an overlay is assembled
    elsewhere and returned instead of the collection folder.

    Args:
        lb_number: LB number claimed by the recording.
        torrent_path: Local ``.torrent`` file.
        opts: Seeding options.

    Returns:
        (folder_path or None, human-readable reason).
    """
    if lb_number is None:
        return None, "recording has no LB number"

    allowed, why = database.is_seedable_to_tracker(lb_number)
    if not allowed:
        return None, f"LB-{lb_number} not seedable ({why})"

    folders = [f for f in database.get_folders_for_lb(lb_number) if Path(f).is_dir()]
    if not folders:
        return None, f"no collection folder on disk for LB-{lb_number}"

    try:
        info = read_torrent(torrent_path)
    except BencodeError as exc:
        return None, f"unreadable torrent: {exc}"

    # Seeding the collection folder in place needs its name to equal the torrent
    # root, since a client resolves files as <save_path>/<root>/… An overlay is
    # created *with* the torrent's name and sources files by basename, so there
    # the collection folder may be named anything.
    named = [f for f in folders if Path(f).name == info.name]

    best = ""
    for folder in named:
        result = verify_folder(info, folder)
        if result.complete:
            return folder, f"verified in place, {result.summary()}"
        best = result.summary()
        if result.missing_files:
            best += f"; first missing: {Path(result.missing_files[0]).name}"

    if not opts.overlay:
        if not named:
            return None, (
                f"torrent root {info.name!r} matches no linked folder "
                f"(have {', '.join(Path(f).name for f in folders[:3])}) "
                f"— enable the overlay to seed regardless of folder naming"
            )
        return None, f"folder incomplete — {best} (enable the overlay to assemble one)"

    source = named[0] if named else best_source_folder(info, folders)
    if source is None:
        return None, (
            f"no linked folder shares enough files with the torrent "
            f"(have {', '.join(Path(f).name for f in folders[:3])})"
        )
    return build_seed_overlay(info, source, opts, best or "name mismatch")


def qbt_seed(torrent_path: str, source_folder: str, opts: SeedOptions) -> dict:
    """Add a ``.torrent`` to qBittorrent pointed at an existing folder.

    Args:
        torrent_path: Local ``.torrent`` file.
        source_folder: Absolute path of the folder holding the files.
        opts: Seeding options; ``tracker`` becomes an extra qBittorrent tag.

    Returns:
        The qbittorrent module's result dict (``ok`` plus optional ``error``).
    """
    host = database.get_meta("qbt_host") or "localhost"
    port = int(database.get_meta("qbt_port") or 8080)
    category = database.get_meta("qbt_category") or ""
    tags = ",".join(
        t for t in [database.get_meta("qbt_tags") or "", opts.tracker] if t
    )
    qbt_user, qbt_pass = get_credentials(SERVICE_QBT)
    _, qbt_key = get_credentials(SERVICE_QBT_KEY)

    result = qbittorrent.add_torrent_for_seeding(
        torrent_path=torrent_path,
        source_folder=source_folder,
        host=host,
        port=port,
        username=qbt_user,
        password=qbt_pass,
        category=category,
        tags=tags,
        api_key=qbt_key,
    )
    if result.get("ok") and opts.paused:
        logger.info("  (added; pause it in the qBittorrent UI if needed)")
    return result


def seed_torrent(
    lb_number: int | None,
    torrent_path: str,
    opts: SeedOptions,
) -> dict:
    """Run the whole gate → overlay → qBittorrent sequence for one torrent.

    Args:
        lb_number: LB number the torrent claims to be.
        torrent_path: Local ``.torrent`` file.
        opts: Seeding options.

    Returns:
        Dict with ``ok`` (bool), ``folder`` (str, the folder handed to
        qBittorrent, or ""), ``reason`` (str, why it was seedable or not),
        ``overlay`` (bool, whether ``folder`` is an assembled overlay) and
        ``error`` (str, a qBittorrent failure) — ``reason`` is always
        populated and is the line worth showing a user.
    """
    folder, reason = find_seedable_folder(lb_number, torrent_path, opts)
    if not folder:
        return {"ok": False, "folder": "", "reason": reason, "overlay": False,
                "error": ""}

    is_overlay = Path(folder).parent.name == opts.overlay_dirname
    qbt = qbt_seed(torrent_path, folder, opts)
    if not qbt.get("ok"):
        return {"ok": False, "folder": folder, "reason": reason,
                "overlay": is_overlay, "error": qbt.get("error") or "qBittorrent refused"}
    return {"ok": True, "folder": folder, "reason": reason, "overlay": is_overlay,
            "error": ""}
