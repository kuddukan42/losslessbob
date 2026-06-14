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
import os
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

        # qBittorrent <5 → 200 "Ok."; qBittorrent 5+ may return 200 with JSON or 204
        if r.status_code in (200, 204):
            return {"ok": True}
        return {"ok": False, "error": f"qBittorrent responded HTTP {r.status_code}: {r.text[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def set_location(
    infohash: str,
    location: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Update the save path qBittorrent uses for an existing torrent.

    Calls POST /api/v2/torrents/setLocation. qBittorrent re-checks the
    content found at the new location against the torrent's piece hashes;
    if it matches, seeding resumes from the new location without
    re-downloading anything.

    Args:
        infohash: Hex infohash of the torrent to relocate.
        location: New parent directory containing the torrent's content.
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
            base + "/api/v2/torrents/setLocation",
            data={"hashes": infohash.lower(), "location": str(location)},
            timeout=15,
        )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code in (200, 204):
            return {"ok": True}
        if r.status_code in (401, 403):
            return {"ok": False, "error": f"Unauthorized (HTTP {r.status_code})"}
        return {"ok": False, "error": f"qBittorrent responded HTTP {r.status_code}: {r.text[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def find_torrent_by_path(
    folder: str | Path,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
    db_path=None,
) -> dict:
    """Search all torrents in qBittorrent for one whose content is a given folder.

    Useful for folders that were added to qBittorrent outside this app's
    "Add to qBittorrent" workflow, so no infohash is recorded in the
    torrents table. Queries GET /api/v2/torrents/info (no filter) and
    compares each torrent's content_path — or save_path/name for older
    qBittorrent versions that omit content_path — against folder.

    If no exact content_path match is found, folder may have been renamed
    by an earlier pipeline step before qBittorrent was told about it. The
    rename_history table is checked for the most recent row whose new_path
    is folder; if found, its old_path's folder name is the root folder name
    qBittorrent still has recorded, and torrents are searched again for a
    content_path of folder.parent / that name. If that still finds nothing
    (the rename happened in a different directory than the one qBittorrent's
    content_path points at — e.g. the folder was relocated between staging
    directories before the in-place rename), torrents are searched once more
    for any whose content_path basename equals old_path's folder name,
    regardless of directory; this match is only used if exactly one torrent
    qualifies. root_name in the result will differ from folder.name in
    either rename_history case, signalling that the caller should rename the
    torrent's root folder via rename_torrent_root() in addition to relocating
    it.

    Args:
        folder: Absolute path of the folder to look for.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.
        db_path: Optional SQLite path override.

    Returns:
        Dict with keys: ok (bool), infohash (str|None), root_name (str|None),
        error (str|None). infohash/root_name are None when ok=True but no
        matching torrent was found. root_name is the torrent's current root
        folder name as known to qBittorrent (may differ from folder.name).
    """
    target = os.path.normpath(str(folder))

    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return {"ok": False, "infohash": None, "root_name": None, "error": err.get("error")}

        r = session.get(base + "/api/v2/torrents/info", timeout=15)

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code in (401, 403):
            return {"ok": False, "infohash": None, "root_name": None,
                    "error": f"Unauthorized (HTTP {r.status_code})"}
        if r.status_code != 200:
            return {"ok": False, "infohash": None, "root_name": None,
                    "error": f"qBittorrent responded HTTP {r.status_code}"}

        torrents = r.json()

        def _content_path(t: dict) -> str:
            return os.path.normpath(t.get("content_path") or str(Path(t.get("save_path", "")) / t.get("name", "")))

        for t in torrents:
            if _content_path(t) == target:
                return {"ok": True, "infohash": t.get("hash"), "root_name": t.get("name"), "error": None}

        conn = db.get_connection(db_path)
        row = conn.execute(
            "SELECT old_path FROM rename_history WHERE new_path=? ORDER BY renamed_at DESC LIMIT 1",
            (str(folder),),
        ).fetchone()
        if row:
            old_name = Path(row["old_path"]).name
            expected = os.path.normpath(str(Path(folder).parent / old_name))
            for t in torrents:
                if _content_path(t) == expected:
                    return {"ok": True, "infohash": t.get("hash"), "root_name": t.get("name"), "error": None}

            name_matches = [t for t in torrents if Path(_content_path(t)).name == old_name]
            if len(name_matches) == 1:
                t = name_matches[0]
                return {"ok": True, "infohash": t.get("hash"), "root_name": t.get("name"), "error": None}

        return {"ok": True, "infohash": None, "root_name": None, "error": None}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "infohash": None, "root_name": None, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "infohash": None, "root_name": None, "error": str(exc)}


def rename_torrent_root(
    infohash: str,
    old_name: str,
    new_name: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Update qBittorrent's record of a torrent's root folder name.

    Calls POST /api/v2/torrents/renameFolder, which remaps every file under
    old_name (the root folder name qBittorrent currently expects, relative
    to the torrent's save_path) to live under new_name instead. Used after
    set_location() when a folder was renamed by an earlier pipeline step
    before qBittorrent learned about it, so content_path ends up pointing
    at the folder's actual on-disk name.

    Args:
        infohash: Hex infohash of the torrent to rename.
        old_name: Root folder name qBittorrent currently has recorded.
        new_name: Actual root folder name on disk.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return err

        r = session.post(
            base + "/api/v2/torrents/renameFolder",
            data={"hash": infohash.lower(), "oldPath": old_name, "newPath": new_name},
            timeout=15,
        )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code in (200, 204):
            return {"ok": True}
        if r.status_code in (401, 403):
            return {"ok": False, "error": f"Unauthorized (HTTP {r.status_code})"}
        return {"ok": False, "error": f"qBittorrent responded HTTP {r.status_code}: {r.text[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def recheck_torrent(
    infohash: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Trigger a hash recheck for a torrent.

    Calls POST /api/v2/torrents/recheck. Used after set_location() and/or
    rename_torrent_root() to make qBittorrent re-validate its content
    against the new location/name so seeding resumes.

    Args:
        infohash: Hex infohash of the torrent to recheck.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), error (str if ok=False).
    """
    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return err

        r = session.post(
            base + "/api/v2/torrents/recheck",
            data={"hashes": infohash.lower()},
            timeout=15,
        )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code in (200, 204):
            return {"ok": True}
        if r.status_code in (401, 403):
            return {"ok": False, "error": f"Unauthorized (HTTP {r.status_code})"}
        return {"ok": False, "error": f"qBittorrent responded HTTP {r.status_code}: {r.text[:200]}"}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _track_external_torrent(
    lb_number: int, source_folder: str | Path, infohash: str, db_path=None
) -> None:
    """Record a torrent discovered in qBittorrent that wasn't added via this app.

    If a torrents row already exists for this lb_number/source_folder, update
    it with the discovered infohash and mark it as tracked/added. Otherwise
    insert a minimal new row, so future relocations find it via the DB lookup
    in relocate_tracked_torrent() instead of a full API search.

    Args:
        lb_number: LB number the folder belongs to.
        source_folder: Current (post-move) absolute path of the folder.
        infohash: Infohash reported by qBittorrent for this content.
        db_path: Optional SQLite path override.
    """
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    conn = db.get_connection(db_path)
    row = conn.execute(
        "SELECT id FROM torrents WHERE lb_number=? AND source_folder=?",
        (lb_number, str(source_folder)),
    ).fetchone()

    fields = {"infohash": infohash, "added_to_qbt": 1, "added_to_qbt_at": now,
              "qbt_infohash_confirmed": 1}
    if row:
        db.update_torrent_record(row["id"], fields, db_path=db_path)
    else:
        new_id = db.add_torrent_record(lb_number, "", str(source_folder), infohash, db_path=db_path)
        db.update_torrent_record(new_id, fields, db_path=db_path)


def relocate_tracked_torrent(
    lb_number: int,
    old_folder: str | Path,
    new_folder: str | Path,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
    db_path=None,
) -> dict:
    """Point qBittorrent at a folder's new location after it has been filed/moved.

    Looks up torrents rows for lb_number whose source_folder matches
    old_folder and are currently marked added_to_qbt=1 with a known
    infohash. For each match, calls set_location() with the new folder's
    parent directory so qBittorrent finds the moved content and resumes
    seeding (after a hash recheck) instead of re-downloading. On success,
    updates the row's source_folder to new_folder.

    If no DB-tracked torrent matches, falls back to searching qBittorrent
    directly for a torrent whose content is old_folder (via
    find_torrent_by_path()), to also cover folders added to qBittorrent
    outside this app's workflow. A match found this way is relocated and
    recorded in the torrents table for future syncs.

    Args:
        lb_number: LB number the folder belongs to.
        old_folder: Absolute path of the folder before the move.
        new_folder: Absolute path of the folder after the move.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.
        db_path: Optional SQLite path override.

    Returns:
        Dict with keys: ok (bool), synced (bool), error (str|None).
        synced=False with ok=True means no torrent (tracked or otherwise)
        matched this folder, so there was nothing to do.
    """
    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT id, infohash FROM torrents WHERE lb_number=? AND source_folder=? "
        "AND added_to_qbt=1 AND infohash IS NOT NULL AND infohash != ''",
        (lb_number, str(old_folder)),
    ).fetchall()

    new_location = str(Path(new_folder).parent)

    if not rows:
        found = find_torrent_by_path(
            old_folder, host=host, port=port,
            username=username, password=password, api_key=api_key, db_path=db_path,
        )
        if not found["ok"]:
            return {"ok": False, "synced": False, "error": found["error"]}
        if not found["infohash"]:
            return {"ok": True, "synced": False, "error": None}

        result = set_location(
            infohash=found["infohash"], location=new_location,
            host=host, port=port, username=username, password=password, api_key=api_key,
        )
        if not result["ok"]:
            return {"ok": False, "synced": False, "error": result.get("error", "unknown error")}

        new_name = Path(new_folder).name
        if found["root_name"] and found["root_name"] != new_name:
            rename_result = rename_torrent_root(
                found["infohash"], found["root_name"], new_name,
                host=host, port=port, username=username, password=password, api_key=api_key,
            )
            if not rename_result["ok"]:
                return {"ok": False, "synced": True, "error": rename_result.get("error", "unknown error")}

        recheck_torrent(found["infohash"], host=host, port=port,
                         username=username, password=password, api_key=api_key)

        _track_external_torrent(lb_number, new_folder, found["infohash"], db_path)
        return {"ok": True, "synced": True, "error": None}

    errors = []
    synced_any = False
    for row in rows:
        result = set_location(
            infohash=row["infohash"], location=new_location,
            host=host, port=port, username=username, password=password, api_key=api_key,
        )
        if result["ok"]:
            db.update_torrent_record(row["id"], {"source_folder": str(new_folder)}, db_path=db_path)
            synced_any = True
        else:
            errors.append(result.get("error", "unknown error"))

    if errors:
        return {"ok": False, "synced": synced_any, "error": "; ".join(errors)}
    return {"ok": True, "synced": synced_any, "error": None}


def check_torrent_presence(
    infohash: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> dict:
    """Check whether a torrent exists in qBittorrent by infohash.

    Queries GET /api/v2/torrents/info?hashes=<hash>.  An empty result list
    means the torrent is not known to qBittorrent (e.g. removed manually).

    Args:
        infohash: Hex infohash to look up.
        host: qBittorrent WebUI host.
        port: Port.
        username: WebUI username (ignored when api_key is set).
        password: WebUI password (ignored when api_key is set).
        api_key: API key (qBittorrent 5+). Takes priority over username/password.

    Returns:
        Dict with keys: ok (bool), present (bool), error (str if ok=False).
    """
    if not infohash:
        return {"ok": True, "present": False}

    base = _base_url(host, port)
    session = _make_session(base, api_key)

    try:
        if not api_key:
            err = _login(session, base, username, password)
            if err:
                return {**err, "present": False}

        r = session.get(
            base + "/api/v2/torrents/info",
            params={"hashes": infohash.lower()},
            timeout=10,
        )

        if not api_key:
            session.post(base + _LOGOUT_PATH, timeout=5)

        if r.status_code in (401, 403):
            return {"ok": False, "present": False, "error": f"Unauthorized (HTTP {r.status_code})"}
        if r.status_code != 200:
            return {"ok": False, "present": False, "error": f"qBittorrent responded HTTP {r.status_code}"}

        try:
            data = r.json()
            present = isinstance(data, list) and len(data) > 0
        except Exception:
            present = False

        return {"ok": True, "present": present}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "present": False, "error": f"Cannot connect to {base}"}
    except Exception as exc:
        return {"ok": False, "present": False, "error": str(exc)}
