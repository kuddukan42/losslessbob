
BUG-192: Windows — test_batch_verify.py and tools/batch_verify.py not runnable on Windows (termios)
Status: Open
File(s): tools/batch_verify.py:36, tests/test_batch_verify.py:18
Reported: 2026-06-15
Root cause: tools/batch_verify.py imports termios at module level (line 36). termios is a
  Unix-only stdlib module for terminal I/O control and does not exist on Windows. pytest
  collection of tests/test_batch_verify.py fails immediately with ModuleNotFoundError.
Fix: Either (a) guard the import with sys.platform != 'win32' and provide a stub, or (b)
  move the termios import inside the function(s) that need it and add a Windows fallback,
  or (c) mark the test module to skip on Windows with @pytest.mark.skipif.

BUG-187: Full pytest run is order-dependent — global bloom filter leaks between test DBs
Status: Open
File(s): backend/db.py:25 (_bloom global), backend/db.py:947 (_rebuild_bloom_bg), backend/db.py:1185 (init_db spawns it), tests/test_db_lookup.py:71-167 (TestLookupChecksumsSnhCompleteness)
Reported: 2026-06-15
Root cause: init_db() unconditionally spawns a daemon thread (_rebuild_bloom_bg) that calls
  rebuild_bloom(db_path) and overwrites the process-global `_bloom` filter (backend/db.py:25)
  with checksums from whichever db_path it was given. Every test that calls init_db() via a
  `_make_db()`-style fixture (now used by ~7 test modules) triggers one of these threads
  against its own temp DB. TestLookupChecksumsSnhCompleteness relies on `_bloom is None`
  (its docstring says "the bloom filter is not populated... all checksums pass through to
  SQLite") — true when run alone, but when other tests' background rebuild threads finish
  later and overwrite `_bloom` with a filter built from a *different* (often already-deleted)
  temp DB, checksum_in_bloom() starts returning real (stale) results for this test's
  checksums, causing lookup_checksums() to treat its SHN/WAV entries as definite misses.
  This is why `tests/test_db_lookup.py::TestLookupChecksumsSnhCompleteness` fails
  intermittently in full-suite runs (different sub-test fails depending on what else ran,
  e.g. test_shn_md5s_only_yields_matched_not_incomplete vs
  test_mixed_shn_and_wav_checksums_still_matched) but always passes in isolation. Confirmed
  reproducible on main without any new test files — pre-existing, not caused by the new
  tests/test_scraper.py / test_bootleg_scraper.py / test_bobdylan_scraper.py / test_setlistfm.py
  / test_geocoder.py added 2026-06-15.
Fix: TBD. Options: (1) have lookup_checksums()/checksum_in_bloom() validate the bloom filter
  against the db_path it was built for (e.g. store the path alongside `_bloom` and skip the
  filter if it doesn't match); (2) let tests pass an explicit empty/None bloom filter into
  lookup_checksums() instead of relying on global state; (3) don't spawn _rebuild_bloom_bg
  from init_db() when called from tests (e.g. add a `build_bloom: bool = True` kwarg).
  Note: BUG-175 above is unrelated despite the proximity.

BUG-175: LBDIR reconcile leaves self-referencing/regenerated entries permanently "MD5 mismatch" — BUG-174 fix may not be the final answer
Status: Open
File(s): backend/checksum_utils.py:find_site_recoverable_files, backend/checksum_utils.py:find_reconcilable_files
Reported: 2026-06-13
Root cause: Investigated by reproducing against the real LB-16216 pipeline folder
  (/mnt/MEDIA1/1-DYLAN/Bob Dylan  Bayfront Amphitheater Pensacola FL 1992-09-12
  Dolphinsmile Archive), whose 24-entry lbdir (LBF-16216-lbdir-bd92-09-12-PDub-
  Dolphinsmile.flac1648.txt) lists itself and DigiFlawFinder-bd92-09-12-PDub-
  Dolphinsmile.flac1648.wavf.html as "missing" — same shape as the BUG-174 screenshot,
  just for LB-16216 instead of LB-13333 (data/site/files now holds near-duplicate
  LBF-13333-* and LBF-16216-* attachment sets for what appears to be the same Pensacola
  1992-09-12 PDub/Dolphinsmile recording, differing only by case in "pdub-dolphinsmile"
  vs "PDub-Dolphinsmile" — this is what the user's file-search screenshot showed).
  Confirmed via live API call (lb_number_hint=16216) that BUG-174's fix correctly
  produces 2 site_proposals, both matched_by:'name' with an MD5-mismatch warning, and
  that the LBF-13333-* vs LBF-16216-* sets do NOT cross-contaminate (prefix filter
  works as intended).
  However, three things suggest "MD5 mismatch" is not actually resolvable, and BUG-174's
  fix may just be the best available band-aid rather than a real fix:
    1. lbdir self-checksum (lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt, expected
       552493726c8ef51482445bf9dfd93649) is circular by construction — no copy of this
       file (cached site copy md5 82021addc07439e01c9e6f35b0ec7bb1, live site copy same,
       on-disk extras/ copy same) can ever match it.
    2. DigiFlawFinder-bd92-09-12-PDub-Dolphinsmile.flac1648.wavf.html (expected
       27b2c69b9ab753cec77fa1a4a7e7dc7c) is dynamically regenerated server-side: cached
       copy (May 23 scrape) is md5 9884fdafd42e61e4274aaa827ab297be (67345 B), but a
       fresh download today is md5 c36f0fce06e24b238cbc1dbee229e0be (63700 B) — despite
       an unchanged Last-Modified: Dec 2024 header. Neither matches expected_md5, and
       re-scraping will never produce a match since the content isn't stable.
    3. The folder also has extras/LBF-16216-lbdir-bd92-09-12-PDub-Dolphinsmile.flac1648.txt
       on disk, byte-identical (md5 82021add...) to the data/site/files copy BUG-174
       proposes copying in. find_reconcilable_files's on-disk scan only matches by exact
       MD5, so this local near-duplicate sits in unmatched_disk and is never offered as
       a rename candidate — the reconcile panel can show an "unmatched disk" file and a
       "site recovery" proposal that are really the same bytes under the same filename,
       which could read as two different candidate files to the user.
Fix: TBD — discussed but not yet implemented: extend find_reconcilable_files with the
  same name-based fallback (matched_by/expected_md5/MD5-mismatch flag) BUG-174 added to
  find_site_recoverable_files, so on-disk near-duplicates like extras/LBF-16216-lbdir-...
  surface as rename proposals too. Separately worth deciding whether self-referencing
  lbdir entries and regenerated report files should just be excluded from "missing"
  counts/integrity status entirely, since they can never pass by MD5 regardless of
  source. Revisit after more thought — user is not yet convinced BUG-174 is the final
  word here.


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
Note (2026-06-10): The "no resolution path in the GUI" symptom is now mitigated — the pipeline Lookup
  panel's Conflict state shows a "Which show is this?" picker with per-LB "Pin {lb} & continue", which
  writes a folder_lb_link row that wins over the raw multi-match set on the next lookup run. The
  underlying duplicate-checksum data issue (fix items 1-3 above) is still open.
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
