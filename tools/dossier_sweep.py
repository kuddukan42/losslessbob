#!/usr/bin/env python3
"""Corpus-wide dossier QC sweep (plan row C33, Phase 8 "Corpus sweep").

Builds :func:`backend.dossier.build_dossier` for every distinct concert date
in ``entries.date_str`` (channel ``public``), resolving any ambiguous date by
building each candidate separately, and records the QC gate outcome for each
resulting target. Writes a Markdown report and a JSON sidecar (for a future
GUI Sweep tab) to ``data/logs/`` and reports night-over-night deltas on the
error counts, optionally sending a desktop notification when any of them rose.

Usage::

    .venv/bin/python3 tools/dossier_sweep.py
    .venv/bin/python3 tools/dossier_sweep.py --limit 50
    .venv/bin/python3 tools/dossier_sweep.py --dates 2010-03-29,1965-06-01
    .venv/bin/python3 tools/dossier_sweep.py --notify --db /path/to/db

Cron wrapper: ``data/dossier_sweep_cron.sh`` (not installed automatically,
see that file's header).
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_log = logging.getLogger(__name__)

# Outcome ranks, worst first -- used both for the "top withheld" report and the
# JSON sidecar's per-target sort order.
_OUTCOME_RANK = {"build_error": 0, "gate_error": 1, "refused": 2, "ok": 3}

ERROR_KEYS = ("refused", "withheld_fields", "gate_errors", "build_errors")

_PROGRESS_EVERY = 250
_MAX_DEPTH = 4  # ambiguity resolution recursion guard


def _distinct_dates(conn, limit: int | None = None,
                     only: list[str] | None = None) -> list[str]:
    """Return every distinct ISO concert date derivable from ``entries.date_str``.

    Args:
        conn: Open SQLite connection.
        limit: Keep only the first N dates (sorted), for a quick test run.
        only: Restrict to this explicit subset of ISO dates (also for testing);
            dates not present in the corpus are silently dropped.

    Returns:
        Sorted ISO dates (``YYYY-MM-DD``).
    """
    from backend.geocoder import entry_date_to_iso

    raw = [r[0] for r in conn.execute("SELECT DISTINCT date_str FROM entries")]
    dates = sorted({iso for iso in (entry_date_to_iso(d) for d in raw) if iso})
    if only:
        wanted = set(only)
        dates = [d for d in dates if d in wanted]
    if limit is not None:
        dates = dates[:limit]
    return dates


def _resolve_targets(build_dossier, date_iso: str, db_path: str | None,
                      location: str | None = None, show: str | None = None,
                      depth: int = 0) -> list[tuple[str | None, str | None, dict | Exception]]:
    """Recursively resolve an ambiguous date into its concrete build targets.

    Args:
        build_dossier: ``backend.dossier.build_dossier`` (passed in so callers
            can patch/import it once).
        date_iso: Concert date.
        db_path: Database path override, or None for the default.
        location: Venue disambiguator to pass through (None on the first call).
        show: Show-part disambiguator to pass through (None on the first call).
        depth: Recursion guard.

    Returns:
        ``(location, show, dossier_or_exception)`` per concrete target --
        a caught exception from :func:`build_dossier` itself is returned in
        place of the dossier dict (a build error), never raised.
    """
    if depth > _MAX_DEPTH:
        return [(location, show, RuntimeError(f"ambiguity depth exceeded for {date_iso}"))]
    try:
        d = build_dossier(date_iso, location=location, channel="public", show=show,
                           db_path=db_path)
    except Exception as exc:  # noqa: BLE001 - recorded as a build_error, never fatal
        _log.exception("build_dossier raised for date=%s location=%r show=%r",
                       date_iso, location, show)
        return [(location, show, exc)]
    if not d.get("ambiguous"):
        return [(location, show, d)]
    candidates = d.get("candidates") or []
    if not candidates:
        return [(location, show, d)]
    out: list[tuple[str | None, str | None, dict | Exception]] = []
    for c in candidates:
        out.extend(_resolve_targets(
            build_dossier, date_iso, db_path,
            location=c.get("location", location), show=c.get("show"), depth=depth + 1,
        ))
    return out


def _classify(qc: dict, exc: Exception | None) -> tuple[str, list[str]]:
    """Classify one built target's outcome.

    Args:
        qc: The target's ``dossier["qc"]`` dict (``{}`` on a build error).
        exc: The exception :func:`build_dossier` raised, or None.

    Returns:
        ``(outcome, reasons)`` -- outcome is one of ``ok``/``refused``/
        ``gate_error``/``build_error``.
    """
    if exc is not None:
        return "build_error", [str(exc)]
    reasons = list(qc.get("reasons") or [])
    if any("QC gate raised an internal error" in r or "no view to gate" in r for r in reasons):
        return "gate_error", reasons
    if qc.get("refused"):
        return "refused", reasons
    return "ok", reasons


def _row_for_target(date_iso: str, location: str | None, show: str | None,
                     result) -> dict:
    """Build one report row for a resolved target.

    Args:
        date_iso: Concert date.
        location: The venue disambiguator this target was built with.
        show: The show-part disambiguator this target was built with.
        result: The dossier dict, or the caught build exception.

    Returns:
        A JSON-safe row dict.
    """
    exc = result if isinstance(result, Exception) else None
    qc = {} if exc is not None else (result.get("qc") or {})
    outcome, reasons = _classify(qc, exc)
    withheld = qc.get("withheld") or []
    view = {} if exc is not None else (result.get("view") or {})
    fields = view.get("fields") or {}
    disputed = (fields.get("show.setlist_confidence") or {}).get("confidence") == "disputed"
    stale = "analysis stale" in (qc.get("notices") or [])
    rules = sorted({w.get("rule") for w in withheld if w.get("rule")})
    return {
        "date_iso": date_iso,
        "location": location,
        "show": show,
        "outcome": outcome,
        "reasons": reasons,
        "withheld_count": len(withheld),
        "withheld_rules": rules,
        "disputed": disputed,
        "stale": stale,
    }


def sweep(db_path: str | None = None, limit: int | None = None,
          only_dates: list[str] | None = None) -> dict:
    """Run the full corpus sweep and return its totals + per-target rows.

    Caches :func:`backend.dossier._rarity_map` for the whole run (it's
    otherwise recomputed from scratch on every single target) by patching the
    module attribute, and always restores the original function afterward.

    Args:
        db_path: Database path override, or None for the default.
        limit: Keep only the first N corpus dates (sorted), for a quick run.
        only_dates: Restrict to this explicit subset of ISO dates.

    Returns:
        ``{"totals": {...}, "targets": [...]}`` -- targets sorted worst first.
    """
    import backend.dossier as dossier_mod
    from backend.db import get_connection

    conn = get_connection(db_path)
    dates = _distinct_dates(conn, limit=limit, only=only_dates)

    orig_rarity_map = dossier_mod._rarity_map
    _rarity_cache: dict[int, dict] = {}

    def _cached_rarity_map(c):
        key = id(c)
        if key not in _rarity_cache:
            _rarity_cache[key] = orig_rarity_map(c)
        return _rarity_cache[key]

    dossier_mod._rarity_map = _cached_rarity_map
    build_dossier = dossier_mod.build_dossier

    rows: list[dict] = []
    started = time.monotonic()
    try:
        for i, date_iso in enumerate(dates, start=1):
            for location, show, result in _resolve_targets(build_dossier, date_iso, db_path):
                rows.append(_row_for_target(date_iso, location, show, result))
            if i % _PROGRESS_EVERY == 0:
                _log.info("sweep progress: %d/%d dates (%d targets so far)",
                          i, len(dates), len(rows))
    finally:
        dossier_mod._rarity_map = orig_rarity_map
    elapsed = time.monotonic() - started

    totals = {
        "targets": len(rows),
        "refused": sum(1 for r in rows if r["outcome"] == "refused"),
        "withheld_fields": sum(r["withheld_count"] for r in rows),
        "shows_with_withheld": sum(1 for r in rows if r["withheld_count"] > 0),
        "disputed_setlists": sum(1 for r in rows if r["disputed"]),
        "stale_shows": sum(1 for r in rows if r["stale"]),
        "gate_errors": sum(1 for r in rows if r["outcome"] == "gate_error"),
        "build_errors": sum(1 for r in rows if r["outcome"] == "build_error"),
        "elapsed_seconds": round(elapsed, 3),
    }
    rows.sort(key=lambda r: (_OUTCOME_RANK.get(r["outcome"], 9), -r["withheld_count"],
                             not (r["disputed"] or r["stale"])))
    return {"totals": totals, "targets": rows}


def _find_previous(out_dir: Path, current_stem: str) -> Path | None:
    """Return the newest earlier ``dossier_sweep_*.json`` in *out_dir*, if any."""
    candidates = sorted(
        p for p in out_dir.glob("dossier_sweep_*.json") if p.stem != current_stem
    )
    return candidates[-1] if candidates else None


def _deltas(prev_totals: dict, cur_totals: dict) -> dict[str, int]:
    """Per-``ERROR_KEYS`` (current - previous), missing keys treated as 0."""
    return {k: cur_totals.get(k, 0) - prev_totals.get(k, 0) for k in ERROR_KEYS}


def _notify(summary: str) -> None:
    """Best-effort desktop notification; failure is logged, never fatal."""
    try:
        subprocess.run(["notify-send", "LosslessBob dossier sweep", summary],
                       check=False, timeout=10)
    except Exception:  # noqa: BLE001 - a notification failure must never fail the sweep
        _log.exception("notify-send failed")


def _render_md(run_date: str, totals: dict, targets: list[dict],
               deltas: dict[str, int] | None) -> str:
    """Render the Markdown report body."""
    lines = [f"# Dossier sweep {run_date}", ""]
    lines.append("| metric | value |")
    lines.append("|---|---|")
    for k in ("targets", "refused", "withheld_fields", "shows_with_withheld",
             "disputed_setlists", "stale_shows", "gate_errors", "build_errors",
             "elapsed_seconds"):
        lines.append(f"| {k} | {totals[k]} |")
    lines.append("")
    if deltas is not None:
        lines.append("## Night-over-night")
        lines.append("")
        lines.append("| metric | delta |")
        lines.append("|---|---|")
        for k in ERROR_KEYS:
            sign = "+" if deltas[k] > 0 else ""
            lines.append(f"| {k} | {sign}{deltas[k]} |")
        lines.append("")

    refused = [t for t in targets if t["outcome"] in ("refused", "gate_error", "build_error")]
    lines.append(f"## Refused / errored ({len(refused)})")
    lines.append("")
    if refused:
        lines.append("| date | location | show | outcome | reasons |")
        lines.append("|---|---|---|---|---|")
        for t in refused:
            lines.append(f"| {t['date_iso']} | {t['location'] or ''} | {t['show'] or ''} "
                         f"| {t['outcome']} | {'; '.join(t['reasons'])[:200]} |")
    else:
        lines.append("(none)")
    lines.append("")

    top_withheld = [t for t in targets if t["withheld_count"] > 0][:25]
    lines.append(f"## Top withheld (worst first, {len(top_withheld)} of "
                f"{totals['shows_with_withheld']})")
    lines.append("")
    if top_withheld:
        lines.append("| date | location | show | withheld | rules |")
        lines.append("|---|---|---|---|---|")
        for t in top_withheld:
            lines.append(f"| {t['date_iso']} | {t['location'] or ''} | {t['show'] or ''} "
                         f"| {t['withheld_count']} | {', '.join(t['withheld_rules'])} |")
    else:
        lines.append("(none)")
    lines.append("")
    return "\n".join(lines)


def run(db_path: str | None, limit: int | None, only_dates: list[str] | None,
       out_dir: Path, notify: bool) -> int:
    """Run the sweep, write the report + sidecar, and report night-over-night deltas.

    Args:
        db_path: Database path override, or None for the default.
        limit: Keep only the first N corpus dates, or None for the full corpus.
        only_dates: Explicit date subset, or None for the full corpus.
        out_dir: Destination directory (created if missing).
        notify: Send a desktop notification when any ``ERROR_KEYS`` metric rose.

    Returns:
        0 (the tool reports failures in its output, it does not fail the process
        unless it itself crashes -- see :func:`main`).
    """
    import datetime

    out_dir.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().isoformat()
    stem = f"dossier_sweep_{run_date}"

    prev_path = _find_previous(out_dir, stem)
    prev_totals = None
    if prev_path is not None:
        try:
            prev_totals = json.loads(prev_path.read_text(encoding="utf-8"))["totals"]
        except Exception:  # noqa: BLE001 - a corrupt/old sidecar just disables the delta
            _log.exception("could not read previous sweep JSON %s", prev_path)

    result = sweep(db_path=db_path, limit=limit, only_dates=only_dates)
    totals, targets = result["totals"], result["targets"]

    deltas = _deltas(prev_totals, totals) if prev_totals is not None else None
    if deltas is not None and notify and any(v > 0 for v in deltas.values()):
        rose = ", ".join(f"{k} +{v}" for k, v in deltas.items() if v > 0)
        _notify(f"Error counts rose: {rose}")

    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    md_path.write_text(_render_md(run_date, totals, targets, deltas), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    _log.info("sweep done: %s targets, %.3fs, wrote %s / %s",
              totals["targets"], totals["elapsed_seconds"], md_path.name, json_path.name)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="only the first N corpus dates")
    ap.add_argument("--dates", default=None, help="comma-separated subset of ISO dates")
    ap.add_argument("--notify", action="store_true",
                    help="desktop notification if any error count rose")
    ap.add_argument("--db", default=None, help="database path override")
    ap.add_argument("--out-dir", default=None, help="override data/logs")
    args = ap.parse_args(argv)

    from backend.paths import LOGS_DIR

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else LOGS_DIR
    only_dates = [d.strip() for d in args.dates.split(",") if d.strip()] if args.dates else None

    try:
        return run(args.db, args.limit, only_dates, out_dir, args.notify)
    except Exception:  # noqa: BLE001 - only the tool's own crash should exit non-zero
        _log.exception("dossier_sweep crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
