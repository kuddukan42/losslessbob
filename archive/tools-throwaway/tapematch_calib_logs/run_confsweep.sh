#!/bin/bash
# Phase-2 lever: lower ratio_confidence_min so estimate_ratio_v2 resamples pairs
# that currently gate out as speed-unknown (e.g. real -45800 ppm offsets landing at
# conf~5.0, just under 6.0). Re-runs dense dates that HAD such stranded pairs and
# measures whether corr recovers (recall up) without breaking precision.
#
# PRECONDITION: the orchestrator has already set align.ratio_confidence_min to the
# sweep value in config.yaml (do NOT do it while the v2-baseline batch is running).
# Guard: ABSOLUTE candidate fp must stay <= 9. Abort otherwise (revert config).
cd /home/tjenkins/Documents/losslessbob
L=tools/tapematch/calib_logs
LOG=$L/confsweep_progress.log
CONF=$(grep -oE 'ratio_confidence_min: [0-9.]+' tools/tapematch/config.yaml | head -1)
echo "CONFSWEEP START $(date -Is)  ($CONF)" > $LOG
for d in 1994-04-28 1994-07-04 1989-06-04; do
  t0=$(date +%s)
  timeout 2400 .venv/bin/python3 tools/tapematch/tapematch_session.py "$d" \
      > "$L/confsweep_$d.log" 2>&1
  rc=$?
  .venv/bin/python3 tools/tapematch/regression.py score --cached > $L/confsweep_score.txt 2>&1
  cand=$(grep 'candidate:' $L/confsweep_score.txt)
  fp=$(echo "$cand" | grep -oE 'fp=[0-9]+' | grep -oE '[0-9]+')
  rec=$(grep -E '^recall' $L/confsweep_score.txt | awk '{print $3}')
  # count how many of this date's speed-unknown/offset pairs now resampled to high corr
  echo "[$(date +%H:%M:%S)] $d rc=$rc dur=$(( $(date +%s) - t0 ))s  cand_recall=$rec  cand_fp=$fp" >> $LOG
  if [ -n "$fp" ] && [ "$fp" -gt 9 ]; then
    echo "CONFSWEEP ABORT: candidate fp=$fp > 9 after $d — lower gate causes false merges, REVERT config" >> $LOG
    exit 1
  fi
done
echo "CONFSWEEP END $(date -Is)" >> $LOG
