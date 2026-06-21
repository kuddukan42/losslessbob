"""
Translate untranslated gui_next locale strings via DeepL API.

Only sends strings that are still identical to the English source (i.e. fell back
from the Qt port). Strings that already have a real translation are left untouched.

Usage:
    DEEPL_API_KEY=<key> .venv/bin/python3 scripts/deepl_translate_gui_next.py
"""

import json
import os
import re
import time
from pathlib import Path

import deepl

ROOT    = Path(__file__).parent.parent
LOC_DIR = ROOT / "gui_next" / "src" / "renderer" / "src" / "locales"
EN_JSON = LOC_DIR / "en.json"

LANG_MAP = {
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "nl": "NL",
}

# i18next {{varName}} tokens — DeepL must not translate these
VAR_RE = re.compile(r"\{\{[^}]+\}\}")

# Strings to skip entirely (pure punctuation, single chars, numbers, etc.)
SKIP_RE = re.compile(r"^[\d\s%°.,;:!?()\-/]+$")


def leaves(node: object, path: str = "") -> list[tuple[str, str]]:
    if isinstance(node, dict):
        result = []
        for k, v in node.items():
            result.extend(leaves(v, f"{path}.{k}" if path else k))
        return result
    return [(path, node)]


def set_leaf(node: dict, path: str, value: str) -> None:
    keys = path.split(".")
    for k in keys[:-1]:
        # Create intermediate dicts so keys whose parent subtree is absent from
        # the target locale (new sections not yet present) don't KeyError.
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def protect_vars(text: str) -> tuple[str, list[str]]:
    """Replace {{varName}} with LBBV0__, LBBV1__, ... so DeepL treats them as codes."""
    tokens: list[str] = VAR_RE.findall(text)
    for i, tok in enumerate(tokens):
        text = text.replace(tok, f"LBBV{i}__", 1)
    return text, tokens


def restore_vars(text: str, tokens: list[str]) -> str:
    for i, tok in enumerate(tokens):
        text = text.replace(f"LBBV{i}__", tok)
    return text


CONTEXT = (
    "Desktop application UI labels for a music archive tool — "
    "navigation menu items, status bar, buttons, table column headers, "
    "and dialog text for managing lossless audio recordings collections."
)

# Key paths whose current translated value should never be re-sent to DeepL.
# Use for strings where the English word is intentionally kept (e.g. established
# technical terms) or where a manual override has been applied.
SKIP_KEYS: set[str] = {
    "appShell.nav.pipeline",       # "Pipeline" is the correct tech term in all locales
    "appShell.nav.bootlegs",       # "Bootlegs" is the established music term in all locales
    "appShell.statusBar.bootlegs", # same
}


def translate_batch(
    translator: deepl.Translator,
    texts: list[str],
    target_lang: str,
) -> list[str]:
    """Translate strings, protecting i18next {{varName}} placeholders from DeepL."""
    protected_list, token_map = [], []
    for t in texts:
        p, toks = protect_vars(t)
        protected_list.append(p)
        token_map.append(toks)

    results = translator.translate_text(
        protected_list,
        source_lang="EN",
        target_lang=target_lang,
        context=CONTEXT,
    )

    return [restore_vars(r.text, toks) for r, toks in zip(results, token_map, strict=True)]


def process_lang(translator: deepl.Translator, lang: str, deepl_lang: str) -> None:
    en = json.loads(EN_JSON.read_text())
    target_path = LOC_DIR / f"{lang}.json"
    target = json.loads(target_path.read_text())

    en_leaves_list = leaves(en)
    target_leaves = dict(leaves(target))

    VAR_RE_LOCAL = re.compile(r"\{\{[^}]+\}\}")

    # Collect paths that are still English OR have mismatched {{var}} placeholders
    to_translate: list[tuple[str, str]] = []
    for path, en_val in en_leaves_list:
        if not isinstance(en_val, str):
            continue
        if SKIP_RE.match(en_val):
            continue
        if path in SKIP_KEYS:
            continue
        missing = path not in target_leaves
        tr_val = target_leaves.get(path, "")
        still_english = tr_val == en_val
        broken_vars = set(VAR_RE_LOCAL.findall(en_val)) != set(VAR_RE_LOCAL.findall(tr_val))
        if missing or still_english or broken_vars:
            to_translate.append((path, en_val))

    if not to_translate:
        print(f"  {lang}: nothing to translate")
        return

    print(f"  {lang}: translating {len(to_translate)} strings...")

    # Batch in groups of 50 to avoid hitting API limits
    BATCH = 50
    translated_values: list[str] = []
    for i in range(0, len(to_translate), BATCH):
        batch = to_translate[i : i + BATCH]
        texts = [v for _, v in batch]
        translated_values.extend(translate_batch(translator, texts, deepl_lang))
        if i + BATCH < len(to_translate):
            time.sleep(0.2)

    # Write translations back into the target JSON
    for (path, _), translated in zip(to_translate, translated_values, strict=True):
        set_leaf(target, path, translated)

    target_path.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n")
    print(f"  {lang}: done — {len(to_translate)} strings written")


def main() -> None:
    api_key = os.environ.get("DEEPL_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPL_API_KEY not set")

    translator = deepl.Translator(api_key)
    usage = translator.get_usage()
    print(f"DeepL usage: {usage.character.count:,} / {usage.character.limit:,} chars")

    for lang, deepl_lang in LANG_MAP.items():
        process_lang(translator, lang, deepl_lang)

    usage2 = translator.get_usage()
    used = usage2.character.count - usage.character.count
    print(f"\nTotal chars used this run: {used:,}")


if __name__ == "__main__":
    main()
