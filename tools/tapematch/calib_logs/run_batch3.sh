#!/bin/bash
cd /home/tjenkins/Documents/losslessbob
LOG=tools/tapematch/calib_logs/progress3.log
echo "BATCH3 START $(date -Is)" > $LOG
for d in 1992-06-30 1987-09-12 1987-09-23 1989-06-20 1995-03-12 1996-10-26 \
         1990-08-18 1990-11-10 1990-11-13 1992-05-02 1993-02-16 1993-04-12 \
         1993-04-19 1995-04-09 2001-07-18; do
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "tools/tapematch/calib_logs/$d.log" 2>&1
  rc=$?
  echo "[$(date +%H:%M:%S)] DONE $d rc=$rc dur=$(( $(date +%s) - t0 ))s" >> $LOG
  .venv/bin/python3 tools/tapematch/regression.py score --cached \
      > tools/tapematch/calib_logs/score_latest.txt 2>&1
  src=$?
  grep -E 'recall|new FP' tools/tapematch/calib_logs/score_latest.txt \
      | sed "s/^/[$d] /" >> $LOG
  if [ $src -ne 0 ]; then
    echo "BATCH3 ABORT: new FP after $d (score exit $src)" >> $LOG
    exit 1
  fi
done
echo "BATCH3 END" >> $LOG
