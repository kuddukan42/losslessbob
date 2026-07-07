---
description: Translate and compile Qt .ts/.qm localisation files for the legacy PyQt6 GUI (gui/) — extraction, DeepL, compile
---

# i18n-update — Translate and compile Qt localisation files

Applies to the **legacy PyQt6 GUI** (`gui/`). For the React/Electron GUI
(`gui_next/`), use `/gui-next-i18n` instead.

Run this skill after adding or changing any `self.tr()` strings in GUI files.
It covers the full pipeline: string extraction → DeepL translation → .qm compilation.

## Step 1 — Extract strings with pylupdate6

Run from the project root:

```bash
.venv/bin/pylupdate6 \
  gui/i18n.py gui/main_window.py gui/lookup_tab.py gui/verify_tab.py \
  gui/lbdir_tab.py gui/search_tab.py gui/bootlegs_tab.py gui/scraper_tab.py \
  gui/setup_tab.py gui/attachments_tab.py gui/rename_tab.py gui/spectrogram_tab.py \
  gui/dbedit_tab.py gui/theme_tab.py gui/map_tab.py \
  gui/widgets/state_store.py gui/widgets/sort_keys.py \
  -ts gui/locales/losslessbob_de.ts gui/locales/losslessbob_fr.ts \
      gui/locales/losslessbob_es.ts gui/locales/losslessbob_it.ts \
      gui/locales/losslessbob_nl.ts
```

## Step 2 — Count untranslated strings

For each language file, count `<translation type="unfinished">` entries:

```bash
grep -c 'type="unfinished"' gui/locales/losslessbob_de.ts || echo 0
grep -c 'type="unfinished"' gui/locales/losslessbob_fr.ts || echo 0
grep -c 'type="unfinished"' gui/locales/losslessbob_es.ts || echo 0
grep -c 'type="unfinished"' gui/locales/losslessbob_it.ts || echo 0
grep -c 'type="unfinished"' gui/locales/losslessbob_nl.ts || echo 0
```

Report the counts to the user. If all are zero, skip to Step 4.

## Step 3 — Translate new strings via DeepL

If there are untranslated strings, use the `DEEPL_API_KEY` from the environment
(it is stored in `.claude/settings.local.json` and should be available
automatically; only ask the user if it is genuinely missing). Then run:

```bash
.venv/bin/python3 scripts/translate_ts.py "$DEEPL_API_KEY"
```

After it completes, recount untranslated strings (Step 2). If any remain, report
which languages still have gaps and ask whether to proceed or fix manually.

## Step 4 — Compile .ts → .qm

```bash
.venv/bin/python scripts/build_qm.py
```

Verify the five .qm files were written/updated:

```bash
ls -lh gui/locales/*.qm
```

## Step 5 — Syntax check

```bash
.venv/bin/python3 -m py_compile gui/i18n.py
```
(Bare `python`/`python3` is not on PATH in this environment — always use the venv.)

## Step 6 — Report

Tell the user:
- How many new strings were extracted
- How many were translated per language
- Whether .qm files compiled successfully
- Remind them to commit both `.ts` and `.qm` files together

## Notes

- Do NOT translate log messages, SQL strings, Flask API paths, LB numbers,
  checksum strings, or filenames — these appear in the SKIP_SOURCES set in
  `scripts/translate_ts.py` and pylupdate6 won't extract them if they aren't
  wrapped in `self.tr()`.
- The pure-Python compiler in `scripts/build_qm.py` replaces `lrelease`
  (not installed). Do not attempt to install Qt tools just for this step.
- After any GUI file change, `pylupdate6` (Step 1) is also run automatically
  by a PostToolUse hook — so the .ts files should already be up to date
  when you run this skill. The skill's value is running Steps 3–4.
