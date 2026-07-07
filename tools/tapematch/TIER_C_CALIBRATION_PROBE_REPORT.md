# Tier C ad hoc calibration probe — 7-date, independently-documented ground truth

**Date:** 2026-07-03  **Verdict:** REJECT confirmed on fresh out-of-sample data — reaffirms the
CC_TAPEMATCH_ADDON Tier C gate rejection (see `CALIBRATION_PROGRESS.md`, gap −0.017/−0.074). Not a
gate re-run; a targeted spot-check requested by the user to see how the dormant, rejected
from-scratch contrastive encoder (`tools/tapematch/embedding/`, checkpoint `ckpt/tierc.pt`) scores
real pairs outside the frozen `regression_set.json`, using ground truth sourced independently of
tapematch's own history where possible.

## Why this probe, and how the ground truth was sourced

Three fresh dates (2025-04-11, 2025-11-16, 2025-11-17) were run live this session as a general
"how do our layers separate known sources" exercise (see CHANGELOG 2026-07-03 BUG-235 entry for the
trim-guard fix these runs also exercised). The user then asked to see how Tier C handles the same
dates, but first proposed narrowing to a **smaller, more robustly-documented calibration set** rather
than trusting three ad hoc dates alone.

Ground truth for the additional 4 dates was mined directly from `entry_lineage` (parsed
`same_as_lb`, `parse_confidence=high`) and a direct text scan of `entries.description` for explicit
"different recording" curator language, both restricted to locally-available (`my_collection`)
pairs on the same show date — see `tools/tapematch/_mine_calibration_candidates.py`. Two of the four
same-source candidates were cross-validated against `observations.db`'s own audio-correlation
history (not just curator text):

| date | pair | evidence |
|---|---|---|
| 1996-11-04 Spartanburg SC | LB-12343/LB-14002 | curator text + `fp_score=0.44`, verdict `same_family` across 3 independent runs (2026-06-16 → 2026-07-03) |
| 1990-08-12 Edmonton AB | LB-12353/LB-12257 | curator text (taper-ID correction in torrent comments) + `fp_score=0.42`, verdict `same_family` across 2 independent runs |
| 2002-02-18 Tupelo MS | LB-4088/LB-331 | curator text only: *"This is not the same recording as LB-331"* |
| 1995-11-05 Austin TX | LB-3674/LB-899 | curator text only: *"Appears to be different recording from LB-899"* |

Combined with the 3 fresh dates (2025-04-11: 3 distinct, confirmed via near-zero waveform corr;
2025-11-16: LB-16525/16544 same source at 0.924 primary corr post-BUG-235-fix, LB-16524 distinct;
2025-11-17: all 3 same source **per user**, with LB-16545 a full stem-separated remix of the same
base recording — confirmed by the user directly, since waveform methods alone showed it as
uncorrelated), this gives **7 dates / 17 sources / 13 pairs** (6 same-source, 7 distinct).

## Method

Reused `embedding/infer.py`'s exact windowing/extraction convention (5×60 s excerpts spread across
the trimmed performance window, 1 s windows / 0.5 s hop, speed-corrected nominal time) and
`embed_eval.py`'s exact pair-scoring convention (median over A-windows of cosine-max to B, either
aligned ±2 s nominal-time neighbourhood or global cosine-max), pointed directly at these 17 sources
instead of the frozen `embed_eval_set.json`. Trim/speed metadata came from each date's own
`tapematch_session.py` run (this session, current code). Script: `tools/tapematch/_tierc_probe.py`,
run under the isolated `tools/tapematch/.venv-emb` torch environment.

## Results

| pair | ground truth | tol2 (aligned ±2s) | tol0 (global) |
|---|---|---|---|
| 2025-11-16 LB-16525/16544 | same-source | **0.855** | 0.855 |
| 2025-11-17 LB-16526/16546 | same-source | **0.846** | 0.846 |
| 1996-11-04 LB-12343/14002 | same-source (hard: waveform corr 0.19) | 0.336 | 0.518 |
| 1990-08-12 LB-12353/12257 | same-source (hard: waveform corr 0.007) | 0.315 | 0.491 |
| 2025-11-17 LB-16545/16546 | same-source (**stem-remix pair**) | 0.287 | 0.490 |
| 2025-11-17 LB-16526/16545 | same-source (**stem-remix pair**) | 0.215 | 0.440 |
| 2025-04-11 LB-16316/16317 | distinct | 0.276 | 0.498 |
| 2025-04-11 LB-16316/16347 | distinct | 0.213 | 0.458 |
| 2025-04-11 LB-16317/16347 | distinct | 0.210 | 0.452 |
| 2025-11-16 LB-16524/16544 | distinct | 0.246 | 0.449 |
| 2025-11-16 LB-16524/16525 | distinct | 0.212 | 0.424 |
| 1995-11-05 LB-3674/899 | distinct | 0.273 | **0.521** |
| 2002-02-18 LB-4088/331 | distinct | 0.175 | 0.382 |

| | tol2 n / min / median / max | tol0 n / min / median / max |
|---|---|---|
| same-source | 6 / 0.215 / 0.325 / 0.855 | 6 / 0.440 / 0.504 / 0.855 |
| distinct | 7 / 0.175 / 0.213 / 0.276 | 7 / 0.382 / 0.452 / 0.521 |

## Interpretation

- **The two high scores (0.855, 0.846) are pairs Tier C didn't need to solve** — both already show
  strong primary waveform correlation (0.924, 0.909) in this session's tapematch runs. The embedding
  just confirms what correlation already caught; it isn't demonstrating new discriminative power.
- **The two hard historical same-source pairs (waveform corr ≈0) score only 0.315–0.336 at tol2** —
  barely above the distinct-pair ceiling (0.276). That margin is too thin to trust as a decision
  boundary, consistent with the frozen-set gate's rejection.
- **The stem-remix pairs are the direct answer to "can Tier C see through a remix":** both LB-16545
  pairings score 0.215 and 0.287 — squarely inside the distinct-source band (0.175–0.276),
  indistinguishable from a genuinely different recording. Stem-separation/remix processing destroys
  whatever lineage signal the encoder learned, the same way it destroys waveform correlation.
- **tol0 (global) is worse, not better:** the confirmed-**distinct** Austin pair (LB-3674/899) scores
  0.521 — higher than three of the six same-source pairs. Global matching inverts the ordering on
  this set; not usable as a discriminator here either.

## Conclusion

This independently reconfirms the CC_TAPEMATCH_ADDON Tier C REJECT decision (gap −0.017/−0.074 on
the frozen eval set) on fresh, out-of-sample, independently-documented pairs: Tier C adds no
reliable signal beyond what tapematch's existing waveform/fingerprint methods already catch, and it
specifically fails on the "same lineage, heavily reprocessed" case (full stem-separation remix) that
would be the strongest justification for shipping it. No config/verdict/schema changes made — this
was a read-only probe against the already-dormant checkpoint.

## Reproduce

```
.venv/bin/python3 tools/tapematch/_mine_calibration_candidates.py   # candidate mining (optional)
tools/tapematch/.venv-emb/bin/python tools/tapematch/_tierc_probe.py
```

Throwaway scripts kept for reuse: `tools/tapematch/_mine_calibration_candidates.py`,
`tools/tapematch/_tierc_probe.py`. Raw run output: `data/tapematch/_tierc_probe_output.txt`,
`data/tapematch/_run_*.stdout` (per-date tapematch session logs for the 4 newly-run calibration
dates).
