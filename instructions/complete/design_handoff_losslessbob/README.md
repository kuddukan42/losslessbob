# LosslessBob — Developer Handoff

This bundle is a **design reference** for the LosslessBob desktop app: a Bob Dylan recording archive tool that manages a large checksum/bootleg database, ingests new folders, and lets a collector search & maintain their library.

The files in `_source/` are HTML/JSX prototypes built with React + Babel — they show the **intended look and behavior**, not production code to ship as-is. Your job is to recreate these designs in the target codebase's environment (likely Electron + React + Vite, or whichever stack the existing LosslessBob app uses), following its established patterns.

If there is no existing codebase yet, pick the framework that fits a cross-platform desktop file-manager-style app best (Electron+React, Tauri+React, or native if scoped).

## Fidelity

**High-fidelity.** Colors, typography, spacing, layout, density modes, theme system, and interaction patterns are all final. Recreate pixel-perfectly using the codebase's existing libraries (or pick equivalents — e.g. TanStack Table for the virtualized data grids).

The mocks use static seed data. Wiring to real data is the developer's job; the design assumes virtualization (15K+ rows in My Collection, 100K+ in DB Editor tables).

## Yes — this can be attacked incrementally

You do **not** need to ship the whole thing at once. The design is structured into discrete, mostly-independent units:

1. **Foundation** — design tokens + primitives + app shell. Ship first; everything else depends on it.
2. **Each screen is independent** — start with the highest-value ones (Pipeline, Home, Collection) and add the rest over time. Stubs are fine for screens not yet built.
3. **Curator mode is gated** — the DB Editor + Scraper screens hide behind a toggle and can be deferred.

The MD sections below are ordered roughly by build dependency. A developer (or Claude Code) can be pointed at any single section and asked to implement just that piece.

## How to read this bundle

| File | What it covers | When to read |
|---|---|---|
| [`00-overview.md`](./00-overview.md) | Product context — what LosslessBob is, who uses it, what each screen does | Once, up front |
| [`01-architecture.md`](./01-architecture.md) | File layout, render shape, how the shell + screens connect, state management notes | Before writing any code |
| [`02-design-tokens.md`](./02-design-tokens.md) | Full color/type/spacing/density token system | Before building primitives |
| [`03-primitives.md`](./03-primitives.md) | Pill, Chip, Button, Input, Card, Table family, icons | Build this layer first |
| [`04-app-shell.md`](./04-app-shell.md) | Sidebar + topbar + status footer | Build right after primitives |
| [`05-screen-home.md`](./05-screen-home.md) | Dashboard / Home | Per-screen — implement in any order |
| [`06-screen-pipeline.md`](./06-screen-pipeline.md) | ⚠️ *Superseded* — original batch-table pipeline (background only) | Skim |
| [`13-pipeline-workspace-target.md`](./13-pipeline-workspace-target.md) | **START HERE for pipeline work** — the visual target, why the build fell short, the plan | **Pipeline — read first** |
| [`14-pipeline-gap-punchlist.md`](./14-pipeline-gap-punchlist.md) | Harvest map + per-stage gaps + exact copy + commit order | After doc 13 |
| [`15-data-contract.md`](./15-data-contract.md) | What data already exists vs. the new Collect mount fields | With doc 14 |
| [`07-screen-collection.md`](./07-screen-collection.md) | My Collection (15,967-row library) | Per-screen |
| [`08-screen-search.md`](./08-screen-search.md) | Master-DB search w/ facets | Per-screen |
| [`09-screen-bootlegs.md`](./09-screen-bootlegs.md) | Bootleg-titles catalog | Per-screen |
| [`10-screens-stub.md`](./10-screens-stub.md) | Verify, Lookup, Rename, LBDIR, Attachments, Spectrograms, Map — designs not yet rendered, behavior described | Reference / future work |
| [`11-screens-curator.md`](./11-screens-curator.md) | DB Editor + Scraper (gated behind Curator mode) | Defer |
| [`12-screens-settings.md`](./12-screens-settings.md) | Setup + Themes | Per-screen |
| [`13-implementation-plan.md`](./13-implementation-plan.md) | **Suggested attack order** + Claude Code prompt templates | Read after 00–04 |
| `_source/` | All original HTML, JSX, CSS files — the source of truth | Reference any time |

## How to use this with Claude Code

In Claude Code, point at the bundle root and prompt one section at a time. Example prompt:

> Read `design_handoff_losslessbob/README.md`, `01-architecture.md`, and `02-design-tokens.md`. Then implement the design tokens described in `02-design-tokens.md` for our codebase. Use the reference at `_source/lbb-tokens.js`.

Then iterate:

> Now implement the primitives described in `03-primitives.md`, using the reference at `_source/lbb-ui.jsx`.

See `13-implementation-plan.md` for a full attack sequence with ready-to-use prompts.

## Files
- `_source/LosslessBob App.html` — the live prototype root
- `_source/*.jsx` — React components
- `_source/pipeline2-*.jsx` + `_source/pipeline2-data.js` — **the current Pipeline Workspace** (app, shell, stages, parts, confirm, quicklookup). Build the pipeline from these, not `screen-pipeline.jsx`.
- `_source/lbb-tokens.js` — theme engine (plain JS, not JSX)
- `_source/app.css` — global styles
