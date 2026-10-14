"""Tests for tools/ledger.py block splitting (BUG-366).

The last open entry used to end at its first blank line, so a later
blank-line-separated diagnosis paragraph was treated as file suffix and left
behind in BUGS.md when that entry was closed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ledger  # noqa: E402  (path must be set up first)

TEXT = (
    "\n"
    "BUG-001: first\nStatus: Open\n\n"
    "BUG-002: last\nStatus: Open\nDescription: d\n\nlater diagnosis\n"
)


def test_cut_last_entry_carries_trailing_paragraph() -> None:
    cut, rest = ledger._cut_entry(TEXT, "BUG", 2, "BUGS.md")
    assert cut.endswith("Description: d\n\nlater diagnosis")
    assert rest == "\nBUG-001: first\nStatus: Open\n"


def test_cut_middle_entry_leaves_next_paragraph() -> None:
    _, rest = ledger._cut_entry(TEXT, "BUG", 1, "BUGS.md")
    assert rest == "\nBUG-002: last\nStatus: Open\nDescription: d\n\nlater diagnosis\n"


def test_footer_stays_in_suffix() -> None:
    text = "TODO-001: a\nStatus: Open\n\nnote\n\n---\n\n---\n\n"
    _, blocks, suffix = ledger._split_file(text, "TODO")
    assert blocks == ["TODO-001: a\nStatus: Open\n\nnote"]
    assert suffix == "\n\n---\n\n---\n\n"
