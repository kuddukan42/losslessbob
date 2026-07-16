"""Secure credential storage via OS keyring with in-session fallback.

Credentials are never written to SQLite or any file on disk.
When no keyring backend is available the app continues normally,
keeping credentials in the in-process session cache only.

Container deployments can pre-load credentials via secret files mounted at
/run/secrets/ (see _SECRET_MAP for the expected filenames).
"""
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_QBT     = "losslessbob_qbittorrent"
SERVICE_QBT_KEY = "losslessbob_qbittorrent_apikey"
SERVICE_WTRF    = "losslessbob_wtrf"
SERVICE_IA      = "losslessbob_archive_org"

# In-session credential cache (cleared when the process exits)
_session: dict[str, tuple[str, str]] = {}

_keyring_ok: bool | None = None  # cached after first probe

# Container secrets — files mounted at /run/secrets/ by the container runtime
_SECRETS_DIR = Path("/run/secrets")
_SECRET_MAP: dict[str, tuple[str, str]] = {
    SERVICE_QBT:     ("qbt_username",    "qbt_password"),
    SERVICE_QBT_KEY: ("qbt_apikey_user", "qbt_apikey"),
    SERVICE_WTRF:    ("wtrf_username",   "wtrf_password"),
}


def _read_docker_secret(name: str) -> str:
    """Return the contents of /run/secrets/<name>, or '' if absent."""
    try:
        return (_SECRETS_DIR / name).read_text().strip()
    except OSError:
        return ""


def _get_from_docker_secrets(service: str) -> tuple[str, str]:
    """Return (username, password) from Docker secret files, or ('', '')."""
    pair = _SECRET_MAP.get(service)
    if not pair:
        return "", ""
    return _read_docker_secret(pair[0]), _read_docker_secret(pair[1])


@dataclass
class StorageResult:
    ok: bool
    label: str  # human-readable status for the Setup tab UI


def keyring_available() -> bool:
    """Return True if a functional keyring backend is present. Cached after first call."""
    global _keyring_ok
    if _keyring_ok is not None:
        return _keyring_ok
    try:
        import keyring  # noqa: F401

        # A no-op probe reveals missing/broken backends before the user tries to save
        import keyring as _kr
        _kr.get_password("_losslessbob_probe", "_probe")
        _keyring_ok = True
    except Exception as exc:
        logger.warning("Keyring unavailable: %s", exc)
        _keyring_ok = False
    return _keyring_ok


def _kr_save(service: str, username: str, password: str) -> None:
    """Two-key keyring write: one entry stores the username, another stores the password."""
    import keyring as _kr
    _kr.set_password(service, "__username__", username)
    _kr.set_password(service, username, password)


def save_credentials(service: str, username: str, password: str) -> StorageResult:
    """Store credentials in OS keyring and session cache.

    Always updates the session cache so the app can proceed even when the
    keyring is unavailable.

    Args:
        service: Service constant (SERVICE_QBT or SERVICE_WTRF).
        username: Plain-text username.
        password: Plain-text password.

    Returns:
        StorageResult with a human-readable label for the Setup tab status widget.
    """
    _session[service] = (username, password)
    if keyring_available():
        try:
            _kr_save(service, username, password)
            return StorageResult(ok=True, label="Saved to system keyring")
        except Exception as exc:
            logger.warning("keyring save failed for %s: %s", service, exc)
            return StorageResult(ok=True, label="Session only — keyring write error")
    return StorageResult(ok=True, label="Session only — no keyring available")


def get_credentials(service: str) -> tuple[str, str]:
    """Return (username, password) from session cache, OS keyring, or Docker secrets.

    Args:
        service: Service constant.

    Returns:
        (username, password), both empty strings if nothing is stored.
    """
    if service in _session:
        return _session[service]
    if keyring_available():
        try:
            import keyring as _kr
            username = _kr.get_password(service, "__username__") or ""
            if username:
                password = _kr.get_password(service, username) or ""
                _session[service] = (username, password)
                return username, password
        except Exception as exc:
            logger.warning("keyring get failed for %s: %s", service, exc)
    # Fall back to Docker secrets mounted at /run/secrets/
    u, p = _get_from_docker_secrets(service)
    if u:
        _session[service] = (u, p)
        return u, p
    return "", ""


def delete_credentials(service: str) -> bool:
    """Remove credentials from keyring and session cache.

    Args:
        service: Service constant.

    Returns:
        True if anything was removed.
    """
    had = service in _session
    _session.pop(service, None)
    if keyring_available():
        try:
            import keyring as _kr
            username = _kr.get_password(service, "__username__") or ""
            if username:
                try:
                    _kr.delete_password(service, username)
                except Exception:
                    pass
                had = True
            try:
                _kr.delete_password(service, "__username__")
                had = True
            except Exception:
                pass
        except Exception as exc:
            logger.warning("keyring delete failed for %s: %s", service, exc)
    return had


def credentials_stored(service: str) -> bool:
    """Quick presence check without returning the actual credentials.

    Args:
        service: Service constant.

    Returns:
        True if credentials exist in session cache, keyring, or Docker secrets.
    """
    if service in _session:
        return True
    if keyring_available():
        try:
            import keyring as _kr
            return bool(_kr.get_password(service, "__username__"))
        except Exception:
            pass
    pair = _SECRET_MAP.get(service)
    if pair:
        return bool(_read_docker_secret(pair[0]))
    return False


def prompt_if_missing(service: str, label: str, parent=None) -> tuple[str, str] | None:
    """Return stored credentials, or prompt the user if none are stored.

    Opens a Qt dialog when credentials are absent. Returns None if the user
    cancels. When no keyring is available, the dialog shows a session-only
    warning.

    Args:
        service: Service constant.
        label: Human-readable service name shown in the dialog title.
        parent: Optional Qt parent widget.

    Returns:
        (username, password) tuple, or None if the user cancelled.
    """
    user, pwd = get_credentials(service)
    if user and pwd:
        return user, pwd

    try:
        from PyQt6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLabel,
            QLineEdit,
            QVBoxLayout,
        )

        dlg = QDialog(parent)
        title = f"Credentials — {label}"
        if not keyring_available():
            title += "  (session only)"
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(380)

        root_layout = QVBoxLayout(dlg)

        if not keyring_available():
            warn = QLabel(
                "No system keyring is available. Credentials will only be used "
                "for this session and will not be saved to disk."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #B8860B;")
            root_layout.addWidget(warn)

        form = QFormLayout()
        user_edit = QLineEdit()
        pass_edit = QLineEdit()
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username:", user_edit)
        form.addRow("Password:", pass_edit)
        root_layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        root_layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        u = user_edit.text().strip()
        p = pass_edit.text()
        if not u:
            return None
        _session[service] = (u, p)
        return u, p

    except ImportError:
        logger.error("PyQt6 not available for credential prompt")
        return None
