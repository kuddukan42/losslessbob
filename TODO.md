
TODO-331: Re-run tapematch for 1993-08-28 — its verdict was computed from the BUG-327 inflated LB-07173 source
Priority: Medium
Status: Open
Added: 2026-09-01
Description: Run data/tapematch/runs/20260821_184430_1993-08-28 ingested LB-07173 at 25 tracks / 3:27:33 (both passes of the show concatenated) and was flagged [INFLATED], which corrupts correlation and clustering for the whole date. BUG-327 is fixed in ingest.list_tracks, so a fresh session for 1993-08-28 will now ingest 11 tracks / ~1:32 and produce a trustworthy verdict. Separately worth analysing the nested 'bd1993-08-28-LB-7173_Milwaukee (REMASTERED)_fixed' pass as its own source by pointing a run at that subfolder.

TODO-330: Bulk tracker seeding has no announce pacing — a large add floods TUIT and drops existing seeds
Priority: Medium
Status: Open
Added: 2026-08-31
Description: Observed 2026-08-31 during the partial-overlay reseed: adding 584 torrents to qBittorrent inside an hour, on top of 1,833 already tagged 'tuit', pushed the tracker's announce endpoint into timeouts. A 200-torrent random sample showed 65 (33%) at tracker status 4 'timed out' and 10 more at status 1. Torrents that fail to announce are dropped from the tracker's peer list, so the site's seeding count FALLS while the local client still believes it is seeding — that is what the user noticed. Mitigation applied live: qBittorrent max_concurrent_http_announces lowered 20 -> 5 via the WebUI API (a runtime setting, not in the repo). TUIT is a ~21-member private tracker and tools/tuit_sync.py already paces its SCRAPE requests at 3s deliberately, but nothing paces the announce storm that a bulk seed triggers. Options to weigh: have the seeding path add torrents paused and release them on a timer; cap how many adds one run may perform; or document a required max_concurrent_http_announces for bulk runs and assert it before starting. Also worth surfacing tracker status in the seeding UI so a silent announce failure is visible. Re-sample announce health before deciding — the cap at 5 may prove sufficient on its own.

TODO-328: Per-LB 'Seed to WTRF' has no progress surface — the board search runs behind a silent toast
Priority: Low
Status: Open
Added: 2026-08-30
Description: POST /api/entry/<lb>/seed_wtrf without a topic_url calls find_torrent_for_lb, which issues paced, flood-control-throttled searches against the WTRF board and can take a minute or more. useLibraryActions.tsx fires it as a plain fetch and only reports the outcome, so the user sees nothing between click and toast. The batch path (/api/wtrf/seed_links) already streams SSE; either give the single-LB route the same stream, or route the action through the WTRF Seeding tab with the link pre-filled.

TODO-326: next_batch.py --newest-per-date can hand back a superseded run, producing contradictory analysis.md files for one date
Priority: Medium
Status: Open
Added: 2026-08-22
Description: Found 2026-08-22 while running three back-to-back tapematch batches. The flag is documented as 'consider only each date's most recent run' and is the stated way to skip superseded re-runs, but it does not do that. In tools/tapematch/next_batch.py ranked() (line ~115), by_date is built from eligible_dirs(), which already filters out any run dir that has an analysis.md. members[-1:] therefore selects the newest run *that is still pending*, not the newest run that exists. Once a date's newest run has been analysed, its older superseded runs become eligible again and --newest-per-date happily hands one back. Observed impact: batch 1 analysed the 2026-07-18 runs of 2008-09-01, 2009-08-04 and 2009-11-05, each correctly split into 2 families; batch 2 was then handed the older 2026-07-15 runs of those same three dates, whose stale clustering merges the pair at correlations 0.003-0.026, and the writer correctly flagged all three as needs-review. The result is two analysis.md files per date on disk reaching opposite verdicts, with nothing recording which one supersedes the other. Stored family data is NOT corrupted — backend.tapematch_sync reads the newest run per date, so the DB reflects the 07-18 clustering — but the on-disk analyses are now self-contradictory, and any later audit or training-set build that walks data/tapematch/runs will ingest both. Fix: under --newest-per-date, compute each date's newest run dir from ALL run dirs for that date, not from the eligible (pending) subset, and drop the date entirely if that newest run already has an analysis.md. Also worth deciding what to do with the three contradictory pairs already written — either delete the superseded 2026-07-15 analyses or mark them superseded in-file. Consider whether --stats should apply the same rule, since the eligible-dir count currently includes superseded runs that arguably should never be picked.

TODO-325: tapematch — require primary-correlation corroboration before a secondary/fingerprint link can merge a family
Priority: Medium
Status: Open
Added: 2026-08-22
Description: Recurring pattern across the three 2026-08-22 batches (50/50/25 runs): a pair is merged into one family on a secondary fingerprint or hiss/noise-profile link while the primary correlation sits far below threshold, directly contradicting two documented, independent taper chains. Confirmed instances: 2024-03-05 (badpainter Sony PCM-M10 + Church Audio CA-11 vs Mani Roland R-05 internal, merged at corr 0.073), 2024-11-08 (spot Roland R-09 internal vs soomlos Schoeps external 6th row, merged on hiss match alone, primary corr 0.189), 2023-04-20 (Spot R-09 vs soomlos Schoeps MK4V, secondary-link merge at corr 0.390), 1990-06-01 (all three recordings collapsed into one family on weak secondary links although all three uploaders independently describe specific audible differences — whistle in t5, distinct crowd sounds, differing fullness), 1995-06-16 (LB-15705 chain-unverified merge at corr 0.02-0.024 with a staircase lag pattern). Also 1981-06-21, which merges at corr 0.005 with a ~3.9 percent speed offset and no secondary evidence at all — that one is a plain threshold failure rather than a secondary-link promotion, but it lands in the same family-formation path. Question to answer: should a secondary/fingerprint link be allowed to form a family edge on its own, or must it only *reinforce* an edge whose primary correlation already clears some floor? Note that secondary evidence is genuinely load-bearing on other dates in the same batches (1995-09-27, 1993-10-03, 1980-12-04 all merged correctly on secondary links corroborated by taper commentary), so the fix is a corroboration requirement or a minimum primary floor, not disabling the path. Overlaps TODO-319 (transitive chain over-merges) — same symptom class, different mechanism: 319 is about connectivity promoting weak links into membership, this is about a single non-primary edge type being trusted alone. Validate any change against both flag sets before shipping. Per-date analysis.md files carry the specifics.

TODO-324: Re-check the 1,869 written analysis.md verdicts whose [DISTINCT SOURCE] line rested on an untrusted speed ratio
Priority: High
Status: Open
Added: 2026-08-21
Description: Fallout from BUG-330, quantified by a scan over data/tapematch/runs on 2026-08-21. Of 5,458 [DISTINCT SOURCE] lines across 2,785 run dirs, 3,678 (67%) name a source whose results.json records speed_kind == 'speed-unknown' — so two out of every three of those 'entirely different recording' claims quoted a ppm figure the pipeline had already rejected, against a correlation computed without resampling. 2,006 distinct run dirs are affected and 1,869 of the bad lines sit in runs that ALREADY have a written analysis.md, so the verdicts in those files may have leaned on the claim. The cli.py fix (commit on this branch) only changes future runs: it emits [SPEED UNRESOLVED] instead, reporting ratio confidence, best cross-family correlation and best fingerprint Dice, and drawing no conclusion. Existing report.md files are not rewritten. Plan: (1) reproduce the scan and dump the affected (run dir, source, ppm, confidence) rows to a work file; (2) for the 1,869 with an analysis.md, grep each verdict for reliance on the distinct-source claim — a verdict already resting on commentary or fingerprint evidence needs no change, one whose only support was the DISTINCT SOURCE line does; (3) re-run tapematch only for the dates where the verdict actually turns on it, since a re-run is the only way to get a trustworthy speed ratio; (4) re-write just those analysis.md files. Do NOT bulk re-run all 2,006 dirs. Note the population skews to off-speed bootleg CD/vinyl pressings, the class most likely to be a same-source copy at wrong pitch, so expect real merges to surface. Related: BUG-330, and triage_analysis.py now escalates [SPEED UNRESOLVED] rather than auto-clearing it.

TODO-322: tapematch — tighten the commentary-audit DISAGREES heuristic, which false-positives on boilerplate
Priority: Low
Status: Open
Added: 2026-08-21
Description: The auto-generated commentary audit in report.md raises DISAGREES by keyword-matching an LB's info-file prose against the clustering result, and in the 2026-08-21 batch several of those flags were spurious: the keyword hit landed in boilerplate or unrelated filler text rather than in an actual lineage claim. Confirmed false positives: 1984-06-04 (noted explicitly in that run's write-up) and 1995-03-31 (keyword hit inside bonus-filler track notes). Cost is real but bounded — an analysis writer must read past the flag to discover it means nothing, on every run where it fires. Worth scoping the match to the lineage/source portion of the info file, or requiring the matched sentence to name another LB number or a source-identity term, before raising the flag. Low priority: it wastes reader attention, it does not corrupt any stored family data.

TODO-320: Fix three data-integrity findings from the 2026-08-21 tapematch batch
Priority: Low
Status: Open
Added: 2026-08-21
Description: Three concrete per-LB defects surfaced while writing analyses; each is a data fix, not a matcher change. (a) LB-04433 is grouped under 2002-04-30 but its info file describes a completely different piano-era show — either the LB is date-mis-tagged or the info file is mis-filed; check the audio against both candidate dates before changing anything. (b) LB-14883 (2019-07-06) and LB-14908 (1997-12-10) were excluded from their runs by ingest failures on unreadable files — establish whether the source files are damaged on disk or merely in a format the ingest path mishandles, repair or re-source, then re-run those two dates. (c) LB-11041 (2006-11-11) appears to span two show dates, which needs a split or a re-tag decision. Also on 2006-11-11: LB-04265's clustering contradicts both the correlation data and the taper identity — that one belongs to TODO-319's over-merge review, not here. Corroborated 2026-08-21 (fifth batch): LB-06631 (1961-11-04) is the same defect class — its only info file's lineage text reads "Vigotone 9; 8/1/71 - Bangladesh; Blood acetates", which describes an unrelated 1971 event, so either the info file is mis-filed or the LB is mis-tagged; check the audio before changing either.

TODO-319: tapematch — investigate chain-clustering over-merges surfaced by the 2026-08-21 batch
Priority: Medium
Status: Open
Added: 2026-08-21
Description: Recurring pattern across the 2026-08-21 50-run batch: a recording gets chained into a family with no confirmed pairwise correlation to any member, against the taper commentary. Instances flagged: 2010-03-23 Tokyo (all 6 recordings merged into one family, zero confirmed pairwise evidence, contradicted by every taper account), 2010-03-24 (LB-15001 plus three others chained in unsupported), 2004-03-05 (LB-01632), 2009-10-10 (LB-08098), 1997-12-10 (over-merged single family against taper accounts), 2007-04-04 (Family 1 contradicts LB-06130's own 'distinct from all four' commentary), 2024-04-06 (LB-16228 merged into the nightlymoth family unsupported). Question to answer: is single-linkage/transitive clustering promoting weak or one-sided links into full family membership, and should family formation require a minimum confirmed-pair density rather than connectivity alone? Note the overlap with TODO-318 — some of these may be genuine same-source pairs that the disabled polarity rescue would have scored correctly, so run that validation first and re-check which of these survive as real over-merges. Per-date analysis.md files carry the specifics. Corroborated 2026-08-21 (fifth batch), same shape on further dates: 2007-04-08 is the new worst case (all 7 recordings collapsed into one family against four explicit taper contradictions), plus 2003-10-17 (Family 1, 7-way DISAGREES), 1997-12-08, 1997-12-18, 2009-07-05, 2012-07-03, 2011-06-26 (LB-12255), 2003-04-19 and 2004-11-13 (near-noise merges contradicted by taper A/B comparisons). The pattern is now seen across five batches and is not date-specific.

TODO-318: tapematch — validate and enable the channel-polarity rescue path
Priority: Medium
Status: Open
Added: 2026-08-21
Description: The 2026-08-21 50-run batch produced a clean validation set for this. Five 1984-tour shows (Boston 1984-05-31, Hamburg 1984-06-02, Basel 1984-06-21, Rome, Miami 1984-07-05) each carry taper commentary claiming the same clapping/talking wavs with channels swapped and/or phase-inverted, and every one reads near-zero mid-mid correlation and got split into distinct families. That is precisely the failure mode match.polarity_aware_corr / match.polarity_rescue were built for under TODO-184 (shipped 2026-06-24, wiring in cli.py:473-490). The capability is NOT missing — config.yaml polarity.enabled is false, held back deliberately because enabling it decodes stereo in Pass 1 (peak RAM ~461 MB mono -> ~1.2 GB stereo) and the matcher threshold is calibrated on mid-mid. The config comment asks for validation on real multi-source dates plus confirmation of no spurious merges before turning it on; these five dates supply that. Work: re-run the five with polarity.enabled=true, check whether the mid-side / side-mid pairings lift them above threshold in the direction the taper commentary predicts, then run the frozen regression set to confirm no new spurious merges, and only then decide whether to flip the default. If it validates, the analysis.md needs-review verdicts on those five dates should be revisited. Corroborated 2026-08-21 (fifth batch): more taper-documented channel-swap/phase-inverted pairs reading near-zero correlation and splitting into distinct families — 1995-06-15 (two independent taper notes describing clapping-match pairs with channels swapped and wavs inverted), 2009-04-02 (LB-07339/LB-07342), 1997-08-23 (LB-12886), 1984-06-09 (LB-01809/LB-09260), and under-merges on 1978-12-10 and 1984-06-04 where correlation was defeated by pitch-correction or heavy remaster processing. The validation set this task needs is now considerably larger than the original five 1984 dates.

TODO-317: File the 1,976 unrouted my_collection folders into the routed tree
Priority: Medium
Status: Open
Added: 2026-08-20
Description: my_collection rows whose disk_path sits outside the collection_mounts x collection_routes roots. Work package: instructions/UNROUTED_COLLECTION_BACKLOG.md (scope, phases, decisions signed off by tj 2026-08-17). 1,976 in-scope folders, ~1.36 TB: PRIVATE LB / Private Clean Ups at status=ok (1,205, formerly private and now public, drop the -NFT suffix), /mnt/DYLAN1 LB HOPPER (753), /mnt/DYLAN2 LB HOPPER (4), LK Collections (9, in scope but excluded from filing per Phase 5), Double LBs (5). 1,968 resolve cleanly, 8 blocked on no_date. Zero destination collisions against the filed tree. Out of scope: the 1,171 deliberately-private status=private rows and 4 status=missing. Audit/dry-run scripts tools/_route_audit.py and tools/_route_dryrun.py are throwaway - delete them when this closes.

TODO-316: TUIT — decide whether to scrape the forum/wiki/requests surfaces
Priority: Low
Status: Open
Added: 2026-08-19
Description: The tracker also exposes /forum, /wiki, /requests, /collages, /songs, /tour, /venue and /stats, none of which backend/tuit_scraper.py touches. Worth deciding which carry lineage or taper intelligence worth mirroring before writing more parsers.

TODO-315: TUIT — crawl the full 1,635-recording catalogue and diff it against lb_master
Priority: Medium
Status: Open
Added: 2026-08-19
Description: tools/tuit_sync.py --pages currently syncs only what is asked for; the remaining ~33 listing pages have never been crawled. Once mirrored, tuit_recordings.lb_number + info_hash + files_json can be diffed against lb_master/my_collection to find (a) shows TUIT has that the collection lacks, (b) checksum/lineage disagreements feeding TODO-299. Pace it like the wtrf crawl — small nightly batches at the 3s delay, not a single sweep.

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

