# TODO-319 — chain-clustering over-merge: replay findings (2026-10-19)

Metadata-only replay of stored pair metrics. No audio was decoded and nothing was written to
`observations.db`. Reproduce with:

```
.venv/bin/python3 tools/tapematch/chain_overmerge_replay.py \
    --density 0.5 --strong primary,rule_d,windowed,hiss,fingerprint [--json OUT]
```

Method: per date, the run the app syncs (`tapematch_sync._pick_best_run`) is replayed through
`verdict.cluster_verdicts` under the shipped `config.yaml` (which already carries the TODO-325
`fingerprint_primary_floor: 0.05`), then again with `family_guard` on. Dates whose stored
verdicts the offline model cannot reproduce under their own run config (the
`replay_writeback.py` fidelity gate) are counted, not measured: 2,926 measured, 136 fidelity
mismatches. Frozen set = `regression_set.json`, matched by `(lb_lo, lb_hi)` as `regression.py`
does.

## Does single linkage promote weak links?

Yes, but it is a minority mechanism.

| Measure (shipped config) | Count |
|---|---|
| same-family pairs | 3,244 |
| …with no direct link leg (reached transitively) | 284 (8.8%) |
| frozen TPs | 555 (520 direct, 35 chained) |
| frozen FPs | 11 (7 direct, 4 chained) |

The named dates are mostly driven by something else. Weak pairwise edges, chiefly
`fingerprint_staircase` at the ~0.42 same-show musical floor, fire *densely*: on 2007-04-08
nine of fifteen pairs link that way. A density rule cannot separate those, because the
connectivity is real at the edge level. That is pairwise territory (TODO-325/BUG-331), not a
chaining problem.

## The guard (`family_guard`, default OFF)

`verdict.form_families`: legs listed in `strong_legs` union freely. Any other leg (in practice
`fingerprint_staircase`) merges two families only when such edges cover at least
`min_link_density` of the |A|×|B| cross pairs. Merges are taken best-density first (average
linkage over the link graph). The same rule runs live (`cli.py`) and offline
(`cluster_verdicts`). In `calibration.py`, the three keys are DECISION + VERDICT_ONLY (so they
can be replayed through `replay_writeback.py`), and `family_guard` is a gated block. It is also
in the new `LATE_GATED_BLOCKS`: while the guard is off, the block adds nothing to the view, so
the shipped hash stays `f786bebf58c8` and no historical run is re-hashed.

## Sweep (frozen TP base 555 / FP 11; chained queue = TODO-336's 59 pairs)

| strong_legs | density | dates split | frozen TPs lost | frozen FPs cleared | queue still merged |
|---|---|---|---|---|---|
| primary | 0.34–0.5 | 41 | 24 | 3 | 4 |
| primary | 0.67 | 116 | 63 | 5 | 0 |
| primary, rule_d | 0.5 | 32 | 11 | 2 | 5 |
| primary, rule_d, windowed, hiss | 0.5 | 27 | 10 | 2 | 5 |
| **primary, rule_d, windowed, hiss, fingerprint** | **0.5** | **14** | **0** | **2** | **5** |
| same | 0.51–0.6 | 25 | 4 | 4 | 2 |
| same | 0.67–1.0 | 27 | 4 | 4 | 1 |

Only the bold row loses no TPs. Treating `windowed`, `rule_d` or base `fingerprint` as weak
costs real TPs, because those legs are calibrated and their chains are mostly genuine. Any
density above 0.5 starts costing TPs: 1987-10-01 602/5516 and 5516/11049, 1995-04-10
1280/15263, 2001-11-11 7717/8643.

Recommended setting (bold row): 14 dates gain 18 families, 0 frozen TPs are lost, and 2
frozen FPs are cleared (1994-07-10 5357/10896 and 2984/10896).

## TODO-336's 59 chained pairs

24 can't be measured: their date's synced run fails fidelity or isn't the latest run. 23 are
already split under the shipped config by the TODO-325 floor. Of the 12 still merged, the guard
resolves 7:

- 1994-07-10 5357/10896
- 2000-06-21 1373/6558
- 2007-04-08 4687/5354 and 4910/5354
- 2009-04-11 7377/11013
- 2011-10-21 9676/9691 and 9680/9691

Five survive:

- 1998-05-23 4648/12940 and 1999-11-14 870/12807 are exactly 1-of-2 (density 0.5).
- 1995-07-03 3831/5691 is 2-of-3.
- 1996-07-10 6278/6283 is dense `windowed`.
- 1994-07-19 789/2898 is a single `rule_d` edge into a primary family. This is the known
  LB-789/LB-2898 chain.

## Named dates (stored / shipped replay / guard family counts)

| Date | n | stored | shipped | guard | Note |
|---|---|---|---|---|---|
| 2011-10-21 | 9 | 1 | 1 | 3 | LB-09691 and LB-09679 split out (09691 = taper's "different recording") |
| 2007-04-08 | 7 | 2 | 2 | 4 | 5354 (LB says different) and {4687, 4910} split; {4686, 4701, 4900} stays on dense staircase fp |
| 2004-03-05 | 6 | 3 | 3 | 4 | LB-01632 split out, as filed |
| 2002-04-28 | 9 | 3 | 3 | 4 | 5-way family → {283, 5434} + {940, 4402, 10096} |
| 2007-04-04 | 6 | 3 | 3 | 4 | 4882 split; 6130 is still merged (partial) |
| 2010-03-23, 03-24, 03-29, 2008-06-11, 1997-12-08/10, 2024-04-06, 2003-10-17, 2003-04-19, 2004-03-01, 2004-06-08, 2004-11-13, 2009-07-05, 2011-06-26, 2012-07-03, 2000-09-20, 2002-10-11 | | = | = | = | already resolved in the stored runs (re-runs and the TODO-325 floor); guard is a no-op |
| 2010-03-28, 2009-10-10, 1997-12-18, 2001-10-12 | | | | | fidelity mismatch: the stored merge isn't reproducible from stored metrics (2010-03-28: under its own config no leg fires on the 5-way family's pairs), so these need a re-run, not a replay |

## Recommendation

Enable it as `strong_legs: [primary, windowed, hiss, fingerprint, rule_d]` and
`min_link_density: 0.5` (the values already in `config.yaml`, with `enabled: false`). It is
strictly Pareto on the frozen set (0 TPs lost, 2 FPs cleared) and splits 14 dates. To apply it
to stored runs, flip `enabled` and run `replay_writeback.py`.

This is tj's call. The guard is a narrow fix: it removes single-edge staircase-fp attachments.
It does not touch the dominant named-date failure (dense staircase fp at the musical floor) or
rule_d chains like 789/2898. Those remain pairwise problems.
