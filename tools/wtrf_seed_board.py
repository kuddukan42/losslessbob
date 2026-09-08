#!/usr/bin/env python3
"""Walk the WTRF board and seed every post the collection can already supply.

The seeding counterpart of ``tools/wtrf_fetch_missing.py``, which goes the
other way and fetches recordings *not* held. This crawls the board itself —
newest first, then backwards in time — so old posts whose swarm has died get a
seeder again.

Every topic seen is written to ``wtrf_downloads``, which doubles as the resume
state: re-running walks the same pages but only stops on topics never tried.

Examples::

    # What would the newest two pages do? No requests for torrents, no seeding.
    tools/wtrf_seed_board.py --pages 2 --dry-run

    # Seed the newest page for real.
    tools/wtrf_seed_board.py --pages 1

    # Work backwards through the board, ten pages a night.
    tools/wtrf_seed_board.py --start-page 12 --pages 10 --limit 40
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db as database  # noqa: E402
from backend.paths import DATA_DIR  # noqa: E402
from backend.tracker_seed import SeedOptions  # noqa: E402
from backend.wtrf_board import TOPICS_PER_PAGE, seed_board  # noqa: E402

logger = logging.getLogger("wtrf_seed_board")


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser.

    Returns:
        The configured parser.
    """
    p = argparse.ArgumentParser(
        description="Seed WTRF posts whose recordings are already in the "
                    "collection, walking the board newest-first.",
        epilog="Attempts are recorded in wtrf_downloads; re-runs skip what was "
               "already tried unless --rescan is given.",
    )
    p.add_argument("--board-id", type=int, default=None,
                   help="WTRF SMF board number (default: the wtrf_board_id meta "
                        "key, or 16).")
    p.add_argument("--start-page", type=int, default=1,
                   help=f"Board page to start on, 1 = newest (default: 1). "
                        f"Page N covers topics {TOPICS_PER_PAGE}(N-1)"
                        f"..{TOPICS_PER_PAGE}N.")
    p.add_argument("--pages", type=int, default=1,
                   help=f"How many listing pages to walk this run "
                        f"(default: 1, i.e. {TOPICS_PER_PAGE} topics).")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after this many topics have been attempted. "
                        "Topics skipped as already-seen do not count.")
    p.add_argument("--delay", type=float, default=2.0,
                   help="Seconds between HTTP requests (default: 2.0). "
                        "Be polite.")
    p.add_argument("--rescan", action="store_true",
                   help="Re-attempt topics that already have a wtrf_downloads "
                        "row (default: skip them, which is how a run resumes).")
    p.add_argument("--include-missing", action="store_true",
                   help="Also handle posts whose recording is not in the "
                        "collection — downloads the torrent so the swarm can "
                        "supply it. Off by default: this tool seeds.")
    p.add_argument("--save-path", default=str(DATA_DIR / "downloads" / "wtrf"),
                   help="Directory for downloaded .torrent files "
                        "(default: data/downloads/wtrf/).")
    p.add_argument("--dry-run", action="store_true",
                   help="Resolve each post and report, but download nothing "
                        "and seed nothing.")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable DEBUG logging.")

    seeding = p.add_argument_group("seeding policy")
    seeding.add_argument("--no-overlay", dest="overlay", action="store_false",
                         help="Refuse a post unless the collection folder can "
                              "seed in place (default: assemble an overlay "
                              "under <mount>/WTRF Seeds; the collection is "
                              "never written to).")
    seeding.add_argument("--overlay-root", default="",
                         help="Where overlays are created. Default "
                              "<mount>/WTRF Seeds, chosen on the source's own "
                              "filesystem so hardlinks work.")
    seeding.add_argument("--no-refetch-sidecars", dest="refetch_sidecars",
                         action="store_false",
                         help="Do not re-download sidecars from losslessbob.com "
                              "when the crawl's stored copy is the wrong size "
                              "(default: re-fetch; often the difference between "
                              "99.7%% and a fully local 100%%).")
    seeding.add_argument("--max-fetch-mb", type=float, default=25.0,
                         help="Refuse an overlay that would still leave more "
                              "than this many MB for the swarm (default: 25).")
    seeding.add_argument("--no-allow-partial-overlay",
                         dest="allow_partial_overlay", action="store_false",
                         help="Refuse an overlay that still hashes short "
                              "(default: accept it — the remainder downloads "
                              "into the overlay, never the collection).")
    seeding.add_argument("--paused", action="store_true",
                         help="Add each torrent to qBittorrent stopped.")
    return p


def _seed_options(args: argparse.Namespace) -> SeedOptions:
    """Translate parsed CLI arguments into a tracker_seed option set.

    Args:
        args: Parsed CLI arguments.

    Returns:
        The SeedOptions describing this run's WTRF seeding policy.
    """
    return SeedOptions(
        tracker="wtrf",
        overlay=args.overlay,
        overlay_root=args.overlay_root,
        refetch_sidecars=args.refetch_sidecars,
        max_fetch_mb=args.max_fetch_mb,
        allow_partial_overlay=args.allow_partial_overlay,
        paused=args.paused,
    )


def main() -> int:
    """Run the board walk.

    Returns:
        Process exit code — 0 unless the crawl could not start.
    """
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    database.init_db()

    dest = Path(args.save_path)
    dest.mkdir(parents=True, exist_ok=True)
    start_offset = max(0, args.start_page - 1) * TOPICS_PER_PAGE

    exit_code = 0
    for event in seed_board(
        opts=_seed_options(args),
        dest_dir=dest,
        board_id=args.board_id,
        start_offset=start_offset,
        pages=args.pages,
        limit=args.limit,
        delay=args.delay,
        dry_run=args.dry_run,
        rescan=args.rescan,
        include_missing=args.include_missing,
    ):
        if event["event"] == "start":
            logger.info("board %d: pages %d-%d, %d topic(s) already attempted",
                        event["board_id"], args.start_page,
                        args.start_page + args.pages - 1, event["known"])
        elif event["event"] == "topic":
            lb = f"LB-{event['lb_number']:05d}" if event["lb_number"] else "LB-?????"
            detail = event["error"] or event["reason"]
            logger.info("%-10s %-9s %-7s %s | %s", event["topic_id"], lb,
                        event["status"], event["title"][:58], detail[:90])
        else:
            if event.get("error"):
                logger.error("%s", event["error"])
                exit_code = 1
            logger.info("done: %d attempted, %d seeded, %d skipped, "
                        "%d refused, %d failed",
                        event.get("attempted", 0), event.get("seeded", 0),
                        event.get("skipped", 0), event.get("refused", 0),
                        event.get("failed", 0))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
