
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
