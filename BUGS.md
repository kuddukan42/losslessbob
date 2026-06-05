
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

BUG-134: Map screen — blank center canvas with no fallback when tiles fail to load
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenMap.tsx
Reported: 2026-06-04
Root cause: Leaflet tile requests to OpenStreetMap silently fail when offline. No overlay or message indicates this; the center area renders blank white. Left/right sidebars (filters, venue list) are unaffected.
Fix: Add a Leaflet tile-error listener that shows a "Map tiles couldn't load — check your internet connection" overlay on the map container.

BUG-133: DB Editor — pagination bar and action buttons render before any table is selected
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:1590-1620
Reported: 2026-06-04
Root cause: currentTable is initialised to '' and total to 0. Math.max(1, Math.ceil(0/limit)) = 1, so the bar renders "Page 1/1 (0 rows total)" and all action buttons (Commit, Discard, Delete Selected, Export CSV, SQL Query) are visible even though no table has been loaded. Looks like the selected table has 0 rows rather than no table being selected.
Fix: Wrap the bottom action bar in {currentTable && ...} so it only renders once a table is chosen.

BUG-132: Attachments — empty-state message misleads user after auto-load finds no entries
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenAttachments.tsx:279
Reported: 2026-06-04
Root cause: loadTree() fires automatically on mount (line 114). If data/attachments/ is empty the API returns 0 entries, busy clears, and the list shows "Click Refresh tree to load" — but a load already happened. The message implies the user needs to act when the data is genuinely absent.
Fix: Distinguish initial-empty from filter-empty: show "No attachments cached yet" when entries === [] and no filter is active; keep "No matches" for the filtered case.

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

BUG-120: Pipeline verify mismatch — 2 folders where audio no longer matches stored checksums
Status: Open
File(s): backend/checksum_utils.py:verify_folder, backend/app.py:4576
Reported: 2026-05-31
Root cause: Two folders produce verify=fail (V:✗) meaning audio files on disk don't match the .ffp/.md5/.st5
  checksums in that folder. Audio has been modified/replaced since the checksums were created, or checksums
  were generated from a different version of the files. One case (LB-12181 Cutting Edge [24-96]) also fails
  lookup (760 checksum entries parsed, no DB match) suggesting a large multi-disc set with no DB record at all.
Fix: Investigate both folders manually to determine whether (a) the audio was re-encoded/edited after
  checksumming, (b) files were swapped, or (c) the checksum file is for a different edition. Pipeline
  already surfaces this correctly as V:✗; no code change needed, but these two entries need manual review.
Reproduce: run tests/test_pipeline_smoke.py --seed 2 --n 500. Look for V:✗ entries:
  • /mnt/DYLAN2/Concerts/1978/1978-06-20 London, England (LB-06548) — verify fail, lookup OK
  • /mnt/DYLAN2/PRIVATE LB/Official Releases.../The Bootlegseries Volume 12 The Cutting Edge [24-96] LB 12181
    No Torrent No trade — verify fail AND lookup not found (760 entries parsed)

BUG-118: Pipeline lookup conflict — 11 folders whose checksums match 2–5 LB entries
Status: Open
File(s): backend/db.py:lookup_checksums, backend/app.py:4610
Reported: 2026-05-31
Root cause: The database has duplicate checksum entries — identical file hashes stored under multiple LB
  records. lookup_checksums finds all matches and returns a "Conflict", leaving rename and lbdir steps muted
  with no resolution path in the GUI. A systemic sub-pattern: LBs 04994/03029/06748/11900 appear as
  "phantom" matches in two unrelated folders (Osaka 2010 and Bonn 2004) suggesting these entries contain
  a very common file hash (possibly a silence/blank track) that matches recordings they don't belong to.
  Rate from 500-folder sample: 2.2% of collection (extrapolates to ~350 entries affected).
Fix: (1) SQL query to find all checksum hashes shared across 2+ lb_numbers and report them. (2) Investigate
  the phantom LBs 04994/03029/06748/11900 for a common/generic track that should be excluded from lookup
  indexing. (3) Add a de-dup guard in importer so checksums already present under a different LB are flagged.
Reproduce: run tests/test_pipeline_smoke.py --seed 2 --n 500. All 11 conflicts found:
  • LB-07160 vs LB-04653 (1993-04-21 Monroe, LA)
  • LB-06195 vs LB-06198 (2008-06-16 Bergamo — same show, two LB entries)
  • LB-13944 vs LB-11702 (1978-06-07 Los Angeles)
  • LB-08497 vs [04994, 03029, 06748, 11900] (2010-03-15 Osaka — 5-way conflict)
  • LB-00355 vs LB-02722 (1981-07-12 Copenhagen)
  • LB-00074 vs LB-07741 (1978-11-23 Norman OK)
  • LB-01901 vs [04994, 03029, 06748, 11900] (2004-06-29 Bonn — same phantom 4)
  • LB-01992 vs LB-01993 (1997-04-27 Boalsburg PA — consecutive LBs, same show)
  • LB-06198 vs LB-06195 (2008-06-16 Bergamo — mirror of above)
  • LB-11862 vs LB-11381 (2014 Tokyo)
  • LB-04332 vs LB-04946

BUG-106: Windows installer does not place app in Program Files
Status: Open
File(s): installer/losslessbob.iss (or equivalent Inno Setup script)
Reported: 2026-05-22
Description: The Windows installer does not install the application to the standard Program Files directory (e.g. C:\Program Files\LosslessBob). Install destination is incorrect or defaults to an unexpected location. May be a misconfigured DefaultDirName or missing {pf} / {autopf} constant in the Inno Setup script.
Root cause: Unknown
Fix: —


BUG-067: PyQt6 + lxml SIGABRT when Qt widget tests run before lxml-importing tests
Status: Open
File(s): tests/test_scraper_crawler.py, tests/test_lb_master.py
Reported: 2026-05-18
Description: Running all three test files in a single pytest process causes a Fatal Python error: Aborted when tests/test_lb_master.py Qt widget tests (TestSearchTabStatusColumn, TestDbEditorIntegrityPanel) run before tests/test_scraper_crawler.py which imports BeautifulSoup (bs4 loads lxml at import time). The SIGABRT is a known incompatibility between PyQt6 cleanup and lxml's memory allocator on Linux.
Root cause: bs4 unconditionally imports lxml at bs4 import time regardless of which parser is used. When lxml's .so is loaded into the same process as PyQt6 objects, Qt's atexit/destructor sequence may SIGABRT.
Fix: Run test files separately (`pytest tests/test_scraper_crawler.py`) or exclude Qt widget tests when running combined (`pytest tests/ -k "not SearchTab and not DbEditor and not CollectionTab"`). All three files pass independently (59 + 27 + 13 = 99 total tests, all green).
