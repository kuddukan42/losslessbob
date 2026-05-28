# Plan: Systematically Wire New GUI Screens to Backend

## Context
The new Electron/React GUI (`gui_next/`) has 7 screens, many with buttons and controls that are
UI stubs (`console.log`, no handler, or empty function). The old PyQt6 GUI (`gui/`) and the Flask
backend (`backend/app.py`) already implement all the underlying functionality — the gap is purely
the wiring layer in the new frontend. This plan audits every stub and maps it to the correct
backend endpoint or IPC call, then implements the connections screen by screen in priority order.

## Audit Summary

| Screen | Wired | Total elements | % |
|---|---|---|---|
| ScreenPipeline | 19 | 20 | 95% |
| ScreenBootlegs | 11 | 14 | 79% |
| ScreenHome | 7 | 10 | 70% |
| ScreenSearch | 11 | 16 | 69% |
| ScreenThemes | 5 | 8 | 63% |
| ScreenCollection | 12 | 36 | 33% |
| ScreenSetup | 1 | 16 | 6% |

---

## Implementation Order (most broken / most foundational first)

### Sprint 1 — ScreenSetup (6% → 100%)
The app is unconfigurable without this screen. Every stub maps to a known endpoint.

| Stub | Endpoint | Method | Notes |
|---|---|---|---|
| Publish master update | `/api/master/github_release` | POST | Poll `/api/master/github_release/status`; progress bar |
| Install master update | `/api/master/export` | POST | Same poll pattern |
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

### Sprint 2 — ScreenCollection (33% → ~90%)

| Stub | Endpoint | Method | Notes |
|---|---|---|---|
| All years filter | `/api/search/years` + filter param | GET | Pass `year=` to collection fetch |
| Xref only checkbox | `/api/collection?xref_only=1` | GET | Add param to existing fetch |
| Add single folder | IPC `pickFolders` → `/api/folder_link` | PUT | Link folder path to selected LB |
| Scan directory | IPC `pickDir` → `/api/pipeline/scan-tree` | POST | Reuse Pipeline scan pattern |
| Scan tree | IPC `pickDir` → `/api/pipeline/scan-tree` | POST | Same |
| Update location | IPC `pickDir` → `/api/folder_link` | PUT | Update path for existing link |
| Remove | `/api/collection/<lb>` | DELETE | Confirm dialog |
| Export HTML | `/api/collection/export?format=html` | GET | Download as file |
| Export M3U | `/api/collection/export?format=m3u` | GET | Download as file |
| Create torrent | `/api/torrent/create` | POST | With LB number; poll status |
| Add to qBittorrent | `/api/qbt/add` | POST | After torrent exists |
| Reveal on disk | `window.api.openPath(folderPath)` | IPC | Use folder path from row |
| Attachments | (screen not built yet) | — | Toast placeholder |
| Spectrograms | (screen not built yet) | — | Toast placeholder |
| On map | (screen not built yet) | — | Toast placeholder |
| Regenerate torrent | `/api/torrent/create` | POST | Force re-create |
| Post to forum | `/api/wtrf/post` | POST | Open preview dialog first |

---

### Sprint 3 — ScreenSearch (69% → ~95%)

| Stub | Endpoint/Action | Notes |
|---|---|---|
| Table row click | `/api/entry/<lb>` | Show detail panel (side-panel like old GUI) |
| Sort dropdown | add `sort=` param to `/api/search` GET | Backend already supports it |
| Export CSV | `/api/search?format=csv` or client-side | Verify if backend has export param |
| Group by year | client-side toggle | Wire button to `groupByYear` state |
| Columns visibility | client-side column toggle state | localStorage persistence |
| Saved views | localStorage store of current filter state | No backend needed |
| More options | TBD | Define scope |

---

### Sprint 4 — ScreenHome (70% → 100%)

| Stub | Endpoint | Notes |
|---|---|---|
| Check for DB update | GitHub Releases API | Show badge if update available; same logic as Setup |
| View full log | `/api/activity/log` or IPC | Verify if endpoint exists; may need to add |

---

### Sprint 5 — ScreenBootlegs (79% → 100%)

| Stub | Endpoint | Notes |
|---|---|---|
| Year filter button | `/api/bootlegs?year=<y>` | Populate dropdown from `/api/search/years` |
| CDs filter button | `/api/bootlegs?cds=<n>` | Add cds param |
| Export CSV | client-side or `/api/bootlegs?format=csv` | Check backend |

---

### Sprint 6 — ScreenThemes (63% → 100%)

| Stub | Action | Notes |
|---|---|---|
| Typeface buttons | set CSS `--font-family` token; save to localStorage | No backend needed |
| Export theme JSON | serialize theme state → `window.api.saveFile` | Need `saveFile` IPC |
| Import theme JSON | `window.api.pickFile` → parse + apply | Need `pickFile` IPC |

**New IPC needed in Sprint 6:** `saveFile(content, filename)` and `pickFile(extensions[])` — add to `preload/index.ts` + `main/index.ts`.

---

## Critical Files

| File | Sprint |
|---|---|
| `gui_next/src/renderer/src/screens/ScreenSetup.tsx` | 1 |
| `gui_next/src/renderer/src/screens/ScreenCollection.tsx` | 2 |
| `gui_next/src/renderer/src/screens/ScreenSearch.tsx` | 3 |
| `gui_next/src/renderer/src/screens/ScreenHome.tsx` | 4 |
| `gui_next/src/renderer/src/screens/ScreenBootlegs.tsx` | 5 |
| `gui_next/src/renderer/src/screens/ScreenThemes.tsx` | 6 |
| `gui_next/src/preload/index.ts` | 6 |
| `gui_next/src/main/index.ts` | 6 |

## Reusable Patterns (establish in Sprint 1, reuse everywhere)

1. **Progress-polling job** — POST to start → poll status endpoint every 500ms → progress bar → clear on done/error
2. **Settings save** — POST to `/api/db/settings` with `{key, value}` → toast on success/error
3. **Confirm-then-DELETE** — modal confirm dialog → DELETE → refresh list
4. **File-download response** — GET with `?format=csv/html` → `Blob` → synthetic `<a>` click

## Verification (each sprint)

1. `npm run dev` in `gui_next/` — start backend + Electron dev mode
2. Exercise every previously-stubbed button manually
3. Check devtools Network tab for correct endpoint calls and 2xx responses
4. Check Flask logs for matching request receipt
5. Confirm state updates (list refreshes, toasts, progress bars) work end-to-end
