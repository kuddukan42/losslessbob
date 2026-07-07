# GUI

> Sources: `PROJECT.md` §GUI sections (lines ~1179–1516) · `gui_next/src/` ·
> `gui/CLAUDE.md` · Status: seeded 2026-07-06

## gui_next — Electron/React (PRIMARY)

- Stack: Electron + React + TypeScript; main process in `gui_next/src/main/`,
  renderer in `gui_next/src/renderer/src/`.
- Talks to the Flask backend on :5174.
- Notable component areas: `components/library/` (DetailPanel etc.),
  `components/pipeline/` (PipelineIcon, PipelineParts — Concert Ranker pipeline UI).
- i18n: `locales/{en,de,fr,es,it,nl}.json`; en.json is source of truth, translate
  with `/gui-next-i18n` (DeepL).
- Verification: `/gui-check` (typecheck main + renderer, production build).
  **Never screenshots/browser automation** — the user checks visuals.

## gui/ — legacy PyQt6

Tab-per-feature layout: `main_window.py` plus lookup, verify, lbdir, search,
bootlegs, setup, attachments, rename, dbedit, theme, and scraper tabs.
Subdirectory rules in `gui/CLAUDE.md` (loads automatically when working there).
Qt localisation (`.ts`/`.qm`) via `/i18n-update`.

## Conventions

- GUI conventions & theming: PROJECT.md §GUI Conventions (~line 1577).
- User-facing feature changes require locale updates before session close.
