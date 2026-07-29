"""Tests for tools/ledger.py's `doctor` subcommand (BUG/TODO ledger integrity guard).

`doctor` is the permanent guard against a repeat of the pre-ledger.py legacy
duplicate-id mess (see tools/ledger_dedup.py, .debug/assignment.md, and the
2026-07-29 renumbering pass): it must exit non-zero and list every problem
when a BUG/TODO number is used as a header more than once across the four
ledger files, or when a letter-suffixed id (e.g. BUG-116b) exists, and exit 0
otherwise. It is regex-only (no git grep), so it stays correct even against
malformed/embedded legacy content.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ledger  # noqa: E402  (path must be set up first)


@pytest.fixture
def ledger_files(tmp_path, monkeypatch):
    """Point ledger.FILES/REPO_ROOT at four empty scratch ledger files.

    Returns a dict of {"bug_open", "bug_done", "todo_open", "todo_done"} paths
    the test can write content into before calling doctor.
    """
    bugs_open = tmp_path / "BUGS.md"
    bugs_done = tmp_path / "BUGS_DONE.md"
    todo_open = tmp_path / "TODO.md"
    todo_done = tmp_path / "TODO_DONE.md"
    for path in (bugs_open, bugs_done, todo_open, todo_done):
        path.write_text("", encoding="utf-8")

    monkeypatch.setattr(ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ledger,
        "FILES",
        {
            "bug": {"open": bugs_open, "done": bugs_done, "prefix": "BUG"},
            "todo": {"open": todo_open, "done": todo_done, "prefix": "TODO"},
        },
    )
    return {
        "bug_open": bugs_open,
        "bug_done": bugs_done,
        "todo_open": todo_open,
        "todo_done": todo_done,
    }


def _bug_block(id_str: str, title: str) -> str:
    return (
        f"{id_str}: {title}\n"
        "Status: Fixed\n"
        "File(s): backend/app.py\n"
        "Reported: 2026-01-01\n"
        "Fixed: 2026-01-02\n"
        "Root cause: test fixture.\n"
        "Fix: test fixture.\n"
    )


def _todo_block(id_str: str, title: str) -> str:
    return (
        f"{id_str}: {title}\n"
        "Priority: Medium\n"
        "Status: Done\n"
        "Added: 2026-01-01\n"
        "Closed: 2026-01-02\n"
        "Description: test fixture.\n"
    )


# ---------------------------------------------------------------------------
# doctor-clean
# ---------------------------------------------------------------------------

def test_doctor_clean_reports_no_problems(ledger_files):
    """A ledger with every id unique and no letter-suffixed ids is healthy."""
    ledger_files["bug_open"].write_text(_bug_block("BUG-010", "Open bug ten") + "\n",
                                         encoding="utf-8")
    ledger_files["bug_done"].write_text(
        _bug_block("BUG-001", "First bug") + "\n" + _bug_block("BUG-002", "Second bug") + "\n",
        encoding="utf-8",
    )
    ledger_files["todo_open"].write_text(_todo_block("TODO-005", "Open task five") + "\n",
                                          encoding="utf-8")
    ledger_files["todo_done"].write_text(
        _todo_block("TODO-001", "First task") + "\n" + _todo_block("TODO-002", "Second task") + "\n",
        encoding="utf-8",
    )

    assert ledger._doctor_report() == []
    # cmd_doctor must not raise SystemExit when healthy.
    ledger.cmd_doctor(argparse_namespace())


def test_doctor_clean_empty_files(ledger_files):
    """All-empty ledger files (no entries at all) are trivially healthy."""
    assert ledger._doctor_report() == []


# ---------------------------------------------------------------------------
# doctor-detects-duplicate
# ---------------------------------------------------------------------------

def test_doctor_detects_duplicate_bug_id_across_open_and_done(ledger_files):
    """The exact legacy scenario: same numeric id used as a header twice."""
    ledger_files["bug_open"].write_text(_bug_block("BUG-107", "Open duplicate") + "\n",
                                         encoding="utf-8")
    ledger_files["bug_done"].write_text(_bug_block("BUG-107", "Done duplicate") + "\n",
                                         encoding="utf-8")

    problems = ledger._doctor_report()
    assert len(problems) == 1
    assert "duplicate BUG-107" in problems[0]
    assert "BUGS.md" in problems[0] and "BUGS_DONE.md" in problems[0]

    with pytest.raises(SystemExit) as exc_info:
        ledger.cmd_doctor(argparse_namespace())
    assert exc_info.value.code == 1


def test_doctor_detects_duplicate_within_same_done_file(ledger_files):
    """Three entries sharing one id inside a single *_DONE.md file (BUG-107-style)."""
    content = (
        _bug_block("BUG-050", "First copy") + "\n"
        + _bug_block("BUG-050", "Second copy") + "\n"
        + _bug_block("BUG-050", "Third copy") + "\n"
    )
    ledger_files["bug_done"].write_text(content, encoding="utf-8")

    problems = ledger._doctor_report()
    assert len(problems) == 1
    assert "duplicate BUG-50" in problems[0] or "duplicate BUG-050" in problems[0]


def test_doctor_detects_duplicate_todo_id(ledger_files):
    """Duplicate detection also applies to the TODO family, independently of BUG."""
    ledger_files["todo_open"].write_text(_todo_block("TODO-024", "Open dup") + "\n",
                                          encoding="utf-8")
    ledger_files["todo_done"].write_text(_todo_block("TODO-024", "Done dup") + "\n",
                                          encoding="utf-8")

    problems = ledger._doctor_report()
    assert len(problems) == 1
    assert "duplicate TODO-24" in problems[0] or "duplicate TODO-024" in problems[0]


# ---------------------------------------------------------------------------
# doctor-detects-letter-suffix
# ---------------------------------------------------------------------------

def test_doctor_detects_letter_suffixed_id(ledger_files):
    """The exact legacy scenario: a hand-patched id like BUG-116b."""
    ledger_files["bug_done"].write_text(
        _bug_block("BUG-116b", "Hand-patched id") + "\n", encoding="utf-8"
    )

    problems = ledger._doctor_report()
    assert len(problems) == 1
    assert "letter-suffixed id BUG-116b" in problems[0]
    assert "BUGS_DONE.md" in problems[0]

    with pytest.raises(SystemExit) as exc_info:
        ledger.cmd_doctor(argparse_namespace())
    assert exc_info.value.code == 1


def test_doctor_detects_letter_suffixed_todo_id(ledger_files):
    """Letter-suffix detection also applies to the TODO family."""
    ledger_files["todo_done"].write_text(
        _todo_block("TODO-050x", "Hand-patched task") + "\n", encoding="utf-8"
    )

    problems = ledger._doctor_report()
    assert len(problems) == 1
    assert "letter-suffixed id TODO-050x" in problems[0]


def test_doctor_reports_both_duplicate_and_letter_suffix_together(ledger_files):
    """A ledger with both problem types lists all of them, not just the first."""
    ledger_files["bug_open"].write_text(_bug_block("BUG-010", "Open dup") + "\n",
                                         encoding="utf-8")
    ledger_files["bug_done"].write_text(
        _bug_block("BUG-010", "Done dup") + "\n" + _bug_block("BUG-116b", "Letter suffix") + "\n",
        encoding="utf-8",
    )

    problems = ledger._doctor_report()
    assert len(problems) == 2
    assert any("duplicate BUG-10" in p or "duplicate BUG-010" in p for p in problems)
    assert any("letter-suffixed id BUG-116b" in p for p in problems)


def argparse_namespace():
    """Minimal stand-in for argparse.Namespace; cmd_doctor ignores its contents."""
    import argparse

    return argparse.Namespace()
