# 07 · My Collection

Source: `_source/screen-collection.jsx`. The user's owned recordings (~15,967 rows).

## Purpose

Lets the user browse, filter, and act on what they own. Selecting a row opens a detail panel on the right with metadata, history, and per-item actions.

## Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ Heading row — H1 + count + export/torrent buttons                  │
│ Filter chips row — All / Missing / Wishlist / Duplicates / …       │
├────────────────────────────────────────────────────────────────────┤
│ Inline action toolbar — Add / Scan / Update / Remove + meta stats  │
├──────────────────────────────────────────┬─────────────────────────┤
│                                          │                         │
│  Main table (10 cols, edge bars)         │  Detail panel (360px)   │
│  - LB# / Status / Date / Location /      │  - Pills row            │
│    Folder / Disk path / Confirmed / FP   │  - LB# + title block    │
│  - Edge color from row.status            │  - Meta grid            │
│                                          │  - Action buttons       │
│                                          │  - History list         │
└──────────────────────────────────────────┴─────────────────────────┘
```

Inner grid: `grid-template-columns: 1fr 360px`.

## Heading

- H1 "My Collection" (20px/700) + 13px fg3 count "15,967 items · across 4 mounts"
- Right-side buttons (small): ghost "Export HTML", ghost "Export M3U", secondary "Create torrent", **primary "Add to qBittorrent"** (this is the headline action — wires to qBittorrent integration)

## Filter chips

Row 1 (replaces tabs): All / Missing / Wishlist / Duplicates / Forum history / Torrent history — each with count
Separator
Row 1 cont: Unconfirmed / No fingerprint

Right side: filter input (320px), ghost "All years" dropdown, "Xref only" checkbox label

## Inline toolbar

Small action row below the filters:
- Secondary: `Add single folder`, `Scan directory`, `Scan tree…`
- Separator
- Ghost `Update location`, danger `Remove`
- Spacer
- Right-aligned meta: "15,925 confirmed · 15,839 fingerprinted"

## Main table

10 columns. Always virtualized in production.

| Col | Width | Notes |
|---|---|---|
| edge bar | 3px | reserved |
| checkbox | 36px | per-row selection |
| LB# | 100px | mono, **accent-mid color, 600 weight** |
| Status | 90px | Pill — Public / New / Missing |
| Date | 100px | mono (mm/dd/yy format) |
| Location | flex | fg color |
| Folder | 240px | mono, the on-disk folder name |
| Disk path | 200px | mono, dim, the parent path |
| Confirmed | 90px | mono dim, ISO date or "yesterday" |
| FP | 40px center | check or x icon |

Row edge color from status field: ok = "Public", warn = "Missing", info = "New".

## Detail panel (right, 360px)

Renders when a row is selected. From top:

1. **Pill row**: ownership pills — e.g. `<Pill tone="ok" soft dot>Owned</Pill> <Pill tone="info" soft>Public</Pill> <Pill tone="mute" soft>FLAC · 16/44</Pill>`

2. **ID + title block**:
   - LB# mono 16/700 accent-mid
   - Title 16/700
   - Meta 12 fg2: "1981-06-29 · Earl's Court, London · 2 CDs"

3. **Meta grid** in a `surface2` boxed inset:
   - 2-col grid, 80px label / 1fr value, 11.5px font
   - Rows: Folder / Disk path / Size / Confirmed / Fingerprinted / Rating
   - Values mono where appropriate; some are Pills (e.g. Rating "A−", Fingerprinted "Yes · acoustid")

4. **Action buttons** (small, wrap):
   - secondary "Reveal on disk" (icon reveal)
   - ghost "Attachments" / "Spectrograms" / "On map" — these navigate to that screen filtered to this LB#

5. **History section**:
   - Section header "HISTORY" (uppercase fg3 11/700)
   - Sub-tabs (Chip-style): Torrents (active) / Forum posts
   - Outlined list of history items: date (mono) + filename (mono) + Pill ("In qBt" or "Local")
   - Two ghost buttons below: "Regenerate", "Post to forum"

## Data shape

```ts
type CollectionRow = {
  lbNumber: string;          // "LB-18"
  status: "Public" | "Private" | "New" | "Missing";
  date: string;              // "06/29/81" — mm/dd/yy, allow "xx" for unknowns
  location: string;
  folder: string;            // on-disk folder name
  diskPath: string;          // parent dir
  confirmed: string;         // ISO date or relative
  fingerprinted: boolean;
};
```

## Interactions

- Single-click row → load detail panel + select that row (edge stays, bg becomes `accent-soft`)
- Double-click row → reveal folder in OS file manager
- Checkbox → multi-select for bulk actions (Remove, Update location)
- Chips are stateful filters; multiple can be active
- "Add to qBittorrent" → batch-add selected items to the configured qBittorrent client (see Integrations in Setup)
- Export HTML / M3U → write files via Electron's file save dialog
