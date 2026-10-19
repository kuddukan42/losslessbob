# Series-vs-series taper conflict review (TODO-234)

**11 cases** (21 `conflict=1` rows in `taper_attributions`, all candidates formal series codes). Read-only review - nothing was split.

A case is a taper-propagation component: the conflict rows are unattributed members; the **anchors** are the confirmed members that pull in different series. Sources: app DB `data/losslessbob.db` (`taper_attributions`, `recording_families`, `tapematch_family_meta`, `entry_lineage`) and `latest_pairs` in `observations.db`; mechanism = shipped `config.yaml` replayed through `verdict.link_mechanism`. Regenerate: `.venv/bin/python3 tools/tapematch/review_series_conflicts.py`.

Calls: **KEEP** = differently-credited anchors are the same tape (curator lineage or primary-corr bridge) so one series credit is wrong - fix the attribution, not the family. **SPLIT** = anchors share a family but link only on weak legs / by chain - a TapeMatch over-merge; split via family review. **NOT-MERGE** = anchors sit in different families; the conflict arises from lineage edges (same_as/derived_from), not a TapeMatch merge - nothing to split in tapematch. **MIXED** = some anchor pairs KEEP, some not.

## Summary

| Call | Cases |
|---|---:|
| KEEP (relabel) | 3 |
| KEEP (relabel, low conf) | 1 |
| NOT-MERGE | 4 |
| SPLIT | 2 |
| SPLIT (curator disagrees) | 1 |

| Date | Anchors (LB:series) | Conflict rows | Call |
|---|---|---:|---|
| 1988-07-17 | 1297:ltg, 10935:ltc | 5 | **NOT-MERGE** |
| 1990-10-11 | 5859:lte, 13554:lta | 1 | **NOT-MERGE** |
| 1993-02-07 | 1343:ltb, 5882:lta, 12768:lta | 2 | **KEEP (relabel)** |
| 1995-03-14 | 8517:ltb, 10658:ltj | 6 | **NOT-MERGE** |
| 1995-03-16 | 556:net taper f, 1618:net taper f, 5768:net taper i | 1 | **KEEP (relabel, low conf)** |
| 1995-10-02 | 5915:lth, 6390:net taper k | 1 | **KEEP (relabel)** |
| 1995-12-09 | 6083:net taper j, 15211:lta | 1 | **SPLIT** |
| 1997-04-05 | 3344:net taper a, 8854:net taper j, 9240:net taper j | 1 | **SPLIT (curator disagrees)** |
| 1998-06-03 | 13487:lta, 13992:net taper f | 1 | **NOT-MERGE** |
| 1998-06-12 | 5800:net taper i, 6462:net taper i, 6465:net taper f | 1 | **SPLIT** |
| 2000-05-25 | 14518:ltb, 14519:net taper f | 1 | **KEEP (relabel)** |

## 1988-07-17 - NOT-MERGE

TapeMatch already has 1297 (ltg) and the 10935 family (ltc) as different_family (corr <= 0.012). The conflict is carried by curator same_as edges (1297 -> 7126/7541/14671) that waveform contradicts. Nothing to split; review the 1297 same_as edges.

Auto: NOT-MERGE - 1297/10935: different_family, no leg (corr 0.012).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 1297 | anchor | ltg | `1988-07-17#1297` | - | 0 | .shn | 4637 | speed-unknown |
| 7126 | conflict |  | `1988-07-17#7126-10937` | 0.21 | 0 | .flac | 4718 | speed-unknown |
| 7541 | conflict |  | `1988-07-17#7541-7554-10754-10935` | 0.63 | 0 | .flac | 4729 | reference |
| 7554 | conflict |  | `1988-07-17#7541-7554-10754-10935` | 0.63 | 0 | .flac | 4727 | staircase/splice |
| 10754 | conflict |  | `1988-07-17#7541-7554-10754-10935` | 0.63 | 0 | .flac | 4718 | staircase/splice |
| 10935 | anchor | ltc | `1988-07-17#7541-7554-10754-10935` | 0.63 | 0 | .flac | 4715 | staircase/splice |
| 10937 | family |  | `1988-07-17#7126-10937` | 0.21 | 0 | .flac | 4728 | speed-unknown |
| 14671 | conflict |  | `1988-07-17#14671` | - | 0 | .flac | 4850 | speed-unknown |

Lineage: 1297-7126 same_as; 1297-7541 same_as; 7126-7541 same_as; 1297-14671 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 1297-7126 | 0.003 | different_family | - | 0.46 | 0.20 | 1 |
| 1297-7541 | 0.012 | different_family | - | 0.47 | 0.43 | 1 |
| 1297-7554 | 0.012 | different_family | - | 0.47 | 0.43 | None |
| 1297-10754 | 0.010 | different_family | - | 0.47 | 0.69 | None |
| 1297-10935 | 0.012 | different_family | - | 0.47 | 0.44 | None |
| 1297-10937 | 0.002 | different_family | - | 0.46 | 0.18 | None |
| 1297-14671 | 0.003 | different_family | - | 0.45 | 0.16 | 1 |
| 7126-7541 | 0.005 | different_family | - | 0.43 | 0.11 | 1 |
| 7126-7554 | 0.005 | different_family | - | 0.43 | 0.11 | None |
| 7126-10754 | 0.003 | different_family | - | 0.43 | 0.13 | None |
| 7126-10935 | 0.004 | different_family | - | 0.43 | 0.11 | None |
| 7126-10937 | 0.163 | same_family | fingerprint | 0.52 | 0.53 | 1 |
| 7126-14671 | 0.002 | different_family | - | 0.45 | 0.09 | None |
| 7541-7554 | 1.000 | same_family | primary | - | 1.00 | 1 |
| 7541-10754 | 0.642 | same_family | primary | - | 0.74 | 1 |
| 7541-10935 | 0.886 | same_family | primary | - | 0.95 | 1 |
| 7541-10937 | 0.004 | different_family | - | 0.43 | 0.11 | None |
| 7541-14671 | 0.003 | different_family | - | 0.43 | 0.18 | 1 |
| 7554-10754 | 0.036 | same_family | windowed | 0.64 | 0.60 | None |
| 7554-10935 | 0.877 | same_family | primary | - | 0.96 | None |
| 7554-10937 | 0.004 | different_family | - | 0.43 | 0.11 | None |
| 7554-14671 | 0.003 | different_family | - | 0.43 | 0.17 | None |
| 10754-10935 | 0.033 | same_family | windowed | 0.64 | 0.58 | None |
| 10754-10937 | 0.003 | different_family | - | 0.43 | 0.11 | None |
| 10754-14671 | 0.004 | different_family | - | 0.43 | 0.19 | None |
| 10935-10937 | 0.004 | different_family | - | 0.43 | 0.13 | None |
| 10935-14671 | 0.003 | different_family | - | 0.43 | 0.18 | None |
| 10937-14671 | 0.002 | different_family | - | 0.45 | 0.09 | None |

## 1990-10-11 - NOT-MERGE

Anchor 5859 (lte) has no observation rows and no family; 166 is tied to both anchors only by same_as lineage. Taper-curation question (lte vs lta), not a family split.

Auto: NOT-MERGE - 5859/13554: no stored pair, different families.

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 166 | conflict |  | `1990-10-11#166` | - | 1 | .shn | 4134 | constant-speed-offset |
| 5859 | anchor | lte | `-` | - | - | None | - | None |
| 13554 | anchor | lta | `1990-10-11#13554` | - | 1 |  | 4041 | constant-speed-offset |

Lineage: 166-5859 same_as; 166-13554 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 166-13554 | 0.002 | different_family | - | - | 0.08 | 1 |

## 1993-02-07 - KEEP (relabel)

Core 5882/12768/16364 (lta) is primary 0.90-0.98. 1343 (ltb) joins at corr 0.29-0.32 on hiss/fingerprint, but emb 0.93-0.95 and LB says same (1343-5882). Corr is depressed by 1343's staircase/splice speed. Likely one tape with a wrong series credit.

Auto: SPLIT - 1343/5882: weak leg hiss (corr 0.324); 1343/12768: weak leg fingerprint_staircase (corr 0.292).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 1343 | anchor | ltb | `1993-02-07#1343-4216-5882-12768-16364` | 0.48 | 0 | .shn | 7498 | staircase/splice |
| 4216 | conflict |  | `1993-02-07#1343-4216-5882-12768-16364` | 0.48 | 0 | .flac | 7520 | speed-unknown |
| 5882 | anchor | lta | `1993-02-07#1343-4216-5882-12768-16364` | 0.48 | 0 | .flac | 7500 | staircase/splice |
| 12768 | anchor | lta | `1993-02-07#1343-4216-5882-12768-16364` | 0.48 | 0 | .flac | 7480 | aligned |
| 16364 | conflict |  | `1993-02-07#1343-4216-5882-12768-16364` | 0.48 | 0 | .flac | 7479 | reference |

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 1343-4216 | 0.299 | same_family | fingerprint | 0.59 | 0.32 | 1 |
| 1343-5882 | 0.324 | same_family | hiss | 0.46 | 0.95 | 1 |
| 1343-12768 | 0.292 | same_family | fingerprint_staircase | 0.45 | 0.93 | None |
| 1343-16364 | 0.286 | same_family | fingerprint | 0.63 | 0.94 | None |
| 4216-5882 | 0.084 | same_family | - | 0.44 | 0.32 | None |
| 4216-12768 | 0.111 | same_family | - | 0.46 | 0.34 | None |
| 4216-16364 | 0.121 | same_family | fingerprint | 0.53 | 0.35 | None |
| 5882-12768 | 0.903 | same_family | primary | - | 0.95 | 1 |
| 5882-16364 | 0.982 | same_family | primary | - | 0.95 | None |
| 12768-16364 | 0.924 | same_family | primary | - | 0.96 | None |

## 1995-03-14 - NOT-MERGE

ltj anchor 10658 has no family; link is lineage only (10385-10658, 8517-10387 same_as). Core 1922/2972/3483 is primary >= 0.89; 8517 (ltb) attaches weakly (fingerprint 0.33, emb 0.44-0.53) - optional split of 8517 only. 1029 same_as 3483 is contradicted by waveform (0.002) and LB (says different) - bad lineage edge.

Auto: NOT-MERGE - 8517/10658: no stored pair, different families.

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 1029 | conflict |  | `1995-03-14#1029` | - | 0 | .shn | 5636 | speed-unknown |
| 1922 | conflict |  | `1995-03-14#1922-2972-3483-8517` | 0.67 | 0 | .shn | 6004 | reference |
| 2972 | conflict |  | `1995-03-14#1922-2972-3483-8517` | 0.67 | 0 | .shn | 6004 | aligned |
| 3483 | conflict |  | `1995-03-14#1922-2972-3483-8517` | 0.67 | 0 |  | 6004 | staircase/splice |
| 8517 | anchor | ltb | `1995-03-14#1922-2972-3483-8517` | 0.67 | 0 | .flac | 6007 | staircase/splice |
| 10385 | conflict |  | `-` | - | - | None | - | None |
| 10387 | conflict |  | `-` | - | - | None | - | None |
| 10658 | anchor | ltj | `-` | - | - | None | - | None |

Lineage: 1029-3483 same_as; 1029-10385 same_as; 8517-10387 same_as; 10385-10658 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 1029-1922 | 0.003 | different_family | - | 0.29 | 0.12 | 0 |
| 1029-2972 | 0.002 | different_family | - | 0.29 | 0.12 | None |
| 1029-3483 | 0.003 | different_family | - | 0.29 | 0.12 | None |
| 1029-8517 | 0.002 | different_family | - | 0.29 | 0.12 | None |
| 1922-2972 | 0.999 | same_family | primary | - | 1.00 | 1 |
| 1922-3483 | 0.919 | same_family | primary | - | 0.99 | None |
| 1922-8517 | 0.334 | same_family | fingerprint | 0.62 | 0.53 | None |
| 2972-3483 | 0.892 | same_family | primary | - | 0.99 | 1 |
| 2972-8517 | 0.334 | same_family | fingerprint | 0.58 | 0.53 | 1 |
| 3483-8517 | 0.270 | same_family | fingerprint_staircase | 0.42 | 0.44 | None |

## 1995-03-16 - KEEP (relabel, low conf)

Family conf 0.22. 1618/3491 primary 0.89; 556 and 5768 attach on fingerprint/windowed/rule_d at corr 0.02-0.17, but emb 0.74-0.93 and LB says same for 556-5768 and 1618-5768. Listen to 5768 (net taper i) before splitting.

Auto: SPLIT - 556/5768: weak leg fingerprint_staircase (corr 0.069); 1618/5768: weak leg rule_d (corr 0.019).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 556 | anchor | net taper f | `1995-03-16#556-1618-3491-5768` | 0.22 | 0 | .shn | 5578 | staircase/splice |
| 1618 | anchor | net taper f | `1995-03-16#556-1618-3491-5768` | 0.22 | 0 | .flac | 5572 | reference |
| 3491 | conflict |  | `1995-03-16#556-1618-3491-5768` | 0.22 | 0 |  | 5572 | aligned |
| 5768 | anchor | net taper i | `1995-03-16#556-1618-3491-5768` | 0.22 | 0 | .flac | 5571 | speed-unknown |

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 556-1618 | 0.168 | same_family | fingerprint | 0.55 | 0.91 | 1 |
| 556-3491 | 0.157 | same_family | windowed | 0.55 | 0.91 | None |
| 556-5768 | 0.069 | same_family | fingerprint_staircase | 0.41 | 0.74 | 1 |
| 1618-3491 | 0.894 | same_family | primary | - | 1.00 | 1 |
| 1618-5768 | 0.019 | same_family | rule_d | 0.42 | 0.93 | 1 |
| 3491-5768 | 0.021 | same_family | rule_d | 0.42 | 0.93 | None |

## 1995-10-02 - KEEP (relabel)

Already review_flag=1, conf 0.14. 5915-6390 hiss 0.21, emb 0.79, LB says same; 3842 rides rule_d at 0.03 with emb 0.93. Weak waveform but consistent embeddings and curator commentary.

Auto: SPLIT - 5915/6390: weak leg hiss (corr 0.206).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 3842 | conflict |  | `1995-10-02#3842-5915-6390` | 0.14 | 1 |  | 6800 | aligned |
| 5915 | anchor | lth | `1995-10-02#3842-5915-6390` | 0.14 | 1 | .flac | 6804 | speed-unknown |
| 6390 | anchor | net taper k | `1995-10-02#3842-5915-6390` | 0.14 | 1 | .flac | 6800 | reference |

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 3842-5915 | 0.029 | same_family | rule_d | 0.40 | 0.93 | 1 |
| 3842-6390 | 0.033 | same_family | rule_d | 0.40 | 0.94 | None |
| 5915-6390 | 0.206 | same_family | hiss | 0.49 | 0.79 | 1 |

## 1995-12-09 - SPLIT

6083 (net taper j) vs 6104/15211 (lta): corr 0.005, no leg, emb 0.29-0.30, and LB says DIFFERENT for 6083-6104. 6104-15211 is a genuine pair (windowed 0.42, emb 0.91, LB same). Split 6083 out.

Auto: SPLIT - 6083/15211: same_family, no leg (corr 0.005).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 6083 | anchor | net taper j | `1995-12-09#6083-6104-15211` | 0.19 | 0 | .flac | 6758 | constant-speed-offset |
| 6104 | conflict |  | `1995-12-09#6083-6104-15211` | 0.19 | 0 | .flac | 6686 | reference |
| 15211 | anchor | lta | `1995-12-09#6083-6104-15211` | 0.19 | 0 |  | 6681 | staircase/splice |

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 6083-6104 | 0.006 | same_family | - | 0.41 | 0.30 | 0 |
| 6083-15211 | 0.005 | same_family | - | 0.41 | 0.29 | None |
| 6104-15211 | 0.423 | same_family | windowed | 0.64 | 0.91 | 1 |

## 1997-04-05 - SPLIT (curator disagrees)

Two tight clusters {3344,3559} (primary 0.988) and {8854,9240} (primary 0.972) bridged only by fingerprint at corr 0.02-0.24, emb 0.46-0.57. Different series credits. Curator same_as edges tie 9240 to all - listen before splitting.

Auto: MIXED - 3344/8854: same_family, no leg (corr 0.238); 3344/9240: curator lineage same_as.

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 3344 | anchor | net taper a | `1997-04-05#3344-3559-8854-9240` | 0.48 | 0 |  | 7121 | reference |
| 3559 | conflict |  | `1997-04-05#3344-3559-8854-9240` | 0.48 | 0 | .flac | 7134 | staircase/splice |
| 8854 | anchor | net taper j | `1997-04-05#3344-3559-8854-9240` | 0.48 | 0 | .flac | 7140 | constant-speed-offset |
| 9240 | anchor | net taper j | `1997-04-05#3344-3559-8854-9240` | 0.48 | 0 | .flac | 7136 | constant-speed-offset |

Lineage: 3344-9240 same_as; 3559-9240 same_as; 8854-9240 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 3344-3559 | 0.988 | same_family | primary | - | 0.60 | 1 |
| 3344-8854 | 0.238 | same_family | - | 0.50 | 0.46 | 1 |
| 3344-9240 | 0.224 | same_family | fingerprint | 0.47 | 0.46 | 1 |
| 3559-8854 | 0.117 | same_family | fingerprint | 0.51 | 0.52 | None |
| 3559-9240 | 0.023 | same_family | - | 0.47 | 0.57 | 1 |
| 8854-9240 | 0.972 | same_family | primary | - | 0.97 | 1 |

## 1998-06-03 - NOT-MERGE

Anchor 13992 (net taper f) has no family or observation rows; the contest is a 3325 same_as 13992 lineage edge. No tapematch lever.

Auto: NOT-MERGE - 13487/13992: no stored pair, different families.

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 3325 | conflict |  | `1998-06-03#3325-13487-15053` | 0.43 | 1 | .flac | 5280 | aligned |
| 13487 | anchor | lta | `1998-06-03#3325-13487-15053` | 0.43 | 1 |  | 5280 | aligned |
| 13992 | anchor | net taper f | `-` | - | - | None | - | None |
| 15053 | family |  | `1998-06-03#3325-13487-15053` | 0.43 | 1 | .flac | 5280 | reference |

Lineage: 3325-13487 same_as; 3325-13992 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 3325-13487 | 0.166 | same_family | - | - | - | 1 |
| 3325-15053 | 0.162 | same_family | - | - | - | 1 |
| 13487-15053 | 0.952 | same_family | primary | - | - | None |

## 1998-06-12 - SPLIT

6465 (net taper f) has no leg to 5800/6462 (net taper i): corr 0.03-0.04, emb 0.34-0.70. It is in the family only by chain via 4436 (windowed 0.02-0.13). Family conf 0.20, already flagged. Split 6465 out; 4436 is itself weak.

Auto: SPLIT - 5800/6465: same_family, no leg (corr 0.039); 6462/6465: same_family, no leg (corr 0.033).

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 4436 | conflict |  | `1998-06-12#4436-5800-6462-6465` | 0.20 | 1 | .flac | 6092 | speed-unknown |
| 5800 | anchor | net taper i | `1998-06-12#4436-5800-6462-6465` | 0.20 | 1 | .flac | 5993 | reference |
| 6462 | anchor | net taper i | `1998-06-12#4436-5800-6462-6465` | 0.20 | 1 | .flac | 5687 | aligned |
| 6465 | anchor | net taper f | `1998-06-12#4436-5800-6462-6465` | 0.20 | 1 | .flac | 6024 | speed-unknown |

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| 4436-5800 | 0.133 | same_family | windowed | 0.48 | 0.94 | 1 |
| 4436-6462 | 0.061 | same_family | windowed | 0.47 | 0.49 | None |
| 4436-6465 | 0.018 | same_family | - | 0.43 | 0.64 | None |
| 5800-6462 | 0.923 | same_family | primary | - | 0.49 | 1 |
| 5800-6465 | 0.039 | same_family | - | 0.43 | 0.70 | None |
| 6462-6465 | 0.033 | same_family | - | 0.43 | 0.34 | None |

## 2000-05-25 - KEEP (relabel)

14518 (ltb) same_as 14519 (net taper f): one tape carrying two series credits. No observation rows; fix the attribution, no split.

Auto: KEEP - 14518/14519: curator lineage same_as.

| LB | Role | Series | Family | Fam conf | Flag | Ext | Dur s | Speed |
|---:|---|---|---|---:|---:|---|---:|---|
| 10677 | conflict |  | `2000-05-25#10677` | - | 0 |  | 7438 | reference |
| 14518 | anchor | ltb | `-` | - | - | None | - | None |
| 14519 | anchor | net taper f | `-` | - | - | None | - | None |

Lineage: 10677-14518 same_as; 14518-14519 same_as

| Pair | corr | verdict | mechanism | fp | emb | LB says same |
|---|---:|---|---|---:|---:|---|
| (no stored pair rows among these LBs) | | | | | | |
