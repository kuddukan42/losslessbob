"""Compose and post a recording to TUIT's ``/upload`` form.

TUIT (tangledupintorrents.org) has no upload API. ``/upload`` is a plain
Laravel multipart form behind a CSRF ``_token``, and the only server-side
assist in the whole wizard is ``GET /api/shows/search?q=`` which resolves a
``show_id``. Nothing is autofilled from the LB number — the field's own help
text says "The desktop uploader detects it automatically", i.e. the client is
expected to supply every value. That is what this module does: it reads the
recording out of ``entries``/``my_collection``, probes the folder for format,
bit depth and sample rate, picks up the ``.ffp`` and info sidecars, and maps
all of it onto the form's fixed vocabularies.

Nothing here posts on its own. :func:`prepare_upload` composes and returns the
payload — the dry run, and the only thing the CLI does by default — while
:func:`post_upload` is the single function that talks to the tracker. Three
gates stand before a POST: ``db.is_seedable_to_tracker`` (lb_status must be
'public'), a duplicate check against the scraped ``tuit_recordings``, and
``torrent_verify`` hashing the folder locally.

Seeding after a successful upload is delegated to
:func:`backend.tracker_seed.seed_torrent`, which already owns the overlay and
qBittorrent halves of the job.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import requests

from backend import db as database
from backend import taper_curation, torrent_maker, tracker_seed, tuit_scraper

logger = logging.getLogger(__name__)

UPLOAD_PATH = "/upload"
SHOWS_SEARCH_PATH = "/api/shows/search"

#: Where ``tools/tuit_sync.py --fetch-torrents`` saves personalised torrents.
#: Any one of them carries this account's announce URL, which is what a new
#: upload must announce to.
TORRENT_DIR = Path(__file__).resolve().parent.parent / "data" / "downloads" / "tuit"

#: ``meta`` key caching the announce URL once it has been read off a torrent.
ANNOUNCE_META_KEY = "tuit_announce_url"

#: The torrent ``source`` field TUIT's own torrents carry.
SOURCE_TAG = "TUIT"

#: Server cap on the info file, from the form's help text.
MAX_INFO_BYTES = 256 * 1024

AUDIO_EXTS = {".flac", ".shn", ".wav", ".aiff", ".aif", ".ape"}

#: Formats that cannot be the source of a lossless upload.
LOSSY_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wma"}

#: ``entries.lb_category`` values worth a word before the upload goes out. The
#: desktop uploader flags the same two shapes (comp_warn, studio_warn): both
#: upload fine, but neither is the live show the show_id says it is.
CATEGORY_WARNINGS = {
    "compilation": "entries calls this a compilation — it may span several shows",
    "studio": "entries calls this studio material, not a live recording",
}

#: ffmpeg sample formats → PCM bit depth. The trailing 'p' is planar layout,
#: not a different width. This is the *last* resort of :func:`_depth_from_probe`
#: because ffmpeg decodes 24-bit FLAC into an s32 buffer — sample_fmt describes
#: the decoded buffer, while bits_per_raw_sample describes the file.
SAMPLE_FMT_DEPTH = {
    "u8": 8, "u8p": 8,
    "s16": 16, "s16p": 16,
    "s32": 32, "s32p": 32,
    "flt": 32, "fltp": 32,
    "dbl": 64, "dblp": 64,
}
INFO_EXTS = (".txt", ".nfo", ".log")

# ── The form's fixed vocabularies ────────────────────────────────────────────
# Every select on /upload is closed. A value outside these sets is silently
# dropped by Laravel's validator, so mapping happens here and anything that
# will not map is reported as a warning rather than guessed at.

SOURCE_TYPES = ("audience", "soundboard", "matrix", "radio", "tv", "ald")
FORMATS = ("flac", "shn")
QUALITIES = ("excellent", "very-good", "good", "fair", "poor")
BIT_DEPTHS = (16, 24, 32)
SAMPLE_RATES = (44100, 48000, 88200, 96000)

#: ``entries.source_type`` → the form's ``source_type``. The left-hand side is
#: the full observed vocabulary of the column (6 values over 16,703 entries).
SOURCE_TYPE_MAP = {
    "audience": "audience",
    "aud": "audience",
    "soundboard": "soundboard",
    "sbd": "soundboard",
    "ald": "ald",
    "fm": "radio",
    "fm/pre-fm": "radio",
    "pre-fm": "radio",
    "mixed": "matrix",
    "matrix": "matrix",
    "mtx": "matrix",
    "tv": "tv",
    # Phrase forms, taken from the official desktop uploader's own
    # normalisation table. entries.source_type does not hold these today, but
    # a --set override or a hand-edited row can, and they cost nothing here.
    "audience recording": "audience",
    "audience master": "audience",
    "soundboard recording": "soundboard",
    "soundboard master": "soundboard",
    "matrix recording": "matrix",
}

#: Free-text quality tokens → the form's ``audio_quality``, used only when
#: ``entries.rating`` is blank (2,838 entries) and a grade has to come out of
#: prose instead. The vocabulary is the desktop uploader's, which is the best
#: evidence available of what the tracker's own curators write. 'off master'
#: and 'low gen' are deliberately absent: they describe a tape's generation,
#: not how it sounds, and mapping them to a grade would be inventing one.
QUALITY_TOKENS = {
    "excellent": "excellent", "exc": "excellent", "ex+": "excellent",
    "ex": "excellent",
    "very good": "very-good", "very-good": "very-good", "vg+": "very-good",
    "vg": "very-good",
    "good": "good",
    "fair": "fair",
    "poor": "poor",
}

#: Extra "nobody knows who taped this" values, lifted from the official
#: desktop uploader's own normalisation table. ``taper_curation`` already owns
#: the repo's placeholder vocabulary and is consulted first; these are the ones
#: it does not carry yet. They stay local to the outbound path on purpose —
#: folding 'anonymous', 'various', 'me' and friends into
#: ``taper_curation._PLACEHOLDER_TAPERS`` is very likely right, but it would
#: move badge trust and the TODO-213 curation counts, which is a decision for
#: that subsystem rather than a side effect of building an uploader.
EXTRA_PLACEHOLDER_TAPERS = frozenset({
    "not certain", "not known", "unknow", "identity withheld",
    "identity unknown", "anonymous", "anon", "no info", "no information",
    "no idea", "various", "me", "myself", "self",
})

#: Longest an unrecognised taper value may be, in words, before it is read as
#: info-file prose rather than a handle. Three-part human names ('Clay C.
#: Brennecke') are the longest real handles in entries, so three is the cut.
MAX_TAPER_WORDS = 3

#: ``entries.rating`` → the form's ``audio_quality``. LB grades on A+…D-, TUIT
#: on five slugs; this is the collapse tj's existing TUIT uploads imply.
QUALITY_MAP = {
    "a+": "excellent", "a": "excellent",
    "a-": "very-good", "b+": "very-good",
    "b": "good", "b-": "good",
    "c+": "fair", "c": "fair", "c-": "fair",
    "d+": "poor", "d": "poor", "d-": "poor", "f": "poor",
}


@dataclass
class UploadPayload:
    """A composed but unsent ``/upload`` submission.

    Attributes:
        lb_number: LB number being posted.
        fields: Form fields, ready to hand to ``requests`` as ``data``.
        info_path: Info/README file to attach as ``info_file``, if one was
            found in the folder.
        torrent_path: Generated ``.torrent``; empty on a payload-only run.
        info_hash: Infohash of that torrent.
        source_folder: Folder the torrent covers.
        show: The ``/api/shows/search`` row the upload attaches to, if matched.
        warnings: Human-readable notes about anything left blank or guessed.
        upload_id: ``tuit_uploads`` row this payload was recorded as, so a
            later POST advances the same attempt instead of filing a new one.
    """

    lb_number: int
    fields: dict
    info_path: Path | None = None
    torrent_path: str = ""
    info_hash: str = ""
    source_folder: str = ""
    show: dict | None = None
    warnings: list[str] = field(default_factory=list)
    upload_id: int | None = None

    def as_dict(self) -> dict:
        """Return a JSON-serialisable view, for logging and the CLI."""
        return {
            "lb_number": self.lb_number,
            "fields": dict(self.fields),
            "info_file": str(self.info_path) if self.info_path else "",
            "torrent_path": self.torrent_path,
            "info_hash": self.info_hash,
            "source_folder": self.source_folder,
            "show": self.show,
            "warnings": list(self.warnings),
        }


# ── Announce URL ─────────────────────────────────────────────────────────────


def announce_url(db_path=None) -> str:
    """Return this account's TUIT announce URL.

    Read from the ``meta`` table when cached, otherwise lifted off any
    ``.torrent`` previously fetched from the tracker — every one of them is
    personalised with the same passkey — and cached for next time.

    Args:
        db_path: Optional DB path override.

    Returns:
        The announce URL, or "" when no TUIT torrent has been fetched yet.
    """
    cached = database.get_meta(ANNOUNCE_META_KEY)
    if cached:
        return cached

    try:
        from torf import Torrent
    except ImportError:
        logger.warning("torf is not installed; cannot read an announce URL")
        return ""

    for path in sorted(TORRENT_DIR.glob("*.torrent")):
        try:
            t = Torrent.read(str(path))
        except Exception:  # noqa: BLE001 - a corrupt torrent is not fatal here
            continue
        urls = [u for tier in (t.trackers or []) for u in tier]
        if urls:
            database.set_meta(ANNOUNCE_META_KEY, urls[0])
            logger.info("TUIT announce URL read from %s", path.name)
            return urls[0]

    logger.warning(
        "No TUIT announce URL: run tools/tuit_sync.py --fetch-torrents once, "
        "or set the '%s' meta key by hand", ANNOUNCE_META_KEY,
    )
    return ""


# ── Folder inspection ────────────────────────────────────────────────────────


def _depth_from_probe(stream: dict) -> int | None:
    """Read a PCM bit depth out of one ffprobe audio stream.

    Three fields can carry it and they disagree by design, so they are tried
    in order of how closely each describes the file rather than the decoder's
    output buffer:

    1. ``bits_per_raw_sample`` — what the encoder was given. A 24-bit FLAC says
       24 here while decoding into a 32-bit buffer.
    2. ``bits_per_sample`` — set for uncompressed PCM, and 0 for every codec
       that has to be decoded, which is why the zero must be rejected rather
       than treated as a reading.
    3. ``sample_fmt`` — always present. It is how a shorten stream's 16 bits
       are recovered, since shn populates neither of the first two.

    Args:
        stream: One entry from ffprobe's ``streams`` array.

    Returns:
        The bit depth, or None when the stream describes none.
    """
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        raw = stream.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return SAMPLE_FMT_DEPTH.get(str(stream.get("sample_fmt") or "").lower())


def probe_audio(folder: str | Path, sample_size: int = 5) -> dict:
    """Probe a folder's audio files for format, bit depth and sample rate.

    Samples the first few audio files rather than the whole folder — a
    recording is one transfer and does not change format mid-set. ``mixed``
    flags the case where it does anyway, which is a curator's problem, not
    something to average away.

    Args:
        folder: Recording folder to probe.
        sample_size: How many audio files to read.

    Returns:
        Dict with ``format`` ('flac'/'shn'/…), ``bit_depth``, ``sample_rate``
        (Hz), ``mixed`` (bool) and ``files_probed``. Values are None when
        nothing could be read.
    """
    empty = {"format": None, "bit_depth": None, "sample_rate": None,
             "mixed": False, "files_probed": 0}
    root = Path(folder)
    if not root.is_dir():
        return empty

    audio = [
        Path(dirpath) / name
        for dirpath, _, names in os.walk(root)
        for name in names
        if Path(name).suffix.lower() in AUDIO_EXTS
    ]
    if not audio:
        return empty

    results = []
    for path in sorted(audio)[:sample_size]:
        fmt = bits = rate = None
        try:
            import soundfile as sf

            info = sf.info(str(path))
            fmt = info.format.lower()
            rate = info.samplerate
            subtype = (info.subtype or "").upper()
            for depth in BIT_DEPTHS:
                if f"PCM_{depth}" in subtype:
                    bits = depth
                    break
            if bits is None and ("FLOAT" in subtype or "DOUBLE" in subtype):
                bits = 32
        except Exception:  # noqa: BLE001 - shn and friends need ffprobe
            try:
                out = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_streams", "-select_streams", "a:0", str(path)],
                    capture_output=True, text=True, timeout=15, check=False,
                )
                streams = json.loads(out.stdout or "{}").get("streams", [])
                if streams:
                    stream = streams[0]
                    fmt = path.suffix.lstrip(".").lower()
                    rate = int(stream.get("sample_rate") or 0) or None
                    bits = _depth_from_probe(stream)
            except Exception:  # noqa: BLE001
                pass
        if fmt:
            results.append({"format": fmt, "bit_depth": bits, "sample_rate": rate})

    if not results:
        # Nothing decoded, but the extensions still say what the format is.
        exts = {p.suffix.lstrip(".").lower() for p in audio}
        return {**empty, "format": sorted(exts)[0] if len(exts) == 1 else None,
                "files_probed": min(len(audio), sample_size)}

    fmts = {r["format"] for r in results if r["format"]}
    depths = {r["bit_depth"] for r in results if r["bit_depth"]}
    rates = {r["sample_rate"] for r in results if r["sample_rate"]}
    return {
        "format": sorted(fmts)[0] if fmts else None,
        "bit_depth": sorted(depths)[0] if depths else None,
        "sample_rate": sorted(rates)[0] if rates else None,
        "mixed": len(fmts) > 1 or len(depths) > 1 or len(rates) > 1,
        "files_probed": len(results),
    }


def read_ffp(folder: str | Path) -> str:
    """Return the folder's FFP text, for the form's ``ffp`` textarea.

    Args:
        folder: Recording folder to search (one level deep plus subfolders).

    Returns:
        The contents of the first ``.ffp`` file found, or "".
    """
    root = Path(folder)
    if not root.is_dir():
        return ""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".ffp":
            try:
                return path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return ""
    return ""


def find_info_file(folder: str | Path) -> Path | None:
    """Pick the info/README file to attach as ``info_file``.

    TUIT reads the uploaded text in and it overrides the description textarea,
    so the best candidate is the largest plain-text file under the cap that is
    not a checksum listing.

    Args:
        folder: Recording folder to search.

    Returns:
        Path to the chosen file, or None when the folder has no usable one.
    """
    root = Path(folder)
    if not root.is_dir():
        return None
    candidates = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in INFO_EXTS:
            continue
        low = path.name.lower()
        if low.endswith((".md5.txt", ".ffp.txt", ".st5.txt")):
            continue
        if re.search(r"\b(md5|ffp|st5|shntool)\b", low):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if 0 < size <= MAX_INFO_BYTES:
            candidates.append((size, path))
    if not candidates:
        return None
    return max(candidates)[1]


# ── Show resolution ──────────────────────────────────────────────────────────


def find_show(session: requests.Session, date_iso: str, venue: str = "") -> dict | None:
    """Resolve a ``show_id`` through the tracker's own search endpoint.

    Args:
        session: Authenticated TUIT session.
        date_iso: Show date as ``YYYY-MM-DD``.
        venue: Venue name, used to disambiguate a two-show date.

    Returns:
        The matching show row (``id``, ``label``, ``date``, ``venue``,
        ``city``, ``set_label``), or None when the date is unknown to TUIT or
        ambiguous and the venue does not settle it.
    """
    if not date_iso:
        return None
    try:
        resp = session.get(
            f"{tuit_scraper.BASE_URL}{SHOWS_SEARCH_PATH}",
            params={"q": date_iso}, timeout=30,
        )
        resp.raise_for_status()
        shows = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("TUIT show search failed for %s: %s", date_iso, exc)
        return None

    shows = [s for s in shows if s.get("date") == date_iso]
    if not shows:
        return None
    if len(shows) == 1:
        return shows[0]

    if venue:
        norm = _norm(venue)
        for show in shows:
            if norm and norm == _norm(show.get("venue") or ""):
                return show
        for show in shows:
            other = _norm(show.get("venue") or "")
            if other and (other in norm or norm in other):
                return show
    # Two shows at the SAME venue is the early/late case, and only the
    # tracker's set_label separates them — nothing in entries says which half
    # of the evening a recording is, so this has to go back to the curator.
    labels = [s.get("set_label") or "?" for s in shows]
    logger.warning(
        "TUIT has %d shows on %s (%s); venue %r did not disambiguate — "
        "pick one with --set show_id=<id>",
        len(shows), date_iso, ", ".join(labels), venue,
    )
    return None


def _norm(text: str) -> str:
    """Lowercase and strip punctuation, for venue comparison."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ── Payload composition ──────────────────────────────────────────────────────


def _local_show_facts(lb_number: int, db_path=None) -> dict:
    """Gather date, venue and tour for an LB number from the local DB.

    ``entries.location`` is noisy free text, so the venue comes from
    ``olof_events`` where the date resolves one — the same rule the dossier
    uses for show identity.

    Args:
        lb_number: LB number to look up.
        db_path: Optional DB path override.

    Returns:
        Dict with ``date_iso``, ``venue``, ``city``, ``region``, ``country``,
        ``tour`` and ``location`` (the raw entries string).
    """
    facts = {"date_iso": "", "venue": "", "city": "", "region": "",
             "country": "", "tour": "", "location": ""}
    with database.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT date_str, location FROM entries WHERE lb_number=?",
            (lb_number,),
        ).fetchone()
        if not row:
            return facts
        facts["location"] = row["location"] or ""
        facts["date_iso"] = database._entry_date_to_iso_local(row["date_str"]) or ""
        if not facts["date_iso"]:
            return facts
        event = conn.execute(
            "SELECT venue, city, region, country, tour_name FROM olof_events "
            " WHERE date_str=? AND event_type='concert' ORDER BY event_id LIMIT 1",
            (facts["date_iso"],),
        ).fetchone()
        if event:
            facts.update({
                "venue": event["venue"] or "",
                "city": event["city"] or "",
                "region": event["region"] or "",
                "country": event["country"] or "",
                "tour": event["tour_name"] or "",
            })
    return facts


def normalise_taper(name: str) -> tuple[str, str]:
    """Decide what to put in the ``taper`` field, and how sure we are.

    ``entries.taper_name`` is transcribed from info files and is not clean: it
    holds real handles, every spelling of "nobody knows", and — often enough to
    matter — text that was never a taper at all ('ripped with EAC', 'excellent
    to outstanding sound'). Posting any of the latter two gives the tracker a
    taper called 'anonymous' with 300 recordings, or one called 'ripped with
    EAC'. ``taper_curation`` already owns the vocabulary that tells them apart,
    so this defers to it and only adds the placeholders it does not carry yet.

    Args:
        name: Raw taper text.

    Returns:
        ``(handle, note)``. ``handle`` is "" when the text carries no
        attribution. ``note`` is "" when the handle is a known taper,
        'placeholder' when the text means unknown, 'not_a_taper' when the
        vocabulary bars it, and 'unrecognised' for a handle nobody has seen
        before — which is sent, since a new taper looks exactly like that, but
        is worth a curator's eye first.
    """
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    if not cleaned:
        return "", ""
    if cleaned.lower().strip(" .") in EXTRA_PLACEHOLDER_TAPERS:
        return "", "placeholder"
    if taper_curation.is_placeholder(cleaned):
        return "", "placeholder"

    canon = taper_curation.canonical(cleaned)
    reason = taper_curation.exclusion_reason(canon)
    if reason in ("not_taper_builtin", "not_taper_user"):
        return "", "not_a_taper"
    if reason == "unknown_text":
        # An unrecognised handle and a sentence of info-file prose are the same
        # thing to the vocabulary, so fall back to shape. Real handles are
        # short — 'cos11', 'shu', 'Clay C. Brennecke' — while the pollution in
        # this column is phrases ('excellent to outstanding sound'). Three
        # tokens is the cut: it keeps a three-part human name and drops prose.
        # It is a shape test, not a vocabulary one, so short pollution like
        # 'ripped with EAC' still gets through — with the warning below.
        if len(cleaned.split()) > MAX_TAPER_WORDS:
            return "", "not_a_taper"
        return cleaned, "unrecognised"
    return cleaned, ""


def quality_from_text(text: str) -> str:
    """Recover an ``audio_quality`` slug from free prose.

    Only used when ``entries.rating`` is blank. Tokens are matched longest
    first and on word boundaries, so the 'ex' in 'excellent' — or in
    'experimental' — never decides the grade.

    Args:
        text: Description or notes to scan.

    Returns:
        A slug from :data:`QUALITIES`, or "" when the text says nothing.
    """
    if not text:
        return ""
    low = text.lower()
    for token in sorted(QUALITY_TOKENS, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", low):
            return QUALITY_TOKENS[token]
    return ""


def folder_warnings(folder: str | Path) -> list[str]:
    """Flag things about a folder that should be seen before it is uploaded.

    A cut-down version of the desktop uploader's pre-upload checks, limited to
    the ones that can be decided from the file listing alone. None of them
    blocks an upload; they exist so a curator is never surprised by what went
    up.

    Args:
        folder: Recording folder to inspect.

    Returns:
        Warning lines, empty when the folder looks ordinary.
    """
    root = Path(folder)
    if not root.is_dir():
        return []
    lossy: set[str] = set()
    wavs = 0
    lossless = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in LOSSY_EXTS:
            lossy.add(ext.lstrip("."))
        elif ext == ".wav":
            wavs += 1
        elif ext in AUDIO_EXTS:
            lossless += 1

    warnings = []
    if lossy:
        warnings.append(
            "lossy: folder contains " + "/".join(sorted(lossy)) +
            " files — a lossy source is not a lossless upload"
        )
    if wavs and lossless:
        warnings.append(f"wav: {wavs} stray .wav file(s) alongside the lossless audio")
    elif wavs:
        warnings.append(
            f"wav: {wavs} .wav file(s) and no compressed audio — TUIT takes flac or shn"
        )
    return warnings


def build_fields(lb_number: int, folder: str | Path, db_path=None) -> tuple[dict, list[str]]:
    """Compose every ``/upload`` field this install can fill from local data.

    ``show_id`` and ``_token`` are not set here — both need the live session —
    and neither are the file parts. Everything else comes out of ``entries``,
    ``olof_events`` and a probe of the folder.

    Args:
        lb_number: LB number being posted.
        folder: Collection folder holding the audio.
        db_path: Optional DB path override.

    Returns:
        ``(fields, warnings)``. Warnings name each value that could not be
        derived, so a curator can fill it in before the POST rather than
        discovering the gap on the tracker.
    """
    warnings: list[str] = []
    # get_entry returns {'entry': …, 'checksums': …, 'files': …}; only the
    # entry row carries the catalogue fields the form wants.
    entry = (database.get_entry(lb_number, db_path) or {}).get("entry") or {}
    facts = _local_show_facts(lb_number, db_path)
    audio = probe_audio(folder)

    fields: dict = {"lb_number": str(lb_number)}

    raw_source = (entry.get("source_type") or "").strip().lower()
    source = SOURCE_TYPE_MAP.get(raw_source, "")
    if source:
        fields["source_type"] = source
    else:
        warnings.append(
            f"source_type: entries has {entry.get('source_type')!r}, "
            "which maps to nothing on the form — set it by hand"
        )

    fmt = (audio.get("format") or "").lower()
    if fmt in FORMATS:
        fields["format"] = fmt
    else:
        warnings.append(f"format: probed {fmt or 'nothing'}; TUIT accepts flac or shn")

    rating = (entry.get("rating") or "").strip().lower()
    quality = QUALITY_MAP.get(rating, "")
    if quality:
        fields["audio_quality"] = quality
    else:
        # No letter grade. The curator usually still said how it sounds
        # somewhere in the description, in the tracker's own shorthand.
        quality = quality_from_text(entry.get("description") or "")
        if quality:
            fields["audio_quality"] = quality
            warnings.append(
                f"audio_quality: no rating — read {quality!r} out of the description"
            )
        else:
            warnings.append(f"audio_quality: entries.rating is {entry.get('rating')!r}")

    if audio.get("bit_depth") in BIT_DEPTHS:
        fields["bit_depth"] = str(audio["bit_depth"])
    elif fields.get("format") == "shn":
        # Only reached when ffprobe could not read the file at all — a readable
        # shorten stream reports s16p and resolves above. Shorten carried 8- or
        # 16-bit PCM only, and all 1,233 SHN recordings on TUIT are labelled
        # 16/44, so fall back to 16 and say so rather than post it blank.
        fields["bit_depth"] = "16"
        warnings.append(
            "bit_depth: fell back to 16 — shn present but nothing could read it"
        )
    else:
        warnings.append(f"bit_depth: probed {audio.get('bit_depth')!r}")
    if audio.get("sample_rate") in SAMPLE_RATES:
        fields["sample_rate"] = str(audio["sample_rate"])
    else:
        warnings.append(f"sample_rate: probed {audio.get('sample_rate')!r}")
    if audio.get("mixed"):
        warnings.append("audio is mixed format/depth/rate — the lowest was taken")

    raw_taper = (entry.get("taper_name") or "").strip()
    taper, taper_note = normalise_taper(raw_taper)
    if taper:
        fields["taper"] = taper
    if taper_note == "placeholder":
        warnings.append(
            f"taper: {raw_taper!r} means 'unknown' — sent blank rather than as a handle"
        )
    elif taper_note == "not_a_taper":
        warnings.append(
            f"taper: {raw_taper!r} is barred by the taper vocabulary (gear, source "
            "or label text, not a person) — sent blank"
        )
    elif taper_note == "unrecognised":
        warnings.append(
            f"taper: {raw_taper!r} is not a known handle — sending it anyway, but "
            "check it is a taper and not stray info-file text"
        )
    lineage = (entry.get("source_chain") or "").strip()
    if lineage:
        fields["lineage"] = lineage
    else:
        warnings.append("lineage: entries.source_chain is empty")

    description = (entry.get("description") or "").strip()
    if description:
        fields["description"] = description

    ffp = read_ffp(folder)
    if ffp:
        fields["ffp"] = ffp
    else:
        warnings.append("ffp: no .ffp sidecar in the folder")

    fields["new_show_date"] = facts["date_iso"]
    fields["new_venue"] = facts["venue"]
    fields["new_city"] = facts["city"]
    fields["new_state"] = facts["region"]
    fields["new_country"] = facts["country"]
    fields["new_tour"] = facts["tour"]
    if not facts["date_iso"]:
        warnings.append(
            f"date: entries.date_str is {entry.get('date_str')!r} — a circa date "
            "cannot resolve a show; set show_id by hand"
        )
    if not facts["venue"]:
        warnings.append(
            f"venue: no olof_events concert on {facts['date_iso'] or 'that date'}; "
            f"entries.location is {facts['location']!r}"
        )

    category = (entry.get("lb_category") or "").strip().lower()
    if category in CATEGORY_WARNINGS:
        warnings.append(f"category: {CATEGORY_WARNINGS[category]}")
    warnings.extend(folder_warnings(folder))
    return fields, warnings


def prepare_upload(
    lb_number: int,
    session: requests.Session | None = None,
    source_folder: str = "",
    make_torrent: bool = True,
    db_path=None,
) -> UploadPayload:
    """Build everything a POST to ``/upload`` needs, without sending it.

    This is the dry run. It runs the local gates, resolves a folder, composes
    the fields, optionally generates the ``.torrent`` against TUIT's announce
    URL, and records a 'prepared' row in ``tuit_uploads``.

    Args:
        lb_number: LB number to post.
        session: Authenticated TUIT session; without one ``show_id`` is left
            unresolved and only the ``new_show_*`` fallback is filled.
        source_folder: Folder override; otherwise the first folder
            ``db.get_folders_for_lb`` knows about is used.
        make_torrent: Generate the ``.torrent``. Hashing a large recording is
            the slow part of a dry run, so the CLI can skip it.
        db_path: Optional DB path override.

    Returns:
        The composed :class:`UploadPayload`.

    Raises:
        RuntimeError: The LB number is not seedable, has no local folder, or
            the torrent could not be generated.
    """
    allowed, reason = database.is_seedable_to_tracker(lb_number, db_path)
    if not allowed:
        raise RuntimeError(f"LB-{lb_number:05d} refuses to seed: {reason}")

    folder = source_folder or next(
        iter(database.get_folders_for_lb(lb_number, db_path)), ""
    )
    if not folder or not Path(folder).is_dir():
        raise RuntimeError(f"LB-{lb_number:05d} has no local folder to upload")

    fields, warnings = build_fields(lb_number, folder, db_path)
    payload = UploadPayload(
        lb_number=lb_number,
        fields=fields,
        info_path=find_info_file(folder),
        source_folder=folder,
        warnings=warnings,
    )
    if payload.info_path is None:
        payload.warnings.append("info_file: no .txt/.nfo/.log under 256 KB in the folder")
    elif payload.fields.pop("description", None) is not None:
        # The form's own help text: an uploaded info file "overrides anything
        # typed below". Sending both just invites a silent mismatch.
        payload.warnings.append(
            "description: dropped — the attached info_file overrides it"
        )

    if session is not None:
        show = find_show(session, fields.get("new_show_date", ""), fields.get("new_venue", ""))
        if show:
            payload.show = show
            payload.fields["show_id"] = str(show["id"])
            for key in ("new_show_date", "new_venue", "new_city",
                        "new_state", "new_country", "new_tour"):
                payload.fields.pop(key, None)
        else:
            payload.warnings.append(
                "show_id: unresolved — the new_show_* fields will create a show"
            )

    if make_torrent:
        announce = announce_url(db_path)
        if not announce:
            raise RuntimeError(
                "No TUIT announce URL known — fetch one torrent from the tracker first"
            )
        result = torrent_maker.make_torrent(
            lb_number,
            folder,
            trackers=[announce],
            source_tag=SOURCE_TAG,
            db_path=db_path,
        )
        payload.torrent_path = result["torrent_path"]
        payload.info_hash = result["infohash"]

    existing = database.tuit_has_recording(lb_number, payload.info_hash, db_path)
    if existing:
        payload.warnings.append(
            "duplicate: TUIT already has /recordings/{} for LB-{:05d} ({})".format(
                existing.get("rec_id"), lb_number,
                "same infohash" if existing.get("info_hash") else "same LB number",
            )
        )

    payload.upload_id = database.add_tuit_upload(
        lb_number=lb_number,
        status="prepared",
        info_hash=payload.info_hash or None,
        torrent_path=payload.torrent_path or None,
        show_id=int(payload.fields["show_id"]) if payload.fields.get("show_id") else None,
        source_folder=folder,
        payload_json=json.dumps(payload.as_dict(), ensure_ascii=False),
        db_path=db_path,
    )
    return payload


# ── The POST ─────────────────────────────────────────────────────────────────


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _csrf_token(session: requests.Session) -> str:
    """Fetch a fresh ``_token`` from the upload page."""
    from bs4 import BeautifulSoup

    resp = session.get(f"{tuit_scraper.BASE_URL}{UPLOAD_PATH}", timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", attrs={"action": re.compile("upload")})
    token = form.find("input", attrs={"name": "_token"}) if form else None
    return token.get("value", "") if token else ""


def post_upload(
    session: requests.Session,
    payload: UploadPayload,
    allow_duplicate: bool = False,
    db_path=None,
) -> dict:
    """POST a prepared payload to ``/upload``.

    The only function in this module that writes to the tracker. It refuses a
    payload carrying a duplicate warning unless told otherwise, and refuses one
    with no torrent — ``torrent_file`` is the form's only required field.

    Args:
        session: Authenticated TUIT session.
        payload: A payload from :func:`prepare_upload`.
        allow_duplicate: Post even though TUIT already has this LB number or
            infohash.
        db_path: Optional DB path override.

    Returns:
        Dict with ``ok``, ``rec_id`` (int or None), ``url`` and ``error``.
    """
    dupes = [w for w in payload.warnings if w.startswith("duplicate:")]
    if dupes and not allow_duplicate:
        return {"ok": False, "rec_id": None, "url": "", "error": dupes[0]}
    if not payload.torrent_path or not Path(payload.torrent_path).is_file():
        return {"ok": False, "rec_id": None, "url": "",
                "error": "no .torrent to upload (torrent_file is required)"}

    upload_id = payload.upload_id
    if upload_id is None:
        upload_id = database.add_tuit_upload(
            lb_number=payload.lb_number,
            status="prepared",
            info_hash=payload.info_hash or None,
            torrent_path=payload.torrent_path,
            show_id=int(payload.fields["show_id"]) if payload.fields.get("show_id") else None,
            source_folder=payload.source_folder,
            payload_json=json.dumps(payload.as_dict(), ensure_ascii=False),
            db_path=db_path,
        )
        payload.upload_id = upload_id

    token = _csrf_token(session)
    if not token:
        database.update_tuit_upload(
            upload_id, {"status": "failed", "error": "no CSRF token"}, db_path
        )
        return {"ok": False, "rec_id": None, "url": "", "error": "no CSRF token on /upload"}

    data = {**payload.fields, "_token": token}
    handles = []
    files = {}
    try:
        torrent = open(payload.torrent_path, "rb")  # noqa: SIM115 - closed below
        handles.append(torrent)
        files["torrent_file"] = (Path(payload.torrent_path).name, torrent,
                                 "application/x-bittorrent")
        if payload.info_path:
            info = open(payload.info_path, "rb")  # noqa: SIM115 - closed below
            handles.append(info)
            files["info_file"] = (payload.info_path.name, info, "text/plain")

        resp = session.post(
            f"{tuit_scraper.BASE_URL}{UPLOAD_PATH}",
            data=data, files=files,
            headers={"Referer": f"{tuit_scraper.BASE_URL}{UPLOAD_PATH}"},
            timeout=300, allow_redirects=True,
        )
    except (requests.RequestException, OSError) as exc:
        database.update_tuit_upload(
            upload_id, {"status": "failed", "error": str(exc)}, db_path
        )
        return {"ok": False, "rec_id": None, "url": "", "error": str(exc)}
    finally:
        for handle in handles:
            handle.close()

    rec_id = tuit_scraper.recording_id_from_url(resp.url or "")
    if rec_id:
        database.update_tuit_upload(
            upload_id,
            {"status": "uploaded", "rec_id": rec_id, "uploaded_at": _now()},
            db_path,
        )
        logger.info("TUIT: LB-%05d uploaded as /recordings/%d", payload.lb_number, rec_id)
        return {"ok": True, "rec_id": rec_id, "url": resp.url, "error": ""}

    error = _form_error(resp.text) or f"upload did not redirect to a recording ({resp.status_code})"
    database.update_tuit_upload(
        upload_id, {"status": "rejected", "error": error}, db_path
    )
    return {"ok": False, "rec_id": None, "url": resp.url or "", "error": error}


def _form_error(html: str) -> str:
    """Pull Laravel's validation messages out of a re-rendered upload page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    messages = [
        el.get_text(" ", strip=True)
        for el in soup.select(".alert-danger, .invalid-feedback, .form-error, .error")
    ]
    messages = [m for m in messages if m]
    return " | ".join(messages[:5])


def upload_and_seed(
    lb_number: int,
    session: requests.Session | None = None,
    source_folder: str = "",
    allow_duplicate: bool = False,
    seed: bool = True,
    opts: tracker_seed.SeedOptions | None = None,
    db_path=None,
) -> dict:
    """Prepare, post and then seed one recording, in that order.

    Args:
        lb_number: LB number to post.
        session: Authenticated TUIT session; one is opened when omitted.
        source_folder: Folder override.
        allow_duplicate: Post even when the tracker already has this recording.
        seed: Hand the torrent to qBittorrent after a successful upload.
        opts: Seeding options; a TUIT default is used when omitted.
        db_path: Optional DB path override.

    Returns:
        Dict with ``ok``, ``rec_id``, ``url``, ``error``, ``payload`` and
        ``seed`` (the :func:`backend.tracker_seed.seed_torrent` result, or
        None when seeding was skipped).
    """
    session = session or tuit_scraper.get_session()
    if session is None:
        return {"ok": False, "rec_id": None, "url": "", "error": "TUIT login failed",
                "payload": None, "seed": None}

    payload = prepare_upload(lb_number, session=session,
                             source_folder=source_folder, db_path=db_path)
    result = post_upload(session, payload, allow_duplicate=allow_duplicate, db_path=db_path)
    result["payload"] = payload.as_dict()
    result["seed"] = None
    if not result["ok"] or not seed:
        return result

    opts = opts or tracker_seed.SeedOptions(tracker="tuit", overlay=True)
    seeded = tracker_seed.seed_torrent(lb_number, payload.torrent_path, opts)
    result["seed"] = seeded
    if payload.upload_id is not None:
        database.update_tuit_upload(
            payload.upload_id,
            {"status": "seeded", "seeded_at": _now()} if seeded.get("ok")
            else {"error": seeded.get("error") or seeded.get("reason") or ""},
            db_path,
        )
    return result
