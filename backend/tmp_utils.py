"""
Temp-directory selection for large intermediate audio files.

The system ``/tmp`` on this machine is a small dedicated partition (~2.7 GB), and
decoded WAV is roughly 10x the size of the FLAC/SHN it came from — a handful of
concurrent decodes, or one process killed before its ``finally`` block runs, is
enough to fill it. Every temp WAV therefore goes to a large-disk scratch base
when one is available, falling back to the system temp dir otherwise.

Same rationale and same base directory as ``tools/tapematch/tapematch/cli.py``.
"""
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Preferred scratch bases, most-preferred first. First writable one wins.
# Overridable per-deployment with LOSSLESSBOB_TMPDIR.
_SCRATCH_BASES: tuple[Path, ...] = (Path("/mnt/DATA0/tmp"),)

_ENV_VAR = "LOSSLESSBOB_TMPDIR"

_cached_base: str | None = None
_cache_valid = False


def _probe(base: Path) -> str | None:
    """Return ``base`` as a string if it exists (or can be created) and is writable."""
    try:
        base.mkdir(parents=True, exist_ok=True)
        if os.access(base, os.W_OK):
            return str(base)
    except OSError:
        pass
    return None


def audio_tmp_dir() -> str | None:
    """
    Return the directory to use for large temp audio files.

    Returns:
        Path to a large-disk scratch directory, or None to mean "use the system
        temp directory" (the value is passed straight to ``tempfile`` as ``dir=``,
        which treats None as the default).
    """
    global _cached_base, _cache_valid
    if _cache_valid:
        return _cached_base

    override = os.environ.get(_ENV_VAR)
    candidates = (Path(override),) if override else _SCRATCH_BASES
    for base in candidates:
        resolved = _probe(base)
        if resolved:
            _cached_base = resolved
            break
    else:
        if override:
            logger.warning(
                "%s=%s is not writable; falling back to %s",
                _ENV_VAR, override, tempfile.gettempdir(),
            )
        _cached_base = None

    _cache_valid = True
    return _cached_base


def reset_cache() -> None:
    """Forget the probed scratch base — for tests, and for drive remounts."""
    global _cached_base, _cache_valid
    _cached_base = None
    _cache_valid = False
