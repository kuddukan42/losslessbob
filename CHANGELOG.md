[2026-06-30] — fix(scraper): WTRF search delay raised to clear forum flood-control
Fixed: backend/wtrf_scraper.py: search_delay was computed as delay * 1.5 (3.0s at the CLI's
  default --delay 2.0), below the WTRF forum's ~5s search flood-control window. Raised
  _SEARCH_DELAY constant to 10.0 and changed find_torrent_for_lb() to
  max(delay * 1.5, _SEARCH_DELAY) so search2 queries never go below the floor. Likely
  explains some of the 'not_found' results in live batch testing — searches may have been
  silently throttled rather than genuinely returning zero candidates. See BUG-226.

[2026-06-30] — fix(scraper): WTRF candidate disqualified when post tagged for a different LB entry
Fixed: backend/wtrf_scraper.py: _score_candidate() now extracts "LB-NNNNN" tag(s) embedded
  in candidate post bodies (forum_poster.py's own posting convention) before scoring. A tag
  matching the target entry's own lb_number is now a strong positive signal (+200,
  classified 'high' in _classify_confidence). A tag for a DIFFERENT lb_number hard-disqualifies
  the candidate — find_torrent_for_lb() now skips it in the scoring loop instead of letting it
  tie/compete on the weak date-match + has_torrent floor (score=5). See BUG-225.

[2026-06-30] — feat(scraper): WTRF fetch CLI accepts LB lists/ranges + prints review URLs
Added: tools/wtrf_fetch_missing.py: --lbs flag (mutually exclusive with --lb) accepting
  comma/space-separated LB numbers and/or inclusive ranges, e.g. '16640-16650,16700'.
  New _parse_lb_spec() helper dedupes and preserves first-seen order; --limit still
  truncates the resulting queue.
Changed: tools/wtrf_fetch_missing.py: _print_row() now prints the matched topic_url
  for 'skipped' rows (needs_review/ambiguous/not_found) so the user can manually open
  and review the candidate post(s) directly from CLI output, without querying
  wtrf_downloads. Ties print both tied URLs.
Changed: backend/wtrf_scraper.py: find_torrent_for_lb() returns topic_url_2 (the
  runner-up topic) on confidence='ambiguous', for the CLI's tie display. Not persisted
  to wtrf_downloads — display-only.

[2026-06-29d] — feat(scraper): WTRF forum torrent fetcher for missing LB items
Added: backend/wtrf_scraper.py: search WTRF board by date variants, multi-round scoring (FFP hashes > filenames > equipment tokens > taper name), confidence classification, torrent download with per-request throttle
Added: backend/qbittorrent.py: add_torrent_for_download() — adds torrent for downloading (no source-folder assumption)
Added: backend/db.py: wtrf_downloads table + add/update/get/get_pending helpers
Added: backend/app.py: POST /api/wtrf/fetch_torrent, POST /api/wtrf/crawl_missing (SSE), GET /api/wtrf/downloads
Added: tools/wtrf_fetch_missing.py: headless CLI for batch missing-item crawl (--limit, --lb, --delay, --add-to-qbt, --dry-run)

[2026-06-29c] — feat(concert-ranker): hard hf_ceiling floors + 30-min duration gate
Changed: concert_ranker/quality_score.py: _HF_FLOOR_RULES constant + _apply_hard_floors() — caps predicted rank after model: hf_ceiling_hz < 4000 → D- ceiling (rank 2); hf_ceiling_hz < 6000 → D ceiling (rank 3). Applied inside grade() after predict_rank(). D- now produced (26 recordings); D increased 1→150. Pearson r 0.66→0.64 (boundary trade-off: some LB C- with restricted HF pushed to D).
Changed: concert_ranker/cli.py: _MIN_CONCERT_DURATION_SEC = 1800 s constant; _filter_short_recordings() removes recordings under 30 min from metrics in-place; called from _rerank alongside other filters. 162 sub-30-min recordings excluded from scan 18; final scored set: 13752 rows.

[2026-06-29b] — fix(concert-ranker): exclude private entries + reclassify xx-date as compilation
Changed: backend/db.py: classify_entry_categories + classify_one_entry: Tier 0 added — if 'xx' in date_str (multi-date, day/month unknown) → 'compilation' before any bobdylan_shows lookup. Reclassified 344 previously-unknown entries; 183 non-concert entries with xx-dates also moved from their old keyword category to compilation (all already excluded from ranker).
Changed: concert_ranker/cli.py: _collection_worklist now LEFT JOINs lb_master and filters lb_status='public', excluding private/missing/nonexistent entries from scan worklists. Added _filter_non_public() helper (mirrors _filter_non_concerts) called from _rerank for the stored-metrics path. Scan 18 reranked: 13914 rows (was 15630); 808 non-concert + 1377 non-public removed.

[2026-06-29] — fix(concert-ranker): skip non-concert recordings + restore hf_ceiling_hz
Changed: concert_ranker/cli.py: _NON_CONCERT_CATEGORIES constant (studio/interview/tv/compilation/rehearsal/radio/soundcheck); _collection_worklist filters these from the scan worklist; _filter_non_concerts() helper removes them from metrics at rerank time. 469 non-concert entries now excluded from scan 18 scores (15630 vs 16099 rows).
Changed: concert_ranker/config.py: QUALITY_MODEL refit with hf_ceiling_hz forced back as 10th predictor (w=+0.42, rho_uni=+0.341). CV impact neutral (Spearman 0.6573 / within-1 76.0%). Moves bandwidth-limited bad recordings down: LB-7351 (F, "very muffled", hf_ceil=3kHz) C-→D+. Reranked scan_id=18.
Changed: concert_ranker/config.py: QUALITY_MODEL refit with hf_ceiling_hz forced back as 10th predictor (w=+0.42, rho_uni=+0.341). Forward selection had dropped it as collinear but scan-18 audit showed D/D-/F recordings have 26–43% incidence of hf_ceiling < 5kHz vs 0.17% for A-tier. CV impact neutral (Spearman 0.6573 / within-1 76.0% vs 0.6588 / 75.8%). Correctly moves bandwidth-limited bad recordings down: LB-7351 ("very muffled", hf_ceil=3kHz, LB=F) C-→D+; LB-7845 (D-) C-→D+. Reranked scan_id=18 (16099 recordings).

[2026-06-27] — feat(db): known-taper curated list + taper_name normalisation (TODO-173)
Changed: backend/db.py: added _KNOWN_TAPER_ALIASES dict (~100+ confirmed taper handles/aliases, all lowercase canonicals); _NOT_TAPER suppression set (mic models, format labels, editorial notes); _LT_TAPER_RE pattern for legendary taper series (lta–ltz); NT series (nta–ntz) aliases; step-0 known-handle scan in extract_taper_and_source fires before all heuristics; prefix-match canonicalization trims equipment bleed-through (e.g. "net taper e schoeps…" → "net taper e"); BOOTLEG: entries now store taper_name='bootleg'; quote-stripping from parsed taper names; taper_name lowercased for case-agnostic storage; _normalise_taper resolves known aliases; _KNOWN_TAPER_KEYS_SORTED pre-computed for prefix lookup
Changed: TODO.md: TODO-173 known tapers list updated with full confirmed set

[2026-06-27] — feat(db): entry_lineage table + batch parser + lineage API (CC_LINEAGE_PARSE)
Added: backend/db.py: entry_lineage USER table schema; _SAME_RE/_DIFF_RE/_DERIVED_RE/_BETTER_RE lineage regexes; extract_lb_references(), _normalise_taper(), _compute_parse_confidence(), upsert_entry_lineage(), get_lineage() functions; "entry_lineage" added to USER_TABLES
Changed: tools/tapematch/tapematch_session.py: _SAME_RE/_DIFF_RE now imported from backend.db (canonical source)
Added: tools/parse_lineage.py: CLI batch script to populate entry_lineage from entries.description (--force/--lb/--limit/--dry-run)
Added: backend/app.py: GET /api/lineage/<lb> route returns entry_lineage row as JSON
Added: tests/test_lineage.py: 8 tests covering extract_lb_references, parse_confidence, taper_normalised, and idempotency

[2026-06-27] — docs(schema): improved contrast, zoom slider, collapse/expand all buttons
Changed: docs/schema.html: raised contrast on col-type/col-note/stat-label/group-count/group-desc/card-desc/legend text; added zoom slider (60–150%) to header; added Expand All / Collapse All buttons scoped to active DB tab

[2026-06-27] — docs(schema): interactive schema viewer with FK navigation, search, tooltips, collapsible groups
Changed: docs/schema.html: added table descriptions, FK jump chips, click-to-highlight FK relationships (gold=focused/blue=related/dimmed), table search/filter, collapsible groups, floating column tooltips; JS auto-assigns data-table from card-name; TABLE_INFO covers all 51 tables; FK_SUPPLEMENT adds 12 undocumented foreign key relationships

[2026-06-26] — fix(scraper): diacritic-dropped locations corrected for 45 LB entries across 9 cities (BUG-211)
Fixed: data/site/detail/LB-*.html (45 files): patched cached HTML so re-scraping from local
  cache preserves correct city names with diacritics
Fixed: data/losslessbob.db entries table: corrected location for 45 entries —
  Saarbrücken (5): LB12124/16153/16154/16155/16167
  Düsseldorf (14): LB10133/11108/11143/11256/11303/11365/11555/12178/12186/13307/15100/16115/16182/16183
  Nürnberg (4): LB13434/16145/16147/16170
  Tübingen (2): LB11985/12043
  Göteborg (3): LB11521/12566/13053
  Malmö (8): LB04999/05212/07579/07751/09510/09715/12930/13273
  Montréal (2): LB14964/15249
  Zürich (6): LB09198/10088/14046/14047/14452/14453
  Jönköping (1): LB10977
  Venue corrections: LB04999 "Slottsmöllan", LB07579 "Malmö Arena", LB12930 "Mölleplatsen, Malmö"

[2026-06-26] — fix(gui): remove unimplemented ⌘K shortcut hints (BUG-222)
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: removed kbd-pill ⌘K span from search button
Fixed: gui_next/src/renderer/src/screens/ScreenHome.tsx: dropped cmd/⌘K tip from TIPS array (3→2 tips); updated render index logic
Fixed: gui_next/src/renderer/src/App.tsx: removed Kbd demo + "Global search" label from dev card; dropped unused Kbd import
Fixed: gui_next/src/renderer/src/locales/{en,fr,es,de,nl,it}.json: deleted tip1 (⌘K), promoted tip2→tip1, tip3→tip2

[2026-06-26] — fix(backend): incremental site crawler misses newly posted LB pages (BUG-217)
Fixed: backend/site_crawler.py: SEED_URLS and start_url are now always removed from
  `visited` before queuing, so index pages are re-fetched on every incremental run;
  their stored Last-Modified is loaded into lm_map so If-Modified-Since is used (304 =
  cheap no-op; 200 = index changed, new links extracted and queued)
Added: backend/site_crawler.py: flat-file download page added to SEED_URLS
  (checksum_lookup/checksum_lookup_lb_zip_download.htm)
Added: backend/db.py: get_inventory_last_modified() — targeted last_modified lookup for
  a list of URLs from site_inventory

[2026-06-26] — fix(gui+backend): spectrograms blank screen + no output (BUG-216)
Fixed: gui_next/src/renderer/src/lib/spectrogramStore.ts: dynRange default '-120' → '120'
Fixed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: dyn_range sent negative to
  SoX -z (requires positive int); now Math.abs(); label corrected to "dB range"
Fixed: backend/app.py: _spectro_state["errors"] was a list of dicts; TypeScript typed it as
  number; React crashed rendering objects in JSX → blank screen. Changed to int count; error
  details now logged via _log.error()

[2026-06-26] — chore(concert_ranker): validate new metrics on scan 17 — none enter QUALITY_MODEL (TODO-191)
Changed: tools/fit_aud_quality_model.py: added brickwall_score + single_ch_transient_count to
  candidate pool; updated speech_band_snr_db comment (rescan no longer pending).
  Findings: speech_band_snr_db (rho=0.409, Δ/σ=0.75) subsumed by existing predictors;
  brickwall_score (rho=-0.179, no signal); single_ch_transient_count BACKWARDS vs commentary.
  QUALITY_MODEL unchanged — scan 8 (2798-sample) fit retained; all three metrics stay in
  POLARITY for family scoring only.

[2026-06-25] — feat(concert_ranker): text features (TODO-188), brickwall/mic-hit waveform detectors (TODO-191), HF source discrimination (TODO-189), TV band detection (TODO-190)
Added: concert_ranker/text_features.py — new module: extract_text_features() parses 18 flaw/artifact
  vocabulary keys from entries.description (txt_clipping, txt_brickwall, txt_digipop, txt_dropout,
  txt_gap, txt_mic_hit, txt_hf_streak, txt_compression, txt_minidisc, txt_floating_parapet, txt_32k_dat,
  txt_talking, txt_singing, txt_limiting, txt_remaster, txt_tv_band, txt_cassette, txt_eac_match).
  Regex patterns cover LB site controlled vocabulary; all keys always present (0.0/1.0 binary).
Added: concert_ranker/features.py — extract_text() wrapper; _brickwall_score() (normalized slope
  variance in mid-amp vs loud frames, captures smooth between-peak ramps); _single_channel_transient_count()
  (L/R ≥2:1 asymmetric impulse events = mic hits, stereo only); _minidisc_parapet_score(), _32k_dat_flag(),
  _cassette_rolloff_flag() (HF ceiling shape discrimination from averaged NativeProbe PSD); _tv_band_flag()
  (narrow elevated band at 14.5-16.5 kHz with per-window pulsing variance check). All added to
  extract_distortion() and extract_hf_native() return dicts.
Changed: concert_ranker/audio/cache.py — NativeProbe gains window_psds_db field (n_windows × n_freqs,
  None by default); build_native_probe() populates it so TV band variance can be measured without a second
  full-file decode.
Changed: concert_ranker/calibration.py — description field threaded through stratified_sample() and
  decade_stratified_sample() into build_samples(); text features injected into calibration metrics dict
  (no rescan needed — DB-side extraction).
Changed: concert_ranker/cli.py — _inject_text() augments metrics dicts at rerank time (mirrors _inject_dff()
  pattern); called in _rerank().
Changed: concert_ranker/config.py — POLARITY entries added for all new features: speech_band_snr_db +1,
  brickwall_score/single_ch_transient_count/minidisc_score/dat32k_flag/cassette_flag -1, tv_band_flag 0,
  all 18 txt_* features (mostly -1, tv_band/cassette_flag 0 for informational ones).
Changed: tests/test_concert_ranker.py — 20 new tests: text feature extraction, brickwall score synthetic
  validation, single-channel transient detection, 32k DAT flag, cassette rolloff, TV band pulsing. 44 pass.

[2026-06-25] — fix(concert_ranker): remove backwards/noise metrics from family scoring and labeling
Changed: concert_ranker/config.py — directness polarity set to 0 (excluded from family comparison):
  scan-8 validation (n=2798 AUD) shows bad recordings score higher (rho=-0.272, commentary Δ/σ=-0.82)
  — the metric measures spectral imbalance, not recording proximity. Labels ("close/direct" /
  "distant/roomy") were inverted relative to actual quality. Removed from QUALITY_BANDS and all
  per-decade QUALITY band dicts. onset_clarity polarity set to 0 (rho=-0.131, commentary Δ/σ=+0.04
  — crowd noise inflates onset_env; no real clarity signal). Both metrics retained in QUALITY_MODEL
  where they contribute CV Spearman with correct negative weights.
Changed: concert_ranker/scoring.py — removed directness and onset_clarity from FAMILY_METRICS
  "clarity" family and from the _PRETTY verdict label map.
Added: concert_ranker/features.py — speech_band_snr_db metric in extract_clarity: 1-4 kHz SNR
  during loud vs quiet frames (same approach as crowd_snr_db but restricted to the vocal
  intelligibility band). Not yet in QUALITY_MODEL — needs rescan to validate against commentary.
Changed: tools/fit_aud_quality_model.py — added commentary audit section (Δ/σ per metric vs
  muffled/distant/upfront labels, with rho column and BACKWARDS detection); added speech_band_snr_db
  to candidate pool; skips candidates with no scan data.

[2026-06-25] — feat(concert_ranker): refit QUALITY_MODEL_SBD on full scan 9 corpus (TODO-183)
Changed: concert_ranker/config.py QUALITY_MODEL_SBD — refit on scan_id=9: 506 SBD+FM recordings
  (479 SBD + 27 FM) all scanned with the current dropout detector. dropout_count tested (rho=-0.077,
  p=0.082, weight ~0) — not predictive with consistent detector values; old rho=0.375 was a
  scan-version artifact from mixing old/new detector outputs across scans 3-7. Same 6 predictors
  as v1 (hiss_floor_db, hf_ceiling_hz, crest_factor_db, air_ratio_db, harsh_ratio_db, directness).
  Validation: AUD model on this set = Spearman 0.429 / 73.5% within one tier; new fit =
  Spearman 0.562 / 80.2% within one tier (5-fold CV, alpha=0.5). 24 tests pass.

[2026-06-25] — concert_ranker: hum_excess_db frequency-resolution fix (Δf 5.4 Hz → 0.5 Hz)
Changed: concert_ranker/features.py: _hum_excess_db now computes a dedicated high-res Welch
  PSD (nperseg=sr×2, Δf=0.5 Hz) instead of reusing the shared cache PSD (nperseg=4096,
  Δf≈5.4 Hz). Root cause of +0.117 rho confound: at 5.4 Hz resolution, G1 bass (49 Hz) and
  50 Hz mains shared the same bin; the 100 Hz and 250 Hz harmonic windows were empty (no bin
  within ±2 Hz). Peak window tightened from ±2 Hz to ±0.5 Hz; harmonics extended from 5 to 7.
  Synthetic validation: 49 Hz bass → 0.00, 58 Hz (A#1) → 0.00, genuine 50/60 Hz comb → fires.
  Needs re-scan to confirm rho improvement (scan_id=8 values computed with broken detector).

[2026-06-25] — concert_ranker: dff_vert_occ added to QUALITY_MODEL; AUD CV Spearman 0.659→0.664
Changed: concert_ranker/config.py: QUALITY_MODEL refit to include dff_vert_occ = log1p(vert_occ)
  from dff_reports; forward selection added it as 7th predictor (CV rho +0.006), weight -0.1274
  (higher vert count → lower rank); 9 total predictors. 5-fold CV Spearman 0.664 / 75.9% within 1 tier.
Changed: concert_ranker/cli.py: _inject_dff() helper — augments metrics dict at rerank time from
  dff_reports table (log1p transform); falls back to model median for LBs without DFF data.
Changed: concert_ranker/calibration.py: build_samples() now injects dff_vert_occ from dff_reports
  so future calibration runs include it automatically.
Added: tools/fit_aud_quality_model.py: fitting script for the AUD ridge model; forward selection over
  14-candidate pool, outputs QUALITY_MODEL dict; accepts --scan-id --alpha --no-forward-select.

[2026-06-25] — tools/parse_dff_reports.py: DFF HTML parser — 12,523 LBs written to dff_reports table
Added: tools/parse_dff_reports.py: parses all DigiFlawFinder HTML reports in data/site/files/,
  extracts drop/clip/horz/vert total occurrence counts (handles both the older Totals-section format
  and the newer "No Flaws Found" format), sums multi-disc primary files per LB, uses xref files only
  for LBs with no primary file, writes to dff_reports table (lb_number PK). 12,523 LBs written,
  67 unresolvable errors (~0.5%), 99.5% parse rate. --summary flag prints vert_occ vs rating table.
Finding: vert_occ gradient confirmed in full corpus: median 1 at A/A- tiers rising to 8 at F.

[2026-06-25] — concert_ranker: dropout_count rework — 3-mode defect detector + DFF vert finding
Changed: concert_ranker/features.py: replaced locally-normalized roughness (rho=+0.417, measuring
  musical transient density) with three DigiFlawFinder-modelled detectors: silence gap (DFF Drops),
  stuck sample (DFF Horizontals), and digipop/vertical (DFF Verticals — exactly-2-wide symmetric
  first-diff spike; min/max ratio >0.5 rejects asymmetric musical attacks). 8 tests, all pass.
Added: tests/test_concert_ranker.py: 8 dropout unit tests including digipop detection.
Finding: DFF vert_occ (from 14,090 downloaded DigiFlawFinder reports) correlates rho=-0.157
  (p=1.5e-14) with AUD rating on scan_id 8 corpus — monotonic A→F (median 1→8). Drop/clip/horz
  near zero. DFF parser to extract per-LB vert counts is the next recommended step.

[2026-06-25] — tapematch: FINDINGS.md — synthesized performance report and architecture limits
Added: tools/tapematch/FINDINGS.md: full findings report — accuracy metrics, all 7 approaches
  tried with outcomes, root-cause analysis, what works, future angles, and recommendation

[2026-06-25] — tapematch: cancel TODO-185/144/140 (all falsified); start TODO-184 polarity batch
Changed: tools/tapematch/tapematch/match.py: added lowband_envelope_corr() (250-2000 Hz zero-phase
  bandpass + log-RMS envelope cross-correlation with lag search; unit tests in
  tests/test_lowband_corr.py, 4 passing). Added windowed_fingerprints() / best_window_fingerprint_match()
  / _fingerprint_hashes() for TODO-185 windowed-overlap investigation (retained, not wired into cli.py).
Changed: tools/tapematch/tapematch/align.py: added locate_splice_points() (extracts step indices from
  lag curve, unit tests in tests/test_splice_points.py, 5 passing; retained, not wired into cli.py).
Added: tools/tapematch/tests/test_fingerprint_windows.py (4 passing), test_splice_points.py (5 passing),
  test_lowband_corr.py (4 passing).
Added: tools/tapematch/calibrate_fingerprint_localize.py, calibrate_fingerprint_baseline.py,
  calibrate_piecewise.py, calibrate_lowband.py — falsify-first pilot scripts (read-only, no cli.py wire).
Changed: tools/tapematch/BASELINE.md: Task 8 (TODO-185 — 3 approaches: contig-run audit, HF-band
  fingerprint, 200-4kHz fingerprint; all falsified); Task 9 (TODO-144 — piecewise pilot, per-seg p50
  same-source 0.004 < different-source 0.005); Task 10 (TODO-140 — 250-2000 Hz envelope pilot,
  confirmed-distinct LB-02470/LB-02478 +0.357 > all missed-pairs max +0.201).
Added: tools/tapematch/validate_polarity.py — batch polarity-rescue dry run across ~474 contradicted-claim
  dates; JSONL checkpoint output; batch in progress (TODO-184 Checkpoint 1 pending).

[2026-06-25] — fix(scheduler): tapematch tmp-dir cleanup race deletes concurrent run's files (BUG-224)
Fixed: tools/tapematch/tapematch_session.py: _clean_stale_tmp_dirs() rmtree'd every
  tapematch_* dir under /mnt/DATA0/tmp unconditionally before each subprocess launch, with no
  liveness check -- two concurrent tapematch_session.py sessions (1989-06-04, 1990-01-12)
  deleted the in-flight memmaps of a separate validate_polarity.py batch run, causing
  cascading FileNotFoundError crashes on 5 dates. Added _tmp_dir_in_use() (open-fd scan via
  /proc + recent-mtime check); cleanup now skips any dir that's still actively written to or
  held open by a running process, regardless of which script or session owns it. New tests:
  tools/tapematch/tests/test_clean_stale_tmp_dirs.py (4 passing).
Added: tools/tapematch/tapematch/match.py: windowed_fingerprints()/best_window_fingerprint_match()
  (TODO-185, revised approach) -- landmark-hash-based localized-overlap evidence to replace the
  falsified "best contiguous run on 60s residual_corr windows" premise (audit on 1991-11-05
  found zero signal differentiation between 5 curator-claimed same-source pairs and a known-
  distinct negative control at both +-10s and +-120s lag search). _fingerprint_hashes() extracted
  from fingerprint_window() as a shared helper. Existing test suite verified unaffected (45
  passed; the only 4 failures are pre-existing and unrelated, in test_batch_queue.py /
  test_find_lb_folders_no_audio.py).

[2026-06-25] — feat(concert_ranker): refit AUD QUALITY_MODEL on scan_id 8 (2798 AUD) (TODO-183)
Changed: concert_ranker/config.py QUALITY_MODEL — refit the absolute-score ridge on the full
  overnight by-decade scan (scan_id 8, 2798 rated AUD, 6x the prior 466-recording basis). New
  predictors chosen by forward selection over a 17-metric pool (alpha=0.3): hiss_floor_db,
  bass_ratio_db, mud_ratio_db, onset_clarity, directness, crowd_snr_db, harsh_ratio_db,
  presence_ratio_db (dropped the collinear HF set hf_ceiling/centroid/air/crest). Every weight's
  sign matches its univariate direction — no confound. 5-fold CV (3 seeds) to LB rating: Spearman
  0.659, 75.6% within one letter tier; verified via the live predict_rank path at 0.661 / 75.9%.
  The previous 466-fit model scored only 0.561 / 46%-within-1 on this full set (mis-centered
  intercept fit on a middle-focused sample); the refit re-centers to the collection's true mean
  rank (~9.8). SBD model (QUALITY_MODEL_SBD) untouched. 16 concert_ranker tests pass.

[2026-06-25] — fix(concert_ranker): disable confounded dropout_count disqualifier (TODO-183)
Changed: concert_ranker/config.py DISQUALIFIERS — removed the dropout_count>150 "has dropouts/
  glitches" entry. The overnight calibration scan (scan_id 8, 2798 AUD, by-decade, all ratings —
  the fresh full scan meant to validate the 06-24 locally-normalized-roughness rework) shows the
  de-confounding did NOT hold at scale: rho vs rating = +0.417 (p=3e-118), median dropout by tier
  A:118 A-:55 B:27 B-:12 ... C/D ~6-17, i.e. the best recordings score highest. The detector still
  tracks transient/HF density, not defects, so the 150 threshold was mislabeling many A-tier
  recordings. Disabled (commented out) until the detector is reworked; comment block corrected
  (previously claimed "the confound is GONE"). dropout_count is not a QUALITY_MODEL predictor, so
  absolute scores/grades are unaffected. 16 concert_ranker tests pass.
Verified: scan_id 8 finished cleanly overnight (2798/2799 scanned; 1 fail = LB1489 empty folder).
  Calibration is report-only; band-cutoff refits from scan_id 8 not yet applied (current basis
  remains scan_id 6).

[2026-06-24] — feat(concert_ranker): dedicated SBD/FM absolute quality model (TODO-183)
Added: concert_ranker/config.py QUALITY_MODEL_SBD — separate ridge model (predictors hiss_floor_db,
  hf_ceiling_hz, crest_factor_db, air_ratio_db, harsh_ratio_db, directness) fit on the 223
  SBD+FM recordings with metrics+rating across scans 3-7 (latest scan per LB). AUD's predictors
  (mud_ratio_db, presence_ratio_db, spectral_centroid_hz, crowd_snr_db) don't separate SBD tiers
  (|rho| < 0.25); harsh_ratio_db/directness do and aren't in the AUD set. dropout_count (rho 0.375)
  deliberately excluded — most of the sample predates the dropout-detector rework, so its values
  aren't comparable to current scans; revisit once SBD is re-scanned with the current detector.
  Validation: applying the AUD model to this SBD+FM set gets a comparable rank correlation
  (Spearman 0.511) but only 48% within-one-letter-tier (wrong absolute level); the dedicated fit
  gets Spearman 0.53 and 69% within one tier (5-fold CV).
Changed: concert_ranker/quality_score.py predict_rank()/grade() take an optional source_class arg
  and route SBD/FM to QUALITY_MODEL_SBD, everything else (incl. unknown/None) to QUALITY_MODEL — same
  pattern as config.resolve_band_set()'s class resolution.
Changed: concert_ranker/families.py rank_group() passes group[lb]["source_class"] into
  quality_score.grade() so each recording's verdict grade uses the right model.
Added: tests/test_concert_ranker.py test_absolute_quality_grade_sbd_model — SBD/FM route to
  QUALITY_MODEL_SBD (not the AUD model) and still discriminate good/bad metrics; 16 tests pass.
Verified: `concert_ranker rerank --scan-id 6` end-to-end against the real DB — SBD/FM grades now
  cluster B-/A (matching the actual top-heavy SBD rating distribution) instead of the AUD curve.

[2026-06-24] — feat(db): curated_lists / curated_list_entries — carbonbit + 10haaf picks (TODO-181)
Added: backend/db.py — curated_lists + curated_list_entries tables (MASTER_TABLES, schema v10);
  CRUD: get_or_create_curated_list, get_curated_lists, add_curated_list_entries,
  get_curated_list_entries.
Added: tools/import_curated_lists.py — stdlib-only (zipfile + ElementTree) importer. Parses
  data/lists/FLglist.xlsx ("front line G list" sheet: one row per date, column C is carbonbit's
  pick(s) — multiple LB numbers per date allowed) and data/lists/dylan_boots.zip +
  data/lists/years.zip (10haaf's per-year HTML bootleg catalogs; every LB-XXXXX found across both
  archives is unioned, since the older per-year pages and the newer allboots.html disagree on
  ~1,100 entries and neither is a clean superset). Idempotent via the entries table's
  UNIQUE(list_id, lb_number) constraint. Ran once against the live DB: carbonbit 4503 entries,
  10haaf 7572 entries.
Note: GUI/filter surfacing on the Library screen (the rest of TODO-181) is intentionally not done
  yet — this pass is DB + import only, per explicit scope decision.

[2026-06-24] — feat(tapematch): polarity-inversion rescue — step 2, wired into the matcher (TODO-184)
Added: tools/tapematch/tapematch/match.py polarity_rescue(): per-anchor driver that re-scores a
  near-zero pair across the L-R cross terms (mid-side / side-mid), each doing its OWN lag search
  (mid-vs-mid can't lock when one channel is inverted), and returns the best median + pairing.
Changed: tools/tapematch/tapematch/cli.py Pass 1 — when polarity.enabled, decode stereo and persist
  an L-R "side" memmap per stereo source (identical trim bounds to the mid memmap; mono sources get
  none); added side_paths dict + _mmap_side() helper. Default OFF, so the mono fast-path is unchanged.
Changed: tools/tapematch/tapematch/cli.py residual matrix loop — after speed refine, a pair whose
  median corr is below polarity.rescue_corr_ceiling is re-scored via match.polarity_rescue (speed-
  correcting both the other source's mid and side by the pair ratio), kept only if it improves, and
  logged as POLARITY_RESCUE. Keep-if-improves means it can rescue a true inverted-channel pair but
  cannot manufacture a false merge.
Added: tools/tapematch/tests/test_polarity_corr.py — 2 driver tests (own-lag recovery of an inverted
  pair; independent sources stay below threshold). 6 polarity tests + 22-test matcher subset pass.
Note: step 3 (enable on the ~37 contradicted-claim dates + validate the stereo Pass-1 memory profile
  on real data, then consider default-on) remains open under TODO-184.

[2026-06-24] — feat(tapematch): polarity-inversion rescue — step 1, config-gated core (TODO-184)
Added: tools/tapematch/tapematch/match.py polarity_aware_corr(): scores an aligned pair across
  mid-mid / mid-side / side-mid channel-polarity variants and keeps the strongest, so a genuine
  same-source copy with one channel polarity-inverted ("right channel inverted") — which collapses
  the L+R mid-vs-mid correlation that Pass 1 ingests — is recovered via the L-R cross term.
Added: tools/tapematch/config.yaml polarity block (enabled: false, rescue_corr_ceiling: 0.60),
  DEFAULT OFF; documents that enabling will require stereo ingest in Pass 1 (raises peak RAM) and
  validation before turning on.
Added: tools/tapematch/tests/test_polarity_corr.py: 4 tests — right/left inverted-channel copies
  rescued ~1.0, independent sources not merged, clean copy still scores on mid-mid.
Note: this is step 1 (testable core). Step 2 (Pass-1 stereo/side-memmap wiring + matrix-loop rescue
  branch) and step 3 (re-run the contradicted-claim dates) remain open under TODO-184. Speed-offset
  false-negatives were found to be ALREADY handled (±30000 ppm + lag-slope refine, committed 06-21).

[2026-06-24] — feat(concert_ranker): absolute quality score — 0-100 + A+..F grade per recording (TODO-183)
Added: concert_ranker/quality_score.py + config.QUALITY_MODEL — a ridge regression predicting the LB
  rating rank (1=F..13=A+) from 8 validated metrics (hiss/hf_ceiling/centroid/crest/crowd_snr/air/mud/
  presence), giving every recording a standalone 0-100 score + +/- letter grade, independent of the
  within-family ranking. Fitted on 466 AUD (scans 6+7). HELD-OUT (5-fold CV) correlation to the real
  LB rating: Spearman 0.65, 93% within one letter tier. Stored-grade check across 873 recordings (incl.
  the C-rich middle): rho 0.67, 94% within one letter; median score per tier A 72 / B 60 / C 46 / D 38.
Changed: families.rank_group now computes the grade per recording and prepends "Grade X (N/100)." to the
  verdict; lb/repo.py quality_recording_scores gained abs_score / abs_grade columns (ensure_schema ALTER
  migration; write_scores/load_scores updated); cli report CSV includes them. Added a unit test (15 total).
  AUD-fit model applied to all classes — SBD/FM grades are approximate (TODO-183).

[2026-06-24] — fix(tapematch): record real model in analysis attribution (BUG-223)
Fixed: .claude/commands/tapematch-batch.md: step 4 hardcoded `*Claude claude-sonnet-4-6 — …*` for
  every session regardless of the running model; now requires the actual session model id. Made all
  per-model quality audits of the analysis corpus impossible.
Fixed: data/tapematch/runs/*/analysis.md (x10): corrected attribution to `claude-haiku-4-5` on the
  analyses proven (via session transcripts) to have been written by haiku, not sonnet — 1989-08-29,
  1989-08-31, 1989-11-02, 1990-06-29, 1990-06-30, 1990-07-07, 1990-07-08, 1990-08-12, 1990-08-20,
  1990-09-05. Opus-stamped files left as-is (correctly self-attributed).

[2026-06-24] — fix(concert_ranker): rework dropout click detector — de-confound from dynamics (TODO-183)
Changed: concert_ranker/features.py _dropout_count(): replaced isolated-2nd-difference detection with
  LOCALLY-NORMALIZED roughness. A click is flagged where |2nd difference| exceeds the LOCAL roughness
  level (a ~12 ms rolling mean via scipy.ndimage.uniform_filter1d), so loud/dynamic passages no longer
  trip it — only narrow (<=3-sample) events count. Validated on a stratified AUD subset: rho vs rating
  +0.43 -> -0.04 (confound eliminated; it's now a neutral defect flag, not a fidelity proxy), counts
  sane (clean ~4-10, glitchy tail ~80-280) vs the old thousands. Much faster too (uniform_filter1d, not
  per-sample median). (A first attempt using a median-filter residual was discarded — it fires on all
  oscillating audio.)
Changed: concert_ranker/config.py DISQUALIFIERS: dropout_count 6900 -> 150 (provisional for the new
  scale). NOTE: scan_id 6's stored dropout values are from the OLD detector — a fresh scan repopulates
  them and the threshold should be refit then.

[2026-06-24] — feat(concert_ranker): per-class bands (hybrid — crowd held absolute) (TODO-183)
Added: concert_ranker/config.py: CLASS_BANDS {"SBD": ...} (fit from 165 SBD in scan_id 6) + resolve_band_set(
  decade, source_class). SBD/FM band hiss + tonal against soundboard norms (SBD hiss floor is much lower,
  median -9.2 vs AUD -5.2, so a soundboard that's hissy FOR a soundboard now flags); FM (n=27) reuses SBD.
Changed: scoring.all_bands / explain_recording + families.rank_group/rank_scan take source_class
  (already present in the loaded metrics) and resolve class+era bands.
Decision: crowd_snr_db is held on the GLOBAL (absolute) band for every class/era inside _build_decade_bands.
  Full per-class relativization made ~60% of soundboards read "some crowd"/"crowd-heavy" (an 8.5-dB SBD
  has far less crowd than any AUD — it should read "clean"); crowd level is meaningful absolutely, and
  within-class fairness is already handled by MAD-z ranking over same-show siblings. Effect: 0 crowd-label
  changes on SBD (the A-rated soundboards that wrongly read "crowd-heavy" now read absolute "some crowd").
  Added tests/test_concert_ranker.py::test_hybrid_crowd_global_hiss_per_class (14 tests pass).

[2026-06-24] — feat(concert_ranker): per-decade bands — era-relative quality labels (TODO-183)
Added: concert_ranker/config.py: _DECADE_CUTS (AUD percentiles per decade from scan_id 6) +
  _build_decade_bands() + DECADE_BANDS {1960..2010: {SIGNED/SEVERITY/QUALITY}} + decade_of(). Recording
  tech shifts the raw scales a lot by era (AUD hiss_floor_db "hissy" cut runs +0.6 in the 1960s tape era
  to -1.4 in the 2000s digital era), so a single global band over-flagged vintage shows as hissy and
  NEVER flagged modern ones. Per-decade bands judge each recording against its own era.
Changed: concert_ranker/scoring.py: band_metric() takes optional per-set band dicts; all_bands(raw,
  decade) + explain_recording(..., decade) select DECADE_BANDS[decade] (global fallback when the decade
  is unknown/unrepresented).
Changed: concert_ranker/families.py: load_decade_map() ({lb: decade} from entries.date_str);
  rank_group/rank_scan thread decades through. cli._rerank passes the decade map so scan/rerank/report
  all band per-era. sibilance/dynamic_range + disqualifiers stay global.
  Effect on scan_id 6 AUD 'hissy': normalized to ~10%/decade (was 1960s-90s over-flagged, 2000s/2010s
  never flagged). Added tests/test_concert_ranker.py::test_decade_bands_are_era_relative (13 tests pass).

[2026-06-24] — feat(concert_ranker): refit all bands from the 697-show decade scan (TODO-183)
Fixed: concert_ranker/calibrate.py score_separation(): forced float dtype so stored None metric values
  (NaN coerced on persist) no longer crash np.isnan — the larger 697-set exposed this (mono spatial /
  empty HF probe produce None). The scan persisted 696/697 fine; only the post-scan report had crashed.
Changed: concert_ranker/config.py: SIGNED/SEVERITY/QUALITY band cutoffs + dropout disqualifier refit
  from scan_id 6 (697 decade-stratified shows, ~320 AUD percentiles — supersedes the scan_id 3 fit).
  At scale the de-confounding held/strengthened: AUD hiss_floor_db -0.64 (now the single strongest
  quality predictor), harsh_ratio_db -0.03 (neutral). crowd_snr tiers widened (p10/p30/p60) to restore
  "crowd-heavy" recall. dropout disqualifier 1000 -> 6900 (worst-track p95) — kept HIGH because the
  metric still correlates +0.43 with rating (isolated-spike test partly catches sharp musical transients
  in dynamic well-rated shows), so a low cutoff would wrongly demote good recordings. Net over 696 shows:
  label-fires 1117 -> 930; verdicts validated against LB comments (A=clean/very-quiet, F=hissy/muddy/buried).
Noted: AUD hiss_floor_db median swings by era (-2.0 1960s tape -> -8.1 2000s digital) — strong candidate
  for per-decade band sets (recorded in config + TODO-183); global bands applied for now.

[2026-06-24] — fix(concert_ranker): rework hum + dropout metrics, worst-track aggregation, decade sampler (TODO-183)
Changed: concert_ranker/features.py:
  - _dropout_count(): replaced the "2nd-difference z>12" test (counted every musical transient —
    medians in the thousands, useless) with ISOLATED-discontinuity detection (z>30 AND both neighbours
    z<8). Clean shows now read 0; LB1233 (comment: "small pop t11 0:15, 1:42…") reads 108 on that track.
  - _hum_excess_db(): now requires a 50/60 Hz harmonic COMB (>=3 harmonics of one mains family above
    the local floor), not the worst single peak — a lone bass bin no longer trips it. Round-3 rho
    +0.45 -> n/a (fires on 0/117, no longer confounded with bass; inert but safe).
Changed: concert_ranker/scan.py aggregate_tracks(): defect metrics (dropout_count, clip_fraction,
  hum_excess_db) now aggregate by WORST track (max) instead of median — median hid one-bad-track
  glitches (e.g. LB2100 had a 1146-glitch track but aggregated to 0). _WORST_TRACK_METRICS set added.
Changed: concert_ranker/config.py DISQUALIFIERS: dropout_count 25000 -> 1000 (provisional from scan_id 5
  worst-track distribution), hum_excess_db 15 -> 10. crowd_snr/bands unchanged.
Added: concert_ranker/calibration.py decade_stratified_sample() + _entry_year() (parses M/D/YY dates);
  `calibrate --by-decade` CLI flag — large decade × rating-tier × source_class sample (every decade
  represented, ALL bad-tier included, good/mid capped at --per-cell). Launched an overnight scan_id 6
  of 697 recordings (all 6 decades, AUD 320/SBD 165/UNKNOWN 184/FM 28) for further iteration.

[2026-06-23] — fix(concert_ranker): de-confound harsh + hiss metrics, calibration round 2 (TODO-183)
Changed: concert_ranker/features.py: two extractors made level-independent after round-1 calibration
  found them confounded with overall HF brightness (both rose WITH the rating):
  - harsh_ratio_db: was harsh(2-5k) - ref_mid; now harsh - 0.5*(ref_mid + sibilance), i.e. a LOCAL
    2-5 kHz prominence above its flanks. Spearman vs rating +0.44 -> +0.06 (no longer fakes harshness
    from brightness).
  - hiss_floor_db: was the absolute native 8-14 kHz level (included musical HF); now computed at bulk
    rate as 8-11 kHz persistence in quiet vs loud frames (new _hiss_floor_db helper) — real hiss is
    constant when music drops, musical HF collapses. Spearman +0.31 -> -0.52 (now correctly predicts
    WORSE ratings, a strong signal). Moved hiss_floor_db out of extract_hf_native into extract_distortion.
Changed: concert_ranker/config.py: harsh_ratio_db + hiss_floor_db SEVERITY bands refit from scan_id 4.
  "hissy"/"harsh" now fire only on B-/C/D shows — zero A-tier false positives (round 1 wrongly tagged
  A-rated LB1419/LB1233 as hissy; both now read "very quiet"). All other metrics/bands unchanged.
Changed: concert_ranker/calibrate.py: (round-1 fix) score_separation `useful` cast to python bool.
  scan_id 4 recorded as the CURRENT calibration basis (supersedes scan 3).

[2026-06-23] — feat(concert_ranker): calibrate bands against real audio + staging support (TODO-183)
Changed: concert_ranker/lb/source_type.py: derive_source_class() now trusts the curator
  entries.source_type column first (Audience→AUD / Soundboard→SBD / FM/Pre-FM→FM / Mixed,ALD,Master→
  UNKNOWN), falling back to free-text mining only when NULL. Real collection split is now
  AUD 11,731 / SBD 480 / FM 28 / UNKNOWN 357 (was ~60% UNKNOWN). classify_entries + calibration +
  cli worklist updated to pass the column.
Added: concert_ranker/runner.py group_by_device(); --staging-dir on `scan` and `calibrate`
  (run_calibration gained classes= + staging_dir=). Staging copies each folder to fast scratch
  (one producer per physical drive via st_dev) before decoding — used /mnt/DATA2 for the cal run.
Fixed: concert_ranker/calibrate.py score_separation(): `useful` was a numpy bool (serialized as the
  string "False"); cast to python bool.
Changed: concert_ranker/config.py: SIGNED/SEVERITY/QUALITY band cutoffs + the crowd_snr "buried"
  disqualifier REPLACED with values fitted from scan_id 3 (117-show sample: 73 AUD + 44 SBD, staged).
  The first-principles guesses fired muddy/dull/boomy on ~95% of real recordings (measured AUD scales
  were far off — mud_ratio_db 18-34 dB, air_ratio_db -44..-24); calibrated cutoffs cut label-fires
  476→171 on the sample and made harsh/hissy/thin/bright labels functional. dropout_count/hum_excess
  parked at "rarely fires" (dropout counts normal transients; hum confounded with level) pending
  metric rework. Calibration findings (Spearman per class, fitted thresholds, label precision/recall)
  in concert_ranker/BUILD_REPORT-style notes; scan_id 3 retained as the fit basis.

[2026-06-23] — feat(backend): Concert Ranker v1 — audio quality scoring + ranking (TODO-183)
Added: concert_ranker/ — new repo-root package. Unzipped the v1 "scoring brain" (config/scoring/
  features/calibrate/audio.cache, pre-built + tested on synthetic audio) and wired it to the real
  machine per instructions/CC_CONCERT_RANKER.md:
  - lb/repo.py: USER-tier persistence (standalone WAL connections, one-transaction-per-recording,
    scan create, raw-metric + score upsert, restart skip, rerank reads). _jsonable() coerces numpy
    float32 / NaN to JSON-safe values.
  - lb/source_type.py: SBD/AUD/FM/UNKNOWN derivation reusing backend.db.classify_source_type
    (Matrix/ALD → UNKNOWN so they never contaminate a pure source-class curve).
  - lb/commentary.py: keyword-mines entries.description into calibrate.LABEL_KEYWORDS (the
    validation oracle), word-boundary matched.
  - audio/io.py: ffmpeg decode (one bulk decode at 22.05 kHz → build_track_cache; 8×20 s windows at
    44.1 kHz → build_native_probe), mirroring tools/tapematch/tapematch/audio.py.
  - scan.py / runner.py: per-folder decode→extract→aggregate(median)→one transaction; direct
    process-pool driver + producer/consumer staging loop (crash=scrap, skip done LBs on restart).
  - families.py: rank within recording_families (MAD-z normalize → fuse → rank_in_family), standalone
    fallback (absolute bands only); sibling-relative completeness injected at rank time.
  - calibration.py: stratified rating×source_class sample → scan → score_separation/fit_thresholds/
    validate_labels; returns a report (does NOT auto-rewrite config.py — human-reviewed step).
  - cli.py: `scan` / `calibrate` / `rerank` / `report` (rerank works purely from stored metric_json).
Added: backend/db.py: USER tables quality_scans / quality_recording_metrics (raw metric_json stored
  separately from scores) / quality_recording_scores, registered in USER_TABLES; init_db creates them.
Added: tests/test_concert_ranker.py — repo roundtrip/idempotency/sanitize, source-class, commentary,
  family ranking, standalone, and rerank-from-stored-metrics (11 tests). No new dependencies
  (numpy/scipy already pinned; ffmpeg is a system binary, as for tapematch).

[2026-06-22] — feat(backend+gui): surface TapeMatch "needs review" verdicts as a queryable DB flag
Added: backend/db.py: tapematch_family_meta.review_flag (INTEGER) and .review_reason (TEXT) columns
  + init_db() migration; MASTER_SCHEMA_VERSION bumped 8->9.
Added: backend/paths.py: TAPEMATCH_RUNS_DIR constant (data/tapematch/runs).
Changed: backend/tapematch_sync.py: parses each synced date's analysis.md "## Verdict:" line
  (_parse_verdict/_read_review_flag/_resolve_run_dir) and writes review_flag/review_reason into
  tapematch_family_meta, so the tapematch-batch skill's "needs review" human judgment calls are no
  longer buried in per-run analysis.md files only — added init_db() call so the standalone CLI sync
  path (`python -m backend.tapematch_sync`) picks up schema migrations even without app.py running.
Changed: backend/app.py: GET /api/tapematch/families now selects fam_needs_review/fam_review_reason.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: recording-lens family rows show a
  "Needs review" warn-tone Pill (with reason as tooltip) when fam.needsReview is set.
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: library.tooltip.tapematchReview,
  library.panel.needsReview.
Added: tests/test_tapematch_sync.py: 7 cases covering _parse_verdict's em-dash verdict-line parsing.

[2026-06-22] — feat(gui): Unified Library visual refinement — type-scale roles + tabbed detail panels
Added: gui_next/src/renderer/src/lib/tokens.ts: nine --t-* type-scale role variables (display/title/
  strong/body/meta/label/micro/mono/mono-sm), four --w-* weight-ramp variables (reg/med/semi/bold),
  and --track-eyebrow, all emitted in applyTheme() and scaled by the active base fontSize. The legacy
  --lbb-fs-* loop stays for other screens. Implements instructions/library Pixel Spec §2/§3.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: replaced every raw fontSize/fontWeight
  literal with --t-*/--w-* roles (650→semi, 800→bold); reworked the performance-table column model —
  dropped the dead 32px spacer, fixed each data column to its longest content (Date 104 · Show 345 ·
  Tour 155 · Families 116 · Recs 52 · ★ 46 · Coverage 112) and added a single trailing flex spacer so
  slack parks at the table's trailing edge; recording-lens ★ column 54→48 (§5/§6). Families column
  was already collapsed to one SRC ×N pill per source family.
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: converted both detail panels
  from a single flat scroll to a pinned identity block + tab strip + swappable pane (new TabStrip
  component). Performance tabs = Overview / Recordings (count) / Setlist / Seed & Share; recording
  tabs = Overview / Assets / Seed & Share. Scroll position resets to top on tab change; Seed & Share
  is now a peer tab reachable in one click. All zone/identity text routed to --t-*/--w-* (§8–§11).
Changed: gui_next/src/renderer/src/components/primitives.tsx: Pill routed to --t-micro/--w-semi,
  centralizing the 650→600 weight normalization (§7).
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: library.panel.tab{Overview,
  Recordings,Setlist,Assets,Share} for the new detail-panel tabs.
Fixed: BUG-217 (summary strip wrapped to two lines and clipped) and BUG-218 (★ rating ellipsized) —
  fixed in passing per the spec's column/summary rework.

[2026-06-21] — fix(gui+scraper): Range Scrape with Force re-scrape ignores end_lb, scrapes all entries
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx:439 was sending lb_numbers array
  instead of start_lb/end_lb parameters; backend route ignored the array and defaulted to
  scraping from LB-1 with no upper limit. Now sends correct start_lb and end_lb parameters.

[2026-06-21] — feat(gui): copy forum topic URL to clipboard after a successful post
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: onForum now reads topic_url from the
  /api/entry/<lb>/post_forum response and writes it to the clipboard on success (single post copies the
  one link; batch copies all successful links newline-joined). Single-post toast switched to
  library.toast.postedForumCopied; batch toast appends library.toast.linksCopiedSuffix.
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: postedForumCopied + linksCopiedSuffix
  (pluralized) toast strings.

[2026-06-21] — fix(scraper): tapematch speed-offset false-distinct — lag-slope ratio refinement
Root cause: across observations.db, curator-says-same pairs that tapematch called "distinct" had
  median |speed| 9500 ppm / median corr 0.004 (vs 0 ppm / 0.815 for the pairs it got right), and 18%
  of ALL pairs railed at the ±20000 ppm edge of estimate_ratio's search range. The primary residual
  matrix resamples by the ~500 ppm coarse envelope ratio before the sample-level residual_corr, but a
  45s window tolerates only ~20 ppm residual speed error (measured: corr 1.0 at ≤20 ppm, 0.015 at
  50 ppm) — so coarse-grid error and clamped >2% offsets decorrelated true matches.
Changed: tools/tapematch/tapematch/match.py: estimate_ratio range/resolution now config-driven
  (match.ratio_search_min/max/steps); added corrected_ratio_from_lags() (pure slope→ratio math,
  refined = ratio/(1+slope)) and refine_speed_ratio() (iterates the lag-slope correction to <5 ppm).
  Lags come from drift-robust music cross-correlation, so they stay measurable when residual_corr has
  collapsed — a far finer, unbounded speed estimate than the envelope grid.
Changed: tools/tapematch/tapematch/cli.py: primary residual matrix refines the ratio for ambiguous
  high-ppm pairs (refine.trigger_min_ppm / trigger_corr_ceiling) and keeps it only if median
  residual_corr improves — self-limiting (cannot manufacture a false merge) and non-regressing.
Changed: tools/tapematch/config.yaml: widened coarse search to ±30000 ppm; new `refine` block.
Added: tools/tapematch/tests/test_ratio_refine.py: recovers offsets incl. +25000 ppm (beyond the old
  rail) to <60 ppm, sign-checked, with a different-source no-merge control. Full suite: 39 pass, 6 new;
  the 4 failing tests (test_batch_queue / test_find_lb_folders_no_audio) are pre-existing and unrelated.
Note: validated synthetically (ratio recovery) + safety guard; production confirmation is a full re-run
  of high-ppm dates (e.g. 1990-06-17, 1990-06-27) to confirm false-distinct splits collapse into the
  curator-confirmed families. See tools/tapematch/BASELINE.md (2026-06-21 section).

[2026-06-20] — feat(gui): TODO-150 step 10 — Library screen i18n (in-screen strings)
Added: gui_next/src/renderer/src/locales/en.json: new top-level `library` namespace (~214 keys:
  lens/actions/groups/bulk/toolbar/facets/views/scope/statusValue/coverageValue/columns/summary/
  empty/tooltip/ctx/toast/panel/coverage/family/setlist/share/assets), with `_one`/`_other` plural
  forms for all counted strings.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx, components/library/DetailPanel.tsx,
  components/library/actions.tsx: extracted every hardcoded English string to `t()` calls. The
  shared action registry (`buildRecordingActions`/`buildPerformanceActions`) and `coverageLabel()`
  are plain functions, so they now take a `TFunction` param threaded from each caller's
  `useTranslation()`; every rendering sub-component gained its own `useTranslation()`. Status/view/
  coverage display values use typed literal-key maps (STATUS_LABEL_KEY/VIEW_LABEL_KEY/
  COVERAGE_LABEL_KEY) so the typed `t()` resolves them without template-literal keys. All three
  files are tsc-clean; `electron-vite build` passes.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: filled the new `library` keys via
  DeepL (~19.7k chars). A few values need a human pass (DeepL quality, not bugs): de
  `lens.byPerformance` → "Nach Leistung" (wrong sense of "performance"), `panel.youHold_other`
  garbled, and `summary.toGo`/`facets.decade` came back English in several locales. (The
  `scripts/deepl_translate_gui_next.py` missing-key/`set_leaf` fixes that made translating a brand-new
  namespace possible were logged in the earlier DeepL-sweep entry below.)

[2026-06-20] — feat(gui): TODO-155 pipeline stage icons — implement design_handoff_pipeline_icons
Added: gui_next/src/renderer/src/components/pipeline/PipelineIcon.tsx: new reusable component
  porting the locked "Pipeline Stage Icons" handoff (Option D tactile tile · Pulse animation ·
  Vivid palette) into the React stack. Exports <PipelineIcon stage status size />, PipelineGlyph,
  PIPELINE_STAGES, and PipelineStage/PipelineStatus types. Glyph paths (verify/lookup/rename/
  lbdir/collect) copied verbatim from the handoff PIPE_GLYPHS; glyph scales to round(size*0.56).
Added: gui_next/src/renderer/src/index.css: appended the .pipe-tile* visual + animation rules
  verbatim from the handoff CSS — radial-gradient fill, bevel/lift box-shadows, status modifiers,
  and the pipeRing/pipeSheen Pulse keyframes wrapped in @media (prefers-reduced-motion:
  no-preference). Derived shades (hi/lo/shadow/glow) computed via color-mix(in oklab,…) off a
  single --pipe-mid per status.
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageNode now renders a
  PipelineIcon tile instead of the old 22px circle (check/x/!/spinner/number), so both the
  per-row StageTracker (queue table) and the full-width StageStepper (detail view) in
  ScreenPipeline show the new tiles. Added STAGE_TO_TILE / STATE_TO_TILE maps (tracker 'file'
  stage → 'collect'; 'mute' state → 'pending'); StageNode gained an optional `size` (default 24)
  and `n` is now unused (kept for API compatibility). The `current` accent ring is preserved as
  an outer box-shadow; running stages now Pulse rather than spin. StageTracker (queue-table row)
  tiles bumped 25% (24→30px), left-aligned with fixed-width connectors and 14px/24px padding so the
  Pulse rings (which expand ~22px past each tile) have room on all sides instead of clipping at the
  column edges; ScreenPipeline.tsx Stages column widened 232→340px, which pulls the icon block
  left. Folder column is the flexible remainder again (~comfortably wide) with word-wrap
  (whiteSpace:normal + overflowWrap:anywhere) so the occasional long folder name wraps instead of
  ellipsis; the right cluster (Stages 340 / Status 420 / LB# 104 / actions 160) is now fixed-width
  and right-anchored, pinning the LB# column to the right edge (a brief earlier pass left actions
  flexible, which pushed LB# inward with a large right gap). Icons column horizontal padding raised
  +50% (24→36px) for extra breathing room on both sides. Status-cell pills constrained to 50%
  width (they were being stretched full-column by the flex-column's default align-items:stretch)
  and centered in the column (container alignItems:center; pill justifyContent:center) so each pill
  sits with equal padding on both sides; the LB# column text is now centered (TD/TH align:center)
  rather than left-justified. Stages and Status column headers also centered (TH align:center) so
  they sit visually over the icon cluster / centered pills. Column widths unchanged. Added light
  vertical column-divider lines to the queue table (index.css .pipe-queue-table cell border-right,
  color-mix 60% of --lbb-border; wrapper div tagged className="pipe-queue-table") — scoped to this
  table only (not the shared TD/TH primitives), skipping the edge-bar and last columns and the
  full-width group-header rows. Centered the select checkboxes (header TH + per-row TD align:center)
  in the left checkbox column.

[2026-06-20] — fix(gui): DeepL i18n sweep — fill all missing/still-English locale strings
Fixed: scripts/deepl_translate_gui_next.py: two bugs that left whole sections untranslated.
  (1) set_leaf() walked into intermediate keys without creating them, so any en.json key whose
  parent subtree was absent from a locale raised KeyError and aborted the run — now uses
  setdefault to create missing parents. (2) The to_translate selection only re-sent keys that
  were present-but-still-English; keys missing entirely from a locale were silently skipped
  (contradicting the skill's documented "missing keys are picked up on the next run"). Added a
  `missing = path not in target_leaves` branch so absent keys are translated too.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ran the fixed script — filled
  ~70 keys per locale that were never propagated (the entire `archiveOrg` upload screen, plus
  `setup.purges`, `rename.disambiguate`, `pipeline.autoRun*`, `lookup.owned.*`) and re-translated
  the remaining still-English strings. All five locales now have 0 keys missing vs en.json;
  residual still-English values are benign (abbreviations LB#/MD5/FFP/ST5, proper nouns
  Pipeline/Bootlegs/qBittorrent, language endonyms Deutsch/Italiano, {{var}}-only strings).
Changed: .claude/settings.local.json: updated the stored DEEPL_API_KEY (the previous one was
  disabled and rejected by DeepL with an authorization failure). DeepL chars used this session: ~13k.

[2026-06-20] — docs(gui+docs): TODO-150 handoff-vs-code gap sweep — theme i18n + doc 07 reconcile
Fixed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: the phase-2 Themes additions
  (Frame theme / Card style controls) shipped with `themes.palette` and `themes.cardStyle` keys in
  en.json only, so ScreenThemes rendered English fallback strings in the other 5 languages —
  violating the "all 6 locales together" rule. Added translated palette/cardStyle blocks to all
  five; all locales now match en's themes keyset exactly.
Changed: instructions/design_handoff_unified_library/07-tapematch-backend-integration.md: reconciled
  the spec with shipped behavior — doc still claimed "singletons are excluded (member_count >= 2
  only)" but tapematch_sync.py syncs them as label='Solo' (per CHANGELOG 2026-06-19). Updated §1,
  the sync step (§2.3), and the verification note to describe the as-shipped Solo behavior.

[2026-06-19] — fix(gui): BUG-215 blank family names in Unified Library performance detail panel
Fixed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: FamilyCard and FamilyMeter
  read fam.label, but the FamilyGroup objects passed from ScreenLibrary carry tmLabel (the field
  was renamed when the source pill replaced the inline source label). The PerfFamily interface
  still declared label, and the call site cast families with `as any`, so the mismatch compiled
  silently and every family card/meter tooltip rendered an empty name. Aligned PerfFamily with
  FamilyGroup (label → tmLabel, dropped unused dupes; famConf widened to number | null) and now
  render `tmLabel ?? src ?? 'Recording'`.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: dropped the `families={... as any}`
  cast on PerformanceDetailPanel so TypeScript verifies the shape and catches future drift.

[2026-06-19] — fix(backend): BUG-212 pin survives folder rename in pipeline
Fixed: backend/app.py: folder_rename() — after physically renaming the folder, the sticky
  "Pin & continue" link in folder_lb_link was left keyed to the old path. The next pipeline
  run (e.g. the file-step refresh that fires right after a rename) re-resolved lookup against
  the new path, found no pin, fell back to the raw "Incomplete match" checksum result, and
  cleared lb_number — leaving the File action unavailable until the user re-pinned manually.
Added: backend/db.py: rekey_folder_link(old_path, new_path) — moves folder_lb_link row(s) from
  old_path to new_path (UPDATE OR IGNORE + cleanup of any row left behind by a PK conflict).
  Wired into folder_rename()'s existing BUG-206 my_collection-sync block.
Added: tests/test_db_writes.py: TestFolderLink gained 4 cases covering rekey_folder_link
  (single link, multi-LB links, PK-conflict cleanup, no-op on nonexistent old path).

[2026-06-19] — refactor(gui): remove dup badges from Unified Library performance lens grouped view
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView family-header row no longer shows the "{N} dup" count Pill, and member rows no longer show the per-recording "dup" Pill — user found them unhelpful. Dropped the now-unused FamilyGroup.dupes field. The flat library list's Dup/Xref column and the DetailPanel's "dup" status pill are unchanged.

[2026-06-19] — refactor(gui): remove acoustic fingerprint references from Unified Library UI
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: dropped the FP column/header from the recording-lens table, the "No FP" health filter, the fp field on RecordingRow, the fpMap prefetch merge, and the onRefp/"Re-fingerprint" context-menu handler — the fingerprint feature is being deprecated.
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: removed the Fingerprint row from the owned-recording metadata card and the "fingerprinted"/"no fingerprint" line from family member rows; dropped fp from DetailRow and PerfRecording.
Changed: gui_next/src/renderer/src/components/library/actions.tsx: removed the onRefp handler and 'refp' (Re-fingerprint) action from the shared Library action registry.
Note: ScreenCollection.tsx and the dedicated Fingerprint screen/backend routes are out of scope — they still reference fingerprinting.

[2026-06-19] — feat(gui): add Expand all / Collapse all toggle to Unified Library performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView filter bar gains an "Expand all"/"Collapse all" button next to the Rating filter — toggles expandedShows for every multi-recording show plus clears collapsedFams in one click, instead of clicking each show's chevron individually; disabled when there are no multi-recording shows to expand

[2026-06-19] — fix(gui): BUG-214 separate source-type label from TapeMatch match-group badge
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: FamilyGroup.label was `famLabel || sourceType`, conflating TapeMatch's match-group name ("Solo"/"Family A"/"Family B") with the tape's source type ("Audience"/"Soundboard"/etc.) in one bold text slot — sibling rows from the same source could show either string with no visual cue they're different dimensions. label now always reflects source type; the TapeMatch name moved to a new tmLabel field rendered as its own info-toned Pill badge with a tooltip.
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: follow-up to the above — the spelled-out source label ("Audience") was then 100% redundant with the existing AUD/SBD source pill since both derived from the same fam.src. Removed FamilyGroup.label and its rendered span; the source pill is now the sole on-screen indicator of source type at the family-row level.

[2026-06-19] — feat(gui): add Year filter to Unified Library performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView filter bar gains a "Year" dropdown next to "Decade" — activeYear state, facetCounts.yearC, filteredPerfs predicate, clearAll/filterChips/perfActiveCount all wired the same way as the existing Decade filter, just keyed on the exact show year instead of the decade bucket

[2026-06-19] — feat(gui): default Unified Library views hide Private/Missing entries (TODO-154)
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: recording lens filteredRows — when no Status filter chip is active (the default), rows with status Private or Missing are now excluded; selecting the Status chip (including Private/Missing themselves) still overrides this and shows exactly the selected statuses, same as any other filter chip
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: performance lens performances memo — recordings with status Private/Missing are now dropped from each show's recordings array before family grouping/coverage rollup, unconditionally (no per-recording Status filter exists in that lens, so there's no chip to opt back in with). Shrinks family/coverage counts accordingly (e.g. "3 of 4 families" becomes "3 of 3" if the 4th member was private); a show whose only recordings were private/missing now rolls up as coverage='Undocumented' instead of showing hidden entries

[2026-06-19] — feat(gui+backend): add ALD (Assisted Listening Device) as a 6th source_type value (TODO-153)
Added: backend/db.py: _SRC_ALD_RE matches \bald\b (case-insensitive); checked first in _classify_source_text(), ahead of Soundboard, since descriptions that mention both (e.g. "Digitally Remastered Soundboard, (assisted listening device (ALD) is the source)") are clarifying the true source, not offering two guesses
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx and gui_next/src/renderer/src/components/library/DetailPanel.tsx: SRC_ABBR/SOURCE_FULL/SRC_HUE maps now include ALD ('ALD' badge, label 'Assisted Listening Device', --lbb-bad-fg hue to stay visually distinct from the other 5)
Changed: data/losslessbob.db: re-tagged the 37 entries whose description names ALD explicitly with source_type='ALD', overriding whatever the earlier bulk passes had swept them into (21 had become Audience, 13 Soundboard, 3 Mixed); backed up DB first

[2026-06-19] — chore(db): bulk-persisted classify_source_type() guesses into entries.source_type (TODO-153)
Changed: data/losslessbob.db: entries.source_type was added at schema v8 as a curator-only field, deliberately "never heuristically backfilled" (see comment at backend/db.py:1078-1082) — at user's explicit request, reversed that for this session: ran classify_source_type() over all rows where source_type was NULL and persisted the result for every confident hit. 3,805 rows updated (Audience 3160, Soundboard 579, Mixed 34, FM/Pre-FM 32); the other ~12,825 rows with no confident keyword signal are untouched and remain NULL.
Changed: data/losslessbob.db: per tape-trading convention (audience is the unstated default for live recordings; soundboard/FM/mixed get called out explicitly because they're notable) — second pass defaults source_type='Audience' for the remaining still-NULL rows where lb_category IN ('concert','unknown') AND description is non-empty (10,972 rows). Deliberately excludes the 408 non-concert rows (studio/tv/interview/compilation/rehearsal/radio/soundcheck — audience-default doesn't fit a TV/radio broadcast or studio session) and the 1,445 rows with a completely empty description (zero text to default from). entries.source_type is now populated for 14,777/16,630 rows (88.8%); 1,853 remain NULL.
Added: data/backups/losslessbob_2026-06-19_194959_780578_source_type_backfill.db and data/backups/losslessbob_2026-06-19_195814_210904_source_type_audience_default.db: pre-write snapshots via backup_database() for both bulk passes, in case either needs to be reverted.

[2026-06-19] — fix(gui): BUG-214 ungrouped recording rows in performance lens now select into DetailPanel
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: fam row onClick called setSelectedId
  (the parent performance) for every family row, including single-member (non-TapeMatch-grouped)
  rows; only true multi-member "member" sub-rows had a click handler that selected the recording
  itself, so clicking an ungrouped recording silently did nothing to the panel. Single fam rows
  now call setSelectedMemberLb(lone.lbNumber), matching member-row behavior, and get the same
  selected-row highlight.

[2026-06-19] — feat(backend): display-only source-type classifier fills SourceBadge gap (TODO-153)
Added: backend/db.py: classify_source_type()/_classify_source_text() — conservative keyword classifier (Soundboard/FM-Pre-FM/Mixed/Audience) over entries.source_chain (preferred, already label-extracted) falling back to raw description; deliberately excludes "Master" (too ambiguous — usually means tape generation, not source type, in trader lineage text); excludes vinyl "Matrix: BDGD"-style runout codes via negative lookahead so they don't get misread as a SBD+AUD matrix mixdown
Fixed: backend/db.py: search_entries() and get_performances() now fall back to classify_source_type() display-only when entries.source_type (curator-edited, NULL for all 16,630 rows) is empty — fixes SourceBadge in the Unified Library performance detail panel always rendering blank; classifies ~3,805/16,630 entries (Audience 3160, Soundboard 579, Mixed 34, FM/Pre-FM 32), never written back to the DB column
Changed: backend/db.py: get_performances() SELECT now also pulls e.description, e.source_chain to feed the classifier

[2026-06-19] — fix(backend): Unified Library date sort now numeric YYYY-MM-DD instead of M/D/YY string
Fixed: backend/db.py: get_unified_library_performances returned "date" as raw M/D/YY date_str; localeCompare on that sorted Oct 2 after Oct 19; now returns ISO date (YYYY-MM-DD) when available so lexicographic sort is chronologically correct

[2026-06-19] — fix(backend): sync TapeMatch singletons as "Solo" to eliminate orphan Recording rows in Library
Fixed: backend/tapematch_sync.py: recordings TapeMatch processed but found no acoustic match were silently dropped by the >= 2 singleton filter; now synced into recording_families / tapematch_family_meta with label='Solo', by='ai' so they render as "Solo LB-XXXXX" in the performance lens instead of the confusing fallback "Recording LB-XXXXX"

[2026-06-19] — feat(gui): PerformanceDetailPanel full rewrite to match prototype perf-parts.jsx
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: complete rewrite of PerformanceDetailPanel; now matches prototype anatomy — DOW badge + CoverageChip identity row → 24px/800-weight date → 14px venue → 12.5px city → 11.5px tour → italic title → ActionBar → weighted FamilyMeter coverage card (with dupe count, upgrade warning, best owned rating) → 3-col Fact cards (Families/Setlist/Length) → RECORDING FAMILIES section with FamilyCard[] (SourceBadge + family label + MatchChip confidence chip + per-member MemberRow with owned/wish/dup pills + fingerprint status) → lazy Setlist from /api/bobdylan/show?date= → AssetStrip scoped to canonical → ShareSeed for owned recordings
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: new subcomponents — CoverageChip, SourceBadge, MatchChip, FamilyMeter, FamilyCard, MemberRow, Setlist, Fact; new PerfFamily and PerfRecording exported interfaces
Added: gui_next/src/renderer/src/components/Icon.tsx: tapematch icon (tape/waveform shape for TapeMatch AI grouping UI)
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceDetailPanel call site now passes families={familiesOf(perf.recordings)}

[2026-06-19] — fix(gui): Library filter bar — FilterMenu styling, Views menu, empty Source fix
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: FilterMenu button height 30→28, borderRadius 7→6, inactive fontWeight 550→500, inactive color lbb-fg→lbb-fg2 to match prototype lbb-ui.jsx spec
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: "Recordings" filter label renamed to "Source"; Source filter in both lenses conditionally rendered only when source_type data exists (currently always NULL in DB, so the empty dropdown is hidden rather than showing a broken menu)
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: PerformanceLensView now has a Views preset menu (All performances / My collection / Coverage gaps / Wishlist / Duplicates) matching the prototype libu-performance.jsx ViewsMenu; wired to perfView state that applies additional post-facet filtering; clearAll resets perfView; active view shows as chip in summary strip

[2026-06-18] — fix(backend): Library performance lens — shows with varying location strings now group correctly
Fixed: backend/db.py: get_performances() was keying show groups on (date_str, location); recordings for the same concert date with different raw location strings (e.g. "Munich" vs "Munich, West Germany") produced multiple duplicate show rows for the same date. Changed primary grouping key to the resolved ISO date when available — Bob Dylan does not play two venues on the same calendar day, so ISO date alone is the correct deduplication unit. Fallback to raw date_str::location for entries with unresolvable dates (unchanged). Also improved city display: prefers dylan_performances.city over raw entries.location when bobdylan_shows has no match.

[2026-06-18] — feat(gui): Unified Library — detail panel structural fix + performance family auto-expand
Changed: gui_next/src/renderer/src/components/library/DetailPanel.tsx: rewritten to match prototype panel anatomy — aside container now uses --sep-detail-bg/border/radius/shadow token cascade; width 380 (recording) / 400 (performance); proper header with DETAILS label + Open LB page button + chevRight collapse; scrollable inner div; collapsed-to-40px stub state with info icon; recording panel content restructured (owned-dot pills at top, 16px LB# identity, file metadata grid, catalog note for unowned); performance panel accepts nullable perf with empty-state message; both panels accept open/onToggle props
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: added detailPanelOpen state to both recording lens and PerformanceLensView; panels always mounted (collapse to 40px instead of being removed); added useEffect auto-expand of first multi-recording show when performance data loads (mirrors prototype which pre-expands one show so family groups are visible by default)

[2026-06-18] — feat(gui): Unified Library — replace left facet rail with top filter bar per 06-pixel-spec.md
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: removed filterPaneOpen state + <aside> facet rail from both lenses; added FilterMenu, MenuLabel, ViewToggle, ScopeControl components; restructured recording lens and PerformanceLensView to 3-bar header stack (toolbar / filter bar / summary strip) with --sep-* CSS tokens; recording lens colgroup updated to 11-col spec (3·34·92·88·88·auto·54·auto·60·52·52 for all/unowned, 3·34·92·88·88·auto·54·250·180·90·44 for owned); performance lens colgroup updated to 10-col spec (3·30·32·116·auto·210·132·56·56·150); BulkActionBar moved to position:absolute float inside table region; ViewToggle moved into each lens toolbar (no longer a separate bar); GroupRow colSpan updated to match new col counts (colCount-1)

[2026-06-18] — fix(backend): make the ruff pre-commit hook cross-platform
Fixed: .pre-commit-config.yaml: entry hardcoded an absolute Windows path to ruff.exe (set in a
  prior Windows session), which failed every commit on Linux. Switched the hook from
  `language: system` (relies on a hardcoded interpreter path) to `language: python` with
  `additional_dependencies: ["ruff==0.15.16"]` — pre-commit now manages its own isolated venv
  for the hook on whichever OS runs `git commit`, so no machine-specific path is needed.
Fixed: backend/app.py: two ruff-flagged unsorted import blocks (geocoder/integrity_monitor
  imports in _running_jobs_summary, folder_naming imports in _pipeline_process_folder),
  auto-fixed via `ruff check --fix`.

[2026-06-18] — fix(gui): collection "Send to →" now sends all checked rows to pipeline/verify/etc
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: handleCtxSendTo used single row.diskPath; now uses getCtxRows to collect all checked rows' paths into the folder queue. Disabled state updated to match.

[2026-06-18] — feat(gui): collection view right-click "Select All Visible"
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: context menu item at top that adds all currently filtered+sorted rows to checkedIds

[2026-06-18] — fix(backend): TODO-151 follow-up — root-cause the guest-spot/NET classification gap
Changed: backend/db.py: `_PERF_CATEGORY_MAP` gained `GUEST -> concert`, `NET -> concert`,
  `SIDEMAN -> studio`. Root cause of the prior degraded-row workaround: `dylan_performances`
  (already imported, 5127 rows) tags guest appearances at other artists' shows as `GUEST`
  (66 rows) and Never Ending Tour-era shows as `NET` (3433 rows — not "internet"), but neither
  code was in the category map, so classify_entry_categories() silently dropped them to tier-3
  keyword matching or 'unknown' instead of tier-2 `dylan_performances` matching. `SIDEMAN`
  (38 rows, backing-musician studio sessions) was unmapped too.
Changed: backend/db.py: bumped the one-time classification backfill meta key from
  `lb_category_backfill_v1` to `_v2` so existing installs reclassify automatically on next
  launch (verified via a real backend restart, not a raw DB edit): concert 14092->14329
  (+237), unknown 2043->1811 (-232), studio 96->101 (+5).
Changed: backend/db.py: get_performances() now falls back to `dylan_performances.venue` when
  `bobdylan_shows` has no row for a show's date (true for nearly all GUEST dates) — e.g. the
  1986-02-19 Melbourne show now reports "Melbourne Sports And Entertainment Centre" instead of
  just the entry's raw location text.
Note: the prior session's `confirmed: false` degraded-row fallback (TODO-151, below) stays in
  place for whatever this still doesn't cover — it now only fires for ~19 shows instead of 198
  (mostly category `FILM`, e.g. the 1986 Bristol Colston Hall "Hearts of Fire" filming, plus a
  few TV-awards/White-House/studio-session dates with no clean mapping). FILM stays unmapped —
  some FILM rows are non-performance B-roll (hotel rooms, a gas station), not shows.

[2026-06-18] — fix(backend+gui): TODO-151 — performance lens recovers misclassified shows
Changed: backend/db.py: get_performances() now also includes lb_category='unknown' entries
  that have a fully-specified date (no 'xx' placeholder) and a non-blank location, grouping
  them the same way as 'concert' entries but flagging the show `confirmed: False`. Audit of
  the live DB found 252 such 'unknown' rows (of 2043 total); spot-checking ~40 showed most
  are real performances bobdylan_shows doesn't track (guest appearances at other artists'
  shows — Dire Straits, U2, Tom Petty, Grateful Dead, Springsteen, Clapton — plus a few
  legitimate Dylan dates missing from bobdylan_shows, e.g. 1986-09-19 Bristol Colston Hall).
  Recovers 198 shows previously invisible in the performance lens. The other 1791 'unknown'
  rows (no date or only an 'xx' date) have no reliable grouping signal and stay excluded.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx, components/library/DetailPanel.tsx:
  PerformanceRow gained an optional `confirmed` field; show rows and the performance detail
  panel render an "Unconfirmed" pill (tooltip explains it's inferred from the recording's own
  date/location, not a matched show) when `confirmed === false`.
Closed: TODO-151 (was Open in TODO.md, moved to TODO_DONE.md).

[2026-06-18] — feat(gui+backend): TODO-150 step-7 follow-up — wire the m3u performance action
Changed: backend/app.py: GET /api/collection/export/m3u accepts an optional `lb_numbers`
  comma-separated query param to restrict the export to specific LB numbers; returns
  `show.m3u` when filtered (vs `collection.m3u` for the full export). Verified against the
  live backend: full export unchanged, `?lb_numbers=1` produces a correct 2-track playlist,
  non-matching/junk LB numbers degrade to an empty-but-valid `#EXTM3U` file rather than erroring.
Added: gui_next/src/renderer/src/components/library/actions.tsx: `onM3u` to `ActionHandlers`
  and the `m3u` action (Export show as M3U) to `buildPerformanceActions()`, operating on the
  show's owned recordings — this was deferred at step 7 pending the backend filter above.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: added a local `blobDownload()`
  helper (same pattern as ScreenCollection.tsx/ScreenTrading.tsx) and an `onM3u` handler.
  `sources`/`notify` action ids and the TapeMatch family `note` field remain unexposed —
  there's no "find sources"/notification system or family-note write path anywhere in the
  app to wire them to; building either would be a new feature, not a loose end of this ticket.
Note: i18n (TODO-150 step 10, in-screen Library strings) is deferred per user decision —
  English-only is acceptable for now.

[2026-06-18] — feat(gui): TODO-150 phase 9 — Library screen/route/nav wiring
Changed: gui_next/src/renderer/src/App.tsx: replaced the temporary, nav-hidden `/library-dev`
  route with the real `/library` route.
Changed: gui_next/src/renderer/src/components/AppShell.tsx: `NAV_GROUPS`'s Library group gained
  a new item (`{ id: 'library', label: 'Library', icon: 'library', featured: true }`) above
  "My Collection", per instructions/design_handoff_unified_library/05-integration.md's nav
  placement spec — picks up the existing featured "NEW" badge for free. No i18n work needed:
  `appShell.nav.library` already existed in all 6 locales (previously only used for the group
  header, which reads the same word). `tsc --noEmit` and `npm run build` both pass.
  Build order step (9) of TODO-150 is done; step (10) (i18n for in-screen Library strings)
  remains.

[2026-06-18] — feat(gui): TODO-150 phase 8 — Library detail-panel zones
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: `RecordingDetailPanel`
  and `PerformanceDetailPanel`, zoned per instructions/design_handoff_unified_library/
  02-action-system-parity.md — header, `ActionBar` (primary + Reveal + grouped "More" using
  the step-7 action registry/menu), `ShareSeed` (status line + qBittorrent/torrent/forum
  actions + a unified date-sorted activity log merged client-side from the existing
  `/api/collection/prefetch` torrents/forum_posts arrays), `AssetStrip` (attachments/
  spectrograms/map as state chips, spectrogram readiness checked lazily via the existing
  `/api/spectrogram/list`), and an optional Setlist line for the performance panel.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: both lenses now render the
  detail panel as a third column on row selection. Recording lens activates the
  already-existing but previously-unused `selectedLb` state; performance lens adds
  `selectedMemberLb` next to the existing `selectedId` (member-row selection takes
  precedence). Added a bulk `/api/attachments/cached` query and a `historyMap`/
  `attachCountMap` built from `prefetch`, shared by both lenses.

[2026-06-18] — fix(backend): TODO-150 — performance lens excludes non-concert recordings
Changed: backend/db.py: get_performances() now filters its source query to
  `lb_category = 'concert'` so radio/tv/interview/studio/rehearsal/soundcheck/
  compilation/other/unknown recordings no longer get grouped into bare, misleading
  show rows in the Library performance lens; they remain visible via the recording
  lens. Added TODO-151 to audit lb_category classification accuracy now that it gates
  lens membership rather than just a cosmetic badge.

[2026-06-18] — feat(gui): TODO-150 phase 7 — Library shared action registry + bulk bar
Added: gui_next/src/renderer/src/components/library/actions.tsx: the shared Library action
  registry per instructions/design_handoff_unified_library/02-action-system-parity.md — `LibAction`
  vocabulary grouped into open/listen/acquire/share/assets/maintain, `buildRecordingActions()`
  and `buildPerformanceActions()`, a grouped fixed-position `ActionMenu` + `useActionMenu()`
  hook, and `BulkActionBar`.
Added: gui_next/src/renderer/src/components/primitives.tsx: `Toast` and `ConfirmDialog`,
  ported from ScreenCollection.tsx's local copies so other screens can reuse them; exported
  from components/index.ts.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: wired the action registry into
  both lenses. Recording lens gained a checkbox column + `BulkActionBar` (Create torrent / Add
  to qBittorrent / Update location / Remove, batched over the checked set) and a right-click
  context menu; performance lens show rows and member rows now open the matching grouped menu.
  All action handlers call the same backend endpoints ScreenCollection.tsx already uses
  (qbt/add, torrent/create, preview_forum+post_forum, collection PATCH/DELETE, wishlist,
  fingerprint/build, spectrogram/generate, open/vlc, window.api.openPath/pickDir) — no backend
  changes this step. `sources`/`notify`/performance-row `m3u` action ids are omitted (no
  existing backend/UI to wire them to) rather than shipped inert.
  Build order step (7) of TODO-150 is done; steps (8)-(10) (detail-panel zones, screen/route/
  nav, i18n) remain.

[2026-06-18] — feat(gui): TODO-150 phase 6 — Library screen performance lens
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: "By performance | By recording"
  segmented toggle (defaults to performance). New `PerformanceLensView` component fetches
  `/api/library/performances` + `/api/tapematch/families`, merging family data into the same
  `RecordingRow` objects the recording lens already built from `/api/search` +
  `/api/collection/prefetch` (by reference, keyed by `lbNumber`) — both lenses always agree on
  a recording's owned/wish/dup/fp state, no second merge implementation. Ported the design
  handoff's `families()`/`rollup()` reference helpers (`_source/perf-data.js`) into TS as
  `familiesOf()`/`rollupOf()`: clusters recordings by `fam` (or by `lb` for ungrouped ones),
  computes per-show coverage (Covered/Upgrade/Gap/Undocumented). Ungrouped recordings become
  singleton families, so the no-families fallback (03-data-contract.md) falls out of the same
  code path with no special-casing. Year-grouped virtualized table with show → family → member
  expand/collapse, own facet rail (decade/coverage/source-available/best-rating). Deliberately
  bare per the step-4 precedent: no detail panel, no bulk bar, no context menu (steps 7/8); the
  family `note` field is omitted since `/api/tapematch/families` doesn't expose it and extending
  that endpoint is out of scope here.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: hoisted `RATING_RANK` and added
  `SOURCE_FULL` to module scope (was recording-lens-local) so the new performance lens can share
  them; extended `RecordingRow` with optional `fam`/`famLabel`/`famConf`/`famBy` fields, set only
  by the performance lens's adapter.

[2026-06-18] — feat(backend): TODO-150 phase 5 — performance/show grouping aggregate endpoint
Added: backend/db.py: `get_performances()` groups `entries` by raw `(date_str, location)` into
  shows, cross-referencing `bobdylan_shows` (venue, setlist key, track count via `bobdylan_setlist`),
  `setlistfm_shows` (tour name), and `bootleg_titles` (release title) — none of which `/api/search`
  exposes. Per the locked TODO-150 decision this is a dedicated backend endpoint, not a client-side
  groupBy over `/api/search` results (06-gap-analysis.md §B3 open decision 1) and not a join bolted
  onto `/api/search` (same reasoning as the TapeMatch families endpoint, 07 §4). Optional fields
  (`dow`, `tour`, `setlist`, `tracks`, `title`) are omitted, never null-faked, when no source data
  exists for a show. Verified against a migrated copy of the live dev DB: 16,630 entries → 10,718
  shows in ~150ms.
Added: backend/app.py: `GET /api/library/performances` — new route, returns `get_performances()`.
  TapeMatch family data deliberately not joined in; the GUI's future performance-lens adapter
  fetches `/api/tapematch/families` separately and merges by `lb_number`, same pattern the
  recording lens already uses for `/api/collection/prefetch`.

[2026-06-18] — feat(gui): TODO-150 phase 4 — Library screen recording lens (no-families fallback)
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: new flat, LB#-keyed table over the
  full catalog — toolbar (search, group-by-year toggle), left facet rail (scope, decade, status,
  rating, source, a derived "health" group for wishlist/duplicates/unconfirmed/no-fingerprint),
  summary strip (live result/owned counts), virtualized year-grouped table. Client-side adapter
  merges the existing `/api/search` catalog with `/api/collection/prefetch` (collection,
  fingerprints, wishlist, duplicates, xref_lb_numbers) — no backend changes. This is also the
  literal no-families fallback row the performance lens (TODO-150 step 6) will reuse. Deliberately
  bare this step: no context menu, no detail panel, no bulk action bar — those are TODO-150 steps
  7/8, scoped separately to avoid building throwaway versions now. Owned-row file-card fields
  (size/files/format/cds) and the design doc's "New" status value are omitted — nothing in the
  backend computes them today and the project doesn't ship placeholder data.
Changed: gui_next/src/renderer/src/App.tsx: registered `/library-dev` as a temporary, nav-hidden
  route (same pattern as the existing `/quicklookup`) so the new screen is reachable during
  development; real nav/route wiring is TODO-150 step 9.

[2026-06-18] — feat(backend): TODO-150 phase 3 — curator-edited entries.source_type column
Added: backend/db.py: new `entries.source_type` column (schema v8, MASTER_SCHEMA_VERSION 7→8)
  for the Library design doc's `src` field (Soundboard/Audience/FM-Pre-FM/Master/Mixed →
  SBD/AUD/FM/MST/MTX badge). Unlike `taper_name`/`source_chain`/`lb_category`, this column is
  never heuristically parsed or backfilled — it stays NULL until a curator sets it via the
  (not-yet-built) detail-panel editor. Migration follows the existing `ALTER TABLE ... ADD
  COLUMN` idiom in `init_db()`. Wired into the existing read paths that already surface
  `lb_category` (`search_entries()`, `get_entries_by_lb_list()`, `get_collection()`) so it's
  available to Search/Collection/Library without a separate fetch.

[2026-06-18] — feat(gui): TODO-150 phase 2 — theme engine additions (frame theme + card style)
Added: gui_next/src/renderer/src/lib/tokens.ts: new `palette` (frame theme: slate/blue/purple/
  green/graphite, tints bg/surface/border/fg over the mode, layered like the existing accent
  system) and `cardStyle` ('framed' | 'flat', default 'flat' — preserves current look) fields on
  ThemeOptions. `PALETTES` table ported verbatim from the design handoff's `_source/lbb-tokens.js`.
Fixed: gui_next/src/renderer/src/lib/tokens.ts: `Mode` now properly includes 'system' as a type
  (previously only reachable via an `as ThemeOptions['mode']` cast in ScreenThemes.tsx that
  silently fell back to light on every reload). `applyTheme()` resolves 'system' to a concrete
  light/dark via `getSystemMode()` before indexing MODES/PALETTES/ACCENT_PALETTES/STATUS, and
  `loadTheme()` now validates 'system' as a legal stored value instead of dropping it.
Added: gui_next/src/renderer/src/index.css: ported the `--sep-*` framed-card CSS token block
  from the design handoff's `app.css` (gutter/card/ring/lift/top-highlight, per-mode shadow
  overrides), adapted from the handoff's nonexistent `#frame` element to `:root` since
  applyTheme() already sets data-mode/data-sep on document.documentElement. Inert until
  data-sep="framed" is set — no existing screen reads these tokens yet.
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: added "Frame theme" (palette
  swatches, with a "Default" tile to opt out / keep current look) and "Card style" (framed/flat
  segmented control) cards to the Themes panel. Fixed handleImportTheme() to round-trip the new
  palette/cardStyle fields instead of silently dropping them on import.
Note: i18n for the two new themes.palette.*/themes.cardStyle.* keys deferred to de/fr/es/it/nl —
  added to en.json only for now; other locales fall back to English until the Library screen
  (TODO-150 build order steps 3-9) is further along.

[2026-06-18] — feat(backend): TODO-150 phase 1 — TapeMatch backend integration
Added: backend/db.py: recording_families + tapematch_family_meta tables (SCHEMA_SQL), added to
  MASTER_TABLES, MASTER_SCHEMA_VERSION bumped 6 → 7.
Added: backend/tapematch_sync.py: sync_tapematch_families() ingests tools/tapematch/observations.db
  into the main DB — picks the best run per concert_date (highest n_sources_ran, tie-break latest
  run_id), computes a deterministic fam_id (not run-scoped), upserts both tables preserving
  label_override across re-syncs, and cleans up dissolved/changed families.
Added: backend/app.py: POST /api/tapematch/sync (manual trigger, not run at startup) and
  GET /api/tapematch/families (flat lb_number → fam_id/fam_label/fam_conf/fam_by list for
  client-side merge).
Fixed: backend/db.py: import_master_db() now checks each MASTER_TABLES table exists in the
  attached incoming DB before DELETE+INSERT, skipping (not erroring on) tables absent from an
  older pre-feature snapshot; skipped tables are reported in the returned skipped_tables list.
Added: backend/tapematch_sync.py: `__main__` CLI entry point (`.venv/bin/python3 -m
  backend.tapematch_sync`) — runs the sync standalone without the Flask backend, since tapematch
  batch runs happen via shell scripts that don't have the app server up. Wired as step 7 of the
  `/tapematch-batch` skill (`.claude/commands/tapematch-batch.md`) per doc 07 §3 — the manual
  trigger point for getting a finished batch's families into the main DB.

[2026-06-18] — fix(tools): BUG-209 — tapematch run_crawl.sh infinite loop on missing-sources date
Fixed: tools/tapematch/tapematch_session.py: run_date() now archives a **missing_sources**
  report.md (mirrors the existing insufficient_sources/rc=2 path) instead of returning rc=3
  with nothing recorded, so next_run()'s --next loop stops re-picking the same unrunnable date
  forever. Delete the run's archive dir under data/tapematch/runs/ to retry once the missing
  source(s) appear on disk.
Changed: tools/tapematch/gen_analysis.py: parse_report/build_analysis/status-line now recognize
  the missing_sources marker, same treatment as insufficient_sources.
Added: tools/tapematch/tests/test_missing_sources.py: regression coverage for the new marker.

[2026-06-18] — feat(backend+gui): multi-LB pipeline — same recording under two archive entries
Added: backend/db.py: folder_lb_link migrated to composite PRIMARY KEY (folder_path, lb_number); added
  get_folder_links() returning all links per folder; set_folder_link now INSERT OR IGNORE (idempotent).
Added: backend/folder_naming.py: build_multi_lb_name() produces compound tag e.g. (LB-16308+LB-16340).
Changed: backend/app.py: lookup step detects all-perfect multi-LB match (all lb_summary statuses
  "MATCHED"), auto-writes links for all LBs, passes lb_numbers list through; rename step builds compound
  folder name when lb_numbers > 1; true ambiguous conflict still blocks as before.
Changed: gui_next/.../ScreenPipeline.tsx: ok lookup block renders multi-LB label ("LB-16308 + LB-16340"),
  "same recording, both entries" annotation, "Multi-LB" status tag, and updated hint text.

[2026-06-17] — fix(backend): BUG-206/207 — pipeline rename leaves stale collection row and logs doubled old_path
Fixed: backend/rename.py: write_rename_log now correctly computes old_path and new_path under both
  calling conventions (folder_path = folder itself, or = parent directory); fixes old_path doubling
  (BUG-207) and pre-existing new_path miscalculation in rename_tab call site.
Fixed: backend/app.py: folder_rename() now queries my_collection after rename and updates disk_path
  + folder_name if the folder was already in the collection (BUG-206).

[2026-06-17] — fix(gui): BUG-208 — pipeline "File all" and explicit filing bypass a pending rename
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: fileableRows/selectedFileable now
  exclude rows where rename.status==='warn' && proposed is set. applyFile bails with a toast if
  rename is pending. CollectReadyDetail gains useTranslation(), a renamePending warning banner, and
  a disabled File button when a rename is outstanding. Also fixes latent crash (t undefined in
  CollectReadyDetail, introduced by BUG-204 fix). 3 i18n keys added to all 6 locale files.

[2026-06-17] — fix(gui): BUG-205 — filing duplicates visible rows and leaves running-state row in shelf section
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: shelfVis was missing !r.running guard, causing
  a row being filed (bucket='shelf', running=true) to appear in both Running and Shelf sections simultaneously.
  Also fixed counts.shelf, fileableRows, and selectedFileable to exclude running rows. Updated _pipelineCache
  on successful filing so component remount restores correct 'done' state instead of stale 'shelf' state.

[2026-06-18] — fix(backend+gui): BUG-204 — filing a folder already in collection silently dropped the new path
Fixed: backend/filer.py: after move/copy, check for existing my_collection row by lb_number;
  call update_collection() to update disk_path/folder_name if already registered, instead of
  relying on INSERT OR IGNORE which silently discarded the new path.
Fixed: backend/app.py: file-step result now includes existing_disk_path from my_collection.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: warn banner shown in Collect
  step when owned=true and existing_disk_path is set, explaining the record will be updated.
Added: all 6 locale files: pipeline.collect.alreadyInCollectionTitle/Body keys.

[2026-06-17] — feat(gui): collection text filter now searches disk path
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: added diskPath to the search predicate so typing any part of the path filters matching rows

[2026-06-17] — fix(gui): BUG-203 — shelving a pipeline folder leaves File button visible
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added `shelved` boolean flag to
  PipelineRow; Shelve sets it, Unshelve clears it and restores computed bucket. File button,
  fileableRows, selectedFileable, and counts.shelf all exclude shelved rows.
  deriveFolderStatus returns "Shelved / Deferred" when flag is set.

[2026-06-17] — fix(backend): BUG-200 — Pipeline Verify tab shows "no checksums" for disc-subfolder layouts
Fixed: backend/checksum_utils.py: verify_folder now uses rglob to find checksum files in subdirectories (disc1/, disc2/ etc.) and qualifies bare filenames with the subdir prefix so they match disk_audio_map keys

[2026-06-17] — fix(gui): pipeline Lookup action column — label, spacing, and column width
Changed: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: renamed "Open" button to "Open on LB Website"; gap between buttons 4→8px; action column 200→360px (pin) / 130→180px (non-pin)
Changed: locales/en|de|fr|es|it|nl.json: updated lookup.table.open to localised "Open on LB Website"

[2026-06-17] — fix(gui): BUG-202 — blocked folders in Pipeline sidebar and stray File button
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: QueueRow now detects
  any step with state 'blocked' and overrides the sidebar dot and label to red/"Blocked" instead
  of yellow/"Needs you"; previously all "attn" severity folders shared the same needs bucket
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: File button in the table row now
  suppressed when any upstream step (verify/lookup/lbdir/rename) has status 'bad'

[2026-06-17] — fix(tools): run_batch OOM after many in-process date runs
Fixed: tools/tapematch/tapematch_session.py: run_batch() now spawns a fresh subprocess per date (same as year_run/crawl_run) instead of calling run_date() in-process; after ~300 iterations the accumulated heap caused an OOM when tapematch tried to mmap 5 audio sources

[2026-06-17] — chore(gui): widen Pipeline table Status and actions columns
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: batch table Status column 240px→420px and actions/buttons column 128px→224px (+75% each); folder name column has no fixed width so it absorbs the difference, shifting the Stages/LB columns left

[2026-06-17] — fix(tools): BUG-199, prep_analysis_input.py misread truncated LB numbers in report.md commentary
Fixed: tools/tapematch/prep_analysis_input.py: LB_TAG_RE now excludes LB numbers immediately followed by an ellipsis ("…"/"...") so a truncated commentary snippet (e.g. "LB-4794…" cut to "LB-47…") can't be misread as a real, distinct LB number and pull in an unrelated info file, while still picking up legitimate untruncated cross-references elsewhere in report.md
Added: 5 more data/tapematch/runs/*/analysis.md write-ups (1998-06-21/23/24/25/26); repo-wide scan of all 923 run dirs for BUG-199 found 2 actually-affected dirs (1998-06-24 already correctly excluded the contamination in its analysis.md; 1990-10-26's stale analysis_input.md regenerated clean) and surfaced a second, separate bug (BUG-200, logged Open) — 1999-02-25 Portland's report.md has another session's tapematch output verbatim

[2026-06-17] — feat(tools): tapematch analysis.md backfill tooling + repeatable batch procedure
Added: tools/tapematch/prep_analysis_input.py: bundles each run's report.md with matched data/site/files/LBF-*.txt lineage prose (checksum/shntool noise stripped) into analysis_input.md
Added: tools/tapematch/ANALYSIS_WRITER_PROMPT.md: fixed spec for writing analysis.md (verdict wording rules, per-LB table/notes/callout conventions) so the procedure doesn't need re-negotiating each run
Added: .claude/commands/tapematch-batch.md: /tapematch-batch slash command — processes the next N missing analysis.md write-ups directly in-session (subagents hit a hard Write-tool block on .md files and cost about the same per file, so direct in-session writing is the reliable path)
Added: 98 of 438 missing data/tapematch/runs/*/analysis.md write-ups generated; caught several real bugs along the way — a report.md with another session's tapematch stdout spliced in (1999-02-25 Portland run), a tapematch ingest crash on a malformed duration read, and a likely date-mis-tagged LB-06939 (its own info file says 1/17/98 New London CT, catalogued under 1998-06-17 Brussels)

[2026-06-17] — fix(backend+gui): BUG-195, incomplete-match folders block downstream pipeline steps
Fixed: backend/app.py: after an incomplete checksum match (e.g. FFP matches but MD5 does not), clear lb_number so lbdir/rename/file steps stay mute unless the folder was explicitly pinned by the user
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: warn+lb_number branch now shows pin option with explanation; handlePin now re-runs all downstream steps after pinning

[2026-06-16] — feat(tapematch): single-date wrapper, decade-priority crawl mode, require-all-sources-by-default
Added: tools/tapematch/run_date.sh: shell wrapper for running a single concert date
Added: tools/tapematch/run_crawl.sh: shell wrapper for --crawl mode
Added: tools/tapematch/tapematch_session.py: get_all_dates(), _decade_priority(), _decade_label(), crawl_run() — processes all unrun dates prioritised 90s→00s→10s→20s→pre-1990, resumable
Changed: tools/tapematch/tapematch_session.py: find_lb_folders() now returns (found, excluded) so truly-missing sources can be distinguished from private/no-audio exclusions
Changed: tools/tapematch/tapematch_session.py: run_date() skips with RC=3 by default when any non-excluded source is absent from disk; --allow-missing overrides
Changed: tools/tapematch/tapematch_session.py: year_run(), crawl_run(), run_batch() propagate allow_missing and handle RC=3 as a labelled [SKIP]

[2026-06-16] — feat(backend+gui): TODO-147 — install hints for missing helper tools in Setup tab
Added: backend/sox_utils.py: get_install_hints() returns per-tool winget/brew/apt install commands for current OS
Changed: backend/app.py: /api/spectrogram/check now includes ffmpeg/sox/flac/shntool _install_hint fields
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: HelpersStrip shows install commands below yellow dots

[2026-06-16] — fix(backend+tools): BUG-187/192, bloom filter path isolation and Windows termios
Fixed: backend/db.py: BUG-187 — track _bloom_db_path alongside _bloom; lookup_checksums skips
  the bloom filter when it was built for a different db_path, preventing stale filters from one
  test's temp DB silently dropping checksums in another test's lookup.
Fixed: tools/batch_verify.py: BUG-192 — moved termios/tty to guarded try/except at module level
  (_HAS_TERMIOS flag); _KeyboardController.start/stop check the flag so the module is importable
  on Windows and pytest collection of test_batch_verify.py no longer fails.

[2026-06-16] — fix(backend+gui): bobdylan scraper intermediate messages now appear in Electron log
Fixed: backend/bobdylan_scraper.py: added _set(message=…) at sitemap index result, per-sitemap
  fetch start/failure, and scrape queue count — these only wrote to Python logger before.
Fixed: gui_next/…/ScreenScraper.tsx: moved bobdylan message→log push outside status==='running'
  gate so terminal messages (done/error) now appear; errors rendered with 'bad' tone.

[2026-06-16] — fix(gui+backend): BUG-195/196/197/198, pipeline display bugs and race conditions
Fixed: backend/app.py: BUG-196 — scan-tree shallow mode no longer adds both parent AND child
  folders when root has direct audio; store root_has_audio once and skip child iteration.
Fixed: backend/app.py: BUG-198 — folder_rename TOCTOU race: inner try/except around
  folder.rename() catches FileExistsError/OSError and returns 409 instead of 500.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: BUG-197 — auto-rename effect
  changed from forEach (all concurrent) to sequential async IIFE (for-of + await applyRename).
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: BUG-195 — added measureElement
  callback to virtualizer so actual DOM heights are used instead of fixed 38 px estimate.
Fixed: gui_next/src/renderer/src/components/table.tsx: BUG-195 — TR and GroupRow converted
  to React.forwardRef so virtualizer can measure their inner <tr> elements.

[2026-06-15] — feat(backend+gui): Bob Dylan scraper card in admin dashboard with stale-reset context
Added: backend/app.py: bobdylan_scraper.get_status() included in /api/admin/status response
Added: backend/admin.html: Bob Dylan Scraper card (status, phase label, progress bar, Start/Stop)
Added: backend/admin.html: updateBdScraperUI() / bdStart() / bdStop() JS; wired into pollStatus()
  The status message (e.g. "Discovered 2000 URLs, 0 new, 7 reset") is shown in the log line.

[2026-06-15] — fix(backend+gui): status bar now reflects all background workers (was always "Idle")
Fixed: backend/app.py: /api/activity/busy was missing site_crawler, bobdylan_scraper,
  setlistfm, and geocoder — four workers that use different status formats. Added them
  with format-aware checks (running bool vs status=="running"). Added matching i18n keys
  in all 6 locale files: crawling, bobdylan_scraping, setlistfm_syncing, geocoding.

[2026-06-15] — fix(backend): dynamic sitemap discovery so new bobdylan.com shows are found
Fixed: backend/bobdylan_scraper.py: replaced hardcoded 3-sitemap list with dynamic index
  fetch (_get_date_sitemap_urls) that reads wp-sitemap.xml and discovers all posts-date
  sitemaps; fallback to _SITEMAP_URLS_FALLBACK if index unavailable. Added 404 WARNING log
  to _fetch so silent failures are visible. Fixes BUG-193.

[2026-06-15] — fix(backend): importer empty-file error, dbedit DoS guard, datetime.utcnow deprecations
Fixed: backend/importer.py:run_import: moved close_connection(temp_db_path) and unlink() outside
  the `with get_connection() as conn:` block. Previously, calling close_connection() inside the
  with-block then returning caused sqlite3's __exit__ to call commit() on the already-closed
  connection, raising ProgrammingError instead of the intended "No checksums found" error.
Fixed: backend/app.py:dbedit_rows: added max(1,...) guard on `limit` and max(0,...) on `page`.
  Previously a caller passing limit=-1 would produce LIMIT -1 in SQLite, returning unlimited
  rows — a memory/timeout hazard on large tables.
Fixed: backend/importer.py, db.py, flat_file.py, qbittorrent.py, app.py: replaced all
  datetime.utcnow() calls with datetime.now(UTC). utcnow() is deprecated since Python 3.12
  and was generating DeprecationWarnings in every test run. Added UTC to relevant imports.

[2026-06-15] — fix(backend): db_reset now wipes all master data, not just early-era tables
Fixed: backend/app.py:db_reset: rewrote to use MASTER_TABLES as the canonical drop list instead
  of a hardcoded 6-table subset. Now clears all 19 master tables (lb_master, lb_alias,
  lb_missing, bootleg_titles, flat_file_releases/changelog, location_geocoded, etc.) and wipes
  MASTER_META_KEYS from meta while preserving all user data. Also removed the incorrect dropping
  of rename_history and torrents (USER_TABLES) that the old reset included.

[2026-06-15] — fix(backend+tests): BUG-190/191 — first Windows pytest run; fixed 2 blocking failures
Fixed: backend/importer.py:_import_flat_file: replaced init_db(temp_db_path) with a raw
  sqlite3.connect() that creates only the checksums table and closes explicitly. init_db spawns
  bloom-filter and migrate_lb_master daemon threads that hold the temp file open; on Windows
  this caused PermissionError on unlink() (BUG-191).
Fixed: tests/test_lb_master.py:test_reconcile_logs_transition: changed test LB from 7 → 11.
  LB 7 is in _LB_MISSING_SEEDS (seeded into lb_missing by init_db), so reconcile_lb_status
  always returned 'nonexistent' rather than 'private' (BUG-190).
Added: BUGS.md: BUG-192 — tools/batch_verify.py imports termios (Unix-only), blocking
  test_batch_verify.py collection on Windows.
Added: pytest installed in .venv (was missing; required for first Windows test run).
Result: 349 passed, 5 skipped, 1 known-flaky (BUG-187 bloom filter race) in 21s.

[2026-06-15] — fix(backend): BUG-189 — master data "Check for Updates" fails when latest app release has no .db asset
Fixed: backend/app.py: master_github_check / master_github_install both used /releases/latest,
  which returns the newest release by tag (e.g. v1.5.1 — an app release with no master snapshot).
  Extracted _find_master_release() helper that pages through /releases (up to 5 pages × 20) and
  returns the first release containing both a .db asset and its .manifest.json sidecar, so master
  data check/install always finds the most recent master data release regardless of app releases
  that arrive in between.

[2026-06-15] — fix(backend+gui): BUG-188 — Windows mount paths display with mixed slashes (c:\/1958/)
Fixed: backend/filer.py:normalise_path: replaced PurePosixPath(Path(raw)).as_posix() with
  Path(raw).as_posix() — on Windows the PurePosixPath wrapper received a backslash-formatted
  str, treated backslash as a literal char, and stored it unchanged in the DB.
Fixed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: added joinRoute() helper that
  strips backslashes (legacy data) and trailing slashes from root_path before joining with
  sub_path, preventing double-slash or mixed-slash display in all four path display sites.

[2026-06-15] — fix(gui+backend): BUG-167 — Scraper shows blank screen on Windows
Fixed: backend/app.py: SQLite SUM() returns NULL on an empty table; wrapped geocoded/
  failed/manual columns in COALESCE(..., 0) so /api/geocode/stats always returns integers
  even when location_geocoded is empty.
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: added (geocoded ?? 0) guard
  on the Geocoder strip-card lastDate; updated GeoStats interface to mark geocoded/failed/
  manual as number|null (accurate).
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: added ScraperErrorBoundary
  so future render crashes show an error message + "Try again" button instead of blank screen.

[2026-06-15] — chore: v1.5.1 release
Changed: gui_next/package.json, gui_next/package-lock.json: version bumped
  1.5.0 -> 1.5.1.

[2026-06-15] — test: add unit test coverage for the scraper/integration backends
Added: tests/test_scraper.py: 20 tests for backend/scraper.py — _is_soft_404,
  _extract_setlist_from_lbbcd, scrape_entry/scrape_range against local cached pages
  (parsing, attachments, soft-404 handling, force re-parse, lb_missing skip path),
  download_pages_range with mocked _fetch, and scrape status/stop helpers.
Added: tests/test_bootleg_scraper.py: 30 tests for backend/bootleg_scraper.py —
  _parse_date (year-pivot/partial-date cases), _parse_row, _diff (add/change/remove/
  dedup), _apply_diff/_record_scrape DB writes, and scrape_bootlegs with mocked
  requests.head/get (ETag no-change, successful scrape, HEAD/GET failures).
Added: tests/test_bobdylan_scraper.py: 15 tests for backend/bobdylan_scraper.py —
  fetch_sitemap_urls (mocked sitemap XML), parse_show_page, run_discover/run_scrape/
  run_update against bobdylan_shows + bobdylan_setlist with mocked _fetch, and status/
  stop/is_running helpers.
Added: tests/test_setlistfm.py: 20 tests for backend/setlistfm.py — _parse_date,
  _fetch_page (429/401/retry handling), _parse_setlist (sets/encore/cover/tape
  flattening), save_api_key/get_api_key, run_update pagination (force vs non-force,
  missing API key, stop mid-pagination) with mocked _fetch_page, and status helpers.
Added: tests/test_geocoder.py: 30 tests for backend/geocoder.py — _entry_date_to_iso,
  _get_performance_location_string, geocode_one (mocked urllib, confidence tiers,
  429 rate-limit, HTTP/generic errors), place_manual, run_batch (dry_run, limit,
  manual_override skip, retry_failed, dylan_performances structured-query path,
  429 retry/exhaustion), and get_progress.
  All 115 new tests mock requests/urllib entirely — no live HTTP calls.
Fixed: BUGS.md: documented BUG-187 (new, Open) — a pre-existing test-isolation issue
  where init_db()'s background bloom-filter rebuild thread leaks a global `_bloom`
  state across test DBs, intermittently breaking tests/test_db_lookup.py in full-suite
  runs. Reproduced on main without the new test files; not caused by this change.

[2026-06-15] — fix: BUG-168 — "Check for update" always reported "already up to date"; add download/apply flow
Fixed: gui_next/src/renderer/src/screens/ScreenHome.tsx: handleCheckUpdate read
  non-existent `data.new_release` / top-level `data.zip_filename` fields from the
  GET /api/flat_file/discover response (which actually returns `available` and
  `current_release.zip_filename`), so the condition was always falsy and the
  "up to date" toast showed even when a new release was available — including on
  a fresh install with no database loaded.
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handleCheckUpdate had the
  same field-name mismatch; fixed identically and now correctly triggers
  loadFlatReleases() when an update is available.
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: Flat file history table now
  has per-row actions — "Download" for detected/failed/deferred releases (POSTs
  /api/flat_file/download/<id>), and "Review & Apply" for downloaded releases (GETs
  /api/flat_file/diff/<id>, shows a confirm dialog with the added/changed/removed
  counts, then POSTs /api/flat_file/apply/<id> on confirm and refreshes db stats).
  Previously "Check for update" could only detect availability with no way to pull
  the file down from the GUI.
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: new
  setup.flatFile.{download,downloading,downloadDone,reviewApply,applying,
  applyConfirmTitle,applyConfirmBody,applyDone} keys (de/fr/es/it/nl pending DeepL
  translation — DEEPL_API_KEY is currently disabled, so these fall back to English).

[2026-06-15] — fix: BUG-186 — footer "Synced · idle" badge now reflects live master-sync and worker activity
Added: backend/app.py: new GET /api/activity/busy aggregates importer/scraper/
  bootleg_scraper/integrity_monitor/filer worker status plus app-update and
  data-download state into {busy, activity}.
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: StatusBar's shield badge
  always read the literal "Synced · idle". Now checks GET /api/master/github_check
  once on mount for "Synced" vs "Update available" (curator's GitHub master-data
  release, not the LB-website flat-file), and polls /api/activity/busy every 5s for
  "Idle" vs a translated activity label (Importing.../Scraping.../Filing folder.../etc).
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: new
  appShell.statusBar.{synced,updateAvailable,idle,activity.*} keys.

[2026-06-15] — fix: BUG-185 — footer status bar now shows live DB stats
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: StatusBar fetched no data and
  rendered hardcoded placeholder values (LB-16630, 704,624, 2026-05-21, 1,380). Now
  fetches GET /api/home/stats on mount and renders live latest_lb, checksum_count,
  last_import, and bootleg_count, matching the pattern already used by Sidebar/ScreenHome.

[2026-06-15] — fix: BUG-146/165/176 — date-prefix, tapematch LB-number resolution, undecodable-source resilience
Fixed: backend/torrent_maker.py: _parse_date now preserves 'xx' month/day placeholders
  as ISO-style 'YYYY-xx-xx' / 'YYYY-MM-xx' instead of returning the raw 'xx/xx/65' string
  (BUG-146), so build_standard_name no longer proposes non-standard date prefixes for
  entries with unknown month/day.
Fixed: tools/tapematch/tapematch_session.py: _lb_num_from_folder now accepts an optional
  name_to_lb map (built from found_folders) and prefers the entry's own DB-resolved LB
  number over a regex scan of the folder name (BUG-165) — fixes degenerate self-pair rows
  in observations.db.pairs for folders whose name embeds a cross-referenced LB number
  ahead of their own (e.g. "...[fixed LB-2204]-LB-10437-v"). insert_sources and
  insert_pairs now build and pass this map; insert_pairs gained a found_folders param.
Fixed: tools/tapematch/tapematch/audio.py, ingest.py, cli.py: a single undecodable source
  track no longer aborts the whole tapematch run (BUG-176). duration_sec() now raises
  UnreadableAudioError on decode failure; ingest.source_report() wraps this into
  UnreadableSourceError(source_dir, track); cli.py main() now drops any source that
  raises this error up front, prints "[SKIP] source excluded: unreadable file <path>",
  and continues with the remaining sources (requires >=2 to proceed).
Added: tools/tapematch/tests/test_unreadable_source.py: covers UnreadableAudioError and
  UnreadableSourceError for a corrupt/non-audio file with a .flac extension.

[2026-06-14] — fix(gui): BUG-184 — backend subprocesses (ffmpeg/sox/shntool) orphaned on quit
Fixed: gui_next/src/main/index.ts: added killProcessTree(pid) — on Windows runs
  `taskkill /F /T /PID` so the entire process tree spawned by LosslessBobBackend.exe is
  killed, not just the exe itself. backendProc.kill('SIGTERM') only TerminateProcess'd
  the backend exe, leaving any in-flight ffmpeg/sox/shntool.exe child process running as
  an orphan after a normal app quit. Used in before-quit and killStalePid; also added
  /T to the existing taskkill in killPortProcess.

[2026-06-14] — fix(gui): BUG-183 — Windows installer "cannot be closed" prompt on orphaned backend
Fixed: gui_next/resources/installer.nsh (new): added `customInit` NSIS macro that force-kills
  any leftover LosslessBobBackend.exe before file extraction. Root cause: that backend
  process can outlive LosslessBob.exe after an abnormal exit (Windows doesn't kill children
  when a parent dies), and electron-builder's built-in "app is running" check only knows
  about LosslessBob.exe, so the locked backend exe made every install/update show
  "LosslessBob cannot be closed. Please close it manually and click Retry to continue."
  electron-builder auto-picks up resources/installer.nsh as the NSIS custom include.

[2026-06-14] — chore: v1.5.0 release
Changed: gui_next/package.json, gui_next/package-lock.json: version bumped
  1.4.0 -> 1.5.0.

[2026-06-13] — fix(tools): TODO-139 Task 7 — tapematch error/no-verdict triage (BUG-180/181/182)
Fixed: tools/tapematch/tapematch/ingest.py: list_tracks now requires p.is_file()
  in addition to suffix matching (BUG-180) — a subdirectory named
  "1987-10-05locarno+asm.flac" was matched as a track and crashed
  audio.duration_sec() with LibsndfileError. Re-run of 1987-10-05 now
  completes (5 sources, 2 families).
Fixed: tools/tapematch/tapematch_session.py: find_lb_folders now drops
  collection folders with no audio files via _has_audio() (BUG-181), printing
  "Excluded (no audio found): LB-XXXXX" — previously such a folder made
  ingest.concat_source raise ValueError("no audio in ...") and crash the
  entire date's run. Re-runs of 1987-10-05/1989-08-26/1989-09-03 now complete
  (2/2/8 families); 1989-09-01 (left with 1 source) now gets the new
  insufficient_sources report below instead of crashing.
Fixed: tools/tapematch/tapematch_session.py: resolve_from_collection now
  catches OSError from p.is_dir() and treats an unreachable collection path
  (e.g. /mnt/DYLAN2 offline) as "missing" instead of crashing the session
  (BUG-182, found during validation).
Added: tools/tapematch/tapematch_session.py: run_date now writes an explicit
  **insufficient_sources** status into report.md (and archives the run) when
  fewer than 2 sources remain after exclusion, instead of returning early with
  nothing written.
Added: tools/tapematch/gen_analysis.py: parse_report/build_analysis/main
  recognize the insufficient_sources marker and render a clean status section
  instead of ERROR.
Added: tools/tapematch/tests/test_ingest_list_tracks.py,
  test_find_lb_folders_no_audio.py, test_insufficient_sources.py (6 new tests;
  full tapematch suite 33/33 pass).
Added: data/tapematch/runs/20260605_214549_2026-06-05/SKIP_REASON,
  20260605_215513_2026-06-05/SKIP_REASON — mark these as test/calibration
  artifacts (2000-03-14 Visalia content under a fake date), kept not deleted.
Note: 1993-04-23 (LB-04994, d1t01.flac, 4186 bytes truncated) and 2001-07-07
  (LB-14942, d1t01.flac, 0 bytes) are genuinely corrupted source files —
  reported to user, not modified per spec. Full writeup in
  tools/tapematch/BASELINE.md "Task 7 results". This completes the TODO-139
  task sequence (Tasks 2-7).

[2026-06-13] — fix(gui): BUG-179 — Pipeline "File all into collection" left stuck-running ghost rows
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now guards
  against re-entrant filing jobs (filingRef/filingActive — bails with a toast if a
  filing job is already in flight) and the "File all N into collection" button is
  disabled while a batch is running. The /api/pipeline/file/status polling loop now
  checks status.path against row.folderPath and bails with a "job mismatch" error
  if the global _FILE_JOB has been taken over by a different job, instead of
  spinning forever with running:true and a frozen progress bar.
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: local toast state +
  showToast() in ScreenPipeline (three existing calls referenced a non-existent
  LbdirStageContent-scoped showToast — also fixed by this).
Added: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: pipeline.file.busy,
  pipeline.file.jobMismatch.

[2026-06-13] — fix(gui): BUG-178 — Pipeline "Final storage" destination stale after Apply rename
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename updated
  row.folderPath/folderName to the renamed path and re-runs the "file" step against
  the new path, merging the refreshed dest/dest_parent/mount_label into the row —
  previously "Final storage" kept showing the destination built from the pre-rename
  folder name even though "Staging" already reflected the applied rename.

[2026-06-13] — fix(gui): BUG-177 — Pipeline "Apply rename" failed silently on duplicate folder
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename ignored error/409
  responses from /api/folder/rename (e.g. "Target already exists" when a folder with the
  proposed name already exists at the destination) and swallowed network errors, leaving the
  Rename step looking unchanged with no feedback. Now stores the error on
  row.steps.rename.error and RenameStageContent shows a "Rename failed" banner with the
  message; status stays 'warn' so the user can edit the name and retry.

[2026-06-13] — fix(gui): TODO-145 — Pipeline table dead space before LB#/Apply/File columns
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: Pipeline queue
  table colgroup gave the Status column no fixed width, so on wide windows it
  absorbed all leftover space while its content stayed left-aligned,
  stranding the LB#/Apply/File columns far to the right. Capped the Status
  column at 240px and made the folder-name column (previously fixed 380px)
  the flexible one that absorbs remaining width.

[2026-06-13] — feat(tools): TODO-139 Task 6 — re-run queue generator + batch mode
Added: tools/tapematch/build_rerun_queue.py: queries observations.db's
  `latest_pairs` view (Task 2) for concert dates with >=1
  `lb_says_same=1 AND tapematch_verdict='different_family'` pair (a miss
  against LB commentary), ordered by miss count desc. Writes
  `tools/tapematch/rerun_queue.txt` (232 dates), one date per line with the
  miss count as a trailing comment. `--since TIMESTAMP|REF` excludes dates
  whose latest run is already at/after a given ISO timestamp or git ref (for
  re-running the queue after a future fix commit lands). `--dry-run` previews
  without writing.
Added: tools/tapematch/tapematch_session.py: `run_batch()` + `--batch FILE`
  consumes a re-run queue file sequentially via the existing `run_date()`.
  Blank/comment/already-`# done`-marked lines are skipped; each completed
  line gets `# done <timestamp>` appended (resumable after interruption or
  KeyboardInterrupt, which leaves the in-progress line unmarked and exits 130).
Added: tools/tapematch/tests/test_build_rerun_queue.py (4 tests),
  tools/tapematch/tests/test_batch_queue.py (4 tests).
Changed: .gitignore: tools/tapematch/rerun_queue.txt is a generated/mutable
  artifact (gets `# done` markers as the queue is processed) — gitignored
  alongside observations.db.
Note: queue currently lists all 232 dates with >=1 lb_says_same miss (no
  --since applied yet — Task 4/5 fixes are uncommitted). Per Task 6 spec
  step 5, dates with 0 misses are never queued. Next: Task 7 (error/no-verdict
  triage).

[2026-06-13] — fix(backend): BUG-176 — pipeline rename now flags folders missing their (LB-NNNNN) tag
Fixed: backend/app.py: in the BUG-119 fallback (rename step when the DB entry has no
  date_str/location), the proposed name was derived from the current folder name with
  no check that it actually contains "(LB-NNNNN)", so untagged folders were reported as
  "Folder name is already correct" and could be promoted to "ready to file". Now, if the
  entry's location is blank but date_str is present, the rename step first looks up
  bobdylan_shows by date to fill in the location, so the standard "date Location (LB-NNNNN)"
  order can still be proposed (e.g. LB-16311 → "2022-10-06 Berlin, Germany (LB-16311)").
  Only when no bobdylan_shows match exists does it fall back to checking for the correct
  "(LB-{lb_number:05d})" tag on the existing name, stripping any stale tag, and proposing
  to append the correct one — without touching date/location (BUG-119 stays fixed).

[2026-06-13] — fix(gui): Animate "Running" spinner in pipeline stage indicators
Fixed: gui_next/src/renderer/src/index.css: the `.p2-spin` class used by
  StateGlyph and StageNode (PipelineParts.tsx) for the "Running" state circle
  had no animation defined, so the spinner rendered static. Added a
  `p2-spin` keyframes rule (360° rotation, 0.8s linear infinite) and the
  `.p2-spin` class.

[2026-06-13] — fix(gui): BUG-166 — Pipeline "In collection" badge shown before filing
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyRename's success branch
  hardcoded `bucket: 'done'` after a rename, even when the File step (step 5) was still
  `'warn'` (not yet filed). Now derives bucket as `r.steps.file.status === 'warn' ? 'shelf'
  : 'done'`, matching serverRowToPipeline's guard. Fixes the green "In collection"/"Filed to
  <mount>" badge appearing prematurely, and restores the "File all N into collection" button
  (was hidden because these rows weren't counted in counts.shelf).

[2026-06-13] — feat(tapematch): TODO-139 Task 5 — staircase union-flag fix + short-window calibration
Added: tools/tapematch/tapematch/align.py: union_staircase_sources() — a source
  counts as "staircase" if classified "staircase/splice" in either lag-curve pass
  (vs initial ref, or vs re-selected central ref). Fixes a reference-ambiguity bug:
  speed_info[ref_name]["kind"] is always "reference" under a single pass, so a pair
  involving the current reference source could never be flagged staircase on that
  source.
Changed: tools/tapematch/tapematch/cli.py: central-ref lag-curve pass
  (speed_info_central) now computed before the secondary-match loop so
  staircase_sources = union_staircase_sources(speed_info, speed_info_central) can
  drive the existing 15s short-window OR-fallback; central-ref pass still printed
  in its original later output position (section order unchanged).
Changed: tools/tapematch/tapematch/match.py: secondary_corr_pair() takes optional
  return_raw bool — adds win_corrs/hiss_corrs (raw per-window correlations) to the
  returned dict for calibration use.
Added: tools/tapematch/calibrate_staircase.py — one-off tool computing per-window
  residual_corr distributions at a short window size for known same-source /
  different-source-same-show staircase pairs (2001-10-30).
Added: tools/tapematch/config.yaml: secondary_match.staircase_window_sec/hop_sec
  (5.0/2.0) and staircase_window_corr_threshold/coverage_threshold (both null) —
  documented but disabled, see Note below.
Added: tools/tapematch/tests/test_staircase_union.py: 3 tests covering the
  2001-10-30 reference-ambiguity scenario, empty-second-pass case, and the
  no-staircase-sources case.
Note: calibration of the new 5s/2s pass on 2001-10-30 found no usable
  residual_corr gap — same-source median 0.0118 vs different-source-same-show
  median 0.0153 (higher), distributions fully overlap at every threshold tried. Per
  spec, the new pass was NOT wired into cli.py (thresholds left null/disabled). The
  union-flag fix itself is regression-free on 3 control dates and on 2001-10-30
  (byte-identical CLUSTERS/LINEAGE/DIAGNOSTICS, same 6/6 lb_says_same misses,
  identical corr values pre/post fix). Full writeup in
  tools/tapematch/BASELINE.md "Task 5 results". Piecewise alignment (spec step 4)
  deferred — tracked as TODO-144.

[2026-06-13] — fix(gui): BUG-175 — Windows fonts render badly (fallback font + blurry ClearType)
Changed: gui_next/src/renderer/index.html: removed the Google Fonts <link>/preconnect
  tags and tightened the CSP — style-src/font-src no longer allow
  fonts.googleapis.com/fonts.gstatic.com.
Changed: gui_next/package.json: added @fontsource/inter, ibm-plex-sans, source-sans-3,
  jetbrains-mono (pinned exact versions) so fonts ship inside the app bundle.
Changed: gui_next/src/renderer/src/main.tsx: imports local font CSS for every
  weight previously requested from Google Fonts; sets a `platform-<platform>`
  class on <html> before React mounts.
Changed: gui_next/src/preload/index.ts, src/renderer/src/env.d.ts: expose
  `process.platform` to the renderer as `window.api.platform`.
Fixed: gui_next/src/renderer/src/index.css: scoped `-webkit-font-smoothing:
  antialiased` to `html.platform-darwin` only — on Windows this property
  disables ClearType subpixel rendering, making all text look blurry/thin
  regardless of which font is loaded.

[2026-06-13] — feat(backend+gui): TODO-143 — "Check for Updates" master snapshot install from GitHub
Added: backend/app.py: GET /api/master/github_check — queries the latest
  kuddukan42/losslessbob GitHub release, downloads its manifest sidecar, and
  compares master_version against the local meta table to report whether a
  newer master snapshot is available.
Added: backend/app.py: POST /api/master/github_install — text/event-stream
  endpoint that downloads the latest master .db + manifest from GitHub
  Releases into data/imports/, verifies SHA256, and applies it via
  database.import_master_db(), streaming progress events (mirrors
  /api/master/github_release's event shape).
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: CuratorToggle gains
  a "Check for updates" button (handleCheckGithubMaster + runGithubInstall)
  that checks GitHub, confirms with the user, then streams install progress
  as toasts. Existing file-picker button relabeled "Install from file…"
  (installUpdate key) to disambiguate from the new GitHub path.
Changed: gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: added
  setup.masterData.checkUpdate/checkingUpdate/githubUpdateBody and
  setup.toast.githubCheckFailed/masterUpToDate; reworded installUpdate to
  "Install from file…".
Note: porting gap from TODO-088 (PyQt _GitHubMasterThread) — gui_next only
  had the file-picker fallback; this restores the GitHub-check path.

[2026-06-13] — fix(gui): Scraper "Single Entry" Go button gave no feedback
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: the Go button's POST
  to /api/entry/<lb>/scrape discarded the response, so a skip (e.g. entry already
  up to date with force/download off) or error appeared as "nothing happened".
  Now awaits the response and writes a result line (done/skipped/error) to the
  Entry Metadata Live Log, and disables the button with a "Working…" label while
  the request is in flight.

[2026-06-13] — feat(tapematch): TODO-139 Task 4 — predicted-lag mode for speed-offset secondary match
Added: tools/tapematch/tapematch/align.py: local_lag_centered() — like local_lag()
  but centers the +-max_lag_sec residual search on an arbitrary lag_center_sec
  instead of zero, via scipy.signal.correlate(mode="valid"). No waveform resampling.
Added: tools/tapematch/config.yaml: secondary_match.high_ppm_threshold: 5000 — pairs
  whose speed offset (ppm, from estimate_ratio) is at or above this center each
  window's lag search on expected_lag(t) = lag_0 + ppm_ratio*(t - anchor0) instead
  of zero; below threshold, behavior unchanged.
Changed: tools/tapematch/tapematch/match.py: secondary_corr_pair() takes optional
  predicted_lag dict (ppm/lag_0/anchor0_sec) and uses local_lag_centered() for the
  windowed-coverage pass when |ppm| >= high_ppm_threshold.
Changed: tools/tapematch/tapematch/cli.py: computes pair_ppm from existing
  pair_ratios and lag_0 from local_lag() at anchors[0] for each cross-pair, passes
  predicted_lag into both secondary_corr_pair() call sites (main + staircase
  short-window fallback); logs PREDICTED_LAG debug lines.
Added: tools/tapematch/tests/test_predicted_lag.py: 3 tests covering
  local_lag_centered (finds a lag beyond +-max_lag_sec when centered correctly,
  not when centered on zero) and secondary_corr_pair predicted-lag activation/
  threshold gating.
Note: validated on 1989-06-04, 1990-01-12 (targets) and 3 control dates incl.
  1988-07-28 (high-ppm) — zero regressions, activates as specified, but does not
  reduce misses on either target date (root cause is not search-range for these
  pairs; see tools/tapematch/BASELINE.md "Task 4 results" and TODO-140).

[2026-06-12] — fix(backend+gui): LBDIR reconcile now recovers self-referencing/regenerated files from site/files (BUG-174)
Fixed: backend/checksum_utils.py: find_site_recoverable_files() only matched
  data/site/files/LBF-{N}-* candidates against missing lbdir entries by exact MD5.
  The lbdir manifest's self-checksum entry and regenerated report files (e.g.
  DigiFlawFinder-*.wavf.html) can never match by MD5 across lbdir revisions — the
  cached site copy is a different version of the same file — so they never produced
  a site_proposal even though a same-named LBF-{N}-* file existed. Added a
  filename-based fallback: strip the LBF-{N:05d}- prefix and compare (case/apostrophe
  -normalised) against the missing entry's basename, returning matched_by:'name' plus
  both md5 (site copy) and expected_md5 (what the folder's lbdir requires) so the user
  can see they differ.
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: SiteProposal gains
  expected_md5 and matched_by:'md5'|'name'.
Changed: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: "Recoverable
  from site/files" rows matched by name only render an "MD5 mismatch" warning pill
  (tooltip shows both hashes) plus a banner explaining the copy won't pass
  verification as-is.
Added: tests/test_checksum_utils_site_recovery.py: covers MD5 match, name-fallback
  match (self-referencing lbdir + DigiFlawFinder report), and the no-missing-entries
  empty case.

[2026-06-12] — fix(backend): qBittorrent save-path sync — match renamed folders moved between staging dirs (BUG-173)
Fixed: backend/qbittorrent.py: find_torrent_by_path()'s BUG-172 rename_history fallback
  computed the pre-rename path as old_folder.parent / <pre-rename name>, assuming the
  pipeline rename happened in the same directory qBittorrent's content_path points at.
  When the folder had been relocated between staging directories (e.g. hopper-bob ->
  1-DYLAN) before that in-place rename, the computed path never matched and sync silently
  no-op'd. Now also matches on the pre-rename folder name alone (basename), regardless of
  directory, when exactly one torrent's content_path basename matches.

[2026-06-12] — fix(backend): qBittorrent save-path sync now also fixes folders renamed before filing (BUG-172)
Fixed: backend/qbittorrent.py: find_torrent_by_path()'s fallback for torrents added outside
  the app workflow only matched on an exact content_path string, so it missed folders
  renamed by the pipeline's rename step before filing (qBittorrent still has the
  pre-rename name recorded). Now also checks rename_history for the most recent row whose
  new_path is the pre-filing folder, and matches qBittorrent torrents against the
  pre-rename name from old_path.
Added: backend/qbittorrent.py: rename_torrent_root() (POST /api/v2/torrents/renameFolder)
  and recheck_torrent() (POST /api/v2/torrents/recheck). relocate_tracked_torrent()'s
  external-match branch now relocates + renames the torrent's root folder to match the
  on-disk name, then triggers a recheck so qBittorrent immediately re-validates against
  the new location without re-downloading.

[2026-06-12] — fix(backend): Publish Master Update — GitHub asset upload returned 400 Bad Request (BUG-171)
Fixed: backend/app.py: master_github_release's _upload_asset() streamed the .db/.manifest
  asset via a plain generator while also setting a manual Content-Length header. requests
  can't size a bare generator, so it added Transfer-Encoding: chunked alongside
  Content-Length — uploads.github.com rejects that combination with 400 Bad Request at
  the first chunk. Replaced the generator with a _ProgressFile object exposing __len__
  (real file size) and read() (1 MB chunks + progress events), so requests sends a real
  Content-Length with no chunked encoding.

[2026-06-12] — fix(backend): Pipeline scan-tree finds top-level folders whose audio is in subfolders (BUG-170)
Fixed: backend/app.py: pipeline_scan_tree's shallow mode checked each immediate child of
  the picked root with `_has_audio()` (direct files only), so release folders whose audio
  lives in CD1/CD2/Extras subfolders (no audio directly in the release folder) were skipped
  entirely after BUG-167 switched the GUI to shallow scanning. Added `_has_audio_anywhere()`
  (rglob-based) for the immediate-children check — a top-level folder is now returned if it
  contains audio anywhere beneath it, while only that top-level path is added (not the
  nested subfolders).

[2026-06-12] — feat(backend): qBittorrent save-path sync now finds torrents added outside the app
Added: backend/qbittorrent.py: find_torrent_by_path() — GET /api/v2/torrents/info (unfiltered)
  and matches each torrent's content_path (or save_path/name fallback) against a folder path.
  _track_external_torrent() records a discovered torrent's infohash into the torrents table
  (updating an existing row or inserting a minimal one) so future relocations use the
  DB-tracked lookup.
Changed: backend/qbittorrent.py: relocate_tracked_torrent() now falls back to
  find_torrent_by_path() when no torrents row has added_to_qbt=1 with a matching
  source_folder/infohash, so folders seeded outside the "Add to qBittorrent" workflow still
  get their save path synced on filing.

[2026-06-12] — feat(backend+gui): sync qBittorrent save path when filing a tracked folder
Added: backend/qbittorrent.py: set_location() (POST /api/v2/torrents/setLocation) and
  relocate_tracked_torrent() — after a pipeline filing move, looks up torrents rows for
  the LB with added_to_qbt=1 and a known infohash whose source_folder matches the
  pre-move path, points qBittorrent at the new parent directory (triggering its normal
  hash recheck so seeding resumes without re-downloading), and updates source_folder in
  the torrents table on success.
Changed: backend/filer.py: start_file_job's _run() calls the new
  _sync_qbt_location() helper after a successful move + collection registration;
  result dict now includes qbt_synced/qbt_error (best-effort — never fails the filing job).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile shows a toast
  on the filing result's qbt_synced/qbt_error. Added pipeline.file.qbtSynced /
  qbtSyncFailed to all 6 locale files.

[2026-06-12] — feat(gui): Pipeline status group headers are now collapsible (TODO-141)
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: per-bucket collapsed
  state (collapsedBuckets) and toggleBucket callback. GroupRow now receives
  expanded/onToggle so clicking NEEDS YOU/READY/RUNNING/ON SHELF/DONE headers
  toggles the chevron and hides/shows that bucket's rows in the virtualized list.

[2026-06-12] — fix(backend): Publish Master Update now refreshes "Master version" / "Last published" (BUG-169)
Fixed: backend/app.py: master_github_release's _work() uploaded the exported snapshot to
  GitHub but never wrote master_version/master_published_at back into the live DB —
  export_master_db() only stamps those keys inside the exported .db, not the source DB.
  /api/master/status reads from the live DB's meta table, so the Setup screen's "Master
  version" / "Last published" fields stayed stale after every publish. Now reads the
  manifest sidecar after both assets upload successfully and calls database.set_meta()
  to write master_version/master_published_at into the live DB before the "done" event.

[2026-06-12] — fix(backend): master release notes summarize status changes by category instead of listing every LB number
Changed: backend/db.py: generate_release_notes now groups lb_status_history rows by
  (old_status, new_status, trigger_event) and emits one summary line per group with a
  count and date range, instead of one line per LB number — a 353-row status change
  (e.g. all "— → private" via flat_file_apply) is now a single "— → private: 353
  _2026-05-21_ flat_file_apply" line rather than 353 individual "LB-NNNNN: ..." lines.

[2026-06-12] — feat(gui): TODO-142 — pipeline batch filing skips per-folder confirmation
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now accepts a
  skipConfirm flag that bypasses the "File into Collection" confirm dialog and applies
  the recommended mount path directly. applyAllFileable and applySelectedFileable pass
  skipConfirm=true so batch filing runs with no per-folder prompts; the single-row
  "File" button still confirms.

[2026-06-12] — fix(gui): Publish Master Update no longer fails with a JSON parse error (BUG-168)
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handlePublishMaster called
  `gr.json()` on the response from POST /api/master/github_release, but that endpoint
  (since TODO-115..120) responds with `text/event-stream` progress events, not JSON —
  `.json()` threw a SyntaxError, surfaced as "Publish failed: ... is not valid JSON",
  and the release was never created. Now reads the SSE stream via `body.getReader()`,
  shows each `progress` event as a toast, and handles `done`/`error` events.

[2026-06-12] — fix(gui): Pipeline "Scan tree…" now scans only 1 level deep (BUG-167)
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: handleScanTree now passes
  shallow: true to POST /api/pipeline/scan-tree (was shallow: false), matching the
  depth-1 behaviour already used by ScreenLBDIR's "Add Root" scan.

[2026-06-12] — feat(tools): TODO-139 Task 3 — OOM audit + validation (1994-02-20 now completes)
Changed: tools/tapematch/tapematch/match.py: removed dead `pairwise_matrix()` — unused
  (no callers anywhere in the repo), held a `streams_mono` dict of every source's full
  mono array in RAM simultaneously. This was the retained-reference pattern the Task 3
  OOM hypothesis described; cli.py's per-pair memmap loop superseded it in the 2026-06-05/06
  OOM fixes (BUG-144 and the Pass-4 OOM fix) but the dead function was left behind.
  tools/tapematch/tapematch/cli.py: added a pre-run estimate log line
  ("est. peak RAM ~X GB (N sources, largest H:MM:SS)") computed from probed durations
  (header reads only) — mono float32 @ analysis_sr is sr*4 bytes/sec; estimate is
  2x the largest source + 300 MB fixed overhead, documented as an order-of-magnitude
  lower bound, not a hard cap.
Fixed: (validation only, no further code change needed) — audited dtype/rate handling
  across ingest.py/audio.py/match.py/align.py/cli.py per CC_TAPEMATCH_FIXES.md Task 3.
  The float64/96kHz-stereo OOM hypothesis was already resolved by prior sessions:
  audio.py's ffmpeg-pipe decode+resample keeps native-rate arrays out of Python entirely
  (only the 16kHz float32 output lands in RAM); ingest.concat_source frees each track
  immediately after copying into a pre-allocated float32 buffer; cli.py Pass 1 writes
  that buffer to a float32 memmap and frees it; resample_ratio uses soxr natively in
  float32. Confirmed empirically (numpy 2.4.6/scipy 1.17.1) that scipy.signal.correlate
  and numpy mean/std preserve float32 — no float64 promotion at any correlation call site.
  1994-02-20 (8 sources, the OOM case study with no prior run dir) now completes:
  5 families, peak RSS 2.6 GB, archived to data/tapematch/runs/20260612_140009_1994-02-20,
  28 pairs logged to observations.db. Re-ran 1993-04-16 (3-source control,
  data/tapematch/runs/20260612_143159_1993-04-16): family assignments, correlation
  matrix, and speed-ppm values are bit-identical to the 2026-06-07 run — float32
  pipeline is deterministic and unchanged.

[2026-06-12] — feat(backend+gui): TODO-110 follow-up — drive stats on Mounts settings screen
Changed: backend/filer.py: disk-usage calculation extracted into new
  get_disk_usage_stats(root_path, online) helper (free/total/used_pct), reused by
  get_mounts_with_stats() and the /api/collection/mounts endpoint.
Changed: backend/app.py: collection_mounts_list() (/api/collection/mounts GET) now
  attaches free/total/used_pct to each mount alongside the existing online flag.
Changed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: CollectionMount gains
  free/total/used_pct; MountCard on the Mounts settings screen now shows "free of
  total" with a colour-coded usage bar (warn at 75%, bad at 90%), matching the
  Collect step's mount picker.
Changed: gui_next locales (en/de/es/fr/it/nl): added mounts.freeOfTotal and
  mounts.usageTooltip.

[2026-06-12] — feat(backend): pipeline filing — hash-verify copies before deleting source
Added: backend/filer.py: hash_tree(root) computes a SHA-256 digest over every file's
  relative path + content under a folder, used to confirm a copy is byte-identical
  to its source. New _HashVerificationError exception.
Changed: backend/filer.py: start_file_job's _run() now hash-verifies the destination
  against the source whenever data is actually copied (file_mode="copy", or a
  cross-device move that falls back to copy+rmtree) — new "verifying" stage before
  comparing hashes, and "removing" stage before deleting the original (move only).
  A hash mismatch deletes the bad copy, leaves the source untouched, and returns
  error_code "hash_mismatch". Same-device moves still use atomic os.rename (no file
  content is rewritten, so no hash check). If the verified copy succeeds but removing
  the original fails, the job still succeeds (warning logged) rather than discarding
  the verified copy.
  gui_next/src/renderer/src/screens/ScreenPipeline.tsx: updated FileProgress stage
  comment to include verifying|removing.
  gui_next/src/renderer/src/locales/{en,de,es,fr,it,nl}.json: added
  pipeline.file.progress.verifying/removing labels.
  PROJECT.md: documented new stages and hash_mismatch error code for
  /api/pipeline/file/status.

[2026-06-12] — feat(scraper): TODO-139 Task 2 — observations.db run versioning + latest_pairs view
Added: tools/tapematch/migrate_observations.py: one-shot, idempotent migration. Normalizes
  pair-key ordering (`lb_a < lb_b`, swapping all `*_a`/`*_b` columns on violating rows) and
  creates `idx_pairs_latest` + the `latest_pairs` view (one row per (concert_date, lb_a, lb_b)
  key — the most recent verdict by run_at, ties broken by id). Dry-run by default; `--apply`
  backs up observations.db to `observations.db.bak-<timestamp>` first.
  tools/tapematch/tests/test_migrate_observations.py: unit tests for normalization,
  idempotency, and the latest_pairs view.
Changed: tools/tapematch/tapematch_session.py: OBS_SCHEMA now creates `idx_pairs_latest` and
  `latest_pairs` (idempotent, CREATE IF NOT EXISTS) so fresh/future DBs get them automatically.
  insert_pairs() now normalizes lb_a/lb_b (and all paired fields) to lb_a < lb_b before
  insert, so new rows never violate the ordering migrate_observations.py enforces.
  .gitignore: added `tools/tapematch/observations.db.bak-*`.
Fixed: tools/tapematch/observations.db: migration applied — 1719 of 4318 rows had
  lb_a > lb_b and were normalized (swapped); 0 remain. latest_pairs view verified: 4105
  distinct (concert_date, lb_a, lb_b) keys → 4105 rows. Backed up to
  observations.db.bak-20260612_124147 before applying (gitignored, not committed).
  Found and logged BUG-165 (lb_a==lb_b degenerate rows from a folder-name regex
  cross-reference bug) — out of scope for this task, left for separate triage.

[2026-06-12] — fix(scraper): BUG-164 — TODO-139 Task 1: gen_analysis.py parser fix + re-baseline
Fixed: tools/tapematch/gen_analysis.py: _build_observations no longer treats
  "alternative recording to X/Y ... which all appear to be same recording" snippets
  as a same-source signal for the subject LB — _diff_signal(snip) now suppresses
  _same_signal(snip), falling through to FALSE MERGE / neutral "→" instead of a
  false MISS. See BUG-164 in BUGS_DONE.md.
Added: tools/tapematch/tests/test_gen_analysis.py: unit tests for the ambiguous
  snippet plus clean positive/negative same/diff-source snippets.
  tools/tapematch/BASELINE.md: corrected reference numbers (totals, corr-bucket
  distribution, per-date worst-miss table, lb_says_same caveat, and a documented
  live example of the Task 2 conflicting-verdicts problem on 1996-07-21).
Changed: data/tapematch/runs/*/analysis.md: all 429 regenerated via
  `gen_analysis.py --overwrite --all` (0 errors); analysis.md-level MISS count for
  2001-10-30 dropped 5→0 (confirmed parser noise).

[2026-06-12] — fix(db): BUG-155 — correct "Mnchen" location typo on 5 entries
Fixed: data/losslessbob.db: entries.location for LB-9546, 10083, 12969, 16298,
  16626 corrected from "Mnchen..." (source-site typo, missing "u" — not an
  encoding/ü-drop issue as originally reported) to "Munchen..." matching the
  existing ASCII convention. Cleaned up matching location_geocoded cache rows
  (renamed two, removed two now-duplicate rows); entries_fts updated via the
  existing AFTER UPDATE trigger.
[2026-06-12] — feat(backend+gui): TODO-111 — collection integrity monitor (lbdir-based)
Added: backend/integrity_monitor.py: new scan engine. scan_collection() iterates
  my_collection, locates each folder's lbdir manifest (folder-local or attached),
  and reuses checksum_utils.verify_folder_lbdir() to classify results — ffp_status
  'fail' = content_issue (bitrot/corruption), md5_status 'fail' with ffp pass/na =
  tag_issue (metadata-only edit), overall 'missing' = missing_files. Files with
  overall == 'extra' are ignored. start_scan_async/get_scan_status/cancel_scan
  provide a background-thread job with progress, modeled on filer.py's _FILE_JOB.
Added: backend/db.py: new tables collection_integrity_status (latest per-LB
  result) and collection_integrity_scans (scan history); idempotent
  integrity_events.mount_id column migration; new functions
  upsert_collection_integrity_status, get_collection_integrity_status,
  get_mount_integrity_summary, record_integrity_scan_start, finish_integrity_scan,
  get_integrity_scan_history; log_integrity_event() gains mount_id param.
Added: backend/scheduler.py: _integrity_scan_worker + start/stop_integrity_scan_scheduler
  — hourly check against meta key integrity_scan_interval_hours (default "0" =
  disabled), triggers a whole-collection scan via integrity_monitor.start_scan_async().
Changed: backend/app.py: new routes POST /api/collection/integrity/scan (+/cancel),
  GET /api/collection/integrity/scan/status, /scan/history, /summary, /status;
  /api/db/settings GET now includes integrity_scan_interval_hours;
  start_integrity_scan_scheduler() wired alongside start_collection_watcher().
Changed: gui_next/src/renderer/src/screens/ScreenMounts.tsx: MountCard shows an
  integrity severity badge (corrupt/missing/tag-only/verified) and a per-mount
  "Scan integrity" button. New "4 · Integrity Monitor" section: scan now (whole
  collection or per-mount) with a live progress bar and cancel button, auto-scan
  interval dropdown (off/daily/weekly/monthly), findings table for non-passing
  folders, and a recent-changes list (content/tags/missing/restored) with
  per-row and bulk acknowledge.

[2026-06-12] — fix(backend): BUG-163 — undefined `_time` in admin restart handler
Fixed: backend/app.py: `_do_restart()` called `_time.sleep(0.3)` but only `time`
  is imported; renamed to `time.sleep(0.3)`. Caught by ruff (F821) on commit.

[2026-06-12] — feat(gui): move Mounts & Routes out of Setup into its own screen
Added: gui_next/src/renderer/src/screens/ScreenMounts.tsx: new screen hosting the
  storage-mounts/year-routing/filing-mode card (extracted from ScreenSetup).
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: removed the
  CollectionRoutingCard and its helper components (now in ScreenMounts.tsx);
  dropped now-unused Input/IconButton imports.
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added 'mounts' nav
  item (Settings group, directly below Setup); added 'mounts' to NavId.
Changed: gui_next/src/renderer/src/App.tsx: added /mounts route -> ScreenMounts.
Added: gui_next/src/renderer/src/components/Icon.tsx: new "mounts" (hard-drive)
  icon for the nav entry.
Added: gui_next locales (en/de/es/fr/it/nl): appShell.nav.mounts and new
  mounts.title/mounts.subtitle keys.

[2026-06-12] — feat(backend+gui): TODO-110 — drive stats on pipeline mount cards
Changed: backend/filer.py: get_mounts_with_stats() now also returns total
  capacity (total) and used percentage (used_pct), via shutil.disk_usage(),
  alongside the existing free space and span fields.
Changed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: Mount
  interface gains total/used_pct; MountPicker mount cards now show "free of
  total" and a colour-coded usage bar (warn at 75%, bad at 90%), updating
  reactively as the pipeline re-resolves the Collect step.
Changed: gui_next locales (en/de/es/fr/it/nl): replaced collect.freeAmount with
  collect.freeOfTotal and added total/used % to collect.mountTooltip.

[2026-06-12] — feat(backend+gui): TODO-112 — backend uptime clock on About screen
Added: backend/app.py: new GET /api/system/uptime endpoint returning
  uptime_seconds since the Flask process started.
Changed: backend/app.py: /api/admin/status now shares the same process-start
  timestamp (_process_start_time) instead of its own duplicate.
Changed: gui_next/src/renderer/src/components/AboutDialog.tsx: About tab now
  shows a live "uptime" field (HH:MM:SS) fetched from /api/system/uptime and
  ticked locally, to help confirm whether a backend restart actually happened.

[2026-06-12] — fix(backend+gui): TODO-113 — consolidate app version numbering
Changed: VERSION: bumped 1.3.0 -> 1.4.0 to match gui_next/package.json (now the
  source of truth, mirrored here for the Python backend/CLI).
Changed: backend/paths.py: removed stale duplicate APP_VERSION constant (1.2.0).
Changed: backend/forum_poster.py: forum post footer now uses backend.version.VERSION
  instead of the removed APP_VERSION.
Changed: cli.py: interactive shell banner now uses backend.version.VERSION instead
  of a separate hardcoded _VERSION ("1.0.3").
Changed: gui_next/electron.vite.config.ts: renderer build now defines __APP_VERSION__
  from gui_next/package.json's version field; declared in env.d.ts.
Changed: gui_next/src/renderer/src/components/SplashOverlay.tsx,
  components/AboutDialog.tsx: replaced hardcoded "1.2.0" version strings with
  __APP_VERSION__.
Changed: gui_next/src/renderer/src/components/AppShell.tsx + locales/*.json:
  sidebar tagline "version" string now interpolates {{version}} = __APP_VERSION__
  instead of a stale hardcoded "v1.0.6".

[2026-06-12] — feat(gui): TODO-138 — Pipeline "Auto-rename" toggle
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: new "Auto-rename"
  toggle in the pipeline header (off by default, alongside "Auto-run on drop").
  When on, any folder where verify/lookup/lbdir all pass and rename has a single
  confident proposed name (bucket "ready") is auto-renamed via the existing
  applyRename() path — marking step 4 (rename) green and advancing the row to
  the collect stage — with no "Apply rename" click needed. When off, behavior
  is unchanged: proposed renames sit in the "ready" bucket for manual Apply.
Added: gui_next/src/renderer/src/locales/en.json: pipeline.autoRename /
  pipeline.autoRenameHint strings. Note: DeepL key in .claude/settings.local.json
  is currently disabled (AuthorizationException), so de/fr/es/it/nl translations
  for these two keys (and the pre-existing ~27/N pipeline-section gap in those
  locales) were not refreshed — i18next falls back to English for now.

[2026-06-12] — feat(backend+gui): TODO-137 — pipeline step order: LBDIR now runs before Rename
Changed: backend/app.py: _pipeline_process_folder reorders steps to
  verify -> lookup -> lbdir -> rename -> file (collect); LBDIR retrieve+verify
  is now step 3 and Rename proposal is step 4. Severity status list reordered
  to match. pipeline_run's default steps list/docstring updated.
Changed: backend/app.py: /api/lbdir/check and /api/lbdir/reconcile accept an
  optional lb_number_hint body param, falling back to my_collection ->
  folder-name regex -> hint, since LBDIR now runs before the folder is
  renamed/filed and won't yet have "LB-NNNNN" in its name.
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx:
  DEFAULT_STAGES reordered/renumbered to verify(1)/lookup(2)/lbdir(3)/rename(4)/
  collect(5).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: all step-key
  iteration orders (toFolderRow, firstActiveStage, deriveFolderStatus,
  mergeServerRow, autorun/auto-complete) reordered to verify/lookup/lbdir/
  rename/file; the auto-complete "stale" check now resumes on
  lbdir.status === 'mute' (was rename) and re-runs ['lookup','lbdir','rename',
  'file']. LbdirStageContent passes lb_number_hint (from the Lookup step) to
  /api/lbdir/check and /api/lbdir/reconcile. Updated stage copy: "Runs after
  lookup" (was "after rename"), Lookup's "flows into LBDIR" (was "Rename"),
  and Rename's success banner now says "Ready to collect next" (was "LBDIR
  will reconcile next").

[2026-06-12] — chore(release): v1.4.0 — pipeline v2 (storage mounts, lookup, lbdir, rename, collect)
Changed: gui_next/package.json: version bumped 1.3.0 -> 1.4.0.
Changed: merged feat/pipeline-v2-storage-mounts into main — collection mount management,
  Quick Lookup screen, pipeline lookup/rename/lbdir/collect stage panels, background
  copy/move with progress, and associated bugfixes (see entries below).

[2026-06-12] — fix(backend+gui): BUG-162 — pipeline Lookup no longer Passes on a partial checksum match
Fixed: backend/app.py: _pipeline_process_folder's lookup step now requires
  summary.matched == summary.given (e.g. 42/42) for a resolved LB# to report
  status "ok"/Pass. A single-LB match with fewer matches than given checksums
  (e.g. 21/42 — ffp matches but md5 doesn't) now reports status "warn" /
  label "Incomplete match", with lb_number still set so Rename/LBDIR/Collect
  proceed, plus a row["errors"] entry noting the X/Y ratio.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LookupStageContent
  gained a warn branch for "Incomplete match" (lb_number set, not a Conflict)
  that explains the mismatch and renders <LookupDetail> (summary + per-checksum
  table) so the unmatched (NOT FOUND) checksum rows are visible — previously the
  "ok" branch showed only a green banner with a small "21/42 matched" caption and
  no detail table at all.
Changed: BUGS.md, BUGS_DONE.md: added BUG-162 (Fixed).

[2026-06-11] — fix(gui): BUG-154 — guard against stray tsc-emitted .js shadowing .tsx sources
Fixed: gui_next/.gitignore: added src/{renderer,main,preload}/**/*.js entries. The stale
  build artifacts from BUG-154 were already removed and tsconfig.web.json/tsconfig.node.json
  already set noEmit:true; this closes the remaining gap so a future non --noEmit tsc run
  can't silently reintroduce shadow .js files.
Changed: BUGS.md, BUGS_DONE.md: moved BUG-154 to the archive as Fixed.

[2026-06-11] — chore(docs): move 25 fixed bugs (BUG-122–153) from BUGS.md to BUGS_DONE.md
Changed: BUGS.md, BUGS_DONE.md: moved all "Fixed" entries to the archive, keeping only
  Open bugs (BUG-106, 118, 120, 146, 154, 155) in BUGS.md. Also removed BUG-133/134 from
  BUGS.md — they were duplicates already present in BUGS_DONE.md.

[2026-06-11] — fix(backend): pipeline — Collect "Confirmed" date now stamps on LBDIR pass
Fixed: backend/app.py: BUG-161 — the pipeline's LBDIR step (step 4) computed a "pass"
  result but never called database.set_lbdir_verified(), so the Collect stage's
  "Confirmed" row (my_collection.lbdir_verified_at) never updated for an owned folder
  re-checked in place. Now calls set_lbdir_verified() on pass, same as /api/lbdir/verify;
  no-op for not-yet-filed folders (no matching my_collection.disk_path row).

[2026-06-11] — feat(backend+gui): pipeline — Collect tag preview shows real status/confirmed data
Changed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: TagTable's
  "Status" row now shows the real lb_master.lb_status (Public/Private/Missing/Nonexistent)
  plus owned/not-in-collection, and "Confirmed" shows the real my_collection.lbdir_verified_at
  date (or "Not yet confirmed") instead of hardcoded "Public · Owned" / "Today".
Removed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: dropped the
  "Fingerprint: Queued · AcoustID" row — a stale design-mockup placeholder never wired to a
  real queue (unrelated to the completed audio-fingerprint-identify feature, TODO-106).
Changed: backend/app.py: `/api/pipeline/status` file step now returns lb_status, owned, and
  lbdir_verified_at (queried from lb_master / my_collection) for the Collect stage.
Changed: gui_next/src/renderer/src/locales/*.json: removed rowFingerprint/valueFingerprint/
  valueStatus/valueConfirmed; added statusPublic/statusPrivate/statusMissing/
  statusNonexistent/statusUnknown/ownedYes/ownedNo/notConfirmed (all 6 languages).

[2026-06-11] — feat(backend+gui): pipeline — progress bar for Collect step copy/move
Added: backend/filer.py: replaced synchronous `file_folder()` with `start_file_job()` +
  `get_file_job_status()` — a background-thread job (shared `_FILE_JOB` dict + lock) that
  scans the source tree for file count/bytes, then moves (os.rename, falling back to
  copy+rmtree across filesystems) or copies (shutil.copytree with a progress-tracking
  copy_function) the folder, updating files_done/bytes_done as it goes.
Changed: backend/app.py: `/api/pipeline/file` replaced by `POST /api/pipeline/file/start`
  (returns immediately) and `GET /api/pipeline/file/status` (poll for progress + result).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile() now starts the
  job and polls status every 400ms, storing progress on the row (`fileProgress`). Added
  FileProgressBar component — shown in the Collect detail panel's "File into collection"
  banner and in the table row's action cell while filing is in progress, so large
  copy/move operations no longer look like nothing is happening.
Changed: gui_next/src/renderer/src/locales/*.json: added pipeline.file.progress.{scanning,
  copying,moving} strings (all 6 languages).
Changed: PROJECT.md: updated Collection Routing & Pipeline Filing API table.

[2026-06-11] — fix(backend): db — BUG-160 rename_history.renamed_at now stored in local time
Fixed: backend/db.py: add_rename_history() now writes an explicit local-time timestamp instead
  of relying on SQLite's CURRENT_TIMESTAMP default (which is UTC). init_db() runs a one-time
  migration (meta key rename_history_localtime_v1) converting existing renamed_at values from
  UTC to local time via datetime(renamed_at, 'localtime').
Changed: PROJECT.md: rename_history.renamed_at column note updated.

[2026-06-11] — chore(gui): pipeline — drop inaccurate "reversible for 30 days" claim
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: all "Logged to rename_history"
  notes (Rename and Collect tabs) no longer claim a 30-day reversal window, since
  rename_history has no time-based retention/auto-purge (purge is manual and deletes all
  rows).

[2026-06-11] — fix(backend): lbdir — BUG-159 whitelist extras/ and rename_log.txt for green status
Fixed: backend/checksum_utils.py: verify_folder_lbdir() no longer counts files under `extras/`
  (created by /api/lbdir/move_extras) or `rename_log.txt` (written by write_rename_log) as
  "extra". If those are the only unclaimed files, status now resolves to 'pass' so the lbdir
  step (pipeline step 4) turns green once a folder has been reconciled. Added
  `_is_reconciled_extra()` helper plus `RENAME_LOG_NAME`/`EXTRAS_DIRNAME` constants.

[2026-06-11] — fix(backend+gui): lbdir — BUG-158 detect extra files on disk during lbdir check
Fixed: backend/checksum_utils.py: verify_folder_lbdir() now scans the folder recursively for
  files not claimed by any lbdir md5/ffp/shntool entry (excluding the manifest itself), adds
  them to `files` with overall='extra', and reports a real `extra` count instead of a hardcoded
  0. New 'extra_files' status is returned when checksums otherwise pass but stray files exist,
  so the folder no longer shows green/Pass while hiding extras.
Changed: backend/app.py: pipeline lbdir step now maps 'extra_files' to a "warn"/"Extra N" label
  and includes `extra` in the check detail.
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: LbdirState gains 'extra_files'; CheckResult
  gains `extra: number`.
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx,
  gui_next/src/renderer/src/screens/ScreenPipeline.tsx: STATE_LABEL entries for 'extra_files'
  (warn tone). Since it's not 'pass', the existing canReconcile gate now triggers the
  reconcile/move-to-extras flow for extra-only folders.
Fixed: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: LbdirFileTable rows with
  overall='extra' now render as a "warn" Extra pill instead of a red "Fail".

[2026-06-11] — fix(gui): pipeline — BUG-157 My Collection screen now refreshes after filing a folder
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile now calls
  queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] }) on a successful
  /api/pipeline/file result, so a folder filed from the pipeline (e.g. LB-16298) appears
  immediately in My Collection instead of requiring an app restart to refresh the stale
  staleTime: Infinity react-query cache.

[2026-06-11] — fix(gui): pipeline — BUG-156 folder no longer shows "In collection" before it's actually filed
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: serverRowToPipeline reclassifies bucket
  'done' as 'shelf' when the file (Collect) step status is 'warn' (ready to file, not yet filed) —
  fixes status column showing "In collection · Filed to DYLAN1" and the header "1 in collection"
  pill while the detail panel's Collect stage still shows "Action — File into collection". Folder
  now correctly shows "Ready to file" and counts toward the shelf/"File all N into collection"
  group until the Collect step actually runs.

[2026-06-10] — docs(gui): diagnosed BUG-154 — stale tsc-emitted .js files shadow .tsx sources, app ran pre-BUG-149 pipeline code
Added: BUGS.md: BUG-154 (Open) — 45 untracked compiled .js files under gui_next/src/renderer/src (tsc emit, 2026-06-10 17:09) shadow the .tsx sources; Vite resolves .js before .tsx so the running app lacked the BUG-149/151/152/153 fixes (rename/lbdir/file mute, statuses cleared on navigation). Backend verified correct via direct /api/pipeline/run + /api/folder/rename on the Munich example folder.
Added: BUGS.md: BUG-155 (Open) — entries.location for LB-16298 is "Mnchen, Germany" (ü dropped, cp1252 decode suspect); pipeline proposes misspelled rename.
Added: tools/debug_pipeline_rename.json: browser_driver session reproducing the pipeline rename stall (add Munich folder → wait for LB# → open Rename stage).

[2026-06-10] — fix(gui): pipeline — step results persist across tab navigation; partial-step runs no longer wipe steps
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added module-level _pipelineCache (Map keyed by folder path); updateRow writes to cache on every result, queue sync restores from cache on component remount — results survive tab navigation within the session
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: queue sync effect now schedules auto-run for unprocessed (all-mute) rows, so folders already in the queue on page load/tab-return run automatically when auto-run is on
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: runSteps and refreshDetailRow now preserve existing step results for stages not included in the requested steps list — "Check rename" no longer resets Verify/Lookup to mute
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: auto-complete effect detects rows where lookup=ok but rename=mute and automatically runs remaining steps
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: cache cleared on queue Clear and on individual row removal; folder path updated in cache on rename apply

[2026-06-10] — fix(gui): pipeline — per-stage re-run buttons now include lookup so lb_number resolves
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Check rename", "Re-check" (rename/lbdir/file), "Check route now" buttons were sending only their own stage to the backend; since the backend rebuilds everything from scratch, lb_number was always None → rename/lbdir/file stayed mute. All 7 per-stage re-run calls now include 'lookup' in the steps list.

[2026-06-10] — fix(backend+gui): pipeline — false "In collection", mute rename, lbdir retrieve with no LB in folder name
Fixed: backend/app.py: severity logic now returns "attn" (not "done") when lookup resolved an LB# but rename or lbdir steps are still mute (not yet run) — prevents folder from being classified as "In collection" too early
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: auto-run now fires all 5 steps (verify+lookup+rename+lbdir+file) instead of only verify+lookup — rename and lbdir were always mute for auto-dropped folders
Fixed: backend/app.py: lbdir_retrieve now accepts an optional lb_number_hint in the request body; falls back to it when neither my_collection nor folder name contains an LB# — allows "Retrieve sidecar now" to work for un-renamed folders whose LB was resolved by lookup
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: handleRetrieve passes lb_number_hint from row.steps.lookup.lb_number when calling /api/lbdir/retrieve

[2026-06-10] — feat(gui+backend): pipeline v2 phase 6 — polish: running progress, shntool state, collect pass rows, tooltips
Changed: backend/app.py: pipeline verify step now handles shntool_missing status from verify_folder (was falling through to bad/Mismatch); returns {status: "warn", label: "No shntool", shntool_missing: true}
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: VerifyStageContent — running-state banner when step is mute+row.running ("Hashing files…"); shntool-missing banner when step.shntool_missing; shntool_missing added to StepResult interface
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: CollectStageContent pass state — LB#/Mount detail rows added below "Added to collection" banner
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: title= tooltips on all re-run/re-check/re-verify buttons ("Re-run this stage"), Copy diff ("Copy to clipboard"), and DetailPanel Open button ("Reveal folder in Finder")

[2026-06-10] — feat(gui+backend): pipeline v2 cleanup phase 5 — Collect mount picker + tag table
Added: backend/filer.py: get_mounts_with_stats() returns collection_mounts with span (decade
range from collection_routes), free (human-readable via shutil.disk_usage), and online
(_path_reachable); new helpers _human_bytes() and _year_span_label()
Changed: backend/filer.py: resolve_destination_for_lb() and file_folder() take an optional
mount_id_override — when set and different from the year-routed mount, files under that
mount's root while keeping the routed sub_path (year subfolder)
Changed: backend/app.py: _pipeline_process_folder() Step 5 "file" result now includes mounts,
recommended_mount, routed_year, and collection_count when the folder is ready to file;
/api/pipeline/file and /api/pipeline/file/preview accept an optional mount_id per folder item
and pass it through as mount_id_override
Added: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: new shared component —
MountPicker (storage-mount picker grid with span/free/"suggested" pill, routed-by-year pill,
"Reset to suggested") and TagTable ("Tag in the collection" preview rows with live item
counter), composed by CollectDetail
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: StepResult/normalizeFileStep
gain mounts/recommended_mount/routed_year/collection_count; new CollectReadyDetail component
renders the route card + <CollectDetail> and live-previews the destination via
/api/pipeline/file/preview when the user picks a different mount; onFile/applyFile now accept
an optional mountId, forwarded to /api/pipeline/file as mount_id when it differs from the
recommended mount
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: pipeline.collect.* strings
(storageMount, routedByYear, resetToSuggested, suggested, mountOffline, mountTooltip,
freeAmount, tagInCollection, itemsCounter, row*/value* tag-table labels) — de/fr/es/it/nl
translated by hand this session (DeepL API key returned AuthorizationException: key disabled)
Fixed: gui_next/src/renderer/src/components/pipeline/CollectDetail.tsx: MountPicker now
disables radio selection on offline mounts (greyed out, "Offline" label) — previously a user
could select an unreachable mount and the live preview would silently fail, leaving the
picker and route card out of sync
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: CollectReadyDetail's "File into
collection" button is disabled while a mount-override preview is pending/unresolved, and now
passes the previewed dest/mount_label through onFile/applyFile so the confirm dialog shows
the destination that will actually be used (previously showed the recommended mount's
dest/label even when a different mount was selected)

[2026-06-10] — feat(gui): pipeline v2 cleanup phase 4 — harvest LbdirDetail into pipeline LBDIR panel
Added: gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx: new shared component —
CheckDot, LbdirFileTable (resizable Filename/MD5/Disk/Overall/Length/Fmt/Ratio columns), and
ReconcilePanel (rename proposals, extras-to-/extras/, and site/files recovery section), composed
by LbdirDetail with a compact prop, harvested from ScreenLBDIR.tsx
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: removed inline CheckDot,
ReconcilePanel, file table, and column-resize state; now renders the shared <LbdirDetail>
non-compact; no behavior change
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LbdirStageContent's truncated
12-row file list and reconcile block (which lacked the site/files recovery section) replaced
with <LbdirDetail compact> — the pipeline LBDIR panel now shows the full file table and full
reconcile UI matching the standalone LBDIR screen

[2026-06-10] — chore(gui+docs): data-testid hooks for nav/stage tabs + GUI verification gotchas
Added: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageStepper tab buttons get
data-testid="stage-tab-{verify|lookup|rename|lbdir|file}"
Added: gui_next/src/renderer/src/components/AppShell.tsx: main sidebar nav buttons get
data-testid="nav-{id}"; Advanced Tools sub-nav (Verify/Lookup/Rename/LBDIR) get
data-testid="nav-adv-{id}"
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: Quick Lookup sidebar button gets
data-testid="sidebar-quick-lookup"
Changed: .claude/CLAUDE.md: new "Verification gotchas" subsection under GUI Verification —
prefer curl for data-shape checks, use data-testid selectors instead of :has-text() (which
case-insensitive substring-matched "Lookup" tab vs "Quick lookup" sidebar button this session),
Unicode ellipsis in button labels, wait-for over fixed waits, kill stray dev-server processes,
absolute paths for browser_driver.mjs
Note: prompted by a session retrospective — GUI screenshot verification looped for ~30min on
selector mismatches; these hooks + doc notes target that directly

[2026-06-10] — feat(gui+backend): pipeline v2 cleanup phase 3 — harvest LookupDetail into pipeline lookup panel
Added: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: new shared component —
LookupSummaryTable (per-LB summary with category pill, alias-canonical pill, optional "Pin {lb} &
continue" column), LookupChecksumTable (grouped per-checksum detail with xref column), and
LookupNotFoundHint, harvested from ScreenLookup.tsx; also exports STATE_TONE/apiStatusToState/
categoryPill/LookupState for reuse
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: replaced inline summary/checksum
tables and status-tone helpers with the shared LookupDetail components; no behavior change
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LookupStageContent now renders
LookupDetail scoped to the active folder — matched state shows category pill + {matched}/{given}
stat; ambiguous (Conflict) state shows "Which show is this?" + per-LB "Pin {lb} & continue" wired
to PUT /api/folder_link (writes folder_lb_link, then re-runs lookup); not-found state shows the
shared checksum table + not-found hint; StepResult gains summary/detail fields
Changed: backend/app.py: _pipeline_process_folder lookup step now calls database.lookup_checksums
to get (summary, detail), annotates detail with is_alias_lb/canonical_lb via
database.get_lb_aliases(), includes summary/detail in the lookup result for all branches, and
honors an existing folder_lb_link pin (wins over raw checksum match set) to resolve ambiguity
Note: design doc 14 §2.2/§3 "Mark as new entry…" button intentionally not implemented — no
backend support exists yet for creating new lb_master entries (would be a no-op stub)

[2026-06-10] — chore(gui): replace Electron GUI driver with headless-Chromium browser driver
Added: tools/browser_driver.mjs: Playwright Chromium driver for GUI verification — same
session JSON / CLI shape as the old gui_driver.mjs (screenshot, navigate, click, fill,
eval, session); spawns `npm run dev` (or `npm run preview` with --preview), stubs
window.api (Electron preload bridge) via addInitScript, no Electron/Xvfb/display needed
Removed: gui_next/gui_driver.mjs: Electron+Playwright+Xvfb driver — consistently failed
in this sandbox (Electron CDP target never connects / GTK aborts under headless ozone);
replaced entirely by tools/browser_driver.mjs
Changed: .claude/CLAUDE.md: GUI verification section now documents tools/browser_driver.mjs
and the requirement to start the Flask backend first so the splash clears quickly
Changed: .claude/settings.json: pre-approved Bash rule updated from gui_driver.mjs to
tools/browser_driver.mjs
Changed: package.json/package-lock.json (root): added playwright devDependency (Chromium
browser binary cached via `npx playwright install chromium`)

[2026-06-09] — fix(gui): pipeline screen — remove filter chips, fix column alignment, wire auto-run
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: (1) removed bucket filter Chip bar from content area; (2) added missing 3px edge-bar <th> spacer to thead so headers align with data rows; (3) wired autorun toggle — addFolders now queues new folder IDs in autorunPendingRef and a useEffect drains the queue via runSteps(['verify','lookup']) once rows state settles

[2026-06-10] — feat(gui): pipeline progress banner — bucket pills, auto-run toggle, correct CTAs
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: replaced old banner right-side (bulk menu + conditional CTAs) with: (1) interactive bucket filter pills — one per non-zero bucket (needs/ready/running/shelf/done), clicking toggles table filter, correct labels/tones per spec; (2) auto-run toggle — sliding pill, default on; (3) "Apply all N ready" — always visible, disabled when 0; (4) "File all N into collection" — only shown when shelf > 0; removed dead bulkMenuRef/bulkMenuOpen state and click-away handler; title now "Pipeline · N folders" with fixed subtitle
Changed: gui_next/src/renderer/src/locales/en.json: added titleFolders, autoRun, autoRunHint, applyAllReady, fileAllCollection keys; updated filter.done to "In collection"

[2026-06-09] — fix(gui): pipeline v2 rename panel — full content (Issue 9); applyRename accepts custom name
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: RenameStageContent replaced with full panel — StageHead (state badge, title, LB# pill, Edit name… button), wrong-LB amber banner (auto-detected from folder name vs lookup LB#), diff box (red/green rows; green becomes input in edit mode, with LB# highlighted/struck-through), dry-run info banner with Copy diff, success banner after apply; onRename threaded as (customName?) so edited name reaches applyRename; Issue 8 already resolved (step key 'file' correct throughout)

[2026-06-09] — feat(gui): guaranteed fresh backend on every `npm run dev` launch
Changed: gui_next/src/main/index.ts: added killPortProcess() — after killStalePid(), scans port 5174 with lsof (Linux/Mac) or netstat (Windows) and kills any occupying process before spawning the backend; ensures stale backends started outside Electron are always evicted

[2026-06-09] — fix(gui): pipeline v2 UX corrections — detail layout, nav, queue rail, table columns
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: detail panel now replaces main content area instead of opening as a narrow right drawer (Issue 1); removed Run On Selected panel + singular Add Folder + shallowScan checkbox from queue rail footer; added Scan/Clear two-column grid, Quick Lookup button-link, and drag hint box (Issue 3); added Status column (deriveFolderStatus + StatusTag + reason) between Stages and LB# in batch table (Issue 6); colgroup updated to 7 columns; spacer/grouprow colSpan updated accordingly
Fixed: gui_next/src/renderer/src/components/AppShell.tsx: Verify/Lookup/Rename/LBDIR moved under collapsible "Advanced tools" disclosure (starts closed); removed Quick Lookup from sidebar nav (Issue 4)
Fixed: gui_next/src/renderer/src/locales/en.json + de/es/fr/it/nl: filter.needs → "Needs you"; filter.ready → "Ready to apply"; filter.shelf → "Ready to file"; runHint updated to remove "Run all 5 steps" reference; added advancedTools nav key (Issues 5, 7)

[2026-06-09] — docs: pipeline v2 phase 9 — documentation and verification
Changed: PROJECT.md: added collection_mounts + collection_routes schema tables; added "Collection Routing & Pipeline Filing" API section (10 routes); updated ScreenPipeline to 5-step; added ScreenQuickLookup entry; added Change Log row
Changed: instructions/pipeline_new/CHECKLIST.md: phases 9 items ticked off

[2026-06-09] — feat(gui): pipeline v2 phase 8 — Quick Lookup screen
Added: gui_next/src/renderer/src/screens/ScreenQuickLookup.tsx: new screen — paste input, clipboard button, drag-and-drop .md5/.ffp zone, results table (Checksum | Filename | LB# | Status)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added quicklookup nav entry under Ingest group
Changed: gui_next/src/renderer/src/App.tsx: added /quicklookup route and import
Changed: gui_next/src/renderer/src/locales/*.json: added appShell.nav.quicklookup and quickLookup namespace to all 6 locales

[2026-06-09] — feat(gui+backend): pipeline v2 phase 7 — stage detail panels
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: replaced GenericStageContent stub with four dedicated stage panels — VerifyStageContent (stats grid, no-checksums generate flow, re-verify), LookupStageContent (LB# matched card, conflict/not-found states, re-run), RenameStageContent (current/proposed diff view, apply rename button), CollectStageContent (route box staging→destination, error-code cards for no_date/no_route/mount_offline/dest_exists/db_error, filed success card); DetailPanel gains onRename prop wired to applyRename callback
Changed: backend/app.py: _pipeline_process_folder verify step now includes total/pass/missing/mismatch/extra/no_checksums counts in the step result dict

[2026-06-09] — feat(gui+backend): pipeline v2 phase 6 — Collect step wired into pipeline screen
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added 5th step column "Collect" with StepPill; "File" action button per-row (opens confirm dialog, calls /api/pipeline/file); "File selected" bulk button in selection bar; "File all ready" button in header; "Collect" individual run button in queue rail; "Run All" now runs all 5 steps; ConfirmDialog for file action shows dest path and mount; severity 'blocked' escalates to attn; right-click context menu wired via onContextMenu on TR rows; filter chip and group row labels now use t() with new pipeline.filter.{needs,ready,running,shelf} i18n keys; "File into Collection" action button in detail panel file stage
Changed: backend/app.py: _pipeline_process_folder severity — file_status=='blocked' now escalates to 'attn'; comment explains why 'ready' does not
Added: gui_next/src/renderer/src/components/pipeline/ConfirmDialog.tsx: useConfirm integration in ScreenPipeline
Changed: gui_next/src/renderer/src/locales/en.json + de/fr/es/it/nl: new keys — pipeline.table.collect, pipeline.file.*, pipeline.queue.collect, pipeline.fileAllReady, pipeline.selection.fileSelected; queue.runAll and runHint updated to "5 steps"; ingestDesc updated to include collect step; pipeline.filter.{needs,ready,running,shelf} added for bucket filter chips

[2026-06-09] — feat(backend+gui): Pipeline v2 — Step 5 File into Collection + Mounts & Routes
Added: backend/filer.py: year extraction, route resolution, timeout-guarded mount reachability check, move/copy filing, my_collection registration
Added: backend/db.py: collection_mounts, collection_routes tables + schema migration guards + meta key pipeline_file_mode; DB helper functions for all CRUD
Added: backend/app.py: 10 new API routes (/api/collection/mounts, /api/collection/routes/*, /api/collection/routes/preview/*, /api/pipeline/file, /api/pipeline/file/preview); pipeline_file_mode in db_settings; step 5 in _pipeline_process_folder
Added: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StateGlyph, StatusTag, StageNode, StageTracker, StageStepper, QueueRow
Added: gui_next/src/renderer/src/components/pipeline/ConfirmDialog.tsx: useConfirm hook, ConfirmDialog, ConfirmDialogProvider
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: CollectionRoutingCard (Mounts, Year Routes, Coverage bar, Preview tester, Filing Mode)

[2026-06-09] — chore(backend): set up ruff linter + pre-commit hook
Added: pyproject.toml: ruff config (E/W/F/I/UP/B/G/LOG, line-length 100, py311, excludes gui/ and tools/)
Added: .pre-commit-config.yaml: local pre-commit hook running ruff check --fix on staged Python files
Added: requirements-dev.txt: pinned ruff==0.15.16 and pre-commit==4.6.0
Changed: backend/: 102 auto-fixes applied (import ordering, deprecated typing imports, OSError aliases, unused imports, f-string cleanup, missing newlines)
Changed: BEST_PRACTICES.md: added §13 Tooling Setup (install steps, ruff rules table, config file reference)

[2026-06-09] — docs: expand BEST_PRACTICES.md with external standards and references
Added: BEST_PRACTICES.md: structured logging with extra=, TypedDict for dict-heavy return types, exception chaining (PEP 3151), pytest parametrize guidance, external references table (PEP 8/257/484/585/604/655/673/3151, Google style guide, Logging HOWTO/Cookbook, pytest docs, Effective Python)

[2026-06-09] — docs: add BEST_PRACTICES.md — Python conventions reference for this project
Added: BEST_PRACTICES.md: covers logging, type hints, docstrings, DB access patterns, error handling, threading, Flask routes, testing, and a pre-PR checklist

[2026-06-09] — perf(gui): Map — Canvas renderer + compositor layer promotion reduce pan/zoom lag
Changed: gui/resources/map.html: pass preferCanvas:true to L.map() so Leaflet uses Canvas instead of SVG for marker rendering; SVG DOM is O(n) with marker count, Canvas is not
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: added transform:translateZ(0) to iframe style to promote it to its own GPU compositor layer, reducing repaint cost during interaction

[2026-06-09] — fix(gui): Map tiles offline — add error banner overlay when tiles fail to load
Fixed: gui/resources/map.html: captured tileLayer reference; added tileerror listener that shows a "Map tiles couldn't load — check your internet connection" banner (z-index 1000, pointer-events:none) anchored to the bottom of the map container; added tileload listener that clears it when tiles subsequently succeed (BUG-134)

[2026-06-09] — fix(gui): DB Editor pagination and action bar hidden until a table is selected
Fixed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: wrapped pagination row and action row in {currentTable && ...} so "Page 1/1 (0 rows total)" and all buttons (Commit, Discard, Delete Selected, Export CSV, SQL Query) no longer appear on initial load before any table is chosen (BUG-133)

[2026-06-09] — fix(gui): Attachments empty-state message no longer misleads after auto-load
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: added hasLoaded flag set in loadTree's finally block; empty-state now shows "Loading…" until first load completes, "No attachments cached yet" when the cache is genuinely empty, and "No matches" when a filter narrows an existing list to zero (BUG-132)

[2026-06-07] — fix(tapematch): year_run now skips dates with existing run folders in RUNS_DIR
Changed: tools/tapematch/tapematch_session.py: year_run() augments `done` set by scanning RUNS_DIR for folders named YYYYMMDD_HHMMSS_{date_iso}; catches dates whose DB insert failed or whose runs were archived without a successful observations.db entry

[2026-06-06] — fix(tapematch): OOM kill in Pass 4 + add per-run debug log
Fixed: tools/tapematch/tapematch/audio.py: resample_ratio now uses soxr instead of scipy.signal.resample_poly; soxr operates natively in float32 so the ~1.84 GB float64 intermediate (922 MB input copy + 922 MB output) is eliminated; peak per speed-correction call drops from ~2.3 GB to ~461 MB; falls back to resample_poly if soxr is unavailable; added sr parameter (default 16000)
Changed: tools/tapematch/tapematch/cli.py: pass sr to resample_ratio call in Pass 4; added _rss_mb()/_DebugLog helpers; added --debug-log PATH argument; log elapsed time + RSS at every pass boundary (INGEST per source, PASS1_DONE, ANCHORS, LAG_CURVES_START, MATRIX_START/DONE, each RESAMPLE event with ratio+ppm, FINGERPRINT_START, SECONDARY_START, LINEAGE_START, DONE)
Changed: tools/tapematch/tapematch_session.py: run_tapematch() replaced subprocess.run(capture_output=True) with Popen + line-by-line stream so tapematch progress and any crash output appear immediately in the terminal; removed redundant print(log_text) after the call; passes --debug-log last_debug.log to cli; archive_run() copies last_debug.log to debug.log in each run archive
Added: requirements.txt: soxr==1.1.0

[2026-06-05] — fix(tools): batch_verify --skip-done now auto-reprocesses api_error/retrieve_error
Changed: tools/batch_verify.py: --skip-done treats api_error and retrieve_error as transient (never skips them); updated help text and usage examples to remove api_error from --reprocess examples

[2026-06-05] — feat(tapematch): manual-dir mode for run.sh
Changed: tools/tapematch/run.sh: now calls tapematch_session.py --manual-dir instead of bare tapematch.cli, giving full post-processing (archive, observations.db, report)
Added: tools/tapematch/tapematch_session.py: run_manual() function + --manual-dir/--label/--date CLI args; root_dir parameter threaded through run_tapematch(), insert_sources(), insert_pairs(), _log_to_obs_db()

[2026-06-05] — fix(gui): Flask backend persists after Electron closes
Fixed: gui_next/src/main/index.ts: added PID file tracking so stale Flask processes from prior or hot-reloaded sessions are killed on startup; removed the port-open short-circuit that left backendProc=null when a prior backend was still running; before-quit now also clears the PID file

[2026-06-05] — fix(tapematch): OOM kill in Pass 1 on dates with 6+ sources
Fixed: tools/tapematch/tapematch/cli.py: changed ingest to mono=True always; to_mono() now returns a zero-cost view instead of a ~388 MB copy; trimmed slice written directly to memmap via ravel() view with no intermediate heap array; peak per source drops from ~1.2 GB to ~500 MB (BUG-144)
Changed: tools/tapematch/config.yaml: marked mono_mix as unused

[2026-06-05] — fix(backend): extend apostrophe normalisation to lbdir verify path (BUG-143)
Fixed: backend/checksum_utils.py: parse_lbdir_file now applies _norm_fname() to all parsed filenames (md5/ffp/shntool/shntool_len sections); verify_folder_lbdir replaces bare folder/fname lookup with a normalised _disk_audio_map (relpath→Path) and normalised _subdir_index (basename→Path), matching the same apostrophe-safe pattern as verify_folder

[2026-06-05] — fix(backend): Verify fails to match filenames with curly apostrophes
Fixed: backend/checksum_utils.py: added _norm_fname() to translate typographic apostrophes (U+2018/2019/etc.) → straight apostrophe before building disk_audio_map keys and before storing parsed checksum filenames; prevents mismatch when checksum files use smart-quotes but disk files use straight apostrophes (BUG-143)

[2026-06-05] — fix(backend): pipeline apply-rename missing rename_log.txt and rename_history row
Fixed: backend/app.py: folder_rename route now calls write_rename_log(source='pipeline') before os.rename(), writing rename_log.txt into the folder and inserting a rename_history row (BUG-142)

[2026-06-05] — feat(pipeline+gui): LBDIR retrieve+check in pipeline step 4 with inline reconcile panel
Changed: backend/app.py: _pipeline_process_folder lbdir step now retrieves lbdir*.txt from attachments cache (scraping if needed) and runs verify_folder_lbdir; returns check summary (status/total/pass/missing/mismatch) instead of bare presence flag
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: LbdirMiniPanel slide-in right panel shows check stats, per-file status table, reconcile proposals and apply workflow; "LBDIR" action button appears in any pipeline row whose lbdir step is not Pass; action column widened to 172px to fit two buttons

[2026-06-05] — fix(backend): Verify shows shntool-format FLAC checksums as missing duplicates
Fixed: backend/checksum_utils.py: _parse_checksum_file now strips [shntool] prefix from MD5-regex captures and reclassifies as shntool type, preventing bogus "[shntool] filename.flac" entries that don't match disk files (BUG-141)

[2026-06-05] — fix(gui): Lookup folder added once showing twice in sources list
Fixed: ScreenLookup.tsx: handleSingleFolder and handleFolders now guard against duplicate adds by checking sources by path before calling addSource; useEffect queue-sync callbacks also re-check after async fetch resolves to prevent race where a folder already added manually gets added again by the sync

[2026-06-05] — fix(gui): Rename screen always showed "No match" for folder sources that matched in Lookup
Fixed: ScreenLookup.tsx + lookupStore.ts: folder sources now store their full path; handleLookupAll builds a checksum→folder map so detail rows are tagged with source_file (full path) after lookup; without this, buildProposals could never map checksums back to folder paths and showed no_match for every row
Fixed: ScreenRename.tsx: buildProposals now compares the matched LB# against LB numbers already in the folder name; a different existing LB# shows wrong_lb state instead of incorrectly showing has_lb

[2026-06-05] — fix(gui): shared folder queue — bidirectional clear sync across Pipeline, Verify, LBDIR, Spectrograms
Fixed: ScreenPipeline.tsx: sync effect now handles removals bidirectionally — clearing on Verify/LBDIR/Spectrograms now also clears Pipeline rows (previously only additions were synced)
Fixed: ScreenPipeline.tsx: applyRename() now updates folderQueueStore with renamed path so the sync effect stays coherent after a rename
Added: FolderQueueRail.tsx: shared sidebar component (header, filter, scroll area, consistent Clear button + onClear callback for screen-specific state reset)
Changed: ScreenVerify.tsx: replaced inline aside with FolderQueueRail; removed redundant clearFolders destructure
Changed: ScreenLBDIR.tsx: replaced inline aside with FolderQueueRail; onClear resets activeFolder; removed redundant clearFolders destructure
Changed: ScreenSpectrograms.tsx: replaced inline aside with FolderQueueRail (adds Clear list button that was missing); onClear resets activeFolder+activeTrack; added useEffect to reset activeFolder when removed from queue on another screen
Changed: components/index.ts: export FolderQueueRail

[2026-06-05] — fix(backend): lookup duplicate resolution — show all equally-complete matches as Matched
Changed: backend/db.py: when a checksum appears in multiple LBs and all are fully complete, promote all to MATCHED (green) instead of leaving them as DUPLICATE (yellow); per-LB duplicates count still reflects the overlap

[2026-06-05] — feat(gui): clear-list button + right-click remove on all 5 pipeline screens
Added: ScreenPipeline.tsx: right-click queue item → "Remove from list" context menu; "Clear list" replaces clearQueue label
Added: ScreenVerify.tsx: "Clear list" trash button in rail; right-click folder row → remove
Added: ScreenLBDIR.tsx: "Clear list" trash button in rail; right-click folder row → remove
Added: ScreenLookup.tsx: right-click source row → remove single source; existing "Clear sources" button unchanged
Added: ScreenRename.tsx: "Clear list" button in header clears folderList; right-click table row → remove that folder
Added: lookupStore.ts: removeSource(idx) action with active-source index adjustment
Added: locales/en|de|fr|nl|it.json: common.clearList + common.removeFromList keys

[2026-06-04] — feat(gui): add single-folder button to all 5 pipeline screens
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Add folder…" button (pickDir → add directly, no tree scan) in queue rail
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: "Add folder…" button in rail bottom section
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: "Add folder…" button in rail bottom section
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: "Add folder…" button (full-width, spans 2 cols) in sources grid; scans folder via /api/lookup/scan_folders
Added: gui_next/src/renderer/src/screens/ScreenRename.tsx: "Add folder…" button in header; adds path to lookupStore.folderList so rename proposals are built for that folder
Added: locales/en|de|fr|nl|it.json: common.addFolder key

[2026-06-04] — fix(gui): Rename screen folder list never populated from folder scans
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: handleFolders now pushes scanned folder paths into folderList via setFolderList; queue-sync effect does the same for queue-pushed folders; runLookup no longer overwrites folderList with an empty array (source_file is never set by /api/lookup so the derived list was always [])

[2026-06-04] — fix(gui): LBDIR renames table column misalignment
Fixed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: colgroup had 6 <col> entries but TR auto-injects a 3px edge bar making 7 columns — disk_rel path was squeezed into the 24px arrow column; added 7th <col style={{width:32}}/> for the checkbox and matching <TH> in header

[2026-06-04] — fix(backend): combined-set lookup INCOMPLETE and lbdir bare-filename matching failures
Fixed: backend/db.py: _norm_track_base() strips directory prefix and normalizes & → _ before grouping DB checksums by track; BUG-130's fix was ineffective for SHN sets where the DB stored Disc1\dead&dylan.shn (md5) and dead_dylan.wav (shntool) as separate base keys — both now map to the same track, so LB-1332 correctly shows MATCHED instead of INCOMPLETE
Fixed: backend/checksum_utils.py: verify_folder_lbdir _norm now uses basename only; adds audio-only subdirectory fallback so bare-filename lbdirs (e.g. LBF-01334 with dead&dylan2003.8.06.d3t01.shn) resolve against Disc3/ entries in a combined multi-LB folder without ambiguously matching non-audio files like checksum.md5

[2026-06-04] — fix(lbdir): phantom "Missing" rows for SHN sets stored in disc subdirectories
Fixed: backend/checksum_utils.py: parse_lbdir_file now extracts the subdirectory context from shntool section headers (e.g. "=== shntool md5/hash for: archive\Disc1") and prepends it to every file entry in that section; without this, shntool entries for multi-disc SHN sets had no directory prefix and failed the _norm remap against the md5_map's Disc1/dead&dylan2003.* keys, producing 26 phantom "Missing" rows

[2026-06-04] — feat(search): right-click context menu with "Go to LB webpage" option
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: right-clicking any row opens the row menu at the cursor position; "Go to LB webpage" opens the LosslessBob detail URL in the browser

[2026-06-04] — fix(collection): View LB Entry opens webpage instead of navigating to lookup screen
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: handleCtxViewLookup was navigating to /lookup instead of opening the LB entry URL; also removed incorrect diskPath guard that disabled the menu item for unowned entries

[2026-06-04] — fix(lookup): group checksum detail by LB; filter non-audio entries from parser
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: checksum detail table now renders a group header row per LB when multiple LBs are present
Fixed: backend/db.py: parse_checksum_text — MD5/SHA1 entries for non-audio files (.txt, .rtf, .html, etc.) are now skipped; previously these appeared as spurious "Not found" rows in lookup results

[2026-06-04] — chore(tools): move tapematch runs/ to data/tapematch/runs/
Changed: tools/tapematch/tapematch_session.py: RUNS_DIR now points to PROJECT_ROOT/data/tapematch/runs — user data kept out of repo tree
Changed: tools/tapematch/gen_analysis.py: RUNS_DIR updated to match new location
Changed: .gitignore: removed stale tools/tapematch/runs/ entry (/data already covers it)

[2026-06-04] — feat(backend+gui): duplicate LB alias integration across all workflows
Changed: backend/db.py: get_missing_from_collection() — exclude alias partners of owned LBs via NOT EXISTS subqueries; get_collection() — annotate each row with linked_lbs list (bidirectional)
Changed: backend/app.py: /api/lookup route — annotate detail entries with is_alias_lb/canonical_lb; _pipeline_process_folder() — resolve aliases before single/conflict check, store alias_resolved_from; lbdir_retrieve() — cascade fallback to canonical LB when alias has no lbdir attachment
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: LookupDetail — add is_alias_lb, canonical_lb fields
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: show ≡ LB-XXXXX badge on summary rows matched to alias LBs
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: StepResult — add alias_resolved_from field; show ↩ alias note in LB label cell when alias was resolved
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: CollectionRow — add linkedLbs field; show ↔ LB-XXXXX pill in detail panel for entries with linked LBs

[2026-06-04] — chore(dev): Playwright GUI driver for automated screenshots and UI interaction
Added: gui_next/gui_driver.mjs: Playwright-based Electron driver; actions: screenshot, navigate, click, fill, eval, session; auto-starts Xvfb when $DISPLAY is unset; waits for splash overlay to detach before acting
Added: tools/debug_screens.json: session file that screenshots all main screens
Changed: gui_next/src/renderer/src/components/SplashOverlay.tsx: added data-testid="splash-overlay" so driver can reliably detect when splash has cleared
Changed: .claude/settings.json: pre-approved Bash rules for gui_driver.mjs and npm build

[2026-06-04] — fix(gui): Lookup tab now syncs folders from the shared folder queue
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: imported useFolderQueueStore and added a useEffect that watches the shared queue; any folder added on other tabs is scanned and added as a source automatically

[2026-06-04] — feat(gui): LBDIR screen — hide-verified filter
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: "Hide verified" checkbox below the folder search input; when checked, folders with a stored lbdir_verified_at timestamp are excluded from both the listbox and the "Process all folders" operation; sidebar count shows filtered/total when active

[2026-06-04] — feat(tools): tapematch — 1987 analysis-driven diagnostic refinements
Changed: tools/tapematch/tapematch/cli.py: add --set-offset HH:MM:SS flag to clip all sources to a given start time (for co-headline shows where the target set starts mid-recording)
Changed: tools/tapematch/tapematch/cli.py: raise TIMING MISMATCH threshold from 3 min to 8 min; AUD recordings of the same show routinely differ by 3–6 min from crowd-intro variation
Changed: tools/tapematch/tapematch/cli.py: suppress TIMING MISMATCH for INFLATED-flagged sources (the existing [INFLATED] flag already covers the cause)
Changed: tools/tapematch/tapematch/cli.py: replace [low confidence] label with [fp-linked] when a family was assembled purely by fingerprint Dice evidence rather than primary STFT
Changed: tools/tapematch/tapematch/cli.py: add [chain-unverified] note to 3+ member families where at least one pair has only transitive evidence (A→B + B→C but A↔C not directly confirmed)
Changed: tools/tapematch/tapematch_session.py: pass --set-offset through run_date → run_tapematch; expose as CLI arg
Changed: tools/tapematch/tapematch_session.py: load results.json before build_report in both normal and --report-only paths; add _build_commentary_audit() which compares LB page "same recording as" claims against tapematch family assignments and appends an audit table to each report

[2026-06-03] — feat(tools): tapematch — 1989 log analysis + 5 diagnostic/algorithm improvements
Changed: tools/tapematch/tapematch/match.py: extend speed-ratio search to ±2.0% (was ±1.5%); many 1989 recordings sit at 14000–15000 ppm boundary
Changed: tools/tapematch/tapematch/cli.py: suppress TIMING MISMATCH warnings for INCOMPLETE-flagged pair members (removes ~200 redundant lines per year-run)
Changed: tools/tapematch/tapematch/cli.py: exclude INCOMPLETE/INFLATED sources from central-ref selection so anchors come from a well-formed recording
Changed: tools/tapematch/tapematch/cli.py: staircase short-window fallback triggers when EITHER source has splice edits, not both
Changed: tools/tapematch/tapematch/cli.py: [SECONDARY SAME-SOURCE] diagnostic distinguishes NR-processed pairs (music aligns, quiet-segment noise doesn't) from remasters

[2026-06-03] — test: regression tests for BUG-127, BUG-128, BUG-130
Added: tests/test_batch_verify.py: 8 tests for _map_verify_status (BUG-127) + 8 tests for has_lbdir LBF-format detection (BUG-128)
Added: tests/test_db_lookup.py: 4 tests for lookup_checksums SHN completeness grouping (BUG-130) — covers MATCHED, partial INCOMPLETE, and mixed .shn/.wav input

[2026-06-03] — feat(gui): Pipeline + Verify — "1 level only" checkbox for root folder scan
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: shallowScan state + checkbox below "Scan tree…" button; passes shallow: true to /api/pipeline/scan-tree when checked
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: same shallowScan toggle below "Add root folder…" button
Added: gui_next/src/renderer/src/locales/*.json: common.shallowScan key in all 6 locales

[2026-06-03] — fix(backend+gui): Lookup — SHN sets falsely shown as Incomplete/Not Found
Fixed: backend/db.py: completeness check now groups .shn/.wav (and any audio ext) entries by base filename; a matched MD5 of foo.shn covers the shntool checksum for foo.wav, so a full SHN set shows MATCHED instead of INCOMPLETE
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: apiStatusToState() now maps backend 'INCOMPLETE' → incomplete; previously fell through to notfound fallback showing red "Not Found" for SHN sets

[2026-06-03] — feat(backend+gui): LBDIR reconcile — recover missing files from site/files by MD5
Added: backend/checksum_utils.py: find_site_recoverable_files() — scans SITE_FILES_DIR for LBF-NNNNN-* files, matches by MD5 against still-missing lbdir entries
Changed: backend/app.py: /api/lbdir/reconcile appends site_proposals; /api/lbdir/apply_reconcile accepts site_copies and copies matched site files to folder (with SITE_FILES_DIR path guard)
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: SiteProposal type, site_proposals on ReconcileResult, siteSelected + setSiteSelected in store
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: ReconcilePanel "Recoverable from site/files" section with checkboxes; apply wires site_copies

[2026-06-03] — fix(backend+tools): lbdir_retrieve skips copy if lbdir already in folder; has_lbdir matches LBF-format files
Fixed: backend/app.py: lbdir_retrieve now checks for any existing lbdir in folder before copying from cache; previously always overwrote, so a cache update between batch_verify and clicking Process would silently swap in a different lbdir causing a false result change
Fixed: tools/batch_verify.py: has_lbdir used case-sensitive glob "lbdir*.txt" missing LBF-*-lbdir.txt files on Linux; now uses iterdir+lower() matching _find_lbdir_in_folder
Fixed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: pre-check folder dot now neutral gray instead of green for stale lbdir_verified_at; green reserved for live pass

[2026-06-03] — fix(tools): batch_verify — don't persist transient connection errors; add --purge-connection-errors
Changed: tools/batch_verify.py: process_folder Phase 1 — connection_error/timeout_error from _api_retrieve no longer written to DB; resume retries them
Changed: tools/batch_verify.py: process_folder Phase 2 — ConnectionError/Timeout from _api_verify no longer written to DB; resume retries them
Added: tools/batch_verify.py: purge_connection_errors() + --purge-connection-errors CLI flag to delete existing stale connection-error rows

[2026-06-03] — fix(backend): LBDIR reconcile — lbdir file itself no longer appears as an extra
Fixed: backend/checksum_utils.py: find_reconcilable_files — skip the lbdir file when building all_disk_rels so it no longer ends up in unmatched_disk and gets proposed for move to /extras/

[2026-06-03] — fix(gui+backend): LBDIR screen — shallow root-folder scan and resizable file-table columns
Changed: backend/app.py: pipeline_scan_tree — added shallow param; when true, only checks root + immediate subdirs (depth 1) instead of full rglob walk
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: handleAddRoot passes shallow:true to scan-tree; file detail table columns are now drag-resizable via startFileColResize + fileColWidths state

[2026-06-03] — feat(gui+backend): DB Editor — add batch_verify.db as selectable database
Changed: backend/paths.py: added BATCH_VERIFY_DB_PATH constant
Changed: backend/app.py: added _dbedit_db_path()/_dbedit_is_batchverify() helpers; all 7 dbedit routes accept ?db=batchverify param; batch_verify tables are all readonly; dbedit_query accepts db in POST body
Changed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: added activeDb state and switchDb(); db selector buttons above table list; all dbedit fetch calls pass ?db=; integrity/alias panels hidden for batch_verify; SqlQueryPanel receives db prop

[2026-06-03] — feat(gui): Collection screen — chip groups, additive Not-in-collection filter, column alignment fix
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Filter chips divided into three groups with separators (status, history, not-in-collection); "Not in collection" converted from primary filter to independent additive toggle (notOwned state); filteredMissingRows computed by lb_status when Public/Private filter is active; not-owned table uses filteredMissingRows; column alignment fixed by removing stray extra <TD /> from not-owned table body rows; Export CSV uses filtered rows; all filter === 'not_owned' guards replaced with notOwned boolean

[2026-06-03] — feat(gui): Collection screen — resizable columns + Public/Private filter chips + column picker
Changed: gui_next/src/renderer/src/components/table.tsx: TH now accepts onResizeStart prop; renders a col-resize drag handle on the right edge with hover indicator
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: FilterKey extended with 'public'/'private'; counts/filter logic added; Public and Private chips added after All chip; ColKey type + ALL_COLS/COL_LABELS/DEFAULT_COL_WIDTHS constants; colWidths Record + lbColWidth state; visibleCols persisted to localStorage (lbb_collection_cols); Columns popover in filter bar; table colgroup/thead/tbody conditioned on visibleCols; startColResize uses ColKey | 'lb'

[2026-06-03] — feat(gui): Collection screen — dynamic category filter chips
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: category chips now derived dynamically from categoryCounts (sorted by count) instead of hardcoded concert/interview; covers all types (concert, tv, studio, interview, compilation, rehearsal, radio, soundcheck)

[2026-06-03] — feat(gui): LBDIR screen — show prior lbdir-verified status in folder sidebar
Added: backend/app.py: POST /api/lbdir/verified_status — queries my_collection for lbdir_verified_at per folder path
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: added lbdir_verified_at to CheckResult type
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: loads verified_status on mount/folder-change; FolderSideRow shows faded green dot + "✓ YYYY-MM-DD" for folders with prior verification and no current check result

[2026-06-03] — refactor(gui): LBDIR screen — unified process flow, no sub-tabs
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: replaced 4 sub-tabs (Check/Retrieve/Reconcile/Extras) with a single Process action that auto-retrieves lbdir then checks; Reconcile button inline below file table; extras moved to /extras/ subfolder instead of deleted
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: removed tab/retrieveResults/extrasResults/extrasSelected state; added clearReconcileFor action
Added: backend/app.py: POST /api/lbdir/move_extras — moves extra files to <folder>/extras/ preserving relative path structure

[2026-06-03] — feat(tools): batch_verify l=full legend, e=expand toggle, updated progress
Added: tools/batch_verify.py: l key prints full status legend with definitions; e key toggles expanded progress mode (full status name + LB tag + folder name + pass/mismatch/missing counts); h key prints compact abbr legend; print_progress gains expanded kwarg

[2026-06-03] — feat(tools): batch_verify interactive keys (q/h/s) during run
Added: tools/batch_verify.py: _KeyboardController reads single keypresses via termios cbreak; q=clean quit after current folder, h=re-print abbr+key legend, s=live stats summary; terminal restored in finally block; no-op when stdin is not a TTY

[2026-06-03] — feat(tools): batch_verify compact progress output ≤30 chars/line
Changed: tools/batch_verify.py: print_progress replaced with compact format [i/total] {abbr} {lb} [{extra}]; status shown as 2-letter code (OK/FL/MF/NL/ER/etc.); extra shows proposal count (MF) or first 7 chars of notes (ER)

[2026-06-03] — feat(tools): batch_verify --skip-done flag + improved --help
Added: tools/batch_verify.py: --skip-done skips any folder with any existing result (vs --resume which only skips pass); --reprocess still overrides; grouped argparse help with examples and descriptions for every flag

[2026-06-03] — fix(tools): batch_verify misclassifies missing-file folders as api_error
Fixed: tools/batch_verify.py: _VERIFY_STATUS_MAP was missing "missing_files" key; verify_folder_lbdir returns "missing_files" (not "incomplete") when n_missing > 0, so all such folders fell through to STATUS_API_ERROR; added "missing_files" → STATUS_MISSING_FILES to the map

[2026-06-03] — feat(tools): tapematch iteration pass — six accuracy/quality improvements; threshold calibrated 0.35→0.50
Changed: tools/tapematch/config.yaml: max_lag_sec 30→90; local_lag_sec 5→10; short_window_sec/short_hop_sec added; fingerprint hf_band_hz [6000,8000] + cluster_threshold calibrated to 0.50 (empirical bimodal gap 0.47/0.51 confirmed across 3 dates)
Changed: tools/tapematch/tapematch/match.py: fingerprint_window slices STFT to hf_band_hz before peak-finding
Changed: tools/tapematch/tapematch/cli.py: staircase/staircase short-window fallback; cluster() wired to fingerprint (F=FP, fp_cluster_thr); will_merge uses fp_cluster_thr; [TIMING MISMATCH] diagnostic; diagnostic section renumbered
Changed: tools/tapematch/WORKFLOW.md: calibration table added; updated config knobs; updated failure mode table

[2026-06-03] — fix(tools): tapematch year_run spawns a fresh subprocess per date
Fixed: tools/tapematch/tapematch_session.py: year_run() now spawns tapematch_session.py <date> as a subprocess instead of calling run_date() in-process — each date's Python heap, page cache mappings, and OS resources are fully released when the subprocess exits; also added _clean_stale_tmp_dirs() in run_tapematch() to remove any tapematch_* memmaps left by OOM-killed subprocesses

[2026-06-02] — feat(gui): collapsible filter pane in Search screen
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: filterPaneOpen state; aside collapses to 32px strip with chevRight expand button; chevLeft button in open pane collapses it; 180ms CSS transition

[2026-06-02] — fix(gui): Search TYPE filter now shows all categories dynamically
Fixed: gui_next/src/renderer/src/screens/ScreenSearch.tsx:1009: hardcoded ['concert','interview'] replaced with dynamic list from facetCounts.categoryC sorted by count — tv, studio, compilation, rehearsal, radio, soundcheck were missing

[2026-06-02] — feat(tools): tapematch — year batch mode with resume support
Added: tools/tapematch/tapematch_session.py: get_year_dates(), run_date() (extracted from main), year_run() — --year YYYY flag loops all collected+paged dates for a year in chronological order, skipping dates already in observations.db; Ctrl+C prints resume command and exits cleanly; --min-entries N (default 2) controls minimum sources per date
Added: tools/tapematch/run_year.sh: convenience wrapper: ./run_year.sh 1995 [--dry-run]

[2026-06-02] — feat(tools): tapematch — INFLATED duration diagnostic
Added: tools/tapematch/tapematch/cli.py: flags sources with performance duration >30% above group median as [INFLATED?] in TRIM section and [INFLATED] in DIAGNOSTICS; mirrors existing INCOMPLETE flag; catches duplicate-track subfolders (e.g. "fixed tracks" copies) that corrupt correlation results

[2026-06-02] — fix(tools): tapematch — skip __MACOSX metadata files during ingest
Fixed: tools/tapematch/tapematch/ingest.py: list_tracks() now filters out ._-prefixed files and paths containing __MACOSX (AppleDouble resource forks created by macOS zip/copy); was crashing on LB-01961 (Brixton Academy 2003-11-25)

[2026-06-02] — fix(tools): tapematch — hiss-driven merge for staircase/CDR re-tracking pairs
Fixed: tools/tapematch/tapematch/match.py: cluster() now accepts H/H_med matrices; merges pair when hiss_frac >= hiss_merge_frac AND hiss_median >= hiss_merge_median (both required to block room-ambience false positives on modern digital recordings)
Fixed: tools/tapematch/tapematch/cli.py: track H_med matrix; pass to cluster(); SECONDARY MATCH label now says "→ SECONDARY LINK" only when merge will actually happen, "→ hiss evidence (below merge threshold)" otherwise
Changed: tools/tapematch/config.yaml: added hiss_merge_frac: 0.60, hiss_merge_median: 0.65 to secondary_match block; clarified hiss_frac_threshold as display-only

[2026-06-02] — feat(tools): tapematch report — enrich Coverage table + save analysis to run folder
Changed: tools/tapematch/tapematch_session.py: Coverage table now includes Rating, Timing, and source snippet columns from LB page; added _lb_source_snippet() helper; analysis.md written manually to run folder after each session
Added: tools/tapematch/runs/20260602_184543_1993-07-09/analysis.md: Claude analysis of 1993-07-09 La Coruna run

[2026-06-02] — feat(tools): tapematch fingerprint — Shazam-style spectral peak landmark matching
Added: tools/tapematch/tapematch/match.py: _stft_mag(), _find_peaks_2d(), fingerprint_window() — builds (f_anchor, f_target, Δt) hash set from 10-min reference window (skip first 3 min); offset-invariant by construction; fingerprint_score() — Dice coefficient between hash sets
Added: tools/tapematch/tapematch/cli.py: computes fingerprints for all sources upfront; adds fp_score to sec_results per cross-family pair; shows Dice score in SECONDARY MATCH and DIAGNOSTICS sections; does NOT drive clustering (confirmatory only)
Added: tools/tapematch/config.yaml: fingerprint block with window/nperseg/fanout/threshold knobs
Fixed: match_threshold raised 0.10→0.60 after discovering live recordings of the same concert score 0.15–0.50 (same musical notes → same Δt hashes); same-source confirmed pairs score 0.60–0.85; documented in config comment
Verified: 1996-07-21 Pori — LB-06986/LB-00513 scores Dice 0.695 (confirms windowed+hiss evidence); 9 different-source pairs score 0.19–0.49 (correctly below threshold); 4 families preserved

[2026-06-02] — feat(tools): tapematch secondary match — windowed coverage + quiet-segment hiss correlation
Added: tools/tapematch/tapematch/match.py: find_quiet_segments() — finds low-energy between-song sections from memmap-safe block reads; secondary_corr_pair() — dense 60s-window grid corr (per-window local lag ±5s, no speed-correction to preserve HF fine-structure) + quiet-segment hiss corr; cluster() extended with optional W/w_threshold for secondary linkage
Added: tools/tapematch/tapematch/cli.py: secondary match pass runs after primary matrix for cross-family pairs only; prints SECONDARY MATCH section; feeds W matrix into combined cluster(); annotates Family output with secondary evidence; adds [SECONDARY SAME-SOURCE] diagnostic; extends JSON output with secondary_matrix and secondary_pairs
Added: tools/tapematch/config.yaml: secondary_match block with windowed and quiet-segment knobs
Fixed: tools/tapematch/tapematch/cli.py: do NOT apply resample_poly before secondary_corr_pair — resample_poly smears HF fine-structure, killing residual_corr even for same-source pairs; windowed local lag search absorbs speed differences natively
Verified: 1996-07-21 Pori — LB-06986 (LTA remaster of LB-00513) now correctly grouped as Family 3 via windowed 0.69 / hiss 0.59; no false positives on remaining 9 cross-family pairs

[2026-06-02] — fix(tools): tapematch LB page relationship detection — bittorrent stripping + full text extraction
Fixed: tools/tapematch/tapematch_session.py: _page_text used regex tag-stripping which bled bittorrent description paragraphs (describing third-party uploads) into relationship search text; switched to soup.get_text() so bare text nodes between <hr/> separators (where "same recording as LB-XXXX" notes live) are included
Fixed: tools/tapematch/tapematch_session.py: added _strip_bittorrent_blocks() — balanced-paren walker that removes (a bittorrent from ...) parentheticals from curator text before relationship detection; prevents uploader-asserted "same as LB-XXXX" claims from polluting lb_says_same in observations DB
Fixed: tools/tapematch/tapematch_session.py: extract_lb_relationship returned None on first ambiguous LB-number mention (e.g. page header) without checking later occurrences; now iterates all matches and only returns None after exhausting them
Fixed: tools/tapematch/tapematch_session.py: "matching" keyword missed "fingerprints which match"; replaced keyword list with compiled regexes _SAME_RE / _DIFF_RE covering "fingerprints.{0,40}match", "eac match", "close match", "identical"

[2026-06-02] — tune(tools): tapematch cluster_threshold 0.55 → 0.45
Changed: tools/tapematch/config.yaml: cluster_threshold lowered from 0.55 to 0.45; motivated by 1998-10-28 LB-06564/LB-12485 (confirmed same DAT master, different transfer path — CDR trade copy vs fresh 2016 transfer) scoring 0.520 and being missed at 0.55; safety margin above highest observed different-source corr (0.362, 1995-07-08) is 0.083

[2026-06-02] — fix(tools): tapematch trim None crash + stale results.json on failed run
Fixed: tools/tapematch/tapematch/trim.py:63: performance_envelope computed end_i = len - 1 - _first_sustained(...) before checking for None; TypeError when no sustained tail region found (vinyl rips / recordings with no silence tail); split into end_raw variable, guard before arithmetic
Fixed: tools/tapematch/tapematch_session.py:669: stale last_results.json from a prior run was loaded in step 7 when tapematch crashed mid-run without writing new results; now unlinks the file before running tapematch so a crash leaves no stale data to pick up

[2026-06-02] — fix(tools): tapematch page parser + staircase message; private LB path filter; post-matrix central-source reference
Fixed: tools/tapematch/tapematch_session.py: extract_lb_commentary now falls back to first substantial <p> tag (most LB pages store commentary in <p>, not <td>); only LB-01863-style pages with "SOURCE:" text were parsing before
Fixed: tools/tapematch/tapematch_session.py: private LB exclusion changed from page-existence check to disk_path substring match ("PRIVATE", "NOTORRENT", "NO TORRENT") — correctly excludes entries that have a local page but private path
Fixed: tools/tapematch/tapematch/cli.py: removed pre-pass reference selection; post-matrix central-source selection via argmax(M.sum(axis=1)) guarantees selection of most-correlated source; pre-pass failed when median-duration source was a low-corr outlier (cassette)
Changed: tools/tapematch/tapematch/cli.py: staircase lag-curve annotation changed from "consistent with bootleg press or edited master" to neutral "staircase pattern (CDR re-tracking or tape edits)"

[2026-06-02] — feat(tools): tapematch workflow tooling — --suggest, private LB exclusion, smart reference, WORKFLOW.md
Added: tools/tapematch/tapematch_session.py: --suggest flag queries DB for 3–5 entry dates not yet analysed; private LBs (no local page) auto-excluded from runs; smart central-source reference selection (1-anchor pre-pass replaces alphabetical default)
Added: tools/tapematch/tapematch/cli.py: auto-select most-central source as lag-curve reference via quick pre-pass; --json-out flag for structured results
Added: tools/tapematch/WORKFLOW.md: self-contained process doc for context-clear restarts

[2026-06-02] — feat(tools): tapematch observations DB, run archiving, config/diagnostic tuning
Added: tools/tapematch/tapematch_session.py: observations.db (runs/sources/pairs tables with full metrics + LB commentary relationship extraction + null human_judgment columns); run archiving to runs/RUN_ID_DATE/ (log, report, config, results.json); --report-only flag; DB-first path resolution via my_collection
Added: tools/tapematch/tapematch/cli.py: --json-out flag writes structured results JSON; matrix labels now show LB-NNNNN; [DISTINCT SOURCE] replaces spurious [REMASTER?] for near-zero-corr singletons; [SHARED HF CEILING] suppressed when ceiling is Nyquist-limited at analysis_sr
Changed: tools/tapematch/config.yaml: n_anchors 6→12 (more robust to track-break lag errors); cluster_threshold 0.70→0.55 (catches same-source pairs with different CDR splits)

[2026-06-02] — feat(tools): tapematch_session.py — iterative analysis session orchestrator
Added: tools/tapematch/tapematch_session.py: script that queries losslessbob.db for a given date, finds LB folders across DYLAN drives, cleans/populates examples/tapematch/, runs tapematch CLI, extracts LB page commentary, and writes a combined last_run_report.md; supports --dry-run and --no-tapematch flags

[2026-06-02] — feat(tools): tapematch diagnostic output improvements
Changed: tools/tapematch/tapematch/match.py: add cluster_confidence() helper (high/medium/low tier); add asymmetry_dc field to lineage_evidence() return dict
Changed: tools/tapematch/tapematch/cli.py: duration outlier detection with [INCOMPLETE?] flag in TRIM section; speed_info dict persisted across lag-curve pass; staircase/splice explanation text; confidence label on CLUSTERS; DC asymmetry column in LINEAGE; new DIAGNOSTICS section cross-referencing [INCOMPLETE], [REMASTER?], [HIGH/MEDIUM/LOW CONFIDENCE], and [SHARED HF CEILING] diagnostics

[2026-06-02] — feat(gui): lb_category type filter chips on Lookup, Search, and Collection views
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: Concert/Interview Chip row below status bars; filters filteredSummary
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: activeCategory Set state; Type FacetGroup in sidebar; category filter in filteredRows; chips in active-filter strip
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: categoryFilter Set state; Concert/Interview chips in filter bar; category applied to filteredRows

[2026-06-02] — feat(gui): surface lb_category (concert/interview) as Type pill on Lookup, Search, and Collection views
Added: backend/db.py: lb_category included in search_entries, get_entries_by_lb_list, get_collection, and lookup_checksums annotation pass
Added: gui_next/src/renderer/src/lib/lookupStore.ts: lb_category field on LookupDetail and LookupSummaryRow interfaces
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: Type column + pill on summary table rows
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: toggleable "cat" column with Type pill
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Type column with pill; category field on CollectionRow

[2026-06-02] — fix(tools): tapematch — correct trim duration basis and ffprobe final-timestamp bug
Fixed: tools/tapematch/tapematch/cli.py:54: use len(stream)/sr as total_sec in trim_bounds; eliminates negative tail display and performance > total anomaly
Fixed: tools/tapematch/tapematch/audio.py:43: _ffprobe_info fallback uses re.findall[-1] for final ffmpeg stats timestamp; fixes non-deterministic duration for SHN/MP3 sources

[2026-06-02] — feat(gui): lookup — flag owned recordings with collection/lbdir-verified status
Added: backend/db.py: lookup_checksums() annotates each detail+summary item with owned (bool) and lbdir_verified (bool) by joining against my_collection
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: added owned+lbdir_verified fields to LookupDetail and LookupSummaryRow
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: owned/lbdir_verified banner above summary table; owned rows show "In collection · verified" (green) or "In collection" (amber) pill replacing the +WL button; fixed STATE_TONE variable shadow (t → tone) that was breaking button labels
Added: gui_next/src/renderer/src/locales/en.json: lookup.owned.* keys for banner and badge strings
Changed: cli.py: _print_lookup_diff prints [IN COLLECTION · LBDIR VERIFIED] or [IN COLLECTION] on the LB header line when owned

[2026-06-02] — fix(tools): tapematch — write memmaps to /mnt/DATA0/tmp instead of system tmpfs
Fixed: tools/tapematch/tapematch/cli.py: mkdtemp now uses dir=/mnt/DATA0/tmp; avoids filling system tmpfs with ~438 MB memmap per source

[2026-06-02] — feat(backend): track lbdir verify pass timestamp per collection folder
Added: backend/db.py: lbdir_verified_at column migration on my_collection; set_lbdir_verified(disk_path) writer; get_collection() now returns lbdir_verified_at
Changed: backend/app.py: lbdir_check() stamps lbdir_verified_at when result status == "pass", returns timestamp in result dict (covers both GUI and batch_verify.py paths)

[2026-06-02] — fix(tools): tapematch — eliminate OOM on large collections (5 fixes)
Changed: tools/tapematch/tapematch/audio.py: load() always decodes+resamples via ffmpeg pipe; removes sf.read+resample_poly path that held 3–12x native-rate memory for hi-res sources; added probe() helper for channel/frame count without audio decode
Changed: tools/tapematch/tapematch/ingest.py: concat_source() pre-allocates output from probed durations then loads+copies+frees each track; peak drops from 2× source size to output + 1 track
Changed: tools/tapematch/tapematch/trim.py: spectral_flatness() processes in 5-min chunks; per-iteration Z capped at ~38 MB vs the ~4.3 GB full-signal STFT matrix
Changed: tools/tapematch/tapematch/align.py: onset_strength() processes in 1-min chunks with del Z/mag per iteration; per-iteration Z capped at ~7.7 MB
Changed: tools/tapematch/tapematch/match.py: lineage_evidence() replaced full STFT+PSD with scipy.signal.welch (returns 1-D PSD only, never allocates freq×time matrix)
Changed: tools/tapematch/tapematch/cli.py: trim pass now writes trimmed mono to disk as np.memmap (.f32 per source); all analysis phases (lag curves, matrix, lineage) open memmaps instead of holding full arrays; peak process heap for 10×2h sources ≈ 2.3 GB vs ~8 GB+ previously

[2026-06-01] — refactor(tools): tapematch cli.py — sequential pair processing, one source in RAM at a time
Changed: tools/tapematch/tapematch/cli.py: replaced streams/trimmed/monos dicts (all N sources simultaneously) with a single trim_bounds pass; added _load_trimmed_mono helper; inlined pairwise matrix loop so each source is loaded per pair and freed immediately; ref_mono kept in RAM for lag + matrix ref-column to avoid redundant reloads; trim bounds saved to root/.tapematch_meta.json after Pass 1; lineage pass loads stereo stream per source and frees after each

[2026-06-01] — feat(gui): SplashOverlay + AboutDialog — startup splash A and tabbed About C
Added: gui_next/src/renderer/src/components/SplashOverlay.tsx: Splash A "Launch card" — plays real boot-phase sequence at measured speed (~2.4 s), polls Flask for real done signal, indeterminate bar on overrun, fades out on ready
Added: gui_next/src/renderer/src/components/AboutDialog.tsx: About C "Tabbed" — four tabs (About / Tech / Credits / Changes) with double-square brand header, close on Escape or backdrop click
Changed: gui_next/src/renderer/src/App.tsx: mount SplashOverlay on startup; manage showAbout state; pass onAbout to AppShell
Changed: gui_next/src/renderer/src/components/AppShell.tsx: add onAbout prop; wire sidebar "more" button to open About dialog
Changed: gui_next/src/renderer/src/index.css: add @keyframes lbbIndet for splash progress bar indeterminate state

[2026-06-01] — feat(gui_next): collection right-click "Send to →" submenu for pipeline screens
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: import useFolderQueueStore; extend ContextMenu to support children (submenu flyout); add handleCtxSendTo callback; add "Send to →" context menu item with Pipeline / Verify / LBDIR / Spectrograms sub-options

[2026-06-01] — fix(backend): BUG-121 add GET /api/collection/audit — flag collection entries missing checksum rows
Added: backend/db.py:audit_collection_checksums(): query my_collection LEFT JOIN checksums, return {total, missing_checksums, entries} for lb_numbers with zero checksum rows
Added: backend/app.py: GET /api/collection/audit route exposes audit_collection_checksums(); documented in PROJECT.md

[2026-06-01] — fix(backend): BUG-117 checksum rglob + BUG-119 NFT rename preserves folder date/location
Fixed: backend/app.py:4604: BUG-117 — changed iterdir() to rglob("*") in pipeline lookup step so checksum files in subfolders are found (was missing ~12% of collection)
Fixed: backend/app.py:4638: BUG-119 — when DB has no date_str/location for an NFT entry, now preserves current folder name and only toggles -NFT suffix (was proposing bare LB-NNNNN-NFT, silently stripping date/location)

[2026-06-01] — feat(db+scraper): entries.lb_category — add column, classify on scrape, bulk reclassify
Added: backend/db.py: classify_one_entry(date_str, description, location, conn) for per-entry classification inside write closures
Changed: backend/scraper.py: _save_entry now computes and stores lb_category on every INSERT OR REPLACE
Added: backend/db.py: lb_category TEXT column to entries; classify_entry_categories() bulk classify; MASTER_SCHEMA_VERSION→6; POST /api/entries/reclassify (curator)

[2026-06-01] — feat(db): add entries.lb_category column; classify concerts from bobdylan_shows
Added: backend/db.py: lb_category TEXT column to entries; classify_entry_categories() classifies all 16 630 entries (concert via bobdylan_shows date-join, non-concert categories via dylan_performances + keyword heuristics, unknown fallback); one-time backfill in init_db(); MASTER_SCHEMA_VERSION bumped to 6
Added: backend/app.py: POST /api/entries/reclassify (curator-only) to re-run classification after bobdylan_shows updates
Results: concert 84.7%, unknown 12.3%, tv/interview/studio/compilation/rehearsal/radio/soundcheck ~3%

[2026-06-01] — feat(tools): batch collection verification pipeline + --from-collection mode
Added: tools/batch_verify.py: headless CLI for lbdir-centric batch verification of large collections; 4-phase pipeline (identify/retrieve/verify/reconcile-preview); report SQLite DB (data/batch_verify.db); --resume/--dry-run/--reprocess/--report modes; --from-collection fetches disk_path+lb_number from GET /api/collection (skips Phase 0 identify); --root walks a directory tree. (BATCH-VERIFY)

[2026-05-31] — chore(tests): pipeline smoke-test 500-folder run; 2 more bugs added
Added: BUGS.md BUG-120: 2 folders with verify mismatch (audio changed since checksumming); BUG-121: Farm Aid LB-12347 in collection but checksums absent from DB
Changed: BUGS.md BUG-117: confirmed 12% rate over 500-folder run (was 11%/100); BUG-118: expanded to 11 conflicts including 5-way match and phantom LB-04994/03029/06748/11900 pattern

[2026-05-31] — chore(tests): pipeline smoke-test script + 3 new bugs documented
Added: tests/test_pipeline_smoke.py: random-sample 100 collection folders through all 4 pipeline steps (verify/lookup/rename/lbdir); outputs detail report + reproducible bug list
Added: BUGS.md BUG-117/118/119: no-checksum folders in collection, lookup conflict (3 shared-checksum pairs), NFT rename strips date/location

[2026-05-31] — fix(backend): forum post description showed checksums instead of entry info text
Fixed: backend/forum_poster.py: _read_lb_txt now excludes double-extension files (.ffp.txt, .md5.txt) via f.suffixes == ['.txt']; prefers file containing LB-{number} in its name as the main info file over alphabetical first

[2026-05-31] — fix(backend): verify_folder shows files as Missing when audio is in subfolders
Fixed: backend/checksum_utils.py: detect_folder_mode now uses rglob instead of glob; verify_folder builds a name→path map with rglob so audio files in subdirectories are found and resolved correctly instead of showing as Missing

[2026-05-31] — fix(backend): LBDIR check inflates track count for SHN recordings with shntool hashes
Fixed: backend/checksum_utils.py: verify_folder_lbdir() normalizes shntool-section filenames via non-alphanumeric → '_' collapse on both sides before matching against md5 keys; handles shntool's space AND special-char (e.g. '&') → '_' substitution, preventing duplicate file rows

[2026-05-31] — fix(backend): LBDIR check reports 0 tracks / false Pass for flat-format lbdir files
Fixed: backend/checksum_utils.py: parse_lbdir_file now has a flat-format fallback — if no section headers (=== MD5 for: / === FFP for:) are found after the main parse pass, re-scans each line directly as MD5/FFP entries; handles *.flacf.md5.txt and *.wavf.md5.txt lbdir variants that contain plain HASH  filename lines without section structure

[2026-05-31] — fix(backend/gui_next): LBDIR "Check all folders" crash on missing files or no lbdir
Fixed: backend/checksum_utils.py: status 'incomplete' renamed to 'missing_files' to match frontend LbdirState; parse-error early-return now emits full schema (status='no_lbdir', mode='unknown', files=[]) instead of bare error dict
Fixed: backend/app.py: no-lbdir branch now returns complete schema (status='no_lbdir', mode='unknown', files=[]) so all fields exist when the folder is rendered
Added: gui_next/src/renderer/src/lib/lbdirStore.ts: 'shntool_missing' added to LbdirState union
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: shntool_missing → STATE_LABEL entry (tone='warn', label='Shntool not installed')

[2026-05-31] — fix(gui_next): ScreenSearch rating filter — full grade scale and ASCII hyphen fix
Fixed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: rating chips were missing A+, C+, C-, D+, D, D-, F; Unicode minus U+2212 replaced with ASCII hyphen so A- filter now matches DB values; RATING_RANK, VALID_RATINGS, RatingGrade type, ratingTone, ratingItems, and "Rated A or A-" built-in view all updated

[2026-05-31] — fix(backend/gui_next): stale torrent records cleanup + ghost torrent_file_exists fix
Fixed: backend/db.py: add delete_torrent_record(); add clear_superseded_torrent_paths() — nulls out torrent_path on older sibling records when a regen reuses the same filename, preventing false torrent_file_exists=True
Fixed: backend/app.py: torrent_create route calls clear_superseded_torrent_paths after regen; new DELETE /api/torrent/<id> route deletes DB record + file (blocked if still in qBt)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: "Del record" button in HISTORY torrent panel + GlobalTorrentPanel (disabled if added_to_qbt=1); ConfirmDialog for both
Added: gui_next/src/renderer/src/locales/*.json: delRecord, recordTitle, recordBody, torrentRecordDeleted keys in all 6 locales

[2026-05-31] — fix(backend): pipeline scan-tree now detects SHN-only folders
Fixed: backend/app.py:4702: Added '.shn' to _AUDIO extension set in pipeline_scan_tree(); folders containing only SHN files were previously invisible to the scan and never added to the pipeline queue.

[2026-05-31] — feat(backend/scraper): setlist from LBBCD track table for all bootleg-CD entries
Added: backend/scraper.py: _extract_setlist_from_lbbcd() — queries bootleg_titles for lbbcd_id, parses cached LBBCD-{id}.html track table, formats numbered setlist with CD headers for multi-disc sets; always preferred over scraped free-text when LBBCD page exists; tries LBBCD-N.html then LBBCD-NNN.html (3-digit pad) to cover both naming conventions; bulk-applied to all 327 existing entries

[2026-05-31] — fix(backend/gui_next): qBt remove robustness + auto-detect manually removed torrents
Fixed: backend/qbittorrent.py: remove_torrent now accepts HTTP 204 as success (qBt 5+ compat); check_torrent_presence() added to detect absent torrents via /api/v2/torrents/info
Fixed: backend/app.py: qbt_remove route — if remove fails but torrent is already gone from qBt, clears DB flag anyway; added GET /api/torrent/<id>/qbt_check route for presence sync
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: fetchTorrentRecords auto-syncs qBt status on load — records marked "In qBt" that were manually removed now update without user action

[2026-05-31] — fix(gui_next): detail panel shows "No forum history" when forum API fails silently
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: initialize forumBusy=true; add forumError state; surface API failures as error message instead of "No forum history"; fix copy-paste bug (loadingTorrents key used in forum tab)
Added: gui_next/src/renderer/src/locales/*.json: loadingForum and forumLoadError i18n keys in all 6 locales

[2026-05-31] — fix(backend): forum post subject uses BOOTLEG title instead of location for BOOTLEG entries
Changed: backend/forum_poster.py: extracted _build_subject helper; uses entry["bootleg_title"] over location when present
Changed: backend/app.py: enrich entry dict with bootleg_title from bootleg_titles table before preview_forum / post_forum calls

[2026-05-31] — feat(gui_next): My Collection — remove fingerprint chips/column, add Post to forum button and right-click actions
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: removed Unconfirmed + No fingerprint filter chips and FP column; added Post to forum header button; added Post to forum / Create torrent / Add to qBittorrent to right-click context menu; all three actions work on multi-selected rows; context menu uses checked rows when the right-clicked row is among them

[2026-05-31] — feat(gui_next/backend): redesign Data Purges card — hierarchy, danger zone, recoverable-space signal
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: split PURGE_ITEMS into SCOPE_ITEMS + ALL_USER_DATA_ITEM; add PurgeRow + PurgeDangerZone sub-components; new card layout with subtitle, magnitude bars, hover-reveal red buttons, isolated danger zone, green archive callout
Changed: backend/app.py: purge_stats adds recoverable_bytes (sum of data/site/ + fingerprints.db disk usage)
Changed: gui_next/src/renderer/src/locales/en.json: add desc/unit strings and new card i18n keys for purges section

[2026-05-31] — refactor(gui_next): move row highlight colors checkbox from Setup to Themes page
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: add useSettingsStore + rowHighlight checkbox in Advanced card
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: remove rowHighlight state and checkbox JSX
Changed: gui_next/src/renderer/src/locales/en.json: add themes.advanced.rowHighlight key

[2026-05-31] — fix(gui_next): typeface Source Sans 3 not loading; font size selector had no effect
Fixed: gui_next/src/renderer/index.html: add IBM Plex Sans + Source Sans 3 to Google Fonts link (only Inter was loaded)
Fixed: gui_next/src/renderer/src/lib/tokens.ts: applyTheme now emits --lbb-fs-* CSS variables scaled by fontSize/13 for all 19 sizes in use
Changed: gui_next/src/renderer/src/ (23 files): replace 538 hardcoded inline fontSize literals with var(--lbb-fs-*) references so they respond to the font size setting

[2026-05-31] — feat(gui_next): global row highlight toggle in Preferences
Added: gui_next/src/renderer/src/store.ts: rowHighlight boolean (default true) + setRowHighlight action persisted in lbb-settings
Changed: gui_next/src/renderer/src/components/table.tsx: TR reads rowHighlight from store; when off, row background and left status bar both render transparent
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: "Row highlight colors" checkbox in Preferences card
Added: gui_next/src/renderer/src/locales/en.json: setup.preferences.rowHighlight key

[2026-05-31] — feat(gui_next): language selector in sidebar user chip
Added: gui_next/src/renderer/src/components/AppShell.tsx: globe+language-code button in sidebar footer; click opens popover with 6 language options; wired to existing useSettingsStore language/setLanguage

[2026-05-31] — feat(backend/gui_next): purge row counts in Data Purges panel
Added: backend/app.py: GET /api/purge/stats — returns row counts for rename_history, flat_file, scraper, fingerprint, and all-user-data groups
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: fetch purge stats on mount and after each purge; display count dimmed next to each item label

[2026-05-30] — fix(backend/gui_next): Attachments screen blank-white crash
Fixed: backend/app.py: added ef.downloaded to SELECT in attachments_cached — missing column caused IndexError → 500 → undefined total → toLocaleString() crash
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: setTotal(d.total ?? 0) to guard against backend error responses

[2026-05-30] — feat(gui_next/backend): DB stats on LB Crawler and Entry Metadata strip cards
Changed: backend/db.py: get_stats() now returns ok_entries and total_entries counts from entries table
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: LB Crawler card shows inventory URL count from /api/crawler/inventory/stats; Entry Metadata card shows ok_entries when idle, session progress when running

[2026-05-30] — feat(gui_next/backend): geocoder cache and coverage stats
Added: backend/app.py: /api/geocode/stats route — returns total_cached, geocoded, failed, manual, entries_total, entries_covered, pct_covered from location_geocoded and entries tables
Added: gui_next/src/renderer/src/screens/ScreenScraper.tsx: GeoStats interface, state, and fetch; GeocoderTab renders Cache Stats and Coverage StatGrids; strip card shows pct_covered and geocoded count

[2026-05-30] — fix(db): correct swapped columns in bobdylan_shows for 2046 pending rows
Fixed: data/losslessbob.db: bobdylan_url and date_str were swapped in 2046 rows inserted by older discover code; one-time UPDATE swapped them back so the scraper can fetch valid URLs

[2026-05-30] — fix(gui_next): remove duplicate AppShell nesting in Trading, Sharing, Scraper screens
Fixed: gui_next/src/renderer/src/screens/ScreenTrading.tsx: removed inner AppShell wrapper — App.tsx already wraps all routes in one, causing double sidebar + title bar
Fixed: gui_next/src/renderer/src/screens/ScreenSharing.tsx: same fix
Fixed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: same fix; deriveCrumbs already auto-resolves "LosslessBob / Curator / Scraper" from NAV_GROUPS

[2026-05-30] — fix(backend): replace inotify collection watcher with polling thread
Fixed: backend/scheduler.py: start_collection_watcher crashed at startup on systems where Electron exhausts the 128 inotify-instance limit; replaced watchdog Observer with a 60-second polling thread — no inotify usage, works on any system

[2026-05-30] — feat(backend/gui_next): archive.org upload integration on Sharing screen
Added: backend/archive_org.py: IA S3-like upload module — credentials test, stream-PUT per-file, thread-safe progress state, stop support
Added: backend/db.py: archive_org_uploads table + create_archive_upload / finish_archive_upload / get_archive_uploads functions
Changed: backend/credentials.py: added SERVICE_IA constant for archive.org keyring slot
Changed: backend/app.py: added 7 /api/archive_org/ routes (credentials CRUD+test, upload start/stop/status, history)
Changed: gui_next/.../ScreenSharing.tsx: added ArchiveOrgSection component — credential form, upload form with progress bar, history table
Changed: gui_next/.../locales/en.json: added archiveOrg translation namespace

[2026-05-30] — feat(backend/gui_next): collection trading + file sharing features (branch feat/trading-and-sharing)
Added: backend/sharing.py: ephemeral token-based share state, ZIP streaming, Cloudflare Tunnel lifecycle, expiry reaper daemon thread, HTML listing page renderer
Added: gui_next/.../ScreenTrading.tsx: friend collection import/export, diff compare, trading list export
Added: gui_next/.../ScreenSharing.tsx: create/revoke file shares, tunnel status banner, LAN + cloudflared modes
Changed: backend/db.py: added friend_collections + friend_collection_entries tables to _ensure_schema()
Changed: backend/app.py: added 5 /api/trading/ routes + 7 /api/share/ routes + sharing module import
Changed: gui_next/.../AppShell.tsx: added Trading and Sharing nav items under Library group
Changed: gui_next/.../App.tsx: registered /trading and /sharing routes + screen imports
Changed: gui_next/.../Icon.tsx: added trading and share icons
Changed: gui_next/.../locales/en.json: added trading and sharing nav labels

[2026-05-30] — feat(gui_next): ScreenScraper — full 6-tab scraper management screen
Added: gui_next/src/renderer/src/screens/ScreenScraper.tsx: new screen with status strip (all 6 scrapers at a glance), tab switcher, left controls + right live log panel per tab, session/scrape history tables; covers LB Crawler, Entry Metadata, Bootleg Catalog, Dylan.com, Setlist.fm, Geocoder
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen for /scraper route with ScreenScraper; added import
Changed: gui_next/src/renderer/src/index.css: added lbb-pulse and lbb-indeterminate CSS keyframe animations used by the scraper screen

[2026-05-30] — feat(backend): setlist.fm API integration
Added: backend/setlistfm.py: run_update(api_key, force) paginates /artist/{mbid}/setlists (~160 pages, ~0.55s/req); stores tour_name, venue, city, country, show info; setlist split by set_index/set_name/is_encore + song-level info/is_cover/cover_artist/is_tape; get_status()/stop()/save_api_key()/get_api_key() helpers
Added: backend/db.py: setlistfm_shows (PK setlistfm_id, date_str indexed, tour_name indexed) + setlistfm_setlist (PK setlistfm_id+position, set_index, track_name indexed); added to MASTER_TABLES; MASTER_SCHEMA_VERSION bumped to 5; setlistfm_api_key added to USER_META_KEYS
Added: backend/app.py: POST /api/setlistfm/key, /update, /stop + GET /api/setlistfm/key, /status, /show?date=YYYY-MM-DD, /stats

[2026-05-30] — feat(backend): bobdylan.com official setlist scraper
Added: backend/bobdylan_scraper.py: new module — fetch_sitemap_urls() discovers 4139 show URLs from 3 WordPress sitemaps; parse_show_page() parses venue/location/track list from each /date/ page; run_discover() upserts URL+date rows; run_scrape(force) scrapes unscraped pages; run_update(force) runs both idempotently; get_status()/stop() for progress/cancellation
Added: backend/db.py: bobdylan_shows table (bobdylan_url PK, date_str indexed) and bobdylan_setlist table (bobdylan_url+position PK, track_name, song_url); both added to MASTER_TABLES; MASTER_SCHEMA_VERSION bumped to 4
Added: backend/app.py: POST /api/bobdylan/update, /discover, /scrape, /stop + GET /api/bobdylan/status, /show?date=YYYY-MM-DD, /stats routes; join to entries/dylan_performances via date_str

[2026-05-30] — feat(gui_next/scraper): setlist file-name fallback + scrape always repopulates setlist
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: EntryDetailPanel setlist section falls back to entry_files list when no setlist available — shows track index, download status icon, and filename in monospace; Files section suppressed when fallback is active to avoid duplication
Changed: backend/scraper.py: setlist now always re-derived on scrape — if _is_setlist_para() finds nothing, falls back to extract_setlist_from_description() on the built description so a re-scrape never wipes a populated setlist

[2026-05-30] — fix(db/scraper/gui_next): setlist coverage 10% → 69% via backfill + scraper + parser fixes
Changed: backend/db.py: added _SL_DOT/_SL_NUM regexes; extract_setlist_from_description() — detects track-listing paragraphs via ≥3 dot/paren markers or num-only sequential pattern; init_db() migration setlist_backfill_v1 — one-time backfill of 9,794 entries using extract_setlist_from_description()
Changed: backend/scraper.py: replaced track_pattern bare-text-node-only detection with _is_setlist_para() helper (same two-pattern logic) applied to all <p> tags — future scrapes now correctly route track listings to setlist column
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: updated parseSetlist() to handle zero-padded numbers (01.), comma-separated dot format (1. Song, 2. Song), comma-separated num-only (1 Song, 2 Song), and space-separated num-only (1 Song 2 Song) formats; added normNum() to strip leading zeros

[2026-05-30] — feat(gui_next): setlist rendered as structured track table in entry detail panel
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: added parseSetlist() helper — detects inline format ("1. Song 2. Song …" all on one line) vs newline-separated format; splits inline format on /\s+(?=\d{1,2}[.)]\s)/ boundaries; parses each part with "N. Title" / "N) Title" regex into {kind:'track',num,title} items, other non-empty lines become section headers; replaced raw <pre> setlist block in EntryDetailPanel with a two-column table (track # | song title), header rows span columns; collapse defaults to first 12 items with "Show N more…" toggle; setlist label shows track count

[2026-05-30] — feat(db/scraper/gui_next): taper_name + source_chain columns extracted from description
Added: backend/db.py: extract_taper_and_source() — 14-step regex extractor covering Taper:/Recording:/Source:/Lineage:/BOOTLEG: labels, raw > chains, AUD DAT codes, short taper handles, legendary/NET taper patterns; ~80.5% coverage on 16k entries; two new TEXT columns taper_name + source_chain on entries table; ALTER TABLE migration with one-time backfill
Added: backend/scraper.py: compute taper_name/source_chain via extract_taper_and_source() on every scrape; included in INSERT OR REPLACE
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: Taper and Source columns in search table (toggleable, with col widths); taper/source rows in entry detail panel meta grid; SearchRow interface extended; CSV export updated

[2026-05-30] — feat(gui_next): best-per-date filter on Search screen
Added: gui_next/src/renderer/src/screens/ScreenSearch.tsx: RATING_RANK constant; bestPerDate state; bestPerDateRows memo (keeps only highest-rated entry per unique concert date, pass-through for undated rows); "Best per date" checkbox in facet sidebar with description; filter chip in result strip; clearAll + hasActiveFilters wired to new toggle

[2026-05-30] — feat(backend/gui): FEAT-11 remote data ZIP retrieval
Added: backend/app.py: POST /api/data/download + GET /api/data/download/status routes; _do_data_download() background worker; _DATA_PROTECTED/EXTS guards; _data_dl_state + _data_dl_lock
Added: gui/setup_tab.py: Remote Data group — ZIP URL field, Download & Extract button, progress bar, _DataDownloadThread, polling logic

[2026-05-30] — feat(backend/gui): FEAT-10 GitHub auto-updater + enhanced About dialog
Added: VERSION: single source of truth for app version (1.2.0)
Added: backend/version.py: get_version() reads VERSION file; VERSION constant
Added: backend/updater.py: restart_application() — cross-platform process relaunch
Added: backend/app.py: GET /api/app/version, GET /api/update/check, GET /api/update/status, POST /api/update/apply; _do_update() background download+apply; github_repo/data_zip_url in settings keys
Changed: gui/main_window.py: VERSION now imported from backend.version; _on_about shows Python/PyQt6/Qt/platform info
Added: gui/setup_tab.py: Application Updates group — GitHub repo field, Check/Download/Restart buttons, progress bar, _UpdateCheckThread, _UpdateApplyThread

[2026-05-30] — feat(backend/gui): FEAT-09 collection folder integrity watchdog
Added: backend/db.py: log_integrity_event(), get_integrity_events(), ack_integrity_events() helpers
Added: backend/scheduler.py: _CollectionEventHandler + start_collection_watcher() — watches all my_collection disk_path dirs for deletions/moves
Added: backend/app.py: GET /api/integrity/events + POST /api/integrity/ack routes; call start_collection_watcher() at startup
Added: gui/main_window.py: yellow ⚠ alert label in status bar; click opens dialog listing events with Acknowledge All button
Cancelled: instructions/CC_INSTRUCTIONS.md: FEAT-06 (info.txt generator) marked cancelled

[2026-05-30] — feat(gui_next): finish wiring gaps — disambiguation panel, NFT suffix, Cache missing, queue location
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: added `candidates[]` to RenameRow; added NFT suffix logic (applyNftSuffix); replaced stub disambiguation panel with fully wired panel that fetches GET /api/folder_link + GET /api/lb_alias/resolve, shows LB candidate buttons, and wires Pin (PUT /api/folder_link), Unlink (DELETE /api/folder_link), and Standardize (GET /api/folder_naming/standard) actions.
Added: gui_next/src/renderer/src/locales/en.json: new i18n keys for rename.disambiguate (pin/unpin/loading/pinned/standardize) and rename.toast (pinned/unpinned/pinFailed/unpinFailed/standardized/standardizeFailed).
Added: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: "Cache missing" batch button — POSTs /api/entry/<lb>/scrape for each missing entry, shows progress, reloads tree on completion.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: wired "Open queue location" IconButton to openPath(parent of first queued folder).

[2026-05-29] — chore(deploy): switch Windows installer + portable to Electron/React (gui_next)
Changed: losslessbob_backend.spec: made cross-platform — Windows uses watchdog.observers.read_directory_changes, no fingerprinting stack, bundles shntool.exe; Linux keeps fingerprinting + inotify.
Changed: backend/paths.py: frozen Windows now uses %LOCALAPPDATA%\LosslessBob for data dir (backend binary lives inside resources/backend/ which is read-only in the installed app).
Changed: gui_next/package.json: added NSIS + portable Windows targets; file associations (.ffp/.md5/.st5); dist:win script.
Changed: gui_next/src/main/index.ts: packaged backend binary name is LosslessBobBackend.exe on Windows, LosslessBobBackend on Linux.
Changed: .github/workflows/release.yml: build-windows job now builds backend onefile → npm ci → copies binary to resources → electron-builder --win → uploads Setup.exe + portable.exe.

[2026-05-29] — chore(deploy): switch Linux AppImage to Electron/React (gui_next)
Changed: .github/workflows/release.yml: build-linux job now builds the backend as a PyInstaller onefile binary, bundles it as an Electron extraResource, and packages the gui_next Electron app as the AppImage via electron-builder instead of PyInstaller + manual AppDir.
Added: losslessbob_backend.spec: backend-only onefile PyInstaller spec (no PyQt6, no GUI); produces dist/LosslessBobBackend for bundling.
Changed: gui_next/package.json: added electron-builder ^25 devDependency + dist:linux script + build config (AppImage target, extraResources for backend binary).
Changed: gui_next/src/main/index.ts: ensureBackend() now branches on app.isPackaged — packaged mode spawns resources/backend/LosslessBobBackend, dev mode uses .venv/python3 as before.

[2026-05-29] — fix(backend): TOCTOU race + missing error guards in background task start routes
Fixed: backend/app.py: All four background-task start routes (spectrogram generate, fingerprint build, dup scan, identify-folder) had a TOCTOU race — the "already running" guard ran inside the lock but the thread started after the lock released, allowing concurrent requests to start two workers. Fixed by claiming status="running" inside the lock before releasing it. Guard widened from status=="running" to not-in-(idle, done, error) so the "scanning" phase is also covered.
Fixed: backend/app.py: Added top-level try/except to _do_fp_build, _do_fp_dup_scan, _do_fp_identify_folder, and _do_spectro_batch so that import failures or unexpected crashes reset status to "error" rather than leaving it permanently stuck at "running".

[2026-05-29] — feat(gui_next+backend): SQL query panel in DB Editor (TODO-101)
Added: backend/app.py: POST /api/dbedit/query — run arbitrary SQL, returns columns+rows for SELECT or rows_affected for DML; blocks DROP/TRUNCATE/VACUUM/ATTACH/DETACH
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: SqlQueryPanel component (textarea, Run/Clear, results table, status line with row count / error); toggle button in action row; Ctrl+Enter shortcut to run
Changed: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: added dbeditor.query.* keys

[2026-05-29] — feat(gui_next): ScreenDbEditor — full DB editor screen ported from legacy dbedit_tab
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: full DB editor screen with table browser, inline editing, pagination, sort, search, Commit/Discard/Delete/Export CSV, DB Integrity panel (reconcile, overrides, backup), and LB Aliases panel (curator-gated add/delete)
Changed: gui_next/src/renderer/src/App.tsx: wired ScreenDbEditor at /dbeditor, replacing PlaceholderScreen
Changed: gui_next/src/renderer/src/components/AppShell.tsx: moved DB Editor nav item from Curator group to Settings group (alongside Setup and Themes); Curator group now only contains Scraper
Changed: gui_next/src/renderer/src/locales/en.json: added dbeditor i18n section (80+ keys)
Changed: gui_next/src/renderer/src/locales/{de,es,fr,it,nl}.json: added dbeditor section (English placeholder text, ready for DeepL pass)

[2026-05-29] — chore(i18n): gui_next locale refresh — add 60 missing keys, DeepL fill all gaps
Added: .claude/commands/gui-next-i18n.md: new skill for React locale workflow (Step 1 count → Step 2 Qt port warning → Step 3 DeepL → Step 4 verify)
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: 60 new keys added (fingerprint, collection toast strings); ~582 strings per language translated via DeepL (57,254 chars total); 53 remaining gaps are intentional proper-noun/abbrev strings (Pipeline, LBDIR, LB#, etc.)
Changed: .claude/settings.local.json: DEEPL_API_KEY added to env block for future sessions

[2026-05-29] — feat(gui_next+backend): ScreenFingerprint — audio fingerprint match by date (TODO-106)
Added: gui_next/src/renderer/src/screens/ScreenFingerprint.tsx: new screen under Assets group; date picker finds collection entries for that date, builds LB fingerprints via existing /api/fingerprint/build, then identifies a user mystery folder; two-phase progress view; ranked results table; cleanup button; all strings wrapped with t() for i18n
Added: backend/app.py: GET /api/fingerprint/collection_by_date, POST /api/fingerprint/identify_folder, GET /api/fingerprint/identify_folder/status, POST /api/fingerprint/identify_folder/stop; _do_fp_identify_folder worker; _fp_id_state/_fp_id_lock/_fp_id_stop module-level state
Added: gui_next/src/renderer/src/components/Icon.tsx: fingerprint icon (scan-crosshair)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: Fingerprint nav item added to Assets group
Changed: gui_next/src/renderer/src/App.tsx: /fingerprint route registered
Changed: gui_next/src/renderer/src/locales/en.json: appShell.nav.fingerprint + full fingerprint i18n namespace

[2026-05-29] — docs: lock gui/ (PyQt6) as frozen; gui_next is sole development target
Changed: PROJECT.md: tech stack, architecture pattern, file structure, GUI strategy note, and change log all updated to reflect gui_next as the only active GUI; gui/ marked FROZEN

[2026-05-29] — feat(gui_next): DeepL machine-translation pass for all 5 gui_next locales
Added: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ~520 previously-untranslated strings (new GUI text with no Qt equivalent) translated via DeepL API; {{varName}} placeholders protected before transmission and restored after, 0 broken vars; coverage now 92–94% per locale
Added: scripts/deepl_translate_gui_next.py: one-off DeepL translation script (retranslates strings still identical to English or with broken {{var}} placeholders)

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in AppShell + ScreenHome
Changed: gui_next/src/renderer/src/components/AppShell.tsx: added useTranslation to Sidebar, Topbar, StatusBar; wrapped appShell.* keys including brand, version, nav group/item labels (dynamic via item.id), curator badge/hint/enable, search placeholder, and status bar labels
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: added useTranslation; wrapped all home.* keys including collection title, DB status, buttons, hero card (with dangerouslySetInnerHTML for HTML desc), step strips, stats, jump tiles, recent activity table, tips, and all toasts

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in ScreenSetup + ScreenCollection; add TypeScript key safety
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: added useTranslation to ScreenSetup, CuratorToggle, IntegCard; wrapped all setup.* keys (database, masterData, integrations, torrent, preferences, purges, packages, flatFile, all toasts); added language selector to Preferences card bound to store.language/setLanguage
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: added useTranslation to 9 sub-components; wrapped all collection.* keys (PersonalInfoModal, ScanPreviewModal, AddFolderModal, ForumModal, DetailPanel, ConfirmDialogs, GlobalForumPanel, GlobalTorrentPanel, main table headers, all toasts)
Added: gui_next/src/renderer/src/i18next.d.ts: TypeScript CustomTypeOptions declaration for compile-time t() key safety
Added: gui_next/src/renderer/src/locales/en.json: added setup.toast.buildingArchive, setup.toast.noRecognisableFiles, setup.toast.scrapedExported keys

[2026-05-29] — feat(gui_next): wrap hardcoded UI strings with t() in six screen files
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: added useTranslation hook; wrapped all pipeline.* keys including header, status pills, bulk actions, queue rail labels, filter chips, selection bar, empty state, and table headers
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: added useTranslation to ScreenLookup and ListboxModal; wrapped all lookup.* keys including header, sources rail, status counters, summary/detail table headers, footer, and all toast messages
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: added useTranslation to ScreenRename and StateChip; wrapped all rename.* keys including header, state labels (in render), hints, bulk bar, table headers, disambiguate panel, dry-run banner, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: added useTranslation to ScreenVerify and StateBadge; wrapped all verify.* keys including header, rail, stats labels, toolbar, shntool warning, file-state pills, showing-problems text, table headers, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: added useTranslation to ScreenThemes and CustomTokenEditor; wrapped all themes.* keys including page title, mode/density/accent/typeface/advanced cards, token labels, preview section, and toasts
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: added useTranslation hook; wrapped all map.* keys including header, filter rail labels, ownership buttons, display options, selected venue panel, entries section, and info hint

[2026-05-29] — fix(gui_next): embed real Leaflet map in ScreenMap
Changed: gui/resources/map.html: added postMessage listener (type:'applyFilters') so React panel can push filter updates without navigation; added ?embedded=1 support to hide the built-in filter bar when shown inside the Electron UI
Changed: gui_next/src/renderer/src/screens/ScreenMap.tsx: replaced fake static canvas + hardcoded pin overlays with a live iframe pointing to http://localhost:5174/map?embedded=1; wired Apply filters, Reset to defaults, Copy share URL, and Open live map buttons

[2026-05-29] — fix(gui_next): HTML attachments blocked by CSP in iframe
Fixed: gui_next/src/renderer/index.html: added frame-src directive to CSP to allow iframes to load from http://127.0.0.1:5174; default-src 'self' was blocking HTML attachment previews with ERR_BLOCKED_BY_CSP

[2026-05-29] — feat(gui_next): integrations startup status check
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: added loadQbtStatus + loadWtrfStatus silent startup checks so integration cards show real status on mount without requiring a manual Test click; also fixes WTRF status label showing "error" instead of "not tested" when tone is warn

[2026-05-29] — fix(backend): all attachment entries shown as stale
Fixed: backend/app.py: attachments_cached omitted "downloaded" field from file objects; frontend stale check (f.downloaded === 1) saw undefined for every file and marked every entry stale.

[2026-05-29] — fix(gui_next): attachment viewer 404 for all file types
Fixed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: frontend was passing raw LBF-prefixed filename to /api/attachment route which queries by clean_name; changed to use clean_name || filename in both the text-fetch and fileUrl.

[2026-05-29] — chore: merge feat/gui-redesign → main (gui_next v1.0 complete)
Changed: PROJECT.md: gui_next marked as PRIMARY GUI, gui/ marked legacy/deprecated; Tech Stack updated
Note: All 14 gui_next screens now on main with full backend wiring; feat/gui-redesign branch retired

[2026-05-29] — feat(gui_next): wire ScreenPipeline Bulk actions menu (TODO-116)
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: inline popover on "Bulk actions" button with Select all visible, Clear selection (conditional), and Clear queue (destructive) — closes TODO-116

[2026-05-29] — feat(gui_next): shared folder queue across Pipeline and detail screens
Added: gui_next/src/renderer/src/lib/folderQueueStore.ts: new Zustand store holding the canonical folder list
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: addFolders/clearQueue syncs to folderQueueStore; useEffect picks up folders added from other screens
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: reads folders from folderQueueStore instead of verifyStore
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: reads folders from folderQueueStore instead of lbdirStore
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: reads folders from folderQueueStore; pending folders also routed through shared queue
Changed: gui_next/src/renderer/src/lib/verifyStore.ts: removed folders/setFolders (moved to folderQueueStore)
Changed: gui_next/src/renderer/src/lib/lbdirStore.ts: removed folders/setFolders (moved to folderQueueStore)
Changed: gui_next/src/renderer/src/lib/spectrogramStore.ts: removed folders/setFolders (moved to folderQueueStore)

[2026-05-29] — feat(backend+gui): data package restore from zip (TODO-104)
Added: backend/app.py: POST /api/package/restore — detects package type, dry_run preview, restores user_data or scrape_data, validates zip
Added: gui/setup_tab.py: _PackageRestoreThread; "Restore from Zip…" button; dry-run + confirm dialog flow; _set_pkg_buttons_enabled helper
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: handleRestorePackage; ConfirmDialog conflict preview; "Restore from zip…" card in Data Packages SetupCard

[2026-05-29] — feat(gui_next): ScreenSetup — Data Packages card with user data and scraped site data export (TODO-102, TODO-103)
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: pkgBusy/pkgUserResult/pkgScrapeResult state; handleExportUserData and handleExportScrapeData handlers; "Data Packages" SetupCard with per-type sub-cards, inline result display (path, file count, size), and clickable path link

[2026-05-29] — feat(backend+gui+cli): data package export — user data and scraped site data (TODO-102, TODO-103)
Added: backend/app.py: POST /api/package/user_data — zips losslessbob.db + settings.ini + gui_state.json into data/exports/losslessbob_userdata_YYYY-MM-DD.zip with JSON manifest
Added: backend/app.py: POST /api/package/scrape_data — zips all of data/site/ into data/exports/losslessbob_sitedata_YYYY-MM-DD.zip with JSON manifest
Added: gui/setup_tab.py: _PackageUserDataThread, _PackageScrapeDataThread worker classes; "Data Packages" QGroupBox with Export User Data and Export Scraped Site Data buttons and result dialog
Added: cli.py: package user-data / package scrape-data subcommands with optional --out path

[2026-05-29] — fix(backend): guarantee ≥2 TCP trackers on every torrent (TODO-132)
Added: backend/torrent_maker.py: _FALLBACK_TCP_TRACKERS constant and _ensure_tcp_trackers() helper
Changed: backend/torrent_maker.py: make_torrent() calls _ensure_tcp_trackers() after fetch_trackers() so any chosen list always has at least 2 http/https trackers

[2026-05-29] — feat(gui_next): complete TODO-122, TODO-125..130 — ScreenCollection batch of improvements
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: sortable column headers (LB#, Status, Date, Location, Folder, Disk path, Confirmed, FP) with ▲▼ indicators (TODO-126)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: batch torrent-create and qBittorrent progress bar showing N/M live count (TODO-130)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: bulk Update Location — multi-row picks parent dir and scans for matching LB-XXXXX subfolders; single-row validates name against /api/folder_naming/standard/<lb> and toasts mismatches (TODO-125)
Added: backend/app.py: /api/collection/<lb>/audioinfo — probes FLAC/WAV with soundfile, falls back to ffprobe for SHN/APE; caches by mtime fingerprint; returns format, bit_depth, sample_rate, mixed (TODO-129)
Added: backend/app.py: /api/wishlist/<lb> PATCH — update priority/notes on a wishlist entry (TODO-122)
Added: backend/db.py: update_wishlist() function (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Wishlist filter view — extra Priority/Notes/Added/Rating columns with inline click-to-edit (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Duplicates filter view — grouped tree by show (date·location) with "Open on LosslessBob", "Open folder", and "Remove" actions per variant (TODO-122)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: detail panel fetches /api/collection/<lb>/audioinfo and displays real format·bit/rate pill (TODO-129)
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: detail panel Attachments → /attachments, Spectrograms → real handler, On map → /map (no more "coming soon" toasts) (TODO-128)
Changed: gui_next/src/renderer/src/components/table.tsx: TH now accepts onClick + sorted prop with ▲▼⇅ sort indicators
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: removed hardcoded "FLAC · 16/44" placeholder pill from detail panel (TODO-127)

[2026-05-29] — fix: resolve BUG-107, BUG-108, BUG-109
Fixed: backend/app.py: POST /api/lookup/scan_folders endpoint added — recursively finds checksum sidecar files (.ffp, .md5, .st5, .sha1) under given folders (BUG-109)
Fixed: backend/app.py: pipeline_scan_tree now checks root itself before rglob so flat folders with audio at the root level are included in results (BUG-108)
Fixed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: handleFolders calls scan_folders endpoint to populate source content, so folder sources work with "Lookup all sources" (BUG-109)
Fixed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: webUiTone converted to useState('ok') — badge now defaults to "connected" and reflects live test results instead of password config (BUG-107)

[2026-05-28] — fix(gui_next): Pipeline screen no longer loses state when navigating away
Fixed: gui_next/src/renderer/src/App.tsx: ScreenPipeline was unmounted by React Router on route change, wiping all useState (folders, queue, run status). Replaced the /pipeline Route with a KeepAlivePipeline wrapper that keeps the component permanently mounted and toggles visibility via display:none / display:contents.

[2026-05-28] — perf(gui_next): Collection screen now loads instantly on every visit
Added: backend/app.py: /api/collection/prefetch endpoint — bundles all 9 collection-screen datasets into a single HTTP response
Added: gui_next/package.json: @tanstack/react-query dependency
Changed: gui_next/src/renderer/src/App.tsx: wrapped app in QueryClientProvider; prefetch query fires at module load so cache is warm before user clicks Collection tab
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replaced version counter + 8-fetch Promise.allSettled + separate missing useEffect with a single useQuery (staleTime: Infinity); refetch now calls queryClient.invalidateQueries so mutations still trigger a reload

[2026-05-28] — fix(gui_next): Pipeline step pills now align under column headers
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: switched virtualizer from absolute-row to padding-based approach — absolute-positioned <tr> breaks table layout so colgroup widths don't apply to cells; replaced position:absolute+top with top/bottom spacer <tr> elements so real rows stay in normal table flow and the colgroup 110px step columns align correctly under their headers

[2026-05-28] — feat(gui_next): Pipeline live progress, column alignment, and Stop button
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: runSteps now processes folders one at a time (sequential fetch per folder) so each row updates as it completes; added stopRun + stopRef/abortRef to abort the in-progress run; StepPill accepts running prop and shows ··· in mute cells instead of — while processing; removed inline "running…" text from folder cell to restore column alignment; Stop button replaces Bulk actions in the top bar while a run is active

[2026-05-28] — chore(gui_next): dark mode palette shifted to neutral gray
Changed: gui_next/src/renderer/src/lib/tokens.ts: MODES.dark bg/surface/border/fg tokens replaced warm-brown values with flat neutral grays; mute status bg/fg/bar updated to match

[2026-05-29] — feat(gui_next): ScreenCollection — non-recursive Scan Directory + owned-aware ScanPreviewModal (TODO-124)
Added: backend/app.py: /api/pipeline/scan-dir route (POST {root, recursive}) — depth-1 or recursive walk matching LB-named folders; returns {entries: [{lb_number, folder_name, path}], skipped}
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: ScanPreviewModal component shows LB# / Folder / Path / Already Owned table (fetches /api/collection/lb_numbers for owned state), per-row Add buttons, and "Add all (N)" bulk action; handleScanDir (depth-1) and handleScanTree (recursive) are now distinct handlers both opening ScanPreviewModal; "Scan tree…" button wired to handleScanTree

[2026-05-29] — feat(gui_next): ScreenCollection — Notes column and editable Folder Name / Notes in AddFolderModal (TODO-123)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Notes column added to owned-collection table (reads c.notes from GET /api/collection); AddFolderModal FolderEntry now carries folderNameInput (editable, defaulted from path) and notesInput fields; both POSTed to /api/collection on add; colSpan updated 10→11 for virtualiser padding rows

[2026-05-29] — feat(gui_next): ScreenCollection — global Forum & Torrent History views + actionable per-row forum history (TODO-121)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: two new filter chips "All forum posts" (filter='forum_global') and "All torrents" (filter='torrent_global'); GlobalForumPanel renders GET /api/forum_posts with columns Posted/LB#/Show/Subject/Actions, actions: Open in Browser (window.open topic_url), Remove Record (DELETE /api/forum_post/<id> with confirm dialog), Go to LB (snaps back to 'all' filter and selects row); GlobalTorrentPanel renders GET /api/torrents with columns Created/LB#/Show/Filename/Status/Actions, actions: Add qBt (POST /api/qbt/add), Go to LB; both panels have a local search box; DetailPanel forum tab now fetches GET /api/entry/<lb>/forum_posts on open (like torrent tab) and shows per-post Open in Browser + Remove Record buttons with confirm dialog, replacing the old read-only pills

[2026-05-28] — feat(gui_next): ScreenCollection — per-torrent-record management in History tab (TODO-120)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: DetailPanel fetches GET /api/torrent/<lb> on open to load full TorrentRecord list; each record displays source-folder-exists and torrent-file-exists status dots; per-record action buttons: Add/Remove qBt, Regen (POST /api/torrent/create), Relocate Source (PATCH /api/torrent/<id>), Delete .torrent file (DELETE /api/torrent/<id>/file, with confirm dialog); forum tab unchanged; bottom "Regenerate" renamed to "Create torrent"

[2026-05-28] — feat(gui_next): ScreenCollection — personal rating, listen count, Log Listen in detail panel (TODO-119)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: DetailPanel fetches /api/collection/<lb>/meta on open; shows "My Rating" (personal_rating 1–5) and "Listens" (listen_count + last_listened) in meta grid; "Log Listen" button POSTs to /api/collection/<lb>/listen; "Edit Personal Info" button opens PersonalInfoModal from panel; saving via modal bumps personalSaveVer to refresh meta without full reload

[2026-05-28] — feat(gui_next): ScreenCollection — restore Missing (un-owned LB) view + CSV export (TODO-117)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: "Not in collection" chip backed by GET /api/collection/missing; separate table with LB# / LB Status / Date / Location / Rating / Description columns; Export CSV button; double-click row opens in Lookup
Changed: gui_next/src/renderer/src/components/table.tsx: added onDoubleClick prop to TR

[2026-05-28] — fix(gui_next): screen state lost on tab switch — move per-screen state to Zustand stores
Added: gui_next/src/renderer/src/lib/verifyStore.ts: Zustand store for ScreenVerify state (folders, results, activeIdx, showAll, filter) + exported types
Added: gui_next/src/renderer/src/lib/lbdirStore.ts: Zustand store for ScreenLBDIR state (all tab results, selections, filter, activeFolder)
Added: gui_next/src/renderer/src/lib/attachmentsStore.ts: Zustand store for ScreenAttachments persistent state (activeLb, search, statusFilter)
Changed: gui_next/src/renderer/src/lib/spectrogramStore.ts: extended with full screen state (folders, activeFolder, inventory, activeTrack, render settings, zoom); exported SpectroTrack type
Changed: gui_next/src/renderer/src/lib/lookupStore.ts: added filter, filterMy, activeSource fields so Lookup UI state survives navigation
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: use useVerifyStore — folders/results/filter/selections persist across tab changes
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: use useLbdirStore — folders, results, tab, selections persist
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: use useSpectrogramStore — folders, inventory, active track, render settings persist
Changed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: use useAttachmentsStore — active LB, search, status filter persist
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: use lookupStore for filter/filterMy/activeSource

[2026-05-28] — fix(gui_next): CSP missing img-src for Flask origin — spectrogram PNGs broken
Fixed: gui_next/src/renderer/index.html: added img-src http://127.0.0.1:5174 to CSP so <img> tags can load spectrogram PNGs from Flask (connect-src alone does not cover image requests)

[2026-05-28] — feat(gui_next): spectrogramStore + context-menu navigate to Spectrograms screen
Added: gui_next/src/renderer/src/lib/spectrogramStore.ts: Zustand store for pending folder queue (addPending / takePending)
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: drain pending folders from store on mount, auto-select first added folder
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: Generate Spectrograms context-menu action now seeds the store and navigates to /spectrograms

[2026-05-28] — feat(gui_next): row context menu + Personal Info modal in ScreenCollection (TODO-118)
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: ContextMenu component (right-click on any row, ESC/click-outside to dismiss); 7 actions: Open Folder, View LB Entry, Scrape Entry, Fingerprint Folder, Play in VLC, Generate Spectrograms, Edit Personal Info
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: PersonalInfoModal with personal_rating 1-5 and tags fields backed by GET/POST /api/collection/<lb>/meta
Added: backend/app.py: POST /api/open/vlc endpoint — launches VLC via gui.platform_utils.open_in_vlc
Changed: gui_next/src/renderer/src/components/table.tsx: added onContextMenu prop to TRProps/TR

[2026-05-28] — feat(gui_next): finish ScreenCollection wiring + AppShell nav badge (TODO-115)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: fetch GET /api/home/stats on mount; show collection_count as live count badge beside "My Collection" nav item
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: add removeProgress state; render inline progress bar during batch-remove DELETE loop

[2026-05-28] — docs: log gui_next My Collection parity gaps as TODO-117..128
Added: TODO.md: 12 tasks (TODO-117..128) capturing old collection_tab.py vs new ScreenCollection.tsx
  feature gaps from parity audit — Missing/Wishlist/Duplicates views, global Forum/Torrent History,
  per-torrent-record mgmt, Personal Info, row context menu, Notes, scan preview, bulk relocate,
  sorting, cross-tab nav. All backing Flask endpoints confirmed present in backend/app.py.

[2026-05-28] — feat(gui_next): wire all stub screens + new backend routes (gap audit)
Changed: gui_next/src/renderer/src/screens/ScreenBootlegs.tsx: add toast; wire Refresh LBBCD response handler
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: add wishlist add/remove toggle in detail panel
Changed: gui_next/src/renderer/src/screens/ScreenVerify.tsx: full backend wiring — folder IPC, verify/generate/retrieve, tool dots
Changed: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: full backend wiring — check/retrieve/reconcile/extras panes
Changed: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: full backend wiring — LB rail, file list, file viewer (text/html/image)
Changed: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: full backend wiring — inventory, generate/stop/poll, PNG display
Changed: gui_next/src/renderer/src/screens/ScreenLookup.tsx: full backend wiring — clipboard/listbox/files/folders sources, Zustand store
Changed: gui_next/src/renderer/src/screens/ScreenRename.tsx: consume useLookupStore, wire Apply renames → POST /api/rename/apply
Added: gui_next/src/renderer/src/lib/lookupStore.ts: Zustand store (sources, summary, detail, folderList)
Added: backend/app.py: POST /api/rename/apply (shutil.move + write_rename_log per item)
Added: backend/app.py: GET /api/spectrogram/png (serve PNG by absolute path for viewer)
Added: gui_next/src/main/index.ts: dialog:pickAndReadFiles IPC (multi-select + read)
Changed: gui_next/src/preload/index.ts: expose pickAndReadFiles
Changed: gui_next/src/renderer/src/env.d.ts: add pickAndReadFiles type

[2026-05-28] — chore(docs): close PLAN_GUI_WIRING.md — all 6 sprints done
Changed: gui_next/PLAN_GUI_WIRING.md → instructions/complete/PLAN_GUI_WIRING.md: plan complete, moved to archive
Added: TODO.md: TODO-115 (ScreenCollection remaining 10%), TODO-116 (ScreenPipeline remaining 5% stub)
Changed: TODO.md / TODO_DONE.md: closed TODO-094 (UI redesign), swept Done entries (113/110/108) out of TODO.md

[2026-05-28] — chore(gui_next): wire ScreenSpectrograms into router
Changed: gui_next/src/renderer/src/App.tsx: import ScreenSpectrograms, replace PlaceholderScreen on /spectrograms route

[2026-05-28] — feat(gui_next): TODO-114 — port ScreenLBDIR from source JSX
Added: gui_next/src/renderer/src/screens/ScreenLBDIR.tsx: four sub-tabs (Check/Retrieve/Reconcile/Extras), folder queue rail with state dots, per-file MD5+shntool detail table with side inspector, retrieve results table, reconcile rename proposals, extras deletion UI with controlled checkboxes
Changed: gui_next/src/renderer/src/App.tsx: wire /lbdir route to ScreenLBDIR, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-113 — port ScreenLookup from source JSX
Added: gui_next/src/renderer/src/screens/ScreenLookup.tsx: sources rail (clipboard/listbox/files/folders), 5-state status counter bar (matched/incomplete/not-found/duplicate/xref), per-LB summary table with filterable state, per-checksum detail table, help banner, footer with Rename link and Confirm matches action
Changed: gui_next/src/renderer/src/App.tsx: wire /lookup route to ScreenLookup, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-112 — port ScreenRename from source JSX
Added: gui_next/src/renderer/src/screens/ScreenRename.tsx: 5 row states (has_lb/needs_rename/wrong_lb/multiple_ids/no_match), state filter chips, bulk action bar with checkbox selection, expandable disambiguation rows for multi-LB conflicts, dry-run banner
Changed: gui_next/src/renderer/src/App.tsx: wire /rename route to ScreenRename, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-111 — port ScreenSpectrograms from source JSX
Added: gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx: folder rail with batch progress, track rail with PNG inventory, spectrogram viewer (.lbb-spec-canvas), thumbnail strip, render options (width/height/dB floor/window), SHN skip warning

[2026-05-28] — feat(gui_next): TODO-110 — port ScreenVerify from source JSX
Added: gui_next/src/renderer/src/screens/ScreenVerify.tsx: folder queue rail, 7-stat cards, MD5/FFP/ST5 detail table, shntool error state, per-file inspector panel
Changed: gui_next/src/renderer/src/App.tsx: wire /verify route to ScreenVerify, replacing PlaceholderScreen

[2026-05-28] — feat(gui_next): TODO-109 — port ScreenAttachments from source JSX
Added: gui_next/src/renderer/src/screens/ScreenAttachments.tsx: three-column layout (LB rail, file list, viewer); viewer dispatches on kind: text/html/image/binary
Changed: gui_next/src/renderer/src/App.tsx: wire /attachments route to ScreenAttachments, replacing PlaceholderScreen

[2026-05-28] — feat(backend,gui): TODO-107 — master publish upload progress via GitHub REST API
Changed: backend/app.py: /api/master/github_release now streams SSE; replaces gh CLI subprocess with requests + gh auth token; uploads .db and manifest in 1 MB chunks with byte-accurate progress events
Changed: gui/setup_tab.py: _GithubReleaseThread consumes SSE stream; adds progress signal (label, pct); _on_publish_progress switches progress bar from indeterminate to determinate during upload

[2026-05-28] — feat(gui_next): TODO-108 — port ScreenMap from source JSX
Added: gui_next/src/renderer/src/screens/ScreenMap.tsx: filter rail (year range + decade chips, ownership toggle, LB status radio), static world map with absolute-positioned pin buttons, selected-venue side panel
Changed: gui_next/src/renderer/src/App.tsx: replace PlaceholderScreen with ScreenMap on /map route

[2026-05-28] — feat(gui_next): Sprint 6 — wire ScreenThemes (~44% → 100%)
Changed: gui_next/src/renderer/src/lib/tokens.ts: add Font/FontSize types, FONT_STACKS, FONTS/FONT_SIZES exports, DEFAULT_THEME export; extend ThemeOptions with font/fontSize/customTokens; update applyTheme to set --lbb-font and --lbb-font-size CSS vars and apply customTokens; update loadTheme to load/validate new fields
Changed: gui_next/src/renderer/src/index.css: font-family and font-size now driven by --lbb-font/--lbb-font-size CSS variables (defaults preserved in :root)
Added: gui_next/src/main/index.ts: dialog:saveFile IPC (showSaveDialog + writeFile) and dialog:pickAndReadFile IPC (showOpenDialog + readFile)
Changed: gui_next/src/preload/index.ts: expose saveFile and pickAndReadFile via contextBridge
Changed: gui_next/src/renderer/src/env.d.ts: add saveFile and pickAndReadFile to Window.api
Changed: gui_next/src/renderer/src/screens/ScreenThemes.tsx: typeface buttons wired (onClick setTweak font, active state, per-button font preview); font size 12/13/14pt buttons replace static text; Custom color tokens button toggles inline CustomTokenEditor (7 CSS tokens, color inputs, per-token reset, reset-all); Export JSON calls window.api.saveFile; Import JSON calls window.api.pickAndReadFile → parse/validate/apply; Toast component added
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 6 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 5 — wire ScreenBootlegs (79% → 100%)
Changed: gui_next/src/renderer/src/screens/ScreenBootlegs.tsx: Year filter popover (derived from loaded rows, sorted descending; active-highlight; outside-click close); CDs filter popover (All / 1 CD / 2 CDs / 3+ CDs; active-highlight; outside-click close); both wired into filteredRows useMemo and clearFilters; Export CSV button wired — Blob download of filteredRows as losslessbob_bootlegs.csv
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 5 marked done; audit table updated

[2026-05-28] — feat(gui_next,backend): Sprint 4 — wire ScreenHome to backend (70% → 100%)
Added: backend/app.py: GET /api/activity/log — unified activity feed from flat_file_releases, rename_history, forum_posts; supports ?limit= param
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: "Check for DB update" wired to /api/flat_file/discover with busy state + toast; "View full log" wired to open full-log modal fetching /api/activity/log?limit=0; Recent activity table renders real rows from /api/activity/log?limit=10 with colour-coded type dots; Toast component added; local fmtActivity + TYPE_COLOUR helpers
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 4 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 3 — wire ScreenSearch to backend (69% → ~95%)
Changed: gui_next/src/renderer/src/screens/ScreenSearch.tsx: all stubs wired; row click opens EntryDetailPanel fetching /api/entry/<lb> with description/setlist/files/scrape action; sort popover (6 client-side sort options, localStorage); CSV export via Blob download; Group-by-year toggle with active highlight; Columns visibility popover with localStorage persistence; Saved views (3 built-ins + user-created stored in localStorage with delete); owned field fixed — fetches /api/collection/lb_numbers on mount; per-row ⋯ menu (position:fixed, Scrape entry action); Toast component added
Changed: gui_next/PLAN_GUI_WIRING.md: Sprint 3 marked done; audit table updated

[2026-05-28] — feat(gui_next): Sprint 2 — wire ScreenCollection to backend (33% → 90%)
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: full rewrite; all 17 stubs wired; Export HTML/M3U blob downloads; Reveal on disk via openPath IPC; Remove with confirm dialog + DELETE /api/collection/<lb>; Add single folder via pickFolders → AddFolderModal with per-row LB# input; Scan directory/tree via pickDir → /api/pipeline/scan-tree → same modal; Update location via pickDir → PATCH /api/collection/<lb>; All years filter with popover dropdown from /api/search/years; Xref only checkbox from /api/checksums/xref_lb_numbers; Create torrent/Add to qBt header buttons act on checked/selected rows; Regenerate torrent and Post to forum (with BBCode preview modal) in detail panel; Attachments/Spectrograms/Map stub toasts; added lbNumberInt and isXref fields to CollectionRow; version-bump refetch pattern

[2026-05-27] — feat(gui_next,backend): IntegCard clear-credentials + DELETE credential endpoints
Added: backend/app.py: DELETE /api/credentials/qbt — removes qBt username/password and API key from keyring
Added: backend/app.py: DELETE /api/credentials/wtrf — removes WTRF credentials from keyring
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: IntegCard gains optional onClear prop; shows inline "Clear creds → Sure? / Yes, clear / Cancel" confirmation flow; handleQbtClear and handleWtrfClear handlers added

[2026-05-27] — fix(gui_next): ScreenSetup Integrations — Admin web UI card + Torrent Settings card
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: renamed "Torrent web UI" stub → "Admin web UI" (wired to /admin + web_password setting); added 4th "Torrent Settings" card with tracker list dropdown and Refresh Trackers button; added web_password/tracker_list to AppSettings interface; added handlers handleWebUiSave, handleWebUiTest, handleTrackerListChange, handleRefreshTrackers; Integrations grid changed from 3→4 columns

[2026-05-27] — feat(gui_next,backend): Sprint 1 — wire ScreenSetup to backend (6% → 100%)
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: full rewrite; all 16 stubs wired to Flask endpoints; real DB stats, master status, flat file history, helpers status loaded on mount; confirm dialogs, toast feedback, inline integration edit forms
Added: gui_next/src/main/index.ts: pickFile IPC handler (dialog:pickFile)
Added: gui_next/src/preload/index.ts: window.api.pickFile() bridge
Added: gui_next/src/renderer/src/env.d.ts: pickFile type declaration
Added: backend/app.py: POST /api/credentials/wtrf — save WTRF credentials to keyring
Added: backend/app.py: POST /api/credentials/qbt — save qBt credentials to keyring
Added: backend/app.py: POST /api/rename_history/purge — clear rename_history (lookup history)
Added: backend/app.py: POST /api/flat_file/purge — clear flat_file_releases + flat_file_changelog
Added: backend/app.py: POST /api/scraper/purge — clear scrape_sessions + site_inventory
Added: backend/app.py: POST /api/fingerprint/purge — delete fingerprints.db file
Changed: backend/app.py: /api/db/settings GET now includes data_dir in response
Changed: backend/app.py: /api/spectrogram/check GET now includes flac_available

[2026-05-27] — fix(gui_next): resolve TypeScript errors in ScreenPipeline and table components
Fixed: gui_next/src/renderer/src/components/table.tsx: added onClick to TDProps/TD and style to GroupRowProps/GroupRow
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: cast File to Electron-extended type with path property

[2026-05-27] — fix(gui,backend): master publish progress bar + timeout increase
Added: gui/setup_tab.py: indeterminate QProgressBar shown during export+upload, hidden on success or error
Fixed: backend/app.py: gh subprocess timeout raised from 120s → 600s (was hitting limit on large snapshots); error message updated to match
Fixed: gui/setup_tab.py: requests timeout raised from 150s → 660s to match backend

[2026-05-27] — fix(gui_next): fix Collection table column alignment with virtualizer
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replaced position:absolute rows with spacer-row pattern so tbody rows stay in normal table flow and colgroup widths apply correctly; widened Confirmed column from 90→160px

[2026-05-27] — fix(gui_next): auto-start Flask backend from Electron main process
Changed: gui_next/src/main/index.ts: spawn run_backend.py if port 5174 is not already open; wait for port before creating the window; kill child on quit

[2026-05-27] — feat(gui_next,backend): wire Collection screen to existing backend endpoints
Changed: backend/db.py: extend get_collection() SELECT to include e.description, e.rating, e.cdr
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: replace single /api/collection fetch with Promise.allSettled of 6 existing endpoints (fingerprint/lb_numbers, wishlist, collection/duplicates, forum_posts, torrents); merge into CollectionRow[] client-side matching old GUI pattern

[2026-05-27] — fix(gui_next,backend): wire Pipeline folder-add, scan-tree, and Open actions
Fixed: gui_next/src/main/index.ts: add ipcMain.handle for dialog:pickFolders, dialog:pickDir, shell:openPath
Fixed: gui_next/src/preload/index.ts: expose pickFolders/pickDir/openPath via contextBridge
Fixed: gui_next/src/renderer/src/env.d.ts: add new methods to Window.api interface
Added: backend/app.py: POST /api/pipeline/scan-tree — walks root dir, returns subdirs containing audio files
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: wire "Add folders…" (×2) to pickFolders, "Scan tree…" (×2) to pickDir+scan-tree, "Open" to openPath

[2026-05-27] — feat(gui_next): Phase 4c — My Collection screen with virtualizer, filter chips, and detail panel
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: full Collection screen — heading row with export/qBittorrent buttons, stateful filter chips (All/Missing/Wishlist/Duplicates/Forum/Torrent/Unconfirmed/No FP), inline action toolbar, TanStack-virtualized 10-col table (edge bars, checkbox, LB#, Status, Date, Location, Folder, Disk path, Confirmed, FP), slide-in 360px detail panel (pill row, ID+title block, meta grid, action buttons, history sub-tabs); backend fetch against GET /api/collection with SAMPLE_DATA fallback
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen at /collection with ScreenCollection

[2026-05-27] — feat(gui_next): Phase 3 — curator mode toggle, Setup screen, and gated route guards
Added: gui_next/src/renderer/src/screens/ScreenSetup.tsx: full Setup screen — Database card, Master Data card with animated curator toggle (44×24 knob, warn-tinted icon, persist via Zustand), Integrations card (3-col qBit/forum/web), Preferences card, Data purges card, Flat file history table
Changed: gui_next/src/renderer/src/App.tsx: /setup now routes to ScreenSetup; /dbeditor and /scraper wrapped in CuratorRoute guard (redirects to / when curatorMode is false); added Navigate import and CuratorRoute component

[2026-05-27] — feat(gui_next,backend): Phase 4a Pipeline screen — batch ingest workflow with virtualizer, selection, drag-drop, backend integration
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: full pipeline screen — top progress banner, folder queue rail, virtualised table (TanStack), filter chips, selection bar with shift-click/⌘A, drag-drop folder ingestion, per-row and bulk apply renames; calls POST /api/pipeline/run and POST /api/folder/rename
Added: backend/app.py: POST /api/pipeline/run — runs verify/lookup/rename/lbdir steps on a list of folders, returns PipelineRow-shaped results
Added: backend/app.py: POST /api/folder/rename — renames a folder on disk to a new name within the same parent directory
Changed: gui_next/src/renderer/src/App.tsx: replaced PlaceholderScreen at /pipeline with ScreenPipeline
Added: gui_next/package.json: @tanstack/react-virtual ^3.13.26

[2026-05-27] — feat(gui_next,backend): Phase 4b Home/Dashboard screen wired to real backend data
Added: gui_next/src/renderer/src/screens/ScreenHome.tsx: full Home screen — welcome strip, hero ingest card with 4-step pipeline strip, At a glance stats, Jump to tiles, recent activity table (placeholder), Tips card; fetches /api/home/stats on mount
Added: backend/app.py: GET /api/home/stats — single-query route returning collection_count, wishlist_count, missing_count, bootleg_count, checksum_count, latest_lb, last_import
Changed: gui_next/src/renderer/src/App.tsx: replaced PrimitivesScreen at / with ScreenHome; import added

[2026-05-27] — feat(gui_next): Phase 2 app shell — Sidebar, Topbar, StatusBar, AppShell, Zustand settings store, react-router routing
Added: gui_next/src/renderer/src/store.ts: Zustand settings store with curatorMode persisted to localStorage
Added: gui_next/src/renderer/src/components/AppShell.tsx: Sidebar (224px, NAV_GROUPS, curator promo, user chip), Topbar (breadcrumbs, search, bell), StatusBar (DB stats), AppShell (composes all; reads active route from react-router, curatorMode from store)
Changed: gui_next/src/renderer/src/components/index.ts: barrel-export AppShell + AppShellProps
Changed: gui_next/src/renderer/src/App.tsx: replaced smoke-test root with HashRouter + AppShell + all 16 placeholder routes; PrimitivesScreen moved to /home route
Changed: instructions/gui_redesign/README.md: Phase 3 app shell marked ✅ Done; 3b curator mode marked 🔄 In Progress (gating works, toggle not in settings UI yet)
Changed: instructions/gui_redesign/13-implementation-plan.md: Phase 2 marked ✅ Done, Phase 3 promoted to NEXT
Verified: sidebar nav active-state, breadcrumbs, curator promo card, status bar — all confirmed via Firefox headless screenshots at /home and /pipeline routes

[2026-05-27] — feat(gui_next): Phase 1 primitives — Icon, Pill, Chip, Button, IconButton, Input, Kbd, Card, Toolbar, Banner, Stat, SectionHead, TableShell, TH, TR, TD, GroupRow
Added: gui_next/src/renderer/src/components/Icon.tsx: embedded LBB icon paths (Lucide-compatible), no added dependency
Added: gui_next/src/renderer/src/components/primitives.tsx: all 11 primitive components, full TypeScript prop types
Added: gui_next/src/renderer/src/components/table.tsx: TableShell+TH+TR+TD+GroupRow; TR injects 3px edge-bar <td> automatically
Added: gui_next/src/renderer/src/components/index.ts: barrel re-export of all components and types
Changed: gui_next/src/renderer/src/App.tsx: smoke-test UI exercises all primitives (stats, pills, buttons, input, table with edge bars and grouping)
Changed: instructions/gui_redesign/README.md: Phase 2 primitives marked ✅ Done
Changed: instructions/gui_redesign/13-implementation-plan.md: Phase 1 items 3-5 marked ✅ Done; Phase 2 marked 🔲 NEXT

[2026-05-27] — feat(gui_next): Phase 1 design tokens — theme engine, global CSS, font wiring
Added: gui_next/src/renderer/src/lib/tokens.ts: TypeScript port of lbb-tokens.js — applyTheme/loadTheme/saveTheme, 2 modes × 8 accents × 3 densities, status palette, full type exports
Changed: gui_next/src/renderer/src/index.css: replaced placeholder with full app.css port (scrollbars, sticky headers, focus rings, density rows, kbd-pill, spec/map canvas helpers)
Changed: gui_next/src/renderer/index.html: CSP widened for Google Fonts; Inter + JetBrains Mono preloaded
Changed: gui_next/src/renderer/src/main.tsx: applyTheme(loadTheme()) called before React.createRoot to prevent FOUC
Changed: gui_next/src/renderer/src/App.tsx: placeholder updated to smoke-test tokens (swatches, status pills, mode/accent/density toggles)

[2026-05-27] — feat(gui_next): replace PyQt6 scaffold with Electron + React + Vite + TS project
Changed: gui_next/: removed __init__.py and main_window.py (PyQt6 stub); replaced with full Electron+Vite project
Added: gui_next/package.json: Electron 42, React 18, Vite 7, electron-vite 5, TypeScript 5 — zero audit vulnerabilities
Added: gui_next/src/main/index.ts: Electron main process — 1440×900 window, loads Vite dev server in dev / built files in prod
Added: gui_next/src/preload/index.ts: contextBridge exposes flaskBase (http://127.0.0.1:5174) to renderer
Added: gui_next/src/renderer/: React+TS entry, placeholder App.tsx, index.css with LBB warm-cream base

[2026-05-27] — chore: create feat/gui-redesign branch and gui_next scaffold
Added: gui_next/__init__.py: new package for redesigned UI
Added: gui_next/main_window.py: stub MainWindow scaffold (same constructor interface as gui/)
Added: run_next.py: launcher for gui_next — shares Flask backend (port 5174) and DB; logs to losslessbob_next.log

[2026-05-27] — fix(backend): master update GitHub publish crash
Fixed: backend/db.py: generate_release_notes() called .get() on a sqlite3.Row (unsupported); changed to subscript access o["manual_notes"] which returns None for NULL, preserving the existing truthiness check

[2026-05-26] — feat(gui): add/remove override buttons in DB Integrity panel
Added: gui/dbedit_tab.py: "Add Override…" button opens a dialog (LB#, status dropdown, notes) and calls PUT /api/lb_master/<lb>/manual; "Remove Override…" prompts for LB# and calls DELETE /api/lb_master/<lb>/manual; both refresh integrity stats on success

[2026-05-26] — fix(db): startup crash on old DBs missing public_no_checksums column
Fixed: backend/db.py: moved idx_lb_master_public_no_chk index out of SCHEMA_SQL (which ran before the migration that adds the column) and into a post-migration CREATE INDEX IF NOT EXISTS call; fixes sqlite3.OperationalError on existing databases

[2026-05-26] — docs: add data_ownership.md explaining master vs. user data split
Added: docs/data_ownership.md: documents MASTER_TABLES, USER_TABLES, MASTER_META_KEYS, USER_META_KEYS, export/import enforcement, and schema versioning

[2026-05-26] — fix(backend): downgrade guard for master import; bundle shntool.exe on Windows

Fixed: backend/db.py: import_master_db() now raises ValueError if the incoming snapshot's
  master_version is older than the currently installed one, preventing accidental data loss
  from installing a stale file. (BUG-112)
Changed: backend/checksum_utils.py: _find_shntool() on Windows now checks the bundled
  PyInstaller path (_MEIPASS/tools/shntool.exe) and the dev-tree path
  (project_root/tools/shntool.exe) before falling back to WSL or PATH. (TODO-091)
Changed: losslessbob.spec: added tools/shntool.exe to datas so PyInstaller bundles it
  into the Windows distribution under _internal/tools/. (TODO-091)
Fixed: BUGS.md/BUGS_DONE.md: closed BUG-113 (hardcoded table backgrounds) — fully
  addressed by the theme-live refactor committed earlier today.

[2026-05-26] — refactor(gui): make all color lookups theme-live; no more stale QColor snapshots

Changed

  gui/lbdir_tab.py: Removed _C_PASS/_FAIL/_MISSING/_NO_LB/_GREY module-level aliases and
    class-level _LB_STATUS_COLOR dict. All call sites now reference styles.* directly so
    each paint picks up the current theme without any signal wiring.

  gui/verify_tab.py: Same pattern; 7 module-level aliases removed.

  gui/rename_tab.py: Removed module-level _STATE_COLORS and _NFT_DISC_COLORS dicts; data()
    builds inline dicts on each call.

  gui/attachments_tab.py: Removed class-level _STATUS_BG dict; data() uses inline lookup.

  gui/bootlegs_tab.py, gui/search_tab.py: Removed module-level _BG_STATUS string dicts;
    data() returns styles.ROW_PRIVATE/ROW_GREY directly. Unused QColor import removed.

  gui/collection_tab.py: Removed module-level _BG_LB_STATUS string dict; both model
    data() methods use inline lookup. Unused QColor import removed.

[2026-05-26] — refactor(gui): extend theme token vocabulary and eliminate all hardcoded hex colors

Changed

  gui/styles.py: Added 21 new module-level constants (ROW_FAIL, ROW_MISSING_FILE, ROW_GREY,
    ROW_PRIVATE, ROW_WRONG_LB, ROW_MULTIPLE_IDS, ROW_DIRTY, ROW_AUDIT, ROW_READONLY,
    ROW_NFT_MISSING, ROW_NFT_STALE, ROW_NFT_UNKNOWN, STATUS_OK, STATUS_WARN, STATUS_ERROR,
    STATUS_NEUTRAL, FG_MUTED, FG_LINK, FG_DANGER, FG_SUCCESS, FG_WARNING). All wired into
    apply_theme() with theme-dict keys; defaults are Light-theme values.

  gui/theme_tab.py: All 13 named themes updated with dark-adapted values for every new token.
    COLOR_LABELS extended with 21 new swatch entries so users can customise them.

  gui/lbdir_tab.py, gui/verify_tab.py: _C_PASS/FAIL/MISSING/NO_LB/GREY aliases now reference
    styles.ROW_OWNED/FAIL/MISSING_FILE/DUPLICATE/GREY. Danger/muted inline styles tokenised.

  gui/rename_tab.py: ROW_STATUS_COLORS and NFT_STATUS_COLORS dicts replaced with styles tokens.
    Legend swatches updated to use .name() from the same tokens.

  gui/dbedit_tab.py: _C_DIRTY/WARN/AUDIT/RDONLY lazy-aliased to styles row tokens.
    setForeground calls use FG_MUTED/FG_DANGER/FG_LINK.

  gui/spectrogram_tab.py: Drop-zone and hint labels use FG_MUTED; dup highlight uses ROW_FAIL.

  gui/scraper_tab.py: All Bootstrap status-color dicts use STATUS_OK/WARN/ERROR/NEUTRAL.
    Count labels use FG_MUTED.

  gui/setup_tab.py: Reset button uses FG_DANGER. All 19 tool-status setStyleSheet("color: X")
    calls replaced with FG_SUCCESS/DANGER/WARNING. Migration status uses STATUS_* tokens.

  gui/attachments_tab.py, gui/bootlegs_tab.py, gui/search_tab.py: private/missing color
    dicts consolidated to ROW_PRIVATE/ROW_GREY (previously duplicated in 7 files).

  gui/lookup_tab.py: lb_status colors use ROW_PRIVATE/GREY; warning row uses
    ROW_MISSING_FILE/FG_WARNING.

  gui/collection_tab.py: All foreground color calls replaced with semantic FG_* tokens.

[2026-05-26] — feat(map): add geocoding cache purge (TODO-097)

Added

  backend/app.py: POST /api/geocode/purge — curator-only route; scope="failed" deletes rows
    where source='failed' or lat IS NULL; scope="all" deletes entire location_geocoded table.
    Returns {ok, deleted}.

  gui/map_tab.py: _PurgeGeoThread — background worker calling /api/geocode/purge.
    Two new buttons in the Geocoding group (curator-only): "Purge Failed/Null" and
    "Purge All…" (requires confirmation). Status label shows deleted row count and
    prompts user to re-run geocoder.

[2026-05-26] — feat(setup): one-click master update from GitHub Releases (TODO-088)

Added

  gui/setup_tab.py: _GitHubMasterThread — fetches latest release via GitHub API,
    streams the .db asset with progress reporting, verifies SHA256, saves sidecar
    manifest to data/imports/, then applies via existing /api/master/import route.
  gui/setup_tab.py: "Check for Updates" button in Master Data section; progress label
    shows download %; _on_check_github/_on_github_progress/_on_github_done handlers.

Changed

  gui/setup_tab.py: Renamed "Install Master Update…" button to "Install from File…"
    for clarity now that the primary path is the GitHub download.

---

[2026-05-26] — feat(map): add lb_number column to location_geocoded for override traceability (TODO-099)

Added

  backend/db.py: Added lb_number TEXT column to location_geocoded schema; migration via
    ALTER TABLE with try/except-style PRAGMA guard for idempotency.
  backend/geocoder.py: place_manual() now accepts optional lb_number parameter; stored on
    INSERT and preserved (COALESCE) on UPDATE.
  backend/app.py: POST /api/geocode/location reads lb_number from body and passes to
    place_manual(). GET /api/geocode/locations now JOINs entries to return lb_numbers
    (comma-separated list of all LBs using each location string).
  gui/map_tab.py: Location Overrides table expanded to 8 columns with LB# column;
    _on_geo_row_dblclick() includes lb_number in POST payload when present.

Changed

  PROJECT.md: location_geocoded schema updated to include lb_number column.

---

[2026-05-26] — feat(search): Public / no checksums filter in Search tab (TODO-095)

Added

  gui/search_tab.py: New "Public / no checksums" option in the status filter combo.
    Filters search results to lb_status='public' entries where public_no_checksums=1,
    surfacing entries that have a known webpage but zero checksum records in the DB.

Changed

  backend/db.py: All SELECT branches in search_entries() and get_entries_by_lb_list()
    now include lm.public_no_checksums so the flag is present in every search result row.

---

[2026-05-26] — feat(db): Dylan performances promoted to MASTER; lb_problems table added (TODO-086, TODO-090)

Added

  backend/db.py: `lb_problems` table in SCHEMA_SQL (id, lb_number FK→lb_master, notes, notes, added).
    Indexed on lb_number. Added 4 DB functions: get_lb_problems(), add_lb_problem(),
    update_lb_problem(), delete_lb_problem(), get_lb_problem_count().

  backend/db.py: `dylan_performances` added to MASTER_TABLES (was unclassified/USER).
    `lb_problems` also added to MASTER_TABLES. MASTER_SCHEMA_VERSION bumped 2→3.

  backend/app.py: GET /api/performances — query dylan_performances by ?date=, ?lb= (auto-resolves
    entry date_str to ISO), ?category=, with pagination.

  backend/app.py: GET /api/lb_problems, POST /api/lb_problems (curator-only),
    PUT /api/lb_problems/<id> (curator-only), DELETE /api/lb_problems/<id> (curator-only).

---

[2026-05-26] — fix(scraper): "Scrape All Missing Entries" no longer queues private LBs (TODO-100)

Fixed

  backend/app.py (/api/scrape/start): Build the scrape list with a LEFT JOIN to lb_master and
    exclude rows where lb_status = 'private'. Private LBs are handled exclusively by
    /api/scrape/private_rescrape ("Re-scrape Private LBs" button) to prevent the two actions
    from overlapping. Updated docstring to document the exclusion.

---

[2026-05-26] — fix(gui): curator panels not shown on map tab at startup if curator mode already enabled (BUG-109)

Fixed

  gui/main_window.py: curator_mode_changed fires during SetupTab.__init__ (via _load_curator_status)
    before MapTab is created and before the signal connection is wired. Added a one-shot
    set_curator_mode(curator_cb.isChecked()) call immediately after connecting the signal so the
    map tab reflects the persisted curator state on every startup, not just after toggling. (BUG-109)

---

[2026-05-26] — fix(gui): AppImage open-folder fix (BUG-110) + BUG-111/115/107 housekeeping

Fixed

  gui/platform_utils.py: open_folder() and open_file() on Linux now call
    QDesktopServices.openUrl(QUrl.fromLocalFile(p)) instead of subprocess.run(["xdg-open", ...]).
    In AppImage environments the modified PATH may hide system xdg-open; QDesktopServices
    is Qt-native and handles file-manager launch reliably regardless of PATH. xdg-open kept
    as a fallback if QDesktopServices returns False. (BUG-110)

  gui/setup_tab.py: _on_open_folder: replaced silent except Exception: pass with
    _log.warning() so failures are visible in the log rather than silently discarded. (BUG-110)

  backend/app.py: (previously fixed, now documented) The allowed_dirs containment check
    ("Snapshot must be in data/exports/ or data/imports/") was removed from
    /api/master/import. The route now accepts any readable .db file. (BUG-111)

Changed

  BUGS.md: moved BUG-110, BUG-111, BUG-115, BUG-107 (all Fixed) to BUGS_DONE.md.

[2026-05-26] — feat(db): lb_missing table (TODO-102) + public_no_checksums flag (TODO-098) + nonexistent status

Added

  backend/db.py: lb_missing table (INTEGER PK, confirmed_date, notes) — MASTER_TABLE seeded
    with 36 confirmed-not-existing LB numbers on init_db(). _LB_MISSING_SEEDS constant.
    is_lb_missing / add_lb_missing / remove_lb_missing / get_lb_missing_list CRUD functions.

  backend/db.py: public_no_checksums column on lb_master (INTEGER NOT NULL DEFAULT 0) and
    partial index idx_lb_master_public_no_chk. Set to 1 when lb_status='public' AND
    has_checksums=0 across all reconcile paths. Count exposed in get_lb_master_stats.

  backend/db.py: 'nonexistent' added as a 4th valid lb_status value (via table recreation
    migration that also adds public_no_checksums). lb_missing entries are classified
    'nonexistent' by all reconcile paths.

  backend/scraper.py: scrape_entry() returns {skipped, reason='nonexistent'} for lb_missing
    entries before any network or DB work.

  backend/app.py: GET/POST /api/lb_missing, DELETE /api/lb_missing/<lb> routes.

  tests/test_db_writes.py: TestLbMissing (8 tests) + TestPublicNoChecksums_Flag (6 tests).
    Total test count: 121 → 135.

[2026-05-26] — fix(db): reconcile_all_lb_master bails early when checksums table is empty (BUG-116b)

Fixed

  backend/db.py: reconcile_all_lb_master now includes MAX(entries.lb_number) when computing
    effective_max, so a fresh install with scraped entries but no checksums no longer short-
    circuits and leaves public-page LBs unclassified.

Added

  tests/test_db_writes.py: test_reconcile_all_no_checksums_public_entry regression test in
    TestPublicNoChecksums — seeds LB-1506 as status='ok' with no checksums, calls
    reconcile_all_lb_master, and asserts lb_status='public'.  All 6 tests in the class pass.

[2026-05-25] — test(db): add regression tests for public-page LB with no checksums (BUG-116)

Added

  tests/test_db_writes.py: TestPublicNoChecksums — 5 tests covering reconcile_lb_status,
    batch_reconcile_lb_status, missing→public transition, get_missing_lb_numbers exclusion,
    and _compute_lb_status(True, False, False) unit check.  All pass; regression guard for
    BUG-116 (reconcile_all_lb_master edge case with zero checksums remains open).

[2026-05-25] — fix(scraper): batch-repair 61 missing entries that had locally cached pages

Fixed

  backend/scraper.py / data: Ran scrape_entry(use_local_pages=True) over all 103 missing
    lb_master entries.  61 had locally cached pages with real content (saved by
    download_pages_range but never parsed after the entry was marked missing).  All 61 now
    have lb_status='public' with parsed metadata.  42 remain missing (no local page);
    a live network scrape will re-check those automatically with the new skip-logic fix.

[2026-05-24] — fix(geocoder): bump performances-sourced confidence from low → medium

Fixed

  backend/geocoder.py: After setting source='performances', promote confidence 'low' → 'medium'
    because Nominatim's importance score penalises specific venues (stadiums, conference centres)
    even when the structured venue+city+state+country query is accurate.  The label 'low' was
    misleading for geocodes that are correct.
  backend/db.py: One-time migration to retroactively fix existing location_geocoded rows where
    source='performances' AND confidence='low'.

[2026-05-24] — fix(scraper): live scrapes now re-check entries previously marked missing

Fixed

  backend/scraper.py: Skip condition for `status='missing'` entries changed from
    `not (use_local_pages and local_page.exists())` to `use_local_pages and not local_page.exists()`.
    Old logic always skipped missing entries during live network scrapes, so pages added to the
    archive after the initial scrape were never rediscovered.  New logic: live scrapes always
    re-fetch missing entries from the server; local-page mode skips only when no local file exists.
    LB-05126 was repaired in-place by re-scraping from its locally cached page (now public, 10/12/89).

[2026-05-24] — fix(db): rewrote DatabaseWriteQueue._worker — isolation_level=None, explicit BEGIN/COMMIT/ROLLBACK, startup ready-event; fixed implicit transaction leak in init_db(); added conftest.py test isolation fixture; updated stale TestWriteConnectionRollback tests

Changed

  backend/db_queue.py: _run() now opens the writer connection with isolation_level=None so
    Python's sqlite3 module never issues implicit BEGIN/ROLLBACK of its own. Transaction
    boundaries are fully explicit: BEGIN before fn(), COMMIT on success, ROLLBACK on error.
    Removed PRAGMA busy_timeout=0 — contention on the single writer is a bug, not a condition
    to mask with a timeout. Increased cache_size to -32000 pages. Added a _ready Event so
    __init__() blocks until the writer has finished its PRAGMA setup (including
    journal_mode=WAL) before returning — eliminating the race between the writer thread and
    init_db()'s get_connection() call on a brand-new database file. shutdown() now also closes
    the writer connection after the thread joins.

  backend/db.py: init_db() now calls conn.commit() unconditionally after the soft-404 UPDATE,
    regardless of rowcount. Previously a zero-row UPDATE left an implicit Python transaction
    open on the read connection, holding a RESERVED lock that blocked the write queue's first
    transaction on every fresh (empty) database.

  conftest.py (new): autouse pytest fixture that shuts down and resets the DatabaseWriteQueue
    singleton and thread-local read connections between every test, preventing the singleton
    from routing writes to the first test's database file in subsequent tests.

  tests/test_db_writes.py: TestWriteConnectionRollback updated to use get_write_queue().execute()
    instead of the removed db.write_connection() context manager.

Fixed

  backend/db_queue.py: "database is locked" OperationalError in site_crawler and
    lb_master_reconcile caused by BEGIN IMMEDIATE competing with Python's implicit transaction
    management on the same connection.

[2026-05-24] — feat(geocoder): performances-table lookup before Nominatim geocoding (TODO-087)

Changed

  backend/geocoder.py: run_batch() now checks dylan_performances for each location before
    calling Nominatim. _entry_date_to_iso() converts M/D/YY entries.date_str to YYYY-MM-DD;
    _get_performance_location_string() scans associated dates and returns a structured
    "venue, city, state, country" query string. If a match is found, that string is geocoded
    and stored with source='performances' + note showing the derived query for provenance.
    Falls back to the raw entries.location text when no performance record exists.
    UPSERT now keys by the raw location text (not the geocode input) so the existing
    map JOIN (entries.location = geo.location_text) remains intact.

Added

  backend/db.py: get_performance_by_date(date_str) — public helper returning the
    dylan_performances row for an ISO date string; logs a warning on rare same-date doubles.

[2026-05-24] — fix(fingerprint): emit scan-progress updates so UI shows activity during initial folder scan

Fixed

  backend/fingerprint.py: build_fingerprint_db() now emits status="scanning" with folder
    progress every 50 rows during the initial file-collection phase, so the GUI label
    updates from "[0/0]" instead of appearing frozen during large collection scans.

  gui/spectrogram_tab.py: _on_fp_build_status() handles status="scanning" by updating
    the build label and returning early (no queue/count changes during scan phase).

---

[2026-05-24] — fix(attachments): route _RefreshTreeThread through Flask API to fix "database is locked" (BUG-114)

Fixed

  gui/attachments_tab.py: Removed direct get_connection() calls from _RefreshTreeThread.
    Thread now calls POST /api/attachments/reconcile then GET /api/attachments/cached via
    HTTP (requests). Removed the backend.db import entirely. Constructor now takes flask_port.

Added

  backend/app.py: POST /api/attachments/reconcile — runs the UPDATE entry_files SET
    downloaded=1 reconcile query inside Flask's connection and returns {updated: N}.
    GET /api/attachments/cached — returns grouped entry_files data + total checksums count
    as {entries: [...], total: N}, replacing the in-thread SELECT.

[2026-05-24] — fix(gui): switch QT_QPA_PLATFORM to wayland, fixing BUG-090 black screen flickers

Fixed

  main.py: default QT_QPA_PLATFORM changed from "xcb" to "wayland" on Linux. Running under
    XWayland was causing intermittent black screen flickers due to compositor interaction with
    Qt's rendering pipeline. Native Wayland eliminates the issue. User env override still honoured.

[2026-05-24] — feat(fingerprint): fingerprinting queue preview with prominent progress counter and up-next list

Added

  backend/fingerprint.py: queue_preview state key — build_fingerprint_db() now emits the next 10 filenames
    (relative "parent/name" form) after the current position on every state update, clearing to [] when done.

  backend/app.py: GET /api/fingerprint/build/queue endpoint returning {pending: N, preview: [...]}.
    queue_preview added to _fp_build_state initial dict so /api/fingerprint/build/status also carries it.

  gui/spectrogram_tab.py: Fingerprint DB sub-tab now shows a bold "X of Y" count label and a QListWidget
    (≤15 rows, "Up next:" header) that updates every 800 ms during a build. _FpBuildStatusThread.run()
    fetches both /status and /queue per tick and merges results into a single emitted dict.

---

[2026-05-24] — feat(collection): add "Play in VLC" context menu action for My Collection entries

Added

  gui/platform_utils.py: open_in_vlc(paths) — cross-platform VLC detection (PATH, common Windows/macOS install
    locations) and subprocess launch. Returns (bool, error_msg) so callers can surface failures gracefully.

  gui/collection_tab.py: "Play in VLC" context menu item in My Collection. Enabled when selected row(s) have a
    valid disk_path on disk. Multiple rows pass all their folder paths to one VLC instance as a playlist.
    Shows a QMessageBox.warning if VLC is not found rather than silently failing.

---

[2026-05-24] — DB-09: Replace ad-hoc write_connection() locking with DatabaseWriteQueue

Changed

  backend/db_queue.py: New module. DatabaseWriteQueue holds ONE persistent sqlite3 connection
    and serialises every write via queue.Queue + threading.Event. All callers call
    get_write_queue().execute(fn) or .execute_async(fn); fn(conn) runs exclusively in the
    single writer thread — eliminating all concurrent-writer races under WAL mode.
  backend/db.py: All write_connection() call sites migrated to get_write_queue().execute();
    write_connection() removed. _write_lock retained only for import_master_db() ATTACH/DETACH
    workflow. Singleton initialised inside init_db().
  backend/scraper.py: Five write_connection() call sites replaced with get_write_queue().
    PRAGMA optimize kept as direct get_connection() op (not DML, no lock needed).
  backend/site_crawler.py: One write_connection() call site replaced.
  backend/app.py: Two database.write_connection() calls (dbedit row update/delete) replaced;
    rowcount returned through queue result box.
  backend/importer.py: Chunked executemany merge submitted as single queue item (timeout=300s).
  backend/flat_file.py: All four write functions (discover, download, apply, defer) routed
    through write queue. apply_flat_file_release() pre-computes all mutations as Python lists
    and submits one atomic executemany batch; set_meta calls follow after queue item commits.
  backend/geocoder.py: save_manual_geocode() and per-iteration run_batch() writes routed
    through write queue.

Fixed

  sqlite3.OperationalError: database is locked — root cause was multiple threads opening
    concurrent write_connection() calls, each racing for the WAL write lock. The write queue
    removes the race entirely.

[2026-05-23] — fix(db): use BEGIN IMMEDIATE in write_connection to prevent database-locked race

Fixed

  backend/db.py: write_connection() now issues BEGIN IMMEDIATE before yielding, acquiring
    the WAL write lock before any reads. Prevents SQLITE_BUSY when out-of-band writers
    (e.g. PRAGMA optimize/ANALYZE from scraper) hold the SQLite write lock after reconcile
    has already completed its read phase. Nested calls detect conn.in_transaction=True and
    skip inner BEGIN/COMMIT so the outermost call owns the transaction.
  backend/scraper.py: PRAGMA optimize at end of scrape_range moved into write_connection
    so it goes through _write_lock instead of competing with other writers outside Python's
    serialisation layer.

[2026-05-23] — fix(scraper): eliminate 15 s startup block from synchronous HTTP calls in ScraperTab

Fixed

  gui/scraper_tab.py: Three methods (_load_crawler_settings, _load_sessions_history,
    _load_bootlegs_history) were making synchronous requests.get/post calls on the main Qt
    thread, each with a 5 s timeout. Additionally, _load_crawler_settings was triggering
    _save_crawler_settings and _save_entry_settings via valueChanged/stateChanged signals as it
    set widget values, causing further blocking POSTs. Combined effect: ~15 s startup freeze.
    Fix: all three methods now fire a _Worker thread and populate widgets via finished signal.
    _load_crawler_settings uses blockSignals() while applying loaded values to suppress the
    spurious save cascade.
  gui/scraper_tab.py: _refresh_pages_count() was also calling glob("*.html") synchronously.
    Replaced with os.scandir() in a _Worker thread (contributing fix from previous attempt).

[2026-05-23] — fix(db): reconcile_all_lb_master uses batch write to fix database-locked error

Fixed

  backend/db.py: reconcile_all_lb_master() replaced per-LB reconcile_lb_status() loop
    (acquires/releases _write_lock N times) with a single batch_reconcile_lb_status() call,
    eliminating the sqlite3.OperationalError: database is locked caused by concurrent writers
    fighting over the lock across thousands of iterations.
  backend/app.py: /api/lb_master/reconcile route now holds _reconcile_lock (non-blocking
    acquire) and returns 409 if a reconcile is already in progress, preventing two simultaneous
    reconcile requests from interleaving writes.

[2026-05-23] — feat(db): import dylan_performances table from ODS on first startup

Added

  backend/db.py: new dylan_performances table (event_id PK, date_str, category, city,
    state, country, venue) added to SCHEMA_SQL with indexes on date_str, category, country.
  backend/db.py: import_dylan_performances() function — one-time ODS parser using stdlib
    zipfile + ElementTree; skips if table already populated; wired into init_db() background
    thread. Source file: data/2026-05-22_Dylan_Performance_fixed.ods (5,129 rows).

---

[2026-05-23] — feat(db): flat_file_apply inserts new LBs as 'public' instead of 'private'

Changed

  backend/db.py: reconcile_lb_status() and batch_reconcile_lb_status() now initialise
    brand-new lb_master rows to 'public' when trigger='flat_file_apply' and the computed
    auto_status would have been 'private' (checksums-only, no web presence). The scraper
    can still demote to 'private' after it confirms no web entry exists. Existing rows
    and any other trigger are unaffected.

[2026-05-23] — feat(map): display LB number on individual map dots

Changed

  gui/resources/map.html: Replaced L.circleMarker with L.divIcon + L.marker so each
    single-concert dot renders the LB number as centred text inside the coloured circle.
    Visual style (colour, owned gold ring, shadow) is preserved.

[2026-05-23] — fix(scraper): detect soft-404 pages (server returns HTTP 200 with error body)

Fixed

  backend/scraper.py: Added _SOFT_404_MARKER constant and _is_soft_404() helper.
    scrape_entry() now checks the HTML content for the server's soft-404 signature
    before parsing; treats it as a true 404 (deletes bad cached page, marks entry
    missing, returns {"error": "404", "missing": True}).

  backend/db.py: init_db() now runs a one-time cleanup UPDATE that finds existing
    entries whose description contains the soft-404 error text and resets them to
    status='missing' with cleared fields. Rebuilds the FTS index afterwards if any
    rows were affected. 68 previously bad entries will be fixed on next app start.

[2026-05-23] — feat(gui): platform-aware install hints for SoX, ffmpeg, shntool (TODO-086)

Changed

  gui/setup_tab.py: Added _sox_tool_hint() static helper that returns an HTML
    install hint (with clickable download link) for each external tool based on
    sys.platform — winget commands on Windows, brew on macOS, apt on Linux.
    SoX, ffmpeg, and shntool status labels now use RichText format with
    setOpenExternalLinks(True) so links are clickable. Windows shntool hint
    notes no native package and suggests WSL or Chocolatey as alternatives.
  backend/sox_utils.py: Replaced hard-coded Linux install commands in
    SoxNotFoundError, ConversionError (ffmpeg missing), and SpectrogenError
    (PNG support missing) with dict-based platform lookups covering win32,
    darwin, and Linux defaults.

[2026-05-23] — docs(backend): update stale docstrings referencing old data/pages/ and data/attachments/ paths

Changed

  backend/scraper.py: Updated download_pages_range docstring — save path is now
    data/site/detail/LB-{n:05d}.html (was data/pages/).
  backend/app.py: Updated /api/download-pages docstring and _start_scrape_thread
    docstring to reference data/site/detail/ instead of data/pages/.
  backend/forum_poster.py: Updated three attachments_dir parameter docstrings
    to reference data/site/files/ instead of data/attachments/LB-XXXXX/.

[2026-05-23] — fix(backend): fix master DB install failing with "internal_error" on Windows (BUG-105)

Changed

  backend/app.py: Removed is_curator() guard from master_import route — export stays
    curator-only but import is open to all (design intent: "Curator publishes, end users
    install"). Removed the path_not_allowed directory-containment check that blocked
    selecting a snapshot from outside data/exports/ or data/imports/ (e.g. USB drive or
    Downloads folder); kept the .db suffix check. Added sqlite3.Error to the caught
    exception list so SQLite failures (ATTACH, VACUUM INTO backup, table operations)
    surface a real error message instead of bare "internal_error". Added "message" field
    to the generic internal_error response. Added import sqlite3 at module level.

[2026-05-23] — fix(db): serialise upsert_inventory writes through _write_lock to prevent DB locked errors

Fixed

  backend/db.py: upsert_inventory() was calling get_connection() directly and committing
    outside the _write_lock, allowing concurrent Flask/crawler writes to race. Swapped to
    write_connection() context manager so all writes go through _write_lock.
  backend/site_crawler.py: inline entry_files downloaded=1 update also used get_connection()
    directly; swapped to write_connection(). Replaced now-unused get_connection import with
    write_connection.

[2026-05-23] — feat(release): add Docker image build and push to GHCR in release workflow

Added

  .github/workflows/release.yml: build-docker job — logs in to ghcr.io with GITHUB_TOKEN,
    uses docker/metadata-action to tag semver + sha + latest (latest only on tag pushes),
    builds with docker/build-push-action and GHA layer cache.
  .github/workflows/release.yml: added packages: write to top-level permissions so
    GITHUB_TOKEN can push to GitHub Container Registry.
  .dockerignore: added secrets/ so credential files are never copied into the image.

---

[2026-05-23] — docs(website): remove macOS install option, add Docker install card

Changed

  docs/index.html: removed macOS install card; added Docker card (docker compose up → noVNC at
    localhost:6080); updated hero platforms line (macOS → Docker); updated og:description;
    updated install section subtitle to reflect Docker as a no-Python-required option.

---

[2026-05-23] — feat(docker): Docker secrets support for pre-loading credentials in containers

Added

  backend/credentials.py: _SECRET_MAP, _read_docker_secret(), _get_from_docker_secrets()
    — get_credentials() now falls back to /run/secrets/ files after keyring; credentials_stored()
    checks secrets too. Mapping: SERVICE_QBT → qbt_username/qbt_password,
    SERVICE_QBT_KEY → qbt_apikey_user/qbt_apikey, SERVICE_WTRF → wtrf_username/wtrf_password.
  docker-compose.yml: secrets: block wires six secret files into the container; comments
    explain how to copy .example files and fill in values.
  secrets/: empty *.txt files (git-ignored) and *.example templates for all six secrets.
  .gitignore: secrets/*.txt excluded to prevent accidental credential commits.

---

[2026-05-22] — feat(docker): add Docker + noVNC support for browser-based GUI access

Added

  Dockerfile: single-stage build on python:3.11-slim; installs Xvfb, x11vnc, noVNC,
    websockify, SoX, and all Qt6/Chromium runtime libs; sets QTWEBENGINE_CHROMIUM_FLAGS
    --no-sandbox so QtWebEngine works in unprivileged containers.
  docker/entrypoint.sh: starts Xvfb :1 → x11vnc → websockify/noVNC on port 6080 →
    launches the app; users open http://localhost:6080 in a browser.
  docker-compose.yml: maps port 6080, named volume for data/, shm_size 256m for
    Chromium, PYTHON_KEYRING_BACKEND=null (credentials are session-only in containers);
    includes commented music-folder volume examples.
  .dockerignore: excludes .git, .venv, data/, dist/, AppDir/ from the build context.

---

[2026-05-22] — fix(paths): use XDG_DATA_HOME for data dir on frozen Linux (AppImage)

Fixed

  backend/paths.py: On Linux with a PyInstaller frozen build the executable lives inside a
    read-only AppImage squashfs mount (or an ephemeral temp dir with --appimage-extract-and-run).
    _app_root() now returns $XDG_DATA_HOME/LosslessBob (defaulting to
    ~/.local/share/LosslessBob) so data/ is writable and persists across runs.
    Windows behaviour is unchanged.

---

[2026-05-22] — fix(release): bundle Qt xcb dependencies for Linux AppImage

Fixed

  .github/workflows/release.yml: Added libxcb-cursor0, libxcb-icccm4, libxcb-image0,
    libxcb-keysyms1, libxcb-render-util0, and libxkbcommon-x11-0 to the apt-get install step so
    PyInstaller can find and bundle them. Without these, the Qt xcb platform plugin fails to load
    on systems that don't have them pre-installed (Qt 6.5+ requires libxcb-cursor0 specifically).

---

[2026-05-22] — feat(release): add Linux AppImage build to GitHub Actions release workflow

Added

  losslessbob_linux.spec: New PyInstaller spec for Linux. Identical to the Windows spec except
    numpy, scipy, librosa, soundfile, and numba are NOT excluded, so the fingerprinting stack is
    bundled. Platform-specific hiddenimports trimmed to Linux (inotify watchdog observer only).
  .github/workflows/release.yml: Added build-linux job on ubuntu-latest. Installs libgl1 and
    upx-ucl, runs PyInstaller with the Linux spec, assembles an AppDir (AppRun + .desktop + icon),
    downloads appimagetool (AppImageKit continuous), and builds a self-contained
    LosslessBob-<ver>-linux-x86_64.AppImage. Both Windows and Linux jobs upload independently to
    the same GitHub Release via softprops/action-gh-release@v2. Workflow renamed to "Release".

---

[2026-05-22] — fix(release): remove invalid "checked" flag from Inno Setup [Tasks] section

Fixed

  tools/losslessbob.iss: Lines 53–54 used `Flags: checked` in the [Tasks] section. "checked"
    is not a valid Inno Setup task flag — tasks are checked by default with no flag. Removed
    the `Flags: checked` parameter from the startmenuicon and desktopicon task entries.

[2026-05-22] — fix(release): ISS preprocessor error and update GHA actions to Node 24

Fixed

  tools/losslessbob.iss: Inno Setup ISPP preprocessor treated standalone `#13#10 +` lines as
    unknown directives, aborting the installer build with exit code 1. Merged the bare blank-line
    `#13#10 +` expressions onto the preceding string lines so `#` never starts a source line.
  .github/workflows/release.yml: Bumped actions/checkout v4→v5 and actions/setup-python v5→v6
    to resolve Node.js 20 deprecation warning (forced to Node.js 24 from 2026-06-02).

[2026-05-22] — fix(backend): correct wrong column names in generate_release_notes

Fixed

  backend/db.py: generate_release_notes queried `notes` and `updated_at` from lb_master,
    which don't exist. Corrected to `manual_notes` and `manual_set_at` (BUG-103).

[2026-05-22] — chore(release): bump version to 1.0.4

Changed

  backend/paths.py: APP_VERSION 1.0 → 1.0.4

[2026-05-22] — feat(release): add file associations, startup option, and data cleanup to Windows installer

Added

  tools/losslessbob.iss [Tasks]: fileassoc task (unchecked by default) registers .ffp/.md5/.st5
    extensions to LosslessBob.Checksum ProgID in HKCU so double-clicking checksum files opens the app.
  tools/losslessbob.iss [Tasks]: startupregistry task (unchecked by default) adds the exe to
    HKCU\...\Run so LosslessBob launches with Windows.
  tools/losslessbob.iss [Code]: CurUninstallStepChanged prompts to delete data\ on uninstall;
    auto-cleans app dir if empty. All registry keys created by the installer are removed automatically.

[2026-05-22] — feat(release): add Inno Setup installer for Windows releases

Added

  tools/losslessbob.iss: Inno Setup 6 script that wraps the PyInstaller dist/LosslessBob/
    directory into a LosslessBob_Setup_<version>.exe wizard installer. Installs to
    %LocalAppData%\LosslessBob (no UAC required); creates data\ dir; Desktop + Start Menu
    shortcuts optional. Output goes to tools/Output/.
  .github/workflows/release.yml: Updated to build the installer after PyInstaller, then
    upload both LosslessBob_Setup_<ver>.exe and a portable .zip to the GitHub Release.

[2026-05-22] — fix(gui): lookup folders now propagate to lbdir and verify immediately on lookup_completed

Fixed

  gui/main_window.py: Connected lookup_tab.lookup_completed to add_folders_from_lookup
    on both verify_tab and lbdir_tab so folders appear immediately after lookup, not only
    on tab switch.
  gui/lbdir_tab.py (add_folders_from_lookup): Removed "only if empty" guard; now merges
    new folders in, skipping duplicates. lbdir list is no longer locked after first use.
  gui/verify_tab.py (add_folders_from_lookup): Same guard removal and merge logic.

---

[2026-05-22] — fix(cli): daemon start uses DETACHED_PROCESS on Windows instead of POSIX-only start_new_session (TODO-078)

Fixed

  cli.py (_daemon_start): Added platform check — Windows now uses
    subprocess.DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP via creationflags;
    POSIX still uses start_new_session=True.

---

[2026-05-22] — fix(backend): Export HTML decade/year dropdowns now populate via folder_name fallback (TODO-084)

Fixed

  backend/app.py (collection_export_html): When entries.date_str is NULL for a collection
    row (LEFT JOIN miss), year was "" and JS filter(Boolean) stripped it, leaving both the
    "All decades" and "All years" selects empty. Now falls back to a regex search on
    folder_name for a 19xx/20xx year, so the dropdowns populate even when date_str is absent.

---

[2026-05-22] — feat(gui): pre-populate lbdir folder list from Lookup tab on tab switch (TODO-081)

Added

  gui/lbdir_tab.py: add_folders_from_lookup(folders) — mirrors verify_tab's implementation; only pre-populates when the lbdir folder list is currently empty, so active sessions are not overwritten.

Changed

  gui/main_window.py (_on_tab_changed): when switching to lbdir_tab, call add_folders_from_lookup with the current Lookup folders, matching the existing Verify tab guard pattern.

---

[2026-05-22] — feat(gui): embed all LB alias numbers in proposed folder name after alias collapse (TODO-080)

Added

  backend/db.py: get_aliases_for_canonical(canonical_lb) — thin helper returning sorted list[int] of alias_lb values for a given canonical, using the existing get_lb_aliases() query.

Changed

  gui/rename_tab.py (populate_from_lookup): after alias collapse resolves to a canonical, fetches all aliases via GET /api/lb_alias?canonical_lb=<lb>. Builds combined suffix LB-canonical-LB-alias1-... and uses it for the proposed folder name. Display column shows all LBs separated by " + " (e.g. "LB-12345 + LB-67890"). Existing _lb_in_name/_has_wrong_lb checks still use the canonical alone so state detection is unaffected.
  gui/rename_tab.py (_on_save_alias): same alias fetch applied after in-place re-resolution so rows updated from the right-click "Save as master alias…" action also reflect the combined suffix immediately.

---

[2026-05-22] — fix(gui): fingerprint build and crawler status polling blocks main thread (BUG-099 through BUG-102)

Fixed

  gui/spectrogram_tab.py: Replaced QTimer-based _fp_poll_build and _fp_poll_dup (which ran
    blocking requests.get on the main thread) with background QThread pollers
    (_FpBuildStatusThread, _FpDupStatusThread) that emit status_update signals to the main
    thread — the same pattern used by the crawler. Fingerprint build stop now shows
    "Stopping…" immediately on the label. _fp_stop_dup_scan was calling the wrong endpoint
    (/api/fingerprint/build/stop) and blocking the main thread; both are fixed. The
    _on_fp_dup_status slot properly cleans up the thread on completion.

  gui/scraper_tab.py: Crawler "Start" and "Stop" buttons were calling requests.post directly
    on the main GUI thread (freezing the app for up to 10 s / 5 s respectively). Both now
    dispatch via a _Worker QThread. Added self._workers list to ScraperTab.

  backend/app.py: Added /api/fingerprint/duplicates/scan/stop endpoint (the old stop button
    was misfiring to /api/fingerprint/build/stop). Added stop_requested field to
    _fp_dup_state so the GUI can show "Stopping…" while the scan winds down.

[2026-05-22] — fix(gui): curator checkbox error dialog on toggle (BUG-098)

Fixed

  gui/setup_tab.py: Moved curator_cb.toggled signal connection to after publish_master_btn is
    created, eliminating the AttributeError risk if the signal fires during _build_ui before its
    dependent widget exists. Added logging.exception in the except block so the actual error text
    is now captured in losslessbob.log. Improved error display: Flask's JSON error body is parsed
    so the dialog shows the plain message rather than raw JSON. Fixed _on_curator_toggled docstring
    (removed incorrect 'geocoder group' claim — that gating happens via curator_mode_changed →
    map_tab.set_curator_mode).

  backend/app.py: Added logging.exception to the curator_set route's except block so any
    server-side failure is captured in the log.

[2026-05-21] — fix(backend): sticky table header broken in exported HTML collection page

Fixed

  backend/app.py: Switched from a page-scroll layout to a flex-column viewport layout.
    Root cause: `overflow-x:auto` on `.card` implicitly forces `overflow-y:auto` (CSS spec),
    making `.card` a vertical scroll container — and `position:sticky` cannot escape its own
    scroll container. No single overflow value fixes this while also enabling horizontal
    scroll and border-radius clipping simultaneously.
    Fix: `html/body` are now `height:100%;overflow:hidden;display:flex;flex-direction:column`.
    `.card` gets `flex:1;min-height:0;overflow:auto` (fills remaining viewport, scrolls
    internally). `thead th` sticks at `top:0` relative to `.card`'s scroll context instead
    of the viewport. `.hdr`, `.pg`, `.ftr` get `flex-shrink:0`. `watchHdr()` and `--hh`
    removed (no longer needed). `go()` now scrolls `.card` instead of `window`. Print
    media query overrides flex layout to restore full-page rendering. (BUG-097)

[2026-05-21] — feat(cli): add fingerprint command (build/stop/status/identify/stats/scan-dupes/dupes)

Added

  cli.py: `fingerprint` subcommand wired into _build_parser(), _execute(), _HELP_TEXT,
          _help_text() (narrow), _COMMAND_HELP, and _COMPLETIONS.
          Sub-actions: build [--force] [--watch], stop, status [--json],
          identify <FILE> [--json], stats [--json], scan-dupes [--watch], dupes [--json].
          _watch_fp_build() — polls /api/fingerprint/build/status with a progress bar.
          _watch_fp_dupes() — polls /api/fingerprint/duplicates until scan finishes.
          _print_fp_status() — formatted build-progress output.
          _print_fp_identify() — ranked candidate list with CONFIDENT flag.
          _print_fp_dupes() — duplicate pair list with lb_a ↔ lb_b and file paths.
          All output adapts to narrow (<50 col) and wide terminal widths.

[2026-05-21] — feat(cli): daemon mode — persistent background backend + auto-attach

Added

  cli.py: _is_flask_running(port) — checks if :5174 is already accepting connections.
          _daemon_start/_daemon_stop/_daemon_status helpers — fork run_backend.py as
          a detached OS process (start_new_session=True), write data/backend.pid,
          redirect output to data/backend.log. SIGTERM on stop.
          `daemon start|stop|status` subcommand added to _build_parser(), _execute(),
          _HELP_TEXT, _COMMAND_HELP, and _COMPLETIONS.
          _run_interactive() now checks _is_flask_running() first; if a backend is
          already up it attaches instead of starting a new server.
          One-shot main() same: skips thread start when port already listening.
          `daemon` command excluded from Flask startup check (needs no backend).

  run_backend.py: Added --port argument (argparse) so cli.py daemon start can pass
                  the configured port when forking the process.

  main.py: Added _wait_for_port(..., timeout=0.5) check before spawning the Flask
           thread. If a daemon backend is already up, the GUI attaches to it; the
           Flask thread and restart-callback registration are skipped. Closing the
           GUI window no longer kills a running daemon.

[2026-05-21] — ux(cli): tabular scraper/crawler status for narrow mobile output

Changed

  cli.py: Added _print_scrape_status() — narrow mode prints an _hr("scraper") block with
          Status / LB / Progress / Errors / Skipped / Action rows (label col 10 chars).
          scrape status dispatch now calls _print_scrape_status() instead of _fmt_scrape_status().
          _watch_scrape() narrow mode: \r-overwrite progress bar [███░░░] N/total LB-NNNNN,
          bar width computed to fill exactly w chars.
          _watch_crawler() narrow mode: single line per URL using HH:MM timestamp (saves 3
          chars vs HH:MM:SS) with inline Q:N count appended — no separate counts line.
          crawler status idle narrow: _hr("crawler") + Status / Fetched table rows.
          crawler start confirmation narrow: two-line "Crawler started / scope: X".
          Removed dead code: _fmt_crawler_status() was defined but never called.

[2026-05-21] — ux(cli): tabular single-line column layout for narrow mobile output

Changed

  cli.py: Replaced 2-line search/recent format with single-line columnar rows that fill
          exactly w chars: LB-NNNNN  YYYY-MM-DD  location (location truncated to w-22).
          lookup narrow: single row LB-NNNNN  m:N  ?:N  status (status fills remaining).
          stats narrow: _hr("stats") section header + aligned two-column key-value table
          (Entries / Checksums / Latest LB / Imported, label col 11 chars wide).

[2026-05-21] — ux(cli): optimise all output for 40-character mobile terminals

Changed

  cli.py: Added `import textwrap`.  All outputs now adapt to the current terminal width
          with a narrow-mode threshold of < 50 columns.
    _fmt_scrape_status(): narrow mode drops errors/skipped/action; shows run/idle + LB only.
    _counts(): narrow mode shows ↓N Q:N (fetched + queue) and drops 304/404 breakdowns.
    _print_show(): values truncated to fit within terminal width (val_w = w - 14).
    _print_diff(): db_sfx shortens to " [DB]" on narrow; fn_w computed per-suffix.
    _print_verify(): narrow mode moves missing-type tag to its own line; fn_w tightened.
    search output: 2-line format (LB+date / location) when w < 50.
    lookup output: narrow 2-line format (LB + m:N ?:N / status) when w < 50.
    recent output: 2-line format matching search when w < 50.
    scrape start: narrow confirmation is 2-line "Scrape started / N entries".
    Interactive banner and Ctrl-C hint: shortened for w < 50.
    _help_text(): new function — returns 10-column compact command list on narrow screens,
                  full _HELP_TEXT on wide screens.
    _fmt_help(): new function — word-wraps per-command help pages to terminal width.
    help/? dispatch: uses _help_text() and _fmt_help(); "No help for X" wraps on narrow.

[2026-05-21] — feat(cli): add 8 new commands — show, open, diff, verify, missing, export, backup, recent

Added

  cli.py: Eight new commands implemented against existing Flask API endpoints.
    show <LB>              Full concert record: metadata, checksums, cached files.
                           Accepts "123", "00123", or "LB-00123" via _parse_lb().
    open <LB>              Opens losslessbob.com detail page in the default browser.
    diff <file> ...        Diff-style lookup: ✓ matched, ✗ missing from input (fetches
                           entry detail to show filenames), ? not in DB at all.
    verify <dir> ...       Wraps POST /api/verify; shows pass/fail + problem files.
    missing [--field ...]  --field checksums → GET /api/db/missing_lb_numbers;
                           --field metadata → paginates GET /api/lb_master?status=missing.
    export [--format ...]  csv → GET /api/dbedit/table/entries/export (streamed bytes);
                           json/txt → paginated GET /api/dbedit/table/entries/rows.
    backup [<dest>]        POST /api/db/backup; optional shutil.copy2 to dest path.
    recent [N]             GET /api/dbedit/table/entries/rows sorted by scraped_at DESC.
    Added _parse_lb(), _LB_URL, _TYPE_LABELS constants; _print_show(), _print_diff(),
    _print_verify() formatters; all 8 commands in _build_parser(), _execute(),
    _COMMAND_HELP, _COMPLETIONS, and _HELP_TEXT.

[2026-05-21] — feat(cli): clear screen on startup and add `clear` shell command

Changed

  cli.py: Added `_clear_screen()` (ANSI `\033[2J\033[H`) so the terminal is wiped clean
    once Flask is ready and the welcome message always starts at line 1. Added `clear`
    as a REPL command (tab-completable) that clears the screen mid-session. Added `clear`
    to the `help` output and `_COMPLETIONS` list.

[2026-05-21] — feat(cli): detect terminal width and adapt all output formatting

Changed

  cli.py: Added `shutil.get_terminal_size()`-based `_term_width()` helper. All output
    formatters now query the live terminal width instead of using hardcoded constants.
    - Removed `_MOB_W = 44` constant; `_hr()` and `_watch_crawler()` use `_term_width()`
    - `_watch_scrape()`: status line capped to terminal width to prevent wrap on narrow TTYs
    - `_watch_crawler()`: `url_w` and message chunk width computed from live terminal size
    - `_fmt_crawler_status()`: URL truncated to available space after the fixed prefix
    - `stats`: vertical (one-field-per-line) layout on terminals narrower than 72 columns
    - `lookup`: two-line-per-result layout on terminals narrower than 70 columns
    - `search`: location field truncated to `max(20, term_width - 27)` instead of fixed 50

[2026-05-21] — feat(cli): interactive REPL shell with per-command help and tab-completion

Changed

  cli.py: Running `cli.py` with no arguments now opens a persistent interactive shell
    (prompt `lb> `) instead of printing usage and exiting.  Flask starts once in a
    background daemon thread on entry; all subsequent commands reuse the running backend.
    One-shot invocation (`cli.py <command> [args]`) is fully backward-compatible.
    Added:
      - _run_interactive(): REPL loop with Ctrl-C safety, EOFError/Ctrl-D exit
      - _setup_readline(): readline history persisted to ~/.losslessbob_history, tab-
          completion for all top-level commands and scrape/crawler sub-commands
      - _build_parser(): extracted parser construction so it can be reused both in
          interactive (_SilentParser, no sys.exit) and one-shot modes
      - _execute(): extracted dispatch logic called by both modes
      - _SilentParser / _UsageError: subclass of ArgumentParser that raises instead of
          calling sys.exit so parse errors don't kill the REPL
      - _HELP_TEXT: structured overview with examples shown by `help` / `?`
      - _COMMAND_HELP dict: full per-command reference (arguments, flags, output format,
          examples) shown by `help <command>` (e.g. `help search`, `help crawler`)
      - --port N with no subcommand also enters interactive mode on the given port

[2026-05-21] — feat(cli): crawler status live tail log for mobile screens

Changed

  cli.py: `crawler status` now enters a live tail-log mode instead of printing
    one snapshot. Each URL change and stage transition prints a new log entry
    (scrolling, not overwriting) sized for ~44-char mobile SSH sessions.
    Format: timestamp + arrow (↓ new / ↺ conditional GET) + short path, then
    counts (ok / 304 / 404 / err / queue) on a second line.
    If no crawl is running it prints "idle — no crawl running" and exits.
    `--json` still produces a raw snapshot and exits as before.
    Added _MOB_W, _short_path(), _counts(), _hr() helpers; _watch_crawler()
    rewritten to use the new format (also used by `crawler start --watch`).

[2026-05-21] — fix(gui): crawler status poll race condition shows "idle" immediately after start

Fixed

  gui/scraper_tab.py: _on_crawler_status now ignores the initial idle state (running=False,
    stage="idle") so the poll thread doesn't stop itself before the crawler thread has had a
    chance to set running=True. UI only resets when stage is a terminal value (done/stopped/error).

[2026-05-21] — feat(cli): add scrape and crawler start/stop/status subcommands

Added

  cli.py: `scrape start/stop/status` and `crawler start/stop/status` subcommands.
    `scrape start` accepts --start-lb, --end-lb, --force, --watch.
    `crawler start` accepts --scope, --force, --delay-ms, --daily-cap, --watch.
    --watch polls the respective status endpoint every 2 s and prints progress until done.
    Extracted _wait_for_flask() helper to clean up the startup probe.

[2026-05-21] — perf(scraper): reduce per-entry DB write overhead in scrape_range

Changed

  backend/scraper.py: Skip-check now uses get_connection (read-only) for reads and only
    acquires write_connection when marking attachment files downloaded; uses executemany
    instead of individual UPDATE per file. Attachment download loop now batches all
    downloaded=1 updates into one executemany after the loop instead of one write_connection
    per file. Added _reconcile param (default True) to scrape_entry so scrape_range can
    defer lb_master reconciliation. Moved NavigableString import to module level.
    Added _RECONCILE_BATCH = 100 constant.
  backend/db.py: Added batch_reconcile_lb_status() — reconciles N lb_master rows in a
    single write transaction using bulk IN-queries (4 SELECTs + executemany) instead of
    the O(N) per-entry pattern (N × 4 queries). Used by scrape_range every 100 entries
    and on stop/finish.

---

[2026-05-21] — test: add comprehensive DB write function test battery (test_db_writes.py)

Added

  tests/test_db_writes.py: 115-test battery covering all database write functions in backend/db.py.
    Grouped into 17 test classes: set_meta, collection CRUD, collection_meta upserts,
    listen-count increment, wishlist, record_entry_changes, insert_missing_entry,
    lb_master reconcile/override/clear, overrides export/import, lb_alias (chain rewrite,
    cycle detection, dedup), folder_lb_link, torrent records, forum posts, rename history,
    all purge functions, scrape sessions, upsert_inventory, write_connection rollback, and
    a dedicated SQL constraint class that deliberately triggers UNIQUE, CHECK, NOT NULL,
    PK, and FK violations. Includes a concurrent-writes thread-safety test.

[2026-05-21] — fix(backend): eliminate SQLite database locking errors under concurrent scrape + fingerprint

Changed

  backend/db.py: Added `_write_lock = threading.RLock()` and `write_connection()` context manager.
    All DML functions now acquire the write lock before opening a write transaction, serialising
    writers at the Python level so SQLite's busy_timeout is never exceeded. Also fixed
    `sqlite3.connect(timeout=30)` to align Python's internal retry with the PRAGMA value.
  backend/scraper.py: Converted three `with get_connection()` write blocks to `write_connection()`.
  backend/app.py: Converted three direct DML routes (DB reset, dbedit UPDATE, dbedit DELETE)
    to use `write_connection()` / `_write_lock`.

[2026-05-20] — fix(backend): exported HTML collection shows no rows (TDZ crash in boot IIFE)

Fixed

  backend/app.py: `const SM` and `const BC` were declared after the boot IIFE in
    _COLLECTION_HTML_TEMPLATE, placing them in the temporal dead zone when mkStats() and
    draw() were called. Moved both declarations before the IIFE so they are initialized
    before boot() runs.

[2026-05-20] — feat(gui/map): custom cluster icon colors with vivid tier-based palette

Changed

  gui/resources/map.html: Replaced default MarkerCluster CSS bubble colors with a custom
    iconCreateFunction. Five count tiers: cyan (<10), mint green (<50), amber (<150),
    deep orange (<500), vivid purple (500+). Bubble size scales with count. Glowing ring
    via box-shadow. Previous STATUS_COLORS changes also preserved for individual markers.

[2026-05-20] — feat(backend): rework HTML collection export into modern interactive single-file report

Changed

  backend/app.py: Rewrote GET /api/collection/export/html. Now generates a self-contained
    interactive HTML report via _COLLECTION_HTML_TEMPLATE (module-level constant). Features:
    • Dark/light mode via prefers-color-scheme CSS media query
    • Stats pills bar: total recordings + per-status counts (Public/Private/Missing/Unknown)
    • Live search with 150 ms debounce across LB#, date, location, folder, notes
    • Search-term highlighting in results (<mark> elements)
    • Column sorting (all 6 columns, toggle asc/desc, visual ▲/▼ arrows)
    • Status filter dropdown (Public/Private/Missing/Unknown)
    • Decade filter dropdown (auto-built from data: 1960s, 1970s, …)
    • Year filter dropdown (auto-built from data)
    • Client-side pagination (100 rows/page default; 50/100/200/500 selector) — essential
      for 16 000+ entry collections; only the current page renders as DOM, full dataset in JSON
    • Keyboard shortcuts: / or Ctrl+K to focus search; Escape to clear; ← → to page
    • CSV download button exports the currently filtered+sorted view with BOM (Excel-safe)
    • Copy LB#s button copies all visible LB numbers to clipboard via navigator.clipboard
    • Sticky header with ResizeObserver so table thead offset tracks header height dynamically
    • Toast notifications for clipboard/CSV actions
    • Print-friendly media query (hides controls)
    • Generation timestamp in header and footer
    All 16 k entries embed as a JSON array (~3–4 MB); JS renders 100 rows at a time.
    No external dependencies — single self-contained file, works fully offline.

[2026-05-20] — feat(gui+backend): export My Collection as HTML table or M3U playlist (FEAT-07)

Added

  backend/app.py: GET /api/collection/export/html — initial simple HTML table (superseded above).
  backend/app.py: GET /api/collection/export/m3u — returns an #EXTM3U playlist walking each
    entry's disk_path for audio files (.flac/.shn/.ape/.wav/.mp3); skips missing folders.
  gui/collection_tab.py: "Export HTML…" and "Export M3U…" buttons in My Collection panel;
    each GETs the corresponding API endpoint and writes the response bytes to a user-chosen
    file via QFileDialog.getSaveFileName(); status label updated on success or error.

[2026-05-20] — feat(gui): more vivid map marker colors and significantly larger popup text

Changed

  gui/resources/map.html: STATUS_COLORS replaced with vivid palette (public #00C853,
    private #00B0FF, missing #FF6D00, unknown #E040FB); fillOpacity 0.85→0.95; owned
    marker ring changed from white to gold (#FFD600); popup title 15px→20px, body
    13px→15px, status label 13px→15px, search button 12px→14px, owned star 11px→15px.

[2026-05-20] — feat(gui): larger map bubbles and popup text for LB markers

Changed

  gui/resources/map.html: increased circleMarker radius from 8 → 12, owned-marker
    border weight from 3 → 4 (non-owned 1 → 1.5); popup title font-size 13px → 15px,
    added base .lb-popup font-size 13px with line-height 1.5, status text bumped to 13px,
    search button font 11px → 12px and padding slightly increased.

[2026-05-20] — fix(gui): rework Attachments tab — QTableView replaces QTreeWidget (BUG-092)

Changed

  gui/attachments_tab.py: full rework of the Cached view.
    - _LbModel(QAbstractTableModel): two-column model (LB Number, Files) read directly from
      the in-memory list; Qt renders only visible rows so all entries display without any
      pagination — page nav buttons removed.
    - QSortFilterProxyModel on the table provides instant text filtering; numeric input
      (e.g. "1234") is normalized to "LB-01234" automatically.
    - QListWidget below the table shows files for the selected LB; connected once in _build_ui
      to avoid repeated signal connections.
    - lb_status fetched via LEFT JOIN lb_master inside _RefreshTreeThread so _render_tree_page's
      blocking get_lb_statuses_batch() call on the main thread is eliminated.
    - Removed: PAGE_SIZE, _page, _render_tree_page, prev/next page buttons, _jump_to_lb, the
      old _tree_context_menu and _LB_STATUS_BG dict; all replaced by the model/proxy approach.
    - Removed import of get_lb_statuses_batch (no longer needed).

[2026-05-20] — fix(gui): Setup tab stats not refreshed after flat file apply (BUG-091)

Fixed

  gui/setup_tab.py: _on_discover_done() now calls _refresh_stats() after the update dialog
    closes, so the DB stats label (total checksums, LB entries, latest LB) updates immediately
    when a flat file is applied. Previously it required an app restart to reflect the new counts.

[2026-05-20] — feat(gui+backend): Fingerprinted column in My Collection; fingerprint progress shows folder name

Added

  gui/collection_tab.py: new "Fingerprinted" column (col 8) in My Collection table. Shows "Yes"
    (green) when at least one audio track for that LB number has been fingerprinted. Tooltip
    shows hash count. Column is sortable. Data is fetched async via the new API endpoint and
    merged into rows without blocking the collection load.
  backend/app.py: GET /api/fingerprint/lb_numbers — returns {lb_number: n_hashes} dict for
    all fingerprinted LBs, used by the new collection column.

Changed

  backend/fingerprint.py: build_fingerprint_db() now sets current to "FolderName / filename"
    instead of just "filename", so the Fingerprinting tab progress label shows which folder is
    being processed.

[2026-05-20] — fix(fingerprint): duplicate scan used raw hash count instead of temporal coherence (BUG-089)

Fixed

  backend/fingerprint.py: find_duplicate_recordings() was grouping by (track_a, track_b)
    and counting raw hash collisions. Any two files sharing spectral content in unrelated
    passages could accumulate enough raw hits to pass MATCH_THRESHOLD, producing mass
    false positives. Fixed by applying the same temporal-coherence approach as
    identify_file(): matches are bucketed by their time-offset delta (rounded to 0.1 s)
    and the peak bin count — not the total hit count — is used as the score.

[2026-05-20] — fix(deps): install numpy/librosa/scipy/soundfile/numba into venv (BUG-088)

Fixed

  requirements.txt: added numpy==2.4.6, numba==0.65.1; bumped librosa to 0.11.0,
    soundfile to 0.13.1, scipy to 1.17.1. All packages now installed in .venv.
    Previously fingerprint_file() failed with "No module named 'numpy'" on every call.
  PROJECT.md: updated Tech Stack table to reflect actual installed versions.

[2026-05-20] — feat(gui+backend): right-click "Fingerprint Folder" in My Collection tab

Added

  gui/collection_tab.py: "Fingerprint Folder" action in the My Collection context menu.
    Appears for any selected row(s) whose disk_path exists on disk. Calls the build
    endpoint with only the selected folder(s) so the full collection is not re-scanned.
  backend/app.py: /api/fingerprint/build now accepts an optional `folders` list of
    {disk_path, lb_number} dicts in the JSON body. When provided, only those rows are
    fingerprinted instead of the whole collection.

[2026-05-20] — fix(fingerprint): remove blocking rglob scan from get_fp_stats (BUG-087)

Fixed

  backend/fingerprint.py: get_fp_stats() no longer walks the filesystem to compute
    coverage_pct. The rglob scan caused the /api/fingerprint/stats endpoint to block for
    10+ seconds on large collections, triggering the GUI read timeout. coverage_pct now
    returns None; the GUI already handles this gracefully.

[2026-05-21] — fix(fingerprint): post-review fixes — temporal coherence, DB timeout, rglob, force wiring

Fixed

  backend/fingerprint.py: _get_fp_conn now passes timeout=30 to sqlite3.connect()
    and sets PRAGMA busy_timeout=30000, matching db.py's get_connection() pattern (BUG-086).
  backend/fingerprint.py: identify_file now uses temporal coherence scoring — hashes must
    agree on a consistent time-offset delta (db_offset − query_offset) to score, not just
    raw hit count. This filters hash collisions and makes matching significantly more robust
    against unrelated tracks (BUG-085).
  backend/fingerprint.py: build_fingerprint_db now uses rglob("*") instead of iterdir()
    so multi-disc folders (Disc1/, Disc2/) are traversed correctly.
  backend/fingerprint.py: find_duplicate_recordings self-join now has LIMIT 500 to prevent
    catastrophic query times on large collections.
  backend/fingerprint.py: get_fp_stats now returns coverage_pct alongside track_count and
    hash_count.

Changed

  backend/fingerprint.py: build_fingerprint_db accepts a force: bool parameter, threaded
    through from the GUI checkbox → POST body → Flask route → _do_fp_build → fingerprint_file.
  backend/app.py: fp_build() route reads force from request JSON and passes to _do_fp_build.
  gui/spectrogram_tab.py: _fp_start_build passes force=checkbox state in POST body;
    progress bar starts indeterminate (setRange(0,0)) until total is known; setMaximum
    called only once per build run.
  gui/spectrogram_tab.py: _fp_stop_build now uses _Worker instead of blocking main thread.
  gui/spectrogram_tab.py: stats label shows coverage_pct when available.

[2026-05-21] — feat(fingerprint): add acoustic fingerprinting engine and UI

Added

  backend/fingerprint.py: Wang/Shazam-style landmark fingerprinting engine.
    Stores spectral-peak hashes in data/fingerprints.db. Public API:
    init_fp_db, fingerprint_file, build_fingerprint_db, identify_file,
    find_duplicate_recordings, get_fp_stats.

  backend/paths.py: Added FP_DB_PATH = DATA_DIR / "fingerprints.db".

  backend/sox_utils.py: Added decode_to_wav() public wrapper around
    _convert_to_wav() for use by the fingerprint engine.

Changed

  backend/app.py: Added _fp_build_state/_fp_dup_state module-level dicts,
    _fp_build_lock/_fp_dup_lock/_fp_build_stop/_fp_dup_stop thread primitives,
    _do_fp_build/_do_fp_dup_scan background workers, init_fp_db() call in
    create_app(), and 7 new routes under /api/fingerprint/*.

  gui/spectrogram_tab.py: Refactored _build_ui into inner QTabWidget with
    "Spectrograms" and "Fingerprinting" sub-tabs. Fingerprinting tab has
    three panels: Fingerprint DB (build/stats/stop), Identify File (file drop
    + browse + results table), Find Duplicates (SQL scan + CSV export).

  requirements.txt: Added librosa==0.10.2, soundfile==0.12.1, scipy==1.13.1.

---

[2026-05-20] — chore(release): bump version to 1.0.2

Changed

  gui/main_window.py: VERSION "1.0.1" → "1.0.2"

---

[2026-05-20] — fix(gui): Attachments tab lag — background thread + SQL-join reconcile (BUG-083)

Fixed

  gui/attachments_tab.py: Replaced blocking _reconcile_site_files() filesystem scan
    (24 k+ iterdir() + 50 batched SQL UPDATEs on the main thread) with a single
    UPDATE…IN(SELECT site_inventory) SQL join. Moved all DB work into
    _RefreshTreeThread(QThread); main thread stays responsive. Removed HTTP round-trip
    to /api/db/stats (now uses COUNT(DISTINCT lb_number) in the worker).

---

[2026-05-20] — refactor(gui): Map tab browser-only + geocoding consolidation (TODO-074)

Changed

  gui/map_tab.py: Replaced QWebEngineView with browser-open button. Added Map Filters
    group (year range, lb_status, owned, text search). Added Geocoding group (Run
    Geocoder, status polling) and Location Overrides group (table + double-click edit),
    both curator-only. PyQt6-WebEngine no longer required for the Map tab.
  gui/setup_tab.py: Removed Geocode Locations group and worker threads (_GeocodeRunThread,
    _GeocodeStatusThread). Added curator_mode_changed signal. Frees vertical space.
  gui/dbedit_tab.py: Removed Location Geocoding sub-panel (PlaceManualDialog,
    _geo_box and all geo methods). Frees vertical space in the DB Editor integrity/aliases
    section.
  gui/main_window.py: Connected setup_tab.curator_mode_changed to map_tab.set_curator_mode().

---

[2026-05-20] — feat(cli): FEAT-01 CLI/headless mode — cli.py

Added

  cli.py: New headless CLI entrypoint. Commands: lookup <glob>, search <query>, stats,
    import <path>, serve. Uses port-poll instead of time.sleep() for cross-platform
    safety. Uses Waitress on Windows. Flask and PyQt6 never imported in CLI mode.

---

[2026-05-20] — feat(backend+gui): audio filename reconcile on Lookup and Rename tabs

Added

  backend/db.py: lookup_checksums() MATCHED detail dicts now include db_filename — the
    canonical filename stored in the checksums table. NOT FOUND dicts include db_filename: null.

  backend/app.py: POST /api/checksums/reconcile_audio — validates proposed audio renames
    against the filesystem (ok | from_missing | to_exists per proposal, audio exts only).
    POST /api/checksums/apply_reconcile_audio — executes Path.rename() for each approved pair.

  gui/widgets/reconcile_dialog.py: AudioReconcileDialog — shared preview dialog showing
    checkbox | Current Filename | DB Canonical Filename | Checksum. Pre-checks ok proposals,
    flags problematic ones in yellow. Returns only checked ok renames via get_selected_renames().

  gui/lookup_tab.py: "Reconcile Audio Files" button — enabled after a lookup when any MATCHED
    row has a filename differing from the DB canonical name. Builds proposals from _last_detail
    + source_file path, calls reconcile API, shows AudioReconcileDialog, applies renames.

  gui/rename_tab.py: "Reconcile Audio Files" button — _ReconcileAudioWorker scans checksum
    files (.ffp/.md5/.st5/.sha1/.shn) in each checked folder, runs /api/lookup, extracts
    filename mismatches, then follows the same reconcile → dialog → apply flow.

---

[2026-05-20] — feat(backend+gui): TODO-064/065 — web GUI basic-auth middleware and Setup tab password control

Added

  backend/app.py: before_request hook (_enforce_web_auth) enforces HTTP Basic Auth on /web/*
    and /frontend/* routes when meta key web_password is set. /api/* routes remain open.
    web_password added to db_settings() GET response as "set"/"" (never exposes actual value).
    import base64 added.
  gui/setup_tab.py: "Web GUI Access" QGroupBox in the connection row. Password-mode QLineEdit,
    Save and Clear buttons, status label. _on_web_password_save(), _on_web_password_clear(),
    and _load_web_password_status() handlers wired up. Status loaded on startup.

[2026-05-20] — feat(gui): TODO-028 — click-to-sort on Rename tab main table

Added

  gui/rename_tab.py: RenameSortProxy (QSortFilterProxyModel) wraps RenameModel. lessThan()
    sorts col 1 (Current Folder Name) and col 2 (Proposed Name) by basename text, col 3
    (LB Found) by first numeric LB (multi-LB rows use smallest LB), col 4 (Reason/State)
    by state rank (needs_rename → has_lb → wrong_lb → multiple_ids → renamed → no_match).
    Default sort: Current Folder Name ASC. _on_cell_clicked and _on_context now map
    proxy→source indices before mutating source model rows.

---

[2026-05-20] — feat(i18n): TODO-069 COMPLETE — .qm files compiled and verified (1067/1067 per language)

Fixed

  scripts/build_qm.py: rewrote pure-Python Qt .qm compiler with correct binary format.
    Previous version had wrong tag IDs (Translation=5 instead of 3, SourceText=3 instead of 6,
    Context=4 instead of 7), wrong section layout (one 0x42 section instead of separate 0x42
    Hashes + 0x69 Messages sections), per-record length prefix (not present in real format),
    and wrong ELF hash shift (>> 23 instead of >> 24). Also added elfHash_finish (0 → 1) and
    hashed sourceText+comment (not just sourceText). Verified: 1067/1067 translations returned
    by QCoreApplication.translate() for all five languages.

[2026-05-20] — feat(gui/i18n): scraper_tab.py wrapped (missed from TODO-068 tracking)

Changed

  gui/scraper_tab.py: wrapped all user-facing strings — groupbox titles, all buttons/labels/
    checkboxes/tooltips, table headers, pagination labels, and all status/error messages;
    inventory status combo fixed from addItems()+currentText() comparison to individual
    addItem(tr(...), userData)+currentData() (same i18n correctness fix as other combos).

[2026-05-20] — feat(gui/i18n): TODO-068 COMPLETE — attachments_tab; widgets confirmed clean

Changed

  gui/attachments_tab.py: wrapped all user-facing strings — toggle buttons, tree header, page
    navigation labels, placeholder text, file preview label, context menu actions, scrape status
    messages, and file-reading error text; widgets/sort_keys.py and widgets/state_store.py
    confirmed to contain no user-facing strings (no changes needed).

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab, collection_tab, dbedit_tab

Changed

  gui/dbedit_tab.py: wrapped all user-facing strings in PlaceManualDialog and DbEditTab — buttons,
    labels, groupbox titles, tooltips, QFileDialog/QMessageBox/QInputDialog calls, table headers,
    and all status/error messages; geo filter combo converted from addItems() + text-based map lookup
    to individual addItem(self.tr(...), userData) + currentData(), fixing the i18n lookup bug.

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab, collection_tab

Changed

  gui/collection_tab.py: wrapped all user-facing strings in _AddDialog, _ScanPreviewDialog,
    _PersonalMetaDialog, and CollectionTab — ~130 strings total including tab names, all buttons,
    labels, tooltips, QFileDialog captions, QMessageBox dialogs, context menu actions,
    QTableWidget/QTreeWidget headers, and all status/error f-string messages; _on_inner_tab_changed
    refactored from fragile tab-text comparison to index-based dispatch (correctness fix for i18n).

[2026-05-20] — feat(gui/i18n): TODO-068 string wrapping — lookup_tab

Changed

  gui/lookup_tab.py: wrapped all user-facing strings in LookupTab and _ChangeHistoryDialog — button
    labels, tooltips, dialog titles, status messages, context menu actions, table header lists,
    QFileDialog captions, filter labels, and all f-string status messages; _TableModel headers now
    wrapped at construction site via [self.tr(h) for h in CONST]; _ChangeHistoryDialog headers use
    [self.tr(h) for h in self._HEADERS]; lb_status_combo items switched from addItems() to individual
    addItem(self.tr(...)) calls for pylupdate compatibility.

[2026-05-19] — feat(gui/i18n): TODO-068 string wrapping — setup_tab, bootlegs_tab, search_tab, lbdir_tab, rename_tab

Changed

  gui/setup_tab.py: wrapped all remaining user-facing strings in handler methods (stats labels, status
    messages, error dialogs, qBittorrent/WTRF/tracker/geocode sections, purge dialog, master publish/install
    dialogs); also wrapped _build_ui ffmpeg/shntool/re-check label strings.
  gui/bootlegs_tab.py: wrapped _BootlegsModel.headerData, tooltip and (no title) strings; wrapped all
    _build_ui combo items (with userData preserved), buttons, labels; wrapped fetch/pagination status messages.
  gui/search_tab.py: wrapped SearchModel.headerData and tooltips; refactored field_combo to use addItem
    with userData so translated display text does not break the field_map lookup; wrapped all _build_ui
    widgets and handler status/error messages.
  gui/lbdir_tab.py: wrapped ReconcilePreviewDialog and ExtraFilesDialog titles, labels, buttons; wrapped all
    LbdirTab._build_ui button texts and tooltips; converted _result_display_status and _fmt_status from
    @staticmethod to instance methods to enable self.tr(); wrapped all handler status messages and error
    strings; wrapped SUMMARY_HEADERS, DETAIL_HEADERS, and INFO_FIELDS at point of use.
  gui/rename_tab.py: wrapped RenameModel.headerData and NFT tooltip dict (inline at use site); wrapped all
    RenameTab._build_ui legend, buttons, and tooltips; wrapped reason strings in populate_from_lookup;
    wrapped all handler status/error messages and context menu action texts; wrapped _AliasDialog.

[2026-05-19] — chore(scraper): raise site crawler daily_cap from 5000 to 99999

Changed

  backend/site_crawler.py: crawl() default daily_cap 5000 → 99999.
  backend/app.py: POST /api/crawler/start default daily_cap 5000 → 99999; updated docstring.
  gui/scraper_tab.py: spinner max 50000 → 99999, default value 5000 → 99999, load fallback 5000 → 99999.

[2026-05-19] — fix(gui/scraper): Attachments tab showed no crawler-downloaded files — entry_files.downloaded never updated by site_crawler

Fixed

  gui/attachments_tab.py: Added _reconcile_site_files() which scans SITE_FILES_DIR on every
    _refresh_tree() call and bulk-updates entry_files SET downloaded=1 for any file that exists
    on disk. Fixes the 6,000+ existing files the crawler had downloaded but that were invisible
    to the tab. Also added `import logging` at module level.
  backend/site_crawler.py: After saving a /files/ URL to disk, now also updates
    entry_files SET downloaded=1 WHERE filename=? so future crawl sessions keep the tab in sync.
    Added get_connection to DB imports.

[2026-05-19] — feat(gui): i18n infrastructure — language loader, Setup tab selector, startup wiring (TODO-067)

Added

  gui/i18n.py: QTranslator loader with load_language() and supported_languages(); reads compiled
    .qm files from gui/locales/; falls back silently to English if file is missing.

Changed

  main.py: read ui_language from meta table via direct SQLite at startup (before any windows are
    shown) and install the matching QTranslator via load_language().
  backend/app.py: added "ui_language" to the GET /api/db/settings response keys so the Setup tab
    can read the current preference on load.
  gui/setup_tab.py: added "Preferences" group box with interface-language QComboBox; saving
    persists via POST /api/db/settings; restart notice appears on change.

---

[2026-05-19] — feat(docs): GitHub Pages marketing website for community advertising

Added

  docs/index.html: Dark-themed landing page showcasing all features, install instructions,
    screenshot placeholders, and GitHub/release links. Ready for GitHub Pages (docs/ source).
  docs/screenshots/README.md: Guide listing which screenshots to capture and where to save them.

[2026-05-19] — feat(gui/backend): map feature complete — local Leaflet, QWebChannel, viewport filter, List in Search

Changed

  gui/resources/map.html: replaced CDN Leaflet/markercluster/heat refs with local /leaflet/ paths;
    added "Open in Search" button to marker popups (calls QWebChannel bridge);
    added Viewport Filter toggle + "List in Search" button that sends visible LB numbers to Search tab.

Added

  gui/resources/leaflet/: bundled Leaflet 1.9.4, leaflet.markercluster 1.5.3,
    leaflet.heat 0.2.0 — map now works fully offline (tiles still require network).
  gui/map_tab.py: _MapBridge(QObject) with openInSearch/listInSearch slots;
    QWebChannel setup with qwebchannel.js injection from Qt resources;
    open_in_search and list_in_search pyqtSignals forwarded from bridge.
  gui/main_window.py: _on_map_open_in_search + _on_map_list_in_search handlers;
    map_tab signals connected on tab creation.
  gui/search_tab.py: _LbListWorker QThread + SearchTab.load_lb_list() for
    direct LB-number loading (used by Map → List in Search).
  backend/db.py: get_entries_by_lb_list() — fetch entries by LB number list.
  backend/app.py: GET /api/entries/by_lb_list + GET /leaflet/<filename> routes.

---

[2026-05-19] — fix(backend/gui): security hardening — CC_SECURITY_REVIEW items #1–11

Fixed

  backend/app.py: #1 Path traversal in /api/master/import — resolve path and
    reject anything outside DATA_DIR/exports or imports; enforce .db extension.
  backend/app.py: #2 /api/master/import had no curator auth check — added
    is_curator() 403 guard matching the export endpoint.
  backend/app.py: #3 /api/lb_master/reconcile was unprotected — added
    is_curator() guard. /api/db/backup rate-limited to once per 60 s.
  backend/db.py: #4 Manifest sha256/master_schema_version not type-checked —
    validate isinstance and length before use; no longer exposes actual SHA on
    mismatch; added lower-bound check (schema ≥ 1).
  gui/setup_tab.py: #5 Blocking requests.post(timeout=600) on Qt main thread
    in _on_install_master and requests.post(timeout=300) in _on_publish_master —
    added _InstallMasterThread and _ExportMasterThread (QThread); both handlers
    now return immediately after starting their worker thread.
  backend/app.py: #6 status query param on /api/lb_master not allowlist-validated
    — returns 400 for any value outside public|private|missing.
  backend/app.py: #7 offset accepts negatives; history limit uncapped — clamped
    offset to ≥ 0, history limit to 1–500.
  backend/app.py: #8 reason field written to manifest/backup without length cap —
    truncated to 200 chars for export, 100 chars for backup.
  backend/app.py: #9 Raw str(exc) in catch-alls for import/export/reconcile/backup
    — replaced with log.exception + {"error": "internal_error"}.
  backend/db.py: #10 f-string table name interpolation — added _SAFE_IDENT
    assertion at module load to guard MASTER_TABLES and USER_TABLES.
  backend/app.py: #11 manual_notes stored without length cap — truncated to 1000.

[2026-05-19] — fix(gui): HiDPI-aware splash screen pixmap on Windows (TODO-049)

Fixed

  main.py: QPixmap(400, 120) was created at logical size with no device-pixel-ratio
    awareness. On Windows at 125%/150%/200% DPI scaling the splash appeared blurry.
    Now queries qt_app.primaryScreen().devicePixelRatio() after QApplication is
    constructed, creates the pixmap at (400*dpr) × (120*dpr) physical pixels, and
    calls pix.setDevicePixelRatio(dpr) so Qt renders it at native resolution.
    Falls back to dpr=1.0 if primaryScreen() returns None (headless/no display).

[2026-05-19] — feat(backend/gui): GET /api/status merged endpoint, halve status-bar loopback (TODO-048)

Added

  backend/app.py: GET /api/status returns database.get_stats() merged with
    database.get_bootleg_stats() under a "bootlegs" key. Halves per-tick loopback
    round-trips from two sequential GETs to one. Existing /api/db/stats and
    /api/bootlegs/stats routes are unchanged.

Changed

  gui/main_window.py: _do_status_fetch() now calls /api/status instead of
    /api/db/stats + /api/bootlegs/stats. Bootleg count read from s["bootlegs"]["total"].
    Removed the inner try/except for the second request — error path simplified to one
    catch.

[2026-05-19] — fix(gui): replace per-tick status thread with persistent poller (TODO-047)

Changed

  gui/main_window.py: _refresh_status() previously spawned a new daemon threading.Thread
    every 10 s (each QTimer tick). Replaced with a single long-lived "status-poller" daemon
    thread (_status_poll_loop) that sleeps via threading.Event.wait(timeout=10). Calling
    _refresh_status() (e.g. from setup_tab.stats_changed) now simply sets _status_wake,
    waking the sleeping thread immediately for an extra fetch. _status_stop + _status_wake
    events are both set in closeEvent to let the thread exit cleanly without joining.
    Removed QTimer and its import; removed the per-tick Thread spawn.

[2026-05-19] — fix(gui): skip QGraphicsDropShadowEffect on Windows to eliminate repaint lag (TODO-046)

Fixed

  gui/styles.py: apply_panel_shadow() now returns immediately on sys.platform == "win32".
    Qt Fusion (Windows) renders entirely in software, so blurRadius=12 shadow effects on
    11 panel widgets forced per-repaint offscreen blits that caused visible scroll/resize lag
    with large tables. Shadows are unaffected on Linux and macOS.

[2026-05-19] — fix(gui): move "Add Root Folder" rglob scan off main thread (BUG-080/TODO-045)

Fixed

  gui/verify_tab.py: _on_add_root_folder used sorted(root_path.rglob("*")) synchronously
    on the Qt main thread. Added _AddRootWorker(QThread) that runs the directory tree scan
    and per-subfolder audio-file check off-thread. _on_add_root_folder now disables the
    button and starts the worker; _on_add_root_finished calls _add_folder() for each
    discovered path and re-enables the button. Added _on_add_root_error for error reporting.
  gui/lbdir_tab.py: Identical fix — same _AddRootWorker pattern added, same slot structure.

[2026-05-19] — fix(main): skip --disable-gpu WebEngine flag on Windows (TODO-044)

Fixed

  main.py: --disable-gpu was applied to QTWEBENGINE_CHROMIUM_FLAGS unconditionally,
    including on Windows. This flag was added to work around Linux/XWayland issues
    (EGL_BAD_NATIVE_WINDOW, GPU-process blackout). On Windows, Chromium uses
    DirectX/ANGLE and GPU acceleration works correctly; forcing --disable-gpu switched
    the Map and Attachments WebEngine tabs to slow Swiftshader software rendering.
    The flag is now injected only when sys.platform != "win32". --disable-logging
    (suppresses Chromium stderr noise) remains unconditional on all platforms.

[2026-05-19] — chore(docs): Windows performance audit — add TODO-044–049 and BUG-080

Added

  TODO.md: TODO-044 (--disable-gpu on Windows), TODO-045 (rglob main-thread freeze),
    TODO-046 (QGraphicsDropShadowEffect repaint lag), TODO-047 (per-tick thread churn),
    TODO-048 (consolidated /api/status), TODO-049 (HiDPI splash pixmap).
  BUGS.md: BUG-080 — rglob("*") on main GUI thread in verify_tab and lbdir_tab.

[2026-05-19] — fix(backend): flat_file relative path, import concurrency guard, .st5 verification

Fixed

  backend/flat_file.py: _DOWNLOADS_DIR was Path("data/downloads") (relative to CWD).
    Changed to DATA_DIR / "downloads" so download/diff/apply work regardless of CWD.
  backend/app.py: /api/db/import POST had no "already running" guard. Two rapid requests
    could start concurrent imports, corrupting _import_state and double-executing the DB merge.
    Added 409 guard matching the pattern used by all other long-running routes.
  backend/checksum_utils.py: .st5 files parsed correctly (via _SHNTOOL_LINE_RE) but stored
    under 'st5' key only — shn_exp = exp.get('shntool') was always None, so verification
    never ran and st5_status was hardcoded 'na'. Fixed: .st5 entries now also populate the
    'shntool' key (when not already set by a .md5 file) and set has_shntool_entries = True.

[2026-05-19] — feat(backend): run_backend.py standalone launcher for phone/LAN use

Added

  run_backend.py: headless Flask launcher (no Qt GUI). Uses the same make_server
    restart loop as main.py. The Restart Server button on the admin page calls the
    in-process callback — only the Flask server recycles, the process stays alive.
    Start with: .venv/bin/python3 run_backend.py

[2026-05-19] — fix(backend/admin): restart button now restarts only the Flask server, not the GUI

Fixed

  main.py: replaced flask_app.run() with werkzeug make_server + serve_forever loop so the
    server can be shut down and restarted in-process without touching the PyQt6 GUI process.
    Added request_flask_restart() and _flask_restart_event / _flask_server globals.
  backend/app.py: added _restart_callback / set_restart_callback(). The admin_restart route
    now calls the callback (set by main.py on Linux) instead of os.execv, so only the Flask
    server recycles. Falls back to os.execv when no callback is set (Windows/standalone).
  backend/admin.html: updated Server card description — "GUI window stays open."

[2026-05-19] — feat(admin): site-crawler control + live status dialog in admin panel

Added

  backend/admin.html: Site Crawler card — Incremental / Full / Stop buttons, progress bar,
    live status line showing current URL. "Live View" button opens a modal dialog that
    polls /api/crawler/status every 1.5 s, displaying stage, fetched / 304 / skipped /
    failed counts and the current URL being fetched. Dialog closes on backdrop click.
  backend/app.py: GET /api/admin/status now includes "crawler" key
    (site_crawler.get_crawler_status() snapshot).

[2026-05-19] — feat(backend): mobile-friendly admin control panel at /admin

Added

  backend/admin.html: self-contained admin UI — dark theme, responsive grid, no external
    dependencies. Sections: DB stats + backup/reset, flat-file update pipeline,
    scraper start/stop with progress bar, LB master reconcile, server restart.
    Auto-polls /api/admin/status every 5 s; toast notifications for all actions;
    confirm overlay for destructive operations (reset DB, restart server).
  backend/app.py: three new admin routes:
    GET  /admin           — serves admin.html
    GET  /api/admin/status — combined DB/scrape/import/master/uptime snapshot
    POST /api/admin/restart — os.execv restart to pick up code changes (202 before exit)

[2026-05-19] — fix(backend/gui): map showed only 434 markers instead of ~9,700 (BUG-075)

Fixed

  backend/app.py: api_map_data() now passes owned=None (no filter) when the
    'owned' query param is absent; previously defaulted to False which applied
    a "non-owned only" WHERE clause. Also accepts "1" as a truthy value for
    the owned=true filter so the Owned-only checkbox works.
  gui/resources/map.html: JS popup corrected to read m.lb_number, m.date_str,
    m.lb_status instead of non-existent m.lb, m.date, m.status field names.
    owned filter now sends owned=true (was owned=1, not matched by Flask).

[2026-05-19] — chore(backend): add __main__ block to app.py for headless backend

Added

  backend/app.py: `if __name__ == "__main__":` entry point so the Flask
    server can be started without the GUI via `python -m backend.app [port]`.
    Port defaults to 5174; pass an integer argument to override.

[2026-05-19] — fix(db): exclude low-confidence geocodes from map markers (BUG-074)

Fixed

  backend/db.py: get_map_data JOIN on location_geocoded now filters out
    confidence='low' rows. Previously, low-confidence Nominatim matches
    (e.g. "Japan 2001" → a village in Indonesia) were shown as map markers.
    They are now counted as unplottable instead.

[2026-05-19] — chore(main): bind Flask to 0.0.0.0 for LAN accessibility

Changed

  main.py: Flask server now listens on 0.0.0.0 instead of 127.0.0.1, making all routes
    (including /map and /api/*) reachable from other machines on the local network.
    The local readiness probe in _wait_for_port still uses 127.0.0.1.

[2026-05-19] — fix(geocoder): retry on HTTP 429 with 60-second back-off (BUG-069)

Fixed

  backend/geocoder.py: geocode_one() now catches urllib.error.HTTPError before the generic
    Exception handler; a 429 response raises the private _RateLimitError sentinel instead of
    silently producing source='failed'. run_batch() wraps geocode_one() in a retry loop (up
    to _MAX_429_RETRIES=3 attempts); on each _RateLimitError it sets stage='rate_limited',
    sleeps _RATE_LIMIT_SLEEP=60 s, then retries without advancing the progress counter. If
    all retries are exhausted the location is written as source='failed' with a descriptive
    note so it can be picked up by --retry-failed later.

[2026-05-19] — feat(gui): column-width save/restore defaults in Setup tab (TODO-029)

Added

  gui/widgets/state_store.py: import weakref; self._registered list tracks every attach_table()
    call as (weakref.ref(table), key, factory_defaults). New methods: has_user_defaults (property),
    save_user_defaults(), restore_user_defaults(), restore_factory_defaults(), clear_user_defaults(),
    _apply_col_widths(). save/restore write immediately (no debounce); _apply_col_widths uses
    _restoring guard so programmatic resize doesn't trigger spurious live-width saves.
  gui/setup_tab.py: accepts state_store=None; new "Column Widths" QGroupBox with three buttons —
    "Save as Defaults", "Restore My Defaults" (disabled when no snapshot exists), "Restore Factory"
    (confirmation required). Status label shows saved vs. none state. _refresh_col_defaults_status()
    syncs button enable state on init.
  gui/main_window.py: SetupTab now receives state_store=self.state_store.

Fixed

  gui/setup_tab.py: removed duplicate layout.addWidget(ff_group) at end of _build_ui().

[2026-05-19] — feat(gui): click-to-sort on Lookup tab summary and detail tables (TODO-027)

Added

  gui/lookup_tab.py: _LookupSortProxy (QSortFilterProxyModel with lessThan() using sort_key_for());
    _SUMMARY_COL_KINDS / _DETAIL_COL_KINDS column kind arrays; _sum_src_row() / _det_src_row()
    helpers to map proxy→source indices. Both summary (default: LB Number ASC) and detail (default:
    Filename ASC) views now support click-to-sort with sort indicator arrows. All selection handlers,
    context menus, double-click, and _on_select_all_incomplete updated to use source row mapping.

---

[2026-05-19] — feat(backend/gui): auto GitHub release upload from Publish button (TODO-022)

Added

  backend/db.py: generate_release_notes() — markdown from lb_status_history + manual overrides
    since the previous master_published_at.
  backend/app.py: GET /api/master/status (returns master_version + master_published_at);
    POST /api/master/github_release — generates tag (master-YYYY-MM-DD[.N]), builds release notes,
    runs gh release create, returns {ok, tag, url}.
  gui/setup_tab.py: _GithubReleaseThread; _on_publish_master now reads prev master_published_at,
    exports, then uploads to GitHub in a background thread; _on_github_release_done shows tag + URL;
    _publish_status_label shows live progress below the Publish button.

---

[2026-05-19] — feat(gui): entry change history viewer in Lookup tab (TODO-005)

Added

  gui/lookup_tab.py: _ChangeHistoryDialog + _ChangeHistoryWorker; "History…" button in detail
    panel header, enabled when exactly one LB is selected in summary; fetches up to 200 rows from
    GET /api/entry/<lb>/changes and displays field, old value, new value, changed_at in a resizable
    table; background fetch never blocks the GUI thread.

---

[2026-05-18] — feat(gui): add curator geocoding controls to Setup tab and DB Editor tab

Changed

  gui/setup_tab.py: add Geocode Locations group box (curator only) with progress polling; _GeocodeRunThread POSTs /api/geocode/run, _GeocodeStatusThread polls /api/geocode/status every 2 s; group shown/hidden on curator toggle.
  gui/dbedit_tab.py: add Location Geocoding sub-panel (curator only) with filter dropdown (All/Failed/Low Confidence/Manual Only), Load button calling GET /api/geocode/locations, QTableWidget (7 cols, first col stretches), double-click → PlaceManualDialog; PlaceManualDialog pre-fills lat/lon/note, Save POSTs /api/geocode/location; all HTTP calls via _Worker(QThread), never on GUI thread.

---

[2026-05-18] — fix: crawler seeded from wrong URL + test suite (BUG-067, BUG-068)

Fixed

backend/site_crawler.py: Added SITE_HOME_URL = BASE_URL + "/LosslessBob.html" (real site entry point; domain root is a DreamHost placeholder). Changed crawl() default start_url from BASE_URL to SITE_HOME_URL. Added SEED_URLS constant (/bynumber/LBMbynumber.html, /detail/LB-bootleg-by-title.html) seeded on every crawl as safety-net index pages. Changed BeautifulSoup parser from "lxml" to "html.parser" (eliminates lxml import, removes deprecation warnings). Removed unused attachment_path import and unused local variable. (BUG-068)
backend/html_utils.py: Changed BeautifulSoup parser from "lxml" to "html.parser". (BUG-067)
backend/db.py: Fixed get_scrape_sessions() ORDER BY to add id DESC tiebreaker so sessions created within the same second are reliably ordered by insertion sequence.

Added

tests/test_scraper_crawler.py: 59-test suite covering html_utils.rewrite_links() (9 tests), paths.py SITE_DIR hierarchy (7 tests), db.py scrape_sessions+site_inventory helpers (14 tests), site_crawler.py pure URL utilities (18 tests), and /api/crawler/* Flask route smoke tests (7 tests). All 59 pass individually; see BUG-067 for combined-run limitation.

---

[2026-05-18] — feat: Dedicated Scraper tab + full-site mirror crawler (TODO-031)

Added

backend/site_crawler.py: BFS spider for losslessbob.wonderingwhattochoose.com. crawl(start_url, scope, force, delay_ms, daily_cap) runs in a daemon thread. _extract_links() discovers same-domain links. _fetch_page() uses If-Modified-Since for efficient incremental fetches (304 = skip, 200 = save + rewrite links). _url_to_local() maps URLs to data/site/ sub-dirs. Separate _crawler_state/_crawler_lock (no shared state with scraper.py). Rate limiting: 1500ms ±20% jitter, Retry-After on 429, exponential backoff on error, configurable daily cap, robots.txt cached per session.
backend/html_utils.py: rewrite_links(html, page_url, base_domain) — rewrites server-absolute paths to relative paths so cached pages work via file:// browsing. Uses BeautifulSoup; processes href, src, action attributes.
backend/paths.py: SITE_DIR = DATA_DIR / "site" and sub-constants SITE_DETAIL_DIR, SITE_FILES_DIR, SITE_LBBCD_DIR, SITE_BN_DIR replacing old PAGES_DIR/ATTACHMENTS_DIR. detail_page_path(), attachment_path(), find_lbdir_attachment() updated to use SITE_DETAIL_DIR / SITE_FILES_DIR. ensure_data_dirs() creates all site/ sub-dirs.
backend/db.py: scrape_sessions and site_inventory tables added to SCHEMA_SQL and MASTER_TABLES. Helpers: create_scrape_session(), finish_scrape_session(), get_scrape_sessions(), upsert_inventory(), get_inventory_stats(), get_inventory_page(), get_pending_urls(), get_downloaded_urls().
backend/app.py: 6 new routes: POST /api/crawler/start, GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/sessions, GET /api/crawler/inventory, GET /api/crawler/inventory/stats. backend.site_crawler imported at module level. _crawler_thread single-element list for background thread ref.
gui/scraper_tab.py: New Scraper tab. 5 panels (crawler control, session history, site inventory, entry scraper, bootleg catalog). _CrawlerStatusThread + _ScrapeStatusThread poll respective status endpoints every 1s. All scraper controls migrated from SetupTab. Settings (delay, daily cap) persisted to DB via /api/db/settings.
gui/main_window.py: ScraperTab imported and registered at tab index 10 (between DB Editor and Setup). Tab count: 12 → 13. Tab order comment updated.

Changed

gui/setup_tab.py: Removed all scraper controls (panels, buttons, progress bar, log widget, _log/_on_stop_scrape/_refresh_log_size methods, _LOG_FILE import). Kept: DB management, master data, qBittorrent credentials, WTRF Forum credentials, SoX status, flat-file update history, data-management purge controls. Dead _refresh_log_size() call removed from __init__.
backend/scraper.py: All path references updated from data/pages/ / data/attachments/ to data/site/detail/ / data/site/files/ via SITE_DETAIL_DIR / SITE_FILES_DIR / detail_page_path() / attachment_path() from paths.py.

---

[2026-05-18] — feat: Bootleg-CD Catalog (LBBCD) — scraper, Bootlegs tab, cross-tab integrations (TODO-030)

Added

backend/bootleg_scraper.py: scrape_bootlegs(force) — HEAD→diff→apply pipeline for the LBBCD index page. _parse_date() handles M/D/YY with 'xx' unknowns (2-digit year pivot Y>=30→19YY). _diff() uses (lb_number, title, date_str) natural key. Pre-scrape DB backup via backup_database(). bootleg_scrapes audit row written on every run. get_scrape_status() for polling.
backend/db.py: bootleg_titles + bootleg_scrapes tables added to SCHEMA_SQL and MASTER_TABLES. MASTER_SCHEMA_VERSION bumped to 2. Helper functions: get_bootleg_lb_numbers(), get_bootlegs_for_lb(), get_bootleg_stats(), get_bootlegs() (paginated/filtered), get_bootleg_scrape_history(). _BOOTLEG_SOURCE_URL constant.
backend/app.py: 7 new routes: POST /api/bootlegs/scrape, GET /api/bootlegs/scrape/status, GET /api/bootlegs/lb_numbers, GET /api/bootlegs, GET /api/bootlegs/by_lb/<lb>, GET /api/bootlegs/scrapes, GET /api/bootlegs/stats. bootleg_scraper imported.
gui/bootlegs_tab.py: New Bootlegs tab. Filter bar (text, year range, CDs, status, owned, has-LBBCD). Paginated QTableView (QAbstractTableModel). Detail pane with LBBCD link + "other titles for this LB" panel. open_lb_in_search signal → MainWindow switches to Search tab. bootleg_lbs_loaded signal pushes LB-number set to Search tab for badge rendering.
gui/main_window.py: Bootlegs tab registered at index 5 (between Search and My Collection). _on_bootleg_open_lb() handler. bootleg_lbs_loaded wired to search_tab.set_bootleg_lbs(). Shadow applied to bootlegs_tab.view. Status bar includes "Bootlegs: N" count when catalog is populated.
gui/search_tab.py: SearchModel._bootleg_lbs set; LB Number column shows 🎵 badge when lb_number is in the bootleg set; tooltip explains the badge. set_bootleg_lbs() public method on SearchTab.
gui/setup_tab.py: "Bootleg-CD Catalog (LBBCD)" QGroupBox added to layout; "Scrape Bootleg Catalog" button + Force checkbox + status label; bootleg scrape history table (5 columns); _on_scrape_bootlegs(), _poll_bootlegs_scrape(), _load_bootlegs_history() handlers. History loads on showEvent.

---

[2026-05-18] — feat(backend/gui): Download Missing Pages — cache HTML without metadata scrape (TODO-002)

Added

backend/scraper.py: download_pages_range(lb_numbers, force, delay_ms) — fetches detail pages and saves them to data/pages/ using the existing _scrape_state so the progress bar, stop button, and log all work. last_action="downloaded" distinguishes page fetches from full metadata scrapes. 404s are treated as skipped (not errors) since no DB writes occur.
backend/app.py: POST /api/scrape/download_pages — body: {start_lb?, end_lb?, force?}. Builds a full integer range (1..max_lb by default) and delegates to _start_download_pages_thread(); _start_download_pages_thread() added alongside _start_scrape_thread().
gui/setup_tab.py: Row 4 "Download Missing Pages" button added to the scraper grid. _on_download_pages() handler; _page_download_mode flag on SetupTab. _on_scrape_status() updated to use "Downloading" verb, "already cached" skip text, and "Downloaded LB-X [web]" log lines in download mode; completion message shows downloaded/cached/error counts and refreshes the pages-count label.

---

[2026-05-18] — fix/feat: TODO-006 connection leak, TODO-001 pages count, TODO-016 forum footer

Changed

backend/db.py: Added close_connection(db_path) — closes and evicts the per-thread SQLite handle for a given path. Prevents stale handle being returned for temp_import.db after it is deleted.
backend/importer.py: Calls close_connection(temp_db_path) before both unlink() sites in run_import() so the thread-local pool is clean for subsequent imports. (TODO-006)
backend/paths.py: Added APP_VERSION = "1.0" constant.
backend/forum_poster.py: Replaced hardcoded _FOOTER string with _build_footer() function that reads the WTRF username from the OS keyring via get_credentials(SERVICE_WTRF) and uses APP_VERSION; falls back to "kuddukan" when no credential is stored. (TODO-016)
gui/setup_tab.py: "Use local pages" checkbox now shares a row with a grey count label "(N pages cached)" populated by _refresh_pages_count(), which globs data/pages/*.html. Called from _load_settings(). (TODO-001)

---

[2026-05-18] — fix(gui/db): search tab row colours delayed 5–6 s after first display (BUG-066)

Changed

gui/search_tab.py: Removed self._page = 0 / _render_page() call from _on_xref_loaded(). model.set_xref_map() already emits dataChanged for the Xref column; the full model reset was the cause of the delayed colour paint. Added _prefetch_owned() called at __init__ so the owned set is warm before the first search render.
backend/db.py: Added idx_chk_xref_pos partial index ON checksums(lb_number, xref) WHERE xref>0. Eliminates the full checksums table scan in get_xref_map() that caused the 5–6 s delay.

---

[2026-05-18] — feat(backend/gui): lb_alias + folder_lb_link disambiguation (CC_LB_INTEGRITY item 8)

Added

backend/db.py: lb_alias and folder_lb_link tables added to SCHEMA_SQL. lb_alias added to MASTER_TABLES; folder_lb_link added to USER_TABLES. New helpers: resolve_aliases(), get_folder_link(), set_folder_link(), delete_folder_link(), add_lb_alias(), delete_lb_alias(), get_lb_aliases() — all with type hints and Google-style docstrings.
backend/app.py: 7 new endpoints: GET /api/lb_alias, POST /api/lb_alias (curator-only), DELETE /api/lb_alias/<alias_lb> (curator-only), GET /api/lb_alias/resolve, GET /api/folder_link, PUT /api/folder_link, DELETE /api/folder_link.
gui/rename_tab.py: RenameTab now accepts flask_port parameter. Resolution order on populate_from_lookup: (1) folder_lb_link lookup; (2) lb_alias collapse; (3) fall back to multiple_ids. Right-click: "Link this folder…", "Unlink this folder", "Save as master alias…" (curator-only). _AliasDialog for curator alias creation.
gui/main_window.py: Pass flask_port to RenameTab constructor.
gui/dbedit_tab.py: "LB Aliases" QGroupBox panel. Auto-loads on load_tables(). Add/Delete curator-gated.

[2026-05-18] — feat(backend/gui): Flat-file update check rework (CC_LB_INTEGRITY item 9)

Added

backend/flat_file.py: New pipeline module — discover_flat_file_release, download_flat_file_release,
  diff_flat_file_release, apply_flat_file_release, defer_flat_file_release, get_releases,
  get_release_changelog. Discovers new releases from the LosslessBob download page, downloads
  the zip, diffs against the live checksums table (tab-delimited format matching importer.py),
  and applies changes with a full flat_file_changelog audit trail. Auto-backup before apply.
  Reconciles lb_master for touched LBs post-apply.
backend/db.py: flat_file_releases and flat_file_changelog tables added to SCHEMA_SQL and
  MASTER_TABLES. _bootstrap_flat_file_legacy() for first-run migration.
backend/app.py: 7 new endpoints under /api/flat_file/*.
gui/setup_tab.py: "Check for Flat File Update" button, _UpdateAvailableDialog, Flat File History panel.

Changed

backend/scraper.py: Removed broken check_for_update() which scraped the bynumber page.

[2026-05-18] — feat(gui/backend): Click-to-sort on all major tables (CC_LB_INTEGRITY item 10)

Added

gui/widgets/sort_keys.py: SortableTableItem + sort_key_for() with typed sort keys.
gui/widgets/state_store.py: get_sort()/set_sort() for persistent sort state.
gui/lbdir_tab.py, gui/verify_tab.py: Client-side sort via SortableTableItem.
gui/search_tab.py, gui/collection_tab.py, gui/dbedit_tab.py: In-memory/server-side sort via sectionClicked.
backend/app.py: sort_col/sort_dir params on /api/search, /api/collection, /api/collection/missing.

[2026-05-18] — feat(gui/backend): Override export/import JSON endpoints and DB Editor buttons

Added

backend/db.py: export_overrides() and import_overrides() helpers.
backend/app.py: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import.
gui/dbedit_tab.py: "Export Overrides" and "Import Overrides" buttons in DB Integrity panel.

---

[2026-05-18] — feat(db/backend): add location_geocoded schema, Nominatim geocoder, CLI tool

Added

backend/geocoder.py: Nominatim geocoder module. `geocode_one(location_text)` performs a single
  lookup (stdlib urllib only, no extra deps). `place_manual(location_text, lat, lon, note)` inserts
  a manual coordinate with `manual_override=1` so batch runs never overwrite it. `run_batch(limit,
  retry_failed, dry_run)` batch-geocodes all un-geocoded `entries.location` values with a 1.1-second
  sleep between requests (Nominatim ToS). Thread-safe `_progress` dict for future GUI integration.
  `get_progress()` returns a snapshot for polling.

tools/geocode_locations.py: CLI wrapper for `run_batch`. Accepts `--limit N`, `--retry-failed`,
  `--dry-run`. Configures root logging and resolves project root so it can be run directly from the
  project root directory.

Changed

backend/db.py: Added `location_geocoded` table (DDL inside `_SCHEMA`) — columns: location_text
  (PK), lat, lon, source, confidence, display_name, manual_override (DEFAULT 0), note, geocoded_at.
  Index `idx_geo_source` on source column. Table added to `MASTER_TABLES` so it is included in
  master-data export/import. Added `get_map_data(filters, db_path)` — returns `{"markers": [...],
  "unplottable_count": int}` for a future map tab; joins entries, location_geocoded, lb_master, and
  my_collection; supports filters: status, owned, year_min, year_max, q.

---

[2026-05-18] — feat(backend): add /map, /api/map/data, /api/geocode/* routes

Changed

  backend/app.py: add GET /map, GET /api/map/data, POST /api/geocode/run, GET /api/geocode/status, POST /api/geocode/location, GET /api/geocode/locations. Also added send_from_directory to Flask imports.

---

[2026-05-18] — feat(gui): add Map tab with Leaflet world map, marker clusters, heatmap toggle, browser view

Added

  gui/map_tab.py: Map tab widget with QWebEngineView + Open in Browser fallback
  gui/resources/map.html: Leaflet map page with filters, marker clustering, heatmap mode

---

[2026-05-18] — feat(gui/backend): Map tab wired into main window, PyQt6-WebEngine added to requirements

Changed

  gui/main_window.py: register Map tab after ThemeTab via graceful try/except import fallback so the
    app starts normally even when gui/map_tab.py is not yet present in the worktree
  requirements.txt: PyQt6-WebEngine already pinned at 6.7.0; requests already pinned at 2.32.3 — no
    version changes required
  PROJECT.md: document map feature: new files (map_tab.py, map.html, geocoder.py,
    geocode_locations.py), location_geocoded schema, six new API routes (GET /map,
    GET /api/map/data, POST/GET /api/geocode/*), tab count updated to 11

---

[2026-05-19] — docs(backend): add type hints and Google-style docstrings to all app.py route handlers (TODO-004)

Changed

backend/app.py: Added `Response` to module-level Flask imports. Added `-> Flask` return type and one-line docstring to `create_app()`. Added `-> Response` return types to all 67 route handler functions. Added URL path-parameter type hints across all parameterised routes. Added Google-style docstrings to 47 route functions that previously had none; left 20 existing docstrings unchanged. Added docstring and parameter types to `_start_scrape_thread()` and `_do_spectro_batch()` helpers.

[2026-05-17] — fix(gui): Column widths now actually persist across restarts (GuiStateStore root-cause fix)

Fixed

gui/widgets/state_store.py: Two root causes identified and fixed via headless regression test.
  Bug A — Qt fires sectionResized for all columns during initial layout, AFTER _on_resized is
  connected but BEFORE _restore sets _restoring. _on_resized saved the auto-calculated garbage
  widths; _restore then read them back. Fix: set _restoring.add(tid) at the very start of
  attach_table, before any signal or timer is wired.
  Bug B — _migrate_from_qsettings was copying column widths from old QSettings into the new JSON.
  Those QSettings were written by the same buggy _on_resized, so they contained auto-layout garbage
  (e.g. 5340px for "Description"). Fix: skip column-width migration entirely; only geometry is
  safe to migrate. Added 10 <= w <= 3000 sanity guard in get_col_widths as a second line of
  defence against any future garbage reaching the store.
Also cleared garbage from system QSettings (LosslessBob/SearchTab col_widths).

[2026-05-17] — feat(gui): Reliable column width persistence via GuiStateStore (CC_LB_INTEGRITY item 11)

Added

gui/widgets/state_store.py: `GuiStateStore` — single source of truth for persistent GUI widget state. Stores column widths, window geometry in `data/gui_state.json`. Atomic writes (tempfile + os.replace), 500 ms debounced saves, `_restoring` guard to suppress spurious saves during programmatic restore. One-time QSettings migration on first run.

Changed

gui/main_window.py: Removed `QSettings` window geometry; replaced with `state_store.restore_window` / `save_window`. `closeEvent` calls `state_store.flush()` before close. `GuiStateStore` instance created at startup and passed to all tabs with tables.
gui/search_tab.py: Removed `_qsettings`, `_col_widths`, `_widths_applied`, `_resizing_programmatically`, `_load_col_widths`, `_save_col_widths`, `_on_col_resized`, `_set_default_col_widths`, `_apply_col_widths`. Now calls `state_store.attach_table(view, "search.results")`. `_render_page` no longer snapshots/restores widths around model resets.
gui/dbedit_tab.py: Removed `QSettings` and `_SETTINGS_PATH`. `_snapshot_and_save` / `_load_saved_widths` / `_on_col_resized` now use `state_store.get_col_widths` / `set_col_widths` with key `dbedit.<table_name>`.
gui/collection_tab.py: Removed `_coll_col_widths`, `_miss_col_widths`, `_wish_col_widths` in-memory tracking and `_apply_coll_col_widths` / `_apply_miss_col_widths`. All 7 tables (my_collection, missing, wishlist, forum_history, torrent_history, entry_torrents, entry_forum_posts) now use `state_store.attach_table`.
gui/lbdir_tab.py: `summary_table` now uses `state_store.attach_table`; removed `resizeColumnsToContents()` call from `_populate_summary` that clobbered user widths on each check run.
gui/rename_tab.py: Removed hardcoded `setColumnWidth(0, 50)` in `_build_ui`; replaced with `state_store.attach_table`.

[2026-05-17] — feat(gui): Standardize folder name button in Rename tab (CC_LB_INTEGRITY item 13)

Added

backend/folder_naming.py: `build_standard_name(lb_number, date_str, location, lb_status)` — builds canonical `YYYY-MM-DD Location (LB-XXXXX)[-NFT]` folder name. Shared between Rename tab and Collection tab. Imports `_parse_date` lazily from `backend/torrent_maker`.

backend/app.py: `GET /api/folder_naming/standard/<lb>` — returns `{standard_name, lb_status, nft}`. Looks up entry metadata and lb_master status; applies NFT suffix via `build_standard_name`.

gui/rename_tab.py: "Standardize Selected" button — for each checked single-LB row, fetches canonical name via `get_entry()` + `get_lb_status()` + `build_standard_name()`, updates the proposed name, and escalates state to `needs_rename` when the standard name differs from the current folder name. Right-click "Standardize Name (YYYY-MM-DD Location…)" action applies the same transform to a single row.

gui/rename_tab.py: `RenameModel.update_state(idx, state)` — new method to update a row's state and emit `dataChanged` for the full row.

Fixed

gui/rename_tab.py: `_on_strip_wrong_lb()` now calls `update_state(i, "needs_rename")` after updating the proposed name. Previously the state stayed `wrong_lb`, which is not in the rename-eligible set, so stripped rows could never be renamed by the "Rename Selected" button. (BUG-064)

---

[2026-05-17] — feat(gui): lb_status filter + tinting across Lookup, Attachments, Rename, Lbdir tabs (TODO-021)

Changed

backend/db.py: `get_lb_statuses_batch(lb_numbers)` — single batch SELECT from lb_master, returns {lb_number: lb_status} dict for bulk UI colouring. Also stamps lb_status onto each lb_summary dict in lookup_checksums() for the filter combobox.

gui/lookup_tab.py: "All LB statuses / Public only / Private only / Missing only" QComboBox in Summary header row. `_lb_status_filter` + `_sum_lb_statuses` list drive filter guard in `_apply_filters()`. Private → #B3E5FC, Missing → #E0E0E0 row tinting ahead of match-quality colors.

gui/rename_tab.py: LB Found column (col 3) tinted #B3E5FC/E0E0E0 for Private/Missing when no NFT discrepancy is active.

gui/attachments_tab.py: `_render_tree_page()` batch-fetches lb_status for the current page via `get_lb_statuses_batch()`, tints Private parent items light blue and Missing items gray, with tooltip text.

gui/lbdir_tab.py: `_populate_summary()` batch-fetches lb_status and tints the LB# column (col 1) by lb_status; verification-result color still applies to all other columns.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Changed

backend/db.py: lookup_checksums() now also stamps lb_status onto each lb_summary dict (reusing the same _lb_status_map batch query that already annotates detail items).

gui/lookup_tab.py: Added "All LB statuses / Public only / Private only / Missing only" QComboBox to the Summary header row. _lb_status_filter state drives a new guard in _apply_filters() that filters sum_indices by _sum_lb_statuses. _process_result() populates _sum_lb_statuses (parallel to _sum_lb_nums) from s["lb_status"]. Private rows get light-blue (#B3E5FC) and Missing rows get light-gray (#E0E0E0) background overrides ahead of match-quality colors. lb_status stored in sum_user_data per row.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Added

backend/folder_naming.py: New module. `apply_nft_suffix(name, lb_status)` appends -NFT when lb_status='private', idempotent, case-normalises existing suffix. `strip_nft_suffix(name)` removes trailing -NFT. `has_nft_suffix(name)` predicate. `nft_discrepancy(folder_name, lb_status)` returns 'missing'|'stale'|'unknown'|None for discrepancy detection.

backend/db.py: `should_mark_nft(lb_number)` returns True when lb_status='private'. `lookup_checksums()` now annotates each detail item with `lb_status` from lb_master via a single batch lookup, making the status available to downstream callers (rename tab, etc.) without extra API calls.

gui/rename_tab.py: Imports `apply_nft_suffix`, `strip_nft_suffix`, `nft_discrepancy` from `backend.folder_naming`. `populate_from_lookup()` builds a `lb_status_map` from detail item annotations, applies NFT suffix to proposed names for Private LBs, proposes stripping -NFT for Public LBs that still have it, and escalates state to `needs_rename` when the proposed name differs from current. Multi-LB rows conservatively inherit `lb_status='private'` if any candidate LB is Private. `RenameModel.data()` overrides BackgroundRole and adds ToolTipRole for NFT discrepancy states (_NFT_DISC_COLORS / _NFT_DISC_TIPS). `_on_strip_wrong_lb()` also applies NFT suffix when rebuilding proposed names. Legend gains three new NFT-discrepancy swatches.

gui/collection_tab.py: `_get_standard_lb_name()` calls `/api/lb_master/<lb>/nft` and appends -NFT to the returned base name when the response is `{nft: true}`.

---

[2026-05-17] — feat(integrity): Re-scrape Private LBs button in Setup tab (TODO-017)

Added

backend/app.py: POST /api/scrape/private_rescrape — queries lb_master for all lb_status='private' rows, starts the scraper with force=True on those lb_numbers, returns {ok, total}. Uses existing _start_scrape_thread so standard /api/scrape/status polling applies.

gui/setup_tab.py: "Re-scrape Private LBs" button added as Row 3 in the Scraper section grid. Clicking it fetches the current private count from /api/lb_master/stats, shows a confirmation dialog with the count, and calls the new endpoint. Uses the existing _ScrapeStatusThread + _on_scrape_status machinery for progress/completion. On completion, fetches updated stats and appends "N promoted to Public, M private remain." to the status message. _on_scrape_all and _on_scrape_range now also disable this button while a scrape is running.

---

[2026-05-17] — feat(db): master/user data ownership split + master publish/install + curator mode (TODO-020)

Added

backend/db.py: MASTER_TABLES, USER_TABLES, MASTER_META_KEYS, USER_META_KEYS, MASTER_SCHEMA_VERSION constants formalise which tables ship in a master release and which stay local. New `is_curator()` / `set_curator()` helpers backed by `meta.is_curator='1'|'0'` (user-local, never shipped). New `export_master_db(reason)` produces a master-only snapshot in `data/exports/` via `VACUUM INTO` → drop every USER_TABLES table → filter `meta` to MASTER_META_KEYS → stamp `master_version` / `master_published_at` / `master_schema_version` → VACUUM → verify (no user tables, no non-master meta keys) → SHA256 → write `<file>.manifest.json` sidecar. New `import_master_db(snapshot_path)` validates the manifest SHA256, refuses incoming schema versions newer than this client, takes a `pre_master_import` backup, ATTACHes the snapshot, copies only MASTER_TABLES, replaces only MASTER_META_KEYS in `meta`, rebuilds the `entries_fts` virtual table, and returns a summary (row counts, pre/post status distribution, backup path).

backend/app.py: GET /api/curator and POST /api/curator endpoints toggle the curator flag (body `{enabled: bool}`). POST /api/master/export requires `is_curator=true` (returns HTTP 403 `error=curator_required` otherwise); returns `{ok, path, manifest_path, manifest}`. POST /api/master/import (body `{path}`) returns the import summary or 400/404 with `error=sha256_mismatch | schema_too_new | not_found`.

gui/setup_tab.py: New "Master Data" QGroupBox below Database. Curator-mode checkbox persists via `/api/curator`. Publish Master Update button (curator-only, gated by checkbox) runs the export and shows a confirmation dialog with version, sha256 prefix, row counts, status distribution, and override count. Install Master Update button opens a file picker (defaults to `data/exports/`) and applies the chosen snapshot with a pre/post status diff in the result dialog. New `_load_curator_status()` called at init reflects the persisted flag in the UI.

tests/test_master_data.py: 13 pytest tests covering the MASTER/USER table constants and disjointness, MASTER_META_KEYS whitelist (no user keys leak), curator-flag round-trip, export-excludes-user-data, SHA256-matches-file-contents, version-stamping, end-to-end import preserves user collection + user meta keys (qbt_*, search_page_size, is_curator) while replacing master tables and master meta keys (import_hash, master_version), SHA-mismatch rejection (ValueError), schema-too-new rejection (RuntimeError), pre-import backup creation, and Flask 403 guard when curator mode is off.

---

[2026-05-16] — feat(integrity): lb_master status system, forum post guard, Search/Collection status columns, DB Editor integrity panel

Changed

backend/db.py: Added lb_master and lb_status_history tables to SCHEMA_SQL. Added backup_database(), migrate_lb_master(), reconcile_lb_status(), reconcile_all_lb_master(), set_lb_manual_override(), clear_lb_manual_override(), get_lb_master_row(), get_lb_master_stats(), get_lb_status(), is_postable_to_forum(), get_lb_master_list(), get_lb_status_history(). search_entries() now LEFT JOINs lb_master to return lb_status on every row. get_collection() and get_missing_from_collection() also return lb_status. migrate_lb_master() is called once from init_db() background thread and deletes entries.status='missing' tombstones after populating lb_master. lb_master.lb_status CHECK constraint enforces 'public'|'private'|'missing'. backup_database() uses VACUUM INTO with microsecond-precision timestamps to avoid filename collisions; keeps last 10 backups.

backend/app.py: Added 9 new endpoints: GET /api/lb_master/stats, GET /api/lb_master/<lb>, GET /api/lb_master, POST /api/lb_master/reconcile, GET /api/lb_master/history/<lb>, PUT /api/lb_master/<lb>/manual, DELETE /api/lb_master/<lb>/manual, GET /api/lb_master/<lb>/nft, POST /api/db/backup. Added forum post guard to preview_forum() and post_forum(): returns HTTP 403 with error=lb_private|lb_missing|status_unknown for non-public LBs.

backend/importer.py: After flat-file merge, calls migrate_lb_master() on first import (lb_master empty) or reconcile_lb_status() for every touched LB on subsequent imports.

backend/scraper.py: Calls reconcile_lb_status() after every scrape_entry() success and 404, wiring the scraper into the lb_master lifecycle.

gui/search_tab.py: Added "Status" column (col 1) to HEADERS. Replaced "Missing only" checkbox with LBStatusComboBox-style QComboBox (All statuses / Public only / Private only / Missing only / Needs review). _filtered_results() uses the status combobox. Background coloring now reads lb_status from result rows (public=default, private=light blue #B3E5FC, missing=light gray #E0E0E0).

gui/collection_tab.py: Added "Status" column (col 1) to COLL_HEADERS and MISS_HEADERS. _CollectionModel.data() and _MissingModel.data() display lb_status and apply matching background colors. _on_post_forum() adds a hard blocking modal dialog for private/missing LBs before attempting any network call. _on_post_forum_done() surfaces backend 403 forum-guard errors with the same modal (handles stale-status race).

gui/dbedit_tab.py: Added "DB Integrity" QGroupBox to the left panel with: live stats label (Public/Private/Missing/Max/Overrides/Needs Review), Reconcile All button (→ POST /api/lb_master/reconcile with confirmation), Show Needs Review button (selects lb_master + applies needs_review:1 search), Backup DB Now button (→ POST /api/db/backup with result dialog). load_tables() now also calls load_integrity_stats().

Added

tests/test_lb_master.py: 27 pytest tests covering schema creation, migrate_lb_master idempotency and status precedence, reconcile_lb_status transitions and override respect, stats counts, importer integration, is_postable_to_forum logic, Flask forum endpoint guard (HTTP 403 for private/missing), and GUI column/widget presence checks (skipped without DISPLAY).

[2026-05-16] — fix(gui): crash on theme apply due to non-existent self.table reference

Fixed

gui/collection_tab.py: resize_columns_to_font() referenced self.table, which only exists on the unrelated _ScanPreviewDialog class — not on CollectionTab. Caused AttributeError on every theme/font change and aborted the app. Removed the stray block; the other view/table resizes were already covering CollectionTab's real widgets.

---

[2026-05-16] — feat(gui): resize table columns to fit whenever font size changes

Added

gui/search_tab.py: resize_columns_to_font() — calls resizeColumnsToContents() on the search results view.
gui/collection_tab.py: resize_columns_to_font(font_size) — resizeColumnsToContents() on coll/miss/wish views and the LB lib table; scales torrent_history_table and forum_posts_table hardcoded pixel widths by font_size/9.
gui/dbedit_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the data table.
gui/lookup_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail views.
gui/rename_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the rename view.
gui/verify_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/lbdir_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/main_window.py: _on_theme_applied() now reads the current font size from theme_tab and calls resize_columns_to_font() on every tab after applying the stylesheet.

---

[2026-05-16] — feat(dbedit): add LB# search field to DB Editor toolbar

Added

gui/dbedit_tab.py: "LB#:" label + lb_input QLineEdit (width 80px) added to the toolbar between "Load Records" and the text search field. Pressing Enter in the field triggers the search; the field is cleared on table switch and "Load Records".
backend/app.py: dbedit_rows now accepts an optional lb_number query param; when the table has an lb_number column and the value is a valid integer, it appends AND lb_number = ? to the WHERE clause (combinable with the existing text search).

---

[2026-05-16] — feat(gui): add font family and font size controls to the Themes tab

Added

gui/styles.py: build_stylesheet() and apply_theme() now accept font_family and font_size keyword args; the chosen font is prepended to the platform stack and the size replaces the hardcoded 9pt.
gui/theme_tab.py: Font row (QComboBox + QSpinBox) inserted in _build_ui() below the colour swatches; _on_apply(), _save_settings(), and load_and_apply_saved() wired to read, persist, and restore font settings via QSettings keys theme/font_family and theme/font_size.

Changed

gui/search_tab.py: _prev_btn / _next_btn setFixedWidth(80) → setMinimumWidth(80) so buttons expand at larger font sizes.
gui/collection_tab.py: _coll_prev_btn / _coll_next_btn setFixedWidth(80) → setMinimumWidth(80).
gui/dbedit_tab.py: prev_btn / next_btn setFixedWidth(70) → setMinimumWidth(70).

---

[2026-05-16] — fix(db): searching a bare integer now always returns the matching lb_number entry

Fixed

backend/db.py: After the FTS5 search in search_entries, if the query is a bare integer and the matching lb_number is not already in the FTS results, a direct lb_number lookup is performed and the matching entry is prepended. Fixes entries like LB-01797 (Paris, 7/6/78) that have a webpage and metadata but no text fields containing their own lb_number, making them invisible to numeric search queries.

---

[2026-05-16] — fix(db): redefine "missing" as entries with no webpage, not entries with no checksums

Fixed

backend/db.py: get_missing_lb_numbers now queries entries.status instead of the checksums table. An entry is missing only when status='missing' (scraper confirmed no page) or the lb_number was never scraped. Entries with status='ok' are real entries and are never returned as missing even if they have no checksums or attachments (e.g. LB-12404). Previously the function returned any lb_number in range 1..max_lb absent from the checksums table, which incorrectly included hundreds of real entries that simply have no downloadable content.

---

[2026-05-16] — fix(attachments): tree page change glitches — viewport not reset after clear

Fixed

gui/attachments_tab.py: _render_tree_page now calls scrollToTop() after populating the new page so the viewport always lands at the top. Also wrapped clear+populate in setUpdatesEnabled(False/True) to suppress incremental repaints during the bulk insert, eliminating visual tearing.

---

[2026-05-16] — feat(attachments): paginate cached LB tree to 1000 entries per page with prev/next buttons

Added

gui/attachments_tab.py: Added PAGE_SIZE = 1000 class constant and _page / _all_lb_dirs state. Split _refresh_tree into a collector phase (builds sorted list of non-empty LB dirs) and _render_tree_page (populates tree for the current page slice). Added ◀ Prev / page label / Next ▶ navigation row that auto-shows in cached view and hides in missing view. _jump_to_lb now calculates the target page from _all_lb_dirs and navigates there before scrolling. Buttons are disabled when at the first or last page.

---

[2026-05-16] — fix(attachments): move WebEngine warmup to app startup instead of first tab visit

Fixed

gui/attachments_tab.py: QWebEngineView initialization (and about:blank warmup) now scheduled via QTimer.singleShot(0) in __init__ so it fires on the first event-loop tick after the main window appears — while the user is still on the Lookup tab — rather than on the first Attachments tab visit. Removed _web_initialised flag and the lazy-init block from showEvent. Added early-return guard in _init_web_view to prevent double-init. Removed the fallback _init_web_view() call from _open_lb_in_webview since the view is always ready by the time the user can interact.

---

[2026-05-16] — fix(main): disable Chromium GPU process to fix full-window blackout and GBM format errors on Linux

Fixed

main.py: Added --disable-gpu to QTWEBENGINE_CHROMIUM_FLAGS. Chromium's GPU process was hijacking the shared OpenGL context (AA_ShareOpenGLContexts) on Qt 6.7/XWayland, causing the entire application window to flash black. --disable-gpu prevents the GPU process from starting; Chromium uses Swiftshader software rendering instead, which is sufficient for the simple pages this app displays. Also eliminates the spurious "Unknown or not supported format: 808530000" (P010 GBM probe) stderr errors.

---

[2026-05-16] — fix(attachments): warm up WebEngine GPU process on tab open to prevent first-load window flash

Fixed

gui/attachments_tab.py: Loading about:blank immediately after QWebEngineView is added to the stack during _init_web_view. This forces the GPU/renderer subprocess to start while the tab is quietly initialising rather than on the first user-triggered URL load, eliminating the native-window flash on Linux.

---

[2026-05-16] — feat(attachments): right-click "Open in browser pane" on tree and missing list

Added

gui/attachments_tab.py: Right-click context menu on both the cached tree and the missing list shows "Open LB-NNNNN in browser pane". Selecting it loads the DETAIL_URL for that entry directly into the embedded QWebEngineView (right panel) instead of opening an external browser. DETAIL_URL imported from backend.scraper; QUrl moved to top-level import and removed from inline lazy import in _preview_file.

---

[2026-05-16] — feat(attachments): Missing LB list with scrape capability

Added

backend/db.py: get_missing_lb_numbers() — returns list of integers in range 1..max_lb absent from the checksums table.
backend/app.py: GET /api/db/missing_lb_numbers route backed by get_missing_lb_numbers().
gui/attachments_tab.py: _MissingThread fetches missing list from backend. Left panel now has Cached/Missing toggle buttons that swap a QStackedWidget between the existing tree and a new QListWidget. Jump-to search box works in both views. "Scrape Selected Entry" button in Missing view calls the same _ScrapeThread; on success the entry is removed from the missing list and the cached tree is marked stale. "No attachments found" status confirms true gaps.

---

[2026-05-16] — fix(gui): xref checkbox — search adds Xref column; collection filters on owned xref folders only

Changed

gui/search_tab.py: Added "Xref" column (col 5) to the search results table showing which xref numbers exist for each entry. _XrefWorker now calls GET /api/checksums/xref_map (returns {lb: [xref_values]}) instead of the bare LB list; SearchModel gains _xref_map and set_xref_map(); _on_xref_loaded converts string JSON keys to ints and pushes the map to the model.

gui/collection_tab.py: "Xref only" checkbox now filters to collection entries where the folder_name contains "xref" (i.e., the user has an xref-named folder in their collection). Previously it filtered on whether the LB exists in the master DB xref list, which was wrong — it showed any LB that has xref variants, not specifically the entries the user collected as xref folders.

backend/db.py: Added get_xref_map() — returns {lb_number: [xref_val, ...]} for all lb_numbers with xref checksums.

backend/app.py: Added GET /api/checksums/xref_map route backed by get_xref_map().

---

[2026-05-16] — feat(gui): attachments tab layout overhaul — wider tree, stat label moved, LB jump-to search box

Changed

gui/attachments_tab.py: Moved the "Entries with cached files" stat label into the left panel (above the tree) so it no longer floats in dead space. Splitter initial sizes changed from 300/700 to 420/580 to give the tree more room. Outer VBoxLayout now uses stretch=1 on the splitter so it fills the full widget height. Added QLineEdit + "Go" button at the bottom of the left panel to jump the tree selection to a typed LB number (accepts plain digits, "LB-NNNNN", or "LBNNNNN").

---

[2026-05-16] — feat(gui): add Forum History and Torrent History tabs to My Collection

Added

gui/collection_tab.py: Two new inner tabs ("Forum History" and "Torrent History") beside Duplicates. Each shows a global, all-entry table loaded lazily on first activation with a Refresh button. Forum History shows LB#, Date, Location, Posted timestamp, Subject with Open in Browser and Remove Record actions and a right-click context menu. Torrent History shows LB#, Date, Location, Created timestamp, Source Folder, Added to qBt status. Right-click on either table offers "Go to LB-XXXXX in My Collection" navigation.

backend/db.py: Added get_all_forum_posts() and get_all_torrents() — full-table queries joined with entries for date_str and location.

backend/app.py: Added GET /api/forum_posts and GET /api/torrents routes.

---

[2026-05-16] — feat(gui): add hover highlight to tab bar tabs

Added

gui/styles.py: Added `QTabBar::tab:hover` rule that blends `tab_bg` halfway toward `tab_selected` using the existing `_blend_hex()` helper, giving a subtle visual cue as the mouse moves over inactive tabs without affecting the selected tab's appearance.

---

[2026-05-16] — fix(gui): button text color now auto-contrasts against accent instead of using header_fg

Fixed

gui/styles.py: `QPushButton` text was hardcoded to `{t['header_fg']}` (Table Header Text), which had no logical connection to buttons and gave wrong results on many themes. Added `_button_text_color()` which picks black or white based on the accent's luminance — the same approach the theme swatch labels use. Each button state (normal, hover, pressed) now gets its own computed text color.

---

[2026-05-16] — fix(gui): disabled buttons now match the active theme instead of rendering as hardcoded gray

Fixed

gui/styles.py: `QPushButton:disabled` was hardcoded to `#A0A0A0` / `#E0E0E0` regardless of theme. On dark themes like Tokyo Night the gray buttons clashed visually with the dark background. Added `_blend_hex()` helper and replaced the hardcoded values with theme-derived colors (accent blended 65% toward app_bg for background, app_fg blended 55% toward app_bg for text).

---

[2026-05-16] — feat(gui): move theme swatches to left side and split into 2-column grid

Changed

gui/theme_tab.py: Restructured `_build_ui` so the swatch panel sits immediately right of the preset list (no right-side expansion). The `QGridLayout` now uses 4 columns (label-A | swatch-A | label-B | swatch-B), distributing the 22 color entries across 11 rows × 2 columns. Added `layout.addStretch()` at the end so the panels stay left-anchored.

---

[2026-05-16] — fix(gui): search tab column widths no longer reset to 100px on every launch

Fixed

gui/search_tab.py: Added `_widths_applied` flag to guard the pre-reset snapshot in `_render_page()`. The snapshot was executing before `_apply_col_widths()` had ever run, so Qt's 100px default widths overwrote the values loaded from QSettings, destroying saved preferences. The snapshot is now skipped until widths have been applied at least once.

---

[2026-05-16] — fix(scraper): use correct SMF form field name "description" instead of "desc"

Fixed

backend/forum_poster.py: Changed "desc": lb_id to "description": lb_id in both the initial POST payload and the retry payload. The SMF modify/post form uses name="description" (confirmed from live page source); the previous key "desc" was silently ignored by the server, so the LB number never appeared in the topic description field. Updated debug log line to match.

---

[2026-05-16] — feat(gui): add 7 new preset themes (Nord, Gruvbox, Monokai, Tokyo Night, Solarized, Everforest, Catppuccin)

Added

gui/theme_tab.py: Nord (Arctic blue-gray), Gruvbox (earthy retro dark), Monokai (vivid dark with cyan accents), Tokyo Night (neon city dark), Solarized (precision warm light), Everforest (forest dark-green), Catppuccin Mocha (soft pastel dark). All 14 row-color keys verified for luminance contrast against each theme's table background. Preset list now shows 14 named themes plus Custom.

Changed

PROJECT.md: Updated Theme Tab description from "Six preset themes" to fourteen.

---

[2026-05-15] — fix(gui): search-tab "missing" row hardcoded yellow; dark-theme row luma audit

Fixed

gui/search_tab.py: Hardcoded QColor("#FFFF99") for status=="missing" rows didn't respect the active theme. Added module-level `import gui.styles as styles`; replaced hardcoded color with `styles.ROW_MISSING` and replaced lazy per-call `from gui.styles import ROW_OWNED` with `styles.ROW_OWNED`. "Row: Missing" in the theme editor now controls search-tab missing-entry rows.
gui/theme_tab.py: Audited all dark-theme row colors for luminance contrast against their table backgrounds. Fixed Dark (row_missing/row_xref/row_owned/row_wishlist all had luma at or below table_bg=58), Black (row_xref luma=20 identical to table_bg; row_missing/row_wishlist below table_alt=28), and Dracula (row_xref/row_missing/row_wishlist at or below table_bg=43). Also fixed Red theme row_xref. Removed unused QApplication import.

---

[2026-05-15] — feat(lbdir): Remove Extra Files — delete disk files not listed in the lbdir, with confirmation dialog

Added

backend/checksum_utils.py: Added find_extra_files(folder_path, lbdir_path) — parses lbdir MD5 section, scans folder recursively, returns files not in the expected set (lbdir file itself excluded).
backend/app.py: Added POST /api/lbdir/find_extra (list extra files per folder) and POST /api/lbdir/delete_extra (unlink selected files by relative path, then prune empty subdirectories).
gui/lbdir_tab.py: Added _LbdirFindExtraWorker and _LbdirDeleteExtraWorker workers. Added ExtraFilesDialog — checkable file list with red delete button and warning label; never deletes without explicit user confirmation. Added "Remove Extra Files" button; handlers re-run Check lbdir Files after deletion.

---

[2026-05-15] — fix(gui): dark-theme row colors always showed light-theme green/purple; add Red theme

Fixed

gui/collection_tab.py: `from gui.styles import ROW_OWNED, ROW_WISHLIST` captured the values at import time; reassignment inside apply_theme() never propagated. Replaced with `import gui.styles as styles` and updated both usages to `styles.ROW_OWNED` / `styles.ROW_WISHLIST`.
gui/lookup_tab.py: Same stale-import bug for ROW_MATCHED/ROW_NOT_FOUND/ROW_MISSING/ROW_DUPLICATE/ROW_XREF. Replaced top-level `from gui.styles import …` with `import gui.styles as styles`; updated all 10 bare references to `styles.ROW_*`; removed redundant lazy `from gui import styles` inside refresh_colors().
gui/styles.py: apply_theme() now updates ROW_WISHLIST global (was never updated on theme switch). Added row_wishlist to the default apply_theme call at module load.
gui/theme_tab.py: Added row_owned and row_wishlist to every theme with dark-appropriate colors for Dark/Black/Dracula. Added both to COLOR_LABELS so they appear in the theme editor.

Added

gui/theme_tab.py: New "Red" dark theme — crimson/dark-red palette with dark-appropriate row colors.

---

[2026-05-15] — fix(gui): suppress GBM "Unknown format" stderr noise from Chromium GPU process

Fixed

main.py: Added --disable-features=VaapiVideoDecoder to QTWEBENGINE_CHROMIUM_FLAGS so Chromium's GPU process no longer probes unsupported hardware video-decode pixel formats (P010/HDR) via GBM, eliminating repeated "Unknown or not supported format: 808530000" stderr errors on Linux.

---

[2026-05-15] — feat(lbdir): Reconcile Files — match missing lbdir entries to disk files by MD5 and propose renames

Added

backend/checksum_utils.py: Added find_reconcilable_files(folder_path, lbdir_path) — parses lbdir MD5 section, identifies entries not on disk, scans all disk files recursively for MD5 matches, returns proposals/unmatched_lbdir/unmatched_disk/warnings.
backend/app.py: Extracted _find_lbdir_in_folder() module-level helper (DRY refactor of lbdir_check and lbdir_retrieve inline lbdir detection). Added POST /api/lbdir/reconcile (preview, read-only) and POST /api/lbdir/apply_reconcile (shutil.move renames, creates subdirs, never deletes).
gui/lbdir_tab.py: Added _LbdirReconcileWorker and _LbdirApplyReconcileWorker QThread workers. Added ReconcilePreviewDialog (checkable table of From→To proposals, Select All/Deselect All, Apply Selected/Cancel). Added "Reconcile Files" button; _on_reconcile, _on_reconcile_done, _apply_reconcile, _on_apply_reconcile_done handlers; re-runs Check lbdir Files after apply.

---

[2026-05-15] — fix(backend): _parse_date swapped month/day — forum post subjects used YYYY-DD-MM instead of YYYY-MM-DD

Fixed

backend/torrent_maker.py: _parse_date was treating parts[0] as day and parts[1] as month (D/M/YY, European), but LosslessBob stores dates in M/D/YY (US) format. Swapped variable assignment so month=parts[0], day=parts[1]. Updated docstring. All subject lines generated from _parse_date (forum posts and torrent names) now produce correctly ordered ISO dates.

---

[2026-05-15] — feat(gui): "Best match only" checkbox in Lookup summary — hides secondary DUPLICATE/INCOMPLETE rows when a full MATCHED result exists

Added

gui/lookup_tab.py: Added "Best match only" QCheckBox (default checked) to the Summary header row. When enabled and at least one summary row is MATCHED, _apply_filters() suppresses all non-MATCHED summary rows and their corresponding detail rows. Unchecking restores the full view. Toggle is instant with no re-lookup required.

---

[2026-05-15] — fix(main): force XWayland (xcb) on Linux to prevent fatal Wayland EGL crash

Fixed

main.py: Set QT_QPA_PLATFORM=xcb before QApplication construction on Linux when not already overridden. Native Wayland + AA_ShareOpenGLContexts + QtWebEngine can produce an unrecoverable EGL_BAD_NATIVE_WINDOW (0x300d) error that kills the Wayland connection (BUG-053). XWayland is stable for this workload with no functional loss.

---

[2026-05-15] — fix(gui): suppress Chromium stderr noise and fix WebEngine profile teardown-order warning on exit

Fixed

main.py: Set QTWEBENGINE_CHROMIUM_FLAGS=--disable-logging before QApplication is created to silence Chromium sandbox and path-override diagnostics that bypass Python logging.
gui/attachments_tab.py: Removed Qt parent from QWebEngineProfile so its lifetime is not tied to the tab's child list. Connected QApplication.aboutToQuit to new _cleanup_webengine() which uses sip.delete() to force destruction order view → page → profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning (BUG-026 reopened and re-fixed).

---

[2026-05-15] — fix(backend): summary row for superseded duplicate LB shows DUPLICATE (yellow) not INCOMPLETE (pink)

Fixed

backend/db.py: After building the per-LB summary, any LB where every matched detail item is still a duplicate (none promoted by resolution) now gets status "DUPLICATE" instead of "INCOMPLETE". This prevents a secondary LB that shares some checksums with the winning LB from appearing as if the user is missing files — it is correctly shown as a yellow duplicate entry alongside the green MATCHED winner.

---

[2026-05-15] — fix(backend): xref lookup completeness — evaluate per (lb, xref) group so full xref match shows MATCHED not INCOMPLETE

Fixed

backend/db.py: lookup_checksums reverse lookup now tracks matched checksums per (lb_number, xref_value) group and queries completeness against that specific xref group (`WHERE lb_number=? AND xref=?`) instead of the whole primary set (`AND xref=0`). A recording that provides all checksums for xref variant N is now correctly shown as MATCHED (green). The summary missing_from_set count is aggregated across all xref groups that had matched items.

---

[2026-05-15] — feat(backend): populate SMF Description field with LB number when posting to forum

Added

backend/forum_poster.py: `lb_id` is now computed unconditionally before the subject branch; `"desc": lb_id` added to both the initial payload and the retry payload so the SMF topic Description (Optional) field is populated with e.g. "LB-10002".

---

[2026-05-15] — fix(backend): lbdir xref file detection — match 'lbdir' anywhere in filename, not just at start

Fixed

backend/app.py: lbdir_check and lbdir_retrieve._find_lbdir now use `'lbdir' in f.name.lower()` instead of `startswith('lbdir')` so xref lbdir files named LBF-XXXXX-xref-NNNN-lbdir.txt are correctly found in both local folders and the attachment cache.

---

[2026-05-15] — feat(backend/gui): torrent history context menu — Remove from qBittorrent + Delete .torrent file from disk

Added

backend/qbittorrent.py: remove_torrent() — calls POST /api/v2/torrents/delete with deleteFiles=false so only the qBt entry is removed; audio files on disk are untouched.
backend/app.py: POST /api/torrent/<id>/qbt_remove — removes from qBt via infohash, clears added_to_qbt in DB on success. DELETE /api/torrent/<id>/file — deletes the .torrent file from disk, clears torrent_path in DB.
gui/collection_tab.py: Added separator + two new context menu actions to torrent history: "Remove from qBittorrent" (disabled when no infohash stored) and "Delete .torrent File from Disk" (disabled when file doesn't exist). Both show a confirmation dialog, refresh the history panel on completion, and update the status label.

---

[2026-05-15] — feat(backend/gui): log forum posts to DB; consolidated History panel with Torrents + Forum Posts tabs; LB detail hyperlink in post header

Added

backend/db.py: forum_posts table (lb_number, subject, topic_url, board_id, posted_at). Added add_forum_post(), get_forum_posts_for_lb(), delete_forum_post() functions.
backend/app.py: post_forum route now calls database.add_forum_post() on success. Added GET /api/entry/<lb>/forum_posts and DELETE /api/forum_post/<id> routes.
backend/forum_poster.py: LB-XXXXX tag in post header is now a [url=...] hyperlink to the LB detail page on losslessbob.wonderingwhattochoose.com.
gui/collection_tab.py: Replaced separate Torrent History and Forum Post History group boxes with a single "History" QGroupBox containing a QTabWidget (Torrents tab + Forum Posts tab). Forum Posts tab shows posted date, subject, URL with Open in Browser and Remove Record buttons. After a successful post the tab switches to Forum Posts automatically. Removed unused QSplitter import.

---

[2026-05-15] — feat(gui): My Collection context menu now has "Generate Spectrograms" action that sends selected folders to the Spectrograms tab

Added

gui/collection_tab.py: Added `send_to_spectrograms = pyqtSignal(list)` signal; added "Generate Spectrograms" action to `_on_coll_context` — visible only when one or more selected rows have a valid `disk_path` directory. Emits the list of paths.

gui/main_window.py: Connected `collection_tab.send_to_spectrograms` to `_on_send_to_spectrograms` which calls `spectrogram_tab._add_folders(folders)` then switches to the Spectrograms tab.

---

[2026-05-15] — fix(backend): forum poster comprehensive reliability overhaul — correct POST URL, hidden-element guards, Firefox UA, board-redirect success on both paths

Changed

backend/forum_poster.py: (1) Removed _post_url() — was hardcoding action=post;sa=post2 which is the wrong SMF handler; the form's own action= attribute is now the authoritative POST URL. _scrape_form_fields() now returns (fields, form_action, diag) and _find_post_form() extracts the action URL directly. (2) post_lb_topic() now posts with allow_redirects=False so the raw Location header can be inspected before following any redirect. (3) Board-redirect success detection: SMF on this forum signals a successful new topic with a 302 → board=N.0 redirect (not topic=), so both the initial post and the retry path now detect this, follow the board URL sorted by first_post desc, and call _find_newest_topic() to return the correct topic link. (4) Lock-warning check now calls _is_element_hidden() before treating #lock_warning as a real warning — the element is present (display:none) on every compose page and was incorrectly firing the retry path on every failed post. (5) _extract_smf_error() now skips hidden elements for the same reason — the empty errorbox present on every compose page was generating phantom SMF error strings. (6) Removed not_approved from payload — not a real SMF field. (7) User-Agent updated to a current Firefox/126.0 string to avoid UA-based blocking.

---

[2026-05-15] — fix(gui): torrent history section no longer expands to fill space; collection table now stretches correctly

Changed

gui/collection_tab.py: Added stretch=1 to the coll_view addWidget call so the collection table claims all available vertical space, keeping the Torrent History group compact at the bottom.

---

[2026-05-15] — feat(gui): Post to Forum auto-creates torrent and adds to qBittorrent if none exists

Changed

gui/collection_tab.py: _on_post_forum now checks for an existing torrent file before building the preview. If none is found it calls /api/torrent/create (using the collection row's disk_path as source_folder), then /api/qbt/add to seed it, then proceeds with the normal preview → confirm → post workflow. If creation fails the error is surfaced in the status bar. qBittorrent add failures are non-fatal — the post proceeds regardless.

---

[2026-05-15] — fix(backend/gui): wrong topic URL in success popup; torrent history stale after auto-create

Fixed

backend/forum_poster.py: _find_newest_topic now uses a three-pass strategy: (1) subject-text match — finds the link whose visible text contains the posted subject, immune to sticky ordering; (2) first non-sticky link — skips <tr>/<div>/<li> ancestors whose class includes "sticky"; (3) last resort, first topic= link found. Subject is now threaded through from post_lb_topic into both the initial-post and retry board-redirect paths.
gui/collection_tab.py: Added _history_gen counter to _load_torrent_history/_populate_torrent_history so stale API responses (earlier load completing after a newer one) are discarded instead of overwriting fresh data. _on_preview_forum_ready now triggers a history refresh so a torrent auto-created during forum-post pre-flight appears immediately without requiring a re-selection.

---

[2026-05-15] — fix(backend): post-success topic URL wrong — board page returns busiest thread, not newest

Fixed

backend/forum_poster.py: _find_newest_topic was picking the first topic= link on the board listing page, which is sorted by last-reply date by default. A busy thread bumped after our post appeared first, returning the wrong URL. Added _board_url_sorted() which appends sort=first_post;desc=1 to the board redirect URL before fetching it, ensuring our newly created topic is always at the top. Applied to both the first POST and retry code paths.

---

[2026-05-15] — fix(backend): forum post line breaks stripped; redesign header with size/hr/red LB number, remove broken spoiler tag, normalise CRLF

Changed

backend/forum_poster.py: (1) Normalise body to \r\n before placing it in the multipart/form-data payload — bare \n is silently stripped by SMF when the request is multipart-encoded due to a file attachment. Applied to both first POST and retry payload. (2) Metadata header now wrapped in [size=13pt] for visibility, LB number appended in [color=red][b]...[/b][/color], followed by [hr] on the next line. (3) Replaced non-working [spoiler=Checksums] with plain [b]Checksums[/b] + [code] block. (4) Footer separated by [hr] above it.

---

[2026-05-15] — feat(backend): redesign forum post body format with structured header, LB txt content, spoilered lbdir checksums, and footer attribution

Changed

backend/forum_poster.py: Replaced the raw-file-dump approach in _build_body with a structured BBcode format. New format: (1) bold labeled metadata header (Date | Location | CDR | Rating | Timing) from entry dict; (2) content from the LB-numbered txt file in the attachment dir (first header line skipped), falling back to entry.description; (3) lbdir checksum manifest in a [spoiler=Checksums][code] block at the end; (4) italicised grey "Brought to you by kuddukan, via the Bob-O-Matic v1.0." footer. Added _read_lb_txt and _read_lbdir helper functions. Updated preview_lb_topic and post_lb_topic to pass lb_number into _build_body.

---

[2026-05-14] — fix(backend): retry payload overrode lock=0, re-introducing the warning it was meant to clear

Fixed

backend/forum_poster.py: The warning page returned by SMF includes lock=1 (server-corrected to match the board's requirement). The retry payload was explicitly overriding lock=0, reintroducing the mismatch that caused the warning on the first POST and making the retry fail identically. Removed lock/sticky/move overrides from the retry payload so the warning page's corrected values pass through. Also removed them from the first POST payload where they were pointless.

---

[2026-05-14] — fix(backend): SMF board lock warning requires confirmation resubmit — add automatic retry

Fixed

backend/forum_poster.py: Board 16 is configured for admin/mod-only posting, so SMF always returns a "warning preview" page asking for confirmation instead of creating the topic immediately. The attachment is already temp-stored server-side at this point. Added lock-warning detection: re-scrapes fresh hidden fields (new seqnum/CSRF) from the warning page and resubmits without the file on a second POST.

---

[2026-05-14] — fix(backend): admin compose page sets lock=1, causing SMF to bounce post with a lock warning

Fixed

backend/forum_poster.py: Admin users' compose pages have lock=1 pre-set as a hidden field. SMF treats this as a locked-topic flag and returns the form with a warning instead of creating the topic. Override lock, sticky, and move to 0 in the payload so admin-default hidden values don't affect the new topic.

---

[2026-05-14] — fix(backend): board ID missing from POST URL — SMF rejected every post as "board doesn't exist"

Fixed

backend/forum_poster.py: _POST_URL was a static constant without a board parameter. SMF requires the board in the POST URL (action=post;sa=post2;board=N.0) just as it does in the compose URL. Replaced _POST_URL with _post_url(board_id) that mirrors _compose_url(board_id).

---

[2026-05-14] — fix(backend/gui): hardcoded forum board ID replaced with configurable setting

Changed

backend/forum_poster.py: Removed FORUM_BOARD=16 constant and module-level _COMPOSE_URL. post_lb_topic() now accepts board_id: int and builds the compose URL dynamically. _scrape_form_fields() accepts compose_url as a parameter.
backend/app.py: wtrf_board_id added to /api/db/settings GET key list. post_forum route reads board_id from meta and returns a clear error if unset.
gui/setup_tab.py: Board ID QSpinBox added to WTRF section (row 2). Saved via _on_wtrf_board_changed on change; loaded in _load_wtrf_settings from /api/db/settings.

---

[2026-05-14] — feat(main): write app module logs to data/losslessbob.log (rotating, 5 MB × 3)

Added

main.py: _configure_logging() installs a RotatingFileHandler on data/losslessbob.log. Root logger stays at WARNING (keeps urllib3/requests/werkzeug quiet); backend.* and gui.* namespaces are set to DEBUG so all our module logging lands in the file.

Added

main.py: _configure_logging() sets up a RotatingFileHandler on data/losslessbob.log (DEBUG level, 5 MB × 3 backups) and a stderr StreamHandler (WARNING+). Called at startup before Flask thread starts so all backend modules log to file from the first request.

---

[2026-05-14] — fix(backend): forum post reports false success — SMF rejects submission silently

Fixed

backend/forum_poster.py: post_lb_topic() was reporting success on any HTTP 200 response, but SMF returns 200 when it bounces the post back to the compose form (e.g. CSRF failure, attachment rejection). Fixed success detection to require 'topic=' in the final URL (the redirect SMF sends only on a real post). Added Referer and Origin headers to the POST request so SMF's CSRF check passes. Added additional_options=1 to the payload so SMF processes the attachment field. Improved error reporting: collects errorbox/error_list/post_error div text, and returns the page title + URL as fallback so the failure reason is always visible.

---

[2026-05-14] — fix(backend): forum post blocked by hardcoded 'sc' field check — WTRF uses hashed CSRF token name

Fixed

backend/forum_poster.py: WTRF's SMF install uses a dynamically-hashed field name for the CSRF token (e.g. 'a9c55b28') instead of the literal 'sc'. Removed the 'sc' presence check; seqnum alone is used to confirm the post form was found. All hidden fields including the hashed token were already forwarded via **hidden, so the post itself was correct. Also added diagnostic output to the error message and improved form-field scraping to target the post form specifically.

---

[2026-05-14] — fix(backend): forum post fails with "sc/seqnum missing" — compose page redirect not detected

Fixed

backend/forum_poster.py: _scrape_form_fields now detects when SMF silently redirects the compose URL to the login page (unauthenticated session) and returns empty instead of scraping login-form fields. Added targeted post-form lookup by action attribute so unrelated hidden inputs on the page don't pollute the result. Added Referer header to the compose-page request. Validation now reports exactly which fields are absent (sc vs seqnum).

---

[2026-05-14] — fix(gui): torrent history panel now refreshes after torrent creation

Fixed

gui/collection_tab.py: _on_torrent_done() never called _load_torrent_history(), so the history panel stayed empty after creating a torrent until the user re-selected the entry. Now reloads history for the currently-displayed LB after a successful create.

---

[2026-05-14] — fix(scraper): fetch tracker list from raw GitHub instead of jsDelivr CDN

Fixed

backend/torrent_maker.py: jsDelivr caches GitHub content and can lag by hours/days. Switched _TRACKER_CDN to raw.githubusercontent.com so the tracker list is always current. Also removed unused json import.

---

[2026-05-14] — fix(backend): handle qBittorrent 5 JSON response for torrents/add

Fixed

backend/qbittorrent.py: qBittorrent 5+ returns a JSON object from /api/v2/torrents/add instead of plain "Ok.". Added a JSON fallback check (failure_count==0 and success_count>0) so successful adds are no longer reported as failures.

---

[2026-05-14] — feat: qBittorrent API key authentication (qBittorrent 5+)

Added

backend/credentials.py: SERVICE_QBT_KEY constant for keyring storage of the API key.
backend/qbittorrent.py: api_key parameter on test_connection(), add_torrent_for_seeding(), and add_torrent_from_db(). When set, a Bearer token header is used and the login/logout flow is skipped entirely. Refactored shared session setup into _make_session() and login logic into _login().
backend/app.py: /api/qbt/test and /api/qbt/add routes now retrieve and forward the stored API key; api_key takes priority over username/password.
gui/setup_tab.py: API Key field added to the qBittorrent section (row 2, password-masked, spanning full width). Save/Clear/Test/Load handlers all updated to prefer the API key when filled.

---

[2026-05-14] — fix(backend): add Origin+Referer headers to qBittorrent login, improve error detail

Fixed

backend/qbittorrent.py: Added both Referer and Origin headers to test_connection() and add_torrent_for_seeding(). Fixed login check to accept HTTP 204 No Content (qBittorrent's response when "Bypass authentication for clients on localhost" is enabled) alongside the normal 200 "Ok." response. Error message now includes HTTP status code and shows "<empty>" for blank bodies.

---

[2026-05-14] — feat(gui/backend): Forum post preview dialog before submitting to WTRF

Added

backend/forum_poster.py: preview_lb_topic() builds subject + body without logging in or posting.
backend/app.py: GET /api/entry/<lb>/preview_forum returns {subject, body} for the GUI to display.
gui/collection_tab.py: "Post to Forum" now opens a preview dialog showing the subject and editable BBcode body; the post only fires after the user clicks "Post to Forum" in the dialog. Subject and body edits in the dialog are forwarded to the backend.
backend/forum_poster.py: post_lb_topic() accepts subject_override and body_override kwargs so user edits from the preview are used verbatim.

---

[2026-05-14] — fix(backend): WTRF forum login failures due to wrong domain and bad URL check

Fixed

backend/forum_poster.py: FORUM_BASE corrected from watchingtheriverflow.com to watchingtheriverflow.org.
backend/forum_poster.py: Login success check was matching "action=login" as a substring of "action=login2" (the POST endpoint), causing every login to be flagged as failed. Fixed to only treat a redirect back to the GET login page as failure. This forum returns 200 with empty body at login2 on success.
backend/forum_poster.py: _get_session now collects all hidden fields from the login form (not just hash_passwrd) to include sc and any other CSRF fields.

---

[2026-05-14] — fix(gui): WTRF and qBittorrent password fields blank on restart

Fixed

gui/setup_tab.py: _load_wtrf_settings and _load_qbt_settings now populate both username and password from keyring (was discarding password with _).

---

[2026-05-14] — feat(gui/backend): WTRF forum "Test Connection" button on Setup tab

Added

gui/setup_tab.py: _WtrfTestThread QThread; "Test Connection" button in the WTRF Forum group; _on_wtrf_test / _on_wtrf_test_finished handlers; green/red status label feedback.
backend/app.py: POST /api/wtrf/test — calls forum_poster._get_session() to verify credentials without posting. Falls back to stored keyring creds if body fields are empty.

---

[2026-05-14] — refactor(gui): setup tab two-column layout to eliminate wasted right-side space

Changed

gui/setup_tab.py: Replaced single-column lower section with a two-column QHBoxLayout. Left column holds Web Scraper and Scraper Log groups (stretch=3); right column holds qBittorrent, WTRF Forum, and Torrent Settings groups (stretch=2). Scraper log switched from fixed height to minimumHeight so it expands to fill available space.

---

[2026-05-14] — fix(checksum): rename generated checksum files from _lbgen to _mychecksums (TODO-014)

Changed

backend/checksum_utils.py: Renamed _lbgen_path() to _mychecksums_path(). All generated checksum files are now named <folder>_mychecksums.ffp / _mychecksums.md5 (incrementing to _mychecksums_2, etc.) instead of _lbgen.*. TORRENT_EXCLUDE in torrent_maker.py already matched this pattern — no change needed there.

---

[2026-05-14] — feat(collection): torrent history panel and path relocation flow (TODO-012, TODO-013)

Changed

gui/collection_tab.py: Added torrent history sub-panel to My Collection tab. Selecting a single entry loads all torrents table records via GET /api/torrent/<lb>. Each row shows a green/red/orange indicator (source_folder_exists / torrent_file_exists), created_at, torrent filename, source folder, and qBt added status. Regenerate button enabled when torrent file is missing. Relocate Source button opens folder browser, cross-checks folder contents against checksums for the entry, updates source_folder via PATCH /api/torrent/<id>, writes a rename_log.txt relocation entry, and optionally renames the folder to the standard YYYY-MM-DD Location (LB-XXXXX) format (calling write_rename_log + shutil.move). Added _STANDARD_LB_NAME_RE module constant. Added _build_torrent_history_panel(), _on_coll_selection_changed(), _load_torrent_history(), _populate_torrent_history(), _get_selected_history_record(), _on_history_context(), _history_add_record(), _on_history_qbt_done(), _history_regen_record(), _on_history_regen_done(), _history_relocate_record(), _cross_check_folder(), _get_standard_lb_name() methods.

---

[2026-05-14] — feat(phase1): Torrent generation, qBittorrent seeding, WTRF forum posting, credentials keyring, rename log

Changed

backend/db.py: Added torrents and rename_history tables to SCHEMA_SQL. Added get_torrents_for_lb(), add_torrent_record(), update_torrent_record(), add_rename_history() helpers.

backend/paths.py: Added TORRENTS_DIR = data/torrents/; ensure_data_dirs() now creates it.

requirements.txt: Added torf==4.3.1 and keyring==25.7.0 (+ transitive deps).

backend/app.py: Added POST /api/torrent/create, GET /api/torrent/<lb>, PATCH /api/torrent/<id>, GET /api/trackers, POST /api/qbt/test, POST /api/qbt/add, POST /api/entry/<lb>/post_forum. Extended GET /api/db/settings to include qbt_host, qbt_port, qbt_category, qbt_tags, tracker_list keys.

gui/rename_tab.py: Calls write_rename_log() before each shutil.move so every folder rename is recorded in rename_log.txt and rename_history.

gui/setup_tab.py: Added qBittorrent section (host, port, username/password, category, tags, Save/Test/Clear), WTRF Forum section (username/password, Save/Clear), and Torrent Settings section (tracker list selector, Refresh Trackers button).

gui/collection_tab.py: Added Create Torrent, Add to qBittorrent, and Post to Forum buttons to the My Collection panel.

Added

backend/credentials.py: Keyring-backed credential storage. SERVICE_QBT / SERVICE_WTRF constants. keyring_available(), save_credentials(), get_credentials(), delete_credentials(), credentials_stored(), prompt_if_missing().

backend/rename.py: write_rename_log() helper — appends a timestamped line to rename_log.txt and inserts a rename_history DB row. Used by rename_tab and (future) collection_tab path relocation.

backend/torrent_maker.py: torf-based .torrent generation. TORRENT_EXCLUDE rules (rename_log.txt, _mychecksums.*, .torrent, Thumbs.db, .DS_Store). fetch_trackers() fetches ngosang/trackerslist via jsDelivr CDN and caches per session. make_torrent() and make_torrent_batch().

backend/qbittorrent.py: qBittorrent WebUI API v2 integration. test_connection(), add_torrent_for_seeding(), add_torrent_from_db(). Sets save_path to parent of source_folder so seeding starts immediately.

backend/forum_poster.py: SMF 2.x HTTP session login + post. post_lb_topic() scrapes sc/seqnum fields, builds body from cached .txt/.ffp attachments (falls back to entry table), attaches .torrent as multipart POST.

[2026-05-14] — feat(rename/xref): Multiple IDs cyan color + right-click resolve; xref-aware naming; xref filter on Search and Collection tabs

Changed

gui/rename_tab.py: Multiple IDs rows now use a distinct cyan color (#B2EBF2) instead of red. Right-click a Multiple IDs row to get a "Resolve — Apply…" submenu listing each candidate LB (with xref suffix when applicable). Choosing one resolves the row into a single-LB rename. Rename is blocked for unresolved multiple_ids rows. Updated legend to include the new color. populate_from_lookup now filters detail items to MATCHED/MATCHED (INCOMPLETE) status only, preventing resolved duplicate losers from triggering spurious "Multiple IDs" rows. xref-aware: lb_str and proposed names include "-xref{N:04d}" suffix when the match is via a cross-reference checksum. _lb_in_name, _has_wrong_lb, and _strip_lb_from_name all handle the xref suffix. _fmt_lb() helper added.

backend/db.py: Added get_xref_lb_numbers() — returns distinct lb_numbers that have any xref checksum (xref > 0).

backend/app.py: Added GET /api/checksums/xref_lb_numbers route.

gui/search_tab.py: Added "Xref only" checkbox filter — fetches xref lb_numbers on startup and filters search results to entries that have xref variants in the DB.

gui/collection_tab.py: Added "Xref only" checkbox filter to My Collection — same xref lb_number set, filters owned entries to those with xref variants.

[2026-05-13] — feat(lookup/verify): duplicate resolution, folder/summary filtering, verify NO CHECKSUMS, lookup→verify folder carry

Changed

backend/db.py: lookup_checksums() now resolves duplicate-checksum ambiguity — when the same checksum appears in multiple LB entries and one is fully MATCHED while others are INCOMPLETE, the fully-matched LB is preferred and its items are reclassified from DUPLICATE to MATCHED.

backend/checksum_utils.py: verify_folder() now returns status='no_checksums' (instead of 'pass') when audio files are present but no checksum files (.ffp/.md5/.st5) exist at all.

gui/lookup_tab.py: Added folder filter (click a listbox item to show only that folder's rows in summary and detail; click again to clear). Added summary LB filter (click a summary row to show only that LB's detail items; click again to clear). Filter state shown in section header labels. No-checksum folder detection now requires audio files to be present (folders with neither audio nor checksums are not flagged). No-checksum summary rows are now built inline in _on_lookup_done for both 'listbox' and 'scan-tree' sources. Added get_lookup_folders() method.

gui/verify_tab.py: NO CHECKSUMS status shown in yellow when a folder has audio but no checksum files. Added add_folders_from_lookup(folders) method to receive folders from the Lookup tab.

gui/main_window.py: On switching to the Verify tab, lookup folders are automatically carried over if the Verify folder list is empty.

[2026-05-13] — fix(checksum): SHN shntool hash now works when shorten is not installed (BUG-040)

Fixed

backend/checksum_utils.py: compute_shntool() silently returned None for .shn files on systems without the shorten decoder — shntool requires shorten to decode SHN, but shorten is not in standard Linux repos. Added _compute_shntool_via_ffmpeg() fallback: when shntool hash produces no output for a .shn file, ffmpeg decodes it to a temp WAV and shntool hashes the WAV instead (lossless, produces identical PCM data). Also updated generate_checksums() for SHN mode to write both file-MD5 hashes and shntool audio hashes into the generated .md5 file, matching the lbdir format.

[2026-05-13] — fix(rename): individual checkboxes on Rename tab now toggle on click

Fixed

gui/rename_tab.py: NoEditTriggers blocked Qt's delegate from routing mouse clicks to setData() for CheckStateRole changes, so clicking a checkbox had no effect. Connected view.clicked to a new _on_cell_clicked() handler that calls model.setData() directly, bypassing the edit-trigger restriction.

[2026-05-13] — fix(lbdir): compute shntool hash for WAV files; include in overall verdict (BUG-039)

Fixed

backend/checksum_utils.py: verify_folder_lbdir() only ran compute_shntool() when is_shn was True, leaving shn_actual=None for .wav files → FAIL display despite passing MD5. Extended compute condition to (is_shn or is_wav) and added shntool check to the else-branch so WAV audio integrity is verified and counted in the overall verdict.

[2026-05-13] — fix(lbdir): WAV-format recordings no longer show phantom .shn MISSING entries

Fixed

backend/checksum_utils.py: parse_lbdir_file() was unconditionally converting every .wav filename in the shntool and shntool_len sections to .shn and forcing has_shn=True. For WAV-format recordings (lbdir *.wavf.txt) the files on disk are .wav, so the conversion created nonexistent .shn keys reported as MISSING and set the mode to SHN incorrectly. Fix: conversion is now conditional on has_shn already being True (i.e. the md5 section already saw real .shn filenames).

[2026-05-13] — feat(rename): allow "LB already in name" rows to be moved to 0. Processed without renaming

Changed

gui/rename_tab.py: _on_rename() now processes two eligible states: "needs_rename" (Complete match) renames and moves; "has_lb" (LB already in name) moves under the existing folder name with no rename. The confirm dialog and status message distinguish between the two operations. All other statuses remain blocked.

[2026-05-13] — fix(rename): restrict rename+move to "Complete match" rows only

Changed

gui/rename_tab.py: _on_rename() now filters the selected rows to only those in "needs_rename" state (Complete match). Rows with any other status (No match, LB already in name, Wrong LB, Multiple IDs) are silently skipped — they are not renamed and not moved to "0. Processed". The confirm dialog count and message now reflect only the eligible rows. If no eligible rows exist among the selection, a descriptive status message is shown and the dialog is not raised.

[2026-05-13] — feat(lookup): show all input folders in summary, including those with no DB match

Added

gui/lookup_tab.py: After building LB summary rows, group NOT FOUND detail items by their source folder (using source_file set by the worker). Any folder whose checksums produced zero DB matches now gets its own NOT FOUND summary row showing the count of unmatched checksums. Folders that share items with a matched LB are excluded to avoid double-counting. Clipboard lookups with no source file fall back to a single "NOT FOUND" label row.

[2026-05-13] — fix(lbdir): normalize Windows backslash path separators in lbdir filenames on Linux

Fixed

backend/checksum_utils.py: parse_lbdir_file() extracted filenames verbatim from lbdir files, preserving Windows-style backslashes (e.g. artwork\back.JPG). On Linux, pathlib treats backslashes as literal characters rather than path separators, so fpath.exists() returned False for all files in subdirectories. Added .replace('\\', '/') on every fname extracted in the md5, ffp, shntool, and shntool_len parsing blocks so keys and paths are consistently normalized before use.

[2026-05-13] — fix(startup): defer AttachmentsTab tree load to first activation — removes 3s startup block

Fixed

gui/attachments_tab.py: _refresh_tree() (HTTP request + directory scan) was called in __init__, blocking main-thread tab construction for ~3s. Replaced with a _tree_loaded flag; tree now populates in showEvent on first activation, matching the existing lazy WebEngine pattern.

[2026-05-13] — feat(setup): add shntool status indicator alongside SoX and ffmpeg; split into three separate rows

Changed

backend/checksum_utils.py: Added check_shntool_version() — calls shntool -v, returns first line of output or empty string if unavailable.
backend/app.py: /api/spectrogram/check now imports check_shntool_version and returns shntool_available and shntool_version alongside existing sox/ffmpeg fields.
gui/setup_tab.py: SoX/ffmpeg/shntool indicators split into three separate labelled rows (SoX:, ffmpeg:, shntool:). _check_sox() updated to populate each label independently. "Re-check" button moved to the shntool row. ffmpeg shown in orange when missing (non-critical), shntool in red (required for SHN verification).

[2026-05-13] — fix(lookup): Scan Tree now populates listbox and uses path-based lookup (BUG-036)

Fixed

gui/lookup_tab.py: _on_scan_tree was reading file contents and passing them as raw text to _run_lookup (clipboard mode), so found files were never added to the listbox and source_file was never populated on detail items. Replaced with _ScanTreeWorker(QThread) that does the rglob off the main thread; _on_scan_tree_done adds found paths to _all_paths, refreshes the listbox, then starts a path-based _LookupWorker. Also fixed inverted _mychecksums filter logic (was keeping _mychecksums files and dropping others, should be the reverse).

[2026-05-13] — fix(collection): scan now recognises "LB XXXXX" (space separator) folder names; remove unused QSpinBox import

Changed

gui/collection_tab.py: _LB_RE updated from r'LB-0*(\d+)' to r'LB[- ]0*(\d+)' so folders named "LB 12345" are matched alongside "LB-12345". Removed unused QSpinBox import.

[2026-05-13] — fix(collection): Scan Directory / Scan Tree froze UI on large drives (BUG-034)

Fixed

gui/collection_tab.py: Moved filesystem walk (iterdir / rglob) and /api/collection/lb_numbers network call out of the main thread into a new _ScanWorker QThread. Both _on_scan_directory and _on_scan_tree now start the worker and show a "Scanning…" status; _on_scan_finished presents the preview dialog and calls _bulk_add when results arrive.

[2026-05-13] — chore(startup): add startup timing logger to data/startup.log

Added

backend/startup_log.py: New module — init(path) truncates the log and records start time; t(label) appends a wall-clock timestamp + elapsed seconds entry. Thread-safe via lock; no-ops silently if not yet initialized.

Changed

main.py: Calls startup_log.init() after ensure_data_dirs(); adds t() probes at flask-thread-start, QApplication creation, splash shown, flask-port-ready, main_window import, MainWindow created, and window.show().
backend/app.py: create_app() adds t() probes around init_db(), start_file_watcher(), and route registration.
gui/main_window.py: __init__ adds t() probes around each build phase; _build_tabs adds t() probes before and after each tab module import and each tab instantiation.

[2026-05-13] — refactor(setup): move Data Management into Database group; add column-width persistence to DB Editor

Changed

gui/setup_tab.py: Database QGroupBox restructured as a horizontal split — existing archive controls on the left, Data Management (purge buttons) on the right with a vertical divider. coll_stats_label added showing live counts for My Collection, Wishlist, Personal Ratings, Watchdog Events, and Scrape Diff Rows. _refresh_collection_stats() added; called from _refresh_stats() on startup and after each purge. Standalone purge_group at the bottom of the tab removed.
gui/dbedit_tab.py: Column width persistence added — widths stored per-table in settings.ini under DbEditTab/<table>/col_widths. Right-click on any column header shows "Set width…", "Fit to contents", and "Fit all columns" options. sectionResized auto-saves on drag. Saved widths restored on table switch; first load falls back to resizeColumnsToContents.

[2026-05-13] — fix(dbedit): rows failed to load due to sqlite3.Row.description AttributeError; added Load Records button

Fixed

backend/app.py: dbedit_rows route now captures cursor before fetchall() and reads column names from cur.description (cursor attribute) instead of rows[0].description (which does not exist on sqlite3.Row). Empty tables also handled correctly.

Added

gui/dbedit_tab.py: "Load Records" button in toolbar clears search and reloads the first page for the current table. Removed unused QFont import.

[2026-05-13] — fix(verify): redefine "incomplete" as missing files on disk, not missing checksum types

Changed

backend/checksum_utils.py: In both verify_folder and verify_folder_lbdir, status logic updated. "incomplete" now means one or more audio files referenced by checksums are absent from disk. "fail" now means hash mismatches only. A folder with only an .md5 file where all hashes match now correctly returns "pass" instead of "incomplete".

[2026-05-13] — feat: FEAT-13 + FEAT-14 — Granular Collection Data Management and DB Editor Tab

Added

backend/db.py: integrity_events table added to SCHEMA_SQL; purge_collection, purge_wishlist, purge_collection_meta, purge_integrity_events, purge_entry_changes, delete_collection_entries functions added.
backend/app.py: _DBEDIT_READONLY/AUDIT/WARN constants; POST /api/collection/purge, POST /api/collection/delete_bulk, GET /api/dbedit/tables, GET /api/dbedit/table/<name>/schema, GET /api/dbedit/table/<name>/rows, PATCH /api/dbedit/table/<name>/row, DELETE /api/dbedit/table/<name>/rows, GET /api/dbedit/table/<name>/export routes.
gui/dbedit_tab.py: New DB Editor tab — table browser, paginated row viewer, inline cell editing with dirty-state tracking, row deletion with confirmation, context menu, CSV export.
gui/collection_tab.py: "Select All" and "Select None" buttons added to My Collection panel; _on_remove() replaced with bulk-delete via POST /api/collection/delete_bulk.
gui/setup_tab.py: "Data Management" group added with per-scope purge buttons (collection, wishlist, personal_meta, integrity_events, entry_changes) and confirmation dialogs.
gui/main_window.py: DbEditTab registered as "DB Editor" tab (after Spectrograms); lazy table load on first activation via _on_tab_changed.

[2026-05-13] — feat(gui): Scan Tree button in My Collection tab — recursive LB-folder discovery

Added

gui/collection_tab.py: "Scan Tree…" button added to My Collection panel beside "Scan Directory". _on_scan_tree() uses rglob to find LB-numbered directories at any depth under a root. For LB numbers found at multiple depths the shallowest folder is kept. Reuses the existing _ScanPreviewDialog preview and _bulk_add workflow.

[2026-05-13] — feat(gui): FEAT-08 — Scan Tree batch lookup button in Lookup tab

Added

gui/lookup_tab.py: "Scan Tree…" button added to left panel below "Add Folders…". _on_scan_tree() recursively finds all .ffp/.md5/.st5/.sha1/.shn files under a user-selected root directory, concatenates their contents, and feeds them to _run_lookup() as a single combined lookup. Respects the _filter_mychecksums flag to skip _mychecksums files when the filter is active.

[2026-05-13] — fix(gui): spectrogram panning overshoot caused by stale label-local coordinates after scroll

Fixed

gui/spectrogram_tab.py: _ImageViewer.eventFilter — changed pan tracking from event.position() (label-local coords) to event.globalPosition() (screen coords). When the scrollbar value was updated on each MouseMove, the label shifted on screen, making the stored _pan_start invalid for the next delta calculation and causing overshoot-then-correction jitter. Global coordinates are unaffected by the widget's scroll position.

[2026-05-12] — feat(backend,gui): SoX spectrogram generation with two-pane viewer tab (SPEC-01 through SPEC-06)

Added

backend/sox_utils.py: New module — SoX/ffmpeg tool detection (cached per process), format classification (_SOX_NATIVE / _NEEDS_CONVERSION / AUDIO_EXTS_ALL), convert-to-temp-WAV pipeline for non-native formats (SHN, APE, WV, M4A, MP3, OGG), generate_spectrogram() public API, check_sox_version(), SoxNotFoundError / ConversionError / SpectrogenError exception hierarchy. Original audio files are never modified; temp WAVs are always deleted in a finally block.
backend/app.py: _spectro_state dict + _spectro_lock for thread-safe batch state; _do_spectro_batch() worker (module-level); five new routes: GET /api/spectrogram/check, POST /api/spectrogram/generate, GET /api/spectrogram/status, POST /api/spectrogram/stop, POST /api/spectrogram/list.
gui/spectrogram_tab.py: New tab — _DropFolderList (drag-drop folders), _ImageViewer (fit-width + Ctrl+scroll zoom + double-click reset), _Worker (QThread), SpectrogramTab (folder/track inventory, generate/stop/poll, right-click context menus, salmon highlight for missing PNGs).
gui/main_window.py: SpectrogramTab registered as tab index 7 (between Attachments and Setup); _on_tab_changed() handler connected to tabs.currentChanged — refreshes inventory on Spectrograms activation and triggers SoX check on first Setup activation.
gui/setup_tab.py: SoX status row added to Database group with Re-check button; _check_sox() calls GET /api/spectrogram/check and shows version + ffmpeg availability with green/red colour.

[2026-05-12] — fix(gui): search tab description column default width 1400→600; column widths now persist across view switches and sessions

Fixed

gui/search_tab.py: _DESC_DEFAULT_W reduced from 1400 to 600px. Added QSettings persistence (LosslessBob/SearchTab) so column widths survive tab switches and restarts. Connected sectionResized signal to update _col_widths immediately on user drag. Added _resizing_programmatically guard to prevent spurious saves during programmatic column sizing. Removed _col_widths = None reset in _on_results so user-set widths are preserved across new searches.

[2026-05-12] — feat(db,backend,gui): FEAT-03 per-entry personal metadata, FEAT-04 wishlist tab, FEAT-05 duplicate concert detector

Added

backend/db.py: New tables collection_meta and my_wishlist in SCHEMA_SQL. New functions get_collection_meta, set_collection_meta, increment_listen_count (FEAT-03); get_wishlist, add_to_wishlist, remove_from_wishlist, get_wishlist_lb_numbers (FEAT-04); get_collection_duplicates (FEAT-05).
backend/app.py: Routes GET/POST /api/collection/<lb>/meta and POST /api/collection/<lb>/listen (FEAT-03); GET/POST /api/wishlist and DELETE /api/wishlist/<lb> (FEAT-04); GET /api/collection/duplicates (FEAT-05).
gui/styles.py: Added ROW_WISHLIST color (#E8D5FF) for wishlist row backgrounds.
gui/collection_tab.py: Added _WishlistModel, _PersonalMetaDialog classes. Wishlist inner tab with context menu (remove, view web). Duplicates inner tab using QTreeWidget showing owned (green) and unowned (grey) LBs per show; lazy-loaded on first activation. "Edit Personal Info…" context menu item on My Collection rows opens rating/tags/listen dialog.
gui/lookup_tab.py: "Add to Wishlist" added to summary right-click context menu.
gui/search_tab.py: Row-level right-click context menu with "Add to Wishlist".

[2026-05-12] — refactor(scraper,gui): remove redundant "fill gaps" checkbox; gap-filling is now unconditional

Changed

backend/app.py: Removed fill_gaps parameter. Gap-filling (marking every sequential LB number not in checksums as MISSING) now always runs for both "Scrape All Missing" and explicit range scrapes. The effective upper bound is derived from the highest checksums lb_number when no end_lb is given.
gui/setup_tab.py: Removed fill_gaps_cb checkbox and all references. _on_scrape_range no longer sends fill_gaps in the payload.

[2026-05-12] — fix(scraper,db): BUG-032 — "Scrape All Missing" left gap LB numbers absent from database; BUG-031 — skip bypassed local page recovery

Fixed

backend/app.py: scrape_start now derives effective_end from the highest checksums lb_number when end_lb is absent ("Scrape All Missing" path). Every sequential gap between start_lb and effective_end is unconditionally passed through insert_missing_entry, ensuring no LB number is left out of the database. For explicit range scrapes the fill_gaps checkbox is still respected.
backend/db.py: insert_missing_entry changed from INSERT OR REPLACE to INSERT OR IGNORE — gap-filling can no longer overwrite a row that already has real scraped data.
backend/scraper.py: Moved local_page resolution before the skip block in scrape_entry(). The status=='missing' guard now permits scraping when use_local_pages=True and the local HTML file exists, so previously-404'd entries can be recovered from disk.

[2026-05-12] — fix(gui,backend): BUG-030 — auto-scrape fires after import post-DB-reset

Fixed

gui/setup_tab.py: _on_reset_finished now calls self._save_settings() after a successful reset so the user's current checkbox states are persisted back to the freshly-wiped meta table. Prevents auto_scrape reverting to NULL (which was treated as enabled).
backend/app.py: on_complete now uses explicit None-check (_val is None or _val != "0") to document the intended default-on behaviour and guard against future Python type surprises.

[2026-05-12] — feat(importer): real-time import progress status

Changed

backend/importer.py: Import is now async. Added _import_state dict (stage, rows_parsed, rows_total, rows_merged, new_lb_count, message, error), get_import_status(), and start_import_async(). run_import() updates state throughout, including per-chunk row counts during the merge step (10k-row batches). _import_flat_file reports row count every 10k lines.
backend/app.py: POST /api/db/import now fires start_import_async() and returns immediately; auto-scrape trigger moved into on_complete callback. Added GET /api/db/import/status endpoint.
gui/setup_tab.py: _ImportThread now uses a 15 s timeout (fire-and-forget start). Added _ImportStatusThread polling /api/db/import/status every 500 ms. Added import_progress QProgressBar to Database group: indeterminate during hash/parse/optimise stages, determinate (rows_merged / rows_total) during merge. Label updates live with stage messages.

[2026-05-12] — BUG-029: 2–4 s startup delay from eager QWebEngineView construction

Fixed

gui/attachments_tab.py: QWebEngineView (and its QWebEngineProfile/QWebEnginePage) are now created lazily on the first showEvent of the Attachments tab via QTimer.singleShot(0, _init_web_view), deferring the WebEngine GPU-process spawn until the user actually visits that tab. _preview_file updated to use setCurrentWidget instead of hardcoded setCurrentIndex so stack order no longer matters.

[2026-05-12] — BUG-028: ~7 s Flask startup delay from synchronous bloom filter build

Fixed

backend/db.py: rebuild_bloom() in init_db() was iterating every checksum row on the startup thread, blocking Flask for ~7 s on large databases. Moved to a daemon background thread via _rebuild_bloom_bg(). checksum_in_bloom() already returns True when _bloom is None so all lookups fall through to SQLite until the filter is ready.

[2026-05-12] — BUG-027: ~10 s Linux startup delay from missing AA_ShareOpenGLContexts

Fixed

main.py: Added QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts) before QApplication(sys.argv). QtWebEngine requires this flag at construction time; without it the GPU process falls back to a slow separate-context path on Linux.

[2026-05-12] — BUG-026: WebEnginePage/Profile teardown order warning on shutdown

Fixed

gui/attachments_tab.py: QWebEnginePage is now parented to QWebEngineProfile (not to the tab widget). Qt destroys a parent's children before the parent itself, so page is always destroyed before profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning.

[2026-05-12] — BUG-025: db_reset "FOREIGN KEY constraint failed" after DB-01 enabled FK enforcement

Fixed

backend/app.py: db_reset now prepends PRAGMA foreign_keys=OFF to the DROP script so my_collection's FK on entries doesn't block the drop, then explicitly re-enables with PRAGMA foreign_keys=ON before calling init_db().

[2026-05-12] — DB-01–DB-08: Database performance pass (WAL, thread-local pool, covering indexes, temp-table lookup, FTS5 search, PRAGMA optimize, bloom filter, scrape diff changelog)

Changed

backend/db.py: DB-01/02 — WAL + performance PRAGMAs (synchronous=NORMAL, cache_size=-65536, mmap_size=536MB, temp_store=MEMORY); persistent per-thread connection pool via threading.local() — eliminates repeated connect/close overhead.
backend/db.py: DB-03 — Added idx_chk_covering (covering index on checksums) and idx_lb_xref0 (partial index WHERE xref=0) to SCHEMA_SQL.
backend/db.py: DB-04 — lookup_checksums() now uses CREATE TEMP TABLE + JOIN instead of dynamic IN clause; fixes 999-param SQLite limit for large lookups.
backend/db.py: DB-05 — Added entries_fts FTS5 virtual table (content='entries') with insert/update/delete triggers; init_db() rebuilds index on first run; search_entries() now uses FTS MATCH with LIKE fallback on syntax error.
backend/db.py: DB-07 — ScalableBloomFilter loaded from checksums on startup; lookup_checksums() skips SQLite entirely for definite-miss checksums.
backend/db.py: DB-08 — Added entry_changes table + idx_changes_lb index to SCHEMA_SQL; record_entry_changes() records field-level diffs before each entry upsert.
backend/importer.py: DB-02 — Removed conn.close() from _import_flat_file(); DB-06 — added PRAGMA optimize after bulk import; DB-07 — rebuild_bloom() called after each successful import.
backend/scraper.py: DB-06 — PRAGMA optimize called at end of scrape_range(); DB-08 — record_entry_changes() called before INSERT OR REPLACE INTO entries.
backend/app.py: DB-08 — Added GET /api/entry/<lb>/changes endpoint; db_reset now drops entries_fts, its triggers, and entry_changes before recreating schema.
requirements.txt: Added pybloom-live==4.0.0.

[2026-05-12] — WIN-05/06/07/08/09/10/11/12/13/14/15/16: Full Windows compat pass

Added

backend/paths.py: to_long_path() prefixes \\?\ on Windows for MAX_PATH bypass. WEBENGINE_DIR constant. ensure_data_dirs() warns when data path exceeds 200 chars on Windows.
gui/platform_utils.py: _subprocess_flags() helper for CREATE_NO_WINDOW. url_to_local_path() strips spurious leading slash from Qt6 Windows QUrl.toLocalFile().
tools/build_windows.bat: Windows build script (runs pyinstaller losslessbob.spec, creates dist/LosslessBob/data/).

Changed

backend/checksum_utils.py: _no_window_kwargs() suppresses console windows for subprocess on Windows. _find_shntool()/_get_shntool_cmd() auto-detect shntool via WSL on Windows; compute_shntool uses WSL path conversion and _no_window_kwargs. compute_md5/compute_ffp wrap open() with to_long_path. All shutil.which('shntool') replaced with _get_shntool_cmd() is not None.
backend/db.py: get_connection wraps DB path with to_long_path before sqlite3.connect.
backend/scraper.py: lb_dir and local_page wrapped with to_long_path at construction.
backend/scheduler.py: _handle() filters Thumbs.db/desktop.ini; delayed() cleans _pending in finally block. start_file_watcher uses WindowsApiObserver on Windows (falls back to Observer).
gui/styles.py: _platform_font_stack() selects Segoe UI on Windows, -apple-system on macOS, Ubuntu/Cantarell on Linux.
gui/rename_tab.py: Rename block uses Path objects; splits PermissionError/FileExistsError/OSError into separate handlers with actionable messages; validates for Windows-illegal characters; appends Windows Explorer tip when permission errors occur. Removed unused import os.
gui/verify_tab.py: shntool_missing message shows WSL install instructions on Windows. dropEvent uses url_to_local_path (WIN-14).
gui/lookup_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/lbdir_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/main_window.py: QSettings migrated to INI format at data/settings.ini (WIN-11). All 9 tab imports moved inside _build_tabs() for lazy loading (WIN-16). _refresh_status moved to background thread; initial fire delayed to 3000ms (WIN-16).
gui/attachments_tab.py: QWebEngineView now uses named profile with storage redirected to data/webengine_cache (WIN-15). Removed stale __file__-relative ATTACHMENTS_DIR definition.
main.py: Splash screen shown during Flask startup wait; QApplication created before _wait_for_port; error dialog and main window both use the same QApplication instance (WIN-16).
requirements.txt: Promoted waitress from optional comment to required dependency (WIN-06).
losslessbob.spec: Added waitress.task and waitress.server to hiddenimports (WIN-12).

[2026-05-12] — WIN-03 + WIN-04: Cross-platform file/folder opener; SQLite lock timeout

Added

gui/platform_utils.py: New shared module with open_folder(), open_file(), open_url(). Centralises all sys.platform branching for launching files and folders; uses os.startfile on Windows, open on macOS, xdg-open on Linux.

Changed

gui/collection_tab.py: _open_folders now delegates to open_folder() from platform_utils. Removed top-level import subprocess.
gui/attachments_tab.py: _open_externally now delegates to open_file() from platform_utils. Removed top-level import subprocess and import sys.
gui/setup_tab.py: _on_open_folder and _on_open_log now delegate to open_folder()/open_file() from platform_utils. Removed top-level import os, import subprocess, and import sys.
backend/db.py: get_connection() now passes timeout=30 and check_same_thread=False to sqlite3.connect(). Adds PRAGMA busy_timeout=30000 on every new connection so SQLite retries for up to 30 seconds before raising OperationalError on Windows lock contention.

[2026-05-10] — WIN-01 + WIN-02: Unified path resolution for frozen builds; Flask readiness poll replacing time.sleep

Added

backend/paths.py: New central path resolver. _app_root() returns Path(sys.executable).parent in PyInstaller frozen builds (sys.frozen=True) and Path(__file__).parent.parent otherwise. Exports APP_ROOT, DATA_DIR, DB_PATH, ATTACHMENTS_DIR, PAGES_DIR, LOG_FILE, TOOLS_DIR, and ensure_data_dirs().

Changed

backend/db.py: Replaced inline DB_PATH definition with import from backend.paths (re-exported so existing callers are unaffected).
backend/app.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR definitions with import from backend.paths.
backend/scraper.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR/PAGES_DIR definitions with import from backend.paths. Removed now-unused pathlib import.
backend/scheduler.py: Replaced inline DATA_DIR definition with import from backend.paths.
backend/importer.py: Replaced inline DATA_DIR definition with import from backend.paths.
gui/setup_tab.py: Replaced __file__-relative _LOG_FILE and data_dir with LOG_FILE and DATA_DIR from backend.paths.
main.py: Replaced time.sleep(0.5) with _wait_for_port() TCP poll (100ms interval, 15s timeout). On Windows uses Waitress as WSGI server for stable port binding. Deferred gui.main_window import to inside main() to avoid PyInstaller/DPI issues. Added fatal error dialog if Flask does not start within timeout. Added ensure_data_dirs() call at Flask startup.

[2026-05-10] — WIN-17: Fix drag-and-drop crash caused by OLE COM reentrancy on Windows

Fixed

gui/lookup_tab.py: Moved event.acceptProposedAction() before signal emission in DropListWidget.dropEvent so OLE marks the transaction complete before any widget modification. Removed self._refresh_listbox() from _add_path() — callers now own the refresh call. Updated _on_files_dropped to defer _refresh_listbox() via QTimer.singleShot(0, ...) so listbox.clear() never runs while the COM Drop() call is on the stack. Added explicit self._refresh_listbox() to _on_add_folders to restore the refresh it previously relied on from _add_path().

gui/verify_tab.py: Same acceptProposedAction-first fix in DropFolderListWidget.dropEvent. Changed _on_folders_dropped to use QTimer.singleShot(0, self._refresh_listbox) instead of a synchronous call.

gui/lbdir_tab.py: Identical fix to verify_tab.py.

[2026-05-08] — Fix Search tab column sizing: description default width, width retention on paging, right-click header width entry

Fixed

gui/search_tab.py: Description column now defaults to 1400 px instead of expanding to fit content; other columns still use `resizeColumnsToContents()` on first load. Column widths are now snapshotted from the header immediately before each `set_rows()` call so any user drag-resize is preserved when paging (Qt resets QHeaderView sections on model reset). Right-click on any column header opens a "Set column width…" dialog (QInputDialog) to enter an exact pixel value; the stored widths are updated so paging continues to respect the change.

[2026-05-08] — Fix column widths jumping on page navigation; add Word wrap toggle to Search and Collection tabs

Fixed

gui/search_tab.py: Column widths are now computed once via `resizeColumnsToContents()` on the first page with data and stored as absolute pixel values. Subsequent page renders restore those stored widths instead of re-calling `resizeColumnsToContents()`, so columns stay stable while paging.

gui/collection_tab.py: Same fix applied to My Collection (`coll_view`) and Missing (`miss_view`). Widths are reset and recomputed on each fresh data load.

Added

gui/search_tab.py: "Word wrap" checkbox in the search bar row. When checked, enables word wrap on the results table and auto-sizes rows; when unchecked, restores fixed single-line rows. Description text is no longer truncated at 120 chars.

gui/collection_tab.py: "Word wrap" checkbox added to My Collection button row and Missing button row, with the same on/off behaviour. Description text truncation removed from `_MissingModel`.

---

[2026-05-08] — Fix Results per page resetting to 50 on every startup

Fixed

gui/setup_tab.py: Added `_loading` flag set to True during `_load_settings` and False in a finally block. `_save_settings` returns early while the flag is set. Previously, each `setChecked`/`setValue` call during loading fired connected signals (`stateChanged`, `valueChanged`) that triggered `_save_settings` before `search_page_spin` had been populated from the DB, overwriting the stored value with the widget default of 50.

---

[2026-05-07] — Uniform fixed width on all four scraper action buttons

Changed

gui/setup_tab.py: Set all four scraper buttons (Scrape All Missing Entries, Stop Scraper, Scrape, Scrape Range) to a shared fixed width of 180px via a local constant `_SCRAPE_BTN_W`.

---

[2026-05-07] — Search filters, collection pagination/year filter, scraper grid and label fixes

Added

gui/search_tab.py: Three client-side filter checkboxes on the search bar — "Missing only" (status == 'missing'), "Owned only" (LB in My Collection), "Not owned" (LB not in My Collection). All three are AND-combined. Combining "Owned only" + "Not owned" yields an empty result. The owned filter re-renders automatically when `_OwnedWorker` finishes loading after a search.

gui/collection_tab.py: My Collection panel now auto-loads on startup (blank-screen fix). Added client-side pagination (Prev/Next, page label) driven by the shared Results per page setting. Added year dropdown filter populated from date_str of loaded entries. Text + year filters combined with AND; both reset to page 0 on change.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `collection_tab.set_page_size` so the Results per page spinner also controls My Collection pagination.

Fixed

gui/search_tab.py: Double-click URL now formats LB number as 5-digit zero-padded (`LB-{lb:05d}.html`). Previously used bare integer, producing 404 for any LB below 10000.

gui/setup_tab.py: "Mark sequential gaps as MISSING" checkbox renamed to "Skip LB numbers with no checksum data" per user request. Grid restructured so Scrape All Missing Entries, Scrape (single), and Scrape Range buttons all occupy column 2 of the grid, making them the same width. Stop Scraper moved to column 3. Status label and fill-gaps checkbox now span columns 3–4.

---

[2026-05-07] — Yellow highlight for status=missing search rows; fixed scraper button layout and height clipping

Fixed

gui/search_tab.py: SearchModel.data() now returns a yellow QColor("#FFFF99") for the BackgroundRole when a row has status="missing", so gap-placeholder entries are visually distinct instead of appearing as blank uncoloured rows.

gui/setup_tab.py: Replaced three stacked QHBoxLayout rows in the Web Scraper section with a QGridLayout (4 columns: label, input, action button, extras). All three rows — bulk scrape, single entry, and range — now align in a clean grid with no visual overlap.

gui/styles.py: Added min-height: 20px to the QPushButton stylesheet rule so buttons in mixed-height rows are never clipped.

---

[2026-05-07] — Persistent scraper log file; fixed [web]/[local] source labels; error entries now logged

Added

gui/setup_tab.py: `_LOG_FILE = data/scraper.log` — every `_log()` call now appends to this file in addition to the in-app widget. Log file management row added to the Scraper Log group: a size label (auto-refreshed after each write and on startup), an "Open Log File" button, and a "Purge Log" button (truncates the file and clears the in-app widget after confirmation).

Fixed

backend/scraper.py: Added `last_lb` field to `_scrape_state`, set to the LB number that just finished processing (alongside `last_source`/`last_action`). Previously `current_lb` was set at the START of processing while `last_source` was set at the END, so the GUI polled them out of sync and log lines showed the wrong source tag.

gui/setup_tab.py: `_on_scrape_status` now logs `last_lb` (the just-completed entry) instead of `current_lb` (the one currently being processed). This ensures every log line's `[local]`/`[web]` tag correctly matches the logged LB number. Added an explicit "Error scraping LB-X" log line for error entries (previously silently dropped, causing the next entry to appear with no source tag).

---

[2026-05-07] — Scraper progress bar enlarged to show percentage text

Changed

gui/styles.py: Added `QProgressBar#scrapeProgress` override — 20 px tall with centered text. The global QProgressBar rule (6 px, no text) still applies to the thin activity bars in Verify and lbdir tabs.

gui/setup_tab.py: Set `objectName("scrapeProgress")` on the scraper progress bar so the taller QSS rule targets only that widget.

---

[2026-05-07] — Search tab pagination and configurable results-per-page setting

Changed

backend/db.py: `search_entries` default limit changed from 100 to `None` (unlimited). Caller can still pass an explicit limit. Search tab now fetches all matching entries and paginates client-side.

backend/app.py: `GET /api/db/settings` now returns `force_scrape` and `search_page_size` in addition to the existing keys.

gui/search_tab.py: Added client-side pagination. All results are fetched from the API and stored in `_all_results`; only the current page slice is shown in the table. Prev/Next buttons and a "Page X of Y (N results)" label appear between the search bar and table whenever there is more than one page. A new `set_page_size(n)` public method resets to page 1 and re-renders; called by the setup tab signal. `_load_page_size` reads `search_page_size` from meta on startup.

gui/setup_tab.py: Added "Search" group with a "Results per page" spinner (range 10–500, step 10, default 50). Saved to meta as `search_page_size`. Emits `search_page_size_changed(int)` signal on change. `_load_settings` now loads `search_page_size` and `force_scrape` from meta.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `search_tab.set_page_size`.

---

[2026-05-07] — Local pages cache, scrape skip fixes, use_local_pages setting, [local]/[web] log labels

Changed

backend/scraper.py: Added `PAGES_DIR = DATA_DIR / "pages"` constant. `scrape_entry` now accepts `use_local_pages` parameter — reads `data/pages/LB-XXXXX.html` from disk when available instead of hitting the network, falling back to web only when no local file exists. When fetching from web, the HTML is saved to `data/pages/` for future reuse. Added `last_source` field (`'local'` or `'web'`) to `_scrape_state` and to the `scrape_entry` return dict. `scrape_range` accepts and threads `use_local_pages`; suppresses the inter-entry delay when `local_source=True`. `scrape_entry` attachment download now respects `use_local_pages` — existing files on disk are never re-downloaded when `use_local_pages=True`, even if `force=True`.

backend/app.py: `use_local_pages` added to `/api/db/settings` GET key list. Single-entry scrape route and `/api/scrape/start` route both read `use_local_pages` from meta and pass it through. `_start_scrape_thread` gains `use_local_pages` parameter forwarded to `scrape_range`.

gui/setup_tab.py: Added "Use local pages for metadata (data/pages/)" checkbox, saved/loaded via `use_local_pages` meta key. Scraper log now appends `[local]` or `[web]` after each "Scraped LB-X" entry using `last_source` from the status poll.

Fixed

backend/scraper.py: Scrape skip logic incorrectly re-scraped entries when `download_files=False` — any entry with `entry_files` rows (even with `downloaded=0`) was not being skipped because the pending-count check always fired. Fixed by returning `{skipped: True}` immediately when `not download_files` and the entry row exists.

backend/scraper.py: Entries with attachment files placed in `data/attachments/` from an external source were never marked `downloaded=1` in the DB, causing the scraper to repeatedly re-scrape them. Fixed by scanning the filesystem for each `downloaded=0` record and updating the DB before evaluating the pending count.

backend/scraper.py: `force=True` caused the attachment download loop to re-download files already present on disk when `use_local_pages=True`. Fixed by changing the skip condition to `local_path.exists() and (not force or use_local_pages)`.

gui/lbdir_tab.py: "Show all files" checkbox was unchecked by default, hiding pass rows and requiring a manual toggle. Changed default to checked.

gui/verify_tab.py: Same as above — "Show all files" now checked by default.

Added

backend/scraper.py: `last_source` field in `_scrape_state` (`'local'` | `'web'` | `None`) so the GUI can distinguish the metadata source per entry.

gui/setup_tab.py: "Use local pages for metadata (data/pages/)" checkbox — persisted in meta as `use_local_pages`.
