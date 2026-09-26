#!/usr/bin/env bash
# Resume the WTRF seed walk where the last run stopped, logging to data/logs/.
#
#   tools/wtrf_resume.sh              # probe for the frontier, walk to the end
#   tools/wtrf_resume.sh --dry-run    # same, but download and seed nothing
#
# Extra arguments pass through to tools/wtrf.sh (and on to wtrf_seed_board.py).
cd "$(dirname "$0")/.." || exit 1
log="data/logs/wtrf_seed_$(date +%Y%m%d_%H%M%S).log"
echo "logging to $log"
tools/wtrf.sh --resume "$@" 2>&1 | tee "$log"
