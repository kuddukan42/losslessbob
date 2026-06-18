#!/usr/bin/env bash
# run_crawl.sh [--min-entries N] [--dry-run] [--allow-missing]
#
# Process all unprocessed concert dates, one at a time, restarting Python
# between each run so memory is fully released between dates.
# Resumable: Ctrl+C cleanly stops; re-run the same command to continue.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
SCRIPT="$SCRIPT_DIR/tapematch_session.py"

RC_QUEUE_EMPTY=75

while true; do
    "$VENV" "$SCRIPT" --next "${@}" || rc=$?
    rc=${rc:-0}

    if [ "$rc" -eq "$RC_QUEUE_EMPTY" ]; then
        echo "=== Crawl complete ==="
        exit 0
    fi

    if [ "$rc" -eq 130 ]; then
        # Ctrl+C propagated from child
        exit 130
    fi

    # rc 0 (success), 2 (skip: 1 source), 3 (skip: missing) — all continue
done
