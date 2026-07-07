#!/usr/bin/env python3
"""make_regression_set_v2.py — flip 3 label-error pairs from negatives to positives.

Reads the frozen ``regression_set.json`` (never modified in place — see repo
rules) and writes ``regression_set_v2.json`` with exactly 3 pairs moved from
``negatives`` to ``positives``. These 3 pairs are objective curator label
errors surfaced by the Tier B embedding evaluation
(``tools/tapematch/TIER_B_EMBED_REPORT.md``, "Same-show collision analysis"):
each has waveform envelope correlation 0.926-0.950 (same-show TN pairs
normally cap at ~0.605 genuine collision), the tapematch pipeline already
verdicts them ``same_family``, and they were flagged ``pairs.label_suspect=1``
by ``audit_fn.py``'s heuristics — i.e. they are same recording mislabeled as
different, not merely hard negatives.

Usage:
    .venv/bin/python3 tools/tapematch/make_regression_set_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
FROZEN_PATH = _HERE / "regression_set.json"
OUTPUT_PATH = _HERE / "regression_set_v2.json"

# (lb_a, lb_b, date) — order-independent on the LB pair. Evidence: waveform
# envelope corr 0.926-0.950, pipeline verdict same_family (4/4), and
# pairs.label_suspect=1 (TIER_B_EMBED_REPORT.md "Same-show collision
# analysis" / FN_AUDIT_REPORT.md label-noise audit).
FLIPS = (
    (4642, 9900, "1988-08-26"),
    (6825, 9180, "1991-07-20"),
    (3431, 3455, "1994-10-28"),
)

V2_NOTE = (
    "3 negatives flipped to positives — objective curator label errors, not "
    "judgment calls. Evidence (TIER_B_EMBED_REPORT.md, \"Same-show collision "
    "analysis\"): each pair has waveform envelope correlation 0.926-0.950 "
    "(genuine same-show different-source collisions cap at ~0.605 in the "
    "same eval), the tapematch pipeline already places both LBs in the same "
    "family (4/4 same_family verdict), and each pair carries "
    "pairs.label_suspect=1 (flagged by audit_fn.py's label-noise heuristics). "
    "Flipped pairs: LB-04642/LB-09900 (1988-08-26, corr~0.950), "
    "LB-06825/LB-09180 (1991-07-20), LB-03431/LB-03455 (1994-10-28)."
)


def _key(a: int, b: int, date: str) -> tuple[frozenset[int], str]:
    """Order-independent identity for a labeled pair."""
    return frozenset((a, b)), date


def main(argv: list[str] | None = None) -> int:
    if not FROZEN_PATH.exists():
        sys.exit(f"error: {FROZEN_PATH} not found.")
    frozen = json.loads(FROZEN_PATH.read_text())

    negatives = list(frozen["negatives"])
    positives = list(frozen["positives"])

    neg_index: dict[tuple[frozenset[int], str], int] = {
        _key(a, b, date): i for i, (a, b, date) in enumerate(negatives)
    }

    moved_indices: list[int] = []
    for a, b, date in FLIPS:
        key = _key(a, b, date)
        if key not in neg_index:
            sys.exit(
                f"error: flip pair LB-{a:05d}/LB-{b:05d} ({date}) not found in "
                f"negatives — regression_set.json may have changed."
            )
        moved_indices.append(neg_index[key])

    moved_entries = [negatives[i] for i in moved_indices]
    remaining_negatives = [
        entry for i, entry in enumerate(negatives) if i not in set(moved_indices)
    ]
    new_positives = positives + moved_entries

    payload = dict(frozen)
    payload["positives"] = new_positives
    payload["negatives"] = remaining_negatives
    payload["v2_note"] = V2_NOTE

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"moved {len(moved_entries)} pair(s) from negatives to positives -> "
          f"{OUTPUT_PATH.name}")
    for a, b, date in moved_entries:
        print(f"  LB-{a:05d} / LB-{b:05d}  {date}")
    print(f"positives: {len(positives)} -> {len(new_positives)}")
    print(f"negatives: {len(negatives)} -> {len(remaining_negatives)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
