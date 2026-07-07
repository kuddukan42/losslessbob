#!/usr/bin/env bash
# run_addon_measure.sh — detached measurement watcher for ADDON Tier A Phase 2.
# The population batch (run_addon_calib.sh, reparented to init) is finishing the
# remaining dates on its own. This watcher does NO live audio (no collision risk):
# it waits for population to finish, then runs calibrate_addon.py + score --cached
# and writes the final RESULTS + ADDON_CALIB_DONE marker. nohup => survives Claude
# session limits.
set -u
cd /home/tjenkins/Documents/losslessbob || exit 3
PY=.venv/bin/python3
LOG=tools/tapematch/calib_logs/addon_calib_progress.log
DATES="1990-06-01 1996-07-21 1998-10-28 1991-02-10 1993-06-27 1994-07-04 1996-11-04 1990-11-08 1994-04-28 2001-10-30 1989-06-04"

log(){ echo "[$(date -Iseconds)] $*" >> "$LOG"; }

count_pop(){  # echo # of populated (flaw_match_score) pairs for <date>
  $PY - "$1" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect("tools/tapematch/observations.db")
print(c.execute("SELECT COUNT(*) FROM pairs WHERE concert_date=? AND flaw_match_score IS NOT NULL",
                (sys.argv[1],)).fetchone()[0])
PYEOF
}

log "=== run_addon_measure.sh START (pid $$) — waiting for population batch to finish ==="
# Wait until BOTH the population batch and any live session are gone.
while pgrep -f 'run_addon_calib\.sh' >/dev/null 2>&1 || pgrep -f 'tapematch_session\.py' >/dev/null 2>&1; do
  sleep 30
done
log "population batch finished; verifying all 11 dates populated"

# Safety net: if any date failed to populate, run it now (idempotent; nothing else
# is running, so the collision guard is already satisfied).
for d in $DATES; do
  n=$(count_pop "$d")
  if [ "${n:-0}" -eq 0 ]; then
    log "MISSING $d — running now (safety)"
    timeout 2400 $PY tools/tapematch/tapematch_session.py "$d" \
        >> "tools/tapematch/calib_logs/addon_sess_${d}.log" 2>&1
    log "done $d rc=$?"
  fi
done

log "running measurement (calibrate_addon.py + score --cached)"
{
  echo ""
  echo "## RESULTS ($(date -Iseconds))"
  echo "### calibrate_addon.py  (gap>=0.10 gate + zero-FP bar + Rule B conjunction)"
  $PY tools/tapematch/calibrate_addon.py
  echo ""
  echo "### regression.py score --cached  (ALL merge rules OFF -> baseline; absolute fp MUST be 9)"
  $PY tools/tapematch/regression.py score --cached
} >> "$LOG" 2>&1
log "ADDON_CALIB_DONE"
