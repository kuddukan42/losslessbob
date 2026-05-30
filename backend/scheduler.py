import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.importer import run_import, md5_file
from backend.db import get_meta, DB_PATH

from backend.paths import DATA_DIR

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


# ── Collection folder integrity watchdog ──────────────────────────────────────

_collection_observer = None


class _CollectionEventHandler(FileSystemEventHandler):
    def __init__(self, lb_number: int, disk_path: str):
        super().__init__()
        self.lb_number = lb_number
        self.disk_path = disk_path

    def on_deleted(self, event):
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "deleted", f"Deleted: {event.src_path}",
        )

    def on_moved(self, event):
        from backend.db import log_integrity_event
        log_integrity_event(
            self.lb_number, self.disk_path,
            "moved", f"Moved: {event.src_path} -> {event.dest_path}",
        )


def start_collection_watcher(db_path=None):
    """Watch every disk_path in my_collection for deletions and moves."""
    global _collection_observer
    from backend.db import get_connection, DB_PATH
    if _collection_observer and _collection_observer.is_alive():
        _collection_observer.stop()
        _collection_observer.join()
    import sys as _sys
    if _sys.platform == "win32":
        try:
            from watchdog.observers.winapi import WindowsApiObserver
            obs = WindowsApiObserver()
        except ImportError:
            obs = Observer()
    else:
        obs = Observer()
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT lb_number, disk_path FROM my_collection WHERE disk_path IS NOT NULL"
        ).fetchall()
    for row in rows:
        dp = Path(row["disk_path"])
        if dp.is_dir():
            handler = _CollectionEventHandler(row["lb_number"], row["disk_path"])
            obs.schedule(handler, str(dp), recursive=False)
    obs.daemon = True
    obs.start()
    _collection_observer = obs


def stop_collection_watcher():
    global _collection_observer
    if _collection_observer:
        _collection_observer.stop()
        _collection_observer.join()
        _collection_observer = None
