"""Central path resolver — handles normal Python, PyInstaller frozen, and portable ZIP builds."""
import os
import sys
from pathlib import Path

APP_VERSION = "1.2.0"


def _app_root() -> Path:
    """Return the directory that contains the data/ folder."""
    if getattr(sys, "frozen", False):
        if sys.platform == "linux":
            # AppImage: read-only squashfs mount. Use XDG_DATA_HOME so data persists.
            xdg = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            return xdg / "LosslessBob"
        if sys.platform == "win32":
            # Electron-packaged: backend binary lives inside resources/backend/ which is
            # inside the installation tree and may be read-only. Store data in LocalAppData.
            localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return localappdata / "LosslessBob"
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "data"
DB_PATH    = DATA_DIR / "losslessbob.db"
FP_DB_PATH = DATA_DIR / "fingerprints.db"
TORRENTS_DIR = DATA_DIR / "torrents"
LOG_FILE = DATA_DIR / "scraper.log"
TOOLS_DIR = APP_ROOT / "tools"
WEBENGINE_DIR = DATA_DIR / "webengine_cache"

# ── Offline site mirror ───────────────────────────────────────────────────────
# data/site/ mirrors the URL directory structure of losslessbob.wonderingwhattochoose.com
# so that relative links work natively when browsing offline via file:// or Flask.
#
#   data/site/detail/LB-XXXXX.html   ← entry detail pages  (links rewritten)
#   data/site/files/LBF-XXXXX-*.ext  ← attachment files    (original filenames)
#   data/site/lbbcd/LBBCD-NNN.html   ← LBBCD detail pages  (links rewritten)
#   data/site/bynumber/*.html         ← bynumber index      (links rewritten)
#   data/site/index.html              ← root / home page    (links rewritten)
#
# These replace the old PAGES_DIR (data/pages/) and ATTACHMENTS_DIR (data/attachments/).
SITE_DIR         = DATA_DIR / "site"
SITE_DETAIL_DIR  = SITE_DIR / "detail"
SITE_FILES_DIR   = SITE_DIR / "files"
SITE_LBBCD_DIR   = SITE_DIR / "lbbcd"
SITE_BN_DIR      = SITE_DIR / "bynumber"


def detail_page_path(lb_id: str) -> "Path":
    """Return the local path for an entry detail page, e.g. LB-00001.html."""
    return SITE_DETAIL_DIR / f"LB-{lb_id}.html"


def attachment_path(filename: str) -> "Path":
    """Return the local path for an attachment file using its ORIGINAL filename.

    Args:
        filename: Original filename as stored in entry_files.filename,
                  e.g. ``LBF-01234-lbdir.txt``.
    """
    return SITE_FILES_DIR / filename


def find_lbdir_attachment(lb_number: int) -> "Path | None":
    """Find the lbdir attachment file for lb_number in SITE_FILES_DIR.

    Searches for files matching ``LBF-{lb_number:05d}-*lbdir*.txt``.
    Returns None if SITE_FILES_DIR does not exist or no file is found.
    """
    if not SITE_FILES_DIR.exists():
        return None
    prefix = f"LBF-{lb_number:05d}-"
    for f in SITE_FILES_DIR.iterdir():
        if (f.name.startswith(prefix)
                and "lbdir" in f.name.lower()
                and f.suffix.lower() == ".txt"):
            return f
    return None


def to_long_path(p: Path) -> Path:
    """On Windows, prefix path with \\?\\ to enable paths > MAX_PATH (260). No-op elsewhere."""
    if sys.platform != "win32":
        return p
    p = p.resolve()
    s = str(p)
    if s.startswith("\\\\?\\"):
        return p
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)


def ensure_data_dirs() -> None:
    """Create data subdirectories if they do not exist."""
    for d in (DATA_DIR, TORRENTS_DIR,
              SITE_DIR, SITE_DETAIL_DIR, SITE_FILES_DIR, SITE_LBBCD_DIR, SITE_BN_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32" and len(str(DATA_DIR)) > 200:
        import warnings
        warnings.warn(
            f"Data directory path is {len(str(DATA_DIR))} characters. "
            "Windows MAX_PATH is 260. Consider moving the app closer to a drive root.",
            stacklevel=2,
        )
