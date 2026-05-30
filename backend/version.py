from backend.paths import APP_ROOT


def get_version() -> str:
    try:
        return (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


VERSION: str = get_version()
