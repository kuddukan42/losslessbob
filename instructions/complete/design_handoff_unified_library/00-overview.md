# 00 · Overview — the unified Library

## One catalogue, two lenses

The Library is a single screen over a single row universe (every release Bob
Dylan recording the user knows about, owned or not). A segmented toggle in the
toolbar switches the *lens*, never the data:

- **By performance** — rows are **shows** (date + venue). Each show expands to
  the **recordings** of it, optionally clustered into **families** (TapeMatch
  groups near-identical transfers of the same source tape). This is the new,
  richer way to browse — "what nights exist, and how well do I cover them."
- **By recording** — rows are **flat LB# entries**, one per recording. This is
  the familiar Collection/Search list — "what individual files/torrents exist."

Both lenses share: the toolbar, the left **facet rail**, the right **detail
panel**, the **bulk action bar**, theming, and — critically — the **action
vocabulary** (see `02-action-system-parity.md`).

## Screen anatomy

```
┌──────────────────────────────────────────────────────────────┐
│ Toolbar:  [By performance | By recording]  search · sort · ⋯  │
├───────────┬──────────────────────────────────┬───────────────┤
│           │  Result table                     │               │
│  Facet    │  (shows+families, or flat LB#)    │  Detail panel │
│  rail     │  · right-click row → context menu │  (selected    │
│  (filters)│  · checkbox select → bulk bar     │   row)        │
│           │                                    │               │
├───────────┴──────────────────────────────────┴───────────────┤
│ Status footer  (see seed-data inventory — counts are samples) │
└──────────────────────────────────────────────────────────────┘
```

The facet rail, table, and detail panel are independently lifted into elevated
cards when **card style = framed**, or sit flush on the body when **flat**
(see `01-theme-additions.md`).

## What's NEW in this screen

1. **The performance lens** — show-grouped browsing with family clustering and
   per-show coverage rollups. Entirely new; no prior screen had it.
2. **The unified detail panel** — redesigned with **intent zones** (action bar →
   share & seed → assets → setlist) instead of the old flat button rows.
3. **The shared action system** — one registry drives both the right-click menu
   and the panel action bar, so they can't drift.
4. **Two new Themes controls** — card style (framed/flat) and frame palette.
5. **Refined light palettes** — light now mirrors the dark hues 1:1.

## What's REUSED (do not rebuild)

- The **app shell** (`app-shell.jsx`): sidebar nav, breadcrumb topbar, status
  footer. The Library mounts inside it.
- The **theme engine** (`lbb-tokens.js`), **primitives** (`lbb-ui.jsx`), **icons**
  (`lbb-icons.jsx`), and **globals** (`app.css`). The only token change is the
  refined light palettes (§01); the only CSS addition is already present
  (`--sep-*`).
- The **detail-panel quick actions** that exist in today's Collection screen
  (torrent history, forum posting, qBittorrent, spectrograms, map). These are
  carried forward — see the parity checklist in §02.

## Build order suggestion

1. Land the theme additions (§01) — cheap, isolated, unblocks visual review.
2. Build the **By recording** lens first — it's the flat list, closest to the
   existing Collection, and is also the **no-families fallback** target (§03).
3. Layer the **By performance** lens on top once family data exists (§03).
4. Wire the **shared action system** (§02) into both lenses simultaneously.
5. Replace every seed value and resolve every TODO in §04 before calling it done.
