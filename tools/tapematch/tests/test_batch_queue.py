"""Tests for tapematch_session.py --batch mode (Task 6 of CC_TAPEMATCH_FIXES.md).

Covers:
- blank/comment/already-done lines are skipped
- completed lines get a '# done <timestamp>' marker appended (resumable)
- a KeyboardInterrupt mid-batch leaves the current line unmarked
- --dry-run does not rewrite the queue file
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tapematch_session as sess  # noqa: E402


def write_queue(tmp_path, text):
    path = tmp_path / "rerun_queue.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_skips_blank_comment_and_done_lines(tmp_path, monkeypatch):
    path = write_queue(tmp_path, "\n".join([
        "# header comment",
        "",
        "1989-06-04  # 8 misses",
        "1990-01-12  # 9 misses  # done 2026-06-13T00:00:00",
        "2001-10-30  # 6 misses",
        "",
    ]))

    seen: list[str] = []

    def fake_run_date(date_iso, **kwargs):
        seen.append(date_iso)
        return 0

    monkeypatch.setattr(sess, "run_date", fake_run_date)

    rc = sess.run_batch(path)
    assert rc == 0
    assert seen == ["1989-06-04", "2001-10-30"]


def test_completed_lines_get_done_marker(tmp_path, monkeypatch):
    path = write_queue(tmp_path, "1989-06-04  # 8 misses\n1990-01-12  # 9 misses\n")

    monkeypatch.setattr(sess, "run_date", lambda date_iso, **kwargs: 0)

    rc = sess.run_batch(path)
    assert rc == 0

    lines = path.read_text().splitlines()
    assert "# done" in lines[0]
    assert lines[0].startswith("1989-06-04  # 8 misses")
    assert "# done" in lines[1]


def test_keyboard_interrupt_leaves_current_line_unmarked(tmp_path, monkeypatch):
    path = write_queue(tmp_path, "1989-06-04  # 8 misses\n1990-01-12  # 9 misses\n")

    calls: list[str] = []

    def fake_run_date(date_iso, **kwargs):
        calls.append(date_iso)
        if date_iso == "1990-01-12":
            raise KeyboardInterrupt
        return 0

    monkeypatch.setattr(sess, "run_date", fake_run_date)

    rc = sess.run_batch(path)
    assert rc == 130
    assert calls == ["1989-06-04", "1990-01-12"]

    lines = path.read_text().splitlines()
    assert "# done" in lines[0]
    assert "# done" not in lines[1]


def test_dry_run_does_not_rewrite_queue_file(tmp_path, monkeypatch):
    original = "1989-06-04  # 8 misses\n1990-01-12  # 9 misses\n"
    path = write_queue(tmp_path, original)

    monkeypatch.setattr(sess, "run_date", lambda date_iso, **kwargs: 0)

    rc = sess.run_batch(path, dry_run=True)
    assert rc == 0
    assert path.read_text() == original
