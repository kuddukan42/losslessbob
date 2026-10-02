"""Remove the records test runs wrote into data/lb_nc_undo.jsonl (throwaway).

Dry-run by default; --apply backs the journal up to data/backups/ and rewrites it.
A record is junk when it names a pytest tmp folder, or is an "undone" record that
retires one of those.

    .venv/bin/python3 tools/_strip_undo_junk.py            # what would go
    .venv/bin/python3 tools/_strip_undo_junk.py --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JOURNAL = REPO / "data" / "lb_nc_undo.jsonl"
BACKUPS = REPO / "data" / "backups"
MARK = "pytest-of-"

log = logging.getLogger("strip_undo_junk")


def main() -> int:
    """Count (and with --apply remove) the junk records."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="back up and rewrite the journal")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    raw = JOURNAL.read_text(encoding="utf-8")
    size = JOURNAL.stat().st_size
    recs = [(line, json.loads(line)) for line in raw.splitlines() if line.strip()]
    junk = {r["id"] for line, r in recs if MARK in line}
    keep = [line for line, r in recs if r["id"] not in junk
            and not (r.get("kind") == "undone" and r.get("undoes") in junk)]
    log.info("records %d | junk %d | kept %d", len(recs), len(recs) - len(keep), len(keep))
    if not args.apply:
        log.info("dry run — nothing written; --apply rewrites the journal")
        return 0

    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"lb_nc_undo_preStrip_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    shutil.copy2(JOURNAL, backup)
    tmp = JOURNAL.with_name(JOURNAL.name + ".tmp")
    tmp.write_text("".join(line + "\n" for line in keep), encoding="utf-8")
    if JOURNAL.stat().st_size != size:              # lb-nc appended meanwhile
        tmp.unlink()
        log.error("journal changed while stripping — nothing replaced, run it again")
        return 1
    os.replace(tmp, JOURNAL)
    log.info("backup %s | journal rewritten", backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
