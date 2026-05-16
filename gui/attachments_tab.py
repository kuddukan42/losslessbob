from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QPushButton, QTextEdit, QLabel, QStackedWidget, QLineEdit, QListWidget, QMenu,
)

from backend.paths import ATTACHMENTS_DIR
from backend.scraper import DETAIL_URL


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


class _MissingThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/missing_lb_numbers",
                timeout=30,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit([])


class AttachmentsTab(QWidget):
    PAGE_SIZE = 1000

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._scrape_thread = None
        self._missing_thread = None
        self._tree_loaded = False
        self._missing_loaded = False
        self._cached_count = 0
        self._missing_count = 0
        self._in_missing_view = False
        self._page = 0
        self._all_lb_dirs = []
        self._build_ui()
        # Schedule WebEngine init on the first event-loop tick so it warms up
        # during app startup rather than on first tab visit or first URL load.
        QTimer.singleShot(0, self._init_web_view)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.top_label = QLabel("Loading...")
        left_layout.addWidget(self.top_label)

        # Cached / Missing toggle buttons
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(2)
        self.btn_cached = QPushButton("Cached")
        self.btn_cached.setCheckable(True)
        self.btn_cached.setChecked(True)
        self.btn_cached.clicked.connect(self._show_cached)
        self.btn_missing = QPushButton("Missing")
        self.btn_missing.setCheckable(True)
        self.btn_missing.setChecked(False)
        self.btn_missing.clicked.connect(self._show_missing)
        toggle_row.addWidget(self.btn_cached)
        toggle_row.addWidget(self.btn_missing)
        left_layout.addLayout(toggle_row)

        # Stacked: index 0 = tree, index 1 = missing list
        self.left_stack = QStackedWidget()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("LB Entries with Cached Files")
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.left_stack.addWidget(self.tree)

        self.missing_list = QListWidget()
        self.missing_list.itemClicked.connect(self._on_missing_item_clicked)
        self.missing_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.missing_list.customContextMenuRequested.connect(self._missing_context_menu)
        self.left_stack.addWidget(self.missing_list)

        left_layout.addWidget(self.left_stack, stretch=1)

        # Page navigation (cached tree only)
        self.page_nav_widget = QWidget()
        page_nav_row = QHBoxLayout(self.page_nav_widget)
        page_nav_row.setContentsMargins(0, 0, 0, 0)
        page_nav_row.setSpacing(4)
        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setFixedWidth(60)
        self.prev_btn.clicked.connect(self._prev_page)
        self.page_label = QLabel("Page 1 / 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setFixedWidth(60)
        self.next_btn.clicked.connect(self._next_page)
        page_nav_row.addWidget(self.prev_btn)
        page_nav_row.addWidget(self.page_label, stretch=1)
        page_nav_row.addWidget(self.next_btn)
        left_layout.addWidget(self.page_nav_widget)

        # Search / jump-to box
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Jump to LB number…")
        self.search_edit.returnPressed.connect(self._jump_to_lb)
        search_row.addWidget(self.search_edit)
        self.search_btn = QPushButton("Go")
        self.search_btn.setFixedWidth(40)
        self.search_btn.clicked.connect(self._jump_to_lb)
        search_row.addWidget(self.search_btn)
        left_layout.addLayout(search_row)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_current)
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
        splitter.setSizes([420, 580])
        layout.addWidget(splitter, stretch=1)

        self._current_file = None
        self._current_lb = None

    # ------------------------------------------------------------------
    # View toggling
    # ------------------------------------------------------------------

    def _show_cached(self):
        self.btn_cached.setChecked(True)
        self.btn_missing.setChecked(False)
        self._in_missing_view = False
        self.left_stack.setCurrentIndex(0)
        self.page_nav_widget.setVisible(True)
        self.download_btn.setText("Refresh / Re-download Selected Entry")
        self.download_btn.setEnabled(False)
        self._current_lb = None
        self.file_label.setText("Select a file to preview.")

    def _show_missing(self):
        self.btn_missing.setChecked(True)
        self.btn_cached.setChecked(False)
        self._in_missing_view = True
        self.left_stack.setCurrentIndex(1)
        self.page_nav_widget.setVisible(False)
        self.download_btn.setText("Scrape Selected Entry")
        self.download_btn.setEnabled(False)
        self._current_lb = None
        self.file_label.setText("Select a missing LB entry to scrape.")
        if not self._missing_loaded:
            self._refresh_missing()

    def _refresh_current(self):
        if self._in_missing_view:
            self._refresh_missing()
        else:
            self._refresh_tree()

    def _update_toggle_labels(self):
        self.btn_cached.setText(f"Cached ({self._cached_count})")
        self.btn_missing.setText(f"Missing ({self._missing_count})")

    # ------------------------------------------------------------------
    # Tree (cached) view
    # ------------------------------------------------------------------

    def _refresh_tree(self):
        total_entries = 0
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5)
            stats = resp.json()
            total_entries = stats.get("total_lb_numbers", 0)
        except Exception:
            pass

        self._all_lb_dirs = []
        if ATTACHMENTS_DIR.exists():
            for lb_dir in sorted(ATTACHMENTS_DIR.iterdir()):
                if not lb_dir.is_dir():
                    continue
                if any(lb_dir.iterdir()):
                    self._all_lb_dirs.append(lb_dir)

        self._cached_count = len(self._all_lb_dirs)
        self.top_label.setText(
            f"Entries with cached files: {self._cached_count} / {total_entries}"
        )
        self._update_toggle_labels()
        self._page = 0
        self._render_tree_page()

    def _render_tree_page(self):
        total_pages = max(1, (len(self._all_lb_dirs) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self._page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        for lb_dir in self._all_lb_dirs[start:end]:
            lb_name = lb_dir.name
            parent_item = QTreeWidgetItem(self.tree, [lb_name])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "lb", "lb_dir": str(lb_dir)})
            for f in sorted(lb_dir.iterdir()):
                child = QTreeWidgetItem(parent_item, [f.name])
                child.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": str(f)})
        self.tree.setUpdatesEnabled(True)
        self.tree.scrollToTop()
        self.page_label.setText(f"Page {self._page + 1} / {total_pages}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < total_pages - 1)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_tree_page()

    def _next_page(self):
        total_pages = max(1, (len(self._all_lb_dirs) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._page < total_pages - 1:
            self._page += 1
            self._render_tree_page()

    def _on_tree_item_clicked(self, item, col):
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

    # ------------------------------------------------------------------
    # Missing view
    # ------------------------------------------------------------------

    def _refresh_missing(self):
        self.missing_list.clear()
        self.missing_list.addItem("Loading…")
        self.refresh_btn.setEnabled(False)
        self._missing_thread = _MissingThread(self.flask_port)
        self._missing_thread.finished.connect(self._on_missing_loaded)
        self._missing_thread.start()

    def _on_missing_loaded(self, numbers: list):
        self._missing_loaded = True
        self.missing_list.clear()
        for n in numbers:
            self.missing_list.addItem(f"LB-{n:05d}")
        self._missing_count = len(numbers)
        self._update_toggle_labels()
        self.refresh_btn.setEnabled(True)

    def _on_missing_item_clicked(self, item):
        text = item.text()
        try:
            self._current_lb = int(text.replace("LB-", ""))
            self.download_btn.setEnabled(True)
        except ValueError:
            pass
        self.file_label.setText(f"Missing: {text} — click Scrape to attempt download")

    # ------------------------------------------------------------------
    # Jump-to search box
    # ------------------------------------------------------------------

    def _jump_to_lb(self):
        raw = self.search_edit.text().strip().upper()
        if not raw:
            return
        lb_str = raw.removeprefix("LB-").removeprefix("LB")
        try:
            num = int(lb_str)
            target = f"LB-{num:05d}"
        except ValueError:
            return

        if self._in_missing_view:
            for i in range(self.missing_list.count()):
                item = self.missing_list.item(i)
                if item.text() == target:
                    self.missing_list.setCurrentItem(item)
                    self.missing_list.scrollToItem(item)
                    self.search_edit.clear()
                    return
        else:
            for idx, lb_dir in enumerate(self._all_lb_dirs):
                if lb_dir.name == target:
                    page = idx // self.PAGE_SIZE
                    if page != self._page:
                        self._page = page
                        self._render_tree_page()
                    for i in range(self.tree.topLevelItemCount()):
                        item = self.tree.topLevelItem(i)
                        if item.text(0) == target:
                            self.tree.setCurrentItem(item)
                            self.tree.scrollToItem(item)
                            self.search_edit.clear()
                            return
                    break

    # ------------------------------------------------------------------
    # Context menus — open LB entry page in embedded browser
    # ------------------------------------------------------------------

    def _tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        lb_str = item.text(0) if data["type"] == "lb" else item.parent().text(0) if item.parent() else None
        if not lb_str:
            return
        try:
            lb_num = int(lb_str.replace("LB-", ""))
        except ValueError:
            return
        menu = QMenu(self)
        act = menu.addAction(f"Open {lb_str} in browser pane")
        act.triggered.connect(lambda: self._open_lb_in_webview(lb_num))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _missing_context_menu(self, pos):
        item = self.missing_list.itemAt(pos)
        if not item:
            return
        try:
            lb_num = int(item.text().replace("LB-", ""))
        except ValueError:
            return
        menu = QMenu(self)
        act = menu.addAction(f"Open {item.text()} in browser pane")
        act.triggered.connect(lambda: self._open_lb_in_webview(lb_num))
        menu.exec(self.missing_list.viewport().mapToGlobal(pos))

    def _open_lb_in_webview(self, lb_num: int):
        if self.web_view is None:
            return  # QtWebEngine unavailable
        url = QUrl(DETAIL_URL.format(n=f"{lb_num:05d}"))
        self.web_view.load(url)
        self.stack.setCurrentWidget(self.web_view)
        self.file_label.setText(f"LB-{lb_num:05d} — entry page")

    # ------------------------------------------------------------------
    # showEvent / WebEngine lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._tree_loaded:
            self._tree_loaded = True
            self._refresh_tree()

    def _init_web_view(self) -> None:
        """Create the QWebEngineView and warm up the renderer process."""
        if self.web_view is not None:
            return
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
            from PyQt6.QtWidgets import QApplication
            from backend.paths import WEBENGINE_DIR
            WEBENGINE_DIR.mkdir(parents=True, exist_ok=True)
            # No Qt parent on the profile — lifecycle is managed explicitly by
            # _cleanup_webengine so we can guarantee view → page → profile order.
            self._web_profile = QWebEngineProfile("losslessbob")
            self._web_profile.setPersistentStoragePath(str(WEBENGINE_DIR))
            self._web_profile.setCachePath(str(WEBENGINE_DIR / "cache"))
            self._web_profile.setHttpCacheMaximumSize(32 * 1024 * 1024)
            self._web_page = QWebEnginePage(self._web_profile, self._web_profile)
            self.web_view = QWebEngineView(self)
            self.web_view.setPage(self._web_page)
            self.stack.addWidget(self.web_view)
            # Warm up the GPU/renderer process now so the first user-triggered
            # load doesn't cause a native-window flash on Linux.
            self.web_view.load(QUrl("about:blank"))
            QApplication.instance().aboutToQuit.connect(self._cleanup_webengine)
        except ImportError:
            pass

    def _cleanup_webengine(self) -> None:
        """Destroy WebEngine objects in safe order: view → page → profile."""
        from PyQt6 import sip
        if self.web_view is not None and not sip.isdeleted(self.web_view):
            sip.delete(self.web_view)
            self.web_view = None
        page = getattr(self, "_web_page", None)
        if page is not None and not sip.isdeleted(page):
            sip.delete(page)
            self._web_page = None
        profile = getattr(self, "_web_profile", None)
        if profile is not None and not sip.isdeleted(profile):
            sip.delete(profile)
            self._web_profile = None

    # ------------------------------------------------------------------
    # File preview
    # ------------------------------------------------------------------

    def _preview_file(self, path):
        suffix = path.suffix.lower()
        if suffix in (".txt", ".ffp", ".md5", ".st5"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                self.text_view.setPlainText(text)
            except Exception as e:
                self.text_view.setPlainText(f"Error reading file: {e}")
            self.stack.setCurrentWidget(self.text_view)
        elif suffix in (".html", ".htm") and self.web_view is not None:
            self.web_view.load(QUrl.fromLocalFile(str(path)))
            self.stack.setCurrentWidget(self.web_view)
        else:
            self.other_label.setText(f"File: {path.name}\nNo in-app preview available.")
            self.stack.setCurrentWidget(self.other_widget)

    def _open_externally(self):
        if not self._current_file:
            return
        from gui.platform_utils import open_file
        try:
            open_file(self._current_file)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Open Failed", str(e))

    # ------------------------------------------------------------------
    # Scrape / download
    # ------------------------------------------------------------------

    def _on_download_all(self):
        if self._current_lb is None:
            return
        self.download_btn.setEnabled(False)
        self.download_status.setText(f"Scraping LB-{self._current_lb:05d}...")

        self._scrape_thread = _ScrapeThread(self.flask_port, self._current_lb)
        self._scrape_thread.finished.connect(self._on_scrape_done)
        self._scrape_thread.start()

    def _on_scrape_done(self, result):
        self.download_btn.setEnabled(True)
        if "error" in result:
            self.download_status.setText(f"Error: {result['error']}")
            return

        downloaded = result.get("files_downloaded", [])
        if self._in_missing_view:
            if downloaded:
                # Remove from missing list — entry now has cached files
                target = f"LB-{self._current_lb:05d}"
                for i in range(self.missing_list.count()):
                    if self.missing_list.item(i).text() == target:
                        self.missing_list.takeItem(i)
                        self._missing_count -= 1
                        self._update_toggle_labels()
                        break
                self.download_status.setText(f"Downloaded {len(downloaded)} file(s) — entry moved to Cached.")
                self._tree_loaded = False  # force tree refresh next time cached view opens
            else:
                self.download_status.setText(
                    f"No attachments found for LB-{self._current_lb:05d} — confirmed gap."
                )
        else:
            self.download_status.setText(f"Downloaded {len(downloaded)} file(s).")
            self._refresh_tree()
