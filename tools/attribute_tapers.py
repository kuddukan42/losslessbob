#!/usr/bin/env python3
"""Recompute taper_attributions from entry_lineage / recording_families /
taper_confirmations (Phase 1: schema + Layer 0 direct extraction + Layer 1
same-source propagation).

Usage:
    python tools/attribute_tapers.py [--dry-run] [--skip-lineage-refresh]
    python tools/attribute_tapers.py --calibrate-fingerprints

Options:
    --dry-run               Recompute but do not write to the DB; print the
                             summary only.
    --skip-lineage-refresh  Skip the entry_lineage freshness pass. Use only
                             when lineage is already known current (e.g.
                             repeated test runs); normal usage always refreshes.
    --calibrate-fingerprints
                             Evaluate Layer-2 fingerprint score thresholds
                             against a deterministic holdout of confirmed-tier
                             entries (see backend.taper_fingerprints.calibrate)
                             and print a precision/coverage table. Read-only —
                             does not write taper_attributions.

Per instructions/SPEC_INTEGRATION_NOTES.md finding F5, this CLI always
refreshes entry_lineage first via tools/parse_lineage.py's run() — it is
hash-guarded incremental, so repeat runs are cheap — before recomputing
attributions, so Layer 1 propagation never runs on stale lineage data. See
instructions/complete/FABLE_TAPER_ATTRIBUTION.md for the design and
backend/taper_attribution.py for the recompute logic.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import taper_fingerprints  # noqa: E402
from backend.db import get_connection, init_db  # noqa: E402
from backend.taper_attribution import _compute_layers01, recompute  # noqa: E402
from tools import parse_lineage  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger(__name__)


def run(
    dry_run: bool = False,
    skip_lineage_refresh: bool = False,
    db_path: str | None = None,
) -> dict:
    """Refresh entry_lineage (F5), then recompute taper_attributions wholesale.

    Args:
        dry_run: Recompute but do not write to the DB.
        skip_lineage_refresh: Skip the parse_lineage.run() freshness pass.
        db_path: Optional database path override.

    Returns:
        Summary stats dict from backend.taper_attribution.recompute().
    """
    if not skip_lineage_refresh:
        _log.info("Refreshing entry_lineage (parse_lineage, incremental)...")
        parse_lineage.run(db_path=db_path)

    _log.info("Recomputing taper_attributions (Layer 0 + Layer 1)...")
    stats = recompute(db_path=db_path, dry_run=dry_run)

    top_tapers = ", ".join(f"{t}={n}" for t, n in stats["top_tapers"]) or "(none)"
    print(
        f"\nDone. Total attributions: {stats['total']}"
        f"  Confirmed: {stats['confirmed']}  Propagated: {stats['propagated']}"
        f"  Inferred: {stats['inferred']}  Conflicts: {stats['conflict']}\n"
        f"\nTop tapers by entry count: {top_tapers}"
    )
    return stats


def run_calibrate_fingerprints(db_path: str | None = None) -> dict:
    """Evaluate Layer-2 fingerprint gate values against a K-fold holdout; read-only.

    Loads the same Layer 0 + Layer 1 inputs :func:`recompute` uses (via
    ``backend.taper_attribution._compute_layers01``) without writing anything,
    then delegates to ``backend.taper_fingerprints.calibrate`` and prints one
    line per candidate (score, margin) gate pair — raw precision/coverage plus
    the reliable-taper-restricted numbers production actually writes — and the
    reliable-taper set at the shipped gates.

    Args:
        db_path: Optional database path override.

    Returns:
        The calibration result dict (see backend.taper_fingerprints.calibrate).
    """
    init_db(db_path)
    conn = get_connection(db_path)
    attrs, fam_members, same_as_adj, derived_from_adj, _rejects, unresolved = (
        _compute_layers01(conn))
    result = taper_fingerprints.calibrate(
        conn, attrs, fam_members, same_as_adj, derived_from_adj, unresolved
    )

    print(f"\nholdout docs: {result['holdout']}")
    print(f"{'score>=':>8} {'margin>=':>9} {'assigned':>9} {'prec':>6} {'cov':>6}"
          f" | {'rel-assigned':>12} {'rel-prec':>8} {'rel-cov':>7} {'tapers':>6}")
    for r in result["rows"]:
        print(
            f"{r['score_gate']:>8} {r['margin_gate']:>9} {r['assigned']:>9} "
            f"{r['precision']:>6.3f} {r['coverage']:>6.3f} | "
            f"{r['reliable_assigned']:>12} {r['reliable_precision']:>8.3f} "
            f"{r['reliable_coverage']:>7.3f} {r['reliable_tapers']:>6}"
        )
    print("\nreliable tapers at shipped gates "
          f"({taper_fingerprints.INFERRED_SCORE_THRESHOLD:g}/"
          f"{taper_fingerprints.INFERRED_MARGIN_THRESHOLD:g}):")
    for taper, (assigned, correct) in result["reliable_tapers"].items():
        print(f"  {taper}: {correct}/{assigned} = {correct / assigned:.3f}")
    return result


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Recompute taper_attributions from entry_lineage / recording_families"
    )
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="Recompute but do not write to DB; print summary only")
    ap.add_argument("--skip-lineage-refresh", dest="skip_lineage_refresh", action="store_true",
                    help="Skip the entry_lineage freshness pass")
    ap.add_argument("--calibrate-fingerprints", dest="calibrate_fingerprints",
                    action="store_true",
                    help="Evaluate Layer-2 fingerprint thresholds on a holdout; no DB write")
    args = ap.parse_args(argv)
    if args.calibrate_fingerprints:
        run_calibrate_fingerprints()
        return
    run(dry_run=args.dry_run, skip_lineage_refresh=args.skip_lineage_refresh)


if __name__ == "__main__":
    main()
