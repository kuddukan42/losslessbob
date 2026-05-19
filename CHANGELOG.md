[2026-05-19] — fix(backend/gui): map showed only 434 markers instead of ~9,700 (BUG-075)

Fixed

  backend/app.py: api_map_data() now passes owned=None (no filter) when the
    'owned' query param is absent; previously defaulted to False which applied
    a "non-owned only" WHERE clause. Also accepts "1" as a truthy value for
    the owned=true filter so the Owned-only checkbox works.
  gui/resources/map.html: JS popup corrected to read m.lb_number, m.date_str,
    m.lb_status instead of non-existent m.lb, m.date, m.status field names.
    owned filter now sends owned=true (was owned=1, not matched by Flask).

[2026-05-19] — chore(backend): add __main__ block to app.py for headless backend

Added

  backend/app.py: `if __name__ == "__main__":` entry point so the Flask
    server can be started without the GUI via `python -m backend.app [port]`.
    Port defaults to 5174; pass an integer argument to override.

[2026-05-19] — fix(db): exclude low-confidence geocodes from map markers (BUG-074)

Fixed

  backend/db.py: get_map_data JOIN on location_geocoded now filters out
    confidence='low' rows. Previously, low-confidence Nominatim matches
    (e.g. "Japan 2001" → a village in Indonesia) were shown as map markers.
    They are now counted as unplottable instead.

[2026-05-19] — chore(main): bind Flask to 0.0.0.0 for LAN accessibility

Changed

  main.py: Flask server now listens on 0.0.0.0 instead of 127.0.0.1, making all routes
    (including /map and /api/*) reachable from other machines on the local network.
    The local readiness probe in _wait_for_port still uses 127.0.0.1.

[2026-05-19] — fix(geocoder): retry on HTTP 429 with 60-second back-off (BUG-069)

Fixed

  backend/geocoder.py: geocode_one() now catches urllib.error.HTTPError before the generic
    Exception handler; a 429 response raises the private _RateLimitError sentinel instead of
    silently producing source='failed'. run_batch() wraps geocode_one() in a retry loop (up
    to _MAX_429_RETRIES=3 attempts); on each _RateLimitError it sets stage='rate_limited',
    sleeps _RATE_LIMIT_SLEEP=60 s, then retries without advancing the progress counter. If
    all retries are exhausted the location is written as source='failed' with a descriptive
    note so it can be picked up by --retry-failed later.

[2026-05-19] — feat(gui): column-width save/restore defaults in Setup tab (TODO-029)

Added

  gui/widgets/state_store.py: import weakref; self._registered list tracks every attach_table()
    call as (weakref.ref(table), key, factory_defaults). New methods: has_user_defaults (property),
    save_user_defaults(), restore_user_defaults(), restore_factory_defaults(), clear_user_defaults(),
    _apply_col_widths(). save/restore write immediately (no debounce); _apply_col_widths uses
    _restoring guard so programmatic resize doesn't trigger spurious live-width saves.
  gui/setup_tab.py: accepts state_store=None; new "Column Widths" QGroupBox with three buttons —
    "Save as Defaults", "Restore My Defaults" (disabled when no snapshot exists), "Restore Factory"
    (confirmation required). Status label shows saved vs. none state. _refresh_col_defaults_status()
    syncs button enable state on init.
  gui/main_window.py: SetupTab now receives state_store=self.state_store.

Fixed

  gui/setup_tab.py: removed duplicate layout.addWidget(ff_group) at end of _build_ui().

[2026-05-19] — feat(gui): click-to-sort on Lookup tab summary and detail tables (TODO-027)

Added

  gui/lookup_tab.py: _LookupSortProxy (QSortFilterProxyModel with lessThan() using sort_key_for());
    _SUMMARY_COL_KINDS / _DETAIL_COL_KINDS column kind arrays; _sum_src_row() / _det_src_row()
    helpers to map proxy→source indices. Both summary (default: LB Number ASC) and detail (default:
    Filename ASC) views now support click-to-sort with sort indicator arrows. All selection handlers,
    context menus, double-click, and _on_select_all_incomplete updated to use source row mapping.

---

[2026-05-19] — feat(backend/gui): auto GitHub release upload from Publish button (TODO-022)

Added

  backend/db.py: generate_release_notes() — markdown from lb_status_history + manual overrides
    since the previous master_published_at.
  backend/app.py: GET /api/master/status (returns master_version + master_published_at);
    POST /api/master/github_release — generates tag (master-YYYY-MM-DD[.N]), builds release notes,
    runs gh release create, returns {ok, tag, url}.
  gui/setup_tab.py: _GithubReleaseThread; _on_publish_master now reads prev master_published_at,
    exports, then uploads to GitHub in a background thread; _on_github_release_done shows tag + URL;
    _publish_status_label shows live progress below the Publish button.

---

[2026-05-19] — feat(gui): entry change history viewer in Lookup tab (TODO-005)

Added

  gui/lookup_tab.py: _ChangeHistoryDialog + _ChangeHistoryWorker; "History…" button in detail
    panel header, enabled when exactly one LB is selected in summary; fetches up to 200 rows from
    GET /api/entry/<lb>/changes and displays field, old value, new value, changed_at in a resizable
    table; background fetch never blocks the GUI thread.

---

[2026-05-18] — feat(gui): add curator geocoding controls to Setup tab and DB Editor tab

Changed

  gui/setup_tab.py: add Geocode Locations group box (curator only) with progress polling; _GeocodeRunThread POSTs /api/geocode/run, _GeocodeStatusThread polls /api/geocode/status every 2 s; group shown/hidden on curator toggle.
  gui/dbedit_tab.py: add Location Geocoding sub-panel (curator only) with filter dropdown (All/Failed/Low Confidence/Manual Only), Load button calling GET /api/geocode/locations, QTableWidget (7 cols, first col stretches), double-click → PlaceManualDialog; PlaceManualDialog pre-fills lat/lon/note, Save POSTs /api/geocode/location; all HTTP calls via _Worker(QThread), never on GUI thread.

---

[2026-05-18] — fix: crawler seeded from wrong URL + test suite (BUG-067, BUG-068)

Fixed

backend/site_crawler.py: Added SITE_HOME_URL = BASE_URL + "/LosslessBob.html" (real site entry point; domain root is a DreamHost placeholder). Changed crawl() default start_url from BASE_URL to SITE_HOME_URL. Added SEED_URLS constant (/bynumber/LBMbynumber.html, /detail/LB-bootleg-by-title.html) seeded on every crawl as safety-net index pages. Changed BeautifulSoup parser from "lxml" to "html.parser" (eliminates lxml import, removes deprecation warnings). Removed unused attachment_path import and unused local variable. (BUG-068)
backend/html_utils.py: Changed BeautifulSoup parser from "lxml" to "html.parser". (BUG-067)
backend/db.py: Fixed get_scrape_sessions() ORDER BY to add id DESC tiebreaker so sessions created within the same second are reliably ordered by insertion sequence.

Added

tests/test_scraper_crawler.py: 59-test suite covering html_utils.rewrite_links() (9 tests), paths.py SITE_DIR hierarchy (7 tests), db.py scrape_sessions+site_inventory helpers (14 tests), site_crawler.py pure URL utilities (18 tests), and /api/crawler/* Flask route smoke tests (7 tests). All 59 pass individually; see BUG-067 for combined-run limitation.

---

[2026-05-18] — feat: Dedicated Scraper tab + full-site mirror crawler (TODO-031)

Added

backend/site_crawler.py: BFS spider for losslessbob.wonderingwhattochoose.com. crawl(start_url, scope, force, delay_ms, daily_cap) runs in a daemon thread. _extract_links() discovers same-domain links. _fetch_page() uses If-Modified-Since for efficient incremental fetches (304 = skip, 200 = save + rewrite links). _url_to_local() maps URLs to data/site/ sub-dirs. Separate _crawler_state/_crawler_lock (no shared state with scraper.py). Rate limiting: 1500ms ±20% jitter, Retry-After on 429, exponential backoff on error, configurable daily cap, robots.txt cached per session.
backend/html_utils.py: rewrite_links(html, page_url, base_domain) — rewrites server-absolute paths to relative paths so cached pages work via file:// browsing. Uses BeautifulSoup; processes href, src, action attributes.
backend/paths.py: SITE_DIR = DATA_DIR / "site" and sub-constants SITE_DETAIL_DIR, SITE_FILES_DIR, SITE_LBBCD_DIR, SITE_BN_DIR replacing old PAGES_DIR/ATTACHMENTS_DIR. detail_page_path(), attachment_path(), find_lbdir_attachment() updated to use SITE_DETAIL_DIR / SITE_FILES_DIR. ensure_data_dirs() creates all site/ sub-dirs.
backend/db.py: scrape_sessions and site_inventory tables added to SCHEMA_SQL and MASTER_TABLES. Helpers: create_scrape_session(), finish_scrape_session(), get_scrape_sessions(), upsert_inventory(), get_inventory_stats(), get_inventory_page(), get_pending_urls(), get_downloaded_urls().
backend/app.py: 6 new routes: POST /api/crawler/start, GET /api/crawler/status, POST /api/crawler/stop, GET /api/crawler/sessions, GET /api/crawler/inventory, GET /api/crawler/inventory/stats. backend.site_crawler imported at module level. _crawler_thread single-element list for background thread ref.
gui/scraper_tab.py: New Scraper tab. 5 panels (crawler control, session history, site inventory, entry scraper, bootleg catalog). _CrawlerStatusThread + _ScrapeStatusThread poll respective status endpoints every 1s. All scraper controls migrated from SetupTab. Settings (delay, daily cap) persisted to DB via /api/db/settings.
gui/main_window.py: ScraperTab imported and registered at tab index 10 (between DB Editor and Setup). Tab count: 12 → 13. Tab order comment updated.

Changed

gui/setup_tab.py: Removed all scraper controls (panels, buttons, progress bar, log widget, _log/_on_stop_scrape/_refresh_log_size methods, _LOG_FILE import). Kept: DB management, master data, qBittorrent credentials, WTRF Forum credentials, SoX status, flat-file update history, data-management purge controls. Dead _refresh_log_size() call removed from __init__.
backend/scraper.py: All path references updated from data/pages/ / data/attachments/ to data/site/detail/ / data/site/files/ via SITE_DETAIL_DIR / SITE_FILES_DIR / detail_page_path() / attachment_path() from paths.py.

---

[2026-05-18] — feat: Bootleg-CD Catalog (LBBCD) — scraper, Bootlegs tab, cross-tab integrations (TODO-030)

Added

backend/bootleg_scraper.py: scrape_bootlegs(force) — HEAD→diff→apply pipeline for the LBBCD index page. _parse_date() handles M/D/YY with 'xx' unknowns (2-digit year pivot Y>=30→19YY). _diff() uses (lb_number, title, date_str) natural key. Pre-scrape DB backup via backup_database(). bootleg_scrapes audit row written on every run. get_scrape_status() for polling.
backend/db.py: bootleg_titles + bootleg_scrapes tables added to SCHEMA_SQL and MASTER_TABLES. MASTER_SCHEMA_VERSION bumped to 2. Helper functions: get_bootleg_lb_numbers(), get_bootlegs_for_lb(), get_bootleg_stats(), get_bootlegs() (paginated/filtered), get_bootleg_scrape_history(). _BOOTLEG_SOURCE_URL constant.
backend/app.py: 7 new routes: POST /api/bootlegs/scrape, GET /api/bootlegs/scrape/status, GET /api/bootlegs/lb_numbers, GET /api/bootlegs, GET /api/bootlegs/by_lb/<lb>, GET /api/bootlegs/scrapes, GET /api/bootlegs/stats. bootleg_scraper imported.
gui/bootlegs_tab.py: New Bootlegs tab. Filter bar (text, year range, CDs, status, owned, has-LBBCD). Paginated QTableView (QAbstractTableModel). Detail pane with LBBCD link + "other titles for this LB" panel. open_lb_in_search signal → MainWindow switches to Search tab. bootleg_lbs_loaded signal pushes LB-number set to Search tab for badge rendering.
gui/main_window.py: Bootlegs tab registered at index 5 (between Search and My Collection). _on_bootleg_open_lb() handler. bootleg_lbs_loaded wired to search_tab.set_bootleg_lbs(). Shadow applied to bootlegs_tab.view. Status bar includes "Bootlegs: N" count when catalog is populated.
gui/search_tab.py: SearchModel._bootleg_lbs set; LB Number column shows 🎵 badge when lb_number is in the bootleg set; tooltip explains the badge. set_bootleg_lbs() public method on SearchTab.
gui/setup_tab.py: "Bootleg-CD Catalog (LBBCD)" QGroupBox added to layout; "Scrape Bootleg Catalog" button + Force checkbox + status label; bootleg scrape history table (5 columns); _on_scrape_bootlegs(), _poll_bootlegs_scrape(), _load_bootlegs_history() handlers. History loads on showEvent.

---

[2026-05-18] — feat(backend/gui): Download Missing Pages — cache HTML without metadata scrape (TODO-002)

Added

backend/scraper.py: download_pages_range(lb_numbers, force, delay_ms) — fetches detail pages and saves them to data/pages/ using the existing _scrape_state so the progress bar, stop button, and log all work. last_action="downloaded" distinguishes page fetches from full metadata scrapes. 404s are treated as skipped (not errors) since no DB writes occur.
backend/app.py: POST /api/scrape/download_pages — body: {start_lb?, end_lb?, force?}. Builds a full integer range (1..max_lb by default) and delegates to _start_download_pages_thread(); _start_download_pages_thread() added alongside _start_scrape_thread().
gui/setup_tab.py: Row 4 "Download Missing Pages" button added to the scraper grid. _on_download_pages() handler; _page_download_mode flag on SetupTab. _on_scrape_status() updated to use "Downloading" verb, "already cached" skip text, and "Downloaded LB-X [web]" log lines in download mode; completion message shows downloaded/cached/error counts and refreshes the pages-count label.

---

[2026-05-18] — fix/feat: TODO-006 connection leak, TODO-001 pages count, TODO-016 forum footer

Changed

backend/db.py: Added close_connection(db_path) — closes and evicts the per-thread SQLite handle for a given path. Prevents stale handle being returned for temp_import.db after it is deleted.
backend/importer.py: Calls close_connection(temp_db_path) before both unlink() sites in run_import() so the thread-local pool is clean for subsequent imports. (TODO-006)
backend/paths.py: Added APP_VERSION = "1.0" constant.
backend/forum_poster.py: Replaced hardcoded _FOOTER string with _build_footer() function that reads the WTRF username from the OS keyring via get_credentials(SERVICE_WTRF) and uses APP_VERSION; falls back to "kuddukan" when no credential is stored. (TODO-016)
gui/setup_tab.py: "Use local pages" checkbox now shares a row with a grey count label "(N pages cached)" populated by _refresh_pages_count(), which globs data/pages/*.html. Called from _load_settings(). (TODO-001)

---

[2026-05-18] — fix(gui/db): search tab row colours delayed 5–6 s after first display (BUG-066)

Changed

gui/search_tab.py: Removed self._page = 0 / _render_page() call from _on_xref_loaded(). model.set_xref_map() already emits dataChanged for the Xref column; the full model reset was the cause of the delayed colour paint. Added _prefetch_owned() called at __init__ so the owned set is warm before the first search render.
backend/db.py: Added idx_chk_xref_pos partial index ON checksums(lb_number, xref) WHERE xref>0. Eliminates the full checksums table scan in get_xref_map() that caused the 5–6 s delay.

---

[2026-05-18] — feat(backend/gui): lb_alias + folder_lb_link disambiguation (CC_LB_INTEGRITY item 8)

Added

backend/db.py: lb_alias and folder_lb_link tables added to SCHEMA_SQL. lb_alias added to MASTER_TABLES; folder_lb_link added to USER_TABLES. New helpers: resolve_aliases(), get_folder_link(), set_folder_link(), delete_folder_link(), add_lb_alias(), delete_lb_alias(), get_lb_aliases() — all with type hints and Google-style docstrings.
backend/app.py: 7 new endpoints: GET /api/lb_alias, POST /api/lb_alias (curator-only), DELETE /api/lb_alias/<alias_lb> (curator-only), GET /api/lb_alias/resolve, GET /api/folder_link, PUT /api/folder_link, DELETE /api/folder_link.
gui/rename_tab.py: RenameTab now accepts flask_port parameter. Resolution order on populate_from_lookup: (1) folder_lb_link lookup; (2) lb_alias collapse; (3) fall back to multiple_ids. Right-click: "Link this folder…", "Unlink this folder", "Save as master alias…" (curator-only). _AliasDialog for curator alias creation.
gui/main_window.py: Pass flask_port to RenameTab constructor.
gui/dbedit_tab.py: "LB Aliases" QGroupBox panel. Auto-loads on load_tables(). Add/Delete curator-gated.

[2026-05-18] — feat(backend/gui): Flat-file update check rework (CC_LB_INTEGRITY item 9)

Added

backend/flat_file.py: New pipeline module — discover_flat_file_release, download_flat_file_release,
  diff_flat_file_release, apply_flat_file_release, defer_flat_file_release, get_releases,
  get_release_changelog. Discovers new releases from the LosslessBob download page, downloads
  the zip, diffs against the live checksums table (tab-delimited format matching importer.py),
  and applies changes with a full flat_file_changelog audit trail. Auto-backup before apply.
  Reconciles lb_master for touched LBs post-apply.
backend/db.py: flat_file_releases and flat_file_changelog tables added to SCHEMA_SQL and
  MASTER_TABLES. _bootstrap_flat_file_legacy() for first-run migration.
backend/app.py: 7 new endpoints under /api/flat_file/*.
gui/setup_tab.py: "Check for Flat File Update" button, _UpdateAvailableDialog, Flat File History panel.

Changed

backend/scraper.py: Removed broken check_for_update() which scraped the bynumber page.

[2026-05-18] — feat(gui/backend): Click-to-sort on all major tables (CC_LB_INTEGRITY item 10)

Added

gui/widgets/sort_keys.py: SortableTableItem + sort_key_for() with typed sort keys.
gui/widgets/state_store.py: get_sort()/set_sort() for persistent sort state.
gui/lbdir_tab.py, gui/verify_tab.py: Client-side sort via SortableTableItem.
gui/search_tab.py, gui/collection_tab.py, gui/dbedit_tab.py: In-memory/server-side sort via sectionClicked.
backend/app.py: sort_col/sort_dir params on /api/search, /api/collection, /api/collection/missing.

[2026-05-18] — feat(gui/backend): Override export/import JSON endpoints and DB Editor buttons

Added

backend/db.py: export_overrides() and import_overrides() helpers.
backend/app.py: GET /api/lb_master/overrides/export and POST /api/lb_master/overrides/import.
gui/dbedit_tab.py: "Export Overrides" and "Import Overrides" buttons in DB Integrity panel.

---

[2026-05-18] — feat(db/backend): add location_geocoded schema, Nominatim geocoder, CLI tool

Added

backend/geocoder.py: Nominatim geocoder module. `geocode_one(location_text)` performs a single
  lookup (stdlib urllib only, no extra deps). `place_manual(location_text, lat, lon, note)` inserts
  a manual coordinate with `manual_override=1` so batch runs never overwrite it. `run_batch(limit,
  retry_failed, dry_run)` batch-geocodes all un-geocoded `entries.location` values with a 1.1-second
  sleep between requests (Nominatim ToS). Thread-safe `_progress` dict for future GUI integration.
  `get_progress()` returns a snapshot for polling.

tools/geocode_locations.py: CLI wrapper for `run_batch`. Accepts `--limit N`, `--retry-failed`,
  `--dry-run`. Configures root logging and resolves project root so it can be run directly from the
  project root directory.

Changed

backend/db.py: Added `location_geocoded` table (DDL inside `_SCHEMA`) — columns: location_text
  (PK), lat, lon, source, confidence, display_name, manual_override (DEFAULT 0), note, geocoded_at.
  Index `idx_geo_source` on source column. Table added to `MASTER_TABLES` so it is included in
  master-data export/import. Added `get_map_data(filters, db_path)` — returns `{"markers": [...],
  "unplottable_count": int}` for a future map tab; joins entries, location_geocoded, lb_master, and
  my_collection; supports filters: status, owned, year_min, year_max, q.

---

[2026-05-18] — feat(backend): add /map, /api/map/data, /api/geocode/* routes

Changed

  backend/app.py: add GET /map, GET /api/map/data, POST /api/geocode/run, GET /api/geocode/status, POST /api/geocode/location, GET /api/geocode/locations. Also added send_from_directory to Flask imports.

---

[2026-05-18] — feat(gui): add Map tab with Leaflet world map, marker clusters, heatmap toggle, browser view

Added

  gui/map_tab.py: Map tab widget with QWebEngineView + Open in Browser fallback
  gui/resources/map.html: Leaflet map page with filters, marker clustering, heatmap mode

---

[2026-05-18] — feat(gui/backend): Map tab wired into main window, PyQt6-WebEngine added to requirements

Changed

  gui/main_window.py: register Map tab after ThemeTab via graceful try/except import fallback so the
    app starts normally even when gui/map_tab.py is not yet present in the worktree
  requirements.txt: PyQt6-WebEngine already pinned at 6.7.0; requests already pinned at 2.32.3 — no
    version changes required
  PROJECT.md: document map feature: new files (map_tab.py, map.html, geocoder.py,
    geocode_locations.py), location_geocoded schema, six new API routes (GET /map,
    GET /api/map/data, POST/GET /api/geocode/*), tab count updated to 11

---

[2026-05-19] — docs(backend): add type hints and Google-style docstrings to all app.py route handlers (TODO-004)

Changed

backend/app.py: Added `Response` to module-level Flask imports. Added `-> Flask` return type and one-line docstring to `create_app()`. Added `-> Response` return types to all 67 route handler functions. Added URL path-parameter type hints across all parameterised routes. Added Google-style docstrings to 47 route functions that previously had none; left 20 existing docstrings unchanged. Added docstring and parameter types to `_start_scrape_thread()` and `_do_spectro_batch()` helpers.

[2026-05-17] — fix(gui): Column widths now actually persist across restarts (GuiStateStore root-cause fix)

Fixed

gui/widgets/state_store.py: Two root causes identified and fixed via headless regression test.
  Bug A — Qt fires sectionResized for all columns during initial layout, AFTER _on_resized is
  connected but BEFORE _restore sets _restoring. _on_resized saved the auto-calculated garbage
  widths; _restore then read them back. Fix: set _restoring.add(tid) at the very start of
  attach_table, before any signal or timer is wired.
  Bug B — _migrate_from_qsettings was copying column widths from old QSettings into the new JSON.
  Those QSettings were written by the same buggy _on_resized, so they contained auto-layout garbage
  (e.g. 5340px for "Description"). Fix: skip column-width migration entirely; only geometry is
  safe to migrate. Added 10 <= w <= 3000 sanity guard in get_col_widths as a second line of
  defence against any future garbage reaching the store.
Also cleared garbage from system QSettings (LosslessBob/SearchTab col_widths).

[2026-05-17] — feat(gui): Reliable column width persistence via GuiStateStore (CC_LB_INTEGRITY item 11)

Added

gui/widgets/state_store.py: `GuiStateStore` — single source of truth for persistent GUI widget state. Stores column widths, window geometry in `data/gui_state.json`. Atomic writes (tempfile + os.replace), 500 ms debounced saves, `_restoring` guard to suppress spurious saves during programmatic restore. One-time QSettings migration on first run.

Changed

gui/main_window.py: Removed `QSettings` window geometry; replaced with `state_store.restore_window` / `save_window`. `closeEvent` calls `state_store.flush()` before close. `GuiStateStore` instance created at startup and passed to all tabs with tables.
gui/search_tab.py: Removed `_qsettings`, `_col_widths`, `_widths_applied`, `_resizing_programmatically`, `_load_col_widths`, `_save_col_widths`, `_on_col_resized`, `_set_default_col_widths`, `_apply_col_widths`. Now calls `state_store.attach_table(view, "search.results")`. `_render_page` no longer snapshots/restores widths around model resets.
gui/dbedit_tab.py: Removed `QSettings` and `_SETTINGS_PATH`. `_snapshot_and_save` / `_load_saved_widths` / `_on_col_resized` now use `state_store.get_col_widths` / `set_col_widths` with key `dbedit.<table_name>`.
gui/collection_tab.py: Removed `_coll_col_widths`, `_miss_col_widths`, `_wish_col_widths` in-memory tracking and `_apply_coll_col_widths` / `_apply_miss_col_widths`. All 7 tables (my_collection, missing, wishlist, forum_history, torrent_history, entry_torrents, entry_forum_posts) now use `state_store.attach_table`.
gui/lbdir_tab.py: `summary_table` now uses `state_store.attach_table`; removed `resizeColumnsToContents()` call from `_populate_summary` that clobbered user widths on each check run.
gui/rename_tab.py: Removed hardcoded `setColumnWidth(0, 50)` in `_build_ui`; replaced with `state_store.attach_table`.

[2026-05-17] — feat(gui): Standardize folder name button in Rename tab (CC_LB_INTEGRITY item 13)

Added

backend/folder_naming.py: `build_standard_name(lb_number, date_str, location, lb_status)` — builds canonical `YYYY-MM-DD Location (LB-XXXXX)[-NFT]` folder name. Shared between Rename tab and Collection tab. Imports `_parse_date` lazily from `backend/torrent_maker`.

backend/app.py: `GET /api/folder_naming/standard/<lb>` — returns `{standard_name, lb_status, nft}`. Looks up entry metadata and lb_master status; applies NFT suffix via `build_standard_name`.

gui/rename_tab.py: "Standardize Selected" button — for each checked single-LB row, fetches canonical name via `get_entry()` + `get_lb_status()` + `build_standard_name()`, updates the proposed name, and escalates state to `needs_rename` when the standard name differs from the current folder name. Right-click "Standardize Name (YYYY-MM-DD Location…)" action applies the same transform to a single row.

gui/rename_tab.py: `RenameModel.update_state(idx, state)` — new method to update a row's state and emit `dataChanged` for the full row.

Fixed

gui/rename_tab.py: `_on_strip_wrong_lb()` now calls `update_state(i, "needs_rename")` after updating the proposed name. Previously the state stayed `wrong_lb`, which is not in the rename-eligible set, so stripped rows could never be renamed by the "Rename Selected" button. (BUG-064)

---

[2026-05-17] — feat(gui): lb_status filter + tinting across Lookup, Attachments, Rename, Lbdir tabs (TODO-021)

Changed

backend/db.py: `get_lb_statuses_batch(lb_numbers)` — single batch SELECT from lb_master, returns {lb_number: lb_status} dict for bulk UI colouring. Also stamps lb_status onto each lb_summary dict in lookup_checksums() for the filter combobox.

gui/lookup_tab.py: "All LB statuses / Public only / Private only / Missing only" QComboBox in Summary header row. `_lb_status_filter` + `_sum_lb_statuses` list drive filter guard in `_apply_filters()`. Private → #B3E5FC, Missing → #E0E0E0 row tinting ahead of match-quality colors.

gui/rename_tab.py: LB Found column (col 3) tinted #B3E5FC/E0E0E0 for Private/Missing when no NFT discrepancy is active.

gui/attachments_tab.py: `_render_tree_page()` batch-fetches lb_status for the current page via `get_lb_statuses_batch()`, tints Private parent items light blue and Missing items gray, with tooltip text.

gui/lbdir_tab.py: `_populate_summary()` batch-fetches lb_status and tints the LB# column (col 1) by lb_status; verification-result color still applies to all other columns.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Changed

backend/db.py: lookup_checksums() now also stamps lb_status onto each lb_summary dict (reusing the same _lb_status_map batch query that already annotates detail items).

gui/lookup_tab.py: Added "All LB statuses / Public only / Private only / Missing only" QComboBox to the Summary header row. _lb_status_filter state drives a new guard in _apply_filters() that filters sum_indices by _sum_lb_statuses. _process_result() populates _sum_lb_statuses (parallel to _sum_lb_nums) from s["lb_status"]. Private rows get light-blue (#B3E5FC) and Missing rows get light-gray (#E0E0E0) background overrides ahead of match-quality colors. lb_status stored in sum_user_data per row.

---

[2026-05-17] — feat(integrity): -NFT suffix for Private LB folder names (TODO-018)

Added

backend/folder_naming.py: New module. `apply_nft_suffix(name, lb_status)` appends -NFT when lb_status='private', idempotent, case-normalises existing suffix. `strip_nft_suffix(name)` removes trailing -NFT. `has_nft_suffix(name)` predicate. `nft_discrepancy(folder_name, lb_status)` returns 'missing'|'stale'|'unknown'|None for discrepancy detection.

backend/db.py: `should_mark_nft(lb_number)` returns True when lb_status='private'. `lookup_checksums()` now annotates each detail item with `lb_status` from lb_master via a single batch lookup, making the status available to downstream callers (rename tab, etc.) without extra API calls.

gui/rename_tab.py: Imports `apply_nft_suffix`, `strip_nft_suffix`, `nft_discrepancy` from `backend.folder_naming`. `populate_from_lookup()` builds a `lb_status_map` from detail item annotations, applies NFT suffix to proposed names for Private LBs, proposes stripping -NFT for Public LBs that still have it, and escalates state to `needs_rename` when the proposed name differs from current. Multi-LB rows conservatively inherit `lb_status='private'` if any candidate LB is Private. `RenameModel.data()` overrides BackgroundRole and adds ToolTipRole for NFT discrepancy states (_NFT_DISC_COLORS / _NFT_DISC_TIPS). `_on_strip_wrong_lb()` also applies NFT suffix when rebuilding proposed names. Legend gains three new NFT-discrepancy swatches.

gui/collection_tab.py: `_get_standard_lb_name()` calls `/api/lb_master/<lb>/nft` and appends -NFT to the returned base name when the response is `{nft: true}`.

---

[2026-05-17] — feat(integrity): Re-scrape Private LBs button in Setup tab (TODO-017)

Added

backend/app.py: POST /api/scrape/private_rescrape — queries lb_master for all lb_status='private' rows, starts the scraper with force=True on those lb_numbers, returns {ok, total}. Uses existing _start_scrape_thread so standard /api/scrape/status polling applies.

gui/setup_tab.py: "Re-scrape Private LBs" button added as Row 3 in the Scraper section grid. Clicking it fetches the current private count from /api/lb_master/stats, shows a confirmation dialog with the count, and calls the new endpoint. Uses the existing _ScrapeStatusThread + _on_scrape_status machinery for progress/completion. On completion, fetches updated stats and appends "N promoted to Public, M private remain." to the status message. _on_scrape_all and _on_scrape_range now also disable this button while a scrape is running.

---

[2026-05-17] — feat(db): master/user data ownership split + master publish/install + curator mode (TODO-020)

Added

backend/db.py: MASTER_TABLES, USER_TABLES, MASTER_META_KEYS, USER_META_KEYS, MASTER_SCHEMA_VERSION constants formalise which tables ship in a master release and which stay local. New `is_curator()` / `set_curator()` helpers backed by `meta.is_curator='1'|'0'` (user-local, never shipped). New `export_master_db(reason)` produces a master-only snapshot in `data/exports/` via `VACUUM INTO` → drop every USER_TABLES table → filter `meta` to MASTER_META_KEYS → stamp `master_version` / `master_published_at` / `master_schema_version` → VACUUM → verify (no user tables, no non-master meta keys) → SHA256 → write `<file>.manifest.json` sidecar. New `import_master_db(snapshot_path)` validates the manifest SHA256, refuses incoming schema versions newer than this client, takes a `pre_master_import` backup, ATTACHes the snapshot, copies only MASTER_TABLES, replaces only MASTER_META_KEYS in `meta`, rebuilds the `entries_fts` virtual table, and returns a summary (row counts, pre/post status distribution, backup path).

backend/app.py: GET /api/curator and POST /api/curator endpoints toggle the curator flag (body `{enabled: bool}`). POST /api/master/export requires `is_curator=true` (returns HTTP 403 `error=curator_required` otherwise); returns `{ok, path, manifest_path, manifest}`. POST /api/master/import (body `{path}`) returns the import summary or 400/404 with `error=sha256_mismatch | schema_too_new | not_found`.

gui/setup_tab.py: New "Master Data" QGroupBox below Database. Curator-mode checkbox persists via `/api/curator`. Publish Master Update button (curator-only, gated by checkbox) runs the export and shows a confirmation dialog with version, sha256 prefix, row counts, status distribution, and override count. Install Master Update button opens a file picker (defaults to `data/exports/`) and applies the chosen snapshot with a pre/post status diff in the result dialog. New `_load_curator_status()` called at init reflects the persisted flag in the UI.

tests/test_master_data.py: 13 pytest tests covering the MASTER/USER table constants and disjointness, MASTER_META_KEYS whitelist (no user keys leak), curator-flag round-trip, export-excludes-user-data, SHA256-matches-file-contents, version-stamping, end-to-end import preserves user collection + user meta keys (qbt_*, search_page_size, is_curator) while replacing master tables and master meta keys (import_hash, master_version), SHA-mismatch rejection (ValueError), schema-too-new rejection (RuntimeError), pre-import backup creation, and Flask 403 guard when curator mode is off.

---

[2026-05-16] — feat(integrity): lb_master status system, forum post guard, Search/Collection status columns, DB Editor integrity panel

Changed

backend/db.py: Added lb_master and lb_status_history tables to SCHEMA_SQL. Added backup_database(), migrate_lb_master(), reconcile_lb_status(), reconcile_all_lb_master(), set_lb_manual_override(), clear_lb_manual_override(), get_lb_master_row(), get_lb_master_stats(), get_lb_status(), is_postable_to_forum(), get_lb_master_list(), get_lb_status_history(). search_entries() now LEFT JOINs lb_master to return lb_status on every row. get_collection() and get_missing_from_collection() also return lb_status. migrate_lb_master() is called once from init_db() background thread and deletes entries.status='missing' tombstones after populating lb_master. lb_master.lb_status CHECK constraint enforces 'public'|'private'|'missing'. backup_database() uses VACUUM INTO with microsecond-precision timestamps to avoid filename collisions; keeps last 10 backups.

backend/app.py: Added 9 new endpoints: GET /api/lb_master/stats, GET /api/lb_master/<lb>, GET /api/lb_master, POST /api/lb_master/reconcile, GET /api/lb_master/history/<lb>, PUT /api/lb_master/<lb>/manual, DELETE /api/lb_master/<lb>/manual, GET /api/lb_master/<lb>/nft, POST /api/db/backup. Added forum post guard to preview_forum() and post_forum(): returns HTTP 403 with error=lb_private|lb_missing|status_unknown for non-public LBs.

backend/importer.py: After flat-file merge, calls migrate_lb_master() on first import (lb_master empty) or reconcile_lb_status() for every touched LB on subsequent imports.

backend/scraper.py: Calls reconcile_lb_status() after every scrape_entry() success and 404, wiring the scraper into the lb_master lifecycle.

gui/search_tab.py: Added "Status" column (col 1) to HEADERS. Replaced "Missing only" checkbox with LBStatusComboBox-style QComboBox (All statuses / Public only / Private only / Missing only / Needs review). _filtered_results() uses the status combobox. Background coloring now reads lb_status from result rows (public=default, private=light blue #B3E5FC, missing=light gray #E0E0E0).

gui/collection_tab.py: Added "Status" column (col 1) to COLL_HEADERS and MISS_HEADERS. _CollectionModel.data() and _MissingModel.data() display lb_status and apply matching background colors. _on_post_forum() adds a hard blocking modal dialog for private/missing LBs before attempting any network call. _on_post_forum_done() surfaces backend 403 forum-guard errors with the same modal (handles stale-status race).

gui/dbedit_tab.py: Added "DB Integrity" QGroupBox to the left panel with: live stats label (Public/Private/Missing/Max/Overrides/Needs Review), Reconcile All button (→ POST /api/lb_master/reconcile with confirmation), Show Needs Review button (selects lb_master + applies needs_review:1 search), Backup DB Now button (→ POST /api/db/backup with result dialog). load_tables() now also calls load_integrity_stats().

Added

tests/test_lb_master.py: 27 pytest tests covering schema creation, migrate_lb_master idempotency and status precedence, reconcile_lb_status transitions and override respect, stats counts, importer integration, is_postable_to_forum logic, Flask forum endpoint guard (HTTP 403 for private/missing), and GUI column/widget presence checks (skipped without DISPLAY).

[2026-05-16] — fix(gui): crash on theme apply due to non-existent self.table reference

Fixed

gui/collection_tab.py: resize_columns_to_font() referenced self.table, which only exists on the unrelated _ScanPreviewDialog class — not on CollectionTab. Caused AttributeError on every theme/font change and aborted the app. Removed the stray block; the other view/table resizes were already covering CollectionTab's real widgets.

---

[2026-05-16] — feat(gui): resize table columns to fit whenever font size changes

Added

gui/search_tab.py: resize_columns_to_font() — calls resizeColumnsToContents() on the search results view.
gui/collection_tab.py: resize_columns_to_font(font_size) — resizeColumnsToContents() on coll/miss/wish views and the LB lib table; scales torrent_history_table and forum_posts_table hardcoded pixel widths by font_size/9.
gui/dbedit_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the data table.
gui/lookup_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail views.
gui/rename_tab.py: resize_columns_to_font() — resizeColumnsToContents() on the rename view.
gui/verify_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/lbdir_tab.py: resize_columns_to_font() — resizeColumnsToContents() on summary and detail tables.
gui/main_window.py: _on_theme_applied() now reads the current font size from theme_tab and calls resize_columns_to_font() on every tab after applying the stylesheet.

---

[2026-05-16] — feat(dbedit): add LB# search field to DB Editor toolbar

Added

gui/dbedit_tab.py: "LB#:" label + lb_input QLineEdit (width 80px) added to the toolbar between "Load Records" and the text search field. Pressing Enter in the field triggers the search; the field is cleared on table switch and "Load Records".
backend/app.py: dbedit_rows now accepts an optional lb_number query param; when the table has an lb_number column and the value is a valid integer, it appends AND lb_number = ? to the WHERE clause (combinable with the existing text search).

---

[2026-05-16] — feat(gui): add font family and font size controls to the Themes tab

Added

gui/styles.py: build_stylesheet() and apply_theme() now accept font_family and font_size keyword args; the chosen font is prepended to the platform stack and the size replaces the hardcoded 9pt.
gui/theme_tab.py: Font row (QComboBox + QSpinBox) inserted in _build_ui() below the colour swatches; _on_apply(), _save_settings(), and load_and_apply_saved() wired to read, persist, and restore font settings via QSettings keys theme/font_family and theme/font_size.

Changed

gui/search_tab.py: _prev_btn / _next_btn setFixedWidth(80) → setMinimumWidth(80) so buttons expand at larger font sizes.
gui/collection_tab.py: _coll_prev_btn / _coll_next_btn setFixedWidth(80) → setMinimumWidth(80).
gui/dbedit_tab.py: prev_btn / next_btn setFixedWidth(70) → setMinimumWidth(70).

---

[2026-05-16] — fix(db): searching a bare integer now always returns the matching lb_number entry

Fixed

backend/db.py: After the FTS5 search in search_entries, if the query is a bare integer and the matching lb_number is not already in the FTS results, a direct lb_number lookup is performed and the matching entry is prepended. Fixes entries like LB-01797 (Paris, 7/6/78) that have a webpage and metadata but no text fields containing their own lb_number, making them invisible to numeric search queries.

---

[2026-05-16] — fix(db): redefine "missing" as entries with no webpage, not entries with no checksums

Fixed

backend/db.py: get_missing_lb_numbers now queries entries.status instead of the checksums table. An entry is missing only when status='missing' (scraper confirmed no page) or the lb_number was never scraped. Entries with status='ok' are real entries and are never returned as missing even if they have no checksums or attachments (e.g. LB-12404). Previously the function returned any lb_number in range 1..max_lb absent from the checksums table, which incorrectly included hundreds of real entries that simply have no downloadable content.

---

[2026-05-16] — fix(attachments): tree page change glitches — viewport not reset after clear

Fixed

gui/attachments_tab.py: _render_tree_page now calls scrollToTop() after populating the new page so the viewport always lands at the top. Also wrapped clear+populate in setUpdatesEnabled(False/True) to suppress incremental repaints during the bulk insert, eliminating visual tearing.

---

[2026-05-16] — feat(attachments): paginate cached LB tree to 1000 entries per page with prev/next buttons

Added

gui/attachments_tab.py: Added PAGE_SIZE = 1000 class constant and _page / _all_lb_dirs state. Split _refresh_tree into a collector phase (builds sorted list of non-empty LB dirs) and _render_tree_page (populates tree for the current page slice). Added ◀ Prev / page label / Next ▶ navigation row that auto-shows in cached view and hides in missing view. _jump_to_lb now calculates the target page from _all_lb_dirs and navigates there before scrolling. Buttons are disabled when at the first or last page.

---

[2026-05-16] — fix(attachments): move WebEngine warmup to app startup instead of first tab visit

Fixed

gui/attachments_tab.py: QWebEngineView initialization (and about:blank warmup) now scheduled via QTimer.singleShot(0) in __init__ so it fires on the first event-loop tick after the main window appears — while the user is still on the Lookup tab — rather than on the first Attachments tab visit. Removed _web_initialised flag and the lazy-init block from showEvent. Added early-return guard in _init_web_view to prevent double-init. Removed the fallback _init_web_view() call from _open_lb_in_webview since the view is always ready by the time the user can interact.

---

[2026-05-16] — fix(main): disable Chromium GPU process to fix full-window blackout and GBM format errors on Linux

Fixed

main.py: Added --disable-gpu to QTWEBENGINE_CHROMIUM_FLAGS. Chromium's GPU process was hijacking the shared OpenGL context (AA_ShareOpenGLContexts) on Qt 6.7/XWayland, causing the entire application window to flash black. --disable-gpu prevents the GPU process from starting; Chromium uses Swiftshader software rendering instead, which is sufficient for the simple pages this app displays. Also eliminates the spurious "Unknown or not supported format: 808530000" (P010 GBM probe) stderr errors.

---

[2026-05-16] — fix(attachments): warm up WebEngine GPU process on tab open to prevent first-load window flash

Fixed

gui/attachments_tab.py: Loading about:blank immediately after QWebEngineView is added to the stack during _init_web_view. This forces the GPU/renderer subprocess to start while the tab is quietly initialising rather than on the first user-triggered URL load, eliminating the native-window flash on Linux.

---

[2026-05-16] — feat(attachments): right-click "Open in browser pane" on tree and missing list

Added

gui/attachments_tab.py: Right-click context menu on both the cached tree and the missing list shows "Open LB-NNNNN in browser pane". Selecting it loads the DETAIL_URL for that entry directly into the embedded QWebEngineView (right panel) instead of opening an external browser. DETAIL_URL imported from backend.scraper; QUrl moved to top-level import and removed from inline lazy import in _preview_file.

---

[2026-05-16] — feat(attachments): Missing LB list with scrape capability

Added

backend/db.py: get_missing_lb_numbers() — returns list of integers in range 1..max_lb absent from the checksums table.
backend/app.py: GET /api/db/missing_lb_numbers route backed by get_missing_lb_numbers().
gui/attachments_tab.py: _MissingThread fetches missing list from backend. Left panel now has Cached/Missing toggle buttons that swap a QStackedWidget between the existing tree and a new QListWidget. Jump-to search box works in both views. "Scrape Selected Entry" button in Missing view calls the same _ScrapeThread; on success the entry is removed from the missing list and the cached tree is marked stale. "No attachments found" status confirms true gaps.

---

[2026-05-16] — fix(gui): xref checkbox — search adds Xref column; collection filters on owned xref folders only

Changed

gui/search_tab.py: Added "Xref" column (col 5) to the search results table showing which xref numbers exist for each entry. _XrefWorker now calls GET /api/checksums/xref_map (returns {lb: [xref_values]}) instead of the bare LB list; SearchModel gains _xref_map and set_xref_map(); _on_xref_loaded converts string JSON keys to ints and pushes the map to the model.

gui/collection_tab.py: "Xref only" checkbox now filters to collection entries where the folder_name contains "xref" (i.e., the user has an xref-named folder in their collection). Previously it filtered on whether the LB exists in the master DB xref list, which was wrong — it showed any LB that has xref variants, not specifically the entries the user collected as xref folders.

backend/db.py: Added get_xref_map() — returns {lb_number: [xref_val, ...]} for all lb_numbers with xref checksums.

backend/app.py: Added GET /api/checksums/xref_map route backed by get_xref_map().

---

[2026-05-16] — feat(gui): attachments tab layout overhaul — wider tree, stat label moved, LB jump-to search box

Changed

gui/attachments_tab.py: Moved the "Entries with cached files" stat label into the left panel (above the tree) so it no longer floats in dead space. Splitter initial sizes changed from 300/700 to 420/580 to give the tree more room. Outer VBoxLayout now uses stretch=1 on the splitter so it fills the full widget height. Added QLineEdit + "Go" button at the bottom of the left panel to jump the tree selection to a typed LB number (accepts plain digits, "LB-NNNNN", or "LBNNNNN").

---

[2026-05-16] — feat(gui): add Forum History and Torrent History tabs to My Collection

Added

gui/collection_tab.py: Two new inner tabs ("Forum History" and "Torrent History") beside Duplicates. Each shows a global, all-entry table loaded lazily on first activation with a Refresh button. Forum History shows LB#, Date, Location, Posted timestamp, Subject with Open in Browser and Remove Record actions and a right-click context menu. Torrent History shows LB#, Date, Location, Created timestamp, Source Folder, Added to qBt status. Right-click on either table offers "Go to LB-XXXXX in My Collection" navigation.

backend/db.py: Added get_all_forum_posts() and get_all_torrents() — full-table queries joined with entries for date_str and location.

backend/app.py: Added GET /api/forum_posts and GET /api/torrents routes.

---

[2026-05-16] — feat(gui): add hover highlight to tab bar tabs

Added

gui/styles.py: Added `QTabBar::tab:hover` rule that blends `tab_bg` halfway toward `tab_selected` using the existing `_blend_hex()` helper, giving a subtle visual cue as the mouse moves over inactive tabs without affecting the selected tab's appearance.

---

[2026-05-16] — fix(gui): button text color now auto-contrasts against accent instead of using header_fg

Fixed

gui/styles.py: `QPushButton` text was hardcoded to `{t['header_fg']}` (Table Header Text), which had no logical connection to buttons and gave wrong results on many themes. Added `_button_text_color()` which picks black or white based on the accent's luminance — the same approach the theme swatch labels use. Each button state (normal, hover, pressed) now gets its own computed text color.

---

[2026-05-16] — fix(gui): disabled buttons now match the active theme instead of rendering as hardcoded gray

Fixed

gui/styles.py: `QPushButton:disabled` was hardcoded to `#A0A0A0` / `#E0E0E0` regardless of theme. On dark themes like Tokyo Night the gray buttons clashed visually with the dark background. Added `_blend_hex()` helper and replaced the hardcoded values with theme-derived colors (accent blended 65% toward app_bg for background, app_fg blended 55% toward app_bg for text).

---

[2026-05-16] — feat(gui): move theme swatches to left side and split into 2-column grid

Changed

gui/theme_tab.py: Restructured `_build_ui` so the swatch panel sits immediately right of the preset list (no right-side expansion). The `QGridLayout` now uses 4 columns (label-A | swatch-A | label-B | swatch-B), distributing the 22 color entries across 11 rows × 2 columns. Added `layout.addStretch()` at the end so the panels stay left-anchored.

---

[2026-05-16] — fix(gui): search tab column widths no longer reset to 100px on every launch

Fixed

gui/search_tab.py: Added `_widths_applied` flag to guard the pre-reset snapshot in `_render_page()`. The snapshot was executing before `_apply_col_widths()` had ever run, so Qt's 100px default widths overwrote the values loaded from QSettings, destroying saved preferences. The snapshot is now skipped until widths have been applied at least once.

---

[2026-05-16] — fix(scraper): use correct SMF form field name "description" instead of "desc"

Fixed

backend/forum_poster.py: Changed "desc": lb_id to "description": lb_id in both the initial POST payload and the retry payload. The SMF modify/post form uses name="description" (confirmed from live page source); the previous key "desc" was silently ignored by the server, so the LB number never appeared in the topic description field. Updated debug log line to match.

---

[2026-05-16] — feat(gui): add 7 new preset themes (Nord, Gruvbox, Monokai, Tokyo Night, Solarized, Everforest, Catppuccin)

Added

gui/theme_tab.py: Nord (Arctic blue-gray), Gruvbox (earthy retro dark), Monokai (vivid dark with cyan accents), Tokyo Night (neon city dark), Solarized (precision warm light), Everforest (forest dark-green), Catppuccin Mocha (soft pastel dark). All 14 row-color keys verified for luminance contrast against each theme's table background. Preset list now shows 14 named themes plus Custom.

Changed

PROJECT.md: Updated Theme Tab description from "Six preset themes" to fourteen.

---

[2026-05-15] — fix(gui): search-tab "missing" row hardcoded yellow; dark-theme row luma audit

Fixed

gui/search_tab.py: Hardcoded QColor("#FFFF99") for status=="missing" rows didn't respect the active theme. Added module-level `import gui.styles as styles`; replaced hardcoded color with `styles.ROW_MISSING` and replaced lazy per-call `from gui.styles import ROW_OWNED` with `styles.ROW_OWNED`. "Row: Missing" in the theme editor now controls search-tab missing-entry rows.
gui/theme_tab.py: Audited all dark-theme row colors for luminance contrast against their table backgrounds. Fixed Dark (row_missing/row_xref/row_owned/row_wishlist all had luma at or below table_bg=58), Black (row_xref luma=20 identical to table_bg; row_missing/row_wishlist below table_alt=28), and Dracula (row_xref/row_missing/row_wishlist at or below table_bg=43). Also fixed Red theme row_xref. Removed unused QApplication import.

---

[2026-05-15] — feat(lbdir): Remove Extra Files — delete disk files not listed in the lbdir, with confirmation dialog

Added

backend/checksum_utils.py: Added find_extra_files(folder_path, lbdir_path) — parses lbdir MD5 section, scans folder recursively, returns files not in the expected set (lbdir file itself excluded).
backend/app.py: Added POST /api/lbdir/find_extra (list extra files per folder) and POST /api/lbdir/delete_extra (unlink selected files by relative path, then prune empty subdirectories).
gui/lbdir_tab.py: Added _LbdirFindExtraWorker and _LbdirDeleteExtraWorker workers. Added ExtraFilesDialog — checkable file list with red delete button and warning label; never deletes without explicit user confirmation. Added "Remove Extra Files" button; handlers re-run Check lbdir Files after deletion.

---

[2026-05-15] — fix(gui): dark-theme row colors always showed light-theme green/purple; add Red theme

Fixed

gui/collection_tab.py: `from gui.styles import ROW_OWNED, ROW_WISHLIST` captured the values at import time; reassignment inside apply_theme() never propagated. Replaced with `import gui.styles as styles` and updated both usages to `styles.ROW_OWNED` / `styles.ROW_WISHLIST`.
gui/lookup_tab.py: Same stale-import bug for ROW_MATCHED/ROW_NOT_FOUND/ROW_MISSING/ROW_DUPLICATE/ROW_XREF. Replaced top-level `from gui.styles import …` with `import gui.styles as styles`; updated all 10 bare references to `styles.ROW_*`; removed redundant lazy `from gui import styles` inside refresh_colors().
gui/styles.py: apply_theme() now updates ROW_WISHLIST global (was never updated on theme switch). Added row_wishlist to the default apply_theme call at module load.
gui/theme_tab.py: Added row_owned and row_wishlist to every theme with dark-appropriate colors for Dark/Black/Dracula. Added both to COLOR_LABELS so they appear in the theme editor.

Added

gui/theme_tab.py: New "Red" dark theme — crimson/dark-red palette with dark-appropriate row colors.

---

[2026-05-15] — fix(gui): suppress GBM "Unknown format" stderr noise from Chromium GPU process

Fixed

main.py: Added --disable-features=VaapiVideoDecoder to QTWEBENGINE_CHROMIUM_FLAGS so Chromium's GPU process no longer probes unsupported hardware video-decode pixel formats (P010/HDR) via GBM, eliminating repeated "Unknown or not supported format: 808530000" stderr errors on Linux.

---

[2026-05-15] — feat(lbdir): Reconcile Files — match missing lbdir entries to disk files by MD5 and propose renames

Added

backend/checksum_utils.py: Added find_reconcilable_files(folder_path, lbdir_path) — parses lbdir MD5 section, identifies entries not on disk, scans all disk files recursively for MD5 matches, returns proposals/unmatched_lbdir/unmatched_disk/warnings.
backend/app.py: Extracted _find_lbdir_in_folder() module-level helper (DRY refactor of lbdir_check and lbdir_retrieve inline lbdir detection). Added POST /api/lbdir/reconcile (preview, read-only) and POST /api/lbdir/apply_reconcile (shutil.move renames, creates subdirs, never deletes).
gui/lbdir_tab.py: Added _LbdirReconcileWorker and _LbdirApplyReconcileWorker QThread workers. Added ReconcilePreviewDialog (checkable table of From→To proposals, Select All/Deselect All, Apply Selected/Cancel). Added "Reconcile Files" button; _on_reconcile, _on_reconcile_done, _apply_reconcile, _on_apply_reconcile_done handlers; re-runs Check lbdir Files after apply.

---

[2026-05-15] — fix(backend): _parse_date swapped month/day — forum post subjects used YYYY-DD-MM instead of YYYY-MM-DD

Fixed

backend/torrent_maker.py: _parse_date was treating parts[0] as day and parts[1] as month (D/M/YY, European), but LosslessBob stores dates in M/D/YY (US) format. Swapped variable assignment so month=parts[0], day=parts[1]. Updated docstring. All subject lines generated from _parse_date (forum posts and torrent names) now produce correctly ordered ISO dates.

---

[2026-05-15] — feat(gui): "Best match only" checkbox in Lookup summary — hides secondary DUPLICATE/INCOMPLETE rows when a full MATCHED result exists

Added

gui/lookup_tab.py: Added "Best match only" QCheckBox (default checked) to the Summary header row. When enabled and at least one summary row is MATCHED, _apply_filters() suppresses all non-MATCHED summary rows and their corresponding detail rows. Unchecking restores the full view. Toggle is instant with no re-lookup required.

---

[2026-05-15] — fix(main): force XWayland (xcb) on Linux to prevent fatal Wayland EGL crash

Fixed

main.py: Set QT_QPA_PLATFORM=xcb before QApplication construction on Linux when not already overridden. Native Wayland + AA_ShareOpenGLContexts + QtWebEngine can produce an unrecoverable EGL_BAD_NATIVE_WINDOW (0x300d) error that kills the Wayland connection (BUG-053). XWayland is stable for this workload with no functional loss.

---

[2026-05-15] — fix(gui): suppress Chromium stderr noise and fix WebEngine profile teardown-order warning on exit

Fixed

main.py: Set QTWEBENGINE_CHROMIUM_FLAGS=--disable-logging before QApplication is created to silence Chromium sandbox and path-override diagnostics that bypass Python logging.
gui/attachments_tab.py: Removed Qt parent from QWebEngineProfile so its lifetime is not tied to the tab's child list. Connected QApplication.aboutToQuit to new _cleanup_webengine() which uses sip.delete() to force destruction order view → page → profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning (BUG-026 reopened and re-fixed).

---

[2026-05-15] — fix(backend): summary row for superseded duplicate LB shows DUPLICATE (yellow) not INCOMPLETE (pink)

Fixed

backend/db.py: After building the per-LB summary, any LB where every matched detail item is still a duplicate (none promoted by resolution) now gets status "DUPLICATE" instead of "INCOMPLETE". This prevents a secondary LB that shares some checksums with the winning LB from appearing as if the user is missing files — it is correctly shown as a yellow duplicate entry alongside the green MATCHED winner.

---

[2026-05-15] — fix(backend): xref lookup completeness — evaluate per (lb, xref) group so full xref match shows MATCHED not INCOMPLETE

Fixed

backend/db.py: lookup_checksums reverse lookup now tracks matched checksums per (lb_number, xref_value) group and queries completeness against that specific xref group (`WHERE lb_number=? AND xref=?`) instead of the whole primary set (`AND xref=0`). A recording that provides all checksums for xref variant N is now correctly shown as MATCHED (green). The summary missing_from_set count is aggregated across all xref groups that had matched items.

---

[2026-05-15] — feat(backend): populate SMF Description field with LB number when posting to forum

Added

backend/forum_poster.py: `lb_id` is now computed unconditionally before the subject branch; `"desc": lb_id` added to both the initial payload and the retry payload so the SMF topic Description (Optional) field is populated with e.g. "LB-10002".

---

[2026-05-15] — fix(backend): lbdir xref file detection — match 'lbdir' anywhere in filename, not just at start

Fixed

backend/app.py: lbdir_check and lbdir_retrieve._find_lbdir now use `'lbdir' in f.name.lower()` instead of `startswith('lbdir')` so xref lbdir files named LBF-XXXXX-xref-NNNN-lbdir.txt are correctly found in both local folders and the attachment cache.

---

[2026-05-15] — feat(backend/gui): torrent history context menu — Remove from qBittorrent + Delete .torrent file from disk

Added

backend/qbittorrent.py: remove_torrent() — calls POST /api/v2/torrents/delete with deleteFiles=false so only the qBt entry is removed; audio files on disk are untouched.
backend/app.py: POST /api/torrent/<id>/qbt_remove — removes from qBt via infohash, clears added_to_qbt in DB on success. DELETE /api/torrent/<id>/file — deletes the .torrent file from disk, clears torrent_path in DB.
gui/collection_tab.py: Added separator + two new context menu actions to torrent history: "Remove from qBittorrent" (disabled when no infohash stored) and "Delete .torrent File from Disk" (disabled when file doesn't exist). Both show a confirmation dialog, refresh the history panel on completion, and update the status label.

---

[2026-05-15] — feat(backend/gui): log forum posts to DB; consolidated History panel with Torrents + Forum Posts tabs; LB detail hyperlink in post header

Added

backend/db.py: forum_posts table (lb_number, subject, topic_url, board_id, posted_at). Added add_forum_post(), get_forum_posts_for_lb(), delete_forum_post() functions.
backend/app.py: post_forum route now calls database.add_forum_post() on success. Added GET /api/entry/<lb>/forum_posts and DELETE /api/forum_post/<id> routes.
backend/forum_poster.py: LB-XXXXX tag in post header is now a [url=...] hyperlink to the LB detail page on losslessbob.wonderingwhattochoose.com.
gui/collection_tab.py: Replaced separate Torrent History and Forum Post History group boxes with a single "History" QGroupBox containing a QTabWidget (Torrents tab + Forum Posts tab). Forum Posts tab shows posted date, subject, URL with Open in Browser and Remove Record buttons. After a successful post the tab switches to Forum Posts automatically. Removed unused QSplitter import.

---

[2026-05-15] — feat(gui): My Collection context menu now has "Generate Spectrograms" action that sends selected folders to the Spectrograms tab

Added

gui/collection_tab.py: Added `send_to_spectrograms = pyqtSignal(list)` signal; added "Generate Spectrograms" action to `_on_coll_context` — visible only when one or more selected rows have a valid `disk_path` directory. Emits the list of paths.

gui/main_window.py: Connected `collection_tab.send_to_spectrograms` to `_on_send_to_spectrograms` which calls `spectrogram_tab._add_folders(folders)` then switches to the Spectrograms tab.

---

[2026-05-15] — fix(backend): forum poster comprehensive reliability overhaul — correct POST URL, hidden-element guards, Firefox UA, board-redirect success on both paths

Changed

backend/forum_poster.py: (1) Removed _post_url() — was hardcoding action=post;sa=post2 which is the wrong SMF handler; the form's own action= attribute is now the authoritative POST URL. _scrape_form_fields() now returns (fields, form_action, diag) and _find_post_form() extracts the action URL directly. (2) post_lb_topic() now posts with allow_redirects=False so the raw Location header can be inspected before following any redirect. (3) Board-redirect success detection: SMF on this forum signals a successful new topic with a 302 → board=N.0 redirect (not topic=), so both the initial post and the retry path now detect this, follow the board URL sorted by first_post desc, and call _find_newest_topic() to return the correct topic link. (4) Lock-warning check now calls _is_element_hidden() before treating #lock_warning as a real warning — the element is present (display:none) on every compose page and was incorrectly firing the retry path on every failed post. (5) _extract_smf_error() now skips hidden elements for the same reason — the empty errorbox present on every compose page was generating phantom SMF error strings. (6) Removed not_approved from payload — not a real SMF field. (7) User-Agent updated to a current Firefox/126.0 string to avoid UA-based blocking.

---

[2026-05-15] — fix(gui): torrent history section no longer expands to fill space; collection table now stretches correctly

Changed

gui/collection_tab.py: Added stretch=1 to the coll_view addWidget call so the collection table claims all available vertical space, keeping the Torrent History group compact at the bottom.

---

[2026-05-15] — feat(gui): Post to Forum auto-creates torrent and adds to qBittorrent if none exists

Changed

gui/collection_tab.py: _on_post_forum now checks for an existing torrent file before building the preview. If none is found it calls /api/torrent/create (using the collection row's disk_path as source_folder), then /api/qbt/add to seed it, then proceeds with the normal preview → confirm → post workflow. If creation fails the error is surfaced in the status bar. qBittorrent add failures are non-fatal — the post proceeds regardless.

---

[2026-05-15] — fix(backend/gui): wrong topic URL in success popup; torrent history stale after auto-create

Fixed

backend/forum_poster.py: _find_newest_topic now uses a three-pass strategy: (1) subject-text match — finds the link whose visible text contains the posted subject, immune to sticky ordering; (2) first non-sticky link — skips <tr>/<div>/<li> ancestors whose class includes "sticky"; (3) last resort, first topic= link found. Subject is now threaded through from post_lb_topic into both the initial-post and retry board-redirect paths.
gui/collection_tab.py: Added _history_gen counter to _load_torrent_history/_populate_torrent_history so stale API responses (earlier load completing after a newer one) are discarded instead of overwriting fresh data. _on_preview_forum_ready now triggers a history refresh so a torrent auto-created during forum-post pre-flight appears immediately without requiring a re-selection.

---

[2026-05-15] — fix(backend): post-success topic URL wrong — board page returns busiest thread, not newest

Fixed

backend/forum_poster.py: _find_newest_topic was picking the first topic= link on the board listing page, which is sorted by last-reply date by default. A busy thread bumped after our post appeared first, returning the wrong URL. Added _board_url_sorted() which appends sort=first_post;desc=1 to the board redirect URL before fetching it, ensuring our newly created topic is always at the top. Applied to both the first POST and retry code paths.

---

[2026-05-15] — fix(backend): forum post line breaks stripped; redesign header with size/hr/red LB number, remove broken spoiler tag, normalise CRLF

Changed

backend/forum_poster.py: (1) Normalise body to \r\n before placing it in the multipart/form-data payload — bare \n is silently stripped by SMF when the request is multipart-encoded due to a file attachment. Applied to both first POST and retry payload. (2) Metadata header now wrapped in [size=13pt] for visibility, LB number appended in [color=red][b]...[/b][/color], followed by [hr] on the next line. (3) Replaced non-working [spoiler=Checksums] with plain [b]Checksums[/b] + [code] block. (4) Footer separated by [hr] above it.

---

[2026-05-15] — feat(backend): redesign forum post body format with structured header, LB txt content, spoilered lbdir checksums, and footer attribution

Changed

backend/forum_poster.py: Replaced the raw-file-dump approach in _build_body with a structured BBcode format. New format: (1) bold labeled metadata header (Date | Location | CDR | Rating | Timing) from entry dict; (2) content from the LB-numbered txt file in the attachment dir (first header line skipped), falling back to entry.description; (3) lbdir checksum manifest in a [spoiler=Checksums][code] block at the end; (4) italicised grey "Brought to you by kuddukan, via the Bob-O-Matic v1.0." footer. Added _read_lb_txt and _read_lbdir helper functions. Updated preview_lb_topic and post_lb_topic to pass lb_number into _build_body.

---

[2026-05-14] — fix(backend): retry payload overrode lock=0, re-introducing the warning it was meant to clear

Fixed

backend/forum_poster.py: The warning page returned by SMF includes lock=1 (server-corrected to match the board's requirement). The retry payload was explicitly overriding lock=0, reintroducing the mismatch that caused the warning on the first POST and making the retry fail identically. Removed lock/sticky/move overrides from the retry payload so the warning page's corrected values pass through. Also removed them from the first POST payload where they were pointless.

---

[2026-05-14] — fix(backend): SMF board lock warning requires confirmation resubmit — add automatic retry

Fixed

backend/forum_poster.py: Board 16 is configured for admin/mod-only posting, so SMF always returns a "warning preview" page asking for confirmation instead of creating the topic immediately. The attachment is already temp-stored server-side at this point. Added lock-warning detection: re-scrapes fresh hidden fields (new seqnum/CSRF) from the warning page and resubmits without the file on a second POST.

---

[2026-05-14] — fix(backend): admin compose page sets lock=1, causing SMF to bounce post with a lock warning

Fixed

backend/forum_poster.py: Admin users' compose pages have lock=1 pre-set as a hidden field. SMF treats this as a locked-topic flag and returns the form with a warning instead of creating the topic. Override lock, sticky, and move to 0 in the payload so admin-default hidden values don't affect the new topic.

---

[2026-05-14] — fix(backend): board ID missing from POST URL — SMF rejected every post as "board doesn't exist"

Fixed

backend/forum_poster.py: _POST_URL was a static constant without a board parameter. SMF requires the board in the POST URL (action=post;sa=post2;board=N.0) just as it does in the compose URL. Replaced _POST_URL with _post_url(board_id) that mirrors _compose_url(board_id).

---

[2026-05-14] — fix(backend/gui): hardcoded forum board ID replaced with configurable setting

Changed

backend/forum_poster.py: Removed FORUM_BOARD=16 constant and module-level _COMPOSE_URL. post_lb_topic() now accepts board_id: int and builds the compose URL dynamically. _scrape_form_fields() accepts compose_url as a parameter.
backend/app.py: wtrf_board_id added to /api/db/settings GET key list. post_forum route reads board_id from meta and returns a clear error if unset.
gui/setup_tab.py: Board ID QSpinBox added to WTRF section (row 2). Saved via _on_wtrf_board_changed on change; loaded in _load_wtrf_settings from /api/db/settings.

---

[2026-05-14] — feat(main): write app module logs to data/losslessbob.log (rotating, 5 MB × 3)

Added

main.py: _configure_logging() installs a RotatingFileHandler on data/losslessbob.log. Root logger stays at WARNING (keeps urllib3/requests/werkzeug quiet); backend.* and gui.* namespaces are set to DEBUG so all our module logging lands in the file.

Added

main.py: _configure_logging() sets up a RotatingFileHandler on data/losslessbob.log (DEBUG level, 5 MB × 3 backups) and a stderr StreamHandler (WARNING+). Called at startup before Flask thread starts so all backend modules log to file from the first request.

---

[2026-05-14] — fix(backend): forum post reports false success — SMF rejects submission silently

Fixed

backend/forum_poster.py: post_lb_topic() was reporting success on any HTTP 200 response, but SMF returns 200 when it bounces the post back to the compose form (e.g. CSRF failure, attachment rejection). Fixed success detection to require 'topic=' in the final URL (the redirect SMF sends only on a real post). Added Referer and Origin headers to the POST request so SMF's CSRF check passes. Added additional_options=1 to the payload so SMF processes the attachment field. Improved error reporting: collects errorbox/error_list/post_error div text, and returns the page title + URL as fallback so the failure reason is always visible.

---

[2026-05-14] — fix(backend): forum post blocked by hardcoded 'sc' field check — WTRF uses hashed CSRF token name

Fixed

backend/forum_poster.py: WTRF's SMF install uses a dynamically-hashed field name for the CSRF token (e.g. 'a9c55b28') instead of the literal 'sc'. Removed the 'sc' presence check; seqnum alone is used to confirm the post form was found. All hidden fields including the hashed token were already forwarded via **hidden, so the post itself was correct. Also added diagnostic output to the error message and improved form-field scraping to target the post form specifically.

---

[2026-05-14] — fix(backend): forum post fails with "sc/seqnum missing" — compose page redirect not detected

Fixed

backend/forum_poster.py: _scrape_form_fields now detects when SMF silently redirects the compose URL to the login page (unauthenticated session) and returns empty instead of scraping login-form fields. Added targeted post-form lookup by action attribute so unrelated hidden inputs on the page don't pollute the result. Added Referer header to the compose-page request. Validation now reports exactly which fields are absent (sc vs seqnum).

---

[2026-05-14] — fix(gui): torrent history panel now refreshes after torrent creation

Fixed

gui/collection_tab.py: _on_torrent_done() never called _load_torrent_history(), so the history panel stayed empty after creating a torrent until the user re-selected the entry. Now reloads history for the currently-displayed LB after a successful create.

---

[2026-05-14] — fix(scraper): fetch tracker list from raw GitHub instead of jsDelivr CDN

Fixed

backend/torrent_maker.py: jsDelivr caches GitHub content and can lag by hours/days. Switched _TRACKER_CDN to raw.githubusercontent.com so the tracker list is always current. Also removed unused json import.

---

[2026-05-14] — fix(backend): handle qBittorrent 5 JSON response for torrents/add

Fixed

backend/qbittorrent.py: qBittorrent 5+ returns a JSON object from /api/v2/torrents/add instead of plain "Ok.". Added a JSON fallback check (failure_count==0 and success_count>0) so successful adds are no longer reported as failures.

---

[2026-05-14] — feat: qBittorrent API key authentication (qBittorrent 5+)

Added

backend/credentials.py: SERVICE_QBT_KEY constant for keyring storage of the API key.
backend/qbittorrent.py: api_key parameter on test_connection(), add_torrent_for_seeding(), and add_torrent_from_db(). When set, a Bearer token header is used and the login/logout flow is skipped entirely. Refactored shared session setup into _make_session() and login logic into _login().
backend/app.py: /api/qbt/test and /api/qbt/add routes now retrieve and forward the stored API key; api_key takes priority over username/password.
gui/setup_tab.py: API Key field added to the qBittorrent section (row 2, password-masked, spanning full width). Save/Clear/Test/Load handlers all updated to prefer the API key when filled.

---

[2026-05-14] — fix(backend): add Origin+Referer headers to qBittorrent login, improve error detail

Fixed

backend/qbittorrent.py: Added both Referer and Origin headers to test_connection() and add_torrent_for_seeding(). Fixed login check to accept HTTP 204 No Content (qBittorrent's response when "Bypass authentication for clients on localhost" is enabled) alongside the normal 200 "Ok." response. Error message now includes HTTP status code and shows "<empty>" for blank bodies.

---

[2026-05-14] — feat(gui/backend): Forum post preview dialog before submitting to WTRF

Added

backend/forum_poster.py: preview_lb_topic() builds subject + body without logging in or posting.
backend/app.py: GET /api/entry/<lb>/preview_forum returns {subject, body} for the GUI to display.
gui/collection_tab.py: "Post to Forum" now opens a preview dialog showing the subject and editable BBcode body; the post only fires after the user clicks "Post to Forum" in the dialog. Subject and body edits in the dialog are forwarded to the backend.
backend/forum_poster.py: post_lb_topic() accepts subject_override and body_override kwargs so user edits from the preview are used verbatim.

---

[2026-05-14] — fix(backend): WTRF forum login failures due to wrong domain and bad URL check

Fixed

backend/forum_poster.py: FORUM_BASE corrected from watchingtheriverflow.com to watchingtheriverflow.org.
backend/forum_poster.py: Login success check was matching "action=login" as a substring of "action=login2" (the POST endpoint), causing every login to be flagged as failed. Fixed to only treat a redirect back to the GET login page as failure. This forum returns 200 with empty body at login2 on success.
backend/forum_poster.py: _get_session now collects all hidden fields from the login form (not just hash_passwrd) to include sc and any other CSRF fields.

---

[2026-05-14] — fix(gui): WTRF and qBittorrent password fields blank on restart

Fixed

gui/setup_tab.py: _load_wtrf_settings and _load_qbt_settings now populate both username and password from keyring (was discarding password with _).

---

[2026-05-14] — feat(gui/backend): WTRF forum "Test Connection" button on Setup tab

Added

gui/setup_tab.py: _WtrfTestThread QThread; "Test Connection" button in the WTRF Forum group; _on_wtrf_test / _on_wtrf_test_finished handlers; green/red status label feedback.
backend/app.py: POST /api/wtrf/test — calls forum_poster._get_session() to verify credentials without posting. Falls back to stored keyring creds if body fields are empty.

---

[2026-05-14] — refactor(gui): setup tab two-column layout to eliminate wasted right-side space

Changed

gui/setup_tab.py: Replaced single-column lower section with a two-column QHBoxLayout. Left column holds Web Scraper and Scraper Log groups (stretch=3); right column holds qBittorrent, WTRF Forum, and Torrent Settings groups (stretch=2). Scraper log switched from fixed height to minimumHeight so it expands to fill available space.

---

[2026-05-14] — fix(checksum): rename generated checksum files from _lbgen to _mychecksums (TODO-014)

Changed

backend/checksum_utils.py: Renamed _lbgen_path() to _mychecksums_path(). All generated checksum files are now named <folder>_mychecksums.ffp / _mychecksums.md5 (incrementing to _mychecksums_2, etc.) instead of _lbgen.*. TORRENT_EXCLUDE in torrent_maker.py already matched this pattern — no change needed there.

---

[2026-05-14] — feat(collection): torrent history panel and path relocation flow (TODO-012, TODO-013)

Changed

gui/collection_tab.py: Added torrent history sub-panel to My Collection tab. Selecting a single entry loads all torrents table records via GET /api/torrent/<lb>. Each row shows a green/red/orange indicator (source_folder_exists / torrent_file_exists), created_at, torrent filename, source folder, and qBt added status. Regenerate button enabled when torrent file is missing. Relocate Source button opens folder browser, cross-checks folder contents against checksums for the entry, updates source_folder via PATCH /api/torrent/<id>, writes a rename_log.txt relocation entry, and optionally renames the folder to the standard YYYY-MM-DD Location (LB-XXXXX) format (calling write_rename_log + shutil.move). Added _STANDARD_LB_NAME_RE module constant. Added _build_torrent_history_panel(), _on_coll_selection_changed(), _load_torrent_history(), _populate_torrent_history(), _get_selected_history_record(), _on_history_context(), _history_add_record(), _on_history_qbt_done(), _history_regen_record(), _on_history_regen_done(), _history_relocate_record(), _cross_check_folder(), _get_standard_lb_name() methods.

---

[2026-05-14] — feat(phase1): Torrent generation, qBittorrent seeding, WTRF forum posting, credentials keyring, rename log

Changed

backend/db.py: Added torrents and rename_history tables to SCHEMA_SQL. Added get_torrents_for_lb(), add_torrent_record(), update_torrent_record(), add_rename_history() helpers.

backend/paths.py: Added TORRENTS_DIR = data/torrents/; ensure_data_dirs() now creates it.

requirements.txt: Added torf==4.3.1 and keyring==25.7.0 (+ transitive deps).

backend/app.py: Added POST /api/torrent/create, GET /api/torrent/<lb>, PATCH /api/torrent/<id>, GET /api/trackers, POST /api/qbt/test, POST /api/qbt/add, POST /api/entry/<lb>/post_forum. Extended GET /api/db/settings to include qbt_host, qbt_port, qbt_category, qbt_tags, tracker_list keys.

gui/rename_tab.py: Calls write_rename_log() before each shutil.move so every folder rename is recorded in rename_log.txt and rename_history.

gui/setup_tab.py: Added qBittorrent section (host, port, username/password, category, tags, Save/Test/Clear), WTRF Forum section (username/password, Save/Clear), and Torrent Settings section (tracker list selector, Refresh Trackers button).

gui/collection_tab.py: Added Create Torrent, Add to qBittorrent, and Post to Forum buttons to the My Collection panel.

Added

backend/credentials.py: Keyring-backed credential storage. SERVICE_QBT / SERVICE_WTRF constants. keyring_available(), save_credentials(), get_credentials(), delete_credentials(), credentials_stored(), prompt_if_missing().

backend/rename.py: write_rename_log() helper — appends a timestamped line to rename_log.txt and inserts a rename_history DB row. Used by rename_tab and (future) collection_tab path relocation.

backend/torrent_maker.py: torf-based .torrent generation. TORRENT_EXCLUDE rules (rename_log.txt, _mychecksums.*, .torrent, Thumbs.db, .DS_Store). fetch_trackers() fetches ngosang/trackerslist via jsDelivr CDN and caches per session. make_torrent() and make_torrent_batch().

backend/qbittorrent.py: qBittorrent WebUI API v2 integration. test_connection(), add_torrent_for_seeding(), add_torrent_from_db(). Sets save_path to parent of source_folder so seeding starts immediately.

backend/forum_poster.py: SMF 2.x HTTP session login + post. post_lb_topic() scrapes sc/seqnum fields, builds body from cached .txt/.ffp attachments (falls back to entry table), attaches .torrent as multipart POST.

[2026-05-14] — feat(rename/xref): Multiple IDs cyan color + right-click resolve; xref-aware naming; xref filter on Search and Collection tabs

Changed

gui/rename_tab.py: Multiple IDs rows now use a distinct cyan color (#B2EBF2) instead of red. Right-click a Multiple IDs row to get a "Resolve — Apply…" submenu listing each candidate LB (with xref suffix when applicable). Choosing one resolves the row into a single-LB rename. Rename is blocked for unresolved multiple_ids rows. Updated legend to include the new color. populate_from_lookup now filters detail items to MATCHED/MATCHED (INCOMPLETE) status only, preventing resolved duplicate losers from triggering spurious "Multiple IDs" rows. xref-aware: lb_str and proposed names include "-xref{N:04d}" suffix when the match is via a cross-reference checksum. _lb_in_name, _has_wrong_lb, and _strip_lb_from_name all handle the xref suffix. _fmt_lb() helper added.

backend/db.py: Added get_xref_lb_numbers() — returns distinct lb_numbers that have any xref checksum (xref > 0).

backend/app.py: Added GET /api/checksums/xref_lb_numbers route.

gui/search_tab.py: Added "Xref only" checkbox filter — fetches xref lb_numbers on startup and filters search results to entries that have xref variants in the DB.

gui/collection_tab.py: Added "Xref only" checkbox filter to My Collection — same xref lb_number set, filters owned entries to those with xref variants.

[2026-05-13] — feat(lookup/verify): duplicate resolution, folder/summary filtering, verify NO CHECKSUMS, lookup→verify folder carry

Changed

backend/db.py: lookup_checksums() now resolves duplicate-checksum ambiguity — when the same checksum appears in multiple LB entries and one is fully MATCHED while others are INCOMPLETE, the fully-matched LB is preferred and its items are reclassified from DUPLICATE to MATCHED.

backend/checksum_utils.py: verify_folder() now returns status='no_checksums' (instead of 'pass') when audio files are present but no checksum files (.ffp/.md5/.st5) exist at all.

gui/lookup_tab.py: Added folder filter (click a listbox item to show only that folder's rows in summary and detail; click again to clear). Added summary LB filter (click a summary row to show only that LB's detail items; click again to clear). Filter state shown in section header labels. No-checksum folder detection now requires audio files to be present (folders with neither audio nor checksums are not flagged). No-checksum summary rows are now built inline in _on_lookup_done for both 'listbox' and 'scan-tree' sources. Added get_lookup_folders() method.

gui/verify_tab.py: NO CHECKSUMS status shown in yellow when a folder has audio but no checksum files. Added add_folders_from_lookup(folders) method to receive folders from the Lookup tab.

gui/main_window.py: On switching to the Verify tab, lookup folders are automatically carried over if the Verify folder list is empty.

[2026-05-13] — fix(checksum): SHN shntool hash now works when shorten is not installed (BUG-040)

Fixed

backend/checksum_utils.py: compute_shntool() silently returned None for .shn files on systems without the shorten decoder — shntool requires shorten to decode SHN, but shorten is not in standard Linux repos. Added _compute_shntool_via_ffmpeg() fallback: when shntool hash produces no output for a .shn file, ffmpeg decodes it to a temp WAV and shntool hashes the WAV instead (lossless, produces identical PCM data). Also updated generate_checksums() for SHN mode to write both file-MD5 hashes and shntool audio hashes into the generated .md5 file, matching the lbdir format.

[2026-05-13] — fix(rename): individual checkboxes on Rename tab now toggle on click

Fixed

gui/rename_tab.py: NoEditTriggers blocked Qt's delegate from routing mouse clicks to setData() for CheckStateRole changes, so clicking a checkbox had no effect. Connected view.clicked to a new _on_cell_clicked() handler that calls model.setData() directly, bypassing the edit-trigger restriction.

[2026-05-13] — fix(lbdir): compute shntool hash for WAV files; include in overall verdict (BUG-039)

Fixed

backend/checksum_utils.py: verify_folder_lbdir() only ran compute_shntool() when is_shn was True, leaving shn_actual=None for .wav files → FAIL display despite passing MD5. Extended compute condition to (is_shn or is_wav) and added shntool check to the else-branch so WAV audio integrity is verified and counted in the overall verdict.

[2026-05-13] — fix(lbdir): WAV-format recordings no longer show phantom .shn MISSING entries

Fixed

backend/checksum_utils.py: parse_lbdir_file() was unconditionally converting every .wav filename in the shntool and shntool_len sections to .shn and forcing has_shn=True. For WAV-format recordings (lbdir *.wavf.txt) the files on disk are .wav, so the conversion created nonexistent .shn keys reported as MISSING and set the mode to SHN incorrectly. Fix: conversion is now conditional on has_shn already being True (i.e. the md5 section already saw real .shn filenames).

[2026-05-13] — feat(rename): allow "LB already in name" rows to be moved to 0. Processed without renaming

Changed

gui/rename_tab.py: _on_rename() now processes two eligible states: "needs_rename" (Complete match) renames and moves; "has_lb" (LB already in name) moves under the existing folder name with no rename. The confirm dialog and status message distinguish between the two operations. All other statuses remain blocked.

[2026-05-13] — fix(rename): restrict rename+move to "Complete match" rows only

Changed

gui/rename_tab.py: _on_rename() now filters the selected rows to only those in "needs_rename" state (Complete match). Rows with any other status (No match, LB already in name, Wrong LB, Multiple IDs) are silently skipped — they are not renamed and not moved to "0. Processed". The confirm dialog count and message now reflect only the eligible rows. If no eligible rows exist among the selection, a descriptive status message is shown and the dialog is not raised.

[2026-05-13] — feat(lookup): show all input folders in summary, including those with no DB match

Added

gui/lookup_tab.py: After building LB summary rows, group NOT FOUND detail items by their source folder (using source_file set by the worker). Any folder whose checksums produced zero DB matches now gets its own NOT FOUND summary row showing the count of unmatched checksums. Folders that share items with a matched LB are excluded to avoid double-counting. Clipboard lookups with no source file fall back to a single "NOT FOUND" label row.

[2026-05-13] — fix(lbdir): normalize Windows backslash path separators in lbdir filenames on Linux

Fixed

backend/checksum_utils.py: parse_lbdir_file() extracted filenames verbatim from lbdir files, preserving Windows-style backslashes (e.g. artwork\back.JPG). On Linux, pathlib treats backslashes as literal characters rather than path separators, so fpath.exists() returned False for all files in subdirectories. Added .replace('\\', '/') on every fname extracted in the md5, ffp, shntool, and shntool_len parsing blocks so keys and paths are consistently normalized before use.

[2026-05-13] — fix(startup): defer AttachmentsTab tree load to first activation — removes 3s startup block

Fixed

gui/attachments_tab.py: _refresh_tree() (HTTP request + directory scan) was called in __init__, blocking main-thread tab construction for ~3s. Replaced with a _tree_loaded flag; tree now populates in showEvent on first activation, matching the existing lazy WebEngine pattern.

[2026-05-13] — feat(setup): add shntool status indicator alongside SoX and ffmpeg; split into three separate rows

Changed

backend/checksum_utils.py: Added check_shntool_version() — calls shntool -v, returns first line of output or empty string if unavailable.
backend/app.py: /api/spectrogram/check now imports check_shntool_version and returns shntool_available and shntool_version alongside existing sox/ffmpeg fields.
gui/setup_tab.py: SoX/ffmpeg/shntool indicators split into three separate labelled rows (SoX:, ffmpeg:, shntool:). _check_sox() updated to populate each label independently. "Re-check" button moved to the shntool row. ffmpeg shown in orange when missing (non-critical), shntool in red (required for SHN verification).

[2026-05-13] — fix(lookup): Scan Tree now populates listbox and uses path-based lookup (BUG-036)

Fixed

gui/lookup_tab.py: _on_scan_tree was reading file contents and passing them as raw text to _run_lookup (clipboard mode), so found files were never added to the listbox and source_file was never populated on detail items. Replaced with _ScanTreeWorker(QThread) that does the rglob off the main thread; _on_scan_tree_done adds found paths to _all_paths, refreshes the listbox, then starts a path-based _LookupWorker. Also fixed inverted _mychecksums filter logic (was keeping _mychecksums files and dropping others, should be the reverse).

[2026-05-13] — fix(collection): scan now recognises "LB XXXXX" (space separator) folder names; remove unused QSpinBox import

Changed

gui/collection_tab.py: _LB_RE updated from r'LB-0*(\d+)' to r'LB[- ]0*(\d+)' so folders named "LB 12345" are matched alongside "LB-12345". Removed unused QSpinBox import.

[2026-05-13] — fix(collection): Scan Directory / Scan Tree froze UI on large drives (BUG-034)

Fixed

gui/collection_tab.py: Moved filesystem walk (iterdir / rglob) and /api/collection/lb_numbers network call out of the main thread into a new _ScanWorker QThread. Both _on_scan_directory and _on_scan_tree now start the worker and show a "Scanning…" status; _on_scan_finished presents the preview dialog and calls _bulk_add when results arrive.

[2026-05-13] — chore(startup): add startup timing logger to data/startup.log

Added

backend/startup_log.py: New module — init(path) truncates the log and records start time; t(label) appends a wall-clock timestamp + elapsed seconds entry. Thread-safe via lock; no-ops silently if not yet initialized.

Changed

main.py: Calls startup_log.init() after ensure_data_dirs(); adds t() probes at flask-thread-start, QApplication creation, splash shown, flask-port-ready, main_window import, MainWindow created, and window.show().
backend/app.py: create_app() adds t() probes around init_db(), start_file_watcher(), and route registration.
gui/main_window.py: __init__ adds t() probes around each build phase; _build_tabs adds t() probes before and after each tab module import and each tab instantiation.

[2026-05-13] — refactor(setup): move Data Management into Database group; add column-width persistence to DB Editor

Changed

gui/setup_tab.py: Database QGroupBox restructured as a horizontal split — existing archive controls on the left, Data Management (purge buttons) on the right with a vertical divider. coll_stats_label added showing live counts for My Collection, Wishlist, Personal Ratings, Watchdog Events, and Scrape Diff Rows. _refresh_collection_stats() added; called from _refresh_stats() on startup and after each purge. Standalone purge_group at the bottom of the tab removed.
gui/dbedit_tab.py: Column width persistence added — widths stored per-table in settings.ini under DbEditTab/<table>/col_widths. Right-click on any column header shows "Set width…", "Fit to contents", and "Fit all columns" options. sectionResized auto-saves on drag. Saved widths restored on table switch; first load falls back to resizeColumnsToContents.

[2026-05-13] — fix(dbedit): rows failed to load due to sqlite3.Row.description AttributeError; added Load Records button

Fixed

backend/app.py: dbedit_rows route now captures cursor before fetchall() and reads column names from cur.description (cursor attribute) instead of rows[0].description (which does not exist on sqlite3.Row). Empty tables also handled correctly.

Added

gui/dbedit_tab.py: "Load Records" button in toolbar clears search and reloads the first page for the current table. Removed unused QFont import.

[2026-05-13] — fix(verify): redefine "incomplete" as missing files on disk, not missing checksum types

Changed

backend/checksum_utils.py: In both verify_folder and verify_folder_lbdir, status logic updated. "incomplete" now means one or more audio files referenced by checksums are absent from disk. "fail" now means hash mismatches only. A folder with only an .md5 file where all hashes match now correctly returns "pass" instead of "incomplete".

[2026-05-13] — feat: FEAT-13 + FEAT-14 — Granular Collection Data Management and DB Editor Tab

Added

backend/db.py: integrity_events table added to SCHEMA_SQL; purge_collection, purge_wishlist, purge_collection_meta, purge_integrity_events, purge_entry_changes, delete_collection_entries functions added.
backend/app.py: _DBEDIT_READONLY/AUDIT/WARN constants; POST /api/collection/purge, POST /api/collection/delete_bulk, GET /api/dbedit/tables, GET /api/dbedit/table/<name>/schema, GET /api/dbedit/table/<name>/rows, PATCH /api/dbedit/table/<name>/row, DELETE /api/dbedit/table/<name>/rows, GET /api/dbedit/table/<name>/export routes.
gui/dbedit_tab.py: New DB Editor tab — table browser, paginated row viewer, inline cell editing with dirty-state tracking, row deletion with confirmation, context menu, CSV export.
gui/collection_tab.py: "Select All" and "Select None" buttons added to My Collection panel; _on_remove() replaced with bulk-delete via POST /api/collection/delete_bulk.
gui/setup_tab.py: "Data Management" group added with per-scope purge buttons (collection, wishlist, personal_meta, integrity_events, entry_changes) and confirmation dialogs.
gui/main_window.py: DbEditTab registered as "DB Editor" tab (after Spectrograms); lazy table load on first activation via _on_tab_changed.

[2026-05-13] — feat(gui): Scan Tree button in My Collection tab — recursive LB-folder discovery

Added

gui/collection_tab.py: "Scan Tree…" button added to My Collection panel beside "Scan Directory". _on_scan_tree() uses rglob to find LB-numbered directories at any depth under a root. For LB numbers found at multiple depths the shallowest folder is kept. Reuses the existing _ScanPreviewDialog preview and _bulk_add workflow.

[2026-05-13] — feat(gui): FEAT-08 — Scan Tree batch lookup button in Lookup tab

Added

gui/lookup_tab.py: "Scan Tree…" button added to left panel below "Add Folders…". _on_scan_tree() recursively finds all .ffp/.md5/.st5/.sha1/.shn files under a user-selected root directory, concatenates their contents, and feeds them to _run_lookup() as a single combined lookup. Respects the _filter_mychecksums flag to skip _mychecksums files when the filter is active.

[2026-05-13] — fix(gui): spectrogram panning overshoot caused by stale label-local coordinates after scroll

Fixed

gui/spectrogram_tab.py: _ImageViewer.eventFilter — changed pan tracking from event.position() (label-local coords) to event.globalPosition() (screen coords). When the scrollbar value was updated on each MouseMove, the label shifted on screen, making the stored _pan_start invalid for the next delta calculation and causing overshoot-then-correction jitter. Global coordinates are unaffected by the widget's scroll position.

[2026-05-12] — feat(backend,gui): SoX spectrogram generation with two-pane viewer tab (SPEC-01 through SPEC-06)

Added

backend/sox_utils.py: New module — SoX/ffmpeg tool detection (cached per process), format classification (_SOX_NATIVE / _NEEDS_CONVERSION / AUDIO_EXTS_ALL), convert-to-temp-WAV pipeline for non-native formats (SHN, APE, WV, M4A, MP3, OGG), generate_spectrogram() public API, check_sox_version(), SoxNotFoundError / ConversionError / SpectrogenError exception hierarchy. Original audio files are never modified; temp WAVs are always deleted in a finally block.
backend/app.py: _spectro_state dict + _spectro_lock for thread-safe batch state; _do_spectro_batch() worker (module-level); five new routes: GET /api/spectrogram/check, POST /api/spectrogram/generate, GET /api/spectrogram/status, POST /api/spectrogram/stop, POST /api/spectrogram/list.
gui/spectrogram_tab.py: New tab — _DropFolderList (drag-drop folders), _ImageViewer (fit-width + Ctrl+scroll zoom + double-click reset), _Worker (QThread), SpectrogramTab (folder/track inventory, generate/stop/poll, right-click context menus, salmon highlight for missing PNGs).
gui/main_window.py: SpectrogramTab registered as tab index 7 (between Attachments and Setup); _on_tab_changed() handler connected to tabs.currentChanged — refreshes inventory on Spectrograms activation and triggers SoX check on first Setup activation.
gui/setup_tab.py: SoX status row added to Database group with Re-check button; _check_sox() calls GET /api/spectrogram/check and shows version + ffmpeg availability with green/red colour.

[2026-05-12] — fix(gui): search tab description column default width 1400→600; column widths now persist across view switches and sessions

Fixed

gui/search_tab.py: _DESC_DEFAULT_W reduced from 1400 to 600px. Added QSettings persistence (LosslessBob/SearchTab) so column widths survive tab switches and restarts. Connected sectionResized signal to update _col_widths immediately on user drag. Added _resizing_programmatically guard to prevent spurious saves during programmatic column sizing. Removed _col_widths = None reset in _on_results so user-set widths are preserved across new searches.

[2026-05-12] — feat(db,backend,gui): FEAT-03 per-entry personal metadata, FEAT-04 wishlist tab, FEAT-05 duplicate concert detector

Added

backend/db.py: New tables collection_meta and my_wishlist in SCHEMA_SQL. New functions get_collection_meta, set_collection_meta, increment_listen_count (FEAT-03); get_wishlist, add_to_wishlist, remove_from_wishlist, get_wishlist_lb_numbers (FEAT-04); get_collection_duplicates (FEAT-05).
backend/app.py: Routes GET/POST /api/collection/<lb>/meta and POST /api/collection/<lb>/listen (FEAT-03); GET/POST /api/wishlist and DELETE /api/wishlist/<lb> (FEAT-04); GET /api/collection/duplicates (FEAT-05).
gui/styles.py: Added ROW_WISHLIST color (#E8D5FF) for wishlist row backgrounds.
gui/collection_tab.py: Added _WishlistModel, _PersonalMetaDialog classes. Wishlist inner tab with context menu (remove, view web). Duplicates inner tab using QTreeWidget showing owned (green) and unowned (grey) LBs per show; lazy-loaded on first activation. "Edit Personal Info…" context menu item on My Collection rows opens rating/tags/listen dialog.
gui/lookup_tab.py: "Add to Wishlist" added to summary right-click context menu.
gui/search_tab.py: Row-level right-click context menu with "Add to Wishlist".

[2026-05-12] — refactor(scraper,gui): remove redundant "fill gaps" checkbox; gap-filling is now unconditional

Changed

backend/app.py: Removed fill_gaps parameter. Gap-filling (marking every sequential LB number not in checksums as MISSING) now always runs for both "Scrape All Missing" and explicit range scrapes. The effective upper bound is derived from the highest checksums lb_number when no end_lb is given.
gui/setup_tab.py: Removed fill_gaps_cb checkbox and all references. _on_scrape_range no longer sends fill_gaps in the payload.

[2026-05-12] — fix(scraper,db): BUG-032 — "Scrape All Missing" left gap LB numbers absent from database; BUG-031 — skip bypassed local page recovery

Fixed

backend/app.py: scrape_start now derives effective_end from the highest checksums lb_number when end_lb is absent ("Scrape All Missing" path). Every sequential gap between start_lb and effective_end is unconditionally passed through insert_missing_entry, ensuring no LB number is left out of the database. For explicit range scrapes the fill_gaps checkbox is still respected.
backend/db.py: insert_missing_entry changed from INSERT OR REPLACE to INSERT OR IGNORE — gap-filling can no longer overwrite a row that already has real scraped data.
backend/scraper.py: Moved local_page resolution before the skip block in scrape_entry(). The status=='missing' guard now permits scraping when use_local_pages=True and the local HTML file exists, so previously-404'd entries can be recovered from disk.

[2026-05-12] — fix(gui,backend): BUG-030 — auto-scrape fires after import post-DB-reset

Fixed

gui/setup_tab.py: _on_reset_finished now calls self._save_settings() after a successful reset so the user's current checkbox states are persisted back to the freshly-wiped meta table. Prevents auto_scrape reverting to NULL (which was treated as enabled).
backend/app.py: on_complete now uses explicit None-check (_val is None or _val != "0") to document the intended default-on behaviour and guard against future Python type surprises.

[2026-05-12] — feat(importer): real-time import progress status

Changed

backend/importer.py: Import is now async. Added _import_state dict (stage, rows_parsed, rows_total, rows_merged, new_lb_count, message, error), get_import_status(), and start_import_async(). run_import() updates state throughout, including per-chunk row counts during the merge step (10k-row batches). _import_flat_file reports row count every 10k lines.
backend/app.py: POST /api/db/import now fires start_import_async() and returns immediately; auto-scrape trigger moved into on_complete callback. Added GET /api/db/import/status endpoint.
gui/setup_tab.py: _ImportThread now uses a 15 s timeout (fire-and-forget start). Added _ImportStatusThread polling /api/db/import/status every 500 ms. Added import_progress QProgressBar to Database group: indeterminate during hash/parse/optimise stages, determinate (rows_merged / rows_total) during merge. Label updates live with stage messages.

[2026-05-12] — BUG-029: 2–4 s startup delay from eager QWebEngineView construction

Fixed

gui/attachments_tab.py: QWebEngineView (and its QWebEngineProfile/QWebEnginePage) are now created lazily on the first showEvent of the Attachments tab via QTimer.singleShot(0, _init_web_view), deferring the WebEngine GPU-process spawn until the user actually visits that tab. _preview_file updated to use setCurrentWidget instead of hardcoded setCurrentIndex so stack order no longer matters.

[2026-05-12] — BUG-028: ~7 s Flask startup delay from synchronous bloom filter build

Fixed

backend/db.py: rebuild_bloom() in init_db() was iterating every checksum row on the startup thread, blocking Flask for ~7 s on large databases. Moved to a daemon background thread via _rebuild_bloom_bg(). checksum_in_bloom() already returns True when _bloom is None so all lookups fall through to SQLite until the filter is ready.

[2026-05-12] — BUG-027: ~10 s Linux startup delay from missing AA_ShareOpenGLContexts

Fixed

main.py: Added QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts) before QApplication(sys.argv). QtWebEngine requires this flag at construction time; without it the GPU process falls back to a slow separate-context path on Linux.

[2026-05-12] — BUG-026: WebEnginePage/Profile teardown order warning on shutdown

Fixed

gui/attachments_tab.py: QWebEnginePage is now parented to QWebEngineProfile (not to the tab widget). Qt destroys a parent's children before the parent itself, so page is always destroyed before profile, eliminating the "Release of profile requested but WebEnginePage still not deleted" warning.

[2026-05-12] — BUG-025: db_reset "FOREIGN KEY constraint failed" after DB-01 enabled FK enforcement

Fixed

backend/app.py: db_reset now prepends PRAGMA foreign_keys=OFF to the DROP script so my_collection's FK on entries doesn't block the drop, then explicitly re-enables with PRAGMA foreign_keys=ON before calling init_db().

[2026-05-12] — DB-01–DB-08: Database performance pass (WAL, thread-local pool, covering indexes, temp-table lookup, FTS5 search, PRAGMA optimize, bloom filter, scrape diff changelog)

Changed

backend/db.py: DB-01/02 — WAL + performance PRAGMAs (synchronous=NORMAL, cache_size=-65536, mmap_size=536MB, temp_store=MEMORY); persistent per-thread connection pool via threading.local() — eliminates repeated connect/close overhead.
backend/db.py: DB-03 — Added idx_chk_covering (covering index on checksums) and idx_lb_xref0 (partial index WHERE xref=0) to SCHEMA_SQL.
backend/db.py: DB-04 — lookup_checksums() now uses CREATE TEMP TABLE + JOIN instead of dynamic IN clause; fixes 999-param SQLite limit for large lookups.
backend/db.py: DB-05 — Added entries_fts FTS5 virtual table (content='entries') with insert/update/delete triggers; init_db() rebuilds index on first run; search_entries() now uses FTS MATCH with LIKE fallback on syntax error.
backend/db.py: DB-07 — ScalableBloomFilter loaded from checksums on startup; lookup_checksums() skips SQLite entirely for definite-miss checksums.
backend/db.py: DB-08 — Added entry_changes table + idx_changes_lb index to SCHEMA_SQL; record_entry_changes() records field-level diffs before each entry upsert.
backend/importer.py: DB-02 — Removed conn.close() from _import_flat_file(); DB-06 — added PRAGMA optimize after bulk import; DB-07 — rebuild_bloom() called after each successful import.
backend/scraper.py: DB-06 — PRAGMA optimize called at end of scrape_range(); DB-08 — record_entry_changes() called before INSERT OR REPLACE INTO entries.
backend/app.py: DB-08 — Added GET /api/entry/<lb>/changes endpoint; db_reset now drops entries_fts, its triggers, and entry_changes before recreating schema.
requirements.txt: Added pybloom-live==4.0.0.

[2026-05-12] — WIN-05/06/07/08/09/10/11/12/13/14/15/16: Full Windows compat pass

Added

backend/paths.py: to_long_path() prefixes \\?\ on Windows for MAX_PATH bypass. WEBENGINE_DIR constant. ensure_data_dirs() warns when data path exceeds 200 chars on Windows.
gui/platform_utils.py: _subprocess_flags() helper for CREATE_NO_WINDOW. url_to_local_path() strips spurious leading slash from Qt6 Windows QUrl.toLocalFile().
tools/build_windows.bat: Windows build script (runs pyinstaller losslessbob.spec, creates dist/LosslessBob/data/).

Changed

backend/checksum_utils.py: _no_window_kwargs() suppresses console windows for subprocess on Windows. _find_shntool()/_get_shntool_cmd() auto-detect shntool via WSL on Windows; compute_shntool uses WSL path conversion and _no_window_kwargs. compute_md5/compute_ffp wrap open() with to_long_path. All shutil.which('shntool') replaced with _get_shntool_cmd() is not None.
backend/db.py: get_connection wraps DB path with to_long_path before sqlite3.connect.
backend/scraper.py: lb_dir and local_page wrapped with to_long_path at construction.
backend/scheduler.py: _handle() filters Thumbs.db/desktop.ini; delayed() cleans _pending in finally block. start_file_watcher uses WindowsApiObserver on Windows (falls back to Observer).
gui/styles.py: _platform_font_stack() selects Segoe UI on Windows, -apple-system on macOS, Ubuntu/Cantarell on Linux.
gui/rename_tab.py: Rename block uses Path objects; splits PermissionError/FileExistsError/OSError into separate handlers with actionable messages; validates for Windows-illegal characters; appends Windows Explorer tip when permission errors occur. Removed unused import os.
gui/verify_tab.py: shntool_missing message shows WSL install instructions on Windows. dropEvent uses url_to_local_path (WIN-14).
gui/lookup_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/lbdir_tab.py: dropEvent uses url_to_local_path (WIN-14).
gui/main_window.py: QSettings migrated to INI format at data/settings.ini (WIN-11). All 9 tab imports moved inside _build_tabs() for lazy loading (WIN-16). _refresh_status moved to background thread; initial fire delayed to 3000ms (WIN-16).
gui/attachments_tab.py: QWebEngineView now uses named profile with storage redirected to data/webengine_cache (WIN-15). Removed stale __file__-relative ATTACHMENTS_DIR definition.
main.py: Splash screen shown during Flask startup wait; QApplication created before _wait_for_port; error dialog and main window both use the same QApplication instance (WIN-16).
requirements.txt: Promoted waitress from optional comment to required dependency (WIN-06).
losslessbob.spec: Added waitress.task and waitress.server to hiddenimports (WIN-12).

[2026-05-12] — WIN-03 + WIN-04: Cross-platform file/folder opener; SQLite lock timeout

Added

gui/platform_utils.py: New shared module with open_folder(), open_file(), open_url(). Centralises all sys.platform branching for launching files and folders; uses os.startfile on Windows, open on macOS, xdg-open on Linux.

Changed

gui/collection_tab.py: _open_folders now delegates to open_folder() from platform_utils. Removed top-level import subprocess.
gui/attachments_tab.py: _open_externally now delegates to open_file() from platform_utils. Removed top-level import subprocess and import sys.
gui/setup_tab.py: _on_open_folder and _on_open_log now delegate to open_folder()/open_file() from platform_utils. Removed top-level import os, import subprocess, and import sys.
backend/db.py: get_connection() now passes timeout=30 and check_same_thread=False to sqlite3.connect(). Adds PRAGMA busy_timeout=30000 on every new connection so SQLite retries for up to 30 seconds before raising OperationalError on Windows lock contention.

[2026-05-10] — WIN-01 + WIN-02: Unified path resolution for frozen builds; Flask readiness poll replacing time.sleep

Added

backend/paths.py: New central path resolver. _app_root() returns Path(sys.executable).parent in PyInstaller frozen builds (sys.frozen=True) and Path(__file__).parent.parent otherwise. Exports APP_ROOT, DATA_DIR, DB_PATH, ATTACHMENTS_DIR, PAGES_DIR, LOG_FILE, TOOLS_DIR, and ensure_data_dirs().

Changed

backend/db.py: Replaced inline DB_PATH definition with import from backend.paths (re-exported so existing callers are unaffected).
backend/app.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR definitions with import from backend.paths.
backend/scraper.py: Replaced inline DATA_DIR/ATTACHMENTS_DIR/PAGES_DIR definitions with import from backend.paths. Removed now-unused pathlib import.
backend/scheduler.py: Replaced inline DATA_DIR definition with import from backend.paths.
backend/importer.py: Replaced inline DATA_DIR definition with import from backend.paths.
gui/setup_tab.py: Replaced __file__-relative _LOG_FILE and data_dir with LOG_FILE and DATA_DIR from backend.paths.
main.py: Replaced time.sleep(0.5) with _wait_for_port() TCP poll (100ms interval, 15s timeout). On Windows uses Waitress as WSGI server for stable port binding. Deferred gui.main_window import to inside main() to avoid PyInstaller/DPI issues. Added fatal error dialog if Flask does not start within timeout. Added ensure_data_dirs() call at Flask startup.

[2026-05-10] — WIN-17: Fix drag-and-drop crash caused by OLE COM reentrancy on Windows

Fixed

gui/lookup_tab.py: Moved event.acceptProposedAction() before signal emission in DropListWidget.dropEvent so OLE marks the transaction complete before any widget modification. Removed self._refresh_listbox() from _add_path() — callers now own the refresh call. Updated _on_files_dropped to defer _refresh_listbox() via QTimer.singleShot(0, ...) so listbox.clear() never runs while the COM Drop() call is on the stack. Added explicit self._refresh_listbox() to _on_add_folders to restore the refresh it previously relied on from _add_path().

gui/verify_tab.py: Same acceptProposedAction-first fix in DropFolderListWidget.dropEvent. Changed _on_folders_dropped to use QTimer.singleShot(0, self._refresh_listbox) instead of a synchronous call.

gui/lbdir_tab.py: Identical fix to verify_tab.py.

[2026-05-08] — Fix Search tab column sizing: description default width, width retention on paging, right-click header width entry

Fixed

gui/search_tab.py: Description column now defaults to 1400 px instead of expanding to fit content; other columns still use `resizeColumnsToContents()` on first load. Column widths are now snapshotted from the header immediately before each `set_rows()` call so any user drag-resize is preserved when paging (Qt resets QHeaderView sections on model reset). Right-click on any column header opens a "Set column width…" dialog (QInputDialog) to enter an exact pixel value; the stored widths are updated so paging continues to respect the change.

[2026-05-08] — Fix column widths jumping on page navigation; add Word wrap toggle to Search and Collection tabs

Fixed

gui/search_tab.py: Column widths are now computed once via `resizeColumnsToContents()` on the first page with data and stored as absolute pixel values. Subsequent page renders restore those stored widths instead of re-calling `resizeColumnsToContents()`, so columns stay stable while paging.

gui/collection_tab.py: Same fix applied to My Collection (`coll_view`) and Missing (`miss_view`). Widths are reset and recomputed on each fresh data load.

Added

gui/search_tab.py: "Word wrap" checkbox in the search bar row. When checked, enables word wrap on the results table and auto-sizes rows; when unchecked, restores fixed single-line rows. Description text is no longer truncated at 120 chars.

gui/collection_tab.py: "Word wrap" checkbox added to My Collection button row and Missing button row, with the same on/off behaviour. Description text truncation removed from `_MissingModel`.

---

[2026-05-08] — Fix Results per page resetting to 50 on every startup

Fixed

gui/setup_tab.py: Added `_loading` flag set to True during `_load_settings` and False in a finally block. `_save_settings` returns early while the flag is set. Previously, each `setChecked`/`setValue` call during loading fired connected signals (`stateChanged`, `valueChanged`) that triggered `_save_settings` before `search_page_spin` had been populated from the DB, overwriting the stored value with the widget default of 50.

---

[2026-05-07] — Uniform fixed width on all four scraper action buttons

Changed

gui/setup_tab.py: Set all four scraper buttons (Scrape All Missing Entries, Stop Scraper, Scrape, Scrape Range) to a shared fixed width of 180px via a local constant `_SCRAPE_BTN_W`.

---

[2026-05-07] — Search filters, collection pagination/year filter, scraper grid and label fixes

Added

gui/search_tab.py: Three client-side filter checkboxes on the search bar — "Missing only" (status == 'missing'), "Owned only" (LB in My Collection), "Not owned" (LB not in My Collection). All three are AND-combined. Combining "Owned only" + "Not owned" yields an empty result. The owned filter re-renders automatically when `_OwnedWorker` finishes loading after a search.

gui/collection_tab.py: My Collection panel now auto-loads on startup (blank-screen fix). Added client-side pagination (Prev/Next, page label) driven by the shared Results per page setting. Added year dropdown filter populated from date_str of loaded entries. Text + year filters combined with AND; both reset to page 0 on change.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `collection_tab.set_page_size` so the Results per page spinner also controls My Collection pagination.

Fixed

gui/search_tab.py: Double-click URL now formats LB number as 5-digit zero-padded (`LB-{lb:05d}.html`). Previously used bare integer, producing 404 for any LB below 10000.

gui/setup_tab.py: "Mark sequential gaps as MISSING" checkbox renamed to "Skip LB numbers with no checksum data" per user request. Grid restructured so Scrape All Missing Entries, Scrape (single), and Scrape Range buttons all occupy column 2 of the grid, making them the same width. Stop Scraper moved to column 3. Status label and fill-gaps checkbox now span columns 3–4.

---

[2026-05-07] — Yellow highlight for status=missing search rows; fixed scraper button layout and height clipping

Fixed

gui/search_tab.py: SearchModel.data() now returns a yellow QColor("#FFFF99") for the BackgroundRole when a row has status="missing", so gap-placeholder entries are visually distinct instead of appearing as blank uncoloured rows.

gui/setup_tab.py: Replaced three stacked QHBoxLayout rows in the Web Scraper section with a QGridLayout (4 columns: label, input, action button, extras). All three rows — bulk scrape, single entry, and range — now align in a clean grid with no visual overlap.

gui/styles.py: Added min-height: 20px to the QPushButton stylesheet rule so buttons in mixed-height rows are never clipped.

---

[2026-05-07] — Persistent scraper log file; fixed [web]/[local] source labels; error entries now logged

Added

gui/setup_tab.py: `_LOG_FILE = data/scraper.log` — every `_log()` call now appends to this file in addition to the in-app widget. Log file management row added to the Scraper Log group: a size label (auto-refreshed after each write and on startup), an "Open Log File" button, and a "Purge Log" button (truncates the file and clears the in-app widget after confirmation).

Fixed

backend/scraper.py: Added `last_lb` field to `_scrape_state`, set to the LB number that just finished processing (alongside `last_source`/`last_action`). Previously `current_lb` was set at the START of processing while `last_source` was set at the END, so the GUI polled them out of sync and log lines showed the wrong source tag.

gui/setup_tab.py: `_on_scrape_status` now logs `last_lb` (the just-completed entry) instead of `current_lb` (the one currently being processed). This ensures every log line's `[local]`/`[web]` tag correctly matches the logged LB number. Added an explicit "Error scraping LB-X" log line for error entries (previously silently dropped, causing the next entry to appear with no source tag).

---

[2026-05-07] — Scraper progress bar enlarged to show percentage text

Changed

gui/styles.py: Added `QProgressBar#scrapeProgress` override — 20 px tall with centered text. The global QProgressBar rule (6 px, no text) still applies to the thin activity bars in Verify and lbdir tabs.

gui/setup_tab.py: Set `objectName("scrapeProgress")` on the scraper progress bar so the taller QSS rule targets only that widget.

---

[2026-05-07] — Search tab pagination and configurable results-per-page setting

Changed

backend/db.py: `search_entries` default limit changed from 100 to `None` (unlimited). Caller can still pass an explicit limit. Search tab now fetches all matching entries and paginates client-side.

backend/app.py: `GET /api/db/settings` now returns `force_scrape` and `search_page_size` in addition to the existing keys.

gui/search_tab.py: Added client-side pagination. All results are fetched from the API and stored in `_all_results`; only the current page slice is shown in the table. Prev/Next buttons and a "Page X of Y (N results)" label appear between the search bar and table whenever there is more than one page. A new `set_page_size(n)` public method resets to page 1 and re-renders; called by the setup tab signal. `_load_page_size` reads `search_page_size` from meta on startup.

gui/setup_tab.py: Added "Search" group with a "Results per page" spinner (range 10–500, step 10, default 50). Saved to meta as `search_page_size`. Emits `search_page_size_changed(int)` signal on change. `_load_settings` now loads `search_page_size` and `force_scrape` from meta.

gui/main_window.py: Connected `setup_tab.search_page_size_changed` to `search_tab.set_page_size`.

---

[2026-05-07] — Local pages cache, scrape skip fixes, use_local_pages setting, [local]/[web] log labels

Changed

backend/scraper.py: Added `PAGES_DIR = DATA_DIR / "pages"` constant. `scrape_entry` now accepts `use_local_pages` parameter — reads `data/pages/LB-XXXXX.html` from disk when available instead of hitting the network, falling back to web only when no local file exists. When fetching from web, the HTML is saved to `data/pages/` for future reuse. Added `last_source` field (`'local'` or `'web'`) to `_scrape_state` and to the `scrape_entry` return dict. `scrape_range` accepts and threads `use_local_pages`; suppresses the inter-entry delay when `local_source=True`. `scrape_entry` attachment download now respects `use_local_pages` — existing files on disk are never re-downloaded when `use_local_pages=True`, even if `force=True`.

backend/app.py: `use_local_pages` added to `/api/db/settings` GET key list. Single-entry scrape route and `/api/scrape/start` route both read `use_local_pages` from meta and pass it through. `_start_scrape_thread` gains `use_local_pages` parameter forwarded to `scrape_range`.

gui/setup_tab.py: Added "Use local pages for metadata (data/pages/)" checkbox, saved/loaded via `use_local_pages` meta key. Scraper log now appends `[local]` or `[web]` after each "Scraped LB-X" entry using `last_source` from the status poll.

Fixed

backend/scraper.py: Scrape skip logic incorrectly re-scraped entries when `download_files=False` — any entry with `entry_files` rows (even with `downloaded=0`) was not being skipped because the pending-count check always fired. Fixed by returning `{skipped: True}` immediately when `not download_files` and the entry row exists.

backend/scraper.py: Entries with attachment files placed in `data/attachments/` from an external source were never marked `downloaded=1` in the DB, causing the scraper to repeatedly re-scrape them. Fixed by scanning the filesystem for each `downloaded=0` record and updating the DB before evaluating the pending count.

backend/scraper.py: `force=True` caused the attachment download loop to re-download files already present on disk when `use_local_pages=True`. Fixed by changing the skip condition to `local_path.exists() and (not force or use_local_pages)`.

gui/lbdir_tab.py: "Show all files" checkbox was unchecked by default, hiding pass rows and requiring a manual toggle. Changed default to checked.

gui/verify_tab.py: Same as above — "Show all files" now checked by default.

Added

backend/scraper.py: `last_source` field in `_scrape_state` (`'local'` | `'web'` | `None`) so the GUI can distinguish the metadata source per entry.

gui/setup_tab.py: "Use local pages for metadata (data/pages/)" checkbox — persisted in meta as `use_local_pages`.
