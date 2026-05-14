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
File(s): gui/attachments_tab.py:84-90
Reported: 2026-05-12
Fixed: 2026-05-12
Description: Qt logged "Release of profile requested but WebEnginePage still not deleted. Expect troubles!" on app exit. Qt's child-destruction order is unspecified, so the QWebEngineProfile (child of the tab) was sometimes destroyed before the QWebEnginePage that referenced it.
Root cause: Both profile and page were parented to self (the tab widget). Qt may destroy them in any order, and if profile goes first the page holds a dangling reference.
Fix: Parent the QWebEnginePage to the QWebEngineProfile instead of to self. Qt now guarantees that when profile is destroyed, it first destroys its own children (including page), eliminating the ordering hazard. Both objects are also stored as self._web_profile / self._web_page for explicit lifetime tracking.

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
