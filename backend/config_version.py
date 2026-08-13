"""Config-only version signals for the pipeline freshness planner (TODO-306).

Two of Phase 1's four out-of-app roots-of-record are driven by *config*, not
rows (spec Sec 1c): the merged taper alias table
(``backend.db._KNOWN_TAPER_ALIASES``) and ``concert_ranker/config.py``. Edit
either and every downstream verdict is wrong while every backlog/watermark
signal stays put — Phase 1 deliberately left this gap open.

This module hashes those config inputs to a short, stable digest, stored in
``meta`` under one key per consuming step. ``refresh.py`` compares the stored
digest against a freshly computed one and reports ``changed`` when they
differ, taking precedence over backlog/watermark (a config change invalidates
output even at backlog 0).

Two separate ranker hashes (scan/extraction vs. rank/banding) rather than one:
``ranker_scan`` only needs to re-run when the *extraction* constants change
(new audio scan required); ``ranker_rerank`` only needs to re-run when the
*banding/scoring* constants change (pure re-derivation from already-scanned
metrics). Each list is explicit names, not "every uppercase module global", so
an unrelated new constant in ``concert_ranker/config.py`` does not spuriously
invalidate every stored metric.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable

from backend import db as _db

# Explicit constant lists (not "all uppercase globals") -- see module docstring.
_SCAN_CONFIG_NAMES = (
    "BULK_SR", "NATIVE_SR", "NATIVE_WINDOW_SEC", "NATIVE_N_WINDOWS",
    "STFT_N_FFT", "STFT_HOP", "BANDS", "POLARITY", "DISQUALIFIERS",
)
_RANK_CONFIG_NAMES = (
    "SIGNED_BANDS", "SEVERITY_BANDS", "QUALITY_BANDS", "_DECADE_CUTS",
    "_SBD_CUTS", "QUALITY_MODEL", "QUALITY_MODEL_SBD", "FAMILY_WEIGHTS",
    "RECORDING_SCORE",
)


def _canonical(obj):
    """Recursively normalize *obj* into a JSON-stable structure.

    Dataclass instances (e.g. ``Disqualifier``) go through
    ``dataclasses.asdict``; sets/frozensets become sorted lists so hash
    stability does not depend on set iteration order.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _canonical(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items(), key=str)}
    if isinstance(obj, (set, frozenset)):
        return sorted(_canonical(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


def _hash_value(value) -> str:
    """Hash *value* (after canonicalization) to a short stable hex digest."""
    encoded = json.dumps(_canonical(value), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _user_taper_aliases_table_exists(db_path: str | None) -> bool:
    conn = _db.get_connection(db_path)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_taper_aliases'"
    ).fetchone()
    return row is not None


def taper_config_hash(db_path: str | None = None) -> str:
    """Hash the effective *merged* taper-alias config.

    Reads ``backend.db._KNOWN_TAPER_ALIASES`` / ``_NOT_TAPER`` as module
    attributes (never via a direct-import binding — see
    ``db.reload_taper_aliases``'s docstring) so a caller that reloaded the
    merged tables in-place is reflected here without a re-import. When
    *db_path* is given and ``user_taper_aliases`` exists there, the merged
    tables are refreshed from that DB first (a rebuild, not a write).

    Args:
        db_path: Optional database path override.

    Returns:
        16-hex-char stable digest of ``{"aliases": ..., "not_taper": ...}``.
    """
    if db_path is not None and _user_taper_aliases_table_exists(db_path):
        _db.reload_taper_aliases(db_path)
    payload = {
        "aliases": dict(_db._KNOWN_TAPER_ALIASES),
        "not_taper": sorted(_db._NOT_TAPER),
    }
    return _hash_value(payload)


def ranker_scan_config_hash() -> str:
    """Hash the concert_ranker audio-extraction constants (scan-invalidating).

    Returns:
        16-hex-char stable digest of the ``_SCAN_CONFIG_NAMES`` constants.
    """
    from concert_ranker import config as cr_config

    payload = {name: getattr(cr_config, name) for name in _SCAN_CONFIG_NAMES}
    return _hash_value(payload)


def ranker_rank_config_hash() -> str:
    """Hash the concert_ranker banding/scoring constants (rerank-invalidating).

    ``DECADE_BANDS``/``CLASS_BANDS`` are derived from ``_DECADE_CUTS``/
    ``_SBD_CUTS`` -- hashing the cuts is sufficient and stabler (no need to
    also hash their derived form).

    Returns:
        16-hex-char stable digest of the ``_RANK_CONFIG_NAMES`` constants.
    """
    from concert_ranker import config as cr_config

    payload = {name: getattr(cr_config, name) for name in _RANK_CONFIG_NAMES}
    return _hash_value(payload)


# step_id -> (meta key, hash function). Hash functions are called with no
# arguments except taper_config_hash, which stamp_for_step/version_state call
# with an explicit db_path when they have one (its default parameter makes a
# bare 0-arg call safe too).
STEP_VERSION_SOURCES: dict[str, tuple[str, Callable[..., str]]] = {
    "attribute_tapers": ("refresh_version_taper_aliases", taper_config_hash),
    "ranker_scan": ("refresh_version_ranker_scan_config", ranker_scan_config_hash),
    "ranker_rerank": ("refresh_version_ranker_rank_config", ranker_rank_config_hash),
}


def compute_expected(step_id: str, db_path: str | None = None) -> str | None:
    """Return the freshly computed hash for *step_id*, or None if unversioned."""
    entry = STEP_VERSION_SOURCES.get(step_id)
    if entry is None:
        return None
    _meta_key, hash_fn = entry
    if hash_fn is taper_config_hash:
        return hash_fn(db_path)
    return hash_fn()


def stamp_for_step(step_id: str, db_path: str | None = None) -> str | None:
    """Compute and store the current config hash for *step_id*, if versioned.

    Called only on a successful run of the consuming step, colocated with the
    ``db.record_step_run`` call for that step so the two cannot drift.

    Args:
        step_id: A key of :data:`STEP_VERSION_SOURCES`. No-op (returns None)
            for any other step_id.
        db_path: Optional database path override.

    Returns:
        The stamped hash, or None if *step_id* has no version source.
    """
    entry = STEP_VERSION_SOURCES.get(step_id)
    if entry is None:
        return None
    meta_key, _hash_fn = entry
    value = compute_expected(step_id, db_path)
    _db.set_meta(meta_key, value, db_path)
    return value


def version_state(step_id: str, stored: str | None) -> str:
    """Classify a step's config-version signal.

    Args:
        step_id: A key of :data:`STEP_VERSION_SOURCES`.
        stored: The value currently stamped in ``meta`` for that step's
            version key (None if never stamped).

    Returns:
        ``'n/a'`` if *step_id* has no version source, ``'unstamped'`` if
        *stored* is None, ``'ok'`` if the current config hash matches
        *stored*, else ``'changed'``.
    """
    if step_id not in STEP_VERSION_SOURCES:
        return "n/a"
    if stored is None:
        return "unstamped"
    expected = compute_expected(step_id)
    return "ok" if expected == stored else "changed"
