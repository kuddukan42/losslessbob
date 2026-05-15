"""qBittorrent WebUI API v2 integration.

Adds generated .torrent files to a running qBittorrent instance so the
client can begin seeding immediately using the existing files on disk.
save_path is set to the *parent* of each source folder so qBittorrent
locates the folder by name and starts seeding without re-downloading.
"""
import logging
from pathlib import Path

import requests

from backend import db
from backend.credentials import SERVICE_QBT, get_credentials

logger = logging.getLogger(__name__)

_LOGIN_PATH  = "/api/v2/auth/login"
_LOGOUT_PATH = "/api/v2/auth/logout"
_VERSION_PATH = "/api/v2/app/version"
_ADD_PATH    = "/api/v2/torrents/add"


def _base_url(host: str, port: int) -> str:
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return f"{host}:{port}"


def test_connection(
    host: str = "localhost",
    port: int = 8080,
    username: str = "",
    password: str = "",
) -> dict:
    """Attempt to log in and return the qBittorrent application version.

    Args:
        host: qBittorrent WebUI hostname or IP.
        port: WebUI port.
        username: WebUI username.
        password: WebUI password.

    Returns:
        Dict with keys: ok (bool), version (str), error (str if ok=False).
    """
    base = _base_url(host, port)
    session = requests.Session()
    try:
        r = session.post(
            base + _LOGIN_PATH,
            data={"username": username, "password": password},
            timeout=10,
        )
        if r.text.strip() != "Ok.":
            return {"ok": False, "error": f"Login rejected: {r.text.strip()[:100]}"}
        ver_r = session.get(base + _VERSION_PATH, timeout=10)
        version = ver_r.text.strip()
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
    username: str,
    password: str,
    category: str = "",
    tags: str = "",
) -> dict:
    """Add a .torrent file to qBittorrent and start seeding immediately.

    Sets save_path to the parent of source_folder so qBittorrent locates
    the existing folder by name and skips downloading.

    Args:
        torrent_path: Path to the .torrent file to upload.
        source_folder: Absolute path to the recording folder on disk.
        host: qBittorrent WebUI host.
        port: qBittorrent WebUI port.
        username: WebUI username.
        password: WebUI password.
        category: Optional category string.
        tags: Optional comma-separated tags string.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    torrent = Path(torrent_path)
    if not torrent.exists():
        return {"ok": False, "error": f"Torrent file not found: {torrent}"}

    save_path = str(Path(source_folder).parent)
    base = _base_url(host, port)
    session = requests.Session()

    try:
        r = session.post(
            base + _LOGIN_PATH,
            data={"username": username, "password": password},
            timeout=10,
        )
        if r.text.strip() != "Ok.":
            return {"ok": False, "error": f"Login rejected: {r.text.strip()[:100]}"}

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

        session.post(base + _LOGOUT_PATH, timeout=5)

        if add_r.text.strip() == "Ok.":
            return {"ok": True}
        return {"ok": False, "error": f"qBittorrent response: {add_r.text.strip()[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def add_torrent_from_db(
    torrent_db_id: int,
    host: str,
    port: int,
    username: str,
    password: str,
    category: str = "",
    tags: str = "",
    db_path=None,
) -> dict:
    """Look up a torrents table record by id and add it to qBittorrent.

    Updates added_to_qbt and added_to_qbt_at on success.

    Args:
        torrent_db_id: Primary key of the torrents row.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username.
        password: WebUI password.
        category: Optional category.
        tags: Optional tags.
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
    )

    if result["ok"]:
        from datetime import datetime
        db.update_torrent_record(
            torrent_db_id,
            {"added_to_qbt": 1, "added_to_qbt_at": datetime.utcnow().isoformat()},
            db_path=db_path,
        )

    return result
