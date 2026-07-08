#!/usr/bin/env bash
# Session briefing — stdout is injected into Claude's context by the SessionStart hook.
# Keep output ~20 lines: it costs context in EVERY session. Must run fast (<1s), never fail.
cd /home/tjenkins/Documents/losslessbob || exit 0

echo "=== SESSION BRIEFING (auto-generated at session start — trust this, don't re-derive) ==="

FLAG_FILE="$PWD/.claude/state/session_end_stale.flag"
if [ -f "$FLAG_FILE" ]; then
    echo "[!] previous session ended with unrecorded changes — run /session-close first"
    rm -f "$FLAG_FILE" 2>/dev/null
fi

echo "[git] branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null) | uncommitted files: $(git status --porcelain 2>/dev/null | wc -l)"
echo "[git] last commit: $(git log -1 --oneline 2>/dev/null)"

echo "[changelog] latest entry:"
grep -m 3 -v '^[[:space:]]*$' CHANGELOG.md 2>/dev/null | cut -c1-120

echo "[todo] top of TODO.md:"
grep -m 3 '^TODO-' TODO.md 2>/dev/null | cut -c1-120

echo "[tapematch] CALIBRATION_PROGRESS.md tail:"
grep -v '^[[:space:]]*$' tools/tapematch/CALIBRATION_PROGRESS.md 2>/dev/null | tail -n 4 | cut -c1-120

echo "[specs] FABLE_* spec pack in instructions/ — read SPEC_INTEGRATION_NOTES.md before implementing any spec"
echo "=== END BRIEFING ==="
exit 0
