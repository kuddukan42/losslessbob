"""Locale key-parity checker for gui_next translation files.

Diffs translation keys between gui_next's ``en.json`` (the reference locale)
and each other locale JSON file (de/fr/es/it/nl), reporting keys that are
missing from a locale and, optionally, extra keys present in a locale but
absent from ``en.json``.

Usage:
    .venv/bin/python3 tools/gui_next_locale_parity.py
    .venv/bin/python3 tools/gui_next_locale_parity.py --show-extra
    .venv/bin/python3 tools/gui_next_locale_parity.py --locales-dir <path>

Exit codes:
    0: full parity across all checked locales.
    1: at least one locale has missing (or, with --show-extra, extra) keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_LOCALES_DIR = (
    Path(__file__).resolve().parent.parent
    / "gui_next"
    / "src"
    / "renderer"
    / "src"
    / "locales"
)
REFERENCE_LOCALE = "en"
TARGET_LOCALES = ("de", "fr", "es", "it", "nl")


def flatten_keys(data: Any, prefix: str = "") -> set[str]:
    """Flatten a nested JSON-like structure into a set of dotted-path keys.

    Args:
        data: A JSON-decoded value (typically a dict) to flatten.
        prefix: The dotted-path prefix accumulated from parent keys.

    Returns:
        A set of dotted-path strings identifying each leaf key. Dict values
        recurse into nested paths; non-dict values (strings, numbers, lists,
        etc.) are treated as leaves.
    """
    keys: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                keys |= flatten_keys(value, path)
            else:
                keys.add(path)
    else:
        if prefix:
            keys.add(prefix)
    return keys


def load_locale(path: Path) -> dict[str, Any]:
    """Load and parse a locale JSON file.

    Args:
        path: Path to the locale JSON file.

    Returns:
        The parsed JSON content as a dict.

    Raises:
        SystemExit: If the file is missing or contains invalid JSON.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        logger.error("Locale file not found: %s", path)
        raise SystemExit(2) from None
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", path, exc)
        raise SystemExit(2) from None


def format_key_list(keys: set[str], limit: int = 12) -> str:
    """Format a sorted key set as a comma-separated string, truncating if long.

    Args:
        keys: The set of dotted-path keys to format.
        limit: Maximum number of keys to list before truncating with a count.

    Returns:
        A comma-separated string of sorted keys, truncated with a
        "(+N more)" suffix if the set exceeds ``limit`` entries.
    """
    sorted_keys = sorted(keys)
    if len(sorted_keys) <= limit:
        return ", ".join(sorted_keys)
    shown = sorted_keys[:limit]
    remaining = len(sorted_keys) - limit
    return ", ".join(shown) + f" (+{remaining} more)"


def check_parity(
    locales_dir: Path,
    reference_locale: str,
    target_locales: tuple[str, ...],
    show_extra: bool,
) -> bool:
    """Check key parity between the reference locale and each target locale.

    Args:
        locales_dir: Directory containing the locale JSON files.
        reference_locale: Filename stem of the reference locale (e.g. "en").
        target_locales: Filename stems of locales to check against the
            reference.
        show_extra: Whether to also report keys present in a target locale
            but absent from the reference locale.

    Returns:
        True if every checked locale has full parity (no missing keys, and
        no extra keys when ``show_extra`` is set); False otherwise.
    """
    reference_path = locales_dir / f"{reference_locale}.json"
    reference_data = load_locale(reference_path)
    reference_keys = flatten_keys(reference_data)
    logger.info("Reference locale %s: %d keys", reference_locale, len(reference_keys))

    all_ok = True
    for locale in target_locales:
        locale_path = locales_dir / f"{locale}.json"
        if not locale_path.exists():
            logger.info("%s: FILE NOT FOUND (%s)", locale, locale_path)
            all_ok = False
            continue

        locale_data = load_locale(locale_path)
        locale_keys = flatten_keys(locale_data)

        missing = reference_keys - locale_keys
        extra = locale_keys - reference_keys if show_extra else set()

        if not missing and not extra:
            logger.info("%s: OK (%d keys)", locale, len(locale_keys))
            continue

        all_ok = False
        if missing:
            logger.info("%s: %d missing — %s", locale, len(missing), format_key_list(missing))
        if extra:
            logger.info("%s: %d extra — %s", locale, len(extra), format_key_list(extra))

    return all_ok


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns:
        The parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Check gui_next locale JSON files for translation key parity.",
    )
    parser.add_argument(
        "--locales-dir",
        type=Path,
        default=DEFAULT_LOCALES_DIR,
        help="Directory containing locale JSON files (default: gui_next locales dir).",
    )
    parser.add_argument(
        "--reference",
        default=REFERENCE_LOCALE,
        help="Filename stem of the reference locale (default: en).",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=list(TARGET_LOCALES),
        help="Filename stems of locales to check (default: de fr es it nl).",
    )
    parser.add_argument(
        "--show-extra",
        action="store_true",
        help="Also report keys present in a locale but missing from the reference.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the locale parity check and return a process exit code.

    Args:
        argv: Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns:
        0 if all checked locales have full parity, 1 otherwise.
    """
    args = parse_args(argv)
    all_ok = check_parity(
        locales_dir=args.locales_dir,
        reference_locale=args.reference,
        target_locales=tuple(args.locales),
        show_extra=args.show_extra,
    )
    logger.info("%s", "PASS: full key parity" if all_ok else "FAIL: key parity issues found")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
