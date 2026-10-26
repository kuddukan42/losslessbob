# Golden-dossier correction plan 2 (C32i)

Source: second adversarial review of the golden set (2026-09-25, in-session), run on a fresh
export after C32h. `tools/dossier_audit.py` passed clean (8 known source conflicts); every
finding below came from reading the 16 pages by hand. Evidence: `.debug/dossier_review2/`.

## Status

| Step | What | State |
|---|---|---|
| 1 | Code fixes (table below) + tests | done |
| 2 | Backup (`data/backups/losslessbob_preC32i_20260925_1003.db`), `show_picks` recompute (rank-1 changed on 22 dates), backend restart | done |
| 3 | Golden case renames + new case, fixture re-cut, `--check` 16/16 | done |
| 4 | Export + `dossier_audit.py` (8 known conflicts, 0 structural) + page re-read | done |
| 5 | Live Olof + bobserve reparse (medley credits, bobserve subtitles) | done with tj's go-ahead (TODO-353) |

## Fixes

| # | Sev | Finding | Fix |
|---|---|---|---|
| 1 | High | A disputed taper credit (R-T6: family carries 2+ confirmed tapers) still earned the ranker's +3 "confirmed taper" bonus; it flipped the pick on 1987-10-11 (94.1 vs 92.9) and 1995-03-16 (105.4 vs 103.2) | `concert_ranker/picks.py` `_disputed_taper_lbs`; `conflict = 1` rows excluded too. Reputation medians unchanged |
| 2 | High | "has the complete setlist (the pick does not)" when the pick's completeness is unknown (1975-11-11, 165-min whole-show master) | `compare_sources`: complete axis needs a *known* incomplete pick (tracklist basis) |
| 3 | Med | "is a soundboard (the pick is not)" for an untyped pick (1965-06-01, all BBC TV transfers) | soundboard axis needs a typed, non-soundboard pick |
| 4 | Med | Bobtalk intros not anchored: shortened cue titles ("(before It Takes A Lot To Laugh)") and uncued intros naming the song ("It's called Isis.") | `anchor_bobtalk`: 3+ word prefix fallback; uncued quote naming exactly one song (case-sensitive, whole words) anchors with cue `mentions` |
| 5 | Med | Family band counted hidden members (1975-12-08 "5 sources", 1 shown); "N tape groups" counted fragment-only buckets | `dossier_anchors._primary_member_count` for both |
| 6 | Med | One family mixing Audience and Soundboard types went unflagged (1986-02-24, 1990-01-25) | family band shows "mixed source types" with the types in its tooltip |
| 7 | Med | Medley credits: "I Walk The Line (Johnny Cash) / Blue Moon Of Kentucky" credited only Bill Monroe (22 rows) | `olof_parser._split_title_parts` splits per medley part. **Needs live Olof reparse (step 5)** |
| 8 | Med | bobserve subtitles as writers ("And I'll Go Mine", "Philosopher Pirate"), 438 rows | parser already fixed in C32b (B6); the C32h rebuild never reparsed bobserve pages. **Needs live bobserve reparse (step 5)** |
| 9 | Low | Olof page furniture in Notes ("Other Bob Dylan concerts in …", "Songs without numbers are performed by The Band …") | `dossier_anchors._strip_page_furniture` |
| 10 | Low | Lineage clipped at 160 chars ended mid-hop ("Macbook Pro >") | `lineage_short` appends " …" to a chain ≥155 chars |
| 11 | Low | QC footer names withheld LBs the page doesn't list; "1 shows", "night(s)" | footer adds "not listed above"; plurals fixed |
| 13 | High | Found while exporting: the claim engine crashed on 1974-01-06 (no claims on either show) -- C32h made `venue_run.dates` per night but `event_ids` stayed per show, and `rotation_rank` zips them `strict=True` | `VenueRun.event_dates` (per show) feeds `rotation_rank` |
| 12 | Low | Case names stale: "propagated-tapers" shows no propagated taper, "no-setlist" has 16 songs | renamed to `1999-06-11_guest-medley`, `1989-06-13_paren-titles`; new `2006-04-30_propagated-tapers` (most renderable propagated credits) |

## Deliberately not changed

- "rdigitally eleased" (1975-12-04 #11), "Bob Dylan harmonica", "Larry Campbell fiddle",
  "Wille Dixon": Olof's own text, verified in `raw_text`; stays verbatim.
- Venue-history names differing from the header (Les Arènes / Arènes de Frejus, Sambodromo /
  Praça da Apoteose): Olof's per-show names vs the geocoded name; both stated.
- 1995-03-16 pick carries "inferior transfer within its family"; fix 1 decides that date.
- Personnel gaps (1986-06-22 Heartbreakers unnamed, 2024 guest in flat list): parser-side,
  low value; left for TODO-342 C34+.
- Lossy-veto double reasons on excluded rows: TODO-351.

## Verification

- `pytest tests/test_dossier*.py tests/test_olof_parser_fixes.py tests/test_taper_attribution.py
  tests/test_qc*.py tests/test_setlist_confidence_file_meta.py tests/test_show_picks.py`
- Live: backup → `compute_show_picks` → `/backend-restart` → `make_fixture_db.py --golden` →
  `dossier_golden.py --check` → `--html ~/Documents/projects/losslessbob_dossiers` →
  `dossier_audit.py` → re-read the affected pages.
