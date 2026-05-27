# 13 · Implementation Plan

A suggested attack order for Claude Code (or any developer) implementing LosslessBob. Each phase is independently shippable.

## Phase 0 — Project setup

Skip if there's already a codebase. Otherwise:

- Stack recommendation: **Electron + React + Vite + TypeScript**, with `better-sqlite3` in the main process
- State: **Zustand** for app state, **TanStack Query** for DB queries
- Tables: **TanStack Table v8** with row virtualization (`useVirtualizer`)
- Icons: **Lucide-React** (the prototype's icon set is intentionally Lucide-compatible)
- Routing: **react-router** with hash history (Electron-friendly)

## Phase 1 — Foundation

**Read first:** `01-architecture.md`, `02-design-tokens.md`, `03-primitives.md`

Build, in order:
1. Theme engine — port `_source/lbb-tokens.js` to your project. Export `applyTheme({mode, accent, density})`. Call once on app boot.
2. Global CSS — port `_source/app.css` (scrollbars, sticky tables, focus rings, density classes, kbd-pill, helper backgrounds for spec/map placeholders)
3. Icon component — port `_source/lbb-icons.jsx` OR swap to Lucide-React (preferred). Either way, expose `<Icon name="..." size={N}/>`
4. Primitives, one at a time: Pill → Chip → Button → IconButton → Input → Kbd → Card → Toolbar → Banner → Stat → SectionHead
5. Table family: TableShell + TH + TR + TD + GroupRow. **This is the most important primitive** — every screen depends on it.

> **Claude Code prompt:**
> Read `design_handoff_losslessbob/01-architecture.md`, `02-design-tokens.md`, and `03-primitives.md`. Implement the design tokens and primitives in our codebase, using `_source/lbb-tokens.js` and `_source/lbb-ui.jsx` as references. Match the visual contract exactly — especially the table family's 3px left-edge bar convention.

## Phase 2 — App shell

**Read:** `04-app-shell.md`

Build:
1. `<Sidebar>` w/ the canonical NAV_GROUPS array
2. `<Topbar>` w/ breadcrumbs + global search button + bell
3. `<StatusBar>` w/ the DB stats footer
4. `<AppShell>` that composes them + accepts `{children, active, onNav, curatorMode, crumbs, ...}`
5. Routing — wire `onNav(id)` to your router. Reading curatorMode from settings store.
6. Create a placeholder body that just renders the active screen name so you can verify nav works.

> **Claude Code prompt:**
> Read `04-app-shell.md` and `_source/app-shell.jsx`. Implement Sidebar, Topbar, StatusBar, and the composing AppShell. Wire to react-router (or our existing router). For now, render a placeholder centered title showing the active screen name as the body.

## Phase 3 — Curator mode toggle

**Read:** Curator-mode sections in `00-overview.md`, `04-app-shell.md`, `12-screens-settings.md`

Build:
1. Settings store that holds `curatorMode: boolean` (zustand + localStorage)
2. The toggle UI in Setup's "Master Data" card
3. Ensure sidebar hides the Curator nav group when off
4. Add a route guard so `/dbeditor` and `/scraper` redirect home if curator is off

You can build this before Phase 4 to validate the gating works end-to-end.

## Phase 4 — Highest-value screens

In order of business value:

### 4a. Pipeline screen — `06-screen-pipeline.md`
This is the *reason the app was redesigned*. Ship this first. Real wiring:
- File-drop integration (HTML5 drag-drop on the window → enqueue paths)
- Per-step backend operations (verify checksums, lookup LB#, rename folder, write LBDIR)
- Virtualized table (TanStack Virtualizer)
- Selection state w/ ⌘A and shift-click range
- Bulk apply

### 4b. Home screen — `05-screen-home.md`
Mostly a composition of cards over real metrics + a recent-activity log. Wire to:
- Library counts query
- Recent app-events log (might need to create an `app_events` table)
- Pipeline state store (for the Resume card)

### 4c. My Collection — `07-screen-collection.md`
Virtualized 15K-row table + detail panel. Real wiring:
- SQL query against the collection table
- Detail panel reads on row-select
- "Add to qBittorrent" action calls the qBittorrent Web API

> **Claude Code prompt for any screen:**
> Read `design_handoff_losslessbob/06-screen-pipeline.md` and `_source/screen-pipeline.jsx`. Implement the Pipeline screen using our primitives, real data from the SQLite DB, and TanStack Virtualizer for the main table. Keep the layout proportions, edge-bar conventions, and pill semantics from the reference.

## Phase 5 — Search & Library

- Search — `08-screen-search.md`. Wire to SQLite FTS5.
- Bootlegs — `09-screen-bootlegs.md`. Wire to `bootleg_titles` + `lbbcd_catalog` tables.

## Phase 6 — Settings

- Setup — `12-screens-settings.md`. Most of this is forms over the integrations / preferences config.
- Themes — `12-screens-settings.md`. The live preview is the trickiest part — make sure setting a tweak immediately calls `applyTheme()` so the preview updates.

## Phase 7 — Stubs

Implement stub screens (`10-screens-stub.md`) as placeholder Banners initially. Design + build them fully later as separate work:
- Verify, Lookup, Rename, LBDIR (single-folder versions of pipeline steps)
- Attachments, Spectrograms, Map (asset browsers)

## Phase 8 — Curator tools

`11-screens-curator.md` — defer. Implement after the collector experience is shipped:
- DB Editor
- Scraper

## How to prompt Claude Code per screen

A reliable template:

```
Read these files first:
- design_handoff_losslessbob/{section}.md
- design_handoff_losslessbob/_source/{matching jsx/js}

Then implement the {screen name} screen in our codebase at {path}.

Specific requirements:
1. Use our existing primitives from {path}, not the prototype ones.
2. Use real data from {table name(s)} via our existing DB layer.
3. Match the visual contract exactly — especially row edge bars, pill semantics, monospace numerics.
4. Virtualize the main table (we use TanStack Virtualizer).
5. Wire {specific interactions} to {specific handlers/actions}.

Skip {anything you want to skip}.
Ask before adding new dependencies.
```

Always include "skip X, ask before Y" — Claude Code will otherwise try to do everything in one go.
