# Analyze Runs (Parallel)

Spawn one Claude subagent per run directory under `tools/tapematch/runs/`, each writing an `analysis.md` into its run folder summarizing matches, false positives, and threshold issues.

## Steps

1. List all subdirectories under `tools/tapematch/runs/` (each is a dated run).
2. For each run directory, launch a background Claude subagent:
   ```bash
   for date in $(ls tools/tapematch/runs/); do
     claude -p "Analyze tools/tapematch/runs/$date logs and write tools/tapematch/runs/$date/analysis.md summarizing: total matches, false positives (flag criteria), threshold issues, and any anomalies. Be concise." \
       --allowedTools "Read,Write,Bash" &
   done
   wait
   ```
3. After all agents finish, read each `analysis.md` and produce a roll-up summary in the chat: a markdown table with columns `Run | Matches | False Positives | Threshold Issues | Notes`.
4. If any run directory is missing logs or produced an error, flag it explicitly.

## Notes
- Run from repo root so paths resolve correctly.
- Each agent writes only its own `analysis.md` — no cross-run writes.
- Do not overwrite an existing `analysis.md` unless the user passes `--force`.
