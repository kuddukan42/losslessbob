"""Internet Archive (archive.org) S3-like upload integration.

Uses the IA S3-compatible API directly via requests — no extra dependencies.
Authentication: LOW access_key:secret_key in Authorization header.
"""

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_UPLOAD_STATE: dict = {
    "running": False,
    "lb_number": None,
    "identifier": None,
    "current_file": None,
    "files_done": 0,
    "files_total": 0,
    "bytes_done": 0,
    "bytes_total": 0,
    "status": "idle",   # idle | running | done | failed | stopped
    "error": None,
    "stop_requested": False,
}
_upload_lock = threading.Lock()

IA_S3_BASE = "https://s3.us.archive.org"
IA_DEFAULT_COLLECTION = "opensource_audio"
AUDIO_EXTENSIONS = {".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".m4a", ".wv"}
CHUNK_SIZE = 1 << 20  # 1 MB


def _auth_headers(access_key: str, secret_key: str) -> dict:
    return {"Authorization": f"LOW {access_key}:{secret_key}"}


def test_credentials(access_key: str, secret_key: str) -> dict:
    """Verify IA S3 credentials with an authenticated GET to s3.us.archive.org.

    Args:
        access_key: IA S3 access key.
        secret_key: IA S3 secret key.

    Returns:
        {ok: bool, error: str | None}
    """
    try:
        r = requests.get(IA_S3_BASE, headers=_auth_headers(access_key, secret_key), timeout=15)
        if r.status_code == 200:
            return {"ok": True, "error": None}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def _put_file(identifier: str, filepath: Path, access_key: str, secret_key: str,
              extra_headers: dict | None = None) -> None:
    """Stream-PUT a single file to an IA item.

    Args:
        identifier: IA item identifier.
        filepath: Absolute path to the file to upload.
        access_key: IA S3 access key.
        secret_key: IA S3 secret key.
        extra_headers: Additional headers (metadata, bucket auto-create).

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    url = f"{IA_S3_BASE}/{identifier}/{filepath.name}"
    headers: dict = {
        **_auth_headers(access_key, secret_key),
        "x-archive-auto-make-bucket": "1",
        "x-amz-auto-make-bucket": "1",
    }
    if extra_headers:
        headers.update(extra_headers)

    def _iter() -> bytes:
        with filepath.open("rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                with _upload_lock:
                    _UPLOAD_STATE["bytes_done"] += len(chunk)
                yield chunk

    r = requests.put(url, data=_iter(), headers=headers, timeout=None)
    r.raise_for_status()


def upload_lb(
    lb_number: int,
    folder_path: str,
    access_key: str,
    secret_key: str,
    identifier: str | None = None,
    collection: str = IA_DEFAULT_COLLECTION,
    title: str | None = None,
    subject: str = "Bob Dylan;lossless;bootleg;losslessbob",
    database=None,
) -> dict:
    """Start an async upload of audio files for one LB entry.

    Returns immediately; progress is polled via get_status().

    Args:
        lb_number: LosslessBob entry number.
        folder_path: Absolute path to the local audio folder.
        access_key: IA S3 access key.
        secret_key: IA S3 secret key.
        identifier: IA item identifier (auto-generated as losslessbob-lb-NNNNN if omitted).
        collection: IA collection slug (default 'opensource_audio').
        title: IA item title (auto-generated if omitted).
        subject: Semicolon-separated IA subject tags.
        database: Optional db module — used to record upload history rows.

    Returns:
        {ok: bool, error?: str}
    """
    with _upload_lock:
        if _UPLOAD_STATE["running"]:
            return {"ok": False, "error": "An upload is already in progress"}

    if identifier is None:
        identifier = f"losslessbob-lb-{lb_number:05d}"

    folder = Path(folder_path)
    if not folder.is_dir():
        return {"ok": False, "error": f"Folder not found: {folder_path}"}

    audio_files = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not audio_files:
        return {"ok": False, "error": "No audio files found in folder"}

    total_bytes = sum(f.stat().st_size for f in audio_files)

    with _upload_lock:
        _UPLOAD_STATE.update({
            "running": True,
            "lb_number": lb_number,
            "identifier": identifier,
            "current_file": None,
            "files_done": 0,
            "files_total": len(audio_files),
            "bytes_done": 0,
            "bytes_total": total_bytes,
            "status": "running",
            "error": None,
            "stop_requested": False,
        })

    def _run() -> None:
        db_id: int | None = None
        if database is not None:
            try:
                db_id = database.create_archive_upload(
                    lb_number, identifier, folder_path, len(audio_files)
                )
            except Exception as exc:
                log.warning("archive_org: could not create DB row: %s", exc)

        item_title = title or f"Bob Dylan - LB-{lb_number:05d}"
        subjects = [s.strip() for s in subject.split(";") if s.strip()]

        try:
            for i, fpath in enumerate(audio_files):
                with _upload_lock:
                    if _UPLOAD_STATE["stop_requested"]:
                        _UPLOAD_STATE.update({"running": False, "status": "stopped"})
                        break
                    _UPLOAD_STATE["current_file"] = fpath.name

                # First file carries all item-level metadata headers
                meta: dict | None = None
                if i == 0:
                    meta = {
                        "x-archive-meta-mediatype": "audio",
                        "x-archive-meta-collection": collection,
                        "x-archive-meta-title": item_title,
                    }
                    for j, subj in enumerate(subjects, start=1):
                        meta[f"x-archive-meta{j:02d}-subject"] = subj

                log.info(
                    "archive_org: uploading %s (%d/%d) → %s",
                    fpath.name, i + 1, len(audio_files), identifier,
                )
                _put_file(identifier, fpath, access_key, secret_key, meta)

                with _upload_lock:
                    _UPLOAD_STATE["files_done"] = i + 1

                time.sleep(0.3)

            with _upload_lock:
                final_status = _UPLOAD_STATE["status"]
                files_done = _UPLOAD_STATE["files_done"]

            if final_status != "stopped":
                with _upload_lock:
                    _UPLOAD_STATE.update({"running": False, "status": "done", "current_file": None})
                final_status = "done"

            if database and db_id is not None:
                try:
                    database.finish_archive_upload(db_id, final_status, files_uploaded=files_done)
                except Exception as exc:
                    log.warning("archive_org: could not update DB row: %s", exc)

            log.info("archive_org: upload %s for LB-%05d → %s", final_status, lb_number, identifier)

        except Exception as exc:
            log.error("archive_org: upload error: %s", exc)
            with _upload_lock:
                _UPLOAD_STATE.update({
                    "running": False, "status": "failed",
                    "error": str(exc), "current_file": None,
                })
            if database and db_id is not None:
                try:
                    database.finish_archive_upload(
                        db_id, "failed", error=str(exc),
                        files_uploaded=_UPLOAD_STATE["files_done"],
                    )
                except Exception:
                    pass

    threading.Thread(target=_run, name=f"ia-upload-lb{lb_number}", daemon=True).start()
    return {"ok": True}


def get_status() -> dict:
    """Return a snapshot of the current upload state for GUI polling."""
    with _upload_lock:
        return dict(_UPLOAD_STATE)


def stop_upload() -> None:
    """Request the running upload to stop after the current file."""
    with _upload_lock:
        _UPLOAD_STATE["stop_requested"] = True
