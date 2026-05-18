# Plan: LB Number Integrity & Status Master Table

## Locked Decisions (2026-05-17)

User-confirmed answers to outstanding planning questions:

- **GitHub repo for master publishing:** `kuddukan42/losslessbob`. Currently **private**; will go public later. Until then the Publish Master Update flow uploads to a private repo — only authenticated users with read access can download. End-user installs of the app will need the repo to be public (or releases mirrored elsewhere) before they can pull updates.
- **Curator mode gating:** **Checkbox in Setup tab** (writes `meta.is_curator='1'`). Not requiring users to edit SQL.
- **Phase order:** Use the recommended sequence (Data Ownership → UX wins → status-consuming features → flat-file & bootlegs → folder linking → Map). **Map view is deferred** — last priority, may be cut.
- **PR cadence:** Feature-by-feature within a phase (safer rollback).
- **Bootleg year pivot:** `Y ≥ 30 → 19YY`, `Y < 30 → 20YY`. Comfortable through ~2029.
- **NFT multi-LB rule:** If *any* matched LB is Private, the whole folder gets `-NFT` (conservative).
- **LBBCD deep-scrape:** Deferred — index page only.
- **Persistent offline map tile cache:** Deferred.
- **Map view as a whole:** Deferred (push to end of queue, possibly cut).
- **Defaults accepted as recommended:** flat-file auto-check cadence (`every_start`), GUI state file location (`data/gui_state.json`), per-section status colors (Private `#B3E5FC`, Missing `#E0E0E0`, needs-review orange ✎), backwards-compat (clean cut for broken code, coexistence otherwise), test bar (similar to `test_lb_master.py` where feasible, lighter for GUI-heavy where pytest can't reach), auto-incremental geocoding (yes, queued during flat-file apply — moot while Map is deferred).

## Implementation Status (last audited 2026-05-17)

Legend: ✅ shipped · 🟡 partial · ⬜ not started

| # | Feature section | Status | Notes |
|---|---|---|---|
| 0 | **Core `lb_master` table + reconciliation + history + manual overrides** | ✅ | Shipped 2026-05-16. `backend/db.py` has tables, `migrate_lb_master`, `reconcile_lb_status`, override helpers, stats. `backend/importer.py` and `backend/scraper.py` integrated. 9 endpoints under `/api/lb_master/*`. 27 pytest tests in `tests/test_lb_master.py`. |
| 0 | **Backup function** (`backup_database()`) | ✅ | Shipped 2026-05-16. `VACUUM INTO` with microsecond timestamps, keeps last 10. `POST /api/db/backup` endpoint live. DB Editor has "Backup DB Now" button. |
| — | **Master ↔ User data ownership model** (publish/subscribe, master export/import) | ✅ | Shipped 2026-05-17 (TODO-020). `MASTER_TABLES`/`USER_TABLES`/`MASTER_META_KEYS` constants in `db.py`. `export_master_db()` / `import_master_db()` with SHA256 manifest + schema-version guard. `POST /api/master/export` + `POST /api/master/import`. Curator mode checkbox in Setup tab. 13 tests in `tests/test_master_data.py`. GitHub release upload still deferred (TODO-022). |
| — | **Override export/import JSON tool** | ⬜ | No `/api/lb_master/overrides/export` or `/import` endpoint. |
| 5 | **Forum post guard for Private LBs** | ✅ | Shipped 2026-05-16. Backend 403 for private/missing in `preview_forum` and `post_forum`. Collection tab modal both pre-click and on 403 response. `is_postable_to_forum()` helper in `db.py`. |
| 6 | **Status filters across all appropriate GUI elements** | ✅ | Shipped 2026-05-17 (TODO-021). Lookup tab: filter combobox + Private/Missing row tinting. Attachments tree: batch page-level tinting. Rename tab: LB Found col tint. Lbdir: LB# col tint. `get_lb_statuses_batch()` in `db.py`. Shared `LBStatusComboBox` / `lb_status_style()` widget module not built (each tab inlined its own); Verify tab skipped (lb_number unavailable in results). |
| 7 | **`-NFT` suffix on folder names for Private LBs** | ✅ | Shipped 2026-05-17 (TODO-018). `backend/folder_naming.py` created with `apply_nft_suffix`, `strip_nft_suffix`, `has_nft_suffix`, `nft_discrepancy`. Rename tab applies suffix to proposed names and shows discrepancy colours (pale red/yellow/orange rows). Collection tab `_get_standard_lb_name()` calls `/api/lb_master/<lb>/nft`. `should_mark_nft()` in `db.py`. `GET /api/lb_master/<lb>/nft` endpoint. |
| 8 | **Persistent folder-to-LB linking (`lb_alias` + `folder_lb_link`)** | ⬜ | Both tables and the Rename tab "Link…" dropdown still need to be built. (TODO-019) |
| 9 | **Flat-file update check rework** | ⬜ | Existing `scraper.check_for_update()` still does the broken bynumber-page scrape. `flat_file_releases`/`flat_file_changelog` tables not created. |
| 10 | **Click-to-sort across all tables** | ⬜ | Existing DB Editor backend has `sort_col`/`sort_dir` already, but no GUI wiring; no `SortableTableItem`/`sort_key_for` helper module. |
| 11 | **Reliable column width persistence** | ✅ | `GuiStateStore` in `gui/widgets/state_store.py`. All tabs (Search, Collection×7, DbEdit, Lbdir, Rename) use `attach_table`. Window geometry also migrated. QSettings migration on first run. 2026-05-17. |
| 12 | **Bootleg-CD catalog (LBBCD)** | ⬜ | No scraper, no tables, no Bootlegs tab. |
| 13 | **Standardize folder name button** | ✅ | Shipped 2026-05-17. `build_standard_name()` in `backend/folder_naming.py`. `GET /api/folder_naming/standard/<lb>`. "Standardize Selected" button + right-click "Standardize Name" action in Rename tab. `RenameModel.update_state()`. Also fixed BUG-064 (`_on_strip_wrong_lb` now transitions state to `needs_rename`). |
| Map | **Map view of LB locations** | ⬜ | Plan extracted to [CC_MAP_FEATURE.md](CC_MAP_FEATURE.md). No `location_geocoded` table, no `gui/map_tab.py`. Deferred — lowest priority. |

**When implementing pending items, check the CHANGELOG before starting** — small follow-on fixes may have already touched the same files since the last plan-doc audit.

## Context

**Why this is needed.** Today the LosslessBob app has no single source of truth for "what is the status of LB-NNNNN?" The answer is reconstructed at query time by joining `entries.status`, the presence of rows in `checksums`, and (sometimes) the presence of rows in `entry_files`. This works but it:

- Makes search/collection UIs ambiguous (yellow-highlight for `status='missing'` doesn't distinguish "404 on website" from "we never tried" from "has checksums, no page").
- Provides no way to filter on or report against the three real-world categories the user thinks in: **Public LB**, **Private LB**, **Doesn't Exist**.
- Has no enumeration of gaps — `get_missing_lb_numbers()` exists but it conflates `status='missing'` with "never scraped".
- Cannot represent the transition where a Private LB becomes Public after the webmaster publishes a page.

**Intended outcome.** A persistent master table that holds one row per integer from 1 to `MAX(lb_number)`, each row carrying a current `lb_status` value. The table is the source of truth; everything else (search filters, collection filters, integrity reports, scrape planning) reads from it. Triggers and a reconciliation function keep it accurate as `checksums`, `entries`, and `entry_files` change.

The plan deliberately writes this file to `instructions/` for later review — no code changes yet.

---

## Status Definitions (Authoritative)

| Status | Code | Rule |
|---|---|---|
| **Public LB** | `public` | Row in `entries` with `status='ok'`. Has a webpage. Attachments/checksums irrelevant. **Majority case.** |
| **Private LB** | `private` | Has ≥1 row in `checksums`, AND no `entries` row with `status='ok'`. Webmaster hasn't published a page; checksums leaked via flat file. |
| **Doesn't Exist** | `missing` | No row in `entries` with `status='ok'`, no row in `checksums`, no row in `entry_files`. Truly absent. |

**Precedence** (when signals conflict, evaluate top-down):
1. `public` wins if a confirmed webpage exists (`entries.status='ok'`) **or** if attachments exist (presence of `entry_files` rows is proof a page existed at some point).
2. `private` wins if checksums exist without any webpage/attachment evidence.
3. `missing` is the residual.

**Attachments-only case → `public` + `needs_review` flag.** `entry_files` rows are only ever inserted by the scraper after parsing a successful page fetch, so their presence proves the LB existed publicly at some point. We classify it `public` (benefit of the doubt — content existed) but raise a `needs_review` flag so the user can confirm or override:
- If the page was depublished → user manually overrides to `private`.
- If truly removed → user manually overrides to `missing`.
- If still public (most likely — just a stale `entries` row) → user re-scrapes; reconciliation clears the flag.

Page-pulls are rare per user's domain knowledge, so this should fire infrequently.

**On "immutability".** The user described this as "immutable", but Private→Public transitions are explicitly mentioned. What they really want is **deterministic and persistent** — a stored value that doesn't drift between page loads, not one that can never change. The plan treats the table as authoritative-but-reconcilable.

---

## Schema Changes

### New table: `lb_master`

Add to [backend/db.py](../../Documents/losslessbob/backend/db.py) inside `init_db()`, using `CREATE TABLE IF NOT EXISTS` for idempotency (per CLAUDE.md).

```sql
CREATE TABLE IF NOT EXISTS lb_master (
    lb_number        INTEGER PRIMARY KEY,
    lb_status        TEXT NOT NULL CHECK (lb_status IN ('public','private','missing')),
    has_webpage      INTEGER NOT NULL DEFAULT 0,   -- entries.status='ok'
    has_checksums    INTEGER NOT NULL DEFAULT 0,   -- ≥1 row in checksums
    has_attachments  INTEGER NOT NULL DEFAULT 0,   -- ≥1 row in entry_files
    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_status_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    previous_status  TEXT,                          -- for tracking transitions, NULL if never changed
    manual_override  INTEGER NOT NULL DEFAULT 0,    -- 1 = user set status manually; reconciliation must NOT overwrite
    manual_status    TEXT,                          -- the user-set status, mirrors lb_status when override=1
    manual_notes     TEXT,                          -- user's reasoning for the manual classification
    manual_set_by    TEXT,                          -- 'user' (room for 'auto' later if needed)
    manual_set_at    TIMESTAMP,                     -- when the override was set / last edited
    needs_review     INTEGER NOT NULL DEFAULT 0     -- 1 = ambiguous auto-classification, user should review
);

CREATE INDEX IF NOT EXISTS idx_lb_master_status   ON lb_master(lb_status);
CREATE INDEX IF NOT EXISTS idx_lb_master_override ON lb_master(manual_override) WHERE manual_override = 1;
CREATE INDEX IF NOT EXISTS idx_lb_master_review   ON lb_master(needs_review) WHERE needs_review = 1;
```

Add column `needs_review INTEGER NOT NULL DEFAULT 0` to the table definition above — set to `1` by reconciliation whenever an LB lands in an ambiguous state that warrants user attention (currently: attachments-only-without-webpage). The user clears the flag by either re-scraping (which resolves the ambiguity) or setting a manual override.

**Override semantics:**
- When `manual_override = 1`, `reconcile_lb_status()` recomputes `has_webpage`/`has_checksums`/`has_attachments` (so the user can see current signals) but **does not change `lb_status`**.
- The `has_*` signals always reflect reality, even under override — they're informational and let the UI show the user "your manual status is X, but the data now looks like Y" so they can decide whether to clear the override.
- Clearing the override (`manual_override = 0`, blank the manual_* fields) restores automatic classification on the next reconcile.

### Optional transition log: `lb_status_history`

For auditing Private→Public flips (the webmaster-published case):

```sql
CREATE TABLE IF NOT EXISTS lb_status_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,
    old_status   TEXT,
    new_status   TEXT NOT NULL,
    changed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trigger_event TEXT  -- 'import', 'scrape', 'reconcile', 'manual'
);
CREATE INDEX IF NOT EXISTS idx_lb_history_lb ON lb_status_history(lb_number, changed_at DESC);
```

---

## Population & Reconciliation Logic

### One-time backfill (migration)

Add `migrate_lb_master()` to [backend/db.py](../../Documents/losslessbob/backend/db.py). Run from `init_db()` after schema creation, guarded by checking if `lb_master` is empty.

```python
def migrate_lb_master(conn):
    """Populate lb_master for all integers 1..MAX(lb_number) based on current data.
    Takes a DB backup first, then deletes redundant entries.status='missing' tombstones."""
    backup_database(reason="pre_lb_master_migration")
    max_lb = conn.execute(
        "SELECT MAX(lb_number) FROM checksums"
    ).fetchone()[0] or 0
    if max_lb == 0:
        return
    # Pre-compute the three signal sets in one pass each
    public_set   = {r[0] for r in conn.execute(
        "SELECT lb_number FROM entries WHERE status='ok'")}
    checksum_set = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM checksums")}
    attach_set   = {r[0] for r in conn.execute(
        "SELECT DISTINCT lb_number FROM entry_files")}
    rows = []
    for n in range(1, max_lb + 1):
        has_web = n in public_set
        has_chk = n in checksum_set
        has_att = n in attach_set
        if has_web:
            status = 'public'
        elif has_chk:
            status = 'private'
        else:
            status = 'missing'
        rows.append((n, status, int(has_web), int(has_chk), int(has_att)))
    conn.executemany(
        """INSERT OR REPLACE INTO lb_master
           (lb_number, lb_status, has_webpage, has_checksums, has_attachments)
           VALUES (?,?,?,?,?)""", rows)
    # Clean slate: remove redundant tombstones now that lb_master is authoritative
    conn.execute("DELETE FROM entries WHERE status='missing'")
    conn.commit()
```

### Incremental reconciliation

Add `reconcile_lb_status(conn, lb_number)` — recomputes a single row and updates if changed, logging to `lb_status_history`. **Skips updating `lb_status` if `manual_override = 1`**, but still refreshes the `has_*` columns and `last_status_at`.

**Where to call it:**
- `importer.py` after flat-file merge — recompute for every LB touched, and extend the table to the new max.
- `scraper.py` after every entry scrape (success → may flip `private`→`public`; 404 → may flip `public`→`missing` if attachments also vanish).
- `db.insert_missing_entry()` and related entry-mutation paths.
- New endpoint `POST /api/db/reconcile_lb_master` for a manual full rebuild.

### Triggers vs. application-level calls

**Recommendation: application-level, not SQL triggers.** Triggers across three source tables (`entries`, `checksums`, `entry_files`) get hairy with the precedence rules and would obscure the logic. A single `reconcile_lb_status()` Python function called from the existing mutation paths is easier to test and debug. The three mutation paths are already small and well-known.

---

## API Surface

Add to [backend/app.py](../../Documents/losslessbob/backend/app.py):

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/lb_master/stats` | `{public: N, private: N, missing: N, max_lb: N}` |
| `GET` | `/api/lb_master/<int:lb>` | Single row from `lb_master` plus joined entry metadata |
| `GET` | `/api/lb_master?status=public\|private\|missing&limit=&offset=` | Paginated list |
| `POST` | `/api/lb_master/reconcile` | Full rebuild; returns counts. Respects manual overrides. |
| `GET` | `/api/lb_master/history/<int:lb>` | Transition history for an LB |
| `PUT` | `/api/lb_master/<int:lb>/manual` | Set manual override. Body: `{status: 'public'\|'private'\|'missing', notes: '...'}`. Sets `manual_override=1`, writes history with `trigger_event='manual'`. |
| `DELETE` | `/api/lb_master/<int:lb>/manual` | Clear override. Sets `manual_override=0`, blanks `manual_*` fields, immediately reconciles. |
| `GET` | `/api/lb_master?override=1` | List all LBs with manual overrides (for the DB Editor's overrides panel). |

Existing `get_missing_lb_numbers()` should be deprecated in favor of `SELECT lb_number FROM lb_master WHERE lb_status='missing'` — keep the function but make it a thin wrapper for backwards compat.

---

## GUI Changes

### Search tab — [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py)

- **New column:** "Status" (between LB Number and Date), values `Public` / `Private` / `Missing`, color-coded:
  - Public → default
  - Private → light blue background
  - Missing → light gray background (replaces the current yellow-for-`status='missing'` logic)
- **New filter combobox:** `All / Public only / Private only / Missing only`, in addition to existing Owned/Xref filters.
- Remove the existing "Missing only" checkbox — superseded by the new Status filter.

### Collection tab — [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py)

- **"Missing from Collection" section:** Add a status filter so user can choose to include Private LBs (currently it only shows `status='ok'`, i.e. `public`). Some users may want to mark Private LBs as wishlist items.
- Add a "Status" column to the Missing-from-Collection table.

### DB Edit tab — [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py)

This is where the **manual status editing** lives.

- **"DB Integrity" sub-panel:**
  - Stats from `/api/lb_master/stats` (Public / Private / Missing / Max / Overrides / Needs Review).
  - "Reconcile All" button → `POST /api/lb_master/reconcile`.
  - "Show Needs Review" filter shortcut → loads only rows where `needs_review=1` into the browser below.

  *(Re-scrape Private LBs lives on the Setup tab — see below.)*

- **"LB Master" browser table:**
  - Columns: `LB Number | Status | Manual? | Has Webpage | Has Checksums | Has Attachments | Notes | Last Changed`
  - Filter combobox: `All / Public / Private / Missing / Manual Overrides Only`
  - Search box for jumping to a specific LB number.
  - Double-click a row → opens **Edit Status dialog**.

- **Edit Status dialog:**
  - Read-only header: LB number, current auto-computed status, current `has_*` signals.
  - Radio: `Public / Private / Missing` (defaults to current status).
  - Text area: "Notes (why you're overriding)" — required when overriding.
  - "Clear Override (use automatic classification)" button → `DELETE /api/lb_master/<lb>/manual`.
  - "Save" button → `PUT /api/lb_master/<lb>/manual` with `{status, notes}`. **Notes are required when the chosen status disagrees with the auto-computed status**; optional otherwise. Save is disabled until notes are filled in the required case.
  - When the chosen status disagrees with the auto-computed one, show a warning banner: "Your manual classification differs from the automatic signals. This is fine — your value will be preserved across reconciliations."

- **Visual indicator** in any table row that has `manual_override=1`: a small icon (e.g. ✎) or bold styling in the Status column, plus tooltip showing `manual_notes` and `manual_set_at`.

### Setup tab — [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) (if it exists)

- **Status bar:** replace `latest_lb` with `Public: N / Private: N / Missing: N / Max: N / Needs Review: N`.
- **"Re-scrape Private LBs" button** — manual trigger only, never automated. Reuses the existing scraper worker. Iterates every LB where `lb_status='private'` and re-fetches the page; reconciliation flips it to `public` if the webmaster has published it. Show progress (X of N), and on completion display a summary ("Promoted 3 LBs from Private to Public").
- **"Backup Database Now" button** — calls `POST /api/db/backup` with `reason='manual'`, then shows the backup path in a confirmation dialog.

---

## Consequences & Risks

1. **Reconciliation cost on flat-file import.** A typical Dylan flat file is ~tens of thousands of rows. The migration is O(max_lb) memory for the three sets (small) and one bulk `executemany` (fast). Should complete in seconds. *Not a perf risk.*

2. **Stale rows after schema migration.** First app launch after this change will run the backfill once. Need to guard with `SELECT COUNT(*) FROM lb_master` and skip if non-zero — but also offer a manual rebuild for users who suspect drift.

3. **Private→Public detection requires re-scraping.** The status table alone doesn't catch newly-published pages; the user needs to periodically rescrape Private LBs. Recommend adding a "Re-scrape all Private LBs" button to DB Edit tab (cheap — there are few Private LBs).

4. **The "Missing" classification is only as good as our scrape coverage.** An LB we've never tried to scrape and that isn't in the flat file will be classified `missing`. That's actually correct per the user's definition — but worth surfacing in docs.

5. **Backwards compatibility.** No existing API breaks. `get_missing_lb_numbers()` keeps working. The Search tab's yellow highlight changes, but the user is asking for a richer status concept anyway.

6. **The `entries.status` field becomes redundant** with `lb_master.has_webpage`. Keep both for now to avoid a bigger migration; revisit later.

7. **Flat-file re-import that lowers max LB.** Vanishingly unlikely but if it happens, the `lb_master` rows above the new max should be deleted. Add to reconciliation. **Caveat:** if any of those rows have `manual_override=1`, don't silently delete — surface them in the DB Editor as "orphaned overrides" and let the user decide.

8. **Manual overrides drifting from reality.** A user marks LB-12345 as `private` based on insider knowledge. Later, the scraper successfully fetches a page for it. The override means `lb_status` stays `private`, but `has_webpage` flips to 1 — the row visibly disagrees with itself. The Edit Status dialog should make this contradiction explicit so the user can either confirm or clear the override. We accept this complexity as the cost of letting human knowledge supersede automation.

---

## Files to Modify (Critical Path)

| File | Change |
|---|---|
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `lb_master` + `lb_status_history` tables in `init_db()`. Add `backup_database()`, `migrate_lb_master()` (deletes `status='missing'` tombstones), `reconcile_lb_status()`, `get_lb_status()`, `get_lb_master_stats()`, override export/import helpers. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add 8 new endpoints: 5 under `/api/lb_master/*`, override export/import, and `POST /api/db/backup`. |
| [backend/importer.py](../../Documents/losslessbob/backend/importer.py) | After merge, call `migrate_lb_master()` to (re)populate up to new max, then reconcile touched rows. |
| [backend/scraper.py](../../Documents/losslessbob/backend/scraper.py) | Call `reconcile_lb_status(conn, lb)` after every entry scrape (success and 404). |
| [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py) | Add Status column + filter combobox; remove old "Missing only" checkbox. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Add Status column + filter to Missing-from-Collection section. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Add Integrity panel with stats + Reconcile button + Private list. |
| `PROJECT.md` | Document new tables, endpoints, GUI columns. |
| `CHANGELOG.md` | Entry per implementation session. |
| `BUGS.md` | Open BUG entry for any edge case found during implementation. |
| `TODO.md` | Track "periodic re-scrape of Private LBs" as a follow-up. |

---

## Verification Plan

1. **Schema migration:** Delete `lb_master` row count check, restart app, confirm table populated and counts in `/api/lb_master/stats` sum to `MAX(lb_number)`.
2. **Public:** Pick a known LB with a scraped page. Confirm `lb_status='public'`. Search tab shows "Public" with no special background.
3. **Private:** Find an LB in `checksums` but not in `entries` (or with `entries.status != 'ok'`). Confirm `lb_status='private'`, blue background in Search.
4. **Missing:** Pick a gap number (e.g. one returned today by `get_missing_lb_numbers()` that's not in `checksums`). Confirm `lb_status='missing'`, gray background.
5. **Transition:** Manually set an LB to Private (delete its `entries` row), reconcile, then rescrape it and confirm `lb_status_history` shows `private`→`public`.
6. **Filter:** In Search tab, switch the Status combobox between Public/Private/Missing and confirm row counts match `/api/lb_master/stats`.
7. **Idempotency:** Restart the app twice; confirm `lb_master` row count unchanged and no duplicate rows in `lb_status_history`.
8. **Flat-file re-import:** Re-run an import on the same file. Confirm `lb_master` row count and status distribution unchanged.
9. **Manual override — set:** In DB Editor, pick an LB currently auto-classified as `public`, edit it to `private` with notes "test override". Confirm `manual_override=1`, `lb_status='private'`, row marked with ✎ in the browser, history row written with `trigger_event='manual'`.
10. **Manual override — persists through reconcile:** Click "Reconcile All". Confirm overridden LB keeps its manual status; non-overridden rows recompute normally.
11. **Manual override — clear:** Open the same LB, click "Clear Override". Confirm `manual_override=0`, `lb_status` reverts to auto-computed value, manual_* fields blanked, new history row written.
12. **Manual override — drift indicator:** Override an LB as `missing` while it has a webpage. Confirm Edit dialog shows the "your manual value differs" banner and that `has_webpage=1` in the row even though `lb_status='missing'`.

---

## Resolved Decisions

1. **Delete `entries.status='missing'` tombstones during migration.** Clean slate. The migration removes them after `lb_master` is populated. A full DB backup is taken first (see below).
2. **Colors:** Missing = light gray background, Private = light blue background, Public = default (no background). `needs_review=1` rows get an orange ✎ badge in the Status column regardless of underlying status.
3. **Manual override notes:** required when the manual status disagrees with the auto-computed status (the case where reasoning matters most), optional otherwise. Optional when clearing.
4. **Override export/import + full DB backup:** both ship with this feature.

## Backup / Restore (ships with this feature)

**Status:** 🟡 `backup_database()` + `POST /api/db/backup` + Backup DB Now button shipped 2026-05-16. Override export/import JSON not started. Auto-backup before `migrate_lb_master` and reconcile-all is in code.

### Full DB backup function

Add `backup_database(reason: str) -> Path` to [backend/db.py](../../Documents/losslessbob/backend/db.py).

- Uses SQLite's `VACUUM INTO` to produce a consistent snapshot file (safer than copying the live DB).
- Output: `data/backups/losslessbob_YYYY-MM-DD_HHMMSS_<reason>.db`
- Returns path to backup file. Logs to `logging` at INFO level.
- Caller passes `reason` (e.g. `"pre_lb_master_migration"`, `"pre_reconcile_all"`, `"manual"`) so backup filenames are self-describing.

**Called automatically before:**
- `migrate_lb_master()` first run (reason=`"pre_lb_master_migration"`) — protects against the tombstone deletion.
- `POST /api/lb_master/reconcile` (reason=`"pre_reconcile_all"`) — full rebuild is destructive enough to warrant.

**Exposed as:**
- `POST /api/db/backup` (body: `{reason: 'manual'}` default) → returns `{path, size_bytes}`.
- Setup tab gets a "Backup Database Now" button next to the existing import controls.

**Retention:** keep last 10 backups, prune older ones in `backup_database()` after a successful write. Configurable later if needed.

### Override export / import

- `GET /api/lb_master/overrides/export` → JSON dump: `[{lb_number, manual_status, manual_notes, manual_set_at}, ...]` for every row with `manual_override=1`.
- `POST /api/lb_master/overrides/import` (body: same JSON) → upserts overrides, writes `lb_status_history` rows with `trigger_event='import'`. Skips rows where lb_number > current max_lb (warns user).
- DB Editor's Integrity panel gets two buttons: **Export Overrides** (saves to user-chosen path) and **Import Overrides** (loads from user-chosen path, shows preview + confirm dialog before applying).

---

## Data Ownership Model (Master vs. User Data)

**Status:** ✅ Shipped 2026-05-17 (TODO-020). `MASTER_TABLES`/`USER_TABLES`/`MASTER_META_KEYS`/`MASTER_SCHEMA_VERSION` constants in `db.py`. `export_master_db()` / `import_master_db()` with SHA256 manifest and schema-version guard. `POST /api/master/export` + `POST /api/master/import`. Curator-mode checkbox in Setup tab. 13 tests in `tests/test_master_data.py`. **Still pending:** GitHub release upload via `gh` CLI (TODO-022); override export/import JSON endpoints.

**Curator role.** The repository owner (kuddukan) is responsible for curating the **master data** — the canonical truth about the LosslessBob archive. Other end users install the app and receive periodic master-data updates from the curator. Their personal collection/wishlist/notes never leave their machine.

This split must be reflected in the schema so master data can be exported and shipped without leaking user-specific information.

### Classification

| Bucket | Tables | Ships to other users? |
|---|---|---|
| **Master data** | `entries`, `checksums`, `entry_files`, `lb_master` (including manual overrides), `lb_status_history`, `entry_changes`, `entries_fts` | **Yes** — curator publishes; users pull. |
| **User data** | `my_collection`, `collection_meta`, `my_wishlist`, `integrity_events`, `torrents`, `rename_history`, `forum_posts` | **No** — strictly local. |
| **Mixed** | `meta` | Some keys are master (`import_hash`, `last_import_date`, `last_lb_number`, `master_version`), some are user config (`auto_scrape`, `scrape_delay_ms`, `qbt_*`, etc.). Split via whitelist on export. |

**Architecture:** Keep one SQLite file. Export filters out user tables. Refactoring to two attached DBs is a larger surgery — defer until pain warrants it.

### Master Data Publish (curator side)

`POST /api/master/export`:
- `VACUUM INTO` a snapshot → drop every user-data table → filter `meta` to master keys → set `master_version` (timestamp).
- Output: `data/exports/losslessbob_master_YYYY-MM-DD_HHMMSS.db` + `.gz` compressed copy + sidecar `.manifest.json` with version, counts, SHA256 (of the uncompressed file).
- The export endpoint **verifies** that no user-data tables exist in the output before writing the manifest — if any are present, abort with an error.
- Setup tab (curator-only): **"Publish Master Update"** button (see GitHub workflow below).

### GitHub Release Publishing (curator workflow)

The "Publish Master Update" button does export + upload in one flow, using the `gh` CLI for GitHub interaction.

#### Configuration (stored in local `meta`, never shipped)

| Key | Example | Notes |
|---|---|---|
| `github_repo` | `kuddukan/losslessbob` | `owner/name` form. Set once via Setup tab field. |
| `release_tag_scheme` | `date` \| `semver` | Default `date`. |
| `release_mark_latest` | `1` \| `0` | Default `1`. |
| `release_default_prerelease` | `0` \| `1` | Default `0`. |

#### Tag scheme

- **Default (`date`):** `master-YYYY-MM-DD`. Same-day re-releases auto-suggest `.2`, `.3`, etc. by querying `gh release view <tag>` first.
- **Optional (`semver`):** `v<major>.<minor>.<patch>` — user types manually; no auto-bump.
- Dialog always shows the tag field as editable so the curator can override either scheme on the fly.

#### Publish dialog UX

```
─── Publish Master Update ───────────────────────────
  Export file:  losslessbob_master_2026-05-16_183000.db.gz  (28 MB)
  SHA256:       a3f2…

  Repository:   kuddukan/losslessbob          [Edit]
  Tag:          master-2026-05-16             [Edit]   ← auto-filled
  Title:        Master data 2026-05-16        [Edit]
  Notes:        (auto-generated, editable, multiline)
                ─────────────────────────────────────
                12 entries promoted Public→Private
                3 new manual overrides:
                  - LB-12345: private  "confirmed depublished"
                  - LB-67890: missing  "truly removed"
                  - LB-11111: public   "rescraped 2026-05-16"

  ☐ Mark as pre-release
  ☑ Mark as latest release

  [Cancel]                                   [Publish]
─────────────────────────────────────────────────────
```

#### Behind the button (step-by-step)

1. **Run export** — `POST /api/master/export` produces `.db`, `.db.gz`, and `.manifest.json` in `data/exports/`.
2. **Check `gh` auth** — `gh auth status`. If not authed, dialog shows: "Run `gh auth login` in your terminal, then try again." Link/instructions inline.
3. **Compute default tag** — based on `release_tag_scheme` and today's date.
4. **Tag collision check** — `gh release view <tag> --repo <repo>`. If exists, bump suffix (`.2`, `.3`…) and pre-fill the bumped tag with a warning banner.
5. **Auto-generate notes** — query `lb_status_history` for rows where `changed_at > meta.master_published_at`, summarize counts by transition (e.g. `public→private: 5`), then list every override created/edited in that window with its `manual_notes`.
6. **User edits anything they want** in the dialog, clicks Publish.
7. **Upload via `gh`** — subprocess call:
   ```
   gh release create <tag> \
     <export.db.gz> <export.manifest.json> \
     --repo <repo> \
     --title "<title>" \
     --notes "<notes>" \
     [--latest | --prerelease]
   ```
   Capture stdout to extract the release URL.
8. **On success** — update `meta.master_published_at` and `meta.master_version` to match what was shipped. Show a result dialog with the release URL, "Copy to Clipboard" and "Open in Browser" buttons.
9. **On failure** — surface stderr from `gh` verbatim, leave `meta.master_published_at` unchanged so retrying produces the same release notes.

#### Safety nets

- `.gitignore` must include `data/losslessbob.db`, `data/backups/`, `data/exports/` — confirm/add as part of implementation. Prevents accidental `git add` of any DB file.
- Export validation (see Master Data Publish above) ensures no user tables can ever land in the uploaded file even if the drop list is mis-edited.
- The publish dialog shows file size and a one-line summary of contained tables — final visual check before upload.
- Setup tab field for `github_repo` must be filled before the Publish button enables.

#### Files to Modify (additions for GitHub publishing)

| File | Change |
|---|---|
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add `POST /api/master/publish_github` that wraps export + `gh release create`. Returns `{release_url, tag, sha256}`. |
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add helpers `compute_default_tag()`, `generate_release_notes(since_ts)`, `tag_exists_on_github(repo, tag)`. |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | Add `github_repo` config field, "Publish Master Update" button, publish dialog with editable tag/title/notes. |
| `.gitignore` | Add `data/losslessbob.db`, `data/backups/`, `data/exports/` if not already present. |
| `requirements.txt` | No new Python deps — `gh` is a system binary, not a pip package. Document the `gh` CLI dependency in README. |
| `README.md` | Add curator setup section: install `gh`, run `gh auth login`, set `github_repo` in Setup tab. |

### Master Data Subscribe (end-user side)

`POST /api/master/import` (uploads `.db` file):
- Validate manifest SHA256 → backup local DB → `ATTACH DATABASE` incoming → for each master table: `DELETE FROM main.<t>; INSERT INTO main.<t> SELECT * FROM incoming.<t>` → only overwrite master-whitelisted `meta` keys → `DETACH`.
- Setup tab: **"Install Master Update"** button.

### Curator-only UI Mode

`meta.is_curator='1'` unlocks: Publish button, write access to manual-override editing. Non-curators see overrides read-only. Never ship `is_curator` in the master export.

### Consequences (additions)

9. **Override edits ship to everyone.** Your `manual_notes` becomes user-facing text. Add a "Review Before Publish" step that lists every override + notes so you can scrub anything not fit for distribution.
10. **Master imports overwrite local auto-classifications.** Surface this in the import summary ("12 LB statuses changed from your local values to master values").
11. **Schema versioning.** Add `master_schema_version` to `meta`. Refuse imports where incoming version > local version (forces app upgrade first).

---

## First-Time Master Generation Workflow (Curator Step-by-Step)

**Status:** 🟡 Procedural document, not a code feature. Step 1 (migration) and Step 2 mechanics (`migrate_lb_master`, `reconcile_lb_status`, `needs_review` flag) are shipped. Steps 3–5 (Re-scrape Private LBs, review, verify) are now supported by the GUI buttons and DB Editor. Steps 6–8 (Pre-publish review, Publish Master Update with GitHub release upload) are partially done: the export/import workflow is live, but GitHub release upload via `gh` CLI is deferred (TODO-022).

This is the operational sequence **you (kuddukan) walk through once** to bootstrap the master table from your existing DB and ship the first master release. Assumes the schema/code from above is already implemented.

### Step 0 — Preflight (5 min)
- Confirm your DB is the most current state you want to canonize. Re-run any pending flat-file imports first.
- In the Setup tab, click **"Backup Database Now"** (separate from the automatic pre-migration backup, just for paranoia).
- Note the current stats from `/api/db/stats`: total checksums, total entries with `status='ok'`, max LB. Write these numbers down — they're your sanity check after migration.

### Step 1 — Run the migration (~seconds)
- Restart the app, or hit a new endpoint `POST /api/lb_master/migrate` if you want explicit control.
- `migrate_lb_master()` fires:
  1. Auto-backup → `data/backups/losslessbob_<ts>_pre_lb_master_migration.db`
  2. Compute `public_set`, `checksum_set`, `attach_set` from existing tables.
  3. Insert 1 row per integer 1..max_lb into `lb_master`.
  4. Set `needs_review=1` for any row where `has_attachments=1` AND `has_webpage=0`.
  5. Delete `entries` rows where `status='missing'`.
- Check `/api/lb_master/stats`. Sanity check:
  - `public + private + missing == max_lb` (must be true).
  - `public count` should be very close to your pre-migration "entries with status='ok'" number.
  - `private count` should equal "LBs in checksums but not in entries-with-status-ok".
  - `missing count` should equal max_lb − public − private.

### Step 2 — Triage `needs_review` (minutes to hours, depending on count)
- DB Editor → "Show Needs Review" filter shortcut.
- For each row, decide:
  - Re-scrape (Setup tab can also trigger a single-LB scrape) → if page now returns 200, reconciliation auto-clears the flag and confirms `public`.
  - Manually override to `private` (page depublished, content still exists) — with notes.
  - Manually override to `missing` (confirmed truly removed) — with notes.
- Expected volume: very low based on your domain knowledge (page-pulls are rare). If `needs_review` count is unexpectedly high, stop and investigate — likely a scraper bug left orphaned `entry_files` rows.

### Step 3 — Re-scrape Private LBs (optional, minutes)
- Setup tab → **"Re-scrape Private LBs"** button.
- This catches the case where the webmaster has published a page since the last scrape. Each promotion from `private`→`public` is logged in `lb_status_history`.
- Review the summary dialog. If 0 promotions, you're done. If several, that's normal.

### Step 4 — Review and hand-classify (variable)
- DB Editor → filter by `Private`. Scan the list for any LBs you personally know should be `missing` or `public` based on out-of-band info. Override with notes.
- DB Editor → filter by `Missing`. Look for any LB you know should actually be `private` (e.g., you've seen checksums elsewhere that aren't in the flat file yet). Override with notes.
- For each override: ask yourself "would I be comfortable shipping this note to every user?" If not, rewrite it cleanly.

### Step 5 — Verify (5 min)
- Check the verification list (#1–#12 above) on your own DB before shipping.
- Spot-check 5 random LBs from each status bucket: open them in the Search tab, confirm the displayed status makes sense.
- Run a Reconcile All from DB Editor. Counts shouldn't change. If they do, you have a reconciliation bug — fix before publishing.

### Step 6 — Pre-publish review
- DB Editor → "Manual Overrides Only" filter. Read every note one more time. This is the only place where your editorial voice ships verbatim to every downstream user.
- If you want a paper trail, click **Export Overrides** to save a JSON copy alongside the eventual `.db` file. Useful for diffing against the next release.

### Step 7 — Publish (1 min)
- Setup tab → **"Publish Master Update"** button.
- Confirm dialog: shows version, status counts, override count, output path.
- File written to `data/exports/losslessbob_master_<ts>.db` + manifest sidecar.
- Upload `.db` + `.manifest.json` to your distribution channel (GitHub release, web mirror, etc.).
- Announce to users. End users click **"Install Master Update"** in their Setup tab and point at the downloaded file.

### Step 8 — Iterate for subsequent releases
- Future releases are much faster: just `reconcile`, triage any new `needs_review`, publish.
- The `lb_status_history` table gives you a changelog between releases — query rows where `changed_at > last_published_at` to see what flipped.

### Files to Modify (additions for master/user split + publish workflow)

| File | Change |
|---|---|
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `MASTER_TABLES`, `USER_TABLES`, `MASTER_META_KEYS` constants. Add `export_master_db()`, `import_master_db()`. Add `master_schema_version` constant. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add `POST /api/master/export`, `POST /api/master/import`, `POST /api/lb_master/migrate` (explicit trigger). |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | "Publish Master Update" (curator-only), "Install Master Update", curator-mode indicator. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Make override editing read-only when `is_curator != '1'`. |
| `PROJECT.md` | Document master/user split, curator workflow, publish/subscribe mechanism. |

### Verification (additions)

13. **Export excludes user data:** Add a row to `my_collection`, export master, open exported `.db` in `sqlite3`, confirm `my_collection` table is empty/missing.
14. **Import preserves user data:** Populate `my_collection`, import a master snapshot, confirm rows unchanged.
15. **Import preserves user `meta` keys:** Set `meta.search_page_size='100'` locally, import master whose meta has `search_page_size='25'`, confirm local still `'100'`.
16. **Override propagation:** Curator overrides LB-X. Export. Wipe a clean test install. Import. Confirm LB-X has the override + notes.
17. **Schema-version guard:** Bump `master_schema_version` in an export, try importing into older app build, confirm rejection.

---

## Ancillary Feature: Forum Post Guard for Private LBs

**Status:** ✅ Shipped 2026-05-16. Backend 403 + Collection tab modal + `is_postable_to_forum()` helper all live. Preview endpoint also guarded.

**Why.** Private LBs are items the webmaster has deliberately not published a webpage for. Posting about them on the public forum would expose unreleased content — directly defeating the webmaster's choice to keep them private. Private items can still legitimately appear in a user's personal collection (the user owns the recordings), so the guard belongs at the *forum-post action*, not at collection inclusion.

### Guard placement (defense in depth)

**Backend — [backend/app.py:1232](../../Documents/losslessbob/backend/app.py#L1232)** (`POST /api/entry/<lb>/post_forum`):
- Before calling `post_lb_topic`, look up `lb_master.lb_status` for the LB.
- If status is `private`: return HTTP 403 with `{"error": "lb_private", "message": "LB-{N} is marked Private. Forum posting is blocked to avoid exposing unreleased content."}`.
- If status is `missing`: return HTTP 403 with `{"error": "lb_missing", "message": "LB-{N} is marked as not existing. There is nothing to post about."}`.
- Public LBs proceed normally.
- Also guard the preview endpoint (`GET /api/entry/<lb>/forum_preview` near [app.py:1215](../../Documents/losslessbob/backend/app.py#L1215)) the same way — no point previewing a post you can't make.

**GUI — [gui/collection_tab.py:546](../../Documents/losslessbob/gui/collection_tab.py#L546)** ("Post to Forum" button):
- When a collection row is selected, fetch its `lb_status` (already loaded if we add a Status column to the collection table per earlier GUI changes; otherwise one-shot lookup).
- If `private` or `missing`: disable the button, tooltip = "Posting blocked: this LB is marked {Private|Missing}".
- If user somehow clicks anyway (race/stale data) and the backend returns 403: show a modal dialog:
  ```
  ─── Forum Post Blocked ──────────────────────
    LB-12345 is marked Private.
    
    Posting to the forum would expose content
    that the webmaster has chosen not to
    publish on the LosslessBob website.
    
    If you believe this status is wrong, you
    can request the curator to review it.
    
                              [OK]
  ─────────────────────────────────────────────
  ```
  Single OK button. No "Proceed Anyway" escape hatch — this is a hard block.

### Manual override interaction

The guard reads `lb_master.lb_status` directly, which already respects manual overrides. So:
- Curator manually overrides an auto-`public` LB to `private` → forum posting now blocked on the next master release.
- Curator manually overrides an auto-`private` LB to `public` → forum posting now allowed.

No special-casing needed.

### Edge cases

- **`needs_review=1` rows that are still classified `public`.** These are auto-classified Public (attachment-only case) but the curator hasn't confirmed. Recommendation: **still allow posting**, since `public` is the active classification. The curator's job is to triage `needs_review` before publishing the master update; once shipped, it's authoritative.
- **LB not in `lb_master` at all.** Shouldn't happen post-migration, but if it does (e.g. corrupted state), block with a generic "status unknown" error rather than silently allowing.
- **Existing forum posts for items now marked Private.** The `forum_posts` table records past posts; this feature does not retroactively delete forum posts or block viewing the history. Existing posts on the actual forum remain (we can't unpost them anyway). Show a small warning icon next to past-post log rows whose LB is now Private — purely informational.

### Files to Modify

| File | Change |
|---|---|
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add status check at top of `post_forum()` (line ~1233) and `forum_preview()` (line ~1215). |
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add helper `is_postable_to_forum(lb_number) -> tuple[bool, str|None]` returning `(allowed, reason)`. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Disable "Post to Forum" button + tooltip when selected LB is Private/Missing. Handle 403 response with the modal above. |

### Verification

18. **Backend block — Private:** Override an LB to `private`. `curl -X POST /api/entry/<lb>/post_forum` → HTTP 403 with `error=lb_private`.
19. **Backend block — Missing:** Pick a `missing` LB. Same call → HTTP 403 with `error=lb_missing`.
20. **Backend allow — Public:** Pick a `public` LB. Same call → proceeds (mock or test against staging forum).
21. **Preview block:** `GET /api/entry/<private_lb>/forum_preview` → HTTP 403.
22. **GUI button state:** Select a Private LB in Collection tab → "Post to Forum" button is greyed out with the blocking tooltip.
23. **GUI modal fallback:** Force a race (e.g. tamper with cached status to make the button enabled for a Private LB, click it) → backend returns 403 → modal appears with single OK button → no post is made.
24. **Override flip:** Take a Public LB that has a forum post enabled in the UI. Override to Private. Refresh — button is now disabled.

---

## Ancillary Feature: Status Filters Across All Appropriate GUI Elements

**Status:** ✅ Shipped 2026-05-17 (TODO-021). Search, Collection (My Collection + Missing), Lookup (filter combobox + Private/Missing row tinting), Attachments tree (batch page-level background tinting), Rename tab (LB Found column tint), Lbdir (LB# column tint). `get_lb_statuses_batch()` in `db.py`. **Not done:** shared `LBStatusComboBox` / `lb_status_style()` widget module (each tab inlined its own); Verify tab skipped (lb_number not in verify results); "Missing only" → "Incomplete matches only" rename in Lookup not done.

**Why.** The `lb_master` status (Public / Private / Missing) is meaningless to users if it only surfaces in one tab. Every place LB numbers are browsed or filtered should expose the same status concept, with the same visual language, so the user builds a single mental model. This section enumerates every GUI element and prescribes the right treatment.

### Shared Components (build these first, reuse everywhere)

To prevent drift, three reusable pieces:

1. **`LBStatusComboBox`** widget — a `QComboBox` pre-populated with: `All`, `Public only`, `Private only`, `Missing only`, `Needs review only`. Emits the canonical status code (`None` for All, `'public'`, `'private'`, `'missing'`, `'needs_review'`). Used wherever status filtering appears.

2. **`lb_status_style(status, needs_review)` → `(bg_color, fg_color, icon)`** helper — single source of truth for colors:
   - `public` → no background (default)
   - `private` → light blue background
   - `missing` → light gray background
   - `needs_review=1` → orange ✎ icon overlaid on whatever the underlying color is

3. **`StatusCell`** convenience function — given a Qt table cell and an LB row, applies background color + status icon + tooltip showing `manual_notes` (if overridden) or "Auto-classified".

All tabs below use these helpers. New colors/icons changed in one place propagate everywhere.

### Per-Tab Treatment

| Tab | Treatment | Priority |
|---|---|---|
| Search | Status column + filter combobox | Already planned |
| Collection — My Collection | Status column + filter combobox | **Add** |
| Collection — Missing from Collection | Status column + filter combobox | Already planned |
| DB Editor — LB Master browser | Full status filter + column | Already planned |
| Setup — status bar | Counts per status | Already planned |
| Lookup — Summary table | Status column + filter combobox + Private warning | **Add** |
| Lookup — Detail table | Status badge on each LB cell | **Add** |
| Attachments — tree view | Status badge on each LB node + filter combobox | **Add** |
| Rename — LB Found column | Status badge inline + warning row coloring | **Add** |
| Verify — Summary table | Status column (when folder name has LB-NNNNN) | **Add (low priority)** |
| Lbdir — Summary table | Status column (LB# column already exists) | **Add (low priority)** |
| Spectrogram | None — folder-centric, status orthogonal | Skip |
| Theme | None — UI configuration only | Skip |

### Details Per Newly-Added Tab

#### Lookup tab — [gui/lookup_tab.py](../../Documents/losslessbob/gui/lookup_tab.py)

- **Summary table:** Insert "Status" column after LB Number. Use `StatusCell`. Default sort doesn't change.
- **Detail table:** When the "LB Number" cell is populated, apply background color via `lb_status_style()`. No new column — keeps the row narrow.
- **New filter combobox** `LBStatusComboBox` placed next to the existing "Best match only" / "Missing only" checkboxes.
- **Naming clash to fix:** The existing "Missing only" checkbox means "rows where the lookup found some checksums but is missing others" — totally different from `lb_status='missing'`. Rename the existing checkbox to **"Incomplete matches only"** to disambiguate. Document this in CHANGELOG.
- **Private warning on lookup result:** When a checksum lookup result includes a Private LB, show a banner above the summary: "⚠ This lookup matched 2 Private LBs. Do not post these to the forum." Reinforces the forum-post guard and educates users about why filtering matters.

#### Collection tab — [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) — "My Collection" section

- **New "Status" column** between "LB Number" and "Date".
- **New filter combobox** `LBStatusComboBox` in the existing toolbar (next to whatever sort/search controls exist for the My Collection section).
- **Critical:** Private items in "My Collection" must be visually distinct because the "Post to Forum" button is blocked for them. The status column makes the reason obvious before the user clicks and gets the blocking modal.

#### Attachments tab — [gui/attachments_tab.py](../../Documents/losslessbob/gui/attachments_tab.py)

- **Tree view:** Each top-level `LB-XXXXX` node gets a colored chip/icon next to it indicating status. Implementation: `QTreeWidgetItem.setBackground(0, color)` and `setIcon(0, icon)`.
- **Missing-on-right list:** This already shows "missing" in the *attachments-cache* sense ("we haven't downloaded the page"), distinct from `lb_status='missing'`. Add a Status column to this list too, and rename the existing toggle to **"Not cached locally"** to disambiguate from the new status filter.
- **New filter combobox** `LBStatusComboBox` placed alongside the existing Cached / Missing toggle. The two filters compose (e.g., "Public only AND not cached locally").

#### Rename tab — [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py)

- **"LB Found" column:** When populated with a single LB, add the status background color + tooltip. Multiple LBs (comma-separated) → no status color, but tooltip lists each LB's status.
- **Warning state:** If `LB Found` resolves to a `missing` LB, treat as a soft warning — color the whole row pale orange and add a tooltip "This folder's name maps to LB-{N} which is marked as not existing. Likely a typo or stale folder." Don't block renaming; this is curator-grade info, not a hard rule.
- **Private LBs are fine to rename** — no warning needed. Renaming a folder to match a Private LB is a normal workflow if the user owns the recording.
- **No filter combobox** — the rename tab's primary filter is by rename state (has_lb, needs_rename, wrong_lb, multiple_ids), which is orthogonal to LB status. Adding a status filter would clutter without much value.

#### Verify tab — [gui/verify_tab.py](../../Documents/losslessbob/gui/verify_tab.py) and Lbdir tab — [gui/lbdir_tab.py](../../Documents/losslessbob/gui/lbdir_tab.py)

- **Summary tables:** Extract LB from folder name (Verify) or from existing LB# column (Lbdir). Apply `StatusCell` background to the Folder/LB# column.
- **No new filter combobox** initially — these tabs operate on folder lists the user manually adds, so volume is low. If user demand emerges, add the combobox in a later iteration.
- **Low priority — implement after the high-priority tabs are stable.**

### Consistency Rules (enforce during code review)

1. **Same combobox labels everywhere:** "All / Public only / Private only / Missing only / Needs review only". Never paraphrase ("Show all", "Public LBs", etc.).
2. **Same colors everywhere:** via `lb_status_style()`. Never hardcode a color in a tab file.
3. **Same icon for needs_review:** orange ✎. Used as overlay, not replacement, of the status color.
4. **Same tooltip pattern on status cells:** `"{Status} — {auto-classified | manual override: {notes}}"`.
5. **Renaming clashes:** Two existing controls collide with the new status vocabulary and MUST be renamed in the same PR:
   - Lookup tab "Missing only" → "Incomplete matches only"
   - Attachments tab "Missing" toggle → "Not cached locally"
   Document both renames in CHANGELOG as user-visible changes.

### Files to Modify

| File | Change |
|---|---|
| [gui/styles.py](../../Documents/losslessbob/gui/styles.py) | Add `lb_status_style()` helper + color constants. |
| New: `gui/widgets/lb_status_widgets.py` | `LBStatusComboBox`, `StatusCell` helper. Reused everywhere. |
| [gui/lookup_tab.py](../../Documents/losslessbob/gui/lookup_tab.py) | Status column on summary + detail, status filter, rename "Missing only" → "Incomplete matches only", Private warning banner. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Status column on My Collection table, status filter combobox. (Missing-from-Collection already covered.) |
| [gui/attachments_tab.py](../../Documents/losslessbob/gui/attachments_tab.py) | Status badge on tree nodes, status filter, rename "Missing" toggle → "Not cached locally". |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | Status background on LB Found cell, orange row warning for missing LBs. |
| [gui/verify_tab.py](../../Documents/losslessbob/gui/verify_tab.py) | Status background on Folder column (low priority). |
| [gui/lbdir_tab.py](../../Documents/losslessbob/gui/lbdir_tab.py) | Status background on LB# column (low priority). |
| `CHANGELOG.md` | Document the two control renames as user-visible. |

### Verification

25. **Combobox consistency:** Open every tab with an `LBStatusComboBox`; confirm identical label text and ordering.
26. **Color consistency:** Set up an LB known to be Private. Find it on Search, Collection (both sections), Lookup summary, Attachments tree, Rename, DB Editor. Confirm identical background color everywhere.
27. **Needs-review badge:** Override the test LB to trigger `needs_review=1`. Confirm orange ✎ appears in every tab.
28. **Lookup Private warning:** Run a lookup whose match includes a Private LB. Confirm the warning banner appears with the count.
29. **Rename warning:** Place a folder named `LB-99999-test` where LB-99999 is `missing`. Confirm row turns pale orange with tooltip.
30. **Filter composition (Attachments):** Set status filter to "Public only" AND cached-toggle to "Not cached locally"; confirm intersection of both filters is displayed.
31. **Rename collision check:** Confirm old "Missing only" / "Missing" toggles are gone and the new names appear; manually test that the new "Incomplete matches only" still filters by the original incomplete-match semantic, not by `lb_status`.

---

## Ancillary Feature: Append `-NFT` to Folder Names for Private LBs

**Status:** ✅ Shipped 2026-05-17 (TODO-018). `backend/folder_naming.py` created with `apply_nft_suffix`, `strip_nft_suffix`, `has_nft_suffix`, `nft_discrepancy`. Rename tab applies suffix to all proposed names and shows discrepancy row colours (pale red = missing NFT, pale yellow = stale NFT, pale orange = NFT on missing LB). Collection tab `_get_standard_lb_name()` appends `-NFT` via `/api/lb_master/<lb>/nft`. `should_mark_nft()` in `db.py`. `GET /api/lb_master/<lb>/nft` endpoint.

**Why.** `NFT` = Not For Trade, the lossless-audio community convention for marking items that must not be shared publicly. Private LBs (no webpage published) fit exactly this category — the webmaster has chosen not to release them, so users with copies must mark folders accordingly. Embedding `-NFT` directly in the folder name makes the constraint travel with the data: any future tool, script, or human looking at the folder sees the restriction immediately, even if they don't have access to this app's DB.

This is automatic: anytime the app *proposes* a folder name and the matched LB is `private`, the proposal includes `-NFT`. The user can still edit before accepting.

### Naming Rule

**Position:** `-NFT` is the **final suffix**, after the LB identifier and any xref tags.

Examples:
- Public: `1965-08-28_Forest_Hills_NY-LB-04321`
- Private: `1965-08-28_Forest_Hills_NY-LB-04321-NFT`
- Private with xref: `1965-08-28_Forest_Hills_NY-LB-04321-x12345-NFT`

**Idempotency:** If the input folder name (or the would-be proposed name) already ends in `-NFT` (case-insensitive), do **not** double-append. Normalize to uppercase `-NFT` if it was lowercase.

**Status changes after rename:** Folder renames are one-shot user actions. We do not retroactively re-rename folders when an LB flips Public→Private or vice versa. Instead, the Rename tab surfaces the mismatch (see Discrepancy Detection below) so the user can choose to act.

### Where the Suffix Gets Applied

#### 1. Rename tab — [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py)

The proposal logic at lines 169–171 and 339–345 builds names via `_fmt_lb()` + concatenation. Wrap the final proposed name with a new helper `_apply_status_suffix(name: str, lb_status: str) -> str`:

```python
def _apply_status_suffix(name: str, lb_status: str) -> str:
    """Append -NFT if LB is private. Idempotent."""
    if lb_status == 'private':
        if not name.upper().endswith('-NFT'):
            return f"{name}-NFT"
        # Normalize casing if it was lowercase
        return name[:-4] + '-NFT' if name.endswith('-nft') else name
    return name
```

Apply at every site where a `proposed` string is constructed in the rename tab. The status is read from `lb_master.lb_status` (respects manual overrides automatically).

**Multi-LB folders:** If `_fmt_lb()` returns comma-separated LBs (`multiple_ids` state), apply `-NFT` only if **any** of the matched LBs is Private. The conservative default — one private LB in a match list contaminates the whole folder. Show a tooltip on those rows explaining "Marked NFT because LB-X is Private."

#### 2. Collection tab — [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py)

The `_get_standard_lb_name(lb)` method builds the canonical name. Modify it to consult `lb_master.lb_status` and apply the same `_apply_status_suffix()` helper. The "Standard: {std_name}" preview dialog at line 2475 will then naturally show the `-NFT` suffix when applicable.

#### 3. Anywhere else canonical names are constructed

Audit during implementation: grep for `_fmt_lb`, `_get_standard_lb_name`, and any other folder-name builders. All must route through the shared `_apply_status_suffix()` helper. Move that helper to a shared module (e.g., `backend/folder_naming.py`) so both GUI files import it.

### Discrepancy Detection (Rename tab enhancement)

When the rename tab analyzes a folder, classify the `-NFT`-vs-status alignment and color the row accordingly:

| Folder name has `-NFT` | LB is Private | State | Treatment |
|---|---|---|---|
| Yes | Yes | ✅ Correct | Normal display |
| No | Yes | ⚠ Missing NFT marker | Pale red row; tooltip "LB is Private — folder should be marked -NFT"; auto-proposes adding NFT |
| Yes | No (Public) | ⚠ Stale NFT marker | Pale yellow row; tooltip "LB is now Public — NFT marker may no longer be needed"; auto-proposes stripping NFT |
| No | No | ✅ Correct | Normal display |
| Yes | Missing | ⚠ Marked NFT but LB is Missing | Pale orange row; tooltip "LB does not exist — investigate this folder" |

The auto-propose-strip case (NFT → no NFT after a Private→Public promotion) is a real workflow event: when the webmaster publishes a previously-Private item, the Rescrape Private button promotes it, and on next folder audit the user sees the stale `-NFT` and can strip it.

### Backend Surfacing

Add to [backend/db.py](../../Documents/losslessbob/backend/db.py):

```python
def should_mark_nft(lb_number: int, db_path=None) -> bool:
    """Return True if folders for this LB should carry the -NFT suffix.
    Currently equivalent to lb_status='private'. Future-proofed so that
    the convention can extend (e.g., 'restricted' status) without touching callers."""
```

Expose via API: `GET /api/lb_master/<int:lb>/nft` → `{"nft": true|false, "reason": "private"|null}`. Used by GUI files that don't have direct DB access.

### Edge Cases

- **User manually types a new name without `-NFT` for a Private LB:** When the user edits the Proposed New Name cell in the rename tab, validate on cell-edit complete. If the LB is Private and the user-typed name lacks `-NFT`, show a soft warning (yellow border on the cell + tooltip) but **do not block** — the user has final say. They can override the convention if they have a reason.
- **Folder already contains `NFT` mid-name (not as suffix):** E.g., `Concert-NFT-Bootleg-LB-X`. The idempotency check uses `.upper().endswith('-NFT')`, so mid-name occurrences don't trip the check — only true terminal `-NFT` is recognized. Append `-NFT` to the end normally, producing potentially `Concert-NFT-Bootleg-LB-X-NFT`. Document this as expected behavior; user can manually fix.
- **Public LB whose user has personal reason to mark NFT:** Out of scope here. They can manually edit the proposed name; no warning will fire since the LB isn't Private.
- **Curator overrides a Public LB to Private:** On next master release, end users' Rename tab will start surfacing those folders as "Missing NFT marker" warnings. This is desired behavior.
- **Migration of existing folders:** Not part of this feature. Existing Private-LB folders without `-NFT` will appear in the discrepancy report next time they're loaded into the Rename tab. The user batches the rename then.

### Files to Modify

| File | Change |
|---|---|
| New: `backend/folder_naming.py` | Shared `_apply_status_suffix()` helper, NFT constants. |
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `should_mark_nft(lb_number)` helper. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add `GET /api/lb_master/<lb>/nft` endpoint. |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | Route all proposed-name construction through `_apply_status_suffix()`. Add discrepancy detection coloring. Add on-edit validation warning. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Modify `_get_standard_lb_name()` to call the helper. The "Standard: {std_name}" preview shows `-NFT` automatically. |
| `PROJECT.md` | Document the NFT convention and the discrepancy states. |
| `CHANGELOG.md` | User-visible change: proposed folder names for Private LBs now include `-NFT`. |

### Verification

32. **Proposal — Public:** Rename a folder matched to a Public LB; confirm no `-NFT` suffix in proposed name.
33. **Proposal — Private:** Rename a folder matched to a Private LB; confirm `-NFT` is appended.
34. **Idempotency:** Rename a folder already ending in `-NFT` (or `-nft`) matched to a Private LB; confirm result has exactly one `-NFT` (uppercase), no double.
35. **Multi-LB match with one Private:** Folder matches LB-X (Public) and LB-Y (Private); confirm proposed name has `-NFT`, tooltip explains which LB triggered it.
36. **Discrepancy — missing NFT:** Place a folder without `-NFT` whose LB is Private; load Rename tab; confirm row is pale red with the explanatory tooltip and proposed name adds `-NFT`.
37. **Discrepancy — stale NFT:** Take a folder ending in `-NFT` whose LB is now Public (e.g., after Rescrape Private promoted it); confirm row is pale yellow and proposed name strips `-NFT`.
38. **Discrepancy — NFT on Missing LB:** Folder ending in `-NFT` whose LB is `missing`; confirm pale orange row with "investigate" tooltip.
39. **Manual override — warning fires:** In Rename tab, manually edit the proposed name to strip `-NFT` for a Private LB; confirm yellow cell border + tooltip warning, but rename still proceeds when applied.
40. **Collection tab parity:** In Collection tab, trigger a rename on a Private LB; confirm "Standard: {std_name}" dialog shows the `-NFT` suffix.
41. **API:** `curl /api/lb_master/<private_lb>/nft` returns `{"nft": true, "reason": "private"}`; `<public_lb>` returns `{"nft": false, "reason": null}`.
42. **Override propagation:** Override a Public LB to Private; load a folder matched to it in Rename tab; confirm discrepancy detection fires and proposal adds `-NFT`.

---

## Ancillary Feature: Persistent Folder-to-LB Linking (Disambiguation)

**Status:** ⬜ Not started. No `lb_alias` or `folder_lb_link` tables; Rename tab multi-LB rows still show comma-separated LBs with no resolution mechanism.

**Why.** Some folders match multiple LB candidates because the LB entry pages reference each other (e.g., LB-A's page mentions LB-B, or vice versa). The existing `xref` mechanism only handles checksum-level cross-references; these entry-level LB-to-LB references aren't captured anywhere structured. Today, the user manually picks the right LB every time the Rename tab encounters such a folder. The choice should persist — and where the curator has decided which LB in a referenced pair is canonical, that decision should ship in the master so every user gets the disambiguation for free.

**Scope clarification.** This is purely about LB-number references between entry pages. It's not about identifying recordings, fingerprinting content, or merging shows. The data model is just `(alias_lb → canonical_lb)` — a flat directional pointer.

### Design — Master Table is Primary

**The linkage is master data.** `lb_alias` is the authoritative record of LB-to-LB references and ships in every master release. The curator's job is to populate it thoroughly so that downstream users almost never see a multi-LB ambiguity in the Rename tab — by the time they install the master update, the canonical LB has already been picked for them.

| Table | Lives in | Ships? | Role |
|---|---|---|---|
| **`lb_alias`** | Master data | **Yes** | **Primary.** Curator-authored "alias LB → canonical LB" pairs. Ships to every user. Every multi-LB match goes through alias collapse before any user interaction. |
| **`folder_lb_link`** | User data | No | **Fallback only.** For the rare residual case where alias collapse doesn't resolve and a user picks one manually for their own folder. If this fires often, it's a signal the curator should add more aliases. |

**Implication for curator workflow:** when you encounter a multi-LB folder in the Rename tab, the *default expectation* is that you save the relationship as a master alias (benefits everyone), not as a per-folder link (benefits only you). The UI should reflect that — "Save as master alias" is the prominent action; the per-folder link is the secondary option for cases where an alias genuinely doesn't generalize.

### Schema

#### `lb_alias` (master data — ships)

```sql
CREATE TABLE IF NOT EXISTS lb_alias (
    alias_lb       INTEGER PRIMARY KEY,        -- the LB being aliased (the "loser")
    canonical_lb   INTEGER NOT NULL,           -- the canonical LB to use instead (the "winner")
    relationship   TEXT NOT NULL DEFAULT 'duplicate',  -- 'duplicate' | 'supersedes' | 'see_also'
    note           TEXT,                       -- curator's reasoning (ships to users)
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (alias_lb != canonical_lb)
);
CREATE INDEX IF NOT EXISTS idx_lb_alias_canonical ON lb_alias(canonical_lb);
```

**Constraint:** `alias_lb` is the PK so each LB can alias to at most one canonical. Prevents cycles by validating on insert (`canonical_lb` must not itself be aliased — if it is, follow the chain to its root and use that).

**Relationship types** (semantic only — all three behave identically for disambiguation):
- `duplicate` — same recording, redundant entry on the website.
- `supersedes` — canonical replaces the alias (e.g., remastered).
- `see_also` — entry page text cross-references the other without claiming identity; curator made an editorial call.

#### `folder_lb_link` (user data — local only)

```sql
CREATE TABLE IF NOT EXISTS folder_lb_link (
    folder_path    TEXT PRIMARY KEY,           -- absolute path, exact match
    lb_number      INTEGER NOT NULL,
    linked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_folder_link_lb ON folder_lb_link(lb_number);
```

**Note** — this table is in the **USER_TABLES** list, so it is dropped during master export and never ships to other users.

### Resolution Order (Rename tab, etc.)

When the Rename tab analyzes a folder and gets multiple candidate LBs, it resolves in this order:

1. **`folder_lb_link` lookup** — exact folder path match → use that LB immediately. Done.
2. **`lb_alias` collapse** — for the set of candidate LBs, follow any alias chains. If after collapsing, only one canonical LB remains, use it. Done.
3. **Still ambiguous** — show as `multiple_ids` state per current behavior; user picks manually. The "Link..." button (see UI) lets them persist the choice.

Step 2 is the master-side power: even users who haven't manually linked anything get auto-disambiguation for any pair the curator has aliased.

### UI

#### Rename tab — [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py)

For rows in the `multiple_ids` state, replace the current static "LB Found" cell with a small **Link…** dropdown button. **For curators, the master-alias options are listed first** to reinforce the primary workflow:

```
LB Found:  [LB-01234, LB-05678  ▾]
              ├─ ⭐ Save alias: LB-05678 → LB-01234   (curator, ships)
              ├─ ⭐ Save alias: LB-01234 → LB-05678   (curator, ships)
              ├─ ─────────────────────────────
              ├─ Use LB-01234 (this folder only, local)
              ├─ Use LB-05678 (this folder only, local)
              ├─ ─────────────────────────────
              └─ Open both in Search tab
```

For non-curators, the alias options are hidden entirely (not greyed) and only the per-folder choices appear.

- **"Save alias: A → B"** (curator only, gated by `meta.is_curator='1'`) → opens a small dialog asking for `relationship` type and a note, then writes to `lb_alias`. This decision ships in the next master release and benefits every user who installs it. After save, the Rename tab row auto-resolves to the canonical LB and the regular rename flow continues.
- **"Use LB-X (this folder only, local)"** → writes to `folder_lb_link`. Cell collapses to single LB. Future loads of this folder auto-resolve **for you only**. Use sparingly — for cases where the multi-match is somehow specific to your local situation and doesn't generalize.
- **Already-linked rows** show a small 🔗 icon and tooltip distinguishing source: "Resolved via master alias: LB-X → LB-Y" vs. "Linked locally to LB-X on YYYY-MM-DD". Right-click → "Unlink this folder" clears the user-data link only (master aliases can't be cleared from the Rename tab — that's done in DB Editor).

**Curator nudge:** when a curator clicks "Use LB-X (this folder only)" without first creating a master alias, show a one-time tooltip: "Tip: you're a curator. Consider saving this as a master alias so all users benefit." Dismissable.

#### DB Editor tab — [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py)

Add an **"Aliases"** sub-panel (curator only — read-only for non-curators):

- Table columns: `Alias LB | → | Canonical LB | Relationship | Note | Created`.
- Filter by canonical LB or relationship type.
- Buttons: **Add Alias** (opens a form: alias LB, canonical LB, relationship, note), **Edit**, **Delete**.
- **Validation on Add/Edit:**
  - Alias and canonical must both exist in `lb_master`.
  - Canonical must not itself be an alias (prevents cycles); if user picks one, show a warning offering to use the root canonical instead.
  - Adding an alias for a `private` or `missing` LB is allowed (sometimes a Private LB is the canonical and the Public one is the duplicate scrape).

Non-curators see this panel as read-only — they can browse aliases that shipped in the master data but can't edit.

### Effects Elsewhere

Aliasing is consequential beyond just disambiguation. The following places should consult `lb_alias` and consider showing canonical instead of alias:

- **Search tab:** When a user searches for content and hits an aliased (non-canonical) LB, show a small badge "→ LB-canonical" with a link to jump. Don't hide the alias row entirely — the curator's note is useful context.
- **Lookup tab:** When a checksum lookup hits an aliased LB, automatically present the canonical LB as the primary result, with the alias listed as "also referenced as".
- **Collection tab — My Collection:** If a user has an alias LB in their collection and the master ships a new alias rule making it non-canonical, flag the row with a soft warning: "LB-X is now aliased to LB-Y. Consider re-linking your collection entry." Don't auto-rewrite — that's destructive.
- **Forum post guard:** If user tries to post for an alias LB, check the canonical's status. If canonical is Private, block; if canonical is Public, allow (and use the canonical's URL/metadata in the post).
- **`lb_master` status reconciliation:** Aliases don't affect `lb_status` directly. An alias LB keeps its own auto-classification (it has its own webpage, checksums, attachments). The alias relationship is *informational* — it doesn't merge or delete data.

### Backend API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/lb_alias` | List all aliases. |
| `POST` | `/api/lb_alias` | Add. Body: `{alias_lb, canonical_lb, relationship, note}`. Curator-only. |
| `DELETE` | `/api/lb_alias/<alias_lb>` | Remove. Curator-only. |
| `GET` | `/api/lb_alias/resolve?lbs=1,2,3` | Returns canonical LBs after alias collapse. Used by Rename tab. |
| `GET` | `/api/folder_link?path=...` | Look up a user's sticky link for a folder. |
| `PUT` | `/api/folder_link` | Set/replace a folder→LB link. Body: `{folder_path, lb_number, note}`. |
| `DELETE` | `/api/folder_link?path=...` | Clear a user's link. |

### Edge Cases

- **Alias chain length:** Limited to 1 hop. If the curator tries to make `A → B` when `B → C` already exists, validation rewrites the request to `A → C` (with a warning shown). Keeps resolution O(1).
- **Curator deletes an alias that users depend on:** When the master release ships without an alias that was present before, any `folder_lb_link` rows users have are unaffected (they're user data, independent). Search/Lookup hint badges silently disappear. No harm.
- **Master alias conflicts with user link:** User has `folder_lb_link` pointing to LB-X. New master release aliases LB-X → LB-Y. The user's link is exact-path, so it still wins (step 1 in resolution order). Show a one-time info nudge on next Rename tab load: "Your link for /path/to/folder points to LB-X, but the master now considers LB-Y canonical. Update?"
- **Folder moved/renamed on disk:** The `folder_path` PK becomes stale and the link is silently inert. Acceptable — when the new path next appears in Rename tab, user re-links if needed. Future enhancement: detect folder moves via existing `rename_history` table and migrate the link automatically.
- **Multi-LB match where one candidate is the alias of another:** Step 2 (alias collapse) handles this — the alias drops out, only the canonical remains. No user action needed.
- **Curator-only restrictions in non-curator mode:** Hide the "Save alias" menu items entirely (don't grey out) to avoid implying a feature that isn't accessible. Same for the DB Editor Aliases panel buttons.

### Files to Modify

| File | Change |
|---|---|
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `lb_alias` and `folder_lb_link` table creation in `init_db()`. Add `lb_alias` to `MASTER_TABLES`, `folder_lb_link` to `USER_TABLES`. Add `resolve_aliases(lb_numbers: list[int]) -> list[int]`, `get_folder_link(path)`, `set_folder_link(path, lb, note)`, `add_lb_alias()`, `delete_lb_alias()`. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add 7 endpoints above. Gate POST/DELETE on `lb_alias` to curator mode (`meta.is_curator='1'`). |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | Apply resolution order (folder_lb_link → alias collapse → manual). Add "Link…" dropdown on multi-LB rows. Show 🔗 icon on linked rows. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Add "Aliases" sub-panel (curator-editable, others read-only). |
| [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py) | Show "→ LB-canonical" badge on aliased rows. |
| [gui/lookup_tab.py](../../Documents/losslessbob/gui/lookup_tab.py) | Re-rank matches so canonical LB is primary; show alias as "also referenced as". |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Soft warning on rows where the LB is now an alias. |
| `PROJECT.md` | Document both tables, the resolution order, curator workflow for aliasing. |
| `CHANGELOG.md` | User-visible: aliases now persist; folder→LB links remembered locally. |

### Verification

43. **Folder link — set:** In Rename tab, multi-LB row, pick "Use LB-X (this folder only)". Reload tab. Confirm row now shows single LB-X with 🔗 icon, no longer ambiguous.
44. **Folder link — unlink:** Right-click linked row → "Unlink this folder". Reload. Confirm ambiguity returns.
45. **Folder link — survives restart:** Set a link, restart the app, reload Rename tab. Confirm link persists.
46. **Alias collapse — curator side:** As curator, add alias LB-B → LB-A. In Rename tab, find a folder that matched both LB-A and LB-B. Confirm it now auto-resolves to LB-A with no manual action.
47. **Alias collapse — end-user side:** Export master with the alias in place. Import on a clean install. Confirm the same auto-resolution happens for that user.
48. **Cycle prevention:** Try to add alias A→B then B→A. Confirm rejection.
49. **Chain rewrite:** Existing alias A→B. Try to add C→A. Confirm system rewrites the request to C→B (with warning).
50. **Search hint:** Search for content matching LB-B (aliased to LB-A). Confirm "→ LB-A" badge appears on the LB-B row.
51. **Lookup re-rank:** Run a checksum lookup that hits LB-B (aliased). Confirm LB-A appears as the primary match.
52. **Forum-post canonical:** Try to post for LB-B (aliased to LB-A, which is Private). Confirm block fires with the Private LB modal — referencing LB-A.
53. **Master export excludes folder_lb_link:** Set several folder links, export master, open the exported `.db`, confirm `folder_lb_link` table is absent.
54. **Curator-only enforcement:** As a non-curator user, attempt `POST /api/lb_alias` via curl. Confirm 403. In the Rename tab, confirm "Save alias…" menu items are hidden.
55. **Master alias overrides user link conflict nudge:** User has `folder_lb_link` for /foo → LB-X. New master adds alias LB-X → LB-Y. Load Rename tab → confirm one-time nudge banner appears mentioning both LBs.

---

## Ancillary Feature: Rework Flat-File Update Check

**Status:** ⬜ Not started. Existing broken `scraper.check_for_update()` still scrapes the bynumber page; no `flat_file_releases`/`flat_file_changelog` tables; no real-file diff pipeline.

**Why current implementation is broken.** [scraper.py:271](../../Documents/losslessbob/backend/scraper.py#L271) `check_for_update()` does not check the flat file at all — it scrapes the bynumber webpage and counts visible LB links to compute a `site_max`. Failure modes:
- Misses any update that doesn't extend the max LB (corrections, added checksums for existing LBs — the majority of real updates).
- Brittle to any HTML change on the bynumber page.
- No actual fetch or hash compare of the flat file.

The hash-based skip logic at [importer.py:88](../../Documents/losslessbob/backend/importer.py#L88) is sound but only fires after the user manually puts a flat file in hand — it plays no role in discovery.

### Source of Truth

The flat file is distributed at:

```
http://www.losslessbob.wonderingwhattochoose.com/checksum_lookup/checksum_lookup_lb_zip_download.htm
```

Page structure (verified live, simple HTML):
- A line: `(this page was updated: M/D/YY H:MM:SS AM/PM)` — page-level timestamp.
- A table row containing a link `Checksum_Lookup_flat_file_LastLB_<NNNNN>.zip` plus its own modified date and size in MB.
- The filename embeds the max LB number (`LastLB_16588` at time of writing).
- The companion `Checksum_Lookup_db_exe_version_<V>_LastLB_<N>.zip` is for the Windows desktop app and is irrelevant — ignore it.

Release cadence: ~once per month.

### Detection Signals (used together)

| Signal | How obtained | Best for |
|---|---|---|
| **HTTP `Last-Modified` of zip** | `HEAD` request on the resolved zip URL | Cheapest, most reliable change indicator. Primary trigger. |
| **`LastLB_NNNNN` in zip filename** | Parsed from the page anchor href | Detects max-LB advancement; lets us preview "X new LBs available" before download. |
| **Page-displayed timestamp** (per-file column) | Parsed from the table row text | Redundancy in case `Last-Modified` is unset or unreliable. |
| **SHA256 of downloaded zip** | Computed post-download | Definitive — captured on apply so re-downloads of the same release are idempotent. |

A release is considered *new* if **any** of the first three signals differs from the stored values for the last known release.

### Schema Additions

Both tables are **master data** (added to `MASTER_TABLES`). The changelog is part of what makes a master release informative.

```sql
CREATE TABLE IF NOT EXISTS flat_file_releases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    downloaded_at   TIMESTAMP,
    applied_at      TIMESTAMP,
    deferred_until  TIMESTAMP,                  -- if user hit Defer, when to ask again
    source_page_url TEXT NOT NULL,
    zip_url         TEXT NOT NULL,              -- resolved absolute URL
    zip_filename    TEXT NOT NULL,              -- e.g. Checksum_Lookup_flat_file_LastLB_16588.zip
    last_lb_in_name INTEGER,                    -- parsed from filename
    page_timestamp  TEXT,                       -- parsed page-displayed date string
    http_last_modified TEXT,                    -- HEAD Last-Modified header value
    zip_size_bytes  INTEGER,
    zip_sha256      TEXT,                       -- filled after download
    rows_added      INTEGER,
    rows_changed    INTEGER,
    rows_removed    INTEGER,
    new_lb_min      INTEGER,
    new_lb_max      INTEGER,
    status          TEXT NOT NULL,              -- 'detected' | 'downloaded' | 'applied' | 'deferred' | 'skipped' | 'failed'
    failure_reason  TEXT
);
CREATE INDEX IF NOT EXISTS idx_flat_releases_status ON flat_file_releases(status, detected_at DESC);

CREATE TABLE IF NOT EXISTS flat_file_changelog (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id    INTEGER NOT NULL REFERENCES flat_file_releases(id),
    lb_number     INTEGER NOT NULL,
    op            TEXT NOT NULL,                -- 'add' | 'change' | 'remove'
    checksum      TEXT NOT NULL,
    filename      TEXT NOT NULL,
    chk_type      TEXT NOT NULL,
    xref          INTEGER NOT NULL,
    old_filename  TEXT,                         -- only on 'change'
    old_xref      INTEGER                       -- only on 'change'
);
CREATE INDEX IF NOT EXISTS idx_flat_changelog_release ON flat_file_changelog(release_id);
CREATE INDEX IF NOT EXISTS idx_flat_changelog_lb      ON flat_file_changelog(lb_number);
```

### Backend Logic

#### `discover_flat_file_release()` — replaces `check_for_update()`

```python
def discover_flat_file_release(db_path=None) -> dict:
    """Check the download page for a new flat-file release.
    Returns a dict describing the current available release and whether it differs
    from the last one recorded in flat_file_releases. Does NOT download the zip."""
```

Steps:
1. `GET` the page URL with a 15s timeout. Cache-bust with `?t=<epoch>` to defeat any intermediate caching.
2. Parse the HTML (BeautifulSoup, already a dep). Locate the anchor whose href matches `Checksum_Lookup_flat_file_LastLB_(\d+)\.zip`.
3. Resolve the zip URL (relative to the page URL). Parse `last_lb_in_name` from the filename via regex.
4. Read the sibling `<td>` cells for `page_timestamp` and `zip_size_bytes` (parse "17.7 Meg" → bytes).
5. `HEAD` the resolved zip URL. Capture `Last-Modified` and `Content-Length` headers.
6. Look up the most recent `flat_file_releases` row.
7. Compare: a release is new if any of `zip_filename`, `page_timestamp`, `http_last_modified` differs (or if no prior row exists).
8. If new: insert a `flat_file_releases` row with `status='detected'`. Otherwise: do nothing.
9. Return: `{available: bool, current_release: {...}, last_applied_release: {...}, lb_count_delta: int}`.

#### `download_flat_file_release(release_id)`

1. Read the row from `flat_file_releases`.
2. Stream-download the zip to `data/downloads/<zip_filename>` with progress callback.
3. Unzip in-memory or to a temp dir; locate the `.txt` flat file inside.
4. Compute SHA256 of the zip, update the row, set `status='downloaded'`, `downloaded_at=now`.

#### `diff_flat_file_release(release_id)` — preview without applying

1. Load the just-downloaded flat file into a temp SQLite (existing `_import_flat_file()` already does this).
2. For each `(checksum, lb_number)` pair, classify against current `checksums` table:
   - In incoming, not in current → `add`.
   - In current, not in incoming → `remove`.
   - In both, but `filename` or `xref` differs → `change`.
3. Return counts only (`{rows_added, rows_changed, rows_removed, new_lb_min, new_lb_max}`) — do not yet write to changelog. Used to populate the review dialog.

#### `apply_flat_file_release(release_id)`

1. Run `diff_flat_file_release` again (re-compute under transaction for correctness).
2. Take an automatic DB backup (`reason=f"pre_flat_apply_{zip_filename}"`).
3. For each diff row, perform the appropriate `INSERT` / `UPDATE` / `DELETE` on `checksums`, and write a corresponding `flat_file_changelog` row referencing the release.
4. Update `flat_file_releases`: `status='applied'`, `applied_at=now`, counts filled.
5. Update `meta`: `import_hash` (zip SHA256), `last_import_date`, `last_lb_number`.
6. Trigger `migrate_lb_master()` / `reconcile_lb_status()` for affected LBs (every LB touched by the changelog needs reconciliation).

The existing `import_flat_file()` becomes a thin wrapper that calls discover→download→diff→apply for a *user-provided* file (manual flow), bypassing the discovery step.

#### `defer_flat_file_release(release_id, days)`

Sets `deferred_until = now + days`. Discovery skips prompting until that time passes. User can also pick "until next release" — sets `deferred_until` to a sentinel (`9999-12-31`) which is cleared automatically when discovery sees a newer release.

### API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/flat_file/discover` | Live check (HTTP HEAD + page parse). Returns the dict from `discover_flat_file_release()`. |
| `POST` | `/api/flat_file/download/<release_id>` | Download the zip (long-running; reports progress via existing import-status mechanism). |
| `GET` | `/api/flat_file/diff/<release_id>` | Returns diff counts without applying. |
| `POST` | `/api/flat_file/apply/<release_id>` | Apply the diff. |
| `POST` | `/api/flat_file/defer/<release_id>` | Body `{days: int}` or `{until_next: true}`. |
| `GET` | `/api/flat_file/releases` | List past releases with counts. For the Setup tab history view. |
| `GET` | `/api/flat_file/changelog/<release_id>` | Paginated list of changelog rows for one release. |

### UI

#### Setup tab — [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py)

**Replace the existing "Check for Update" button** at line 190. New behavior:

- Button label: **"Check for Flat File Update"**.
- On click: calls `/api/flat_file/discover`.
- Result handling:
  - `available=false` → small dialog "You're up to date. Last applied release: <name> on <date>."
  - `available=true` and deferral active → still show in a small banner "Release <name> available (deferred until <date>)." with [Review Now] button.
  - `available=true` and not deferred → open the **Update Available** dialog (below).

**Auto-check on startup** — controlled by new `meta.flat_file_check_cadence`:
- `every_start` (default), `daily`, `weekly`, `never`.
- Run quietly in a worker thread on app launch. If a new release is detected (and not deferred), pop the Update Available dialog modally over the main window.

**New stats row** in the Setup status bar: "Flat file: applied <release_name> on <date>. Latest available: <release_name> (<delta> LBs newer)."

**New "Flat File History" sub-panel** (collapsible) listing past `flat_file_releases` rows: date, filename, counts, status. Click a row to view its changelog.

#### Update Available dialog (modal)

```
─── Flat File Update Available ───────────────────────
  New release detected on the LosslessBob website.

  Filename:    Checksum_Lookup_flat_file_LastLB_16588.zip
  Page date:   3/30/26 5:19:35 PM
  Size:        17.7 MB

  Your last applied release:
    Checksum_Lookup_flat_file_LastLB_16432.zip (2026-03-01)

  Estimated new LBs: 156 (LB-16433 through LB-16588)
  (Existing-LB changes can't be counted until downloaded.)

  [Download & Review]   [Defer 1 day ▾]   [Skip This Release]
─────────────────────────────────────────────────────
```

- **Download & Review** → kicks off download with a progress bar, then opens the **Review & Apply** dialog.
- **Defer** dropdown options: 1 day / 3 days / 1 week / Until next release.
- **Skip This Release** → marks `status='skipped'` so we never prompt again for this exact release, but next release still prompts.

#### Review & Apply dialog (modal, after download completes)

```
─── Review Flat File Changes ─────────────────────────
  Release: Checksum_Lookup_flat_file_LastLB_16588.zip
  Downloaded: 17.7 MB (SHA256: a3f2…)

  Summary of changes vs your current DB:
    + 156 new LBs added            (LB-16433 to LB-16588)
    + 4,210 new checksum rows
    ~ 23 existing checksum rows changed
    − 4 checksum rows removed

  [Show Detailed Changelog ▾]   ← expandable list of every row

  Applying will:
   • Take an automatic DB backup first
   • Modify ~4,237 rows in your checksums table
   • Update lb_master for affected LBs
   • Be logged as a master-data event (ships in next master release)

  [Apply Update]   [Cancel]
─────────────────────────────────────────────────────
```

The detailed changelog is paginated; large change sets don't lock the UI.

### Edge Cases

- **Page fetch fails** (network, DreamHost down, HTML structure changed): discovery returns `{available: null, error: "..."}`. The button shows a non-modal warning. Auto-check on startup logs the failure but doesn't block the app.
- **Zip download interrupted**: partial file in `data/downloads/` is deleted on failure detection; user can retry.
- **Already-downloaded but not applied**: discovery sees the existing row in `status='downloaded'` and skips re-download; "Review & Apply" dialog can be re-opened from the Setup tab History panel.
- **Existing user provides a manually-downloaded flat file**: the manual import path computes SHA256 on the file, checks `flat_file_releases` for a matching `zip_sha256`, and if found, attaches the import to that release row instead of creating a new one. This way changelogs are correctly attributed regardless of how the file got there.
- **`Last-Modified` header missing or stuck**: discovery falls back to `page_timestamp` and `zip_filename` for comparison.
- **Curator workflow:** because the changelog tables ship in master, every end user sees not just what the curator changed but what the upstream flat file changed. Tie-in: the master-release auto-generated notes should include a line "Flat file updates included since last master: release_N (X added, Y changed, Z removed)".

### Manual Import — No Downgrades Allowed

The naïve diff-and-apply pipeline above is **wrong** if the incoming flat file is older than what's already applied. Example failure:

> User has release_16588 applied (with corrections to old LBs made in release_16500). User drags in `LastLB_16432.zip` manually. The diff sees "missing" rows for LB-16433…16588 (marks them for **deletion**) and "changed" rows wherever the old file conflicts with newer corrections (marks them for **revert**). Apply would silently downgrade the DB.

**Policy: downgrades are not permitted.** Every manual import is classified by age first; older releases are refused outright with a clear explanation. There is no "additive-only" or "force" escape hatch — the only way to legitimately re-apply an older release is to first restore an older DB backup, then import.

#### Classification on manual import

1. Compute SHA256. Look up `flat_file_releases.zip_sha256`.
2. Parse `LastLB_NNNNN` from filename (if the pattern matches).
3. Compare to the highest-`last_lb_in_name` applied release:

| Match by SHA256? | Filename LastLB vs latest applied | Classification | Action |
|---|---|---|---|
| Yes, `status='applied'` | (irrelevant) | **Already applied** | Show "This release was applied on <date>. Nothing to do." Dismiss. |
| Yes, `status='downloaded'` | (irrelevant) | **Recognized, not yet applied** | Open Review & Apply dialog for that release. |
| No SHA match, filename LastLB > latest applied | Newer | **Newer release** | Insert new `flat_file_releases` row; normal diff/apply pipeline. |
| No SHA match, filename LastLB == latest applied | Same max LB, different content | **Same-release re-cut** | Prompt: "Same LastLB as your applied release but different file contents — looks like a re-cut. Treat as a replacement release?" → if Yes, normal pipeline; if No, cancel. |
| No SHA match, filename LastLB < latest applied | Older | **Downgrade — REFUSED** | Error dialog (see below). No apply path. |
| No filename match (renamed) | Can't tell | **Unknown age** | Prompt user to confirm: "Is this a newer release than your currently-applied <name>? (Yes / No / Cancel)" — only Yes proceeds. No or Cancel = refused. |

#### Downgrade refusal dialog

```
─── Cannot Import Older Flat File ────────────────────
  File:        Checksum_Lookup_flat_file_LastLB_16432.zip
  Filename LastLB: 16432
  Your applied release: 16588 (2026-03-30)

  This file is OLDER than the release you currently have
  applied. Importing it would:
   • Mark thousands of rows for deletion
   • Revert corrections made in newer releases

  Downgrades are not permitted. To re-apply an older
  release, first restore a DB backup from before your
  current release was applied (Setup tab → Backups).

  [Open Backups Folder]                            [OK]
─────────────────────────────────────────────────────
```

No "Force" or "Override" button. The only way past is the explicit backup-restore path.

#### Unknown-age prompt

```
─── Confirm Release Age ──────────────────────────────
  File:        my_custom_filename.zip
  SHA256:      bd91…
  
  This file's name doesn't match the standard LosslessBob
  naming pattern, so we can't tell if it's newer or older
  than what you've already applied.

  Your applied release: LastLB 16588 (2026-03-30)
  Incoming row count:   1,234,567

  Is this file NEWER than your currently-applied release?

  [Yes — Proceed]   [No — Cancel]   [Cancel]
─────────────────────────────────────────────────────
```

Only **Yes** proceeds (and routes through the normal Newer-release pipeline). No and Cancel both abort with no DB changes.

#### Bootstrap for users upgrading from the old importer

Users who have been manually importing flat files for years will install this feature with a populated DB but no `flat_file_releases` history. First-run handling:

- On first launch after upgrade, look at `meta.import_hash`. If present, insert a single synthetic `flat_file_releases` row: `status='applied_legacy'`, `zip_sha256=<existing import_hash>`, `last_lb_in_name=<current MAX(lb_number)>`, `applied_at=<existing last_import_date>`, source/url fields blank, counts zero, note "Backfilled from pre-feature import history."
- Future imports use this as the baseline for the downgrade check.
- No changelog rows are backfilled — accepted one-time loss of per-row history.

### Files to Modify

| File | Change |
|---|---|
| [backend/scraper.py](../../Documents/losslessbob/backend/scraper.py) | Remove old `check_for_update()`. Add `discover_flat_file_release()`. |
| New: `backend/flat_file.py` | `discover_flat_file_release`, `download_flat_file_release`, `diff_flat_file_release`, `apply_flat_file_release`, `defer_flat_file_release`. Parse the date format `M/D/YY H:MM:SS AM/PM` carefully. Also handles the manual-import classification (already applied / recognized / newer / re-cut / downgrade refused / unknown). |
| [backend/importer.py](../../Documents/losslessbob/backend/importer.py) | Restructure so the merge step writes to `flat_file_changelog` when invoked under a `release_id`. Manual file imports compute SHA256 and attach to an existing release row if matched. Downgrade refusal path is enforced here. |
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `flat_file_releases` and `flat_file_changelog` to `init_db()` and `MASTER_TABLES`. Add legacy bootstrap (`applied_legacy` row) on first run if `meta.import_hash` is present. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add 7 new endpoints. Remove `/api/db/check_update`. |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | Rebuild the Check button; add Update Available dialog, Review & Apply dialog, History sub-panel, downgrade-refusal dialog, unknown-age confirmation dialog. Implement startup auto-check worker. Add cadence dropdown. |
| `CHANGELOG.md` | User-visible: "Check for Update" rework — now genuinely checks the flat file, prompts with diff preview before applying. Downgrades refused. |
| `PROJECT.md` | Document the discovery → download → diff → apply pipeline, the master-data changelog, and the no-downgrades policy. |

### Verification

56. **Discovery — no change:** With current release applied, click Check. Confirm "up to date" dialog.
57. **Discovery — new release:** Manually edit `flat_file_releases` to point at a fake older release. Click Check. Confirm Update Available dialog appears with the right filename/date.
58. **Discovery — Last-Modified change without filename change:** Simulate by clearing the stored `http_last_modified` only. Confirm discovery fires correctly.
59. **Download → diff:** Download a release on a populated DB. Confirm the diff dialog shows non-zero added/changed/removed counts that match a hand-computed expected.
60. **Apply — backup created:** Apply a release. Confirm a `pre_flat_apply_*` backup exists in `data/backups/`.
61. **Apply — changelog written:** Confirm `flat_file_changelog` has one row per modified `checksums` row, with `release_id` set.
62. **Apply — lb_master reconciled:** Pick an LB that gained checksums in the release; confirm its `lb_master` row's `has_checksums` flag updated and `lb_status` reconciled.
63. **Defer:** Click Defer 1 day. Restart app. Confirm no Update Available dialog appears (banner still surfaces in Setup).
64. **Skip release:** Click Skip. Discovery still reports `available=true` but the dialog doesn't auto-pop. New release supersedes the skip.
65. **Manual file matches downloaded release:** Manually drag in the same `.zip` (or its extracted flat file). Confirm it attaches to the existing `flat_file_releases` row instead of creating a duplicate, and the changelog is generated correctly.
66. **Auto-check cadence:** Set cadence to `daily`. Restart twice within an hour; second restart should not re-fire discovery. Restart >24h later (or manually set `last_check` back) — discovery fires.
67. **Page format breaks:** Edit the page-parse regex to fail. Confirm error surfaces as a non-blocking warning, not a crash.
68. **Master export includes changelog:** After applying a release, export master. Confirm `flat_file_releases` and `flat_file_changelog` are present in the exported `.db`.
69. **Master import: end-user sees release history:** On a clean install, import the master. Confirm Setup tab History panel lists the curator's applied releases.
70. **Manual import — already applied:** Drag the currently-applied zip in. Confirm "already applied" dialog with last apply date; no DB changes.
71. **Manual import — downgrade refused:** Drag an older zip in. Confirm refusal dialog with no Force/Override button. Verify zero DB changes after dismissing.
72. **Manual import — same LastLB re-cut:** Edit one byte of the current zip and re-drag. Confirm re-cut prompt fires; choosing No leaves DB unchanged; choosing Yes runs normal pipeline.
73. **Manual import — renamed file, user says Yes:** Rename a newer zip to strip `LastLB_NNNNN`. Drag in. Confirm unknown-age prompt. Click Yes — verify normal apply runs.
74. **Manual import — renamed file, user says No:** Same setup, click No. Verify refusal with no DB changes.
75. **Legacy bootstrap:** Wipe `flat_file_releases`. Restart with `meta.import_hash` populated. Confirm one synthetic `applied_legacy` row appears with the right SHA and LB max, and that subsequent downgrade detection works against it.
76. **Backup-restore as the only downgrade path:** Restore a pre-release_N backup, then import release_N-2 (older than N but newer than the restored backup). Confirm it now applies normally.

---

## Ancillary Feature: Click-to-Sort Across All Tables

**Status:** ⬜ Not started. DB Editor backend already has `sort_col`/`sort_dir` support but no GUI wiring; no shared `SortableTableItem`/`sort_key_for` helper module.

**Why.** Today only the DB Editor has any sort support (and only at the backend level via `sort_col`/`sort_dir` params on `/api/db/table_rows`). No GUI table allows the user to click a column header to sort. Users have to mentally scan or rely on whatever default order the backend returns. The fix is straightforward Qt plumbing plus a shared sort-key helper, but it needs to be done consistently — otherwise different tabs will sort the same data type differently and create more confusion than they solve.

### Two Sort Paths Depending on Pagination

| Table type | Sort path | Tabs |
|---|---|---|
| **In-memory** (full dataset already loaded) | Enable `QTableWidget.setSortingEnabled(True)` + custom `QTableWidgetItem` subclasses for typed sorting. Click on header is handled entirely client-side. | Lookup (summary+detail), Rename, Verify, Lbdir, Attachments-list, Flat File History |
| **Server-paginated** (only one page loaded at a time) | Header click sends `sort_col`/`sort_dir` to the backend; backend adds `ORDER BY` to the SQL; first page reloaded. | Search, Collection (both sections), DB Editor, LB Master browser |

Native Qt sort on a paginated table would sort *only the current page*, which is misleading. Server-side sort applies to the whole dataset and is the correct choice.

### Shared Components

#### `SortableTableItem` subclass (client-side typed sorting)

A `QTableWidgetItem` subclass that compares by a stored sort key, not display text:

```python
class SortableTableItem(QTableWidgetItem):
    def __init__(self, display: str, sort_key):
        super().__init__(display)
        self._sort_key = sort_key
    def __lt__(self, other):
        if isinstance(other, SortableTableItem):
            try:
                return self._sort_key < other._sort_key
            except TypeError:
                return str(self._sort_key) < str(other._sort_key)
        return super().__lt__(other)
```

#### `sort_key_for(value, kind)` helper

Single source of truth for "how does this kind of value sort?" Used both client and server side (server returns sort keys alongside display values where types are non-obvious).

| Kind | Display | Sort key | Notes |
|---|---|---|---|
| `lb_number` | `"LB-01234"` | `1234` (int) | Numeric, never lexicographic. |
| `date_iso` | `"1965-08-28"` | `"1965-08-28"` (already lex-sortable) | OK as-is. |
| `date_mdy` | `"3/30/26 5:19 PM"` | `datetime(2026, 3, 30, 17, 19)` (ISO timestamp string) | Parse once on row load. |
| `file_size_h` | `"17.7 Meg"` | `18_559_795` (bytes) | Normalize human sizes to bytes. |
| `lb_status` | `"Public"` | rank: public=0, private=1, missing=2 | Avoid alphabetical (Missing/Private/Public is wrong order). |
| `bool_owned` | `"✓"` / `""` | `1` / `0` | Truthy values first when descending. |
| `text` | the string | the string lowercased | Case-insensitive default. |
| `int` | `"12"` | `12` | Trivial but explicit. |

Put this in `gui/widgets/sort_keys.py` so it's importable by every tab and by any future GUI code.

#### `SortableHeaderMixin` for paginated tables

A small mixin / helper for views backed by server pagination. Wires `horizontalHeader().sectionClicked` to:
1. Toggle ASC ↔ DESC if same column clicked, else default to ASC for the new column.
2. Render a triangle indicator on the active column header.
3. Re-issue the data fetch with the new `sort_col`/`sort_dir` params, jumping to page 1.

Visual indicator uses Qt's native `setSortIndicator(col, Qt.AscendingOrder | DescendingOrder)`.

### Per-Tab Rollout

#### Client-side (in-memory) tables

| Tab | Table | Default sort | Notes |
|---|---|---|---|
| Lookup | Summary | LB Number ASC | Detail table also sortable by Status, Filename, Checksum. |
| Rename | All rows | Current Folder Name ASC | LB Found column uses lb_number sort key (handles single LB; multi-LB rows sort by first LB). |
| Verify | Summary | Folder ASC | Status column uses defined rank (Pass < Mismatch < Missing). |
| Verify | Detail | Filename ASC | Three independent status sub-columns each get the rank order. |
| Lbdir | Summary | Folder ASC | LB# uses lb_number sort key. |
| Lbdir | Detail | Filename ASC | |
| Attachments | Missing list | LB Number ASC | |
| Setup | Flat File History | Date DESC (newest first) | |

Implementation: in each tab's table-populate function, replace `QTableWidgetItem(text)` with `SortableTableItem(text, sort_key_for(value, kind))`. Then call `setSortingEnabled(True)` once after populate. Set the default sort with `sortByColumn(col, Qt.AscendingOrder)`.

**Critical gotcha:** `setSortingEnabled(True)` causes resorting after every cell write, slowing populate to a crawl on large tables. Standard pattern: disable sorting *before* populate, enable it after. Wrap in a helper `populate_sortable(table, rows, populate_fn)`.

#### Server-paginated tables

| Tab | Table | Default sort | Sortable columns |
|---|---|---|---|
| Search | Results | LB Number ASC | LB Number, Date, Location, Rating, Status, Owned |
| Collection | My Collection | LB Number ASC | LB Number, Date, Location, Folder Name, Confirmed, Status |
| Collection | Missing from Collection | LB Number ASC | LB Number, Date, Location, Rating, Status |
| DB Editor | Generic table view | per-table default | All columns (already supported, just wire up header click) |
| DB Editor | LB Master browser | LB Number ASC | LB Number, Status, Manual?, Has Webpage, Has Checksums, Has Attachments, Last Changed |

Backend changes required per endpoint:
- Accept `sort_col` (whitelisted to the actual columns) and `sort_dir` (`asc`/`desc`).
- For non-trivial sort keys (e.g., `lb_status` ranked, not alphabetical), translate the requested col into the right SQL `ORDER BY` expression. Concretely: `lb_status` ASC → `ORDER BY CASE lb_status WHEN 'public' THEN 0 WHEN 'private' THEN 1 WHEN 'missing' THEN 2 END`.
- LB number sort is already numeric since `lb_number` is INTEGER in SQL — no special handling needed.
- Always append a stable secondary `ORDER BY lb_number ASC` to ensure deterministic pagination across page boundaries when the primary sort has ties.

### Persistence (per-table sort memory)

Each sortable table remembers its last sort across:
- Tab switches within a session (Qt does this for free if the widget isn't destroyed).
- App restarts — store as a single JSON blob in `meta.gui_sort_state`, keyed by `tab_name.table_name` → `{col: int, dir: 'asc'|'desc'}`. Loaded on tab construction; saved on every sort change via a debounced writer (500ms).

`gui_sort_state` is a **user-data** meta key — local only, never shipped in master.

### Edge Cases

- **Mixed types in a single column** (e.g., DB Editor showing whatever table the user picks): fall back to text sort with case-insensitive comparison. Numeric columns still sort numerically because the SQL column type is INTEGER/REAL.
- **NULL values:** SQL `ORDER BY` puts NULLs first in ASC, last in DESC by default in SQLite. That's fine for most columns. For LB Master where `manual_notes` is often NULL, sort by `manual_notes ASC` should put NULLs first — acceptable.
- **Sort by Status when manual override differs from auto-classification:** sort by `lb_status` (the effective status). Don't try to sort by both; the `manual_override` column is its own boolean column for users who want to find overrides.
- **Sortable column with custom rendering (icons, badges):** e.g. the Status column shows colored badges. The sort uses the underlying status code, not the rendered cell. Confirm via tooltip explanation.
- **Performance on large in-memory tables:** Verify Lookup summary with 5,000+ rows — sort should still feel snappy. If not, switch that table to server-side pagination as a follow-up.
- **Pagination boundary correctness:** When the user clicks a header on a paginated table that's currently on page 5, the reload jumps to page 1. Don't try to preserve position — the position has no meaning under a different sort.

### Files to Modify

| File | Change |
|---|---|
| New: `gui/widgets/sort_keys.py` | `sort_key_for()` helper, `SortableTableItem`, `SortableHeaderMixin`. |
| [gui/lookup_tab.py](../../Documents/losslessbob/gui/lookup_tab.py) | Switch summary + detail tables to `SortableTableItem`; enable sorting; set defaults. |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | Same. |
| [gui/verify_tab.py](../../Documents/losslessbob/gui/verify_tab.py) | Same for both tables. |
| [gui/lbdir_tab.py](../../Documents/losslessbob/gui/lbdir_tab.py) | Same for both tables. |
| [gui/attachments_tab.py](../../Documents/losslessbob/gui/attachments_tab.py) | Missing list table → sortable. Tree view stays unsorted (hierarchical). |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | Flat File History table → sortable. |
| [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py) | Wire header click → `sort_col`/`sort_dir` params on `/api/search`. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Same for both sections' endpoints. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Wire header click to existing `sort_col`/`sort_dir` support on `/api/db/table_rows`. Add the LB Master browser table sort. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add `sort_col`/`sort_dir` to search, collection, missing-from-collection, lb_master endpoints. Whitelist allowed columns per endpoint. Handle `lb_status` rank ordering. Always append stable secondary sort. |
| `PROJECT.md` | Document sortable columns per tab in the GUI section. |
| `CHANGELOG.md` | User-visible: all major tables now sort by column header click. |

### Verification

77. **Click-to-sort works on every named table** — manual click test, one column per table, both ASC and DESC.
78. **Numeric LB sort:** Search tab, click LB Number header. LB-2 sorts before LB-10 (not after, which would be the lexicographic bug).
79. **Status rank sort:** Search tab, click Status header ASC → order is Public/Private/Missing, not alphabetical.
80. **Date sort with M/D/YY format:** Flat File History, click Date header. 2026-03-30 sorts after 2026-02-15.
81. **Sort persists across restart:** Set Search to Date DESC, restart app, return to Search. Sort still Date DESC with the triangle on the right column.
82. **Server-paginated reset to page 1:** On Search page 5, click a header. Confirm jump to page 1 with new sort.
83. **Whitelist guard:** `curl /api/search?sort_col=password` → backend ignores or returns 400, doesn't blindly inject into SQL.
84. **Stable secondary sort:** With ties in primary sort, confirm page boundaries are consistent (same row never appears on two pages or skipped).
85. **Disable-during-populate:** Load a Lookup result with 1,000 matches. Confirm populate doesn't take noticeably longer than before (sort was disabled during fill).

---

## Ancillary Feature: Reliable Column Width Persistence

**Status:** 🟡 Search tab got a targeted "no longer reset to 100px on launch" fix on 2026-05-16. Collection, Lbdir, Rename still hardcode widths in populate functions. No shared `GuiStateStore` module, no JSON file, no atomic write + debounce + flush-on-close infra. Note: `resize_columns_to_font()` shipped on every tab — that's a separate concern (font scaling) and orthogonal to persistence.

**Why current attempts keep breaking.** The codebase has three different approaches in flight simultaneously:

| Tab | Current behavior | Result |
|---|---|---|
| Search, DB Editor | `QSettings` save on `sectionResized`, restore on load. | Mostly works but platform-dependent storage and timing-fragile. |
| Collection (multiple tables), Lbdir, Rename | Hardcoded `setColumnWidth(i, N)` in populate functions. | **Every populate clobbers user resize.** This is the visible "didn't save" bug. |
| Other tabs | No persistence at all. | Widths reset to Qt defaults on every restart. |

The user has fixed this "numerous times" because each fix was per-tab, not systemic. The next tab to need it copies whichever neighbor's approach happens to be visible, perpetuating the inconsistency.

**Root-cause fix:** one shared module, used uniformly. Hardcoded `setColumnWidth` calls are removed entirely; first-load defaults become a one-time fallback inside the shared module.

### Storage Decision: JSON File, Not QSettings

Move off `QSettings` for column widths (and table sort state from the previous section, splitter sizes, and tab geometry). Reasons:

1. **Platform inconsistency.** QSettings writes to Windows registry, Linux `~/.config`, macOS plist. Debugging or copying state across machines is awkward. A flat file in the project's `data/` directory is portable and obvious.
2. **Co-located with DB and backups.** Lives alongside `data/losslessbob.db` so the existing backup workflow covers it without extra plumbing.
3. **Human-readable.** A user (or me) can `cat data/gui_state.json` to see what's stored and edit it manually if state ever wedges.
4. **Survives Qt version changes.** QSettings format has had subtle changes between Qt5 and Qt6; JSON does not.
5. **Single file vs. many keys.** Easier to back up, version, and reason about.

File path: `data/gui_state.json`.

Top-level structure:

```json
{
  "version": 1,
  "tables": {
    "search.results":            {"col_widths": [80, 100, 200, 60, 600, 60, 60], "sort": {"col": 0, "dir": "asc"}},
    "collection.my_collection":  {"col_widths": [80, 90, 220, 200, 400, 110, 200], "sort": {"col": 0, "dir": "asc"}},
    "collection.missing":        {"col_widths": [80, 90, 220, 60, 500], "sort": {"col": 0, "dir": "asc"}},
    "dbedit.data":               {"col_widths": [...], "sort": {...}},
    "lookup.summary":            {"col_widths": [...], "sort": {...}},
    "...":                       {"...": "..."}
  },
  "splitters": {
    "collection.main_split": [400, 600]
  },
  "window": {
    "main": {"x": 100, "y": 100, "w": 1280, "h": 800}
  }
}
```

Keyed by `tab_name.widget_name` so every persistent widget has a stable, unique slot. No more clashes between tabs that happen to use the same widget variable name.

### Shared Module: `gui/widgets/state_store.py`

Three responsibilities, single class:

```python
class GuiStateStore:
    """Single source of truth for persistent GUI widget state.
    Lives in data/gui_state.json. Atomic writes (tempfile + rename).
    Debounced saves (500ms) to avoid disk thrash during user resize."""

    def __init__(self, path: Path = Path("data/gui_state.json")): ...

    # ── table column widths ────────────────────────────────────────
    def attach_table(self, table: QTableView | QTableWidget,
                     key: str,
                     defaults: list[int] | None = None) -> None:
        """Bind a table to persistent storage.
        - On showEvent: restore widths from JSON, or use defaults, or autosize.
        - On sectionResized: debounce-save to JSON.
        - On programmatic populate: do NOT clobber widths (caller's responsibility
          to not call setColumnWidth directly — assert and warn if they do)."""

    # ── sort state ─────────────────────────────────────────────────
    def attach_sort(self, table, key: str, default_col: int, default_dir: str) -> None: ...

    # ── splitters ──────────────────────────────────────────────────
    def attach_splitter(self, splitter: QSplitter, key: str, defaults: list[int]) -> None: ...

    # ── window geometry ────────────────────────────────────────────
    def attach_window(self, window: QMainWindow | QDialog, key: str) -> None: ...

    # ── manual ─────────────────────────────────────────────────────
    def flush(self) -> None:
        """Force-write any pending state immediately. Call on app close."""
```

Single global instance created at app startup, passed to every tab during construction. Replaces all current `QSettings(_SETTINGS_PATH, ...)` instances scattered across files.

### Restoration Lifecycle (the part that's been buggy)

Per-table flow:

1. **Tab `__init__`:** construct the table widget. Do NOT set column widths.
2. **Call `state_store.attach_table(table, key, defaults=[...])`** during construction.
3. **`attach_table` installs:**
   - A one-shot `showEvent` handler that runs after the first show: restores widths from JSON if the key exists; otherwise applies `defaults`; otherwise calls `resizeColumnsToContents()`.
   - A `sectionResized` listener that triggers the debounced save.
   - A guard flag `_restoring` that suppresses save during the restore window (first 1 second after attach, or first show, whichever is later).
4. **Subsequent populate calls** must **not** touch column widths. Audit and remove every hardcoded `setColumnWidth` call from populate functions.

The `_restoring` guard fixes the most common past-bug class: programmatic resize during restore fires `sectionResized` → debounce-save → user's good state gets overwritten with the wrong defaults from milliseconds earlier.

### Save Path (atomic + debounced + flushed-on-close)

- **Debounce:** every state change (column resize, sort change, splitter move) marks the state dirty and schedules a write 500ms later. Continued events reset the timer. Final state hits disk once after the user stops fiddling.
- **Atomic write:** marshal full JSON → write to `data/gui_state.json.tmp` → `os.replace()` to final path. Crash mid-write can't corrupt the file.
- **Flush on close:** `MainWindow.closeEvent` calls `state_store.flush()` to force any pending debounced write through immediately. Backstop against the user closing during the 500ms window.
- **No SIGTERM hook:** intentionally not handling kill -9 / OS shutdown perfectly. If 500ms of resize state is lost on hard kill, that's acceptable. Avoids the complexity of atexit + signal handlers that don't always fire.

### What This Removes

The cleanup is substantial. Every one of these gets deleted or rewritten:

| File | What to remove |
|---|---|
| [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py) | `_qsettings`, `_on_col_resized`, all explicit `setColumnWidth` in populate paths. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Same — local `_qsettings`, `_on_col_resized`, the populate-time width restoration block. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | All hardcoded `setColumnWidth(i, N)` calls in `_forum_hist_table`, `_torrent_hist_table`, `coll_view`, `miss_view`, `torrent_history_table`, `forum_posts_table` populate functions. |
| [gui/lbdir_tab.py](../../Documents/losslessbob/gui/lbdir_tab.py) | The 3× repeated `setColumnWidth(0, 28)` calls (these are setting the checkbox column width every time the table is rebuilt). |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | `setColumnWidth(0, 50)`. |
| [gui/theme_tab.py](../../Documents/losslessbob/gui/theme_tab.py) | `QSettings` for theme state — migrate to the same JSON store. |
| [gui/main_window.py](../../Documents/losslessbob/gui/main_window.py) | `QSettings` for window geometry — migrate. |

Replaced by `state_store.attach_*` calls in each tab's `__init__`.

### Migration of Existing User State

For users upgrading from the current QSettings-based code:

- On first run after the migration, if `data/gui_state.json` doesn't exist:
  - Read each known QSettings key from the old locations.
  - Translate into the new JSON structure.
  - Write `data/gui_state.json`.
  - Leave the old QSettings entries in place (don't delete) — harmless residue, lets the user roll back the app version if needed.
- If the user has no QSettings state either, the defaults from `attach_table` calls apply.

### Edge Cases

- **First show on a table that was never populated yet:** Apply `defaults` if provided, else `resizeColumnsToContents()`. Widths get saved on first user resize.
- **Column count changes** (e.g., a tab adds a Status column per the earlier feature): stored array is shorter than current columns → fill remainder from defaults; longer → truncate. Don't crash.
- **JSON file corrupted or unreadable:** log a warning, rename to `gui_state.json.broken.<timestamp>`, start fresh with defaults. Don't lose the user's other state silently — surface a small status-bar notice on next launch.
- **Concurrent app instances:** acceptable for last-writer-wins on the JSON file. Two LosslessBob instances open simultaneously isn't a normal flow.
- **`sectionResized` firing during programmatic `setColumnWidth` calls from inside `attach_table` itself:** `_restoring` guard handles this.
- **Removed columns shouldn't leave orphan widths growing the JSON forever:** when loading, intersect stored widths with current column count and drop the rest on next save. Cleans up after schema changes.

### Files to Modify

| File | Change |
|---|---|
| New: `gui/widgets/state_store.py` | The `GuiStateStore` class described above. |
| [gui/main_window.py](../../Documents/losslessbob/gui/main_window.py) | Construct one `GuiStateStore` instance at startup; pass to every tab. Replace `QSettings` window-geometry calls with `state_store.attach_window`. Call `state_store.flush()` in `closeEvent`. |
| Every tab file with tables | Replace `QSettings` and hardcoded `setColumnWidth` with `state_store.attach_table(self.table, "tab.widget", defaults=[...])`. |
| New: `tools/migrate_qsettings_to_json.py` (optional) | One-shot script to translate existing QSettings keys to the new JSON. Useful for the curator's own dev machine before shipping the upgrade. |
| `PROJECT.md` | Document `data/gui_state.json` and the `state_store` module. |
| `CHANGELOG.md` | User-visible: column widths, sort, splitter, window state now persist reliably to `data/gui_state.json`. |

`data/gui_state.json` is **user data** — never shipped in master. Add to `USER_TABLES`-equivalent file allowlist if any export logic touches `data/`.

### Verification

86. **Resize → restart → restored:** Resize Search column "Description" to 800 px. Close app. Restart. Confirm column is still 800 px.
87. **Resize → close fast:** Resize then immediately close within 500ms. Confirm the resize persists (flush on close worked).
88. **Populate doesn't clobber:** Resize Collection "Folder Name" column. Trigger a refresh that re-populates rows. Confirm width unchanged.
89. **Restore guard:** Trace `sectionResized` calls on first show; confirm the debounced save is suppressed during the 1-second restore window.
90. **Column added later:** Add a Status column to a tab (per the earlier filters feature). Confirm old stored widths don't crash, and the new column gets its default.
91. **Corrupt JSON:** Truncate `data/gui_state.json` mid-object. Restart. Confirm app starts, file is renamed `.broken.<ts>`, defaults apply, status bar shows the notice.
92. **Concurrent instances:** Open two app instances, resize different tabs in each, close both. Confirm whichever closed last is the surviving state.
93. **QSettings migration:** With existing QSettings state on disk and no `gui_state.json`, restart. Confirm JSON file is created with translated widths/sort/geometry; user sees no visible regression.
94. **Audit pass:** `grep -rn "setColumnWidth\|QSettings" gui/` returns only references inside `state_store.py` and migration script. Every other call site is gone.

---

## Ancillary Feature: Bootleg-CD Catalog (LBBCD)

**Status:** ⬜ Not started. No scraper, no `bootleg_titles`/`bootleg_scrapes` tables, no Bootlegs tab.

**Why.** The LosslessBob site maintains a separate sub-catalog of named bootleg releases at `http://www.losslessbob.wonderingwhattochoose.com/detail/LB-bootleg-by-title.html`. Each row pairs a bootleg title (e.g., "Zurich Modern Times") with the canonical LB number it corresponds to, plus date, location, and CD count. Some titles link further to a dedicated `LBBCD-NNN` detail page. This is curator-relevant content that today the app has no awareness of — Search results, Lookup matches, and Collection views can't surface "this LB is also released as bootleg titled X" or "I own three bootlegs that map to LB-Y." Per the user, this is master-class data that should ship to all users.

### Source Page Format (verified live)

```
Date       Title                                 Location              cd   LB
xx/xx/67   (empty)                               Big Pink               1   LB-9041
07/02/81   A Lot Of Love Talk,                   White House Hotel...   1   LB-7198
03/11/95   <a href="lbbcd/LBBCD-275.html">12/- A Pound</a>  Prague    2   LB-6877
04/29/07   zurich modern times                   Zurich, Switzerland    0   LB-13409
```

- Single HTML `<table>`, ~thousands of rows.
- 5 columns: Date (MD/DD/YY, with `xx` for unknown components), Title (sometimes empty, sometimes linking to `LBBCD-NNN.html`), Location, cd (integer count, can be 0), LB (always a single LB-NNNNN link to the standard detail page).
- No page-level "updated" timestamp. Update detection must rely on HTTP headers (`Last-Modified` / `ETag`) and/or a hash of the response body.
- Same LB can appear in multiple rows (one LB → multiple bootleg titles).

### Schema (master data — ships)

```sql
CREATE TABLE IF NOT EXISTS bootleg_titles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lb_number    INTEGER NOT NULL,             -- canonical LB this bootleg maps to
    title        TEXT,                         -- as displayed (may be empty/whitespace)
    date_str     TEXT,                         -- as displayed, e.g. "xx/xx/67"
    date_iso     TEXT,                         -- best-effort YYYY-MM-DD or YYYY-MM or YYYY; NULL if unparsable
    year         INTEGER,                      -- best-effort 4-digit year for fast filtering
    location     TEXT,
    cd_count     INTEGER,                      -- 0 is valid (vinyl-only / unreleased)
    lbbcd_id     INTEGER,                      -- e.g. 275 from "LBBCD-275.html"; NULL if no link
    lbbcd_url    TEXT,                         -- relative URL to the LBBCD detail page; NULL if no link
    scraped_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bootleg_lb       ON bootleg_titles(lb_number);
CREATE INDEX IF NOT EXISTS idx_bootleg_lbbcd    ON bootleg_titles(lbbcd_id) WHERE lbbcd_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bootleg_year     ON bootleg_titles(year);
CREATE INDEX IF NOT EXISTS idx_bootleg_title    ON bootleg_titles(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS bootleg_scrapes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url      TEXT NOT NULL,
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    http_etag       TEXT,
    http_last_modified TEXT,
    body_sha256     TEXT,
    rows_total      INTEGER,
    rows_added      INTEGER,
    rows_changed    INTEGER,
    rows_removed    INTEGER,
    status          TEXT NOT NULL              -- 'success' | 'no_change' | 'failed'
);
```

Both tables added to `MASTER_TABLES`.

**Date parsing.** The `xx/xx/67` style needs careful handling. Algorithm:
- Split on `/` → `[M, D, Y]`.
- Y is 2-digit; assume 19YY for Y >= 30 (Dylan started ~1960) and 20YY for Y < 30. Tune the pivot.
- If both M and D are numeric → produce `YYYY-MM-DD` and store `year`.
- If only D is `xx` → produce `YYYY-MM`; still store `year`.
- If both `xx` → produce `YYYY`; store `year` only.
- If everything is `xx` or unparseable → both NULL.

### Scrape Strategy

Driven by a new module `backend/bootleg_scraper.py`. Manual trigger from Setup tab; no auto-scrape on startup (the user explicitly preferred manual triggers for similar features).

`scrape_bootlegs(force: bool = False) -> dict`:
1. `HEAD` the page URL to read `ETag` and `Last-Modified`. Compare to the most recent `bootleg_scrapes` row.
2. If unchanged and `force=False` → insert `bootleg_scrapes` row with `status='no_change'`, return early.
3. `GET` the page. Compute body SHA256.
4. Parse with BeautifulSoup. For each `<tr>` after the header, extract the 5 cells and (if present) the inner `LBBCD-N` link.
5. Build the desired in-memory set of rows.
6. Diff against current `bootleg_titles`:
   - Match by `(lb_number, title, date_str)` as natural key. Anything in incoming not in current → add. Anything in current not in incoming → remove. Anything where `location`/`cd_count`/`lbbcd_id`/`lbbcd_url`/`date_iso`/`year` differs → change.
7. Apply the diff inside a transaction (after taking a `pre_bootleg_scrape` DB backup).
8. Insert a `bootleg_scrapes` row with counts and `status='success'`.

The diff-then-apply mirrors the flat-file approach so users get a meaningful change log per scrape rather than blind wipe-and-reload.

### API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/bootlegs/scrape` | Run a scrape now. Body `{force: bool}`. Returns counts. |
| `GET` | `/api/bootlegs` | Paginated list with filters: `q` (title/location text), `year_min`, `year_max`, `cd_min`, `cd_max`, `lb_status` (`public`/`private`/`missing`), `owned` (true/false), `has_lbbcd` (bool), `sort_col`, `sort_dir`. |
| `GET` | `/api/bootlegs/<int:id>` | Single row + joined `entries`/`lb_master` info. |
| `GET` | `/api/bootlegs/by_lb/<int:lb>` | All bootleg titles that map to one LB. Used by Search/Lookup tab integrations. |
| `GET` | `/api/bootlegs/scrapes` | History of past scrapes for the History panel. |

All read endpoints respect the master/user split (no user data exposed).

### UI

#### New "Bootlegs" tab (gui/bootlegs_tab.py — new file)

Registered in `main_window.py` alongside the existing tabs.

Layout: filter bar at top, sortable table beneath, detail pane on the right for the selected row.

**Table columns** (uses the click-to-sort plumbing from the earlier feature):
- LB Number (`lb_number` sort key)
- Title
- Date (`date_iso` sort key when present, else NULL last)
- Year (separate column for quick scanning)
- Location
- CDs (`cd_count`)
- LBBCD (icon + link when `lbbcd_id` present)
- Status (joined from `lb_master.lb_status`, with the standard color background)
- Owned (joined from `my_collection`, ✓ or empty)

**Filter bar:**
- Free-text search (title + location, case-insensitive, debounced 300ms)
- Year range (two spinboxes)
- CDs filter combobox: All / 0 / 1 / 2 / 3+
- Status filter `LBStatusComboBox` (reused from earlier section)
- Owned filter combobox: All / Owned / Not owned
- LBBCD filter: All / Has LBBCD link / No LBBCD link

**Detail pane on selection:**
- Full title/date/location/CD count
- Link to open the corresponding LB in the Search tab
- If `lbbcd_url` present: clickable link that opens the LBBCD page in browser (no in-app render; the page is a separate scrape target if user demand emerges later)
- All other bootleg titles that share the same LB (one-to-many awareness)

#### Integration into existing tabs

- **Search tab:** add a small "🎵 N" badge next to LB Number when that LB has bootleg titles. Click → opens the Bootlegs tab filtered to that LB.
- **Lookup tab:** when a checksum match resolves to an LB with bootleg titles, list them under the match summary (read-only).
- **Collection tab — My Collection:** add a "Bootleg" column showing the title(s) where this LB appears. Sortable.
- **DB Editor:** the `bootleg_titles` table appears in the table list like any other; the LB Master browser shows a bootleg count column.

#### Setup tab additions

- **"Scrape Bootleg Catalog" button** — calls `POST /api/bootlegs/scrape`. Shows progress (parse + diff + apply phases). Result dialog: counts added/changed/removed/total.
- **Bootleg scrape history** sub-panel — lists `bootleg_scrapes` rows with timestamp, status, counts.
- **Status bar** — append "Bootlegs: N catalogued (last scrape: YYYY-MM-DD)".

### Curator Tie-In

The bootleg catalog ships in master releases. Practical consequences:

- The "Publish Master Update" auto-notes pull from `bootleg_scrapes` since last publish (just like flat-file changelog). So end users see "this master includes a bootleg-catalog refresh: +12 titles, 3 changed".
- The Pre-publish Review dialog gains a "Bootleg titles added/changed since last release" section.

### Edge Cases

- **Title cell empty/whitespace** (`&nbsp;`): store as empty string, not NULL. Avoids index/sort weirdness. Display as "(no title)" in the UI.
- **LB number in catalog that doesn't exist in our `lb_master` yet:** likely means the bootleg page is ahead of the flat file. Insert the bootleg row; on next `lb_master` reconciliation the LB will be added (status `missing` until a flat-file release covers it). Surface as `needs_review` on `lb_master` ("referenced by bootleg catalog but no checksums").
- **Same LB referenced N times with the same title and date** (page duplication): the natural key collides. Deduplicate during parse with a warning to the scrape log.
- **HTTP request blocked / page format breaks:** scrape returns `status='failed'` with an error stored; no DB changes; UI shows a non-blocking warning.
- **Page is enormous and gets bigger:** the current 282 KB / few-thousand-rows scale is tiny. No streaming needed; whole page fits in memory comfortably.
- **Owned-filter scaling:** the `owned` filter joins `my_collection`. That table is user-local and small; no perf concern.
- **LBBCD detail pages:** deliberately out of scope for v1. Only the index page is scraped. Future enhancement could scrape each LBBCD detail page for track listings, but defer until concrete user demand.
- **Date pivot for 2-digit year:** Dylan's career started ~1960. Use pivot Y=30 → 19YY for Y≥30, 20YY for Y<30 (so "67" → 1967, "24" → 2024). Document the pivot constant; it will need revisiting in ~2030.

### Files to Modify

| File | Change |
|---|---|
| New: `backend/bootleg_scraper.py` | `scrape_bootlegs()`, `_parse_date()`, `_parse_row()`, diff helpers. |
| [backend/db.py](../../Documents/losslessbob/backend/db.py) | Add `bootleg_titles` + `bootleg_scrapes` tables to `init_db()` and `MASTER_TABLES`. Add `get_bootlegs(filters)`, `get_bootlegs_for_lb(lb)`, `get_bootleg_stats()`. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add 5 new endpoints under `/api/bootlegs/*`. |
| New: `gui/bootlegs_tab.py` | Full tab implementation. |
| [gui/main_window.py](../../Documents/losslessbob/gui/main_window.py) | Register Bootlegs tab in the tab bar. |
| [gui/search_tab.py](../../Documents/losslessbob/gui/search_tab.py) | Add "🎵 N" badge next to LB Number on rows that have bootlegs. |
| [gui/lookup_tab.py](../../Documents/losslessbob/gui/lookup_tab.py) | Show bootleg titles in match detail. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Add Bootleg column to My Collection table. |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | Scrape Bootleg Catalog button, History panel, status-bar count. |
| [gui/dbedit_tab.py](../../Documents/losslessbob/gui/dbedit_tab.py) | Bootleg count column on LB Master browser. |
| `PROJECT.md` | Document the new tables, endpoints, tab, and curator workflow. |
| `CHANGELOG.md` | User-visible: new Bootlegs tab and catalog scraping. |

### Verification

95. **Initial scrape:** With empty `bootleg_titles`, click Scrape Bootleg Catalog. Confirm rows match the live page count (within a small margin for parse edge cases). `bootleg_scrapes` row inserted with `rows_added > 0`.
96. **Idempotent re-scrape:** Click again immediately. Confirm `status='no_change'` row inserted and zero DB changes.
97. **Diff on edited row:** Manually edit one `bootleg_titles.location` field in SQL. Re-scrape with force. Confirm `rows_changed = 1`, location reverted.
98. **Date parsing — full:** Spot-check rows with `xx/xx/67`, `11/xx/68`, `08/31/69`. Confirm `year` and `date_iso` are correct per the pivot.
99. **Filter — text:** Type "modern times" in the title filter. Confirm matching rows appear.
100. **Filter — owned:** Set Owned filter to "Owned" with a populated `my_collection`. Confirm only owned bootlegs appear.
101. **Filter — status:** Filter by Private. Confirm rows where the joined `lb_master.lb_status='private'` appear.
102. **Sort:** Click LB Number header. Confirm LB-2 sorts before LB-10. Click Date header. Confirm chronological order with NULL dates last.
103. **Search integration badge:** Find an LB known to have bootlegs. Open Search tab. Confirm 🎵 badge appears.
104. **Search badge click:** Click the badge. Confirm Bootlegs tab opens filtered to that LB.
105. **Bootleg LB not in `lb_master`:** Manually delete an `lb_master` row referenced by `bootleg_titles`. Reconcile. Confirm new `lb_master` row appears with `needs_review=1` and a note "referenced by bootleg catalog".
106. **Master export contains bootlegs:** Export master, open exported `.db`, confirm `bootleg_titles` + `bootleg_scrapes` present and `my_collection` is not.
107. **Curator release notes:** Scrape twice with rows added between scrapes (simulate by deleting rows and re-scraping). Then publish a master update. Confirm release notes section "Bootleg catalog updates" lists the additions.

---

## Ancillary Feature: Standardize Folder Name Button

**Status:** ✅ Shipped 2026-05-17 (CC_LB_INTEGRITY item 13). `build_standard_name()` added to `backend/folder_naming.py`. `GET /api/folder_naming/standard/<lb>` endpoint returns `{standard_name, lb_status, nft}`. Rename tab has "Standardize Selected" button and right-click "Standardize Name" action; both update the proposed name and escalate state to `needs_rename` when the standard name differs from the current folder name. NFT suffix applied automatically. Also fixed BUG-064 (`_on_strip_wrong_lb` now transitions row state so stripped rows become eligible for rename).

**Why.** The canonical format for a Dylan show folder is:

```
YYYY-MM-DD Location (LB-XXXXX)
```

Example: `1965-08-28 Forest Hills, NY (LB-04321)`

The Date and Location strings are sourced from the `entries` table (i.e., from the LB master metadata — *not* literal text inserted into the filename).

Today the Rename tab proposes names by **appending** the LB suffix to whatever the existing folder name is. The Collection tab has a `_get_standard_lb_name()` helper that already produces this exact format and a regex `_STANDARD_LB_NAME_RE` that matches it — but the helper isn't shared, the Rename tab has no equivalent button, and neither integrates with the `-NFT` suffix for Private LBs. The user wants a one-click way to apply the standard format to selected folders in the Rename tab, using the same shared helper everywhere.

### Two Distinct Operations — Both Stay Available

This feature is **not** a replacement for the existing append-LB-suffix proposal. They are separate user actions, both retained:

| Operation | Trigger | What it does | When to use |
|---|---|---|---|
| **Append LB** (existing) | Default proposal generated when Rename tab analyzes folders | Keeps the existing folder name and appends `-LB-XXXXX` (or just the LB tag in the configured position) | When the user has crafted a folder name they want to preserve and just need the LB identifier added |
| **Standardize** (new) | Explicit button or right-click action in Rename tab | **Replaces the entire folder name** with the canonical `YYYY-MM-DD Location from LB (LB-XXXXX)` format | When the user wants the folder name to match master metadata exactly — wipes whatever was there |

The Rename tab analyzes folders and pre-fills proposals using the existing **Append LB** logic by default. The user can then opt into **Standardize** for individual rows or in bulk; doing so overwrites the proposal with the canonical form. After standardization, the user can still manually edit the proposed name in the cell before applying. Until **Rename Selected** is clicked, nothing touches disk.

This tightens the relationship between folder names and master metadata (date + location), which makes auditing and discrepancy detection more reliable later — but only for folders the user has chosen to standardize.

### Format Specification

```
YYYY-MM-DD<SP>Location<SP>(LB-XXXXX)[-NFT]
```

- `YYYY-MM-DD` — ISO date derived from `entries.date_str`. Required.
- `Location` — `entries.location`, sanitized for filesystem safety. Required.
- `(LB-XXXXX)` — LB number zero-padded to 5 digits, wrapped in parentheses.
- `-NFT` — appended when `lb_master.lb_status='private'` (per the earlier NFT feature).

Component order is fixed; do not reorder for shorter strings.

The existing regex `_STANDARD_LB_NAME_RE` in `gui/collection_tab.py` already matches this pattern. After consolidation, it lives in the shared module:

```
^\d{4}-\d{2}-\d{2}\s.+\s\(LB-\d{5}\)(-NFT)?$
```

### Consolidation

Move all folder-name construction into the shared `backend/folder_naming.py` module (already created in the NFT plan). New canonical function:

```python
def build_standard_folder_name(lb_number: int, db_path=None) -> tuple[str | None, str | None]:
    """Return (standard_name, error). standard_name is the canonical folder name
    for the given LB, or None if it can't be built (no date / no location / etc.)
    error is a human-readable reason when standard_name is None."""
```

The function:
1. Reads `entries.date_str` and `entries.location` for the LB.
2. Parses date via the existing `backend.torrent_maker._parse_date()` (or moved into `folder_naming.py` if it makes sense; one canonical date parser). Requires full M/D/Y — partial dates (`xx/xx/67`) are not standardizable.
3. Reads `lb_master.lb_status` to decide on the `-NFT` suffix.
4. Sanitizes the location string (see below).
5. Truncates the location if the total name exceeds the filesystem cap.
6. Returns `(name, None)` on success or `(None, "reason")` on failure.

Replaces:
- `_get_standard_lb_name()` in [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py).
- Any ad-hoc name construction in [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) `_fmt_lb()` consumers.
- The existing `_STANDARD_LB_NAME_RE` regex used by Collection tab to test "is this folder already standard" — extend to optionally allow the trailing `-NFT` for Private folders:
  ```
  ^\d{4}-\d{2}-\d{2}\s.+\s\(LB-\d{5}\)(-NFT)?$
  ```

### Filesystem Sanitization

Locations can contain characters that are invalid in folder names on at least one of {Linux, macOS, Windows}. Sanitization rules applied in order:

1. Replace each of `< > : " / \ | ? *` with `-`.
2. Strip control characters (anything < ASCII 32) entirely.
3. Collapse runs of whitespace into single spaces.
4. Strip leading/trailing whitespace and dots (Windows strips trailing dots silently, causing confusion).
5. If the resulting full name length exceeds **200 characters** (leaving headroom below the 255 component-length cap), truncate the location portion at a word boundary with an ellipsis `…`. The date prefix, "from LB", LB-XXXXX, and optional `-NFT` are never truncated.
6. If after sanitization the location is empty, return `(None, "Location is empty after sanitization")`.

A separate helper `sanitize_location(loc: str) -> str` so it's testable in isolation.

### UI

#### Rename tab — [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py)

Add a new toolbar button **"Standardize Selected"** alongside the existing Select All / Deselect All / Select Wrong LB buttons.

Behavior:
1. Iterate over checked rows.
2. For each row with `has_lb` state (single LB resolved, possibly via alias collapse): call `build_standard_folder_name(lb_number)`.
3. On success: overwrite the row's "Proposed New Name" cell with the returned standard name. Update the reason cell to "Standardize". Re-color according to discrepancy state (NFT mismatch etc.).
4. On failure: leave the row unchanged. Collect failures into a summary.
5. After processing, show a summary dialog: "Standardized 23 of 28 selected folders. 5 skipped: 2 missing date, 1 missing location, 2 LB resolves to multiple candidates."

The user still has to click **Rename Selected** afterward to apply the proposals to disk — standardization just rewrites the proposals.

#### Single-row "Standardize this folder" action

Right-click a single row → "Standardize Name" → same logic, applied to that one row. Saves a click vs. selecting + bulk action when fixing just one.

#### Collection tab — [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py)

The existing "rename folder to standard format" prompt at line 2469 already produces the correct format. The change is: replace the local `_get_standard_lb_name()` body with a call to the shared `build_standard_folder_name()`. The "Standard:" preview text continues to look the same for Public folders; for Private folders it now includes `-NFT`. The `_STANDARD_LB_NAME_RE` regex is updated to optionally allow the trailing `-NFT` so existing Public-format folders don't suddenly start triggering the rename prompt.

#### Setup tab (optional, low priority)

Add a "Standardize All Collection Folders" maintenance button under DB Maintenance. Iterates every `my_collection` row, computes the standard name, lists mismatches in a dialog, lets the user batch-apply. Useful one-time migration tool. Operates on user data, not master, so no curator gating.

### Backend Endpoint

```
GET /api/folder_naming/standard/<int:lb>
→ {"name": "1965-08-28 Forest Hills, NY from LB (LB-04321)",
   "error": null,
   "nft": false}

GET /api/folder_naming/standard/<int:lb>
→ {"name": null,
   "error": "Date xx/xx/67 cannot be parsed to YYYY-MM-DD",
   "nft": false}
```

GUI calls this rather than poking the DB directly. Keeps the canonical name logic on the backend.

### Edge Cases

- **Date is partial** (`xx/xx/67`, `11/xx/68`): not standardizable. Skip with reason "Partial date — needs YYYY-MM-DD". The bootleg-catalog tab is a more appropriate browse view for partial-date entries.
- **Location contains only punctuation** (e.g., `, ,`): sanitizer strips to empty → skip with "Location is empty after sanitization".
- **Two valid candidate LBs after alias collapse** (rare, residual ambiguity): skip with "Multi-LB folder — link to a single LB first". User uses the existing folder_lb_link mechanism to resolve.
- **LB is `missing`:** skip with "LB-XXXXX is marked Doesn't Exist — investigate before renaming".
- **LB is `private`:** standardize normally, `-NFT` suffix included. No warning.
- **Folder is already in standard format:** the proposed name equals the current name. Skip silently (don't add to failure summary; don't propose a no-op rename). The Rename tab's existing `needs_rename` state correctly hides these.
- **Location contains characters that look like valid filenames but render as RTL or are confusable** (e.g., Cyrillic, accented Latin): preserve as-is. Sanitization only blocks technically-invalid characters, not "confusing" ones.
- **Collision with an existing folder of the same standardized name**: the Rename tab already detects collisions and errors at apply time. Standardization doesn't pre-check.

### Files to Modify

| File | Change |
|---|---|
| New (or extend existing): `backend/folder_naming.py` | Add `build_standard_folder_name()`, `sanitize_location()`. Move `_get_standard_lb_name` logic here. Centralize on one `_parse_date()`. |
| [backend/app.py](../../Documents/losslessbob/backend/app.py) | Add `GET /api/folder_naming/standard/<lb>` endpoint. |
| [gui/rename_tab.py](../../Documents/losslessbob/gui/rename_tab.py) | Add "Standardize Selected" toolbar button. Add right-click "Standardize Name" action. Wire to the new endpoint. |
| [gui/collection_tab.py](../../Documents/losslessbob/gui/collection_tab.py) | Delete the local `_get_standard_lb_name()`. Call the new endpoint. Update `_STANDARD_LB_NAME_RE` to match the new format. |
| [gui/setup_tab.py](../../Documents/losslessbob/gui/setup_tab.py) | (Optional) Add "Standardize All Collection Folders" maintenance button. |
| `CHANGELOG.md` | User-visible: standard folder name format updated to include "from LB" segment; one-click standardize button added. |
| `PROJECT.md` | Document the canonical folder naming convention in a dedicated section. |

### Verification

108. **Format — public LB:** Call endpoint for a Public LB with full date and location. Confirm result is `YYYY-MM-DD Location (LB-XXXXX)`.
109. **Format — private LB:** Same with a Private LB. Confirm trailing `-NFT`.
110. **Format — partial date:** LB with `xx/xx/67`. Confirm `{name: null, error: "Partial date..."}`.
111. **Format — empty location:** LB with `location=""`. Confirm `error: "Location is empty..."`.
112. **Sanitization — Windows-illegal chars:** Test location `"London / UK : 8:00 PM"`. Confirm slashes/colons replaced with `-`.
113. **Sanitization — truncation:** Manufacture a 500-char location. Confirm result name ≤200 chars, truncation at word boundary with `…`, LB suffix preserved.
114. **Rename tab — bulk standardize:** Check 10 rows, click Standardize Selected. Confirm Proposed New Name updates for valid rows, summary dialog lists skips with reasons.
115. **Rename tab — single row:** Right-click → Standardize Name. Confirm just that row updates.
116. **Collection tab — Private LB without NFT triggers prompt:** Folder named `1965-08-28 Forest Hills (LB-04321)` belonging to a Private LB. Confirm rename prompt fires with `-NFT` added.
117. **Collection tab — already-standard format does not trigger:** Folder already in standard format (with `-NFT` for Private, without for Public). Confirm no rename prompt fires.
118. **Convergence:** `grep -rn "_get_standard_lb_name\|_STANDARD_LB_NAME_RE" gui/` returns only collection_tab.py call sites that use the new endpoint. The local function definition is gone.
119. **NFT discrepancy still works:** Standardize a Private LB folder; confirm `-NFT` is appended and discrepancy detection from the earlier feature does not flag it.
120. **No-op rename suppression:** Folder already matches standard format exactly. Click Standardize Selected. Confirm row is not modified and not listed in summary as a skip.

---

## Ancillary Feature: Map View of LB Locations

**Status:** ⬜ Not started — **deferred to end of implementation queue**, may be cut. Full plan in [CC_MAP_FEATURE.md](CC_MAP_FEATURE.md).

**Moved to its own plan file:** [CC_MAP_FEATURE.md](CC_MAP_FEATURE.md).

Brief recap (full design and verification list in the linked file):

- Plot every LB on an interactive world map by joining `entries.location` with a new master table `location_geocoded` (lat/lon per unique location).
- Two-phase: curator runs Nominatim geocoding once (rate-limited, ships in master); end users get pre-geocoded coordinates and only ever talk to OpenStreetMap tile servers.
- New "Map" tab uses `QWebEngineView` + Leaflet.js + marker clustering. Markers colored via the shared `lb_status_style()` helper. Filters mirror the Search tab.
- Whole stack is free: OSM tiles + Leaflet + Nominatim + PyQt6-WebEngine.
- New schema: `location_geocoded` (master data), curator-managed via DB Editor sub-panel with drag-to-place dialog for failed/approximate geocodes.

See the dedicated plan file for schema, endpoints, UI mockup, edge cases, files to modify, and verification steps.

