"""Final cleanup pass — targeted fixes for remaining corruptions.

1. Restores %%N% / %N%% tokens to original {placeholder} from source.
2. Manual fixes for strings where placeholder was dropped entirely.
3. Fixes remaining … → .. ellipsis corruption.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "gui" / "locales"
_PH_RE   = re.compile(r'\{[^}]*\}')
_TOK_RE  = re.compile(r'%%(\d+)%|%(\d+)%%')   # matches %%N% and %N%%

LANGUAGES = ["de", "fr", "es", "it", "nl"]


def _restore_tokens(translation: str, source_tokens: list[str]) -> str:
    """Replace %%N% / %N%% tokens with the original source placeholder."""
    def _sub(m: re.Match) -> str:
        idx = int(m.group(1) if m.group(1) is not None else m.group(2))
        if idx < len(source_tokens):
            return source_tokens[idx]
        return m.group(0)  # unknown index — leave as-is
    return _TOK_RE.sub(_sub, translation)


# Manual overrides for strings where placeholder was silently dropped
# Keys: (source, lang) → corrected translation
MANUAL_FIXES: dict[tuple[str, str], str] = {
    # ~{0}m {1}s left — {0} dropped in FR/NL
    ("~{0}m {1}s left", "fr"): "~{0}m {1}s restantes",
    ("~{0}m {1}s left", "nl"): "~{0}m {1}s resterend",

    # Starting range scrape — translated verb semantically wrong in some langs
    ("Starting range scrape LB-{} to LB-{}…", "de"): "Starte Abruf LB-{} bis LB-{}…",
    ("Starting range scrape LB-{} to LB-{}…", "fr"): "Démarrage de la récupération LB-{} à LB-{}…",
    ("Starting range scrape LB-{} to LB-{}…", "es"): "Iniciando recuperación LB-{} a LB-{}…",
    ("Starting range scrape LB-{} to LB-{}…", "it"): "Avvio recupero LB-{} fino a LB-{}…",
    ("Starting range scrape LB-{} to LB-{}…", "nl"): "Ophalen LB-{} tot LB-{}…",
}

# Ellipsis patterns that survive as "..." (3 dots) — only fix the ones that
# are truly wrong (… within format strings, not display ellipsis in UI labels)
ELLIPSIS_SOURCES_TO_FIX = {
    "Version:     {version}\nTag:         {tag}\nSize:        {size:,} bytes\n"
    "SHA256:      {sha256}…\n\nLB master:   {lb_master:,}\n  Public:    {public:,}\n"
    "  Private:   {private_:,}\n  Missing:   {missing:,}\nOverrides:   {overrides}\n\n"
    "GitHub release:\n{url}",
}


def fix_file(ts_path: Path, lang: str) -> None:
    tree = ET.parse(ts_path)
    changed = 0

    for msg in tree.iter("message"):
        src_el   = msg.find("source")
        trans_el = msg.find("translation")
        if src_el is None or trans_el is None:
            continue

        source      = src_el.text or ""
        translation = trans_el.text or ""
        original    = translation

        # 1. Manual overrides take priority
        key = (source, lang)
        if key in MANUAL_FIXES:
            translation = MANUAL_FIXES[key]

        # 2. Restore %%N% token corruption
        elif _TOK_RE.search(translation):
            src_tokens = _PH_RE.findall(source)
            translation = _restore_tokens(translation, src_tokens)

        # 3. Fix ellipsis corruption in targeted strings
        if source in ELLIPSIS_SOURCES_TO_FIX:
            translation = translation.replace("{sha256}..", "{sha256}…")

        if translation != original:
            trans_el.text = translation
            changed += 1

    print(f"  [{lang}] {changed} fix(es) applied.")
    ET.indent(tree, space="  ")
    tree.write(str(ts_path), encoding="utf-8", xml_declaration=True)


def main() -> None:
    for lang in LANGUAGES:
        ts_path = LOCALES_DIR / f"losslessbob_{lang}.ts"
        if ts_path.exists():
            fix_file(ts_path, lang)

    # Final check
    print("\n── Final placeholder check ──")
    total_bad = 0
    for lang in LANGUAGES:
        tree = ET.parse(LOCALES_DIR / f"losslessbob_{lang}.ts")
        bad = 0
        for msg in tree.iter("message"):
            src   = msg.findtext("source") or ""
            trans = msg.findtext("translation") or ""
            src_ph   = set(_PH_RE.findall(src))
            trans_ph = set(_PH_RE.findall(trans))
            if src_ph != trans_ph or re.search(r'\{[^}]*\}%', trans):
                bad += 1
                print(f"  [{lang}] {src!r} → {trans!r}")
        print(f"  [{lang}] remaining issues: {bad}")
        total_bad += bad
    print(f"  Total: {total_bad}")


if __name__ == "__main__":
    main()
