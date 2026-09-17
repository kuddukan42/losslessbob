#!/usr/bin/env bash
# Nightly TUIT sync: newest two listing pages, seed what the collection holds.
# Partial overlays are the default; pass --no-allow-partial-overlay to refuse.
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/python3 tools/tuit_sync.py --pages 2 --fetch-torrents --seed --overlay "$@"
