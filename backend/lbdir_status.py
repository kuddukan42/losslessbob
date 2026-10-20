"""LBDIR verify status helpers: step verdicts, split counts and the cached per-LB status
used by the forum-posting gate and the pipeline row builder (TODO-369)."""

import logging
import shutil
from datetime import UTC
from pathlib import Path

from backend import (
    checksum_utils,
)
from backend import db as database
from backend.folder_lb import (
    _find_lbdir_in_folder,
    _resolve_xref_for_folder,
)
from backend.paths import (
    SITE_FILES_DIR,
    find_lbdir_attachment,
)

_log = logging.getLogger(__name__)


def _lbdir_verdict(check: "dict | None") -> dict:
    """Map a :func:`checksum_utils.verify_folder_lbdir` result to a step verdict.

    Single source of truth for the LBDIR step's wire shape, shared by the
    pipeline row builder and the forum-preview status endpoint so both label a
    given manifest check identically.

    Args:
        check: The verify result, or None when the folder has no manifest.

    Returns:
        Dict with ``status`` (ok/warn/bad), ``label``, ``label_key``,
        ``label_params`` and ``check`` (the trimmed counts, or None).
    """
    if not check:
        return {"status": "warn", "label": "No LBDIR", "check": None,
                "label_key": "no_lbdir", "label_params": {}}
    chk_status = check.get("status", "fail")
    n_miss = check.get("missing", 0)
    n_mm = check.get("mismatch", 0)
    n_extra = check.get("extra", 0)
    detail = {"status": chk_status, "total": check.get("total", 0),
              "pass": check.get("pass", 0), "missing": n_miss,
              "mismatch": n_mm, "extra": n_extra}
    if chk_status == "pass":
        return {"status": "ok", "label": "Pass", "check": detail,
                "label_key": "pass", "label_params": {}}
    if chk_status == "missing_files":
        return {"status": "warn", "label": f"Missing {n_miss}", "check": detail,
                "label_key": "missing", "label_params": {"n": n_miss}}
    if chk_status == "extra_files":
        return {"status": "warn", "label": f"Extra {n_extra}", "check": detail,
                "label_key": "extra", "label_params": {"n": n_extra}}
    if chk_status == "shntool_missing":
        return {"status": "warn", "label": "No shntool", "check": detail,
                "label_key": "no_shntool", "label_params": {}}
    return {"status": "bad", "label": f"Fail {n_mm}" if n_mm else "Fail",
            "check": detail, "label_key": "fail_n" if n_mm else "fail",
            "label_params": {"n": n_mm} if n_mm else {}}


def _lbdir_split_counts(check: "dict | None") -> dict:
    """Split a manifest check's per-file verdicts into audio and non-audio buckets.

    The forum workflow judges a folder on its *audio* alone — a missing text
    file is a description, not a red light — so the two populations have to be
    counted separately rather than through the manifest's single total.

    Args:
        check: A :func:`checksum_utils.verify_folder_lbdir` result, or None.

    Returns:
        ``{"audio": {...}, "text": {...}}``, each with ``total``, ``pass``,
        ``missing``, ``mismatch`` and ``extra`` (unlisted disk files, which are
        counted separately and excluded from ``total``).
    """
    buckets = {k: {"total": 0, "pass": 0, "missing": 0, "mismatch": 0, "extra": 0}
               for k in ("audio", "text")}
    for entry in (check or {}).get("files", []):
        name = entry.get("filename", "")
        kind = "audio" if Path(name).suffix.lower() in checksum_utils.AUDIO_EXTS else "text"
        b = buckets[kind]
        overall = entry.get("overall")
        if overall == "extra":
            # Unlisted disk files ride along in the same list but are not
            # manifest entries — the manifest's own totals exclude them, so
            # these must not inflate `total` either.
            b["extra"] += 1
            continue
        b["total"] += 1
        if overall == "pass":
            b["pass"] += 1
        elif overall == "fail":
            b["mismatch"] += 1
        else:
            b["missing"] += 1
    return buckets


def _lbdir_reconcile_text(folder: Path, manifest: "Path | None", lb_number: int) -> dict:
    """Best-effort recovery of a folder's *non-audio* manifest entries.

    Only exact-MD5 matches are acted on, and only for non-audio files: a
    same-name-different-hash match is a different revision of the document and
    must stay a human decision, and audio is never moved or copied behind the
    user's back. Nothing is ever deleted — in-folder matches are moved to the
    path the manifest expects, and entries the site mirror still holds are
    copied in.

    Args:
        folder: The collection folder to repair.
        manifest: Manifest to reconcile against, or None to do nothing.
        lb_number: LB the folder belongs to (selects the site mirror's files).

    Returns:
        ``{"renamed": [...], "copied": [...], "errors": [...]}`` — relative
        paths that were actually restored.
    """
    result: dict[str, list] = {"renamed": [], "copied": [], "errors": []}
    if manifest is None:
        return result

    def _is_text(rel: str) -> bool:
        return Path(rel).suffix.lower() not in checksum_utils.AUDIO_EXTS

    # In-folder renames need a manifest that lives inside the folder — the
    # site-mirror copy has no relative path within it.
    in_folder = _find_lbdir_in_folder(folder, lb_number)
    if in_folder is not None:
        try:
            found = checksum_utils.find_reconcilable_files(folder, in_folder)
            for prop in found.get("proposals", []):
                if prop.get("matched_by") != "md5" or not _is_text(prop["lbdir_rel"]):
                    continue
                dst = folder / prop["lbdir_rel"]
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(folder / prop["disk_rel"]), str(dst))
                    result["renamed"].append(prop["lbdir_rel"])
                except OSError as exc:
                    result["errors"].append({"rel": prop["lbdir_rel"], "error": str(exc)})
        except Exception as exc:
            result["errors"].append({"stage": "rename", "error": str(exc)})

    try:
        site = checksum_utils.find_site_recoverable_files(
            folder, manifest, SITE_FILES_DIR, lb_number)
        for prop in site.get("site_proposals", []):
            if prop.get("matched_by") != "md5" or not _is_text(prop["lbdir_rel"]):
                continue
            src = Path(prop["site_path"])
            try:
                src.relative_to(SITE_FILES_DIR)
            except ValueError:
                continue
            dst = folder / prop["lbdir_rel"]
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                result["copied"].append(prop["lbdir_rel"])
            except OSError as exc:
                result["errors"].append({"rel": prop["lbdir_rel"], "error": str(exc)})
    except Exception as exc:
        result["errors"].append({"stage": "site_copy", "error": str(exc)})

    return result


def _lbdir_forum_view(check: "dict | None", split: dict) -> dict:
    """Audio-first labelling of a manifest check, for the forum post preview.

    ``status`` reflects the audio only, so a folder whose music is intact reads
    green even when a text file is absent; the text population gets its own
    descriptive label instead of dragging the verdict down.

    Args:
        check: The manifest check result, or None when there is no manifest.
        split: The :func:`_lbdir_split_counts` buckets for that check.

    Returns:
        Dict with ``audio_status``, ``audio_label_key``/``_params`` and
        ``text_label_key``/``_params``.
    """
    if not check:
        return {"audio_status": "warn", "audio_label_key": "no_lbdir",
                "audio_label_params": {}, "text_label_key": "text_none",
                "text_label_params": {}}
    a, txt = split["audio"], split["text"]
    if a["total"] == 0:
        audio = ("warn", "audio_none", {})
    elif a["mismatch"]:
        audio = ("bad", "audio_fail", {"n": a["mismatch"]})
    elif a["missing"]:
        audio = ("warn", "audio_missing", {"n": a["missing"]})
    else:
        audio = ("ok", "audio_pass", {"n": a["pass"]})

    if txt["total"] == 0:
        text = ("text_none", {})
    elif txt["mismatch"]:
        text = ("text_mismatch", {"n": txt["mismatch"], "total": txt["total"]})
    elif txt["missing"]:
        text = ("text_missing", {"n": txt["missing"], "total": txt["total"]})
    else:
        text = ("text_pass", {"total": txt["total"]})

    return {"audio_status": audio[0], "audio_label_key": audio[1],
            "audio_label_params": audio[2],
            "text_label_key": text[0], "text_label_params": text[1]}


def _lbdir_status_for_lb(lb_number: int, force: bool = False) -> dict:
    """LBDIR pipeline verdict for an LB's filed collection folder.

    Reuses the pipeline's cached per-folder step verdict
    (``pipeline_folder_state``) when the folder's stat fingerprint still
    matches, so opening the forum preview is free for a folder the pipeline
    already checked; otherwise the manifest is verified live and the result is
    written back into the same cache.

    Args:
        lb_number: LB to resolve a collection folder for.
        force: Ignore any cached verdict and re-verify from disk.

    Missing non-audio entries are auto-reconciled first (see
    :func:`_lbdir_reconcile_text`) and the folder re-verified, so the caller
    sees the state after the recoverable text files have been restored.

    Returns:
        A :func:`_lbdir_verdict` dict (the strict, pipeline-shaped verdict)
        plus the audio-first ``audio_*``/``text_*`` labels, the ``split``
        counts, ``reconciled``, ``folder``, ``manifest``, ``cached`` and
        ``checked_at``. ``status`` is ``"unknown"`` with a ``reason`` of
        ``no_disk_path`` or ``folder_missing`` when there is nothing to check.
    """
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb_number,)
        ).fetchone()
    disk_path = row["disk_path"] if row else None
    if not disk_path:
        return {"status": "unknown", "reason": "no_disk_path", "label": "No folder",
                "label_key": "no_folder", "label_params": {}, "check": None,
                "folder": None, "manifest": None, "cached": False, "checked_at": None}
    folder = Path(disk_path)
    if not folder.is_dir():
        return {"status": "unknown", "reason": "folder_missing", "label": "Folder missing",
                "label_key": "folder_missing", "label_params": {}, "check": None,
                "folder": str(folder), "manifest": None, "cached": False,
                "checked_at": None}

    fingerprint = database.folder_fingerprint(str(folder))
    if not force and fingerprint:
        state = database.get_folder_state(str(folder))
        cached = (state or {}).get("steps", {}).get("lbdir")
        # A verdict cached by the pipeline (or by an older build) carries no
        # audio/text split; re-check rather than report the folder as unknown.
        if state and state.get("fingerprint") == fingerprint and cached and cached.get("split"):
            return {**cached, "folder": str(folder),
                    "manifest": cached.get("manifest"), "cached": True,
                    "reconciled": {"renamed": [], "copied": [], "errors": []},
                    "checked_at": state.get("updated_at")}

    xref = _resolve_xref_for_folder(folder, lb_number)
    manifest = _find_lbdir_in_folder(folder, lb_number, strict=True)
    if manifest is None:
        manifest = find_lbdir_attachment(lb_number, xref=xref)
    if manifest is None:
        manifest = _find_lbdir_in_folder(folder, lb_number)

    check = (checksum_utils.verify_folder_lbdir(str(folder), manifest)
             if manifest else None)

    # Auto-reconcile the non-audio entries before judging the folder: a text
    # file the site mirror still holds is a fetch, not a defect the user has to
    # act on. Audio is never touched, so a re-verify afterwards costs only the
    # hash cache's lookups.
    reconciled = {"renamed": [], "copied": [], "errors": []}
    if check and _lbdir_split_counts(check)["text"]["missing"]:
        reconciled = _lbdir_reconcile_text(folder, manifest, lb_number)
        if reconciled["renamed"] or reconciled["copied"]:
            check = checksum_utils.verify_folder_lbdir(str(folder), manifest)
            fingerprint = database.folder_fingerprint(str(folder))

    split = _lbdir_split_counts(check)
    verdict = _lbdir_verdict(check)
    verdict["manifest"] = manifest.name if manifest else None
    verdict["split"] = split
    verdict.update(_lbdir_forum_view(check, split))
    if fingerprint:
        try:
            database.put_folder_state(str(folder), fingerprint, {"lbdir": dict(verdict)})
        except Exception:
            _log.exception("Could not cache LBDIR verdict for LB-%05d", lb_number)
    from datetime import datetime
    return {**verdict, "folder": str(folder), "cached": False,
            "reconciled": reconciled,
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds")}
