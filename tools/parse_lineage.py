#!/usr/bin/env python3
"""Batch-populate entry_lineage from entries.description.

Usage:
    python tools/parse_lineage.py [--force] [--lb N] [--limit N] [--dry-run]

Options:
    --force     Re-parse all rows even if source_text_hash is unchanged.
    --lb N      Parse only LB-N (for spot-checking).
    --limit N   Stop after N rows (for testing).
    --dry-run   Parse but do not write to DB; print results to stdout.

The script is safe to kill mid-run and resume: the source_text_hash guard skips
unchanged entries on the next run so partial runs never corrupt the table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db  # noqa: E402
from backend.db import (  # noqa: E402
    _compute_parse_confidence,
    _normalise_taper,
    extract_lb_references,
    extract_taper_and_source,
    get_connection,
    get_lineage,
    get_write_queue,
    upsert_entry_lineage,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _build_row(lb_number: int, description: str) -> dict:
    taper_name, source_chain = extract_taper_and_source(description)
    refs = extract_lb_references(description)
    taper_normalised = _normalise_taper(taper_name)
    confidence = _compute_parse_confidence(description, taper_name, source_chain)
    text_hash = _sha256(description)
    return {
        "lb_number": lb_number,
        "taper_name": taper_name,
        "source_chain": source_chain,
        "taper_normalised": taper_normalised,
        "mentions_lb": json.dumps(refs["mentions_lb"]),
        "same_as_lb": json.dumps(refs["same_as_lb"]),
        "derived_from_lb": json.dumps(refs["derived_from_lb"]),
        "better_than_lb": json.dumps(refs["better_than_lb"]),
        "parse_confidence": confidence,
        "source_text_hash": text_hash,
    }


def run(
    force: bool = False,
    lb_filter: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    db_path: str | None = None,
) -> None:
    """Parse entries and populate entry_lineage.

    Args:
        force:     Re-parse even when source_text_hash matches.
        lb_filter: If given, parse only this LB number.
        limit:     Stop after this many rows processed.
        dry_run:   Print results without writing to DB.
        db_path:   Optional database path override.
    """
    db.init_db(db_path)

    conn = get_connection(db_path)
    if lb_filter is not None:
        rows = conn.execute(
            "SELECT lb_number, description FROM entries"
            " WHERE lb_number = ? AND description IS NOT NULL AND description != ''",
            (lb_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT lb_number, description FROM entries"
            " WHERE description IS NOT NULL AND description != ''"
            " ORDER BY lb_number"
        ).fetchall()

    total = len(rows)
    if limit:
        rows = rows[:limit]

    parsed = 0
    skipped = 0
    errors = 0
    taper_found = 0
    chain_found = 0
    refs_found = 0

    for idx, row in enumerate(rows, 1):
        lb_number = row["lb_number"]
        description = row["description"]

        try:
            text_hash = _sha256(description)

            if not force and not dry_run:
                existing = get_lineage(lb_number, db_path)
                if existing and existing.get("source_text_hash") == text_hash:
                    skipped += 1
                    if idx % 500 == 0:
                        _log.info(
                            "Parsed %d / %d — taper: %d, refs: %d (skipped so far: %d)",
                            idx, total, taper_found, refs_found, skipped,
                        )
                    continue

            lineage_row = _build_row(lb_number, description)

            if lineage_row["taper_name"]:
                taper_found += 1
            if lineage_row["source_chain"]:
                chain_found += 1
            lb_refs = json.loads(lineage_row["mentions_lb"])
            if lb_refs:
                refs_found += 1

            if dry_run:
                print(f"LB-{lb_number:05d} | confidence={lineage_row['parse_confidence']}"
                      f" | taper={lineage_row['taper_name']!r}"
                      f" | lb_refs={len(lb_refs)}")
            else:
                upsert_entry_lineage(lineage_row, db_path)

            parsed += 1

        except Exception as exc:
            _log.error("LB-%05d: error — %s", lb_number, exc)
            errors += 1

        if idx % 500 == 0:
            _log.info(
                "Parsed %d / %d — taper: %d, refs: %d",
                idx, total, taper_found, refs_found,
            )

    print(
        f"\nDone. Parsed: {parsed}  Skipped (unchanged): {skipped}  Errors: {errors}\n"
        f"\nTaper found: {taper_found} ({taper_found * 100 // max(parsed, 1)}%)"
        f"  Source chain found: {chain_found} ({chain_found * 100 // max(parsed, 1)}%)"
        f"  LB refs found: {refs_found} rows"
    )


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Batch-populate entry_lineage from entries.description"
    )
    ap.add_argument("--force", action="store_true",
                    help="Re-parse all rows even if source_text_hash is unchanged")
    ap.add_argument("--lb", type=int, metavar="N",
                    help="Parse only LB-N (for spot-checking)")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="Stop after N rows (for testing)")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="Parse but do not write to DB; print results to stdout")
    args = ap.parse_args(argv)
    run(
        force=args.force,
        lb_filter=args.lb,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
