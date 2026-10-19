# TUIT vs collection diff

Generated 2026-10-19 22:45 UTC by `tools/tuit_lb_diff.py` (read-only).

| Measure | Count |
|---|---|
| tuit recordings | 5468 |
| missing from collection | 2 |
| missing distinct lbs | 2 |
| unlinked | 32 |
| lb without checksums | 1 |
| filename disagreements | 1166 |
| filename distinct lbs | 1099 |
| filename db lacks tracks | 18 |
| filename renamed | 72 |
| filename mixed | 84 |
| filename db extra | 992 |

TUIT's detail page lists file names and sizes, not hashes, so (ii) compares track-name sets only; hash-level disputes still need the `.md5`/`.ffp` sidecars fetched from the torrent.

## (i) TUIT recordings the collection lacks (2)

By lb_status: public=2

| rec | LB | status | date | venue | format |
|---|---|---|---|---|---|
| 2656 | 2986 | public | 1994-07-14 | Schwarzl Freizeitzentrum | FLAC 16/44 |
| 3664 | 16353 | public | 2025-05-16 | Hollywood Bowl | FLAC 24/48 |

## (ii) Track-name disagreements (1166) - checksum-dispute input

### db_lacks_tracks (18)

| rec | LB | TUIT | DB | only on TUIT | only in DB |
|---|---|---|---|---|---|
| 513 | 12339 | 14 | 13 | tough_mama |  |
| 724 | 4907 | 25 | 9 | 2003.04.23cd1track01, 2003.04.23cd1track02, 2003.04.23cd1track03 ... |  |
| 869 | 3050 | 37 | 18 | 101. intro, 102. the wicked messenger, 103. she belongs to me ... |  |
| 1020 | 7397 | 61 | 20 | d3track01, d3track02, d3track03 ... |  |
| 1230 | 9663 | 32 | 16 | 01_2011_lux_intro, 02_2011_lux_leopard-skin pill-box hat, 03_2011_lux_it's all over now, baby blue ... |  |
| 1470 | 12231 | 42 | 21 | 01 bd2016-04-12d1t1, 01 bd2016-04-12d2t1, 02 bd2016-04-12d1t2 ... |  |
| 1861 | 3564 | 25 | 17 | bd1980-01-22sbd.t01, bd1980-01-22sbd.t02, bd1980-01-22sbd.t03 ... |  |
| 2492 | 3310 | 18 | 17 | bd1991-10-25d2tr08 |  |
| 2603 | 2368 | 37 | 18 | bd1993-04-17rtm_d1t01, bd1993-04-17rtm_d1t02, bd1993-04-17rtm_d1t03 ... |  |
| 2679 | 9022 | 15 | 14 | bd1994-10-01-d2t08 |  |
| 2713 | 11783 | 31 | 16 | bd1995-03-24 paris01, bd1995-03-24 paris02, bd1995-03-24 paris03 ... |  |
| 3147 | 3273 | 22 | 13 | track14, track15, track16 ... |  |
| 3995 | 8703 | 18 | 17 | 14 oh, boy [repaired] |  |
| 4046 | 3109 | 25 | 16 | d2t06, d2t07, d2t08 ... |  |
| 4354 | 3524 | 14 | 11 | 06 track06, 07 track07, 08 track08 |  |
| 4432 | 1762 | 19 | 18 | 2004-03-29_d1t01 |  |
| 4605 | 11719 | 17 | 16 | bob dylan - zepp divercity tokyo 2014 cc_disc 01 track 0 |  |
| 4883 | 2732 | 21 | 19 | 01 - introduction, 14 - i get lonesome |  |

### renamed (72)

| rec | LB | TUIT | DB | only on TUIT | only in DB |
|---|---|---|---|---|---|
| 202 | 4132 | 15 | 15 | 101 - all along the watchtower, 102 - tonight i'll be staying here with you, 103 - cold irons bound ... | track 01, track 02, track 03 ... |
| 203 | 2996 | 16 | 16 | 12-love sick, 13-rainy day women # 12 & 35, 14-blowing in the wind ... | 01-love sick, 02-rainy day women # 12 & 35, 03-blowing in the wind ... |
| 275 | 6640 | 18 | 18 | 01 d1tr1 2x2, 01 d2tr1 don't think twice it's allright, 02 d1tr2 pretty peggy-o (trad.) ... | bd92-07-07-meran-92-d1t01, bd92-07-07-meran-92-d1t02, bd92-07-07-meran-92-d1t03 ... |
| 278 | 6833 | 15 | 15 | bob dylan - san jose revisited_track01, bob dylan - san jose revisited_track02, bob dylan - san jose revisited_track03 ... | bd92-05-09-san-jose-revisted-d1t01, bd92-05-09-san-jose-revisted-d1t02, bd92-05-09-san-jose-revisted-d1t03 ... |
| 354 | 8164 | 19 | 19 | bob dylan - triple night_disc01 track01, bob dylan - triple night_disc01 track02, bob dylan - triple night_disc01 track03 ... | dylan - his triple night_disc01track01, dylan - his triple night_disc01track02, dylan - his triple night_disc01track03 ... |
| 404 | 4986 | 15 | 15 | bob dylan-28.5.95 reno-d1-track01, bob dylan-28.5.95 reno-d1-track02, bob dylan-28.5.95 reno-d1-track03 ... | bd1995-05-28-d1t01, bd1995-05-28-d1t02, bd1995-05-28-d1t03 ... |
| 465 | 6902 | 15 | 15 | 01 bob dylan - down in the flood (hall omnisports (differdange, luxembourg); june 24, 1996), 01 bob dylan - it's all over now, baby blue (hall omnisports (differdange, luxembourg); june 24, 1996), 02 bob dylan - god knows (hall omnisports (differdange, luxembourg); june 24, 1996) ... | bd96-06-24-you-may-call-me-zimmy-d1t01, bd96-06-24-you-may-call-me-zimmy-d1t02, bd96-06-24-you-may-call-me-zimmy-d1t03 ... |
| 509 | 4153 | 15 | 15 | 01 crash on the levee (down in the flood), 02 tonight i'll be staying here with you, 03 all along the watchtower ... | bd1999-04-20d1t01, bd1999-04-20d1t02, bd1999-04-20d1t03 ... |
| 553 | 2958 | 14 | 14 | 97-08-05 - 101-fixed, 97-08-05 - 102-fixed, 97-08-05 - 103-fixed ... | 97-08-05 - 101, 97-08-05 - 102, 97-08-05 - 103 ... |
| 617 | 50 | 20 | 20 | 00 announcement, 01 duncan and brady, 02 to ramona ... | bd00-09-13d1t01, bd00-09-13d1t02, bd00-09-13d1t03 ... |
| 651 | 5060 | 17 | 17 | 01 duncan and brady, 01 things have changed, 02 like a rolling stone ... | bd2001-05-06d1t01, bd2001-05-06d1t02, bd2001-05-06d1t03 ... |
| 783 | 1850 | 18 | 18 | bd2004-06-08d1t01, bd2004-06-08d1t02, bd2004-06-08d1t03 ... | d1track01, d1track02, d1track03 ... |
| 800 | 10242 | 18 | 18 | - 101 announcement, - 102 drifter's escape, - 103 it's all over now, baby blue ... | 101 announcement, 102 drifter's escape, 103 it's all over now, baby blue ... |
| 837 | 3891 | 15 | 15 | bd2006-07-20-bach-d1t01, bd2006-07-20-bach-d1t02, bd2006-07-20-bach-d1t03 ... | cosenza-06-pt.1(1), cosenza-06-pt.1(2), cosenza-06-pt.1(3) ... |
| 845 | 3875 | 14 | 14 | bd-060624-01 maggie's farm, bd-060624-02 she belongs to me, bd-060624-03 tweedle dee & tweedle dum ... | bd06-06-24d1tr01, bd06-06-24d1tr02, bd06-06-24d1tr03 ... |
| 873 | 3425 | 23 | 23 | bd_2005-10-21 - 101 intro, bd_2005-10-21 - 102 maggie's farm, bd_2005-10-21 - 103 tell me that it isn't true ... | 101 intro, 102 maggie's farm, 103 tell me that it isn't true ... |
| 880 | 3868 | 15 | 15 | track 101, track 102, track 103 ... | bd2006-07-02_ac_d1t01, bd2006-07-02_ac_d1t02, bd2006-07-02_ac_d1t03 ... |
| 909 | 5297 | 23 | 23 | 101-intro, 102-cat's in the well, 103-it ain't me, babe ... | 101 intro, 102 cat's in the well, 103 it ain't me, babe ... |
| 1017 | 7971 | 17 | 17 | bob dylan - 2009-07-05 sbmx 02 señor (tales of yankee power) | bob dylan - 2009-07-05 sbmx 02 senor (tales of yankee power) |
| 1033 | 7424 | 19 | 19 | d1t11_bobdylan_brussels_20090422_highway61 | d1t11_bobdylan_brussels_20090422_highway_61 |

...52 more in the --json output.

### mixed (84)

| rec | LB | TUIT | DB | only on TUIT | only in DB |
|---|---|---|---|---|---|
| 358 | 558 | 16 | 34 | bd1994-05-00.areyouexperienced.t01, bd1994-05-00.areyouexperienced.t02, bd1994-05-00.areyouexperienced.t03 ... | 01 - track01, 01_-_track01, 02 - track02 ... |
| 372 | 8904 | 31 | 60 | 101_fixed | bob dylan - positively west 52nd street cd 3 - 01. mama, you've been on my mind, bob dylan - positively west 52nd street cd 3 - 02. the lonesome death of hattie carrol, bob dylan - positively west 52nd street cd 3 - 03. boots of spanish leather ... |
| 379 | 6880 | 13 | 23 | track01, track01 - ballad of a thin man [fixed], track02 ... | bd95-04-12-gets-to-the-point-d1t01, bd95-04-12-gets-to-the-point-d1t02, bd95-04-12-gets-to-the-point-d1t03 ... |
| 493 | 2964 | 15 | 20 | disc01_track01, disc01_track02, disc01_track03 ... | 01 track01, 02 track02, 03 track03 ... |
| 508 | 2870 | 15 | 8 | 01 crash on the levee (down in the flood), 02 tonight i'll be staying here with you, 03 all along the watchtower ... | bob dylan - track 01, bob dylan - track 02, bob dylan - track 03 ... |
| 532 | 9205 | 15 | 24 | 02 señor (tales of yankee power) | 02 se�or (tales of yankee power), track01, track02 ... |
| 552 | 4785 | 13 | 21 | 02 señor (tales of yankee power) | 02 se�or (tales of yankee power), track01, track02 ... |
| 555 | 2012 | 16 | 8 | 1997-10-25d1track01, 1997-10-25d1track02, 1997-10-25d1track03 ... | track01, track02, track03 ... |
| 597 | 5099 | 16 | 52 | 01 - mrs robinson, 02 - me and julio, 03 - graceland | 01 bridge over troubled waters, 02 cant run but, 03 boy in the bubble ... |
| 609 | 2175 | 18 | 36 | bd1999-11-15t01, bd1999-11-15t02, bd1999-11-15t03 ... | 01 somebody touched me, 01_somebody_touched_me, 02 song to woody ... |
| 619 | 1434 | 19 | 31 | 2000_05_13_lund_cd1track01, 2000_05_13_lund_cd1track02, 2000_05_13_lund_cd1track03 ... | 101 announcement, 102 roving gambler, 103 the times they are a-changin' ... |
| 723 | 976 | 11 | 67 | track04-2 | 01 bob dylan - dignity, 01 bob dylan - tweedle dee & tweedle dum, 02 bob dylan - moonlight ... |
| 755 | 2139 | 20 | 52 | 13 most likely you go your way (and i'll go mine), 14 the lonesome death of hattie carroll, 15 honest with me ... | 01 most likely you go your way (and i'll go mine), 02 the lonesome death of hattie carroll, 03 honest with me ... |
| 756 | 1518 | 17 | 34 | 01-bob dylan - dylan2003-10-17d1t01, 01-bob dylan - dylan2003-10-17d2t01, 02-bob dylan - dylan2003-10-17d1t02 ... | 03 10 17 d1 t01, 03 10 17 d1 t02, 03 10 17 d1 t03 ... |
| 833 | 3881 | 17 | 32 | paestum-06-pt.2-fixed version(1) | 01. highway 61 revisited, 01. intro, 02. every grain of sand ... |
| 1519 | 14036 | 29 | 44 | 101 intro, 102 things have changed, 103 it aint me babe ... | 01 track01, 02 track02, 03 track03 ... |
| 1774 | 479 | 20 | 16 | bd1975-11-17lated1t01, bd1975-11-17lated1t02, bd1975-11-17lated1t03 ... | track01, track02, track03 ... |
| 1933 | 810 | 7 | 14 | 01 - do right woman, do right man (baez) (82-06-06 pasadena, ca), 05 - with god on our side (dylan & baez) (82-06-06 pasadena, ca), 06 - a pirate looks at forty (dylan & baez) (82-06-06 pasadena, ca) ... | 01 - do right woman, do right man (baez) (82-06-06 pasadena,, 01_-_do_right_woman,_do_right_man_(baez)_(82-06-06_pasadena,, 02_-_warriors_of_the_sun_(baez)_(82-06-06_pasadena,_ca) ... |
| 1935 | 881 | 20 | 40 | 1-01 - highway 61 revisited, 1-02 - jokerman, 1-03 - all along the watchtower ... | 84 05 31 d1 t01, 84 05 31 d1 t02, 84 05 31 d1 t03 ... |
| 1949 | 362 | 26 | 52 | d1track 01, d1track 02, d1track 03 ... | d1track 1, d1track 2, d1track 3 ... |

...64 more in the --json output.

### db_extra (992)

| rec | LB | TUIT | DB | only on TUIT | only in DB |
|---|---|---|---|---|---|
| 210 | 5160 | 12 | 36 |  | bd1998-06-28t01, bd1998-06-28t02, bd1998-06-28t03 ... |
| 212 | 4400 | 14 | 30 |  | dylan_1998_07_06_lucca_d1_01, dylan_1998_07_06_lucca_d1_02, dylan_1998_07_06_lucca_d1_03 ... |
| 218 | 1424 | 16 | 80 |  | 1989-07-21t01, 1989-07-21t02, 1989-07-21t03 ... |
| 220 | 2301 | 16 | 32 |  | 01, 02, 03 ... |
| 223 | 1777 | 18 | 31 |  | track01, track02, track03 ... |
| 226 | 2246 | 15 | 30 |  | 01 - positively 4th street, 02 - masters of war, 03 - lay lady lay ... |
| 230 | 244 | 17 | 26 |  | 01, 02, 03 ... |
| 244 | 1196 | 20 | 40 |  | bd_90-11-02_cd1_track_01, bd_90-11-02_cd1_track_10, bd_90-11-02_cd1_track_2 ... |
| 276 | 1877 | 18 | 36 |  | 01-i can't be satisfied (mckinley morganfield), 01-unbelievable, 02-dear landlord ... |
| 279 | 855 | 18 | 54 |  | 92_03_18_d1_t01, 92_03_18_d1_t02, 92_03_18_d1_t03 ... |
| 280 | 3225 | 18 | 36 |  | 92_09_02_d1_t01, 92_09_02_d1_t02, 92_09_02_d1_t03 ... |
| 282 | 403 | 18 | 32 |  | track01, track02, track03 ... |
| 284 | 3773 | 18 | 36 |  | bd_1991_11_12_d1t01, bd_1991_11_12_d1t02, bd_1991_11_12_d1t03 ... |
| 295 | 1950 | 18 | 36 |  | 01 new morning, 02 lay lady lay, 03 all along the watchtower ... |
| 296 | 10605 | 18 | 36 |  | track 01, track 02, track 03 ... |
| 350 | 628 | 19 | 56 |  | bd2002-08-23d1t01, bd2002-08-23d1t02, bd2002-08-23d1t03 ... |
| 351 | 631 | 19 | 38 |  | 00 announcement, 01 i am the man, thomas, 02 man in the long black coat ... |
| 355 | 4380 | 15 | 55 |  | 01 bd2000-03-10 late diskone, 01 bd2000-03-10 late disktwo, 01 i am the man, thomas ... |
| 360 | 9483 | 15 | 30 |  | bd1994-04-27.d1t01, bd1994-04-27.d1t02, bd1994-04-27.d1t03 ... |
| 362 | 5598 | 15 | 29 |  | 01 jokerman, 02 the man in me, 03 all along the watchtower ... |

...972 more in the --json output.


## Unlinked recordings (32)

| rec | LB | reason | date | venue |
|---|---|---|---|---|
| 152 |  | no LB number | 2004-03-25 | Avalon |
| 169 |  | no LB number | 1990-01-12 | Toad's Place |
| 176 |  | no LB number | 2026-06-20 | Acrisure Arena |
| 216 |  | no LB number | 1987-07-12 | Giants Stadium |
| 1593 |  | no LB number | 1992-04-24 | Waikiki Shell |
| 1594 |  | no LB number | 1994-08-16 | Art Park |
| 3767 |  | no LB number | 2026-07-08 | Huntington Bank Pavilion |
| 3768 |  | no LB number | 2026-07-08 | Huntington Bank Pavilion |
| 3769 |  | no LB number | 2026-07-08 | Huntington Bank Pavilion |
| 3770 |  | no LB number | 1990-02-07 | Hammersmith Odeon |
| 4381 |  | no LB number | 2026-06-23 | Arizona Financial Theatre |
| 4383 |  | no LB number | 1990-02-05 | Hammersmith Odeon |
| 4384 |  | no LB number | 1990-02-08 | Hammersmith Odeon |
| 4389 |  | no LB number | 1976-04-18 | Civic Center |
| 4390 |  | no LB number | 1990-02-01 | Theatre de Grand Rex |
| 4491 |  | no LB number | 2026-06-26 | Sandia Casino Amphitheater |
| 4492 |  | no LB number | 2026-06-24 | Casino del Sol Anselmo Valencia Amphitheater (AVA) |
| 5120 |  | no LB number | 1975-11-04 | Civic Center |
| 5121 |  | no LB number | 1976-05-01 | Reid Green Coliseum |
| 5399 |  | no LB number | 1961-07-21 | VARIOUS |
| 5400 |  | no LB number | 1961-07-29 | Riverside Church |
| 5401 |  | no LB number | 1960-05-04 | VARIOUS |
| 5402 |  | no LB number | 1961-11-23 | The Home Of Eve and Mac McKenzie |
| 5403 |  | no LB number | 1961-05-06 | Montewese Hotel |
| 5404 |  | no LB number | 1976-05-16 | Tarrant County Convention Center Arena |
| 5405 |  | no LB number | 1976-05-16 | Tarrant County Convention Center Arena |
| 5413 |  | no LB number | 2026-06-30 | Whitewater Amphitheater |
| 5558 |  | no LB number | 1991-02-08 | Hammersmith Odeon |
| 5559 |  | no LB number | 1994-07-10 | Tanzbrunnen, Rheinpark |
| 5560 |  | no LB number | 1994-08-12 | Stratton Mountain Ski Resort |
| 5561 |  | no LB number | 2000-11-02 | Elliott Hall of Music |
| 6039 |  | no LB number | 2000-07-08 | Riverport Amphitheatre |

## LBs on TUIT with no checksum rows (1)

| rec | LB | tracks |
|---|---|---|
| 4509 | 15930 | 21 |
