#!/usr/bin/env python3
"""Map TUIT spellings of known tapers into ``user_taper_aliases`` (dossier C10).

Mechanical mappings only — see ``backend.taper_curation.tuit_alias_candidates``.
Dry-run by default; ``--apply`` writes each row as an approved 'add' alias.

Usage:
    .venv/bin/python3 tools/map_tuit_taper_aliases.py [--apply] [--db PATH]
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
from backend.taper_curation import tuit_alias_candidates  # noqa: E402

_NOTE = "TUIT alias mapping (dossier C10)"
_log = logging.getLogger(__name__)


def run(apply: bool = False, db_path: str | None = None) -> dict[str, str]:
    """Propose (and with *apply*, write) TUIT alias rows.

    Args:
        apply: Write the rows; otherwise only report them.
        db_path: Optional database path override.

    Returns:
        ``{alias_norm: canonical}`` proposed (and written when *apply*).
    """
    db.reload_taper_aliases(db_path)
    candidates = tuit_alias_candidates(db.get_connection(db_path))
    for alias, canon in sorted(candidates.items()):
        _log.info("%s %r -> %r", "add" if apply else "would add", alias, canon)
        if apply:
            db.add_taper_alias(alias, canon, note=_NOTE, db_path=db_path)
    _log.info("%d alias row(s) %s", len(candidates), "written" if apply else "proposed")
    return candidates


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the alias rows")
    ap.add_argument("--db", default=None, help="DB path (default: backend.paths.DB_PATH)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(apply=args.apply, db_path=args.db)


if __name__ == "__main__":
    main()
