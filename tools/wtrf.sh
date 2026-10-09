#!/usr/bin/env bash
# Walk the WTRF board newest-first and seed every post the collection holds,
# stopping once it catches up with earlier runs.
#
#   tools/wtrf.sh                         # newest posts until a page of known ones
#   tools/wtrf.sh --stop-after-seen 60    # tolerate more bumped old topics first
#   tools/wtrf.sh --pages 2 --dry-run     # bounded: just the newest two pages
#   tools/wtrf.sh --full                  # whole board, up to 5000 attempts
#
# --limit makes wtrf_seed_board.py ignore --pages, so the default limit is only
# added when the caller did not bound the walk by pages themselves. The
# catch-up stop is likewise dropped when the caller sets their own bound.
cd "$(dirname "$0")/.." || exit 1

limit=(--limit 5000)
catchup=(--stop-after-seen 20)     # one full page of already-attempted topics
args=()
for arg in "$@"; do
    case "$arg" in
        --full) catchup=(); continue ;;
        --pages|--pages=*|--limit|--limit=*) limit=(); catchup=() ;;
        --stop-after-seen|--stop-after-seen=*|--resume|--rescan) catchup=() ;;
    esac
    args+=("$arg")
done

exec .venv/bin/python3 tools/wtrf_seed_board.py "${limit[@]}" "${catchup[@]}" \
    --delay 10 --verbose "${args[@]}"
