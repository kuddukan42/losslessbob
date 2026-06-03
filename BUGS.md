
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
