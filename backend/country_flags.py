"""Country flag emoji for a show's location, for forum post subject lines.

WatchingTheRiverFlow (SMF 2.0, UTF-8) renders four-byte emoji in topic titles
unchanged, and the board's convention — set by other posters — is a single flag
prefixed to the subject: ``🇺🇸 Rochester, MI 1987-07-18``. This module resolves
an LB entry to that flag.

The location vocabulary is Olof Björner's, not ISO: ``olof_events.country``
holds names like "England", "West Germany" and "Yugoslavia", and its ``region``
column is a mixed bag — mostly US states, but the page parser also filed whole
countries ("The Netherlands"), Canadian provinces and typos ("Irelandw") there.
Both columns are therefore mapped by name through :data:`_NAME_TO_CODE`, which
is exhaustive over the values actually present in the corpus. Anything that
does not resolve unambiguously returns None: a subject with no flag is right,
a subject with the wrong flag is not.

A date Olof has no event for falls back to the entry's free-text ``location``
via :func:`flag_for_location` — the 1975 Rolling Thunder gap (New Haven
1975-11-13 and friends) is real and left US shows unflagged.

The UK nations get their subdivision flags (🏴󠁧󠁢󠁳󠁣󠁴󠁿 and friends) rather than
🇬🇧, matching the board's existing usage.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Subdivision-flag tag sequences: BASE + tag letters + CANCEL TAG.
_TAG_BASE = "\U0001f3f4"
_TAG_CANCEL = "\U000e007f"

#: Names that map to a subdivision flag rather than a two-letter country.
_SUBDIVISION = {
    "england": "gbeng",
    "scotland": "gbsct",
    "wales": "gbwls",
}

#: Every ``country``/``region`` value present in olof_events, lowercased, mapped
#: to an ISO 3166-1 alpha-2 code. Values that cannot be resolved to exactly one
#: country are deliberately absent (see module docstring).
_NAME_TO_CODE: dict[str, str] = {
    # ── Countries as Olof spells them ────────────────────────────────────────
    "argentina": "AR", "australia": "AU", "austria": "AT", "belgium": "BE",
    "brazil": "BR", "bulgaria": "BG", "canada": "CA", "chile": "CL",
    "china": "CN", "costa rica": "CR", "croatia": "HR", "czech republic": "CZ",
    "czechia": "CZ", "denmark": "DK", "estonia": "EE", "finland": "FI",
    "france": "FR", "germany": "DE", "greece": "GR", "hong kong": "HK",
    "hungary": "HU", "iceland": "IS", "ireland": "IE", "israel": "IL",
    "italy": "IT", "japan": "JP", "lithuania": "LT", "luxembourg": "LU",
    "macedonia": "MK", "malaysia": "MY", "mexico": "MX", "netherlands": "NL",
    "new zealand": "NZ", "northern ireland": "GB", "norway": "NO",
    "poland": "PL", "portugal": "PT", "romania": "RO", "russia": "RU",
    "serbia": "RS", "singapore": "SG", "slovakia": "SK", "slovenia": "SI",
    "south korea": "KR", "spain": "ES", "sweden": "SE", "switzerland": "CH",
    "taiwan": "TW", "turkey": "TR", "uruguay": "UY", "vietnam": "VN",
    "united states": "US", "united kingdom": "GB", "andorra": "AD",
    # Historical states whose successor is unambiguous. Yugoslavia, the USSR
    # and Czechoslovakia are not here on purpose — they have no single one.
    "east germany": "DE", "west germany": "DE",
    # Olof's own spelling variants and parser typos.
    "holland": "NL", "the netherlands": "NL", "irelandw": "IE",
    "republic of singapore": "SG", "slovak republic": "SK",
    "isle of wight": "GB",
    # Spellings that only ever turn up in free-text entry locations.
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "uk": "GB", "u.k.": "GB",
    # ── US states and DC ─────────────────────────────────────────────────────
    **{s: "US" for s in (
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
        "connecticut", "d. c.", "delaware", "district of columbia", "florida",
        "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
        "kentucky", "louisiana", "maine", "maryland", "massachusetts",
        "michigan", "minnesota", "mississippi", "missouri", "montana",
        "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
        "new york", "north carolina", "north dakota", "ohio", "oklahoma",
        "oregon", "pennsylvania", "rhode island", "south carolina",
        "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
        "washington", "west virginia", "wisconsin", "wyoming",
    )},
    # ── Canadian provinces ───────────────────────────────────────────────────
    **{s: "CA" for s in (
        "alberta", "british columbia", "manitoba", "new brunswick",
        "newfoundland", "nova scotia", "ontario", "quebec", "saskatchewan",
    )},
    # ── Australian states ────────────────────────────────────────────────────
    **{s: "AU" for s in (
        "australian capitol territory", "new south wales", "northern territory",
        "queensland", "south australia", "tasmania", "victoria",
        "west australia", "west australia. australia", "western australia",
    )},
    # ── Other sub-national values the parser filed as regions ────────────────
    "niigata": "JP", "skåne": "SE", "skane": "SE",
}

#: Values that appear in the data but resolve to no single country. Listed so a
#: reader can see they were considered rather than missed.
_UNRESOLVABLE = frozenset({
    "yugoslavia", "unknown state/province", "wood", "australia/los angeles",
})


def flag_for_name(name: str | None) -> str | None:
    """Flag emoji for a country or region name, or None if it doesn't resolve.

    Args:
        name: A value from ``olof_events.country``/``region`` or an equivalent
            free-text country name. Case and surrounding space are ignored.

    Returns:
        The flag emoji, or None when the name is empty, unknown, or names a
        state with no single successor (e.g. "Yugoslavia").
    """
    key = (name or "").strip().lower()
    if not key or key in _UNRESOLVABLE:
        return None
    tag = _SUBDIVISION.get(key)
    if tag:
        return _TAG_BASE + "".join(chr(0xE0000 + ord(c)) for c in tag) + _TAG_CANCEL
    code = _NAME_TO_CODE.get(key)
    if not code:
        return None
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def flag_for_date(date_str: str | None) -> str | None:
    """Flag emoji for the show on *date_str*, or None.

    Resolves against ``olof_events`` — its ``country`` first, then its
    ``region``, which for a US show is the only column carrying the location.
    A date with several events (an afternoon and an evening show) is one place,
    so the first row settles it.

    Args:
        date_str: The entry's date in the ``entries`` table's format (``m/d/yy``)
            or already ISO. Anything unparseable yields None.

    Returns:
        The flag emoji, or None when the date is unknown, has no Olof event, or
        the event's location does not resolve.
    """
    from backend.torrent_maker import _parse_date

    raw = (date_str or "").strip()
    if not raw:
        return None
    iso = raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else _parse_date(raw)
    if not iso:
        return None

    from backend import db

    try:
        with db.get_connection() as conn:
            rows = conn.execute(
                "SELECT country, region FROM olof_events WHERE date_str=?", (iso,)
            ).fetchall()
    except Exception:
        logger.exception("Could not read olof_events for %s", iso)
        return None

    for row in rows:
        flag = flag_for_name(row["country"]) or flag_for_name(row["region"])
        if flag:
            return flag
    return None


#: Separators that split a free-text location into candidate place names.
_LOCATION_SPLIT = re.compile(r"[,;()\[\]]")


def flag_for_location(location: str | None) -> str | None:
    """Flag emoji for a free-text ``entries.location`` string, or None.

    The fallback for a date Olof's corpus does not cover. ``location`` is
    user-entered and unstructured ("New Haven, Connecticut, Veterans Memorial
    Coliseum", "Columbia Studio A. Nashville, Tennessee, USA"), so it is split
    on commas, semicolons and brackets and every part is looked up in the same
    name table :func:`flag_for_name` uses. Two-letter abbreviations are
    deliberately not recognised: "DE" is Delaware or Germany, and a wrong flag
    is worse than none.

    Returns:
        The flag emoji when exactly one country is named, or None when nothing
        resolves or the parts disagree (a city that shares a country's name,
        say — "Mexico, Missouri" names two, so it names neither).
    """
    raw = (location or "").strip()
    if not raw:
        return None
    found: set[str] = set()
    for part in _LOCATION_SPLIT.split(raw):
        flag = flag_for_name(part.strip().strip("."))
        if flag:
            found.add(flag)
    if len(found) != 1:
        if found:
            logger.debug("Location %r names %d countries; no flag", raw, len(found))
        return None
    return found.pop()
