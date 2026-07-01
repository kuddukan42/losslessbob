"""Startup timing logger — writes timestamped events to data/logs/startup.log.

Usage:
    import backend.startup_log as startup_log
    startup_log.init(path)          # call once, early in main()
    startup_log.t("event label")    # call at each milestone

The log is truncated on each run. Events from both the main thread and the
Flask thread are written safely via a lock.
"""
import threading
import time
from datetime import datetime
from pathlib import Path

_t0: float = time.perf_counter()   # set at import time for maximum coverage
_log_path: Path | None = None
_lock = threading.Lock()


def init(log_path: Path) -> None:
    """Open (truncate) the log file and write a start marker."""
    global _log_path
    _log_path = log_path
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(log_path, "w") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                f.write(f"[{ts}] === startup begin ===\n")
    except Exception:
        pass


def t(label: str) -> None:
    """Write a timestamped event — elapsed seconds since module import."""
    if _log_path is None:
        return
    elapsed = time.perf_counter() - _t0
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] +{elapsed:6.3f}s  {label}\n"
    with _lock:
        try:
            with open(_log_path, "a") as f:
                f.write(line)
        except Exception:
            pass
