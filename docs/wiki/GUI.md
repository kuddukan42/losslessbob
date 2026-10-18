# GUI

> Sources: `PROJECT.md` §GUI (Next) (~line 1931), §GUI Conventions (~line 2038) ·
> `gui_next/src/renderer/src/lib/navigation.ts` · `gui_next/src/renderer/src/App.tsx` · `gui_next/src/` · Status: fresh 2026-10-18

## gui_next — Electron/React (sole GUI)

Electron + React + TypeScript; main process in `gui_next/src/main/`, renderer in
`gui_next/src/renderer/src/`. Talks to the Flask backend on :5174.

## Screens (23 sidebar + 4 routed-only, registered in `App.tsx`)

Sidebar groups (`NAV_GROUPS`): Home · **Ingest** Pipeline, Disk Scanner ·
**Library** Library (flagship: performance/recording lens toggle, zoned
DetailPanel with Quality/Picks/Taper/Olof tabs, dossier export; the
performance lens absorbed the retired Gaps screen) · My Collection · Trading ·
Sharing · Search · Bootlegs · TapeMatch (`ScreenTapeMatchCuration`; the old
ScreenTapeMatch is retired) · Songs · Timeline · **Assets** Attachments ·
Spectrograms · Map (legacy Leaflet page in an iframe) · **Curator** (gated)
Scraper · Fingerprint · Checksum Disputes · **Settings** Setup · Mounts ·
File Integrity · Themes · DB Editor.

Routed but not in the sidebar: QuickLookup (`/quicklookup`, reached from
Pipeline/Collection), Coverage award (`/about/coverage`, from the About modal),
LB ledger (`/lbdir/ledger`) and catalogue sync (`/lbdir/sync`).

`lib/navigation.ts` is the **single source of truth for screens** — sidebar and
command palette both consume `NAV_GROUPS`, so curator-gated screens vanish from
both when curator mode is off.

## Conventions (full detail: PROJECT.md §GUI (Next) Conventions)

- **State**: zustand for settings/screen-scoped state (one small store per
  concern under `lib/`, never one giant store); backend data goes through
  `@tanstack/react-query` — never into zustand. Refetch-after-mutation via
  `invalidateQueries`; long-lived reference data uses `staleTime: Infinity`.
- **Virtual tables**: `@tanstack/react-virtual`, group headers flattened into
  the same item list. Shared `useResizableColumns` hook for column widths.
- **Command palette** (Ctrl+K, TODO-263): LB-number jump, fuzzy screen nav,
  debounced date/venue search; `lib/commandRegistry.ts` is the extension point.
- **Shared primitives**: `components/primitives.tsx` Toast; `lib/api.ts` (`BASE`,
  `getJson`/`postJson`) is the one fetch helper; design tokens in
  `lib/tokens.ts`; LB URLs via `lib/lbUrl.ts` (backend twin `paths.py`).
- **i18n**: all strings through `t()`; per-screen namespaces in
  `locales/{en,de,fr,es,it,nl}.json`; `_one`/`_other` plurals. en.json is
  source of truth — translate with `/gui-next-i18n` (DeepL) before merging.

## Screenshots

Captures in `docs/screenshots/` (home, library, search, map, quicklookup,
pipeline); refresh recipe: `docs/screenshots/README.md`.

## Verification

- `/gui-check` (typecheck main + renderer, production build) — always required.
- Visual/layout changes: also `/verify` — screenshot engine **sanctioned
  2026-07-22**, Claude may run it on own initiative; Tier A renders the
  renderer only, `--electron` drives the real app on Xvfb. See
  [Visual-Verification](Visual-Verification.md).

## Legacy PyQt6 GUI — removed

`gui/` removed 2026-07-16 (`archive/specs/LEGACY_GUI_REMOVAL_SPEC.md`); its
Leaflet map survives at `backend/resources/map.html` (`GET /map`, ScreenMap iframe).
