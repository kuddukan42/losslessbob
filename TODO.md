
TODO-275: gui_next — internationalise ScreenTapeMatchCuration (tapematch.* keys)
Priority: Medium
Status: Open
Added: 2026-07-28
Description: The curation screen replaced ScreenTapeMatch at /tapematch on 2026-07-28 with all strings hardcoded English, so the TapeMatch screen is no longer translated in de/fr/es/it/nl. The retired screen's tapematch.* keys are still in locales/*.json and cover part of the surface (crawl strip, rail, judgment vocabulary, analysis section); the new surface (triage filters, matrix legend, evidence bars, speed-strip glyph legend, verdict cards, save/accept status lines) needs new keys. Extract to t() in the tapematch namespace, then run /gui-next-i18n to fill the five locales via DeepL.

TODO-274: gui_next — Topbar retired (breadcrumbs + global search removed from AppShell)
Priority: Low
Status: Open
Added: 2026-07-27
Description: Reverses the TODO-179 won't-do (2026-07-14), whose closure note said to re-file if the vertical-space itch returned. It returned: the Topbar component was removed in a session that ended without bookkeeping, and this task records the change retroactively.

Change as found in the working tree: gui_next/src/renderer/src/components/AppShell.tsx -145 lines, removing the Topbar component (52px header) and its deriveCrumbs() helper, i.e. the breadcrumb trail, the per-screen actions slot, and the global search field. The appShell.search locale key was removed from all six locale files (en/de/fr/es/it/nl), which remain at 1,725 keys each -- parity intact, and no /gui-next-i18n run is needed since this was a key removal, not an addition.

Verified 2026-07-27 before committing: no dangling references to Topbar, deriveCrumbs, or appShell.search anywhere under gui_next/src; gui-check PASS (node types 0 errors, renderer types 0 errors, production build clean).

OPEN QUESTION FOR TJ -- TODO-179 explicitly required 'a concrete decision on where breadcrumbs/per-screen actions move' BEFORE removal, and that decision is not recorded anywhere. The removal appears deliberate and is self-consistent, but two affordances are simply gone rather than relocated: (1) the breadcrumb trail, which was the only visible indicator of nesting depth for screens reached via drill-down; (2) the global search field ('Find LB#, folder, location...'), which had no other entry point in the shell. If either is meant to reappear inside individual screen headers, that work is not done. Close this task if the loss is intended; otherwise it is the tracking item for relocating them.

Status left Open deliberately -- the code change is shipped, the design decision is not.

TODO-273: tapematch — characterize the 1,822 curator-contradicted pairs (what class are they?)
Priority: Medium
Status: Open
Added: 2026-07-27
Rescoped: 2026-07-27 (same day) — the original scope was segment-level overlap rescue, which is
  a DUPLICATE of TODO-185, cancelled 2026-06-25 after three falsify-first pilots. Do not rebuild
  it. See TODO_DONE.md TODO-185 + BASELINE.md "Task 8 results" (line 388) for the full negative
  result. In particular the exact approach this task originally proposed -- best contiguous run
  over 60s residual_corr windows via secondary_corr_pair(return_raw=True) -- was already built
  (calibrate_contig_run.py) and returned longest-run = 0 windows at EVERY threshold
  (0.20/0.25/0.30/0.40) for positives AND the negative control, at both +-10s and +-120s lag
  search. Approaches 2 and 3 (HF-band and 200-4kHz windowed landmark fingerprinting) also failed,
  the latter dying in cross-validation when confirmed-distinct same-show pairs scored 0.235-0.301
  against a claimed-positive range of 0.194-0.244. Root cause recorded there: a few seconds of
  shared crowd noise cannot be separated from same-show musical content at 20s window granularity
  without onset-aligned sub-second event matching or a fundamentally different signal.

WHAT IS ACTUALLY STILL OPEN. TODO-185 characterized ONE date (1991-11-05 Madison) plus two
cross-validation dates. The claim that the whole contradicted-claim corpus is that same
patchwork/clapping-wav class was an inference from that single worked example -- it has never been
measured. The population is 1,822 pairs across 939 dates:
  SELECT concert_date, lb_a, lb_b FROM latest_pairs
  WHERE lb_says_same=1 AND tapematch_verdict='different_family' AND lb_a != lb_b
(tools/tapematch/observations.db). Earlier notes citing "~37 contradicted" described only the
Jun-22 analysis batch, not the corpus.

TASK: classify those 1,822 pairs into failure classes before proposing any new matcher. This is
metadata + curator-text work, NOT an audio campaign -- cheap, and it decides whether anything
further is worth building. Candidate classes to bucket into:
  - LABEL NOISE: curator text asserts same-source but is wrong, or the "same as" phrasing was
    mis-parsed into lb_says_same=1. TODO-201 already flags 265 pairs with objective label-noise
    markers (explicit "different recording" text, speed-corrected duration ratio >15% off unity);
    those markers should be run across all 1,822, not just the frozen set.
  - LB-NUMBER COLLISION: BUG-277 -- a cross-referenced LB tag in a folder name shadows the
    folder's own number, so pair rows can be attributed to the wrong entry entirely.
  - SEGMENT/PATCHWORK: the TODO-185 class. Known unrescuable with current signals. Measure how
    big it actually is; if it is a small minority, the corpus-scale framing was wrong.
  - WHOLE-RECORDING ALIGNMENT FAILURE: staircase/heavy-drift pairs where the anchor/lag aligner
    never locks. This is TODO-204's territory and is NOT falsified by TODO-185 (different failure
    mode, and 204 confirms via residual corr -- the signal 185 showed remains trustworthy; it was
    the Dice/fingerprint statistics that failed).
Deliverable: a bucket census with counts + a handful of worked examples per bucket, written to
tools/tapematch/ as a report. Only after that does a new matcher proposal make sense.

CENSUS DONE 2026-07-27 — tools/tapematch/census_contradicted.py, report at
tools/tapematch/CONTRADICTED_CENSUS.md (metadata only, no audio, cheap to re-run).
Priority-ordered buckets over all 1,822 pairs / 939 dates:
    alignment_failure   806 (44.2%)   [marker hits 1,269 = 69.6%]
    unexplained         377 (20.7%)
    duration_mismatch   316 (17.3%)   [marker 381 = 20.9%]
    label_contradiction 308 (16.9%)   [marker 309 = 17.0%]
    lb_collision         10 ( 0.5%)   [BUG-277]
    segment_patchwork     5 ( 0.3%)   [marker 52 = 2.9%]
FINDINGS:
  1. The patchwork/segment class -- the thing TODO-185 was built for and this task was
     originally scoped around -- is **~52 pairs (2.9%)**, not the corpus. TODO-185 was
     cancelled correctly, and it killed something that was never the main problem. The
     corpus-scale framing in the original TODO-273 description was wrong by ~35x.
  2. ALIGNMENT FAILURE IS THE PLURALITY at 44-70% depending on exclusive-vs-marker
     counting: at least one side is speed-unknown / staircase/splice, so the ratio
     estimator never locked and the pair was routed to the fingerprint path. This is
     TODO-204's failure mode, and it makes 204 substantially more interesting than its
     own 11-pair band suggested. Whatever fixes ratio-lock on these sources is the
     highest-leverage tapematch work available.
  3. LABEL NOISE IS REAL AND MEASURABLE: 309 pairs assert same-source in text that ALSO
     contains explicit "different recording"/"not the same" language, and 381 have
     speed-corrected durations differing >15%. Both are TODO-201's markers, applied
     corpus-wide here for the first time instead of to the 265-pair frozen set. Combined
     exclusive share 624 pairs (34.2%) -- i.e. a third of the "contradictions" look like
     the curator label being wrong or mis-parsed, not tapematch failing.
  4. CURATOR EVIDENCE STANDARD (the unexpected one). Most same-source claims rest on one
     stock formula: "same recording as LB-NNNN based on same clapping wavs at end of
     dXtY" -- a single localised waveform comparison. It appears in 0.0% of pairs the
     curator is silent on and 0.9% of explicit-different pairs, so it is purely a
     same-claim justification; but it appears in 54.7% of contradicted claims vs 39.7% of
     confirmed ones. Claims justified this way are confirmed 41.9% of the time (719/1,716)
     vs 56.9% (1,090/1,915) for claims justified any other way. The heuristic is
     measurably weaker but is NOT noise. Note this is also exactly the signal BASELINE.md
     Task 8 approach 3 proved unusable machine-side (same-show different-source pairs
     score 0.235-0.301 on clap-band fingerprinting, overlapping claimed positives) -- so
     the curator is leaning hardest on the one cue tapematch provably cannot verify.
  5. corr is <0.05 for 1,700 of 1,822 (93.3%) and never reaches 0.40. Whatever these
     pairs are, no current signal puts them near a merge bar.
NEXT: (a) the 624 label-noise-marked pairs are curator-review work, not matcher work --
they belong with TODO-201, which should be widened from its 265-pair frozen set to this
population; (b) the 806 alignment-failure pairs are the real matcher target and should
drive the TODO-204 decision; (c) the 377 unexplained need a second pass with a different
discriminator before anything is concluded about them.

ITEM (c) DONE 2026-07-27 — tools/tapematch/emb_second_pass.py, report at
tools/tapematch/CONTRADICTED_EMB_SECOND_PASS.md. Second discriminator = the nmfp
embedding (emb_score / emb_score_global), the one persisted audio signal the census
did not use and the only one with a calibrated production bar behind it
(addon_links.rule_d, t_emb 0.75 both-convention). corr was unusable inside the corpus
(<0.05 for 93.3%) and fp_score is NULL for 351 of the 377. Tiers, all 1,822 pairs:
    A rule_d-qualifying    46 ( 2.5%)   clears the SHIPPED merge bar, stored different
    B elevated             69 ( 3.8%)   above control p95 (0.649), below the bar
    C control-like      1,655 (90.8%)
    no_emb                 52 ( 2.9%)
FINDINGS:
  6. THE 377 UNEXPLAINED ARE NOT A HIDDEN FAILURE CLASS. 333 of 377 (88.3%) sit in
     the curator-silent negative-control emb band. Combined with the census (clean on
     every metadata axis: both sides speed-locked, duration ratio within 15%, no
     disclaimer text, no LB-tag collision) the economical reading is curator label
     noise with no textual marker -- the claim is wrong or was mis-parsed and the
     recordings really are different. Caveat stated in the report: the embedding
     recalls only 59% of confirmed pairs at that floor, so tier C is absence of
     evidence, not proof of difference. What it does establish is that no persisted
     signal puts them near a merge bar. No new matcher is justified by this
     population; item (c) is answered, not deferred.
  7. THE CONTRADICTED CORPUS TRACKS THE NEGATIVE CONTROL. emb quartiles for the 1,822
     (p25 0.132 / med 0.212 / p75 0.362) are indistinguishable from the 15,310
     curator-silent different pairs (0.128 / 0.220 / 0.325), against confirmed
     same-source at 0.467 / 0.909 / 0.975. This reframes the whole corpus: on the one
     audio signal with a calibrated bar, most "contradictions" look like the curator
     being wrong, not tapematch failing. Consistent with census finding 3 (34.2%
     carry objective label-noise markers) and finding 5.
  8. BUG-278 FOUND -- rule_d has never fired in a live session. cli.py's
     _pair_metrics() omits emb_score/emb_score_global from the dict passed to
     verdict.pair_links, so _rule_d_emb_both abstains on every pair; emb_live only
     populates the columns from _log_to_obs_db(), after clustering. So tier A is 46
     STALE VERDICTS, not a matcher gap -- the rule that merges them shipped 2026-07-04.
     Transitive corpus effect if wired: 58 curator-claimed + 80 curator-silent pairs
     flip to same_family across 80 dates. The 80 silent flips are why this is filed as
     a bug to be scoped rather than patched here -- rule_d's zero-new-FP proof covers
     the 2,245-pair frozen sets only.
REMAINING: (a) and (b) above are unchanged and belong to TODO-201 and TODO-204
respectively. Note finding 8 lands on (b): 34 of the 46 tier-A pairs are in the
alignment_failure bucket, so BUG-278 recovers a slice of TODO-204's target population
for free, and TODO-204 should be re-scoped only after BUG-278 is decided.

TODO-264: DYLAN2 disk health + re-source 2 corrupt files found in BUG-120 forensics
Priority: High
Status: Open
Added: 2026-07-22
Description: BUG-120 forensics (2026-07-22) found two non-FLAC corrupt files sharing an identical 420KB high-entropy prefix despite mtimes 9 years apart — evidence of cross-linked clusters / filesystem damage on the DYLAN2 disk, not per-file corruption. Actions for tj: (1) fsck/chkdsk /mnt/DYLAN2 and assess disk health (SMART); (2) re-source '/mnt/DYLAN2/Concerts/1978/1978-06-20 London, England (LB-06548)/09 Don't Think Twice.flac' (expected md5 21116b8f97590bb15f8da8dbdcbbca23) and 'd18 2 - bd65-cutting-edge - More and More (Mono, Live).flac' in the Cutting Edge [24-96] LB 12181 folder (expected md5 per bd65-Cutting-Edge.md5); (3) optional: regenerate LB-12181's md5 entry for 'd18 7 - Young but Daily Growing' — audio is bit-perfect (PCM fingerprint matches ffp), only the container/tags were rewritten during the 2021 disc-18 recopy.

TODO-234: TapeMatch family over-merge review — 22 series-vs-series taper conflicts
Priority: Medium
Status: Open
Added: 2026-07-13
Description: After the TODO-213 taper-attribution curation pass (non-taper credits excluded, robert removed, mention-downgrade rule) the taper_attributions conflict queue dropped to 53, of which 22 are SERIES-vs-SERIES: two *legitimate* taper series (e.g. ltc/ltg, net taper a/net taper i, lta/ntj) attributed to members of one recording_families family, both with strong (series_code/explicit) evidence. These are NOT an attribution bug and NOT a wordlist fix — they indicate the fingerprint/clustering pulled two genuinely different sources into one family (a false-merge). Recurs around prolific series: net taper a (10 merges), ltb (6), ltc/ltg (5). Approach: for each of the 22, pull the family's members + tapematch evidence (observations.db corr / duration / explicit signals for the pair), decide split vs keep; if split, the family_meta review_flag or a family-split path in tapematch is the lever, then re-run taper_attribution.recompute(). Belongs to the tapematch calibration/family subsystem, not backend/db.py taper curation. Query for the 22: SELECT lb_number, evidence_json FROM taper_attributions WHERE conflict=1 — filter to rows whose candidate tokens are all lt[a-z]/net taper [a-z]. Related: [TODO-213].

TODO-204: emb-gated MrMsDTW confirmation probe (near-miss band rescue)
Priority: Low
Status: Open
Added: 2026-07-04
Deferred (2026-07-09): calibration frozen for the 7/09–7/12 window
  (WORK_PACKAGE_2026-07-09 decision 1) — this is the parked breakthrough probe;
  12× embed-cache artifacts retained for it.
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
REMEASURED 2026-07-27 (while closing TODO-184; fullset_pairs_scores.json, both conventions
in [0.55, 0.75)):
  - CEILING HAS DROPPED. The band is now 50 pairs, not ~73: 39 frozen negatives (UNCHANGED,
    exactly as described) + **11 low-corr FN, down from 34**. The negatives held still while
    two thirds of the FN side was already rescued by other means -- presumably the 07-20
    corpus rescore (TODO-254/235) and/or TODO-255 frozen-set gating. So the realistic ceiling
    is ~+11 TP / ~+0.5 recall pts, not +34 / +1.6. The 12x scoring is smaller still (42 pairs:
    36 neg + 6 fn_lowcorr), so the probe's own cross-check measurement is thinner too.
  - THE BAND SEPARATES PERFECTLY BY CURATOR TESTIMONY. All 11 fn_lowcorr pairs are
    curator-contradicted same-source claims (lb_says_same=1, verdict=different_family); all 39
    negatives are not. Zero crossover. That makes the band an unusually clean 11-pair labeled
    test set -- a true same-tape pair should flip under MrMsDTW confirmation and a negative
    should not, with curator testimony as an independent label. 11 pairs is a cheap probe, and
    that cheapness (not the recall number) is now the argument for running it.
  - NOT A SUBSTITUTE FOR TODO-273. The band covers 11 of the 1,822 curator-contradicted pairs
    (0.6%); against the 826 of those that are scored in the fullset at all, still only 1.3%.
    Widening to EITHER convention in band gives 343 pairs / 117 contradicted, but that band is
    not the calibrated one. Segment-level overlap (TODO-273) remains the corpus-scale lever;
    this probe is a narrow, well-labeled experiment alongside it.
  - The "calibration frozen for the 7/09-7/12 window" deferral above is expired, and TODO-202
    already discharged the other blocker -- this is parked on inertia, not on a live constraint.
  - The 11 pairs: (1988-09-03, 2588/14344) (1989-07-19, 2216/2448) (1989-08-05, 7993/12848)
    (1991-06-06, 4089/12326) (1992-05-11, 5938/12553) (1992-06-30, 763/764) (1996-06-19,
    1919/5498) (1996-11-23, 4155/7134) (1997-02-10, 3279/12897) (1998-01-20, 10583/11496)
    (2001-03-13, 471/5370).

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

TODO-251: Trading — multi-friend batch compare
Priority: Low
Status: Open
Added: 2026-05-30
Renumbered: from TODO-106 on 2026-07-15 (TODO-248 — id collided with the unrelated done
  TODO-106 "Audio fingerprint matching" in TODO_DONE.md)
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

---

