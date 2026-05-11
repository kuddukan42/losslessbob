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
LOG_FILE = DATA_DIR / "scraper.log"
TOOLS_DIR = APP_ROOT / "tools"


def ensure_data_dirs() -> None:
    """Create data subdirectories if they do not exist."""
    for d in (DATA_DIR, ATTACHMENTS_DIR, PAGES_DIR):
        d.mkdir(parents=True, exist_ok=True)
