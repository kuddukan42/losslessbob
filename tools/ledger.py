#!/usr/bin/env python3
"""Ledger CLI for the LosslessBob BUG/TODO bookkeeping files.

Stdlib-only helper that automates the mechanical parts of the repo's
end-of-session bookkeeping (see ``.claude/commands/session-close.md``) for the
four ledger files at the repository root:

    * ``BUGS.md``       — open bugs (newest first)
    * ``BUGS_DONE.md``  — fixed / wontfix bugs (newest first, header comment)
    * ``TODO.md``       — open tasks (newest first, trailing ``---`` footer)
    * ``TODO_DONE.md``  — done / cancelled tasks (newest first, header comment)

Subcommands:
    next-id     Print the next free BUG-/TODO- id (max across both files + 1).
    bug-open    Allocate an id and prepend a fresh open-bug block.
    todo-open   Allocate an id and prepend a fresh open-task block.
    bug-close   Cut a bug from BUGS.md, add fix fields, move to BUGS_DONE.md top.
    todo-close  Cut a task from TODO.md, mark done, move to TODO_DONE.md top.

All writes are atomic (temp file in the same directory + ``os.replace``) and
byte-exact to the surrounding files. ``--dry-run`` prints the would-be block to
stdout and touches nothing. All paths derive from this script's location.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

logger = logging.getLogger("ledger")

REPO_ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "bug": {
        "open": REPO_ROOT / "BUGS.md",
        "done": REPO_ROOT / "BUGS_DONE.md",
        "prefix": "BUG",
    },
    "todo": {
        "open": REPO_ROOT / "TODO.md",
        "done": REPO_ROOT / "TODO_DONE.md",
        "prefix": "TODO",
    },
}

# Em-dash used by the ledger files as the "nothing yet" placeholder.
EM_DASH = "—"

# Every field label that can begin a line inside a ledger block. Any line that
# does not start with one of these (followed by ':') is treated as a wrapped
# continuation of the previous field (or of the title header).
KNOWN_LABELS = (
    "Status",
    "File(s)",
    "Reported",
    "Fixed",
    "Root cause",
    "Fix",
    "Wontfix reason",
    "Priority",
    "Added",
    "Closed",
    "Description",
    "Progress",
)


# --------------------------------------------------------------------------- #
# Low-level file model: (prefix, [blocks], suffix)
# --------------------------------------------------------------------------- #
def _read(path: Path) -> str:
    """Read a ledger file verbatim (no newline translation).

    Args:
        path: File to read.

    Returns:
        The file contents as text with newlines preserved exactly.
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via a same-dir temp file.

    Args:
        path: Destination file.
        text: Full file contents to write.
    """
    directory = str(path.parent)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _split_file(text: str, id_prefix: str) -> tuple[str, list[str], str]:
    """Split a ledger file into a fixed prefix, entry blocks, and a suffix.

    Blocks never contain blank lines internally; entries are separated by a
    single blank line. ``prefix`` is everything before the first entry (a
    leading blank line and/or header comments) and ``suffix`` is everything
    after the last entry (a trailing newline and/or a ``---`` footer). The file
    is reconstructed exactly as ``prefix + "\\n\\n".join(blocks) + suffix``.

    Args:
        text: Full file contents.
        id_prefix: ``"BUG"`` or ``"TODO"``.

    Returns:
        Tuple of (prefix, blocks, suffix).
    """
    header_re = re.compile(rf"^{id_prefix}-\d+:", re.MULTILINE)
    starts = [m.start() for m in header_re.finditer(text)]
    if not starts:
        return text, [], ""

    prefix = text[: starts[0]]
    blocks: list[str] = []
    suffix = ""
    count = len(starts)
    for i in range(count):
        seg_end = starts[i + 1] if i + 1 < count else len(text)
        seg = text[starts[i] : seg_end]
        if i + 1 < count:
            # "block\n\n"; strip the separating blank line.
            blocks.append(seg.rstrip("\n"))
        else:
            # Last block owns the file suffix.
            sep = seg.find("\n\n")
            if sep != -1:
                blocks.append(seg[:sep])
                suffix = seg[sep:]
            else:
                body = seg.rstrip("\n")
                blocks.append(body)
                suffix = seg[len(body) :]
    return prefix, blocks, suffix


def _entry_starts(text: str, id_prefix: str) -> list[int]:
    """Return the character offsets of every entry header line.

    Args:
        text: Full file contents.
        id_prefix: ``"BUG"`` or ``"TODO"``.

    Returns:
        Sorted list of start offsets for lines matching ``^PREFIX-<n>:``.
    """
    header_re = re.compile(rf"^{id_prefix}-\d+:", re.MULTILINE)
    return [m.start() for m in header_re.finditer(text)]


# --------------------------------------------------------------------------- #
# Block parsing / field access
# --------------------------------------------------------------------------- #
def _parse_block(block: str) -> tuple[str, list[list[str]]]:
    """Parse one entry block into its title header and ordered fields.

    Lines beginning with a known ``Label:`` start a field; other lines are
    appended (as wrapped continuations) to the current field, or to the title
    header if no field has begun yet. Multi-line values keep their embedded
    newlines.

    Args:
        block: A single entry block (no surrounding blank lines).

    Returns:
        Tuple of (header, fields) where ``fields`` is a list of
        ``[label, value]`` pairs preserving file order.
    """
    label_re = re.compile(
        r"^(" + "|".join(re.escape(label) for label in KNOWN_LABELS) + r"):(?: (.*))?$"
    )
    lines = block.split("\n")
    header_lines = [lines[0]]
    fields: list[list[str]] = []
    for line in lines[1:]:
        match = label_re.match(line)
        if match:
            value = match.group(2) if match.group(2) is not None else ""
            fields.append([match.group(1), value])
        elif fields:
            fields[-1][1] += "\n" + line
        else:
            header_lines.append(line)
    return "\n".join(header_lines), fields


def _get_field(fields: list[list[str]], label: str) -> str:
    """Return the value of ``label`` in ``fields`` (empty string if absent).

    Args:
        fields: Parsed ``[label, value]`` pairs.
        label: Field label to look up.

    Returns:
        The field value, or ``""`` if the field is not present.
    """
    for name, value in fields:
        if name == label:
            return value
    return ""


def _field_line(label: str, value: str) -> str:
    """Format one field line, omitting the trailing space when empty.

    Args:
        label: Field label.
        value: Field value (may contain embedded newlines for continuations).

    Returns:
        ``"Label: value"`` or ``"Label:"`` when ``value`` is empty.
    """
    return f"{label}:" if value == "" else f"{label}: {value}"


# --------------------------------------------------------------------------- #
# ID allocation
# --------------------------------------------------------------------------- #
def _collect_ids(kind: str) -> list[int]:
    """Return every numeric id used for ``kind`` across its open + done files.

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        List of integer ids found in either file.
    """
    id_prefix = FILES[kind]["prefix"]
    id_re = re.compile(rf"\b{id_prefix}-(\d+)\b")
    nums: list[int] = []
    for key in ("open", "done"):
        text = _read(FILES[kind][key])
        nums.extend(int(m.group(1)) for m in id_re.finditer(text))
    return nums


def _id_width(kind: str) -> int:
    """Return the zero-pad width matching the existing ids for ``kind``.

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        The maximum digit width of existing ids (defaults to 3).
    """
    id_prefix = FILES[kind]["prefix"]
    id_re = re.compile(rf"\b{id_prefix}-(\d+)\b")
    widths = [3]
    for key in ("open", "done"):
        text = _read(FILES[kind][key])
        widths.extend(len(m.group(1)) for m in id_re.finditer(text))
    return max(widths)


def next_id(kind: str) -> str:
    """Compute the next free id for ``kind`` (max across both files + 1).

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        The next id, e.g. ``"BUG-238"``, zero-padded to the existing width.
    """
    id_prefix = FILES[kind]["prefix"]
    nums = _collect_ids(kind)
    nxt = (max(nums) + 1) if nums else 1
    return f"{id_prefix}-{str(nxt).zfill(_id_width(kind))}"


# --------------------------------------------------------------------------- #
# Block builders
# --------------------------------------------------------------------------- #
def _build_bug_open(new_id: str, title: str, files: str, desc: str, today: str) -> str:
    """Build a fresh open-bug block (mirrors the BUG-106 template).

    Args:
        new_id: Allocated id, e.g. ``"BUG-238"``.
        title: Bug title.
        files: ``File(s):`` value (may be empty).
        desc: Optional ``Description:`` value (omitted when empty).
        today: ISO date string for ``Reported:``.

    Returns:
        The block text (no trailing newline).
    """
    lines = [
        f"{new_id}: {title}",
        _field_line("Status", "Open"),
        _field_line("File(s)", files),
        _field_line("Reported", today),
    ]
    if desc:
        lines.append(_field_line("Description", desc))
    lines.append(_field_line("Root cause", "Unknown"))
    lines.append(_field_line("Fix", EM_DASH))
    return "\n".join(lines)


def _build_todo_open(
    new_id: str, title: str, priority: str, desc: str, today: str
) -> str:
    """Build a fresh open-task block (mirrors the open-TODO template).

    Args:
        new_id: Allocated id, e.g. ``"TODO-205"``.
        title: Task title.
        priority: ``Priority:`` value (High/Medium/Low).
        desc: ``Description:`` value (may be empty).
        today: ISO date string for ``Added:``.

    Returns:
        The block text (no trailing newline).
    """
    lines = [
        f"{new_id}: {title}",
        _field_line("Priority", priority),
        _field_line("Status", "Open"),
        _field_line("Added", today),
        _field_line("Description", desc),
    ]
    return "\n".join(lines)


def _build_bug_done(header: str, fields: list[list[str]], root_cause: str,
                    fix: str, today: str) -> str:
    """Build a fixed-bug block from a cut open block (mirrors BUG-237).

    Reuses the title, ``File(s):`` and ``Reported:`` from the open entry, sets
    ``Status: Fixed``, stamps ``Fixed:`` with today, and writes the supplied
    root-cause and fix. Any interim ``Description:`` is dropped (the done format
    carries its detail in ``Root cause``/``Fix``).

    Args:
        header: Title header from the open block (may be multi-line).
        fields: Parsed fields from the open block.
        root_cause: ``Root cause:`` value.
        fix: ``Fix:`` value.
        today: ISO date string for ``Fixed:``.

    Returns:
        The block text (no trailing newline).
    """
    lines = [
        header,
        _field_line("Status", "Fixed"),
        _field_line("File(s)", _get_field(fields, "File(s)")),
        _field_line("Reported", _get_field(fields, "Reported")),
        _field_line("Fixed", today),
        _field_line("Root cause", root_cause),
        _field_line("Fix", fix),
    ]
    return "\n".join(lines)


def _build_todo_done(header: str, fields: list[list[str]], resolution: str,
                     today: str) -> str:
    """Build a done-task block from a cut open block (mirrors TODO-202).

    Reuses the title, ``Priority:`` and ``Added:``, sets ``Status: Done``,
    stamps ``Closed:`` with today, and preserves the ``Description:``. When a
    resolution is given it is appended as a new continuation line of the
    description (matching how outcomes are recorded inline in TODO_DONE.md).

    Args:
        header: Title header from the open block (may be multi-line).
        fields: Parsed fields from the open block.
        resolution: Optional resolution/outcome text (appended to Description).
        today: ISO date string for ``Closed:``.

    Returns:
        The block text (no trailing newline).
    """
    description = _get_field(fields, "Description")
    if resolution:
        description = f"{description}\n{resolution}" if description else resolution
    lines = [
        header,
        _field_line("Priority", _get_field(fields, "Priority")),
        _field_line("Status", "Done"),
        _field_line("Added", _get_field(fields, "Added")),
        _field_line("Closed", today),
        _field_line("Description", description),
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# High-level operations
# --------------------------------------------------------------------------- #
def _prepend_entry(text: str, id_prefix: str, block: str) -> str:
    """Insert ``block`` as the first entry, preserving all other separators.

    Only the boundary between the new entry and the previously-first entry uses
    the standard single-blank-line (``\\n\\n``) separator; every existing
    separator in the file is left byte-for-byte untouched.

    Args:
        text: Full file contents.
        id_prefix: ``"BUG"`` or ``"TODO"``.
        block: New entry block (no trailing newline).

    Returns:
        The updated file contents.
    """
    starts = _entry_starts(text, id_prefix)
    if starts:
        pos = starts[0]
        return text[:pos] + block + "\n\n" + text[pos:]
    # Empty ledger: append the entry after any existing prefix content.
    body = text.rstrip("\n")
    tail = text[len(body):] or "\n"
    return f"{body}\n{block}{tail}" if body else f"{block}{tail}"


def _cut_entry(text: str, id_prefix: str, number: int, filename: str) -> tuple[str, str]:
    """Remove one entry from ``text`` and return the cut block plus new text.

    Exactly one adjacent separator is removed with the block (the trailing one,
    or the preceding one when the entry is last), so no dangling blank line or
    missing gap is left behind. All other separators are preserved verbatim.

    Args:
        text: Full open-file contents.
        id_prefix: ``"BUG"`` or ``"TODO"``.
        number: Numeric id to remove.
        filename: File name, used only for the not-found error message.

    Returns:
        Tuple of (cut_block, new_text).

    Raises:
        SystemExit: If the id is not present in ``text``.
    """
    _, blocks, _ = _split_file(text, id_prefix)
    starts = _entry_starts(text, id_prefix)
    for index, block in enumerate(blocks):
        match = re.match(rf"{id_prefix}-0*(\d+):", block)
        if match and int(match.group(1)) == number:
            block_start = starts[index]
            content_end = block_start + len(block)
            if index + 1 < len(starts):
                new_text = text[:block_start] + text[starts[index + 1]:]
            elif index > 0:
                prev_end = starts[index - 1] + len(blocks[index - 1])
                new_text = text[:prev_end] + text[content_end:]
            else:
                new_text = text[:block_start] + text[content_end:]
            return block, new_text
    raise SystemExit(
        f"error: {id_prefix}-{number} not found in {filename} "
        f"(only open entries can be closed)"
    )


def cmd_next_id(args: argparse.Namespace) -> None:
    """Handle ``next-id``: print the next free id.

    Args:
        args: Parsed CLI arguments (``args.kind``).
    """
    logger.info(next_id(args.kind))


def cmd_open(args: argparse.Namespace, kind: str) -> None:
    """Handle ``bug-open`` / ``todo-open``: prepend a fresh entry.

    Args:
        args: Parsed CLI arguments.
        kind: ``"bug"`` or ``"todo"``.
    """
    today = date.today().isoformat()
    new_id = next_id(kind)
    if kind == "bug":
        files = ",".join(p.strip() for p in (args.files or "").split(",") if p.strip())
        block = _build_bug_open(new_id, args.title, files, args.desc or "", today)
    else:
        block = _build_todo_open(
            new_id, args.title, args.priority, args.desc or "", today
        )

    open_path = FILES[kind]["open"]
    new_text = _prepend_entry(_read(open_path), FILES[kind]["prefix"], block)

    if args.dry_run:
        logger.info("[dry-run] would prepend to %s:\n%s", open_path.name, block)
        return
    _atomic_write(open_path, new_text)
    logger.info(new_id)


def cmd_close(args: argparse.Namespace, kind: str) -> None:
    """Handle ``bug-close`` / ``todo-close``: move an entry to its done file.

    Args:
        args: Parsed CLI arguments.
        kind: ``"bug"`` or ``"todo"``.
    """
    today = date.today().isoformat()
    id_prefix = FILES[kind]["prefix"]
    number = int(re.sub(r"\D", "", str(args.id)))
    open_path = FILES[kind]["open"]
    cut, new_open = _cut_entry(_read(open_path), id_prefix, number, open_path.name)
    header, fields = _parse_block(cut)

    if kind == "bug":
        done_block = _build_bug_done(header, fields, args.root_cause, args.fix, today)
    else:
        done_block = _build_todo_done(header, fields, args.resolution or "", today)

    done_path = FILES[kind]["done"]
    new_done = _prepend_entry(_read(done_path), id_prefix, done_block)
    id_str = header.split(":", 1)[0]

    if args.dry_run:
        logger.info(
            "[dry-run] would remove %s from %s and prepend to %s:\n%s",
            id_str,
            FILES[kind]["open"].name,
            done_path.name,
            done_block,
        )
        return
    _atomic_write(FILES[kind]["open"], new_open)
    _atomic_write(done_path, new_done)
    logger.info("%s closed -> %s", id_str, done_path.name)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse command-line parser.

    Returns:
        The configured top-level parser.
    """
    parser = argparse.ArgumentParser(
        prog="ledger.py", description="BUG/TODO ledger operations."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the would-be result and touch no files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_next = sub.add_parser("next-id", parents=[common], help="Print next free id.")
    p_next.add_argument("kind", choices=["bug", "todo"])
    p_next.set_defaults(func=cmd_next_id)

    p_bo = sub.add_parser("bug-open", parents=[common], help="Open a new bug.")
    p_bo.add_argument("title")
    p_bo.add_argument("--files", help="Comma-separated file:line references.")
    p_bo.add_argument("--desc", help="Optional description text.")
    p_bo.set_defaults(func=lambda a: cmd_open(a, "bug"))

    p_to = sub.add_parser("todo-open", parents=[common], help="Open a new task.")
    p_to.add_argument("title")
    p_to.add_argument("--desc", help="Description text.")
    p_to.add_argument(
        "--priority",
        default="Medium",
        choices=["High", "Medium", "Low"],
        help="Task priority (default: Medium).",
    )
    p_to.set_defaults(func=lambda a: cmd_open(a, "todo"))

    p_bc = sub.add_parser("bug-close", parents=[common], help="Close a bug.")
    p_bc.add_argument("id")
    p_bc.add_argument("--root-cause", required=True, dest="root_cause")
    p_bc.add_argument("--fix", required=True)
    p_bc.set_defaults(func=lambda a: cmd_close(a, "bug"))

    p_tc = sub.add_parser("todo-close", parents=[common], help="Close a task.")
    p_tc.add_argument("id")
    p_tc.add_argument("--resolution", help="Optional resolution/outcome text.")
    p_tc.set_defaults(func=lambda a: cmd_close(a, "todo"))

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
