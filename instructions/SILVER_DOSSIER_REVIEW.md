# Silver-dossier review (C32k)

Purpose: test whether the C32a–j golden fixes generalise. 15 new "silver" dates, chosen from a
per-date feature table (source count, private, soundboard, mix, "alternate to", compilation,
confirmed/propagated/conflicted tapers, Olof event count, bobserve, official releases, guests) to
mirror the golden spread without repeating a golden date. Specs: `tests/silver/dossier/*.json`
(review-only — no fixture, no `expected`). Render: `tools/dossier_golden.py --html DIR --specs
tests/silver/dossier`. Evidence: `.debug/silver_export/`, `.debug/silver_text{,_v1}/`.

`tools/dossier_audit.py`: 0 structural findings; 8 setlist diffs (title spelling, Olof vs bobserve
counts) — same class as the golden set's known conflicts.

## Did the golden fixes generalise?

| Golden fix | Silver evidence |
|---|---|
| Disputed-taper bonus (C32i #1) | holds — 1997-02-16, 2002-04-28, 2013-11-16 disputed credits get no +3 |
| "Alternate to LB-x" (C32j #5) | holds — 1999-07-20 LB-09657 stays an independent recording |
| Two-show selector / per-night runs (C32h, C32i #13) | holds — 1974-01-26, 1975-11-06, 2000-03-10 render both shows with claims |
| Page-furniture strip (C32i #9) | partial — missed the singular "Other Bob Dylan concert in …:" + its list, and "Reviews from BobLinks." (fixed, below) |
| same_as negation guard (C32a E1) | partial — clause guard splits on commas, so "different recording than LB-a, LB-b" and a nearby "same recording" still linked (fixed, below) |

## Findings and fixes

| # | Sev | Finding | Fix | Live step |
|---|---|---|---|---|
| 1 | High | `extract_lb_references` ±200-char window: a "same recording" phrase vouched for every LB near it. LB-13981's private note ("of the other 3 LB-1116 is most distant…; LB-14078 is same recording as this") linked LB-1116/13219 and relayed pdub onto LB-01116 (an FOB Schoeps master) and LB-14078 (1998-05-21). Corpus: 123 of 1,112 same_as edges wrong, most "different recording than LB-x" | same-phrases bind to the LB refs in their own sentence (`;`, `. `, blank line); a "different …" phrase earlier in a ref's sentence refuses it; "Fixed LB-x" / "LosslessBob entry: LB-x" / "previous version = LB-x" count as same (+61 edges) | parse_lineage --force, attribute_tapers, show_picks |
| 2 | High | Olof bobtalk ran into the "CD bootlegs" list; bootleg titles rendered as Bobtalk (1965-09-03; 6 events, all 1965/66) | `olof_parser` bobtalk stops at bootleg/release headers | Olof reparse |
| 3 | High | Venue run keyed on venue name only: Providence + Springfield "Civic Center" = "2-night run", "Closing night" on 1975-11-06 afternoon; 11 false runs corpus-wide | `run_context` also requires the city (containment — Olof's "Tokyo International Forum Tokyo") | none (render-time) |
| 4 | Med | Chronicle glued the next range entry onto a date ("…Lone Star Café. 11 April – 17 May The Infidels recording sessions…", 1983-02-16); full reparse 1,244 → 1,264 rows (6 range + 14 season headings split off) | `olof_chronicle_parser` recognises cross-month range and season headings | chronicle reparse |
| 5 | Low | Furniture: singular "Other Bob Dylan concert in <city>:" + date/venue lines, "Review(s) from BobLinks." (711 events) | `_strip_page_furniture` | none |
| 6 | Low | Tour-premiere names joined with ", " — "I Am The Man, Thomas, My Back Pages, …" reads as 11 songs for 9 | joined with "; " | none |
| 7 | Low | Uncued band intro "This is called It's Alright Ma" not anchored to "It's Alright, Ma" (1978-02-28) | mention match ignores commas | none |

## For tj — not changed

| # | Finding | Why it's yours |
|---|---|---|
| A | Silver/unrated copies with carbonbit +8 out-rank masters on 3 of 15 dates (1962-07-02 silver SBD over the A+-scanned family member; 2002-04-28 silver over schubert/zimmy21 masters; 2024-10-04 unrated silver, baseline 40, over bach's 24/48 master) | generalises the open 1989-06-04 ranking question (C32j #8) |
| B | TapeMatch families span distinct stated rigs: 2013-11-16 "Family A" = 3dogs Core Sound, condor OKM II, zimmy21 SP-CMC-10, Schoeps CCM4; 2002-04-28 = schubert Neumann + zimmy21 AKG. The ±5/−3 "within its tape family" terms then compare different recordings | family merge policy (tapematch), not dossier |
| C | 61 of 1,783 series-code credits are hedged in the text ("net taper D ?", "legendary taper C ?") but count as confirmed (+3); e.g. 2000-03-10 pick LB-14402 | catalog convention vs. uncertainty — demote to propagated? |
| D | Propagated credits sourced only from a **private** entry show on the public channel (1989-10-20 LB-01777 "lte" via private LB-6539); no private LB number leaks | channel policy |
| E | "Longer runtime" alternates from sources holding other material: 1965-09-03 LB-09432 144 min (show ≈75), 2000-03-10 LB-08757 141 min / LB-04380 129 min (both shows) | runtime is a plain fact by your rule; flag "includes other material"? |
| F | Both-shows sources appear on one show's page only (1974-01-26 LB-01610, Olof lists it for both; 2000-03-10 LB-08757/LB-04380) | two-show assignment policy |
| G | Olof per-song range notes render as song annotations: "are incomplete", "mono audience recording, 60 minutes" on 14 songs (1975-11-06 evening) | Olof's text; strip the copula/duration or keep verbatim? |
| H | 2013-11-16 pick states "Taper: 3dogs" but 3dogs isn't a known handle, so no credit | alias-list candidate |
| I | 1999-07-20 LB-13779 "DAT copy" classed master (named-recorder rule) | generation rule edge |

## Re-review after the live rebuild

Found on the second read (setlists of 1989–2000 were skimmed in pass 1):

| # | Sev | Finding | Fix |
|---|---|---|---|
| 8 | Med | A medley Olof wraps onto the next line ("That'll Be The Day (…) /" ⏎ "The Wanderer (E. Maresca)") lost its second song and rendered the credit in the title (1999-07-20; 19 events) | `olof_parser` joins continuation lines while the title ends in "/" (BUG-363) |

Everything else on the 21 pages re-read clean: 1965 Bobtalk is empty (bootleg titles gone), 1983
chronicle ends at the Lone Star Café, LB-01116/LB-14078 carry no pdub credit, 1975-11-06 has no run
claim. Audit: 0 structural, 8 known setlist diffs (the 1999 one is now medley-vs-split rendering).

## Status

Done 2026-09-25 with tj's OK. Backups `data/backups/losslessbob_preC32k_20260925_1434.db` (before
everything) and `…_preC32k_medley_*.db` (before the medley reparse). Live: Olof + chronicle reparse
(chronicle 1,244 → 1,264), compute_song_performances (72,994, unchanged), parse_lineage --force,
attribute_tapers (5,263 → 5,206; propagated 784 → 727), show_picks (0 rank-1 changes), qc run,
backend restart; golden `--check` 18/18 (no fixture re-cut needed). Decisions A–I remain with tj
(TODO-354).
