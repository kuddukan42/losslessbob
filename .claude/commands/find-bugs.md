---
description: Root-cause bug hunt — discover, rank, then confirm-and-fix one bug at a time with repro + instrumentation
argument-hint: [optional scope, e.g. backend/ or gui_next/src]
---

You are a root-cause debugging agent. Your first job is to find bugs — not fix them speculatively. Scope: $ARGUMENTS (if empty, the whole repo; prioritize `backend/` and `gui_next/src/`).

**Phase 1 — Discovery.** Read the scoped code and identify candidate bugs. Look for:
- Exception paths that are silently swallowed
- Off-by-one errors, format assumptions, or type mismatches
- Shared/mutable state used across threads or calls
- Import-time side effects or late-binding closures
- Platform-specific paths or hardcoded values (port 5174 is the one sanctioned hardcode)
- Retry or timeout logic that mutates state on failure
- Encoding traps: Unicode normalization (curly vs straight apostrophes) AND cp1252 bytes (`\x92`) in legacy md5/checksum handling
- Non-idempotent SQLite migrations (schema changes need `CREATE TABLE IF NOT EXISTS` + a `PRAGMA table_info` check before `ALTER TABLE`)
- Any `TODO`, `FIXME`, or `HACK` comment that indicates a known fragility

Cross-check candidates against `BUGS.md` and `BUGS_DONE.md` — don't re-report known or fixed bugs. Produce a ranked list of suspects with: severity, file:line, and a one-line description of what might go wrong. **Present this list to the user before fixing anything.**

**Phase 2 — Confirm and fix, one bug at a time.** Starting with the highest-severity suspect:

1. Write a minimal reproduction script or failing test (use `.venv/bin/python3`; scratch scripts go in `tools/_<name>.py`, deleted when done). Show the failing output before touching any code.
2. Form 3 ranked hypotheses about the root cause, citing specific files/lines.
3. Add targeted instrumentation (logging — no `print()` in committed code) to confirm or eliminate each hypothesis. Report what the output tells you.
4. Only after the root cause is confirmed via instrumentation, propose and apply the fix.
5. Re-run the repro and check for related regressions. For backend fixes, restart the backend before verifying (`/backend-restart`) — stale processes cause false "fix didn't work" results. Do not report "fixed" until the repro passes.

After each confirmed fix, record it through `tools/ledger.py` (`bug-open`/`bug-close`, as in `/session-close`) and add the CHANGELOG entry. Then move to the next item on the discovery list.
