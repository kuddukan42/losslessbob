# Handoff: TapeMatch triage-rail filter (add-on)

## What this is

An **additive change package** for one component of the TapeMatch curation screen: the
272px triage-queue rail (§2 of `design_handoff_tapematch_curation/README.md`). Nothing else
on that screen changes — not the date header, matrix, speed strip, verdict cards, dossier,
report or diff views. Read the main handoff first; this document only describes the delta.

**The problem.** The rail as designed lists the queue and four status chips. The real crawl
index is **2,075 dates** (the number is printed in the top bar). Four chips over two
thousand rows is not navigation — a curator who remembers "the Boston show, mid-seventies,
the one with the conflict" has no way to get there except scrolling. `Needs you` alone still
returns hundreds of rows.

**The move.** Three cheap layers on top of the existing rail, in this order of importance:

1. **One query field** that accepts everything a curator actually remembers — a city, a year,
   a decade, a partial date, a status word — in any combination, no operators to learn.
2. **A year brush**: a 64-bar histogram of the queue, drag-to-scope, with decade chips.
   Dates are the domain's primary key; the year is how this audience thinks.
3. **A windowed, year-grouped list** so the rail stays responsive at any queue size.

Everything else in the rail is preserved verbatim: row markup, row contents, status dots,
counts, chips, hover/selected treatments, the cursor-vs-open two-state model, `j`/`k`/`enter`,
and the 272/224px widths.

## Fidelity

**High fidelity** for layout, type and behavior; the values below are final-intent and all
come from existing tokens in `tm.css` — this add-on introduces **no new color, radius, or
type value**. The only genuinely new number is the fixed row height needed for windowing
(§4).

`tmf-data.js` is a **generated demo index** (a deterministic PRNG over a plausible touring
history). It exists so the prototype exercises 2,075 rows. Do not port it; the real list is
the queue query.

---

## 1. Where it sits

```
┌──────────────┬──────────────────────────────────
│ RAIL 272px   │  (unchanged)
│ ┌──────────┐ │
│ │ title    │ │  ← existing "TRIAGE QUEUE · n need you"
│ │ [search] │ │  ← NEW
│ │ chips    │ │  ← existing, unchanged
│ │ ▁▂▇▃ bars│ │  ← NEW year brush + decade chips
│ ├──────────┤ │
│ │ n of N   │ │  ← NEW result bar (sort / reset)
│ ├──────────┤ │
│ │ 1974   38│ │  ← NEW year group header
│ │ ░ row    │ │  ← existing row, unchanged markup
│ │ ░ row    │ │
│ ├──────────┤ │
│ │ / j k ⏎  │ │  ← existing footer, restated as keys
└──────────────┴──────────────────────────────────
```

Header block `.tmfHead` replaces `.tmRailHead`: `padding:10px 10px 9px;
border-bottom:1px solid var(--border); display:flex; flex-direction:column; gap:8px`.
It contains, in order: the existing title row, the search field, the existing
`.tmRailFilters` chips, the year brush. Padding drops 12 → 10px because the block now holds
four things; the chips themselves are untouched.

---

## 2. Query field ★

`.tmfSearch` — `width:100%; background:var(--surface2); border:1px solid var(--border);
border-radius:6px; color:var(--fg); font:500 11.5px var(--mono); padding:6px 26px 6px 22px`.
Focus: `border-color:var(--accent); background:var(--accent-soft)`. A `⌕` at 10px
`var(--fg3)` sits absolutely at `left:8px`; a `×` clear button (`.tmfClear`) appears at
`right:5px` only when non-empty. Placeholder: `date, city, 1974, 70s, conflict…` — the
placeholder **is** the documentation for the grammar, which is why it lists four different
token shapes rather than saying "Search".

**Mono, not sans.** Two thirds of what gets typed here is numeric (dates, years); tabular
mono keeps `1974-05-17` aligned with the rows it filters.

### Grammar

Tokens are whitespace-separated and **AND** together. Each token is classified by shape, in
this order (`parseQuery` in `tmf-rail.jsx`):

| Shape | Example | Meaning |
|---|---|---|
| status word, bare or `status:`-prefixed | `conflict`, `status:review` | exact status match |
| `19xx` / `20xx` | `1974` | that year |
| `19x0s` / `20x0s` | `70s` (→ `1970s` also accepted) | that decade |
| 2-digit, optional apostrophe | `'74`, `74` | year; `>30` → 19xx, else 20xx |
| `YYYY-M[-D]` | `1974-05`, `1974-5-17` | date prefix, month/day zero-padded on the way in |
| `M/D` | `5/17` | that month + day in **any** year |
| anything else | `boston`, `garden` | substring of `date + " " + location`, lowercased |

Multiple tokens of the same class are **OR**ed within the class and ANDed across classes:
`1974 1975 boston` = (1974 or 1975) and "boston". Decades expand to ten year values, which
is why years are a set rather than a range.

The two-digit rule (`74` → 1974) is the one guess in the grammar. It's worth it: curators
type `74-05-17` from memory of tape labels. The cutoff at 30 is arbitrary but safe for a
catalogue that starts in 1961.

**No results-list ranking.** Matching is boolean, and order stays chronological. A relevance
sort would fight the year grouping and destroy the curator's spatial memory of the queue.

---

## 3. Year brush ★

`.tmfBars` — `display:flex; align-items:flex-end; gap:1px; height:34px; cursor:ew-resize;
touch-action:none; border-bottom:1px solid var(--border)`. One `.tmfBar` per year in the
queue's full span (61 years for the demo index), `flex:1 1 0`.

Each bar is a **two-segment stack**, bottom-up: `.tmfBarRest` (`var(--fg3)`, or
`var(--border2)` when out of range) and `.tmfBarNeed` (`var(--warn-bar)`) on top. Heights:
`h = max(2, round(count/max * 32))`, needs-share `nh = round(need/count * h)`.

- **The warm cap is the whole point.** Total volume tells you where the tapes are; the amber
  segment tells you where the *work* is. A curator scanning the strip is looking for amber,
  not height.
- Bars outside the active range drop to `opacity:.42` rather than being hidden — the shape of
  the whole catalogue stays visible as context.
- `title` on each bar: `1974 · 40 dates · 9 need you`.

**Counts react to the query.** The histogram is computed from the *staged* set (status chips
+ query applied, year range **not** applied). So typing `boston` immediately redraws the
strip as "where Boston shows are", and the brush then scopes within that. Computing it from
the unfiltered queue would make the two controls independent and much less useful; computing
it from the final set would collapse it to the selection and make it useless.

**Interaction** — pointer events on the track, with `setPointerCapture`:
- `pointerdown` sets the anchor year and a 1-year range; `pointermove` extends it in either
  direction; `pointerup` ends. So click = one year, drag = a span. No handles to grab.
- Readout above the strip: `1974–1978` with an inline `×`, or a muted `all · drag to scope`.
- **Decade chips** (`.tmfDec`, 9.5px mono, `60s`…`20s`) below the strip set a decade in one
  click and toggle off. They exist because a 3.5px-wide bar is a poor pointer target for the
  most common case.

Accessibility: the brush is currently pointer-only. **Add keyboard access before shipping** —
make the strip a two-thumb `role="slider"` pair, or expose the same range through the
decade chips plus arrow keys. The query field already covers years textually, which is the
accessible fallback in the meantime.

---

## 4. List: grouping + windowing ★

**Year headers** (`.tmfYear`, 26px tall): `font:700 9.5px var(--mono); letter-spacing:.06em;
color:var(--fg3)`, the year, a per-year count in `.tmfYearN`, then a flexible 1px rule filling
the remaining width (`::after`). They are **not sticky** — with 61 possible groups a sticky
header spends most of its life covering a row, and the header pitch is short enough that the
year is never far above.

**Rows are unchanged.** Same `<button class="tmDateRow">`, same three children (status dot /
date + location / `recs→fams`), same hover, `.on` and `.cur` treatments from `tm.css`.

**Two additive rules**, both scoped inside `.tmfList`:

```css
.tmfList .tmDateRow { height: 46px }        /* was intrinsic (~46px) */
.tmfList .tmDateRow.cur { border-color: var(--border2) }
```

A **fixed row height is the enabling constraint** for windowing — 46px is the height the row
already had at its natural size, so nothing moves.

**Windowing** — `.tmfList` scrolls; inside it a `.tmfSpacer` of the full computed height holds
absolutely-positioned items (`.tmfAbs { position:absolute; left:0; right:0 }`) placed by `top`.

- Items are a flat array of `{year header}` and `{date row}` entries with a **prefix-offset
  table** built once per filter change: `O(n)` over ~2,100 items, negligible.
- The visible slice is found by binary search over that table, with **8 items of overscan**
  either side. Roughly 20 rows are in the DOM at any time regardless of queue size.
- Scroll position is read from a `scroll` listener plus a `ResizeObserver` on the list.

**Why not `content-visibility` or an off-the-shelf virtualizer:** the codebase almost
certainly has one — **use it**. This implementation is here to specify the *behavior*
(fixed pitch, grouped items, overscan, offset table) and to prove the rail stays smooth at
2,075 rows, not to be ported line for line. The one requirement any substitute must meet is
the next section.

**Cursor scrolling must use the offset table, not `scrollIntoView`** — same rule as the
existing rail (§2 of the main handoff), and now doubly true: with windowing the target row may
not be in the DOM at all. `tmf-rail.jsx` computes `top = offsets[itemIndex]` and adjusts
`list.scrollTop` directly, leaving a header's worth of margin (26px + 4px) above.

---

## 5. Result bar

`.tmfResult` — `padding:6px 12px; border-bottom:1px solid var(--border);
font:500 10px var(--mono); color:var(--fg3)`, between the header block and the list.

- Left: `**1,284** of 2,075 dates` — matched count bold in `var(--fg2)`, total dimmed.
  **Always visible, even unfiltered**, so the queue's true size is never a surprise.
- Right: a `reset` text button (shown only when any filter is active — clears query, range,
  and sets chips to `All`) and a sort toggle reading `newest ↓` / `oldest ↑`.

Default sort is **newest first**. Reverse sorting reverses the row order and therefore the
year groups too.

---

## 6. Keyboard

Additive to the existing model; nothing is taken away.

| Key | Behavior |
|---|---|
| `/` | Focus the query field (suppressed while already typing) |
| `j` / `k` / `↑` / `↓` | Move the cursor within the **filtered** list, clamped, no wrap — unchanged |
| `↑` / `↓` **while typing** | Move the cursor without leaving the field — type, then arrow down and hit enter |
| `enter` | Open the cursor's date. From inside the field it also blurs |
| `esc` (in field) | First press clears the query, second blurs the field |
| `esc` (elsewhere) | Unchanged — clears the pair selection / closes the dossier |

The window handler still bails on `meta`/`ctrl`/`alt` and on events targeting inputs — except
for the four keys above, which are explicitly handled while typing. `/` is only intercepted
when the target is *not* an input.

Footer (`.tmfFoot`) restates them as `<kbd>`s: `/ search · j k move · ⏎ open · esc clear`,
same kbd styling as the existing rail footer.

---

## 7. Empty state

Uses the existing `.tmRailEmpty` block: "No dates match." over a dimmed second line, "Try a
year, a city, or clear the filters." §10.3 of the main handoff defines the richer
filter-specific empty states (e.g. "No conflicts left.") — **those still apply**; this add-on
only supplies the generic no-match case. Wire the §10.3 copy in when the chip alone is the
reason for the emptiness.

---

## 8. State

All filter state moves out of `App` and into the rail component:

```
q      : string                       default ""       query text
chip   : "needs"|"conflict"|"all"|"curated"  default "needs"
range  : [startYear, endYear] | null  default null     year brush
asc    : boolean                      default false    sort direction
cursor : number                       default 0        index into the FILTERED rows
view   : { top, h }                   scroll position + viewport height
```

Derived, all memoized: `indexed` (rows + a precomputed lowercased haystack) → `staged`
(chip + query) → `counts` (histogram) → `rows` (+ range, + sort) → `items`/`offsets`
(grouping + windowing). Only `indexed` depends on the data prop; the rest recompute per
interaction and are cheap at this size.

**Production notes**
- `q`, `chip`, `range` and `sort` belong in the **URL** alongside `date` — "the 1974 conflicts"
  is exactly the kind of thing a curator sends to a colleague. The add-on keeps them local
  only because the prototype has no router.
- Filtering is client-side over the full index. At 2,075 rows with a ~20-char haystack per row
  that is well under a frame; at 10× that, move `staged` to the server and keep the histogram
  as an aggregate the queue endpoint returns.
- Precompute the haystack once (`date + " " + location`, lowercased) — not per keystroke.
- Debouncing is **not** needed at this size and was deliberately left out; the histogram
  redrawing on every keystroke is the feature.

---

## 9. Drop-in

Three new files, two edits, nothing removed from the design.

```diff
  <!-- TapeMatch Curation.html -->
+ <link rel="stylesheet" href="tmf.css">
+ <script src="tmf-data.js"></script>            <!-- real queue index -->
+ <script type="text/babel" src="tmf-rail.jsx"></script>

  // tm-app.jsx
- <Rail filter={filter} setFilter={setFilter} active={active} setActive={setActive}
-       narrow={narrowRail} cursor={cursor} setCursor={setCursor} listRef={listRef} />
+ <TMFRail dates={QUEUE} active={active} onActivate={(d) => setActive(d.date)}
+          narrow={narrowRail} />
```

The add-on owns filter state, cursor state and the `j`/`k` handler, so these come **out** of
`tm-app.jsx` with the old rail: the `filter`/`cursor`/`listRef` state, the cursor-reconcile
and cursor-scroll effects, the `FILTERS`/`match` helpers, and the key handler's `j`/`k`/`enter`
branches (keep its `esc` branch — that closes the dossier and diff, which the rail knows
nothing about). Everything else in the file is untouched.

**Props**

| Prop | Type | Notes |
|---|---|---|
| `dates` | `QueueItem[]` | `{ date, loc, recs, fams, status }` — the existing shape |
| `active` | `string` | open date, `YYYY-MM-DD` |
| `onActivate` | `(QueueItem) => void` | fires on click and on `enter` |
| `narrow` | `boolean` | from the existing `≤1380px` matchMedia — sets `.narrow` |

---

## 10. Files

| File | Contents |
|---|---|
| `TapeMatch Rail Filter (add-on).html` | Demo entry point — loads `tm.css` + `tmf.css`, then the add-on and its demo shell |
| `tmf-rail.jsx` | **The add-on.** `TMFRail`, `YearBrush`, `parseQuery`. This is the file to port |
| `tmf.css` | Add-on styles. Every selector is new (`tmf*`) except the two scoped row rules in §4 |
| `tmf-data.js` | Generated 2,075-date demo index — **reference only**, do not port |
| `tmf-demo.jsx` | Demo shell and the on-screen spec pane — demo chrome, does not ship |
| `tm.css`, `tm-data.js`, `tm-app.jsx` | Copies of the current screen files, for diffing against §9 |
| `screenshots/` | Four states, below |

Serve over HTTP (the `.jsx` files are fetched and transpiled in-browser); `file://` will not
work.

| File | State |
|---|---|
| `01-default-needs-you.png` | Load state — `Needs you`, no query, no range. Full histogram, 2,075-date total in the result bar |
| `02-query-74-boston.png` | `74 boston` — two token classes ANDed; note the histogram collapsed to the matching years |
| `03-decade-brush-70s-all.png` | Chip `All` + the `70s` decade chip — in-range bars at full opacity, out-of-range at 42% |
| `04-empty-result.png` | A query with no matches — the generic empty state |

---

## Open questions

1. **Saved views.** "My conflicts, 1966" is a query a curator will retype daily. A row of
   saved chips under the search field is the obvious next step — deliberately not designed
   here, because it needs to know whether views are per-user and where they persist.
2. **Venue in the haystack.** Rows show city only; the fixture's `venue` lives on the date
   record. If venue is available on the queue item, add it to the haystack (not to the row) —
   "garden" is a plausible search and a poor row label.
3. **Brush keyboard access** (§3) — needs a decision before this ships.
4. **Server-side filtering** threshold (§8) — a product call about how big the index gets.
