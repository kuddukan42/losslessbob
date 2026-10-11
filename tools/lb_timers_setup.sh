#!/usr/bin/env bash
# Install systemd user timers for wtrf.sh and tuit.sh, with their logins held as
# a TPM2/host-key encrypted credential (systemd-creds --user) instead of the
# desktop keyring or a plain-text env file.
#
#   tools/lb_timers_setup.sh            # dry run: show what would be written
#   tools/lb_timers_setup.sh --apply    # edit secrets, encrypt, install, enable
#   tools/lb_timers_setup.sh --test     # dry-run both jobs through the credential
#
# The secrets are edited in $XDG_RUNTIME_DIR (tmpfs, 0700) and shredded after
# encryption. Seeded from data/credentials.env when that file exists. Jobs log
# to the user journal: journalctl --user -u lb-wtrf -u lb-tuit
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
CRED_DIR="$HOME/.config/credstore.encrypted"
CRED="$CRED_DIR/lb-creds.cred"
WTRF_CAL="*-*-* 12:46:00"
TUIT_CAL="*-*-* 01:30:00"
MODE="${1:-dry}"

unit() {  # name, description, command, calendar
    cat <<EOF
# ---- $UNIT_DIR/$1.service
[Unit]
Description=$2

[Service]
Type=oneshot
LoadCredentialEncrypted=lb-creds:$CRED
Environment=LB_CREDENTIALS_FILE=%d/lb-creds
ExecStart=$3
TimeoutStartSec=6h

# ---- $UNIT_DIR/$1.timer
[Unit]
Description=$2 (schedule)

[Timer]
OnCalendar=$4
Persistent=true

[Install]
WantedBy=timers.target
EOF
}

write_unit() {  # name, description, command, calendar
    unit "$@" | awk -v dir="$UNIT_DIR" '
        /^# ---- / { out = $3; next }
        { print > out }'
}

try() {  # name, command...
    local name="$1"; shift
    echo "== $name"
    systemd-run --user --quiet --wait --pipe --collect \
        -p "LoadCredentialEncrypted=lb-creds:$CRED" \
        /bin/sh -c 'LB_CREDENTIALS_FILE="$CREDENTIALS_DIRECTORY/lb-creds" exec "$@"' sh "$@"
}

case "$MODE" in
dry)
    echo "Would encrypt secrets to $CRED and write:"
    unit lb-wtrf "WTRF board seed walk" "$REPO/tools/wtrf.sh" "$WTRF_CAL"
    unit lb-tuit "TUIT nightly sync" "$REPO/tools/tuit.sh" "$TUIT_CAL"
    echo "Re-run with --apply."
    ;;
--apply)
    mkdir -p "$UNIT_DIR" "$CRED_DIR"
    chmod 700 "$CRED_DIR"
    tmp="$(mktemp -p "${XDG_RUNTIME_DIR:?}" lb-creds.XXXXXX)"
    trap 'shred -u "$tmp" 2>/dev/null || rm -f "$tmp"' EXIT
    if [[ -f "$CRED" ]]; then
        systemd-creds --user decrypt --name=lb-creds "$CRED" "$tmp"
    elif [[ -f "$REPO/data/credentials.env" ]]; then
        cat "$REPO/data/credentials.env" > "$tmp"
    fi
    for key in LB_WTRF_USER LB_WTRF_PASSWORD LB_TUIT_USER LB_TUIT_PASSWORD \
               LB_QBT_APIKEY_USER LB_QBT_APIKEY LB_QBT_USER LB_QBT_PASSWORD; do
        grep -q "^$key=" "$tmp" || echo "$key=" >> "$tmp"
    done
    echo "# qBittorrent: fill the APIKEY pair OR the USER/PASSWORD pair." >> "$tmp"
    "${EDITOR:-nano}" "$tmp"
    systemd-creds --user encrypt --name=lb-creds "$tmp" "$CRED"
    chmod 600 "$CRED"
    write_unit lb-wtrf "WTRF board seed walk" "$REPO/tools/wtrf.sh" "$WTRF_CAL"
    write_unit lb-tuit "TUIT nightly sync" "$REPO/tools/tuit.sh" "$TUIT_CAL"
    systemctl --user daemon-reload
    systemctl --user enable --now lb-wtrf.timer lb-tuit.timer
    systemctl --user list-timers 'lb-*' --no-pager
    echo "Encrypted: $CRED. Next: tools/lb_timers_setup.sh --test"
    ;;
--test)
    try wtrf "$REPO/tools/wtrf.sh" --pages 1 --dry-run
    try tuit "$REPO/.venv/bin/python3" "$REPO/tools/tuit_sync.py" --pages 1 --listing-only
    ;;
*)
    echo "usage: $0 [--apply | --test]" >&2; exit 2 ;;
esac
