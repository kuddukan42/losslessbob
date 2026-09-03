#!/usr/bin/env python3
"""TODO-334 — build the collection gap list for tapematch's run dates.

``observations.db`` records ``n_sources_db`` (entries in ``losslessbob.db`` for
the date) against ``n_sources_found`` (folders the session actually resolved),
and the shortfall across the corpus is large -- 1,414 recordings over 926 dates
as of 2026-09-03. That number was read as an acquisition gap. It is not: this
census resolves the shortfall per LB number and finds it is almost entirely
recordings that are **on disk with audio** and excluded by
``find_lb_folders``'s path-name rule, not recordings we lack.

Four categories, assigned per LB entry that shares a date with a tapematch run:

    present   -- ``my_collection.disk_path`` is a directory and carries no
                 private/no-torrent marker. The analyzable population.
    private   -- the path exists and holds audio, but its name matches
                 PRIVATE / NOTORRENT / NO TORRENT, so ``find_lb_folders``
                 drops it before the run. Held, not missing.
    absent    -- no ``my_collection`` row, or the recorded path is not a
                 directory. This, and only this, is an acquisition target.
    unranked  -- present, but the date's latest run did not ingest it: either
                 the folder has no locally analyzable audio (the second
                 ``find_lb_folders`` exclusion) or the entry was catalogued
                 after that run. Both mean the stored verdict saw less than
                 the catalogue now holds.

Metadata only -- no audio is decoded and no directory is walked except to test
existence, so this is cheap to re-run as the corpus grows.

Usage:
    .venv/bin/python3 tools/tapematch/build_gap_list.py [--all-dates]
                      [--json PATH] [--md PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tapematch_session import (  # noqa: E402  (needs the sys.path line above)
    DB_PATH,
    SEARCH_ROOTS,
    parse_db_date,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OBS_PATH = Path(__file__).resolve().parent / "observations.db"
DEFAULT_JSON = PROJECT_ROOT / "data" / "tapematch" / "gap_list.json"
DEFAULT_MD = Path(__file__).resolve().parent / "GAP_LIST.md"

PRIVATE_MARKERS = ("PRIVATE", "NOTORRENT", "NO TORRENT")

log = logging.getLogger("gaplist")


def check_drives() -> list[str]:
    """Return the configured search roots that are not currently mounted.

    Every ``absent`` classification is a filesystem existence test, so an
    unmounted drive would turn thousands of held recordings into fictional
    acquisition targets. Callers must refuse to write a report when this
    returns anything.

    Returns:
        The unreachable roots, as strings, in ``SEARCH_ROOTS`` order.
    """
    return [str(r) for r in SEARCH_ROOTS if not r.is_dir()]


def load_run_dates(obs_path: Path) -> dict[str, dict]:
    """Return the latest run per concert date from ``observations.db``.

    Args:
        obs_path: Path to ``observations.db``.

    Returns:
        Mapping of ISO concert date to the latest run's ``run_id``, ``run_at``,
        ``n_sources_db``, ``n_sources_found`` and ``n_families``.
    """
    conn = sqlite3.connect(str(obs_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT r.concert_date, r.run_id, r.run_at, r.n_sources_db,
                  r.n_sources_found, r.n_families
             FROM runs r
             JOIN (SELECT concert_date, MAX(run_at) ra FROM runs GROUP BY 1) m
               ON r.concert_date = m.concert_date AND r.run_at = m.ra"""
    ).fetchall()
    conn.close()
    return {r["concert_date"]: dict(r) for r in rows}


def load_ingested(obs_path: Path, run_ids: set[str]) -> dict[str, set[int]]:
    """Return the LB numbers each of the given runs actually ingested.

    Args:
        obs_path: Path to ``observations.db``.
        run_ids: The run ids to look up.

    Returns:
        Mapping of ``run_id`` to the set of LB numbers in its ``sources`` rows.
    """
    conn = sqlite3.connect(str(obs_path))
    out: dict[str, set[int]] = defaultdict(set)
    for run_id, lb in conn.execute("SELECT run_id, lb_number FROM sources"):
        if run_id in run_ids and lb is not None:
            out[run_id].add(int(lb))
    conn.close()
    return out


def classify(db_path: Path, run_dates: dict[str, dict],
             ingested: dict[str, set[int]],
             all_dates: bool) -> tuple[dict[str, dict], Counter, int]:
    """Assign every catalogued entry on a run date to one of the four buckets.

    Args:
        db_path: Path to ``losslessbob.db``.
        run_dates: Output of :func:`load_run_dates`.
        ingested: Output of :func:`load_ingested`.
        all_dates: Include dates tapematch has never run, not just run dates.

    Returns:
        ``(per_date, totals, unparseable)`` where ``per_date`` maps ISO date to
        its bucket lists and run context, ``totals`` counts entries per bucket,
        and ``unparseable`` counts entries whose ``date_str`` did not parse.
    """
    conn = sqlite3.connect(str(db_path))
    collection = {n: p for n, p in conn.execute(
        "SELECT lb_number, disk_path FROM my_collection")}
    entries = conn.execute(
        "SELECT lb_number, date_str, location, lb_category FROM entries").fetchall()
    conn.close()

    per_date: dict[str, dict] = {}
    totals: Counter = Counter()
    unparseable = 0

    for lb, date_str, location, category in entries:
        try:
            iso = parse_db_date(date_str).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            unparseable += 1
            continue
        run = run_dates.get(iso)
        if run is None and not all_dates:
            continue

        rec = per_date.setdefault(iso, {
            "date": iso,
            "location": location or "",
            "run_id": run["run_id"] if run else None,
            "run_at": run["run_at"] if run else None,
            "n_families": run["n_families"] if run else None,
            "present": [], "private": [], "absent": [], "unranked": [],
        })

        path = collection.get(lb)
        if path is None or not Path(path).is_dir():
            bucket = "absent"
        elif any(m in path.upper() for m in PRIVATE_MARKERS):
            bucket = "private"
        elif run is not None and lb not in ingested.get(run["run_id"], set()):
            bucket = "unranked"
        else:
            bucket = "present"

        rec[bucket].append({"lb": lb, "category": category or "",
                            "path": path or ""})
        totals[bucket] += 1

    for rec in per_date.values():
        for key in ("present", "private", "absent", "unranked"):
            rec[key].sort(key=lambda e: e["lb"])
        rec["n_catalogued"] = sum(len(rec[k]) for k in
                                  ("present", "private", "absent", "unranked"))
        rec["n_unseen"] = len(rec["private"]) + len(rec["absent"]) + len(rec["unranked"])
    return per_date, totals, unparseable


def _decade(iso: str) -> str:
    return f"{iso[:3]}0s"


def render_md(per_date: dict[str, dict], totals: Counter, unparseable: int,
              all_dates: bool) -> str:
    """Render the human-readable summary of the gap list.

    Args:
        per_date: Output of :func:`classify`.
        totals: Per-bucket entry counts.
        unparseable: Entries whose ``date_str`` did not parse.
        all_dates: Whether dates without a run were included.

    Returns:
        The full Markdown document.
    """
    n_dates = len(per_date)
    catalogued = sum(totals.values())
    worst = sorted(per_date.values(), key=lambda r: -r["n_unseen"])
    with_absent = [r for r in per_date.values() if r["absent"]]

    by_dec: dict[str, Counter] = defaultdict(Counter)
    for rec in per_date.values():
        d = by_dec[_decade(rec["date"])]
        d["dates"] += 1
        for k in ("present", "private", "absent", "unranked"):
            d[k] += len(rec[k])

    out: list[str] = []
    out.append("# Collection gap list (TODO-334)\n")
    out.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by "
               "`tools/tapematch/build_gap_list.py`. Metadata only — no audio "
               "decoded. Machine-readable form: `data/tapematch/gap_list.json`.\n")
    scope = "every catalogued date" if all_dates else "dates tapematch has run"
    out.append(f"Scope: **{scope}** — {n_dates} dates, {catalogued} catalogued "
               f"recordings. {unparseable} entries skipped for an unparseable "
               "`date_str`.\n")

    out.append("\n## Headline\n")
    out.append("| Bucket | Recordings | Meaning |")
    out.append("|---|---:|---|")
    out.append(f"| `present` | {totals['present']} | resolved and ingested by the "
               "latest run |")
    out.append(f"| `private` | {totals['private']} | on disk **with audio**, dropped "
               "by the private/no-torrent path rule |")
    out.append(f"| `unranked` | {totals['unranked']} | on disk, not ingested — no "
               "analyzable audio, or catalogued after the run |")
    out.append(f"| `absent` | {totals['absent']} | not on disk — **the only real "
               "acquisition target** |")

    out.append("\nThe shortfall `n_sources_db - n_sources_found` in "
               "`observations.db` is dominated by `private`, not `absent`. It is "
               "an analysis-coverage gap, not an acquisition gap.\n")

    out.append("\n## By decade\n")
    out.append("| Decade | Dates | present | private | unranked | absent |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for dec in sorted(by_dec):
        c = by_dec[dec]
        out.append(f"| {dec} | {c['dates']} | {c['present']} | {c['private']} | "
                   f"{c['unranked']} | {c['absent']} |")

    out.append(f"\n## Acquisition targets — `absent` ({totals['absent']} "
               f"recordings across {len(with_absent)} dates)\n")
    if not with_absent:
        out.append("None. Every catalogued recording on these dates is on disk.\n")
    else:
        out.append("| Date | Location | LB | Category | Recorded path |")
        out.append("|---|---|---|---|---|")
        for rec in sorted(with_absent, key=lambda r: r["date"]):
            for e in rec["absent"]:
                path = e["path"] or "_(no my_collection row)_"
                out.append(f"| {rec['date']} | {rec['location'][:40]} | "
                           f"LB-{e['lb']:05d} | {e['category']} | `{path}` |")

    out.append("\n## Dates with the most unseen recordings\n")
    out.append("Ranked by `private + unranked + absent`. A date high on this list "
               "has a family count computed from materially less than the "
               "catalogue holds.\n")
    out.append("| Date | Location | Catalogued | Ingested | private | unranked | "
               "absent | Families |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for rec in worst[:40]:
        if not rec["n_unseen"]:
            break
        out.append(f"| {rec['date']} | {rec['location'][:34]} | "
                   f"{rec['n_catalogued']} | {len(rec['present'])} | "
                   f"{len(rec['private'])} | {len(rec['unranked'])} | "
                   f"{len(rec['absent'])} | {rec['n_families']} |")

    out.append("\n## How to read this\n")
    out.append("- `private` recordings are excluded by `find_lb_folders` because a "
               "private/no-torrent folder has no local LB page, and therefore no "
               "curator commentary to corroborate a merge against. The audio is "
               "there. Admitting them is a policy decision, not a sourcing one.\n")
    out.append("- `unranked` mixes two causes that this census cannot separate "
               "without walking the folder: no locally analyzable audio, and "
               "catalogued-since-the-run. Re-running the date resolves both.\n")
    out.append("- A date's `n_families` is only as complete as its `present` "
               "column. Do not read a family count on a high-`n_unseen` date as "
               "the number of source tapes that exist.\n")
    return "\n".join(out) + "\n"


def main() -> int:
    """Entry point: classify, then write the JSON and Markdown artifacts."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all-dates", action="store_true",
                    help="include catalogued dates tapematch has never run")
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    unmounted = check_drives()
    if unmounted:
        log.error("REFUSING to write: drive(s) not mounted: %s. Every 'absent' "
                  "classification is a filesystem test, so the report would be "
                  "fiction.", ", ".join(unmounted))
        return 1
    if not OBS_PATH.exists():
        log.error("observations.db not found at %s", OBS_PATH)
        return 1

    run_dates = load_run_dates(OBS_PATH)
    ingested = load_ingested(OBS_PATH, {r["run_id"] for r in run_dates.values()})
    per_date, totals, unparseable = classify(DB_PATH, run_dates, ingested,
                                             args.all_dates)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "scope": "all_dates" if args.all_dates else "run_dates",
        "totals": dict(totals),
        "unparseable_date_str": unparseable,
        "dates": [per_date[k] for k in sorted(per_date)],
    }, indent=1), encoding="utf-8")
    args.md.write_text(render_md(per_date, totals, unparseable, args.all_dates),
                       encoding="utf-8")

    log.info("%d dates, %d recordings: present=%d private=%d unranked=%d absent=%d",
             len(per_date), sum(totals.values()), totals["present"],
             totals["private"], totals["unranked"], totals["absent"])
    log.info("wrote %s and %s", args.json, args.md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
