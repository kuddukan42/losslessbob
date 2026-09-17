#!/usr/bin/env bash
# Walk the WTRF board newest-first and seed every post the collection holds.
# The walk ends at the board's last page; --limit only caps attempts per run.
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/python3 tools/wtrf_seed_board.py --limit 5000 --delay 10 --verbose "$@"
