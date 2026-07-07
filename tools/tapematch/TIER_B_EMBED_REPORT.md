# Tier B — Pretrained neural-fingerprint embedding evaluation (CC_TAPEMATCH_ADDON Task 6)

**Date:** 2026-07-03  **Verdict:** REJECT on the spec gate (p10(TP)−p90(TN) ≥ 0.10 not met),
but a **qualified / encouraging** negative — learned similarity clearly separates the population
that killed every content-based signal. Green-lights Tier C (Task 7).

## Model (spec 6.1.1)

- **`neural-music-fp` (raraz15, ISMIR 2025)**, checkpoint **`nmfp-triplet` / ckpt-100** (Zenodo
  record 15719945). The spec-named degradation-robust neural audio fingerprint, with a
  **discriminative fingerprint head** (contrastive triplet loss) — trained for exactly this
  transformation class (same recording under noise/RIR/mic-IR/EQ/codec degradation).
- **Input:** 8 kHz mono, 1 s segments, 256-mel (essentia, f∈[160,4000] Hz, STFT 1024/256,
  80 dB dynamic range, scaled to [−1,1]), 0.5 s hop → **128-d L2-normalized** fingerprints.
- **Why it should separate same-show pairs (unlike triplet):** it is trained to match a query to
  the *same master recording* under degradation, and to push apart *different* recordings. Two
  different-source captures of one concert are different masters (mic position / room / transfer),
  so a faithful fingerprint should rate them dissimilar — the property env_corr / triplet lacked.
- **Env:** isolated `tools/tapematch/.venv-nmfp` (py3.11, tensorflow-cpu 2.13, essentia); CPU
  inference (RTX 3080 unused). Faithful by construction — fingerprints computed on exactly-8000-
  sample segments (the trained L/H), no resampling/parameter drift vs the released weights.

## Evaluation set (spec 6.1.4) — `embed_eval_set.json`

60 TP (frozen positives, corr ≥ 0.05) / 60 same-date different-source TN / 60 target-FN (frozen
positives, corr < 0.05, `label_suspect` excluded). 184 distinct sources over 67 dates; each source
embedded once (`nmfp_embed.py` → `embed_cache/`), scored by `embed_eval.py`. Pair score = median
over A-windows of cosine-max to B-windows (aligned ±2 s neighbourhood, or global cosine-max).

## Results

| population | n | p10 | median | p90 | max |
|---|---|---|---|---|---|
| **aligned (±2 s)** ||||||
| TP | 60 | 0.401 | **0.912** | 0.993 | 1.000 |
| TN (same-show) | 59 | 0.058 | **0.150** | 0.435 | 0.961 |
| FN (target) | 60 | 0.099 | 0.215 | 0.494 | 0.944 |
| **global cosine-max** ||||||
| TP | 60 | 0.485 | **0.958** | 0.989 | 1.000 |
| TN (same-show) | 60 | 0.258 | **0.344** | 0.478 | 0.961 |
| FN (target) | 60 | 0.270 | 0.397 | 0.780 | 0.966 |

- **Gap (spec metric):** aligned **−0.034**, global **+0.007** — both **< 0.10 → REJECT**.
  (Triplet baseline was −0.012; nmfp is comparable on the *strict tail gap* but see below.)
- **Central separation is dramatic:** TP median ≈ 0.91–0.96 vs same-show-TN median ≈ 0.15–0.34
  (Δ ≈ 0.6–0.76). The learned fingerprint captures real lineage structure — the opposite of
  triplet's flat collision (median Δ ≈ 0). The gate fails only on **tail overlap** (TP low tail
  meets TN high tail), which governs *lone-merge* safety; nmfp would only ever be a Rule-C
  (conjunctive) signal.

## Same-show collision analysis (the killer tail)

The single worst "collision", **TN max = 0.961 (LB4642/LB9900, 1988-08-26)**, is a **label error**,
not a model failure: waveform **corr = 0.950** and the tapematch pipeline already places both in the
**same family (4/4)** — a frozen "negative" that is actually the same recording. A full frozen-set
scan found **3** such waveform-contradicted negatives (corr 0.92–0.95, same family: LB4642/LB9900,
LB6825/LB9180, LB3431/LB3455); all flagged `pairs.label_suspect=1` (they are poison as Tier C hard
negatives — you cannot teach a model to push apart two identical recordings).

Excluding that label error, **genuine same-show collisions cap at 0.605**. Zero-clean-FP operating
points (over the 59 eval negatives):

| bar | FN recovered /60 | clean-neg FP | FP incl. label-error |
|---|---|---|---|
| 0.60 | 12 (20%) | 2 | 3 |
| **0.65** | **8 (13%)** | **0** | 1 |
| 0.70 | 8 | 0 | 1 |
| 0.80 | 5 | 0 | 1 |

So a Rule-C conjunctive threshold ≈ **0.65** is **precision-safe on this eval subset** and recovers
~13% of target FN. The low-TP tail (e.g. LB4535/LB9529 corr 0.95 but emb 0.41) is largely a
**sparse-excerpt alignment artifact** — differently-trimmed transfers sample different songs across
the 5×60 s excerpts — not a true model miss; denser excerpts would lift the TP tail.

## Verdict & handoff (spec 6.2)

- **Per the spec gate (p10(TP)−p90(TN) ≥ 0.10): REJECT.** nmfp is not a lone-merge signal.
- **Unlike triplet, this is a POSITIVE signal for Tier C:** a *pretrained* fingerprint already
  separates same-source lineage (median 0.9) from same-show different-source (median 0.15–0.34),
  and the only high-tail collisions are label errors (waveform corr ≥ 0.9). Genuine collisions cap
  at ~0.60. **Tier C's contrastive model, trained with same-show hard negatives, targets exactly the
  0.3–0.6 collision band** this measurement isolates.
- **Baseline carried into Task 7:** same-show-TN median ≈ 0.15 (aligned) / 0.34 (global), max genuine
  collision ≈ 0.605; TP median ≈ 0.91–0.96. Augmentation-sanity + same-show-gap gates (7.3) measured
  against this population.
- **Not shipped:** no `pairs.emb_score` / Rule C wiring. The marginal precision-safe bar (0.65,
  ~8 FN, 0 clean FP) is validated only over 59 negatives; a production merge path would require
  populating `emb_score` over the **full 1390 frozen negatives** and passing `regression.py score
  --cached` at absolute fp ≤ 9 — deferred (the strict gate having failed, spec says stop Tier B).

## Reproduce

```
.venv/bin/python3 tools/tapematch/build_embed_eval_set.py
tools/tapematch/.venv-nmfp/bin/python tools/tapematch/nmfp_embed.py     # → embed_cache/
.venv/bin/python3 tools/tapematch/embed_eval.py --tol 2                 # aligned
.venv/bin/python3 tools/tapematch/embed_eval.py --tol 0                 # global
```
