#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
exec "$VENV" "$SCRIPT_DIR/mem_monitor.py" "$VENV" -m tapematch.cli "${@}"
