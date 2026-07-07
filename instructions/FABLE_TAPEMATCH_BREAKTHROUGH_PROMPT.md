You are being brought in as a fresh pair of eyes on a stuck research problem. This is not
a "read the docs and summarize" task — it's a "find the breakthrough we're missing" task.
Multiple prior sessions (by other Claude instances) have attacked this and plateaued. Your
job is to find an angle they haven't tried, or spot a flaw in their reasoning that reopens
a path they wrongly closed. Do not just re-propose something already listed as rejected
below unless you have a specific reason their rejection of it was wrong.

REPO: /home/tjenkins/Documents/losslessbob  (read files directly, don't take this brief as
a substitute for looking at the code/data yourself)

## The domain problem

`tools/tapematch/` analyzes sets of audience recordings of the same Bob Dylan concert date
and decides which recordings share a common source tape (same taper/transfer chain), i.e.
groups files into "families" of duplicate/derivative recordings. This feeds curation of the
LosslessBob lossless archive. It works via layered signals: (1) primary residual cross-
correlation at 12 anchor windows (HF diff signal — catches clean same-source pairs after
speed/lag alignment), (2) secondary matching for cross-family pairs (60s-grid windowed
coverage + quiet-segment hiss correlation — catches remasters/EQ'd copies), (3) a Shazam-
style spectral-peak fingerprint (confirmatory, HF-band-restricted).

## The metric and where it's stuck

Scored against a frozen labeled regression set (`tools/tapematch/regression_set.json`,
2965 pairs / 827 dates, ground truth = curator field `lb_says_same`) via
`tools/tapematch/regression.py score --cached`.

- Original baseline: recall 38.3%, precision 98.2% (tp=663 fn=1066 fp=12 tn=1422)
- Current shipped state after ~7 rounds of fixes: recall 41.6–41.7%, precision 98.6%,
  fp=9 (frozen — must never regress above this)
- A dedicated false-negative audit (Task 1, see FN_AUDIT_REPORT.md) estimated ~36.7%
  (CI 25.6–49.3%) of the remaining corr<0.05 false negatives are curator label noise
  (mislabeled pairs, not true same-family). Re-based achievable ceiling: ~80% recall
  (CI 73.1–86.0%), not 100%.
- So: 41.6% actual vs ~80% achievable ceiling. That gap is the problem. Nobody has closed
  it. Every attempt to close it with a hand-engineered or learned similarity signal has
  failed the same way (see below) — this repeated failure mode is the most important
  thing to understand before proposing anything new.

## Everything tried so far, chronologically, with outcomes

Read `instructions/CC_TAPEMATCH_FIXES.md` and `instructions/CC_TAPEMATCH_ADDON.md` in full
for the detailed narrative. Also read `tools/tapematch/CALIBRATION_PROGRESS.md`,
`tools/tapematch/FN_AUDIT_REPORT.md`, `tools/tapematch/RECALL_RECOVERY_REPORT.md`,
`tools/tapematch/TIER_B_EMBED_REPORT.md`, `tools/tapematch/TIER_C_CALIBRATION_PROBE_REPORT.md`.
Condensed history:

1. Cat-3 focused re-run (6 known-hard pairs, staged in isolation): 0/6 flipped. They still
   score corr~0.005 even directly aligned against each other.
2. Staircase either-side fallback + conditional fingerprint threshold (0.40): SHIPPED,
   +2.3–2.4 recall pts, zero new FP. This is the one clean win in the whole effort.
3. Curator-conditional FP threshold (0.43) + lo-fi hiss relaxation (0.40): shipped but only
   covers 15.5% of frozen positives, marginal gain. A tempting but circular version (keying
   directly on the ground-truth label `lb_says_same` itself) was correctly identified and
   rejected as methodologically invalid — worth understanding why, so you don't repeat it.
4. `estimate_ratio_v2` (prior-centered speed estimator) + duration-ratio prior + confidence
   gate: shipped, precision-safe, but only +0.2 recall across 10 dense dates.
5. Lag-curve slope residual correction + pyin pitch fallback: folded in, rarely fires,
   self-limiting (can't create false positives, can only fail to help).
6. Confidence-gate threshold sweep (6.0 → 4.5): NEGATIVE RESULT, reverted. This is a key
   diagnostic: pairs correctly resampled at a lower confidence threshold, and correlation
   stayed 0.002–0.010 regardless. Direct quote from the report: "Correct speed alignment
   does not make them correlate." I.e. for this population, speed/alignment error is ruled
   out as the cause of non-matching.
7. Ratio-invariant triplet fingerprint (Panako-style, encodes only interval ratios so it
   should survive speed changes): REJECTED. Same-source Dice median 0.656 vs same-date-
   different-source Dice median 0.638 — a gap of -0.012 (they overlap; at threshold 0.45 it
   produced 5 false merges on frozen negatives). Root cause as stated in the report: "same-
   concert recordings share real temporal/spectral structure, so ratio-encoded hashes
   collide as badly for true negatives as positives."
8. Flaw fingerprint (dropout/click/cut event matching, content-blind by design): the
   cleanest signal found (TN caps at 0.133, TP fans to 0.900 — no collision), but only
   covers ~6% of frozen FN, so max gain ≈ +1-2 TP. Also surfaced a "guard-masking trap":
   a per-run A/B check said "new FP: none" but the true absolute FP count vs the frozen
   baseline of 9 had actually risen to 10 via transitive clustering. Left dormant.
9. Spectral-ratio stationarity signal, envelope correlation signal, and their AND-
   combination ("Rule B"): all REJECTED, large negative gaps (-0.464, -0.377), Rule B
   recovers 0 TP.
10. Tier B: pretrained neural audio fingerprint embedding (neural-music-fp / nmfp-triplet
    checkpoint): REJECTED on a strict statistical gate (p10(TP) - p90(TN) = -0.034 aligned /
    +0.007 global; needed >=0.10), BUT flagged as an encouraging near-miss — median
    separation is dramatic (TP median 0.91-0.96 vs same-show-TN median 0.15-0.34). The
    failure is specifically in the tails overlapping, not the bulk of the distribution.
    Also surfaced 3 labels that look wrong on manual waveform inspection (flagged
    `label_suspect`, never actually corrected in the label set).
11. Tier C: from-scratch contrastive embedding, trained with same-show hard negatives
    (PyTorch, RTX 3080, 30 epochs / ~70 min): REJECTED, gap -0.017 (tol=0) / -0.074 (tol=2),
    WORSE than the off-the-shelf Tier B model even at the median (TP/TN medians 0.520/0.441
    vs nmfp's 0.912/0.150). One config, one run — not a real hyperparameter search. An
    out-of-sample probe on 7 fresh dates reconfirmed the reject, and additionally found that
    stem-separated remix pairs score indistinguishably from genuinely different recordings
    (0.215-0.287) — the embedding's lineage signal does not survive heavy reprocessing.

## The recurring failure mode ("the triplet lesson")

Every hand-engineered or learned similarity signal that is even partly driven by shared
musical/performance content collides on same-concert-different-source negatives, because
two audience recordings of the same show inherently share timing, pitch, and energy
contour. This governed every subsequent signal design choice in the addon effort and is
the single most important constraint you must respect or explicitly argue against.

## Two paths the prior effort named but did not pursue

(a) A real hyperparameter/architecture search for the contrastive embedding — Tier C was
    one config trained once, not a search.
(b) Cleaning the label set before re-measuring anything. A meaningful slice of "ground
    truth" (`lb_says_same`) is itself acknowledged to be wrong (see the label-noise
    estimate and the 3 `label_suspect` flags from Tier B). A manual-audit tool already
    exists for this (`tools/tapematch/calibration_audit.html` / `.json`,
    `build_calibration_audit_html.py`) but the labels were never actually edited. Nobody
    has re-run the recall measurement against a corrected label set to see how much of the
    "gap" is actually real.

## Key code (for grounding any concrete proposal in what exists)

- `tools/tapematch/tapematch/verdict.py` — `pair_links` (~257-306, the OR-logic that
  decides same-family) and `cluster_verdicts` (~309-366, transitive union-find per date).
- `tools/tapematch/tapematch/match.py` — `estimate_ratio_v2` (200-262), `pitch_ratio_pyin`
  (311-412, has a flagged possible direction bug), `secondary_corr_pair` (592-703),
  `_fingerprint_hashes` (733-779), `cluster` (859-910), `extract_flaw_events` /
  `flaw_match_score` (1155-1255), `spectral_ratio_stationarity` (1268-1391), `envelope_corr`
  (1411-1501), `triplet_hashes` / `triplet_window` (1567-1649).
- `tools/tapematch/tapematch/align.py` — `local_lag` / `local_lag_centered` (73-134),
  `residual_ppm_from_lag_curve` (149-175), `interpret_curve` (178-197).
- `tools/tapematch/config.yaml` — every threshold above lives here; note which signals are
  `enabled: false` (dormant, not deleted) vs live.
- `tools/tapematch/regression.py` + `regression_set.json` — the scoring harness and frozen
  labels. NEVER regenerate `regression_set.json` mid-experiment; it must stay frozen for
  A/B comparisons to mean anything.

## What I actually need from you

1. Read the source materials above yourself — don't just work from this summary.
2. Identify the single most promising unexplored angle to close some of the 41.6% → ~80%
   recall gap, OR make the case that a previously-rejected approach was rejected for the
   wrong reason / with a fixable flaw in its own experiment design (e.g., check whether the
   flaw-fingerprint "guard-masking trap" pattern might be silently invalidating any of the
   OTHER "clean gap" numbers reported above — nobody seems to have gone back and checked
   that).
3. Give a concrete, falsifiable next experiment: what signal/change, what you predict it
   will show, and specifically how it would be measured against `regression.py score
   --cached` such that a real (absolute, not per-run-relative) fp regression above 9 would
   be caught.
4. If your answer is "clean the labels first," say exactly how you'd distinguish a true
   label-noise correction from a curator-domain-knowledge correction you're not qualified
   to make, and how many pairs you'd expect to flip.

Do not hand back a restatement of the problem or a rehash of tiers A/B/C. I need either a
genuinely new hypothesis or a specific, evidenced objection to how an existing rejection was
measured.
