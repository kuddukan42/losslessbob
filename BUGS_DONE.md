# Fixed Bugs Archive
# Active/open bugs are in BUGS.md. Entries here are Fixed or Wontfix.

BUG-260: verify_folder ingests extras/ sidecars + audio → reconciled folders wedge on 'incomplete'
Status: Fixed
File(s): backend/checksum_utils.py:629,backend/checksum_utils.py:642
Reported: 2026-07-19
Fixed: 2026-07-19
Root cause: verify_folder()'s two rglob scans (disk-audio map + .ffp/.md5/.st5 sidecar gather) never got the _is_reconciled_extra() guard the BUG-257 lookup fix added, so a set-aside sidecar under extras/ contributed expected entries (qualified extras/<name>) — missing on disk in the BUG-257 folder shape → n_missing>0 → status 'incomplete' → pipeline Step-1 Verify stuck on warn for a folder lookup now passes. With extras audio present, the superseded fileset was silently re-verified and inflated total/extra counts.
Fix: Skip _is_reconciled_extra() paths in both scans, keeping the extras/ subtree out of the verify universe entirely (mirrors lookup + verify_folder_lbdir semantics). Repro'd both shapes (extras-only sidecar → was incomplete/missing=1, now pass; full sidecar+audio extras → total drops to main fileset only). Regression tests in tests/test_checksum_extras.py; full suite 880+11 green.

BUG-259: generate_checksums hashes audio under extras/ into fresh top-level sidecars — reopens BUG-257 via Generate button
Status: Fixed
File(s): backend/checksum_utils.py:1267
Reported: 2026-07-19
Fixed: 2026-07-19
Root cause: The multi-disc recursion change (this branch) swapped iterdir() for folder.rglob('*') without excluding move_extras' set-aside dir, so "Generate FFP + MD5" hashed superseded/alternate audio under extras/ into a new top-level _mychecksums.ffp/.md5. Pipeline lookup only skips sidecars *located under* extras/, so it ingests the top-level sidecar — merging the other fileset's hashes back into the input and recreating the false multi-LB "perfect match" BUG-257 fixed.
Fix: Filter _is_reconciled_extra() relative paths out of the audio rglob in generate_checksums(); disc-subfolder audio (CD1/…) still included. Repro'd before/after (extras/alt-t01.wav line present → absent); regression tests in tests/test_checksum_extras.py.

BUG-258: Private metadata importer silently skipped bracketed folders and misread canonical LB-<num>.txt sidecars
Status: Fixed
File(s): tools/import_private_metadata.py:185,tools/import_private_metadata.py:204
Reported: 2026-07-18
Fixed: 2026-07-18
Root cause: info_txt_candidates() globbed folder paths without escaping; private folders carry [LB-NNNNN]/[taper] brackets that glob treats as character classes, matching nothing. Separately the lineage regex required space-padded arrows, and the setlist extractor only handled one-track-per-line, missing the LB-<num>.txt sidecars' inline comma-run setlists (which wrap mid-title across lines, use 1-/101 variants, and run a footer onto the last track).
Fix: glob.escape(folder) before globbing; broadened _LINEAGE_LINE to match unicode arrow, -> and word>word; added block-based _setlist_from_inline() that de-wraps -----fenced blocks, splits only on ', <n>' boundaries (commas inside titles survive), reuses the chain/disc-restart validator, and strips disc-label + 'Please retain...' tails. Result on the live DB: setlists 1210->1309 (+99), descriptions 1356->1362; no_info_txt 54->11.

BUG-257: Pipeline lookup ingests extras/ sidecars → false multi-LB 'identical' match
Status: Fixed
File(s): backend/app.py:7287
Reported: 2026-07-18
Fixed: 2026-07-18
Root cause: Step-2 Lookup gathered checksum sidecars with folder.rglob('*') and read every .ffp/.md5/.st5 including those under extras/ (move_extras' set-aside dir). extras/ held the alternate-transfer sidecars, so the parsed set covered both filesets → lookup_checksums reported both LBs MATCHED → the _all_perfect multi-LB auto-link fired and renamed the folder (LB-12226+LB-16533).
Fix: (1) Skip files matched by checksum_utils._is_reconciled_extra() (extras/ subtree + rename_log.txt) when gathering lookup input in app.py. Verified on the real folder: LB-16533 drops MATCHED→DUPLICATE, so no false multi-LB auto-link. (2) Added a pipeline 'Override LB#' control (ScreenPipeline OverridePanel) to force a single LB via replace_folder_link when sidecars mislead the match. (3) Made a single explicit folder pin authoritative in the LBDIR LB# resolvers — _resolve_lb_number_for_folder + the inline resolvers in /api/lbdir/check, /retrieve, /reconcile previously ordered my_collection→name-regex→pin, so an override was ignored (LBDIR verified the wrong LB); new _pinned_lb_for_folder() helper puts a single pin first. Verified /api/lbdir/check returns 16533 (23/23 pass) even with lb_number_hint=12226.

BUG-256: Pipeline lookup wedges duplicate-fileset folders in 'Incomplete match'
Status: Fixed
File(s): backend/app.py:7374
Reported: 2026-07-18
Fixed: 2026-07-18
Root cause: full_match = summary['matched'] == summary['given'] compares the GLOBAL matched count, which double-counts checksums matched under duplicate LB entries (matched == given*N), so a genuinely-complete folder is misclassified as Incomplete match. The is_multi_lb escape hatch doesn't help once alias resolution collapses the duplicates to a single canonical LB.
Fix: Test full_match on distinct unmatched checksums instead: full_match = summary.get('unmatched', 1) == 0. Duplicate-fileset folder now resolves ok to the canonical LB (with or without a pin); a genuine NOT-FOUND still blocks as Incomplete match. Verified against live DB (LB-16353 alias -> LB-16369 canonical).

BUG-106: Windows installer does not place app in Program Files
Status: Fixed
File(s): installer/losslessbob.iss (or equivalent Inno Setup script)
Reported: 2026-05-22
Fixed: 2026-07-16
Root cause: Inno Setup script (tools/losslessbob.iss) targeted the legacy PyQt6 desktop build; DefaultDirName never fixed.
Fix: Obsolete by removal: the legacy desktop distribution channel (PyInstaller specs + Inno Setup script) was deleted in the legacy GUI removal 2026-07-16; gui_next Electron packaging replaces it.

BUG-249: pytest full-suite intermittent native crash in test_lb_master.py::test_status_combobox_exists
Status: Fixed
File(s): tests/test_lb_master.py:373
Reported: 2026-07-11
Fixed: 2026-07-16
Root cause: Native Qt/pytest-qt widget-teardown interaction in the legacy GUI test classes — never root-caused at the Qt level.
Fix: Resolved by removal: the legacy PyQt6 GUI and its qtbot test classes were deleted (legacy GUI removal, 2026-07-16); pytest-qt uninstalled. The crashing test no longer exists.

BUG-251: tapematch — report.md for 1999-02-25 Portland, Maine contains another session's tapematch output verbatim
Status: Fixed
File(s): data/tapematch/runs/20260602_205451_1999-02-25/report.md
Reported: 2026-06-17
Renumbered: from BUG-200 on 2026-07-15 (TODO-248 — id collided with the unrelated fixed
  BUG-200 "Verify tab no checksums" in BUGS_DONE.md; pre-2026-07-15 references to BUG-200
  for the tapematch report contamination mean this bug)
Fixed: 2026-07-15
Root cause: One-off stale-stdout attach on 2026-06-02: report generation at 20:54:51 grabbed cached tapematch stdout from the earlier 2018-08-26 Auckland session; a corrected regeneration of the same session followed 9 seconds later (20260602_205500). Not a systemic generator fault — full-corpus scan 2026-07-15 (fenced tapematch-output LBs vs rest-of-report LBs across 2,280 run dirs) found this single contaminated report.
Fix: No re-run needed: clean sibling runs 20260602_205500 (the immediate regeneration) and 20260602_204033 both carry correct Portland output for LB-04452/LB-05683/LB-09627/LB-12715 — verdicts drawable from them. Contaminated dir marked with SUPERSEDED.md pointing at the clean runs (non-destructive; deleting the dir is at tj's discretion).

BUG-118: Pipeline lookup conflict — 11 folders whose checksums match 2–5 LB entries
Status: Fixed
File(s): backend/db.py:lookup_checksums, backend/app.py:4610
Reported: 2026-05-31
Fixed: 2026-07-15
Root cause: Two distinct causes: (1) degenerate hashes — the empty-file MD5 (d41d8cd9…) and SHA-1, and the all-zero FLAC ffp written when STREAMINFO carries no MD5 — are shared by unrelated LB entries (phantom quartet 04994/03029/06748/11900 share the empty-file MD5), so any folder containing a zero-byte/no-MD5 file matched them all; (2) genuine duplicate data — 5,261 (checksum,chk_type) groups appear under 2+ LB numbers (same show under consecutive LB entries, one recording under multiple entries — worst: 16054/16101/16440/16511/16621 sharing 718 hashes).
Fix: backend/db.py: _is_degenerate_checksum() + _DEGENERATE_CHECKSUMS; lookup_checksums now treats degenerate hashes as non-evidence in both directions (excluded from matching AND from missing-from-set counts; still listed in detail with ignored=True, status NOT FOUND). backend/importer.py: de-dup guard after incremental merges (<=500 new LBs) logs hashes already present under other LB numbers. Full report: shared_checksums_report.md (repo root). 32 lb_problems rows added for the conflict pairs/clusters (also TODO-156). Genuine same-show duplicates remain data facts — pin-picker mitigation from 2026-06-10 still the resolution path; per-entry curation tracked in lb_problems. Verified: functional test (degenerate+real mix resolves to single LB, counts exclude ignored rows) + 240 tests pass (test_db_lookup/test_db_writes/test_setlistfm/test_geocoder).

BUG-250: Checksum-lookup detail_url built without zero-padding — LB-42.html style 404 links
Status: Fixed
File(s): backend/db.py:2512
Reported: 2026-07-15
Fixed: 2026-07-15
Root cause: Site base URL was an independent literal in 6 backend modules; db.py's copy interpolated the raw int (f"LB-{lb}.html") instead of the LB-%05d convention.
Fix: Added SITE_BASE_URL + detail_url(lb) (zero-pads via int(lb):05d) to backend/paths.py; all 6 modules now derive from it (commit 30d97229). Backend twin of BUG-221's lbUrl.ts consolidation.

BUG-230: GNOME Wayland dev window still shows generic gear icon in the dock/taskbar
Status: Fixed
File(s): gui_next/src/main/index.ts, gui_next/resources/losslessbob-next.desktop
Reported: 2026-07-01
Fixed: 2026-07-14
Root cause: Unconfirmed (candidates: Wayland app_id/desktop-file-id mismatch, .desktop not picked up in dev, Electron app_id emission) — dev-window-only cosmetic; packaged AppImage expected unaffected.
Fix: Won't-fix (user decision 2026-07-14): dev-only cosmetic issue, not worth root-causing. Reopen if the packaged AppImage ever shows the generic gear icon.

BUG-246: Live show_picks wiped — first-init-wins write queue lets derived writers hit a different DB than they read from
Status: Fixed
File(s): backend/db_queue.py:146,concert_ranker/picks.py:353
Reported: 2026-07-10
Fixed: 2026-07-14
Root cause: Writers that READ current state via get_connection(db_path) but committed a state-dependent wholesale/derived write through the first-caller-wins get_write_queue() singleton could split reads and writes across different DBs (empty read on the intended DB → destructive commit against the queue's live DB).
Fix: Applied the picks-style _run_write path-match guard to the two remaining vulnerable writers: taper_attribution._write_attributions (wholesale DELETE+reinsert; wipe class) plus its single-row confirm/reject/mark_unresolved, and flat_file.apply_flat_file_release (read-derived diff; desync class) — on db_path != queue.db_path they write directly via get_connection(db_path). Audit of tapematch_sync (uses same conn, no queue), parse_lineage (upsert-only), scrapers/geocoder/importer (external-driven or upsert-only) found no further exposure; song_index/setlist_fingerprint already carried the guard. Regression test test_write_targets_db_path_not_queue_binding added for the taper wipe vector.

BUG-248: tests/test_geocoder.py: 13 stale TODO-220/221-era tests fail on main
Status: Fixed
File(s): tests/test_geocoder.py
Reported: 2026-07-11
Fixed: 2026-07-13
Root cause: TODO-220/221 session changed geocoder.py contracts (tuple returns, concert-eligibility filter) without updating the 13 pre-existing test fixtures/assertions
Fix: Fixed 2026-07-11 in commit 74507645 (test(backend): un-rot tests/test_geocoder.py): fixtures updated to insert bobdylan_shows/setlistfm_shows rows and assertions updated to the (full, city_only) tuple contract; 52/52 pass, no production code change

BUG-247: tapematch crawl crash-loops on merged folders (two LB ids, one directory)
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:514
Reported: 2026-07-10
Fixed: 2026-07-10
Root cause: Merged archive folders map several LB ids to one physical directory; copy_folders() iterated per LB id and re-copytree'd the same destination, crashing on the duplicate.
Fix: copy_folders() now tracks already-copied source paths and skips duplicates with a log line (tapematch_session.py copy_folders). Verified live: skip fired once, crawl resumed through 2000-03-16.

BUG-245: Library grid taper pill shows unvalidated free-text guesses (mono/poor sound/etc.)
Status: Fixed
File(s): backend/db.py:1034,gui_next/src/renderer/src/screens/ScreenLibrary.tsx:857
Reported: 2026-07-09
Fixed: 2026-07-09
Root cause: Two disconnected taper systems: legacy free-text parser (db.py extract_taper_and_source) stores an unvalidated best-guess taper_name per recording, while the newer taper_attribution.py engine only recognizes curated _KNOWN_TAPER_ALIASES. The Library grid pill read raw taper_name filtered only against a small generic-word denylist (NON_TAPER_LABELS), never against the curated universe the Taper tab uses, so parser false positives (rule 12's loose stopword list didn't cover quality/broadcast descriptor words) rendered as authoritative-looking pills.
Fix: Tightened rule-12 stopwords (mono/sound/poor/good/excellent/hum/hiss/radio/broadcast/special/dylan/bob) and added 'poor sound'/'mono' to the _NOT_TAPER denylist in backend/db.py. Added is_known_taper()/_TAPER_UNIVERSE (shared with taper_attribution.py, which now imports it instead of recomputing) and a taper_known field on every /api/search row. ScreenLibrary.tsx's taper pill now gates on r.taperKnown, so it only renders when the taper_attribution engine would also recognize the name -- closing the disagreement even for already-persisted bad taper_name values.

BUG-236: gui_next renderer has 14 pre-existing baseline TypeScript errors
Status: Fixed
File(s): gui_next/src/renderer/src (ScreenScraper.tsx ×4, ScreenCollection.tsx ×4,
  ScreenPipeline.tsx ×2, ScreenRename.tsx ×2, AppShell.tsx ×1, pipeline/LookupDetail.tsx ×1
  as of 2026-07-07)
Reported: 2026-07-04
Fixed: 2026-07-08
Root cause: 14 pre-existing renderer TS errors (dynamic i18n keys, missing Pill title / IconButton disabled / Input type props, wrong addSource payload shape, shiftKey read from ChangeEvent, string|null widening, toast tone typo) left the /gui-check baseline dirty.
Fix: All 14 fixed properly (two were functional bugs: addSource payload shape in ScreenCollection, shift-click range-select moved to onClick). tsc -b clean, production build clean; typecheck script added to gui_next/package.json and wired into .pre-commit-config.yaml (gui-next-typecheck, scoped to gui_next/*.ts(x)).

BUG-233: WTRF torrent saved with junk filename "UTF-8.torrent" from RFC 5987 Content-Disposition
Status: Fixed
File(s): backend/wtrf_scraper.py:555 (_download_torrent Content-Disposition parse)
Reported: 2026-07-01
Fixed: 2026-07-08
Root cause: Content-Disposition filename regex matched the RFC 5987 filename*= form and captured the charset token 'UTF-8'; in batch runs every torrent shared that name and overwrote the previous one (data loss). Core regex fix was already committed in c3257c02 but the ledger was never updated.
Fix: Parsing extracted into _filename_from_content_disposition(): plain filename= preferred; filename*= handled per RFC 5987 (strip charset''lang'', percent-decode with the declared charset); attach-id/LB fallback when neither usable. 11 new unit tests in tests/test_wtrf_scraper.py, all passing.

BUG-217: Incremental crawler does not pick up new LB website pages when posted
Status: Fixed
File(s): backend/site_crawler.py, backend/db.py
Reported: 2026-06-22
Fixed: 2026-06-26
Root cause: crawl() pre-populated `visited` from get_downloaded_urls() — all URLs with
  status 'downloaded'/'not_found'/'skipped'. _seed() skips URLs already in `visited`,
  so SEED_URLS (including /bynumber/LBMbynumber.html, the master LB index) were never
  re-queued after their initial download. The If-Modified-Since logic was present but
  dead for already-downloaded pages; the queue only ever contained status='pending'/'failed'
  URLs, which are empty after a successful full crawl. Result: no index page was ever
  re-fetched incrementally, so newly posted LB detail pages linked from the index were
  never discovered.
Fix: Before queuing, temporarily remove SEED_URLS + start_url from `visited` so _seed()
  re-queues them every run. Load their stored last_modified from site_inventory into
  lm_map so If-Modified-Since is sent — a 304 means nothing changed (cheap), a 200 means
  the index changed and new links are extracted and queued. Added get_inventory_last_modified()
  to backend/db.py to support the targeted last_modified lookup.

BUG-214: Library — family label slot conflates source type with TapeMatch match group
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx:1251-1263, 1880-1889
Reported: 2026-06-19
Fixed: 2026-06-19
Root cause: familiesOf() rendered a single bold label per family row using
  `famLabel || sourceType` — famLabel is TapeMatch's match-group name ("Solo",
  "Family A", "Family B"...), only present once TapeMatch has processed that
  date; sourceType is the tape's source ("Audience", "Soundboard"...). Two
  unrelated dimensions sharing one text slot meant sibling rows for the same
  AUD-source date could read "Solo" or "Audience" with no visual cue that
  these aren't parallel categories — confusing in the UI (reported via
  screenshot of McCarter Theater 1990-01-15 rows).
Fix: label now always shows source type (consistent across every row).
  TapeMatch's match-group name moved to its own `tmLabel` field, rendered as
  a separate info-toned Pill badge next to the source pill, with a tooltip
  clarifying it's a TapeMatch acoustic match group.
Follow-up (2026-06-19): the spelled-out source label (e.g. "Audience") was
  itself 100% redundant with the existing AUD/SBD/etc. source pill once the
  fix above made it always derive from the same `fam.src` value (reported via
  a second screenshot showing "AUD" + "Audience" side by side on every row).
  Removed the FamilyGroup.label field and its rendered span entirely — the
  source pill alone now carries that information; tmLabel badge unaffected.

BUG-213: Library — TapeMatch singletons appear as orphan "Recording LB-XXXXX" rows
Status: Fixed
File(s): backend/tapematch_sync.py:136
Reported: 2026-06-19
Fixed: 2026-06-19
Root cause: _sync_one_date filtered out any TapeMatch family with only 1 member (len >= 2 guard).
  Recordings TapeMatch analyzed and found acoustically distinct from all siblings on the same date
  were silently excluded from recording_families, so the frontend had no fam assignment for them
  and fell through to the "Recording" label fallback in familiesOf().
Fix: Extract singletons after the >= 2 filter; sync them into recording_families and
  tapematch_family_meta with label='Solo', by='ai'. Frontend already handles single-member
  families correctly — they now render as "└ Solo LB-XXXXX" at family level.

BUG-208: Pipeline — "File all" and explicit filing bypass a pending rename
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1376-1377 (fileableRows/selectedFileable), 1679 (applyFile), 993 (CollectReadyDetail)
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: fileableRows and selectedFileable only checked file.status==='warn' and dest; a folder
  with a pending rename (rename.status==='warn' && proposed set) could be included and silently
  filed under its old name. applyFile had no guard either. CollectReadyDetail also lacked a
  useTranslation() call, causing t() to be undefined when step.owned && existing_disk_path
  (latent crash from BUG-204 fix).
Fix: Exclude rename-pending rows from fileableRows and selectedFileable. Add early-return guard in
  applyFile with toast. Add useTranslation() + renamePending banner + disabled File button in
  CollectReadyDetail. Added 3 i18n keys (pipeline.file.renamePending,
  pipeline.collect.renamePendingTitle/Body) to all 6 locales.

BUG-205: Pipeline — filing creates duplicate visible rows; row stays in running section after completion
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1369,1393,1376-1377,1760
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: shelfVis filter did not exclude running rows, so a row being filed (bucket='shelf', running=true)
  appeared in both the Running section AND the Shelf section simultaneously. Also: counts.shelf and
  fileableRows included running rows, inflating counts during filing. _pipelineCache not updated on
  successful filing meant a component remount would restore the row as "ready to file."
Fix: Added !r.running to shelfVis, counts.shelf, fileableRows, selectedFileable. Updated _pipelineCache
  inside the success setRows callback after filing completes.

BUG-204: Pipeline — filing a folder already in collection at a different path silently loses the new path
Status: Fixed
File(s): backend/filer.py:534-550, backend/app.py:5684-5687, gui_next/src/renderer/src/screens/ScreenPipeline.tsx
Reported: 2026-06-17
Fixed: 2026-06-18
Root cause: add_to_collection uses INSERT OR IGNORE; lb_number has a UNIQUE constraint in
  my_collection, so if the lb was already registered at any path, the INSERT silently did
  nothing. The folder was physically moved to the new location but the collection record
  still pointed to the old (now missing) path. No warning was shown before filing.
Fix: filer.py _run(): after filesystem op succeeds, check for an existing my_collection row
  by lb_number; if found, call update_collection(folder_name, disk_path) to update the
  path instead of relying on INSERT OR IGNORE. app.py file-step: query disk_path alongside
  lbdir_verified_at and include existing_disk_path in the step result. Frontend: when
  owned=true and existing_disk_path is set, show a warn banner before the File button
  explaining that the collection record will be updated. All 6 locale files updated.

BUG-203: Pipeline — shelving a folder leaves the File button visible and item counts in "File all"
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: Shelving only changed `bucket` to 'shelf', but 'shelf' is also the natural "ready to file"
  state. So a shelved folder still satisfied the File button condition (file.status==='warn' && dest set)
  and was still included in fileableRows / counts.shelf used by "File all N".
Fix: Added `shelved: boolean` flag to PipelineRow. Shelve sets it; unshelve clears it and restores the
  correct bucket (shelf if steps are all done, needs otherwise). File button, fileableRows,
  selectedFileable, and counts.shelf all exclude shelved rows. deriveFolderStatus returns "Shelved /
  Deferred" when shelved flag is set.

BUG-202: Pipeline — blocked folders show "Needs you" in sidebar panel; File button visible on blocked rows
Status: Fixed
File(s): gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx:256-289
         gui_next/src/renderer/src/screens/ScreenPipeline.tsx:2378
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: QueueRow in PipelineParts always used BUCKET[folder.bucket].label; since all "bad"
  severity folders land in bucket "needs", they showed "Needs you" not "Blocked". Separately,
  the File button in the main table row checked only file.status === 'warn' without verifying
  that upstream steps are not blocked.
Fix: QueueRow now checks if any step has state 'blocked' and overrides tone+label to bad/Blocked.
  File button condition extended to exclude rows where any of verify/lookup/lbdir/rename is bad.

BUG-195: Pipeline — incomplete-match folders (FFP-only) show yellow LBDIR/rename/file and allow action
Status: Fixed
File(s): backend/app.py:5535-5556, gui_next/src/renderer/src/screens/ScreenPipeline.tsx:688,761-785
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: When lookup resolved an LB# from a partial checksum match (e.g. FFP matched but
  MD5 did not), the local lb_number variable stayed set. Downstream steps (lbdir, rename, file)
  all gate on lb_number being non-null, so they ran and showed actionable UI even though the
  files on disk hadn't been confirmed against the archive. The frontend warn+lb_number branch
  also showed no pin option, so there was no recovery path.
Fix: Backend clears lb_number for downstream steps after an incomplete-match lookup unless
  pinned_lb is set (user explicitly confirmed the folder via "Pin & continue"). Frontend:
  warn+lb_number branch now passes onPin/pinBusyLb to LookupDetail and explains the block.
  handlePin now runs all downstream steps (lookup/lbdir/rename/file) after pinning, not
  just re-lookup.

BUG-193: Scraper — new shows not discovered; hardcoded sitemap list misses dynamic sitemaps
Status: Fixed
File(s): backend/bobdylan_scraper.py:32-36, 123-149
Reported: 2026-06-15
Fixed: 2026-06-15
NOTE: duplicate id — an older, unrelated BUG-193 (importer ProgrammingError) also exists in
  this file; renumbering is pending the TODO-209 dedup pass.
Root cause: _SITEMAP_URLS was hardcoded to 3 URLs. WordPress generates date sitemaps
  dynamically; as the site grows past 2000 entries a new numbered file appears. Sitemaps 2
  and 3 returned 404 (silent in _fetch), so only sitemap 1 was used. New shows landing in
  sitemap 2+ were never discovered and therefore never scraped.
Fix: Added _get_date_sitemap_urls() which fetches wp-sitemap.xml (the WP sitemap index)
  and extracts all posts-date sitemaps dynamically. Falls back to _SITEMAP_URLS_FALLBACK
  if the index is unavailable. Also added WARNING log for 404 responses in _fetch so
  future silent failures are visible.

BUG-223: tapematch analysis.md attribution line is hardcoded, not the real model
Status: Fixed
File(s): .claude/commands/tapematch-batch.md:4, data/tapematch/runs/*/analysis.md
Reported: 2026-06-24
Fixed: 2026-06-24
Root cause: The tapematch-batch skill (step 4) instructed every session to write the literal
  string `*Claude claude-sonnet-4-6 — …*` regardless of which model actually ran. gen_analysis.py
  also hardcodes MODEL = "claude-sonnet-4-6". As a result the attribution in all analysis.md files
  reflects nothing about the writing model. Session-transcript cross-reference proved 10 analyses
  (1989-08-29, 1989-08-31, 1989-11-02, 1990-06-29, 1990-06-30, 1990-07-07, 1990-07-08, 1990-08-12,
  1990-08-20, 1990-09-05) were actually written by claude-haiku-4-5 but stamped sonnet. (10 other
  files were correctly self-stamped claude-opus-4-8 from a real opus session.)
Fix: Skill step 4 now requires the actual running session model id (no fixed string). The 10
  mislabeled haiku files corrected to `*Claude claude-haiku-4-5 — …*`. The remaining ~690 analyses
  were confirmed by the user to have been written by sonnet, so their existing label is correct.
  Final on-disk attribution: 690 sonnet, 10 haiku, 10 opus. gen_analysis.py still hardcodes MODEL
  — left for a follow-up if that path is reused.

BUG-244: Re-pinning a folder to a different LB keeps the old pin, which wins lookups
Status: Fixed
File(s): backend/db.py:5029,backend/app.py:4981,tests/test_db_writes.py:1347
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: The folder_lb_link composite-PK migration made set_folder_link additive (INSERT OR IGNORE) for the multi-LB auto-link flow, but PUT /api/folder_link (Pin & continue, documented 'Set or replace') kept calling it. A re-pin therefore accumulated rows, and since get_folder_link/pinned_lbs[0] take the lowest lb_number, the OLD pin silently won whenever the new LB was higher. Surfaced by stale test test_replace_existing failing on main.
Fix: New db.replace_folder_link() does DELETE+INSERT atomically in one write-queue transaction; the PUT endpoint uses it. Tests updated: test_set_is_additive covers the auto-link semantics, test_replace_existing covers re-pin. Full suite 435 passed / 0 failed.

BUG-243: db_queue async write failures are completely silent
Status: Fixed
File(s): backend/db_queue.py:113
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: execute_async's docstring claimed failures are logged at DEBUG inside the writer thread, but _run never logged them — a failed fire-and-forget write left no trace anywhere (currently zero call sites, but a booby trap for the first user).
Fix: Writer thread now logs async failures at WARNING with traceback when no caller is waiting; docstring corrected. Verified by repro: failure logged, queue survives and serves subsequent writes.

BUG-242: Flat-file import silently drops malformed rows
Status: Fixed
File(s): backend/importer.py:84
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: _import_flat_file wrapped each INSERT in except Exception: pass with no counter or log, so unparseable rows (bad int, short lines) vanished — the import reported clean success with checksums missing.
Fix: Skipped rows are counted (short lines included), first 5 logged with line numbers at WARNING, and a summary warning logged when any were skipped; except narrowed to (ValueError, sqlite3.Error). Verified by repro: 3 inserted / 2 skipped with warnings.

BUG-241: App quit orphans backend child processes (ffmpeg/sox/shntool) on Linux/macOS
Status: Fixed
File(s): gui_next/src/main/index.ts:38
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: killProcessTree() only tree-kills on Windows (taskkill /T); the POSIX branch plain-SIGTERMed the one PID, so the backend's spawned ffmpeg/sox/shntool workers were reparented and kept running after app quit — the exact orphan problem the function's own comment says it prevents.
Fix: Backend is now spawned detached on POSIX (own process group, pgid==pid) and killProcessTree signals the group via kill(-pid) with single-pid fallback; killPortProcess routes through killProcessTree too. Verified by node repro (grandchild survives current pattern, dies with fix); gui-check node types + build PASS.

BUG-240: Scheduled integrity scans fire hours late: UTC started_at compared to local now()
Status: Fixed
File(s): backend/scheduler.py:196
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: collection_integrity_scans.started_at is written by SQLite CURRENT_TIMESTAMP (UTC wall time, no offset marker); the scheduler parsed it naive and subtracted from local datetime.now(). On this CDT machine a just-started scan read as -5h elapsed, so every scheduled scan fired 5 hours late (east of UTC it would re-fire early).
Fix: started_at is parsed then tagged UTC when naive, and compared against datetime.now(UTC). Verified by repro: just-started scan now reads ~0 elapsed.

BUG-239: list_shares drops expired shares without persist or tunnel stop
Status: Fixed
File(s): backend/sharing.py:162
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: list_shares popped expired shares straight out of _active_shares instead of routing through revoke_share, so _persist() never ran (stale state file) and stop_cloudflare_tunnel() never fired — once the last share expired via this path the cloudflared tunnel ran forever with zero shares.
Fix: Expired tokens are collected under the lock and revoked via revoke_share() after release, matching the reaper. Verified by repro: _persist and stop_cloudflare_tunnel now both fire.

BUG-238: Share-expiry reaper thread dies permanently on first exception
Status: Fixed
File(s): backend/sharing.py:336
Reported: 2026-07-07
Fixed: 2026-07-07
Root cause: _reaper_loop ran without any exception guard; the thread is started once at import with no restart path, so a single ValueError/KeyError (corrupt expires_at) or OSError escaping revoke_share()->_persist() (whose mkdir sat outside its try) killed share expiry for the whole session — expired shares kept serving files over the public tunnel until restart.
Fix: Loop body wrapped in try/except with log.exception; shares with invalid expires_at are now reaped instead of fatal; _persist()'s mkdir moved inside its best-effort try. Verified by repro: thread survives malformed share and revokes it.

BUG-237: emb_fullset_eval.py acceptance check stale after Rule D ship (false MISMATCH,
  sweep self-declared untrustworthy)
Status: Fixed
File(s): tools/tapematch/emb_fullset_eval.py:356 (_acceptance_check)
Reported: 2026-07-05
Fixed: 2026-07-05
Root cause: The sweep's no-injection baseline is deliberately the pre-Rule-D system
  (candidate rules REPLACE Rule D so flip counts stay comparable with the shipped +25),
  but the startup acceptance check reproduced the reference via
  regression._candidate_verdicts_for_date with the committed config — which, since the
  2026-07-04 Rule D ship, unions passthrough verdicts with rule_d fires
  (_passthrough_with_rule_d). Guaranteed 25-TP mismatch on every post-ship run, flagging
  all numbers untrustworthy (first hit: TODO-202 12x densification sweep).
Fix: Acceptance reference now runs with a rule_d-disabled deep copy of the committed
  config; identity re-proven exactly (tp=659 fn=916 fp=9 tn=1381 v1 / tp=662 fp=6 v2,
  independently confirmed via regression.py score --cached --config <rule_d off>). The
  shipped rule_d-on confusion is printed alongside with the derived ship bar. Module +
  function docstrings document the replacement framing.

BUG-235: tapematch performance_envelope trim spuriously cuts 30-70% of a recording on
  heavily-compressed/normalised sources
Status: Fixed
File(s): tools/tapematch/tapematch/trim.py:51 (performance_envelope), config.yaml (trim block)
Reported: 2026-07-03
Fixed: 2026-07-03
Root cause: performance_envelope's is_music mask is (flatness < 0.45) AND (energy > p10+6dB).
  Live diagnosis (2025-11-16/17 Glasgow entries) showed flatness NEVER exceeds ~0.15 on any
  real recording tested (including known-good control dates) -- the flatness term is dead
  weight in practice, so the whole music/crowd decision rides on the fixed p10+6dB energy
  gate alone. Known-good controls (1996-07-21, 1990-06-01) have a clean ~12-15dB energy
  contrast (p90-p10) between crowd padding and performance, giving long sustained is_music
  runs. Several 2025-11-16/17 Glasgow sources (LB-16526, LB-16545, LB-16525) had that
  contrast compressed to 6.4-8.5dB (heavy loudness normalisation/limiting on the release),
  so the energy signal chattered in/out of the gate roughly every 1-3 seconds instead of
  forming 8+ second sustained blocks. _first_sustained then locked onto whichever tiny
  lucky run happened to appear first/last, producing head/tail cuts of 28-75 minutes on
  ~1:44 recordings -- LB-16526/LB-16545 on 2025-11-17 were both cut to a 20-second
  "performance" window. Every downstream signal (anchors, primary correlation, secondary
  match) then ran on that near-empty window, corrupting the session's clustering verdict.
Fix: Added a dynamic-range guard: if the whole-recording energy spread (p90-p10) is below
  a new `trim.min_dynamic_range_db` (10.0, calibrated against 5 known-good control sources
  at 11.9-15.4dB vs. 4 broken sources at 6.4-8.5dB), performance_envelope skips trimming
  and returns the full recording -- reusing the function's existing safe-fallback path
  (previously only reached when no sustained region was found at all) rather than trusting
  a coin-flip trim. Unit tests added: tools/tapematch/tests/test_trim.py (wide-range trims
  normally, narrow-range skips trim, boundary case just above threshold still trims).
  Verified live: re-running 2025-11-17 and 2025-11-16 post-fix, all 6 sources now keep their
  full ~1:44 length (0:00 head/tail trim on the previously-broken ones); 2025-11-16's known
  same-source pair (LB-16525/LB-16544) went from a fragile fingerprint-only merge (Dice
  0.455, mean intra-corr 0.005, low confidence) to a strong primary-correlation merge
  (0.924, high confidence) -- same correct verdict, now on solid evidence instead of a
  score sitting in the ambiguous same-show band.

BUG-234: Checksum body-search false-matched 3 different shows to the same WTRF topic
Status: Wontfix (not a bug — verified correct match)
File(s): backend/wtrf_scraper.py (checksum body-search / candidate scoring)
Reported: 2026-07-01
Fixed: 2026-07-02
Root cause: Not a defect. Logged into WTRF and fetched topic=55005 directly: it is
  "Garden Party" Outlaw Tour 2025, Crystal Cat 1174-1176 — a single torrent/post that
  legitimately bundles THREE shows as CD1/CD2/CD3 (Phoenix AZ 5/13/25, Chula Vista CA
  5/15/25, George WA 5/25/25), each with its own per-track FFP/MD5 checksums in the
  post body. LB-16404/16405/16406 each carry the checksums for exactly one CD of that
  boxset, so each entry's own md5/filename hits against the shared post body are
  genuine, not a collision — this is the same "multiple LB entries, one WTRF post"
  situation already known-good for LB-16308/LB-16340 (BUGS.md originally), just
  generalized from a duplicate-catalog-entry case to a multi-show box-set release.
Fix: No matching-logic change needed. find_torrent_for_lb() already handles this
  correctly by scoring each LB entry's own checksums independently per call — no
  cross-entry state prevents two (or three) entries from resolving to the same topic
  when that's actually correct. Closed as Wontfix; original report's "at most one
  match is correct" assumption was wrong for box-set releases. However, this case did
  expose a real download-naming gap: since all three entries share one physical
  .torrent, _download_torrent's Content-Disposition filename (post-BUG-233 fix) was
  identical across entries and would still overwrite on disk. Fixed alongside BUG-233
  by prefixing every downloaded filename with `LB-{lb_number:05d}-`, so each entry's
  copy persists independently even when multiple entries share one torrent.

BUG-232: WTRF matcher never finds the correct post when a different taper titles the show differently
Status: Fixed
File(s): backend/wtrf_scraper.py (_search_board, _checksum_search_terms, find_torrent_for_lb)
Reported: 2026-07-01
Fixed: 2026-07-01
Root cause: The WTRF forum search was (1) subject-only, so a post was only found when its topic
  TITLE contained a recognised date-string variant, and (2) the date-variant loop broke at the
  first variant that returned any results. When a show has multiple tapers whose topics use
  different title formats (e.g. "bd2026-05-01 Abilene…" vs "Up To Me / Abilene - May 1, 2026"),
  the ISO variant matched the other tapers' posts first and the loop stopped, so the entry's own
  post — titled with a long-month date — was never fetched. Example: LB-16644 (nightly moth,
  Abilene 2026-05-01) was reported "ambiguous" between LB-16616 (BenM) and LB-16617 (soomlos)
  posts while its real post (topic 60289, blindwilly/nightlymoth) went unseen.
Fix: Added a deterministic Phase-1 checksum body-search: WTRF full-text search indexes the raw
  MD5/SHA1 hash in the post body, and a track hash is unique to one recording, so searching for
  the entry's own checksum lands directly on the correct taper's post regardless of title format
  (`_search_board` gained a `subject_only` flag; `_checksum_search_terms` picks up to 3 hashes).
  Date-variant subject search is now the fallback and unions candidates across ALL variants
  instead of breaking early. LB-16644 now resolves definitively to topic 60289.

BUG-231: WTRF matcher reports false "ambiguous" tie between other tapers' posts
Status: Fixed
File(s): backend/wtrf_scraper.py (_score loop in find_torrent_for_lb), backend/db.py
  (lookup_checksum_owners)
Reported: 2026-07-01
Fixed: 2026-07-01
Root cause: When an entry had no forum post of its own, the scorer would tie two OTHER tapers'
  posts of the same show at score=5 (torrent present + matching date, no distinguishing signal)
  and return "ambiguous — manual review required". Those posts' checksums provably belong to
  different LB entries, but the matcher only hard-disqualified a candidate carrying an explicit
  "LB-NNNNN" tag, which legacy posts lack. Example: LB-16644's two "tied" candidates were the
  BenM (LB-16616) and soomlos (LB-16617) tapings — neither is LB-16644.
Fix: Added a cross-recording guard: any candidate whose body MD5/SHA1 checksums resolve to a
  different lb_number (via new db.lookup_checksum_owners) is disqualified — it documents that
  other recording. Only applies when none of THIS entry's checksums matched (a positive match
  already proves ownership). Turns the false "ambiguous" into a correct "not_found" for the
  fallback path and prevents downloading the wrong taper's torrent.

BUG-218: Performance screen — column widths wrong/misaligned
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx:1849-2126 (performance-view table)
Reported: 2026-06-22
Fixed: 2026-07-01
Root cause: Original report never specified the exact symptom (which column, too narrow/wide/
  misaligned) and cited line numbers (1541, 1768-1777) that no longer match the file. On review,
  the performance (date-row) table's column model at its current location is internally
  consistent: colgroup defines 10 `<col>`s (edge/expand/date/show/tour/families/recs/★/coverage/
  flex-spacer), and the header row, "show" rows, "fam" rows, and "member" rows each sum to exactly
  10 cells once TR's auto-injected 3px edge `<td>` and the colSpans used in fam/member rows are
  accounted for. The table appears to have already been reworked under a "Column model (spec §5)"
  comment at line 1849 sometime after this bug was filed.
Fix: Confirmed fixed by user; no further code change required. Closed as already resolved by a
  prior unrelated pass.

BUG-201: Pipeline screen — extensive untranslated English when non-English locale is active
Status: Fixed
File(s): gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx
         gui_next/src/renderer/src/components/pipeline/lookupState.ts
         gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx
         gui_next/src/renderer/src/screens/ScreenPipeline.tsx (throughout)
         gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json
Reported: 2026-06-17
Fixed: 2026-07-01
Root cause: Three distinct gaps: (1) DEFAULT_STAGES (PipelineParts.tsx) hard-coded English stage
  labels used by the pipeline stepper/tracker, never wired to i18n despite matching
  `pipeline.queue.*` locale keys already existing unused. (2) STATE_TONE (lookupState.ts)
  hard-coded lookup-state pill labels (Matched/Incomplete/Not found/Duplicate/XRef). (3)
  ScreenPipeline.tsx had ~110 hard-coded English inline strings (button labels, banner
  titles/bodies, guidance text, table headers/row actions, context menu) with no i18n key,
  including two frontend-owned lookup maps (STATE_LABEL for LBDIR status pills, ERROR_MSG for
  file-stage errors) keyed by stable backend enum codes but with hardcoded English values.
Fix: Converted STATE/BUCKET (PipelineParts.tsx), STATE_TONE (lookupState.ts), STATE_LABEL and
  ERROR_MSG (ScreenPipeline.tsx) to store `labelKey` locale-key references resolved via `t()` at
  each render site (all consuming components already are, or were made, function components with
  hook access; `deriveFolderStatus()` now takes a `TFunction` param since it's a plain function).
  DEFAULT_STAGES reuses the pre-existing `pipeline.queue.{verify,lookup,lbdir,rename,collect}`
  keys. Systematic pass through ScreenPipeline.tsx replaced every remaining hard-coded string with
  `t()` + ~120 new keys added under `pipeline.*` in en.json, then translated to all 5 other
  locales via `deepl_translate_gui_next.py` (with a handful of ambiguous single words —
  pipeline.buckets.shelf, pipeline.contextMenu.shelve/unshelve — hand-corrected where DeepL left
  them as English in most languages). `tsc -b tsconfig.web.json --noEmit` and `electron-vite
  build` both clean; the 3 residual tsc errors touching files this fix modified (Pill `title`
  prop, IconButton `disabled` prop, `shiftKey` on ChangeEvent) all predate this change. Backend-
  returned free-text `step.label`/`step.error` values (genuinely dynamic, embed counts/filenames/
  mount names server-side) intentionally left in English per user decision — tracked as TODO-195
  for a future backend i18n-plumbing pass.

BUG-215: Map screen renders white/blank — no map shown in app
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenMap.tsx:63, gui_next/src/renderer/src/locales/*.json
Reported: 2026-06-22
Fixed: 2026-07-01
Root cause: MAP_URL hardcoded `http://localhost:5174/map` for the live-map iframe's src, but
  index.html's CSP frame-src/connect-src/img-src directives only allowlist
  `http://127.0.0.1:5174` (the convention window.api.flaskBase and every other screen uses).
  CSP treats localhost and 127.0.0.1 as distinct origins, so the browser silently blocked the
  iframe navigation entirely, leaving the Map screen blank/white with no console-visible error
  in the app itself (only a CSP violation report).
Fix: Changed MAP_URL to `${window.api.flaskBase}/map` so the iframe origin matches the CSP
  allowlist. Updated the map.desc locale string in all 6 locale files (en/de/fr/es/nl/it) from
  "localhost:5174/map" to "127.0.0.1:5174/map" to match.

BUG-219: Search/filter state lost when navigating away from a screen and back
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx (new useLibraryFilterStore +
  ScreenLibrary/PerformanceLensView filter state), gui_next/src/renderer/src/App.tsx:265-285
Reported: 2026-06-22
Fixed: 2026-07-01
Root cause: App.tsx renders each screen behind a react-router <Route>, which unmounts the
  component when navigating to a different route. Search/filter values (`query` and the
  `active*` filter Sets in ScreenLibrary.tsx, plus the same pattern duplicated in its
  PerformanceLensView child component for the performance lens) were plain local useState, so
  they reset to default the moment the screen unmounts — navigating away and back lost whatever
  filter/search was applied.
Fix: Added a module-scope `useLibraryFilterStore` (zustand, no persist middleware — survives
  route changes within a session, matching the other ephemeral UI stores in lib/*Store.ts, e.g.
  useFolderQueueStore) and swapped both lenses' filter useState calls for it: recording lens
  (scope/query/activeDecade/activeStatus/activeRating/activeSource/activeHealth) and performance
  lens (query/activeDecade/activeYear/activeCoverage/activeSource/activeRating/perfView). Store
  setters mirror React's `Dispatch<SetStateAction<T>>` signature so existing toggleSet()/
  setX(new Set()) call sites needed no changes. View/selection-only state (groupByYear,
  sortKey/sortDir, selectedLb, detailPanelOpen, checkedIds, expandedShows, collapsedFams, etc.)
  intentionally left as local useState — out of scope for a search/filter bug. Considered
  reusing the existing `KeepAlivePipeline` always-mounted (CSS display:none) pattern from
  App.tsx instead, but that would keep Library's heavy virtualized table + queries running even
  when off-screen; the store-only fix is more proportionate to the actual symptom. `tsc --noEmit`
  clean for the changed file (pre-existing unrelated errors remain in other files, unchanged by
  this fix). Root cause note that this pattern "likely affects other screens" too was not
  chased further — out of scope, no other screen was named in the bug report.

BUG-220: LB metadata scraper-by-range excludes start/end LB numbers that have no checksum entry yet
Status: Fixed
File(s): backend/app.py:1782-1849 (scrape_start)
Reported: 2026-06-22
Fixed: 2026-07-01
Root cause: scrape_start builds the scrape list lb_numbers from
  "SELECT DISTINCT c.lb_number FROM checksums c ... WHERE c.lb_number >= start_lb AND <= end_lb"
  — only LB numbers that already have a checksums row are included. Gaps within
  [start_lb, effective_end] are detected afterward and given an insert_missing_entry()
  placeholder row, but those gap LB numbers (which may include the start_lb/end_lb the user
  typed in) were never added to lb_numbers, so _start_scrape_thread never actually scraped them
  — they just sat as "missing" stubs. User-specified start/end LB boundaries could silently be
  skipped if no checksum existed for them yet.
Fix: Gap numbers are now appended to lb_numbers (list re-sorted) right after the
  insert_missing_entry() stub, so they're queued into the scrape thread like any other LB.
  Gap numbers whose lb_master.lb_status is 'private' are excluded from queuing (checked via a
  single batched query), preserving the route's documented "excludes private LBs" contract —
  scrape_entry's existing handling of entries.status='missing' (always re-checks on live
  scrapes) already does the right thing once these numbers reach it, so no scraper.py change
  was needed. Verified via an isolated temp-DB simulation (gaps queued + stubbed, private gap
  excluded, existing checksum'd numbers untouched); no pre-existing test coverage for this route.

BUG-221: "Open LB page" link doesn't work in some locations — inconsistent URL construction
Status: Fixed
File(s): gui_next/src/renderer/src/lib/lbUrl.ts (new),
         gui_next/src/renderer/src/components/library/DetailPanel.tsx:660,
         gui_next/src/renderer/src/screens/ScreenLibrary.tsx:366,
         gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx:78,
         gui_next/src/renderer/src/screens/ScreenSearch.tsx:1538,
         gui_next/src/renderer/src/screens/ScreenCollection.tsx:2479
Reported: 2026-06-22
Fixed: 2026-07-01
Root cause: 5 separate call sites built the same losslessbob.wonderingwhattochoose.com
  detail-page URL inline with two different, inconsistent formats — 3 sites zero-padded
  and prefixed "LB-" themselves; DetailPanel.tsx/ScreenLibrary.tsx instead interpolated
  `row.lb` directly, which 404s wherever `row.lb` isn't already a zero-padded "LB-NNNNN"
  string.
Fix: Added `lbDetailUrl(lb: number | string): string` (gui_next/src/renderer/src/lib/lbUrl.ts) —
  strips any existing "LB-" prefix, zero-pads to 5 digits, and rebuilds the full detail URL.
  All 5 call sites now use it instead of duplicating the URL string inline; DetailPanel.tsx
  and ScreenLibrary.tsx switched from `row.lb` to `row.lbNumber` (the raw number already on
  `ActionRow`) so the helper always receives a consistent input regardless of caller.

BUG-229: LBDIR reconcile/move-extras file moves never resynced qBittorrent, breaking seeding
Status: Fixed
File(s): backend/qbittorrent.py:rename_file, backend/qbittorrent.py:sync_file_renames,
  backend/filer.py:_sync_qbt_file_renames, backend/app.py:lbdir_apply_reconcile,
  backend/app.py:lbdir_move_extras, backend/app.py:_resolve_lb_number_for_folder
Reported: 2026-06-30
Fixed: 2026-06-30
Root cause: This is the actual gap the user meant by "the reconcile function on the lbdir
  screen that can rename files and move them to a subfolder" — distinct from BUG-228 (which
  covered the whole root folder being renamed/moved). The LBDIR screen's "Reconcile Files"
  action (`/api/lbdir/apply_reconcile`) renames individual files in place to match the lbdir
  manifest, and "move extras" (`/api/lbdir/move_extras`) relocates stray files into
  `<folder>/extras/` — both change file paths *inside* a folder whose root path never moves.
  qBittorrent tracks each file's path within a torrent independently of the root folder, so a
  same-folder file rename/move it wasn't told about leaves that file "missing" and stalls
  seeding for it — BUG-228's `relocate_tracked_torrent()`/`rename_torrent_root()` machinery
  never fires here since it only exists to handle the root folder itself moving or being
  renamed (`setLocation`/`renameFolder`); nothing analogous existed for individual files.
Fix: New `rename_file()` in backend/qbittorrent.py (`POST /api/v2/torrents/renameFile`, the
  per-file counterpart to `rename_torrent_root()`'s `renameFolder`) and `sync_file_renames()`
  (resolves the tracked torrent for an unchanged folder path the same way
  `relocate_tracked_torrent()` does — DB-tracked row first, `find_torrent_by_path()` fallback —
  applies each rename via `rename_file()`, then a single recheck). New
  `_sync_qbt_file_renames()` credential-loading wrapper in backend/filer.py, mirroring
  `_sync_qbt_location()`. `lbdir_apply_reconcile` and `lbdir_move_extras` call it after
  successfully applying file changes on disk, using a new shared `_resolve_lb_number_for_folder()`
  helper (my_collection row, else `LB-NNNNN` in the folder name, else a folder_lb_link pin) to
  find the relevant lb_number.

BUG-228: Renaming a folder never resynced qBittorrent, breaking seeding
Status: Fixed
File(s): backend/app.py:rename_apply, backend/app.py:folder_rename, backend/qbittorrent.py:relocate_tracked_torrent
Reported: 2026-06-30
Fixed: 2026-06-30
Root cause: The "file" pipeline step (backend/filer.py:start_file_job) already synced
  qBittorrent's save path/root folder name after a move via _sync_qbt_location() ->
  relocate_tracked_torrent(), including recovering from an earlier untracked rename via the
  rename_history table. But the two rename-only endpoints — /api/rename/apply and
  /api/folder/rename — did the filesystem rename and logged rename_history without ever
  calling into qBittorrent at all. A torrent already tracked in qBittorrent
  (torrents.added_to_qbt=1) for an already-filed item would keep expecting the pre-rename
  folder name/location indefinitely, showing missing files and dropping out of seeding, unless
  a later "file" step happened to run and its fallback recovery path stumbled onto the fix.
  Separately, relocate_tracked_torrent()'s DB-tracked branch (an existing torrents row already
  matching lb_number+source_folder) only called set_location() and never rename_torrent_root()
  or recheck_torrent() — only the fallback (untracked) branch did the full sequence — so even a
  rename it was told about would leave qBittorrent's root folder name stale.
Fix: Both rename endpoints now call backend.filer._sync_qbt_location() (best-effort, non-raising)
  after a successful on-disk rename whenever lb_number is known — rename_apply uses the
  lb_number already sent per-item by ScreenRename.tsx; folder_rename resolves it from the
  my_collection row synced for BUG-206, falling back to a "Pin & continue" folder_lb_link
  (BUG-212) if the folder hasn't been filed yet. relocate_tracked_torrent()'s DB-tracked branch
  now also calls rename_torrent_root() when the folder name changed and always calls
  recheck_torrent() afterward, matching the fallback branch.

BUG-227: WTRF LB-tag disqualification (BUG-225) missed unpadded/attachment-only tags
Status: Fixed
File(s): backend/wtrf_scraper.py:_score_candidate, _fetch_topic, find_torrent_for_lb
Reported: 2026-06-30
Fixed: 2026-06-30
Root cause: BUG-225 added a Round 0 check that hard-disqualifies a candidate post explicitly
  tagged "LB-NNNNN" for a different entry, but two gaps let a wrong candidate slip through as
  a "low-confidence" match instead of being blocked outright. (1) The tag regex required 3-5
  digits (`lb-0*(\d{3,5})\b`), written to match this app's own zero-padded 5-digit tags —
  but legacy/non-app posts often write the tag unpadded, e.g. "LB-8", which has only 1 digit
  and never matched. (2) The regex only scanned the post body div text; attachment filenames
  (e.g. a torrent literally named "LB-00008.torrent") live in a sibling `div.attachments`
  that `_fetch_topic` never fed into scoring at all. User-confirmed example: WTRF topic
  topic=54221.msg77946 was returned as the sole "low-confidence" candidate for both LB-16632
  and LB-16633 ("Del Mar, CA 7/1/00" duplicates), but the post body plainly reads "LB-8" and
  its attached torrent is named "LB-00008.torrent" — i.e. it documents LB-8, not either
  16000-series entry.
Fix: Widened the tag regex to `lb-0*(\d{1,5})\b` (minimum 1 digit instead of 3) so unpadded
  short numbers are caught. `_fetch_topic` now also collects the visible link text of every
  attachment in the first post into a new `attachment_text` field; `find_torrent_for_lb`
  concatenates it with `body_text` before calling `_score_candidate`, so an LB tag on either
  the body or the attachment filename triggers disqualification. See BUG-225 for the original
  mechanism this extends.

BUG-226: WTRF search queries spaced below the forum's flood-control window
Status: Fixed
File(s): backend/wtrf_scraper.py:_SEARCH_DELAY, find_torrent_for_lb
Reported: 2026-06-30
Fixed: 2026-06-30
Root cause: find_torrent_for_lb() computed search_delay = delay * 1.5, which at the CLI's
  default --delay 2.0 produces 3.0s between action=search2 requests. The module also defined
  an unused _SEARCH_DELAY = 3.0 constant suggesting this was an intentional but wrong value.
  The user confirmed WTRF has a search flood-control timer that rejects/blocks searches issued
  less than 5s apart. Live batch runs (25 highest missing LB numbers) showed a high proportion
  of 'not_found' results with zero candidates returned even for dates that plausibly have a
  post — consistent with searches silently failing flood-control rather than the post not
  existing, since the symptom is indistinguishable from a true empty result in the current
  logging.
Fix: _SEARCH_DELAY raised to 10.0 (user requested a comfortable margin above the 5s minimum).
  find_torrent_for_lb now computes search_delay = max(delay * 1.5, _SEARCH_DELAY), so search
  queries never go below the 10s floor regardless of the --delay argument passed in. Per-page
  fetch delay (_DEFAULT_DELAY = 2.0) is unaffected — only action=search2 calls were implicated.
  Validated with a fresh 25-item batch run combined with the BUG-225 fix: downloaded jumped
  from 5/25 to 8/25, including LB-16627 (previously 'not_found' with zero candidates at the
  3s delay, now matches 'definitive' with ffp_matches=13 at the 10s delay) — direct evidence
  that under-throttled searches were silently swallowing real matches. Prior 'not_found'
  results in wtrf_downloads from before this fix should still be treated as unreliable.

BUG-225: WTRF scraper matches posts tagged for a different LB entry
Status: Fixed
File(s): backend/wtrf_scraper.py:_score_candidate, _classify_confidence, find_torrent_for_lb
Reported: 2026-06-30
Fixed: 2026-06-30
Root cause: _score_candidate only ever added points for positive signals (FFP checksum,
  filename, equipment token, taper name) and never checked whether a candidate post's body
  explicitly identifies a DIFFERENT LB entry. Posts created by this app's own forum_poster.py
  embed an "LB-{lb_number:05d}" link in the metadata header (_build_body), so when search2
  returned a candidate carrying another entry's tag, it competed on the same weak
  date-match/has_torrent floor (score=5) as legitimate candidates, producing false
  'ambiguous'/'needs_review' matches. Live run against the 25 highest missing LB numbers
  found LB-16632 and LB-16633 (both "Del Mar, CA 7/1/00", duplicate source entries) tied
  between two WTRF posts, neither of which was correct — one (topic=48280) was explicitly
  tagged "LB-8834" in its own metadata header.
Fix: _score_candidate now extracts any "lb-NNNNN" tag(s) from the post body first. If the
  entry's own lb_number is tagged, treat as a strong positive signal (score +200,
  classified 'high'). If only OTHER lb_number tag(s) are present, hard-disqualify the
  candidate (skip it entirely in find_torrent_for_lb's scoring loop) rather than letting it
  compete on weak signals. Untagged posts (e.g. legacy pre-app posts) are unaffected and
  still fall through to the existing FFP/filename/equipment/taper rounds.

BUG-211: Diacritic issue — 45 LB entries across 9 cities with dropped diacritics (ü/ö/é) in location
Status: Fixed
File(s): data/site/detail/LB-*.html (45 files), data/losslessbob.db (entries table)
Reported: 2026-06-18
Fixed: 2026-06-26
Root cause: The LB website admin consistently omits diacritics when manually entering location
  data into HTML — e.g. "Dsseldorf" for Düsseldorf, "Malm" for Malmö. This is a data entry
  error, not an encoding bug (LB site is valid UTF-8; characters are simply absent). Scraper
  faithfully captured the typos. Effects: (a) location displayed wrong in app; (b) folder-rename
  proposals use wrong name; (c) FTS searches for the correct name (e.g. "Saarbrücken") miss
  these entries because unicode61 tokenises "Saarbrücken"→"saarbr"+"ucken" but the corrupted
  "Saarbrcken"→"saarbrcken" (one token), so no match. Venue sub-location strings were split on
  comma by the dropped ö — e.g. "Malm, Sweden, Slottsm, llan" for "Malmö, Sweden, Slottsmöllan".
Cities and entries affected:
  Saarbrücken (5): LB12124, 16153, 16154, 16155, 16167
  Düsseldorf (14): LB10133, 11108, 11143, 11256, 11303, 11365, 11555, 12178, 12186, 13307,
    15100, 16115, 16182, 16183
  Nürnberg (4): LB13434, 16145, 16147, 16170
  Tübingen (2): LB11985, 12043
  Göteborg (3): LB11521, 12566, 13053
  Malmö (8): LB04999, 05212, 07579, 07751, 09510, 09715, 12930, 13273
  Montréal (2): LB14964, 15249
  Zürich (6): LB09198, 10088, 14046, 14047, 14452, 14453
  Jönköping (1): LB10977
Fix: Updated entries.location in DB and patched corresponding cached HTML files for all 45
  entries. Complex Malmö cases: LB04999 "Slottsmöllan", LB07579 "Malmö Arena", LB12930
  "Mölleplatsen, Malmö". "Malmo" (phonetic anglicisation) entries left unchanged as they are
  a different data-entry choice, not a truncation. If the LB admin fixes the live site, a fresh
  scrape will update the DB from the server's UTF-8 response.

BUG-222: UI tips show Mac-only "⌘K" shortcut that doesn't work and has no Mac build anyway
Status: Fixed
File(s): gui_next/src/renderer/src/App.tsx:169, gui_next/src/renderer/src/components/AppShell.tsx:648,
         gui_next/src/renderer/src/screens/ScreenHome.tsx:80
Reported: 2026-06-22
Fixed: 2026-06-26
Root cause: Three places hint a "⌘K" quick-jump shortcut, but no keydown listener for 'k'
  exists anywhere in the GUI — the shortcut was never implemented. ⌘ is also the Mac Command
  symbol; this project has no Mac build.
Fix: Removed all ⌘K references. App.tsx dev-card Kbd combo and "Global search" label
  removed; AppShell.tsx search-button kbd-pill span removed; ScreenHome.tsx TIPS array
  dropped the cmd/⌘K entry (now 2 tips instead of 3); render logic updated to match.
  All 6 locale files: tip1 (⌘K) deleted, tip2→tip1, tip3→tip2. Unused Kbd import
  removed from App.tsx.

BUG-217: Incremental crawler does not pick up new LB website pages when posted
Status: Fixed
File(s): backend/site_crawler.py, backend/db.py
Reported: 2026-06-22
Fixed: 2026-06-26
Root cause: crawl() pre-populated `visited` from get_downloaded_urls() — all URLs with
  status 'downloaded'/'not_found'/'skipped'. _seed() skips URLs already in `visited`,
  so SEED_URLS (including /bynumber/LBMbynumber.html, the master LB index) were never
  re-queued after their initial download. The If-Modified-Since logic was present but
  dead for already-downloaded pages; the queue only ever contained status='pending'/'failed'
  URLs, which are empty after a successful full crawl. Result: no index page was ever
  re-fetched incrementally, so newly posted LB detail pages linked from the index were
  never discovered.
Fix: Before queuing, temporarily remove SEED_URLS + start_url from `visited` so _seed()
  re-queues them every run. Load their stored last_modified from site_inventory into
  lm_map so If-Modified-Since is sent — a 304 means nothing changed (cheap), a 200 means
  the index changed and new links are extracted and queued. Added get_inventory_last_modified()
  to backend/db.py to support the targeted last_modified lookup.

BUG-216: Spectrograms no longer generate via the UI
Status: Fixed
File(s): gui_next/src/renderer/src/lib/spectrogramStore.ts,
         gui_next/src/renderer/src/screens/ScreenSpectrograms.tsx
Reported: 2026-06-22
Fixed: 2026-06-26
Root cause: Two bugs. (1) dynRange store default was '-120'; SoX's -z flag requires a positive
  integer (dynamic range in dB) so every file errored out with no PNG produced. (2) The backend
  _spectro_state["errors"] was a list of {file,error} dicts, but the TypeScript GenerateStatus
  interface typed it as number. When SoX failed on every file, the errors list filled with
  objects; React crashed trying to render {genStatus.errors} in JSX → blank screen.
Fix: (1) spectrogramStore default '-120' → '120'; handleGenerate uses Math.abs() + positive
  fallback; UI label "dB floor" → "dB range". (2) backend _spectro_state["errors"] changed to
  int count (0); _do_spectro_batch now passes errors=len(errors) everywhere; error details
  logged via _log.error() instead.

BUG-224: tapematch_session.py's tmp-dir cleanup deletes another concurrent run's in-flight files
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:461-509 (_clean_stale_tmp_dirs, new _tmp_dir_in_use)
Reported: 2026-06-25
Fixed: 2026-06-25
Root cause: _clean_stale_tmp_dirs() unconditionally rmtree'd every tapematch_* dir under
  TMP_BASE (/mnt/DATA0/tmp) before launching each new tapematch.cli subprocess, with no
  check for whether another subprocess -- from this session or a different concurrent
  Claude Code session -- was still using one. Every tapematch.cli invocation shares this
  same hardcoded tmp base regardless of which script launched it (tapematch_session.py or
  the new validate_polarity.py), so two sessions running tapematch_session.py for
  1989-06-04 and 1990-01-12 deleted the in-flight memmaps of a concurrently-running
  validate_polarity.py batch, surfacing as cascading FileNotFoundError crashes
  (1988-08-07, 1988-08-18, 1988-08-20, 1988-08-23, 1988-08-26).
Fix: Added _tmp_dir_in_use(d) -- skips deletion if any file inside the dir was modified in
  the last 10 minutes, or if any running process holds an open file descriptor inside it
  (scans /proc/*/fd; covers memmaps, which keep a duped fd open after the opening Python
  file object closes). _clean_stale_tmp_dirs() now only removes dirs that are both old and
  fd-free. New tests: tools/tapematch/tests/test_clean_stale_tmp_dirs.py.

BUG-218: Library — ★ rating column clipped two-character ratings (A−, B+) to an ellipsis
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx (recording-lens colgroup)
Reported: 2026-06-22
Fixed: 2026-06-22
Root cause: The recording-lens ★ column shipped at a width that, combined with cell padding,
  truncated the rating pill for two-character grades.
Fix: Set the ★ column to the spec/reference width (48px) so A−/B+ pills render in full.
  Fixed in passing during the Unified Library visual refinement (Pixel Spec §6).

BUG-217: Library — summary strip wrapped to two lines and clipped on narrow widths
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx (both lens summary strips)
Reported: 2026-06-22
Fixed: 2026-06-22
Root cause: The summary strip used min-height:36 with flex-wrap:wrap, so on narrow panels it
  wrapped to a second line that the fixed-height container then clipped.
Fix: Changed to height:40 · flex-wrap:nowrap · overflow:hidden with every child white-space:nowrap
  (Pixel Spec §4). Fixed in passing during the Unified Library visual refinement.

BUG-216: Scraper — Range Scrape with Force re-scrape ignores end_lb, scrapes all entries
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenScraper.tsx:439
Reported: 2026-06-21
Fixed: 2026-06-21
Root cause: The "Scrape Range" button was sending an `lb_numbers` array to /api/scrape/start,
  but the backend route /api/scrape/start (app.py:1762) expects `start_lb` and `end_lb` as
  separate integer parameters. The backend route did not recognize the `lb_numbers` parameter,
  so it defaulted to start_lb=1, end_lb=None, causing a query that selected all LB numbers
  with checksums from LB-1 onwards, scraping the entire 15,140-entry collection instead of
  just the specified range.
Fix: Changed ScreenScraper.tsx line 439 to send `start_lb` and `end_lb` as separate integer
  parameters matching the backend route's expected API contract. GUI now correctly queries
  only the specified range, respecting both the lower and upper bounds.

BUG-215: Unified Library — blank family names in performance detail panel
Status: Fixed
File(s): gui_next/src/renderer/src/components/library/DetailPanel.tsx (FamilyCard, FamilyMeter,
  PerfFamily/PerfRecording interfaces); gui_next/src/renderer/src/screens/ScreenLibrary.tsx:2022
Reported: 2026-06-19
Fixed: 2026-06-19
Root cause: FamilyGroup.label was renamed to tmLabel when the source-type pill replaced the inline
  source label, but the detail-panel PerfFamily interface still declared `label` and FamilyCard /
  FamilyMeter still read `fam.label` / `f.label`. The PerformanceDetailPanel call site passed the
  families with `as any`, suppressing the type error, so `fam.label` resolved to undefined at
  runtime and every family card heading + meter tooltip rendered an empty name.
Fix: Aligned PerfFamily with FamilyGroup (label → tmLabel: string | null; removed unused dupes;
  widened PerfRecording.famConf to number | null to match RecordingRow). FamilyCard/FamilyMeter now
  render `tmLabel ?? src ?? 'Recording'`. Removed the `as any` cast so tsc enforces the shape —
  which immediately surfaced the second (FamilyMeter) blank-label site that grep alone had missed.

BUG-212: Pipeline — File blocked after pin-and-continue + rename; must re-pin to unblock
Status: Fixed
File(s): backend/app.py:5892-5939 (folder_rename), backend/db.py:rekey_folder_link
Reported: 2026-06-18
Fixed: 2026-06-19
Root cause: folder_lb_link (the "Pin & continue" sticky link) is keyed on the exact folder
  path. handlePin writes the pin under the pre-rename path. After applyRename physically
  renames the folder, the frontend refreshes only the file step for the new path — but
  _pipeline_process_folder always forces lookup back into that step set, and lookup re-runs
  database.get_folder_links() against the NEW path, finding nothing. For an incomplete-match
  case this falls through to the unpinned branch, which clears lb_number again, so the file
  step goes mute and the File button disappears. Re-pinning from Lookup writes a fresh link
  under the now-current (post-rename) path, which is why a second pin "fixes" it.
Fix: Added database.rekey_folder_link(old_path, new_path) — UPDATE OR IGNORE moves
  folder_lb_link row(s) to the new path, then deletes any row left behind by a primary-key
  conflict (a link already existing under new_path for the same LB#). Wired into
  folder_rename() right next to the existing BUG-206 my_collection disk_path sync, so both
  auxiliary tables stay consistent through a rename in one place. 4 new tests in
  tests/test_db_writes.py::TestFolderLink cover single-link, multi-LB, conflict, and no-op
  cases.

BUG-214: Performance lens — clicking an ungrouped (non-family) recording row does not update DetailPanel
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLibrary.tsx:1823-1837 (fam row onClick)
Reported: 2026-06-19
Fixed: 2026-06-19
Root cause: Every "family" row's onClick called setSelectedId(item.perf.id), selecting the
  parent performance/show rather than the recording. Recordings grouped into a multi-member
  TapeMatch family render separate indented "member" rows with their own onClick that calls
  setSelectedMemberLb(rec.lbNumber), correctly showing the recording-specific panel. But
  recordings with no family grouping render as single-member fam rows (fam.multi === false)
  with no separate member sub-row — clicking them just re-selected the already-selected
  performance, so the right panel never changed.
Fix: fam row onClick now branches on `single` (fam.multi === false): calls
  setSelectedMemberLb(lone.lbNumber) for ungrouped recordings instead of setSelectedId,
  matching member-row behavior. Added matching selected-row highlight
  (var(--lbb-accent-soft)) for the single case.

BUG-209: tapematch run_crawl.sh loops forever on a date with missing sources
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:962-977 (run_date), tools/tapematch/gen_analysis.py
Reported: 2026-06-18
Fixed: 2026-06-18
Root cause: run_date() returned rc=3 for a date with sources missing from disk (and
  --allow-missing not passed) without calling archive_run() or logging to observations.db —
  unlike the analogous rc=2 "only 1 source" path, which does archive. next_run() (backing
  run_crawl.sh's --next loop) recomputes its "done" set from observations.db + RUNS_DIR on
  every invocation, so an unarchived missing-sources date never became "done" and was
  re-selected as the highest-priority todo item every single loop iteration, forever.
Fix: run_date() now writes a report.md marked **missing_sources** and calls archive_run() for
  this case too, mirroring the existing insufficient_sources (rc=2) handling, so the date gets
  a RUNS_DIR folder and is correctly skipped by --next/--year/--crawl on subsequent runs (delete
  the run's archive dir to retry once the missing source appears on disk). gen_analysis.py now
  recognizes the **missing_sources** marker (parse_report/build_analysis/status line) so these
  archived runs get a clean "missing sources" status instead of being misread. Added
  tools/tapematch/tests/test_missing_sources.py covering the parse/build path.

BUG-207: rename_history — pipeline renames log a doubled old_path (folder/folder.name)
Status: Fixed
File(s): backend/rename.py:57-71 (write_rename_log path computation)
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: write_rename_log built old_path as str(folder / old_name). When folder_rename()
  called it with folder_path=folder and old_name=folder.name, this produced
  /parent/FolderName/FolderName — the name doubled.
Fix: Detect the "folder_path is the folder itself" convention (old_name == folder.name) and
  set old_path = str(folder) directly. Also fixed the complementary new_path bug that
  affected the rename_tab call site (parent_dir convention produced new_path one level too high).

BUG-206: Pipeline — auto-rename after filing leaves my_collection with stale folder path
Status: Fixed
File(s): backend/app.py:5802-5813 (folder_rename, after folder.rename())
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: /api/folder/rename renamed the folder on disk and logged the rename but never
  updated my_collection, leaving disk_path and folder_name pointing to the old name.
  Folders opened from Collection screen would fail because the path no longer existed.
Fix: After folder.rename(new_path) succeeds, query my_collection WHERE disk_path = old path;
  if a row is found, call database.update_collection() to sync folder_name and disk_path.
Note: Two affected rows were patched manually on 2026-06-17:
  LB-16388: /mnt/DYLAN2/Concerts/1974/1974-01-19 Hollywood, FL (LB-16388)
  LB-15905: /mnt/DYLAN1/LB HOPPER/2023-11-19 Philadelphia, Pennsylvania (LB-15905)

BUG-200: Pipeline Verify tab shows "no checksums" for disc-subfolder layouts
Status: Fixed
File(s): backend/checksum_utils.py:537
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: verify_folder used folder.iterdir() (top-level only) to find checksum sidecar files.
  Folders with disc subdirectories (disc1/, disc2/ etc.) store checksums inside those subdirs,
  so they were never found and the folder appeared to have no checksums.
Fix: Changed to folder.rglob('*') and when a checksum file is found in a subdirectory, bare
  filenames in its entries are qualified with the subdir prefix (e.g. "song.flac" →
  "disc1/song.flac") so they match the disk_audio_map keys.

BUG-199: tapematch — prep_analysis_input.py misreads truncated LB numbers in report.md commentary, pulls in unrelated info files
Status: Fixed
File(s): tools/tapematch/prep_analysis_input.py:36-76
Reported: 2026-06-17
Fixed: 2026-06-17
Root cause: report.md truncates long commentary/audit snippets with an ellipsis ("…" or
  "..."). When truncation lands mid multi-digit LB number (e.g. "...sennheiser LB-4794…"
  cut to "LB-47…"), lb_numbers_in_report()'s regex (\bLB-(\d+)\b) matched the truncated
  digits as a complete, distinct LB number — "47" zero-padded to "00047" — and pulled in
  that LB's unrelated info file (a 2000-09-23 Cardiff show spliced into the 1998-06-24
  Birmingham bundle). Found while writing tapematch-batch analysis.md entries. A repo-wide
  scan of all 923 run dirs under data/tapematch/runs/ found exactly 2 where this actually
  pulled a wrong file: 20260615_170155_1998-06-24 (→ LB-00047) and 20260616_231225_1990-10-26
  (→ LB-00090). The first already has analysis.md, written with the contamination correctly
  noticed and excluded by the writer rather than used in the verdict; the second had only a
  stale analysis_input.md bundle (no analysis.md yet), now regenerated clean. No other run
  dirs were affected — most other candidates the old broader regex would also flag turned
  out to be legitimate, untruncated cross-references (e.g. "see 7/26/88 LB-7841 for info as
  part of that set", matrix/remix lineage notes like "Lineage: LB-2337+LB-10411") that are
  useful context and should still be pulled in.
Fix: Added a negative lookahead to LB_TAG_RE so it no longer matches an LB number immediately
  followed by "…" or "..." (rather than restricting extraction to just the Coverage table,
  which would also have dropped the legitimate cross-references above). Verified against
  both true-positive contamination cases (now excluded) and several true-negative legitimate-
  reference cases (still included).

BUG-192: Windows — test_batch_verify.py and tools/batch_verify.py not runnable on Windows (termios)
Status: Fixed
File(s): tools/batch_verify.py:36-42
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: tools/batch_verify.py imported termios and tty at module level. Both are Unix-only
  stdlib modules; their absence on Windows raised ModuleNotFoundError during import, blocking
  pytest collection of test_batch_verify.py entirely.
Fix: Replaced module-level imports with a guarded try/except block that sets _HAS_TERMIOS=True/False.
  _KeyboardController.start() checks _HAS_TERMIOS before attempting terminal setup; stop() guards
  the tcsetattr call the same way. The module is now importable on Windows and the keyboard
  controller degrades gracefully (same as when stdin is not a TTY).

BUG-187: Full pytest run is order-dependent — global bloom filter leaks between test DBs
Status: Fixed
File(s): backend/db.py:25 (_bloom/_bloom_db_path globals), backend/db.py:936 (rebuild_bloom), backend/db.py:1448 (lookup_checksums)
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: init_db() spawns a daemon thread that calls rebuild_bloom(db_path), overwriting the
  process-global _bloom filter. When multiple tests each call init_db() with their own temp DB,
  the background rebuild from one test could overwrite _bloom with checksums from a different
  (unrelated) temp DB. lookup_checksums() then used this stale filter to short-circuit lookups,
  treating valid checksums as definite misses. TestLookupChecksumsSnhCompleteness failed
  intermittently depending on which background thread finished last.
Fix: Added _bloom_db_path global (set alongside _bloom in rebuild_bloom). lookup_checksums()
  reads both under _bloom_lock and only uses the filter if _bloom_db_path matches the active
  db_path; otherwise all entries are treated as candidates and fall through to SQLite. No change
  to production behavior (single DB path, so bloom always matches).

BUG-198: Pipeline — folder_rename has TOCTOU race under concurrent rename requests
Status: Fixed
File(s): backend/app.py:5757-5786 (folder_rename route)
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: The `/api/pipeline/folder/rename` route checks `new_path.exists()` and then
  calls `folder.rename(new_path)` as two separate non-atomic operations. Under Flask's
  default threaded mode, two concurrent rename requests for different source folders that
  both resolve to the same `new_path` can both pass the `exists()` check before either
  has called `rename()`, causing the second call to raise `FileExistsError`/`OSError`.
  The backend then returned 500 instead of a structured conflict response.
Fix: Added inner try/except around `folder.rename(new_path)` that catches
  `FileExistsError`/`OSError` and returns 409 `{error: "Target already exists: <name>"}`.
  The pre-existing `if new_path.exists()` guard is retained as the fast path; the new
  catch handles the race window between that check and the actual rename call.

BUG-197: Pipeline — multiple simultaneous "Running" rows for the same show during bulk auto-rename
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1628-1647
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: The auto-rename effect fired `void applyRename(r)` for ALL rename candidates
  simultaneously via `candidates.forEach(...)` — no await, no serial queue. Each call
  immediately set `running: true` on its row before any network round-trip. When BUG-196's
  scan-tree shallow mode added both the parent folder AND every child disc-folder of a
  multi-disc concert, all rows became rename candidates at once, causing 5–10 identical-looking
  "Running - In progress" rows simultaneously. Confirmed by 2026-06-15 screenshots
  (5× Stuttgart LB-16264, ~10× Prague LB-16201).
Fix: Replaced the `forEach` with a sequential async IIFE (`for...of` + `await applyRename(r)`)
  so only one row is in the Running state at a time. The `autoRenamedRef.current.add(r.id)`
  before the await prevents double-processing if the effect re-fires while the loop is in
  progress.

BUG-196: Pipeline — scan-tree shallow mode adds parent folder AND all child folders, duplicating multi-disc sets
Status: Fixed
File(s): backend/app.py:5815-5820 (pipeline_scan_tree)
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: When `shallow=True`, `pipeline_scan_tree` checked `_has_audio(root)` and if
  true appended `root` to `found`, then unconditionally iterated all children and appended
  any child dir that `_has_audio_anywhere()`. If the root folder also contained a direct
  audio file (flat rip with mirror/extras subfolders), both the root AND every child
  disc-folder were added to the queue, producing 4–11 pipeline rows for what the user
  intended as one concert entry.
Fix: Store `root_has_audio = _has_audio(root)` once and only iterate children when
  `not root_has_audio`. When root has direct audio, only root is returned.

BUG-195: Pipeline — virtualizer fixed estimateSize causes blank space between sections
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1407-1412,
  gui_next/src/renderer/src/components/table.tsx:103-127,181-211
Reported: 2026-06-15
Fixed: 2026-06-16
Root cause: The virtualizer was configured with `estimateSize: () => 38` and no
  `measureElement` callback. Running rows displaying the `FileProgressBar` are ~70–80 px
  tall; the underestimate caused incorrect scroll offset calculations and blank space
  between the Running section and the next section header.
Fix: Added `measureElement: (el) => el?.getBoundingClientRect().height ?? 38` to the
  virtualizer config. Converted TR and GroupRow in components/table.tsx to
  `React.forwardRef`. Each rendered virtual item now uses a ref callback that stamps
  `node.dataset.index = String(vItem.index)` then calls `virtualizer.measureElement(node)`
  so TanStack Virtual uses actual DOM heights for all position calculations.

BUG-194: dbedit /rows endpoint: negative limit bypasses 500-row cap, returns unlimited rows
Status: Fixed
File(s): backend/app.py:dbedit_rows (~2784)
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: limit = min(int(request.args.get("limit", 100)), 500) has no lower bound.
  limit=-1 passes LIMIT -1 to SQLite, which returns all rows — memory/timeout hazard on
  large tables (checksums has millions of rows). page=-1 similarly maps to OFFSET -N,
  which SQLite treats as OFFSET 0, silently returning the first page.
Fix: limit = max(1, min(int(...), 500)); page = max(0, int(...))

BUG-193: importer.run_import: ProgrammingError on empty flat file — close_connection inside with-block
Status: Fixed
File(s): backend/importer.py:run_import (~138)
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: When the flat file contained 0 parseable rows, close_connection(temp_db_path)
  was called inside `with get_connection(temp_db_path) as temp_conn:`. The with-block's
  __exit__ then called conn.commit() on the already-closed connection, raising
  sqlite3.ProgrammingError ("Cannot operate on a closed database") instead of returning
  the intended {"error": "No checksums found in file."} dict. The ProgrammingError was
  caught by start_import_async and shown as a confusing internal error.
Fix: Restructured to read all data inside the with-block (using a conditional fetchall),
  then call close_connection() and unlink() outside the with-block, then return the error.

BUG-191: Windows — importer._import_flat_file background threads keep temp DB locked, causing PermissionError on unlink
Status: Fixed
File(s): backend/importer.py:_import_flat_file
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: _import_flat_file called init_db(temp_db_path) to create the temp checksums DB.
  init_db spawns two daemon threads (bloom filter rebuild + migrate_lb_master) that hold open
  connections to temp_db_path. On Windows, open file handles prevent deletion; close_connection()
  only closes the main thread's connection, so unlink() raised PermissionError: [WinError 32].
  Reproduced by test_run_import_updates_lb_master.
Fix: Replaced init_db(temp_db_path) + get_connection(temp_db_path) in _import_flat_file with a
  raw sqlite3.connect() that creates only the checksums table and is explicitly closed before
  returning. No background threads are spawned, so unlink() succeeds on Windows.

BUG-190: test_reconcile_logs_transition used LB 7 which is in _LB_MISSING_SEEDS
Status: Fixed
File(s): tests/test_lb_master.py:TestReconcileLbStatus.test_reconcile_logs_transition
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: The test seeded checksums for lb_number=7 and expected reconcile_lb_status to
  classify it as 'private', but init_db() seeds lb_missing with 7 (it is a confirmed
  non-existent LB), so reconcile_lb_status always returns 'nonexistent' for it regardless
  of checksums. Fails on all platforms, not Windows-specific.
Fix: Changed test to use lb_number=11 (not in _LB_MISSING_SEEDS) so reconcile_lb_status
  correctly transitions private → public as expected.

BUG-189: Master data "Check for Updates" fails when latest app release has no .db asset
Status: Fixed
File(s): backend/app.py:master_github_check, backend/app.py:master_github_install
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: Both routes called GET /releases/latest, which returns the newest GitHub release by
  creation date. When a new app release (e.g. v1.5.1) is pushed without a master snapshot, the
  endpoint returned "No .db asset found in release v1.5.1" even though an older release held a
  valid master .db + .manifest.json pair.
Fix: Extracted _find_master_release() helper (backend/app.py) that paginates /releases (up to
  5 pages × 20) and returns the first release containing both a .db asset and its .manifest.json
  sidecar. Both github_check and github_install now use this helper.

BUG-167: Windows — clicking "Scraper" menu item shows blank screen, requires app restart
Status: Fixed
File(s): backend/app.py:api_geocode_stats, gui_next/src/renderer/src/screens/ScreenScraper.tsx
Reported: 2026-06-12
Fixed: 2026-06-15
Root cause: SQLite SUM() returns NULL (not 0) on an empty table. When location_geocoded is
  empty (fresh install, no geocoding run yet), /api/geocode/stats returned {"geocoded": null, ...}.
  The Geocoder strip card then evaluated `null.toLocaleString()` → TypeError → React had no error
  boundary → entire screen went blank with no recovery path.
Fix: (1) backend/app.py: wrap SUM aggregates in COALESCE(..., 0) so the API always returns integers.
  (2) gui_next/src/renderer/src/screens/ScreenScraper.tsx: add `?? 0` guard on the geocoded field
  in the strip card; update GeoStats interface to type geocoded/failed/manual as number|null.
  (3) Add ScraperErrorBoundary class so any future render crash shows an error + retry button
  instead of a blank screen.

BUG-188: Windows mount root paths display with mixed slashes — c:\/1958/
Status: Fixed
File(s): backend/filer.py:22 (normalise_path), gui_next/src/renderer/src/screens/ScreenMounts.tsx (joinRoute)
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: normalise_path() used PurePosixPath(Path(raw)).as_posix(). On Windows,
  Path("c:\\") is a WindowsPath; PurePosixPath received its str() form ("c:\\") and
  treated the backslash as a literal character (not a path separator), so .as_posix()
  returned "c:\\" unchanged and stored the backslash in the DB. The GUI then built
  paths as root_path + "/" + sub_path = "c:\" + "/" + "1958" = "c:\/1958/".
Fix: (1) backend/filer.py — use Path(raw).as_posix() directly; WindowsPath.as_posix()
  correctly converts "c:\\" → "c:/" and "\\NAS\share" → "//NAS/share".
  (2) gui_next ScreenMounts.tsx — added joinRoute(root, sub) helper that strips
  backslashes (handles legacy DB data) and trailing slashes from root_path before
  joining, used in BulkFill preview, PreviewTester, routes table header, and per-row
  destination columns.

BUG-168: "Check for update" does not prompt to install new DB from LB website
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenHome.tsx:122-138,
  gui_next/src/renderer/src/screens/ScreenSetup.tsx:634-697,1749-1788,
  backend/flat_file.py:discover_flat_file_release
Reported: 2026-06-12
Fixed: 2026-06-15
Root cause: Two issues. (1) Both "Check for update" handlers (Home and Setup) read
  non-existent response fields `data.new_release` / top-level `data.zip_filename`
  from GET /api/flat_file/discover. The real response shape is `{available,
  current_release: {zip_filename, ...}, last_applied_release, error}`. Since
  `data.new_release` was always `undefined`, the handlers always took the "up to
  date" branch regardless of whether `available` was true — including on a fresh
  install with an empty database, where `discover_flat_file_release()` correctly
  returns `available=True` and inserts a 'detected' row. (2) Even when an update
  was correctly detected, there was no GUI action to download/apply it — the
  backend's /api/flat_file/download/<id>, /diff/<id>, and /apply/<id> routes were
  never called from the frontend.
Fix: (1) Both handlers now read `data.available` and
  `data.current_release?.zip_filename`. (2) Added per-row actions to the Setup
  screen's flat-file history table: "Download" (POST /flat_file/download/<id>) for
  detected/failed/deferred releases, and "Review & Apply" (GET /flat_file/diff/<id>
  → confirm dialog with added/changed/removed counts → POST /flat_file/apply/<id>)
  for downloaded releases.

BUG-186: Footer "Synced · idle" badge is static text, not a live sync/activity indicator
Status: Fixed
File(s): gui_next/src/renderer/src/components/AppShell.tsx, backend/app.py:341-368
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: The shield badge in StatusBar always rendered the literal string
  "Synced · idle" regardless of actual master-data sync state or background
  activity — same placeholder problem as BUG-185, for the right-hand badge.
Fix: Split into two independent signals. (1) "Synced"/"Update available" now
  reflects GET /api/master/github_check (compares local meta.master_version
  against the curator's latest GitHub master-data release — the curator-published
  master export, NOT the LB website's flat-file zip, which stays a curator-only
  Setup-tab concept). Checked once on mount; falls back to "Synced" if the check
  fails (e.g. offline). (2) New GET /api/activity/busy aggregates
  importer.get_import_status(), scraper.get_scrape_status(),
  bootleg_scraper.get_scrape_status(), integrity_monitor.get_scan_status(),
  filer.get_file_job_status(), plus the app-update/data-download states, into
  {busy, activity}. Polled every 5s; footer shows "Idle" or a translated
  activity label (Importing…/Scraping…/Filing folder…/etc). New locale keys
  added to all 6 languages.

BUG-185: Footer status bar shows hardcoded placeholder counts instead of live DB stats
Status: Fixed
File(s): gui_next/src/renderer/src/components/AppShell.tsx:687-772
Reported: 2026-06-15
Fixed: 2026-06-15
Root cause: StatusBar (footer) rendered fixed literal strings ("LB-16630", "704,624",
  "2026-05-21", "1,380") with no fetch/state — a fresh install with an empty database
  showed the same non-zero counts as a fully populated one.
Fix: StatusBar now fetches GET /api/home/stats on mount (same endpoint already used by
  Sidebar and ScreenHome) and renders latest_lb, checksum_count, last_import, and
  bootleg_count via new fmtLb/fmtNum/fmtLastImport helpers, showing '…' while loading.

BUG-176: tapematch run aborts entirely when one source file can't be decoded
Status: Fixed
File(s): tools/tapematch/tapematch/audio.py, tools/tapematch/tapematch/ingest.py,
  tools/tapematch/tapematch/cli.py
Reported: 2026-06-14
Fixed: 2026-06-15
Root cause: During the 1997 tapematch year run, date 1997-02-09 (6 sources) failed at the
  pre-run RAM-estimate step. `duration_sec()` for .../LB-14923/disc1/bd1997-02-09-d1t04.flac
  first tries `sf.info()` (libsndfile), which raises `LibsndfileError: Format not
  recognised` — the file is not readable as FLAC despite its extension. `duration_sec()`
  falls back to `_ffprobe_info()`, which also has no `format.duration` and falls back to
  scanning `ffmpeg -stats` output for `time=` timestamps; ffmpeg apparently produced no
  decodable output either, so `_ffprobe_info` raised `RuntimeError("could not determine
  duration for ...")`. This exception was uncaught all the way up through `source_report`
  → `cli.py main()`'s `_durs_sec = [...]` comprehension (cli.py:96), crashing the whole
  date's run before any alignment/matching happened — the session script then found no
  results.json and skipped DB logging for all 6 sources, not just the bad LB-14923 one.
Fix: `audio.duration_sec()` now raises a dedicated `UnreadableAudioError` when neither
  libsndfile nor the ffprobe/ffmpeg fallback can determine a file's duration.
  `ingest.source_report()` catches that per-track and re-raises `UnreadableSourceError`
  (carrying `source_dir`/`track`). `cli.py main()` now runs `source_report` on every
  discovered source up front, drops any source that raises `UnreadableSourceError` with a
  printed `[SKIP] source excluded: unreadable file <path>` message, and only proceeds if
  ≥2 readable sources remain — so the rest of the date's sources are still compared.
  LB-14923's bd1997-02-09-d1t04.flac itself was not separately investigated (out of scope
  for this fix; the run now completes regardless).
Reproduce: tapematch 1997 year run, date 1997-02-09, source LB-14923, file
  disc1/bd1997-02-09-d1t04.flac — see session 20260614_215503.

BUG-165: _lb_num_from_folder picks up a cross-referenced LB number instead of the entry's own
Status: Fixed
File(s): tools/tapematch/tapematch_session.py
Reported: 2026-06-12
Fixed: 2026-06-15
Root cause: `_lb_num_from_folder` used `re.search(r"LB-(\d+)", folder_name)`, returning the
  *first* "LB-XXXX" match in the folder name. Folder names that embed a cross-reference
  earlier than the entry's own LB number (e.g. "1989-07-16 Bristol, CT [fixed LB-2204]-LB-10437-v",
  whose own entry is LB-10437) resolved to the cross-referenced number (2204) instead. When
  the *other* source in the pair was the actual LB-02204 folder, both `lb_a` and `lb_b`
  resolved to 2204 — a degenerate self-pair row in observations.db (`pairs.lb_a == pairs.lb_b`).
  Found while auditing observations.db for TODO-139 Task 2 (7 such rows: dates 1989-07-16,
  1988-06-07, 1988-06-25, 1988-07-20, 1988-09-11, 1988-09-23, 1993-06-19).
Fix: `_lb_num_from_folder` now takes an optional `name_to_lb` map (folder name -> LB number,
  built from `found_folders`) and prefers that DB-resolved mapping over the regex scan,
  falling back to the regex only when the folder isn't in the map. `insert_sources` and
  `insert_pairs` (which gained a `found_folders` parameter) now build and pass this map.
  The 7 pre-existing self-pair rows in observations.db were not corrected in place — the
  upgrade-folder LB numbers involved (10437, 14661, 14665, 14672, 10934, 14683, 2072) aren't
  in `my_collection` for these dates, so reconstructing the correct mapping requires the
  drive-scan fallback (`scan_drives_for`) from a live session, not just DB data. Future runs
  for these dates will log correct rows.

BUG-146: build_standard_name produces xx/xx/YY folder date prefix for entries with unknown month/day
Status: Fixed
File(s): backend/torrent_maker.py, backend/folder_naming.py
Reported: 2026-06-09
Fixed: 2026-06-15
Root cause: `_parse_date` caught `ValueError` from `int('xx')` and fell back to
  `date_str.strip()`, returning the raw DB string (e.g. `'xx/xx/65'`) unchanged.
  `build_standard_name` then used this as the date prefix, producing
  `'xx/xx/65 HIGHWAY 61 ROM... (LB-12205)'`. Existing folders for these entries already use
  ISO-style `'1965-xx-xx ...'` format.
Fix: `_parse_date` now parses month/day/year independently, preserving an `'xx'` component
  as `'xx'` in the ISO output while still formatting any numeric component normally —
  e.g. `xx/xx/65` -> `1965-xx-xx`, `3/xx/72` -> `1972-03-xx`, `xx/15/72` -> `1972-xx-15`.
  Falls back to the original string only if the year itself can't be parsed.

BUG-184: Backend subprocesses (ffmpeg/sox/shntool) orphaned on normal app quit
Status: Fixed
File(s): gui_next/src/main/index.ts
Reported: 2026-06-14
Fixed: 2026-06-14
Root cause: `backend/app.py`, `checksum_utils.py`, `sox_utils.py`, `updater.py`, and
  `sharing.py` all shell out via `subprocess.Popen/run/call` (ffmpeg, sox, shntool.exe)
  during checksum/verify/scan operations. `before-quit`'s `backendProc.kill('SIGTERM')`
  maps to Windows `TerminateProcess(pid)`, which kills only `LosslessBobBackend.exe`
  itself — it does not cascade to subprocess children. If the user quits while such an
  operation is running, the child process (e.g. shntool.exe holding a handle on an LB
  mount) becomes an orphan, separate from the crash-only scenario fixed in BUG-183.
Fix: Added `killProcessTree(pid)` in `gui_next/src/main/index.ts` — on Windows runs
  `taskkill /F /T /PID <pid>` (the `/T` flag kills the whole descendant process tree);
  on POSIX falls back to `process.kill`. Used in `before-quit` (was a plain
  `backendProc.kill('SIGTERM')`) and in `killStalePid` (was a plain `process.kill`),
  and added `/T` to the existing `taskkill` call in `killPortProcess`.

BUG-183: Windows installer/updater shows "LosslessBob cannot be closed" — requires manual intervention
Status: Fixed
File(s): gui_next/resources/installer.nsh (new), gui_next/src/main/index.ts
Reported: 2026-06-14
Fixed: 2026-06-14
Root cause: `LosslessBobBackend.exe` (the Flask backend, spawned as a child process by the
  Electron main process — see `ensureBackend()` in `gui_next/src/main/index.ts`) becomes an
  orphan if LosslessBob.exe exits abnormally (crash, Task Manager "End Task", etc.), since
  `before-quit`'s `backendProc.kill()` never runs and Windows does not kill child processes
  when their parent dies. The orphaned LosslessBobBackend.exe keeps its own exe file (under
  `resources\backend\`) locked. electron-builder's NSIS "app is running" check
  (`_CHECK_APP_RUNNING`) only knows about `LosslessBob.exe` (APP_EXECUTABLE_FILENAME), so it
  never detects or closes the orphaned backend — file extraction/overwrite of
  LosslessBobBackend.exe then repeatedly fails, surfacing electron-builder's generic
  "${PRODUCT_NAME} cannot be closed. Please close it manually and click Retry to continue."
  message (app-builder-lib/templates/nsis/messages.yml: appCannotBeClosed).
Fix: Added `gui_next/resources/installer.nsh` defining a `customInit` NSIS macro (runs early
  in .onInit, before file extraction) that force-kills any leftover `LosslessBobBackend.exe`
  via `taskkill /F /IM`. electron-builder auto-discovers this file as the installer's custom
  include (no nsis.include config needed since it matches the default `installer.nsh` name
  in `directories.buildResources`).

BUG-182: tapematch resolve_from_collection crashes with OSError on unreachable drive mount
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:resolve_from_collection
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: p.is_dir() raised OSError("[Errno 5] Input/output error") for a
  my_collection disk_path on /mnt/DYLAN2 while that drive was unreachable
  (DYLAN2 is intermittently offline), crashing the whole tapematch session
  before find_lb_folders' private/no-torrent/no-audio exclusion logic ever ran.
  Found while validating BUG-181's fix against 1989-09-01 (LB-13295 lives on
  DYLAN2).
Fix: wrap p.is_dir() in try/except OSError; an unreachable path is treated as
  "missing" (falls through to scan_drives_for / not-found) instead of crashing
  the session. Re-run of 1989-09-01 with DYLAN2 offline now completes and
  produces the new insufficient_sources report (TODO-139 Task 7).

BUG-181: tapematch find_lb_folders includes no-audio folders, crashing
  ingest.concat_source (1989-08-26 / 1989-09-01 / 1989-09-03)
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:find_lb_folders
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: resolve_from_collection returns folder paths that exist on disk
  but contain only text/image/md5 files and no audio (cover-scan / EAC-log-only
  collection entries) — LB-01430 (1989-08-26), LB-01588 (1989-09-01), LB-02245
  (1989-09-03). find_lb_folders included these as tapematch sources, and
  ingest.concat_source then raised ValueError("no audio in <folder>") for the
  *entire date*, even though other folders for the same date had real audio.
Fix: find_lb_folders now drops folders failing the existing _has_audio() helper
  the same way it already drops private/no-torrent folders, printing
  "Excluded (no audio found): LB-XXXXX". Unit-tested
  (tests/test_find_lb_folders_no_audio.py, 2/2 pass). Validated: 1987-10-05 and
  1989-08-26 now complete full tapematch runs; 1989-09-01 (left with only 1
  source after exclusion) now gets the new insufficient_sources report instead
  of crashing.

BUG-180: tapematch ingest.list_tracks matches a directory named like an audio
  file as a track (1987-10-05 crash)
Status: Fixed
File(s): tools/tapematch/tapematch/ingest.py:list_tracks
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: list_tracks used Path.rglob("*") + suffix matching with no
  is_file() check. The 1987-10-05 LB-10681 source folder contains a
  *subdirectory* named "1987-10-05locarno+asm.flac" holding the real per-track
  .flac files; that directory's name also ends in ".flac", so it was matched as
  a "track" itself. audio.duration_sec() then called sf.info() on the
  directory, raising LibsndfileError("Format not recognised") and crashing the
  whole 1987-10-05 session.
Fix: list_tracks now requires p.is_file() in addition to suffix matching.
  Unit-tested (tests/test_ingest_list_tracks.py, 2/2 pass). Validated:
  1987-10-05 now completes a full 5-source tapematch run (2 families).

BUG-179: Pipeline "File all into collection" leaves duplicate stuck-running ghost rows
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1675-1768 (applyFile),
  :2010-2020 ("File all into collection" button)
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: TODO-142 (batch filing with skipConfirm=true) made `applyAllFileable`
  loop through `fileableRows` quickly with no per-folder confirm dialog, but the
  "File all N into collection" button had no `disabled` guard and `applyFile` had
  no re-entrancy guard. A second click (or a second batch trigger) while a batch
  was still in flight started a second `applyFile`/`applyAllFileable` loop that
  raced against the first against the single global `_FILE_JOB` in
  backend/filer.py. The second loop's polling could read `/api/pipeline/file/status`
  for a job belonging to a *different* row (no row/job correlation existed), so its
  own row's `while (!result)` loop never saw its own job's `result` and stayed
  `running:true` with a frozen `fileProgress` forever — even though the folder had
  actually been filed (the other loop's row correctly flipped to `bucket:'done'`).
Fix: (1) Added a `filingRef`/`filingActive` re-entrancy guard — `applyFile` now
  bails out (with a toast) if a filing job is already in flight, and the
  "File all N into collection" button is disabled (`disabled={filingActive}`)
  while a batch is running. (2) `applyFile`'s polling loop now checks
  `status.path` (already present in `_FILE_JOB`/`get_file_job_status()`) against
  `row.folderPath`; if `_FILE_JOB` has been taken over by a different job, the
  loop exits with an error result (`pipeline.file.jobMismatch`) instead of
  spinning forever. Added `pipeline.file.busy`/`pipeline.file.jobMismatch` i18n
  strings (all locales) and a local toast (`showToast`/`toast` state — previously
  missing from ScreenPipeline, three call sites referenced a non-existent
  LbdirStageContent-scoped `showToast`).

BUG-178: Pipeline "Final storage" destination uses pre-rename folder name after Apply rename
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1570-1593 (applyRename)
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: resolve_destination_for_lb() builds `dest = dest_parent / Path(folder_path).name`
  (backend/filer.py:224), so the "file" step's dest/dest_parent are tied to whatever folder
  basename was current at the time `/api/pipeline/run` last ran. applyRename() renames the
  folder on disk and updates row.folderPath/folderName plus steps.rename to "Renamed", but
  never recomputed steps.file — so CollectReadyDetail's "Final storage" box kept showing the
  destination built from the OLD (pre-rename) folder name even though "Staging" already showed
  the new, already-applied name and Rename read "Pass".
Fix: After a successful /api/folder/rename, applyRename now POSTs /api/pipeline/run
  {folders: [new_path], steps: ['file']} and merges the returned `file` step (dest,
  dest_parent, mount_label, etc., via normalizeFileStep) into the row, so "Final storage"
  reflects the renamed folder immediately without re-running verify/lookup/lbdir.

BUG-177: Pipeline "Apply rename" fails silently when a folder with the proposed name already exists
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1535-1592 (applyRename), :913-919 (RenameStageContent)
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: `applyRename` POSTs to `/api/folder/rename`, which already returns 409
  `{error: "Target already exists: <name>"}` when `new_path.exists()` (backend/app.py:5721-5722).
  The frontend only handled the `data.ok && data.new_path` success branch — any error response
  (including this 409) and the `catch` block were both no-ops, so the Rename step just stayed in
  its "ready to apply" state with no indication anything went wrong.
Fix: When the response is not `ok`/`new_path`, store `data.error` (or a generic message for network
  failures) on `row.steps.rename.error` while keeping `status: 'warn'` so "Apply rename" remains
  available for retry. RenameStageContent now renders a "Rename failed" banner with that message
  above the diff box when `step.error` is set; it clears on the next successful apply or "Re-check".

BUG-176: Pipeline rename reports "Folder name is already correct" even when folder is missing its (LB-NNNNN) tag — causes Shelf folders to be promoted to "ready to file"
Status: Fixed
File(s): backend/app.py:5566-5596 (rename step, BUG-119 fallback)
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: When the DB entry for the resolved LB# has an empty `location` (or `date_str`), the BUG-119
  fallback set `proposed = apply_nft_suffix(strip_nft_suffix(folder_name), lb_status)` — i.e. it derived
  the "proposed" name directly from the *current* folder name instead of validating against the canonical
  `build_standard_name()` output. The fallback never checked whether `folder_name` actually contained
  "(LB-NNNNN)". So `folder_name == proposed` was trivially true whenever lb_status didn't require an
  -NFT change, and the rename step reported status "ok" / label "Correct" — surfaced in the GUI as
  "Folder name is already correct" (ScreenPipeline.tsx:875) — even though the folder had no LB# tag at all.
  Example: LB-16311 has date_str='10/6/22', location='' (empty), lb_status='public'. Folder on disk is
  "Berlin 2022-10-06 TK" (no "(LB-16311)" suffix). Rename step still reported "Correct".
  Downstream effect: with verify/lookup/lbdir/rename all "ok", severity computed to "done"
  (backend/app.py:5656), and if the file step resolved a destination the folder was counted in
  "ready to file" — so a folder still sitting in "Shelf" status with an untagged name was surfaced
  as ready to file, even though filing it would leave the LB# tag permanently missing from the name.
Fix: Before checking date_str/location, if location is blank but date_str is present, look up
  bobdylan_shows by the ISO-converted date and use its location (e.g. "Berlin, Germany" for
  2022-10-06) as a fallback so build_standard_name can still produce the canonical
  "YYYY-MM-DD Location (LB-NNNNN)" order (for LB-16311: "2022-10-06 Berlin, Germany (LB-16311)").
  Only if no bobdylan_shows match exists either does the BUG-119 fallback apply: strip the -NFT
  suffix and check whether the base name already ends with the correct "(LB-{lb_number:05d})" tag.
  If so, only the NFT suffix is adjusted as before. If not, any existing/stale "(LB-NNNNN)" tag is
  stripped via regex and the correct tag is appended before re-applying the NFT suffix — so the
  rename step proposes adding the missing tag instead of reporting "Correct". Date/location text
  already present in the folder name is never touched in this last-resort path, so BUG-119 remains
  fixed.

BUG-166: Pipeline status badge shows "In collection" (green) while step 5 (File) is still "Needs you"
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1556
Reported: 2026-06-12
Fixed: 2026-06-13
Root cause: `applyRename` hardcoded `bucket: 'done'` on a successful rename, without checking
  `r.steps.file.status`. `deriveFolderStatus`'s `bucket === 'done'` branch renders the green
  "In collection" / "Filed to <mount>" badge purely from `bucket`, regardless of the per-step
  statuses — so a folder whose rename just succeeded but whose File step (step 5) is still
  `'warn'` ("Ready to file", not yet moved into the collection mount) showed the green
  "In collection" badge with a yellow "!" on step 5. `serverRowToPipeline` already had a guard
  for exactly this case (`if (bucket === 'done' && file.status === 'warn') bucket = 'shelf'`),
  but `applyRename`'s direct bucket assignment bypassed it.
  Secondary effect: these rows were also miscounted as not-`shelf`, so `counts.shelf` stayed 0
  for them and the "File all N into collection" button (gated on `counts.shelf > 0`) did not
  appear even though `fileableRows` (based on `file.status === 'warn'` alone) still included them.
Fix: `applyRename`'s success branch now derives `bucket` the same way `serverRowToPipeline`
  does: `bucket: r.steps.file.status === 'warn' ? 'shelf' : 'done'`.

BUG-175: Windows — fonts render badly (wrong fallback font / blurry ClearType)
Status: Fixed
File(s): gui_next/src/renderer/index.html, gui_next/src/renderer/src/index.css,
  gui_next/src/renderer/src/main.tsx, gui_next/src/preload/index.ts,
  gui_next/src/renderer/src/env.d.ts, gui_next/package.json
Reported: 2026-06-13
Fixed: 2026-06-13
Root cause: Two compounding issues. (1) index.html loaded Inter/IBM Plex Sans/Source Sans 3/
  JetBrains Mono from fonts.googleapis.com at runtime. On a Windows install without a live
  connection to Google (firewall/offline/captive portal), that request fails and the
  app silently falls back to generic system fonts. (2) index.css applied
  `-webkit-font-smoothing: antialiased` globally. On Windows, Chromium honours this and
  disables ClearType subpixel rendering, making *all* text — including the fallback
  fonts — look noticeably blurrier/thinner than native Windows apps.
Fix: Self-hosted all four font families via @fontsource (pinned exact versions: inter
  5.2.8, ibm-plex-sans 5.2.8, source-sans-3 5.2.9, jetbrains-mono 5.2.8), imported per-weight
  in main.tsx for the same weights previously requested from Google Fonts. Removed the
  Google Fonts <link>/preconnect tags from index.html and tightened the CSP (no more
  fonts.googleapis.com/fonts.gstatic.com in style-src/font-src). Exposed `process.platform`
  via the preload bridge (`window.api.platform`) and have main.tsx set a
  `platform-<platform>` class on <html> before React mounts; scoped
  `-webkit-font-smoothing: antialiased` to `html.platform-darwin` only.

BUG-174: LBDIR reconcile doesn't pull matching files from data/site/files for self-referencing/regenerated entries
Status: Fixed
File(s): backend/checksum_utils.py:find_site_recoverable_files, gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx, gui_next/src/renderer/src/lib/lbdirStore.ts
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: find_site_recoverable_files() matched data/site/files/LBF-{N}-* candidates
  against missing lbdir entries by exact MD5 only. For a folder whose on-disk lbdir
  manifest lists itself (e.g. lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt) and a
  DigiFlawFinder report (DigiFlawFinder-bd92-09-12-PDub-Dolphinsmile.flac1648.wavf.html)
  in its === md5 for: === section, both files were "Missing" with overall='missing'.
  Same-named copies existed in data/site/files/ as
  LBF-13333-lbdir-bd92-09-12-pdub-dolphinsmile.flac1648.txt and
  LBF-13333-DigiFlawFinder-bd92-09-12-pdub-dolphinsmile.flac1648.wavf.html, but their
  content (and therefore MD5) differs from what this folder's (older) lbdir expects —
  a manifest necessarily can't checksum a byte-identical copy of a different lbdir
  revision, and report files get regenerated over time. MD5-only matching could never
  recover them, so site_proposals stayed empty and the Reconcile panel showed "No
  rename proposals" / "Nothing to reconcile" despite the files being present in
  data/site/files/.
Fix: Added a filename-based fallback in find_site_recoverable_files(): for missing
  entries with no MD5 match, strip the LBF-{lb_number:05d}- prefix from each
  data/site/files/ candidate and compare (case/apostrophe-normalised) against the
  missing entry's basename. Matches are returned with matched_by:'name' plus both
  md5 (site copy's actual hash) and expected_md5 (the folder's lbdir requirement) so
  the caller can see they differ. gui_next's ReconcilePanel renders these rows with
  an "MD5 mismatch" warning pill (tooltip shows both hashes) and a banner noting the
  copy won't pass verification as-is — the user can still apply it (better than
  missing) but is warned the content is a different revision.

BUG-173: qBittorrent save-path sync still missed renamed folders moved between staging dirs
Status: Fixed
File(s): backend/qbittorrent.py:find_torrent_by_path
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: BUG-172's rename_history fallback computes the pre-rename path as
  `old_folder.parent / <pre-rename name>` — i.e. it assumes the pipeline rename happened
  in the same directory qBittorrent's content_path still points at. LB-16295/16309/16211
  were renamed in place under /mnt/MEDIA1/1-DYLAN/, but their qBittorrent torrents'
  content_path is still under /mnt/MEDIA1/hopper-bob/ (the files were relocated between
  those two staging directories at an earlier step not captured in rename_history), so the
  computed `expected` path never matched and sync silently no-op'd (synced: False) for 3 of
  5 folders filed in one batch.
Fix: find_torrent_by_path() now also falls back to matching qBittorrent torrents on the
  pre-rename folder *name* alone (basename of old_path), regardless of directory, when the
  directory-aware `expected` match fails — but only if exactly one torrent's content_path
  basename matches, to avoid relocating the wrong torrent. Verified live: LB-16295/16309/
  16211 now resolve to their correct infohashes; LB-16227 (genuinely never added to
  qBittorrent) still correctly returns no match.

BUG-172: qBittorrent save-path sync didn't relocate a torrent renamed before filing
Status: Fixed
File(s): backend/qbittorrent.py:find_torrent_by_path, relocate_tracked_torrent
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: The pipeline's rename step renames a folder in place (e.g. "Bob Dylan Aarhus
  Festival at Tangkrugen DK 1996-06-15 Dolphinsmile Archive" → "1996-06-15 Aarhus, Denmark
  (LB-16281)") before filing moves it, but never tells qBittorrent — qBittorrent still has
  the pre-rename name in content_path. find_torrent_by_path()'s fallback for torrents
  added outside the app workflow only did an exact content_path string match against the
  pre-filing path, so a renamed-then-moved folder (LB-16281) matched nothing and was
  silently skipped (synced: False).
Fix: find_torrent_by_path() now also checks rename_history for the most recent row whose
  new_path is the pre-filing folder, derives the pre-rename root folder name from
  old_path, and matches qBittorrent torrents on that name. New rename_torrent_root()
  (POST /api/v2/torrents/renameFolder) and recheck_torrent() (POST
  /api/v2/torrents/recheck) let relocate_tracked_torrent() fix both the save path and the
  root folder name in one pass. Verified live against LB-16281's torrent
  (23704b9e2974...): save_path/content_path now point at the new location, progress
  stayed at 1 (no re-download), state stoppedUP.

BUG-171: Publish Master Update fails with "400 Client Error: Bad Request" uploading to GitHub
Status: Fixed
File(s): backend/app.py:master_github_release._upload_asset
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: _upload_asset() streamed the asset body via a plain generator (`_reader()`)
  while also setting a `Content-Length` header manually. `requests` cannot determine a
  length from a bare generator (no `__len__`/`fileno`), so `prepare_content_length` adds
  `Transfer-Encoding: chunked` regardless — sending both `Content-Length` and
  `Transfer-Encoding: chunked` to uploads.github.com, which rejects the request with
  `400 Bad Request` as soon as the first chunk is sent (confirmed by re-running
  master_github_release directly: release `master-2026-06-13.2` was created, then the
  .db asset upload failed at 0%).
Fix: Replaced the generator with a `_ProgressFile` file-like object exposing `__len__`
  (returns the real file size) and `read()` (returns 1 MB chunks while emitting the same
  progress events). `requests`' `super_len()` then finds `__len__` and sets a real
  `Content-Length` with no `Transfer-Encoding` header, matching what uploads.github.com
  requires.
Note: The diagnostic re-run created an empty GitHub release `master-2026-06-13.2`
  (id 338888978, no assets) on kuddukan42/losslessbob — left in place pending user
  decision on whether to delete it.

BUG-170: Pipeline scan-tree (shallow) misses top-level folders whose audio is in subfolders
Status: Fixed
File(s): backend/app.py:pipeline_scan_tree
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: BUG-167 switched the GUI's "Scan tree…" to `shallow: true`, which checks each
  immediate child of the picked root via `_has_audio(child)` — a non-recursive check of
  that child's direct files only. Release folders organized with audio inside CD1/CD2/Extras
  subfolders (no audio directly in the release folder itself) have no direct audio files,
  so `_has_audio(child)` returns False and the whole release folder is silently skipped.
Fix: Added `_has_audio_anywhere(d)` (uses `d.rglob("*")`) and used it for the shallow
  immediate-children check, so a top-level folder is added if it contains audio anywhere
  beneath it, while only the top-level folder path itself (not its nested subfolders) is
  returned. Root's own direct-audio check (BUG-108) is unchanged.

BUG-169: Publish Master Update does not update "Master version" / "Last published" in GUI
Status: Fixed
File(s): backend/app.py:4086-4106 (master_github_release), backend/db.py:3510-3522 (export_master_db)
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: export_master_db() stamps master_version/master_published_at/master_schema_version
  into the *exported snapshot* (a separate sqlite3 connection on the .db copy created via
  VACUUM INTO), not into the live database's meta table. master_github_release uploaded
  that snapshot to GitHub but never wrote those keys back to the live DB. /api/master/status
  reads master_version/master_published_at from the live DB's meta table, so the Setup
  screen's "Master version" / "Last published" fields stayed stale (or blank) after every
  publish, even though loadMasterStatus() correctly re-fetched on the "done" SSE event.
Fix: After both assets (db + manifest) upload successfully, master_github_release reads
  the manifest sidecar JSON and calls database.set_meta() to write master_version and
  master_published_at into the live DB, so the post-publish /api/master/status refresh
  reflects the just-published snapshot.

BUG-168: Publish Master Update fails with "json failed" / does not complete
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenSetup.tsx:744-786
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: `handlePublishMaster`'s step 2 called `await gr.json()` on the response from
  `POST /api/master/github_release`. That endpoint was rewritten to a `text/event-stream`
  response (progress events for tag selection, release notes, and chunked asset upload)
  during the TODO-115..120 stub-screen wiring (commit df708ce8), but the frontend caller
  was never updated to match — it still expected a single `{ok, tag, url}` JSON body.
  `gr.json()` threw a SyntaxError parsing the `data: {...}\n\n` SSE frames, caught by the
  outer try/catch and surfaced as "Publish failed: ... is not valid JSON" — the GitHub
  release was never created (or its result was never reported) and `master_published_at`
  was never refreshed.
Fix: Read `gr.body` via `getReader()`/`TextDecoder`, split on `\n\n`, and parse each
  `data: {...}` frame. `progress` events are shown as toasts, `done` triggers the
  "Released <tag>" toast + `loadMasterStatus()`, and `error` shows the existing
  "GitHub upload failed" toast.

BUG-167: Pipeline "Scan tree…" button scans recursively instead of 1 level deep
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1726-1733
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: `handleScanTree` called `POST /api/pipeline/scan-tree` with `shallow: false`,
  which triggers `pipeline_scan_tree()`'s `root.rglob("*")` branch — every audio-containing
  subdirectory at any depth under the picked folder was added to the queue, including
  nested CD/disc/extras subfolders that shouldn't be queued as separate pipeline entries.
  The backend already supports `shallow: true` (root + immediate subdirs only, depth 1),
  used by ScreenLBDIR's equivalent scan.
Fix: Changed `handleScanTree` to pass `shallow: true`.

BUG-164: gen_analysis.py false MISS on "alternative recording to X/Y ... same recording" snippets
Status: Fixed
File(s): tools/tapematch/gen_analysis.py:_build_observations
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: `_build_observations` computed `is_same = _same_signal(snip) or _same_signal(text[:200])`
  independent of `_diff_signal(snip)`. A snippet like "Alternative recording to LB-0491/LB-0569
  which all appear to be same recording" matches both patterns — the "same recording" clause
  describes the LB-0491/LB-0569 group's relationship to *each other*, not to the subject LB —
  so the pair was wrongly flagged "MISS" whenever tapematch (correctly) placed the subject in a
  different family.
Fix: `is_same` is now `not is_diff and (_same_signal(snip) or _same_signal(text[:200]))`. When
  `_diff_signal(snip)` matches, the pair falls through to the existing FALSE MERGE check (if
  tapematch grouped them together) or the neutral `→` observation (if not), per
  instructions/CC_TAPEMATCH_FIXES.md Task 1. Added unit tests
  (tools/tapematch/tests/test_gen_analysis.py) covering the ambiguous snippet plus clean
  positive/negative same/diff snippets. Regenerated all 429 analysis.md (--overwrite --all,
  0 errors); 2001-10-30's MISS count dropped 5→0 (was entirely parser noise). Corrected
  baseline written to tools/tapematch/BASELINE.md, superseding instructions/TAPEMATCH_PLAN.md.

BUG-155: DB — entry locations with non-ASCII chars stored corrupted (LB-16298 "Mnchen, Germany", ü dropped)
Status: Fixed
File(s): data/losslessbob.db (entries.location, location_geocoded)
Reported: 2026-06-10
Fixed: 2026-06-12
Root cause: Not an encoding bug — verified against the live site (and the local
  cached detail pages) that the source HTML for LB-9546, 10083, 12969, 16298, and
  16626 literally contains the byte string "Mnchen" (the letter "u" is simply
  missing). No "ü"/accented character is involved and 0 rows in entries.location
  contain any non-ASCII character, so the scraper/decode path is not at fault —
  this is a typo on the LosslessBob site itself. Re-scraping cannot fix it since
  the upstream page is wrong.
Fix: One-time data correction. Updated entries.location for LB-9546, 10083,
  12969, 16298, 16626 from "Mnchen..." to "Munchen..." (matches the existing
  ASCII-transliteration convention used by entries 671, 2634, 3320, 3391, 4123).
  Renamed/cleaned the corresponding location_geocoded cache rows so geocoding
  isn't re-run unnecessarily. entries_fts picked up the change automatically via
  the existing AFTER UPDATE trigger.
BUG-163: NameError on /api/admin/restart — stray `_time.sleep` undefined name
Status: Fixed
File(s): backend/app.py:_do_restart (admin restart endpoint)
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: `_do_restart()` called `_time.sleep(0.3)`, but only `time` is imported
  at module scope (no `_time` alias). Caught by ruff (F821 undefined name) during
  pre-commit; would have raised NameError at runtime the first time
  /api/admin/restart was hit.
Fix: changed `_time.sleep(0.3)` to `time.sleep(0.3)`.

BUG-162: Pipeline Lookup shows green "Pass" on a half-matched checksum set with no detail widget
Status: Fixed
File(s): backend/app.py:_pipeline_process_folder (lookup step), gui_next/src/renderer/src/screens/ScreenPipeline.tsx:LookupStageContent
Reported: 2026-06-12
Fixed: 2026-06-12
Root cause: When exactly one LB# was found, `_pipeline_process_folder` set
  `lookup.status = "ok"` (green Pass) purely on `len(lb_list) == 1`, ignoring
  `summary.matched` vs `summary.given`. For "2018-08-06 Singapore Mani R-05"
  (LB-13718) the folder's local .ffp checksums matched all 21 DB 'f' (ffp/audio)
  rows for that LB, so the per-LB xref-group was "complete" — but the folder's
  local .md5 checksums (21 more) matched none of the DB's 'm' (md5/whole-file)
  rows, giving an overall 21/42 match. The pipeline showed a green Pass with only
  a small "21/42 matched" caption, and the LookupStageContent "ok" branch never
  rendered <LookupDetail>, so the 21 NOT FOUND checksums were never surfaced.
Fix: In _pipeline_process_folder, a resolved LB# (pinned or single match) is only
  "ok" (Pass) when `summary.matched == summary.given` (42/42). Otherwise status is
  "warn" / label "Incomplete match" with an error row noting the X/Y ratio — lb_number
  stays set so Rename/LBDIR/Collect can still proceed, but the stage shows as
  "Needs you" instead of Pass. ScreenPipeline.tsx's LookupStageContent gained a new
  warn branch (lb_number set, non-Conflict) that explains the mismatch and renders
  <LookupDetail> (LookupSummaryTable + LookupChecksumTable), so the 21 NOT FOUND
  checksum rows are visible.

BUG-154: Pipeline — stale tsc-emitted .js files shadow .tsx sources; app runs pre-BUG-149 pipeline code
Status: Fixed
File(s): gui_next/src/renderer/src/**/*.js (45 untracked build artifacts, e.g. screens/ScreenPipeline.js)
Reported: 2026-06-10
Fixed: 2026-06-11
Root cause: A tsc run with emit (no --noEmit) on 2026-06-10 ~17:09 wrote compiled .js files next to
  every .tsx/.ts source under gui_next/src/renderer/src. Vite resolves extensionless imports
  (e.g. `import { ScreenPipeline } from './screens/ScreenPipeline'` in App.tsx:15) with .js BEFORE
  .tsx, so the dev/build app silently loads the stale compiled code. screens/ScreenPipeline.js
  predates the BUG-149/151/152/153 fixes: auto-run only sends ['verify','lookup'] (rename/lbdir/file
  stay mute → "Rename unlocks after lookup resolves an LB#" even though lookup shows LB-NNNNN),
  no _pipelineCache (statuses cleared on tab navigation), no auto-complete effect.
Fix: Untracked .js artifacts under gui_next/src/renderer/src no longer present (removed in a prior
  session). tsconfig.web.json and tsconfig.node.json already set "noEmit": true, so a `tsc -p` run
  on either project config can't regenerate them. Added gui_next/.gitignore entries for
  src/{renderer,main,preload}/**/*.js as a guard against any future stray emitted file shadowing
  a .tsx/.ts source.

BUG-153: Pipeline — step results lost on tab navigation; component remount resets all rows to emptyRow
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:87,1199,1290,1409
Reported: 2026-06-10
Fixed: 2026-06-10
Root cause: Pipeline step results (verify, lookup, rename, lbdir, file) live only in ScreenPipeline's local useState. Every time the user navigates away and back, the component unmounts/remounts and useState resets to []. The queue sync effect then re-adds folders as emptyRow (all steps mute), losing all previously-run results.
Fix: Added module-level _pipelineCache Map (keyed by folder path). updateRow writes to cache on every result update. Queue sync restores from cache for any folder already processed in this session. Cache is cleared on queue Clear and on individual row removal; updated (key migrated) on rename apply.

BUG-152: Pipeline — stale folders (lookup=ok, rename=mute) never auto-complete after BUG-149 fix
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1344
Reported: 2026-06-10
Fixed: 2026-06-10
Root cause: BUG-149 fixed auto-run for NEW folders but existing queue rows that were already processed with old auto-run (verify+lookup only) stayed with rename=mute forever — no mechanism re-ran the missing steps.
Fix: Added auto-complete useEffect that detects rows where lookup=ok and rename=mute, adds them to autocompleteStarted ref (prevents re-triggering), and runs ['lookup','rename','lbdir','file'] to complete the pipeline.

BUG-151: Pipeline — partial-step runs (Check rename, Re-check) wipe existing Verify/Lookup results
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1304
Reported: 2026-06-10
Fixed: 2026-06-10
Root cause: serverRowToPipeline always returns all 5 steps from the server response. The backend initialises unrun steps as mute, so a partial run (e.g. ['lookup','rename']) overwrites the client's existing verify=Pass and lbdir results with mute. updateRow replaced the whole steps object unconditionally.
Fix: In runSteps, after calling serverRowToPipeline, iterate all 5 step keys and for any key NOT in the requested steps set, restore target.steps[key] (the pre-run value) into fresh.steps before calling updateRow.

BUG-150: Pipeline — per-stage re-run buttons send only their stage; lb_number is always None → rename/lbdir/file stay mute
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:733,773,860,960,1037,1055,1075
Reported: 2026-06-10
Fixed: 2026-06-10
Root cause: "Check rename", "Re-check", "Check route now" etc. called onRun(['rename'|'file'|stageKey])
  with only the target stage. The backend rebuilds lb_number from scratch each call, so without 'lookup'
  in the steps list lb_number is always None → downstream stages stay mute.
Fix: Prepend 'lookup' to steps for all 7 per-stage re-run buttons that depend on lb_number
  (rename×3, file×3, lbdir×1).

BUG-149: Pipeline — auto-run only ran verify+lookup; rename/lbdir stayed mute → false "In collection"
Status: Fixed
File(s): backend/app.py:5251-5258, gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1328
Reported: 2026-06-10
Fixed: 2026-06-10
Root cause: (1) Auto-run fired runSteps(['verify','lookup']) — rename, lbdir, file steps were never
  requested so they stayed 'mute'. (2) The backend severity formula treated 'mute' as equivalent to 'ok'
  (all steps in ("ok","mute") and at least one "ok"), so a folder with verify+lookup passing but
  rename/lbdir never run got severity="done" → bucket="done" → shown as "IN COLLECTION" in batch view,
  and "Done · LB-NNNNN" in the queue sidebar — a false positive. (3) The mute LBDIR panel's
  "Retrieve sidecar now" button called /api/lbdir/retrieve with no way to supply the LB# resolved
  by lookup; endpoint only checked my_collection.disk_path and folder-name regex — both fail for an
  un-filed, un-renamed folder.
Fix: (1) Auto-run now runs ['verify','lookup','rename','lbdir','file'] in one pass. (2) Severity
  now returns "attn" when lb_number is resolved but rename or lbdir are still mute. (3)
  lbdir_retrieve accepts lb_number_hint in the request body; handleRetrieve passes
  row.steps.lookup.lb_number as the hint.

BUG-145: batch_verify --skip-done silently preserves api_error/retrieve_error from transient backend failures
Status: Fixed
File(s): tools/batch_verify.py:1007-1009
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: --skip-done skips any folder with any stored result, including api_error and retrieve_error. A transient backend crash (run 15, 2026-06-04 18:52–19:00) wrote ~9,300 api_error/retrieve_error rows with notes=''. Subsequent runs with --skip-done preserved these stale results indefinitely; only way to fix was --reprocess api_error,retrieve_error.
Fix: When --skip-done is active, api_error and retrieve_error are automatically added to reprocess_set so they are always reprocessed regardless of prior result.

BUG-144: tapematch Pass 1 OOM — stereo ingest + mono copy peaks at ~1.2 GB per source
Status: Fixed
File(s): tools/tapematch/tapematch/cli.py:57-98
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: concat_source loaded stereo (shape N×2, ~776 MB for a 2h show at 16 kHz).
  performance_envelope then called to_mono() which allocated a second mono copy (~388 MB).
  Both lived simultaneously, peaking at ~1.16 GB per source. For 1990-06-02 with 6 sources,
  the tapematch CLI subprocess was OOM-killed after completing the first source (LB-12209)
  and starting the second (LB-12888). Orphaned tmp dir left at /mnt/DATA0/tmp/tapematch_f9d_8xw7.
Fix: Changed ingest to mono=True always. to_mono() now returns a zero-cost view. Trimmed
  slice written directly to memmap via ravel() view — no third heap array. Peak per source
  drops from ~1.2 GB to ~500 MB.

BUG-143: Verify — filenames with curly/smart apostrophes don't match disk files
Status: Fixed
File(s): backend/checksum_utils.py:_parse_checksum_file, verify_folder, parse_lbdir_file, verify_folder_lbdir
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: Checksum files (e.g. created by EAC) can use typographic RIGHT SINGLE QUOTATION MARK (U+2019) in filenames like "04 Talkin' New York.flac", while the actual files on disk use a straight apostrophe (U+0027). The string comparison used as dict keys failed silently, causing both a "disk-only extra" row and a "checksum-only missing" row.
Fix: Added _norm_fname() using str.maketrans to normalise U+2018/2019/201B/02BC/02B9 → U+0027. Applied to disk_audio_map keys in verify_folder and to all filenames parsed in _parse_checksum_file. Extended to parse_lbdir_file (md5/ffp/shntool/shntool_len sections) and verify_folder_lbdir (normalised _disk_audio_map + _subdir_index replace bare folder/fname lookup).

BUG-142: Pipeline — apply rename renames folder but does not write rename_log.txt
Status: Fixed
File(s): backend/app.py:4920
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: The /api/folder/rename route performed folder.rename() without calling write_rename_log(), so no rename_log.txt was created inside the folder and no rename_history DB row was inserted.
Fix: Import write_rename_log in folder_rename() and call it with source='pipeline' before the os-level rename, matching the pattern used by /api/rename/apply.

BUG-141: Verify — shntool-format .md5 entries for FLAC files show as "Missing" duplicates
Status: Fixed
File(s): backend/checksum_utils.py:435-444
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: _SHNTOOL_LINE_RE only matches .wav filenames, so "hash  [shntool]  file.flac" lines from externally-run shntool fell through to _MD5_RE, which captured "[shntool]  file.flac" as the literal filename. These bogus keys didn't match disk files → "Missing", doubling the TOTAL count.
Fix: In _parse_checksum_file, after _MD5_RE matches, detect a [shntool] prefix in the captured filename, strip it, and store the entry as 'shntool' type instead of 'md5'.

BUG-140: Lookup — adding a folder once shows it twice in sources list
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLookup.tsx:129-145, 247, 265
Reported: 2026-06-05
Fixed: 2026-06-05
Root cause: handleSingleFolder and handleFolders called addSource without checking if the folder was already present. The useEffect queue-sync also added folders asynchronously after a fetch, but checked for duplicates synchronously before the fetch — so if a folder was manually added while the sync fetch was in-flight, the sync's .then() would add it a second time. Together these two paths produced duplicates whenever a folder existed in both the shared queue store and was manually added on the Lookup tab.
Fix: Added path-based dedup guard at the start of handleSingleFolder and handleFolders (skip if path already in sources). Also re-check inside the useEffect's .then()/.catch() callbacks so the async race no longer causes duplicates.

BUG-139: LBDIR renames table — current path column collapsed to ~24px
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLBDIR.tsx:158-167
Reported: 2026-06-04
Fixed: 2026-06-04
Root cause: colgroup had 6 <col> entries but TR component auto-injects a 3px edge-bar <td>, giving 7 actual columns. With tableLayout:fixed the disk_rel path column (col 4) was mapped to the 24px arrow <col>, truncating filenames to "1..".
Fix: Added <col style={{width:32}}/> for the checkbox column and a matching <TH> in the header, shifting disk_rel to the correct auto-width col.

BUG-138: verify_folder_lbdir _norm uses full path — patch track and multi-LB bare-filename lbdirs mismatch
Status: Fixed
File(s): backend/checksum_utils.py:654-657
Reported: 2026-06-04
Fixed: 2026-06-04
Root cause: _norm in verify_folder_lbdir normalized full paths (Disc2/dead_dylan2003.8.05.d2t04.shn), so the shntool key for the patch track (incorrectly assigned to Disc2/ by the section parser) did not match the md5 canonical key (dead&dylan2003.8.05.d2t04.patch/dead&dylan2003.8.05.d2t04.shn). Also, LBF-01334 lbdirs list bare filenames; when used against a combined multi-LB folder where audio is in Disc3/, the files were not found.
Fix: (1) _norm now strips the directory component and uses basename only before normalizing, so disc-prefix differences never block remapping. (2) verify_folder_lbdir builds an audio-only subdir index and falls back to it when a bare-filename lbdir entry is not found at the exact path — only for audio extensions, preventing ambiguous non-audio name matches (checksum.md5).

BUG-137: lookup_checksums base grouping fails for SHN sets with & → _ and disc prefix differences
Status: Fixed
File(s): backend/db.py:1431-1453
Reported: 2026-06-04
Fixed: 2026-06-04
Root cause: BUG-130's fix grouped DB entries by _AUDIO_EXT_RE.sub('', filename).lower() to unify foo.shn and foo.wav as the same track. But the DB stores SHN entries as Disc1\dead&dylan2003.*.shn (with disc prefix and &) and shntool WAV entries as dead_dylan2003.*.wav (bare filename, & replaced by _ by shntool). The bases Disc1\dead&dylan2003.7.29.d1t01 and dead_dylan2003.7.29.d1t01 do not match, so all 26 shntool WAV entries for LB-1332 were counted as uncovered tracks and the set showed INCOMPLETE instead of MATCHED.
Fix: Added _norm_track_base() which strips the directory prefix and replaces & with _ before grouping. Now Disc1\dead&dylan2003.*.shn and dead_dylan2003.*.wav both normalize to dead_dylan2003_* and are correctly treated as the same track.

BUG-135: LBDIR shows phantom "Missing" rows for all SHN disc-subdirectory entries
Status: Fixed
File(s): backend/checksum_utils.py:136-199
Reported: 2026-06-04
Fixed: 2026-06-04
Root cause: parse_lbdir_file ignored the subdirectory context embedded in shntool section headers ("=== shntool md5/hash for: archive\Disc1"). Shntool entries list bare filenames (dead_dylan2003.*.wav) without the Disc1/ prefix. The _norm remap in verify_folder_lbdir requires matching normalized keys between md5_map (Disc1/dead&dylan2003.*) and shn_map. Without the prefix, "disc1_dead_dylan2003_*" != "dead_dylan2003_*", so all 26 shntool entries for a 3-disc SHN set added phantom underscore-named files to all_files that didn't exist on disk.
Fix: parse_lbdir_file now extracts the subdirectory path from shntool section headers via _shn_dir_from_header() and prepends it to each file entry in that section.

BUG-131: Lookup tab folder list not synced with shared folder queue
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLookup.tsx:119-138
Reported: 2026-06-04
Fixed: 2026-06-04
Root cause: ScreenLookup never subscribed to useFolderQueueStore, so folders added on Verify/Pipeline/LBDIR tabs were invisible to it. Every other tab reads the shared store.
Fix: Added useFolderQueueStore subscription and a useEffect that scans+adds any queue folder not already present as a source.

BUG-130: Lookup shows SHN sets as Incomplete due to missing shntool WAV checksums
Status: Fixed
File(s): backend/db.py:1422-1448
Reported: 2026-06-03
Fixed: 2026-06-03
Root cause: The DB stores both MD5 checksums of .shn files (chk_type='m', filename='foo.shn') and shntool checksums of the decoded WAV (chk_type='s', filename='foo.wav') for the same track. The completeness check counted unmatched checksums by hash value only, so if the user provided MD5s of their SHN files (matching the 'm' entries), the 18 'wav' shntool entries were marked as missing — incorrectly flagging a fully-owned SHN set as INCOMPLETE.
Fix: Completeness check now groups DB entries by base filename (stripping audio extension). A track is covered if ANY of its checksums was matched; foo.shn (md5) and foo.wav (shntool) sharing the same base are treated as the same track.

BUG-129: Lookup LB summary shows "Not Found" (red) instead of "Incomplete" (orange) for incomplete SHN sets
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenLookup.tsx:35
Reported: 2026-06-03
Fixed: 2026-06-03
Root cause: apiStatusToState() handled 'MATCHED (INCOMPLETE)' (per-row status) but not 'INCOMPLETE' (LB-level summary status from backend). The fallback returned 'notfound', showing a red "Not Found" pill even though the checksums were matched in the DB.
Fix: Added if (status === 'INCOMPLETE') return 'incomplete' before the NOT FOUND branch.

BUG-128: LBDIR Process silently replaces lbdir with updated cache version; has_lbdir misses LBF-format files
Status: Fixed
File(s): backend/app.py:2134-2136, tools/batch_verify.py:305-307, gui_next/src/renderer/src/screens/ScreenLBDIR.tsx:47-51
Reported: 2026-06-03
Fixed: 2026-06-03
Root cause: (1) lbdir_retrieve always called shutil.copy2 regardless of whether an lbdir already existed in the folder, so if the attachments cache was updated (re-scraped) after batch_verify ran, clicking Process would silently swap in a different lbdir version with more entries, making previously-passing folders appear as missing_files. (2) has_lbdir in batch_verify used case-sensitive glob "lbdir*.txt" which never matched LBF-*-lbdir.txt files on Linux, causing unnecessary retrieve calls and masking the presence of the file. (3) Pre-check folder dot was green for any stale lbdir_verified_at timestamp.
Fix: (1) lbdir_retrieve now checks _find_lbdir_in_folder first and returns already_present without overwriting. (2) has_lbdir now uses iterdir+lower() matching _find_lbdir_in_folder. (3) Pre-check dot color changed from var(--lbb-ok-bar) to var(--lbb-fg3).

BUG-127: batch_verify misclassifies folders with missing files as api_error
Status: Fixed
File(s): tools/batch_verify.py:66
Reported: 2026-06-03
Fixed: 2026-06-03
Root cause: _VERIFY_STATUS_MAP mapped "incomplete" → STATUS_MISSING_FILES but verify_folder_lbdir (checksum_utils.py:736) returns "missing_files" when n_missing > 0. The unmapped key fell through to the default STATUS_API_ERROR, making every folder with a missing lbdir entry appear as api_error with notes=None.
Fix: Added "missing_files": STATUS_MISSING_FILES to _VERIFY_STATUS_MAP.

BUG-126: tapematch session uses stale last_results.json when tapematch crashes mid-run
Status: Fixed
File(s): tools/tapematch/tapematch_session.py:669
Reported: 2026-06-02
Fixed: 2026-06-02
Root cause: last_results.json was not cleared before running tapematch; if tapematch crashed early (before writing new results), the file from the prior run survived and was read in step 7, causing insert_sources/insert_pairs to iterate folder names from the wrong concert date
Fix: unlink last_results.json (missing_ok=True) immediately before run_tapematch() call

BUG-125: tapematch trim.performance_envelope crashes with TypeError on recordings with no detectable silence tail
Status: Fixed
File(s): tools/tapematch/tapematch/trim.py:63
Reported: 2026-06-02
Fixed: 2026-06-02
Root cause: end_i computed as len(is_music)-1 - _first_sustained(reversed) before the None guard; _first_sustained returns None when no sustained music region is found in reversed signal (e.g. vinyl rips that end mid-music); TypeError: unsupported operand type(s) for -: 'int' and 'NoneType'
Fix: assign to end_raw first, check for None, then compute end_i = len(is_music)-1 - end_raw

BUG-124: tapematch trim report shows negative tail time
Status: Fixed
File(s): tools/tapematch/tapematch/cli.py:54
Reported: 2026-06-02
Fixed: 2026-06-02
Root cause: trim_bounds stored rep["total_sec"] (sum of native-rate durations via soundfile/ffprobe)
  but s1 from performance_envelope is clamped to len(stream)/sr (resampled frame count). These differ
  by up to ~26s per source. When resampled > native-rate total, total_sec - s1 < 0, and Python's
  floor division on negatives makes fmt_hms wrap around (e.g. -2s renders as "-1:59:58").
Fix: compute stream_dur = len(stream)/sr after concat_source and use it for both trim_bounds
  and the no_trim s1 fallback, so total_sec and s1 share the same frame-count basis.

BUG-123: tapematch source duration non-deterministic for formats without container duration field
Status: Fixed
File(s): tools/tapematch/tapematch/audio.py:43
Reported: 2026-06-02
Fixed: 2026-06-02
Root cause: _ffprobe_info fallback (SHN, MP3, etc.) runs "ffmpeg -stats -f null" and uses
  re.search to find the first "time=" match in stderr. ffmpeg emits multiple progress lines;
  the first match is an early intermediate timestamp, not the final decode position — giving
  a shorter-than-actual duration that varies with CPU/IO speed between runs.
Fix: use re.findall and take matches[-1] (the last progress update = true total duration).

BUG-122: tapematch fills system tmpfs with memmap files
Status: Fixed
File(s): tools/tapematch/tapematch/cli.py:37
Reported: 2026-06-02
Fixed: 2026-06-02
Root cause: tempfile.mkdtemp() with no dir= argument writes to /tmp (system tmpfs); ~438 MB per source × N sources exhausts the tmpfs, crashing the run and Claude Code's own /tmp buffer.
Fix: Pass dir=/mnt/DATA0/tmp (created if absent) to mkdtemp so memmaps land on the data drive.

BUG-161: Pipeline Collect "Confirmed" date never updates on LBDIR pass for owned folders
Status: Fixed
File(s): backend/app.py:5197-5201
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: The Collect stage's "Tag in the collection" preview shows a "Confirmed" row
  sourced from my_collection.lbdir_verified_at (CollectDetail.tsx TagTable, fed via
  step.lbdir_verified_at). The /api/pipeline/run LBDIR step (step 4) computed a "pass"
  result but never called database.set_lbdir_verified(), so for an already-owned folder
  that's re-checked in place, lbdir_verified_at was never refreshed and "Confirmed"
  stayed stuck on "Not yet confirmed" (or a stale date) even after a fresh Pass.
Fix: When the pipeline LBDIR step result is "pass", call database.set_lbdir_verified
  (str(folder)) — same call already used by /api/lbdir/verify. It's a no-op (rowcount 0)
  if the folder has no matching my_collection.disk_path row (not yet filed), so
  not-yet-filed folders still correctly show "Not yet confirmed". Step 5 (file) already
  re-queries lbdir_verified_at after step 4 runs, in the same request, so the updated
  timestamp is picked up immediately.

BUG-160: rename_history.renamed_at stored in UTC instead of local time
Status: Fixed
File(s): backend/db.py:add_rename_history, backend/db.py:init_db
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: The `rename_history` table's `renamed_at` column relied on SQLite's
  `DEFAULT CURRENT_TIMESTAMP`, which SQLite always evaluates in UTC. Meanwhile
  rename.py's rename_log.txt entries used `datetime.now()` (local time), so the
  two records of the same event disagreed by the local UTC offset.
Fix: `add_rename_history()` now computes and inserts an explicit local-time
  timestamp (`datetime.now()`), overriding the UTC default. Added a one-time
  migration in `init_db()` (gated by meta key `rename_history_localtime_v1`)
  that converts existing `renamed_at` values from UTC to local time via
  SQLite's `datetime(renamed_at, 'localtime')`.

BUG-159: LBDIR status stuck on "Extra files" after extras moved to extras/ and rename logged
Status: Fixed
File(s): backend/checksum_utils.py:verify_folder_lbdir
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: BUG-158 made verify_folder_lbdir() scan the whole folder recursively for files not
  claimed by the lbdir manifest. After a user reconciles a folder (move_extras relocates strays
  to extras/, and a rename appends rename_log.txt), those two now-expected artifacts were still
  counted as "extra", so `status` stayed 'extra_files' (warn) forever and pipeline step 4 never
  turned green even though the folder was fully reconciled.
Fix: Added `_is_reconciled_extra()` — unclaimed files under `extras/` or named `rename_log.txt`
  are excluded from `extra_names`/`extra` count. If those are the only unclaimed files, status
  now resolves to 'pass' (green); any other stray file still yields 'extra_files'.

BUG-158: LBDIR check — extra files on disk not detected unless another problem already exists
Status: Fixed
File(s): backend/checksum_utils.py:verify_folder_lbdir; backend/app.py (pipeline lbdir step);
  gui_next/src/renderer/src/lib/lbdirStore.ts; gui_next/src/renderer/src/screens/ScreenLBDIR.tsx;
  gui_next/src/renderer/src/screens/ScreenPipeline.tsx;
  gui_next/src/renderer/src/components/pipeline/LbdirDetail.tsx
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: verify_folder_lbdir() only iterated files referenced in the lbdir's md5/ffp/shntool
  sections and hardcoded `'extra': 0`, never scanning disk for unreferenced files. As long as
  every lbdir-listed file was present and matched, status was 'pass' (green), and the GUI's
  canReconcile gate (status !== 'pass') skipped /api/lbdir/reconcile entirely — so extra files
  were silently invisible. They were only surfaced as a side effect of find_reconcilable_files's
  unmatched_disk once a missing/mismatched file already made canReconcile true.
Fix: verify_folder_lbdir now tracks which on-disk paths are claimed by an lbdir entry, scans the
  folder recursively for unclaimed files (excluding the lbdir manifest itself), appends them to
  `files` with overall='extra', and reports the real `extra` count. Added a new 'extra_files'
  status (between missing_files/fail and pass in priority) so a folder with otherwise-clean
  checksums but stray files no longer shows green and now triggers the reconcile/move-to-extras
  flow. Updated the pipeline lbdir step label, GUI LbdirState type + STATE_LABEL maps in
  ScreenLBDIR/ScreenPipeline, and LbdirFileTable's row styling for overall='extra' (was
  mis-rendered as a red "Fail").

BUG-157: Pipeline — "File into collection" succeeds but My Collection screen doesn't show the new entry
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:1488-1521
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: applyFile() POSTs to /api/pipeline/file, which moves/copies the folder and inserts a
  my_collection row (verified directly in data/losslessbob.db — the LB-16298 row and dest path
  were correct). The My Collection screen reads from a single react-query cache keyed
  ['collection-prefetch'] with staleTime: Infinity, refreshed only via queryClient.invalidateQueries.
  applyFile never called invalidateQueries, so if the Collection screen's cache was already warm
  from earlier in the session, it kept showing the pre-filing snapshot — the newly filed LB
  appeared as "not in collection" even though the DB and filesystem were correct.
Fix: Imported useQueryClient in ScreenPipeline and called
  queryClient.invalidateQueries({ queryKey: ['collection-prefetch'] }) after a successful
  /api/pipeline/file result, so the My Collection screen refetches and shows the new entry.

BUG-156: Pipeline — folder shows "In collection"/"Filed to X" before Collect step is run
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenPipeline.tsx:140-163
Reported: 2026-06-11
Fixed: 2026-06-11
Root cause: backend/app.py severity logic (app.py:5278) returns "done" once
  verify/lookup/rename/lbdir all pass, regardless of the file (Collect) step's
  status — by design, "ready" doesn't change severity so the row keeps its
  per-row File button. serverRowToPipeline mapped severity "done" straight to
  bucket 'done', and deriveFolderStatus treats bucket 'done' as "In collection" /
  "Filed to <mount>" unconditionally. Result: the detail panel correctly showed
  Collect as "Action — File into collection" while the list/status badge claimed
  the folder was already filed.
Fix: serverRowToPipeline now reclassifies bucket 'done' as 'shelf' when the
  normalized file step status is 'warn' (i.e. backend file.status == "ready",
  not yet filed). The existing 'shelf' bucket already renders "Ready to file" /
  "Archive-clean — file into the collection" via deriveFolderStatus and is
  counted in the "Ready to file" banner pill / "File all N into collection"
  action, so no new UI states were needed.

BUG-134: Map screen — blank center canvas with no fallback when tiles fail to load
Status: Fixed
File(s): gui/resources/map.html
Reported: 2026-06-04
Fixed: 2026-06-09
Root cause: Leaflet tile requests to OpenStreetMap silently fail when offline. No overlay or message indicates this; the center area renders blank white. Left/right sidebars (filters, venue list) are unaffected.
Fix: Added tileerror/tileload listeners on the tile layer; tileerror shows a "Map tiles couldn't load — check your internet connection" banner overlay (z-index 1000, pointer-events:none, bottom-anchored) inside #map; tileload hides it again if tiles subsequently succeed.

BUG-133: DB Editor — pagination bar and action buttons render before any table is selected
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:1582-1679
Reported: 2026-06-04
Fixed: 2026-06-09
Root cause: currentTable is initialised to '' and total to 0. Math.max(1, Math.ceil(0/limit)) = 1, so the bar renders "Page 1/1 (0 rows total)" and all action buttons (Commit, Discard, Delete Selected, Export CSV, SQL Query) are visible even though no table has been loaded. Looks like the selected table has 0 rows rather than no table being selected.
Fix: Wrapped both the pagination row and action row in {currentTable && (<>...</>)} so they only render once a table is chosen.

BUG-132: Attachments — empty-state message misleads user after auto-load finds no entries
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenAttachments.tsx:279
Reported: 2026-06-04
Fixed: 2026-06-09
Root cause: loadTree() fires automatically on mount. If the cache is empty, busy clears and entries.length === 0 shows "Click Refresh tree to load" — implying the user needs to act when the data is genuinely absent.
Fix: Added hasLoaded state (false until loadTree's finally block runs). Empty-state message now shows "Loading…" until hasLoaded is true, then "No attachments cached yet" when entries is empty, and "No matches" when a filter reduces a non-empty list to zero.

BUG-111: Forum post description shows checksum file contents instead of entry description
Status: Fixed
File(s): backend/forum_poster.py:268-279
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: _read_lb_txt picked the first .txt file alphabetically. Entries with .ffp.txt fingerprint files (e.g. LBF-12220-Bob-Dylan-May-1960.ffp.txt) sorted before the actual info txt file, so checksum hashes landed in the forum post description section. Additionally, when multiple plain .txt files exist, the main info file (which contains LB-NNNNN in its name) sorted after short filenames like Note.txt.
Fix: Changed suffix filter to f.suffixes == ['.txt'] to exclude double-extension files (.ffp.txt, .md5.txt etc). Added a preference step: if any candidate contains LB-{lb_number} in its name, use that file first; otherwise fall back to the alphabetically first candidate.

BUG-110: TOCTOU race in background-task start routes allows double workers
Status: Fixed
File(s): backend/app.py:2033,4000,4099,4156
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: The "already running" guard for spectrogram generate, fingerprint build, dup scan, and identify-folder all checked status inside the lock but released the lock before starting the thread. Two concurrent POST requests could both see "idle", both pass the guard, and both start worker threads simultaneously. Additionally, the guard checked only status=="running", missing the "scanning" state emitted by build_fingerprint_db during its folder-discovery phase.
Fix: Inside the lock, immediately after the guard, set status="running" to claim the slot atomically. Changed guard to `status not in ("idle", "done", "error")` to block all non-terminal states.

BUG-109: Crashed background workers leave status permanently stuck at "running"
Status: Fixed
File(s): backend/app.py:_do_fp_build,_do_fp_dup_scan,_do_fp_identify_folder,_do_spectro_batch
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: None of the four background worker functions had a top-level exception handler. A crash (e.g., import error, unexpected exception) would leave the state dict at status="running" forever, preventing any future invocation from passing the guard. This was a latent issue; BUG-110's fix (pre-marking status inside the lock) made it immediately observable.
Fix: Wrapped each worker body in try/except; on exception, sets status="error" with the exception message via the per-worker _set helper.

BUG-108: All attachment entries shown as stale regardless of download state
Status: Fixed
File(s): backend/app.py:626
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: attachments_cached response omitted the "downloaded" field from each file object. Frontend stale check (f.downloaded === 1) always saw undefined, so every entry with files evaluated to "stale".
Fix: Added "downloaded": r["downloaded"] to the file dict in attachments_cached.

BUG-107: Attachment viewer always shows 404 for text/html/image files
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenAttachments.tsx:134,198
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: Frontend passed activeFile.filename (raw LBF-prefixed name) to /api/attachment/<lb>/<name>, but the backend route queries entry_files WHERE clean_name=? — the LBF- prefix caused every lookup to miss.
Fix: Changed both the text-content fetch and fileUrl to use activeFile.clean_name || activeFile.filename.

BUG-121: Pipeline lookup not found — LB-12347 (Farm Aid) checksums pass verify but have no DB match
Status: Fixed
File(s): backend/db.py:audit_collection_checksums, backend/app.py:collection_audit
Reported: 2026-05-31
Fixed: 2026-06-01
Root cause: Entries added to my_collection via folder-link or manual add have no corresponding rows in the checksums table. The DB record exists but the lookup index is incomplete, so verify passes (using on-disk .ffp/.md5) but lookup returns nothing.
Fix: Added GET /api/collection/audit endpoint and audit_collection_checksums() DB function. Returns {total, missing_checksums, entries:[...]} listing every collection entry with zero checksum rows, so the user can identify and re-import affected entries.

BUG-119: Pipeline rename — NFT private entries with no date/location produce bare LB-NNNNN-NFT
Status: Fixed
File(s): backend/app.py:4638
Reported: 2026-05-31
Fixed: 2026-06-01
Root cause: build_standard_name falls back to "LB-NNNNN" when date_str or location is empty in the entries table, then apply_nft_suffix appends -NFT. Result is "LB-08985-NFT" even though the folder contains date and location in its name. Accepting the rename proposal would silently strip the date and location from the folder name.
Fix: In _pipeline_process_folder rename step: when date_str or location is absent from DB, use current folder name (NFT suffix stripped) as the base and apply_nft_suffix to toggle the -NFT marker — never touching the date/location portion of the name.

BUG-117: Pipeline — ~12% of collection folders have no checksum files on disk
Status: Fixed
File(s): backend/app.py:4604
Reported: 2026-05-31
Fixed: 2026-06-01
Root cause: The pipeline lookup step used folder.iterdir() (top-level only) to find .ffp/.md5/.st5 files, while verify_folder uses rglob for audio. When checksum files sit in a subfolder, verify finds the audio but the lookup step misses the checksum entirely, producing V:~ L:~ (Incomplete / No checksums) instead of a proper match.
Fix: Changed iterdir() to folder.rglob("*") with an is_file() + suffix check so checksums in subfolders are included.

BUG-111: LBDIR check inflates track count (16 instead of 7) for SHN recordings
Status: Fixed
File(s): backend/checksum_utils.py:615-632
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: shntool section filenames use underscores (shntool converts spaces→underscores), md5 section uses actual disk filenames with spaces. Union of both maps created duplicate entries per file.
Fix: verify_folder_lbdir() normalizes shntool-section keys by replacing underscores with spaces when a matching md5/ffp key exists, then remaps len_map the same way.

BUG-115: LBDIR check shows 0 total / spurious Pass for flat-format lbdir files (*.flacf.md5.txt)
Status: Fixed
File(s): backend/checksum_utils.py:200-204
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: parse_lbdir_file only collects entries inside known section blocks (=== MD5 for: / === FFP for:). Flat-format lbdir files (*.flacf.md5.txt, *.wavf.md5.txt) have no section headers — plain HASH  filename lines. The main pass left current_section=None throughout; all lines were skipped; md5/ffp/shntool all came back empty → all_files=set() → total=0 → status='pass' (false positive).
Fix: Added flat-format fallback after the section-based pass: if all three lists are still empty, re-scan the file treating each line directly as a MD5 or FFP entry (same logic as parse_checksum_file). Mode detection (shn/flac/mixed) is applied afterwards to the combined result.

BUG-114: LBDIR "Check all folders" crashes when any folder has missing files or no lbdir
Status: Fixed
File(s): backend/checksum_utils.py:576-582,676; backend/app.py:1999-2010; gui_next/src/renderer/src/lib/lbdirStore.ts:3; gui_next/src/renderer/src/screens/ScreenLBDIR.tsx:17-24
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: Three mismatch paths between backend status strings and the frontend STATE_LABEL record.
  1. backend emitted `status='incomplete'` (n_missing>0); frontend STATE_LABEL has no 'incomplete' key → `STATE_LABEL['incomplete'].tone` throws TypeError.
  2. backend emitted `status='shntool_missing'`; same missing-key crash.
  3. when no lbdir*.txt found, backend returned {folder, lb_number, error} with no mode/status/files fields; frontend's `checkResult.mode.toUpperCase()` threw on undefined.
Fix:
  - checksum_utils.py: 'incomplete' → 'missing_files'; parse-error early-return now returns full schema shape with status='no_lbdir'.
  - app.py: no-lbdir branch now returns complete schema with status='no_lbdir', mode='unknown', files=[].
  - lbdirStore.ts: added 'shntool_missing' to LbdirState union.
  - ScreenLBDIR.tsx: added shntool_missing entry to STATE_LABEL.

BUG-113: Pipeline scan-tree misses folders containing only SHN audio files
Status: Fixed
File(s): backend/app.py:4702
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: The _AUDIO extension set in pipeline_scan_tree() omitted '.shn', so folders containing only SHN files matched no extension and were silently excluded from the returned folder list.
Fix: Added '.shn' to the _AUDIO set on line 4702.

BUG-112: Detail panel shows "No forum history" when Forum posts count > 0
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenCollection.tsx:946-1342
Reported: 2026-05-31
Fixed: 2026-05-31
Root cause: forumBusy initialized to false so first render shows "No forum history" before fetch; fetch errors swallowed silently by .catch(()=>{}) leaving forumRecords=[] while row.historyForum (from prefetch) has count>0; copy-paste bug used loadingTorrents key in forum tab loading state
Fix: initialize forumBusy=true; add forumError state set in .catch and when API returns non-array; show error message instead of "No forum history" on failure; fix i18n key to loadingForum

BUG-111: Attachments screen blank-white crash — `total.toLocaleString()` on undefined
Status: Fixed
File(s): backend/app.py:641, gui_next/src/renderer/src/screens/ScreenAttachments.tsx:99
Reported: 2026-05-30
Fixed: 2026-05-30
Root cause: BUG-108 fix added r["downloaded"] to the file dict in attachments_cached but forgot to add ef.downloaded to the SELECT. The IndexError caused the route to return a 500 error response; the frontend then called setTotal(undefined), and total.toLocaleString() threw during render with no ErrorBoundary — blank white screen.
Fix: Added ef.downloaded to the SELECT in attachments_cached; added ?? 0 fallback to setTotal(d.total ?? 0) as defence against future backend errors.

BUG-110: bobdylan.com scraper stuck at 2000 — pending rows have swapped columns
Status: Fixed
File(s): data/losslessbob.db (bobdylan_shows table)
Reported: 2026-05-30
Fixed: 2026-05-30
Root cause: Older version of run_discover passed (date_str, url) instead of (url, date_str) to executemany INSERT; INSERT OR IGNORE then prevented correction on subsequent runs.
Fix: One-time UPDATE swapped bobdylan_url and date_str for all 2046 rows where scraped_at IS NULL AND bobdylan_url NOT LIKE 'http%'.

BUG-109: Lookup tab — "Add Folders" does not include checksum files, nothing is looked up
Status: Fixed
File(s): backend/app.py, gui_next/src/renderer/src/screens/ScreenLookup.tsx
Reported: 2026-05-28
Fixed: 2026-05-29
Root cause: handleFolders added folder sources with content:'', and handleLookupAll
  filtered out empty-content sources before running the lookup, so folder sources were
  never scanned or submitted.
Fix: Added POST /api/lookup/scan_folders backend endpoint that recursively finds .ffp,
  .md5, .st5, .sha1 files under given folders. handleFolders now calls this endpoint and
  stores the combined text as the source content, making it available to handleLookupAll.

---

BUG-108: LB directory — adding root folder fails with "no audio found"
Status: Fixed
File(s): backend/app.py
Reported: 2026-05-28
Fixed: 2026-05-29
Root cause: pipeline_scan_tree used root.rglob("*") which iterates descendants but never
  yields root itself. A flat folder (audio files directly in root, no subdirs) produced
  an empty found list, triggering the "No audio folders found" toast.
Fix: Added an explicit check of root before the rglob loop so root is included if it
  directly contains audio files.

---

BUG-107: Admin web UI status badge shows "disabled" after successful connection test
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenSetup.tsx
Reported: 2026-05-28
Fixed: 2026-05-29
Root cause: webUiTone was a derived constant driven solely by settings.web_password
  ('ok' if set, 'mute' otherwise). handleWebUiTest showed a toast but never updated
  the badge. The admin UI is always running so the badge defaulted to "disabled" for
  any user without a password configured.
Fix: Converted webUiTone to a useState variable initialised to 'ok' (always running).
  handleWebUiTest now calls setWebUiTone('ok') on success or 'warn' on failure.

BUG-107: Master update publish fails — 'sqlite3.Row' object has no attribute 'get'
Status: Fixed
File(s): backend/db.py:2533
Reported: 2026-05-27
Fixed: 2026-05-27
Root cause: generate_release_notes() called o.get("manual_notes") on a sqlite3.Row result; sqlite3.Row supports subscript access but not the dict .get() method.
Fix: Changed o.get("manual_notes") → o["manual_notes"]; sqlite3.Row returns None for NULL columns so the truthiness check still works correctly.

---

BUG-113: Hard-coded table backgrounds break theming
Status: Fixed
File(s): gui/lbdir_tab.py, gui/verify_tab.py (and other tab files)
Reported: 2026-05-24
Fixed: 2026-05-26
Root cause: Module-level colour aliases and class-level dicts captured QColor values at
  import time, so they never reflected theme changes after startup.
Fix: Removed all module-level and class-level colour caches; all call sites now
  reference styles.* inline at paint time via the theme-live refactor (commits
  e78e584f and 9327b2f4).

---

BUG-112: Master update install incorrectly restricted to Curator and allows downgrade
Status: Fixed
File(s): backend/db.py:import_master_db
Reported: 2026-05-24
Fixed: 2026-05-26
Root cause:
  1. Curator gate: The /api/master/import route already had "intentionally not
     curator-gated" (no code change needed); the GUI never gated install_master_btn
     behind curator mode either — the bug report was describing an obsolete state.
  2. Downgrade: import_master_db() had no comparison between the incoming snapshot's
     master_version timestamp and the locally installed one.
Fix: Added a downgrade guard (Step 2b) in import_master_db() that reads the current
  master_version from the meta table and raises ValueError if the incoming version
  string is lexicographically earlier (the format is YYYY-MM-DD_HHMMSS, so string
  comparison equals date comparison).

---

BUG-109: Map geocode layer not shown on load when Curator mode is already checked
Status: Fixed
File(s): gui/main_window.py
Reported: 2026-05-23
Fixed: 2026-05-26
Description: When the app starts with Curator mode already enabled, the geocoding and
  location-overrides panels on the Map tab remained hidden. Toggling the checkbox off
  and back on would make them appear.
Root cause: curator_mode_changed is emitted inside SetupTab.__init__ (via _load_curator_status)
  before MapTab is created and before the signal connection in _build_tabs is wired.
  The initial emission fires with no listeners, so MapTab starts with both curator
  panels hidden (setVisible(False)).
Fix: Added map_tab.set_curator_mode(setup_tab.curator_cb.isChecked()) immediately after
  connecting the signal in main_window.py._build_tabs(), so the current checkbox state
  is applied on every startup regardless of signal timing.

---

BUG-115: Fingerprint Build DB shows [0/0] with no feedback during folder scan
Status: Fixed
File(s): backend/fingerprint.py, gui/spectrogram_tab.py
Reported: 2026-05-24
Fixed: 2026-05-24
Description: Clicking "Build DB" with a large collection (15,967 folders) left the
  progress bar in indeterminate mode showing "[0/0]" for several minutes because
  build_fingerprint_db() collects all audio files before setting total.
Root cause: File-collection loop emitted no state updates until complete. For a large
  collection the scan can take several minutes, giving the appearance of being frozen.
Fix: Emit status="scanning" with folder count every 50 rows during collection;
  GUI handles the new status by updating the label without touching the queue widgets.

---

BUG-111: Snapshot install fails on AppImage — "must be in data/exports/ or data/imports/"
Status: Fixed
File(s): backend/app.py
Reported: 2026-05-24
Fixed: 2026-05-25
Description: When attempting to install a snapshot in the AppImage build, an "Install Failed"
  dialog was shown with the message "Snapshot must be in data/exports/ or data/imports/".
  The install worked correctly in non-AppImage (dev) runs.
Root cause: /api/master/import had an allowed_dirs check that compared the user-selected
  path against DATA_DIR / "exports" and DATA_DIR / "imports". In AppImage, DATA_DIR resolves
  to ~/.local/share/LosslessBob/data. A snapshot file placed anywhere else (e.g. ~/Downloads)
  failed the containment check, while the same path worked in dev because DATA_DIR was the
  project-relative data/.
Fix: Removed the allowed_dirs containment check entirely from /api/master/import.
  The route now only validates that the path has a .db suffix; any readable file is accepted.

---

BUG-110: Open data folder button does nothing on AppImage
Status: Fixed
File(s): gui/platform_utils.py, gui/setup_tab.py
Reported: 2026-05-24
Fixed: 2026-05-26
Description: Clicking the "Open data folder" button had no effect when running the AppImage
  build on Linux. The folder did not open in the file manager.
Root cause: open_folder() called subprocess.run(["xdg-open", ...], check=False). In AppImage
  environments the modified PATH may not include xdg-open, causing a FileNotFoundError that
  was silently swallowed by except Exception: pass in _on_open_folder.
Fix: Changed Linux path in open_folder() and open_file() to use
  QDesktopServices.openUrl(QUrl.fromLocalFile(p)) with xdg-open as a fallback. Also replaced
  except Exception: pass in setup_tab._on_open_folder with a _log.warning() call.

---

BUG-107: Soft-404 pages stored as entry descriptions
Status: Fixed
File(s): backend/scraper.py:177, backend/db.py:init_db
Reported: 2026-05-23
Fixed: 2026-05-23
Description: Archive server returns HTTP 200 with a 404 error HTML body for non-existent
  entries. Scraper parsed the error page text ("The requested URL was not found on this
  server.") as the entry description, resulting in 68 entries with garbage metadata.
Root cause: _fetch() only checked the HTTP status code; the server's soft-404 responses
  always returned 200 so the check was bypassed.
Fix: Added _is_soft_404() in scraper.py to detect the error text in HTML before parsing.
  Added one-time cleanup SQL in init_db() to fix existing affected rows.

---

BUG-116b: Public-page LB with no checksums misclassified as 'missing' in reconcile_all_lb_master
Status: Fixed
File(s): backend/db.py:reconcile_all_lb_master
Reported: 2026-05-25
Fixed: 2026-05-26
Description: reconcile_all_lb_master computed effective_max = max(checksums max, lb_master max).
  On a fresh install (no checksums, empty lb_master), effective_max=0 and the function returned
  early without reconciling any scraped entries.  LBs like LB-1506 (public page, no checksums)
  were left unclassified or stayed 'missing' after a full rebuild.
Root cause: effective_max did not consult the entries table — only checksums and lb_master.
Fix: Added entries_max = MAX(lb_number) FROM entries; effective_max = max(max_lb, master_max,
  entries_max).  Added regression test test_reconcile_all_no_checksums_public_entry in
  TestPublicNoChecksums (tests/test_db_writes.py).

---

BUG-116: Live scrape never re-checks entries previously marked missing
Status: Fixed
File(s): backend/scraper.py:143-147
Reported: 2026-05-24
Fixed: 2026-05-24
Description: LB-05126 (and potentially others) showed lb_status='missing' even though
  the archive page is publicly accessible and contains real metadata.  Subsequent live
  scrapes did not correct the status.
Root cause: scrape_entry() skip condition `not (use_local_pages and local_page.exists())`
  evaluated True whenever use_local_pages=False, causing ALL missing-status entries to be
  silently skipped during live network scrapes regardless of whether the page now exists.
  61 of 103 missing entries had locally cached pages with real content; all were invisible
  to normal scrape runs.
Fix: Condition changed to `use_local_pages and not local_page.exists()` — live scrapes
  always re-fetch missing entries; local-page mode only skips when no local file is present.
  LB-05126 repaired immediately by re-scraping from the existing local cache (now public).

---

BUG-114: Attachments tab causes "database is locked" via direct SQLite connection
Status: Fixed
File(s): gui/attachments_tab.py:94, backend/app.py
Reported: 2026-05-24
Fixed: 2026-05-24
Description: _RefreshTreeThread called get_connection() directly, opening a second
  SQLite write connection from a QThread while Flask/Waitress already held the WAL
  write lock. This caused sqlite3.OperationalError: database is locked on every
  attachments tab load.
Root cause: _reconcile() wrote directly to entry_files via a raw connection bypassing
  the Flask serialisation layer.
Fix: Added POST /api/attachments/reconcile and GET /api/attachments/cached endpoints
  in app.py. Rewrote _RefreshTreeThread to call these via HTTP (requests), removed all
  direct get_connection() usage and the backend.db import from attachments_tab.py.

---

BUG-090: Black screen flickers in app at certain times
Status: Fixed
File(s): main.py
Reported: 2026-05-20
Fixed: 2026-05-24
Description: Intermittent black screen flickers occurring during use; trigger conditions not
  fully isolated but consistently present. Suspected regression introduced during XWayland-related
  changes. Ruled out: _apply_shadows(), QT_XCB_GL_INTEGRATION=none.
Root cause: App was forcing QT_QPA_PLATFORM=xcb (XWayland); XWayland compositor interaction with
  Qt's rendering pipeline caused the flickers.
Fix: Changed default QT_QPA_PLATFORM from "xcb" to "wayland" in main.py so the app runs under
  native Wayland. User-set QT_QPA_PLATFORM env var still takes precedence.

BUG-108: DB Integrity reconcile fails with "database is locked"
Status: Fixed
File(s): backend/db.py, backend/db_queue.py, backend/scraper.py, backend/site_crawler.py,
         backend/app.py, backend/importer.py, backend/flat_file.py, backend/geocoder.py
Reported: 2026-05-23
Fixed: 2026-05-24
Description: Clicking "Reconcile All" showed "Error: internal_error". Backend logged
  sqlite3.OperationalError: database is locked on INSERT into lb_status_history inside
  batch_reconcile_lb_status. Underlying issue affected all write paths — any concurrent
  background threads could race for the SQLite WAL write lock.
Root cause: write_connection() opened a fresh sqlite3.connect() per call and issued
  BEGIN IMMEDIATE, so multiple threads could hold competing write connections simultaneously.
  No amount of locking within Python could prevent WAL-level contention between separate
  connection objects.
Fix: DB-09 — introduced DatabaseWriteQueue (backend/db_queue.py): a single persistent writer
  thread that holds ONE connection and serialises all writes via queue.Queue. All
  write_connection() call sites across all backend files migrated to get_write_queue().execute().
  write_connection() removed from db.py.

BUG-105: Windows release — master DB install fails with "internal_error"
Status: Fixed
File(s): backend/app.py
Reported: 2026-05-22
Fixed: 2026-05-23
Description: On the Windows release build, clicking Yes on the "Install Master Update?" confirmation dialog results in "Install Failed — internal_error". The backup and install process does not complete.
Root cause: Three stacked issues: (1) master_import route had an is_curator() guard blocking non-curator end users. (2) path_not_allowed check required snapshot to be in data/exports/ or data/imports/, blocking selection from USB drive or Downloads. (3) sqlite3.Error was not caught explicitly — any SQLite failure fell through to the generic handler returning bare "internal_error" with no message.
Fix: Removed is_curator() guard (export stays curator-only; import open to all). Removed directory containment check (kept .db suffix check). Added sqlite3.Error to caught exceptions with descriptive message. Added "message" field to generic internal_error response. Added import sqlite3 to app.py.

BUG-107: sqlite3.OperationalError: database is locked during crawler upsert_inventory
Status: Fixed
File(s): backend/db.py, backend/site_crawler.py
Reported: 2026-05-22
Fixed: 2026-05-23
Description: During a crawl, sqlite3.OperationalError: database is locked raised in upsert_inventory() when concurrent Flask request threads also write to the DB.
Root cause: upsert_inventory() called get_connection() directly and committed outside _write_lock, so concurrent writers (Flask pool + crawler) bypassed Python-level write serialisation. The inline entry_files update in site_crawler.py had the same flaw.
Fix: Replaced get_connection()+manual commit in upsert_inventory() with the write_connection() context manager, which acquires _write_lock. Same swap applied to the entry_files update in site_crawler.py; replaced now-unused get_connection import with write_connection.

BUG-104: Inno Setup build fails with "Unknown preprocessor directive" on standalone #13#10 lines
Status: Fixed
File(s): tools/losslessbob.iss:108
Reported: 2026-05-22
Fixed: 2026-05-22
Description: CI build-windows job failed (exit code 1) at the "Build installer" step.
Root cause: Inno Setup's ISPP preprocessor scans every source line before the Pascal parser.
  Lines that start with `#` (even after whitespace) are interpreted as preprocessor directives.
  Three lines in the [Code] section started with `#13#10 +` (bare blank-line expressions), which
  ISPP rejected as unknown directives.
Fix: Merged each standalone `#13#10 +` line onto the preceding string-literal line, so `#` no
  longer appears as the first token on any source line.

BUG-103: generate_release_notes queries non-existent columns from lb_master
Status: Fixed
File(s): backend/db.py:2140,2159
Reported: 2026-05-22
Fixed: 2026-05-22
Description: GitHub upload failed with "no such column: notes". The generate_release_notes function queried `notes` and `updated_at` from lb_master, neither of which exist.
Root cause: Wrong column names — lb_master uses `manual_notes` and `manual_set_at`.
Fix: Changed query to SELECT `manual_notes, manual_set_at` and updated the dict key reference from `o['notes']` to `o['manual_notes']`.

BUG-102: _fp_stop_dup_scan calls wrong endpoint and blocks main thread
Status: Fixed
File(s): gui/spectrogram_tab.py, backend/app.py
Reported: 2026-05-22
Fixed: 2026-05-22
Description: The "Stop" button for the duplicate scan called /api/fingerprint/build/stop
  (stopping the fingerprint BUILD instead) and ran requests.post on the main thread.
Root cause: Copy-paste error in endpoint URL; no _Worker used for the POST.
Fix: Call correct new /api/fingerprint/duplicates/scan/stop endpoint via _Worker. Added
  that endpoint to app.py. Added stop_requested to _fp_dup_state so the GUI can show
  "Stopping…" while the scan finishes its current SQL query.

BUG-101: Fingerprint build poll (QTimer) blocks main GUI thread
Status: Fixed
File(s): gui/spectrogram_tab.py
Reported: 2026-05-22
Fixed: 2026-05-22
Description: _fp_poll_build and _fp_poll_dup were QTimer callbacks that called
  requests.get synchronously on the main thread (up to 5 s per poll, every 800 ms),
  starving the event loop and making the app unresponsive while both operations ran.
Root cause: Wrong threading model — polling HTTP should never run on the main thread.
Fix: Replaced both QTimers with background QThread pollers (_FpBuildStatusThread,
  _FpDupStatusThread) that emit status_update signals, identical to the pattern used
  by _CrawlerStatusThread.

BUG-100: Crawler Start/Stop buttons block main GUI thread
Status: Fixed
File(s): gui/scraper_tab.py
Reported: 2026-05-22
Fixed: 2026-05-22
Description: _on_crawler_start called requests.post directly on the main thread
  (timeout=10 s); _on_crawler_stop also blocked (timeout=5 s). The main thread was
  unresponsive for the full timeout duration when either was clicked, preventing abort
  button presses from registering.
Root cause: Missing _Worker QThread wrapper for the start/stop HTTP calls.
Fix: Both methods now dispatch via _Worker. Added self._workers list to ScraperTab.
  Added _on_crawler_start_result / _on_crawler_start_error slots for the callback.

BUG-099: Fingerprint build "Stop" showed no immediate feedback
Status: Fixed
File(s): gui/spectrogram_tab.py
Reported: 2026-05-22
Fixed: 2026-05-22
Description: Clicking "Stop" on the fingerprint build disabled the button but left
  the label and progress bar unchanged, making it appear the stop had no effect. The
  build continued until the current file finished before the UI reset.
Root cause: _fp_stop_build only disabled the button; label update was missing.
Fix: _fp_stop_build now immediately sets the label to "Stopping…". _on_fp_build_status
  (the renamed poll slot) shows "Stopping… [N/M]" when stop_requested=True and
  distinguishes "Stopped." vs "Done." in the final message.

BUG-098: Curator checkbox shows an error dialog when toggled
Status: Fixed
File(s): gui/setup_tab.py, backend/app.py
Reported: 2026-05-21
Fixed: 2026-05-22
Description: Toggling the "Curator mode" checkbox triggered an error dialog
  ("Could not update flag: …"). Exact error was not captured; docstring also
  incorrectly claimed the method gated a "geocoder group."
Root cause: Three defensive/correctness issues: (1) curator_cb.toggled was connected
  before publish_master_btn was created — any unexpected signal emission during _build_ui
  would produce an AttributeError caught silently by the except block; (2) neither the
  GUI nor the Flask route logged the exception, so the real error text was lost; (3) the
  Flask route returned raw JSON as resp.text, making the dialog message cryptic.
Fix: Moved signal connection to after publish_master_btn exists. Added logging.exception
  in both the GUI except block and the Flask curator_set route. Parse Flask JSON error
  body in the GUI so the dialog shows a plain message. Fixed docstring.

BUG-097: Exported HTML collection table header appears mid-table (sticky broken)
Status: Fixed
File(s): backend/app.py:3398
Reported: 2026-05-21
Fixed: 2026-05-21
Description: In the exported HTML collection page, the sticky `thead th` header row
  was rendered at its natural DOM position instead of sticking below the page header
  bar as the user scrolled. It appeared to float in the middle of visible rows.
Root cause: `overflow-x:auto` on `.card` forces `overflow-y:auto` per CSS spec, making
  `.card` a vertical scroll container. A `position:sticky` element cannot escape its own
  scroll container — so the thead stuck within the card (which never actually scrolls
  vertically since it's auto-height), making sticky a no-op. `overflow:clip` has the same
  problem. There is no single CSS overflow value that enables horizontal scroll AND
  preserves border-radius clipping AND doesn't break vertical sticky.
Fix: Switched to flex-column viewport layout. `html/body` are `height:100%;overflow:hidden;
  display:flex;flex-direction:column`. `.card` fills remaining viewport with `flex:1;
  overflow:auto` and scrolls internally. `thead th{position:sticky;top:0}` sticks within
  `.card`'s scroll context. Removed `watchHdr()`, `--hh`, and `window.scrollTo` in `go()`.

BUG-096: Crawler status shows "idle" immediately after clicking Start Crawl
Status: Fixed
File(s): gui/scraper_tab.py:641
Reported: 2026-05-21
Fixed: 2026-05-21
Description: After clicking "Start Crawl" the status label would immediately revert to
  "Done — stage: idle" and the Start button re-enabled, while the crawler was actually
  running in the background unmonitored.
Root cause: Race condition — the _CrawlerStatusThread polls /api/crawler/status immediately
  on startup (no initial delay). If the first poll fires before the daemon crawler thread
  has executed its first line (_set(running=True, ...)), the status dict still has the
  default running=False / stage="idle" values. _on_crawler_status treated any running=False
  as a terminal condition and tore down the polling thread.
Fix: Guard the teardown with `stage != "idle"` so the poll thread ignores the pre-start
  idle state and only resets the UI when stage is a real terminal value (done/stopped/error).

BUG-095: scrape_range acquires write lock N×4 times per entry for lb_master reconcile
Status: Fixed
File(s): backend/scraper.py, backend/db.py
Reported: 2026-05-21
Fixed: 2026-05-21
Description: scrape_range called reconcile_lb_status() after every single scraped entry,
  each call acquiring the write lock and issuing 3 read queries + 1-2 write queries.
  For a full 13,000-entry scrape this was ~52,000 individual query round-trips just for
  lb_master housekeeping. The skip-check also used write_connection for purely read
  operations, and each attachment download opened its own write_connection for downloaded=1.
Root cause: reconcile_lb_status and the skip/download patterns were written for single-entry
  use; no batch path existed for bulk scrape runs.
Fix: Added batch_reconcile_lb_status() to db.py that reconciles N entries in one write
  transaction using IN-queries (4 queries total). scrape_entry gains _reconcile=False path;
  scrape_range batches reconcile every 100 entries and at stop/finish. Skip-check switched
  to get_connection for reads + executemany for the downloaded flag update. Attachment
  download loop replaced N individual write_connection calls with one executemany.

BUG-094: SQLite "database is locked" errors during concurrent scrape + fingerprint
Status: Fixed
File(s): backend/db.py, backend/scraper.py, backend/app.py
Reported: 2026-05-21
Fixed: 2026-05-21
Description: When the scraper background thread and Flask request threads both attempted
  DB writes simultaneously, SQLite's busy_timeout (30 s) was occasionally exceeded,
  producing OperationalError: database is locked.
Root cause: Multiple threads (scraper, Flask/Waitress pool) holding separate thread-local
  WAL connections all competing to write. SQLite serialises writers via its own retry loop,
  but rapid write bursts (one per scraped entry × reconcile_lb_status) could exhaust the
  timeout. Additionally, sqlite3.connect() defaulted to timeout=5 (Python default) before
  the PRAGMA busy_timeout=30000 took effect on a brand-new connection.
Fix: Added threading.RLock() (_write_lock) and write_connection() context manager in
  db.py. All DML functions now acquire the lock before starting a write transaction,
  serialising writers at the Python level. Fixed sqlite3.connect(timeout=30) to align
  Python's handler with the PRAGMA.

BUG-093: Exported HTML collection shows no rows in browser
Status: Fixed
File(s): backend/app.py:_COLLECTION_HTML_TEMPLATE
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Export HTML (4.5 MB) renders the UI chrome correctly but the table body is
  always empty; stats pills never appear.
Root cause: `const SM` and `const BC` were declared after the boot IIFE in the embedded
  JS template, placing them in the temporal dead zone when the IIFE called mkStats() and
  draw(). Browser threw "Cannot access 'SM' before initialization", silently aborting
  after the two timestamp writes.
Fix: Moved both const declarations to immediately before the boot IIFE so they are
  initialized by the time boot() executes.

BUG-089: find_duplicate_recordings reports too many false-positive duplicates
Status: Fixed
File(s): backend/fingerprint.py:426
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Duplicate scan flagged large numbers of unrelated recordings as duplicates.
Root cause: find_duplicate_recordings() counted raw hash collisions between track pairs.
  Any two files sharing similar spectral content (same key, similar instrumentation) could
  accumulate 20+ raw hits even with no temporal alignment, passing MATCH_THRESHOLD.
  identify_file() correctly used temporal coherence (peak bin count per offset-delta),
  but find_duplicate_recordings() did not.
Fix: Replaced the flat GROUP BY (ta, tb) COUNT(*) query with a nested query that first
  bins matches by ROUND(a.time_offset - b.time_offset, 1) and then takes MAX(bin_count)
  as the pair score, matching the identify_file() algorithm.

BUG-088: fingerprint_file fails with "No module named 'numpy'"
Status: Fixed
File(s): backend/fingerprint.py, requirements.txt
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Every fingerprint_file() call failed with "No module named 'numpy'".
  numpy, scipy (new version), librosa (new version), soundfile (new version), and
  numba were not installed in the .venv despite being required by fingerprint.py.
Root cause: requirements.txt listed outdated versions of librosa/soundfile/scipy and
  omitted numpy and numba entirely; packages were never installed into the venv.
Fix: pip install numpy==2.4.6 librosa==0.11.0 soundfile==0.13.1 scipy==1.17.1
  numba==0.65.1; updated requirements.txt and PROJECT.md tech stack table.

BUG-087: Fingerprint DB Stats causes 10-second read timeout
Status: Fixed
File(s): backend/fingerprint.py:469
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Opening the Fingerprinting tab shows "Error: HTTPConnectionPool … Read timed out"
  in the Database Stats panel. The GET /api/fingerprint/stats endpoint triggered a full
  recursive rglob("*") scan across all collection folders on every call to compute
  coverage_pct, blocking the Flask thread until the 10-second GUI timeout fired.
Root cause: get_fp_stats() called _maindb.get_collection() then iterated p.rglob("*") on
  every folder to count audio files — O(n) filesystem walk, unbounded on large collections.
Fix: Removed the rglob scan; coverage_pct now returns None. The GUI already handles None
  gracefully (omits the "% of collection" suffix).

BUG-086: fingerprint.py _get_fp_conn missing timeout=30 and busy_timeout PRAGMA
Status: Fixed
File(s): backend/fingerprint.py:48
Reported: 2026-05-21
Fixed: 2026-05-21
Description: _get_fp_conn used sqlite3.connect() with default timeout=5s and no
  PRAGMA busy_timeout, unlike db.py's get_connection(). Under concurrent write load
  (e.g. fingerprint build + identify running together) this would raise
  OperationalError: database is locked after only 5 seconds.
Root cause: New module did not replicate the timeout fix applied to db.py (BUG-084).
Fix: Added timeout=30 to sqlite3.connect() and PRAGMA busy_timeout=30000.

BUG-085: identify_file used raw hash hit count instead of temporal coherence
Status: Fixed
File(s): backend/fingerprint.py:identify_file
Reported: 2026-05-21
Fixed: 2026-05-21
Description: identify_file counted raw fingerprint hash matches per track without
  checking that matched hashes agreed on a consistent time offset. Hash collisions
  across unrelated tracks could produce false high scores.
Root cause: Temporal coherence histogram (the key Shazam discriminator) was omitted
  from the initial implementation.
Fix: Now fetches time_offset from DB hits, computes db_offset - query_offset per
  (track_id, delta) bin, and uses the peak histogram bin count as the score.

BUG-084: Site crawler crashes with "database is locked" under concurrent writes
Status: Fixed
File(s): backend/db.py:434, backend/db.py:2662
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Thread-35 (crawl) raised sqlite3.OperationalError: database is locked
  on upsert_inventory() INSERT when the scraper or another writer held the DB lock.
  The crawler thread died entirely, causing the scraper to appear hung.
Root cause: sqlite3.connect() used the default timeout=5.0 seconds. In Python 3.12+,
  Python's own retry mechanism uses this value rather than deferring to PRAGMA
  busy_timeout=30000, so the 30-second intent was not honoured. Under concurrent
  write load (crawler + scraper both active), 5 seconds was insufficient.
Fix: Added timeout=30 to sqlite3.connect() to align Python's retry timeout with the
  PRAGMA. Added retry loop (3 attempts, 2s back-off) in upsert_inventory() so a
  transient lock does not crash the crawler thread.

BUG-092: Attachments tab still extremely slow and buggy after BUG-083 partial fix
Status: Fixed
File(s): gui/attachments_tab.py
Reported: 2026-05-20
Fixed: 2026-05-20
Description: Even after BUG-083's thread fix, the Attachments tab remained sluggish and
  unreliable: paging through 1000-item QTreeWidget pages was slow (thousands of QTreeWidgetItem
  C++ objects allocated per page turn), get_lb_statuses_batch() ran on the main thread on every
  page navigation blocking the UI, pagination state was fragile (selected item lost on page
  turn, _render_tree_page could be called from multiple code paths), and the search box only
  jumped-to not filtered.
Root cause: QTreeWidget is fundamentally the wrong widget for this volume of data. Allocating
  and destroying thousands of C++ QTreeWidgetItem objects per page render is inherently slow.
  The tree-with-children pattern also required eager child population — all file children were
  added even for collapsed nodes — compounding the cost.
Fix: Replaced QTreeWidget + pagination with QTableView backed by _LbModel(QAbstractTableModel).
  Qt only renders visible rows so all entries load without pagination. lb_status is now fetched
  via LEFT JOIN inside _RefreshTreeThread so no per-page main-thread DB call is needed.
  Files for the selected LB are shown in a QListWidget below the table, populated on selection.
  Proxy model (QSortFilterProxyModel) provides instant text filtering; no custom jump logic
  needed.

BUG-091: Setup tab flat file update requires app restart to reflect changes
Status: Fixed
File(s): gui/setup_tab.py:1208
Reported: 2026-05-20
Fixed: 2026-05-20
Description: After applying an updated flat file (downloaded and unzipped successfully), the Setup tab does not reflect the updated data until the app is exited and re-launched. The update appears to complete without error but the UI is not refreshed.
Root cause: _on_discover_done() called _load_flat_file_history() and stats_changed.emit() after
  the dialog closed, but never called _refresh_stats(). The stats_changed signal refreshes the
  main window status bar and other tabs, but the Setup tab's own db_stats_label (showing total
  checksums, LB entries, latest LB) is only updated by _refresh_stats() itself.
Fix: Added self._refresh_stats() call in _on_discover_done() immediately after
  _load_flat_file_history(), matching the pattern used by _on_import_status and _on_reset_finished.

---

BUG-083: Attachments tab extremely slow/laggy after site crawler migration
Status: Fixed
File(s): gui/attachments_tab.py
Reported: 2026-05-20
Fixed: 2026-05-20
Description: After migrating attachments storage to the site crawler, the Attachments
  tab became very slow to load and refresh. The cached view would freeze the GUI for
  several seconds on every open/refresh.
Root cause: Two issues: (1) _reconcile_site_files() was called on the main thread and
  iterated all 24 k+ files in SITE_FILES_DIR via os.scandir/iterdir, building a Python
  set, then issuing batched SQL UPDATE chunks — all blocking the UI. (2) _refresh_tree()
  also ran its DB query and data-grouping on the main thread, compounding the freeze.
Fix: Replaced _reconcile_site_files() filesystem scan with a single SQL UPDATE…IN(SELECT)
  join against site_inventory (O(index) instead of O(dir scan + 50 SQL statements)).
  Moved all DB work into _RefreshTreeThread(QThread) so the main thread stays responsive;
  _on_tree_data_ready() is called on completion and calls _render_tree_page() on the
  main thread. Also removed the HTTP call to /api/db/stats (replaced by a direct
  COUNT(DISTINCT lb_number) in the worker thread).

---

BUG-082: build_qm.py produced .qm files that load but return no translations
Status: Fixed
File(s): scripts/build_qm.py
Reported: 2026-05-20
Fixed: 2026-05-20
Description: QTranslator.load() returned True but every QCoreApplication.translate() call
  returned the English source string. The compiler was writing structurally invalid .qm files.
Root cause: Four bugs combined: (1) Wrong tag IDs — MSG_TRANSLATION=5 (correct: 3),
  MSG_SOURCE_TEXT=3 (correct: 6), MSG_CONTEXT=4 (correct: 7). (2) Wrong section layout —
  all data went into one 0x42 section instead of separate 0x42 Hashes + 0x69 Messages.
  (3) Per-record length prefix emitted (Qt does not use one — records start directly at the
  offset stored in the Hashes section). (4) Wrong ELF hash — shift was >> 23; Qt uses >> 24;
  elfHash_finish (0 → 1) was missing; hash must cover sourceText+comment, not sourceText alone.
Fix: Rewrote build_qm.py with correct two-section layout (0x42 sorted hash+offset pairs,
  0x69 message records), correct tag IDs from Qt 6 qtranslator.cpp enum, correct ELF hash
  (>> 24, elfHash_finish), and TAG_COMMENT (8) subtag included. Verified 1067/1067 per language.

---

BUG-081: Attachments tab shows no files downloaded by the site crawler
Status: Fixed
File(s): gui/attachments_tab.py, backend/site_crawler.py
Reported: 2026-05-19
Fixed: 2026-05-19
Description: The Attachments tab queries entry_files WHERE downloaded=1, but the site_crawler
  wrote files to data/site/files/ without ever setting entry_files.downloaded=1. Only the
  per-entry scraper.scrape_entry() updated that flag, so all 6,000+ crawler-downloaded files
  were invisible to the tab.
Root cause: site_crawler.py only wrote to site_inventory; it had no code to update entry_files.
Fix: (1) gui/attachments_tab.py — added _reconcile_site_files() called from _refresh_tree().
  It scans SITE_FILES_DIR and bulk-updates entry_files.downloaded=1 for all files present on
  disk, fixing existing data immediately.
  (2) backend/site_crawler.py — after saving a /files/ URL, now updates
  entry_files.downloaded=1 for the matching filename so future crawls stay in sync.

---

BUG-080: rglob("*") on main thread in Verify and lbdir "Add Root Folder" freezes UI
Status: Fixed
File(s): gui/verify_tab.py, gui/lbdir_tab.py
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Both _on_add_root_folder handlers traversed the selected directory tree using
  sorted(root_path.rglob("*")) synchronously on the Qt main thread. On Windows (NTFS, slower
  directory reads) or large archives this triggered an unresponsive-window timeout. Same pattern
  as BUG-034 which was fixed in collection_tab.py.
Root cause: No worker thread offloaded the filesystem traversal.
Fix: Added _AddRootWorker(QThread) to each tab. The worker runs the rglob scan and
  iterdir() audio-file check off the main thread, emitting finished(list[str]) on completion.
  _on_add_root_folder starts the worker and disables the button; _on_add_root_finished
  adds paths via _add_folder() (which deduplicates) and re-enables the button.

BUG-079: .st5 hashes parsed but never verified — stored under wrong dict key
Status: Fixed
File(s): backend/checksum_utils.py:verify_folder
Reported: 2026-05-19
Fixed: 2026-05-19
Description: .st5 files contain shntool-format MD5s and are parsed correctly by
  _parse_checksum_file (via _SHNTOOL_LINE_RE). However verify_folder stored them under
  expected[fname]['st5'] rather than ['shntool'], so shn_exp = exp.get('shntool') was
  always None, shntool verification was skipped, and st5_status was always 'na'. A folder
  with only a .st5 file (no .md5 shntool section) would get status='no_checksums'.
Root cause: The ext == '.st5' branch in verify_folder used a separate 'st5' key that no
  downstream verification code read from, while the verification code only checked 'shntool'.
Fix: .st5 entries now also set expected[fname]['shntool'] (when not already present from a
  .md5 file) and has_shntool_entries = True, so shntool verification runs normally.

---

BUG-078: /api/db/import POST route has no concurrency guard — concurrent imports corrupt state
Status: Fixed
File(s): backend/app.py:db_import
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Unlike every other long-running operation (scraper, geocoder, spectrogram, site
  crawler — all guarded with 409), start_import_async() was called unconditionally. Two rapid
  POST requests could start concurrent imports, corrupt _import_state, and double-execute the
  DB merge. The first to finish would delete temp_import.db; the second would then error.
Root cause: Missing "already running" guard before start_import_async().
Fix: Added get_import_status().get("running") check; returns 409 if True, matching the
  pattern used by all other long-running routes.

---

BUG-077: flat_file._DOWNLOADS_DIR uses relative path — wrong location if CWD ≠ project root
Status: Fixed
File(s): backend/flat_file.py:29
Reported: 2026-05-19
Fixed: 2026-05-19
Description: _DOWNLOADS_DIR = Path("data/downloads") resolved relative to the process CWD.
  In development (CWD = project root) this worked, but on a frozen/PyInstaller build or when
  launched from another directory, download_flat_file_release put zips in the wrong location,
  and diff_flat_file_release / apply_flat_file_release raised FileNotFoundError because the
  zip was not found at the CWD-relative path.
Root cause: flat_file.py did not import from backend.paths, unlike all other modules.
Fix: Imported DATA_DIR from .paths and changed to _DOWNLOADS_DIR = DATA_DIR / "downloads".

---

BUG-076: Admin "Restart Server" button restarted the entire app including the GUI
Status: Fixed
File(s): main.py, backend/app.py, backend/admin.html
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Clicking Restart Server on the admin page (e.g. from a phone) killed the PyQt6
  GUI window because os.execv replaced the whole process.
Root cause: admin_restart used os.execv unconditionally — no distinction between "restart
  only Flask" and "restart the whole process."
Fix: main.py now runs Flask via werkzeug make_server in a restart loop and registers
  request_flask_restart() as a callback. The route calls the callback instead of os.execv,
  so only the Flask server recycles; the GUI remains open.

---

BUG-075: Map shows only ~434 markers instead of ~9,700 (owned filter applied by default)
Status: Fixed
File(s): backend/app.py:api_map_data, gui/resources/map.html
Reported: 2026-05-19
Fixed: 2026-05-19
Description: The map loaded with almost no markers even with no filters applied.
Root cause: api_map_data() set owned=False when no 'owned' query param was present
  (request.args.get("owned") == "true" evaluates to False, not None).
  get_map_data() treats owned=False as "show non-owned only" (mc.lb_number IS NULL),
  filtering out ~9,300 entries. A secondary bug: the JS sent owned=1 but Flask
  checked for "true", so the Owned-only checkbox also never worked.
  A third bug: the JS popup read m.lb/m.date/m.status instead of the correct
  API field names m.lb_number/m.date_str/m.lb_status, causing all popups to show
  no LB number, no date, and all markers to render orange (unknown status).
Fix: api_map_data() now passes None (no filter) when owned param is absent;
  owned=True only when param is "true" or "1". JS corrected to send owned=true
  and to read correct field names from the API response.

---

BUG-074: Map shows garbage markers for low-confidence Nominatim geocodes
Status: Fixed
File(s): backend/db.py:get_map_data
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Low-confidence geocode results (e.g. "Japan 2001" → village in Indonesia, "1964 revisited" → Chicago tattoo studio) were shown as map markers because get_map_data only checked lat IS NOT NULL.
Root cause: The JOIN on location_geocoded did not filter by confidence, so low-quality matches with valid lat/lon coordinates were included.
Fix: Added AND geo.confidence != 'low' to the JOIN condition so low-confidence rows produce NULL lat/lon and fall into the unplottable bucket.

---

BUG-073: Location Geocoding panel shows "Unexpected response from server" on Load
Status: Fixed
File(s): gui/dbedit_tab.py:_on_geo_loaded
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Clicking Load in the Location Geocoding sub-panel always showed "Unexpected response from server." even when the API returned valid data.
Root cause: GET /api/geocode/locations returns {"locations": [...]} (a dict wrapper). _on_geo_loaded checked isinstance(data, list) which failed for a dict, hitting the error branch even on success.
Fix: Unwrap the "locations" key when data is a dict before the isinstance(list) check.

---

BUG-072: Bootleg scraper retrieves zero entries — picks title-banner table instead of data table
Status: Fixed
File(s): backend/bootleg_scraper.py:322
Reported: 2026-05-19
Fixed: 2026-05-19
Description: "Scrape Bootleg Catalog" always produced 0 rows_total despite the catalog page having ~1379 entries.
Root cause: The catalog page (LB-bootleg-by-title.html) has two <table> elements: a 1-row title banner and the data table. soup.find("table") returned the first (banner) table. rows[1:] on a 1-row table produces an empty slice → zero entries parsed.
Fix: Changed selector to find the table containing <th> header cells (the data table). Falls back to the last table if no <th> is found.

---

BUG-071: Geocode locations panel crashes — "no such column: location"
Status: Fixed
File(s): backend/app.py:2252
Reported: 2026-05-19
Fixed: 2026-05-19
Description: GET /api/geocode/locations returned sqlite3 OperationalError: no such column: location.
Root cause: ORDER BY clause used column name "location" but the table column is "location_text".
Fix: Changed ORDER BY location to ORDER BY location_text in api_geocode_locations().

---

BUG-070: Setup tab shows "Status: error — already running" on first geocoder run
Status: Fixed
File(s): gui/setup_tab.py:389, gui/setup_tab.py:1539
Reported: 2026-05-19
Fixed: 2026-05-19
Description: Clicking "Run Geocoder" immediately showed "Status: error — already running" even though the geocoder had never been started.
Root cause: _GeocodeRunThread emitted resp.json() for 409 responses ({"error": "already running"} with no status_code key). _on_geocode_started checked result.get("status_code") == 409 which was always False, so it fell through to the generic error handler and displayed "error — already running".
Fix: Replaced the ternary emit with explicit branches; 409 now emits {"error": "already running", "status_code": 409} so the status_code check in _on_geocode_started works correctly.

---

BUG-069: Nominatim batch geocoder has no HTTP-429 / rate-limit retry logic
Status: Fixed
File(s): backend/geocoder.py:geocode_one, run_batch
Reported: 2026-05-19
Fixed: 2026-05-19
Description: run_batch() sleeps 1.1 s between requests to stay within Nominatim's 1 req/sec ToS. However, if the server still returns HTTP 429 (overloaded or policy breach), the request is logged as a network error and marked source='failed' with no retry or back-off. Large batch runs against a slow Nominatim endpoint may accumulate many false 'failed' rows that require --retry-failed later.
Root cause: geocode_one() wraps urllib.request.urlopen in a generic except; 429 responses are not distinguished from actual failures.
Fix: geocode_one() now catches urllib.error.HTTPError before the generic except; a 429 raises the private _RateLimitError sentinel. run_batch() wraps geocode_one() in a retry loop (up to 3 attempts); on each _RateLimitError it sets stage='rate_limited', sleeps 60 s, then retries without advancing the progress counter. After all retries are exhausted the location falls back to source='failed' with a descriptive note.

---

BUG-068: Crawler seeded from domain root — DreamHost placeholder has no useful links
Status: Fixed
File(s): backend/site_crawler.py
Reported: 2026-05-18
Fixed: 2026-05-18
Description: Running the site crawler in full mode fetched only one file (the domain root index.html, 808 bytes) and stopped. The root URL http://www.losslessbob.wonderingwhattochoose.com/ serves a DreamHost "coming soon" placeholder page with no same-domain links. The correct entry point is /LosslessBob.html.
Root cause: crawl() default start_url was BASE_URL ("/") instead of SITE_HOME_URL ("/LosslessBob.html"). No explicit seed URLs were added, so the BFS queue was empty after the root fetch.
Fix: Added SITE_HOME_URL = BASE_URL + "/LosslessBob.html"; changed crawl() default start_url to SITE_HOME_URL. Added SEED_URLS constant seeding /bynumber/LBMbynumber.html and /detail/LB-bootleg-by-title.html as a safety net for every crawl session, regardless of start_url.

---

BUG-066: Search tab row colours not applied for 5–6 seconds after results appear
Status: Fixed
File(s): gui/search_tab.py:413-423, backend/db.py:88-89
Reported: 2026-05-18
Fixed: 2026-05-18
Description: After a search returned results, row background colours (owned green, private blue, missing grey) did not appear for approximately 5–6 seconds.
Root cause: Two compounding issues. (1) _XrefWorker (started at tab init) called GET /api/checksums/xref_map. get_xref_map() did a full table scan on checksums (WHERE xref > 0) because the only partial index — idx_lb_xref0 — covers xref=0, not xref>0. On a large DB this took 5–6 s. (2) _on_xref_loaded() called self._page = 0; self._render_page() whenever _all_results was non-empty. That unnecessary beginResetModel/endResetModel cycle discarded the view's previously-painted state and issued a fresh repaint 5–6 s after the initial display — the repaint that made colours first visible. Additionally, the owned set (_OwnedWorker) was only started after search results were rendered, adding a second HTTP round-trip delay before owned (green) colours could appear.
Fix: (1) Removed the self._page = 0 / _render_page() call from _on_xref_loaded; model.set_xref_map() already emits dataChanged for the Xref column. (2) Added idx_chk_xref_pos partial index ON checksums(lb_number, xref) WHERE xref>0 so get_xref_map() uses an index-only scan. (3) Added _prefetch_owned() called at SearchTab.__init__ to warm the owned set before the user's first search.

---

BUG-065: check_for_update() misses flat-file corrections and non-max-LB additions
Status: Fixed
File(s): backend/scraper.py:276 (removed)
Reported: 2026-05-18
Fixed: 2026-05-18
Description: The old check_for_update() scraped the bynumber page and compared the maximum LB number found in links against the local max. Any release that only corrected checksums, added checksums for LBs already in the database, or updated filenames would not be detected because the max LB number didn't change.
Root cause: Wrong data source — the download page for the flat-file zip was never consulted. The bynumber page shows the highest LB entry, not the state of the flat file.
Fix: Removed check_for_update() entirely and replaced with the backend/flat_file.py pipeline (discover_flat_file_release). Discovery checks the actual download page for zip filename, page timestamp, and HTTP Last-Modified header, which change whenever any update (including corrections) is published. API route changed from /api/db/check_update to /api/flat_file/discover.

---

BUG-064: _on_strip_wrong_lb leaves state as 'wrong_lb' — stripped rows can never be renamed
Status: Fixed
File(s): gui/rename_tab.py:_on_strip_wrong_lb
Reported: 2026-05-17
Fixed: 2026-05-17
Description: After "Strip Wrong LB from Selected" updated the proposed name for a wrong_lb row, the state stayed 'wrong_lb'. The rename button's eligible set is {"needs_rename", "has_lb"}, so stripped rows were silently skipped and could never be renamed without a manual re-load of the lookup results.
Root cause: _on_strip_wrong_lb called update_proposed_name() but never called update_state(), so the state never transitioned to 'needs_rename'.
Fix: Added update_state(i, "needs_rename") call in _on_strip_wrong_lb() after the proposed name is updated. Added RenameModel.update_state() helper that updates _states[idx] and emits dataChanged for the full row.

---

BUG-063: AttributeError 'CollectionTab' object has no attribute 'table' on theme apply
Status: Fixed
File(s): gui/collection_tab.py:2574
Reported: 2026-05-16
Fixed: 2026-05-16
Description: Applying a theme (or any font-size change) aborted the app with AttributeError: 'CollectionTab' object has no attribute 'table'. Triggered via main_window._on_theme_applied → collection_tab.resize_columns_to_font.
Root cause: resize_columns_to_font referenced self.table, but that attribute only exists on the unrelated _ScanPreviewDialog class in the same module. CollectionTab's real tables are coll_view/miss_view/wish_view plus the forum/torrent history tables, all of which were already being resized correctly.
Fix: Removed the self.table block from resize_columns_to_font.

---

BUG-062: Searching by lb_number returns no results when text fields don't contain that number
Status: Fixed
File(s): backend/db.py:594-626
Reported: 2026-05-16
Fixed: 2026-05-16
Description: Searching for an entry by its lb_number (e.g. "1797") returned no results when none of the entry's text fields (date_str, location, description, setlist) contained that token. Entries with a webpage but no attachments — invisible to the Attachments tab — were completely unfindable.
Root cause: search_entries used FTS5 exclusively, which only indexes text content columns. lb_number is not a text column and not in the FTS index.
Fix: After FTS results are collected, if the query parses as a bare integer and that lb_number is not already in the result set, a direct SELECT by lb_number is performed and the match is prepended to the results.

---

BUG-061: Attachments "Missing" list incorrectly includes real entries with no checksums
Status: Fixed
File(s): backend/db.py:281-299
Reported: 2026-05-16
Fixed: 2026-05-16
Description: The Missing view in the Attachments tab listed entries like LB-12404 as missing even though they have a valid webpage on the archive site. Any lb_number in range 1..max_lb without a row in the checksums table was returned, regardless of whether the entry had a webpage.
Root cause: get_missing_lb_numbers queried the checksums table rather than entries.status. Entries with a webpage but no checksum files were indistinguishable from entries with no page at all.
Fix: Rewrote get_missing_lb_numbers to query entries.status. Only lb_numbers where status='missing' (scraper confirmed no page) or that have never been scraped are returned. lb_numbers with status='ok' are excluded — they are real entries, just without downloadable content.

---

BUG-060: Full-window blackout and GBM format errors when Attachments tab is opened
Status: Fixed
File(s): main.py
Reported: 2026-05-16
Fixed: 2026-05-16
Description: Clicking the Attachments tab caused the entire application window to flash black (full blackout, not just the WebEngine pane) and printed "GBM-DRV error (get_bytes_per_component): Unknown or not supported format: 808530000" to stderr repeatedly.
Root cause: QtWebEngine initialises a Chromium GPU process on first use. With AA_ShareOpenGLContexts set (required to avoid a ~10 s startup stall on Linux), Chromium's GPU process hijacked the shared OpenGL context on Qt 6.7 / XWayland, causing Qt's own widget compositor to lose its context and render a black frame. The GBM errors were Chromium probing the P010 (10-bit YUV) pixel format, which the system's Mesa/DRM driver does not support.
Fix: Added --disable-gpu to QTWEBENGINE_CHROMIUM_FLAGS in main.py. This prevents Chromium from starting a GPU process at all; it falls back to Swiftshader software rendering, which is sufficient for the plain HTML pages this app displays. Both the blackout and the GBM stderr noise are eliminated.

---

BUG-059: Disabled buttons render as hardcoded gray on dark themes
Status: Fixed
File(s): gui/styles.py:build_stylesheet
Reported: 2026-05-16
Fixed: 2026-05-16
Description: Buttons in a disabled state (e.g. "Generate Missing Checksums", "Select Missing Checksums") showed as medium gray (#A0A0A0) regardless of theme, clashing badly against dark app backgrounds like Tokyo Night's #1A1B26.
Root cause: `QPushButton:disabled` in `build_stylesheet` used hardcoded color values instead of theme-derived ones.
Fix: Added `_blend_hex()` helper; disabled button background is now `accent` blended 65% toward `app_bg`, and disabled text is `app_fg` blended 55% toward `app_bg`, so it adapts to every theme.

---

BUG-058: Search tab column widths reset to 100px on every launch and ignore user settings
Status: Fixed
File(s): gui/search_tab.py:_render_page
Reported: 2026-05-16
Fixed: 2026-05-16
Description: All columns on the Search tab defaulted to 100px on every launch. User-adjusted widths were not persisted across sessions.
Root cause: The snapshot block in `_render_page()` ran before `_apply_col_widths()` was ever called, so it captured Qt's 100px defaults and immediately overwrote the widths that had been loaded from QSettings.
Fix: Added `_widths_applied` bool flag; the snapshot is now guarded by `and self._widths_applied` so it is skipped until after the saved widths have been applied to the view at least once. `_apply_col_widths()` and `_set_default_col_widths()` both set the flag to True.

---

BUG-057: Forum poster sends wrong field name for SMF description — "desc" instead of "description"
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic (lines 564, 659)
Reported: 2026-05-16
Fixed: 2026-05-16
Description: LB number never appeared in the SMF topic Description field. BUG-055 added the field to the payload, but used the key "desc" while the actual HTML form field is named "description" (confirmed from the modify-post page source).
Root cause: Wrong key name in both initial payload and retry_payload dicts.
Fix: Changed "desc": lb_id to "description": lb_id in both payload dicts and updated the debug log string to match.

---

BUG-056: _parse_date swaps month and day — subject dates posted as YYYY-DD-MM instead of YYYY-MM-DD
Status: Fixed
File(s): backend/torrent_maker.py:_parse_date
Reported: 2026-05-15
Fixed: 2026-05-15
Description: Forum post subjects showed wrong date formats — e.g. "1980-22-01 Denver, Colorado" instead of "1980-01-22 Denver, Colorado". LosslessBob stores dates as M/D/YY (US format) but _parse_date was assigning parts[0] to `day` and parts[1] to `month`, producing YYYY-DD-MM output.
Root cause: Docstring and variable names assumed D/M/YY (European) format; the actual LosslessBob date format is M/D/YY (US: month/day/year).
Fix: Swapped variable assignment — parts[0] → month, parts[1] → day. Updated docstring to reflect M/D/YY.

---

BUG-055: SMF topic Description field (desc) not sent — LB number never appeared on forum
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-15
Fixed: 2026-05-15
Description: After the desc feature was added to forum posts, the LB number never appeared in the SMF topic Description field because `"desc": lb_id` was missing from both the initial payload and the retry payload. Additionally, `lb_id` was scoped inside the `else:` branch (only defined when subject_override was None), so calling code that always supplies subject_override (the GUI) would encounter a NameError if desc had been included.
Root cause: `lb_id` was defined inside `if not subject_override: else:` block instead of unconditionally; `"desc": lb_id` was never added to either payload dict.
Fix: Moved `lb_id = f"LB-{lb_number:05d}"` to before the subject branch so it is always defined. Added `"desc": lb_id` to both the initial payload and the retry_payload.

---

BUG-054: Superseded duplicate LB shows INCOMPLETE (pink) instead of DUPLICATE (yellow) in summary
Status: Fixed
File(s): backend/db.py:lookup_checksums
Reported: 2026-05-15
Fixed: 2026-05-15
Description: When two LBs share checksums and one is a complete match (MATCHED, green), the other showed as INCOMPLETE (pink) in the summary, implying the user is missing files. The 8 shared checksums were all duplicates — none were unique to the secondary LB — so the user is not missing anything.
Root cause: The summary status was set to INCOMPLETE whenever missing_from_set was non-empty, regardless of whether all matched items were DUPLICATEs superseded by a better-matching LB. The "missing" files belong to the secondary LB's primary set, not to what the user actually has.
Fix: After building the summary, any LB where duplicates == given (all items still DUPLICATE after resolution) and status == INCOMPLETE is reclassified to DUPLICATE. The GUI's existing color mapping renders it yellow.

---

BUG-053: Fatal crash under Wayland — EGL_BAD_NATIVE_WINDOW kills the compositor connection
Status: Fixed
File(s): main.py
Reported: 2026-05-15
Fixed: 2026-05-15
Description: App crashed with "qt.qpa.wayland: eglSwapBuffers failed with 0x300d, surface: 0x0" followed by "The Wayland connection experienced a fatal error: Invalid argument". The process was killed with no Python traceback.
Root cause: Qt's native Wayland plugin + AA_ShareOpenGLContexts + QtWebEngine EGL context sharing triggers EGL_BAD_NATIVE_WINDOW (surface becomes 0x0) on some Wayland compositors. The fatal Wayland protocol error that follows is unrecoverable at the application level.
Fix: Set QT_QPA_PLATFORM=xcb before QApplication construction on non-Windows platforms when the variable is not already set by the user. XWayland is stable for this workload and loses no functionality. User can override by exporting QT_QPA_PLATFORM before launch.

---

BUG-052: xref full match shown as INCOMPLETE — completeness checked against primary set instead of xref group
Status: Fixed
File(s): backend/db.py:lookup_checksums
Reported: 2026-05-15
Fixed: 2026-05-15
Description: A recording that provides all checksums for a specific xref variant (e.g. xref 253) was shown as MATCHED (INCOMPLETE) instead of MATCHED (green). The summary correctly identified the xref but the status was wrong.
Root cause: The reverse lookup queried `WHERE lb_number=? AND xref=0` for every matched LB, comparing input against the full primary set. Since the user only had xref-253 files, all 32 primary checksums appeared "missing" and flipped the status to INCOMPLETE.
Fix: Refactored lb_to_matched to lb_xref_to_matched keyed by (lb_number, xref_value). Reverse lookup now queries `WHERE lb_number=? AND xref=?` per group. Completeness is evaluated independently per xref variant — the primary set is not consulted when the user has no primary files.

---

BUG-051: lbdir xref files not found — startswith('lbdir') misses LBF-XXXXX-xref-NNNN-lbdir.txt naming
Status: Fixed
File(s): backend/app.py:lbdir_check, lbdir_retrieve._find_lbdir
Reported: 2026-05-15
Fixed: 2026-05-15
Description: xref lbdir files are named LBF-02283-xref-00253-lbdir.txt (not lbdir*.txt). Both the lbdir_check route and the _find_lbdir helper used startswith('lbdir'), so xref lbdir files in local folders and in the attachment cache were never detected.
Root cause: The filename detection predicate only matched the original naming convention and did not account for the xref attachment naming pattern where 'lbdir' appears mid-name rather than at the start.
Fix: Changed both detection predicates from startswith('lbdir') to 'lbdir' in f.name.lower(), which matches both conventions while remaining specific (combined with the .txt suffix check).

---

BUG-050: _post_url() hardcoded wrong SMF handler — form action= is the authoritative POST target
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic, _scrape_form_fields
Reported: 2026-05-15
Fixed: 2026-05-15
Description: Even after BUG-044 added board_id to the POST URL, the constructed URL still used a hardcoded action=post;sa=post2 path that does not match the form's actual action attribute, causing posts to land on the wrong SMF handler.
Root cause: _post_url(board_id) was built from a hardcoded string rather than reading the form's own action= value. SMF's compose form is the only reliable source of the correct POST endpoint.
Fix: Removed _post_url(). _scrape_form_fields() now returns (fields, form_action, diag) where form_action is extracted from _find_post_form(soup).get("action"). post_lb_topic() uses form_action as the POST target; fails fast if form_action is empty.

---

BUG-049: Retry path did not handle board-redirect success — always reported failure after confirmation resubmit
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic (retry block)
Reported: 2026-05-15
Fixed: 2026-05-15
Description: After the lock-warning retry was introduced (BUG-046), the retry POST only checked for topic= in the redirect Location. This forum returns a board=N.0 redirect on success, so every successful retry was reported as "Retry: unexpected redirect".
Root cause: The retry success-detection block was copied from the pre-board-redirect era and only handled the topic= case.
Fix: Extended retry success detection to mirror the initial POST: checks topic= first, then board=N.0, then treats anything else as a failure. Both paths call _find_newest_topic() on the board page sorted by first_post desc.

---

BUG-048: _extract_smf_error returned phantom error text on every compose page — hidden errorbox triggered
Status: Fixed
File(s): backend/forum_poster.py:_extract_smf_error
Reported: 2026-05-15
Fixed: 2026-05-15
Description: _extract_smf_error() returned "SMF: ..." error strings even when the post had succeeded, causing false failure reports. The function scraped the errorbox/windowbg divs that are always present (but empty and display:none) on the compose page.
Root cause: Error-element checks did not filter out hidden elements. A valid empty errorbox (display:none) matched the class selector and its empty text still satisfied len > 10 when combined with whitespace from nested elements.
Fix: Added _is_element_hidden() check before extracting text from any candidate error element. Elements with inline display:none are skipped entirely.

---

BUG-047: Lock-warning retry fired on every failed post — #lock_warning always present but hidden
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-15
Fixed: 2026-05-15
Description: Any failed post that returned HTTP 200 (no redirect) triggered the lock-warning retry path, even when no real lock warning was shown. The retry then failed identically, masking the real error.
Root cause: The lock-warning check used soup.find(id="lock_warning") without checking whether the element was visible. SMF includes #lock_warning on every compose page but sets display:none when there is no active warning. The check therefore always matched.
Fix: Added _is_element_hidden() helper. is_lock_warning is now True only when the element exists AND does not carry a display:none inline style.

---

BUG-046: Forum post stuck in lock-warning loop — board requires admin confirmation resubmit
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-14
Fixed: 2026-05-14
Description: After fixing the board URL, every post still bounced with "Warning: topic is currently/will be locked!" regardless of lock=0 in the payload.
Root cause: Board 16 ("Up To Me") is a restricted board (admin/mod-only posting). SMF always returns a confirmation-preview page for new topics on such boards, even for admins. This is a board-level policy, not a form-field issue. The attachment was already temp-stored server-side by the time the warning appeared.
Fix: Detect the lock-warning page by text content. Re-scrape fresh hidden fields (new seqnum/CSRF token) from the warning page and resubmit via a second POST without the file. The second submission confirms the action and SMF creates the topic.

---

BUG-045: Forum post bounced with lock warning — admin compose page pre-sets lock=1
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-14
Fixed: 2026-05-14
Description: After fixing the board URL, SMF returned the compose form with "Warning: topic is currently/will be locked! Only admins and moderators can reply." instead of creating the topic.
Root cause: Admin users' compose pages include lock=1 as a hidden field. This was forwarded verbatim via **hidden, causing SMF to treat every new topic as locked and requiring a second confirmation POST.
Fix: Explicitly override lock=0, sticky=0, move=0 in the payload after **hidden so admin-default values are always neutralised.

---

BUG-044: Forum post always fails with "board doesn't exist" — board missing from POST URL
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-14
Fixed: 2026-05-14
Description: Every post attempt returned "The board you specified doesn't exist" even though the compose page loaded correctly for the same board.
Root cause: _POST_URL was hardcoded as ?action=post;sa=post2 with no board parameter. SMF requires board=N.0 in the POST URL (not just the compose/GET URL) to know which board to write the topic into.
Fix: Replaced the static _POST_URL constant with _post_url(board_id) that appends ;board=N.0 to match the compose URL pattern.

---

BUG-043: Forum post fails with "board doesn't exist" — board ID was hardcoded to wrong value
Status: Fixed
File(s): backend/forum_poster.py, backend/app.py, gui/setup_tab.py
Reported: 2026-05-14
Fixed: 2026-05-14
Description: After the false-success fix, posting failed with "The board you specified doesn't exist" because FORUM_BOARD was hardcoded to 16, which is not a valid board on this forum instance.
Root cause: Board ID was a hardcoded constant in forum_poster.py with no way to configure it without editing source.
Fix: Removed the constant. post_lb_topic() now accepts board_id as a required parameter. The value is stored in the meta table as wtrf_board_id, exposed via /api/db/settings, and configured via a new Board ID spinbox in the Setup tab WTRF section.

---

BUG-042: Forum post reports "Posted successfully" but topic never appears on forum
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-14
Fixed: 2026-05-14
Description: After BUG-041 was fixed, "Post to Forum" showed a success dialog with a topic URL, but no topic appeared on the forum.
Root cause: SMF returns HTTP 200 when it bounces a rejected post back to the compose form (CSRF failure, attachment rejected, flood control, etc.). The fallback "if status==200 assume success" path fired, returning the POST endpoint URL as the fake topic URL. Additionally, the POST was missing Referer/Origin headers (needed for SMF's CSRF check), and additional_options was left at 0 (the compose-page default), which suppresses attachment processing.
Fix: Success is now gated on 'topic=' appearing in the final response URL (the redirect SMF sends only on a real post). Added Referer and Origin headers to the POST. Added additional_options=1 to the payload. Error reporting now collects errorbox/error_list/post_error div text and falls back to page title + URL so failures are always diagnosable.

---

BUG-041: Forum post fails with "sc missing" — WTRF SMF uses a hashed field name instead of 'sc'
Status: Fixed
File(s): backend/forum_poster.py:post_lb_topic
Reported: 2026-05-14
Fixed: 2026-05-14
Description: "Post to Forum" always failed with "Could not retrieve SMF form fields (sc missing)." even though login succeeded and the compose page loaded correctly (HTTP 200, 'Start new topic').
Root cause: post_lb_topic validated that both 'sc' and 'seqnum' were present in the hidden form fields. This WTRF SMF install uses a dynamically-hashed field name for the CSRF token (e.g. 'a9c55b28') instead of the literal 'sc'. seqnum was present; sc was absent under that name. All fields including the hashed token were already forwarded via **hidden, so the post would have succeeded if the validation had not blocked it.
Fix: Removed the 'sc' name check. Only seqnum is validated (it uniquely identifies the real post form). The hashed CSRF field is passed through automatically with all other hidden fields.

---

BUG-040: generate_checksums produces no shntool hashes for SHN files when shorten is not installed
Status: Fixed
File(s): backend/checksum_utils.py:compute_shntool, generate_checksums
Reported: 2026-05-13
Fixed: 2026-05-13
Description: "Generate Missing Checksums" silently produced no shntool entries for .shn files. The generated .md5 file was either not created or contained only file-MD5 lines.
Root cause: shntool requires the external shorten binary to decode .shn files before hashing. shorten is not packaged in standard Linux repos. compute_shntool ran shntool hash file.shn, shntool reported a decoder-not-found error to stderr and wrote nothing to stdout, so compute_shntool returned None for every file. Additionally, generate_checksums for SHN mode only generated shntool hashes — it did not generate file-MD5 hashes, which lbdir files include.
Fix: Added _compute_shntool_via_ffmpeg() fallback: when shntool hash produces no output for a .shn file, ffmpeg decodes the SHN to a temp WAV (ffmpeg has a built-in Shorten codec) and shntool hashes the WAV. The PCM data is identical so the hash matches. Updated generate_checksums SHN block to also compute and write file-MD5 hashes alongside the shntool hashes.

---

BUG-039: lbdir check shows shntool FAIL for WAV-format recordings even when files pass MD5
Status: Fixed
File(s): backend/checksum_utils.py:verify_folder_lbdir
Reported: 2026-05-13
Fixed: 2026-05-13
Description: After BUG-037 was fixed, WAV-format recordings correctly showed .wav filenames in the detail grid, but the FFP/Shn column showed FAIL for every .wav audio file. Overall verdict remained PASS because the failing shntool status wasn't included in the .wav verdict, but the FAIL display was confusing and no shntool actual hash was computed.
Root cause: verify_folder_lbdir only ran compute_shntool() when is_shn was True. For .wav files with a shntool expected hash (WAV-format recordings have shntool hashes in the lbdir), shn_actual stayed None, so _cmp returned 'fail'. The .wav else-branch also excluded the shntool check from the overall verdict, making the FAIL invisible but still wrong to display.
Fix: Extended the shntool compute condition to also fire for .wav files (shntool md5 handles WAV natively). Added shn_exp/shntool_ok check to the else-branch so the computed hash is included in the overall verdict for WAV files.

---

BUG-038: Rename tab checkboxes cannot be toggled by clicking — only "Select All" works
Status: Fixed
File(s): gui/rename_tab.py:_build_ui, _on_cell_clicked
Reported: 2026-05-13
Fixed: 2026-05-13
Description: Clicking a checkbox in the Rename column had no effect. The "Select All" / "Deselect All" buttons worked, but individual row selection via the checkbox did not.
Root cause: The view has setEditTriggers(NoEditTriggers), which prevents Qt's delegate from routing mouse clicks to setData() even for CheckStateRole changes. The ItemIsUserCheckable flag makes the checkbox visible but the edit-trigger guard blocks the toggle from firing.
Fix: Connected self.view.clicked to _on_cell_clicked(), which calls model.setData() directly with the toggled CheckState. The clicked signal fires regardless of edit triggers.

---

BUG-037: lbdir check shows .shn files as MISSING for WAV-format recordings
Status: Fixed
File(s): backend/checksum_utils.py:parse_lbdir_file
Reported: 2026-05-13
Fixed: 2026-05-13
Description: When checking a lbdir file for a WAV-format recording (lbdir *.wavf.txt), the detail grid showed phantom .shn entries marked MISSING alongside the correctly-found .wav files. The actual .wav files were verified fine but the .shn ghost rows inflated the missing count and the mode was incorrectly shown as SHN.
Root cause: parse_lbdir_file() unconditionally converted every .wav filename in the shntool and shntool_len sections to .shn (e.g. "I Got A New Girl.wav" → "I Got A New Girl.shn") and forced has_shn=True. For SHN recordings this is correct (shntool decodes to WAV internally, actual files are .shn). For WAV recordings the files really are .wav on disk, so the conversion produced nonexistent .shn keys, which fpath.exists() then reported as MISSING.
Fix: In both shntool and shntool_len parsing blocks, only perform the .wav → .shn conversion when has_shn is already True (set by the md5 section having seen real .shn filenames). WAV-format recordings have .wav in the md5 section so has_shn stays False, and the shntool filenames are kept as .wav — matching what is actually on disk.

---

BUG-036: Lookup Scan Tree doesn't populate listbox; shows results but no files added
Status: Fixed
File(s): gui/lookup_tab.py:_on_scan_tree
Reported: 2026-05-13
Fixed: 2026-05-13
Description: Clicking "Scan Tree…" on the Lookup tab found checksum files but never added them to the folder listbox. Results appeared in the summary/detail panes but with no source_file context, and the "Generate Missing Checksums" / select-by-folder features didn't work for scan-tree results. Also, the _mychecksums filter was inverted — when enabled it excluded _mychecksums files instead of keeping them.
Root cause: _on_scan_tree read file contents and joined them into a single string passed to _run_lookup() (the clipboard/text path). This bypasses _LookupWorker's path-based branch that maps checksums back to their source files, and never calls _add_path / _refresh_listbox.
Fix: Replaced the method body with _ScanTreeWorker(QThread) that does the rglob off the main thread. _on_scan_tree_done adds found paths to _all_paths, calls _refresh_listbox(), then starts _LookupWorker with paths= so source_file is correctly set on all detail items. Fixed filter logic: skip files where "_mychecksums" not in name when filter is active.

---

BUG-035: Subfolder files in lbdir show as MISSING on Linux due to Windows backslash paths
Status: Fixed
File(s): backend/checksum_utils.py:123,134,142,150
Reported: 2026-05-13
Fixed: 2026-05-13
Description: Files in subdirectories listed in lbdir files (e.g. artwork\back.JPG) were always reported as MISSING even when the files existed on disk. Root-level files were found correctly.
Root cause: lbdir files created on Windows use backslash as the path separator. parse_lbdir_file() stored filenames verbatim without normalizing separators. On Linux, pathlib treats backslashes as literal filename characters (not directory separators), so Path(folder) / "artwork\back.JPG" resolved to a non-existent path and fpath.exists() returned False.
Fix: Added .replace('\\', '/') on every fname/wav_fname/raw_fname extracted in the md5, ffp, shntool, and shntool_len parsing blocks inside parse_lbdir_file(). All dict keys and fpath construction now use forward-slash paths.

---

BUG-034: Scan Directory / Scan Tree freezes the UI ("python is not responding")
Status: Fixed
File(s): gui/collection_tab.py:_on_scan_directory, _on_scan_tree
Reported: 2026-05-13
Fixed: 2026-05-13
Description: Clicking "Scan Directory" or "Scan Tree…" then selecting a large root directory caused Python to become unresponsive. The OS showed a "python is not responding" dialog.
Root cause: Both methods called Path.iterdir() / Path.rglob("*") and requests.get() synchronously on the Qt main thread after the file dialog closed. A large archive drive (thousands of subdirectories) blocks the event loop long enough to trigger the not-responding timeout.
Fix: Added _ScanWorker(QThread) that performs the filesystem traversal and the /api/collection/lb_numbers network call off the main thread. Both _on_scan_directory and _on_scan_tree now start the worker immediately and show a status message; _on_scan_finished (connected to worker.finished) presents the preview dialog and proceeds with _bulk_add.

---

BUG-033: Spectrogram panning overshoots then snaps back
Status: Fixed
File(s): gui/spectrogram_tab.py:87,100,101
Reported: 2026-05-13
Fixed: 2026-05-13
Description: Small drags caused the view to pan too far then immediately correct, producing jerky movement.
Root cause: Pan tracking used event.position() (label-local coordinates). After each scroll bar update Qt moves the label widget, invalidating the stored _pan_start — next delta was computed against a stale coordinate in a different frame, causing equal-and-opposite overshoot.
Fix: Changed _pan_start capture and delta calculation to use event.globalPosition() (screen coordinates), which are unaffected by the widget's scroll position.

---

BUG-032: "Scrape All Missing" leaves gap LB numbers (not in checksums) completely absent from the database
Status: Fixed
File(s): backend/app.py:303, backend/db.py:421
Reported: 2026-05-12
Fixed: 2026-05-12
Description: "Scrape All Missing" queried only lb_numbers present in the checksums table. Any sequential gap (e.g. LB-7 with no checksum data) was never included in the scrape list, never attempted, and never written to entries — leaving a blank hole in the database instead of a MISSING placeholder row.
Root cause: The gap-filling logic (fill_gaps) only ran when an explicit end_lb was provided and the range-scrape checkbox was checked. The "all missing" path sent no end_lb, so fill_gaps was never applied and gaps were silently skipped. Additionally, insert_missing_entry used INSERT OR REPLACE which could have overwritten an already-scraped entry.
Fix: backend/app.py — derive effective_end from the highest checksum lb_number when end_lb is absent, then unconditionally fill every sequential gap between start_lb and effective_end using insert_missing_entry. For explicit range scrapes the fill_gaps checkbox is still respected. backend/db.py — changed insert_missing_entry to INSERT OR IGNORE so gap-filling can never clobber a row that already has real scraped data.

---

BUG-031: scrape_entry skips status='missing' entries even when a local page could be used
Status: Fixed
File(s): backend/scraper.py:64
Reported: 2026-05-12
Fixed: 2026-05-12
Description: When use_local_pages=True, entries previously marked status='missing' were silently skipped by scrape_entry() even if a local HTML page existed in data/pages/ that could provide real metadata. The status=='missing' early-return fired before the local-page existence check.
Root cause: local_page path was computed after the skip block. The skip logic had no visibility into whether a local file was present, so it unconditionally bailed on any 'missing' entry.
Fix: Moved local_page resolution before the skip block. The status=='missing' branch now only skips if no usable local page is present.

---

BUG-030: Auto-scrape fires after import even when checkbox is unchecked (post-DB-reset)
Status: Fixed
File(s): gui/setup_tab.py:485, backend/app.py:59
Reported: 2026-05-12
Fixed: 2026-05-12
Description: After clicking "Reset Database", the meta table is wiped. _on_reset_finished did not re-persist the current UI settings, so auto_scrape became NULL in the DB. on_complete then evaluated NULL != "0" as True and started the scraper even though the checkbox was unchecked.
Root cause: DB reset drops all meta rows but the GUI never re-saves its settings to the fresh DB, leaving auto_scrape as NULL; NULL != "0" is always True in Python.
Fix: Added self._save_settings() call in _on_reset_finished after a successful reset so user preferences survive the meta table wipe. Added explicit NULL handling in on_complete (val is None or val != "0") to document the intended default-on behaviour.

---

BUG-029: 2–4 s startup delay from eager QWebEngineView construction in AttachmentsTab
Status: Fixed
File(s): gui/attachments_tab.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: MainWindow took 2–4 extra seconds to appear because AttachmentsTab.__init__ created QWebEngineView immediately, triggering the WebEngine GPU subprocess spawn during startup.
Root cause: WebEngine subprocess starts synchronously on first QWebEngineView instantiation.
Fix: Moved all WebEngine construction (profile, page, view) into _init_web_view(), called via QTimer.singleShot(0, ...) from showEvent on first activation. _preview_file now uses setCurrentWidget instead of setCurrentIndex.

---

BUG-028: ~7 s Flask startup delay from synchronous bloom filter rebuild in init_db()
Status: Fixed
File(s): backend/db.py:init_db
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Flask took ~7 seconds to start serving requests because init_db() called rebuild_bloom() synchronously, iterating every checksum row before returning.
Root cause: DB-07 added rebuild_bloom() at the end of init_db() without considering startup cost on large databases.
Fix: Added _rebuild_bloom_bg() helper and launch it as a daemon thread. init_db() returns immediately; the filter populates in the background. Lookups fall through to SQLite (correct, if slightly slower) until the filter is ready.

---

BUG-027: ~10 s startup delay on Linux — Qt::AA_ShareOpenGLContexts not set before QApplication
Status: Fixed
File(s): main.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: App took ~10 seconds to show any window on Linux. Console printed "Attribute Qt::AA_ShareOpenGLContexts must be set before QCoreApplication is created."
Root cause: QtWebEngine registers its GPU/renderer subprocess during QApplication construction. Without AA_ShareOpenGLContexts the renderer cannot share the host GL context and falls back to a slow separate-process initialisation path.
Fix: Added QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts) immediately before QApplication(sys.argv) in main.py.

---

BUG-026: "Release of profile requested but WebEnginePage still not deleted" on shutdown
Status: Fixed
File(s): gui/attachments_tab.py:_init_web_view, _cleanup_webengine
Reported: 2026-05-12
Fixed: 2026-05-15
Description: Qt logged "Release of profile requested but WebEnginePage still not deleted. Expect troubles!" on app exit. The previous fix (parenting page to profile) was insufficient — the profile itself was still a sibling of web_view under the tab, so Qt could still destroy the profile while the view held live Chromium web-contents references.
Root cause: QWebEngineProfile had the tab as its Qt parent; Qt destroyed siblings in arbitrary order. Even with the page parented to the profile, the Chromium-level web-contents tracked by the view were still alive when the profile destructor ran.
Fix: Removed the Qt parent from QWebEngineProfile (no second arg to constructor). Connected QApplication.aboutToQuit to _cleanup_webengine(), which uses sip.delete() to force destruction in the required order: view first (disconnects Chromium web-contents from the profile), then page, then profile.

---

BUG-025: db_reset raises "FOREIGN KEY constraint failed" after DB-01 enabled PRAGMA foreign_keys=ON
Status: Fixed
File(s): backend/app.py:db_reset
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Clicking Reset Database in the Setup tab raised "FOREIGN KEY constraint failed" because my_collection has a FK on entries(lb_number) and PRAGMA foreign_keys was now ON (added in DB-01). The original code relied on FK enforcement being OFF by default.
Root cause: DB-01 added PRAGMA foreign_keys=ON to get_connection(). The drop script in db_reset dropped entries before my_collection, violating the FK while enforcement was active.
Fix: Prepend PRAGMA foreign_keys=OFF to the executescript drop sequence. Re-enable with conn.execute("PRAGMA foreign_keys=ON") after the script, before calling init_db().

---

BUG-024: WebEngine cache written outside app folder, breaks portable installs (WIN-15)
Status: Fixed
File(s): gui/attachments_tab.py, backend/paths.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: QWebEngineView used the default profile, writing cache to %LOCALAPPDATA%\QtProject on Windows and ~/.local/share/QtProject on Linux. Breaks USB/portable use and leaves debris after uninstall.
Root cause: No custom profile was configured for the WebEngine instance.
Fix: Added WEBENGINE_DIR = DATA_DIR / "webengine_cache" to paths.py. attachments_tab now creates a named QWebEngineProfile("losslessbob") with storage and cache redirected to WEBENGINE_DIR. Also removed stale __file__-relative ATTACHMENTS_DIR definition.

---

BUG-023: _pending dict in scheduler leaks memory on long-running sessions (WIN-13)
Status: Fixed
File(s): backend/scheduler.py:FileEventHandler._handle
Reported: 2026-05-12
Fixed: 2026-05-12
Description: _handle() set _pending[key] = True before spawning the delayed thread but the thread never cleaned it up, so every detected file event permanently bloated _pending.
Root cause: Missing finally cleanup in the delayed() thread function.
Fix: Moved the _pending cleanup into a finally block in delayed(). Added early-exit for Windows system files (Thumbs.db, desktop.ini, dotfiles). Use WindowsApiObserver on Windows for reliable ReadDirectoryChangesW behaviour.

---

BUG-022: Qt6 DnD returns '/C:/path' with leading slash on Windows (WIN-14)
Status: Fixed
File(s): gui/platform_utils.py, gui/lookup_tab.py, gui/verify_tab.py, gui/lbdir_tab.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: QUrl.toLocalFile() returns '/C:/Users/...' on Windows Qt6 — the leading slash makes Path resolve relative to the drive root, so path.is_dir() is always False and drag-drop silently adds nothing.
Root cause: Qt6 Windows behaviour difference from Linux.
Fix: Added url_to_local_path() to platform_utils.py that strips the spurious leading slash on win32. All three DropWidget.dropEvent methods now use it.

---

BUG-021: shutil.move raises PermissionError on Windows with no user guidance (WIN-07)
Status: Fixed
File(s): gui/rename_tab.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Windows Explorer holding a folder open causes shutil.move to raise PermissionError. The bare exception was shown as a raw Python traceback with no actionable message.
Root cause: Single broad except clause; no Windows-specific guidance.
Fix: Split rename block into distinct mkdir + move try/except catching PermissionError, FileExistsError, and OSError separately. Added Windows tip to the error display. Also added check for illegal filename characters before attempting the move.

---

BUG-020: console windows flash on Windows during subprocess calls (WIN-05)
Status: Fixed
File(s): gui/platform_utils.py, backend/checksum_utils.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Every subprocess.run call in checksum_utils.py spawned a visible console window on Windows, flashing on screen during verification.
Root cause: No STARTUPINFO / CREATE_NO_WINDOW flags passed to subprocess on Windows.
Fix: Added _no_window_kwargs() to checksum_utils.py and _subprocess_flags() to platform_utils.py. compute_shntool now passes **_no_window_kwargs() to subprocess.run.

---

BUG-019: shntool unavailable on Windows with no user guidance (WIN-08)
Status: Fixed
File(s): backend/checksum_utils.py, gui/verify_tab.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: On Windows, shutil.which('shntool') returns None and SHN folders report INCOMPLETE with no instruction on how to fix it.
Root cause: shntool is a Linux binary; no WSL detection or Windows-specific guidance existed.
Fix: Added _find_shntool() that auto-detects shntool via WSL on Windows. Added _get_shntool_cmd() cache. compute_shntool converts Windows paths to WSL /mnt/ paths. verify_tab shntool_missing message now shows Windows-specific WSL install instructions.

---

BUG-018: Paths > 260 chars silently fail on Windows (WIN-09)
Status: Fixed
File(s): backend/paths.py, backend/checksum_utils.py, backend/db.py, backend/scraper.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Python on Windows raises FileNotFoundError for paths exceeding MAX_PATH (260 chars) unless the \\?\ long-path prefix is used.
Root cause: No long-path prefix applied to file I/O operations.
Fix: Added to_long_path() to paths.py. Applied in compute_md5, compute_ffp (checksum_utils), get_connection (db), and lb_dir/local_page construction (scraper). Added data-dir length warning in ensure_data_dirs().

---

BUG-017: Font-family hardcoded to Segoe UI — layout differs on Linux (WIN-10)
Status: Fixed
File(s): gui/styles.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Stylesheet hardcoded 'Segoe UI, Arial, sans-serif'. On Linux this falls back to Arial or generic sans-serif, causing minor layout differences.
Root cause: No platform-aware font selection.
Fix: Added _platform_font_stack() helper. Windows uses Segoe UI; macOS uses -apple-system; Linux uses Ubuntu/Cantarell/DejaVu Sans.

---

BUG-016: QSettings writes to Windows registry — not portable (WIN-11)
Status: Fixed
File(s): gui/main_window.py
Reported: 2026-05-12
Fixed: 2026-05-12
Description: QSettings(APP_NAME, APP_NAME) stores geometry in HKCU\Software\LosslessBobLookup on Windows, breaking portable/USB installs and leaving registry debris after uninstall.
Root cause: Default QSettings backend uses the registry on Windows.
Fix: Replaced with QSettings(path, QSettings.Format.IniFormat) pointing to data/settings.ini. Window geometry now stored as a plain text INI file alongside the database.

---

BUG-015: xdg-open hardcoded in collection_tab.py — crashes on Windows (WIN-03)
Status: Fixed
File(s): gui/collection_tab.py:792, gui/attachments_tab.py:206, gui/setup_tab.py:454,509
Reported: 2026-05-12
Fixed: 2026-05-12
Description: collection_tab._open_folders unconditionally called subprocess.Popen(["xdg-open", path]), which raises FileNotFoundError on Windows. attachments_tab and setup_tab had inline sys.platform branches that were correct but duplicated across files.
Root cause: Platform branching was scattered and collection_tab was missed entirely.
Fix: Created gui/platform_utils.py with open_folder(), open_file(), and open_url(). All three files now delegate to these helpers. Removed top-level subprocess and os imports from collection_tab, attachments_tab, and setup_tab.

---

BUG-014: SQLite "database is locked" under concurrent access on Windows (WIN-04)
Status: Fixed
File(s): backend/db.py:get_connection
Reported: 2026-05-12
Fixed: 2026-05-12
Description: sqlite3.connect() had no timeout, so any write contention between the scraper thread and GUI polling raised OperationalError: database is locked immediately on Windows.
Root cause: Windows uses LockFileEx for SQLite file-locking, which is more aggressive than Linux advisory locks. Without a retry timeout, contention raises immediately.
Fix: Added timeout=30 and check_same_thread=False to sqlite3.connect(). Added PRAGMA busy_timeout=30000 as belt-and-suspenders to mirror the connect timeout.

---

BUG-013: PyInstaller frozen build cannot find data/ directory (WIN-01)
Status: Fixed
File(s): backend/paths.py (new), backend/db.py, backend/app.py, backend/scraper.py, backend/scheduler.py, backend/importer.py, gui/setup_tab.py, main.py
Reported: 2026-05-10
Fixed: 2026-05-10
Description: When packaged with PyInstaller, every backend module computed DATA_DIR as Path(__file__).parent.parent / "data". In a frozen build __file__ resolves to the _MEIPASS temp extraction directory, not the .exe location, so the data/ folder was never found.
Root cause: All modules used __file__-relative path construction, which breaks in frozen executables.
Fix: Created backend/paths.py with a central _app_root() that returns Path(sys.executable).parent when sys.frozen is set, and Path(__file__).parent.parent otherwise. All modules now import their path constants from backend.paths.

---

BUG-012: Flask startup race — GUI hits dead port on slow Windows machines (WIN-02)
Status: Fixed
File(s): main.py
Reported: 2026-05-10
Fixed: 2026-05-10
Description: main.py used time.sleep(0.5) before starting the GUI. On Windows, Flask + socket binding takes 1-3 seconds (Defender scan, socket setup), so the GUI started before the backend was ready, causing ConnectionRefusedError in the status bar on first load.
Root cause: Fixed sleep is too short on Windows; no readiness check was performed.
Fix: Replaced time.sleep(0.5) with _wait_for_port() which polls the TCP port every 100ms for up to 15 seconds. On Windows, Waitress is used as the WSGI server (more stable port binding than Werkzeug). A fatal error dialog is shown if the port is not ready within 15 seconds. The gui.main_window import is deferred to inside main() to avoid DPI scaling issues on Windows with PyInstaller.

---

BUG-011: Drag-and-drop crashes on Windows (OLE COM reentrancy violation)
Status: Fixed
File(s): gui/lookup_tab.py:dropEvent,_add_path,_on_files_dropped; gui/verify_tab.py:dropEvent,_on_folders_dropped; gui/lbdir_tab.py:dropEvent,_on_folders_dropped
Reported: 2026-05-10
Fixed: 2026-05-10
Description: Dropping folders onto the Lookup, Verify, or lbdir list widgets crashed the app on Windows with no Python traceback. On Linux it worked fine, masking the bug entirely.
Root cause: Windows drag-and-drop uses OLE COM — the IDropTarget::Drop() call stack is still active inside dropEvent(). The handler synchronously emitted a signal whose slot called listbox.clear() on the same widget mid-drop, corrupting the COM reference and causing an access violation. Additionally, _add_path() called _refresh_listbox() (and thus listbox.clear()) once per dropped item, causing repeated reentrancy violations for multi-item drops.
Fix: (1) Moved event.acceptProposedAction() to before signal emission in all three dropEvent methods so OLE marks the transaction complete before any downstream code runs. (2) Removed the _refresh_listbox() call from _add_path(); callers now own the refresh. (3) Changed _on_files_dropped and _on_folders_dropped to defer _refresh_listbox() via QTimer.singleShot(0, ...) so it runs only after the event loop processes the drop completion. (4) Added explicit _refresh_listbox() call to _on_add_folders in lookup_tab.py to restore the refresh it previously got from _add_path().

---

BUG-010: Search and Collection table columns resize on every page navigation
Status: Fixed
File(s): gui/search_tab.py:_render_page, gui/collection_tab.py:_render_coll_page, _on_missing_loaded
Reported: 2026-05-08
Fixed: 2026-05-08
Description: Column widths changed on every Prev/Next page click because `resizeColumnsToContents()` was called unconditionally on each render, sizing to the current page's content rather than a stable baseline.
Root cause: `resizeColumnsToContents()` in `_render_page()` and `_render_coll_page()` ran on every page change, not just on first load.
Fix: On first data load, all columns except Description are sized by content; Description defaults to 1400 px. Before each page render, current header widths (including any user drag-resizes) are snapshotted and then restored after the model reset that Qt uses to clear QHeaderView sections. Right-click on any column header opens a pixel-width entry dialog whose result is written into the stored widths immediately.

---

BUG-009: Results per page resets to 50 on every GUI startup
Status: Fixed
File(s): gui/setup_tab.py:_load_settings, _save_settings
Reported: 2026-05-08
Fixed: 2026-05-08
Description: The "Results per page" spinner on the Setup tab always reverted to 50 when the GUI was opened, regardless of the saved value.
Root cause: During `_load_settings`, each `setChecked`/`setValue` call on the checkboxes and `delay_spin` fired their connected signals (`stateChanged`, `valueChanged`), which triggered `_save_settings`. At that point `search_page_spin` had not yet been updated from the DB, so `_save_settings` wrote the widget default of 50 back to the `meta` table, overwriting the user's saved value before it could be applied.
Fix: Added a `_loading` boolean flag initialized to False in `__init__`. `_load_settings` sets it to True at entry and clears it in a `finally` block. `_save_settings` returns immediately when `_loading` is True. Also removed the now-redundant per-widget `blockSignals` calls on `search_page_spin`.

---

BUG-008: Search tab double-click opens 404 URL for LB numbers below 10000
Status: Fixed
File(s): gui/search_tab.py:_on_double_click
Reported: 2026-05-07
Fixed: 2026-05-07
Description: Double-clicking any non-LB-number column in the Search results table opened a URL like `LB-103.html` instead of `LB-00103.html`, producing a 404 for any LB number below 10000.
Root cause: f-string used bare `{lb}` integer formatting instead of `{lb:05d}`.
Fix: Changed to `f"...LB-{lb:05d}.html"` to match the site's 5-digit zero-padded naming convention.

---

BUG-007: status=missing search rows had no visual distinction
Status: Fixed
File(s): gui/search_tab.py:42
Reported: 2026-05-07
Fixed: 2026-05-07
Description: Entries inserted by "Mark sequential gaps as MISSING" appeared in search results as completely blank, uncoloured rows — identical to a broken or empty record.
Root cause: SearchModel.data() BackgroundRole only handled _owned rows; the status field returned from the API was never checked.
Fix: Added a status == "missing" check before the owned check; returns QColor("#FFFF99") so gap placeholders are clearly yellow.

---

BUG-006: Scraper section buttons too short, text clipped
Status: Fixed
File(s): gui/styles.py
Reported: 2026-05-07
Fixed: 2026-05-07
Description: Buttons in the scraper section QHBoxLayouts that shared a row with QLineEdit or QSpinBox widgets were height-constrained by the smaller widget, clipping the bottom of descender characters.
Root cause: No minimum height on QPushButton in the stylesheet; Qt layout shrank buttons to match adjacent inputs.
Fix: Added min-height: 26px to the QPushButton rule in build_stylesheet().

---

BUG-005: Scraper log [web]/[local] source tags sometimes missing or wrong
Status: Fixed
File(s): backend/scraper.py, gui/setup_tab.py
Reported: 2026-05-07
Fixed: 2026-05-07
Description: Some scraped entries appeared in the log with no `[web]` or `[local]` tag, and others showed the wrong tag. Entries that failed with an error were silently skipped in the log, causing the next entry to appear without a source tag.
Root cause: `current_lb` was set at the START of processing each entry, while `last_source` was set at the END. The GUI polled them together every second, pairing the source from the previously-completed entry with the LB number of the currently-being-processed entry. Error entries set `last_source = None`, which then propagated to the next logged line.
Fix: Added `last_lb` field to `_scrape_state` in `scraper.py`, updated alongside `last_source`/`last_action` after each entry completes. `_on_scrape_status` now logs `last_lb` (just completed) rather than `current_lb` (being processed), ensuring source tag always matches. Added explicit "Error scraping LB-X" log line for error entries.

---

BUG-004: force_scrape checkbox does not persist across restarts
Status: Fixed
File(s): backend/app.py:85, gui/setup_tab.py
Reported: 2026-05-07
Fixed: 2026-05-07
Description: The "Force re-scrape" checkbox was saved to meta as `force_scrape` but was never loaded back on startup because `GET /api/db/settings` did not include it in the returned keys list. The checkbox always defaulted to unchecked.
Root cause: `force_scrape` was missing from the hardcoded keys list in `backend/app.py`'s `db_settings` GET handler.
Fix: Added `force_scrape` (and `search_page_size`) to the keys list in `GET /api/db/settings`. `_load_settings` in setup_tab already read `data.get("force_scrape", "0")` so no GUI change was needed.

---

BUG-001: Scraper re-processes entries with download_files=False even when already scraped
Status: Fixed
File(s): backend/scraper.py:66-79
Reported: 2026-05-07
Fixed: 2026-05-07
Description: With force unchecked and scrape_attachments disabled, the scraper still re-scraped entries that were already in the DB. Entries with any `entry_files` rows (even with `downloaded=0`) were not skipped because the pending-count check always ran regardless of whether this scrape run intended to download files.
Root cause: The skip logic only returned `{skipped: True}` for an existing non-missing entry when `pending == 0`. If attachment records existed with `downloaded=0` (e.g. from a previous run with attachments on, or from a metadata-only scrape), the count was > 0 and the entry was not skipped.
Fix: Added `if not download_files: return {"skipped": True}` immediately after the missing-status check, so any entry already in the DB is skipped when this run has no intention of downloading files.

---

BUG-002: Externally sourced attachment files not recognized as downloaded — triggers repeat scrapes
Status: Fixed
File(s): backend/scraper.py:66-91
Reported: 2026-05-07
Fixed: 2026-05-07
Description: Files placed in `data/attachments/LB-XXXXX/` from an external source had `downloaded=0` in the DB (since the scraper never wrote them). The skip check counted these as pending and kept re-scraping those entries on every bulk scrape run.
Root cause: Skip logic only read the `downloaded` column from the DB; it never checked whether the file actually existed on disk.
Fix: Before evaluating the pending count, the skip check now iterates all `downloaded=0` records for the entry and updates them to `downloaded=1` if the file exists on disk. The pending count is then re-evaluated against the updated DB state.

---

BUG-003: force=True re-downloads attachment files already on disk when use_local_pages is enabled
Status: Fixed
File(s): backend/scraper.py:193-199
Reported: 2026-05-07
Fixed: 2026-05-07
Description: With both "Force re-scrape" and "Use local pages" checked, the scraper re-downloaded attachment files that were already present in `data/attachments/`, hitting the website unnecessarily.
Root cause: The attachment download loop's skip condition was `local_path.exists() and not force`. With `force=True`, this evaluated to False and the download always proceeded, ignoring the filesystem.
Fix: Changed condition to `local_path.exists() and (not force or use_local_pages)`. When `use_local_pages=True`, existing files are always preserved regardless of `force`.
