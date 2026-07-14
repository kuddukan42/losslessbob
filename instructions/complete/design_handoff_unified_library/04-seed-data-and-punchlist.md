# 04 · Seed-data inventory & interaction punchlist

> **The anti-gap doc.** Everything in the prototype that *looks* live but is
> illustrative is listed here, with the real source to wire it to. Everything
> that's *drawn but inert* is listed as a TODO with intended behavior + data
> needs. Work top-to-bottom; when every row is resolved, the demo and the code
> agree — which is the whole point of this handoff.

---

## Part A — Seed values to REPLACE (do not ship as literals)

These are realistic placeholders. Each is hardcoded in the prototype and **must
be bound to a real source** before shipping.

### A1 · Status footer (inherited from the app shell)

`_source/app-shell.jsx` → `StatusBar` hardcodes these. The footer is **shared
chrome**, not owned by the Library — but the Library tab displays it, so the
fake values surface here too. Bind in the shell (out of this screen's scope, but
flagged so it isn't missed):

| Shown | Literal | Bind to |
|---|---|---|
| DB | `LB-16630` | max LB# in master DB |
| Checksums | `704,624` | indexed-checksum count |
| Last import | `2026-05-21` | last import timestamp |
| Bootlegs | `1,380` | bootleg-catalog row count |
| "Synced · idle" | static | real sync state |

> This footer is the exact kind of value a prior handoff shipped as fake. Don't
> repeat it — either wire the shell's `StatusBar`, or have it accept props.

### A2 · Library status-footer extra (`statusExtra`) — **in scope**

`_source/libu-app.jsx` passes a hardcoded `statusExtra`:

| Lens | Literal | Bind to |
|---|---|---|
| By performance | `Shows covered: 5,104 / 5,988` | `covered` / `performances` totals (derive from data) |
| By recording | `Owned: 15,967 / 16,630` | owned-row count / master-DB total |

### A3 · Sidebar nav counts — **in scope**

`_source/libu-app.jsx` → `NAV`:

| Item | Literal | Bind to |
|---|---|---|
| Library badge | `16630` | master-DB total |
| Bootlegs badge | `1380` | bootleg count (out-of-scope screen, but the badge renders) |

### A4 · Dataset totals & facet tallies

`_source/perf-data.js`:

- `TOTALS = { performances: 5988, recordings: 16630, families: 9740, covered: 5104, gaps: 884 }` — **all illustrative.** Derive from real data or fetch from the backend; don't ship these numbers.
- `FACETS` — every count is a placeholder tally:
  - `decade` (60s…20s), `coverage` (Covered/Upgrade/Gap/Undocumented),
    `recordings` (Multiple/Single/SBD/AUD), `source` (SBD/AUD/FM/MST/MTX),
    `rating` (A…C).
  - **Facet counts must reflect the current filtered result set**, computed
    server-side or from the loaded rows — not static. A static count that
    doesn't move when you filter is a classic "looks real, isn't" tell.

### A5 · Sample rows & history

- `_source/perf-data.js` `PERFS[]` and `_source/library-data.js` rows are a
  **representative sample**, not the catalogue. Shapes are the contract (§03);
  values are throwaway.
- `LBB_LIB.HISTORY` torrent/forum entries are sample log rows. Real history per
  §03; **absent key = empty state**, never a fake log.

---

## Part B — Interaction punchlist (drawn but inert → TODO)

Each control below renders and looks active but has **no real handler** in the
prototype. Listed with intended behavior + data/integration needs. **None of
these should ship doing nothing** — wire it or hide it.

### B1 · Row + panel actions (the action registry)

All action ids from `_source/libu-actions.jsx` (§02) are currently inert — they
only close the menu. Wire each `id` to its handler:

| id(s) | Intended behavior | Needs |
|---|---|---|
| `open` | Open the LB# web page | LB# → URL template |
| `copyLb`, `copyPath` | Copy to clipboard + toast | clipboard API |
| `play` | Play (best owned) recording | player integration + resolved file path |
| `reveal` | Reveal folder in OS file manager | OS shell open + `path` |
| `qbt` | Add torrent/files to qBittorrent | qBittorrent integration (same as Collection's headline action) |
| `torrent` | Create / regenerate `.torrent` | torrent-create service; writes a `HISTORY.torrents` row |
| `forum` | Post / open forum composer | forum integration; writes a `HISTORY.forum` row |
| `m3u` | Export show as M3U playlist | track list + file paths |
| `attach`, `spectro`, `map` | Open the respective asset view scoped to this row | existing Attachments/Spectrograms/Map screens (already built) |
| `reconfirm`, `refp` | Re-run checksum / fingerprint jobs | verify/fingerprint services |
| `relocate` | Update stored file location | mount/path picker |
| `remove` | Remove from collection (confirm) | collection-write + undo |
| `wishlist`, `wishlistGaps`, `notify`, `sources` | Wishlist + source-discovery | wishlist store; "find sources" search |

> These are the **parity-critical** ones (§02). The torrent/forum/qBittorrent
> trio especially — they exist in today's Collection and must work here.

### B2 · Toolbar controls

| Control | Intended behavior | Needs |
|---|---|---|
| Search box | Filter rows live (debounced); empties to full list | search index over loaded rows |
| Sort control | Re-sort table (date / rating / coverage / LB#) | sort state |
| `⋯` overflow (Export / Columns / Save view) | Export current view; choose columns; persist a named view | export service; column prefs store; saved-views store |

### B3 · Bulk action bar (recording lens, multi-select)

The bar appears on checkbox-select and shows Create torrent · Add to qBittorrent
· Update location · Remove. **All inert.** Wire to the same handlers as B1, but
batched over the selection. (Parity: Collection's bulk actions must survive.)

### B4 · Facet rail

Clicking a facet currently does **not** filter (counts are static, A4). Intended:
toggle a filter, intersect across facet groups, and recompute counts. Until the
backend supports filtered counts, ship with counts hidden rather than static.

---

## Part C · Sign-off gate

Do not call the new tab done until:

- [ ] Every Part A value is bound to a real source (or explicitly deferred with a ticket)
- [ ] Every Part B control either works or is hidden — **nothing inert ships visible**
- [ ] The §02 parity checklist passes against the live Collection
- [ ] The §03 no-families fallback renders when `fams` is absent
- [ ] Themes: card style + palette persist and re-apply on boot (§01)
