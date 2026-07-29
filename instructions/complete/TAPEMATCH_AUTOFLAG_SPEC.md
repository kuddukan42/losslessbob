# TapeMatch Auto-Triage (rule-based flagger) — spec

*Written 2026-07-31. Status: SHIPPED 2026-07-31 (TODO-294) — see instructions/README.md for the closing note.*

## Problem

3,037 dates have a completed TapeMatch run. Only 1,397 have an `analysis.md`.
`backend/tapematch_sync.py` reads the human verdict out of that prose
(`_read_review_flag`, `tapematch_sync.py:84-96`, applied at `:315-320`), so the
1,640 un-analysed dates carry **no review signal at all** — not "clean", just
silent. At the nightly `/tapematch-batch` rate (25 dirs/night) that gap closes in
about 62 nights.

Everything else already works without the prose: `recording_families` (11,942
rows), `tapematch_family_meta` (9,100), `tapematch_pairs` (23,966) cover 3,036
dates today. The prose backlog gates the review signal and nothing else.

`tools/tapematch/triage_analysis.py` was built for the adjacent problem
(auto-*writing* trivially clean analyses) and does not help here: on the current
backlog it classifies **AUTO=0 / ESCALATE=2,344 / SKIP=174**, because 1,793 dirs
have at least one merge and merges always escalate. Leave it alone; this spec
does not modify it.

## Goal

Give every date a machine-derived triage signal computed from `observations.db`
alone, so the un-analysed 1,640 can be **prioritised** rather than treated as
uniformly unknown. Explicitly **not** a goal: replicating the human verdict, or
substituting for `analysis.md`.

## What the calibration showed

Measured against the 1,362 labelled dates (130 human-flagged / 1,232 clean —
base rate 9.5%). Signals computed from the best run per date, using the same
`_pick_best_run` rule as the sync.

| Rule | Definition | Fires on flagged | on clean | Precision | Recall |
|---|---|---|---|---|---|
| R1 contradiction | a pair with `lb_says_same=1`, `corr < 0.05`, and different `family_id` | 88 | 288 | 0.23 | 0.68 |
| R3 duration outlier | a source whose `perf_dur_sec` is <0.90× or >1.10× the date median (≥2 sources) | 60 | 255 | 0.19 | 0.46 |
| R7 all-zero multi | ≥4 sources and `max(corr) < 0.05` across every pair | 28 | 128 | 0.18 | 0.22 |
| R5 label suspect | any pair with `label_suspect=1` | 3 | 9 | 0.25 | 0.02 |
| ~~R2 low-conf merge~~ | same-family pair with `0.10 ≤ corr < 0.35` | 7 | 92 | 0.07 | 0.05 | 
| ~~R4 coverage gap~~ | `n_sources_found < n_sources_db` | 21 | 396 | 0.05 | 0.16 |
| ~~R6 staircase~~ | ≥3 segments in `lag_segments_json` | 0 | 392 | 0.00 | 0.00 |

**R2 and R4 are rejected** — both fire below the base rate, i.e. they are
anti-signals as defined. R4's failure is informative: a coverage gap on the
chosen run usually did not change the human's verdict.

**R6 is deferred, not rejected.** Segment *count* is not staircase detection;
the real discontinuity logic lives in `tools/tapematch/tapematch/cli.py` and was
never surfaced into `observations.db`. Reimplement against that logic before
judging the rule — the 0.00 above measures a bad proxy, not the signal.

### Operating point

`CORE = R1 ∨ R3 ∨ R5 ∨ R7`:

| | labelled | un-analysed |
|---|---|---|
| **attention** | 41% of dates, precision 0.19, recall 0.84 | 892 dates |
| **clear** | n=802, **97.4% were human-judged clean** | 783 dates |

Read that asymmetrically. As a flag it is weak (0.19 precision — the human
verdict leans on info-file prose the rules cannot see). As a **clear** signal it
is strong: 781 of 802 no-fire dates were judged clean, and only 18 of 130
flagged dates fire nothing. That is the value — it retires 783 un-analysed dates
to the back of the queue with a measured 2.6% miss rate, and concentrates the
remaining prose work on 892.

`CORE ≥2 rules` was also tested (flag-rate 0.18, clear purity 0.936). Prefer
plain `CORE any`: the tighter variant buys a smaller attention set at the cost of
letting 6.4% of the clear bucket be genuinely flaggable, which is the wrong
error to trade for.

## Design

### 1. New module `tools/tapematch/autoflag.py`

```python
def date_signals(obs_conn, run_id) -> set[str]:
    """Return the set of CORE rule names firing on one run."""

def triage(obs_conn) -> dict[str, tuple[str, list[str]]]:
    """Return {concert_date: (verdict, reasons)} for the best run per date,
    where verdict is 'clear' or 'attention'."""
```

Reuse `tapematch_sync._pick_best_run` — do not re-derive best-run selection, or
the triage will describe a different run than the one whose families are in the
DB. Thresholds (0.05 / 0.90 / 1.10 / 4) live in module constants, not literals.

### 2. Schema — new columns, do not overload `review_flag`

Add to `tapematch_family_meta`, via the existing `PRAGMA table_info` +
`ALTER TABLE` idiom used for `review_flag`/`review_reason`:

- `auto_triage TEXT` — `'clear'` | `'attention'` | NULL
- `auto_triage_reasons TEXT` — JSON array of fired rule names

Keep them **separate** from `review_flag`/`review_reason`. Those mean "a human
or Claude read the prose and judged this"; conflating a 0.19-precision heuristic
into the same field would silently degrade a field the Curation UI already
trusts, and make the 130 real flags unrecoverable.

### 3. Sync integration

Populate in `_sync_one_date`, alongside the existing `_read_review_flag` call
(`tapematch_sync.py:319-320`). Same uniform-per-date application as
`review_flag` — the rules judge the whole date's identity picture.

### 4. Batch queue ordering

`/tapematch-batch` step 1 currently takes the first N eligible dirs in `sort`
order. Change the ordering to: `auto_triage='attention'` first, descending by
rule count, then ascending by DB-entry count. Rationale — the backlog's entry
counts are 257 dirs at 2 entries, 371 at 3, 338 at 4, tailing to 13; cheap
attention dates should clear before expensive clean ones. `clear` dates stay
eligible, just last.

### 5. Reporting

`autoflag.py --report` prints the calibration table above regenerated from
current data, so the operating point is re-checkable as the labelled set grows
(every `/tapematch-batch` night adds ~25 labels). Re-run it after each 250 new
labels and re-tune thresholds if clear-bucket purity drops below 0.95.

## Acceptance

1. `autoflag.py --report` reproduces clear-bucket purity ≥0.97 on the labelled set.
2. All 3,037 dates in `observations.db` receive a non-NULL `auto_triage` after a sync.
3. `review_flag` counts are unchanged by the migration (130 flagged dates, verified before/after).
4. `/tapematch-batch` picks an `attention` dir first when one is eligible.

## Out of scope

- Auto-writing `analysis.md` (that is `triage_analysis.py`'s job; it is stuck at AUTO=0).
- The 783 incomplete-set + 190 no-CLUSTERS run dirs — those need source recovery, not triage.
- Surfacing `auto_triage` in the Curation UI. Worth doing, but spec it separately
  once the field has been populated and spot-checked.
