# gui-next-i18n — Translate React GUI locale JSON files

Run this skill after:
- Adding or editing `t()` strings in any `gui_next` TSX/TS file
- Adding new keys to `gui_next/src/renderer/src/locales/en.json`
- Any time locale coverage looks incomplete

Locales covered: `de`, `fr`, `es`, `it`, `nl`.
Source of truth: `gui_next/src/renderer/src/locales/en.json` (nested by screen section).
Translation files: `gui_next/src/renderer/src/locales/<lang>.json`.
Script: `scripts/deepl_translate_gui_next.py` — idempotent, only sends strings still matching English.

---

## Step 1 — Count untranslated strings

A string is "untranslated" when the locale JSON value still equals the English source value.
Run from the project root:

```python
# run with: .venv/bin/python3 -c "..."
import json

def leaves(n, p=''):
    if isinstance(n, dict): return [x for k,v in n.items() for x in leaves(v, f'{p}.{k}' if p else k)]
    return [(p, n)]

en = json.loads(open('gui_next/src/renderer/src/locales/en.json').read())
en_l = dict(leaves(en))
total = sum(1 for v in en_l.values() if isinstance(v, str))

for lang in ['de', 'fr', 'es', 'it', 'nl']:
    t = json.loads(open(f'gui_next/src/renderer/src/locales/{lang}.json').read())
    t_l = dict(leaves(t))
    still_en = sum(1 for k,v in en_l.items() if isinstance(v,str) and t_l.get(k)==v)
    print(f'{lang}: {still_en}/{total} still English ({100*still_en//total}%)')
```

Report the per-language counts. If all are zero, skip to Step 3 (verify).

---

## Step 2 — Translate with DeepL

`DEEPL_API_KEY` is stored in `.claude/settings.local.json` and should be available automatically.
Verify it is set:

```bash
echo "${DEEPL_API_KEY:0:8}..."
```

If not set, ask the user for their key. Then run:

```bash
DEEPL_API_KEY=<key> .venv/bin/python3 scripts/deepl_translate_gui_next.py
```

The script:
- Only translates strings that are still identical to the English source (idempotent — safe to re-run).
- Passes a domain context string to DeepL so it knows these are music-archive software UI labels,
  steering away from literal translations (e.g. "Pipeline" as plumbing rather than a data pipeline).
- Protects `{{varName}}` i18next placeholders from being altered by DeepL.
- Batches in groups of 50 strings with a 0.2 s pause between batches.
- Prints DeepL character usage before and after, and the delta for this run.

If the script exits with `DEEPL_API_KEY not set`, the key was not passed correctly.
If DeepL returns an error for a language, report it and continue with the others.

---

## Step 3 — Verify

Re-run the Step 1 count. If any language still shows > 0 untranslated strings after
DeepL, report exactly which keys are affected:

```python
# run with: .venv/bin/python3 -c "..."
import json

def leaves(n, p=''):
    if isinstance(n, dict): return [x for k,v in n.items() for x in leaves(v, f'{p}.{k}' if p else k)]
    return [(p, n)]

en = json.loads(open('gui_next/src/renderer/src/locales/en.json').read())
en_l = dict(leaves(en))

for lang in ['de', 'fr', 'es', 'it', 'nl']:
    t = json.loads(open(f'gui_next/src/renderer/src/locales/{lang}.json').read())
    t_l = dict(leaves(t))
    gaps = [k for k,v in en_l.items() if isinstance(v,str) and t_l.get(k)==v]
    if gaps:
        print(f'{lang}: {len(gaps)} gaps — {gaps[:5]}{"..." if len(gaps)>5 else ""}')
```

Remaining gaps are typically strings in `SKIP_KEYS` (intentionally kept as English across all locales,
e.g. "Pipeline", "Bootlegs") or pure abbreviations like "LBDIR", "LB#". Both are benign — i18next
falls back to English for anything missing, and SKIP_KEYS strings are manually set to their correct
values in each locale file.

---

## Step 4 — Report

Tell the user:
- Per-language before/after untranslated counts
- DeepL character usage for this run
- Any remaining gaps and whether they are benign
- Remind them to commit all six locale files together: `gui_next/src/renderer/src/locales/*.json`

---

## Notes

- **Never translate** log messages, SQL strings, Flask route paths, LB numbers,
  checksum strings, or filenames. These should not appear in the locale JSON files.
- **New TSX screens**: when adding a new screen with `t()` calls, add its keys to
  `en.json` first (nested under a section key matching the screen name), then run
  this skill to populate the other five locales.
- **i18next placeholder syntax**: use `{{varName}}` (double braces) — not `{varName}`.
  The DeepL script protects these tokens automatically.
- **Freezing a string**: if a translated value needs to stay as-is permanently (e.g. an
  established term like "Pipeline" or "Bootlegs"), add its i18n key path to `SKIP_KEYS`
  in `scripts/deepl_translate_gui_next.py` so future runs won't overwrite the manual value.
- **Keys missing entirely** from locale files (not just still-English) are also picked
  up by DeepL on the next run — the script compares all en.json keys against each locale.
