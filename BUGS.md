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

BUG-068: Crawler seeded from domain root — DreamHost placeholder has no useful links
Status: Fixed
File(s): backend/site_crawler.py
Reported: 2026-05-18
Fixed: 2026-05-18
Description: Running the site crawler in full mode fetched only one file (the domain root index.html, 808 bytes) and stopped. The root URL http://www.losslessbob.wonderingwhattochoose.com/ serves a DreamHost "coming soon" placeholder page with no same-domain links. The correct entry point is /LosslessBob.html.
Root cause: crawl() default start_url was BASE_URL ("/") instead of SITE_HOME_URL ("/LosslessBob.html"). No explicit seed URLs were added, so the BFS queue was empty after the root fetch.
Fix: Added SITE_HOME_URL = BASE_URL + "/LosslessBob.html"; changed crawl() default start_url to SITE_HOME_URL. Added SEED_URLS constant seeding /bynumber/LBMbynumber.html and /detail/LB-bootleg-by-title.html as a safety net for every crawl session, regardless of start_url.

---

BUG-067: PyQt6 + lxml SIGABRT when Qt widget tests run before lxml-importing tests
Status: Open
File(s): tests/test_scraper_crawler.py, tests/test_lb_master.py
Reported: 2026-05-18
Description: Running all three test files in a single pytest process causes a Fatal Python error: Aborted when tests/test_lb_master.py Qt widget tests (TestSearchTabStatusColumn, TestDbEditorIntegrityPanel) run before tests/test_scraper_crawler.py which imports BeautifulSoup (bs4 loads lxml at import time). The SIGABRT is a known incompatibility between PyQt6 cleanup and lxml's memory allocator on Linux.
Root cause: bs4 unconditionally imports lxml at bs4 import time regardless of which parser is used. When lxml's .so is loaded into the same process as PyQt6 objects, Qt's atexit/destructor sequence may SIGABRT.
Fix: Run test files separately (`pytest tests/test_scraper_crawler.py`) or exclude Qt widget tests when running combined (`pytest tests/ -k "not SearchTab and not DbEditor and not CollectionTab"`). All three files pass independently (59 + 27 + 13 = 99 total tests, all green).

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

BUG-069: Nominatim batch geocoder has no HTTP-429 / rate-limit retry logic
Status: Open
File(s): backend/geocoder.py:run_batch
Reported: 2026-05-19
Description: run_batch() sleeps 1.1 s between requests to stay within Nominatim's 1 req/sec ToS. However, if the server still returns HTTP 429 (overloaded or policy breach), the request is logged as a network error and marked source='failed' with no retry or back-off. Large batch runs against a slow Nominatim endpoint may accumulate many false 'failed' rows that require --retry-failed later.
Root cause: geocode_one() wraps urllib.request.urlopen in a generic except; 429 responses are not distinguished from actual failures.
Fix: Not yet implemented. Suggested fix: check resp.status == 429 and raise with a marker; run_batch catches the marker, sleeps an additional 60 s, then retries the same location without advancing the progress counter.

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
