# Plan: Collection Trading Feature

## Context

Users want to share their LosslessBob collection with friends to facilitate trading. The feature needs to: export your collection in a shareable format (no private data), import and store multiple friends' collections, diff two collections to see what each person has that the other doesn't, and generate a trading list (offer / want).

---

## Overview

New top-level **Trading** tab (`gui/trading_tab.py`) + backend `/api/trading/*` routes + two new DB tables. Follows existing patterns exactly: QTableView + QAbstractTableModel for tables, `requests` to Flask backend, `QFileDialog` for file I/O, JSON as the interchange format.

---

## New DB Tables (USER — never exported in master snapshot)

Added in `backend/db.py` `_ensure_schema()` using `CREATE TABLE IF NOT EXISTS`:

```sql
CREATE TABLE IF NOT EXISTS friend_collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_name   TEXT NOT NULL UNIQUE,
    imported_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lb_count      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friend_collection_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    friend_id  INTEGER NOT NULL REFERENCES friend_collections(id) ON DELETE CASCADE,
    lb_number  INTEGER NOT NULL,
    date_str   TEXT,
    location   TEXT,
    lb_status  TEXT,
    UNIQUE(friend_id, lb_number)
);
```

---

## Export Format (`.lbcollection` JSON)

`GET /api/trading/export` returns this; saved to disk as `<username>_collection.lbcollection`:

```json
{
  "losslessbob_collection": true,
  "export_version": 1,
  "exported_at": "2026-05-21T12:34:56Z",
  "entries": [
    {"lb_number": 123, "date_str": "01/15/99", "location": "New York, NY", "lb_status": "public"}
  ]
}
```

**No disk_path, notes, ratings, or any personal data.**

---

## Backend Routes (`backend/app.py`)

Five new routes, all under `/api/trading/`:

| Method | Route | Body / Params | Returns |
|--------|-------|---------------|---------|
| GET | `/api/trading/export` | — | JSON export of `my_collection` |
| GET | `/api/trading/friends` | — | List of stored friends |
| POST | `/api/trading/friends` | `{friend_name, entries:[...]}` | `{ok, friend_id}` — upserts friend |
| DELETE | `/api/trading/friends/<int:friend_id>` | — | `{ok}` |
| GET | `/api/trading/compare/<int:friend_id>` | — | Diff result (see below) |

Compare response:
```json
{
  "friend_name": "Alice",
  "you_have_they_dont": [...],
  "they_have_you_dont": [...],
  "both_have_count": 42
}
```

Each entry in the arrays: `{lb_number, date_str, location, lb_status}` joined with `entries` + `lb_master`.

---

## GUI (`gui/trading_tab.py` — new file)

Layout:

```
┌─────────────────────────────────────────────────────────┐
│  [Export My Collection…]                                 │
├──────────────┬──────────────────────────────────────────┤
│  Friends     │  [Select friend ▼]  [Compare]            │
│ ┌──────────┐ │                                          │
│ │ Alice 45 │ │  They have / You don't (N)              │
│ │ Bob   23 │ │  ┌──────────────────────────────────┐   │
│ └──────────┘ │  │ LB# | Date | Location | Status   │   │
│ [Import…]    │  └──────────────────────────────────┘   │
│ [Rename]     │                                          │
│ [Remove]     │  You have / They don't (N)              │
│              │  ┌──────────────────────────────────┐   │
│              │  │ LB# | Date | Location | Status   │   │
│              │  └──────────────────────────────────┘   │
│              │                                          │
│              │  [Export Trading List…]                  │
└──────────────┴──────────────────────────────────────────┘
```

- Left panel: `QListWidget` of stored friends (name + count), with Import / Rename / Remove buttons
- Right panel: two `QTableView` with `QAbstractTableModel` (4 cols: LB#, Date, Location, Status)
- **Export My Collection** button at top → `QFileDialog.getSaveFileName` → calls `GET /api/trading/export` → writes `.lbcollection` JSON
- **Import Friend** button → `QFileDialog.getOpenFileName` → reads JSON → validates → prompts for friend name → `POST /api/trading/friends`
- **Compare** → `GET /api/trading/compare/<id>` → populates both tables
- **Export Trading List** → writes a plain-text file:
  ```
  === Trading List: You & Alice ===
  Generated: 2026-05-21

  WHAT ALICE HAS THAT YOU DON'T (want list — 23 shows):
  LB-00123  1999-01-15  New York, NY
  ...

  WHAT YOU HAVE THAT ALICE DOESN'T (offer list — 15 shows):
  LB-00456  2001-07-04  Chicago, IL
  ...
  ```

---

## `gui/main_window.py` Change

Add after the `collection_tab` block:

```python
from gui.trading_tab import TradingTab
self.trading_tab = TradingTab(self.flask_port)
self.tabs.addTab(self.trading_tab, self.tr("Trading"))
```

Insert between "My Collection" and "Attachments" (line ~141).

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/db.py` | Add `friend_collections` + `friend_collection_entries` to `_ensure_schema()` |
| `backend/app.py` | Add 5 `/api/trading/` routes |
| `gui/trading_tab.py` | **New file** — full Trading tab implementation |
| `gui/main_window.py` | Import and register `TradingTab` |
| `PROJECT.md` | Schema, file structure, API routes |
| `CHANGELOG.md` | New entry |
| `TODO.md` | Add TODO for multi-friend batch compare (future) |

---

## Reuse / Patterns

- Table models: follow `_CollectionModel` pattern in `gui/collection_tab.py:~180`
- File I/O: `QFileDialog.getSaveFileName` / `getOpenFileName` as in `collection_tab.py:1764`
- Backend calls: `requests.get/post/delete` in a `QThread` worker as in `collection_tab.py:~400`
- Schema migration: `CREATE TABLE IF NOT EXISTS` in `db.py _ensure_schema()`

---

## Verification

1. Run `python -m py_compile gui/trading_tab.py backend/app.py backend/db.py` — no syntax errors
2. Start app: `python main.py`
3. Go to Trading tab → click "Export My Collection…" → confirm `.lbcollection` file written with correct JSON structure
4. Import the exported file back as a friend named "Me" → confirm friend appears in list with correct count
5. Click Compare → confirm "You have / They don't" is empty, "They have / You don't" is empty (same collection)
6. Create a second export with a subset of entries → import as "Test Friend" → confirm diff shows correct missing entries on both sides
7. Export trading list → confirm plain-text file has both sections with correct LB numbers
8. Remove a friend → confirm they disappear from the list
