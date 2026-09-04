# Calibration eras of the shipped family verdicts (TODO-333)

Latest run per date: **3062 dates**. Shipped `config.yaml` hashes to **`0e764850fc22`**, which covers **768 dates (25.1%)**; the rest were computed under an earlier calibration.

Regenerate with `.venv/bin/python3 tools/tapematch/calibration_eras.py`. Staleness is a provenance fact, not a verdict on correctness — see the module docstring before using this to schedule re-runs.


## Eras, newest activity first

| Calibration | Dates | Share | Last run | Months | Flipped pairs | Δ keys vs current | Replayable |
|---|---:|---:|---|---|---:|---:|---|
| `0e764850fc22` **(current)** | 768 | 25.1% | 2026-09-03 | 2026-07, 2026-08, 2026-09 | 201 | — | — |
| `76f78b8480f3` | 876 | 28.6% | 2026-07-21 | 2026-07 | 1355 | 1 | yes — 25 date(s) move |
| `31b4465ce221` | 811 | 26.5% | 2026-07-15 | 2026-07 | 1 | 4 | yes — 8 date(s) move |
| `50609144e7e9` | 3 | 0.1% | 2026-07-04 | 2026-07 | 10 | 5 | no (signal keys differ) |
| `d9a6b7539176` | 12 | 0.4% | 2026-07-03 | 2026-07 | 1 | 7 | no (signal keys differ) |
| `67231b68507e` | 3 | 0.1% | 2026-07-02 | 2026-07 | 5 | 40 | no (signal keys differ) |
| `134bb2bc5fba` | 4 | 0.1% | 2026-07-02 | 2026-07 | 0 | 12 | no (signal keys differ) |
| `c5a7793b70b8` | 499 | 16.3% | 2026-06-19 | 2026-06 | 0 | 13 | no (signal keys differ) |
| `4f2cbbd62045` | 82 | 2.7% | 2026-06-03 | 2026-06 | 0 | 16 | no (signal keys differ) |
| `867e6d952e3e` | 1 | 0.0% | 2026-06-02 | 2026-06 | 0 | 15 | no (signal keys differ) |
| `7e4ed1203754` | 3 | 0.1% | 2026-06-02 | 2026-06 | 0 | 16 | no (signal keys differ) |

## What each era differs on

Only keys whose VALUE differs from the shipped config are listed — a key absent from an older config but equal to today's default is not a difference and does not appear.


### `76f78b8480f3` — 876 dates

| Key | This era | Current |
|---|---|---|
| `fingerprint.staircase_corroboration.min_hiss_median` | `None` | `0.05` |

### `31b4465ce221` — 811 dates

| Key | This era | Current |
|---|---|---|
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |

### `50609144e7e9` — 3 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.live_embed` | `False` | `True` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |

### `d9a6b7539176` — 12 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |

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
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `fingerprint.triplet.cluster_threshold` | `0.45` | `(absent)` |
| `fingerprint.triplet.enabled` | `True` | `False` |
| `fingerprint.triplet.fanout` | `4` | `(absent)` |
| `fingerprint.triplet.tmax_sec` | `8.0` | `(absent)` |
| `fingerprint.triplet.tmin_sec` | `0.5` | `(absent)` |

### `c5a7793b70b8` — 499 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.enabled` | `False` | `True` |
| `addon_links.rule_d.live_embed` | `(absent)` | `True` |
| `addon_links.rule_d.t_emb` | `(absent)` | `0.75` |
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
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
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
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
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
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
| `fingerprint.cluster_threshold_curator` | `None` | `0.43` |
| `fingerprint.cluster_threshold_staircase` | `None` | `0.4` |
| `fingerprint.hf_band_hz` | `None` | `[6000, 8000]` |
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.cluster_threshold` | `0.55` | `0.45` |
| `refine.max_iter` | `(absent)` | `2` |
| `refine.stop_ppm` | `(absent)` | `5.0` |
| `refine.trigger_corr_ceiling` | `(absent)` | `0.6` |
| `refine.trigger_min_ppm` | `(absent)` | `2000` |

## Replay: dates whose verdict actually moves under the current config

1687 stale dates differ from the shipped config ONLY in threshold keys, so their stored pair metrics can be re-decided exactly without touching audio. Of those, **33 change verdict** and 1654 are identical — i.e. most of the staleness in those eras is bookkeeping, not disagreement. A re-run for a date in the identical set buys a fresher `calibration_hash` and nothing else.

| Date | Calibration | Pairs that move | Flipped before | Sources ran / catalogued |
|---|---|---:|---:|---|
| 1997-10-03 | `76f78b8480f3` | 15 | 7 | 8/10 ⚠ |
| 2009-04-11 | `76f78b8480f3` | 6 | 0 | 8/8 |
| 2010-11-22 | `31b4465ce221` | 5 | 0 | 4/4 |
| 2014-06-27 | `76f78b8480f3` | 5 | 0 | 4/4 |
| 1996-06-17 | `76f78b8480f3` | 4 | 4 | 6/7 ⚠ |
| 2014-07-08 | `76f78b8480f3` | 4 | 0 | 6/6 |
| 1997-04-11 | `76f78b8480f3` | 3 | 4 | 5/6 ⚠ |
| 1997-08-05 | `76f78b8480f3` | 3 | 4 | 5/7 ⚠ |
| 2002-04-29 | `76f78b8480f3` | 3 | 4 | 5/5 |
| 2002-11-09 | `76f78b8480f3` | 3 | 0 | 8/9 ⚠ |
| 2007-04-15 | `76f78b8480f3` | 3 | 6 | 7/7 |
| 2013-10-25 | `76f78b8480f3` | 3 | 0 | 4/5 ⚠ |
| 1995-06-16 | `31b4465ce221` | 2 | 0 | 3/3 |
| 1997-04-13 | `76f78b8480f3` | 2 | 3 | 4/8 ⚠ |
| 1997-05-02 | `76f78b8480f3` | 2 | 3 | 4/4 |
| 1997-08-09 | `76f78b8480f3` | 2 | 0 | 3/4 ⚠ |
| 1999-04-10 | `76f78b8480f3` | 2 | 3 | 5/7 ⚠ |
| 1999-11-19 | `76f78b8480f3` | 2 | 29 | 9/14 ⚠ |
| 2001-07-25 | `76f78b8480f3` | 2 | 2 | 4/5 ⚠ |
| 2009-10-23 | `31b4465ce221` | 2 | 0 | 3/3 |
| 2010-03-23 | `76f78b8480f3` | 2 | 12 | 6/7 ⚠ |
| 1999-01-30 | `31b4465ce221` | 1 | 0 | 5/6 ⚠ |
| 2004-11-02 | `31b4465ce221` | 1 | 0 | 6/6 |
| 2007-08-13 | `31b4465ce221` | 1 | 0 | 3/3 |
| 2007-08-15 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2010-03-28 | `76f78b8480f3` | 1 | 18 | 8/9 ⚠ |
| 2010-03-29 | `76f78b8480f3` | 1 | 27 | 9/9 |
| 2010-06-13 | `31b4465ce221` | 1 | 0 | 3/4 ⚠ |
| 2011-06-27 | `76f78b8480f3` | 1 | 4 | 4/5 ⚠ |
| 2013-10-22 | `76f78b8480f3` | 1 | 0 | 6/8 ⚠ |
| 2013-11-03 | `76f78b8480f3` | 1 | 0 | 4/4 |
| 2014-04-05 | `76f78b8480f3` | 1 | 0 | 6/6 |
| 2014-06-29 | `76f78b8480f3` | 1 | 0 | 4/4 |

## Re-run priority (highest expected change first)

Dates on a non-current calibration, ordered by how many of their pairs have already flipped verdict between runs. A date with flips has demonstrated that its verdicts turn on the config; a date with none may well be stable across the difference. Incomplete-set dates are marked: re-running one under a current config does not make it correct, because it is still missing sources.

| Date | Calibration | Flipped pairs | Sources ran / catalogued | Last run |
|---|---|---:|---|---|
| 2003-10-17 | `76f78b8480f3` | 48 | 13/14 ⚠ incomplete | 2026-07-17 |
| 2009-04-10 | `76f78b8480f3` | 38 | 11/12 ⚠ incomplete | 2026-07-17 |
| 1999-11-19 | `76f78b8480f3` | 29 | 9/14 ⚠ incomplete | 2026-07-17 |
| 2002-04-11 | `76f78b8480f3` | 29 | 11/12 ⚠ incomplete | 2026-07-18 |
| 2003-11-23 | `76f78b8480f3` | 29 | 10/10 | 2026-07-17 |
| 2010-03-29 | `76f78b8480f3` | 27 | 9/9 | 2026-07-17 |
| 1997-12-01 | `76f78b8480f3` | 25 | 9/11 ⚠ incomplete | 2026-07-17 |
| 2001-10-12 | `76f78b8480f3` | 22 | 11/11 | 2026-07-18 |
| 1988-07-17 | `76f78b8480f3` | 21 | 8/8 | 2026-07-18 |
| 2002-08-15 | `76f78b8480f3` | 20 | 7/7 | 2026-07-17 |
| 2002-04-05 | `76f78b8480f3` | 19 | 8/8 | 2026-07-17 |
| 1995-05-27 | `76f78b8480f3` | 18 | 10/12 ⚠ incomplete | 2026-07-17 |
| 2010-03-28 | `76f78b8480f3` | 18 | 8/9 ⚠ incomplete | 2026-07-17 |
| 2003-05-10 | `76f78b8480f3` | 17 | 7/7 | 2026-07-17 |
| 1994-07-19 | `76f78b8480f3` | 15 | 8/9 ⚠ incomplete | 2026-07-18 |
| 1995-06-25 | `76f78b8480f3` | 15 | 9/11 ⚠ incomplete | 2026-07-17 |
| 1997-12-08 | `76f78b8480f3` | 15 | 9/15 ⚠ incomplete | 2026-07-17 |
| 2004-03-01 | `76f78b8480f3` | 14 | 6/6 | 2026-07-17 |
| 2004-06-08 | `76f78b8480f3` | 14 | 6/6 | 2026-07-18 |
| 2008-06-11 | `76f78b8480f3` | 14 | 6/6 | 2026-07-17 |
| 2010-03-21 | `76f78b8480f3` | 14 | 7/8 ⚠ incomplete | 2026-07-17 |
| 1995-12-16 | `76f78b8480f3` | 13 | 8/11 ⚠ incomplete | 2026-07-17 |
| 2000-10-31 | `76f78b8480f3` | 13 | 6/7 ⚠ incomplete | 2026-07-17 |
| 2001-10-07 | `76f78b8480f3` | 13 | 6/6 | 2026-07-18 |
| 2004-06-06 | `76f78b8480f3` | 13 | 6/6 | 2026-07-17 |
| 2002-10-11 | `76f78b8480f3` | 12 | 11/11 | 2026-07-17 |
| 2010-03-23 | `76f78b8480f3` | 12 | 6/7 ⚠ incomplete | 2026-07-17 |
| 1996-11-04 | `76f78b8480f3` | 11 | 7/8 ⚠ incomplete | 2026-07-19 |
| 1997-08-20 | `76f78b8480f3` | 11 | 7/10 ⚠ incomplete | 2026-07-17 |
| 1997-12-10 | `76f78b8480f3` | 11 | 6/9 ⚠ incomplete | 2026-07-17 |
| 1999-06-07 | `76f78b8480f3` | 11 | 6/7 ⚠ incomplete | 2026-07-17 |
| 1999-11-14 | `76f78b8480f3` | 11 | 6/8 ⚠ incomplete | 2026-07-18 |
| 2000-06-15 | `76f78b8480f3` | 11 | 6/8 ⚠ incomplete | 2026-07-17 |
| 2000-06-17 | `76f78b8480f3` | 11 | 6/6 | 2026-07-17 |
| 2000-06-21 | `76f78b8480f3` | 11 | 8/9 ⚠ incomplete | 2026-07-17 |
| 2009-07-05 | `76f78b8480f3` | 11 | 7/7 | 2026-07-17 |
| 1990-08-12 | `76f78b8480f3` | 10 | 5/5 | 2026-07-17 |
| 1995-05-26 | `76f78b8480f3` | 10 | 8/9 ⚠ incomplete | 2026-07-17 |
| 1996-07-21 | `50609144e7e9` | 10 | 5/5 | 2026-07-04 |
| 1997-12-18 | `76f78b8480f3` | 10 | 12/12 | 2026-07-17 |
| 2002-05-05 | `76f78b8480f3` | 10 | 5/6 ⚠ incomplete | 2026-07-18 |
| 1987-09-12 | `76f78b8480f3` | 9 | 7/9 ⚠ incomplete | 2026-07-17 |
| 1994-07-10 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-19 |
| 1997-12-14 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-17 |
| 1999-06-05 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-17 |
| 1999-07-17 | `76f78b8480f3` | 9 | 6/9 ⚠ incomplete | 2026-07-17 |
| 1999-09-08 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-18 |
| 2000-06-16 | `76f78b8480f3` | 9 | 6/8 ⚠ incomplete | 2026-07-18 |
| 2007-04-06 | `76f78b8480f3` | 9 | 5/5 | 2026-07-17 |
| 2009-04-05 | `76f78b8480f3` | 9 | 7/7 | 2026-07-18 |
| 1999-10-29 | `76f78b8480f3` | 8 | 7/8 ⚠ incomplete | 2026-07-18 |
| 2000-09-23 | `76f78b8480f3` | 8 | 5/9 ⚠ incomplete | 2026-07-17 |
| 1993-02-12 | `76f78b8480f3` | 7 | 7/8 ⚠ incomplete | 2026-07-19 |
| 1997-04-18 | `76f78b8480f3` | 7 | 5/9 ⚠ incomplete | 2026-07-17 |
| 1997-05-03 | `76f78b8480f3` | 7 | 5/6 ⚠ incomplete | 2026-07-17 |
| 1997-08-23 | `76f78b8480f3` | 7 | 9/14 ⚠ incomplete | 2026-07-17 |
| 1997-10-03 | `76f78b8480f3` | 7 | 8/10 ⚠ incomplete | 2026-07-17 |
| 1997-10-05 | `76f78b8480f3` | 7 | 8/9 ⚠ incomplete | 2026-07-17 |
| 2011-11-14 | `76f78b8480f3` | 7 | 5/5 | 2026-07-17 |
| 1992-06-30 | `76f78b8480f3` | 6 | 7/8 ⚠ incomplete | 2026-07-18 |

_2294 stale dates in total; the 2234 beyond the top 60 carry no recorded flips._


Of the 2294 stale dates, 745 also ran on an incomplete set (TODO-334), so their family counts are provisional for a second, independent reason.

