
TODO-210: Detect exact-quality-match splits as family-matching signal (LB-1594/LB-5065)
Priority: Medium
Status: Open
Added: 2026-07-08
Description: User found LB-1594 and LB-5065 have identical quality ratings and are audibly the exact same recording — only difference is track splits a few seconds apart. Investigate using exact/near-identical quality-score equality as an additional signal in family matching (e.g. as a corroborating feature or a targeted check for split-only duplicates), since a quality-rating match this precise is unlikely by chance for unrelated masters.

TODO-209: Ledger duplicate-ID audit — 17 TODO + 22 BUG header IDs reused across open/done files
Priority: Low
Status: Open
Added: 2026-07-08
Progress (2026-07-08): audit script shipped — tools/ledger_dedup.py (report-only default;
  --apply exists but is experimental and unused). Report finds 21 duplicated BUG ids and the
  TODO set, proposes keep/renumber per entry, and lists every cross-reference (CHANGELOG,
  archive, other ledger files) that needs manual attribution before renumbering. Remaining
  work: review the plan, attribute shared cross-refs, then renumber via next-id.
Description: Found while closing TODO-198 (2026-07-08): header-line grep (^TODO-N / ^BUG-N across the open+done pairs) turns up 17 duplicated TODO ids (024, 086, 102, 106-113, 140, 151, 153-155, 198) and 22 duplicated BUG ids (107-118ish, 167, 168, 175, 176, 193, 195, 200, 214-218). Almost all are low-numbered and predate tools/ledger.py (added 2026-07-07, TODO-205) — legacy manual-numbering debt from before next-id existed. TODO-198 was the one recent exception: its number was hand-set rather than assigned via next-id, bypassing the tool's own duplicate protection (_collect_ids scans both open+done files correctly, so the tool itself cannot produce a collision). Fix requires, per id: confirm which of the N entries is authoritative (check dates/content), grep every cross-reference (CHANGELOG.md mentions, [[TODO-NNN]]/[[BUG-NNN]] links in other entries, instructions/ docs) before renumbering the duplicate(s) via next-id, then verify no reference breaks. Do this as a batch script, not by hand — 39 ids is too many for manual edits to stay safe. Low priority: cosmetic/traceability issue, not a functional bug.

TODO-204: emb-gated MrMsDTW confirmation probe (near-miss band rescue)
Priority: Low
Status: Open
Added: 2026-07-04
Description: The emb near-miss band (both-conventions in [0.55, 0.75)) holds 34 low-corr FN
+ 39 frozen negatives (~73 pairs total) — too mixed to threshold, small enough for expensive
per-pair alignment. Probe: synctoolbox MrMsDTW alignment on band pairs only, then confirm
via residual corr (the trusted zero-FP-risk signal); true same-tape pairs flip, negatives
fail to confirm. Ceiling ≈ +34 TP (+1.6 recall pts). Also targets staircase/heavy-drift
pairs where the anchor/lag aligner fails. Rejected alternatives from the same review
(measured grounds): spectral-ratio stationarity = shipped spec_stationarity, rejected, 4.6%
FN coverage (alignment-gated); Panako-style speed-invariant hashing = wrong failure mode
(fp_triplet fails on same-show COLLISION Δ≈0, not speed; many sources cap at 3-4kHz HF);
htdemucs stem geometry = EQ shifts stems differentially (invariance claim fails) + massive
compute. UNBLOCKED 2026-07-05: TODO-202 densification done (12× REJECTED, 5×/0.75 kept —
net +1 flip only at the plateau edge; see TIER_B_FULLSET_REPORT.md); the near-miss band
stands, and embed_cache_12x/ + fullset_pairs_12x_scores.json are retained as a second
measurement the probe can cross-check band pairs against.

TODO-203: Tier C retrain with family-aware hard negatives (label-noise fix)
Priority: Low
Status: Open
Added: 2026-07-04
Description: Tier C's HardNegBatchSampler groups hard negatives by (date, slot) only —
embedding/data.py fetches family_id in select_sources() but never uses it. 16.2% of
same-date cross-source pairs in latest_pairs are pipeline-verified same_family, so with
hard_frac>=25% per batch and source-dense dates preferred, a material slice of the
contrastive "push apart" gradient separated same-tape transfers — training the encoder to
destroy the exact invariance TapeMatch needs. The 2026-07-03 clean-truth probe
(TIER_C_CALIBRATION_PROBE_REPORT.md) condemns the checkpoint, not the approach: it never
tested a cleanly-trained model. Re-run proposal: (1) group negatives by (date, family_id),
never same-family; (2) add pipeline-verified same-family cross-source windows as REAL
positives (corr-verified, no curator text); (3) exclude fn_label_census.py-flagged pairs
from the negative pool; (4) taper-attribution negatives (user 2026-07-04): pairs whose
entries resolve to two DIFFERENT curated tapers (_KNOWN_TAPER_ALIASES, backend/db.py) are
provenance-certified hard negatives — measured 138 such pairs agree with pipeline
different_family vs only 9 conflicts (6 of 9 involve "dolphinsmile", likely a
transferer/seeder miscaptured as taper — curator to confirm; raw taper_name strings are
NOT truth-grade: 381/2366 diff-raw-taper pairs are waveform-verified same_family because
the field mixes tapers, transferers, and generic descriptors). Dividend: same-curated-
taper + different_family pairs (21 curated / 142 raw) are a provenance-backed FN mining
list for TODO-201. Expanding the curated alias list directly grows all of these sets.
Gate: same absolute-FP protocol as Rule D; must beat nmfp's zero-FP recovery to earn a
production slot. Sequenced after TODO-202 densification results.

TODO-201: Curator review of census-flagged frozen-set labels (265 pairs)
Priority: Medium
Status: Open
Added: 2026-07-04
Description: fn_label_census.py flags 265/855 (31.0%) of the remaining corr<0.05 frozen FN
with objective label-noise markers (128 explicit "different recording" curator text, 162
speed-corrected duration ratio >15% off unity). These require curator domain judgment (only
the 3 machine-provable negative flips went into regression_set_v2.json). Reviewing them
would re-base the honest recall denominator (~52% at current tp if all confirmed). Use
calibration_audit.html for browsing; census output lists the pairs + evidence snippets.

TODO-195: Backend pipeline step.label strings need i18n key+params, not rendered English
Priority: Low
Status: Open
Added: 2026-07-01
Description: BUG-201's frontend-generated Pipeline UI vocabulary (stage names, step states,
  bucket labels) is now fully translated, but backend/app.py's pipeline step results
  (verify/lookup/lbdir/rename/file `label` and `error`/`error_code` payload fields) still return
  pre-rendered English strings — e.g. "Pass", "Missing 3", "Incomplete match", "Filed to
  Vault_A" — which the frontend displays as-is (see ScreenPipeline.tsx step.label usages and the
  no_checksums/shntool_missing/mismatch paths). Some are static enough for a frontend lookup map
  (done for STATE_LABEL/ERROR_MSG, keyed by stable status/error_code enums), but others embed
  dynamic data (counts, filenames, mount names) baked into the string server-side, which can't be
  cleanly localized without the backend returning a translation key + params instead of a
  finished sentence. Requires backend route changes (pipeline check/lookup/rename/file handlers
  in app.py) plus a frontend mapping layer — deferred out of BUG-201's scope by user decision.

TODO-194: WTRF scraper — improve match quality for remaining needs_review/ambiguous cases
Priority: Medium
Status: Open
Added: 2026-06-30
Description: After BUG-225 (LB-tag mismatch disqualification) and BUG-226 (10s search-delay
  floor) fixed the worst false-positive/false-negative classes, a validated 25-item batch run
  still leaves 9/25 entries genuinely unresolved (not counting clean not_found / date-parse
  failures). Audit results from that run, for use as concrete test cases when refining scoring:

  Ambiguous — real positive-score ties, not just the score=5 floor:
  - LB-16596: top two posts (topic=60197, topic=60199) tied at score=733, both with
    filename_matches=72 equipment_matches=1. This is a hard case — likely two near-identical
    posts for the same show/taper (e.g. original + re-up, or two encodes), so filename overlap
    alone can't break the tie. Needs an additional differentiator: post date, attachment file
    size/count vs checksums table row count, or post age (prefer earliest/most-replied topic).
  - LB-16644: topic=59943 / topic=59965 tied at score=5 (no real signal either side) — genuine
    toss-up, no data to disambiguate from.

  needs_review — single surviving candidate, weak signal:
  - LB-16633, LB-16632: RESOLVED by BUG-227, not a needs_review case — the lone candidate
    (topic=54221) isn't an unmatched pre-app post, it's explicitly labeled "LB-8" in the post
    body with an attached torrent named "LB-00008.torrent" (user-confirmed by inspecting the
    page directly). It documents LB-8, an unrelated entry, not either Del Mar 16000-series
    duplicate. The original score=5/has_torrent-only read was correct about the weak signal but
    missed the tag because the Round 0 regex required 3-5 digits (missed unpadded "LB-8") and
    never scanned attachment filenames at all. Both gaps fixed in backend/wtrf_scraper.py; this
    candidate now hard-disqualifies instead of surfacing as needs_review. The placeholder
    taper_name ("same source recording") idea below may still be worth doing for other entries,
    just not load-bearing for this pair anymore.
  - LB-16614: score=33, equipment_matches=1 + taper_match=mkws — single equipment token plus a
    taper hit still isn't enough to clear the 'medium' bar under _classify_confidence's
    `(eq>=2 and tap) or (fname>=1 and eq>=2)` rule. Worth checking whether 1 equipment token +
    taper match should count as medium.
  - LB-16613, LB-16612: score=21, equipment_matches=2 only (no taper, no filename) — sits right
    at the medium threshold's eq>=2 condition but fails because that branch also requires
    `tap` or `fname>=1`. Worth revisiting whether eq>=2 alone, with no contradicting signal,
    should be enough.
  - LB-16586, LB-16622: score=5, has_torrent only, no other signal — likely genuine not_found;
    the search is matching on date alone with no content confirmation.

  DONE (2026-06-30): Two more disqualification/scoring gaps fixed in backend/wtrf_scraper.py:
  - Download-date window: entries.description's "bittorrent download MM/YY" note (this
    curator's own acquisition date) is now parsed and any candidate post made more than 6
    months before it is hard-disqualified — a post can't be the source of a download that
    predates it. Live-verified: LB-16627's stale 2024-10-14 candidate now filtered while its
    genuine FFP match still downloads; LB-16633/16632's lone candidate disqualified on date too
    (independent of the BUG-227 LB-tag fix above). LB-16586, LB-16622, LB-16613, LB-16612 (the
    has_torrent-only / weak-equipment cases below) should be re-tested against this — some may
    now resolve to a clean not_found (correctly) rather than lingering as needs_review.
  - MD5/SHA1 checksum round added alongside FFP (chk_type 'm'/'s', same 100pt/definitive tier)
    — older SHN-era posts often list raw hashes instead of FFP fingerprints, which were
    previously invisible to scoring entirely.

  Ideas still open, roughly in order of expected payoff:
  1. Tie-breaker for positive-score ambiguous matches (post date / attachment size or count /
     reply count) — currently any tie at any score, even a strong one like 733, is treated
     identically to a zero-signal tie. (Post date is now extracted per-candidate for the
     download-window check above — reuse it here instead of refetching.)
  2. Exclude placeholder taper_name values ("same source recording" and similar) from the
     taper-match round so they don't mask genuinely unmatchable entries as "weak signal"
     when they're actually "no signal available."
  3. Revisit _classify_confidence's medium-tier boundary — eq>=2 alone and (fname>=1 OR
     eq=1)+taper currently don't clear it; check against more real examples before loosening.
  4. Board-page crawl mode (already listed under TODO-193) as a fallback for entries that are
     consistently not_found via search2.
  Relates to: [[TODO-193]] (WTRF torrent fetcher — GUI surface and review flow).

TODO-193: WTRF torrent fetcher — GUI surface and review flow
Priority: Medium
Status: Open
Added: 2026-06-29
Description: backend/wtrf_scraper.py + tools/wtrf_fetch_missing.py implement the
  search/download/qbt pipeline for missing items (see CHANGELOG 2026-06-29d).
  LIVE TESTING (2026-06-30): user ran it against the real WTRF instance — search2
  + scoring confirmed working in most cases. Two real-world failure modes observed:
  'ambiguous' (two posts score identically, no way to auto-pick), and cases where
  the best match wasn't actually the most relevant post. Both already land in
  wtrf_downloads as status='skipped' with confidence 'ambiguous'/'needs_review' for
  manual review — the manual-review action below is what's needed to actually act
  on them; not yet scoped further than that.
  CLI list/range input added 2026-06-30: --lbs flag accepts comma-separated LB
  numbers and/or ranges (e.g. '16640-16650,16700'), mutually exclusive with --lb.
  CLI now also prints the matched topic_url for skipped (needs_review/ambiguous/
  not_found) rows, including both tied URLs on an ambiguous match, so the user can
  manually open and check candidates without a DB query — a stopgap ahead of the
  full GUI review action below.
  REFINEMENT (2026-06-30): root-caused both observed failure modes from a 25-item
  dry run. (1) BUG-225: candidate scoring never checked whether a post body's own
  "LB-NNNNN" tag (embedded by forum_poster.py's metadata header) named a DIFFERENT
  entry, so posts documenting other shows competed on weak date/has_torrent signals
  and won 'ambiguous'/'needs_review' ties — fixed by hard-disqualifying tag
  mismatches in find_torrent_for_lb. (2) BUG-226: search2 queries were spaced only
  delay*1.5 (3.0s at the default --delay 2.0) apart, below WTRF's ~5s search
  flood-control window — likely caused some 'not_found' results to be silently
  throttled empty pages rather than genuine no-match. Fixed by flooring
  search_delay at 10.0s (_SEARCH_DELAY constant). wtrf_downloads rows written
  before this fix should be treated as unreliable, especially 'not_found' rows.
  PAUSED-ADD (2026-06-30): `--paused` CLI flag (backend/qbittorrent.py
  `add_torrent_for_download(paused=...)`) lets `--add-to-qbt` queue matches in
  qBittorrent without starting the download — used for a full batch run against the
  220 missing LB entries above LB-16000 (113 paused-added, 22 downloaded-only, 85
  unmatched; skipped list with candidate links exported to wtrf_skipped_review.md
  for manual review). This covers the "don't auto-download unreviewed matches"
  half of the manual-review action below; the GUI surface to actually review/
  confirm/reject from the app is still open.
  Remaining work:
  - GUI screen or panel to drive the crawl (start/stop, progress, results table)
    that surfaces wtrf_downloads rows with confidence + signals for review.
  - Manual review action for 'needs_review' / 'ambiguous' rows: show the matched
    topic URL so the user can open it and manually confirm/reject before adding
    to qBittorrent (or resuming a paused-added torrent).
  - Board-page crawl mode as an alternative to search2 when SMF search is
    throttled or returns unexpected results (walk board=16.0, board=16.20, …).
  Relates to: [[TODO-135]] (scrape WTRF for existing posts), [[TODO-194]] (match quality
    refinement — audit data from the 2026-06-30 batch runs).

TODO-192: Library UI — taper name badge on library panel entry rows
Priority: Low
Status: Open
Added: 2026-06-27
Description: Display the taper_name as a small badge/chip on each concert entry row in the library
panel, similar to the quality grade badge. Should be omitted when taper_name is null/empty or a
non-taper source label (e.g. "master", "sbd"). Helps users quickly identify recordings by a
preferred or known taper without opening the detail view.

TODO-187: Concert ranker / project — document LB rating philosophy and artifact taxonomy
Priority: Low
Status: Open
Added: 2026-06-25
Description: The LB site's two "what the information means" pages define the authoritative
  semantics behind the rating scale and the controlled vocabulary used in recording descriptions.
  This knowledge should be captured in a project document so it informs future feature
  development, calibration decisions, and new contributor onboarding — rather than living only
  in the source HTML of a page with a self-signed certificate and cp1252 encoding.

  Sources:
    - http://www.losslessbob.wonderingwhattochoose.com/LosslessBob-what.html
    - http://www.losslessbob.wonderingwhattochoose.com/LosslessBob-what-images.html

  Content to document:
    1. Rating scale semantics (from what.html):
         A+ / 5 = outstanding — casual Bob fans can enjoy
         A / A- / 4 = excellent — casual fans can enjoy
         B+/B/B- / 3 = very good — "a little more into Bob" needed
         C+/C/C- / 2 = average/good — serious devotees only
         D+/D/D- / 1 = poor — completionists only; "probably listened to once"
         F / 0 = very poor — completionists only
       These map exactly to RATING_RANK in `concert_ranker/calibrate.py:27`.
    2. Comparison methodology (from what.html): 15–30s sample from a quiet vocal passage,
       levels matched, bias toward warmer/less harsh sound; binaural > cardioid; wider capture
       > narrower. Most remasters that fiddle with tone add harshness; clipping / midrange boost
       = bad; vocal peaks clipping = especially penalised.
    3. Rating subjectivity caveats: can drift ±1 letter tier across sessions; more likely to
       move down by one tier than up; up moves ≤ 1 sublevel. Not all recordings have letter
       ratings (older ones may only have numeric 0–5).
    4. Audience annoyance policy: brief/resolved talking/singing not cited; noted when
       persistent enough to be annoying.
    5. Full artifact taxonomy (from what-images page) — all 17 named artifact types with their
       spectral/waveform signatures and quality implications (DAT, cassette, mini-disc "lego
       parapets", floating parapets, 32k DAT, digital clipping, limiting, brickwalling,
       compression, digi-pops, discontinuity pop, square wav static, digital drops, between-track
       gap, mic hit, TV band, high-end streaking).
    6. EAC match note: "exact eac match" or "close eac match" in description = recording is a
       CDR rip of a prior version, offers nothing new. The ranker could use txt_eac_match as a
       strong negative feature (see [[TODO-188]]).

  The document should also include the 22 reference image filenames and what each depicts,
  since the images add visual precision the text alone doesn't convey:
    lb_dat_spectral_view.JPG — full-spectrum DAT benchmark (reference "good" state)
    lb_cassette.JPG — dense HF noise above 18k, fuzzy grain vs. clean DAT
    lb_parapet.JPG — continuous alternating step ceiling at 15-17k (mini-disc staircase)
    lb_floating_parapet.JPG — scattered rectangular islands at irregular intervals (MP3/streaming)
    lb_dat_at_32k.JPG — perfectly clean wall at 16kHz, completely black above (most distinctive)
    lb_clipping.JPG — flat-topped peaks at 0dB
    lb_limiting.JPG, lb_limiting2.JPG — rounded/plateaued peaks, two asymmetry examples
    lb_brickwall.JPG/.2/.3 — diagonal/curved lines filling the VALLEYS BETWEEN peaks
    lb_heavily_compressed.JPG — solid rectangle waveform at full-track zoom (no dynamics)
    lb_heavily_compressed_before.JPG — natural dynamic range on same track pre-compression
    lb_digipops.JPG — isolated narrow high-amplitude spikes above quiet music
    lb_discontinuity.JPG — abrupt step-change in signal level (not silence, a DC jump)
    lb_square_wav_static.JPG — repeating rectangular/square waveform shapes (DAT error)
    lb_drops.JPG — multiple multi-second silence segments through a track
    lb_gap.JPG — abrupt step in noise floor level at a precise timestamp (sector boundary)
    lb_mic_hit.JPG — single-channel only spike (other channel flat); distinguishes from digipop
    lb_tv_band.JPG — thin horizontal stripe at 15-16k pulsing in brightness over time
    lb_high_end_streaking.JPG — chaotic vertical noise above 15k during loud passages
    lb_high_end_streaking_done_right.JPG — same track, clean professional transfer (no streaks)
  Images are from http://www.losslessbob.wonderingwhattochoose.com/lbjpg/ and were downloaded
  2026-06-25 (the site uses self-signed HTTPS and cp1252 encoding; curl -sk required).
  Suggested location: `concert_ranker/LB_KNOWLEDGE.md` (new file). Keep it factual/reference,
  not opinionated — this is the curator's own words, not our interpretation.
  Relates to: [[TODO-188]] (text features use this vocabulary), [[TODO-189]], [[TODO-190]], [[TODO-191]].


TODO-186: Library UI — quality grade + curated-pick badges, saved curated-list filter views
Priority: Medium
Status: Open
Added: 2026-06-24
Description: Surface the two new "best of" signals on the Library screen as at-a-glance chips
  rather than leaving them buried in detail views:
    - Quality grade chip: render concert_ranker's `quality_recording_scores.final_score` /
      A+..F grade (TODO-183) on each recording row/card — likely the recording lens row and
      DetailPanel.tsx, following the existing "Unconfirmed" pill pattern used for
      fam_needs_review (ScreenLibrary.tsx).
    - Curated-pick chip(s): for any LB present in `curated_list_entries`, show a small badge
      naming the curator(s) (e.g. "carbonbit's pick", "10haaf's pick") — a date/recording can
      carry more than one.
    - Saved filter views: add "carbonbit's picks" / "10haaf's picks" (and a combined "any
      curated pick") as selectable filters alongside the existing activeDecade/activeStatus
      filter sets (ScreenLibrary.tsx:336-340), backed by the still-open GET /api/curated_lists
      route from TODO-181.
  Depends on / relates to: [[TODO-181]] (curated_lists DB + import done; GET routes + filter
  wiring explicitly deferred from that pass — this TODO is that deferred UI work plus the new
  badge requirement), [[TODO-183]] (grade field this surfaces).


TODO-184: tapematch — rescue same-source false-negatives (channel-polarity inversion + partial overlap)
Priority: Medium
Status: In Progress
Added: 2026-06-24
Description: Across the Jun-22 analysis batch, tapematch repeatedly contradicts LB curator
  "same recording" commentary with near-zero correlation (~37 contradicted vs 3 corroborated
  among verdicts that cite an explicit same-source claim). Root-cause audit:
    - SPEED OFFSET — ALREADY HANDLED. estimate_ratio search is ±30000 ppm, lag-slope
      refine_speed_ratio (config refine.enabled) and the high_ppm secondary_corr_pair path
      were committed 2026-06-21. The opus Winnipeg (1990-06-17) analysis that flagged speed
      as the cause was written 2026-06-20, i.e. before that fix landed.
    - CHANNEL-POLARITY INVERSION — NOT handled. Curator notes like "right channel inverted"
      / "channels swapped and wavs inverted" (e.g. 1991-11-05 LB-10660) defeat correlation
      because Pass 1 ingests MONO ONLY (cli.py:143 mono=True, a deliberate RAM optimisation),
      so the L-R side signal needed to detect a one-channel polarity flip is discarded before
      matching. residual_corr's abs() only catches a WHOLE-signal flip (both channels), not
      one inverted channel, and a pure L<->R swap (no inversion) already survives the L+R
      mixdown. So the unhandled subset is specifically single-channel polarity inversion.
    - PARTIAL OVERLAP / PATCHWORK COMPOSITES — partially handled. secondary_corr_pair's
      windowed-coverage fraction can link a partial match, but whole-recording median corr
      still collapses and the verdict reports needs-review.
  PLAN (staged):
    1. [done] Config-gated polarity block + polarity-aware correlation helper + unit test
       (synthetic inverted-channel pair must be rescued; independent pair must NOT merge).
    2. [done] Wired stereo ingest behind the flag: Pass 1 (cli.py) now decodes stereo when
       polarity.enabled and writes an L-R "side" memmap per stereo source (same trim bounds as
       mid); the residual matrix loop re-scores a near-zero pair (med < rescue_corr_ceiling) via
       match.polarity_rescue (mid-side / side-mid, each with its OWN per-anchor lag lock, speed-
       corrected by the pair ratio), keeps the max, logs POLARITY_RESCUE. _mmap_side helper +
       side_paths dict added; default path is flag-guarded and byte-identical. 6 polarity tests +
       22-test matcher subset green.
    3. [todo] Re-run the ~37 contradicted-claim dates with polarity: true on (validate the
       Pass-1 stereo memory profile on real multi-source dates first); confirm rescues are
       genuine (curator-claimed) and no spurious merges appear; then consider default-on.
    DRY-RUN 2026-06-24 (1991-11-05 Madison, 5 sources, polarity:true via temp config, non-
    destructive — staged symlinks, package CLI direct, no archive/DB write):
      - PLUMBING VALIDATED: all 5 sources decoded stereo + got side memmaps; POLARITY_RESCUE
        fired on 4 eligible pairs. Memory peaked RSS ~2.7 GB (vs ~1.1 GB mono estimate) — the
        resample of BOTH mid and side for high-ppm pairs is the spike; acceptable but real.
      - SAFETY VALIDATED: every off-diagonal stayed ~0.002-0.007 (max 0.0065); rescue nudged
        only 0.002->0.003; n_families 5 == baseline 5. No false merge despite all pairs eligible.
      - NO RESCUE WIN HERE: LB-10660's "channels swapped and wavs inverted" is NOT a whole-
        recording single-channel inversion — the curator match is SEGMENT-level ("same clapping
        wavs at end of d1t1/d1t8/d1t10") inside patchwork composites (LB-09174 is cassette+CD,
        perf trimmed to 4934s). A whole-recording cross-term corr averages over mostly non-
        matching material -> stays near-zero. This date is really the PARTIAL-OVERLAP class.
      - IMPLICATION: partial-overlap/segment matching (clapping-wav level) looks like the bigger
        remaining lever for the contradicted-claim dates than polarity. To demonstrate a polarity
        WIN, pick a date whose curator note is a clean whole-recording "right channel inverted"
        (not segment clapping-wav). Consider a new TODO for segment-level overlap rescue.

TODO-183: Concert Ranker — audio quality scoring & ranking
Priority: Medium
Status: In Progress
Added: 2026-06-23
Description: New `concert_ranker/` package (repo root) that scores the audio quality of the user's
  own copies and ranks the best transfer of each show. The "scoring brain" (config/scoring/features/
  calibrate/audio.cache) arrived pre-built + synthetic-tested in the v1 package; this session wired it
  to the real machine per instructions/CC_CONCERT_RANKER.md — DONE: DB integration (lb/repo.py + USER
  tables quality_scans/quality_recording_metrics/quality_recording_scores), source-class derivation
  (lb/source_type.py), commentary mining (lb/commentary.py), real ffmpeg decode (audio/io.py),
  per-folder scan + producer/consumer staging loop (scan.py/runner.py, crash=scrap), recording_families
  ranking + standalone fallback (families.py), calibration harness orchestration (calibration.py), and
  the scan/calibrate/rerank/report CLI (cli.py). 11 pytest tests pass; verified end-to-end on real
  generated audio (scan→rank→rerank→report).
  CALIBRATION (done 2026-06-23): ran `calibrate` on a 117-show sample (73 AUD + 44 SBD), staged via
  /mnt/DATA2, recorded as scan_id 3. Replaced the first-principles SIGNED/SEVERITY/QUALITY band cutoffs
  + crowd_snr "buried" disqualifier in config.py with values fitted from the AUD percentiles (label-fires
  476→171; muddy/dull/boomy no longer fire on ~everything; harsh/hissy/thin/bright now functional).
  Source-class derivation switched to trust the curator entries.source_type column. Staging added to
  scan/calibrate CLI.
  ROUND 2 (done 2026-06-23): de-confounded harsh_ratio_db (now a local 2-5 kHz bump; rating rho
  +0.44->+0.06) and hiss_floor_db (now quiet-vs-loud HF persistence; rho +0.31->-0.52, correctly
  negative). Re-scanned the 117-show sample as scan_id 4, refit harsh/hiss bands — "hissy"/"harsh"
  now fire only on B-/C/D shows (zero A-tier false positives, verified against LB comments).
  ROUND 3 (done 2026-06-24): reworked dropout_count (isolated-discontinuity detection + worst-track
  aggregation; clean shows now 0, glitchy tracks surfaced) and hum_excess_db (50/60 Hz harmonic comb;
  no longer confounded by bass). Added decade-stratified sampler + `calibrate --by-decade`. Launched
  overnight scan_id 6 = 697 recordings across all 6 decades (all bad-tier included) for further iteration.
  ROUND 4 (done 2026-06-24): ran the overnight 697-show decade scan (scan_id 6, 696/697 ok), fixed a
  score_separation None-handling crash, and refit ALL bands + the dropout disqualifier (->6900, worst-
  track p95) from the 697-set into config.py. De-confounding held at scale (hiss -0.64 = top predictor);
  crowd-heavy recall restored. label-fires 1117->930; verdicts validated vs LB comments.
  ROUND 5 (done 2026-06-24): PER-DECADE bands implemented — config.DECADE_BANDS (1960s-2010s, AUD
  percentiles from scan_id 6); scoring.all_bands/explain_recording + families.rank_scan band each
  recording against its own era (global fallback when decade unknown). 'hissy' now ~10%/decade instead
  of vintage-over-flagged / modern-never-flagged. 13 tests pass.
  ROUND 6 (done 2026-06-24): PER-CLASS bands (hybrid). config.CLASS_BANDS["SBD"] + resolve_band_set();
  SBD/FM band hiss + tonal against soundboard norms. crowd_snr held GLOBAL/absolute for all classes —
  full per-class relativization wrongly made ~60% of soundboards read "crowd-heavy"; within-class
  fairness is already in the MAD-z ranking. 14 tests pass.
  ABSOLUTE SCORE (done 2026-06-24): concert_ranker/quality_score.py + config.QUALITY_MODEL — ridge
  model gives every recording a 0-100 score + A+..F grade (prepended to verdicts; stored as
  quality_recording_scores.abs_score/abs_grade). Middle filled via scan_id 7 (C tier 7->132).
  AUD MODEL REFIT (done 2026-06-25) on scan_id 8 = 2798 rated AUD (the full by-decade overnight
  scan, 6x the prior 466). 5-fold CV (3 seeds) to LB rating: Spearman 0.659, 75.6% within one tier.
  Predictors forward-selected from a 17-metric pool (alpha=0.3): hiss_floor_db, bass_ratio_db,
  mud_ratio_db, onset_clarity, directness, crowd_snr_db, harsh_ratio_db, presence_ratio_db — every
  weight sign matches its univariate direction (no confound). The old HF metrics (hf_ceiling/
  centroid/air/crest) dropped as collinear. The previous 466-fit "0.65" was small-sample-optimistic:
  it scored only 0.561 / 46%-within-1 on the full set, mostly from a mis-centered intercept (fit on
  a middle-focused sample vs the collection's true mean rank ~9.8). New model verified via the live
  predict_rank path: Spearman 0.661 / 75.9% in-sample; 16 tests pass.
  SBD QUALITY MODEL (done 2026-06-24, refit 2026-06-25): config.QUALITY_MODEL_SBD — dedicated ridge
  model for SBD/FM (predictors hiss_floor_db, hf_ceiling_hz, crest_factor_db, air_ratio_db,
  harsh_ratio_db, directness; AUD's mud_ratio_db/presence_ratio_db/spectral_centroid_hz/crowd_snr_db
  don't separate SBD tiers). Initial fit (2026-06-24) on 223 recordings (scans 3-7): Spearman 0.53,
  69% within one tier. Refit (2026-06-25, scan_id=9): 506 SBD+FM recordings all scanned with the
  current detector. dropout_count tested: rho=-0.077 (p=0.082), weight ~0 — not predictive with
  consistent detector values (old rho=0.375 was a scan-version artifact). Excluded. Same 6-predictor
  model, Spearman 0.562, 80.2% within one tier (5-fold CV, alpha=0.5). AUD model on same set:
  Spearman 0.429, 73.5% within one tier. 24 tests pass.
  FILTERING + FLOORS (done 2026-06-29, scan_id=18 = full-library rescan post hum-fix):
    - Non-concert recordings (studio/interview/tv/compilation/rehearsal/radio/soundcheck) excluded
      from scan worklist + rerank metrics (`concert_ranker/cli.py` `_NON_CONCERT_CATEGORIES` /
      `_filter_non_concerts()`); 469 entries removed (15630 vs 16099 rows).
    - hf_ceiling_hz forced back into QUALITY_MODEL as 10th predictor (w=+0.42, rho_uni=+0.341;
      forward selection had dropped it as collinear, but D/D-/F recordings showed 26-43%
      incidence of hf_ceiling < 5kHz vs 0.17% for A-tier). CV impact neutral.
    - Private/missing/nonexistent entries excluded (`_collection_worklist` LEFT JOIN lb_master
      filtered to lb_status='public', `_filter_non_public()`); xx-date (multi-date, day/month
      unknown) entries reclassified to 'compilation' tier-0 in `classify_entry_categories`
      (344 reclassified, 183 of them non-concert). 1377 non-public + 808 non-concert removed
      (13914 rows).
    - `_HF_FLOOR_RULES` hard ceiling caps added in `concert_ranker/quality_score.py`
      `_apply_hard_floors()` (post-`predict_rank()`): hf_ceiling_hz < 4000 Hz -> D- ceiling
      (rank 2); < 6000 Hz -> D ceiling (rank 3). D- now produced (26 recordings); D 1->150.
    - `_MIN_CONCERT_DURATION_SEC` = 1800s gate in `cli.py` (`_filter_short_recordings()`)
      excludes sub-30-min recordings from metrics (162 excluded). Final scored set: 13752 rows.
  REMAINING:
    - SBD-per-decade bands (deferred — sparse, esp. 2010s n=7); per-decade DISQUALIFIERS (still global).
    - dropout_count RETIRED AS MODEL PREDICTOR 2026-06-25. Reworked 2026-06-25 to detect
      3 defect types modelled on DFF (silence gaps / stuck samples / digipops). However the
      DFF pipeline (dff_vert_occ, 89% corpus coverage) supersedes it for model purposes:
      DFF drop/horz had near-zero rho; DFF vert_occ already captures the digipop signal with
      ground-truth data from the reference tool. No validation re-scan needed. Code kept
      in features.py — useful for per-recording defect display in the UI; not a model input.
    - POP/CLICK DETECTOR: the digipop arm of dropout_count covers single-sample anomalies
      (width-2 first-diff spike). A broader multi-sample click detector (2–20 samples, ~0.1–1ms)
      is NOT worth building for this corpus — DAT/cassette transfers are already well-covered by
      DFF vert_occ; vinyl clicks are rare here. Deferred/low-priority.
    - DFF ON LINUX (deferred, low priority): DFF is a Windows-only tool (sffog.com, 2009).
      New recordings added to the collection won't have pre-existing DFF HTML reports; for those
      LBs the model falls back to the training median (~2 verticals = A-/B+ level). Investigate
      whether DFF runs under Wine, or whether a comparable open-source tool exists, only if the
      fraction of unanalysed new recordings becomes large enough to matter.
    - DFF PIPELINE COMPLETE 2026-06-25: parse_dff_reports.py (12,523 LBs in dff_reports);
      dff_vert_occ = log1p(vert_occ) added to QUALITY_MODEL via forward selection — 7th
      predictor, CV rho 0.659→0.664 (+0.005), weight -0.1274; injected at rerank time by
      _inject_dff() in cli.py (89% scan_id=8 coverage; falls back to model median). Scan_id=8
      reranked. fitting script: tools/fit_aud_quality_model.py.
    - hum_excess_db FIXED 2026-06-25: root cause was PSD frequency resolution (nperseg=4096,
      Δf≈5.4 Hz) — G1 bass (49 Hz) and 50 Hz mains shared the same bin; 100 Hz and 250 Hz
      harmonic windows were EMPTY (no bin within ±2 Hz), making detection unreliable. Fixed
      with dedicated high-res Welch (nperseg=sr×2, Δf=0.5 Hz) and tight ±0.5 Hz peak window.
      Synthetic tests pass. RE-SCANNED 2026-06-26/27 (scan_id=18, full-library scan, fixed
      detector) — confirmed negative rho(hum_excess_db, rating_rank) = -0.213 (n=11723 AUD,
      p=2.4e-120; no nulls). Direction matches expectation (more hum -> worse rating).
      EVALUATED 2026-06-30 (`tools/fit_aud_quality_model.py --scan-id 18`, n=11723): full
      forward selection over the 17-candidate pool does NOT pick hum_excess_db — air_ratio_db/
      onset_clarity/crest_factor_db/hiss_floor_db/directness/dff_vert_occ/brickwall_score/
      hf_ceiling_hz already cover its signal. Isolated test (current 10 production predictors
      +hum_excess_db, no reshuffle) on the same scan: CV rho 0.6674->0.6696 (+0.0022, right at
      the 0.002 inclusion threshold), within-1 +0.07pp — within noise, not worth the added
      complexity. NOT added to QUALITY_MODEL. Closed.
    - SIDE FINDING (2026-06-30) — EVALUATED, DECLINED, CLOSED: the CURRENT production
      QUALITY_MODEL's 10 predictors score CV rho=0.6674 on scan_id=18 (full-library, post-filter
      corpus, n=11723) vs the documented 0.659-0.664 fit on scan_id=8 (n=2799) — most of that gap
      is dataset size/cleanliness, not predictor choice. A full forward-select refit on scan_id=18
      reaches rho=0.686/within-1=84.9% with a DIFFERENT 8-predictor set (drops bass_ratio_db/
      mud_ratio_db/crowd_snr_db/harsh_ratio_db/presence_ratio_db; adds air_ratio_db/
      crest_factor_db/brickwall_score) — isolated from the dataset effect, the predictor swap
      itself is only +0.019 rho / +0.16pp within-1 over running the CURRENT predictors on the
      same scan_id=18 data. DECISION: too small a gain for the blast radius (would re-rank all
      ~13,752 scored recordings and change which signals drive every score) — not applied.
      config.py unchanged. No further action.
    - lossy_flag never fires — NOT calibratable without labeled known-lossy files; needs a handful of
      known-lossy recordings to tune the 25 dB brick-wall. Parked/inert.
    - SIBILANCE DETECTION implemented 2026-06-30, calibration OPEN QUESTION (see below):
      `concert_ranker/features.py` `_sibilance_native()` produces real `sibilance_ratio_db`
      (native 5-9 kHz band local excess vs its flanking bands — 2-5 kHz below, 9-14 kHz above)
      and `sibilance_crest` (loudest-window vs median-window excess in the band, from
      `NativeProbe.window_psds_db`). Wired into `extract_hf_native()`; the `test_pipeline.py`
      stand-in (`sibilance_ratio_db = harsh_ratio_db`) removed. `POLARITY`/`SEVERITY_BANDS`/
      `FAMILY_METRICS["tonal"]`/calibration `_FIT_METRICS` already referenced `sibilance_ratio_db`
      and needed no changes. 6 new tests in `tests/test_concert_ranker.py` (synthetic NativeProbe
      PSDs). Neither metric is in `QUALITY_MODEL` yet.
      CALIBRATION INVESTIGATION (2026-06-30, scan_id=20 then 21, 107 recordings each, ~19 min/scan):
      First pass used a plain `sib - ref_mid` ratio — found it correlated POSITIVELY with rating
      in all 4 source classes (rho +0.50 to +0.67), the opposite of its polarity=-1. That's the
      same overall-brightness confound `harsh_ratio_db` had pre-ROUND-2 (brighter recordings rate
      higher in this corpus — see `hf_ceiling_hz` rho=+0.80 AUD). Rewrote to the local-excess form
      above (mirroring the proven `harsh_ratio_db` fix) and re-scanned (scan_id=21): rho dropped
      but stayed positive (+0.50 SBD/+0.50 AUD/+0.57 UNKNOWN; FM not significant). Root cause
      found from the scan_id=21 per-recording data WITHOUT a third rescan: when `hf_ceiling_hz`
      falls inside/near the sibilance band, the band + flanks read noise floor asymmetrically
      (the lower 2-5 kHz flank straddles the ceiling and still carries real signal; the band and
      upper flank don't), producing deep spurious-negative values for band-limited (low-rated)
      recordings — an `hf_ceiling_hz` artifact, not sibilance. Splitting scan_id=21 by ceiling:
      recordings with `hf_ceiling_hz` < 9000 show rho≈0 (pure floor noise, AUD 0.0/UNKNOWN -0.20);
      recordings with `hf_ceiling_hz` >= 9000 (real spectral content in-band) still show rho=+0.34
      (p=0.005, n=66 pooled) — weaker but not fully neutral, possibly an irreducible residual of
      the same brightness-correlates-with-source-quality pattern `air_ratio_db`/`hf_ceiling_hz`
      already carry in this corpus. `sibilance_crest` has NO such problem — validated cleanly in
      BOTH scans with the correct sign (rho -0.34 to -0.65, p<0.05, SBD/AUD/UNKNOWN).
      DECISION NEEDED (not yet made): (a) gate `sibilance_ratio_db` to NaN below ~9000 Hz ceiling
      and re-scan once more to see if the residual +0.34 is an acceptable "useful but imperfect"
      tonal metric, (b) drop its defect framing — set polarity=0 (informational, like
      `air_ratio_db`) and lean on `sibilance_crest` as the real sibilance signal, or (c) something
      else. Code currently left as the local-excess form (b above's polarity=-1 unchanged) pending
      this decision — do not wire `sibilance_ratio_db` into `QUALITY_MODEL` or trust its
      `SEVERITY_BANDS` labels until resolved.
    - dynamic_range_dr from the NativeProbe still not produced by the scan.
    - Polish band-label phrasing; GUI surface for quality scores/verdicts (backend + CLI only so far).
  GUI QUALITY TAB (2026-07-01): `/api/quality/<lb>` now also returns a banded `metrics` sub-dict
  (stereo/mono + width, clip_fraction, crowd_snr_db, bass/mud/harsh tonal ratios, source-type flags)
  read from `quality_recording_metrics.metric_json` and banded via `concert_ranker.scoring.band_metric()`
  (`backend/app.py:_quality_metrics_for()`); `DetailPanel.tsx` Quality tab renders these as tone-colored
  meters (`QualityMetricsPanel`/`MetricBar`/`FlagChip`) below the LB Rating/AI Quality Index tiles.

TODO-182: Explore "best LB per date" via user voting — unsure how this would work
Priority: Low
Status: Open
Added: 2026-06-22
Description: Idea: let users vote on which LB recording is the best source for a given
  date, surfaced as a "community pick" per date. Not yet scoped/decided how this would work.
  Key tradeoff: this app is single-user/local (SQLite + local Flask backend, no shared
  server), so real cross-user voting would need either (a) a new shared backend service to
  aggregate votes, which is a big architectural lift, or (b) piggybacking on the WTRF forum —
  e.g. a sticky "best of" thread that gets scraped/parsed similarly to the curated lists in
  TODO-181 — which fits the existing architecture far better. Needs a decision before any
  implementation.

TODO-181: Add curated "best of" lists as filter views (carbonbit, 10haaf)
Priority: Medium
Status: In Progress
Added: 2026-06-22
Description: No curated-list mechanism currently exists in backend/db.py. Add support for
  named curated lists of best LB recordings (starting with carbonbit and 10haaf's lists) —
  needs a new table (e.g. curated_lists + curated_list_entries mapping lb_number to a list
  name/source) and a way to import each curator's picks. Surface as a filter option on the
  Library screen (alongside the existing activeDecade/activeStatus/etc. filter sets in
  ScreenLibrary.tsx:336-340) so users can filter to "carbonbit's picks" or "10haaf's picks".
  DONE (2026-06-24): curated_lists/curated_list_entries MASTER tables (schema v9->v10) +
  CRUD in backend/db.py; tools/import_curated_lists.py (stdlib-only xlsx/zip parsing) imports
  carbonbit's data/lists/FLglist.xlsx (4503 entries, multiple LB picks per date allowed) and
  10haaf's data/lists/dylan_boots.zip + years.zip (7572 entries, union of both archives — they
  disagree on ~1,100 LB numbers between an older per-year snapshot and a newer allboots.html
  dump, neither a clean superset of the other). Ran once against the live DB.
  REMAINING: GET (and curator-gated POST/DELETE) routes for /api/curated_lists; wire a
  "carbonbit's picks" / "10haaf's picks" filter into ScreenLibrary.tsx. Explicitly deferred —
  this pass was scoped to DB + import only.

TODO-180: Show total collection size in GB somewhere in the UI
Priority: Medium
Status: Open
Added: 2026-06-22
Description: No metric currently exists for the actual size of the user's recording
  collection content. get_disk_usage_stats (backend/filer.py:61-81) only reports per-mount
  disk free/total/used_pct (filesystem-level, not collection content), surfaced on
  ScreenMounts.tsx. Need to compute total bytes across all my_collection folders (sum of
  on-disk folder sizes for owned LBs) and surface it somewhere in the UI — candidates:
  Collection screen header/stats, Home screen, or the AppShell footer stats bar
  (AppShell.tsx:814-820, alongside checksum_count/bootleg_count).

TODO-179: Consider removing the top bar to gain vertical space
Priority: Low
Status: Open
Added: 2026-06-22
Description: Tentative idea (user said "maybe") — consider removing the Topbar component
  (gui_next/src/renderer/src/components/AppShell.tsx:565+, breadcrumbs + actions, 52px height)
  to reclaim vertical space for screen content. Needs a decision on where breadcrumbs/
  per-screen actions would go instead (e.g. fold into each screen's own header) before
  actually removing it — not yet committed, just flagged as worth considering.

TODO-178: Minimized left sidebar — new icon-only nav representation
Priority: Low
Status: Open
Added: 2026-06-22
Description: No collapsed/minimized sidebar mode currently exists in
  gui_next/src/renderer/src/components/AppShell.tsx (Sidebar component, ~lines 120-561) —
  nav items always render icon + label. Implementing "new icons for when left bar is
  minimized" depends on first adding a minimize/collapse toggle for the sidebar, then
  rendering a icon-only nav state (just the Icon, no label, narrower width) using new icon
  assets suited to that compact form.

TODO-177: Implement the new app icon
Priority: Low
Status: Open
Added: 2026-06-22
Description: Replace the app icon with a new design. No icon asset exists yet in the repo
  (gui_next/resources/ only has installer.nsh; no .ico/.icns/.png app icon found) and no new
  asset has been provided yet — needs the actual icon file before implementation, then wire
  it into the Electron build config (gui_next build resources) and installer.

TODO-173: Confirmed taper tag on LB entries (soomlos, spot, hide, lta, etc.) — only show when confirmed
Priority: Medium
Status: Open
Added: 2026-06-22
Description: entries.taper_name (backend/db.py:137) already exists and is populated
  heuristically by extract_taper_and_source() (db.py:678-811), which parses free-text
  descriptions for "Taper:" labels etc. — but it's unconfirmed/best-guess text, no curation
  or confidence flag, and nothing gates whether it's shown. Add a real taper tag concept:
  a curated set of known taper names (soomlos, spot, hide, lta, and others as identified)
  with a confirmed flag per entry, and only display the tag in the UI when an entry's taper
  is confirmed — not just whatever extract_taper_and_source guessed from the description text.
  Needs a DB field/table for the confirmed flag (separate from or alongside taper_name) and
  UI work to surface the tag (e.g. as a pill) on confirmed entries.
  Known tapers now implemented in _KNOWN_TAPER_ALIASES (backend/db.py). Curated list:
  soomlos, spot, hide, lta, mk, southside butcher (ssb), iar, mjs, bw, dolphinsmile, jtt,
  pl, cedar, holy grail, vw, cck, jt, cta, tyrus, zimmy21, fine wine, hv, condor, lowgen,
  schubert, mb, jersey john, theodore, mike savage, m&a, wario, mani (=manie), bach, romeo,
  cb master, lk, hhtfp, jf, sullylove, ebr, tom moore, dk-wi, tk, bt, vito, glen dundas,
  nightly moth, csheb, streetcar visions, sk, jerseyboy, spyder9, bob meyer, markp,
  downfromtheglen, mrsoul, sh, sm, gs, rcm, mike millard (=mm), billie, jgb, tom paine (tp/tompaine56),
  mango farmer, ironchef, soledriver, goodnitesteve, clapberry, bigjim, teddy ballgame,
  theshadow, robert, sfy, caretaker, beer (=beerly=mikebeerly), caspar (=jon caspar), kuddukan,
  pdub, audiowhore, arashi, dopersan, markitospb, krw co, maloney, radioshack, kingrue,
  warburton (=jimmy warburton), captain acid (=captainacid=acidproject), andrea82, pike1957,
  sway, whofan70, two of us, mcforce, thelonius (=thelonious), jems, tarantula, lbp51,
  unwanted man music (uww), travelin man records (tmr), stevemtl, bobby bourbon (=bourbon),
  elliot, jvs, v4tx, lta–ltz (legendary taper series), nta–ntz (net taper series)

TODO-172: DB Editor — make it more like a real SQL management tool (SSMS-style)
Priority: Low
Status: Open
Added: 2026-06-22
Description: Note: column-header click-to-sort already exists (ScreenDbEditor.tsx:1492-1509,
  with ▲/▼ indicator) — not a gap. Broader ask is to make gui_next/src/renderer/src/screens/
  ScreenDbEditor.tsx feel more like SQL Server Management Studio generally. Candidate
  features to scope out: resizable/reorderable columns, a schema tree sidebar (tables/views
  grouped, expandable to show columns+types), multi-tab query windows (multiple
  SqlQueryPanel instances open at once, ScreenDbEditor.tsx:566), copyable cell/row selection
  in the results grid, query history/favorites, pinned/frozen first column, and per-column
  type-aware cell formatting (dates, booleans, NULL styling) in the rows view.

TODO-171: Add TapeMatch's observations.db as a selectable database in DB Editor
Priority: Low
Status: Open
Added: 2026-06-22
Description: DB Editor (gui_next/src/renderer/src/screens/ScreenDbEditor.tsx) currently
  only supports two databases via activeDb: 'losslessbob' (main DB) and 'batchverify'
  (BATCH_VERIFY_DB_PATH) — db picker at ScreenDbEditor.tsx:1290-1304, backend resolution in
  _dbedit_db_path()/_dbedit_is_batchverify() (backend/app.py:96-103), used throughout the
  /api/dbedit/* routes (app.py:2742-2973). Add a third option for TapeMatch's observations.db
  (tools/tapematch/, per project memory) so its tables can be browsed/edited the same way,
  likely read-only given it's tool-generated data.

TODO-170: Add a dedicated TapeMatch screen — visualize results, review logs, provide user
  feedback/corrections, and manage running the scripts
Priority: Medium
Status: Open
Added: 2026-06-22
Description: There is currently no GUI screen for TapeMatch at all — only backend sync
  endpoints (/api/tapematch/sync, /api/tapematch/families in backend/app.py:4255-4304,
  backend/tapematch_sync.py) that ingest tools/tapematch/observations.db family clusters
  into recording_families/tapematch_family_meta for display on the Library screen. TapeMatch
  itself is run/managed entirely outside the app via tools/tapematch scripts, with run output
  (results, logs, report.md) in data/tapematch/runs/ (per project memory) and
  observations.db + last_run_report.md at root. Add a new screen that: (1) visualizes
  TapeMatch results/family clusters per run, (2) lets the user review run logs and
  analysis.md/report.md write-ups in-app, (3) provides a way to submit user feedback or
  corrections on a match (e.g. wrong family grouping) that feeds back into the
  observations.db / tapematch_family_meta data, and (4) lets the user kick off/manage
  running the TapeMatch scripts themselves rather than only via the command line.

TODO-169: Home screen — remove ingest box, doesn't serve a purpose and takes up space
Priority: Low
Status: Open
Added: 2026-06-22
Description: Remove the "Hero ingest card" on gui_next/src/renderer/src/screens/ScreenHome.tsx
  (~lines 187-214, home.ingestNew/home.ingestTitle/home.ingestDesc i18n keys). User finds it
  doesn't serve a purpose and just takes up space on the Home screen. Remove the card and
  its now-unused locale keys from all 6 locale files.

TODO-168: Sidebar bottom-left shows hardcoded fake username — replace with real WTRF username
Priority: Medium
Status: Open
Added: 2026-06-22
Description: gui_next/src/renderer/src/components/AppShell.tsx:440-464 hardcodes a fake
  identity in the sidebar's bottom-left: "RW" avatar initials and the name "rolling.thunder"
  (with "Local · 4 mounts" subtitle). Replace with the actual WTRF forum username — the same
  value saved via /api/credentials/wtrf and surfaced in ScreenSetup.tsx (wtrf_username,
  handleWtrfSave/handleWtrfTest) — or render blank/no-name state if no WTRF credential is
  configured.

TODO-166: Collection screen — view/filter folders stored in nonstandard locations (not matching mount routing)
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a view or filter on gui_next/src/renderer/src/screens/ScreenCollection.tsx
  to surface my_collection folders whose disk_path doesn't match the expected mount/year
  routing — i.e. _mount_for_path (backend/integrity_monitor.py:115) resolves to a mount
  other than the one upsert_collection_routes (backend/db.py:5057) says that folder's year
  should route to, or resolves to no configured mount at all. Lets the user spot folders
  that drifted to a nonstandard location instead of finding them by accident.

TODO-164: Theme screen — add high-contrast toggle (bright white text on dark themes)
Priority: Low
Status: Open
Added: 2026-06-22
Description: gui_next/src/renderer/src/screens/ScreenThemes.tsx manages the theme CSS vars
  (--lbb-bg, --lbb-surface, --lbb-fg, etc., see vars list starting ~line 83) but has no
  accessibility/high-contrast option. Add a toggle on the Themes screen that, when enabled,
  bumps text color (--lbb-fg and related fg vars) to bright white on dark themes for better
  readability/contrast.

TODO-163: Unified Library context panel — show actual attachments list, not just a count
Priority: Medium
Status: Open
Added: 2026-06-22
Description: AssetStrip in gui_next/src/renderer/src/components/library/DetailPanel.tsx:506-544
  currently only shows an attachment count (t('library.assets.attachments', { count: attachCount })
  / noAttachments). Add the actual list of attachments (names/links, not just a number) to the
  Unified Library context/detail panel so users can see and open individual attachments
  without leaving the panel.

TODO-162: Add Olof's Files database table + scrape show/tour info into it
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a new DB table for Olof's Files (Dylan tour/setlist archive) data, modeled
  on the existing setlistfm_shows table (backend/db.py:533-541), and a new scraper module
  (alongside backend/bobdylan_scraper.py and backend/site_crawler.py) to pull show and tour
  info from olofsfiles.com into it. This is a candidate secondary source for the tour-name
  gaps tracked in TODO-153 — setlist.fm's tour_name field is empty for a large share of
  dates, and Olof's Files may have better/more complete tour coverage.

TODO-161: Pipeline — show inactive/disabled action buttons instead of blank space until they appear
Priority: Low
Status: Open
Added: 2026-06-22
Description: In gui_next/src/renderer/src/screens/ScreenPipeline.tsx, action buttons (e.g.
  Verify/Lookup/Rename/File and similar per-row actions) are currently not rendered at all
  until their step becomes actionable, leaving blank space in the row/detail panel. Render
  them in an inactive/disabled state from the start instead, so the layout stays visually
  consistent and buttons simply enable when their step becomes actionable rather than
  popping in from empty space.

TODO-160: Revamp curator mode — consolidate options and hide existence from normal users
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Curator mode currently exposes itself to every user: AppShell.tsx:400-424 always
  renders a visible "curatorHint" block + "Enable curator mode" link in the sidebar when
  curatorMode is off, so any user can discover and turn it on. The "Curator" nav group
  (AppShell.tsx:78, gated at :226 via `group.gatedGroup && !curatorMode`) and the
  curatorMode/setCuratorMode flag (store.ts:5-17) otherwise work as a simple client-side
  toggle with no real access control. Needs a revamp: (1) consolidate whatever curator-only
  options exist into one coherent settings surface instead of scattering gated items, and
  (2) replace the always-visible hint/link with a hidden trigger (e.g. a secret key
  combo, hidden settings entry, or build-time flag) so normal users have no visible
  indication curator mode exists at all.

TODO-158: Batch forum posting via multi-select or pasted LB list
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Forum posting (backend/forum_poster.py:post_lb_topic, UI in
  gui_next/src/renderer/src/screens/ScreenCollection.tsx) currently posts one LB at a time.
  Add a batch mode: either multi-select rows in the Collection screen or paste/enter a list
  of LB numbers, then post_lb_topic for each in sequence (with per-item success/failure
  reporting) instead of requiring one post action per LB.

TODO-159: LBDIR verify prior to forum post, to ensure integrity before posting
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Before calling post_lb_topic (backend/forum_poster.py), run an LBDIR verify pass
  (backend/checksum_utils.py:verify_folder, same check used in the Pipeline verify step) on
  the folder being posted, to confirm the on-disk audio still matches its checksums. Currently
  nothing blocks a forum post if the folder's integrity has degraded (see BUG-120 for examples
  of verify-fail folders); add a pre-post integrity gate so a bad/modified recording can't be
  posted without at least a warning.

TODO-157: Auto-create torrent + add to qBittorrent on forum post when no torrent exists
Priority: Medium
Status: Open
Added: 2026-06-22
Description: When posting to the forum for a recording that has no torrent yet, the forum-post
  flow should automatically generate the torrent (backend/torrent_maker.py) and add it to
  qBittorrent (backend/qbittorrent.py) as part of a single one-click "post" action in
  backend/forum_poster.py, instead of requiring the torrent to be created/added manually
  beforehand.

TODO-156: Populate all the LB problem entries
Priority: Medium
Status: Open
Added: 2026-06-22
Description: The lb_problems table (backend/db.py:497-503, CRUD in db.py:4803-4894, API at
  app.py:3827+) exists but is not populated for all known problem LB numbers. Need to go
  through known problem cases (e.g. lookup conflicts in BUG-118, verify mismatches in
  BUG-120, reconcile issues in BUG-175) and add corresponding lb_problems rows so they
  surface consistently via get_lb_problem_count()/the lb_problems UI instead of only living
  in BUGS.md.

TODO-155: Improve xref handling
Priority: Medium
Status: Open
Added: 2026-06-22
Description: xref handling needs improvement. Current xref logic lives in the `checksums`
  table (backend/db.py:114, idx_lb_xref0 partial index at :121-122), importer.py:65-164,
  and flat_file.py:362-530 (sync/diff logic comparing xref values between incoming and
  current rows). Lookup-side, the Pipeline Lookup UI surfaces an "Xref" status pill
  (see BUG-201, LookupDetail.tsx STATE_TONE). Specific improvements not yet scoped —
  needs follow-up on what's currently breaking/missing in xref handling before
  implementation.

TODO-154: New DB field for r#### source info (e.g. r9453)
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a new database field to capture "r####"-style source info seen in info
  filenames (e.g. LBF-04929-bd1990-08-16.info.r9453.txt — see
  data/tapematch/runs/20260616_200028_1990-08-16/analysis_input.md:95). This r#### id is not
  currently parsed or stored anywhere in backend/db.py or the importer; need to determine
  which table it belongs on (likely tied to the recording/LB record or a per-file source
  table) and what the r#### value actually identifies (taper/source catalog id) before
  implementing.

TODO-153: Library/perf screen — backfill good tour names across all dates
Priority: Medium
Status: Open
Added: 2026-06-22
Description: The Library screen's tour column (gui_next/src/renderer/src/screens/ScreenLibrary.tsx,
  `p.tour`) is sourced from setlistfm_shows.tour_name joined onto dylan_performances in
  backend/db.py:2121-2206 (tours dict keyed by date_str, applied at line 2204-2206). tour_name is
  empty for a large share of dates, so the column is blank for most performances. Need a way to
  pull/derive good tour names across all dates — likely requires either a better/secondary tour
  data source beyond setlist.fm, or a manual/heuristic backfill (e.g. date-range-based tour
  era tagging) for shows setlist.fm doesn't have tour info for.

TODO-152: Pipeline — Auto-unselect row when it transitions to Filed / In Collection
Priority: Low
Status: Open
Added: 2026-06-18
Description: When a row's file step completes successfully and its bucket becomes 'done'
  (Filed / In Collection), automatically clear its checkbox (set selected: false) in the
  setRows update inside applyFile (ScreenPipeline.tsx ~line 1787). Without this, bulk-filing
  a batch leaves all processed rows still checked, so the user ends up with a growing set of
  selected rows they've already finished working with.

TODO-151: Pipeline — Open button uses stale path after rename/collect
Priority: Low
Status: Open
Added: 2026-06-18
Description: After a folder is renamed or collected (moved), the "Open" button in the
  pipeline detail panel still resolves the old folder name/location. The button should
  use the updated path (post-rename / post-collect destination) rather than the path
  that was current at pipeline run time.

TODO-148: Scraper — persist live log across tab navigation
Priority: Low
Status: Open
Added: 2026-06-17
Description: The live log panel on the Scraper screen is cleared/lost whenever the
user navigates to another tab and returns. Log messages emitted during a run are not
retained, so the full session log is unrecoverable after leaving the screen. Fix should
buffer log lines in component or app state (not re-fetched from backend) so the log
panel re-renders the accumulated history when the screen is revisited. Also consider
a max-line cap to prevent unbounded memory growth during long scrape runs.

TODO-146: Setup — bundle flac.exe in tools/ like shntool.exe
Priority: Low
Status: Open
Added: 2026-06-15
Description: flac is detected via shutil.which("flac") only, so it shows yellow on
every fresh Windows install. flac.exe is a small static binary (~1 MB). Bundle it in
tools/flac.exe and update _find_flac() logic in app.py's spectrogram_check route to
probe tools/flac.exe before PATH (same pattern as _find_shntool() in checksum_utils.py
lines 24-35). This would make flac silently green on all installs with zero user
friction, matching the shntool experience.
  Source: https://xiph.org/flac/download.html  (Windows builds — grab flac.exe only)
  Winget fallback (for TODO-147 hint): winget install xiph.FLAC


TODO-136: Post editor form for existing WTRF posts
Priority: Low
Status: Open
Added: 2026-06-10
Description: Add a UI form to edit the subject and body of a WTRF forum topic that was
previously posted through the app (or discovered via TODO-135 scraper). The backend
already has the topic_url stored in forum_posts; use SMF's edit-post endpoint (POST to
index.php?action=post2 with the existing msg ID and sa=useredit or equivalent). The GUI
should surface this as an "Edit post…" action on the forum post history entry for an LB
entry — pre-populate subject/body from a scrape of the existing topic, allow editing in a
textarea, then submit. Depends on TODO-135 for posts not originally made through this app.

TODO-135: Scrape WTRF board for existing LB posts
Priority: Medium
Status: Open
Added: 2026-06-10
Description: Scrape the WTRF SMF board(s) to discover which LB entries already have a forum
topic, regardless of whether they were posted through this app. Parse board index pages
(sorted by date) and individual topic subjects to extract the LB number. Store results in
the existing `forum_posts` table (or a parallel `scraped_posts` table) so the GUI can show
"already posted" status on the Rename/post panel without relying solely on the local log.
Should be runnable on-demand (e.g. "Sync from WTRF" button) and optionally on startup.
Credentials already managed by credentials.py; HTTP session logic already in forum_poster.py.

TODO-109: Python best practices — BP document and code review
Priority: Low
Status: In Progress
Added: 2026-06-03
Description: Create a BEST_PRACTICES.md document summarising agreed Python conventions for
this project. Then do a pass over existing backend files to apply improvements: add missing
type hints to older public functions (db.py, app.py, etc.), break up oversized functions
(e.g. init_db), remove late imports, and fill in missing docstrings on exported functions.
Start with db.py as the reference — it was rated 8/10 and has the most surface area.
Note: BEST_PRACTICES.md written 2026-06-09. ruff + pre-commit configured 2026-06-09.
Code-pass over backend files deferred. 36 pre-existing ruff violations remain (E701 x12,
B023 x9, F841 x5, B905 x3, B007 x2, B904 x2, LOG015 x2, F821 x1) — will surface as
blockers when those files are next edited. E501 suppressed in pyproject.toml until then.

TODO-108: Collection tab — fix header UI problems
Priority: Medium
Status: Open
Added: 2026-06-03
Description: Investigate and fix UI problems with column headers on the Collection tab.
  Exact issues to be identified on investigation (misalignment, overflow, sticky behaviour,
  sort indicators, etc.).

---

TODO-107: Disk Scanner — find audio folders on disk for bulk collection add
Priority: Medium
Status: Open
Added: 2026-06-03
Description: Add a Disk Scanner screen that walks user-defined root paths (e.g. /mnt/nas,
  /home/user/music) using os.scandir() with early pruning, finds all directories containing
  lossless audio files (FLAC, WAV, APE, ALAC, AIFF), and presents them as candidates to
  add to the collection DB.

  Backend:
  - POST /api/scanner/scan — accepts {"roots": [...], "extensions": [...]}; walks each root
    with os.scandir(), skips hidden dirs and a configurable exclude list (system paths,
    node_modules, .git, etc.); returns list of {path, file_count, extensions, in_collection}
    where in_collection is True if the path already exists in lbdir.
  - Scan runs in a background thread; streams progress via SSE or returns a job ID to poll.
  - No persistent index — one-shot on demand. plocate can be used as an optional fast-path
    if installed (locate -r '\.flac$' | dirname | sort -u).

  GUI (new ScreenScanner.tsx):
  - Left panel: editable list of root paths to scan + exclude patterns; Scan button.
  - Right panel: results table — path, file count, extensions found, "In Collection" badge.
  - Checkboxes for bulk selection; "Add Selected to Collection" button calls existing
    LBDIR add logic.
  - Progress bar / spinner during scan; cancel button to abort background job.
  - Already-in-collection rows shown but greyed out so user can see full picture.

---

TODO-106: Trading — multi-friend batch compare
Priority: Low
Status: Open
Added: 2026-05-30
Description: Extend the Trading screen to compare your collection against multiple friends at
  once — show a matrix view (friends × shows) so you can find the best candidate to trade
  any given recording with. Also: add a GET /api/trading/friends/<id>/entries route so the
  GUI can retrieve raw friend entries without going through the compare diff endpoint.

---

---

TODO-085: Map tab — sequential date-linked travel view across the globe
Priority: Low
Status: Open
Added: 2026-05-21
Description: Add a new sub-view (or toggle) on the Map tab that renders concert locations
  as a chronological travel trail — polylines (or an animated path) connecting each
  geocoded entry to the next in date order, visualising movement across the globe over
  the years. Current map just plots pins with no temporal linkage.
  Design considerations:
    • Sort geocoded entries by date_str ascending; skip entries with no lat/lon.
    • Draw a Leaflet polyline (or GeoJSON LineString) through the ordered coordinates.
    • Optionally colour-code segments by decade so different eras are visually distinct.
    • Consider a play/scrub slider to animate the route year-by-year.
    • Hook into the existing MapTab _open_filtered_map() or add a separate "Travel view"
      button that generates a different HTML payload from the /api/map endpoint.
    • Cluster of same-venue returns (same lat/lon) should be shown as a loop or ignored
      to keep the line readable.

---

TODO-083: Export HTML — add column picker with more My Collection fields
Priority: Low
Status: Open
Added: 2026-05-21
Description: The exported HTML has six fixed columns (LB#, Status, Date, Location,
  Folder, Notes). Add a column-picker UI in the Collection tab's export dialog (or as
  query-params on /api/collection/export/html) so the user can choose which columns
  to include and their order.
  Additional columns available from get_collection() / entries / lb_master to expose:
    • disk_path (full local path)
    • confirmed_at (date added to collection)
    • source / lineage / format / bitrate / sbd (from entries if present)
    • venue / city / state / country (if entries has them split out)
    • audio_fingerprint match status (once fingerprinting lands)
  Implementation sketch:
    • Add a small "Columns…" button next to "Export HTML" in the Collection tab.
    • Pass selected column keys as ?cols=lb,status,date,location,folder,notes,... to
      the /api/collection/export/html route.
    • In collection_export_html() (app.py:882) read the cols param, fetch the extra
      fields (may require extending get_collection()), and inject column definitions
      into the HTML template dynamically rather than hardcoding the <th> block.

---

