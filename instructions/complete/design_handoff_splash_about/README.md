# Handoff: LosslessBob — Startup Splash + About dialog

## Overview
Two surfaces for the LosslessBob desktop app (Electron + React + TypeScript):

1. **Startup Splash — variant A "Launch card"** — the window shown while the app
   boots. Brand mark + a progress bar driven by the **real startup sequence**.
2. **About dialog — variant C "Tabbed"** — the Help → About window. Brand header +
   four tabs (About / Tech / Credits / Changes).

Build **only these two variants**. The bundle also contains variants B and C of the
splash and A and B of the About dialog — those are alternates for context, **do not
build them**.

## About the Design Files
The files in this bundle are **design references created in HTML/React-via-Babel** —
prototypes that show intended look and behavior. They are **not** production code to
paste in. The task is to **recreate these designs inside the real LosslessBob app**
(the Electron + React + TypeScript `gui_next` target) using its existing component
patterns, not to ship this HTML.

Open `LosslessBob Splash & About.html` in a browser to see everything live on a
pan/zoom canvas. The splash auto-plays its boot sequence at **true speed (~2.4s)**;
click any splash to replay.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and motion are final. Recreate
pixel-for-pixel using the codebase's component library. Every measurement below is
exact (pulled from the source).

---

## The startup sequence (the important part)

The splash progress is **not decorative** — it must reflect real boot phases. The
phases and timings below were measured from a normal cold start (`main()` →
`window.show()` ≈ **2.407 s**). Source of truth: `lbb-launch-data.js` → `boot`.

| # | label              | detail                          | begins at (ms) |
|---|--------------------|---------------------------------|---------------:|
| 0 | Starting backend   | Flask · Waitress                |            120 |
| 1 | Opening database   | checksum_lookup.db · LB-16630   |            510 |
| 2 | Loading interface  | electron-vite · renderer        |            792 |
| 3 | Backend ready      | localhost:5174                  |          1 679 |
| 4 | Building views     | 14 panels                       |          1 712 |
| 5 | Restoring session  | geometry · shadows              |          2 381 |
|   | **Ready**          | 704,624 checksums               |  **2 407** (done) |

Notes that matter for implementation:

- **The biggest visible dwell is "Building views"** (1.71 s → 2.38 s). That is the
  renderer instantiating the 14 tab panels — the only heavy work happening *while the
  splash is actually on screen*. If you can emit a real `n/14` count here, do; it is
  the most honest progress signal in the whole boot.
- **Backend is up early.** `Backend ready` (localhost:5174) fires at ~1.68 s, near the
  start of the visible splash — do not narrate it as the *last* step.
- **The bar tracks elapsed-vs-expected**, capped at 96% until a real `done`. It never
  shows a fake 100%.

### Driving it in production (and the 8-second-boot question)
`useBoot` (in `lbb-launch-parts.jsx`) accepts a real feed so the bar reflects genuine
state instead of a fixed timer:

```js
// MOCK (what the HTML uses): replays the phases above at true speed
const boot = useBoot();

// PRODUCTION: feed real elapsed time + a done flag from the Electron main process
const boot = useBoot({ feed: { elapsedMs, done } });
```

- Wire `elapsedMs` from `performance.now() - bootStart`, pushed over IPC (or set in the
  renderer as phases complete). `done` flips true on the real "window ready" event.
- **Overrun / slow boot:** if `elapsedMs` passes `bootReadyMs` (2407) without `done`,
  `useBoot` returns `overrun: true`. The splash then switches the bar to an
  **indeterminate sliding animation** and shows `…` instead of a percentage — so an
  8-second cold start honestly *dwells on the current phase* rather than finishing at
  2 s and lying. (`ProgressBar` already supports `indeterminate`.)
- If you cannot produce a real `elapsedMs`, render the bar **indeterminate from the
  start** and just swap the phase label as each milestone fires. Never fake a percentage.

`useBoot` return shape: `{ pct, idx, label, detail, done, overrun, replay, run, elapsed }`.

---

## Screen 1 — Splash A · "Launch card"
Source: `splash-variants.jsx` → `SplashClassic`. Frame size in the mock: 900×560 (the
real splash window can be any size; content is centered).

### Layout
- **Stage** (fills the window):
  - background `#131110` (deeper than the app body — intentional).
  - accent glow: `radial-gradient(120% 90% at 50% 42%, color-mix(in oklab, var(--accent-mid) 16%, transparent), transparent 55%)`.
  - hairline frame: `position:absolute; inset:16px; border:1px solid rgba(241,236,223,0.05); border-radius:4px`.
  - centered flex column.
- **Brand frame** — a *double-square* motif (the app's signature mark):
  - outer box **440×232**, `border:1.5px solid rgba(241,236,223,0.85); border-radius:3px`.
  - inner box inset **8px**, `border:1px solid rgba(241,236,223,0.28); border-radius:2px`.
  - contents: centered column, `gap:18px`, `padding:0 40px`:
    - **Monogram** 52×52, `border-radius:13px`, bg `var(--accent-mid)` `#5b8df2`,
      text "LB" color `var(--accent-onMid)` `#0a0f1c`, `font-weight:800`,
      `font-size:~22px`, `box-shadow: 0 1px 0 rgba(255,255,255,.18) inset, 0 2px 8px rgba(0,0,0,.35)`.
    - **Wordmark** `font-size:38px`: "Lossless" `font-weight:500` color `rgba(241,236,223,.62)`
      + "Bob" `font-weight:700` color `rgba(241,236,223,.96)`; `letter-spacing:-0.84px`.
    - **Tagline** "Checksum Lookup": JetBrains Mono `11px`, uppercase,
      `letter-spacing:~3.1px`, color `rgba(241,236,223,.4)`.
- **Progress block** — `width:440px; margin-top:30px`:
  - **ProgressBar**: `height:3px`, track `rgba(241,236,223,.1)`, `border-radius:999px`.
    Fill `var(--accent-mid)`, `box-shadow:0 0 10px var(--accent-mid)`,
    `transition:width 120ms linear`. Indeterminate state = a 40%-wide bar sliding via
    `@keyframes lbbIndet { 0%{transform:translateX(-110%)} 100%{transform:translateX(290%)} }`, `1.15s` loop.
  - **Status row** (`space-between`, `margin-top:12px`, JetBrains Mono `11.5px`):
    - left, in progress: `{label}` color `rgba(241,236,223,.55)` + ` · {detail}` color `rgba(241,236,223,.32)`.
    - left, done: color `var(--ok-fg)` `#5db679`, text `Ready · 704,624 checksums`.
    - right: `{pct}%` color `rgba(241,236,223,.4)`, `font-variant-numeric:tabular-nums`; shows `…` when `overrun`.
- **Version footers** (mono `10.5px`, color `rgba(241,236,223,.3)`):
  - bottom-left @ `bottom:26px; left:30px`: `v1.2.0 · stable`.
  - bottom-right @ `bottom:26px; right:30px`: `build 2026.05.29`.
- **Replay hint** (mock only — drop in production): centered `bottom:22px`,
  `10.5px`, `rgba(241,236,223,.22)`, "click to replay".

---

## Screen 2 — About C · "Tabbed"
Source: `about-variants.jsx` → `AboutTabbed`, plus blocks in `about-parts.jsx`.
This is a modal dialog. In the mock it fills a 900×620 frame; in-app size it ~640–720px
wide, height to content (the body scrolls).

### Shell
- **Backdrop stage**: background `#131110` with a top glow
  `radial-gradient(120% 90% at 50% 0%, color-mix(in oklab, var(--accent-mid) 10%, transparent), transparent 50%)`, `padding:18px`.
- **Dialog card**: flex column, `background:var(--surface)` `#1d1c16`,
  `border:1px solid var(--border2)` `#4b463c`, `border-radius:12px`,
  `box-shadow:0 24px 70px rgba(0,0,0,.55)`, `overflow:hidden`.

### Header (compact)
Flex row, `align-items:center; gap:18px; padding:20px 22px; border-bottom:1px solid var(--border)` `#36332b`.
- Double-square frame **66×66** (inset 6, radius 10, outer stroke `rgba(241,236,223,.55)`,
  inner `rgba(241,236,223,.2)`) wrapping a **Monogram 42×42, radius 9**.
- Wordmark `28px` (color `var(--fg)` `#f1ecdf`). Below it a row (`gap:14px`):
  - **version pill** "v1.2.0": mono `11px`, `font-weight:600`, color `var(--accent-mid)`,
    `padding:2px 8px`, `border-radius:5px`, bg `var(--accent-soft)` `#1c2640`,
    `border:1px solid color-mix(in oklab, var(--accent-mid) 40%, transparent)`.
  - Tagline `9.5px`.
- **Close button** (right): 30×30, `border-radius:7px`, `border:1px solid var(--border)`,
  color `var(--fg2)`, an "x" icon at 14px. Wire to dialog close.

### Tab bar
Flex `gap:4px; padding:12px 22px 0; border-bottom:1px solid var(--border)`.
Four tabs; each is a button: inline-flex `gap:7px`, `padding:9px 14px 11px`,
transparent background, `font-size:12.5px`.
- active: `font-weight:600`, color `var(--fg)`, `border-bottom:2px solid var(--accent-mid)` (`margin-bottom:-1px` to sit on the bar line), icon tinted `var(--accent-mid)`.
- inactive: `font-weight:500`, color `var(--fg3)` `#756f60`, icon `var(--fg3)`.

| tab id  | label   | icon  |
|---------|---------|-------|
| about   | About   | info  |
| tech    | Tech    | setup |
| credits | Credits | user  |
| log     | Changes | lbdir |

### Body (scrolls) — `padding:22px 24px 26px`
- **About** — column `gap:24px`:
  - **Blurb** `<p>` `font-size:13px; line-height:1.7; color:var(--fg2)`:
    "A local-first tool for cataloguing, verifying and renaming a lossless live-recording
    collection against the master **LB** checksum database. 704,624 checksums indexed
    across 4 mounts." ("LB" bolded in `var(--fg)`.)
  - **Meta grid** 2-col, `gap:8px; row-gap:12px`, `padding:14px 16px`, `border-radius:9px`,
    bg `var(--surface2)` `#27251d`, `border:1px solid var(--border)`. Each meta = mono
    `11px`: key in `var(--fg3)`, value in `var(--fg2)` weight 600 (version value tinted `var(--accent-mid)`):
    `version 1.2.0 · stable` · `build 2026.05.29` · `database LB-16630` · `index 704,624`.
  - **Links** block: a "LINKS" block-title (uppercase `11px/700`, `var(--fg3)`, with a
    hairline rule) then a 2-col grid of link rows (icon tile + label + sub + reveal chevron).
- **Tech** — `TechStack`: four groups, each a mono `10px` uppercase `var(--accent-mid)`
  label over rows. Each row is a grid `120px 1fr auto`: name `var(--fg3)` `11.5px`,
  value `var(--fg)` `12.5px/500` (the **Electron + React + TypeScript** row gets a glowing
  `var(--accent-mid)` "primary target" dot), version mono `11px` `var(--fg2)` right-aligned.
  Groups + rows are data in `lbb-launch-data.js` → `stack`. Ends with an info-boxed
  architecture note (`arch`).
- **Credits** — `Acks`: stacked cards (icon tile + name + handle + note). The
  `tone:"memory"` entry (Robert Cook) gets the accent-tinted treatment + an "In memory"
  pill. Data: `acks`.
- **Changes** — `Changelog`: "v1.2.0 · May 29, 2026" then entries as a `74px 1fr` grid;
  the left cell is a colored uppercase tag (`new`=accent, `improved`=ok, `changed`=warn,
  `fixed`=fg3). Data: `changelog`.

### Footer
`padding:12px 26px; border-top:1px solid var(--border)`, mono `10.5px`, color `var(--fg3)`,
bg `var(--surface)`. Left: copyright `© 2024–2026 LosslessBob project · A community archival tool.`
Right: `DB LB-16630 · build 2026.05.29`.

---

## Interactions & Behavior
- **Splash**: auto-runs on launch. In production, dismiss/replace with the main window on
  the real "ready" event (the mock's click-to-replay is for demo only). Show indeterminate
  bar + `…` when `overrun`.
- **About tabs**: local state `tab` (default `"about"`); clicking a tab swaps the body.
  No animation required (instant swap in the mock). Close button dismisses the dialog.
- **Motion**: progress bar `transition: width 120ms linear`. Draw/scan animations belong
  to the *other* splash variants — not needed for A.

## State Management
- Splash: `{ elapsedMs, done }` from the boot pipeline → `useBoot` derives everything else.
- About: a single `tab` string. All content is static data (see `lbb-launch-data.js`).

## Design Tokens (dark mode, **indigo** accent — the shipped theme)
Resolved hex values (full system in `lbb-tokens.js`; theme = `{ mode:"dark", accent:"indigo", density:"default" }`):

| token | value | use |
|---|---|---|
| `--bg` | `#161510` | app body (note: splash/about stage uses a deeper `#131110`) |
| `--surface` | `#1d1c16` | dialog card |
| `--surface2` | `#27251d` | wells / meta grid |
| `--surface3` | `#34312a` | hover |
| `--border` | `#36332b` | hairlines |
| `--border2` | `#4b463c` | stronger borders |
| `--fg` | `#f1ecdf` | primary text (warm white) |
| `--fg2` | `#b6ad9a` | secondary |
| `--fg3` | `#756f60` | tertiary / labels |
| `--accent-mid` | `#5b8df2` | primary fill / monogram / progress |
| `--accent-hi` | `#7aa3f7` | hover |
| `--accent-lo` | `#3d72de` | pressed |
| `--accent-soft` | `#1c2640` | subtle accent bg (pills) |
| `--accent-onMid` | `#0a0f1c` | text on accent fill |
| `--ok-fg` | `#5db679` | "Ready" / success tag |
| `--warn-fg` | `#d4a35a` | "changed" tag |
| `--bad-fg` | `#e08070` | error |
| `--info-fg` | `#7eb4e8` | info |

The "warm white" strokes in the splash (`rgba(241,236,223,a)`) are just `--fg` `#f1ecdf`
at varying alpha — reuse the token with opacity.

**Typography**
- UI: **Inter** (400/500/600/700/800).
- Mono: **JetBrains Mono** (400/500/600) — taglines, version strings, progress status,
  tech versions, footer.

**Radii used**: 2, 3 (splash frame), 5 (pill), 7 (close btn), 9 (meta well / ack card),
10–13 (monogram), 12 (dialog), 999 (progress).

## Assets / Icons
No raster assets. Icons (`info`, `setup`, `user`, `lbdir`, `x`, `globe`, `link`, `star`,
`reveal`, `refresh`) come from the project's inline icon set in `lbb-icons.jsx`
(`window.LBB_Icon`, stroked, `size` prop). Map these to your codebase's existing icon
library — match the glyph meaning, not necessarily the exact path. The monogram is pure
CSS (text "LB" in a rounded accent square) — no asset needed.

## Files in this bundle
| file | role |
|---|---|
| `LosslessBob Splash & About.html` | runnable canvas of all variants (open this) |
| `lbb-launch-data.js` | **all content + the real boot sequence** (single source of truth) |
| `lbb-launch-parts.jsx` | `useBoot`, `ProgressBar` (incl. indeterminate), `DoubleSquareFrame`, `Monogram`, `Wordmark`, `Tagline` |
| `splash-variants.jsx` | `SplashClassic` = **the splash to build** (also B, C) |
| `about-parts.jsx` | About building blocks: header, tech stack, acks, changelog, links, footer |
| `about-variants.jsx` | `AboutTabbed` = **the About to build** (also A, B) |
| `lbb-tokens.js` | full design-token system + `applyTheme` |
| `lbb-icons.jsx` | inline icon set (`window.LBB_Icon`) |
| `design-canvas.jsx` | mock-only pan/zoom canvas — not part of the product |

Build target: **`SplashClassic`** + **`AboutTabbed`**. Everything else is reference.
