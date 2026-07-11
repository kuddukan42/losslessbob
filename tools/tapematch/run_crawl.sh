#!/usr/bin/env bash
# run_crawl.sh [--min-entries N] [--dry-run] [--allow-missing]
#
# Process all unprocessed concert dates, one at a time, restarting Python
# between each run so memory is fully released between dates.
# Resumable: Ctrl+C cleanly stops; re-run the same command to continue.
#
# TODO-227: guards against hot crash-looping on a single poison date. Any
# exit code other than 0/2/3 (success/skip-continue), 75 (queue empty), or
# 130 (Ctrl+C) is treated as a failure: sleep 30s, then track consecutive
# failures. 3 consecutive failures on the SAME date -> that date is appended
# to crawl_skip.txt (tapematch_session.py's --next honors this) and the
# same-date counter resets, so the crawl skips past the poison date on the
# next iteration. 10 consecutive failures overall (regardless of date)
# indicates a systemic problem -> abort with nonzero exit. A success or
# skip rc resets both counters.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
SCRIPT="$SCRIPT_DIR/tapematch_session.py"
DATA_DIR="$SCRIPT_DIR/../../data/tapematch"
LAST_ATTEMPT_FILE="$DATA_DIR/crawl_last_attempt.txt"
SKIP_FILE="$DATA_DIR/crawl_skip.txt"

RC_QUEUE_EMPTY=75

FAIL_SLEEP_SEC=30
MAX_SAME_DATE_FAILS=3
MAX_TOTAL_FAILS=10

same_date=""
same_date_fails=0
total_fails=0

while true; do
    rc=0
    "$VENV" "$SCRIPT" --next "${@}" || rc=$?

    if [ "$rc" -eq "$RC_QUEUE_EMPTY" ]; then
        echo "=== Crawl complete ==="
        exit 0
    fi

    if [ "$rc" -eq 130 ]; then
        # Ctrl+C propagated from child
        exit 130
    fi

    if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ] || [ "$rc" -eq 3 ]; then
        # success / skip: continue immediately, reset failure tracking
        same_date=""
        same_date_fails=0
        total_fails=0
        continue
    fi

    # Any other rc: unhandled failure. Slow down and track it.
    echo "=== run_crawl: rc=$rc — sleeping ${FAIL_SLEEP_SEC}s before retry ==="
    sleep "$FAIL_SLEEP_SEC"

    attempted_date=""
    if [ -f "$LAST_ATTEMPT_FILE" ]; then
        attempted_date="$(cat "$LAST_ATTEMPT_FILE" 2>/dev/null || true)"
    fi

    total_fails=$((total_fails + 1))

    if [ -n "$attempted_date" ] && [ "$attempted_date" = "$same_date" ]; then
        same_date_fails=$((same_date_fails + 1))
    else
        same_date="$attempted_date"
        same_date_fails=1
    fi

    if [ "$same_date_fails" -ge "$MAX_SAME_DATE_FAILS" ] && [ -n "$attempted_date" ]; then
        echo "=== run_crawl: ${attempted_date} failed ${same_date_fails} times consecutively — adding to ${SKIP_FILE} ==="
        mkdir -p "$DATA_DIR"
        echo "$attempted_date" >> "$SKIP_FILE"
        same_date=""
        same_date_fails=0
    fi

    if [ "$total_fails" -ge "$MAX_TOTAL_FAILS" ]; then
        echo "=== run_crawl: ${total_fails} consecutive failures overall — aborting (systemic problem) ===" >&2
        exit 1
    fi
done
