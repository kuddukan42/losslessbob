#!/usr/bin/env python3
"""PreToolUse guard: block file access outside the project directory.

Covers two matchers:
  - Read|Write|Edit|NotebookEdit: denies any file_path/notebook_path that
    resolves outside the project root (Claude's memory dir ~/.claude is the
    only exception).
  - Bash: denies commands that reference temp locations outside the project
    (/tmp, /var/tmp, /dev/shm, mktemp, $TMPDIR) so shell redirects and
    downloads can't bypass the file-tool guard.

Fail-closed: any unexpected error denies the call rather than letting it
through. Temp files belong in <project>/.scratch/ (gitignored).
"""
import json
import os
import re
import sys

PROJECT = os.path.realpath("/home/tjenkins/Documents/losslessbob")
ALLOWED_ROOTS = (PROJECT, os.path.realpath(os.path.expanduser("~/.claude")))
BASH_DENY = re.compile(r"/tmp(/|\s|['\"]|$)|/var/tmp|/dev/shm|\bmktemp\b|\$\{?TMPDIR")


def deny(reason: str) -> None:
    """Emit a PreToolUse deny decision and exit."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main() -> None:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if tool == "Bash":
        cmd = tool_input.get("command", "") or ""
        if BASH_DENY.search(cmd):
            deny("Blocked by path_guard: command references a temp location "
                 "outside the project (/tmp, /var/tmp, /dev/shm, mktemp, "
                 "$TMPDIR). All temp/scratch files must go in "
                 f"{PROJECT}/.scratch/ instead.")
        return

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return
    resolved = os.path.realpath(file_path)
    for root in ALLOWED_ROOTS:
        if resolved == root or resolved.startswith(root + os.sep):
            return
    deny(f"Blocked by path_guard: {file_path} is outside the project "
         f"directory. Stay under {PROJECT} (temp files: .scratch/).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail-closed by design
        deny(f"path_guard internal error (fail-closed): {exc}")
