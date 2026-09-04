# False-merge census — LB says different, tapematch merged (TODO-336)

Population: **114 pairs** across **76 dates** where `lb_says_same=0` but the latest run said `same_family`.

Metadata only — no audio decoded. Mechanism is attributed by replaying the shipped `config.yaml` through `verdict.link_mechanism`, so it reflects TODAY's config, not necessarily the calibration era each row was run under (TODO-333). Regenerate with `.venv/bin/python3 tools/tapematch/census_false_merge.py`.


## Work queues

| Queue | Pairs | Share |
|---|---:|---:|
| `lb_error_candidate` | 14 | 12.3% |
| `weak_link` | 41 | 36.0% |
| `chained` | 59 | 51.8% |

`lb_error_candidate` = links on primary corr ≥ `match.cluster_threshold` (0.45); `weak_link` = links on a secondary/fingerprint/addon leg below it; `chained` = no direct leg fires under today's config, so the family edge came through a third source.


## Denial scope — is the curator actually disputing THIS pair?

`lb_says_same=0` is set when a `_DIFF_RE` phrase appears anywhere in a ±250-character window around a mention of the other side's LB number. When that phrase is immediately followed by a THIRD LB number, the curator was denying a different match and this pair was caught by proximity — such a row is not evidence against the matcher.

| Queue | pair_scoped | third_party |
|---|---:|---:|
| `lb_error_candidate` | 10 | 4 |
| `weak_link` | 31 | 10 |
| `chained` | 43 | 16 |
| **all** | 84 | 30 |

## Link mechanism

| Mechanism | Pairs |
|---|---:|
| `(none — chained)` | 59 |
| `fingerprint_staircase` | 21 |
| `primary` | 14 |
| `fingerprint` | 13 |
| `windowed` | 6 |
| `rule_d` | 1 |

## Correlation distribution

| corr band | Pairs |
|---|---:|
| < 0.05 | 66 |
| 0.05–0.20 | 31 |
| 0.20–0.45 | 3 |
| 0.45–0.75 | 0 |
| ≥ 0.75 | 14 |

## Dates by pair count

| Date | Pairs | Already in TODO |
|---|---:|---|
| 1997-10-05 | 6 | — |
| 1999-03-02 | 5 | — |
| 2007-04-08 | 4 | 319 |
| 2009-04-11 | 4 | — |
| 1990-06-01 | 3 | 325 |
| 1995-05-26 | 3 | — |
| 1997-10-03 | 3 | — |
| 1997-12-11 | 3 | — |
| 1999-07-10 | 3 | — |
| 1999-10-26 | 3 | 319 |
| 2002-04-28 | 3 | 319 |
| 2010-03-24 | 3 | — |
| 1994-07-10 | 2 | — |
| 1997-04-13 | 2 | — |
| 1997-12-18 | 2 | 319 |
| 1998-06-27 | 2 | — |
| 2000-06-18 | 2 | — |
| 2010-03-23 | 2 | — |
| 2011-10-21 | 2 | 319 |
| 1971-08-01 | 1 | — |

## Queue `lb_error_candidate` (14 pairs)

Listen to these. Primary correlation is decisive, so either the waveform match is real and the LB pages need a catalogue correction, or the pair identity itself is wrong (BUG-277 folder collisions).

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1974-01-11 | LB-2652/LB-9316 | 0.9819 | `primary` | pair_scoped | aligned/reference | — |
| 1974-01-16 | LB-2655/LB-9328 | 0.9781 | `primary` | pair_scoped | reference/aligned | — |
| 1974-01-17 | LB-2663/LB-9330 | 0.9894 | `primary` | pair_scoped | reference/speed-unknown | — |
| 1974-01-19 | LB-2664/LB-9334 | 0.9638 | `primary` | pair_scoped | speed-unknown/speed-unknown | — |
| 1988-08-26 | LB-4642/LB-9900 | 0.9497 | `primary` | third_party | reference/aligned | — |
| 1991-07-20 | LB-6825/LB-9180 | 0.9437 | `primary` | third_party | aligned/reference | — |
| 1994-10-28 | LB-3431/LB-3455 | 0.9256 | `primary` | pair_scoped | aligned/reference | — |
| 1998-06-28 | LB-5160/LB-15721 | 0.8177 | `primary` | pair_scoped | speed-unknown/staircase/splice | — |
| 2000-06-17 | LB-6544/LB-8768 | 0.9891 | `primary` | third_party | aligned/reference | — |
| 2002-10-12 | LB-4615/LB-8387 | 0.9804 | `primary` | third_party | reference/speed-unknown | — |
| 2003-08-09 | LB-1416/LB-4587 | 0.8948 | `primary` | pair_scoped | staircase/splice/reference | — |
| 2003-10-12 | LB-1291/LB-11725 | 0.8372 | `primary` | pair_scoped | aligned/reference | — |
| 2008-09-06 | LB-6481/LB-6605 | 0.9488 | `primary` | pair_scoped | staircase/splice/staircase/splice | — |
| 2012-07-16 | LB-10308/LB-10834 | 0.9815 | `primary` | pair_scoped | speed-unknown/reference | — |

## Queue `weak_link` (41 pairs)

Do NOT adjudicate by hand yet — re-run this census after a TODO-325 floor ships. A floor that clears these without costing frozen-set true positives is a floor worth shipping.

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1971-08-01 | LB-3504/LB-9568 | 0.0034 | `fingerprint` | pair_scoped | constant-speed-offset/speed-unknown | — |
| 1974-01-06 | LB-2638/LB-9314 | 0.0115 | `windowed` | pair_scoped | speed-unknown/speed-unknown | — |
| 1974-01-31 | LB-2698/LB-11624 | 0.0011 | `fingerprint` | pair_scoped | speed-unknown/speed-unknown | — |
| 1978-06-16 | LB-651/LB-6554 | 0.0047 | `fingerprint` | pair_scoped | speed-unknown/speed-unknown | — |
| 1978-11-11 | LB-2888/LB-5299 | 0.0029 | `fingerprint` | pair_scoped | speed-unknown/speed-unknown | — |
| 1980-05-03 | LB-953/LB-8400 | 0.0040 | `fingerprint` | pair_scoped | aligned/speed-unknown | — |
| 1984-07-08 | LB-5697/LB-13883 | 0.0054 | `fingerprint` | pair_scoped | speed-unknown/speed-unknown | — |
| 1987-09-30 | LB-792/LB-6050 | 0.0096 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 1988-09-23 | LB-267/LB-3164 | 0.0046 | `fingerprint` | pair_scoped | aligned/speed-unknown | — |
| 1990-06-01 | LB-4200/LB-12552 | 0.0019 | `fingerprint` | pair_scoped | reference/speed-unknown | 325 |
| 1990-06-01 | LB-4200/LB-12884 | 0.0028 | `fingerprint` | pair_scoped | reference/speed-unknown | 325 |
| 1990-08-24 | LB-2519/LB-12628 | 0.0349 | `fingerprint` | pair_scoped | staircase/splice/reference | — |
| 1994-07-10 | LB-2984/LB-10896 | 0.0967 | `fingerprint_staircase` | pair_scoped | reference/staircase/splice | — |
| 1995-03-31 | LB-1884/LB-10825 | 0.2391 | `fingerprint` | pair_scoped | reference/staircase/splice | — |
| 1995-05-26 | LB-5362/LB-12175 | 0.1976 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 1995-05-26 | LB-5362/LB-14741 | 0.0183 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 1995-09-23 | LB-6377/LB-10348 | 0.0016 | `fingerprint` | pair_scoped | reference/speed-unknown | — |
| 1997-04-13 | LB-3055/LB-7130 | 0.0635 | `fingerprint_staircase` | pair_scoped | staircase/splice/constant-speed-offset | — |
| 1997-08-13 | LB-4365/LB-9097 | 0.0198 | `fingerprint_staircase` | pair_scoped | speed-unknown/staircase/splice | — |
| 1997-08-18 | LB-3464/LB-8943 | 0.0494 | `fingerprint_staircase` | pair_scoped | staircase/splice/staircase/splice | — |
| 1997-10-05 | LB-8265/LB-11619 | 0.0512 | `fingerprint_staircase` | third_party | staircase/splice/speed-unknown | — |
| 1997-11-09 | LB-4349/LB-7720 | 0.0785 | `fingerprint_staircase` | pair_scoped | staircase/splice/staircase/splice | — |
| 1998-06-27 | LB-5043/LB-8586 | 0.0245 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 1999-03-02 | LB-4596/LB-4960 | 0.0358 | `fingerprint_staircase` | third_party | staircase/splice/staircase/splice | — |
| 1999-03-02 | LB-4597/LB-4960 | 0.2571 | `fingerprint_staircase` | pair_scoped | speed-unknown/staircase/splice | — |
| 1999-03-02 | LB-4960/LB-12180 | 0.1660 | `fingerprint_staircase` | third_party | staircase/splice/speed-unknown | — |
| 1999-05-01 | LB-6417/LB-6421 | 0.4338 | `windowed` | third_party | reference/speed-unknown | — |
| 1999-09-11 | LB-2007/LB-7091 | 0.1513 | `windowed` | pair_scoped | staircase/splice/reference | — |
| 1999-11-09 | LB-2737/LB-4289 | 0.1014 | `rule_d` | third_party | speed-unknown/speed-unknown | — |
| 2000-05-23 | LB-4220/LB-4572 | 0.0324 | `fingerprint_staircase` | third_party | reference/staircase/splice | — |
| 2000-09-20 | LB-20/LB-1494 | 0.1252 | `windowed` | pair_scoped | staircase/splice/aligned | — |
| 2000-09-25 | LB-34/LB-1897 | 0.1695 | `fingerprint` | pair_scoped | speed-unknown/reference | — |
| 2000-10-31 | LB-3925/LB-7170 | 0.0236 | `fingerprint_staircase` | pair_scoped | staircase/splice/speed-unknown | — |
| 2005-03-16 | LB-2547/LB-11917 | 0.1545 | `windowed` | third_party | staircase/splice/reference | — |
| 2007-04-08 | LB-4686/LB-5354 | 0.0932 | `fingerprint_staircase` | third_party | reference/staircase/splice | 319 |
| 2007-04-08 | LB-4900/LB-5354 | 0.0444 | `fingerprint_staircase` | pair_scoped | staircase/splice/staircase/splice | 319 |
| 2009-04-11 | LB-7398/LB-11013 | 0.0957 | `fingerprint_staircase` | third_party | staircase/splice/staircase/splice | — |
| 2009-04-11 | LB-7684/LB-11013 | 0.0325 | `fingerprint_staircase` | third_party | staircase/splice/staircase/splice | — |
| 2010-03-23 | LB-8494/LB-15000 | 0.0334 | `fingerprint_staircase` | pair_scoped | aligned/staircase/splice | — |
| 2010-03-24 | LB-8498/LB-15001 | 0.0533 | `fingerprint_staircase` | pair_scoped | aligned/staircase/splice | — |

_… 1 more; full list in the JSON queue file._


## Queue `chained` (59 pairs)

Transitive merges: the family edge is a property of the chain, not of this pair. TODO-319's territory.

| Date | Pair | corr | mechanism | denial scope | speed_kind a/b | TODO |
|---|---|---:|---|---|---|---|
| 1990-06-01 | LB-12552/LB-12884 | 0.0017 | `—` | third_party | speed-unknown/speed-unknown | 325 |
| 1994-07-10 | LB-5357/LB-10896 | 0.1106 | `—` | pair_scoped | staircase/splice/staircase/splice | — |
| 1994-07-19 | LB-789/LB-2898 | 0.0199 | `—` | pair_scoped | staircase/splice/speed-unknown | — |
| 1995-05-26 | LB-12175/LB-14741 | 0.0133 | `—` | pair_scoped | speed-unknown/speed-unknown | — |
| 1995-07-03 | LB-3831/LB-5691 | 0.1142 | `—` | pair_scoped | staircase/splice/aligned | — |
| 1995-12-09 | LB-6083/LB-6104 | 0.0063 | `—` | pair_scoped | constant-speed-offset/reference | — |
| 1995-12-14 | LB-6098/LB-13972 | 0.0032 | `—` | pair_scoped | reference/speed-unknown | — |
| 1996-06-17 | LB-4535/LB-5649 | 0.0402 | `—` | third_party | reference/staircase/splice | — |
| 1996-07-10 | LB-6278/LB-6283 | 0.1453 | `—` | pair_scoped | aligned/aligned | — |
| 1997-02-13 | LB-4633/LB-6009 | 0.0071 | `—` | pair_scoped | constant-speed-offset/staircase/splice | — |
| 1997-04-13 | LB-2914/LB-7130 | 0.0022 | `—` | pair_scoped | reference/constant-speed-offset | — |
| 1997-04-28 | LB-1998/LB-13868 | 0.0578 | `—` | pair_scoped | speed-unknown/staircase/splice | — |
| 1997-08-05 | LB-2958/LB-14740 | 0.0251 | `—` | pair_scoped | reference/speed-unknown | — |
| 1997-08-17 | LB-2129/LB-5761 | 0.0226 | `—` | pair_scoped | staircase/splice/staircase/splice | — |
| 1997-10-01 | LB-4520/LB-5576 | 0.1262 | `—` | pair_scoped | constant-speed-offset/aligned | — |
| 1997-10-03 | LB-5159/LB-8264 | 0.0312 | `—` | third_party | speed-unknown/aligned | — |
| 1997-10-03 | LB-6327/LB-8264 | 0.1171 | `—` | pair_scoped | aligned/aligned | — |
| 1997-10-03 | LB-6330/LB-8264 | 0.0110 | `—` | third_party | staircase/splice/aligned | — |
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
| 1998-06-27 | LB-5043/LB-5249 | 0.0178 | `—` | pair_scoped | staircase/splice/staircase/splice | — |
| 1999-03-02 | LB-4596/LB-4597 | 0.0510 | `—` | pair_scoped | staircase/splice/speed-unknown | — |
| 1999-03-02 | LB-4596/LB-12180 | 0.0315 | `—` | pair_scoped | staircase/splice/speed-unknown | — |
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
| 2001-07-25 | LB-10165/LB-10241 | 0.0458 | `—` | pair_scoped | staircase/splice/speed-unknown | — |
| 2002-04-28 | LB-292/LB-10887 | 0.0028 | `—` | pair_scoped | staircase/splice/staircase/splice | 319 |
| 2002-04-28 | LB-940/LB-10887 | 0.0130 | `—` | third_party | speed-unknown/staircase/splice | 319 |
| 2002-04-28 | LB-5434/LB-10887 | 0.0040 | `—` | third_party | speed-unknown/staircase/splice | 319 |
| 2004-11-02 | LB-4424/LB-7133 | 0.0965 | `—` | third_party | speed-unknown/staircase/splice | — |
| 2007-04-08 | LB-4687/LB-5354 | 0.0958 | `—` | third_party | staircase/splice/staircase/splice | 319 |
| 2007-04-08 | LB-4910/LB-5354 | 0.0399 | `—` | third_party | speed-unknown/staircase/splice | 319 |
| 2007-05-05 | LB-4941/LB-5297 | 0.0310 | `—` | third_party | speed-unknown/speed-unknown | — |
| 2009-04-11 | LB-7377/LB-11013 | 0.0291 | `—` | pair_scoped | reference/staircase/splice | — |
| 2009-04-11 | LB-7493/LB-11013 | 0.0259 | `—` | third_party | constant-speed-offset/staircase/splice | — |
| 2010-03-23 | LB-8460/LB-15000 | 0.0318 | `—` | pair_scoped | reference/staircase/splice | — |
| 2010-03-24 | LB-8459/LB-15001 | 0.0179 | `—` | pair_scoped | aligned/staircase/splice | — |
| 2010-03-24 | LB-8468/LB-15001 | 0.0193 | `—` | pair_scoped | reference/staircase/splice | — |
| 2011-10-21 | LB-9676/LB-9691 | 0.0311 | `—` | pair_scoped | staircase/splice/staircase/splice | 319 |
| 2011-10-21 | LB-9680/LB-9691 | 0.0410 | `—` | pair_scoped | reference/staircase/splice | 319 |
