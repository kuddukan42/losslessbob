# Plan: gui_next i18n — Remaining Implementation Steps

**Created:** 2026-05-29  
**Status:** Done — completed in commit 4df479cf (2026-05-29)  
**Branch:** feat/gui-redesign

---

## What Is Already Done

| Step | File | Notes |
|------|------|-------|
| Install packages | `gui_next/package.json` | i18next + react-i18next added |
| i18n initializer | `src/renderer/src/i18n.ts` | Imports all 6 locale JSON files, calls `i18next.init()` |
| Language in store | `src/renderer/src/store.ts` | `language: string` + `setLanguage` added, persisted in `lbb-settings` |
| Wire in main.tsx | `src/renderer/src/main.tsx` | `import './i18n'` before ReactDOM.createRoot |
| Wire in App.tsx | `src/renderer/src/App.tsx` | `useEffect(() => i18n.changeLanguage(language), [language])` |
| en.json | `src/renderer/src/locales/en.json` | ~665 strings, nested by screen section |

---

## Remaining Steps

### Step 1 — Port Qt translations → locale JSON files

**Files to create:**
- `src/renderer/src/locales/de.json`
- `src/renderer/src/locales/fr.json`
- `src/renderer/src/locales/es.json`
- `src/renderer/src/locales/it.json`
- `src/renderer/src/locales/nl.json`

**Method:** Write a one-off Python port script. The Qt `.ts` XML files in `gui/locales/` use
the English source string as the lookup key. Walk every leaf value in `en.json`, look it up
in the Qt source→translation map, and output the matching JSON.

```python
# scripts/port_qt_translations.py  (run once, then delete)
import xml.etree.ElementTree as ET, json, pathlib, re

LOCALES_DIR = pathlib.Path('gui/locales')
EN_JSON     = pathlib.Path('gui_next/src/renderer/src/locales/en.json')
OUT_DIR     = pathlib.Path('gui_next/src/renderer/src/locales')

def qt_map(lang: str) -> dict[str, str]:
    tree = ET.parse(LOCALES_DIR / f'losslessbob_{lang}.ts')
    m: dict[str, str] = {}
    for msg in tree.iter('message'):
        src  = (msg.findtext('source') or '').strip()
        tran = msg.find('translation')
        if src and tran is not None and tran.get('type') != 'unfinished' and tran.text:
            m[src] = tran.text.strip()
    return m

def walk(node, qt: dict[str, str]) -> object:
    """Recursively translate every leaf string."""
    if isinstance(node, dict):
        return {k: walk(v, qt) for k, v in node.items()}
    if isinstance(node, str):
        # Strip i18next {{var}} markers when looking up in Qt map
        bare = re.sub(r'\s*\{\{[^}]+\}\}', '', node).strip()
        if bare in qt:
            # Re-insert i18next {{var}} markers from the original key
            translated = qt[bare]
            return translated
        return node  # fall back to English
    return node

en = json.loads(EN_JSON.read_text())
for lang in ('de', 'fr', 'es', 'it', 'nl'):
    qt = qt_map(lang)
    out = walk(en, qt)
    (OUT_DIR / f'{lang}.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f'{lang}: done')
```

Run with: `.venv/bin/python3 scripts/port_qt_translations.py`

**Important caveats:**
- Qt `{}` positional placeholders vs i18next `{{varName}}` named — the script strips
  markers during lookup only; the translated values in Qt files use `{}` which will be
  left as-is. After running, do a search for `{}` in the output files and replace with
  the correct `{{varName}}` form from the English key.
- Strings that are new in the Electron UI (not in old PyQt6 GUI) will fall back to English,
  which i18next handles automatically via `fallbackLng: 'en'`.

---

### Step 2 — Add language selector to ScreenSetup

**File:** `src/renderer/src/screens/ScreenSetup.tsx`

Add to the **Preferences** card (near the `resultsPerPage` and `autoScrape` rows):

```tsx
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '../store'

// inside ScreenSetup component:
const { t } = useTranslation()
const { language, setLanguage } = useSettingsStore()

// In the Preferences card JSX:
<div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
  <span style={{ fontSize: 12.5, color: 'var(--lbb-fg2)', minWidth: 140 }}>
    {t('setup.preferences.language')}
  </span>
  <select
    value={language}
    onChange={e => setLanguage(e.target.value)}
    style={{
      height: 28, padding: '0 8px', fontSize: 12.5,
      background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border2)',
      borderRadius: 5, color: 'var(--lbb-fg)', cursor: 'pointer',
      fontFamily: 'inherit',
    }}
  >
    {(['en','de','fr','es','it','nl'] as const).map(code => (
      <option key={code} value={code}>{t(`setup.languages.${code}`)}</option>
    ))}
  </select>
</div>
```

No restart required — `i18n.changeLanguage()` is called reactively by the `useEffect` in
`App.tsx` whenever `language` changes in the store.

---

### Step 3 — Wrap strings with `t()` — screen by screen

For each file: add `const { t } = useTranslation()` to the component, then replace every
hardcoded string with `t('section.key')`. Use `t('key', { var: value })` for strings with
`{{var}}` interpolation.

**Order and key sections to wrap:**

#### AppShell.tsx (`appShell.*`)
- Brand name + version tagline
- All NAV_GROUPS labels (the `label` property and each item's `label` — these are strings
  rendered as-is, so replace with `t()` in the JSX render, not in the constant definition)
- Curator hint block
- Status bar labels: DB, Checksums, Last import, Bootlegs, Synced · idle
- Global search placeholder

#### ScreenHome.tsx (`home.*`)
- Welcome heading, collection count line, DB status line
- Check for DB update / Ingest buttons
- Hero card: PRIMARY WORKFLOW badge, tagline, title, description, drag hint
- Step strip labels (in `STEP_STRIPS` array — replace with `t()` calls or keep as a
  function that returns `t()`-wrapped values)
- Jump tile labels (same pattern as step strips)
- Stat labels: in My Collection, missing entries, on wishlist, bootleg titles, checksums indexed
- Card titles: At a glance, Jump to, Recent activity, Tips
- Table headers + No activity yet
- Toast messages

#### ScreenThemes.tsx (`themes.*`)
- Page title and subtitle
- SetupCard titles: Mode, Density, Accent, Typeface, Advanced, Live preview
- Mode labels: Light, Dark, System
- Density tiles: labels + row-count hints
- Typeface descriptions
- Size label
- Custom token labels (Background, Surface, etc.)
- Status colors note
- Toast messages

#### ScreenMap.tsx (`map.*`)
- Header title, pill labels
- Description text
- Button labels: Copy share URL, Open live map
- Filter section labels: Year range, Ownership, LB status, Search, Display
- Ownership buttons: All, Owned, Not owned
- STATUS_OPTIONS labels (in array — use `t()` in render)
- DISPLAY_OPTS labels (same)
- Apply filters / Reset to defaults buttons
- Selected venue panel labels
- Info hint text

#### ScreenRename.tsx (`rename.*`)
- Header title, subtitle pill, description
- Go to Lookup button
- Empty state text
- STATES labels (the `label` property — replace in render not in constant)
- Filter All button
- Bulk bar: selected count, Select all confident, Apply renames, Applying
- Table headers
- Disambiguate panel
- Dry-run banner
- Toast messages

#### ScreenVerify.tsx (`verify.*`)
- Header title, subtitle pill, description
- Tool labels: FFP, MD5, shntool
- Add folders button
- Rail: Folders label, filter placeholder, No folders / No matches, button labels
- Stat labels: Total, Pass, Mismatch, Missing, Extra, FFP, MD5
- Toolbar: Files label, Problems chip, Show all chip, Open in Finder, Copy report, Generate missing FFP
- StateBadge labels (Pass, Mismatch, etc.)
- shntool warning block
- Empty state messages
- Table headers
- Showing N problem files / show all N link
- Toast messages

#### ScreenLookup.tsx (`lookup.*`)
- Header title, subtitle pill, description
- ListboxModal: title, placeholder, Cancel, Lookup
- Sources rail: label, button labels, Hide _mychecksums, No sources yet, rail button labels
- Status counter bar labels (Matched, Incomplete, etc.) — these come from `STATE_TONE` labels,
  replace in render
- Status bar empty message
- Summary section labels + button labels
- Detail section label + rows count
- Not found info box
- Footer: auto-populate note, Go to Rename, Re-lookup all
- Toast messages

#### ScreenPipeline.tsx (`pipeline.*`)
- Header: Pipeline title, folder count, hint messages
- Status pills: done, ready to rename, need attention
- Stop / Bulk actions buttons
- Bulk menu items: Select all visible, Clear selection, Clear queue
- Apply all renames button
- Queue rail: label, filter placeholder, empty messages, button labels
- Run on selected section + step buttons
- Filter chips: All, Need attention, Ready to rename, Done, Not found, Mismatch, Incomplete
- Filter input placeholder
- Selection bar: selected count, hint, button labels
- Empty state text
- Table headers + step column headers

#### ScreenCollection.tsx (`collection.*`)
- PersonalInfoModal: title, rating label, Tags label/placeholder, Save/Cancel
- ScanPreviewModal: title, skipped note, Already Owned column, Add/Close/Add all buttons
- AddFolderModal: title, instruction, column labels, button labels
- ForumModal: title, Subject/Body labels, Post topic button
- DetailPanel: all labels in META_ROWS, action buttons, History section
- Torrent record buttons: In qBt/Local, Remove qBt, Add qBt, Regen, Relocate, Del file
- Forum record buttons + empty states
- ConfirmDialog titles+bodies for torrent delete and forum remove
- GlobalForumPanel: post count, filter placeholder, column headers, button labels
- GlobalTorrentPanel: torrent count, filter placeholder, column headers, button labels
- Table headers in main table
- Toast messages

#### ScreenSetup.tsx (`setup.*`)
- Page title + subtitle
- SetupCard titles (Database, Master Data, Integrations, Torrent Settings, Preferences, Data purges, Data Packages, Flat file history)
- Database card: all MetaGrid labels, all button labels + states
- CuratorToggle: title, description, MetaGrid labels, button labels
- IntegCard: status pill labels (connected/degraded/disabled), all field labels, Test/Edit/Clear/Save buttons
- Preferences card: results-per-page label + options, auto-scrape label + states
- Language selector (from Step 2)
- Data purges: each label, Purge button, disclaimer text
- Data Packages: all text blocks and button labels
- Flat file history: column headers, No import history, active badge, Reveal button
- Toast messages

---

### Step 4 — TypeScript key safety (optional, do after strings are stable)

**New file:** `src/renderer/src/i18next.d.ts`

```ts
import en from './locales/en.json'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: typeof en }
  }
}
```

This makes `t('bad.key')` a compile error. Do this last so you're not fighting type errors
while iterating on the JSON structure.

---

### Step 5 — Verify

1. `cd gui_next && npm run dev` — app starts, all text renders in English.
2. Open **Setup → Preferences** → change language to **Français** → nav labels, buttons,
   table headers switch immediately without reload.
3. Open **Lookup** screen — verify source labels, toast messages, and table headers are French.
4. Switch back to English — all strings revert correctly.
5. Test each screen briefly — confirm no raw keys visible (a missing key shows as the key path).
6. `npm run build` — TypeScript compile succeeds with no errors.

---

### Step 6 — Update docs

- **CHANGELOG.md** — prepend entry:
  ```
  [2026-05-29] — Add react-i18next translations to gui_next
  Added: gui_next/src/renderer/src/i18n.ts: i18next initializer
  Added: gui_next/src/renderer/src/locales/*.json: en/de/fr/es/it/nl locale files
  Changed: store.ts: language field + setLanguage action
  Changed: main.tsx: import i18n before render
  Changed: App.tsx: sync i18n.changeLanguage on language store change
  Changed: ScreenSetup.tsx: language selector in Preferences card
  Changed: All Screen*.tsx + AppShell.tsx: wrap strings with t()
  ```
- **TODO.md** — mark TODO-??? as Done, move to TODO_DONE.md (create TODO entry if not exists).

---

## Key Files Reference

| Path | Role |
|------|------|
| `gui_next/src/renderer/src/i18n.ts` | i18next init — already done |
| `src/renderer/src/locales/en.json` | Source of truth — already done |
| `src/renderer/src/locales/{de,fr,es,it,nl}.json` | Ported translations — **TODO** |
| `src/renderer/src/store.ts` | language + setLanguage — already done |
| `src/renderer/src/main.tsx` | import i18n — already done |
| `src/renderer/src/App.tsx` | changeLanguage effect — already done |
| `gui/locales/losslessbob_{lang}.ts` | Source Qt translations for porting |
