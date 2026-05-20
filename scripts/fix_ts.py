"""Post-processing fixes for the translated .ts files.

1. Restores Unicode ellipsis (…) where DeepL converted it to (..)
2. Re-translates the small number of placeholder-corrupted strings using
   DeepL XML tag_handling for reliable placeholder preservation.
3. Applies manual glossary corrections for a handful of mistranslations.

Usage:
    python scripts/fix_ts.py <api_key>
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import deepl

LOCALES_DIR = Path(__file__).parent.parent / "gui" / "locales"

LANGUAGES: dict[str, str] = {
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "nl": "NL",
}

# ── Glossary overrides ─────────────────────────────────────────────────────────
# (source_string, lang) -> correct_translation
# Used for strings where DeepL produced a wrong or misleading result.

MANUAL: dict[tuple[str, str], str] = {
    # "Missing" — UI status label, not "gone/vanished"
    ("Missing", "de"): "Fehlend",
    ("Missing", "fr"): "Manquant",
    ("Missing", "es"): "Faltante",
    ("Missing", "nl"): "Ontbreekt",

    # "Re-scrape Private LBs" — web-scraping term; keep English verb, only translate noun
    ("Re-scrape Private LBs", "de"): "Private LBs neu abrufen",
    ("Re-scrape Private LBs", "fr"): "Réanalyser les LBs privés",
    ("Re-scrape Private LBs", "es"): "Re-scrape de LBs privados",
    ("Re-scrape Private LBs", "it"): "Re-scrape dei LB privati",
    ("Re-scrape Private LBs", "nl"): "Private LBs opnieuw ophalen",

    # "Commit Changes" — database commit action, not promise/pledge
    ("Commit Changes", "fr"): "Valider les modifications",
    ("Commit Changes", "es"): "Aplicar cambios",
    ("Commit Changes", "it"): "Applica modifiche",
    ("Commit Changes", "nl"): "Wijzigingen opslaan",

    # "Scrape Entry" — web scraping, not metal scrapping
    ("Scrape Entry", "de"): "Eintrag abrufen",
    ("Scrape Entry", "fr"): "Récupérer l'entrée",
    ("Scrape Entry", "es"): "Obtener entrada",
    ("Scrape Entry", "it"): "Recupera voce",
    ("Scrape Entry", "nl"): "Inzending ophalen",

    # "Scrape Bootleg Catalog"
    ("Scrape Bootleg Catalog", "de"): "Bootleg-Katalog abrufen",
    ("Scrape Bootleg Catalog", "fr"): "Récupérer le catalogue bootleg",
    ("Scrape Bootleg Catalog", "es"): "Obtener catálogo de bootlegs",
    ("Scrape Bootleg Catalog", "it"): "Recupera catalogo bootleg",
    ("Scrape Bootleg Catalog", "nl"): "Bootleg-catalogus ophalen",

    # "Scrape All Missing Entries"
    ("Scrape All Missing Entries", "de"): "Alle fehlenden Einträge abrufen",
    ("Scrape All Missing Entries", "fr"): "Récupérer toutes les entrées manquantes",
    ("Scrape All Missing Entries", "es"): "Obtener todas las entradas faltantes",
    ("Scrape All Missing Entries", "it"): "Recupera tutte le voci mancanti",
    ("Scrape All Missing Entries", "nl"): "Alle ontbrekende items ophalen",

    # "Scrape Range"
    ("Scrape Range", "de"): "Bereich abrufen",
    ("Scrape Range", "fr"): "Récupérer la plage",
    ("Scrape Range", "es"): "Obtener rango",
    ("Scrape Range", "it"): "Recupera intervallo",
    ("Scrape Range", "nl"): "Bereik ophalen",

    # "Scrape Selected Entry"
    ("Scrape Selected Entry", "de"): "Ausgewählten Eintrag abrufen",
    ("Scrape Selected Entry", "fr"): "Récupérer l'entrée sélectionnée",
    ("Scrape Selected Entry", "es"): "Obtener entrada seleccionada",
    ("Scrape Selected Entry", "it"): "Recupera voce selezionata",
    ("Scrape Selected Entry", "nl"): "Geselecteerde inzending ophalen",

    # "Scraping" (verb, progress label)
    ("Scraping", "de"): "Abrufen",
    ("Scraping", "fr"): "Récupération",
    ("Scraping", "es"): "Obteniendo",
    ("Scraping", "it"): "Recupero",
    ("Scraping", "nl"): "Ophalen",

    # "Scrape" (button label)
    ("Scrape", "de"): "Abrufen",
    ("Scrape", "fr"): "Récupérer",
    ("Scrape", "es"): "Obtener",
    ("Scrape", "it"): "Recupera",
    ("Scrape", "nl"): "Ophalen",
}

# ── Placeholder protection (XML tags — DeepL preserves these reliably) ─────────

_PLACEHOLDER_RE = re.compile(r'\{[^}]*\}')


def _protect_xml(text: str) -> tuple[str, list[str]]:
    """Replace {placeholders} with <x id='N'/> XML tags."""
    tokens: list[str] = []
    def _sub(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"<x id='{len(tokens) - 1}'/>"
    return _PLACEHOLDER_RE.sub(_sub, text), tokens


def _restore_xml(text: str, tokens: list[str]) -> str:
    """Restore <x id='N'/> back to original placeholders."""
    for i, tok in enumerate(tokens):
        text = re.sub(rf"<x\s+id=['\"]?{i}['\"]?\s*/?>", tok, text)
    return text


def _has_corrupted_placeholder(source: str, translation: str) -> bool:
    """Return True if translation has different placeholder set than source."""
    src_phs = set(_PLACEHOLDER_RE.findall(source))
    trans_phs = set(_PLACEHOLDER_RE.findall(translation))
    if src_phs != trans_phs:
        return True
    # Also catch stray % immediately after a placeholder
    if re.search(r'\{[^}]*\}%', translation):
        return True
    return False


# ── Per-file fixes ─────────────────────────────────────────────────────────────

def fix_file(
    translator: deepl.Translator,
    ts_path: Path,
    lang_code: str,
    target_lang: str,
) -> None:
    print(f"\n── {lang_code.upper()} ({ts_path.name}) ──")

    tree = ET.parse(ts_path)
    changed = 0

    # Collect strings needing re-translation (placeholder corruption)
    retranslate_elements: list[tuple[ET.Element, str]] = []

    for msg in tree.iter("message"):
        src_el  = msg.find("source")
        trans_el = msg.find("translation")
        if src_el is None or trans_el is None:
            continue

        source      = src_el.text or ""
        translation = trans_el.text or ""

        # 1. Fix ellipsis: DeepL converted … to ..
        if "…" in source and translation.endswith("..") and not translation.endswith("…"):
            trans_el.text = translation[:-2] + "…"
            changed += 1
            continue

        # 2. Apply manual glossary corrections
        key = (source, lang_code)
        if key in MANUAL:
            if trans_el.text != MANUAL[key]:
                trans_el.text = MANUAL[key]
                changed += 1
            continue

        # 3. Flag corrupted placeholders for re-translation
        if source and _has_corrupted_placeholder(source, translation):
            retranslate_elements.append((trans_el, source))

    # Re-translate corrupted placeholder strings using XML tag_handling
    if retranslate_elements:
        print(f"  Re-translating {len(retranslate_elements)} corrupted strings…")
        for trans_el, source in retranslate_elements:
            protected, tokens = _protect_xml(source)
            try:
                result = translator.translate_text(
                    protected,
                    target_lang=target_lang,
                    source_lang="EN",
                    tag_handling="xml",
                    ignore_tags=["x"],
                )
                restored = _restore_xml(result.text, tokens)
                trans_el.text = restored
                changed += 1
            except Exception as e:
                print(f"    WARNING: failed to re-translate {source!r}: {e}")

    print(f"  Fixed {changed} string(s).")
    ET.indent(tree, space="  ")
    tree.write(str(ts_path), encoding="utf-8", xml_declaration=True)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    api_key = sys.argv[1]
    translator = deepl.Translator(api_key)

    for lang_code, target_lang in LANGUAGES.items():
        ts_path = LOCALES_DIR / f"losslessbob_{lang_code}.ts"
        if not ts_path.exists():
            print(f"SKIP: {ts_path.name} not found")
            continue
        fix_file(translator, ts_path, lang_code, target_lang)

    # Show usage
    usage = translator.get_usage()
    print(f"\nDeepL total used: {usage.character.count:,} / {usage.character.limit:,}")


if __name__ == "__main__":
    main()
