# Handoff: "Complete against LB" — coverage award screen

## Overview
A milestone screen shown when the user's collection holds **every entry in the current Lossless Bob (LB) catalogue snapshot**. It is a celebration surface *and* a live status surface: LB publishes updates most months (typically 20–30 new entries, no fixed day), so "complete" is a state the collection can enter, leave, and re-enter. The screen must never read as "finished forever."

Design reference: `Archive Complete - Award Screen v2.html` (in this bundle).

## About the design files
The HTML in this bundle is a **design reference** — a static prototype of look and behavior, written outside the app's build. Do not ship it. Recreate it inside the existing LosslessBob React app using the established patterns:

- `lbb-tokens.js` — theme tokens (`window.LBB_TOKENS.applyTheme({mode, accent, density})`), which write `--lbb-*` CSS custom properties.
- `lbb-ui.jsx` — shared primitives (buttons, pills, cards).
- `lbb-icons.jsx` — `window.LBB_Icon` (`<Icon name size />`).
- `app-shell.jsx` — `window.LBB_AppShell` (sidebar + topbar + status footer, 1920×1080 frame).

**Important:** the prototype was drawn with its own hard-coded dark palette. It must be re-expressed in `--lbb-*` tokens so it works in light mode, dark mode, all eight accents, and all frame palettes. The token mapping table below is normative — where the prototype's hex and the token disagree, **the token wins**.

## Fidelity
**High-fidelity.** Layout, type scale, spacing, and copy are final. Colors are final *as token references*, not as the literal hexes in the prototype.

---

## 1. Where this lives (routes)

The app is a sidebar-nav SPA; `app-shell.jsx` drives navigation by string id (`home`, `pipeline`, `verify`, `lookup`, `tapematch`, `rename`, `lbdir`, `collection`, `search`, `bootlegs`, `attachments`, `spectrograms`, `map`, `dbeditor`, `scraper`, `setup`, `themes`). Add the following:

**Placement decision:** this is *not* a sidebar destination and *not* a home-screen card. It is a **progress screen reached from the About page**, and it only puts on the award treatment once coverage hits 100%. Until then it is a quiet "how far along am I" page the user goes looking for — never something the app pushes at them.

| Route | Nav id | Purpose | Entry points |
|---|---|---|---|
| `/about/coverage` | — (About sub-view) | **The progress / award screen.** One route, one component; the award treatment is a state of it, not a separate screen. | About page → "Collection progress" row (primary and, until 100%, only entry point) |
| `/lbdir/ledger` | `lbdir` | Full per-entry ledger: every LB#, its match state, source family, resolution note, date filed | "View full ledger" button; deep-link from any LB# |
| `/lbdir/sync` | `lbdir` | LB catalogue sync — history of snapshots, diff per update, manual pull | "Sync with LB now"; settings |
| `/about/coverage/certificate` | modal over the screen | Export preview + format/scope options, then download | "Export certificate" — only exists at 100% |

Deep-linking: all four must be addressable by URL and restorable on reload (the award state is a thing people screenshot and share; a dead link is a bug).

### Touch points elsewhere in the app
1. **About page** — the entry point. Add a row/card: "Collection progress" with the coverage percentage (`98.4%`) or, at 100%, a small gold seal and "Complete against LB 2026.08". Clicking opens `/about/coverage`. This row is always present, in every state.
2. **TapeMatch** (`screen-tapematch.jsx`) — when a curation session resolves the *last* unmatched LB entry, the completion state offers "See the whole collection" → `/about/coverage`. This is the one moment the app volunteers the screen, because the user just earned it.
3. **Sync completion toast** — **only** when a sync moves coverage *to* 100%: "Complete against LB 2026.09" with "View". Routine syncs that add entries do not toast the award screen; they toast into TapeMatch as normal work.
4. **Notifications bell** — coverage-change events land in the notification list (see event log below), including the drop from 100% when a new update lands.
5. **Settings / Setup** — LB sync cadence, auto-sync on/off, notify-on-new-entries toggle, credentials/source URL for the LB catalogue.

**Deliberately not touch points:** no sidebar nav item, no sidebar badge, no status-footer coverage chip, no home-screen card. The screen is opt-in.

If you later want a permanent surface, the status-footer chip is the least intrusive option — but ship without it first.

---

## 2. Screen: `/about/coverage` (complete state — the award)

### Layout
Rendered inside `AppShell` (crumbs: `LosslessBob / About / Collection progress`), so the content area is 1696×1000 at the 1920×1080 frame. The prototype frame is 1280×800; treat it as **scalable, centered content, max-width 1180px**, not a fixed canvas.

Content column (the "certificate" card):
- Card inset from the content area: `56px` top, `150px` left/right (or `max-width:1180px; margin:0 auto`), `94px` bottom reserved for the action row.
- Card: `1px` border in gold at 32% opacity over surface, radius `6px`, background `linear-gradient(180deg, var(--lbb-surface), var(--lbb-bg))`, padding `38px 56px 30px`.
- Inner hairline: `::before`, `inset:7px`, `1px solid` gold at 14%, radius `3px`.
- Flex column, `align-items:center`, `text-align:center`.
- Ambient glow behind the card: radial gradient, gold at 13% alpha, `inset:-30% 20% 50%`, `pointer-events:none`. **Dark mode only** — suppress in light mode (use `--lbb-shadowLg` instead).

Vertical stack, in order:

| # | Element | Spec |
|---|---|---|
| 1 | **Seal** | 88×88 circle. Border `1px` gold @45%. Background `radial-gradient(70% 70% at 50% 30%, #2a2314, var(--lbb-surface))` (dark) / gold-soft wash (light). Inner `1px dashed` gold @35% ring at `inset:7px`. Glyph: check, mono 25px 700, gold. Use `<Icon name="shield" />` or a check icon from `lbb-icons.jsx` rather than a text character. |
| 2 | **Eyebrow** | `margin-top:16px`. Inter 700 / 10.5px / `letter-spacing:.14em` / uppercase / `--lbb-fg3`. Copy: **"Complete against LB 2026.08"** — the snapshot label is data, format `LB YYYY.MM`. |
| 3 | **Headline** | `margin-top:20px`. Inter 800 / 42px / line-height 1.05 / `letter-spacing:-.025em` / `--lbb-fg`. Copy: **"Every LB entry, collected."** |
| 4 | **Subhead** | `margin-top:11px`, `max-width:660px`. Inter 400 / 14.5px / 1.55 / `--lbb-fg2` / `text-wrap:pretty`. Copy: *"As of the August update, every date in the Lossless Bob catalogue is in your archive, matched to a source family and verified. Nothing missing, nothing unresolved — and the archive stays open for whatever surfaces next."* Month name is interpolated from the snapshot. |
| 5 | **Rule** | Full width, 1px, `linear-gradient(90deg, transparent, var(--lbb-border2), transparent)`, margin `26px 0 20px`. |
| 6 | **Stat row** | 4-col grid, `gap:2px`. Each cell: `padding:13px 8px`, background `--lbb-surface2`, `1px solid --lbb-border`. Value: mono 600 / 22px / tabular-nums / `letter-spacing:-.01em`. Label: Inter 600 / 10px / `.1em` / uppercase / `--lbb-fg3`. Cells: **LB entries held**, **recordings**, **families**, **entries missing**. The last is `0` and takes `--lbb-ok-fg` when zero. |
| 7 | **Era bars** | 7-col grid, `gap:6px`. Each: 5px-tall bar, radius 3px, `linear-gradient(90deg, gold-dark, gold)`, with a mono 600 / 9.5px `--lbb-fg3` decade label below (`60s`…`20s`). **Fill each bar proportionally to that decade's coverage** — full gold at 100%, partial fill over `--lbb-surface2` otherwise. In the prototype they are all full. |
| 8 | **Live strip** | `margin-top:22px`, full width, `padding:12px 16px`, `1px solid --lbb-border`, radius 7px, background `--lbb-surface`, flex row, `gap:14px`, left-aligned text. Contains: 8px `--lbb-ok-bar` dot with a pulsing ring (see Motion); body Inter 13px `--lbb-fg2` with bolded lead — *"**Watching LB for the next update.** They land most months, usually 20–30 entries — the last batch was 26, all matched and filed within 6 days."*; right-aligned mono 11px `--lbb-fg3` two-liner — *"last checked 2026-08-11 · 03:41"* / *"updates arrive monthly, no fixed day"*. |
| 9 | **Signature row** | `margin-top:auto`, `padding-top:22px`, space-between, mono 11px/1.6 `--lbb-fg3`; first line per column in `--lbb-fg2` 500. Left: *"Caught up 2026-08-11"* / *"first entry filed 2024-02-19 · 906 days · 412 sessions"*. Right (right-aligned): *"ledger sha256"* / *"4f9c…a17e · signed by lbdir v2.4.1"*. |
| 10 | **Action row** | Absolute bottom, centered, `gap:10px`, `padding-bottom:20px`. Buttons: **Export certificate** (gold fill), **Sync with LB now** (default), **View full ledger** (ghost). |

### Button specs
All `radius:6px`, `padding:8px 15px`, Inter 600 / 12px.
- Gold: background + border gold, text `#1a1408` (`--lbb-accent-onMid` when accent = amber). Hover: gold-hi. Active: gold-lo.
- Default: background `--lbb-surface2`, border `--lbb-border2`, text `--lbb-fg`. Hover: `--lbb-surface3`.
- Ghost: transparent, no border, `--lbb-fg2`. Hover: `--lbb-surface2`, `--lbb-fg`.
- Focus (all): `box-shadow: var(--lbb-focusRing)`.

---

## 3. Screen: `/about/coverage` (incomplete state — the default)

**This is the state the screen spends most of its life in, and the one to build first.** Same route, same component, different treatment. It should feel like an honest progress page, not a withheld trophy — no locked/greyed award, no "keep going!" nagging:

- No gold: card border `--lbb-border`, no glow, no seal. Replace the seal with a **coverage ring** — a circular progress indicator showing the percentage (mono 20px in the center).
- Eyebrow: `"LB 2026.09 · 26 entries outstanding"`.
- Headline: `"26 new entries to chase."` (`n === 1` → `"One new entry to chase."`)
- Subhead: what arrived and where it came from, e.g. *"The September update added 26 dates. 12 are already matched from tapes you hold; 14 aren't in the archive yet."*
- Stat row labels stay identical; **entries missing** takes `--lbb-warn-fg` when > 0.
- Era bars show partial fills — this is where they earn their place.
- Live strip becomes a work strip: *"Newest entries queued for matching"* + "Open in TapeMatch" link.
- Actions: **Open in TapeMatch** (accent-primary), **Sync with LB now**, **View full ledger**. No export while incomplete.

Third state — **never-complete / first run**: same layout, coverage ring from real data, headline `"78% of the LB catalogue, collected."` No award language until 100% is first reached.

---

## 4. Data

### Model
```
LBSnapshot     { id, label: "2026.08", published_at, entry_count, source_url, fetched_at, checksum }
LBEntry        { lb_id, date, venue, city, snapshot_first_seen, retired_at? }
CoverageState  { snapshot_id, entries_total, entries_held, entries_missing,
                 recordings, families, coverage_pct, by_decade: [{decade, total, held}],
                 complete_since?, ledger_sha256, signed_by: "lbdir v2.4.1" }
CoverageEvent  { type: "snapshot_ingested" | "coverage_complete" | "coverage_broken" |
                        "entries_matched", at, snapshot_id, delta, note }
CurationStats  { first_entry_filed_at, sessions, days_active, conflicts_resolved, tb_verified }
```

### Endpoints (or IPC calls, if this stays local-first)
| Call | Returns |
|---|---|
| `GET /api/lb/coverage` | current `CoverageState` + `CurationStats` — everything the screen renders |
| `GET /api/lb/coverage/ledger?page=&filter=` | paginated `LBEntry` rows with match state |
| `POST /api/lb/sync` | kicks a sync; returns job id. Poll or stream progress |
| `GET /api/lb/snapshots` | snapshot history with per-update diffs |
| `GET /api/lb/events?limit=` | `CoverageEvent` log — feeds the bell and the "last batch" copy |
| `POST /api/lb/certificate` | `{ format: "png" \| "pdf", scope }` → rendered file |

### Numbers are computed, never hard-coded
Every figure in the prototype is placeholder. **They also contradict the shipping app's own status bar** (`DB: LB-16630`, `Checksums: 704,624`, `My Collection 15,967`, `Bootlegs 1,380`), which implies an LB catalogue an order of magnitude larger than the prototype's 2,075. Resolve against the real DB before building — and confirm which unit "LB entries" counts (LB# rows vs. distinct dates), because the headline copy depends on it. The layout is designed to hold 5-digit numbers without reflow.

Derived values:
- `coverage_pct = entries_held / entries_total`
- `complete = entries_missing === 0`
- `days = today - first_entry_filed_at`
- "last batch was 26, all matched and filed within 6 days" — from the most recent `snapshot_ingested` event and the time to the `entries_matched` event that cleared it. If the last batch isn't cleared yet, the copy changes (see incomplete state).
- `ledger_sha256` — hash over the sorted set of `(lb_id, family_id, resolution)` triples. Recomputed on every coverage change; displayed truncated `first4…last4`.

---

## 5. Behavior

### Sync
- Background check on the configured cadence (default: daily poll; LB publishes monthly, no fixed day) plus on app launch if the last check is older than 24h.
- "Sync with LB now" → button enters loading state (spinner in place of label text, disabled, `aria-busy`), fetch snapshot, diff against local, write new `LBEntry` rows, recompute coverage, emit events.
- On completion: toast + screen re-render. If coverage dropped from 100%, the screen **animates from the gold state to the incomplete state** rather than hard-swapping — the gold recedes, the ring appears. That transition is the whole point of the design.
- Failure: inline error strip in place of the live strip, `--lbb-bad-*` tokens, with retry and last-successful-check time. Never blank the screen on a failed sync.

### Count-up
On mount, all four stats and any hero numeral animate from 0 to value: 1400ms, ease-out cubic (`1-(1-p)³`), `requestAnimationFrame`, `toLocaleString('en-US')` formatting, tabular-nums so nothing jitters. **Clicking anywhere on the screen replays the count-up** (the user asked for this explicitly — keep it). Respect `prefers-reduced-motion: reduce` → render final values immediately, no replay animation.

### Pulse
Live-strip dot: `::after` ring, `2.4s ease-out infinite`, `scale(.6)→scale(1.5)`, opacity `.6→0`. Suppressed under `prefers-reduced-motion`.

### First-time celebration
The first time coverage hits 100% for a given snapshot, entering the route plays a one-off entrance: card fades/rises 12px over 420ms, seal scales in 200ms later, glow ramps over 800ms. Store `celebrated_snapshot_ids` locally so it plays once per milestone, not every visit.

### Export certificate
Opens a modal: format (PNG / PDF), and whether to include the signature block. Renders server-side or via canvas at 2× from the same component with chrome hidden. Filename `losslessbob-complete-LB-2026.08.png`. If the app is offline-only, render client-side.

---

## 6. State
```
coverage        : CoverageState | null      // null → skeleton
stats           : CurationStats | null
loading         : boolean                    // initial fetch
syncing         : boolean                    // manual sync in flight
syncError       : string | null
exportOpen      : boolean
countKey        : number                     // increment to replay count-up
celebrated      : Set<snapshot_id>           // persisted locally
```
Transitions: `mount → loading → coverage` · `sync click → syncing → (coverage | syncError)` · `coverage.complete false→true → celebration` · `true→false → recede transition` · `screen click → countKey++`.

Loading: skeleton card with shimmer blocks in the stat/era positions — never a spinner over an empty frame.

---

## 7. Design tokens

| Prototype hex | Token | Notes |
|---|---|---|
| `#0c1017` bg | `--lbb-bg` | |
| `#131822` | `--lbb-surface` | |
| `#1a2130` | `--lbb-surface2` | |
| `#232b3a` | `--lbb-border` | |
| `#33405a` | `--lbb-border2` | |
| `#e6e9f0` | `--lbb-fg` | |
| `#9aa5b5` | `--lbb-fg2` | |
| `#5f6b7d` | `--lbb-fg3` | |
| `#5db679` / `#39a360` / `#16241b` | `--lbb-ok-fg` / `--lbb-ok-bar` / `--lbb-ok-bg` | |
| `#d4a35a` | `--lbb-warn-fg` | incomplete-state accents |
| `#5b8df2` | `--lbb-accent-mid` | |
| `#d9b26a` **gold** | **new token: `--lbb-award`** | Add an award ramp to `lbb-tokens.js`, fixed across accents so the milestone reads the same in every theme: dark `mid:#d9b26a hi:#e6c689 lo:#b8924f soft:#241d10 on:#1a1408`; light `mid:#9a6800 hi:#ad7400 lo:#7d5200 soft:#f7ead0 on:#ffffff`. Reuse the amber accent ramp if adding a token is unwelcome. |

Type: Inter 400/500/600/700/800 + JetBrains Mono 400/500/600/700 (already loaded app-wide). Scale used here: 42 / 22 / 14.5 / 13 / 12 / 11 / 10.5 / 10 / 9.5.
Spacing: 2 / 5 / 6 / 7 / 10 / 11 / 13 / 14 / 16 / 20 / 22 / 26 / 30 / 38 / 56.
Radii: 3 / 5 / 6 / 7 / 50%. Shadows: `--lbb-shadow`, `--lbb-shadowLg`. Focus: `--lbb-focusRing`.

## 8. Accessibility
- The screen is a live region for coverage changes (`aria-live="polite"` on the stat row).
- Count-up must not be the only way a number is announced — set the final value as `aria-label` on each stat immediately.
- Click-to-replay is a nicety, not a control: bind it to the card with `pointer-events` care so it never swallows button clicks, and don't make it keyboard-focusable.
- Era bars need text alternatives (`<span class="sr-only">1980s: 100% covered</span>`).
- Contrast: gold on dark surface passes at 14px+ 600 weight; do not use `--lbb-award` for body copy in light mode.

## 9. Responsive
- ≥1440px content: as specified.
- 1100–1440px: card `margin:0 32px`; headline 36px; stat row stays 4-up.
- <1100px: stat row 2×2; era bars wrap to two rows of 4/3; signature row stacks; actions become full-width stacked buttons.
- <700px (mobile shell, see `m-app.jsx`): single column, seal 64px, headline 28px, live strip stacks with the timestamp below the copy.

## 10. Assets
None. The seal is CSS + one check icon from `lbb-icons.jsx`. No images, no illustration. Fonts are the app's existing Google Fonts load.

## 11. Files in this bundle
- `Archive Complete - Award Screen v2.html` — the refined design reference (the one to build).
- `Archive Complete - Award Screens.html` — earlier exploration, three directions (A certificate / B mosaic / C ledger). **A is the chosen one**; B's coverage mosaic is a good candidate for the ledger route later, C is superseded.
- `screenshots/01-complete-against-lb.png` — the complete state as rendered.
- `screenshots/02-explorations.png` — the three original directions side by side, for context.

## 12. Open questions for the product owner
1. Real catalogue scale — 2,075 or ~16,630? Determines type sizes for the stat row.
2. Is "LB entries" LB# rows or distinct dates?
3. Does the certificate export need to be verifiable by a third party (signed hash the user can post), or is it decorative?
4. Should losing 100% coverage clear the award, or should the app keep a permanent "was complete against LB 2026.08" badge in history?
