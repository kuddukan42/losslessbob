# 12 · Settings — Setup & Themes

Source: `_source/screen-settings.jsx` (`ScreenSetup` and `ScreenThemes` functions).

## Setup

### Purpose

DB management, integrations, preferences, master-data tooling. Outer padding `24px 32px 40px`, max-width 1500 centered. H1 "Setup" + 13 fg3 subtitle.

### Layout: 2-column grid of `<SetupCard>`s

`<SetupCard>` is a local helper — `surface` bg, `border` outline, radius 10, padding 18. Title row: uppercase 12/700 + optional Pill badge. Body below.

Card grid:

```
┌─────────────────┬─────────────────┐
│ Database        │ Master Data     │
│   ok pill       │   curator toggle│
├─────────────────┴─────────────────┤
│ Integrations  (span 2)            │
│   3-col: qBittorrent / forum / web│
├─────────────────┬─────────────────┤
│ Preferences     │ Data purges     │
├─────────────────┴─────────────────┤
│ Flat file history  (span 2)       │
└───────────────────────────────────┘
```

### Database card

- Badge: `<Pill tone="ok" soft dot>connected</Pill>`
- Meta grid (2-col, label / value): Active (button-dropdown "LossLessBob") / Checksums (mono "704,624") / LB entries / Last import / DB size
- 4-button row: secondary "Import DB file…", secondary "Check for update", ghost "Open data folder", **danger "Reset DB…"**
- "Helpers" strip: `surface2` bg, 11.5 text. Each helper = colored dot + name. Right-side ghost "Re-check"

### Master Data card (the Curator toggle)

- The Curator switch is the centerpiece.
- Big inset block: 38×38 icon square (warn-tinted when on) + label/desc + custom toggle switch (44×24, accent-mid when on, animates the 20×20 white knob from left=2 to left=22)
- Below: master version meta + secondary "Publish master update…" (disabled when curator off) + ghost "Install master update…"

### Integrations card (full width)

3-col grid of `<Integ>` mini-cards:
- Title (12/600) + status Pill (ok/warn/mute)
- 2-col label/value grid (mono values)
- Bottom: ghost "Test" + secondary "Edit…"

Integrations shown: qBittorrent, Watching the River Flow forum, Torrent web UI.

### Preferences card

- 2-col grid, 140px labels / values, 8px row gap
- Rows: Interface language (dropdown) / Results per page (segmented 50/100/250/All) / Column widths (3 buttons) / Auto-scrape on import (checkbox) / Send anon. usage (checkbox)

### Data purges card

- Same 1-col list of purge actions, each a label + ghost "Purge…" button
- Bottom fg3 note: "User data only. The checksum archive is never affected."

### Flat file history card

- Full-width table: Detected timestamp / Filename / Status pill / Added (mono) / Changed (mono) / Action button

## Themes

### Purpose

Live preview of mode × accent × density. Status colors are pinned (note at bottom of Advanced card).

### Layout: 2-col grid of cards

```
┌─────────────────┬─────────────────┐
│ Mode            │ Density         │
├─────────────────┴─────────────────┤
│ Accent  (span 2)                  │
├─────────────────┬─────────────────┤
│ Typeface        │ Advanced        │
├─────────────────┴─────────────────┤
│ Live preview  (span 2)            │
└───────────────────────────────────┘
```

### Mode card
- 3 tiles (Light / Dark / System) — each a button with a small preview swatch (sidebar+main mock 80px tall) + label below
- Active tile: 2px accent-mid border (vs 2px border default)

### Density card
- 3 tiles (Comfortable / Default / Compact) — each shows N stacked grey bars at the matching height to visualize row density. Label + "~25/32/55 rows" sub-line.

### Accent card (span 2)
- Row of 8 circular swatch tiles, one per accent. 50×50 circle + label below. Active = 2px accent-mid border.

### Typeface card
- 3 stacked buttons (Inter / IBM Plex Sans / Source Sans 3). Each: title (13/600) + subtitle (11.5 fg3). Selected: 1px accent-mid border + check icon right.
- Bottom fg3 note: "Size: 12pt · 13pt · 14pt"

### Advanced card
- 3 buttons: secondary "Custom color tokens…" / ghost "Export theme as JSON" / ghost "Import theme…"
- Bottom info box (surface2 bg): note about status colors being pinned

### Live preview card (span 2)

The critical card. Shows a miniature "Library / My Collection" frame:
- Top: accent-mid filled bar with white icon + crumb-style title "Library / My Collection" + meta
- Body: `var(--lbb-bg)` bg with a TableShell (4 rows showing one of each edge color: ok/warn/bad/info) + below the table a row of Chips + Pills

This preview live-updates as the user clicks any mode/accent/density option above — that's the whole point of the screen.

## Both screens accept these props

```js
{ curatorMode, onSetCurator, tweaks, setTweak }
```

- `tweaks` = the current theme state object `{ mode, accent, density }` (plus `curatorMode` and `screen` in the prototype, but in production those are routing/auth state, not theme)
- `setTweak(key, value)` writes the new value; this should call `applyTheme()` and persist to localStorage
