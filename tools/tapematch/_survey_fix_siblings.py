"""Survey a corpus root for fix/patch sibling directories (BUG-335).

Read-only, dry-run report. For each top-level source folder under *root*, this
runs the same de-duplication pipeline as ``ingest.list_tracks`` up to and
including ``_replace_fix_siblings``, and reports which sources have a
directory that predicate would fold in as a replacement set. Nothing is
copied, moved, or written — this only prints a report.

The corpus survey BUG-335 asked for was intentionally left out of the fix
itself: this repo's session may not walk media-drive paths (/mnt/*) on its
own. Run this yourself over a real corpus root, e.g.:

    .venv/bin/python3 tools/tapematch/_survey_fix_siblings.py /mnt/DATA0/some/root
    .venv/bin/python3 tools/tapematch/_survey_fix_siblings.py /mnt/DATA0/some/root --apply-log survey.log

Usage:
    .venv/bin/python3 tools/tapematch/_survey_fix_siblings.py <root>
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tapematch.ingest import (  # noqa: E402
    _dedupe_formats,
    _dedupe_subtrees,
    _natural_key,
    _replace_fix_siblings,
    _select_version,
    discover_sources,
)

log = logging.getLogger("survey_fix_siblings")

# Mirrors config.yaml's audio_exts; kept local so this script has no config
# dependency for a one-off read-only survey.
_AUDIO_EXTS = {".flac", ".shn", ".ape", ".wav", ".aiff", ".aif", ".m4a", ".mp3"}


def _raw_tracks(source_dir: Path, exts: set[str]) -> list[Path]:
    """Return every audio file under *source_dir*, mirroring list_tracks's filter.

    Args:
        source_dir: The source folder to walk.
        exts: Lower-cased audio extensions to accept.

    Returns:
        Matching file paths, unsorted and un-deduplicated.
    """
    return [
        p
        for p in source_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in exts
        and not p.name.startswith("._")
        and "__MACOSX" not in p.parts
    ]


def survey_source(source_dir: Path) -> list[tuple[Path, int]]:
    """Return the fix-sibling directories BUG-335's fix would fold into *source_dir*.

    Args:
        source_dir: One top-level source folder.

    Returns:
        A list of ``(fix_dir, n_replaced)`` — empty if none apply.
    """
    tracks = _raw_tracks(source_dir, _AUDIO_EXTS)
    tracks, _ = _dedupe_formats(tracks)
    tracks = sorted(tracks, key=_natural_key)
    tracks, _ = _dedupe_subtrees(tracks, source_dir)
    tracks, _ = _select_version(tracks, source_dir)
    tracks = sorted(tracks, key=_natural_key)
    _, replacements = _replace_fix_siblings(tracks, source_dir)
    return replacements


def main() -> None:
    """Walk `root`'s top-level source folders and print a fix-sibling report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Corpus root (one subfolder per source)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    root = args.root
    if not root.is_dir():
        log.error("not a directory: %s", root)
        raise SystemExit(1)

    sources = discover_sources(root)
    n_sources = 0
    n_hits = 0
    n_fix_dirs = 0
    for name, path in sources.items():
        try:
            replacements = survey_source(path)
        except Exception as exc:  # noqa: BLE001 - keep surveying past a bad source
            log.warning("skip %s: %s", name, exc)
            continue
        n_sources += 1
        if not replacements:
            continue
        n_hits += 1
        n_fix_dirs += len(replacements)
        for fix_dir, n in replacements:
            log.info(
                "%s: %r replaces %d track(s)",
                name,
                str(fix_dir.relative_to(path)),
                n,
            )

    log.info("---")
    log.info(
        "%d/%d source folders carry at least one fix-sibling directory (%d directories total)",
        n_hits,
        n_sources,
        n_fix_dirs,
    )


if __name__ == "__main__":
    main()
