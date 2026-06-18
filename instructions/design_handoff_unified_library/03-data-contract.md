# 03 · Data contract — what the UI reads

This is the **field-shape contract** between the Library UI and the backend.
Per the handoff scope: **this documents the shapes the UI reads, not how the
backend clusters.** TapeMatch / family logic lives in the backend; the UI only
consumes the result and **must degrade gracefully when it isn't there yet**
(see "No-families fallback" below — this is the part that lets you ship the
Library before clustering exists).

> All sample data is in `_source/perf-data.js` (performance lens) and
> `_source/library-data.js` (recording lens + history). Treat those as a
> **shape reference with realistic values**, not as production data.

---

## Entity 1 — Recording (the atomic unit)

One circulating source of a show, keyed by its LB catalog number. This is the
*only* truly required entity — the recording lens needs nothing else.

| Field | Type | Required | UI use |
|---|---|---|---|
| `lb` | string `"LB-456"` | ✅ | Row key, mono display, Copy LB# |
| `src` | enum: `Soundboard \| Audience \| FM/Pre-FM \| Master \| Mixed` | ✅ | Source badge (SBD/AUD/FM/MST/MTX) |
| `rating` | string `"A" "A−" "B+"` … | ✅ | Rating chip + "best source" ranking |
| `owned` | boolean | ✅ | Owned/unowned styling; gates owned-only actions |
| `lineage` | string | – | Detail panel provenance line |
| `status` | enum: `Public \| Private \| New \| Missing` | – | Row edge color + pill |
| `wish` | boolean | – | Wishlist state on unowned rows |
| **Owned-only file fields** | | | Present **only when `owned: true`** |
| `folder` | string | – | File card |
| `path` | string | – | Reveal on disk / Copy path |
| `size` | string `"812 MB"` | – | File card |
| `files` | number | – | File card |
| `format` | string `"FLAC 16/44.1"` | – | File card |
| `cds` | number | – | File card |
| `conf` | ISO date | – | "Checksums confirmed" date |
| `fp` | boolean | – | Fingerprinted indicator |

> **Owned-only fields must be null/absent when not owned** — don't ship
> placeholder file sizes for unowned rows. That's the classic "looked real in
> the demo, was fake in code" trap. The UI already branches on `owned`.

---

## Entity 2 — Performance / show (performance lens only)

A show = date + venue, carrying one or more recordings.

| Field | Type | Required | UI use |
|---|---|---|---|
| `id` | string | ✅ | Row key |
| `date` | ISO `"1980-04-19"` | ✅ | Sort key, year grouping |
| `disp` | string `"Apr 19, 1980"` | ✅ | Human date label |
| `dow` | string `"Sat"` | – | Weekday |
| `year` | number | ✅ | Year section grouping |
| `venue`, `city` | string | ✅ | Primary row label |
| `tour`, `leg` | string | – | Facet filters / context |
| `status` | enum (as above) | – | Row edge + pill |
| `tracks`, `length` | number / string | – | Show metadata |
| `setlist` | key | – | Setlist lookup (separate table) |
| `title` | string | – | "Released as …" (named bootlegs) |
| `recordings` | `Recording[]` | ✅ | The show's sources |
| `fams` | `{ [famId]: Family }` | – | **Optional** — clustering result; see below |

**Coverage rollup** (`PERF.rollup`) is **derived in the UI**, not stored:
`ownedCount` / `totalCount` over `recordings`, plus best owned rating. Don't ship
a stored coverage number — it would drift from the recordings array.

---

## Entity 3 — Family (TapeMatch cluster) — **optional, degradable**

A family groups recordings the backend believes are the same source tape. It is
**purely additive**: every recording stands alone without it.

`recordings[].fam` is a string id; `perf.fams[famId]` describes the cluster:

| Field | Type | UI use |
|---|---|---|
| `label` | string `"Rock Solid master"` | Family group header |
| `by` | enum: `lb \| ai \| ai+lb` | Provenance of the grouping (manual LB#, AI, or both) |
| `conf` | number 0–1 | Match-confidence chip (only shown when present) |
| `note` | string | Tooltip / sub-label explaining the cluster |

Recording-level hints the UI reads (all optional):
- `dup: true` — byte-identical re-upload; UI can de-emphasize / mark "duplicate"
- `upgrade: true` — a better source you don't own (upgrade opportunity)
- `xref` — cross-reference id to a named release

> **Backend can ship clustering incrementally.** Start by returning **no `fams`
> and no `fam` ids** → the UI shows the fallback (below). Add `by:"lb"` manual
> groups next, then `by:"ai"`/`by:"ai+lb"` with `conf`. The UI already renders
> all three and only shows confidence when `conf` is present.

---

## No-families fallback (ship-before-clustering path)  ← required

When family data is absent or the user turns grouping off, the performance lens
renders **flat, ungrouped LB# rows nested under each show** — no family headers,
no clustering, fully usable.

**Triggers (any one):**
1. Backend returns a performance with **no `fams`** and recordings with **no
   `fam`** → render flat automatically.
2. User toggles **"Group recordings into families"** off in Themes/options.
3. Partial data: some recordings have `fam`, others don't → ungrouped ones list
   flat beneath the families. (No recording is ever dropped.)

**Fallback rendering:** under an expanded show, list each recording as its own
row — `LB# · source badge · rating · owned state` — sorted by rating then LB#.
This is identical to the recording lens's row, just scoped to the show. The
"Show match confidence" control is hidden when there are no families to score.

> This is why building the **recording lens first** is recommended (§00): its
> flat row *is* the fallback row. The performance lens then adds grouping on top
> when `fams` arrives — it never depends on clustering to be usable.

---

## Entity 4 — Distribution history (`LBB_LIB.HISTORY[lb]`)

Feeds the **Share & seed** activity log. Keyed by LB#; **absent key = "not
shared yet"** (the UI shows the empty-state prompt, not a fake log).

```js
HISTORY["LB-16630"] = {
  torrents: [ { d: "2026-05-21", f: "LB-16630 ... .torrent", tag: "qBittorrent" }, … ],
  forum:    [ { d: "2024-08-02", f: "Re: 1966-05-17 Manchester", tag: "Posted" }, … ],
};
```

| Field | Type | UI use |
|---|---|---|
| `torrents[]` | `{ d, f, tag }` | Activity log (torrent rows); `tag ~ /qbt/i` ⇒ counts as "seeding" |
| `forum[]` | `{ d, f, tag }` | Activity log (forum rows); newest `d` ⇒ "last forum post" |
| `d` | ISO date | Mono date column, sort key (log is newest-first) |
| `f` | string | File name / thread title |
| `tag` | string | Status pill (`qBittorrent`, `Posted`, `Local`, …) |

The UI merges `torrents` + `forum` into one date-sorted log with an
all/torrents/forum filter. Provide real rows or omit the key — **do not ship a
placeholder log.**
