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

_UNSET = object()
_SOX_CMD = _UNSET
_FFMPEG_CMD = _UNSET
_FLAC_CMD = _UNSET


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


def _find_flac() -> list | None:
    """Return ['flac'] (or bundled/WSL equivalent) or None."""
    if sys.platform == "win32":
        # 1. Bundled flac in PyInstaller frozen build (_MEIPASS/tools/flac.exe)
        if getattr(sys, "frozen", False):
            bundled = Path(sys._MEIPASS) / "tools" / "flac.exe"  # type: ignore[attr-defined]
            if bundled.exists():
                return [str(bundled)]
        # 2. tools/flac.exe alongside the source tree (dev and non-frozen installs)
        _local = Path(__file__).resolve().parent.parent / "tools" / "flac.exe"
        if _local.exists():
            return [str(_local)]
        # 3. PATH
        if shutil.which("flac"):
            return ["flac"]
        # 4. WSL flac
        if shutil.which("wsl"):
            try:
                r = subprocess.run(
                    ["wsl", "which", "flac"],
                    capture_output=True, text=True, timeout=8,
                    **_no_window(),
                )
                if r.returncode == 0 and r.stdout.strip():
                    return ["wsl", "flac"]
            except Exception:
                pass
        return None
    return ["flac"] if shutil.which("flac") else None


def get_flac() -> list | None:
    global _FLAC_CMD
    if _FLAC_CMD is _UNSET:
        _FLAC_CMD = _find_flac()
    return _FLAC_CMD


def get_sox() -> list | None:
    global _SOX_CMD
    if _SOX_CMD is _UNSET:
        _SOX_CMD = _find_sox()
    return _SOX_CMD


def get_ffmpeg() -> list | None:
    global _FFMPEG_CMD
    if _FFMPEG_CMD is _UNSET:
        _FFMPEG_CMD = _find_ffmpeg()
    return _FFMPEG_CMD


# ── Install hints ────────────────────────────────────────────────────────────

_INSTALL_HINTS: dict[str, dict[str, str | None]] = {
    "ffmpeg": {
        "win32":  "winget install Gyan.FFmpeg",
        "darwin": "brew install ffmpeg",
        "linux":  "sudo apt install ffmpeg",
    },
    "sox": {
        "win32":  "winget install SoX.SoX",
        "darwin": "brew install sox",
        "linux":  "sudo apt install sox libsox-fmt-all",
    },
    "flac": {
        "win32":  "winget install xiph.FLAC",
        "darwin": "brew install flac",
        "linux":  "sudo apt install flac",
    },
    "shntool": {
        "win32":  None,  # bundled in tools/shntool.exe
        "darwin": "brew install shntool",
        "linux":  "sudo apt install shntool",
    },
}


def get_install_hints() -> dict[str, str | None]:
    """Return per-tool install hint strings for the current OS platform."""
    platform_key = sys.platform if sys.platform in ("win32", "darwin") else "linux"
    return {tool: hints.get(platform_key) for tool, hints in _INSTALL_HINTS.items()}


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
        _ffmpeg_hints = {
            "win32":  "winget install Gyan.FFmpeg  (or https://ffmpeg.org/download.html)",
            "darwin": "brew install ffmpeg",
        }
        install_hint = _ffmpeg_hints.get(sys.platform, "sudo apt install ffmpeg")
        raise ConversionError(
            f"Format {audio_path.suffix!r} requires ffmpeg for decoding, "
            "but ffmpeg was not found.\n"
            f"Install with: {install_hint}\n\n"
            "Alternatively, convert the file to FLAC or WAV manually and "
            "re-run the spectrogram generator."
        )

    # Create temp file — mkstemp returns (fd, path), close fd immediately.
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
        ) from None

    if r.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        msg = (r.stderr or r.stdout or "").strip()
        raise ConversionError(
            f"ffmpeg failed on {audio_path.name} (exit {r.returncode}): {msg}"
        )

    return tmp_path


def decode_to_wav(audio_path: Path) -> Path:
    """Decode any supported audio file to a temporary WAV. Caller must delete."""
    return _convert_to_wav(audio_path)


# ── Spectrogram generation ────────────────────────────────────────────────────

def generate_spectrogram(
    audio_path: Path,
    output_png:  Path,
    width:     int = 1500,
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
        height:     PNG height in pixels (frequency axis). Must be odd.
                    513 → 256 FFT bins, covers 0–22 kHz at 44.1kHz.
        dyn_range:  Colour scale range in dB. 120 = standard lossless reference.
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
        _sox_hints = {
            "win32":  "winget install SoX.SoX  (or https://sox.sourceforge.net)",
            "darwin": "brew install sox",
        }
        install_hint = _sox_hints.get(sys.platform, "sudo apt install sox libsox-fmt-all")
        raise SoxNotFoundError(f"SoX not found. Install with: {install_hint}")

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if height % 2 == 0:
        height += 1

    title = title or audio_path.name
    ext   = audio_path.suffix.lower()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    sox_input: Path = audio_path
    tmp_wav:   Path | None = None

    if ext in _NEEDS_CONVERSION:
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
    """Run SoX spectrogram on input_wav, write output_png."""
    use_wsl = _is_wsl_sox()

    def _p(path: Path) -> str:
        return _to_wsl_path(path) if use_wsl else str(path)

    cmd = (
        sox
        + [_p(input_wav), "-n",
           "remix", "-",        # mix all channels to mono
           "rate", "44100",     # normalise to 44.1kHz for consistent px/sec scale
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
        ) from None

    if r.returncode != 0:
        raise SpectrogenError(
            f"SoX failed (exit {r.returncode}): {(r.stderr or '').strip()}"
        )

    if not output_png.exists():
        _png_hints = {
            "win32":  "reinstall SoX from https://sox.sourceforge.net (ensure the installer includes libpng)",
            "darwin": "brew reinstall sox",
        }
        png_hint = _png_hints.get(sys.platform, "sudo apt install sox libsox-fmt-all")
        raise SpectrogenError(
            f"SoX exited 0 but {output_png.name} was not created. "
            f"Ensure SoX was compiled with PNG support (libpng). Fix: {png_hint}"
        )
