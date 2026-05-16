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
