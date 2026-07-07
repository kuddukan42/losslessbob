# Tapematch Calibration — Quick Guide

## The rule that governs everything

**Never trade precision for recall.** A false merge fuses two whole families
and poisons everything downstream. A miss just waits for a better algorithm.
Every change must show zero new false positives before it ships.

## One-time setup

1. Hand `CC_TAPEMATCH_FIXES.md` to Claude Code.
2. Confirm Task 1 (regression harness) is done first and the baseline
   reproduces: recall 38.3%, precision 98.2%.
3. Commit `regression_set.json`. This is your fixed measuring stick — don't
   regenerate it.

## The iteration loop (repeat for every change)

```
1. Change ONE thing        (one threshold, one algorithm, one task)
2. Score it                python tools/tapematch/regression.py score
                           (use --cached for threshold-only changes — seconds)
3. Read two numbers        recall delta  +  list of NEW false positives
4. Decide:
     - New FPs = 0, recall up      -> keep it, commit, log in CHANGELOG
     - New FPs > 0                 -> inspect each FP by hand
         - curator label wrong?    -> fix the label, re-score
         - real false merge?       -> back off the change (raise threshold
                                       in small steps) until FPs = 0
5. Next change.
```

## Order of work (biggest win per effort)

1. **Cat 3 re-run** — 6 pairs, no code. Free wins.
2. **Staircase fixes** (Task 3) — config + small guard change.
3. **Conditional thresholds** (Task 4) — config only, scores in seconds.
4. **Speed estimator** (Tasks 5–6) — biggest recall jump (~55% of misses).
5. **Triplet fingerprint** (Task 7) — highest risk; calibrate before enabling.

## When you run out of labeled pairs

- Run tapematch on the 411 curator pairs not yet processed — every run adds
  labeled data to the harness for free.
- When you manually confirm/deny a family in the GUI, that verdict feeds the
  harness too. Your everyday verification work IS the calibration data.
- Re-freeze the regression set only at milestones (after a full task lands),
  never mid-experiment.

## Sanity checks before trusting a big recall jump

- Run 2–3 control dates you know by heart — family output must be identical
  or the differences must be explainable.
- Spot-listen to 2–3 newly merged pairs. If your ears disagree, the ears win:
  mark the pair, investigate.

## What "done" looks like

Recall climbing in steps toward ~80%+ while the FP list stays empty.
When a plateau holds after Tasks 5–7, the remaining misses are the genuine
signal-loss cases — that's when the Phase-1 feature extraction (dropouts,
stereo geometry) and the embedding conversation start, not before.
