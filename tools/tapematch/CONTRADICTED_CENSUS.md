# Curator-contradicted pair census (TODO-273)

Population: **1822 pairs** across **939 dates** where `lb_says_same=1` but the latest run said `different_family`.

Metadata only — no audio decoded. Regenerate with `.venv/bin/python3 tools/tapematch/census_contradicted.py`.


## Buckets (priority-ordered, mutually exclusive)

| Bucket | Pairs | Share |
|---|---:|---:|
| `lb_collision` | 10 | 0.5% |
| `label_contradiction` | 308 | 16.9% |
| `duration_mismatch` | 316 | 17.3% |
| `alignment_failure` | 806 | 44.2% |
| `segment_patchwork` | 5 | 0.3% |
| `unexplained` | 377 | 20.7% |

## Markers (non-exclusive — a pair can carry several)

| Marker | Pairs | Share |
|---|---:|---:|
| `lb_collision` | 10 | 0.5% |
| `label_contradiction` | 309 | 17.0% |
| `duration_mismatch` | 381 | 20.9% |
| `alignment_failure` | 1269 | 69.6% |
| `segment_patchwork` | 52 | 2.9% |

Markers per pair:

| Markers matched | Pairs |
|---:|---:|
| 0 | 377 |
| 1 | 939 |
| 2 | 439 |
| 3 | 64 |
| 4 | 3 |

## Correlation of the contradicted population

| corr band | Pairs |
|---|---:|
| < 0.05 | 1700 |
| 0.05–0.20 | 98 |
| 0.20–0.40 | 24 |
| ≥ 0.40 | 0 |

## Curator evidence standard (orthogonal to the buckets)

LB curators justify most same-source claims with one stock formula: _"same recording as LB-NNNN based on same clapping wavs at end of dXtY"_ — a single localised waveform comparison. Base rates below show how far that evidence standard carries.

| Population | Pairs | Clap-phrase | Rate |
|---|---:|---:|---:|
| curator says SAME, tapematch agrees | 1809 | 719 | 39.7% |
| curator says SAME, tapematch contradicts | 1822 | 997 | 54.7% |
| curator says DIFFERENT | 3039 | 26 | 0.9% |
| curator silent | 17299 | 0 | 0.0% |

So a same-source claim justified by clapping-wavs is confirmed by tapematch **41.9%** of the time (719/1716); one justified some other way is confirmed **56.9%** of the time (1090/1915). The heuristic is measurably weaker, but it is not noise — it is right more often than not-quite-half the time, and it is absent entirely from pairs the curator does not claim.


## Worked examples per bucket


### `lb_collision` (10 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1980-05-20 | LB-309/LB-8359 | 0.0054 | 1.304 | speed-unknown/speed-unknown |
| 1980-05-20 | LB-309/LB-12755 | 0.0052 | 1.036 | speed-unknown/speed-unknown |
| 1988-09-11 | LB-2585/LB-4747 | 0.0045 | 1.008 | constant-speed-offset/constant-speed-offset |
| 1988-09-23 | LB-3164/LB-15854 | 0.0109 | 1.018 | constant-speed-offset/constant-speed-offset |
| 1989-06-28 | LB-2147/LB-3733 | 0.0023 | 1.112 | constant-speed-offset/reference |

### `label_contradiction` (308 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1974-01-07 | LB-2320/LB-3604 | 0.0031 | 1.365 | speed-unknown/speed-unknown |
| 1974-01-07 | LB-2647/LB-3604 | 0.0031 | 1.007 | speed-unknown/speed-unknown |
| 1974-01-21 | LB-3638/LB-10788 | 0.0038 | 1.037 | speed-unknown/speed-unknown |
| 1974-01-21 | LB-9338/LB-10788 | 0.0022 | 1.595 | speed-unknown/speed-unknown |
| 1974-01-26 | LB-2501/LB-9326 | 0.0030 | 1.384 | constant-speed-offset/aligned |

### `duration_mismatch` (316 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1974-01-03 | LB-2580/LB-12560 | 0.0023 | 1.438 | speed-unknown/speed-unknown |
| 1974-01-03 | LB-2635/LB-12560 | 0.0024 | 1.286 | speed-unknown/speed-unknown |
| 1974-01-03 | LB-9303/LB-12560 | 0.0025 | 1.286 | reference/speed-unknown |
| 1974-01-04 | LB-2636/LB-5586 | 0.0039 | 1.475 | speed-unknown/reference |
| 1974-01-06 | LB-2638/LB-3603 | 0.0021 | 1.334 | speed-unknown/speed-unknown |

### `alignment_failure` (806 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1974-01-09 | LB-2650/LB-5218 | 0.0077 | 1.019 | speed-unknown/speed-unknown |
| 1974-01-11 | LB-2652/LB-3616 | 0.0084 | 1.012 | aligned/speed-unknown |
| 1974-01-11 | LB-2652/LB-5375 | 0.0074 | 1.012 | aligned/speed-unknown |
| 1974-01-12 | LB-2653/LB-3623 | 0.0035 | 1.022 | reference/speed-unknown |
| 1974-01-23 | LB-3650/LB-9637 | 0.0047 | 1.048 | speed-unknown/speed-unknown |

### `segment_patchwork` (5 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1989-07-26 | LB-1429/LB-8588 | 0.0052 | 1.006 | reference/constant-speed-offset |
| 1990-09-02 | LB-165/LB-4429 | 0.0024 | 1.033 | reference/constant-speed-offset |
| 1993-10-02 | LB-117/LB-5820 | 0.0014 | 1.013 | constant-speed-offset/constant-speed-offset |
| 1996-10-23 | LB-3447/LB-15488 | 0.0021 | 1.021 | reference/constant-speed-offset |
| 1998-02-14 | LB-3660/LB-4154 | 0.0716 | 1.003 | aligned/aligned |

### `unexplained` (377 pairs)

| Date | Pair | corr | dur ratio | speed_kind a/b |
|---|---|---:|---:|---|
| 1975-12-04 | LB-457/LB-5398 | 0.0242 | 1.014 | constant-speed-offset/reference |
| 1976-05-16 | LB-8287/LB-11131 | 0.0047 | 1.002 | reference/constant-speed-offset |
| 1978-03-04 | LB-7316/LB-9609 | 0.0105 | 1.076 | reference/constant-speed-offset |
| 1978-12-10 | LB-245/LB-7099 | 0.0023 | 1.090 | aligned/constant-speed-offset |
| 1979-11-11 | LB-1887/LB-4553 | 0.0529 | 1.001 | reference/constant-speed-offset |
