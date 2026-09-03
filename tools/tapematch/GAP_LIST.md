# Collection gap list (TODO-334)

Generated 2026-09-03 16:07 by `tools/tapematch/build_gap_list.py`. Metadata only — no audio decoded. Machine-readable form: `data/tapematch/gap_list.json`.

Scope: **dates tapematch has run** — 3061 dates, 14215 catalogued recordings. 646 entries skipped for an unparseable `date_str`.


## Headline

| Bucket | Recordings | Meaning |
|---|---:|---|
| `present` | 12017 | resolved and ingested by the latest run |
| `private` | 2069 | on disk **with audio**, dropped by the private/no-torrent path rule |
| `unranked` | 110 | on disk, not ingested — no analyzable audio, or catalogued after the run |
| `absent` | 19 | not on disk — **the only real acquisition target** |

The shortfall `n_sources_db - n_sources_found` in `observations.db` is dominated by `private`, not `absent`. It is an analysis-coverage gap, not an acquisition gap.


## By decade

| Decade | Dates | present | private | unranked | absent |
|---|---:|---:|---:|---:|---:|
| 1960s | 43 | 221 | 7 | 2 | 0 |
| 1970s | 195 | 1002 | 123 | 7 | 6 |
| 1980s | 407 | 1875 | 316 | 45 | 5 |
| 1990s | 867 | 3576 | 1157 | 27 | 4 |
| 2000s | 855 | 3267 | 362 | 11 | 2 |
| 2010s | 502 | 1560 | 104 | 6 | 1 |
| 2020s | 192 | 516 | 0 | 12 | 1 |

## Acquisition targets — `absent` (19 recordings across 18 dates)

| Date | Location | LB | Category | Recorded path |
|---|---|---|---|---|
| 1974-05-09 | Chile Benefit | LB-01881 | concert | `_(no my_collection row)_` |
| 1975-11-11 | Palace Theater, Waterbury, CT | LB-05611 | concert | `_(no my_collection row)_` |
| 1978-03-27 | Perth, West Australia, Australia, Entert | LB-04162 | concert | `_(no my_collection row)_` |
| 1978-10-28 | Illinois State University, Carbondale, I | LB-01808 | concert | `_(no my_collection row)_` |
| 1978-11-04 | Omaha NE | LB-01795 | concert | `_(no my_collection row)_` |
| 1978-11-04 | Omaha NE | LB-01822 | concert | `_(no my_collection row)_` |
| 1987-10-14 | Wembley Arena, London | LB-05119 | concert | `_(no my_collection row)_` |
| 1987-10-16 | Wembley Arena, London | LB-05120 | concert | `_(no my_collection row)_` |
| 1988-10-13 | Tower Theater, Upper Darby, PA | LB-05117 | concert | `_(no my_collection row)_` |
| 1989-10-12 | The Beacon Theatre, New York City, New Y | LB-05126 | concert | `_(no my_collection row)_` |
| 1989-10-15 | Upper Darby, PA | LB-05128 | concert | `_(no my_collection row)_` |
| 1991-10-25 | Austin, TX | LB-08887 | concert | `_(no my_collection row)_` |
| 1993-09-11 | Jones Beach Amphitheatre, Wantagh, NY | LB-02406 | concert | `_(no my_collection row)_` |
| 1995-05-10 | San Diego, CA, Embarcadero Amphitheater, | LB-16340 | concert | `_(no my_collection row)_` |
| 1999-07-10 | Riverport Amphitheatre, Maryland Heights | LB-12508 | concert | `_(no my_collection row)_` |
| 2001-03-09 | Fukuoka | LB-03836 | concert | `_(no my_collection row)_` |
| 2003-08-23 | Niagara Falls, Ontario, Oakes Garden The | LB-16310 | concert | `_(no my_collection row)_` |
| 2017-04-01 | STOCKHOLM, SWEDEN | LB-13054 | concert | `/mnt/DYLAN1/Concerts/2017/2017-04-01 Stockholm (LB-13054+LB-13055+LB-13056)` |
| 2025-10-26 | Lingen, Germany | LB-16480 | concert | `_(no my_collection row)_` |

## Dates with the most unseen recordings

Ranked by `private + unranked + absent`. A date high on this list has a family count computed from materially less than the catalogue holds.

| Date | Location | Catalogued | Ingested | private | unranked | absent | Families |
|---|---|---:|---:|---:|---:|---:|---:|
| 1995-03-16 | Stadthalle, Bielefeld, Germany | 14 | 6 | 8 | 0 | 0 | 3 |
| 2000-09-24 | Portsmouth, England, Guildhall | 12 | 6 | 6 | 0 | 0 | 2 |
| 1997-12-08 | Irving Plaza, New York City | 15 | 9 | 6 | 0 | 0 | 3 |
| 1987-10-11 | Birmingham, England | 10 | 4 | 3 | 3 | 0 | 3 |
| 2000-03-17 | Reno | 13 | 7 | 6 | 0 | 0 | 7 |
| 1974-01-06 | The Spectrum, Philadelphia, Pennsy | 13 | 7 | 6 | 0 | 0 | 4 |
| 1989-10-22 | Keaney Auditorium, University Of R | 11 | 6 | 3 | 2 | 0 | 5 |
| 1974-01-31 | Madison Square Garden, New York Ci | 31 | 26 | 5 | 0 | 0 | 15 |
| 1995-03-13 | Prague | 11 | 6 | 5 | 0 | 0 | 3 |
| 1995-03-12 | Prague, Czech Republic | 12 | 7 | 5 | 0 | 0 | 3 |
| 1995-03-14 | Stadthalle, Furth, Germany | 12 | 7 | 5 | 0 | 0 | 4 |
| 2000-10-01 | Munster, Germany | 9 | 4 | 5 | 0 | 0 | 3 |
| 1990-01-12 | Toad's Place (New Haven, CT) | 17 | 12 | 2 | 3 | 0 | 11 |
| 1991-06-23 | Hamburg | 8 | 3 | 5 | 0 | 0 | 3 |
| 1991-06-22 | Bad Mergentheim | 7 | 2 | 5 | 0 | 0 | 2 |
| 1989-10-10 | New York City | 9 | 4 | 4 | 1 | 0 | 3 |
| 1993-09-11 | Jones Beach Amphitheatre, Wantagh, | 8 | 3 | 4 | 0 | 1 | 3 |
| 1999-11-19 | Sands Casino Atlantic City, New Je | 14 | 9 | 5 | 0 | 0 | 4 |
| 1975-10-31 | Plymouth, Massachusetts, War Memor | 15 | 10 | 5 | 0 | 0 | 9 |
| 1997-08-15 | Holmdel, New Jersey, PNC Bank Arts | 8 | 3 | 5 | 0 | 0 | 2 |
| 1997-08-23 | Vienna, Virginia, Filene Center. W | 14 | 9 | 5 | 0 | 0 | 3 |
| 1997-08-24 | Vienna, Virginia, Vienna, VA | 10 | 5 | 4 | 1 | 0 | 1 |
| 2000-06-18 | George, WA | 9 | 5 | 4 | 0 | 0 | 1 |
| 2000-10-05 | London | 8 | 4 | 4 | 0 | 0 | 4 |
| 2000-09-17 | Glasgow, Scotland | 8 | 4 | 4 | 0 | 0 | 3 |
| 2000-09-25 | Portsmouth, England, Guildhall | 8 | 4 | 4 | 0 | 0 | 2 |
| 2000-09-23 | International Arena, Cardiff, Wale | 9 | 5 | 4 | 0 | 0 | 3 |
| 2000-09-19 | Telewest Arena, Newcastle, England | 6 | 2 | 4 | 0 | 0 | 2 |
| 2000-09-29 | Jahrhunderthalle Menuhin Saal, Fra | 7 | 3 | 4 | 0 | 0 | 3 |
| 1999-04-13 | Santander, Spain | 9 | 5 | 4 | 0 | 0 | 3 |
| 1995-03-19 | Rodahal, Kerkrade, The Netherlands | 9 | 5 | 4 | 0 | 0 | 4 |
| 2000-03-10 | Anaheim | 10 | 6 | 4 | 0 | 0 | 5 |
| 1991-02-13 | London | 9 | 5 | 4 | 0 | 0 | 5 |
| 1995-03-15 | Aschaffenburg, Germany | 13 | 9 | 4 | 0 | 0 | 4 |
| 1999-07-10 | Riverport Amphitheatre, Maryland H | 7 | 3 | 3 | 0 | 1 | 2 |
| 1990-10-17 | New York City | 7 | 3 | 4 | 0 | 0 | 2 |
| 1990-10-18 | New York City | 7 | 3 | 4 | 0 | 0 | 1 |
| 2000-05-11 | Cologne, Germany | 10 | 6 | 4 | 0 | 0 | 2 |
| 1990-07-03 | Stadtpark, Hamburg, Germany | 10 | 6 | 4 | 0 | 0 | 5 |
| 2000-05-06 | Zurich, Switzerland | 9 | 5 | 4 | 0 | 0 | 3 |

## How to read this

- `private` recordings are excluded by `find_lb_folders` because a private/no-torrent folder has no local LB page, and therefore no curator commentary to corroborate a merge against. The audio is there. Admitting them is a policy decision, not a sourcing one.

- `unranked` mixes two causes that this census cannot separate without walking the folder: no locally analyzable audio, and catalogued-since-the-run. Re-running the date resolves both.

- A date's `n_families` is only as complete as its `present` column. Do not read a family count on a high-`n_unseen` date as the number of source tapes that exist.

