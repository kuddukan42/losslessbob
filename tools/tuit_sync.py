"""Sync recordings from TUIT (tangledupintorrents.org) into the local DB.

Scrapes the newest recordings off ``/browse``, stores every field the site
exposes in ``tuit_recordings``, and can optionally fetch the personalised
``.torrent`` and hand it to qBittorrent pointed at files already in the
collection so the recording starts seeding instead of downloading.

Usage::

    python tools/tuit_sync.py                          # newest 5, metadata only
    python tools/tuit_sync.py --limit 20               # newest 20
    python tools/tuit_sync.py --pages 3                # first 3 listing pages
    python tools/tuit_sync.py --rec 1837               # one recording by id
    python tools/tuit_sync.py --fetch-torrents         # also save .torrent files
    python tools/tuit_sync.py --fetch-torrents --seed  # …and seed from collection
    python tools/tuit_sync.py --dry-run                # show the queue, no writes

Run from the project root. Credentials come from the OS keyring
(``losslessbob_tuit``); ``--username``/``--password`` override for a one-off.

Politeness: TUIT is a ~21-member private tracker. The default 3s delay between
requests is deliberate — do not lower it for bulk runs.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend import qbittorrent, tuit_scraper  # noqa: E402
from backend.credentials import (  # noqa: E402
    SERVICE_QBT,
    SERVICE_QBT_KEY,
    get_credentials,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tuit_sync")

DEFAULT_TORRENT_DIR = _project_root / "data" / "downloads" / "tuit"


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
    p.add_argument("--seed", action="store_true",
                   help="With --fetch-torrents: locate the recording's files in "
                        "my_collection (then folder_lb_link) and add the torrent "
                        "to qBittorrent for seeding.")
    p.add_argument("--paused", action="store_true",
                   help="Add torrents to qBittorrent in a stopped state.")
    p.add_argument("--force-seed", action="store_true",
                   help="Add to qBittorrent even when the torrent's root folder "
                        "name does not match the local folder. UNSAFE — "
                        "qBittorrent will start downloading instead of seeding.")
    p.add_argument("--username", default="", help="Override the stored username.")
    p.add_argument("--password", default="", help="Override the stored password.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the queue and exit without writing to the DB.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _qbt_seed(torrent_path: str, source_folder: str, paused: bool) -> dict:
    """Add a .torrent to qBittorrent pointed at an existing collection folder.

    Args:
        torrent_path: Local .torrent file.
        source_folder: Absolute path of the folder holding the files.
        paused: Add in a stopped state.

    Returns:
        The qbittorrent module's result dict (``ok`` plus optional ``error``).
    """
    host = database.get_meta("qbt_host") or "localhost"
    port = int(database.get_meta("qbt_port") or 8080)
    category = database.get_meta("qbt_category") or ""
    tags = ",".join(t for t in [database.get_meta("qbt_tags") or "", "tuit"] if t)
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
    if result.get("ok") and paused:
        logger.info("  (added; pause it in the qBittorrent UI if needed)")
    return result


def _match_local_folder(lb_number: int | None, torrent_path: str,
                        force: bool) -> tuple[str | None, str]:
    """Find a collection folder whose name matches the torrent's root folder.

    qBittorrent only resumes an existing download when the torrent's root name
    matches a directory inside ``save_path``. A mismatch silently turns a
    seed into a fresh download, so a non-matching folder is rejected unless
    ``force`` is set.

    Args:
        lb_number: LB number claimed by the recording.
        torrent_path: Local .torrent file.
        force: Accept a name mismatch anyway.

    Returns:
        (folder_path or None, human-readable reason).
    """
    if lb_number is None:
        return None, "recording has no LB number"

    folders = database.get_folders_for_lb(lb_number)
    if not folders:
        return None, f"no collection folder linked to LB-{lb_number}"

    root = tuit_scraper.torrent_root_name(torrent_path)
    if root:
        for folder in folders:
            if Path(folder).name == root:
                if not Path(folder).is_dir():
                    continue
                return folder, "root name matches"

    existing = [f for f in folders if Path(f).is_dir()]
    if not existing:
        return None, f"linked folder(s) for LB-{lb_number} not on disk"
    if force:
        return existing[0], (
            f"FORCED — torrent root {root!r} != folder {Path(existing[0]).name!r}"
        )
    return None, (
        f"torrent root {root!r} does not match linked folder "
        f"{Path(existing[0]).name!r} (use --force-seed to override)"
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
    rec = tuit_scraper.fetch_recording(session, rec_id, delay=args.delay)
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

    folder, reason = _match_local_folder(
        rec.lb_number, torrent_path, args.force_seed
    )
    if folder is None:
        database.add_tuit_download(
            rec.rec_id, rec.lb_number, torrent_path, "no_local_files", error=reason
        )
        logger.info("  seed: skipped — %s", reason)
        return "no_local_files"

    dl_id = database.add_tuit_download(
        rec.rec_id, rec.lb_number, torrent_path, "downloaded", seed_folder=folder
    )
    qbt = _qbt_seed(torrent_path, folder, args.paused)
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

    database.init_db()

    session = tuit_scraper.get_session(
        args.username, args.password, delay=args.delay
    )
    if session is None:
        print("TUIT login failed — check the keyring credentials.", file=sys.stderr)
        return 1

    rows_by_id: dict[int, object] = {}
    queue: list[int] = []

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
                if row.rec_id and row.rec_id not in rows_by_id:
                    rows_by_id[row.rec_id] = row
                    queue.append(row.rec_id)
    else:
        for row in tuit_scraper.fetch_recent(session, args.limit, delay=args.delay):
            if row.rec_id and row.rec_id not in rows_by_id:
                rows_by_id[row.rec_id] = row
                queue.append(row.rec_id)

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
