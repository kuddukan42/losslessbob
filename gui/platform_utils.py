"""Cross-platform file/folder/URL opener utilities."""
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


def open_folder(path: str | Path) -> None:
    """Open a folder in the system file manager."""
    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.run(["open", p], check=False)
    else:
        subprocess.run(["xdg-open", p], check=False)


def open_file(path: str | Path) -> None:
    """Open a file with its default application."""
    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.run(["open", p], check=False)
    else:
        subprocess.run(["xdg-open", p], check=False)


def open_url(url: str) -> None:
    """Open a URL in the default browser."""
    webbrowser.open(url)


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


def url_to_local_path(url) -> Path:
    """Convert a QUrl from a drag-drop event to a correct local Path.

    Fixes Qt6 on Windows returning '/C:/Users/...' with a spurious leading slash.
    """
    local = url.toLocalFile()
    if sys.platform == "win32":
        import re
        local = re.sub(r'^/([A-Za-z]:)', r'\1', local)
    return Path(local)
