# Calibration eras of the shipped family verdicts (TODO-333)

Latest run per date: **3062 dates**. Shipped `config.yaml` hashes to **`f786bebf58c8`**, which covers **0 dates (0.0%)**; the rest were computed under an earlier calibration.

Regenerate with `.venv/bin/python3 tools/tapematch/calibration_eras.py`. Staleness is a provenance fact, not a verdict on correctness — see the module docstring before using this to schedule re-runs.


## Eras, newest activity first

| Calibration | Dates | Share | Last run | Months | Flipped pairs | Δ keys vs current | Replayable |
|---|---:|---:|---|---|---:|---:|---|
| `0e764850fc22` | 768 | 25.1% | 2026-09-03 | 2026-07, 2026-08, 2026-09 | 201 | 1 | yes — 84 date(s) move |
| `76f78b8480f3` | 876 | 28.6% | 2026-07-21 | 2026-07 | 1355 | 2 | yes — 124 date(s) move |
| `31b4465ce221` | 811 | 26.5% | 2026-07-15 | 2026-07 | 1 | 5 | yes — 52 date(s) move |
| `50609144e7e9` | 3 | 0.1% | 2026-07-04 | 2026-07 | 10 | 6 | no (signal keys differ) |
| `d9a6b7539176` | 12 | 0.4% | 2026-07-03 | 2026-07 | 1 | 8 | no (signal keys differ) |
| `67231b68507e` | 3 | 0.1% | 2026-07-02 | 2026-07 | 5 | 41 | no (signal keys differ) |
| `134bb2bc5fba` | 4 | 0.1% | 2026-07-02 | 2026-07 | 0 | 13 | no (signal keys differ) |
| `c5a7793b70b8` | 499 | 16.3% | 2026-06-19 | 2026-06 | 0 | 14 | no (signal keys differ) |
| `4f2cbbd62045` | 82 | 2.7% | 2026-06-03 | 2026-06 | 0 | 17 | no (signal keys differ) |
| `867e6d952e3e` | 1 | 0.0% | 2026-06-02 | 2026-06 | 0 | 16 | no (signal keys differ) |
| `7e4ed1203754` | 3 | 0.1% | 2026-06-02 | 2026-06 | 0 | 17 | no (signal keys differ) |

## What each era differs on

Only keys whose VALUE differs from the shipped config are listed — a key absent from an older config but equal to today's default is not a difference and does not appear.


### `0e764850fc22` — 768 dates

| Key | This era | Current |
|---|---|---|
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `76f78b8480f3` — 876 dates

| Key | This era | Current |
|---|---|---|
| `fingerprint.staircase_corroboration.min_hiss_median` | `None` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `31b4465ce221` — 811 dates

| Key | This era | Current |
|---|---|---|
| `fingerprint.staircase_corroboration.enabled` | `False` | `True` |
| `fingerprint.staircase_corroboration.min_hiss_frac` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_hiss_median` | `(absent)` | `0.05` |
| `fingerprint.staircase_corroboration.min_windowed_frac` | `(absent)` | `0.05` |
| `match.fingerprint_primary_floor` | `None` | `0.05` |

### `50609144e7e9` — 3 dates

| Key | This era | Current |
|---|---|---|
| `addon_links.rule_d.live_embed` | `False` | `True` |
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

2455 stale dates differ from the shipped config ONLY in threshold keys, so their stored pair metrics can be re-decided exactly without touching audio. Of those, **260 change verdict** and 2195 are identical — i.e. most of the staleness in those eras is bookkeeping, not disagreement. A re-run for a date in the identical set buys a fresher `calibration_hash` and nothing else.

| Date | Calibration | Pairs that move | Flipped before | Sources ran / catalogued |
|---|---|---:|---:|---|
| 2002-04-28 | `76f78b8480f3` | 23 | 0 | 9/9 |
| 1988-07-17 | `76f78b8480f3` | 21 | 21 | 8/8 |
| 1997-08-23 | `76f78b8480f3` | 18 | 7 | 9/14 ⚠ |
| 1988-06-30 | `76f78b8480f3` | 15 | 0 | 10/11 ⚠ |
| 1988-12-04 | `76f78b8480f3` | 15 | 0 | 13/13 |
| 1997-10-03 | `76f78b8480f3` | 15 | 7 | 8/10 ⚠ |
| 1966-05-10 | `0e764850fc22` | 14 | 0 | 6/6 |
| 1974-01-26 | `0e764850fc22` | 14 | 0 | 10/10 |
| 1974-02-04 | `0e764850fc22` | 14 | 0 | 10/10 |
| 1980-01-22 | `0e764850fc22` | 14 | 0 | 7/7 |
| 1997-12-08 | `76f78b8480f3` | 14 | 15 | 9/15 ⚠ |
| 2000-09-20 | `76f78b8480f3` | 12 | 0 | 8/8 |
| 1978-07-15 | `0e764850fc22` | 11 | 0 | 14/15 ⚠ |
| 2001-10-12 | `76f78b8480f3` | 11 | 22 | 11/11 |
| 1981-10-18 | `0e764850fc22` | 10 | 0 | 5/5 |
| 1988-09-23 | `0e764850fc22` | 9 | 2 | 6/6 |
| 1995-05-27 | `76f78b8480f3` | 9 | 18 | 10/12 ⚠ |
| 1974-01-31 | `0e764850fc22` | 8 | 0 | 26/31 ⚠ |
| 1997-02-13 | `76f78b8480f3` | 8 | 6 | 5/6 ⚠ |
| 2010-03-24 | `76f78b8480f3` | 8 | 5 | 6/7 ⚠ |
| 1974-01-17 | `0e764850fc22` | 7 | 0 | 5/6 ⚠ |
| 1974-02-14 | `0e764850fc22` | 7 | 0 | 22/24 ⚠ |
| 1975-12-08 | `0e764850fc22` | 7 | 0 | 16/17 ⚠ |
| 1978-12-03 | `0e764850fc22` | 7 | 0 | 5/5 |
| 1998-05-19 | `76f78b8480f3` | 7 | 0 | 9/11 ⚠ |
| 1993-02-15 | `76f78b8480f3` | 6 | 0 | 8/8 |
| 1995-03-12 | `0e764850fc22` | 6 | 9 | 7/12 ⚠ |
| 1995-06-25 | `76f78b8480f3` | 6 | 15 | 9/11 ⚠ |
| 2002-08-16 | `31b4465ce221` | 6 | 0 | 4/4 |
| 2009-04-11 | `76f78b8480f3` | 6 | 0 | 8/8 |
| 1964-10-10 | `0e764850fc22` | 5 | 0 | 4/4 |
| 1965-05-09 | `0e764850fc22` | 5 | 0 | 5/5 |
| 1965-08-28 | `0e764850fc22` | 5 | 0 | 5/5 |
| 1971-08-01 | `0e764850fc22` | 5 | 0 | 5/5 |
| 1978-06-16 | `0e764850fc22` | 5 | 0 | 8/9 ⚠ |
| 1978-07-01 | `0e764850fc22` | 5 | 0 | 8/8 |
| 1992-04-30 | `76f78b8480f3` | 5 | 0 | 4/4 |
| 1997-03-31 | `76f78b8480f3` | 5 | 5 | 6/6 |
| 1997-08-17 | `76f78b8480f3` | 5 | 0 | 4/7 ⚠ |
| 1998-06-27 | `76f78b8480f3` | 5 | 0 | 8/11 ⚠ |
| 1999-04-09 | `31b4465ce221` | 5 | 0 | 4/4 |
| 2002-04-29 | `76f78b8480f3` | 5 | 4 | 5/5 |
| 2010-11-22 | `31b4465ce221` | 5 | 0 | 4/4 |
| 2014-06-27 | `76f78b8480f3` | 5 | 0 | 4/4 |
| 2014-07-08 | `76f78b8480f3` | 5 | 0 | 6/6 |
| 1974-01-25 | `0e764850fc22` | 4 | 0 | 8/10 ⚠ |
| 1974-02-02 | `0e764850fc22` | 4 | 0 | 5/6 ⚠ |
| 1974-02-11 | `0e764850fc22` | 4 | 0 | 15/15 |
| 1978-03-03 | `0e764850fc22` | 4 | 0 | 5/6 ⚠ |
| 1978-03-15 | `0e764850fc22` | 4 | 0 | 6/6 |
| 1980-04-22 | `0e764850fc22` | 4 | 0 | 6/6 |
| 1980-05-03 | `0e764850fc22` | 4 | 0 | 5/5 |
| 1984-06-10 | `0e764850fc22` | 4 | 0 | 7/7 |
| 1990-08-21 | `76f78b8480f3` | 4 | 4 | 5/7 ⚠ |
| 1993-06-29 | `76f78b8480f3` | 4 | 4 | 5/6 ⚠ |
| 1995-05-26 | `76f78b8480f3` | 4 | 10 | 8/9 ⚠ |
| 1995-06-03 | `76f78b8480f3` | 4 | 0 | 5/7 ⚠ |
| 1996-06-17 | `76f78b8480f3` | 4 | 4 | 6/7 ⚠ |
| 1996-10-26 | `0e764850fc22` | 4 | 5 | 8/11 ⚠ |
| 1997-04-01 | `76f78b8480f3` | 4 | 0 | 5/5 |
| 1997-08-24 | `31b4465ce221` | 4 | 0 | 5/5 |
| 1999-03-02 | `76f78b8480f3` | 4 | 0 | 5/7 ⚠ |
| 1999-06-14 | `76f78b8480f3` | 4 | 0 | 5/6 ⚠ |
| 2001-10-05 | `76f78b8480f3` | 4 | 4 | 5/6 ⚠ |
| 2002-04-30 | `31b4465ce221` | 4 | 0 | 6/6 |
| 2003-07-29 | `31b4465ce221` | 4 | 0 | 6/6 |
| 2007-04-04 | `76f78b8480f3` | 4 | 5 | 6/6 |
| 2007-04-15 | `76f78b8480f3` | 4 | 6 | 7/7 |
| 2009-07-05 | `76f78b8480f3` | 4 | 11 | 7/7 |
| 1979-11-16 | `0e764850fc22` | 3 | 0 | 7/7 |
| 1980-11-16 | `0e764850fc22` | 3 | 0 | 14/14 |
| 1984-07-07 | `0e764850fc22` | 3 | 0 | 11/11 |
| 1987-09-30 | `76f78b8480f3` | 3 | 2 | 4/5 ⚠ |
| 1988-06-07 | `0e764850fc22` | 3 | 3 | 7/10 ⚠ |
| 1991-06-06 | `76f78b8480f3` | 3 | 2 | 6/7 ⚠ |
| 1993-09-08 | `76f78b8480f3` | 3 | 0 | 7/8 ⚠ |
| 1994-02-16 | `0e764850fc22` | 3 | 3 | 7/7 |
| 1996-06-26 | `76f78b8480f3` | 3 | 3 | 5/5 |
| 1996-10-27 | `76f78b8480f3` | 3 | 0 | 6/8 ⚠ |
| 1997-04-11 | `76f78b8480f3` | 3 | 4 | 5/6 ⚠ |
| 1997-08-05 | `76f78b8480f3` | 3 | 4 | 5/7 ⚠ |
| 1998-11-02 | `31b4465ce221` | 3 | 0 | 4/4 |
| 1999-07-06 | `31b4465ce221` | 3 | 0 | 4/5 ⚠ |
| 1999-07-17 | `76f78b8480f3` | 3 | 9 | 6/9 ⚠ |
| 1999-11-11 | `76f78b8480f3` | 3 | 0 | 4/5 ⚠ |
| 1999-11-20 | `76f78b8480f3` | 3 | 4 | 5/7 ⚠ |
| 2000-06-16 | `76f78b8480f3` | 3 | 9 | 6/8 ⚠ |
| 2001-07-18 | `76f78b8480f3` | 3 | 6 | 4/4 |
| 2002-11-09 | `76f78b8480f3` | 3 | 0 | 8/9 ⚠ |
| 2003-10-17 | `76f78b8480f3` | 3 | 48 | 13/14 ⚠ |
| 2004-03-21 | `76f78b8480f3` | 3 | 0 | 5/5 |
| 2008-08-16 | `76f78b8480f3` | 3 | 3 | 4/4 |
| 2009-04-22 | `31b4465ce221` | 3 | 0 | 5/5 |
| 2010-03-23 | `76f78b8480f3` | 3 | 12 | 6/7 ⚠ |
| 2013-10-25 | `76f78b8480f3` | 3 | 0 | 4/5 ⚠ |
| 1961-07-29 | `0e764850fc22` | 2 | 0 | 4/4 |
| 1963-04-12 | `0e764850fc22` | 2 | 0 | 15/15 |
| 1974-01-19 | `0e764850fc22` | 2 | 0 | 14/16 ⚠ |
| 1975-11-11 | `0e764850fc22` | 2 | 0 | 11/13 ⚠ |
| 1975-11-13 | `0e764850fc22` | 2 | 2 | 13/16 ⚠ |
| 1975-12-01 | `0e764850fc22` | 2 | 0 | 8/8 |
| 1978-03-12 | `0e764850fc22` | 2 | 0 | 3/3 |
| 1978-06-07 | `0e764850fc22` | 2 | 0 | 7/7 |
| 1978-10-06 | `0e764850fc22` | 2 | 0 | 7/7 |
| 1980-05-08 | `0e764850fc22` | 2 | 0 | 5/6 ⚠ |
| 1980-11-21 | `0e764850fc22` | 2 | 0 | 9/9 |
| 1981-10-16 | `0e764850fc22` | 2 | 0 | 3/4 ⚠ |
| 1984-06-04 | `0e764850fc22` | 2 | 0 | 7/7 |
| 1987-09-12 | `76f78b8480f3` | 2 | 9 | 7/9 ⚠ |
| 1990-08-12 | `76f78b8480f3` | 2 | 10 | 5/5 |
| 1991-07-20 | `76f78b8480f3` | 2 | 0 | 4/5 ⚠ |
| 1992-08-25 | `76f78b8480f3` | 2 | 0 | 3/4 ⚠ |
| 1992-10-28 | `76f78b8480f3` | 2 | 0 | 4/5 ⚠ |
| 1993-02-12 | `76f78b8480f3` | 2 | 7 | 7/8 ⚠ |
| 1993-04-19 | `0e764850fc22` | 2 | 2 | 6/7 ⚠ |
| 1993-06-17 | `76f78b8480f3` | 2 | 0 | 5/5 |
| 1995-06-16 | `31b4465ce221` | 2 | 0 | 3/3 |
| 1995-07-04 | `76f78b8480f3` | 2 | 0 | 4/5 ⚠ |
| 1995-07-12 | `31b4465ce221` | 2 | 0 | 7/7 |
| 1995-09-27 | `31b4465ce221` | 2 | 0 | 3/3 |
| 1996-08-03 | `76f78b8480f3` | 2 | 0 | 4/5 ⚠ |
| 1996-11-10 | `0e764850fc22` | 2 | 3 | 4/5 ⚠ |
| 1996-11-23 | `76f78b8480f3` | 2 | 0 | 8/11 ⚠ |
| 1997-04-07 | `76f78b8480f3` | 2 | 3 | 4/6 ⚠ |
| 1997-04-13 | `76f78b8480f3` | 2 | 3 | 4/8 ⚠ |
| 1997-05-02 | `76f78b8480f3` | 2 | 3 | 4/4 |
| 1997-08-09 | `76f78b8480f3` | 2 | 0 | 3/4 ⚠ |
| 1997-08-18 | `76f78b8480f3` | 2 | 0 | 4/7 ⚠ |
| 1997-08-22 | `76f78b8480f3` | 2 | 3 | 4/7 ⚠ |
| 1997-11-04 | `76f78b8480f3` | 2 | 0 | 4/5 ⚠ |
| 1997-12-01 | `76f78b8480f3` | 2 | 25 | 9/11 ⚠ |
| 1997-12-16 | `31b4465ce221` | 2 | 0 | 6/8 ⚠ |
| 1997-12-17 | `31b4465ce221` | 2 | 0 | 4/7 ⚠ |
| 1997-12-19 | `76f78b8480f3` | 2 | 3 | 4/7 ⚠ |
| 1998-03-31 | `76f78b8480f3` | 2 | 0 | 5/7 ⚠ |
| 1998-06-07 | `76f78b8480f3` | 2 | 2 | 5/6 ⚠ |
| 1998-06-20 | `76f78b8480f3` | 2 | 2 | 5/8 ⚠ |
| 1998-09-22 | `31b4465ce221` | 2 | 0 | 5/5 |
| 1999-04-07 | `76f78b8480f3` | 2 | 0 | 3/4 ⚠ |
| 1999-04-10 | `76f78b8480f3` | 2 | 3 | 5/7 ⚠ |
| 1999-04-22 | `0e764850fc22` | 2 | 2 | 7/8 ⚠ |
| 1999-05-02 | `31b4465ce221` | 2 | 0 | 5/5 |
| 1999-06-07 | `76f78b8480f3` | 2 | 11 | 6/7 ⚠ |
| 1999-11-19 | `76f78b8480f3` | 2 | 29 | 9/14 ⚠ |
| 2000-10-02 | `76f78b8480f3` | 2 | 3 | 6/9 ⚠ |
| 2001-07-25 | `76f78b8480f3` | 2 | 2 | 4/5 ⚠ |
| 2001-10-30 | `76f78b8480f3` | 2 | 2 | 7/10 ⚠ |
| 2002-02-05 | `76f78b8480f3` | 2 | 0 | 3/3 |
| 2003-04-19 | `76f78b8480f3` | 2 | 6 | 7/7 |
| 2003-05-10 | `76f78b8480f3` | 2 | 17 | 7/7 |
| 2003-10-16 | `76f78b8480f3` | 2 | 0 | 5/5 |
| 2004-11-03 | `31b4465ce221` | 2 | 0 | 4/4 |
| 2006-11-16 | `31b4465ce221` | 2 | 0 | 5/5 |
| 2007-10-05 | `76f78b8480f3` | 2 | 0 | 4/4 |
| 2009-10-23 | `31b4465ce221` | 2 | 0 | 3/3 |
| 2010-03-26 | `76f78b8480f3` | 2 | 3 | 5/6 ⚠ |
| 2013-10-18 | `76f78b8480f3` | 2 | 0 | 7/9 ⚠ |
| 2014-07-03 | `0e764850fc22` | 2 | 0 | 4/4 |
| 1961-09-06 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1963-10-26 | `0e764850fc22` | 1 | 0 | 7/7 |
| 1964-11-27 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1965-12-12 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1966-03-12 | `0e764850fc22` | 1 | 0 | 2/3 ⚠ |
| 1974-01-07 | `0e764850fc22` | 1 | 1 | 7/9 ⚠ |
| 1974-05-09 | `0e764850fc22` | 1 | 0 | 5/5 |
| 1975-10-31 | `0e764850fc22` | 1 | 0 | 10/15 ⚠ |
| 1975-11-02 | `0e764850fc22` | 1 | 0 | 2/3 ⚠ |
| 1975-11-06 | `0e764850fc22` | 1 | 0 | 6/6 |
| 1975-11-08 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1976-04-27 | `0e764850fc22` | 1 | 0 | 2/3 ⚠ |
| 1976-05-03 | `0e764850fc22` | 1 | 0 | 11/11 |
| 1976-05-08 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1978-03-27 | `0e764850fc22` | 1 | 0 | 3/3 |
| 1978-10-12 | `0e764850fc22` | 1 | 0 | 5/5 |
| 1978-10-27 | `0e764850fc22` | 1 | 0 | 3/3 |
| 1978-11-11 | `0e764850fc22` | 1 | 0 | 6/6 |
| 1978-11-13 | `0e764850fc22` | 1 | 0 | 2/3 ⚠ |
| 1978-12-05 | `0e764850fc22` | 1 | 0 | 3/4 ⚠ |
| 1980-12-02 | `0e764850fc22` | 1 | 0 | 3/3 |
| 1981-07-10 | `0e764850fc22` | 1 | 0 | 8/9 ⚠ |
| 1981-10-25 | `0e764850fc22` | 1 | 0 | 3/3 |
| 1981-11-05 | `0e764850fc22` | 1 | 0 | 2/2 |
| 1981-11-11 | `0e764850fc22` | 1 | 0 | 5/5 |
| 1982-06-06 | `0e764850fc22` | 1 | 0 | 4/4 |
| 1984-06-13 | `0e764850fc22` | 1 | 0 | 9/9 |
| 1984-06-16 | `0e764850fc22` | 1 | 1 | 8/8 |
| 1984-06-26 | `0e764850fc22` | 1 | 0 | 6/6 |
| 1984-06-30 | `0e764850fc22` | 1 | 0 | 6/6 |
| 1984-07-08 | `0e764850fc22` | 1 | 0 | 14/14 |
| 1986-07-31 | `0e764850fc22` | 1 | 0 | 9/9 |
| 1987-10-07 | `76f78b8480f3` | 1 | 0 | 2/5 ⚠ |
| 1989-07-03 | `76f78b8480f3` | 1 | 0 | 3/3 |
| 1990-11-12 | `76f78b8480f3` | 1 | 0 | 5/6 ⚠ |
| 1991-06-19 | `76f78b8480f3` | 1 | 1 | 5/8 ⚠ |
| 1992-05-08 | `76f78b8480f3` | 1 | 0 | 4/5 ⚠ |
| 1993-08-20 | `76f78b8480f3` | 1 | 0 | 3/3 |
| 1993-08-21 | `76f78b8480f3` | 1 | 0 | 2/3 ⚠ |
| 1993-09-09 | `76f78b8480f3` | 1 | 0 | 4/6 ⚠ |
| 1993-11-16 | `76f78b8480f3` | 1 | 0 | 12/15 ⚠ |
| 1994-04-22 | `76f78b8480f3` | 1 | 0 | 3/3 |
| 1994-10-19 | `76f78b8480f3` | 1 | 0 | 7/8 ⚠ |
| 1994-10-23 | `76f78b8480f3` | 1 | 0 | 3/4 ⚠ |
| 1995-04-09 | `0e764850fc22` | 1 | 1 | 5/7 ⚠ |
| 1995-05-25 | `0e764850fc22` | 1 | 2 | 6/9 ⚠ |
| 1995-06-29 | `31b4465ce221` | 1 | 0 | 2/2 |
| 1995-09-23 | `31b4465ce221` | 1 | 0 | 3/4 ⚠ |
| 1995-09-30 | `31b4465ce221` | 1 | 0 | 4/4 |
| 1995-10-06 | `31b4465ce221` | 1 | 0 | 3/3 |
| 1995-10-25 | `31b4465ce221` | 1 | 0 | 4/4 |
| 1997-12-20 | `31b4465ce221` | 1 | 0 | 4/7 ⚠ |
| 1998-07-11 | `31b4465ce221` | 1 | 0 | 3/3 |
| 1998-09-03 | `31b4465ce221` | 1 | 0 | 3/3 |
| 1998-10-25 | `76f78b8480f3` | 1 | 5 | 4/6 ⚠ |
| 1999-01-30 | `31b4465ce221` | 1 | 0 | 5/6 ⚠ |
| 1999-04-28 | `31b4465ce221` | 1 | 0 | 4/4 |
| 1999-04-30 | `31b4465ce221` | 1 | 0 | 3/3 |
| 1999-06-06 | `31b4465ce221` | 1 | 0 | 2/2 |
| 1999-07-31 | `31b4465ce221` | 1 | 0 | 4/4 |
| 1999-10-27 | `31b4465ce221` | 1 | 0 | 4/4 |
| 1999-10-29 | `76f78b8480f3` | 1 | 8 | 7/8 ⚠ |
| 1999-10-30 | `31b4465ce221` | 1 | 0 | 6/6 |
| 1999-11-14 | `76f78b8480f3` | 1 | 11 | 6/8 ⚠ |
| 2000-03-15 | `76f78b8480f3` | 1 | 5 | 8/9 ⚠ |
| 2000-05-23 | `76f78b8480f3` | 1 | 2 | 4/5 ⚠ |
| 2000-06-18 | `31b4465ce221` | 1 | 0 | 5/5 |
| 2000-07-07 | `76f78b8480f3` | 1 | 5 | 5/6 ⚠ |
| 2000-07-11 | `31b4465ce221` | 1 | 0 | 3/3 |
| 2000-10-31 | `76f78b8480f3` | 1 | 13 | 6/7 ⚠ |
| 2000-11-19 | `31b4465ce221` | 1 | 0 | 5/6 ⚠ |
| 2002-04-16 | `31b4465ce221` | 1 | 0 | 6/6 |
| 2002-04-23 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2002-05-08 | `31b4465ce221` | 1 | 0 | 5/6 ⚠ |
| 2002-08-03 | `31b4465ce221` | 1 | 0 | 8/8 |
| 2003-02-11 | `76f78b8480f3` | 1 | 2 | 3/3 |
| 2003-05-06 | `31b4465ce221` | 1 | 0 | 2/2 |
| 2003-05-18 | `31b4465ce221` | 1 | 0 | 2/2 |
| 2003-07-17 | `31b4465ce221` | 1 | 0 | 5/5 |
| 2003-10-18 | `76f78b8480f3` | 1 | 3 | 5/6 ⚠ |
| 2004-03-03 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2004-06-06 | `76f78b8480f3` | 1 | 13 | 6/6 |
| 2004-11-02 | `31b4465ce221` | 1 | 0 | 6/6 |
| 2007-04-14 | `76f78b8480f3` | 1 | 2 | 3/3 |
| 2007-08-13 | `31b4465ce221` | 1 | 0 | 3/3 |
| 2007-08-15 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2008-06-16 | `76f78b8480f3` | 1 | 2 | 5/5 |
| 2008-07-08 | `31b4465ce221` | 1 | 0 | 2/2 |
| 2008-10-30 | `31b4465ce221` | 1 | 0 | 2/2 |
| 2009-04-25 | `76f78b8480f3` | 1 | 2 | 6/6 |
| 2009-05-05 | `31b4465ce221` | 1 | 0 | 4/4 |
| 2009-10-10 | `76f78b8480f3` | 1 | 6 | 6/6 |
| 2010-03-28 | `76f78b8480f3` | 1 | 18 | 8/9 ⚠ |
| 2010-03-29 | `76f78b8480f3` | 1 | 27 | 9/9 |
| 2010-06-13 | `31b4465ce221` | 1 | 0 | 3/4 ⚠ |
| 2011-06-27 | `76f78b8480f3` | 1 | 4 | 4/5 ⚠ |
| 2013-10-22 | `76f78b8480f3` | 1 | 0 | 6/8 ⚠ |
| 2013-11-03 | `76f78b8480f3` | 1 | 0 | 4/4 |
| 2014-04-05 | `76f78b8480f3` | 1 | 0 | 6/6 |
| 2014-04-09 | `76f78b8480f3` | 1 | 0 | 5/5 |
| 2014-06-29 | `76f78b8480f3` | 1 | 0 | 4/4 |
| 2014-07-07 | `76f78b8480f3` | 1 | 0 | 6/6 |

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
| 2003-07-31 | `0e764850fc22` | 13 | 6/6 | 2026-08-07 |
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
| 2011-10-16 | `0e764850fc22` | 10 | 5/5 | 2026-08-07 |
| 1986-02-24 | `0e764850fc22` | 9 | 15/16 ⚠ incomplete | 2026-07-28 |
| 1987-09-12 | `76f78b8480f3` | 9 | 7/9 ⚠ incomplete | 2026-07-17 |
| 1994-07-10 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-19 |
| 1995-03-12 | `0e764850fc22` | 9 | 7/12 ⚠ incomplete | 2026-07-28 |
| 1997-12-14 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-17 |
| 1999-06-05 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-17 |
| 1999-07-17 | `76f78b8480f3` | 9 | 6/9 ⚠ incomplete | 2026-07-17 |
| 1999-09-08 | `76f78b8480f3` | 9 | 5/6 ⚠ incomplete | 2026-07-18 |
| 2000-06-16 | `76f78b8480f3` | 9 | 6/8 ⚠ incomplete | 2026-07-18 |
| 2007-04-06 | `76f78b8480f3` | 9 | 5/5 | 2026-07-17 |
| 2009-04-05 | `76f78b8480f3` | 9 | 7/7 | 2026-07-18 |
| 2011-10-20 | `0e764850fc22` | 9 | 5/5 | 2026-08-07 |
| 1999-10-29 | `76f78b8480f3` | 8 | 7/8 ⚠ incomplete | 2026-07-18 |
| 2000-09-23 | `76f78b8480f3` | 8 | 5/9 ⚠ incomplete | 2026-07-17 |
| 1993-02-12 | `76f78b8480f3` | 7 | 7/8 ⚠ incomplete | 2026-07-19 |
| 1995-04-03 | `0e764850fc22` | 7 | 9/10 ⚠ incomplete | 2026-07-28 |
| 1997-04-18 | `76f78b8480f3` | 7 | 5/9 ⚠ incomplete | 2026-07-17 |

_3062 stale dates in total; the 3002 beyond the top 60 carry no recorded flips._


Of the 3062 stale dates, 940 also ran on an incomplete set (TODO-334), so their family counts are provisional for a second, independent reason.

