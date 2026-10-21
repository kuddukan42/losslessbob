"""Collection trading routes: export, friends, compare, batch compare (TODO-369)."""

import logging

from flask import (
    Blueprint,
    jsonify,
    request,
)

from backend import db as database

_log = logging.getLogger(__name__)

bp = Blueprint("trading", __name__)


# ── Collection Trading ────────────────────────────────────────────────────

@bp.route("/api/trading/export", methods=["GET"])
def trading_export():
    """Export the user's collection as a .lbcollection JSON blob.

    Returns:
        JSON: {losslessbob_collection, export_version, exported_at, entries}
    """
    try:
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT mc.lb_number, e.date_str, e.location, e.status "
                "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number "
                "ORDER BY mc.lb_number"
        ).fetchall()
        import datetime as _dt
        return jsonify({
            "losslessbob_collection": True,
            "export_version": 1,
            "exported_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "entries": [
                {"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]}
                for r in rows
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/friends", methods=["GET"])
def trading_friends_list():
    """List all stored friend collections.

    Returns:
        JSON: [{id, friend_name, imported_at, updated_at, lb_count}]
    """
    try:
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT id, friend_name, imported_at, updated_at, lb_count FROM friend_collections ORDER BY friend_name"
        ).fetchall()
        return jsonify([
            {"id": r[0], "friend_name": r[1], "imported_at": r[2], "updated_at": r[3], "lb_count": r[4]}
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/friends", methods=["POST"])
def trading_friends_upsert():
    """Import or update a friend's collection.

    Request JSON: {friend_name: str, entries: [{lb_number, date_str?, location?, lb_status?}]}

    Returns:
        JSON: {ok, friend_id}
    """
    try:
        data = request.get_json(force=True)
        friend_name = str(data.get("friend_name", "")).strip()
        entries = data.get("entries", [])
        if not friend_name:
            return jsonify({"error": "friend_name required"}), 400

        import datetime as _dt
        conn = database.get_connection()
        now = _dt.datetime.now(_dt.UTC).isoformat()
        existing = conn.execute(
            "SELECT id FROM friend_collections WHERE friend_name = ?", (friend_name,)
        ).fetchone()

        if existing:
            friend_id = existing[0]
            conn.execute(
                "UPDATE friend_collections SET updated_at = ?, lb_count = ? WHERE id = ?",
                (now, len(entries), friend_id),
            )
            conn.execute("DELETE FROM friend_collection_entries WHERE friend_id = ?", (friend_id,))
        else:
            cur = conn.execute(
                "INSERT INTO friend_collections (friend_name, lb_count) VALUES (?, ?)",
                (friend_name, len(entries)),
            )
            friend_id = cur.lastrowid

        conn.executemany(
            "INSERT OR IGNORE INTO friend_collection_entries (friend_id, lb_number, date_str, location, lb_status) VALUES (?, ?, ?, ?, ?)",
            [
                (friend_id, e.get("lb_number"), e.get("date_str"), e.get("location"), e.get("lb_status"))
                for e in entries if e.get("lb_number")
            ],
        )
        conn.commit()
        return jsonify({"ok": True, "friend_id": friend_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/friends/<int:friend_id>", methods=["DELETE"])
def trading_friends_delete(friend_id):
    """Remove a stored friend collection.

    Args:
        friend_id: Row ID in friend_collections.

    Returns:
        JSON: {ok}
    """
    try:
        conn = database.get_connection()
        conn.execute("DELETE FROM friend_collections WHERE id = ?", (friend_id,))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/compare/<int:friend_id>", methods=["GET"])
def trading_compare(friend_id):
    """Diff the user's collection against a friend's.

    Args:
        friend_id: Row ID in friend_collections.

    Returns:
        JSON: {friend_name, you_have_they_dont, they_have_you_dont, both_have_count}
    """
    try:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT friend_name FROM friend_collections WHERE id = ?", (friend_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "friend not found"}), 404
        friend_name = row[0]

        mine = {r[0] for r in conn.execute("SELECT lb_number FROM my_collection").fetchall()}
        theirs = {r[0] for r in conn.execute(
            "SELECT lb_number FROM friend_collection_entries WHERE friend_id = ?", (friend_id,)
        ).fetchall()}

        def _enrich(lb_numbers):
            if not lb_numbers:
                return []
            result = []
            for lb in sorted(lb_numbers):
                r = conn.execute(
                    "SELECT mc.lb_number, e.date_str, e.location, e.status "
                        "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number "
                        "WHERE mc.lb_number = ? "
                        "UNION SELECT fce.lb_number, fce.date_str, fce.location, fce.lb_status "
                        "FROM friend_collection_entries fce WHERE fce.friend_id = ? AND fce.lb_number = ?",
                    (lb, friend_id, lb),
                ).fetchone()
                if r:
                    result.append({"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]})
                else:
                    result.append({"lb_number": lb, "date_str": None, "location": None, "lb_status": None})
            return result

        you_have = mine - theirs
        they_have = theirs - mine
        both = mine & theirs

        return jsonify({
            "friend_name": friend_name,
            "you_have_they_dont": _enrich(you_have),
            "they_have_you_dont": _enrich(they_have),
            "both_have_count": len(both),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/friends/<int:friend_id>/entries", methods=["GET"])
def trading_friend_entries(friend_id):
    """Paginated raw entries of one friend's collection.

    Args:
        friend_id: Row ID in friend_collections.

    Query: q (substring of date/location/LB#), limit (default 100, max 500), offset.

    Returns:
        JSON: {friend_id, friend_name, total, offset, limit, entries}
    """
    try:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT friend_name FROM friend_collections WHERE id = ?", (friend_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "friend not found"}), 404
        limit = max(1, min(request.args.get("limit", 100, type=int), 500))
        offset = max(0, request.args.get("offset", 0, type=int))
        q = (request.args.get("q") or "").strip()
        where, params = "friend_id = ?", [friend_id]
        if q:
            where += " AND (CAST(lb_number AS TEXT) LIKE ? OR date_str LIKE ? OR location LIKE ?)"
            like = f"%{q}%"
            params += [like, like, like]
        total = conn.execute(
            f"SELECT COUNT(*) FROM friend_collection_entries WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT lb_number, date_str, location, lb_status FROM friend_collection_entries "
                f"WHERE {where} ORDER BY lb_number LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return jsonify({
            "friend_id": friend_id, "friend_name": row[0], "total": total,
            "offset": offset, "limit": limit,
            "entries": [
                {"lb_number": r[0], "date_str": r[1], "location": r[2], "lb_status": r[3]}
                for r in rows
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/trading/batch-compare", methods=["POST"])
def trading_batch_compare():
    """Compare the user's collection against N friends at once (friends x shows).

    Request JSON: {friend_ids: [int], mode?: "want"|"offer"|"all" (default "all"),
    q?: str, limit?: int (default 100, max 500), offset?: int}

    A show is a "want" row when you lack it and some selected friend has it, and an
    "offer" row when you have it and some selected friend lacks it. For each row,
    best_friend_id is the candidate friend (has it / lacks it) with the largest
    two-way trade potential min(they_have_you_dont, you_have_they_dont), ties broken
    by total overlap potential then name.

    Returns:
        JSON: {friends: [{id, friend_name, they_have_you_dont, you_have_they_dont,
        both_have, potential}], total, offset, limit, rows: [{lb_number, date_str,
        location, lb_status, you_have, kind, cells: {friend_id: bool},
        best_friend_id}]}
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        ids = []
        for v in data.get("friend_ids") or []:
            try:
                if int(v) not in ids:
                    ids.append(int(v))
            except (TypeError, ValueError):
                return jsonify({"error": "friend_ids must be integers"}), 400
        if not ids:
            return jsonify({"error": "friend_ids required"}), 400
        if len(ids) > 50:
            return jsonify({"error": "too many friends (max 50)"}), 400
        mode = data.get("mode") or "all"
        if mode not in ("want", "offer", "all"):
            return jsonify({"error": "invalid mode"}), 400
        limit = max(1, min(int(data.get("limit") or 100), 500))
        offset = max(0, int(data.get("offset") or 0))
        q = str(data.get("q") or "").strip().lower()

        conn = database.get_connection()
        ph = ",".join("?" * len(ids))
        frows = conn.execute(
            f"SELECT id, friend_name FROM friend_collections WHERE id IN ({ph})", ids
        ).fetchall()
        names = {r[0]: r[1] for r in frows}
        ids = [i for i in ids if i in names]
        if not ids:
            return jsonify({"error": "friends not found"}), 404

        mine = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
            "SELECT mc.lb_number, e.date_str, e.location, e.status "
                "FROM my_collection mc LEFT JOIN entries e ON e.lb_number = mc.lb_number"
        ).fetchall()}
        theirs: dict[int, set[int]] = {i: set() for i in ids}
        meta: dict[int, tuple] = {}
        ph = ",".join("?" * len(ids))
        for fid, lb, d, loc, st in conn.execute(
            "SELECT friend_id, lb_number, date_str, location, lb_status "
                f"FROM friend_collection_entries WHERE friend_id IN ({ph})", ids
        ):
            theirs[fid].add(lb)
            meta.setdefault(lb, (d, loc, st))

        mine_set = set(mine)
        summary = {}
        for i in ids:
            want = len(theirs[i] - mine_set)
            offer = len(mine_set - theirs[i])
            summary[i] = {
                "id": i, "friend_name": names[i], "they_have_you_dont": want,
                "you_have_they_dont": offer, "both_have": len(mine_set & theirs[i]),
                "potential": min(want, offer),
            }

        def rank(i: int) -> tuple:
            s = summary[i]
            return (-s["potential"], -(s["they_have_you_dont"] + s["you_have_they_dont"]),
                    names[i].lower())

        all_lbs = mine_set.union(*theirs.values())
        out = []
        for lb in sorted(all_lbs):
            have = lb in mine_set
            holders = [i for i in ids if lb in theirs[i]]
            if not have and holders:
                kind, cands = "want", holders
            elif have and len(holders) < len(ids):
                kind, cands = "offer", [i for i in ids if lb not in theirs[i]]
            else:
                continue
            if mode != "all" and kind != mode:
                continue
            d, loc, st = mine[lb] if have else meta.get(lb, (None, None, None))
            if q and q not in f"{lb} {d or ''} {loc or ''}".lower():
                continue
            out.append({
                "lb_number": lb, "date_str": d, "location": loc, "lb_status": st,
                "you_have": have, "kind": kind,
                "cells": {str(i): lb in theirs[i] for i in ids},
                "best_friend_id": min(cands, key=rank),
            })
        return jsonify({
            "friends": [summary[i] for i in ids], "total": len(out),
            "offset": offset, "limit": limit, "rows": out[offset:offset + limit],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
