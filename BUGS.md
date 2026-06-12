
BUG-155: DB — entry locations with non-ASCII chars stored corrupted (LB-16298 "Mnchen, Germany", ü dropped)
Status: Open
File(s): data/losslessbob.db (entries.location); likely backend/scraper.py or importer encoding path
Reported: 2026-06-10
Root cause: Not yet isolated. entries row for LB-16298 has location "Mnchen, Germany" — the "ü" was
  dropped (not mojibake'd), consistent with a cp1252/latin-1 decode that discarded the byte (see
  Known Pitfalls in CLAUDE.md). Effect: pipeline rename proposes the misspelled
  "2011-10-26 Mnchen, Germany (LB-16298)". Audit needed: other entries with umlauts/accents.
Fix: TBD — re-scrape affected entries with correct decoding; add an audit query for stripped chars.

BUG-146: build_standard_name produces xx/xx/YY folder date prefix for entries with unknown month/day
Status: Open
File(s): backend/torrent_maker.py:129, backend/folder_naming.py:72
Reported: 2026-06-09
Root cause: `_parse_date` catches `ValueError` from `int('xx')` and falls back to `date_str.strip()`, returning the raw DB string (e.g. `'xx/xx/65'`) unchanged. `build_standard_name` then uses this as the date prefix, producing `'xx/xx/65 HIGHWAY 61 ROM... (LB-12205)'`. Existing folders for these entries already use ISO-style `'1965-xx-xx ...'` format.
Fix: In `_parse_date`, detect `xx` parts before trying `int()` and emit ISO-style `YYYY-xx-xx` (or `YYYY-MM-xx`) for the known parts — e.g. `xx/xx/65` → `1965-xx-xx`, `3/xx/72` → `1972-03-xx`.

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
