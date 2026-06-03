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
| `tools/tapematch/tapematch/align.py` | Anchor detection, local_lag, lag curve interpretation |
| `tools/tapematch/tapematch_session.py` | Session orchestrator |
| `tools/tapematch/last_run_report.md` | Latest human-readable report |
| `tools/tapematch/last_run.log` | Raw tapematch stdout |
| `tools/tapematch/observations.db` | Accumulated pair observations across all runs |
| `tools/tapematch/runs/` | Archived logs/reports/configs per run |

---

## Config knobs (most commonly tuned)

### Primary

| Knob | Current | Effect |
|------|---------|--------|
| `match.cluster_threshold` | 0.45 | Raise = fewer false positives; lower = catches more degraded same-source |
| `anchors.n_anchors` | 12 | Higher = more robust to track-break lag errors |
| `anchors.window_sec` | 45.0 | Wider = more audio per anchor comparison |
| `align.ratio_flag_ppm` | 200 | Speed offset before resampling kicks in |
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

### Fingerprint

| Knob | Current | Effect |
|------|---------|--------|
| `fingerprint.hf_band_hz` | [6000, 8000] | HF-only peak-finding — reduces same-show false matches |
| `fingerprint.match_threshold` | 0.60 | Display threshold for fingerprint evidence |
| `fingerprint.cluster_threshold` | 0.35 | Dice above this drives clustering (safe with `hf_band_hz`) |
| `fingerprint.window_start_sec` | 180 | Skip intro/tuning; set higher if shows start late |
| `fingerprint.window_dur_sec` | 600 | 10-min window; increase for more hashes (slower) |
| `fingerprint.fanout` | 5 | Landmark pairs per peak; increase for more hashes |

---

## Known failure modes and what handles each

| Failure mode | Example | Detection |
|---|---|---|
| Clean same-source, different trim | Most pairs | Primary residual corr |
| Speed difference (DAT pitch drift) | 1998-10-28 LB-06564/LB-12485 | Primary + estimate_ratio resample |
| Edited remaster (track boundary edits) | 1996-07-21 LB-06986/LB-00513 | Windowed coverage + hiss + fingerprint |
| Heavy EQ/NR on music, hiss intact | (not yet observed) | Quiet-segment hiss |
| Dithered amplitude remaster | (not yet observed alone) | Fingerprint (cluster_threshold) |
| Staircase/CDR re-tracking (one side) | 1996-07-21 LB-06984↔LB-06985 | Lag curve staircase flag |
| Staircase/staircase (both sides) | 2001 tour many pairs | Short-window fallback (15s windows) |
| Large timing drift (>3 min content diff) | 2001-07-03 LB-417/LB-56 | [TIMING MISMATCH] diagnostic |
| Incomplete recording | 1996-07-21 LB-06984 | [INCOMPLETE] diagnostic |

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
