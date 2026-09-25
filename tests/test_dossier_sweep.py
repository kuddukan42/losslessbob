"""Tests for the corpus sweep and export-drift tools (plan row C33, Phase 8).

Both tools are exercised against the committed golden fixture (the same
``tools/make_fixture_db.py --golden`` cut used by ``tests/test_dossier_golden.py``),
loaded into a temp DB via ``tools.dossier_golden.load_fixture``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from tools.dossier_golden import load_fixture
from tools.make_fixture_db import golden_dates


@pytest.fixture(scope="module")
def golden_db():
    import backend.db as _db
    import backend.paths as _paths

    saved = (_db.DB_PATH, _paths.DATA_DIR)
    tmp_dir = tempfile.mkdtemp(prefix="lbtest_sweep_")
    db_path = os.path.join(tmp_dir, "golden.db")
    _paths.DATA_DIR = Path(tmp_dir)
    _db.DB_PATH = Path(db_path)
    load_fixture(db_path)
    _db.reload_taper_aliases(db_path)
    yield db_path

    empty = os.path.join(tmp_dir, "empty.db")
    _db.reload_taper_aliases(empty)
    _db.close_connection(db_path)
    _db.close_connection(empty)
    _db.DB_PATH, _paths.DATA_DIR = saved
    shutil.rmtree(tmp_dir, ignore_errors=True)


# --- dossier_sweep ---------------------------------------------------------


def test_sweep_writes_report_and_sidecar(golden_db, tmp_path):
    from tools.dossier_sweep import run

    dates = sorted(golden_dates())
    rc = run(golden_db, None, dates, tmp_path, notify=False)
    assert rc == 0

    md_files = list(tmp_path.glob("dossier_sweep_*.md"))
    json_files = list(tmp_path.glob("dossier_sweep_*.json"))
    assert len(md_files) == 1
    assert len(json_files) == 1

    result = json.loads(json_files[0].read_text(encoding="utf-8"))
    totals = result["totals"]
    assert totals["targets"] >= len(dates)  # >= : an ambiguous date fans out
    assert totals["refused"] >= 0
    assert totals["withheld_fields"] >= 0
    assert totals["elapsed_seconds"] >= 0
    for row in result["targets"]:
        assert row["outcome"] in ("ok", "refused", "gate_error", "build_error")
    assert "# Dossier sweep" in md_files[0].read_text(encoding="utf-8")


def test_sweep_only_dates_and_limit(golden_db, tmp_path):
    from tools.dossier_sweep import sweep

    one_date = sorted(golden_dates())[:1]
    result = sweep(db_path=golden_db, only_dates=one_date)
    assert {t["date_iso"] for t in result["targets"]} == set(one_date)

    result_limit = sweep(db_path=golden_db, limit=1)
    assert len({t["date_iso"] for t in result_limit["targets"]}) <= 1


def test_deltas_rise_detection():
    from tools.dossier_sweep import ERROR_KEYS, _deltas

    prev = {k: 1 for k in ERROR_KEYS}
    higher = {k: 2 for k in ERROR_KEYS}
    same = dict(prev)
    lower = {k: 0 for k in ERROR_KEYS}

    d = _deltas(prev, higher)
    assert all(v > 0 for v in d.values())

    d_same = _deltas(prev, same)
    assert all(v == 0 for v in d_same.values())

    d_lower = _deltas(prev, lower)
    assert all(v <= 0 for v in d_lower.values())


def test_sweep_reports_night_over_night_delta(golden_db, tmp_path):
    from tools.dossier_sweep import ERROR_KEYS, run

    dates = sorted(golden_dates())[:2]
    # A previous sidecar (different, earlier stem) with deliberately low counts, so
    # the fresh run's real counts read as a rise for every ERROR_KEYS metric.
    prev_totals = {k: -1000 for k in ERROR_KEYS}
    prev_totals.update({"targets": 0, "elapsed_seconds": 0})
    (tmp_path / "dossier_sweep_2000-01-01.json").write_text(
        json.dumps({"totals": prev_totals, "targets": []}), encoding="utf-8")

    rc = run(golden_db, None, dates, tmp_path, notify=False)
    assert rc == 0
    md = next(tmp_path.glob("dossier_sweep_*.md")).read_text(encoding="utf-8")
    assert "Night-over-night" in md
    assert re.search(r"\|\s*refused\s*\|\s*\+", md)


# --- dossier_verify_export --------------------------------------------------


def _render_export(golden_db, date_iso: str):
    from backend.app import create_app

    client = create_app().test_client()
    res = client.get(f"/api/dossier/html?date={date_iso}&inline=1&link_mode=none")
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_data(as_text=True)


def test_verify_export_ok(golden_db, tmp_path):
    from tools.dossier_verify_export import verify_file

    date_iso = sorted(golden_dates())[0]
    html = _render_export(golden_db, date_iso)
    assert 'id="lb-dossier-id"' in html
    path = tmp_path / f"dossier-{date_iso}.html"
    path.write_text(html, encoding="utf-8")

    status, diffs = verify_file(path)
    assert status == "OK", diffs
    assert diffs == []


def test_verify_export_drift_on_doctored_fingerprint(golden_db, tmp_path):
    from tools.dossier_verify_export import verify_file

    date_iso = sorted(golden_dates())[0]
    html = _render_export(golden_db, date_iso)
    doctored = re.sub(r'("input_fingerprint":\s*")[0-9a-f]+"', r'\1deadbeef"', html)
    assert doctored != html, "fingerprint pattern did not match; test fixture drifted"
    path = tmp_path / f"dossier-{date_iso}-doctored.html"
    path.write_text(doctored, encoding="utf-8")

    status, diffs = verify_file(path)
    assert status == "DRIFT"
    assert any("input_fingerprint" in d for d in diffs)


def test_verify_export_unidentifiable(tmp_path):
    from tools.dossier_verify_export import verify_file

    path = tmp_path / "not_a_date.html"
    path.write_text("<html><body>no markers here</body></html>", encoding="utf-8")
    status, diffs = verify_file(path)
    assert status == "ERROR"
    assert "unidentifiable" in diffs[0]
