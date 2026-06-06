#!/usr/bin/env bash
# run.sh DIR [--date YYYY-MM-DD] [--label LABEL] [--set-offset HH:MM:SS]
# Run a full tapematch session on an arbitrary folder (no DB lookup or copying).
# Equivalent to run_year.sh steps 5-8: tapematch, archive, observations.db, report.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/../../.venv/bin/python3"
exec "$VENV" "$SCRIPT_DIR/tapematch_session.py" --manual-dir "${@}"
