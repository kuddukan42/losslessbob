# FABLE spec — Xref incorporation (TODO-246 steps 2+3)

Written 2026-07-15. Semantics authority: **docs/XREF_SEMANTICS.md** (signed off by tj
2026-07-15) — read it first; every change below is measured against it. This spec is the
full-app audit (step 2) plus the required changes (step 3), written for handoff: each
bite is independently implementable and verifiable.

**The one rule, restated:** an xref number is a global *fileset id* naming an alternate
circulating fileset of exactly one LB entry. There are two distinct statements an app
surface can make — **copy-level** ("this folder is the xref-X fileset of LB-N") and
**entry-level** ("LB-N has alternate filesets documented") — and no badge, filter, or
column may conflate them.

---

## 1. Audit results (verified 2026-07-15)

| # | Touchpoint | Current behavior | Verdict |
|---|-----------|------------------|---------|
| A1 | `db.py lookup_checksums` reverse lookup | Completeness judged per `(lb_number, xref)` group | **OK** — keep, this is the semantic anchor |
| A2 | `db.py lookup_checksums` `lb_summary` | Carries `xrefs` (count of xref-matched rows) but not *which* fileset matched | **GAP** — downstream can't know the copy is xref-X |
| A3 | `"XREF"` lookup status | Backend emits only MATCHED / DUPLICATE / NOT FOUND; PROJECT.md documents an XREF status, and `cli.py:1662`, `lookupState.ts:17`, `ScreenQuickLookup.tsx:36` all guard on it | **DEAD contract** — guards unreachable |
| A4 | `app.py xref_map` docstring | Claims `{xref_id: lb_number}`; implementation (and PROJECT.md) is `{lb_number: [xref ids]}` | **WRONG** docstring |
| A5 | `GET /api/checksums/xref_map` | Zero consumers in gui_next (legacy Search tab was the consumer) | **ORPHANED** |
| A6 | `app.py _pipeline_process_folder` | Picks `lb_number` from lookup summary, ignores xref entirely; rename proposal built without fileset id | **GAP** — pipeline erases xref identity |
| A7 | `backend/folder_naming.py` | `build_standard_name` / `build_multi_lb_name` have no xref parameter | **GAP** (legacy `gui/rename_tab.py _fmt_lb` did `LB-{n}-xref{v:04d}`) |
| A8 | Schema, copy side | `folder_lb_link`, `my_collection`, `pipeline_folder_state` have no xref column | **GAP** — copy-level xref can't persist |
| A9 | `flat_file.py` / `importer.py` | Master format carries xref through export/import/diff | **OK** |
| A10 | `backend/scraper.py` | Writes `entries` + `entry_files` only; checksum rows (incl. xref) enter *only* via master import; `data/site/files/LBF-*-xref-*-text.txt` (5,575 files ≈ 1,858 filesets) sit unread | **DESIGN DECISION** (§4, D-2) |
| A11 | `lookupState.ts`, `ScreenQuickLookup.tsx` | `status === 'XREF'` mapping → the `xref` pill state never fires | **DEAD** |
| A12 | `ScreenLookup.tsx` "Cross-refs" status bar | Counts a state that never occurs — permanently 0 | **DEAD** |
| A13 | `ScreenSearch.tsx` Xref column | Hardcoded `null` (regression from legacy Search, which filled it from `xref_map`) | **DEAD** |
| A14 | `ScreenCollection.tsx` `isXref` pill + "Xref only" filter | Driven by entry-level `xref_lb_numbers` but rendered on the user's *copy* rows | **WRONG meaning** (conflation) |
| A15 | `ScreenLibrary.tsx` facet + `library/DetailPanel.tsx` pill | Entry-level set on the catalog lens — correct meaning, but labeled bare "Xref" | **RELABEL** |
| A16 | `LookupDetail.tsx` per-checksum xref column | Shows the fileset id on matched rows | **OK** |
| A17 | `tools/parse_dff_reports.py` | Reads `LBF-{lb}-xref-{id}` as "report for LB {id}" and attributes flaw counts to the xref id *as an LB number* — verified wrong against site files (`LBF-00002-xref-00961-*` = DB group (2, 961)). `dff_reports` has no consumers yet, so the fix is contained | **WRONG** |
| A18 | `cli.py` lookup rendering | Dead XREF guard (1662); missing-file list (1693–95) excludes xref rows, so a *partial* xref-group match lists canonical filenames as missing instead of that group's | **Minor WRONG** |
| A19 | PROJECT.md | Schema tables call xref "1 = cross-reference" / "0 or 1" (lines ~295, ~1048); status table still lists XREF | **STALE docs** |
| A20 | Legacy `gui/` (6 files) | Own xref column/filter/naming implementations | **FROZEN** — no changes (§4, D-3) |

Existing test hooks: `tests/test_db_lookup.py` already seeds xref rows; `tests/test_pipeline_smoke.py` covers `_pipeline_process_folder`.

---

## 2. Target design

**D1 — Lookup names the fileset.** Extend each `lb_summary` entry with:
- `xref_groups`: `[{xref: int, given: int, matched: int, missing: int}]` — one row per
  `(lb, xref)` group touched by the input (xref 0 = canonical fileset);
- `matched_xref`: the fileset id of the *winning* group — the group with the fewest
  missing files (ties → lowest id; canonical 0 wins ties against xref groups). `0`
  means the copy is the canonical fileset.
Per-row `xref` in `detail` stays as-is. **No "XREF" status resurrection** — copy-level
xref is a dimension (`matched_xref > 0`), not a status; MATCHED/INCOMPLETE/DUPLICATE
stay orthogonal to it.

**D2 — Naming carries the fileset.** `build_standard_name` / `build_multi_lb_name`
gain `xref: int = 0` (multi: `xrefs: list[int]` aligned with `lb_numbers`); when
xref > 0 the tag becomes `LB-XXXXX-xrefYYYYY` (both 5-digit, matching Jeff's site-file
padding `LBF-00002-xref-00961`, superseding the legacy 4-digit `_fmt_lb`). Any parser
of folder names must accept the wild variants already on disk:
`[Xx]ref[- ]?0*(\d+)` (real examples: `xref-01995`, `Xref-1292`, `xref2141`).

**D3 — Copy-level xref persists.** Add `xref INTEGER NOT NULL DEFAULT 0` to
`folder_lb_link` and `my_collection` (idempotent `PRAGMA table_info` + `ALTER TABLE`
per repo rule). The pipeline writes `matched_xref` at the link/rename/file steps; the
Add-to-collection path carries it into `my_collection.xref`.

**D4 — Two badges, two meanings.**
- *Copy-level* (pipeline, lookup screens, collection rows): "Xref fileset ·
  xref-00961" — fires from `matched_xref > 0` (live lookup) or the persisted
  `my_collection.xref` (collection views).
- *Entry-level* (Search, Library, DetailPanel, facets): "has alternate filesets" —
  fires from `xref_lb_numbers` / `xref_map`. Label it as such (i18n:
  `xref.entryHasAlts` ≈ "Alt filesets", tooltip with the ids from `xref_map`), never
  bare "Xref" on a row that also represents a copy.

**D5 — Entry detail mirrors the site.** Views rendering an entry's checksums
(`/api/entry/<lb>` consumers: LookupDetail-style tables, library DetailPanel) group
rows by fileset: canonical block first, then one block per xref id, titled
`xref-YYYYY (n files)` — the same shape as Jeff's page.

---

## 3. Work bites (handoff units — commit each separately)

### B1 — Backend lookup summary (S)
`backend/db.py`: build `xref_groups` + `matched_xref` from the existing
`_lb_xref_missing` map (the data is already computed — this is exposure, not new
analysis). Fix `app.py xref_map` docstring (A4). Extend `tests/test_db_lookup.py`:
a fixture folder fully matching an xref group must yield `status MATCHED`,
`matched_xref = <id>`; a canonical match must yield `matched_xref = 0`.
**Accept:** new fields in `/api/lookup` response; existing tests green.

### B2 — Naming, schema, pipeline wiring (M) — depends on B1
`folder_naming.py` xref params (D2) + unit tests for both builders and the
legacy-variant parser regex. Idempotent ALTERs (D3). `_pipeline_process_folder`:
thread `matched_xref` from the lookup step into the rename proposal
(`LB-XXXXX-xrefYYYYY`), `folder_lb_link` writes, and the file step; a folder whose
`matched_xref` changed (e.g. re-lookup after DB update) must re-propose the rename.
Extend `tests/test_pipeline_smoke.py` with an xref-group fixture.
**Accept:** pipeline run on an xref-matching fixture folder proposes the xref-suffixed
name and persists `folder_lb_link.xref`; canonical folders unchanged.

### B3 — gui_next copy-level surfaces (M) — depends on B1/B2
- `lookupState.ts` + `ScreenQuickLookup.tsx`: derive the `xref` pill state from
  `matched_xref > 0` (delete the dead `status === 'XREF'` branches) — the state
  *augments* matched/incomplete rather than replacing it: keep the status pill, add
  the copy-level xref pill (D4).
- `ScreenLookup.tsx`: "Cross-refs" bar counts `matched_xref > 0` rows (A12).
- `LookupDetail.tsx`: summary row shows `matched_xref` id, per-checksum column stays.
- Pipeline rename card shows the xref-suffixed proposal (comes free from B2, verify).
**Accept:** `/gui-check` PASS; an xref lookup fixture shows the pill; run
`/gui-next-i18n` for new keys.

### B4 — gui_next entry-level surfaces (M) — independent of B2/B3
- `ScreenSearch.tsx`: populate the Xref column from `xref_map` (one fetch, cached like
  the legacy tab did; display as comma-joined ids) (A13).
- `ScreenCollection.tsx`: split the conflated filter into two: **"My xref copies"**
  (copy-level: `my_collection.xref > 0`, needs B2's column — until then hide it) and
  **"Entries with alt filesets"** (entry-level set, the current behavior renamed).
  Row pill becomes copy-level; move the entry-level marker into the detail pane (A14).
- `ScreenLibrary.tsx` + `DetailPanel.tsx`: keep entry-level, relabel per D4 (A15);
  DetailPanel checksum listing groups by fileset (D5).
**Accept:** `/gui-check` PASS; no surface uses one label for both meanings;
`/gui-next-i18n` run.

### B5 — parse_dff_reports fix (S) — independent
Key `dff_reports` by `(lb_number, xref)` (composite PK; xref 0 = primary report);
`LBF-{lb}-xref-{id}` rows are attributed to `{lb}` with `xref = {id}` (A17). No
consumers exist, so drop/recreate + full reparse is acceptable.
**Accept:** reparse count matches file census (~5,575 xref-named files); spot-check
`LBF-00002-xref-00961` lands on (2, 961).

### B6 — cli.py cleanup (XS) — after B1
Remove the dead XREF guard; missing-file list uses the winning group's filenames
(filter `/api/entry` checksums by `xref == matched_xref` instead of `not xref`) (A18).

### B7 — Docs (XS) — last
PROJECT.md: fix the two schema rows ("fileset id, 0 = canonical"), replace the XREF
status row with the `matched_xref` dimension, note the new columns and API fields
(A19). Cross-link docs/XREF_SEMANTICS.md from the schema section.

### B8 — Site-mirror xref ingest (M, **deferred — needs D-2 decision**)
Staging tool: parse `data/site/files/LBF-*-xref-*-text.txt` (checksum text) →
report filesets present on the site mirror but absent from `checksums`
(new xref ids > 2151 and gaps among the 215 described-but-uncaptured entries).
Output = report + staged rows only; **nothing writes to `checksums` outside the
master-import path** unless tj decides otherwise.

Suggested order: B1 → B2 → {B3, B4, B5 in any order} → B6 → B7. B8 waits on D-2.

---

## 4. Decisions for tj (defaults apply if unaddressed)

- **D-1 naming padding** — default: 5-digit `xrefYYYYY` (site-file padding). The 4
  existing hand-named collection folders are **not** auto-renamed; the pipeline will
  propose canonical names if/when those folders pass through it.
- **D-2 ingest policy** — default: B8 stays report-only; new xref checksums continue
  to arrive via master import. Alternative: promote B8 to a reviewed import path.
- **D-3 legacy `gui/`** — default: frozen, no xref changes there (superseded by
  gui_next; its 4-digit naming remains only as a parse-input variant).

---

## 5. Definition of done (TODO-246)

1. Every surface listed in §1 is OK / fixed / explicitly frozen; no DEAD or WRONG
   verdicts remain.
2. A folder that is an xref fileset: lookup says MATCHED + `matched_xref`, pipeline
   names it `… (LB-XXXXX-xrefYYYYY)`, collection records `xref`, GUI shows the
   copy-level pill — end to end on one fixture.
3. Entry-level and copy-level indicators verifiably distinct (different i18n keys,
   different data sources).
4. `/gui-check` + backend test suite green; locales updated; PROJECT.md consistent
   with docs/XREF_SEMANTICS.md.
