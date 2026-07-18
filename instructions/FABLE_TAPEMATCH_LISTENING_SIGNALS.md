# TapeMatch "Simulated Listening" Signals — Idea Spec Pack

Spec author: Fable 5, 2026-07-06 (ideation session; user wants ALL sections eventually).
Status 2026-07-17: un-parked; §1 handoff prompt drafted + approved (see §1 HANDOFF
below) — awaiting launch.
Execution target: Opus/Sonnet sessions, one section at a time. Like
FABLE_LISTENING_INSIGHT_IDEAS.md these are *seeds*: the executing session expands its
section into a short plan before coding, and reads `tools/tapematch/CLAUDE.md` +
CALIBRATION_PROGRESS.md first.

Theme: every existing TapeMatch signal (corr, fp/fp_triplet, env_corr, emb_score,
flaw_match) measures the **music**. These five measure other things — the room's
electricity, the spoken words, the physics of the tape, the human ear — giving evidence
axes that are independent of the current ones, which is exactly what hardening needs.

---

## 0. Shared integration rules (apply to every section)

- **New pair signals land as new columns on `pairs`** (observations.db) via idempotent
  ALTER, and blend into the verdict through `config.yaml` weights — follow how
  `emb_score`/`flaw_match_score` were integrated in `tapematch/match.py`. NULL = signal
  unavailable for that pair; the blend must treat NULL as "no evidence", never 0.
- **Calibrate before trusting**: every new signal first ships dark (computed + logged,
  weight 0), gets its same-family vs different-family distribution pulled from `pairs`,
  and only then gets a weight. §1's synthetic harness supersedes this eyeballing once it
  exists.
- Audio access: owned files only (same constraint as the ranker/scanner).
- Never run concurrently with a live tapematch session (standing rule).
- New Python deps: pinned exact versions in requirements.txt + PROJECT.md note. Heavy
  deps (§4 torch, §5 metric libs) are **feature-gated** behind config flags so the core
  pipeline never grows a hard dependency on them.
- Each section = its own TODO entry at session start + normal `/session-close`.

---

## 1. Synthetic lineage simulator (BUILD FIRST — it measures everything else)

**What:** a "tape deck simulator" that takes owned sources and programmatically
generates derived copies with known truth — unlimited labeled pairs for calibration,
threshold ROC curves per signal, and a regression suite that catches when a hardening
change quietly breaks a case. Fixes the pipeline's oldest limitation: no ground truth.

**Build:** `tapematch/simulate.py` + CLI `tools/tapematch/make_synth_pairs.py`.
Composable degradation ops (each a pure function on float32 PCM, chained per a recipe):
speed offset (fixed ppm), **staircase** (segment-wise ppm steps — we shipped detection
for this; now we can synthesize it), wow/flutter (sinusoid + random-walk pitch
modulation via variable-rate resampling), EQ tilt/shelf + telephone-band, azimuth loss
(stereo HF rolloff + small interchannel delay), added hiss, added mains hum (50/60 Hz +
harmonics — also §2's test fixture), soft clipping, lossy encode round-trip (ffmpeg
mp3/ogg at several bitrates), head/tail trims, mono-fold, dropouts. Each generated pair
writes a manifest JSON: recipe, expected verdict, expected speed_ppm/kind.

Negatives: different-date pairs are free; **hard negatives** = same song from adjacent
tour dates (pull candidates from setlist data) — the case that actually fools signals.

**Harness:** `--synth-regress` mode runs the full pipeline over the synth corpus and
reports per-signal ROC + verdict accuracy + speed-estimate error. Wire into the
calibration workflow as a gate: no threshold/weight change lands without a synth run.

**Gotchas:** synthetic runs must NEVER pollute real observations — separate
observations file (e.g. `observations_synth.db`) or a `synthetic=1` column filtered
everywhere; seed all randomness for reproducible corpora. ffmpeg already available.
**Deps:** none new. **Size:** medium. **Dependencies:** none.

## 2. ENF / mains-hum forensics (top pick — new physics, zero new deps)

**What:** extract the 50/60 Hz electrical-network-frequency hum many AUD tapes carry
(PA bleed, lighting, recorder pickup). Three payoffs:

1. **Same-performance verifier:** grid frequency wanders uniquely over any given hour;
   two tapes of the same show share the same ENF wander curve after alignment —
   evidence fully independent of all music-based signals.
2. **Precision speed measurement:** hum reading 59.4 on a 60 Hz grid = tape ~1% slow.
   Grid wander averages out to nominal over long spans, so long-window mean gives
   absolute speed; per-segment tracking gives a sharper **staircase detector** than
   correlation-based ppm estimation. Cross-check against existing `speed_ppm`.
3. **Geography sanity check:** 50 vs 60 Hz tells you the continent — a "US 1981" tape
   humming at 50 Hz is mislabel-hunter evidence (feeds LISTENING_INSIGHT §4).

**Build:** `tapematch/enf.py`. Long-window STFT (multi-second frames, ~1 s hop) with
quadratic peak interpolation on narrow bands around 50/60 and harmonics
(100/120/150/180 — harmonics are often stronger and sit in quieter spectral territory);
pick the strongest consistent track; output = presence flag + SNR, mean carrier Hz,
per-frame ENF curve stored as a compact artifact in the run dir. Pair scoring =
correlation of aligned ENF curves. New `pairs` columns: `enf_corr`, plus per-side
`enf_hz`, `enf_snr` on `sources`; new speed estimate `speed_ppm_enf`.

**Gotchas:** many tapes have no detectable hum (battery decks, good mics) — the SNR
gate must be honest and NULL out cleanly; heavily speed-shifted tapes alias the 50/60
identity (a 20% slow 60 Hz reads 48 — resolve via the existing speed estimate first);
music energy sits on the harmonics — prefer frames from quiet gaps (reuse §3's gap
finder once it exists, or a simple low-energy frame filter for v1).
**Deps:** numpy/scipy only. **Size:** medium. **Dependencies:** none (§1 harness makes
calibration much easier — the simulator injects hum with known parameters).

## 3. Banter/ASR transcript matching (listening in the human sense)

**What:** transcribe stage banter and between-song crowd moments with Whisper. Same
performance ⇒ same words, same shouts, same timing — robust to EQ, generation loss,
and awful transfers, i.e. strongest exactly where audio-signal similarity is weakest
(two very different-sounding tapes of one show).

**Build:** gap finder (between-song regions from track boundaries + low music energy)
→ transcribe ±30 s around each gap with faster-whisper (tiny/base, CPU, temperature 0
for determinism) → store in a new observations table
`transcripts(run_id, lb, t_start, t_end, text, avg_logprob)`. Pair scoring
`banter_score`: fuzzy token overlap of gap transcripts **and** agreement of matched
utterances' aligned timestamps; require ≥2 corroborating utterances before the score
counts (single-utterance matches are noise).

**Reuse value beyond TapeMatch (why this section punches up):** transcripts feed the
mislabel hunter ("good evening <city>" vs claimed venue), the song-centric index
(sung-lyric fragments confirm setlist rows), and taper attribution (spoken credits).
Store them once, in observations.db, keyed by lb + time.

**Gotchas:** ASR on rough AUD hallucinates — keep `avg_logprob`, discard low-confidence
segments; multilingual crowds; compute cost is real — gaps only, never full shows;
model download needs a pinned model revision for reproducibility.
**Deps:** faster-whisper (pin) + its CTranslate2 runtime — feature-gated.
**Size:** medium-large. **Dependencies:** none hard; §1 can't synthesize banter, so
calibration here is distribution-based (rule §0).

## 4. Wow & flutter signature matching (the tape's fingerprint)

**What:** the pitch micro-modulation a cassette/deck bakes into every digitization of
that physical tape. Shared wow curve ⇒ shared analog ancestor, even when transfers
differ wildly — separating **same-tape** from **same-performance-different-taper**,
the exact boundary current signals blur.

**Build:** two carriers, cheapest first:
1. **Hum carrier (preferred):** if §2 found hum, the ENF curve = grid wander (slow,
   <0.1 Hz) + tape speed modulation (wow 0.5–6 Hz, flutter 6–20 Hz) — band-split the
   ENF curve and the fast band IS the wow/flutter signature. Zero extra extraction.
2. **Tonal carrier (fallback):** high-resolution f0 track on sustained tonal segments
   (harmonica holds, organ, vocal sustains), same band-split. Performance vibrato lives
   on the note; tape wow is common to all simultaneous partials and continues through
   non-vocal content — use that to separate.

Pair scoring `wf_corr` = correlation of aligned wow/flutter curves. Bonus per-side
metric: absolute W&F magnitude is a generation/quality indicator — expose to
concert_ranker as a candidate metric (coordinate with `quality_recording_metrics`).

**Gotchas:** silence/atonal stretches yield nothing (NULL, per §0); two clean digital
clones of the same transfer trivially match (that's fine — still same family); f0
octave errors if using carrier 2 (median-filter the track).
**Deps:** none new for carrier 1; carrier 2 may want librosa's pyin if librosa is
already in the tree — check before adding. **Size:** small-medium **after §2** (shares
its extraction); medium standalone. **Dependencies:** §2 strongly recommended first.

## 5. Perceptual similarity / simulated listener score

**What:** score aligned, level-matched clip pairs the way a human ear would —
psychoacoustic metrics built to predict listening-test judgments. Two uses:
(a) pair signal `pq_sim` for the verdict blend; (b) **within-family transfer ranking**
— "which copy sounds better" — as a second opinion for `rank_in_family`, automating
the LB curator's A/B method (same method FABLE_LISTENING_INSIGHT §2 automates for
human ears; share the clip-selection helper: quiet vocal passage, RMS-matched).

**Build:** clip selection via ranker band features (reuse `concert_ranker/audio/`);
metric backend behind an interface so we can swap: candidates are ViSQOL (best
validated; C++ build — painful), CDPAM/DPAM (pip + torch — heavy), or a **no-dep v1**:
multi-band log-spectral distance + loudness-model weighting on the aligned clips.
Executing session: check what the existing `emb_score` stack already ships (if torch
is already a tapematch dep, CDPAM is cheap to add; if not, start with no-dep v1).

**Gotchas:** these metrics assume same content, aligned and level-matched — garbage on
misaligned pairs, so gate on alignment quality; scores are clip-local — sample 3–5
passages and take the median; staircase pairs need per-segment alignment (restrict v1
to cleanly-aligned pairs, same as A/B listening).
**Deps:** none for v1; torch-family optional later. **Size:** medium.
**Dependencies:** benefits from §1 (synthesized degradations give known "worse" copies
to validate the ranking direction).

---

## §1 HANDOFF (drafted 2026-07-17 by Fable — approved for sonnet, NOT yet executed)

Launch as a sonnet implementation session with exactly this prompt (minimal-context
format: task + paths + constraints; the docs it points at carry the rest):

```text
Implement §1 (synthetic lineage simulator) of
instructions/FABLE_TAPEMATCH_LISTENING_SIGNALS.md. Per that spec's header: expand
§0 + §1 into a short written plan BEFORE coding, and read tools/tapematch/CLAUDE.md
and the tail of tools/tapematch/CALIBRATION_PROGRESS.md first.

Context deltas since the spec was written (2026-07-06):
- A corpus rescore batch is in flight until ~2026-07-20 (TODO-254). Standing rule:
  never run concurrently with a live tapematch session. This session: BUILD + unit
  tests only — do not run --synth-regress or any pipeline invocation over audio.
  Note the first real harness run as a follow-up in the TODO.
- Per-segment staircase lag curves are now persisted by the engine (TODO-235,
  commits d29dd39b + 3194b90f). Synthesize staircase degradations so expected
  values are checkable against that persisted format — read the TODO-235 work
  before designing the staircase op's manifest fields.
- Calibration moved since the 07-09 freeze: staircase corr floor 0.40 and the
  corroboration gate shipped (TODO-234). TODO-255 (hiss_median floor for the gate)
  is open — design the harness so a ROC sweep over synthesized hiss levels can
  answer it; name this as a target use case in your plan.

Deliverables (from spec §1):
- tapematch/simulate.py: composable degradation ops, each a pure function on
  float32 PCM, chained per recipe (op list is in the spec).
- tools/tapematch/make_synth_pairs.py CLI; per-pair manifest JSON (recipe,
  expected verdict, expected speed_ppm/kind).
- --synth-regress harness mode (implemented, NOT executed this session).
- Hard negatives: same-song adjacent-tour-date candidates from setlist data.
- Unit tests for the ops (pure-PCM level, no pipeline run needed).

Constraints:
- Synthetic results must never pollute real observations — spec prefers a separate
  observations_synth.db; commit to the isolation choice in your plan.
- Seed all randomness (reproducible corpora).
- No new Python deps (ffmpeg already available). No threshold/weight/config.yaml
  verdict changes — this section is measurement infrastructure only.
- Repo rules apply: .venv/bin/python3, type hints + docstrings, logging not print,
  100-char lines. Open a TODO entry at session start; end with /session-close.
```

Model routing: sonnet. §2 (ENF) is next after §1 but its DSP is intricate — route
to opus, or sonnet with plan review. §4 stays coupled to §2; do not hand it off
standalone.

---

## Suggested execution order

1. **§1 simulator** — measurement infrastructure; every later section calibrates
   against it instead of eyeballs.
2. **§2 ENF** — no new deps, three payoffs, new evidence axis.
3. **§4 wow/flutter** — mostly free once §2's extraction exists.
4. **§3 ASR banter** — biggest new capability; heaviest dep; transcripts feed three
   other specs.
5. **§5 perceptual score** — start with the no-dep v1; upgrade the backend only if
   the v1 distribution looks promising.

Cross-links: §2 geography evidence → mislabel hunter (LISTENING_INSIGHT §4); §3
transcripts → song index (§3), mislabel hunter, taper attribution evidence layer; §4
W&F magnitude + §5 ranking → concert_ranker; §5 clip selection ↔ A/B listening
(LISTENING_INSIGHT §2). None of these change verdict semantics until calibration
assigns them weight — dark-launch per §0 is mandatory.
