# Calibration eras of the shipped family verdicts (TODO-333)

Latest run per date: **3062 dates**. Shipped `config.yaml` hashes to **`d8c433ea3149`**, which covers **14 dates (0.5%)**; the rest were computed under an earlier calibration.

Regenerate with `.venv/bin/python3 tools/tapematch/calibration_eras.py`. Staleness is a provenance fact, not a verdict on correctness — see the module docstring before using this to schedule re-runs.


## Eras, newest activity first

| Calibration | Dates | Share | Last run | Months | Flipped pairs | Δ keys vs current | Replayable |
|---|---:|---:|---|---|---:|---:|---|
| `d8c433ea3149` **(current)** | 14 | 0.5% | 2026-10-26 | 2026-10 | 169 | — | — |
| `f786bebf58c8` | 246 | 8.0% | 2026-10-14 | 2026-10 | 1168 | 3 | yes — 0 date(s) move |
| `0e764850fc22` | 685 | 22.4% | 2026-09-03 | 2026-07, 2026-08, 2026-09 | 166 | 4 | yes — 1 date(s) move |
| `76f78b8480f3` | 748 | 24.4% | 2026-07-21 | 2026-07 | 819 | 5 | yes — 8 date(s) move |
| `31b4465ce221` | 762 | 24.9% | 2026-07-15 | 2026-07 | 1 | 8 | yes — 3 date(s) move |
| `50609144e7e9` | 3 | 0.1% | 2026-07-04 | 2026-07 | 10 | 9 | no (signal keys differ) |
| `d9a6b7539176` | 12 | 0.4% | 2026-07-03 | 2026-07 | 1 | 11 | no (signal keys differ) |
| `67231b68507e` | 3 | 0.1% | 2026-07-02 | 2026-07 | 5 | 44 | no (signal keys differ) |
| `134bb2bc5fba` | 4 | 0.1% | 2026-07-02 | 2026-07 | 0 | 16 | no (signal keys differ) |
| `c5a7793b70b8` | 499 | 16.3% | 2026-06-19 | 2026-06 | 0 | 17 | no (signal keys differ) |
| `4f2cbbd62045` | 82 | 2.7% | 2026-06-03 | 2026-06 | 0 | 20 | no (signal keys differ) |
| `867e6d952e3e` | 1 | 0.0% | 2026-06-02 | 2026-06 | 0 | 19 | no (signal keys differ) |
| `7e4ed1203754` | 3 | 0.1% | 2026-06-02 | 2026-06 | 0 | 20 | no (signal keys differ) |

## What each era differs on

Only keys whose VALUE differs from the shipped config are listed — a key absent from an older config but equal to today's default is not a difference and does not appear.


### `f786bebf58c8` — 246 dates

| Key | This era | Current |
|---|---|---|
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |

### `0e764850fc22` — 685 dates

| Key | This era | Current |
|---|---|---|
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `76f78b8480f3` — 748 dates

| Key | This era | Current |
|---|---|---|
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `None` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `31b4465ce221` — 762 dates

| Key | This era | Current |
|---|---|---|
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `50609144e7e9` — 3 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.live_embed` | `False` | `True` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `d9a6b7539176` — 12 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `67231b68507e` — 3 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `envelope_corr.band_hi_cap_hz` | `2000.0` | `(absent)` |
| `envelope_corr.band_lo_hz` | `200.0` | `(absent)` |
| `envelope_corr.enabled` | `True` | `False` |
| `envelope_corr.filter_order` | `6` | `(absent)` |
| `envelope_corr.frame_rate_hz` | `20.0` | `(absent)` |
| `envelope_corr.min_overlap_min` | `10.0` | `(absent)` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `flaw_fingerprint.click_cap` | `200` | `(absent)` |
| `flaw_fingerprint.click_local_window_ms` | `50.0` | `(absent)` |
| `flaw_fingerprint.click_max_dur_ms` | `5.0` | `(absent)` |
| `flaw_fingerprint.click_sigma` | `6.0` | `(absent)` |
| `flaw_fingerprint.cut_frame_sec` | `0.1` | `(absent)` |
| `flaw_fingerprint.cut_sigma` | `4.0` | `(absent)` |
| `flaw_fingerprint.dropout_depth_db` | `20.0` | `(absent)` |
| `flaw_fingerprint.dropout_frame_sec` | `0.02` | `(absent)` |
| `flaw_fingerprint.dropout_local_window_sec` | `2.0` | `(absent)` |
| `flaw_fingerprint.dropout_max_sec` | `0.8` | `(absent)` |
| `flaw_fingerprint.dropout_min_sec` | `0.04` | `(absent)` |
| `flaw_fingerprint.enabled` | `True` | `False` |
| `flaw_fingerprint.flaw_min_events` | `5` | `(absent)` |
| `flaw_fingerprint.min_quiet_sec` | `3.0` | `(absent)` |
| `flaw_fingerprint.quiet_energy_percentile` | `25` | `(absent)` |
| `flaw_fingerprint.tol_sec` | `0.5` | `(absent)` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |
| `spectral_stationarity.enabled` | `True` | `False` |
| `spectral_stationarity.hop_sec` | `30.0` | `(absent)` |
| `spectral_stationarity.local_lag_sec` | `10.0` | `(absent)` |
| `spectral_stationarity.min_frames_per_window` | `20` | `(absent)` |
| `spectral_stationarity.n_mels` | `32` | `(absent)` |
| `spectral_stationarity.noise_floor_margin_db` | `6.0` | `(absent)` |
| `spectral_stationarity.stationarity_min_windows` | `6` | `(absent)` |
| `spectral_stationarity.stationarity_norm_db` | `6.0` | `(absent)` |
| `spectral_stationarity.stft_hop` | `256` | `(absent)` |
| `spectral_stationarity.stft_nperseg` | `1024` | `(absent)` |
| `spectral_stationarity.window_sec` | `60.0` | `(absent)` |

### `134bb2bc5fba` — 4 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `fingerprint.triplet.cluster_threshold` | `0.45` | `(absent)` |
| `fingerprint.triplet.enabled` | `True` | `False` |
| `fingerprint.triplet.fanout` | `4` | `(absent)` |
| `fingerprint.triplet.tmax_sec` | `8.0` | `(absent)` |
| `fingerprint.triplet.tmin_sec` | `0.5` | `(absent)` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `c5a7793b70b8` — 499 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |
| `refine.max_iter` | `(absent)` | `2` |
| `refine.stop_ppm` | `(absent)` | `5.0` |
| `refine.trigger_corr_ceiling` | `(absent)` | `0.6` |
| `refine.trigger_min_ppm` | `(absent)` | `2000` |

### `4f2cbbd62045` — 82 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `align.max_lag_sec` | `30.0` | `90.0` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |
| `refine.max_iter` | `(absent)` | `2` |
| `refine.stop_ppm` | `(absent)` | `5.0` |
| `refine.trigger_corr_ceiling` | `(absent)` | `0.6` |
| `refine.trigger_min_ppm` | `(absent)` | `2000` |
| `secondary_match.local_lag_sec` | `5.0` | `10.0` |

### `867e6d952e3e` — 1 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `align.max_lag_sec` | `30.0` | `90.0` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |
| `refine.max_iter` | `(absent)` | `2` |
| `refine.stop_ppm` | `(absent)` | `5.0` |
| `refine.trigger_corr_ceiling` | `(absent)` | `0.6` |
| `refine.trigger_min_ppm` | `(absent)` | `2000` |

### `7e4ed1203754` — 3 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `align.max_lag_sec` | `30.0` | `90.0` |
| `family_guard.enabled` | `(absent)` | `True` |
| `family_guard.min_link_density` | `(absent)` | `0.5` |
| `family_guard.strong_legs` | `(absent)` | `['primary', 'windowed', 'hiss', 'fingerprint', 'rule_d']` |
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.cluster_threshold` | `0.55` | `0.45` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |
| `refine.max_iter` | `(absent)` | `2` |
| `refine.stop_ppm` | `(absent)` | `5.0` |
| `refine.trigger_corr_ceiling` | `(absent)` | `0.6` |
| `refine.trigger_min_ppm` | `(absent)` | `2000` |

## Replay: dates whose verdict actually moves under the current config

2441 stale dates differ from the shipped config ONLY in threshold keys, so their stored pair metrics can be re-decided exactly without touching audio. Of those, **12 change verdict** and 2429 are identical — i.e. most of the staleness in those eras is bookkeeping, not disagreement. A re-run for a date in the identical set buys a fresher `calibration_hash` and nothing else.

| Date | Calibration | Pairs that move | Flipped before | Sources ran / catalogued |
|---|---|---:|---:|---|
| 1997-12-18 | `76f78b8480f3` | 14 | 10 | 12/12 |
| 2001-10-12 | `76f78b8480f3` | 11 | 22 | 11/11 |
| 1997-10-05 | `76f78b8480f3` | 4 | 7 | 8/9 ⚠ |
| 2013-10-25 | `76f78b8480f3` | 3 | 0 | 4/5 ⚠ |
| 1993-02-12 | `76f78b8480f3` | 2 | 7 | 7/8 ⚠ |
| 1997-12-17 | `31b4465ce221` | 2 | 0 | 4/7 ⚠ |
| 1974-01-07 | `0e764850fc22` | 1 | 1 | 7/9 ⚠ |
| 1999-04-28 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2000-06-18 | `31b4465ce221` | 1 | 0 | 5/5 |
| 2009-10-10 | `76f78b8480f3` | 1 | 6 | 6/6 |
| 2010-03-28 | `76f78b8480f3` | 1 | 18 | 8/9 ⚠ |
| 2014-04-09 | `76f78b8480f3` | 1 | 0 | 5/5 |

## Re-run priority (highest expected change first)

Dates on a non-current calibration, ordered by how many of their pairs have already flipped verdict between runs. A date with flips has demonstrated that its verdicts turn on the config; a date with none may well be stable across the difference. Incomplete-set dates are marked: re-running one under a current config does not make it correct, because it is still missing sources.

| Date | Calibration | Flipped pairs | Sources ran / catalogued | Last run |
|---|---|---:|---|---|
| 2003-10-17 | `f786bebf58c8` | 51 | 13/14 ⚠ incomplete | 2026-10-14 |
| 2009-04-10 | `76f78b8480f3` | 38 | 11/12 ⚠ incomplete | 2026-07-17 |
| 1999-11-19 | `f786bebf58c8` | 31 | 9/14 ⚠ incomplete | 2026-10-14 |
| 1997-12-08 | `f786bebf58c8` | 29 | 9/15 ⚠ incomplete | 2026-10-14 |
| 2002-04-11 | `76f78b8480f3` | 29 | 11/12 ⚠ incomplete | 2026-07-18 |
| 2003-11-23 | `76f78b8480f3` | 29 | 10/10 | 2026-07-17 |
| 2010-03-29 | `f786bebf58c8` | 28 | 9/9 | 2026-10-14 |
| 1995-05-27 | `f786bebf58c8` | 27 | 10/12 ⚠ incomplete | 2026-10-14 |
| 1997-12-01 | `f786bebf58c8` | 27 | 9/11 ⚠ incomplete | 2026-10-14 |
| 1997-08-23 | `f786bebf58c8` | 25 | 9/14 ⚠ incomplete | 2026-10-14 |
| 1997-10-03 | `f786bebf58c8` | 22 | 8/10 ⚠ incomplete | 2026-10-14 |
| 2001-10-12 | `76f78b8480f3` | 22 | 11/11 | 2026-07-18 |
| 1988-07-17 | `f786bebf58c8` | 21 | 8/8 | 2026-10-14 |
| 2002-08-15 | `76f78b8480f3` | 20 | 7/7 | 2026-07-17 |
| 2002-04-05 | `76f78b8480f3` | 19 | 8/8 | 2026-07-17 |
| 2003-05-10 | `f786bebf58c8` | 19 | 7/7 | 2026-10-14 |
| 2010-03-28 | `76f78b8480f3` | 18 | 8/9 ⚠ incomplete | 2026-07-17 |
| 1988-06-30 | `f786bebf58c8` | 15 | 10/11 ⚠ incomplete | 2026-10-14 |
| 1988-12-04 | `f786bebf58c8` | 15 | 13/13 | 2026-10-14 |
| 1994-07-19 | `76f78b8480f3` | 15 | 8/9 ⚠ incomplete | 2026-07-18 |
| 2009-07-05 | `f786bebf58c8` | 15 | 7/7 | 2026-10-14 |
| 2010-03-23 | `f786bebf58c8` | 15 | 6/7 ⚠ incomplete | 2026-10-14 |
| 1966-05-10 | `f786bebf58c8` | 14 | 6/6 | 2026-10-14 |
| 1974-01-26 | `f786bebf58c8` | 14 | 10/10 | 2026-10-14 |
| 1974-02-04 | `f786bebf58c8` | 14 | 10/10 | 2026-10-14 |
| 1980-01-22 | `f786bebf58c8` | 14 | 7/7 | 2026-10-14 |
| 1995-05-26 | `f786bebf58c8` | 14 | 8/9 ⚠ incomplete | 2026-10-14 |
| 2000-10-31 | `f786bebf58c8` | 14 | 6/7 ⚠ incomplete | 2026-10-14 |
| 2004-03-01 | `76f78b8480f3` | 14 | 6/6 | 2026-07-17 |
| 2004-06-06 | `f786bebf58c8` | 14 | 6/6 | 2026-10-14 |
| 2004-06-08 | `76f78b8480f3` | 14 | 6/6 | 2026-07-18 |
| 2008-06-11 | `76f78b8480f3` | 14 | 6/6 | 2026-07-17 |
| 2010-03-21 | `76f78b8480f3` | 14 | 7/8 ⚠ incomplete | 2026-07-17 |
| 1995-12-16 | `76f78b8480f3` | 13 | 8/11 ⚠ incomplete | 2026-07-17 |
| 1999-06-07 | `f786bebf58c8` | 13 | 6/7 ⚠ incomplete | 2026-10-14 |
| 2001-10-07 | `76f78b8480f3` | 13 | 6/6 | 2026-07-18 |
| 2003-07-31 | `0e764850fc22` | 13 | 6/6 | 2026-08-07 |
| 2010-03-24 | `f786bebf58c8` | 13 | 6/7 ⚠ incomplete | 2026-10-14 |
| 1999-07-17 | `f786bebf58c8` | 12 | 6/9 ⚠ incomplete | 2026-10-14 |
| 1999-11-14 | `f786bebf58c8` | 12 | 6/8 ⚠ incomplete | 2026-10-14 |
| 2000-06-16 | `f786bebf58c8` | 12 | 6/8 ⚠ incomplete | 2026-10-14 |
| 2000-09-20 | `f786bebf58c8` | 12 | 8/8 | 2026-10-14 |
| 2002-10-11 | `76f78b8480f3` | 12 | 11/11 | 2026-07-17 |
| 1978-07-15 | `f786bebf58c8` | 11 | 14/15 ⚠ incomplete | 2026-10-14 |
| 1996-11-04 | `76f78b8480f3` | 11 | 7/8 ⚠ incomplete | 2026-07-19 |
| 1997-08-20 | `76f78b8480f3` | 11 | 7/10 ⚠ incomplete | 2026-07-17 |
| 1997-12-10 | `76f78b8480f3` | 11 | 6/9 ⚠ incomplete | 2026-07-17 |
| 2000-06-15 | `76f78b8480f3` | 11 | 6/8 ⚠ incomplete | 2026-07-17 |
| 2000-06-17 | `76f78b8480f3` | 11 | 6/6 | 2026-07-17 |
| 1981-10-18 | `f786bebf58c8` | 10 | 5/5 | 2026-10-14 |
| 1990-08-12 | `f786bebf58c8` | 10 | 5/5 | 2026-10-14 |
| 1996-07-21 | `50609144e7e9` | 10 | 5/5 | 2026-07-04 |
| 1997-12-18 | `76f78b8480f3` | 10 | 12/12 | 2026-07-17 |
| 2002-05-05 | `76f78b8480f3` | 10 | 5/6 ⚠ incomplete | 2026-07-18 |
| 2007-04-15 | `f786bebf58c8` | 10 | 7/7 | 2026-10-14 |
| 2011-10-16 | `0e764850fc22` | 10 | 5/5 | 2026-08-07 |
| 1986-02-24 | `0e764850fc22` | 9 | 15/16 ⚠ incomplete | 2026-07-28 |
| 1987-09-12 | `f786bebf58c8` | 9 | 7/9 ⚠ incomplete | 2026-10-14 |
| 1988-09-23 | `f786bebf58c8` | 9 | 6/6 | 2026-10-14 |
| 1995-03-12 | `f786bebf58c8` | 9 | 7/12 ⚠ incomplete | 2026-10-14 |

_3048 stale dates in total; the 2988 beyond the top 60 carry no recorded flips._


Of the 3048 stale dates, 935 also ran on an incomplete set (TODO-334), so their family counts are provisional for a second, independent reason.

