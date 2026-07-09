#!/usr/bin/env python3
"""Auto-write analysis.md for trivially clean tapematch runs; escalate the rest.

Splits the analysis backlog (run dirs with report.md but no analysis.md) into:

- SKIP      — incomplete set (insufficient/missing sources, no CLUSTERS):
              left alone, same as /tapematch-batch (re-picked when sources appear).
- AUTO      — nothing for a human/Claude to judge: complete set, every source its
              own family (no merges), DIAGNOSTICS limited to [DISTINCT SOURCE] /
              [INCOMPLETE], no run errors, and gen_analysis's commentary
              cross-check raises no MISS / FALSE MERGE observation.
              analysis.md is written from gen_analysis's template with an honest
              auto-triage attribution line.
- ESCALATE  — everything else (merges, timing mismatches, confidence-tagged
              links, stderr/exit-code, commentary contradictions): left for
              /tapematch-batch, where real judgment is applied.

Default is report-only. Nothing is written without --apply.

Usage:
    .venv/bin/python3 tools/tapematch/triage_analysis.py            # classify only
    .venv/bin/python3 tools/tapematch/triage_analysis.py --apply    # write AUTO dirs
    .venv/bin/python3 tools/tapematch/triage_analysis.py --apply --limit 20
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import gen_analysis as ga

RUNS_DIR = Path(__file__).parent.parent.parent / "data" / "tapematch" / "runs"

# Diagnostic tags that do NOT block an all-distinct auto verdict.
ALLOWED_TAGS = {"DISTINCT SOURCE", "INCOMPLETE"}

ATTRIBUTION = f"*auto-triage (triage_analysis.py, gen_analysis template) — {ga.TODAY}*"

log = logging.getLogger("triage_analysis")


def diagnostics_tags(report_text: str) -> set[str]:
    """Return the set of bracketed tags in the report's DIAGNOSTICS section."""
    m = re.search(r"^=== DIAGNOSTICS ===$(.*?)(?:^## |\Z)", report_text,
                  re.MULTILINE | re.DOTALL)
    if not m:
        return set()
    return set(re.findall(r"\[([A-Z][A-Z /_-]*)\]", m.group(1)))


def classify(run_dir: Path) -> tuple[str, str]:
    """Classify one run dir.

    Returns:
        (category, reason) where category is one of AUTO / ESCALATE / SKIP.
    """
    report_path = run_dir / "report.md"
    r = ga.parse_report(report_path)

    if r["insufficient_sources"] or r["missing_sources"]:
        return "SKIP", "incomplete set"
    if r["has_error"]:
        return "ESCALATE", "run error (stderr/exit code)"

    n_src = r["coverage_disk"]
    n_fam = r["n_families"] or len(r["clusters"])
    if not n_fam:
        return "SKIP", "no CLUSTERS section"
    if n_fam != n_src:
        return "ESCALATE", f"{n_fam} families < {n_src} sources (merges need judgment)"

    report_text = report_path.read_text(errors="replace")
    bad_tags = diagnostics_tags(report_text) - ALLOWED_TAGS
    if bad_tags:
        return "ESCALATE", "diagnostics: " + ", ".join(sorted(bad_tags))
    if "EXIT CODE" in report_text or "STDERR" in report_text:
        return "ESCALATE", "stderr/exit-code in tapematch output"

    results: dict = {}
    results_path = run_dir / "results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text())
    rows = ga._source_rows(r, results)
    obs = ga._build_observations(r, rows)
    verdict = ga._verdict(r, obs)
    if "MISS" in verdict or "FALSE MERGE" in verdict:
        return "ESCALATE", f"commentary cross-check: {verdict}"
    # Commentary-derived relationships between two in-set LBs are judgment
    # territory unless the snippet explicitly agrees with the all-distinct
    # result (a _DIFF_PATS hit — "different source/recording/taper" — while
    # tapematch also put the pair in different families). MISS / FALSE MERGE
    # pair notes escalate via the verdict check above; ambiguous notes (no
    # clear signal either way) escalate here.
    pair_note = re.compile(r"### LB-\d+ (?:/|→) LB-\d+")
    for o in obs:
        if not pair_note.search(o):
            continue
        m = re.search(r'LB commentary notes: "(.*)"', o)
        if m and ga._diff_signal(m.group(1)):
            continue
        return "ESCALATE", "commentary cross-check: in-set pair note needs judgment"
    if any("staircase lag curve" in o for o in obs):
        return "ESCALATE", "staircase lag curve"

    return "AUTO", f"{n_src} sources, all distinct, clean diagnostics"


def write_auto(run_dir: Path) -> None:
    """Write analysis.md for an AUTO-classified run dir with honest attribution."""
    r = ga.parse_report(run_dir / "report.md")
    results: dict = {}
    results_path = run_dir / "results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text())
    content = ga.build_analysis(run_dir, r, results)
    lines = content.splitlines()
    if len(lines) > 1 and lines[1].startswith("*Claude"):
        lines[1] = ATTRIBUTION
    (run_dir / "analysis.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="Write analysis.md for AUTO dirs (default: report only).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max AUTO dirs to write with --apply (0 = no limit).")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Log every dir, not just the summary.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(message)s", stream=sys.stdout)

    pending = sorted(
        d for d in RUNS_DIR.iterdir()
        if d.is_dir() and (d / "report.md").exists()
        and not (d / "analysis.md").exists()
    )
    buckets: dict[str, list[tuple[Path, str]]] = {"AUTO": [], "ESCALATE": [], "SKIP": []}
    for run_dir in pending:
        try:
            cat, reason = classify(run_dir)
        except Exception as exc:  # parse failure = never auto-write
            cat, reason = "ESCALATE", f"classify failed: {exc}"
        buckets[cat].append((run_dir, reason))
        log.debug("%-9s %s — %s", cat, run_dir.name, reason)

    written = 0
    if args.apply:
        todo = buckets["AUTO"][: args.limit or None]
        for run_dir, _ in todo:
            write_auto(run_dir)
            written += 1
            log.info("wrote %s/analysis.md", run_dir.name)

    log.info("")
    log.info("pending=%d | AUTO=%d | ESCALATE=%d | SKIP(incomplete)=%d | written=%d",
             len(pending), len(buckets["AUTO"]), len(buckets["ESCALATE"]),
             len(buckets["SKIP"]), written)
    if not args.apply:
        log.info("(report-only — re-run with --apply to write AUTO analyses)")
    reasons: dict[str, int] = {}
    for _, reason in buckets["ESCALATE"]:
        key = "merges need judgment" if "families <" in reason else reason.split(":")[0]
        reasons[key] = reasons.get(key, 0) + 1
    for key, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        log.info("  escalate: %-45s %d", key, n)


if __name__ == "__main__":
    main()
