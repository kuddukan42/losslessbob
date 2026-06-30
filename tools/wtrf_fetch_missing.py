#!/usr/bin/env python3
"""Fetch WTRF torrent files for LosslessBob entries not yet in your collection.

Queries lb_master for public entries that are not in my_collection, starting
with the highest LB number first, and for each:
  1. Searches the WTRF forum for a matching torrent post.
  2. Downloads the .torrent file when a confident match is found.
  3. Optionally adds the torrent to qBittorrent for downloading.

Results are recorded in the wtrf_downloads table for review.

Usage examples::

    # Preview the first 10 missing items (no network requests)
    python tools/wtrf_fetch_missing.py --dry-run --limit 10

    # Fetch one specific LB entry
    python tools/wtrf_fetch_missing.py --lb 16642 --save-path /tmp/torrents

    # Fetch a specific list and/or range of LB numbers
    python tools/wtrf_fetch_missing.py --lbs 16640-16650,16700,16705-16708

    # Batch crawl newest 50 missing items, 3-second throttle, add to qBittorrent
    python tools/wtrf_fetch_missing.py --limit 50 --delay 3.0 --add-to-qbt

Must be run from the project root directory (the folder containing ``backend/``
and ``tools/``).
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so backend imports work.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend.wtrf_scraper import find_torrent_for_lb  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_CONF_EMOJI = {
    "definitive": "✓✓",
    "high":       "✓ ",
    "medium":     "~ ",
    "needs_review": "? ",
    "ambiguous":  "??",
    "not_found":  "✗ ",
}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch WTRF torrent files for missing LosslessBob entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    lb_group = p.add_mutually_exclusive_group()
    lb_group.add_argument(
        "--lb",
        type=int,
        default=None,
        metavar="N",
        help="Process a single LB number instead of the missing-items queue.",
    )
    lb_group.add_argument(
        "--lbs",
        type=str,
        default=None,
        metavar="SPEC",
        help="Process specific LB numbers instead of the missing-items queue: "
             "a comma/space-separated list and/or ranges, "
             "e.g. '16640,16642,16700' or '16640-16650,16700-16708'.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of entries to attempt in this run (default: all).",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=2.0,
        metavar="SECS",
        help="Seconds between HTTP requests (default: 2.0). Be polite.",
    )
    p.add_argument(
        "--save-path",
        default=None,
        metavar="DIR",
        help="Directory to write .torrent files into "
             "(default: data/downloads/wtrf/ under project root).",
    )
    p.add_argument(
        "--board-id",
        type=int,
        default=None,
        metavar="N",
        help="WTRF SMF board number to search (default: wtrf_board_id meta key, "
             "or 16 if unset).",
    )
    p.add_argument(
        "--add-to-qbt",
        action="store_true",
        help="Also add each downloaded torrent to qBittorrent via its WebUI API.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the work queue without making any network requests.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return p


def _parse_lb_spec(spec: str) -> list[int]:
    """Parse a ``--lbs`` value into an ordered list of LB numbers.

    Accepts comma/space-separated tokens, each either a single number
    (``16642``) or an inclusive range (``16640-16650``). Duplicates are
    dropped, first-seen order is preserved.

    Args:
        spec: Raw --lbs argument value.

    Returns:
        Ordered list of unique LB numbers.

    Raises:
        ValueError: If a token isn't a valid number or range.
    """
    numbers: list[int] = []
    seen: set[int] = set()
    for token in re.split(r"[,\s]+", spec.strip()):
        if not token:
            continue
        if "-" in token:
            start_s, _, end_s = token.partition("-")
            start, end = int(start_s), int(end_s)
            if start > end:
                start, end = end, start
            token_numbers = range(start, end + 1)
        else:
            token_numbers = (int(token),)
        for n in token_numbers:
            if n not in seen:
                seen.add(n)
                numbers.append(n)
    return numbers


def _qbt_add(torrent_path: str, save_path: str) -> bool:
    """Add a torrent to qBittorrent using stored credentials and meta settings.

    Args:
        torrent_path: Path to the .torrent file.
        save_path: Destination directory for downloaded content.

    Returns:
        True on success.
    """
    from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
    from backend.qbittorrent import add_torrent_for_download

    host     = database.get_meta("qbt_host") or "localhost"
    port     = int(database.get_meta("qbt_port") or 8080)
    category = database.get_meta("qbt_category") or ""
    tags     = database.get_meta("qbt_tags") or ""
    qbt_user, qbt_pass = get_credentials(SERVICE_QBT)
    _, qbt_key         = get_credentials(SERVICE_QBT_KEY)

    result = add_torrent_for_download(
        torrent_path=torrent_path,
        save_path=save_path,
        host=host, port=port,
        username=qbt_user, password=qbt_pass,
        category=category, tags=tags,
        api_key=qbt_key,
    )
    if not result.get("ok"):
        logger.warning("qBittorrent add failed: %s", result.get("error"))
    return bool(result.get("ok"))


def _print_row(
    lb: int,
    conf: str,
    signals: dict,
    status: str,
    error: str | None,
    topic_url: str | None = None,
    topic_url_2: str | None = None,
) -> None:
    icon = _CONF_EMOJI.get(conf, "  ")
    sig_str = " ".join(
        f"{k}={v}" for k, v in signals.items() if k != "has_torrent"
    )
    err_str = f"  [{error[:60]}]" if error else ""
    print(f"  {icon} LB-{lb:05d}  {conf:<12}  {status:<12}  {sig_str}{err_str}")
    if status == "skipped" and topic_url:
        print(f"       -> {topic_url}")
        if topic_url_2:
            print(f"       -> {topic_url_2}  (tied)")


def main() -> int:
    args = _build_parser().parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    database.init_db()

    save_path = args.save_path or str(_project_root / "data" / "downloads" / "wtrf")
    board_id  = args.board_id or int(database.get_meta("wtrf_board_id") or 16)

    # Build work queue
    if args.lb:
        queue = [args.lb]
    elif args.lbs:
        try:
            queue = _parse_lb_spec(args.lbs)
        except ValueError as exc:
            print(f"Invalid --lbs value {args.lbs!r}: {exc}", file=sys.stderr)
            return 1
    else:
        queue = database.get_wtrf_pending_lb_numbers()

    if args.limit:
        queue = queue[: args.limit]

    if not queue:
        print("No pending items in the queue.")
        return 0

    print(f"\nWTRF torrent fetcher — {len(queue)} item(s) | "
          f"delay={args.delay}s | save_path={save_path}")
    print(f"{'LB':>10}  {'date_str':<14}  {'location'}")
    print("-" * 72)

    if args.dry_run:
        for lb in queue:
            entry_data = database.get_entry(lb)
            entry = (entry_data or {}).get("entry", {})
            print(f"  LB-{lb:05d}  {entry.get('date_str', '?'):<14}  "
                  f"{(entry.get('location') or '')[:40]}")
        print(f"\n[dry-run] would attempt {len(queue)} item(s) — no requests sent.")
        return 0

    print()
    counts = {k: 0 for k in ("downloaded", "qbt_added", "skipped", "failed")}

    for i, lb_number in enumerate(queue, 1):
        print(f"[{i}/{len(queue)}] LB-{lb_number:05d}", end="  ", flush=True)

        result = find_torrent_for_lb(
            lb_number=lb_number,
            board_id=board_id,
            dest_dir=save_path,
            delay=args.delay,
        )

        conf    = result.get("confidence", "not_found")
        signals = result.get("signals", {})
        error   = result.get("error")

        if result["ok"]:
            status = "downloaded"
            counts["downloaded"] += 1
        elif conf in ("needs_review", "ambiguous", "not_found"):
            status = "skipped"
            counts["skipped"] += 1
        else:
            status = "failed"
            counts["failed"] += 1

        dl_id = database.add_wtrf_download(
            lb_number=lb_number,
            topic_url=result.get("topic_url"),
            torrent_path=result.get("torrent_path"),
            confidence=conf,
            signals_json=json.dumps(signals),
            status=status,
            error=error,
        )

        if result["ok"] and args.add_to_qbt:
            ok_qbt = _qbt_add(result["torrent_path"], save_path)
            if ok_qbt:
                from datetime import UTC, datetime
                database.update_wtrf_download(
                    dl_id, {
                        "status": "qbt_added",
                        "qbt_added_at": datetime.now(UTC).isoformat(),
                    }
                )
                status = "qbt_added"
                counts["qbt_added"] += 1

        _print_row(
            lb_number, conf, signals, status, error,
            topic_url=result.get("topic_url"),
            topic_url_2=result.get("topic_url_2"),
        )

    print("\n" + "-" * 72)
    print(f"Done.  downloaded={counts['downloaded']}  "
          f"qbt_added={counts['qbt_added']}  "
          f"skipped={counts['skipped']}  "
          f"failed={counts['failed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
