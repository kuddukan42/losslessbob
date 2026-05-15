"""Central path resolver — handles normal Python, PyInstaller frozen, and portable ZIP builds."""
import sys
from pathlib import Path


def _app_root() -> Path:
    """Return the directory that contains the data/ folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "data"
DB_PATH = DATA_DIR / "losslessbob.db"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
PAGES_DIR = DATA_DIR / "pages"
TORRENTS_DIR = DATA_DIR / "torrents"
LOG_FILE = DATA_DIR / "scraper.log"
TOOLS_DIR = APP_ROOT / "tools"
WEBENGINE_DIR = DATA_DIR / "webengine_cache"


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
    for d in (DATA_DIR, ATTACHMENTS_DIR, PAGES_DIR, TORRENTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32" and len(str(DATA_DIR)) > 200:
        import warnings
        warnings.warn(
            f"Data directory path is {len(str(DATA_DIR))} characters. "
            "Windows MAX_PATH is 260. Consider moving the app closer to a drive root.",
            stacklevel=2,
        )
