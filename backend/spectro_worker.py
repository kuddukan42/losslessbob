"""Spectrogram batch worker state + thread body, shared by the spectrogram routes and
backend/activity.py (TODO-369)."""

import logging
from pathlib import Path

_log = logging.getLogger(__name__)


_spectro_state = {
    "status":    "idle",
    "current":   "",
    "done":      0,
    "total":     0,
    "errors":    0,
    "skipped":   0,
    "stop_requested": False,
}
_spectro_lock = __import__("threading").Lock()


def get_spectrogram_status() -> dict:
    """Return a snapshot of the spectrogram batch generation worker state.

    Module-level helper (TODO-262) for ``backend/activity.py`` — mirrors the
    ``/api/spectrogram/status`` route body.

    Returns:
        Dict copy of ``_spectro_state``.
    """
    with _spectro_lock:
        return dict(_spectro_state)


def _do_spectro_batch(folders: list[str], opts: dict) -> None:
    """Run spectrogram generation for all audio files in the given folders.

    Intended to be executed in a daemon thread. Updates _spectro_state in-place
    with progress, skipped, error counts, and final status.

    Args:
        folders: List of absolute folder paths to process.
        opts: Generation options — width, height, dyn_range (int), force (bool).
    """
    def _set(**kw):
        with _spectro_lock:
            _spectro_state.update(kw)

    try:
        from backend.sox_utils import (
            AUDIO_EXTS_ALL,
            ConversionError,
            SoxNotFoundError,
            SpectrogenError,
            generate_spectrogram,
        )
    except Exception as exc:
        _set(status="error", current=str(exc))
        return

    all_files: list[tuple[Path, Path]] = []
    for folder in folders:
        p = Path(folder)
        if not p.is_dir():
            continue
        spectro_dir = p / "spectrograms"
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS_ALL:
                png = spectro_dir / (f.stem + ".png")
                all_files.append((f, png))

    _set(status="running", done=0, total=len(all_files),
         errors=0, skipped=0, stop_requested=False, current="")

    if not all_files:
        _set(status="done", current="", done=0)
        return

    done = 0
    skipped = 0
    errors = []

    for audio_path, output_png in all_files:
        with _spectro_lock:
            if _spectro_state["stop_requested"]:
                break

        _set(current=audio_path.name)

        if output_png.exists() and not opts.get("force"):
            skipped += 1
            done += 1
            _set(done=done, skipped=skipped)
            continue

        try:
            generate_spectrogram(
                audio_path, output_png,
                width=opts["width"],
                height=opts["height"],
                dyn_range=opts["dyn_range"],
                title=audio_path.name,
            )
        except SoxNotFoundError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
            _log.error("Spectrogram SoxNotFoundError: %s", e)
            _set(status="error", errors=len(errors), done=done,
                 current="SoX not found — generation stopped.")
            return
        except ConversionError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
            _log.error("Spectrogram ConversionError on %s: %s", audio_path.name, e)
        except SpectrogenError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
            _log.error("Spectrogram SpectrogenError on %s: %s", audio_path.name, e)
        except Exception as e:
            errors.append({"file": audio_path.name,
                           "error": f"Unexpected: {e}"})
            _log.error("Spectrogram unexpected error on %s: %s", audio_path.name, e)

        done += 1
        _set(done=done, errors=len(errors), skipped=skipped)

    _set(status="done", current="", done=done,
         errors=len(errors), skipped=skipped)
