#!/usr/bin/env bash
# Install the "Send to LosslessBob pipeline" Nemo right-click action for the
# current user. Idempotent — re-run after moving the repo. Pass --uninstall to
# remove it.

set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ACTIONS_DIR="${HOME}/.local/share/nemo/actions"
TARGET="${ACTIONS_DIR}/losslessbob-pipeline.nemo_action"

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$TARGET"
  echo "removed  ${TARGET}"
  exit 0
fi

mkdir -p "$ACTIONS_DIR"
chmod +x "${HERE}/lb-send-to-pipeline.sh"
sed "s|<INSTALL_DIR>|${HERE}|g" "${HERE}/losslessbob-pipeline.nemo_action" > "$TARGET"
echo "installed  ${TARGET}  ->  ${HERE}/lb-send-to-pipeline.sh"
echo "Restart Nemo to pick it up:  nemo -q"
