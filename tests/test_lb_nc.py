"""Tests for tools/lb_nc.py — the two-pane collection commander, driven over FakeApi."""

import shutil
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import lb_nc  # noqa: E402

MISFILED = "1987-10-17 London, England (LB-01860)"
TORONTO = "1975-11-19 Toronto, Canada (LB-04410)"
PRAGUE = "1995-03-01 Prague, Czech Republic (LB-05555)"
TOKYO = "1978-06-15 Tokyo, Japan (LB-03003)"
TEL_AVIV = "1987-09-05 Tel Aviv, Israel (LB-02311)"
LEGACY = "bd1966-05-26 LB-321 London"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "POLL", 0)
    api = lb_nc.build_fixture(tmp_path)
    return lb_nc.App(api, threaded=False, size_cache=None, persist=False, journal_path=None)


def _pick(pane: lb_nc.Pane, name: str) -> None:
    pane.cursor = [e.name for e in pane.visible()].index(name)


def _statuses(pane: lb_nc.Pane) -> dict[str, str]:
    return {e.name: e.status for e in pane.entries if e.lb is not None}


def test_classify_every_status(app, tmp_path):
    assert _statuses(app.left) == {
        "1966-05-17 Manchester, England (LB-00123)": "canonical",
        TORONTO: "canonical",
        TOKYO: "canonical",
        LEGACY: "canonical",
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
    assert [r["lb_number"] for r in app.coll.misfiled()] == [8002]   # public-in-private


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
    assert sorted(e.lb for e in app.left.entries) == [1860, 4410, 8002]


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
    app = lb_nc.App(api, read_only=True, threaded=False, size_cache=None, persist=False, journal_path=None)
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
                    size_cache=None, persist=False, journal_path=None)
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
    assert all(TORONTO not in d for d in labels) and len(labels) == 5
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


PRIVATE = ("PRIVATE LB", "Batch A")


def test_private_lb_in_private_area_is_canonical(app):
    status, note = app.coll.row_status(app.coll.by_lb[8001])
    assert (status, note) == ("canonical", lb_nc.PRIVATE_AREA)


def test_public_lb_in_private_area_is_flagged_and_listed(app, tmp_path):
    status, note = app.coll.row_status(app.coll.by_lb[8002])
    assert status == "public"
    assert note == lb_nc.norm(tmp_path / "DYLAN2" / "1991")
    assert 8002 in [int(r["lb_number"]) for r in app.coll.misfiled()]
    assert 8001 not in [int(r["lb_number"]) for r in app.coll.misfiled()]


def test_f7_files_public_lb_out_of_private(app, tmp_path):
    app.set_root(app.left, tmp_path / "DYLAN2")
    app.set_dir(app.left, tmp_path / "DYLAN2" / PRIVATE[0] / PRIVATE[1])
    _pick(app.left, "1991-02-20 New York, NY (LB-08002)")
    app.handle("f7")
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / "1991" / "1991-02-20 New York, NY (LB-08002)").is_dir()


def test_show_filter_cycles(app, tmp_path):
    names = lambda: [e.name for e in app.left.visible() if e.kind != "parent"]  # noqa: E731
    assert "notes.txt" in names()
    app.handle("f")                                   # off: not in the right spot
    assert names() == [MISFILED, PRAGUE]
    app.handle("f")                                   # public in private: none on DYLAN1
    assert names() == []
    app.handle("f")                                   # -NFT mismatch
    assert names() == [TOKYO]
    app.handle("f")                                   # non-canonical names
    assert names() == [TOKYO, LEGACY]                 # Tokyo lacks its -NFT too
    app.handle("f")                                   # integrity issues: none loaded
    assert names() == []
    app.handle("f")
    assert "notes.txt" in names()


def test_show_filter_public_in_misfiled_view(app):
    app.handle("f8")
    app.handle("f")
    app.handle("f")
    assert [e.lb for e in app.left.visible()] == [8002]



# ---- utilities: gone / relink / drop, NFT, integrity, duplicates, extras, undo, rebalance


def test_gone_record_listed_dropped_and_undone(app, tmp_path):
    shutil.rmtree(tmp_path / "DYLAN2" / "1987" / TEL_AVIV)
    app.reload()
    row = app.coll.by_lb[2311]
    assert app.coll.row_status(row)[0] == "gone"
    app.set_root(app.left, None, "gone")
    assert [e.lb for e in app.left.entries] == [2311]
    app.handle("x")
    app.handle("y")
    app.tick()
    assert 2311 not in app.coll.by_lb
    app.dialog = None
    app.handle("z")
    app.handle("enter")                               # newest: the drop
    app.handle("y")
    app.tick()
    assert app.coll.by_lb[2311]["disk_path"].endswith(TEL_AVIV)


def test_relink_to_surviving_copy(app, tmp_path):
    shutil.rmtree(tmp_path / "DYLAN1" / TORONTO)
    app.reload()
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    app.active = app.right
    copy = "1975-11-19 Toronto, Canada (LB-04410)-copy"
    assert {e.name: e.status for e in app.right.entries}[copy] == "relink"
    _pick(app.right, copy)
    app.handle("l")
    app.handle("y")
    app.tick()
    assert app.coll.by_lb[4410]["disk_path"].endswith(copy)


def test_nft_fix_and_undo(app, tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "PROBE_INTERVAL", 0)
    app.api.no_page = {3003}                          # private: no page on the site
    _pick(app.left, TOKYO)
    app.handle("n")
    assert [j.detail.split("⇒ ")[1].split("  [")[0] for j in app.dialog.jobs] \
        == [TOKYO + "-NFT"]
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / (TOKYO + "-NFT")).is_dir()
    app.dialog = None
    app.handle("z")
    app.handle("enter")
    app.handle("y")
    app.tick()                                        # undo would drop -NFT from a private LB
    assert "refused" in app.dialog.title
    assert (tmp_path / "DYLAN1" / (TOKYO + "-NFT")).is_dir()
    app.dialog = None
    app.api.no_page = set()                           # once it has a page, undo goes through
    app.handle("z")
    app.handle("enter")
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / TOKYO).is_dir()
    assert app.coll.by_lb[3003]["disk_path"].endswith(TOKYO)


def test_integrity_flag_and_filter(app, tmp_path):
    app.api.integrity = [{"lb_number": 123, "status": "content_issue",
                          "disk_path": str(tmp_path / "DYLAN1" /
                                           "1966-05-17 Manchester, England (LB-00123)")}]
    app.reload()
    app.left.show = "bad"
    assert [e.lb for e in app.left.visible() if e.kind != "parent"] == [123]
    assert "!" in lb_nc.plain(app.frame(120, 30)[3]) or any(
        "!" in lb_nc.plain(line) for line in app.frame(120, 30))
    app.handle("i")
    assert isinstance(app.dialog, lb_nc.Confirm)
    app.handle("y")
    app.tick()
    assert any(p == "/api/collection/integrity/scan" for p, _ in app.api.calls)


def test_duplicate_resolver_sets_aside(app, tmp_path):
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    app.active = app.right
    copy = "1975-11-19 Toronto, Canada (LB-04410)-copy"
    _pick(app.right, copy)
    app.handle("=")
    app.tick()                                        # compare finished → picker
    assert isinstance(app.dialog, lb_nc.Picker)
    assert any("lbdir pass" in line for line in app.dialog.lines)
    app.handle("2")                                   # keep the collection copy
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / lb_nc.DUP_DIR / copy).is_dir()
    assert app.coll.by_lb[4410]["disk_path"].endswith(TORONTO)


def test_extras_moved(app, tmp_path):
    app.set_dir(app.right, tmp_path / "DYLAN2" / "1987")
    app.active = app.right
    _pick(app.right, TEL_AVIV)
    app.handle("e")
    assert [j.label for j in app.dialog.jobs] == ["extras"]
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / "1987" / TEL_AVIV / "extras" / "cover.jpg").is_file()


def test_undo_same_drive_move(app, tmp_path):
    _pick(app.left, MISFILED)
    app.handle("f7")
    app.handle("y")
    app.tick()
    app.dialog = None
    app.handle("z")
    app.handle("enter")
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / MISFILED).is_dir()
    assert app.coll.row_status(app.coll.by_lb[1860])[0] == "misfiled"


def test_plan_rebalance_balances():
    gb = 1024 ** 3
    steps, chosen = lb_nc.plan_rebalance(
        {1966: 100 * gb, 1975: 100 * gb, 1978: 100 * gb},
        src=(50 * gb, 1000 * gb), dst=(900 * gb, 1000 * gb), from_high=True)
    assert [y for y, *_ in steps] == [1978, 1975, 1966]
    assert chosen == 3 or chosen == 2
    _, chosen_none = lb_nc.plan_rebalance({1966: gb}, src=(500 * gb, 1000 * gb),
                                          dst=(500 * gb, 1000 * gb), from_high=True)
    assert chosen_none == 0


def test_rebalance_applies_moves_and_reroutes(app, monkeypatch):
    gb = 1024 ** 3
    monkeypatch.setattr(lb_nc, "same_device", lambda a, b: False)
    monkeypatch.setattr(app, "usage", lambda path, fresh=False:
                        (1 * gb, 100 * gb) if "DYLAN1" in str(path) else (90 * gb, 100 * gb))
    monkeypatch.setattr(app.sizes, "get_now", lambda path: 10 * gb)
    app.handle("b")
    app.tick()                                        # measure finished → plan
    assert isinstance(app.dialog, lb_nc.PlanView)
    app.handle("a")
    assert isinstance(app.dialog, lb_nc.Confirm)
    labels = [j.label for j in app.dialog.jobs]
    assert any(label.startswith("move") for label in labels)
    assert any(label.startswith("route") for label in labels)


def test_suggest_routes_fits_and_moves_least():
    gb = 1024 ** 3
    where = {1960: {"A": 40 * gb}, 1970: {"A": 40 * gb}, 1980: {"B": 30 * gb},
             1990: {"A": 30 * gb}}                  # 1990 sits on A but A can't hold all
    cap = {"A": 90 * gb, "B": 100 * gb}
    totals = {"A": 100 * gb, "B": 100 * gb}
    plan = lb_nc.suggest_routes(where, cap, totals, {"A": 0, "B": 0})
    assert plan is not None
    assert plan.ranges["A"] == [1960, 1970] and plan.ranges["B"] == [1980, 1990]
    assert plan.moved == 30 * gb
    assert lb_nc.suggest_routes(where, {"A": 10 * gb, "B": 10 * gb}, totals,
                                {"A": 0, "B": 0}) is None


def test_move_order_frees_the_full_drive_first():
    gb = 1024 ** 3
    steps, stuck = lb_nc.move_order({("A", "B"): 50 * gb, ("B", "A"): 50 * gb},
                                    {"A": 5 * gb, "B": 60 * gb})
    assert steps[0][:2] == ("A", "B")                # A is full, so it empties first
    assert sum(s[2] for s in steps) == 100 * gb and not stuck


def test_route_suggestion_dialog_applies_route_changes(app, monkeypatch):
    gb = 1024 ** 3
    monkeypatch.setattr(app, "usage", lambda path, fresh=False: (90 * gb, 100 * gb))
    app.handle("w")
    app.tick()
    assert isinstance(app.dialog, lb_nc.PlanView)
    assert any(line.startswith("Suggested") for line in app.dialog.text)


# ---- live LB-page gate on private-marked moves


def test_private_marked():
    assert lb_nc.private_marked("x (LB-00001)-NFT", Path("/a/x"), None)
    assert lb_nc.private_marked("x (LB-00001)", Path("/a/PRIVATE LB/b/x"), None)
    assert lb_nc.private_marked("x (LB-00001)", Path("/a/x"), {"lb_status": "private"})
    assert not lb_nc.private_marked("x (LB-00001)", Path("/a/x"), {"lb_status": "public"})


def test_move_refused_without_live_page_rest_of_queue_runs(app, tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "PROBE_INTERVAL", 0)
    app.api.no_page = {8002}
    app.handle("f8")                                  # misfiled view: 1860 and 8002
    app.handle("+")
    app.handle("f7")
    assert any("checked live" in line for line in app.dialog.blurb)
    app.handle("y")
    app.tick()
    assert "refused" in app.dialog.title
    assert (tmp_path / "DYLAN2" / "PRIVATE LB" / "Batch A" /
            "1991-02-20 New York, NY (LB-08002)").is_dir()          # refused: untouched
    assert (tmp_path / "DYLAN2" / "1987" / MISFILED).is_dir()        # the other still moved
    live = [p for p, _ in app.api.calls if p.endswith("/live")]
    assert live == ["/api/lb_master/8002/live"]                      # only the private one


def test_move_allowed_with_live_page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "PROBE_INTERVAL", 0)
    app.set_root(app.left, tmp_path / "DYLAN2")
    app.set_dir(app.left, tmp_path / "DYLAN2" / "PRIVATE LB" / "Batch A")
    _pick(app.left, "1991-02-20 New York, NY (LB-08002)")
    app.handle("f7")
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN2" / "1991" / "1991-02-20 New York, NY (LB-08002)").is_dir()


def test_nft_add_refused_when_lb_has_a_live_page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(lb_nc, "PROBE_INTERVAL", 0)   # 3003 has a page → not private
    _pick(app.left, TOKYO)
    app.handle("n")
    app.handle("y")
    app.tick()
    assert "refused" in app.dialog.title
    assert (tmp_path / "DYLAN1" / TOKYO).is_dir()


def test_plain_public_rename_is_not_checked(app, tmp_path):
    old = tmp_path / "DYLAN1" / TORONTO
    app.pipeline_results[str(old)] = {"rename": {"proposed": "1975-11-19 Toronto (LB-04410)"}}
    _pick(app.left, TORONTO)
    app.handle("r")
    app.handle("y")
    app.tick()
    assert not any(p.endswith("/live") for p, _ in app.api.calls)


def test_noncanonical_name_highlighted_and_renamed(app, tmp_path):
    entry = next(e for e in app.left.entries if e.name == LEGACY)
    assert entry.canon == "1966-05-26 London, England (LB-00321)"
    _pick(app.left, "1966-05-17 Manchester, England (LB-00123)")      # cursor elsewhere
    row = next(line for line in app.frame(120, 30) if LEGACY in lb_nc.plain(line))
    assert any(role == "odd" for role, _ in row)
    app.handle("h")                                   # highlight off
    row = next(line for line in app.frame(120, 30) if LEGACY in lb_nc.plain(line))
    assert not any(role == "odd" for role, _ in row)
    app.handle("h")
    _pick(app.left, LEGACY)
    app.handle("r")                                   # no F4 result: uses the row's name
    assert app.dialog.jobs[0].detail.endswith(entry.canon)
    app.handle("y")
    app.tick()
    assert (tmp_path / "DYLAN1" / entry.canon).is_dir()


def test_canonical_name_skips_what_it_cannot_judge():
    row = {"lb_number": 5, "date_str": "5/26/66", "location": "", "lb_status": "public"}
    assert lb_nc.canonical_name("anything (LB-00005)", row) == ""
    row["location"] = "Paris"
    assert lb_nc.canonical_name("x (LB-00005+LB-00006)", row) == ""
    assert lb_nc.canonical_name("1966-05-26 Paris (LB-00005)", row) == ""


# ---- queueing behind a running job, and the progress bar

@pytest.fixture
def held(app):
    """A threaded runner holding one blocking job, so the UI queues behind it."""
    app.runner = lb_nc.Runner(False, threaded=True)
    app.runner.on_change = app.save_queue
    go = threading.Event()
    hold = lb_nc.Job("hold", "hold", lambda emit: go.wait(5), gated=False)
    app.run([hold])

    def release() -> None:
        go.set()
        app.runner.thread.join(5)
        app.dialog = None
        app.tick()
    yield release
    go.set()


def test_move_and_rename_queue_behind_a_running_job(app, held, tmp_path):
    _pick(app.left, MISFILED)
    app.handle("f7")
    assert any("added behind" in line for line in app.dialog.blurb)
    app.handle("y")
    assert "queued 1 job(s)" in app.flash[0]
    old = tmp_path / "DYLAN1" / TORONTO
    app.pipeline_results[str(old)] = {"rename": {"proposed": "1975-11-19 Toronto (LB-04410)"}}
    _pick(app.left, TORONTO)
    app.handle("r")
    app.handle("y")
    assert [j.label for j in app.runner.outstanding()] == ["hold", "move LB-01860", "rename"]
    assert (tmp_path / "DYLAN1" / MISFILED).is_dir()         # nothing ran yet
    held()
    assert (tmp_path / "DYLAN2" / "1987" / MISFILED).is_dir()
    assert (tmp_path / "DYLAN1" / "1975-11-19 Toronto (LB-04410)").is_dir()
    assert app.pipeline_results == {} and not app.runner.running


def test_folder_already_queued_is_not_queued_twice(app, held):
    _pick(app.left, MISFILED)
    app.handle("f7")
    app.handle("y")
    app.handle("f7")
    assert isinstance(app.dialog, lb_nc.Message)
    assert any("already in the queue" in line for line in app.dialog.text)
    assert len(app.runner.outstanding()) == 2


def test_result_jobs_wait_for_the_queue(app, held):
    app.run([lb_nc.Job("measure", "measure", lambda emit: None, gated=False)])
    assert app.dialog.title == "Busy"
    assert len(app.runner.outstanding()) == 1


def test_failure_drops_only_its_own_batch():
    ran: list[str] = []

    def boom(emit):
        raise lb_nc.JobError("nope")
    runner = lb_nc.Runner(False, threaded=True)
    go = threading.Event()
    runner.submit([lb_nc.Job("hold", "", lambda emit: go.wait(5))])
    runner.submit([lb_nc.Job("bad", "", boom), lb_nc.Job("lost", "", lambda e: ran.append("lost"))])
    runner.submit([lb_nc.Job("kept", "", lambda e: ran.append("kept"))])
    assert runner.progress()[2] == 4
    go.set()
    runner.thread.join(5)
    assert ran == ["kept"]
    assert runner.failure[0] == "bad"
    assert "1 queued job(s) of that batch not run" in runner.failure[1]
    assert runner.finished and runner.progress() == (None, 3, 3)


def test_stop_drops_everything_queued():
    ran: list[str] = []
    runner = lb_nc.Runner(False, threaded=True)
    go = threading.Event()
    runner.submit([lb_nc.Job("hold", "", lambda emit: go.wait(5))])
    runner.submit([lb_nc.Job("later", "", lambda e: ran.append("later"))])
    runner.stop.set()
    go.set()
    runner.thread.join(5)
    assert ran == [] and any("1 job(s) not run" in line for line in runner.lines)


def test_space_check_counts_moves_queued_ahead(app, held, monkeypatch):
    monkeypatch.setattr(lb_nc, "same_device", lambda a, b: False)
    monkeypatch.setattr(app, "usage", lambda path, fresh=False: (500 * 1024 ** 3, 10 ** 13))
    _pick(app.left, MISFILED)
    app.handle("f7")
    app.handle("y")
    _pick(app.left, TORONTO)
    app.handle("f6")
    assert any("(1.0K queued ahead)" in line for line in app.dialog.blurb)


@pytest.mark.parametrize("cols", [110, 70, 45])
def test_progress_bar_row(app, held, cols):
    job = lb_nc.Job("move LB-01860", "", lambda emit: None, meter=[50, 100])
    app.runner.submit([job])
    with app.runner.lock:                              # as if the move were the one running
        app.runner.job, app.runner.current = job, lb_nc.deque()
    lines = app.frame(cols, 30)
    assert len(lines) == 30 and all(lb_nc.line_width(ln) == cols for ln in lines)
    bar = lb_nc.plain(app.progress_bar(cols))
    assert "move LB-01860" in bar and "50%" in bar and "queue 1/2" in bar
    assert bar.count("█") >= 2 and "░" in bar
    assert any(lb_nc.plain(ln) == bar for ln in lines)


def test_no_progress_bar_when_idle(app):
    assert not any("█" in lb_nc.plain(ln) or "queue" in lb_nc.plain(ln)
                   for ln in app.frame(110, 30))


# ---- the queue on disk

def _app(api, queue_path) -> lb_nc.App:
    return lb_nc.App(api, threaded=False, size_cache=None, persist=False, journal_path=None,
                     queue_path=queue_path)


@pytest.fixture
def saved(app, held, tmp_path):
    """A queue file left behind: a move and a rename queued, the session then lost."""
    app.queue = lb_nc.QueueStore(tmp_path / "queue.json")
    _pick(app.left, MISFILED)
    app.handle("f7")
    app.handle("y")
    app.pipeline_results[str(tmp_path / "DYLAN1" / TORONTO)] = {
        "rename": {"proposed": "1975-11-19 Toronto (LB-04410)"}}
    _pick(app.left, TORONTO)
    app.handle("r")
    app.handle("y")
    text = app.queue.path.read_text()
    app.queue = lb_nc.QueueStore(None)            # the old session writes no more
    app.runner.stop.set()
    held()
    path = tmp_path / "queue.json"
    path.write_text(text)
    return path


def test_queue_is_saved_as_it_changes_and_removed_when_done(app, held, tmp_path):
    app.queue = lb_nc.QueueStore(tmp_path / "queue.json")
    _pick(app.left, MISFILED)
    app.handle("f7")
    app.handle("y")
    data = lb_nc.json.loads(app.queue.path.read_text())
    assert [[s["kind"] for s in b] for b in data["batches"]] == [["file"]]
    assert data["batches"][0][0]["path"] == str(tmp_path / "DYLAN1" / MISFILED)
    held()
    assert not app.queue.path.exists()


def test_saved_queue_resumes_after_a_restart(app, saved, tmp_path):
    again = _app(app.api, saved)
    assert isinstance(again.dialog, lb_nc.Picker) and "Resume 2 job(s)" in again.dialog.items[0][0]
    again.handle("enter")
    again.tick()
    assert (tmp_path / "DYLAN2" / "1987" / MISFILED).is_dir()
    assert (tmp_path / "DYLAN1" / "1975-11-19 Toronto (LB-04410)").is_dir()
    assert not saved.exists()


def test_saved_queue_blocks_new_queueing_until_decided(app, saved):
    again = _app(app.api, saved)
    before = saved.read_text()
    again.handle("esc")
    _pick(again.left, PRAGUE)
    again.handle("f7")
    assert isinstance(again.dialog, lb_nc.Picker)         # the saved queue, not a confirm
    assert saved.read_text() == before
    again.handle("3")                                     # discard
    assert not saved.exists() and again.saved is None
    again.handle("f7")
    assert isinstance(again.dialog, lb_nc.Confirm)


def test_saved_jobs_whose_folder_is_gone_are_dropped(app, saved, tmp_path):
    shutil.rmtree(tmp_path / "DYLAN1" / MISFILED)
    shutil.rmtree(tmp_path / "DYLAN1" / TORONTO)
    again = _app(app.api, saved)
    assert isinstance(again.dialog, lb_nc.Message)
    assert any("no longer there" in line for line in again.dialog.text)
    assert not saved.exists()


def test_another_live_lb_nc_keeps_its_queue(app, saved, monkeypatch):
    monkeypatch.setattr(lb_nc.QueueStore, "owner_alive", staticmethod(lambda data: True))
    again = _app(app.api, saved)
    assert again.saved is None and again.queue.path is None and again.dialog is None
    assert saved.exists()


def test_resume_adopts_a_move_the_backend_is_still_running(app, tmp_path):
    path = tmp_path / "DYLAN1" / MISFILED
    spec = {"kind": "file", "path": str(path), "lb": 1860, "mount_id": None,
            "file_mode": "move", "dest": str(tmp_path / "DYLAN2" / "1987" / MISFILED),
            "running": True}
    job = app.job_from(spec, {"running": True, "path": str(path)})
    app.api.status = {"running": False, "result": {"ok": True, "dest": spec["dest"],
                                                   "file_mode": "move"}}
    job.run(lambda text, progress: None)
    assert not any(p == "/api/pipeline/file/start" for p, _ in app.api.calls)
    assert app.journal.mem[-1]["to"] == spec["dest"]


def test_move_that_finished_while_closed_is_journaled_not_rerun(app, tmp_path):
    path = tmp_path / "DYLAN1" / "gone (LB-01860)"
    spec = {"kind": "file", "path": str(path), "lb": 1860, "dest": "/x", "running": True}
    status = {"running": False, "path": str(path),
              "result": {"ok": True, "dest": "/x", "file_mode": "move"}}
    assert "finished while lb-nc was closed" in app.job_from(spec, status)
    assert app.journal.mem[-1]["from"] == str(path)


# ---- destination preview in the right pane

def _ghosts(pane: lb_nc.Pane) -> list[str]:
    return [e.name for e in pane.entries if e.kind == "ghost"]


def _left_on(app, name: str) -> None:
    _pick(app.left, name)
    app.handle("h")                               # any key: the preview follows the cursor
    app.handle("h")


def test_right_pane_previews_the_left_cursor_destination(app, tmp_path):
    _left_on(app, MISFILED)
    assert app.right.cwd == tmp_path / "DYLAN2" / "1987"       # the 1987 route's sub-folder
    assert _ghosts(app.right) == [MISFILED]
    assert app.right.current().kind == "ghost"
    screen = "\n".join(lb_nc.plain(line) for line in app.frame(120, 24))
    assert f"⇒ {MISFILED}" in screen and "preview" in screen
    _left_on(app, TORONTO)                                      # 1975 has no sub-folder
    assert app.right.cwd == tmp_path / "DYLAN2" and _ghosts(app.right) == [TORONTO]
    assert not (tmp_path / "DYLAN2" / TORONTO).exists()         # nothing written


def test_preview_lands_where_f6_moves_it(app, tmp_path):
    _left_on(app, TORONTO)
    ghost = app.right.current().path
    app.handle("f6")
    app.handle("y")
    app.tick()
    assert ghost.is_dir() and _ghosts(app.right) == []


def test_preview_clears_when_the_right_pane_takes_over(app):
    _left_on(app, MISFILED)
    app.handle("tab")
    assert _ghosts(app.right) == [] and app.right.current().kind != "ghost"
    app.handle("+")
    assert all(e.kind != "ghost" for e in app.right.selection())


def test_preview_off_and_tagged_right_pane_stay_put(app, tmp_path):
    app.handle("p")
    _left_on(app, MISFILED)
    assert app.right.cwd == tmp_path / "DYLAN2" and _ghosts(app.right) == []
    app.handle("p")                                             # back on: follows at once
    assert app.right.cwd == tmp_path / "DYLAN2" / "1987"
    app.handle("tab")
    app.handle("+")                                             # tags on the right pane
    app.handle("tab")
    _left_on(app, TORONTO)
    assert app.right.cwd == tmp_path / "DYLAN2" / "1987" and _ghosts(app.right) == []


def test_preview_points_at_a_folder_already_there(app, tmp_path):
    (tmp_path / "DYLAN2" / TORONTO).mkdir()
    app.reload()
    _left_on(app, TORONTO)
    assert _ghosts(app.right) == [] and app.right.current().name == TORONTO


def test_preview_skips_folders_f6_would_not_move(app, tmp_path):
    _left_on(app, MISFILED)
    app.handle("home")                                          # the ".." row
    assert _ghosts(app.right) == []
    app.set_root(app.right, tmp_path / "DYLAN1")                # same drive, canonical folder
    _left_on(app, TORONTO)
    assert _ghosts(app.right) == [] and app.right.cwd == tmp_path / "DYLAN1"


def test_preview_row_is_scrolled_to_mid_pane_among_its_neighbours(app, tmp_path):
    year = tmp_path / "DYLAN2" / "1987"
    for day in range(1, 29):
        (year / f"1987-10-{day:02d} Somewhere (LB-0{9000 + day})").mkdir()
        (year / f"1987-11-{day:02d} Somewhere (LB-0{9100 + day})").mkdir()
    app.reload()
    app.frame(120, 30)                                          # the pane height is known
    _left_on(app, MISFILED)                                     # 1987-10-17 London
    lines = [lb_nc.plain(line) for line in app.frame(120, 30)]
    row = next(i for i, text in enumerate(lines) if f"⇒ {MISFILED}" in text)
    assert "1987-10-16 Somewhere" in lines[row - 1]             # sorted among its neighbours
    assert "1987-10-17 Somewhere" in lines[row + 1]
    _y, height, _x, _w = app.pane_rows["right"]
    assert height // 3 <= row - 2 <= 2 * height // 3            # mid-pane, not at an edge


def test_preview_follows_the_route_to_another_drive(app, tmp_path):
    app.set_root(app.right, tmp_path / "DYLAN1")               # the right pane is elsewhere
    _left_on(app, MISFILED)                                     # 1987 routes to DYLAN2/1987
    assert app.right.root == tmp_path / "DYLAN2"
    assert app.right.cwd == tmp_path / "DYLAN2" / "1987" and _ghosts(app.right) == [MISFILED]


def test_preview_shows_a_year_folder_not_made_yet(app, tmp_path):
    name = "1991-02-20 New York, NY (LB-08002)"                 # public LB in the private folder
    app.set_root(app.left, tmp_path / "DYLAN2")
    app.set_dir(app.left, tmp_path / "DYLAN2" / "PRIVATE LB" / "Batch A")
    _left_on(app, name)
    assert app.right.cwd == tmp_path / "DYLAN2"                # 1991/ does not exist yet
    assert _ghosts(app.right) == [f"1991/{name}"]
    names = [e.name for e in app.right.visible()]
    assert names.index("1987") < names.index(f"1991/{name}") < names.index("1998")


def test_wrap_keeps_every_word_at_phone_width():
    text = "  skip 2017-04-02 Stockholm_spot: name already correct, nothing to rename"
    rows = lb_nc.wrap(text, 32)
    assert len(rows) > 1
    assert all(lb_nc.text_width(r) == 32 and "…" not in r for r in rows)
    assert all(r.startswith("  ") for r in rows)
    assert " ".join("".join(rows).split()) == " ".join(text.split())
    assert lb_nc.wrap("  [ a ] apply      [ Esc ] close", 40)[0].startswith(
        "  [ a ] apply      [ Esc ]")                  # a row that fits is left alone
    assert "".join(r.strip() for r in lb_nc.wrap("x" * 70, 32)) == "x" * 70


def test_confirm_dialog_wraps_and_keeps_buttons_on_a_phone(app):
    _pick(app.left, MISFILED)
    app.handle("f7")
    dialog = app.dialog
    assert isinstance(dialog, lb_nc.Confirm)
    dialog.blurb = ["Renames each folder in place to the pipeline's proposed name, or for a"] * 12
    lines = dialog.render(app, 36, 20)
    text = ["".join(t for _, t in line) for line in lines]
    assert all(lb_nc.text_width(t) == 34 for t in text)
    assert not any("…" in t for t in text)
    assert "[ y ] run" in text[-2] and "[ n ] cancel" in text[-2]
