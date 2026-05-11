import sys
import socket
import threading
import time

from PyQt6.QtWidgets import QApplication

from backend.app import create_app
from backend.paths import ensure_data_dirs

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
    ignore_pos = "-ignore_start_positions" in sys.argv

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    if not _wait_for_port("127.0.0.1", FLASK_PORT, timeout=15.0):
        QApplication(sys.argv)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Startup Error",
            f"Flask backend did not start on port {FLASK_PORT}.\n"
            "Another process may be using that port.\n"
            "Try restarting the application.",
        )
        sys.exit(1)

    from gui.main_window import MainWindow

    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("LosslessBob Checksum Lookup")

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    window.show()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
