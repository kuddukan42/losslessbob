# TODO-234 — series-vs-series taper-conflict review (2026-07-16)

Evidence review of the 22 conflict=1 rows in `taper_attributions` (the full
queue — it shrank from 53 to 22 since the TODO was filed). Method: rebuilt the
strong-edge components (family cliques + same_as/derived_from, per
`taper_attribution._propagate_strong`), pulled pairwise evidence from
`tools/tapematch/observations.db` (corr / fp / windowed / hiss / emb), and read
the source descriptions for every label in dispute.

**Headline: the TODO's framing ("all 22 are family false-merges") is wrong.**
The 22 rows collapse to 11 graph components with three distinct root causes:

1. **Taper label errors** (3 LBs) — wrong/hedged layer-0 labels, audio decides.
2. **Bogus `same_as` lineage edges** (5 LBs) — parser misreads; families agree
   with audio, the lineage edges bridge unrelated tapes.
3. **True family over-merges** (7 families) — low-corroboration fp merges,
   mostly staircase pairs in the fp 0.40–0.49 zone; exactly the population the
   parked post-7/12 gating changes (CALIBRATION_PROGRESS.md tail: corroborating
   signal gate / pair-scoped 0.40 / raised `cluster_threshold_staircase`)
   are meant to block. **These become the validation set for the TODO-235
   rescore** — do not hand-split them first.

---

## Per-component dispositions

| Component (date) | Conflict | Evidence | Disposition |
|---|---|---|---|
| 1995-12-09 | lta(15211) vs ntj(6083) | subclusters {534,5710} emb .996, {6104,15211} corr .42/hiss .94; 6083 isolated (fp≈.41, win 0, hiss 0) | **Over-merge → rescore.** Expect 6083 split out. Labels fine. |
| 1995-07-04 | ntf(5879) vs nti(5681) | {1899,5681} corr .36; 5879 weak to both (corr .05) | **Over-merge → rescore.** Expect 5879 split out. |
| 1996-07-07 | nta(15322) vs nti(5776,6252,8818) | {2082,3059} .93, {3439,5776,6252} .91–.98; 15322 max corr .108, 15574 max .035, 8818 max .068 | **Over-merge → rescore.** Expect 15322 (and likely 15574, 8818) split out. |
| 1995-05-26 | nta(5362) vs ntd(13215,14859) | 5362~13215/14859 corr **.514**; 5362 desc says "(**probably** NET Taper A)"; 13215/14859 are documented NTD/LTA-transfer | **Label error → curator reject `net taper a` on LB-5362.** Audio ties it to the NTD tape. Family keep. |
| 1996-05-16 | nta(821, curator-CONFIRMED) vs ltg(7544,7823) | 821~7823 corr **.906** (same tape); 7823 desc: "Taper: unidentified… same recording as ltg" (clapping/spectral guess). Separate cluster {2273,7544} corr .53 | **Label error → curator reject `ltg` on LB-7823** (audio beats the uploader's guess). Remaining 7544-vs-821 conflict is an **over-merge → rescore** (two clusters, cross-corr ≤ .07). |
| 1997-04-05 | nta(3344) vs ntj(8854,9240) | {3344,3559} .988 vs {8854,9240} .972, cross .03; 9240 desc claims "Same recording as LB-3344/3559/8854" — audio contradicts for 3344/3559 | **Edge fix:** drop 3344,3559 from 9240's same_as/derived (keep 8854). Then **over-merge → rescore** for the family split. 3344's "NET TAPER A AGAIN?????" is hedged but intra-cluster, harmless after split. |
| 1990-11-08 | ltd(8251,9060) vs ltf(13427) | 13427 desc: "**different** recording from LTD LB-01219/03730/07094/08251" — parser stored these as same_as (tie-break bug); audio: different_family everywhere (corr ≤ .003) | **Edge fix:** clear LB-13427 same_as. Families already correct. |
| 1993-02-07 | lta(5882) vs ltb(1343) | {5882,12768} .90; 1343 links .29–.32 (staircase) | **Over-merge → rescore.** Borderline; the raised staircase threshold (change c) should split it. |
| 1990-08-12 | ltf(12257) vs ltm(12353,14330) | 12257's own torrent comments: "torrenter **corrected taper to LTM**"; all corr ≤ .016, merged on bare fp .40–.49 | **Label error → curator reject `ltf` on LB-12257** (all named members are LTM → conflict clears regardless of family shape). Family itself is fp-only glue — rescore may disband it; taper-neutral either way. |
| 1988-07-17 | ltc(10935) vs ltg(1297 CONFIRMED, 10937) | Families match audio ({7541,7554,10754,10935} .63–1.0; {7126,10937}; 1297, 14671 singletons; all cross pairs different_family). Bridges are parser over-claims: 7126 ("LB-1297 is the only recording listed for this date"), 7541 ("drop… mentioned on LB-7126"), 14671 (one-track patch "(b) from LB-1297") | **Edge fix:** clear same_as/derived on LB-7126, LB-7541, LB-14671 (toward 1297/7126). No family action. |
| 1997-08-17 | ltf(5761) vs ntm(12866) | {2129,12866,13290} emb .94–.96; 5761 weak (emb .65, corr .03) | **Over-merge → rescore.** Expect 5761 split out. |

## Immediate actions

**A. Curator rejects — APPLIED 2026-07-16 (tj sign-off)** (`taper_confirmations`,
action='reject' — survive rescore):

- LB-5362 reject `net taper a` → now `net taper d` (propagated) ✓
- LB-7823 reject `ltg` → unattributed until its family splits (821-vs-7544
  conflict remains by design); expect `net taper a` post-rescore
- LB-12257 reject `ltf` → now `ltm` (propagated) ✓

Recompute done: conflict queue **22 → 18**. Remaining 18 = the 1988-07-17 +
1990-11-08 components (6 rows, blocked on held action B) + the over-merge
families (12 rows, deferred to the TODO-235 rescore).

**B. `same_as`/`derived_from` corrections — ON HOLD (tj: discuss first)**
(`entry_lineage` — survive normal
re-parse via source_text_hash guard; a `--force` re-parse would clobber, noted
in the parser TODO below):

- LB-13427: same_as [1219,3730,7094,8251,9060] → []
- LB-7126: same_as [1297] → [], derived [1297] → []
- LB-7541: same_as [1297,7126] → []
- LB-14671: same_as [1297] → []
- LB-9240: same_as/derived [3344,3559,8854] → [8854]

Then `taper_attribution.recompute()`. Expected: components 1995-05-26,
1990-08-12, 1990-11-08, 1988-07-17 clear ≈ conflict queue 22 → ~13.

**C. Proposed new TODO — ON HOLD (tj: discuss first) — lineage parser tie-break bug:** `extract_lb_references`
(backend/db.py:2097) stores same_as when `same_count >= diff_count`; a window
with "different recording from LB-X … same recording as …" ties 1-1 and stores
the *different* refs as same_as (LB-13427 case). Fix: require `same_count >
diff_count` (or proximity-weight), then targeted re-parse + diff review.

## Deferred to TODO-235 rescore — validation expectations

After the gating changes + corpus rescore + `tapematch_sync`, verify these
splits happened (if any survive, hand-split via family review then):

**RESCORED LIVE 2026-07-17** (runs 20260717_082233–092849; committed config with
corroboration gate). Outcome: hazard blocked, but most expected splits did NOT
happen — live runs found evidence the cached replay lacked. Per date:

- [x] 1995-12-09: PARTIAL — {534,5710} split out ✓, but 6083 stayed with
  {6104,15211}: 6104 staircase-flagged in pass 1 → relaxed fp .409, and the
  corroboration gate passed at the EXACT boundary (hiss_frac 0.05 == floor,
  hiss_median .05). Boundary artifact — gate floor has no median requirement.
  lta-vs-ntj conflict persists.
- [x] 1995-07-04: NO SPLIT (as the sweep predicted for variant (a)) — 5879
  passes on hiss corroboration .111. Conflict persists → hand-split candidate.
- [x] 1996-07-07: NO SPLIT, and evidence now CONTRADICTS the split expectation:
  windowed_frac .95 between the two supposed subclusters (2082/3059 ↔
  3439/5776/6252) is decisive same-source evidence; 8818/15322/15574 glue via
  plain-bar fp .50–.54. Disposition should flip: over-merge → label review.
- [x] 1996-05-16: NO SPLIT — bridge 7544–7823 crosses the UNRELAXED fp bar
  (.504 ≥ .50); 3429–7823 hiss .637/median .422 also near lo-fi merge. Family
  holds on plain-bar evidence; nta(821 CONFIRMED)-vs-ltg(7544) persists.
- [x] 1997-04-05: NO SPLIT — bridge 3559–8854 fp .505 ≥ .50 (unrelaxed).
  Note held action B (drop 3344/3559 from 9240 same_as) is independent of this.
- [x] 1993-02-07: NO SPLIT — 1343–5882 is a genuine hiss merge (.62 frac /
  .727 median) and 1343–4216 fp .588 plain bar. Family holds on real evidence;
  the old "change (c) should split it" expectation died with (c)'s rejection.
- [x] 1997-08-17: NO SPLIT (as the sweep predicted for (a)) — 5761 passes on
  hiss corroboration .191 at relaxed fp .445. Conflict persists.
- [x] 1997-11-11 (hazard date): **GATE VALIDATED** — LB-01126 now isolated
  (own family; {13287,9042,4854} intact, 4283 separate). The exact 2026-07-11
  false merge no longer occurs live.
- [x] `tapematch_sync` (2,032 dates, 5,811 families, 0 errors) +
  `taper_attribution.recompute()` run 2026-07-17. Conflict queue did NOT reach
  0 — expected, since the families largely held; surviving conflicts need
  either hand-splits (95-07-04, 97-08-17, 95-12-09) or disposition flips to
  label review (96-07-07, and plausibly 96-05-16 / 97-04-05 / 93-02-07 where
  plain-bar fp/hiss now vouch for the family). tj decision needed.

## Resume tracking

- [x] Evidence review (all 11 components) — 2026-07-16
- [x] Apply A, recompute — queue 22 → 18 (2026-07-16)
- [ ] B: same_as edge fixes — ON HOLD pending tj (would clear 6 more rows)
- [ ] C: file parser TODO — ON HOLD pending tj
- [x] Post-rescore validation — DONE 2026-07-17 on live re-runs (results above).
  Gate validated (1997-11-11); most families HELD on real evidence.
- [ ] tj: disposition call per surviving family — hand-split (95-07-04, 97-08-17,
  95-12-09) vs flip to label review (96-07-07 strongly; 96-05-16 / 97-04-05 /
  93-02-07 plausibly). Until then the ~12 series-vs-series rows stay in the queue
  BY DESIGN — do not "fix" them by hand-editing families without sign-off.
- [ ] Full-corpus rescore batch drains ~2026-07-20 → completion runbook at the tail
  of tools/tapematch/CALIBRATION_PROGRESS.md (sync + recompute + spot-checks).
