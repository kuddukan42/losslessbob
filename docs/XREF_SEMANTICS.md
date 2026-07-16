# Xref semantics — the intended meaning (TODO-246 step 1)

Written 2026-07-15 against `data/losslessbob.db` and the `data/site/` mirror. This page
defines what an xref number *means*; step 2 audits every touchpoint against it. Nothing
below is aspirational — every claim was verified by query, and the queries are noted.

---

## 1. What an xref number is

For each LB entry, Jeff documents one **canonical fileset** (the checksums of the copy
the entry was written around) plus any **alternate circulating filesets** — usually
later bittorrents — that contain the *same recording* with different files (different
rip, lineage, tracking, or retracked/renamed copies).

Each alternate fileset gets a number from a **single global sequence**:
`xref-00001` onward (highest captured in our data: `xref-02151`). The number identifies
the *fileset*, and only the fileset:

- It is **not an LB number**. The two sequences are independent; any overlap in range
  is coincidence (paired entries' concert dates match in 1 of 1,871 cases).
- It is **not a flag**. `checksums.xref` is the fileset id, not a boolean —
  PROJECT.md's schema tables ("1 = cross-reference entry", "0 or 1") are wrong.
- Each xref id belongs to **exactly one LB** (0 collisions across 1,871 ids).

On the site, an xref fileset shows up in two places:

1. **The entry page commentary** — a parenthetical paragraph (torrent date, lineage
   quote, sample filenames) ending with the tag `xref-NNNNN`.
2. **Per-fileset site files** — `LBF-{lb:05d}-xref-{id:05d}-text.txt` (checksums),
   `…-lbdir.txt`, `…-DigiFlawFinder.html` in `data/site/files/` (5,575 files).

## 2. What `checksums.xref` means

- `xref = 0` → the row belongs to the **canonical fileset** of `lb_number`.
- `xref = N > 0` → the row belongs to **alternate fileset xref-N** of `lb_number`.

The unit of identity is the `(lb_number, xref)` group = one fileset. An xref fileset
**is** its `lb_number`'s recording; there is no cross-entry resolution to perform. A
copy matching group `(N, X)` is LB-N, in the xref-X packaging.

Scale (verified): 70,751 rows with `xref > 0`, 1,871 distinct ids, across 1,507 LBs;
LBs carry 1–4 xref groups (1,213 / 233 / 52 / 9).

Cross-validation: of 1,459 entries that have both `xref-NNNNN` tags in their page text
and xref checksum groups, **1,360 match exactly** (93%). Residue: 215 entries describe
an xref fileset with no checksums captured (no checksum file, or text-only mention);
48 LBs have xref checksums without a regex-detectable tag. Neither breaks the model.

## 3. What follows for the app — the one documented meaning

**Copy-level** (a folder / lookup result): matching group `(N, X)` means *"this is
LB-N, as the alternate circulating fileset xref-X, not the canonical rip."*
- Folder naming: `LB-N-xref{X:05d}`.
- Lookup status `XREF` = matched, but against an xref group.
- Completeness must be judged **within the group** — a complete xref-X copy is
  complete, even though it matches none of the canonical checksums
  (`backend/db.py` reverse lookup already does this correctly).

**Entry-level** (catalog metadata): "this entry has alternate filesets documented"
(`GET /api/checksums/xref_lb_numbers`; `xref_map` = `{lb_number: [xref ids]}`).
This is a property of the **entry**, not of anyone's copy.

**Badge rule:** those are two different statements. A badge on a *copy/folder* must
mean "your copy is an xref fileset"; a marker on a *catalog entry* must mean "alternate
filesets exist for this entry". One badge must never serve both meanings.

## 4. Where the data comes from (pipeline reality)

`checksums` rows — including xref — enter the DB **only via master import**
(`backend/importer.py` legacy path, `backend/flat_file.py` master format, which
carries the xref column). `backend/scraper.py` writes `entries` + `entry_files` only;
it never inserts checksum rows. Consequence: xref filesets Jeff publishes after the
master snapshot arrive only through a master re-import, never through scraping. The
raw material exists in the site mirror (`LBF-*-xref-*-text.txt`).

## 5. Known divergences (queue for step 2 audit)

| Where | Divergence |
|-------|-----------|
| PROJECT.md schema (×2) | Documents `xref` as a 0/1 flag — it's a fileset id. |
| `backend/app.py` `xref_map` docstring | Claims `{xref_id: lb_number}` — actual is `{lb_number: [xref ids]}`. |
| `tools/parse_dff_reports.py` | Reads `LBF-{lb}-xref-{id}` as "report for LB {id}" and attributes xref flaw reports to the xref id *as an LB number* — wrong entry for essentially all ~1,858 xref filesets. |
| Collection "Xref only" filter | Historically switched to `folder_name LIKE '%xref%'` (PROJECT.md 2026-05-16); gui_next now filters on `xref_lb_numbers` — an **entry-level** set applied to the user's copies, so it shows "entries that have xrefs", not "my copies that are xref filesets". Verify intent per screen. |
| `ScreenCollection` row pill | `isXref` pill on a collection row is driven by entry-level `xref_lb_numbers` — conflates the two meanings in §3. Audit all 9 GUI touchpoints for the same conflation. |
| Scraper | No path for new xref checksum files into `checksums` (§4) — decide whether master-import-only is the intended design or a gap to close. |
