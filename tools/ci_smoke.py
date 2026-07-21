#!/usr/bin/env python3
"""CI/onboarding boot smoke test (TODO-261, FABLE_CI_FIXTURE.md B3).

Builds a synthetic fixture DB, boots the real Flask backend against it via
the LOSSLESSBOB_APP_ROOT override (D1), and curls the four cheap routes that
exercise real query paths (D1's verified facts). Exits non-zero on any
failure — a 500, a timeout, or an empty payload.

Runnable locally, identically to CI::

    .venv/bin/python3 tools/ci_smoke.py
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PORT = 58174  # distinct from the real dev backend's 5174, unlikely to collide
_BASE = f"http://127.0.0.1:{_PORT}"
# (path, sanity_check) — sanity_check(parsed_json) raises AssertionError on failure.
_ROUTES = [
    ("/api/onboarding/status", lambda b: b["entries_count"] > 0),
    ("/api/search?q=", lambda b: len(b) > 0),
    ("/api/library/performances", lambda b: len(b) > 0),
    ("/api/songs?q=", lambda b: len(b["songs"]) > 0),
]


def _wait_for_port(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", _PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"backend did not open port {_PORT} within {timeout}s")


def _check_route(path: str, sanity_check) -> None:
    resp = requests.get(_BASE + path, timeout=10)
    if resp.status_code != 200:
        raise AssertionError(f"{path} -> HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    try:
        ok = sanity_check(body)
    except (KeyError, TypeError) as exc:
        raise AssertionError(f"{path} -> 200 but malformed body ({exc}): {body!r:.300}") from exc
    if not ok:
        raise AssertionError(f"{path} -> 200 but sanity check failed: {body!r:.300}")
    print(f"  OK {path} -> 200")


def main() -> int:
    dest = Path(tempfile.mkdtemp(prefix="lb_ci_smoke_"))
    proc: subprocess.Popen | None = None
    try:
        print(f"Building fixture DB at {dest} ...")
        subprocess.run(
            [sys.executable, "tools/make_fixture_db.py", "--dest", str(dest)],
            cwd=str(_REPO_ROOT), check=True,
        )

        print(f"Booting backend on :{_PORT} against the fixture ...")
        env = {**os.environ, "LOSSLESSBOB_APP_ROOT": str(dest)}
        proc = subprocess.Popen(
            [sys.executable, "run_backend.py", "--port", str(_PORT)],
            cwd=str(_REPO_ROOT), env=env,
        )
        _wait_for_port()

        print("Checking routes:")
        for route, sanity_check in _ROUTES:
            _check_route(route, sanity_check)

        print("ci_smoke: PASS")
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        shutil.rmtree(dest, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
