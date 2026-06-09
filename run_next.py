"""Launcher for the gui_next redesign UI.

Shares the same Flask backend (port 5174) and SQLite DB as the legacy UI.
Launch the stable UI with:  .venv/bin/python3 main.py
Launch the redesign UI with: .venv/bin/python3 run_next.py
"""
import logging
import os
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from PyQt6.QtWidgets import QApplication

import backend.startup_log as _slog
from backend.app import create_app
from backend.paths import DATA_DIR, ensure_data_dirs

FLASK_PORT = 5174
_FLASK_READY = threading.Event()

_flask_server = None
_flask_server_lock = threading.Lock()
_flask_restart_event = threading.Event()


def request_flask_restart() -> None:
    """Shut down the current Flask server so the start_flask loop restarts it."""
    global _flask_server
    _flask_restart_event.set()
    with _flask_server_lock:
        srv = _flask_server
    if srv is not None:
        srv.shutdown()


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    """Block until the TCP port accepts connections or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_flask() -> None:
    """Start the Flask backend in a loop that supports in-process restart."""
    global _flask_server
    ensure_data_dirs()

    if sys.platform == "win32":
        flask_app = create_app()
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        try:
            from waitress import serve as waitress_serve
            _FLASK_READY.set()
            waitress_serve(flask_app, host="0.0.0.0", port=FLASK_PORT,
                           threads=8, channel_timeout=120)
        except ImportError:
            flask_app.run(host="0.0.0.0", port=FLASK_PORT,
                          debug=False, use_reloader=False)
        return

    from werkzeug.serving import make_server
    while True:
        flask_app = create_app()
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        srv = make_server("0.0.0.0", FLASK_PORT, flask_app, threaded=True)
        with _flask_server_lock:
            _flask_server = srv
        srv.serve_forever()
        srv.server_close()

        if not _flask_restart_event.is_set():
            break
        _flask_restart_event.clear()
        time.sleep(0.5)


def _configure_logging() -> None:
    log_path = DATA_DIR / "losslessbob_next.log"

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(fh)
    root.addHandler(sh)

    for ns in ("backend", "gui_next"):
        logging.getLogger(ns).setLevel(logging.DEBUG)

    for ns in ("urllib3", "requests"):
        logging.getLogger(ns).setLevel(logging.WARNING)


def main() -> None:
    ensure_data_dirs()
    _configure_logging()
    _slog.init(DATA_DIR / "startup_next.log")
    _slog.t("main: start (gui_next)")

    ignore_pos = "-ignore_start_positions" in sys.argv

    _backend_already_running = _wait_for_port("127.0.0.1", FLASK_PORT, timeout=0.5)
    if not _backend_already_running:
        if sys.platform != "win32":
            import backend.app as _backend_app
            _backend_app.set_restart_callback(request_flask_restart)
        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()
        _slog.t("flask thread started")
    else:
        _slog.t("existing backend detected on port 5174 — skipping flask thread")

    if sys.platform != "win32" and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "wayland"

    _flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    _always_flags = ["--disable-logging"]
    _linux_flags = ["--disable-gpu"] if sys.platform != "win32" else []
    for _f in _always_flags + _linux_flags:
        if _f not in _flags:
            _flags = (_flags + " " + _f).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags

    from PyQt6.QtCore import Qt as _Qt
    QApplication.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("LosslessBob Next")
    _slog.t("QApplication created")

    if not _wait_for_port("127.0.0.1", FLASK_PORT, timeout=15.0):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Startup Error",
            f"Flask backend did not start on port {FLASK_PORT}.\n"
            "Another process may be using that port.\n"
            "Try restarting the application.",
        )
        sys.exit(1)
    _slog.t("flask port ready")

    from gui_next.main_window import MainWindow
    _slog.t("gui_next main_window imported")

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    _slog.t("MainWindow created")
    window.show()
    _slog.t("window.show() called")
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
