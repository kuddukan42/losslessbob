#!/bin/bash
cd /home/tjenkins/Documents/losslessbob
OUT=tools/tapematch/calib_logs/staircase_analysis.txt
for i in $(seq 1 60); do
  grep -q 'DONE  1996-11-04' tools/tapematch/calib_logs/progress.log 2>/dev/null && break
  sleep 30
done
{
echo "=== analysis at $(date -Is) ==="
echo "--- harness A/B (candidate = staircase0.40+curator0.43+lofi0.40) ---"
.venv/bin/python3 tools/tapematch/regression.py score --cached 2>&1 | tail -12
echo
echo "--- staircase dates: FN (says_same=1,different) vs NEG (says_same=0) fp/hiss bands ---"
.venv/bin/python3 - <<'PY'
import sqlite3
c=sqlite3.connect("tools/tapematch/observations.db")
for d in ('1993-06-27','1996-11-04'):
    print(f"### {d}")
    for r in c.execute("""select lb_a,lb_b,lb_says_same,corr,windowed_frac,hiss_frac,hiss_median,fp_score,
                          speed_kind_a,speed_kind_b,tapematch_verdict from latest_pairs
                          where concert_date=? order by lb_says_same desc, fp_score desc""",(d,)):
        if r[2] not in (0,1): continue
        stair = 'S' if ('staircase' in (r[8] or '') or 'staircase' in (r[9] or '')) else ' '
        fp='%.3f'%r[7] if r[7] is not None else 'NA'
        hm='%.3f'%r[6] if r[6] is not None else 'NA'
        wf='%.2f'%r[4] if r[4] is not None else 'NA'
        tag='FN' if (r[2]==1 and r[10]=='different_family') else ('TP' if r[2]==1 else ('FP' if r[10]=='same_family' else 'TN'))
        print(f"  [{stair}] LB-{r[0]}/{r[1]} ss={r[2]} {tag}  corr={r[3]:.3f} wf={wf} hmed={hm} fp={fp}")
c.close()
PY
} > $OUT 2>&1
echo "ANALYSIS_DONE" >> $OUT
