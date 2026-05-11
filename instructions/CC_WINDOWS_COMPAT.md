# LosslessBob — Windows Compatibility & Cross-Platform Parity
# Claude Code Instructions

**Baseline:** Everything works on Linux. Windows build is buggy.  
**Read `PROJECT.md` and `CC_INSTRUCTIONS.md` for full architecture context.**  
**Complete WIN-01 and WIN-02 first — all other tasks depend on correct path resolution and Flask readiness.**

---

## BUGS FOUND (by severity)

| ID | Severity | Location | Issue |
|----|----------|----------|-------|
| WIN-01 | Critical | `backend/db.py`, all backends | `__file__`-relative paths break in PyInstaller frozen builds |
| WIN-02 | Critical | `main.py` | `time.sleep(0.5)` Flask startup — too short on Windows, GUI hits dead port |
| WIN-03 | Critical | `gui/collection_tab.py:792` | `xdg-open` hardcoded — crashes on Windows with no platform branch |
| WIN-04 | Critical | `backend/db.py` | `sqlite3.connect()` has no `timeout` — instant `database is locked` on Windows under concurrent access |
| WIN-05 | Critical | `backend/checksum_utils.py:176` | `subprocess.run(['shntool',...])` pops a console window on Windows for every file verified |
| WIN-06 | High | `main.py` | Flask dev server on Windows has port-release bugs on restart — need Waitress |
| WIN-07 | High | `gui/rename_tab.py:310` | `shutil.move()` raises `PermissionError` on Windows when Explorer has the folder focused |
| WIN-08 | High | `backend/checksum_utils.py` | `shntool` unavailable on Windows — SHN folders silently report `INCOMPLETE` with no user guidance |
| WIN-09 | Medium | all file I/O | Windows paths >260 chars fail silently — no long-path guard |
| WIN-10 | Medium | `gui/styles.py` | `font-family: Segoe UI` is Windows-only — falls back to Arial on Linux but causes layout differences |
| WIN-11 | Low | `gui/main_window.py` | `QSettings(APP_NAME, APP_NAME)` writes to Windows registry — should use INI for portability |

---

## WIN-01: Unified Path Resolution for Frozen Executables

**Files:** `backend/paths.py` (new), `backend/db.py`, `backend/app.py`, `backend/scraper.py`, `backend/scheduler.py`, `backend/importer.py`, `gui/setup_tab.py`  
**Dependencies:** None — do this first  
**New packages:** None

**Problem:** Every backend module computes `DATA_DIR` as `Path(__file__).parent.parent / "data"`. When PyInstaller bundles the app on Windows, `__file__` resolves to a temp extraction directory (`_MEIPASS`), not the executable's directory. The `data/` folder is sibling to the `.exe`, so `Path(__file__).parent.parent` points to the wrong place.

**Steps:**

1. Create `backend/paths.py`:

```python
"""
Central path resolver for LosslessBob.
Handles three execution contexts:
  - Normal Python:      data/ is sibling to project root
  - PyInstaller frozen: data/ is sibling to the .exe
  - Portable ZIP:       data/ is sibling to the .exe
"""
import sys
from pathlib import Path


def _app_root() -> Path:
    """Return the directory that contains the data/ folder."""
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys.frozen = True and sys.executable = path to .exe
        return Path(sys.executable).parent
    # Normal Python: project root is two levels above this file
    return Path(__file__).parent.parent


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "data"
DB_PATH = DATA_DIR / "losslessbob.db"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
PAGES_DIR = DATA_DIR / "pages"
LOG_FILE = DATA_DIR / "scraper.log"
TOOLS_DIR = APP_ROOT / "tools"


def ensure_data_dirs():
    """Create data subdirectories if they do not exist."""
    for d in (DATA_DIR, ATTACHMENTS_DIR, PAGES_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

2. In `backend/db.py`, replace:
```python
DB_PATH = Path(__file__).parent.parent / "data" / "losslessbob.db"
```
With:
```python
from backend.paths import DB_PATH  # noqa: F401  (re-exported for callers that import from db)
```

3. In `backend/app.py`, replace:
```python
DATA_DIR = Path(__file__).parent.parent / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
```
With:
```python
from backend.paths import DATA_DIR, ATTACHMENTS_DIR
```

4. In `backend/scraper.py`, replace:
```python
DATA_DIR = Path(__file__).parent.parent / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
PAGES_DIR = DATA_DIR / "pages"
```
With:
```python
from backend.paths import DATA_DIR, ATTACHMENTS_DIR, PAGES_DIR
```

5. In `backend/scheduler.py`, replace:
```python
DATA_DIR = Path(__file__).parent.parent / "data"
```
With:
```python
from backend.paths import DATA_DIR
```

6. In `backend/importer.py`, replace:
```python
DATA_DIR = Path(__file__).parent.parent / "data"
```
With:
```python
from backend.paths import DATA_DIR
```

7. In `gui/setup_tab.py`, replace:
```python
_LOG_FILE = Path(__file__).parent.parent / "data" / "scraper.log"
```
With:
```python
from backend.paths import LOG_FILE as _LOG_FILE
```

8. In `main.py`, add a call to `ensure_data_dirs()` before Flask starts:
```python
from backend.paths import ensure_data_dirs
ensure_data_dirs()
```

**Done when:** App finds `losslessbob.db` correctly when launched as `dist/LosslessBob.exe` from a PyInstaller build, and when launched as `python main.py` from the project root.

---

## WIN-02: Flask Readiness Poll (Replace `time.sleep`)

**Files:** `main.py`  
**Dependencies:** WIN-01  
**New packages:** None

**Problem:** `time.sleep(0.5)` is a fixed delay. On Windows, Flask + socket binding takes 1–3 seconds on first launch (Windows Defender scan, socket setup). GUI starts, immediately fires the status bar refresh timer, gets `ConnectionRefusedError`, and shows error state. On fast Linux machines 0.5s is fine; on Windows it often isn't.

**Steps:**

Replace the `start_flask` / startup block in `main.py` with:

```python
import sys
import socket
import threading
import time

from PyQt6.QtWidgets import QApplication

from backend.app import create_app
from backend.paths import ensure_data_dirs

FLASK_PORT = 5174
_FLASK_READY = threading.Event()


def _wait_for_port(host, port, timeout=15.0):
    """Block until TCP port accepts connections or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_flask():
    import sys
    ensure_data_dirs()
    flask_app = create_app()

    # Use Waitress on Windows for production-grade stability;
    # fall back to Flask dev server on Linux/macOS.
    if sys.platform == "win32":
        try:
            from waitress import serve as waitress_serve
            _FLASK_READY.set()  # Waitress blocks, set before serving
            waitress_serve(flask_app, host="127.0.0.1", port=FLASK_PORT,
                           threads=8, channel_timeout=120)
        except ImportError:
            flask_app.run(host="127.0.0.1", port=FLASK_PORT,
                          debug=False, use_reloader=False)
    else:
        flask_app.run(host="127.0.0.1", port=FLASK_PORT,
                      debug=False, use_reloader=False)


def main():
    ignore_pos = "-ignore_start_positions" in sys.argv

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Wait for Flask to actually accept connections (up to 15 seconds)
    if not _wait_for_port("127.0.0.1", FLASK_PORT, timeout=15.0):
        # Flask did not start — show a fatal error without hanging
        app = QApplication(sys.argv)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Startup Error",
                             f"Flask backend did not start on port {FLASK_PORT}.\n"
                             "Another process may be using that port.\n"
                             "Try restarting the application.")
        sys.exit(1)

    from gui.main_window import MainWindow
    import gui.styles as styles

    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("LosslessBob Checksum Lookup")

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    window.show()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
```

**Note:** The `from gui.main_window import MainWindow` import is moved inside `main()` intentionally — on Windows with PyInstaller, top-level GUI imports before `QApplication` creation can trigger DPI scaling issues.

**Done when:** App starts correctly on Windows even when it takes 2+ seconds for Flask to bind. Fatal error dialog appears if port 5174 is occupied.

---

## WIN-03: Fix `xdg-open` in `collection_tab.py`

**Files:** `gui/collection_tab.py`  
**Dependencies:** None  
**New packages:** None

**Problem:** Line 792 unconditionally calls `subprocess.Popen(["xdg-open", path])`. On Windows, `xdg-open` does not exist — this raises `FileNotFoundError` and the folder never opens. `attachments_tab.py` and `setup_tab.py` already have correct platform branches; `collection_tab.py` was missed.

**Steps:**

1. Create a shared platform-open utility. Add a new file `gui/platform_utils.py`:

```python
"""
Cross-platform file/folder/URL opener utilities.
Centralises the sys.platform branching that was scattered across GUI files.
"""
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
```

2. In `gui/collection_tab.py`, replace the `_open_folders` method:

```python
    def _open_folders(self, rows):
        from gui.platform_utils import open_folder
        for row in rows:
            path = row.get("disk_path", "")
            if path and Path(path).is_dir():
                try:
                    open_folder(path)
                except Exception:
                    pass
```

3. In `gui/attachments_tab.py`, replace the platform-open block (around line 206–212) with:

```python
        from gui.platform_utils import open_file
        try:
            open_file(self._current_file)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Open Failed", str(e))
```

4. In `gui/setup_tab.py`, replace both platform-open blocks (around lines 454–459 and 509–514) with calls to `open_folder` and `open_file` from `gui.platform_utils`.

**Done when:** Right-clicking a collection row and selecting "Open Folder" opens Windows Explorer on Windows, Nautilus/Thunar on Linux.

---

## WIN-04: SQLite Connection Timeout + `check_same_thread`

**Files:** `backend/db.py`  
**Dependencies:** None (or apply after DB-01/DB-02 from `CC_INSTRUCTIONS.md`)  
**New packages:** None

**Problem:** On Windows, SQLite's file-locking uses `LockFileEx` which is more aggressive than Linux's advisory locks. Without a `timeout`, any write contention raises `OperationalError: database is locked` immediately instead of waiting. This affects the scraper thread (writing entries) running concurrently with GUI polling (reading stats). Also, `check_same_thread=True` (the default) will raise errors if the connection pool from DB-02 is ever used cross-thread.

**Steps:**

In `get_connection()` (current version or the pool version from DB-02), add `timeout=30` and `check_same_thread=False`:

```python
conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
```

`timeout=30` tells SQLite to retry for up to 30 seconds before raising `OperationalError`. This is safe because all write operations are short (milliseconds); 30 seconds is a generous ceiling for any real deadlock scenario.

Additionally, add a busy handler as a belt-and-suspenders measure:

```python
conn.execute("PRAGMA busy_timeout=30000")  # 30 000 ms — mirrors the connect timeout
```

Add this PRAGMA line immediately after the other PRAGMAs in `get_connection()`.

**Done when:** Running a bulk scrape (writes every 1.5 seconds) while clicking through search results (reads) produces no `OperationalError` on Windows.

---

## WIN-05: Suppress Console Windows for All Subprocess Calls

**Files:** `backend/checksum_utils.py`, `gui/platform_utils.py`  
**Dependencies:** WIN-03 (platform_utils.py must exist)  
**New packages:** None

**Problem:** On Windows, every `subprocess.run()` or `subprocess.Popen()` spawns a visible console window that flashes on screen. This affects: `shntool` calls in `checksum_utils.py`, and the `open_folder` / `open_file` calls via `subprocess` in the new `platform_utils.py`.

**Steps:**

1. Add a helper to `gui/platform_utils.py`:

```python
def _subprocess_flags() -> dict:
    """
    Returns kwargs to suppress console windows on Windows.
    No-op on other platforms.
    """
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            "startupinfo": si,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    return {}
```

2. In `backend/checksum_utils.py`, add at the top of file:

```python
import sys as _sys

def _no_window_kwargs() -> dict:
    if _sys.platform == "win32":
        import subprocess as _sp
        si = _sp.STARTUPINFO()
        si.dwFlags |= _sp.STARTF_USESHOWWINDOW
        si.wShowWindow = _sp.SW_HIDE
        return {"startupinfo": si, "creationflags": _sp.CREATE_NO_WINDOW}
    return {}
```

3. In `compute_shntool()`, change the `subprocess.run` call to:

```python
        result = subprocess.run(
            ['shntool', 'md5', str(filepath)],
            capture_output=True, text=True, timeout=120,
            **_no_window_kwargs(),
        )
```

4. In `gui/platform_utils.py`, update `open_folder` and `open_file` subprocess calls:

```python
def open_folder(path: str | Path) -> None:
    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)   # os.startfile never creates a console window
    elif sys.platform == "darwin":
        subprocess.run(["open", p], check=False)
    else:
        subprocess.run(["xdg-open", p], check=False)
```

`os.startfile` on Windows does not create any subprocess or console window, so no extra flags are needed there.

**Done when:** Verifying a folder of FLAC files on Windows produces no console window flashes.

---

## WIN-06: Use Waitress as WSGI Server on Windows

**Files:** `main.py`, `requirements.txt`  
**Dependencies:** WIN-02  
**New packages:** `waitress` (already in `requirements.txt` as optional — make it required)

**Problem:** Flask's built-in `app.run()` uses Werkzeug's single-threaded dev server on Windows. Under concurrent GUI polling + scraper writes, it queues requests or drops them. Werkzeug also fails to release port 5174 reliably on Windows process restart, causing `OSError: [WinError 10048]` on second launch. Waitress is already in `requirements.txt` but unused.

**Steps:**

1. In `requirements.txt`, move `waitress` from the optional comment section to the core section and pin it:

```
waitress==3.0.0
```

2. The `start_flask()` function in WIN-02 already conditionally uses Waitress on Windows. If WIN-02 is already applied, no additional change is needed here.

   If WIN-02 has not been applied yet, replace the `start_flask()` function in `main.py`:

```python
def start_flask():
    ensure_data_dirs()
    flask_app = create_app()
    if sys.platform == "win32":
        from waitress import serve as waitress_serve
        waitress_serve(flask_app, host="127.0.0.1", port=FLASK_PORT,
                       threads=8, channel_timeout=120)
    else:
        flask_app.run(host="127.0.0.1", port=FLASK_PORT,
                      debug=False, use_reloader=False)
```

**Done when:** Second launch of the app on Windows after closing does not produce `OSError: [WinError 10048]`.

---

## WIN-07: `shutil.move` Permission Errors in Rename Tab

**Files:** `gui/rename_tab.py`  
**Dependencies:** None  
**New packages:** None

**Problem:** On Windows, `shutil.move(src, final_dst)` raises `PermissionError` if:
- Windows Explorer has the source folder focused/selected
- Any audio player has a file in the folder open
- A virus scanner is scanning the folder at that moment

Currently the error is caught and added to `errors[]` but the message is cryptic. Also, `os.makedirs` with a path containing a trailing space or reserved Windows names (`CON`, `PRN`, `AUX`, etc.) will fail silently or raise obscure errors.

**Steps:**

1. In `rename_tab.py`, locate the rename execution block (around line 300–314). Replace the `shutil.move` call and surrounding logic:

```python
            new_name = Path(proposed_dst).name
            processed_dir = Path(src).parent / "0. Processed"
            final_dst = processed_dir / new_name

            # Guard: validate proposed name has no Windows-illegal characters
            illegal = set('<>:"/\\|?*')
            if any(c in illegal for c in new_name):
                errors.append(
                    f"{Path(src).name}: proposed name contains illegal characters"
                )
                continue

            try:
                processed_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"Cannot create '0. Processed': {e}")
                continue

            try:
                shutil.move(str(src), str(final_dst))
                renamed += 1
            except PermissionError:
                errors.append(
                    f"{Path(src).name}: Permission denied. Close any programs "
                    "that may have files in this folder open (Explorer, media player, "
                    "antivirus) and try again."
                )
            except FileExistsError:
                errors.append(
                    f"{Path(src).name}: A folder named '{new_name}' already exists "
                    "in '0. Processed'."
                )
            except OSError as e:
                errors.append(f"{Path(src).name}: {e}")
```

2. Add Windows-specific rename guidance to the error display. After the rename loop, if any `errors` contain "Permission denied", append to the error dialog message:

```python
            if any("Permission denied" in e for e in errors):
                msg += (
                    "\n\nTip (Windows): If rename fails with permission errors, "
                    "click somewhere else in Explorer to deselect the folder, "
                    "then retry."
                )
```

**Done when:** Attempting to rename a folder that Windows Explorer has selected shows a clear, actionable error message instead of a raw Python exception.

---

## WIN-08: SHN / `shntool` Feature Parity on Windows

**Files:** `backend/checksum_utils.py`, `gui/verify_tab.py`, `gui/setup_tab.py`  
**Dependencies:** None  
**New packages:** None

**Problem:** `shntool` is a Linux/macOS binary. On Windows it does not exist. Currently `shutil.which('shntool')` returns `None` and the code marks SHN folders as `INCOMPLETE` with `missing_types=['shntool']`. The user gets no guidance on how to get SHN verification working. Feature parity options:

- **Option A:** Direct the user to install `shntool` via WSL (Windows Subsystem for Linux) and invoke it via `wsl shntool`.
- **Option B:** Document that SHN verification requires WSL and provide a detection path.
- **Option C (recommended):** Auto-detect WSL `shntool` on Windows, fall back gracefully.

**Steps:**

1. In `backend/checksum_utils.py`, replace the `compute_shntool()` function with one that auto-detects WSL on Windows:

```python
def _find_shntool() -> list[str] | None:
    """
    Return the command prefix to invoke shntool, or None if unavailable.
    - Linux/macOS: ['shntool'] if in PATH
    - Windows: ['wsl', 'shntool'] if WSL is available and shntool is installed in WSL
    """
    import sys
    if sys.platform == "win32":
        if shutil.which("wsl"):
            # Check if shntool is available inside WSL
            try:
                r = subprocess.run(
                    ["wsl", "which", "shntool"],
                    capture_output=True, text=True, timeout=10,
                    **_no_window_kwargs(),
                )
                if r.returncode == 0 and r.stdout.strip():
                    return ["wsl", "shntool"]
            except Exception:
                pass
        return None
    # Linux/macOS
    if shutil.which("shntool"):
        return ["shntool"]
    return None


# Module-level cache — checked once per process
_SHNTOOL_CMD: list[str] | None | object = object()  # sentinel = not yet checked


def _get_shntool_cmd() -> list[str] | None:
    global _SHNTOOL_CMD
    if _SHNTOOL_CMD is object or isinstance(_SHNTOOL_CMD, type(object())):
        _SHNTOOL_CMD = _find_shntool()
    return _SHNTOOL_CMD


def compute_shntool(filepath):
    """
    Run shntool md5 <filepath>, return decoded audio hash.
    On Windows, attempts to use WSL shntool if native is unavailable.
    Raises ShntoolNotFoundError if no shntool found by any method.
    """
    cmd = _get_shntool_cmd()
    if cmd is None:
        raise ShntoolNotFoundError(
            "shntool not found. "
            "On Windows: install WSL (wsl --install) then run: "
            "wsl sudo apt install shntool"
        )

    # On Windows via WSL, convert Windows path to WSL path
    import sys
    invoke_path = str(filepath)
    if sys.platform == "win32" and cmd[0] == "wsl":
        # Convert C:\path\to\file -> /mnt/c/path/to/file
        p = Path(filepath).resolve()
        drive = p.drive.rstrip(":").lower()
        rest = str(p)[len(p.drive):].replace("\\", "/")
        invoke_path = f"/mnt/{drive}{rest}"

    try:
        result = subprocess.run(
            cmd + ['md5', invoke_path],
            capture_output=True, text=True, timeout=120,
            **_no_window_kwargs(),
        )
        for line in result.stdout.splitlines():
            if '[shntool]' in line:
                parts = line.split()
                if parts:
                    return parts[0].lower()
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
```

2. Replace every `shutil.which('shntool')` check in `checksum_utils.py` (there are 3 occurrences in `verify_folder`, `verify_folder_lbdir`, and `generate_checksums`) with `_get_shntool_cmd() is not None`.

3. In `gui/verify_tab.py`, update the status message for `shntool_missing` to include Windows-specific instructions. In `_on_verify_done()`, change:

```python
        if any(r.get("status") == "shntool_missing" for r in results):
            msg += "\nshntool not found — install with: sudo apt install shntool"
```
To:
```python
        if any(r.get("status") == "shntool_missing" for r in results):
            import sys
            if sys.platform == "win32":
                msg += (
                    "\nshntool not found on Windows. Options:\n"
                    "  1. Install WSL: wsl --install (then: wsl sudo apt install shntool)\n"
                    "  2. SHN MD5 checksums can still be verified; only shntool hashes require it."
                )
            else:
                msg += "\nshntool not found — install with: sudo apt install shntool"
```

**Done when:** On Windows with WSL+shntool installed, SHN verification runs correctly. Without WSL, the error message gives actionable instructions instead of a bare "INCOMPLETE".

---

## WIN-09: Long Path Support (>260 Characters)

**Files:** `backend/paths.py`, `backend/checksum_utils.py`, `backend/scraper.py`  
**Dependencies:** WIN-01  
**New packages:** None

**Problem:** Windows has a 260-character `MAX_PATH` limit by default. Collectors with deeply nested folder structures hit this when opening files, writing checksum files, or when SQLite opens the DB path. Python's `pathlib` on Windows raises `FileNotFoundError` or silently truncates on paths > 260 chars unless the `\\?\` long-path prefix is used.

**Steps:**

1. Add a helper to `backend/paths.py`:

```python
import sys as _sys


def to_long_path(p: Path) -> Path:
    """
    On Windows, prefix path with \\?\\ to enable paths longer than MAX_PATH (260).
    No-op on Linux/macOS. Only applies to absolute paths.
    Requires Windows 10 1607+ or enabling long paths via Group Policy / registry.
    """
    if _sys.platform != "win32":
        return p
    p = p.resolve()
    s = str(p)
    if s.startswith("\\\\?\\"):
        return p  # Already prefixed
    if s.startswith("\\\\"):
        # UNC path: \\server\share -> \\?\UNC\server\share
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)
```

2. In `backend/checksum_utils.py`, in `compute_md5()` and `compute_ffp()`, wrap the file open:

```python
from backend.paths import to_long_path

def compute_md5(filepath):
    try:
        h = hashlib.md5()
        with open(to_long_path(Path(filepath)), 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, OSError):
        return None
```

Apply the same `to_long_path()` wrap to `compute_ffp()`.

3. In `backend/scraper.py`, when constructing `lb_dir` and `local_path` for attachment downloads, wrap with `to_long_path()` before `open()` calls.

4. In `backend/db.py`, wrap `DB_PATH` before passing to `sqlite3.connect()`:

```python
from backend.paths import to_long_path

def get_connection(db_path=None):
    path = to_long_path(Path(db_path or DB_PATH))
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    ...
```

5. Add a check in `backend/paths.py` `ensure_data_dirs()` that warns if the data path exceeds 200 characters (leaving headroom for filenames):

```python
def ensure_data_dirs():
    for d in (DATA_DIR, ATTACHMENTS_DIR, PAGES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    import sys
    if sys.platform == "win32" and len(str(DATA_DIR)) > 200:
        import warnings
        warnings.warn(
            f"Data directory path is {len(str(DATA_DIR))} characters. "
            "Windows MAX_PATH is 260. Consider moving the app closer to a drive root.",
            stacklevel=2,
        )
```

**Done when:** App opens and verifies files in a folder whose full path is 280 characters long on Windows.

---

## WIN-10: Cross-Platform Font Stack

**Files:** `gui/styles.py`  
**Dependencies:** None  
**New packages:** None

**Problem:** The stylesheet hardcodes `font-family: Segoe UI, Arial, sans-serif`. `Segoe UI` is a Windows font. On Linux it falls back to `Arial` if installed, or to the generic `sans-serif`. This causes minor layout differences: Segoe UI is proportionally narrower than common Linux sans-serif fonts, so labels and buttons sized for Segoe UI may clip text on Linux.

**Steps:**

1. In `build_stylesheet()` in `styles.py`, replace the hardcoded font-family line with a platform-aware font stack. Add this helper at the top of `styles.py`:

```python
import sys as _sys

def _platform_font_stack() -> str:
    if _sys.platform == "win32":
        return "Segoe UI, Arial, sans-serif"
    elif _sys.platform == "darwin":
        return "-apple-system, Helvetica Neue, Arial, sans-serif"
    else:
        # Linux: prefer system UI fonts
        return "Ubuntu, Cantarell, DejaVu Sans, Arial, sans-serif"
```

2. In `build_stylesheet(t)`, replace:
```python
    font-family: Segoe UI, Arial, sans-serif;
```
With:
```python
    font-family: {_platform_font_stack()};
```

**Done when:** Font renders using the platform's native UI font on each OS.

---

## WIN-11: Portable Settings (INI Instead of Registry)

**Files:** `gui/main_window.py`  
**Dependencies:** WIN-01  
**New packages:** None

**Problem:** `QSettings(APP_NAME, APP_NAME)` on Windows stores geometry and preferences in the registry (`HKEY_CURRENT_USER\Software\LosslessBobLookup`). This means:
- Settings are not preserved if the user copies the app folder to another machine
- Settings survive uninstalls, leaving registry debris
- Portable USB installs retain no settings

**Steps:**

1. In `gui/main_window.py`, replace:
```python
self._settings = QSettings(APP_NAME, APP_NAME)
```
With:
```python
from backend.paths import DATA_DIR
from PyQt6.QtCore import QSettings
_settings_path = str(DATA_DIR / "settings.ini")
self._settings = QSettings(_settings_path, QSettings.Format.IniFormat)
```

2. Do the same for any other `QSettings` instantiation in the codebase. Search all files:
```bash
grep -rn "QSettings(" gui/
```
Apply the same replacement to every occurrence.

**Note:** This migration invalidates any existing registry-stored geometry. On first launch after this change, windows will open at default size. This is acceptable — document it in `CHANGELOG.md`.

**Done when:** Window geometry is stored in `data/settings.ini` as a plain text INI file. Copying the entire app folder preserves settings.

---

## WIN-12: PyInstaller Spec File for Windows Build

**Files:** `LosslessBob.spec` (new), `tools/build_windows.bat` (new)  
**Dependencies:** WIN-01, WIN-02, WIN-03  
**New packages:** `pyinstaller` (build-time only, not in runtime requirements)

**Problem:** No Windows build configuration exists. A proper `.spec` file is needed to:
- Include the `data/` directory
- Bundle the `tools/` directory (for `ExportSqlCE40.exe` if used)
- Set the Windows app icon
- Avoid including development dependencies
- Suppress the console window (`console=False`)

**Steps:**

1. Create `LosslessBob.spec` in the project root:

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('tools', 'tools'),         # Include ExportSqlCE40.exe
    ],
    hiddenimports=[
        'waitress',
        'waitress.task',
        'waitress.server',
        'lxml.etree',
        'lxml._elementpath',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', 'black', 'mypy', 'pylint',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LosslessBob',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='tools/icon.ico',  # Uncomment when icon exists
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LosslessBob',
)
```

2. Create `tools/build_windows.bat`:

```batch
@echo off
REM Build LosslessBob for Windows
REM Run from the project root: tools\build_windows.bat

echo Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
pyinstaller LosslessBob.spec

echo.
echo Build complete: dist\LosslessBob\LosslessBob.exe
echo.
echo Post-build: create data\ folder next to the .exe if it does not exist.
if not exist dist\LosslessBob\data mkdir dist\LosslessBob\data

pause
```

3. After building, verify that `dist/LosslessBob/LosslessBob.exe` launches without a console window and finds its `data/` directory correctly.

**Done when:** `tools\build_windows.bat` produces a runnable `dist/LosslessBob/LosslessBob.exe` that starts correctly on a clean Windows machine with no Python installed.

---

## WIN-13: Watchdog Observer — Windows-Specific Backend

**Files:** `backend/scheduler.py`  
**Dependencies:** WIN-01  
**New packages:** None (Watchdog supports Windows via `ReadDirectoryChangesW`)

**Problem:** The default Watchdog `Observer` on Windows uses `ReadDirectoryChangesW`. Unlike Linux `inotify`, it fires events for SQLite WAL files (`.db-shm`, `.db-wal`) and Windows thumbnail cache files (`Thumbs.db`, `desktop.ini`). These are not `.txt` files so the current filter handles them, but `_pending` dict cleanup never runs (the delayed thread leaves stale keys), creating a memory leak on long-running sessions.

**Steps:**

1. In `backend/scheduler.py`, replace the `FileEventHandler._handle()` method to clean up `_pending` after processing:

```python
    def _handle(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".txt":
            return
        # Skip system/hidden files on Windows
        name = path.name
        if name.startswith('.') or name.lower() in ('thumbs.db', 'desktop.ini'):
            return

        key = str(path)
        if key in self._pending:
            return
        self._pending[key] = True

        def delayed():
            try:
                time.sleep(2)
                stored_hash = get_meta("import_hash", self.db_path)
                try:
                    current_hash = md5_file(path)
                except Exception:
                    return
                if current_hash == stored_hash:
                    return
                _notify(f"New data file detected: {path.name}. Starting import...")

                def do_import():
                    try:
                        result = run_import(path, progress_callback=_notify,
                                            db_path=self.db_path)
                        if result.get("skipped"):
                            _notify("Import skipped (no changes).")
                        else:
                            _notify(f"Import complete: {result['new_lb_count']} new LB entries.")
                    except Exception as e:
                        _notify(f"Import error: {e}")

                t = threading.Thread(target=do_import, daemon=True)
                t.start()
            finally:
                # Always clean up the pending key
                self._pending.pop(key, None)

        t = threading.Thread(target=delayed, daemon=True)
        t.start()
```

2. Use the Watchdog `WindowsApiObserver` explicitly on Windows for better reliability. In `start_file_watcher()`:

```python
def start_file_watcher(db_path=None):
    global _observer
    if _observer and _observer.is_alive():
        return
    import sys
    handler = FileEventHandler(db_path=db_path)
    if sys.platform == "win32":
        try:
            from watchdog.observers.winapi import WindowsApiObserver
            _observer = WindowsApiObserver()
        except ImportError:
            from watchdog.observers import Observer
            _observer = Observer()
    else:
        from watchdog.observers import Observer
        _observer = Observer()
    _observer.schedule(handler, str(DATA_DIR), recursive=False)
    _observer.daemon = True
    _observer.start()
```

**Done when:** App runs for 30+ minutes on Windows without increasing memory usage from the scheduler. Dropping a flat file into `data/` triggers auto-import correctly.

---

---

## WIN-14: Fix Drag and Drop on Windows (`toLocalFile` Leading Slash Bug)

**Files:** `gui/platform_utils.py`, `gui/lookup_tab.py`, `gui/verify_tab.py`, `gui/lbdir_tab.py`  
**Dependencies:** WIN-03 (platform_utils.py must exist)  
**New packages:** None

**Problem:** Qt6 on Windows returns paths from `QUrl.toLocalFile()` with a spurious leading slash: `/C:/Users/Bob/Music` instead of `C:/Users/Bob/Music`. On Linux this string is a valid absolute path and works. On Windows, `Path("/C:/Users/Bob/Music")` resolves relative to the current drive root — it becomes `\C:\Users\Bob\Music` (a path that does not exist). Consequently `path.is_dir()` returns `False` for every dropped item, the folder list is never populated, and drag and drop appears completely broken with no error message.

This affects all three drop handlers identically.

**Steps:**

1. Add a URL normaliser to `gui/platform_utils.py`:

```python
def url_to_local_path(url) -> Path:
    """
    Convert a QUrl from a drag-drop event to a correct local Path.
    Fixes Qt6 on Windows returning '/C:/Users/...' with a leading slash.
    """
    local = url.toLocalFile()
    if sys.platform == "win32":
        # Strip leading slash before a drive letter: /C:/... -> C:/...
        import re
        local = re.sub(r'^/([A-Za-z]:)', r'\1', local)
    return Path(local)
```

2. In `gui/lookup_tab.py`, replace the `dropEvent` in `DropListWidget`:

```python
    def dropEvent(self, event):
        from gui.platform_utils import url_to_local_path
        paths = [str(url_to_local_path(url)) for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()
```

3. In `gui/verify_tab.py`, replace the `dropEvent` in `DropFolderListWidget`:

```python
    def dropEvent(self, event):
        from gui.platform_utils import url_to_local_path
        folders = []
        seen = set()
        for url in event.mimeData().urls():
            path = url_to_local_path(url)
            folder = str(path if path.is_dir() else path.parent)
            if folder not in seen:
                seen.add(folder)
                folders.append(folder)
        self.folders_dropped.emit(folders)
        event.acceptProposedAction()
```

4. In `gui/lbdir_tab.py`, apply the identical replacement to its `DropFolderListWidget.dropEvent` — it is a copy of the same class.

**Done when:** Dragging a folder from Windows Explorer onto the Lookup, Verify, and lbdir list widgets adds the folder correctly. Verify by checking that the folder name appears in the list and `path.is_dir()` would return `True` for the resolved path.

---

## WIN-15: Redirect WebEngine Cache for Full Portability

**Files:** `gui/attachments_tab.py`, `backend/paths.py`  
**Dependencies:** WIN-01, WIN-11  
**New packages:** None

**Problem:** `QWebEngineView` with no explicit profile uses the default `QWebEngineProfile`, which stores its cache and persistent data at a platform-specific location:
- Windows: `%LOCALAPPDATA%\QtProject\QtWebEngine\`  (not portable, survives uninstall)
- Linux: `~/.local/share/QtProject/QtWebEngine/`

This means:
1. The app writes outside its own folder, breaking USB/portable use.
2. The cache path contains user account data left behind after the app is removed.
3. On a machine that has never run the app before, no cache exists and WebEngine re-downloads its resources.

**Steps:**

1. Add to `backend/paths.py`:

```python
WEBENGINE_DIR = DATA_DIR / "webengine_cache"
```

2. In `gui/attachments_tab.py`, find where `QWebEngineView` is instantiated (inside `_build_right_panel` or similar, around line 89). Before creating the view, set up an off-the-record profile redirected to the data directory:

```python
    def _build_right_panel(self):
        ...
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineProfile
            from backend.paths import WEBENGINE_DIR

            WEBENGINE_DIR.mkdir(parents=True, exist_ok=True)
            profile = QWebEngineProfile("losslessbob", self)
            profile.setPersistentStoragePath(str(WEBENGINE_DIR))
            profile.setCachePath(str(WEBENGINE_DIR / "cache"))
            profile.setHttpCacheMaximumSize(32 * 1024 * 1024)  # 32 MB cap

            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEnginePage
            page = QWebEnginePage(profile, self)
            self.web_view = QWebEngineView(self)
            self.web_view.setPage(page)
        except ImportError:
            self.web_view = None
        ...
```

3. If `gui/attachments_tab.py` currently constructs the `QWebEngineView` with just `QWebEngineView()` (no profile), replace that single line with the block above.

4. Add `webengine_cache/` to `.gitignore` if one exists, or document in `README.md` that `data/webengine_cache/` is machine-local and should not be committed or copied between machines.

**Done when:**
- After loading an HTML attachment, no files appear under `%LOCALAPPDATA%\QtProject\`.
- `data/webengine_cache/` exists and contains the cache.
- Copying the entire app folder to a USB drive and running it on another machine works without errors (WebEngine rebuilds its cache in the new location).

---

## WIN-16: Startup Lag — Lazy Tab Imports and Deferred Status Bar

**Files:** `gui/main_window.py`, `main.py`  
**Dependencies:** WIN-02  
**New packages:** None

**Problem:** Two independent lag sources on every platform, worse on Windows:

**Source 1 — Eager tab imports at module load time.**  
The top of `main_window.py` imports all 9 tab modules unconditionally:
```python
from gui.lookup_tab import LookupTab
from gui.rename_tab import RenameTab
...  # 7 more
```
Each of these transitively imports `requests`, `PyQt6.QtWebEngineWidgets` (slow DLL init on Windows), and all other GUI dependencies. All of this runs before `QApplication` is created, before the window is visible, before Flask is ready. On Windows with PyInstaller, Defender may scan newly extracted DLLs during this phase — this is the primary source of the 5–15 second blank screen on first launch.

**Source 2 — Status bar fires a blocking network call 500ms after launch.**  
`QTimer.singleShot(500, self._refresh_status)` fires while the window is still rendering its first frame. `_refresh_status` calls `requests.get(..., timeout=3)` on the main thread. If Flask isn't warm yet (cold DB, first search index build), this 3-second timeout blocks the Qt event loop, freezing the UI.

**Steps:**

1. In `main_window.py`, remove all top-level tab imports and move them inside `_build_tabs()` as local imports:

```python
# DELETE these lines from the top of main_window.py:
# from gui.lookup_tab import LookupTab
# from gui.rename_tab import RenameTab
# from gui.verify_tab import VerifyTab
# from gui.lbdir_tab import LbdirTab
# from gui.search_tab import SearchTab
# from gui.collection_tab import CollectionTab
# from gui.attachments_tab import AttachmentsTab
# from gui.setup_tab import SetupTab
# from gui.theme_tab import ThemeTab

def _build_tabs(self):
    # Local imports: each tab module is loaded only when _build_tabs() runs,
    # which happens after QApplication and the window skeleton exist.
    from gui.lookup_tab import LookupTab
    from gui.rename_tab import RenameTab
    from gui.verify_tab import VerifyTab
    from gui.lbdir_tab import LbdirTab
    from gui.search_tab import SearchTab
    from gui.collection_tab import CollectionTab
    from gui.attachments_tab import AttachmentsTab
    from gui.setup_tab import SetupTab
    from gui.theme_tab import ThemeTab

    self.tabs = QTabWidget()
    self.setCentralWidget(self.tabs)
    # ... rest of _build_tabs unchanged
```

2. In `main_window.py`, change the status bar initial fire from 500ms to 3000ms so it runs after the window has fully painted and Flask is warm:

```python
# Replace:
QTimer.singleShot(500, self._refresh_status)
# With:
QTimer.singleShot(3000, self._refresh_status)
```

3. Move `_refresh_status` off the main thread. Replace the synchronous `requests.get` with a `QThread` worker so the status bar update never blocks the UI:

```python
    def _refresh_status(self):
        """Fetch DB stats in a background thread and update status bar."""
        import threading
        def _fetch():
            try:
                import requests as _req
                resp = _req.get(
                    f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5
                )
                s = resp.json()
                lb = s.get("latest_lb", "?")
                checksums = s.get("total_checksums", 0)
                last_import = s.get("last_import", "Never")
                if last_import and len(str(last_import)) > 10:
                    last_import = str(last_import)[:10]
                msg = f"DB: LB-{lb}  |  Checksums: {checksums:,}  |  Last import: {last_import}"
            except Exception:
                msg = "Database not connected."
            # Marshal back to Qt main thread via a single-shot timer
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.status_bar.showMessage(msg))

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()
```

4. Optionally, add a splash screen in `main.py` to give the user feedback during the Flask startup wait. Insert after `QApplication` is created and before `_wait_for_port`:

```python
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap, QColor
    from PyQt6.QtCore import Qt

    # Minimal splash — plain coloured rectangle with text
    pix = QPixmap(400, 120)
    pix.fill(QColor("#1F4E79"))
    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.showMessage(
        "  LosslessBob — starting…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
        QColor("#FFFFFF"),
    )
    splash.show()
    qt_app.processEvents()

    # ... _wait_for_port() call here ...

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    window.show()
    splash.finish(window)
```

**Done when:**
- Window appears within 1–2 seconds on Windows (splash screen visible during Flask startup).
- Window is immediately interactive after appearing — no frozen period while status bar loads.
- Status bar populates 3 seconds after launch without blocking input.

---

---

## WIN-17: Fix Drag-and-Drop Crash (OLE Reentrancy)

**Files:** `gui/lookup_tab.py`, `gui/verify_tab.py`, `gui/lbdir_tab.py`  
**Dependencies:** None — this is the primary crash fix, do it independently of WIN-14  
**New packages:** None

**Root cause:** The crash is a Windows OLE COM reentrancy violation, not a path issue. On Windows, Qt handles drag-and-drop via `IDropTarget::Drop()` (OLE COM). When `Drop()` calls Qt's `dropEvent`, the COM transaction is still active on the call stack. The current code dispatches a synchronous signal from within `dropEvent`, whose handler calls `self.listbox.clear()` on the same widget that is mid-`dropEvent`. Clearing the widget's internal model while OLE holds a live COM reference to it causes an access violation — the process terminates without a Python traceback.

On Linux this never crashes because the X11/XDND protocol completes the drop transaction asynchronously before any widget modification can happen. The bug is latent and Linux-only testing masked it entirely.

**Exact call chain that crashes:**

```
DropListWidget.dropEvent(event)
  └─ self.files_dropped.emit(paths)          ← synchronous Qt signal
       └─ LookupTab._on_files_dropped(paths)
            └─ for p in paths: self._add_path(p)
                 └─ self._refresh_listbox()  ← called once PER dropped item
                      └─ self.listbox.clear() ← self IS the widget in dropEvent
                                               ← OLE Drop() still on call stack
                                               ← ACCESS VIOLATION → crash
```

Same pattern in `verify_tab.py` and `lbdir_tab.py`:
```
DropFolderListWidget.dropEvent(event)
  └─ self.folders_dropped.emit(folders)
       └─ VerifyTab._on_folders_dropped(folders)
            └─ self._refresh_listbox()
                 └─ self.listbox.clear()  ← same crash
```

**Additional bug in `lookup_tab.py`:** `_add_path()` calls `_refresh_listbox()` once per dropped item. Dropping a folder containing 10 subfolders calls `listbox.clear()` 10 times during one drop event — both a performance problem and repeated reentrancy violations.

**Fix:** Defer all `_refresh_listbox()` calls that originate from drop handlers to run after `dropEvent` returns, using `QTimer.singleShot(0, ...)`. Zero-delay single-shot timers post the call to the event queue, guaranteeing it runs only after the current event (including OLE's `Drop()`) finishes processing.

**Steps:**

**1. `gui/lookup_tab.py` — fix `_add_path` and `_on_files_dropped`:**

Remove the `self._refresh_listbox()` call at the end of `_add_path()`:

```python
    def _add_path(self, path):
        p = Path(path)
        if p.is_dir():
            found_any = False
            candidates = list(p.iterdir())
            for child in candidates:
                if child.is_file() and child.suffix.lower() in self._CHECKSUM_EXTS:
                    found_any = True
                    s = str(child)
                    if s not in self._all_paths:
                        self._all_paths.append(s)
                elif child.is_dir():
                    for grandchild in child.iterdir():
                        if grandchild.is_file() and grandchild.suffix.lower() in self._CHECKSUM_EXTS:
                            found_any = True
                            s = str(grandchild)
                            if s not in self._all_paths:
                                self._all_paths.append(s)
            if found_any:
                self._no_checksum_folders.discard(str(p))
            else:
                self._no_checksum_folders.add(str(p))
        else:
            s = str(p)
            if s not in self._all_paths:
                self._all_paths.append(s)
        # NOTE: do NOT call _refresh_listbox() here.
        # Callers are responsible for refreshing once after all paths are added.
```

Update `_on_files_dropped` to refresh once with a deferred call:

```python
    def _on_files_dropped(self, paths):
        for p in paths:
            self._add_path(p)
        self._update_list_header()
        # Defer the listbox rebuild until after dropEvent and OLE Drop() have returned.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_listbox)
```

Verify that every other caller of `_add_path` still calls `_refresh_listbox()` itself after the loop. Search the file for `_add_path(` — each non-drop caller (e.g. `_on_add_files`, `_on_add_folders`) should call `self._refresh_listbox()` after its loop. These are not inside a drop event so they can call it synchronously; confirm they already do or add the call.

**2. `gui/verify_tab.py` — fix `_on_folders_dropped`:**

```python
    def _on_folders_dropped(self, folders):
        for f in folders:
            self._add_folder(f)
        # Deferred: do not call _refresh_listbox() directly from within dropEvent.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_listbox)
```

**3. `gui/lbdir_tab.py` — fix `_on_folders_dropped`:**

```python
    def _on_folders_dropped(self, folders):
        for f in folders:
            self._add_folder(f)
        # Deferred: same OLE reentrancy fix as verify_tab.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_listbox)
```

**4. Update the `DropListWidget.dropEvent` and `DropFolderListWidget.dropEvent` in all three files** to call `acceptProposedAction()` before emitting the signal, not after. This lets OLE mark the transaction complete before any downstream code runs:

```python
    def dropEvent(self, event):
        event.acceptProposedAction()   # ← accept FIRST, close OLE transaction
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)  # ← then emit
```

Apply the same reordering in `verify_tab.py` and `lbdir_tab.py`:

```python
    def dropEvent(self, event):
        event.acceptProposedAction()   # ← accept first
        folders = []
        seen = set()
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            folder = str(path if path.is_dir() else path.parent)
            if folder not in seen:
                seen.add(folder)
                folders.append(folder)
        self.folders_dropped.emit(folders)
```

**Note:** Apply both fixes (accept-first AND deferred refresh). The accept-first closes the OLE transaction at the earliest possible point. The deferred refresh ensures that even if any intermediate code path triggers a refresh synchronously, it arrives after the event loop processes the drop completion.

**Done when:** Dragging a folder from Windows Explorer onto any of the three list widgets adds the folder without crashing. Dragging 10 folders at once works. App does not crash if drag is cancelled mid-way (drag over widget then drag back out without dropping).

---

## APPENDIX: Windows Testing Checklist

Run these after all tasks are complete on a Windows 10/11 machine (or VM) with no Python installed — test from the PyInstaller build.

**Drag and Drop:**
- [ ] Dragging a folder from Windows Explorer onto the Lookup list adds it
- [ ] Dragging a folder onto the Verify list adds it
- [ ] Dragging a folder onto the lbdir list adds it
- [ ] Dragging a checksum file (not a folder) onto Lookup adds it correctly

**Startup:**
- [ ] `LosslessBob.exe` starts without console window
- [ ] First launch creates `data/` directory next to `.exe`
- [ ] Second launch after closing does not show "port in use" error
- [ ] `data/settings.ini` is created after first launch

**Database:**
- [ ] Dropping a flat `.txt` import file into `data/` triggers auto-import
- [ ] Concurrent scraping + search produces no "database is locked" errors
- [ ] DB path with 250+ characters opens correctly

**Lookup / Verify:**
- [ ] Pasting a checksum file returns correct LB matches
- [ ] Verifying a FLAC folder shows PASS/FAIL correctly
- [ ] No console window appears during checksum computation

**SHN (requires WSL + shntool):**
- [ ] Without WSL: SHN folder shows `INCOMPLETE` with Windows-specific install instructions
- [ ] With WSL + shntool: SHN folder verifies correctly

**Collection / Rename:**
- [ ] "Open Folder" opens Windows Explorer at the correct path
- [ ] Renaming a folder while Explorer has it focused shows a clear permission error
- [ ] Renaming a folder not held by Explorer succeeds

**Paths:**
- [ ] Settings survive copying the entire `LosslessBob/` folder to another drive
- [ ] Settings do NOT appear in Windows Registry (`HKCU\Software\LosslessBobLookup`)
- [ ] No files written to `%LOCALAPPDATA%\QtProject\` after loading an HTML attachment
- [ ] `data/webengine_cache/` exists and contains WebEngine data after first HTML load
- [ ] App runs from a USB drive path (e.g. `E:\LosslessBob\LosslessBob.exe`) without errors

---

## APPENDIX: Implementation Order

```
WIN-17  (drag-and-drop crash — the primary crash, no dependencies, do first)
WIN-01  (path resolution — everything else depends on it)
WIN-02  (Flask readiness poll + Waitress — required before testing anything)
WIN-03  (xdg-open crash fix — creates platform_utils.py needed by WIN-05/WIN-14)
WIN-04  (SQLite timeout)
WIN-05  (console window suppression — after WIN-03)
WIN-06  (Waitress — covered in WIN-02 if done together)
WIN-07  (rename permission errors — standalone)
WIN-08  (shntool / WSL — standalone)
WIN-09  (long paths — after WIN-01)
WIN-10  (font stack — standalone)
WIN-11  (INI settings — after WIN-01)
WIN-14  (drag-and-drop path fix — after WIN-03; separate from WIN-17, fixes silent failure)
WIN-15  (WebEngine cache — after WIN-01 and WIN-11)
WIN-16  (startup lag — after WIN-02)
WIN-12  (PyInstaller spec — last, after all runtime fixes are complete)
WIN-13  (Watchdog — after WIN-01)
```
