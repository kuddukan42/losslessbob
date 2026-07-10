#!/usr/bin/env python3
"""make_regression_set_v3.py — apply the TODO-201 curator-approved label flips.

Reads ``regression_set_v2.json`` (never modified in place — see repo rules)
and writes ``regression_set_v3.json`` with the 83 pairs tj signed off on
2026-07-09 moved from ``positives`` to ``negatives``. The flips are the
``FLIP`` rows of ``FN_LABEL_REVIEW.md`` batches 1–2 (TODO-201): census-flagged
frozen-set positives whose curator/info text explicitly asserts, pair-scoped,
that the two LBs are different recordings. Parsed from the review ledger
rather than hardcoded so the ledger stays the single source of truth; the
count is pinned to exactly 83 so a later batch-3 edit to the ledger cannot
silently change this version's output (batch 3 gets a v4).

Usage:
    .venv/bin/python3 tools/tapematch/make_regression_set_v3.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
V2_PATH = _HERE / "regression_set_v2.json"
REVIEW_PATH = _HERE / "FN_LABEL_REVIEW.md"
OUTPUT_PATH = _HERE / "regression_set_v3.json"

EXPECTED_FLIPS = 83

_FLIP_ROW_RE = re.compile(
    r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*LB-(\d+)\s*/\s*LB-(\d+)\s*\|\s*FLIP\s*\|"
)

V3_NOTE = (
    "83 positives flipped to negatives — TODO-201 curator label-error review, "
    "batches 1+2 (FN_LABEL_REVIEW.md), approved by tj 2026-07-09. Each pair's "
    "curator/info text explicitly asserts, pair-scoped, that the two LBs are "
    "different recordings (batch 1: overlap tier 17 flips; batch 2: "
    "explicit-only tier 66 flips). KEEP/UNSURE rows and the 136 duration-only "
    "pairs are untouched. Applied on top of regression_set_v2.json (which had "
    "flipped 3 negatives to positives); the full flipped-pair list is in "
    "v3_flips."
)


def _key(a: int, b: int, date: str) -> tuple[frozenset[int], str]:
    """Order-independent identity for a labeled pair."""
    return frozenset((a, b)), date


def load_flips() -> list[tuple[str, int, int]]:
    """Parse the FLIP rows out of FN_LABEL_REVIEW.md's decision tables.

    Returns:
        List of ``(date, lb_a, lb_b)`` tuples, one per FLIP row.
    """
    flips: list[tuple[str, int, int]] = []
    for line in REVIEW_PATH.read_text().splitlines():
        m = _FLIP_ROW_RE.match(line)
        if m:
            flips.append((m.group(1), int(m.group(2)), int(m.group(3))))
    return flips


def main(argv: list[str] | None = None) -> int:
    """Write regression_set_v3.json; exits non-zero on any inconsistency."""
    for path in (V2_PATH, REVIEW_PATH):
        if not path.exists():
            sys.exit(f"error: {path} not found.")

    flips = load_flips()
    if len(flips) != EXPECTED_FLIPS:
        sys.exit(
            f"error: parsed {len(flips)} FLIP rows from {REVIEW_PATH.name}, "
            f"expected exactly {EXPECTED_FLIPS} (batches 1+2 as signed off). "
            "A later review batch belongs in a v4, not here."
        )
    if len({_key(a, b, d) for d, a, b in flips}) != len(flips):
        sys.exit("error: duplicate FLIP rows in the review ledger.")

    frozen = json.loads(V2_PATH.read_text())
    positives = list(frozen["positives"])
    negatives = list(frozen["negatives"])

    pos_index: dict[tuple[frozenset[int], str], int] = {
        _key(a, b, date): i for i, (a, b, date) in enumerate(positives)
    }

    moved_indices: list[int] = []
    for date, a, b in flips:
        key = _key(a, b, date)
        if key not in pos_index:
            sys.exit(
                f"error: flip pair LB-{a:05d}/LB-{b:05d} ({date}) not found in "
                f"positives — {V2_PATH.name} may have changed."
            )
        moved_indices.append(pos_index[key])

    moved_set = set(moved_indices)
    moved_entries = [positives[i] for i in sorted(moved_set)]
    remaining_positives = [
        entry for i, entry in enumerate(positives) if i not in moved_set
    ]
    new_negatives = negatives + moved_entries

    payload = dict(frozen)
    payload["positives"] = remaining_positives
    payload["negatives"] = new_negatives
    payload["v3_note"] = V3_NOTE
    payload["v3_flips"] = moved_entries

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"moved {len(moved_entries)} pair(s) from positives to negatives -> "
          f"{OUTPUT_PATH.name}")
    print(f"positives: {len(positives)} -> {len(remaining_positives)}")
    print(f"negatives: {len(negatives)} -> {len(new_negatives)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
