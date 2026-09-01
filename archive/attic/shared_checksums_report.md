# Shared-checksum report (BUG-118 item 1)

Generated 2026-07-15 from data/losslessbob.db (checksums, xref=0 rows only).

- (checksum, chk_type) groups appearing under 2+ distinct LB numbers: **5261**
- Distribution by number of LBs sharing: 2 LBs: 4231, 3 LBs: 159, 4 LBs: 149, 5 LBs: 718, 6 LBs: 3, 7 LBs: 1

## Degenerate hashes (root cause of phantom conflicts — now excluded from lookup)

| hash | meaning | LBs affected |
|---|---|---|
| `00000000000000000000…` (f) | all-zero ffp (no MD5 in STREAMINFO) | 3595,4243,7275,12671,13392,14392,14532 |
| `d41d8cd98f00b204e980…` (f) | hash of zero-byte file | 4994,11900 |

## Top 25 LB-sets by number of shared hashes

Sets sharing hundreds of hashes are almost certainly one recording under multiple
LB entries (candidates for xref/same_as linkage or curator merge review).

| shared hashes | LB set |
|---|---|
| 718 | LB-16054, LB-16101, LB-16440, LB-16511, LB-16621 |
| 172 | LB-00010, LB-00024 |
| 149 | LB-16101, LB-16440, LB-16511, LB-16621 |
| 100 | LB-12525, LB-16456 |
| 98 | LB-04819, LB-07837 |
| 76 | LB-01264, LB-03231 |
| 70 | LB-05309, LB-05732 |
| 66 | LB-13059, LB-13060 |
| 56 | LB-01363, LB-01364 |
| 56 | LB-10300, LB-14258 |
| 54 | LB-12923, LB-12924 |
| 50 | LB-03605, LB-12061 |
| 50 | LB-01979, LB-03289 |
| 50 | LB-09326, LB-09355 |
| 48 | LB-08904, LB-08918 |
| 45 | LB-05195, LB-11998 |
| 44 | LB-07757, LB-07776 |
| 43 | LB-06805, LB-14059 |
| 42 | LB-07775, LB-07777 |
| 42 | LB-07716, LB-07738 |
| 40 | LB-15915, LB-15957 |
| 40 | LB-07275, LB-07302, LB-07307 |
| 40 | LB-02654, LB-09327 |
| 38 | LB-01642, LB-09520 |
| 38 | LB-08277, LB-12390 |

## Notes

- 32 lb_problems rows were added 2026-07-15 covering the BUG-118 conflict pairs,
  the phantom quartet (04994/03029/06748/11900), the 16000-series six-way cluster,
  BUG-120 verify mismatches, and BUG-252 reconcile entries.
- Lookup now ignores degenerate hashes (backend/db.py _is_degenerate_checksum).
- Importer logs a de-dup warning when an incremental import introduces hashes
  already present under other LB numbers (backend/importer.py).
