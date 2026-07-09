#!/usr/bin/env bash
# crawl_start.sh [--min-entries N] [--allow-missing]
#
# Launch run_crawl.sh detached (survives terminal close). Single instance:
# refuses to start if a crawl or live session is already running.
# Log: data/tapematch/crawl.log. Stop with crawl_stop.sh, check with crawl_status.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/../../data/tapematch"
LOG="$LOG_DIR/crawl.log"

if pgrep -f "run_crawl.sh" >/dev/null || pgrep -f "tapematch_session.py" >/dev/null; then
    echo "A tapematch crawl or session is already running — not starting a second one."
    echo "Check: $SCRIPT_DIR/crawl_status.sh"
    exit 1
fi

mkdir -p "$LOG_DIR"
echo "=== crawl started $(date '+%Y-%m-%d %H:%M:%S') (args: ${*:-none}) ===" >> "$LOG"
nohup "$SCRIPT_DIR/run_crawl.sh" "$@" >> "$LOG" 2>&1 &
disown
echo "Crawl started (pid $!). Follow with: tail -f $LOG"
