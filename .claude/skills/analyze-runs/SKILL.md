---
name: analyze-runs
description: Roll up existing tapematch analysis.md verdicts across data/tapematch/runs/ into a summary table. Read-only — to WRITE missing analyses, use /tapematch-batch instead.
---

# Analyze Runs (Roll-up)

Aggregate the per-run `analysis.md` files under `data/tapematch/runs/` into one
summary so cross-run patterns (repeat false positives, threshold drift, runs
flagged for review) become visible.

> Superseded note: this skill previously spawned one `claude -p` subagent per
> run to *write* analyses. That approach was abandoned — subagents hit a hard
> `Write`-tool block on `.md` files. Writing analyses now happens in-session
> via `/tapematch-batch`. This skill only reads and summarizes.

## Steps

1. Collect all existing analyses:
   ```bash
   find data/tapematch/runs -maxdepth 2 -name "analysis.md" | sort
   ```
2. Read each `analysis.md` (they are short; batch the reads) and extract:
   verdict outcome, whether it was flagged "needs review", and any anomaly
   callouts (data splicing, ingest crashes, date-mis-tagged LBs).
3. Produce a roll-up in chat: a markdown table
   `Run | Verdict | Flagged? | Notes`, followed by a short prose paragraph on
   cross-run patterns worth acting on.
4. Report coverage: how many run dirs have `report.md` but no `analysis.md`
   yet (these are `/tapematch-batch`'s backlog), and how many were skipped as
   incomplete sets.

## Notes

- Run from repo root so paths resolve.
- Read-only: never create, edit, or delete anything in the run dirs.
- If a specific date or date range is passed as an argument, restrict the
  roll-up to matching run dirs (dir names are `YYYYMMDD_HHMMSS_<concert-date>`).
