# Scheduled jobs: WTRF + TUIT

`tools/wtrf.sh` and `tools/tuit.sh` run unattended as **systemd user timers**. They do not
run from cron. Their logins come from an **encrypted systemd credential**, not the
desktop keyring and not a plain-text file. Installer: `tools/lb_timers_setup.sh`.

## Why not cron + keyring

A cron job has no D-Bus session, so `backend/credentials.py` can't reach the keyring. It
falls back to `data/credentials.env`, and that file held no WTRF login. Every cron run
of `wtrf.sh` exited 1 with `WTRF credentials not configured`. There's no MTA, so cron
dropped the output and nothing reported the failure.

## How it works

| Piece | Location |
|---|---|
| Encrypted credential (TPM2 + host key, scoped to your UID) | `~/.config/credstore.encrypted/lb-creds.cred` |
| Units | `~/.config/systemd/user/lb-wtrf.{service,timer}`, `lb-tuit.{service,timer}` |
| Schedule | `lb-wtrf` daily 12:46, `lb-tuit` daily 01:30 (`WTRF_CAL` / `TUIT_CAL` in the script) |

At run time systemd decrypts the credential into a private tmpfs, exposed to that service
only as `$CREDENTIALS_DIRECTORY/lb-creds` (mode 0400). The unit sets
`LB_CREDENTIALS_FILE=%d/lb-creds`, so the existing env-file loader in
`backend/credentials.py` reads it with no code change. The copy is removed when the job
exits. Lingering is enabled (`loginctl show-user tjenkins -p Linger`), so timers run
while you're logged out. With `Persistent=true`, a run missed while the machine was off
happens at next boot.

The credential file is a plain `KEY=VALUE` env file:

```
LB_WTRF_USER=...          LB_WTRF_PASSWORD=...
LB_TUIT_USER=...          LB_TUIT_PASSWORD=...
LB_QBT_APIKEY_USER=...    LB_QBT_APIKEY=...       # or LB_QBT_USER / LB_QBT_PASSWORD
```

## Setup (one time)

```
tools/lb_timers_setup.sh            # dry run: prints the units it would write
tools/lb_timers_setup.sh --apply    # edit secrets → encrypt → install → enable timers
tools/lb_timers_setup.sh --test     # wtrf --dry-run + tuit --listing-only via the credential
crontab -e                          # delete the old "46 12 * * * …/tools/wtrf.sh" line
```

`--apply` opens `$EDITOR` on a temp file in `$XDG_RUNTIME_DIR` (tmpfs, 0700). It is
pre-filled from `data/credentials.env`, or from the existing credential on a re-run.
Blank keys are added for anything missing. The temp file is shredded after encryption.

Once `--test` passes, `data/credentials.env` can be shredded (`shred -u`). Check the GUI
app first: it may read the TUIT login from that file if the keyring doesn't have it.

## Day to day

| Task | Command |
|---|---|
| Next/last run times | `systemctl --user list-timers 'lb-*'` |
| Logs | `journalctl --user -u lb-wtrf -u lb-tuit --since today` |
| Run now | `systemctl --user start lb-wtrf.service` (real run, not a dry run) |
| Change a password or schedule | edit `WTRF_CAL`/`TUIT_CAL` if needed, re-run `--apply` |
| Pause | `systemctl --user disable --now lb-wtrf.timer` |
| Remove | disable both timers, delete the four unit files + `lb-creds.cred`, `daemon-reload` |

## Security notes

- **Protected:** the secret at rest. The `.cred` file is useless if copied to a backup or
  another machine, because the key is in the TPM and `/var/lib/systemd/credential.secret`
  (root-only).
- **Not protected:** a process running as `tjenkins` *while a job runs* could read the
  decrypted copy. Isolating the secret from your own processes would need a dedicated
  system user.
- Use a WTRF password unique to WTRF. Prefer the qBittorrent API key over the WebUI password.
- Never `cat` the decrypted credential in a Claude session: tool output is transmitted.
