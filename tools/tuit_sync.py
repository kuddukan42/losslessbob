"""Sync recordings from TUIT (tangledupintorrents.org) into the local DB.

Scrapes the newest recordings off ``/browse``, stores every field the site
exposes in ``tuit_recordings``, and can optionally fetch the personalised
``.torrent`` and hand it to qBittorrent pointed at files already in the
collection so the recording seeds without downloading anything.

Seeding is gated three ways and is otherwise skipped, never forced:

* ``lb_status`` must be 'public' (``db.is_seedable_to_tracker``);
* a linked collection folder must exist whose name matches the torrent root;
* the folder must hash to 100 % against the torrent's pieces, checked locally
  and read-only by ``backend.torrent_verify`` before qBittorrent is contacted.

The third gate is the important one: qBittorrent given a 99 %-complete torrent
downloads the remainder *into* the collection folder. Curated folders are
never modified, so an incomplete match is reported and dropped.

Usage::

    python tools/tuit_sync.py                          # newest 5, metadata only
    python tools/tuit_sync.py --limit 20               # newest 20
    python tools/tuit_sync.py --pages 3                # first 3 listing pages
    python tools/tuit_sync.py --rec 1837               # one recording by id
    python tools/tuit_sync.py --fetch-torrents         # also save .torrent files
    python tools/tuit_sync.py --fetch-torrents --seed  # …and seed from collection
    python tools/tuit_sync.py --dry-run                # show the queue, no writes
    python tools/tuit_sync.py --set-credentials        # store/rotate the password

Run from the project root. Credentials come from the OS keyring
(``losslessbob_tuit``). ``--set-credentials`` prompts for them without echoing
and verifies with a real login; ``--username``/``--password`` override for a
one-off but land in your shell history.

Politeness: TUIT is a ~21-member private tracker. The default 3s delay between
requests is deliberate — do not lower it for bulk runs.
"""
from __future__ import annotations

import argparse
import getpass
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend import tuit_scraper  # noqa: E402
from backend.credentials import (  # noqa: E402
    SERVICE_TUIT,
    get_credentials,
    save_credentials,
)
from backend.seed_overlay import overlay_status  # noqa: E402
from backend.tracker_seed import (  # noqa: E402
    SeedOptions,
    find_seedable_folder,
    qbt_seed,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tuit_sync")

DEFAULT_TORRENT_DIR = _project_root / "data" / "downloads" / "tuit"
DEFAULT_HTML_DIR = _project_root / "data" / "downloads" / "tuit" / "html"


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    p = argparse.ArgumentParser(
        description="Scrape newest TUIT recordings into the local DB."
    )
    p.add_argument("--limit", type=int, default=5,
                   help="How many recordings to sync (default 5).")
    p.add_argument("--pages", type=int,
                   help="Sync whole listing pages instead of --limit rows "
                        "(50 rows/page). Overrides --limit.")
    p.add_argument("--rec", type=int, action="append",
                   help="Sync a specific recording id. Repeatable.")
    p.add_argument("--delay", type=float, default=tuit_scraper.DEFAULT_DELAY,
                   help="Seconds between HTTP requests (default 3.0).")
    p.add_argument("--fetch-torrents", action="store_true",
                   help="Also download each recording's personalised .torrent.")
    p.add_argument("--torrent-dir", default=str(DEFAULT_TORRENT_DIR),
                   help="Where to write .torrent files.")
    p.add_argument("--html-dir", default=str(DEFAULT_HTML_DIR),
                   help="Where the raw /recordings/<id> detail pages are "
                        "archived as rec-<id>.html (default "
                        "data/downloads/tuit/html).")
    p.add_argument("--no-save-html", action="store_true",
                   help="Do not archive the raw detail-page HTML.")
    p.add_argument("--seed", action="store_true",
                   help="With --fetch-torrents: locate the recording's files in "
                        "my_collection (then folder_lb_link) and add the torrent "
                        "to qBittorrent for seeding — only when lb_status is "
                        "'public' AND the folder already hashes to 100%%. "
                        "Collection folders are never written to.")
    p.add_argument("--paused", action="store_true",
                   help="Add torrents to qBittorrent in a stopped state.")
    p.add_argument("--overlay", action="store_true",
                   help="When the collection folder is not 100%%, assemble a "
                        "separate seed folder instead of giving up: audio "
                        "hardlinked from the collection (no extra disk space), "
                        "LBF sidecars copied from data/site/files. The "
                        "collection is never written to.")
    p.add_argument("--overlay-root", default="",
                   help="Where overlays are created. Default <mount>/TUIT Seeds, "
                        "chosen on the source's own filesystem so hardlinks work.")
    p.add_argument("--refetch-sidecars", action="store_true",
                   help="With --overlay: re-download sidecars from "
                        "losslessbob.com when the crawl's stored copy is the "
                        "wrong size (saved HTML was link-rewritten). Often the "
                        "difference between 99.7%% and a fully local 100%%.")
    p.add_argument("--max-fetch-mb", type=float, default=25.0,
                   help="Refuse an overlay that would still leave more than this "
                        "many MB for the swarm to download (default 25).")
    p.add_argument("--allow-partial-overlay", action="store_true",
                   help="Seed an overlay that is not yet 100%%. The remainder "
                        "downloads into the overlay — never the collection.")
    p.add_argument("--rescan", action="store_true",
                   help="Include recordings that already have a tuit_downloads "
                        "attempt (default: --pages/--limit skip them so re-runs "
                        "advance past what was already scanned). Ignored with "
                        "--rec, which always processes the ids given.")
    p.add_argument("--check-overlays", action="store_true",
                   help="List every recorded seed overlay and flag any whose "
                        "collection folder was deleted or moved to another "
                        "drive, leaving the overlay holding the only copy of "
                        "those bytes. Exits 1 if any are orphaned.")
    p.add_argument("--set-credentials", action="store_true",
                   help="Prompt for the TUIT username and password, store them "
                        "in the OS keyring, verify them with a login, and exit. "
                        "The password is never echoed, written to disk, or put "
                        "in your shell history. Use this after rotating it.")
    p.add_argument("--username", default="", help="Override the stored username.")
    p.add_argument("--password", default="",
                   help="Override the stored password for one run. Prefer "
                        "--set-credentials; an argument here lands in your "
                        "shell history.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the queue and exit without writing to the DB.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _set_credentials(delay: float) -> int:
    """Prompt for TUIT credentials, store them in the keyring, verify by login.

    Args:
        delay: Seconds between the token fetch and the login POST.

    Returns:
        A process exit code — 0 when the stored credentials logged in.
    """
    current, _pw = get_credentials(SERVICE_TUIT)
    prompt = f"TUIT username [{current}]: " if current else "TUIT username: "
    username = input(prompt).strip() or current
    if not username:
        print("No username given.", file=sys.stderr)
        return 1

    password = getpass.getpass("TUIT password (not echoed): ")
    if not password:
        print("No password given.", file=sys.stderr)
        return 1

    stored = save_credentials(SERVICE_TUIT, username, password)
    print(f"Stored: {stored.label}")
    if "Session only" in stored.label:
        print("WARNING: no OS keyring backend — this will not survive a reboot.",
              file=sys.stderr)

    session = tuit_scraper.get_session(username, password, delay=delay)
    if session is None:
        print("Login FAILED with these credentials — they are stored but wrong.",
              file=sys.stderr)
        return 1
    print(f"Login OK as {username}.")
    return 0


def _check_overlays() -> int:
    """Report every recorded seed overlay and whether it has been orphaned.

    A same-volume collection rename leaves an overlay perfectly healthy — the
    hardlinks follow the inode. A delete or cross-volume move drops the link
    count to 1, and the overlay silently becomes the only holder of those
    bytes, so the disk space is never reclaimed. That is what this flags.

    Returns:
        A process exit code — 1 when at least one overlay looks orphaned.
    """
    # get_tuit_downloads() is newest-first, so the first row per LB is the seed
    # currently in force; earlier attempts have been superseded.
    latest: dict[int, str] = {}
    for row in database.get_tuit_downloads():
        folder = row.get("seed_folder")
        lb_number = row.get("lb_number")
        if folder and lb_number is not None and lb_number not in latest:
            latest[lb_number] = folder

    if not latest:
        print("No seed overlays recorded.")
        return 0

    collection_roots = [
        m["root_path"] for m in database.get_collection_mounts() if m.get("root_path")
    ]

    print(f"\n{len(latest)} recorded seed folder(s):\n")
    orphans = 0
    pinned_total = 0
    for lb_number, folder in sorted(latest.items()):
        status = overlay_status(folder)
        label = f"LB-{lb_number:05d}"
        kind = (
            "direct" if any(folder.startswith(r) for r in collection_roots)
            else "overlay"
        )
        if not status.exists:
            print(f"  {label}  GONE      {folder}")
            continue
        flag = "ORPHANED" if status.orphaned else "ok      "
        if status.orphaned:
            orphans += 1
            pinned_total += status.pinned_bytes
        print(f"  {label}  {flag}  [{kind}] {folder}")
        print(f"           {status.summary()}")

    if orphans:
        print(
            f"\n{orphans} overlay(s) now hold the only copy of their audio "
            f"({pinned_total / 1e9:.2f} GB). Their collection folder was deleted "
            f"or moved to another drive. Deleting an overlay reclaims that space "
            f"— but check you still have the recording elsewhere first."
        )
        return 1
    print("\nAll overlays still share their audio with the collection.")
    return 0


def _seed_options(args) -> SeedOptions:
    """Translate parsed CLI arguments into a tracker_seed option set.

    Args:
        args: Parsed CLI arguments.

    Returns:
        The SeedOptions describing this run's TUIT seeding policy.
    """
    return SeedOptions(
        tracker="tuit",
        overlay=args.overlay,
        overlay_root=args.overlay_root,
        refetch_sidecars=args.refetch_sidecars,
        max_fetch_mb=args.max_fetch_mb,
        allow_partial_overlay=args.allow_partial_overlay,
        paused=args.paused,
    )


def _sync_one(session, rec_id: int, row, args) -> str:
    """Fetch, store and optionally seed a single recording.

    Args:
        session: Authenticated TUIT session.
        rec_id: Site recording id.
        row: The BrowseRow that led here, or None.
        args: Parsed CLI arguments.

    Returns:
        A short status word for the summary counter.
    """
    html_dir = None if args.no_save_html else args.html_dir
    rec = tuit_scraper.fetch_recording(
        session, rec_id, delay=args.delay, html_dir=html_dir
    )
    if rec is None:
        logger.warning("  rec %s: detail page unavailable", rec_id)
        return "failed"
    if row is not None:
        tuit_scraper.merge_row_into_recording(rec, row)

    stored = rec.as_dict()
    stored.pop("lineage_nodes", None)
    stored.pop("setlist", None)
    stored.pop("files", None)
    stored.pop("siblings", None)
    stored.update(tuit_scraper.recording_to_json_fields(rec))
    if row is not None:
        stored["added_at"] = row.added_at
        stored["uploader_url"] = row.uploader_url

    database.upsert_tuit_recording(stored)
    logger.info(
        "  stored rec %s | LB-%s | %s | %s | %s | %s files | %s",
        rec.rec_id, rec.lb_number or "?", rec.date_str or "?",
        rec.title or rec.venue, rec.source_type, rec.n_files or "?", rec.quality,
    )

    if not args.fetch_torrents:
        return "stored"

    result = tuit_scraper.download_torrent(
        session, rec, args.torrent_dir, delay=args.delay
    )
    if not result["ok"]:
        database.add_tuit_download(
            rec.rec_id, rec.lb_number, None, "failed", error=result["error"]
        )
        logger.warning("  torrent: %s", result["error"])
        return "failed"

    torrent_path = result["torrent_path"]
    logger.info("  torrent: %s", torrent_path)

    if not args.seed:
        database.add_tuit_download(
            rec.rec_id, rec.lb_number, torrent_path, "downloaded"
        )
        return "downloaded"

    opts = _seed_options(args)
    folder, reason = find_seedable_folder(rec.lb_number, torrent_path, opts)
    if folder is None:
        database.add_tuit_download(
            rec.rec_id, rec.lb_number, torrent_path, "not_seeded", error=reason
        )
        logger.info("  seed: skipped, folder untouched — %s", reason)
        return "not_seeded"

    dl_id = database.add_tuit_download(
        rec.rec_id, rec.lb_number, torrent_path, "downloaded", seed_folder=folder
    )
    qbt = qbt_seed(torrent_path, folder, opts)
    if qbt.get("ok"):
        database.update_tuit_download(dl_id, {
            "status": "qbt_added",
            "qbt_added_at": datetime.now(UTC).isoformat(),
        })
        logger.info("  seed: qBittorrent added, seeding from %s (%s)", folder, reason)
        return "qbt_added"

    database.update_tuit_download(dl_id, {
        "status": "failed", "error": qbt.get("error", "qbt add failed"),
    })
    logger.warning("  seed: qBittorrent refused — %s", qbt.get("error"))
    return "failed"


def main() -> int:
    """Entry point. Returns a process exit code."""
    args = _build_parser().parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.set_credentials:
        return _set_credentials(args.delay)

    database.init_db()

    if args.check_overlays:
        return _check_overlays()

    session = tuit_scraper.get_session(
        args.username, args.password, delay=args.delay
    )
    if session is None:
        print("TUIT login failed — check the keyring credentials.", file=sys.stderr)
        return 1

    rows_by_id: dict[int, object] = {}
    queue: list[int] = []
    known_ids = set() if args.rescan else database.get_tuit_download_rec_ids()
    skipped_known = 0

    if args.rec:
        queue = list(dict.fromkeys(args.rec))
    elif args.pages:
        for page in range(1, args.pages + 1):
            rows, total, _ = tuit_scraper.fetch_browse_page(
                session, page=page, delay=args.delay
            )
            if page == 1 and total:
                logger.info("TUIT catalogue: %s recordings", f"{total:,}")
            for row in rows:
                if not row.rec_id or row.rec_id in rows_by_id:
                    continue
                if row.rec_id in known_ids:
                    skipped_known += 1
                    continue
                rows_by_id[row.rec_id] = row
                queue.append(row.rec_id)
    else:
        page = 1
        while len(queue) < args.limit:
            rows, _total, _html = tuit_scraper.fetch_browse_page(
                session, page=page, delay=args.delay
            )
            if not rows:
                break
            for row in rows:
                if not row.rec_id or row.rec_id in rows_by_id:
                    continue
                if row.rec_id in known_ids:
                    skipped_known += 1
                    continue
                rows_by_id[row.rec_id] = row
                queue.append(row.rec_id)
                if len(queue) >= args.limit:
                    break
            page += 1

    if skipped_known:
        logger.info(
            "  skipped %s already-scanned recording(s) (use --rescan to include)",
            skipped_known,
        )

    if not queue:
        print("Nothing to sync.")
        return 0

    if args.dry_run:
        print(f"\n[dry-run] {len(queue)} recording(s) would be synced:")
        for rec_id in queue:
            row = rows_by_id.get(rec_id)
            if row is None:
                print(f"  rec {rec_id}")
            else:
                print(f"  rec {rec_id:>6}  LB-{row.lb_number or '?':<7} "
                      f"{row.date_str:<12} {row.source_type:<4} "
                      f"{row.venue_location[:44]}")
        print("\nNo requests beyond the listing were sent.")
        return 0

    print(f"\nTUIT sync — {len(queue)} recording(s) | delay={args.delay}s")
    counts: dict[str, int] = {}
    for i, rec_id in enumerate(queue, 1):
        print(f"[{i}/{len(queue)}] rec {rec_id}")
        status = _sync_one(session, rec_id, rows_by_id.get(rec_id), args)
        counts[status] = counts.get(status, 0) + 1

    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
