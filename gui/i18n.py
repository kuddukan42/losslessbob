from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QTranslator

_log = logging.getLogger(__name__)
_LOCALES_DIR = Path(__file__).parent / "locales"
_SUPPORTED = {"de", "fr", "es", "it", "nl"}
_active_translator: QTranslator | None = None


def load_language(app: QCoreApplication, lang_code: str) -> bool:
    """Install a QTranslator for lang_code; returns True on success.

    Pass lang_code='en' or any unsupported code to use English (no file loaded).
    Safe to call at startup before any windows are shown.
    """
    global _active_translator
    if _active_translator is not None:
        app.removeTranslator(_active_translator)
        _active_translator = None

    if lang_code not in _SUPPORTED:
        return lang_code == "en"

    translator = QTranslator(app)
    qm_path = _LOCALES_DIR / f"losslessbob_{lang_code}.qm"
    if not qm_path.exists():
        _log.warning("i18n: .qm file not found for %r at %s", lang_code, qm_path)
        return False

    if translator.load(str(qm_path)):
        app.installTranslator(translator)
        _active_translator = translator
        _log.info("i18n: loaded language %r", lang_code)
        return True

    _log.warning("i18n: failed to load translator for %r", lang_code)
    return False


def supported_languages() -> list[tuple[str, str]]:
    """Return [(code, display_name), ...] in display order, English first."""
    return [
        ("en", "English"),
        ("de", "Deutsch"),
        ("fr", "Français"),
        ("es", "Español"),
        ("it", "Italiano"),
        ("nl", "Nederlands"),
    ]
