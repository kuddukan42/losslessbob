# LosslessBob — SoX Spectrogram Integration
# Claude Code Instructions

**Read `PROJECT.md` for architecture context before starting.**  
**All WIN fixes are implemented. `gui/platform_utils.py` and `backend/paths.py` are in place. Use `_subprocess_flags()` from `gui/platform_utils.py` for any new subprocess calls — but `backend/sox_utils.py` keeps its own inline copy to avoid a gui→backend import.**  
**This feature is entirely new. No existing files need breaking changes — all additions are additive.**

---

## Overview

Generate per-file audio spectrograms using SoX for visual lossy-artifact inspection.
For each audio file, produce one PNG written to a `spectrograms/` subfolder inside the
recording's folder. Stereo and multi-channel files are mixed to mono before rendering
so one image represents the full recording. The GUI provides a two-pane viewer: left
lists files, right displays the selected spectrogram at full width with vertical scroll.

---

## Tool Dependency Map

| Format | SoX native | Handling |
|--------|-----------|---------|
| .flac  | Yes       | SoX reads directly |
| .wav   | Yes       | SoX reads directly |
| .aif/.aiff | Yes  | SoX reads directly |
| .shn   | No        | ffmpeg decodes to temp WAV → SoX → delete WAV |
| .ape   | No        | ffmpeg decodes to temp WAV → SoX → delete WAV |
| .wv    | No        | ffmpeg decodes to temp WAV → SoX → delete WAV |
| .m4a   | No        | ffmpeg decodes to temp WAV → SoX → delete WAV |

**Original files are never modified.** The only file written inside a recording folder
is the PNG under `spectrograms/`. Temp WAVs go to the OS temp directory and are
deleted unconditionally after each spectrogram is written, even on error.

SoX with FLAC support is the only hard dependency. ffmpeg is optional — its absence
means non-FLAC/WAV formats are skipped with a `ConversionError` per file, not a crash.

**Install references (included in GUI help text):**
- Linux: `sudo apt install sox libsox-fmt-all`
- macOS: `brew install sox`
- Windows: https://sox.sourceforge.net — add install dir to PATH

---

## SPEC-01: Backend — Tool Detection

**Files:** `backend/sox_utils.py` (new)  
**Dependencies:** None. WIN fixes are all in place. `_no_window()` is defined inline in `sox_utils.py` to avoid a backend→gui circular import — do NOT import from `gui/platform_utils.py` in backend code.  
**New packages:** None

Create `backend/sox_utils.py`:

```python
"""
SoX tool detection and spectrogram generation.

Strategy for non-native formats (SHN, APE, WV, M4A, etc.):
  1. Decode to a temporary WAV in the system temp directory using ffmpeg.
  2. Run SoX on the temp WAV.
  3. Delete the temp WAV unconditionally in a finally block.

Original audio files are NEVER modified, moved, or written to.
The only file written inside the recording folder is the PNG under spectrograms/.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ── Console suppression (inline — no gui imports in backend) ──────────────────

def _no_window() -> dict:
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            "startupinfo": si,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    return {}


# ── Tool detection (cached per process) ──────────────────────────────────────

_SOX_CMD:    list | None | object = object()
_FFMPEG_CMD: list | None | object = object()


def _find_sox() -> list | None:
    """Return ['sox'] or WSL equivalent, or None."""
    if sys.platform == "win32":
        if shutil.which("sox"):
            return ["sox"]
        if shutil.which("wsl"):
            try:
                r = subprocess.run(
                    ["wsl", "which", "sox"],
                    capture_output=True, text=True, timeout=8,
                    **_no_window(),
                )
                if r.returncode == 0 and r.stdout.strip():
                    return ["wsl", "sox"]
            except Exception:
                pass
        return None
    return ["sox"] if shutil.which("sox") else None


def _find_ffmpeg() -> list | None:
    if sys.platform == "win32":
        if shutil.which("ffmpeg"):
            return ["ffmpeg"]
        if shutil.which("wsl"):
            try:
                r = subprocess.run(
                    ["wsl", "which", "ffmpeg"],
                    capture_output=True, text=True, timeout=8,
                    **_no_window(),
                )
                if r.returncode == 0 and r.stdout.strip():
                    return ["wsl", "ffmpeg"]
            except Exception:
                pass
        return None
    return ["ffmpeg"] if shutil.which("ffmpeg") else None


def get_sox() -> list | None:
    global _SOX_CMD
    if isinstance(_SOX_CMD, type(object())):
        _SOX_CMD = _find_sox()
    return _SOX_CMD


def get_ffmpeg() -> list | None:
    global _FFMPEG_CMD
    if isinstance(_FFMPEG_CMD, type(object())):
        _FFMPEG_CMD = _find_ffmpeg()
    return _FFMPEG_CMD


def check_sox_version() -> str:
    """Return version string, or empty string if unavailable."""
    sox = get_sox()
    if not sox:
        return ""
    try:
        r = subprocess.run(
            sox + ["--version"],
            capture_output=True, text=True, timeout=8,
            **_no_window(),
        )
        return (r.stderr or r.stdout).strip().splitlines()[0]
    except Exception:
        return ""


# ── Format classification ─────────────────────────────────────────────────────

# SoX reads these natively with no intermediate step.
_SOX_NATIVE = frozenset({".flac", ".wav", ".wave", ".aif", ".aiff"})

# These require decoding to a temp WAV via ffmpeg before SoX can read them.
# The original file is never touched — only a temporary WAV is created and
# deleted after the spectrogram PNG is written.
_NEEDS_CONVERSION = frozenset({".shn", ".ape", ".wv", ".m4a", ".mp3", ".ogg"})

# All audio extensions this module will attempt to process
AUDIO_EXTS_ALL = _SOX_NATIVE | _NEEDS_CONVERSION


def _is_wsl_sox() -> bool:
    sox = get_sox()
    return sox is not None and len(sox) > 1 and sox[0] == "wsl"


def _to_wsl_path(p: Path) -> str:
    """Convert a Windows absolute path to a WSL /mnt/X/... path."""
    p = p.resolve()
    drive = p.drive.rstrip(":").lower()
    rest  = str(p)[len(p.drive):].replace("\\", "/")
    return f"/mnt/{drive}{rest}"
```

---

## SPEC-02: Backend — Convert-Analyze-Cleanup Pattern

**Files:** `backend/sox_utils.py` (continued)  
**Dependencies:** SPEC-01

**Design contract:**
- Original audio files are read-only inputs. Nothing is ever written next to them.
- Temp WAVs go to the OS temp directory (`tempfile.gettempdir()`), not to the
  recording folder.
- Temp WAVs are deleted in a `finally` block — cleanup happens even on exception,
  keyboard interrupt, or SoX error.
- One temp WAV exists at a time (sequential processing). Peak temp disk usage equals
  the size of one uncompressed WAV. For 24-bit/96kHz stereo, a 90-minute recording
  is approximately 3 GB. The system temp dir must have sufficient space.
- The `spectrograms/` directory is the only location written inside a recording folder.

Append to `backend/sox_utils.py`:

```python
# ── Exceptions ────────────────────────────────────────────────────────────────

class SoxNotFoundError(Exception):
    pass

class ConversionError(Exception):
    pass

class SpectrogenError(Exception):
    pass


# ── Temp WAV conversion ───────────────────────────────────────────────────────

def _convert_to_wav(audio_path: Path) -> Path:
    """
    Decode audio_path to a temporary PCM WAV in the system temp directory.

    The caller MUST delete the returned path when done — use a try/finally block.
    The original file is never modified.

    Returns the Path to the temp WAV.
    Raises ConversionError if ffmpeg is unavailable or fails.
    """
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise ConversionError(
            f"Format {audio_path.suffix!r} requires ffmpeg for decoding, "
            "but ffmpeg was not found.\n"
            "Install with:\n"
            "  Linux:   sudo apt install ffmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html  (add to PATH)\n\n"
            "Alternatively, convert the file to FLAC or WAV manually and "
            "re-run the spectrogram generator."
        )

    # Create temp file — mkstemp returns (fd, path), close fd immediately.
    # We pass the path to ffmpeg as the output; ffmpeg will overwrite the empty file.
    fd, tmp_path_str = tempfile.mkstemp(
        suffix=".wav",
        prefix=f"lb_spectro_{audio_path.stem}_",
    )
    os.close(fd)
    tmp_path = Path(tmp_path_str)

    use_wsl = _is_wsl_sox()

    if use_wsl and not shutil.which("ffmpeg"):
        # ffmpeg is only available in WSL — use wsl ffmpeg
        in_path  = _to_wsl_path(audio_path)
        out_path = _to_wsl_path(tmp_path)
        cmd = ["wsl", "ffmpeg",
               "-y",                    # overwrite temp file
               "-i", in_path,
               "-vn",                   # no video stream
               "-c:a", "pcm_s32le",     # 32-bit PCM — lossless, handles all depths
               "-loglevel", "error",
               out_path]
    else:
        cmd = ffmpeg + [
            "-y",
            "-i", str(audio_path),
            "-vn",
            "-c:a", "pcm_s32le",
            "-loglevel", "error",
            str(tmp_path),
        ]

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            **_no_window(),
        )
    except subprocess.TimeoutExpired:
        tmp_path.unlink(missing_ok=True)
        raise ConversionError(
            f"ffmpeg timed out (>600s) decoding {audio_path.name}. "
            "The file may be corrupt."
        )

    if r.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        msg = (r.stderr or r.stdout or "").strip()
        raise ConversionError(
            f"ffmpeg failed on {audio_path.name} (exit {r.returncode}): {msg}"
        )

    return tmp_path


# ── Spectrogram generation ────────────────────────────────────────────────────

def generate_spectrogram(
    audio_path: Path,
    output_png:  Path,
    width:     int = 1500,    # per-song default (5–10 min/track)
    height:    int = 513,
    dyn_range: int = 120,
    title:     str = "",
) -> Path:
    """
    Generate a spectrogram PNG for one audio file.

    All channels are mixed to mono so stereo and multi-channel recordings
    produce one composite image. This is correct for lossy-artifact
    inspection — you want one image showing the full frequency content,
    not separate per-channel images.

    For formats SoX cannot read natively (SHN, APE, WV, M4A, etc.):
      1. ffmpeg decodes the file to a temp WAV in the OS temp directory.
      2. SoX reads the temp WAV and writes the PNG.
      3. The temp WAV is deleted unconditionally.
    The original file is never modified or written to.

    Args:
        audio_path: source audio file. Read-only — never modified.
        output_png: destination PNG. Parent dir created if absent.
                    This is the ONLY file written; it goes inside
                    <recording_folder>/spectrograms/<stem>.png.
        width:      PNG width in pixels (time axis).
                    Each file is one song (typically 5–10 minutes).
                    At 3000px: ~5–10px/sec — high detail, good for artifact inspection.
                    At 1500px: ~2.5–5px/sec — standard detail, faster to generate.
                    Wider images show more detail but use more disk space and RAM.
        height:     PNG height in pixels (frequency axis). Must be odd.
                    513 → 256 FFT bins, covers 0–22 kHz at 44.1kHz.
                    Use 1025 for 88.2/96kHz recordings to see full range.
        dyn_range:  Colour scale range in dB.
                    120 = standard lossless reference.
                    Lossy re-encodes show raised noise floors at 120dB.
        title:      Text rendered in the PNG header. Defaults to filename.

    Returns:
        output_png Path on success.

    Raises:
        SoxNotFoundError:  SoX not in PATH.
        ConversionError:   Non-native format and ffmpeg unavailable/failed.
        SpectrogenError:   SoX ran but failed or produced no PNG.
        FileNotFoundError: audio_path does not exist.
    """
    sox = get_sox()
    if not sox:
        raise SoxNotFoundError(
            "SoX not found. Install with:\n"
            "  Linux:   sudo apt install sox libsox-fmt-all\n"
            "  macOS:   brew install sox\n"
            "  Windows: https://sox.sourceforge.net  (add to PATH)"
        )

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if height % 2 == 0:
        height += 1

    title = title or audio_path.name
    ext   = audio_path.suffix.lower()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    # Decide which file SoX will read: the original (native) or a temp WAV.
    sox_input: Path = audio_path
    tmp_wav:   Path | None = None

    if ext in _NEEDS_CONVERSION:
        # Decode to temp WAV. tmp_wav MUST be deleted in the finally block below.
        tmp_wav   = _convert_to_wav(audio_path)
        sox_input = tmp_wav
    elif ext not in _SOX_NATIVE:
        raise SpectrogenError(
            f"Unsupported format: {ext!r}. "
            f"Native: {sorted(_SOX_NATIVE)}  "
            f"Via ffmpeg: {sorted(_NEEDS_CONVERSION)}"
        )

    try:
        _run_sox_spectrogram(
            sox, sox_input, output_png,
            width, height, dyn_range, title,
        )
    finally:
        # Always clean up the temp WAV — even on exception.
        # The original file (audio_path) is never touched.
        if tmp_wav is not None:
            tmp_wav.unlink(missing_ok=True)

    return output_png


def _run_sox_spectrogram(
    sox:       list,
    input_wav: Path,
    output_png: Path,
    width:     int,
    height:    int,
    dyn_range: int,
    title:     str,
) -> None:
    """
    Internal: run SoX spectrogram on input_wav, write output_png.
    input_wav must be a format SoX can read natively (FLAC, WAV, AIFF,
    or a temp WAV produced by _convert_to_wav).
    """
    use_wsl = _is_wsl_sox()

    def _p(path: Path) -> str:
        return _to_wsl_path(path) if use_wsl else str(path)

    cmd = (
        sox
        + [_p(input_wav), "-n",
           "remix", "-",        # mix all channels to mono
           "rate", "44100",     # normalise to 44.1kHz for consistent px/sec scale
                                  # NOTE: for 88.2/96kHz source files this clips
                                  # content above 22kHz. Remove this line if the
                                  # source sample rate needs to be preserved in the
                                  # image (set height=1025 alongside).
           "spectrogram",
           "-x", str(width),
           "-y", str(height),
           "-z", str(dyn_range),
           "-w", "Kaiser",
           "-t", title,
           "-o", _p(output_png)]
    )

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            **_no_window(),
        )
    except subprocess.TimeoutExpired:
        raise SpectrogenError(
            f"SoX timed out after 300s on {input_wav.name}. "
            "Try reducing image width or check available memory."
        )

    if r.returncode != 0:
        raise SpectrogenError(
            f"SoX failed (exit {r.returncode}): {(r.stderr or '').strip()}"
        )

    if not output_png.exists():
        raise SpectrogenError(
            f"SoX exited 0 but {output_png.name} was not created. "
            "Ensure SoX was compiled with PNG support (libpng). "
            "On Linux: sudo apt install sox libsox-fmt-all"
        )
```

---

## SPEC-03: Backend — Batch Processing + API Routes

**Files:** `backend/app.py`, `backend/sox_utils.py`  
**Dependencies:** SPEC-01, SPEC-02

### Part A — Batch State

Add module-level state in `backend/app.py` after `_data_dl_state`:

```python
_spectro_state = {
    "status":    "idle",    # idle | running | done | error
    "current":   "",        # filename currently being processed
    "done":      0,
    "total":     0,
    "errors":    [],        # list of {file, error} dicts
    "skipped":   0,         # already-existing PNGs skipped
    "stop_requested": False,
}
_spectro_lock = __import__("threading").Lock()
```

### Part B — API Routes

Add inside `create_app()` in `backend/app.py`:

```python
    @app.route("/api/spectrogram/check", methods=["GET"])
    def spectrogram_check():
        """Return tool availability for the Setup tab indicator."""
        from backend.sox_utils import check_sox_version, get_ffmpeg
        sox_ver = check_sox_version()
        ffmpeg  = get_ffmpeg()
        return jsonify({
            "sox_available":    bool(sox_ver),
            "sox_version":      sox_ver,
            "ffmpeg_available": ffmpeg is not None,
        })

    @app.route("/api/spectrogram/generate", methods=["POST"])
    def spectrogram_generate():
        """
        Start batch spectrogram generation for a list of folders.
        Body: {
            folders:    ["/path/to/folder", ...],
            width:      1500,          # optional — per-song default (5–10 min/file)
            height:     513,           # optional
            dyn_range:  120,           # optional
            force:      false,         # re-generate even if PNG exists
        }
        """
        with _spectro_lock:
            if _spectro_state["status"] == "running":
                return jsonify({"error": "Generation already running"}), 409

        data    = request.get_json() or {}
        folders = data.get("folders", [])
        if not folders:
            return jsonify({"error": "folders list required"}), 400

        opts = {
            "width":     int(data.get("width",    1500)),
            "height":    int(data.get("height",    513)),
            "dyn_range": int(data.get("dyn_range", 120)),
            "force":     bool(data.get("force",  False)),
        }
        import threading as _t
        _t.Thread(target=_do_spectro_batch,
                  args=([str(f) for f in folders], opts),
                  daemon=True).start()
        return jsonify({"ok": True})

    @app.route("/api/spectrogram/status", methods=["GET"])
    def spectrogram_status():
        with _spectro_lock:
            return jsonify(dict(_spectro_state))

    @app.route("/api/spectrogram/stop", methods=["POST"])
    def spectrogram_stop():
        with _spectro_lock:
            _spectro_state["stop_requested"] = True
        return jsonify({"ok": True})

    @app.route("/api/spectrogram/list", methods=["POST"])
    def spectrogram_list():
        """
        Return a dict of {folder -> [png_relative_path, ...]} for the viewer.
        Body: {folders: [...]}
        """
        from backend.sox_utils import AUDIO_EXTS_ALL
        folders = (request.get_json() or {}).get("folders", [])
        result  = {}
        for folder in folders:
            p = Path(folder)
            if not p.is_dir():
                continue
            spectro_dir = p / "spectrograms"
            audio_files = sorted(
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS_ALL
            )
            pngs = {
                png.stem: str(png)
                for png in (spectro_dir.iterdir() if spectro_dir.is_dir() else [])
                if png.suffix.lower() == ".png"
            }
            entries = []
            for af in audio_files:
                png_path = pngs.get(af.stem, None)
                entries.append({
                    "audio_file": str(af),
                    "audio_name": af.name,
                    "png_path":   png_path,
                    "has_png":    png_path is not None,
                })
            if entries:
                result[folder] = entries
        return jsonify(result)
```

### Part C — Batch Worker Function

Add at module level in `backend/app.py` (outside `create_app()`):

```python
def _do_spectro_batch(folders: list[str], opts: dict) -> None:
    from pathlib import Path
    from backend.sox_utils import (
        generate_spectrogram, AUDIO_EXTS_ALL,
        SoxNotFoundError, ConversionError, SpectrogenError,
    )

    def _set(**kw):
        with _spectro_lock:
            _spectro_state.update(kw)

    # Count total files across all folders first
    all_files: list[tuple[Path, Path]] = []   # (audio_path, output_png)
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
         errors=[], skipped=0, stop_requested=False, current="")

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

        # Skip if already generated and force=False
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
            # Fatal — SoX not installed, no point continuing
            errors.append({"file": audio_path.name, "error": str(e)})
            _set(status="error", errors=list(errors), done=done,
                 current="SoX not found — generation stopped.")
            return
        except ConversionError as e:
            # ffmpeg unavailable or decode failed — log and continue to next file
            errors.append({"file": audio_path.name, "error": str(e)})
        except SpectrogenError as e:
            errors.append({"file": audio_path.name, "error": str(e)})
        except Exception as e:
            errors.append({"file": audio_path.name,
                            "error": f"Unexpected: {e}"})

        done += 1
        _set(done=done, errors=list(errors), skipped=skipped)

    _set(status="done", current="", done=done,
         errors=list(errors), skipped=skipped)
```

### Part D — Add `AUDIO_EXTS_ALL` to `sox_utils.py`

Add at module level in `backend/sox_utils.py` after the format sets.
Note: `AUDIO_EXTS_ALL` is already defined in SPEC-01 as `_SOX_NATIVE | _NEEDS_CONVERSION`.
If SPEC-01 was applied correctly this step is already done. Verify the line exists:

```python
# All audio extensions this module will attempt to process
AUDIO_EXTS_ALL = _SOX_NATIVE | _NEEDS_CONVERSION
```

---

## SPEC-04: GUI — Spectrogram Tab

**Files:** `gui/spectrogram_tab.py` (new), `gui/main_window.py`  
**Dependencies:** SPEC-01 through SPEC-03. WIN-14 is already implemented — `url_to_local_path()` exists in `gui/platform_utils.py`. WIN-17 drop fix pattern is already applied — use `event.acceptProposedAction()` first then `QTimer.singleShot(0, ...)` for refresh.

Create `gui/spectrogram_tab.py`:

```python
"""
SpectrogramTab: generate and review per-file spectrograms.
Left panel:  folder list + per-folder file/PNG inventory.
Right panel: full-width zoomable PNG viewer.
"""
import requests
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPixmap, QColor, QAction, QWheelEvent
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QPushButton, QLabel, QScrollArea, QProgressBar,
    QFileDialog, QMenu, QCheckBox, QSpinBox, QGroupBox,
    QSizePolicy, QMessageBox,
)


# ── Drag-and-drop folder list ─────────────────────────────────────────────────

class _DropFolderList(QListWidget):
    folders_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        # WIN-17 pattern (already in codebase): accept first, defer refresh
        event.acceptProposedAction()
        from gui.platform_utils import url_to_local_path
        folders, seen = [], set()
        for url in event.mimeData().urls():
            p    = url_to_local_path(url)
            path = str(p if p.is_dir() else p.parent)
            if path not in seen:
                seen.add(path)
                folders.append(path)
        if folders:
            self.folders_dropped.emit(folders)


# ── Zoomable image viewer ─────────────────────────────────────────────────────

class _ImageViewer(QScrollArea):
    """
    Scroll area that shows a spectrogram PNG.
    - Default: image fills the scroll area width (fit-width mode).
    - Ctrl+scroll or zoom buttons: scale freely.
    - Double-click: reset to fit-width.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setWidgetResizable(False)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._label.mouseDoubleClickEvent = lambda e: self._fit_width()
        self.setWidget(self._label)

        self._pixmap:   QPixmap | None = None
        self._scale:    float  = 1.0
        self._fit_mode: bool   = True   # True = always fit to scroll width

    def load(self, png_path: str) -> bool:
        pix = QPixmap(png_path)
        if pix.isNull():
            self._label.setText("Could not load image.")
            self._pixmap = None
            return False
        self._pixmap   = pix
        self._fit_mode = True
        self._fit_width()
        return True

    def clear_image(self):
        self._pixmap   = None
        self._fit_mode = True
        self._label.clear()
        self._label.setText("")

    def zoom_in(self):
        self._fit_mode = False
        self._set_scale(self._scale * 1.25)

    def zoom_out(self):
        self._fit_mode = False
        self._set_scale(self._scale * 0.80)

    def _fit_width(self):
        if not self._pixmap:
            return
        self._fit_mode = True
        vw = self.viewport().width() - 4
        ratio = vw / max(1, self._pixmap.width())
        self._scale = ratio
        self._apply_scale()

    def _set_scale(self, scale: float):
        self._scale = max(0.05, min(scale, 8.0))
        self._apply_scale()

    def _apply_scale(self):
        if not self._pixmap:
            return
        w = int(self._pixmap.width()  * self._scale)
        h = int(self._pixmap.height() * self._scale)
        self._label.setPixmap(
            self._pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        )
        self._label.resize(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._pixmap:
            self._fit_width()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)


# ── Worker ────────────────────────────────────────────────────────────────────

class _Worker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


# ── Main tab ──────────────────────────────────────────────────────────────────

class SpectrogramTab(QWidget):

    def __init__(self, flask_port: int, parent=None):
        super().__init__(parent)
        self.flask_port    = flask_port
        self._folders:     list[str] = []
        self._inventory:   dict      = {}   # folder -> [{audio_name,png_path,has_png}]
        self._workers:     list      = []
        self._poll_timer:  QTimer | None = None
        self._current_png: str = ""
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        main = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)

        # Folder list
        folder_label = QLabel("Folders")
        ll.addWidget(folder_label)
        self.folder_list = _DropFolderList()
        self.folder_list.folders_dropped.connect(self._on_folders_dropped)
        ll.addWidget(self.folder_list)

        folder_btns = QHBoxLayout()
        add_folder_btn = QPushButton("Add Folder…")
        add_folder_btn.clicked.connect(self._on_add_folder)
        folder_btns.addWidget(add_folder_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._on_clear_folders)
        folder_btns.addWidget(clear_btn)
        ll.addLayout(folder_btns)

        # File list inside selected folder
        track_label = QLabel("Tracks")
        ll.addWidget(track_label)
        self.track_list = QListWidget()
        self.track_list.currentItemChanged.connect(self._on_track_selected)
        ll.addWidget(self.track_list)

        # Options group
        opts_group = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_group)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Image width (px):"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(300, 9000)
        self.width_spin.setValue(1500)
        self.width_spin.setSingleStep(300)
        self.width_spin.setToolTip(
            "PNG width in pixels (time axis). Each file is one song (5–10 min).\n"
            "1500px → ~2.5–5px/sec  |  3000px → ~5–10px/sec (more detail)\n"
            "Wider = more time detail, more disk space, slower generation."
        )
        width_row.addWidget(self.width_spin)
        opts_layout.addLayout(width_row)

        dyn_row = QHBoxLayout()
        dyn_row.addWidget(QLabel("Dynamic range (dB):"))
        self.dyn_spin = QSpinBox()
        self.dyn_spin.setRange(20, 180)
        self.dyn_spin.setValue(120)
        self.dyn_spin.setToolTip(
            "Colour scale range in dB. 120 is standard for lossless.\n"
            "Lossy artifacts (noise floor plateaus, spectral cutoffs) \n"
            "are most visible at 120dB."
        )
        dyn_row.addWidget(self.dyn_spin)
        opts_layout.addLayout(dyn_row)

        self.force_cb = QCheckBox("Regenerate existing spectrograms")
        self.force_cb.setToolTip(
            "Re-run SoX even if a PNG already exists for this file.\n"
            "Uncheck to skip already-generated files (faster for large batches)."
        )
        opts_layout.addWidget(self.force_cb)

        ll.addWidget(opts_group)

        # Generate button
        self.generate_btn = QPushButton("Generate Spectrograms")
        self.generate_btn.setToolTip(
            "Run SoX on all audio files in all listed folders.\n"
            "PNGs are saved to <folder>/spectrograms/<trackname>.png"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        ll.addWidget(self.generate_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        ll.addWidget(self.stop_btn)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        ll.addWidget(self.progress_bar)
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("font-size: 10px;")
        ll.addWidget(self.progress_label)

        left.setFixedWidth(280)
        splitter.addWidget(left)

        # ── Right panel ──────────────────────────────────────────────────────
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        # Viewer toolbar
        viewer_toolbar = QHBoxLayout()
        self.image_title = QLabel("Select a track to view its spectrogram")
        self.image_title.setStyleSheet("font-weight: bold;")
        viewer_toolbar.addWidget(self.image_title)
        viewer_toolbar.addStretch()

        zoom_in_btn = QPushButton("Zoom In (+)")
        zoom_in_btn.setFixedWidth(90)
        zoom_in_btn.clicked.connect(lambda: self.viewer.zoom_in())
        viewer_toolbar.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("Zoom Out (−)")
        zoom_out_btn.setFixedWidth(90)
        zoom_out_btn.clicked.connect(lambda: self.viewer.zoom_out())
        viewer_toolbar.addWidget(zoom_out_btn)

        fit_btn = QPushButton("Fit Width")
        fit_btn.setFixedWidth(80)
        fit_btn.clicked.connect(lambda: self.viewer._fit_width())
        viewer_toolbar.addWidget(fit_btn)

        open_btn = QPushButton("Open Folder")
        open_btn.setFixedWidth(90)
        open_btn.clicked.connect(self._on_open_folder)
        viewer_toolbar.addWidget(open_btn)

        rl.addLayout(viewer_toolbar)

        # Hint bar
        self.hint_label = QLabel(
            "Tip: Ctrl+scroll to zoom · Double-click image to reset fit · "
            "Pink/salmon rows = PNG not yet generated"
        )
        self.hint_label.setStyleSheet("font-size: 10px; color: #666;")
        rl.addWidget(self.hint_label)

        # Image viewer
        self.viewer = _ImageViewer()
        rl.addWidget(self.viewer)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 10px;")
        rl.addWidget(self.status_label)

        splitter.addWidget(right)
        splitter.setSizes([280, 820])
        main.addWidget(splitter)

        # Right-click on folder list
        self.folder_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(
            self._on_folder_context)

        # Right-click on track list
        self.track_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_list.customContextMenuRequested.connect(
            self._on_track_context)

    # ── Folder management ─────────────────────────────────────────────────────

    def _on_add_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Recording Folder", str(Path.home()))
        if path:
            self._add_folders([path])

    def _on_folders_dropped(self, folders):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._add_folders(folders))

    def _add_folders(self, folders: list[str]):
        for f in folders:
            if f not in self._folders:
                self._folders.append(f)
                item = QListWidgetItem(Path(f).name)
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setToolTip(f)
                self.folder_list.addItem(item)
        self._refresh_inventory()

    def _on_clear_folders(self):
        self._folders.clear()
        self._inventory.clear()
        self.folder_list.clear()
        self.track_list.clear()
        self.viewer.clear_image()
        self.image_title.setText("Select a track to view its spectrogram")

    def _on_folder_context(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole)
        menu   = QMenu(self)

        load_act = QAction("Load Tracks", self)
        load_act.triggered.connect(lambda: self._load_tracks_for(folder))
        menu.addAction(load_act)

        rm_act = QAction("Remove Folder", self)
        rm_act.triggered.connect(lambda: self._remove_folder(folder))
        menu.addAction(rm_act)

        menu.exec(self.folder_list.mapToGlobal(pos))

    def _remove_folder(self, folder: str):
        self._folders = [f for f in self._folders if f != folder]
        self._inventory.pop(folder, None)
        for i in range(self.folder_list.count()):
            if self.folder_list.item(i).data(Qt.ItemDataRole.UserRole) == folder:
                self.folder_list.takeItem(i)
                break
        self.track_list.clear()
        self.viewer.clear_image()

    # ── Inventory ─────────────────────────────────────────────────────────────

    def _refresh_inventory(self):
        """Ask backend for the current PNG status of all folders."""
        if not self._folders:
            return
        folders = list(self._folders)
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/list",
            json={"folders": folders}, timeout=15,
        ).json())
        w.finished.connect(self._on_inventory_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_inventory_loaded(self, data):
        if not isinstance(data, dict):
            return
        self._inventory = data
        # Update folder list visual indicators
        for i in range(self.folder_list.count()):
            folder = self.folder_list.item(i).data(Qt.ItemDataRole.UserRole)
            entries = data.get(folder, [])
            total  = len(entries)
            has    = sum(1 for e in entries if e["has_png"])
            label  = f"{Path(folder).name}  [{has}/{total}]"
            self.folder_list.item(i).setText(label)
        # Reload track list if a folder is selected
        item = self.folder_list.currentItem()
        if item:
            self._load_tracks_for(item.data(Qt.ItemDataRole.UserRole))

    def _load_tracks_for(self, folder: str):
        self.track_list.clear()
        self.viewer.clear_image()
        entries = self._inventory.get(folder, [])
        for e in entries:
            item = QListWidgetItem(e["audio_name"])
            item.setData(Qt.ItemDataRole.UserRole, e)
            if not e["has_png"]:
                item.setBackground(QColor("#ffe4e1"))   # salmon — no PNG yet
                item.setToolTip("No spectrogram yet — click Generate to create")
            else:
                item.setToolTip(e["png_path"])
            self.track_list.addItem(item)

    def _on_track_selected(self, current, _previous):
        if not current:
            return
        e = current.data(Qt.ItemDataRole.UserRole)
        if not e:
            return
        if e.get("has_png") and e.get("png_path"):
            self._load_image(e["png_path"], e["audio_name"])
        else:
            self.viewer.clear_image()
            self.image_title.setText(f"{e['audio_name']} — no spectrogram yet")
            self.status_label.setText(
                "No PNG for this track. Run Generate Spectrograms first."
            )

    def _load_image(self, png_path: str, name: str):
        self._current_png = png_path
        ok = self.viewer.load(png_path)
        if ok:
            self.image_title.setText(name)
            self.status_label.setText(f"Loaded: {png_path}")
        else:
            self.status_label.setText(f"Failed to load: {png_path}")

    def _on_track_context(self, pos):
        item = self.track_list.itemAt(pos)
        if not item:
            return
        e    = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        if e.get("has_png"):
            view_act = QAction("View Spectrogram", self)
            view_act.triggered.connect(
                lambda: self._load_image(e["png_path"], e["audio_name"]))
            menu.addAction(view_act)

            open_act = QAction("Open PNG Externally", self)
            open_act.triggered.connect(
                lambda: self._open_externally(e["png_path"]))
            menu.addAction(open_act)

        gen_act = QAction("Generate This File Only", self)
        gen_act.triggered.connect(lambda: self._generate_single(e))
        menu.addAction(gen_act)

        menu.exec(self.track_list.mapToGlobal(pos))

    def _open_externally(self, path: str):
        from gui.platform_utils import open_file
        try:
            open_file(path)
        except Exception as e:
            self.status_label.setText(f"Open failed: {e}")

    def _on_open_folder(self):
        item = self.folder_list.currentItem()
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole)
        spectro_dir = Path(folder) / "spectrograms"
        target = spectro_dir if spectro_dir.is_dir() else Path(folder)
        from gui.platform_utils import open_folder
        try:
            open_folder(target)
        except Exception as e:
            self.status_label.setText(f"Open failed: {e}")

    # ── Generation ────────────────────────────────────────────────────────────

    def _on_generate(self):
        if not self._folders:
            self.status_label.setText("Add folders first.")
            return
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting…")

        payload = {
            "folders":   self._folders,
            "width":     self.width_spin.value(),
            "dyn_range": self.dyn_spin.value(),
            "force":     self.force_cb.isChecked(),
        }
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/generate",
            json=payload, timeout=10,
        ).json())
        w.finished.connect(lambda r: (
            self._start_poll() if not r.get("error")
            else self._on_gen_error(r["error"])
        ))
        w.error.connect(self._on_gen_error)
        self._workers.append(w)
        w.start()

    def _generate_single(self, entry: dict):
        """Generate spectrogram for one file via the batch API with one file."""
        folder = str(Path(entry["audio_file"]).parent)
        payload = {
            "folders": [folder],
            "width":     self.width_spin.value(),
            "dyn_range": self.dyn_spin.value(),
            "force":     True,
        }
        self.status_label.setText(f"Generating: {entry['audio_name']}…")
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/generate",
            json=payload, timeout=10,
        ).json())
        w.finished.connect(lambda r: (
            self._start_poll() if not r.get("error")
            else self.status_label.setText(f"Error: {r['error']}")
        ))
        self._workers.append(w)
        w.start()

    def _on_gen_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {msg}")

    def _on_stop(self):
        self.stop_btn.setEnabled(False)
        requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/stop",
            timeout=5,
        )

    def _start_poll(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(800)

    def _poll(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/spectrogram/status",
                timeout=5,
            ).json()
        except Exception:
            return

        status = r.get("status", "")
        done   = r.get("done",  0)
        total  = r.get("total", 0)
        errs   = r.get("errors", [])

        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)

        skip_msg = f"  ({r['skipped']} skipped)" if r.get("skipped") else ""
        err_msg  = f"  {len(errs)} error(s)" if errs else ""
        self.progress_label.setText(
            f"{r.get('current', '')}  [{done}/{total}]{skip_msg}{err_msg}"
        )

        if status in ("done", "error"):
            self._poll_timer.stop()
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

            if status == "error":
                self.progress_label.setText(
                    r.get("current", "Generation failed.")
                )
                self.status_label.setText("Generation stopped with errors.")
            else:
                self.status_label.setText(
                    f"Done. {done} file(s) processed, "
                    f"{r.get('skipped',0)} skipped, {len(errs)} error(s)."
                )
                if errs:
                    err_text = "\n".join(
                        f"{e['file']}: {e['error']}" for e in errs
                    )
                    QMessageBox.warning(
                        self, "Generation Errors",
                        f"{len(errs)} file(s) failed:\n\n{err_text}"
                    )

            self.progress_bar.setVisible(False)
            # Refresh inventory so track list updates PNG status
            self._refresh_inventory()
```

---

## SPEC-05: Register Tab in Main Window

**Files:** `gui/main_window.py`  
**Dependencies:** SPEC-04

In `_build_tabs()`, add after the DB Editor tab:

```python
        from gui.spectrogram_tab import SpectrogramTab
        self.spectrogram_tab = SpectrogramTab(self.flask_port)
        self.tabs.addTab(self.spectrogram_tab, "Spectrograms")
```

Extend `_on_tab_changed()` to refresh inventory on first activation:

```python
    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if widget is self.dbedit_tab and self.dbedit_tab.table_list.count() == 0:
            self.dbedit_tab.load_tables()
        if widget is self.spectrogram_tab and self.spectrogram_tab._folders:
            self.spectrogram_tab._refresh_inventory()
```

---

## SPEC-06: Setup Tab — SoX Status Indicator

**Files:** `gui/setup_tab.py`  
**Dependencies:** SPEC-01 through SPEC-03

In `gui/setup_tab.py`, add a SoX status row to the Database group or as a standalone
row near the top of `_build_ui()`. This gives users immediate feedback on whether SoX
is ready before they navigate to the Spectrograms tab.

```python
        # SoX availability indicator
        sox_row = QHBoxLayout()
        sox_row.addWidget(QLabel("SoX:"))
        self.sox_status_label = QLabel("Checking…")
        sox_row.addWidget(self.sox_status_label)
        self.sox_check_btn = QPushButton("Re-check")
        self.sox_check_btn.setFixedWidth(80)
        self.sox_check_btn.clicked.connect(self._check_sox)
        sox_row.addWidget(self.sox_check_btn)
        sox_row.addStretch()
        layout.addLayout(sox_row)   # or db_layout.addLayout if inside the DB group
```

Add `_check_sox()` slot and trigger on tab show:

```python
    def _check_sox(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/spectrogram/check",
                timeout=8,
            ).json()
            if r.get("sox_available"):
                ver = r.get("sox_version", "")
                ff  = "  ffmpeg: OK" if r.get("ffmpeg_available") else \
                      "  ffmpeg: not found (SHN/APE/WV unsupported)"
                self.sox_status_label.setText(
                    f"OK — {ver}{ff}"
                )
                self.sox_status_label.setStyleSheet("color: green;")
            else:
                self.sox_status_label.setText(
                    "Not found — install: sudo apt install sox libsox-fmt-all"
                )
                self.sox_status_label.setStyleSheet("color: red;")
        except Exception as e:
            self.sox_status_label.setText(f"Error: {e}")
```

Trigger `_check_sox()` once when the Setup tab first becomes visible. In
`gui/main_window.py` `_on_tab_changed()`:

```python
        if widget is self.setup_tab and not getattr(self.setup_tab, '_sox_checked', False):
            self.setup_tab._sox_checked = True
            self.setup_tab._check_sox()
```

---

## APPENDIX: Implementation Order

```
SPEC-01  (sox_utils.py — all other SPEC tasks depend on it)
SPEC-02  (generate_spectrogram — depends on SPEC-01)
SPEC-03  (API routes — depends on SPEC-01, SPEC-02)
SPEC-04  (GUI tab — depends on SPEC-03; platform_utils.py exists,
          url_to_local_path exists, WIN-17 drop pattern already applied)
SPEC-05  (register tab — after SPEC-04)
SPEC-06  (Setup tab indicator — after SPEC-03)
```

---

## APPENDIX: SoX Spectrogram Command Reference

Full annotated command for one FLAC file:

```
sox  input.flac  -n  remix -  rate 44100  spectrogram
     │            │   │        │           │
     input        │   mix all  normalise   effect
                  null channels rate
                  output to mono

spectrogram flags:
  -x 1500       width in pixels  (time axis)
                per-song (5–10 min): 1500 → ~2.5–5px/sec | 3000 → ~5–10px/sec
  -y 513        height in pixels (freq axis — must be odd; 513 = 256 FFT bins)
  -z 120        dynamic range dB (120 = standard lossless reference)
  -w Kaiser     window function  (Kaiser: best spectral leakage suppression)
  -t "title"    title text rendered in image header
  -o out.png    output PNG path
```

**Height guide:**

| Height | FFT bins | Frequency resolution |
|--------|----------|---------------------|
| 257    | 128      | ~86 Hz/bin at 44.1kHz — fast, coarse |
| 513    | 256      | ~43 Hz/bin — standard, good for artifact detection |
| 1025   | 512      | ~22 Hz/bin — high detail, slow |

513 is the recommended default. For 96kHz recordings, 1025 is more useful to
resolve content above 22kHz.

**Width guide — per-song files (5–10 min each):**

| Width | px/sec for 5-min track | px/sec for 10-min track | Use case |
|-------|----------------------|------------------------|---------|
| 600   | ~2px/sec             | ~1px/sec               | Quick overview, small files |
| 1500  | ~5px/sec             | ~2.5px/sec             | **Default — good balance** |
| 3000  | ~10px/sec            | ~5px/sec               | High detail, artifact inspection |
| 4500  | ~15px/sec            | ~7.5px/sec             | Maximum detail for short tracks |

1500px is the recommended default for per-song files. Use 3000px when closely
inspecting for subtle artifacts. The API accepts up to 9000px.

**Disk space at 24–96 files per folder:**

| Width | Approx PNG size per track | 48 files | 96 files |
|-------|--------------------------|---------|---------|
| 1500  | ~150–400 KB              | ~15 MB  | ~30 MB  |
| 3000  | ~300–800 KB              | ~30 MB  | ~60 MB  |

**Artifact signatures to look for:**

- **High-frequency cutoff** (hard horizontal line at 16kHz, 18kHz, 20kHz): strong
  indicator of MP3/AAC re-encode. Lossless originals should extend to 22kHz.
- **Noise floor plateau**: lossy codecs introduce a raised, uniform noise floor
  across all frequencies. Lossless from analogue sources show frequency-dependent
  noise.
- **Smeared transients**: vertical (transient) features appear blurred in
  heavily compressed audio.
- **Frequency "stripes"**: some codec artefacts produce periodic horizontal
  banding, especially in low-bitrate encodes.

---

## APPENDIX: Cross-Platform Notes

**All platforms:**
- `backend/sox_utils.py` uses `_no_window()` on all subprocess calls — no console
  windows on Windows.
- WSL detection mirrors the pattern in WIN-08 (`wsl which sox`).
- Non-native formats use convert-to-temp-WAV: ffmpeg decodes to a temp file,
  SoX reads it, temp file is deleted. No pipes, no `Popen` stdin chaining.
  This eliminates the WSL cross-process pipe reliability issues entirely.

**Windows — PATH note:**
- SoX for Windows must be added to the system PATH by the user. The installer does not
  do this automatically. The Setup tab check (`/api/spectrogram/check`) will show
  "Not found" if this step is missed. Include this in the help text of the status label.
- ffmpeg for Windows must similarly be on the PATH. The Setup tab check reports
  `ffmpeg_available` separately. Without ffmpeg, only .flac/.wav/.aif files will
  be processed; SHN and other formats will show a `ConversionError` with install guidance.

**Windows — libpng:**
- The Windows SoX binary from sox.sourceforge.net includes libpng. If SoX runs but
  produces no PNG (exit 0, file missing), the user likely has a stripped build without
  libpng. The error message in `generate_spectrogram()` covers this case explicitly.

**macOS:**
- `brew install sox` includes libpng. No special handling needed.

**Linux (Debian/Ubuntu):**
- `sox` package alone does not include FLAC support. User must install
  `libsox-fmt-all`. The Setup tab check runs `sox --version` which will succeed even
  without FLAC format support; if FLAC generation fails, SoX exits non-zero with
  "no handler for file extension" — this surfaces as a `SpectrogenError` with the
  raw SoX message, which is sufficient to diagnose the missing format package.

---

## APPENDIX: Testing Checklist

- [ ] `GET /api/spectrogram/check` returns `sox_available: true` when SoX is in PATH
- [ ] `POST /api/spectrogram/generate` with a folder of 3 FLAC files creates
  `spectrograms/` directory with 3 PNG files
- [ ] `spectrograms/` is created inside the recording folder, not next to it
- [ ] PNG filenames match audio stems: `track01.flac` → `spectrograms/track01.png`
- [ ] Stereo FLAC produces a single PNG (not two)
- [ ] Re-running without `force: true` skips existing PNGs (progress shows "skipped")
- [ ] Re-running with `force: true` overwrites existing PNGs
- [ ] Stop button halts generation after the current file finishes
- [ ] Clicking a track with a PNG loads it in the right panel
- [ ] Tracks without a PNG show a salmon background in the track list
- [ ] Clicking a salmon track shows "No spectrogram yet" — not a crash
- [ ] Ctrl+scroll zooms the spectrogram image
- [ ] Double-click resets to fit-width
- [ ] Right-click → "Generate This File Only" generates one PNG and refreshes the list
- [ ] "Export PNG Externally" opens the file in the system image viewer
- [ ] "Open Folder" opens the `spectrograms/` directory
- [ ] A folder containing only SHN files with ffmpeg absent shows a
  `ConversionError` per file with an install instruction — not a crash
- [ ] A SHN file with ffmpeg present: a temp WAV appears in the OS temp dir
  during generation, then is deleted — it is NOT in the recording folder
- [ ] After generation of SHN/APE/WV files, no WAV files exist anywhere in
  the recording folder — only the PNG in spectrograms/
- [ ] Interrupting generation mid-file (Stop button) does not leave orphan
  temp WAVs in the OS temp dir (the finally block runs on clean stop)
- [ ] On Windows: no console windows appear during generation
- [ ] Drag a folder from Explorer onto the folder list — it is added without crashing
  (WIN-17 fix applied)
