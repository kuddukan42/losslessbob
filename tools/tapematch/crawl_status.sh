#!/usr/bin/env bash
# crawl_status.sh — one-glance crawl status: running?, current date, progress, log tail.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNS_DIR="$SCRIPT_DIR/../../data/tapematch/runs"
LOG="$SCRIPT_DIR/../../data/tapematch/crawl.log"

if pgrep -f "run_crawl.sh" >/dev/null; then
    echo "RUNNING (pid $(pgrep -of 'run_crawl.sh'))"
else
    echo "NOT RUNNING"
fi

if [ -d "$RUNS_DIR" ]; then
    total=$(find "$RUNS_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    dates=$(ls "$RUNS_DIR" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort -u | wc -l)
    echo "runs on disk: $total ($dates distinct dates)"
fi

if [ -f "$LOG" ]; then
    echo "--- last log lines ($LOG) ---"
    tail -n 5 "$LOG"
fi
