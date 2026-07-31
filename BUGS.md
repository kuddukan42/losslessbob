
BUG-278: tapematch: addon_links.rule_d can never fire in a live session (emb_score absent from the link metrics)
Status: FIXED 2026-07-27 (code); re-run of the 79 remaining affected dates in progress
File(s): tools/tapematch/tapematch/cli.py:890,tools/tapematch/tapematch_session.py:1665,tools/tapematch/tapematch/verdict.py:311
Reported: 2026-07-27
Description: `addon_links.rule_d` (emb_score AND emb_score_global both >= 0.75) was calibrated on the full frozen set 2026-07-04 at zero new FP and shipped `enabled: true`. It has never fired during an actual tapematch session. 46 curator-claimed pairs in observations.db clear its bar and are still stored `different_family`; run dates span 2026-06-02 to 2026-07-26, i.e. well past the enablement date.

Root cause: cli.py's `_pair_metrics(i, j)` (the dict handed to `verdict.pair_links` via `match.cluster(link_fn=...)`) builds only corr / windowed_frac / hiss / fp_score / speed_kind / hf_ceiling / nyquist / lb_a / lb_b. It never sets `emb_score` or `emb_score_global`, so `verdict._rule_d_emb_both` hits its `if emb is None` guard and returns False on every pair. The columns DO get populated -- but by `emb_live.populate_live_emb_scores()` called from `tapematch_session.py::_log_to_obs_db()`, which runs after the analysis has already clustered and decided `same_family`. TODO-200 added the live embedding path intending exactly this rule to fire live; the values land in the DB one stage too late to affect the verdict that is written alongside them.

Impact: the only production merge path for the embedding is dead in live runs. Offline it partly compensates -- regression.py::_passthrough_with_rule_d additively unions rule_d into the passthrough result -- so the harness and the shipped session disagree about what the configured system does, and CALIBRATION/regression numbers reflect a rule the pipeline is not actually applying. Measured effect of linking rule_d and re-closing each date transitively: 58 curator-claimed pairs and 80 curator-silent pairs flip to same_family across 80 dates.

VALIDATION GATE PASSED 2026-07-27: the corpus-wide flips were scored against the curator's own stance before proposing the fix. Splitting all 23,962 pairs by lb_says_same (1 = claims same, 0 = EXPLICIT denial, NULL = silent), rule_d fires on 20.16% of claims-same (732/3,631), 4.17% of silent (721/17,293) and 0.39% of explicit denials (12/3,038) -- a 52x discrimination between claimed-same and curator-denied, i.e. the rule tracks source identity rather than firing indiscriminately. Of those 12 denial hits, 10 already carry corr >= 0.83 (primary signal merges them anyway -- curator label noise, the TODO-201 class), not rule_d errors. Of the 138 transitive flips: 58 curator-claims-same, 79 curator-silent, and exactly ONE contradicts an explicit denial -- 1999-11-09 LB-02737/LB-04289 (emb 0.872/0.937, corr 0.101), where LB-4289's notes read "different recording than LB-1401 , LB-2064 , and LB-2737 based on different crowd at begin of d1t2". That single pair is the entire measured FP exposure. Earlier framing of "80 unvalidated silent merges" was wrong: curator SILENCE is not curator DISAGREEMENT, and separating NULL from 0 is what resolves it.

Fix direction: NOT a one-line addition of two dict keys. Making rule_d fire live requires emb scores to exist before clustering, which means hoisting the emb_live extraction ahead of `match.cluster` in the cli analyze path (it needs only source folder paths, not `results`, so this is feasible) and then adding the two keys to `_pair_metrics`. Then re-run the 80 affected dates and re-sync families. Two non-blocking watch items: (a) 1978-03-09 is the only date with >=4 sources where rule_d links EVERY pair, collapsing the date into one family -- spot-check before/after; (b) 156 of 793 rule_d-firing dates have median emb >= 0.60 across all pairs (the same-show/different-source confound from BASELINE.md Task 8) -- the both-convention requirement appears to handle it, but a per-date baseline guard is the natural mitigation if t_emb is ever loosened below 0.75. Evidence + per-pair tables: tools/tapematch/CONTRADICTED_EMB_SECOND_PASS.md (section 4), regenerate with tools/tapematch/emb_second_pass.py.
Fix (commit a27594cb): (1) emb_live.score_session_pairs() -- DB-free scoring shared by the pre-clustering path and the existing post-clustering persist path, so a live verdict and the row later written to observations.db cannot disagree. (2) tapematch/cli.py: new `--concert-date` (the embedding cache is date-keyed and the CLI had no notion of a date); scores every pair before `match.cluster` and feeds emb_score/emb_score_global into `_pair_metrics`. Lazy, defensive import -- any failure leaves the scores None and rule_d abstains exactly as before. (3) tapematch_session.py: passes the date at both run_tapematch call sites.
VERIFIED end-to-end 2026-07-27 on 1994-02-16 (a tier-A date): the run logged "embedding: scored 21 pair(s), 3 at/above the rule_d bar" -- the first time rule_d has ever fired in a live session -- and produced exactly the 3 predicted flips. LB-10872 joined the {5202, 14921, 15363} family via two direct links (5202/10872 emb 0.978, 10872/15363 emb 0.954) plus 10872/14921 transitively. Regression test test_cli_shaped_metrics_reach_rule_d pins the behaviour: the same metrics dict links with emb present and abstains without, so dropping the keys again fails the suite.
Remaining: re-run the other 79 affected dates + re-sync families to the app DB.

BUG-210: backend/lossless_bob.db keeps reappearing in repo root (untracked, empty)
Status: Open
File(s): backend/lossless_bob.db (unknown origin)
Reported: 2026-06-18
Root cause: Unconfirmed. The real DB path is APP_ROOT/data/losslessbob.db (no underscore,
  see backend/paths.py:25 DB_PATH), and grepping the entire codebase (backend/, tools/,
  tests/, gui_next/src) for the literal string "lossless_bob" (with underscore) returns zero
  matches — no application code, test, fixture, or config constructs this filename. Deleting
  the file and re-running the full pytest suite + test_db_writes.py from backend/ as cwd did
  not recreate it. Likely created by an ad hoc shell/Python one-liner run with backend/ as cwd
  (e.g. a manual `sqlite3.connect("lossless_bob.db")` sanity check using a mistyped/placeholder
  filename instead of the real DB_PATH) rather than a reproducible app code path. Needs a repro
  case next time it reappears — note what command/action immediately preceded its creation.
REPRO CONFIRMED 2026-07-27 — and the 2026-06-18 hypothesis above was exactly right. The file
  reappeared during the TODO-184 session; the Claude session itself created it while probing
  for a review-flag column, via `sqlite3.connect('backend/lossless_bob.db')` run from the repo
  root — a guessed-at DB filename in an ad hoc one-liner, never touched by application code.
  sqlite3.connect() creates a 0-byte file on connect even when no table is ever written, which
  is why it always turns up empty with `SELECT name FROM sqlite_master` returning [].
  So this is NOT an application bug: every recurrence is an agent or human typing the wrong DB
  path in a throwaway query. The real path remains backend/paths.py:25 DB_PATH →
  APP_ROOT/data/losslessbob.db (no underscore).
Recommended close: add `lossless_bob.db` (or `backend/*.db`) to .gitignore so the stray file
  stops showing up as untracked noise in git status and session briefings, and close this as
  won't-fix/by-design rather than leaving it open against application code. The 0-byte file
  from this session was deleted.
Fix: TBD — pending repro. Stray file deleted from working tree each time it's noticed; it has
  never been committed (untracked since it doesn't match any .gitignore rule, but also isn't
  staged/added).
