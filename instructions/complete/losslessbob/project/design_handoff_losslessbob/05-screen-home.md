# 05 · Home / Dashboard

Source: `_source/screen-home.jsx`. The landing screen.

## Purpose

Three things, in priority order:

1. **Get the user into the Pipeline** (the primary workflow) with one click
2. **Show "what changed since last visit"** — recent activity log
3. **Resume any incomplete work** — paused verify, half-applied rename batch, etc.

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Welcome strip — "Welcome back, Rolling" + headline + CTA buttons│
├──────────────────────────────────────┬───────────────────────────┤
│                                      │  At a glance              │
│  Hero ingest card                    │  (4 stats grid)           │
│  (dropzone + 4-step pipeline strip)  ├───────────────────────────┤
│  ratio 1.45fr                        │  Jump to                  │
│                                      │  (4 nav tiles)            │
├──────────────────────────────────────┼───────────────────────────┤
│                                      │  Continue where you left  │
│  Recent activity table               │  off                      │
│  (7-row sample)                      ├───────────────────────────┤
│                                      │  Tips                     │
└──────────────────────────────────────┴───────────────────────────┘
```

Two-column grid, 1.45fr / 1fr, gap 18px. Outer padding `24px 28px 36px`, max-width 1680px centered.

## Pieces

### Welcome strip
- Left: tiny uppercase `fg3` eyebrow `"Welcome back, Rolling"`, then big H1 `Your collection · 15,967 entries` (28px, 700), then meta line w/ mono LB#
- Right: two buttons — secondary `Check for DB update`, primary `Ingest new folders` (→ Pipeline)

### Hero ingest card (top-left)
- Background: `linear-gradient(180deg, var(--lbb-accent-soft), var(--lbb-surface))`
- Border: `1px solid var(--lbb-accent-mid)`, radius 12, padding 22
- Top eyebrow pill: white bg + accent border + accent text, "PRIMARY WORKFLOW"
- Big dropzone: 100% wide, 2px dashed accent border, radius 10, `surface` bg, padding 30px 20px
  - Centered: `folderPlus` icon + "Drag folders here · or click to browse"
- Below: 4-step strip — 4 equal tiles in `grid-template-columns: repeat(4, 1fr)`, each containing a numbered circle + step icon + step label
  - Steps: Verify checksums → Lookup LB# → Rename folder → Check LBDIR

### At a glance (top-right top)
- `<Card>` with 2x2 grid of `<Stat>`: 15,967 / 663 / 3 / 1,380
- Bottom info strip: `surface2` bg, check icon + "704,624 checksums indexed across 4 mounts"

### Jump to (top-right bottom)
- `<Card>` with 2x2 grid of button-tiles. Each tile:
  - 30×30 rounded accent-soft icon square
  - Label (12.5/600) + tabular-nums sub-count (10.5 fg3)
  - Trailing chev-right icon
  - Hover: bg goes `surface` → `surface2`

### Recent activity (bottom-left)
- `<Card pad={0}>` so the table touches the card edges
- Table action button (top-right of card header): ghost "View full log →" in accent color
- TableShell with columns: When / Action / Target / Result
  - 7 sample rows with mixed `edge` colors (ok/info/warn/mute)
  - "When" col uses mono "2h ago" / "yesterday" / etc.
  - "Result" col is always a Pill

### Continue where you left off (bottom-right top)
- `<Card>` containing one inset warn-bg block:
  - Top row: small alert icon + `<Pill tone="warn">Verify · incomplete</Pill>`
  - Title: bold folder name
  - Meta: "18 of 36 files missing · paused 3 days ago"
  - Two CTAs: primary `Resume in Pipeline`, ghost `Dismiss`
- This card is **conditional** — only renders when there's an unfinished workflow.

### Tips (bottom-right bottom)
- `<Card>` with 3 tip rows: icon + 11.5px copy with inline `<span class="kbd-pill">⌘K</span>` mentions

## Data needs

| What | Source |
|---|---|
| User name + collection count | User store + library count from DB |
| LB# version | `SELECT MAX(lb_number) FROM lb_master` |
| Stats (15967/663/3/1380) | Counts from collection / wishlist / bootleg tables |
| Recent activity log | An app-events table (writes on every import / verify / rename / etc.) |
| Resume card | The pipeline state store — if a workflow is paused, show it |

## Interactions

- All cards' primary CTAs and Jump-to tiles call `onNav(screenId)` to route to that screen
- Dropzone accepts native drag-drop (HTML5 drag events on the button) → opens Pipeline screen with the dropped paths prefilled
- "View full log" → routes to a full activity log screen (not yet designed)
