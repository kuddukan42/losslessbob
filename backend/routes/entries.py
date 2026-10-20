"""Entry detail, attachments, entry changes/scrape, search and xref-map routes."""

import json
import logging
import sqlite3

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    request,
    send_file,
)

from backend import db as database
from backend import scraper
from backend.paths import attachment_path
from concert_ranker.config import resolve_band_set
from concert_ranker.scoring import band_metric

_log = logging.getLogger(__name__)

bp = Blueprint("entries", __name__)


# Metrics surfaced on the Quality tab, banded to human labels via the same
# thresholds concert_ranker's scoring brain uses for verdict_text (see
# concert_ranker/config.py SIGNED_BANDS/SEVERITY_BANDS). Source-type flags use
# the 0.5 threshold concert_ranker's lossy_flag disqualifier uses (config.py).
_SOURCE_FLAG_LABELS = {
    "lossy_flag": "lossy source suspected",
    "minidisc_score": "minidisc (ATRAC) signature",
    "dat32k_flag": "32kHz DAT (16k bandwidth cap)",
    "cassette_flag": "cassette tape rolloff",
    "tv_band_flag": "TV-band artifact",
}


def _quality_metrics_for(conn: sqlite3.Connection, scan_id: int, lb_number: int) -> dict | None:
    """Pull raw Concert Ranker metrics for one scored recording and band them.

    Args:
        conn: Open DB connection.
        scan_id: The scan whose metrics to read.
        lb_number: The LB number to look up.

    Returns:
        Dict of banded stereo/clipping/crowd/tonal/source-flag fields for the
        Quality tab, or None if the recording has no stored raw metrics.
    """
    row = conn.execute(
        "SELECT metric_json, source_class FROM quality_recording_metrics"
        " WHERE scan_id=? AND lb_number=?",
        (scan_id, lb_number),
    ).fetchone()
    if not row or not row["metric_json"]:
        return None
    raw = json.loads(row["metric_json"]).get("metrics", {})
    bset = resolve_band_set(source_class=row["source_class"])
    signed, severity, quality = bset["SIGNED"], bset["SEVERITY"], bset["QUALITY"]

    def band(metric: str) -> str | None:
        return band_metric(metric, raw.get(metric), signed, severity, quality)

    source_flags = [
        label for metric, label in _SOURCE_FLAG_LABELS.items()
        if (raw.get(metric) or 0) >= 0.5
    ]
    return {
        "mono": raw.get("lr_corr") is None,
        "stereo_width": raw.get("stereo_width"),
        "stereo_width_label": band("stereo_width"),
        "clip_fraction": raw.get("clip_fraction"),
        "crowd_snr_db": raw.get("crowd_snr_db"),
        "crowd_snr_label": band("crowd_snr_db"),
        "bass_ratio_db": raw.get("bass_ratio_db"),
        "bass_label": band("bass_ratio_db"),
        "mud_ratio_db": raw.get("mud_ratio_db"),
        "mud_label": band("mud_ratio_db"),
        "harsh_ratio_db": raw.get("harsh_ratio_db"),
        "harsh_label": band("harsh_ratio_db"),
        "source_flags": source_flags,
    }


# ── Entry Detail & Attachments ───────────────────────────────────────────

@bp.route("/api/entry/<int:lb_number>", methods=["GET"])
def get_entry(lb_number: int) -> Response:
    """Return metadata for a single LB entry.

    Args:
        lb_number: The LB number to look up.

    Returns:
        JSON dict with entry fields, or 404 if not found.
    """
    try:
        data = database.get_entry(lb_number)
        if not data:
            return jsonify({"error": "Entry not found"}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/entry/<int:lb_number>/files", methods=["GET"])
def get_entry_files(lb_number: int) -> Response:
    """Return all entry_files rows for a single LB entry.

    Args:
        lb_number: The LB number whose files to retrieve.

    Returns:
        JSON list of entry_files dicts.
    """
    try:
        with database.get_connection() as conn:
            files = conn.execute(
                "SELECT * FROM entry_files WHERE lb_number=?", (lb_number,)
            ).fetchall()
        return jsonify([dict(f) for f in files])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/quality/<int:lb_number>", methods=["GET"])
def get_quality(lb_number: int) -> Response:
    """Return the latest Concert Ranker quality score for one recording.

    Args:
        lb_number: The LB number to look up.

    Returns:
        JSON dict with final_score/rank_in_family/vetoed/verdict_text/
        abs_score/abs_grade from the most recent scan that actually wrote
        scores, plus a ``metrics`` sub-dict of banded raw signals (stereo
        width, clipping, crowd separation, tonal balance, source-type
        flags) for the Quality tab visualizations, or 204 if the
        recording has never been scanned.
    """
    try:
        with database.get_connection() as conn:
            # Calibration runs and one-off scans rerank a few LBs into their
            # own scan_id, so read the library's scored scan (BUG-345).
            from concert_ranker.lb import repo as cr_repo

            scan_id = cr_repo.scored_scan_id(conn)
            if scan_id is None:
                return "", 204
            row = conn.execute(
                "SELECT final_score, rank_in_family, vetoed, verdict_text,"
                    " abs_score, abs_grade FROM quality_recording_scores"
                    " WHERE scan_id=? AND lb_number=?",
                (scan_id, lb_number),
            ).fetchone()
            if not row:
                return "", 204
            result = dict(row)
            result["metrics"] = _quality_metrics_for(conn, scan_id, lb_number)
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/attachment/<int:lb_number>/<path:filename>", methods=["GET"])
def get_attachment(lb_number: int, filename: str) -> Response:
    """Serve a downloaded attachment file for an LB entry.

    Args:
        lb_number: The LB number owning the attachment.
        filename: Clean filename (no LBF- prefix); looked up in entry_files.

    Returns:
        The file contents, or 404 if not found.
    """
    # filename is the clean_name (no LBF- prefix); look up original filename
    row = database.get_connection().execute(
        "SELECT filename FROM entry_files WHERE lb_number=? AND clean_name=?",
        (lb_number, filename),
    ).fetchone()
    if not row:
        abort(404)
    file_path = attachment_path(row["filename"])
    if not file_path.exists():
        abort(404)
    return send_file(str(file_path))


@bp.route("/api/attachments/reconcile", methods=["POST"])
def attachments_reconcile() -> Response:
    """Mark entry_files.downloaded=1 for rows present in site_inventory.

    Returns:
        JSON {updated: N} with the number of rows updated.
    """
    try:
        with database.get_connection() as conn:
            cur = conn.execute(
                """
                    UPDATE entry_files
                    SET downloaded = 1
                    WHERE downloaded = 0
                      AND file_url IN (
                          SELECT url FROM site_inventory WHERE status = 'downloaded'
                      )
                    """
            )
            updated = cur.rowcount
        return jsonify({"updated": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/attachments/cached", methods=["GET"])
def attachments_cached() -> Response:
    """Return downloaded entry_files grouped by LB number, plus total entry count.

    Returns:
        JSON {entries: [{lb_number, files: [{filename, clean_name}], lb_status}],
              total: int}.
    """
    try:
        conn = database.get_connection()
        rows = conn.execute(
            """
                SELECT ef.lb_number, ef.filename, ef.clean_name, ef.downloaded, lm.lb_status
                FROM entry_files ef
                LEFT JOIN lb_master lm ON lm.lb_number = ef.lb_number
                WHERE ef.downloaded = 1
                ORDER BY ef.lb_number, ef.clean_name
                """
        ).fetchall()
        grouped: dict = {}
        for r in rows:
            lb = r["lb_number"]
            if lb not in grouped:
                grouped[lb] = {
                    "lb_number": lb,
                    "files": [],
                    "lb_status": r["lb_status"],
                }
            grouped[lb]["files"].append(
                {"filename": r["filename"], "clean_name": r["clean_name"], "downloaded": r["downloaded"]}
            )
        all_entries = [v for _, v in sorted(grouped.items())]
        total = conn.execute(
            "SELECT COUNT(DISTINCT lb_number) FROM checksums"
        ).fetchone()[0]
        return jsonify({"entries": all_entries, "total": total})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/entry/<int:lb_number>/changes", methods=["GET"])
def entry_changes(lb_number: int) -> Response:
    """Return field-level change history for a single LB entry.

    Args:
        lb_number: The LB number to query.

    Returns:
        JSON list of {field, old_value, new_value, changed_at} dicts,
        ordered by changed_at DESC. Query param: limit (default 50).
    """
    try:
        limit = int(request.args.get("limit", 50))
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT field, old_value, new_value, changed_at "
                "FROM entry_changes WHERE lb_number=? "
                "ORDER BY changed_at DESC LIMIT ?",
            (lb_number, limit)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/entry/<int:lb_number>/scrape", methods=["POST"])
def scrape_entry_route(lb_number: int) -> Response:
    """Scrape (or force re-scrape) a single LB entry from the source site.

    Args:
        lb_number: The LB number to scrape.

    Body: {force: bool}
    Returns:
        JSON result dict from scraper.scrape_entry().
    """
    try:
        data = request.get_json() or {}
        force = data.get("force", False)
        download = database.get_meta("scrape_attachments") != "0"
        use_local_pages = database.get_meta("use_local_pages") == "1"
        result = scraper.scrape_entry(lb_number, force=force, download_files=download, use_local_pages=use_local_pages)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Search ───────────────────────────────────────────────────────────────

@bp.route("/api/search", methods=["GET"])
def search() -> Response:
    """Search entries by keyword, field filter, and optional year.

    Query params: q (text), field (all|title|location|etc.), year (int).
    Returns:
        JSON list of matching entry dicts.
    """
    # NOTE: sort_col/sort_dir accepted for API completeness; the GUI currently
    # performs in-memory sorting on the full result set.
    try:
        q = request.args.get("q", "")
        field = request.args.get("field", "all")
        year_str = request.args.get("year")
        year = int(year_str) if year_str else None
        sort_col = request.args.get("sort_col", "")
        sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
        _SEARCH_SORT_COLS = {
            "lb_number": "e.lb_number",
            "date_str":  "e.date_str",
            "location":  "e.location",
            "lb_status": (
                "CASE lm.lb_status WHEN 'public' THEN 0 "
                    "WHEN 'private' THEN 1 WHEN 'missing' THEN 2 END"
            ),
        }
        results = database.search_entries(q, field, year=year)
        if sort_col and sort_col in _SEARCH_SORT_COLS:
            reverse = sort_dir == "DESC"
            key_map = {
                "lb_number": lambda r: r.get("lb_number") or 0,
                "date_str":  lambda r: (r.get("date_str") or "").lower(),
                "location":  lambda r: (r.get("location") or "").lower(),
                "lb_status": lambda r: {"public": 0, "private": 1,
                                        "missing": 2}.get(
                                       r.get("lb_status") or "", 99),
            }
            results.sort(key=key_map[sort_col], reverse=reverse)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/search/years", methods=["GET"])
def search_years() -> Response:
    """Return the distinct years present in the entries table.

    Returns:
        JSON list of year strings for populating filter dropdowns.
    """
    try:
        return jsonify(database.get_distinct_years())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/checksums/xref_map", methods=["GET"])
def xref_map() -> Response:
    """Return, per LB entry, the alternate xref fileset ids documented for it.

    Returns:
        JSON dict {lb_number: [xref ids]} (entry-level: which LBs have
        alternate circulating filesets, and which fileset ids those are —
        see docs/XREF_SEMANTICS.md §3).
    """
    try:
        return jsonify(database.get_xref_map())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/entries/reclassify", methods=["POST"])
def entries_reclassify() -> Response:
    """Re-classify all entries lb_category using bobdylan_shows + dylan_performances + keywords.

    Curator-only. Returns classification counts.
    """
    if not database.is_curator():
        return jsonify({"error": "curator_required"}), 403
    try:
        counts = database.classify_entry_categories()
        return jsonify({"ok": True, **counts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
