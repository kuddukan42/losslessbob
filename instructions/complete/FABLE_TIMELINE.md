# FABLE spec — Timeline navigator (FABLE_IDEAS UI-2)

Written 2026-07-24. Expands `instructions/FABLE_IDEAS.md` UI-2 into a handoff spec,
scoped via a live interview with tj rather than Fable defaults — all "Decisions"
below are **locked**, not open. Audience: **sonnet implementation sessions** — every
bite states exact accept criteria; when reality diverges from a stated fact below,
stop and re-verify before improvising.

The idea: the archive is fundamentally temporal but browsing today is list-shaped. A
zoomable Decade → Tour → Night navigator, colored by the best grade held for each
night, turns "browse the collection" into "browse time." Clicking a night opens the
existing dossier (TODO-257) — everything the app knows about that date.

**What this is NOT:** not an absorption of `/gaps` (ScreenGaps stays untouched, no
shared code, no route changes there — may be revisited later, not now); not
"tonight in history" (dropped from v1); not a Library-filter jump (drill-down target
is the dossier, not `/library?lb=...`); no new derived/materialized table — computed
live like `gap_analysis.py`, same read-only philosophy.

---

## 1. Verified facts (2026-07-24 — trust these, re-verify only on contradiction)

- `olof_events.tour_name`: **4,905 / 4,924** rows populated (218 distinct tours) —
  tour-grouping is reliable, not a data gap to design around. Top tours by **raw
  row count** (NOT the filtered night count this screen shows — see the concert
  filter below): "Rough and Rowdy Ways World Wide Tour" (282), "1965 Recording
  sessions & concerts" (95), "1999 US Summer Tour with Paul Simon" (56). Under the
  concert-only filter these become 282 / 53 / 55 respectively — note the #2/#3
  ordering **flips** (the 1965 tour is mostly `session` rows), so never rank tours
  off raw counts.
- **Event-type filter (do not skip):** this screen counts *concerts only*, exactly
  as `gap_analysis` does — reuse its `_olof_concert_events` /
  `_CONCERT_TYPE_FILTER` (`backend/gap_analysis.py:32-34,136-160`):
  `event_type = 'concert' OR event_type LIKE 'concert - %'`, and
  `tour_name NOT LIKE '%ehearsal%'`. This drops 205 `session` / 91 `broadcast` /
  63 `interview` / 299 `other` rows — concert-filtered total is **4,211**, not
  4,924. A row is one event, so two-show dates yield two rows; **group by
  `date_str`** for per-night cells and counts.
- `entries.rating` is a 13-step letter scale: `A+ A A- B+ B B- C+ C C- D+ D D- F`.
  No shared backend or frontend ordinal/ramp constant exists yet — every occurrence
  (`ScreenSongs.tsx:63-65` `GRADE_ORDER`, `ScreenSearch.tsx:75` `RATING_RANK`,
  `DetailPanel.tsx:1682`, `ScreenLibrary.tsx:145`) is frontend-local and duplicated.
  This spec defines the first backend ordinal (`timeline.py::GRADE_RANK`) — do not
  import a frontend file into the backend; it's a fresh Python table.
- "What counts as held" mirrors `gap_analysis._entry_coverage_maps`
  (`backend/gap_analysis.py:96-133`): entries with a clean `date_str`, excluding
  `lb_master.lb_status = 'nonexistent'` (private/missing still count — a tape that
  circulated proves the night, even if you can't currently get it).
- The app's theme engine (`gui_next/src/renderer/src/lib/tokens.ts:69-80`) already
  ships a validated 5-tone **categorical status** palette (ok/warn/bad/info/mute,
  light+dark). This spec deliberately does **not** reuse it for grade coloring — tj
  chose a proper sequential single-hue ramp instead (dataviz skill: magnitude gets
  one hue, light→dark, not a categorical set) over reusing the shipped tones. Reason
  it wasn't a free reuse: the existing `ratingTone()` helper
  (`ScreenLibrary.tsx:194-199`, `ScreenSearch.tsx:161-166`) already maps `D`/`F` →
  `mute`, which would collide with "no tape" if reused verbatim.
- No lightweight "view the dossier" trigger exists anywhere in the frontend today —
  only `DossierExportModal.tsx`, which always shows a channel/sections/format form
  before doing anything (PDF via Electron IPC, HTML via file download — never an
  in-app view). Backend route `GET /api/dossier/html` already accepts `date`,
  `location?`, `channel?` as query params (`backend/app.py:6457`) and needs nothing
  new — the gap is purely a frontend viewer.
- Backend: single Flask app `backend/app.py`, port 5174, routes as direct
  `@app.route` decorators (no blueprints) — see the gaps block
  (`app.py:6405-6430`) for the exact try/except/jsonify/500 convention to copy.
  GUI: gui_next React; routes registered in `App.tsx` (`:351-370`, e.g. `/gaps` →
  `ScreenGaps` at `:356`); sidebar + palette both driven from
  `lib/navigation.ts` (`NavId` union `:8-12`, `NAV_GROUPS` `:38-89`) — the palette
  needs **no separate registration**, `commandRegistry.ts::navCommands()`
  (`:71-87`) auto-generates one entry per `NAV_GROUPS` item. New user-facing
  strings go in `en.json`; `/gui-next-i18n` translates at close.

---

## 2. Target design

### D1 — Backend: `backend/timeline.py` (new, mirrors `gap_analysis.py`)

Pure functions, no Flask coupling, computed live (no derived table):

- `get_summary(db_path=None) -> dict` — one row per decade: `{decade, label,
  night_count, circulating_count, best_grade}`.
- `get_decade_detail(decade, db_path=None) -> dict` — one row per tour whose
  earliest show falls in that decade: `{tour_name, start_date, end_date,
  night_count, best_grade}`. (A tour spanning a decade boundary is attributed
  wholly to the decade of its earliest show — rare enough not to split.)
- `get_tour_detail(tour_name, decade, db_path=None) -> dict` — one row per night:
  `{date_iso, venue, city, best_grade}` (`best_grade: null` = no tape).

Grade rollup: select the concert-only olof set via `_olof_concert_events` /
`_CONCERT_TYPE_FILTER` (§1 — this is the *event-side* filter and is NOT optional),
then join `olof_events` (date_str, tour_name, venue, city) to `entries` by resolved
ISO date under the same *entry-side* exclusion as `_entry_coverage_maps` (§1,
`nonexistent` lb_status dropped). Both filters apply — one gates which events count,
the other which entries count. One olof row is one event, so **group by `date_str`
first** (two-show dates → two rows → one night); `night_count`/`circulating_count`
are per-date, never per-row. Reduce to best grade per date via `GRADE_RANK`
(`A+`→0 … `F`→12, `min()` wins) in Python — no attempt to rank letter grades in
SQL. Feature-detect `olof_events` absence the same way `gap_analysis.py` does
(`available: false`, HTTP 200, GUI shows empty state).

### D2 — API (all GET, read-only)

- `GET /api/timeline/summary`
- `GET /api/timeline/decade/<int:decade>`
- `GET /api/timeline/tour?name=<tour_name>&decade=<int>` — query param, not a path
  segment (tour names carry spaces/punctuation); scoped by decade because tour
  names are not guaranteed globally unique.

Same error convention as the gaps routes: broad `except Exception` →
`_log.exception(...)` → `jsonify({"error": str(e)}), 500`.

### D3 — `ScreenTimeline.tsx` (new, structured like `ScreenGaps.tsx`)

`useQuery` + `window.api.flaskBase`, inline styles against `--lbb-*` CSS custom
properties (no CSS module, no Tailwind) — match ScreenGaps' data-fetching and
styling conventions exactly, but the interaction model is a genuine zoom-in/out
(not ScreenGaps' fixed grid + side detail pane):

1. **Decade grid** (top level, from `/api/timeline/summary`) — one cell per decade,
   colored by that decade's `best_grade` on the sequential ramp (D5).
2. Click a decade → **tour grid** (`/api/timeline/decade/<decade>`) — one row/cell
   per tour, same coloring, sorted by start date.
3. Click a tour → **night strip** (`/api/timeline/tour?...`) — one small cell per
   night in chronological order; no-tape nights render in the neutral/mute state
   (D5), distinctly separate from the ramp.
4. Click a night with a grade → opens the dossier viewer (D4). Click a no-tape
   night → no-op or a small "no circulating tape" tooltip (no dossier to show).
5. Breadcrumb (`Decades / 1980s / Real Live Tour`) to zoom back out at any level.

### D4 — Dossier viewer (new, minimal)

An in-app modal: `<iframe src="${BASE}/api/dossier/html?date=${date}&channel=public">`
+ close button + a secondary "Open full export..." link that hands off to the
existing `DossierExportModal` (`components/library/DossierExportModal.tsx`) for
anyone who wants PDF/BBcode/format options instead of just looking. This is the
first read-only dossier viewer in the app — don't retrofit `DossierExportModal`
itself, it's an exporter with a required options step, not a viewer.

### D5 — Sequential color ramp

New `--lbb-seq-*` tokens in `lib/tokens.ts`. Note the existing status tones aren't a
static token block — they're the `STATUS` record (`:67-80`) emitted by a loop in
`applyTheme()` (`:199-202`), so the ramp needs its own `SEQ` record (light + dark)
**plus its own emission loop**, not a copy-pasted `root.style.setProperty` block.
Light + dark, 5–7 steps, one hue (derived from the app's existing
`info`/blue hue for visual consistency with the rest of the theme — not a
copy-paste of the dataviz skill's generic reference blue). Lightest step = worst
grade, darkest = best. Validate both light and dark step sets with the dataviz
skill's `scripts/validate_palette.js` before treating them as final. No-tape cells
use the existing `--lbb-mute-bg`/`-fg` tokens, deliberately kept outside the new
ramp so "no data" never reads as "a low grade."

---

## 3. Decisions (locked via interview, 2026-07-24 — not open for this build)

- **Placement**: standalone screen at `/timeline`, own sidebar entry (Library
  group, alongside `gaps`), own palette entry (free via `navCommands()`).
- **Relationship to ScreenGaps**: none. No shared route, no absorption, no
  retirement. May be revisited later — out of scope now.
- **Zoom tiers**: Decade → Tour → Night (confirmed viable per §1's tour_name
  coverage — not Decade → Year → Night).
- **Color job**: sequential ramp for grade magnitude, not the existing categorical
  status tones — see §1 for why the reuse option was rejected.
- **Drill-down target**: the dossier (viewer, D4), not `/library?lb=...`.
- **v1 exclusions**: "tonight in history" widget, saved/pinned timeline views,
  filtering — all explicitly deferred, not forgotten.

---

## 4. Work bites (handoff units — commit each separately; sonnet tier)

Allocate ONE TODO id for the whole spec at the first implementation session (repo
numbering rules in `/session-close`). Repo rules apply throughout: type hints +
Google docstrings, `logging` not `print`, 100-char lines, read-only end to end — any
bite that finds itself writing to the DB has misread the spec.

### B1 — `backend/timeline.py` + routes + tests (M)
D1 + D2. Tests in `tests/test_timeline.py`, following `tests/test_gap_analysis.py`'s
fixture-DB structure: a decade with multiple tours, a tour spanning a decade
boundary (attributed to the earlier decade), a night with multiple entries at
different grades (best wins), a night with only a `nonexistent`-status LB (must
render as no-tape), a private-status entry (must count and contribute its grade).
**Accept:** tests green; against the live DB, `/api/timeline/summary` decade counts
are sane (sum of `night_count` across decades ≈ olof_events concert-type count) —
paste the decade table into the session summary for tj.

### B2 — Sequential ramp (S) — can run in parallel with B1
D5. Add `--lbb-seq-*` steps to `tokens.ts`, run `validate_palette.js` for both
light and dark chart surfaces, adjust steps until it passes. **Accept:** validator
reports pass for both light and dark; steps visibly distinct from `--lbb-mute-*` at
a glance.

### B3 — `ScreenTimeline.tsx` + registration (L) — after B1, B2
D3 + registration (`navigation.ts`, `Icon.tsx` new `timeline` glyph, `App.tsx`
route, `en.json` keys incl. `appShell.nav.timeline`). Verify with `/gui-check`.
**Accept:** typecheck + build green; empty state renders when the API reports
`available: false`; decade→tour→night zoom and breadcrumb back-out both work.

### B4 — Dossier viewer modal (M) — after B3
D4, wired from night-cell clicks in `ScreenTimeline.tsx`. **Accept:** clicking a
graded night opens the iframe viewer with the correct date's dossier; "Open full
export..." correctly hands off to `DossierExportModal`; closing the viewer returns
to the night strip without a full remount/refetch.

### B5 — Docs + verification (S) — last
`/gui-next-i18n` for the new keys; `PROJECT.md` (new module, three routes, screen);
CHANGELOG via `/session-close`; `/verify` (Tier A minimum — new layout, new color
ramp) confirming both light and dark theme render correctly; update
`instructions/FABLE_IDEAS.md` UI-2 to `📋 SPEC WRITTEN` pointing at this file.

Order: (B1 ∥ B2) → B3 → B4 → B5.

---

## 5. Definition of done

1. `/timeline` renders a decade grid; clicking a decade zooms to its tours;
   clicking a tour zooms to its nights; a breadcrumb zooms back out at any level.
2. Grade coloring uses the new sequential ramp end-to-end; no-tape nights are
   visually distinct from every graded step, not just the lightest one.
3. Clicking a graded night opens the dossier viewer for that exact date; clicking a
   no-tape night does not attempt to open a dossier.
4. `nonexistent`-status LB numbers never produce a grade; private/missing entries
   do.
5. Zero DB writes; screen behaves identically (empty state) when `olof_events` is
   absent.
6. ScreenGaps is untouched — no shared code, no route changes, no behavior change.
