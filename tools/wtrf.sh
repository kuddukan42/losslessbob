#!/usr/bin/env bash
# Walk the WTRF board newest-first and seed every post the collection holds.
#
#   tools/wtrf.sh                       # whole board, up to 5000 attempts
#   tools/wtrf.sh --pages 2 --dry-run   # bounded: just the newest two pages
#
# --limit makes wtrf_seed_board.py ignore --pages, so the default limit is only
# added when the caller did not bound the walk by pages themselves.
cd "$(dirname "$0")/.." || exit 1

limit=(--limit 5000)
for arg in "$@"; do
    case "$arg" in
        --pages|--pages=*|--limit|--limit=*) limit=() ;;
    esac
done

exec .venv/bin/python3 tools/wtrf_seed_board.py "${limit[@]}" --delay 10 --verbose "$@"
