# FABLE spec — Show dossier / liner-notes export (FABLE_IDEAS §5)

Written 2026-07-17 (Fable 5). Expands FABLE_IDEAS.md app idea 5 (⭐ HIGH PRIORITY per tj
2026-07-13) into a handoff spec. One command renders everything the app knows about a
date into a printable page: setlist with rarities flagged, all circulating sources with
family grouping and pick ranking, taper credit, quality verdicts, historical context.
Export as self-contained HTML (and PDF via Electron) for archive folders, trades, or
forum posts.

**Read `instructions/SPEC_INTEGRATION_NOTES.md` first** (repo rule). The findings that
bind here: F3 (evidence records are `{kind, detail, ...}` — render them, don't invent a
new shape) and F4 (DetailPanel gets an *action*, never inline content).

**The one rule:** a dossier is an *outward-facing* artifact. It may only contain what
the public LB site channel would contain, plus clearly-labelled local analysis — never
disk paths, collection/friend data, or (by default) private-entry metadata. §3 D-1/D-2.

---

## 1. Data inventory (verified against PROJECT.md schema + routes, 2026-07-17)

Every row is feature-detected at assembly time — a fresh install has none of the
derived tables populated, and `olof_*` is local-only. A missing source silently drops
its dossier section; it never errors.

| Source | Dossier use | Availability |
|---|---|---|
| `entries` (per LB of the date) | rating, timing, description, taper_name/source_chain, source_type, lb_category, `status` (private gate) | always |
| `db.get_performances()` grouping | show identity `(date_str, location)`, venue/tour/title cross-refs (bobdylan_shows, dylan_performances, setlistfm, bootleg_titles) | always |
| `olof_events` + `olof_songs` (by date) | authoritative setlist (encores, credits, annotations), event type, tour, NET/year concert #s, lineup, notes, bobtalk quote | local-only, gate on `/api/olof/status` pattern |
| `olof_chronicle` (by date) | diary/calendar context paragraph | local-only |
| `song_performances` | per-song rarity: all-time performance count, first/last/only performance | derived (TODO-230) |
| `recording_families` / `tapematch_family_meta` | group sources by master-tape family (label, conf, member_count, needs_review) | synced, may be absent |
| `entry_lineage` | same_as / derived_from / better_than edges → lineage notes per source | derived |
| `taper_attributions` | taper credit + confidence tier (confirmed/propagated/inferred; skip conflicted) | derived |
| `show_picks` (by `concert_date_iso`) | pick ranking + F3 evidence list; rank 1 = "recommended" | derived |
| `quality_recording_scores` (latest scan) | AI grade (`abs_grade` letter) + `verdict_text` snippet | USER-tier, local scans only |
| `curated_lists` / `curated_list_entries` | curator endorsements ("carbonbit's picks", note text) | master |
| `checksums` xref groups | per-LB alternate fileset count ("+2 alt filesets") | always |
| `meta` master_version | provenance footer | always |

Existing precedents to reuse, not reinvent: `/api/collection/export/html`
(self-contained HTML attachment pattern, `_EXPORT_COLUMN_DEFS` in app.py),
`/api/entry/<lb>/preview_forum` (generated share text), the Library performance-lens
`m3u` row action (per-show export wiring, `lb_numbers` filter pattern).

---

## 2. Target design

### D1 — Assembly: one module, one JSON shape

New `backend/dossier.py`: `build_dossier(date_iso: str, location: str | None = None,
channel: str = 'public') -> dict`. Show identity matches the performance lens: when a
date has multiple shows (early/late), `location` disambiguates; ambiguous request
without it → 300-style response listing the candidate `(date_str, location)` pairs.

Output shape (sections omitted when their source is absent, never null-faked —
same convention as `/api/library/performances`):

```
{
  show: {date_iso, date_disp, dow, venue, city, tour?, event_type?, net_number?,
         year_concert_number?, title?},
  context: {chronicle?, bobtalk?, notes?, lineup?},
  setlist: [{position, title, is_encore, credits?, annotations?,
             rarity?: {n_performances, first_date, last_date,
                       flag: 'only'|'first'|'last'|'rare'|null}}],
  sources: [{fam_id?, fam_label?, fam_conf?, fam_needs_review?, members: [
     {lb, rating?, timing?, source_type?, taper?: {name, tier}, source_chain?,
      lineage_notes?: [str], pick?: {rank, score, evidence: [{kind, detail, points}]},
      quality?: {grade, verdict}, curated?: [{list_label, note?}],
      alt_filesets?: int, private?: true}]}],
  recommendation?: {lb, evidence: [...]},          // rank-1 pick, restated
  provenance: {generated_at, master_version?, channel,
               local_analysis: bool}               // true if any USER-tier section present
}
```

Rarity rule (from `song_performances` by `song_norm`): `only` = 1 all-time
performance; `first`/`last` = this date is the min/max `concert_date_iso` for the
song; `rare` = ≤ 10 all-time performances. Thresholds are module constants.

### D2 — Privacy channel (mirrors TODO-253 master-export semantics)

`channel='public'` (default): an `entries.status='private'` source appears as LB
number + `private: true` only — no description-derived fields (rating, timing, taper,
lineage, chain). `channel='full'` includes them (friends-only distribution, same
meaning as master export's `full`). **Never in any channel:** `disk_path`, collection
ownership, friend data, wishlist. USER-tier analysis (grades, picks, families) IS
included — it's tj's own output and half the dossier's value — but the rendered page
labels those sections "local analysis" and the options modal can toggle them off (D4).

### D3 — Rendering: server-side Jinja, self-contained, print-first

`GET /api/dossier?date=&location?=&channel?=` → JSON (D1).
`GET /api/dossier/html?...same params + sections?=` → rendered page as attachment
(`dossier-YYYY-MM-DD.html`), template `backend/templates/dossier.html` via Flask's
built-in Jinja (zero new deps; first template in the repo — create the directory).
Self-contained: inline CSS, no external requests, `@media print` rules so
browser/Electron print produces clean pages (section page-break avoidance, no
UI chrome). Single-column, light background — it's a document, not an app screen.
Evidence lists render as plain label rows (ranking-spec §6 style, the HTML twin of
gui_next's `EvidenceList`).

### D4 — GUI surface: one action, one modal, PDF via Electron

- Performance-lens row action **"Export dossier…"** in `components/library/actions.tsx`
  (registry pattern, next to `m3u`) + the same action in DetailPanel's ActionBar when
  a performance is selected (F4: action, not inline content).
- Options modal: channel (public/full), section toggles (local-analysis sections,
  context, setlist), format **HTML / PDF**. Remembers last choices (`useSettingsStore`).
- PDF = Electron main process: hidden `BrowserWindow` loads the HTML (from the
  backend URL), `webContents.printToPDF`, save dialog — new `window.api` IPC channel,
  no Python PDF dependency. HTML fallback (plain download) when running outside
  Electron.

### D5 — Forum digest (optional, after D1–D4)

`GET /api/dossier/bbcode?...` — compact BBcode digest (show header, setlist with
rarity marks, source list with picks) for WTRF posts, following the
`preview_forum` pattern; copy-to-clipboard button in the modal. Text-only sibling of
the HTML template — keep both fed from the same D1 JSON so they can't drift.

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 private sources in public dossiers** — default: LB number + "private entry"
  marker only (D2). Alternative: omit the row entirely.
- **D-2 local analysis in shared dossiers** — default: included, labelled
  "local analysis (this install)", toggleable in the modal. Alternative: off by
  default for `channel='public'`.
- **D-3 rarity threshold** — default: `rare` = ≤ 10 all-time performances.
- **D-4 forum digest (D5/B5)** — default: build it (small); say the word to drop it.

---

## 4. Work bites (handoff units — commit each separately)

Implementation tier: sonnet per agent policy; allocate the TODO id at the first
implementation session per repo numbering rules (one TODO for the whole spec, bites
tracked in-spec). Backend restart before verifying any backend bite (repo rule).

### B1 — Assembly module + JSON route (M)
`backend/dossier.py` (`build_dossier`), `GET /api/dossier` in app.py. Reuse
`get_performances()`-style loaders / existing helpers, don't re-derive grouping
logic. Tests `tests/test_dossier.py`: fixture date with 2 families + a singleton;
asserts (i) section omission when derived tables are empty (fresh-install case),
(ii) `channel='public'` blanks private-source metadata, `'full'` keeps it,
(iii) rarity flags for an `only` and a `rare` song, (iv) ambiguous two-show date
requires `location`.
**Accept:** route returns D1 shape on a real date; tests green.

### B2 — HTML template + route (M) — after B1
`backend/templates/dossier.html` + `GET /api/dossier/html`. Self-contained (verify:
zero external URLs in output), `@media print` clean. A `sections=` param filters
per D4's toggles. Render a real date and eyeball in a browser (this is a served
document, not a GUI screen — the no-screenshots rule isn't in play, but keep
verification to opening the file).
**Accept:** one real date renders complete with all sections; a fresh-DB render
degrades to header + setlist without error.

### B3 — GUI action + modal + Electron PDF (M) — after B2
`actions.tsx` registry entry, options modal, `window.api` printToPDF IPC in
gui_next main. i18n: new keys in the `library` namespace, run `/gui-next-i18n`.
**Accept:** `/gui-check` PASS; HTML export downloads from the modal; PDF saves via
Electron dialog.

### B4 — Docs (XS) — last
PROJECT.md: new routes in the API table, `backend/dossier.py` + templates dir in the
file tree; CHANGELOG per session-close.

### B5 — BBcode digest (S, optional — D-4)
`GET /api/dossier/bbcode` + modal copy button. Shares B1's JSON.

Order: B1 → B2 → B3 → B4; B5 whenever after B1.

---

## 5. Definition of done

1. One command (Library row action) turns any fully-populated date into a
   self-contained HTML/PDF dossier: header, context, rarity-flagged setlist,
   family-grouped sources with taper credit + pick ranking + quality verdicts,
   recommendation, provenance footer.
2. The same action on a fresh install (no derived data, no olof) still produces a
   valid, smaller document — no errors, no empty-section skeletons.
3. A `channel='public'` dossier contains no private-entry metadata, no disk paths,
   no collection/friend data — verified by a test, not by inspection.
4. Local-analysis sections are visibly labelled as such and can be toggled off.
5. `/gui-check` + backend tests green; locales updated; PROJECT.md updated.
