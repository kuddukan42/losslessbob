# False-merge census — LB says different, tapematch merged (TODO-336)

Population: **78 pairs** across **55 dates** where `lb_says_same=0` but the latest run said `same_family`.

Metadata only — no audio decoded. Mechanism is attributed by replaying the shipped `config.yaml` through `verdict.link_mechanism`, so it reflects TODAY's config, not necessarily the calibration era each row was run under (TODO-333). Regenerate with `.venv/bin/python3 tools/tapematch/census_false_merge.py`.


## Work queues

| Queue | Pairs | Share |
|---|---:|---:|
| `lb_error_candidate` | 15 | 19.2% |
| `weak_link` | 20 | 25.6% |
| `chained` | 43 | 55.1% |

`lb_error_candidate` = links on primary corr ≥ `match.cluster_threshold` (0.45); `weak_link` = links on a secondary/fingerprint/addon leg below it; `chained` = no direct leg fires under today's config, so the family edge came through a third source.


## Denial scope — is the curator actually disputing THIS pair?

`lb_says_same=0` is set when a `_DIFF_RE` phrase appears anywhere in a ±250-character window around a mention of the other side's LB number. When that phrase is immediately followed by a THIRD LB number, the curator was denying a different match and this pair was caught by proximity — such a row is not evidence against the matcher.

| Queue | pair_scoped | third_party |
|---|---:|---:|
| `lb_error_candidate` | 11 | 4 |
| `weak_link` | 13 | 7 |
| `chained` | 33 | 10 |
| **all** | 57 | 21 |

## Link mechanism

| Mechanism | Pairs |
|---|---:|
| `(none — chained)` | 43 |
| `primary` | 15 |
| `fingerprint_staircase` | 10 |
| `windowed` | 6 |
| `rule_d` | 2 |
| `fingerprint` | 2 |

## Correlation distribution

| corr band | Pairs |
|---|---:|
| < 0.05 | 32 |
| 0.05–0.20 | 28 |
| 0.20–0.45 | 3 |
| 0.45–0.75 | 0 |
| ≥ 0.75 | 15 |

## Dates by pair count

| Date | Pairs | Already in TODO |
|---|---:|---|
| 1997-10-05 | 6 | — |
| 2007-04-08 | 4 | 319 |
| 1990-06-01 | 3 | 325 |
| 1997-12-11 | 3 | — |
| 1999-07-10 | 3 | — |
| 1999-10-26 | 3 | 319 |
| 2009-04-11 | 3 | — |
| 1994-07-10 | 2 | — |
| 1997-12-18 | 2 | 319 |
| 1999-03-02 | 2 | — |
| 2000-06-18 | 2 | — |
| 2011-10-21 | 2 | 319 |
| 1974-01-06 | 1 | — |
| 1974-01-11 | 1 | — |
| 1974-01-16 | 1 | — |
| 1974-01-17 | 1 | — |
| 1974-01-19 | 1 | — |
| 1988-08-26 | 1 | — |
| 1990-08-24 | 1 | — |
| 1991-07-20 | 1 | — |

## Queue `lb_error_candidate` (15 pairs)

Listen to these. Primary correlation is decisive, so either the waveform match is real and the LB pages need a catalogue correction, or the pair identity itself is wrong (BUG-277 folder collisions).

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1974-01-11 | LB-2652/LB-9316 | 0.9819 | `primary` | pair_scoped | aligned/reference | — |
| 1974-01-16 | LB-2655/LB-9328 | 0.9781 | `primary` | pair_scoped | reference/aligned | — |
| 1974-01-17 | LB-2663/LB-9330 | 0.9894 | `primary` | pair_scoped | reference/speed-unknown | — |
| 1974-01-19 | LB-2664/LB-9334 | 0.9638 | `primary` | pair_scoped | speed-unknown/speed-unknown | — |
| 1988-08-26 | LB-4642/LB-9900 | 0.9497 | `primary` | third_party | reference/aligned | — |
| 1991-07-20 | LB-6825/LB-9180 | 0.9437 | `primary` | third_party | aligned/reference | — |
| 1993-08-28 | LB-5903/LB-7173 | 1.0000 | `primary` | pair_scoped | reference/aligned | — |
| 1994-10-28 | LB-3431/LB-3455 | 0.9256 | `primary` | pair_scoped | aligned/reference | — |
| 1998-06-28 | LB-5160/LB-15721 | 0.8177 | `primary` | pair_scoped | speed-unknown/staircase/splice | — |
| 2000-06-17 | LB-6544/LB-8768 | 0.9891 | `primary` | third_party | aligned/reference | — |
| 2002-10-12 | LB-4615/LB-8387 | 0.9804 | `primary` | third_party | reference/speed-unknown | — |
| 2003-08-09 | LB-1416/LB-4587 | 0.8948 | `primary` | pair_scoped | staircase/splice/reference | — |
| 2003-10-12 | LB-1291/LB-11725 | 0.8372 | `primary` | pair_scoped | aligned/reference | — |
| 2008-09-06 | LB-6481/LB-6605 | 0.9488 | `primary` | pair_scoped | staircase/splice/staircase/splice | — |
| 2012-07-16 | LB-10308/LB-10834 | 0.9815 | `primary` | pair_scoped | speed-unknown/reference | — |

## Queue `weak_link` (20 pairs)

Do NOT adjudicate by hand yet — re-run this census after a TODO-325 floor ships. A floor that clears these without costing frozen-set true positives is a floor worth shipping.

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1974-01-06 | LB-2638/LB-9314 | 0.0115 | `windowed` | pair_scoped | speed-unknown/speed-unknown | — |
| 1990-08-24 | LB-2519/LB-12628 | 0.0349 | `rule_d` | pair_scoped | staircase/splice/reference | — |
| 1994-07-10 | LB-2984/LB-10896 | 0.0967 | `fingerprint_staircase` | pair_scoped | reference/staircase/splice | — |
| 1995-03-31 | LB-1884/LB-10825 | 0.2391 | `fingerprint` | pair_scoped | reference/staircase/splice | — |
| 1995-05-26 | LB-5362/LB-12175 | 0.1976 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 1997-04-13 | LB-3055/LB-7130 | 0.0635 | `fingerprint_staircase` | pair_scoped | staircase/splice/constant-speed-offset | — |
| 1997-10-05 | LB-8265/LB-11619 | 0.0512 | `fingerprint_staircase` | third_party | staircase/splice/speed-unknown | — |
| 1997-11-09 | LB-4349/LB-7720 | 0.0785 | `fingerprint_staircase` | pair_scoped | staircase/splice/staircase/splice | — |
| 1999-03-02 | LB-4597/LB-4960 | 0.2571 | `fingerprint_staircase` | pair_scoped | speed-unknown/staircase/splice | — |
| 1999-03-02 | LB-4960/LB-12180 | 0.1660 | `fingerprint_staircase` | third_party | staircase/splice/speed-unknown | — |
| 1999-05-01 | LB-6417/LB-6421 | 0.4338 | `windowed` | third_party | reference/speed-unknown | — |
| 1999-09-11 | LB-2007/LB-7091 | 0.1513 | `windowed` | pair_scoped | staircase/splice/reference | — |
| 1999-11-09 | LB-2737/LB-4289 | 0.1014 | `rule_d` | third_party | speed-unknown/speed-unknown | — |
| 2000-09-20 | LB-20/LB-1494 | 0.1252 | `windowed` | pair_scoped | staircase/splice/aligned | — |
| 2000-09-25 | LB-34/LB-1897 | 0.1695 | `fingerprint` | pair_scoped | speed-unknown/reference | — |
| 2005-03-16 | LB-2547/LB-11917 | 0.1545 | `windowed` | third_party | staircase/splice/reference | — |
| 2007-04-08 | LB-4686/LB-5354 | 0.0932 | `fingerprint_staircase` | third_party | reference/staircase/splice | 319 |
| 2009-04-11 | LB-7398/LB-11013 | 0.0957 | `fingerprint_staircase` | third_party | staircase/splice/staircase/splice | — |
| 2010-03-24 | LB-8498/LB-15001 | 0.0533 | `fingerprint_staircase` | pair_scoped | aligned/staircase/splice | — |
| 2011-06-22 | LB-9445/LB-9462 | 0.1099 | `windowed` | pair_scoped | reference/aligned | — |

## Queue `chained` (43 pairs)

Transitive merges: the family edge is a property of the chain, not of this pair. TODO-319's territory.

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1990-06-01 | LB-4200/LB-12552 | 0.0019 | `—` | pair_scoped | reference/speed-unknown | 325 |
| 1990-06-01 | LB-4200/LB-12884 | 0.0028 | `—` | pair_scoped | reference/speed-unknown | 325 |
| 1990-06-01 | LB-12552/LB-12884 | 0.0017 | `—` | third_party | speed-unknown/speed-unknown | 325 |
| 1994-07-10 | LB-5357/LB-10896 | 0.1106 | `—` | pair_scoped | staircase/splice/staircase/splice | — |
| 1994-07-19 | LB-789/LB-2898 | 0.0199 | `—` | pair_scoped | staircase/splice/speed-unknown | — |
| 1995-07-03 | LB-3831/LB-5691 | 0.1142 | `—` | pair_scoped | staircase/splice/aligned | — |
| 1995-12-09 | LB-6083/LB-6104 | 0.0063 | `—` | pair_scoped | constant-speed-offset/reference | — |
| 1995-12-14 | LB-6098/LB-13972 | 0.0032 | `—` | pair_scoped | reference/speed-unknown | — |
| 1996-07-10 | LB-6278/LB-6283 | 0.1453 | `—` | pair_scoped | aligned/aligned | — |
| 1997-04-28 | LB-1998/LB-13868 | 0.0578 | `—` | pair_scoped | speed-unknown/staircase/splice | — |
| 1997-08-13 | LB-4365/LB-9097 | 0.0198 | `—` | pair_scoped | speed-unknown/staircase/splice | — |
| 1997-10-01 | LB-4520/LB-5576 | 0.1262 | `—` | pair_scoped | constant-speed-offset/aligned | — |
| 1997-10-05 | LB-6424/LB-6434 | 0.0330 | `—` | pair_scoped | aligned/speed-unknown | — |
| 1997-10-05 | LB-6424/LB-8265 | 0.1010 | `—` | pair_scoped | aligned/staircase/splice | — |
| 1997-10-05 | LB-6424/LB-11619 | 0.0639 | `—` | third_party | aligned/speed-unknown | — |
| 1997-10-05 | LB-6434/LB-8265 | 0.0315 | `—` | pair_scoped | speed-unknown/staircase/splice | — |
| 1997-10-05 | LB-6434/LB-11619 | 0.0161 | `—` | third_party | speed-unknown/speed-unknown | — |
| 1997-12-11 | LB-5243/LB-6593 | 0.0053 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1997-12-11 | LB-5243/LB-7305 | 0.0137 | `—` | third_party | speed-unknown/speed-unknown | — |
| 1997-12-11 | LB-6593/LB-7305 | 0.0145 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1997-12-17 | LB-4932/LB-15184 | 0.0037 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1997-12-18 | LB-7641/LB-14205 | 0.1358 | `—` | pair_scoped | speed-unknown/aligned | 319 |
| 1997-12-18 | LB-7643/LB-14205 | 0.0830 | `—` | pair_scoped | speed-unknown/aligned | 319 |
| 1998-05-23 | LB-4648/LB-12940 | 0.0034 | `—` | pair_scoped | speed-unknown/staircase/splice | — |
| 1999-07-10 | LB-890/LB-10665 | 0.0129 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1999-07-10 | LB-890/LB-15723 | 0.0210 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1999-07-10 | LB-10665/LB-15723 | 0.0058 | `—` | third_party | speed-unknown/speed-unknown | — |
| 1999-10-26 | LB-3743/LB-8007 | 0.0582 | `—` | pair_scoped | reference/speed-unknown | 319 |
| 1999-10-26 | LB-3743/LB-11417 | 0.0465 | `—` | pair_scoped | reference/speed-unknown | 319 |
| 1999-10-26 | LB-8007/LB-11417 | 0.0365 | `—` | third_party | speed-unknown/speed-unknown | 319 |
| 1999-11-14 | LB-870/LB-12807 | 0.1242 | `—` | pair_scoped | reference/speed-unknown | — |
| 2000-06-18 | LB-5/LB-6549 | 0.0129 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 2000-06-18 | LB-2135/LB-6549 | 0.0057 | `—` | pair_scoped | reference/speed-unknown | — |
| 2000-06-21 | LB-1373/LB-6558 | 0.1074 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 2000-11-18 | LB-3275/LB-3585 | 0.0030 | `—` | pair_scoped | speed-unknown/reference | — |
| 2007-04-08 | LB-4687/LB-5354 | 0.0958 | `—` | third_party | staircase/splice/staircase/splice | 319 |
| 2007-04-08 | LB-4900/LB-5354 | 0.0444 | `—` | pair_scoped | staircase/splice/staircase/splice | 319 |
| 2007-04-08 | LB-4910/LB-5354 | 0.0399 | `—` | third_party | speed-unknown/staircase/splice | 319 |
| 2007-05-05 | LB-4941/LB-5297 | 0.0310 | `—` | third_party | speed-unknown/speed-unknown | — |
| 2009-04-11 | LB-7377/LB-11013 | 0.0291 | `—` | pair_scoped | reference/staircase/splice | — |
| 2009-04-11 | LB-7684/LB-11013 | 0.0325 | `—` | third_party | staircase/splice/staircase/splice | — |
| 2011-10-21 | LB-9676/LB-9691 | 0.0311 | `—` | pair_scoped | staircase/splice/staircase/splice | 319 |
| 2011-10-21 | LB-9680/LB-9691 | 0.0410 | `—` | pair_scoped | reference/staircase/splice | 319 |

## Re-run after the 0.05 floor (2026-10-19, TODO-336)

Replayed the 41 direct-leg (`weak_link`) pairs from the 2026-09-03 queue against the
current `observations.db` + shipped config (`fingerprint_primary_floor: 0.05`). Population
fell 114 -> 78 pairs; queues now 15 / 20 / 43 (`lb_error_candidate` / `weak_link` / `chained`).

| Outcome of the original 41 | Pairs |
|---|---:|
| Still link on a direct leg | 20 |
| Now `chained` (no direct leg; reached family transitively) | 5 |
| Left the population (no longer `same_family`) | 16 |

| Mechanism (original -> now) | Still linking |
|---|---:|
| fingerprint_staircase -> fingerprint_staircase | 10 of 21 |
| windowed -> windowed | 6 of 6 |
| fingerprint -> fingerprint | 2 of 13 |
| fingerprint -> rule_d | 1 |
| rule_d -> rule_d | 1 of 1 |

Reading: the floor clears fingerprint links almost entirely (13 -> 2 + 1 re-attributed to
rule_d) and about half the staircase links; `windowed` and `rule_d` legs are untouched by it,
so those 8 plus 10 staircase pairs need a separate corroboration gate. The 5 newly chained
(1990-06-01 x2, 1997-08-13, 2007-04-08, 2009-04-11) are TODO-319's, not pairwise-fixable.
No new direct-leg pairs appeared. Per-pair data: `data/tapematch/false_merge_queue.json`.
