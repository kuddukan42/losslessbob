# Show Dossier Redesign — Execution Plan

Spec: `instructions/Show Dossier Redesign.pdf` (Rev A, 2026-09-09).
Mock: `instructions/Show Dossier 2010-03-29 (standalone).html`.
Audit: `instructions/SHOW_DOSSIER_AUDIT.md`. It holds the rationale; every finding is folded
into the phases below, and IDs such as *audit M1* point back to its evidence.
Baseline: `backend/dossier.py` + `backend/templates/dossier.html` @ master `2026-08-20_003101`.

Every number below was measured against the live DB on 2026-09-10 unless marked "target".

## Context

The dossier should answer one question: *which copy of this show should I get, and why*.
Today it puts the reference material first, gives every source equal weight, and passes scraped
blobs straight through to the page. The spec reorders the page into seven sections, defines
~90 anchors and 13 data requirements (D-01…D-13), and sets two hard rules: every value must be
traceable to a source, and every field needs a defined null fallback.

Two findings shape this plan:
1. **Most §7 defects come from our Olof parser.** Two of the spec's own acceptance cases are
   also wrong for this reason. The chronicle itself is fine. So the parser is fixed first.
2. **Traceable is not the same as true.** The mock traces nearly every value to a real
   source, yet makes at least 12 false statements: unverified superlatives, propagated tapers,
   labels that claim more than their source measured (audit §4). So this plan adds database
   QC, cross-source corroboration, a per-dossier QC gate and a claim engine, and the template
   is built only after those exist.

**Guiding rule:** bad data is the enemy. When the pipeline can't verify a value, the page
shows the field's fallback and lists it as withheld. It never guesses.

## Decisions (tj, 2026-09-10)

| Topic | Decision |
|---|---|
| Reference mock | Added (`Show Dossier 2010-03-29 (standalone).html`). The template's layout follows the mock; its data rules follow this plan, not the mock (audit §4 lists 17 errors in the mock). |
| D-03 source | Olof release lines, classified against a hand-curated allowlist of official titles. Wolfgang's Vault, Westwood One radio discs and Crystal Cat bootlegs are **not official**. |
| Sibling-night links | `run.dates[].url` = relative `dossier-YYYY-MM-DD.html`, only when this install has `entries` for that date; otherwise the chip is unlinked. In inline (iframe) mode the link goes to `/api/dossier/html?date=…&inline=1` instead. |
| Gap badge | Fires when **≥100 Dylan concerts** have passed since the song's previous performance. |
| Label | "AI grade" becomes **"Scanned quality"** in every dossier output (HTML, BBcode, footer). GUI Library labels are out of scope. |
| Map | **Kept, compact, and inside the venue card.** This overrides the spec's removal. It pins the venue only when the venue coordinates are verified; otherwise it shows a hollow city-centre marker labelled "city centre (setlist.fm)". It is never a venue pin drawn from city coordinates. See `venue.map`. |
| Audit adopted | Everything in `SHOW_DOSSIER_AUDIT.md` §3–§9 is binding and folded in below. |

## Trust model (replaces the spec's `confidence` values)

| Level | Meaning | Rendering |
|---|---|---|
| `corroborated` | ≥2 independent sources agree | plain value; ✓ in the tooltip |
| `stated` | one source says so, and none contradicts it | plain value; source in the tooltip |
| `inferred` | derived by a rule | dotted underline and tooltip (§8.5) |
| `disputed` | sources disagree | the credited source's value plus a "disputed: X says Y" notice; never used for a superlative |
| `withheld` | blocked by the QC gate or an open finding | the field's fallback; listed in `prov.withheld[]` |
| `unavailable` | no source | the field's fallback |

- **Tier ≠ truth.** T1 means the data is available, not that it's correct.
- **Independence rule.** Two sources count as independent only if neither was derived from the
  other. A taper propagated through a family can't corroborate that family.
- Every `Field` carries `derived_from`, and the gate rejects evidence cycles.

## Probe findings

### Parser and source data

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | The Olof song walk stops at guest-set headers (`Bob Neuwirth:`, `Tom Petty & The Heartbreakers:`). | 1975-12-08 parses **0 songs**; 1986-02-24 parses **7 of 25**. Corpus-wide: 99 concerts with 0 songs, 434 truncated. bobdylan.com and TUIT both list 25 songs for 1986-02-24 and 22 for 1975-12-08. | Phase 1 P1a. The spec's D-09 case is wrong: after the fix, 1986-02-24 reads *complete, 25 songs*. |
| F2 | Venue-history date lines (`1 March 1978`) and the rotation-stat line are parsed as per-song notes. | 6,214 + 2,686 rows. | P1b, P1d (spec §7.2). |
| F3 | The "Other Bob Dylan shows in X" blob sits in `notes`. | 80 events. It's frozen when Olof wrote the page: the corpus has 50 Tokyo concerts, the blob 45. | P1c. `city_history` is built from the corpus. |
| F4 | Subtitles are stored as credits, and long composer credits are left inside the title. | `And I'll Go Mine` ×486; `My Wife's Home Town (…)`. | P1e. |
| F5 | Olof's rotation and tour-premiere stats can be recovered. | 2,707 events. | T1 for `stats.rotation` / `stats.premiere_count`. |
| F6 | Our tour-premiere recompute agrees with Olof's count on only 90.2% of shows; rotation agrees on 86.0%. | Truncation (F1) and tour-boundary cases. | D-02 and D-04 gates, plus corroboration. |
| F7 | `quality_recording_metrics.completeness` is NULL in every row. | 21,788 rows. | D-01 must be computed. |
| F8 | Per-source tracklists exist only as free text in `entries.setlist`. TUIT has a second one. | 13,137 LBs; 3,881 have both, and their lengths agree within ±2 tracks for 82%. | D-01 plus corroboration. |
| F9 | No catalog date-added exists anywhere. | `lb_master.first_seen_at` is install-relative. | D-12 ships its null path only. |
| F10 | File-level metadata exists only in TUIT. | 5,068 `lb_verified` rows. LB-08485's file is FLAC 16/44 (714 MB for 126 min); its lineage "24bit/96kHz" is the recorder setting. | D-11 file-record precedence. The mock's "only 24/96 transfer" is false (audit M1). |
| F11 | All 18 sources for 1965-06-01 have `lb_category='tv'`. | 92 tv, 9 radio corpus-wide. | D-13 signal. |
| F12 | Olof city/country fields are inconsistent. | 2,705 concerts with an empty country. setlist.fm covers 3,983 of 4,222 concerts. | D-07 groups cities by the setlist.fm key. |
| F13 | Family `conf` is the mean pairwise waveform correlation, plus 0.05 for a quality match; `by='ai+lb'` means the LB page says "same source". | `tapematch_sync.py:354-363`. | `family.basis` is derived at render time. |
| F14 | Template output is 37% blank lines. | Masthead at line 383. | Phase 6. |
| F15 | The `review` badge fires on every family for 2 of the 5 sample shows. | 2,156 flagged families. | Remove it; §8.5's tag replaces it. |

### Data-quality findings (from the audit)

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F16 | Taper propagation matches bare text mentions. | 3,683 attributions. LB-08493's "mike millard" comes from the gear name "MM-EBM-1", and Millard died in 1994. Another 168 were propagated through review-flagged families and 510 fall outside the taper's era. | Phase 2 fixes plus quarantine (audit D5–D7). |
| F17 | Derived tables are stale. | `show_picks` (08-31) is older than `recording_families` (09-04). 114 LBs have newer metrics than scores. 383 LBs lose their grade because the code reads only the global `MAX(scan_id)`. | Phase 2 fixes plus gate G6 (audit P7, P8). |
| F18 | setlist.fm coordinates are city centroids. | 48 Tokyo dates share one point. The geocoder also matched Zepp Tokyo to Zepp DiverCity (1,141 low-confidence rows). | C6 venue rule (audit M11, M12). |
| F19 | Mis-dated and compilation catalog entries land on shows. | LB-06654 (a studio mono-mixes compilation) matches 0 of 12 songs on 1965-06-01. Multi-date compilations appear on 1986-02-24. | Gate G2 (audit S11). |
| F20 | Olof's "2010 Tour of Japan" ends in Seoul on 2010-03-31. | — | 2010-03-29 `is_last` is **false** (audit M4). |
| F21 | The true 2010-03-29 tour premieres are songs 4 and 14 (My Wife's Home Town, Forever Young). The mock guessed 13 and 16. | Our corpus count matches Olof's count of 2. | D-02 acceptance case (audit M5). |
| F22 | Independent setlist sources are already in the DB. | Equal song counts vs Olof: setlist.fm 90.8%, bobdylan.com 79.9%, TUIT 69.2%. | Q1 setlist quorum. |

## Architecture

- **Keep** the D1 JSON payload from `build_dossier()`. `/api/dossier`, `render_bbcode()` and
  the existing tests depend on it.

**New modules:**

| Module | Role |
|---|---|
| `backend/qc/rules.py`, `backend/qc/__main__.py` | Database QC rules → `qc_findings`. CLI: `.venv/bin/python3 -m backend.qc run [--rule ID]`. |
| `backend/qc/corroborate.py` | Cross-source agreement: setlists, tracklists, file format, taper, venue. |
| `backend/dossier_fields.py` | Pure derivations D-01…D-13 plus the supporting parsers. Read-only. |
| `backend/dossier_claims.py` | Claim engine. The only producer of comparative or positional wording. |
| `backend/dossier_anchors.py` | `ANCHORS` registry (spec §6), `Field` shape, `build_view(d1, conn, link_mode)`. |
| `backend/dossier_qc.py` | Per-dossier gate G1–G9; writes `dossier["qc"]`. |
| `backend/qc/review.py` + `backend/qc_review.html` | QC review console at `/qc-review` (Phase 2b), modelled on the taper-curation pages. |

**`Field` shape:** `{value, tier, source, confidence, derived_from[]}`. Confidence uses the
trust model above.

**Flow:** `build_dossier()` → D1 payload → `build_view` → `dossier_qc.gate(view)` →
`dossier["view"]` + `dossier["qc"]`. The template renders **only** from `view`, and every
anchor element carries `data-lb="<key>"`.

**Storage:**
- New Olof columns (Phase 1).
- New USER tables `qc_findings` and `corrections` (Phase 2). Both are local-only and never in
  the master export.
- Everything else is computed per dossier. Staleness is still possible *upstream*, and gate G6
  catches it.

---

## Chunks & progress

One row = one commit, through `/session-close` and pushed. **Resume at the first row not
`done`.** Flip a row to `done` in that chunk's own commit. Its commit subject ends
`[dossier Cnn]`, so `git log --grep 'dossier C07'` finds it.

- **Order:** the phase order is binding (see Execution notes), with one deviation. C13 pulls
  the D-01 track matcher ahead of Phase 3, because the 3a quorum and R-E2 both align titles
  with it.
- **Tests ship with their chunk.** The Phase 8 list is the union of these tests, not a separate
  later chunk.
- **PROJECT.md** sections are updated in the chunk that adds the schema, route or file.
- **Sign-off** marks a chunk that stops for tj before it merges. Chunks that aren't marked
  don't wait for him.

> **Resume here (2026-09-11).** C00–C21 are done and **BUG-347 is closed**: the parser repair,
> the two-page reparse (diff gate changed 2 / B347 2 / UNEXPLAINED 0), `song_index.run()`
> (70,711 performances), `backend.qc run` (R-O4 −12) and `--d07` **5/5** all landed. Rollback
> snapshot if ever needed: `.debug/olof_before_bug347.db`.
>
> **Next: C23** (supporting parsers). C22 landed 2026-09-11: `setlist_confidence()`, `file_meta()`,
> `--d09` both accept cases PASS, constants calibrated in `.debug/dossier_calibration.md`.
>
> Pending with tj: the C19 allowlist sign-off (`backend/assets/official_releases.json`) and
> the C21 100-row generation audit (`.debug/d05_audit.txt`; its three rule questions are
> decided).

| # | Ph | Scope | Needs | Model | Done when | Status |
|---|---|---|---|---|---|---|
| C00 | 0 | Ledger: redesign TODO + the Phase 0 BUGs; branch `feat/dossier-redesign` | — | orch. | IDs: TODO-342; BUG-340 (F1), 341 (F2), 342 (F4), 343 (F14), 344 (F16), 345 (F17), 346 (NULL-date picks) | done |
| C01 | 1 | New Olof columns (idempotent) + upsert lists; `tools/olof_reparse_diff.py`; `tools/dossier_acceptance.py --parser` baseline. No parser behaviour change | C00 | orch. | `init_db` twice is clean; baseline counts recorded: 84 zero-song concerts (82 with numbered songs on the page), 352 truncated, 6,222 date-line annotation rows, 2,714 stat annotation rows, 1,867 events with the stat in notes/releases, 3,102 pages state the stat, 80 venue blobs in notes, 306 `And I'll Go Mine` credits, 292 titles ending in a composer credit; 0/9 checks pass (`.debug/dossier_acceptance_parser_baseline.txt`). Counts differ from the audit's (99 / 434 / 6,214 / 2,686 / 2,707 / 486) because the method differs; this tool's numbers are the gate from here on | done |
| C02 | 1 | P1a guest/interlude blocks + P1g section guard | C01 | opus | fixture tests: 1975-12-08 = 22, 1986-02-24 = 25 (also on the real pages). In-memory HEAD-vs-new over all DSN pages: zero-song concerts 84 → 21, truncated 352 → 236, +2,867 songs in 185 events, 0 songs lost, 0 release changes; the only annotation changes are 306 rotation-stat fragments dropped (P1d). P1g keeps range/list, release and recording lines inside prose, and ends a section at `Unauthorized releases` / `Releases` / `Official release` / `Bootlegs` too. Live DB not reparsed (C05) | done |
| C03 | 1 | P1b date lines, P1c venue-history blob, P1d rotation stat → new columns | C01 | opus | fixture tests for each fix. In-memory HEAD-vs-new over all DSN pages, classified by `olof_reparse_diff.classify_event`: 0 UNEXPLAINED; P1d 3,104 events (stat parsed on 3,104 / 3,104 pages, 0 left in section text or annotations); P1c 1,193 events — the list is far wider than the audit's 80 "Other … shows in" blobs (header variants `Other/Previous/Next … concerts in`, typos, Swedish months, ranges, same-line venue); P1b 1,213 events, 0 date-line annotation rows. 243 list headers stay in notes: pointer lines with no dated entries. Hedged tour counts (`Probably`, `possible`) → `tour_new_count` NULL. The diff gate now also moves text out of `bobtalk` / `references_raw` (the stat sits there on 329 events). Live DB not reparsed (C05) | done |
| C04 | 1 | P1e credits vs subtitle, P1f release lines | C01 | opus | fixture tests (1965-06-01, `and part of 22`). In-memory C03-vs-new over all DSN pages: 0 UNEXPLAINED; P1e 2,170 events — 2,670 songs get a subtitle from a curated list of 16 Olof alternate titles, 528 titles shed a composer credit (0 left), 0 `And I'll Go Mine` credits; P1f 154 events — `released in/as`, `available as/from` lines leave annotations (0 left), `and part of N` → `(part) ` prefix (12 songs), positions beside an `or` → `(uncertain) ` (27 songs), 0 `and part of` tokens. `_split_title_credits` (bobserve / chronicle) unchanged; the DSN walk uses `_split_title_parts`. Live DB not reparsed (C05) | done |
| C05 | 1 | Full reparse → diff gate → `song_index.run()` | C02–C04 | orch. | UNEXPLAINED = 0; `--parser` PASS; counts in CHANGELOG; F1/F2/F4 BUGs closed. Done: full DB backup `.debug/losslessbob_preC05.db`, snapshot, reparse (214 pages, 0 errors); diff 3,589 changed events, **UNEXPLAINED 0** (P1a 185, P1b 1,211, P1c 1,192, P1d 3,102, P1e 2,052, P1f 151); `--parser` **9/9** (the venue-list metric now needs a day + month after the header — 7 pointer headers followed by release lines were false positives); `song_performances` 67,844 → 70,711. BUG-340/341/342 closed. BUG-337 **not** fixed by Phase 1 (27 split title keys, 941 stranded rows — spacing artifacts like `Tim es`, `Blowin '`); stays open | done |
| C06 | 2 | `backend/qc/` package + CLI; all five tables; `evidence_hash` reopen; quarantine lookup; rules R-O1, R-O3 | C05 | sonnet | `python -m backend.qc run` prints per-rule counts; reopen test. Done: live baseline R-O1 **255** open (236 truncated + 19 zero-song with numbered lines — the C05 residuals), R-O3 **0**; a re-run is idempotent (0 new / fixed / reopened). `tests/test_qc.py` covers open → fixed → reopened and false_positive stays / reopens on evidence change. Reopen and fixed transitions overwrite `decided_by`/`decided_at` with `qc-run`; the curator's decision survives in `qc_decision_log` | done |
| C07 | 2 | Rules R-O2, R-G1, R-E1, R-F1, R-S1 | C06 | sonnet | one test per rule; baseline counts in CHANGELOG. Done: R-O2 193, R-G1 576, R-E1 26, R-F1 2,371, R-S1 115 (114 LBs measured after the scan-18 rerank + stale `show_picks`). R-G1 reads the POI from `venue_geocoded.note` (there is no `display_name` column) and fires on renamed venues too, so expect false positives in the 2b queue. R-S1's per-LB check means "metrics newer than the last rerank", not "no score": the 2,117 LBs scan 18 left unscored are not stale | done |
| C08 | 2 | Upstream fix 1 (taper: no bare mention, no weak-family propagation) + R-T1–R-T3; re-run tapers | C06 | opus | 0 open R-T1/R-T2 on the five samples; LB-08493 has no Millard; F16 BUG closed. Done: before → after the fix, R-T1 **3,286 → 0**, R-T2 **473 → 0**, R-T3 **510 → 139** (107 are `spot`; they stay open and quarantine). A mention now needs a taper-context phrase directly before the handle (`taped/recorded/recording/master by`, `taper`); `mastered by` / `transferred by` don't count. Families propagate only at conf ≥ 0.5 and not review-flagged; `_propagate_weak` deleted. Attributions 8,715 → 4,968 (confirmed 3,846 unchanged, propagated 4,869 → 1,122, conflicts 396 → 68). LB-08493 has no attribution; 0 open R-T findings on the 60 LBs of the four sample dates in the plan (2010-03-29, 1986-02-24, 1975-12-08, 1965-06-01). Also fixed: `tools/attribute_tapers.py` never loaded `user_taper_aliases`, so a CLI run dropped 272 confirmed rows for curated tapers. BUG-344 closed | done |
| C09 | 2 | Upstream fixes 2–3: picks after families, NULL-date skip, per-LB latest scored scan; queue the 114-LB rerank | C07 | sonnet | R-S1 count drops; the 383 LBs have grades; F17 + NULL-date BUGs closed. Done: R-S1 **115 → 0**; NULL-date picks **589 → 0** (all 112 NULL-iso `concert_date`s were partial `xx` dates). Both audit premises were wrong: the 383 "lost" grades belong to LBs the scan-18 rerank filters on purpose (312 non-concert, 71 < 30 min), so they stay ungraded; the 114 "unscored" LBs were calibration re-measurements (scans 21/22) of LBs already in scan 18, so no rerank is queued. Grade readers (dossier, song_index, db, `/api/quality`, picks) now use `repo.scored_scan_id` (the scan with the most score rows) instead of `MAX(scan_id)`; `concert_ranker rerank` defaults to the reusable scan, not the newest, which would have moved every grade to a 21-LB scan. R-S1 per-LB = main-scan metrics measured after the last `ranker_rerank`. `tapematch_sync` (CLI + route) re-runs tapers → picks after a family sync. BUG-345/346 closed | done |
| C10 | 2 | Upstream fix 4: TUIT taper names → `user_taper_aliases`; rule R-T4 | C08 | sonnet | R-T4 count measured after mapping. Done: R-T4 **69** open (warn), the same before and after mapping; **67** after C11 dropped not-a-taper TUIT handles (`dolphinsmile`). The audit's 743 was a raw-string comparison: `_normalise_taper` already resolves "Legendary Taper D" → `ltd` and the NT forms, so of 1,309 joined LBs only 69 disagree. `tools/map_tuit_taper_aliases.py` adds only mechanical spelling folds — 5 rows (`tapeboy` → `tape boy`, `zimmy 21`, `krewe chief`, `captainsimard`, `s h`). The residue is judgement pairs (`UK C`/`SY` vs `lta`, `cb` vs `ltb`, `rb-canada` vs `net taper g`, "Taper Bt" vs `bt`) for the 2b queue. A TUIT field agrees when any part matches (`taper_curation.tuit_taper_parts` splits on `, ; / ( ) = … & and`); placeholders are skipped | done |
| C11 | 2b | `backend/qc/review.py`, GET routes, page shell + Findings tab | C07 | sonnet | read-route tests. Done: `backend/qc/review.py` + 5 GET routes + `backend/qc_review.html` (Findings tab with filters, pager, detail drawer; Queue tab placeholder); 22 tests in `tests/test_qc_review.py`. Venue findings resolve dates through one `olof_events` index per request. R-F1 has a family context panel too (not in the spec's list) | done |
| C12 | 2b | Write routes + curator 403, Queue tab (cards, keys), `queues.py` entries | C11 | sonnet | 2b acceptance 2, 4, 5; steps 1 and 3 re-checked at C29. **tj can now work findings in parallel**. Done: `backend/qc/decisions.py` (decide / bulk one-rule all-or-nothing / add_correction; `fixed` and `corrected` → 409), `backend/qc/jobs.py` (JobState rules run), 5 routes (every POST curator-gated), Queue tab (cards, per-family evidence, Reject attribution, keys `c f e s j k o`, modifier keys ignored, localStorage resume), Findings bulk bar, `qc_errors` gate + `qc_warnings` backlog queues (both `screen=None`, `blocks=()`). 33 tests in `tests/test_qc_decisions.py` (acceptance 2 and 4); acceptance 5 checked in Chromium against the live page (resume after j/j and skip survive reload, 0 console errors). `POST /api/qc/releases/<title_key>` moves to C19 with R-R1. Live queue at C12: 3,627 open (970 errors, 2,657 warnings) | done |
| C13 | 4* | `clean_track_title()`, `match_track()`, `_ENTRY_TRACK_MARKER_RE` fix; rule R-E2 | C06 | opus | matcher tests; LB-08477 = 18 tracks. Done: the "18 tracks" premise was false — 18 is Olof's 2010-03-29 song count; LB-08477's own list is Introduction + 12 songs (10 → 13 split titles after the fix), all 12 match. `backend/dossier_fields.py` holds `clean_track_title`, `parse_entry_tracklist` (partial / missing flags), `build_setlist_index`, `match_track` (exact → base → `song_canonical` alias → containment). Marker fix: 141 of 13,137 live setlists change, all upward (+768 titles). R-E2 (error) = share of the entry's song tracks matching the union of the date's Olof songs < 20%, ≥ 3 song tracks, skipping glued tracklists (12) and entries covering ≥ 50% of the date's Olof songs (33 — Olof lists a subset): **70** open. LB-06654 fires 0/25; LB-10364 1/1 and LB-08855 8/8 (2 missing tracks) don't. Known miss: "Girl Of The North Country" needs a `song_canonical` row | done |
| C14 | 3 | 3a setlist quorum + rule R-O4 | C05, C13 | sonnet | `--corroborate`: both samples `corroborated` now, `disputed` against `.debug/olof_before.db`; shares in CHANGELOG. Done: `backend/qc/corroborate.py` (`setlist_quorum` per date, `corroborate_all` corpus pass, shared `quorum_verdict`); `--corroborate` **4/4**. Shares over 4,494 dated concerts: corroborated 81.1%, stated 8.1%, disputed 7.2%, unavailable 3.6%. TUIT has no running order (`id` is alphabetical), so it agrees on set only. A source agrees within 1 song each way. R-O4 **325** open: 292 error (198 on events R-O1 already flags as truncated; the rest mostly Olof listing a subset, e.g. the 1965 UK tour) + 33 **warn** for order-only disputes (a swapped pair shouldn't withhold the setlist). `store.run_rule` now refreshes a finding's severity on re-run. Talkin'/Talking spellings and Olof placeholders ("Unidentified …", "… Riffs") are folded before comparing | done |
| C15 | 3 | 3b premieres & rotation recompute; 3c tracklist vs TUIT | C14 | sonnet | `tests/test_corroborate.py`. Done: `tour_premieres`, `rotation_check`, `tracklist_check` in `backend/qc/corroborate.py`, no new tables or rules. `--premieres`: 2010-03-29 premieres at positions 4 and 14, count 2 = `tour_new_count` (PASS). setlist.fm's own `tour_name` is one "Never Ending Tour" bucket for NET shows, so setlist.fm rarely confirms a NET premiere — weigh at C18. Rotation: previous concert = preceding concert-filtered `olof_events` row, not tour/venue scoped; 87.3% of 3,068 stated events agree (residual mostly thin 1974 listings). LB vs TUIT tracklists (set + count): 76.4% of 3,816. 23 tests | done |
| C16 | 3 | 3d file format, 3e taper, 3f venue / city | C10, C14 | sonnet | `tests/test_corroborate.py`. Done: `file_format_check`, `taper_check` (shares `taper_agreement` with R-T4, still 67), `venue_check` + corpus passes in `backend/qc/corroborate.py`; `parse_resolution_tokens` is the D-11 regex. 3d over 5,068 verified LBs: 4,568 file record only, 170 documented conversions agree and 2 don't, 131 state one figure equal to the file, 123 state only a differing recorder figure (read "recorded X", not a conflict). 3e: 1,234 / 1,301 corroborated. 3f: 3,362 / 4,057 dates corroborated on exact folded venue name; of 695 disputed, **666 agree on city** — see C28. Also fixed two C15 bugs: `tour_premieres` now scopes setlist.fm history to our tour's date span (setlist.fm's `tour_name` is one "Never Ending Tour" bucket), and `setlist_json='[]'` reads as no tracklist | done |
| C17 | 4 | D-01 completeness + G2 fit flag | C13, C15 | opus | D-01 accept cases (2010-03-29, 1965-06-01). Done: `completeness(conn, event_id, lb_numbers)` + `fits_show()` in `backend/dossier_fields.py`; all accept cases pass (`--d01`). Takes an `event_id`, so the caller's event pick matters: corpus-wide, 60 sources fail G2 against their date's own events, but 193 more fail only against the date's *primary* event while fitting a sibling (early/late shows, TV spots). TUIT confidence: corroborated 2,498, stated 8,579, inferred 1,201. Matcher now ignores spacing and folds Talkin'; cleaning fixes for "(encore break)", "Encore 1", slash-glued intros | done |
| C18 | 4 | D-02 song history + three-part gate + gap badge | C15 | opus | 2010-03-29 badges songs 4 and 14 only; `--d02` rate in CHANGELOG. Done: `song_history(conn, event_id)` in `backend/dossier_fields.py` (86 ms on 2010-03-29, ~50 ms/show). Premieres reuse `corroborate.tour_premieres`; a song played twice in a show (210 events) premieres at its first position only. `--d02` (seed 342): the gate passes on **93 / 200** sampled concerts (46.5%), 193 premiere badges, 13 gap badges. Failing items: 60 an open R-O1/R-O4 somewhere earlier in the tour (item 3 blocks a whole tour on one truncated setlist), 53 no `tour_new_count` from Olof, 31 setlist.fm doesn't confirm, 11 count mismatch | done |
| C19 | 4 | D-03: draft `official_releases.json`, `official_release()`, rule R-R1 | C05, C06 | sonnet | D-03 accept cases. **Sign-off: allowlist**. Done (sign-off pending): `backend/assets/official_releases.json` 84 entries (73 official / 11 not), `official_release()`, R-R1 (535 open), `POST /api/qc/releases/<title_key>` + queue card. Multi-release strings take the release named earliest. `--d03` passes; **1975-12-08 reads `partial`, not `none`**: song 5 is on CD 14 of the 2019 Rolling Thunder Revue box | done |
| C20 | 4 | D-07 run / tour / city history, then D-04 rotation rank | C15 | sonnet | night 7 of 7, `is_last` false, Tokyo = 50; sum assertion; synthetic tie → no superlative. Done: `run_context()` + `rotation_rank()` in `backend/dossier_fields.py` (~42 ms each). 2010-03-29: tour 14 of 15 (`is_last` false), Zepp Tokyo night 7 of 7, Tokyo = 50 with Tokyo Garden Theater ×5 in 2023, sum invariant holds. 72% ranks 1 of 7 and `superlative_ok` is **true** since **BUG-347** was fixed (2026-09-11): Olof's page had spliced a credit into "Like A Rolling Stone", so nights 1–2 didn't verify; all 7 nights verify now and the claim renders. Synthetic tie → no superlative (tested) | done |
| C21 | 4 | D-05 generation, D-13 medium (incl. the broadcast-taper R-T finding) | C08 | sonnet | D-05 / D-13 accept cases. **Sign-off: 100-row generation audit**. Done (sign-off pending): `classify_generation()`, `classify_medium()` (audio / audio_from_video + a broadcast flag, so an audience DVD keeps its taper), `media_available()`, rule R-T5 (4 open). `--d05` 6/6; the audit table is in `.debug/d05_audit.txt`. Rules decided by tj (2026-09-11): LB-08637's `bootleg_titles` row makes it silver (accept case changed from unknown); "master" followed by a clone is low_gen (451 LBs); a silver disc needs no label or catalogue number (+15). The 100-row audit table is still his to review | done |
| C22 | 4 | D-09 setlist confidence + `.debug/dossier_calibration.md`; D-11 file meta | C14 | sonnet | 1986-02-24 complete / 25 / corroborated; LB-08485 "16/44 file · recorded 24/96". Done: `setlist_confidence()` + `file_meta()` in `backend/dossier_fields.py`, `--d09` (both accept cases PASS), 18 tests. Constants calibrated in `.debug/dossier_calibration.md`: `_MINS_PER_SONG` 6.33 (corpus median `recording_mins / song_count`, n=3,089) and a runtime gap threshold of **5**, picked against the quorum verdicts as ground truth — 1.7% false `partial` on corroborated dates for 42% recall on disputed, vs 8.8% / 47.7% at 3. The secondary signal only runs on quorum `stated`. Corpus: 3,994 complete, 338 partial, 162 unavailable of 4,494. Review fix: the disputed notice now leads with **our** count (the external sources usually agree with each other), which exposes that most recent-year disputes are dates where Olof parses 0 songs — R-O1 queue work, not a D-09 defect | done |
| C23 | 4 | Supporting parsers (band, members, instruments, tally, writers, `set[].label`, character / flags, lineage_short, runtime, `family.basis`, taper render rule) | C04, C08 | sonnet | parser tests; runtime split sums to total | todo |
| C24 | 4 | D-08 pairwise comparison; D-10 bobtalk anchoring | C17, C22 | sonnet | D-08 / D-10 accept cases | todo |
| C25 | 5 | `dossier_anchors.py`: `Field`, full `ANCHORS` map (D-06 / D-12 as null stubs), `build_view`; `dossier["view"]`; `filter_dossier_sections(local_analysis=0)` | C17–C24 | sonnet | D1 payload unchanged (existing `test_dossier.py` passes); every anchor's fallback tested | todo |
| C26 | 5 | Claim engine + T4 slot templates | C25 | opus | `tests/test_dossier_claims.py` (ties, partial scope, disputed input → no claim) | todo |
| C27 | 5 | §8 selection rules: fragments (7.4), verdict pick, collapse, families, confidence, tape wording | C26 | sonnet | 300-show histogram in `.debug/`. **Sign-off: 60% fragment threshold** | todo |
| C28 | 5 | `dossier_qc.py` gate G1–G9, 422 refusals, `prov.withheld`, lint L1 | C27 | sonnet | `tests/test_dossier_qc.py` pass + fail per check; <100 ms. **Decided (tj, 2026-09-11):** G1 passes when the venue *or* the city agrees with ≥1 source; a city-only match renders a venue-name notice. Exact venue match alone would have refused 695 of 4,057 shows, 666 of which agree on city ("Stadio Communale" / "Stadio Comunale") | todo |
| C29 | 6–7 | Template rewrite: sections, `lbf` / `claim` macros, palette, "Scanned quality" (HTML / BBcode / footer), QC footer + `lb-qc` JSON, 7.5–7.8, lint L2 | C28 | sonnet | L1 / L2, anchor coverage, blank lines <5%; 2b acceptance 1 and 3; `/verify` Tier A on 2010-03-29 + 1965-06-01, light and dark | todo |
| C30 | 7 | Compact map: `marker` param, ~240×150, venue card, `view.venue.coords`, L1 pin rule | C29 | sonnet | 2010-03-29 hollow ring; one verified-`high` show gets a solid pin | todo |
| C31 | 8 | `tools/make_fixture_db.py` + golden-set harness, run in CI | C30 | sonnet | harness runs green on placeholder files | todo |
| C32 | 8 | Golden values for the 15 shows | C31 | orch. | **Sign-off: tj hand-verifies every file** | todo |
| C33 | 8 | `tools/dossier_sweep.py` + nightly cron + push on rise; `tools/dossier_verify_export.py` | C28 | sonnet | sweep report written; export drift detected on a doctored file | todo |
| C34 | 8 | Full verification in the Phase 8 order of checks, incl. `/verify --electron` PDF | C32, C33 | orch. | `--all` PASS; sweep totals in CHANGELOG | todo |
| C35 | 9 | `/wiki-update` pages + new Data-Quality page; close the redesign TODO + remaining BUGs; open follow-up TODOs; merge to `main` (tj) | C34 | orch. | ledger consistent; merged | todo |

\* C13 is Phase 4 work pulled forward; see *Order* above.

## Phase 0 — Prerequisites

1. The mock is in `instructions/`. Its data is **not** authoritative (audit §4).
2. Open ledger entries via `tools/ledger.py`:
   - TODO "Show Dossier redesign (spec Rev A)".
   - BUGs for F1, F2, F4, F14, F16 (taper mention and weak-family propagation), F17 (picks
     computed before families; per-LB scan selection) and the NULL-date rank-1 bucket in
     `show_picks`.
3. Branch `feat/dossier-redesign`. Cut from `todo-312-taper-curation-console` @ `08493b2f`, not
   `main`: `main` lacks this plan and the TUIT tables/scrapers that F8, F10 and F22 rely on.
4. Related open bug: BUG-337 (Olof song-title spacing/encoding splits in `song_canonical`) sits in
   the same parser. Check whether C02–C05 fix it; if not, it stays open and C05's diff must not
   mask it.

## Phase 1 — Olof parser fixes + reparse diff gate

File: `backend/olof_parser.py`. Change `_parse_song_lines` (583-670),
`_resolve_annotations_and_releases` (673-720), `_split_title_credits` (533-557),
`_extract_sections` (468-500), and the regex block (164-189).

| Fix | Change | Baseline → target |
|---|---|---|
| P1a Guest/interlude blocks | A line ≤60 chars ending `:` that isn't a section keyword (`BobTalk:`, `Notes`, `CO-numbers:`, `Cue sheet:`) is a guest header. Skip it and the unnumbered titles after it until the next `N.` / bare `N.` marker. If a special line or `_LINEUP_RE` line comes before any song marker, stop at the header. Guest songs are not stored. | 99 zero-song concerts and 434 truncated → re-measure; list every residual case |
| P1b Date lines | `^\d{1,2}\s+<Month>\s+\d{4}\.?$` is never a position list | 6,214 bogus annotations → 0 |
| P1c Venue-history blob | The header plus its date/venue lines move from `notes` into a new column `venue_history_raw`, and are excluded from the annotation scan | 80 events |
| P1d Rotation stat | `(N|No|One) new songs? \((P)%\) compared to previous concert\.? (N|No|One) new songs? for this tour` → new columns `rotation_new`, `rotation_pct`, `tour_new_count`; stripped from `notes` / `releases_raw` / annotations | 2,707 events populated; 2,686 bogus notes → 0 |
| P1e Credits vs subtitle | A parenthetical with composer markers (`/`, a `-`/`–` between capitalised names, `&`, a comma between names, `trad`, `?`) is `credits`, whatever its length. Otherwise it goes to new column `olof_songs.subtitle`. `song_title` stays the main title, so `song_norm` stays stable. Credits and subtitles are stored exactly as Olof spells them ("Wille Dixon" stays); corrections only through Phase 2's `corrections` table. | subtitles and credits correctly split |
| P1f Release lines | Keywords become `released (on|in|as)` / `available (on|as)`; `and part of N` marks N as partial | 1986 song 4 clean |
| P1g Section guard | Lines inside the bobtalk and references sections are never position lists | — |

- **P1e caution (found in C01):** single-writer credits carry none of the listed markers —
  1986-02-24 has `I'm Moving On (Hank Snow)`, `Uranium Rock (Warren Smith)`; 1975-12-08 has
  `(Ned Albright)`, `(Joni Mitchell)`. The marker rule alone would file these as subtitles. C04
  must keep a parenthetical that reads as a person's name (or matches a writer already seen in
  `olof_songs.credits`) in `credits`, and send only known alternate titles to `subtitle`.
- **Schema** (`backend/db.py` `init_db`, idempotent `PRAGMA table_info` checks, then `ALTER`):
  - `olof_events`: add `rotation_new`, `rotation_pct`, `tour_new_count` (INTEGER) and
    `venue_history_raw` (TEXT DEFAULT '').
  - `olof_songs`: add `subtitle` (TEXT DEFAULT '').
  - Update the upsert column lists and the song tuple at line 192.
  - Rows with `source='bobserve'` (2022+) are untouched; their new columns stay NULL, and the
    gates fall back.
- **Reparse diff gate (audit P9):**
  - `tools/olof_reparse_diff.py` snapshots `olof_events` / `olof_songs` into
    `.debug/olof_before.db`.
  - Run the full reparse (`.venv/bin/python3 -m backend.olof_parser`).
  - Diff into `.debug/olof_reparse_diff.md`, bucketing every changed event by the fix that
    explains it (P1a–P1g). Anything unexplained lands in **UNEXPLAINED**, and **any
    UNEXPLAINED change blocks the commit** until it's understood.
  - Then rebuild `song_performances` via `backend/song_index.run()`.
- **Tests:** `tests/test_olof_parser_fixes.py`, with inline HTML fixtures modelled on the
  1975-12-08 guest blocks, the 1986-02-24 interludes, the 2010-03-29 blob and stat line,
  1965-06-01's `It's Alright, Ma (I'm Only Bleeding)`, and 1986's `and part of 22`.
- **Acceptance:** `tools/dossier_acceptance.py --parser` prints the corpus counts before and
  after. The 1986-02-24 and 1975-12-08 song counts must equal bobdylan.com/TUIT (25 / 22).

## Phase 2 — Database QC, quarantine & upstream fixes (audit Q0, Q5)

**Tables** (`CREATE TABLE IF NOT EXISTS`; USER, local-only):
- `qc_findings(id, rule_id, entity_kind, entity_key, severity[error|warn|info], detail,
  evidence_json, evidence_hash, first_seen, last_seen,
  status[open|confirmed|false_positive|corrected|fixed], decided_by, decided_at, note)`,
  unique on `(rule_id, entity_kind, entity_key)`. The status values are defined in Phase 2b.
- `qc_decision_log(id, finding_id, rule_id, entity_key, prev_status, new_status, note,
  decided_by, decided_at)`: append-only; mirrors `taper_decision_log`.
- `qc_runs(run_id, rule_id, started_at, finished_at, n_open, n_new, n_fixed, n_reopened)`:
  per-rule history for trend lines.
- `release_classifications(title_key, official, decided_by, decided_at, note)`: curator verdicts
  on release titles. D-03 reads the asset allowlist plus this table, and the table wins.
- `corrections(entity_kind, entity_key, field, original, corrected, reason, decided_by,
  decided_at)`. Source tables are never edited in place.

**Rules** (`backend/qc/rules.py`; one pure function each; run after every ingest and derived
step, and nightly):

| Rule | Checks | Severity |
|---|---|---|
| R-O1 | Olof raw numbered-song count > parsed count | error |
| R-O2 | Olof city/country anomalies | warn |
| R-O3 | Date-shaped or stat-shaped song annotations | error |
| R-O4 | Olof setlist disagrees with ≥2 agreeing independent sources (Phase 3) | error |
| R-T1 | Taper evidence is a bare mention with no taper-context pattern ("taped by", "recorded by", "master by", "taper:") | error |
| R-T2 | Taper propagated through a family with `review_flag=1` or conf < 0.5 | error |
| R-T3 | Propagated taper more than 5 years outside the taper's confirmed years | error |
| R-T4 | Taper disagrees with TUIT after alias mapping | warn → `disputed` |
| R-G1 | `venue_geocoded` name tokens don't match `display_name` (e.g. Zepp Tokyo → DiverCity) | error |
| R-E1 | Entry field ranges (timing junk, cdr ≤0 or >6, rating outside vocabulary) | warn |
| R-E2 | Tracklist matches <20% of the dated setlist (mis-dated / compilation) | error |
| R-F1 | Family merged at conf < 0.1, or `review_flag` set | warn |
| R-S1 | Derived table older than its inputs (picks vs families, scores vs metrics, `song_performances` vs Olof `parsed_at`) | error |

- **Quarantine:** a dossier field sourced from a row with an `open` or `confirmed` error
  finding renders its fallback and is listed in `prov.withheld[]` with the rule ID.
- **Decisions persist but can't go stale:**
  - A `false_positive` is bound to the finding's `evidence_hash`.
  - If the underlying row changes, the next run reopens the finding (`n_reopened`) instead of
    honouring the old dismissal.
  - Humans make these decisions in the Phase 2b console.

**Upstream fixes** (separate commits, each closing its BUG):
1. `backend/taper_attribution.py`:
   - A bare mention no longer propagates (the R-T1 pattern is required).
   - No propagation through weak or review-flagged families (R-T2).
   - Then re-run the tapers step.
2. Picks after families: `tapematch_sync` triggers the picks recompute (or marks it stale)
   after every family sync. `tools/compute_show_picks.py` skips NULL dates.
3. Scan selection: `dossier._load_quality` switches to the per-LB latest *scored* scan (not the
   global MAX). Queue a `concert_ranker rerank` for the 114 unscored LBs.
4. Map TUIT taper names into `user_taper_aliases` (e.g. "Legendary Taper E" → `lte`), so R-T4
   measures real disagreement.

**Acceptance:** `python -m backend.qc run` prints one line per rule with its count. After the
fixes, there are 0 open R-T1/R-T2 errors on the five sample shows, and LB-08493 no longer
carries "mike millard".

## Phase 2b — QC review console (`/qc-review`, experimental)

Built the same way as `/taper-review` and `/taper-curation`:
- A self-contained HTML page in `backend/`, served by Flask.
- It talks only to JSON routes and is English-only.
- Every decision persists server-side immediately, so a review can stop and resume across
  reloads.

It's an **experiment**:
- **v1** is the Queue and Findings tabs, used on the Phase 2 findings.
- **v2** adds the Rules, Sweep and Corrections tabs, if v1 earns it.
- After v1, tj decides whether it stays HTML, grows, or moves into `gui_next`.

**Files:**
- `backend/qc_review.html` (the page).
- `backend/qc/review.py` (read model, like `backend/taper_curation.py`).
- Routes in `backend/app.py`, next to the taper pages.

### Decision vocabulary (`qc_findings.status`)

| Status | Set by | Meaning | Quarantine |
|---|---|---|---|
| `open` | rule run | not yet judged | yes (error severity) |
| `confirmed` | curator | a real problem, not yet fixed | yes |
| `false_positive` | curator | the data is fine; bound to `evidence_hash`, and reopens if the row changes | lifted |
| `corrected` | curator, via the correction form | a `corrections` row supplies the right value | lifted; the corrected value renders with a "corrected" tooltip showing the original |
| `fixed` | rule run | the rule no longer fires (upstream fix or data change) | lifted |

### Routes

Reads are open. Writes are curator-only, with the same `database.is_curator()` → 403
`curator_required` guard as `/api/tapers/attributions/<lb>/confirm`.

| Route | Purpose |
|---|---|
| `GET /qc-review` | serve the page |
| `GET /api/qc/summary` | counts per rule by severity × status, last run per rule, total open errors |
| `GET /api/qc/findings?rule=&severity=&status=&entity_kind=&date=&q=&page=` | paged list |
| `GET /api/qc/findings/<id>` | the finding + evidence + rule-specific context panel data + affected dossier dates |
| `POST /api/qc/findings/<id>/decision` | `{status: confirmed|false_positive, note}` |
| `POST /api/qc/findings/bulk` | `{ids[], status, note}`; one rule per batch |
| `POST /api/qc/corrections` | `{finding_id, field, corrected, reason}` → a `corrections` row; finding becomes `corrected` |
| `POST /api/qc/releases/<title_key>` | `{official: bool, note}` → `release_classifications`; the R-R1 finding closes |
| `POST /api/qc/run` · `GET /api/qc/run` | start or poll a rules run (all or one), `JobState`-backed like `backend/ranker_jobs.py` |
| `GET /api/qc/decisions?page=` | decision log |

### Page layout

**Header:** open errors · open warnings · last run · **Run rules** button.

**Queue tab (v1).** One card at a time, mobile-friendly, keyboard-driven:
- **Card head:** rule ID and name, severity, entity (e.g. "LB-08493 · taper attribution"),
  first seen, and how many shows it touches.
- **Why flagged:** the rule's one-line explanation plus the finding's detail.
- **Evidence panel, by rule family:**
  - **R-T1–T4 (taper):** the attribution, its evidence text with the matching mention
    highlighted, the taper's confirmed years, and TUIT's taper.
    - Actions: **Reject attribution** (calls the existing
      `/api/tapers/attributions/<lb>/reject`; the next run marks the finding `fixed`),
      **Open in /taper-review**.
  - **R-O1/O3/O4 (setlist):** the Olof raw block vs the parsed songs, plus a side-by-side quorum
    (Olof · setlist.fm · bobdylan.com · TUIT) with mismatches highlighted, and a link to the
    Olof page.
  - **R-G1 (geocode):** the venue name vs the geocoder's `display_name`, its confidence, and its
    distance from the city centre.
  - **R-E1/E2 (entry):** the entry's fields, and the tracklist-vs-setlist alignment (matched /
    missing).
  - **R-S1 (staleness):** table timestamps side by side.
  - **R-R1 (release):** the release string; **Official** / **Not official** buttons.
- **Impact strip:** the affected dates, each with **Open dossier**
  (`/api/dossier/html?date=…&inline=1`) so you can see what's withheld.
- **Decision row:** Confirm · False positive · Correct… (opens the correction form) · Skip, with
  a note field.
- **Keys:** `c` confirm · `f` false positive · `e` correct · `s` skip · `j`/`k` next/prev ·
  `o` open source.

**Findings tab (v1).** A workbench table like `/taper-curation`:
- Columns: rule, severity, status, entity, detail, first/last seen, shows affected.
- Filter chips, multi-select bulk decisions (one rule per batch), and a pager.

**Rules tab (v2).** Per rule: its description, counts by status, the trend over recent
`qc_runs`, and a per-rule run button.

**Sweep tab (v2).** The latest `dossier_sweep` (it also writes JSON next to the `.md`): shows
refused and fields withheld, worst first, each with an Open dossier link.

**Corrections tab (v2).** List, edit and revoke corrections. Revoking reopens the finding.

### Integration

- **`backend/queues.py`:** add `RefreshQueue(queue_id="qc_errors", kind="gate", count_sql=
  "SELECT COUNT(*) FROM qc_findings WHERE severity='error' AND status IN ('open','confirmed')",
  blocks=(), screen=None, action="review at /qc-review")`, plus a `qc_warnings` **backlog**
  queue. The Home freshness card badges them through `/api/refresh/queues`, with no GUI code.
- **Taper rules:** the page complements `/taper-review` and doesn't duplicate it. Rejecting an
  attribution uses the existing endpoint and the existing `taper_decision_log`.

### Acceptance

1. **LB-08493 end to end:** its R-T1 card shows the "MM-EBM-1" mention highlighted →
   **Reject attribution** → **Run rules** → the finding becomes `fixed`. The 2010-03-29 dossier
   then drops the Millard taper, and its footer withheld count changes to match.
2. **False positive reopens:** marking an R-G1 finding `false_positive` lifts the quarantine on
   that show's coords. Editing the geocode row then reopens the finding on the next run.
3. **Correction round trip:** a correction ("Wille" → "Willie" Dixon) renders with its tooltip.
   Revoking it restores Olof's spelling.
4. **Curator gate:** every POST returns 403 when `meta.is_curator` is off.
5. **Resume:** reload mid-queue and continue where you left off, with no lost decisions.

## Phase 3 — Cross-source corroboration (audit Q1, `backend/qc/corroborate.py`)

| Check | Sources | Output |
|---|---|---|
| (a) Setlist quorum | Olof vs `setlistfm_setlist`, `bobdylan_setlist`, `tuit_song_performances`, aligned title by title with the D-01 matcher (not by count) | `corroborated` if ≥1 source agrees in count and order, allowing each source's intro/cover conventions; `disputed` if ≥2 independent sources agree against Olof; feeds R-O4 |
| (b) Premieres & rotation | Our corpus recompute + setlist.fm ordering | Per-song agreement map for the D-02 and D-04 gates |
| (c) Source tracklist | LB site `entries.setlist` vs TUIT `setlist_json` (3,881 LBs) | D-01 confidence |
| (d) File format | TUIT verified record vs lineage | D-11 basis and confidence |
| (e) Taper | `taper_attributions` vs TUIT `taper` | `corroborated` / `disputed` |
| (f) Venue / city | Olof vs setlist.fm vs `bobdylan_shows` | Header and G1 identity |

**Acceptance:** `tools/dossier_acceptance.py --corroborate`:
- 1986-02-24 and 1975-12-08 are `corroborated` after Phase 1. Before Phase 1 they would read
  `disputed`, which proves the check works.
- The corpus-wide share of `corroborated` / `stated` / `disputed` setlists is recorded in
  CHANGELOG.

## Phase 4 — Requirement derivations (`backend/dossier_fields.py`)

Each requirement gives its source, method, corroboration and QC, output shape, null rule, and
acceptance test. Tier follows the spec. None of these functions writes comparative wording;
that comes only from the Phase 5 claim engine.

### D-01 Per-source completeness (BLOCKER, T3) — `completeness(conn, event, sources)`

- **Source:** `entries.setlist` (via `db.parse_entry_setlist_titles`) against post-fix
  `olof_songs`.
- **New `clean_track_title()`:**
  - Drop durations (`[04:32.44]`, `(5:21)`, `04:03, 30:21`).
  - Drop suffixes (`[Petty]`, `(Live)`, `*`).
  - Split `10.When` markers by fixing `_ENTRY_TRACK_MARKER_RE`.
  - Drop header fragments (`Disc N`, `Second Show:`, `First Broadcast:`).
  - Exclude non-songs (intro, applause, band intros, encore break, tuning).
- **New `match_track()`:** compare the title with and without the subtitle, then via
  `song_canonical` aliases, then `db.titles_match`.
- **Partial positions:** tracks marked `incomplete`, `cut`, `fade`.
- **Output:** `{songs_present, songs_total, missing, partial, basis, confidence}`.
- **Corroboration:** if TUIT's tracklist for the same LB gives a different present-count, the
  confidence is `inferred`, and the bar shows only when both agree (Phase 3c).
- **Source–show fit (G2):** below 20% of the setlist matched, the source is flagged "tracklist
  doesn't match this show" and excluded from the verdict. LB-06654 is the example.
- **Null:** `basis:"runtime"` renders the runtime only; completeness is never inferred from
  duration.
- **Accept:**
  - 2010-03-29: all 9 sources have `basis:"tracklist"`. LB-08477 reaches 18 tracks after the
    marker fix.
  - 1965-06-01: LB-10364 and LB-12222 read 1/12. LB-08855 lists its missing positions.
    LB-06654 is flagged as not matching the show.

### D-02 Song-level performance history (BLOCKER, T3) — `song_history(conn, event)`

- **Source:** post-fix `song_performances` joined to `olof_events` (concert filter), ordered by
  `(date_str, event_id)`.
- **Per position:**

  | Field | Definition |
  |---|---|
  | `tour_premiere` | no earlier performance in the same `tour_name` |
  | `career_debut` | no earlier concert performance at all |
  | `last_played` | date of the previous concert performance |
  | `gap_shows` | concert events strictly between that performance and this show |
  | `times_played` | concert performances up to and including this show |

- **Gate (all three must hold, or no per-song badges; the premiere count renders alone):**
  1. The computed premiere count equals `olof_events.tour_new_count`.
  2. Each badged song is also a tour premiere per ≥1 independent setlist source (Phase 3b).
  3. No open R-O1/R-O4 finding exists on this event or on any earlier event in the same tour.
- **Gap badge:** `gap_shows ≥ 100`, and only when that gap span has no open R-O1 findings
  (a truncated earlier setlist would fake a gap).
- **Accept:**
  - **2010-03-29 → badges on songs 4 and 14 only.**
  - `--d02` samples 200 shows and reports how many pass the gate; the rate goes in CHANGELOG.

### D-03 Official release status (BLOCKER, T3) — `official_release(conn, event)`

- **Sources:**
  - `olof_songs.released_on` (per song).
  - `olof_events.releases_raw` (whole-show `Released on …` lines).
  - Curated `backend/assets/official_releases.json`: `[{title, year, kind, patterns[]}]`.
- **Building the asset:**
  - Extract the ~250 distinct Olof release titles.
  - Draft a classification: official = Columbia / Legacy / Sony, Bootleg Series 1–18, live
    albums, 50th Anniversary and copyright collections. Not official = Wolfgang's Vault,
    Westwood One, Crystal Cat.
  - **tj signs off before merge.**
  - A release string matching no allowlist entry is `unclassified`: it isn't counted as
    official, and it goes to a QC finding (`R-R1`, warn) so the allowlist grows deliberately.
- **Status:** `full` (whole-show official line, or every position covered) / `partial` /
  `none` (Olof has the event and no official match). No Olof event means the row is omitted.
- **Accept:** 1965-06-01 → `full` (if the 50th Anniversary 1965 entry is allowlisted) plus
  song 8 on *Live 1962-1966*; 1986-02-24 → `partial` (*Hard To Handle*);
  1975-12-08 → `none` ("None indexed").

### D-04 Cross-show rotation (HIGH, T3) — `rotation_rank(conn, event, run)`

- **Source:** `rotation_pct` / `rotation_new` for every sibling in the D-07 `venue_run`.
- **Verification:** each sibling's Olof stat must match our recompute from the previous show
  (Phase 3b). Where it doesn't, that sibling's value is `disputed`.
- **Output:** `{pct, rank_in_run, run_size, run_median_pct}`.
- **The superlative claim** is produced only by the claim engine, and only when all hold: every
  sibling has a non-disputed stat; this show is rank 1 with no tie; the scope is named ("of the
  7-night Zepp Tokyo run"). Otherwise render the bare "13 changed songs (72%)".
- **Accept:** 2010-03-29 has 72%, verified as the maximum across the run's 7 nights (52, 52, 58,
  64, 70, 52, 72), so the claim renders with its scope. A synthetic tie produces no superlative.

### D-05 Generation classification (HIGH, T3) — `classify_generation(entry, taper, bootleg_title)`

- **Source:** `entries.source_chain` (9,633 non-empty), `bootleg_titles`, and the taper tier
  **after QC** (a quarantined taper counts as no taper).
- **Rules (first match wins):**
  1. `BOOTLEG:`, silver disc/CD + label/catalogue, or a `bootleg_titles` row → `silver`.
  2. vinyl/LP → `vinyl`.
  3. TV/FM/pre-FM/radio/broadcast → `broadcast`.
  4. Explicit `1st gen` / `low gen` / `clone of master` → `low_gen`.
  5. The literal word "master" → `master` (stated).
  6. A mic → preamp → recorder chain with a *confirmed* (not propagated) taper → `master`
     (inferred).
  7. Otherwise → `unknown`, and the tag is omitted.
- **Evidence** is the substring that fired the rule. A class is never guessed from rating or
  grade.
- **Accept:** LB-15005 silver, LB-09493 vinyl, LB-06654 silver, LB-08637 unknown; **LB-08493
  shows no "low gen"** (audit M7). The acceptance tool prints a random 100-row audit table for
  tj to sign off.

### D-06 Venue enrichment (LATER, T3)

- Deferred: `district`, `capacity` and `status` stay null. "Odaiba" is not used.
- **Venue identity is by exact venue name** (audit C6). Zepp DiverCity is a different venue from
  Zepp Tokyo and never appears in Zepp Tokyo's history line.

### D-07 Run, tour & city history (HIGH, T3) — `run_context(conn, event)`

- **Source:** the `olof_events` corpus (concert filter).
- **One tour object per page (audit P6):**
  - `tour = {name: olof tour_name, position, size, is_first, is_last}`.
  - The header shows this leg name, with NET # as the umbrella. setlist.fm's "Never Ending
    Tour" is not shown as a second tour.
  - Suppressed when `tour_name` matches `Recording sessions` (Olof's year buckets aren't tours).
- **`venue_run`:** consecutive concerts with the same `tour_name` + exact `venue` and no other
  concert between. `{position, size, dates[], dossier_urls[]}`.
- **`city_history`:** rows of `{year, venue, count}`, grouped by setlist.fm `(city, country)`
  for each date, with the normalised Olof fallback. Venues are never merged within a row.
- **Invariant (gate G5):** `sum(count) == venue.city_total`; on failure, suppress the panel.
- **Completeness guard:** position claims (`is_first`, `is_last`, "night N of M") need every
  event in the tour/run to be present with parsed songs and no open R-O1 findings.
- **Accept:**
  - 2010-03-29: Zepp Tokyo run, night 7 of 7.
  - **`is_last` = false** (the tour continues to Seoul, 03-31), so there is no "closing" claim.
  - Tokyo `city_total` = 50, including Tokyo Garden Theater ×5 in 2023.
  - The sum assertion is tested.

### D-08 Pairwise comparison (HIGH, T2) — `compare_sources(visible_sources)`

- **Scope:** runs **only over the visible set**. In the public channel, withheld/private sources
  never take part, and the wording names the scope (audit S7).
- **Diffs** the pick against the runner-up on rating, scan score, runtime, resolution,
  generation and character terms.
- **Axes:** best scan, longest runtime, highest resolution, only soundboard, only complete.
- **An axis counts only when:** both sides are non-null, from the **same basis** (file record
  vs lineage never compared), and not disputed or withheld. Ties are reported and never broken.
- A leader that isn't the pick becomes an alternate. "No meaningful deltas" collapses the
  block.
- **Accept:**
  - 2010-03-29: LB-08637 is the best-scan alternate (90 vs 84).
  - **No resolution alternate:** LB-08485 and LB-08476 are both 16/44 files; LB-08493 has only
    a lineage basis.
  - **No "smaller file set" claim** (audit M17).
  - 1965-06-01 collapses.

### D-09 Setlist completeness (HIGH, T3) — `setlist_confidence(event, songs, sources)`

- **Primary:** Phase 3a quorum. `disputed` → status `partial`, with a notice that names the
  sources and their counts.
- **Secondary** (no external source available): listed songs vs the expected count (sources'
  median runtime ÷ the corpus minutes-per-song calibrated from `recording_mins`), plus Olof's
  "incomplete setlist" phrasing. The threshold comes from the calibration histogram in
  `.debug/dossier_calibration.md`.
- **Accept:** **1986-02-24 = complete, 25 songs, corroborated.** A synthetic 7-song fixture →
  `partial`. The corpus scan lists every remaining `partial` for review.

### D-10 Bobtalk anchored to songs (LATER, T2) — `anchor_bobtalk(event, songs)`

- Cues `(before|after|plays|during) <title>`: 1,862 cues in 677 events.
- Resolve cues space- and hyphen-insensitively, then with `titles_match`. Unresolved lines stay
  in Context.
- **Accept:** 1986-02-24 attaches ≥3 lines. 2010-03-29 collapses with no empty container.

### D-11 Format & file metadata (LATER, T3) — `file_meta(lb)`

- **`resolution`:** a TUIT `lb_verified` format is a **file record** and wins. Otherwise use
  the lineage regex, preferring a parenthetical `(16bit/44.1kHz)` over a recorder model's
  `24/96`.
- **Labels always say which basis they show:** "16/44 file" vs "recorded 24/96". When both
  exist and differ, show both.
- **`filesize`:** TUIT `size_bytes` only.
- **`filecount`:** distinct audio filenames in `checksums` where `xref=0`, falling back to TUIT
  `n_files`.
- **`disc_count`:** `entries.cdr`, ignoring `''`, `≤0` and `>6` (R-E1).
- **Null:** "—". No size figure renders unless it came from a file record.
- **Accept:** **LB-08485 renders "16/44 file · recorded 24/96"**. No page says "only 24/96
  transfer" (lint L1).

### D-12 Catalog freshness (LATER, T3)

- No source exists (F9). The registry keeps the anchor with fallback "suppress". Revisit only if
  the LB site starts exposing a date.

### D-13 Medium (HIGH, T3) — `classify_medium(entry, event)`

- **Signals:** `lb_category` tv/radio; Olof notes and recording phrases; lineage tokens (DVD,
  VOB, VHS, TV, broadcast); video extensions in `checksums.filename`.
- **Output:** `{medium, evidence}` and `show.media_available`.
- **Wording follows the medium:** "broadcast copy" vs "transfer". A broadcast-derived source
  gets no taper line; an attributed taper on a broadcast source raises an R-T finding.
- **Null:** audio.
- **Accept:** every 1965-06-01 source is `audio_from_video`, with no taper lines.

### Supporting parsers (T2, same module)

- **`band_index` / `band.label`:** regex on `Concert # ?N with the <ordinal> Never-Ending Tour
  Band` (3,117 of 4,185 lineups); "solo" when the lineup is Dylan alone.
- **`band.members`:** from the lineup's first clause, Dylan first.
- **`song.instruments`:** lineup range lines plus per-song sidemen and Dylan notes.
- **`stats.instrument_tally`:** counts per instrument only ("harp 8 · keyboard 15 · guitar 1").
  No "otherwise" generalisation (audit M13).
- **`song.writers`:** post-fix `credits` in Olof's spelling, with `corrections` applied (shown
  with a "corrected" tooltip). Shown only when the song isn't solely Dylan's.
- **`set[].label`:**
  - A broadcast range note covering a contiguous block becomes a band.
  - A non-contiguous one stays a per-song marker.
  - A whole-show recording note goes to `context.session_notes`.
- **`source.character` / `.flags`:** from `verdict_text` with the grade/LB prefix and the rank
  phrase stripped; `Flags: …` split off; `no lineage on file` when `source_chain` is empty.
- **`pick.lineage_short`:** `source_chain` cut before the first DAW/codec hop.
- **`runtime`:** parsed from `entries.timing` (12,338 of 16,646 parse). The split must sum to
  the total (G5).
- **`family.basis`** (render time): the waveform-correlation mean, plus "LB page states same
  source" if `by='ai+lb'`, plus a quality match (reuse `tapematch_sync._has_quality_match`).
- **`taper`:**
  - Rendered only when it passes QC (no open R-T errors).
  - `propagated` renders with the inferred marker, `disputed` with its notice.
  - A missing taper renders nothing, never "unknown" (audit M8).
- **Scan quality:** the per-LB latest scored scan (Phase 2 fix). If `show_picks`' audio-quality
  evidence differs from the displayed score, the gate (G5) withholds both.

## Phase 5 — View model, claim engine & QC gate

### Claim engine (`backend/dossier_claims.py`, audit C3)

- **Every** comparative or positional word ("only", "highest", "best", "biggest", "first",
  "last", "closing", "new to tour", "debut", "since") is a `Claim`:
  `{kind, text_key, slots, scope, verified_by, ties, derived_from}`.
- A comparator returns a Claim only when all hold:
  - every candidate has the value;
  - none is disputed or withheld;
  - the scope was fully loaded;
  - ties are reported ("tied highest").
- Otherwise it returns `None`, and the plain value renders.
- **T4 sentences** (`verdict.why`, `context.chronicle`) are slot templates filled only by Fields
  and Claims, with no free text. A slot filled by an `inferred` Field carries the marker inside
  the sentence.

### Selection and ordering rules (spec §8)

- **Fragments (§8.2):**
  - What counts: completeness below 60%, or with no tracklist a runtime below 60% of the
    median.
  - The 60% threshold is confirmed by a 300-show histogram first (spec Q5). Today 20 of 2,044
    rank-1 picks fall under the runtime rule.
  - Fragments go to an "Excerpts & fragments" group. Sources failing G2 go to "Doesn't match
    this show".
- **Verdict pick:** the best `pick_rank` among visible, non-fragment, G2-passing sources, whose
  pick evidence is fresh (G6). Applied in the dossier only; feeding D-01 into
  `concert_ranker/picks.py` is a follow-up TODO.
- **Collapse (§8.3):** pick + next 3; promote D-08 axis leaders. No collapse at ≤5 sources.
- **Families (§8.4):**
  - Band only families with ≥2 members.
  - The label `"<taper>'s tape"` requires **every member's taper to be confirmed** (not
    propagated, not quarantined); otherwise "Family A" (audit M10, P2).
  - Sort within a family by generation, then rank.
- **Confidence (§8.5):**
  - Below 50% → low-confidence tag, with the basis in the tooltip.
  - **Below 50%, no identity prose** ("same master", "reissue") and no taper-based label.
- **Tape wording:** "N tape groups", counting only tapematch-analysed sources. Never
  "independent tapes" (audit M9).
- **`prov.local_fields`:** the non-null tier≥3/T4 anchors on the page. **`prov.withheld`:**
  every withheld field with its rule.

### Anchor map (spec §6, exhaustive)

Every row becomes a `Field`. The fallback matches the spec's, and every row is subject to the
G3/G4 quarantine.

**Header and verdict**

| Anchor | Tier | Source / computation | Fallback |
|---|---|---|---|
| show.date.long / .dow | T1 | `date_iso` long / `%A` | required / omit |
| show.venue | T1 | `_build_show` cascade, corroborated with setlist.fm / bobdylan_shows (3f) | "Venue unknown" |
| show.city / .country | T1 | city + country; region code dropped | omit clause |
| show.tour · .net_number · .year_index | T1 | D-07 tour object (Olof leg) · `concert_no_net` · `concert_no_year` | omit |
| show.band_index | T2 | lineup regex | omit |
| run.label · .position · .dates[] · .dates[].url | T3 | D-07 (completeness guard) | suppress strip / chip unlinked |
| pick.lb_id · pick.url | T1 | verdict pick · `detail_url` | suppress §2 / plain ID |
| pick.taper.name · .confidence | T1 | QC-passed `taper_attributions` + TUIT corroboration (3e) | omit line / no mark |
| pick.medium | T3 | D-13 | audio |
| pick.type · .lb_rating · .scan_grade | T1 | `source_type` · `rating` · per-LB latest scored scan | omit · "—" · omit row |
| pick.lineage_short | T1 | parser | omit line |
| pick.resolution · .runtime | T2 | D-11 (basis-labelled) · runtime | omit row |
| pick.generation · .completeness | T3 | D-05 · D-01 | omit row (+ bar) |
| pick.curated_in[] | T1 | `curated_lists` | omit row |
| show.official_release | T3 | D-03 | omit row |
| verdict.why | T4 | claim-engine slot template | omit column |
| verdict.vs_runner_up · .alternates[] | T2 | D-08 via the claim engine | omit column |
| ledger[] · ledger.total | T1 | `evidence_json` · `pick_score` (G5 sum check; G6 freshness) | suppress disclosure |

**Setlist**

| Anchor | Tier | Source / computation | Fallback |
|---|---|---|---|
| setlist.count | T1 | post-fix `olof_songs` | omit suffix |
| show.setlist_confidence | T3 | D-09 (Phase 3a quorum) | assume complete only if `stated`/`corroborated` |
| set[].label | T1 | encore + broadcast bands | single list |
| song[].position · .title | T1 | `olof_songs` title + " (subtitle)" | required |
| song[].writers · .instruments[] | T2 | parsers | omit |
| song[].premiere · .gap | T3 | D-02 (three-part gate) | no badge |
| song[].bobtalk | T2 | D-10 | stays in Context |
| song[].official_release | T3 | D-03 | no marker |
| stats.rotation · .premiere_count | T1 | P1d columns | omit stat |
| stats.rotation_rank | T3 | D-04 claim | percentage alone |
| stats.premiere_titles | T3 | D-02 (gated) | count without names |
| stats.instrument_tally | T2 | counts only | omit |
| band.members[] · band.label | T2 | lineup parser | raw lineup / "Personnel" |

**Sources**

| Anchor | Tier | Source / computation | Fallback |
|---|---|---|---|
| sources.count | T1 | visible sources | required |
| sources.tape_count | T1 | "N tape groups", only when every visible source is tapematch-analysed | omit clause |
| sources.visible_n | T2 | §8.3 | show all |
| source[].lb_id / .url · .taper | T1 | existing · QC-passed taper | required · omit (never "unknown") |
| source[].generation · .medium · .completeness | T3 | D-05 · D-13 · D-01 | omit · audio · omit |
| source[].type · .scan_grade | T1 | existing · per-LB latest scored scan | suppress column if empty show-wide |
| source[].lb_rating · .runtime · .resolution | T1/T2/T2 | existing · runtime · D-11 | "—" |
| source[].character · .flags[] · .lineage · .curated_in[] · .rank | T1 | parsers / existing; lineage moves to the footnote | empty · omit · omit · omit · omit column |
| family[].id/.label · .size · .confidence | T1 | families + meta, per the §8.4/§8.5 rules above | no band · bar omitted |
| family[].basis | T3 | `family.basis` | omit tooltip |

**Context, related and provenance**

| Anchor | Tier | Source / computation | Fallback |
|---|---|---|---|
| context.chronicle | T4 | slot template (run, tour, Olof chronicle line); no position claim without a verified Claim | chronicle verbatim |
| context.bobtalk | T1 | bobtalk minus anchored lines | "No bobtalk recorded" |
| context.session_notes | T1 | post-fix `notes` + recording notes | omit |
| venue.name / .city | T1 | show fields | omit card |
| venue.coords | T1 | `venue_geocoded` at confidence ≥ medium with no open R-G1; otherwise setlist.fm labelled **"city centre (setlist.fm)"** | omit line |
| venue.map | T1 | Compact `_render_locator_svg` inside the venue card. Marker kind comes from `venue.coords`: a solid pin for `venue` (verified: `venue_geocoded` confidence `high`/`medium`, `display_name` matches the venue name, no open R-G1), a hollow ring for `city_centre`. The caption repeats the coordinate label. G5 invariant: the marker kind equals the `venue.coords` basis. | no map when there are no coords or the country is unknown |
| venue.district | T3 | D-06 (null) | omit |
| venue.run_nights · .city_total · city_history[] | T3 | D-07 (exact venue names; G5 sum) | omit · omit · suppress panel |
| xrefs[] | T1 | `_build_xref`; no link to a page that doesn't exist | omit missing rows |
| prov.credits · prov.stamps | T1 | footer; stamps add `inputs` (each derived table's `computed_at`, `master_version`, parser version) | required |
| prov.local_fields[] · prov.withheld[] | T3 | registry scan · gate output | blanket sentence · omit |
| source[].added · show.newest_source_date | T3 | D-12 (null) | suppress |
| source[].filesize · .disc_count · .filecount | T3 | D-11 | "—" |

**`filter_dossier_sections(local_analysis=0)`** strips the verdict, ledger, scan grades, family
confidence and basis, inferred tags, T4 sentences, and every Claim.

### Per-dossier QC gate (`backend/dossier_qc.py`, audit Q2)

Runs at the end of every `build_dossier()` call, target <100 ms.

| Check | Rule | On failure |
|---|---|---|
| G1 Identity | Exactly one Olof event (or a disambiguated `location`); venue **or city** agrees with ≥1 of setlist.fm / bobdylan_shows (`corroborate.venue_check`); a city-only match renders a venue-name notice (tj, 2026-09-11) | **Refuse**: HTTP 422 + reasons; no page |
| G2 Source–show fit | Each source's tracklist matches ≥20% of the setlist | Source leaves the verdict; listed separately |
| G3 Provenance | Every non-null Field has `source` + `confidence`; no `derived_from` cycles | Withhold the field |
| G4 Quarantine | No Field sourced from a row with an `open` or `confirmed` error finding | Withhold the field |
| G5 Invariants | City-history sum; runtime split sum; ledger sum = total ±0.05; ledger audio evidence = displayed scan score; tape groups ≤ sources; badge count = premiere count | Withhold the dependent block |
| G6 Freshness | Each derived input is newer than its inputs (R-S1) | Withhold dependents; "analysis stale" note |
| G7 Claims | Every comparative word comes from a verified Claim | Drop the claim; keep the plain value |
| G8 Channel | Public view: no private attribute anywhere, and no comparison involving a withheld source | **Refuse** |
| G9 Lint | Rendered HTML passes L1, and every `data-lb` is in the registry | Test failure; in production, log + withhold the element |

**Output:**
- `dossier["qc"] = {checks_run, passed, withheld:[{key, rule}], refused, input_fingerprint}`.
- The footer reads, for example, "QC · 212 checks · 3 withheld · analysis as of 2026-09-04".
- The HTML embeds `<script type="application/json" id="lb-qc">` with the same data, so an
  export can be re-checked later.

**Lint L1** (forbidden in rendered HTML):
- "taper unknown" / "unknown taper";
- "independent tapes";
- "none indexed" unless D-03 consulted the index;
- bare only / highest / best / biggest / first / last / closing outside Claim spans.

**Lint L2:** the template source may not contain those words outside the claim macro.

## Phase 6 — Remaining §7 generator defects

| Defect | Fix |
|---|---|
| 7.1–7.3 | Phase 1 (P1b–P1d) + `set[].label` banding |
| 7.4 Fragments ranked | §8.2 group + verdict selection (Phase 5) |
| 7.5 Empty columns / scoreless rows | Suppress per show any column empty for every source. A scoreless row shows its `unrated` evidence detail ("no rating on file"). |
| 7.6 Always-on review badge | Removed; §8.5's tag replaces it (`review_flag` stays in JSON and feeds R-F1) |
| 7.7 Solo families | Plain rows |
| 7.8 Whitespace | `{%- -%}` on every control line. Target: blank lines <5%; masthead within ~30 lines of `</style>` |

## Phase 7 — Template rewrite (`backend/templates/dossier.html`)

- **Layout** follows the mock. **Values** come only from `view`, and comparative text only from
  Claims. The mock's errors (audit §4) are **not** reproduced.
- **Section order:** Header (date H1, run strip), Verdict, Setlist, Sources, Context (with the
  venue card), Related, Provenance.
- **Removals:** the at-a-glance strip, and the 300 px standalone Location section.
- **Map, kept and compact** (decision; `venue.map`):
  - Keep `_render_locator_svg`, `_world_features`, `_COUNTRY_MAP_META`,
    `_COUNTRY_ALIASES` and `backend/assets/world_countries_110m.json`.
  - Add a `marker` parameter (`venue` = solid pin + halo; `city_centre` = hollow ring, no
    halo) and a compact size (~240×150, down from `_MAP_W`/`_MAP_H` 300×210).
  - It renders at the top of the Context section's venue card.
  - Coordinates move off `show.lat/lng` (setlist.fm city) onto `view.venue.coords`, which
    carries its basis.
  - **Accept:** 2010-03-29 draws a hollow city-centre ring captioned "city centre
    (setlist.fm)", because Zepp Tokyo's geocode is `low` and matches Zepp DiverCity (R-G1).
    Also accept one show whose venue has a verified `high` geocode (chosen in Phase 8) with a
    solid venue pin.
  - Lint L1 adds: no solid pin unless `venue.coords.basis == "venue"`.
- **Rendering macros:**
  - `lbf(key, field)`: the value or its fallback, plus `data-lb`, the inferred/disputed marker
    and the provenance tooltip.
  - `claim(c)`: the only way comparative text reaches the page.
- **Palette:** the mock's `--pick` / `--pick-hi` / `--pick-soft` / `--on-pick` warm tokens in
  the light, dark and print palettes, used only for the recommended copy.
- **Labels:** "Scanned quality" replaces "AI grade" in the HTML, BBcode (`render_bbcode`
  line 1147) and footer.
- **Footer:** the QC stamp, the withheld list and the embedded `lb-qc` JSON.
- **Links:** `render_template("dossier.html", d=view, link_mode=…)` (`app.py:8463`).

## Phase 8 — Tests & verification

- **Unit tests:**
  - `tests/test_olof_parser_fixes.py`.
  - `tests/test_qc_rules.py`: one test per rule, on fixture rows.
  - `tests/test_corroborate.py`.
  - `tests/test_dossier_fields.py`: accept and null cases per D-requirement.
  - `tests/test_dossier_claims.py`: ties, incomplete scope, disputed inputs → no claim.
  - `tests/test_dossier_qc.py`: each G-check's pass and fail paths, including the G1 and G8
    refusals.
  - `tests/test_qc_review.py`:
    - the read routes;
    - the curator 403;
    - decision and bulk persistence;
    - a correction closes its finding, and revoking it reopens the finding;
    - an `evidence_hash` change reopens a false positive;
    - quarantine lifts in the dossier view after a decision;
    - `queues.py` counts.
  - Manual smoke test: work through the five Phase 2b acceptance steps in a browser at
    `http://localhost:5174/qc-review`.
  - Extend `tests/test_dossier.py`: fresh-install degrade; anchor coverage (template `data-lb`
    = `ANCHORS`); lints L1/L2; no `review` badge; whitespace ratio.
- **Golden set (audit Q3):** `tests/golden/dossier/*.json`, 15 shows:
  - the five spec samples;
  - a two-show day;
  - a 2022+ bobserve show;
  - a Rolling Thunder guest-set date;
  - a 1986/87 Heartbreakers date;
  - a solo 1960s date;
  - a propagated-taper-heavy date;
  - a show with private sources;
  - a no-setlist date;
  - a compilation-polluted date;
  - a show with official releases.

  Each file lists expected anchor values **verified by tj by hand** against the Olof page, the
  LB detail page and TUIT. The files run against a fixture DB cut by `tools/make_fixture_db.py`,
  so they work in CI. Any diff fails; changing a golden file needs a note in the same commit.
- **Live acceptance:** `tools/dossier_acceptance.py [--parser|--corroborate|--d02|--all]` prints
  one PASS/FAIL line per criterion above, for the five samples plus 25 random dates.
- **Corpus sweep (audit Q4):** `tools/dossier_sweep.py`:
  - Builds every concert date in memory (caching `_rarity_map`) through the gate.
  - Writes `data/logs/dossier_sweep_<date>.md` with refused / withheld / disputed / stale
    totals.
  - Joins the nightly cron and sends a push notification when any error count rises night over
    night.
- **Export re-check:** `tools/dossier_verify_export.py <file.html>` compares the embedded
  `lb-qc` fingerprint against the current DB and reports drift.
- **Order of checks:**
  1. `/backend-restart`.
  2. `pytest` (all of the above plus `tests/test_song_index.py tests/test_tapematch_sync.py`).
  3. `python -m backend.qc run`.
  4. The acceptance tool.
  5. The sweep.
  6. `/verify` Tier A on the timeline iframe for 2010-03-29 and 1965-06-01 (light and dark).
  7. `/verify --electron` once for the PDF path.
- `/gui-check` only if GUI files change (none are planned).

## Phase 9 — Bookkeeping (`/session-close` per bite)

- **CHANGELOG per bite.** Record:
  - the reparse diff counts;
  - the QC rule counts before and after the upstream fixes;
  - the corroboration shares;
  - the D-02 gate pass rate;
  - the D-09 and §8.2 thresholds;
  - the D-03 allowlist sign-off;
  - golden-set sign-off.
- **PROJECT.md:**
  - Olof schema (~line 1331): new columns.
  - New `qc_findings` / `corrections` sections.
  - Dossier routes (~1821-1826): the `view` / `qc` layers, 422 refusals, the compact map with
    verified-venue vs city-centre markers.
  - File tree (lines 80-82, 131, 230): new modules, tools and tests.
- **`/wiki-update`:** Show-Dossier, Setlist-Sources, Taper-Attribution-Flow; then a new
  Data-Quality page (added to `Home.md`).
- **Close:** the Phase 0 BUGs and the redesign TODO.
- **PROJECT.md additions for 2b:**
  - The `/qc-review` page and the `/api/qc/*` routes table.
  - The `qc_decision_log`, `qc_runs` and `release_classifications` schema sections.
  - File-tree lines for `backend/qc_review.html` and `backend/qc/review.py`.
- **Follow-ups:** D-01 into `picks.py`; the 2b v2 tabs, or moving the console into `gui_next`
  (tj's call after v1); D-06; D-12 if the LB site ever exposes dates.
- No i18n: no GUI strings change.

## Execution notes

- **Build order is binding:** 0 → 1 → 2 → 2b → 3 → 4 → 5 → 6 → 7 → 8 → 9. No template work
  before the Phase 5 gate exists. The 2b console lands right after the QC rules, so the first
  wave of findings (tapers, geocodes, staleness) can be worked while Phases 3–5 are built.
- **Commit in small bites**, one per row of *Chunks & progress*, each through `/session-close`
  and pushed (standing preference).
  Phase 1's reparse and Phase 2's upstream fixes land first, because every later acceptance
  number depends on them.
- **Delegation:** opus for Phase 1 (parser), the Phase 2 taper fix, D-01/D-02 and the claim
  engine; sonnet for the QC rules, corroboration, the other derivations, the template and the
  tests. The orchestrator reviews every diff and runs the acceptance tool, QC and sweep itself.
- **Throwaway scripts** go in `tools/_<name>.py` and are deleted after use; reports go to
  `.debug/`. Nothing in `/tmp` via the file tools. Bulk audio never enters this work.
