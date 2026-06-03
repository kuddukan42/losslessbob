#!/usr/bin/env bash
# run_year.sh YYYY [--min-entries N] [--dry-run]
# Process all tapematch candidate dates for a year, skipping already-done ones.
# Resumable: Ctrl+C cleanly stops; re-run the same command to continue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
exec "$VENV" "$SCRIPT_DIR/tapematch_session.py" --year "${@}"
