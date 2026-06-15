# Fixed Bugs Archive
# Active/open bugs are in BUGS.md. Entries here are Fixed or Wontfix.

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
