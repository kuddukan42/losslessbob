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
| Bloom filter | pybloom-live | 4.0.0 |
| Web scraping | BeautifulSoup4 + lxml | 4.12.3 / 6.1.0 |
| HTTP client | Requests | 2.32.3 |
| File watching | Watchdog | 4.0.1 |
| Torrent generation | torf | 4.3.1 |
| Credential storage | keyring | 25.7.0 |
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
│   ├── checksum_utils.py     # Shared: FFP/MD5/shntool compute, lbdir parse, verify, generate
│   ├── credentials.py        # OS keyring credential storage (SERVICE_QBT, SERVICE_WTRF)
│   ├── importer.py           # Flat-file import logic
│   ├── rename.py             # write_rename_log() — rename_log.txt + rename_history DB row
│   ├── scraper.py            # Web scraper for losslessbob.com
│   ├── scheduler.py          # Watchdog file watcher, auto-import
│   ├── sox_utils.py          # SoX/ffmpeg tool detection + spectrogram generation
│   ├── startup_log.py        # Startup timing logger → data/startup.log
│   ├── torrent_maker.py      # torf-based .torrent generation; tracker CDN fetch
│   ├── qbittorrent.py        # qBittorrent WebUI API v2 integration
│   └── forum_poster.py       # SMF 2.x WTRF forum topic posting
├── gui/
│   ├── main_window.py        # Main window, tab container, menu, status bar
│   ├── lookup_tab.py         # Core feature: paste/load checksums, view results
│   ├── verify_tab.py         # Verify local checksum files (.ffp/.md5/.st5) against audio
│   ├── lbdir_tab.py          # Verify official lbdir*.txt files against audio on disk
│   ├── search_tab.py         # Full-text search across entries
│   ├── setup_tab.py          # Import, scraper control, DB management, SoX status
│   ├── attachments_tab.py    # Browse and preview cached attachment files
│   ├── rename_tab.py         # Propose and execute folder renames based on LB match
│   ├── spectrogram_tab.py    # Generate and view per-file SoX spectrograms
│   ├── dbedit_tab.py         # DB Editor: browse/edit/delete rows, export CSV
│   ├── theme_tab.py          # Color theme picker and custom color editor
│   └── styles.py             # Generates Qt stylesheets from color dict
└── data/
    ├── losslessbob.db        # SQLite database
    ├── *_flat_file.txt       # Tab-delimited flat-file (user-provided)
    ├── attachments/
    │   └── LB-{N}/           # Cached .ffp, .txt, .html per entry
    ├── pages/
    │   └── LB-{N}.html       # Cached detail page HTML (used by local-pages scrape mode)
    └── torrents/
        └── *.torrent          # Generated .torrent files (excluded from git)
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

### `entries_fts` — FTS5 full-text search index (virtual table)
Content table over `entries`. Columns: `description`, `setlist`, `location`, `date_str`. Maintained by `entries_fts_insert/update/delete` triggers. Rebuilt by `init_db()` on first run when index is empty but `entries` is not.

### `entry_changes` — Field-level scrape diff log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER NOT NULL | Entry that changed |
| field | TEXT NOT NULL | Field name from `TRACKED_ENTRY_FIELDS` |
| old_value | TEXT | Previous value |
| new_value | TEXT | New value after scrape |
| changed_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |

Index: `idx_changes_lb ON entry_changes(lb_number, changed_at DESC)`.

### `integrity_events` — Watchdog file-change alert log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | Owning collection entry |
| disk_path | TEXT | Path being watched |
| event_type | TEXT | e.g. `'deleted'`, `'modified'` |
| detail | TEXT | Human-readable description |
| occurred_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| acknowledged | INTEGER | 0 = unread, 1 = dismissed |

### `torrents` — Generated .torrent file records
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | FK to entries |
| torrent_path | TEXT | Absolute path to .torrent in data/torrents/ |
| source_folder | TEXT | Absolute path to LB folder on disk |
| created_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| infohash | TEXT | Read from .torrent via torf at creation time |
| added_to_qbt | INTEGER | 0 / 1 |
| added_to_qbt_at | TIMESTAMP | NULL if never added |
| qbt_infohash_confirmed | INTEGER | 0 / 1 |
| last_seen_at | TIMESTAMP | Last time source_folder verified on disk |
| excluded_files | TEXT | JSON list of files excluded from torrent |

### `rename_history` — Folder rename audit log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| lb_number | INTEGER | FK to entries (nullable) |
| old_path | TEXT | Full path before rename |
| new_path | TEXT | Full path after rename |
| renamed_at | TIMESTAMP | Defaults to CURRENT_TIMESTAMP |
| source | TEXT | 'rename_tab', 'collection_tab', or 'auto' |
| notes | TEXT | Warnings, mismatch details, relocation notes |

### `meta` — Key-value configuration store
Persists settings between runs. Key examples:
- `import_hash` — MD5 of last imported flat file (skip re-import if unchanged)
- `last_import_date` — ISO timestamp of last import
- `auto_scrape` — `'1'` or `'0'`
- `scrape_delay_ms` — Delay between scrape requests
- `download_files` — Whether to cache attachment files
- `use_local_pages` — `'1'` or `'0'` — read metadata from `data/pages/` instead of web when available
- `search_page_size` — integer string, results per page in Search tab (default `'50'`)
- `qbt_host` — qBittorrent WebUI hostname (default `'localhost'`)
- `qbt_port` — qBittorrent WebUI port (default `'8080'`)
- `qbt_category` — optional category label for added torrents
- `qbt_tags` — optional comma-separated tag string for added torrents
- `tracker_list` — tracker list name for torrent generation (default `'best'`)

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
| POST | `/api/db/import` | Start async flat-file import. Returns `{ok, running}` immediately. |
| GET | `/api/db/import/status` | Poll import progress: `{running, stage, rows_parsed, rows_total, rows_merged, new_lb_count, message, error}` |
| GET | `/api/db/settings` | Load all `meta` key-value pairs |
| POST | `/api/db/settings` | Save `meta` key-value pairs |
| POST | `/api/db/reset` | Drop and recreate all tables (destructive) |
| GET | `/api/db/check_update` | Compare local max LB vs site max |

### Entry Detail
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/entry/<lb>` | Full entry record + checksums + files |
| GET | `/api/entry/<lb>/files` | List attachment files for entry |
| GET | `/api/entry/<lb>/changes` | Field-level scrape diff history. Query param: `limit` (default 50). Returns `[{field, old_value, new_value, changed_at}]`. |
| GET | `/api/attachment/<lb>/<filename>` | Serve cached attachment file |
| POST | `/api/entry/<lb>/scrape` | Trigger scrape of single entry |

### Search
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/search?q=&field=` | `field`: `all`, `location`, `date`, `description`. Returns all matching entries (no limit). |
| GET | `/api/checksums/xref_lb_numbers` | Return sorted list of lb_numbers that have at least one xref checksum (xref > 0). |

### Scraper Control
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/scrape/start` | Start bulk scrape. Body: `{lb_numbers, force, download_files, delay_ms}` |
| GET | `/api/scrape/status` | Poll progress: `{running, current_lb, done, total, errors, skipped, last_action, last_source}` |
| POST | `/api/scrape/stop` | Request stop |

### Collection Data Management
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/collection/purge` | Purge a data scope. Body: `{scope}`. Scopes: `collection`, `wishlist`, `personal_meta`, `integrity_events`, `entry_changes`. |
| POST | `/api/collection/delete_bulk` | Remove specific entries from My Collection. Body: `{lb_numbers:[...]}`. Returns `{ok, deleted}`. |

### DB Editor
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/dbedit/tables` | List all tables with row counts and edit flags (`readonly`, `audit`, `warn`). |
| GET | `/api/dbedit/table/<name>/schema` | Return `PRAGMA table_info` for the named table. |
| GET | `/api/dbedit/table/<name>/rows` | Paginated rows. Query params: `page`, `limit` (max 500), `search`, `sort_col`, `sort_dir`. Returns `{columns, rows, total, page, limit}`. |
| PATCH | `/api/dbedit/table/<name>/row` | Update one row by rowid. Body: `{rowid, updates:{col:val,...}}`. Blocked for readonly/audit tables. |
| DELETE | `/api/dbedit/table/<name>/rows` | Delete rows by rowid list. Body: `{rowids:[...]}`. Blocked for readonly tables. |
| GET | `/api/dbedit/table/<name>/export` | Download entire table as CSV attachment. |

### Torrent Generation
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/torrent/create` | Generate a .torrent for one LB entry. Body: `{lb_number, source_folder, tracker_list?}`. Returns `{ok, torrent_path, infohash, torrent_id, name, excluded_files}`. |
| GET | `/api/torrent/<lb>` | List all torrent records for an LB entry. Each row includes `source_folder_exists` and `torrent_file_exists` booleans. |
| PATCH | `/api/torrent/<id>` | Update a torrents row (e.g. source_folder after relocation). |
| GET | `/api/trackers` | Return tracker list. Query params: `list_name`, `force_refresh`. |

### qBittorrent Integration
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/qbt/test` | Test WebUI connectivity. Body: `{host, port, username?, password?}`. Returns `{ok, version}`. |
| POST | `/api/qbt/add` | Add torrent(s) to qBittorrent. Body: `{torrent_id?, lb_numbers?, host?, port?, username?, password?, category?, tags?}`. Returns `{ok, added, total, results}`. |

### Forum Posting
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/entry/<lb>/post_forum` | Post a topic to the WTRF forum. Body: `{username?, password?, torrent_id?}`. Returns `{ok, topic_url}`. |

### Spectrogram
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/spectrogram/check` | Tool availability: `{sox_available, sox_version, ffmpeg_available}` |
| POST | `/api/spectrogram/generate` | Start batch generation. Body: `{folders, width, height, dyn_range, force}` |
| GET | `/api/spectrogram/status` | Poll batch state: `{status, current, done, total, errors, skipped, stop_requested}` |
| POST | `/api/spectrogram/stop` | Request stop after current file |
| POST | `/api/spectrogram/list` | Inventory PNGs per folder. Body: `{folders}`. Returns `{folder -> [{audio_file, audio_name, png_path, has_png}]}` |

### Verify (Local Checksums)
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/verify` | Verify audio files against `.ffp`/`.md5`/`.st5` in each folder. Body: `{folders:[...]}`. |
| POST | `/api/verify/generate` | Generate `_mychecksums.ffp` and/or `_mychecksums.md5` for each folder. Body: `{folders:[...]}`. |

### LBDir
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/lbdir/check` | Find `lbdir*.txt` in each folder, parse, and verify all listed files. Returns extended result with `lbdir_found`, `lbdir_path`, `lb_number`, plus `length`/`expanded_size`/`cdr`/`wave_problems`/`fmt`/`ratio` per file from shntool_len section. |
| POST | `/api/lbdir/retrieve` | Copy `lbdir*.txt` from `data/attachments/LB-{N:05d}/` to the target folder (triggering a scrape if not yet cached). Looks up LB number from `my_collection` by `disk_path`. |

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

## Backend: Checksum Utilities (`backend/checksum_utils.py`)

Shared module for local file verification and checksum generation. Used by `/api/verify`, `/api/verify/generate`, `/api/lbdir/check`, and `/api/lbdir/retrieve`.

### Functions

| Function | Description |
|----------|-------------|
| `parse_lbdir_file(path)` | Parse a `lbdir*.txt` into `{mode, md5, ffp, shntool, shntool_len}` sections. Detects mode from content. Maps shntool `.wav` → `.shn`. |
| `compute_ffp(filepath)` | Scan FLAC metadata blocks for STREAM_INFO, return bytes 18–33 as 32-char hex (MD5 of unencoded audio). Returns `None` if not valid FLAC. |
| `compute_md5(filepath)` | Streaming `hashlib.md5` of full file bytes. Returns `None` on IOError. |
| `compute_shntool(filepath)` | Shell out to `shntool md5 <file>`, parse `[shntool]` line. Raises `ShntoolNotFoundError` if binary not in PATH. |
| `detect_folder_mode(folder_path)` | Returns `'flac'`, `'shn'`, or `'mixed'` by globbing for `.flac`/`.shn` files. |
| `_mychecksums_path(folder, basename, ext)` | Returns `<folder>/<basename>_mychecksums.<ext>`, incrementing to `_mychecksums_2`, `_mychecksums_3`, … until a non-existent path is found. |
| `verify_folder(folder_path)` | Verify audio files against standalone `.ffp`/`.md5`/`.st5` checksum files in the folder. |
| `verify_folder_lbdir(folder_path, lbdir_path)` | Verify all files listed in a `lbdir*.txt` (audio + non-audio), including `length`/`cdr`/`wave_problems` from shntool_len section. |
| `generate_checksums(folder_path)` | FLAC: write `_mychecksums.ffp` + `_mychecksums.md5`. SHN: write `_mychecksums.md5` with shntool `[shntool]` format lines. Never overwrites existing files. |

### Verify result schema (per folder)
```json
{
  "folder": "/path",
  "mode": "flac|shn|mixed",
  "status": "pass|fail|incomplete|shntool_missing",
  "total": 12, "pass": 10, "mismatch": 1, "missing": 1, "extra": 0,
  "missing_types": ["ffp"],
  "files": [
    {
      "filename": "01 - Track.flac",
      "md5_expected": "...", "md5_actual": "...", "md5_status": "pass|fail|missing|na",
      "ffp_expected": "...", "ffp_actual": "...", "ffp_status": "pass|fail|missing|na",
      "shntool_expected": null, "shntool_actual": null, "shntool_status": "na",
      "st5_expected": null, "st5_status": "na",
      "on_disk": true, "overall": "pass|fail|missing|extra"
    }
  ]
}
```
`/api/lbdir/check` adds `lbdir_found`, `lbdir_path`, `lb_number` at the top level and `length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio` per file (all six shntool_len fields).

### lbdir file format
```
=== md5 for: LB-01234 ===
d41d8cd98f00b204e9800998ecf8427e *01 - Track.flac

=== ffp for: LB-01234 ===
01 - Track.flac:a9f1234...

=== shntool md5/hash for: LB-01234 ===
e5d3a...  [shntool]  01 - Track.wav

=== shntool len for: LB-01234 ===
  3:47.15  39,684,620  -  ---  FLAC  0.5012  01 - Track.wav
```

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
1. If `use_local_pages=True` and `data/pages/LB-{N:05d}.html` exists → read from disk (no network request)
2. Otherwise fetch `/detail/LB-{N:05d}.html` → save HTML to `data/pages/LB-{N:05d}.html` for future reuse
3. Parse HTML table for date, location, CDR, rating, timing
4. Extract description from `<p>` tags + bare text nodes
5. Extract setlist from numbered lines (`1. song`, `2. song`)
6. Find attachment links matching `/files/LBF-*`
7. Optionally download files to `data/attachments/LB-{N:05d}/`; skip if file already on disk unless `force=True` and `use_local_pages=False`
8. 404 → write `status='missing'` to DB

**Rate limiting:** 3 retries with exponential backoff; 60-second pause on HTTP 429.

**Skip logic:** `scrape_entry` skips an entry (returns `{skipped: True}`) when `force=False` and any of:
- Entry exists in DB with `status='missing'`
- Entry exists and `download_files=False` (metadata already present)
- Entry exists and all `entry_files` records have `downloaded=1` (including files synced from disk — see below)

**Filesystem sync:** Before counting pending downloads, the skip check updates any `downloaded=0` record to `downloaded=1` if the corresponding file already exists in `data/attachments/LB-{N:05d}/`. This handles files placed there from external sources.

**Bulk scrape:** Thread-safe progress state `{running, current_lb, done, total, errors, skipped, last_action, last_source, stop_requested}` polled by GUI every 1 second. `last_action` is `'scraped'`, `'skipped'`, or `'error'`. `last_source` is `'local'`, `'web'`, or `None`.

**Delay suppression:** The inter-request delay is suppressed when an entry was read from a local page file (`last_source='local'`) since no network I/O occurred. Web fallbacks still observe the configured delay.

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

Ten tabs in order: **Lookup**(0) · **Rename Folders**(1) · **Verify**(2) · **lbdir**(3) · **Search**(4) · **My Collection**(5) · **Attachments**(6) · **Spectrograms**(7) · **DB Editor**(8) · **Setup**(9) · **Themes**(10)

**Menu bar:**
- File → Exit
- Database → Check for Update / Select Database / Open DB Folder (all navigate to Setup via `tabs.indexOf(setup_tab)`)
- Help → Help / About

**Status bar:** Refreshes every 10 seconds with latest DB stats (most recent LB, checksum count, last import date).

**Settings persistence:** Window geometry saved/restored via `QSettings`.

**Tab index policy:** All `setCurrentIndex()` calls use `self.tabs.indexOf(self.whichever_tab)` rather than hardcoded integers so the order can change without breaking navigation.

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

**Checksum generation:** Posts to `POST /api/verify/generate` with the selected folder path(s). The backend (`backend/checksum_utils.py`) computes FFP (FLAC STREAM_INFO bytes 18–34) and MD5 hashes and writes `<foldername>_mychecksums.ffp` and `<foldername>_mychecksums.md5`, incrementing the suffix (`_mychecksums_2`, etc.) if files already exist. Generated file paths and any errors are shown in the status area below the file list.

**Double-click summary row:** Opens the LosslessBob detail page in the system browser.

**Signal to Rename tab:** After each lookup, emits results so the Rename tab can auto-populate folder rename proposals.

**Threading:** `_LookupWorker` (QThread) performs API calls without blocking the UI.

---

## GUI: Verify Tab (`gui/verify_tab.py`)

Verifies audio files against **locally-generated** checksum files (`.ffp`, `.md5`, `.st5`) — distinct from lbdir_tab which checks the official archive record.

**Left panel:** Folder list (drag-drop, dirs only). Buttons: Add Folders, Add Root Folder (recursive audio scan), Remove Selected, Clear List, Verify Folders, Generate Checksums, Retrieve from LB.

**Summary table** (one row per folder):
Columns: Folder | Mode | FFP | MD5 | Shntool | Total | Pass | Mismatch | Missing | Extra | Status

**Detail table** (one row per audio file in selected folder):
Columns: Filename | MD5 | FFP/Shntool | ST5 | On Disk | Overall
Default: problem rows only. Toggle: "Show all files" checkbox.

**Row colors:**
| Color | Meaning |
|-------|---------|
| Green | PASS |
| Red | FAIL (mismatch) |
| Orange | MISSING FILES (files not on disk) |
| Yellow | INCOMPLETE (missing checksum type) |

**Workers:**
- `_VerifyWorker` → `POST /api/verify`
- `_GenerateWorker` → `POST /api/verify/generate`, then auto-triggers verify
- `_RetrieveWorker` → `POST /api/lbdir/retrieve`, then auto-triggers verify

shntool missing → yellow row + status label install hint.

---

## GUI: lbdir Tab (`gui/lbdir_tab.py`)

Verifies the **official lbdir*.txt** file for each folder against actual files on disk. The lbdir file is the archive's authoritative checksum record scraped from losslessbob.com.

**Left panel:** Folder list (drag-drop, dirs only). Buttons: Add Folders, Add Root Folder, Remove Selected, Clear List, Check lbdir Files (all folders), Retrieve lbdir (selected or all → auto-triggers check).

**Summary table** (one row per folder):
Columns: Folder | LB# | lbdir File | Mode | Total | Pass | Mismatch | Missing | Status

**Row colors:**
| Color | Meaning |
|-------|---------|
| Green | PASS |
| Red | FAIL, MISSING FILES, SHNTOOL MISSING, PARSE ERROR |
| Yellow | NO LBDIR (lbdir absent but LB# known, retrievable) |
| Grey | NO LB# (cannot retrieve, entry unknown) |

**Double-click summary row:** Opens `http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html`.

**Detail table** (one row per file listed in lbdir):
Columns: Filename | MD5 Exp. | MD5 Act. | MD5 | FFP/Shn Exp. | FFP/Shn Act. | FFP/Shn | On Disk | Overall
Hash columns truncated to 12 chars with full hash in tooltip. Column-0 `UserRole` stores the original file index so the "Show all files" toggle correctly maps visible rows to file data.

**Info panel** (right of detail table): Displays shntool_len data for the selected detail row — Length, Expanded Size, CDR, WAVE Problems, Format, Ratio. Populated from `/api/lbdir/check` per-file fields; blank for non-audio files or when no shntool_len data is available.

**Retrieve lbdir button:** Uses selected listbox items if any, otherwise all folders. Status messages distinguish `copied` (local cache), `scraped_and_copied` (fresh scrape), `not_found`, and `no_lb_number` (folder not in My Collection).

**Workers:**
- `_LbdirCheckWorker` → `POST /api/lbdir/check`
- `_LbdirRetrieveWorker` → `POST /api/lbdir/retrieve`, then auto-triggers check

---

## GUI: Search Tab (`gui/search_tab.py`)

Search field + field selector (All / Location / Date / Description) + year dropdown. All matching entries are fetched from the API and paginated client-side. Columns: LB Number, Date, Location, Rating, Description, Owned.

**Pagination:** Prev/Next buttons and a "Page X of Y (N results)" label appear between the search bar and table whenever results exceed the configured page size. Page size defaults to 50 and is set in the Setup tab. `set_page_size(n)` resets to page 1 and re-renders.

**Client-side filters (checkboxes, all AND-combined):**
- **Missing only** — show only rows with `status == "missing"` (yellow highlighted)
- **Owned only** — show only rows whose LB number is in My Collection
- **Not owned** — show only rows NOT in My Collection
- Combining "Missing only" + "Owned" = missing entries that are owned; combining "Owned only" + "Not owned" = empty result (contradictory)

**Owned data** is fetched from `GET /api/collection/lb_numbers` after each search result arrives. If an owned filter is active when data loads, the page is re-rendered automatically.

**Double-click col 0:** Switches to Lookup tab. **Double-click any other column:** Opens `LB-{lb:05d}.html` on losslessbob.com (5-digit zero-padded).

---

## GUI: Setup Tab (`gui/setup_tab.py`)

**Database section:** Stats display, Import Database File button, Check for Update, Open DB Folder, destructive Reset button.

**Search section:** "Results per page" spinner (range 10–500, step 10, default 50). Saved to meta as `search_page_size`. Emits `search_page_size_changed(int)` signal picked up by the Search tab.

**Scraper section:**
- Checkboxes: Auto-scrape after import, Download attachment files, Force re-scrape (ignore already-complete entries), **Use local pages for metadata (data/pages/)**
- Delay spinner (500–10000 ms, default 1500 ms)
- Scrape All / Stop buttons
- Single-entry scrape (enter one LB number)
- Range scrape (start, end, optional Fill Gaps mode)
- Progress bar + scrolling log (max 500 lines)

**Force re-scrape checkbox:** When checked, passes `force=True` to all three scrape modes (single, range, all), bypassing the skip-if-already-complete logic. Persisted in `meta` as `force_scrape`.

**Skip LB numbers with no checksum data:** For LB numbers in the range not present in the checksum DB, inserts a `status='missing'` placeholder entry (renamed from "Mark sequential gaps as MISSING").

**Scraper log:** Shows "Scraped LB-X [local]" / "Scraped LB-X [web]", "Skipped LB-X — already complete", or "Error scraping LB-X" per entry. Uses `last_lb` (the just-completed entry) paired with `last_source`/`last_action` from the status poll so the source tag always matches the logged LB number. Completion message includes skipped and error counts.

**Scraper log file:** Every log line is appended to `data/scraper.log`. The Scraper Log group shows the current file size, an "Open Log File" button, and a "Purge Log" button that truncates the file and clears the in-app widget.

**Background threads:**
- `_ImportThread` — calls `/api/db/import`
- `_ResetThread` — calls `/api/db/reset`
- `_SingleScrapeThread(flask_port, lb_number, force)` — calls `/api/entry/<lb>/scrape`
- `_ScrapeStatusThread` — polls `/api/scrape/status` every 1 second; updates progress bar and log

---

## GUI: Attachments Tab (`gui/attachments_tab.py`)

**Left panel:** Tree of entries that have locally cached files, with file count. Only entries with at least one downloaded file appear.

**Right panel (stacked widget):**
- Text viewer for `.txt`, `.ffp`, `.md5`, `.st5`
- Web viewer (PyQt6-WebEngine) for `.html`
- Generic panel with Open Externally button for other types

**Re-download button:** Forces a fresh scrape of the selected entry.

**Manual file placement:** Files dropped directly into `data/attachments/LB-XXXXX/` (matching the zero-padded naming convention) are displayed in the tree after clicking Refresh — no DB write required. The "Refresh / Re-download" button will overwrite manually placed files, so avoid using it on manually populated entries.

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
  → POST /api/scrape/start {lb_numbers, force, use_local_pages}
    → Background thread: for each LB:
        if use_local_pages and data/pages/LB-N.html exists:
            read HTML from disk (no network)
        else:
            GET /detail/LB-{N:05d}.html
            save HTML → data/pages/LB-{N:05d}.html
        Parse HTML → entries table
        Download missing files → data/attachments/LB-{N:05d}/
        Sleep delay_ms only if source was web
  ← GET /api/scrape/status every 1s
  → Progress bar + log update ([local] / [web] label per entry)
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
  - Verify: `summary_container`, `detail_container`
  - lbdir: `summary_container`, `detail_container`
  - Search: `view`
  - Collection: `coll_view`, `miss_view`
  Do **not** apply globally or to the window frame.

- **QTableWidget vs QTableView:** The Lookup and Rename tabs use `QTableView` + custom `QAbstractTableModel`. The Verify and lbdir tabs use `QTableWidget` (no model class) since their data is repopulated wholesale on each run and per-cell color/tooltip control is simpler with `QTableWidgetItem`. Both use `QHeaderView.ResizeMode.Interactive` and `resizeColumnsToContents()` after load.

- **Worker pattern:** All background operations use `QThread` subclasses with `finished(dict)` and `error(str)` signals, matching `_LookupWorker`. Workers that auto-chain (generate→verify, retrieve→check) call the next `_start_*` method from the `finished` handler in the main thread.

- **Folder index in detail tables:** When the Verify or lbdir detail table filters rows (show-problems-only mode), column-0 of each visible row stores the original index into the full file list via `item.setData(Qt.ItemDataRole.UserRole, file_idx)`. This allows the info panel click handler to correctly retrieve shntool_len data regardless of which rows are hidden.

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
| 2026-05-06 | Scraper: skip logic no longer fires delay for already-complete entries; `_scrape_state` gains `skipped` count and `last_action`; log distinguishes scraped vs skipped. |
| 2026-05-06 | Setup tab: added "Force re-scrape" checkbox applied to all three scrape modes; `_SingleScrapeThread` accepts `force` parameter. |
| 2026-05-06 | Added `backend/checksum_utils.py`: FFP/MD5/shntool compute, lbdir parsing, `verify_folder`, `verify_folder_lbdir`, `generate_checksums`, `_lbgen_path`. |
| 2026-05-06 | Added four new API routes: `POST /api/verify`, `POST /api/verify/generate`, `POST /api/lbdir/check`, `POST /api/lbdir/retrieve`. |
| 2026-05-06 | Lookup tab: checksum generation now calls `POST /api/verify/generate` instead of doing file I/O in the GUI worker; output uses `_lbgen` naming convention. |
| 2026-05-07 | Added `gui/verify_tab.py`: folder-level verification against local checksum files; three workers (verify, generate, retrieve); summary + detail tables with color coding. |
| 2026-05-07 | Added `gui/lbdir_tab.py`: verification against official lbdir*.txt archive records; detail table with truncated hash columns + tooltip; info panel for shntool_len data; double-click opens LB detail page. |
| 2026-05-07 | `checksum_utils.verify_folder_lbdir` now passes all six shntool_len fields per file (`length`, `expanded_size`, `cdr`, `wave_problems`, `fmt`, `ratio`). |
| 2026-05-07 | Tab order updated: Lookup(0) Rename(1) Verify(2) lbdir(3) Search(4) Collection(5) Attachments(6) Setup(7) Themes(8). All `setCurrentIndex` calls replaced with `indexOf()` for future-proofing. |
| 2026-05-07 | lbdir_tab, verify_tab: "Show all files" checkbox now checked by default. |
| 2026-05-07 | scraper.py: Fixed three skip/download bugs (see BUGS.md BUG-001–003). |
| 2026-05-07 | scraper.py, app.py, setup_tab.py: Added `use_local_pages` feature — metadata scraped from `data/pages/LB-XXXXX.html` when available; web scrapes cache HTML to `data/pages/` for reuse; delay suppressed for local reads; `last_source` field in scrape state. |
| 2026-05-07 | data/pages/: New directory for cached detail page HTML files. |
| 2026-05-07 | Search tab: client-side pagination with Prev/Next buttons; Setup tab: "Results per page" spinner (10–500); db.py search_entries limit removed; search_page_size meta key added. |
| 2026-05-07 | Scraper log now persisted to data/scraper.log; log management UI (size, Open, Purge) added; [web]/[local] label bug fixed via last_lb state field; error entries now logged explicitly. |
| 2026-05-07 | Search tab: added Missing only / Owned only / Not owned client-side filter checkboxes (AND-combinable); fixed double-click URL to zero-pad LB number to 5 digits. Setup tab: renamed "Mark sequential gaps as MISSING" → "Skip LB numbers with no checksum data"; Scrape All/Scrape/Scrape Range buttons moved to same grid column so they render at equal width. My Collection tab: auto-loads on startup; client-side pagination (shares Results per page from Setup tab); year dropdown filter. |
| 2026-05-12 | DB-01/02: WAL mode + performance PRAGMAs; persistent per-thread connection pool in db.py. |
| 2026-05-12 | DB-03: idx_chk_covering and idx_lb_xref0 partial index added to checksums. |
| 2026-05-12 | DB-04: lookup_checksums uses temp table JOIN instead of IN clause. |
| 2026-05-12 | DB-05: entries_fts FTS5 virtual table + triggers; search_entries uses FTS MATCH with LIKE fallback. |
| 2026-05-12 | DB-06: PRAGMA optimize called after import (importer.py) and after scrape_range (scraper.py). |
| 2026-05-12 | DB-07: ScalableBloomFilter pre-filters definite-miss checksums; pybloom-live==4.0.0 added. |
| 2026-05-12 | DB-08: entry_changes table + record_entry_changes(); GET /api/entry/lb/changes endpoint; db_reset drops FTS and entry_changes. |
| 2026-05-12 | Import progress: async import with stage/row-count state; GET /api/db/import/status; import progress bar in Setup tab. |
| 2026-05-12 | Added backend/sox_utils.py: SoX/ffmpeg detection, generate_spectrogram(), spectrogram batch worker. Five /api/spectrogram/* routes. |
| 2026-05-12 | Added gui/spectrogram_tab.py: two-pane spectrogram viewer tab. Registered as tab 7 (Spectrograms). |
| 2026-05-12 | gui/setup_tab.py: SoX availability indicator with Re-check button added to Database group. |
| 2026-05-13 | FEAT-13: integrity_events schema added; purge_* / delete_collection_entries in db.py; POST /api/collection/purge and /delete_bulk; Select All/None + bulk _on_remove in collection_tab; Data Management group in setup_tab. |
| 2026-05-13 | FEAT-14: _DBEDIT constants and 6 /api/dbedit/* routes in app.py; gui/dbedit_tab.py (DbEditTab) created; registered as DB Editor tab (index 8) in main_window.py. Tab count: 11. |
| 2026-05-13 | Added backend/startup_log.py; instrumented main.py, backend/app.py, gui/main_window.py with startup timing probes → data/startup.log. |
| 2026-05-13 | Lookup: duplicate resolution prefers MATCHED over INCOMPLETE; folder/summary click filtering; verify NO CHECKSUMS yellow status; lookup→verify folder carry. |
| 2026-05-14 | Rename: Multiple IDs cyan color + right-click resolve; xref-aware naming (LB-N-xrefXXXX); _fmt_lb helper; populate_from_lookup filters to MATCHED status only. |
| 2026-05-14 | Added GET /api/checksums/xref_lb_numbers; db.get_xref_lb_numbers(); "Xref only" filter on Search and Collection tabs. |
| 2026-05-14 | Phase 1: Added torrents + rename_history tables; backend/credentials.py, rename.py, torrent_maker.py, qbittorrent.py, forum_poster.py; 7 new API routes; qBt/WTRF/Torrent sections in Setup tab; Create Torrent/Add to qBt/Post to Forum in My Collection; write_rename_log() wired to Rename tab; torf==4.3.1 + keyring==25.7.0 added. |
| 2026-05-14 | TODO-012/013: Torrent history sub-panel in My Collection — lists all torrents records per selected entry with green/red/orange status indicator, per-row context menu, Add to qBittorrent / Regenerate / Relocate Source buttons; path relocation flow with file cross-check, rename_log.txt logging, and optional rename to standard format. |
