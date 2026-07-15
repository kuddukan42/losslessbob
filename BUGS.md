
BUG-249: pytest full-suite intermittent native crash in test_lb_master.py::test_status_combobox_exists
Status: Open
File(s): tests/test_lb_master.py:373
Reported: 2026-07-11
Description: Intermittent native crash (not a Python exception/traceback — process dies) in test_status_combobox_exists when run as part of the full pytest suite. Not reproduced in isolation. Observed during TODO-231 session (2026-07-11) while running the full suite for unrelated backend/ab_clips.py work; predates today's changes and is unrelated to them. Likely a native Qt/PyQt6 widget-teardown or event-loop interaction under pytest-qt when combined with other GUI tests earlier in the same suite run (ordering/state leakage), rather than a logic bug in the test itself. Root cause not yet investigated. Needs repro: re-run full suite a few times, note whether it always follows the same preceding test(s), and whether isolating the class or module avoids it.
Root cause: Unknown
Fix: —

BUG-210: backend/lossless_bob.db keeps reappearing in repo root (untracked, empty)
Status: Open
File(s): backend/lossless_bob.db (unknown origin)
Reported: 2026-06-18
Root cause: Unconfirmed. The real DB path is APP_ROOT/data/losslessbob.db (no underscore,
  see backend/paths.py:25 DB_PATH), and grepping the entire codebase (backend/, tools/,
  tests/, gui_next/src) for the literal string "lossless_bob" (with underscore) returns zero
  matches — no application code, test, fixture, or config constructs this filename. Deleting
  the file and re-running the full pytest suite + test_db_writes.py from backend/ as cwd did
  not recreate it. Likely created by an ad hoc shell/Python one-liner run with backend/ as cwd
  (e.g. a manual `sqlite3.connect("lossless_bob.db")` sanity check using a mistyped/placeholder
  filename instead of the real DB_PATH) rather than a reproducible app code path. Needs a repro
  case next time it reappears — note what command/action immediately preceded its creation.
Fix: TBD — pending repro. Stray file deleted from working tree each time it's noticed; it has
  never been committed (untracked since it doesn't match any .gitignore rule, but also isn't
  staged/added).

BUG-200: tapematch — report.md for 1999-02-25 Portland, Maine contains another session's tapematch output verbatim
Status: Open
File(s): data/tapematch/runs/20260602_205451_1999-02-25/report.md
Reported: 2026-06-17
Root cause: Unknown — found incidentally while scanning tapematch run dirs for BUG-199. The
  Coverage table and LB page commentary in this report.md are correctly for 1999-02-25
  Portland, Maine (LB-04452, LB-05683, LB-09627, LB-12715), but the entire `## tapematch
  output` fenced block (INGEST/TRIM through DIAGNOSTICS) is verbatim output from an unrelated
  2018-08-26 Auckland, New Zealand session (LB-13696, LB-13704, LB-13729) — none of the
  Portland LB numbers appear in that block and none of the Auckland LB numbers appear in the
  Coverage table. Looks like the wrong cached tapematch stdout was attached when this
  report.md was generated. Already flagged by a prior session in this run's own analysis.md
  but never logged as a tracked bug until now.
Fix: TBD — re-run tapematch for the 1999-02-25 Portland, Maine session to regenerate a
  correct report.md before any source-identity verdict can be drawn for LB-04452/LB-05683/
  LB-09627/LB-12715. Also worth checking the run/report-generation pipeline for how a
  different session's stdout could get attached, in case other run dirs are silently
  affected without an obvious Coverage-table/tapematch-output mismatch to notice it by.

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
