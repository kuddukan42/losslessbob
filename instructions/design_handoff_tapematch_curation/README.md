# Handoff: TapeMatch Curation Screen

## Overview

TapeMatch is the recording-comparison engine inside LosslessBob. For a given concert date it takes every known recording (each identified by an `LB-#####` number), measures whether pairs of recordings come from the same original tape, and groups them into **families** (a family = one underlying tape, in any number of transfers/generations).

The algorithm is confident most of the time and wrong some of the time. **This screen is the human review layer.** A curator works a queue of dates, and for the date they're on they can see:

1. Every pairwise similarity score at once (the matrix)
2. Why any given score looks the way it does (speed/lag strip)
3. The written analysis verdict for the date
4. All evidence for one selected pair, against its thresholds (the dossier side panel), where they record a human judgment

The screen exists for the disagreement case: LosslessBob's own page text may claim two recordings are the same source while TapeMatch found no acoustic link (or vice versa). Those conflicts are what put a date in the queue, and resolving them is the job to be done.

## About the Design Files

The files in this bundle are **design references created in HTML** — prototypes showing the intended look and behavior. They are **not production code to copy directly**.

The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, SwiftUI, native, whatever the app uses) using its established component library, styling system, state patterns, and data layer. If no environment exists yet, choose the most appropriate framework for the project and implement there.

Specifically:
- The HTML prototype uses React 18 UMD + in-browser Babel and a single hand-written stylesheet. Do **not** carry that setup over. Use the codebase's build, its component primitives (Button, Pill/Badge, Sheet/Drawer), and its token system.
- `tm-data.js` is **fixture data with a deterministic hash fallback** for pairs that have no hand-authored values. Real implementations read pairs from the backing store (`observations.db`, see State & Data). Keep the file only as a source of shape and realistic values.
- CSS class names (`tmMatrix`, `tmDossier`, …) are prototype-local. Rename to match codebase conventions.

## Fidelity

**High fidelity.** Colors, typography, spacing, density, interaction states, and copy are all final-intent. Recreate the UI closely — this is a dense professional tool where density and alignment carry meaning (the matrix is read as a heatmap; the evidence bars are read against threshold marks). Every exact value is given below.

Two things are deliberately *not* final: the data-fetching layer, and the persistence of human judgments (prototype queues them in memory).

---

## Screen: TapeMatch Curation

**Route intent:** `/library/tapematch/curation` with the active date as a param, e.g. `?date=2001-11-19`.

### Top-level layout

```
┌───────────────────────────────────────────────────────────────────────────┐
│ TOP BAR  (fixed height ~41px, flex:0 0 auto)                              │
├──────────────┬────────────────────────────────────────────────────────────┤
│              │  DATE HEADER  (flex:0 0 auto, wraps)                       │
│  TRIAGE      ├────────────────────────────────┬───────────────────────────┤
│  QUEUE RAIL  │  WORK COLUMN (scrolls)         │  PAIR DOSSIER             │
│  272px fixed │   · Similarity matrix          │  350px fixed              │
│  (224px      │   · Speed & lag                │  (becomes an overlay      │
│   ≤1380px)   │   · Analysis verdict           │   drawer ≤1520px)         │
│              │                                │                           │
└──────────────┴────────────────────────────────┴───────────────────────────┘
```

- Root: `height:100vh; display:flex; flex-direction:column; min-height:0`
- Body row: `flex:1; display:flex; min-height:0`
- Main: `flex:1; min-width:0; display:flex; flex-direction:column; min-height:0; overflow-y:auto; position:relative`
- Work grid: `display:grid; grid-template-columns: minmax(0,1fr) 350px; flex:1; min-height:0`
  - At the drawer breakpoint this collapses to `grid-template-columns: minmax(0,1fr)` and the dossier renders as a fixed overlay.

Every flex/grid ancestor carries `min-height:0` / `min-width:0` — without them the scroll containers and the matrix's `minmax(0,1fr)` columns blow out. This is load-bearing.

---

### 1. Top bar

`display:flex; align-items:center; gap:14px; padding:10px 18px; border-bottom:1px solid #232b3a; background:#131822`

| Element | Spec | Content |
|---|---|---|
| Breadcrumb | 12.5px, `#9aa5b5`; separators `/` in `#5f6b7d`; last segment `#e6e9f0` weight 700 | `LosslessBob / Library / **TapeMatch**` |
| Subtitle | 11.5px, `#5f6b7d` | `Curation — review the algorithm's family calls, pair by pair` |
| Right cluster | `margin-left:auto; display:flex; align-items:center; gap:10px` | — |
| Crawl status | 11px mono, `#5f6b7d`, preceded by a 7px green dot (`#39a360`) | `crawl idle · 2,226 runs · 2,075 dates` |
| Queued-judgments pill | `pill sm info`, only when count > 0 | `3 judgments queued` (singular/plural) |

Real implementation: crawl status should be live (idle / running / failed) with the dot tone following it — green `#39a360` idle, amber `#b58a3a` running, red `#c25a48` failed.

---

### 2. Triage queue rail

`flex: 0 0 272px` (→ `224px` at ≤1380px), `background:#131822`, `border-right:1px solid #232b3a`, column flex, `min-height:0`.

**Header** — `padding:12px 12px 10px; border-bottom:1px solid #232b3a`
- Title: 11px, weight 700, `letter-spacing:.08em`, `text-transform:uppercase`, `#5f6b7d` — "TRIAGE QUEUE"
- Inline count: 10.5px, `#d4a35a` (warn), no letter-spacing, not uppercased — `7 need you`
- Filter chips: `display:flex; gap:5px; margin-top:9px; flex-wrap:wrap`
  - Chips: `background:#1a2130; border:1px solid #232b3a; color:#9aa5b5; border-radius:999px; padding:3px 10px; font:600 11px Inter`
  - Active chip: `background:#1a2740; border-color:#5b8df2; color:#5b8df2`
  - Options in order: **Needs you** (default), **Conflicts**, **All**, **Done**
  - Filter predicates: `needs` → status is `conflict` or `review`; `conflict` → status `conflict`; `all` → everything; `curated` → status `curated`

**List** — `flex:1; overflow-y:auto; padding:6px`

Each row is a `<button>` (keyboard reachable), `width:100%`, `display:flex; align-items:center; gap:9px; padding:8px 9px; border-radius:6px`, transparent bg + `1px solid transparent` border, `text-align:left`.
- Hover: `background:#1a2130`
- Selected: `background:#1a2740; border-color:#5b8df2`, and the date text turns `#5b8df2`
- Contents, left → right:
  1. Status dot — 7px circle, `flex:0 0 7px`, color from status tone bar
  2. Main column (`flex:1; min-width:0; column flex; gap:1px`): date 11.5px/600 **mono**; location 11.5px→`10.5px` `#5f6b7d` with `white-space:nowrap; overflow:hidden; text-overflow:ellipsis`
  3. Counts, 11px mono `#5f6b7d`: `{recordings}→{families}`, arrow dimmed `#5f6b7d`, families in `#9aa5b5` weight 700

Empty state: `padding:20px; text-align:center; font-size:11.5px; color:#5f6b7d` — "Nothing here."

**Footer** — `padding:8px 12px; border-top:1px solid #232b3a; font-size:10.5px; mono; color:#5f6b7d` — `j / k to move · enter to open · esc to close`, with each key in a `<kbd>`: `font:600 10px mono; color:#9aa5b5; background:#1a2130; border:1px solid #33405a; border-radius:3px; padding:0 3px`.

**Keyboard model** (implemented — see `tm-app.jsx`, and `screenshots/24-detail-rail-keyboard-cursor.png`)

There are **two** distinct row states, and keeping them separate is the whole point of the interaction: the **cursor** (where the keyboard is) and the **open date** (what the workspace shows). A curator can run down the queue with `j` reading statuses and counts without tearing down and refetching the workspace on every step.

| Key | Behavior |
|---|---|
| `j` / `↓` | Move cursor down one row in the **filtered** list, clamped at the end (no wrap — wrapping in a triage queue loses your place) |
| `k` / `↑` | Move cursor up one row, clamped at 0 |
| `enter` | Open the cursor's date |
| `esc` | Clear the pair selection (closes the dossier drawer). No-op when nothing is selected |

- **Cursor styling** — `.tmDateRow.cur`: `box-shadow: inset 2px 0 0 #9aa5b5` plus `border-color:#33405a`. When the cursor is also the open row (`.cur.on`) the inset bar switches to the accent `#5b8df2` so it reads as one state, not two competing ones. A 2px inset bar was chosen over an outline because the selected row already owns a border.
- Handler is on `window` and **bails on `meta`/`ctrl`/`alt`**, and on any event whose target is an input, textarea, select, or `contenteditable` — so browser shortcuts and future filter/search fields keep working. `preventDefault()` only on keys actually handled.
- **Cursor reconciliation:** whenever the filter or the open date changes, the cursor snaps to the open date's row if it's in the filtered list, otherwise it clamps into range. It deliberately does *not* re-snap when only the cursor moves.
- **Keeping the cursor visible:** the rail list's `scrollTop` is adjusted manually with a 6px margin (`row.offsetTop - box.offsetTop` against `box.scrollTop`/`clientHeight`). Do **not** use `scrollIntoView` — it scrolls ancestor containers too and knocks the whole app layout around.
- Rows remain real `<button>`s, so tab focus and click still work independently; clicking a row also moves the cursor there, keeping the two models in sync.

**Status vocabulary** (drives dot color + pill tone everywhere):

| status | label | tone | bar color | fg color | bg color |
|---|---|---|---|---|---|
| `conflict` | conflict | bad | `#c25a48` | `#e08070` | `#2b1b18` |
| `review` | review | warn | `#b58a3a` | `#d4a35a` | `#2a2416` |
| `clean` | clean | ok | `#39a360` | `#5db679` | `#16241b` |
| `curated` | curated | mute | `#4a5568` | `#8b94a3` | `#181e29` |

---

### 3. Date header

`display:flex; gap:18px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; padding:16px 22px 14px` (→ `14px 16px 12px` at ≤1380px), `border-bottom:1px solid #232b3a`.

**Left block**
- Row 1 (`display:flex; align-items:baseline; gap:10px; flex-wrap:wrap`):
  - Date — 19px weight 700 **mono** — `2001-11-19`
  - Venue + city — 13px `#9aa5b5` — `Madison Square Garden · New York, NY`
  - Run id — `pill sm mute mono` — `run 20260602_211540`
- Row 2 (`margin-top:7px; display:flex; align-items:center; gap:9px; flex-wrap:wrap`):
  - Status pill in the date's tone — `needs review`
  - Verdict summary — 12px `#9aa5b5` — `5 families from 10 recordings — 1 conflict with LB commentary`
  - Provenance — 10.5px mono `#5f6b7d` — `claude-sonnet-4-6 · 2026-06-03`

**Right block** — `display:flex; flex-direction:column; align-items:flex-end; gap:9px`
- Family chips (`display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end`), one per family:
  - `background:#1a2130; border:1px solid #232b3a; border-radius:999px; padding:2px 8px; font-size:10.5px; weight 600; color:#9aa5b5; gap:5px`
  - Contents: 8px family swatch (`border-radius:2px` — square-ish, distinct from the round status dots), family label `F1`, then member short-ids in 9.5px mono `#5f6b7d` weight 500, space-separated (`11201 11458 13022`)
- Actions (`display:flex; gap:8px`):
  - `Open report.md` — ghost button (transparent bg, `#9aa5b5` text, `1px solid #33405a`). Opens the report overlay — see §11.
  - `Accept families` — primary (`background:#5b8df2; color:#0b1020`), **disabled until at least one pair judgment exists**; label gains a count suffix once judgments exist: `Accept families · 2 judged`

Buttons generally: `border-radius:6px; padding:6px 12px; font:600 12px Inter`. Disabled: `opacity:.45; cursor:default`.

---

### 4. Section wrapper (used by all three work-column blocks)

`margin-top:18px`. Header row: `display:flex; align-items:baseline; gap:10px; margin-bottom:9px; flex-wrap:wrap`.
- Title: 11px/700, `letter-spacing:.08em`, uppercase, `#5f6b7d`
- Hint: 11px `#5f6b7d`

Work column padding: `6px 22px 26px` (→ `6px 16px 22px` at ≤1380px). All three blocks are capped at `max-width:760px`.

Section titles + hints, verbatim:
1. **Similarity matrix** — *family-ordered · % is the banded corr+embedding blend · click a cell for the dossier*
2. **Speed & lag** — *why a pair's correlation looks the way it does*
3. **Analysis verdict** — *parsed from analysis.md — the human/AI review layer*

---

### 5. The similarity matrix ★

The centerpiece. An N×N grid of pairwise similarity percentages, rendered as a colored heatmap, ordered so family members sit adjacent.

**Grid**
- `display:grid; gap:2px; grid-template-columns: 52px repeat(N, minmax(0,1fr))`
- Row 1 is column headers, preceded by an empty 52px corner cell.
- Column header (`tmMxHead`): column flex, `align-items:center; justify-content:flex-end; gap:2px; padding-bottom:3px; font:600 10px mono; color:#9aa5b5; min-width:0`. Contains the 8px family swatch above the short id (`11201`). `title` attr = full `LB-11201`.
- Row header (`tmMxRowHead`): `display:flex; align-items:center; justify-content:flex-end; gap:5px; padding-right:5px`, same type. Short id then swatch (mirrored order vs. the column header, so both point inward at the grid).

**Cells** — `<button>`, `aspect-ratio:1`, `min-width:0`, `border:1px solid #232b3a`, `border-radius:4px`, `font: 500 clamp(9px,1vw,11.5px) mono`, centered, `padding:0`, `transition: opacity .12s`.

Cell coloring — three regimes, all computed via `color-mix(in oklab, …)` against `--surface` (`#131822`) so cells sit in the same value family as the chrome:

| Case | Background |
|---|---|
| Same family (`a.fam === b.fam`) | `color-mix(in oklab, {familyColor} {30 + sim*0.55}% , #131822)` — i.e. 30% at sim 0 → 85% at sim 100. Text `#e6e9f0`, weight **700**. |
| Different family | `t = (sim/100)^0.8 * 72`; `color-mix(in oklab, #5b8df2 {t}%, #131822)`. Text `#5f6b7d`, weight 500 — but `#e6e9f0` once `sim ≥ 45` (the "check this" band needs to be readable). |
| Not comparable (`sim == null`) | `repeating-linear-gradient(45deg, #1a2130, #1a2130 4px, #131822 4px, #131822 8px)` — diagonal hatch. Cell text is `n/c` at `0.85em` in `#5f6b7d`. |
| Diagonal (i === j) | `background:#1a2130; border-color:#232b3a; cursor:default`, empty, not a button. |

The `^0.8` gamma on the non-family ramp is intentional — it lifts mid-range values so a 40–60% "worth checking" pair doesn't read as background noise.

**Conflict marker** — when the pair has a conflict with LB commentary, an absolutely-positioned 7px dot at `top:2px; right:2px`, `background:#c25a48`, `border:1px solid #0c1017` (the page bg, so it reads as a cut-out against any cell color).

**Selection + focus behavior**
- Clicking a cell selects that pair; clicking the selected cell deselects.
- Selected cell: `border: 2px solid #e6e9f0; z-index:1`.
- Selection is symmetric — cell (i,j) and (j,i) both show selected for the same pair.
- **Cross-dimming:** when any pair is selected, every cell *not* in the selected pair's row or column drops to `opacity:0.3` (with the 120ms transition). Cells sharing a row/column with either selected recording stay at full opacity. This turns the matrix into a "here's everything else we know about these two recordings" view.
- Tooltip (`title`): `LB-11201 × LB-11340 — 22%`, or `… — not comparable`.

**Legend** — below the grid, `display:flex; align-items:center; gap:7px; flex-wrap:wrap; margin-top:10px; font-size:10.5px; color:#5f6b7d`. Swatches are 13×11px, `border-radius:3px`, `1px solid #232b3a`, `margin-left:8px` (first has none).

1. accent @12% → `unrelated 0–40`
2. accent @55% → `check 40–85`
3. family-1 color → `same family 85–100 · tinted by family`
4. hatch → `n/c not comparable`
5. red dot → `LB-page conflict`

**Accessibility note for implementation:** color alone carries the family grouping. The number in every cell is the fallback, which is why cells are never blank. Give each cell an `aria-label` of the form `LB-11201 by LB-11340, 22 percent similar, different family` and make the grid arrow-key navigable (roving tabindex) rather than 90 sequential tab stops.

**Scaling beyond 10 recordings:** the fixture date has 10, so cells land around 60px. Dates with 30+ recordings exist. Decide a strategy: cap cell size with a min (e.g. `minmax(22px,1fr)`) and let the block scroll horizontally, drop the in-cell number below ~28px (tooltip only), and keep headers sticky. Do not let cells shrink below 14px.

---

### 6. Speed & lag strip ★

A one-dimensional plot of every recording's playback-speed offset relative to the reference recording, measured in **ppm** (parts per million). It answers "why is this correlation bad?" — two transfers of the same tape running at different speeds won't correlate until aligned, and an extreme offset (a PAL/NTSC transfer error) means correlation is not measurable at all.

**Container** — `border:1px solid #232b3a; border-radius:8px; background:#131822; padding:12px 14px 10px; max-width:760px`

**Scale** — ppm values span roughly −1,512 to +12,480, so a linear axis would pile nine dots on top of each other. Uses a **signed square-root scale**: `sym(p) = sign(p) * sqrt(|p|)`. Then `x% = 4 + ((sym(p) − min) / (max − min)) * 92` — i.e. the plot inhabits 4%–96% of the width, leaving room for the outermost labels. The axis note says so explicitly: `ppm vs reference · √ scale`.

**Ticks** at `-1500`, `0`, `12480`:
- `.tmTick` — `position:absolute; top:0; bottom:16px`, positioned by `left:{x}%`
- Line: `position:absolute; top:0; bottom:0; width:1px; background:#33405a; left:0`
- Label: `position:absolute; bottom:-15px; left:0; transform:translateX(-50%); font:500 9.5px mono; color:#5f6b7d; white-space:nowrap`. Value 0 renders as `ref`; others as `−1,500` / `+12,480` (note: true minus sign U+2212, thousands separators).

**Dots** — each recording is a `<button>`, `position:absolute; transform:translateX(-50%)`, column flex, `align-items:center; gap:1px`, no bg/border, `z-index:1`.
- Glyph: 18×18px circle, `background: {familyColor}`, centered 9px glyph in `#0b1020` weight 700
- Label below: `font:600 9px mono; color:#5f6b7d` — short id
- Selected (recording is in the current pair): label → `#e6e9f0`, glyph gains `outline:2px solid #e6e9f0`
- Tooltip: `LB-11340 · -1,512 ppm · constant-speed-offset · confidence 8.8`

**Glyph vocabulary (lag-curve kind → glyph):**

| kind | glyph | meaning |
|---|---|---|
| `reference` | ◆ | the date's reference recording, 0 ppm by definition |
| `aligned` | ● | lag curve flat, offset near zero |
| `constant-speed-offset` | ● | flat lag curve at a nonzero slope — clean, correctable |
| `staircase` | ▤ | discontinuous lag steps — re-tracked CDR indices |
| `splice` | ✂ | lag jumps at one point — tape flip / patched section |
| `speed-unknown` | ? | ratio confidence below the 6.0 minimum; correlation not comparable |

**Collision avoidance (lane packing)** — labels are ~4.8% wide, and clustered recordings would overlap. Greedy algorithm, in `REC` order:

```
for each recording:
  x = X(ppm)
  lane = 0
  while any already-placed dot has the same lane and |placedX − x| < 4.8:
    lane++
  place at lane
```

Dot vertical position: `top: lane * 34 + 4`. Lane container height: `(maxLane + 1) * 34 + 22` (the trailing 22px is the tick-label gutter). This means the strip grows taller as needed and never clips — reproduce this rather than hardcoding a height.

**Interaction:** clicking a dot mutates the pair selection — the clicked recording becomes one half of the selected pair, keeping the other half if it isn't the same recording (prototype logic: if the clicked index is already `sel[0]`, deselect; otherwise select `[clicked, previous sel[0] or (clicked+1) % N]`). This is functional but blunt. **Recommended production behavior:** click a dot to select the recording (highlighting its whole matrix row/column); click a second dot to form a pair and open its dossier. Confirm with design before shipping either.

**Legend** — `display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; font-size:10px; color:#5f6b7d`:
`◆ reference` · `● aligned / constant offset` · `▤ staircase (re-tracking)` · `✂ splice` · `? speed-unknown → fingerprint path only` (this one in warn `#d4a35a`) · then right-aligned (`margin-left:auto`, mono) `ppm vs reference · √ scale`.

---

### 7. Analysis verdict cards

Notes parsed out of the run's `analysis.md`. `display:flex; flex-direction:column; gap:7px; max-width:760px`.

Each card: `display:flex; gap:10px; padding:10px 12px; border-radius:7px; background:#131822; border:1px solid #232b3a`
- Left tone bar: `width:3px; flex:0 0 3px; border-radius:2px`, colored by the note's tone bar color
- Head: 12px weight 600 — a mono reference (`LB-11201 × LB-11340`, 11px), an em-dash, then the headline in the tone's **fg** color
- Body: 11.5px `#9aa5b5`, `line-height:1.5; margin-top:3px; text-wrap:pretty`

The four fixture notes (tones: bad, info, warn, info) are in `tm-data.js` → `NOTES`, and their copy is worth reading — it establishes the voice for this whole surface: plainspoken, numeric, states the threshold, states the recommendation. Example headline + body:

> **LB-11201 × LB-11340 — Conflict — LB page claims same source, algorithm disagrees**
> LB-11340's page says "probably the same recording as LB-11201." Residual correlation is 0.041 with 12% windowed coverage — no acoustic evidence of a shared tape. DFC vs FOB mic placement would explain the LB confusion. Recommend human judgment; if confirmed different, set `lb_wrong`.

### 7.1 Three heading shapes (B1) — `### <ref> — <headline>` is only one of them

21% of real `###` headings are not ref-plus-headline. Full reasoning in
`DESIGN_ANSWERS_B.md`; the rule, matched on the text left of the first ` — ` (or the whole
heading when there is no dash):

| left side | subject | shape |
|---|---|---|
| `LB-#####`, one or several joined by `/ → × vs , + and`, optional `(Family n)` tail | ref | card with ref chip (A7 — quoted verbatim) |
| `Family n` | family | card with a **family chip** (swatch + label; click selects the family's members) |
| anything else | none | **statement block** — dashed border, uppercase key, no chip, no tone bar |

- **No headline** (`### LB-11958 → LB-10780`): the chip stays, the headline row collapses, no
  em-dash is rendered. Nothing is promoted into the empty slot — not the ref, not the body's
  first line.
- **The body carries structure instead.** `label: value` lines render as a 104px uppercase
  key + value row (`.tmNoteKv`); a value opening with a quote takes the dossier's quote
  treatment; `- ` lines stay a list; everything else is prose. This is what makes a stack of
  eleven identically-shaped cards scannable.
- **Statement blocks keep document order** and their key is tone-tinted (`COVERAGE GAP` warn,
  `AUDIT TABLE` mute). Same block as A6's `ALGORITHM NOTE`.
- **Tone:** headlined cards key on the headline; headline-less cards key on the body. In both
  cases **quoted commentary is stripped before matching** — scraped LB text carries words like
  `DISAGREES` out of tables it was swept up from, and it must not set a card's severity.

Tone table (B2), ordered, first match wins: `MISS` → bad ·
`contradicted|contradicts|disagrees|conflicts with` → **bad** · `INCOMPLETE` → warn ·
`speed offset` → warn · `LOW CONFIDENCE` → warn ·
`mismatch|unreliable|uncorroborated|coincidence|inflated|needs review` → warn ·
`coverage gap|not found on disk|no tapematch comparison` → warn · else info.

The date header's `## Verdict:` line clamps to 2 lines past ~160 characters with an inline
`more` / `less` (B3) — the corpus tail reaches 316 characters and the header must not change
height under the cursor.

---

### 8. Pair dossier side panel ★

The right-hand panel. Everything TapeMatch measured for one pair, each signal shown against the threshold it's judged by, ending in the curator's judgment control.

**Container** — `border-left:1px solid #232b3a; background:#131822; padding:16px; overflow-y:auto; min-height:0`

**Drawer mode** (viewport ≤1520px): the work grid goes single-column and the dossier becomes `position:fixed; top:0; right:0; bottom:0; width:min(380px, 92vw); z-index:30; box-shadow:-18px 0 40px rgba(0,0,0,.45); border-left:1px solid #33405a`, over a scrim `position:fixed; inset:0; background:rgba(5,8,14,.5); z-index:25`. Clicking the scrim clears the selection. A close `✕` button (`#5f6b7d`, 14px, `padding:4px`) appears in the header only in drawer mode.

> Production: add a slide-in transition (`transform: translateX(100%) → 0`, 180ms `cubic-bezier(.2,.8,.25,1)`), focus-trap the drawer, restore focus to the originating cell on close, and close on `esc`.

**Empty state** — when nothing is selected. Container gets `display:flex; align-items:center; justify-content:center`; content `text-align:center; max-width:260px`:
- Icon `⊞` at 26px `#5f6b7d`
- Head 13.5px/700 `margin-top:8px` — "Select a pair"
- Body 11.5px `#5f6b7d`, `line-height:1.5; margin-top:5px` — "Click any matrix cell to open the evidence dossier — every signal TapeMatch measured for that pair, against its threshold."

**Populated content, top to bottom:**

**a. Header** — `display:flex; align-items:center; justify-content:space-between; gap:8px`. Pair labels: each is `font:700 13px mono` with its 8px family swatch, separated by a `×` in `#5f6b7d`. Wraps (`flex-wrap:wrap`).

**b. Verdict block** — `margin-top:12px; padding:10px 12px; border-radius:7px; background:#1a2130; border:1px solid #232b3a`, `display:flex; align-items:center; justify-content:space-between; gap:10px`
- Left: the similarity number at `font:800 24px mono; line-height:1` (or `n/c`), then a caption block, 9.5px `#5f6b7d`, `margin-top:3px; max-width:170px`:
  - normal — `similarity · banded blend of corr + embedding`
  - n/c — `similarity — speed ratio unconfident, correlation not comparable`
- Right: verdict pill, one of:
  - same family, primary link → `same family`, **ok** tone
  - same family, secondary link → `same family · secondary link`, **warn** tone
  - not comparable → `not comparable`, **mute** tone
  - otherwise → `different family`, **info** tone

**c. Conflict callout** — only when the pair conflicts. `margin-top:10px; padding:9px 11px; border-radius:7px; background:#2b1b18; border:1px solid color-mix(in oklab, #c25a48 50%, transparent); font-size:11.5px; color:#e08070; line-height:1.45`. Copy: "**Conflict.** LB page says same source; TapeMatch found no acoustic link. This pair is why this date is in the queue."

**d. Evidence bars** — under two sub-headings, `Primary evidence` and `Secondary evidence`. Sub-heading style (`tmDossSec`): `font-size:10px; weight 700; letter-spacing:.08em; uppercase; color:#5f6b7d; margin:16px 0 7px`.

Each bar (`margin-bottom:11px`):
- Top row: `display:flex; justify-content:space-between; align-items:baseline` — label 11.5px/600 `#9aa5b5`; value `font:600 11.5px mono`, formatted to **3 decimals** (`0.041`), or `n/c` when null
- Track: `position:relative; height:9px; border-radius:999px; background:#1a2130; border:1px solid #232b3a; margin-top:4px; overflow:visible`
  - Fill: absolute, left-anchored, `border-radius:999px; background:#5b8df2`, width `= value/max * 100%`
  - Threshold mark: `position:absolute; top:-3px; bottom:-3px; width:2px; background:#b58a3a; border-radius:1px`, at `left: threshold/max * 100%` — deliberately overhangs the track so it reads as a gate, not a fill boundary
  - Band (used only by fingerprint dice): `position:absolute; top:0; bottom:0`, spanning `[0.15, 0.50]`, filled with `repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,255,255,.09) 3px, rgba(255,255,255,.09) 6px)`
- Demoted variant (fingerprint dice): whole bar `opacity:.72`, fill color becomes `#4a5568` (mute) instead of accent — visually says "this signal does not group recordings"
- Note: 10px `#5f6b7d`, `margin-top:4px; line-height:1.4; text-wrap:pretty`

The four bars, in order, all `max = 1`:

| # | Label | Threshold / band | Note (conditional) |
|---|---|---|---|
| 1 | Residual correlation | thresh **0.45** | null → "not measured — speed-unknown source"; ≥0.45 → "≥ 0.45 cluster threshold — merges on primary evidence"; below + secondary link → "below threshold — that's why the secondary path ran"; else → "below the 0.45 cluster threshold" |
| 2 | Windowed coverage | thresh **0.60** | "fraction of dense 60 s windows correlating — drives secondary clustering" |
| 3 | Quiet-segment hiss corr | none | "tape hiss survives EQ/NR applied to the music" |
| 4 | Fingerprint dice | band **0.15–0.50**, demoted | "confirmatory only — never groups. Shaded band = 0.15–0.50 coincidence range for two tapers at the same show." |

That conditional note on bar 1 is the pedagogical heart of the panel — it tells the curator *why* the algorithm did what it did. Keep it.

**e. "LB page says"** — sub-heading, then `display:flex; flex-direction:column; gap:7px; align-items:flex-start`
- A `pill sm`: **bad** `disagrees` when conflict; **ok** `agrees · same source` when LB claims a relation; **mute** `no claim` otherwise
- Quote block: 11.5px `#9aa5b5`, `line-height:1.5; padding:8px 11px; border-left:2px solid #33405a; background:#1a2130; border-radius:0 6px 6px 0; text-wrap:pretty`
- When there is no claim (or the fixture stores `"—"`), render only a muted quote — `color:#5f6b7d; border-left-color:#232b3a` — reading "No relation claim between these LB numbers on either page."

**f. Judgment control** — sub-heading `Your judgment`, then a 2×2 grid: `display:grid; grid-template-columns:1fr 1fr; gap:6px`

Buttons: `padding:8px 6px; border-radius:6px; font:600 11.5px Inter; background:#1a2130; border:1px solid #33405a; color:#9aa5b5`. When selected, the button takes its tone's bg / bar-as-border / fg:

| key | label | tone | selected bg / border / text |
|---|---|---|---|
| `confirmed_same` | Same source | ok | `#16241b` / `#39a360` / `#5db679` |
| `confirmed_different` | Different | info | `#16222e` / `#5891cf` / `#7eb4e8` |
| `uncertain` | Uncertain | warn | `#2a2416` / `#b58a3a` / `#d4a35a` |
| `lb_wrong` | LB wrong | bad | `#2b1b18` / `#c25a48` / `#e08070` |

Single-select, and **clicking the selected option clears it** (toggle-off). Below: 10px `#5f6b7d; margin-top:8px; line-height:1.4` — "Writes `human_judgment` to `observations.db · pairs` — queued locally in this demo." Real implementation should replace the trailing clause with actual save state (saving / saved / retry).

---

### 9. Non-featured date placeholder

Only the fixture date carries a full artifact set. Selecting any other queue row shows, in the main area: `max-width:340px; padding-top:110px; text-align:center; margin:0 auto`
- `☰` at 26px `#5f6b7d`
- The date in mono, 13.5px/700
- Body text with an inline text-button link (`background:none; border:none; color:#5b8df2; text-decoration:underline; font:inherit; padding:0`) back to the featured date

This is a prototype affordance. In production every date renders fully; no placeholder needed.

---

## Interactions & Behavior — summary

| Trigger | Result |
|---|---|
| Click filter chip | Filters the queue list; chip becomes active. Does not change the open date. |
| Click queue row | Sets the active date **and** moves the keyboard cursor to it; main area re-renders. Selection state for pairs should reset. |
| `j` / `k` / `↑` / `↓` | Move the rail cursor without changing the workspace |
| `enter` | Open the cursor's date |
| `esc` | Clear the pair selection / close the drawer |
| Click matrix cell | Selects that pair → dossier populates; matrix cross-dims; matching speed-strip dots highlight. |
| Click selected matrix cell | Deselects → dossier returns to empty state, dimming clears. |
| Click diagonal cell | Nothing (`cursor:default`, not focusable). |
| Click speed-strip dot | Mutates pair selection (see §6 — reconsider for production). |
| Click judgment button | Sets that judgment for the pair; clicking it again clears. Increments/decrements the queued-count pill and the `Accept families` count. |
| Any judgment exists | `Accept families` becomes enabled; top-bar pill appears. |
| Click scrim (drawer mode) | Clears selection, closing the drawer. |
| Click drawer `✕` | Same. |
| Click `Open report.md` | Opens the report overlay (§11) over the curation screen |
| Click a pair row / LB chip inside the report | Closes the report and selects that pair in the matrix |
| Hover matrix cell / speed dot / queue row | Native `title` tooltip on the first two; bg lift on the third. |

**Transitions present:** matrix cell `opacity .12s` only. Everything else is instant — this is intentional for a dense tool. The one addition to make is the drawer slide (§8).

**Responsive breakpoints**
- `≤1520px` → dossier becomes an overlay drawer, work grid single-column
- `≤1380px` → rail narrows 272 → 224px; work column and date-header horizontal padding drop 22 → 16px
- Below ~900px the design has no defined behavior. This is a desktop curation tool; either define a mobile read-only view with the design team or gate it behind a min-width notice. Do not naively stack it.

**All of these states are now designed** — see §10 and `TapeMatch States.html`: loading, fetch error, empty filter result, zero-recording date, single-recording date, 30+ recording date, and the three judgment-save states.

---

## State Management

Prototype state, all local to the app root:

```
filter    : "needs" | "conflict" | "all" | "curated"     default "needs"
active    : date string                                   default "2001-11-19"
sel       : [indexA, indexB] | null                       default [0, 5] (the conflict pair, pre-selected)
judgments : { [pairKey]: judgmentKey | null }             default {}
drawer    : boolean   ← matchMedia("(max-width: 1520px)")
narrowRail: boolean   ← matchMedia("(max-width: 1380px)")
judged    : derived — count of truthy values in judgments
```

Notes for production:
- `sel` holds **indices into the recordings array**, which is fragile — key by `LB` number instead.
- `pairKey` is the two short ids, numerically sorted, joined by `|`: `"11201|11340"`. Pair identity must be order-independent everywhere.
- The pre-selected conflict pair on load is a nice touch — generalize it: **auto-select the highest-priority unresolved pair for the date** (conflicts first, then below-threshold-but-secondary-linked pairs).
- `active` should live in the URL so a curator can link a colleague to a date. Consider putting the selected pair there too.
- Media queries are read via `matchMedia` with a change listener, not a resize handler. Preserve that.

**Data the screen needs**

```
Date        { date, location, venue, runId, verdict, tone, model, ranAt }
Recording   { lb, family, isReference, ppm, lagKind, ratioConfidence, rating, duration, sourceLineage }
Pair        { key, corr, windowed, hissCorr, fingerprintDice, similarity,
              sameFamily, secondaryLink, notComparable, conflict,
              lbClaimsRelation, lbQuote, humanJudgment }
Note        { ref, tone, headline, body }
QueueItem   { date, location, recordingCount, familyCount, status }
Thresholds  { corr: 0.45, windowed: 0.60, fingerprintBand: [0.15, 0.50], minRatioConfidence: 6.0 }
```

Thresholds should come from the API alongside the data, not be hardcoded in the client — they're tuning parameters of the engine and the UI's job is to render whatever gate the engine actually used.

Writes: a judgment is a single upsert of `human_judgment` on the pair row in `observations.db`. Prototype queues in memory; production should write immediately and optimistically, with the note line under the buttons reflecting save state.

`sourceLineage`, `rating`, and `duration` exist in the fixture but are only surfaced via tooltips today. They are good candidates for a recording-detail popover — worth designing.

---

## Design Tokens

**Colors** — dark, cool-neutral. Backgrounds step in small increments; the accent is the only high-chroma UI color, and semantic tones each come as a triple (fg / bar / bg).

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0c1017` | page background |
| `--surface` | `#131822` | panels, cards, top bar, rail |
| `--surface2` | `#1a2130` | insets, chips, row hover, tracks |
| `--surface3` | `#222b3d` | (defined, reserve) |
| `--border` | `#232b3a` | default hairline |
| `--border2` | `#33405a` | emphasized border, tick lines, button border |
| `--fg` | `#e6e9f0` | primary text |
| `--fg2` | `#9aa5b5` | secondary text |
| `--fg3` | `#5f6b7d` | tertiary / labels / hints |
| `--accent` | `#5b8df2` | selection, links, primary button, evidence fill |
| `--accent-soft` | `#1a2740` | selected chip / row background |
| `--ok-fg` / `--ok-bar` / `--ok-bg` | `#5db679` / `#39a360` / `#16241b` | clean, confirmed same |
| `--warn-fg` / `--warn-bar` / `--warn-bg` | `#d4a35a` / `#b58a3a` / `#2a2416` | review, thresholds, uncertain |
| `--bad-fg` / `--bad-bar` / `--bad-bg` | `#e08070` / `#c25a48` / `#2b1b18` | conflict, LB wrong |
| `--info-fg` / `--info-bar` / `--info-bg` | `#7eb4e8` / `#5891cf` / `#16222e` | different family, neutral notices |
| `--mute-fg` / `--mute-bar` / `--mute-bg` | `#8b94a3` / `#4a5568` / `#181e29` | curated, demoted, n/c |
| primary button text | `#0b1020` | on accent, and inside speed-strip glyphs |

**Family colors** — five, in oklch, equal lightness and chroma, hue-rotated. Do not substitute arbitrary hues; the equal L/C is what keeps the matrix readable as a heatmap.

| Family | Value |
|---|---|
| F1 | `oklch(0.66 0.10 35)` |
| F2 | `oklch(0.62 0.09 240)` |
| F3 | `oklch(0.64 0.10 145)` |
| F4 | `oklch(0.68 0.10 75)` |
| F5 | `oklch(0.60 0.09 320)` |

Dates with more than five families need an extended ramp — continue rotating hue at the same L/C (e.g. add 285, 190, 110, 55, 340) rather than reusing colors.

**Typography**
- UI: **Inter** (Google Fonts), weights 400/500/600/700/800, fallback `system-ui, sans-serif`
- Data: **JetBrains Mono** (Google Fonts), weights 400/500/600/700, with `font-variant-numeric: tabular-nums`
- Base: `13px / 1.45`

Everything numeric or identifier-like is mono: dates, LB numbers, ppm values, run ids, evidence values, keybinding hints, model names. Everything prose is Inter. That split is the type system — hold it.

Scale in use: 9px, 9.5px, 10px, 10.5px, 11px, 11.5px, 12px, 12.5px, 13px, 13.5px, 19px, 24px. Yes, it's a fine-grained scale — that's deliberate for information density. Round to the nearest step in your own scale only if you have one, and keep the *relationships* (labels below body, uppercase section titles at the smallest step).

**Uppercase label recipe** (rail title, section titles, dossier sub-headings): `font-size:10–11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#5f6b7d`.

**Radii** — `2px` (family swatch, tone bar), `3px` (legend swatch), `4px` (matrix cell), `6px` (buttons, rows), `7px` (notes, verdict block, callout), `8px` (speed container), `999px` (pills, chips, evidence track), `50%` (status dots, speed glyphs).

**Spacing** — 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 22, 26px. Effectively a 1–2px-granular scale at small sizes; the recurring rhythm is **gap 6–10px inside a component, 18px between sections, 16–22px page padding**.

**Shadow** — one only: the drawer, `-18px 0 40px rgba(0,0,0,.45)`.

**Fixed dimensions** — rail 272/224px, dossier 350px docked / `min(380px, 92vw)` drawer, matrix row-header column 52px, speed-strip lane pitch 34px.

---

## Assets

**None.** No images, no icon set, no logos. Every glyph is a Unicode character rendered in the page font:

`◆` U+25C6 · `●` U+25CF · `▤` U+25A4 · `✂` U+2702 · `?` · `⊞` U+229E · `☰` U+2630 · `✕` U+2715 · `×` U+00D7 · `→` U+2192 · `−` U+2212 (true minus, in ppm labels) · `·` U+00B7 (separator, used throughout) · `≥` U+2265 · `—` U+2014 · curly quotes `“ ”`

If the codebase has an icon library, swap the UI-affordance glyphs (`✕` close, `⊞`/`☰` empty-state marks) for real icons at equivalent optical size. **Keep the lag-kind glyphs as characters or replace them with a purpose-drawn set** — they're a semantic vocabulary explained by an on-screen legend, so whatever you use must be visually distinct at 9px and must match the legend exactly.

Only two web fonts are loaded (Inter + JetBrains Mono). If the codebase already ships a UI sans and a mono, use those and re-check the density — the sizes above assume Inter's x-height.

---

## Screenshots

In `screenshots/`. Captured from the live prototype at ~2166×1219 CSS px (docked-dossier layout) except where noted. Use these to check your build state-by-state — every state below is reachable in the prototype, so if something is ambiguous, open the HTML and click it.

**Full-screen states**

| File | State | What to check against it |
|---|---|---|
| `01-default-conflict-pair-selected.png` | Default on load — the conflict pair `LB-11201 × LB-11340` pre-selected | The baseline. Matrix cross-dimming (note rows/columns 11201 and 11340 stay bright, everything else at 30%), the selected cell's 2px white border, the red conflict dot, the dossier's conflict callout and `disagrees` pill, `Accept families` **disabled** |
| `02-pair-same-family.png` | Pair `11201 × 11458`, family 1, sim 99 | `same family` **ok** pill; residual correlation **above** the 0.45 mark with the "merges on primary evidence" note; family-tinted cell coloring at the top of its ramp |
| `03-pair-secondary-link.png` | Pair `11890 × 12704`, family 2, sim 87 | `same family · secondary link` **warn** pill; correlation 0.21 sits *below* the threshold mark while windowed coverage 0.83 sits above — the "that's why the secondary path ran" note. This is the case that proves the threshold marks are doing real work |
| `04-pair-not-comparable.png` | Pair `12455 × 11201` — speed-unknown | `n/c` in place of the big percentage; the longer caption; **three** bars reading `n/c` with empty fills but thresholds still drawn; fingerprint dice still has a value (0.206); `no claim` LB state with the muted quote. Also shows the full `n/c` hatched row/column in the matrix |
| `05-judgment-same-source.png` | Judgment `Same source` set on `14210 × 14567` | Green selected judgment button; top-bar `1 judgment queued` pill appears; `Accept families · 1 judged` now enabled |
| `06-judgment-lb-wrong-queued.png` | Judgment `LB wrong` set on the conflict pair | Red selected judgment button — the intended resolution path for a conflict |
| `07-no-selection-empty-dossier.png` | Nothing selected | Dossier empty state (`⊞` / "Select a pair"); matrix at **full opacity with no dimming** — compare against 01 to see exactly what dimming does; note the undimmed matrix is where you can read the family block structure along the diagonal |
| `08-queue-filter-all.png` | Rail filter `All` — 12 dates | Full status vocabulary visible in one column: red conflict, amber review, green clean, grey curated dots |
| `09-queue-filter-conflicts.png` | Rail filter `Conflicts` | Two dates only. Filtering does **not** change the open date |
| `10-queue-filter-done.png` | Rail filter `Done` (curated) | All-grey dots; also shows the non-featured placeholder in the main area |
| `11-non-featured-date-placeholder.png` | Non-featured date selected | The prototype-only placeholder (§9). Production renders every date fully — do not build this |

**Narrow layout (≤1520px)**

| File | State |
|---|---|
| `12-narrow-drawer-open.png` | Dossier as an overlay drawer over the scrim, with its `✕` close button, plus the narrowed 224px rail. Work grid is single-column beneath |
| `13-narrow-drawer-closed.png` | Same width, selection cleared — full-width work column, reduced 16px padding, date-header right block wrapped below the left block |

**Component details** (element captures at 2–3×, for measuring)

| File | Component |
|---|---|
| `14-detail-speed-lag-strip.png` | Speed & lag strip — read the √-scale distribution, the three ticks (`−1,500` / `ref` / `+12,480`), lane packing pushing collided labels to a second row, all six glyph kinds, and the legend |
| `15-detail-verdict-cards.png` | All four analysis verdict cards — one per tone (bad / info / warn / info). Reference for the tone-bar treatment and the copy voice |
| `16-detail-judgment-tones.png` | All four judgment buttons forced into their **selected** state simultaneously (not reachable by clicking — single-select). Use it to sample the four tone triples side by side |
| `25-report-rendered-in-context.png` | report.md overlay open over the curation screen — header, stale banner, outline rail, top of the document |
| `26-report-full-document.png` | The **entire** rendered report as one tall image (720×2295) — every section, table, and the judgment annotation. Best single reference for §11 |
| `27-report-raw-markdown.png` | Raw markdown view with line-number gutter and token tinting |
| `29-diff-in-context.png` | Run diff overlay open over the curation screen — run bar, stat tiles, cause callout |
| `30-diff-full-document.png` | The **entire** run diff as one tall image (720×2444) — run bar through judgment impact. Best single reference for §12 |
| `31-diff-judgment-impact.png` | All three judgment-impact rows together: contradicted (red), corroborated (green), unchanged (grey) |
| — | Screenshot 30 is the reference for the family diff: F1 `regrouped` with two struck-through departures, F3 `split out of base F1` |
| `28-report-print-layout.png` | The report's **print** rendering — light palette, print-only file header, outlined pills, repeating table headers (previewed at a 760px page measure) |
| `24-detail-rail-keyboard-cursor.png` | Rail with the keyboard cursor (grey inset bar, 2001-11-17) on a **different** row than the open date (accent, 2001-11-19) — the two-state model from §2 |

**Designed states** (from `TapeMatch States.html`, full-frame at 1440×870)

| File | State |
|---|---|
| `17-state-loading.png` | Loading — rail, matrix, and dossier skeletons |
| `18-state-fetch-error.png` | Fetch error with technical detail and Retry |
| `19-state-empty-queue-result.png` | Filter matches nothing |
| `20-state-zero-recordings.png` | Date with no recordings indexed |
| `21-state-single-recording.png` | One recording — no pairs, solo card instead of a matrix |
| `22-state-large-date-34-recordings.png` | 34 recordings — compact matrix, rotated headers, horizontal scroll |
| `23-state-judgment-save-states.png` | Saving / saved / save-failed, stacked for comparison |

**Still not designed** — only the drawer's slide-in mid-transition, which is a motion spec rather than a state: `transform: translateX(100%) → 0`, 180ms `cubic-bezier(.2,.8,.25,1)`, scrim cross-fading `0 → 1` over the same duration, both suppressed under `prefers-reduced-motion`.

**Two capture artifacts to ignore** — the screenshotter re-renders the DOM, so a few labels show as slightly split or letter-spaced (e.g. `judgment s queued` in 06, faint doubled cell numbers in 13). Those are not in the live prototype. Open the HTML if a glyph looks wrong.

## 12. Run diff view

Reached from `Compare runs` in the date header, or by clicking the `run …` pill (which gains a `· diff` affordance). **Implemented in the prototype** (`tm-diff.jsx`). Screenshots 29–31.

### The question it answers

A date gets re-analysed when the pipeline changes. The curator's question is never "what are the numbers" — it's **"does the new run invalidate what I already decided?"** Everything in this view is ordered to answer that, and the last section answers it literally.

Note what this means: the diff is not a generic text diff of two `report.md` files. A line-diff would show hundreds of changed digits and bury the four facts that matter. This view diffs *conclusions*, and explains them by *cause*.

### Shell

Reuses the report's sheet shell exactly — `.rpWrap` / `.rpScrim` / `.rpSheet` / `.rpHead` / `.rpOutline` / `.rpDoc` (§11), with `Run diff` as the filename slot and the date + venue as the path slot. Deliberate: these are two readings of the same artifact set, and a curator shouldn't have to learn a second overlay. Actions are `Export diff` and `✕`. `esc` closes the diff first when several layers are open (diff → report → dossier).

### Run bar

`.dfRunbar`: `display:grid; grid-template-columns:1fr auto 1fr; gap:12px` — base card, a `→` in `#5f6b7d`, head card. Cards are `.dfRun` (`border:1px solid #232b3a; border-radius:8px; background:#131822; padding:10px 12px`); the head card takes the brighter `#33405a` border.

Each card: an uppercase role label (`BASE — EARLIER RUN` / `HEAD — CURRENT RUN`), the run id at `700 12px mono` with a status pill (`superseded` mute / `in review` info), then a mono meta block giving model, date, **and the thresholds that run used** — `corr ≥ 0.5 · win ≥ 0.6 · dice groups ≥ 0.35` versus `corr ≥ 0.45 · win ≥ 0.60 · dice confirmatory only`.

**Putting thresholds in the run header is the point of the run bar.** Most "the algorithm changed its mind" moments are threshold moves, and a curator who can see that immediately doesn't waste time re-listening to tape.

### Stat tiles

`.dfStats`: four equal columns. Each `.dfStat` shows a `800 20px mono` figure over a 10.5px label, toned by kind:
1. **`7→5` families · 3 merged · 2 split** (ok green) — the count *and* the two kinds of regrouping, because "fewer families" alone hides a split.
2. **calls flipped** (warn amber)
3. **values moved, call held** (mute) — explicitly counted so a curator knows numbers moved without conclusions changing.
4. **judgments to re-examine** (bad red; mute at zero)

The fourth tile is the headline. It's the only number that implies work.

### 1. What changed in the pipeline

Prose first: "*Same audio, same recordings — every difference below comes from the analysis, not the tapes. Read this section first; it explains every change that follows.*"

Then `.dfCause` — an info-toned callout (`background:#16222e`, border `color-mix(in oklab,#5891cf 42%,transparent)`) listing each pipeline change as a bolded claim plus explanation, with numeric values in `<code>` (`600 11px mono`, `#e6e9f0`). For the fixture: dice demoted from grouping to confirmatory, staircase/splice-aware alignment, secondary clustering added, primary threshold `0.50 → 0.45`.

**Cause before effect.** Every other section is a consequence of this list, and the first cause — dice no longer groups — is what surfaced the LB conflict the curator is being asked to resolve. Leading with per-pair numbers instead would make the run look arbitrary.

### 2. Families

`.dfFamRow`: `display:grid; grid-template-columns:112px minmax(0,1fr) auto; gap:11px` — identity, members, verdict pill.
- Identity: family dot + `F1` at `700 11.5px mono`, with a 10px mono sub-line stating the relationship to the base run: `unchanged`, `was 2 families`, `regrouped from 2 families`, `N left for another family`, or `split out of base F1`.
- Members are `.dfChip`s (`background:#1a2130; border:1px solid #232b3a; border-radius:4px; font:600 11px mono`). A member that **moved in** from another family takes `.moved`: ok-toned fill, green border, `+` marker. A member that **left** is still listed in the family it left, as `.gone`: bad-toned, red border, `text-decoration:line-through`, `−` marker, with a tooltip naming where it went.
- Verdict pill: `held` (mute), `merged` (ok), `split` / `regrouped` (warn).

**Successor mapping — the part that's easy to get wrong.** A naive diff iterates only the *current* families and asks where each member came from. That can never see a departure, so a family that was carved out of a larger one reports itself as "unchanged". The fixture makes this concrete: base family 1 held `11201 11458 11340 11977`; the head run splits it into F1 (`11201 11458` + `13022`) and F3 (`11340 11977`).

So each **base** family is inherited by the head family holding the plurality of its members (ties → lowest head family index):
- That head family is the base family's successor. Its missing base members render as `.gone` chips — F1 shows `−11340 −11977`.
- A head family that inherits nothing was **carved out** — F3 reads `split out of base F1` with a `split` pill. Its members are *not* marked `+`: nobody moved in, the family itself is the change.
- A family that both gained and lost members is `regrouped`.

**Membership is shown once, in its current state, annotated** — not as before/after columns. Two parallel family lists force the reader to diff by eye, which is the work the view is supposed to do for them. Only the delta is marked.

A closing note covers the case the fixture doesn't contain: added recordings get a family row of their own; removed ones stay visible struck through. **Never silently drop a recording between runs** — disappearance is exactly what a curator needs to see.

### 3. Similarity delta

The same matrix geometry as §5, re-encoded to show **change rather than value** — the strongest reuse in the design, because the curator already knows how to read this grid.
- Cell content is the signed point delta (`+33`, `−49`), or `·` when it moved less than a point.
- Background: `color-mix(in oklab, var(--ok-bar) t%, var(--surface))` for more similar, `var(--bad-bar)` for less, where `t = min(72, |Δ| × 2.4)`. Unchanged cells stay flat `#131822`. Text lifts to `#e6e9f0` past `|Δ| ≥ 18`.
- **Green/red here means "moved toward/away from similar", not good/bad** — the legend says "less similar / unchanged / more similar" rather than using the semantic tone names, precisely so it isn't read as a quality judgment.
- **Flipped calls get a 2px `#e6e9f0` ring plus an `!` marker** at top-right (`.dfFlipMk`, `700 8px mono`). A big delta that didn't change the call is interesting; a small delta that *did* is urgent. Magnitude is in the fill, consequence is in the ring — two channels, so neither hides the other.
- Not comparable in either run keeps the established diagonal hatch and `n/c` label, non-interactive.
- Cells are clickable and open the pair in the matrix.

### 4. Pair changes

`.dfTable`, sorted flipped-first then by `|Δcorr|`, listing only pairs that flipped or moved ≥ 0.01. Columns: Pair, Residual correlation, Windowed coverage, Call.

Values use the `Delta` component: `0.440 → 0.520` with a signed `+0.080` in ok green or bad red (`.dfUp` / `.dfDown`), old value in `#5f6b7d` so the new one reads first. Call shows either two pills separated by `→`, or a muted `held · same`. A closing line accounts for the pairs that didn't change — silence about them would read as an omission.

### 5. Your judgments

The section the whole view exists for. Framed by a single sentence of policy: "*A judgment is a call about the tapes, not about a run — so it survives re-analysis. What changes is whether the algorithm still disagrees with you.*"

`.dfImpRow`: `display:grid; grid-template-columns:118px auto minmax(0,1fr)` with a **3px left border** carrying the tone — pair id, the judgment as its toned pill, then the consequence in plain language. Three cases:

| Case | Tone | Copy |
|---|---|---|
| Call unchanged between runs | mute | "The algorithm's call for this pair didn't change between runs — your judgment still stands against the same evidence." |
| Call flipped, now agrees with you | ok | "The algorithm flipped its call and now agrees with you. Your judgment is corroborated; nothing to redo." |
| Call flipped, now contradicts you | bad | "The algorithm flipped its call and now contradicts you. This judgment was recorded against the older run — re-examine it." |

Each row ends with an `Open pair` link. Empty state (`.dfEmpty`, dashed border): "No judgments recorded for this date yet — nothing to reconcile."

Closing policy note: judgments are never rewritten or deleted by a re-run, and a judgment whose pair disappears is **kept and marked orphaned rather than dropped**. Destroying a human decision because a machine re-ran is the one unrecoverable error this screen could make.

### Implementation notes

- `PREV.pairs` is keyed by the two short ids **numerically sorted** and joined by `|` (`"11340|11458"`, never `"11458|11340"`) — the same rule as `TM.pair`. A mis-sorted key fails *silently*: the lookup misses, the pair falls through to "unchanged", and a flipped call vanishes from the matrix, the table, and the counts. `tm-diff.jsx` therefore asserts the invariant at load and `console.warn`s on any violation. **Keep an equivalent guard** — order-independent pair keys are used in four places in this design and this is the failure mode.
- The prototype holds the prior run inline in `tm-diff.jsx` (`PREV`) with the current run coming from `window.TM`. Production fetches any two runs by id — **make the run bar's ids into pickers**; the design leaves room for a select in `.dfRunSel` and this is the one obvious gap.
- Diffing is a pure function of two run artifacts and is computed client-side; **neither run is mutated by viewing** (stated in the footer, because it's the kind of thing a cautious curator will worry about).
- The pipeline-cause list can't be derived from the two artifacts' numbers. It needs the runs to record their own pipeline version / threshold set / changelog entry. **If the backend doesn't store that yet, that's the prerequisite for this view** — without causes it degrades into an unexplained pile of deltas.
- Not designed: diffing across more than two runs (a per-pair timeline), and diffing two *dates* (not a real need — families are per-date).

## 11. report.md view

Reached from `Open report.md` in the date header, and **implemented in the prototype** (`tm-report.jsx`). Screenshots 25–27.

### What it is, and the one decision that shapes everything

`report.md` is a file TapeMatch generates per run — the human-readable rendering of what the algorithm decided. It already exists on disk; a curator can open it in an editor. So this view earns its place only by doing two things a text editor can't:

1. **Link the document back to the workspace.** Every LB number is a chip, every pair row is clickable, and both jump to that pair in the matrix. The report becomes a table of contents for the review, not a dead end.
2. **Show where the human and the report disagree.** The report is a snapshot from generation time; judgments accumulate after it. The view annotates that gap instead of pretending the file is current.

Everything else follows from that. It is **read-only** — no editing a generated artifact.

### Shell

- **Overlay, not a route.** `.rpWrap`: `position:fixed; inset:0; z-index:40; display:flex; align-items:center; justify-content:center; padding:26px`, over a scrim `rgba(5,8,14,.62)`. The curation screen stays visible behind it, because the report is reference material consulted *during* review. Scrim click and `esc` both close (`esc` closes the report before the dossier when both are open).
- **Sheet** (`.rpSheet`): `width:min(1040px,95vw); height:min(880px,94vh); background:#0c1017; border:1px solid #33405a; border-radius:10px; box-shadow:0 24px 70px rgba(0,0,0,.55); overflow:hidden`, column flex. Wider than the dossier because tables need it; capped so it never becomes a full-bleed second app.
- **Header** `.rpHead`: `padding:11px 14px; border-bottom:1px solid #232b3a; background:#131822`. Left: `report.md` at `700 13px mono` plus the real path (`library/dates/2001-11-19/runs/20260602_211540/`) at `500 10.5px mono #5f6b7d`, ellipsised. Naming the path matters — this audience works in the filesystem too.
- Right: a **Rendered / Raw** segmented control (`.rpSeg`: `background:#1a2130; border:1px solid #232b3a; border-radius:6px; padding:2px`; active `.rpSegBtn.on` = `background:#222b3d; color:#e6e9f0`), then `Copy` and `Download` (`.rpIcoBtn`, 11px, `1px solid #33405a`), then the `✕`.
- **Stale banner** `.rpStale` — appears only when judgments exist: `padding:8px 14px; background:#2a2416; color:#d4a35a; border-bottom:1px solid color-mix(in oklab,#b58a3a 40%,transparent)`, an amber dot, the count, and a ghost `Regenerate` on the right. Copy: "*N human judgments recorded since this report was generated — it doesn't reflect them yet.*"
- **Body** `.rpBody`: `display:grid; grid-template-columns:196px minmax(0,1fr); min-height:0`.

### Outline rail (196px)

`.rpOutline`: `background:#131822; border-right:1px solid #232b3a; overflow-y:auto; padding:12px 8px`. Uppercase "CONTENTS" label, then one `.rpOutLink` per section: `11.5px Inter; color:#9aa5b5; padding:5px 7px; border-radius:5px`, hover `#1a2130`, active `background:#1a2740; color:#5b8df2`.

Each entry carries a right-aligned count in 10px mono `#5f6b7d` (`.rpOutN`) — Families 5, Pair evidence 7, Speed & lag 10, Recordings 10. **The counts are the point:** they tell the curator the shape of the report before they scroll it. "Your judgments" appears as an extra entry only when judgments exist.

Clicking sets `scrollTop` on the doc column manually (`el.offsetTop - box.offsetTop - 14`) — again, never `scrollIntoView`.

### Rendered document

`.rpDoc`: `overflow-y:auto; padding:22px 30px 60px`, inner `.rpDocIn` capped at **720px** for line length. Markdown element styles, all in `tm.css`:

| Element | Spec |
|---|---|
| `.rpH1` | 19px/700, `#e6e9f0`, `line-height:1.3` — matches the date header's size so the two surfaces feel like one product |
| `.rpMeta` | 10.5px mono `#5f6b7d`, flex with 8px gaps — run, model, generated timestamp |
| `.rpH2` | 13px/700 `#e6e9f0`, `margin-top:28px; padding-top:12px; border-top:1px solid #232b3a` — the rule does the sectioning, no oversized type needed. Optional count in 10px mono |
| `.rpH3` | 12.5px/600 `#e6e9f0`, `margin-top:18px` |
| `.rpP` | 12.5px/1.6 `#9aa5b5`, `text-wrap:pretty` — larger and looser than the app's 11.5–12px UI text, because this is prose to read rather than a dense control surface |
| `.rpUl` | same type, `padding-left:17px`, 3px between items |
| `.rpTable` | `width:100%; border-collapse:collapse; font-size:11.5px`. `th`: `700 9.5px Inter`, uppercase, `letter-spacing:.07em`, `#5f6b7d`, bottom hairline. `td`: `padding:7px 9px 7px 0`, bottom hairline, `#9aa5b5`, `vertical-align:top`. `.num` cells right-align in tabular mono |
| `.rpQuote` | 12px `#9aa5b5`, `border-left:2px solid #33405a`, `background:#131822`, `border-radius:0 6px 6px 0` — same shape as the dossier's LB quote |
| `.rpFoot` | 10.5px mono `#5f6b7d` above a hairline — "Source of truth is observations.db; this file is a rendering of it." |

**LB chips** (`.rpLb`) — `background:#1a2130; border:1px solid #232b3a; border-radius:4px; padding:1px 6px; font:600 11px mono`, with the 6px family swatch inline. Hover lifts border to `#33405a` and text to `#e6e9f0`. Every LB number in the document is one of these; clicking selects that recording in the matrix. The swatch means family membership is legible even in a plain table row.

**Clickable table rows** (`tr.click`) — `cursor:pointer`, hover `td{background:#131822}`. Used on the pair-evidence and judgments tables. A line of body copy says so explicitly ("Rows are clickable — each opens its dossier in the matrix") rather than relying on the hover to be discovered.

**Judgment annotation** (`.rpJudge`) — a dashed-border block appended to each conflict section: `background:#1a2130; border:1px dashed #33405a; border-radius:6px; padding:7px 11px; font-size:11px`, led by an uppercase `YOUR JUDGMENT` key. **The dashed border is deliberate** — it marks content that is *not* part of the generated file. When the judgment contradicts the report it takes `.differs`: `background:#2b1b18`, red border, `#e08070` text. With no judgment yet it reads "not yet recorded" plus an `open the pair` link.

**Sections**, in order: Summary (prose, with the speed-unknown recording called out inline), Families (family / members / basis / confidence — "basis" names *which* evidence path merged them: primary, secondary, fingerprint-only, single recording), Conflicts (heading + body + judgment annotation), Pair evidence, Speed & lag (ppm / lag curve / ratio confidence, with sub-6.0 confidences and `speed-unknown` in warn amber), Recordings (rating / duration / lineage), Thresholds, and Your judgments.

**Pair evidence tabulates 7 of 45 pairs** — every same-family pair, every conflict, and anything at or above 40% similarity. Below that is noise, and a line under the table says how many were omitted. A 45-row table on a 10-recording date (or a 561-row one at 34 recordings) is not a document, it's a data dump; the matrix is the right tool for the full set.

**Your judgments** table columns: Pair / Judgment (as a toned pill) / Report said — with "— differs" in `#e08070` when they disagree. Copy states the rule: "Regenerating folds them in as an appendix; the algorithm's own calls above are never rewritten." Provenance must stay separable.

### Raw view

Same document, its actual markdown source. `.rpRawIn`: `display:grid; grid-template-columns:auto 1fr; font:500 11.5px/1.75 mono`.
- **Gutter** `.rpGut`: right-aligned line numbers, `background:#131822`, `border-right:1px solid #232b3a`, `user-select:none`, color `color-mix(in oklab,#5f6b7d 65%,transparent)` — present for reference, never competing with the text.
- **Source** `.rpSrc`: `white-space:pre`, `#9aa5b5`, with restrained tinting — headings `#e6e9f0`/700 (`.mdH`), frontmatter and comments `#5f6b7d` (`.mdMeta`), table pipes `#33405a` (`.mdPipe`) so columns read as structure, numeric cells `#7eb4e8` (`.mdNum`). Four token colors, no more — this is a diffable artifact, not a code playground.
- Raw exists so a curator can verify what will land in a commit or a paste. `Copy` copies this text in both modes.

### Implementation notes

- In the prototype the markdown is **generated from the same data as the rendered view** (`markdown(judgments)` in `tm-report.jsx`), so the two can't drift. In production it's the reverse: the file on disk is the source, and the rendered view parses it. **Use the codebase's existing markdown renderer** with these styles applied — do not port the prototype's hand-rolled rendering, and do not write a parser.
- The interactive layer (LB chips, clickable rows, judgment annotations) has to be injected into the rendered output. Two viable routes: post-process the rendered HTML for `LB-#####` patterns and pair headings, or have the generator emit anchors/data attributes the view can hydrate. **The second is better** — the generator already knows the LB numbers; regex-matching your own output is fragile.
- Focus-trap the sheet, return focus to `Open report.md` on close.
- Not designed: a diff view between two runs of the same date (worth asking about — the obvious next feature once dates get re-analysed).

### Print (§11.1)

A curator forwarding a contested date to another collector, or filing a decision, prints the report. Full `@media print` block at the end of `tm.css`; screenshot 28. The `Print` button in the sheet header calls `window.print()`, and the page declares `<meta name="omelette-owns-print" content="report.md">` so a PDF export produces the document, not the screen.

**The report inverts to ink on paper.** Printing a dark UI wastes toner and reads badly, so the print block re-declares a light palette rather than reusing the screen tokens: text `#14181f`, body copy `#3c4553`, secondary `#6b7482`, hairlines `#d6dbe3`, stronger rules `#b9c0cb`, quote fill `#f4f6f9`. Everything is in **pt** in print, not px.

- **Scope is conditional on the report being open**, via `:has()`:
  - `.tmApp:has(.rpWrap) > .tmTop, .tmApp:has(.rpWrap) > .tmBody { display:none !important }` — with the report open, only the report prints.
  - `.tmApp:not(:has(.rpWrap)) > .tmTop, .tmApp:not(:has(.rpWrap)) > .tmBody { display:none !important }` and `.tmApp:not(:has(.rpWrap)) > .tmPrintNotice { display:block }` — with the report **closed**, neither the top bar nor the workspace prints; only the notice does. The top bar has to go too: its dark surface and `#e6e9f0`/`#9aa5b5` text land on white at roughly 1.2:1 and 2.4:1 once a printer drops backgrounds. Product identity is carried by the notice's own `.pnMeta` line instead.
- **The curation screen is deliberately not printable.** It's an interactive workspace — a dense 10×10 heatmap, a scrolling queue, and an overlay panel do not become a useful sheet of paper. Rather than emit a mangled screenshot or (worse) a silently blank page, print with the report closed produces a short **print-only notice** (`.tmPrintNotice`, hidden on screen): "*Nothing to print yet — the curation workspace is an interactive screen, not a document. To print or export this date, open report.md from the date header and print from there.*", with the date in a mono footer line. It names the path forward instead of failing.
- Because `omelette-owns-print` is declared page-wide, this also governs host PDF export: exporting with the report closed yields the notice, not an empty file. **If you want unattended export, open the report first.**
- `<TMReport>` renders as a **child of `.tmApp`, not inside `.tmMain`** — nested inside the scrollable work area it would be hidden along with it. Keep that structure (or use a portal). The `.tmPrintNotice` element is a sibling for the same reason.
- The sheet loses its chrome entirely: `position:static`, auto size, no border, radius, shadow, or `overflow:hidden`; `.rpBody` becomes a block, `.rpDocIn` drops its 720px cap and takes the page measure. Header, scrim, and outline rail are hidden.
- **`@page { margin: 14mm 15mm }`** and no declared paper size, so it prints correctly on Letter and A4 alike.
- **Print-only document header** (`.rpPrintHead`, `display:none` on screen): `report.md` in bold plus the full repository path and product name, above a 1pt rule. The screen header carried that identity; on paper the file has to identify itself.
- **Type:** h1 17pt, h2 12pt over a 0.5pt rule, h3 10.5pt, body 10pt/1.5, tables 9pt with 7.5pt uppercase headers, meta and footer 8.5pt.
- **Pagination rules that matter:**
  - `thead { display:table-header-group }` — column headers repeat on every page a table spans. Non-negotiable for the pair-evidence and recordings tables.
  - `tr { break-inside:avoid }` — no row split across a page break.
  - `h2`/`h3` `{ break-after:avoid }` — a heading never ends a page.
  - `.rpJudge` and `.rpQuote` `{ break-inside:avoid }` — an annotation stays whole with its meaning.
- **Fills become outlines.** Pills and LB chips drop their backgrounds for 0.5pt borders with dark text (`!important`, since the screen pills are tone-filled). Ink-frugal, and tone-coded fills turn to mud in grayscale.
- **The two things that must survive grayscale** keep explicit color-adjust: family swatches and the conflict dot get `print-color-adjust:exact` with a 0.5pt outline so they're visible even if a printer drops backgrounds. Family identity is the report's core claim.
- **Warn-colored values are re-inked, not dropped:** `speed-unknown` and sub-6.0 ratio confidences go to `#7a5b12` at weight 600 — the screen amber (`#d4a35a`) is unreadable on white. These are `.rpWarn` / `.rpDiff` / `.rpAgree` **classes**, not inline styles, precisely so print can restyle them; note they're selected as `.rpTable td.rpWarn` to beat the `td` color rule.
- **The human layer stays marked on paper.** The stale banner reverts to a plain line of text above a rule (its Regenerate button hidden) instead of an amber panel, and `.rpJudge` keeps its **dashed** border — on a printout that hasn't been regenerated, distinguishing the algorithm's claims from the curator's annotations is the whole point.
- **Raw view prints too**, and changes shape to suit paper: the line-number gutter is hidden and `.rpSrc` switches to `white-space:pre-wrap` with `overflow-wrap:break-word`. Paper has no horizontal scrollbar, so long table lines wrap rather than being guillotined. Token tinting collapses to two greys.
- Not handled: page numbers and "page N of M" (CSS `@page` margin boxes are still unreliable across browsers) — add them server-side if the printout needs to be citable.

## 10. Edge and transient states

Designed in `TapeMatch States.html` — a pannable canvas of seven frames, built from the same `tm.css` as the main prototype, so every value below is real and inspectable. New CSS for these states is appended to `tm.css` under clearly-marked section comments (`states: skeleton`, `states: generic empty / error block`, `states: single-recording solo card`, `states: compact matrix for large N`, `states: judgment save feedback`).

### 10.1 Loading

The rail resolves first (it's a cheap query), so it can render real rows while the date's artifacts are still in flight — but the design shows the harder case, everything loading at once.

- **Skeleton primitive** — `.sk`: `background:#1a2130; border-radius:4px; position:relative; overflow:hidden`, with an `::after` sweep: `linear-gradient(90deg, transparent, rgba(255,255,255,.045) 45%, transparent)` translating `-100% → 100%` over **1.25s** `cubic-bezier(.4,0,.2,1)`, infinite. Under `prefers-reduced-motion:reduce` the animation is dropped and replaced with a flat `rgba(255,255,255,.02)`.
- The sweep is deliberately faint (4.5% white). At normal shimmer intensity it fights the matrix's own color coding once cells populate.
- **Matrix skeleton renders the real grid** — same `52px repeat(N, minmax(0,1fr))` template, same `aspect-ratio:1` cells, same diagonal treatment. **There must be no reflow when values arrive.** N comes from the date's recording count, which is known before the pair measurements are.
- Cells are `.sk` blocks with the standard 1px border and 4px radius; row/column headers are 34×8px pills.
- **Progress line under the matrix** (`.tmSkNote`, 10.5px mono `#5f6b7d`): `measuring 45 pairs · 31 done`. Pair count is `n(n−1)/2` and is knowable up front, so show real progress rather than an indeterminate spinner — on a 34-recording date this is 561 measurements and the curator needs to know it's a wait.
- **Top-bar crawl indicator** switches to the amber bar color with the label `measuring pairs…`.
- **Dossier skeleton** mirrors its real structure: pair labels, verdict block (a 74×22px number block over a 150×7px caption, plus a pill-shaped block), then both evidence sub-headings with their bars. Sub-headings render as **real text**, not skeletons — they're static labels, so blanking them loses orientation for nothing.
- Evidence tracks render empty (real track styling, no fill, no threshold mark). Don't skeleton the track itself; it's already a container.

### 10.2 Fetch error

- Date header still renders whatever is known (date, venue) and drops what isn't (`run` pill, model line). Status pill becomes **bad** / `unavailable`, verdict text `Couldn't load this date's analysis`.
- Body uses the new `.tmState` block: `max-width:400px; margin:0 auto; padding-top:104px; text-align:center`.
  - Icon `⚠` at 26px in `#e08070`
  - Head 13.5px/700 — "Couldn't load this date"
  - Body 11.5px `#5f6b7d` — "The run's artifacts didn't come back. Nothing has been changed — your queued judgments are safe." **Reassurance about queued judgments is required copy**; a curator mid-session needs to know the failure didn't eat their work.
  - Technical detail block (`.tmStateDetail`): left-aligned, 10.5px mono `#5f6b7d`, `background:#131822; border:1px solid #232b3a; border-radius:6px; padding:8px 11px; white-space:pre-wrap`. Contains the failing request, status, elapsed time, run id, and attempt count. This audience is technical — give them the real error, don't hide it behind "something went wrong".
  - Actions: `Retry` (primary) + `Open run log` (ghost), `display:flex; gap:8px; justify-content:center; margin-top:13px`
- **The rail stays fully interactive.** One date failing must never block the queue.

### 10.3 Empty filter result

The rail's own empty state (`.tmRailEmpty`) is extended from bare "Nothing here." into something useful:
- Line 1 states the outcome in the filter's own terms — `No conflicts left.`
- Line 2, 10.5px, `margin-top:6px` — `Every disagreement on this page is resolved.`
- A `.tmLink` text button, `margin-top:9px` — `Show all dates`, which switches the filter to All.
- The header count reads `0 need you` (same warn color; zero is good news here but the token stays consistent).
- **The main area keeps the open date.** Filtering the rail never unloads the workspace. The main-area block only appears if nothing was open to begin with: `⊞` / "Nothing left in this filter" / "The date you were working on stays open. Widen the filter to keep going."

### 10.4 Date with zero recordings

A known show with nothing circulating. Distinct from an error — nothing is wrong.
- Status pill **mute** / `no recordings`; verdict text `Known date · nothing circulating in the library`. No run pill, no model line — no analysis ran.
- `.tmState` with icon `∅` at 26px in `#8b94a3` (mute, not bad — tone carries the "this is fine" signal).
- Head "No recordings for this date"; body explains both the cause and the recovery: "The show is in the library but no audience recordings have been indexed, so TapeMatch has nothing to compare. It will re-enter the queue automatically when a recording appears."
- Actions are both ghost: `Open date page`, `Skip in queue`. No primary — there's no productive action, so nothing should look like one.
- Rail row shows `0→0`.

### 10.5 Single-recording date

One recording means zero pairs, so the matrix, the dossier, and the judgment control all have nothing to operate on. Rather than render three empty components, the date collapses to a solo card.
- Work grid uses the existing `.tmWork.single` (no dossier column at any width).
- Section title becomes **Recording** with the hint *nothing to compare — pair views only appear from two recordings up*. Naming the threshold prevents the state reading as a bug.
- **`.tmSolo` card** — `max-width:520px; border:1px solid #232b3a; border-radius:8px; background:#131822; padding:13px 15px`
  - Top row: family swatch, `LB-11902` at `700 13px mono`, then `pill sm ok` → `reference` and `pill sm mute` → the letter rating
  - Meta grid: `display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin-top:11px; font-size:11px` — keys `#5f6b7d`, values `#9aa5b5` in mono. Rows: Duration, Speed (`0 ppm · reference`), Lineage. **This is where `sourceLineage`, `duration`, and `rating` finally surface in the UI** — use the same treatment for the recording-detail popover suggested in §State Management.
  - Footer note, separated by `border-top:1px solid #232b3a; padding-top:10px; margin-top:11px`, 11px `#5f6b7d`: "Sole recording, so it becomes its own family with no evidence needed. Accepting records the family without a human pair judgment."
- `Accept families` is **enabled** here despite zero judgments — the "needs a judgment first" rule exists to stop rubber-stamping pair decisions, and there are no pair decisions. Special-case it.
- The speed strip is **kept** with its single reference dot and the axis note replaced by `no offsets to plot`. Keeping it preserves the page's shape across dates; the empty axis is honest and costs one row of height.

### 10.6 Large date (30+ recordings)

Designed at 34 recordings / 561 pairs — the practical worst case in the library.
- `.tmMatrixWrap.wide` drops the 760px cap and scrolls horizontally (`overflow-x:auto`).
- `.tmMatrix.compact`: `gap:1px`, fixed **22px** columns (`grid-template-columns:46px repeat(N,22px)`) rather than `minmax(0,1fr)` — past ~20 recordings, fitting the viewport wins over filling it.
- Cells: `border-radius:2px`, `font-size:0` — **the number is dropped below 28px** and lives in the tooltip. This is the documented behavior from §5, realized. Color and position carry the reading at this density; a 7px numeral would not.
- Column headers rotate: `writing-mode:vertical-rl; transform:rotate(180deg)` at 8.5px with `letter-spacing:-.02em`, swatch inline. Row headers shrink to 46px and 8.5px.
- **Family block structure becomes the primary read.** Because rows are family-ordered, the same-family tints form squares along the diagonal — at this size that pattern *is* the information, and off-diagonal bright cells are exactly what the curator is hunting.
- Conflict dots stay full size (7px) — they must not shrink with the cells; at 22px a conflict dot occupies a third of the cell, which is correct emphasis.
- Legend gains a right-aligned density note (`.tmDensity`, mono): `34 recordings · 9 families · 561 pairs · values in tooltip below 28px`.
- **This frame demonstrates the extended family ramp** required past five families (§Design Tokens). Nine distinct hues at the same lightness/chroma: the five base values plus `oklch(0.65 0.10 285)`, `oklch(0.63 0.09 190)`, `oklch(0.66 0.10 110)`, `oklch(0.61 0.09 340)`. Never recycle a hue on the same date — two unrelated families sharing a color reads as one family split across the matrix, which is the exact error the curator is looking for.
- Dossier still docks on wide viewports; the frame shows the single-column case for matrix clarity.
- **Recommended additions** if this date type is common: sticky row/column headers on scroll, and a family-boundary rule (`.tmFamRule`, 1px `#33405a`) between family blocks. The class is in the stylesheet but not wired — confirm with design before enabling, it adds a lot of lines.

### 10.7 Judgment save states

Replaces the prototype's fixed "queued locally in this demo" line with a real save-status line (`.tmSave`, `display:flex; align-items:center; gap:6px; margin-top:8px; font-size:10px`), each variant led by a 6px dot.

| Variant | Dot | Text color | Copy |
|---|---|---|---|
| `.saving` | `#4a5568`, opacity pulsing to .3 over 1s (dropped under reduced-motion) | `#5f6b7d` | `Saving…` |
| `.saved` | `#39a360` | `#5db679` | `Saved 14:22 · LB wrong` |
| `.failed` | `#c25a48` | `#e08070` | `Couldn't save — kept locally.` + a `Retry` text button (`600 10px Inter`, `#e08070`, underlined) |

- The static explainer line ("Writes `human_judgment` to `observations.db · pairs`.") stays above the status line — it explains the mechanism, the status line reports the attempt.
- Writes are **optimistic**: the button turns on immediately, the queued-count pill and `Accept families · n judged` update immediately, and a failure does **not** revert any of them. The judgment is the curator's, not the server's — losing it to a dropped request is the worst outcome here. Retry, and flush any pending judgments on `Accept families`.
- `Saved` should fade to the idle explainer after a few seconds rather than persisting; failures persist until retried.

## Files

All in this bundle, and at the project root:

| File | Contents |
|---|---|
| `TapeMatch Curation.html` | Entry point. Script tags + a `<link>` to `tm.css`. |
| `tm-data.js` | Fixture data: family colors, 10 recordings, hand-authored pair overrides, deterministic hash fallback for unauthored pairs, the date record, analysis notes, the 12-date queue, status vocabulary, thresholds. Exposed as `window.TM`. |
| `tm-parts.jsx` | The four visualizations: `Matrix`, `EvBar`, `SpeedStrip`, `VerdictCards`, `Dossier`. All the interesting rendering logic (color mixing, √ scale, lane packing) lives here. |
| `tm-app.jsx` | Shell: `Rail`, `DateHeader`, `Section`, `App`. Holds all state, including the keyboard model and the report overlay. |
| `tm-diff.jsx` | The run diff view (§12) — run bar, cause list, family diff, delta matrix, pair-change table, judgment impact. Carries the fixture's prior run (`PREV`). |
| `tm-report.jsx` | The report.md view (§11) — rendered + raw, outline, LB chips, clickable pair rows, judgment annotations, and the markdown generator that feeds both views. |
| `screenshots/` | 31 captures — states 01–16 from the live prototype, 17–23 from the states document. |
| `TapeMatch States.html` | Canvas of the seven edge/transient states designed in §10. Pan and zoom; each frame is labelled. |
| `tm-states.js` | Builds those frames. Static markup generated in plain JS — **reference only**, not a component to port. The large-N matrix generator in here is useful for stress-testing your own matrix. |
| `tm.css` | The shared stylesheet, used by both HTML files. Ends with the new state styles from §10. |

To run the prototype: serve the folder over HTTP (the Babel-transpiled `.jsx` files are fetched, so `file://` will not work) and open the HTML.

Reading order for implementation: `tm.css` (tokens + every component style — read this first) → `tm-data.js` (shapes) → `tm-parts.jsx` (the visuals) → `tm-app.jsx` (composition) → `tm-states.js` (§10 states).

---

## Implementation Order (suggested)

1. Tokens + type into the codebase's theme. Verify the four semantic tone triples and the five family colors resolve.
2. Shell: top bar, rail, date header, work grid, the two media-query breakpoints. Get the `min-height:0` chain right before adding content.
3. Matrix. This is the hardest piece — get the three color regimes, the diagonal, `n/c` hatching, the conflict dot, symmetric selection, and cross-dimming all correct, plus the a11y grid navigation.
4. Dossier with evidence bars — including the conditional correlation note and the demoted fingerprint bar with its coincidence band.
5. Speed strip — √ scale, ticks, lane packing.
6. Verdict cards.
7. Judgment write path + `Accept families`. (Rail keybindings are already implemented in the prototype — port them as-is.)
8. The report.md view (§11) — shell, outline, document styles, then the interactive layer.
9. The run diff (§12) — needs run artifacts to record their own pipeline/threshold metadata first.
10. The §10 states: loading skeletons (get the no-reflow grid right), fetch error, empty filter, zero/single-recording dates, save status. Then the large-N matrix path and the drawer transition + focus management.
