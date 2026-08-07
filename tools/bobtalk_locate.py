"""Locate Olof's bobtalk quotes inside our recordings and persist timestamps.

TODO-303. The scoring, confidence and persistence rules live in
``backend/bobtalk.py``; this is the ASR half — it decodes one window around
every track boundary and hands the token sets over.

Why boundaries, and why *all* of them: bobtalk happens between songs, and
inferring WHICH boundary holds a given quote from the setlist position was
tried and drifts (it failed in both directions on the 1978-12-16 PoC). Decoding
every boundary once and letting each quote pick its own best window costs one
pass and removes the assumption entirely.

Requires ``model: large-v3`` and ``vad_filter: False``: the shipped ``base``
model garbles too heavily to recognise a known line, and Silero VAD silently
discards announcer-over-crowd speech (see CALIBRATION_PROGRESS.md "§3
banter/ASR signal").

Usage:
    .venv/bin/python3 tools/bobtalk_locate.py --lb 212
    .venv/bin/python3 tools/bobtalk_locate.py --date 1978-12-16 --all-sources
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

import yaml

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(APP_ROOT / "tools" / "tapematch"))

from backend import bobtalk as bt  # noqa: E402
from backend import paths as bpaths  # noqa: E402

log = logging.getLogger("bobtalk_locate")

PRE_SEC = 55.0          # how far before a track boundary to listen
POST_SEC = 25.0         # ...and after; banter straddles the split either way
DEFAULT_MODEL = "large-v3"
CONFIG_PATH = APP_ROOT / "tools" / "tapematch" / "config.yaml"


def _asr_cfg(model: str, threads: int) -> tuple[dict, list[str]]:
    """Build the ASR config block and audio extensions for a locate pass.

    Args:
        model: faster-whisper model name.
        threads: CPU threads to allow the decoder.

    Returns:
        ``(asr_cfg, audio_exts)``.
    """
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    cfg = dict(raw["asr"])
    cfg.update(model=model, cpu_threads=threads, vad_filter=False, enabled=True)
    return cfg, raw["ingest"]["audio_exts"]


def _event_for_date(conn: sqlite3.Connection, date_str: str) -> tuple[int, str] | None:
    """Return the ``(event_id, bobtalk)`` for a date, preferring the fullest block."""
    row = conn.execute(
        "SELECT event_id, bobtalk FROM olof_events "
        "WHERE date_str = ? AND bobtalk IS NOT NULL AND TRIM(bobtalk) <> '' "
        "ORDER BY LENGTH(bobtalk) DESC LIMIT 1", (date_str,)).fetchone()
    return (row[0], row[1]) if row else None


def _sources_for_date(conn: sqlite3.Connection, date_str: str) -> list[tuple[int, str]]:
    """Return ``(lb_number, disk_path)`` for every collected recording of a date."""
    out = []
    for lb, fn, dp in conn.execute(
            "SELECT lb_number, folder_name, disk_path FROM my_collection"):
        if (fn or "").startswith(date_str) and dp and Path(dp).is_dir():
            out.append((int(lb), dp))
    return sorted(out)


def locate_one(conn: sqlite3.Connection, lb_number: int, disk_path: str,
               event_id: int, block: str, cfg: dict, exts: list[str],
               model_name: str) -> list[bt.Match]:
    """Decode a recording's boundary windows and locate every bobtalk quote.

    Args:
        conn: Open main-database connection.
        lb_number: Recording being searched.
        disk_path: Folder holding its audio.
        event_id: ``olof_events.event_id`` supplying the quotes.
        block: Raw bobtalk text.
        cfg: ASR config block.
        exts: Audio file extensions to ingest.
        model_name: Model identifier, stored for provenance.

    Returns:
        The matches written (both confident and not).
    """
    from tapematch import asr, ingest  # deferred: heavy, and optional for tests

    quotes = bt.parse_bobtalk(block)
    if not quotes:
        log.warning("LB-%05d: no matchable quotes in event %s", lb_number, event_id)
        return []

    mono, sr, bounds = ingest.concat_source(Path(disk_path), exts, 16000, mono=True)
    dur = len(mono) / float(sr)
    model = asr.load_model(cfg)
    if model is None:
        raise RuntimeError("faster-whisper unavailable; cannot locate")

    windows: list[tuple[float, frozenset[str]]] = []
    t0 = time.time()
    for b in bounds:
        ts = b / float(sr)
        w0, w1 = max(0.0, ts - PRE_SEC), min(dur, ts + POST_SEC)
        toks: set[str] = set()
        for u in asr.transcribe_gaps(mono, sr, [(w0, w1)], cfg, model=model):
            toks |= bt.content_tokens(u.text)
        windows.append((w0, frozenset(toks)))
    log.info("LB-%05d: decoded %d windows in %.0fs", lb_number, len(windows),
             time.time() - t0)

    matches = bt.locate_quotes(quotes, windows)
    bt.save_locations(conn, lb_number, event_id, matches, model=model_name)
    return matches


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--lb", type=int, help="locate within one LB recording")
    g.add_argument("--date", help="locate within a date's recordings (YYYY-MM-DD)")
    p.add_argument("--all-sources", action="store_true",
                   help="with --date, process every source, not just the first")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--threads", type=int, default=0, help="0 = all cores")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")
    cfg, exts = _asr_cfg(args.model, args.threads)
    conn = sqlite3.connect(str(bpaths.DB_PATH))
    try:
        if args.lb is not None:
            row = conn.execute(
                "SELECT folder_name, disk_path FROM my_collection WHERE lb_number = ?",
                (args.lb,)).fetchone()
            if not row or not row[1] or not Path(row[1]).is_dir():
                p.error(f"LB-{args.lb:05d}: no collected folder on disk")
            m = re.match(r"(\d{4}-\d{2}-\d{2})", row[0] or "")
            if not m:
                p.error(f"LB-{args.lb:05d}: folder name carries no date")
            targets, date_str = [(args.lb, row[1])], m.group(1)
        else:
            date_str = args.date
            targets = _sources_for_date(conn, date_str)
            if not args.all_sources:
                targets = targets[:1]
            if not targets:
                p.error(f"{date_str}: no collected recordings on disk")

        ev = _event_for_date(conn, date_str)
        if ev is None:
            p.error(f"{date_str}: no olof_events row carries bobtalk")
        event_id, block = ev

        for lb_number, disk_path in targets:
            try:
                matches = locate_one(conn, lb_number, disk_path, event_id, block,
                                     cfg, exts, args.model)
            except Exception as exc:  # noqa: BLE001 — one bad source, not the run
                log.error("LB-%05d: locate failed (%s)", lb_number, exc)
                continue
            ok = sum(1 for m in matches if m.confident)
            for m in matches:
                flag = "OK " if m.confident else "-- "
                sys.stdout.write(
                    f"{flag}LB-{lb_number:05d} q{m.quote_index:<3} "
                    f"t={m.t_start / 60:7.1f}min dice={m.dice:.2f} "
                    f"runner={m.runner_up:.2f}\n")
            sys.stdout.write(
                f"LB-{lb_number:05d}: {ok}/{len(matches)} quote(s) located "
                f"(event {event_id}, {date_str})\n")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
