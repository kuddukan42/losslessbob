# tools/tapematch — TapeMatch conventions

- Read before working here: `WORKFLOW.md` (pipeline + commands). For calibration
  work, `CALIBRATION_PROGRESS.md` is the state file — read it first, update it after.
- Thresholds/config: `config.yaml`. Don't change shipped thresholds without a
  calibration sweep documented in CALIBRATION_PROGRESS.md.
- Run outputs (results, logs, reports) live in `data/tapematch/runs/` at repo root.
- **Never run live tapematch sessions concurrently** — they share caches and the DB.
- Batch analysis writing: `/tapematch-batch` — complete sets only (DB entries ==
  files found on disk), batch size 5, skip incomplete runs. Read-only roll-up:
  `/analyze-runs`.
- Library crawl (detached, single-instance): `crawl_start.sh` / `crawl_stop.sh` /
  `crawl_status.sh`; log at `data/tapematch/crawl.log`. Wraps `run_crawl.sh`.
- Before `/tapematch-batch`, run `triage_analysis.py --apply` — it auto-writes
  analysis.md for trivially clean runs (all-distinct, clean diagnostics, no in-set
  commentary pair notes) and leaves everything needing judgment for the batch.
