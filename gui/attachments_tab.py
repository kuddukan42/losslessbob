import subprocess
import sys
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QPushButton, QTextEdit, QLabel, QStackedWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

ATTACHMENTS_DIR = Path(__file__).parent.parent / "data" / "attachments"


class _ScrapeThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port, lb_number):
        super().__init__()
        self.flask_port = flask_port
        self.lb_number = lb_number

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{self.lb_number}/scrape",
                json={"force": True},
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


class AttachmentsTab(QWidget):
    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._scrape_thread = None
        self._build_ui()
        self._refresh_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.top_label = QLabel("Loading...")
        layout.addWidget(self.top_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("LB Entries with Cached Files")
        self.tree.itemClicked.connect(self._on_item_clicked)
        left_layout.addWidget(self.tree)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_tree)
        left_layout.addWidget(self.refresh_btn)

        splitter.addWidget(left)

        # Right panel: file viewer
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.file_label = QLabel("Select a file to preview.")
        right_layout.addWidget(self.file_label)

        self.stack = QStackedWidget()

        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.stack.addWidget(self.text_view)

        if _HAS_WEBENGINE:
            self.web_view = QWebEngineView()
            self.stack.addWidget(self.web_view)
        else:
            self.web_view = None

        self.other_widget = QWidget()
        other_layout = QVBoxLayout(self.other_widget)
        self.other_label = QLabel("")
        other_layout.addWidget(self.other_label)
        self.open_ext_btn = QPushButton("Open Externally")
        self.open_ext_btn.clicked.connect(self._open_externally)
        other_layout.addWidget(self.open_ext_btn)
        other_layout.addStretch()
        self.stack.addWidget(self.other_widget)

        right_layout.addWidget(self.stack)

        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Refresh / Re-download Selected Entry")
        self.download_btn.clicked.connect(self._on_download_all)
        self.download_btn.setEnabled(False)
        btn_row.addWidget(self.download_btn)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        self.download_status = QLabel("")
        right_layout.addWidget(self.download_status)

        splitter.addWidget(right)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter)

        self._current_file = None
        self._current_lb = None

    def _refresh_tree(self):
        self.tree.clear()
        entries_with_files = 0
        total_entries = 0

        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5)
            stats = resp.json()
            total_entries = stats.get("total_lb_numbers", 0)
        except Exception:
            pass

        if not ATTACHMENTS_DIR.exists():
            self.top_label.setText(f"Entries with cached files: 0 / {total_entries}")
            return

        for lb_dir in sorted(ATTACHMENTS_DIR.iterdir()):
            if not lb_dir.is_dir():
                continue
            files = list(lb_dir.iterdir())
            if not files:
                continue
            entries_with_files += 1
            lb_name = lb_dir.name
            parent_item = QTreeWidgetItem(self.tree, [lb_name])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "lb", "lb_dir": str(lb_dir)})
            for f in sorted(files):
                child = QTreeWidgetItem(parent_item, [f.name])
                child.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": str(f)})

        self.top_label.setText(f"Entries with cached files: {entries_with_files} / {total_entries}")

    def _on_item_clicked(self, item, col):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "lb":
            lb_str = item.text(0)
            try:
                self._current_lb = int(lb_str.replace("LB-", ""))
                self.download_btn.setEnabled(True)
            except ValueError:
                pass
            self.file_label.setText(f"Selected: {lb_str}")
            return

        if data["type"] == "file":
            path = Path(data["path"])
            self._current_file = path
            parent = item.parent()
            if parent:
                lb_str = parent.text(0)
                try:
                    self._current_lb = int(lb_str.replace("LB-", ""))
                    self.download_btn.setEnabled(True)
                except ValueError:
                    pass
            self.file_label.setText(str(path.name))
            self._preview_file(path)

    def _preview_file(self, path):
        suffix = path.suffix.lower()
        if suffix in (".txt", ".ffp", ".md5", ".st5"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                self.text_view.setPlainText(text)
                self.stack.setCurrentIndex(0)
            except Exception as e:
                self.text_view.setPlainText(f"Error reading file: {e}")
                self.stack.setCurrentIndex(0)
        elif suffix in (".html", ".htm") and _HAS_WEBENGINE and self.web_view:
            from PyQt6.QtCore import QUrl
            self.web_view.load(QUrl.fromLocalFile(str(path)))
            self.stack.setCurrentIndex(1)
        else:
            self.other_label.setText(f"File: {path.name}\nNo in-app preview available.")
            self.stack.setCurrentIndex(2)

    def _open_externally(self):
        if not self._current_file:
            return
        if sys.platform == "win32":
            import os
            os.startfile(str(self._current_file))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(self._current_file)])
        else:
            subprocess.run(["xdg-open", str(self._current_file)])

    def _on_download_all(self):
        if self._current_lb is None:
            return
        self.download_btn.setEnabled(False)
        self.download_status.setText(f"Scraping LB-{self._current_lb}...")

        self._scrape_thread = _ScrapeThread(self.flask_port, self._current_lb)
        self._scrape_thread.finished.connect(self._on_scrape_done)
        self._scrape_thread.start()

    def _on_scrape_done(self, result):
        self.download_btn.setEnabled(True)
        if "error" in result:
            self.download_status.setText(f"Error: {result['error']}")
        else:
            downloaded = result.get("files_downloaded", [])
            self.download_status.setText(f"Downloaded {len(downloaded)} file(s).")
            self._refresh_tree()
