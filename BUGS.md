
BUG-146: build_standard_name produces xx/xx/YY folder date prefix for entries with unknown month/day
Status: Open
File(s): backend/torrent_maker.py:129, backend/folder_naming.py:72
Reported: 2026-06-09
Root cause: `_parse_date` catches `ValueError` from `int('xx')` and falls back to `date_str.strip()`, returning the raw DB string (e.g. `'xx/xx/65'`) unchanged. `build_standard_name` then uses this as the date prefix, producing `'xx/xx/65 HIGHWAY 61 ROM... (LB-12205)'`. Existing folders for these entries already use ISO-style `'1965-xx-xx ...'` format.
Fix: In `_parse_date`, detect `xx` parts before trying `int()` and emit ISO-style `YYYY-xx-xx` (or `YYYY-MM-xx`) for the known parts — e.g. `xx/xx/65` → `1965-xx-xx`, `3/xx/72` → `1972-03-xx`.

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

