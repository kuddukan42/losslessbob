# Show Dossier — Pre-Build Audit

Scope: the design spec (`Show Dossier Redesign.pdf`, Rev A), the reference mock
(`Show Dossier 2010-03-29 (standalone).html`), and the execution plan
(`SHOW_DOSSIER_REDESIGN_PLAN.md`).

Method: every claim in the mock was checked against the live DB on 2026-09-10, and every
spec rule and plan step was checked for a path that lets wrong data reach the page.

## 1. Verdict

The spec's core rules (trace every value to a source; every field has a null fallback) are
right, but they aren't enough on their own. **The spec controls where data comes from. It
doesn't control whether that data is true.** The mock shows the gap: nearly every value on it
traces to a real source, yet at least 12 of its statements are false. The causes are mostly
three:
- A true input fed into an unverified comparison ("only", "highest", "closing").
- A propagated attribute used as if it were fact.
- A field whose label claims more than its source measured.

The database also has systemic defects that a traced value would pass straight through: the
Olof parser truncates setlists, taper propagation matches gear names, and several derived
tables are stale.

**Recommendation.** Build three quality-control layers **before** any template work, and make
them binding:
- **Q0: database QC.** A rules engine plus a findings table. Bad source rows are quarantined.
- **Q1: cross-source corroboration.** The DB already holds four independent setlist sources
  and a second file and taper source (TUIT).
- **Q2: a per-dossier QC gate.** It runs on every generation, turns failing fields into
  fallbacks, refuses to render a show whose identity it can't confirm, and stamps the result
  onto the page.

Behind them sit a hand-verified golden set (Q3) and a nightly corpus sweep (Q4).

## 2. Direct answers

| Question | Answer |
|---|---|
| How do we verify accuracy? | Four independent checks, none of which trusts the generator:<br>(a) A **golden set**: hand-verified expected values for 15 shows across the eras. Any diff fails.<br>(b) **Cross-source quorum**: each fact is compared across Olof, setlist.fm, bobdylan.com, TUIT and the LB site.<br>(c) **Invariants**: sums, counts, uniqueness, and consistency between the ledger and what's displayed.<br>(d) **Provenance trace**: every rendered field names its source row, and the gate rejects any field that doesn't. |
| QC on each dossier generation? | **Yes, and mandatory.** It runs inside `build_dossier()` in well under 100 ms. Outcomes are *pass*, *withhold field* (render the fallback and list it in provenance), or *refuse* (identity failure: HTTP 422 with reasons, no page). The result is embedded in the page as JSON, so an export can be re-checked against a later DB. |
| QC on the database in general? | **Yes.** It's the bigger lever, because one bad row poisons every page that uses it. Persistent `qc_findings` rows are written by rules that run after every ingest and every derived-chain step, and nightly. The dossier gate reads open findings and quarantines the affected fields. |

## 3. Trust model (binding vocabulary)

The spec's `confidence` values (`certain | stated | inferred | unavailable`) are replaced
with the following. `certain` is dropped, because nothing we ingest is certain.

| Level | Meaning | Rendering |
|---|---|---|
| `corroborated` | ≥2 independent sources agree | plain, with a ✓ in the tooltip |
| `stated` | one source says so, and no source contradicts it | plain, source in the tooltip |
| `inferred` | a rule derived it (tier ≥2 computation) | dotted underline and tooltip (spec §8.5) |
| `disputed` | sources disagree | show the credited source's value, plus a "disputed: X says Y" notice; never a superlative built on it |
| `withheld` | the QC gate or an open finding blocked it | the field's fallback; listed under `prov.withheld[]` |
| `unavailable` | no source | the field's fallback |

**Independence rule.** Two sources count as independent only if neither was derived from the
other. Examples of evidence that is *not* independent:
- A taper propagated through a family can't corroborate that family.
- A TUIT title copied from the LB page can't corroborate the LB page.

Every `Field` gets a `derived_from: [field keys / source rows]` list, and the gate rejects
evidence cycles.

## 4. The mock — false or unsupported statements (2010-03-29)

| # | Mock says | Truth (DB, 2026-09-10) | Failure class | Guard |
|---|---|---|---|---|
| M1 | "the only 24/96 transfer in circulation"; resolution "24-bit / 96 kHz" | LB-08485's **circulating fileset is FLAC 16/44**: TUIT verified record, 714 MB for 126 min, which fits 16/44 and not 24/96. "24bit/96kHz" is the *recorder* setting in the lineage. | Label claims more than the source measured | D-11 file-record precedence; the label says "recorded at" vs "file"; C3 exclusivity check |
| M2 | "Highest LB rating on the show (A)" | Tied: LB-08476, 08493 and 08637 are also rated A. | Unverified superlative | C3: superlatives come only from a comparator that handles ties ("tied highest") |
| M3 | "the only one from a confirmed taper with a high median rating" | LB-08476 (romeo) has the same evidence line. | Unverified exclusive | C3 |
| M4 | "closing the 2010 Tour of Japan" | Olof's "2010 Tour of Japan" continues to **2010-03-31 in Seoul**. 03-29 is the last *Japan* night, not the last night of the tour. | Unverified position claim | D-07 `is_last` from the corpus; C3 |
| M5 | "new to tour" on songs 13 and 16 | Our corpus says **songs 4 and 14** (My Wife's Home Town, Forever Young), and that count matches Olof's "2 new songs for this tour". | Invented data | D-02 gate plus Q1 per-song corroboration |
| M6 | LB-08493 "mike millard (propagated)" | Millard died in 1994. The attribution comes from a text *mention* matching the gear name "MM-EBM-1". | Bad upstream data rendered as fact | Q0 rules R-T1/R-T2; propagated tapers render only once they pass QC |
| M7 | LB-08493 "low gen" | No source for it. | Invented | D-05 evidence rule |
| M8 | "taper unknown" ×4 | The spec (§8.1) forbids this. | Null rendered as a finding | Forbidden-phrase lint L1 |
| M9 | "8 independent tapes" | 7 sources were never matched, and a failed match isn't proof of independence. Family A itself is at 4% confidence. | Absence treated as proof | Wording "8 tape groups"; count only tapematch-analysed sources |
| M10 | "oscar's tape · same master, one is a silver-disc reissue" next to "4% match" | A 4%-confidence merge described as fact. LB-15005's "oscar" is *propagated through that same family*, so the evidence is circular. | Circular evidence; confidence contradiction | Independence rule; C5: below 50% confidence, no identity prose and no taper-based label |
| M11 | "Odaiba"; "9 shows at Zepp DiverCity in 2014" as the venue's history | Odaiba isn't in any source. Zepp DiverCity is a **different venue**, and the geocoder matched "Zepp Tokyo" to it at low confidence. | Invented / conflated | D-06 null; C6: venue identity by exact name only |
| M12 | Coordinates "35.6900, 139.6920 · setlist.fm" on the venue card | These are setlist.fm's **city centroid**: all 48 Tokyo dates share one coordinate pair, which is in Shinjuku, not Aomi. | Label claims more than the source measured | Label it "city centre (setlist.fm)", or use `venue_geocoded` only at confidence ≥ medium |
| M13 | "keyboard otherwise, guitar only on Baby Blue" | The lineup lists keyboard for songs 1, 3, 5, 6, 8-13 and 15-18. Songs 4, 7 and 14 have no instrument (centre stage). | Over-generalisation | The instrument tally states the counts per instrument only; no "otherwise" |
| M14 | "45 Tokyo shows since 1978" | That's the frozen blob. The corpus has **50** (it adds Tokyo Garden Theater ×5, 2023). The mock also merges venues ("Forum ×2 / Budokan ×1"). | Stale source | D-07 from the corpus |
| M15 | "Official release — none indexed" | No index exists. | Invented | D-03 |
| M16 | Writer credit "Willie Dixon" | Olof has "Wille Dixon". The mock silently corrected it. | Silent edit of a source | Corrections only through a `corrections` table with a note (Q5); never inline |
| M17 | "LB-08493 — you prefer a smaller 16/44.1 file set" | There's no size record for LB-08493, and LB-08485 is 16/44 as well (M1). | Invented comparison | D-08 axes need both sides non-null and from the same basis |

What the mock gets right, and verified: the run (7 Zepp Tokyo nights, night 7 of 7), 13/18
songs changed (72%), and "biggest rotation of the run". 72% is the maximum across all 14 shows
of Olof's tour, and across the 7 Zepp Tokyo nights (52, 52, 58, 64, 70, 52, 72). Also right:
the ledger, the scan scores, the runtimes, and the band.

## 5. Spec holes

| # | Hole | Fix |
|---|---|---|
| S1 | Traceability is required, but *truth* is never checked: comparisons and composed sentences aren't verified. | Claim engine (C3): every comparative or positional word ("only", "highest", "best", "biggest", "first", "last", "closing", "new") is produced by a comparator that returns a verified Claim or nothing. Templates may not contain these words outside claim macros (lint L2). |
| S2 | No `disputed` state. | Section 3 above. |
| S3 | `certain` is undefined; T1 is treated as fact. | Tier ≠ truth. T1 means "available" and still carries a confidence level. |
| S4 | No cross-source verification, although the DB holds 4 setlist sources, 2 venue sources, and 2 taper/format sources. | Q1. |
| S5 | No freshness rule. Derived tables can be older than their inputs (see D4). | Gate check G6 plus `prov.stamps.inputs`. |
| S6 | No rule for propagated attributes (spec §6 treats `taper.confidence: propagated` as T1). | Propagated values render only if they pass QC rules R-T1..R-T3, and never feed identity claims (C5). |
| S7 | Public channel: comparisons can silently span sources the viewer can't see. | C7: comparisons run only over the visible set, and the wording says so ("best of the 8 public sources"). |
| S8 | Static exports go stale with no way to detect it. | Embed `<script type="application/json" id="lb-qc">` with the input fingerprint and QC results; `tools/dossier_verify_export.py` re-checks an export against the current DB. |
| S9 | D-09 treats our parser's truncation as a chronicle defect. | Cross-source setlist quorum (Q1-a) detects both kinds. |
| S10 | Venue coordinates and venue identity are underspecified. | C6 plus M12. |
| S11 | Date identity: sources are joined to a show only by the parsed `entries.date_str`. A mis-dated catalog entry lands on the wrong show; LB-06654 ("Mono Mixes", studio tracks) matches 0 of 12 songs on 1965-06-01. | G2: a source whose tracklist matches <20% of the setlist is flagged `misdated?`, excluded from the verdict, and listed separately. |
| S12 | The "run" in "biggest rotation of the run" is ambiguous (venue run, or tour). | The claim names its scope: "of the 7-night Zepp Tokyo run". |

## 6. Plan holes

| # | Hole | Fix (plan amendment) |
|---|---|---|
| P1 | No DB QC layer; the plan trusts `taper_attributions`, `venue_geocoded`, `show_picks` and `quality_recording_scores` as given. | New Phase Q0 (below), before Phase 2. |
| P2 | Taper quality isn't addressed at all (M6, M10). | Rules R-T1..R-T3; a family label may use a taper handle only if every member's taper is *confirmed* (not propagated). |
| P3 | `venue.coords` taken from setlist.fm "as text" — that's the city centroid. | C6/M12 fix. |
| P4 | D-02 gate on count equality: two errors can cancel out. | Also require per-song agreement with ≥1 independent setlist source (setlist.fm / bobdylan.com / TUIT) for each badged song. |
| P5 | D-04 relies on Olof's rotation stat alone. | Also require it to match our own recompute from the previous show (86% agree today); otherwise `stated`, no superlative. |
| P6 | Header tour ("Never Ending Tour", from setlist.fm) differs from the D-07 tour ("2010 Tour of Japan", Olof), and one page asserts both. | One tour object per page. The header shows the Olof leg when it isn't a "Recording sessions" bucket, with NET # as the umbrella, and every tour reference uses that object. |
| P7 | `_load_quality` uses the global `MAX(scan_id)`. **383 LBs** graded only in older scans silently lose their grade, and **114 LBs** have newer metrics (scans 19–22) but no score, because no rerank has run since. | Per-LB latest scored scan; gate G6 flags any LB with metrics newer than its score. |
| P8 | Picks are stale against families: `show_picks` was computed 2026-08-31 and `recording_families` imported 2026-09-04. The "best transfer in its family" evidence may describe families that no longer exist. | G6 freshness; the derived chain must re-run picks after every family sync (fix in `tapematch_sync` → recompute hook). |
| P9 | The parser reparse changes thousands of rows, with no review. | Reparse diff report: every event whose song list, titles or annotations changed goes to `.debug/olof_reparse_diff.md`, split into expected classes (P1a–P1g) and unexpected. Unexpected changes block the commit. |
| P10 | D-01 is validated only against itself. | Corroborate against TUIT's per-LB tracklists (3,881 LBs have both; lengths agree within ±2 tracks for 82%). A disagreement lowers completeness to `inferred`. |
| P11 | No golden set; the acceptance checks come from the same code that produces the values. | Q3. |
| P12 | No forbidden-phrase lint. | L1 (below). |

## 7. Database quality findings (feed Q0)

| ID | Issue | Scale | Dossier impact | Fix |
|---|---|---|---|---|
| D1 | Olof parser truncation (guest/interlude blocks) | 99 zero-song concerts, 434 truncated | Wrong or missing setlists, wrong D-02 and D-04 | Plan Phase 1 (P1a) |
| D2 | Olof per-song mis-joins (date lines, stat line) | 6,214 + 2,686 rows | False per-song notes | Plan P1b–P1d |
| D3 | Olof subtitle/credit split | ~1,500 rows | Wrong titles and writers; false premieres | Plan P1e |
| D4 | Derived-table staleness | picks older than families; 114 LBs unscored | Stale ledger and grades | P7/P8; rule R-S1 |
| D5 | Taper propagation by bare text *mention* | 3,683 attributions | False tapers (Millard on 2000s–2010s) | R-T1: a mention of gear or a label is not taper evidence; propagation by mention needs the taper-context pattern ("taped by", "recorded by", "master by") |
| D6 | Propagation through review-flagged families | 168 | Circular or false tapers | R-T2: never propagate through a `review_flag=1` family or one below 0.5 confidence |
| D7 | Propagated taper outside the taper's confirmed era (±5 y) | 510 | Implausible credits | R-T3: finding, then quarantine |
| D8 | Taper disagreement between TUIT and us | 743 of 2,167 (mostly alias spelling, e.g. "Legendary Taper E" vs `lte`) | None today; usable as corroboration once aliases are mapped | Map TUIT names into `user_taper_aliases`; remaining disagreements become `disputed` |
| D9 | `venue_geocoded` wrong-venue matches | 1,141 low-confidence rows (e.g. Zepp Tokyo → Zepp DiverCity) | Wrong venue facts | C6; R-G1 name-token check |
| D10 | setlist.fm coordinates are city centroids | all rows | Mislabelled coordinates | M12 |
| D11 | Mis-dated or compilation catalog entries | e.g. LB-06654 on 1965-06-01; LB-09091/09373 multi-date compilations on 1986-02-24 | Wrong sources ranked on a show | G2 |
| D12 | Undated entries (`xx/xx/61` etc.) | 589 | Excluded, which is correct; they collect under a NULL-date rank-1 bucket in `show_picks` | Leave excluded; make `compute_show_picks` skip NULL dates |
| D13 | Junk timing / cdr values | 2 timing, 24 cdr | Wrong runtime and disc counts | R-E1 range checks |
| D14 | Olof country empty; "London England" appears as a city | 2,705 / 8 | Wrong city grouping | D-07 uses the setlist.fm key; R-O2 |
| D15 | Setlist count disagreement, Olof vs others | Equal counts: setlist.fm 90.8%, bobdylan.com 79.9%, TUIT 69.2% (TUIT and bobdylan.com drop intros and covers differently) | Detects D1 and residual truncation | Q1-a quorum |

## 8. Verification architecture

### Q0 — Database QC (new module `backend/qc/`, table `qc_findings`)

- **Table** (`CREATE TABLE IF NOT EXISTS`): `qc_findings(id, rule_id, entity_kind, entity_key,
  severity[error|warn|info], detail, evidence_json, first_seen, last_seen,
  status[open|confirmed|false_positive|corrected|fixed], decided_by, decided_at, note)`. Unique on
  `(rule_id, entity_kind, entity_key)`.
- **Rules** are one small pure function each, registered in `backend/qc/rules.py`; they return
  findings. First set:

| Rule | Checks |
|---|---|
| R-O1 | Olof raw numbered count > parsed count (truncation) |
| R-O2 | Olof city/country anomalies |
| R-O3 | Annotation shape: date-shaped or stat-shaped notes |
| R-O4 | Olof setlist count disagrees with ≥2 agreeing independent sources |
| R-T1 | Taper evidence is a bare mention with no taper-context pattern |
| R-T2 | Taper propagated through a weak family |
| R-T3 | Taper outside its era |
| R-T4 | Taper disagrees with TUIT after alias mapping |
| R-G1 | Geocode names don't match (venue tokens vs `display_name`) |
| R-E1 | Entry field ranges (timing, cdr, rating vocabulary) |
| R-E2 | Tracklist disjoint from the dated setlist (mis-dated / compilation) |
| R-F1 | Family merged below 0.1 confidence, or `review_flag` set |
| R-S1 | Derived table older than its input (picks vs families, scores vs metrics, `song_performances` vs Olof `parsed_at`) |

- **Runs:** as a new final step of the `/api/derived/recompute` chain; after `olof_parser`,
  `tapematch_sync` and scraper imports; and nightly in the existing cron. CLI:
  `.venv/bin/python3 -m backend.qc run [--rule R-T1]`, which prints a single-line summary per
  rule.
- **Quarantine:** any dossier field whose source row has an *open error* finding renders its
  fallback and is listed under `prov.withheld[]` with the rule ID.
- **Human loop:** findings are worked in the `/qc-review` HTML console (plan Phase 2b),
  modelled on the taper-curation pages. The statuses are confirmed / false_positive /
  corrected / fixed. A `false_positive` is bound to the evidence hash, so it reopens if the
  underlying row changes.

### Q1 — Cross-source corroboration (`backend/qc/corroborate.py`)

- **(a) Setlist quorum:** Olof vs `setlistfm_setlist`, `bobdylan_setlist` and
  `tuit_song_performances`, aligned title by title with the D-01 matcher (not just by count).
  The Olof list is `corroborated` if ≥1 source agrees in order and count (±intro/cover
  conventions), and `disputed` if ≥2 independent sources agree with each other against it.
  - Today this already corrects 1986-02-24 (Olof as parsed: 7; bobdylan.com and TUIT: 25) and
    1975-12-08 (0 vs 22).
- **(b) Per-song premiere and rotation:** recompute from the setlist.fm ordering as well; a
  badge needs Olof's aggregate + our corpus + ≥1 external source to agree.
- **(c) Source tracklist (D-01):** LB site vs TUIT per-LB `setlist_json`.
- **(d) File format (D-11):** TUIT file record vs lineage.
- **(e) Taper:** `taper_attributions` vs TUIT `taper` (after alias mapping).
- **(f) Venue and city:** Olof vs setlist.fm vs `bobdylan_shows`.

### Q2 — Per-dossier QC gate (`backend/dossier_qc.py`, called at the end of `build_dossier`)

| Check | Rule | On failure |
|---|---|---|
| G1 Identity | Date resolves to exactly one Olof event (or a disambiguated `location`); venue agrees with ≥1 of setlist.fm / bobdylan.com | **Refuse** (422 + reasons) |
| G2 Source–show fit | Each source's tracklist matches ≥20% of the setlist (when both exist) | That source is withheld from the verdict and listed as "tracklist doesn't match this show" |
| G3 Provenance | Every non-null field has `source` + `confidence`; no `derived_from` cycles | Withhold the field |
| G4 Quarantine | No field sourced from a row with an open error finding | Withhold the field |
| G5 Invariants | City-history sum = total; runtime split sum = total; ledger sum = `ledger.total` (±0.05); ledger audio evidence = displayed scan score; tape groups ≤ sources; premiere badges = premiere count | Withhold the dependent block |
| G6 Freshness | Each derived input's `computed_at` ≥ its inputs' timestamps | Withhold the dependent fields and show a "stale analysis" note in provenance |
| G7 Claims | Every comparative or positional word comes from a verified Claim; ties produce "tied"; scope is named | Drop the claim text; keep the plain value |
| G8 Channel | In the public view, no comparison references a withheld source, and no private-source attribute appears anywhere | **Refuse** (privacy is never degraded, only refused) |
| G9 Lint | The rendered HTML contains no forbidden phrases (L1) and every `data-lb` is in the registry | Fails the test suite; in production, logs an error and withholds the element |

- **Output:** `dossier["qc"] = {checks_run, passed, withheld:[{key, rule}], refused?, input_fingerprint}`.
  The footer shows "QC: 212 checks · 3 fields withheld · analysis as of …".
- **Lint L1 (forbidden phrases):** "taper unknown", "unknown taper", "none indexed" unless the
  D-03 index was consulted, "independent tapes", and bare "only/highest/best/biggest/first/last/closing"
  outside Claim spans.
- **Lint L2:** the template source may not contain those words outside the claim macro.

### Q3 — Golden set (`tests/golden/dossier/*.json`)

- **15 shows:** the 5 spec samples, plus 10 chosen to stress different failure modes:
  - a two-show day;
  - a 2022+ bobserve show;
  - a guest-set Rolling Thunder date;
  - a Heartbreakers 1986/87 date;
  - a solo acoustic 1960s date;
  - a heavily-propagated-taper date;
  - a show with private sources;
  - a no-setlist date;
  - a compilation-polluted date;
  - a show with official releases.
- Each file lists expected anchor values **verified by tj by hand** against the primary sources
  (Olof page, LB detail page, TUIT).
- The test runs against a fixture DB cut from live data (`tools/make_fixture_db.py`), so it can
  run in CI. Any diff fails; an intended change needs the golden file updated in the same
  commit, with a note.

### Q4 — Corpus sweep (`tools/dossier_sweep.py`, nightly cron)

- Build every concert date's dossier in memory (cache `_rarity_map` for the sweep) and run Q2.
- Write `data/logs/dossier_sweep_<date>.md` with totals by check: refused, fields withheld,
  disputed setlists, stale shows.
- Alert (push notification) if any error count rises against the previous night. This is the
  regression net for parser, scraper and derived-chain changes.

### Q5 — Corrections, never silent edits

- New `corrections(entity_kind, entity_key, field, original, corrected, reason, decided_by,
  decided_at)`, e.g. the "Wille" → "Willie" Dixon credit.
- The dossier renders the corrected value with a "corrected" tooltip showing the original.
  Source tables are never edited in place.

## 9. Required plan amendments (summary)

> **Status: folded into `SHOW_DOSSIER_REDESIGN_PLAN.md` on 2026-09-10.** The phase numbers in
> this section refer to the plan as it stood before the fold. The plan now runs:
> 0 Prerequisites, 1 Parser + diff gate, 2 DB QC and upstream fixes (Q0/Q5),
> 3 Corroboration (Q1), 4 Derivations, 5 View, claims and gate (Q2/C3), 6 §7 defects,
> 7 Template, 8 Tests, golden set, sweep (Q3/Q4), 9 Bookkeeping.

1. Insert **Phase Q0** (DB QC and quarantine) and **Q1** (corroboration) after Phase 1 and
   before Phase 2. D-02, D-04, D-09 and D-01 consume the Q1 results.
2. Phase 1 gains the reparse diff report (P9) as a commit gate.
3. Insert **Phase Q2** (the gate) and the claim engine (C3) into Phase 3. The template
   (Phase 5) may only render verified Claims.
4. Phase 6 gains the golden set (Q3), lints L1/L2, and the sweep (Q4).
5. Rewritten acceptance cases:
   - 2010-03-29 `is_last` = **false**. The verdict may say "last night of the Japan leg" only
     if a leg concept exists; it doesn't, so no closing claim.
   - The tour premieres are songs 4 and 14, not 13 and 16.
   - LB-08485's resolution shows "16/44 file · recorded 24/96".
   - "Scanned quality" shows the per-LB latest scored scan.
6. Upstream fixes, each its own BUG/TODO: taper propagation (D5–D7), the picks-after-families
   recompute hook (P8), per-LB scan selection (P7), and skipping NULL dates in picks (D12).

## Appendix — claim-engine contract (C3)

```python
Claim(kind="superlative|exclusive|position|premiere|comparison",
      text_key="i18n-free template id", slots={...Field refs...},
      scope="venue_run|tour|show|visible_sources",
      verified_by="comparator id", ties=int, derived_from=[...])
```

- A comparator returns a Claim only if all of these hold:
  - every sibling or candidate has the compared value (no nulls);
  - no compared value is `disputed` or `withheld`;
  - the claimed scope was fully loaded (e.g. every night of the run is present);
  - ties are reported, never broken silently.
- Otherwise it returns `None`, and the template falls back to the plain value.
