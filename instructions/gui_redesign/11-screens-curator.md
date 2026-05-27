# 11 · Curator-Only Screens

Sources: `_source/screen-settings.jsx` (`ScreenDBEditor` and `ScreenScraper` functions). Both gated behind the **Curator mode** toggle in Setup.

These are **defer-able**. Ship the Collector experience first; add Curator tools in a follow-up.

## DB Editor

### Purpose

Raw, low-level access to all DB tables. Curator can edit any field, reconcile integrity, delete rows. Dangerous — that's why it's gated.

### Layout

```
┌────────────────────────────────────────────────────────────────┐
│ Header — icon block + H1 + "Curator only" pill                 │
├──────────────────┬─────────────────────────────────────────────┤
│ Tables list      │ Editor toolbar — table name + search + Run  │
│ (300px)          ├─────────────────────────────────────────────┤
│ - filter input   │                                             │
│ - list of tables │ Data grid (current table)                   │
│ - DB integrity   │                                             │
│   panel below    │                                             │
│ - Backup button  │                                             │
│                  │ Bottom: Commit/Discard/Delete + paging      │
└──────────────────┴─────────────────────────────────────────────┘
```

### Tables list (300px left)
- Search input at top
- ~15 table buttons, each: mono name (left, 11.5px) + row count (right, mono dim)
- Active table: accent-soft bg
- Below: **DB integrity** section — 5 metrics (Public / Private / Missing / Max LB / Needs review) in a 2-col stat grid
- "Reconcile all" + "Backup DB now" block buttons

### Editor (right pane)
- Top bar: mono table name (accent-mid 600) + row count meta + search input + "Load records" / "Run query" buttons
- Body: TableShell with the current table's columns. Cell `<TD>`s should become editable on double-click in production.
- Footer: "Commit changes" / "Discard" / **danger "Delete selected"** / "Export CSV…" + paging info "Page 1 / 52" + Prev/Next buttons

The sample table shown is `dylan_performances` with columns: rowid / event_id / date_str / category / city / state / country / venue. Real implementation should be schema-driven — read the column list from `PRAGMA table_info(<table>)`.

### Header warning treatment
- Icon block uses warn-themed colors (warn-bg / warn-fg / warn-bar border) instead of accent — visual flag that this is destructive
- The "Curator only" pill is `warn` tone

## Scraper

### Purpose

Crawler / scraper UI for the master DB curator. Three components stacked vertically:

1. **Site mirror crawler** — bulk crawl of the source site's directory listings
2. **Entry pages & metadata scraper** — per-LB# page fetching
3. **Bootleg-CD catalog (LBBCD)** — refreshes the bootleg titles catalog (collapsed by default)

### Layout

Padding `20px 24px 32px`, max-width 1500, centered. Header (similar warn-tinted icon + "Curator only" pill). Below: vertical stack of three `<SetupCard>`s with gap 14px.

### Site mirror crawler card

- Title + status pill ("Idle · 110,938 rows in site inventory")
- Controls row: 4-col field grid (Scope dropdown / Delay ms input / Daily cap input / Force re-fetch checkbox) + right-side button group (ghost "Stop", primary "Start crawl")
- Below: uppercase fg3 "Crawler session history" label
- TableShell: Started / Finished / Scope / Status / Fetched / Notes

### Entry pages scraper card

- 3 checkboxes inline (Auto-scrape on import / Download attachments / Force re-scrape) + right-aligned Stop + primary "Scrape missing (1,375)"
- Below: single-entry controls — "LB#" input + Scrape one, range start–end inputs + Scrape range, secondary "Re-scrape private LBs"
- **Live log block** — `<pre>` element:
  - bg `#0f0e0a` (near-black), text `#dfd9c8` (warm cream)
  - mono 11.5px, line-height 1.55
  - 180px tall, scrollable
  - 1px border-radius 6
  - Sample log content with timestamps + status lines

### LBBCD card (collapsed)

- Title + "collapsed" mute pill
- Single info row with chev-right + "Click to expand · last refreshed 2026-04-12 · 1,380 titles"

## Behavior notes

- Both screens need a confirm modal on every destructive action (delete, reconcile, publish)
- The DB Editor table grid should support inline cell editing with optimistic updates + a "dirty" indicator per row until Commit
- The Scraper's live log should stream from a backend process (SSE / WebSocket / IPC, depending on stack)
- Both screens should rate-limit themselves to be polite to the source site
