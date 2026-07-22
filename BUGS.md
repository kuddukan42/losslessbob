
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

BUG-252: LBDIR reconcile leaves self-referencing/regenerated entries permanently "MD5 mismatch" — BUG-174 fix may not be the final answer
Status: Open
File(s): backend/checksum_utils.py:find_site_recoverable_files, backend/checksum_utils.py:find_reconcilable_files
Reported: 2026-06-13
Renumbered: from BUG-175 on 2026-07-15 (TODO-248 — id collided with the unrelated fixed
  BUG-175 "Windows fonts render badly" in BUGS_DONE.md; pre-2026-07-15 references to BUG-175
  for the LBDIR reconcile MD5-mismatch issue mean this bug)
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
