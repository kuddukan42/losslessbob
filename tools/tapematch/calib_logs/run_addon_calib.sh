#!/bin/bash
# Phase 2 ADDON Tier A calibration — serial live runs for the remaining 10 dates
# (1990-06-01 already run standalone before this script). No merge rule is armed
# (addon_links.rule_* all enabled:false), so no per-date FP guard is needed here;
# regression.py score --cached is run once at the very end (task step 5).
cd /home/tjenkins/Documents/losslessbob
LOG=tools/tapematch/calib_logs/addon_calib_run.log
echo "ADDON_CALIB START $(date -Is)" > "$LOG"
for d in 1996-07-21 1998-10-28 1991-02-10 1993-06-27 1994-07-04 1996-11-04 \
         1990-11-08 1994-04-28 2001-10-30 1989-06-04; do
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "tools/tapematch/calib_logs/addon_$d.log" 2>&1
  rc=$?
  echo "[$(date +%H:%M:%S)] DONE $d rc=$rc dur=$(( $(date +%s) - t0 ))s" >> "$LOG"
done
echo "ADDON_CALIB END $(date -Is)" >> "$LOG"
