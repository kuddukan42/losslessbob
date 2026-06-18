Process the next batch of missing tapematch `analysis.md` write-ups, directly in this session (no subagents — they hit a hard `Write`-tool block on `.md` files and cost about the same per file anyway).

Batch size: $ARGUMENTS (a number of run dirs to process this invocation). If empty, default to 25.

## Steps

1. List run dirs under `data/tapematch/runs/` that have `report.md` but no `analysis.md` yet:
   ```bash
   find data/tapematch/runs -maxdepth 2 -name "report.md" -printf "%h\n" | sort | while read d; do
     [ -f "$d/analysis.md" ] || echo "$d"
   done
   ```
2. Take the first N of those (N = the batch size above) and build their input bundles:
   ```bash
   .venv/bin/python3 tools/tapematch/prep_analysis_input.py <dir1> <dir2> ...
   ```
   This writes `analysis_input.md` into each dir (report.md + matched `data/site/files/LBF-*.txt` lineage prose, checksum noise stripped).
3. For each dir, **read its own `analysis_input.md`** and write `analysis.md` directly with the Write tool, following `tools/tapematch/ANALYSIS_WRITER_PROMPT.md` exactly (format, verdict wording rules, per-LB note/callout conventions). Then delete `analysis_input.md`. Do this one dir at a time in this session — don't spawn Task/Agent subagents for the writing step.
4. Use today's actual date in the `*Claude claude-sonnet-4-6 — YYYY-MM-DD*` attribution line.
5. Apply real judgment, not a template fill: cross-check the report's CLUSTERS/DIAGNOSTICS against each LB's own info-file commentary, flag genuine contradictions as "needs review" (with the specific reason), and don't force a clean verdict when the data doesn't support one. Past runs have caught real bugs this way (a report.md with another session's data spliced in, a tapematch ingest crash, a likely date-mis-tagged LB number) — stay alert for that class of issue, not just source-identity calls.
6. When the batch is done, print a short summary table: `Run dir | Verdict outcome | Flagged for review?`. Then report how many missing run dirs remain (re-run step 1's count) so progress is visible across sessions.
7. Sync the batch's family clusters into the main app DB:
   ```bash
   .venv/bin/python3 -m backend.tapematch_sync
   ```
   Report the returned stats (`dates_processed`/`families_written`/`recordings_linked`/`errors`). This is what makes `recording_families`/`tapematch_family_meta` (and `GET /api/tapematch/families`) reflect the batch just processed — it does not run automatically.
