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
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend import db as database
from backend import qbittorrent
from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
from backend.seed_overlay import (
    build_overlay,
    choose_source_folder,
    collection_is_untouched,
    http_fetch,
    plan_overlay,
    repair_overlay,
    snapshot_folder,
    unique_overlay_name,
)
from backend.torrent_verify import BencodeError, TorrentInfo, read_torrent, verify_folder

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Where the site crawl already stored the ``LBF-*`` sidecars a tracker's
#: torrent contains but the curated collection folder does not keep.
SIDECAR_DIR = _PROJECT_ROOT / "data" / "site" / "files"

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
        allow_partial_overlay: Accept an overlay that still hashes short
            (default). The remainder downloads into the overlay, never the
            collection.
        paused: Add the torrent to qBittorrent in a stopped state.
        allow_private: Seed a recording whose ``lb_status`` is 'private'. Set
            only on the WTRF paths, and only because every one of them starts
            from a post that already exists on the board: the recording is
            public there whatever the local status says, so refusing to seed
            it only starves a swarm the curator already published to. 'missing'
            and 'nonexistent' still refuse, and TUIT is unaffected.
    """

    tracker: str
    overlay: bool = False
    overlay_root: str = ""
    refetch_sidecars: bool = False
    max_fetch_mb: float = 25.0
    allow_partial_overlay: bool = True
    paused: bool = False
    allow_private: bool = False

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


def same_date_folders(lb_number: int) -> dict[int, list[str]]:
    """On-disk folders of the other LB entries dated like ``lb_number``.

    Args:
        lb_number: The LB number the tracker claims.

    Returns:
        ``{lb_number: [existing folders]}``, entries without a folder on disk
        dropped. Empty on any DB error — a missing sibling pool only narrows
        the choice back to the claimed LB's own folders.
    """
    try:
        raw = database.get_folders_for_same_date(lb_number)
    except sqlite3.Error as exc:
        logger.warning("same-date folder lookup failed for LB-%d: %s", lb_number, exc)
        return {}
    out: dict[int, list[str]] = {}
    for lb, folders in raw.items():
        present = [f for f in folders if Path(f).is_dir()]
        if present:
            out[lb] = present
    return out


def best_source_folder(
    info: TorrentInfo, folders: list[str], named: list[str] | None = None
) -> str | None:
    """Pick the collection folder that supplies the most of a torrent.

    Selection is by content, not by name, and by the same recursive
    path-suffix rule the overlay planner uses, so a nested torrent
    (``<root>/<show>/cd-1/…``) scores against a nested collection folder
    instead of finding nothing at its top level. A folder *named* after the
    torrent root only breaks a tie: the tracker's attribution is not
    authoritative (two recordings repaired on 2026-09-06 were filed against
    the wrong LB outright), so the folder that resolves more of the torrent
    wins even when another one carries the matching name.

    Args:
        info: Parsed torrent metadata.
        folders: Candidate collection folders, all known to exist.
        named: The subset whose directory name equals the torrent root.

    Returns:
        The best-matching folder, or None when none supplies any file.
    """
    return choose_source_folder(info, list(folders), named)


def build_seed_overlay(
    info: TorrentInfo,
    source_folder: str,
    opts: SeedOptions,
    shortfall: str,
    link_dirs: list[str] | None = None,
    lb_number: int | None = None,
    details: dict | None = None,
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
        link_dirs: Further collection folders to hardlink from, for a torrent
            that spans more than one LB entry.
        lb_number: LB entry being seeded, used to keep the overlay folder from
            colliding with another entry whose torrent has the same root name.
        details: Optional dict filled in with ``overlay`` (the target dir),
            ``repaired`` (torrent-relative paths whose source was re-resolved
            out of a failing piece) and ``bad_pieces``. A caller that finds
            ``repaired`` non-empty and the torrent *already* in qBittorrent
            must trigger a recheck — see :func:`recheck_seed` — because the
            client hashed the overlay before those files changed.

    Returns:
        (overlay_path or None, human-readable reason).
    """
    source = Path(source_folder)
    root = overlay_root_for(source, opts)
    names = [Path(p).name for p, _s in info.files]
    site_urls = database.get_site_file_urls(names) if opts.refetch_sidecars else {}

    plan = plan_overlay(info, source, root, [SIDECAR_DIR], site_urls,
                        link_dirs=link_dirs,
                        overlay_name=unique_overlay_name(root, info.name, lb_number))
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
        # A short overlay whose failing pieces are locally complete is a wrong
        # pick, not a shortfall — re-resolve just those files before handing
        # the remainder to a swarm that may have nobody left in it.
        repair = repair_overlay(info, plan)
        if details is not None:
            details["overlay"] = str(plan.target_dir)
            details["repaired"] = list(repair["repaired"])
            details["bad_pieces"] = repair["bad_pieces"]
        if repair["repaired"]:
            logger.info(
                "  overlay repair: re-resolved %s; now %s",
                ", ".join(Path(p).name for p in repair["repaired"][:3]),
                repair["verify"].summary(),
            )
            result = repair["verify"]
        elif repair["bad_pieces"]:
            logger.warning(
                "  overlay repair: %d piece(s) hash wrong with every byte "
                "present locally, and no alternative local source to try — "
                "this seed stays short unless the swarm supplies them",
                repair["bad_pieces"],
            )
        for err in repair["errors"]:
            logger.warning("  overlay repair: %s", err)

        touched = collection_is_untouched(source, before)
        if touched:
            return None, (
                f"ABORTED — repairing the overlay altered the collection: "
                f"{', '.join(touched[:3])}"
            )

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
    link_dirs: list[str] | None = None,
    details: dict | None = None,
) -> tuple[str | None, str]:
    """Find a folder that may be seeded for ``lb_number`` and is complete.

    Runs the three gates described in the module docstring. With
    ``opts.overlay`` the third becomes a fallback: an overlay is assembled
    elsewhere and returned instead of the collection folder.

    Args:
        lb_number: LB number claimed by the recording.
        torrent_path: Local ``.torrent`` file.
        opts: Seeding options.
        link_dirs: Further collection folders to hardlink from when the
            torrent spans more than one LB entry.
        details: Optional dict filled in by :func:`build_seed_overlay` with
            what the overlay repair did, for a caller that must recheck the
            torrent in qBittorrent afterwards.

    Returns:
        (folder_path or None, human-readable reason).
    """
    if lb_number is None:
        return None, "recording has no LB number"

    allowed, why = database.is_seedable_to_tracker(lb_number)
    if not allowed and not (why == "lb_private" and opts.allow_private):
        return None, f"LB-{lb_number} not seedable ({why})"

    folders = [f for f in database.get_folders_for_lb(lb_number) if Path(f).is_dir()]
    # The tracker's LB number is a claim, not a fact (TODO-348): with the
    # overlay allowed, every same-date entry's folder is a candidate too, and
    # content decides. Ranked after the claimed LB's own folders so a genuine
    # tie still goes to the attribution.
    siblings = same_date_folders(lb_number) if opts.overlay else {}
    sibling_owner = {f: lb for lb, fs in siblings.items() for f in fs}
    if not folders and not siblings:
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
        if not folders:
            return None, f"no collection folder on disk for LB-{lb_number}"
        if not named:
            return None, (
                f"torrent root {info.name!r} matches no linked folder "
                f"(have {', '.join(Path(f).name for f in folders[:3])}) "
                f"— enable the overlay to seed regardless of folder naming"
            )
        return None, f"folder incomplete — {best} (enable the overlay to assemble one)"

    # Content first, the tracker's naming only as a last resort: a folder that
    # resolves nothing still beats no overlay at all when it is the named one.
    candidates = folders + [f for f in sibling_owner if f not in folders]
    source = best_source_folder(info, candidates, named) or (named[0] if named else None)
    if source is None:
        return None, (
            f"no linked or same-date folder shares enough files with the torrent "
            f"(have {', '.join(Path(f).name for f in candidates[:3])})"
        )
    owner = sibling_owner.get(source) if source not in folders else None
    if owner is not None:
        logger.warning(
            "LB-%d: tracker attribution looks wrong — the torrent's content "
            "is in LB-%d's folder %s; sourcing the overlay from there",
            lb_number, owner, source,
        )
        if details is not None:
            details["source_lb"] = owner
    folder, reason = build_seed_overlay(info, source, opts, best or "name mismatch",
                                        link_dirs, lb_number, details)
    if owner is not None:
        reason += f"; content matches LB-{owner}, not the claimed LB-{lb_number}"
    return folder, reason


def _qbt_connection() -> dict:
    """Collect the qBittorrent WebUI connection settings.

    Returns:
        Kwargs shared by every qBittorrent call: ``host``, ``port``,
        ``username``, ``password``, ``api_key``.
    """
    qbt_user, qbt_pass = get_credentials(SERVICE_QBT)
    _, qbt_key = get_credentials(SERVICE_QBT_KEY)
    return {
        "host": database.get_meta("qbt_host") or "localhost",
        "port": int(database.get_meta("qbt_port") or 8080),
        "username": qbt_user,
        "password": qbt_pass,
        "api_key": qbt_key,
    }


def recheck_seed(source_folder: str) -> dict:
    """Make qBittorrent re-hash a seed folder whose files changed underneath it.

    A torrent already in the client was hashed when it was added. When
    :func:`backend.seed_overlay.repair_overlay` then swaps a wrongly-picked
    file, qBittorrent keeps reporting the old, short result until it is told to
    look again — so a repaired overlay that is *not* rechecked stays at
    99-point-something forever, which is exactly the state TODO-337 set out to
    clear. Nothing here writes to disk.

    Args:
        source_folder: The folder qBittorrent is seeding from (the overlay).

    Returns:
        Dict with ``ok``, ``infohash`` (str, empty when the torrent could not
        be located) and ``error``.
    """
    conn = _qbt_connection()
    found = qbittorrent.find_torrent_by_path(source_folder, **conn)
    if not found.get("ok"):
        return {"ok": False, "infohash": "", "error": found.get("error") or
                "could not query qBittorrent"}
    infohash = found.get("infohash") or ""
    if not infohash:
        return {"ok": False, "infohash": "", "error": (
            f"no torrent in qBittorrent has {source_folder} as its content "
            f"path — nothing to recheck")}

    result = qbittorrent.recheck_torrent(infohash, **conn)
    return {"ok": bool(result.get("ok")), "infohash": infohash,
            "error": result.get("error") or ""}


def recheck_repaired_seed(
    source_folder: str, details: dict | None, qbt_result: dict
) -> bool:
    """Recheck a repaired overlay when qBittorrent already held the torrent.

    A freshly added torrent is hashed by the client on add, so it sees the
    repaired files anyway. An ``already_present`` one does not: it was hashed
    before :func:`backend.seed_overlay.repair_overlay` swapped a wrongly-picked
    file, and without a recheck it keeps reporting the old shortfall — the very
    stuck state TODO-337 exists to clear. Failures are logged, never raised:
    the seed itself succeeded.

    Args:
        source_folder: The folder handed to qBittorrent.
        details: The dict :func:`find_seedable_folder` filled in, or None.
        qbt_result: What :func:`qbt_seed` returned.

    Returns:
        True when qBittorrent accepted a recheck.
    """
    repaired = (details or {}).get("repaired") or []
    if not repaired:
        return False
    if not qbt_result.get("already_present"):
        logger.info(
            "  recheck: not needed — qBittorrent hashed the repaired overlay "
            "as it was added"
        )
        return False

    outcome = recheck_seed(source_folder)
    if outcome["ok"]:
        logger.info(
            "  recheck: qBittorrent re-hashing %s after %d repaired file(s)",
            outcome["infohash"][:12], len(repaired),
        )
        return True
    logger.warning(
        "  recheck FAILED for a repaired overlay (%s) — qBittorrent will keep "
        "reporting the old shortfall until it re-hashes %s: %s",
        ", ".join(Path(p).name for p in repaired[:3]), source_folder,
        outcome["error"],
    )
    return False


def qbt_seed(torrent_path: str, source_folder: str, opts: SeedOptions) -> dict:
    """Add a ``.torrent`` to qBittorrent pointed at an existing folder.

    Args:
        torrent_path: Local ``.torrent`` file.
        source_folder: Absolute path of the folder holding the files.
        opts: Seeding options; ``tracker`` becomes an extra qBittorrent tag.

    Returns:
        The qbittorrent module's result dict (``ok`` plus optional ``error``).
    """
    category = database.get_meta("qbt_category") or ""
    tags = ",".join(
        t for t in [database.get_meta("qbt_tags") or "", opts.tracker] if t
    )

    result = qbittorrent.add_torrent_for_seeding(
        torrent_path=torrent_path,
        source_folder=source_folder,
        category=category,
        tags=tags,
        **_qbt_connection(),
    )
    if result.get("ok") and opts.paused:
        logger.info("  (added; pause it in the qBittorrent UI if needed)")
    return result


def seed_torrent(
    lb_number: int | None,
    torrent_path: str,
    opts: SeedOptions,
    link_dirs: list[str] | None = None,
) -> dict:
    """Run the whole gate → overlay → qBittorrent sequence for one torrent.

    Args:
        lb_number: LB number the torrent claims to be.
        torrent_path: Local ``.torrent`` file.
        opts: Seeding options.
        link_dirs: Further collection folders to hardlink from when the
            torrent spans more than one LB entry.

    Returns:
        Dict with ``ok`` (bool), ``folder`` (str, the folder handed to
        qBittorrent, or ""), ``reason`` (str, why it was seedable or not),
        ``overlay`` (bool, whether ``folder`` is an assembled overlay),
        ``rechecked`` (bool, whether a repaired overlay was re-hashed by
        qBittorrent) and ``error`` (str, a qBittorrent failure) — ``reason``
        is always populated and is the line worth showing a user.
    """
    details: dict = {}
    folder, reason = find_seedable_folder(
        lb_number, torrent_path, opts, link_dirs, details
    )
    if not folder:
        return {"ok": False, "folder": "", "reason": reason, "overlay": False,
                "rechecked": False, "error": ""}

    is_overlay = Path(folder).parent.name == opts.overlay_dirname
    qbt = qbt_seed(torrent_path, folder, opts)
    if not qbt.get("ok"):
        return {"ok": False, "folder": folder, "reason": reason,
                "overlay": is_overlay, "rechecked": False,
                "error": qbt.get("error") or "qBittorrent refused"}
    rechecked = recheck_repaired_seed(folder, details, qbt)
    return {"ok": True, "folder": folder, "reason": reason, "overlay": is_overlay,
            "rechecked": rechecked, "error": ""}
