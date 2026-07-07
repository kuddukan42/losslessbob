---
description: Write the next batch of missing tapematch analysis.md files (complete sets only), then sync families to the app DB
argument-hint: [batch size, default 5]
---

Process the next batch of missing tapematch `analysis.md` write-ups, directly in this session (no subagents — they hit a hard `Write`-tool block on `.md` files and cost about the same per file anyway).

Batch size: $ARGUMENTS (number of run dirs this invocation). If empty, default to **5**.

## Steps

1. List eligible run dirs under `data/tapematch/runs/`: has `report.md`, no `analysis.md`, **and is a complete set** — tapematch actually ran (`=== CLUSTERS ===` present) and every DB entry was found on disk. Incomplete runs lack comparative data and yield no actionable verdict; skip them and return to them when secondary sources appear.

   Note: `DB entries:` and `Found on disk:` are on the **same** line (`DB entries: **9** | Found on disk: **9**`) — do not grep them as separate lines.
   ```bash
   find data/tapematch/runs -maxdepth 2 -name "report.md" | sort | while read report; do
     dir=$(dirname "$report")
     if [ ! -f "$dir/analysis.md" ]; then
       if grep -q "^=== CLUSTERS ===" "$report" 2>/dev/null; then
         line=$(grep "^DB entries:" "$report")
         db_entries=$(echo "$line" | grep -o "DB entries: \*\*[0-9]*\*\*" | grep -o "[0-9]*")
         found_disk=$(echo "$line" | grep -o "Found on disk: \*\*[0-9]*\*\*" | grep -o "[0-9]*")
         if [ "$db_entries" = "$found_disk" ] && [ -n "$db_entries" ]; then
           echo "$dir"
         fi
       fi
     fi
   done | head -5   # head -N = batch size
   ```
2. Build input bundles for those dirs:
   ```bash
   .venv/bin/python3 tools/tapematch/prep_analysis_input.py <dir1> <dir2> ...
   ```
   This writes `analysis_input.md` into each dir (report.md + matched `data/site/files/LBF-*.txt` lineage prose, checksum noise stripped).
3. For each dir, **read its own `analysis_input.md`** and write `analysis.md` directly with the Write tool, following `tools/tapematch/ANALYSIS_WRITER_PROMPT.md` exactly (format, verdict wording rules, per-LB note/callout conventions). Then delete `analysis_input.md`. One dir at a time, in this session — don't spawn Task/Agent subagents for the writing step.
4. In the attribution line `*Claude <model-id> — YYYY-MM-DD*`, use **the model actually running this session** (your own model id) — do **not** hardcode a fixed id — and today's actual date. The attribution must record who really wrote the file; a wrong id makes later quality audits by model impossible.
5. Apply real judgment, not a template fill: cross-check the report's CLUSTERS/DIAGNOSTICS against each LB's own info-file commentary, flag genuine contradictions as "needs review" (with the specific reason), and don't force a clean verdict when the data doesn't support one. Past runs have caught real bugs this way (a report.md with another session's data spliced in, a tapematch ingest crash, a likely date-mis-tagged LB number) — stay alert for that class of issue, not just source-identity calls.
6. When the batch is done, print a short summary table: `Run dir | Verdict outcome | Flagged for review?`. Then report backlog counts (re-run step 1 without `head`): eligible complete-set dirs remaining, and separately how many were skipped as incomplete, so progress is visible across sessions.
7. Sync the batch's family clusters into the main app DB:
   ```bash
   .venv/bin/python3 -m backend.tapematch_sync
   ```
   Report the returned stats (`dates_processed`/`families_written`/`recordings_linked`/`errors`). This is what makes `recording_families`/`tapematch_family_meta` (and `GET /api/tapematch/families`) reflect the batch just processed — it does not run automatically.
