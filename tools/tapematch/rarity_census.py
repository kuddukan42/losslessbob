#!/usr/bin/env python3
"""TODO-335 — source-tape rarity census: how many copies of each tape circulate.

A TapeMatch family is one source tape; its size is the number of circulating
copies the pipeline has heard. This reads the clustering as a preservation
dataset rather than a matcher-accuracy one and writes ``docs/RARITY_CENSUS.md``:

* the copies-per-family distribution, from both family sets the repo holds —
  ``observations.db``'s **latest run per date** (the TODO-335 measurement) and
  the app DB's **synced** ``recording_families`` (the best run per date, which
  is what the GUI shows, via ``backend.rarity``);
* redundancy by decade, year and Olof tour (``olof_events.tour_name``);
* dates where every recording present collapses to one tape;
* every single-copy family with its LB number, split by whether the date is
  fully analysed or has recordings tapematch never ingested — crossed against
  TODO-334's gap list (``data/tapematch/gap_list.json``: private / unranked /
  absent per date) and the app DB's current unanalysed count.

Over-merge (TODO-319/325) can only move tapes out of the single-copy bucket,
so the singleton counts are lower bounds; the head of the size distribution is
the unreliable end. Do not present the redundancy ratio to users until
TODO-319 lands.

Read-only: both DBs are opened ``mode=ro``; no audio, no filesystem walk.

Usage:
    .venv/bin/python3 tools/tapematch/rarity_census.py [--db PATH] [--obs PATH]
        [--gap-list PATH] [--md PATH] [--json PATH]
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.rarity import unanalysed_by_date  # noqa: E402  (needs the sys.path line)

DEFAULT_DB = PROJECT_ROOT / "data" / "losslessbob.db"
DEFAULT_OBS = Path(__file__).resolve().parent / "observations.db"
DEFAULT_GAP = PROJECT_ROOT / "data" / "tapematch" / "gap_list.json"
DEFAULT_MD = PROJECT_ROOT / "docs" / "RARITY_CENSUS.md"
DEFAULT_JSON = PROJECT_ROOT / "data" / "tapematch" / "rarity_census.json"

# Tours with fewer families than this are folded out of the tour table.
MIN_TOUR_FAMILIES = 20
UNSEEN_BUCKETS = ("private", "unranked", "absent")

log = logging.getLogger("rarity_census")


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_obs_families(obs_path: Path) -> dict[str, dict[int, list]]:
    """Return families from the latest run (``MAX(run_at)``) per concert date.

    Args:
        obs_path: Path to ``observations.db``.

    Returns:
        ISO date -> family_id -> list of member ``(lb_number, dominant_ext)``;
        ``lb_number`` may be None for an unnumbered source.
    """
    conn = _ro(obs_path)
    out: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for date, fam, lb, ext in conn.execute(
        """SELECT s.concert_date, s.family_id, s.lb_number, s.dominant_ext
             FROM sources s
             JOIN runs r ON r.run_id = s.run_id
             JOIN (SELECT concert_date, MAX(run_at) ra FROM runs GROUP BY 1) m
               ON r.concert_date = m.concert_date AND r.run_at = m.ra"""
    ):
        out[date][fam].append((lb, ext))
    conn.close()
    return out


def load_app_families(db_path: Path) -> tuple[dict[str, list[int]], dict[str, str], Counter]:
    """Return the synced families, their dates, and current unanalysed counts.

    Args:
        db_path: Path to ``losslessbob.db``.

    Returns:
        ``(members, fam_date, unanalysed)``: fam_id -> sorted LB numbers,
        fam_id -> ISO date, and ISO date -> entries with no family.
    """
    conn = _ro(db_path)
    members: dict[str, list[int]] = defaultdict(list)
    fam_date: dict[str, str] = {}
    for lb, fam, date in conn.execute(
        "SELECT lb_number, fam_id, concert_date FROM recording_families"
    ):
        members[fam].append(lb)
        fam_date[fam] = date
    unanalysed = unanalysed_by_date(conn, set(fam_date.values()))
    conn.close()
    return {f: sorted(v) for f, v in members.items()}, fam_date, unanalysed


def load_tours(db_path: Path) -> dict[str, str]:
    """Return ISO date -> Olof tour name (first concert event of the date)."""
    conn = _ro(db_path)
    tours: dict[str, str] = {}
    for date, tour in conn.execute(
        "SELECT date_str, tour_name FROM olof_events "
        "WHERE event_type = 'concert' AND tour_name IS NOT NULL AND tour_name != '' "
        "ORDER BY event_id"
    ):
        tours.setdefault(date, tour)
    conn.close()
    return tours


def load_gap_list(gap_path: Path) -> tuple[dict[str, Counter], str | None]:
    """Return ISO date -> unseen-bucket counts from TODO-334's gap list.

    Args:
        gap_path: Path to ``gap_list.json`` (absent is fine — returns empty).

    Returns:
        ``(per_date, generated_at)``; ``per_date[date]`` counts the
        private/unranked/absent LBs on that date. Only counts are read.
    """
    if not gap_path.is_file():
        return {}, None
    data = json.loads(gap_path.read_text())
    per_date = {
        d["date"]: Counter({b: len(d.get(b) or []) for b in UNSEEN_BUCKETS})
        for d in data.get("dates", [])
    }
    return per_date, data.get("generated_at")


def size_distribution(sizes: list[int]) -> Counter:
    """Count families per member count."""
    return Counter(sizes)


def _era_rows(fam_sizes: dict[str, int], fam_key: dict[str, str]) -> list[tuple]:
    """Group families by a key -> (key, families, sources, singletons, ratio)."""
    agg: dict[str, list[int]] = defaultdict(list)
    for fam, size in fam_sizes.items():
        agg[fam_key[fam]].append(size)
    rows = []
    for key in sorted(agg):
        s = agg[key]
        rows.append((key, len(s), sum(s), sum(1 for x in s if x == 1), sum(s) / len(s)))
    return rows


def build_census(obs_path: Path, db_path: Path, gap_path: Path) -> dict:
    """Compute the whole census as a JSON-serialisable dict.

    Args:
        obs_path: ``observations.db``.
        db_path: ``losslessbob.db``.
        gap_path: TODO-334 ``gap_list.json``.

    Returns:
        The census: distributions, era tables, collapsed dates, singletons.
    """
    obs = load_obs_families(obs_path)
    obs_sizes = [len(m) for fams in obs.values() for m in fams.values()]
    obs_ext: dict[int, str] = {
        lb: (ext or "") for fams in obs.values() for m in fams.values()
        for lb, ext in m if lb is not None
    }

    members, fam_date, unanalysed = load_app_families(db_path)
    tours = load_tours(db_path)
    gaps, gap_generated = load_gap_list(gap_path)
    sizes = {f: len(m) for f, m in members.items()}

    by_decade = _era_rows(sizes, {f: f"{d[:3]}0s" for f, d in fam_date.items()})
    by_year = _era_rows(sizes, {f: d[:4] for f, d in fam_date.items()})
    by_tour = [r for r in _era_rows(
        sizes, {f: tours.get(d, "(no Olof tour)") for f, d in fam_date.items()})
        if r[1] >= MIN_TOUR_FAMILIES]
    tour_first = defaultdict(lambda: "9999")
    for f, d in fam_date.items():
        t = tours.get(d, "(no Olof tour)")
        tour_first[t] = min(tour_first[t], d)
    by_tour.sort(key=lambda r: tour_first[r[0]])

    fams_by_date: dict[str, list[str]] = defaultdict(list)
    for f, d in fam_date.items():
        fams_by_date[d].append(f)
    collapsed = sorted(
        d for d, fs in fams_by_date.items() if len(fs) == 1 and sizes[fs[0]] >= 2)

    singletons = []
    for f, m in members.items():
        if len(m) != 1:
            continue
        d = fam_date[f]
        g = gaps.get(d)
        singletons.append({
            "lb": m[0], "fam_id": f, "date": d,
            "siblings_on_date": len(fams_by_date[d]) - 1,
            "unanalysed_now": unanalysed.get(d, 0),
            "gap": dict(g) if g else None,
            "ext": obs_ext.get(m[0], ""),
        })
    singletons.sort(key=lambda s: (s["date"], s["lb"]))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gap_list_generated_at": gap_generated,
        "obs": {
            "dates": len(obs), "families": len(obs_sizes), "sources": sum(obs_sizes),
            "distribution": dict(sorted(size_distribution(obs_sizes).items())),
        },
        "app": {
            "dates": len(fams_by_date), "families": len(sizes),
            "sources": sum(sizes.values()),
            "distribution": dict(sorted(size_distribution(list(sizes.values())).items())),
        },
        "by_decade": by_decade, "by_year": by_year, "by_tour": by_tour,
        "collapsed_dates": collapsed,
        "singletons": singletons,
    }


def _dist_table(obs: dict, app: dict) -> list[str]:
    keys = sorted(set(obs["distribution"]) | set(app["distribution"]))
    out = ["| Copies | Families (obs latest run) | % | Families (app synced) | % |",
           "|---:|---:|---:|---:|---:|"]
    for k in keys:
        a, b = obs["distribution"].get(k, 0), app["distribution"].get(k, 0)
        out.append(f"| {k} | {a:,} | {100 * a / max(obs['families'], 1):.1f} "
                   f"| {b:,} | {100 * b / max(app['families'], 1):.1f} |")
    return out


def _era_table(rows: list[tuple], label: str) -> list[str]:
    out = [f"| {label} | Families | Sources | Single-copy | % single | Copies/tape |",
           "|---|---:|---:|---:|---:|---:|"]
    for key, fams, srcs, single, ratio in rows:
        out.append(f"| {key} | {fams:,} | {srcs:,} | {single:,} "
                   f"| {100 * single / fams:.0f} | {ratio:.2f} |")
    return out


def _lb_lines(lbs: list[int], per_line: int = 12) -> list[str]:
    tags = [f"LB-{n:05d}" for n in lbs]
    return [" ".join(tags[i:i + per_line]) for i in range(0, len(tags), per_line)]


def classify_singleton(s: dict) -> str:
    """Return why a singleton is single-copy: ``complete`` or an unseen reason.

    ``complete`` means neither the gap list nor the current app DB shows any
    unanalysed recording on the date, so the tape is single-copy on the evidence
    the collection holds. Otherwise the first unseen bucket wins, with
    ``unanalysed`` for dates the gap list predates.
    """
    g = s["gap"] or {}
    for b in UNSEEN_BUCKETS:
        if g.get(b):
            return b
    return "unanalysed" if s["unanalysed_now"] else "complete"


def render_md(c: dict) -> str:
    """Render the census dict as ``docs/RARITY_CENSUS.md``."""
    obs, app = c["obs"], c["app"]
    singles = c["singletons"]
    reason = Counter(classify_singleton(s) for s in singles)
    single_obs = obs["distribution"].get(1, 0)
    ext = Counter((s["ext"] or "unknown").lstrip(".").upper() for s in singles)
    lines = [
        "# Source-tape rarity census (TODO-335)",
        "",
        f"Generated {c['generated_at']} by `tools/tapematch/rarity_census.py` — "
        "read-only over `observations.db` and `losslessbob.db`. Re-run after every "
        "`tapematch_sync`.",
        "",
        "A TapeMatch family is one source tape; its size is the number of circulating "
        "copies the pipeline has heard.",
        "",
        "> **Caveat — over-merge (TODO-319/325).** A false merge can only move a tape "
        "*out* of the single-copy bucket, so every single-copy count below is a **lower "
        "bound**. The head of the size distribution (the largest families) is the "
        "unreliable end. Do not present the copies-per-tape ratio to users until "
        "TODO-319's family guard ships.",
        "",
        "## Headline",
        "",
        "| Family set | Dates | Sources | Families | Single-copy | Copies/tape |",
        "|---|---:|---:|---:|---:|---:|",
        f"| observations.db, latest run per date | {obs['dates']:,} | {obs['sources']:,} "
        f"| {obs['families']:,} | {single_obs:,} "
        f"({100 * single_obs / max(obs['families'], 1):.0f}%) "
        f"| {obs['sources'] / max(obs['families'], 1):.2f} |",
        f"| app DB synced `recording_families` (what the GUI shows) | {app['dates']:,} "
        f"| {app['sources']:,} | {app['families']:,} | {len(singles):,} "
        f"({100 * len(singles) / max(app['families'], 1):.0f}%) "
        f"| {app['sources'] / max(app['families'], 1):.2f} |",
        "",
        "The two sets differ because `tapematch_sync` picks the run with the most "
        "sources ingested per date, not the newest, and drops unnumbered sources. The "
        "rest of this report uses the synced set, so it matches the Library badge.",
        "",
        "## Copies per family",
        "",
        *_dist_table(obs, app),
        "",
        "## Why single-copy — crossed with TODO-334's gap list",
        "",
        f"Gap list: `data/tapematch/gap_list.json`, generated "
        f"{c['gap_list_generated_at'] or '(missing)'}. A single-copy tape on a date with "
        "recordings tapematch never ingested may have an unmeasured copy.",
        "",
        "| Reason | Single-copy families | Meaning |",
        "|---|---:|---|",
        f"| complete | {reason['complete']:,} | every catalogued recording on the date was "
        "analysed — single-copy on all the evidence held |",
        f"| private | {reason['private']:,} | date has private/no-torrent recordings "
        "`find_lb_folders` excludes (TODO-334 policy decision) |",
        f"| unranked | {reason['unranked']:,} | date has present recordings the run did "
        "not ingest (no analysable audio, or catalogued after the run) |",
        f"| absent | {reason['absent']:,} | date has catalogued recordings not on disk |",
        f"| unanalysed | {reason['unanalysed']:,} | not in the gap list's buckets, but the "
        "app DB now holds un-familied entries on the date (catalogued since) |",
        "",
        f"So **{reason['complete']:,}** of {len(singles):,} single-copy tapes "
        f"({100 * reason['complete'] / max(len(singles), 1):.0f}%) are single-copy "
        "independent of the analysis gap; the rest are single-copy *as far as tapematch "
        "has measured*.",
        "",
        "Format of the single-copy tapes (`sources.dominant_ext`; unknown = source "
        "predates the column): "
        + ", ".join(f"{k} {v:,}" for k, v in ext.most_common()) + ".",
        "",
        f"**{len(c['collapsed_dates']):,} dates** hold 2+ recordings that all collapse "
        "to one tape — redundancy in the collection, no independent second capture.",
        "",
        "## By decade",
        "",
        *_era_table(c["by_decade"], "Decade"),
        "",
        "## By year",
        "",
        *_era_table(c["by_year"], "Year"),
        "",
        f"## By Olof tour (≥{MIN_TOUR_FAMILIES} families, chronological)",
        "",
        *_era_table(c["by_tour"], "Tour"),
        "",
        "## Single-copy families by LB number",
        "",
        "`complete` = single-copy on all evidence; the second list is single-copy only "
        "as far as tapematch has measured. Grouped by decade.",
        "",
    ]
    for label, want in (("complete", True), ("unmeasured siblings", False)):
        by_dec: dict[str, list[int]] = defaultdict(list)
        for s in singles:
            if (classify_singleton(s) == "complete") == want:
                by_dec[f"{s['date'][:3]}0s"].append(s["lb"])
        lines += [f"### Single-copy — {label}", ""]
        for dec in sorted(by_dec):
            lbs = sorted(by_dec[dec])
            lines += [f"<details><summary>{dec} — {len(lbs):,}</summary>", "",
                      *_lb_lines(lbs), "", "</details>", ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--obs", type=Path, default=DEFAULT_OBS)
    ap.add_argument("--gap-list", type=Path, default=DEFAULT_GAP)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    census = build_census(args.obs, args.db, args.gap_list)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.md.write_text(render_md(census))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(census, indent=1))
    log.info("families=%d single-copy=%d -> %s, %s", census["app"]["families"],
             len(census["singletons"]), args.md, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
