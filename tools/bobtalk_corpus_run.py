"""Run the TODO-303 bobtalk locate pass across the corpus, one source per date.

Every date Olof records bobtalk for is covered exactly once, using the best
recording we hold for it. That is the cheap way to full coverage: a second
source of the same show mostly re-finds the same quotes, so redundancy is worth
buying only for dates the first pass does badly on. `--all-sources` on
``bobtalk_locate.py`` fills those in later, per date, without redoing this.

Best source = ``show_picks`` rank 1 when that recording is collected and on
disk (the derived per-date "best of" ranking, FABLE_UNIFIED_RANKING §3/§4),
else the lowest collected LB number for the date.

Searches each recording END TO END by default (``bobtalk_locate --full-show``).
The first corpus pass used track-boundary windows and located 998 of 3,301
quotes; boundary windows only cover about a fifth of a show, so quotes spoken
away from a track split could not be found at any threshold. ``--boundaries``
restores the old geometry.

Resumable by design, because this is a long run: a date whose chosen source
already carries locations for the current model AND geometry is skipped, so
re-launching after an interrupt continues rather than restarts. Rows from the
boundary pass do not count as done for a full-show run. SIGINT/SIGTERM finish the
recording in flight and then stop, which keeps the database consistent — a
half-written recording is never left behind.

Usage:
    .venv/bin/python3 tools/bobtalk_corpus_run.py            # the full run
    .venv/bin/python3 tools/bobtalk_corpus_run.py --dry-run  # plan only, no ASR
    .venv/bin/python3 tools/bobtalk_corpus_run.py --limit 20
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(APP_ROOT / "tools" / "tapematch"))

from backend import bobtalk as bt  # noqa: E402
from backend import bobtalk_decodes as dec  # noqa: E402
from backend import paths as bpaths  # noqa: E402
from tools import bobtalk_locate as loc  # noqa: E402

log = logging.getLogger("bobtalk_corpus")

LOCK_PATH = bpaths.DATA_DIR / "bobtalk_corpus_run.lock"
LOG_PATH = bpaths.LOGS_DIR / "bobtalk_corpus.log"

_stop = False


def _request_stop(signum: int, _frame) -> None:
    """Ask the loop to stop after the recording currently in flight."""
    global _stop
    _stop = True
    log.warning("signal %s received — finishing this recording, then stopping", signum)


def acquire_lock() -> bool:
    """Take the single-instance lock.

    Two concurrent passes would fight over the same rows and the same GPU, so
    a second launch refuses rather than interleaving. A lock left behind by a
    killed process is reclaimed.

    Returns:
        True if the lock is now held by this process.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
            os.kill(pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            log.warning("reclaiming stale lock %s", LOCK_PATH)
        else:
            log.error("already running as pid %s (%s)", pid, LOCK_PATH)
            return False
    LOCK_PATH.write_text(str(os.getpid()))
    return True


def plan(conn: sqlite3.Connection) -> list[tuple[str, int, int, str]]:
    """Choose one recording per bobtalk date.

    Args:
        conn: Open main-database connection.

    Returns:
        ``(date_str, event_id, lb_number, disk_path)`` per covered date, in
        date order. Dates with no collected audio are omitted.
    """
    collected: dict[str, list[tuple[int, str]]] = {}
    for lb, folder, dp in conn.execute(
            "SELECT lb_number, folder_name, disk_path FROM my_collection"):
        if not dp or not (folder or ""):
            continue
        date_str = folder[:10]
        if len(date_str) == 10 and date_str[4] == "-" and Path(dp).is_dir():
            collected.setdefault(date_str, []).append((int(lb), dp))

    picks: dict[str, int] = {}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "show_picks" in tables:
        for date_iso, lb in conn.execute(
                "SELECT concert_date_iso, lb_number FROM show_picks WHERE pick_rank = 1"):
            if date_iso:
                picks[date_iso] = int(lb)

    out = []
    for date_str, event_id in conn.execute(
            "SELECT date_str, event_id FROM olof_events o WHERE bobtalk IS NOT NULL "
            "AND TRIM(bobtalk) <> '' AND LENGTH(bobtalk) = ("
            "  SELECT MAX(LENGTH(bobtalk)) FROM olof_events x WHERE x.date_str = o.date_str"
            "   AND x.bobtalk IS NOT NULL AND TRIM(x.bobtalk) <> '') "
            "GROUP BY date_str ORDER BY date_str"):
        sources = collected.get(date_str)
        if not sources:
            continue
        by_lb = dict(sources)
        lb = picks.get(date_str) if picks.get(date_str) in by_lb else min(by_lb)
        out.append((date_str, int(event_id), lb, by_lb[lb]))
    return out


def already_done(conn: sqlite3.Connection, lb_number: int, event_id: int, model: str,
                 geometry: str) -> bool:
    """Return whether this recording already carries locations for *model*.

    Geometry is part of the question, not a detail: rows from the weaker
    boundary pass must not make a full-show run skip the recording, or the
    upgrade silently covers nothing.

    Args:
        conn: Open main-database connection.
        lb_number: Recording to check.
        event_id: Event whose quotes were searched for.
        model: ASR model the existing rows must have used.
        geometry: Search geometry the existing rows must have used.

    Returns:
        True when an equivalent pass has already been stored.
    """
    row = conn.execute(
        "SELECT 1 FROM bobtalk_locations WHERE lb_number = ? AND event_id = ? "
        "AND model = ? AND geometry = ? LIMIT 1",
        (lb_number, event_id, model, geometry)).fetchone()
    return row is not None


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=0, help="stop after N recordings (0 = all)")
    p.add_argument("--dry-run", action="store_true", help="print the plan, decode nothing")
    p.add_argument("--model", default=loc.DEFAULT_MODEL)
    p.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    p.add_argument("--compute-type", default=None)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--boundaries", dest="full_show", action="store_false",
                   help="search track boundaries only (the original, weaker geometry)")
    p.add_argument("--redo", action="store_true",
                   help="re-locate recordings that already have rows for this pass")
    args = p.parse_args()
    geometry = bt.GEOM_FULL if args.full_show else bt.GEOM_BOUNDARIES

    bpaths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if not args.dry_run:
        handlers.append(logging.FileHandler(LOG_PATH))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")

    conn = sqlite3.connect(str(bpaths.DB_PATH))
    bt.ensure_schema(conn)   # already_done() reads geometry; the column must exist
    todo = plan(conn)
    log.info("plan: %d date(s) with bobtalk and audio on disk", len(todo))

    if args.dry_run:
        for date_str, event_id, lb, _ in todo[:args.limit or len(todo)]:
            done = already_done(conn, lb, event_id, args.model, geometry)
            sys.stdout.write(f"{date_str}  ev{event_id:<6} LB-{lb:05d}"
                             f"{'  (done)' if done else ''}\n")
        conn.close()
        return

    if not acquire_lock():
        conn.close()
        sys.exit(1)
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    cfg, exts, device = loc.build_asr_cfg(args.model, args.threads, args.device,
                                          args.compute_type)
    log.info("decoding with %s on %s (%s), geometry=%s",
             args.model, device, cfg["compute_type"], geometry)
    cache = dec.connect()

    started = time.time()
    done = skipped = failed = attempted = 0
    located = quotes = 0
    try:
        for date_str, event_id, lb, disk_path in todo:
            if _stop or (args.limit and attempted >= args.limit):
                break
            if not args.redo and already_done(conn, lb, event_id, args.model, geometry):
                skipped += 1
                continue
            block = conn.execute("SELECT bobtalk FROM olof_events WHERE event_id = ?",
                                 (event_id,)).fetchone()
            if not block or not (block[0] or "").strip():
                skipped += 1
                continue
            attempted += 1
            t0 = time.time()
            try:
                matches = loc.locate_one(conn, lb, disk_path, event_id, block[0],
                                         cfg, exts, args.model, cache=cache,
                                         full_show=args.full_show)
            except Exception as exc:  # noqa: BLE001 — one bad source must not end the run
                failed += 1
                log.error("LB-%05d (%s): %s", lb, date_str, exc)
                continue
            ok = sum(1 for m in matches if m.confident)
            done += 1
            located += ok
            quotes += len(matches)
            rate = (time.time() - started) / max(done + failed, 1)
            remaining = sum(1 for d, e, n, _ in todo
                            if not already_done(conn, n, e, args.model, geometry)) if done % 25 == 0 else None
            log.info("[%d/%d] %s LB-%05d: %d/%d located in %.0fs%s",
                     done, len(todo) - skipped, date_str, lb, ok, len(matches),
                     time.time() - t0,
                     f" — ~{remaining * rate / 3600:.1f} h left" if remaining else "")
    finally:
        cache.close()
        conn.close()
        LOCK_PATH.unlink(missing_ok=True)

    elapsed = (time.time() - started) / 3600.0
    log.info("run %s: %d done, %d skipped, %d failed; %d/%d quotes located in %.2f h",
             "stopped" if _stop else "complete", done, skipped, failed, located, quotes, elapsed)


if __name__ == "__main__":
    main()
