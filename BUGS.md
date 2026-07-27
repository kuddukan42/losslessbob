
BUG-278: tapematch: addon_links.rule_d can never fire in a live session (emb_score absent from the link metrics)
Status: Open
File(s): tools/tapematch/tapematch/cli.py:890,tools/tapematch/tapematch_session.py:1665,tools/tapematch/tapematch/verdict.py:311
Reported: 2026-07-27
Description: `addon_links.rule_d` (emb_score AND emb_score_global both >= 0.75) was calibrated on the full frozen set 2026-07-04 at zero new FP and shipped `enabled: true`. It has never fired during an actual tapematch session. 46 curator-claimed pairs in observations.db clear its bar and are still stored `different_family`; run dates span 2026-06-02 to 2026-07-26, i.e. well past the enablement date.

Root cause: cli.py's `_pair_metrics(i, j)` (the dict handed to `verdict.pair_links` via `match.cluster(link_fn=...)`) builds only corr / windowed_frac / hiss / fp_score / speed_kind / hf_ceiling / nyquist / lb_a / lb_b. It never sets `emb_score` or `emb_score_global`, so `verdict._rule_d_emb_both` hits its `if emb is None` guard and returns False on every pair. The columns DO get populated -- but by `emb_live.populate_live_emb_scores()` called from `tapematch_session.py::_log_to_obs_db()`, which runs after the analysis has already clustered and decided `same_family`. TODO-200 added the live embedding path intending exactly this rule to fire live; the values land in the DB one stage too late to affect the verdict that is written alongside them.

Impact: the only production merge path for the embedding is dead in live runs. Offline it partly compensates -- regression.py::_passthrough_with_rule_d additively unions rule_d into the passthrough result -- so the harness and the shipped session disagree about what the configured system does, and CALIBRATION/regression numbers reflect a rule the pipeline is not actually applying. Measured effect of linking rule_d and re-closing each date transitively: 58 curator-claimed pairs and 80 curator-silent pairs flip to same_family across 80 dates.

Fix direction: NOT a one-line addition of two dict keys. Making rule_d fire live requires emb scores to exist before clustering, which means hoisting the emb_live extraction ahead of `match.cluster` in the cli analyze path (it needs only source folder paths, not `results`, so this is feasible) and then adding the two keys to `_pair_metrics`. Gate the change on scoring the 80 curator-silent flips first: rule_d's zero-new-FP proof covers the 2,245-pair frozen sets only, and these merges are corpus-wide and outside that population. Evidence + per-pair tables: tools/tapematch/CONTRADICTED_EMB_SECOND_PASS.md (section 4), regenerate with tools/tapematch/emb_second_pass.py.
Fix: TBD — see "Fix direction" above.

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
