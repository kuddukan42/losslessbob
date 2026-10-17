# CC_CONCERT_RANKER.md — Audio Quality Ranking for LosslessBob

Handoff spec for Claude Code. The **scoring brain** (DSP feature extraction,
human-readable banding, MAD-z sibling normalization, two-stage scoring,
calibration harness) is already built and tested — see the attached
`concert_ranker/` package. Your job is the parts that require the real machine:
DB integration, mining, the staging run loop, and calibration against real audio.

## What already exists (do not rebuild)

```
concert_ranker/
  config.py        # ALL thresholds/weights/bands, externalized. # CALIBRATE markers.
  audio/cache.py   # TrackCache + NativeProbe. ONE decode + ONE STFT per track.
  features.py      # clarity / crowd / tonal / distortion / spatial / hf_native
  scoring.py       # band_metric, check_disqualifiers, mad_z, fusion, explain_recording
  calibrate.py     # score_separation, fit_thresholds, validate_labels
```

Verified working end-to-end on synthetic audio. The scoring brain is correct;
the thresholds are first-principles guesses awaiting calibration.

## Architectural decisions already made (honor these)

1. **One decode + one STFT per track.** Every feature reads `TrackCache`. No
   extractor decodes or STFTs. This is the difference between days and months at
   15k recordings — enforce it; do not let new features recompute spectra.
2. **Two-rate.** Bulk metrics at 22.05 kHz (clarity/crowd/tonal/onset/stereo).
   HF metrics (hiss/air/HF-ceiling/lossy) from a cheap `NativeProbe`: 8 windows
   × 20 s at 44.1 kHz, NOT a second full decode.
3. **Scan once, store RAW metrics.** All banding/scoring/ranking derives from
   stored raw values. Re-tuning thresholds re-categorizes the corpus with ZERO
   rescans. Never store only the final scores — store the raw metric values.
4. **Two-stage scoring.** Hard disqualifiers (lossy / dropouts / hum / clipping /
   incomplete / buried) VETO or demote BEFORE fusion. They are not averaged in.
5. **Within-source-class calibration.** An A-rated AUD and an A-rated SBD are not
   on the same absolute curve. Fit thresholds per class.
6. **Crash = scrap.** No mid-process persistence. Worker computes the whole
   folder in memory, writes ONE transaction at the end. Crash before write =
   nothing persisted = nothing to clean up. Job status is just `pending → done`.

## Your tasks

### Task 1 — `lb/repo.py`: DB integration (USER tables in losslessbob.db)
Quality data is USER-tier derived data about the user's own copies. Put it in
`losslessbob.db` as USER tables (NOT a separate concert_ranker.db, NOT MASTER):

```sql
CREATE TABLE IF NOT EXISTS quality_scans (
    scan_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_json  TEXT,            -- thresholds used, for reproducibility
    notes        TEXT
);
CREATE TABLE IF NOT EXISTS quality_recording_metrics (
    lb_number    INTEGER NOT NULL,
    scan_id      INTEGER NOT NULL,
    source_class TEXT,            -- SBD/AUD/FM/UNKNOWN (derived)
    metric_json  TEXT NOT NULL,   -- the RAW aggregated metric dict
    completeness REAL,
    duration_sec REAL,
    scored_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lb_number, scan_id),
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
CREATE TABLE IF NOT EXISTS quality_recording_scores (
    lb_number    INTEGER NOT NULL,
    scan_id      INTEGER NOT NULL,
    family_id    INTEGER,         -- recording_families id, NULL if ungrouped
    final_score  REAL,
    rank_in_family INTEGER,
    vetoed       INTEGER DEFAULT 0,
    verdict_text TEXT,            -- explain_recording() output
    PRIMARY KEY (lb_number, scan_id),
    FOREIGN KEY (lb_number) REFERENCES entries(lb_number)
);
```
Store the raw `metric_json` separately from scores so reranking/rebanding never
needs a rescan. Follow the existing USER-table conventions in `backend/db.py`.

### Task 2 — `lb/source_type.py`: derive SBD/AUD/FM
Extend the existing patterns in `backend/db.py` (`extract_taper_and_source`,
the `AUD DAT`/`DAUD`/`SBD` recognizers). Classify each entry from
`source_chain` + `description` into SBD / AUD / FM / UNKNOWN. This is the
source class for conditioning calibration.

### Task 3 — `lb/commentary.py`: mine human commentary
Keyword-mine `entries.description` into the category vocabulary (see
`calibrate.LABEL_KEYWORDS`). This produces the validation oracle: the human's
own words about each recording, to check the algorithm's labels against.

### Task 4 — `audio/io.py`: real decode (the only audio I/O)
Decode FLAC/SHN/etc. to mono+stereo PCM at BULK_SR (reuse the ffmpeg approach in
`backend/sox_utils.py` / `tools/tapematch/tapematch/audio.py`). Then call
`build_track_cache`. Separately sample 8×20 s windows at NATIVE_SR for
`build_native_probe`. Decode each file exactly once for the bulk cache; the
native windows are a cheap second targeted read, not a full re-decode.

### Task 5 — staging run loop (minimal, crash=scrap)
3 producer processes (one per HDD), each walking its drive in on-disk order,
copying folders to `NVMe/staging/<lb>/`, blocking on a bounded queue
(`multiprocessing.Queue(maxsize=~40)`). 16 consumer processes drain it:
decode → cache → extract → aggregate tracks → write ONE transaction → delete
staged folder. On any exception: log the LB, move on. Skip `done` LBs on restart.
Do NOT build the watermark/state-machine version — crash=scrap makes it
unnecessary.

### Task 6 — calibration (the step that makes thresholds trustworthy)
1. Pull a stratified sample from `entries` JOIN `my_collection`: stratify by
   `rating` (cover A+→F) × derived source_class (SBD/AUD), ~5 per cell, only
   LBs present on disk.
2. Run the scan over the sample → raw metrics per recording.
3. `calibrate.score_separation` → drop/down-weight metrics that don't track the
   rating (Spearman |rho| < 0.3).
4. `calibrate.fit_thresholds` per metric per class → write fitted cutoffs back
   into `config.py` SEVERITY/QUALITY/SIGNED bands and DISQUALIFIERS.
5. `calibrate.validate_labels` → precision/recall of each category label vs mined
   commentary. Fix labels that disagree with humans.
6. Record the fitted config in `quality_scans.config_json`.

### Task 7 — recording_families integration (when it exists)
When a recording belongs to a family (same show, different transfers), rank
within the family: normalize across siblings, fuse, set `rank_in_family`. When a
recording is ungrouped, score it standalone (no relative rank, absolute bands
only). Do NOT make family grouping a hard dependency of the scan.

## Known issues the synthetic test surfaced (fix during calibration)
- **Lossy detector threshold** (`_lossy_brickwall`, 25 dB drop) needs validation
  against real known-lossy files. On synthetic near-silent HF it under-fires.
- **crowd_snr disqualifier** (3.0 dB) is in synthetic range; real distributions
  will differ — set from the calibration sample.
- **Band label phrasing** composes slightly awkwardly ("present vocals, distant /
  roomy"); polish `_PRETTY` / band labels for fluent sentences.
- **Sibilance** is HF-capped at BULK_SR; if you want true 5–9 kHz sibilance
  crest/modulation, compute it in `hf_native` from the NativeProbe windows, not
  the bulk cache.

## CLI surface (build in `cli.py`)
```
concert_ranker scan      --all | --lb N... | --family N      (staging run loop)
concert_ranker calibrate --sample-size 30                    (Task 6)
concert_ranker rerank    --scan-id N                         (re-band/rank, no rescan)
concert_ranker report    --family N | --lb N                 (JSON/CSV + verdicts)
```
`rerank` must work entirely from stored `metric_json` — proving the scan-once
guarantee.
