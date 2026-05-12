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
