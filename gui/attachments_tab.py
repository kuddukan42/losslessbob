from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QThread, QTimer, pyqtSignal,
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
)
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableView, QHeaderView, QListWidget, QListWidgetItem,
    QAbstractItemView,
    QPushButton, QTextEdit, QLabel, QStackedWidget, QLineEdit, QMenu,
)

from backend.paths import attachment_path
import gui.styles as styles
import logging

log = logging.getLogger(__name__)
from backend.scraper import DETAIL_URL


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class _LbModel(QAbstractTableModel):
    """Flat table: one row per LB entry that has cached attachment files."""

    _HEADERS = ["LB Number", "Files"]
    def __init__(self, entries: list[dict], parent=None):
        super().__init__(parent)
        self._entries = entries

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 2

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{entry['lb_number']:05d}"
            return str(len(entry["files"]))
        if role == Qt.ItemDataRole.BackgroundRole:
            status = entry.get("lb_status")
            _lb_color = {"private": styles.ROW_PRIVATE, "missing": styles.ROW_GREY}.get(status)
            if _lb_color:
                return QBrush(_lb_color)
        if role == Qt.ItemDataRole.ToolTipRole and col == 0:
            status = entry.get("lb_status")
            if status == "private":
                return "Private LB — no published webpage"
            if status == "missing":
                return "Missing LB — not in DB"
        if role == Qt.ItemDataRole.UserRole:
            return entry
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[section]
        return None


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _RefreshTreeThread(QThread):
    """Reconciles entry_files with site_inventory via API, then fetches grouped data.

    Emits: finished(all_lb_entries: list[dict], total_entries: int)
    Each entry dict: {lb_number, files: [{filename, clean_name}], lb_status}
    """

    finished = pyqtSignal(list, int)

    def __init__(self, flask_port: int):
        super().__init__()
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            base = f"http://127.0.0.1:{self.flask_port}"
            resp = requests.post(f"{base}/api/attachments/reconcile", timeout=30)
            if resp.ok:
                updated = resp.json().get("updated", 0)
                if updated:
                    log.debug("_reconcile: marked %d rows downloaded=1", updated)
            data = requests.get(f"{base}/api/attachments/cached", timeout=30).json()
            self.finished.emit(data.get("entries", []), data.get("total", 0))
        except Exception:
            log.exception("_RefreshTreeThread failed")
            self.finished.emit([], 0)


class _ScrapeThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, lb_number: int):
        super().__init__()
        self.flask_port = flask_port
        self.lb_number = lb_number

    def run(self) -> None:
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

    def __init__(self, flask_port: int):
        super().__init__()
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/missing_lb_numbers",
                timeout=30,
            )
            self.finished.emit(resp.json())
        except Exception:
            self.finished.emit([])


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class AttachmentsTab(QWidget):

    def __init__(self, flask_port: int, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._scrape_thread: _ScrapeThread | None = None
        self._missing_thread: _MissingThread | None = None
        self._refresh_thread: _RefreshTreeThread | None = None
        self._tree_loaded = False
        self._missing_loaded = False
        self._cached_count = 0
        self._missing_count = 0
        self._in_missing_view = False
        self._all_lb_entries: list[dict] = []
        self._current_lb: int | None = None
        self._current_file: Path | None = None
        self._lb_model: _LbModel | None = None
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(0)
        self.web_view = None
        self._build_ui()
        QTimer.singleShot(0, self._init_web_view)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel ────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.top_label = QLabel(self.tr("Loading..."))
        left_layout.addWidget(self.top_label)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(2)
        self.btn_cached = QPushButton(self.tr("Cached"))
        self.btn_cached.setCheckable(True)
        self.btn_cached.setChecked(True)
        self.btn_cached.clicked.connect(self._show_cached)
        self.btn_missing = QPushButton(self.tr("Missing"))
        self.btn_missing.setCheckable(True)
        self.btn_missing.clicked.connect(self._show_missing)
        toggle_row.addWidget(self.btn_cached)
        toggle_row.addWidget(self.btn_missing)
        left_layout.addLayout(toggle_row)

        # Stacked: index 0 = cached split-view, index 1 = missing list
        self.left_stack = QStackedWidget()

        # Cached view: LB table (top) + file list (bottom)
        cached_widget = QWidget()
        cached_layout = QVBoxLayout(cached_widget)
        cached_layout.setContentsMargins(0, 0, 0, 0)
        cached_layout.setSpacing(2)

        self.lb_table = QTableView()
        self.lb_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lb_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lb_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lb_table.horizontalHeader().setStretchLastSection(True)
        self.lb_table.verticalHeader().setVisible(False)
        self.lb_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lb_table.customContextMenuRequested.connect(self._lb_table_context_menu)
        self.lb_table.setModel(self._proxy)
        self.lb_table.selectionModel().currentRowChanged.connect(self._on_lb_row_changed)
        cached_layout.addWidget(self.lb_table, stretch=3)

        self.file_list = QListWidget()
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_list_context_menu)
        self.file_list.currentItemChanged.connect(self._on_file_changed)
        cached_layout.addWidget(self.file_list, stretch=1)

        self.left_stack.addWidget(cached_widget)

        # Missing view
        self.missing_list = QListWidget()
        self.missing_list.itemClicked.connect(self._on_missing_item_clicked)
        self.missing_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.missing_list.customContextMenuRequested.connect(self._missing_context_menu)
        self.left_stack.addWidget(self.missing_list)

        left_layout.addWidget(self.left_stack, stretch=1)

        # Filter / jump-to box
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Filter / jump to LB number…"))
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit)
        left_layout.addLayout(search_row)

        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self._refresh_current)
        left_layout.addWidget(self.refresh_btn)

        splitter.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.file_label = QLabel(self.tr("Select a file to preview."))
        right_layout.addWidget(self.file_label)

        self.stack = QStackedWidget()

        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.stack.addWidget(self.text_view)   # index 0

        self.other_widget = QWidget()
        other_layout = QVBoxLayout(self.other_widget)
        self.other_label = QLabel("")
        other_layout.addWidget(self.other_label)
        self.open_ext_btn = QPushButton(self.tr("Open Externally"))
        self.open_ext_btn.clicked.connect(self._open_externally)
        other_layout.addWidget(self.open_ext_btn)
        other_layout.addStretch()
        self.stack.addWidget(self.other_widget)  # index 1

        right_layout.addWidget(self.stack)

        btn_row = QHBoxLayout()
        self.download_btn = QPushButton(self.tr("Refresh / Re-download Selected Entry"))
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

    # ------------------------------------------------------------------
    # View toggling
    # ------------------------------------------------------------------

    def _show_cached(self) -> None:
        self.btn_cached.setChecked(True)
        self.btn_missing.setChecked(False)
        self._in_missing_view = False
        self.left_stack.setCurrentIndex(0)
        self.download_btn.setText(self.tr("Refresh / Re-download Selected Entry"))
        self.download_btn.setEnabled(self._current_lb is not None)
        self.file_label.setText(self.tr("Select a file to preview."))

    def _show_missing(self) -> None:
        self.btn_missing.setChecked(True)
        self.btn_cached.setChecked(False)
        self._in_missing_view = True
        self.left_stack.setCurrentIndex(1)
        self.download_btn.setText(self.tr("Scrape Selected Entry"))
        self.download_btn.setEnabled(False)
        self._current_lb = None
        self.file_label.setText(self.tr("Select a missing LB entry to scrape."))
        if not self._missing_loaded:
            self._refresh_missing()

    def _refresh_current(self) -> None:
        if self._in_missing_view:
            self._refresh_missing()
        else:
            self._refresh_tree()

    def _update_toggle_labels(self) -> None:
        self.btn_cached.setText(self.tr("Cached ({})").format(self._cached_count))
        self.btn_missing.setText(self.tr("Missing ({})").format(self._missing_count))

    # ------------------------------------------------------------------
    # Cached (table) view
    # ------------------------------------------------------------------

    def _refresh_tree(self) -> None:
        self.top_label.setText(self.tr("Loading cached files…"))
        self.refresh_btn.setEnabled(False)
        self._refresh_thread = _RefreshTreeThread(self.flask_port)
        self._refresh_thread.finished.connect(self._on_tree_data_ready)
        self._refresh_thread.start()

    def _on_tree_data_ready(self, all_lb_entries: list, total_entries: int) -> None:
        self.refresh_btn.setEnabled(True)
        self._all_lb_entries = all_lb_entries
        self._cached_count = len(all_lb_entries)
        self.top_label.setText(
            self.tr("Entries with cached files: {} / {}").format(self._cached_count, total_entries)
        )
        self._update_toggle_labels()

        # Swap source model — proxy and view selection model are reused
        self._lb_model = _LbModel(all_lb_entries, self)
        self._proxy.setSourceModel(self._lb_model)
        self.lb_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

        self.file_list.clear()
        self._current_lb = None
        self.download_btn.setEnabled(False)

    def _on_lb_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid() or self._lb_model is None:
            self.file_list.clear()
            self._current_lb = None
            self.download_btn.setEnabled(False)
            return

        source_idx = self._proxy.mapToSource(
            self._proxy.index(current.row(), 0)
        )
        entry = self._lb_model.data(source_idx, Qt.ItemDataRole.UserRole)
        if entry is None:
            return

        self._current_lb = entry["lb_number"]
        self.download_btn.setEnabled(True)
        self.file_label.setText(self.tr("Selected: LB-{}").format(f"{self._current_lb:05d}"))

        self.file_list.clear()
        for frow in entry["files"]:
            item = QListWidgetItem(frow["clean_name"])
            item.setData(Qt.ItemDataRole.UserRole, str(attachment_path(frow["filename"])))
            self.file_list.addItem(item)

    def _on_file_changed(self, current: QListWidgetItem | None,
                         _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        self._current_file = path
        self.file_label.setText(path.name)
        self._preview_file(path)

    def _on_search_changed(self, text: str) -> None:
        raw = text.strip().upper()
        # Allow bare numeric input: "1234" matches "LB-01234"
        if raw.isdigit():
            raw = f"LB-{int(raw):05d}"
        self._proxy.setFilterFixedString(raw)

    # ------------------------------------------------------------------
    # Missing view
    # ------------------------------------------------------------------

    def _refresh_missing(self) -> None:
        self.missing_list.clear()
        self.missing_list.addItem(self.tr("Loading…"))
        self.refresh_btn.setEnabled(False)
        self._missing_thread = _MissingThread(self.flask_port)
        self._missing_thread.finished.connect(self._on_missing_loaded)
        self._missing_thread.start()

    def _on_missing_loaded(self, numbers: list) -> None:
        self._missing_loaded = True
        self.missing_list.clear()
        for n in numbers:
            self.missing_list.addItem(f"LB-{n:05d}")
        self._missing_count = len(numbers)
        self._update_toggle_labels()
        self.refresh_btn.setEnabled(True)

    def _on_missing_item_clicked(self, item: QListWidgetItem) -> None:
        text = item.text()
        try:
            self._current_lb = int(text.replace("LB-", ""))
            self.download_btn.setEnabled(True)
        except ValueError:
            pass
        self.file_label.setText(
            self.tr("Missing: {} — click Scrape to attempt download").format(text)
        )

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    def _lb_table_context_menu(self, pos) -> None:
        idx = self.lb_table.indexAt(pos)
        if not idx.isValid() or self._lb_model is None:
            return
        source_idx = self._proxy.mapToSource(self._proxy.index(idx.row(), 0))
        entry = self._lb_model.data(source_idx, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        lb_num = entry["lb_number"]
        menu = QMenu(self)
        act = menu.addAction(self.tr("Open LB-{} in browser pane").format(f"{lb_num:05d}"))
        act.triggered.connect(lambda: self._open_lb_in_webview(lb_num))
        menu.exec(self.lb_table.viewport().mapToGlobal(pos))

    def _file_list_context_menu(self, pos) -> None:
        if self._current_lb is None:
            return
        menu = QMenu(self)
        act = menu.addAction(
            self.tr("Open LB-{} in browser pane").format(f"{self._current_lb:05d}")
        )
        act.triggered.connect(lambda: self._open_lb_in_webview(self._current_lb))
        menu.exec(self.file_list.viewport().mapToGlobal(pos))

    def _missing_context_menu(self, pos) -> None:
        item = self.missing_list.itemAt(pos)
        if item is None:
            return
        try:
            lb_num = int(item.text().replace("LB-", ""))
        except ValueError:
            return
        menu = QMenu(self)
        act = menu.addAction(self.tr("Open LB-{} in browser pane").format(item.text()))
        act.triggered.connect(lambda: self._open_lb_in_webview(lb_num))
        menu.exec(self.missing_list.viewport().mapToGlobal(pos))

    def _open_lb_in_webview(self, lb_num: int) -> None:
        if self.web_view is None:
            return
        url = QUrl(DETAIL_URL.format(n=f"{lb_num:05d}"))
        self.web_view.load(url)
        self.stack.setCurrentWidget(self.web_view)
        self.file_label.setText(self.tr("LB-{} — entry page").format(f"{lb_num:05d}"))

    # ------------------------------------------------------------------
    # showEvent / WebEngine lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._tree_loaded:
            self._tree_loaded = True
            self._refresh_tree()

    def _init_web_view(self) -> None:
        if self.web_view is not None:
            return
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
            from PyQt6.QtWidgets import QApplication
            from backend.paths import WEBENGINE_DIR
            WEBENGINE_DIR.mkdir(parents=True, exist_ok=True)
            self._web_profile = QWebEngineProfile("losslessbob")
            self._web_profile.setPersistentStoragePath(str(WEBENGINE_DIR))
            self._web_profile.setCachePath(str(WEBENGINE_DIR / "cache"))
            self._web_profile.setHttpCacheMaximumSize(32 * 1024 * 1024)
            self._web_page = QWebEnginePage(self._web_profile, self._web_profile)
            self.web_view = QWebEngineView(self)
            self.web_view.setPage(self._web_page)
            self.stack.addWidget(self.web_view)  # index 2
            self.web_view.load(QUrl("about:blank"))
            QApplication.instance().aboutToQuit.connect(self._cleanup_webengine)
        except ImportError:
            pass

    def _cleanup_webengine(self) -> None:
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

    def _preview_file(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in (".txt", ".ffp", ".md5", ".st5"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                self.text_view.setPlainText(text)
            except Exception as e:
                self.text_view.setPlainText(self.tr("Error reading file: {}").format(e))
            self.stack.setCurrentWidget(self.text_view)
        elif suffix in (".html", ".htm") and self.web_view is not None:
            self.web_view.load(QUrl.fromLocalFile(str(path)))
            self.stack.setCurrentWidget(self.web_view)
        else:
            self.other_label.setText(
                self.tr("File: {}\nNo in-app preview available.").format(path.name)
            )
            self.stack.setCurrentWidget(self.other_widget)

    def _open_externally(self) -> None:
        if not self._current_file:
            return
        from gui.platform_utils import open_file
        try:
            open_file(self._current_file)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("Open Failed"), str(e))

    # ------------------------------------------------------------------
    # Scrape / download
    # ------------------------------------------------------------------

    def _on_download_all(self) -> None:
        if self._current_lb is None:
            return
        self.download_btn.setEnabled(False)
        self.download_status.setText(
            self.tr("Scraping LB-{}...").format(f"{self._current_lb:05d}")
        )
        self._scrape_thread = _ScrapeThread(self.flask_port, self._current_lb)
        self._scrape_thread.finished.connect(self._on_scrape_done)
        self._scrape_thread.start()

    def _on_scrape_done(self, result: dict) -> None:
        self.download_btn.setEnabled(True)
        if "error" in result:
            self.download_status.setText(self.tr("Error: {}").format(result["error"]))
            return

        downloaded = result.get("files_downloaded", [])
        if self._in_missing_view:
            if downloaded:
                target = f"LB-{self._current_lb:05d}"
                for i in range(self.missing_list.count()):
                    if self.missing_list.item(i).text() == target:
                        self.missing_list.takeItem(i)
                        self._missing_count -= 1
                        self._update_toggle_labels()
                        break
                self.download_status.setText(
                    self.tr("Downloaded {} file(s) — entry moved to Cached.").format(
                        len(downloaded)
                    )
                )
                self._tree_loaded = False
            else:
                self.download_status.setText(
                    self.tr("No attachments found for LB-{} — confirmed gap.").format(
                        f"{self._current_lb:05d}"
                    )
                )
        else:
            self.download_status.setText(
                self.tr("Downloaded {} file(s).").format(len(downloaded))
            )
            self._refresh_tree()
