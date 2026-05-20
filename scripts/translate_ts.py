"""Translate Qt .ts files using the DeepL API.

Usage:
    python scripts/translate_ts.py <api_key>

Reads gui/locales/losslessbob_XX.ts for each target language, translates all
<translation type="unfinished"> entries, and writes the file back in-place.

Format-string placeholders ({}, {name}, {0}) are protected before sending to
DeepL and restored exactly afterward.
"""
from __future__ import annotations

import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import deepl

# ── Configuration ──────────────────────────────────────────────────────────────

LOCALES_DIR = Path(__file__).parent.parent / "gui" / "locales"

LANGUAGES: dict[str, str] = {
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "nl": "NL",
}

# Strings that should never be translated
SKIP_SOURCES: set[str] = {
    "", "LB", "LBBCD", "qBittorrent", "→", "◀ Prev", "Next ▶",
    "◀ Prev", "Next ▶", "Page 1 / 1", "304",
}

# Regex that matches Python format placeholders: {}, {0}, {name}, {name!r}, etc.
_PLACEHOLDER_RE = re.compile(r'\{[^}]*\}')

BATCH_SIZE = 50  # DeepL max per request


# ── Placeholder protection ─────────────────────────────────────────────────────

def _protect(text: str) -> tuple[str, list[str]]:
    """Replace format placeholders with %%0%%, %%1%%, … and return the tokens."""
    tokens: list[str] = []
    def _sub(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"%%{len(tokens) - 1}%%"
    protected = _PLACEHOLDER_RE.sub(_sub, text)
    return protected, tokens


def _restore(text: str, tokens: list[str]) -> str:
    """Put the original placeholder tokens back."""
    for i, tok in enumerate(tokens):
        text = text.replace(f"%%{i}%%", tok)
    return text


# ── .ts file helpers ───────────────────────────────────────────────────────────

def _load_ts(path: Path) -> ET.ElementTree:
    ET.register_namespace("", "")
    tree = ET.parse(path)
    return tree


def _collect_unfinished(tree: ET.ElementTree) -> list[tuple[ET.Element, str]]:
    """Return [(translation_element, source_text), ...] for unfinished entries."""
    results = []
    for msg in tree.iter("message"):
        src_el = msg.find("source")
        trans_el = msg.find("translation")
        if src_el is None or trans_el is None:
            continue
        if trans_el.get("type") != "unfinished":
            continue
        source = src_el.text or ""
        if source in SKIP_SOURCES:
            continue
        results.append((trans_el, source))
    return results


def _write_ts(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(str(path), encoding="utf-8", xml_declaration=True)


# ── Translation ────────────────────────────────────────────────────────────────

def _translate_batch(
    translator: deepl.Translator,
    texts: list[str],
    target_lang: str,
) -> list[str]:
    """Translate a batch of strings, protecting placeholders."""
    protected_texts = []
    all_tokens: list[list[str]] = []
    for t in texts:
        p, tokens = _protect(t)
        protected_texts.append(p)
        all_tokens.append(tokens)

    results = translator.translate_text(
        protected_texts,
        target_lang=target_lang,
        source_lang="EN",
        preserve_formatting=True,
    )

    translated = []
    for result, tokens in zip(results, all_tokens):
        restored = _restore(result.text, tokens)
        translated.append(restored)
    return translated


def translate_file(
    translator: deepl.Translator,
    ts_path: Path,
    lang_code: str,
    target_lang: str,
) -> None:
    print(f"\n{'─'*60}")
    print(f"  {lang_code} ({ts_path.name})")
    print(f"{'─'*60}")

    tree = _load_ts(ts_path)
    unfinished = _collect_unfinished(tree)

    if not unfinished:
        print("  Nothing to translate.")
        return

    print(f"  {len(unfinished)} strings to translate…")

    # Batch-translate
    elements = [el for el, _ in unfinished]
    sources  = [src for _, src in unfinished]

    translated_all: list[str] = []
    for i in range(0, len(sources), BATCH_SIZE):
        batch_src = sources[i:i + BATCH_SIZE]
        batch_trans = _translate_batch(translator, batch_src, target_lang)
        translated_all.extend(batch_trans)
        print(f"    {min(i + BATCH_SIZE, len(sources))}/{len(sources)}", end="\r")
        # Small pause to be a polite API citizen
        if i + BATCH_SIZE < len(sources):
            time.sleep(0.2)

    # Write translations back into the tree
    for el, text in zip(elements, translated_all):
        el.text = text
        if "type" in el.attrib:
            del el.attrib["type"]

    _write_ts(tree, ts_path)
    print(f"  Done — {len(unfinished)} strings translated.      ")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    api_key = sys.argv[1]
    translator = deepl.Translator(api_key)

    # Check usage before starting
    usage = translator.get_usage()
    chars_used = usage.character.count
    chars_limit = usage.character.limit
    chars_remaining = chars_limit - chars_used
    print(f"DeepL usage: {chars_used:,} / {chars_limit:,} chars used "
          f"({chars_remaining:,} remaining)")

    for lang_code, target_lang in LANGUAGES.items():
        ts_path = LOCALES_DIR / f"losslessbob_{lang_code}.ts"
        if not ts_path.exists():
            print(f"  SKIP: {ts_path.name} not found")
            continue
        translate_file(translator, ts_path, lang_code, target_lang)

    # Final usage report
    usage2 = translator.get_usage()
    chars_used2 = usage2.character.count
    print(f"\nDone. DeepL chars used this run: "
          f"{chars_used2 - chars_used:,} "
          f"(total: {chars_used2:,} / {chars_limit:,})")


if __name__ == "__main__":
    main()
