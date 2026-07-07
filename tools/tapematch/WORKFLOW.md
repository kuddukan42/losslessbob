# tapematch improvement workflow

Hand this file to Claude at the start of each session.

---

## What this tool does

tapematch analyses a set of Bob Dylan audience recordings of the same concert date
and determines which recordings share a common source tape (same taper/transfer).
It uses three layers of evidence in order of strength:

1. **Primary residual correlation** — HF diff cross-correlation at 12 anchor windows.
   Catches clean same-source pairs (no timing edits between them).

2. **Secondary match** — runs only for cross-family pairs (primary below threshold):
   - *Windowed coverage*: 60s-window dense grid, per-window ±5s lag search.
     Catches remasters whose edits cluster at track boundaries (within-track audio
     stays coherent). **This drives secondary clustering.**
   - *Quiet-segment hiss*: correlates between-song low-energy sections.
     Catches EQ/NR applied to music but not to tape hiss texture.

3. **Fingerprint** (confirmatory only, does NOT cluster):
   Shazam-style (f_anchor, f_target, Δt) hash set from the first 10 min of music
   (minutes 3–13). Dice score > 0.60 confirms same recording chain.
   **Known limitation**: live recordings of the same show score 0.15–0.50 from
   shared musical-note peaks → threshold must stay above ~0.55 to avoid false
   positives. Only used as evidence, never for grouping decisions.

---

## One iteration = one concert date

### Step 1 — pick a date

```bash
cd /home/tjenkins/Documents/losslessbob
.venv/bin/python3 tools/tapematch/tapematch_session.py --suggest
```

Shows dates with **3–5 collected entries that have local LB pages and have not
been analysed yet**. Pick one from the list.

### Step 2 — run the session

```bash
.venv/bin/python3 tools/tapematch/tapematch_session.py YYYY-MM-DD
```

This will:
- Copy the LB folders to `/mnt/DATA0/examples/tapematch/`
- Run tapematch (primary + secondary + fingerprint)
- Archive results to `tools/tapematch/runs/`
- Log every pair to `tools/tapematch/observations.db`
- Write `tools/tapematch/last_run_report.md`

### Step 3 — analyse with Claude

Tell Claude to read `last_run_report.md`.
Ask Claude to compare verdicts against LB commentary and identify:
- Pairs where tapematch grouped incorrectly (missed same-source or false-grouped)
- Which layer (primary / windowed / hiss / fingerprint) was responsible
- What change to make

### Step 4 — apply the fix

Claude edits `config.yaml` and/or `tools/tapematch/tapematch/*.py`.

### Step 5 — re-run same date to verify

```bash
.venv/bin/python3 tools/tapematch/tapematch_session.py YYYY-MM-DD
```

Once the date looks correct, go back to Step 1 with a new date.

---

## Reading the output

### SECONDARY MATCH section

```
LB-06986 / LB-00513: windowed 0.69 (176 win, med 0.813); hiss 0.59 (116 segs, med 0.737);
                     fingerprint Dice 0.695 (61450 / 61195 hashes)  [primary corr 0.023] → SECONDARY LINK
```

All three signals confirm the same-source verdict for this pair.
If only fingerprint triggers (no windowed/hiss), treat with scepticism — could be
same-show musical content similarity rather than same recording chain.

### CLUSTERS section

```
Family 3: LB-06986, LB-00513  (mean intra-corr 0.023 [low confidence])
          [secondary: LB-06986/LB-00513 via windowed 0.69+hiss 0.59+fp 0.695]
```

`[low confidence]` on a secondary-linked family is expected — primary corr was
below threshold; the link is carried by windowed/hiss evidence.

### DIAGNOSTICS section

- `[SECONDARY SAME-SOURCE]` — pair grouped via secondary evidence; verify against LB commentary
- `[DISTINCT SOURCE]` — singleton with near-zero correlation to everything; confirmed different recording
- `[INCOMPLETE]` — recording is >5% shorter than group median; likely truncated

---

## Key files

| File | Purpose |
|------|---------|
| `tools/tapematch/config.yaml` | All tunable knobs — edit here first |
| `tools/tapematch/tapematch/cli.py` | Analysis pipeline — primary + secondary + fingerprint |
| `tools/tapematch/tapematch/match.py` | Correlation, clustering, secondary_corr_pair, fingerprint_window |
| `tools/tapematch/tapematch/verdict.py` | Single source of truth for the pairwise clustering decision (thresholds + conditional relaxations) |
| `tools/tapematch/regression.py` | Recall/precision regression harness — `freeze` / `score --cached` / `score --dates` vs the frozen labeled set |
| `tools/tapematch/tapematch/align.py` | Anchor detection, local_lag, lag curve interpretation |
| `tools/tapematch/tapematch_session.py` | Session orchestrator |
| `tools/tapematch/last_run_report.md` | Latest human-readable report |
| `tools/tapematch/last_run.log` | Raw tapematch stdout |
| `tools/tapematch/observations.db` | Accumulated pair observations across all runs |
| `tools/tapematch/runs/` | Archived logs/reports/configs per run |

---

## Config knobs (most commonly tuned)

### Trim (head/tail crowd-padding removal)

| Knob | Current | Effect |
|------|---------|--------|
| `trim.flatness_music_max` | 0.45 | Frame counts as "music" if spectral flatness is below this. In practice flatness stays well under this on every source tested (real or synthetic) — it does not gate; the energy term below does all the work. |
| `trim.min_sustain_sec` | 8.0 | Continuous music-seconds required to declare show start/end. |
| `trim.pad_keep_sec` | 5.0 | Safety margin kept either side of the detected boundary. |
| `trim.min_dynamic_range_db` | 10.0 | (BUG-235, 2026-07-03) If whole-source energy spread (p90-p10) is below this, skip trim entirely and keep the full recording. Heavily normalised/compressed releases put crowd padding and performance within a few dB of each other, so the fixed p10+6dB energy gate chatters every 1-3s instead of forming sustained blocks — `_first_sustained` then locks onto a spurious tiny run and cuts 30-70% of the recording. Calibrated: known-good controls measure 11.9-15.4dB spread; broken 2025-11-16/17 Glasgow sources measured 6.4-8.5dB. |

### Primary

| Knob | Current | Effect |
|------|---------|--------|
| `match.cluster_threshold` | 0.45 | Raise = fewer false positives; lower = catches more degraded same-source |
| `anchors.n_anchors` | 12 | Higher = more robust to track-break lag errors |
| `anchors.window_sec` | 45.0 | Wider = more audio per anchor comparison |
| `align.ratio_flag_ppm` | 200 | Speed offset before resampling kicks in |
| `align.ratio_confidence_min` | 6.0 | `estimate_ratio_v2` peak-prominence confidence below this ⇒ `speed-unknown`: don't resample (untrusted ratio). Sweep to 4.5 recovered nothing — stranded pairs resample but corr stays ~0.005, so they don't correlate regardless. |
| `align.pyin_fallback` | true | Use `pitch_ratio_pyin` (absolute-pitch ratio) for speed-unknown pairs with no duration prior. Rarely fires; ±5800 ppm resolution limits it. |
| `align.step_flag_sec` | 0.5 | Lag jump threshold for staircase detection |

### Secondary (windowed / hiss)

| Knob | Current | Effect |
|------|---------|--------|
| `secondary_match.coverage_threshold` | 0.35 | Fraction of windows that must agree to link |
| `secondary_match.local_lag_sec` | 10.0 | ±lag search per window; covers up to 10s accumulated drift |
| `secondary_match.window_corr_threshold` | 0.30 | Per-window residual corr to count as matching |
| `secondary_match.hiss_frac_threshold` | 0.40 | Fraction of quiet segs that must correlate |
| `secondary_match.short_window_sec` | 15.0 | Fallback window size for staircase/staircase pairs |
| `secondary_match.short_hop_sec` | 5.0 | Hop for short-window fallback |
| `secondary_match.hiss_merge_median` | 0.65 | Min hiss median to drive a merge (room-ambience FP guard) |
| `secondary_match.hiss_merge_median_lofi` | 0.40 | Relaxed median when BOTH sides `hf_ceiling_hz` < `hiss_lofi_ceiling_hz` and neither is nyquist-capped (Task 4.2) |
| `secondary_match.hiss_lofi_ceiling_hz` | 12000 | Below this on both sides ⇒ treat as lo-fi cassette generation |

### Fingerprint

| Knob | Current | Effect |
|------|---------|--------|
| `fingerprint.hf_band_hz` | [6000, 8000] | HF-only peak-finding — reduces same-show false matches |
| `fingerprint.match_threshold` | 0.60 | Display threshold for fingerprint evidence |
| `fingerprint.cluster_threshold` | 0.50 | Dice above this drives clustering (safe with `hf_band_hz`) |
| `fingerprint.cluster_threshold_staircase` | 0.40 | Relaxed Dice bar when either side is staircase-flagged (Task 3.2) |
| `fingerprint.cluster_threshold_curator` | 0.43 | Relaxed Dice bar when curator lineage text claims same source (Task 4.1); text is a prior — audio must still cross it |
| `fingerprint.window_start_sec` | 180 | Skip intro/tuning; set higher if shows start late |
| `fingerprint.window_dur_sec` | 600 | 10-min window; increase for more hashes (slower) |
| `fingerprint.fanout` | 5 | Landmark pairs per peak; increase for more hashes |
| `fingerprint.triplet.enabled` | **false** | Ratio-invariant triplet fingerprint (Task 7). **DISABLED** — real same-show different-source pairs collide (Dice 0.63–0.65, overlapping true same-source 0.66); at 0.45 it made 5 false merges. Re-enable only if calibration ever shows a ≥0.10 TP/TN gap. |
| `fingerprint.triplet.cluster_threshold` | 0.45 | Provisional only — NOT viable at 6/7-bit quant (see `calibrate_triplet.py`). |

### Shared-flaw event fingerprint (CC_TAPEMATCH_ADDON.md Task 2)

| Knob | Current | Effect |
|------|---------|--------|
| `flaw_fingerprint.enabled` | **false** | Master switch. Off = zero cost (extraction skipped entirely) and the OR-path is inert (NULL columns). **NOT yet calibrated** — do not enable without a real-audio gap check per the Calibration protocol. |
| `flaw_fingerprint.dropout_depth_db` / `dropout_min_sec` / `dropout_max_sec` | 20.0 / 0.04 / 0.8 | Short-time RMS collapse vs. its 2s local median — the "dropout" event. |
| `flaw_fingerprint.click_sigma` / `click_max_dur_ms` / `click_cap` | 6.0 / 5.0 / 200 | Sample-domain residual spike vs. local MAD — the "click" event; isolated + capped to the 200 strongest/source. |
| `flaw_fingerprint.cut_sigma` | 4.0 | Joint 100ms spectral-centroid + RMS discontinuity — the "cut"/splice event. |
| `flaw_fingerprint.flaw_min_events` | 5 | `flaw_match_score` is `None` (not 0.0) below `min(|A|,|B|)` events. |
| `flaw_fingerprint.tol_sec` | 0.5 | Matched-event time tolerance after speed-mapping A onto B's clock. |
| ~~`flaw_fingerprint.merge_threshold` / `min_events_merge`~~ | removed | **SUPERSEDED by `addon_links.rule_a` (Task 5)** — the standalone flaw OR-path that used to live directly in `verdict.py:pair_links` was folded into Rule A; see the Task 5 section below. |

### Spectral-ratio stationarity (CC_TAPEMATCH_ADDON.md Task 3)

| Knob | Current | Effect |
|------|---------|--------|
| `spectral_stationarity.enabled` | **false** | Master switch. Off = zero cost (metric call skipped, NULL column). **NOT yet calibrated** — do not enable without a real-audio gap check per the Calibration protocol. Registered in `verdict.METRIC_KEYS` but has **no OR-path** — conjunctive-only per spec; combination rules are Task 5's `addon_links`. |
| `spectral_stationarity.window_sec` / `hop_sec` / `local_lag_sec` | 60.0 / 30.0 / 10.0 | Windowed-coverage grid (own knobs, mirrors `secondary_match`'s shape but independent config): each window does its own local-lag search (or predicted-lag centered search under a large speed offset) before scoring. |
| `spectral_stationarity.n_mels` | 32 | Log-mel band count, capped at `min(hf_ceiling_a, hf_ceiling_b, 0.45*sr)` — never compares above the narrower side's HF ceiling. |
| `spectral_stationarity.stft_nperseg` / `stft_hop` | 1024 / 256 | STFT front end feeding the mel filterbank (via `librosa.filters.mel`). |
| `spectral_stationarity.noise_floor_margin_db` | 6.0 | A frame is scored only if both sides are this far above their own `lineage_evidence` `noise_floor_db` — skips quiet frames per side. |
| `spectral_stationarity.min_frames_per_window` | 20 | Below this many usable (non-quiet) STFT frames, the window is skipped (not scored 0). |
| `spectral_stationarity.stationarity_norm_db` | 6.0 | `1 - mean_band(std_w(R_w)) / norm_db`, clipped to [0,1] — a 6dB per-band wobble across the show maps to 0. |
| `spectral_stationarity.stationarity_min_windows` | 6 | Fewer usable windows → `None`, not 0.0 (absence of evidence, not evidence of instability). |

### Band-limited envelope correlation (CC_TAPEMATCH_ADDON.md Task 4)

| Knob | Current | Effect |
|------|---------|--------|
| `envelope_corr.enabled` | **false** | Master switch. Off = zero cost (metric call skipped, NULL column). **NOT yet calibrated** — do not enable without a real-audio gap check per the Calibration protocol. Registered in `verdict.METRIC_KEYS` but has **no OR-path**, and per spec 4.2 **never gets one even after calibration** — highest same-show collision risk of any Tier A signal (envelope is music-dominated, the triplet failure mode); it may only ever be wired as one AND'd leg of a Task 5 `addon_links` rule. |
| `envelope_corr.band_lo_hz` / `band_hi_cap_hz` | 200.0 / 2000.0 | Bandpass limits; actual high edge is `min(hf_ceiling_a, hf_ceiling_b, band_hi_cap_hz)` — never above the narrower side's HF ceiling. |
| `envelope_corr.filter_order` | 6 | Zero-phase Butterworth bandpass order (`sosfiltfilt`). |
| `envelope_corr.frame_rate_hz` | 20.0 | RMS-envelope frame rate for both sides before speed-mapping + Pearson. |
| `envelope_corr.min_overlap_min` | 10.0 | Mapped overlap below this many minutes → `None`, not 0.0 (absence of evidence, not evidence of difference). |

### Evidence combination + coverage (CC_TAPEMATCH_ADDON.md Task 5)

`verdict.py` gains an `addon_links` block, evaluated alongside every other OR-path in
`pair_links`. Every rule is independently gated on its own `enabled` flag; NULL on ANY leg
means that rule ABSTAINS (never coerced to 0.0/False-as-0.0). No rule reads `lb_says_same`
or `entry_lineage`. All three `enabled: false` until each contributing signal clears the
Calibration protocol.

| Knob | Current | Effect |
|------|---------|--------|
| `addon_links.rule_a.enabled` / `t_flaw` / `min_events` | false / 0.6 / 8 | **Rule A (lone lineage)** — `flaw_match_score >= t_flaw` AND both-side `flaw_n_events >= min_events`. This is now the **sole canonical flaw-fingerprint merge path**, replacing the Task 2.3 standalone OR-leg (`flaw_fingerprint.enabled` still separately gates whether the metric is *computed*, not whether it may merge). |
| `addon_links.rule_b.enabled` / `t_stat` / `t_env` | false / 0.7 / 0.90 | **Rule B (two-leg)** — `spec_stationarity >= t_stat` AND `env_corr >= t_env`. Conjunctive by construction: the only route either signal has into a verdict (both are individually banned from a lone-merge path). |
| `addon_links.rule_c.enabled` / `t_emb` / `t_flaw_weak` / `t_stat` | false / 0.70 / 0.4 / 0.7 | **Rule C (belt-and-braces, Tier B/C)** — `emb_score >= t_emb` AND (`flaw_match_score >= t_flaw_weak` OR `spec_stationarity >= t_stat`). `emb_score` (Task 6) has no persisted column yet — the rule reads it via `dict.get` and abstains defensively rather than crashing while it's absent. |

**Coverage instrumentation**: `regression.py score --cached` now prints a per-signal line —
for each of `flaw_match_score` / `spec_stationarity` / `env_corr` / `emb_score` that exists
as a `pairs` column, how many frozen FN pairs (positives the candidate verdicts
`different_family`) carry a non-NULL value. This bounds each signal's max possible recall
contribution and surfaces low-coverage signals immediately (e.g. "works but only 40 pairs
have flaws"). Example output:

```
addon-links signal coverage (frozen FN, n=920) — bounds each signal's max recall contribution:
  flaw_match_score    :     0 / 920    (  0.0%)
  spec_stationarity   :     0 / 920    (  0.0%)
```

(`env_corr` / `emb_score` are omitted here because those columns don't exist yet in this
`observations.db` — they only appear once/if `open_obs_db()`'s idempotent `ALTER` has run.)

---

## Known failure modes and what handles each

| Failure mode | Example | Detection |
|---|---|---|
| Heavily normalised/compressed source spuriously mistrimmed (crowd/music energy contrast <10dB) | 2025-11-16/17 Glasgow LB-16525/16526/16545 (BUG-235, fixed) | `trim.min_dynamic_range_db` guard — skips trim, keeps full recording |
| Clean same-source, different trim | Most pairs | Primary residual corr |
| Speed difference (DAT pitch drift) | 1998-10-28 LB-06564/LB-12485 | Primary + estimate_ratio resample |
| Edited remaster (track boundary edits) | 1996-07-21 LB-06986/LB-00513 | Windowed coverage + hiss + fingerprint |
| Heavy EQ/NR on music, hiss intact | (not yet observed) | Quiet-segment hiss |
| Dithered amplitude remaster | (not yet observed alone) | Fingerprint (cluster_threshold) |
| Staircase/CDR re-tracking (one side) | 1996-07-21 LB-06984↔LB-06985 | Lag curve staircase flag |
| Staircase/staircase (both sides) | 2001 tour many pairs | Short-window fallback (15s windows) |
| Large timing drift (>3 min content diff) | 2001-07-03 LB-417/LB-56 | [TIMING MISMATCH] diagnostic |
| Incomplete recording | 1996-07-21 LB-06984 | [INCOMPLETE] diagnostic |
| Confident speed offset, still no corr | 1994-04-28 LB-05569/* | `constant-speed-offset` resample applied, corr still ~0.005 — NON-RECOVERABLE (different generation/noise). Cat-1. |
| Low-confidence ratio (speed-unknown) | 1994-07-04 LB-06863/LB-12340 (−45800 ppm) | `estimate_ratio_v2` conf < 6.0 ⇒ not resampled. Triplet fallback (Task 7) was the intended rescue but is disabled — currently UNRECOVERABLE. |
| Same show, band-limited lo-fi siblings | 1987-09-19 LB-00131/LB-05156 (2–3 kHz ceilings) | NON-RECOVERABLE by any in-scope signal; needs learned similarity (out of scope). |
| corr<0.05, HF fine-structure destroyed but tape flaws (dropouts/clicks/splices) inherited | Target population for CC_TAPEMATCH_ADDON Task 2 | Shared-flaw event fingerprint (`flaw_fingerprint`) — content-blind by construction, so it survives band-limiting where residual_corr/HF fingerprint both die. **Not yet calibrated/enabled.** |
| corr<0.05, HF fine-structure destroyed but a fixed copy-chain EQ/band-limit ties both sides' magnitude spectra together over time | Target population for CC_TAPEMATCH_ADDON Task 3 | Spectral-ratio stationarity (`spectral_stationarity`) — phase-blind, magnitude-only frame-wise log-spectral ratio; constant over time for same-lineage pairs, time-varying for independent recordings. **Conjunctive-only by spec (no lone-merge path); not yet calibrated/enabled.** |
| corr<0.05, HF fine-structure destroyed but the surviving low/mid-band (200Hz–2kHz) RMS energy envelope still tracks between sides | Target population for CC_TAPEMATCH_ADDON Task 4 | Band-limited envelope correlation (`envelope_corr`) — Pearson correlation of speed-mapped RMS envelopes. **High same-show collision risk (music-dominated); conjunctive-only, never a lone-merge path even if calibrated (hard spec rule); not yet calibrated/enabled.** |

### Critical implementation note — do NOT resample before secondary_corr_pair

`resample_poly` smears the HF fine-structure that `residual_corr` relies on.
Even a 500 ppm resample drops correlation from ~0.78 to ~0.07 on same-source pairs.
The per-window local lag search absorbs speed differences natively (±10s covers
accumulated drift from ≤10000 ppm over the first ~70% of any 90-min show).

---

## Querying the observations DB

```bash
cd /home/tjenkins/Documents/losslessbob
.venv/bin/python3 - <<'EOF'
import sqlite3
conn = sqlite3.connect("tools/tapematch/observations.db")

# Pairs where LB says same but tapematch said different
rows = conn.execute("""
    SELECT concert_date, lb_a, lb_b, corr, tapematch_verdict, lb_says_same
    FROM pairs
    WHERE lb_says_same = 1 AND tapematch_verdict = 'different_family'
    ORDER BY concert_date, corr DESC
""").fetchall()
for r in rows:
    print(r)
EOF
```

---

## Fingerprint calibration notes

The fingerprint uses `hf_band_hz: [6000, 8000]` (tape hiss / room band only).
`cluster_threshold: 0.50` is calibrated across three dates (2001-10-07, 1996-07-21,
2001-10-30):

| Category | Observed HF-band Dice range |
|---|---|
| Same-source pairs | 0.51–0.60+ |
| Different-source, same show | 0.35–0.47 |
| Different-source, different show | 0.01–0.05 |

The bimodal gap (0.47–0.51) is stable across outdoor and indoor venues. Note that the
6–8 kHz band still carries shared room/PA acoustics within a venue, so scores do NOT
drop to ~0.10 as the full-band theory predicted — but the gap is reliably present.

If different-source same-show scores creep above 0.47 on a new date, raise
`cluster_threshold` to 0.52. If same-source pairs are being missed by fingerprint alone,
lower `fanout` or increase `window_dur_sec`.

---

## What private LBs are

Entries in `my_collection` whose folder path contains "PRIVATE LB" or "NO TORRENT"
typically don't have a local LB page and are excluded automatically by the session
script. They appear in the DB coverage table as "not found" but are not copied or
analysed.
