#!/usr/bin/env python3
"""TODO-324 step 1-2: find analysis verdicts that may rest on a BUG-330 line.

Scans every run dir for `[DISTINCT SOURCE]` diagnostics whose source is
recorded in results.json as ``speed_kind == "speed-unknown"`` -- the lines
BUG-330 showed were gated on, and quoted, a speed ratio the pipeline had
already rejected. For each such row it collects the corroborating evidence
that exists independently of that line, so the re-check can be aimed at the
verdicts that actually turn on it instead of all 2,000 run dirs.

Emits a TSV work file; prints the class distribution. Read-only, and safe to
re-run: it rebuilds the queue from scratch each time.

Usage:
    .venv/bin/python3 tools/tapematch/todo324_scan.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = ROOT / "data" / "tapematch" / "runs"
OUT = ROOT / "tools" / "tapematch" / "todo324_recheck_queue.tsv"

DS_RE = re.compile(
    r"\[DISTINCT SOURCE\] (?P<name>.+?) \((?P<ppm>[-+]\d+) ppm speed offset, "
    r"best cross-family corr (?P<corr>[\d.]+)\)")
LB_RE = re.compile(r"LB-?(\d{3,6})")
SITE_FILES = ROOT / "data" / "site" / "files"
# A taper asserting their tape is not someone else's. Two shapes occur: prose
# ("different recording than LB-2569 and jtt LB-5390") and a bare link
# ("This is NOT: http://jokerman.org.uk/lb/detail/LB-05390.html"). The clause
# may name several LBs, so the tail is captured and mined for ids.
#
# The comparative connector (than/from/as/...) is REQUIRED: without it the
# pattern swallows upload boilerplate like "alternate recordings I am sharing
# for this date", whose trailing LB ids are a track list, not a claim. That
# misread credits a verdict with corroboration it never had -- the one error
# direction that silently drops a broken verdict out of the queue. Same
# boilerplate-false-positive shape as TODO-322.
DISTINCT_CLAIM_RE = re.compile(
    r"(?:(?:different|not the same|separate|alternate)\s+"
    r"(?:recording|source|tape|taping)s?\s+(?:than|from|to|as|vs\.?)"
    r"|this is not\b)(?P<tail>[^.;|]{0,160})",
    re.IGNORECASE)

_claims_cache: dict[str, set[str]] = {}
_lbf_index: dict[str, list[Path]] | None = None


def lbf_index() -> dict[str, list[Path]]:
    """Map each LB id to its info files, scanning data/site/files once.

    prep_analysis_input.py globs per LB, which is fine for one run's handful of
    sources; this scan touches thousands, and the directory holds ~99k files,
    so a single pass replaces tens of thousands of directory walks.
    """
    global _lbf_index
    if _lbf_index is None:
        _lbf_index = {}
        for f in SITE_FILES.iterdir():
            n = f.name
            if not n.startswith("LBF-") or not n.endswith(".txt"):
                continue
            parts = n.split("-", 2)
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            _lbf_index.setdefault(lb_pad(parts[1]), []).append(f)
    return _lbf_index


def lb_pad(num: str | int) -> str:
    """Return the canonical zero-padded LB id for a raw number."""
    return f"LB-{int(num):05d}"


def distinct_claims(lb: str) -> set[str]:
    """Return the LB ids this LB's own info files assert it is distinct from.

    Reads data/site/files/LBF-<padded>-*.txt, the same prose
    prep_analysis_input.py bundles -- report.md truncates its commentary block
    at a few hundred characters, so the assertions are usually not in it.

    Args:
        lb: Zero-padded LB id, e.g. "LB-05390".

    Returns:
        Zero-padded LB ids named in a distinctness claim; empty if none.
    """
    if lb in _claims_cache:
        return _claims_cache[lb]
    out: set[str] = set()
    for f in lbf_index().get(lb, ()):
        try:
            txt = f.read_text(errors="replace")
        except OSError:
            continue
        for m in DISTINCT_CLAIM_RE.finditer(txt):
            out.update(lb_pad(g) for g in LB_RE.findall(m.group("tail")))
    out.discard(lb)
    _claims_cache[lb] = out
    return out


def lb_of(name: str) -> str:
    """Return the zero-padded LB id in a source name, or '' if it has none."""
    m = LB_RE.search(name)
    return lb_pad(m.group(1)) if m else ""


def section(text: str, header: str, stop: str = r"^(?:## |=== )") -> str:
    """Return the body of one report.md section, or '' if absent."""
    m = re.search(rf"^{re.escape(header)}.*?$(.*?)(?={stop}|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def scan_run(rd: Path) -> list[dict]:
    """Collect one run dir's affected rows, with independent-evidence signals."""
    rep, rj = rd / "report.md", rd / "results.json"
    if not rep.exists() or not rj.exists():
        return []
    text = rep.read_text(errors="replace")
    hits = list(DS_RE.finditer(text))
    if not hits:
        return []
    try:
        srcs = json.load(open(rj)).get("sources", {})
    except Exception:
        return []

    audit = section(text, "## Commentary vs tapematch audit")
    secondary = section(text, "=== SECONDARY MATCH")
    has_analysis = (rd / "analysis.md").exists()

    # Distinctness is symmetric evidence: if any source in this run asserts it
    # is a different recording from LB-X, that corroborates the split for both
    # the claimant and LB-X, so credit runs in both directions.
    run_lbs = {lb_of(n) for n in srcs} - {""}
    asserted: set[str] = set()
    for lb in run_lbs:
        named = distinct_claims(lb) & run_lbs
        if named:
            asserted.add(lb)
            asserted |= named

    rows = []
    for h in hits:
        name = h.group("name")
        info = srcs.get(name)
        if not isinstance(info, dict) or info.get("speed_kind") != "speed-unknown":
            continue
        lb = lb_of(name)
        short = lb.replace("LB-0", "LB-").replace("LB-0", "LB-") if lb else ""
        disagrees = sum(
            1 for line in audit.splitlines()
            if "DISAGREES" in line and lb and (lb in line or short in line))
        # Per-LINE, not per-section: an earlier version asked only whether the
        # LB and the words "SECONDARY LINK" both appeared somewhere in the
        # section, which credited a source with a link that belonged to an
        # unrelated pair. Both of its "contradicted" hits turned out to sit on
        # below-threshold lines instead.
        sec_lines = [ln for ln in secondary.splitlines() if lb and lb in ln]
        fp_linked = any("SECONDARY LINK" in ln for ln in sec_lines)
        sec_subthreshold = any("below merge threshold" in ln for ln in sec_lines)
        rows.append({
            "run": rd.name,
            "lb": lb or "(no LB)",
            "ppm": h.group("ppm"),
            "corr": h.group("corr"),
            "conf": f"{info.get('speed_confidence', float('nan')):.2f}",
            "commentary_says_distinct": lb in asserted,
            "audit_disagrees": disagrees,
            "fp_linked": fp_linked,
            "sec_subthreshold": sec_subthreshold,
            "has_analysis": has_analysis,
        })
    return rows


def classify(r: dict) -> str:
    """Bucket one row by how much the verdict leans on the BUG-330 line."""
    if r["fp_linked"]:
        return "CONTRADICTED"          # secondary evidence links it to something
    if r["sec_subthreshold"]:
        # Real hiss/fingerprint overlap that missed the merge bar, on a source
        # simultaneously called "entirely different recording" off an untrusted
        # ratio. The two claims cannot both be right; see also BUG-329.
        return "CONFLICTED-SUBTHRESHOLD"
    if r["commentary_says_distinct"]:
        return "SAFE-COMMENTARY"       # a taper asserts the split independently
    if r["audit_disagrees"]:
        return "AT-RISK-DISAGREES"     # commentary already fought the clustering
    return "AT-RISK-UNCORROBORATED"    # the line was the only support


def main() -> int:
    rows = []
    for rd in sorted(RUNS.iterdir()):
        if rd.is_dir():
            rows.extend(scan_run(rd))
    for r in rows:
        r["class"] = classify(r)

    cols = ["class", "run", "lb", "ppm", "corr", "conf", "commentary_says_distinct",
            "audit_disagrees", "fp_linked", "sec_subthreshold", "has_analysis"]
    with open(OUT, "w") as f:
        f.write("# TODO-324 re-check queue (BUG-330 fallout). Generated by tools/_todo324_scan.py\n")
        f.write("\t".join(cols) + "\n")
        for r in sorted(rows, key=lambda x: (x["class"], x["run"])):
            f.write("\t".join(str(r[c]) for c in cols) + "\n")

    print(f"affected rows: {len(rows)}   run dirs: {len({r['run'] for r in rows})}")
    print(f"written: {OUT.relative_to(ROOT)}\n")
    print(f"{'class':<26} {'rows':>6} {'run dirs':>9} {'w/ analysis.md':>15}")
    for c in sorted({r["class"] for r in rows}):
        sub = [r for r in rows if r["class"] == c]
        dirs = {r["run"] for r in sub}
        withan = {r["run"] for r in sub if r["has_analysis"]}
        print(f"{c:<26} {len(sub):>6} {len(dirs):>9} {len(withan):>15}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
