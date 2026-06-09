import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.db import DB_PATH, get_meta
from backend.importer import md5_file, run_import
from backend.paths import DATA_DIR

_log = logging.getLogger(__name__)
_import_callbacks = []
_observer = None


def register_import_callback(cb):
    _import_callbacks.append(cb)


def _notify(msg):
    for cb in _import_callbacks:
        try:
            cb(msg)
        except Exception:
            pass


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, db_path=None):
        super().__init__()
        self.db_path = db_path or DB_PATH
        self._pending = {}

    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)

    def _handle(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".txt":
            return
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
                        result = run_import(path, progress_callback=_notify, db_path=self.db_path)
                        if result.get("skipped"):
                            _notify("Import skipped (no changes).")
                        else:
                            _notify(f"Import complete: {result['new_lb_count']} new LB entries.")
                    except Exception as e:
                        _notify(f"Import error: {e}")

                threading.Thread(target=do_import, daemon=True).start()
            finally:
                self._pending.pop(key, None)

        threading.Thread(target=delayed, daemon=True).start()


def start_file_watcher(db_path=None):
    global _observer
    if _observer and _observer.is_alive():
        return
    import sys as _sys
    handler = FileEventHandler(db_path=db_path)
    if _sys.platform == "win32":
        try:
            from watchdog.observers.winapi import WindowsApiObserver
            _observer = WindowsApiObserver()
        except ImportError:
            _observer = Observer()
    else:
        _observer = Observer()
    _observer.schedule(handler, str(DATA_DIR), recursive=False)
    _observer.daemon = True
    _observer.start()


def stop_file_watcher():
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None


# ── Collection folder integrity poller ────────────────────────────────────────

_collection_poll_stop: threading.Event | None = None
_collection_poll_thread: threading.Thread | None = None

_COLLECTION_POLL_INTERVAL = 60  # seconds


def _collection_poll_worker(stop_event: threading.Event, db_path=None) -> None:
    from backend.db import get_connection, log_integrity_event
    reported_missing: set[int] = set()
    while not stop_event.wait(_COLLECTION_POLL_INTERVAL):
        try:
            with get_connection(db_path) as conn:
                rows = conn.execute(
                    "SELECT lb_number, disk_path FROM my_collection WHERE disk_path IS NOT NULL"
                ).fetchall()
        except Exception:
            _log.exception("collection_poll: DB query failed")
            continue
        current_ids = {row["lb_number"] for row in rows}
        reported_missing &= current_ids
        for row in rows:
            lb = row["lb_number"]
            dp = Path(row["disk_path"])
            if not dp.exists():
                if lb not in reported_missing:
                    reported_missing.add(lb)
                    try:
                        log_integrity_event(
                            lb, row["disk_path"],
                            "missing", f"Path no longer accessible: {dp}",
                        )
                    except Exception:
                        _log.exception("collection_poll: log_integrity_event failed")
            else:
                reported_missing.discard(lb)


def start_collection_watcher(db_path=None):
    """Poll every disk_path in my_collection for missing folders."""
    global _collection_poll_stop, _collection_poll_thread
    stop_collection_watcher()
    _collection_poll_stop = threading.Event()
    _collection_poll_thread = threading.Thread(
        target=_collection_poll_worker,
        args=(_collection_poll_stop,),
        kwargs={"db_path": db_path},
        daemon=True,
        name="collection-poll",
    )
    _collection_poll_thread.start()


def stop_collection_watcher():
    global _collection_poll_stop, _collection_poll_thread
    if _collection_poll_stop:
        _collection_poll_stop.set()
    if _collection_poll_thread:
        _collection_poll_thread.join(timeout=5)
    _collection_poll_stop = None
    _collection_poll_thread = None
