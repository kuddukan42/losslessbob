#!/bin/bash
cd /home/tjenkins/Documents/losslessbob
LOG=tools/tapematch/calib_logs/progress2.log
echo "BATCH2 START $(date -Is)" > $LOG
for d in 2001-10-30 1990-08-12 1991-06-06 1990-11-08; do
  echo "[$(date +%H:%M:%S)] START $d" >> $LOG
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "tools/tapematch/calib_logs/$d.log" 2>&1
  rc=$?
  t1=$(date +%s)
  echo "[$(date +%H:%M:%S)] DONE  $d  rc=$rc dur=$((t1-t0))s" >> $LOG
done
.venv/bin/python3 tools/tapematch/regression.py score --cached \
    > tools/tapematch/calib_logs/score_after_batch2.txt 2>&1
echo "[$(date +%H:%M:%S)] SCORE rc=$?" >> $LOG
echo "BATCH2 END" >> $LOG
