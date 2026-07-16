# GUI

> Sources: `PROJECT.md` §GUI (Next) sections · `gui_next/src/` ·
> Status: seeded 2026-07-06, updated 2026-07-16 (legacy GUI removed)

## gui_next — Electron/React (sole GUI)

- Stack: Electron + React + TypeScript; main process in `gui_next/src/main/`,
  renderer in `gui_next/src/renderer/src/`.
- Talks to the Flask backend on :5174.
- Notable component areas: `components/library/` (DetailPanel etc.),
  `components/pipeline/` (PipelineIcon, PipelineParts — Concert Ranker pipeline UI).
- i18n: `locales/{en,de,fr,es,it,nl}.json`; en.json is source of truth, translate
  with `/gui-next-i18n` (DeepL).
- Verification: `/gui-check` (typecheck main + renderer, production build).
  **Never screenshots/browser automation** — the user checks visuals.

## Legacy PyQt6 GUI — removed

The 14-tab PyQt6 GUI (`gui/`) was removed 2026-07-16
(spec: `instructions/complete/LEGACY_GUI_REMOVAL_SPEC.md`). Its Leaflet map
page survives at `backend/resources/map.html`, served at `GET /map` and
embedded by gui_next's ScreenMap iframe. Historical tab docs: git history.

## Conventions

- GUI conventions: PROJECT.md §GUI (Next) Conventions.
- User-facing feature changes require locale updates before session close.
