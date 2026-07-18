# FABLE spec — Command palette, Ctrl+K (FABLE_IDEAS UI §1)

Written 2026-07-17 (Fable 5). Expands FABLE_IDEAS.md UI idea 1 into a handoff spec.
Audience: **sonnet implementation sessions** — every bite states exact accept
criteria; when reality diverges from a stated fact below, stop and re-verify before
improvising.

One fuzzy-search box that does everything: type an LB number, a date, a venue, a
screen name, or an action, and jump straight there. Users of this app think in LB
numbers and dates — the palette collapses most navigation to two keystrokes, and
gives every future spec a place to register actions without new menu real estate.

**What this is NOT:** no new npm deps (no cmdk/kbar — the component is ~200 lines
in-house), no backend changes (existing `GET /api/search` only), no job-triggering
actions with progress UI in v1 (SSE actions like recompute wait for the activity
center — see D4), no changes to sidebar behavior.

---

## 1. Verified facts (2026-07-17 — trust these, re-verify only on contradiction)

- GUI: React + `HashRouter`; routes in `gui_next/src/renderer/src/App.tsx`
  (lines ~261–279): `/` home, `/quicklookup`, `/library`, `/tapematch`, `/songs`,
  `/collection`, `/trading`, `/sharing`, `/search`, `/bootlegs`, `/attachments`,
  `/spectrograms`, `/map`, `/dbeditor`, `/scraper` + `/fingerprint` (both wrapped
  in `CuratorRoute`), `/setup`, `/mounts`, `/themes`. `/pipeline` is special:
  always mounted, shown/hidden via `display` toggle at App.tsx ~line 238 —
  navigation to it is still an ordinary pathname change.
- Sidebar: `components/AppShell.tsx` defines `NAV_GROUPS: NavGroup[]` (~line 39)
  with i18n label keys (`appShell.nav.*`) and `gatedGroup` flags — gated groups
  render only when `curatorMode` (from `useSettingsStore`) is true. **This array
  is the single source of truth for screens — the palette must consume it, not
  duplicate it** (B1 extracts it to a shared module).
- No global keyboard shortcuts exist yet (no `ctrlKey` handling in AppShell/App).
  `AboutDialog.tsx` (~line 577) has the repo's existing Escape-key + dialog
  pattern; `components/pipeline/ConfirmDialog.tsx` and `primitives.tsx` show the
  house modal/overlay style — match them, don't invent a new look.
- `GET /api/search?q=&field=&year=` (backend/app.py ~1187) returns a JSON list of
  entry dicts — the GUI already sorts client-side. Fine for top-N palette results.
- `ScreenLibrary.tsx` honors a `?lb=<number>` search param (reads `searchParams`,
  scrolls/selects the row) — the verified deep-link target for LB jumps.
- i18n: `react-i18next`, keys in `locales/en.json`; `/gui-next-i18n` translates
  de/fr/es/it/nl at close.
- Verification: `/gui-check` (typecheck + build) only — **no screenshots, no
  browser automation**; tj verifies visuals.
- `GET /api/flat_file/discover` returns `{available, current_release,
  last_applied_release, error}` synchronously — the one safe "real action" for
  v1. `POST /api/derived/recompute` is SSE with per-step progress — explicitly
  NOT a v1 palette action (D4).

---

## 2. Target design

### D1 — Shared navigation registry (refactor, zero behavior change)

Move `NAV_GROUPS` (types + array + gating semantics) from `AppShell.tsx` into
`lib/navigation.ts`; AppShell imports it. The palette derives its screen commands
from the same array — label key, path, gated flag. Curator-gated screens are
**absent** from palette results when `curatorMode` is off (not shown-disabled —
same rule as the sidebar, D-4).

### D2 — Command model + registry (`lib/commandRegistry.ts`)

```ts
type PaletteCommand = {
  id: string            // stable, e.g. 'nav.library', 'action.checkUpdate'
  labelKey: string      // i18n key
  keywords?: string[]   // extra match terms (english, not translated)
  section: 'screens' | 'actions' | 'entries'
  curatorOnly?: boolean
  run: (ctx: { navigate: NavigateFunction }) => void | Promise<string>
}
```

Module-level `registerCommands(cmds)` / `getCommands()` so future specs
(activity center, dossier, gaps) register actions from their own modules — this
extension contract is the point of the feature; document it in a header comment.
Built-ins at v1: one nav command per NAV_GROUPS item + `action.checkUpdate`
(calls `/api/flat_file/discover`, renders its one-line outcome inside the palette
footer — resolved `Promise<string>` — instead of navigating).

### D3 — Query interpretation, ranked

Evaluated top-down on each keystroke:

1. **LB patterns** — `^(lb[-\s]?)?0*(\d{1,5})$` (case-insensitive) → synthetic
   top hit "Go to LB-N" → `navigate('/library?lb=N')`.
2. **Command fuzzy match** — in-house scorer over translated label +
   `keywords`: case-insensitive subsequence match, scored by (consecutive-run
   length, word-start hits, match position); no dependency. Ties broken by
   section order screens → actions.
3. **Entry search** — query ≥ 2 chars: debounced (200 ms) `GET /api/search?q=`,
   top 8 rows rendered in an "Entries" section (`LB-N · date_str · location`),
   Enter → `/library?lb=N`. In-flight responses discarded if the query changed
   (stale-response guard). Backend errors degrade silently to sections 1–2.

### D4 — Component + interaction (`components/CommandPalette.tsx`)

Overlay centered near top, single input, grouped result list. Mounted once in
AppShell. Global `keydown` listener (window, capture): `Ctrl/Cmd+K` toggles —
registered regardless of focused element (palette steals focus by design);
Escape closes and restores focus to the previously focused element; ArrowUp/Down
cycle across sections; Enter runs the highlighted command; click works too.
While open, background scroll locked (match AboutDialog's pattern). Highlight
state resets on query change. Styling via existing theme tokens
(`lib/tokens.ts`) and the ConfirmDialog/AboutDialog overlay idiom.

**Deferred by design:** SSE-backed actions (recompute, scans) join the palette
only after FABLE_ACTIVITY_CENTER.md ships a place for their progress to live —
the registry contract (D2) is what makes that a 5-line follow-up, not a rework.

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 shortcut** — default: `Ctrl+K` (`Cmd+K` on mac). Alternative: also `/`
  when no input is focused (cheap, but steals a real search character).
- **D-2 entry-result count** — default: 8. More = scrollier palette.
- **D-3 v1 actions** — default: `checkUpdate` only. Alternative: none (pure
  navigation) if even that feels premature.
- **D-4 gated screens** — default: hidden entirely when `curatorMode` off
  (sidebar parity). Alternative: shown with a lock badge.

---

## 4. Work bites (handoff units — commit each separately; sonnet tier)

Allocate ONE TODO id for the whole spec at the first implementation session (repo
numbering rules in `/session-close`). All-frontend: verify every bite with
`/gui-check`; no backend restarts needed.

### B1 — nav registry extraction (S)
`lib/navigation.ts` per D1; AppShell imports it. Pure refactor. **Accept:**
`/gui-check` green; AppShell renders from the moved array with zero behavior
change (no other file touched except the import site).

### B2 — palette core (M) — after B1
`lib/commandRegistry.ts` + `components/CommandPalette.tsx` per D2/D4 with
sections 1–2 of D3 (LB pattern + fuzzy commands), `en.json` keys
(`palette.placeholder`, `palette.sections.*`, `palette.goToLb`, …). Fuzzy scorer
gets a plain unit-testable export; add a vitest/jest test file only if the
renderer already has a test runner configured — **check `gui_next/package.json`
first**; if none exists, do NOT introduce one (scorer correctness is covered by
the accept walkthrough instead). **Accept:** `/gui-check` green; Ctrl+K / Escape
/ arrows / Enter wired; curator commands absent when `curatorMode` off; `lb1234`,
`1234`, `LB-01234` all produce the Go-to-LB hit.

### B3 — entry search (S) — after B2
D3 section 3: debounced `/api/search` with stale-response guard and silent
degradation. **Accept:** `/gui-check` green; typing a venue fragment lists
entries; Enter lands on `/library?lb=N` with the row selected (existing deep-link
behavior, unchanged).

### B4 — checkUpdate action + extension contract (S) — after B2
`action.checkUpdate` per D2 (skip if D-3 decided "none") + the
`registerCommands` header doc naming the three future consumers (activity
center, dossier, gaps). **Accept:** `/gui-check` green; the action renders the
discover outcome without leaving the palette; a failed fetch shows the error
string, not a crash.

### B5 — i18n + docs (XS) — last
`/gui-next-i18n`; PROJECT.md (new files, palette in the GUI-screens section);
FABLE_IDEAS.md UI §1 status line → 📋 SPEC WRITTEN → (on ship) ✅; CHANGELOG via
`/session-close`.

Order: B1 → B2 → B3 / B4 (either order) → B5.

---

## 5. Definition of done

1. From any screen, `Ctrl+K` + "son" + Enter lands on `/songs`; `Ctrl+K` +
   "1234" + Enter lands on `/library?lb=1234` with the row selected.
2. Venue/date fragments surface real entries via the existing search API; a dead
   backend degrades the palette to navigation, never breaks it.
3. Sidebar and palette provably share one screen registry (delete a NAV_GROUPS
   item → it vanishes from both).
4. Curator gating matches the sidebar exactly.
5. A future module adds a palette action by calling `registerCommands` — no
   palette-file edits required.
6. All strings translated; `/gui-check` green; zero new npm dependencies.
