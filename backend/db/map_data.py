"""Map feature payload: geocoded shows with filters (from backend.db, TODO-369 S2)."""

from backend.db import get_connection


def get_map_data(filters: dict, db_path=None) -> dict:
    """Return marker data and unplottable count for the map view.

    Args:
        filters: Dict with optional keys: status (str), owned (bool),
                 year_min (int), year_max (int), q (str).
        db_path: Optional path to the SQLite database file. Defaults to DB_PATH.

    Returns:
        Dict with keys "markers" (list of dicts) and "unplottable_count" (int).
        Each marker dict contains: lb_number, date_str, location, lb_status,
        owned, lat, lon, display_name, city_level (bool — True when the pin
        is only city-precision rather than a resolved venue, TODO-223 bite 3).
    """
    conn = get_connection(db_path)

    clauses: list[str] = []
    params: list = []

    status = filters.get("status")
    if status:
        clauses.append("lm.lb_status = ?")
        params.append(status)

    owned = filters.get("owned")
    if owned is True:
        clauses.append("mc.lb_number IS NOT NULL")
    elif owned is False:
        clauses.append("mc.lb_number IS NULL")

    year_min = filters.get("year_min")
    if year_min is not None:
        clauses.append("CAST(SUBSTR(e.date_str, INSTR(e.date_str, '/') + INSTR(SUBSTR(e.date_str,"
                       " INSTR(e.date_str, '/') + 1), '/') + INSTR(e.date_str, '/'), 10) AS INTEGER)"
                       " >= ?")
        params.append(int(year_min))

    year_max = filters.get("year_max")
    if year_max is not None:
        clauses.append("CAST(SUBSTR(e.date_str, INSTR(e.date_str, '/') + INSTR(SUBSTR(e.date_str,"
                       " INSTR(e.date_str, '/') + 1), '/') + INSTR(e.date_str, '/'), 10) AS INTEGER)"
                       " <= ?")
        params.append(int(year_max))

    q = filters.get("q")
    if q:
        like = f"%{q}%"
        clauses.append("(e.lb_number LIKE ? OR e.location LIKE ?)")
        params.extend([like, like])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
        SELECT e.lb_number, e.date_str, e.location,
               lm.lb_status,
               CASE WHEN mc.lb_number IS NOT NULL THEN 1 ELSE 0 END AS owned,
               geo.lat, geo.lon, geo.display_name, geo.source, geo.confidence
        FROM entries e
        LEFT JOIN location_geocoded geo
               ON e.location = geo.location_text AND geo.confidence != 'low'
        LEFT JOIN lb_master lm ON e.lb_number = lm.lb_number
        LEFT JOIN my_collection mc ON e.lb_number = mc.lb_number
        {where}
        ORDER BY e.lb_number
    """

    rows = conn.execute(sql, params).fetchall()

    markers: list[dict] = []
    unplottable_count = 0

    city_level_sources = {"setlistfm_city", "city_geocode", "gazetteer_city"}
    for row in rows:
        if row["lat"] is not None and row["lon"] is not None:
            source = row["source"] or ""
            markers.append({
                "lb_number": row["lb_number"],
                "date_str": row["date_str"],
                "location": row["location"],
                "lb_status": row["lb_status"],
                "owned": bool(row["owned"]),
                "lat": row["lat"],
                "lon": row["lon"],
                "display_name": row["display_name"],
                "city_level": source in city_level_sources or source.endswith("-city"),
            })
        else:
            unplottable_count += 1

    return {"markers": markers, "unplottable_count": unplottable_count}
