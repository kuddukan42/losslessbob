# 02 · Design Tokens

The full token system lives in `_source/lbb-tokens.js`. It's a small plain-JS module that takes `{mode, accent, density}` and writes ~40 CSS custom properties to `:root`. Copy its shape; replace the load mechanism with whatever your stack uses (CSS-in-JS, CSS modules, Tailwind config, etc.).

## Token surface

Every visual value in the app is one of these CSS variables:

### Mode tokens (`--lbb-*`)

Light and dark mode both define the same keys:

| Variable | Light | Dark | Use |
|---|---|---|---|
| `--lbb-bg` | `#faf8f3` | `#161510` | App body — warm cream / graphite |
| `--lbb-surface` | `#ffffff` | `#1d1c16` | Cards, sidebar, topbar, panels |
| `--lbb-surface2` | `#f1efe7` | `#27251d` | Table headers, subtle wells, secondary surfaces |
| `--lbb-surface3` | `#e7e4d8` | `#34312a` | Hover surfaces |
| `--lbb-border` | `#e2dfd2` | `#36332b` | Hairlines |
| `--lbb-border2` | `#c8c3b1` | `#4b463c` | Stronger borders (button outlines, separators) |
| `--lbb-fg` | `#1c1a17` | `#f1ecdf` | Primary text |
| `--lbb-fg2` | `#5b554a` | `#b6ad9a` | Secondary text |
| `--lbb-fg3` | `#8e8676` | `#756f60` | Tertiary text / placeholders / metadata |
| `--lbb-shadow` | `0 1px 0 rgba(0,0,0,0.02), 0 2px 6px rgba(40,30,15,0.06)` | dark-tuned | Card shadow |
| `--lbb-shadowLg` | larger version | larger version | Floating panel shadow |
| `--lbb-focusRing` | `0 0 0 3px rgba(0,0,0,0.08)` | white@12% | Focus outline |

The warm cream `#faf8f3` is essential — it differentiates LosslessBob from generic apps. Don't substitute pure white.

### Accent tokens (`--lbb-accent-*`)

Eight accent palettes, each tuned for both modes. Pick one (or let the user pick via Themes).

| Accent | Light mid | Dark mid |
|---|---|---|
| **indigo** (default) | `#2b5fd0` | `#5b8df2` |
| plum | `#7a3fb1` | `#b07cd9` |
| rust | `#a8462e` | `#d9784c` |
| forest | `#2a7a4a` | `#5db679` |
| teal | `#2b6f7c` | `#5ab0bc` |
| amber | `#9a6800` | `#d6a455` |
| gray | `#4a463e` | `#a59c89` |
| crimson | `#a31a35` | `#e26679` |

Each accent exposes 5 tones:
- `--lbb-accent-mid` — primary fill (button bg, active state)
- `--lbb-accent-hi` — hover
- `--lbb-accent-lo` — pressed
- `--lbb-accent-soft` — subtle bg (active row, selected chip)
- `--lbb-accent-onMid` — text color on top of `mid` (white in light, near-black in dark)

### Status tokens (`--lbb-{ok|warn|bad|info|mute}-{fg|bg|bar}`)

**Status colors stay fixed regardless of mode/accent** — green/amber/red must always mean the same thing for accessibility.

| Tone | Used for | Light fg / bg / bar | Dark fg / bg / bar |
|---|---|---|---|
| `ok` | Pass, done, owned | `#1f7a3e` / `#e7f2e2` / `#39a360` | `#5db679` / `#1f2d22` / `#39a360` |
| `warn` | Proposed, incomplete, attention | `#9a6800` / `#f8eed3` / `#cc9f3d` | `#d4a35a` / `#2e2719` / `#b58a3a` |
| `bad` | Fail, missing, mismatch | `#b03f30` / `#fbe6df` / `#d8604f` | `#e08070` / `#321f1d` / `#c25a48` |
| `info` | New, indexed, neutral-positive | `#1f5b8f` / `#e2ecf6` / `#4c89c4` | `#7eb4e8` / `#1b2733` / `#5891cf` |
| `mute` | Not started, n/a, disabled | `#8a8473` / `#ecebe4` / `#a8a293` | `#857d6b` / `#252320` / `#6e6759` |

- `fg` = text + icon color
- `bg` = soft tinted background wash (used for Pill backgrounds + row washes)
- `bar` = saturated indicator color (used for the 3px row-edge bar + status dots)

### Density tokens (`--lbb-d-*`)

| Variable | Compact | Default | Comfortable |
|---|---|---|---|
| `--lbb-d-row` | 24px | 32px | 40px |
| `--lbb-d-pad` | 6px | 8px | 12px |
| `--lbb-d-gap` | 4px | 6px | 10px |
| `--lbb-d-font` | 11.5px | 12.5px | 13.5px |
| `--lbb-d-sideRow` | 24px | 28px | 34px |

Every density-sensitive component reads `var(--lbb-d-*)`. Never hardcode row/padding values.

## Typography

| Family | Use | CSS |
|---|---|---|
| **Inter** | All UI text | Google Fonts: weights 400/500/600/700/800 |
| **JetBrains Mono** | All numbers, IDs (LB-numbers), file paths, dates, log output | Google Fonts: weights 400/500/600. Stored as `var(--lbb-mono)` |

The split is rigorous: anything that's a code-like identifier (LB#, paths, dates in `mm/dd/yy`, timestamps, sizes, counts) gets the mono family + `font-variant-numeric: tabular-nums`. Body labels, headings, button text — Inter.

### Type scale (used throughout)

| Use | Size | Weight | Where |
|---|---|---|---|
| Page H1 | 20–22px | 700 | Screen titles |
| Hero H1 | 28px | 700 | Home welcome strip |
| Section heading | 13px / uppercase / `letter-spacing: 0.04` | 700 | Card titles, side rail headers |
| Body | 12.5–13px | 400–500 | Most copy |
| Compact body | 11.5–12px | 400 | Table cells, dense panels |
| Table header (TH) | 10.5px / uppercase / 0.04 spacing | 600 | Column headers |
| Metadata / tertiary | 10.5–11px | 500 | Counts, "4 days ago", paths |
| Pill | 10.5px | 600 | Status pills |
| Keyboard hint | 10.5px mono | 500 | ⌘K, kbd-pill class |

Letter-spacing: H1/H2 use `letter-spacing: -0.01` (slight tighten). Uppercase section headings use positive `0.04–0.14`. Everything else default.

## Spacing rhythm

Roughly an 8-step modular scale, though the design uses precise pixel values rather than a strict scale. Common pads:
- Card content padding: 16–18px
- Screen top padding: 18–24px
- Toolbar padding: 10–14px vertical, 20–24px horizontal
- Card title padding: 12–14px vertical, 16–18px horizontal
- Gap between major cards in a grid: 14–18px
- Gap within a card: 6–12px

When in doubt, copy from the matching source file rather than inventing a value.

## Border radii

| Use | Radius |
|---|---|
| Buttons, inputs, table cells | **6px** |
| Cards, larger panels | **8px** |
| Hero / primary surfaces | **10–12px** |
| Pills, chips, status dots | **999px** (pill) |
| Keyboard hints, mini bars | **3–5px** |

## Theme application

Call `applyTheme({ mode, accent, density })` on app boot **before** React mounts. It sets all the variables on `:root` and also sets `data-mode`, `data-accent`, `data-density` attributes for CSS hooks. Persist the user's choice in localStorage; re-apply on every boot.

See `_source/lbb-tokens.js` for the canonical implementation.
