# Fixed Bugs Archive
# Active/open bugs are in BUGS.md. Entries here are Fixed or Wontfix.

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
