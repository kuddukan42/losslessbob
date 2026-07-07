#!/bin/bash
cd /home/tjenkins/Documents/losslessbob
L=tools/tapematch/calib_logs
timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py 1996-11-04 > "$L/1996-11-04.rerun.log" 2>&1
rc=$?
echo "[$(date +%H:%M:%S)] RERUN 1996-11-04 rc=$rc" >> "$L/rerun_progress.log"
if [ $rc -eq 0 ]; then
  bash "$L/analyze_staircase.sh" > "$L/analyzer.rerun.log" 2>&1
  echo "[$(date +%H:%M:%S)] ANALYZER rc=$?" >> "$L/rerun_progress.log"
fi
echo "CHAIN_END rc=$rc" >> "$L/rerun_progress.log"
