#!/usr/bin/env bash
# run_date.sh YYYY-MM-DD [--dry-run] [--no-tapematch] [--report-only] [--set-offset HH:MM:SS]
# Run a full tapematch session for a single concert date.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
exec "$VENV" "$SCRIPT_DIR/tapematch_session.py" "${@}"
