# 06 · Pixel spec — exact layout geometry

> **Use this as the layout source of truth.** Every value below is lifted
> verbatim from the prototype source (`_source/*.jsx`, `app.css`, `lbb-tokens.js`).
> Where this doc and the ASCII diagram in `00-overview.md` disagree, **this doc
> wins** — it reflects what the running prototype actually renders.
>
> Acceptance test: open `Library (Unified) - Standalone.html`, screenshot it,
> and diff your build against it until they're indistinguishable. Don't re-derive
> the layout from prose — match these numbers.

---

## ⚠️ Read this first — the overview diagram is misleading

`00-overview.md` draws a **three-column** body: `facet rail │ table │ detail`.
**The built prototype does not have a left facet rail.** Filters live in a
**top filter bar**; the body is **two panes: table + detail panel**. The 248px
`FacetRail` component in `_source/library-parts.jsx` is dead code from an earlier
study — do not build it. If a previous implementation pass added a left rail,
that's the diagram's fault, not yours.

Correct anatomy:

```
┌─────────────────────────────────────────────────────────────┐
│ Toolbar          (view toggle · scope · search · columns · ⋯)│  h: content of 12px+ pad
├─────────────────────────────────────────────────────────────┤
│ Filter bar       (Views ▾ · Decade ▾ · Status ▾ · …)         │  flex-wrap row
├─────────────────────────────────────────────────────────────┤
│ Summary strip    (N results · chips · coverage · sort)       │  min-height 36
├──────────────────────────────────────────┬──────────────────┤
│  Table (flex: 1, scrolls)                 │  Detail panel    │
│                                           │  (fixed width)   │
└──────────────────────────────────────────┴──────────────────┘
```

---

## Frame & shell  (`app-shell.jsx`)

| Region | Value |
|---|---|
| Outer frame | `width: 1920px; height: 1080px;` flex column, `overflow: hidden` |
| **Sidebar** | `width: 224px; flex: 0 0 224px;` bg `--lbb-surface`, `border-right: 1px solid --lbb-border` |
| **Topbar** | `height: 52px; flex: 0 0 52px;` `padding: 0 20px;` `gap: 16px;` `border-bottom: 1px` |
| **Status footer** | `height: 28px; flex: 0 0 28px;` `padding: 0 20px;` `gap: 20px;` `font: 11px var(--lbb-mono)` |
| Main column | `flex: 1`, column; content area is `flex: 1; overflow: auto; min-height: 0` |

**Sidebar internals**
- Brand block: `padding: 16px 18px 14px;` `gap: 10px;` `border-bottom: 1px`. LB badge `30×30`, `border-radius: 8px`, `font: 800 14px`.
- Nav scroll area: `padding: 10px 8px 16px`.
- Group spacing: `margin-top: 14px` (first group `0`).
- Group label: `font: 700 10px` uppercase, `letter-spacing: 0.12`, `padding: 6px 10px 6px`.
- Nav item: `padding: 7px 10px; margin-bottom: 1px; gap: 10px; border-radius: 6px; font-size: 12.5px;` icon `15px`. Active = bg `--lbb-accent-soft`, fg `--lbb-accent-mid`, weight 600.
- "NEW" / count badges: `font-size: 8.5px` / `10.5px`.
- User chip: `padding: 10px 12px; gap: 10px;` avatar `28×28` circle.

**Topbar internals**
- Crumbs: `gap: 8px;` separator `/` `font-size: 12px`; crumb `font-size: 13px`, last crumb weight 600 / `--lbb-fg`, others 500 / `--lbb-fg2`.
- ⌘K search button: `height: 32px; min-width: 280px; border-radius: 8px; padding: 0 10px 0 12px;` bg `--lbb-surface2`.
- Bell button: `34×34`, `border-radius: 8px`; dot `7×7` at `top: 7px; right: 8px`.

**Status footer**: mono items separated by `·` (`--lbb-border2`), `gap: 20px`. Sync chip pushed right via `flex: 1` spacer.

---

## Content header stack (identical in both lenses)

All three bars are full-width, stacked, each with `border-bottom: 1px solid --lbb-border`.

| Bar | padding | gap | bg | z-index | notes |
|---|---|---|---|---|---|
| **Toolbar** | `12px 20px` | `10px` | `var(--sep-chrome-bg, --lbb-surface)` | 4 | view toggle, scope, search, columns, icons |
| **Filter bar** | `8px 20px` | `8px` | `var(--sep-summary-bg, --lbb-surface)` | 3 | `flex-wrap: wrap`; Views ▾ + facet ▾ menus |
| **Summary strip** | `8px 20px` | `12px` | `var(--sep-summary-bg, --lbb-surface)` | 1 | `min-height: 36px; font-size: 12px` |

**Toolbar contents (left→right):** ViewToggle · vertical divider `1px × 22px` (`--lbb-border`) · ScopeControl (recording lens only) · search `<Input>` (`flex: 1; height: 32px`) · `Columns` button (secondary, md) · download IconButton · more IconButton.

**Filter bar contents:** Views menu button · divider `1px × 20px` · Decade / Status / Rating / Source (+ Files in owned scope) facet menus · `flex: 1` spacer · `Clear N` ghost button when active.

**Summary strip contents:** bold result count · "of N in master DB" · active-filter chips · `flex: 1` spacer · coverage figure · divider `1px × 14px` · Sort ghost button. Dividers in this strip are `1px × 14px`.

**ViewToggle / ScopeControl segmented control:** outer `padding: 2px; border-radius: 8px;` bg `--lbb-surface2`, `border: 1px`. Buttons `height: 28px; padding: 0 12px; border-radius: 6px; gap: 7px; font-size: 12px;` icon `14px`. Active button = bg `--lbb-surface`, `border: 1px --lbb-border2`, `box-shadow: --lbb-shadow`, weight 650.

---

## Body: table + detail  (`libu-recording.jsx`, `libu-performance.jsx`)

Body wrapper (the `flex: 1` region below the summary strip):
```css
flex: 1; display: flex; min-height: 0; position: relative;
background: var(--sep-body-bg, transparent);
gap: var(--sep-body-gap, 0px);
padding: var(--sep-body-pad, 0px);
```

Table region:
```css
flex: 1; overflow: auto; min-height: 0; min-width: 0; position: relative;
background: var(--sep-table-bg, transparent);
border-radius: var(--sep-radius, 0px);
box-shadow: var(--sep-table-shadow, none);
```

**Detail panel** (`aside`):
- Open: `width: {W}px; flex: 0 0 {W}px;` `border-left: 1px solid --lbb-border` (flush) ; header `padding: 10px 10px 10px 16px` + `border-bottom: 1px`; body `flex: 1; overflow-y: auto; padding: 16px`.
- Collapsed: `width: 40px; flex: 0 0 40px;` single centered info IconButton.
- Default width: **recording lens 380px**, **performance lens 400px**.
- Width is tweakable: slider **min 340 / max 480 / step 10** (`detailWidth`). Default tweak value `400`.
- The bulk-action bar floats over the table: `position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%); padding: 8px 10px 8px 14px; border-radius: 10px;` shadow `--lbb-shadowLg`.

---

## Framed vs. flush separation  (`app.css`, set on `#frame`)

The app toggles `data-sep="framed"` on `#frame` (driven by Tweak `cardStyle`).
When **unset (flush)**, every `--sep-*` var is undefined so the fallbacks apply:
transparent body, `0px` gap/pad/radius, no shadow, and the chrome/summary bars
fall back to `--lbb-surface`. When **`data-sep="framed"`**:

| token | value |
|---|---|
| `--sep-body-bg` | `var(--lbb-bg)` |
| `--sep-body-gap` | `12px` |
| `--sep-body-pad` | `14px` |
| `--sep-radius` | `12px` |
| card backgrounds (rail/detail/table/chrome/summary) | `var(--lbb-surface)` |
| `--sep-ring` | `0 0 0 1px var(--lbb-border)` |
| `--sep-lift` (dark) | `0 14px 34px rgba(0,0,0,0.52)` |
| `--sep-lift` (light) | `0 10px 26px rgba(40,30,15,0.14)` |
| `--sep-top` (dark) | `inset 0 1px 0 rgba(255,255,255,0.07)` |
| card shadow | `var(--sep-ring), var(--sep-lift), var(--sep-top)` |

So "framed" = each of toolbar/filter/summary/table/detail becomes a `--lbb-surface`
card with `12px` radius, lifted on a `14px` `--lbb-bg` gutter with the ring+lift+top
shadow. Both `data-sep` **and** `data-mode` live on `#frame` so the shadow adapts per mode.

### 🔧 If the framed toggle does nothing (no cards appear)

The toggle is a **CSS-custom-property cascade**, not a class that styles anything by
itself. Three links must ALL be present — debug in this order:

**Link 1 — the attribute lands on `#frame`.** The toggle must do exactly:
```js
const frame = document.getElementById("frame");
frame.setAttribute("data-mode", mode);               // "light" | "dark"
if (cardStyle === "framed") frame.setAttribute("data-sep", "framed");
else frame.removeAttribute("data-sep");
```
The element it targets **must have `id="frame"`**. The per-mode shadow rules are
`#frame[data-mode="dark"][data-sep="framed"]` — if your root node isn't `id="frame"`,
those never match and `--sep-lift`/`--sep-top` stay undefined. Setting `data-sep` on
`<body>` or a React wrapper is the #1 cause of "toggle does nothing."
*Check:* toggle on → inspect → confirm `data-sep="framed"` sits on the `#frame` node.

**Link 2 — the `[data-sep="framed"]` block from `app.css` is actually loaded.** The
`--sep-*` definitions live in `app.css` (see the token table above). If that file/block
wasn't ported, the attribute toggles but defines nothing.
*Check:* in devtools, on `#frame`, the Computed/Variables panel shows `--sep-body-pad: 14px`
when framed is on.

**Link 3 — the layout elements READ the vars.** This is the link most often lost when the
layout is rebuilt from scratch. The body/table/detail/header elements must consume the
tokens with flush-look fallbacks, e.g.:
```jsx
// body wrapper
background: "var(--sep-body-bg, transparent)",
gap:        "var(--sep-body-gap, 0px)",
padding:    "var(--sep-body-pad, 0px)",
// table region
background:   "var(--sep-table-bg, transparent)",
borderRadius: "var(--sep-radius, 0px)",
boxShadow:    "var(--sep-table-shadow, none)",
// each header bar
background: "var(--sep-chrome-bg, var(--lbb-surface))",   // toolbar
background: "var(--sep-summary-bg, var(--lbb-surface))",  // filter + summary
// detail panel
background: "var(--sep-detail-bg, transparent)",
borderRadius: "var(--sep-radius, 0px)",
boxShadow:    "var(--sep-detail-shadow, none)",
```
If these elements use hardcoded `background`/`box-shadow` instead of `var(--sep-*, …)`,
the toggle flips an attribute that nothing consumes → zero visible change. Grep your
build for `--sep-` — if it returns nothing in the layout components, that's the bug.

---

## Table cells & density  (`lbb-ui.jsx` + `lbb-tokens.js`)

Cell padding is density-driven via `--lbb-d-pad`:
- **TH**: `padding: 8px var(--lbb-d-pad);` `font: 600 10.5px` uppercase, `letter-spacing: 0.04`; sticky, bg `--lbb-surface2`.
- **TD**: `padding: calc(var(--lbb-d-pad) - 2px) var(--lbb-d-pad);` `border-bottom: 1px solid --lbb-border`.
- **GroupRow** (year header): leading `3px` spacer `<td>`, then `padding: 5px var(--lbb-d-pad);` bg `--lbb-surface2`, `font: 600 11px`.
- Every row's **first column is a 3px-wide status edge** (`<col width: 3>`); colored per status (`--lbb-ok-bar` owned, warn/info edges).

Density presets (`applyTheme` writes these as `--lbb-d-*`):

| density | `--lbb-d-row` | `--lbb-d-pad` | `--lbb-d-gap` | `--lbb-d-font` | `--lbb-d-sideRow` |
|---|---|---|---|---|---|
| compact | 24px | 6px | 4px | 11.5px | 24px |
| **default** | **32px** | **8px** | **6px** | **12.5px** | **28px** |
| comfortable | 40px | 12px | 10px | 13.5px | 34px |

---

## Column templates (`<colgroup>`, exact px)

**Recording lens — `all` / `unowned` scope** (11 cols):
`3 · 34 · 92 · 88 · 88 · [auto: Location] · 54 · [auto: Description] · 60 · 52 · 52`

**Recording lens — `owned` scope** (11 cols):
`3 · 34 · 92 · 88 · 88 · [auto: Location] · 54 · 250 · 180 · 90 · 44`

**Performance lens** (10 cols):
`3 · 30 · 32 · 116 · [auto: Performance] · 210 · 132 · 56 · 56 · 150`

(`3` = status edge; `30–34` = expand chevron / checkbox; `[auto]` columns absorb remaining width.)

---

## Buttons & inputs (`lbb-ui.jsx`)

| Control | sm | md | lg |
|---|---|---|---|
| Button height | 24px | 30px | 36px |
| Button padding-x | 8px | 12px | 14px |
| Button font-size | 11.5px | 12.5px | 13.5px |
| Button icon size | 12px | 14px | 14px |

- All buttons `border-radius: 6px`, `font-weight: 600`, `gap: 6px`.
- IconButton: square, default `28×28`, `border-radius: 6px`, icon ≈ `0.55 × size`.
- The search `<Input>` in both toolbars is forced to `height: 32px` (overrides md default).

---

## Type & base (`app.css`)

- Body: `font-family: "Inter", ui-sans-serif, system-ui; font-size: 13px;` antialiased.
- Mono: `--lbb-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace` — used for LB#, dates, paths, counts, status footer.
- Row hover: `background: color-mix(in oklab, currentColor 4%, transparent)`.
- Focus: `box-shadow: var(--lbb-focusRing); border-radius: 6px`.
- Scrollbar: `10px` wide, thumb `--lbb-fg3 @ 50%`, `6px` radius, `2px --lbb-bg` border.

---

## Quick parity checklist for the implementer

- [ ] Body is **two panes** (table + detail). **No left facet rail.**
- [ ] Sidebar `224`, topbar `52`, footer `28` — exact.
- [ ] Three stacked header bars: toolbar `12px 20px`, filter `8px 20px`, summary `8px 20px` (min-h 36).
- [ ] Detail panel default `380` (recording) / `400` (performance); collapses to `40`.
- [ ] Default density rows are `32px`; cell pad keyed to `--lbb-d-pad` (`8px` default).
- [ ] Column widths match the `<colgroup>` tables above, per scope/lens.
- [ ] Framed mode = `14px` gutter, `12px` radius cards, ring+lift+top shadow; flush mode = transparent, no radius, no shadow.
- [ ] 3px status edge as the first column of every data row.
