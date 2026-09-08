"""Secure credential storage via OS keyring with in-session fallback.

Credentials are never written to SQLite or any file on disk.
When no keyring backend is available the app continues normally,
keeping credentials in the in-process session cache only.

Container deployments can pre-load credentials via secret files mounted at
/run/secrets/ (see _SECRET_MAP for the expected filenames).

Headless callers (cron, systemd) get no D-Bus session, so the OS keyring is
unreachable there. For those, credentials may come from the environment, or
from a KEY=VALUE file the operator writes by hand (see _ENV_MAP for the
variable names). The app only ever reads that file — it is never written here,
so the "no credentials on disk" rule still holds for everything the app itself
stores.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_QBT     = "losslessbob_qbittorrent"
SERVICE_QBT_KEY = "losslessbob_qbittorrent_apikey"
SERVICE_WTRF    = "losslessbob_wtrf"
SERVICE_IA      = "losslessbob_archive_org"
SERVICE_TUIT    = "losslessbob_tuit"
# The TUIT RSS passkey is a bearer secret in its own right: the feed URL needs
# no login, and its <enclosure> links download .torrent files as the account.
# Stored separately from the login so it can be rotated on its own.
SERVICE_TUIT_RSS = "losslessbob_tuit_rss"

# In-session credential cache (cleared when the process exits)
_session: dict[str, tuple[str, str]] = {}

_keyring_ok: bool | None = None  # cached after first probe

# Container secrets — files mounted at /run/secrets/ by the container runtime
_SECRETS_DIR = Path("/run/secrets")
_SECRET_MAP: dict[str, tuple[str, str]] = {
    SERVICE_QBT:     ("qbt_username",    "qbt_password"),
    SERVICE_QBT_KEY: ("qbt_apikey_user", "qbt_apikey"),
    SERVICE_WTRF:    ("wtrf_username",   "wtrf_password"),
    SERVICE_TUIT:    ("tuit_username",   "tuit_password"),
    SERVICE_TUIT_RSS: ("tuit_rss_user",  "tuit_rss_passkey"),
}

# Environment fallback — used when the keyring is unreachable (cron, systemd).
_ENV_MAP: dict[str, tuple[str, str]] = {
    SERVICE_QBT:      ("LB_QBT_USER",      "LB_QBT_PASSWORD"),
    SERVICE_QBT_KEY:  ("LB_QBT_APIKEY_USER", "LB_QBT_APIKEY"),
    SERVICE_WTRF:     ("LB_WTRF_USER",     "LB_WTRF_PASSWORD"),
    SERVICE_IA:       ("LB_IA_ACCESS_KEY", "LB_IA_SECRET_KEY"),
    SERVICE_TUIT:     ("LB_TUIT_USER",     "LB_TUIT_PASSWORD"),
    SERVICE_TUIT_RSS: ("LB_TUIT_RSS_USER", "LB_TUIT_RSS_PASSKEY"),
}

# Operator-written KEY=VALUE file, read when a variable is absent from os.environ.
# Override the location with LB_CREDENTIALS_FILE.
_ENV_FILE_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "credentials.env"
_env_file_cache: dict[str, str] | None = None


def _env_file_path() -> Path:
    """Return the credentials env-file path, honouring LB_CREDENTIALS_FILE."""
    override = os.environ.get("LB_CREDENTIALS_FILE", "").strip()
    return Path(override) if override else _ENV_FILE_DEFAULT


def _load_env_file() -> dict[str, str]:
    """Parse the credentials env file into a dict. Cached; missing file gives {}.

    Accepts ``KEY=VALUE`` lines with optional ``export`` prefix, ``#`` comments,
    and single- or double-quoted values. Malformed lines are skipped.

    Returns:
        Mapping of variable name to value, empty when the file is absent.
    """
    global _env_file_cache
    if _env_file_cache is not None:
        return _env_file_cache
    values: dict[str, str] = {}
    path = _env_file_path()
    try:
        raw = path.read_text()
    except OSError:
        _env_file_cache = values
        return values
    try:
        mode = path.stat().st_mode
        if mode & 0o077:
            logger.warning("%s is readable by other users — chmod 600 it", path)
    except OSError:
        pass
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    _env_file_cache = values
    return values


def _get_from_env(service: str) -> tuple[str, str]:
    """Return (username, password) from the environment or env file, or ('', '')."""
    pair = _ENV_MAP.get(service)
    if not pair:
        return "", ""
    file_values = _load_env_file()
    user = os.environ.get(pair[0]) or file_values.get(pair[0], "")
    secret = os.environ.get(pair[1]) or file_values.get(pair[1], "")
    return user.strip(), secret.strip()


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
    """Return (username, password) from session cache, keyring, env, or Docker secrets.

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
    # Fall back to the environment / operator env file (cron, systemd)
    u, p = _get_from_env(service)
    if u:
        _session[service] = (u, p)
        return u, p
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
        True if credentials exist in session cache, keyring, env, or Docker secrets.
    """
    if service in _session:
        return True
    if keyring_available():
        try:
            import keyring as _kr
            return bool(_kr.get_password(service, "__username__"))
        except Exception:
            pass
    if _get_from_env(service)[0]:
        return True
    pair = _SECRET_MAP.get(service)
    if pair:
        return bool(_read_docker_secret(pair[0]))
    return False
