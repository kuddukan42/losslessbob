BUG-387: qBittorrent overwrote 1,147 collection masters through overlay hardlinks (100 with corrupt audio) — restore needed
Status: Open
File(s): tools/wtrf_repair_extras.py:148,backend/wtrf_review.py:173,backend/seed_overlay.py:831
Reported: 2026-10-22
Description: Audit 2026-10-22 of all 13,074 qBittorrent torrents: qBittorrent has already written through overlay hardlinks into collection masters. 2,339 masters modified after creation since overlays began (2026-08-19); 100 FLACs now fail audio md5 (34 LBs, 36 folders), 1,047 more no longer match their LB md5 (98 LBs; control siblings 99.4% match), 841 modified with no LB md5 to check, 351 rewritten byte-identical. Cause: size-only links to LB-good masters where the tracker copy differs (bit rot / other version), then qBittorrent downloaded those pieces through the links — wtrf_repair_extras start-before-recheck and WTRF-review resume were the live triggers. Exposure closed same day (tools/overlay_isolate.py --apply: 1,039 links / 23.7 GB copied out of 224 overlays; resume guard). OPEN: restore damaged masters from a clean source. Full list: data/logs/bug387_damaged_masters.tsv. LB-15933 seeds in place at 99.95% from /mnt/DYLAN2/Concerts/1974 — keep stopped.
Root cause: Unknown
Fix: —
