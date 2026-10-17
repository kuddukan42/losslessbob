# Listening & Insight Features — Idea Spec Pack

Spec author: Fable 5, 2026-07-06 (brainstorm session with the user; user approved all
items for capture). Execution target: Opus/Sonnet sessions, one idea at a time — each
section is independent unless its Dependencies line says otherwise. These are *seeds*,
deliberately lighter than FABLE_TAPER_ATTRIBUTION.md / FABLE_UNIFIED_RANKING.md: the
executing session should expand its chosen section into a short plan before coding.

Theme: most of the app's machinery was built for *cataloguing*; these features convert
it into tools for *listening* and *insight*. The user's own priority signal from the
brainstorm: A/B listening (§2) and the song index (§3) excited him most; §1 was his own
idea and is fully validated.

---

## 0. Shared infrastructure facts (verified 2026-07-06, this session)

- `tools/tapematch/observations.db` has THREE core tables: `runs`, `sources`, `pairs`.
  **`pairs` (8,875 rows) stores every compared pair per date — including cross-family
  pairs — with:** `corr` (residual cross-correlation 0–1), `tapematch_verdict`
  (same_family/different_family), `family_id_a/b`, `lb_a/lb_b`, per-side metrics
  (hf_ceiling, noise_floor, speed_ppm/kind, perf_dur, track_count), similarity signals
  `fp_score`, `fp_triplet_score`, `env_corr`, `emb_score`, `emb_score_global`,
  `flaw_match_score`, plus `lb_says_same`/`lb_relation_text` (what the LB page claims)
  and `human_judgment`/`human_notes` (curator annotations, mostly unfilled).
- `sources` carries per-recording `trim_head_sec`/`trim_tail_sec`, `perf_dur_sec`,
  `speed_ppm`, `speed_kind` — i.e. alignment/coverage data survives the run.
- Families sync to the app DB via `backend/tapematch_sync.py:sync_tapematch_families()`
  (manual trigger; latest-complete-run-per-date rule; deterministic `fam_id`). Any new
  sync work must follow this same pattern — see PROJECT.md §recording_families.
- Full per-run artifacts (alignment offsets, logs, analysis.md) live in
  `data/tapematch/runs/<RUN_ID>/`; `runs.archive_dir` points there.
- Quality machinery: `concert_ranker/` package; `quality_recording_scores.abs_score/
  abs_grade`, per-metric detail in `quality_recording_metrics.metric_json`.
- Setlists: `entries.setlist` (free text) + `setlistfm_shows` (scraped, structured-ish)
  + `bobdylan_shows`. Curated picks: `curated_lists`/`curated_list_entries`.
- All new tables: idempotent CREATE/ALTER per repo SQLite rules; USER-tier unless noted.
- GUI work: gui_next only; i18n via `/gui-next-i18n`; verify via `/gui-check`; never
  screenshot.

---

## 1. Pairwise match % per date (USER'S IDEA — validated, build first)

**What:** every LB on a performance date gets a quantitative similarity % against every
other LB on that date — including across family splits — so the user can see *how
different* an outlier recording actually is instead of just "different family".

**Data:** already complete in `pairs` (§0). Zero new audio computation.

**Build:**
1. Extend `tapematch_sync.py` to sync a slim pairwise table into the app DB
   (`tapematch_pairs`: concert_date, lb_a, lb_b, corr, emb_score, fp_score,
   same_family flag, run_id), same latest-complete-run rule as families, wholesale
   replace per date on sync.
2. **Presentation is the design problem.** Raw `corr` is NOT a linear "percent similar"
   — it collapses toward noise floor for unrelated recordings (0.12 vs 0.08 is
   meaningless). For cross-family cells `emb_score` tracks perceptual "sounds similar"
   better. Recommended: a banded blend calibrated against the verdict distribution so
   same-family pairs render ~85–100% and unrelated ~0–40%, raw signals in a tooltip.
   Calibrate the mapping empirically: pull the corr/emb distributions for
   same_family vs different_family verdicts from `pairs` and pick monotone breakpoints.
3. Expose flat via API next to `/api/tapematch/families` (follow that endpoint's
   shape); render as a small N×N matrix/heatmap per date. Natural home: the dedicated
   TapeMatch screen (TODO-170) — this feature is a good reason to finally build a
   minimal v1 of that screen (matrix + family list + link to analysis.md verdict).
   If TODO-170 is deferred, an expandable matrix in the Library DetailPanel works.

**Gotchas:** pairs are run-scoped — never mix runs across a date; some dates have
n_sources_ran < n_sources_db (missing folders) so the matrix may be smaller than the
date's LB list — render missing LBs as "not compared" cells, not 0%.
**Dependencies:** none. **Size:** small-medium (1 session).

## 2. Aligned A/B listening (highest user excitement)

**What:** for any pair of same-show sources, play the *same musical moment* from both,
level-matched, back to back — automating the LB curator's documented comparison method
(TODO-187: 15–30 s quiet vocal passage, levels matched, bias vs harshness).

**Data/machinery:** tapematch alignment offsets (per-run artifacts under
`runs.archive_dir`; `sources.trim_head_sec` + speed data approximate global offset —
executing session must check what per-pair offset detail the run archive stores, see
`tools/tapematch/tapematch/align.py`). Decode via the same ffmpeg path the ranker uses
(`concert_ranker/audio/io.py`). Candidate passage selection: quiet vocal segment =
low crowd_snr + vocal-band energy; the ranker's metric code already computes related
band features — reuse, don't reinvent.

**Build sketch:** backend endpoint `POST /api/ab_clip {lb_a, lb_b, t?}` → finds the
aligned timestamp pair, decodes ~20 s from each, RMS-matches levels, returns two clip
URLs (cache under data/, keyed by lb pair + t). GUI: A/B player widget (single toggle
button swaps sources mid-play — instant switching is what makes differences audible).
Auto-pick t if not given. **Gotchas:** only works for pairs tapematch aligned
(same_family or at least aligned run data); speed-drifted pairs (speed_kind=staircase)
need per-segment offset, not global — v1 can restrict to cleanly-aligned pairs.
**Dependencies:** §1's sync helps find pairs but isn't required. **Size:** medium
(backend clip service + player widget).

## 3. Song-centric index (highest user excitement, tied)

**What:** invert the catalog — browse by song: "every circulating *Visions of
Johanna*, ranked by quality grade." Date-centric = archivist view; song-centric =
listener view. No LB tool has ever offered it.

**Data:** `entries.setlist` free text + `setlistfm_shows`. The hard 20%: song-title
normalisation (aliases, abbreviations, medleys, cover attribution). setlist.fm data is
already normalised per-song — prefer it as the spine, match LB entries to setlistfm
shows by date, fall back to parsing `entries.setlist` only for dates setlist.fm lacks.
**Build sketch:** derived table `song_performances(song_norm, concert_date, lb_number,
seq_no, source)`; a song browser screen (search song → list of dates/LBs joined with
abs_grade + pick_rank from show_picks when present, sorted best-first). A "play best
version" affordance if §2/§7 exist. **Gotchas:** medleys and fragments; song-title
canonicalisation table will need curator edits — make it a real table, not code
constants. **Dependencies:** none hard; FABLE_UNIFIED_RANKING show_picks enriches it.
**Size:** medium (parser + table + screen).

## 4. Mislabel hunter

**What:** run fingerprint comparison ACROSS dates (adjacent shows, same venue/tour) to
catch recordings filed under the wrong date — real errors in 60 years of tape trading,
and every confirmed hit is a community-level contribution.

**Data/machinery:** tapematch fingerprint scoring (`fp_score` path in
`tools/tapematch/tapematch/match.py`); `pairs.label_suspect` column already exists —
the concept is half-anticipated. **Build sketch:** batch tool that, for candidate sets
(same tour ±N days, or entries whose `perf_dur_sec`/setlist look anomalous for their
date), computes cross-date fp scores and writes a suspects report; surface confirmed
suspects via `human_judgment='lb_wrong'`. Start with a cheap pre-filter (setlist text
similarity across dates) before any audio work. **Gotchas:** this is compute-heavy —
it's a targeted batch tool with a candidate heuristic, NOT an all-pairs scan; respect
the never-run-concurrent-tapematch rule. **Dependencies:** none. **Size:** medium,
mostly tooling not UI.

## 5. Best-composite patch map

**What:** per date/family, compute which combination of tapes covers the most of the
show and where the patch points are ("source A for sets 1–2, patch encore from B") —
what bootleg remasterers do by hand. Even just a per-source coverage timeline is new.

**Data:** `sources.trim_head_sec/trim_tail_sec/perf_dur_sec` + per-run alignment
artifacts (segment-level coverage lives in the run archive; executing session should
inspect one `runs/<RUN_ID>/` folder to see exact artifact shape — `tapematch/trim.py`
and `align.py` are the writers). **Build sketch:** coverage model = per-source
intervals on a common show timeline (alignment offsets place each source); greedy
best-coverage selection weighted by quality (abs_score) when available; render as
stacked horizontal timeline bars per date (DetailPanel or TapeMatch screen). **Gotchas:**
intervals are only trustworthy within aligned families; cross-family composites need §1
similarity as a sanity guard. **Dependencies:** benefits from §1's screen home.
**Size:** medium.

## 6. Artifact evidence viewer

**What:** when a quality detector fires (brickwall, digipops, 32k DAT, parapets…),
show the actual spectrogram snippet where it fired next to the LB reference image of
that artifact type. "Why is this a C+?" answered with a picture.

**Data:** artifact taxonomy + 22 reference images documented in TODO-187 (images
downloaded 2026-06-25; destined for `concert_ranker/LB_KNOWLEDGE.md` — do TODO-187
first); detector fire locations — check whether `quality_recording_metrics.metric_json`
tracks per-track/per-time detail (it has a `tracks` key) or whether detectors must be
re-run with a "record location" flag on targeted files. **Build sketch:** spectrogram
render via matplotlib or ffmpeg showspectrumpic on the flagged region; cache PNGs under
data/; DetailPanel gallery: flagged-region image + reference image + taxonomy blurb.
**Gotchas:** needs access to the audio files (owned copies only — same constraint the
scanner has); keep renders lazy/on-demand. **Dependencies:** TODO-187 doc.
**Size:** medium.

## 7. Most-wanted gap list

**What:** dates Dylan performed but with ZERO circulating recording, ranked by
significance — then point the WTRF watcher at the list so the user is alerted the day
a tape surfaces. Turns the scraper from a fetch tool into a hunting tool.

**Data:** `setlistfm_shows` + `bobdylan_shows` (performance universe) vs `entries`
(circulating universe) vs `lb_missing` (confirmed-nonexistent — exclude these).
Significance ranking inputs: tour/era rarity, setlist rarities (needs §3's song table
for "only known performance of X" detection — the killer sort key), venue.
**Build sketch:** derived `show_gaps` table + a Library/Reports view; wire into the
WTRF scraper (TODO-193/194 surface) as a standing watch list — new-post scan matches
against gap dates. **Gotchas:** date-matching between setlist.fm and LB conventions
(timezone/multi-show days); exclude pre-career/spurious setlistfm rows. **Dependencies:**
§3 makes the ranking much better but a v1 can rank on era alone. **Size:** small-medium.

## 8. Taper geography

**What:** map each taper's venue/region/era footprint. Fun as a map layer; genuinely
useful as an attribution prior ("unattributed AUD on the 1999 East Coast leg where lta
is known to have worked").

**Data:** geocoded shows (TODO-167 — prerequisite) + `taper_attributions`
(FABLE_TAPER_ATTRIBUTION.md — prerequisite). **Build sketch:** per-taper
(region, era) histograms from confirmed attributions; render on the existing Map tab
concept (TODO-085) or a per-taper panel; expose as an evidence `kind:"geography"`
signal in the attribution engine's Layer 2 with a small score contribution.
**Dependencies:** TODO-167 + taper attribution phases 1–2. **Size:** small once
prerequisites exist — do it as a follow-on to the attribution spec, not standalone.

## 9. "This night in Dylan history"

**What:** on app launch (Home screen), surface the best-graded show performed on
today's calendar date across all years, one click to play/open. Converts the archive
into a daily listening habit.

**Build sketch:** trivial query — entries WHERE date matches MM-DD, join show_picks
(rank 1) or fall back to best `entries.rating`; small Home card (Home has free space —
TODO-169 removes the ingest box; combine). Rotate among top candidates so repeat
launches on the same day vary. **Dependencies:** none (show_picks enriches).
**Size:** small — a good warm-up task before any bigger section.

---

## Suggested execution order

1. §1 pairwise match % (validated, small, seeds the TapeMatch screen)
2. §9 tonight-in-history (trivial win) → then FABLE_UNIFIED_RANKING if not done
3. §3 song index → §7 gap list (chain: song table powers gap ranking)
4. §2 A/B listening (the crown jewel; do after §1 so pair data is in the app DB)
5. §5 patch map, §6 artifact viewer (medium, independent)
6. §4 mislabel hunter (batch tooling, anytime)
7. §8 taper geography (only after TODO-167 + attribution spec)

Each completed section: normal bookkeeping (`/session-close`), i18n pass for UI
strings, and add a TODO entry at start if one doesn't exist so the work is tracked.
