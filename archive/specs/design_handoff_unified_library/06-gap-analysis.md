# 06 — Gap Analysis: Handoff vs. Current Codebase

This doc cross-checks `00`–`05` of this handoff against the **actual** state of
`gui_next/` and `backend/` (verified by reading the real files, not assumed).
Use it as the pre-flight checklist before any implementation work starts.
Nothing here is prose-only speculation — every claim cites a real path/line.

---

## 1. Already satisfied — don't rebuild

| Handoff ask | Reality | File |
|---|---|---|
| §02: `TR` must forward `onContextMenu` ("most common way right-click gets lost") | **Already done.** `TR` already accepts and forwards `onContextMenu`. | `gui_next/src/renderer/src/components/table.tsx:98,113` |
| `lbb-ui.jsx` primitives (`Pill/Chip/Button/IconButton/Input/Kbd/Card/Toolbar/Banner/Stat/SectionHead`) | All have existing 1:1 equivalents — reuse, don't port the prototype versions. | `gui_next/src/renderer/src/components/primitives.tsx` |
| Table primitives (`TableShell/TH/TR/TD/GroupRow`), incl. the 3px edge-bar convention | Already implemented, in active use by Search/Collection. | `gui_next/src/renderer/src/components/table.tsx` |
| Theme engine base (mode, accent, density) | Already implemented: `applyTheme()`, `loadTheme()`/`saveTheme()` via `localStorage['lbb-theme']`, applied pre-mount. Only the two *new* §01 controls (palette, card style) are missing — see §2/C1 below. | `gui_next/src/renderer/src/lib/tokens.ts` |
| §02 right-click menu pattern (open/close on outside-click, row→menu state) | Already proven and working — generalize this implementation rather than porting `libu-actions.jsx`'s `ContextMenu` from scratch. | `gui_next/src/renderer/src/screens/ScreenCollection.tsx:270-394` |
| §02 parity checklist items: torrent history, forum posting, qBittorrent, spectrograms, map | All **live and working today**. The checklist is about not losing access to them in the new screen — not building them. | `ScreenCollection.tsx` handlers (`handleCtxCreateTorrent`, `handleCtxAddToQbt`, `handleCtxPostForum`, `handleCtxSpectrograms`, etc., ~lines 2472-2612) + `/api/torrent/*`, `/api/entry/{lb}/*forum*`, `/api/qbt/*`, `/api/spectrogram/*` |
| §04 Part A1 — status footer (DB / Checksums / Last import / Bootlegs / Synced) | **Already bound to real data**, not hardcoded. `StatusBar` fetches `/api/home/stats`, `/api/master/github_check`, `/api/activity/busy` and formats them (`fmtNum`/`fmtLb`/`fmtLastImport`). The handoff's own A1 flagged this as a literal to bind "out of scope but don't miss it" — it's already done, no shell work needed. | `gui_next/src/renderer/src/components/AppShell.tsx:689-761` |
| §02/§04 Part B3 — bulk action bar (Create torrent, Add to qBittorrent, Post to forum) | **Partially already live.** Collection's batch toolbar uses `getTargetRows()` (checked rows, falling back to the single selected row) feeding `handleBatchCreateTorrent` / `handleBatchAddToQbt` / `handleBatchPostForum`. Reuse this pattern, don't rebuild it. | `ScreenCollection.tsx:2191-2196` (`getTargetRows`), buttons at `:2725-2729` |

> **Caveat on the row above:** "Update location" and "Remove from collection" do **not** have batch equivalents — `handleUpdateLocation` (`ScreenCollection.tsx:2870`) and the remove handler (`:2274`) only operate on the single selected/detail-panel row. Doc 02's bulk-bar checklist item ("Update location · Remove") is **not yet at parity** — this is a real, unflagged gap, not just a reuse opportunity. See **C9** below.

---

## 2. Backend gaps

### B1 — No family/TapeMatch integration at all
`tools/tapematch/` is a **standalone offline CLI** with its own `observations.db`,
run manually per show (`python -m tapematch.cli /path/to/processing`). Confirmed
zero wiring into the app: no `tapematch`/`family`/`cluster` hits anywhere in
`backend/` or `gui_next/src`.

The handoff's own §03 anticipates exactly this ("ship with no `fams`, UI falls
back to flat rows"), so this isn't a blocker — but it means:
**build the no-families fallback as the only path this round.** Ingesting
TapeMatch's output into a real DB table + API is a separate future project,
not part of this implementation pass.

### B2 — No structured `src` (source-type) field
Design's `Recording.src` enum (Soundboard/Audience/FM/Pre-FM/Master/Mixed) has
no backing column. `entries` only has free-text `source_chain`, `description`,
`taper_name` — no enum.

```
backend/db.py:124-138
CREATE TABLE IF NOT EXISTS entries (
    lb_number INTEGER PRIMARY KEY,
    date_str TEXT, location TEXT, cdr TEXT, rating TEXT, timing TEXT,
    description TEXT, setlist TEXT, status TEXT DEFAULT 'ok',
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    taper_name TEXT, source_chain TEXT, lb_category TEXT
);
```

SourceBadge and the "source" facet have nothing structured to read.
**Decision needed** (see §4): heuristic-parse from free text, add a curator-edited
column, or hide the feature until real data exists.

### B3 — No performance/show grouping endpoint
`/api/search` (`backend/app.py:827-867`) returns **flat per-recording rows
only**; the GUI already does in-memory sort/filter client-side (`sort_col`
handling at lines 854-864 is dead-code-adjacent — "GUI currently performs
in-memory sorting on the full result set" per the function's own docstring).

Performance lens needs grouping by `(date_str, location)`. This can likely be
done **client-side** over the already-fetched full result set — consistent
with the data contract's "rollups are derived in the UI, not stored" rule —
rather than a new backend aggregate endpoint. Needs a perf sanity check at
~16,630 rows, but should be fine for a desktop app render.

### B4 — Status enum mismatch
Design wants `Public | Private | New | Missing`. Real `entries.status` defaults
to `'ok'` and is a different, unrelated field. The actual `Public/Private/Missing`
value used today is **computed**, via a `CASE` over a joined table:

```
backend/app.py:848-851
"lb_status": (
    "CASE lm.lb_status WHEN 'public' THEN 0 "
    "WHEN 'private' THEN 1 WHEN 'missing' THEN 2 END"
),
```

`New` has no existing source at all — needs a definition (e.g. recently
`scraped_at`, or recently added to collection).

### B5 — History entity needs a merge adapter, not new data
Design wants one `HISTORY[lb] = { torrents: [...], forum: [...] }` shape feeding
the unified Share & Seed log. Today this is two separate, already-working
endpoints with their own shapes:
- `GET /api/torrent/{lb}` → `TorrentRecord[]`
- `GET /api/entry/{lb}/forum_posts` → `DetailForumRecord[]`

Don't rebuild the data — write a thin client-side adapter mapping both into the
unified `{ d, f, tag }` log shape for the new `ShareSeed`-style component.

### B6 — `notify` / `sources` actions have no backend
`my_wishlist` only has `priority` and `notes` columns. "Notify when available"
and "Find sources" (recording acquire-group actions in §02/§04) are **net-new
features** with no existing support at all. Flag as deferred/TODO — do not
ship a button that silently does nothing (per the handoff's own sign-off gate
in §04 Part C).

### B7 — `dup` / `upgrade` / `xref` hints partially exist
- `dup` ≈ existing `lb_alias` relationship type `"duplicate"` — reuse.
- `xref` ≈ existing cross-reference concept already in the schema — reuse.
- `upgrade` (a better unowned source exists for a show you partly own) has
  **no existing computed flag** — needs new derivation logic comparing ratings
  across a show's recordings.

---

## 3. Frontend (gui_next) gaps

### C1 — Theme engine missing palette + card style entirely
Verified by reading the full file: `lib/tokens.ts` has **no `PALETTES`**, no
`data-sep`/`data-palette` handling, and no `palette`/`cardStyle` fields on
`ThemeOptions` (current fields: `mode, accent, density, font, fontSize,
customTokens` — `lib/tokens.ts:10-17`).

Needs:
- Extend `ThemeOptions` with `palette` and `cardStyle`.
- Add the 5 dark + 5 light palette tables (exact hex values are in
  `01-theme-additions.md`).
- Extend `applyTheme()` to set `data-palette` and `data-sep`.
- Update `loadTheme()`/`saveTheme()` validation for the new fields.
- Add two new controls to `ScreenThemes.tsx` (564 lines; currently has Mode /
  Density / Accent sections at lines ~262, ~300, ~340 — extend, don't replace).

**Four sub-gaps the original pass missed, found by reading the full file:**

- **C1a — `ScreenThemes.tsx` has 5 existing sections, not 3.** Beyond
  Mode/Density/Accent there's a **Typeface** section (font + font size,
  `:381-436`) and an **Advanced** section (custom token editor, export/import
  theme JSON, row-highlight toggle, `:439-483`), plus a **Live Preview** mock
  table (`:486-555`). The grid is `gridTemplateColumns: '1fr 1fr'` — adding
  Frame theme + Card style means picking where in that 5-card grid they land,
  and deciding whether the Live Preview mock should also demonstrate
  framed/flat + palette (it currently only reflects mode/accent/density/font).

- **C1b — `handleImportTheme()` will silently drop the new fields.**
  `ScreenThemes.tsx:207-234` reconstructs `ThemeOptions` from imported JSON
  **field-by-field** (`mode: parsed.mode ?? DEFAULT_THEME.mode`, etc.) rather
  than spreading the parsed object. Adding `palette`/`cardStyle` to
  `ThemeOptions` without adding matching lines here means importing a
  previously-exported theme that has them will quietly lose them — the same
  failure mode this function already has to guard against in `loadTheme()`
  (`tokens.ts:151-169`, which the original C1 did flag). Both reconstruction
  sites need the new fields, not just one.

- **C1c — existing "System" mode option isn't in the `Mode` type, and the new
  `PALETTES` table will inherit the same hole.** `ScreenThemes.tsx:267` offers
  a third Mode tile, `system`, cast through `as ThemeOptions['mode']` even
  though `Mode = 'light' | 'dark'` only (`tokens.ts:4`). Today this silently
  degrades to `MODES.light` inside `applyTheme()` because `MODES['system']` is
  `undefined` and the lookup falls back (`tokens.ts:121`). The new `PALETTES`
  table will be keyed the same way (`Mode` → palette) and will have the
  identical silent-fallback behavior for "system" — fine if intentional, but
  `01-theme-additions.md §3`'s recommended layout only lists `Mode (light |
  dark)`, not three options, so this needs an explicit decision (resolve
  `system` via `getSystemMode()` at apply-time instead of relying on the
  fallback, or accept the existing fallback as-is) rather than inheriting an
  undocumented quirk into new code.

- **C1d — the CSS/boot-wiring snippets target a `#frame` element that doesn't
  exist in this codebase.** Both `01-theme-additions.md` (`#frame[data-mode=
  "dark"] [data-sep="framed"] { … }`) and `05-integration.md`'s boot snippet
  (`document.getElementById("frame")`, then `frame.setAttribute(...)`) assume
  a wrapper `<div id="frame">` mirroring the prototype's structure. The real
  app has no such element — `gui_next/src/renderer/index.html:10` has only
  `<div id="root">`, and the real `applyTheme()` sets `data-mode` /
  `data-accent` / `data-density` directly on `document.documentElement`
  (`tokens.ts:145-148`). Porting either snippet "verbatim" as C1/§01 instruct
  will silently match nothing. **Adapt both to `:root`/`document.documentElement`
  before porting** — don't copy-paste the `#frame` selectors or the
  `getElementById("frame")` call.

### C2 — No `--sep-*` CSS tokens anywhere
`gui_next/src/renderer/src/index.css` (137 lines) has **zero** hits for
`sep-`/`data-sep`. Need to port the full framed-card CSS block (gutter / card /
ring / lift / top-highlight, with per-mode shadow overrides) from this
handoff's `app.css` reference, scoped so it's inert until `data-sep="framed"`
is actually set — matching `05-integration.md`'s "additive, no effect on
existing screens" guarantee. **See C1d** — the selectors in the reference CSS
are scoped to `#frame`, which must become `:root` (or be dropped, since
`applyTheme()` already operates on `document.documentElement`) when ported.

### C3 — No unified Library screen/route yet
Needs a new `ScreenLibrary.tsx` + route + nav entry, additive alongside the
existing, fully-functional `/collection` and `/search` (confirmed both
untouched and both should stay live per this handoff).

### C4 — No shared action-registry module
Today, Collection's 10-item context menu + handlers
(`ScreenCollection.tsx:2472-2612`) and Search's 2-item menu
(`ScreenSearch.tsx:1523-1569`) are hardcoded per-screen — not a reusable
`recordingActions()`/`performanceActions()` registry like `libu-actions.jsx`.

Plan: port the *registry shape* (`{ id, label, group, primary?, danger? }`)
but wire each `id` to the **existing, already-working handler
implementations**. Do not reimplement qBittorrent/torrent/forum logic that
already works correctly.

### C5 — No shared `FilterMenu` primitive
Search and Collection each build their facet rails inline (ad hoc) rather than
via a shared dropdown component like `lbb-ui.jsx`'s `FilterMenu`/`MenuLabel`.
**Decision needed** (see §4): introduce a shared primitive now, or keep
following the established per-screen inline convention.

### C6 — No `ActionBar` / `AssetStrip` / `ShareSeed`-style detail-panel zones
Current Collection detail panel uses a flat button list plus two separate tabs
(Torrents / Forum Posts) — `ScreenCollection.tsx:1360-1519`. The handoff's
merged, filterable, date-sorted activity log is a new UI concept. Build new
components, but feed them from data already fetched today (no new backend
calls needed beyond the §B5 adapter).

### C7 — i18n
None of the new screen's strings exist yet in any of the 6 locale files
(`locales/{en,de,fr,es,it,nl}.json`). Expected for a new screen — must follow
the existing nested-namespace convention (e.g. add a top-level `"library"`
key), and per project rules, all 6 locales must be updated together.

### C9 — Bulk action bar is not at parity (Update location / Remove missing)
Collection's existing batch toolbar (`getTargetRows()` + `handleBatchCreateTorrent`
/ `handleBatchAddToQbt` / `handleBatchPostForum`, `ScreenCollection.tsx:2191-2729`)
covers 3 of the 4 actions doc 02's "Bulk bar" checklist and doc 04 §B3 require.
`handleUpdateLocation` (`:2870`) and the remove handler (`:2274`) are **single-row
only** — there's no batched version reusing `getTargetRows()`. Unlike the other
parity items in §1, this is a **real gap to build**, not just a reuse target:
add batch `relocate`/`remove` handlers before claiming bulk-bar parity in the
new screen.

### C8 — Nav placement differs from the prototype's assumption
`05-integration.md` describes adding a brand-new top-level nav **group**. The
real app already has a **"Library" group** in `AppShell.tsx` containing My
Collection / Trading / Sharing / Search / Bootlegs. The new screen slots in as
a featured item **inside that existing group**, not as a new group.

---

## 4. Open decisions (need an answer before coding starts)

1. **Performance grouping**: client-side `groupBy` over already-fetched
   `/api/search` results, or a new backend aggregate endpoint?
2. **`src` source-type**: heuristic-parse from existing free text, add a new
   curator-edited column, or hide the feature until real data exists?
3. Confirm TapeMatch/family wiring is explicitly **out of scope** for this
   implementation pass (ship flat-fallback only) — real integration is a
   separate, larger future project.
4. Confirm scope boundary: this pass builds the Library screen + theme
   additions + action registry; it does **not** retire Search/Collection
   (retirement is explicitly future/out-of-scope per `05-integration.md`).
5. **"System" mode + the new palette table** (C1c): resolve `system` to a
   concrete `light`/`dark` via `getSystemMode()` before indexing `PALETTES`,
   or accept today's silent fallback-to-light behavior as-is for palettes too?
6. **Bulk action parity** (C9): build batched `relocate`/`remove` handlers now,
   or ship the new screen's bulk bar without them and track as a follow-up?

---

## 5. Suggested build sequence

1. Theme additions (palette + card style) — isolated, additive, zero risk to
   existing screens.
2. Recording lens via a client-side adapter over existing `/api/search` +
   `/api/collection/lb_numbers` (this *is* the required no-families fallback
   row per §03).
3. Performance lens via client-side grouping of the same data (still no
   families).
4. Shared action registry, wired to existing handlers (§C4).
5. New detail-panel zones (ActionBar/ShareSeed/AssetStrip) over existing
   fetched data (§C6, §B5).
6. New screen/route/nav entry (§C3, §C8).
7. i18n strings (§C7).
8. **Explicitly deferred**: TapeMatch/family backend integration (§B1), `src`
   field (§B2), `upgrade` hint (§B7), `notify`/`sources` actions (§B6).

---

## Sign-off gate (mirrors §04 Part C, updated for verified gaps)

- [ ] Every Part A seed value (status footer, badges, facet tallies) bound to
      a real source or explicitly deferred with a ticket
- [ ] Every action id either wired to a real handler or hidden — nothing
      inert ships visible
- [ ] §02 parity checklist passes against live Collection
- [ ] No-families fallback renders correctly (it's the only path this round)
- [ ] Card style + palette persist and re-apply on boot
- [ ] Card style/palette CSS and boot wiring target `:root`/`document.documentElement`,
      not a `#frame` element (C1d — that element doesn't exist in this app)
- [ ] `handleImportTheme()` round-trips `palette`/`cardStyle`, not just `loadTheme()` (C1b)
- [ ] Bulk action bar has batched `relocate`/`remove`, not just create-torrent/qBt/forum (C9)
- [ ] All 6 open decisions in §4 above have an explicit answer, not a default
