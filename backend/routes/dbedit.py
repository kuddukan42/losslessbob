"""DB Editor routes (FEAT-14) — /api/dbedit/*."""

import logging
import re
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from backend import db as database
from backend.paths import BATCH_VERIFY_DB_PATH, TAPEMATCH_DB_PATH

_log = logging.getLogger(__name__)

bp = Blueprint("dbedit", __name__)


# ── FEAT-14: DB Editor table classification ───────────────────────────────────
_DBEDIT_READONLY = frozenset({"entries_fts"})
_DBEDIT_AUDIT    = frozenset({"entry_changes", "integrity_events"})
_DBEDIT_WARN     = frozenset({"checksums", "entries", "entry_files"})


# Alternate databases browsable in the DB Editor, all read-only (tool-generated data).
_DBEDIT_READONLY_DBS = {
    "batchverify": BATCH_VERIFY_DB_PATH,
    "tapematch":   TAPEMATCH_DB_PATH,
}


def _dbedit_db_path() -> str:
    """Return the SQLite path for the current dbedit request based on ?db= param."""
    alt = _DBEDIT_READONLY_DBS.get(request.args.get("db", "").lower())
    return str(alt) if alt is not None else str(database.DB_PATH)


def _dbedit_is_batchverify() -> bool:
    """Return True if the current dbedit request targets a read-only alternate DB."""
    return request.args.get("db", "").lower() in _DBEDIT_READONLY_DBS


def _parse_lb_filter(lb_filter: str) -> list[int] | None:
    """Parse a comma/space-separated LB-number filter into a list of ints.

    Accepts one or more integers separated by any mix of commas and/or
    whitespace (e.g. "4929", "4929,5683", "4929 5683", "4929, 5683 9627").

    Args:
        lb_filter: Raw filter string from the ``lb_number`` query param.

    Returns:
        A list of parsed integers, or None if any token is not a valid
        integer (matching the prior single-value rejection behavior, which
        silently skips the filter rather than erroring).
    """
    tokens = [t for t in re.split(r"[,\s]+", lb_filter.strip()) if t]
    if not tokens:
        return None
    values = []
    for token in tokens:
        if not token.lstrip("-").isdigit():
            return None
        values.append(int(token))
    return values


# ── FEAT-14: DB Editor ───────────────────────────────────────────────────

@bp.route("/api/dbedit/tables", methods=["GET"])
def dbedit_tables() -> Response:
    """List all user-visible tables and views with row counts and edit flags.

    Returns:
        JSON list of {name, row_count, readonly, audit, warn} dicts.
    """
    try:
        is_bv = _dbedit_is_batchverify()
        conn = database.get_connection(_dbedit_db_path())
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY name"
        ).fetchall()
        result = []
        for r in rows:
            name = r["name"]
            if (name.startswith("sqlite_")
                    or any(name.endswith(sfx) for sfx in
                           ("_fts_data", "_fts_idx", "_fts_content",
                            "_fts_docsize", "_fts_config"))):
                continue
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM [{name}]"
                ).fetchone()[0]
            except Exception:
                count = -1
            result.append({
                "name":      name,
                "row_count": count,
                "readonly":  is_bv or name in _DBEDIT_READONLY,
                "audit":     not is_bv and name in _DBEDIT_AUDIT,
                "warn":      not is_bv and name in _DBEDIT_WARN,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/table/<name>/schema", methods=["GET"])
def dbedit_schema(name: str) -> Response:
    """Return PRAGMA table_info columns for a named table.

    Args:
        name: The SQLite table name to inspect.

    Returns:
        JSON list of column info dicts from PRAGMA table_info.
    """
    try:
        conn = database.get_connection(_dbedit_db_path())
        cols = conn.execute(
            f"PRAGMA table_info([{name}])"
        ).fetchall()
        return jsonify([dict(c) for c in cols])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/table/<name>/rows", methods=["GET"])
def dbedit_rows(name: str) -> Response:
    """Return a paginated, searchable, sortable slice of a table's rows.

    Args:
        name: The SQLite table name to query.

    Query params: page, limit (max 500), search, sort_col, sort_dir, lb_number.
    Returns:
        JSON {columns, rows, total, page, limit}.
    """
    try:
        page     = max(0, int(request.args.get("page", 0)))
        limit    = max(1, min(int(request.args.get("limit", 100)), 500))
        search   = request.args.get("search", "").strip()
        sort_col = request.args.get("sort_col", "")
        sort_dir = "DESC" if request.args.get("sort_dir", "asc") == "desc" else "ASC"
        conn     = database.get_connection(_dbedit_db_path())

        lb_filter = request.args.get("lb_number", "").strip()
        where, params = "", []
        if search:
            text_cols = [
                c["name"] for c in
                conn.execute(f"PRAGMA table_info([{name}])").fetchall()
                if "TEXT" in (c["type"] or "").upper() or not c["type"]
            ]
            if text_cols:
                clauses = [f"CAST([{c}] AS TEXT) LIKE ?" for c in text_cols]
                where   = "WHERE " + " OR ".join(clauses)
                params  = [f"%{search}%"] * len(text_cols)
        if lb_filter:
            lb_values = _parse_lb_filter(lb_filter)
            if lb_values:
                col_names = [c["name"] for c in
                             conn.execute(f"PRAGMA table_info([{name}])").fetchall()]
                if "lb_number" in col_names:
                    placeholders = ", ".join("?" * len(lb_values))
                    lb_clause = f"lb_number IN ({placeholders})"
                    where = (f"WHERE {lb_clause}" if not where
                             else where + f" AND {lb_clause}")
                    params.extend(lb_values)

        order = f"ORDER BY [{sort_col}] {sort_dir}" if sort_col else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM [{name}] {where}", params
        ).fetchone()[0]
        cur = conn.execute(
            f"SELECT rowid, * FROM [{name}] {where} {order} LIMIT ? OFFSET ?",
            params + [limit, page * limit]
        )
        rows = cur.fetchall()

        # cur.description is always populated after execute, even for empty result sets
        cols = ([d[0] for d in cur.description] if cur.description else
                ["rowid"] + [c["name"] for c in
                 conn.execute(f"PRAGMA table_info([{name}])").fetchall()])
        return jsonify({
            "columns": cols,
            "rows":    [list(r) for r in rows],
            "total":   total,
            "page":    page,
            "limit":   limit,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/table/<name>/row", methods=["PATCH"])
def dbedit_update_row(name: str) -> Response:
    """Update a single row in a named table by rowid.

    Args:
        name: The SQLite table name to update.

    Body: {rowid: int, updates: {col: value, ...}}
    Returns:
        JSON {ok, affected} or 403/400 on permission/validation error.
    """
    if _dbedit_is_batchverify() or name in _DBEDIT_READONLY or name in _DBEDIT_AUDIT:
        return jsonify({"error": f"Table {name!r} is not editable"}), 403
    try:
        data    = request.get_json() or {}
        rowid   = data.get("rowid")
        updates = data.get("updates", {})
        if rowid is None or not updates:
            return jsonify({"error": "rowid and updates required"}), 400
        rconn = database.get_connection()
        valid = {c["name"] for c in
                 rconn.execute(f"PRAGMA table_info([{name}])").fetchall()}
        bad = [k for k in updates if k not in valid]
        if bad:
            return jsonify({"error": f"Unknown columns: {bad}"}), 400
        set_clause = ", ".join(f"[{k}]=?" for k in updates)
        _tbl, _sc, _vals = name, set_clause, list(updates.values()) + [rowid]
        affected = database.get_write_queue().execute(
            lambda c: c.execute(
                f"UPDATE [{_tbl}] SET {_sc} WHERE rowid=?", _vals
            ).rowcount
        )
        return jsonify({"ok": True, "affected": affected})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/table/<name>/rows", methods=["DELETE"])
def dbedit_delete_rows(name: str) -> Response:
    """Delete one or more rows from a named table by rowid list.

    Args:
        name: The SQLite table name to delete from.

    Body: {rowids: [int, ...]}
    Returns:
        JSON {ok, deleted} or 403/400 on permission/validation error.
    """
    if _dbedit_is_batchverify() or name in _DBEDIT_READONLY:
        return jsonify({"error": f"Table {name!r} cannot be modified"}), 403
    try:
        rowids = (request.get_json() or {}).get("rowids", [])
        if not rowids:
            return jsonify({"error": "rowids list required"}), 400
        ph = ",".join("?" * len(rowids))
        _tbl, _ph, _rids = name, ph, list(rowids)
        deleted = database.get_write_queue().execute(
            lambda c: c.execute(
                f"DELETE FROM [{_tbl}] WHERE rowid IN ({_ph})", _rids
            ).rowcount
        )
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/table/<name>/export", methods=["GET"])
def dbedit_export(name: str) -> Response:
    """Export all rows of a named table as a CSV file download.

    Args:
        name: The SQLite table name to export.

    Returns:
        CSV file attachment with Content-Disposition header.
    """
    try:
        import csv
        import io
        conn = database.get_connection(_dbedit_db_path())
        rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
        buf  = io.StringIO()
        if rows:
            writer = csv.writer(buf)
            writer.writerow(rows[0].keys())
            writer.writerows(rows)
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition":
                     f"attachment; filename={name}.csv"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dbedit/query", methods=["POST"])
def dbedit_query() -> Response:
    """Execute an arbitrary SQL query against losslessbob.db.

    Body: {sql: str, limit: int (optional, default 500, max 2000)}
    Returns:
        SELECT/PRAGMA/WITH: {columns, rows, row_count, truncated}
        DML (INSERT/UPDATE/DELETE): {ok, rows_affected}
        Error: {error: str} with 400 status.
    """
    body = request.get_json(force=True, silent=True) or {}
    sql: str = (body.get("sql") or "").strip()
    if not sql:
        return jsonify({"error": "No SQL provided."}), 400

    limit = min(int(body.get("limit", 500)), 2000)
    alt_db = _DBEDIT_READONLY_DBS.get((body.get("db") or "").lower())
    query_db = str(alt_db) if alt_db is not None else str(database.DB_PATH)
    is_bv_query = alt_db is not None

    upper = sql.upper()
    for blocked in ("DROP ", "TRUNCATE ", "VACUUM", "ATTACH ", "DETACH "):
        if upper.startswith(blocked):
            return jsonify({
                "error": f"Statement type blocked: {blocked.strip()}."
                         " Use the schema editor for structural changes."
            }), 400

    is_read = any(upper.startswith(kw) for kw in
                  ("SELECT", "PRAGMA", "WITH", "EXPLAIN", "VALUES"))
    if is_bv_query and not is_read:
        return jsonify({"error": f"{Path(query_db).name} is read-only."}), 403
    try:
        if is_read:
            conn = database.get_connection(query_db)
            cur = conn.execute(sql)
        else:
            result_holder: list = []

            def _run(c: object) -> None:
                cur = c.execute(sql)  # type: ignore[attr-defined]
                result_holder.append(cur)

            database.get_write_queue().execute(_run)
            cur = result_holder[0] if result_holder else None

        if cur is not None and cur.description:
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(limit)]
            return jsonify({
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": len(rows) >= limit,
            })
        else:
            affected = cur.rowcount if cur is not None else 0
            return jsonify({"ok": True, "rows_affected": affected, "columns": [], "rows": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
