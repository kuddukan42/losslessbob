#!/usr/bin/env bash
# SessionEnd hook, advisory only: fires on /clear or exit. Runs the same
# staleness check as changelog_check.sh — if there are uncommitted changes
# under backend/, gui_next/src/, gui/, or tools/ but CHANGELOG.md's first
# dated entry isn't today's date, drops a flag file. session_brief.sh
# surfaces that flag (and clears it) at the next SessionStart.
# Always exits 0 — SessionEnd hooks can't block anyway.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/home/tjenkins/Documents/losslessbob}"
CHANGELOG="$PROJECT_DIR/CHANGELOG.md"
FLAG_FILE="$PROJECT_DIR/.claude/state/session_end_stale.flag"

status="$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null)"
[ -z "$status" ] && exit 0

relevant="$(printf '%s\n' "$status" | grep -E ' (backend/|gui_next/src/|gui/|tools/)' )"
[ -z "$relevant" ] && exit 0

[ -f "$CHANGELOG" ] || exit 0

today="$(date +%F)"
first_dated_line="$(grep -m1 -E '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$CHANGELOG")"

case "$first_dated_line" in
    *"$today"*)
        exit 0
        ;;
esac

mkdir -p "$PROJECT_DIR/.claude/state" 2>/dev/null
date -Iseconds > "$FLAG_FILE" 2>/dev/null

exit 0
