#!/usr/bin/env python3
"""Post a recording to TUIT and seed it.

Dry run by default: the payload is composed, the torrent is built and every
gap is reported, but nothing is sent. ``--apply`` is the only flag that
POSTs.

Examples:
    # See exactly what would be submitted for LB-00707, no torrent hashing
    .venv/bin/python3 tools/tuit_upload.py 707 --no-torrent

    # Full dry run: build the .torrent too, resolve the show, list warnings
    .venv/bin/python3 tools/tuit_upload.py 707

    # Actually upload and hand it to qBittorrent
    .venv/bin/python3 tools/tuit_upload.py 707 --apply | tee tuit_upload.log
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db as database  # noqa: E402
from backend import tracker_seed, tuit_scraper, tuit_upload  # noqa: E402

logger = logging.getLogger("tuit_upload")

#: Fields worth showing first in the dry-run dump — the ones a curator checks.
FIELD_ORDER = (
    "lb_number", "show_id", "new_show_date", "new_venue", "new_city",
    "new_state", "new_country", "new_tour", "source_type", "format",
    "audio_quality", "bit_depth", "sample_rate", "taper", "equipment",
    "recording_position", "lineage", "tags", "allow_partial",
)


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("lb_number", type=int, help="LB number to upload.")
    p.add_argument("--apply", action="store_true",
                   help="Actually POST the upload. Without this nothing is sent.")
    p.add_argument("--folder", default="",
                   help="Override the source folder (default: the collection folder).")
    p.add_argument("--no-torrent", action="store_true",
                   help="Skip generating the .torrent (faster dry run; cannot --apply).")
    p.add_argument("--no-seed", action="store_true",
                   help="Upload but do not hand the torrent to qBittorrent.")
    p.add_argument("--allow-duplicate", action="store_true",
                   help="Upload even though TUIT already has this LB number or infohash.")
    p.add_argument("--no-overlay", action="store_true",
                   help="Refuse to seed from an assembled overlay folder.")
    p.add_argument("--paused", action="store_true",
                   help="Add the torrent to qBittorrent stopped.")
    p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                   help="Override or add one form field; repeatable.")
    p.add_argument("--json", action="store_true",
                   help="Print the payload as JSON instead of a table.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _apply_overrides(fields: dict, overrides: list[str]) -> list[str]:
    """Apply ``FIELD=VALUE`` overrides onto the composed fields.

    Args:
        fields: The payload's form fields, mutated in place.
        overrides: Raw ``FIELD=VALUE`` strings from the CLI.

    Returns:
        Notes describing each override, for the run's output.
    """
    notes = []
    for raw in overrides:
        if "=" not in raw:
            notes.append(f"ignored --set {raw!r}: expected FIELD=VALUE")
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        fields[key] = value
        notes.append(f"override: {key} = {value!r}")
    return notes


def _print_payload(payload: tuit_upload.UploadPayload) -> None:
    """Print a composed payload as an aligned field table."""
    fields = payload.fields
    print(f"\n  LB-{payload.lb_number:05d}   {payload.source_folder}")
    if payload.show:
        print(f"  show      /shows/{payload.show['id']}  {payload.show.get('label', '')}")
    else:
        print("  show      NEW (the new_show_* fields will create one)")
    print()
    ordered = [k for k in FIELD_ORDER if k in fields]
    ordered += [k for k in fields if k not in FIELD_ORDER]
    for key in ordered:
        value = str(fields[key]).replace("\n", " ⏎ ")
        if len(value) > 110:
            value = value[:107] + "…"
        print(f"    {key:20} {value}")
    print(f"\n    {'info_file':20} {payload.info_path or '— none —'}")
    print(f"    {'torrent_file':20} {payload.torrent_path or '— not built —'}")
    if payload.info_hash:
        print(f"    {'info_hash':20} {payload.info_hash}")


def main(argv: list[str] | None = None) -> int:
    """Compose, show and optionally post one TUIT upload.

    Args:
        argv: Argument vector; ``sys.argv[1:]`` when omitted.

    Returns:
        Process exit code — 0 on success, 1 on any refusal or failure.
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.apply and args.no_torrent:
        logger.error("--apply needs a .torrent; drop --no-torrent")
        return 1

    # init_db also binds the write queue every DB write in this path goes through.
    database.init_db()

    session = tuit_scraper.get_session()
    if session is None:
        logger.warning("No TUIT session — show_id cannot be resolved")
        if args.apply:
            logger.error("refusing to --apply without a session")
            return 1

    try:
        payload = tuit_upload.prepare_upload(
            args.lb_number,
            session=session,
            source_folder=args.folder,
            make_torrent=not args.no_torrent,
        )
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    notes = _apply_overrides(payload.fields, args.set)
    if notes:
        payload.warnings.extend(notes)
        # Keep the filed 'prepared' row honest about what would actually be sent.
        database.update_tuit_upload(
            payload.upload_id,
            {"payload_json": json.dumps(payload.as_dict(), ensure_ascii=False)},
        )

    if args.json:
        print(json.dumps(payload.as_dict(), indent=2, ensure_ascii=False))
    else:
        _print_payload(payload)

    if payload.warnings:
        print("\n  Warnings:")
        for warning in payload.warnings:
            print(f"    ! {warning}")

    if not args.apply:
        print("\n  DRY RUN — nothing was sent. Re-run with --apply to upload.\n")
        return 0

    result = tuit_upload.post_upload(
        session, payload, allow_duplicate=args.allow_duplicate
    )
    if not result["ok"]:
        logger.error("upload refused: %s", result["error"])
        return 1
    print(f"\n  UPLOADED  {result['url']}")

    if args.no_seed:
        return 0

    opts = tracker_seed.SeedOptions(
        tracker="tuit", overlay=not args.no_overlay, paused=args.paused,
    )
    seeded = tracker_seed.seed_torrent(args.lb_number, payload.torrent_path, opts)
    status = "SEEDING" if seeded.get("ok") else "NOT SEEDED"
    print(f"  {status}  {seeded.get('reason', '')} {seeded.get('error', '')}".rstrip())
    return 0 if seeded.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
