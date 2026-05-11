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

        # Debounce: wait 2s then check hash
        def delayed():
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

            t = threading.Thread(target=do_import, daemon=True)
            t.start()

        key = str(path)
        if key in self._pending:
            return
        self._pending[key] = True
        t = threading.Thread(target=delayed, daemon=True)
        t.start()


def start_file_watcher(db_path=None):
    global _observer
    if _observer and _observer.is_alive():
        return

    handler = FileEventHandler(db_path=db_path)
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
