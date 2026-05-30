"""
One-off script: port existing DeepL Qt .ts translations → gui_next JSON locale files.

Qt .ts uses English source string as key; en.json uses same English strings as values.
Qt uses {} positional placeholders; i18next uses {{varName}} named placeholders.

Strategy per leaf string:
  1. Extract {{varName}} tokens from the en.json value in order → ["count", "error", ...]
  2. Normalise en.json value to Qt form: replace {{varName}} with {} → look up in Qt map
  3. If found, restore {}s in the Qt translation back to {{varName}} in original order
  4. Fall back to English if not found (i18next handles fallback automatically)
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT      = Path(__file__).parent.parent
QT_DIR    = ROOT / 'gui' / 'locales'
EN_JSON   = ROOT / 'gui_next' / 'src' / 'renderer' / 'src' / 'locales' / 'en.json'
OUT_DIR   = ROOT / 'gui_next' / 'src' / 'renderer' / 'src' / 'locales'
LANGUAGES = ['de', 'fr', 'es', 'it', 'nl']

VAR_RE = re.compile(r'\{\{([^}]+)\}\}')


def load_qt_map(lang: str) -> dict[str, str]:
    """Parse Qt .ts XML → {source_english: translation} with {} placeholders."""
    path = QT_DIR / f'losslessbob_{lang}.ts'
    tree = ET.parse(path)
    m: dict[str, str] = {}
    for msg in tree.iter('message'):
        src  = (msg.findtext('source') or '').strip()
        tran = msg.find('translation')
        if (src and tran is not None
                and tran.get('type') != 'unfinished'
                and tran.text and tran.text.strip()):
            m[src] = tran.text.strip()
    return m


def to_qt_form(value: str) -> tuple[str, list[str]]:
    """
    Extract {{varName}} tokens and return (qt_form, [varnames_in_order]).
    Example: "Error: {{error}}" → ("Error: {}", ["error"])
    """
    varnames: list[str] = []

    def replace(m: re.Match) -> str:
        varnames.append(m.group(1))
        return '{}'

    qt_form = VAR_RE.sub(replace, value)
    return qt_form, varnames


def restore_vars(translation: str, varnames: list[str]) -> str:
    """
    Replace {} occurrences in translation back to {{varName}} in order.
    If Qt translation has fewer {} than expected, leave remainder as-is.
    """
    if not varnames:
        return translation
    it = iter(varnames)

    def replace_one(m: re.Match) -> str:
        try:
            return '{{' + next(it) + '}}'
        except StopIteration:
            return m.group(0)

    return re.sub(r'\{\}', replace_one, translation)


def translate_node(node: object, qt_map: dict[str, str]) -> object:
    """Recursively translate every leaf string in the JSON tree."""
    if isinstance(node, dict):
        return {k: translate_node(v, qt_map) for k, v in node.items()}
    if isinstance(node, list):
        return [translate_node(v, qt_map) for v in node]
    if isinstance(node, str):
        qt_form, varnames = to_qt_form(node)
        # Try exact Qt form first
        if qt_form in qt_map:
            return restore_vars(qt_map[qt_form], varnames)
        # Try original value (no vars) as fallback
        if node in qt_map:
            return qt_map[node]
        # Fall back to English
        return node
    return node


def main() -> None:
    en = json.loads(EN_JSON.read_text(encoding='utf-8'))

    for lang in LANGUAGES:
        qt_map = load_qt_map(lang)
        translated = translate_node(en, qt_map)
        out_path = OUT_DIR / f'{lang}.json'
        out_path.write_text(
            json.dumps(translated, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        # Stats
        total = 0
        hits  = 0

        def count(orig: object, trans: object) -> None:
            nonlocal total, hits
            if isinstance(orig, dict):
                for k in orig:
                    count(orig[k], trans[k])   # type: ignore[index]
            elif isinstance(orig, str):
                total += 1
                if trans != orig:
                    hits += 1

        count(en, translated)
        print(f'{lang}: {hits}/{total} strings translated ({100*hits//total}%)')

    print('\nDone. Locale files written to', OUT_DIR)


if __name__ == '__main__':
    main()
