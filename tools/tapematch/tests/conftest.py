"""Suite-wide safety net for the tapematch tests (BUG-279).

``run_batch`` / ``run_year`` / ``run_crawl`` launch a fresh interpreter per date
rather than calling ``run_date`` in-process. Tests that patched ``run_date``
were therefore silently ineffective, and running ``pytest tests/`` spawned real
sessions: decoding audio from ``/mnt/DATA0`` and committing runs to the
production ``observations.db`` (two such runs landed on 2026-07-27 before this
was caught). It also made the suite take 11 minutes.

The autouse fixture below replaces ``tapematch_session._spawn`` — the one seam
all three drivers go through — with a stub that fails the test loudly. A test
that legitimately exercises a driver must patch ``_spawn`` itself with an
explicit fake; that patch wins because it is applied after this fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_session_spawns(monkeypatch):
    """Make any unpatched per-date session spawn fail instead of running."""

    def _forbidden(cmd):
        raise AssertionError(
            "A test tried to spawn a real tapematch session "
            f"({' '.join(map(str, cmd))}). Patch tapematch_session._spawn in "
            "the test itself — see BUG-279."
        )

    monkeypatch.setattr(sess, "_spawn", _forbidden)
