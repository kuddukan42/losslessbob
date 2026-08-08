#!/usr/bin/env bash
# Send one or more folders to the LosslessBob Pipeline screen.
#
# Invoked by the Nemo right-click action (losslessbob-pipeline.nemo_action) with
# every selected folder as a separate argument. Writes the paths to the app's
# pipeline inbox; the running app picks them up within ~150ms and navigates to
# Pipeline. If the app is not running it is launched, and it drains the inbox at
# startup.
#
# Launcher resolution: $LB_LAUNCH_CMD > `losslessbob` on PATH > `npm run dev` in
# gui_next > newest AppImage in gui_next/dist. The AppImage is last on purpose —
# gui_next/dist can hold a months-old build, and silently starting that instead of
# the working tree is worse than not starting anything.

set -euo pipefail

STATE_DIR="${HOME}/.local/share/losslessbob"
INBOX="${STATE_DIR}/pipeline-inbox"
GUI_PID_FILE="${STATE_DIR}/gui.pid"
REPO="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"

notify() {
  command -v notify-send >/dev/null 2>&1 && notify-send -a LosslessBob "$@" || true
}

# ── Collect the selected folders ──────────────────────────────────────────────
folders=()
for arg in "$@"; do
  [ -d "$arg" ] || continue
  folders+=("$(readlink -f "$arg")")
done

if [ ${#folders[@]} -eq 0 ]; then
  notify "Nothing to send" "Select one or more folders."
  exit 1
fi

# ── Drop them in the inbox ────────────────────────────────────────────────────
mkdir -p "$INBOX"
drop="${INBOX}/$(date +%s%N)-$$.txt"
# Write to a temp name first, then rename: the app watches this directory and
# must never read a half-written list.
printf '%s\n' "${folders[@]}" > "${drop}.part"
mv "${drop}.part" "$drop"

# ── Launch the app if it isn't running ────────────────────────────────────────
gui_alive() {
  local pid
  [ -r "$GUI_PID_FILE" ] || return 1
  pid="$(cat "$GUI_PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

if gui_alive; then
  notify "Sent to pipeline" "${#folders[@]} folder(s) queued."
  exit 0
fi

launch() {
  if [ -n "${LB_LAUNCH_CMD:-}" ]; then
    setsid nohup bash -c "$LB_LAUNCH_CMD" >/dev/null 2>&1 &
    return 0
  fi
  if command -v losslessbob >/dev/null 2>&1; then
    setsid nohup losslessbob >/dev/null 2>&1 &
    return 0
  fi
  if [ -d "$REPO/gui_next/node_modules" ]; then
    setsid nohup npm --prefix "$REPO/gui_next" run dev >/dev/null 2>&1 &
    return 0
  fi
  local appimage
  appimage="$(ls -t "$REPO"/gui_next/dist/*.AppImage 2>/dev/null | head -n1 || true)"
  if [ -n "$appimage" ] && [ -x "$appimage" ]; then
    setsid nohup "$appimage" >/dev/null 2>&1 &
    return 0
  fi
  return 1
}

if launch; then
  notify "Starting LosslessBob" "${#folders[@]} folder(s) queued for the pipeline."
else
  notify "LosslessBob not found" "Queued ${#folders[@]} folder(s); start the app to load them."
  exit 1
fi
