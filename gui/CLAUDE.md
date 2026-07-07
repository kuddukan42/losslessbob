# gui/ — Legacy PyQt6 GUI

- **Frozen**: gui_next/ is the primary GUI. Bug fixes only here, no new features.
- GUI↔backend calls: QThread workers only, never the main thread.
- User-facing strings changed → `/i18n-update` (Qt `.ts`/`.qm` files in `gui/locales/`).
- Verify with code checks only (`py_compile`); no screenshots or UI automation.
