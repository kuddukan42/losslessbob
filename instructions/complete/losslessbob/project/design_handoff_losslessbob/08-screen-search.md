# 08 · Search (Master DB)

Source: `_source/screen-search.jsx`. Search across all 16,630 master-DB entries (vs. Collection which is only the user's 15,967).

## Purpose

Lookup any LB# / show / location across the entire catalog, with faceted filtering, saved views, and group-by.

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ Facet rail │  Big search input + dropdowns + export              │  ~64px
│   260px    ├──────────────────────────────────────────────────────┤
│            │  Result summary strip — counts + active filters     │  ~40px
│ - Saved    ├──────────────────────────────────────────────────────┤
│   views    │                                                     │
│ - Decade   │  Results table — grouped by year                    │
│ - Status   │    GroupRow "1980 · 18 results"                     │
│ - Rating   │    GroupRow "1981 · 32 results"                     │
│ - Source   │    GroupRow "1982 · 41 results"  (collapsed)        │
│ - Ownership│    …                                                │
│ - Year     │                                                     │
│   range    │                                                     │
│            │                                                     │
└────────────┴─────────────────────────────────────────────────────┘
```

Inner: `display: flex` with a 260px aside + flex-1 main.

## Facet rail (260px)

Top section (with bottom border):
- **Saved views** label (uppercase fg3 10.5/700)
- Each view = a clickable row: star icon + name + count (right-aligned mono)
  - Active view = `accent-soft` bg + filled star
  - Last entry: dashed-border "+ Save current filter as view" button

Scrollable body:
- **Decade** facet — `<FacetGroup>` w/ uppercase title + chev-down toggle, wrapped chips below
- **Status**, **Rating**, **Source** — same shape
- **Ownership** — segmented 3-button control (Any / Owned / Not owned)
- **Year range** — custom dual-handle slider (10–13px), mono year labels below ("1961" / "2030")
- Bottom: ghost "Clear all filters" block button

Chips inside facets use `size="sm"`. Active facets have `active={true}`.

## Main results pane

### Big search toolbar (top)
- `<Input size="lg" placeholder="Search title, location, description, LB# …" />` flex-1, height 38
- Secondary "All Fields" dropdown
- Separator
- Secondary "Group by year" w/ filter icon + chev-down
- Secondary "Columns" w/ chev-down
- Icon buttons: download (export CSV), more

### Result summary strip
- Bold "245 results" + fg3 "of 16,630"
- Separator
- Active filter chips: `ActiveFilter` component — accent-soft bg, 4px radius, accent text, x-close button right
- Spacer
- "Sort:" label + ghost "LB# ↑" w/ chev-down + ghost "⌘F find in results"

### Results table

Columns: edge / LB# / Status / Date / Location / ★ (rating) / Description / Xref / Own / spacer

Grouped by year via `<GroupRow>`. Some groups collapsed (`expanded={false}` shows only the header, body hidden).

Row anatomy:
- LB# mono accent-mid 600 weight
- Status: Pill (Public/Missing/Private)
- Date mono
- Location truncates with ellipsis (white-space nowrap)
- Rating: `<RatingChip>` — Pill colored by grade (A/A− → ok, B+/B → info, B−/C → warn/mute)
- Description fg2
- Xref mono dim, right-aligned
- Own: check or x icon, centered
- Trailing more icon

## Data shape

```ts
type SearchRow = {
  lb: string;
  status: "Public" | "Private" | "Missing";
  date: string;
  location: string;
  rating: "A" | "A−" | "B+" | "B" | "B−" | "C" | "—";
  description: string;
  xref: string | null;
  owned: boolean;
};
```

## Interactions

- Typing in the search input → debounced filter (200ms)
- Facet chips toggle on click; multi-select within a facet means OR, across facets means AND
- Year-range slider drags update both handles
- ⌘F focuses the in-results find input
- Click LB# in any row → open that entry in the entry-drillin overlay (not yet built, but slot exists)
- Saved views: clicking applies all stored filters at once
- "Save current filter as view" → opens small modal asking for name

## Production notes

- SQLite FTS5 is the right fit for the full-text search. Index `lb_master.location || description || venue || city`.
- Faceted counts should re-compute on each filter change but use cached query plans where possible.
- The "Group by year" toggle is one of several group-by options (by decade, by rating, by status). The dropdown currently only shows "Group by year" but should expand.
