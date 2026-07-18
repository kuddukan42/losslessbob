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
import json
import logging
import sqlite3

from backend.db import get_connection
from backend.geocoder import entry_date_to_iso

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
    scan_row = conn.execute("SELECT MAX(scan_id) AS m FROM quality_recording_scores").fetchone()
    scan_id = scan_row["m"] if scan_row else None
    if scan_id is None:
        return {}
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, abs_grade, verdict_text FROM quality_recording_scores "
        f"WHERE scan_id = ? AND lb_number IN ({placeholders}) "
        f"AND abs_grade IS NOT NULL AND vetoed = 0",
        [scan_id, *lb_numbers],
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        entry = {"grade": r["abs_grade"]}
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
            member = {"lb": f"LB-{lb:05d}"}
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
        The D1 JSON shape, or ``{"ambiguous": True, "date_iso", "candidates"}``
        when *location* is required but not given.
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
