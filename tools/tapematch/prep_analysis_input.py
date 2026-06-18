#!/usr/bin/env python3
"""prep_analysis_input.py — bundle inputs needed to write a run's analysis.md.

For each run folder under data/tapematch/runs/ that has a report.md but no
analysis.md, this collects the LB numbers referenced in that run's coverage
table and pulls their original archive info files from data/site/files/
(LBF-<lbnum>-*.txt). Archive txt files use dozens of ad-hoc ripper-tool
suffixes (.md5, .flacf, .ffp, .shnf, .sfv, .st5, ...) for pure checksum/
shntool dumps that carry no lineage prose, and some files (xref-*) mix a
checksum block with real prose. Rather than chase every suffix convention,
checksum-looking lines (hex digests, "===" banners, shntool rows) are
stripped from each file's content; files left with no real prose afterward
are skipped.

It writes one bundle file, analysis_input.md, into each run folder:
report.md verbatim, followed by the matched LB info-file text per LB number.
That bundle is the only input a writer (human or agent) needs to produce
analysis.md for that run — no separate digging through data/site required.

Usage:
    python prep_analysis_input.py                  # all missing runs
    python prep_analysis_input.py RUN_DIR [RUN_DIR ...]
    python prep_analysis_input.py --list-missing    # just print the run dirs
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "data" / "tapematch" / "runs"
SITE_FILES_DIR = REPO_ROOT / "data" / "site" / "files"

LB_TAG_RE = re.compile(r"\bLB-(\d+)\b(?!…|\.\.\.)")

# Lines that are pure checksum/shntool noise rather than lineage prose.
_BANNER_RE = re.compile(r"^=+\s*$|^===.*===\s*$|^===.*for:.*$")
_HEX_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{16,40}[ *]")
_SHNTOOL_ROW_RE = re.compile(r"^\s*\d+:\d+\.\d+\s+\d+\s*B")
_SHNTOOL_HEADER_RE = re.compile(r"^\s*length\s+expanded size\b")
_TOOL_COMMENT_RE = re.compile(r"^\s*;")
_MIN_PROSE_CHARS = 40

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def find_missing_runs() -> list[Path]:
    """Return run dirs that have report.md but no analysis.md yet."""
    return sorted(
        d for d in RUNS_DIR.iterdir()
        if d.is_dir() and (d / "report.md").exists() and not (d / "analysis.md").exists()
    )


def lb_numbers_in_report(report_text: str) -> list[str]:
    """Extract distinct LB numbers (as zero-padded 5-digit strings) from a report.

    Commentary snippets ("Commentary vs tapematch audit", "LB page
    commentary") are truncated for display and can cut a multi-digit LB
    number short, gluing an ellipsis directly onto the remaining digits
    (e.g. "LB-4794…" truncated to "LB-47…"). A naive \\bLB-(\\d+)\\b scan
    misreads "47" as a real, distinct LB number and pulls in an unrelated
    info file. Genuine LB references in prose are never glued directly to
    "…" or "...", so excluding that adjacency filters out truncation
    artifacts while still picking up legitimate cross-references (e.g.
    "see 7/26/88 LB-7841 for info as part of that set").
    """
    seen: dict[str, None] = {}
    for m in LB_TAG_RE.finditer(report_text):
        padded = m.group(1).zfill(5)
        seen[padded] = None
    return list(seen)


def strip_checksum_noise(text: str) -> str:
    """Drop hex-digest lines, "===" banners, and shntool rows from a txt file body."""
    kept = [
        line for line in text.splitlines()
        if not (
            _BANNER_RE.match(line)
            or _HEX_DIGEST_RE.match(line)
            or _SHNTOOL_ROW_RE.match(line)
            or _SHNTOOL_HEADER_RE.match(line)
            or _TOOL_COMMENT_RE.match(line)
        )
    ]
    return "\n".join(kept).strip()


def info_files_for_lb(lb_padded: str) -> list[Path]:
    """Return candidate info txt files for one LB number, sorted by name."""
    return sorted(SITE_FILES_DIR.glob(f"LBF-{lb_padded}-*.txt"))


def build_bundle(run_dir: Path) -> str:
    """Build the analysis_input.md content for one run dir."""
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    lb_numbers = lb_numbers_in_report(report_text)

    sections = ["# Analysis input bundle\n", "## report.md\n", report_text.rstrip(), ""]
    sections.append("## Source info files (data/site/files)\n")

    for lb_padded in lb_numbers:
        files = info_files_for_lb(lb_padded)
        seen_bodies: set[str] = set()
        kept_any = False
        for f in files:
            raw = f.read_text(encoding="utf-8", errors="replace")
            body = strip_checksum_noise(raw)
            if len(body) < _MIN_PROSE_CHARS or body in seen_bodies:
                continue
            seen_bodies.add(body)
            kept_any = True
            sections.append(f"### LB-{lb_padded} — {f.name}\n")
            sections.append(body)
            sections.append("")
        if not kept_any:
            sections.append(f"### LB-{lb_padded}: no info file found\n")

    return "\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="*", help="Specific run dir(s); default: all missing")
    parser.add_argument("--list-missing", action="store_true", help="Just print missing run dirs")
    args = parser.parse_args()

    if args.list_missing:
        for d in find_missing_runs():
            print(d)
        return

    targets = [Path(p).resolve() for p in args.run_dirs] if args.run_dirs else find_missing_runs()
    log.info("Building analysis_input.md for %d run(s)...", len(targets))

    for run_dir in targets:
        bundle = build_bundle(run_dir)
        out_path = run_dir / "analysis_input.md"
        out_path.write_text(bundle, encoding="utf-8")
        log.info("  wrote %s", out_path.relative_to(REPO_ROOT))

    log.info("Done.")


if __name__ == "__main__":
    main()
