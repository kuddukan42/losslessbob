# LosslessBob — Unified Library · Developer Handoff

This bundle is the **complete, build-ready** spec for the new **unified Library**
screen — the one that merges *Search* and *My Collection* into a single
catalogue with two lenses ("By performance" and "By recording").

It is **scoped to the Library screen only.** Pipeline, Verify, Lookup, Rename,
LBDIR, Bootlegs, Map, Attachments, Spectrograms and Setup already exist and are
**out of scope** — do not touch them. The Library ships as a **brand-new tab
added alongside** the existing Search and My Collection tabs, which stay live
and functional until the unified view fully replaces them later.

## Why this bundle exists (read this first)

Previous handoffs left gaps: things that *looked* functional in the design demo
but had no real plumbing behind them, so when code took over they silently
broke or shipped fake values. This bundle is written to make that impossible:

- **Every visible number is traced to a field or flagged as seed data.**
  See `04-seed-data-and-punchlist.md` — the status-bar counts, sidebar badges,
  facet tallies and coverage figures are all illustrative. Do not ship them as
  literals; wire each to the source listed.
- **Every inert button is documented as a TODO**, with its intended behavior
  and the data it needs — never left to "obvious from the demo."
- **Functionality that must NOT be lost** in the merge (right-click row menus;
  detail-panel quick actions like torrent history, forum posting, qBittorrent,
  spectrograms, map) has an explicit **parity checklist** in
  `02-action-system-parity.md`.
- **The family / TapeMatch concept has a defined fallback**: when the backend
  clustering isn't ready, the Library degrades to flat, ungrouped LB# rows —
  fully usable. Contract in `03-data-contract.md`.

## Documents

| Doc | What it covers |
|---|---|
| `00-overview.md` | Screen anatomy, the two lenses, what's new vs. reused |
| `01-theme-additions.md` | New Themes controls: **card style (framed/flat)** + **frame palettes**; refined **light** token tables (1:1 with dark) |
| `02-action-system-parity.md` | The shared action system, right-click menu, redesigned panel workflows, and the **don't-lose-this** parity checklist |
| `03-data-contract.md` | Field shapes the UI reads (performance, recording, family, history) + the **no-families fallback** |
| `04-seed-data-and-punchlist.md` | Every illustrative value to replace + every inert control as a TODO |
| `05-integration.md` | How the new tab slots in **additively** without disturbing Search / Collection |
| `06-pixel-spec.md` | **Exact layout geometry** — every dimension lifted from source. **Use as the layout source of truth; it overrides the `00` ASCII diagram.** |

## Source files

`_source/` holds the canonical prototype files. They are a **design reference**,
not a drop-in module — port the structure into your stack (the theme engine is
plain JS and can be lifted nearly verbatim; the React components are a faithful
behavioral spec). The live prototype is `Library (Unified).html` at project root.

| File | Role |
|---|---|
| `libu-app.jsx` | Screen shell, view toggle, theme wiring, Themes/Tweaks state |
| `libu-performance.jsx` | "By performance" lens (shows → families → recordings) |
| `libu-recording.jsx` | "By recording" lens (flat LB# rows) |
| `library-parts.jsx` | Recording-lens sub-components (facets, detail panel, bulk bar) |
| `perf-parts.jsx` | Performance-lens sub-components (rollups, families, detail panel) |
| `libu-actions.jsx` | **The shared action system** — registry + context menu + panel workflows |
| `library-data.js` / `perf-data.js` | Sample datasets (see data contract for real shapes) |
| `lbb-tokens.js` | Theme engine — modes, accents, density, **frame palettes** |
| `lbb-ui.jsx` / `lbb-icons.jsx` | Primitives + icon set |
| `app.css` | Globals + the **`--sep-*` framed-card recipe** |
| `app-shell.jsx` | Sidebar + topbar + status footer (reused, not modified here) |
