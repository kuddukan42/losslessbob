# i18n Implementation Progress

**Last updated:** 2026-05-20  
**Overall:** TODO-067 DONE, TODO-068 DONE (all 15 files incl. scraper_tab), TODO-069 in progress, TODO-070 not started.

---

## TODO-067 — Infrastructure — DONE

All four changes complete and syntax-checked:

- `gui/i18n.py` — new file; `load_language()` and `supported_languages()` helpers
- `main.py` — reads `ui_language` from meta table via direct SQLite at startup (before any windows shown), calls `load_language()`
- `backend/app.py` — added `"ui_language"` to the GET `/api/db/settings` response keys
- `gui/setup_tab.py` — "Preferences" group box added with language `QComboBox` and restart notice label; `_load_language_setting()` and `_on_language_changed()` methods added
- `gui/locales/` — directory created (empty; .ts and .qm files go here in TODO-069)

---

## TODO-068 — String Wrapping — IN PROGRESS

### Rules (quick reference)
- Wrap with `self.tr("...")` — all targets are QWidget subclasses
- f-strings: `f"Added {n} items"` → `self.tr("Added {} items").format(n)`
- Multi-var f-strings: use named `.format()` keys for clarity
- Multi-line tooltips: wrap whole string `self.tr("line1\nline2")`
- `setHorizontalHeaderLabels(CONST_LIST)` → `[self.tr(h) for h in CONST_LIST]`
- **Do NOT wrap:** log messages, SQL, API URLs, dict keys, programmatic state values (`"public"`/`"private"`/`"missing"`), `setObjectName()`, CSS/QSS strings, archive data (LB numbers, checksums, filenames)

### File status

| File | Status | Notes |
|------|--------|-------|
| `styles.py` | ✓ Skip | No user-facing strings |
| `platform_utils.py` | ✓ Skip | No user-facing strings |
| `main_window.py` | ✓ Done | Window title, menus, tab names, status bar, Help/About dialogs |
| `theme_tab.py` | ✓ Done | Presets label, hint, color dialog, font row, Apply button, status label, `self.tr(label_text)` at grid insertion |
| `map_tab.py` | ✓ Done | Map label, Open in Browser, Refresh, fallback notice |
| `verify_tab.py` | ✓ Done | All buttons, labels, headers, context menu, status messages |
| `spectrogram_tab.py` | ✓ Done | All buttons, labels, options group, context menu, status messages, error dialogs |
| `setup_tab.py` | ✓ Done | All sections wrapped including handler methods, dialogs |
| `bootlegs_tab.py` | ✓ Done | Model headerData/tooltips, all build_ui strings, status messages |
| `search_tab.py` | ✓ Done | field_combo refactored to use userData; all strings wrapped |
| `lbdir_tab.py` | ✓ Done | Both dialogs, build_ui, static methods converted to instance methods |
| `rename_tab.py` | ✓ Done | Model, _AliasDialog, all tab strings including reason strings |
| `lookup_tab.py` | ✓ Done | Buttons, tooltips, dialogs, status messages, headers, context menus |
| `collection_tab.py` | ✓ Done | All dialogs, buttons, labels, status msgs, context menus, headers; tab names; _on_inner_tab_changed fixed to use indices |
| `dbedit_tab.py` | ✓ Done | PlaceManualDialog, all build_ui panels, all data/status methods; geo filter fixed to use userData+currentData() |
| `attachments_tab.py` | ✓ Done | All buttons, labels, status messages, context menus, file preview strings |
| `widgets/state_store.py` | ✓ Skip | No user-facing strings (confirmed) |
| `widgets/sort_keys.py` | ✓ Skip | No user-facing strings (confirmed) |

### Suggested order to complete
1. ~~`setup_tab.py`~~ ✓ Done
2. ~~`bootlegs_tab.py`~~ ✓ Done
3. ~~`search_tab.py`~~ ✓ Done
4. ~~`lbdir_tab.py`~~ ✓ Done
5. ~~`rename_tab.py`~~ ✓ Done
6. ~~`lookup_tab.py`~~ ✓ Done
7. ~~`collection_tab.py`~~ ✓ Done
8. ~~`dbedit_tab.py`~~ ✓ Done
9. ~~`attachments_tab.py`~~ ✓ Done
10. ~~`widgets/`~~ ✓ Done (no UI strings in either file)

After each file: `python3 -m py_compile gui/<file>.py`

---

## TODO-069 — Translation Files — Not started

Once all files in TODO-068 are done:

```bash
# From project root
pylupdate6 gui/*.py gui/widgets/*.py -ts \
    gui/locales/losslessbob_de.ts \
    gui/locales/losslessbob_fr.ts \
    gui/locales/losslessbob_es.ts \
    gui/locales/losslessbob_it.ts \
    gui/locales/losslessbob_nl.ts
```

Then fill translations in each `.ts` file (see glossary in `CC_I18N.md`), then compile:

```bash
lrelease gui/locales/losslessbob_de.ts -qm gui/locales/losslessbob_de.qm
# repeat for fr, es, it, nl
```

Check `pylupdate6 --version` first — it ships with `PyQt6-tools`. If missing: `pip install PyQt6-tools`.

---

## TODO-070 — Integration Testing — Not started

See `CC_I18N.md` TODO-070 section for the full checklist.
