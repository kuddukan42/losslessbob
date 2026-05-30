# gui_next Wiring Gap Audit — 2026-05-28

Cross-referenced against the legacy PyQt6 GUI (`gui/`) and Flask backend (`backend/app.py`).
Each gap entry now notes the exact legacy source file that implements the same feature so the
frontend wiring can be ported directly.

---

## Summary — Updated 2026-05-30

All screens are now wired. Remaining gaps from the 2026-05-28 audit have been closed.

| Screen | Status | Wired% | Notes |
|---|---|---|---|
| ScreenSetup | ✓ done | ~100% | |
| ScreenSearch | ✓ done | ~95% | |
| ScreenCollection | ✓ done | ~100% | Wishlist, batch-remove progress bar, tab badge all wired |
| ScreenHome | ✓ done | ~100% | |
| ScreenBootlegs | ✓ done | ~100% | |
| ScreenThemes | ✓ done | 100% | |
| ScreenPipeline | ✓ done | ~98% | "Open queue location" IconButton wired 2026-05-30 |
| **ScreenLookup** | **✓ done** | **~90%** | "Generate missing" shows advisory toast (intentional — delegates to Verify) |
| **ScreenVerify** | **✓ done** | **~95%** | All actions wired |
| **ScreenRename** | **✓ done** | **~98%** | Disambiguation panel fully wired 2026-05-30; NFT suffix logic added |
| **ScreenLBDIR** | **✓ done** | **~95%** | All 4 panes wired |
| **ScreenAttachments** | **✓ done** | **~98%** | "Cache missing" batch button added 2026-05-30 |
| **ScreenSpectrograms** | **✓ done** | **~95%** | Tool dots, inventory, generate/stop/poll, PNG viewer |
| ScreenMap | ✓ done | — | |

---

## 1. Backend Route Status (revised after cross-reference)

The original audit over-reported missing routes. After checking `backend/app.py` line-by-line,
**most routes already exist**. The table below corrects the record.

| Route | Status in app.py | app.py line | Legacy caller |
|---|---|---|---|
| `GET /api/home/stats` | **EXISTS** | 184 | New screen; route added recently |
| `GET /api/activity/log` | **EXISTS** | 225 | New screen; route added recently |
| `GET /api/master/status` | **EXISTS** | 2963 | `gui/setup_tab.py` |
| `POST /api/credentials/qbt` | **EXISTS** | 2357 | `gui/setup_tab.py` |
| `DELETE /api/credentials/qbt` | **EXISTS** | 2380 | `gui/setup_tab.py` |
| `POST /api/credentials/wtrf` | **EXISTS** | 2338 | `gui/setup_tab.py` |
| `DELETE /api/credentials/wtrf` | **EXISTS** | 2395 | `gui/setup_tab.py` |
| `POST /api/rename_history/purge` | **EXISTS** | 1028 | `gui/setup_tab.py` |
| `POST /api/flat_file/purge` | **EXISTS** | 1040 | `gui/setup_tab.py` |
| `POST /api/scraper/purge` | **EXISTS** | 1053 | `gui/setup_tab.py` |
| `POST /api/fingerprint/purge` | **EXISTS** | 1066 | `gui/setup_tab.py` |
| `GET /api/collection` | **EXISTS** | 752 | `gui/main_window.py` |
| `POST /api/collection` | **EXISTS** | 781 | `gui/main_window.py` |
| `PATCH /api/collection/<lb>` | **EXISTS** | 802 | `gui/main_window.py` |
| `DELETE /api/collection/<lb>` | **EXISTS** | 820 | `gui/main_window.py` |
| `GET /api/collection/lb_numbers` | **EXISTS** | 878 | `gui/search_tab.py` |
| `GET /api/search/years` | **EXISTS** | 698 | `gui/search_tab.py` |
| `GET /api/wishlist` | **EXISTS** | 942 | `gui/main_window.py` |
| `POST /api/wishlist` | **EXISTS** | 954 | `gui/lookup_tab.py` (right-click menu) |
| `DELETE /api/wishlist/<lb>` | **EXISTS** | 972 | `gui/main_window.py` |
| `GET /api/collection/duplicates` | **EXISTS** | 990 | `gui/main_window.py` |
| `POST /api/pipeline/scan-tree` | **EXISTS** | 3942 | `gui/main_window.py` |
| `GET /api/fingerprint/lb_numbers` | **EXISTS** | 3710 | `gui/spectrogram_tab.py` |
| `POST /api/spectrogram/list` | **EXISTS** | 1855 | `gui/spectrogram_tab.py` |
| `GET /api/spectrogram/check` | **EXISTS** | 1782 | `gui/setup_tab.py`, `gui/spectrogram_tab.py` |

### Routes that are genuinely new (need to be created)

| Route | Why needed | Suggested body / response |
|---|---|---|
| `POST /api/rename/apply` | Old GUI does `shutil.move` + `write_rename_log()` directly in the Python process (no HTTP hop). Electron frontend cannot call Python modules, so a route is required. | Body: `{renames: [{old_path, new_path, lb_number?}]}` → `{applied: N, errors: [...]}`. Implementation: loop, `shutil.move(old_path, new_path)`, call `backend.rename.write_rename_log()`. |
| `POST /api/master/github_release` | Used in ScreenSetup two-step publish flow. No legacy equivalent — curator-only feature not in old GUI. | Design needed before implementation. |

---

## 2. ScreenLookup — 0% wired

**Legacy:** `gui/lookup_tab.py` — complete implementation, port the API call patterns directly.

### API response format (from `_on_lookup_done`, lookup_tab.py:1204)

`POST /api/lookup {text: string}` returns:
```json
{
  "summary": {
    "lb_summary": [
      { "lb_number": 810, "given": 18, "matched": 18, "not_found": 0,
        "missing_from_set": 0, "duplicates": 0, "xrefs": 0,
        "status": "MATCHED", "lb_status": "public" }
    ],
    "matched": 18, "given": 18, "lb_numbers_found": [810]
  },
  "detail": [
    { "checksum": "...", "filename": "d01t01.flac", "type": "f",
      "lb_number": 810, "xref": 0, "status": "MATCHED",
      "source_file": "/path/to/file.ffp", "db_filename": "d01t01.flac",
      "lb_status": "public" }
  ]
}
```

`status` values: `"MATCHED"`, `"MATCHED (INCOMPLETE)"`, `"DUPLICATE"`, `"NOT FOUND"`, `"XREF"`

### Wiring gaps

| Stub | Endpoint / IPC | Legacy pattern (lookup_tab.py) |
|---|---|---|
| "Clipboard" source button | `navigator.clipboard.readText()` → `POST /api/lookup {text}` | `_on_clipboard_lookup` L1168: `QApplication.clipboard().text()` |
| "Listbox…" source button | Modal textarea → `POST /api/lookup {text}` | `_on_listbox_lookup` L1176 |
| "Files…" source button | `pickFile` IPC (multi) → read file content → `POST /api/lookup {text}` | `_on_add_files` L629 + `_LookupWorker` L131 |
| "Folders…" source button | `pickFolders` IPC → glob `.ffp/.md5/.st5` files in each folder → `POST /api/lookup {text}` | `_on_add_folders` L635 + `_add_path` L570 globs folder children |
| "Lookup all sources" button | Re-run `POST /api/lookup` with all loaded file contents concatenated | `_on_listbox_lookup` L1176 |
| "Generate missing" button | `POST /api/verify/generate {folders: [...]}` | `_on_generate_checksums` L978; `_GenerateWorker` L203 |
| "Clear sources" button | Clear source list and result state | `_on_clear_list` L750 + `_on_clear_results` L757 |
| Filter checkbox (_mychecksums) | Client-side filter on source list | `_toggle_filter` L805; `_refresh_listbox` L602 |
| Summary status filter chips | Client-side filter — `_lb_status_filter` + `_best_match_only` | `_apply_filters` L901 |
| "Copy summary" button | `navigator.clipboard.writeText(tsvText)` | `_on_detail_context` L1441: `copy_chk` / `copy_row` QActions |
| "Export CSV…" button | Blob download, same pattern as ScreenSearch/ScreenBootlegs | No direct legacy equivalent — new feature |
| "Open" button per summary row | `window.open(losslessbob_url)` | `_on_summary_double_click` L1412: `webbrowser.open(url)` |
| "Re-lookup all" button | Re-run `POST /api/lookup` over all loaded sources | Same as "Lookup all sources" |
| "Go to Rename →" button | `navigate('/rename')` — pass lookup result via `useLookupStore` | `lookup_completed` signal L334 emitted to main_window → RenameTab |
| "Confirm matches" button | Not in legacy GUI — consider omitting or wiring to wishlist/collection action | — |
| "Mark as new entry…" button | Not in legacy GUI — curator-only, skip for now | — |
| Add to Wishlist (right-click) | `POST /api/wishlist {lb_number}` | `_add_to_wishlist` L1135 |

### Key architectural note — cross-tab state

In the old GUI, `LookupTab` emits a `lookup_completed` signal (L334) carrying `(detail_list, folder_list)`. `MainWindow` connects that signal to `RenameTab.populate_from_lookup()`. In the new GUI this cross-screen data flow must use the **Zustand store** — add a `useLookupStore` slice holding `{detailList, folderList}`. ScreenRename subscribes to that slice.

### Scan-tree pattern (from `_ScanTreeWorker`, lookup_tab.py:177)

The old GUI walks a directory tree client-side (Python, off main thread) to find `.ffp/.md5/.st5` files. In the new GUI two approaches are possible:
- **Option A (simpler):** `pickFolders` IPC picks individual folders; user adds them one at a time. Tree-walk via `POST /api/pipeline/scan-tree` already exists for audio-folder discovery.
- **Option B (faithful port):** Add a new `POST /api/lookup/scan-tree {root}` route that walks the tree for checksum files and returns them as a list. The old `_ScanTreeWorker` logic is 18 lines and trivially portable to a Flask route.

---

## 3. ScreenVerify — 0% wired

**Legacy:** `gui/verify_tab.py` — complete implementation.

### API contracts (from verify_tab.py workers)

`POST /api/verify {folders: [...]}` → `{results: [{folder, mode, status, total, pass, mismatch, missing, extra, missing_types, files: [{filename, md5_status, ffp_status, shntool_status, st5_status, on_disk, overall, md5_expected, md5_actual, ffp_expected, ffp_actual}]}]}`

`status` values per folder: `"pass"`, `"fail"`, `"incomplete"`, `"shntool_missing"`, `"no_checksums"`

`POST /api/verify/generate {folders: [...]}` → `{results: [{folder, generated: [...], skipped: [...], errors: [...]}]}`

`POST /api/lbdir/retrieve {folders: [...]}` → `{results: [{folder, lb_number, status, msg}]}`

`status` values per result: `"copied"`, `"scraped_and_copied"`, `"not_found"`, `"no_lb_number"`

### Wiring gaps

| Stub | Endpoint / IPC | Legacy pattern (verify_tab.py) |
|---|---|---|
| "Add folders…" / "Add root folder…" | `pickFolders` IPC → append to local `folders` state | `_on_add_folders` L320; `_on_add_root_folder` L326 |
| "Add root folder" tree-walk | `_AddRootWorker` L90 walks tree for audio subfolders (client-side Python). In new GUI: either renderer-side or call a new backend route. `POST /api/pipeline/scan-tree` already returns audio folders for a root dir. | `_AddRootWorker.run` L106 |
| Tool status dots (FFP/MD5/shntool) | `GET /api/spectrogram/check` → `{sox_available, ffmpeg_available, shntool_available, flac_available}` | `gui/setup_tab.py` calls same route |
| "Verify all folders" button | `POST /api/verify {folders: [...]}` → update result state | `_on_verify` L407; `_VerifyWorker` L25 |
| "Generate checksums" button | `POST /api/verify/generate {folders: [...]}` → on success, auto-re-verify | `_on_generate` L452; auto-calls `_start_verify` on done L482 |
| "Retrieve from LB" button | `POST /api/lbdir/retrieve {folders: [...]}` → if any copied, auto-re-verify | `_on_retrieve` L486; `_RetrieveWorker` L69 |
| Folder summary table | Populated from `POST /api/verify` response `.results` array | `_populate_summary` L544 |
| File detail table | Populated by clicking a summary row, using cached `_verify_results[row]` | `_on_summary_row_clicked` L608 |
| "Show all files" toggle | Client-side filter: hide rows where `overall === "pass"` | `_on_show_all_changed` L615; `_populate_detail` L627 |
| "Open in Finder" button | `window.api.openPath(folder)` | Not in legacy Verify tab; in LBDir tab |
| "Copy report" button | `navigator.clipboard.writeText(text)` — format as `_populate_detail` rows | Not in legacy Verify tab |
| "Generate missing FFP" button | Same as "Generate checksums" — `POST /api/verify/generate` | Same worker |
| "Mark verified" button | Likely `PATCH /api/collection/<lb> {confirmed_at: now}` — clarify with user | Not in legacy Verify tab |
| "Verify without shntool" button | `POST /api/verify` — backend already handles absence of shntool gracefully (`shntool_missing` status) | Implicit — the route just runs without shntool |
| "Install shntool…" button | Show install-instructions modal — no backend call | Not applicable |

---

## 4. ScreenRename — 0% wired

**Legacy:** `gui/rename_tab.py` — complete implementation.

### Critical architectural finding: renames happen server-side in new GUI

The old `_on_rename` (rename_tab.py:721) calls:
1. `shutil.move(str(src), str(final_dst))` — direct filesystem op
2. `write_rename_log(folder_path, old_name, new_name, source="rename_tab", lb_number)` — direct Python import

The Electron frontend **cannot** call Python functions directly. A `POST /api/rename/apply` route is needed (see §1). This is the **only genuinely missing backend route** required by this screen.

### Proposal-building logic (from `populate_from_lookup`, rename_tab.py:596)

The old GUI builds proposed names locally without any API call per folder. The logic:
1. From the lookup `detail_list`, group checksums by `source_file` parent → folder
2. For each folder, collect `{lb_number: xref_value}` from `MATCHED`/`MATCHED (INCOMPLETE)` entries
3. Single candidate → `proposed = f"{folder_name}-{lb_str}"` (just appends suffix)
4. Multiple candidates → call `GET /api/folder_link?path=...` then `GET /api/lb_alias/resolve?lbs=...`
5. Calls `apply_nft_suffix(proposed, lb_status)` from `backend.folder_naming` — this is pure string logic, easily ported to TypeScript

The `GET /api/folder_naming/standard/<lb>` Flask route exists but is not used here; it's for building canonical `YYYY-MM-DD Location (LB-XXXXX)` names. That's an optional enhancement ("Standardize" button).

### Wiring gaps

| Stub | Endpoint / IPC | Legacy pattern (rename_tab.py) |
|---|---|---|
| Folder proposal list | Read from `useLookupStore.detailList` + `useLookupStore.folderList` | `populate_from_lookup` L596 called via signal |
| "Re-resolve from Lookup" button | Re-run `populate_from_lookup` logic against current store state | Re-triggers same signal connection |
| Multi-ID disambiguation → `GET /api/folder_link` | `GET /api/folder_link?path=<encoded_path>` | `_resolve_single_lb` L555: `self._api(f"/api/folder_link?path={...}")` |
| Multi-ID disambiguation → `GET /api/lb_alias/resolve` | `GET /api/lb_alias/resolve?lbs=1,2,3` | `_resolve_single_lb` L583: `self._api(f"/api/lb_alias/resolve?lbs=...")` |
| "Apply X renames" button | **NEW** `POST /api/rename/apply {renames: [{old_path, new_path, lb_number}]}` | `_on_rename` L721: `shutil.move` + `write_rename_log` (direct) |
| "Pin selection · update folder_lb_link" | `PUT /api/folder_link {folder_path, lb_number}` | `_api_put("/api/folder_link", {...})` L1079 |
| "Unlink" (clear folder_lb_link) | `DELETE /api/folder_link?path=<encoded>` | `_api_delete(f"/api/folder_link?path={...}")` L1123 |
| NFT suffix logic (`-NFT` append/strip) | Port `apply_nft_suffix` / `strip_nft_suffix` to TypeScript (~20 lines of regex) | `backend/folder_naming.py`: `apply_nft_suffix`, `strip_nft_suffix` |
| "Standardize" button | `GET /api/folder_naming/standard/<lb>` per selected row | `_on_standardize_selected` L873: calls `build_standard_name` locally |
| "Copy diff…" button | `navigator.clipboard.writeText(diffText)` | No legacy equivalent |
| "Export plan…" button | `window.api.saveFile(content, 'rename_plan.txt')` | No legacy equivalent |
| LB.com row link | `window.open(url)` | `_on_summary_double_click` L1412 |

---

## 5. ScreenLBDIR — 0% wired

**Legacy:** `gui/lbdir_tab.py` — complete implementation with all four sub-tabs.

### API contracts (from lbdir_tab.py workers)

All routes already exist in `backend/app.py`. Workers:

| Worker | Route | Timeout |
|---|---|---|
| `_LbdirCheckWorker` (L42) | `POST /api/lbdir/check {folders: [...]}` | 600s |
| `_LbdirRetrieveWorker` (L65) | `POST /api/lbdir/retrieve {folders: [...]}` | 120s |
| `_LbdirReconcileWorker` (L86) | `POST /api/lbdir/reconcile {folders: [...]}` | 300s |
| `_LbdirApplyReconcileWorker` (L107) | `POST /api/lbdir/apply_reconcile {folder, renames: [...]}` | 120s |
| `_LbdirFindExtraWorker` (L129) | `POST /api/lbdir/find_extra {folders: [...]}` | 120s |
| `_LbdirDeleteExtraWorker` (L150) | `POST /api/lbdir/delete_extra {folder, files: [...]}` | 120s |

### Check pane response format

`POST /api/lbdir/check` returns per-folder:
```json
{ "folder": "/path", "lb_number": 810, "lbdir_found": true, "lbdir_path": "...",
  "mode": "shn", "status": "pass|fail|missing_files|no_lbdir|no_lb",
  "total": 18, "pass": 15, "mismatch": 0, "missing": 3,
  "files": [
    { "filename": "d01t01.shn", "md5_status": "pass", "on_disk": true, "overall": "pass",
      "length": "4:42.20", "expanded_size": "49.7 MB", "cdr": true,
      "wave_problems": "—", "fmt": "SHN", "ratio": "0.62" }
  ]
}
```

### Wiring gaps

| Stub | Endpoint | Legacy pattern (lbdir_tab.py) |
|---|---|---|
| "Add folders…" / "Add root folder…" | `pickFolders` IPC | Same as ScreenVerify |
| shntool/attachments status indicators | `GET /api/spectrogram/check` + `GET /api/attachments/cached` | Inline checks at tab load |
| **Check pane — "Check all folders"** | `POST /api/lbdir/check {folders: [...]}` | `_LbdirCheckWorker` L42 |
| **Check pane — "Re-check this folder"** | `POST /api/lbdir/check {folders: [currentFolder]}` | Same worker, single folder |
| **Check pane — "Open lbdir.txt"** | `window.api.openPath(lbdir_path)` | `webbrowser.open` in detail double-click |
| Check pane summary stats | From `POST /api/lbdir/check` response | `_populate_summary` in lbdir_tab.py |
| Check pane file table | From `response.files` array | `_populate_detail` in lbdir_tab.py |
| Shntool side panel fields | From per-file `length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio` | `INFO_FIELDS` L32 in lbdir_tab.py |
| **Retrieve pane — "Retrieve missing lbdir"** | `POST /api/lbdir/retrieve {folders: [...]}` | `_LbdirRetrieveWorker` L65 |
| Retrieve pane result table | From `POST /api/lbdir/retrieve` response | `_on_retrieve_done` in lbdir_tab.py |
| Retrieve "Run Lookup" button | `navigate('/lookup')` | Tab switch in old GUI |
| **Reconcile pane — "Re-scan disk"** | `POST /api/lbdir/reconcile {folders: [...]}` | `_LbdirReconcileWorker` L86 |
| **Reconcile pane — "Apply N renames"** | `POST /api/lbdir/apply_reconcile {folder, renames: [...]}` | `_LbdirApplyReconcileWorker` L107 |
| **Extras pane — extras list** | `POST /api/lbdir/find_extra {folders: [...]}` | `_LbdirFindExtraWorker` L129 |
| **Extras pane — "Delete N"** | `POST /api/lbdir/delete_extra {folder, files: [...]}` | `_LbdirDeleteExtraWorker` L150 |

---

## 6. ScreenAttachments — 0% wired

**Legacy:** `gui/attachments_tab.py` — complete implementation.

### API contracts (from attachments_tab.py workers)

`_RefreshTreeThread` (attachments_tab.py:78):
1. `POST /api/attachments/reconcile` → `{updated: N}` — syncs `entry_files.downloaded` with disk
2. `GET /api/attachments/cached` → `{entries: [{lb_number, files: [{filename, clean_name}], lb_status}], total: N}`

`_ScrapeThread` (attachments_tab.py:106): `POST /api/entry/<lb>/scrape {force: true}`

File serving (existing route): `GET /api/attachment/<lb>/<filename>` — returns raw file bytes with correct Content-Type.

### Wiring gaps

| Stub | Endpoint / IPC | Legacy pattern (attachments_tab.py) |
|---|---|---|
| "Refresh tree" button | `POST /api/attachments/reconcile` → `GET /api/attachments/cached` → populate LB rail | `_RefreshTreeThread` L78 |
| LB rail list | From `GET /api/attachments/cached` response `.entries` | `_on_tree_refreshed` populates `_LbModel` |
| Aggregate counts (N current/stale/missing) | From `GET /api/attachments/cached` response | Model uses `lb_status` per entry for color-coding |
| LB status classification | `lb_status` from `GET /api/attachments/cached`; 'current' = `downloaded=1`, 'stale' = older scrape, 'missing' = 0 files | `_LbModel.data` L43 |
| File list for active LB | `GET /api/entry/<lb>/files` → `[{filename, clean_name, downloaded}]` | `_FileModel` / file list click in attachments_tab.py |
| "Re-download LB-X" button | `POST /api/entry/<lb>/scrape {force: true}` | `_ScrapeThread` L106 |
| "Open folder…" button | `window.api.openPath(data_dir + "/attachments/LB-" + lb + "/")` | `attachment_path(lb)` from `backend.paths` |
| File viewer (text) | `GET /api/attachment/<lb>/<filename>` → render as `<pre>` | `QTextEdit.setPlainText(content)` |
| File viewer (HTML) | `GET /api/attachment/<lb>/<filename>` → render in `<iframe>` (sandbox) | `QWebEngineView` in old GUI |
| File viewer (image) | `<img src="{BASE}/api/attachment/{lb}/{filename}">` — the route serves bytes | `QPixmap` from response bytes |
| "Cache missing" button | `POST /api/entry/<lb>/scrape {force: false, download_files: true}` in batch over all entries with `downloaded < total` | Not in legacy GUI as a bulk action — new feature |
| "Copy contents" button | Fetch text content → `navigator.clipboard.writeText(text)` | `QTextEdit.selectAll` + copy |
| "Open externally" button | `window.api.openPath(local_file_path)` | `QDesktopServices.openUrl` |
| LB search input | Client-side filter on LB rail list | `QLineEdit` text filter in attachments_tab.py |

---

## 7. ScreenSpectrograms — 0% wired

**Legacy:** `gui/spectrogram_tab.py` — complete implementation.

### API contracts (from spectrogram_tab.py)

| Route | Direction | Description |
|---|---|---|
| `GET /api/spectrogram/check` | On mount | `{sox_available, sox_version, ffmpeg_available, shntool_available, flac_available}` |
| `POST /api/spectrogram/list {folders: [...]}` | On folder add / re-scan | Returns `{folder_path: [{audio_file, audio_name, png_path, has_png}]}` |
| `POST /api/spectrogram/generate {folders, width, height, dyn_range, force}` | Generate button | Starts batch; returns immediately |
| `GET /api/spectrogram/status` | **Polled every 800ms** | `{status, current, done, total, errors, skipped, stop_requested}` |
| `POST /api/spectrogram/stop` | Stop button | Returns immediately |

**Polling pattern** (spectrogram_tab.py:924): The old GUI uses a `QTimer` polling `GET /api/spectrogram/status` every 800ms after generation starts, stopping when `stop_requested` or `status !== "running"`. In React: `useEffect` with `setInterval(800)`, cleared in cleanup.

**PNG display**: The old GUI loads PNG bytes from disk via `QPixmap(png_path)`. The new GUI should serve the file through Flask: `GET /api/attachment/<lb>/<filename>` can serve spectrogram PNGs if they're in the attachments directory, or add a dedicated route `GET /api/spectrogram/png?path=<encoded>` for arbitrary paths.

### Wiring gaps

| Stub | Endpoint / IPC | Legacy pattern (spectrogram_tab.py) |
|---|---|---|
| "Add folder…" button | `pickFolders` IPC → local folders state | `_DropFolderList` + `QFileDialog` |
| SoX/ffmpeg version / tool dots | `GET /api/spectrogram/check` on mount | L749 in spectrogram_tab.py |
| Folder rail list | `POST /api/spectrogram/list {folders: [...]}` → per-folder track inventory | L749 |
| Track rail list (per folder) | From `POST /api/spectrogram/list` response | Same response, nested |
| Batch progress stats | `GET /api/spectrogram/status` polled at 800ms | L924: QTimer.timeout → status poll |
| "Generate missing" button | `POST /api/spectrogram/generate {folders, width, height, dyn_range, force: false}` → start 800ms poll | L872 |
| "Stop after current" button | `POST /api/spectrogram/stop` | L912 |
| "Re-scan inventory" button | `POST /api/spectrogram/list {folders: [...]}` again | Same as initial load |
| "Re-render" button (single track) | `POST /api/spectrogram/generate {folders: [currentFolder], force: true}` → start poll | L893 |
| Spectrogram canvas (actual PNG) | `<img src="{BASE}/api/attachment/{lb}/{png_name}">` or dedicated serve route | `_ImageViewer.load(png_path)` L117: `QPixmap(png_path)` |
| "Open PNG" button | `window.api.openPath(png_path)` | `QDesktopServices.openUrl` |
| Render options (width/height/dB) | State → body of `POST /api/spectrogram/generate` | Spinboxes in `_render_options_group` |
| "Force re-render" checkbox | `force: true` in generate body | `QCheckBox` → `force` param |
| Zoom controls | Client-side CSS `transform: scale(N)` on `<img>` | `_ImageViewer` zoom/pan widget L58 |
| Thumbnail strip | `<img>` per track where `has_png === true` | Thumbnail list built from `/api/spectrogram/list` response |

---

## 8. Partially Wired Screens — Remaining Gaps

### ScreenCollection (~11% remaining)

| Gap | Endpoint / IPC | Legacy pattern |
|---|---|---|
| Wishlist add | `POST /api/wishlist {lb_number}` | `lookup_tab.py:_add_to_wishlist` L1135 |
| Wishlist remove | `DELETE /api/wishlist/<lb>` | `gui/main_window.py` wishlist toggle |
| Batch-remove progress bar | Show per-item progress during DELETE loop | No legacy equivalent — new UX |
| "My Collection" nav tab count badge | Read `rows.length` from store / pass via context | No direct equivalent — new UX |

### ScreenHome (~20% remaining)

Both `/api/home/stats` and `/api/activity/log` routes already exist (§1). The frontend just needs to call them — the gap is only in the React component, not the backend.

### ScreenBootlegs (~2% remaining)

"Refresh LBBCD" fires `POST /api/bootlegs/scrape` but the `.then()` chain is missing — response is silently ignored. Add `.then(r => r.json()).then(d => showToast(d.ok ? 'Scrape started' : d.error, d.ok ? 'info' : 'bad'))`.

### ScreenSetup (~3% remaining)

`GET /api/master/status` exists at line 2963 — the route is there but the frontend component silently swallows the 404 during an early test. Now just needs the call to succeed. `POST /api/master/github_release` is still missing and needs design before implementation.

---

## 9. Suggested Implementation Order

### Priority 1 — Fix ScreenHome (trivial — routes already exist)

Both `/api/home/stats` and `/api/activity/log` exist; the screen just needs to call them. 30-minute fix. Unblocks the dashboard from showing live data.

### Priority 2 — ScreenLookup (core feature, blocks Rename)

1. Add `useLookupStore` Zustand slice: `{detailList, folderList, sources}`
2. Wire all four source buttons (clipboard, listbox, files, folders) to `POST /api/lookup`
3. Replace static `SOURCES/SUMMARY/DETAIL` with state derived from the API response
4. Emit results to store so ScreenRename can consume them
5. Port the "Add to Wishlist" right-click action via `POST /api/wishlist`

### Priority 3 — ScreenVerify (ingest workflow step 1)

1. Wire folder queue to IPC pickers (+ `POST /api/pipeline/scan-tree` for root folder)
2. Wire tool dots to `GET /api/spectrogram/check`
3. Wire "Verify all" → `POST /api/verify` → populate summary + detail tables
4. Wire "Generate" → `POST /api/verify/generate` → auto-re-verify on completion
5. Wire "Retrieve from LB" → `POST /api/lbdir/retrieve` → auto-re-verify on completion

### Priority 4 — `POST /api/rename/apply` (backend only, ~1 hour)

Create the route in `backend/app.py`: accept `{renames: [{old_path, new_path, lb_number}]}`, loop calling `shutil.move` and `backend.rename.write_rename_log`, return `{applied, errors}`.

### Priority 5 — ScreenRename (ingest workflow step 2 — depends on P2 + P4)

1. Consume `useLookupStore` for proposal generation
2. Port proposal-building logic from `populate_from_lookup` (rename_tab.py:596) to TypeScript
3. Port `apply_nft_suffix` / `strip_nft_suffix` from `backend/folder_naming.py` to TypeScript (~20 lines)
4. Wire disambiguation calls: `GET /api/folder_link`, `GET /api/lb_alias/resolve`
5. Wire "Apply renames" → `POST /api/rename/apply`
6. Wire "Pin selection" → `PUT /api/folder_link`

### Priority 6 — ScreenLBDIR (ingest workflow step 3)

1. Wire folder queue to IPC pickers
2. Wire Check pane → `POST /api/lbdir/check` + result state
3. Wire Retrieve pane → `POST /api/lbdir/retrieve`
4. Wire Reconcile pane → `POST /api/lbdir/reconcile` + `POST /api/lbdir/apply_reconcile`
5. Wire Extras pane → `POST /api/lbdir/find_extra` + `POST /api/lbdir/delete_extra`

### Priority 7 — ScreenAttachments (supporting / browsing)

1. Wire "Refresh tree" → `POST /api/attachments/reconcile` → `GET /api/attachments/cached`
2. Wire LB rail from cached response; wire file list → `GET /api/entry/<lb>/files`
3. Wire file viewer → `GET /api/attachment/<lb>/<filename>` (text/HTML/image branches)
4. Wire "Re-download" → `POST /api/entry/<lb>/scrape {force: true}`
5. Wire "Open folder" → `window.api.openPath`

### Priority 8 — ScreenSpectrograms (supporting / analysis)

1. Wire tool dots → `GET /api/spectrogram/check` on mount
2. Wire folder queue → IPC + `POST /api/spectrogram/list`
3. Wire generate/stop → `POST /api/spectrogram/generate` + 800ms poll + stop
4. Wire PNG display as `<img>` served through Flask
5. Wire render options form → params on generate body

### Priority 9 — Remaining minor gaps

- ScreenCollection: wishlist toggle buttons, progress bar during batch-remove, tab count badge
- ScreenBootlegs: add `.then()` to scrape response
- ScreenSetup: `GET /api/master/status` call already exists — verify it resolves cleanly now

---

## 10. New Routes Required Summary (revised)

Only **two** routes are genuinely absent from `backend/app.py`:

| Route | Method | Priority |
|---|---|---|
| `/api/rename/apply` | POST | P4 — needed before ScreenRename can be wired |
| `/api/master/github_release` | POST | Low — curator-only, needs design first |

All other routes listed in the original audit already exist. Before starting any screen wiring, verify the relevant routes against the line numbers in §1 above.
