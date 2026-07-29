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
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402  (path must be set up first)

logger = logging.getLogger("ledger_dedup")

REPO_ROOT = ledger.REPO_ROOT

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
        raw: The full raw block text this entry was parsed from (used by
            ``--apply`` to detect byte-identical duplicate blocks and to
            rewrite headers in place).
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
    raw: str = ""


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
                    raw=block,
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

    Searches the whole git-tracked repo (via ``git grep``) rather than a
    fixed allowlist of roots, so real reference sites outside CHANGELOG.md /
    docs/ / instructions/ — e.g. PROJECT.md, backend/*.py, gui_next/**/*.tsx,
    tests/, tools/tapematch/, pyproject.toml, BEST_PRACTICES.md — are not
    missed. Since every entry in a duplicate-id group shares the exact same
    token, this is computed once per id (not once per entry) — entries in
    the group cannot be told apart by grep on the token alone.

    Args:
        id_str: Exact token to search for, e.g. ``"TODO-024"``.
        own_header_lines: ``(path, lineno)`` pairs for every entry's own
            header line in this duplicate group; these are excluded since a
            header restating its own id is not a cross-reference.

    Returns:
        List of ``"path:line: text"`` strings for every match.
    """
    pattern = rf"\b{re.escape(id_str)}\b"
    result = subprocess.run(
        ["git", "grep", "-nE", pattern],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        # 0 = matches found, 1 = no matches; anything else is a real error.
        logger.warning("git grep failed for %s: %s", id_str, result.stderr.strip())
        return []

    hits: list[str] = []
    for raw_line in result.stdout.splitlines():
        # git grep -n output is "path:lineno:text"; text itself may contain ':'.
        match = re.match(r"^(.+?):(\d+):(.*)$", raw_line)
        if not match:
            continue
        rel_str, lineno_str, text = match.groups()
        path = REPO_ROOT / rel_str
        lineno = int(lineno_str)
        if (path, lineno) in own_header_lines:
            continue  # one of this group's own header lines
        hits.append(f"{rel_str}:{lineno}: {text.strip()}")
    return hits


# --------------------------------------------------------------------------- #
# --apply: the approved renumbering (PHASE 2, .debug/assignment.md)
# --------------------------------------------------------------------------- #
# Every resolved cross-reference site from .debug/assignment.md, keyed by the
# (file, 1-based line number) it was found at in the PRE-renumber files. Lines
# not listed here (KEEP targets, UNRESOLVED sites, and the 3 docstring
# non-references in this file) are deliberately left untouched.
#
# One entry: {"file": <repo-relative path>, "line": <1-based line, pre-edit>,
#             "subs": [(old_token, new_token), ...]}. Multiple (old, new)
# pairs on one entry handle lines that name 2+ different colliding ids (see
# assignment.md's "Multi-id lines" section) — they are applied together in a
# single pass over that line so an earlier substitution never invalidates a
# later one's lookup.
#
# NOTE: BUGS_DONE.md:478 (a "BUG-193 (importer ProgrammingError)" mention
# inside the renumbered Scraper entry's own NOTE) is deliberately excluded —
# on inspection it already correctly names the KEEP entry (the importer bug),
# not itself, so no rewrite is correct there. This is a correction versus the
# literal text of assignment.md's BUG-193 section (which proposed rewriting
# it); see the PHASE 2 report for the full explanation.
CROSS_REF_REWRITES: list[dict] = [
    {"file": "CHANGELOG_ARCHIVE.md", "line": 324,
     "subs": [("BUG-107", "BUG-282"), ("BUG-108", "BUG-286"), ("BUG-109", "BUG-288")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 328, "subs": [("BUG-107", "BUG-282")]},
    {"file": "BUGS_DONE.md", "line": 1855, "subs": [("BUG-108", "BUG-286")]},
    {"file": "BUGS_DONE.md", "line": 2468, "subs": [("BUG-108", "BUG-285")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 326, "subs": [("BUG-108", "BUG-286")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 325, "subs": [("BUG-109", "BUG-288")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 327, "subs": [("BUG-109", "BUG-288")]},
    {"file": "BUGS_DONE.md", "line": 2373, "subs": [("BUG-110", "BUG-289")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 824, "subs": [("BUG-116b", "BUG-298")]},
    {"file": "CHANGELOG.md", "line": 5374, "subs": [("BUG-167", "BUG-299")]},
    {"file": "CHANGELOG.md", "line": 5416, "subs": [("BUG-168", "BUG-300")]},
    {"file": "PROJECT.md", "line": 2257, "subs": [("BUG-168", "BUG-300")]},
    {"file": "CHANGELOG.md", "line": 5468, "subs": [("BUG-176", "BUG-301")]},
    {"file": "tools/tapematch/tests/test_unreadable_source.py", "line": 1,
     "subs": [("BUG-176", "BUG-301")]},
    {"file": "CHANGELOG.md", "line": 5324, "subs": [("BUG-193", "BUG-302")]},
    {"file": "CHANGELOG.md", "line": 5265, "subs": [("BUG-195", "BUG-303")]},
    {"file": "CHANGELOG.md", "line": 4905, "subs": [("BUG-214", "BUG-304")]},
    {"file": "CHANGELOG.md", "line": 4031, "subs": [("BUG-215", "BUG-305")]},
    {"file": "TODO_DONE.md", "line": 1343, "subs": [("BUG-215", "BUG-305")]},
    {"file": "CHANGELOG.md", "line": 4292, "subs": [("BUG-216", "BUG-306")]},
    {"file": "CHANGELOG.md", "line": 4282, "subs": [("BUG-217", "BUG-307")]},
    {"file": "CHANGELOG.md", "line": 3986, "subs": [("BUG-218", "BUG-308")]},
    {"file": "CHANGELOG.md", "line": 3987, "subs": [("BUG-218", "BUG-308")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 738, "subs": [("TODO-086", "TODO-278")]},
    {"file": "PROJECT.md", "line": 2363, "subs": [("TODO-086", "TODO-278")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 297, "subs": [("TODO-102", "TODO-279")]},
    {"file": "CHANGELOG_ARCHIVE.md", "line": 300, "subs": [("TODO-102", "TODO-279")]},
    {"file": "TODO_DONE.md", "line": 2497, "subs": [("TODO-102", "TODO-279")]},
    {"file": "CHANGELOG.md", "line": 2329, "subs": [("TODO-108", "TODO-280")]},
    {"file": "instructions/WORK_PACKAGE_2026-07-14.md", "line": 14,
     "subs": [("TODO-108", "TODO-280"), ("TODO-154", "TODO-291")]},
    {"file": "instructions/WORK_PACKAGE_2026-07-14.md", "line": 40, "subs": [("TODO-108", "TODO-280")]},
    {"file": "BEST_PRACTICES.md", "line": 351, "subs": [("TODO-109", "TODO-281")]},
    {"file": "CHANGELOG.md", "line": 1984, "subs": [("TODO-109", "TODO-281")]},
    {"file": "pyproject.toml", "line": 24, "subs": [("TODO-109", "TODO-281")]},
    {"file": "CHANGELOG.md", "line": 5881, "subs": [("TODO-110", "TODO-282")]},
    {"file": "CHANGELOG.md", "line": 6003, "subs": [("TODO-110", "TODO-282")]},
    {"file": "PROJECT.md", "line": 2262, "subs": [("TODO-110", "TODO-282")]},
    {"file": "PROJECT.md", "line": 2271, "subs": [("TODO-110", "TODO-282")]},
    {"file": "PROJECT.md", "line": 2272, "subs": [("TODO-110", "TODO-282")]},
    {"file": "TODO_DONE.md", "line": 2248, "subs": [("TODO-110", "TODO-282")]},
    {"file": "TODO_DONE.md", "line": 2253, "subs": [("TODO-110", "TODO-282")]},
    {"file": "CHANGELOG.md", "line": 5956, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 94, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 343, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 347, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 1172, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 1187, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 1622, "subs": [("TODO-111", "TODO-284")]},
    {"file": "PROJECT.md", "line": 2269, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/app.py", "line": 7866, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/db.py", "line": 863, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/db.py", "line": 2472, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/db.py", "line": 4777, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/integrity_monitor.py", "line": 1, "subs": [("TODO-111", "TODO-284")]},
    {"file": "backend/scheduler.py", "line": 184, "subs": [("TODO-111", "TODO-284")]},
    {"file": "docs/wiki/Collection-Pipeline.md", "line": 45, "subs": [("TODO-111", "TODO-284")]},
    {"file": "gui_next/src/renderer/src/screens/ScreenMounts.tsx", "line": 28,
     "subs": [("TODO-111", "TODO-284")]},
    {"file": "gui_next/src/renderer/src/screens/ScreenMounts.tsx", "line": 419,
     "subs": [("TODO-111", "TODO-284")]},
    {"file": "CHANGELOG.md", "line": 6014, "subs": [("TODO-112", "TODO-285")]},
    {"file": "PROJECT.md", "line": 2273, "subs": [("TODO-112", "TODO-285")]},
    {"file": "backend/app.py", "line": 605, "subs": [("TODO-112", "TODO-285")]},
    {"file": "gui_next/src/renderer/src/components/AboutDialog.tsx", "line": 110,
     "subs": [("TODO-112", "TODO-285")]},
    {"file": "gui_next/src/renderer/src/components/AboutDialog.tsx", "line": 121,
     "subs": [("TODO-112", "TODO-285")]},
    {"file": "CHANGELOG.md", "line": 6023, "subs": [("TODO-113", "TODO-286")]},
    {"file": "CHANGELOG.md", "line": 4415, "subs": [("TODO-140", "TODO-287")]},
    {"file": "CHANGELOG.md", "line": 5724, "subs": [("TODO-140", "TODO-287")]},
    {"file": "TODO_DONE.md", "line": 2124, "subs": [("TODO-140", "TODO-287")]},
    {"file": "TODO_DONE.md", "line": 2180, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/BASELINE.md", "line": 166, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/BASELINE.md", "line": 342, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/BASELINE.md", "line": 506, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/BASELINE.md", "line": 543, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/calibrate_lowband.py", "line": 2, "subs": [("TODO-140", "TODO-287")]},
    {"file": "tools/tapematch/tests/test_lowband_corr.py", "line": 1, "subs": [("TODO-140", "TODO-287")]},
    {"file": "CHANGELOG.md", "line": 2892, "subs": [("TODO-151", "TODO-288")]},
    {"file": "CHANGELOG.md", "line": 2895, "subs": [("TODO-151", "TODO-288")]},
    {"file": "PROJECT.md", "line": 2242, "subs": [("TODO-151", "TODO-289")]},
    {"file": "CHANGELOG.md", "line": 2560, "subs": [("TODO-153", "TODO-290")]},
    {"file": "CHANGELOG.md", "line": 2570, "subs": [("TODO-153", "TODO-290")]},
    {"file": "PROJECT.md", "line": 1445, "subs": [("TODO-153", "TODO-290")]},
    {"file": "TODO_DONE.md", "line": 992, "subs": [("TODO-153", "TODO-290")]},
    {"file": "backend/db.py", "line": 3799, "subs": [("TODO-153", "TODO-290")]},
    {"file": "instructions/complete/FABLE_OLOF_FILES.md", "line": 252, "subs": [("TODO-153", "TODO-290")]},
    {"file": "instructions/complete/WORK_PACKAGE_2026-07-09.md", "line": 86,
     "subs": [("TODO-153", "TODO-290")]},
    {"file": "instructions/complete/WORK_PACKAGE_2026-07-09.md", "line": 87,
     "subs": [("TODO-153", "TODO-290")]},
    {"file": "CHANGELOG.md", "line": 2338, "subs": [("TODO-154", "TODO-291")]},
    {"file": "CHANGELOG.md", "line": 3165, "subs": [("TODO-198", "TODO-292")]},
    {"file": "CHANGELOG.md", "line": 3166, "subs": [("TODO-198", "TODO-292")]},
]


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repo root, as a string.

    Args:
        path: Absolute path under ``REPO_ROOT``.

    Returns:
        POSIX-ish relative path string.
    """
    return str(path.relative_to(REPO_ROOT))


def _apply_cross_ref_rewrites(kinds: list[str]) -> list[str]:
    """Apply ``CROSS_REF_REWRITES``, restricted to the selected ``kinds``.

    Must run before any structural ledger-file edit (header renumbering,
    ``Formerly:`` insertion, block deletion) in the same ``--apply`` pass,
    since its line numbers are only valid against the pre-edit files —
    cross-ref rewrites themselves are same-length token swaps and never
    change any file's line count. Idempotent: a token already rewritten
    (or a site already applied) is silently skipped.

    Args:
        kinds: Subset of ``["bug", "todo"]`` to restrict rewrites to.

    Returns:
        List of human-readable change descriptions (one per token rewritten).
    """
    allowed_prefixes = {ledger.FILES[k]["prefix"] for k in kinds}
    changes: list[str] = []
    by_file: dict[str, list[dict]] = {}
    for rule in CROSS_REF_REWRITES:
        subs = [(o, n) for o, n in rule["subs"] if o.split("-", 1)[0] in allowed_prefixes]
        if subs:
            by_file.setdefault(rule["file"], []).append({"line": rule["line"], "subs": subs})

    for relpath, rules in by_file.items():
        path = REPO_ROOT / relpath
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        lines = text.split("\n")
        modified = False
        for rule in rules:
            idx = rule["line"] - 1
            if idx < 0 or idx >= len(lines):
                continue
            line = lines[idx]
            new_line = line
            for old, new in rule["subs"]:
                pattern = re.compile(rf"\b{re.escape(old)}\b")
                if pattern.search(new_line):
                    new_line = pattern.sub(new, new_line)
                    changes.append(f"{relpath}:{rule['line']}  {old} -> {new}")
            if new_line != line:
                lines[idx] = new_line
                modified = True
        if modified:
            new_text = "\n".join(lines)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(new_text)
    return changes


def _max_header_id(kind: str) -> int:
    """Return the highest numeric id used as a genuine entry header for ``kind``.

    Deliberately narrower than ``ledger._collect_ids`` (which regex-scans
    *any* ``PREFIX-NNN`` token anywhere in the file text): this only counts
    ``^PREFIX-NNN:`` at the start of a line. That distinction matters here
    because by the time renumbering allocation happens, the cross-reference
    rewrite pass may already have written new, higher id tokens into *body*
    text inside BUGS_DONE.md/TODO_DONE.md (e.g. "...(BUG-286)..." on some
    other entry's Root cause line) — a permissive whole-text scan would see
    those and inflate the next-id counter. Header-only scanning is immune to
    that and also naturally ignores letter-suffixed ids (``BUG-116b:`` does
    not match ``\\d+:``).

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        The highest numeric id found (0 if none).
    """
    id_prefix = ledger.FILES[kind]["prefix"]
    header_re = re.compile(rf"^{id_prefix}-(\d+):", re.MULTILINE)
    nums = [0]
    for key in ("open", "done"):
        text = ledger._read(ledger.FILES[kind][key])
        nums.extend(int(m.group(1)) for m in header_re.finditer(text))
    return max(nums)


def _plan_renumbering(kind: str, start_num: int):
    """Plan the full renumbering for one kind: ids, deletions, letter-suffix fixes.

    Re-parses the ledger files fresh (so it reflects whatever
    ``_apply_cross_ref_rewrites`` already did — which never changes headers or
    entry counts) and allocates new ids in a single ascending-by-number pass
    that interleaves ordinary duplicate groups with any letter-suffixed ids,
    exactly matching the approved allocation order in ``.debug/assignment.md``
    (e.g. BUG-116b lands at BUG-298, between the BUG-115 and BUG-167 groups).

    Args:
        kind: ``"bug"`` or ``"todo"``.
        start_num: First new id to allocate. Must be computed via
            ``_max_header_id(kind) + 1`` *before* any file in this apply run
            has been touched (see ``_max_header_id`` for why).

    Returns:
        Tuple of (renumber_map, delete_set, letter_plan, changes):
            renumber_map: ``{(file, line): (new_id, old_id, opened_date)}``
                for ordinary duplicate-group entries, keyed by their current
                header line (block-rebuild consumes this).
            delete_set: ``{(file, line)}`` of byte-identical duplicate blocks
                to remove outright.
            letter_plan: list of ``(file, old_id, new_id, opened_date)`` for
                letter-suffixed ids (text-search based, order-independent).
            changes: human-readable change descriptions.

    Raises:
        SystemExit: If a byte-identical duplicate no longer matches its twin
            at plan time (re-verification safety check).
    """
    id_prefix = ledger.FILES[kind]["prefix"]
    entries = _collect_entries(kind)
    dupes = _find_duplicates(entries)
    letter_entries = _collect_letter_suffix_entries(kind)

    work: list[tuple[int, str, object]] = [(num, "group", group) for num, group in dupes.items()]
    work += [(entry["number"], "letter", entry) for entry in letter_entries]
    work.sort(key=lambda item: item[0])

    next_num = start_num
    id_width = ledger._id_width(kind)

    renumber_map: dict[tuple[Path, int], tuple[str, str, str]] = {}
    delete_set: set[tuple[Path, int]] = set()
    letter_plan: list[tuple[Path, str, str, str]] = []
    changes: list[str] = []

    for _number, tag, payload in work:
        if tag == "group":
            group = payload
            authoritative = _pick_authoritative(group)
            others = [e for e in group if e is not authoritative]
            seen_raw: dict[str, Entry] = {}
            for entry in others:
                twin = seen_raw.get(entry.raw)
                if twin is not None:
                    if twin.raw != entry.raw:
                        raise SystemExit(
                            f"abort: expected byte-identical duplicate at "
                            f"{_rel(entry.file)}:{entry.line} no longer matches "
                            f"{_rel(twin.file)}:{twin.line} -- refusing to delete"
                        )
                    delete_set.add((entry.file, entry.line))
                    changes.append(
                        f"DELETE {_rel(entry.file)}:{entry.line} "
                        f"(byte-identical duplicate of {_rel(twin.file)}:{twin.line})"
                    )
                    continue
                seen_raw[entry.raw] = entry
                new_id = f"{id_prefix}-{str(next_num).zfill(id_width)}"
                next_num += 1
                opened_val = entry.opened.split("\n", 1)[0].strip()
                renumber_map[(entry.file, entry.line)] = (new_id, entry.id_str, opened_val)
                changes.append(f"{_rel(entry.file)}:{entry.line}  {entry.id_str} -> {new_id}")
        else:
            entry = payload
            new_id = f"{id_prefix}-{str(next_num).zfill(id_width)}"
            next_num += 1
            letter_plan.append((entry["file"], entry["id_str"], new_id, entry["opened"]))
            changes.append(f"{_rel(entry['file'])}  {entry['id_str']} -> {new_id} (letter-suffix)")

    return renumber_map, delete_set, letter_plan, changes


def _collect_letter_suffix_entries(kind: str) -> list[dict]:
    """Find letter-suffixed ids (e.g. ``BUG-116b``) not caught by ``_collect_entries``.

    These are invisible to the normal block splitter (``ledger._split_file``
    only recognizes ``PREFIX-<digits>:`` as an entry boundary), so this scans
    raw file text directly for the header line, then isolates just that
    sub-block's own lines (up to the next blank line) to parse its fields.

    Args:
        kind: ``"bug"`` or ``"todo"``.

    Returns:
        List of dicts with ``number``, ``id_str``, ``file``, ``line``, ``opened``.
    """
    id_prefix = ledger.FILES[kind]["prefix"]
    opened_label, _ = DATE_LABELS_BY_KIND[kind]
    header_re = re.compile(rf"^({id_prefix}-(\d+)[A-Za-z]+):\s?(.*)$", re.MULTILINE)
    results: list[dict] = []
    for key in ("open", "done"):
        path = ledger.FILES[kind][key]
        text = ledger._read(path)
        lines = text.split("\n")
        for match in header_re.finditer(text):
            id_str, num_str, _title = match.groups()
            line_no = text.count("\n", 0, match.start()) + 1
            idx = line_no - 1
            block_lines = [lines[idx]]
            j = idx + 1
            while j < len(lines) and lines[j].strip() != "":
                block_lines.append(lines[j])
                j += 1
            _, fields = ledger._parse_block("\n".join(block_lines))
            opened_val = ledger._get_field(fields, opened_label).split("\n", 1)[0].strip()
            results.append(
                {
                    "number": int(num_str),
                    "id_str": id_str,
                    "file": path,
                    "line": line_no,
                    "opened": opened_val,
                }
            )
    return results


def _execute_block_rebuild(
    kind: str,
    renumber_map: dict[tuple[Path, int], tuple[str, str, str]],
    delete_set: set[tuple[Path, int]],
) -> None:
    """Rewrite headers + insert ``Formerly:`` fields + drop deleted blocks.

    Runs before the letter-suffix splice so its own fresh read/line numbers
    are never invalidated by a prior insertion elsewhere in the same file.

    Args:
        kind: ``"bug"`` or ``"todo"``.
        renumber_map: From ``_plan_renumbering``.
        delete_set: From ``_plan_renumbering``.
    """
    if not renumber_map and not delete_set:
        return
    id_prefix = ledger.FILES[kind]["prefix"]
    for key in ("open", "done"):
        path = ledger.FILES[kind][key]
        text = ledger._read(path)
        prefix, blocks, suffix = ledger._split_file(text, id_prefix)
        starts = ledger._entry_starts(text, id_prefix)
        new_blocks: list[str] = []
        file_modified = False
        for block, start in zip(blocks, starts):
            line = _line_number(text, start)
            lookup_key = (path, line)
            if lookup_key in delete_set:
                file_modified = True
                continue
            if lookup_key in renumber_map:
                new_id, old_id, opened_val = renumber_map[lookup_key]
                header, fields = ledger._parse_block(block)
                new_header = re.sub(rf"^{re.escape(old_id)}:", f"{new_id}:", header, count=1)
                formerly_value = f"{old_id} (duplicate, opened {opened_val})"
                new_fields = [["Formerly", formerly_value]] + fields
                new_block_lines = [new_header] + [
                    ledger._field_line(label, value) for label, value in new_fields
                ]
                new_blocks.append("\n".join(new_block_lines))
                file_modified = True
            else:
                new_blocks.append(block)
        if file_modified:
            new_text = prefix + "\n\n".join(new_blocks) + suffix
            ledger._atomic_write(path, new_text)


def _execute_letter_suffix_splices(letter_plan: list[tuple[Path, str, str, str]]) -> None:
    """Rewrite letter-suffixed headers in place and insert their ``Formerly:`` field.

    Text-search based (matches on the literal old id string), so it is
    immune to any line-number shift caused by ``_execute_block_rebuild``
    running first, and naturally idempotent (a second run finds no more
    letter-suffixed headers to match).

    Args:
        letter_plan: From ``_plan_renumbering``.
    """
    by_file: dict[Path, list[tuple[str, str, str]]] = {}
    for path, old_id, new_id, opened_val in letter_plan:
        by_file.setdefault(path, []).append((old_id, new_id, opened_val))

    for path, items in by_file.items():
        text = ledger._read(path)
        lines = text.split("\n")
        changed = False
        for old_id, new_id, opened_val in items:
            for i, line in enumerate(lines):
                if line.startswith(f"{old_id}:"):
                    lines[i] = new_id + line[len(old_id) :]
                    formerly = f"Formerly: {old_id} (duplicate, opened {opened_val})"
                    lines.insert(i + 1, formerly)
                    changed = True
                    break
            else:
                logger.warning(
                    "letter-suffix header %s not found in %s (already applied?)",
                    old_id,
                    path.name,
                )
        if changed:
            ledger._atomic_write(path, "\n".join(lines))


_DEDUP_NOTE_MARKER = "duplicate ids from the pre-ledger.py era were renumbered"


def _insert_dedup_header_note(path: Path, today: str) -> bool:
    """Insert the dated dedup-migration note near the top of a done-ledger file.

    Idempotent: skipped if a note with the same marker text is already present.

    Args:
        path: ``BUGS_DONE.md`` or ``TODO_DONE.md``.
        today: ISO date string to stamp the note with.

    Returns:
        True if the note was inserted, False if it was already present.
    """
    text = ledger._read(path)
    if _DEDUP_NOTE_MARKER in text:
        return False
    note = (
        f"<!-- {today}: historical duplicate ids from the pre-ledger.py era were renumbered "
        f"in this file; renumbered entries carry a `Formerly:` field. Ids referenced in git "
        f"commit messages and in CHANGELOG entries predating {today} may refer to the "
        f"pre-renumber numbering. -->\n"
    )
    # Insert right after any existing leading HTML-comment header block, else
    # at the very top of the file.
    lines = text.split("\n")
    insert_at = 0
    while insert_at < len(lines) and (
        lines[insert_at].strip() == "" or lines[insert_at].strip().startswith("<!--")
    ):
        insert_at += 1
        if insert_at >= 2 and lines[insert_at - 1].strip().startswith("-->"):
            break
    new_lines = lines[:insert_at] + [note.rstrip("\n")] + lines[insert_at:]
    ledger._atomic_write(path, "\n".join(new_lines))
    return True


def cmd_apply(args: argparse.Namespace) -> None:
    """Handle ``--apply``: perform the approved renumbering for real.

    Order matters and is deliberate:
      1. Cross-reference site rewrites (uses pre-edit line numbers — must run
         before any structural edit changes a file's line count).
      2. Per-kind duplicate-group block rebuild (header rewrite + ``Formerly:``
         insertion + byte-identical-duplicate deletion).
      3. Per-kind letter-suffix id normalization (text-search based, so it is
         safe to run after step 2's line-number-shifting edits).
      4. Dated migration note near the top of both *_DONE.md files.

    Idempotent: a second run finds no duplicates, no letter-suffixed ids, no
    matching cross-ref line text, and an already-present migration note, so it
    reports "nothing to do" and touches no files.

    Args:
        args: Parsed CLI arguments (``args.kind``).
    """
    kinds = ["bug", "todo"] if args.kind == "both" else [args.kind]
    all_changes: list[str] = []

    # Snapshot the starting id BEFORE any edit in this run (including the
    # cross-ref rewrites below), per _max_header_id's docstring.
    start_nums = {kind: _max_header_id(kind) + 1 for kind in kinds}

    all_changes.extend(_apply_cross_ref_rewrites(kinds))

    for kind in kinds:
        renumber_map, delete_set, letter_plan, plan_changes = _plan_renumbering(
            kind, start_nums[kind]
        )
        all_changes.extend(plan_changes)
        _execute_block_rebuild(kind, renumber_map, delete_set)
        _execute_letter_suffix_splices(letter_plan)

    today = date.today().isoformat()
    for kind in kinds:
        done_path = ledger.FILES[kind]["done"]
        if _insert_dedup_header_note(done_path, today):
            all_changes.append(f"{_rel(done_path)}: inserted dedup-migration header note")

    if not all_changes:
        logger.info("Nothing to do -- ledger already deduplicated (idempotent no-op).")
        return
    for line in all_changes:
        logger.info(line)
    logger.info("\n%d change(s) applied.", len(all_changes))


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
            "Apply the human-reviewed renumbering proposal from "
            ".debug/assignment.md: rewrite non-authoritative entry header "
            "ids, insert `Formerly:` fields, normalize letter-suffixed ids, "
            "delete verified byte-identical duplicate blocks, and rewrite "
            "the resolved cross-reference sites (UNRESOLVED sites are left "
            "untouched). Idempotent -- a second run is a no-op. Default "
            "(without this flag) stays report-only."
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
        cmd_apply(args)
        return 0
    cmd_report(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
