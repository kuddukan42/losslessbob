
TODO-309: Wire up the olof chronicle parser (no registry step runs it)
Priority: Low
Status: Open
Added: 2026-08-16
Description: Found during TODO-308 (2026-08-16). backend/olof_chronicle_parser.py exists with its own run_parse() writing olof_chronicle/olof_new_tapes/olof_events, but nothing calls it: no Flask route, no refresh.STEPS entry, no tool. Chronicle pages are fetched by olof_fetch and then parsed by nothing. Phase 3 scoped olof_parse's backlog_sql to corpus='dsn' to stop a permanently-stale backlog (see the 2026-08-16 CHANGELOG entry), which is correct for the step that exists but leaves chronicle pages with no freshness signal at all. Options: add an olof_chronicle_parse step + POST /api/olof/chronicle_parse and register it in refresh.STEPS/EXECUTORS, or decide chronicles are deliberately unparsed and record that. Note chronologies.htm (the year index) has no year, so the chronicle parser cannot take it either way.

TODO-305: Coverage award: build the /lbdir/ledger and /lbdir/sync routes
Priority: Low
Status: Open
Added: 2026-08-12
Description: instructions/design_handoff_lb_coverage_award/README.md section 1 specifies four routes. /about/coverage and its certificate modal shipped 2026-08-12; the full per-entry ledger (/lbdir/ledger) and the LB snapshot-sync history (/lbdir/sync) are not built and the shipped screen has no entry points to them. Spec stays in instructions/ until these land.

TODO-304: Translate the coverage-award screen strings (de/fr/es/it/nl)
Priority: Medium
Status: Open
Added: 2026-08-12
Description: The 'Complete against LB' coverage screen and its About-dialog entry row added ~60 keys to gui_next/src/renderer/src/locales/en.json; the other five locales are untranslated. Run /gui-next-i18n.

TODO-303: Locate Olof's bobtalk quotes in our audio and add a play button
Priority: Medium
Status: Open — BUILT 2026-08-07, re-geometried 2026-08-08; only the corpus-wide run remains
Corpus run 2026-08-08: the FIRST corpus pass (boundary windows, 807 recordings, 998 of 3,301 quotes
  located) is superseded, not authoritative — full-show is now the default geometry and rows carry
  a `geometry` column so the run redoes rather than skips them. Relaunch:
  `.venv/bin/python3 tools/bobtalk_corpus_run.py` (resumable; SIGINT finishes the recording in
  flight). Budget ~20-25 h of GPU time at the measured 65x realtime — an overnight job, unlike the
  boundary pass. Expect roughly double the located quotes and a real false-positive rate; see the
  2026-08-08 CHANGELOG entry for the gate measurement and MIN_DICE_FULL.
Built 2026-08-07: backend/bobtalk.py (parse/score/confidence/persist/clip), bobtalk_locations table, tools/bobtalk_locate.py, GET /api/bobtalk/<lb> + POST /api/bobtalk/clip, BobtalkZone in the Library DetailPanel's Olof tab, locale keys in all 6 languages. 20 tests; backend suite 1,144 pass; gui-check PASS. Verified live on LB-00212 (1978-12-16): 6 of 10 quotes located, written to the DB, clip extraction from .shn confirmed playable. Remaining: decide the corpus-wide run scope (item 5 below), and optionally render play buttons inline against each line of the bobtalk block rather than as a separate list (needs the frontend to agree with backend.bobtalk's quote_index, which is why v1 renders the API's own text instead).
Added: 2026-08-07
Description: tj's idea, and it inverts the failed TODO-293 approach. Instead of asking ASR to PRODUCE transcripts (which fails -- see TODO-293 and CALIBRATION_PROGRESS.md '§3 banter/ASR signal'), use Olof's already-curated bobtalk as the target and use ASR only to LOCATE it in our own audio. Fuzzy-matching a garbled decode against a KNOWN string is a far easier problem than open transcription, so large-v3's fidelity ceiling stops mattering. The stored artifact is a timestamp, not a transcript: (lb_number, event_id, quote_index, t_start, confidence) -- small, and a low-confidence match degrades to "no play button" rather than to wrong text on screen.

Data on hand: olof_events.bobtalk is populated for 859 events (median 538 chars, max 19,329), concentrated where Dylan actually talked (674 of 859 in the 70s-90s; only 65 in the 2000s). 812 of 826 bobtalk dates have audio on disk = 3,275 source recordings. 766 of 859 (89%) also have olof_songs setlist rows. Quotes carry positional cues: 606 blocks have a 'before' cue, 436 an 'after' cue, 198 an 'introduction' cue, and 542 name a known song title. Separately, 18 bobtalk sidecar files ship inside collection folders (incl. LB-13216 "1979 - All the BobTalk") -- too sparse to be a primary source, useful as a validation set.

PoC RESULT (1978-12-16 Hollywood Sportatorium, ev5020, LB-00212, 154 min, 29 tracks == 29 setlist songs): decode a window around EVERY track boundary once, then let each quote argmax Dice (asr.content_tokens, already shipped) over all windows. 5 of 10 quotes located confidently, 2 marginal, 3 no-match. The separation is the usable part: every confident match beats its runner-up by 3-6x (0.82 vs 0.17, 0.76 vs 0.14, 0.72 vs 0.12, 0.59 vs 0.14, 0.54 vs 0.15) while every failure ties its runner-up (0.00/0.00, 0.10/0.10). So best-vs-second-best is a self-calibrating confidence rule -- no threshold tuning. Cost 443s per source (29 windows, 8 threads, batch running concurrently).

Design notes learned the hard way: (a) do NOT guess which boundary holds a quote from the setlist position -- track/setlist mapping drifts, and guessing failed in BOTH directions (a 'that was <song>' = after-cue correction made quote 1 worse, 0.49 -> 0.06). Scan all boundaries instead. (b) Track filenames are numeric (d1t01.shn / track001.flac), so title->filename matching is impossible; boundaries, not names, are the anchor. (c) Requires model: large-v3 + vad_filter: False -- base garbles too much and VAD silently drops speech entirely (TODO-293). (d) Multiple sources per date give redundancy: a quote missing from one tape may be present on another.

Work: (1) generalise the PoC (tools/_bobtalk_scan.py was the throwaway -- rewrite properly under tools/); (2) persist matches to a new table + confidence; (3) parse the 55 short bobtalk blocks that look like release-metadata bleed rather than speech; (4) GUI: render the Olof bobtalk block on the entry/show screen with a play button per located quote, hidden when confidence is low; (5) decide scope -- 3,275 source recordings at ~440s each is ~400 single-stream hours, so run it selectively (one best source per date) or parallel.

TODO-299: Triage the 312 checksum disputes and surface them in the GUI
Priority: Medium
Status: Open
Added: 2026-08-05
Description: Follow-up to TODO-296, rewritten 2026-08-06 for the two-reference audit shipped in TODO-300 (the earlier "188 high-confidence db_mismatch" framing is superseded). `lb checksum-audit` now judges each source against both the checksums table and the LB's own lbdir manifest, and tools/checksum_dispute_report.py pairs the two per track into 312 findings across 93 LBs — every one at status=open. (Counts refreshed 2026-08-06 after TODO-302 added collection-folder sidecars as a source and split the receipt bucket by audio impact.) Triage them by verdict, because the fix differs: (a) 191 db_error (uploader and lbdir agree, only the DB differs) — a transcription error repairable in one checksums row, and the highest-value work since 177 findings overall carry an orphan value whose owner gets a bare NOT FOUND today; (b) 13 audio_differs (DB and lbdir agree, both differ from the uploader, and the FFP moved) — the LB carries a different or damaged recording, not a DB fix but a re-source/flag decision, and see TODO-301 before trusting the count; (c) 27 retag (MD5-only, FFP agrees — same audio, rewritten container; the DB is not wrong about the audio but the uploader's original still fails an MD5 lookup, so decide whether to ingest the uploader's value as an accepted alternate) plus 9 receipt_unknown; (d) 72 lbdir_only. 49 findings come only from collection-folder sidecars (source_kind='collection') and need `lb checksum-audit --include-collection` to reproduce. Record verdicts via PUT /api/checksum-disputes/<id> (note: one finding = up to two rows, so a verdict may need applying to both ids). GUI work unchanged and still open: the lookup result detail items carry a dispute{} annotation and the summary a disputed count, but no screen reads either — surface it in the lookup/diff result view, add a curator triage list (GET /api/checksum-disputes, which now accepts a reference filter), and consider a badge on the entry detail screen when an LB has open disputes. Re-running the audit is cheap (30s) and preserves verdicts, so it can be wired into the flat-file update pipeline once triage exists.

TODO-295: gui_next — surface auto_triage in the TapeMatch Curation screen
Priority: Medium
Status: Open
Added: 2026-07-31
Description: Expose backend/tapematch_autoflag's machine triage in ScreenTapeMatchCuration: an 'attention'/'clear' indicator per date plus the fired rule names from auto_triage_reasons (JSON array; rule -> human text is in tapematch_autoflag.RULES). Needs GET /api/tapematch/families to return the two columns first — it currently selects review_flag/review_reason only (surfaced as fam_needs_review/fam_review_reason). Keep it visually distinct from and subordinate to the existing 'Needs review' Pill: review_flag means a human read the analysis.md prose, auto_triage is a ~0.19-precision prioritisation hint whose real value is the inverse (97.4% of 'clear' dates were human-judged clean). Do not merge the two into one badge. Deferred deliberately at ship time (TODO-294, 2026-07-31) so the field could be eyeballed in the DB first. i18n required (see TODO-275). Rule R6 staircase is also still deferred — it needs the real discontinuity logic from tools/tapematch/tapematch/cli.py surfaced into observations.db before it can be calibrated.

TODO-293: tapematch — calibrate the §3 banter/ASR signal and decide its weight
Priority: Medium
Status: Open
Added: 2026-07-30
Description: The signal is BUILT and DARK (asr.enabled: false, no addon_links rule reads banter_score). Shipped 2026-07-30: tapematch/asr.py, pairs.banter_score + banter_n_utts_a/b + banter_n_matched + banter_offset_sec, new transcripts table, 46 tests. Live proof on 2003-05-11: LB-01097/13538 scored 0.778 with 2 corroborating utterances at a consistent -16.3s offset on a pair whose corr is only 0.233 (same performance, very different-sounding tapes -- exactly the case music-based signals miss); the different-taper pair LB-01015/01046 correctly scored 0.0.

Work (spec §0 dark-launch contract): (1) enable asr on a labeled multi-source date set and pull the banter_score distribution split by frozen-set truth label; (2) DONE 2026-08-07 -- see below; (3) cross-check banter_offset_sec against each pair's alignment lag (a high score at an implausible offset is coincidence); (4) only then propose an addon_links rule, and only after a synth/frozen-set regression run. Detail + the two empirically-set gates are in CALIBRATION_PROGRESS.md '§3 banter/ASR signal'.

Step (2) DONE 2026-08-07 -- scalar is now matched-count-aware. Two corrections to this item as written: (a) "banter_n_matched is persisted so this is re-derivable without re-transcribing" was FALSE -- observations.db has 33,103 pairs with ZERO non-NULL banter_score and an empty transcripts table, since asr.enabled:false means nothing ever persists it; the 2003-05-11 figures above came from an unarchived dev run. The decision was therefore taken analytically against asr.banter_score itself. (b) The defect is worse than "2-of-2 scores like 8-of-8": the old denominator min(n_a,n_b,cap) is built from tunable ASR knobs (max_gaps, max_total_sec, model size, the confidence gates), so with evidence held fixed at 2 corroborating utterances the score falls 1.000 -> 0.500 as yield rises 2 -> 4. Since raising yield is this item's own stated next move, every planned improvement would have depressed true pairs and invalidated any threshold set beforehand. New default score_mode: witnesses = sum(sim)/score_denominator_cap (yield-independent, saturating); score_mode: rate keeps the old scalar; BOTH are always computed and persisted (pairs.banter_score = selected, new pairs.banter_score_rate = always rate, both also in results.json), so step (1) compares the two distributions from ONE transcription pass. score_denominator_cap 8 -> 4 (provisional -- under 'witnesses' it sets the whole scale, and at 8 every real pair compresses into ~[0.25,0.5]); step (1) confirms it. Free to do now only because no addon_links rule reads the score yet. 5 new tests in tests/test_asr.py.

Known limiter -- REVISED 2026-08-07 by the full-show coverage experiment (detail in CALIBRATION_PROGRESS.md '§3 banter/ASR signal'). Coverage is NOT the limiter: transcribing all five 2003-05-11 sources end to end costs ~10s each (~600x realtime), so full-show ASR is free, and yield rose only 2-9 -> 6-13 because a 2003 Dylan show contains ~50 seconds of speech (the announcer intro + the band intro). Revised priorities: (a) vad_filter:true is the real limiter and fails SILENTLY -- full-show ASR on 2003-04-18 (98 min) and 2003-11-01 (121 min) returned ZERO utterances each, and it is not the confidence gates (still zero with all three disabled); with vad_filter:False the same Dallas source yields 32 utterances in its first 300s at no_speech_prob 0.63, well inside the shipped 0.8 gate. Silero VAD discards announcer-over-crowd-noise, NULLing whole dates. (b) The announcer intro is tour BOILERPLATE (confirmed -- the same scripted announcement recovered from 2003-04-18), so matching on it identifies 'a 2002+ Dylan show', not this show; it drives 7 of 9 true-different pairs above zero, and the documented 'correct negative' LB-01015/01046 is not one -- it scores 0.708 once coverage reaches the intro. always_head_sec guarantees transcription of the LEAST identifying utterance for the which-show question. (c) DEFECT: consecutive fragments of ONE sentence count as independent witnesses toward min_corroborating (that pair's 4 'corroborations' are 4 chunks of a single announcement) -- affects the shipped windowed path too; fix before any threshold. (d) Still open from before: boundary-robust matching ('Judge Rossell is on the drums' vs 'God, the sun is on the drums', Dice 0.33) costs real matches at min_similarity 0.5. Scope caution: three dates, all 2002-03, an era when Dylan barely spoke on stage -- re-run on a 1970s date before concluding corpus-wide.

TODO-275: gui_next — internationalise ScreenTapeMatchCuration (tapematch.* keys)
Priority: Medium
Status: Open
Added: 2026-07-28
Description: The curation screen replaced ScreenTapeMatch at /tapematch on 2026-07-28 with all strings hardcoded English, so the TapeMatch screen is no longer translated in de/fr/es/it/nl. The retired screen's tapematch.* keys are still in locales/*.json and cover part of the surface (crawl strip, rail, judgment vocabulary, analysis section); the new surface (triage filters, matrix legend, evidence bars, speed-strip glyph legend, verdict cards, save/accept status lines) needs new keys. Extract to t() in the tapematch namespace, then run /gui-next-i18n to fill the five locales via DeepL. 2026-08-10: the rail-filter add-on (design_handoff_tapematch_rail_filter, folded into TriageRail) added more hardcoded strings on top — the query field's placeholder/grammar, year-brush readout ("all · drag to scope"), decade chip labels, result-bar reset/sort toggle, and the updated keyboard footer.

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

