"""Pipeline routes: file pipeline, folder pipeline run/status/cancel, state, rename, tree scan (TODO-369)."""

import logging
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import (
    checksum_utils,
    scraper,
)
from backend import db as database
from backend.folder_lb import _find_lbdir_in_folder
from backend.lbdir_status import _lbdir_verdict
from backend.paths import find_lbdir_attachment

_log = logging.getLogger(__name__)

bp = Blueprint("pipeline", __name__)


# ── Async pipeline job (TODO-205 Phase 2 / P2) ─────────────────────────────────
_PIPELINE_JOB_LOCK = threading.Lock()
_PIPELINE_JOB: dict = {
    "running": False,
    "folders_total": 0,
    "folders_done": 0,
    "in_progress": [],   # list of folder paths currently processing
    "results": {},       # {folder_path: PipelineRow}
    "errors": [],        # [{folder, message}]
    "steps": [],         # requested steps for this run
    "started_at": None,
    "cancelled": False,
}
_PIPELINE_CANCEL_EVENT = threading.Event()


def get_pipeline_run_status() -> dict:
    """Return a snapshot of the async pipeline job status.

    Module-level helper (TODO-262) for ``backend/activity.py`` — mirrors the
    ``/api/pipeline/run/status`` route body.

    Returns:
        Dict copy of ``_PIPELINE_JOB`` with its nested containers copied too.
    """
    with _PIPELINE_JOB_LOCK:
        snapshot = dict(_PIPELINE_JOB)
        snapshot["results"] = dict(_PIPELINE_JOB["results"])
        snapshot["in_progress"] = list(_PIPELINE_JOB["in_progress"])
        snapshot["errors"] = list(_PIPELINE_JOB["errors"])
    return snapshot


# Blocked file-step codes that need human configuration (a missing recording
# date or an unroutable year) — these escalate a folder to "attn". Every other
# blocked code (mount_offline/dest_exists/db_error/unknown) is transient and
# self-heals on a live re-resolve, so it falls through to the done/shelf path
# (P8, TODO-205 Ph.6).
_TRUE_ATTN_BLOCK_CODES = {"no_date", "no_route"}


def compute_pipeline_severity(
    verify: dict,
    lookup: dict,
    lbdir: dict,
    rename: dict,
    file_status: str,
    file_error_code: "str | None",
    lb_number: "int | None",
) -> str:
    """Compute a pipeline row's severity bucket from its per-step verdicts.

    Pure function extracted from ``_pipeline_process_folder`` (TODO-211) so it is
    directly unit-testable and reusable for warm-start bucket reconstruction
    (TODO-205 Phase 7 ``/api/pipeline/state``) without re-running the pipeline.

    Args:
        verify: Verify step verdict dict (reads ``status``).
        lookup: Lookup step verdict dict (reads ``status``).
        lbdir: LBDIR step verdict dict (reads ``status`` and optional
            ``pending_fetch``).
        rename: Rename step verdict dict (reads ``status`` and optional
            ``label``).
        file_status: The file step's status (``ok``/``warn``/``blocked``/
            ``mute``/…).
        file_error_code: The file step's ``error_code`` when blocked, else None.
        lb_number: The resolved LB number, or None.

    Returns:
        One of ``"attn"``, ``"ready"``, or ``"done"``.
    """
    statuses = [verify["status"], lookup["status"], lbdir["status"], rename["status"]]
    if "bad" in statuses or (
        file_status == "blocked" and file_error_code in _TRUE_ATTN_BLOCK_CODES
    ):
        return "attn"
    if rename.get("label") == "Proposed":
        return "ready"
    if lb_number and (
        rename["status"] == "mute"
        or (lbdir["status"] == "mute" and not lbdir.get("pending_fetch"))
    ):
        # Lookup resolved but downstream steps weren't run yet — not done.
        # A pending_fetch lbdir is exempt: it's parked on a background prefetch,
        # not un-run, so it must fall through to the all-ok/mute → done rule.
        return "attn"
    # A folder is only "done" (in collection) once Lookup has actually
    # identified it: my_collection is keyed by LB#, so no resolved LB# means it
    # was never filed. Without this guard a partial run whose only non-mute step
    # is verify=ok (a re-verify or generate-missing pass, lookup/lbdir/rename all
    # still mute) reads as all-ok/mute and is wrongly promoted to "In collection".
    if lb_number and all(s in ("ok", "mute") for s in statuses) and "ok" in statuses:
        return "done"
    return "attn"


# ── P3 background LBDIR prefetch (TODO-205 Phase 5) ───────────────────────────
_LBDIR_PREFETCH_LOCK = threading.Lock()
_LBDIR_PREFETCH_INFLIGHT: set[int] = set()      # LB numbers currently being fetched
_LBDIR_PREFETCH_POOL: "ThreadPoolExecutor | None" = None   # lazy, max_workers=2


def _lbdir_prefetch_worker(lb_number: int) -> None:
    """Fetch an LB's lbdir attachment in the background (best-effort).

    Mirrors the inline lbdir retrieval in ``_pipeline_process_folder``: scrape the
    LB and, if its lbdir attachment is still missing afterwards, resolve the
    canonical alias and scrape that too. All failures are swallowed — prefetch is
    advisory; the lbdir step's synchronous fallback still covers a missed fetch.

    Args:
        lb_number: The LB number to prefetch the lbdir attachment for.
    """
    try:
        scraper.scrape_entry(lb_number, force=False, download_files=True)
        if find_lbdir_attachment(lb_number) is None:
            canonicals = database.resolve_aliases([lb_number])
            canonical = (
                canonicals[0]
                if canonicals and canonicals[0] != lb_number else None
            )
            if canonical:
                scraper.scrape_entry(canonical, force=False, download_files=True)
    except Exception as exc:
        _log.warning("lbdir prefetch for LB-%05d failed: %s", lb_number, exc)
    finally:
        with _LBDIR_PREFETCH_LOCK:
            _LBDIR_PREFETCH_INFLIGHT.discard(lb_number)


def _submit_lbdir_prefetch(lb_number: int) -> bool:
    """Kick off a best-effort background fetch of an LB's lbdir attachment.

    The lbdir stage is the slowest, least-reliable link (a live
    ``scraper.scrape_entry``). Prefetching it the moment Lookup resolves an LB
    keeps that scrape off the folder's stage chain. Dedup is by LB number, not
    folder: many folders can resolve to the same LB and only one fetch should
    run. ``max_workers=2`` bounds site concurrency; ``scrape_entry``'s own
    politeness (retry backoff, 429 sleep) is reused, so no new rate-limit logic.

    Args:
        lb_number: The canonical or alias LB number to prefetch.

    Returns:
        True if the LB is now (or already was) being fetched; False if the
        submission failed.
    """
    global _LBDIR_PREFETCH_POOL
    with _LBDIR_PREFETCH_LOCK:
        if lb_number in _LBDIR_PREFETCH_INFLIGHT:
            return True  # already inflight — dedupe concurrent folders on one LB
        _LBDIR_PREFETCH_INFLIGHT.add(lb_number)
        try:
            if _LBDIR_PREFETCH_POOL is None:
                _LBDIR_PREFETCH_POOL = ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="lbdir-fetch"
                )
            _LBDIR_PREFETCH_POOL.submit(_lbdir_prefetch_worker, lb_number)
        except Exception:
            _LBDIR_PREFETCH_INFLIGHT.discard(lb_number)
            return False
    return True


@bp.route("/api/pipeline/file/start", methods=["POST"])
def pipeline_file_start() -> Response:
    """Start step 5: file one folder into the collection (async, progress-tracked).

    Body: {folders: [{path: str, lb_number: int, mount_id?: int}]}
    Only the first entry is processed; mount_id, if given, overrides the
    year-routed mount (see the Collect mount picker). Returns {ok, error?,
    error_code?} immediately — poll /api/pipeline/file/status for progress
    and the final result.

    ``xref`` (optional, default 0) is the copy-level fileset id the
    pipeline's lookup step resolved (row.file.xref) — persisted to
    my_collection.xref (FABLE_XREF_INCORPORATION.md D3).

    ``file_mode`` (optional, "move" | "copy") overrides the
    pipeline_file_mode setting for this one job — tools/lb_nc.py sends
    "move" when shuffling a collection folder between mounts, which a
    global "copy" setting must never turn into a duplicate.
    """
    try:
        from backend.filer import start_file_job
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"ok": False, "error": "folders list required", "error_code": "bad_input"}), 400
        item = folders[0]
        path = item.get("path", "")
        lb = item.get("lb_number")
        mount_id = item.get("mount_id")
        xref = item.get("xref")
        if not path or not lb:
            return jsonify({
                "ok": False,
                "error": "path and lb_number are required",
                "error_code": "bad_input",
            }), 400
        file_mode = data.get("file_mode") or database.get_meta("pipeline_file_mode") or "move"
        if file_mode not in ("move", "copy"):
            return jsonify({
                "ok": False,
                "error": "file_mode must be move or copy",
                "error_code": "bad_input",
            }), 400
        result = start_file_job(
            int(lb), path, file_mode=file_mode,
            mount_id_override=int(mount_id) if mount_id is not None else None,
            xref=int(xref) if xref is not None else 0,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/pipeline/file/status", methods=["GET"])
def pipeline_file_status() -> Response:
    """Poll progress of the filing job started via /api/pipeline/file/start."""
    from backend.filer import get_file_job_status
    return jsonify(get_file_job_status())


@bp.route("/api/pipeline/file/preview", methods=["POST"])
def pipeline_file_preview() -> Response:
    """Pre-flight check: resolve destinations without moving anything.

    Body: {folders: [{path: str, lb_number: int, mount_id?: int}, ...]}
    mount_id, if given, previews filing under that mount instead of the
    year-routed default.
    """
    try:
        from backend.filer import _path_reachable, resolve_destination_for_lb
        data = request.get_json() or {}
        folders = data.get("folders", [])
        results = []
        for item in folders:
            path = item.get("path", "")
            lb = item.get("lb_number")
            mount_id = item.get("mount_id")
            if not path or not lb:
                results.append({
                    "path": path,
                    "lb_number": lb,
                    "ok": False,
                    "error": "path and lb_number required",
                    "error_code": "bad_input",
                })
                continue
            r = resolve_destination_for_lb(
                int(lb), path,
                mount_id_override=int(mount_id) if mount_id is not None else None,
            )
            r["path"] = path
            r["lb_number"] = lb
            if r["ok"]:
                r["mount_online"] = _path_reachable(r["mount_root"])
            results.append(r)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Pipeline ─────────────────────────────────────────────────────────────

# TODO-195: stable label_key enums for every pipeline step's `label` text.
# `_FILE_BLOCKED_LABELS` doubles as the error_code -> (label, label_key) map
# for the file step's "blocked" branch, since those error codes are already
# stable enums.
_FILE_BLOCKED_LABELS: dict[str, str] = {
    "no_date":       "No date",
    "no_route":      "No route",
    "mount_offline": "Mount offline",
    "dest_exists":   "Already exists",
    "db_error":      "DB error",
}


def _file_blocked_label(error_code: str | None) -> str:
    return _FILE_BLOCKED_LABELS.get(error_code or "", "Blocked")


def _file_blocked_label_key(error_code: str | None) -> str:
    return error_code if error_code in _FILE_BLOCKED_LABELS else "blocked"


def _pipeline_process_folder(folder_path: str, steps: set, force: bool = False) -> dict:
    """Run one or more pipeline steps on a single folder and return a PipelineRow dict.

    When ``force`` is False the two expensive hash steps (verify, lbdir) may be
    served from the P7 folder-state cache if the folder fingerprint is unchanged;
    ``force=True`` bypasses the cache and recomputes every requested step.
    """
    from backend.folder_naming import (
        apply_nft_suffix,
        lb_tag,
        strip_lb_tag,
        strip_nft_suffix,
    )
    from backend.folder_naming import (
        build_multi_lb_name as _build_multi_name,
    )
    from backend.folder_naming import (
        build_standard_name as _build_name,
    )

    folder = Path(folder_path)
    folder_name = folder.name

    # Rename/LBDIR/File all key off the LB# resolved by Lookup.  Force the
    # lookup step into any run that includes a downstream step so the link
    # between stages never depends on the caller sending the right combo.
    if steps & {"rename", "lbdir", "file"}:
        steps = steps | {"lookup"}

    _mute = {"label_key": "mute", "label_params": {}}
    row: dict = {
        "folder": folder_path,
        "folderName": folder_name,
        "verify":  {"status": "mute", "label": "—", **_mute},
        "lookup":  {"status": "mute", "label": "—", "lb_number": None, **_mute},
        "rename":  {"status": "mute", "label": "—", "proposed": None, **_mute},
        "lbdir":   {"status": "mute", "label": "—", **_mute},
        "file":    {"status": "mute", "label": "—", "error": None, "error_code": None, **_mute},
        "severity": "attn",
        "errors": [],
    }

    if not folder.exists() or not folder.is_dir():
        row["errors"].append({"step": "verify", "message": "Folder not found"})
        row["verify"] = {
            "status": "bad", "label": "Missing",
            "label_key": "missing_folder", "label_params": {},
        }
        return row

    # ── P7 folder-state cache read (design §2b, §3) ──────────────────────
    # The fingerprint comparison below IS the design's R3 revalidation sweep:
    # a per-file os.stat aggregate that changes on any add/remove/rename/
    # in-place edit. Only the two expensive hash steps (verify, lbdir) are
    # ever served from cache; the cheap DB-dependent steps (lookup, rename,
    # file) always run fresh.
    fp_now = database.folder_fingerprint(folder_path)
    state = database.get_folder_state(folder_path)
    cache_valid = (
        (not force)
        and state is not None
        and fp_now is not None
        and state["fingerprint"] == fp_now
    )

    lb_number: int | None = None
    lb_numbers: list[int] = []
    # Copy-level xref (FABLE_XREF_INCORPORATION.md D1/D2/D3): per-LB
    # matched_xref from the lookup summary, populated in Step 2. Read via
    # _xref_for() in the rename/file steps so a re-lookup that resolves a
    # different fileset (e.g. after a DB update) always re-derives it
    # fresh rather than reusing a stale value from an earlier run.
    _lb_xref_map: dict[int, int] = {}

    def _xref_for(lb: int | None) -> int:
        return _lb_xref_map.get(lb, 0) if lb is not None else 0

    # ── Step 1: Verify ────────────────────────────────────────────────────
    if "verify" in steps and cache_valid and "verify" in state["steps"]:
        row["verify"] = {**state["steps"]["verify"], "cached": True}
    elif "verify" in steps:
        vr = checksum_utils.verify_folder(folder_path)
        _vcounts = {
            "total":        vr.get("total", 0),
            "pass":         vr.get("pass", 0),
            "missing":      vr.get("missing", 0),
            "mismatch":     vr.get("mismatch", 0),
            "extra":        vr.get("extra", 0),
            "no_checksums": vr.get("status") == "no_checksums",
            "files":        vr.get("files", []),
        }
        if vr.get("error"):
            row["verify"] = {
                "status": "bad", "label": "Error",
                "label_key": "error", "label_params": {}, **_vcounts,
            }
            row["errors"].append({"step": "verify", "message": vr["error"]})
        elif vr["status"] == "pass":
            row["verify"] = {
                "status": "ok", "label": "Pass",
                "label_key": "pass", "label_params": {}, **_vcounts,
            }
        elif vr["status"] in ("incomplete", "no_checksums"):
            row["verify"] = {
                "status": "warn", "label": "Incomplete",
                "label_key": "incomplete", "label_params": {}, **_vcounts,
            }
        elif vr["status"] == "shntool_missing":
            row["verify"] = {
                "status": "warn", "label": "No shntool", "shntool_missing": True,
                "label_key": "no_shntool", "label_params": {}, **_vcounts,
            }
        else:
            row["verify"] = {
                "status": "bad", "label": "Mismatch",
                "label_key": "mismatch", "label_params": {}, **_vcounts,
            }

    # ── Step 2: Lookup ────────────────────────────────────────────────────
    if "lookup" in steps:
        from backend.checksum_utils import _is_reconciled_extra
        chk_parts: list[str] = []
        _chk_exts = {".ffp", ".md5", ".st5"}
        for f in sorted(folder.rglob("*")):
            if not (f.is_file() and f.suffix.lower() in _chk_exts):
                continue
            # Never ingest sidecars that were deliberately set aside under
            # extras/ (move_extras). Those are superseded or alternate-version
            # checksums; parsing them merges a *different* fileset's hashes
            # into the input and makes the lookup falsely report a multi-LB
            # "perfect match" (e.g. a folder holding one transfer whose extras/
            # still carries the other transfer's .ffp/.md5). See BUG-257.
            if _is_reconciled_extra(f.relative_to(folder).as_posix()):
                continue
            try:
                chk_parts.append(f.read_text(errors="ignore"))
            except OSError:
                pass

        if not chk_parts:
            row["lookup"] = {
                "status": "warn", "label": "No checksums", "lb_number": None,
                "label_key": "no_checksums", "label_params": {},
            }
        else:
            chk_text = "\n".join(chk_parts)
            parsed = database.parse_checksum_text(chk_text)
            if not parsed:
                row["lookup"] = {
                    "status": "bad", "label": "Not found", "lb_number": None,
                    "label_key": "not_found", "label_params": {},
                }
            else:
                summary, detail = database.lookup_checksums(parsed)
                _lb_xref_map = {
                    s["lb_number"]: s.get("matched_xref", 0)
                    for s in summary.get("lb_summary", [])
                }
                alias_map = {
                    r["alias_lb"]: r["canonical_lb"]
                    for r in database.get_lb_aliases()
                }
                for d in detail:
                    d["is_alias_lb"] = d["lb_number"] in alias_map
                    d["canonical_lb"] = alias_map.get(d["lb_number"])
                raw_lb_list: list[int] = summary.get("lb_numbers_found", [])
                lb_list: list[int] = database.resolve_aliases(raw_lb_list)
                alias_resolved_from: list[int] = [
                    lb for lb in raw_lb_list if lb not in set(lb_list)
                ]

                # Sticky folder→LB links (set via "Pin & continue", or
                # auto-written for multi-LB perfect matches) win over the
                # raw checksum match set.
                pinned_links = database.get_folder_links(folder_path)
                pinned_lbs = sorted(r["lb_number"] for r in pinned_links)

                if pinned_lbs:
                    lb_numbers = pinned_lbs
                    lb_number = pinned_lbs[0]
                elif len(lb_list) == 1:
                    lb_numbers = lb_list
                    lb_number = lb_list[0]
                else:
                    lb_numbers = []
                    lb_number = None

                # When multiple LBs all have perfect (MATCHED) status in the
                # summary, the recording is genuinely archived under both
                # entries — auto-link all and proceed rather than blocking.
                if lb_number is None and len(lb_list) > 1 and not pinned_lbs:
                    _lb_summary_map = {
                        s["lb_number"]: s
                        for s in summary.get("lb_summary", [])
                    }
                    _all_perfect = all(
                        _lb_summary_map.get(lb, {}).get("status") == "MATCHED"
                        for lb in lb_list
                    )
                    if _all_perfect:
                        lb_numbers = sorted(lb_list)
                        lb_number = lb_numbers[0]
                        for _lb in lb_numbers:
                            database.set_folder_link(
                                folder_path, _lb,
                                "Auto-linked (multi-LB perfect match)",
                                xref=_xref_for(_lb),
                            )

                # For the single-pin incomplete-match guard below.
                pinned_lb = pinned_lbs[0] if len(pinned_lbs) == 1 else (
                    lb_number if pinned_lbs else None
                )

                # A single resolved LB# is only a true "pass" when every
                # parsed checksum (across all types — ffp/md5/st5) found a
                # home in the DB. A 50% match (e.g. ffp matches but md5
                # doesn't) means the files on disk diverge from the
                # archived copy and needs human review, even though the
                # LB# itself is correctly identified.
                #
                # Test on *distinct unmatched* checksums, not
                # summary["matched"]: when the identical fileset is archived
                # under more than one LB (duplicate entries — even when they
                # collapse to one canonical after alias resolution), every
                # checksum matches N times so summary["matched"] == given*N.
                # A naive matched==given check then never holds and wedges a
                # genuinely-complete folder in "Incomplete match" forever —
                # pinning either LB can't clear it because the guard sees the
                # inflated global count, not the pinned LB's own totals.
                full_match = summary.get("unmatched", 1) == 0
                is_multi_lb = len(lb_numbers) > 1

                if lb_number is not None and (full_match or is_multi_lb):
                    label = (
                        "+".join(f"LB-{lb:05d}" for lb in lb_numbers)
                        if is_multi_lb else f"LB-{lb_number:05d}"
                    )
                    row["lookup"] = {
                        "status": "ok",
                        "label": label,
                        # The matched LB tag(s) are locale-invariant data, not a
                        # translatable sentence — no label_key means the frontend
                        # falls back to this raw label unchanged.
                        "label_key": None,
                        "label_params": {},
                        "lb_number": lb_number,
                        "lb_numbers": lb_numbers,
                        "alias_resolved_from": alias_resolved_from or None,
                        "summary": summary,
                        "detail": detail,
                    }
                elif lb_number is not None:
                    row["lookup"] = {
                        "status": "warn",
                        "label": "Incomplete match",
                        "label_key": "incomplete_match",
                        "label_params": {},
                        "lb_number": lb_number,
                        "lb_numbers": lb_numbers,
                        "alias_resolved_from": alias_resolved_from or None,
                        "summary": summary,
                        "detail": detail,
                    }
                    row["errors"].append({
                        "step": "lookup",
                        "message": (
                            f"{summary['matched']}/{summary['given']} checksums "
                                f"matched for LB-{lb_number:05d}"
                        ),
                    })
                    # Downstream steps (lbdir/rename/file) must stay mute for an
                    # incomplete match — the files on disk haven't been confirmed
                    # against the archive.  Only allow them through if the user
                    # has explicitly pinned this folder (they've reviewed and
                    # accepted the partial match).
                    if pinned_lb is None:
                        lb_number = None
                elif len(lb_list) > 1:
                    row["lookup"] = {"status": "warn", "label": "Conflict",
                                     "label_key": "conflict", "label_params": {},
                                     "lb_number": None, "lb_numbers": [],
                                     "alias_resolved_from": None,
                                     "summary": summary, "detail": detail}
                    row["errors"].append({"step": "lookup", "message": f"Multiple LBs: {lb_list}"})
                else:
                    row["lookup"] = {"status": "bad", "label": "Not found",
                                     "label_key": "not_found", "label_params": {},
                                     "lb_number": None, "lb_numbers": [],
                                     "alias_resolved_from": None,
                                     "summary": summary, "detail": detail}

    # ── P3 prefetch trigger (TODO-205 Phase 5) ───────────────────────────
    # Once Lookup has settled on an LB, warm its lbdir attachment off the
    # stage chain — but only if the folder has no lbdir file and none is
    # cached (both cheap fs/cache checks). Best-effort: a prefetch failure
    # must never break the lookup step.
    if lb_number and "lbdir" in steps:
        try:
            if (_find_lbdir_in_folder(folder, lb_number) is None
                    and find_lbdir_attachment(lb_number, xref=_xref_for(lb_number)) is None):
                _submit_lbdir_prefetch(lb_number)
        except Exception as exc:
            _log.warning("lbdir prefetch trigger failed for LB-%05d: %s",
                         lb_number, exc)

    # ── Step 3: LBDIR retrieve + verify ──────────────────────────────────
    if ("lbdir" in steps and cache_valid and "lbdir" in state["steps"]
            and state["steps"]["lbdir"].get("lb_number") == lb_number
            and not state["steps"]["lbdir"].get("pending_fetch")):
        # Serve the cached manifest verdict only when it was verified against
        # the same LB the lookup just resolved (lookup always runs fresh). A
        # re-pin to a different LB changes lb_number and forces a fresh check.
        # No set_lbdir_verified() here: nothing was re-verified this run, so
        # the collection's "Confirmed" date must not be re-stamped.
        row["lbdir"] = {**state["steps"]["lbdir"], "cached": True}
    elif "lbdir" in steps:
        if lb_number:
            # Scoped to the LB the lookup just resolved: after an override
            # the folder still holds the previous LB's manifest, and
            # verifying against it reports the wrong archive entry until
            # the file is manually removed (BUG-315).
            lbdir_file = _find_lbdir_in_folder(folder, lb_number, strict=True)
            pending_fetch = False
            if not lbdir_file:
                # Try the attachments cache; if uncached, either park on an
                # inflight P3 prefetch or (fallback) scrape synchronously.
                try:
                    xref = _xref_for(lb_number)
                    lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
                    if not lbdir_src:
                        # Resolve canonical alias once — needed both for the
                        # inflight check and the synchronous fallback. Alias
                        # resolution only applies to canonical (xref=0) lookups:
                        # an xref-N miss means the specific fileset attachment
                        # is missing, not that lb_number is an alias (BUG-310).
                        canonicals = database.resolve_aliases([lb_number]) if xref == 0 else []
                        canonical = canonicals[0] if canonicals and canonicals[0] != lb_number else None
                        with _LBDIR_PREFETCH_LOCK:
                            inflight = (
                                lb_number in _LBDIR_PREFETCH_INFLIGHT
                                or (canonical is not None
                                    and canonical in _LBDIR_PREFETCH_INFLIGHT)
                            )
                        if inflight:
                            # A P3 prefetch is running for this LB — don't block
                            # on a live scrape. Park the row instead.
                            pending_fetch = True
                        else:
                            # Safety-net: no prefetch inflight (submission
                            # failed or never fired) — original synchronous
                            # scrape path, unchanged.
                            scraper.scrape_entry(lb_number, force=False, download_files=True)
                            lbdir_src = find_lbdir_attachment(lb_number, xref=xref)
                            if not lbdir_src and canonical:
                                lbdir_src = find_lbdir_attachment(canonical)
                                if not lbdir_src:
                                    scraper.scrape_entry(canonical, force=False, download_files=True)
                                    lbdir_src = find_lbdir_attachment(canonical)
                    if lbdir_src:
                        shutil.copy2(str(lbdir_src), str(folder / lbdir_src.name))
                        lbdir_file = folder / lbdir_src.name
                except Exception:
                    pass

            if not lbdir_file:
                # This LB has no manifest of its own to pull in (common for
                # double-LB pairs — only one entry carries the lbdir). Fall
                # back to whatever manifest the folder already holds rather
                # than reporting nothing, and don't park on a prefetch that
                # has something to verify against meanwhile (BUG-315).
                lbdir_file = _find_lbdir_in_folder(folder, lb_number)
                if lbdir_file:
                    pending_fetch = False

            if pending_fetch:
                # Wire status stays "mute" because the GUI StepStatus type is a
                # closed union; the pending_fetch marker carries the "fetching,
                # don't escalate" semantics for severity + auto-complete.
                row["lbdir"] = {"status": "mute", "label": "Fetching LBDIR…",
                                "label_key": "fetching", "label_params": {},
                                "pending_fetch": True, "check": None}
            elif lbdir_file:
                check = checksum_utils.verify_folder_lbdir(str(folder), lbdir_file)
                row["lbdir"] = _lbdir_verdict(check)
                if check.get("status") == "pass":
                    # If this folder is already an owned collection item (re-check
                    # of an in-place folder), stamp lbdir_verified_at so the Collect
                    # stage's "Confirmed" date reflects this pass. No-op otherwise.
                    database.set_lbdir_verified(str(folder))
            else:
                row["lbdir"] = _lbdir_verdict(None)
        # else: stays mute

    # ── Step 4: Rename proposal ───────────────────────────────────────────
    if "rename" in steps:
        if lb_number:
            entry_data = database.get_entry(lb_number)
            entry = (entry_data or {}).get("entry", {})
            date_str = entry.get("date_str") or ""
            location = (entry.get("location") or "").strip()
            lb_status = database.get_lb_status(lb_number)
            # BUG-176: when the LB entry's location is blank, fall back to
            # bobdylan.com's location for the same date so the canonical
            # "date Location (LB-NNNNN)" order can still be built.
            if date_str and not location:
                from backend.torrent_maker import _parse_date
                iso_date = _parse_date(date_str)
                with database.get_connection() as conn:
                    show = conn.execute(
                        "SELECT location FROM bobdylan_shows WHERE date_str=?", (iso_date,)
                    ).fetchone()
                if show and show["location"]:
                    location = show["location"].strip()
            # Copy-level xref (D2): each LB tag carries the fileset id this
            # folder's checksums matched, re-derived fresh every run so a
            # changed matched_xref (e.g. after a master re-import) always
            # produces a new proposal — see _xref_for() above.
            matched_xrefs = [_xref_for(lb) for lb in lb_numbers]
            if len(lb_numbers) > 1:
                proposed = _build_multi_name(
                    lb_numbers, date_str, location, lb_status, matched_xrefs,
                )
                if not date_str or not location:
                    base = strip_nft_suffix(folder_name)
                    multi_tag = "(" + "+".join(
                        lb_tag(lb, xr)
                        for lb, xr in zip(lb_numbers, matched_xrefs, strict=True)
                    ) + ")"
                    if not base.rstrip().upper().endswith(multi_tag.upper()):
                        untagged = strip_lb_tag(base)
                        proposed = apply_nft_suffix(f"{untagged} {multi_tag}", lb_status)
            else:
                matched_xref = _xref_for(lb_number)
                proposed = _build_name(lb_number, date_str, location, lb_status, matched_xref)
            # BUG-119: when DB has no date/location the standard name falls
            # back to bare LB-NNNNN[-NFT], which would silently strip any
            # date/location already in the folder name.  Use the current
            # folder name as the base and only adjust the NFT suffix and
            # (LB-NNNNN[-xrefYYYYY]) tag — never touch the date/location portion.
            if len(lb_numbers) <= 1 and (not date_str or not location):
                base = strip_nft_suffix(folder_name)
                correct_tag = f"({lb_tag(lb_number, _xref_for(lb_number))})"
                if base.rstrip().lower().endswith(correct_tag.lower()):
                    proposed = apply_nft_suffix(base, lb_status)
                else:
                    # BUG-176: folder is missing (or has a stale) LB# tag —
                    # strip any existing tag (incl. a stale/wild xref suffix)
                    # and append the correct one.
                    untagged = strip_lb_tag(base)
                    proposed = apply_nft_suffix(f"{untagged} {correct_tag}", lb_status)
            if folder_name == proposed:
                row["rename"] = {
                    "status": "ok", "label": "Correct", "proposed": None,
                    "label_key": "correct", "label_params": {},
                }
            else:
                row["rename"] = {
                    "status": "warn", "label": "Proposed", "proposed": proposed,
                    "label_key": "proposed", "label_params": {},
                }
        # else: stays mute — lookup hasn't resolved an LB#

    # ── Step 5: File (resolve only — no filesystem action here) ─────────
    if "file" in steps and lb_number:
        from backend.filer import (
            _path_reachable,
            get_mounts_with_stats,
            resolve_destination_for_lb,
        )
        resolution = resolve_destination_for_lb(lb_number, folder_path)
        if resolution["ok"]:
            mount_online = _path_reachable(resolution["mount_root"])
            if mount_online:
                with database.get_connection() as conn:
                    collection_count = conn.execute(
                        "SELECT COUNT(*) FROM my_collection"
                    ).fetchone()[0]
                    lb_status_row = conn.execute(
                        "SELECT lb_status FROM lb_master WHERE lb_number=?", (lb_number,)
                    ).fetchone()
                    owned_row = conn.execute(
                        "SELECT disk_path, lbdir_verified_at FROM my_collection WHERE lb_number=?",
                        (lb_number,),
                    ).fetchone()
                row["file"] = {
                    "status": "ready",
                    "label": "Ready to file",
                    "label_key": "ready_to_file",
                    "label_params": {},
                    "dest_parent": resolution["dest_parent"],
                    "dest": resolution["dest"],
                    "mount_label": resolution["mount_label"],
                    "year": resolution["year"],
                    "error": None,
                    "error_code": None,
                    "mounts": get_mounts_with_stats(),
                    "recommended_mount": resolution["mount_id"],
                    "routed_year": resolution["year"],
                    "collection_count": collection_count,
                    "lb_status": lb_status_row["lb_status"] if lb_status_row else None,
                    "owned": owned_row is not None,
                    "existing_disk_path": owned_row["disk_path"] if owned_row else None,
                    "lbdir_verified_at": owned_row["lbdir_verified_at"] if owned_row else None,
                    # Copy-level xref (D3): carried by the GUI into
                    # /api/pipeline/file/start so filing persists it to
                    # my_collection.xref.
                    "xref": _xref_for(lb_number),
                }
            else:
                row["file"] = {
                    "status": "blocked",
                    "label": "Mount offline",
                    "label_key": "mount_offline",
                    "label_params": {},
                    "dest_parent": "",
                    "dest": "",
                    "mount_label": resolution["mount_label"],
                    "year": resolution["year"],
                    "error": f"Mount '{resolution['mount_label']}' is offline",
                    "error_code": "mount_offline",
                }
        else:
            row["file"] = {
                "status": "blocked",
                "label": _file_blocked_label(resolution["error_code"]),
                "label_key": _file_blocked_label_key(resolution["error_code"]),
                "label_params": {},
                "dest_parent": "",
                "dest": "",
                "mount_label": "",
                "year": resolution["year"],
                "error": resolution["error"],
                "error_code": resolution["error_code"],
            }
    else:
        row["file"] = {
            "status": "mute", "label": "—", "error": None, "error_code": None,
            "label_key": "mute", "label_params": {},
        }

    # ── Severity (pure fn extracted for testability/warm-start, TODO-211) ──
    # On a partial run the steps that weren't requested stay "mute" in `row`.
    # Fold in the last-known verdicts from the validated folder-state cache so
    # severity reflects the whole folder, not just the step(s) that ran this
    # call — a re-verify of an already-filed folder keeps its "done" state
    # instead of being demoted, and a lone verify pass on an unidentified
    # folder is not promoted to "done".
    def _sev_step(name: str) -> dict:
        cur = row[name]
        if name in steps or cur.get("status", "mute") != "mute":
            return cur
        if cache_valid and name in state["steps"]:
            return state["steps"][name]
        return cur

    _sev_lookup = _sev_step("lookup")
    _sev_lb = lb_number if lb_number is not None else _sev_lookup.get("lb_number")
    row["severity"] = compute_pipeline_severity(
        _sev_step("verify"), _sev_lookup, _sev_step("lbdir"), _sev_step("rename"),
        row["file"]["status"], row["file"].get("error_code"), _sev_lb,
    )

    # ── P7 folder-state cache write (design §4d) ─────────────────────────
    # Recompute the fingerprint here instead of reusing fp_now: the lbdir step
    # may have copied a manifest file into the folder mid-run, which changes
    # the per-file stat aggregate — persisting under the stale entry
    # fingerprint would make the row look invalid on the very next request.
    try:
        fp_post = database.folder_fingerprint(folder_path)
        if fp_post is not None:
            step_results: dict = {}
            for name in steps:
                if name == "lbdir" and row["lbdir"].get("pending_fetch"):
                    # Never persist a pending verdict: the folder fingerprint
                    # doesn't change until the lbdir file is copied in, so a
                    # stored pending verdict would be served cached:true forever
                    # even after the prefetch completes.
                    continue
                verdict = dict(row[name])
                verdict.pop("cached", None)  # transport annotation, never stored
                if name == "lbdir":
                    # Record the LB this manifest check ran against so the
                    # rule-3 guard can reject the verdict after a re-pin.
                    verdict["lb_number"] = lb_number
                step_results[name] = verdict
            database.put_folder_state(folder_path, fp_post, step_results)
    except Exception as exc:
        _log.warning("pipeline: folder-state cache write failed for %s: %s",
                     folder_path, exc)

    return row


@bp.route("/api/pipeline/run", methods=["POST"])
def pipeline_run() -> Response:
    """Run pipeline steps on a list of folders.

    Body: {folders: [path, ...], steps: ["verify","lookup","lbdir","rename","file"],
    force?: bool}. ``force=true`` bypasses the P7 folder-state cache and
    recomputes every requested step.
    Returns:
        JSON {results: [PipelineRow, ...]}
    """
    try:
        data = request.get_json() or {}
        folders: list[str] = data.get("folders", [])
        steps: set[str] = set(data.get("steps", ["verify", "lookup", "lbdir", "rename", "file"]))
        force: bool = bool(data.get("force", False))
        if not folders:
            return jsonify({"error": "folders list required"}), 400
        results = [_pipeline_process_folder(f, steps, force) for f in folders]
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _pipeline_run_async_coordinator(folders: list[str], steps: list[str], workers: int,
                                    force: bool = False) -> None:
    """Drain ``folders`` through ``_pipeline_process_folder`` across worker threads.

    Folders are grouped by source device (``os.stat().st_dev``); a folder whose
    stat fails is still processed, in a ``None`` group of its own (it yields the
    "Folder not found" row from ``_pipeline_process_folder``). One daemon thread
    drains each device group serially (FIFO within the group), while a global
    ``threading.Semaphore(workers)`` caps how many folders are in flight across
    *different* groups at once — at most one worker per device, at most
    ``workers`` folders total, per design doc §4c (parallel hashing on one
    spindle seek-thrashes).

    Cancellation (`_PIPELINE_CANCEL_EVENT`) is cooperative and checked only
    between folders (once before a group's next folder, once more right after
    the semaphore is acquired) — never mid-folder.

    Args:
        folders: Absolute folder paths to process, in caller-supplied order.
        steps: Pipeline step names to run per folder (pre-validated by the
            caller route).
        workers: Global concurrency cap, already clamped to 1-4.
        force: When True, bypass the P7 folder-state cache and recompute
            every requested step for every folder.
    """
    groups: dict[object, list[str]] = {}
    for folder in folders:
        try:
            dev = os.stat(folder).st_dev
        except OSError:
            dev = None
        groups.setdefault(dev, []).append(folder)

    semaphore = threading.Semaphore(workers)
    step_set = set(steps)

    def _process_one(folder: str) -> None:
        with _PIPELINE_JOB_LOCK:
            _PIPELINE_JOB["in_progress"].append(folder)
        try:
            row = _pipeline_process_folder(folder, step_set, force)
        except Exception as exc:
            _log.exception("pipeline async: folder failed: %s", folder)
            with _PIPELINE_JOB_LOCK:
                _PIPELINE_JOB["errors"].append({"folder": folder, "message": str(exc)})
        else:
            with _PIPELINE_JOB_LOCK:
                _PIPELINE_JOB["results"][folder] = row
        finally:
            with _PIPELINE_JOB_LOCK:
                if folder in _PIPELINE_JOB["in_progress"]:
                    _PIPELINE_JOB["in_progress"].remove(folder)
                _PIPELINE_JOB["folders_done"] += 1

    def _drain(group_folders: list[str]) -> None:
        for folder in group_folders:
            if _PIPELINE_CANCEL_EVENT.is_set():
                return
            semaphore.acquire()
            try:
                if _PIPELINE_CANCEL_EVENT.is_set():
                    return
                _process_one(folder)
            finally:
                semaphore.release()

    drain_threads = [
        threading.Thread(target=_drain, args=(group_folders,), daemon=True,
                          name=f"pipeline-drain-{dev}")
        for dev, group_folders in groups.items()
    ]
    for t in drain_threads:
        t.start()
    for t in drain_threads:
        t.join()

    with _PIPELINE_JOB_LOCK:
        _PIPELINE_JOB["running"] = False
        _PIPELINE_JOB["cancelled"] = _PIPELINE_CANCEL_EVENT.is_set()


@bp.route("/api/pipeline/run/start", methods=["POST"])
def pipeline_run_start() -> Response:
    """Start an async pipeline run across multiple folders (TODO-205 Phase 2).

    Body: {folders: [path, ...], steps?: ["verify","lookup","lbdir","rename","file"],
    workers?: int, force?: bool}. ``force=true`` bypasses the P7 folder-state
    cache and recomputes every requested step. Returns immediately with
    {ok: true, started: N} or {ok: false, error, error_code}. Poll
    /api/pipeline/run/status for progress
    and cancel via /api/pipeline/run/cancel. The synchronous /api/pipeline/run
    route is unaffected and keeps working standalone.
    """
    try:
        data = request.get_json() or {}
        folders: list[str] = data.get("folders", [])
        if not folders:
            return jsonify({
                "ok": False,
                "error": "folders list required",
                "error_code": "bad_input",
            }), 400

        allowed_steps = {"verify", "lookup", "lbdir", "rename", "file"}
        steps = data.get("steps", ["verify", "lookup", "lbdir", "rename", "file"])
        if not isinstance(steps, list) or not set(steps).issubset(allowed_steps):
            return jsonify({
                "ok": False,
                "error": "steps must be a subset of verify, lookup, lbdir, rename, file",
                "error_code": "bad_input",
            }), 400

        try:
            workers = int(data.get("workers", 2))
        except (TypeError, ValueError):
            workers = 2
        workers = max(1, min(4, workers))
        force: bool = bool(data.get("force", False))

        with _PIPELINE_JOB_LOCK:
            if _PIPELINE_JOB["running"]:
                return jsonify({
                    "ok": False,
                    "error": "A pipeline job is already in progress",
                    "error_code": "busy",
                })
            _PIPELINE_CANCEL_EVENT.clear()
            _PIPELINE_JOB["running"] = True
            _PIPELINE_JOB["folders_total"] = len(folders)
            _PIPELINE_JOB["folders_done"] = 0
            _PIPELINE_JOB["in_progress"] = []
            _PIPELINE_JOB["results"] = {}
            _PIPELINE_JOB["errors"] = []
            _PIPELINE_JOB["steps"] = list(steps)
            _PIPELINE_JOB["started_at"] = time.time()
            _PIPELINE_JOB["cancelled"] = False

        thread = threading.Thread(
            target=_pipeline_run_async_coordinator,
            args=(folders, list(steps), workers, force),
            daemon=True,
            name="pipeline-run-coordinator",
        )
        thread.start()
        return jsonify({"ok": True, "started": len(folders)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/pipeline/run/status", methods=["GET"])
def pipeline_run_status() -> Response:
    """Poll progress of the async pipeline job started via /api/pipeline/run/start."""
    return jsonify(get_pipeline_run_status())


@bp.route("/api/pipeline/run/cancel", methods=["POST"])
def pipeline_run_cancel() -> Response:
    """Request cancellation of the running async pipeline job, if any.

    Cancellation is cooperative (see `_pipeline_run_async_coordinator`):
    in-flight folders finish, no new folder starts.
    """
    with _PIPELINE_JOB_LOCK:
        was_running = _PIPELINE_JOB["running"]
    _PIPELINE_CANCEL_EVENT.set()
    return jsonify({"ok": True, "was_running": was_running})


@bp.route("/api/pipeline/state", methods=["POST"])
def pipeline_state() -> Response:
    """Return last-known cached verdicts for a set of folders (warm-start).

    TODO-205 Phase 7: lets the GUI paint pipeline buckets immediately after an
    app restart, before any re-run. For each folder whose stored fingerprint
    still matches the folder on disk (design R3 revalidation), the persisted
    per-step verdicts are returned with a freshly computed severity. Folders
    with no cache, an invalidated fingerprint, or an unreadable path are
    omitted — the GUI leaves those rows empty and runs them normally. The file
    step is returned for appearance only and is never trusted (P8); the GUI
    re-resolves it live on the next run.

    Body: {folders: [path, ...]}
    Returns: {ok: true, results: {path: row}} where each row mirrors a
    /api/pipeline/run result (verify/lookup/lbdir/rename/file/severity/errors).
    """
    try:
        data = request.get_json() or {}
        folders = data.get("folders", [])
        if not isinstance(folders, list):
            return jsonify({
                "ok": False,
                "error": "folders must be a list",
                "error_code": "bad_input",
            }), 400

        results: dict[str, dict] = {}
        for folder_path in folders:
            try:
                state = database.get_folder_state(folder_path)
                if state is None:
                    continue
                fp_now = database.folder_fingerprint(folder_path)
                if fp_now is None or state["fingerprint"] != fp_now:
                    continue
                steps = state["steps"]
                mute = {"status": "mute", "label": "—"}
                verify = steps.get("verify", dict(mute))
                lookup = steps.get("lookup", dict(mute))
                lbdir = steps.get("lbdir", dict(mute))
                rename = steps.get("rename", dict(mute))
                file_step = steps.get("file", {
                    "status": "mute", "label": "—",
                    "error": None, "error_code": None,
                })
                lb_number = lookup.get("lb_number") or lbdir.get("lb_number")
                results[folder_path] = {
                    "folder": folder_path,
                    "verify": verify,
                    "lookup": lookup,
                    "lbdir": lbdir,
                    "rename": rename,
                    "file": file_step,
                    "errors": [],
                    "severity": compute_pipeline_severity(
                        verify, lookup, lbdir, rename,
                        file_step.get("status", "mute"),
                        file_step.get("error_code"), lb_number,
                    ),
                }
            except Exception as exc:
                _log.warning("pipeline: warm-start state read failed for %s: %s",
                             folder_path, exc)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/folder/rename", methods=["POST"])
def folder_rename() -> Response:
    """Rename a folder on disk to a new name within the same parent directory.

    Also best-effort syncs qBittorrent (see backend.filer._sync_qbt_location)
    if the folder is already tracked in qBittorrent for a known lb_number,
    resolved from the request body's ``lb_number`` (the pipeline's lookup
    match — set for the typical single-LB-match rename candidate, which has
    not been filed into my_collection yet at rename time, BUG-309), else
    my_collection, else a "Pin & continue" folder link — so an already-added
    torrent keeps seeding under the new name.

    Body: {folder: "/abs/path/to/folder", new_name: "new folder name",
           lb_number?: int}
    Returns:
        JSON {ok: true, new_path: "...", qbt_synced: bool, qbt_error: str|None}
    """
    try:
        from backend.filer import _sync_qbt_location
        from backend.rename import write_rename_log
        data = request.get_json() or {}
        folder = Path(data.get("folder", ""))
        new_name: str = (data.get("new_name") or "").strip()
        lb_number_hint = data.get("lb_number")
        if lb_number_hint is not None:
            try:
                lb_number_hint = int(lb_number_hint)
            except (ValueError, TypeError):
                lb_number_hint = None
        if not folder.exists() or not folder.is_dir():
            return jsonify({"error": "Folder not found"}), 400
        if not new_name or "/" in new_name or "\\" in new_name:
            return jsonify({"error": "Invalid new_name"}), 400
        new_path = folder.parent / new_name
        if new_path.exists():
            return jsonify({"error": f"Target already exists: {new_name}"}), 409
        write_rename_log(
            folder_path=folder,
            old_name=folder.name,
            new_name=new_name,
            source="pipeline",
        )
        try:
            folder.rename(new_path)
        except (FileExistsError, OSError):
            if new_path.exists():
                return jsonify({"error": f"Target already exists: {new_name}"}), 409
            raise
        # BUG-206: sync my_collection if this folder was already filed
        old_disk_path = str(folder)
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT lb_number FROM my_collection WHERE disk_path=?",
                (old_disk_path,),
            ).fetchone()
        if row:
            database.update_collection(
                row["lb_number"],
                {"folder_name": new_name, "disk_path": str(new_path)},
            )
        # BUG-212: a "Pin & continue" link is keyed on the exact folder
        # path — move it forward so the pinned LB# survives the rename
        # instead of being silently lost on the next pipeline run.
        database.rekey_folder_link(old_disk_path, str(new_path))
        # Best-effort qBittorrent sync so a torrent already tracked under
        # the old name keeps seeding instead of erroring on missing files.
        # lb_number: prefer the my_collection row just synced above, else
        # the caller-supplied lookup hint (BUG-309 — the typical single-LB
        # rename candidate has no my_collection row yet, since it isn't
        # filed until later), else a "Pin & continue" folder link.
        lb_number = row["lb_number"] if row else None
        if lb_number is None:
            lb_number = lb_number_hint
        if lb_number is None:
            link = database.get_folder_link(old_disk_path)
            lb_number = link["lb_number"] if link else None
        qbt_synced = False
        qbt_error = None
        if lb_number is not None:
            qbt_synced, qbt_error = _sync_qbt_location(int(lb_number), folder, new_path)
        return jsonify({
            "ok": True, "new_path": str(new_path),
            "qbt_synced": qbt_synced, "qbt_error": qbt_error,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/pipeline/scan-tree", methods=["POST"])
def pipeline_scan_tree() -> Response:
    """Walk a root directory and return subdirectories containing audio files.

    Body: {root: "/abs/path", shallow: false}
    shallow=true limits results to root + immediate subdirectories only (depth 1),
    but each immediate subdirectory is checked for audio at any depth below it
    (e.g. a release folder whose audio lives in CD1/CD2/Extras subfolders still
    counts as containing audio).
    Returns:
        JSON {folders: [str, ...]} sorted alphabetically
    """
    _AUDIO = {'.flac', '.shn', '.mp3', '.wav', '.m4a', '.aiff', '.ape', '.ogg', '.wv'}
    try:
        data = request.get_json() or {}
        root = Path(data.get("root", ""))
        shallow: bool = bool(data.get("shallow", False))
        if not root.is_dir():
            return jsonify({"error": "root is not a directory"}), 400
        found: list[str] = []

        def _has_audio(d: Path) -> bool:
            return any(f.suffix.lower() in _AUDIO for f in d.iterdir() if f.is_file())

        def _has_audio_anywhere(d: Path) -> bool:
            return any(f.suffix.lower() in _AUDIO for f in d.rglob("*") if f.is_file())

        root_has_audio = _has_audio(root)
        if root_has_audio:
            found.append(str(root))
        if shallow:
            if not root_has_audio:
                for child in root.iterdir():
                    if child.is_dir() and _has_audio_anywhere(child):
                        found.append(str(child))
        else:
            for dirpath in root.rglob("*"):
                if dirpath.is_dir() and _has_audio(dirpath):
                    found.append(str(dirpath))
        return jsonify({"folders": sorted(found)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

_LB_RE_SCAN = re.compile(r'LB[-\s]0*(\d+)', re.IGNORECASE)


@bp.route("/api/pipeline/scan-dir", methods=["POST"])
def pipeline_scan_dir() -> Response:
    """Walk a directory and return LB-numbered subdirectories.

    Non-recursive (depth-1) by default; pass recursive=true for a full tree walk.
    Uses folder-name LB matching, not audio-file detection.

    Body: {root: "/abs/path", recursive: false}
    Returns:
        JSON {entries: [{lb_number, folder_name, path}], skipped: int}
    """
    try:
        data = request.get_json() or {}
        root = Path(data.get("root", ""))
        recursive = bool(data.get("recursive", False))
        if not root.is_dir():
            return jsonify({"error": "root is not a directory"}), 400

        skipped = 0

        if recursive:
            by_lb: dict[int, tuple[int, str, str]] = {}
            for child in root.rglob("*"):
                if not child.is_dir():
                    continue
                m = _LB_RE_SCAN.search(child.name)
                if m:
                    lb = int(m.group(1))
                    depth = len(child.relative_to(root).parts)
                    if lb not in by_lb or depth < by_lb[lb][0]:
                        by_lb[lb] = (depth, child.name, str(child))
                else:
                    skipped += 1
            entries = [
                {"lb_number": lb, "folder_name": name, "path": path}
                for lb, (_, name, path) in sorted(by_lb.items())
            ]
        else:
            entries = []
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                m = _LB_RE_SCAN.search(child.name)
                if m:
                    entries.append({
                        "lb_number": int(m.group(1)),
                        "folder_name": child.name,
                        "path": str(child),
                    })
                else:
                    skipped += 1

        return jsonify({"entries": entries, "skipped": skipped})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
