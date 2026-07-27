"""Tests for tapematch_session.py --batch mode (Task 6 of CC_TAPEMATCH_FIXES.md).

Covers:
- blank/comment/already-done lines are skipped
- completed lines get a '# done <timestamp>' marker appended (resumable)
- a KeyboardInterrupt mid-batch leaves the current line unmarked
- --dry-run does not rewrite the queue file, and passes --dry-run to the child

These patch ``sess._spawn``, the seam ``run_batch`` actually uses. They used to
patch ``run_date``, which ``run_batch`` has not called since 2026-06-18 — so the
fakes were no-ops and the tests ran the real dates in the fixtures against live
audio and the production DB (BUG-279). Dates below are deliberately synthetic
(year 2999) so a regression cannot resolve them to real LB folders.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402

D1, D2, D3 = "2999-06-04", "2999-01-12", "2999-10-30"


def write_queue(tmp_path, text):
    path = tmp_path / "rerun_queue.txt"
    path.write_text(text, encoding="utf-8")
    return path


def spawn_recorder(monkeypatch, on_date=None):
    """Patch ``_spawn`` with a recorder; returns the list of spawned argv."""
    spawned: list[list[str]] = []

    def fake_spawn(cmd):
        spawned.append([str(c) for c in cmd])
        if on_date is not None:
            return on_date(str(cmd[2]))
        return 0

    monkeypatch.setattr(sess, "_spawn", fake_spawn)
    return spawned


def dates_of(spawned):
    """The concert date argument of each spawned command."""
    return [cmd[2] for cmd in spawned]


def test_skips_blank_comment_and_done_lines(tmp_path, monkeypatch):
    path = write_queue(tmp_path, "\n".join([
        "# header comment",
        "",
        f"{D1}  # 8 misses",
        f"{D2}  # 9 misses  # done 2026-06-13T00:00:00",
        f"{D3}  # 6 misses",
        "",
    ]))
    spawned = spawn_recorder(monkeypatch)

    rc = sess.run_batch(path)
    assert rc == 0
    assert dates_of(spawned) == [D1, D3]


def test_spawns_a_fresh_interpreter_per_date(tmp_path, monkeypatch):
    """The contract run_batch actually has: one child process per date."""
    path = write_queue(tmp_path, f"{D1}  # 8 misses\n")
    spawned = spawn_recorder(monkeypatch)

    assert sess.run_batch(path) == 0
    assert len(spawned) == 1
    cmd = spawned[0]
    assert cmd[0] == str(sess.VENV_PYTHON)
    assert cmd[1].endswith("tapematch_session.py")
    assert cmd[2] == D1


def test_completed_lines_get_done_marker(tmp_path, monkeypatch):
    path = write_queue(tmp_path, f"{D1}  # 8 misses\n{D2}  # 9 misses\n")
    spawn_recorder(monkeypatch)

    rc = sess.run_batch(path)
    assert rc == 0

    lines = path.read_text().splitlines()
    assert "# done" in lines[0]
    assert lines[0].startswith(f"{D1}  # 8 misses")
    assert "# done" in lines[1]


def test_keyboard_interrupt_leaves_current_line_unmarked(tmp_path, monkeypatch):
    path = write_queue(tmp_path, f"{D1}  # 8 misses\n{D2}  # 9 misses\n")

    def on_date(date_iso):
        if date_iso == D2:
            raise KeyboardInterrupt
        return 0

    spawned = spawn_recorder(monkeypatch, on_date=on_date)

    rc = sess.run_batch(path)
    assert rc == 130
    assert dates_of(spawned) == [D1, D2]

    lines = path.read_text().splitlines()
    assert "# done" in lines[0]
    assert "# done" not in lines[1]


def test_dry_run_does_not_rewrite_queue_file(tmp_path, monkeypatch):
    original = f"{D1}  # 8 misses\n{D2}  # 9 misses\n"
    path = write_queue(tmp_path, original)
    spawned = spawn_recorder(monkeypatch)

    rc = sess.run_batch(path, dry_run=True)
    assert rc == 0
    assert path.read_text() == original
    # --dry-run must reach the child, or the "dry" run would do real work.
    assert all("--dry-run" in cmd for cmd in spawned)


def test_unpatched_spawn_is_blocked_by_conftest(tmp_path):
    """The BUG-279 guard itself: an unpatched driver must not spawn anything."""
    path = write_queue(tmp_path, f"{D1}  # 8 misses\n")
    try:
        sess.run_batch(path)
    except AssertionError as exc:
        assert "real tapematch session" in str(exc)
    else:
        raise AssertionError("conftest guard did not block the spawn")
