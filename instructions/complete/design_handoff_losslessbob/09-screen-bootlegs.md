# 09 · Bootlegs (LBBCD Catalog)

Source: `_source/screen-bootlegs.jsx`. The bootleg-CD title catalog (1,380 titles).

## Purpose

The LBBCD catalog is a separate dataset — names of bootleg releases (like "A Bird's Nest In Your Hair") that correspond to one-or-more LB# recordings. Lets the user browse those titles, see their tracklists, and jump to the underlying recording.

## Layout

Mirrors Collection's two-pane shape:

```
┌──────────────────────────────────────────────────────────┐
│ Heading row — H1 + count + Export/Refresh buttons        │
│ Search + Year/CDs/Status dropdowns + chips               │
├────────────────────────────────────┬─────────────────────┤
│                                    │                     │
│  Main table (9 cols)               │  Detail panel       │
│  - LB# / Title / Date / Year /     │  (380px)            │
│    Location / CDs / Status / Owned │                     │
│                                    │  - LB# block        │
│                                    │  - Cover art card   │
│                                    │  - Tracklist meta   │
│                                    │  - CTAs             │
│                                    │  - Other titles     │
└────────────────────────────────────┴─────────────────────┘
```

Grid: `1fr 380px`.

## Heading

- H1 "Bootleg titles" (20/700) + 13 fg3 "1,380 titles · LBBCD catalog"
- Right: ghost "Export CSV", secondary "Refresh LBBCD"

## Filter row

- Search input (360px) "Search title or location…"
- Three ghost dropdowns: "Year", "CDs", "All statuses"
- Chips: Owned (1210) / Unowned (170) / Private (42)
- Spacer + ghost "Clear"

## Table

Columns: edge / LB# / Title / Date / Year / Location / CDs / Status / Owned

- LB# mono accent-mid 600
- Title: regular text, **bold (600) when row is selected**
- Date: mono "06/29/81"
- Year: mono 4-digit
- CDs: small int, centered, mono
- Status: Pill (Public ok / Private info)
- Owned: check or x icon

## Detail panel (380px)

1. **Heading**: uppercase fg3 "BOOTLEG DETAIL"
2. **LB# block**: mono 14/700 accent-mid + H2 title (20/700) + 12 fg2 meta line w/ LBBCD catalog number
3. **Cover art placeholder**:
   - 200px tall, radius 8
   - Background: `linear-gradient(135deg, #1c1a17 0%, var(--lbb-accent-lo) 100%)`
   - Hatch pattern overlay at 25% opacity: `repeating-linear-gradient(45deg, transparent 0 12px, rgba(255,255,255,0.08) 12px 13px)`
   - White text bottom-stacked: label "Bird's Nest Records · 1981" + title + meta
   - This is intentionally a stylized placeholder; in production it should be replaced with actual cover art when scraped, falling back to this generated look
4. **Tracklist meta grid**: 2-col, 90px / 1fr, 12px font
   - Disc 1 / 2 — track count + duration (mono)
   - Source description
   - Notes
5. **CTAs**: primary "Open in search" + secondary "Open LBBCD"
6. **Other titles section**: section header + small dashed-bordered note (in this case "Only bootleg title issued for LB-18.")

## Data shape

```ts
type BootlegRow = {
  lb: string;              // "LB-00018"
  title: string;
  date: string;
  year: number;
  location: string;
  cds: number;
  status: "Public" | "Private";
  owned: boolean;
};

type BootlegDetail = BootlegRow & {
  lbbcdCatalog: string;    // "LBBCD-00231"
  discs: { trackCount: number; duration: string }[];
  source: string;
  notes: string;
  otherTitlesForSameLB: BootlegRow[];
  coverArt: { url: string | null; label: string; year: number };
};
```

## Interactions

- Click row → load detail panel
- "Open in search" → routes to Search screen with this LB# pre-filled
- "Refresh LBBCD" → kicks off the LBBCD scraper (see Scraper screen) for just this catalog
