"""qBittorrent WebUI API v2 integration.

Adds generated .torrent files to a running qBittorrent instance so the
client can begin seeding immediately using the existing files on disk.
save_path is set to the *parent* of each source folder so qBittorrent
locates the folder by name and starts seeding without re-downloading.

Auth priority: if api_key is provided it is used as a Bearer token and
the login/logout flow is skipped entirely.  Fall back to username/password
when no key is set.
"""
import logging
from pathlib import Path

import requests

from backend import db

logger = logging.getLogger(__name__)

_LOGIN_PATH   = "/api/v2/auth/login"
_LOGOUT_PATH  = "/api/v2/auth/logout"
_VERSION_PATH = "/api/v2/app/version"
_ADD_PATH     = "/api/v2/torrents/add"


def _base_url(host: str, port: int) -> str:
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return f"{host}:{port}"


def _make_session(base: str, api_key: str = "") -> requests.Session:
    """Return a requests Session with CSRF and optional Bearer auth headers."""
    session = requests.Session()
    session.headers.update({"Referer": base, "Origin": base})
    if api_key:
        session.headers["Authorization"] = f"Bearer {api_key}"
    return session


def _login(session: requests.Session, base: str, username: str, password: str) -> dict | None:
    """Perform username/password login.  Returns an error dict on failure, None on success."""
    r = session.post(
        base + _LOGIN_PATH,
        data={"username": username, "password": password},
        timeout=10,
    )
    # 204 = bypass-auth (localhost bypass, no body); 200 + "Ok." = normal success
    login_ok = r.status_code == 204 or (r.status_code == 200 and r.text.strip() == "Ok.")
    if not login_ok:
        body = r.text.strip()[:100] or "<empty>"
        return {"ok": False, "error": f"Login rejected (HTTP {r.status_code}): {body}"}
    return None


def test_connection(
    host: str = "localhost",
    port: int = 8080,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Attempt to authenticate and return the qBittorrent application version.

    Args:
        host: qBittorrent WebUI hostname or IP.
        port: WebUI port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), version (str), error (str if ok=False).
    """
    base = _base_url(host, port)
    session = _make_session(base, api_key)
    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return err

        ver_r = session.get(base + _VERSION_PATH, timeout=10)
        if ver_r.status_code in (401, 403):
            return {"ok": False, "error": f"Unauthorized (HTTP {ver_r.status_code}) — check API key or credentials"}
        version = ver_r.text.strip()

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        return {"ok": True, "version": version}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def add_torrent_for_seeding(
    torrent_path: str | Path,
    source_folder: str | Path,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    category: str = "",
    tags: str = "",
    api_key: str = "",
) -> dict:
    """Add a .torrent file to qBittorrent and start seeding immediately.

    Sets save_path to the parent of source_folder so qBittorrent locates
    the existing folder by name and skips downloading.

    Args:
        torrent_path: Path to the .torrent file to upload.
        source_folder: Absolute path to the recording folder on disk.
        host: qBittorrent WebUI host.
        port: qBittorrent WebUI port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        category: Optional category string.
        tags: Optional comma-separated tags string.
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    torrent = Path(torrent_path)
    if not torrent.exists():
        return {"ok": False, "error": f"Torrent file not found: {torrent}"}

    save_path = str(Path(source_folder).parent)
    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return err

        form: dict = {
            "savepath": save_path,
            "autoTMM": "false",
            "sequentialDownload": "false",
        }
        if category:
            form["category"] = category
        if tags:
            form["tags"] = tags

        with torrent.open("rb") as fh:
            files = {"torrents": (torrent.name, fh, "application/x-bittorrent")}
            add_r = session.post(
                base + _ADD_PATH,
                data=form,
                files=files,
                timeout=30,
            )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        body = add_r.text.strip()
        # qBittorrent <5 returns plain "Ok."; qBittorrent 5+ returns JSON
        if body == "Ok.":
            return {"ok": True}
        try:
            j = add_r.json()
            if j.get("failure_count", 1) == 0 and j.get("success_count", 0) > 0:
                return {"ok": True}
        except Exception:
            pass
        return {"ok": False, "error": f"qBittorrent response: {body[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def add_torrent_from_db(
    torrent_db_id: int,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    category: str = "",
    tags: str = "",
    api_key: str = "",
    db_path=None,
) -> dict:
    """Look up a torrents table record by id and add it to qBittorrent.

    Updates added_to_qbt and added_to_qbt_at on success.

    Args:
        torrent_db_id: Primary key of the torrents row.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        category: Optional category.
        tags: Optional tags.
        api_key: API key (qBittorrent 5+). Takes priority over username/password.
        db_path: DB path override for testing.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    conn = db.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM torrents WHERE id=?", (torrent_db_id,)
    ).fetchone()
    if not row:
        return {"ok": False, "error": f"No torrent record with id={torrent_db_id}"}

    result = add_torrent_for_seeding(
        torrent_path=row["torrent_path"],
        source_folder=row["source_folder"],
        host=host,
        port=port,
        username=username,
        password=password,
        category=category,
        tags=tags,
        api_key=api_key,
    )

    if result["ok"]:
        from datetime import datetime
        db.update_torrent_record(
            torrent_db_id,
            {"added_to_qbt": 1, "added_to_qbt_at": datetime.utcnow().isoformat()},
            db_path=db_path,
        )

    return result


def remove_torrent(
    infohash: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Remove a torrent from qBittorrent without deleting the content files.

    Uses POST /api/v2/torrents/delete with deleteFiles=false so only the
    torrent entry is removed from qBittorrent's list; the seeded audio files
    on disk are left untouched.

    Args:
        infohash: Hex infohash of the torrent to remove.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    if not infohash:
        return {"ok": False, "error": "No infohash — cannot identify torrent in qBittorrent"}

    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return err

        r = session.post(
            base + "/api/v2/torrents/delete",
            data={"hashes": infohash.lower(), "deleteFiles": "false"},
            timeout=15,
        )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "error": f"qBittorrent responded HTTP {r.status_code}: {r.text[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
