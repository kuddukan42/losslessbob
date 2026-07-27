
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
