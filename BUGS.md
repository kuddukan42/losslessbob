BUG-329: tapematch secondary-match display and cluster merge use different predicates, so a pair prints 'below merge threshold' and is merged anyway
Status: Open
File(s): tools/tapematch/tapematch/cli.py:835,tools/tapematch/tapematch/cli.py:839
Reported: 2026-08-21
Description: In cli.py the SECONDARY MATCH section computes will_merge = windowed_frac >= wc_thr or (hiss_frac >= hm_thr and hiss_median >= hm_med_thr) or (fp_cluster_thr > 0 and fp_score >= fp_cluster_thr), and prints '-> SECONDARY LINK' or '-> hiss evidence (below merge threshold)' from it. The clustering step decides the merge separately, and the two disagree. Reproduced in data/tapematch/runs/20260710_030008_1997-12-05: SECONDARY MATCH prints 'LB-03909 / LB-16114: hiss 0.58 (89 segs, med 0.222) [primary corr 0.074] -> hiss evidence (below merge threshold)' (hiss_median 0.222 fails hm_med_thr), yet CLUSTERS emits 'Family 1: ... (mean intra-corr 0.074 [low confidence]) [secondary: LB-03909/LB-16114 via hiss 0.58]' and DIAGNOSTICS tags it [SECONDARY SAME-SOURCE]. Either the display predicate or the clustering predicate is wrong; they must be one shared function. This matters beyond cosmetics — the merged family is written to recording_families by backend.tapematch_sync, so whichever side is wrong is either creating or hiding real family merges. Decide which threshold set is authoritative, extract it to a single helper used by both call sites, then re-check whether other already-analysed dates carry the same contradiction.
Root cause: Unknown
Fix: —

BUG-328: prep_analysis_input.py attaches unrelated LB info files pulled from typos in uploader commentary
Status: Open
File(s): tools/tapematch/prep_analysis_input.py:36,tools/tapematch/prep_analysis_input.py:101
Reported: 2026-08-21
Description: LB_TAG_RE scans each source's commentary for \bLB-(\d+)\b and globs LBF-<padded>-*.txt for every hit, with no check that the matched id belongs to the date under analysis. Uploader commentary routinely contains typo'd or cross-referenced ids, so unrelated shows get spliced into analysis_input.md as if they were lineage evidence for this date. Two cases from the 2026-08-21 batch: (1) 20260710_120810_1999-06-20 — LB-11925's text cites 'Source: LB-0897', which pulled in the LBF file for LB-00897, a 1981-06-30 London show; the real match was LB-00857. (2) 20260710_131015_1999-07-24 — LB-07488's text contains 'LB-1711', pulling in LB-01711 (1999-06-26 Las Vegas); the real reference was LB-01771. Neither changed its verdict, but the analysis writer (human or model) is handed prose from the wrong concert and asked to reconcile it, which is exactly the input that produces false 'needs review' flags. Fix: before attaching an LBF file, confirm its concert date matches the run's date (or attach it under an explicit 'cross-reference, different date' heading rather than inline with the source's own lineage).
Root cause: Unknown
Fix: —

BUG-327: tapematch ingest still double-counts a source whose duplicate copies sit in sibling subfolders
Status: Open
File(s): tools/tapematch/tapematch/ingest.py:158,tools/tapematch/tapematch/ingest.py:175,tools/tapematch/tapematch/ingest.py:182
Reported: 2026-08-21
Description: Sibling of BUG-326. LB-07173 (run data/tapematch/runs/20260821_184430_1993-08-28) ingests 25 tracks / 3:27:33 against a 1:32:48 date median — flagged [INFLATED] at 120.2% longer, 'correlation results for this source are unreliable'. Both existing de-dup passes fired on it: _dedupe_formats logged 'dropped 2 duplicate file(s)' five times and _dedupe_subtrees ran after it, yet the doubled runtime survives. So neither the suffix-based format de-dup (BUG-326's fix) nor the subtree de-dup catches this layout. Two other runs in the 2026-08-21 batch show the same unexplained duration shape and should be checked against the same cause: LB-06780 (20260821_174451_1987-07-19) and LB-06698 (20260821_150958_1969-08-31) — both short rather than long, so confirm before assuming one root cause. Next step: locate LB-07173's source folder on disk and dump list_tracks() output to see which 25 files survive de-dup and why _dedupe_subtrees does not collapse them. Inflated sources silently corrupt correlation and clustering for their whole date, so this also puts the 1993-08-28 verdict in question.
Root cause: Unknown
Fix: —


