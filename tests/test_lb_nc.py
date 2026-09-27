"""Tests for tools/lb_nc.py — the two-pane collection commander, driven over FakeApi."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import lb_nc  # noqa: E402

MISFILED = "1987-10-17 London, England (LB-01860)"
TORONTO = "1975-11-19 Toronto, Canada (LB-04410)"
PRAGUE = "1995-03-01 Prague, Czech Republic (LB-05555)"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "POLL", 0)
    api = lb_nc.build_fixture(tmp_path)
    return lb_nc.App(api, threaded=False, size_cache=None, persist=False)


def _pick(pane: lb_nc.Pane, name: str) -> None:
    pane.cursor = [e.name for e in pane.visible()].index(name)


def _statuses(pane: lb_nc.Pane) -> dict[str, str]:
    return {e.name: e.status for e in pane.entries if e.lb is not None}


def test_classify_every_status(app, tmp_path):
    assert _statuses(app.left) == {
        "1966-05-17 Manchester, England (LB-00123)": "canonical",
        TORONTO: "canonical",
        MISFILED: "misfiled",
        PRAGUE: "stray",
    }
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    assert _statuses(app.right) == {
        "1987-09-05 Tel Aviv, Israel (LB-02311)": "canonical",
        "1987-10-05 Verona, Italy (LB-07777)": "stray",
        "1975-11-19 Toronto, Canada (LB-04410)-copy": "dup",
        "1975-11-19 Toronto (LB-04410) alt": "dup",
    }


def test_expected_parent_joins_sub_path(app, tmp_path):
    assert app.coll.expected_parent(1987) == lb_nc.norm(tmp_path / "DYLAN2" / "1987")
    assert app.coll.expected_parent(1966) == lb_nc.norm(tmp_path / "DYLAN1")
    assert app.coll.expected_parent(1950) is None


def test_file_misfiled_moves_to_route(app, tmp_path):
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert isinstance(app.dialog, lb_nc.Confirm)
    assert len(app.dialog.jobs) == 1
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / "1987" / MISFILED).is_dir()
    assert not (tmp_path / "DYLAN1" / MISFILED).exists()
    start = next(b for p, b in app.api.calls if p == "/api/pipeline/file/start")
    assert start["file_mode"] == "move"            # a registered folder never copies
    assert "mount_id" not in start["folders"][0]
    assert app.coll.misfiled() == []


def test_file_skips_canonical_and_dup(app, tmp_path):
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    app.active = app.right
    app.handle("+")
    app.handle("f7")
    jobs = app.dialog.jobs
    assert [j.label for j in jobs] == ["register LB-07777"]  # in-place stray: register only
    text = "\n".join(app.dialog.blurb)
    assert "already canonical" in text
    assert "collection has LB-04410" in text


def test_move_to_other_mount_with_reroute(app, tmp_path):
    _pick(app.left, TORONTO)
    app.handle("f6")                                 # right pane shows DYLAN2
    dialog = app.dialog
    assert isinstance(dialog, lb_nc.Confirm)
    assert [j.label for j in dialog.jobs] == ["move LB-04410"]
    app.handle("r")
    assert [j.label for j in dialog.jobs] == ["move LB-04410", "route 1975"]
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / TORONTO).is_dir()
    assert app.coll.routes[1975]["mount_id"] == 2
    row = app.coll.by_lb[4410]
    assert app.coll.row_status(row)[0] == "canonical"


def test_move_without_reroute_leaves_it_misfiled(app, tmp_path):
    _pick(app.left, TORONTO)
    app.handle("f6")
    app.handle("y")
    app.tick()
    assert app.coll.row_status(app.coll.by_lb[4410])[0] == "misfiled"
    app.dialog = None
    app.active = app.left
    app.handle("f8")
    assert sorted(e.lb for e in app.left.entries) == [1860, 4410]


def test_file_out_of_place_stray_registers_it(app, tmp_path):
    _pick(app.left, PRAGUE)
    app.handle("f7")
    assert [j.label for j in app.dialog.jobs] == ["file LB-05555"]
    app.handle("y")
    app.tick()
    start = next(b for p, b in app.api.calls if p == "/api/pipeline/file/start")
    assert "file_mode" not in start                  # strays follow the pipeline setting
    assert (tmp_path / "DYLAN2" / "1995" / PRAGUE).is_dir()
    assert app.coll.row_status(app.coll.by_lb[5555])[0] == "canonical"


def test_register_in_place_stray(app, tmp_path):
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    app.active = app.right
    _pick(app.right, "1987-10-05 Verona, Italy (LB-07777)")
    app.handle("f7")
    app.handle("y")
    app.tick()
    assert app.coll.row_status(app.coll.by_lb[7777])[0] == "canonical"


def test_move_refuses_virtual_target(app):
    app.active = app.right
    app.handle("f8")                                 # right pane -> misfiled view
    app.active = app.left
    _pick(app.left, TORONTO)
    app.handle("f6")
    assert isinstance(app.dialog, lb_nc.Message)


def test_read_only_gates_writes(tmp_path, monkeypatch):
    api = lb_nc.build_fixture(tmp_path)
    app = lb_nc.App(api, read_only=True, threaded=False, size_cache=None, persist=False)
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert isinstance(app.dialog, lb_nc.Message)
    assert not any(p == "/api/pipeline/file/start" for p, _ in api.calls)


def test_backend_down_still_browses(tmp_path):
    (tmp_path / "x (LB-00001)").mkdir()

    class Down(lb_nc.Api):
        def _call(self, method, path, body=None):
            raise lb_nc.ApiError("backend unreachable")

    app = lb_nc.App(Down(), left=tmp_path, right=tmp_path, threaded=False,
                    size_cache=None, persist=False)
    assert [e.name for e in app.left.entries] == ["..", "x (LB-00001)"]
    screen = "\n".join(lb_nc.plain(line) for line in app.frame(100, 24))
    assert "backend unreachable" in screen


@pytest.mark.parametrize("cols", [110, 70, 45])
def test_frame_is_exact_width(app, cols):
    for line in app.frame(cols, 24):
        assert lb_nc.line_width(line) == cols
    app.handle("f7")
    for line in app.frame(cols, 24):
        assert lb_nc.line_width(line) == cols


def test_decode_keys():
    assert lb_nc.decode(b"\x1b[17~\x1b[18~\t ") == ["f6", "f7", "tab", " "]
    assert lb_nc.decode(b"\x1bOP") == ["f1"]
    assert lb_nc.decode(b"\x15") == ["ctrl-u"]


def test_same_drive_move_needs_no_space(app):
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert any("same-drive" in line for line in app.dialog.blurb)


def test_cross_drive_move_refused_when_it_wont_fit(app, monkeypatch):
    monkeypatch.setattr(lb_nc, "same_device", lambda a, b: False)
    monkeypatch.setattr(app, "usage", lambda path, fresh=False: (3 * 1024 ** 3, 10 ** 13))
    monkeypatch.setattr(lb_nc, "SPACE_RESERVE", 3 * 1024 ** 3)   # 1K folder tips it over
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert isinstance(app.dialog, lb_nc.Message)
    assert "not enough space" in app.dialog.title
    assert any("WON'T FIT" in line for line in app.dialog.text)


def test_cross_drive_move_shows_space_after(app, monkeypatch):
    monkeypatch.setattr(lb_nc, "same_device", lambda a, b: False)
    monkeypatch.setattr(app, "usage", lambda path, fresh=False: (500 * 1024 ** 3, 10 ** 13))
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert isinstance(app.dialog, lb_nc.Confirm)
    assert any("DYLAN2: needs 1.0K of 500G free" in line for line in app.dialog.blurb)


def test_drives_line_lists_every_mount(app):
    screen = "\n".join(lb_nc.plain(line) for line in app.frame(120, 30))
    assert "drives: DYLAN1" in screen and "DYLAN2" in screen


def test_generate_checksums_skips_folders_that_have_them(app, tmp_path):
    folder = tmp_path / "DYLAN1" / TORONTO
    (folder / "x.md5").write_text("")
    app.handle("+")
    app.handle("c")
    labels = [j.detail for j in app.dialog.jobs]
    assert all(TORONTO not in d for d in labels) and len(labels) == 3
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / MISFILED / "_mychecksums.ffp").is_file()


def test_rename_uses_pipeline_proposal(app, tmp_path):
    old = tmp_path / "DYLAN1" / TORONTO
    app.pipeline_results[str(old)] = {"rename": {"proposed": "1975-11-19 Toronto (LB-04410)"}}
    _pick(app.left, TORONTO)
    app.handle("r")
    assert [j.label for j in app.dialog.jobs] == ["rename"]
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / "1975-11-19 Toronto (LB-04410)").is_dir()
    assert app.coll.by_lb[4410]["folder_name"] == "1975-11-19 Toronto (LB-04410)"
    assert app.pipeline_results == {}


def test_rename_without_pipeline_result_is_skipped(app):
    _pick(app.left, TORONTO)
    app.handle("r")
    assert isinstance(app.dialog, lb_nc.Message)
    assert any("F4 it first" in line for line in app.dialog.text)
