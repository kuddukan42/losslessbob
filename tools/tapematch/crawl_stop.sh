#!/usr/bin/env bash
# crawl_stop.sh — cleanly stop a detached crawl (equivalent of Ctrl+C).
#
# Sends SIGINT to the current tapematch_session.py; it exits 130 and
# run_crawl.sh stops looping. The interrupted date is re-picked on next start.
set -euo pipefail

if ! pgrep -f "tapematch_session.py" >/dev/null; then
    if pgrep -f "run_crawl.sh" >/dev/null; then
        pkill -INT -f "run_crawl.sh"
        echo "Stopped run_crawl.sh (was between dates)."
    else
        echo "No crawl running."
    fi
    exit 0
fi

pkill -INT -f "tapematch_session.py"
echo "Sent SIGINT to the running session — it will stop after cleanup."
echo "Resume later with crawl_start.sh (the queue is resumable)."
