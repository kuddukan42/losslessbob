"""POST /api/pipeline/file/start: the per-request ``file_mode`` override (tools/lb_nc.py).

start_file_job is monkeypatched, so nothing on disk is touched.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import backend.db as db
import backend.filer as filer
import backend.paths as _paths


@pytest.fixture
def client(monkeypatch):
    tmp_dir = tempfile.mkdtemp(prefix="lb_file_mode_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(_paths, "DB_PATH", db_path)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    from backend.app import create_app
    return create_app().test_client()


@pytest.fixture
def calls(monkeypatch):
    seen: list[dict] = []

    def fake_start(lb, path, file_mode="move", mount_id_override=None, xref=0, db_path=None):
        seen.append({"lb": lb, "file_mode": file_mode, "mount_id": mount_id_override})
        return {"ok": True}
    monkeypatch.setattr(filer, "start_file_job", fake_start)
    return seen


def _post(client, **extra):
    body = {"folders": [{"path": "/x/y (LB-00001)", "lb_number": 1}], **extra}
    return client.post("/api/pipeline/file/start", json=body)


def test_default_follows_setting(client, calls):
    db.set_meta("pipeline_file_mode", "copy")
    assert _post(client).get_json()["ok"] is True
    assert calls[-1]["file_mode"] == "copy"


def test_body_overrides_setting(client, calls):
    db.set_meta("pipeline_file_mode", "copy")
    _post(client, file_mode="move")
    assert calls[-1]["file_mode"] == "move"


def test_bad_file_mode_rejected(client, calls):
    resp = _post(client, file_mode="delete")
    assert resp.status_code == 400
    assert resp.get_json()["error_code"] == "bad_input"
    assert calls == []
