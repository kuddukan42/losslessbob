
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
