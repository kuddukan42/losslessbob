# 05 · Integration — adding the tab without breaking anything

The unified Library ships as a **new, additive tab.** Search and My Collection
**stay exactly as they are** and remain fully functional. Nothing about them
changes. This lets you build, dogfood, and validate the unified view in
production while the old tabs keep working — then retire them later in a
separate, deliberate step.

## Nav placement

Add **one** new nav item. Recommended: a "Library" item under a Library group,
sitting **above** the existing My Collection and Search items (so it's the
new default destination) without removing them:

```
Library
  • Library        ← NEW unified view (this handoff)   [featured]
  • My Collection  ← existing, untouched
  • Search         ← existing, untouched
  • Bootlegs       ← existing, untouched
```

> In the prototype `_source/libu-app.jsx` the `NAV` array shows the new item as
> `{ id: "library", label: "Library", icon: "library", featured: true }`. Keep
> the existing collection/search ids and routes intact — just add this one.

## What you are adding (file inventory)

| New file | Purpose |
|---|---|
| `libu-app.jsx` | The screen shell + view toggle + theme/settings wiring |
| `libu-performance.jsx`, `perf-parts.jsx` | "By performance" lens |
| `libu-recording.jsx`, `library-parts.jsx` | "By recording" lens |
| `libu-actions.jsx` | Shared action system (menu + panel workflows) |
| `perf-data.js`, `library-data.js` | Data adapters (replace sample with real fetch) |

## What you are MODIFYING (small, safe, isolated)

These touch shared files but are **additive / backward-compatible** — they don't
change any existing screen's behavior:

1. **`lbb-tokens.js`** — refined `PALETTES.light` values + `slate` light authored
   (§01). The existing light *default* (warm cream, used when no palette is set)
   is unchanged, so current screens look identical. New palettes only apply when
   a palette is selected.
2. **`app.css`** — the `--sep-*` framed-card block. Already present; inert unless
   `data-sep="framed"` is set on `#frame`. No effect on existing screens.
3. **`lbb-ui.jsx`** — `TR` now forwards `onContextMenu`. Purely additive — rows
   that don't pass it behave exactly as before.

> **Nothing is deleted or repointed.** Search/Collection keep their own files,
> routes, and data paths. If you reverted this tab tomorrow, the rest of the app
> would be byte-for-byte unaffected.

## Boot wiring

On app boot, before React mounts (the existing Themes settings flow already does
the first call — extend it with `palette` + the `data-sep` step):

```js
const s = loadThemeSettings(); // {mode, accent, density, palette, cardStyle}
LBB_TOKENS.applyTheme({ mode: s.mode, accent: s.accent, density: s.density, palette: s.palette });
const frame = document.getElementById("frame");
frame.setAttribute("data-mode", s.mode);
if (s.cardStyle === "framed") frame.setAttribute("data-sep", "framed");
else                          frame.removeAttribute("data-sep");
```

## Data wiring order (matches §00 build order)

1. Point `library-data.js`'s adapter at the real owned-recordings + master-DB
   source → the **By recording** lens goes live (this is also the no-families
   fallback, §03).
2. Point `perf-data.js`'s adapter at the show + recordings source. With **no
   `fams`**, the **By performance** lens already works (flat nested rows).
3. When TapeMatch ships `fams`, the family grouping lights up automatically — no
   UI change needed (§03).
4. Wire the action handlers (§04 Part B) and the status/facet counts (§04 Part A).

## Retirement (later, out of scope)

Once the unified Library is validated in production, retiring Search + My
Collection is a separate task: remove their nav items + routes, redirect any
deep links to the new Library with the matching lens preselected. **Not part of
this handoff** — listed only so the path is clear.
