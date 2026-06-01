BUG-200: Pipeline smoke — Checksum verify mismatch (audio files differ from .ffp/.md5/.st5) (2 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN2/Concerts/1978/1978-06-20 London, England (LB-06548)
  • /mnt/DYLAN2/PRIVATE LB/Official Releases with LB NO Torrent/The Bootlegseries Volume 12 The Cutting Edge [24-96] LB 12181 No Torrent No trade

BUG-201: Pipeline smoke — No checksum files found (.ffp/.md5/.st5 absent) (60 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN1/Concerts/1996/1996-06-15 Tangkrogen Aarhus, Denmark (LB-01409)
  • /mnt/DYLAN1/Concerts/1999/1999-01-28 Sunrise, Fort Lauderdale, Florida (LB-12202)
  • /mnt/DYLAN1/Concerts/2013/2013-10-31 Amsterdan, NL Heineken Music Hall (LB-11291)
  • /mnt/DYLAN1/Concerts/1992/1992-04-16 State Theatre, Sydney (LB-00401)
  • /mnt/DYLAN1/Concerts/2001/2001-xx-xx Europe 2001 - LJK version (LB-08528)
  • /mnt/DYLAN1/Concerts/1996/1996-05-17 Cleveland, Ohio (LB-07407)
  • /mnt/DYLAN1/Concerts/1997/1997-08-05 Montréal (rb-canada)-LB-14964
  • /mnt/DYLAN1/Concerts/1991/1991-04-27 Sunrise FL (LB-12000)
  • /mnt/DYLAN1/Concerts/1997/1997-12-18 Los Angeles, CA (LB-07970)
  • /mnt/DYLAN1/Concerts/1996/1996-10-27 Austin, TX (LB-13770)
  … and 50 more (see pipeline_smoke_results.txt)

BUG-202: Pipeline smoke — Lookup not found (checksums parsed but no LB match) (1 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN1/Concerts/1985/1985-09-22 FARM AID 1, Champaign, Illinois (LB-12347)

BUG-203: Pipeline smoke — Lookup conflict (multiple LB matches) (11 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN1/Concerts/1993/1993-04-21 Monroe, La, USA (LB-07160) — Multiple LBs: [7160, 4653]
  • /mnt/DYLAN1/Concerts/2008/2008-06-16 Bergamo, Italy, Summer Sound Festival, Lazzaretto (LB-06195) — Multiple LBs: [6195, 6198]
  • /mnt/DYLAN2/Concerts/1978/1978-06-07 Los Angeles, CA (LB-11702) — Multiple LBs: [13944, 11702]
  • /mnt/DYLAN1/Concerts/2010/2010-03-15 Osaka, Japan Zepp Osaka (LB-08497) — Multiple LBs: [4994, 3029, 6748, 11900, 8497]
  • /mnt/DYLAN2/Concerts/1981/1981-07-12 Brondby-Hallen, Copenhagen (LB-00355) — Multiple LBs: [355, 2722]
  • /mnt/DYLAN2/Concerts/1978/1978-11-23 LLoyd Noble Center, Norman, OK (LB-00074) — Multiple LBs: [74, 7741]
  • /mnt/DYLAN1/Concerts/2004/2004-06-29 Bonn, Germany, Museumsplatz (LB-01901) — Multiple LBs: [1901, 4994, 3029, 6748, 11900]
  • /mnt/DYLAN1/Concerts/1997/1997-04-27 Boalsburg, Pennsylvania, Tussey Mountain Amphitheatre (LB-01992) — Multiple LBs: [1993, 1992]
  • /mnt/DYLAN1/Concerts/2008/2008-06-16 Bergamo, Italy, Summer Sound Festival, Lazzaretto (LB-06198) — Multiple LBs: [6198, 6195]
  • /mnt/DYLAN1/Concerts/2014/2014 The Tokyo Box-v-NoLB/2014-04-03 Tokyo Zepp Divercity-LB-11862 — Multiple LBs: [11381, 11862]
  … and 1 more (see pipeline_smoke_results.txt)

BUG-204: Pipeline smoke — Rename mismatch (folder name doesn't match LB standard) (123 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN1/LB HOPPER/BOB DYLAN 2023-07-07 Perugia, Italy (spot)-LB-15843 → 2023-07-07 Perugia, Italy (LB-15843)
  • /mnt/DYLAN1/LB HOPPER/2014-06-29 Klam, Austria - Bach-LB-15702 → 2014-06-29 Klam, Austria (LB-15702)
  • /mnt/DYLAN2/PRIVATE LB/1998 NOTORRENT/Sydney 3-9-1998-NTN No Torrent LB-14065 → LB-14065-NFT
  • /mnt/DYLAN2/PRIVATE LB/2002 NOTORRENT/London 12-5-2002-Condor-LB-6013 NO TORRENT → LB-06013-NFT
  • /mnt/DYLAN2/PRIVATE LB/1993 NOTORRENT/Washington 17-1-1993-Blue Jeans Bash-PA No Torrent LB-13843 → LB-13843-NFT
  • /mnt/DYLAN2/PRIVATE LB/2018 NOTorrent/Neu-Ulm 12-4-2018-CB No Torrent LB-13404 → LB-13404-NFT
  • /mnt/DYLAN2/PRIVATE LB/1997-3 NOTORRENT/Washington 5-12-1997 GD-LB-10049 NO TORRENT → LB-10049-NFT
  • /mnt/DYLAN2/PRIVATE LB/1997-3 NOTORRENT/Washington 5-12-1997-rp-LB 10063 No torrent → LB-10063-NFT
  • /mnt/DYLAN1/LB HOPPER/bd2022-10-02.mk4v.soomlos-LB-15727.flac24 → 2022-10-02 Flensburg, Germany (LB-15727)
  • /mnt/DYLAN1/LB HOPPER/bd 2022-05-31 Portland, Oregon (spot 44-16) FLACS-LB-15503 → 2022-05-31 Portland, Oregon (LB-15503)
  … and 113 more (see pipeline_smoke_results.txt)

BUG-205: Pipeline smoke — No LBDIR file found in folder (313 folders)
Status: Open
File(s): backend/app.py:4547, backend/checksum_utils.py:439
Reported: 2026-05-31
Root cause: (TBD — see samples below)
Fix: (TBD)
Samples:
  • /mnt/DYLAN1/LB HOPPER/BOB DYLAN 2023-07-07 Perugia, Italy (spot)-LB-15843
  • /mnt/DYLAN1/Concerts/2019/2019-06-26 Stockholm, Sweden (LB-14297)
  • /mnt/DYLAN1/LB HOPPER/2014-06-29 Klam, Austria - Bach-LB-15702
  • /mnt/DYLAN2/PRIVATE LB/1998 NOTORRENT/Sydney 3-9-1998-NTN No Torrent LB-14065
  • /mnt/DYLAN1/Concerts/1998/1998-09-23 Portland, Oregon, Rose Garden Arena (LB-00938)
  • /mnt/DYLAN2/PRIVATE LB/1993 NOTORRENT/Washington 17-1-1993-Blue Jeans Bash-PA No Torrent LB-13843
  • /mnt/DYLAN2/PRIVATE LB/2018 NOTorrent/Neu-Ulm 12-4-2018-CB No Torrent LB-13404
  • /mnt/DYLAN1/Concerts/2013/2013-10-18 Hannover, GER (LB-11102)
  • /mnt/DYLAN1/Concerts/2019/2019-05-03 Seville, Spain (LB-14144)
  • /mnt/DYLAN1/Concerts/1994/1994-07-05 Lyon, France (LB-05144)
  … and 303 more (see pipeline_smoke_results.txt)
