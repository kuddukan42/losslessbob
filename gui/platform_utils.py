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
