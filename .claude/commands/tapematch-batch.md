---
description: Write the next batch of missing tapematch analysis.md files (complete sets only), then sync families to the app DB
argument-hint: [batch size, default 5]
---

Process the next batch of missing tapematch `analysis.md` write-ups.

Subagents **are** usable for the writing step — the old claim that they hit a hard
`Write`-tool block on `.md` files was wrong (the only `PreToolUse` hook in
`.claude/settings.json` is a path guard for writes outside the project root). Use them
to run the batch on a cheaper model than the orchestrating session. The real constraint
is `next_batch.py`: it is stateless and only ever reports dirs lacking `analysis.md`, so
concurrent agents each calling it get handed the **same** dirs. To fan out, the parent
session must do steps 1–2 once, partition the dirs into disjoint per-agent lists, and
forbid the agents from calling `next_batch.py` / `prep_analysis_input.py` themselves.

Batch size: $ARGUMENTS (number of run dirs this invocation). If empty, default to **5**.

## Steps

1. Pick the batch's run dirs:
   ```bash
   .venv/bin/python3 tools/tapematch/next_batch.py 5   # arg = batch size
   ```
   This applies the eligibility rule — has `report.md`, no `analysis.md`, **complete set** (tapematch actually ran, `=== CLUSTERS ===` present, and every DB entry was found on disk) — and orders what's left by `backend.tapematch_autoflag`'s machine triage: `attention` dates first, most rules fired first, then fewest entries first. Incomplete runs lack comparative data and yield no actionable verdict; the script skips them and they get re-picked when secondary sources appear.

   The printed `attention` / `N rules` columns are a **prioritisation hint, not a verdict** — the rules run at ~0.19 precision against human judgment. Don't let them pre-bias the analysis: a 3-rule `attention` date can still be entirely clean, and a `clear` date can still need review. Write what the report and info files actually support.
2. Build input bundles for those dirs:
   ```bash
   .venv/bin/python3 tools/tapematch/prep_analysis_input.py <dir1> <dir2> ...
   ```
   This writes `analysis_input.md` into each dir (report.md + matched `data/site/files/LBF-*.txt` lineage prose, checksum noise stripped).
3. For each dir, **read its own `analysis_input.md`** and write `analysis.md` directly with the Write tool, following `tools/tapematch/ANALYSIS_WRITER_PROMPT.md` exactly (format, verdict wording rules, per-LB note/callout conventions). Then delete `analysis_input.md`. One dir at a time — either in this session, or fanned out to subagents holding disjoint dir lists as described above.
4. In the attribution line `*Claude <model-id> — YYYY-MM-DD*`, use **the model that actually wrote the file** — the orchestrator's id when written in-session, the subagent's id when fanned out — do **not** hardcode a fixed id — and today's actual date. The attribution must record who really wrote the file; a wrong id makes later quality audits by model impossible.
5. Apply real judgment, not a template fill: cross-check the report's CLUSTERS/DIAGNOSTICS against each LB's own info-file commentary, flag genuine contradictions as "needs review" (with the specific reason), and don't force a clean verdict when the data doesn't support one. Past runs have caught real bugs this way (a report.md with another session's data spliced in, a tapematch ingest crash, a likely date-mis-tagged LB number) — stay alert for that class of issue, not just source-identity calls.
6. When the batch is done, print a short summary table: `Run dir | Verdict outcome | Flagged for review?`. Then report backlog counts via `.venv/bin/python3 tools/tapematch/next_batch.py --stats` (eligible complete-set dirs remaining, split attention/clear), so progress is visible across sessions.
7. Sync the batch's family clusters into the main app DB:
   ```bash
   .venv/bin/python3 -m backend.tapematch_sync
   ```
   Report the returned stats (`dates_processed`/`families_written`/`recordings_linked`/`errors`). This is what makes `recording_families`/`tapematch_family_meta` (and `GET /api/tapematch/families`) reflect the batch just processed — it does not run automatically.
