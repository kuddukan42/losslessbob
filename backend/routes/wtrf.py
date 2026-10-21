"""Forum posting, WTRF torrent fetcher and WTRF fetch-review routes."""

import logging
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend.lbdir_status import _lbdir_status_for_lb
from backend.paths import (
    DATA_DIR,
    SITE_FILES_DIR,
)

_log = logging.getLogger(__name__)

bp = Blueprint("wtrf", __name__)


# ── Forum Posting ─────────────────────────────────────────────────────────

@bp.route("/api/wtrf/test", methods=["POST"])
def wtrf_test() -> Response:
    """Test WTRF forum credentials by attempting a login (no post is made).

    Body: {username?, password?} — falls back to stored keyring credentials.
    Returns: {ok, username} or {ok=False, error}.
    """
    try:
        from backend.credentials import SERVICE_WTRF, get_credentials
        from backend.forum_poster import _get_session
        data = request.get_json() or {}
        username = data.get("username") or ""
        password = data.get("password") or ""
        if not username:
            username, password = get_credentials(SERVICE_WTRF)
        if not username:
            return jsonify({"ok": False, "error": "No credentials provided"}), 400
        session = _get_session(username, password)
        if session is None:
            return jsonify({"ok": False, "error": "Login failed — check username and password."})
        return jsonify({"ok": True, "username": username})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/credentials/wtrf", methods=["GET"])
def credentials_wtrf_get() -> Response:
    """Return the stored WTRF username only — never the password.

    Returns:
        JSON {username: str} — empty string if no credentials are stored.
    """
    try:
        from backend.credentials import SERVICE_WTRF, get_credentials
        username, _ = get_credentials(SERVICE_WTRF)
        return jsonify({"username": username})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/credentials/wtrf", methods=["POST"])
def credentials_wtrf_save() -> Response:
    """Save WTRF forum credentials to the OS keyring.

    Body: {username, password}
    Returns: {ok: true} or {error}.
    """
    try:
        from backend.credentials import SERVICE_WTRF, save_credentials
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username:
            return jsonify({"ok": False, "error": "Username required"}), 400
        save_credentials(SERVICE_WTRF, username, password)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/credentials/qbt", methods=["POST"])
def credentials_qbt_save() -> Response:
    """Save qBittorrent credentials to the OS keyring.

    Body: {username, password} or {api_key}
    Returns: {ok: true} or {error}.
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, save_credentials
        data = request.get_json() or {}
        api_key = data.get("api_key", "").strip()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if api_key:
            save_credentials(SERVICE_QBT_KEY, "", api_key)
        elif username:
            save_credentials(SERVICE_QBT, username, password)
        else:
            return jsonify({"ok": False, "error": "Username or api_key required"}), 400
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/credentials/qbt", methods=["DELETE"])
def credentials_qbt_delete() -> Response:
    """Remove qBittorrent credentials from the OS keyring.

    Returns:
        JSON {ok: true} or {error}.
    """
    try:
        from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, delete_credentials
        delete_credentials(SERVICE_QBT)
        delete_credentials(SERVICE_QBT_KEY)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/credentials/wtrf", methods=["DELETE"])
def credentials_wtrf_delete() -> Response:
    """Remove WTRF forum credentials from the OS keyring.

    Returns:
        JSON {ok: true} or {error}.
    """
    try:
        from backend.credentials import SERVICE_WTRF, delete_credentials
        delete_credentials(SERVICE_WTRF)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/entry/<int:lb>/preview_forum", methods=["GET"])
def preview_forum(lb: int) -> Response:
    """Return the forum post subject and body for an LB entry without posting.

    Returns: {subject, body}.
    Blocked (HTTP 403) for private and missing LBs.
    """
    try:
        allowed, reason = database.is_postable_to_forum(lb)
        if not allowed:
            _msg = {
                "lb_private": f"LB-{lb:05d} is marked Private. Forum posting is blocked.",
                "lb_missing": f"LB-{lb:05d} is marked as not existing. Nothing to post.",
                "status_unknown": f"LB-{lb:05d} has no master status record. Cannot post.",
            }.get(reason, f"LB-{lb:05d} cannot be posted.")
            return jsonify({"error": reason, "message": _msg}), 403

        from backend.forum_poster import preview_lb_topic
        entry_data = database.get_entry(lb)
        if not entry_data:
            return jsonify({"ok": False, "error": f"Entry LB-{lb} not found"}), 404
        entry = dict(entry_data["entry"])
        bootlegs = database.get_bootlegs_for_lb(lb)
        if bootlegs:
            entry["bootleg_title"] = bootlegs[0]["title"]
        result = preview_lb_topic(lb_number=lb, entry=entry, attachments_dir=SITE_FILES_DIR)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/entry/<int:lb>/lbdir_status", methods=["GET"])
def lbdir_status(lb: int) -> Response:
    """Return the LBDIR pipeline verdict for an LB's filed collection folder.

    Query: ``force=1`` re-verifies instead of reusing the pipeline's cached
    per-folder verdict. Surfaced in the forum post preview so the folder's
    manifest state is visible before the post is made.

    The verdict shown is audio-first: ``audio_status`` is green whenever
    every audio file in the manifest passes, and the folder's non-audio
    entries are described by ``text_label_key`` instead of colouring the
    result. Recoverable text files are restored before the answer is
    computed (exact-MD5 matches only; nothing is deleted).

    Returns: {ok, lb, status, label, label_key, label_params, check,
    audio_status, audio_label_key, audio_label_params, text_label_key,
    text_label_params, split, reconciled, folder, manifest, cached,
    checked_at}.
    """
    try:
        force = request.args.get("force", "").lower() in ("1", "true", "yes")
        result = _lbdir_status_for_lb(lb, force=force)
        return jsonify({"ok": True, "lb": lb, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/entry/<int:lb>/post_forum", methods=["POST"])
def post_forum(lb: int) -> Response:
    """Post a topic to the WTRF forum for one LB entry.

    Body: {username?, password?, torrent_id?}
    If no torrents record exists (and torrent_id isn't given), a torrent is generated
    from the entry's my_collection folder and added to qBittorrent automatically before
    posting; qBittorrent failure is reported but does not block the post.
    Returns: {ok, topic_url, torrent_auto_created?, qbt_auto_add?} or {ok=False, error}.
    """
    try:
        # Guard: block private and missing LBs from being posted to the forum
        allowed, reason = database.is_postable_to_forum(lb)
        if not allowed:
            _msg = {
                "lb_private": (
                    f"LB-{lb:05d} is marked Private. "
                        "Forum posting is blocked to avoid exposing unreleased content."
                ),
                "lb_missing": (
                    f"LB-{lb:05d} is marked as not existing. There is nothing to post about."
                ),
                "status_unknown": (
                    f"LB-{lb:05d} has no master status record. Cannot determine postability."
                ),
            }.get(reason, f"LB-{lb:05d} cannot be posted.")
            return jsonify({"error": reason, "message": _msg}), 403

        from backend.credentials import SERVICE_WTRF, get_credentials
        from backend.forum_poster import post_lb_topic
        data = request.get_json() or {}

        # Resolve credentials
        username = data.get("username") or ""
        password = data.get("password") or ""
        if not username:
            username, password = get_credentials(SERVICE_WTRF)
        if not username:
            return jsonify({"ok": False, "error": "WTRF credentials not set"}), 400

        # Get entry metadata
        entry_data = database.get_entry(lb)
        if not entry_data:
            return jsonify({"ok": False, "error": f"Entry LB-{lb} not found"}), 404
        entry = dict(entry_data["entry"])
        bootlegs = database.get_bootlegs_for_lb(lb)
        if bootlegs:
            entry["bootleg_title"] = bootlegs[0]["title"]

        conn = database.get_connection()
        coll_row = conn.execute(
            "SELECT disk_path FROM my_collection WHERE lb_number=?", (lb,)
        ).fetchone()

        # Integrity gate: block posting a folder whose audio no longer matches
        # its stored checksums (see BUG-120 — swapped/re-encoded audio slipping
        # through undetected). Runs before torrent resolution so a bad folder
        # isn't auto-torrented/seeded either.
        #
        # Judged on the LBDIR manifest alone — the same verdict the forum
        # preview's banner shows — not on whatever loose .ffp/.md5 sidecars
        # happen to sit in the folder. Those are frequently stale or written
        # under a different filename convention (LB-03696 carried an
        # uppercase .ffp and a lowercase .md5 for the same 32 tracks), and
        # the sidecar sweep counted each convention separately and reported
        # half of them missing while the manifest verified clean.
        skip_integrity_check = bool(data.get("skip_integrity_check"))
        if coll_row and coll_row["disk_path"]:
            lbdir_state = _lbdir_status_for_lb(lb)
            audio = (lbdir_state.get("split") or {}).get("audio") or {}
            n_mismatch = audio.get("mismatch", 0)
            n_missing = audio.get("missing", 0)
            # A mismatch means audio content itself doesn't match the manifest --
            # possible swapped/re-encoded file (BUG-120) -- never skippable. A
            # missing entry just means the manifest lists audio the folder no
            # longer holds, which can be a stale manifest; allow an explicit
            # user override for that case only. Non-audio entries never gate.
            if n_mismatch or (n_missing and not skip_integrity_check):
                verify_status = "fail" if n_mismatch else "incomplete"
                return jsonify({
                    "ok": False,
                    "error": (
                        f"LBDIR verify failed ({verify_status}: "
                            f"{n_mismatch} mismatch, {n_missing} missing audio file(s)) — "
                            "fix the folder's integrity before posting to the forum."
                    ),
                    "skippable": not n_mismatch,
                }), 400

        # Resolve torrent file
        torrent_id = data.get("torrent_id")
        if torrent_id:
            row = conn.execute(
                "SELECT torrent_path FROM torrents WHERE id=?", (torrent_id,)
            ).fetchone()
            torrent_path = row["torrent_path"] if row else None
        else:
            rows = database.get_torrents_for_lb(lb)
            torrent_path = rows[0]["torrent_path"] if rows else None

        qbt_auto_add_result = None
        if not torrent_path:
            if not coll_row or not coll_row["disk_path"]:
                return jsonify({
                    "ok": False,
                    "error": "No torrent file found for this entry, and no collection "
                                 "folder to generate one from. Create a torrent first.",
                }), 400
            try:
                from backend.torrent_maker import make_torrent
                tracker_list = database.get_meta("tracker_list") or "best"
                mk_result = make_torrent(lb, coll_row["disk_path"], tracker_list=tracker_list)
            except RuntimeError as exc:
                return jsonify({"ok": False, "error": f"Auto torrent creation failed: {exc}"}), 500
            torrent_path = mk_result["torrent_path"]
            database.clear_superseded_torrent_paths(
                lb, mk_result["torrent_id"], torrent_path
            )

            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY
            from backend.credentials import get_credentials as get_qbt_credentials
            from backend.qbittorrent import add_torrent_from_db
            qbt_host = database.get_meta("qbt_host") or "localhost"
            qbt_port = int(database.get_meta("qbt_port") or 8080)
            qbt_category = database.get_meta("qbt_category") or ""
            qbt_tags = database.get_meta("qbt_tags") or ""
            _, qbt_api_key = get_qbt_credentials(SERVICE_QBT_KEY)
            qbt_username = qbt_password = ""
            if not qbt_api_key:
                qbt_username, qbt_password = get_qbt_credentials(SERVICE_QBT)
            qbt_auto_add_result = add_torrent_from_db(
                mk_result["torrent_id"], qbt_host, qbt_port, qbt_username, qbt_password,
                qbt_category, qbt_tags, api_key=qbt_api_key,
            )
            # Best-effort: a failed qBittorrent add doesn't block the forum post
            # (the torrent file itself was created fine and can be added manually).

        board_id = int(database.get_meta("wtrf_board_id") or 0)
        if not board_id:
            return jsonify({"ok": False, "error": "Forum board ID not set. Configure it in Setup → WTRF Forum."}), 400

        result = post_lb_topic(
            lb_number=lb,
            torrent_path=torrent_path,
            username=username,
            password=password,
            entry=entry,
            board_id=board_id,
            attachments_dir=SITE_FILES_DIR,
            subject_override=data.get("subject") or None,
            body_override=data.get("body") or None,
        )
        if result.get("ok"):
            from backend.torrent_maker import _parse_date
            subj = data.get("subject") or ""
            if not subj:
                iso_date = _parse_date(entry.get("date_str") or "")
                loc = (entry.get("location") or "").strip()
                lb_id = f"LB-{lb:05d}"
                subj = (f"{iso_date} {loc} ({lb_id})" if iso_date and loc
                        else f"{loc} ({lb_id})" if loc else lb_id)
            database.add_forum_post(
                lb_number=lb,
                subject=subj,
                topic_url=result.get("topic_url", ""),
                board_id=board_id,
            )
        if qbt_auto_add_result is not None:
            result["torrent_auto_created"] = True
            result["qbt_auto_add"] = qbt_auto_add_result
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/entry/<int:lb>/forum_posts", methods=["GET"])
def forum_posts_list(lb: int) -> Response:
    """Return all logged forum posts for an LB entry, newest first."""
    try:
        return jsonify(database.get_forum_posts_for_lb(lb))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/wtrf/sync_posts", methods=["POST"])
def wtrf_sync_posts() -> Response:
    """Sync "already posted" status from the WTRF board (TODO-135).

    JSON body: ``mode`` = ``archive`` (offline import of data/wtrf_board.db) or
    ``board`` (paced live crawl; optional ``full``, ``max_pages``).
    """
    from backend import wtrf_discovery as _wd
    from backend.paths import DATA_DIR as _DATA_DIR
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "board")

    def _write(fn):
        return database.get_write_queue().execute(fn)

    def _read(fn):
        return fn(database.get_connection())

    try:
        if mode == "archive":
            archive = _DATA_DIR / "wtrf_board.db"
            if not archive.exists():
                return jsonify({"ok": False, "error": "no board archive DB"}), 404
            return jsonify({"ok": True, **_write(
                lambda c: _wd.import_from_archive(c, archive))})
        if mode != "board":
            return jsonify({"ok": False, "error": "bad mode"}), 400
        from backend.credentials import SERVICE_WTRF, get_credentials
        from backend.forum_poster import _get_session
        user, pw = get_credentials(SERVICE_WTRF)
        if not user or not pw:
            return jsonify({"ok": False, "error": "WTRF credentials not set"}), 400
        session = _get_session(user, pw)
        if session is None:
            return jsonify({"ok": False, "error": "WTRF login failed"}), 502
        stats = _wd.sync_from_board(
            session, _read, _write, int(database.get_meta("wtrf_board_id") or 16),
            full=bool(body.get("full")),
            max_pages=max(1, min(int(body.get("max_pages", 10)), 50)),
        )
        return jsonify({"ok": True, **stats})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/forum_post/<int:post_id>", methods=["DELETE"])
def forum_post_delete(post_id: int) -> Response:
    """Delete a forum post log record by id."""
    try:
        database.delete_forum_post(post_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _wtrf_edit_session(topic_url: str):
    """Validate a topic URL and log in for the post editor (TODO-136).

    Returns:
        ``(session, None)`` or ``(None, (json_response, status))``.
    """
    from backend import forum_poster
    from backend.credentials import SERVICE_WTRF, get_credentials
    from backend.wtrf_seed import is_wtrf_topic_url
    if not topic_url or not is_wtrf_topic_url(topic_url):
        return None, (jsonify({"ok": False, "error": "Not a WTRF topic URL"}), 400)
    user, pw = get_credentials(SERVICE_WTRF)
    if not user or not pw:
        return None, (jsonify({"ok": False, "error": "WTRF credentials not set"}), 400)
    session = forum_poster._get_session(user, pw)
    if session is None:
        return None, (jsonify({"ok": False, "error": "WTRF login failed"}), 502)
    return session, None


@bp.route("/api/forum_post/edit_form", methods=["GET"])
def forum_post_edit_form() -> Response:
    """Current subject/BBCode body of a WTRF topic's opening post (TODO-136).

    Query: ``topic_url``. Read-only — logs in and fetches SMF's edit form.
    Returns ``{ok, topic_id, msg_id, subject, body}``; the form's session
    tokens stay server-side.
    """
    from backend.wtrf_post_editor import fetch_post_for_edit
    try:
        topic_url = request.args.get("topic_url", "").strip()
        session, err = _wtrf_edit_session(topic_url)
        if err:
            return err
        got = fetch_post_for_edit(session, topic_url)
        if not got["ok"]:
            return jsonify(got), 502
        return jsonify({k: got[k] for k in ("ok", "topic_id", "msg_id", "subject", "body")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/forum_post/edit", methods=["POST"])
def forum_post_edit() -> Response:
    """Edit the opening post of a WTRF topic (TODO-136).

    JSON body: ``topic_url``, ``subject``, ``body``, ``confirm``. Dry-run
    (fetch + diff, nothing POSTed to the forum) unless ``confirm`` is the
    JSON literal ``true``. A confirmed save also rewrites the subject of any
    local ``forum_posts`` row for that topic.
    """
    from backend.wtrf_post_editor import edit_post
    try:
        data = request.get_json(silent=True) or {}
        topic_url = (data.get("topic_url") or "").strip()
        session, err = _wtrf_edit_session(topic_url)
        if err:
            return err
        result = edit_post(
            session, topic_url,
            subject=data.get("subject") or "", body=data.get("body") or "",
            dry_run=data.get("confirm") is not True,
        )
        if not result["ok"]:
            return jsonify(result), 502
        if result.get("saved") and "subject" in result["changed"]:
            database.update_forum_post_subject(
                result["topic_url"], result["proposed"]["subject"])
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

# ── WTRF torrent fetcher ──────────────────────────────────────────────────

_wtrf_crawl_running = False
_wtrf_seed_running = False


@bp.route("/api/wtrf/fetch_torrent", methods=["POST"])
def wtrf_fetch_torrent() -> Response:
    """Search WTRF for a torrent matching a single LB entry and download it.

    Body JSON:
      lb_number (int, required)
      save_path (str, required) — directory for the downloaded .torrent
      add_to_qbt (bool, optional, default false)
      delay (float, optional, default 2.0) — seconds between HTTP requests

    Returns JSON with ok, torrent_path, topic_url, confidence, signals, error.
    Also records the attempt in wtrf_downloads.
    """
    import json as _json

    from backend.wtrf_scraper import find_torrent_for_lb
    try:
        data        = request.get_json(force=True) or {}
        lb_number   = int(data["lb_number"])
        save_path   = data.get("save_path") or str(DATA_DIR / "downloads" / "wtrf")
        add_to_qbt  = bool(data.get("add_to_qbt", False))
        delay       = float(data.get("delay", 2.0))

        result = find_torrent_for_lb(
            lb_number=lb_number,
            board_id=int(database.get_meta("wtrf_board_id") or 16),
            dest_dir=save_path,
            delay=delay,
        )

        status = "downloaded" if result["ok"] else "failed"
        dl_id = database.add_wtrf_download(
            lb_number=lb_number,
            topic_url=result.get("topic_url"),
            torrent_path=result.get("torrent_path"),
            confidence=result.get("confidence", "not_found"),
            signals_json=_json.dumps(result.get("signals", {})),
            status=status,
            error=result.get("error"),
        )

        if result["ok"] and add_to_qbt:
            from backend.credentials import SERVICE_QBT, SERVICE_QBT_KEY, get_credentials
            from backend.qbittorrent import add_torrent_for_download
            host     = database.get_meta("qbt_host") or "localhost"
            port     = int(database.get_meta("qbt_port") or 8080)
            category = database.get_meta("qbt_category") or ""
            tags     = database.get_meta("qbt_tags") or ""
            qbt_user, qbt_pass = get_credentials(SERVICE_QBT)
            _, qbt_key         = get_credentials(SERVICE_QBT_KEY)
            qbt_result = add_torrent_for_download(
                torrent_path=result["torrent_path"],
                save_path=save_path,
                host=host, port=port,
                username=qbt_user, password=qbt_pass,
                category=category, tags=tags, api_key=qbt_key,
            )
            if qbt_result.get("ok"):
                from datetime import UTC, datetime
                database.update_wtrf_download(
                    dl_id, {"status": "qbt_added",
                            "qbt_added_at": datetime.now(UTC).isoformat()}
                )
                result["qbt_added"] = True
            else:
                result["qbt_error"] = qbt_result.get("error")

        result["download_id"] = dl_id
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"ok": False, "error": f"Missing field: {exc}"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/wtrf/downloads", methods=["GET"])
def wtrf_downloads_list() -> Response:
    """List wtrf_downloads records, optionally filtered by lb_number.

    Query params: lb (int, optional).
    """
    try:
        lb = request.args.get("lb")
        rows = database.get_wtrf_downloads(int(lb) if lb else None)
        return jsonify(rows)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── WTRF fetch review (TODO-193) — keep these three routes together ───────
@bp.route("/api/wtrf/review", methods=["GET"])
def wtrf_review_list() -> Response:
    """Latest wtrf_downloads row per LB with parsed signals + candidates.

    Query params: filter (review|added|not_found|rejected|all), limit, offset.
    """
    from backend import wtrf_review
    try:
        return jsonify(wtrf_review.list_review_rows(
            request.args.get("filter", "review"),
            int(request.args.get("limit", 200)),
            int(request.args.get("offset", 0)),
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/wtrf/review/<int:download_id>/confirm", methods=["POST"])
def wtrf_review_confirm(download_id: int) -> Response:
    """Confirm a row: resume its paused torrent, or fetch + add to qBittorrent.

    Body JSON (optional): topic_url (the picked candidate), save_path.
    """
    from backend import wtrf_review
    try:
        data = request.get_json(silent=True) or {}
        res = wtrf_review.confirm_row(
            download_id, topic_url=data.get("topic_url"),
            save_path=data.get("save_path"),
        )
        return jsonify(res), (200 if res.get("ok") else 400)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/wtrf/review/<int:download_id>/reject", methods=["POST"])
def wtrf_review_reject(download_id: int) -> Response:
    """Mark a wtrf_downloads row rejected (kept as history)."""
    from backend import wtrf_review
    try:
        res = wtrf_review.reject_row(download_id)
        return jsonify(res), (200 if res.get("ok") else 404)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/wtrf/crawl_missing", methods=["POST"])
def wtrf_crawl_missing() -> Response:
    """Start a background batch crawl of missing items (SSE stream).

    Queries lb_master for public entries not in my_collection, ordered by
    lb_number DESC (highest first), skipping any already downloaded.
    Emits Server-Sent Events: progress, done, error.

    Body JSON (all optional):
      limit (int) — max entries to attempt this run
      delay (float) — seconds between HTTP requests (default 2.0)
      save_path (str) — directory for .torrent files
      add_to_qbt (bool) — also add each matched torrent to qBittorrent
    """
    import json as _json

    from backend.wtrf_scraper import find_torrent_for_lb

    global _wtrf_crawl_running
    if _wtrf_crawl_running:
        return jsonify({"error": "Crawl already running"}), 409

    data       = request.get_json(force=True) or {}
    limit      = int(data.get("limit") or 0) or None
    delay      = float(data.get("delay", 2.0))
    save_path  = data.get("save_path") or str(DATA_DIR / "downloads" / "wtrf")
    add_to_qbt = bool(data.get("add_to_qbt", False))
    board_id   = int(database.get_meta("wtrf_board_id") or 16)

    pending = database.get_wtrf_pending_lb_numbers()
    if limit:
        pending = pending[:limit]

    def _stream():
        from backend import activity as _activity

        global _wtrf_crawl_running
        _wtrf_crawl_running = True
        counts = {"attempted": 0, "downloaded": 0, "qbt_added": 0,
                  "skipped": 0, "failed": 0}
        with _activity.track("wtrf_crawl", screen="/scraper") as _job:
            try:
                for lb_number in pending:
                    counts["attempted"] += 1
                    _prog = _json.dumps({
                        "event": "progress", "lb_number": lb_number,
                        "attempted": counts["attempted"], "total": len(pending),
                    })
                    _job.update({"current": counts["attempted"], "total": len(pending)})
                    yield f"data: {_prog}\n\n"

                    result = find_torrent_for_lb(
                        lb_number=lb_number,
                        board_id=board_id,
                        dest_dir=save_path,
                        delay=delay,
                    )
                    status = "downloaded" if result["ok"] else (
                        "skipped" if result.get("confidence") in
                        ("needs_review", "ambiguous", "not_found") else "failed"
                    )
                    dl_id = database.add_wtrf_download(
                        lb_number=lb_number,
                        topic_url=result.get("topic_url"),
                        torrent_path=result.get("torrent_path"),
                        confidence=result.get("confidence", "not_found"),
                        signals_json=_json.dumps(result.get("signals", {})),
                        status=status,
                        error=result.get("error"),
                    )
                    counts[status if status in counts else "failed"] += 1

                    if result["ok"] and add_to_qbt:
                        from datetime import UTC, datetime

                        from backend.credentials import (
                            SERVICE_QBT,
                            SERVICE_QBT_KEY,
                            get_credentials,
                        )
                        from backend.qbittorrent import add_torrent_for_download
                        host     = database.get_meta("qbt_host") or "localhost"
                        port     = int(database.get_meta("qbt_port") or 8080)
                        category = database.get_meta("qbt_category") or ""
                        tags     = database.get_meta("qbt_tags") or ""
                        qbt_user, qbt_pass = get_credentials(SERVICE_QBT)
                        _, qbt_key         = get_credentials(SERVICE_QBT_KEY)
                        qbt_r = add_torrent_for_download(
                            torrent_path=result["torrent_path"],
                            save_path=save_path,
                            host=host, port=port,
                            username=qbt_user, password=qbt_pass,
                            category=category, tags=tags, api_key=qbt_key,
                        )
                        if qbt_r.get("ok"):
                            from datetime import UTC, datetime
                            database.update_wtrf_download(
                                dl_id, {"status": "qbt_added",
                                        "qbt_added_at": datetime.now(UTC).isoformat()}
                            )
                            counts["qbt_added"] += 1

                yield f"data: {_json.dumps({'event': 'done', **counts})}\n\n"
            except Exception as exc:
                yield f"data: {_json.dumps({'event': 'error', 'error': str(exc)})}\n\n"
            finally:
                _wtrf_crawl_running = False

    return Response(
        _stream(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _wtrf_seed_options(data: dict):
    """Build a tracker_seed.SeedOptions for WTRF from a request body.

    The overlay defaults to ON here, unlike the TUIT CLI: a WTRF torrent
    carries the ``LBF-*`` sidecars the curated folder does not keep, so
    seeding in place almost always falls a fraction short, and refusing is
    never what the button was pressed for. The collection is protected by
    the overlay itself, not by the flag.

    Args:
        data: Parsed request JSON.

    Returns:
        The SeedOptions describing this request's seeding policy.
    """
    from backend.tracker_seed import SeedOptions
    return SeedOptions(
        tracker="wtrf",
        overlay=bool(data.get("overlay", True)),
        overlay_root=data.get("overlay_root") or "",
        refetch_sidecars=bool(data.get("refetch_sidecars", True)),
        max_fetch_mb=float(data.get("max_fetch_mb", 25.0)),
        allow_partial_overlay=bool(data.get("allow_partial_overlay", True)),
        paused=bool(data.get("paused", False)),
        # Every WTRF seeding path starts from a post already on the board,
        # so a private lb_status is not a reason to leave it unseeded.
        allow_private=True,
    )


@bp.route("/api/wtrf/seed_links", methods=["POST"])
def wtrf_seed_links() -> Response:
    """Seed every recording named by a pasted list of WTRF topic links (SSE).

    Each link is walked to its first post, which yields the LB number and
    the ``.torrent`` attachment; the torrent is downloaded and handed to
    the shared seeding gates, which never point qBittorrent at an
    incomplete collection folder. Attempts land in wtrf_downloads.

    Body JSON:
      links (str, required) — pasted text, one topic URL per line; a line
        may be prefixed with "LB-00123" to pin the entry explicitly
      save_path (str, optional) — directory for the downloaded .torrent
      delay (float, optional, default 2.0) — seconds between HTTP requests
      dry_run (bool, optional) — resolve and report, download nothing
      overlay / overlay_root / refetch_sidecars / max_fetch_mb /
        allow_partial_overlay / paused — seeding policy, see _wtrf_seed_options

    Emits Server-Sent Events: start, link (one per URL), done, error.
    """
    import json as _json

    from backend.wtrf_seed import seed_from_links

    global _wtrf_seed_running
    if _wtrf_seed_running:
        return jsonify({"error": "A WTRF seed run is already in progress"}), 409

    data      = request.get_json(force=True) or {}
    links     = data.get("links") or ""
    save_path = data.get("save_path") or str(DATA_DIR / "downloads" / "wtrf")
    delay     = float(data.get("delay", 2.0))
    dry_run   = bool(data.get("dry_run", False))
    opts      = _wtrf_seed_options(data)

    def _stream():
        from backend import activity as _activity

        global _wtrf_seed_running
        _wtrf_seed_running = True
        with _activity.track("wtrf_seed", screen="/scraper") as _job:
            try:
                for event in seed_from_links(
                    links, opts, save_path, delay=delay, dry_run=dry_run
                ):
                    if event.get("event") == "link":
                        _job.update({"current": event.get("index", 0),
                                     "total": event.get("total", 0)})
                    yield f"data: {_json.dumps(event)}\n\n"
            except Exception as exc:
                _log.exception("wtrf_seed_links failed")
                yield f"data: {_json.dumps({'event': 'error', 'error': str(exc)})}\n\n"
            finally:
                _wtrf_seed_running = False

    return Response(
        _stream(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@bp.route("/api/entry/<int:lb_number>/seed_wtrf", methods=["POST"])
def entry_seed_wtrf(lb_number: int) -> Response:
    """Seed one LB entry to WTRF, finding its forum post if needed.

    With a ``topic_url`` the post is used directly — the curator has the
    link and knows it is right — and this returns a single JSON object,
    unchanged from before. Without one, the board is searched the same
    way ``/api/wtrf/fetch_torrent`` searches it; that search is paced and
    flood-control-throttled and can take a minute or more (TODO-328), so
    this path instead streams Server-Sent Events — the same start/done/
    error shape the batch WTRF routes use — so the caller can show live
    progress instead of a silent multi-second fetch. A match weaker than
    'medium' is refused rather than guessed at. Either way the torrent is
    downloaded and then run through the shared seeding gates.

    Body JSON (all optional):
      topic_url (str) — skip the search and use this post; when present
        the response is the plain JSON object described below instead of
        an SSE stream
      save_path (str) — directory for the downloaded .torrent
      delay (float, default 2.0) — seconds between HTTP requests
      plus the seeding-policy fields of /api/wtrf/seed_links

    With topic_url: returns JSON with ok, lb_number, topic_url,
    torrent_path, folder, overlay, reason, confidence and error.
    Without topic_url: emits SSE events start, done, error — the done
    and error payloads carry those same fields.
    """
    import json as _json

    from backend.wtrf_seed import (
        LinkSpec,
        _canonical_topic_url,
        _download_torrent,
        is_wtrf_topic_url,
        resolve_link,
        seed_one,
    )

    data      = request.get_json(force=True) or {}
    topic_url = (data.get("topic_url") or "").strip()
    save_path = data.get("save_path") or str(DATA_DIR / "downloads" / "wtrf")
    delay     = float(data.get("delay", 2.0))
    opts      = _wtrf_seed_options(data)

    def _new_out(topic: str | None) -> dict:
        return {
            "ok": False, "lb_number": lb_number, "topic_url": topic,
            "torrent_path": None, "folder": "", "overlay": False,
            "reason": "", "confidence": "not_found", "error": "",
        }

    def _seed_with_torrent(out: dict, torrent_path: str | None, signals: dict) -> dict:
        """Run the shared download-bookkeeping + seed_one tail.

        Args:
            out: The response dict built so far; mutated and returned.
            torrent_path: Path to the downloaded .torrent, or None on
                download failure.
            signals: Match signals recorded alongside the download row.

        Returns:
            The same `out` dict, updated with the seeding outcome.
        """
        if not torrent_path:
            out["error"] = "torrent download failed"
            database.add_wtrf_download(
                lb_number=lb_number, topic_url=out["topic_url"],
                torrent_path=None, confidence=out["confidence"],
                signals_json=_json.dumps(signals), status="failed",
                error=out["error"],
            )
            return out
        out["torrent_path"] = torrent_path
        result = seed_one(lb_number, torrent_path, opts)
        out.update({"ok": result["ok"], "folder": result["folder"],
                    "overlay": result["overlay"], "reason": result["reason"],
                    "error": result["error"]})
        status = "qbt_added" if result["ok"] else (
            "failed" if result["error"] else "not_seeded"
        )
        dl_id = database.add_wtrf_download(
            lb_number=lb_number, topic_url=out["topic_url"],
            torrent_path=torrent_path, confidence=out["confidence"],
            signals_json=_json.dumps(signals),
            status="downloaded" if result["ok"] else status,
            error=result["error"] or (None if result["ok"] else result["reason"]),
            seed_folder=result["folder"] or None,
        )
        if result["ok"]:
            from datetime import UTC, datetime
            database.update_wtrf_download(dl_id, {
                "status": "qbt_added",
                "qbt_added_at": datetime.now(UTC).isoformat(),
            })
        return out

    if topic_url:
        try:
            out = _new_out(topic_url)

            # The cheapest gate first: an entry that may not be published
            # at all should cost nobody a forum round-trip.
            allowed, why = database.is_seedable_to_tracker(lb_number)
            if not allowed:
                out["error"] = f"LB-{lb_number:05d} is not seedable ({why})"
                return jsonify(out), 400

            if not is_wtrf_topic_url(topic_url):
                out["error"] = "That link is not a WTRF forum topic"
                return jsonify(out), 400
            from backend.credentials import SERVICE_WTRF, get_credentials
            from backend.forum_poster import _get_session
            username, password = get_credentials(SERVICE_WTRF)
            session = _get_session(username, password) if username else None
            if session is None:
                out["error"] = "WTRF login failed — check the stored credentials"
                return jsonify(out), 502
            spec = LinkSpec(url=_canonical_topic_url(topic_url),
                            lb_number=lb_number, raw=topic_url)
            info = resolve_link(session, spec, delay)
            out.update({"topic_url": spec.url,
                        "confidence": info["confidence"]})
            if info["error"] or not info["torrent_url"]:
                out["error"] = info["error"] or "no .torrent attachment in that post"
                return jsonify(out), 404
            path = _download_torrent(
                session, info["torrent_url"], Path(save_path), lb_number, delay
            )
            torrent_path = str(path) if path else None
            signals = {"via": "topic_url", "title": info["title"]}
            out = _seed_with_torrent(out, torrent_path, signals)
            return jsonify(out)
        except Exception as exc:
            _log.exception("entry_seed_wtrf LB-%s failed", lb_number)
            return jsonify({"ok": False, "error": str(exc)}), 500

    # No topic_url: the board search is slow, so stream progress via SSE
    # instead of leaving the caller waiting on a single silent fetch.
    def _stream():
        from backend import activity as _activity
        from backend.wtrf_scraper import find_torrent_for_lb

        out = _new_out(None)
        with _activity.track("wtrf_seed_one", screen="/library") as _job:
            try:
                allowed, why = database.is_seedable_to_tracker(lb_number)
                if not allowed:
                    out["error"] = f"LB-{lb_number:05d} is not seedable ({why})"
                    yield f"data: {_json.dumps({'event': 'error', **out})}\n\n"
                    return

                _job.update({"current": 0, "total": 1})
                yield f"data: {_json.dumps({'event': 'start', 'lb_number': lb_number})}\n\n"

                found = find_torrent_for_lb(
                    lb_number=lb_number,
                    board_id=int(database.get_meta("wtrf_board_id") or 16),
                    dest_dir=save_path,
                    delay=delay,
                )
                out.update({"topic_url": found.get("topic_url"),
                            "confidence": found.get("confidence", "not_found")})
                signals = found.get("signals", {})
                if not found["ok"]:
                    out["error"] = found.get("error") or "no matching WTRF post found"
                    database.add_wtrf_download(
                        lb_number=lb_number, topic_url=found.get("topic_url"),
                        torrent_path=None, confidence=out["confidence"],
                        signals_json=_json.dumps(signals), status="skipped",
                        error=out["error"],
                    )
                    yield f"data: {_json.dumps({'event': 'error', **out})}\n\n"
                    return

                out = _seed_with_torrent(out, found.get("torrent_path"), signals)
                _job.update({"current": 1, "total": 1})
                yield f"data: {_json.dumps({'event': 'done', **out})}\n\n"
            except Exception as exc:
                _log.exception("entry_seed_wtrf LB-%s failed", lb_number)
                yield f"data: {_json.dumps({'event': 'error', 'error': str(exc)})}\n\n"

    return Response(
        _stream(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
