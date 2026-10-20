# TUIT ↔ entries reconciliation (TODO-332, TODO-339 parts 1–2)

Generated 2026-10-20 02:47 UTC by `tools/tuit_reconcile.py` (read-only). 5468 TUIT recordings, 5436 claim an LB number; 5436 pairs over 5300 LBs join an entry.

## Headline

- Dates: 5373 agree, 4 full-date conflict rows (multi_night 2, tuit_lb_wrong 2), 59 circa rows of which 5 are single-show refinements.
- Source type: 4883 agree, 100 conflicts, 453 rows where only TUIT has one.
- Fill plan: 6496 additive values (setlist 917, source_chain 2335, source_type 434, venue 2810).

Stage the fills (dry run first; `--apply` backs the DB up to `data/backups/` and audit-logs to `data/logs/tuit_reconcile_audit.jsonl`; `--revert --apply` undoes):

```
.venv/bin/python3 tools/tuit_reconcile.py --fill
.venv/bin/python3 tools/tuit_reconcile.py --fill --apply
```

## Per-field policy

| field | TUIT is | why |
|---|---|---|
| date | advisory | 99.9% agree; the residue is TUIT misattribution or compilations, ne... |
| source_type | additive (fill blank) / advisory on conflict | entries.source_type is curator-edited; conflicts need the lineage text |
| venue | additive | entries has no venue column; TUIT's is structured |
| lineage | additive | fills an empty source_chain only |
| setlist | additive | fills an empty setlist only |
| taper | advisory | handled by the taper curation console (TODO-213/339 (4)) |

Fills are staged in `corrections` (`entity_kind='entry'`, `decided_by='tuit_reconcile'`), never written into `entries`: the scraper rewrites entries rows with INSERT OR REPLACE, and a non-NULL `entries.metadata_source` makes the public master export strip the row. No reader consumes entry corrections yet — rendering them is follow-up work.

## Dates

| class | rows |
|---|---|
| agree | 5373 |
| circa_mismatch | 24 |
| circa_refine | 35 |
| conflict | 4 |

### Full-date conflicts

| LB | rec | LB date | TUIT date | TUIT venue | LB setlist ~ LB date | ~ TUIT date | class | action |
|---|---|---|---|---|---|---|---|---|
| 12610 | 4495 | 4/17/17 | 2015-10-30 | O2 Guildhall Southampton | 20/22 | 14/22 | tuit_lb_wrong | Fix TUIT's lb_number (tracker side); LB date stands — setlist match... |
| 13920 | 4233 | 10/9/93 | 1993-09-19 | Walnut Creek Amphitheatre | 13/13 | 5/13 | tuit_lb_wrong | Fix TUIT's lb_number (tracker side); LB date stands — setlist match... |
| 13944 | 3812 | 6/3/78 | 1978-06-01 | Universal Amphitheater | 27/37 | 26/37 | multi_night | Leave — 97-song multi-night Universal Amphitheatre set fits both 6/... |
| 13944 | 5268 | 6/3/78 | 1978-06-01 | Universal Amphitheater | 27/37 | 26/37 | multi_night | Leave — 97-song multi-night Universal Amphitheatre set fits both 6/... |

### Circa-date refinements (TODO-339 part 1)

| class | rows |
|---|---|
| compilation | 27 |
| misattribution | 16 |
| single_show | 5 |
| unverified | 11 |

| LB | rec | LB date | TUIT date | LB location | TUIT venue | class | action |
|---|---|---|---|---|---|---|---|
| 10 | 4362 | 7/xx/87 | 1987-07-19 | US tour with Grateful Dead | Autzen Stadium | unverified | Review: no olof venue match on TUIT date |
| 24 | 4460 | 7/xx/87 | 1987-07-04 | Dylan & the Dead Live, | Sullivan Stadium | unverified | Review: no olof venue match on TUIT date |
| 24 | 5922 | 7/xx/87 | 1987-07-04 | Dylan & the Dead Live, | Sullivan Stadium | unverified | Review: no olof venue match on TUIT date |
| 558 | 358 | 5/xx/94 | 1994-05-22 | The Great Music Experience (Nara City, Japan) | The Great Music Experience | single_show | Arguably refine to 1994-05-22 (Nara, Great Music Experience) — same... |
| 703 | 5371 | xx/xx/74 | 1974-01-03 | Hero Blues - All known versions | Chicago Stadium | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 966 | 5366 | xx/xx/64 | 1995-06-25 | Singing with the Crow bootleg | RFK Stadium | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1138 | 5385 | xx/xx/98 | 1998-01-17 | MASTERS (BobDylan.com) | The Theater, Madison Square Garden | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1369 | 4360 | xx/xx/63 | 1963-08-17 | LK's Bob Dylan & Joan Baez Together Again 63-64 | Forest Hills Tennis Stadium | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1460 | 5364 | xx/xx/63 | 1963-07-26 | LK's Bob Dylan & Joan Baez Together Again 63-64 - LK Remaster | Freebody Park | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1688 | 1667 | xx/xx/62 | 1961-09-06 | Early Recordings Vol. II | Gaslight Caf | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1716 | 1638 | xx/xx/61 | 1961-11-04 | Early Recordings Vol. III, Walls Of Concert Halls | Carnegie Chapter Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 1978 | 5352 | xx/xx/61 | 1997-12-01 | Complete Bob Dylan.com, (8 CDs) | Coca Cola Roxy Theatre | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 2024 | 5365 | xx/xx/64 | 1964-05-17 | Fantasy Records acetate | Right), Royal Festival Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 2114 | 5387 | xx/xx/99 | 1999-06-14 | ACE OF CLUBS | Erb Memorial Union Ballroom, University of Oregon | unverified | Review: no olof venue match on TUIT date |
| 2311 | 1702 | xx/xx/64 | 1998-01-24 | Friends will Arrive, Friends will Disappear | Fleet Center | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 2558 | 4313 | xx/xx/61 | 1961-12-22 | THE GREAT WHITE WONDER | The Home Of Bonnie Beecher | unverified | Review: no olof venue match on TUIT date |
| 2852 | 1636 | xx/xx/61 | 1961-11-04 | Carnegie Chaper hall, NYC | Carnegie Chapter Hall | single_show | Refine to 1961-11-04 (Carnegie Chapter Hall) — needs an entry date_... |
| 2862 | 1611 | 2/xx/61 | 1961-12-22 | Gleason Home Tape | The Home Of Bonnie Beecher | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 3004 | 1641 | xx/xx/61 | 1962-08-11 | TELEPHONE TAPE AND MISCELLANEOUS PERFORMANCES | The Home Of Dave Whitaker | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 3014 | 1699 | 5/xx/64 | 1964-05-12 | BBC Studios, London, England | BBC Studios | single_show | Refine date once an entry date_str correction consumer exists |
| 3016 | 1640 | xx/xx/61 | 1961-11-04 | Hard Times In NYC | Carnegie Chapter Hall | unverified | Review: no olof venue match on TUIT date |
| 3524 | 4354 | xx/xx/61 | 1961-05-06 | Pre-Columbian Bob Dylan Volume Four | Montewese Hotel | unverified | Review: no olof venue match on TUIT date |
| 4820 | 3772 | xx/xx/60 | 1975-09-10 | Various dvd 39 | The World Of John Hammond' TV-program | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 4836 | 5356 | 5/xx/62 | 2007-05-01 | Broadside Show, WBAI-FM, New York, NY | Broadside Show, WBAI-FM | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 4837 | 5357 | 5/xx/62 | 1963-07-30 | Broadside Show, WBAI-FM, New York, NY | Broadside Show, WBAI-FM | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 4902 | 4178 | xx/xx/65 | 1965-04-26 | 1965 Odds and Ends | Arrival Area, London Airport | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 4916 | 5916 | xx/xx/61 | 1961-09-06 | Hollow Horn Reference Recording, Volume 2 | Gaslight Caf | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 4952 | 3803 | xx/xx/65 | 1965-05-06 | several dates in May | City Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 5441 | 1619 | 9/xx/61 | 1961-09-06 | Gaslight Cafe, NYC | Gaslight Caf | single_show | Refine date once an entry date_str correction consumer exists |
| 5627 | 5358 | 10/xx/62 | 2007-12-23 | Gaslight Cafe, New York City, New York | Gaslight Cafe | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 5982 | 1618 | 9/xx/61 | 1961-09-06 | Gaslight Caf, New York City, New York | Gaslight Caf | single_show | Refine date once an entry date_str correction consumer exists |
| 6629 | 1612 | 2/xx/61 | 1961-11-04 | New Jersey | Carnegie Chapter Hall | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 6644 | 5355 | 4/xx/62 | 1964-02-01 | Gerde's,NYC | CBC TV Studios, Toronto | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 6646 | 5360 | 11/xx/62 | 1963-08-28 | NY | Lincoln Memorial | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 6676 | 5369 | xx/xx/66 | 1966-02-26 | collection | Island Garden | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 6687 | 5905 | 5/xx/66 | 1966-05-17 | England | Free Trade Hall | unverified | Review: no olof venue match on TUIT date |
| 6850 | 5359 | 10/xx/62 | 2008-10-30 | Gaslight Caf�, New York, NY | Enmax Centre | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 7832 | 1637 | xx/xx/61 | 1961-12-22 | Early Dylan (Remastered) | The Home Of Bonnie Beecher | unverified | Review: no olof venue match on TUIT date |
| 8499 | 5362 | xx/xx/62 | 1961-09-06 | Gaslight Tapes (Rare Cassette Box Set) | Gaslight Caf | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 8533 | 1643 | xx/xx/61 | 1963-08-28 | The Radio Songs 1961- 63 Vol. 2 | Lincoln Memorial | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 8558 | 5913 | xx/xx/58 | 1961-05-06 | various | Montewese Hotel | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 9026 | 1646 | xx/xx/61 | 1961-12-22 | minnesota and freewheelin sessions | The Home Of Bonnie Beecher | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 9441 | 1994 | xx/xx/86 | 1986-02-24 | Hard to Handle, (TV-movie HBO-Special) | Entertainment Centre | unverified | Review: no olof venue match on TUIT date |
| 10181 | 5928 | xx/xx/97 | 1998-02-25 | Recorded live in the US 1997-98 | Radio City Music Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 10221 | 5368 | xx/xx/66 | 1966-05-26 | Britain various | Royal Albert Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 10230 | 1644 | xx/xx/61 | 1962-08-11 | The Whitaker Tapes (a.k.a. The Telephone Tapes) | The Home Of Dave Whitaker | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 10578 | 5917 | xx/xx/61 | 1961-11-23 | various | The Home Of Eve and Mac McKenzie | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 10879 | 1614 | 5/xx/61 | 2013-06-30 | Minnesota Party Tape | The Lawn at Riverfront Park | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 11004 | 5361 | xx/xx/62 | 1963-08-17 | Broadside Ballads & Forest Hills Revisited | Forest Hills Tennis Stadium | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 11746 | 5363 | xx/xx/62 | 1962-03-11 | various radio 62-66 | BOB DYLAN | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 12068 | 5536 | xx/xx/66 | 1966-05-17 | Gelston Acetates | Free Trade Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 14987 | 5537 | xx/xx/66 | 1966-04-20 | UK Tour 1966 | Festival Hall | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 15034 | 1635 | xx/xx/61 | 1961-12-22 | Blind Boy Grunt | The Home Of Bonnie Beecher | unverified | Review: no olof venue match on TUIT date |
| 15038 | 1647 | xx/xx/61 | 1961-12-22 | various mainly Minnesota Hotel Tapes | The Home Of Bonnie Beecher | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 15296 | 5351 | 9/xx/60 | 2021-10-08 | Minneapolis, MN | 711 15th Ave SE | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 15445 | 5378 | xx/xx/86 | 1986-06-06 | Hearts Of Fire music and dialogues, various locations Wales and Tor... | Hearts Of Fire music and dialogues | compilation | Leave: multi-show compilation; TUIT files it under one date |
| 15718 | 5353 | 2/xx/62 | 1962-01-13 | Cynthia Gooding's apartment, New York City, New York | Manufacturer: Yellow Dog | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 16054 | 5915 | xx/xx/60 | 1991-11-04 | Uncover my Heart | McCaw Hall, The Northwestern University | misattribution | Leave LB; TUIT date/lb_number likely wrong (year/month differ) |
| 16355 | 5538 | xx/xx/66 | 1966-05-16 | various | Gaumont Theatre | compilation | Leave: multi-show compilation; TUIT files it under one date |

## Source type

| class | rows |
|---|---|
| agree | 4883 |
| conflict | 100 |
| conflict_broadcast | 19 |
| conflict_lb_aud_at_sbd | 9 |
| conflict_lb_wrong | 5 |
| conflict_matrix | 1 |
| conflict_no_evidence | 45 |
| conflict_tuit_wrong | 6 |
| conflict_vocab_overlap | 15 |
| tuit_fill | 453 |

### Conflicts (TODO-339 part 2)

`target` is the source type the evidence points to; blank = keep LB. Every change is a curator edit on our side (entries.source_type is curator-only); `tuit_wrong` rows are a tracker-side note.

| LB | rec | LB | TUIT | class | target | action |
|---|---|---|---|---|---|---|
| 80 | 2735 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 301 | 4852 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 448 | 3167 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 536 | 5157 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 558 | 358 | Soundboard | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 692 | 3261 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 697 | 714 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 722 | 1992 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 733 | 3044 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 816 | 4806 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 881 | 1935 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 900 | 2940 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 1070 | 3802 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 1258 | 4545 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 1259 | 6063 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 1262 | 1591 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 1608 | 4487 | ALD | Mixed | lb_aud_at_sbd | Mixed | Curator edit LB -> Mixed: SBD/AUD matrix |
| 1681 | 5048 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2316 | 2626 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2317 | 2622 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2319 | 2589 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2321 | 2842 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2322 | 2593 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2325 | 2838 | Audience | Soundboard | lb_wrong | Soundboard | Review: soundboard wording, no mic chain |
| 2339 | 2142 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2368 | 2603 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2372 | 2553 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2382 | 2618 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2405 | 2639 | Audience | Soundboard | tuit_wrong |  | Keep LB: mic chain in lineage, no soundboard wording |
| 2484 | 2616 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2558 | 4313 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 2615 | 2465 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2633 | 4428 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2832 | 3423 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 2842 | 1828 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 2847 | 1608 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 2851 | 1939 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 2860 | 2122 | Audience | Soundboard | tuit_wrong |  | Keep LB: mic chain in lineage, TUIT label wrong |
| 2867 | 1701 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 2984 | 373 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3001 | 1938 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3013 | 1698 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3109 | 4046 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3208 | 2574 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 3309 | 1971 | Soundboard | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 3404 | 831 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3435 | 4732 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 3524 | 4354 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 3525 | 1659 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3564 | 1861 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 3678 | 5957 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 4476 | 638 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 4563 | 1617 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 4746 | 1975 | Soundboard | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 5099 | 597 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 5772 | 3206 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 5888 | 1677 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 5970 | 1683 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 6170 | 4796 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 6432 | 2910 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 6627 | 1687 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 6636 | 4063 | Audience | Soundboard | lb_wrong | Soundboard | Review: soundboard wording, no mic chain |
| 6809 | 4011 | Audience | Soundboard | lb_wrong | Soundboard | Review: soundboard wording, no mic chain |
| 6884 | 2739 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 6920 | 4873 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 7123 | 3179 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 7160 | 4069 | Audience | Soundboard | tuit_wrong |  | Keep LB: mic chain in lineage, TUIT label wrong |
| 7200 | 593 | Soundboard | Mixed | lb_aud_at_sbd | Mixed | Curator edit LB -> Mixed: SBD/AUD matrix |
| 7234 | 4488 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 7732 | 3502 | Audience | Mixed | matrix | Mixed | Review: matrix wording in lineage |
| 7847 | 1615 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 7909 | 5897 | Audience | Soundboard | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 7943 | 1072 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 8058 | 4514 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 8101 | 1554 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 8519 | 3794 | Audience | Soundboard | lb_wrong | Soundboard | Review: soundboard wording, no mic chain |
| 8581 | 1682 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Review: broadcast wording in lineage |
| 8870 | 3015 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 8944 | 5522 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 9026 | 1646 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 9425 | 1660 | Audience | Mixed | vocab_overlap |  | Leave: Mixed includes the other side's source |
| 9648 | 1241 | Audience | FM/Pre-FM | tuit_wrong |  | Keep LB: mic chain in lineage, TUIT label wrong |
| 9649 | 1242 | Audience | FM/Pre-FM | tuit_wrong |  | Keep LB: mic chain in lineage, TUIT label wrong |
| 9875 | 1302 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 10247 | 3512 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 10305 | 4413 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: 'at the soundboard' is a mic position |
| 10433 | 4406 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 10706 | 5344 | Audience | FM/Pre-FM | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 10753 | 4335 | Soundboard | Audience | lb_aud_at_sbd | Audience | Curator edit LB -> Audience: mic recorded AT the soundboard |
| 11032 | 3796 | Audience | Soundboard | lb_wrong | Soundboard | Review: soundboard wording, no mic chain |
| 11086 | 150 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 11087 | 3790 | Audience | Soundboard | broadcast | FM/Pre-FM | Curator edit LB -> FM/Pre-FM: radio/TV broadcast |
| 11321 | 5000 | Audience | Soundboard | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 11734 | 1366 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 16253 | 4021 | Audience | Soundboard | tuit_wrong |  | Keep LB: mic chain in lineage, TUIT label wrong |
| 16374 | 2504 | Audience | FM/Pre-FM | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 16414 | 3682 | ALD | Audience | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 16545 | 1598 | ALD | Soundboard | vocab_overlap |  | Leave: ALD is a venue feed TUIT files as SBD/AUD; keep LB |
| 16552 | 3983 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |
| 16580 | 5189 | Soundboard | Audience | no_evidence |  | Leave: lineage carries no source evidence (advisory) |

## Venue

| class | rows |
|---|---|
| agree | 2039 |
| city_only | 2851 |
| differs | 294 |
| lb_blank | 1 |
| partial | 251 |

`city_only`/`lb_blank` are fill candidates; `differs`/`partial` need a human (location may name a different venue or a sub-room).

### Venue `differs` (first 40 of 294)

| LB | rec | LB location | TUIT venue | TUIT location |
|---|---|---|---|---|
| 10 | 4362 | US tour with Grateful Dead | Autzen Stadium | Eugene, Oregon, United States |
| 24 | 4460 | Dylan & the Dead Live, | Sullivan Stadium | Foxboro, Massachusetts, United States |
| 24 | 5922 | Dylan & the Dead Live, | Sullivan Stadium | Foxboro, Massachusetts, United States |
| 89 | 4489 | San Paola | Estadio Cicero Pompeu de Toledo | Sao Paulo, Brazil |
| 170 | 1607 | Barcelona, Spain, Palau Municipal dels Esports | Palacio de los Deportes | Barcelona, Spain |
| 221 | 5182 | Adelaide, Austrailia | Memorial Drive | Adelaide, South Australia, Australia |
| 301 | 4852 | Vancouver, British Columbia | General Motors Arena | Vancouver, BC, Canada |
| 304 | 3774 | Home Of Eve And Mac Mckenzie, NYC, McKenzie Tapes 3 & 4 | Town Hall | New York, New York, United States |
| 359 | 5201 | Freilichtbuhne, Loreley, St. Goarshausen, Germany | Freileichtbühne | Loreley, West Germany |
| 368 | 5202 | Freilichttheater, Bad Segeberg, West Germany | Freileichttheater | Bad Segeberg, West Germany |
| 370 | 5203 | Freilichttheater, Bad Segeberg, West Germany | Freileichttheater | Bad Segeberg, West Germany |
| 420 | 655 | Goteberg | Trädgårdsföreningen | Gothenburg, Sweden |
| 455 | 1955 | Sydney, Austrailia | Entertainment Centre | Sydney, New South Wales, Australia |
| 482 | 3165 | Central Point, OR | Jackson County Fairgrounds | Medford, Oregon, United States |
| 485 | 2166 | Patras, Greec | Patras Festival, Ethniko Stadio | Patras, Greece |
| 534 | 2774 | Boston, MA, Oprheum Theater | The Orpheum Theatre | Boston, Massachusetts, United States |
| 594 | 5258 | Binghampton | Broome County Veterans Memorial Arena | Binghamton, New York, United States |
| 634 | 2143 | The Bridge Benefit, Oakland, CA | Oakland Coliseum | Oakland, California, United States |
| 637 | 1820 | Perth, Western Australia | Entertainment Center | Perth, West Australia, Australia |
| 638 | 2487 | Sao Paulo | Palace Theatre | Sao Paolo, Brazil |
| 671 | 5191 | Munchen, West Germany | Olympia Stadion | Munich, West Germany |
| 693 | 2074 | Portland | Old Orchard Beach Ballpark | Old Orchard Beach, Maine, United States |
| 698 | 5187 | Goteborg, Sweden | Ullevi Stadion | Gothenburg, Sweden |
| 703 | 5371 | Hero Blues - All known versions | Chicago Stadium | Chicago, Illinois, United States |
| 749 | 3242 | St. John | Harbour Station | Saint John, NB, Canada |
| 750 | 3295 | Pittsburg | Pittsburgh, Pennsylvania Duquesne University AJ Palumbo Center | Unknown City, Unknown |
| 765 | 3305 | Boston, Massachusetts, Fleet Center | FleetCenter | Boston, MA, United States |
| 817 | 4366 | Sydney | State Theatre | New South Wales, Australia |
| 853 | 1704 | BBC Studios, London England | BOB DYLAN | London, Transfer from Tape |
| 891 | 4933 | Roskilde Festival, Roskilde, Denmark | Dyrskuepladsen | Roskilde, Denmark |
| 966 | 5366 | Singing with the Crow bootleg | RFK Stadium | Washington, DC, United States |
| 1041 | 3806 | Maple Leaf Garden, Toronto | BOB DYLAN | Maple Leaf Gardens, Toronto |
| 1047 | 4367 | Sydney | State Theatre | New South Wales, Australia |
| 1095 | 3859 | Pittsburg | Civic Arena | Pittsburgh, Pennsylvania, United States |
| 1095 | 5108 | Pittsburg | Civic Arena | Pittsburgh, Pennsylvania, United States |
| 1138 | 5385 | MASTERS (BobDylan.com) | The Theater, Madison Square Garden | New York, New York, United States |
| 1146 | 3893 | Brussels, Belgium, Forest National | Vorst Nationaal | Brussels, Belgium |
| 1146 | 4826 | Brussels, Belgium, Forest National | Vorst Nationaal | Brussels, Belgium |
| 1174 | 3952 | Darien Lake Performing Arts Center, Darien,N.Y | Darien Lakes PAC | Darien Center, New York, United States |
| 1297 | 5137 | Meadow Brook | Meadowbrook Music Theatre, Oakland University | Rochester Hills, Michigan, United States |

## Lineage

| class | rows |
|---|---|
| both | 2974 |
| neither | 1 |
| tuit_only | 2461 |

## Setlist

| class | rows |
|---|---|
| both | 4139 |
| lb_only | 243 |
| neither | 79 |
| tuit_only | 975 |

## Fill plan (`--fill`)

Only LBs whose every TUIT recording agrees on the full date; only fields empty on our side; only when all TUIT recordings for the LB offer the same value.

| class | rows |
|---|---|
| setlist | 917 |
| source_chain | 2335 |
| source_type | 434 |
| venue | 2810 |

### `source_type` (first 40 of 434)

| LB | rec | value |
|---|---|---|
| 4 | 3087 | Audience |
| 306 | 3773 | Audience |
| 510 | 1756 | Audience |
| 853 | 1704 | FM/Pre-FM |
| 1906 | 4715 | Audience |
| 2408 | 5513 | Audience |
| 2422 | 1665 | Audience |
| 2546 | 3980 | FM/Pre-FM |
| 2617 | 1714 | FM/Pre-FM |
| 2789 | 6062 | Audience |
| 3222 | 1592 | Soundboard |
| 3227 | 1707 | FM/Pre-FM |
| 3236 | 1706 | FM/Pre-FM |
| 3241 | 1705,5333 | FM/Pre-FM |
| 3556 | 1666 | Audience |
| 3672 | 5925 | Audience |
| 3867 | 5872 | Audience |
| 3869 | 5873 | Audience |
| 3872 | 5871 | Audience |
| 3895 | 3800 | FM/Pre-FM |
| 4124 | 1628 | Audience |
| 4430 | 1629 | Audience |
| 4507 | 5918 | Audience |
| 4510 | 5866 | Audience |
| 4511 | 5919 | Audience |
| 4512 | 5920 | Audience |
| 4555 | 5870 | Audience |
| 4624 | 5867 | Audience |
| 5329 | 5539 | Audience |
| 5330 | 5857 | Audience |
| 5339 | 5856 | Audience |
| 5360 | 5855 | Audience |
| 5550 | 1662 | Audience |
| 5551 | 4007 | Audience |
| 5662 | 5858 | Audience |
| 5726 | 5511 | Audience |
| 5751 | 5549 | Audience |
| 5753 | 5510 | Audience |
| 5758 | 6075 | Audience |
| 5799 | 5578 | Audience |

### `source_chain` (first 40 of 2335)

| LB | rec | value |
|---|---|---|
| 4 | 3087 | LB-4 |
| 38 | 3117 | LB-38 |
| 39 | 5306 | LB-39 |
| 46 | 3082 | audio disks (likely low generational source) > (dBpowerAMP set to c... |
| 50 | 617 | Crystal Cat |
| 61 | 1799 | Master > CDR > EAC > FLAC |
| 66 | 3237 | matt engle |
| 68 | 1553 | Crystal Cat |
| 79 | 5067 | LB-79 |
| 80 | 2735 | My low gen tape > Tascam 102 > Cool Edit Pro > CD |
| 85 | 4847 | LB-85 |
| 86 | 676 | LB-86 |
| 89 | 4489 | unknown |
| 94 | 4788 | shn > wav > plexwriter > cdr > ultraplex > eac > wav > flac; d1 was... |
| 103 | 248 | LB-103 |
| 105 | 5037 | LB-105 |
| 110 | 5234 | LB-110 |
| 111 | 1849 | LB-111 |
| 120 | 4048 | LB-120 |
| 121 | 426 | Sony D7, micros Sennheiser. Master Dat |
| 124 | 2836 | LB-124 |
| 130 | 2786 | LB-130 |
| 132 | 3014 | LB-132 |
| 133 | 2628 | LB-133 |
| 138 | 2350 | LB-138 |
| 140 | 2347 | trade cdrs > eac > flac |
| 142 | 2912 | LB-142 |
| 146 | 5295 | LB-146 |
| 147 | 2151 | LB-147 |
| 156 | 2005 | Master > CDr(x) > EAC(secure) > FLAC |
| 160 | 5236 | LB-160 |
| 165 | 5061 | LB-165 |
| 170 | 1607 | dylantree data vine cd |
| 175 | 4786 | LB-175 |
| 178 | 1850,5243 | shn files derived from an off-master copy |
| 179 | 4787 | LB-179 |
| 208 | 2276 | LB-208 |
| 210 | 1727 | Low Generation TDK SA90 > Akai GX95 11 > Soundforge PRO 10c > FLAC ... |
| 216 | 2262 | LB-216 |
| 217 | 4061 | LB-217 |

### `setlist` (first 40 of 917)

| LB | rec | value |
|---|---|---|
| 17 | 4071 | 1. Crash On The Levee 2. Lay Lady Lay 3. All Along The Watchtower 4... |
| 32 | 3110 | 1. Duncan And Brady 2. My Back Pages 3. Desolation Row 4. Fourth Ti... |
| 39 | 5306 | 1. Hero Blues 2. Lay Lady Lay 3. Tough Mama 4. The Night They Drove... |
| 50 | 617 | 1. Duncan And Brady 2. To Ramona 3. Desolation Row 4. Tomorrow Is A... |
| 79 | 5067 | 1. Most Likely You Go Your Way (And I'll Go Mine) 2. I'll Remember ... |
| 80 | 2735 | 1. Drifter's Escape 2. Pledging My Time 3. All Along The Watchtower... |
| 94 | 4788 | 1. Hallelujah, I'm Ready To Go 2. The Times They Are A-Changin' 3. ... |
| 103 | 248 | 1. Hey, Good Lookin' 2. Subterranean Homesick Blues 3. My Back Page... |
| 105 | 5037 | 1. To Be Alone With You 2. Joey 3. All Along The Watchtower 4. I'll... |
| 110 | 5234 | 1. Gotta Serve Somebody 2. I Believe In You 3. When You Gonna Wake ... |
| 111 | 1849 | 1. Gotta Serve Somebody 2. I Believe In You 3. When You Gonna Wake ... |
| 121 | 426 | 1. Drifter's Escape 2. It Takes A Lot To Laugh, It Takes A Train To... |
| 130 | 2786 | 1. Drifter's Escape 2. If Not For You 3. All Along The Watchtower 4... |
| 133 | 2628 | 1. You're Gonna Quit Me 2. Stuck Inside Of Mobile With The Memphis ... |
| 138 | 2350 | 1. Marine Hymn 2. Masters Of War 3. Tomorrow Is A Long Time 4. Man ... |
| 140 | 2347 | 1. Most Likely You Go Your Way (And I'll Go Mine) 2. I Believe In Y... |
| 142 | 2912 | 1. Absolutely Sweet Marie 2. It Takes A Lot To Laugh, It Takes A Tr... |
| 146 | 5295 | 1. When I Paint My Masterpiece 2. It Ain't Me, Babe 3. The Lonesome... |
| 147 | 2151 | 1. Subterranean Homesick Blues 2. Congratulations 3. Stuck Inside O... |
| 156 | 2005 | 1. Forever Young 2. Shelter From The Storm 3. Seeing The Real You A... |
| 160 | 5236 | 1. Gotta Serve Somebody 2. I Believe In You 3. When You Gonna Wake ... |
| 165 | 5061 | 1. Absolutely Sweet Marie 2. Tomorrow Is A Long Time 3. I Want You ... |
| 178 | 1850,5243 | 1. Gotta Serve Somebody 2. I Believe In You 3. When You Gonna Wake ... |
| 208 | 2276 | 1. Subterranean Homesick Blues 2. Lay Lady Lay 3. All Along The Wat... |
| 216 | 2262 | 1. Most Likely You Go Your Way (And I'll Go Mine) 2. Masters Of War... |
| 217 | 4061 | 1. Gotta Serve Somebody 2. I Believe In You 3. Like A Rolling Stone... |
| 227 | 1822 | 1. A Hard Rain's A-Gonna Fall 2. Love Her With A Feeling 3. Baby St... |
| 244 | 230 | 1. Stuck Inside Of Mobile With The Memphis Blues Again 2. Masters O... |
| 255 | 2046 | 1. Subterranean Homesick Blues 2. Absolutely Sweet Marie 3. Masters... |
| 307 | 4393 | 1. Jokerman 2. The Man In Me 3. All Along The Watchtower 4. I Don't... |
| 352 | 5253 | 1. My Back Pages 2. She's Love Crazy 3. Mr. Tambourine Man 4. Shelt... |
| 365 | 2708 | 1. Crash On The Levee 2. Lay Lady Lay 3. All Along The Watchtower 4... |
| 369 | 5269 | 1. A Hard Rain's A-Gonna Fall 2. Love Her With A Feeling 3. Baby St... |
| 379 | 3207 | 1. Hallelujah, I'm Ready To Go 2. Mr. Tambourine Man 3. It's Alrigh... |
| 383 | 5301 | 1. Most Likely You Go Your Way (And I'll Go Mine) 2. Lay Lady Lay 3... |
| 401 | 5028 | 1. Rainy Day Women # 12 & 35 2. Sally Sue Brown 3. Union Sundown 4.... |
| 402 | 4931 | 1. Crash On The Levee 2. Tonight I'll Be Staying Here With You 3. A... |
| 403 | 282 | 1. Maggie's Farm 2. One Irish Rover 3. Rainy Day Women # 12 & 35 4.... |
| 411 | 1712 | 1. She Belongs To Me 2. To Ramona 3. Gates Of Eden 4. It's All Over... |
| 418 | 2380 | 1. My Head's In Mississippi 2. Seeing The Real You At Last 3. I Bel... |

### `venue` (first 40 of 2810)

| LB | rec | value |
|---|---|---|
| 4 | 3087 | Pine Knob Music Theatre |
| 38 | 3117 | Sun Palace |
| 61 | 1799 | Expo Hall - Afternoon, Municipal Auditorium |
| 64 | 3023 | Silvretta Ski- und Funsportarena, Idalp |
| 66 | 3237 | Fort Stage, Fort Adams State Park |
| 68 | 1553 | Manchester Evening News Arena |
| 79 | 5067 | O'Keefe Centre For The Performing Arts |
| 86 | 676 | Metro Centre |
| 94 | 4788 | Forum |
| 103 | 248 | Coleman Coliseum |
| 105 | 5037 | University Hall, University Of Virginia |
| 124 | 2836 | The Sports Complex |
| 132 | 3014 | Velodromo Anoeta |
| 133 | 2628 | Riverfest, Minnesota State Fair |
| 138 | 2350 | Mesa Amphitheater |
| 140 | 2347 | Riverpark Amphitheater |
| 147 | 2151 | Hall 4, Scottish Exhibition And Conference Centre |
| 153 | 601 | Sala Ataulfo Argenta, Palacio de Festivales |
| 156 | 2005 | St. Jakobshalle |
| 165 | 5061 | Riverfront Amphitheater |
| 175 | 4786 | Stadionsporthalle |
| 208 | 2276 | Theatre de Grand Rex |
| 210 | 1727 | BOB DYLAN |
| 216 | 2262 | Chrysler Hall |
| 232 | 1738 | The Omni |
| 244 | 230 | Festival Hall, Tampa Bay Performing Arts Center |
| 255 | 2046 | Concord Pavilion |
| 257 | 4783 | Hallenstadion |
| 276 | 1983 | Sandstone Amphitheater |
| 280 | 675 | Manchester Evening News Arena |
| 307 | 4393 | Rochester Auditorium Center |
| 308 | 679 | Joel Coliseum |
| 325 | 5296 | Civic Center |
| 328 | 5213 | Stade Municipal des Minimes |
| 376 | 1956 | Entertainment Centre |
| 403 | 282 | Morris Civic Auditorium |
| 408 | 1777 | Harvard Square Theater |
| 411 | 1712 | Arie Crown Theatre |
| 412 | 4815 | Nygaardsparken |
| 417 | 4813 | Borgholms Slott, (Borgholm Castle) |
