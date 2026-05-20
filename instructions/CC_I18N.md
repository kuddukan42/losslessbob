# Plan: GUI Internationalisation (i18n)

**Target languages:** German (de), French (fr), Spanish (es), Italian (it), Dutch (nl)  
**Scope:** All user-facing strings in `gui/` only — archive content, LB numbers, filenames, and checksums are never translated.  
**Pipeline:** Qt Linguist (`pylupdate6` → `.ts` → `lrelease` → `.qm`)

---

## Context

Friends of the project owner speak German, French, Spanish, Italian, and Dutch. The archive itself is English and stays that way. Only Qt widget text — labels, buttons, tab titles, status messages, tooltips, dialog text, placeholder text — needs translation. All five target languages are LTR, so no layout mirroring is required.

---

## Architecture Overview

```
gui/
  i18n.py                   ← new: translation loader + language helpers
  locales/
    losslessbob_de.ts        ← German source (XML, human-edited)
    losslessbob_fr.ts        ← French
    losslessbob_es.ts        ← Spanish
    losslessbob_it.ts        ← Italian
    losslessbob_nl.ts        ← Dutch
    losslessbob_de.qm        ← compiled binary (gitignored or committed)
    losslessbob_fr.qm
    losslessbob_es.qm
    losslessbob_it.qm
    losslessbob_nl.qm
```

Language preference is stored in the `meta` table as `key='ui_language'`, value = ISO 639-1 code (`de`, `fr`, `es`, `it`, `nl`) or `en` (default, no translator loaded).

A language selector dropdown is added to the **Setup tab** (Preferences section). Changing language shows a "Restart required" notice — dynamic retranslation is out of scope.

---

## New Dependency

```
PyQt6-Qt6  # already present — pylupdate6 ships with PyQt6-tools
PyQt6-tools>=6.4.0   # add to requirements.txt — provides pylupdate6 + lrelease
```

Check first: `pylupdate6 --version`. If already available (some PyQt6 installs include it), skip adding the dep.

---

## TODO-067: i18n Infrastructure

**Files:** `gui/i18n.py` (new), `gui/setup_tab.py`, `backend/app.py`, `main.py` (or whatever launches `QApplication`)  
**Dependencies:** None — do this before string wrapping so the helpers exist.

### Step 1 — `gui/i18n.py`

```python
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QTranslator, QLocale

_LOCALES_DIR = Path(__file__).parent / "locales"
_SUPPORTED = {"de", "fr", "es", "it", "nl"}
_active_translator: QTranslator | None = None


def load_language(app: QCoreApplication, lang_code: str) -> bool:
    """Install a QTranslator for lang_code; returns True on success.

    Pass lang_code='en' or any unsupported code to unload (use English).
    Safe to call at startup before any windows are shown.
    """
    global _active_translator

    # Remove previous translator if any
    if _active_translator is not None:
        app.removeTranslator(_active_translator)
        _active_translator = None

    if lang_code not in _SUPPORTED:
        return lang_code == "en"  # en is valid but needs no file

    translator = QTranslator(app)
    qm_path = _LOCALES_DIR / f"losslessbob_{lang_code}.qm"
    if not qm_path.exists():
        return False

    if translator.load(str(qm_path)):
        app.installTranslator(translator)
        _active_translator = translator
        return True
    return False


def supported_languages() -> list[tuple[str, str]]:
    """Return [(code, display_name), ...] including English."""
    return [
        ("en", "English"),
        ("de", "Deutsch"),
        ("fr", "Français"),
        ("es", "Español"),
        ("it", "Italiano"),
        ("nl", "Nederlands"),
    ]
```

### Step 2 — Load at startup

In `main.py` (or wherever `QApplication` is created), after creating the app and before showing any window:

```python
from gui.i18n import load_language

# Read saved preference from meta table
lang = db.get_meta("ui_language") or "en"
load_language(app, lang)
```

`db.get_meta` must be available before the main window is constructed. If `db` is not importable that early, fall back to reading the SQLite file directly with a one-liner:

```python
import sqlite3
from backend.paths import DB_PATH

def _read_saved_lang() -> str:
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='ui_language'"
            ).fetchone()
            return row[0] if row else "en"
    except Exception:
        return "en"
```

### Step 3 — Language selector in Setup tab

Add a **Preferences** group box to `gui/setup_tab.py` (above or below the existing DB path section):

```
┌─ Preferences ───────────────────────────────────────────┐
│  Interface language:  [ English         ▼ ]             │
│                       ⓘ Restart the app to apply        │
└──────────────────────────────────────────────────────────┘
```

Implementation notes:
- Populate `QComboBox` from `supported_languages()`.
- On selection change, call `backend/app.py` route `POST /api/meta` with `{"key": "ui_language", "value": lang_code}` (this route already exists for meta writes, or add it — see API section below).
- Show a `QLabel` "Restart the app to apply the new language." that is hidden until a change is made.
- Do **not** attempt live retranslation — it requires every widget to re-call `retranslateUi()` which is not implemented in this codebase. Restart is correct and simple.

### Step 4 — Backend: `POST /api/meta` route (if not present)

```python
@app.route("/api/meta", methods=["POST"])
def api_set_meta():
    data = request.get_json(force=True)
    key = data.get("key", "").strip()
    value = str(data.get("value", ""))
    allowed_keys = {"ui_language"}          # whitelist — add keys as needed
    if key not in allowed_keys:
        return jsonify({"error": "key not allowed"}), 400
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    return jsonify({"ok": True})
```

**Done when:** App reads `ui_language` from meta at startup, loads the correct `.qm` if present, and falls back to English silently if the file is missing.

---

## TODO-068: Wrap Strings in All GUI Files

**Files:** All 14 files in `gui/*.py`  
**Dependencies:** TODO-067 complete (i18n.py must exist)

### Rules

| Situation | Before | After |
|-----------|--------|-------|
| Plain string literal in widget call | `QLabel("Clear")` | `QLabel(self.tr("Clear"))` |
| f-string with variables | `f"Added {n} entries"` | `self.tr("Added {} entries").format(n)` |
| f-string with multiple vars | `f"LB-{lb:05d} — {title}"` | `self.tr("LB-{} — {}").format(f"{lb:05d}", title)` |
| Module-level constant (outside class) | `TITLE = "LosslessBob Lookup"` | `TITLE = QCoreApplication.translate("MainWindow", "LosslessBob Lookup")` — or move into a method |
| String that is NOT user-facing | Column keys, API URLs, log messages, SQL, file paths | **Leave as-is** — do not wrap |
| Tooltip / status tip | `setToolTip("Reload the map")` | `setToolTip(self.tr("Reload the map"))` |
| `QMessageBox` text | `QMessageBox.warning(self, "Error", "File not found")` | `QMessageBox.warning(self, self.tr("Error"), self.tr("File not found"))` |
| Tab title in `addTab()` | `addTab(widget, "Search")` | `addTab(widget, self.tr("Search"))` |
| Placeholder text | `setPlaceholderText("Jump to LB…")` | `setPlaceholderText(self.tr("Jump to LB…"))` |

### What NOT to wrap

- Log strings (`logging.debug(...)`, `logging.info(...)`)  
- SQL queries  
- API endpoint strings  
- LB numbers, checksums, filenames — archive data  
- Internal state strings (`"public"`, `"private"`, `"missing"`) that are compared programmatically  
- Class/method docstrings  
- Exception messages that only appear in logs  

### File-by-file checklist

Work through files in this order (smallest → largest to build confidence):

1. `gui/platform_utils.py` — utility module, minimal UI strings
2. `gui/styles.py` — likely none
3. `gui/main_window.py` — menu items, window title, status bar
4. `gui/setup_tab.py` — labels, buttons, the new language selector
5. `gui/theme_tab.py` — labels, buttons
6. `gui/lookup_tab.py` — largest tab, most strings
7. `gui/search_tab.py`
8. `gui/collection_tab.py`
9. `gui/rename_tab.py`
10. `gui/lbdir_tab.py`
11. `gui/bootlegs_tab.py`
12. `gui/dbedit_tab.py`
13. `gui/attachments_tab.py`
14. `gui/map_tab.py`
15. `gui/verify_tab.py`
16. `gui/spectrogram_tab.py`
17. `gui/widgets/*.py` (any widget subclasses)

After each file: run `python -m py_compile gui/<file>.py` before moving on.

**Done when:** `grep -rn '["'"'"'][A-Z]' gui/ --include="*.py"` returns only non-UI strings (archive data, log messages, SQL). Manual spot-check: 10 random UI strings confirmed wrapped.

---

## TODO-069: Generate and Populate Translation Files

**Files:** `gui/locales/*.ts` (5 new files)  
**Dependencies:** TODO-068 complete

### Step 1 — Extract strings with pylupdate6

```bash
pylupdate6 gui/*.py gui/widgets/*.py -ts \
    gui/locales/losslessbob_de.ts \
    gui/locales/losslessbob_fr.ts \
    gui/locales/losslessbob_es.ts \
    gui/locales/losslessbob_it.ts \
    gui/locales/losslessbob_nl.ts
```

This produces XML files with every `tr()` call as an unfinished `<translation type="unfinished">` entry.

### Step 2 — Translate each `.ts` file

Each `.ts` file is XML. Each translatable string looks like:

```xml
<message>
    <source>Clear</source>
    <translation type="unfinished"></translation>
</message>
```

Fill in the `<translation>` element and remove the `type="unfinished"` attribute:

```xml
<message>
    <source>Clear</source>
    <translation>Effacer</translation>   <!-- French example -->
</message>
```

**Translation approach options (choose one or combine):**

1. **AI-assisted batch translation** — feed the raw `.ts` XML to a language model, ask it to fill all translations for one language at a time. Review the output for domain-specific terms.
2. **Qt Linguist GUI** — open each `.ts` file in `linguist` (ships with Qt tools), navigate entry by entry.
3. **Manual text editor** — edit XML directly for small string counts.

**Domain-specific terms to keep in English across all languages** (these are proper nouns or technical IDs in the archive — do not translate):

- LB, LBBCD, LB-NNNNN format  
- "LosslessBob" (product name)  
- "qBittorrent"  
- Status values shown to users: Public, Private, Missing — translate these; they are UI concepts  
- Column headers that are archive field names (Date, Location, Source) — translate these  

**Glossary — suggested translations for key recurring terms:**

| English | Deutsch | Français | Español | Italiano | Nederlands |
|---------|---------|----------|---------|----------|------------|
| Clear | Löschen | Effacer | Borrar | Cancella | Wissen |
| Search | Suchen | Rechercher | Buscar | Cerca | Zoeken |
| Cancel | Abbrechen | Annuler | Cancelar | Annulla | Annuleren |
| Confirm | Bestätigen | Confirmer | Confirmar | Conferma | Bevestigen |
| Error | Fehler | Erreur | Error | Errore | Fout |
| Loading… | Laden… | Chargement… | Cargando… | Caricamento… | Laden… |
| Refresh | Aktualisieren | Actualiser | Actualizar | Aggiorna | Vernieuwen |
| Export | Exportieren | Exporter | Exportar | Esporta | Exporteren |
| Import | Importieren | Importer | Importar | Importa | Importeren |
| Add | Hinzufügen | Ajouter | Agregar | Aggiungi | Toevoegen |
| Delete | Löschen | Supprimer | Eliminar | Elimina | Verwijderen |
| Save | Speichern | Enregistrer | Guardar | Salva | Opslaan |
| Close | Schließen | Fermer | Cerrar | Chiudi | Sluiten |
| Status | Status | Statut | Estado | Stato | Status |
| Public | Öffentlich | Public | Público | Pubblico | Openbaar |
| Private | Privat | Privé | Privado | Privato | Privé |
| Missing | Fehlend | Manquant | Faltante | Mancante | Ontbreekt |
| Collection | Sammlung | Collection | Colección | Collezione | Collectie |
| Wishlist | Wunschliste | Liste de souhaits | Lista de deseos | Lista desideri | Verlanglijst |
| Checksum | Prüfsumme | Somme de contrôle | Suma de verificación | Checksum | Controlesom |

### Step 3 — Compile to `.qm`

```bash
lrelease gui/locales/losslessbob_de.ts -qm gui/locales/losslessbob_de.qm
lrelease gui/locales/losslessbob_fr.ts -qm gui/locales/losslessbob_fr.qm
lrelease gui/locales/losslessbob_es.ts -qm gui/locales/losslessbob_es.qm
lrelease gui/locales/losslessbob_it.ts -qm gui/locales/losslessbob_it.qm
lrelease gui/locales/losslessbob_nl.ts -qm gui/locales/losslessbob_nl.qm
```

`lrelease` reports untranslated strings — aim for 0 warnings before shipping each file.

**Done when:** All 5 `.qm` files exist with 0 untranslated strings reported by `lrelease`.

---

## TODO-070: Integration Testing

**Files:** All modified GUI files, `main.py`  
**Dependencies:** TODO-069 complete

### Test checklist

For each of the 5 languages:

1. Set `ui_language` in meta to the target code.
2. Restart the app.
3. Verify tab titles are translated.
4. Open Lookup tab — verify button labels, column headers, placeholder text.
5. Open Search tab — verify filter labels.
6. Open Collection tab — verify action buttons.
7. Trigger a `QMessageBox` (e.g. try to remove a collection entry) — verify dialog text.
8. Open Setup tab — verify the language selector shows the correct selection.
9. Switch language back to English — restart — verify English restored.

### Regression check

- Run `python -m py_compile gui/*.py` — zero errors.
- Spot-check that LB numbers (e.g. `LB-00042`) are not translated/garbled.
- Verify that status bar checksums and file paths display correctly.

**Done when:** All 5 languages pass the checklist above with no garbled strings, no untranslated placeholders visible to the user, and English still works as default.

---

## File Structure Updates Required

When this feature is implemented, update `PROJECT.md` File Structure to include:

```
gui/
  i18n.py
  locales/
    losslessbob_de.ts
    losslessbob_de.qm
    losslessbob_fr.ts
    losslessbob_fr.qm
    losslessbob_es.ts
    losslessbob_es.qm
    losslessbob_it.ts
    losslessbob_it.qm
    losslessbob_nl.ts
    losslessbob_nl.qm
```

Update Tech Stack table with `PyQt6-tools` if it was added.  
Update Database Schema section: `meta` table gains `ui_language` key.  
Update API routes section with `POST /api/meta` if it was added.

---

## .gitignore Note

`.qm` files are compiled binaries. Two valid approaches:

- **Commit them** — translators don't need the toolchain, users just clone and run. Recommended for this project since translation updates are infrequent.  
- **Gitignore + build step** — keeps the repo clean but requires `lrelease` on every clone. Not recommended for a small team.

Default: **commit the `.qm` files**.

---

## Future Languages

To add a new language later:

1. Run `pylupdate6 ... -ts gui/locales/losslessbob_XX.ts` (merges new strings, preserves existing).
2. Translate the new `.ts` file.
3. `lrelease` it to `.qm`.
4. Add `("XX", "Language Name")` to `supported_languages()` in `gui/i18n.py`.
5. No other code changes needed.
