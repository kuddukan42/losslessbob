#!/usr/bin/env python3
"""(BUG-326 / TODO-323 step 2) Diff post-fix family assignments against the pre-fix run.

For every concert date re-run after the ingest de-dup fix, compare the source
families in the new ``report.md`` against those in the newest run that predates
it. Only dates whose partition actually changed need their ``analysis.md``
rewritten; the rest keep the verdict they already have.

Prints one row per date, then a summary. Exit status is always 0 — this is a
reporting tool.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RUNS = Path("data/tapematch/runs")
_LB = re.compile(r"LB-(\d+)")
_FAMILY = re.compile(r"^\s*Family\s+\d+:", re.M)


def parse_clusters(report: Path) -> tuple[frozenset[frozenset[str]] | None, str]:
    """Read the CLUSTERS block of a report.md.

    Args:
        report: Path to a run dir's ``report.md``.

    Returns:
        ``(partition, note)``. ``partition`` is a frozenset of families, each a
        frozenset of zero-padded LB ids, or ``None`` when the report has no
        usable CLUSTERS section. ``note`` explains a ``None``.
    """
    if not report.is_file():
        return None, "no report.md"
    text = report.read_text(errors="replace")
    if "=== CLUSTERS ===" not in text:
        return None, "no CLUSTERS section (incomplete run)"
    block = text.split("=== CLUSTERS ===", 1)[1]
    for stop in ("\n=== ", "\nDistinct source families:", "\n  Distinct source families:"):
        if stop in block:
            block = block.split(stop, 1)[0]
    families = []
    for line in block.splitlines():
        if not _FAMILY.match(line):
            continue
        lbs = {f"LB-{int(n):05d}" for n in _LB.findall(line)}
        if lbs:
            families.append(frozenset(lbs))
    if not families:
        return None, "CLUSTERS section held no Family lines"
    return frozenset(families), ""


def ingest_tracks(report: Path) -> dict[str, int]:
    """Map LB id -> track count from a report's INGEST / TRIM block."""
    if not report.is_file():
        return {}
    text = report.read_text(errors="replace")
    if "=== INGEST / TRIM ===" not in text:
        return {}
    block = text.split("=== INGEST / TRIM ===", 1)[1].split("\n===", 1)[0]
    out: dict[str, int] = {}
    for line in block.splitlines():
        m = re.search(r"LB-(\d+)\).*?(\d+) tracks", line)
        if m:
            out[f"LB-{int(m.group(1)):05d}"] = int(m.group(2))
    return out


def describe(part: frozenset[frozenset[str]]) -> str:
    """Render a partition as a stable, readable string."""
    return " | ".join(
        "+".join(sorted(fam)) for fam in sorted(part, key=lambda f: sorted(f)[0])
    )


def main() -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--new-prefix", default="20260821",
                    help="Run-dir timestamp prefix of the post-fix batch.")
    ap.add_argument("--verbose", action="store_true",
                    help="Print the full old/new partition for every date.")
    args = ap.parse_args()

    new_dirs = sorted(RUNS.glob(f"{args.new_prefix}_*"))
    buckets: dict[str, list[str]] = {
        "CHANGED": [], "SAME": [], "NO-PRIOR": [], "UNUSABLE": [],
    }

    for nd in new_dirs:
        date = nd.name.split("_", 2)[-1]
        priors = sorted(p for p in RUNS.glob(f"*_{date}")
                        if not p.name.startswith(f"{args.new_prefix}_"))
        new_part, new_note = parse_clusters(nd / "report.md")
        has_new_analysis = (nd / "analysis.md").is_file()

        if not priors:
            buckets["NO-PRIOR"].append(date)
            print(f"{date}  NO-PRIOR    new_analysis={'Y' if has_new_analysis else 'N'}")
            continue

        prior = priors[-1]
        old_part, old_note = parse_clusters(prior / "report.md")
        old_analysis = prior / "analysis.md"

        if new_part is None or old_part is None:
            buckets["UNUSABLE"].append(date)
            why = new_note or old_note
            print(f"{date}  UNUSABLE    {why}  (prior={prior.name})")
            continue

        # Confirm the de-dup actually took effect on at least one source.
        old_tr, new_tr = ingest_tracks(prior / "report.md"), ingest_tracks(nd / "report.md")
        shrunk = sorted(lb for lb, n in old_tr.items()
                        if lb in new_tr and new_tr[lb] < n)

        if old_part == new_part:
            buckets["SAME"].append(date)
            tag = "SAME"
        else:
            buckets["CHANGED"].append(date)
            tag = "CHANGED"
        print(f"{date}  {tag:9s}  old_families={len(old_part)} new_families={len(new_part)}  "
              f"dedup_shrunk={','.join(shrunk) or 'none'}  "
              f"old_analysis={'Y' if old_analysis.is_file() else 'N'} "
              f"new_analysis={'Y' if has_new_analysis else 'N'}  prior={prior.name}")
        if args.verbose or tag == "CHANGED":
            print(f"      old: {describe(old_part)}")
            print(f"      new: {describe(new_part)}")

    print("\n=== SUMMARY ===")
    for k, v in buckets.items():
        print(f"  {k:9s} {len(v):3d}  {' '.join(v) if v else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
