# Golden-dossier correction plan 3 (C32j)

Source: third adversarial review of the golden set (2026-09-25, in-session), after C32i and the
TODO-353 reparse. Audit clean (8 known conflicts), fixture 16/16. New finding came from the new
`2006-04-30_propagated-tapers` case.

## Findings and fixes

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | High | LB-08495 "jh mix of jh and m&a" matches both tapes, so TapeMatch put the jh tape (LB-03752, LB-08530 and its remasters LB-03760/03761) and the m&a tape (LB-03808) in one family; m&a was propagated onto the jh tape | `taper_attribution._load_mix_sources`: a family holding a mix/matrix member (source_type Mixed, or "mix"/"matrix" on the first line) is not a propagation edge. `_MATRIX_RE` now also matches "mix", so a mix never *receives* a taper either |
| 2 | Med | An entry opening "M&A Recording, MBHO 603a > …" (LB-03808) named its own taper but was only credited via propagation | `explicit_credit`: a description opening "<alias> Recording" is an explicit credit, unless it disowns it ("NOT his recording", LB-01542) |
| 5 | High | Found on the replacement case 1989-06-04: LB-14054 "Alternate to LB-2470/LB-2478/…, which appear to be derived from same recording" was parsed as same_as **and** derived_from all five, and relayed LTD to them and to itself | `db.extract_lb_references`: "alternate/alternative (recording) to" is a `_DIFF_RE` phrase and negates the whole chained LB list, for same_as and derived_from; a generic "not" still doesn't block derived_from ("is not LB-67; it is derived from it"). Live: 11 entries, 31 same_as + 5 derived_from links dropped |
| 6 | High | 34 of 1,339 same_as/derived_from edges join entries of different dates; 5 propagated credits rode them (LB-05661 2004 ← LB-02841, a 1998 compilation; LB-05364 2000 ↔ LB-04002 2006) | `taper_attribution._drop_cross_date_edges` |
| 7 | Low | Pick why-line said "taped by lta" for a propagated credit | `dossier_claims.verdict_why` appends " (inferred)" / " (disputed)" |
| 8 | — | 1989-06-04 pick is LB-10916, a silver EAC copy ("offers nothing new" −10) that edges the LTD master LB-07214 80 vs 79 on carbonbit's +8 | not changed: ranking policy, for tj |
| 3 | Low | "100% complete" beside the pick's own "Crash On The Levee incomplete" (1995-03-16) | not changed: completeness counts songs present by design |
| 4 | Low | Runner-up repeated under Alternates with the same reason | not changed: pre-existing layout, low value |

## Rejected approach

Contesting a propagation when the target's `entry_lineage.taper_name` names a different taper.
The leading handle is often the *transferer*, not the taper ("cb, legendary taper D" is a
carbonbit transfer of an LTD tape; "jf, legendary taper E"), and the field is free text
("complete aud", "raw", "lowgen"). Dry run: 109 propagations flipped to conflict, many wrongly.

## Dry-run impact (in-memory vs live table)

95 none→confirmed and 6 propagated→confirmed (lead "<alias> Recording" credits: m&a, Schubert,
Bach, hv); 8 propagated→none (the 2006 jh tape; bootleg/silver copies in mix-bridged families);
18 none→propagated (components split by a mix now have one confirmed taper); 23 none→conflict and
5 propagated→conflict (LB-04002 "M&A Recording" now contradicts the bt credit in its family).

## Status

Done 2026-09-25. Backups `data/backups/losslessbob_preC32j_20260925_1101.db` (before tapers) and
`…_preC32j_lineage_20260925_1109.db` (before the forced lineage re-parse). Live: parse_lineage
--force, attribute_tapers (5,263 attributions; 784 propagated, was 803 before C32j), show_picks
(rank-1 changed on 4 dates), qc run (R-T3 7→4). Golden cases: `2006-04-30_mix-bridged-family`,
`1989-06-04_alternate-recording`, `2004-10-21_propagated-tapers`; fixture --check 18/18; audit 8
known conflicts; full suite 2,879 passed.

## Verification

`pytest tests/test_taper*.py tests/test_dossier*.py tests/test_show_picks.py`; live: backup →
`tools/attribute_tapers.py` → `compute_show_picks` → `backend.qc run` → `/backend-restart` →
`make_fixture_db.py --golden` → `dossier_golden.py --check` → `--html` → `dossier_audit.py` →
re-read 2006-04-30.
