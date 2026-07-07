# Tier B full-set re-measurement — nmfp Rule D SHIPPED (+25 TP, zero new FP)

**Date:** 2026-07-04  **Verdict: SHIPPED** — `addon_links.rule_d` (`t_emb: 0.75`, both-convention
embedding merge) enabled after a full-frozen-set proof: **recall 41.8% → 43.4%** (v1 labels) at
**absolute fp = 9** (zero new false merges), 43.5% at fp = 6 on the corrected v2 label set.
This re-opens and lands the Tier B path that TIER_B_EMBED_REPORT.md rejected on 2026-07-03.

## Why the Tier B rejection was re-opened (the two findings)

### Finding 1 — 3 of the frozen fp=9 were label errors; the real FP count was 6

The 9 frozen FPs include LB4642/LB9900 (corr 0.950), LB6825/LB9180 (corr 0.942),
LB3431/LB3455 (corr 0.926) — all flagged `label_suspect=1` by Tier B's own scan. They are
physically the same recording; the matcher merges them correctly. A third of the defended fp
budget was phantom, and these were the only frozen negatives ever seen above nmfp 0.605.

Shipped as `regression_set_v2.json` (v1 untouched/frozen; `regression.py score --set` added):
v2 baseline fp=6, precision 99.1%. Continuity gating stays on v1 (abs fp ≤ 9); v2 is the
honesty gate (abs fp ≤ 6). Rule D passes both.

### Finding 2 — the gap gate tested the wrong operating mode, and the decisive measurement was deferred

The spec gate `p10(TP) − p90(TN) ≥ 0.10` tests lone-merge *distribution* separation (the
triplet failure mode). nmfp was always a high-bar precision-first signal; the operative
quantity is the absolute-FP curve at threshold T over all 1,390 frozen negatives **through
transitive clustering**. TIER_B_EMBED_REPORT.md said verbatim that this measurement was
"deferred (the strict gate having failed, spec says stop Tier B)". Additionally, even a gate
PASS would have shipped nmfp behind Rule C, whose conjunctive legs were already dead (flaw
coverage ~5% of FN, stationarity rejected) — pass or fail, nmfp had no viable wired path.

## The measurement (2026-07-04)

- **Embedding:** all sources in frozen negatives ∪ corr<0.05 FN = 2,467; 2,465 embedded
  (2 folders absent), nmfp-triplet/ckpt-100, 5×60 s excerpts, `embed_cache/`.
  Worklist tooling: `build_fullset_worklist.py`, `nmfp_embed.py --eval-set`.
- **Scoring:** all 2,245 frozen pairs (1,390 neg + 855 corr<0.05 FN), both conventions
  (`emb_tol2` aligned ±2 s, `emb_tol0` global) — `emb_score_pairs.py` →
  `fullset_pairs_scores.json`.
- **Sweep:** `emb_fullset_eval.py`, pre-registered grid T ∈ {0.55…0.90, step 0.025} × 3
  variants, scored through `cluster_verdicts` with **absolute** post-transitive fp counting,
  acceptance-checked byte-identical to `score --cached` on both label sets before any
  injection (tp=659 fn=916 fp=9 / tp=662 fp=6 — MATCH).

### Results (after self-pair fix, v1 labels)

| T | lone fp / flips | both_tol fp / flips | dur fp / flips |
|---|---|---|---|
| 0.550 | 104 / 109 | 48 / 60 | 94 / 92 |
| 0.650 | 43 / 71 | 22 / 36 | 41 / 60 |
| 0.700 | 14 / 63 | 11 / 27 | 13 / 53 |
| **0.725** | 11 / 58 | **9 / 25** | 11 / 49 |
| 0.750–0.850 | 10 / 55–50 | **9 / 25** | 10 / 47–44 |
| 0.900 | 10 / 43 | 9 / 22 | 10 / 36 |

- **`both_tol` (emb_tol2 ≥ T AND emb_tol0 ≥ T) holds absolute fp = 9 — zero new FP — from
  T = 0.725 through 0.90, recovering 25 FN.** Identical result at fp = 6 under v2. Shipped
  at **0.75** (one step of margin from the 0.700 cliff, abs fp = 11).
- **`lone` (aligned-only) REJECTED:** floor abs fp = 10 at every T ≤ 0.90 — including a pure
  transitive FP (LB-789/LB-2898, own score 0.487, merged through a chain) — the
  guard-masking trap observed live. The both-convention requirement is what kills it.
- Pre-registered predictions: P1 (genuine TN cap ≤ ~0.65) **failed** — the pilot found 5/300
  genuine negatives above 0.65 (max 0.680), and the full set has a long tail; the Tier B
  59-negative eval subset materially underestimated it. P2 (≥50 flips at fp-safe T) **not
  met** (25); kill condition (<15) **not triggered**. Outcome: marginal-positive, shipped
  per the precision-first standing rule (+25 TP at zero FP cost; for scale, the entire
  7-round recall-recovery effort netted +37 TP).
- Flip quality: 23/25 recovered pairs have BOTH conventions ≥ 0.90 (nmfp's same-lineage
  band); 1/25 census-flagged (duration mismatch 1.40 — consistent with an incomplete
  transfer; entered transitively). None of the 25 are on the control dates.

### Artifacts found during measurement

- **Self-pair LB-3164/LB-3164 (1988-09-23)**, a frozen negative of one LB# against itself:
  union-find marks any self-pair same-family trivially, and the LB-keyed embed cache scores
  it 1.0 against itself. Excluded from candidate links and verdict-inherits its stored value
  everywhere (sweep + regression passthrough extension). It is unmeasurable by this signal.
- **Metric-replay is NOT authoritative for historical dates:** force-recomputing the 726
  emb-scored dates from stored metrics (instead of stored-verdict passthrough) collapses the
  baseline tp 659 → 512 (−147 stored merges that current metric replay cannot reproduce).
  Hence the shipped scoring semantics: on passthrough dates, Rule D is **strictly additive**
  — union-find over {stored SAME_FAMILY edges} ∪ {Rule D links}
  (`regression.py:_passthrough_with_rule_d`). Baseline is preserved exactly by construction.

## Shipped state

- `pairs.emb_score` / `pairs.emb_score_global` (REAL, nullable, idempotent ALTER in
  `tapematch_session.py`); populated for 2,240 frozen pairs by `persist_emb_scores.py`
  (verified read-back via `latest_pairs`). NULL = not measured; Rule D abstains.
- `verdict.py:_rule_d_emb_both` — fires iff cross-source AND both conventions ≥ `t_emb`.
- `config.yaml addon_links.rule_d: enabled: true, t_emb: 0.75`.
- Tests: 177 pass in `test_verdict_equivalence.py` incl. 3 new Rule-D cases (dormant
  byte-identical, NULL abstain, self-pair never links).
- **Proof:** `score --cached` candidate tp=684 fn=891 fp=9 tn=1381 (43.4% / 98.7%);
  `--set regression_set_v2.json` tp=687 fp=6 (43.5% / 99.1%). emb coverage of remaining FN:
  92.6% (vs 4.8% for every Tier A signal).
- **Control dates (1991-02-10, 1990-06-01, 1996-07-21, 1998-10-28): PASS.** Live re-run
  (recomputed, Rule D enabled) is byte-identical to baseline on all 31 frozen pairs:
  tp=3 fn=2 fp=3 tn=23 both sides, zero verdict changes, "new FP: none". As predicted:
  none of the 25 Rule-D flips are on these dates, and live runs insert NULL emb rows so
  Rule D abstains (caveat 1). The 3 baseline FPs here (1990-06-01) merge via fp_score
  regardless of Rule D. Log: `calib_logs/control_dates_ruled.log`.

## Caveats / follow-ups (TODOs filed)

1. ~~Live sessions do not compute embeddings~~ **RESOLVED 2026-07-04 (TODO-200 Done):**
   `emb_live.py` hooks after `insert_pairs` — cache hits score directly, misses subprocess
   into `.venv-nmfp`, any failure leaves NULL (Rule D abstains). Gated by
   `rule_d.live_embed`. Verified live on 1998-10-28 (run 20260704_171831): all 10 fresh
   rows carry emb scores, zero frozen-verdict changes.
2. **Label census (report-only):** 265/855 (31.0%) of remaining corr<0.05 FN carry objective
   label-noise markers (128 explicit "different recording" curator text, 162 duration >15%
   off, 25 overlap) — `fn_label_census.py`. Curator review TODO filed; no labels edited
   beyond the 3 machine-provable v2 flips.
3. ~~Densification (12×60 s excerpts) could lift the zero-FP recovery above 25 (Tier B's
   sparse-excerpt TP-tail artifact); priced but not run.~~ **RESOLVED 2026-07-05 (TODO-202
   Done): run in full and REJECTED — see "Densification probe" section below.**

## Densification probe (TODO-202, 2026-07-05) — gate NOT cleared, 5× kept

**What ran.** Full-population 12×60 s re-embed of the FN+neg source population
(`nmfp_embed.py --n-excerpts 12 --cache embed_cache_12x`, ~8.5 h: 1942 extracted +
523 pilot cache hits; 2 sources absent from my_collection — LB14682 1988-09-22,
LB2147 1989-06-28), rescored `fullset_pairs.json` → `fullset_pairs_12x_scores.json`,
swept via `emb_fullset_eval.py` against v1 and v2 labels. Logs:
`logs/densification_12x_20260704_2028.log`, `logs/fullset_eval_12x_{v1,v2}.log`.

**Result (both_tol, the shipped rule shape).** Plateau structure reproduces at 12×
but shifted one step down: 0.750–0.825 gives exactly **25 flips** (= shipped 5×, zero
improvement) at baseline fp (9 v1 / 6 v2); the plateau edge **0.725 gives 26 flips** at
baseline fp; the FP cliff is at 0.700 (v1 fp 12, v2 fp 9). Pilot's genuine-TN
both-conv max 0.704 held on the full negative population.

**Gate reading.** Pre-registered bar: flips > 25 at abs fp ≤ 9 (v1) AND ≤ 6 (v2).
The only qualifying cell is both_tol T=0.725 — the plateau edge, one step from the
0.700 cliff, i.e. the exact margin position the 5× calibration refused when it chose
0.75 ("one-step margin from the 0.700 cliff", config.yaml rule_d comment). At every
margin-respecting threshold, 12× is a wash.

**Churn at 0.725 (why the +1 is worse than it looks).** Three shipped recoveries
would REGRESS: LB-859/2281 (12× global-conv 0.7096 < bar), LB-4428/7275 (aligned
score collapsed 1.000 → 0.510 under densification — the 5× near-1.0 was itself an
excerpt-sampling artifact), LB-4428/7302 (transitive casualty of the former). Four
gains: LB-576/9116 (0.844/0.921) + 2 transitive (LB-576/3274, LB-576/4527), and
LB-4351/6518 at 0.7401 — only 0.015 above the bar. Net +1 labeled TP.

**Hypothesis verdict.** Tier B's sparse-excerpt-artifact theory is falsified as a
broad effect: no TP-tail lift at 12× (fn_lowcorr median emb_tol2 0.416); densification
moves individual pairs in BOTH directions.

**Decision: keep 5× / t_emb 0.75.** Net +1 TP does not buy plateau-edge operation,
3 production regressions, a cache/persist migration, and a permanent ~2.4× live-session
embed cost. `embed_cache_12x/` and `fullset_pairs_12x_scores.json` are retained (the
TODO-204 near-miss-band probe can reuse them as a second measurement).

**Tooling fix (BUG-237).** `emb_fullset_eval.py`'s acceptance check went stale when
Rule D shipped: the sweep's baseline is deliberately the pre-Rule-D system (candidates
REPLACE Rule D, keeping flip counts comparable with the shipped +25), but the check
compared it against `score --cached` semantics, which now union `_passthrough_with_rule_d`
— a guaranteed 25-TP false MISMATCH. The reference now strips `rule_d` (identity
re-proven exactly: tp=659 fn=916 fp=9 tn=1381 v1 / tp=662 fp=6 v2) and prints the
shipped rule_d-on confusion alongside with the ship bar.

## Reproduce

```
.venv/bin/python3 tools/tapematch/build_fullset_worklist.py
tools/tapematch/.venv-nmfp/bin/python tools/tapematch/nmfp_embed.py --eval-set tools/tapematch/fullset_sources.json
.venv/bin/python3 tools/tapematch/emb_score_pairs.py tools/tapematch/fullset_pairs.json
.venv/bin/python3 tools/tapematch/emb_fullset_eval.py                # sweep, v1
.venv/bin/python3 tools/tapematch/emb_fullset_eval.py --set tools/tapematch/regression_set_v2.json
.venv/bin/python3 tools/tapematch/persist_emb_scores.py
.venv/bin/python3 tools/tapematch/regression.py score --cached       # proof
```
