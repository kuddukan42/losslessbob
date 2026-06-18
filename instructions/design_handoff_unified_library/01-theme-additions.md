# 01 · Theme additions

The existing theme engine (`_source/lbb-tokens.js`) already ships **modes**
(light/dark), **8 accents**, and **3 density presets** — all documented in the
base bundle (`design_handoff_losslessbob/02-design-tokens.md`). This screen adds
**two new user-facing controls** and **refines the light palettes**. Nothing
else about the engine changes.

> **Themes screen, not just dev tweaks.** You have a real Themes panel in the
> app. These five controls belong there as persistent user settings:
> **Mode**, **Frame theme (palette)**, **Accent**, **Density**, **Card style**.
> In the prototype they also appear in the dev Tweaks panel for review — that
> panel is a design affordance, not the shipping surface.

---

## 1. Card style — framed vs. flat  ← new control

A single switch that toggles the whole Library between two separation styles:

| Value | Look | Mechanism |
|---|---|---|
| **framed** | Facet rail, table, and detail panel lift into elevated cards on a tinted gutter (ring + drop shadow + top highlight) | sets `data-sep="framed"` on `#frame` |
| **flat** (a.k.a. "flush") | The old style — surfaces sit flush, separated only by hairline borders | removes the `data-sep` attribute |

**This is pure CSS — no component logic.** The `--sep-*` token block already
lives in `_source/app.css`. Default tokens (no attribute) give the flat look;
`[data-sep="framed"]` overrides them. The framed shadow recipe adapts per mode
because **both** `data-mode` and `data-sep` are set on `#frame`:

```css
[data-sep="framed"] {
  --sep-body-gap: 12px;   --sep-body-pad: 14px;   --sep-radius: 12px;
  --sep-rail-bg / --sep-table-bg / --sep-detail-bg: var(--lbb-surface);
  --sep-ring: 0 0 0 1px var(--lbb-border);
  --sep-lift: 0 10px 28px rgba(0,0,0,0.22);   /* per-mode overridden below */
  --sep-top:  inset 0 1px 0 rgba(255,255,255,0.06);
  --sep-rail-shadow / --sep-table-shadow / --sep-detail-shadow:
      var(--sep-ring), var(--sep-lift), var(--sep-top);
}
#frame[data-mode="dark"]  [data-sep="framed"] { --sep-lift: 0 14px 34px rgba(0,0,0,0.52); --sep-top: inset 0 1px 0 rgba(255,255,255,0.07); }
#frame[data-mode="light"] [data-sep="framed"] { --sep-lift: 0 10px 26px rgba(40,30,15,0.14); --sep-top: inset 0 1px 0 rgba(255,255,255,0.85); }
```

The Library components read `var(--sep-rail-bg)`, `var(--sep-table-shadow)`,
`var(--sep-radius)`, etc. — they never hardcode the framed look. **Port the
token block verbatim**; wiring is just: set/remove one attribute.

```js
// on theme change:
frame.setAttribute("data-mode", mode);
if (cardStyle === "framed") frame.setAttribute("data-sep", "framed");
else                        frame.removeAttribute("data-sep");
```

**No shipped default is dictated.** The prototype previews `framed`; pick the
shipping default during review. Both are first-class.

---

## 2. Frame theme (palette)  ← new control

Five palettes that tint **the surfaces themselves** (gutter + cards + borders +
text), layered on top of the chosen mode. This is distinct from *accent*, which
only colors interactive highlights. Options:
**slate · blue · purple · green · graphite.**

```js
applyTheme({ mode, accent, density, palette });
// internally: const pal = PALETTES[mode][palette];
//             const m = pal ? { ...base, ...pal } : base;   // layered over mode
// sets data-palette on :root
```

A palette overrides the mode's `bg / surface / surface2 / surface3 / border /
border2 / fg / fg2 / fg3`. Framed cards (which read `--lbb-surface`) pick up the
tint automatically, which is what makes framed + palette feel cohesive.

### Dark palettes (unchanged — these are good as-is)

| Palette | bg | surface | surface2 | border | fg |
|---|---|---|---|---|---|
| **slate** | `#1b1f26` | `#252a33` | `#2f3540` | `#3b4250` | `#eef1f6` |
| **blue** | `#161d2b` | `#1f2738` | `#283248` | `#324162` | `#eef2fb` |
| **purple** | `#1f1a2b` | `#292338` | `#332b47` | `#413663` | `#f3eefb` |
| **green** | `#16201b` | `#1f2c25` | `#283930` | `#324a3b` | `#eef7f1` |
| **graphite** | `#17181b` | `#202227` | `#2a2d33` | `#383c44` | `#eef0f4` |

> Full per-palette values (incl. surface3 / border2 / fg2 / fg3) are in
> `_source/lbb-tokens.js` → `PALETTES.dark`.

### Light palettes — REFINED (the fix you asked for)

The previous light set read **washed-out**: `slate` light was `null` (it silently
fell back to warm cream, so "slate + light" looked like no palette at all), and
the others used pure-white cards on barely-tinted gutters, so cards didn't
separate and tints looked muddy. **Replaced.** Light now mirrors the dark hues
1:1, tuned so that:

- the **gutter (`bg`) carries a real tint** → framed cards visibly float;
- **cards (`surface`) are the lightest element**, faintly tinted (never stark `#fff`);
- `surface2/3` step down for wells + hover; **borders are visible hairlines**;
- `fg/fg2/fg3` carry a hint of the palette hue so text isn't dead neutral.

| Palette | bg (gutter) | surface (card) | surface2 | surface3 | border | border2 | fg | fg2 | fg3 |
|---|---|---|---|---|---|---|---|---|---|
| **slate** | `#e3e7ef` | `#f8f9fc` | `#e7ebf3` | `#dae0ec` | `#cdd5e2` | `#aab5c8` | `#191d26` | `#48515f` | `#76808f` |
| **blue** | `#dde7f6` | `#f6f9fe` | `#e3edfa` | `#d2e1f4` | `#c2d4ec` | `#9bb9e0` | `#13203a` | `#3f547a` | `#6f83a6` |
| **purple** | `#eae3f6` | `#faf8fe` | `#ebe2f7` | `#ddd0f1` | `#d4c6ec` | `#b9a2df` | `#1f1336` | `#534277` | `#8579a6` |
| **green** | `#deeae1` | `#f5faf7` | `#e2efe8` | `#d1e6da` | `#c5ddcf` | `#9fc7b1` | `#12281d` | `#3d5d4c` | `#739283` |
| **graphite** | `#e6e6eb` | `#fbfbfd` | `#ececf1` | `#e0e0e6` | `#d6d6dd` | `#b7b7c1` | `#18191d` | `#4f515a` | `#81838c` |

These are the literal values in `_source/lbb-tokens.js` → `PALETTES.light`.
`slate` is now authored (no longer `null`), so "slate + light" is a real,
neutral-cool light theme rather than a fallback.

> **Status colors are not touched.** `ok/warn/bad/info/mute` stay fixed across
> mode + palette (accessibility — green always means owned/pass). See base bundle.

---

## 3. The Themes panel — recommended layout

```
THEME
  Mode          ( light | dark )            ← segmented
  Frame theme   ( slate · blue · purple · green · graphite )   ← select/swatches
  Accent        ( indigo · plum · rust · forest · teal · amber · gray · crimson )
  Density       ( compact | default | comfortable )
  Card style    ( framed | flat )           ← segmented
```

**Persistence:** store all five in the same settings store the existing Themes
panel already uses; re-apply on boot **before** React mounts (call
`applyTheme(...)` and set `data-sep` in the same boot step). The prototype keeps
them in tweak state purely for live review; production reads/writes real settings.
