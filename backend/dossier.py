"""Show dossier assembly (TODO-257, instructions/FABLE_SHOW_DOSSIER.md).

Renders everything the app knows about one date into a single JSON shape:
setlist with rarity flags, circulating sources grouped by master-tape family
with taper credit / pick ranking / quality verdicts, historical context, and
a provenance footer. Feature-detected end to end — a fresh install with none
of the derived tables populated still assembles a smaller, valid dossier; a
missing source silently drops its section, it never errors (spec §1).

Entry point: :func:`build_dossier`. Two return shapes: the normal D1 shape,
or ``{"ambiguous": True, "date_iso", "candidates"}`` when the date has more
than one distinct ``olof_events.venue`` (a genuine two-show date) and no
``location`` was given to disambiguate (spec D1).

:func:`filter_dossier_sections` and :func:`render_bbcode` are the D4/D5
presentation layer — the HTML template and the BBcode digest render from the
same filtered view so they can't drift (spec D5).

Privacy (spec D2): ``channel='public'`` (default) reduces any source whose
``entries.status='private'`` to ``{lb, private: true}`` — literally nothing
else. ``channel='full'`` includes everything. Disk paths, collection
ownership, friend data and wishlists are never touched by this module at all.
"""
from __future__ import annotations

import datetime
import functools
import json
import logging
import math
import os
import sqlite3
import urllib.parse

from backend.db import get_connection
from backend.geocoder import entry_date_to_iso
from backend.paths import SITE_BASE_URL, detail_url

log = logging.getLogger(__name__)

# D-3: rarity threshold — <= this many all-time performances is 'rare'.
RARE_THRESHOLD = 10

# Local copy of gap_analysis.py's concert-type filter (repo convention is to
# duplicate small private feature-detect helpers rather than cross-import —
# see gap_analysis.py's own docstring on this).
_CONCERT_TYPE_FILTER = (
    "((event_type = 'concert' OR event_type LIKE 'concert - %') "
    "AND tour_name NOT LIKE '%ehearsal%')"
)

# D-Bite2: country -> {focus (world-atlas country name), scale (mercator zoom)}
# for the dossier locator map. world-atlas (countries-110m.json) spellings
# matter — notably the US/UK long forms. Loosely tuned locator zooms, not
# precise cartography. Lookup is normalized (stripped, case-insensitive) with
# aliases folded to a canonical key below.
_COUNTRY_MAP_META: dict[str, dict] = {
    "united states of america": {"focus": "United States of America", "scale": 680},
    "united kingdom": {"focus": "United Kingdom", "scale": 1400},
    "australia": {"focus": "Australia", "scale": 640},
    "canada": {"focus": "Canada", "scale": 420},
    "germany": {"focus": "Germany", "scale": 1200},
    "france": {"focus": "France", "scale": 1500},
    "italy": {"focus": "Italy", "scale": 1400},
    "spain": {"focus": "Spain", "scale": 1300},
    "netherlands": {"focus": "Netherlands", "scale": 2200},
    "sweden": {"focus": "Sweden", "scale": 900},
    "norway": {"focus": "Norway", "scale": 900},
    "denmark": {"focus": "Denmark", "scale": 2000},
    "japan": {"focus": "Japan", "scale": 1000},
    "new zealand": {"focus": "New Zealand", "scale": 900},
    "ireland": {"focus": "Ireland", "scale": 1800},
    "switzerland": {"focus": "Switzerland", "scale": 2600},
    "austria": {"focus": "Austria", "scale": 2000},
    "belgium": {"focus": "Belgium", "scale": 3000},
}

# Aliases -> canonical key in _COUNTRY_MAP_META.
_COUNTRY_ALIASES: dict[str, str] = {
    "usa": "united states of america",
    "us": "united states of america",
    "u.s.a.": "united states of america",
    "u.s.": "united states of america",
    "united states": "united states of america",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "england": "united kingdom",
    "scotland": "united kingdom",
    "wales": "united kingdom",
    "northern ireland": "united kingdom",
    "great britain": "united kingdom",
}


def _country_map_meta(country: str | None) -> dict | None:
    """``{"focus", "scale"}`` for *country*, or ``None`` when unrecognised.

    Normalizes case/whitespace and folds common US/UK aliases before the
    :data:`_COUNTRY_MAP_META` lookup. Unknown country -> ``None`` (the map
    still renders, centered on lat/lng, just without a host-country fill).
    """
    if not country:
        return None
    key = country.strip().lower()
    key = _COUNTRY_ALIASES.get(key, key)
    return _COUNTRY_MAP_META.get(key)


# --- Locator map (server-side pre-render) --------------------------------
# The dossier is delivered as a downloadable, self-contained HTML file, so the
# map is pre-rendered to a static inline SVG here rather than drawn client-side
# with d3 — no network fetch, no JS, and it prints reliably. The projection
# replicates ``d3.geoMercator().center([lng,lat]).scale(k).translate([w/2,h/2])``
# so the geometry lines up with the design prototypes (which used d3 directly).
_WORLD_GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__), "assets", "world_countries_110m.json"
)
_DEFAULT_MAP_SCALE = 400
_MAP_W = 300
_MAP_H = 210
# d3.geoMercator clips latitude to this value (map becomes square); clamp to it
# so near-polar geometry doesn't blow up the log-tangent.
_MERCATOR_LAT_CLAMP = 85.05112878


@functools.lru_cache(maxsize=1)
def _world_features() -> list[dict]:
    """Load the bundled world-countries GeoJSON (177 features), cached.

    Returns:
        The FeatureCollection's ``features`` list, or ``[]`` if the asset is
        missing/unreadable (the dossier then renders without a map).
    """
    try:
        with open(_WORLD_GEOJSON_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("features", [])
    except (OSError, ValueError) as exc:  # missing file or malformed JSON
        log.warning("locator map asset unavailable (%s): %s", _WORLD_GEOJSON_PATH, exc)
        return []


def _merc_y(deg: float) -> float:
    """Mercator y (in radians of projected latitude) for *deg*, pole-clamped."""
    d = max(-_MERCATOR_LAT_CLAMP, min(_MERCATOR_LAT_CLAMP, deg))
    return math.log(math.tan(math.pi / 4.0 + math.radians(d) / 2.0))


def _ring_area(ring: list) -> float:
    """Absolute shoelace area of a lng/lat ring, for size comparison only."""
    area = 0.0
    n = len(ring)
    for i in range(n):
        lo0, la0 = ring[i]
        lo1, la1 = ring[(i + 1) % n]
        area += lo0 * la1 - lo1 * la0
    return abs(area) / 2.0


def _mainland_bbox(feature: dict) -> tuple[float, float, float, float] | None:
    """lng/lat bbox of *feature*'s single largest polygon (its main landmass).

    Picking the largest-area polygon drops outlying members of a MultiPolygon
    (Alaska/Hawaii, overseas territories, small islands) so the recognizable
    mainland frames the locator instead of being shrunk to fit distant land.

    Returns:
        ``(min_lng, min_lat, max_lng, max_lat)`` or ``None`` if the geometry
        has no usable polygon.
    """
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    if gtype == "Polygon":
        polys = [geom["coordinates"]]
    elif gtype == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return None
    best_ring = None
    best_area = -1.0
    for rings in polys:
        if not rings:
            continue
        a = _ring_area(rings[0])
        if a > best_area:
            best_area, best_ring = a, rings[0]
    if not best_ring:
        return None
    los = [p[0] for p in best_ring]
    las = [p[1] for p in best_ring]
    return (min(los), min(las), max(los), max(las))


def _render_locator_svg(lat: float, lng: float, focus: str | None, scale: float,
                        width: int = _MAP_W, height: int = _MAP_H) -> str | None:
    """Pre-render a country-locator map framing the host country, as inline SVG.

    When *focus* resolves to a bundled country feature, the map auto-fits that
    country's main landmass into the viewport and drops the pin on the venue —
    so interior venues (e.g. Denver) show the recognizable country outline
    rather than a featureless fill. With no host match, it falls back to a
    venue-centered view at *scale*.

    Args:
        lat: Geocoded venue latitude (degrees).
        lng: Geocoded venue longitude (degrees).
        focus: Host country's world-atlas name, filled with the ``map-host``
            class and used to auto-fit the frame; ``None`` to draw no host
            highlight and center on the venue.
        scale: d3 Mercator scale (zoom) for the no-host fallback only.
        width: SVG viewbox width in px.
        height: SVG viewbox height in px.

    Returns:
        An ``<svg class="loc-map">`` string whose fills are driven by the
        template's CSS custom properties (so it recolors for dark/print), or
        ``None`` if the geometry asset is unavailable.
    """
    features = _world_features()
    if not features:
        return None

    half_w, half_h = width / 2.0, height / 2.0

    # Auto-fit the host country's mainland when we can identify it; otherwise
    # fall back to the venue-centered fixed-scale view.
    fit_bbox = None
    if focus is not None:
        host_feat = next(
            (f for f in features if (f.get("properties") or {}).get("name") == focus),
            None,
        )
        if host_feat is not None:
            fit_bbox = _mainland_bbox(host_feat)

    if fit_bbox is not None:
        min_lo, min_la, max_lo, max_la = fit_bbox
        # Keep the venue pin inside the frame even if it sits off the mainland.
        min_lo, max_lo = min(min_lo, lng), max(max_lo, lng)
        min_la, max_la = min(min_la, lat), max(max_la, lat)
        center_lng = (min_lo + max_lo) / 2.0
        center_lat = (min_la + max_la) / 2.0
        pad = 14.0
        span_x = math.radians(max_lo - min_lo) or 1e-6
        span_y = (_merc_y(max_la) - _merc_y(min_la)) or 1e-6
        k = max(1.0, min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y))
    else:
        center_lng, center_lat = lng, lat
        k = float(scale)

    lam_c = math.radians(center_lng)
    y_c = _merc_y(center_lat)

    def _project(lo: float, la: float) -> tuple[float, float]:
        return half_w + k * (math.radians(lo) - lam_c), half_h - k * (_merc_y(la) - y_c)

    margin = 4.0

    def _poly_path(rings: list) -> str | None:
        parts: list[str] = []
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for ring in rings:
            pts: list[str] = []
            for lo, la in ring:
                px, py = _project(lo, la)
                min_x, max_x = min(min_x, px), max(max_x, px)
                min_y, max_y = min(min_y, py), max(max_y, py)
                pts.append(f"{px:.1f},{py:.1f}")
            if pts:
                parts.append("M" + "L".join(pts) + "Z")
        if not parts:
            return None
        # Drop polygons whose bbox falls entirely outside the viewport.
        if (max_x < -margin or min_x > width + margin
                or max_y < -margin or min_y > height + margin):
            return None
        return "".join(parts)

    land: list[str] = []
    host: list[str] = []
    for feat in features:
        name = (feat.get("properties") or {}).get("name")
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        if gtype == "Polygon":
            polys = [geom["coordinates"]]
        elif gtype == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        is_host = focus is not None and name == focus
        for rings in polys:
            path_d = _poly_path(rings)
            if path_d:
                (host if is_host else land).append(path_d)

    pin_x, pin_y = _project(lng, lat)
    out = [
        f'<svg class="loc-map" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">',
        f'<rect class="map-ocean" x="0" y="0" width="{width}" height="{height}"/>',
    ]
    out += [f'<path class="map-land" d="{d}"/>' for d in land]
    # Host drawn after land so neighbours don't overpaint it; keeps map-land
    # stroke, map-host fill wins by later CSS source order.
    out += [f'<path class="map-land map-host" d="{d}"/>' for d in host]
    out += [
        f'<circle class="pin-halo" cx="{pin_x:.1f}" cy="{pin_y:.1f}" r="13"/>',
        f'<circle class="pin-dot" cx="{pin_x:.1f}" cy="{pin_y:.1f}" r="4.5"/>',
        "</svg>",
    ]
    return "".join(out)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _entries_for_date(conn: sqlite3.Connection, date_iso: str) -> list[sqlite3.Row]:
    """All ``entries`` rows whose ``date_str`` resolves to *date_iso*."""
    rows = conn.execute(
        "SELECT lb_number, date_str, location, rating, timing, source_chain, "
        "source_type, lb_category, status, taper_name FROM entries "
        "WHERE date_str IS NOT NULL AND date_str != ''"
    ).fetchall()
    return [r for r in rows if entry_date_to_iso(r["date_str"]) == date_iso]


def _distinct_event_venues(conn: sqlite3.Connection, date_iso: str) -> list[str]:
    """Distinct non-blank ``olof_events.venue`` values for this date.

    Used to detect a genuine multi-show date (the rare early/late-show case).
    ``entries.location`` is free text scraped per-recording and routinely has
    a dozen spellings of the same real venue (e.g. "Foxboro, MA" vs "Foxboro
    MA, Sullivan Stadium" vs "Foxborough, MA, U.S.A." all for one show) — far
    too noisy to use for ambiguity detection. ``olof_events.venue`` is the
    clean, normalised field, same source ``get_performances()`` trusts.
    """
    if not _table_exists(conn, "olof_events"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT venue FROM olof_events WHERE date_str = ? AND venue != ''",
        (date_iso,),
    ).fetchall()
    return sorted(r["venue"] for r in rows)


def _primary_event(conn: sqlite3.Connection, date_iso: str,
                    prefer_venue: str | None = None) -> sqlite3.Row | None:
    """The olof_events row that best represents this date's show, if any."""
    if not _table_exists(conn, "olof_events"):
        return None
    if prefer_venue:
        row = conn.execute(
            "SELECT * FROM olof_events WHERE date_str = ? AND venue = ? "
            "ORDER BY event_id LIMIT 1",
            (date_iso, prefer_venue),
        ).fetchone()
        if row is not None:
            return row
    row = conn.execute(
        f"SELECT * FROM olof_events WHERE {_CONCERT_TYPE_FILTER} AND date_str = ? "
        "ORDER BY event_id LIMIT 1",
        (date_iso,),
    ).fetchone()
    if row is not None:
        return row
    return conn.execute(
        "SELECT * FROM olof_events WHERE date_str = ? ORDER BY event_id LIMIT 1",
        (date_iso,),
    ).fetchone()


def _build_show(conn: sqlite3.Connection, date_iso: str, location: str | None,
                 event: sqlite3.Row | None, visible_lbs: list[int]) -> dict:
    show: dict = {"date_iso": date_iso}
    try:
        dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
        show["date_disp"] = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
        show["dow"] = dt.strftime("%a")
    except ValueError:
        pass

    bd = conn.execute(
        "SELECT venue FROM bobdylan_shows WHERE date_str = ?", (date_iso,)
    ).fetchone()
    dp = conn.execute(
        "SELECT venue, city FROM dylan_performances WHERE date_str = ? "
        "AND venue NOT IN ('', '?') LIMIT 1",
        (date_iso,),
    ).fetchone()
    venue = (
        (bd["venue"] if bd and bd["venue"] else None)
        or (dp["venue"] if dp else None)
        or (event["venue"] if event is not None and event["venue"] else None)
        or location
    )
    if venue:
        show["venue"] = venue
    city = (
        (dp["city"] if dp and dp["city"] else None)
        or (event["city"] if event is not None and event["city"] else None)
    )
    if city:
        show["city"] = city

    tour = None
    sf = conn.execute(
        "SELECT tour_name FROM setlistfm_shows WHERE date_str = ? AND tour_name != '' LIMIT 1",
        (date_iso,),
    ).fetchone()
    if sf:
        tour = sf["tour_name"]
    elif event is not None and event["tour_name"]:
        tour = event["tour_name"]
    if tour:
        show["tour"] = tour

    if event is not None:
        if event["event_type"]:
            show["event_type"] = event["event_type"]
        if event["concert_no_net"] is not None:
            show["net_number"] = event["concert_no_net"]
        if event["concert_no_year"] is not None:
            show["year_concert_number"] = event["concert_no_year"]

    if visible_lbs:
        placeholders = ",".join("?" * len(visible_lbs))
        title_row = conn.execute(
            f"SELECT title FROM bootleg_titles WHERE lb_number IN ({placeholders}) "
            "AND title != '' LIMIT 1",
            visible_lbs,
        ).fetchone()
        if title_row:
            show["title"] = title_row["title"]

    # Bite 2: locator-map coordinates + country/city_line. All optional — a
    # missing or column-short table just leaves the map off (spec §1: never
    # error, always degrade cleanly).
    country: str | None = None
    region: str | None = None
    if _table_exists(conn, "setlistfm_shows"):
        sf_cols = {r[1] for r in conn.execute("PRAGMA table_info(setlistfm_shows)")}
        needed = {"city_lat", "city_lon", "country", "city_state"}
        if needed <= sf_cols:
            sf_loc = conn.execute(
                "SELECT city_lat, city_lon, country, city_state FROM setlistfm_shows "
                "WHERE date_str = ? LIMIT 1",
                (date_iso,),
            ).fetchone()
            if sf_loc is not None:
                if sf_loc["city_lat"] is not None and sf_loc["city_lon"] is not None:
                    show["lat"] = sf_loc["city_lat"]
                    show["lng"] = sf_loc["city_lon"]
                if sf_loc["country"]:
                    country = sf_loc["country"]
                if sf_loc["city_state"]:
                    region = sf_loc["city_state"]

    if not country and _table_exists(conn, "dylan_performances"):
        dp_cols = {r[1] for r in conn.execute("PRAGMA table_info(dylan_performances)")}
        if "country" in dp_cols:
            dp_country = conn.execute(
                "SELECT country FROM dylan_performances WHERE date_str = ? "
                "AND country IS NOT NULL AND country != '' LIMIT 1",
                (date_iso,),
            ).fetchone()
            if dp_country:
                country = dp_country["country"]

    if not country and event is not None and event["country"]:
        country = event["country"]

    if country:
        show["country"] = country

    city_group = ", ".join(p for p in (city, region) if p)
    city_line = " · ".join(p for p in (city_group, country) if p)
    if city_line:
        show["city_line"] = city_line

    focus = None
    scale = _DEFAULT_MAP_SCALE
    if country:
        meta = _country_map_meta(country)
        if meta:
            focus = meta["focus"]
            scale = meta["scale"]
            show["map_focus"] = focus
            show["map_scale"] = scale

    if "lat" in show and "lng" in show:
        svg = _render_locator_svg(show["lat"], show["lng"], focus, scale)
        if svg:
            show["map_svg"] = svg

    return show


def _build_context(conn: sqlite3.Connection, date_iso: str, event: sqlite3.Row | None) -> dict:
    context: dict = {}
    if _table_exists(conn, "olof_chronicle"):
        chron = conn.execute(
            "SELECT entry_text FROM olof_chronicle WHERE date_str = ? AND entry_text != '' "
            "ORDER BY year, seq LIMIT 1",
            (date_iso,),
        ).fetchone()
        if chron:
            context["chronicle"] = chron["entry_text"]
    if event is not None:
        if event["bobtalk"]:
            context["bobtalk"] = event["bobtalk"]
        if event["notes"]:
            context["notes"] = event["notes"]
        if event["lineup"]:
            context["lineup"] = event["lineup"]
    return context


def _rarity_map(conn: sqlite3.Connection) -> dict[str, dict]:
    """``{song_norm: {n, first_date, last_date}}`` across the whole corpus."""
    if not _table_exists(conn, "song_performances"):
        return {}
    rows = conn.execute(
        "SELECT song_norm, COUNT(*) AS n, MIN(concert_date_iso) AS first_date, "
        "MAX(concert_date_iso) AS last_date FROM song_performances GROUP BY song_norm"
    ).fetchall()
    return {r["song_norm"]: dict(r) for r in rows}


def _song_rarity_flag(date_iso: str, stats: dict | None) -> str | None:
    if stats is None:
        return None
    if stats["n"] == 1:
        return "only"
    if stats["first_date"] == date_iso:
        return "first"
    if stats["last_date"] == date_iso:
        return "last"
    if stats["n"] <= RARE_THRESHOLD:
        return "rare"
    return None


def _build_setlist(conn: sqlite3.Connection, date_iso: str, event: sqlite3.Row | None) -> list[dict]:
    if event is None or not _table_exists(conn, "olof_songs"):
        return []
    songs = conn.execute(
        "SELECT position, song_title, credits, is_encore, annotations FROM olof_songs "
        "WHERE event_id = ? ORDER BY position",
        (event["event_id"],),
    ).fetchall()
    if not songs:
        return []

    norm_by_position: dict[int, str] = {}
    if _table_exists(conn, "song_performances"):
        for r in conn.execute(
            "SELECT position, song_norm FROM song_performances WHERE event_id = ?",
            (event["event_id"],),
        ).fetchall():
            norm_by_position[r["position"]] = r["song_norm"]

    rarity_map = _rarity_map(conn)

    setlist = []
    for s in songs:
        row: dict = {
            "position": s["position"],
            "title": s["song_title"],
            "is_encore": bool(s["is_encore"]),
        }
        if s["credits"]:
            row["credits"] = s["credits"]
        if s["annotations"]:
            row["annotations"] = s["annotations"]
        norm = norm_by_position.get(s["position"])
        stats = rarity_map.get(norm) if norm else None
        if stats is not None:
            flag = _song_rarity_flag(date_iso, stats)
            row["rarity"] = {
                "n_performances": stats["n"],
                "first_date": stats["first_date"],
                "last_date": stats["last_date"],
                "flag": flag,
            }
        setlist.append(row)
    return setlist


def _load_families(conn: sqlite3.Connection, date_iso: str, lb_numbers: list[int]) -> dict[int, dict]:
    """``{lb_number: {fam_id, fam_label, fam_conf, fam_needs_review}}``."""
    if not lb_numbers or not _table_exists(conn, "recording_families"):
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, fam_id FROM recording_families "
        f"WHERE concert_date = ? AND lb_number IN ({placeholders})",
        [date_iso, *lb_numbers],
    ).fetchall()
    if not rows:
        return {}
    fam_ids = sorted({r["fam_id"] for r in rows})
    meta_by_id: dict[str, sqlite3.Row] = {}
    if _table_exists(conn, "tapematch_family_meta"):
        fam_placeholders = ",".join("?" * len(fam_ids))
        for r in conn.execute(
            f"SELECT fam_id, label, conf, review_flag FROM tapematch_family_meta "
            f"WHERE fam_id IN ({fam_placeholders})",
            fam_ids,
        ).fetchall():
            meta_by_id[r["fam_id"]] = r
    out: dict[int, dict] = {}
    for r in rows:
        meta = meta_by_id.get(r["fam_id"])
        entry = {"fam_id": r["fam_id"]}
        if meta is not None:
            if meta["label"]:
                entry["fam_label"] = meta["label"]
            if meta["conf"] is not None:
                entry["fam_conf"] = meta["conf"]
            if meta["review_flag"]:
                entry["fam_needs_review"] = True
        out[r["lb_number"]] = entry
    return out


def _load_taper(conn: sqlite3.Connection, lb_numbers: list[int]) -> dict[int, dict]:
    if not lb_numbers or not _table_exists(conn, "taper_attributions"):
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, taper_normalised, confidence, conflict FROM taper_attributions "
        f"WHERE lb_number IN ({placeholders})",
        lb_numbers,
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        if r["conflict"]:
            continue
        out[r["lb_number"]] = {"name": r["taper_normalised"], "tier": r["confidence"]}
    return out


def _load_lineage(conn: sqlite3.Connection, lb_numbers: list[int]) -> dict[int, list[str]]:
    if not lb_numbers or not _table_exists(conn, "entry_lineage"):
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, same_as_lb, derived_from_lb, better_than_lb FROM entry_lineage "
        f"WHERE lb_number IN ({placeholders})",
        lb_numbers,
    ).fetchall()
    out: dict[int, list[str]] = {}
    for r in rows:
        notes: list[str] = []
        for lb in json.loads(r["same_as_lb"] or "[]"):
            notes.append(f"same source as LB-{lb:05d}")
        for lb in json.loads(r["derived_from_lb"] or "[]"):
            notes.append(f"derived from LB-{lb:05d}")
        for lb in json.loads(r["better_than_lb"] or "[]"):
            notes.append(f"supersedes LB-{lb:05d}")
        if notes:
            out[r["lb_number"]] = notes
    return out


def _load_picks(conn: sqlite3.Connection, date_iso: str) -> dict[int, dict]:
    if not _table_exists(conn, "show_picks"):
        return {}
    rows = conn.execute(
        "SELECT lb_number, pick_rank, pick_score, evidence_json FROM show_picks "
        "WHERE concert_date_iso = ?",
        (date_iso,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        out[r["lb_number"]] = {
            "rank": r["pick_rank"],
            "score": r["pick_score"],
            "evidence": json.loads(r["evidence_json"] or "[]"),
        }
    return out


def _load_quality(conn: sqlite3.Connection, lb_numbers: list[int]) -> dict[int, dict]:
    if not lb_numbers or not _table_exists(conn, "quality_recording_scores"):
        return {}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quality_recording_scores)")}
    if "abs_grade" not in cols:
        return {}
    has_score = "abs_score" in cols
    scan_row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_recording_scores").fetchone()
    scan_id = scan_row["m"] if scan_row else None
    if scan_id is None:
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    score_col = ", abs_score" if has_score else ""
    rows = conn.execute(
        f"SELECT lb_number, abs_grade{score_col}, verdict_text FROM quality_recording_scores "
        f"WHERE scan_id = ? AND lb_number IN ({placeholders}) "
        f"AND abs_grade IS NOT NULL AND vetoed = 0",
        [scan_id, *lb_numbers],
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        entry = {"grade": r["abs_grade"]}
        if has_score and r["abs_score"] is not None:
            entry["score"] = r["abs_score"]
        if r["verdict_text"]:
            entry["verdict"] = r["verdict_text"]
        out[r["lb_number"]] = entry
    return out


def _load_curated(conn: sqlite3.Connection, lb_numbers: list[int]) -> dict[int, list[dict]]:
    if not lb_numbers or not _table_exists(conn, "curated_lists"):
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT cl.label AS list_label, ce.note AS note, ce.lb_number AS lb_number "
        f"FROM curated_list_entries ce JOIN curated_lists cl ON cl.id = ce.list_id "
        f"WHERE ce.lb_number IN ({placeholders})",
        lb_numbers,
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        entry = {"list_label": r["list_label"]}
        if r["note"]:
            entry["note"] = r["note"]
        out.setdefault(r["lb_number"], []).append(entry)
    return out


def _load_alt_filesets(conn: sqlite3.Connection, lb_numbers: list[int]) -> dict[int, int]:
    if not lb_numbers:
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, COUNT(DISTINCT xref) AS n FROM checksums "
        f"WHERE lb_number IN ({placeholders}) AND xref > 0 GROUP BY lb_number",
        lb_numbers,
    ).fetchall()
    return {r["lb_number"]: r["n"] for r in rows if r["n"]}


def _build_sources(conn: sqlite3.Connection, date_iso: str, entries: list[sqlite3.Row],
                    channel: str) -> tuple[list[dict], bool]:
    """Returns (sources grouped by family, local_analysis: bool)."""
    lb_numbers = [e["lb_number"] for e in entries]
    visible_lbs = [
        e["lb_number"] for e in entries
        if channel == "full" or e["status"] != "private"
    ]

    families = _load_families(conn, date_iso, lb_numbers)
    taper = _load_taper(conn, visible_lbs)
    lineage = _load_lineage(conn, visible_lbs)
    picks = _load_picks(conn, date_iso)
    quality = _load_quality(conn, visible_lbs)
    curated = _load_curated(conn, visible_lbs)
    alt_filesets = _load_alt_filesets(conn, visible_lbs)

    local_analysis = False
    buckets: dict[str | None, dict] = {}
    order: list[str | None] = []
    for e in entries:
        lb = e["lb_number"]
        fam = families.get(lb)
        fam_id = fam["fam_id"] if fam else f"__singleton_{lb}"
        if fam_id not in buckets:
            bucket: dict = {"members": []}
            if fam:
                bucket["fam_id"] = fam["fam_id"]
                if "fam_label" in fam:
                    bucket["fam_label"] = fam["fam_label"]
                if "fam_conf" in fam:
                    bucket["fam_conf"] = fam["fam_conf"]
                if "fam_needs_review" in fam:
                    bucket["fam_needs_review"] = True
            buckets[fam_id] = bucket
            order.append(fam_id)

        if e["status"] == "private" and channel != "full":
            member = {"lb": f"LB-{lb:05d}", "private": True}
        else:
            member = {"lb": f"LB-{lb:05d}", "url": detail_url(lb)}
            if e["rating"]:
                member["rating"] = e["rating"]
            if e["timing"]:
                member["timing"] = e["timing"]
            if e["source_type"]:
                member["source_type"] = e["source_type"]
            if lb in taper:
                member["taper"] = taper[lb]
                local_analysis = True
            if e["source_chain"]:
                member["source_chain"] = e["source_chain"]
            if lb in lineage:
                member["lineage_notes"] = lineage[lb]
            if lb in picks:
                member["pick"] = picks[lb]
                local_analysis = True
            if lb in quality:
                member["quality"] = quality[lb]
                local_analysis = True
            if lb in curated:
                member["curated"] = curated[lb]
                local_analysis = True
            if lb in alt_filesets:
                member["alt_filesets"] = alt_filesets[lb]
        buckets[fam_id]["members"].append(member)

    sources = []
    named = [buckets[k] for k in order if not k.startswith("__singleton_")]
    named.sort(key=lambda b: b.get("fam_label", ""))
    singles = [buckets[k] for k in order if k.startswith("__singleton_")]
    singles.sort(key=lambda b: b["members"][0]["lb"])
    sources = named + singles
    for bucket in sources:
        bucket["members"].sort(key=lambda m: m["lb"])

    return sources, local_analysis


# Olof's Files are scraped from the bobserve mirror (olof_fetcher.BASE_URL) —
# deep links go there so they always resolve to the exact page we ingested.
_OLOF_MIRROR_BASE = "https://www.bobserve.com/olof/"
_OLOF_HOME = "http://www.bjorner.com/still.htm"
_BOBLINKS_HOME = "https://boblinks.com"
_BOBSERVE_HOME = "https://bobserve.com"
# Boblinks per-show pages (MMDDYYs.html) only exist from 1995 on.
_BOBLINKS_FIRST_YEAR = 1995


def _build_xref(date_iso: str, event: sqlite3.Row | None,
                lb_number: int | None) -> list[dict]:
    """Cross-reference cards with working deep links for one date.

    Every card carries both ``site`` (the source's home page, used for
    attribution links) and ``url`` (the deepest link we can build for this
    show that is guaranteed to resolve: the LB detail page, the exact Olof
    page the context/setlist were ingested from, the Boblinks per-date page
    when one can exist, and the Bobserve year index).

    Args:
        date_iso: Concert date, ``'YYYY-MM-DD'``.
        event: The primary ``olof_events`` row for the date, if any.
        lb_number: LB number to deep-link on the LosslessBob card
            (recommendation first, else first visible source).

    Returns:
        List of ``{key, name, desc, site, url, link_label}`` dicts.
    """
    try:
        dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        dt = None
    year = f"{dt.year}" if dt else None

    lbb = {
        "key": "losslessbob",
        "name": "LosslessBob",
        "desc": "Lossless recording catalog — the LB-number source for "
                "transfers, lineage & ratings.",
        "site": SITE_BASE_URL,
        "url": SITE_BASE_URL,
        "link_label": "catalog home",
    }
    if lb_number is not None:
        lbb["url"] = detail_url(lb_number)
        lbb["link_label"] = f"LB-{lb_number:05d} detail page"

    olof = {
        "key": "olof",
        "name": "Olof's Files · Still on the Road",
        "desc": "Olof Björner's chronicle — dates, personnel, bobtalk and "
                "song-by-song session notes.",
        "site": _OLOF_HOME,
        "url": _OLOF_HOME,
        "link_label": "chronicle index",
    }
    if event is not None and event["page_filename"]:
        olof["url"] = _OLOF_MIRROR_BASE + urllib.parse.quote(event["page_filename"])
        olof["link_label"] = event["page_filename"]

    boblinks = {
        "key": "boblinks",
        "name": "Bob Links",
        "desc": "Fan-contributed setlists, concert reviews and venue notes "
                "by date.",
        "site": _BOBLINKS_HOME,
        "url": _BOBLINKS_HOME,
        "link_label": "site home",
    }
    if dt and dt.year >= _BOBLINKS_FIRST_YEAR:
        boblinks["url"] = f"{_BOBLINKS_HOME}/{dt.strftime('%m%d%y')}s.html"
        boblinks["link_label"] = f"setlist page · {date_iso}"

    bobserve = {
        "key": "bobserve",
        "name": "Bobserve",
        "desc": "Setlist observations and performance statistics across the "
                "touring history.",
        "site": _BOBSERVE_HOME,
        "url": _BOBSERVE_HOME,
        "link_label": "site home",
    }
    if year:
        bobserve["url"] = f"{_BOBSERVE_HOME}/eventsperiod?period={year}"
        bobserve["link_label"] = f"events · {year}"

    return [lbb, olof, boblinks, bobserve]


def build_dossier(date_iso: str, location: str | None = None, channel: str = "public",
                   db_path: str | None = None) -> dict:
    """Assemble the show dossier for one date.

    Args:
        date_iso: Concert date, ``'YYYY-MM-DD'``.
        location: Disambiguates a date with more than one distinct
            ``olof_events.venue`` (a genuine two-show date). Required when
            ambiguous.
        channel: ``'public'`` (default, private-entry metadata stripped) or
            ``'full'``.
        db_path: Optional database path override.

    Returns:
        The D1 JSON shape (plus an additive ``xref`` list of external
        deep-link cards, see :func:`_build_xref`), or
        ``{"ambiguous": True, "date_iso", "candidates"}`` when *location*
        is required but not given.
    """
    if channel not in ("public", "full"):
        channel = "public"
    conn = get_connection(db_path)

    venues = _distinct_event_venues(conn, date_iso)
    if location is None and len(venues) > 1:
        return {
            "ambiguous": True,
            "date_iso": date_iso,
            "candidates": [{"date_iso": date_iso, "location": v} for v in venues],
        }

    entries = _entries_for_date(conn, date_iso)
    event = _primary_event(conn, date_iso, prefer_venue=location)
    visible_lbs = [
        e["lb_number"] for e in entries if channel == "full" or e["status"] != "private"
    ]

    dossier: dict = {"show": _build_show(conn, date_iso, location, event, visible_lbs)}

    context = _build_context(conn, date_iso, event)
    if context:
        dossier["context"] = context

    setlist = _build_setlist(conn, date_iso, event)
    if setlist:
        dossier["setlist"] = setlist

    sources, local_analysis = _build_sources(conn, date_iso, entries, channel)
    if sources:
        dossier["sources"] = sources

    picks = _load_picks(conn, date_iso)
    rank1_lb = next((lb for lb, p in picks.items() if p["rank"] == 1), None)
    if rank1_lb is not None and rank1_lb in visible_lbs:
        dossier["recommendation"] = {"lb": f"LB-{rank1_lb:05d}", "evidence": picks[rank1_lb]["evidence"]}

    xref_lb = rank1_lb if rank1_lb is not None and rank1_lb in visible_lbs else (
        visible_lbs[0] if visible_lbs else None)
    dossier["xref"] = _build_xref(date_iso, event, xref_lb)

    provenance: dict = {"generated_at": _now_iso(), "channel": channel, "local_analysis": local_analysis}
    mv = conn.execute("SELECT value FROM meta WHERE key = 'master_version'").fetchone()
    if mv and mv["value"]:
        provenance["master_version"] = mv["value"]
    dossier["provenance"] = provenance

    return dossier


def filter_dossier_sections(dossier: dict, sections: set[str] | None = None,
                             local_analysis: bool = True) -> dict:
    """Presentation-layer view of a built dossier for the HTML/BBcode renderers (D4).

    Never mutates *dossier* — the JSON route always returns the full D1 shape;
    this is only applied to the served document, so it can't drift the API
    contract. ``provenance.local_analysis`` is left untouched: it reports
    whether the underlying data *has* local analysis, independent of whether
    this view is choosing to display it.

    Args:
        dossier: A dict returned by :func:`build_dossier` (non-ambiguous).
        sections: If given, keep ``context``/``setlist`` only when their key
            is in this set (both default to shown when *sections* is None).
        local_analysis: When False, strips pick/quality/curated verdicts and
            family confidence/review flags — and the ``recommendation``
            section — from the view, leaving only outward-facing facts.

    Returns:
        A new dict, safe for the template to render directly.
    """
    view = dict(dossier)
    if sections is not None:
        if "context" not in sections:
            view.pop("context", None)
        if "setlist" not in sections:
            view.pop("setlist", None)

    if not local_analysis:
        view.pop("recommendation", None)
        if "sources" in view:
            new_sources = []
            for bucket in view["sources"]:
                new_bucket = {k: v for k, v in bucket.items() if k not in ("fam_conf", "fam_needs_review")}
                new_bucket["members"] = [
                    {k: v for k, v in m.items() if k not in ("pick", "quality", "curated")}
                    for m in bucket["members"]
                ]
                new_sources.append(new_bucket)
            view["sources"] = new_sources

    return view


_RARITY_LABEL: dict[str, str] = {
    "only": "only performance",
    "first": "live debut",
    "last": "last performance",
}


def _rarity_bbcode_mark(rarity: dict | None) -> str:
    if not rarity or not rarity.get("flag"):
        return ""
    flag = rarity["flag"]
    if flag == "rare":
        return f" [i](rare, {rarity['n_performances']}x)[/i]"
    label = _RARITY_LABEL.get(flag)
    return f" [i]({label})[/i]" if label else ""


def render_bbcode(view: dict) -> str:
    """Compact BBcode digest of a (filtered) dossier view for forum posts (spec D5).

    Text-only sibling of ``dossier.html`` — both render from the same
    :func:`build_dossier` / :func:`filter_dossier_sections` output so the
    two can never disagree.

    Args:
        view: A dict from :func:`build_dossier` (non-ambiguous), optionally
            passed through :func:`filter_dossier_sections` first.

    Returns:
        A BBcode string.
    """
    show = view["show"]
    lines: list[str] = []

    title = show.get("title") or show.get("venue") or show.get("date_disp") or show["date_iso"]
    lines.append(f"[b]{title}[/b]")
    meta_bits = [show.get("date_disp", show["date_iso"])]
    if show.get("venue"):
        meta_bits.append(show["venue"])
    if show.get("city"):
        meta_bits.append(show["city"])
    if show.get("tour"):
        meta_bits.append(show["tour"])
    lines.append(" — ".join(meta_bits))

    if view.get("setlist"):
        lines.append("")
        lines.append("[b]Setlist[/b]")
        lines.append("[list=1]")
        for song in view["setlist"]:
            mark = _rarity_bbcode_mark(song.get("rarity"))
            encore = " (encore)" if song.get("is_encore") else ""
            lines.append(f"[*]{song['title']}{encore}{mark}")
        lines.append("[/list]")

    if view.get("sources"):
        lines.append("")
        lines.append("[b]Sources[/b]")
        for bucket in view["sources"]:
            if bucket.get("fam_label"):
                lines.append(f"[u]{bucket['fam_label']}[/u]")
            for m in bucket["members"]:
                if m.get("private"):
                    lines.append(f"{m['lb']} — private entry")
                    continue
                bits = [m["lb"]]
                if m.get("source_type"):
                    bits.append(m["source_type"])
                if m.get("rating"):
                    bits.append(f"rating {m['rating']}")
                if m.get("taper"):
                    bits.append(f"taper: {m['taper']['name']}")
                if m.get("pick"):
                    bits.append(f"pick #{m['pick']['rank']}")
                if m.get("quality"):
                    bits.append(f"AI grade {m['quality']['grade']}")
                lines.append(" — ".join(bits))

    if view.get("recommendation"):
        lines.append("")
        lines.append(f"[b]Recommended:[/b] {view['recommendation']['lb']}")

    lines.append("")
    lines.append(f"[i]Generated by LosslessBob{' · local analysis included' if view['provenance'].get('local_analysis') else ''}[/i]")

    return "\n".join(lines)
