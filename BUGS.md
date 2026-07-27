
BUG-279: tapematch: `pytest tests/` launches REAL tapematch sessions against the production DB and live audio
Status: FIXED 2026-07-27
File(s): tools/tapematch/tests/test_batch_queue.py:24,tools/tapematch/tapematch_session.py:1473
Reported: 2026-07-27
Description: Running the tapematch suite spawns full `tapematch_session.py <date>` subprocesses that decode real audio from /mnt/DATA0/examples/tapematch and COMMIT runs to tools/tapematch/observations.db. Observed 2026-07-27: two suite invocations wrote two complete runs for 1989-06-04 (run_ids 20260727_095955, 20260727_100316) to the production DB. Also the reason the suite takes 11 minutes (662s) instead of seconds.

Root cause: the four tests in test_batch_queue.py do `monkeypatch.setattr(sess, "run_date", fake_run_date)`, but `run_batch()` has not called `run_date` since commit ac804108 (2026-06-18), which refactored it to spawn one subprocess per date -- `cmd = [str(VENV_PYTHON), script, date_iso]; subprocess.run(cmd)` (tapematch_session.py:1473) -- so that Python heap and page cache are released between dates. The test file was last touched by c1059dd5 (2026-06-14) and was never updated, so the monkeypatch has been a silent no-op for ~6 weeks. The queue fixtures contain real dates ("1989-06-04", "1990-01-12", "2001-10-30"), so each unpatched test runs those dates for real.

Impact: (a) the production observations.db is mutated by anyone running the test suite -- benign so far only by luck (the 1989-06-04 runs reproduced the existing verdicts exactly: 15 pairs, 2 same_family, 0 changes vs the 2026-07-17 baseline), but a suite run during any other session would breach the project's "never run live tapematch sessions concurrently" rule and race on the shared caches and DB; (b) 2 of the 4 tests fail outright (`test_skips_blank_comment_and_done_lines`, `test_keyboard_interrupt_leaves_current_line_unmarked`) because the fake never records calls, so run_batch's queue/resume logic is currently UNTESTED; (c) 11-minute suite time discourages running it. Note the suite also has 2 unrelated pre-existing failures in test_find_lb_folders_no_audio.py (not investigated here).

Fix: (1) tapematch_session.py: new `_spawn(cmd) -> int` seam; all three drivers (run_batch, run_year, run_crawl) go through it instead of calling subprocess.run inline. (2) tools/tapematch/tests/conftest.py (new): autouse fixture replaces `sess._spawn` with a stub that raises AssertionError, so no test in the suite can spawn a real session -- a test needing a driver must patch `_spawn` explicitly, which wins by being applied later. (3) test_batch_queue.py rewritten to patch `_spawn` and assert on the spawned argv (run_batch's actual contract), with synthetic year-2999 dates so a regression cannot resolve real LB folders; added test_spawns_a_fresh_interpreter_per_date and test_unpatched_spawn_is_blocked_by_conftest (pins the guard itself). (4) test_find_lb_folders_no_audio.py: the same class of staleness, unrelated to the spawn issue -- both tests treated `find_lb_folders`'s `(found, excluded)` tuple as a dict (`TypeError: unhashable type: 'dict'`); now unpacked, and they assert on `excluded` too.
Result: suite is 314 passed / 0 failed in 26s, down from 4 failed / 662s. The 25x speedup is itself the proof that no real sessions spawn any more.

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

BUG-277: tapematch: a cross-referenced LB tag in a folder name shadows the folder's own LB number
Status: Open
File(s): tools/tapematch/tapematch/cli.py:512,tools/tapematch/tapematch_session.py:697
Reported: 2026-07-27
Description: Two distinct source folders on the same date can resolve to the SAME LB number, producing self-pairs (lb_a == lb_b) in observations.db latest_pairs. 7 such rows exist today: 1989-07-16/2204, 1988-06-07/2564, 1988-06-25/6295, 1988-07-20/1475, 1988-09-11/2585, 1988-09-23/3164, 1993-06-19/1929.

Root cause: cli.py:512 _lb_num() extracts the LB number by regexing the staged folder name (re.search(r'LB-(\\d+)', name)) and takes the FIRST match. Folder names that embed a cross-referenced LB tag before their own -- the docstring's own example is '... [fixed LB-2204]-LB-10437-v' -- therefore return 2204 instead of 10437. tapematch_session.py:697 _lb_num_from_folder() falls back to the same regex when its DB lookup misses, so the harness agrees with the wrong answer rather than catching it. The cli.py docstring already calls this 'a known, rare gap'; LB-2204 is one of the 7 live collisions, so it is firing in production, not hypothetical.

Impact: (a) a self-pair correlates 1.0 by construction and reads as a same_family merge -- it produced a spurious 'new merge' in the TODO-184 polarity validation on 1988-09-23; (b) more seriously, wherever the shadowing fires the pair/family rows are attributed to the WRONG LB entry, so recording_families membership for those sources is incorrect; (c) two of the 7 have corr ~0.003, confirming they are genuinely different recordings collapsed onto one LB number, not duplicate folders.

Fix direction: prefer the trailing/own LB tag over an embedded cross-reference (e.g. take the LAST LB-NNNNN match, or strip bracketed '[... LB-N ...]' segments before matching), and make the session-level DB lookup authoritative instead of silently falling back. Add a post-run assertion that no run emits lb_a == lb_b. Backfill: re-run the 7 affected dates after the fix. Guard already added in tools/tapematch/validate_polarity.py (skips lb_a == lb_b) so the validation harness no longer scores them.
Fix: TBD — see "Fix direction" above.

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
