# Handoff: LosslessBob Pipeline Stage Icons

## Overview
A set of five **pipeline stage icons** for LosslessBob's processing tracker. Each icon is a tactile, rounded "tile" carrying a line glyph, tinted by the stage's current run status. When a stage is actively processing it plays a **Pulse** animation (a double expanding ring + a sheen sweep). The five stages, in pipeline order, are **Verify → Lookup → Rename → LBDIR → Collect**.

This is the locked direction chosen after exploration:
- **Icon style:** Option D — tactile tile (radial-gradient fill, inset highlight, raised drop shadow)
- **Running animation:** Pulse (double ripple + diagonal sheen)
- **Palette:** Vivid

## About the Design Files
The files in this bundle are **design references created in HTML/React** — a prototype showing the intended look and behavior, **not production code to ship as-is**. The task is to **recreate these designs in your app's existing environment** (React, Vue, SwiftUI, native, etc.) using its established component and styling patterns. If the project has no front-end environment yet, choose the most appropriate framework and implement there.

`PipelineIcon.jsx` and `pipeline-icons.css` are written to be very close to drop-in for a React + plain-CSS stack, and can be lifted nearly verbatim. Treat them as a precise spec even if your stack differs — the CSS values (gradients, shadows, keyframes, timings) are the source of truth.

## Fidelity
**High-fidelity (hifi).** Final colors, geometry, shadows, radii, and animation timings. Recreate pixel-for-pixel using the values documented here and in the CSS.

## The Icon Component

### Props
| Prop | Type | Default | Notes |
|------|------|---------|-------|
| `stage` | `"verify" \| "lookup" \| "rename" \| "lbdir" \| "collect"` | — | Which glyph |
| `status` | `"pending" \| "running" \| "pass" \| "action" \| "blocked"` | `"pending"` | Drives tile color + animation |
| `size` | number (px) | `48` | Tile is `size`×`size`; glyph scales to `round(size*0.56)` |

### Behavior by status
- **pending** — Pending color, tile rendered at **0.5 opacity** (dimmed, not-yet-reached)
- **running** — Running blue, **Pulse animation active** (rings + sheen)
- **pass / action / blocked** — solid status color, no animation (resolved state)

Only the `running` state renders the animation layers (`.pipe-tile__ring` ×2 and `.pipe-tile__sheen`). All other states are static.

## Geometry & Construction

### Tile
- **Shape:** square, `border-radius: size * 0.30` (e.g. 48px tile → ~14px radius)
- **Fill:** `radial-gradient(118% 118% at 50% 16%, HI 0%, MID 54%, LO 100%)`
  - `MID` = the status color (see palette)
  - `HI`  = `color-mix(in oklab, MID 74%, #fff)` (lighter, top)
  - `LO`  = `color-mix(in oklab, MID 82%, #000)` (darker, bottom)
- **Border:** `1px solid LO`
- **Shadow (raised):**
  ```
  0 4px 9px color-mix(in oklab, MID 40%, transparent),
  0 1px 2px rgba(40,34,24,0.12),
  inset 0 1.5px 0.5px rgba(255,255,255,0.6),
  inset 0 -2px 2px rgba(0,0,0,0.18)
  ```
  The two inset shadows (bright top edge, dark bottom edge) create the tactile bevel; the two outer shadows lift it off the surface.

### Glyph
- 24×24 viewBox, `fill: none`, `stroke: #fff`, `stroke-width: 1.85`, round caps + joins
- Rendered at `round(size * 0.56)` px, centered, `z-index: 1` above animation layers
- Exact path data is in `PipelineIcon.jsx` (`PIPE_GLYPHS`). The glyphs: Verify = shield + check, Lookup = magnifier over text lines, Rename = price tag + hole, LBDIR = document with folded corner + lines, Collect = open box with slot.

## The Pulse Animation
Active only on `status="running"`. Three layers behind the glyph:

1. **Ring A** — `box-shadow` ring expanding `0 → 22px` spread while fading `opacity 1 → 0`
2. **Ring B** — identical, `animation-delay: 0.55s` (staggered second ripple)
3. **Sheen** — a 115° white gradient band sweeping left→right across the tile

```
@keyframes pipeRing  { 0% { box-shadow:0 0 0 0 GLOW; opacity:1 } 70%,100% { box-shadow:0 0 0 22px transparent; opacity:0 } }
@keyframes pipeSheen { 0% { transform:translateX(-120%) } 55%,100% { transform:translateX(120%) } }

ring:  pipeRing  1.2s ease-out infinite   (ring B delayed 0.55s)
sheen: pipeSheen 1.7s ease-in-out infinite
```
- `GLOW` = `color-mix(in oklab, MID 92%, transparent)`
- The sheen rides inside an `overflow:hidden` clip with the tile's border-radius.
- **All animation is wrapped in `@media (prefers-reduced-motion: no-preference)`** — reduced-motion users see a static running tile. Preserve this.

## Design Tokens

### Vivid status palette (the `MID` colors)
| Status | Hex | Usage |
|--------|-----|-------|
| Pending | `#a8a293` | tile @ 0.5 opacity |
| Running | `#4c89c4` | + Pulse animation |
| Pass | `#39a360` | resolved OK |
| Action | `#cc9f3d` | needs attention |
| Blocked | `#d8604f` | failed / blocked |

All other tile shades (highlight, shadow, glow) are **derived** from these via `color-mix(in oklab, …)` — do not hardcode them; compute from the mid color so the system stays consistent if a status hue is ever retuned. If your platform lacks `color-mix`, precompute the derived hex values per status.

> A **Muted** palette also exists (Running `#6e8aa6`, Pass `#6a9b78`, Action `#c0a064`, Blocked `#bd7a6e`, Pending unchanged). Vivid is the chosen default; Muted is documented only as a fallback if the team later finds Vivid too saturated in dense lists.

### Scale
- `border-radius` = `size * 0.30`
- glyph = `size * 0.56`
- recommended sizes: 24 (list rows), 32–40 (default UI), 48 (cards), 64–88 (hero/empty states)

### Animation timing
- Ring: `1.2s ease-out`, infinite, second ring `+0.55s` delay
- Sheen: `1.7s ease-in-out`, infinite

## Files in this bundle
| File | What it is |
|------|-----------|
| `pipeline-icons.css` | All visual + animation CSS. Tile shell, status modifiers, Pulse keyframes. The source of truth for values. |
| `PipelineIcon.jsx` | Production React component + glyph path data + stage metadata (`PIPELINE_STAGES`). |
| `Pipeline Icons — Pulse Vivid.html` | Visual reference. Open in a browser to see every stage × state and all sizes rendering live, driven by the two files above. |

## Integration notes
- `PipelineIcon.jsx` ends with a commented `export {…}` — uncomment for an ES-module build, or wire up however your project imports components.
- The component has **no dependencies** beyond React + the CSS file.
- To port to a non-React stack: the markup per icon is a `<span class="pipe-tile pipe-tile--{status}">` containing (only when running) two `.pipe-tile__ring` spans + a `.pipe-tile__sheen-clip > .pipe-tile__sheen`, then a `.pipe-tile__glyph` span wrapping the inline SVG. Set `--pipe-size` inline. Everything else is CSS.
- These are original geometric glyphs — no external icon library or licensed assets required.
