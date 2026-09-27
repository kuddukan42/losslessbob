#!/usr/bin/env python3
"""Restore the missing extras of WTRF seed overlays from local sources.

For every torrent carrying a qBittorrent tag (default ``missing extras``, as
written by ``tools/wtrf_tag_incomplete.py``) this re-plans the torrent's
existing overlay with :func:`backend.seed_overlay.plan_overlay` and
re-materialises **only the files qBittorrent reports incomplete** that a local
source can now satisfy: the collection folder (same-date siblings included),
``data/site/files``, or a re-fetch from losslessbob.com. Pieces that still hash
wrong are then handed to :func:`backend.seed_overlay.repair_overlay`, which
tries every same-size local candidate. Files no local source has are left to
the swarm.

Writes land only in the overlay; the collection folder is snapshotted and
checked unchanged. With ``--apply`` each touched torrent is stopped first,
then rechecked and restarted. Dry-run by default.

Usage::

    .venv/bin/python3 tools/wtrf_repair_extras.py            # preview
    .venv/bin/python3 tools/wtrf_repair_extras.py --apply    # repair + recheck
    .venv/bin/python3 tools/wtrf_repair_extras.py --tag "missing music" \
        --complete-only --apply    # only torrents that can reach 100% locally

Must be run from the project root directory.
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db as database  # noqa: E402
from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials  # noqa: E402
from backend.qbittorrent import _base_url, _login, _make_session  # noqa: E402
from backend.seed_overlay import (  # noqa: E402
    FETCH,
    OverlayPlan,
    build_overlay,
    choose_source_folder,
    collection_is_untouched,
    http_fetch,
    plan_overlay,
    repair_overlay,
    snapshot_folder,
)
from backend.torrent_verify import read_torrent  # noqa: E402
from backend.tracker_seed import SIDECAR_DIR, same_date_folders  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

EXPORT_DIR = _project_root / ".debug" / "wtrf_repair_extras"


def lb_for_seed_folder(folder: str) -> int | None:
    """Return the LB number whose WTRF download was seeded from ``folder``.

    Args:
        folder: The overlay directory qBittorrent seeds from.

    Returns:
        The LB number of the latest matching ``wtrf_downloads`` row, or None.
    """
    con = sqlite3.connect(database.DB_PATH)
    try:
        row = con.execute(
            "SELECT lb_number FROM wtrf_downloads WHERE seed_folder = ? "
            "ORDER BY attempted_at DESC LIMIT 1", (folder.rstrip("/"),),
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def repair_one(s, base: str, t: dict, apply: bool, complete_only: bool = False) -> str:
    """Plan (and with ``apply``, perform) the repair of one torrent's overlay.

    Args:
        s: Authenticated qBittorrent session.
        base: qBittorrent WebUI base URL.
        t: The torrent's ``/torrents/info`` entry.
        apply: Write files and recheck; otherwise only report.
        complete_only: Touch the overlay only when every missing file has a
            local source, so the torrent can reach 100%.

    Returns:
        A one-line outcome for the log.
    """
    overlay = Path(t["content_path"])
    lb = lb_for_seed_folder(str(overlay))
    if lb is None:
        return "skip: no wtrf_downloads row for this overlay"

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tpath = EXPORT_DIR / f"{t['hash']}.torrent"
    r = s.get(base + "/api/v2/torrents/export", params={"hash": t["hash"]}, timeout=30)
    r.raise_for_status()
    tpath.write_bytes(r.content)
    info = read_torrent(tpath)

    folders = [f for f in database.get_folders_for_lb(lb) if Path(f).is_dir()]
    folders += [f for fs in same_date_folders(lb).values() for f in fs
                if f not in folders and Path(f).is_dir()]
    source = choose_source_folder(info, folders, None) if folders else None
    if source is None:
        return f"LB-{lb:05d} skip: no collection folder supplies any file"

    names = [Path(p).name for p, _s in info.files]
    plan = plan_overlay(info, source, overlay.parent, [SIDECAR_DIR],
                        database.get_site_file_urls(names),
                        link_dirs=[f for f in folders if f != source],
                        overlay_name=overlay.name)

    files = s.get(base + "/api/v2/torrents/files",
                  params={"hash": t["hash"]}, timeout=30).json()
    missing = {f["name"] for f in files if f["progress"] < 1}
    fixable = [e for e in plan.entries if e.rel_path in missing and e.action != FETCH]
    left = len(missing) - len(fixable)
    mb = sum(e.size for e in fixable) / 1e6
    summary = (f"LB-{lb:05d} missing {len(missing)}: local source for {len(fixable)}"
               f" [{mb:.1f} MB]"
               f" ({', '.join(sorted({e.reason for e in fixable})) or '-'}), swarm {left}")
    if complete_only and left:
        return f"{summary} | skip: not completable locally"
    if not apply or not fixable:
        return summary

    s.post(base + "/api/v2/torrents/stop", data={"hashes": t["hash"]}, timeout=30)
    before = snapshot_folder(source)
    built = build_overlay(OverlayPlan(target_dir=plan.target_dir, entries=fixable),
                          fetcher=http_fetch)
    repair = repair_overlay(info, plan)
    touched = collection_is_untouched(source, before)
    if touched:
        logger.error("ABORT — collection changed: %s", ", ".join(touched[:3]))
        raise SystemExit(2)
    for err in built["errors"] + repair["errors"]:
        logger.warning("  %s", err)
    # Start before the recheck: a stopped torrent stays stopped after checking,
    # and a start sent mid-check is dropped.
    s.post(base + "/api/v2/torrents/start", data={"hashes": t["hash"]}, timeout=30)
    s.post(base + "/api/v2/torrents/recheck", data={"hashes": t["hash"]}, timeout=30)
    return (f"{summary} | wrote {built['linked'] + built['copied'] + built['refetched']}"
            f", repaired {len(repair['repaired'])}, rechecking")


def main() -> int:
    """Repair every tagged torrent's overlay; return an exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write files + recheck")
    ap.add_argument("--tag", default="missing extras", help="qBittorrent tag to repair")
    ap.add_argument("--complete-only", action="store_true",
                    help="only torrents whose every missing file has a local source")
    args = ap.parse_args()

    base = _base_url(database.get_meta("qbt_host") or "localhost",
                     int(database.get_meta("qbt_port") or 8080))
    user, pw = get_credentials(SERVICE_QBT)
    _, key = get_credentials(SERVICE_QBT_KEY)
    s = _make_session(base, key or "")
    if not key and (err := _login(s, base, user or "", pw or "")):
        logger.error(err["error"])
        return 1

    torrents = s.get(base + "/api/v2/torrents/info",
                     params={"tag": args.tag}, timeout=60).json()
    logger.info("%d torrent(s) tagged %r", len(torrents), args.tag)
    for t in torrents:
        try:
            logger.info("%s — %s", repair_one(s, base, t, args.apply, args.complete_only), t["name"][:60])
        except Exception as exc:  # one bad torrent must not stop the batch
            logger.warning("error on %s: %s", t["name"][:60], exc)
    if not args.apply:
        logger.info("dry run — re-run with --apply to write files and recheck")
    return 0


if __name__ == "__main__":
    sys.exit(main())
