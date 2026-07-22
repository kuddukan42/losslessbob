# GUI

> Sources: `PROJECT.md` §GUI (Next) (~line 1931), §GUI Conventions (~line 2038) ·
> `gui_next/src/` · Status: fresh 2026-07-22

## gui_next — Electron/React (sole GUI)

Electron + React + TypeScript; main process in `gui_next/src/main/`, renderer in
`gui_next/src/renderer/src/`. Talks to the Flask backend on :5174.

## Screens (20, drop-in registered via `App.tsx` routes)

Home · Setup · Mounts · Collection · Search · **Library** (flagship: performance/
recording lens toggle, zoned DetailPanel with Quality/Picks/Taper/Olof tabs,
dossier export) · Bootlegs · TapeMatch · Songs · Gaps (living Kokay list) ·
Fingerprint · Themes · Pipeline · QuickLookup · Attachments · Spectrograms ·
Map (legacy Leaflet page in an iframe) · DbEditor · Scraper · Sharing · Trading.

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
- **Shared primitives**: `components/primitives.tsx` Toast; design tokens in
  `lib/tokens.ts`; LB URLs via `lib/lbUrl.ts` (backend twin `paths.py`).
- **i18n**: all strings through `t()`; per-screen namespaces in
  `locales/{en,de,fr,es,it,nl}.json`; `_one`/`_other` plurals. en.json is
  source of truth — translate with `/gui-next-i18n` (DeepL) before merging.

## Screenshots

Real captures in `docs/screenshots/` (also used by the website + README):
[home](../screenshots/home.png) · [library](../screenshots/library.png) ·
[search](../screenshots/search.png) · [map](../screenshots/map.png) ·
[gaps](../screenshots/gaps.png) · [quicklookup](../screenshots/quicklookup.png) ·
[pipeline](../screenshots/pipeline.png). Refresh recipe: `docs/screenshots/README.md`.

## Verification

- `/gui-check` (typecheck main + renderer, production build) — always required.
- Visual/layout changes: also `/verify` — screenshot engine **sanctioned
  2026-07-22**, Claude may run it on own initiative; Tier A renders the
  renderer only, `--electron` drives the real app on Xvfb. See
  [Visual-Verification](Visual-Verification.md).

## Legacy PyQt6 GUI — removed

The 14-tab PyQt6 GUI (`gui/`) was removed 2026-07-16
(spec: `instructions/complete/LEGACY_GUI_REMOVAL_SPEC.md`). Its Leaflet map
page survives at `backend/resources/map.html`, served at `GET /map` and
embedded by ScreenMap's iframe. Historical tab docs: git history.
