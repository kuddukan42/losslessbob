#!/usr/bin/env bash
# PostToolUse (Edit|Write) advisory hook: py_compile check on edited/written .py files.
# Exit 2 + stderr on compile failure feeds the error back to the model as advisory
# feedback (does not block/undo the edit). Exit 0 otherwise.

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

[ -z "$file" ] && exit 0
[ "${file##*.}" != "py" ] && exit 0
[ -f "$file" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/home/tjenkins/Documents/losslessbob}"
PY="$PROJECT_DIR/.venv/bin/python3"

[ -x "$PY" ] || exit 0

if ! err="$("$PY" -m py_compile "$file" 2>&1)"; then
    echo "py_compile failed for $file:" >&2
    echo "$err" >&2
    exit 2
fi

exit 0
