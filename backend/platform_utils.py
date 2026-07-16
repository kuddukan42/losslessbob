"""Cross-platform process helpers used by the Flask backend.

Migrated from the removed legacy GUI package (gui/platform_utils.py); the
Qt-dependent helpers were dropped with the PyQt6 GUI.
"""
import shutil
import subprocess
import sys
from pathlib import Path


def _subprocess_flags() -> dict:
    """Return kwargs to suppress console windows on Windows. No-op on other platforms."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def open_in_vlc(paths: list[str | Path]) -> tuple[bool, str]:
    """Launch VLC with one or more folder/file paths as a playlist.

    Returns (True, '') on success, or (False, error_message) when VLC is not found
    or the subprocess fails to start.
    """
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        vlc = next((c for c in candidates if Path(c).is_file()), shutil.which("vlc"))
    elif sys.platform == "darwin":
        mac_vlc = "/Applications/VLC.app/Contents/MacOS/VLC"
        vlc = mac_vlc if Path(mac_vlc).is_file() else shutil.which("vlc")
    else:
        vlc = shutil.which("vlc")

    if not vlc:
        return False, (
            "VLC media player was not found.\n\n"
            "Install VLC and ensure it is on your PATH, then try again."
        )

    str_paths = [str(p) for p in paths]
    try:
        subprocess.Popen([vlc] + str_paths, **_subprocess_flags())
        return True, ""
    except Exception as exc:
        return False, str(exc)
