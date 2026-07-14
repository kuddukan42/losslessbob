# 02 · Action system & parity checklist

> **This is the doc that prevents silent functionality loss in the merge.**
> The old Collection screen had right-click row menus and a cluster of
> detail-panel quick actions (torrent history, forum posting, qBittorrent,
> spectrograms, map, reveal-on-disk). When two screens merge into one, those
> are exactly the things that quietly disappear. They don't here — every one
> is in the registry below and has a home in the new UI.

## The core idea: one vocabulary, two surfaces

There is a **single action registry per row type**. It is rendered in **two
places** that read the same array, so they can never drift:

1. the **right-click context menu** on a row, and
2. the **detail-panel action bar** (one primary action + Reveal + a `⋯ More`
   overflow that lists the full grouped vocabulary).

Source of truth: `_source/libu-actions.jsx`. It exports:

| Export | Purpose |
|---|---|
| `LBB_recordingActions(row)` | Returns the action array for a recording (LB#) row |
| `LBB_performanceActions(perf, rollup)` | Returns the action array for a show row |
| `LBB_useRowMenu()` | Hook → `{ openMenu(e, {title, actions}), menuNode }` for right-click |
| `LBB_ActionBar({actions})` | The detail-panel command row (primary + Reveal + More) |
| `LBB_ShareSeed({lb, hist})` | The unified torrent + forum distribution workflow block |
| `LBB_AssetStrip({assets})` | Attachments / spectrograms / map as state chips |

Each action is `{ id, label, icon, group, primary?, danger? }`. Groups render in
this order with these headers: `open` (no header), `listen`, `acquire`
("Acquire"), `share` ("Share & seed"), `assets` ("Assets"), `maintain`
("Maintain"). **`id` is the contract** — wire your real handler to the id; the
punchlist (§04) lists what each id must do and what data it needs.

### Recording (LB#) action registry

| id | Label | Group | Shown when |
|---|---|---|---|
| `open` | Open LB page | open | always |
| `copyLb` | Copy LB number | open | always |
| `play` | Play *(primary)* | listen | owned |
| `reveal` | Reveal on disk | listen | owned |
| `copyPath` | Copy disk path | listen | owned |
| `qbt` | Add to qBittorrent | share | owned |
| `torrent` | Create / regenerate torrent | share | owned |
| `forum` | Post to forum | share | owned |
| `attach` | Attachments | assets | owned |
| `spectro` | Spectrograms | assets | owned |
| `map` | Show on map | assets | owned |
| `reconfirm` | Re-confirm checksums | maintain | owned |
| `refp` | Re-fingerprint | maintain | owned |
| `relocate` | Update location… | maintain | owned |
| `remove` | Remove from collection *(danger)* | maintain | owned |
| `wishlist` | Add to / On wishlist *(primary if not yet)* | acquire | not owned |
| `sources` | Find sources | acquire | not owned |
| `notify` | Notify when available | acquire | not owned |

### Performance (show) action registry

| id | Label | Group | Shown when |
|---|---|---|---|
| `open` | Open LB page | open | always |
| `play` | Play best recording *(primary)* | listen | any recording owned |
| `reveal` | Reveal best on disk | listen | any recording owned |
| `m3u` | Export show as M3U | share | any recording owned |
| `qbt` | Add owned to qBittorrent | share | any recording owned |
| `torrent` | Create torrent… | share | any recording owned |
| `forum` | Post to forum | share | any recording owned |
| `wishlistGaps` | Wishlist missing sources | acquire | always |

> In the performance lens, the share/asset actions operate on the show's **best
> owned recording** (highest rating). The detail panel makes this explicit:
> "Distribution for best owned source · LB-#####".

## Right-click menu — implementation notes

- `LBB_useRowMenu()` gives a row an `onContextMenu` handler and a `menuNode` you
  render once near the screen root.
- The menu **portals to `<body>`** so it escapes the scaled `#frame` transform
  and clamps to the real viewport (flips up/left near edges).
- Closes on outside-click, Escape, window blur, and resize.
- **Primitive change required:** `TR` (the table-row primitive in `lbb-ui.jsx`)
  now forwards `onContextMenu`. If you reimplement rows, your row element must
  forward it too — that's the single most common way right-click "gets lost."
- Wire it on **both** lenses: pass `title` (e.g. `"LB-12345 · 1966-05-17"`) and
  the matching `actions` array.

## Redesigned detail panel — intent zones (replaces the old button soup)

The old panel stacked equal-weight ghost buttons and bolted a torrent/forum
toggle on with disconnected Regenerate/Post buttons. The new panel is zoned by
intent so the primary path is obvious and nothing is buried:

```
┌ Detail panel ────────────────────────────────┐
│ Title · LB# · rating · source badges          │
│                                                │
│ [▶ Play]  [Reveal on disk]            [⋯ More] │  ← ActionBar (1 primary + reveal + overflow)
│                                                │
│ SHARE & SEED                                   │  ← LBB_ShareSeed
│  ┌ status: "Seeding 2 torrents · last forum…"┐ │
│  [Add to qBittorrent] [Regenerate] [Post…]    │
│  ── unified activity log (torrents + forum) ── │  ← filter: all / torrents / forum
│                                                │
│ ASSETS                                         │  ← LBB_AssetStrip
│  [Attachments 3] [Spectrograms ready] [Map]    │  ← state-bearing chips, not buttons
│                                                │
│ SETLIST …                                      │
└────────────────────────────────────────────────┘
```

- **ActionBar** surfaces only the one primary + Reveal inline; everything else
  lives in `⋯ More` (which renders the identical grouped list as the right-click
  menu). No more wall of equal buttons.
- **ShareSeed** turns the old scattered torrent/forum controls into one coherent
  workflow: a status summary line, the primary distribution actions, and a
  **single date-sorted activity log** merging torrents + forum posts (filterable
  all / torrents / forum). Degrades to a "Not shared yet" prompt when there's no
  history. Reads `LBB_LIB.HISTORY[lb]` (see §03 for shape).
- **AssetStrip** shows attachments count, spectrogram readiness, and map
  availability as compact chips that carry state — not three identical buttons.

---

## ⛳ PARITY CHECKLIST — must survive the merge

Tick every one against the live Collection before sign-off. Each maps to a
registry id and/or panel zone above.

**Row right-click menu**
- [ ] Right-click any row opens the context menu (both lenses)
- [ ] Menu actions match the row's owned/unowned state
- [ ] Menu flips/clamps at viewport edges; closes on outside-click/Esc

**Detail panel — owned recording**
- [ ] Play, Reveal on disk, Copy disk path
- [ ] **Torrent history** visible (now in the unified activity log)
- [ ] **Forum-post history** visible (same log, filterable)
- [ ] **Create / regenerate torrent**
- [ ] **Post to forum**
- [ ] **Add to qBittorrent**
- [ ] Attachments · Spectrograms · Show on map
- [ ] Re-confirm checksums · Re-fingerprint · Update location · Remove

**Detail panel — performance (show)**
- [ ] Play / Reveal best owned source
- [ ] Export show as M3U
- [ ] Share & seed scoped to best owned source (qBittorrent / torrent / forum)
- [ ] Wishlist missing sources

**Bulk bar (multi-select)** — already present in the recording lens; verify it
carries Collection's bulk actions: Create torrent · Add to qBittorrent · Update
location · Remove. (Documented as TODO handlers in §04.)

> If any box can't be ticked, it's a regression from Collection — fix before
> shipping the new tab, not after.
