"""Cross-platform file/folder/URL opener utilities."""
import os
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


def url_to_local_path(url) -> Path:
    """Convert a QUrl from a drag-drop event to a correct local Path.

    Fixes Qt6 on Windows returning '/C:/Users/...' with a spurious leading slash.
    """
    local = url.toLocalFile()
    if sys.platform == "win32":
        import re
        local = re.sub(r'^/([A-Za-z]:)', r'\1', local)
    return Path(local)
