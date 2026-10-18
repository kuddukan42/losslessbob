#!/bin/bash
# Phase-2 Cat-1 validation of estimate_ratio_v2 (triplet already disabled).
# Re-runs Cat-1-dense frozen dates with the new code; skips (rc=3) are harmless.
# Guard: ABSOLUTE candidate fp must stay <= 9 (the frozen pre-existing FP count) —
# this catches a v2-induced false merge that the per-date candidate-vs-baseline
# guard would mask. Abort on fp>9.
cd /home/tjenkins/Documents/losslessbob
L=tools/tapematch/calib_logs
LOG=$L/catval_progress.log
echo "CATVAL BATCH START $(date -Is)" > $LOG
for d in 1994-04-28 1989-06-04 1994-07-04 1990-10-26 1991-06-11 1991-11-05 \
         1989-05-27 1989-10-31 1988-07-08 1989-06-07; do
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "$L/catval_$d.log" 2>&1
  rc=$?
  .venv/bin/python3 tools/tapematch/regression.py score --cached > $L/catval_score.txt 2>&1
  cand=$(grep 'candidate:' $L/catval_score.txt)
  fp=$(echo "$cand" | grep -oE 'fp=[0-9]+' | grep -oE '[0-9]+')
  rec=$(grep -E '^recall' $L/catval_score.txt | awk '{print $3}')
  echo "[$(date +%H:%M:%S)] $d rc=$rc dur=$(( $(date +%s) - t0 ))s  cand_recall=$rec  cand_fp=$fp" >> $LOG
  if [ -n "$fp" ] && [ "$fp" -gt 9 ]; then
    echo "CATVAL ABORT: candidate fp=$fp > 9 after $d — v2 precision regression, investigate" >> $LOG
    exit 1
  fi
done
echo "CATVAL BATCH END $(date -Is)" >> $LOG
