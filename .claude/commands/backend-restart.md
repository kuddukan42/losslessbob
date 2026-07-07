---
description: Fully restart the Flask backend on port 5174 so it runs the latest code, then verify freshness via uptime + status
---

# backend-restart — Restart Flask backend with latest code

Kills the running backend process and relaunches it, then proves the new
process is up. Use after any `backend/` code change — stale processes are the
repo's #1 source of false "fix didn't work" results.

**Why kill + relaunch:** `POST /api/admin/restart` only truly reloads code
(`os.execv`) when the backend was started directly. Under `run_backend.py`
(both standalone and Electron-dev — Electron spawns
`.venv/bin/python3 run_backend.py`), the registered callback merely recycles
the werkzeug server inside the same Python process; already-imported modules
are **not** reloaded. A full process restart is the only reliable way to pick
up code changes.

## Steps

1. Syntax-check any files changed this session first — don't relaunch into a
   crash loop:
   ```bash
   .venv/bin/python3 -m py_compile backend/<changed_file>.py
   ```
2. Find the running backend:
   ```bash
   pgrep -af "run_backend.py|LosslessBobBackend"
   ```
   If nothing is found, skip to step 4 (just start it).
3. Kill it gracefully (SIGTERM, then SIGKILL only if still alive after ~3 s):
   ```bash
   pkill -f run_backend.py; sleep 3; pkill -9 -f run_backend.py 2>/dev/null
   ```
   If the backend was spawned by a running Electron GUI that's fine — the GUI
   talks to port 5174 and will use the replacement process transparently.
4. Relaunch in the background from repo root:
   ```bash
   nohup .venv/bin/python3 run_backend.py > data/logs/backend_stdout.log 2>&1 &
   ```
5. Verify the new process (poll up to ~10 s for startup):
   ```bash
   curl -s http://127.0.0.1:5174/api/system/uptime
   curl -s http://127.0.0.1:5174/api/status | head -c 200
   ```
   PASS = uptime is a few seconds (proves it's the new process, not a
   survivor) and `/api/status` returns stats, not an error. If the port never
   comes up, read the tail of `data/logs/backend_stdout.log` and report the
   traceback — do not retry blindly.

## Notes

- Port 5174 is the sanctioned hardcode; never start on another port.
- Packaged builds run `LosslessBobBackend` (PyInstaller) — this skill targets
  dev, where the process is `run_backend.py`.
