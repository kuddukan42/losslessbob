#!/usr/bin/env python3
"""
scan_collection_folders.py — LosslessBob collection folder audit tool.

Reads disk_path + lb_number from my_collection, then scans each registered
folder and all immediate sub-folders for LB tag patterns in folder names.

Reports:
  A  Sub-folders with LB tags not registered in my_collection
  B  Top-level collection folders with multiple LB numbers in the name
       (collection likely only linked to the first)
  C  Folders containing xref tokens after an LB number
  D  Top-level collection folders whose name LB does not match the DB lb_number
  E  Sub-folders with NO LB tag (unidentified content under a registered path)

Usage:
  python tools/scan_collection_folders.py [--db PATH] [--depth N] [--json] [--out FILE]

  --db PATH     Path to losslessbob.db  (default: data/losslessbob.db)
  --depth N     How many directory levels below each disk_path to scan (default: 2)
  --json        Output machine-readable JSON instead of plain text report
  --out FILE    Write report to FILE (stdout if omitted)
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# LB pattern helpers
# ---------------------------------------------------------------------------

# Matches a single LB token, zero-padded or not: LB-328, LB-0328, LB-00328.
# Uses (?!\d) instead of trailing \b so that underscore-suffixed tokens like
# 'LB-328_xref99' are captured — \b does not fire between a digit and '_'
# because underscore is \w.
_LB_RE = re.compile(r'\bLB-(\d+)(?!\d)', re.IGNORECASE)

# Matches xref token directly after (or near) an LB token.
# Covers: LB-123-xref456, LB-123 xref-456, LB-123 xref 456, LB-5000_xref500
# NOTE: no trailing \b after (\d+) — underscore is \w so \b fires between
#       a digit and '_', which would break 'LB-5000_xref500'.
_XREF_RE = re.compile(
    r'\bLB-(\d+)(?!\d)'        # LB token — no trailing \b
    r'(?:'
        r'(?:[\s-]+xref[-_\s]?(\d+))'   # space/dash-separated: 'LB-123 xref-456'
        r'|'
        r'(?:[_-]xref[-_]?(\d+))'        # underscore/dash-attached: 'LB-5000_xref500'
    r')',
    re.IGNORECASE,
)

# Standalone xref number not attached to an explicit LB (rare)
_XREF_BARE_RE = re.compile(r'\bxref[-_]?(\d+)\b', re.IGNORECASE)

# Pure disc/tape/track label: disc1, Disc Two, cd1, d1, side a, tape 1, etc.
# Pure disc/tape label: disc1, disc 2, disk-1, cd1, d1, side a, Disc Two, disc too, etc.
_DISC_ONLY_RE = re.compile(
    r'^(?:disc|disk|cd|d|side|tape)\s*[-_]?\s*'
    r'(?:\d+|[a-d]|one|two|too|three|four|five|six|seven|eight|nine|ten)$',
    re.IGNORECASE,
)

# Name ends with a disc indicator — bracketed ([CD1], (Disc 2)) or separator-attached (-d1, _cd2).
_DISC_SUFFIX_RE = re.compile(
    r'(?:'
    r'[\[\(]\s*(?:cd|disc|disk|d)\s*\d+\s*[\]\)]'   # [CD1], (Disc 2)
    r'|'
    r'[-_]\s*(?:cd|disc|disk|d)\s*\d+'               # -d1, _cd2, -disc1
    r')'
    r'(?:\.\w+)?\s*$',
    re.IGNORECASE,
)

# Common structural media sub-folders that are never LB-tagged.
_STRUCTURAL_NAME_RE = re.compile(
    r'^(?:flacs?|mp3s?|wavs?|art|artwork|scans?|covers?|extras?|bonus|'
    r'liner\s*notes?|booklet|images?|photos?|pictures?|pics?|videos?|info|'
    r'infofiles?|tracks?)$',
    re.IGNORECASE,
)

# Compound structural names: "Artwork & Info", "Artwork and info", "Info_files", etc.
_STRUCTURAL_WORDS = (
    r'artwork?|art|info|infofiles?|scans?|covers?|extras?|flacs?|mp3s?|wavs?|'
    r'tracks?|liner\s*notes?|booklet|files?|images?|photos?|videos?|bonus'
)
_COMPOUND_STRUCTURAL_RE = re.compile(
    r'^(?:' + _STRUCTURAL_WORDS + r')'
    r'(?:\s*(?:[&+]|and|_)\s*(?:' + _STRUCTURAL_WORDS + r'))*$',
    re.IGNORECASE,
)

# Audio quality spec sub-folders: 16_44, 24_96, 16-44, etc.
_QUALITY_SPEC_RE = re.compile(r'^\d{1,2}[-_]\d{2,3}(?:k?hz)?$', re.IGNORECASE)

# Date-prefixed disc labels with no LB.
# ISO (bd2005-07-30d1, bd_00-06-21_cd1.shnf), YYMMDD (791103 d2 verified), YY-MM-DD (98-06-07d1.shnf).
_DATE_DISC_RE = re.compile(
    r'^(?:'
    r'[a-z_]{0,6}\d{4}-\d{2}-\d{2}[-_]?\s*(?:d|disc|cd)\s*\d+(?:\s+\w+)*(?:\.\w+)?'  # ISO
    r'|'
    r'\d{6}\s*[-_]?\s*(?:d|disc|cd)\s*\d+(?:\s+\w+)*(?:\.\w+)?'                        # YYMMDD
    r'|'
    r'[a-z_]{0,6}\d{2}-\d{2}-\d{2}[-_]?\s*(?:d|disc|cd)\s*\d+(?:\s+\w+)*(?:\.\w+)?'  # YY-MM-DD
    r')$',
    re.IGNORECASE,
)

# Bare disc numbers: "1", "2", "01", "02" — clearly structural when standing alone.
_BARE_DISC_NUM_RE = re.compile(r'^\d{1,2}$')


def extract_lb_numbers(name: str) -> list[int]:
    """Return all LB numbers found in a folder name, in order."""
    return [int(m) for m in _LB_RE.findall(name)]


def extract_xrefs(name: str) -> list[tuple[int, int]]:
    """Return [(lb_number, xref_number), ...] for xref tokens in name."""
    results = []
    for m in _XREF_RE.finditer(name):
        lb = int(m.group(1))
        xref = int(m.group(2) or m.group(3))
        results.append((lb, xref))
    return results


def has_any_lb(name: str) -> bool:
    return bool(_LB_RE.search(name))


def has_any_xref(name: str) -> bool:
    return bool(_XREF_RE.search(name) or _XREF_BARE_RE.search(name))


def is_structural_subfolder(name: str) -> bool:
    """Return True if name is a structural sub-folder that will never carry an LB tag.

    Covers: pure disc/tape labels (disc1, Disc Two, cd2, tape 1, side a),
    names ending with a bracketed disc indicator (Title [CD1]), and common
    media/artwork folders (flac, art, artwork, scans, covers, extras, …).
    """
    n = name.strip()
    return bool(
        _DISC_ONLY_RE.match(n)
        or _DISC_SUFFIX_RE.search(n)
        or _STRUCTURAL_NAME_RE.match(n)
        or _COMPOUND_STRUCTURAL_RE.match(n)
        or _QUALITY_SPEC_RE.match(n)
        or _DATE_DISC_RE.match(n)
        or _BARE_DISC_NUM_RE.match(n)
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_collection(db_path: str) -> dict[str, int]:
    """Return {disk_path: lb_number} for all my_collection rows."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT disk_path, lb_number FROM my_collection")
        return {row["disk_path"]: row["lb_number"] for row in cur.fetchall()}
    finally:
        conn.close()


def load_all_lb_numbers(db_path: str) -> set[int]:
    """Return the set of all lb_numbers known in the checksums table."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        cur = conn.execute("SELECT DISTINCT lb_number FROM checksums")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def load_folder_links(db_path: str) -> dict[str, int]:
    """Return {folder_path: lb_number} from folder_lb_link."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT folder_path, lb_number FROM folder_lb_link")
        return {row["folder_path"]: row["lb_number"] for row in cur.fetchall()}
    finally:
        conn.close()


def load_collection_filenames(db_path: str, lb_numbers: set[int]) -> dict[int, set[str]]:
    """Return {lb_number: set[filename]} for the given lb_numbers from checksums."""
    if not lb_numbers:
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        cur = conn.execute(
            f"SELECT lb_number, filename FROM checksums WHERE lb_number IN ({placeholders})",
            list(lb_numbers),
        )
        result: dict[int, set[str]] = defaultdict(set)
        for lb, fname in cur.fetchall():
            result[lb].add(fname)
        return dict(result)
    finally:
        conn.close()


_AUDIO_EXTS = frozenset({".flac", ".shn", ".wav", ".mp3", ".ape", ".ogg", ".m4a", ".wv"})


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_folder(
    root_path: str,
    registered_lb: int,
    collection_paths: set[str],
    folder_links: dict[str, int],
    known_lbs: set[int],
    max_depth: int,
    lb_filenames: dict[int, set[str]] | None = None,
) -> dict:
    """
    Scan root_path up to max_depth levels deep.

    Returns a dict with keys:
      top_lbs          list[int]   all LB numbers in the root folder name
      top_xrefs        list[(int,int)]
      top_lb_mismatch  bool        root name LB != registered_lb (if any LB in name)
      sub_findings     list[dict]  one entry per interesting sub-folder
    """
    root = Path(root_path)
    root_name = root.name

    top_lbs = extract_lb_numbers(root_name)
    top_xrefs = extract_xrefs(root_name)

    # mismatch: folder has an LB in name but it doesn't match DB
    top_lb_mismatch = bool(top_lbs and top_lbs[0] != registered_lb)

    sub_findings = []

    if not root.is_dir():
        return {
            "top_lbs": top_lbs,
            "top_xrefs": top_xrefs,
            "top_lb_mismatch": top_lb_mismatch,
            "sub_findings": sub_findings,
            "missing_root": True,
        }

    def _recurse(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return
        for child in entries:
            if not child.is_dir():
                continue
            child_str = str(child)
            child_name = child.name

            # Skip if already a top-level collection entry itself
            if child_str in collection_paths:
                continue

            lbs = extract_lb_numbers(child_name)
            xrefs = extract_xrefs(child_name)
            bare_xrefs = [int(m) for m in _XREF_BARE_RE.findall(child_name)
                          if not any(x[1] == int(m) for x in xrefs)]

            if lbs or xrefs or bare_xrefs:
                in_folder_link = child_str in folder_links
                linked_lb = folder_links.get(child_str)
                in_collection = child_str in collection_paths

                flags = []
                if lbs:
                    flags.append("has_lb")
                if len(lbs) > 1:
                    flags.append("multi_lb")
                if xrefs:
                    flags.append("has_xref")
                if bare_xrefs:
                    flags.append("bare_xref")
                # Only flag unlinked if the LBs aren't all already covered by the
                # parent collection entry.  A subfolder named with the same LB as
                # its parent needs no separate registration.
                covered_by_parent = lbs and all(lb == registered_lb for lb in lbs)
                if not in_collection and not in_folder_link and not covered_by_parent:
                    flags.append("unlinked")
                if in_folder_link:
                    flags.append("folder_linked")

                # Check whether the LBs are known in the checksums table
                unknown_lbs = [lb for lb in lbs if lb not in known_lbs]

                sub_findings.append({
                    "path": child_str,
                    "name": child_name,
                    "depth": depth,
                    "lb_numbers": lbs,
                    "xrefs": [(lb, x) for lb, x in xrefs],
                    "bare_xrefs": bare_xrefs,
                    "unknown_lbs": unknown_lbs,
                    "in_collection": in_collection,
                    "folder_linked": in_folder_link,
                    "linked_lb": linked_lb,
                    "flags": flags,
                })
            else:
                # No LB tag — report as unidentified if shallow and the name has
                # enough content to be meaningful (skip pure disc/track labels).
                if depth == 1 and not is_structural_subfolder(child_name):
                    # Suppress if the subfolder's audio files are already registered
                    # under the parent lb_number in the checksums table.
                    parent_fnames = (lb_filenames or {}).get(registered_lb, set())
                    covered = parent_fnames and any(
                        f.suffix.lower() in _AUDIO_EXTS and f.name in parent_fnames
                        for f in child.iterdir()
                        if f.is_file()
                    )
                    if not covered:
                        sub_findings.append({
                            "path": child_str,
                            "name": child_name,
                            "depth": depth,
                            "lb_numbers": [],
                            "xrefs": [],
                            "bare_xrefs": [],
                            "unknown_lbs": [],
                            "in_collection": child_str in collection_paths,
                            "folder_linked": child_str in folder_links,
                            "linked_lb": folder_links.get(child_str),
                            "flags": ["no_lb_tag"],
                        })

            _recurse(child, depth + 1)

    _recurse(root, 1)

    return {
        "top_lbs": top_lbs,
        "top_xrefs": top_xrefs,
        "top_lb_mismatch": top_lb_mismatch,
        "sub_findings": sub_findings,
        "missing_root": False,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

ISSUE_LABELS = {
    "A": "Sub-folder with LB tag(s) — not in collection/folder_lb_link",
    "B": "Top-level folder has MULTIPLE LB numbers in name (only first linked)",
    "C": "Folder name contains xref token",
    "D": "Top-level folder name LB does not match DB lb_number",
    "E": "Sub-folder with NO LB tag (unidentified content)",
    "F": "Sub-folder LB number unknown in checksums table",
    "G": "Root folder path does not exist on disk",
}


def classify_top(scan: dict, registered_lb: int, disk_path: str) -> list[dict]:
    issues = []
    if scan.get("missing_root"):
        issues.append({"code": "G", "path": disk_path, "detail": "Path missing"})
        return issues
    top_lbs = scan["top_lbs"]
    top_xrefs = scan["top_xrefs"]
    if scan["top_lb_mismatch"]:
        issues.append({
            "code": "D",
            "path": disk_path,
            "detail": f"Name LB={top_lbs[0]}, DB lb_number={registered_lb}",
        })
    if len(top_lbs) > 1:
        issues.append({
            "code": "B",
            "path": disk_path,
            "detail": f"LBs in name: {top_lbs}  (DB links only lb_number={registered_lb})",
        })
    if top_xrefs:
        issues.append({
            "code": "C",
            "path": disk_path,
            "detail": f"xrefs in name: {top_xrefs}",
        })
    return issues


def classify_sub(finding: dict) -> list[dict]:
    issues = []
    flags = finding["flags"]
    path = finding["path"]
    lbs = finding["lb_numbers"]
    xrefs = finding["xrefs"]
    unknown = finding["unknown_lbs"]

    if "no_lb_tag" in flags:
        issues.append({"code": "E", "path": path, "detail": f"No LB tag — name: {finding['name']}"})
        return issues

    if "unlinked" in flags and lbs:
        issues.append({
            "code": "A",
            "path": path,
            "detail": (
                f"LBs={lbs}"
                + (f"  xrefs={xrefs}" if xrefs else "")
                + (f"  bare_xrefs={finding['bare_xrefs']}" if finding["bare_xrefs"] else "")
                + f"  depth={finding['depth']}"
            ),
        })
    if len(lbs) > 1:
        issues.append({
            "code": "B",
            "path": path,
            "detail": f"Multiple LBs in name: {lbs}",
        })
    if xrefs:
        issues.append({
            "code": "C",
            "path": path,
            "detail": f"xrefs in name: {xrefs}",
        })
    if unknown:
        issues.append({
            "code": "F",
            "path": path,
            "detail": f"LB numbers not found in checksums table: {unknown}",
        })
    return issues


def build_report(
    collection: dict[str, int],
    scan_results: dict[str, dict],
    folder_links: dict[str, int],
) -> dict:
    all_issues = defaultdict(list)
    per_path = {}

    for disk_path, registered_lb in collection.items():
        scan = scan_results.get(disk_path, {})
        path_issues = []

        # Top-level checks
        path_issues.extend(classify_top(scan, registered_lb, disk_path))

        # Sub-folder checks
        for finding in scan.get("sub_findings", []):
            path_issues.extend(classify_sub(finding))

        per_path[disk_path] = path_issues
        for issue in path_issues:
            all_issues[issue["code"]].append(issue)

    summary = {code: len(items) for code, items in all_issues.items()}
    return {
        "summary": summary,
        "issues_by_code": dict(all_issues),
        "issues_by_collection_path": {
            p: issues for p, issues in per_path.items() if issues
        },
    }


def print_text_report(report: dict, outfile):
    summary = report["summary"]
    total = sum(summary.values())

    print("=" * 72, file=outfile)
    print("LosslessBob Collection Folder Audit Report", file=outfile)
    print("=" * 72, file=outfile)
    print(f"\nTotal issues found: {total}\n", file=outfile)

    for code, label in ISSUE_LABELS.items():
        count = summary.get(code, 0)
        print(f"  [{code}] {count:>4}  {label}", file=outfile)

    print(file=outfile)

    for code, label in ISSUE_LABELS.items():
        items = report["issues_by_code"].get(code, [])
        if not items:
            continue
        print("-" * 72, file=outfile)
        print(f"[{code}] {label}  ({len(items)} items)", file=outfile)
        print("-" * 72, file=outfile)
        for issue in sorted(items, key=lambda x: x["path"]):
            print(f"  {issue['path']}", file=outfile)
            print(f"    → {issue['detail']}", file=outfile)
        print(file=outfile)

    print("=" * 72, file=outfile)
    print("End of report", file=outfile)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Audit collection folders for LB tag anomalies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        default="data/losslessbob.db",
        help="Path to losslessbob.db (default: data/losslessbob.db)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Sub-directory levels to scan below each disk_path (default: 2)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of plain text",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write output to this file (default: stdout)",
    )
    args = parser.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading collection from {db_path} …", file=sys.stderr)
    collection = load_collection(db_path)
    if not collection:
        print("my_collection is empty — nothing to scan.", file=sys.stderr)
        sys.exit(0)

    print(f"  {len(collection)} collection entries", file=sys.stderr)

    known_lbs = load_all_lb_numbers(db_path)
    folder_links = load_folder_links(db_path)
    collection_paths = set(collection.keys())

    print("Loading checksums filenames …", file=sys.stderr)
    lb_filenames = load_collection_filenames(db_path, set(collection.values()))
    print(f"  {sum(len(v) for v in lb_filenames.values())} filename entries", file=sys.stderr)

    print(f"Scanning folders (depth={args.depth}) …", file=sys.stderr)
    scan_results: dict[str, dict] = {}
    for i, (disk_path, registered_lb) in enumerate(collection.items(), 1):
        if i % 100 == 0:
            print(f"  {i}/{len(collection)} …", file=sys.stderr)
        scan_results[disk_path] = scan_folder(
            disk_path,
            registered_lb,
            collection_paths,
            folder_links,
            known_lbs,
            args.depth,
            lb_filenames,
        )

    print("Building report …", file=sys.stderr)
    report = build_report(collection, scan_results, folder_links)

    outfile = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.json:
            json.dump(report, outfile, indent=2)
            print(file=outfile)
        else:
            print_text_report(report, outfile)
    finally:
        if args.out:
            outfile.close()

    total = sum(report["summary"].values())
    print(f"Done. {total} issues reported.", file=sys.stderr)
    if args.out:
        print(f"Report written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
