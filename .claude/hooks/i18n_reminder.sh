#!/usr/bin/env bash
# PostToolUse (Edit|Write) advisory hook: reminds to sync locales when the
# gui_next English source locale file changes. Exit 2 + stderr surfaces the
# reminder to the model as advisory feedback (does not block the edit).

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

[ -z "$file" ] && exit 0

case "$file" in
    */gui_next/src/renderer/src/locales/en.json)
        echo "en.json changed — run /gui-next-i18n before session close to sync de/fr/es/it/nl." >&2
        exit 2
        ;;
    *)
        exit 0
        ;;
esac
