# 04 · App Shell

Source: `_source/app-shell.jsx`. Three pieces: `<Sidebar>` (224px left), `<Topbar>` (52px top), `<StatusBar>` (28px bottom). All theme-aware.

## Overall layout

```
┌─────────────────────────────────────────────────────────────────┐
│ Sidebar │  Topbar — crumbs · spacer · actions · search · bell   │  52px
│  224px  ├───────────────────────────────────────────────────────┤
│         │                                                       │
│  brand  │                                                       │
│  nav    │                  Active screen body                   │
│  groups │                                                       │
│  user   │                                                       │
│         ├───────────────────────────────────────────────────────┤
│         │ DB · Checksums · Imports · Bootlegs · …      · Synced │  28px
└─────────────────────────────────────────────────────────────────┘
```

`AppShell` is a flex column. The middle row is a flex row of `<Sidebar>` + `<main>`. `<main>` is a flex column containing `<Topbar>` + scrollable body. `<StatusBar>` sits below the whole thing.

## Sidebar (224px)

### Sections, top to bottom

1. **Brand block** (top, 1px bottom border)
   - 30×30 square with `LB` glyph — `accent-mid` bg, `accent-onMid` text, weight 800
   - Stacked: "LosslessBob" 14px/700, then `"Checksum Lookup · v3.2.0"` 10.5px `fg3`

2. **Nav groups** (scrollable)
   - Each group has an uppercase `fg3` label (10px, weight 700, `letter-spacing: 0.12`)
   - Nav items are buttons: `padding: 7px 10px`, gap 10px, 12.5px text
   - Active state: `accent-soft` bg, `accent-mid` text, weight 600
   - Hover (non-active): `surface2` bg
   - Right-side trailing slot: `count` (tabular-nums) OR `NEW` badge
   - Icon left (15px)

3. **Curator promo card** (only when Curator mode is OFF)
   - Dashed-border tile, `surface2` bg, fg3 prompt + accent CTA

4. **User chip** (bottom, 1px top border)
   - 28×28 circle initials, user.handle + meta, overflow menu icon

### Nav structure (canonical)

```js
const NAV_GROUPS = [
  { label: null,
    items: [{ id: "home", label: "Home", icon: "home" }] },
  { label: "Ingest", items: [
    { id: "pipeline", label: "Pipeline", icon: "pipeline", featured: true },  // NEW badge
    { id: "verify",   label: "Verify",   icon: "verify" },
    { id: "lookup",   label: "Lookup",   icon: "lookup" },
    { id: "rename",   label: "Rename",   icon: "rename" },
    { id: "lbdir",    label: "LBDIR",    icon: "lbdir" },
  ]},
  { label: "Library", items: [
    { id: "collection", label: "My Collection", icon: "collection", count: 15967 },
    { id: "search",     label: "Search",        icon: "search" },
    { id: "bootlegs",   label: "Bootlegs",      icon: "bootlegs", count: 1380 },
  ]},
  { label: "Assets", items: [
    { id: "attachments",  label: "Attachments",  icon: "attachments" },
    { id: "spectrograms", label: "Spectrograms", icon: "spectro" },
    { id: "map",          label: "Map",          icon: "map" },
  ]},
  // ──── Curator-gated group ────
  { label: "Curator", gatedGroup: true, items: [
    { id: "dbeditor", label: "DB Editor", icon: "dbeditor" },
    { id: "scraper",  label: "Scraper",   icon: "scraper" },
  ]},
  { label: "Settings", items: [
    { id: "setup",  label: "Setup",  icon: "setup" },
    { id: "themes", label: "Themes", icon: "themes" },
  ]},
];
```

When `gatedGroup: true` and curatorMode is off, **the whole group renders nothing** (no label, no items). When curatorMode is on, the group label gets a small amber `CURATOR` badge next to it.

The featured `NEW` badge on Pipeline disappears when the item is active.

## Topbar (52px)

Left → right:
1. **Breadcrumbs** — array of strings like `["LosslessBob", "Library", "My Collection"]`. Slashes between. Last crumb weight 600 `fg`, earlier weight 500 `fg2`.
2. **Flex spacer**
3. **Per-screen actions slot** — `<Topbar actions={...}>` lets screens inject extra buttons here. Currently none use it heavily.
4. **Global search button** — pill-shaped, `surface2` bg, 280px min-width. Click opens cmd-K palette. Renders `Find LB#, folder, location…` placeholder + `⌘K` keyboard hint pill.
5. **Bell** — 34×34 icon button with a tiny red dot when there are notifications.

Bottom border `1px var(--lbb-border)`, bg `var(--lbb-surface)`.

## StatusBar (28px)

Persistent footer with read-only system stats. Mono 11px font.

```
● DB: LB-16630   ·   Checksums: 704,624   ·   Last import: 2026-05-21   ·   Bootlegs: 1,380          🛡 Synced · idle
```

The `●` is a 6px dot in `var(--lbb-{tone}-bar)` for the DB freshness state. `·` separators in `border2` color. Right-side shield icon + "Synced · idle" in `fg3`.

The screen can inject one extra status item via `<AppShell statusExtra={...}>`. The Pipeline screen, for instance, would show queue progress here in production.

## AppShell props

```js
<AppShell
  active={"pipeline"}                 // active screen id
  onNav={fn}                          // (id) => void
  curatorMode={false}
  crumbs={["LosslessBob", "Ingest", "Pipeline"]}
  topActions={null}                   // optional ReactNode injected into topbar
  statusExtra={null}                  // optional ReactNode appended to status items
>
  {/* screen body */}
</AppShell>
```

## Responsive notes

The shell is designed for ≥1440px windows. At ~1280px the sidebar might want to collapse to icons-only; that variant **wasn't built** — design + ship it as a stretch goal. Below 1280px the table-heavy screens would be unusable.
