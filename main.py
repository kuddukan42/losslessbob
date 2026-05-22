import logging
import os
import sys
import socket
import threading
import time
from logging.handlers import RotatingFileHandler

from PyQt6.QtWidgets import QApplication

from backend.app import create_app
from backend.paths import ensure_data_dirs, DATA_DIR
import backend.startup_log as _slog

FLASK_PORT = 5174
_FLASK_READY = threading.Event()

# ── Flask in-process restart support ─────────────────────────────────────────
_flask_server = None
_flask_server_lock = threading.Lock()
_flask_restart_event = threading.Event()


def request_flask_restart() -> None:
    """Shut down the current Flask server so the start_flask loop restarts it.

    Called by the /api/admin/restart route. Only the Flask backend restarts;
    the GUI process stays alive.
    """
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
    """Start the Flask backend in a loop that supports in-process restart.

    On Linux/macOS: uses werkzeug's make_server so the server can be shut down
    and restarted without touching the GUI process.
    On Windows: uses Waitress (no clean shutdown support) — restart falls back
    to os.execv and restarts the whole process.
    """
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

    # Linux/macOS: restart loop using werkzeug make_server
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
        time.sleep(0.5)  # brief pause to ensure the OS releases the port


def _configure_logging() -> None:
    """Write DEBUG+ from our own modules to data/losslessbob.log; keep third-party at WARNING."""
    log_path = DATA_DIR / "losslessbob.log"

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    # Root logger at WARNING so urllib3/requests/werkzeug stay quiet.
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(fh)
    root.addHandler(sh)

    # Our own namespaces get DEBUG so every logger.debug() call lands in the file.
    for ns in ("backend", "gui"):
        logging.getLogger(ns).setLevel(logging.DEBUG)

    # urllib3/requests: pin now (Flask hasn't touched them yet).
    for ns in ("urllib3", "requests"):
        logging.getLogger(ns).setLevel(logging.WARNING)


def main() -> None:
    ensure_data_dirs()
    _configure_logging()
    _slog.init(DATA_DIR / "startup.log")
    _slog.t("main: start")

    ignore_pos = "-ignore_start_positions" in sys.argv

    # If a persistent daemon backend is already up (e.g. started via `cli.py daemon
    # start`), attach to it instead of launching a competing Flask thread.
    _backend_already_running = _wait_for_port("127.0.0.1", FLASK_PORT, timeout=0.5)
    if not _backend_already_running:
        # Register restart callback before starting Flask so it's available immediately.
        # Windows still uses waitress (no clean shutdown) — leave callback unset there
        # so admin_restart falls back to os.execv.
        if sys.platform != "win32":
            import backend.app as _backend_app
            _backend_app.set_restart_callback(request_flask_restart)
        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()
        _slog.t("flask thread started")
    else:
        _slog.t("existing backend detected on port 5174 — skipping flask thread")

    # Force XWayland (xcb) on Linux when running under a Wayland compositor.
    # Native Wayland + AA_ShareOpenGLContexts + QtWebEngine can trigger fatal
    # EGL_BAD_NATIVE_WINDOW (0x300d) errors that kill the Wayland connection
    # with no recovery path. XWayland is stable for this workload and loses
    # no functionality. Honour an explicit QT_QPA_PLATFORM override from the
    # environment so the user can still opt in to native Wayland if desired.
    if sys.platform != "win32" and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    # Suppress Chromium-level sandbox diagnostics and path-override warnings that
    # go directly to stderr and can't be filtered through Python's logging.
    # --disable-gpu is Linux/XWayland-only: it prevents Chromium from starting a
    # GPU process, which fixes two Qt 6.7 regressions on XWayland:
    #   1. GBM "Unknown or not supported format: 808530000" (P010 format probe)
    #   2. Full-window blackout caused by Chromium's GPU process hijacking the
    #      shared OpenGL context established by AA_ShareOpenGLContexts.
    # On Windows, Chromium uses DirectX/ANGLE and GPU acceleration works correctly;
    # applying --disable-gpu there forces Swiftshader software rendering and makes
    # the Map and Attachments tabs noticeably laggy (TODO-044).
    _flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    _always_flags = ["--disable-logging"]
    _linux_flags = ["--disable-gpu"] if sys.platform != "win32" else []
    for _f in _always_flags + _linux_flags:
        if _f not in _flags:
            _flags = (_flags + " " + _f).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags

    # Must be set before QApplication is constructed so QtWebEngine can share
    # the GPU process's OpenGL context; without this the renderer falls back to
    # a slow separate-context path that causes a ~10 s stall on Linux.
    from PyQt6.QtCore import Qt as _Qt
    QApplication.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    _slog.t("AA_ShareOpenGLContexts set")

    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("LosslessBob Checksum Lookup")
    _slog.t("QApplication created")

    # Load UI language before any windows are constructed so all tr() calls use
    # the right translator from the start.
    import sqlite3 as _sqlite3
    from backend.paths import DB_PATH as _DB_PATH
    from gui.i18n import load_language as _load_language

    def _read_saved_lang() -> str:
        try:
            with _sqlite3.connect(str(_DB_PATH)) as _conn:
                _row = _conn.execute(
                    "SELECT value FROM meta WHERE key='ui_language'"
                ).fetchone()
                return _row[0] if _row else "en"
        except Exception:
            return "en"

    _load_language(qt_app, _read_saved_lang())
    _slog.t("i18n language loaded")

    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap, QColor
    from PyQt6.QtCore import Qt

    _screen = qt_app.primaryScreen()
    dpr = _screen.devicePixelRatio() if _screen else 1.0
    pix = QPixmap(int(400 * dpr), int(120 * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(QColor("#1F4E79"))
    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.showMessage(
        "  LosslessBob — starting…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
        QColor("#FFFFFF"),
    )
    splash.show()
    qt_app.processEvents()
    _slog.t("splash shown")

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

    from gui.main_window import MainWindow
    _slog.t("main_window module imported")

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    _slog.t("MainWindow created")
    window.show()
    _slog.t("window.show() called")
    splash.finish(window)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
