# Plan: Systematically Wire New GUI Screens to Backend

## Context
The new Electron/React GUI (`gui_next/`) has 7 screens, many with buttons and controls that are
UI stubs (`console.log`, no handler, or empty function). The old PyQt6 GUI (`gui/`) and the Flask
backend (`backend/app.py`) already implement all the underlying functionality — the gap is purely
the wiring layer in the new frontend. This plan audits every stub and maps it to the correct
backend endpoint or IPC call, then implements the connections screen by screen in priority order.

## Audit Summary

| Screen | Wired | Total | % | Status |
|---|---|---|---|---|
| ScreenSetup | 16 | 16 | 100% | **✓ done 2026-05-27** |
| ScreenCollection | 32 | 36 | ~89% | **✓ done 2026-05-28** |
| ScreenSearch | 18 | 19 | ~95% | **✓ done 2026-05-28** |
| ScreenHome | 10 | 10 | 100% | **✓ done 2026-05-28** |
| ScreenPipeline | 19 | 20 | 95% | pre-existing |
| ScreenBootlegs | 14 | 14 | 100% | **✓ done 2026-05-28** |
| ScreenThemes | 9 | 9 | 100% | **✓ done 2026-05-28** |

**ScreenCollection remaining ~11%:** wishlist add/remove actions; batch-remove progress bar; tab count badge.  
**ScreenSearch remaining ~5%:** "More options" toolbar item (stub toast — intentional for now).  
**ScreenPipeline remaining 5%:** one pre-existing stub not yet identified.

---

## Implementation Order (most broken / most foundational first)

### ~~Sprint 1 — ScreenSetup (6% → 100%)~~ **DONE 2026-05-27**
All stubs wired. New backend routes added: `POST /api/credentials/wtrf`, `POST /api/credentials/qbt`,
`POST /api/rename_history/purge`, `POST /api/flat_file/purge`, `POST /api/scraper/purge`,
`POST /api/fingerprint/purge`. `data_dir` added to `/api/db/settings` GET. `flac_available` added
to `/api/spectrogram/check`. `pickFile` IPC added to main/preload. Correct "Install" endpoint is
`/api/master/import` (plan doc had incorrect `/api/master/export`).

| Stub | Endpoint | Method | Notes |
|---|---|---|---|
| Publish master update | `/api/master/export` → `/api/master/github_release` | POST | Two-step; confirm dialog |
| Install master update | `pickFile` IPC → `/api/master/import` | POST | Confirm dialog |
| Import DB file | `/api/db/import` | POST | File picker IPC → upload; poll `/api/db/import/status` |
| Check for update | GitHub Releases API | GET | Same logic as old `setup_tab.py` |
| Open data folder | `window.api.openPath(dataDir)` | IPC | Get `dataDir` from `/api/db/settings` GET |
| Reset DB | `/api/db/reset` | POST | Confirm dialog before firing |
| qBt Test | `/api/qbt/test` | POST | Show pass/fail inline |
| qBt Edit (save) | `/api/db/settings` | POST | Fields: host, port, category, tags |
| Forum (WTRF) Test | `/api/wtrf/test` | POST | Show pass/fail inline |
| Forum Edit (save) | keyring via `/api/db/settings` | POST | Username/password |
| Helpers Re-check | `/api/spectrogram/check` | GET | Show sox/ffmpeg/shntool status |
| Results per page | `/api/db/settings` | POST | Key: `search_page_size` |
| Auto-scrape on import | `/api/db/settings` | POST | Key: `auto_scrape` |
| Data purge buttons (×5) | Various DELETE endpoints | DELETE | Confirm dialog each |
| Flat file history Reveal | `/api/flat_file/releases` + `window.api.openPath` | GET+IPC | Load on mount |

**New IPC needed:** None beyond what Pipeline already uses.
**New API needed:** None — all endpoints exist.

---

### ~~Sprint 2 — ScreenCollection (33% → ~90%)~~ **DONE 2026-05-28**
All 17 stubs wired. Added `lbNumberInt` and `isXref` fields to `CollectionRow`. Year filter
uses `/api/search/years` + client-side filtering (dropdown popover). Xref filter uses
`/api/checksums/xref_lb_numbers` + client-side checkbox. Add single folder and both scan
buttons share one `AddFolderModal` (per-row LB# input + Add button). Forum post opens a
`ForumModal` with editable subject + BBCode body before calling `preview_forum` → `post_forum`.
`version`-bump `refetch()` pattern established for post-mutation reload.

| Stub | Endpoint | Method | Notes |
|---|---|---|---|
| All years filter | `/api/search/years` | GET | Fetched on mount; popover dropdown; client-side filter |
| Xref only checkbox | `/api/checksums/xref_lb_numbers` | GET | Fetched on mount; client-side filter on `isXref` field |
| Add single folder | `pickFolders` IPC → `POST /api/collection` | POST | `AddFolderModal` with LB# input per folder |
| Scan directory | `pickDir` IPC → `/api/pipeline/scan-tree` | POST | Reuses same `AddFolderModal` |
| Scan tree | `pickDir` IPC → `/api/pipeline/scan-tree` | POST | Same as Scan directory |
| Update location | `pickDir` IPC → `PATCH /api/collection/<lb>` | PATCH | Updates `disk_path` + `folder_name`; single-row only |
| Remove | `DELETE /api/collection/<lb>` | DELETE | Confirm dialog; acts on checked rows or selected row |
| Export HTML | `/api/collection/export/html` | GET | Blob download → `collection.html` |
| Export M3U | `/api/collection/export/m3u` | GET | Blob download → `collection.m3u` |
| Create torrent | `/api/torrent/create` | POST | Batch over checked/selected rows; needs `disk_path` |
| Add to qBittorrent | `/api/qbt/add` | POST | `{lb_numbers:[...]}` for checked/selected rows |
| Reveal on disk | `window.api.openPath(diskPath)` | IPC | Uses `disk_path` from row |
| Attachments | — | — | Toast: "Attachments screen coming soon" |
| Spectrograms | — | — | Toast: "Spectrograms screen coming soon" |
| On map | — | — | Toast: "Map screen coming soon" |
| Regenerate torrent | `/api/torrent/create` | POST | Detail panel; uses selected row's lb + disk_path |
| Post to forum | GET `/api/entry/<lb>/preview_forum` → POST `.../post_forum` | GET+POST | `ForumModal` with editable subject + BBCode body |

**New IPC needed:** None.
**New API needed:** None — all endpoints existed.
**Remaining ~10%:** Wishlist add/remove flows; `My Collection` tab count badge; batch-remove progress bar.

---

### ~~Sprint 3 — ScreenSearch (69% → ~95%)~~ **DONE 2026-05-28**
All stubs wired. `owned` field fixed (fetches real collection data from `/api/collection/lb_numbers`).
Client-side sort (6 options via popover). CSV export (Blob download). Group-by-year toggle (active state on button).
Column visibility popover (localStorage persistence). Saved views (localStorage, built-in + user-created with delete). 
Detail panel (fetches `/api/entry/<lb>`, shows date/location/description/setlist/files, Scrape entry action).
Per-row ⋯ menu (position:fixed, Scrape entry action). Toast component added.

| Stub | Endpoint/Action | Notes |
|---|---|---|
| Table row click | `/api/entry/<lb>` | Shows `EntryDetailPanel` side panel; toggle on re-click |
| Sort dropdown | client-side sort on `sortedRows` | 6 sort options; popover with active highlight |
| Export CSV | client-side Blob download | Exports `sortedRows` (post-filter, post-sort) |
| Group by year | client-side `groupByYear` toggle | Button shows accent highlight when active |
| Columns visibility | client-side `visibleCols` Set | Popover with checkboxes; localStorage persistence |
| Saved views | localStorage `lbb_search_views` | 3 built-in + user-created; apply/delete |
| More options (toolbar) | toast | "Additional options coming in a future update" |
| Per-row ⋯ | `POST /api/entry/<lb>/scrape` | position:fixed dropdown; "Scrape entry" action |
| `owned` field | `/api/collection/lb_numbers` | Fetched on mount; refreshed after collection changes |

---

### ~~Sprint 4 — ScreenHome (70% → 100%)~~ **DONE 2026-05-28**
Both stubs wired. New backend route `/api/activity/log` added — aggregates `flat_file_releases` (applied),
`rename_history`, and `forum_posts` into a unified feed sorted by timestamp; supports `?limit=N` (0 = all).
"Check for DB update" calls `/api/flat_file/discover` (same as Setup). "View full log" opens a modal
fetching `?limit=0`. Recent activity table shows real rows with colour-coded type dots.

| Stub | Endpoint | Notes |
|---|---|---|
| Check for DB update | `/api/flat_file/discover` | Busy state + toast (same pattern as Setup) |
| View full log | `/api/activity/log?limit=0` | Full-log modal; new endpoint added to app.py |

---

### ~~Sprint 5 — ScreenBootlegs (79% → 100%)~~ **DONE 2026-05-28**
All stubs wired. Year filter popover derived from loaded rows (sorted descending), outside-click close,
active-highlight on button. CDs popover (All / 1 CD / 2 CDs / 3+). Both filters integrated into
filteredRows useMemo and clearFilters. Export CSV Blob-downloads `filteredRows` as
`losslessbob_bootlegs.csv` (columns: LB#, Title, Date, Year, Location, CDs, Status, Owned).

| Stub | Action | Notes |
|---|---|---|
| Year filter button | client-side filter on `year` field | Popover with year list derived from loaded rows; active highlight |
| CDs filter button | client-side filter on `cdCount` field | Popover: All / 1 CD / 2 CDs / 3+ CDs |
| Export CSV | client-side Blob download of `filteredRows` | Same pattern as ScreenSearch CSV export |

---

### ~~Sprint 6 — ScreenThemes (~44% → 100%)~~ **DONE 2026-05-28**
All stubs wired. `Font`/`FontSize`/`customTokens` added to `ThemeOptions`; `applyTheme` sets `--lbb-font` and `--lbb-font-size` CSS vars; `index.css` drives `font-family`/`font-size` from CSS vars. Typeface buttons wire `setTweak('font', k)` with per-button font preview and active highlight. Font size 12/13/14pt are real buttons. Custom token editor opens inline below "Custom color tokens…" button — 7 CSS token rows (bg, surface, surface2, border, fg, fg2, fg3), color inputs, per-token reset, reset-all. Export/Import use new `dialog:saveFile` / `dialog:pickAndReadFile` IPC. Toast component added locally.

| Stub | Action | Notes |
|---|---|---|
| Typeface buttons (3) | `setTweak('font', k)` → `--lbb-font` CSS var | `Font` type + `FONT_STACKS` in tokens.ts; active border + check icon |
| Font size buttons (3) | `setTweak('fontSize', n)` → `--lbb-font-size` CSS var | Replaced static `<p>` with 3 toggle buttons |
| Custom color tokens | `CustomTokenEditor` inline panel | 7 tokens; color inputs; per-token reset; reset-all; localStorage via saveTheme |
| Export theme JSON | `window.api.saveFile(json, 'losslessbob-theme.json')` | New `dialog:saveFile` IPC (showSaveDialog + fs.writeFile) |
| Import theme JSON | `window.api.pickAndReadFile` → parse + apply | New `dialog:pickAndReadFile` IPC (showOpenDialog + fs.readFile) |

**New IPC added:** `dialog:saveFile` and `dialog:pickAndReadFile` in `main/index.ts` + `preload/index.ts`.

---

## Critical Files

| File | Sprint |
|---|---|
| `gui_next/src/renderer/src/screens/ScreenSetup.tsx` | 1 ✓ |
| `gui_next/src/renderer/src/screens/ScreenCollection.tsx` | 2 ✓ |
| `gui_next/src/renderer/src/screens/ScreenSearch.tsx` | 3 ✓ |
| `gui_next/src/renderer/src/screens/ScreenHome.tsx` | 4 ✓ |
| `gui_next/src/renderer/src/screens/ScreenBootlegs.tsx` | 5 ✓ |
| `gui_next/src/renderer/src/screens/ScreenThemes.tsx` | 6 ✓ |
| `gui_next/src/preload/index.ts` | 6 ✓ |
| `gui_next/src/main/index.ts` | 6 ✓ |

## Reusable Patterns (established in Sprints 1–2)

1. **Progress-polling job** — POST to start → poll status endpoint every 500ms → progress bar → clear on done/error
2. **Settings save** — POST to `/api/db/settings` with `{key, value}` → toast on success/error
3. **Confirm-then-DELETE** — modal confirm dialog → DELETE → refresh list
4. **File-download response** — GET blob → synthetic `<a>` click → `URL.revokeObjectURL`
5. **Version-bump refetch** — `const [version, setVersion] = useState(0)` + `useEffect([version])` + `refetch = () => setVersion(v => v+1)`
6. **Bulk action target** — checked rows first, fall back to selected row; show "Select rows first" toast if neither

## Verification (each sprint)

1. `npm run dev` in `gui_next/` — start backend + Electron dev mode
2. Exercise every previously-stubbed button manually
3. Check devtools Network tab for correct endpoint calls and 2xx responses
4. Check Flask logs for matching request receipt
5. Confirm state updates (list refreshes, toasts, progress bars) work end-to-end
