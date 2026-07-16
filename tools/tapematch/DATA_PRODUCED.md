# What data tapematch produces

Reference for the outputs of a tapematch run: what gets written, where it lands, and
what each field means. This is a data dictionary, not a how-to — for running the tool
see `README.md`, for tuning and interpretation see `WORKFLOW.md`.

The unit of work is **one concert date**. A run ingests every LB folder found on disk
for that date, decides which recordings share a source tape, and writes five artifacts
to an archive directory plus three tables in an accumulating database. A separate sync
step copies a slice of that into the app's own DB.

---

## 1. Where output goes

| Location | Written | Contents |
|----------|---------|----------|
| `data/tapematch/runs/<RUN_ID>/` | once per run, immutable | `results.json`, `report.md`, `config.yaml`, `tapematch.log`, `debug.log`, and later `analysis.md` |
| `tools/tapematch/observations.db` | appended every run | `runs`, `sources`, `pairs` tables — the cross-run record |
| `tools/tapematch/last_run.json`, `last_run_report.md`, `last_run.log`, `last_debug.log` | overwritten every run | convenience copies of the most recent run's artifacts |
| `tools/tapematch/embed_cache/<date>/LB<n>.npz` | on demand, reused | cached pretrained-embedding vectors per LB |
| `data/losslessbob.db` | on `/tapematch-batch` sync | `recording_families`, `tapematch_family_meta`, `tapematch_pairs` |

`RUN_ID` is `YYYYMMDD_HHMMSS_<concert-date>`, e.g. `20260602_130446_1995-07-08`. A date
can be run many times; runs are never overwritten, which is what makes the calibration
history in `observations.db` usable.

---

## 2. `results.json` — the machine-readable run output

Eight top-level keys. This is the authoritative record of what the algorithm measured;
`report.md` is a rendering of it.

### `sources` — per-recording measurements

Keyed by folder name (which embeds the LB number). One entry per recording that ran.

| Field | Meaning |
|-------|---------|
| `track_count` | audio files ingested |
| `total_dur_sec` | full duration as delivered |
| `perf_dur_sec` | duration after head/tail trim — the performance envelope |
| `trim_head_sec`, `trim_tail_sec` | crowd noise / padding removed at each end |
| `hf_ceiling_hz` | highest frequency with real content — a lineage/format hint, **capped by Nyquist** at `analysis_sr/2` (8 kHz at the default 16 kHz analysis rate) |
| `noise_floor_db` | measured noise floor |
| `dc_asymmetry` | DC offset asymmetry — a taper/equipment signature, explicitly *not* a source-identity marker |
| `nyquist_capped` | true when `hf_ceiling_hz` hit the analysis-rate ceiling and is therefore not a real format measurement |
| `speed_ppm` | speed offset vs the reference source, in parts per million |
| `speed_kind` | `reference`, `aligned`, `staircase`, `splice`, `constant-speed-offset`, or `speed-unknown` — how the lag curve behaved |
| `speed_confidence` | confidence in the speed ratio; below `align.ratio_confidence_min` (default 6.0) the source is marked `speed-unknown` and routed to the fingerprint path only |
| `family_id` | the cluster this recording was assigned to, 1-based per run |
| `flaw_event_count`, `flaw_events` | shared-flaw fingerprint: `[timestamp_sec, kind, magnitude]` triples, where kind is `click`, `dropout`, or `cut`. Empty unless `flaw_fingerprint.enabled` |

### `correlation_matrix` — the primary evidence

`{names: [...], values: [[...]]}` — a symmetric matrix of residual cross-correlation
(0–1) measured at the anchor windows. Diagonal is 1.0. This is the strongest signal and
the main clustering input; pairs at or above `match.cluster_threshold` (0.45) merge.

### `anchors_sec`

The 12 timestamps in the reference recording where correlation was measured. Chosen for
onset density in preferentially quiet windows.

### `n_families`

Count of distinct source families found — the headline result.

### `secondary_matrix`

Matrix form of the fallback signals, computed only for pairs the primary rejected:
`windowed_frac`, `hiss_frac`, `fingerprint_dice`.

### `secondary_pairs` — per-pair secondary evidence

Keyed `"<folder_a>|<folder_b>"`. Only cross-family pairs appear here.

| Field | Meaning |
|-------|---------|
| `windowed_frac`, `windowed_median`, `n_windows` | dense 60 s windowed coverage — the fraction of windows that correlate above threshold, plus the median. **This is what drives secondary clustering** (catches remasters whose edits sit at track boundaries) |
| `hiss_frac`, `hiss_median`, `n_hiss_segs` | correlation of between-song quiet segments — catches EQ/NR applied to music but not to tape hiss |
| `fp_score` | Shazam-style (f_anchor, f_target, Δt) hash Dice score over minutes 3–13. **Confirmatory only — never groups.** Same-show-different-taper pairs score 0.15–0.50 from shared musical peaks alone, so this cannot be trusted as identity evidence on its own |
| `fp_triplet_score`, `flaw_match_score`, `flaw_n_events_a/b`, `spec_stationarity`, `env_corr` | add-on signals, `null` unless their config block is enabled (all are off by default) |

### `fingerprint_hash_counts`

Hash-set size per source — context for reading a Dice score.

### `config`

The full effective config for the run, inlined. Combined with the archived `config.yaml`
this makes any historical run reproducible and explains why an old run differs from a
new one on the same date.

---

## 3. `report.md` — the human-readable run output

Same data, rendered for reading, with LB page context the JSON doesn't carry:

- **Coverage** — DB entries vs found on disk, and a per-LB table with rating, timing,
  source text, and folder name.
- **tapematch output** — the pipeline's stdout: ingest/trim, anchors, lag curves and
  speed, the residual correlation matrix, the secondary match section, clusters with
  mean intra-correlation, lineage evidence, and diagnostics.
- **LB page commentary** — the full SOURCE/NOTE block per LB, which is how a merge gets
  corroborated against what the taper actually said.

The diagnostics line is the part worth reading first: `[SECONDARY SAME-SOURCE]` (grouped
on fallback evidence — verify against commentary), `[DISTINCT SOURCE]` (near-zero
correlation to everything), `[INCOMPLETE]` (>5% shorter than the group median).

## 4. `analysis.md` — the human/AI verdict layer

Not produced by the algorithm. Written afterwards per run (by `/tapematch-batch`) and
added to the same run directory. Contains a `## Verdict:` line, a per-LB table with
family assignment and confidence notes, and a prose section per interesting finding.
This is the only artifact that carries a judgment about whether the run is *correct* —
and `tapematch_sync.py` parses its verdict line back out to set the `review_flag` on
synced families.

## 5. Logs

`tapematch.log` is the run's stdout as-written; `debug.log` holds the verbose internal
trace. Both archive per run, both mirror to `last_run.log` / `last_debug.log`.

---

## 6. `observations.db` — the cross-run record

Three tables, appended to on every run. This is where calibration work lives, because
it holds every observation ever made rather than just the latest.

**`runs`** — one row per run: `run_id`, `concert_date`, `location`, source counts
(`n_sources_db` in the LB database vs `n_sources_found` on disk vs `n_sources_ran`),
`n_families`, the full `config_json`, `archive_dir`, `run_at`, `duration_sec`. The
db/found/ran spread is what tells you a run was on an incomplete set.

**`sources`** — one row per recording per run, mirroring `results.json`'s `sources`
plus the LB-page fields (`lb_rating`, `lb_timing`, `lb_source_text`) and `dominant_ext`
(`.flac` / `.shn` / `.wav` …).

**`pairs`** — one row per pair per run, and the table most queries want. Carries the
verdict (`tapematch_verdict`: `same_family` / `different_family`), `corr`, both
`family_id`s, and every measurement for *both* sides side-by-side (`speed_ppm_a/b`,
`hf_ceiling_hz_a/b`, `noise_floor_db_a/b`, `perf_dur_sec_a/b`, `track_count_a/b`,
`dominant_ext_a/b`, …) so a pair can be judged without joining back to `sources`. It
also carries all the secondary signals (`windowed_frac`, `hiss_frac`, `hiss_median`,
`fp_score`, `fp_triplet_score`, `flaw_match_score`, `spec_stationarity`, `env_corr`,
`emb_score`, `emb_score_global`) and three columns the algorithm never writes:

- `lb_says_same` (1/0/NULL) and `lb_relation_text` — what the LB page claims about the
  pair, the independent check on a merge.
- `human_judgment` (`confirmed_same` / `confirmed_different` / `uncertain` / `lb_wrong`)
  and `human_notes` — filled in later, by hand. These are the ground-truth labels the
  regression harness scores against.
- `label_suspect` — flags a label the label census found questionable.

**`latest_pairs`** is a view collapsing `pairs` to the most recent observation per
(date, lb_a, lb_b) — use it when you want current state rather than history.

---

## 7. What reaches the app

`backend/tapematch_sync.py` picks the best run per date and copies a slice into
`data/losslessbob.db`. This is derived user data: rewritten wholesale per date on every
sync, never hand-edited, never included in master export.

- **`recording_families`** — `lb_number` → `fam_id`, with `concert_date` and `run_id`.
  The clustering result, one row per recording.
- **`tapematch_family_meta`** — one row per family: `label` / `label_override`, `by`
  (`ai` or human), `conf`, `note`, `member_count`, and the `review_flag` / `review_reason`
  parsed out of `analysis.md`.
- **`tapematch_pairs`** — per-pair `corr`, `emb_score`, `fp_score`, `same_family`, and
  `similarity_pct`.

`similarity_pct` is worth calling out because it's the only place the raw numbers get
transformed. Raw `corr` isn't a linear "percent similar" — it collapses toward the noise
floor for unrelated recordings, where 0.12 vs 0.08 means nothing. So `similarity_pct` is
a banded monotone blend of `corr` and `emb_score`, calibrated against the measured
verdict distribution, that renders same-family pairs at 85–100 and unrelated pairs at
0–40. It can be `NULL`, meaning "not comparable" — which the GUI should show as `n/c`
rather than implying a real 0% match. The raw signals stay in the table alongside it.

---

## 8. Reading the output honestly

Three properties of this data cause most misreadings:

**Fingerprint Dice never groups anything.** It is confirmatory evidence only. Two
different tapers recording the same show score 0.15–0.50 purely from shared musical
note peaks, so a high-ish Dice with no windowed/hiss support is not evidence of a shared
source tape.

**`hf_ceiling_hz` is usually a lie about format.** At the default 16 kHz analysis rate
everything is capped at 8 kHz; `nyquist_capped` tells you when the number is an artifact
of the analysis rate rather than a property of the recording.

**Low intra-family correlation is expected on secondary-linked families.** The primary
correlation was below threshold — that's *why* the secondary path ran. `[low confidence]`
on such a family is normal, not a defect.

The add-on signals (`fp_triplet_score`, `flaw_match_score`, `spec_stationarity`,
`env_corr`) are `null` in most runs because their config blocks are disabled by default.
`emb_score` is populated only when `addon_links.rule_d` fires.
