"""lb_missing, lb_problems, entry lineage, curator mode and master data publish/subscribe routes (TODO-369)."""

import importlib
import json
import logging
import sqlite3
import threading
import time
from datetime import UTC
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    stream_with_context,
)

from backend import db as database
from backend.github_upload import _github_upload_asset
from backend.paths import DATA_DIR

_log = logging.getLogger(__name__)

bp = Blueprint("lb_data", __name__)


# Rate-limit for /api/db/backup (#3): reject if last manual backup was < 60 s ago
_last_backup_at: float = 0.0
_backup_lock = threading.Lock()


# ── lb_missing management ─────────────────────────────────────────────────

@bp.route("/api/lb_missing", methods=["GET"])
def lb_missing_list() -> Response:
    """List all entries in lb_missing ordered by lb_number."""
    try:
        return jsonify(database.get_lb_missing_list())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_missing", methods=["POST"])
def lb_missing_add() -> Response:
    """Curator-only. Add an lb_number to lb_missing.

    Body: {lb_number, confirmed_date?, notes?}
    """
    try:
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        body = request.get_json(force=True) or {}
        lb = body.get("lb_number")
        if not isinstance(lb, int) or lb < 1:
            return jsonify({"error": "lb_number must be a positive integer"}), 400
        database.add_lb_missing(
            lb,
            confirmed_date=body.get("confirmed_date", ""),
            notes=body.get("notes", ""),
        )
        return jsonify({"ok": True, "lb_number": lb})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_missing/<int:lb>", methods=["DELETE"])
def lb_missing_remove(lb: int) -> Response:
    """Curator-only. Remove an lb_number from lb_missing."""
    try:
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        database.remove_lb_missing(lb)
        return jsonify({"ok": True, "lb_number": lb})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# ── Dylan Performances API ─────────────────────────────────────────────────


# ── lb_problems API ────────────────────────────────────────────────────────

@bp.route("/api/checksum-disputes", methods=["GET"])
def checksum_disputes_list() -> Response:
    """List LB entries whose stored checksum disagrees with the uploader's file.

    Query params: lb (int) — restrict to one entry; status (str, default
    ``open``, empty for any); all (``1`` to include low-confidence whole-set
    divergences alongside the isolated DB mismatches); reference (``db`` or
    ``lbdir``) — restrict to disputes against that reference; grouped (``1``)
    — return curator-triage findings instead of raw rows: disputes paired by
    disputed value across both references and classified into a ``verdict``
    bucket (``db_error``/``audio_differs``/``retag``/``receipt_unknown``/
    ``lbdir_only``, see TODO-299). A grouped finding's ``ids`` lists every
    ``checksum_disputes.id`` it spans (usually one, sometimes two) — apply a
    verdict via PUT to each id in that list.

    Returns:
        JSON list of checksum_disputes rows, or (``grouped=1``) findings.
    """
    try:
        from backend import checksum_provenance
        lb_q = request.args.get("lb", "").strip()
        show_all = request.args.get("all") == "1"
        status = request.args.get("status", "open").strip() or None
        reference = request.args.get("reference", "").strip() or None
        if request.args.get("grouped") == "1":
            findings = checksum_provenance.get_findings(
                database.get_connection(),
                lb_number=int(lb_q) if lb_q else None,
                status=status,
                reference_kind=reference,
            )
            return jsonify(findings)
        rows = checksum_provenance.get_disputes(
            database.get_connection(),
            lb_number=int(lb_q) if lb_q else None,
            status=status,
            kind=None if show_all else "isolated_mismatch",
            confidence=None if show_all else ("high", "medium"),
            reference_kind=reference,
        )
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/checksum-disputes/<int:dispute_id>", methods=["PUT"])
def checksum_disputes_update(dispute_id: int) -> Response:
    """Curator-only. Record a verdict on a checksum dispute.

    Body: {status: open|confirmed|dismissed, note?: str}

    Returns:
        JSON {ok, id, status}.
    """
    try:
        from backend import checksum_provenance
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        body = request.get_json(force=True) or {}
        status = (body.get("status") or "").strip()
        try:
            updated = checksum_provenance.set_dispute_status(
                database.get_connection(), dispute_id, status, body.get("note")
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not updated:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "id": dispute_id, "status": status})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_problems", methods=["GET"])
def lb_problems_list() -> Response:
    """List lb_problems rows, optionally filtered to a single LB.

    Query param: lb (int) — when supplied, returns only that LB's rows.

    Returns:
        JSON list of {id, lb_number, notes, added}.
    """
    try:
        lb_q = request.args.get("lb", "").strip()
        lb_num = int(lb_q) if lb_q else None
        return jsonify(database.get_lb_problems(lb_num))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_problems", methods=["POST"])
def lb_problems_add() -> Response:
    """Curator-only. Add a problem note for an LB entry.

    Body: {lb_number (int), notes (str), added? (YYYY-MM-DD str)}

    Returns:
        JSON {ok, id, lb_number}.
    """
    try:
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        body = request.get_json(force=True) or {}
        lb = body.get("lb_number")
        notes = (body.get("notes") or "").strip()
        if not isinstance(lb, int) or lb < 1:
            return jsonify({"error": "lb_number must be a positive integer"}), 400
        if not notes:
            return jsonify({"error": "notes must not be empty"}), 400
        new_id = database.add_lb_problem(lb, notes, body.get("added"))
        return jsonify({"ok": True, "id": new_id, "lb_number": lb})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_problems/<int:problem_id>", methods=["PUT"])
def lb_problems_update(problem_id: int) -> Response:
    """Update the notes on an lb_problems row.

    Body: {notes (str)}

    Returns:
        JSON {ok, id}.
    """
    try:
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        body = request.get_json(force=True) or {}
        notes = (body.get("notes") or "").strip()
        if not notes:
            return jsonify({"error": "notes must not be empty"}), 400
        database.update_lb_problem(problem_id, notes)
        return jsonify({"ok": True, "id": problem_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/lb_problems/<int:problem_id>", methods=["DELETE"])
def lb_problems_delete(problem_id: int) -> Response:
    """Curator-only. Delete an lb_problems row by id.

    Returns:
        JSON {ok, id}.
    """
    try:
        if not database.is_curator():
            return jsonify({"error": "curator_required"}), 403
        database.delete_lb_problem(problem_id)
        return jsonify({"ok": True, "id": problem_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Entry lineage ──────────────────────────────────────────────────────────

@bp.route("/api/lineage/<int:lb>", methods=["GET"])
def lineage_get(lb: int) -> Response:
    """Return the entry_lineage row for one LB number.

    Returns:
        JSON of the lineage row on success, or ``{"error": "not found"}``
        with 404 when no row has been parsed yet for this LB number.
    """
    try:
        row = database.get_lineage(lb)
        if row is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(row)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/folder_naming/standard/<int:lb>", methods=["GET"])
def folder_naming_standard(lb: int) -> Response:
    """Return the canonical folder name for an LB entry.

    Returns:
        JSON: standard_name (str), lb_status (str|null), nft (bool).
    """
    try:
        from backend.folder_naming import build_standard_name
        result = database.get_entry(lb)
        entry = (result or {}).get("entry", {})
        date_str = entry.get("date_str") or ""
        location = (entry.get("location") or "").strip()
        lb_status = database.get_lb_status(lb)
        standard_name = build_standard_name(lb, date_str, location, lb_status)
        return jsonify({
            "standard_name": standard_name,
            "lb_status": lb_status,
            "nft": lb_status == "private",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/db/backup", methods=["POST"])
def db_backup() -> Response:
    """Create a manual DB backup. Body: {reason} (optional)."""
    global _last_backup_at
    with _backup_lock:  # #3 — rate-limit to once per 60 s
        now = time.monotonic()
        if now - _last_backup_at < 60:
            return jsonify({"error": "rate_limited",
                            "message": "Please wait 60 s between manual backups"}), 429
        _last_backup_at = now
    try:
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason", "manual"))[:100]  # #8
        path = database.backup_database(reason=reason)
        size = path.stat().st_size
        return jsonify({"ok": True, "path": str(path), "size_bytes": size})
    except Exception:
        _log.exception("db_backup failed")  # #9
        return jsonify({"error": "internal_error"}), 500


# ── Curator mode (local flag) ──────────────────────────────────────────────

@bp.route("/api/curator", methods=["GET"])
def curator_get() -> Response:
    """Return whether this install is flagged as the curator."""
    try:
        return jsonify({"is_curator": database.is_curator()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/curator", methods=["POST"])
def curator_set() -> Response:
    """Toggle the local curator flag. Body: {enabled: bool}."""
    try:
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get("enabled", False))
        database.set_curator(enabled)
        return jsonify({"ok": True, "is_curator": enabled})
    except Exception as exc:
        logging.getLogger(__name__).exception("curator_set failed")
        return jsonify({"error": str(exc)}), 500


# ── Master data publish / subscribe ────────────────────────────────────────

@bp.route("/api/master/status", methods=["GET"])
def master_status() -> Response:
    """Return the current master snapshot version and publish timestamp.

    Returns:
        JSON dict with master_version and master_published_at from the meta table.
    """
    try:
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT key, value FROM meta WHERE key IN ('master_version', 'master_published_at')"
        ).fetchall()
        return jsonify({r["key"]: r["value"] for r in rows})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/master/export", methods=["POST"])
def master_export() -> Response:
    """Build a master-data snapshot + manifest. Curator-only.

    Body (optional): {reason, channel}. channel defaults to 'public'
    (private-entry metadata stripped, TODO-253); 'full' keeps it for
    friends-only distribution and is refused by /api/master/github_release.
    Returns: {ok, path, manifest_path, manifest: {...}}.
    """
    try:
        if not database.is_curator():
            return jsonify({
                "error": "curator_required",
                "message": "Master export is only available in curator mode. "
                               "Enable Curator Mode in Setup tab.",
            }), 403
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason", "publish"))[:200]  # #8
        channel = str(body.get("channel", "public"))
        if channel not in ("public", "full"):
            return jsonify({"error": "bad_channel",
                            "message": "channel must be 'public' or 'full'"}), 400
        path, manifest = database.export_master_db(
            reason=reason, include_private=(channel == "full"))
        return jsonify({
            "ok": True,
            "path": str(path),
            "manifest_path": str(path) + ".manifest.json",
            "manifest": manifest,
        })
    except Exception:
        _log.exception("master_export failed")  # #9
        return jsonify({"error": "internal_error"}), 500


@bp.route("/api/master/github_release", methods=["POST"])
def master_github_release() -> Response:
    """Create a GitHub release with real upload progress. Curator-only.

    Replaces gh CLI subprocess with direct GitHub REST API calls.
    Token is obtained via ``gh auth token``.  Assets (.db and manifest)
    are uploaded in 1 MB chunks so the GUI can display byte-accurate
    progress, matching the pattern used by the download flow.

    Body: {db_path, manifest_path, version, prev_published_at (optional)}.
    Returns: text/event-stream with events:
      data: {"type": "progress", "label": "...", "pct": N_or_null}
      data: {"type": "done", "tag": "...", "url": "..."}
      data: {"type": "error", "error": "...", "message": "..."}
    """
    import json as _json
    import queue
    import subprocess
    from datetime import datetime

    import requests as _req

    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403

    body = request.get_json(silent=True) or {}
    db_path_str = body.get("db_path", "")
    manifest_path_str = body.get("manifest_path", "")
    version = body.get("version", "")
    prev_published_at = body.get("prev_published_at")

    if not db_path_str or not manifest_path_str:
        return jsonify({"error": "db_path and manifest_path are required"}), 400

    # TODO-253 guard: the release lands on a PUBLIC repo — only snapshots
    # whose manifest proves the private-metadata strip ran may be uploaded.
    # Manifests without a channel field predate the strip and are refused.
    try:
        with open(manifest_path_str, encoding="utf-8") as _mf:
            _manifest = _json.load(_mf)
    except (OSError, ValueError):
        return jsonify({"error": "manifest_unreadable",
                        "message": "Could not read manifest sidecar."}), 400
    if _manifest.get("channel") != "public":
        return jsonify({
            "error": "private_data",
            "message": "This snapshot was not exported on the public channel "
                           "(private-entry metadata not stripped). Re-export with "
                           "channel='public' before publishing to GitHub.",
        }), 400

    _REPO = "kuddukan42/losslessbob"
    _GH_API = "https://api.github.com"
    ev_q: queue.Queue = queue.Queue()

    def _work() -> None:
        try:
            # Obtain token via gh CLI
            tok = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=15,
            )
            if tok.returncode != 0:
                ev_q.put({"type": "error", "error": "gh_auth_failed",
                          "message": tok.stderr.strip() or "gh auth token failed"})
                return
            token = tok.stdout.strip()
            if not token:
                ev_q.put({"type": "error", "error": "gh_no_token",
                          "message": "gh auth token returned empty — run `gh auth login` first."})
                return

            gh_hdr = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            }

            # Derive date for tag
            try:
                date_str = version[:10] if version else datetime.now(UTC).strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now(UTC).strftime("%Y-%m-%d")

            # Find an unused tag: master-YYYY-MM-DD[.N]
            ev_q.put({"type": "progress", "label": "Checking for existing releases…", "pct": None})
            base_tag = f"master-{date_str}"
            tag = None
            for suffix in ["", ".2", ".3", ".4", ".5"]:
                candidate = f"{base_tag}{suffix}" if suffix else base_tag
                chk = _req.get(
                    f"{_GH_API}/repos/{_REPO}/releases/tags/{candidate}",
                    headers=gh_hdr, timeout=15,
                )
                if chk.status_code == 404:
                    tag = candidate
                    break
            if tag is None:
                ev_q.put({"type": "error", "error": "too_many_releases",
                          "message": f"5 releases already exist for {date_str}."})
                return

            # Build release notes
            ev_q.put({"type": "progress", "label": "Building release notes…", "pct": None})
            notes = database.generate_release_notes(since_timestamp=prev_published_at)

            # Create the GitHub release
            ev_q.put({"type": "progress", "label": f"Creating release {tag}…", "pct": None})
            cr = _req.post(
                f"{_GH_API}/repos/{_REPO}/releases",
                headers=gh_hdr,
                json={"tag_name": tag, "name": f"Master Update {date_str}", "body": notes},
                timeout=30,
            )
            if not cr.ok:
                msg = cr.json().get("message", cr.text[:300]) if cr.content else cr.reason
                ev_q.put({"type": "error", "error": "create_failed", "message": msg})
                return
            release = cr.json()
            # upload_url: "https://uploads.github.com/.../assets{?name,label}" — strip template
            upload_base = release["upload_url"].split("{")[0]
            release_url = release["html_url"]

            def _upload_asset(file_path_s: str, label: str) -> None:
                _github_upload_asset(_req, upload_base, token, file_path_s, label, ev_q)

            db_fname = Path(db_path_str).name
            mf_fname = Path(manifest_path_str).name
            ev_q.put({"type": "progress", "label": f"Uploading {db_fname}…", "pct": 0})
            _upload_asset(db_path_str, db_fname)

            ev_q.put({"type": "progress", "label": f"Uploading {mf_fname}…", "pct": 0})
            _upload_asset(manifest_path_str, mf_fname)

            # Stamp the live DB so the GUI reflects what was just published —
            # the snapshot's meta rows only existed inside the exported .db.
            try:
                with open(manifest_path_str, encoding="utf-8") as mf:
                    manifest_data = _json.load(mf)
                database.set_meta(
                    "master_version", manifest_data.get("master_version", version)
                )
                database.set_meta(
                    "master_published_at", manifest_data.get("master_published_at", "")
                )
            except Exception:
                _log.exception("Failed to record published master_version/master_published_at")

            ev_q.put({"type": "done", "tag": tag, "url": release_url})

        except FileNotFoundError:
            ev_q.put({"type": "error", "error": "gh_not_found",
                      "message": "gh CLI not found — install GitHub CLI first."})
        except Exception as exc:
            ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

    threading.Thread(target=_work, daemon=True).start()

    def _stream():
        from backend import activity as _activity

        with _activity.track("master_publish", screen="/setup") as _job:
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {"type": "error", "error": "timeout",
                          "message": "Upload timed out after 680 s."}
                if ev.get("type") == "progress":
                    _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

    return Response(
        stream_with_context(_stream()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@bp.route("/api/master/import", methods=["POST"])
def master_import() -> Response:
    """Apply a master snapshot to the local DB, preserving user data.

    Body: {path: "/abs/path/to/snapshot.db"}. Manifest sidecar must live
    alongside the snapshot at <path>.manifest.json.

    Note: intentionally not curator-gated — curators publish, anyone installs.
    """
    try:
        body = request.get_json(silent=True) or {}
        path = body.get("path")
        if not path:
            return jsonify({"error": "missing_path"}), 400
        snapshot_path = Path(path).resolve()
        if snapshot_path.suffix.lower() != ".db":
            return jsonify({"error": "path_not_allowed",
                            "message": "Snapshot must be a .db file"}), 400
        summary = database.import_master_db(str(snapshot_path))
        return jsonify({"ok": True, **summary})
    except FileNotFoundError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": "schema_too_new", "message": str(exc)}), 400
    except sqlite3.Error as exc:
        _log.exception("master_import: SQLite error")
        return jsonify({"error": "db_error", "message": str(exc)}), 500
    except Exception as exc:
        _log.exception("master_import failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/tapematch/sync", methods=["POST"])
def tapematch_sync() -> Response:
    """Ingest TapeMatch family clusters + pairwise similarity from
    tools/tapematch/observations.db.

    Manual trigger only — not run automatically at startup, since that
    would make backend boot depend on observations.db existing/unlocked.
    One trigger runs both syncs (families, then pairs — per
    instructions/FABLE_LISTENING_INSIGHT_IDEAS.md §1) so callers never
    need to remember to fire two requests. The families stats keys are
    unchanged; pairs stats are merged in as ``pairs_synced``/``pair_dates``
    plus any pairs-specific errors appended to the shared ``errors`` list.
    """
    from backend import tapematch_sync as _tapematch_sync

    try:
        stats = _tapematch_sync.sync_tapematch_families()
        pair_stats = _tapematch_sync.sync_tapematch_pairs()
        stats["pairs_synced"] = pair_stats["pairs_written"]
        stats["pair_dates"] = pair_stats["dates_processed"]
        stats["errors"] = [*stats["errors"], *pair_stats["errors"]]
        if stats["dates_processed"]:
            # Tapers + picks read families (BUG-345); ~1 min, so off the request.
            threading.Thread(
                target=_tapematch_sync.refresh_derived_after_sync,
                kwargs={"trigger_source": "route"},
                name="tapematch-derived-refresh", daemon=True,
            ).start()
            stats["derived_refresh"] = "started"
        return jsonify({"ok": True, **stats})
    except FileNotFoundError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": "locked", "message": str(exc)}), 409
    except sqlite3.Error as exc:
        _log.exception("tapematch_sync: SQLite error")
        return jsonify({"error": "db_error", "message": str(exc)}), 500
    except Exception as exc:
        _log.exception("tapematch_sync failed")
        return jsonify({"error": "internal_error", "message": str(exc)}), 500


@bp.route("/api/derived/recompute", methods=["POST"])
def derived_recompute() -> Response:
    """Chained derived-data recompute: parse_lineage -> attribute_tapers ->
    compute_show_picks -> song_index.

    Per instructions/SPEC_INTEGRATION_NOTES.md finding F1, this replaces
    the ranking spec's standalone ``POST /api/picks/recompute`` — it's the
    one endpoint the onboarding wizard's "Done" step (and a "Recompute
    derived data" button, for curators after rating/list changes) calls,
    so a fresh install regenerates lineage, taper attributions, show
    picks, and the song index from master data alone. SSE, sequential;
    each step is run in canonical order (attribution before picks, per
    F5, so the taper reputation scoring term sees fresh attributions;
    song_index last since it has no cross-step dependency) and skipped
    gracefully (a 'skipped' event) if its module isn't importable, so the
    chain degrades cleanly when a later phase hasn't shipped yet.

    Manual trigger only (like /api/tapematch/sync) — never run at
    startup. Not curator-gated: unlike the master-data endpoints above,
    this recomputes only the user's OWN local USER-tier derived tables
    (entry_lineage, taper_attributions, show_picks, song_canonical/
    song_performances), never exported in master — same rationale as
    /api/tapematch/sync.
    """
    steps = (
        ("parse_lineage", "tools.parse_lineage", "run"),
        ("attribute_tapers", "tools.attribute_tapers", "run"),
        ("compute_show_picks", "tools.compute_show_picks", "run"),
        ("song_index", "backend.song_index", "run"),
    )

    def _stream():
        from backend import activity as _activity
        from backend import config_version as _config_version

        with _activity.track("derived_recompute", screen="/dbeditor") as _job:
            for name, module_name, func_name in steps:
                _job.update({"label": name})
                yield f"data: {json.dumps({'event': 'start', 'step': name})}\n\n"
                try:
                    module = importlib.import_module(module_name)
                    func = getattr(module, func_name)
                except (ImportError, AttributeError):
                    yield f"data: {json.dumps({'event': 'skipped', 'step': name})}\n\n"
                    continue
                started_at = time.strftime("%Y-%m-%d %H:%M:%S")
                try:
                    result = func()
                    payload = {"event": "done", "step": name}
                    if isinstance(result, dict):
                        payload["stats"] = result
                    database.record_step_run(
                        name, status="ok", started_at=started_at,
                        counters=result if isinstance(result, dict) else None,
                        trigger_source="route",
                    )
                    _config_version.stamp_for_step(name)
                    yield f"data: {json.dumps(payload)}\n\n"
                except Exception as exc:
                    _log.exception("derived/recompute: step %s failed", name)
                    database.record_step_run(
                        name, status="error", started_at=started_at,
                        trigger_source="route",
                    )
                    err = json.dumps(
                        {"event": "error", "step": name, "message": str(exc)}
                    )
                    yield f"data: {err}\n\n"
                    return
            yield f"data: {json.dumps({'event': 'chain_done'})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ── Master data install from GitHub (subscribe side) ──────────────────────────

def _find_master_release(_req):
    """Search recent GitHub releases for the latest one containing a .db master asset.

    Returns (release, db_asset, manifest_asset) or raises RuntimeError with a
    human-readable message when nothing usable is found.
    """
    _REPO = "kuddukan42/losslessbob"
    page = 1
    while page <= 5:
        resp = _req.get(
            f"https://api.github.com/repos/{_REPO}/releases",
            headers={"Accept": "application/vnd.github+json"},
            params={"per_page": 20, "page": page},
            timeout=15,
        )
        if resp.status_code == 404 or (page == 1 and resp.json() == []):
            raise RuntimeError("No releases found on GitHub yet.")
        resp.raise_for_status()
        releases = resp.json()
        if not releases:
            break
        for release in releases:
            assets = release.get("assets", [])
            db_asset = next(
                (a for a in assets
                 if a["name"].endswith(".db") and not a["name"].endswith(".manifest.json.db")),
                None,
            )
            if not db_asset:
                continue
            manifest_name = db_asset["name"] + ".manifest.json"
            manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
            if not manifest_asset:
                continue
            return release, db_asset, manifest_asset
        page += 1
    raise RuntimeError("No release with a master .db asset found on GitHub.")


@bp.route("/api/master/github_check", methods=["GET"])
def master_github_check() -> Response:
    """Check GitHub Releases for a master snapshot newer than the local one.

    Returns:
        JSON dict with ``available`` (bool) plus ``tag``, ``remote_version``,
        ``remote_published_at``, ``local_version``, ``local_published_at``,
        ``asset_name``, ``asset_size``, ``release_url`` when a release is found.
        If no usable release exists, ``available`` is ``false`` with a
        human-readable ``message``.
    """
    import requests as _req

    try:
        try:
            release, db_asset, manifest_asset = _find_master_release(_req)
        except RuntimeError as exc:
            return jsonify({"available": False, "message": str(exc)})

        tag = release.get("tag_name", "?")
        mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
        mresp.raise_for_status()
        manifest = mresp.json()
        remote_version = manifest.get("master_version", "")
        remote_published_at = manifest.get("master_published_at", "")

        conn = database.get_connection()
        rows = conn.execute(
            "SELECT key, value FROM meta WHERE key IN ('master_version', 'master_published_at')"
        ).fetchall()
        local = {r["key"]: r["value"] for r in rows}

        return jsonify({
            "available": bool(remote_version) and remote_version != local.get("master_version", ""),
            "tag": tag,
            "remote_version": remote_version,
            "remote_published_at": remote_published_at,
            "local_version": local.get("master_version", ""),
            "local_published_at": local.get("master_published_at", ""),
            "asset_name": db_asset["name"],
            "asset_size": db_asset.get("size", 0),
            "release_url": release.get("html_url", ""),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/master/github_install", methods=["POST"])
def master_github_install() -> Response:
    """Download and apply the latest master snapshot from GitHub Releases.

    Streams progress via ``text/event-stream``, mirroring
    ``/api/master/github_release``'s event shape:
      data: {"type": "progress", "label": "...", "pct": N_or_null}
      data: {"type": "done", "summary": {...}}
      data: {"type": "error", "error": "...", "message": "..."}
    """
    import hashlib
    import json as _json
    import queue

    import requests as _req

    ev_q: queue.Queue = queue.Queue()

    def _work() -> None:
        try:
            ev_q.put({"type": "progress", "label": "Checking GitHub for latest release…", "pct": None})
            try:
                release, db_asset, manifest_asset = _find_master_release(_req)
            except RuntimeError as exc:
                ev_q.put({"type": "error", "error": "no_releases", "message": str(exc)})
                return

            tag = release.get("tag_name", "?")

            ev_q.put({"type": "progress", "label": f"Downloading manifest for {tag}…", "pct": None})
            mresp = _req.get(manifest_asset["browser_download_url"], timeout=30)
            mresp.raise_for_status()
            manifest = mresp.json()

            dest_dir = DATA_DIR / "imports"
            dest_dir.mkdir(parents=True, exist_ok=True)
            db_dest = dest_dir / db_asset["name"]
            manifest_dest = dest_dir / manifest_asset["name"]

            total_bytes = db_asset.get("size", 0)
            total_mb = total_bytes / (1 << 20)
            ev_q.put({"type": "progress",
                      "label": f"Downloading {db_asset['name']} ({total_mb:.0f} MB)…", "pct": 0})
            dresp = _req.get(db_asset["browser_download_url"], stream=True, timeout=600)
            dresp.raise_for_status()

            downloaded = 0
            with open(db_dest, "wb") as fh:
                for chunk in dresp.iter_content(chunk_size=1 << 18):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes:
                            pct = downloaded * 100 // total_bytes
                            dl_mb = downloaded / (1 << 20)
                            ev_q.put({
                                "type": "progress",
                                "label": f"Downloading… {pct}%  ({dl_mb:.1f} / {total_mb:.0f} MB)",
                                "pct": pct,
                            })

            ev_q.put({"type": "progress", "label": "Verifying checksum…", "pct": None})
            sha = hashlib.sha256()
            with open(db_dest, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    sha.update(chunk)
            expected_sha = manifest.get("sha256", "")
            if sha.hexdigest() != expected_sha:
                db_dest.unlink(missing_ok=True)
                ev_q.put({"type": "error", "error": "sha256_mismatch",
                          "message": "SHA256 mismatch — download may be corrupt. Please try again."})
                return

            with open(manifest_dest, "w", encoding="utf-8") as fh:
                _json.dump(manifest, fh, indent=2)

            ev_q.put({"type": "progress", "label": "Applying update to local database…", "pct": None})
            summary = database.import_master_db(str(db_dest), source="github")
            ev_q.put({"type": "done", "summary": summary})

        except Exception as exc:
            ev_q.put({"type": "error", "error": type(exc).__name__, "message": str(exc)})

    threading.Thread(target=_work, daemon=True).start()

    def _stream():
        from backend import activity as _activity

        with _activity.track("master_install", screen="/setup") as _job:
            while True:
                try:
                    ev = ev_q.get(timeout=680)
                except queue.Empty:
                    ev = {
                        "type": "error", "error": "timeout",
                        "message": "Update timed out after 680 s.",
                    }
                if ev.get("type") == "progress":
                    _job.update({"pct": ev.get("pct"), "label": ev.get("label")})
                yield f"data: {_json.dumps(ev)}\n\n"
                if ev.get("type") in ("done", "error"):
                    break

    return Response(
        stream_with_context(_stream()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
