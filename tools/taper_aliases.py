#!/usr/bin/env python3
"""CLI conduit to add/remove known-taper handles without a code edit (TODO-241).

Wraps ``backend.db.{list,add,remove}_taper_alias`` and
``backend.db.reload_taper_aliases`` directly — the same functions the
``/api/tapers/aliases`` HTTP routes call — so curators can manage the
``user_taper_aliases`` overrides on top of the builtin
``backend.db._BUILTIN_TAPER_ALIASES`` table from a terminal.

Usage:
    python tools/taper_aliases.py list
    python tools/taper_aliases.py add <alias> <canonical> [--note NOTE] [--recompute]
    python tools/taper_aliases.py remove <alias> [--recompute]

``--recompute`` on add/remove runs a full ``taper_attribution.recompute()``
afterward, so existing entries are re-scored against the new/removed alias
immediately instead of waiting for the next ``/api/derived/recompute`` call.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend import db  # noqa: E402
from backend import taper_attribution  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger(__name__)


def _maybe_recompute(do_recompute: bool, db_path: str | None) -> None:
    """Rebuild taper_attribution's alias index and, if requested, recompute.

    Args:
        do_recompute: If True, run a full ``taper_attribution.recompute()``.
        db_path: Optional database path override.
    """
    taper_attribution._rebuild_alias_index()
    if do_recompute:
        _log.info("Recomputing taper_attributions...")
        stats = taper_attribution.recompute(db_path=db_path)
        print(
            f"Recompute done. Total: {stats['total']}  Confirmed: {stats['confirmed']}"
            f"  Propagated: {stats['propagated']}  Inferred: {stats['inferred']}"
            f"  Conflicts: {stats['conflict']}"
        )


def cmd_list(args: argparse.Namespace) -> None:
    """List the merged known-taper alias table (builtin + user overrides)."""
    data = db.list_taper_aliases(db_path=args.db_path)
    counts = data["counts"]
    print(
        f"{counts['merged']} aliases total "
        f"(builtin={counts['builtin']}, user_add={counts['user_add']}, "
        f"user_remove={counts['user_remove']})\n"
    )
    for entry in data["entries"]:
        print(f"  {entry['alias']:<28} -> {entry['canonical']:<24} [{entry['origin']}]")
    if data["suppressed"]:
        print("\nSuppressed builtin keys: " + ", ".join(data["suppressed"]))


def cmd_add(args: argparse.Namespace) -> None:
    """Add or override one known-taper alias."""
    row = db.add_taper_alias(args.alias, args.canonical, note=args.note, db_path=args.db_path)
    print(f"Added: {row['alias_norm']!r} -> {row['canonical']!r}")
    _maybe_recompute(args.recompute, args.db_path)


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a user alias, or suppress a builtin one."""
    try:
        result = db.remove_taper_alias(args.alias, db_path=args.db_path)
    except KeyError:
        _log.error("%r is not a known alias (neither a user row nor a builtin key)", args.alias)
        sys.exit(1)
    print(f"{args.alias!r}: {result}")
    _maybe_recompute(args.recompute, args.db_path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Add/remove known-taper handles without a code edit (TODO-241)"
    )
    ap.add_argument("--db-path", dest="db_path", default=None,
                     help="Optional database path override")
    sub = ap.add_subparsers(dest="command", required=True)

    sp_list = sub.add_parser("list", help="List the merged alias table")
    sp_list.set_defaults(func=cmd_list)

    sp_add = sub.add_parser("add", help="Add or override one alias")
    sp_add.add_argument("alias", help="Raw or normalised alias handle")
    sp_add.add_argument("canonical", help="Canonical taper name")
    sp_add.add_argument("--note", default=None, help="Optional provenance note")
    sp_add.add_argument("--recompute", action="store_true",
                         help="Run taper_attribution.recompute() afterward")
    sp_add.set_defaults(func=cmd_add)

    sp_remove = sub.add_parser("remove", help="Remove a user alias / suppress a builtin one")
    sp_remove.add_argument("alias", help="Raw or normalised alias handle")
    sp_remove.add_argument("--recompute", action="store_true",
                            help="Run taper_attribution.recompute() afterward")
    sp_remove.set_defaults(func=cmd_remove)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
