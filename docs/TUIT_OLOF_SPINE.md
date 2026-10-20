# TUIT show spine × olof_events (TODO-338 parts 1–2)

Read-only analysis, 2026-10-20. Tool: `tools/tuit_olof_spine.py` (tests:
`tests/test_tuit_olof_spine.py`). Re-run with
`.venv/bin/python3 tools/tuit_olof_spine.py` — it rewrites only the generated block below.

## Part 1 — date residue (summary)

The TODO's 94 / 216 are stale. BUG-371/372 (2026-10-14) took them to 56 / 203; today the
residue is **17 TUIT rows with no olof concert** and **199 olof concert dates with no TUIT
row**. Every row is classified in the generated tables; no class needs a date change in
`entries`.

| side | class | n | meaning |
|---|---|---|---|
| TUIT-only | corroborated | 6 | setlist.fm + bobdylan.com have it → **olof gap** (2 are known olof parser gaps: DSN36360, DSN40330) |
| TUIT-only | circa | 3 | 1961 home/club tapes TUIT pins to the 1st of a month |
| TUIT-only | olof_nonconcert | 3 | olof has the date typed `other` (Corpus Christi 1976, Perth 1986 ×2) |
| TUIT-only | multi_night | 2 | olof has the neighbouring night of the same run, not this one |
| TUIT-only | unverified / non_show | 3 | Dobell's 1963, two TV/awards appearances |
| olof-only | non_show | 95 | studios, TV/radio, homes, hotel rooms, rehearsal halls (Rundown Studios alone is ~40) |
| olof-only | corroborated | 42 | bobdylan.com has it → **TUIT calendar gap** (Bangladesh MSG 1971, Astrodome 1976, Live Aid 1985…) |
| olof-only | multi_night | 16 | TUIT has the other night(s) at that venue but not this one |
| olof-only | corroborated_sfm | 15 | setlist.fm only — weaker |
| olof-only | unverified | 28 | guest spots, private events, rehearsals olof types `concert` |
| olof-only | after_crawl | 3 | Oct 2026 shows after the 2026-09-07 TUIT crawl |

No `date_offset` rows: nowhere does one corpus put a show on a day the other has nothing at
that venue. **Neither corpus has date typos in the residue** — the gaps are coverage, not
error. Actionable leftovers: 6 olof gaps (report to Olof / parser fixes) and ~58 real shows
missing from TUIT's calendar (42 + 16).

## Part 2 — venue join key

Ground truth is free: on 3,986 shared dates each corpus names one venue, and same date ⇒ same
venue. Each candidate key was scored by how many of those pairs it links *without looking
at the date*.

| key | links | conflicting-evidence links | TUIT venues left unlinked |
|---|---|---|---|
| `exact` normalised name + city | 69.5% | 13 (all true — strings swap between eras) | 934 / 2,714 |
| `fuzzy` same city + token containment / ratio ≥ 0.85 | 93.2% | 345 | 202 |
| `geo25` fuzzy name + city centroids ≤ 25 km | 94.1% | 358 | 176 |
| `crosswalk` TUIT venue → olof venue learned from other shared dates (leave-one-out) | 44.8% | 136 | 19 |
| **`geo25` + crosswalk** | **95.0%** | 384 | **10** |

- **Precision.** The conflicting-evidence count is an upper bound: it flags a link whose
  dated evidence names other venues on both sides, which also catches sponsor renames
  (Spectrum → First Union → Wachovia Spectrum) and `exact`'s 13 true matches. Hand-labelling
  the seeded 40-link sample of what `geo25` adds over `exact`: **38/40 clearly right, 2
  room/campus-level** (#14 Halle D ↔ Stadthalle, #36 UMass Mullins Center ↔ "University of
  Massachusetts"), 0 clearly wrong. The real false-link pattern is *rooms inside one
  building*: Carnegie Chapter Hall ↔ Carnegie Hall, Gerde's basement ↔ Gerde's.
- **Coordinates buy little.** 10/25/50 km add only 32/36/40 date pairs over `fuzzy` (St.
  Kilda ↔ Melbourne, Greenwood Village ↔ Denver, Hollywood ↔ Los Angeles); the rest of the
  misses are name divergence (Point Depot ↔ Point Theatre, Ahoy ↔ Sportpaleis) and
  language/spelling (Genua ↔ Genoa, Gøteborg ↔ Gothenburg). 25 km is the knee.
- **Crosswalk alone is weak** (most TUIT venues have one or two dates, so leave-one-out has
  nothing to learn from) but it is the only key that catches renames, so it is the right
  fallback.
- **TUIT strings are noisier than they look.** Session suffixes (`· Evening`), glued
  concatenations (`Casino RamaEntertainment Centre`, `…CountyUMBC Event Center`), and on a
  handful of rows lineage text or a song title in the venue field (`m-audio delta
  audiophile 2496 -> Wavelab…`, `You Win Again`). 213 of 4,036 TUIT rows don't resolve to a
  register venue. One olof row has stripped non-ASCII (`Universit tspark`, `Schw bisch Gm nd`).
- **Which side is longer** on the 3,986 shared dates: equal 2,838 · TUIT longer 699 (17.5%)
  · olof longer 117 · different 332.

## Recommendation

1. **Join key = shared date first, `geo25` name rule second, no transitive merge.** Build a
   pairwise `venue_xref` (TUIT register venue ↔ olof `(venue_norm, city_norm)`, `method` =
   `date` | `name`, `n_dates`) — every shared date contributes its pair directly (that is
   the crosswalk in-sample, 100% of the 3,986), and `geo25` covers TUIT venues with no
   shared date. Pairwise only: a union-find closure would chain Carnegie Chapter Hall into
   Carnegie Hall through one bad link. Reuse `venue_gazetteer._norm_city` for the key so it
   lines up with `venue_geocoded`.
2. **Keep `olof_events.venue` as the dossier's identity/grouping string.** Grouping is
   per-date, so the longer TUIT string changes nothing there, and TUIT's text is the
   noisier of the two. Show the TUIT string as a secondary line only where it is a strict
   superset (the 699 `tuit_longer` dates — "Lisner Auditorium, George Washington
   University").

**The one question for tj:** build `venue_xref` as above (date pairs + `geo25`, pairwise,
olof string stays primary in the dossier with TUIT's longer string as a secondary line) —
yes, or do you want TUIT's longer string to *replace* olof's in the dossier header?

---

<!-- GENERATED:tuit_olof_spine START -->
_Generated 2026-10-20 06:59 by `tools/tuit_olof_spine.py` — re-run to refresh._

TUIT: 4,036 show rows on 4,011 dates (223 rows don't resolve to a register venue); last crawl 2026-09-07.

### Part 1a — TUIT rows with no olof concert

| class | rows |
|---|---|
| corroborated | 6 |
| circa | 3 |
| olof_nonconcert | 3 |
| unverified | 2 |
| multi_night | 2 |
| non_show | 1 |

| date | TUIT venue | location | circ | class | evidence | 2026-10-14 note |
|---|---|---|---|---|---|---|
| 1961-02-01 | The Home of Bob and Sid Gleason | East Orange, New Jersey, United States | 0 | circa | TUIT pins a 1960s day olof can't |  |
| 1961-09-01 | Gaslight Café | New York, New York, United States | 0 | circa | TUIT pins a 1960s day olof can't |  |
| 1961-10-01 | Folklore Center | New York, New York, United States | 0 | circa | TUIT pins a 1960s day olof can't |  |
| 1963-01-15 | Dobell's Jazz Record Shop | London, England | 0 | unverified |  |  |
| 1963-04-18 | The Home Of Eve and Mac MacKenzie | New York, New York, United States | 0 | multi_night | olof has 1963-04-19 at The Home Of Eve and Mac MacKenzie too — olof lacks this night of the run |  |
| 1965-12-04 | Berkeley Community Theatre | Berkeley, California, United States | 0 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap |  |
| 1966-05-12 | Odeon Theatre | Birmingham, England | 0 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap |  |
| 1976-05-10 | Memorial Coliseum | Corpus Christi, Texas, United States | 0 | olof_nonconcert | olof other: Memorial Coliseum, Corpus Christi | olof files as non-concert |
| 1986-02-17 | Perth Entertainment Center | Perth, West Australia, Australia | 0 | olof_nonconcert | olof other: Perth Entertainment Center, Perth | olof files as non-concert (Perth) |
| 1986-02-18 | Perth Entertainment Center | Perth, West Australia, Australia | 0 | olof_nonconcert | olof other: Perth Entertainment Center, Perth | olof files as non-concert (Perth) |
| 1988-08-18 | Portland Civic Auditorium | Portland, Oregon, USA | 1 | multi_night | olof has 1988-08-19 at Civic Auditorium too — olof lacks this night of the run | real show olof's pages lack or don't parse |
| 1996-04-18 | The Strand | Providence, USA | 1 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap | real show olof's pages lack or don't parse |
| 1997-05-21 | Beverly Hilton Hotel International Room | Beverly Hills, California, United States | 0 | unverified |  | TV/awards appearance |
| 2004-10-18 | University Of California Davis, The Pavilion | Davis, California, United States | 1 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap | real show olof's pages lack or don't parse |
| 2012-01-12 | Critics' Choice Movie Awards, Hollywood Palladium | Hollywood, CA, USA | 1 | non_show | TV/awards/studio venue | TV/awards appearance |
| 2014-11-25 | DAR Constitution Hall | Washington, D.C., United States | 1 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap | DSN36360 header has no number line — olof parser gap |
| 2019-11-12 | University of Maryland Baltimore CountyUMBC Event Center | Baltimore, Maryland, United States | 0 | corroborated | setlist.fm+bobdylan.com lists the date — olof gap | DSN40330 has no bookmark — olof parser gap |

### Part 1b — olof concert dates with no TUIT row

| class | dates |
|---|---|
| non_show | 95 |
| corroborated | 42 |
| unverified | 28 |
| multi_night | 16 |
| corroborated_sfm | 15 |
| after_crawl | 3 |

| date | olof venue | city | country | DSN | class | evidence |
|---|---|---|---|---|---|---|
| 1956-12-24 | Terlinde Music | St. Paul |  | 2 | corroborated_sfm | setlist.fm only — weaker |
| 1959-01-10 | Unidentified venue | Hibbing |  | 4 | non_show | studio/TV/radio/home/rehearsal venue |
| 1963-03-03 | Westinghouse Studios | New York City |  | 398 | non_show | studio/TV/radio/home/rehearsal venue |
| 1963-04-26 | WFMT-Radio Studio | Chicago |  | 460 | non_show | studio/TV/radio/home/rehearsal venue |
| 1963-07-30 | WNEW TV Studios | New York City |  | 540 | non_show | studio/TV/radio/home/rehearsal venue |
| 1964-02-01 | CBC TV Studios | Toronto | Canada | 640 | non_show | studio/TV/radio/home/rehearsal venue |
| 1964-02-22 | Berkeley Community Theatre | Berkeley |  | 647 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1964-02-25 | NBC Studios | Los Angeles |  | 650 | non_show | studio/TV/radio/home/rehearsal venue |
| 1964-05-14 | Didsbury Studios | Manchester | England | 693 | non_show | studio/TV/radio/home/rehearsal venue |
| 1964-09-19 | High School | Ann Arbor |  | 743 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1964-11-01 | Kleinhans Music Hall | Buffalo |  | 751 | corroborated_sfm | setlist.fm only — weaker |
| 1964-11-13 | Massey Hall | Toronto | Canada | 755 | corroborated_sfm | setlist.fm only — weaker |
| 1964-11-21 | Oriental Theatre | Milwaukee |  | 759 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1964-12-01 | College Gymnasium | San Mateo |  | 777 | corroborated_sfm | setlist.fm only — weaker |
| 1965-02-17 | WABC TV Studios | New York City |  | 810 | non_show | studio/TV/radio/home/rehearsal venue |
| 1965-04-26 | Arrival Area | London | England | 850 | non_show | studio/TV/radio/home/rehearsal venue |
| 1965-05-12 | Levy's Recording Studio | London England |  | 1010 | non_show | studio/TV/radio/home/rehearsal venue |
| 1965-06-01 | BBC Studios | London England |  | 1020 | non_show | studio/TV/radio/home/rehearsal venue |
| 1968-01-20 | Carnegie Hall | New York City |  | 1660 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1970-05-17 | The Home Of Thomas B. Allen | Carmel |  | 1820 | non_show | studio/TV/radio/home/rehearsal venue |
| 1971-08-01 | Madison Square Garden | New York City |  | 1930 | corroborated | bobdylan.com — TUIT calendar gap |
| 1971-09-24 | Studio B | New York City |  | 1960 | non_show | studio/TV/radio/home/rehearsal venue |
| 1971-10-30 | PBS-TV Studios | New York City |  | 1970 | non_show | studio/TV/radio/home/rehearsal venue |
| 1971-10-31 | Unidentified Location | New York City |  | 1975 | unverified | no other source has the date |
| 1971-11-04 | Columbia Studio B | New York City |  | 1980 | non_show | studio/TV/radio/home/rehearsal venue |
| 1972-01-01 | New York Academy Of Music | New York City |  | 2025 | unverified | no other source has the date |
| 1972-09-09 | The Bitter End | New York City |  | 2055 | unverified | no other source has the date |
| 1974-01-10 | Maple Leaf Gardens | Toronto | Canada | 2290 | multi_night | TUIT has 1974-01-09 at Maple Leaf Gardens too — TUIT lacks this night of the run |
| 1975-03-23 | Kezar Stadium | San Francisco |  | 2780 | unverified | no other source has the date |
| 1975-07-03 | Other End | New York City |  | 2830 | unverified | no other source has the date |
| 1975-09-10 | WTTW-TV Studios | Chicago |  | 2880 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-10-19 | Studio Instrumental Rentals | New York City |  | 2882 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-10-21 | Studio Instrumental Rentals | New York City |  | 2884 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-10-24 | Gerde's Folk City | New York City |  | 2885 | unverified | no other source has the date |
| 1975-10-28 | Mahjong Parlor | Falmouth |  | 2917 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-10-29 | Seacrest Motel | Falmouth |  | 2918 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-11-03 | Jack Kerouac's grave | Lowell |  | 2940 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-11-16 | Tuscarora Indian Reservation, New York | Tuscarora Indian Reservation |  | 3055 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-11-23 | Unidentified location | Unidentified location |  | 3125 | unverified | no other source has the date |
| 1975-11-25 | A Gas Station | Fenway |  | 3140 | non_show | studio/TV/radio/home/rehearsal venue |
| 1975-12-05 | A Hotel Room | Montreal | Canada | 3210 | non_show | studio/TV/radio/home/rehearsal venue |
| 1976-01-22 | Instrumental Rentals Studio | Los Angeles |  | 3240 | non_show | studio/TV/radio/home/rehearsal venue |
| 1976-01-23 | Instrumental Rentals Studio | Los Angeles |  | 3245 | non_show | studio/TV/radio/home/rehearsal venue |
| 1976-01-25 | Houston Astrodrome | Houston |  | 3250 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1976-01-27 | Municipal Auditorium | Austin |  | 3260 | unverified | no other source has the date |
| 1976-03-30 | Shangri-La Studios | Malibu |  | 3265 | non_show | studio/TV/radio/home/rehearsal venue |
| 1976-04-15 | Belleview Biltmore Hotel | Clearwater |  | 3280 | multi_night | TUIT has 1976-04-22 at Starlight Ballroom - Afternoon, Belleview Biltmore Hotel too — TUIT lacks this night of the run |
| 1976-04-17 | Belleview Biltmore Hotel | Clearwater |  | 3283 | multi_night | TUIT has 1976-04-22 at Starlight Ballroom - Afternoon, Belleview Biltmore Hotel too — TUIT lacks this night of the run |
| 1976-11-25 | Winterland | San Francisco |  | 3520 | unverified | no other source has the date |
| 1977-12-26 | Rundown Studios | Santa Monica |  | 3557 | non_show | studio/TV/radio/home/rehearsal venue |
| 1977-12-30 | Rundown Studios | Santa Monica |  | 3560 | non_show | studio/TV/radio/home/rehearsal venue |
| 1978-01-27 | Rundown Studios | Santa Monica |  | 3600 | non_show | studio/TV/radio/home/rehearsal venue |
| 1978-01-30 | Rundown Studios | Santa Monica |  | 3610 | non_show | studio/TV/radio/home/rehearsal venue |
| 1978-02-01 | Rundown Studios | Santa Monica |  | 3620 | non_show | studio/TV/radio/home/rehearsal venue |
| 1978-09-27 | Nassau County Coliseum | Uniondale |  | 4420 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1979-09-25 | Rundown Studios | Santa Monica |  | 5040 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-09-26 | Rundown Studios | Santa Monica |  | 5041 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-09-28 | Rundown Studios | Santa Monica |  | 5042 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-02 | Rundown Studios | Santa Monica |  | 5046 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-08 | Rundown Studios | Santa Monica |  | 5052 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-09 | Rundown Studios | Santa Monica |  | 5053 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-10 | Rundown Studios | Santa Monica |  | 5054 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-11 | Rundown Studios | Santa Monica |  | 5055 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-12 | Rundown Studios | Santa Monica |  | 5056 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-20 | NBC Studios | New York City |  | 5060 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-23 | Rundown Studios | Santa Monica |  | 5071 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-24 | Rundown Studios | Santa Monica |  | 5072 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-25 | Rundown Studios | Santa Monica |  | 5073 | non_show | studio/TV/radio/home/rehearsal venue |
| 1979-10-29 | Rundown Studios | Santa Monica |  | 5077 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-01-12 | Paramount Theatre | Portland |  | 5348 | multi_night | TUIT has 1980-01-16 at Paramount Theatre too — TUIT lacks this night of the run |
| 1980-01-15 | Paramount Northwest Theatre | Seattle |  | 5365 | multi_night | TUIT has 1980-01-14 at Paramount Northwest Theatre too — TUIT lacks this night of the run |
| 1980-02-27 | Shrine Auditorium | Los Angeles |  | 5560 | corroborated_sfm | setlist.fm only — weaker |
| 1980-09-18 | Rundown Studios | Santa Monica |  | 5851 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-09-19 | Rundown Studios | Santa Monica |  | 5852 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-09-23 | Rundown Studios | Santa Monica |  | 5853 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-09-24 | Rundown Studios | Santa Monica |  | 5854 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-09-26 | Rundown Studios | Santa Monica |  | 5855 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-09-30 | Rundown Studios | Santa Monica |  | 5856 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-01 | Rundown Studios | Santa Monica |  | 5857 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-03 | Rundown Studios | Santa Monica |  | 5858 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-08 | Rundown Studios | Santa Monica |  | 5859 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-09 | Rundown Studios | Santa Monica |  | 5860 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-10 | Rundown Studios | Santa Monica |  | 5861 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-14 | Rundown Studios | Santa Monica |  | 5862 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-15 | Rundown Studios | Santa Monica |  | 5863 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-16 | Rundown Studios | Santa Monica |  | 5864 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-22 | Rundown Studios | Santa Monica |  | 5865 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-27 | Rundown Studios | Santa Monica |  | 5866 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-28 | Rundown Studios | Santa Monica |  | 5867 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-29 | Rundown Studios | Santa Monica |  | 5868 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-30 | Rundown Studios | Santa Monica |  | 5869 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-10-31 | Rundown Studios | Santa Monica |  | 5870 | non_show | studio/TV/radio/home/rehearsal venue |
| 1980-11-22 | Fox Warfield Theatre | San Francisco |  | 6060 | multi_night | TUIT has 1980-11-21 at Fox Warfield Theatre too — TUIT lacks this night of the run |
| 1981-07-10 | Drammenshallen | Drammen | Norway | 6420 | multi_night | TUIT has 1981-07-09 at Drammenshallen too — TUIT lacks this night of the run |
| 1982-06-06 | Rose Bowl | Pasadena |  | 6910 | unverified | no other source has the date |
| 1983-02-16 | Lone Star Cafe | New York City |  | 6920 | unverified | no other source has the date |
| 1984-03-21 | The Home Of Bob Dylan | Malibu |  | 6975 | non_show | studio/TV/radio/home/rehearsal venue |
| 1984-03-22 | NBC Studios | New York City |  | 6980 | non_show | studio/TV/radio/home/rehearsal venue |
| 1984-06-28 | Minestadio del F.C. Barcelona | Barcelona | Spain | 7250 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1984-07-03 | Grenoble Alpexpo | Grenoble | France | 7280 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1985-04-17 | Cherokee Studio | Los Angeles |  | 7445 | non_show | studio/TV/radio/home/rehearsal venue |
| 1985-06-12 | Cherokee Studio | Los Angeles |  | 7460 | non_show | studio/TV/radio/home/rehearsal venue |
| 1985-06-16 | Oceanway Studios | Los Angeles |  | 7462 | non_show | studio/TV/radio/home/rehearsal venue |
| 1985-07-12 | The Home Of Ron Wood | New York City |  | 7475 | non_show | studio/TV/radio/home/rehearsal venue |
| 1985-07-13 | John F. Kennedy Stadium | Philadelphia |  | 7480 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1985-08-22 | Gymnasium Of First Methodist Church | Los Angeles |  | 7500 | unverified | no other source has the date |
| 1985-09-19 | Universal Studios | Los Angeles |  | 7520 | non_show | studio/TV/radio/home/rehearsal venue |
| 1985-09-21 | Memorial Stadium | Champaign |  | 7530 | unverified | no other source has the date |
| 1985-09-22 | Memorial Stadium | Champaign |  | 7540 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1985-10-31 | Cherokee Studio | Los Angeles |  | 7570 | non_show | studio/TV/radio/home/rehearsal venue |
| 1986-01-20 | John F. Kennedy Performing Arts Center | Washington |  | 7630 | corroborated_sfm | setlist.fm only — weaker |
| 1986-02-10 | Entertainment Centre | Sydney | Australia | 7710 | multi_night | TUIT has 1986-02-11 at Entertainment Centre too — TUIT lacks this night of the run |
| 1986-06-06 | The Forum | Los Angeles |  | 7980 | unverified | no other source has the date |
| 1986-07-17 | Madison Square Garden | New York City |  | 8280 | multi_night | TUIT has 1986-07-16 at Madison Square Garden too — TUIT lacks this night of the run |
| 1986-09-09 | Colston Hall | Bristol | England | 8480 | unverified | no other source has the date |
| 1986-09-20 | Colston Hall, | Bristol | England | 8500 | unverified | no other source has the date |
| 1986-10-10 | Canadian General Electric Warehouse | Toronto | Canada | 8520 | non_show | studio/TV/radio/home/rehearsal venue |
| 1987-02-19 | Palomino | Los Angeles |  | 8560 | unverified | no other source has the date |
| 1987-03-11 | Brooklyn Academy Of Music | New York City |  | 8590 | corroborated_sfm | setlist.fm only — weaker |
| 1987-04-20 | Sports Arena | Los Angeles |  | 8600 | unverified | no other source has the date |
| 1987-10-14 | Wembley Arena | London | England | 8960 | multi_night | TUIT has 1987-10-15 at Wembley Arena too — TUIT lacks this night of the run |
| 1987-11-22 | Studio Instrumental Rentals | New York City |  | 9005 | non_show | studio/TV/radio/home/rehearsal venue |
| 1988-01-20 | The Grand Ballroom | New York City |  | 9020 | corroborated_sfm | setlist.fm only — weaker |
| 1988-05-29 | Lone Star Café | New York City |  | 9070 | unverified | no other source has the date |
| 1988-08-03 | Greek Theatre | Los Angeles |  | 9460 | multi_night | TUIT has 1988-08-02 at Greek Theatre, Hollywood too — TUIT lacks this night of the run |
| 1989-02-12 | The Forum | Los Angeles |  | 9830 | unverified | no other source has the date |
| 1989-11-02 | State Theatre | Cleveland |  | 10760 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1989-11-20 | Belmont Hall Studio | Bloomington |  | 10853 | non_show | studio/TV/radio/home/rehearsal venue |
| 1990-01-06 | Oceanway Studios | Los Angeles |  | 10855 | non_show | studio/TV/radio/home/rehearsal venue |
| 1990-02-24 | Universal Amphitheater | Los Angeles |  | 11010 | unverified | no other source has the date |
| 1990-03-01 | The Forum | Los Angeles |  | 11020 | unverified | no other source has the date |
| 1990-03-16 | Culver City Studios | Los Angeles |  | 11030 | non_show | studio/TV/radio/home/rehearsal venue |
| 1990-11-04 | The Fox Theater | St. Louis |  | 11720 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1990-11-13 | University Of Dayton Arena | Dayton |  | 11780 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1991-04-30 | The Johnny Mercer Theater | Savannah |  | 12115 | corroborated_sfm | setlist.fm only — weaker |
| 1991-06-10 | Olympic Stadium | Ljubljana | Yugoslavia | 12240 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1991-06-11 | Zadjan Stadium | Belgrade | Yugoslavia | 12250 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1991-08-12 | Cirilindas Municipal | Montevideo |  | 12570 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1991-09-15 | KCOP TV Studios | Los Angeles |  | 12625 | non_show | studio/TV/radio/home/rehearsal venue |
| 1991-10-24 | Bayfront Auditorium | Corpus Christi |  | 12640 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1992-01-18 | Radio City Music Hall | New York City |  | 12850 | unverified | no other source has the date |
| 1993-01-13 | WSM Grand Ole Opry | Nashville |  | 13790 | unverified | no other source has the date |
| 1993-02-15 | Vredenburg | Utrecht |  | 13900 | multi_night | TUIT has 1993-02-16 at Vredenburg too — TUIT lacks this night of the run |
| 1993-02-17 | Muziekcentrum Frits Philips | Eindhoven |  | 13920 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1993-02-25 | Mansfield Leisure Centre | Belfast | Northern Ireland | 13970 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1993-04-18 | Thomas Wolfe Auditorium | Asheville |  | 14030 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1993-04-27 | KRLU-TV Studios | Austin |  | 14065 | non_show | studio/TV/radio/home/rehearsal venue |
| 1993-04-28 | KRLU-TV Studios | Austin |  | 14070 | non_show | studio/TV/radio/home/rehearsal venue |
| 1993-05-19 | Grandma’s Warehouse | Los Angeles |  | 14072 | non_show | studio/TV/radio/home/rehearsal venue |
| 1993-11-18 | CBS TV Studio | New York City |  | 14640 | non_show | studio/TV/radio/home/rehearsal venue |
| 1994-02-09 | Nippon Budokan | Tokyo | Japan | 14680 | multi_night | TUIT has 1994-02-08 at Nippon Budokan too — TUIT lacks this night of the run |
| 1994-02-14 | Kyushu Koseinenkin Kaikan | Kokura | Japan | 14710 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1994-02-15 | Kyushu Koseinenkin Kaikan | Kokura | Japan | 14720 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1994-03-23 | Universal Amphitheater | Los Angeles |  | 14790 | unverified | no other source has the date |
| 1994-04-05 | Auditorium | Springfield |  | 14800 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1994-04-20 | Assembly Hall | Champaign |  | 14910 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1994-05-20 | Todaiji Temple | Nara | Japan | 15070 | corroborated_sfm | setlist.fm only — weaker |
| 1994-05-21 | Todaiji Temple | Nara | Japan | 15080 | corroborated_sfm | setlist.fm only — weaker |
| 1994-07-12 | Montreux Jazz Festival | Montreux | Switzerland | 15170 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1994-09-30 | Sony Music Studios | New York City |  | 15415 | non_show | studio/TV/radio/home/rehearsal venue |
| 1996-02-02 | Probably The Pavilion | Phoenix |  | 16975 | corroborated_sfm | setlist.fm only — weaker |
| 1997-04-18 | Recreation and Convocation Center | Albany |  | 18100 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1997-08-18 | Oakdale Theatre | Wallingford |  | 18350 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 1997-09-26 | Centro Agroalimentare Bolognese | Bologna | Italy | 18450 | unverified | no other source has the date |
| 1997-09-27 | Centro Agroalimentare Bolognese | Bologna | Italy | 18460 | corroborated_sfm | setlist.fm only — weaker |
| 1998-10-31 | Unidentified Studio | New York City |  | 19915 | non_show | studio/TV/radio/home/rehearsal venue |
| 2000-07-30 | Waterloo Village | Stanhope |  | 22140 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2001-11-26 | Sony Recording Studios | New York City |  | 23555 | non_show | studio/TV/radio/home/rehearsal venue |
| 2002-02-27 | Staples Center | Los Angeles |  | 23740 | corroborated_sfm | setlist.fm only — weaker |
| 2002-03-04 | Unidentified Recording Studio | Los Angeles |  | 23745 | non_show | studio/TV/radio/home/rehearsal venue |
| 2002-07-16 | Stage 6 | Canoga Park |  | 24035 | non_show | studio/TV/radio/home/rehearsal venue |
| 2002-07-23 | Scream Studios | Studio City |  | 24037 | non_show | studio/TV/radio/home/rehearsal venue |
| 2004-03-01 | The Pageant | St. Louis |  | 25730 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2004-03-02 | The Pageant | St. Louis |  | 25740 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2004-03-03 | The Pageant | St. Louis |  | 25750 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2004-08-24 | Fifth Third Ballpark | Comstock Park |  | 26450 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2005-04-02 | Auditorium Theatre | Chicago |  | 27010 | multi_night | TUIT has 2005-04-01 at Auditorium Theatre too — TUIT lacks this night of the run |
| 2005-05-25 | William H. Hammond Stadium | Fort Myers |  | 27220 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2005-05-28 | Osceola County Stadium | Kissimmee |  | 27240 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2005-06-01 | BellSouth Park | Chattanooga |  | 27270 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2005-06-10 | Salem Memorial Baseball Stadium | Salem |  | 27320 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2007-09-17 | Sound Emporium Recording Studio | Nashville |  | 29632 | non_show | studio/TV/radio/home/rehearsal venue |
| 2007-09-18 | Sound Emporium Recording Studio | Nashville |  | 29633 | non_show | studio/TV/radio/home/rehearsal venue |
| 2008-08-25 | Unidentified Venue | Little Rock |  | 30585 | non_show | studio/TV/radio/home/rehearsal venue |
| 2009-06-11 | Stage 15 | Culver City |  | 31227 | non_show | studio/TV/radio/home/rehearsal venue |
| 2010-02-11 | East Room | Washington |  | 31865 | non_show | studio/TV/radio/home/rehearsal venue |
| 2010-06-16 | Cittadella del Carnevale | Viareggio | Italy | 32140 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2010-10-25 | Overture Hall | Madison |  | 32630 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2011-02-13 | Staples Center | Los Angeles |  | 32890 | unverified | no other source has the date |
| 2011-04-15 | Marina Promenade | Singapore |  | 32960 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2013-05-02 | Red Hat Amphitheater | Raleigh |  | 34860 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2015-05-19 | Ed Sullivan Theatre | New York City |  | 36710 | corroborated_sfm | setlist.fm only — weaker |
| 2015-10-05 | Stockholm Waterfront Auditorium | Stockholm | Sweden | 36940 | multi_night | TUIT has 2015-10-06 at Stockholm Waterfront too — TUIT lacks this night of the run |
| 2016-10-28 | WorkPlay Theatre | Birmingham |  | 37875 | unverified | no other source has the date |
| 2018-03-30 | El Gran Teatre del Liceu | Barcelona | Spain | 38950 | multi_night | TUIT has 2018-03-31 at El Gran Teatre del Liceu too — TUIT lacks this night of the run |
| 2023-10-29 | Place des Arts, Salle Wilfrid-Pelletier | Montreal | Canada | 9004289 | corroborated | setlist.fm+bobdylan.com — TUIT calendar gap |
| 2026-10-17 | Spektrum | Oslo | Norway | 9004935 | after_crawl | after TUIT crawl 2026-09-07 |
| 2026-10-19 | Scandinavium | Gothenburg | Sweden | 9004936 | after_crawl | after TUIT crawl 2026-09-07 |
| 2026-10-21 | Forum Horsens | Horsens | Denmark | 9004937 | after_crawl | after TUIT crawl 2026-09-07 |

### Part 2 — venue join keys

Ground truth: 3,986 shared dates where each side names one venue. 2,714 TUIT venue entities, 2,411 olof venue strings (venue+city).

| key | date pairs linked | rate | conflicting-evidence links | TUIT venues linked | TUIT residue |
|---|---|---|---|---|---|
| exact | 2772 | 69.5% | 13 | 1780/2714 | 934 |
| fuzzy | 3716 | 93.2% | 345 | 2512/2714 | 202 |
| geo10 | 3748 | 94.0% | 351 | 2535/2714 | 179 |
| geo25 | 3752 | 94.1% | 358 | 2538/2714 | 176 |
| geo50 | 3756 | 94.2% | 375 | 2540/2714 | 174 |
| crosswalk | 1786 | 44.8% | 136 | 2695/2714 | 19 |
| geo25+crosswalk | 3785 | 95.0% | 384 | 2704/2714 | 10 |

#### Links `geo25` adds over `exact` — seeded sample of 40 / 1,282 (hand-labelled in the prose above)

| # | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1 | 2006 New Orleans Jazz & Heritage Festival, Fair Grounds - Acura Stage | New Orleans, Louisiana | Acura Stage | New Orleans |
| 2 | Beethovensaal | Stuttgart | Beethovensaal, Liederhalle | Stuttgart |
| 3 | Borgata Hotel Casino & SpaEvent Center | Atlantic City, New Jersey | Borgata Hotel Casino and Spa Event Center | Atlantic City |
| 4 | Brown County Arena | Green Bay, Wisconsin | Brown County Veterans Memorial Arena | Green Bay |
| 5 | Civic Center | Salem, Virginia | Salem Civic Center | Salem |
| 6 | Clay Center Maier Foundation Performance Hall | Charleston, West Virginia | Maier Foundation Performance Hall | Charleston |
| 7 | Colorado State Fair, The Events Center | Pueblo, Colorado | The Events Center | Pueblo |
| 8 | Donald N. Dedmon Center, Radford University | Radford, Virginia | Donald N. Dedmon Center | Radford |
| 9 | FirstEnergy Park | Lakewood | First Energy Park | Lakewood |
| 10 | Frederick Mann Music Center | Philadelphia, Pennsylvania | Mann Music Center | Philadelphia |
| 11 | Garden State Performing Arts Center | Holmdel, New Jersey | Garden State Arts Center | Holmdel |
| 12 | HMV Hammersmith Apollo | London | Hammersmith Apollo | London |
| 13 | Hall 4, S.E.C.C. | Glasgow | Hall 4 | Glasgow |
| 14 | Halle D, Wiener Stadthalle | Vienna | Stadthalle | Vienna |
| 15 | Hammersmith Apollo | London | HMV Hammersmith Apollo | London |
| 16 | Hard Rock Hotel & Casino, The Joint | Las Vegas, Nevada | The Joint | Las Vegas |
| 17 | Indiana (Emens Auditorium | Muncie, Indiana | Emens Auditorium | Muncie |
| 18 | LeFrak Gymnasium, Amherst College | Amherst, Massachusetts | LeFrak Gymnasium | Amherst |
| 19 | Lille Grand PalaisLe Zénith | Lille | Le Zénith | Lille |
| 20 | MSU Auditorium, Michigan State University | East Lansing, Michigan | MSU Auditorium | East Lansing |
| 21 | McMenamins Edgefield | Troutdale, Oregon | McMenamins Historic Edgefield Manor | Troutdale |
| 22 | Metro Radio Arena, (formerly Telewest Arena) | Newcastle | Metro Radio Arena | Newcastle |
| 23 | Mississippi Coliseum | Jackson, Mississippi | The Coliseum | Jackson |
| 24 | Montana State University, Brick Breeden Fieldhouse | Bozeman, Montana | Brick Breeden Field House | Bozeman |
| 25 | Palatrussadi di Milano | Milano | Palatrussardi di Milano | Milano |
| 26 | Performing Arts Center | Saratoga Springs, New York | Saratoga Performing Arts Center | Saratoga Springs |
| 27 | Pori Jazz 2014Kirjurinluoto Arena Main Stage | Pori | Main Stage | Pori |
| 28 | Prudential Hall, New Jersey Performing Arts Center | Newark, New Jersey | Prudential Hall | Newark |
| 29 | Saint Bonaventure University, Reilly Center Arena | Saint Bonaventure, New York | Reilly Center Arena | Olean |
| 30 | Shapiro Gymnasium, Brandeis University | Waltham, Massachusetts | Shapiro Gymnasium | Waltham |
| 31 | Sheffield Arena | Sheffield | The Arena | Sheffield |
| 32 | Shreveport Municipal Auditorium | Shreveport, Louisiana | Shreveport Municipal Memorial Auditorium | Shreveport |
| 33 | Soaring Eagle Casino and Resort, Soaring Eagle Entertainment Hall | Mt. Pleasant, Michigan | Soaring Eagle Entertainment Hall | Mt. Pleasant |
| 34 | Stephen O'Connell Center, University Of Florida | Gainesville, Florida | O'Connell Center | Gainesville |
| 35 | UNO Lakefront Arena | New Orleans | Nat Kiefer UNO Lakefront Arena | New Orleans |
| 36 | University of Massachusetts, Mullins Center | Amherst, Massachusetts | University of Massachusetts | Amherst |
| 37 | Wachovia Spectrum | Philadelphia, Pennsylvania | The Spectrum | Philadelphia |
| 38 | What Stage, Bonnaroo Music Festival | Manchester, TN | Bonnaroo Music Festival | Manchester |
| 39 | Wicomico Youth & Civic Center | Salisbury, Maryland | Wicomico County Civic Center | Salisbury |
| 40 | XXII Festival Cultural ZacatecasPlaza de Armas | Zacatecas | Plaza de Armas | Zacatecas |

Which side is longer on the shared dates:

| relation | pairs |
|---|---|
| equal | 2838 |
| tuit_longer | 699 |
| different | 332 |
| olof_longer | 117 |

#### `exact` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Kiva Auditorium, Convention Center | Albuquerque, New Mexico | Kiva Auditorium, Convention Center | Albuquerque |
| Prudential Hall, New Jersey Performing Arts Center | Newark, New Jersey | Prudential Hall, New Jersey Performing Arts Center | Newark |
| Indiana University Auditorium | Bloomington, IN | Indiana University Auditorium | Bloomington |
| Elliott Hall of Music | West Lafayette, IN | Elliott Hall of Music | West Lafayette |
| A.J. Palumbo Center, Duquesne University | Pittsburgh, PA | A.J. Palumbo Center at Duquesne University | Pittsburgh |
| Windsor Hall, Bournemouth International Centre | Bournemouth | Windsor Hall, Bournemouth International Centre | Bournemouth |
| Greek Theatre, UC Berkeley | Berkeley, CA | Greek Theatre, UC Berkeley | Berkeley |
| Borgata Hotel Casino And Spa, Event Center | Atlantic City, New Jersey | Borgata Hotel Casino and Spa Event Center | Atlantic City |
| Borgata Hotel Casino & Spa, Event Center | Atlantic City, New Jersey | Borgata Hotel Casino and Spa Event Center | Atlantic City |
| River Center Theatre For The Performing Arts | Baton Rouge, Louisiana | River Center Theatre for Performing Arts | Baton Rouge |
| Municipal Auditorium | Shreveport | Municipal Auditorium | Shreveport |
| Broward Center for the Performing Arts | Fort Lauderdale, Florida | Broward Center For The Performing Arts | Fort Lauderdale |
| ExploreAsheville.com Arena | Asheville, North Carolina | ExploreAsheville.com Arena | Asheville |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1988-10-19 | Unknown lineage apart transfered from Cassette, A Pop Life Recording. | New York, New York | Radio City Music Hall | New York City |
| 1992-05-21 | The Pantages Theater, Hollywood | Los Angeles, California | The Pantages Theater | Los Angeles |
| 1995-09-29 | Sunrise Music Center | Sunrise, Florida | Sunrise Musical Theatre | Fort Lauderdale |
| 1998-02-22 | Patriot Center, George Mason University | Fairfax, Virginia | Patriot Center | Fairfax |
| 1999-11-09 | The Apollo Of Temple, Temple University | Philadelphia, PA | The Apollo Of Temple | Philadelphia |
| 2001-07-07 | Universitätspark, (University Park) | Schwäbisch Gmünd | Universit tspark | Schw bisch Gm nd |
| 2003-05-10 | Hilton Hotel, Grand Theater | Atlantic City, New Jersey | Grand Theater | Atlantic City |
| 2004-11-11 | Saint Bonaventure University, Reilly Center Arena | Saint Bonaventure, New York | St. Bonaventure University | St. Bonaventure |
| 2007-07-08 | Casino RamaEntertainment Centre | Orillia, Ontario | Entertainment Centre | Orillia |
| 2009-08-05 | Whataburger Field | Corpus Christi, Texas | What-A-Burger Field | Corpus Christi |
| 2011-10-20 | Ahoy | Rotterdam | Sportpaleis Ahoy | Rotterdam |
| 2014-10-24 | Dolby Theatre | Hollywood, California | Dolby Theatre | Los Angeles |
| 2017-06-21 | Providence Performing Arts Center | Providence, Rhode Island | Performing Arts Center | Providence |
| 2022-04-08 | Mississippi State University Riley Center | Meridian Mississippi, Mississippi | MSU Riley Center | Meridian |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island |
| Porch # 2, Lawn of Newport Casino, Freebody Park | Newport, Rhode Island |
| Lisner Auditorium, George Washington University | Washington, District Of Columbia |
| County Center | White Plains, New York |
| Right), Royal Festival Hall | London |
| The State College, Rutgers Gymnasium | New Brunswick, New Jersey |
| Ciro's Le Disc, Hollywood | Los Angeles, California |
| The Oval, City Hall | Sheffield |
| A Hotel Room, Savoy Hotel | London |
| Hollywood Bowl Los Angeles | Los Angeles, California |
| Barton Hall, Cornell University | Ithaca, New York |
| San José Civic Auditorium | San José, California |

#### `fuzzy` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Carnegie Chapter Hall | New York, New York | Carnegie Hall | New York City |
| Gerde's Folk City | New York, New York | The Basement of Gerde's Folk City | New York City |
| Carnegie Hall | New York, New York | Carnegie Chapter Hall | New York City |
| The Basement of Gerde's Folk City | New York, New York | Gerde's Folk City | New York City |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island | Freebody Park, | Newport |
| The Arena | Seattle, Washington | Key Arena | Seattle |
| Odeon | Liverpool | Odeon Theatre | Liverpool |
| Jacksonville Coliseum | Jacksonville, Florida | The Coliseum | Jacksonville |
| Jacksonville Coliseum | Jacksonville, Florida | Jacksonville Veterans Memorial Coliseum | Jacksonville |
| Odeon Theatre | Liverpool | Odeon | Liverpool |
| The Spectrum · Afternoon | Philadelphia | First Union Spectrum | Philadelphia |
| The Spectrum · Afternoon | Philadelphia | Wachovia Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | First Union Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | Wachovia Spectrum | Philadelphia |
| Coliseum | Charlotte, North Carolina | Charlotte Coliseum | Charlotte |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1992-03-24 | State Theatre | New South Wales | State Theatre | Sydney |
| 1993-08-29 | Tinley Park World Of Music | Chicago, Illinois | Tinley Park World Of Music | Chicago. Illinois |
| 1997-08-13 | Hershey | Pennsylvania | Star Pavilion | Hershey |
| 1999-07-16 | Nissan Pavilion | Bristow, VA | Nissan Pavillion At Stone Ridge | Bristow |
| 2001-02-27 | Sun Palace | Sendai | Sun Plaza Hall | Sendai |
| 2002-08-02 | The Palladium | Worcester | Downstairs | Worcester |
| 2003-11-01 | Palalottomatica (Palaeur) | Rome | Roma Palaeur | Rome |
| 2005-11-17 | SECC | Glasgow | Scottish Exhibition And Conference Center | Glasgow |
| 2008-10-24 | General Motors Place | Vancouver, British Columbia | General Motors Arena | Vancouver |
| 2011-07-02 | Peace & Love Festival | Borlänge | Festivalområdet | Borlänge |
| 2013-07-31 | Fiddler's Green Amphitheatre | Greenwood Village | Fiddler's Green Amphitheatre | Denver |
| 2014-10-26 | Dolby Theatre | Hollywood, California | Dolby Theatre | Los Angeles |
| 2016-07-13 | Mann Center for the Performing Arts (The Mann Center) | Philadelphia, Pennsylvania | Mann Music Center | Philadelphia |
| 2022-03-08 | Buddy Holly Hall Helen DeVitt Jones Theater | Lubbock, Texas | Buddy Holly Hall of Performing Arts and Sciences | Lubbock |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| A Hotel Room, Savoy Hotel | London |
| Odeon Theatre | Birmingham |
| Memorial Coliseum | Corpus Christi, Texas |
| Unknown lineage apart transfered from Cassette, A Pop Life Recording. | New York, New York |
| Seashore Performing Arts Center, Old Orchard Beach | Portland, Maine |
| Chabad Telethon | Chabad Telethon |
| Houston Fieldhouse, Rensselaer Polytechnic Institute | Troy, New York |
| Estadio Cicero Pompeu de Toledo | Sao Paulo |
| Bob Dylan | London |
| The Charles Ives Center, Western Connecticut State College | Danbury, Connecticut |
| Kingswood Music Theatre, Maple | Ontario |
| Lakeside Amphitheater, Darien Lake Amusement Park, Darien Center | Corfu, New York |

#### `geo10` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Carnegie Chapter Hall | New York, New York | Carnegie Hall | New York City |
| Gerde's Folk City | New York, New York | The Basement of Gerde's Folk City | New York City |
| Carnegie Hall | New York, New York | Carnegie Chapter Hall | New York City |
| The Basement of Gerde's Folk City | New York, New York | Gerde's Folk City | New York City |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island | Freebody Park, | Newport |
| The Arena | Seattle, Washington | Key Arena | Seattle |
| Odeon | Liverpool | Odeon Theatre | Liverpool |
| Jacksonville Coliseum | Jacksonville, Florida | The Coliseum | Jacksonville |
| Jacksonville Coliseum | Jacksonville, Florida | Jacksonville Veterans Memorial Coliseum | Jacksonville |
| Odeon Theatre | Liverpool | Odeon | Liverpool |
| The Spectrum · Afternoon | Philadelphia | First Union Spectrum | Philadelphia |
| The Spectrum · Afternoon | Philadelphia | Wachovia Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | First Union Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | Wachovia Spectrum | Philadelphia |
| Coliseum | Charlotte, North Carolina | Charlotte Coliseum | Charlotte |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1992-07-04 | Porta Siberia | Genua | Porta Siberia | Genoa |
| 1993-09-03 | Darien Center, State Fairgrounds | Syracuse, New York | New York State Fairgrounds Grandstand | Syracuse |
| 1997-08-13 | Hershey | Pennsylvania | Star Pavilion | Hershey |
| 1999-09-17 | The Cynthia Woods Mitchell Pavilion | The Woodlands, TX | The Cynthia Woods Mitchell Pavilion | Houston |
| 2001-03-06 | Kosei-Nenkin Hall | Osaka | Kosei Nenkin Kaikan | Osaka |
| 2002-04-20 | FilaForum | Milan | Forum di Assago | Milan |
| 2003-10-04 | Flushing | New York | Shea Stadium | Flushing |
| 2005-10-20 | Location: Row 4, dead center | Karlstad | Löfbergs Lila Arena | Karlstad |
| 2007-10-08 | War Memorial at Oncenter | Syracuse, New York | War Memorial Arena | Syracuse |
| 2010-07-04 | Thomond Park Stadium | Limerick City | Thomond Park Stadium | Limerick |
| 2012-06-30 | Hop Farm Festival | Paddock Wood | Hop Farm | Paddock |
| 2014-07-07 | Stadthalle (City Hall) | Rostock | Stadt Halle Rostock | Rostock |
| 2015-07-08 | Palacio de Deportes de Granada (Granada Sports Palace) | Granada | Palacio Municipal de Deportes | Granada |
| 2017-10-14 | The Cosmopolitan Hotel and Casino The Chelsea | Las Vegas Nevada, Nevada | The Chelsea | Las Vegas |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Odeon Theatre | Birmingham |
| Memorial Coliseum | Corpus Christi, Texas |
| Unknown lineage apart transfered from Cassette, A Pop Life Recording. | New York, New York |
| Seashore Performing Arts Center, Old Orchard Beach | Portland, Maine |
| Chabad Telethon | Chabad Telethon |
| Houston Fieldhouse, Rensselaer Polytechnic Institute | Troy, New York |
| Bob Dylan | London |
| The Charles Ives Center, Western Connecticut State College | Danbury, Connecticut |
| Kingswood Music Theatre, Maple | Ontario |
| Gigantinho | Puerto Alegre |
| EXPO '92 | Seville |
| State Theatre | New South Wales |

#### `geo25` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Carnegie Chapter Hall | New York, New York | Carnegie Hall | New York City |
| Gerde's Folk City | New York, New York | The Basement of Gerde's Folk City | New York City |
| Carnegie Hall | New York, New York | Carnegie Chapter Hall | New York City |
| The Basement of Gerde's Folk City | New York, New York | Gerde's Folk City | New York City |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island | Freebody Park, | Newport |
| Forest Hills Tennis Stadium | New York, New York | Forest Hills Stadium | Forest Hills |
| The Arena | Seattle, Washington | Key Arena | Seattle |
| Odeon | Liverpool | Odeon Theatre | Liverpool |
| Jacksonville Coliseum | Jacksonville, Florida | The Coliseum | Jacksonville |
| Jacksonville Coliseum | Jacksonville, Florida | Jacksonville Veterans Memorial Coliseum | Jacksonville |
| Odeon Theatre | Liverpool | Odeon | Liverpool |
| The Spectrum · Afternoon | Philadelphia | First Union Spectrum | Philadelphia |
| The Spectrum · Afternoon | Philadelphia | Wachovia Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | First Union Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | Wachovia Spectrum | Philadelphia |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1992-07-04 | Porta Siberia | Genua | Porta Siberia | Genoa |
| 1993-09-03 | Darien Center, State Fairgrounds | Syracuse, New York | New York State Fairgrounds Grandstand | Syracuse |
| 1997-08-13 | Hershey | Pennsylvania | Star Pavilion | Hershey |
| 1999-09-17 | The Cynthia Woods Mitchell Pavilion | The Woodlands, TX | The Cynthia Woods Mitchell Pavilion | Houston |
| 2001-03-07 | Kosei-Nenkin Hall | Osaka | Kosei Nenkin Kaikan | Osaka |
| 2002-08-02 | The Palladium | Worcester | Downstairs | Worcester |
| 2003-10-24 | Budapest Sportaréna | Budapest | Budapest Sporthalle | Budapest |
| 2005-10-21 | Scandinavium | Gøteborg | Scandinavium | Gothenburg |
| 2007-10-16 | Wright State University Nutter Center | Dayton, Ohio | Ervin J. Nutter Center | Dayton |
| 2010-09-04 | Bumbershoot 2010, Seattle Center | Seattle, Washington | Seattle Center Coliseum | Seattle |
| 2012-07-13 | Benicassim Festival | Benicassim | Recinto de Conciertos | Benicàssim |
| 2014-08-18 | Palais Theatre | St. Kilda | Palais Theatre | Melbourne |
| 2015-07-13 | Festival de PoupetTheatre De Verdure | Saint-Malô-du-Bois | Theatre De Verdure | Saint-Malô-du-Bois |
| 2018-11-15 | Stanley Center For The Arts Stanley Theatre | Utica, New York | Stanley Performing Arts Center | Utica |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Odeon Theatre | Birmingham |
| Memorial Coliseum | Corpus Christi, Texas |
| Unknown lineage apart transfered from Cassette, A Pop Life Recording. | New York, New York |
| Seashore Performing Arts Center, Old Orchard Beach | Portland, Maine |
| Chabad Telethon | Chabad Telethon |
| Houston Fieldhouse, Rensselaer Polytechnic Institute | Troy, New York |
| Bob Dylan | London |
| The Charles Ives Center, Western Connecticut State College | Danbury, Connecticut |
| Kingswood Music Theatre, Maple | Ontario |
| Gigantinho | Puerto Alegre |
| EXPO '92 | Seville |
| State Theatre | New South Wales |

#### `geo50` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Carnegie Chapter Hall | New York, New York | Carnegie Hall | New York City |
| Gerde's Folk City | New York, New York | The Basement of Gerde's Folk City | New York City |
| Carnegie Hall | New York, New York | Carnegie Chapter Hall | New York City |
| The Basement of Gerde's Folk City | New York, New York | Gerde's Folk City | New York City |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island | Freebody Park, | Newport |
| Forest Hills Tennis Stadium | New York, New York | Forest Hills Stadium | Forest Hills |
| The Arena | Seattle, Washington | Key Arena | Seattle |
| Odeon | Liverpool | Odeon Theatre | Liverpool |
| Jacksonville Coliseum | Jacksonville, Florida | The Coliseum | Jacksonville |
| Jacksonville Coliseum | Jacksonville, Florida | Jacksonville Veterans Memorial Coliseum | Jacksonville |
| Odeon Theatre | Liverpool | Odeon | Liverpool |
| The Spectrum · Afternoon | Philadelphia | First Union Spectrum | Philadelphia |
| The Spectrum · Afternoon | Philadelphia | Wachovia Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | First Union Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | Wachovia Spectrum | Philadelphia |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1992-07-04 | Porta Siberia | Genua | Porta Siberia | Genoa |
| 1993-09-03 | Darien Center, State Fairgrounds | Syracuse, New York | New York State Fairgrounds Grandstand | Syracuse |
| 1997-08-13 | Hershey | Pennsylvania | Star Pavilion | Hershey |
| 1999-10-31 | UIC Pavilion | Chicago, IL | University Of Illinois Conference Center Pavilion | Chicago |
| 2001-06-30 | Roskilde Festival | Roskilde | Dyrskuepladsen | Roskilde |
| 2002-10-05 | McArthur Court, University Of Oregon | Eugene | MacArthur Court | Eugene |
| 2003-11-01 | Palalottomatica (Palaeur) | Rome | Roma Palaeur | Rome |
| 2005-11-08 | Zenith | München | Zenith | Munich |
| 2008-08-10 | Virgin Mobile Festival Pimlico Race Course | Baltimore, Maryland | Pimlico Race Track | Baltimore |
| 2010-11-14 | Monmouth University | West Long Branch, New Jersey | MAC Center | West Long Branch |
| 2012-07-18 | Fourviere Nights Festival, Theatres Romains De Fourviere | Lyon | Théâtre Antique de Fourvière | Lyon |
| 2014-08-21 | Palais Theatre | St. Kilda | Palais Theatre | Melbourne |
| 2015-10-09 | Falconer Salen | Frederiksberg | Falconer Salen | Copenhagen |
| 2019-06-28 | Scandinavium | Gothenberg | Scandinavium | Gothenburg |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Odeon Theatre | Birmingham |
| Memorial Coliseum | Corpus Christi, Texas |
| Unknown lineage apart transfered from Cassette, A Pop Life Recording. | New York, New York |
| Seashore Performing Arts Center, Old Orchard Beach | Portland, Maine |
| Chabad Telethon | Chabad Telethon |
| Houston Fieldhouse, Rensselaer Polytechnic Institute | Troy, New York |
| Bob Dylan | London |
| The Charles Ives Center, Western Connecticut State College | Danbury, Connecticut |
| Kingswood Music Theatre, Maple | Ontario |
| Gigantinho | Puerto Alegre |
| EXPO '92 | Seville |
| State Theatre | New South Wales |

#### `crosswalk` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| The Home Of Dave Whitaker | Minneapolis, Minnesota | The Home Of Dave Whitaker | Minneapolis |
| Royal Albert Hall | London | Royal Albert Hall | London |
| Royal Albert Hall | London | Royal Albert Hall | London |
| Veterans Memorial Coliseum · Afternoon | New Haven | New Haven Coliseum | New Haven |
| Holiday Star Music Theater | Merrillville, Indiana | Star Theatre | Merrillville |
| The Muny, Forest Park | St. Louis, Missouri | The Muny, Forest Park | St. Louis |
| New York State Fairground Grandstand | Syracuse, New York | New York State Fairground Empire Court | Syracuse |
| The Muny, Forest Park | St. Louis, Missouri | The Muny | St. Louis |
| Dyrskuepladsen | Roskilde | Dyrskuepladsen | Roskilde |
| Holiday Star Music Theater | Merrillville, Indiana | Holiday Star Music Theater | Merrillville |
| Holiday Star Music Theater | Merrillville, Indiana | Holiday Star Music Theater | Merrillville |
| Paramount Performing Arts Center | Springfield, Massachusetts | Paramount Theatre | Springfield |
| Charleston Municipal Auditorium | Charleston, West Virginia | Municipal Auditorium | Charleston |
| The Point Depot | Dublin | The Point Theatre | Dublin |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1961-05-06 | Montewese Hotel | Branford, Connecticut | Montewese Hotel | Branford |
| 1978-10-31 | Civic Center | St. Paul, Minnesota | Civic Center | St. Paul |
| 1989-07-12 | Allentown Fairgrounds | Allentown, Pennsylvania | Allentown Fairgrounds | Allentown |
| 1992-07-07 | Hippodromo di Maia | Merano | Ippodromo di Maia | Merano |
| 1995-03-15 | Otto Franke Halle | Aschaffenburg | Otto Franke Halle | Aschaffenburg |
| 1997-12-08 | Irving Plaza | New York, New York | Irving Plaza | New York City |
| 1999-11-10 | Veterans Memorial Coliseum | New Haven | New Haven Coliseum | New Haven |
| 2001-10-17 | University of California San Diego, RIMAC Arena | La Jolla, California | RIMAC Arena | La Jolla |
| 2003-11-13 | Le Zénith | Paris | Le Zénith | Paris |
| 2005-11-10 | Palamalaguti | Bologna | Palamalaguti | Bologne |
| 2008-06-05 | Siemens Arena | Vilnius | Siemens Arena | Vilnius |
| 2010-10-13 | Birmingham Jefferson Convention Center (BJCC) Concert Hall | Birmingham, Alabama | Concert Hall | Birmingham |
| 2013-07-11 | Peoria Civic Center | Peoria, Illinois | Peoria Civic Center Theater | Peoria |
| 2017-07-15 | Mosaic Place | Moose Jaw, Saskatchewan | Mosaic Place | Moose Jaw |
| 2022-10-27 | Bonus Arena | Hulll | Bonus Arena | Hull |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Porch # 2, Lawn of Newport Casino, Freebody Park | Newport, Rhode Island |
| City Hall | Newcastle |
| Odeon Theatre | Birmingham |
| North British Station Hotel | Glasgow |
| Memorial Coliseum | Corpus Christi, Texas |
| Portland Civic Auditorium | Portland, Oregon |
| Estadio Cicero Pompeu de Toledo | Sao Paulo |
| Estadio Cicero Pompeu de Toledo, Morumbi Stadium | Sao Paolo |
| m-audio delta audiophile 2496, -> Wavelab -> ssrc -> cdwave for tracking -> | Washington |
| The Strand | Providence |
| Beverly Hilton Hotel International Room | Beverly Hills, California |
| Centennial Park, Parade | Sydney |

#### `geo25+crosswalk` samples

Suspected false links:

| TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|
| Carnegie Chapter Hall | New York, New York | Carnegie Hall | New York City |
| Gerde's Folk City | New York, New York | The Basement of Gerde's Folk City | New York City |
| Carnegie Hall | New York, New York | Carnegie Chapter Hall | New York City |
| The Basement of Gerde's Folk City | New York, New York | Gerde's Folk City | New York City |
| Porch # 1 of Newport Casino, Freebody Park | Newport, Rhode Island | Freebody Park, | Newport |
| Forest Hills Tennis Stadium | New York, New York | Forest Hills Stadium | Forest Hills |
| The Arena | Seattle, Washington | Key Arena | Seattle |
| Odeon | Liverpool | Odeon Theatre | Liverpool |
| Jacksonville Coliseum | Jacksonville, Florida | The Coliseum | Jacksonville |
| Jacksonville Coliseum | Jacksonville, Florida | Jacksonville Veterans Memorial Coliseum | Jacksonville |
| Odeon Theatre | Liverpool | Odeon | Liverpool |
| The Spectrum · Afternoon | Philadelphia | First Union Spectrum | Philadelphia |
| The Spectrum · Afternoon | Philadelphia | Wachovia Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | First Union Spectrum | Philadelphia |
| The Spectrum | Philadelphia, Pennsylvania | Wachovia Spectrum | Philadelphia |

Missed date pairs (spread sample):

| date | TUIT venue | TUIT city | olof venue | olof city |
|---|---|---|---|---|
| 1963-07-17 | The Home Of Dave Whitaker | Minneapolis, Minnesota | [TOP] | Minneapolis |
| 1992-05-09 | Positivly 4th Street (Crocodile Beat 53008) | San Jose, California | San José Event State Center | San José |
| 1993-07-01 | El Pueblo Espaol | Barcelona rtm | El Pueblo Español | Barcelona |
| 1995-07-10 | Beethovensaal | Stuttgart | Stuttgart Killesberg | Stuttgart |
| 1999-04-17 | Plaza de Toros de La Malagueta | Málaga | La Malagueta Bull Ring | Málaga |
| 2000-06-20 | Jackson County Expo | Central Point, OR | Jackson County Expo Hall | Medford |
| 2001-07-08 | Montreux Jazz Festival, Stravinsky Auditorium | Montreux | Stravinsky Hall | Montreux |
| 2002-11-21 | First Union Arena | Wilkes-Barre, PA | First Union Center | Wilkes-Barre |
| 2004-05-05 | You Win Again | Wiltern Theater, LA | Wiltern Theatre | Los Angeles |
| 2005-11-27 | The Point Theatre | Dublin | The Point Depot | Dublin |
| 2008-09-06 | Concerts on the Green at Qualcomm | San Diego, California | Qualcomm Stadium | San Diego |
| 2011-07-02 | Peace & Love Festival | Borlänge | Festivalområdet | Borlänge |
| 2014-06-22 | LimaniThessaloniki Harbour | Thessaloniki | Thessaloniki Harbour, Limani | Thessaloniki |
| 2015-07-08 | Palacio de Deportes de Granada (Granada Sports Palace) | Granada | Palacio Municipal de Deportes | Granada |
| 2019-06-28 | Scandinavium | Gothenberg | Scandinavium | Gothenburg |

Unlinked TUIT venues:

| TUIT venue | city |
|---|---|
| The Home of Bob and Sid Gleason | East Orange, New Jersey |
| Folklore Center | New York, New York |
| Dobell's Jazz Record Shop | London |
| Odeon Theatre | Birmingham |
| Memorial Coliseum | Corpus Christi, Texas |
| m-audio delta audiophile 2496, -> Wavelab -> ssrc -> cdwave for tracking -> | Washington |
| The Strand | Providence |
| University Of California Davis, The Pavilion | Davis, California |
| Critics' Choice Movie Awards, Hollywood Palladium | Hollywood, CA |
| University of Maryland Baltimore CountyUMBC Event Center | Baltimore, Maryland |

<!-- GENERATED:tuit_olof_spine END -->
