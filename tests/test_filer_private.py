"""Tests for backend.filer's private_collection_path routing of private LBs."""

from __future__ import annotations

import pytest

import backend.filer as filer


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A private folder on a drive, with meta/status/entry lookups stubbed."""
    drive = tmp_path / "DYLAN2"
    private = drive / "LB-Private"
    private.mkdir(parents=True)
    state = {"meta": str(private) + "/", "status": "private"}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            class _R:
                @staticmethod
                def fetchall():
                    return [{"id": 7, "label": "DYLAN2", "root_path": str(drive / "Concerts")}]
            return _R()

    monkeypatch.setattr(filer.database, "get_meta", lambda k, db_path=None: state["meta"])
    monkeypatch.setattr(filer.database, "get_lb_status", lambda lb, db_path=None: state["status"])
    monkeypatch.setattr(filer.database, "get_entry",
                        lambda lb, db_path=None: {"entry": {"date_str": "6/15/78"}})
    monkeypatch.setattr(filer.database, "get_connection", lambda db_path=None: _Conn())
    return private, state


def test_private_lb_files_flat_into_private_path(env, tmp_path):
    private, _ = env
    res = filer.resolve_destination_for_lb(3003, str(tmp_path / "x (LB-03003)"))
    assert res["ok"] and res["private"]
    assert res["dest"] == str(private / "x (LB-03003)")
    assert res["dest_parent"] == str(private)
    assert (res["mount_id"], res["year"]) == (7, 1978)


def test_private_path_dest_exists(env, tmp_path):
    private, _ = env
    (private / "x (LB-03003)").mkdir()
    res = filer.resolve_destination_for_lb(3003, str(tmp_path / "x (LB-03003)"))
    assert res["error_code"] == "dest_exists"


def test_private_path_offline(env, tmp_path, monkeypatch):
    monkeypatch.setattr(filer, "_path_reachable", lambda p: False)
    res = filer.resolve_destination_for_lb(3003, str(tmp_path / "x (LB-03003)"))
    assert res["error_code"] == "mount_offline"


@pytest.mark.parametrize("change", [{"status": "public"}, {"meta": ""}, {"override": 1}])
def test_year_route_used_otherwise(env, tmp_path, monkeypatch, change):
    _, state = env
    state.update({k: v for k, v in change.items() if k != "override"})
    called = []
    monkeypatch.setattr(filer, "_private_destination",
                        lambda *a, **k: called.append(a) or {"ok": True})
    monkeypatch.setattr(filer.database, "get_collection_route", lambda *a, **k: None,
                        raising=False)
    filer.resolve_destination_for_lb(3003, str(tmp_path / "x (LB-03003)"),
                                     mount_id_override=change.get("override"))
    assert called == []
