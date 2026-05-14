import sys
import socket
import threading
import time

from PyQt6.QtWidgets import QApplication

from backend.app import create_app
from backend.paths import ensure_data_dirs, DATA_DIR
import backend.startup_log as _slog

FLASK_PORT = 5174
_FLASK_READY = threading.Event()


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
    """Start the Flask backend, using Waitress on Windows for stability."""
    ensure_data_dirs()
    flask_app = create_app()
    if sys.platform == "win32":
        try:
            from waitress import serve as waitress_serve
            _FLASK_READY.set()  # waitress_serve blocks; signal readiness before it starts
            waitress_serve(flask_app, host="127.0.0.1", port=FLASK_PORT,
                           threads=8, channel_timeout=120)
        except ImportError:
            flask_app.run(host="127.0.0.1", port=FLASK_PORT,
                          debug=False, use_reloader=False)
    else:
        flask_app.run(host="127.0.0.1", port=FLASK_PORT,
                      debug=False, use_reloader=False)


def main() -> None:
    ensure_data_dirs()
    _slog.init(DATA_DIR / "startup.log")
    _slog.t("main: start")

    ignore_pos = "-ignore_start_positions" in sys.argv

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    _slog.t("flask thread started")

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

    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap, QColor
    from PyQt6.QtCore import Qt

    pix = QPixmap(400, 120)
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
