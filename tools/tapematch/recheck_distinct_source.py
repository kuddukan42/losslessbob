#!/usr/bin/env python3
"""TODO-324 steps (1)-(2): re-check written analysis.md verdicts that may have
leaned on a [DISTINCT SOURCE] claim whose speed ratio was actually untrusted
(speed_kind == 'speed-unknown' in results.json — fallout from BUG-330).

Step 1 — scan: for every run dir under data/tapematch/runs/*, find
[DISTINCT SOURCE] lines in report.md and cross-reference the named source
against results.json. A line is "affected" when that source's speed_kind is
'speed-unknown' (i.e. the ppm figure quoted in the line was already rejected
by the pipeline as untrustworthy).

Step 2 — classify: for the affected lines whose run dir has a written
analysis.md, decide whether the verdict in that file relies on the (bad)
distinct-source claim as its ONLY support, or whether it rests on independent
evidence (LB-page commentary, taper attribution, fingerprint/dice linking,
lineage/documented-source facts, etc). Only the former need a real re-run
(TODO-324 steps 3-4, out of scope here).

Outputs:
  - tools/tapematch/DISTINCT_SOURCE_RECHECK.md   (tracked summary + re-run list)
  - data/tapematch/distinct_source_recheck.json  (gitignored, full per-row detail)

Deterministic heuristic (see classify_source() docstring for the full
decision tree). No audio is touched; no analysis.md is rewritten; tapematch
is never invoked.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "data" / "tapematch" / "runs"
SUMMARY_PATH = REPO_ROOT / "tools" / "tapematch" / "DISTINCT_SOURCE_RECHECK.md"
JSON_PATH = REPO_ROOT / "data" / "tapematch" / "distinct_source_recheck.json"

DISTINCT_SOURCE_RE = re.compile(
    r"\[DISTINCT SOURCE\]\s+(?P<name>.+?)\s+\("
    r"(?P<ppm>[+-]?\d+)\s+ppm speed offset,\s*"
    r"best cross-family corr\s+(?P<corr>[\d.]+)\)"
)

LB_ID_RE = re.compile(r"\(LB-\d+\)")
LB_ID_BARE_RE = re.compile(r"LB-\d+")

# Table row: | LB-XXXXX | Rating | Timing | Source | Family | Notes |
TABLE_ROW_RE = re.compile(r"^\|\s*(LB-\d+)\s*\|(.*)\|\s*$")

# Phrases that show the analysis text is doing nothing more than restating
# the algorithm's own [DISTINCT SOURCE] reasoning (speed offset / near-zero
# correlation) with no independent corroboration. Documented here for the
# reader; the classifier's default bucket already covers this case (see
# classify_source), so this list is not matched against directly.
ONLY_CLAIM_MARKERS = (
    "correctly isolated as distinct source",
    "near-zero correlation",
    "possible tape deck speed",
    "differently clocked",
    "pal/cassette",
    "pal/ntsc",
    "speed offset",
    "tape pitch drift",
)

# Phrases showing the verdict cites evidence independent of the (untrusted)
# speed ratio / correlation claim — commentary, documented attribution,
# fingerprint linking, lineage facts, cross-referenced info files, etc.
OTHER_EVIDENCE_MARKERS = (
    "commentary",
    "info file",
    "info-file",
    "fp-linked",
    "fp linked",
    "fingerprint",
    "dice",
    "taper",
    "attribution",
    "mis-dated",
    "mis-reports",
    "misreport",
    "mislabel",
    "same source as",
    "same recording",
    "unknown taper as",
    "xref",
    "md5",
    "trade chain",
    "sourced from",
    "different tour",
    "own note",
    "own commentary",
    "bittorrent",
    "write-up",
    "curator-noted",
    "cross-referenced",
)

BUCKETS = (
    "only-claim",  # verdict's sole support is the (bad) distinct-source claim -> re-run
    "other-evidence",  # verdict also cites independent evidence -> no change needed
    "unclear-no-mention",  # source isolated in table but never discussed in prose -> re-run (conservative)
    "merged-despite-flag",  # analysis.md verdict merged this source anyway -> claim was already rejected
    "unparseable",  # no usable table / no analysis text matched -> manual review
    "no-analysis",  # run dir has no analysis.md at all -> out of TODO-324 step-2 scope
)


@dataclass
class AffectedRow:
    run_dir: str
    date: str
    source_name: str
    lb_id: str | None
    ppm: int
    corr: float
    has_analysis: bool
    bucket: str
    reason: str
    matched_text: str = ""


def normalize_lb_id(lb_id: str) -> str:
    """LB ids appear zero-padded to 5 digits in the DB/analysis tables but
    sometimes unpadded in report.md source names (e.g. "LB-2690" vs
    "LB-02690"). Normalize to 5 digits so both forms compare equal.
    """
    prefix, _, num = lb_id.partition("-")
    return f"{prefix}-{int(num):05d}"


def extract_lb_id(source_name: str) -> str | None:
    m = LB_ID_RE.search(source_name)
    if not m:
        # Fall back to a bare "LB-#####" anywhere in the name (e.g. names
        # ending in "...DS Archive-LB-15782" with no surrounding parens).
        m = LB_ID_BARE_RE.search(source_name)
    if not m:
        return None
    return normalize_lb_id(m.group(0).strip("()"))


def find_distinct_source_lines(report_text: str) -> list[tuple[str, int, float]]:
    out = []
    for m in DISTINCT_SOURCE_RE.finditer(report_text):
        out.append((m.group("name"), int(m.group("ppm")), float(m.group("corr"))))
    return out


def load_speed_kinds(results: dict) -> dict[str, str]:
    sources = results.get("sources", {})
    return {name: s.get("speed_kind") for name, s in sources.items()}


def parse_table(analysis_text: str) -> dict[str, dict]:
    """Return {lb_id: {"family": str, "notes": str}} from the first markdown
    table found (header: | LB | Rating | Timing | Source | Family | Notes |).
    Family column is assumed to be the second-to-last cell, Notes the last.
    """
    rows: dict[str, dict] = {}
    for line in analysis_text.splitlines():
        m = TABLE_ROW_RE.match(line.strip())
        if not m:
            continue
        lb_id = normalize_lb_id(m.group(1))
        rest = m.group(2)
        cells = [c.strip() for c in rest.split("|")]
        if len(cells) < 2:
            continue
        family = cells[-2] if len(cells) >= 2 else ""
        notes = cells[-1] if cells else ""
        rows[lb_id] = {"family": family, "notes": notes}
    return rows


def prose_paragraphs_for(lb_id: str, analysis_text: str) -> str:
    """Return the prose evidence for lb_id: every markdown "section" (a run
    of blank-line-delimited paragraphs starting at a "#"-heading and
    continuing to the next heading) where lb_id appears anywhere in the
    section, plus any headingless paragraph mentioning lb_id directly.

    A verdict's evidence for a source is often stated once, in the section
    heading (e.g. "### LB-06485 — clustered as distinct, ..."), and then
    discussed over several following paragraphs that never repeat the LB id
    (e.g. the next paragraph opens "Report.md clusters LB-06485 alone..." but
    the paragraph after THAT — the one with "own info file describes the
    identical chain" — doesn't mention LB-06485 again by name). Matching only
    lines/paragraphs containing the literal id would miss that evidence, so
    the whole section is treated as one unit once the heading names the LB.
    """
    non_table_lines = [
        line for line in analysis_text.splitlines() if not line.strip().startswith("|")
    ]
    text = "\n".join(non_table_lines)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    sections: list[list[str]] = []
    for p in paragraphs:
        if p.startswith("#") or not sections:
            sections.append([p])
        else:
            sections[-1].append(p)

    matched: list[str] = []
    for section in sections:
        if any(lb_id in p for p in section):
            matched.append("\n\n".join(section))
    return "\n\n".join(matched)


def classify_source(
    lb_id: str | None,
    source_name: str,
    analysis_text: str,
) -> tuple[str, str, str]:
    """Deterministic decision tree. Returns (bucket, reason, matched_text).

    1. No LB id extractable from the source name -> unparseable.
    2. Parse the analysis.md verdict table (LB | ... | Family | Notes).
       - lb_id not found in any row -> fall back to prose-only search (3);
         if that finds nothing either -> unparseable.
       - lb_id's family number is shared with >=1 other row -> merged-despite-flag
         (the written verdict already didn't treat this source as distinct,
         so the untrusted claim was not relied upon).
       - lb_id is alone in its family -> continue to (3).
    3. Build context text = table Notes cell + every prose "section"
       (heading + its following paragraphs, see prose_paragraphs_for)
       mentioning lb_id anywhere in the section.
       - context is empty -> unclear-no-mention (isolated in the table, never
         discussed in prose; conservatively treated as needing re-run).
       - context contains any OTHER_EVIDENCE_MARKERS keyword -> other-evidence.
       - otherwise (context only restates speed/correlation, or is generic
         boilerplate matching ONLY_CLAIM_MARKERS) -> only-claim.
    """
    if not lb_id:
        return "unparseable", "no LB id in source name", ""

    table = parse_table(analysis_text)
    if lb_id not in table:
        prose = prose_paragraphs_for(lb_id, analysis_text)
        if not prose:
            return "unparseable", "no table row and no prose mention", ""
        lower = prose.lower()
        if any(k in lower for k in OTHER_EVIDENCE_MARKERS):
            return "other-evidence", "prose-only match on evidence keyword", prose
        return "only-claim", "prose-only, no independent-evidence keyword found", prose

    row = table[lb_id]
    family = row["family"]
    sibling_lbs = [
        other for other, r in table.items() if other != lb_id and r["family"] == family and family
    ]
    if family and sibling_lbs:
        return (
            "merged-despite-flag",
            f"verdict placed {lb_id} in family {family} with {', '.join(sibling_lbs)}",
            "",
        )

    context = (row["notes"] + "\n" + prose_paragraphs_for(lb_id, analysis_text)).strip()
    if not context:
        return "unclear-no-mention", "isolated family, no notes/prose mention of this LB", ""

    lower = context.lower()
    if any(k in lower for k in OTHER_EVIDENCE_MARKERS):
        return "other-evidence", "matched independent-evidence keyword", context
    # Default: isolated family, notes/prose exist (often matching
    # ONLY_CLAIM_MARKERS like "near-zero correlation" / "speed offset") but
    # cite nothing beyond the algorithm's own [DISTINCT SOURCE] reasoning.
    return "only-claim", "isolated family, only speed/correlation reasoning found", context


def scan() -> list[AffectedRow]:
    affected: list[AffectedRow] = []
    for run_dir in sorted(RUNS_DIR.glob("*")):
        if not run_dir.is_dir():
            continue
        report_path = run_dir / "report.md"
        results_path = run_dir / "results.json"
        if not report_path.exists() or not results_path.exists():
            continue
        report_text = report_path.read_text(errors="replace")
        lines = find_distinct_source_lines(report_text)
        if not lines:
            continue
        try:
            results = json.loads(results_path.read_text())
        except json.JSONDecodeError:
            continue
        speed_kinds = load_speed_kinds(results)

        date = run_dir.name.split("_", 2)[-1] if "_" in run_dir.name else run_dir.name
        analysis_path = run_dir / "analysis.md"
        has_analysis = analysis_path.exists()
        analysis_text = analysis_path.read_text(errors="replace") if has_analysis else ""

        for name, ppm, corr in lines:
            if speed_kinds.get(name) != "speed-unknown":
                continue
            lb_id = extract_lb_id(name)
            if not has_analysis:
                affected.append(
                    AffectedRow(
                        run_dir=run_dir.name,
                        date=date,
                        source_name=name,
                        lb_id=lb_id,
                        ppm=ppm,
                        corr=corr,
                        has_analysis=False,
                        bucket="no-analysis",
                        reason="run dir has no analysis.md",
                    )
                )
                continue
            bucket, reason, matched = classify_source(lb_id, name, analysis_text)
            affected.append(
                AffectedRow(
                    run_dir=run_dir.name,
                    date=date,
                    source_name=name,
                    lb_id=lb_id,
                    ppm=ppm,
                    corr=corr,
                    has_analysis=True,
                    bucket=bucket,
                    reason=reason,
                    matched_text=matched[:400],
                )
            )
    return affected


def write_json(rows: list[AffectedRow]) -> None:
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps([asdict(r) for r in rows], indent=2, ensure_ascii=False) + "\n")


def write_summary(rows: list[AffectedRow]) -> None:
    counts: dict[str, int] = {b: 0 for b in BUCKETS}
    for r in rows:
        counts[r.bucket] = counts.get(r.bucket, 0) + 1

    rerun_rows = [r for r in rows if r.bucket in ("only-claim", "unclear-no-mention")]
    rerun_dates = sorted({r.date for r in rerun_rows})
    rerun_run_dirs = sorted({r.run_dir for r in rerun_rows})

    lines = []
    lines.append("# TODO-324 steps 1-2 — distinct-source re-check")
    lines.append("")
    lines.append(
        "Generated by `tools/tapematch/recheck_distinct_source.py`. Scans "
        "`data/tapematch/runs/*/report.md` for `[DISTINCT SOURCE]` lines whose "
        "named source has `speed_kind == 'speed-unknown'` in `results.json` "
        "(the untrusted-ppm fallout from BUG-330), then classifies whether "
        "each run's written `analysis.md` verdict relies on that claim alone."
    )
    lines.append("")
    lines.append("## Bucket counts")
    lines.append("")
    lines.append("| Bucket | Count | Meaning |")
    lines.append("|---|---|---|")
    lines.append(f"| only-claim | {counts['only-claim']} | verdict's sole support is the bad claim — re-run candidate |")
    lines.append(
        f"| unclear-no-mention | {counts['unclear-no-mention']} | isolated in the verdict table, never discussed in prose — treated as re-run candidate (conservative) |"
    )
    lines.append(
        f"| other-evidence | {counts['other-evidence']} | verdict also cites commentary/fingerprint/lineage evidence — no change needed |"
    )
    lines.append(
        f"| merged-despite-flag | {counts['merged-despite-flag']} | written verdict already merged this source anyway — claim was not relied upon |"
    )
    lines.append(f"| unparseable | {counts['unparseable']} | table/prose format didn't match — needs manual look |")
    lines.append(f"| no-analysis | {counts['no-analysis']} | run dir has no analysis.md — out of TODO-324 step-2 scope |")
    lines.append("")
    lines.append(f"Total affected `[DISTINCT SOURCE]` lines scanned: **{len(rows)}**")
    lines.append("")
    lines.append("## Re-run list (TODO-324 step 3 input)")
    lines.append("")
    lines.append(
        f"**{len(rerun_dates)} dates** ({len(rerun_run_dirs)} run dirs) whose written verdict turns on an "
        "untrusted distinct-source claim (`only-claim` + `unclear-no-mention` buckets). "
        "Re-running tapematch for these dates is step 3, out of scope for this script."
    )
    lines.append("")
    if rerun_dates:
        lines.append("<details><summary>dates</summary>")
        lines.append("")
        for d in rerun_dates:
            lines.append(f"- {d}")
        lines.append("")
        lines.append("</details>")
    lines.append("")
    lines.append(
        "Full per-row detail (source name, ppm, corr, matched text, reason) is in "
        "the gitignored `data/tapematch/distinct_source_recheck.json`."
    )
    lines.append("")
    SUMMARY_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    rows = scan()
    write_json(rows)
    write_summary(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.bucket] = counts.get(r.bucket, 0) + 1
    print(f"scanned {len(rows)} affected [DISTINCT SOURCE] lines")
    for b in BUCKETS:
        print(f"  {b}: {counts.get(b, 0)}")


if __name__ == "__main__":
    main()
