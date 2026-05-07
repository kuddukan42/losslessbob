# LosslessBob Checksum Lookup — Project Overview

**Purpose:** Cross-platform desktop replacement for the original Windows-only `Checksum_Lookup` utility used by collectors of Bob Dylan lossless recordings from the [LosslessBob archive](http://www.losslessbob.wonderingwhattochoose.com). Users paste or load checksum files (FFP, MD5, ST5/SHA1) and the app matches them against the archive database to identify which LosslessBob entry (LB number) a recording belongs to, and whether the set is complete or has missing/duplicate files.

---

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| GUI | PyQt6 | 6.7.1 |
| Web view (attachments) | PyQt6-WebEngine | 6.7.0 |
| REST backend | Flask + Flask-CORS | 3.0.3 / 4.0.1 |
| WSGI server (optional) | Waitress | 3.0.0 |
| Database | SQLite3 | (stdlib) |
| Web scraping | BeautifulSoup4 + lxml | 4.12.3 / 6.1.0 |
| HTTP client | Requests | 2.32.3 |
| File watching | Watchdog | 4.0.1 |
| Language | Python | 3.11+ |

**Architecture pattern:** The GUI and backend are separated by a local Flask REST API (port 5174). The GUI makes HTTP requests to `localhost:5174` for all data operations. Flask runs in a daemon thread started before the PyQt6 event loop.

---

## File Structure

```
losslessbob/
├── main.py                   # Entrypoint: starts Flask thread, then PyQt6 app
├── requirements.txt
├── PROJECT.md                # This file
├── backend/
│   ├── app.py                # Flask REST API — all routes
│   ├── db.py                 # SQLite layer, checksum parsing, search
│   ├── importer.py           # Flat-file import logic
│   ├── scraper.py            # Web scraper for losslessbob.com
│   └── scheduler.py          # Watchdog file watcher, auto-import
├── gui/
│   ├── main_window.py        # Main window, tab container, menu, status bar
│   ├── lookup_tab.py         # Core feature: paste/load checksums, view results
│   ├── search_tab.py         # Full-text search across entries
│   ├── setup_tab.py          # Import, scraper control, DB management
│   ├── attachments_tab.py    # Browse and preview cached attachment files
│   ├── rename_tab.py         # Propose and execute folder renames based on LB match
│   ├── theme_tab.py          # Color theme picker and custom color editor
│   └── styles.py             # Generates Qt stylesheets from color dict
└── data/
    ├── losslessbob.db        # SQLite database
    ├── *_flat_file.txt       # Tab-delimited flat-file (user-provided)
    └── attachments/
        └── LB-{N}/           # Cached .ffp, .txt, .html per entry
```

---

## Database Schema

**File:** `data/losslessbob.db`

### `checksums` — Core lookup table
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| checksum | TEXT NOT NULL | MD5/SHA1/FFP hash value |
| filename | TEXT NOT NULL | Audio filename |
| chk_type | TEXT | `'f'` FFP, `'s'` ST5/SHA1, `'m'` MD5 |
| lb_number | INTEGER NOT NULL | Links to LosslessBob entry |
| xref | INTEGER | 1 = cross-reference entry (not primary) |

Unique index on `(checksum, lb_number)`.

### `entries` — Entry metadata scraped from losslessbob.com
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER PK | LosslessBob number |
| date_str | TEXT | Concert date |
| location | TEXT | Venue / city |
| cdr | TEXT | CDR info |
| rating | TEXT | Archive rating |
| timing | TEXT | Recording length |
| description | TEXT | Full text description |
| setlist | TEXT | Setlist text |
| status | TEXT | `'ok'`, `'missing'` |
| scraped_at | TIMESTAMP | When row was last scraped |

### `entry_files` — Attachment files per entry
| Column | Type | Notes |
|--------|------|-------|
| lb_number | INTEGER NOT NULL | |
| filename | TEXT | Remote filename (`LBF-N-name.ext`) |
| clean_name | TEXT | Display name (prefix stripped) |
| file_url | TEXT | Full remote URL |
| downloaded | INTEGER | 1 = cached locally in `data/attachments/` |

PK: `(lb_number, filename)`.

### `meta` — Key-value configuration store
Persists settings between runs. Key examples:
- `import_hash` — MD5 of last imported flat file (skip re-import if unchanged)
- `last_import_date` — ISO timestamp of last import
- `auto_scrape` — `'1'` or `'0'`
- `scrape_delay_ms` — Delay between scrape requests
- `download_files` — Whether to cache attachment files

---

## Backend: Flask API (`backend/app.py`)

**Base URL:** `http://localhost:5174`

### Checksum Lookup
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/lookup` | Parse text input and match checksums. Body: `{text}`. Returns `{summary, detail}` arrays. |

### Database Management
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/db/stats` | Row counts, latest LB number, last import date |
| POST | `/api/db/import` | Import flat-file. Body: `{file_path}` |
| GET | `/api/db/settings` | Load all `meta` key-value pairs |
| POST | `/api/db/settings` | Save `meta` key-value pairs |
| POST | `/api/db/reset` | Drop and recreate all tables (destructive) |
| GET | `/api/db/check_update` | Compare local max LB vs site max |

### Entry Detail
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/entry/<lb>` | Full entry record + checksums + files |
| GET | `/api/entry/<lb>/files` | List attachment files for entry |
| GET | `/api/attachment/<lb>/<filename>` | Serve cached attachment file |
| POST | `/api/entry/<lb>/scrape` | Trigger scrape of single entry |

### Search
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/search?q=&field=` | `field`: `all`, `location`, `date`, `description`. Returns up to 100 entries. |

### Scraper Control
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/scrape/start` | Start bulk scrape. Body: `{lb_numbers, force, download_files, delay_ms}` |
| GET | `/api/scrape/status` | Poll progress: `{running, current_lb, done, total, errors}` |
| POST | `/api/scrape/stop` | Request stop |

---

## Backend: Database Layer (`backend/db.py`)

### Checksum parsing (`parse_checksum_text`)
Regex-based parser supporting three formats:

```
FFP:   filename.flac:8d08d2e3b1e3c3c8...
MD5:   8d08d2e3b1e3c3c8...  filename.flac
       8d08d2e3b1e3c3c8... *filename.flac
ST5:   8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3c3c3c3c3 *filename.shn  (40-char hex)
```

### Lookup logic (`lookup_checksums`)
For each parsed checksum, queries `checksums` table, then aggregates per LB number:
- **MATCHED** — all files in the DB set were found in input
- **MATCHED (INCOMPLETE)** — some files from DB set not in input
- **DUPLICATE** — same checksum exists in multiple LB entries
- **NOT FOUND** — no DB match at all
- **XREF** — matched, but entry is a cross-reference

---

## Backend: Importer (`backend/importer.py`)

Accepts a tab-delimited flat file:
```
checksum<TAB>filename<TAB>type<TAB>lb_number<TAB>xref
```

**Process:**
1. MD5-hash the source file
2. Compare against stored `import_hash` in meta — skip if identical
3. Parse into temporary SQLite
4. `INSERT OR IGNORE` merge into main DB
5. Store new hash + timestamp in meta

---

## Backend: Scraper (`backend/scraper.py`)

**Target site:** `http://www.losslessbob.wonderingwhattochoose.com`

**URL pattern:** `http://...losslessbob.wonderingwhattochoose.com/detail/LB-{N:05d}.html`
- LB numbers are zero-padded to 5 digits (e.g., `LB-00042`, `LB-01025`)

**Single entry scrape:**
1. Fetch `/detail/LB-{N:05d}.html`
2. Parse HTML table for date, location, CDR, rating, timing
3. Extract description from `<p>` tags + bare text nodes
4. Extract setlist from numbered lines (`1. song`, `2. song`)
5. Find attachment links matching `/files/LBF-*`
6. Optionally download files to `data/attachments/LB-{N:05d}/`
7. 404 → write `status='missing'` to DB

**Rate limiting:** 3 retries with exponential backoff; 60-second pause on HTTP 429.

**Bulk scrape:** Thread-safe progress state `{running, current_lb, done, total, errors, stop_requested}` polled by GUI every 1 second.

---

## Backend: Scheduler (`backend/scheduler.py`)

Watchdog observer monitors the `data/` directory for `.txt` file changes.

**On file change:**
1. Debounce 2 seconds
2. MD5-hash the file
3. Compare to `import_hash` in meta
4. If different: call `run_import()` in background thread
5. If `auto_scrape` meta is `'1'`: scrape any newly imported LB numbers

---

## GUI: Main Window (`gui/main_window.py`)

Six tabs: **Lookup**, **Rename Folders**, **Search**, **Attachments**, **Setup**, **Themes**

**Menu bar:**
- File → Exit
- Database → Check for Update / Select Database / Open DB Folder
- Help → Help / About

**Status bar:** Refreshes every 10 seconds with latest DB stats (most recent LB, checksum count, last import date).

**Settings persistence:** Window geometry saved/restored via `QSettings`.

---

## GUI: Lookup Tab (`gui/lookup_tab.py`)

The primary user-facing feature.

**Left panel:** File list (drag-and-drop). Buttons: Lookup Clipboard, Lookup Listbox, Add Files, Add Folders, Clear List, Generate Checksums. Toggle to filter `_mychecksums` files.

**Right panel — Summary table** (per-LB aggregate):
- Columns: LB Number, Source, Given, Matched, Not Found, Missing, Dups, Xrefs, Status

**Right panel — Detail table** (per-checksum):
- Columns: Checksum, Filename, Type, LB Number, Xref, Status, Source

**Color coding:**
| Color | Meaning |
|-------|---------|
| Green | MATCHED (complete set) |
| Orange | NOT FOUND |
| Pink/rose | MATCHED INCOMPLETE (missing files) |
| Yellow | DUPLICATE (in multiple LBs) |
| Light blue | XREF (cross-reference entry) |

**Checksum generation:** For a selected folder, reads FLAC `STREAM_INFO` block (bytes 18–34) for FFP hashes; computes MD5 for all audio files. Writes `.ffp` and `.md5` files.

**Double-click summary row:** Opens the LosslessBob detail page in the system browser.

**Signal to Rename tab:** After each lookup, emits results so the Rename tab can auto-populate folder rename proposals.

**Threading:** `_LookupWorker` (QThread) performs API calls without blocking the UI.

---

## GUI: Search Tab (`gui/search_tab.py`)

Search field + field selector (All / Location / Date / Description). Results table shows up to 100 entries: LB Number, Date, Location, Rating, Description.

**Double-click:** Switches to Lookup tab and loads that LB number's checksums.

---

## GUI: Setup Tab (`gui/setup_tab.py`)

**Database section:** Stats display, Import Database File button, Check for Update, Open DB Folder, destructive Reset button.

**Scraper section:**
- Checkboxes: Auto-scrape after import, Download attachment files
- Delay spinner (500–10000 ms, default 1500 ms)
- Scrape All / Stop buttons
- Single-entry scrape (enter one LB number)
- Range scrape (start, end, optional Fill Gaps mode)
- Progress bar + scrolling log (max 500 lines)

**Fill Gaps mode:** Queries DB for LB numbers that have no entry yet and scrapes only those, filling holes in the local cache.

**Background threads:**
- `_ImportThread` — calls `/api/db/import`
- `_ResetThread` — calls `/api/db/reset`
- `_SingleScrapeThread` — calls `/api/entry/<lb>/scrape`
- `_ScrapeStatusThread` — polls `/api/scrape/status` every 1 second; updates progress bar and log

---

## GUI: Attachments Tab (`gui/attachments_tab.py`)

**Left panel:** Tree of entries that have locally cached files, with file count. Only entries with at least one downloaded file appear.

**Right panel (stacked widget):**
- Text viewer for `.txt`, `.ffp`, `.md5`, `.st5`
- Web viewer (PyQt6-WebEngine) for `.html`
- Generic panel with Open Externally button for other types

**Re-download button:** Forces a fresh scrape of the selected entry.

---

## GUI: Rename Tab (`gui/rename_tab.py`)

Populated automatically after each lookup. Shows folders from the input file list alongside proposed new names.

**Row states and colors:**
| State | Color | Meaning |
|-------|-------|---------|
| `has_lb` / `renamed` | Green `#C8E6C9` | Correct LB already in name / just renamed |
| `needs_rename` | Orange `#FFE0B2` | Match found, rename to `{folder}-LB-{N}` |
| `wrong_lb` | Purple `#E1BEE7` | Folder has a *different* LB number — needs strip + rename |
| `no_match` | Red `#FFCDD2` | No match or multiple IDs |

**Wrong-LB workflow:** When a folder already contains an LB number that doesn't match the correct one, the row shows "Wrong LB in name" (purple). Use **Select Wrong LB** to batch-select all such rows, then **Strip Wrong LB from Selected** to rewrite proposed names from `OldFolder-LB-old-LB-new` → `OldFolder-LB-new`. Then click **Rename Selected** to apply.

**Select All** checks only actionable rows (`needs_rename` + `wrong_lb`); green/red rows are left unchecked.

**Execute:** Rename Selected → moves folders into a `0. Processed/` subdirectory alongside the source.

---

## GUI: Theme Tab (`gui/theme_tab.py`)

Six preset themes (Light, Dark, Black, Dracula, Blue, Purple) plus custom color picker. Color changes apply immediately via `styles.py` which generates Qt QSS from a color dictionary. Theme name and per-color overrides persist in `QSettings`.

---

## Key Data Flows

### Lookup
```
User pastes text / drops files
  → POST /api/lookup {text}
    → parse_checksum_text() — regex extraction
    → lookup_checksums() — SQLite query per checksum
    → aggregate per LB number
  ← {summary[], detail[]}
  → Color-code tables
  → Signal → Rename tab auto-populates
```

### Import
```
User clicks Import / file dropped in data/
  → POST /api/db/import {file_path}
    → MD5 hash file; skip if matches stored import_hash
    → parse tab-delimited rows
    → INSERT OR IGNORE into checksums
    → store import_hash in meta
  → If auto_scrape: scrape new LB numbers
```

### Scrape
```
User clicks Scrape All / Range / Single
  → POST /api/scrape/start {lb_numbers}
    → Background thread: for each LB:
        GET /detail/LB-{N:05d}.html
        Parse HTML → entries table
        Download files → data/attachments/LB-{N:05d}/
        Sleep delay_ms
  ← GET /api/scrape/status every 1s
  → Progress bar + log update
```

---

## Checksum Format Reference

```
# FFP (FLAC Fingerprint)
filename.flac:8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3

# MD5 (with or without asterisk)
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3 *filename.flac
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3  filename.flac

# ST5 / SHA1 (40-hex)
8d08d2e3b1e3c3c8f3a3c3c3c3c3c3c3c3c3c3c3 *filename.shn
```

---

## GUI Conventions

- **Table column resizing:** All `QTableView` instances use `QHeaderView.ResizeMode.Interactive` for the horizontal header so the user can drag column borders freely. After data loads, call `view.resizeColumnsToContents()` once to set sensible initial widths. Never use `ResizeToContents` or `Stretch` as the persistent resize mode.

- **Qt style base:** `QApplication.setStyle("Fusion")` is set in `main.py` before any QSS is applied. Fusion renders consistently cross-platform and is required for QSS overrides (especially rounded corners and flat buttons) to work correctly.

- **Stylesheet generation:** All QSS is generated in `gui/styles.py` → `build_stylesheet(theme_dict)`. The stylesheet is applied to the main window and regenerated whenever the user changes themes. Key QSS rules:
  - `QPushButton`: `border-radius 6px`, `padding 5px 14px`; accent-colored background with hover/pressed/disabled states; no 3D border.
  - `QLineEdit`, `QComboBox`, `QSpinBox`: `border-radius 4px`, `padding 2px 6px`.
  - `QTabBar::tab`: `border: none`, `border-radius 4px 4px 0 0`; selected tab gets a `border-bottom: 2px solid accent` underline indicator instead of a raised appearance.
  - `QGroupBox`: `border-radius 6px`, `margin-top 1.5em`, `padding-top 6px`; title via `subcontrol-position: top left`.
  - `QProgressBar`: `border: none`, 6 px fixed height, `border-radius 3px`; chunk also rounded. No text overlay.
  - `font-weight`: always 700 — never 500 (inconsistent cross-platform).

- **Drop shadows:** `styles.apply_panel_shadow(widget)` attaches a `QGraphicsDropShadowEffect` (blurRadius 12, offset 0,2, color rgba 0,0,0,60) to a widget. Applied in `main_window.py → _apply_shadows()` to the 1–2 main result panels per tab:
  - Lookup: `summary_container`, `detail_container`
  - Rename: `view`
  - Search: `view`
  - Collection: `table`
  Do **not** apply globally or to the window frame.

---

## Notable Implementation Details

- **LB number URL padding:** LosslessBob URLs use 5-digit zero-padded numbers (`LB-00042`). The scraper and directory names use `f"{lb_number:05d}"` formatting.
- **Checksum generation (FFP):** Reads raw FLAC file bytes 18–34 from the `STREAM_INFO` metadata block, which is the MD5 signature of the decoded audio stream — not a hash of the file itself.
- **Local API port:** Flask runs on port 5174. If this conflicts with another service, it is hardcoded in `backend/app.py` and `gui/` tabs that construct the base URL.
- **File access restriction:** `.claude/settings.json` restricts Claude Code to read/write only within this project directory and `~/.claude/` (memory). Bash commands are not path-restricted.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-05-06 | Fixed scraper URL/directory formatting: LB numbers now zero-padded to 5 digits (`LB-{n:05d}`) in `backend/scraper.py` |
| 2026-05-06 | Added `.claude/settings.json` — restricts file access to project directory + deny rules for sensitive system paths |
| 2026-05-06 | Created this document |
| 2026-05-06 | Removed SDF/Wine/ExportSqlCE40 import path; flat-file only. Renamed `sdf_hash` meta key to `import_hash`. Deleted `tools/` directory. |
| 2026-05-06 | QSS modernization: Fusion base style, rounded corners, flat buttons, tab underline indicator, slim progress bar, `font-weight 700`, drop shadows on result panels. |
| 2026-05-06 | Rename tab: added `wrong_lb` state (purple) for folders with mismatched LB numbers; "Select Wrong LB" and "Strip Wrong LB from Selected" buttons; "Select All" now only checks actionable rows. |
