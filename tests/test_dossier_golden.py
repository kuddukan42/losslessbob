"""Golden-set harness for the show dossier (plan rows C31/C32, audit Q3).

Every ``tests/golden/dossier/*.json`` spec is built against the committed
fixture cut from live data (``tools/make_fixture_db.py --golden``). A spec with
``expected: null`` is a placeholder: it must still build, unambiguously, with
every anchor present. Once tj has verified a spec by hand (C32) its
``expected`` snapshot is pinned and any diff fails; changing a golden file
needs a note in the same commit.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from tools.dossier_golden import build_snapshot, first_diffs, golden_specs, load_fixture
from tools.make_fixture_db import GOLDEN_FIXTURE

_SPECS = golden_specs()


@pytest.fixture(scope="module")
def golden_db():
    import backend.db as _db
    import backend.paths as _paths

    saved = (_db.DB_PATH, _paths.DATA_DIR)
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_golden_")
    db_path = os.path.join(tmp_dir, "golden.db")
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)
    load_fixture(db_path)
    _db.reload_taper_aliases(db_path)
    yield db_path

    # Put the alias tables back to builtin-only so later tests see no curated tapers.
    empty = os.path.join(tmp_dir, "empty.db")
    _db.reload_taper_aliases(empty)
    _db.close_connection(db_path)
    _db.close_connection(empty)
    _db.DB_PATH, _paths.DATA_DIR = saved
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_specs_are_well_formed():
    assert len(_SPECS) == 16
    assert GOLDEN_FIXTURE.exists()
    for path, spec in _SPECS:
        assert path.stem.startswith(spec["date"]), path.name
        assert spec.get("channel") in ("public", "full"), path.name
        # A pinned snapshot must name who verified it; a placeholder must not.
        assert (spec.get("expected") is None) == (spec.get("verified_by") is None), path.name


@pytest.mark.parametrize("spec", [s for _, s in _SPECS], ids=[p.stem for p, _ in _SPECS])
def test_golden_dossier(golden_db, spec):
    from backend.dossier_anchors import ANCHORS

    snap = build_snapshot(spec, golden_db)
    if snap.get("reason") == "show":
        # A two-show day with no show named (TODO-345): every candidate must build.
        assert len(snap["candidates"]) >= 2
        for cand in snap["candidates"]:
            each = build_snapshot(spec, golden_db, show=cand["show"])
            assert not each.get("ambiguous"), cand
            assert set(each["fields"]) == {k for k in ANCHORS if "[]." not in k}
    else:
        assert not snap.get("ambiguous"), f"{spec['date']} needs a location"
        # Scalar anchors live in view.fields; "x[].y" row anchors in view.rows.
        assert set(snap["fields"]) == {k for k in ANCHORS if "[]." not in k}
    if spec.get("expected") is None:
        return
    diffs = first_diffs(spec["expected"], snap)
    assert not diffs, "golden diff:\n" + "\n".join(diffs)
