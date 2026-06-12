# 01 · Architecture

## Source file layout (prototype)

```
LosslessBob App.html          # root — loads everything in order
app.css                       # global CSS (scrollbars, sticky tables, focus rings, density)
lbb-tokens.js                 # theme engine — writes CSS custom props to :root
lbb-icons.jsx                 # <Icon name="..."/> with ~40 line icons (Lucide-style)
lbb-ui.jsx                    # primitive components — Pill, Chip, Button, Input, Card, Table*…
tweaks-panel.jsx              # design-time only (theme/screen picker overlay) — DELETE in prod
app-shell.jsx                 # <AppShell> = Sidebar + Topbar + StatusBar
app-main.jsx                  # <App> — wires shell + screens, owns nav state
screen-home.jsx
screen-pipeline.jsx
screen-search.jsx
screen-collection.jsx
screen-bootlegs.jsx
screen-settings.jsx           # contains ScreenSetup + ScreenThemes + ScreenDBEditor + ScreenScraper
```

Note: the prototype uses a single global namespace (`window.LBB_*`) because it runs as standalone HTML with `<script type="text/babel">` tags. **In production, switch to ES modules** — `import { Pill } from './ui/Pill'`, etc.

## Render shape

```
<App>                                    // owns nav state + theme tweaks
  <AppShell>                             // layout chrome
    <Sidebar>                            // 224px, fixed nav groups
    <main>
      <Topbar>                           // 52px — breadcrumbs + global search + bell
      <ScreenRouter>                     // renders one of the 16 screens
    </main>
    <StatusBar>                          // 28px — DB stats + sync state
  </AppShell>
  <TweaksPanel/>                         // design-time only — remove in prod
</App>
```

The canvas is a **fixed 1920×1080 frame** scaled to fit the viewport via `transform: scale()`. **Do not ship this scaling logic** — that's a prototype convention so it looks right in screenshots. Production should be fluid/responsive within reason (the layout is built for ≥1440px windows; minimum sensible width is ~1280px).

## Component contract — the table family

Every data table in the app uses the same shell:

```jsx
<TableShell>
  <colgroup>...</colgroup>           // explicit widths — important for fixed table-layout
  <thead><tr><TH/>...</tr></thead>
  <tbody>
    <GroupRow label="..." count={n} expanded={true} colSpan={N} />   // optional section header
    <TR edge="ok|warn|bad|info|mute" selected={bool}>                // edge = left-edge color bar
      <TD/> <TD mono/> <TD dim/> <TD align="right"/> ...
    </TR>
  </tbody>
</TableShell>
```

The **left-edge status bar** is the visual signature of the whole app — every data row has a 3px-wide colored column at its left. The body cells beneath get an optional matching tinted wash. The first `<col>` is always `width: 3` for that bar; the first `<TH>` and `<TD>` in each row are reserved for it.

Recreate this contract in the target codebase — it's load-bearing for the visual identity.

## State management

The prototype's `App` component holds everything in tweaks state (mocked). In production:

| State | Where it lives | Notes |
|---|---|---|
| Active screen / nav | URL router (Electron + react-router, or hash routing) | Each screen = a route |
| Theme (mode/accent/density) | localStorage, applied via `applyTheme()` on boot | See `02-design-tokens.md` |
| Curator mode | localStorage + IPC for sensitive ops | Default off |
| Pipeline queue, table data | App-level data store (Zustand, Redux, TanStack Query) | Mostly read-from-disk + SQLite |
| Selection (rows, filters) | Per-screen local state | Persist filters across sessions |

The actual data layer talks to **SQLite** (the `checksum_lookup.db` file mentioned in screens). Use a SQLite driver appropriate to your stack (better-sqlite3 in Electron main process, or sqlite-wasm in renderer).

## Density / mode CSS attributes

The theme engine sets these on `<html>`:

```html
<html data-mode="light|dark" data-accent="indigo|plum|..." data-density="compact|default|comfortable">
```

CSS can hook into these attributes — see `app.css` for examples. Density adjusts:
- table row height (`--lbb-d-row`)
- cell padding (`--lbb-d-pad`)
- gap (`--lbb-d-gap`)
- font size (`--lbb-d-font`)
- sidebar row height (`--lbb-d-sideRow`)

Always read density-sensitive sizes from `var(--lbb-d-*)`, never hardcode.

## What to drop on the way to production

- The `tweaks-panel.jsx` overlay (design-time tool only)
- The 1920×1080 transform scaling in `LosslessBob App.html`
- The Babel inline JSX setup
- The `window.LBB_*` global exports — switch to real imports
- Seed data arrays inside each screen file
