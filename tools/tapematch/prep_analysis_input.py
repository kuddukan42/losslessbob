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

LB numbers scraped out of uploader commentary are frequently typo'd or refer
to a different concert entirely (BUG-328), so every LB number is checked
against the run's own date before its info file is attached: on-date sources
go in the main section, everything else goes under an explicit
"cross-references" heading that tells the writer not to read it as lineage
for this run.

Usage:
    python prep_analysis_input.py                  # all missing runs
    python prep_analysis_input.py RUN_DIR [RUN_DIR ...]
    python prep_analysis_input.py --list-missing    # just print the run dirs
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "data" / "tapematch" / "runs"
SITE_FILES_DIR = REPO_ROOT / "data" / "site" / "files"
DB_PATH = REPO_ROOT / "data" / "losslessbob.db"

LB_TAG_RE = re.compile(r"\bLB-(\d+)\b(?!…|\.\.\.)")
# A run dir is named <timestamp>_<ISO date>, e.g. 20260710_120810_1999-06-20.
_RUN_DIR_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
# "# tapematch session — 1999-06-20 — Anaheim, California, ..."
_REPORT_DATE_RE = re.compile(r"^#\s+tapematch session\s+\S\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)
# Coverage-table rows: "| LB-00857 | ✓ | B+ | ..." — the run's own sources.
_COVERAGE_ROW_RE = re.compile(r"^\|\s*LB-(\d+)\s*\|", re.MULTILINE)
# entries.date_str is M/D/YY (unpadded), e.g. "6/20/99".
_DB_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2})\s*$")

# Lines that are pure checksum/shntool noise rather than lineage prose.
_BANNER_RE = re.compile(r"^=+\s*$|^===.*===\s*$|^===.*for:.*$")
_HEX_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{16,40}[ *]")
_SHNTOOL_ROW_RE = re.compile(r"^\s*\d+:\d+\.\d+\s+\d+\s*B")
_SHNTOOL_HEADER_RE = re.compile(r"^\s*length\s+expanded size\b")
_TOOL_COMMENT_RE = re.compile(r"^\s*;")
# "some\path\Track 01.flac:d0768cdb27099fc..." — per-track checksum manifest
# lines (.ffp/.flacf/lbdir dumps). These start with a filename/path, not a
# bare hex digest, so _HEX_DIGEST_RE never catches them; site-wide these are
# ~499k lines, always ".flac"/".FLAC", never carrying lineage prose.
_CHECKSUM_MANIFEST_RE = re.compile(r"\.flac\s*:\s*[0-9a-fA-F]{16,40}\s*$", re.IGNORECASE)
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
            or _CHECKSUM_MANIFEST_RE.search(line)
        )
    ]
    return "\n".join(kept).strip()


def coverage_lb_numbers(report_text: str) -> set[str]:
    """Return the zero-padded LB numbers listed in the report's coverage table.

    These are the run's own sources, so they belong to the run's date by
    construction and never need a date check.
    """
    return {m.group(1).zfill(5) for m in _COVERAGE_ROW_RE.finditer(report_text)}


def run_date_iso(run_dir: Path, report_text: str) -> str | None:
    """Return the run's concert date as ``YYYY-MM-DD``, or None if undetermined.

    The run dir name carries the date as its suffix; the report title is used
    as a fallback for run dirs that were renamed or built by hand.
    """
    m = _RUN_DIR_DATE_RE.search(run_dir.name)
    if m:
        return m.group(1)
    m = _REPORT_DATE_RE.search(report_text)
    return m.group(1) if m else None


def db_date_matches_iso(date_str: str, iso: str) -> bool:
    """Check whether an ``entries.date_str`` (``M/D/YY``) is the same day as an ISO date.

    Compared field-by-field on the two-digit year rather than by parsing into
    a ``datetime``, so no century-pivot guess is involved (see BUG-280) — the
    corpus has no two dates that share a day, month and two-digit year.

    Args:
        date_str: A date from ``entries.date_str``, e.g. ``"6/20/99"``.
        iso: An ISO date, e.g. ``"1999-06-20"``.

    Returns:
        True if both denote the same calendar day.
    """
    m = _DB_DATE_RE.match(date_str or "")
    if not m:
        return False
    month, day, year2 = (int(g) for g in m.groups())
    y, mo, d = (int(part) for part in iso.split("-"))
    return (month, day, year2) == (mo, d, y % 100)


def lb_dates(db_path: Path = DB_PATH) -> dict[str, tuple[str, str]]:
    """Map zero-padded LB number -> (date_str, location) from the entries table.

    Returns an empty mapping when the DB is absent or unreadable, in which
    case no LB number can be date-verified and every prose reference is
    reported as such rather than silently trusted.
    """
    if not db_path.exists():
        log.warning("  %s not found — LB dates cannot be verified", db_path)
        return {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT lb_number, date_str, location FROM entries WHERE lb_number IS NOT NULL"
            ).fetchall()
    except sqlite3.Error as exc:
        log.warning("  could not read %s (%s) — LB dates cannot be verified", db_path, exc)
        return {}
    return {str(lb).zfill(5): (date or "", loc or "") for lb, date, loc in rows}


def info_files_for_lb(lb_padded: str) -> list[Path]:
    """Return candidate info txt files for one LB number, sorted by name."""
    return sorted(SITE_FILES_DIR.glob(f"LBF-{lb_padded}-*.txt"))


def _info_sections(lb_padded: str, heading_suffix: str = "") -> list[str]:
    """Render the de-duplicated, noise-stripped info-file bodies for one LB number."""
    sections: list[str] = []
    seen_bodies: set[str] = set()
    for f in info_files_for_lb(lb_padded):
        body = strip_checksum_noise(f.read_text(encoding="utf-8", errors="replace"))
        if len(body) < _MIN_PROSE_CHARS or body in seen_bodies:
            continue
        seen_bodies.add(body)
        sections.append(f"### LB-{lb_padded} — {f.name}{heading_suffix}\n")
        sections.append(body)
        sections.append("")
    if not sections:
        sections.append(f"### LB-{lb_padded}: no info file found{heading_suffix}\n")
    return sections


def build_bundle(run_dir: Path, lb_date_map: dict[str, tuple[str, str]] | None = None) -> str:
    """Build the analysis_input.md content for one run dir.

    LB numbers found only in uploader commentary are checked against the run's
    date (BUG-328). Ones from another concert — or ones whose date cannot be
    established — are still attached, because a genuine cross-reference is
    useful evidence, but under a heading that names the other date so the
    writer does not reconcile them as this run's lineage.

    Args:
        run_dir: The run folder, which must contain report.md.
        lb_date_map: Optional pre-loaded LB -> (date_str, location) mapping;
            loaded from the app DB when omitted.

    Returns:
        The full analysis_input.md text.
    """
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    lb_numbers = lb_numbers_in_report(report_text)
    in_set = coverage_lb_numbers(report_text)
    run_iso = run_date_iso(run_dir, report_text)
    dates = lb_dates() if lb_date_map is None else lb_date_map

    on_date: list[str] = []
    cross_refs: list[tuple[str, str]] = []  # (lb_padded, heading suffix)
    for lb_padded in lb_numbers:
        if lb_padded in in_set:
            on_date.append(lb_padded)
            continue
        date_str, location = dates.get(lb_padded, ("", ""))
        if run_iso and date_str and db_date_matches_iso(date_str, run_iso):
            on_date.append(lb_padded)
        elif date_str:
            where = f", {location}" if location else ""
            cross_refs.append((lb_padded, f"  [DIFFERENT DATE: {date_str}{where}]"))
        else:
            cross_refs.append((lb_padded, "  [DATE UNKNOWN — not in the entries table]"))

    sections = ["# Analysis input bundle\n", "## report.md\n", report_text.rstrip(), ""]
    sections.append("## Source info files (data/site/files)\n")
    for lb_padded in on_date:
        sections.extend(_info_sections(lb_padded))

    if cross_refs:
        run_label = run_iso or "this run's date"
        sections.append("## Cross-references from commentary — NOT sources for this run\n")
        sections.append(
            "These LB numbers appear only in uploader prose, not in this run's coverage "
            f"table, and do not belong to {run_label}. Uploader commentary routinely "
            "carries typo'd LB numbers, so treat each as a claim to verify, never as "
            "lineage for a source in this run.\n"
        )
        for lb_padded, suffix in cross_refs:
            sections.extend(_info_sections(lb_padded, suffix))

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
    date_map = lb_dates()

    for run_dir in targets:
        bundle = build_bundle(run_dir, date_map)
        out_path = run_dir / "analysis_input.md"
        out_path.write_text(bundle, encoding="utf-8")
        log.info("  wrote %s", out_path.relative_to(REPO_ROOT))

    log.info("Done.")


if __name__ == "__main__":
    main()
