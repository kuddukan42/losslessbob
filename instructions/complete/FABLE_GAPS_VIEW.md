# FABLE spec — Gaps view, "the living Kokay list" (PLATFORM_ROADMAP §3)

Written 2026-07-17 (Fable 5). Expands FABLE_PLATFORM_ROADMAP.md §3 into a handoff
spec. Audience: **sonnet implementation sessions** — every bite states exact accept
criteria; when reality diverges from a stated fact below, stop and re-verify before
improvising.

The idea: Les Kokay's uncirculated-shows list as a self-updating view. Every known
Dylan concert date becomes a cell in a year-by-year grid, colored by whether a
recording circulates — absence made visible, with click-through to what Olof knows
about the show.

**What this is NOT:** no new scraping, no derived tables, no writes to any table
(read-only feature end to end), no shadow-pile integration (roadmap §4 hooks in
later), no family trees (§6 gets a tab placeholder only).

---

## 1. Verified facts (2026-07-17 — trust these, re-verify only on contradiction)

- `olof_events` (local-only, NOT in MASTER_TABLES): one row per event; `event_id` PK
  in three disjoint ranges (DSN numbers `source='dsn'`, `year*1000+seq`
  `source='chronicle_appendix'` — superseded, never populated with setlists,
  `9_000_000+id` `source='bobserve'` for 2022+). Fields include `date_str` (ISO) +
  raw date, venue/city/region/country splits, `event_type`
  (`concert|session|rehearsal|broadcast|interview|other`; bobserve also emits
  compound labels like `concert - outlaw music festival` — match with
  `event_type = 'concert' OR event_type LIKE 'concert - %'`), `tour_name`,
  recording kind/mins fields, notes/bobtalk. Authoritative column list:
  `instructions/complete/FABLE_OLOF_FILES.md` §4 — read it before writing queries.
  Index `idx_olof_events_date` exists.
- Verified first cut (2026-07-15): **4,131 ISO-dated concerts**; entries resolve to
  3,919 exact dates + 112 partial `xx` date-strings; **347 concert dates have no LB
  entry** (1950s 2, 60s 69, 70s 35, 80s 29, 90s 23, 2000s 27, 2010s 82, 2020s 80).
  Numbers will shift slightly: Olof/bobserve list future 2026 dates not yet played
  (must be excluded), and the bobserve corpus keeps growing.
- `entries.date_str` is M/D/YY text with `xx` partials (`'5/xx/87'`).
  `backend/geocoder.py::_entry_date_to_iso()` already implements normalization
  (century pivot, returns `None` for `xx`/unparseable) — **reuse it, do not
  reimplement**. `geocoder.py::_table_exists()` is the feature-detect pattern for
  optional tables (olof_events may be absent on old installs).
- `lb_missing` = LB numbers confirmed non-existent (semantics:
  `docs/lb_missing_vs_missing_status.md`); `lb_master.status` distinguishes
  public/private/missing/nonexistent. A private or missing entry still proves a
  tape circulates/circulated → counts as coverage; a nonexistent LB number proves
  nothing. Entries with `entries.status='private'` exist since TODO-245.
- 1960s coffeehouse events often carry Olof recording notes saying no tape exists —
  surface the recording fields in the UI; do NOT auto-exclude those dates.
- Backend: single Flask app `backend/app.py`, port 5174. GUI: gui_next React;
  routes registered in `gui_next/src/renderer/src/App.tsx` (e.g. `/songs` →
  `ScreenSongs`); match ScreenSongs for screen + sidebar patterns. New user-facing
  strings go in `en.json`; `/gui-next-i18n` translates at close.

---

## 2. Target design

### D1 — Compute live, no derived table

4,131 events joined against an indexed entries date lookup is a sub-second query at
this scale. `backend/gap_analysis.py` computes everything on demand — no derived
table, no recompute-chain hook, nothing to go stale. Build once per request:
(a) map every entry to ISO date via `_entry_date_to_iso` (promote to public
`entry_date_to_iso`, keep a private alias so geocoder callers are untouched), and
to a month key (`'1987-05'`) for `xx` partials (new helper alongside);
(b) classify each distinct olof concert date:

| class | rule |
|---|---|
| `covered` | ≥1 entry resolves to this exact ISO date |
| `partial` | no exact match, but ≥1 `xx` entry's month key covers it |
| `gap` | neither |
| `future` | `date_str > today` — reported separately, never counted as gap |

Coverage matching excludes entries whose lb_master status is `nonexistent`
(private/missing still count — see §1). Keep the classifier a pure function over
plain dicts so it's trivially unit-testable.

### D2 — API (all GET, read-only)

- `GET /api/gaps/summary` → `{available, generated_at, totals, years: [{year,
  shows, covered, partial, gap, future}]}`. `available: false` (HTTP 200) when
  olof_events is absent or empty — GUI shows an explanatory empty state.
- `GET /api/gaps/year/<year>` → `{dates: [{date_iso, coverage, events: [{event_id,
  venue, city, tour_name, event_type, recording_kind, recording_mins}], lb_numbers,
  partial_lb_numbers}]}` — one element per date, all same-date events grouped
  (two-show days are one cell with `events` length 2).
- `GET /api/gaps/date/<iso>` → the drill-down: full olof event rows (incl. notes,
  bobtalk, recording fields), all entries on that date (lb_number, rating, status,
  taper_name), month-partial candidate entries, and recording_families on that
  date if the table exists. This payload is the future home of §6 family trees.

### D3 — ScreenGaps

Master-detail screen at `/gaps`: top strip = decade chips with gap counts; main
area = year rows, one small cell per show date in date order, colored by coverage
class (theme tokens — covered/dim, partial/mid, gap/warm-alert; future dimmed
outline). Clicking a cell loads the drill-down into a right-hand detail pane
rendered as a **tab group with one tab ("Event & sources")** — §6 later adds a
"Family tree" tab, so use a tab component now even with a single tab. Cell grid
must handle 80-show years without horizontal page scroll (wrap within the year
row). No new npm deps.

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 event universe** — default: concerts only (incl. bobserve compound
  labels). Alternative: a toggle adding broadcasts/sessions (more cells, muddier
  "gap" semantics).
- **D-2 future dates** — default: shown dimmed at the tail of the current year,
  excluded from all gap counts. Alternative: hidden entirely.
- **D-3 sidebar name** — default: "Gaps". Alternative: "Timeline" (but FABLE_IDEAS
  UI §2 timeline navigator is a distinct un-spec'd idea — don't blur them).
- **D-4 Kokay credit** — default: a one-line footer crediting Les Kokay's original
  list. Skip if you'd rather not.

---

## 4. Work bites (handoff units — commit each separately; sonnet tier)

Allocate ONE TODO id for the whole spec at the first implementation session (repo
numbering rules in `/session-close`). Repo rules apply throughout: type hints +
Google docstrings, `logging` not `print`, 100-char lines, read-only — any bite
that finds itself writing to the DB has misread the spec.

### B1 — date helpers (S)
Promote `entry_date_to_iso` to public in `backend/geocoder.py` (private alias
kept); add `entry_date_month_key(date_str) -> str | None` for `xx` partials.
Tests: exact dates across the century pivot, `xx` month keys, garbage in → None.
**Accept:** geocoder's existing tests untouched and green; new tests green.

### B2 — gap_analysis + routes (M) — after B1
`backend/gap_analysis.py` per D1 + the three D2 routes in `backend/app.py`.
Feature-detect olof_events (`_table_exists` pattern). Tests seed a temp DB (match
existing test fixtures) with: covered/partial/gap/future dates, a two-show date, a
nonexistent-status LB on an otherwise-gap date (must stay gap), a private entry on
a date (must count covered). **Accept:** tests green; against the live DB,
`/api/gaps/summary` totals are sane vs the §1 verified counts (shows ≥ 4,000; gap
total within ~300–420 after future-date exclusion) — paste the decade table into
the session summary for tj.

### B3 — ScreenGaps (M) — after B2
Screen + route + sidebar entry per D3, `en.json` keys. Verify with `/gui-check`
only — **no screenshots, no browser automation** (repo rule; tj verifies visuals).
**Accept:** typecheck + build green; empty state renders when the API reports
`available: false`.

### B4 — docs + i18n (XS) — last
`/gui-next-i18n` for the new keys; PROJECT.md (new module, three routes, screen);
update the FABLE_PLATFORM_ROADMAP §3 status line and instructions/README.md row;
CHANGELOG via `/session-close`.

Order: B1 → B2 → B3 → B4.

---

## 5. Definition of done

1. `/gaps` renders every ISO-dated Olof concert as a colored cell; decade chips
   and per-year counts match `/api/gaps/summary`.
2. A gap date's drill-down shows venue/tour/recording notes from Olof and proves
   the absence (no entries); a covered date lists its LB numbers.
3. `xx`-dated entries produce `partial` coverage, not false gaps.
4. Future-dated shows never inflate gap counts; nonexistent LB numbers never
   create coverage.
5. Zero DB writes; app behaves identically when olof_events is absent.
6. The drill-down pane is a tab group ready to receive §6's family-tree tab.
