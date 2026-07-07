#!/bin/bash
cd /home/tjenkins/Documents/losslessbob
LOG=tools/tapematch/calib_logs/progress.log
echo "BATCH START $(date -Is)" > $LOG
for d in 1990-06-01 1996-07-21 1998-10-28 1993-06-27 1996-11-04 1991-02-10; do
  echo "[$(date +%H:%M:%S)] START $d" >> $LOG
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "tools/tapematch/calib_logs/$d.log" 2>&1
  rc=$?
  t1=$(date +%s)
  echo "[$(date +%H:%M:%S)] DONE  $d  rc=$rc  ${t1}s dur=$((t1-t0))s" >> $LOG
done
echo "BATCH END $(date -Is)" >> $LOG
