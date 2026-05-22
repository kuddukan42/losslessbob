# Completed TODO Archive
# Active/open tasks are in TODO.md. Entries here are Done or Cancelled.

TODO-066: Web GUI — docs update after web UI ships
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-063: Web GUI — status bar data in nav
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-062: Web GUI — frontend/index.html landing redirect
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-061: Web GUI — add nav links to admin.html and map.html
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-060: Web GUI — frontend/bootlegs.html Bootleg catalog browser
Priority: Low
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-059: Web GUI — frontend/lb_master.html LB Master viewer
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-058: Web GUI — frontend/entry.html Entry detail page
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-057: Web GUI — Collection tab write operations
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-056: Web GUI — frontend/collection.html Collection tab (read)
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-055: Web GUI — frontend/lookup.html Lookup tab
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-054: Web GUI — Search tab owned column async load
Priority: Medium
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-053: Web GUI — frontend/search.html Search tab
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-052: Web GUI — frontend/utils.js shared JS utilities
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-051: Web GUI — frontend/base.css shared dark theme
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

TODO-050: Web GUI — Flask routes for frontend static files
Priority: High
Status: Cancelled
Added: 2026-05-19
Closed: 2026-05-22
Description: Web GUI feature deferred indefinitely.

---

TODO-078: CLI daemon — Windows support for start_new_session
Priority: Low
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: _daemon_start() uses start_new_session=True which is a POSIX concept.
  On Windows the equivalent is DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP via
  subprocess creationflags. Add a platform check so daemon start works correctly
  on Windows.

TODO-084: Export HTML — decade/year filter dropdowns do not populate
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: Decade/year dropdowns in exported collection HTML were always empty because
  year was derived solely from entries.date_str, which is NULL for any collection row
  whose lb_number has no matching entries row.
Fix: In collection_export_html() (app.py), after failing to parse a 4-digit year from
  date_str, fall back to a regex search on folder_name for a 19xx/20xx year. This ensures
  rows where the LEFT JOIN misses still contribute a year to the JS DATA array so that
  filter(Boolean) retains them and both dropdowns populate.

---

TODO-081: Cross-tab folder sync — preload all first-4 tabs from Lookup folder selection
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: lbdir tab had no connection to Lookup folder list.
Fix: Added add_folders_from_lookup() to lbdir_tab.py (guard: only when list is empty).
  Wired in main_window.py _on_tab_changed alongside the existing Verify guard.

TODO-080: Rename tab — embed all LB alias numbers in folder name when aliases are present
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-22
Description: After alias collapse resolves a multi-candidate folder to a canonical LB,
  fetch all known aliases for that canonical and include them in the proposed folder name.
Fix: Added get_aliases_for_canonical() to backend/db.py. In rename_tab.py
  populate_from_lookup and _on_save_alias, after alias collapse fetches aliases via
  GET /api/lb_alias?canonical_lb=<lb> and builds combined suffix LB-canonical-LB-alias1...
  Display column shows "LB-12345 + LB-67890". Named convention documented in PROJECT.md.

TODO-077: Interactive REPL shell for CLI
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-21
Description: Refactor cli.py so running it with no arguments opens a persistent
  interactive shell (lb> prompt) with Flask started once in the background.
  Commands, tab-completion, readline history (~/.losslessbob_history), and
  per-command help (help <command>) all work inside the shell.
  One-shot mode unchanged for backward compatibility.

---

TODO-076: DB write function test battery
Priority: Medium
Status: Done
Added: 2026-05-21
Closed: 2026-05-21
Description: Write a comprehensive pytest battery for all database write functions in
  backend/db.py. Cover happy-path, idempotency, constraint violations (UNIQUE, CHECK,
  NOT NULL, PK, FK), rollback on error, and thread-safety. 115 tests in 17 classes
  across tests/test_db_writes.py.

---

TODO-075: FEAT-07 — Portable Export Formats (HTML + M3U)
Priority: Low
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Export My Collection as a self-contained HTML table (collection.html) or as an
  M3U playlist (collection.m3u). Backend: GET /api/collection/export/html and
  GET /api/collection/export/m3u in backend/app.py. GUI: "Export HTML…" and "Export M3U…"
  buttons in My Collection panel of gui/collection_tab.py.

---

TODO-074: Map tab rework — browser-only, consolidate geocoding
Priority: Medium
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Removed QWebEngineView from Map tab; map now opens in system browser.
  Moved geocoding controls (Run Geocoder, location overrides table) from Setup tab
  and DB Editor tab to Map tab. Map Filters group lets user pre-filter the browser URL.
  Freed space on Setup and DB Editor tabs.

---

TODO-073: FEAT-01 — CLI / Headless Mode
Priority: Low
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: Create cli.py in project root providing headless CLI for LosslessBob.
  Commands: lookup, search, stats, import, serve. Cross-platform: port-poll instead of
  time.sleep(), Waitress on Windows, forward-slash M3U paths. On Linux/macOS optionally
  chmod +x; on Windows invoke as python cli.py.

---

TODO-072: Audio filename reconcile on Lookup and Rename tabs
Priority: Medium
Status: Done
Added: 2026-05-20
Closed: 2026-05-20
Description: After a lookup, offer "Reconcile Audio Files" button that renames audio files
  on disk to match canonical filenames in the checksum DB. Available on Lookup tab (auto-enabled
  when mismatches are found) and Rename tab (scans checksum files in checked folders).
  Backend: POST /api/checksums/reconcile_audio + apply_reconcile_audio. GUI: AudioReconcileDialog
  in gui/widgets/reconcile_dialog.py. db_filename field added to lookup detail dicts.

---

TODO-071: FEAT-02 — Fuzzy Filename Matching Fallback
Priority: Low
Status: Cancelled
Added: 2026-05-20
Closed: 2026-05-20
Description: Fuzzy filename matching for NOT FOUND checksums using rapidfuzz.
  Cancelled — not useful. Lookup matches on checksum only; if the checksum doesn't
  match, a similar filename doesn't confirm anything about the recording content.

---

TODO-069: Generate, translate, and compile .ts/.qm files for 5 languages
Priority: Medium
Status: Done
Closed: 2026-05-20
Added: 2026-05-19
Description: Run pylupdate6 against all gui/*.py to extract tr() strings into
  gui/locales/losslessbob_{de,fr,es,it,nl}.ts. Fill all translations (AI-assisted
  batch is fine; review domain-specific terms against the glossary in CC_I18N.md).
  Compile each .ts to .qm with lrelease — target 0 untranslated warnings.
  Commit both .ts and .qm files. Prerequisite: TODO-068.
  See instructions/CC_I18N.md TODO-069 section for full spec and glossary.

---

TODO-068: Wrap all user-facing GUI strings in self.tr()
Priority: Medium
Status: Done
Closed: 2026-05-20
Added: 2026-05-19
Description: Go through all 14 gui/*.py files and gui/widgets/*.py and wrap every
  user-facing string literal in self.tr("..."). Convert f-strings with variables to
  self.tr("template {}").format(var). Do NOT wrap log messages, SQL, API URLs, or
  archive data (LB numbers, checksums, filenames). Run py_compile after each file.
  ~1,209 call sites total. Prerequisite: TODO-067 (i18n.py must exist first).
  See instructions/CC_I18N.md TODO-068 section for rules and file-by-file checklist.

---

TODO-067: i18n infrastructure — language loader, meta key, Setup tab selector
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Create gui/i18n.py with load_language() and supported_languages() helpers.
  Wire language loading at QApplication startup (read ui_language from meta table).
  Add POST /api/meta route to backend if not present (whitelist key=ui_language).
  Add language selector QComboBox to Setup tab Preferences section with restart notice.
  Supported languages: de, fr, es, it, nl (all LTR — no layout mirroring needed).
  See instructions/CC_I18N.md TODO-067 section for full spec.

---

TODO-065: Web GUI — web password setting in Setup tab
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-20
Description: Add "Web GUI Password" QLineEdit (password mode) in Setup tab Network section.
  POSTs to /api/db/settings with {web_password: "..."}. Empty = auth disabled. Add
  web_password to the GET keys list in db_settings() (return "set"/"" not actual value).
  See CC_WEB_GUI_PLAN.md TODO-065.

---

TODO-064: Web GUI — optional basic-auth middleware for web routes
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-20
Description: Add before_request hook in backend/app.py that enforces HTTP Basic Auth on
  /web/* and /frontend/* routes when meta key web_password is set. API routes (/api/*)
  remain unauthenticated (desktop app calls them directly). Flask already binds to
  0.0.0.0 so this is needed before any web UI page ships.
  See CC_WEB_GUI_PLAN.md TODO-064.

---

TODO-049: Windows — HiDPI-aware splash screen pixmap
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: The splash screen in main.py creates QPixmap(400, 120) without considering the
  display's device pixel ratio. On Windows with 125%/150%/200% scaling the splash appears
  blurry. Should query QScreen.devicePixelRatio() before QApplication is shown, create the
  pixmap at (400*dpr) × (120*dpr), and call pixmap.setDevicePixelRatio(dpr) so Qt renders
  it at native resolution.

---

TODO-048: Windows — consolidated /api/status endpoint to halve loopback overhead
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _refresh_status() in main_window.py makes two sequential HTTP GETs every 10 s:
  /api/db/stats then /api/bootlegs/stats. On Windows, loopback TCP has more overhead than
  Linux. Add GET /api/status returning both payloads merged; update _refresh_status() to use
  the single call. Reduces per-tick network cost and simplifies the error path.

---

TODO-047: Windows — replace per-tick daemon thread in _refresh_status with persistent worker
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _refresh_status() in main_window.py (main_window.py:216) spawns a new
  threading.Thread every 10 s. On Windows, thread creation costs ~0.5–2 ms (kernel TLS init
  + scheduler registration) vs ~100 µs on Linux. Over a long session this is measurable churn.
  Replace with a single persistent QThread (or threading.Thread with a threading.Event sleep
  loop) that polls at the same 10 s interval without re-creating OS threads.

---

TODO-046: Windows — QGraphicsDropShadowEffect on 11 panels causes repaint lag
Priority: Medium
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: _apply_shadows() in main_window.py applies a blurRadius=12 QGraphicsDropShadow-
  Effect to 11 widgets (Lookup, Rename, Search, Collection ×2, Verify ×2, lbdir ×2, Bootlegs).
  On Windows, Qt renders the Fusion style entirely in software; the shadow forces each affected
  widget to blit into an offscreen buffer, apply a Gaussian blur, and composite back on every
  repaint. With large tables this causes visible lag during resize/scroll. Options:
    (a) Skip shadows on Windows:  `if sys.platform != "win32": apply_panel_shadow(…)`
    (b) Reduce blurRadius from 12 to 4 and offset from (0,2) to (0,1) to lower cost on all platforms.
  Option (a) is the safest short-term fix. Option (b) benefits all platforms.

---

TODO-045: Windows — rglob("*") on main thread in Verify and lbdir "Add Root Folder"
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: verify_tab._on_add_root_folder (verify_tab.py:304) and
  lbdir_tab._on_add_root_folder (lbdir_tab.py:608) both call sorted(root_path.rglob("*"))
  synchronously on the Qt main thread after the file dialog closes. On Windows with NTFS and
  large collections, this freezes the GUI ("Python not responding"). This is the same pattern
  fixed for collection_tab in BUG-034; see _ScanWorker there for the reference fix.
  Fix: add a _AddRootWorker(QThread) to each tab that runs the rglob traversal off-thread,
  emits the discovered folder list, and lets the main thread update the listbox.
  See also: BUG-080.

---

TODO-044: Windows — --disable-gpu Chromium flag applied on Windows, killing GPU acceleration
Priority: High
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: main.py:157–165 unconditionally appends --disable-gpu and --disable-logging to
  QTWEBENGINE_CHROMIUM_FLAGS. These flags were added to work around Linux/XWayland issues
  (EGL_BAD_NATIVE_WINDOW, GPU-process blackout — see BUG-053, BUG-060). On Windows,
  Chromium uses DirectX/ANGLE for GPU compositing, which works well and produces smooth
  scrolling in the Map tab and Attachments tab. Forcing --disable-gpu switches Chromium to
  Swiftshader software rendering, making both tabs noticeably laggy.
  Fix: wrap the flag injection in `if sys.platform != "win32":` so Windows retains GPU
  acceleration while Linux still gets the XWayland workarounds.

---

TODO-043: Admin panel — site-crawler control and live status dialog
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Extend the /admin panel to control the master website site_crawler.
  Site Crawler card: Incremental / Full / Stop buttons, progress bar, live status line.
  Live View modal: polls /api/crawler/status every 1.5 s; shows stage, fetched/304/skipped/
  failed counts, current URL. /api/admin/status now includes "crawler" snapshot.

TODO-042: Mobile-friendly admin control panel
Priority: Low
Status: Done
Added: 2026-05-19
Closed: 2026-05-19
Description: Web admin page at /admin for managing the backend from mobile or browser.
  Features: DB stats/backup/reset, flat-file update pipeline, scraper start/stop,
  LB master reconcile, server restart (os.execv). Routes: GET /admin,
  GET /api/admin/status, POST /api/admin/restart.

TODO-041: Backend geocoding API endpoints
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: The curator geocoding GUI added in setup_tab.py and dbedit_tab.py requires four backend routes that do not yet exist:
  POST /api/geocode/run        — start geocoder; body {retry_failed: bool}; returns 409 if already running
  GET  /api/geocode/status     — poll running state; returns {running, done, total, current, errors}
  GET  /api/geocode/locations  — list geocoded location rows; query param filter=all|failed|low_confidence|manual
  POST /api/geocode/location   — save a manual lat/lon; body {location, lat, lon, note}
Nominatim (geopy or direct HTTP) should be used with a polite 1-request-per-second rate limit and User-Agent header. DB schema: location_geocodes(location_text PK, source, confidence, lat, lon, is_manual, note, geocoded_at). Add to MASTER_TABLES.

---

TODO-040: [TODO-031 Step 9] Docs — update PROJECT.md and CHANGELOG.md after scraper work
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: After TODO-032 through TODO-039 are complete: update PROJECT.md file structure tree (new backend/site_crawler.py, gui/scraper_tab.py), DB schema section (scrape_sessions + page_cache_state), API routes section (/api/crawler/*), and Tech Stack table if any new deps were added. Prepend CHANGELOG.md entry summarising the full TODO-031 scraper tab implementation. This TODO should be the last closed item in the TODO-031 work sequence.

---

TODO-039: [TODO-031 Step 8] gui/main_window.py — register Scraper tab, update order
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Import ScraperTab from gui/scraper_tab.py. Add it to the tab widget after Setup (or wherever fits the intended tab order). Update tab count assertions or comments if present. Verify no initialization-order issues with other tabs that may reference scraper state.

---

TODO-038: [TODO-031 Step 7] gui/setup_tab.py — strip all scraper controls
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Remove from gui/setup_tab.py: all entry-scraper controls (Scrape All Missing, Scrape Range, Single Entry, Force re-scrape, Use local pages, Download attachments, Re-scrape Private LBs, Download Missing Pages, delay spinner, progress bar, stop button), the Bootleg Catalog scrape section, and the scraper log widget. Keep: DB management, master data import/export, SoX path, and forum credentials. Update any signals/slots that referenced removed widgets.

---

TODO-037: [TODO-031 Step 6] gui/scraper_tab.py — 6 sub-panels
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create gui/scraper_tab.py with 6 collapsible QGroupBox panels: (1) Control & Status — scope selector, Start/Stop/Pause, live ticker, progress bar, counts; (2) Entry Pages — existing scraper controls moved from Setup tab; (3) Bootleg Catalog — existing LBBCD scrape controls moved from Setup tab; (4) Session History — scrape_sessions table, click-to-filter Change Log; (5) Change Log — queryable entry_changes joined to scrape_sessions; (6) Settings — delay, jitter, daily cap, toggles. Move scraper log widget here from Setup tab.

---

TODO-036: [TODO-031 Step 5] API routes /api/crawler/* in app.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add Flask routes to backend/app.py: POST /api/crawler/start (body: {scope, start_url, force}), GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/history (paginated scrape_sessions rows), GET /api/crawler/page_cache (paginated page_cache_state). Follow existing scraper route patterns. Add migration comment if any existing route signature changes.

---

TODO-035: [TODO-031 Step 4] backend/site_crawler.py — spider engine
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Create backend/site_crawler.py with: crawl(start_url, session_id, force, scope), _discover_links(html, base_url), _fetch_page(url, stored_last_modified) → (status, body, last_modified), _cache_path(url) mapping URLs to data/pages/ sub-dirs, get_crawler_status(), stop_crawler(). Rate limiting: 1500ms default delay ±20% jitter, 750ms for 304-check-only requests, Retry-After on 429, exponential backoff on connection error. Daily request cap. robots.txt read once per session. Separate _crawler_state dict and _crawler_lock (does not share state with scraper.py).

---

TODO-034: [TODO-031 Step 3] Update path refs in scraper.py, app.py, forum_poster.py, attachments_tab.py
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Audit all imports of PAGES_DIR and ATTACHMENTS_DIR across scraper.py, app.py, forum_poster.py, and gui/attachments_tab.py. Confirm they still point to the correct locations after the SITE_DIR addition in TODO-032. Add SITE_DIR import where site-crawled content will be read. No functional behaviour change — path wiring only.

---

TODO-033: [TODO-031 Step 2] db.py — scrape_sessions + page_cache_state tables + helpers
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Add scrape_sessions(id PK, started_at, finished_at, scope, start_url, pages_fetched, pages_304, pages_skipped, pages_failed, files_fetched, status, notes) and page_cache_state(url TEXT PK, last_fetched_at, last_modified, body_sha256, content_type, size_bytes, status_code, session_id FK) to db.py init_db(). Add helpers: create_scrape_session(), update_scrape_session(), upsert_page_cache(), get_page_cache(url), get_scrape_sessions(). Use idempotent ALTER TABLE / CREATE TABLE IF NOT EXISTS for safety on existing DBs.

---

TODO-032: [TODO-031 Step 1] paths.py — replace PAGES_DIR/ATTACHMENTS_DIR with SITE_DIR hierarchy
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: In backend/paths.py, add SITE_DIR = DATA_DIR / "pages" / "site" and ensure PAGES_DIR and ATTACHMENTS_DIR constants remain unchanged (detail pages and attachments dirs are not moving). Create the data/pages/lbbcd/ and data/pages/site/ sub-directories as needed. No consumer code changes in this step — those follow in TODO-034.

---

TODO-031: Dedicated Scraper tab + full-site crawler (replaces scraping section in Setup)
Priority: High
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Move all scraping controls out of Setup tab into a dedicated Scraper tab. Add a full domain-aware site crawler that produces a complete offline mirror of losslessbob.wonderingwhattochoose.com using If-Modified-Since for efficient incremental updates. Sub-tasks: TODO-032 through TODO-040.

---

TODO-030: Bootleg-CD Catalog (LBBCD) — scraper, tables, Bootlegs tab, and cross-tab integration
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: Scrape and store the LosslessBob bootleg titles catalog from LB-bootleg-by-title.html.
  Schema: bootleg_titles + bootleg_scrapes tables (added to MASTER_TABLES). New backend/bootleg_scraper.py.
  New gui/bootlegs_tab.py. 5 new /api/bootlegs/* routes. Cross-tab integrations: Search (badge),
  Lookup (titles in summary), Collection (Bootleg column), DB Editor (bootleg count).

---

TODO-029: Save / restore column-width defaults across all GUI tabs
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: Allow the user to snapshot their current column layout as reusable defaults and restore to them (or to factory defaults) on demand. GuiStateStore: save_user_defaults(), restore_user_defaults(), restore_factory_defaults(). UI: "Column Widths" group in Setup/Theme tab with Save/Restore/Factory buttons.

---

TODO-028: Click-to-sort on Rename tab main table
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-20
Description: Rename tab uses RenameModel (QAbstractTableModel) + QTableView. Added QSortFilterProxyModel wrapper. lessThan() sorts by: Current Folder Name, LB Found (numeric), Proposed Name, State (custom rank). Wire header sectionClicked; default sort by Current Folder Name ASC. Proxy maps indices back to source before mutating.

---

TODO-027: Click-to-sort on Lookup tab summary and detail tables
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: Lookup tab uses QAbstractTableModel + QTableView. Added QSortFilterProxyModel wrapper to both tables. Custom lessThan() uses typed sort keys consistent with sort_key_for(). Wire header sectionClicked to toggle direction. Default: summary sorted by LB Number ASC, detail by Filename ASC.

---

TODO-026: Flat-file update check rework (CC_LB_INTEGRITY item 9)
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: New backend/flat_file.py pipeline: discover→download→diff→apply with audit trail in flat_file_releases + flat_file_changelog tables. 7 new API endpoints under /api/flat_file/*. Setup tab UI rework with _DiscoverThread, _UpdateAvailableDialog, Flat File History panel. Removed broken check_for_update() from scraper.py.

---

TODO-025: Click-to-sort across all tables
Priority: Medium
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: SortableTableItem and sort_key_for() in gui/widgets/sort_keys.py. Client-side sort for lbdir and verify QTableWidget tables. In-memory sort for Search, Collection, Missing QTableView tables. Server-side sort for DB Editor. GuiStateStore.get_sort()/set_sort() added.

---

TODO-024: Override export/import JSON
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-18
Description: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import. DB Editor buttons for Export and Import Overrides in the Integrity panel.

---

TODO-023: Reliable column width persistence (CC_LB_INTEGRITY item 11)
Priority: Medium
Status: Done
Added: 2026-05-17
Closed: 2026-05-17
Description: GuiStateStore in gui/widgets/state_store.py storing state in data/gui_state.json (atomic writes, 500ms debounce, _restoring guard). Migrated all tabs off QSettings / hardcoded setColumnWidth. One-time QSettings migration on first run. Covers Search, Collection (7 tables), DbEdit, lbdir summary, Rename. ThemeTab QSettings and main_window geometry also migrated to GuiStateStore.

---

TODO-022: GitHub release upload from "Publish Master Update" button
Priority: Low
Status: Done
Added: 2026-05-17
Closed: 2026-05-19
Description: After the export endpoint produces data/exports/<file>.db + .manifest.json, automate the upload to the kuddukan42/losslessbob GitHub releases via the gh CLI. Tag scheme: master-YYYY-MM-DD with auto-bump (.2, .3) on same-day re-release. Auto-generate release notes from lb_status_history rows since the last published master_version.

---

TODO-021: Status filter combobox on remaining tabs (Lookup, Attachments, Rename, Verify, lbdir)
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: lb_status background coloring and optional filter combobox. Done: Lookup tab (filter combobox + Private/Missing row tinting), Attachments tree (page-level batch tinting), Rename tab (LB Found col tint), Lbdir summary (LB# col tint). Verify tab skipped — lb_number not available in verify results without backend change.

---

TODO-020: Master data publish/subscribe system (curator workflow)
Priority: Low
Status: Done (partial — GitHub release publishing deferred)
Added: 2026-05-16
Closed: 2026-05-17
Description: POST /api/master/export and POST /api/master/import. MASTER_TABLES / USER_TABLES / MASTER_META_KEYS constants. Curator-mode flag + checkbox. 13 tests in tests/test_master_data.py. GitHub-release-via-gh-CLI upload deferred (see TODO-022).

---

TODO-019: lb_alias and folder_lb_link disambiguation tables
Priority: Low
Status: Done
Added: 2026-05-16
Closed: 2026-05-18
Description: lb_alias (master) and folder_lb_link (user) tables. Rename tab resolution order: folder_lb_link first, lb_alias collapse second, fall back to multiple_ids. Curator creates aliases in DB Editor Aliases panel. 7 API endpoints. Right-click "Link…"/"Unlink…"/"Save as master alias…" actions in Rename tab.

---

TODO-018: NFT folder-name suffix for Private LBs
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: _apply_status_suffix() helper in backend/folder_naming.py. Rename tab and Collection tab append -NFT to proposed folder names for Private LBs. GET /api/lb_master/<lb>/nft integration.

---

TODO-017: Periodic re-scrape of Private LBs to detect newly-published pages
Priority: Medium
Status: Done
Added: 2026-05-16
Closed: 2026-05-17
Description: "Re-scrape Private LBs" button in Setup tab. Iterates every lb_status='private' row, attempts a fresh scrape, calls reconcile_lb_status() to flip status if a page is now found. Shows completion summary.

---

TODO-016: Make forum post footer attribution (username/version) configurable
Priority: Low
Status: Done
Added: 2026-05-15
Closed: 2026-05-18
Description: Read username from forum credentials and version from a project constant. Footer no longer hardcoded in forum_poster.py.

---

TODO-015: db_reset should drop torrents and rename_history tables
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: Added DROP TABLE IF EXISTS rename_history and torrents to the executescript drop sequence in backend/app.py:db_reset.

---

TODO-014: Confirm _mychecksums filename convention and finalize TORRENT_EXCLUDE
Priority: Low
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: generate_checksums() renamed from _lbgen_* to _mychecksums_* convention; TORRENT_EXCLUDE_PATTERNS already matched this pattern and requires no change.

---

TODO-013: Path relocation flow for stale torrent records
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: When a torrent's source_folder is no longer valid (red indicator in the history panel), allow the user to browse for the new folder location, cross-check files against checksums, and optionally rename the folder to the standard format.

---

TODO-012: Torrent history panel in My Collection tab
Priority: Medium
Status: Done
Added: 2026-05-14
Closed: 2026-05-14
Description: Torrent history sub-panel in My Collection tab. Green/red indicator for source_folder_exists; Regenerate button when torrent_path is missing; Add to qBittorrent and added_to_qbt_at per record.

---

TODO-011: xref filter on Search and Collection tabs
Priority: Low
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: "Xref only" checkbox on Search tab and My Collection tab. Backed by GET /api/checksums/xref_lb_numbers (db.get_xref_lb_numbers).

---

TODO-010: xref support in lookup, rename, search, collection
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: xref support across all tabs. Naming: LB-XXXXX-xrefXXXX (zero-padded to 4 digits). Lookup duplicate resolution, Rename xref suffix, Search/Collection xref filters, complete xref match wins over partial primary LB match.

---

TODO-009: Rename tab — Multiple IDs right-click resolution
Priority: Medium
Status: Done
Added: 2026-05-13
Closed: 2026-05-14
Description: Right-click context menu for "Multiple IDs" rename reason. Select which LB to apply; block rename until ambiguity resolved. Unique color for Multiple IDs.

---

TODO-008: FEAT-14 — Database Editor Tab
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: DB Editor tab (gui/dbedit_tab.py) with table browser, paginated row viewer, inline cell editing, row deletion, CSV export. Backend routes: GET /api/dbedit/tables, schema, rows, PATCH row, DELETE rows, GET export.

---

TODO-007: FEAT-13 — Granular Collection Data Management
Priority: High
Status: Done
Added: 2026-05-13
Closed: 2026-05-13
Description: Fine-grained purge control for user data (collection, wishlist, personal meta, integrity events, entry changes). Bulk delete from collection tab. Select All/None buttons in My Collection.

---

TODO-006: Close stale temp-DB connection in importer._import_flat_file
Priority: Low
Status: Done
Added: 2026-05-12
Closed: 2026-05-18
Description: Delete the cached entry from _local.connections for the temp path after unlink to avoid stale handle on next import in the same thread.

---

TODO-005: GUI viewer for entry change history (DB-08 follow-up)
Priority: Low
Status: Done
Added: 2026-05-12
Closed: 2026-05-19
Description: "History" button on the detail panel calls GET /api/entry/<lb>/changes and displays a table of field diffs with timestamps.

---

TODO-004: Add type hints and docstrings to app.py route handlers
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-19
Description: Flask route functions now have type hints and Google-style docstrings per project code standards.

---

TODO-003: Add type hints and Google-style docstrings to scraper.py public functions
Priority: Medium
Status: Done
Added: 2026-05-07
Closed: 2026-05-19
Description: `scrape_entry`, `scrape_range`, `get_scrape_status`, `stop_scrape`, and `check_for_update` have type hints and docstrings.

---

TODO-002: Bulk-download pages HTML to pages/ folder without scraping metadata
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: "Download Pages Only" button fetches and caches all missing LB-XXXXX.html files to data/pages/ without parsing metadata or writing to the DB.

---

TODO-001: Show local pages coverage count in Setup tab
Priority: Low
Status: Done
Added: 2026-05-07
Closed: 2026-05-18
Description: Display a count of HTML files present in `data/pages/` next to the "Use local pages" checkbox (e.g. "13,124 pages cached").

---

TODO-024: Map tab — interactive map of concert locations
Priority: Low
Status: Done
Added: 2026-05-18
Closed: 2026-05-19
Description: gui/map_tab.py using QWebEngineView + Leaflet.js to render concert locations from location_geocoded table as clickable markers. Phase 1: basic map. Phase 2 (CC_MAP_FEATURE.md fully implemented): local Leaflet assets, QWebChannel bridge (_MapBridge), Viewport Filter toggle, "List in Search", curator geocoding panel in DB Editor.
