#!/usr/bin/env python3
"""Duplicate-ID audit for the LosslessBob BUG/TODO ledger files.

Legacy manual numbering left ~17 duplicated ``TODO-NNN`` header ids and ~22
duplicated ``BUG-NNN`` header ids across the four ledger files (see TODO-209).
This script finds every duplicated header id, proposes which entry keeps the
id ("authoritative") and which would need renumbering, and greps the exact
``PREFIX-NNN`` token across CHANGELOG.md, CHANGELOG_ARCHIVE.md, instructions/,
docs/, and the other ledger files so a future renumbering pass knows the full
blast radius of each change.

Reuses the block-splitting/parsing helpers from ``tools/ledger.py`` so the
notion of an "entry" here matches exactly what ``ledger.py`` operates on.

Default mode is a **report only** — nothing is written or modified. The
``--apply`` flag is scaffolding for a future renumbering pass; see its help
text, it is explicitly disabled in this version.

Usage:
    .venv/bin/python3 tools/ledger_dedup.py
    .venv/bin/python3 tools/ledger_dedup.py --kind bug
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402  (path must be set up first)

logger = logging.getLogger("ledger_dedup")

REPO_ROOT = ledger.REPO_ROOT

# Where cross-references to a PREFIX-NNN token are searched for, beyond the
# four ledger files themselves (which are always included).
CROSS_REF_ROOTS = [
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "CHANGELOG_ARCHIVE.md",
    REPO_ROOT / "instructions",
    REPO_ROOT / "docs",
]

DATE_LABELS_BY_KIND = {
    "bug": ("Reported", "Fixed"),
    "todo": ("Added", "Closed"),
}


@dataclass
class Entry:
    """One parsed ledger entry (a single ``PREFIX-NNN:`` block).

    Attributes:
        kind: ``"bug"`` or ``"todo"``.
        number: Numeric id (unpadded), e.g. ``24`` for ``TODO-024``.
        id_str: The id token as it appears in the file, e.g. ``"TODO-024"``.
        file: Path of the ledger file the entry was found in.
        line: 1-based line number of the header line within ``file``.
        title: Entry title (text after ``"ID: "`` on the header line).
        status: Value of the ``Status:`` field, if present.
        opened: Value of the ``Reported:``/``Added:`` field, if present.
        closed: Value of the ``Fixed:``/``Closed:`` field, if present.
    """

    kind: str
    number: int
    id_str: str
    file: Path
    line: int
    title: str
    status: str
    opened: str
    closed: str


def _line_number(text: str, offset: int) -> int:
    """Return the 1-based line number of ``offset`` within ``text``.

    Args:
        text: Full file contents.
        offset: Character offset into ``text``.

    Returns:
        1-based line number containing ``offset``.
    """
    return text.count("\n", 0, offset) + 1


def _collect_entries(kind: str) -> list[Entry]:
    """Parse every entry for ``kind`` out of its open and done files.

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        Entries in file order: open file first, then done file.
    """
    id_prefix = ledger.FILES[kind]["prefix"]
    opened_label, closed_label = DATE_LABELS_BY_KIND[kind]
    entries: list[Entry] = []
    for key in ("open", "done"):
        path = ledger.FILES[kind][key]
        text = ledger._read(path)
        _, blocks, _ = ledger._split_file(text, id_prefix)
        starts = ledger._entry_starts(text, id_prefix)
        for block, start in zip(blocks, starts):
            header, fields = ledger._parse_block(block)
            match = re.match(rf"({id_prefix}-0*(\d+)):\s?(.*)", header, re.DOTALL)
            if not match:
                continue
            id_str, num_str, rest = match.groups()
            title = rest.split("\n", 1)[0].strip()
            entries.append(
                Entry(
                    kind=kind,
                    number=int(num_str),
                    id_str=id_str,
                    file=path,
                    line=_line_number(text, start),
                    title=title,
                    status=ledger._get_field(fields, "Status"),
                    opened=ledger._get_field(fields, opened_label),
                    closed=ledger._get_field(fields, closed_label),
                )
            )
    return entries


def _find_duplicates(entries: list[Entry]) -> dict[int, list[Entry]]:
    """Group entries by numeric id, keeping only ids that appear more than once.

    Args:
        entries: All parsed entries for one kind.

    Returns:
        Mapping of numeric id -> entries sharing that id, sorted by id.
    """
    by_number: dict[int, list[Entry]] = {}
    for entry in entries:
        by_number.setdefault(entry.number, []).append(entry)
    return {num: group for num, group in sorted(by_number.items()) if len(group) > 1}


def _is_done_file(entry: Entry) -> bool:
    """Return whether ``entry`` lives in a ``*_DONE.md`` file.

    Args:
        entry: Entry to check.

    Returns:
        True if the entry's file is the "done" ledger for its kind.
    """
    return entry.file == ledger.FILES[entry.kind]["done"]


def _pick_authoritative(group: list[Entry]) -> Entry:
    """Choose which entry in a duplicate group keeps the id.

    Heuristic (matches the task's stated default): a done/closed entry is
    preferred over an open one, since it is presumably the older, already
    externally-referenced record; ties broken by earliest date field, then by
    file order. This is a proposal only — a human should confirm before any
    renumbering actually happens.

    Args:
        group: Entries sharing one numeric id.

    Returns:
        The entry proposed to keep the id.
    """

    def sort_key(entry: Entry) -> tuple[int, str]:
        done_rank = 0 if _is_done_file(entry) else 1
        date_value = entry.closed or entry.opened or ""
        return (done_rank, date_value)

    return sorted(group, key=sort_key)[0]


def _grep_cross_references(id_str: str, own_header_lines: set[tuple[Path, int]]) -> list[str]:
    """Grep every exact ``PREFIX-NNN`` token occurrence outside its own headers.

    Searches CHANGELOG.md, CHANGELOG_ARCHIVE.md, instructions/, docs/, and all
    four ledger files. Since every entry in a duplicate-id group shares the
    exact same token, this is computed once per id (not once per entry) —
    entries in the group cannot be told apart by grep on the token alone.

    Args:
        id_str: Exact token to search for, e.g. ``"TODO-024"``.
        own_header_lines: ``(path, lineno)`` pairs for every entry's own
            header line in this duplicate group; these are excluded since a
            header restating its own id is not a cross-reference.

    Returns:
        List of ``"path:line: text"`` strings for every match.
    """
    token_re = re.compile(rf"\b{re.escape(id_str)}\b")
    search_paths: list[Path] = list(CROSS_REF_ROOTS)
    search_paths.extend(ledger.FILES["bug"].get(k) for k in ("open", "done"))
    search_paths.extend(ledger.FILES["todo"].get(k) for k in ("open", "done"))

    files: list[Path] = []
    for path in search_paths:
        if isinstance(path, Path) and path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
        elif isinstance(path, Path) and path.is_file():
            files.append(path)

    seen: set[Path] = set()
    hits: list[str] = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.split("\n"), start=1):
            if not token_re.search(line):
                continue
            if (path, lineno) in own_header_lines:
                continue  # one of this group's own header lines
            rel = path.relative_to(REPO_ROOT)
            hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def _format_entry(entry: Entry, opened_label: str, closed_label: str) -> str:
    """Format one entry's report line.

    Args:
        entry: Entry to format.
        opened_label: ``"Reported"`` or ``"Added"``.
        closed_label: ``"Fixed"`` or ``"Closed"``.

    Returns:
        A single indented report line.
    """
    rel = entry.file.relative_to(REPO_ROOT)
    date_bits = []
    if entry.opened:
        date_bits.append(f"{opened_label}={entry.opened}")
    if entry.closed:
        date_bits.append(f"{closed_label}={entry.closed}")
    dates = " ".join(date_bits) if date_bits else "no dates"
    return (
        f"    {rel}:{entry.line}  [{entry.status or 'no status'}] {dates}\n"
        f"      \"{entry.title}\""
    )


def build_report(kind: str) -> str:
    """Build the full dry-run report for one ledger kind.

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        The formatted, print-ready report text (empty-group case included).
    """
    id_prefix = ledger.FILES[kind]["prefix"]
    opened_label, closed_label = DATE_LABELS_BY_KIND[kind]
    entries = _collect_entries(kind)
    dupes = _find_duplicates(entries)

    lines = [f"=== {id_prefix} duplicate ids: {len(dupes)} found ==="]
    if not dupes:
        lines.append("  (none)")
        return "\n".join(lines)

    for number, group in dupes.items():
        id_display = f"{id_prefix}-{str(number).zfill(3)}"
        renumber_count = len(group) - 1
        lines.append(f"\n{id_display}  ({len(group)} entries, {renumber_count} to renumber)")
        authoritative = _pick_authoritative(group)
        for entry in group:
            role = "KEEP id " if entry is authoritative else "RENUMBER"
            lines.append(f"  [{role}] {_format_entry(entry, opened_label, closed_label)}")

        own_header_lines = {(e.file, e.line) for e in group}
        refs = _grep_cross_references(id_display, own_header_lines)
        lines.append(
            f"    -> cross-references to {id_display} outside its headers "
            f"({len(refs)} found; shared by all {len(group)} entries above, so "
            f"each match's true target needs manual attribution before renumbering):"
        )
        if refs:
            for ref in refs:
                lines.append(f"         {ref}")
        else:
            lines.append("         (none)")
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> None:
    """Handle the default report-only invocation.

    Args:
        args: Parsed CLI arguments (``args.kind``).
    """
    kinds = ["bug", "todo"] if args.kind == "both" else [args.kind]
    for kind in kinds:
        logger.info(build_report(kind))
        logger.info("")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse command-line parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="ledger_dedup.py",
        description=(
            "Report duplicated BUG-/TODO- header ids across the ledger files, "
            "propose which entry keeps the id, and count cross-references for "
            "the ones that would need renumbering. Report-only by default; "
            "modifies nothing."
        ),
    )
    parser.add_argument(
        "--kind",
        choices=["bug", "todo", "both"],
        default="both",
        help="Which ledger family to audit (default: both).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "EXPERIMENTAL / NOT IMPLEMENTED. Intended to perform the proposed "
            "renumbering (rewrite the non-authoritative entry's header id and "
            "every cross-reference found by this report) directly on disk. Do "
            "not use: every cross-reference this report finds must be reviewed "
            "by a human first, since some may be prose mentions rather than "
            "true references, and this flag currently refuses to run."
        ),
    )
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
    if args.apply:
        logger.error(
            "--apply is experimental and not implemented in this version. "
            "Run without --apply for the dry-run report."
        )
        return 2
    cmd_report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
