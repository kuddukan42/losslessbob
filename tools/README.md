# tools/

Most scripts here are wired into something: a skill, a cron or systemd job
(`SCHEDULED_JOBS.md`), the backend, or another tool. This page covers the
standalone ones that nothing else calls, so a reference count of zero doesn't
mark them as dead. Each one documents its full usage in its own docstring.

Run everything from the project root with `.venv/bin/python3`.

| Tool | What it's for | When to reach for it |
|---|---|---|
| `wtrf/wtrf_board_archive.py` | Crawls a WTRF board into `data/wtrf_board.db` for local search (`fetch`, `search`, `show`). Throttled, uses the app's keyring login. | Searching old board posts offline. Unlike `backend/wtrf_board.py`, which seeds the posts the collection already holds, this archives every post. |
| `wtrf_repair_extras.py` | Re-materialises the incomplete files of tagged WTRF seed overlays from local sources, then rechecks them in qBittorrent. Dry-run by default, `--apply` to write. | After `wtrf_tag_incomplete.py` tags overlays `missing extras` / `missing music`. |
| `wtrf_requeue_disk_full.py` | Takes a seed-walk log, finds the overlays it left half-built on a full drive (ENOSPC), removes them and requeues their topics. Dry-run by default. | Whenever a seed walk runs a drive out of space (BUG-364). |
| `tapematch/todo324_scan.py` | Rebuilds `tapematch/todo324_recheck_queue.tsv`, which lists the analysis verdicts that quote a speed-unknown `[DISTINCT SOURCE]` line. Read-only. | Working on TODO-324. Archive both files once it closes. |
| `tapematch/mem_monitor.py` | `mem_monitor.py <cmd...>` runs a command, samples its RSS every 0.5 s, prints a peak/timeline summary and appends it to `tapematch/last_run.log`. | Profiling the memory use of a tapematch run. |

Finished one-shots go to `archive/tools-throwaway/` (see `archive/README.md`),
not into this table.
