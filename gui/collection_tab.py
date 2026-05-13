import csv
import math
import re
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QThread, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableView, QPushButton,
    QLabel, QLineEdit, QAbstractItemView, QHeaderView, QMenu, QDialog,
    QFormLayout, QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QSpinBox,
)

from gui.styles import ROW_OWNED, ROW_WISHLIST

_LB_RE = re.compile(r'LB-0*(\d+)', re.IGNORECASE)

COLL_HEADERS = ["LB Number", "Date", "Location", "Folder Name", "Disk Path", "Confirmed", "Notes"]
MISS_HEADERS = ["LB Number", "Date", "Location", "Rating", "Description"]


def _extract_lb(name):
    m = _LB_RE.search(name)
    return int(m.group(1)) if m else None


class _CollectionModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._all_rows = []
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLL_HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{row['lb_number']}"
            if col == 1:
                return row.get("date_str") or ""
            if col == 2:
                return row.get("location") or ""
            if col == 3:
                return row.get("folder_name", "")
            if col == 4:
                return row.get("disk_path", "")
            if col == 5:
                v = row.get("confirmed_at", "") or ""
                return str(v)[:10]
            if col == 6:
                return row.get("notes", "") or ""
        if role == Qt.ItemDataRole.FontRole and col in (1, 2):
            val = row.get("date_str") if col == 1 else row.get("location")
            if not val:
                f = QFont()
                f.setItalic(True)
                return f
        if role == Qt.ItemDataRole.ForegroundRole and col in (1, 2):
            val = row.get("date_str") if col == 1 else row.get("location")
            if not val:
                return QColor("#888888")
        if role == Qt.ItemDataRole.BackgroundRole:
            return ROW_OWNED
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLL_HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._all_rows = rows
        self._rows = rows
        self.endResetModel()

    def filter(self, text):
        self.beginResetModel()
        if not text:
            self._rows = self._all_rows
        else:
            t = text.lower()
            self._rows = [
                r for r in self._all_rows
                if t in str(r.get("lb_number", "")).lower()
                or t in (r.get("folder_name", "") or "").lower()
                or t in (r.get("disk_path", "") or "").lower()
            ]
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None


class _MissingModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(MISS_HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{row.get('lb_number', '')}"
            keys = ["lb_number", "date_str", "location", "rating", "description"]
            val = row.get(keys[col], "") or ""
            if col == 4:
                return str(val)
            return str(val)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return MISS_HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None

    def all_rows(self):
        return list(self._rows)


WISH_HEADERS = ["LB Number", "Date", "Location", "Rating", "Priority", "Notes", "Added"]


class _WishlistModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(WISH_HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{row['lb_number']}"
            if col == 1:
                return row.get("date_str") or ""
            if col == 2:
                return row.get("location") or ""
            if col == 3:
                return row.get("rating") or ""
            if col == 4:
                return str(row.get("priority") or 3)
            if col == 5:
                return row.get("notes") or ""
            if col == 6:
                v = row.get("added_at") or ""
                return str(v)[:10]
        if role == Qt.ItemDataRole.BackgroundRole:
            return ROW_WISHLIST
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return WISH_HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None


class _ApiWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


class _AddDialog(QDialog):
    def __init__(self, lb_number=None, folder_name="", disk_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to My Collection")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.lb_edit = QLineEdit(str(lb_number) if lb_number is not None else "")
        self.folder_edit = QLineEdit(folder_name)
        self.path_edit = QLineEdit(disk_path)
        self.notes_edit = QLineEdit()
        layout.addRow("LB Number:", self.lb_edit)
        layout.addRow("Folder Name:", self.folder_edit)
        layout.addRow("Disk Path:", self.path_edit)
        layout.addRow("Notes:", self.notes_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_values(self):
        try:
            lb = int(self.lb_edit.text().strip())
        except ValueError:
            lb = None
        return {
            "lb_number": lb,
            "folder_name": self.folder_edit.text().strip(),
            "disk_path": self.path_edit.text().strip(),
            "notes": self.notes_edit.text().strip() or None,
        }


class _ScanPreviewDialog(QDialog):
    def __init__(self, entries, owned_set, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Results — Confirm Add")
        self.setMinimumSize(700, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Found {len(entries)} folder(s) with LB numbers:"))

        self.table = QTableWidget(len(entries), 4)
        self.table.setHorizontalHeaderLabels(["LB Number", "Folder Name", "Path", "Already Owned"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, (lb, name, path) in enumerate(entries):
            owned = lb in owned_set
            self.table.setItem(i, 0, QTableWidgetItem(f"LB-{lb}"))
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, QTableWidgetItem(path))
            item = QTableWidgetItem("Yes" if owned else "No")
            if owned:
                item.setForeground(QColor("#388E3C"))
            self.table.setItem(i, 3, item)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        skipped = getattr(self, '_skipped', 0)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Add All")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


class _PersonalMetaDialog(QDialog):
    def __init__(self, lb_number, meta, flask_port, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Personal Info — LB-{lb_number:05d}")
        self._lb = lb_number
        self._flask_port = flask_port
        layout = QFormLayout(self)

        self._rating = QComboBox()
        self._rating.addItem("— none —", userData=None)
        for i in range(1, 6):
            self._rating.addItem("★" * i, userData=i)
        current_rating = meta.get("personal_rating")
        if current_rating:
            self._rating.setCurrentIndex(current_rating)
        layout.addRow("Rating:", self._rating)

        self._tags = QLineEdit(meta.get("tags") or "")
        layout.addRow("Tags:", self._tags)

        listen_count = meta.get("listen_count") or 0
        last = meta.get("last_listened") or "never"
        self._listen_label = QLabel(f"{listen_count}  (last: {str(last)[:19]})")
        layout.addRow("Listen count:", self._listen_label)

        log_btn = QPushButton("Log Listen")
        log_btn.clicked.connect(self._log_listen)
        layout.addRow("", log_btn)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _log_listen(self):
        try:
            requests.post(
                f"http://127.0.0.1:{self._flask_port}/api/collection/{self._lb}/listen",
                timeout=5,
            )
            resp = requests.get(
                f"http://127.0.0.1:{self._flask_port}/api/collection/{self._lb}/meta",
                timeout=5,
            ).json()
            count = resp.get("listen_count") or 0
            last = resp.get("last_listened") or "never"
            self._listen_label.setText(f"{count}  (last: {str(last)[:19]})")
        except Exception as e:
            self._listen_label.setText(f"Error: {e}")

    def get_values(self):
        return {
            "personal_rating": self._rating.currentData(),
            "tags": self._tags.text().strip() or None,
        }


class CollectionTab(QWidget):
    lookup_lb = pyqtSignal(int)

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._workers = []
        self._all_collection: list = []
        self._page: int = 0
        self._page_size: int = 50
        self._coll_col_widths: list | None = None
        self._miss_col_widths: list | None = None
        self._wish_col_widths: list | None = None
        self._duplicates_loaded: bool = False
        self._load_page_size()
        self._build_ui()
        self.refresh_collection()

    def _load_page_size(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            )
            self._page_size = int(resp.json().get("search_page_size") or 50)
        except Exception:
            pass

    def set_page_size(self, size: int) -> None:
        """Update results-per-page and re-render the current collection."""
        self._page_size = max(1, size)
        self._page = 0
        if self._all_collection:
            self._render_coll_page()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inner_tabs = QTabWidget()
        layout.addWidget(self.inner_tabs)
        self.inner_tabs.addTab(self._build_collection_panel(), "My Collection")
        self.inner_tabs.addTab(self._build_missing_panel(), "Missing")
        self.inner_tabs.addTab(self._build_wishlist_panel(), "Wishlist")
        self.inner_tabs.addTab(self._build_duplicates_panel(), "Duplicates")
        self.inner_tabs.currentChanged.connect(self._on_inner_tab_changed)

    # ── My Collection panel ───────────────────────────────────────────────────

    def _build_collection_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # Filter row: text search + year dropdown
        filter_row = QHBoxLayout()
        self.coll_search = QLineEdit()
        self.coll_search.setPlaceholderText("Filter by LB number, folder name, or path…")
        self.coll_search.textChanged.connect(self._on_coll_filter)
        filter_row.addWidget(self.coll_search)

        self.coll_year_combo = QComboBox()
        self.coll_year_combo.setMinimumWidth(100)
        self.coll_year_combo.addItem("All Years", userData=None)
        self.coll_year_combo.currentIndexChanged.connect(self._on_coll_filter)
        filter_row.addWidget(self.coll_year_combo)
        layout.addLayout(filter_row)

        # Button row
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Single Folder")
        add_btn.clicked.connect(self._on_add_single)
        btn_row.addWidget(add_btn)

        scan_btn = QPushButton("Scan Directory")
        scan_btn.clicked.connect(self._on_scan_directory)
        btn_row.addWidget(scan_btn)

        scan_tree_btn = QPushButton("Scan Tree…")
        scan_tree_btn.setToolTip("Recursively find LB-numbered folders at any depth under a root directory.")
        scan_tree_btn.clicked.connect(self._on_scan_tree)
        btn_row.addWidget(scan_tree_btn)

        self.update_loc_btn = QPushButton("Update Location")
        self.update_loc_btn.clicked.connect(self._on_update_location)
        btn_row.addWidget(self.update_loc_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(self.remove_btn)

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self.coll_view.selectAll())
        btn_row.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: self.coll_view.clearSelection())
        btn_row.addWidget(select_none_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_collection)
        btn_row.addWidget(refresh_btn)

        self._coll_wrap_cb = QCheckBox("Word wrap")
        self._coll_wrap_cb.stateChanged.connect(self._on_coll_wrap_toggled)
        btn_row.addWidget(self._coll_wrap_cb)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Pagination controls
        page_row = QHBoxLayout()
        self._coll_prev_btn = QPushButton("← Prev")
        self._coll_prev_btn.setFixedWidth(80)
        self._coll_prev_btn.clicked.connect(self._coll_prev_page)
        page_row.addWidget(self._coll_prev_btn)
        self._coll_page_label = QLabel("Page 1 of 1")
        page_row.addWidget(self._coll_page_label)
        self._coll_next_btn = QPushButton("Next →")
        self._coll_next_btn.setFixedWidth(80)
        self._coll_next_btn.clicked.connect(self._coll_next_page)
        page_row.addWidget(self._coll_next_btn)
        page_row.addStretch()
        self._coll_page_widget = QWidget()
        self._coll_page_widget.setLayout(page_row)
        self._coll_page_widget.setVisible(False)
        layout.addWidget(self._coll_page_widget)

        self.coll_model = _CollectionModel()
        self.coll_view = QTableView()
        self.coll_view.setModel(self.coll_model)
        self.coll_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.coll_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.coll_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.coll_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.coll_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.coll_view.customContextMenuRequested.connect(self._on_coll_context)
        layout.addWidget(self.coll_view)

        self.coll_status = QLabel("")
        layout.addWidget(self.coll_status)
        return w

    # ── Missing panel ─────────────────────────────────────────────────────────

    def _build_missing_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_missing)
        btn_row.addWidget(refresh_btn)

        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._on_export_csv)
        btn_row.addWidget(export_btn)

        self._miss_wrap_cb = QCheckBox("Word wrap")
        self._miss_wrap_cb.stateChanged.connect(self._on_miss_wrap_toggled)
        btn_row.addWidget(self._miss_wrap_cb)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.miss_model = _MissingModel()
        self.miss_view = QTableView()
        self.miss_view.setModel(self.miss_model)
        self.miss_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.miss_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.miss_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.miss_view.doubleClicked.connect(self._on_missing_double_click)
        layout.addWidget(self.miss_view)

        self.miss_status = QLabel("")
        layout.addWidget(self.miss_status)
        return w

    # ── Wishlist panel ────────────────────────────────────────────────────────

    def _build_wishlist_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_wishlist)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.wish_model = _WishlistModel()
        self.wish_view = QTableView()
        self.wish_view.setModel(self.wish_model)
        self.wish_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.wish_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.wish_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wish_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.wish_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.wish_view.customContextMenuRequested.connect(self._on_wish_context)
        layout.addWidget(self.wish_view)

        self.wish_status = QLabel("")
        layout.addWidget(self.wish_status)
        return w

    # ── Duplicates panel ──────────────────────────────────────────────────────

    def _build_duplicates_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_duplicates)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.dupes_tree = QTreeWidget()
        self.dupes_tree.setColumnCount(2)
        self.dupes_tree.setHeaderLabels(["LB Number / Show", "Rating"])
        self.dupes_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dupes_tree.customContextMenuRequested.connect(self._on_dupes_context)
        layout.addWidget(self.dupes_tree)

        self.dupes_status = QLabel("")
        layout.addWidget(self.dupes_status)
        return w

    def _on_inner_tab_changed(self, index: int) -> None:
        tab_text = self.inner_tabs.tabText(index)
        if tab_text == "Duplicates" and not self._duplicates_loaded:
            self.refresh_duplicates()

    # ── Column sizing & word wrap ─────────────────────────────────────────────

    def _apply_coll_col_widths(self) -> None:
        if not self._coll_col_widths:
            return
        for i, w in enumerate(self._coll_col_widths):
            self.coll_view.setColumnWidth(i, w)

    def _apply_miss_col_widths(self) -> None:
        if not self._miss_col_widths:
            return
        for i, w in enumerate(self._miss_col_widths):
            self.miss_view.setColumnWidth(i, w)

    def _on_coll_wrap_toggled(self, state: int) -> None:
        enabled = bool(state)
        self.coll_view.setWordWrap(enabled)
        vh = self.coll_view.verticalHeader()
        if enabled:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        else:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.coll_view.resizeRowsToContents()

    def _on_miss_wrap_toggled(self, state: int) -> None:
        enabled = bool(state)
        self.miss_view.setWordWrap(enabled)
        vh = self.miss_view.verticalHeader()
        if enabled:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        else:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.miss_view.resizeRowsToContents()

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh_collection(self):
        self.coll_status.setText("Loading…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/collection", timeout=15
        ).json())
        w.finished.connect(self._on_collection_loaded)
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_collection_loaded(self, data):
        if isinstance(data, list):
            self._all_collection = data
            self._page = 0
            self._coll_col_widths = None
            self._populate_year_combo()
            self._render_coll_page()
        else:
            self.coll_status.setText(f"Error: {data.get('error', 'unknown')}")

    def _populate_year_combo(self) -> None:
        current = self.coll_year_combo.currentData()
        self.coll_year_combo.blockSignals(True)
        self.coll_year_combo.clear()
        self.coll_year_combo.addItem("All Years", userData=None)
        years: set = set()
        for row in self._all_collection:
            date_str = row.get("date_str") or ""
            parts = date_str.split("/")
            if len(parts) >= 3:
                try:
                    y = int(parts[-1].strip())
                    if y < 100:
                        y = 1900 + y if y >= 49 else 2000 + y
                    years.add(y)
                except ValueError:
                    pass
        for y in sorted(years, reverse=True):
            self.coll_year_combo.addItem(str(y), userData=y)
        if current is not None:
            idx = self.coll_year_combo.findData(current)
            if idx >= 0:
                self.coll_year_combo.setCurrentIndex(idx)
        self.coll_year_combo.blockSignals(False)

    def _filtered_collection(self) -> list:
        text = self.coll_search.text().lower()
        year = self.coll_year_combo.currentData()
        results = self._all_collection
        if text:
            results = [
                r for r in results
                if text in str(r.get("lb_number", "")).lower()
                or text in (r.get("folder_name", "") or "").lower()
                or text in (r.get("disk_path", "") or "").lower()
            ]
        if year is not None:
            short = str(year)[-2:]
            long_ = str(year)
            results = [
                r for r in results
                if (r.get("date_str") or "").endswith(f"/{short}")
                or (r.get("date_str") or "").endswith(f"/{long_}")
            ]
        return results

    def _total_coll_pages(self) -> int:
        n = len(self._filtered_collection())
        return max(1, math.ceil(n / self._page_size))

    def _render_coll_page(self) -> None:
        filtered = self._filtered_collection()
        start = self._page * self._page_size
        end = start + self._page_size
        self.coll_model.set_rows(filtered[start:end])

        if self._coll_col_widths is None and self.coll_model.rowCount() > 0:
            self.coll_view.resizeColumnsToContents()
            self._coll_col_widths = [
                self.coll_view.columnWidth(i) for i in range(self.coll_model.columnCount())
            ]
        else:
            self._apply_coll_col_widths()

        pages = self._total_coll_pages()
        total = len(self._all_collection)
        shown = len(filtered)
        if pages > 1:
            self._coll_page_widget.setVisible(True)
            self._coll_page_label.setText(f"Page {self._page + 1} of {pages}  ({shown} item(s))")
            self._coll_prev_btn.setEnabled(self._page > 0)
            self._coll_next_btn.setEnabled(self._page < pages - 1)
        else:
            self._coll_page_widget.setVisible(False)

        if shown == total:
            self.coll_status.setText(f"{total} item(s) in collection.")
        else:
            self.coll_status.setText(f"{shown} item(s) shown (of {total} total).")

    def _coll_prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_coll_page()

    def _coll_next_page(self) -> None:
        if self._page < self._total_coll_pages() - 1:
            self._page += 1
            self._render_coll_page()

    def refresh_missing(self):
        self.miss_status.setText("Loading…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/collection/missing", timeout=15
        ).json())
        w.finished.connect(self._on_missing_loaded)
        w.error.connect(lambda e: self.miss_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_missing_loaded(self, data):
        if isinstance(data, list):
            self._miss_col_widths = None
            self.miss_model.set_rows(data)
            if data:
                self.miss_view.resizeColumnsToContents()
                self._miss_col_widths = [
                    self.miss_view.columnWidth(i) for i in range(self.miss_model.columnCount())
                ]
            self.miss_status.setText(f"{len(data)} missing from collection.")
        else:
            self.miss_status.setText(f"Error: {data.get('error', 'unknown')}")

    # ── Wishlist data ─────────────────────────────────────────────────────────

    def refresh_wishlist(self):
        self.wish_status.setText("Loading…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/wishlist", timeout=15
        ).json())
        w.finished.connect(self._on_wishlist_loaded)
        w.error.connect(lambda e: self.wish_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_wishlist_loaded(self, data):
        if isinstance(data, list):
            self._wish_col_widths = None
            self.wish_model.set_rows(data)
            if data:
                self.wish_view.resizeColumnsToContents()
                self._wish_col_widths = [
                    self.wish_view.columnWidth(i) for i in range(self.wish_model.columnCount())
                ]
            self.wish_status.setText(f"{len(data)} item(s) on wishlist.")
        else:
            self.wish_status.setText(f"Error: {data.get('error', 'unknown')}")

    def _on_wish_context(self, pos):
        index = self.wish_view.indexAt(pos)
        if not index.isValid():
            return
        row = self.wish_model.get_row(index.row())
        if not row:
            return
        lb = row["lb_number"]
        menu = QMenu(self)

        remove_act = QAction("Remove from Wishlist", self)
        remove_act.triggered.connect(lambda: self._wishlist_remove(lb))
        menu.addAction(remove_act)

        view_act = QAction("View LB Entry", self)
        url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
        view_act.triggered.connect(lambda: webbrowser.open(url))
        menu.addAction(view_act)

        menu.exec(self.wish_view.mapToGlobal(pos))

    def _wishlist_remove(self, lb: int):
        w = _ApiWorker(lambda: requests.delete(
            f"http://127.0.0.1:{self.flask_port}/api/wishlist/{lb}", timeout=10
        ).json())
        w.finished.connect(lambda _: self.refresh_wishlist())
        w.error.connect(lambda e: self.wish_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Duplicates data ───────────────────────────────────────────────────────

    def refresh_duplicates(self):
        self.dupes_status.setText("Loading…")
        self._duplicates_loaded = True
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/collection/duplicates", timeout=15
        ).json())
        w.finished.connect(self._on_duplicates_loaded)
        w.error.connect(lambda e: self.dupes_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_duplicates_loaded(self, data):
        self.dupes_tree.clear()
        if not isinstance(data, list):
            self.dupes_status.setText(f"Error: {data.get('error', 'unknown')}")
            return
        for group in data:
            show_item = QTreeWidgetItem([
                f"{group['date_str']}  —  {group['location']}",
                f"({len(group['owned'])} owned)",
            ])
            for lb_row in group["owned"]:
                child = QTreeWidgetItem([
                    f"LB-{lb_row['lb_number']:05d}",
                    lb_row.get("rating") or "",
                ])
                child.setForeground(0, QColor("#1B5E20"))
                child.setForeground(1, QColor("#1B5E20"))
                child.setData(0, Qt.ItemDataRole.UserRole, ("owned", lb_row["lb_number"]))
                show_item.addChild(child)
            for lb_row in group["unowned"]:
                child = QTreeWidgetItem([
                    f"LB-{lb_row['lb_number']:05d}",
                    lb_row.get("rating") or "",
                ])
                child.setForeground(0, QColor("#757575"))
                child.setForeground(1, QColor("#757575"))
                child.setData(0, Qt.ItemDataRole.UserRole, ("unowned", lb_row["lb_number"]))
                show_item.addChild(child)
            self.dupes_tree.addTopLevelItem(show_item)
            show_item.setExpanded(True)
        self.dupes_tree.resizeColumnToContents(0)
        self.dupes_status.setText(f"{len(data)} duplicate show(s) found.")

    def _on_dupes_context(self, pos):
        item = self.dupes_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, lb = data
        menu = QMenu(self)
        if kind == "owned":
            rm_act = QAction("Remove from Collection", self)
            rm_act.triggered.connect(lambda: self._dupes_remove_collection(lb))
            menu.addAction(rm_act)
        else:
            open_act = QAction("Open on LosslessBob", self)
            url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
            open_act.triggered.connect(lambda: webbrowser.open(url))
            menu.addAction(open_act)
        menu.exec(self.dupes_tree.mapToGlobal(pos))

    def _dupes_remove_collection(self, lb: int):
        confirm = QMessageBox.question(
            self, "Confirm Remove",
            f"Remove LB-{lb:05d} from My Collection?\n(Files are not deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        w = _ApiWorker(lambda: requests.delete(
            f"http://127.0.0.1:{self.flask_port}/api/collection/{lb}", timeout=10
        ).json())
        w.finished.connect(lambda _: (self.refresh_collection(), self.refresh_duplicates()))
        w.error.connect(lambda e: self.dupes_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Collection filter ─────────────────────────────────────────────────────

    def _on_coll_filter(self, *_) -> None:
        self._page = 0
        self._render_coll_page()

    # ── Add Single Folder ─────────────────────────────────────────────────────

    def _on_add_single(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not path:
            return
        folder = Path(path)
        lb_number = _extract_lb(folder.name)
        dlg = _AddDialog(lb_number, folder.name, str(folder), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if not vals["lb_number"]:
            QMessageBox.warning(self, "Invalid", "LB Number is required and must be an integer.")
            return
        self._post_collection(vals)

    def _post_collection(self, vals):
        def call():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection",
                json=vals, timeout=10,
            ).json()
        w = _ApiWorker(call)
        w.finished.connect(lambda r: self._on_post_done(r, 1, 0))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_post_done(self, result, added, skipped):
        if isinstance(result, dict) and result.get("error"):
            self.coll_status.setText(f"Error: {result['error']}")
        else:
            self.coll_status.setText(f"Added: {added}, already existed: {skipped}.")
            self.refresh_collection()

    # ── Scan Directory ────────────────────────────────────────────────────────

    def _on_scan_directory(self):
        root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Scan")
        if not root:
            return
        root_path = Path(root)
        entries = []
        skipped = 0
        for child in sorted(root_path.iterdir()):
            if not child.is_dir():
                continue
            lb = _extract_lb(child.name)
            if lb is not None:
                entries.append((lb, child.name, str(child)))
            else:
                skipped += 1

        if not entries:
            QMessageBox.information(self, "Scan", f"No folders with LB numbers found.\n{skipped} folder(s) skipped.")
            return

        try:
            owned_resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/collection/lb_numbers", timeout=10
            )
            owned_set = set(owned_resp.json())
        except Exception:
            owned_set = set()

        dlg = _ScanPreviewDialog(entries, owned_set, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._bulk_add(entries, skipped)

    def _on_scan_tree(self):
        """Recursively scan all subdirectories for LB-numbered folders and bulk-add them."""
        root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Scan")
        if not root:
            return
        root_path = Path(root)
        by_lb: dict = {}
        skipped = 0
        for child in root_path.rglob("*"):
            if not child.is_dir():
                continue
            lb = _extract_lb(child.name)
            if lb is not None:
                depth = len(child.relative_to(root_path).parts)
                if lb not in by_lb or depth < by_lb[lb][0]:
                    by_lb[lb] = (depth, child.name, str(child))
            else:
                skipped += 1

        if not by_lb:
            QMessageBox.information(
                self, "Scan Tree",
                f"No folders with LB numbers found.\n{skipped} folder(s) skipped."
            )
            return

        entries = [(lb, name, path) for lb, (_, name, path) in sorted(by_lb.items())]

        try:
            owned_resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/collection/lb_numbers", timeout=10
            )
            owned_set = set(owned_resp.json())
        except Exception:
            owned_set = set()

        dlg = _ScanPreviewDialog(entries, owned_set, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._bulk_add(entries, skipped)

    def _bulk_add(self, entries, skipped_count):
        flask_port = self.flask_port

        def call():
            added = 0
            already = 0
            for lb, name, path in entries:
                resp = requests.post(
                    f"http://127.0.0.1:{flask_port}/api/collection",
                    json={"lb_number": lb, "folder_name": name, "disk_path": path},
                    timeout=10,
                ).json()
                if resp.get("added"):
                    added += 1
                else:
                    already += 1
            return {"added": added, "already": already, "skipped": skipped_count}

        w = _ApiWorker(call)
        w.finished.connect(lambda r: self._on_bulk_done(r))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()
        self.coll_status.setText("Adding…")

    def _on_bulk_done(self, result):
        self.coll_status.setText(
            f"Added: {result['added']}, already existed: {result['already']}, "
            f"skipped (no LB): {result['skipped']}."
        )
        self.refresh_collection()

    # ── Update Location ───────────────────────────────────────────────────────

    def _on_update_location(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more rows to update.")
            return

        if len(rows) == 1:
            row = rows[0]
            path = QFileDialog.getExistingDirectory(self, "Select New Folder Location")
            if not path:
                return
            folder = Path(path)
            self._patch_collection(row["lb_number"], {
                "disk_path": str(folder),
                "folder_name": folder.name,
            })
        else:
            root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Search")
            if not root:
                return
            root_path = Path(root)
            updated = 0
            not_found = []
            for row in rows:
                folder_name = row.get("folder_name", "")
                candidate = root_path / folder_name
                if not candidate.is_dir():
                    # Case-insensitive fallback
                    candidate = next(
                        (c for c in root_path.iterdir()
                         if c.is_dir() and c.name.lower() == folder_name.lower()),
                        None,
                    )
                if candidate:
                    self._patch_collection(row["lb_number"], {
                        "disk_path": str(candidate),
                        "folder_name": candidate.name,
                    })
                    updated += 1
                else:
                    not_found.append(f"LB-{row['lb_number']}")
            msg = f"Updated: {updated}."
            if not_found:
                msg += f" Not found: {', '.join(not_found)}."
            self.coll_status.setText(msg)
            self.refresh_collection()

    def _patch_collection(self, lb_number, fields):
        def call():
            return requests.patch(
                f"http://127.0.0.1:{self.flask_port}/api/collection/{lb_number}",
                json=fields, timeout=10,
            ).json()
        w = _ApiWorker(call)
        w.finished.connect(lambda _: self.refresh_collection())
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Remove ────────────────────────────────────────────────────────────────

    def _on_remove(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more rows to remove.")
            return
        lb_numbers = [r["lb_number"] for r in rows]
        if QMessageBox.question(
            self, "Confirm Remove",
            f"Remove {len(lb_numbers)} item(s) from My Collection?\n\n"
            "Personal ratings, tags, and watchdog alerts for these entries "
            "will also be removed. Audio files on disk are NOT deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def call():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/delete_bulk",
                json={"lb_numbers": lb_numbers}, timeout=30,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(lambda r: (
            self.coll_status.setText(
                f"Removed {r.get('deleted', 0)} item(s)."
                if not r.get("error") else f"Error: {r['error']}"
            ),
            self.refresh_collection(),
        ))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_coll_context(self, pos):
        index = self.coll_view.indexAt(pos)
        menu = QMenu(self)

        rows = self._selected_rows()
        if rows:
            open_act = QAction("Open Folder", self)
            open_act.triggered.connect(lambda: self._open_folders(rows))
            menu.addAction(open_act)

        if index.isValid():
            row = self.coll_model.get_row(index.row())
            if row:
                lb = row["lb_number"]
                view_act = QAction("View LB Entry", self)
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
                view_act.triggered.connect(lambda: webbrowser.open(url))
                menu.addAction(view_act)

                scrape_act = QAction("Scrape Entry", self)
                scrape_act.triggered.connect(lambda: self._scrape_entry(lb))
                menu.addAction(scrape_act)

                upd_act = QAction("Update Location", self)
                upd_act.triggered.connect(self._on_update_location)
                menu.addAction(upd_act)

                meta_act = QAction("Edit Personal Info…", self)
                meta_act.triggered.connect(lambda: self._on_edit_personal_info(lb))
                menu.addAction(meta_act)

        if not menu.isEmpty():
            menu.exec(self.coll_view.mapToGlobal(pos))

    def _open_folders(self, rows):
        from gui.platform_utils import open_folder
        for row in rows:
            path = row.get("disk_path", "")
            if path and Path(path).is_dir():
                try:
                    open_folder(path)
                except Exception:
                    pass

    def _scrape_entry(self, lb_number):
        self.coll_status.setText(f"Scraping LB-{lb_number}…")
        w = _ApiWorker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/entry/{lb_number}/scrape",
            timeout=60,
        ).json())
        w.finished.connect(lambda _: (
            self.coll_status.setText(f"Scraped LB-{lb_number}."),
            self.refresh_collection(),
        ))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_edit_personal_info(self, lb_number: int):
        try:
            meta = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/collection/{lb_number}/meta",
                timeout=5,
            ).json()
        except Exception as e:
            self.coll_status.setText(f"Error loading meta: {e}")
            return
        dlg = _PersonalMetaDialog(lb_number, meta, self.flask_port, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/{lb_number}/meta",
                json=vals, timeout=5,
            )
            self.coll_status.setText(f"Saved personal info for LB-{lb_number:05d}.")
        except Exception as e:
            self.coll_status.setText(f"Error saving meta: {e}")

    # ── Missing: double-click & export ────────────────────────────────────────

    def _on_missing_double_click(self, index):
        row = self.miss_model.get_row(index.row())
        if row:
            self.lookup_lb.emit(row["lb_number"])

    def _on_export_csv(self):
        rows = self.miss_model.all_rows()
        if not rows:
            self.miss_status.setText("Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Missing as CSV", "missing_from_collection.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=MISS_HEADERS)
                writer.writeheader()
                for r in rows:
                    writer.writerow({
                        "LB Number": f"LB-{r.get('lb_number', '')}",
                        "Date": r.get("date_str", ""),
                        "Location": r.get("location", ""),
                        "Rating": r.get("rating", ""),
                        "Description": r.get("description", ""),
                    })
            self.miss_status.setText(f"Exported {len(rows)} rows to {Path(path).name}.")
        except Exception as e:
            self.miss_status.setText(f"Export error: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _selected_rows(self):
        seen = set()
        rows = []
        for idx in self.coll_view.selectedIndexes():
            r = idx.row()
            if r not in seen:
                seen.add(r)
                row = self.coll_model.get_row(r)
                if row:
                    rows.append(row)
        return rows
