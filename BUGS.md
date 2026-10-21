BUG-378: test_wtrf_tiebreak TestFindTorrentTie fails only in full-suite runs (order-dependent)
Status: Open
File(s): tests/test_wtrf_tiebreak.py
Reported: 2026-10-21
Description: test_tie_resolved_to_earliest and test_unresolvable_tie_records_candidates fail in a full serial pytest run on 876689938 and after; pass when the file runs alone. Likely state leaking from an earlier test (module global / shared DB / monkeypatch). Found 2026-10-21 during perf review.
Root cause: Unknown
Fix: —

BUG-377: test_commentary_audit cross-clause test fails on base
Status: Open
File(s): tools/tapematch/tests/test_commentary_audit.py
Reported: 2026-10-19
Description: test_cross_clause_same_keyword_does_not_leak_to_unrelated_lb fails on ccb1ec3cc too (pre-existing, found 2026-10-19 while validating TODO-319); tests tapematch_session.py commentary attribution.
Root cause: Unknown
Fix: —

BUG-375: Undefined CSS token var(--lbb-accent) renders uncoloured
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenFileIntegrity.tsx:135,gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:565,gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:656
Reported: 2026-10-18
Description: tokens.ts only defines --lbb-accent-{mid,soft,bg,line}; bare --lbb-accent is never set, so these 3 styles fall back to inherit/none (Known Tapers USER badge, recompute step colour, a File Integrity bar). Use --lbb-accent-mid. Found 2026-10-18 while linking /taper-curation.
Root cause: Unknown
Fix: —

BUG-374: tapematch test_cross_clause_same_keyword fails: 'alternate recording to' now reads as 0, test expects None
Status: Open
File(s): tools/tapematch/tests/test_commentary_audit.py:34,tools/tapematch/tapematch_session.py
Reported: 2026-10-17
Description: Found 2026-10-17 during TODO-361; fails on a clean tree too (pre-existing, not caused by the lint pass). sess._relationship_from_text(text, 680) for the 1984-06-04 LB-03917 commentary returns same=0 where the test expects None ('alternate recording to LB-0680' has no same/different keyword; the 'close eac match' clause is about LB-3914). Either the parser now deliberately maps 'alternate recording' to different (then update the test + docstring) or the cross-clause leak guard regressed. Rest of tools/tapematch/tests: 532 pass.
Root cause: Unknown
Fix: —
