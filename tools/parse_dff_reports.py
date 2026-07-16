#!/usr/bin/env python3
"""Parse DigiFlawFinder HTML reports and store per-LB flaw counts in the DB.

DigiFlawFinder (sffog.com) is a tool that analyses 16-bit WAV files from DAT
transfers and reports four flaw types:

  DROP  — sustained samples at 0 (silence gaps / buffer drops)
  CLIP  — sustained clipping at ±32767
  HORZ  — horizontal lines: samples stuck at a constant value (square-wave static)
  VERT  — vertical jumps between samples (digipops, discontinuities)

14,090 DFF HTML reports are downloaded and stored in data/site/files/ under the
pattern::

  LBF-{lb}-DigiFlawFinder-{name}.html      primary: canonical report for LB {lb}
  LBF-{lb}-xref-{id}-DigiFlawFinder.html   report for LB {lb}'s alternate
                                            fileset xref-{id}

Per docs/XREF_SEMANTICS.md §2, ``{id}`` is a fileset id from a global
sequence — it is *not* an LB number and must not be treated as one. The row
belongs to ``lb_number = {lb}``, ``xref = {id}``.

This tool reads all downloaded reports, extracts the total occurrence counts
from the "Totals" section, and writes them to the ``dff_reports`` table,
keyed by the composite ``(lb_number, xref)`` fileset identity (``xref = 0``
for the primary/canonical report).

Strategy
--------
* Each ``(lb_number, xref)`` fileset is its own row. Multiple files for the
  same fileset (e.g. disc-1 + disc-2) are **summed**.
* Re-running is idempotent: existing rows are replaced.

Usage::

    python tools/parse_dff_reports.py
    python tools/parse_dff_reports.py --db data/losslessbob.db
    python tools/parse_dff_reports.py --files-dir data/site/files
    python tools/parse_dff_reports.py --dry-run

Must be run from the project root (the folder containing ``backend/`` and
``tools/``).
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from backend.paths import DB_PATH, SITE_FILES_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_DFF_SCHEMA = """
CREATE TABLE IF NOT EXISTS dff_reports (
    lb_number  INTEGER NOT NULL,
    xref       INTEGER NOT NULL DEFAULT 0,
    drop_occ   INTEGER NOT NULL DEFAULT 0,
    clip_occ   INTEGER NOT NULL DEFAULT 0,
    horz_occ   INTEGER NOT NULL DEFAULT 0,
    vert_occ   INTEGER NOT NULL DEFAULT 0,
    file_count INTEGER NOT NULL DEFAULT 0,
    parsed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lb_number, xref)
);
"""

_RE_PRIMARY = re.compile(r'^LBF-(\d+)-DigiFlawFinder-', re.IGNORECASE)
_RE_XREF = re.compile(r'^LBF-(\d+)-xref-(\d+)-DigiFlawFinder', re.IGNORECASE)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create ``dff_reports`` with the ``(lb_number, xref)`` composite PK.

    Migrates from the legacy ``lb_number``-only-PK schema (pre-TODO-246 B5)
    by dropping and recreating the table — it has no consumers that depend
    on rows surviving a schema change, so a full reparse is acceptable.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(dff_reports)")}
    if cols and "xref" not in cols:
        log.info(
            "Migrating dff_reports to (lb_number, xref) composite PK — "
            "dropping legacy table"
        )
        conn.execute("DROP TABLE dff_reports")
    conn.executescript(_DFF_SCHEMA)


def _parse_totals(path: Path) -> dict[str, int] | None:
    """Extract (drop_occ, clip_occ, horz_occ, vert_occ) from a DFF HTML file.

    Returns None on any parse failure; returns a dict with zero values if the
    Totals section is found but a flaw type has no occurrences.
    """
    try:
        html = path.read_text(encoding="cp1252", errors="replace")
    except OSError:
        return None

    # Strip HTML tags, convert non-breaking spaces, drop non-ASCII artifacts
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("\xa0", " ").replace("\xc2", " ")
    text = re.sub(r"[^\x00-\x7f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Newer DFF version (v1.0.0.41+) emits "No Flaws Found" with no Totals block.
    if re.search(r"No\s+Flaws\s+Found", text, re.IGNORECASE):
        return {"drop": 0, "clip": 0, "horz": 0, "vert": 0}

    # Locate the Totals block (appears once near the end)
    m = re.search(
        r"Totals\s+Left\s+Len\s+Left\s+Occ(.+?)(?:Application\s+DigiFlawFinder|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    block = m.group(1)

    result: dict[str, int] = {}
    for flaw in ("DROP", "CLIP", "HORZ", "VERT"):
        fm = re.search(rf"\b{flaw}\b([^\n]*)", block, re.IGNORECASE)
        if fm:
            # Total Occ = last integer on the line (after left_len left_occ
            # right_len right_occ total_len).  `\d+` on floats like '.63098'
            # returns ['63098'], so the final element is always Total Occ.
            nums = re.findall(r"\d+", fm.group(1))
            result[flaw.lower()] = int(nums[-1]) if nums else 0
        else:
            result[flaw.lower()] = 0

    return result


def _classify_files(files_dir: Path) -> dict[tuple[int, int], list[Path]]:
    """Group DFF report files by ``(lb_number, xref)`` fileset identity.

    ``xref == 0`` is the LB's own canonical/primary report(s); ``xref > 0``
    is an alternate fileset, keyed by the LB it belongs to (the filename's
    first number) and the fileset id (the filename's second number) — per
    docs/XREF_SEMANTICS.md §2 the id is *not* an LB number.
    """
    groups: dict[tuple[int, int], list[Path]] = defaultdict(list)

    for path in files_dir.iterdir():
        name = path.name
        m = _RE_XREF.match(name)
        if m:
            groups[(int(m.group(1)), int(m.group(2)))].append(path)
            continue
        m = _RE_PRIMARY.match(name)
        if m:
            groups[(int(m.group(1)), 0)].append(path)

    return dict(groups)


def _aggregate(paths: list[Path]) -> dict[str, int] | None:
    """Parse and SUM flaw counts across multiple DFF files (e.g. multi-disc)."""
    totals: dict[str, int] | None = None
    for p in paths:
        t = _parse_totals(p)
        if t is None:
            continue
        if totals is None:
            totals = dict(t)
        else:
            for k in totals:
                totals[k] += t[k]
    return totals


def parse_and_store(
    db_path: Path | None = None,
    files_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Parse all DFF reports and write results to the dff_reports table.

    Returns a summary dict with counts: parsed, skipped, written, errors.
    """
    db_path = db_path or DB_PATH
    files_dir = files_dir or SITE_FILES_DIR

    if not files_dir.exists():
        log.error("Files directory not found: %s", files_dir)
        return {"parsed": 0, "skipped": 0, "written": 0, "errors": 1}

    log.info("Scanning %s for DFF reports …", files_dir)
    groups = _classify_files(files_dir)
    n_primary = sum(1 for (_, xref) in groups if xref == 0)
    n_xref = len(groups) - n_primary
    log.info(
        "Found %d filesets (%d primary, %d xref)", len(groups), n_primary, n_xref
    )

    rows: list[tuple[int, int, int, int, int, int, int]] = []
    errors = 0

    for (lb, xref), paths in groups.items():
        t = _aggregate(paths)
        if t is None:
            errors += 1
            log.debug(
                "Parse failed for LB-%d xref-%d (%d files)", lb, xref, len(paths)
            )
            continue
        rows.append(
            (lb, xref, t["drop"], t["clip"], t["horz"], t["vert"], len(paths))
        )

    log.info("Parsed %d filesets (%d errors)", len(rows), errors)

    if dry_run:
        log.info("[dry-run] Would write %d rows — no DB changes made", len(rows))
        return {"parsed": len(rows), "skipped": 0, "written": 0, "errors": errors}

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn)
        conn.executemany(
            """INSERT OR REPLACE INTO dff_reports
               (lb_number, xref, drop_occ, clip_occ, horz_occ, vert_occ,
                file_count, parsed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    log.info("Wrote %d rows to dff_reports", len(rows))
    return {"parsed": len(rows), "skipped": 0, "written": len(rows), "errors": errors}


def _print_summary(db_path: Path | None = None) -> None:
    """Print correlation of DFF vert_occ with LB rating (quick validation).

    Restricted to canonical (``xref = 0``) rows so each LB contributes once;
    alternate-fileset rows would otherwise fan out the join.
    """
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("""
            SELECT e.rating, d.vert_occ
            FROM dff_reports d
            JOIN entries e ON d.lb_number = e.lb_number
            WHERE e.rating IS NOT NULL AND d.xref = 0
        """).fetchall()
    finally:
        conn.close()

    from collections import defaultdict as dd
    import statistics

    by_tier: dict[str, list[int]] = dd(list)
    for rating, vert in rows:
        by_tier[rating].append(vert)

    order = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
    print(f"\n{'Rating':6s} {'n':>6s} {'median_vert':>12s} {'pct_nonzero':>12s}")
    print("-" * 42)
    for t in order:
        vals = by_tier.get(t, [])
        if vals:
            med = statistics.median(vals)
            pct = sum(1 for v in vals if v > 0) / len(vals) * 100
            print(f"{t:6s} {len(vals):>6d} {med:>12.0f} {pct:>11.0f}%")

    total = len(rows)
    covered = sum(1 for _, v in rows if v is not None)
    print(f"\nTotal LBs with rating + DFF data: {total} ({covered} with vert data)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", metavar="PATH", help="Override database path")
    ap.add_argument("--files-dir", metavar="DIR", help="Override files directory")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse but do not write to the database")
    ap.add_argument("--summary", action="store_true",
                    help="Print vert_occ vs rating summary after writing")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else None
    files_dir = Path(args.files_dir) if args.files_dir else None

    result = parse_and_store(db_path=db_path, files_dir=files_dir, dry_run=args.dry_run)
    print(
        f"DFF parse complete: {result['parsed']} parsed, "
        f"{result['written']} written, {result['errors']} errors"
    )

    if args.summary and not args.dry_run:
        _print_summary(db_path=db_path)


if __name__ == "__main__":
    main()
