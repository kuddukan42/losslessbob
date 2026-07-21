"""Tests for LOSSLESSBOB_APP_ROOT env override (backend/paths.py::_app_root()).

Part of the CI fixture spec (instructions/FABLE_CI_FIXTURE.md, D1) — this is the
single switch that lets CI/cloud agents point the whole backend at a throwaway
data dir. Since APP_ROOT is computed once at import time, the override must be
verified via a subprocess so the env var is read before backend.paths is
imported for the first time.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_PRINT_DB_PATH = "from backend import paths; print(paths.DB_PATH)"


def test_env_override_redirects_app_root(tmp_path: Path) -> None:
    """Setting LOSSLESSBOB_APP_ROOT points APP_ROOT/DATA_DIR/DB_PATH at it."""
    override = tmp_path / "fixture_root"
    env = dict(os.environ, LOSSLESSBOB_APP_ROOT=str(override))
    proc = subprocess.run(
        [sys.executable, "-c", _PRINT_DB_PATH],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    printed = Path(proc.stdout.strip())
    assert printed == override / "data" / "losslessbob.db"


def test_default_app_root_unchanged_when_unset() -> None:
    """With the env var unset, APP_ROOT still resolves to the repo root."""
    env = dict(os.environ)
    env.pop("LOSSLESSBOB_APP_ROOT", None)
    proc = subprocess.run(
        [sys.executable, "-c", _PRINT_DB_PATH],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    printed = Path(proc.stdout.strip())
    assert printed == _REPO_ROOT / "data" / "losslessbob.db"
