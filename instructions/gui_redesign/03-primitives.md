# 03 · Primitives

Source: `_source/lbb-ui.jsx`. ~10 components, all theme-aware via CSS variables. Build these first; every screen depends on them.

All primitives accept a `style` prop for one-off overrides. None should hardcode colors — everything reads `var(--lbb-*)`.

## Pill — status indicator

```jsx
<Pill tone="ok|warn|bad|info|mute" soft={bool} dot={bool}>Pass</Pill>
```

- Rounded (`border-radius: 999`), 10.5px font, 600 weight, 0.02em letter-spacing
- `soft={true}` → bg = `var(--lbb-{tone}-bg)`, no border. Default → transparent bg + colored border.
- `dot={true}` → prepends a 6×6 colored dot
- Padding `1px 7px`, line-height 1.45
- Color always = `var(--lbb-{tone}-fg)`

Used everywhere — every row status, every pipeline step result, every integration state.

## Chip — filter / tag

```jsx
<Chip active={bool} onClick={fn} count={42} icon="...">Label</Chip>
```

- Pill-shape, but bigger than Pill (3px 10px padding)
- Inactive: white bg, `border2` border, `fg2` text
- Active: `accent-soft` bg, `accent-mid` border + text, weight 600
- Optional `count` renders right-aligned, 60% opacity
- Optional `icon` renders left (12px)
- `size="sm"` variant (smaller padding, 11px font) for facet rails

## Button — 4 variants × 3 sizes

```jsx
<Button variant="primary|secondary|ghost|danger" size="sm|md|lg" icon="..." iconRight="..." block>Label</Button>
```

| Variant | Bg | Fg | Border | Hover bg |
|---|---|---|---|---|
| `primary` | `accent-mid` | `accent-onMid` | `accent-mid` | `accent-hi` |
| `secondary` | `surface` | `fg` | `border2` | `surface2` |
| `ghost` | transparent | `fg2` | transparent | `surface2` |
| `danger` | `surface` | `bad-fg` | `bad-fg` | `bad-bg` |

Sizes: heights 24/30/36, padX 8/12/14, font 11.5/12.5/13.5. All radius 6px, weight 600, gap 6px between icon + label. `block` = full width. Transition `background 120ms, border-color 120ms`.

## IconButton — square icon-only

```jsx
<IconButton icon="more" size={28} active={bool} title="..." />
```

Square, transparent default, `surface2` on hover or when `active`. Icon scales to `size * 0.55`.

## Input

```jsx
<Input icon="search" placeholder="..." value={v} onChange={fn} size="sm|md|lg" width={...} />
```

Heights 24/30/36. White bg, `border2` border, radius 6. Icon slot on the left (13px, `fg3` color). Transparent text input inside.

## Card

```jsx
<Card title="..." subtitle="..." action={<Button.../>} pad={16}>
  ...
</Card>
```

`surface` bg, `border` outline, radius 8, `var(--lbb-shadow)`. Optional title bar with bottom hairline. Default pad 16px.

## Toolbar

```jsx
<Toolbar bordered={true} pad="10px 14px">
  <Button.../> <Chip.../> ...
</Toolbar>
```

Horizontal action strip, flexbox with `gap: 8`, optional bottom border, `flex-wrap`.

## Table family

The single most important primitive group. Every screen has at least one of these.

```jsx
<TableShell stickyHeader={true}>
  <colgroup>
    <col style={{ width: 3 }} />     {/* ALWAYS — reserved for edge bar */}
    <col style={{ width: 100 }} />
    <col />
    ...
  </colgroup>
  <thead>
    <tr>
      <TH/>                          {/* empty header above edge bar */}
      <TH>LB#</TH>
      <TH align="right">Count</TH>
      ...
    </tr>
  </thead>
  <tbody>
    <GroupRow label="1980 · 18 results" count={18} expanded={true} colSpan={9} />
    <TR edge="ok" selected={bool} onClick={fn}>
      <TD mono>LB-12</TD>                {/* TR auto-injects the edge-bar TD */}
      <TD>Location text</TD>
      <TD mono dim>tertiary</TD>
      <TD align="right">42</TD>
    </TR>
  </tbody>
</TableShell>
```

### `<TableShell>`
- `border-collapse: separate`, `border-spacing: 0`, `table-layout: fixed`
- Font size = `var(--lbb-d-font)` so it responds to density
- Pass `stickyHeader` → adds class `lbb-sticky` → thead becomes `position: sticky; top: 0`

### `<TH>` — column header
- `padding: 8px var(--lbb-d-pad)`
- `font-size: 10.5px`, weight 600, `letter-spacing: 0.04`, uppercase
- Color: `fg3`. Bg: `surface2`. Bottom border: `border2`.
- Props: `align`, `width`, `style`

### `<TR>` — row
- Props: `edge="ok|warn|bad|info|mute"`, `selected`, `onClick`, `style`
- Renders an extra leading `<td>` that's 3px wide with `background: var(--lbb-{edge}-bar)`
- The whole row gets a subtle wash: `background: var(--lbb-{edge}-bg)`
- `selected={true}` overrides wash with `accent-soft`

### `<TD>` — cell
- `padding: calc(var(--lbb-d-pad) - 2px) var(--lbb-d-pad)`
- Default color `fg2`. Props:
  - `mono` → JetBrains Mono, 0.5px smaller
  - `dim` → color `fg3` instead of `fg2`
  - `align="left|center|right"`
  - `colSpan`
- `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` — cells truncate, the colgroup width controls column size

### `<GroupRow>` — section header inside a table

```jsx
<GroupRow label="Need attention" count={14} expanded={true} colSpan={8} onToggle={fn} />
```

A whole-table-width row that visually breaks the body into named sections. `surface2` bg, uppercase 11px label, left chevron toggles expanded state.

## Stat — big metric

```jsx
<Stat value="15,967" label="in My Collection" delta="+12" tone="ok" />
```

Big number (22px, 700, tabular-nums) over an 11.5px `fg3` label with an optional `Pill` delta.

## SectionHead — h3 inside a screen

```jsx
<SectionHead title="Recent activity" subtitle="last 7 days" action={<Button.../>} />
```

13px uppercase 700 letter-spaced title, optional 12px `fg3` subtitle, optional right-aligned action node.

## Banner — inline notification

```jsx
<Banner tone="info" icon="info" title="..." action={...}>Body copy</Banner>
```

Tinted bg by tone, icon left, optional title + action. Use sparingly — most state is conveyed by row edges and pills, not banners.

## Kbd / kbd-pill

For keyboard hints. The `.kbd-pill` class in `app.css` is the canonical version (small mono bg-tinted pill); the `<Kbd>` component is the JS equivalent.

## Icon

`<Icon name="..." size={16} stroke={1.5}>` — line icons with `currentColor` stroke. Names exhausted in `_source/lbb-icons.jsx`. Add new icons by adding paths to `LBB_ICON_PATHS` — Lucide-style 1.5px stroke, 24×24 viewBox.

**You may swap to Lucide-React** in production if it's already in the codebase — the icon set is intentionally Lucide-compatible.

## Things to delete from the prototype version

The reference file mixes some inline styles that should become real classes when porting to a styled-components / CSS modules / Tailwind setup. The `Object.assign(window, {...})` line at the bottom is the global-scope hack — replace with named exports.
