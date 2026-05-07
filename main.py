import sys
import threading
import time

from PyQt6.QtWidgets import QApplication

from backend.app import create_app
from gui.main_window import MainWindow

FLASK_PORT = 5174


def start_flask():
    app = create_app()
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False, use_reloader=False)


def main():
    ignore_pos = "-ignore_start_positions" in sys.argv

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(0.5)

    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("LosslessBob Checksum Lookup")

    window = MainWindow(flask_port=FLASK_PORT, ignore_saved_pos=ignore_pos)
    window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
