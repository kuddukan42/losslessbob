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
    QGroupBox,
)

from gui.styles import ROW_OWNED, ROW_WISHLIST

_LB_RE = re.compile(r'LB[- ]0*(\d+)', re.IGNORECASE)
_STANDARD_LB_NAME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\s.+\(LB-\d{5}\)$')

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


class _ScanWorker(QThread):
    """Filesystem walker for Scan Directory / Scan Tree — runs off the main thread."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, root_path: Path, recursive: bool, flask_port: int):
        super().__init__()
        self._root = root_path
        self._recursive = recursive
        self._flask_port = flask_port

    def run(self):
        try:
            by_lb: dict = {}
            skipped = 0
            if self._recursive:
                for child in self._root.rglob("*"):
                    if not child.is_dir():
                        continue
                    lb = _extract_lb(child.name)
                    if lb is not None:
                        depth = len(child.relative_to(self._root).parts)
                        if lb not in by_lb or depth < by_lb[lb][0]:
                            by_lb[lb] = (depth, child.name, str(child))
                    else:
                        skipped += 1
                entries = [(lb, name, path) for lb, (_, name, path) in sorted(by_lb.items())]
            else:
                entries = []
                for child in sorted(self._root.iterdir()):
                    if not child.is_dir():
                        continue
                    lb = _extract_lb(child.name)
                    if lb is not None:
                        entries.append((lb, child.name, str(child)))
                    else:
                        skipped += 1

            try:
                owned_resp = requests.get(
                    f"http://127.0.0.1:{self._flask_port}/api/collection/lb_numbers",
                    timeout=10,
                )
                owned_set = set(owned_resp.json())
            except Exception:
                owned_set = set()

            self.finished.emit({
                "entries": entries,
                "skipped": skipped,
                "owned_set": owned_set,
            })
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
        self._xref_lb_numbers: set = set()
        self._page: int = 0
        self._page_size: int = 50
        self._coll_col_widths: list | None = None
        self._miss_col_widths: list | None = None
        self._wish_col_widths: list | None = None
        self._duplicates_loaded: bool = False
        self._torrent_history_records: list = []
        self._current_history_lb: int | None = None
        self._load_page_size()
        self._build_ui()
        self.refresh_collection()
        self._load_xref_lb_numbers()

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

        self._coll_xref_cb = QCheckBox("Xref only")
        self._coll_xref_cb.setToolTip(
            "Show only collection entries whose LB number has cross-reference (xref) variants in the DB."
        )
        self._coll_xref_cb.stateChanged.connect(self._on_coll_filter)
        filter_row.addWidget(self._coll_xref_cb)

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

        # Torrent / forum action row
        torrent_row = QHBoxLayout()
        self.create_torrent_btn = QPushButton("Create Torrent")
        self.create_torrent_btn.setToolTip(
            "Generate a .torrent file for the selected entry. Requires the folder to exist on disk."
        )
        self.create_torrent_btn.clicked.connect(self._on_create_torrent)
        torrent_row.addWidget(self.create_torrent_btn)

        self.add_qbt_btn = QPushButton("Add to qBittorrent")
        self.add_qbt_btn.setToolTip(
            "Add the most recent torrent for the selected entry to qBittorrent for seeding."
        )
        self.add_qbt_btn.clicked.connect(self._on_add_to_qbt)
        torrent_row.addWidget(self.add_qbt_btn)

        self.post_forum_btn = QPushButton("Post to Forum")
        self.post_forum_btn.setToolTip(
            "Post a topic to the WTRF forum with the .torrent as an attachment. "
            "Requires a torrent to exist for this entry."
        )
        self.post_forum_btn.clicked.connect(self._on_post_forum)
        torrent_row.addWidget(self.post_forum_btn)

        torrent_row.addStretch()
        layout.addLayout(torrent_row)

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
        self.coll_view.selectionModel().selectionChanged.connect(self._on_coll_selection_changed)

        self.coll_status = QLabel("")
        layout.addWidget(self.coll_status)

        self.torrent_history_group = self._build_torrent_history_panel()
        layout.addWidget(self.torrent_history_group)
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

    def _load_xref_lb_numbers(self) -> None:
        from PyQt6.QtCore import QThread, pyqtSignal as _sig

        class _W(QThread):
            finished = _sig(list)

            def __init__(self, port):
                super().__init__()
                self._port = port

            def run(self):
                try:
                    import requests as _r
                    resp = _r.get(
                        f"http://127.0.0.1:{self._port}/api/checksums/xref_lb_numbers",
                        timeout=15,
                    )
                    self.finished.emit(resp.json())
                except Exception:
                    self.finished.emit([])

        self._xref_load_worker = _W(self.flask_port)
        self._xref_load_worker.finished.connect(self._on_xref_loaded)
        self._xref_load_worker.start()

    def _on_xref_loaded(self, lb_numbers: list) -> None:
        self._xref_lb_numbers = set(lb_numbers)
        if self._coll_xref_cb.isChecked() and self._all_collection:
            self._page = 0
            self._render_coll_page()

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
        if self._coll_xref_cb.isChecked():
            results = [r for r in results if r.get("lb_number") in self._xref_lb_numbers]
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
        self.coll_status.setText("Scanning…")
        w = _ScanWorker(Path(root), recursive=False, flask_port=self.flask_port)
        w.finished.connect(self._on_scan_finished)
        w.error.connect(lambda e: self.coll_status.setText(f"Scan error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_scan_tree(self):
        """Recursively scan all subdirectories for LB-numbered folders and bulk-add them."""
        root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Scan")
        if not root:
            return
        self.coll_status.setText("Scanning (recursive)…")
        w = _ScanWorker(Path(root), recursive=True, flask_port=self.flask_port)
        w.finished.connect(self._on_scan_finished)
        w.error.connect(lambda e: self.coll_status.setText(f"Scan error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_scan_finished(self, result: dict):
        entries = result["entries"]
        skipped = result["skipped"]
        owned_set = result["owned_set"]

        if not entries:
            QMessageBox.information(
                self, "Scan",
                f"No folders with LB numbers found.\n{skipped} folder(s) skipped."
            )
            self.coll_status.setText("Scan complete — no LB folders found.")
            return

        dlg = _ScanPreviewDialog(entries, owned_set, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.coll_status.setText("Scan cancelled.")
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

    # ── Torrent / Forum actions ───────────────────────────────────────────────

    def _on_create_torrent(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more entries to create torrents for.")
            return
        entries = [
            {"lb_number": r["lb_number"], "source_folder": r.get("disk_path", "")}
            for r in rows
            if r.get("disk_path")
        ]
        if not entries:
            self.coll_status.setText("Selected entries have no disk path set.")
            return

        flask_port = self.flask_port
        total = len(entries)
        self.coll_status.setText(f"Creating {total} torrent(s)…")
        self.create_torrent_btn.setEnabled(False)

        def call():
            results = []
            errors = []
            for e in entries:
                try:
                    resp = requests.post(
                        f"http://127.0.0.1:{flask_port}/api/torrent/create",
                        json=e,
                        timeout=300,
                    ).json()
                    if resp.get("ok"):
                        results.append(resp)
                    else:
                        errors.append(f"LB-{e['lb_number']}: {resp.get('error', 'unknown')}")
                except Exception as exc:
                    errors.append(f"LB-{e['lb_number']}: {exc}")
            return {"results": results, "errors": errors}

        w = _ApiWorker(call)
        w.finished.connect(self._on_torrent_done)
        w.error.connect(lambda e: (
            self.coll_status.setText(f"Error: {e}"),
            self.create_torrent_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_torrent_done(self, result: dict):
        self.create_torrent_btn.setEnabled(True)
        ok_count = len(result.get("results", []))
        errors = result.get("errors", [])
        msg = f"Created {ok_count} torrent(s)."
        if errors:
            msg += f" {len(errors)} error(s): " + "; ".join(errors[:3])
        self.coll_status.setText(msg)

    def _on_add_to_qbt(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more entries to add to qBittorrent.")
            return
        lb_numbers = [r["lb_number"] for r in rows]
        flask_port = self.flask_port
        self.coll_status.setText(f"Adding {len(lb_numbers)} torrent(s) to qBittorrent…")
        self.add_qbt_btn.setEnabled(False)

        def call():
            return requests.post(
                f"http://127.0.0.1:{flask_port}/api/qbt/add",
                json={"lb_numbers": lb_numbers},
                timeout=60,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(self._on_qbt_done)
        w.error.connect(lambda e: (
            self.coll_status.setText(f"Error: {e}"),
            self.add_qbt_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_qbt_done(self, result: dict):
        self.add_qbt_btn.setEnabled(True)
        if result.get("ok"):
            added = result.get("added", 0)
            total = result.get("total", 0)
            errors = [r for r in result.get("results", []) if not r.get("ok")]
            msg = f"Added {added}/{total} torrent(s) to qBittorrent."
            if errors:
                msg += " Errors: " + "; ".join(
                    r.get("error", "?") for r in errors[:3]
                )
            self.coll_status.setText(msg)
        else:
            self.coll_status.setText(f"Error: {result.get('error', 'unknown')}")

    def _on_post_forum(self):
        rows = self._selected_rows()
        if len(rows) != 1:
            self.coll_status.setText("Select exactly one entry to post to the forum.")
            return
        row = rows[0]
        lb = row["lb_number"]
        flask_port = self.flask_port
        self.coll_status.setText(f"Posting LB-{lb:05d} to WTRF forum…")
        self.post_forum_btn.setEnabled(False)

        def call():
            return requests.post(
                f"http://127.0.0.1:{flask_port}/api/entry/{lb}/post_forum",
                json={},
                timeout=60,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(lambda r: self._on_post_forum_done(r, lb))
        w.error.connect(lambda e: (
            self.coll_status.setText(f"Error: {e}"),
            self.post_forum_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_post_forum_done(self, result: dict, lb: int):
        self.post_forum_btn.setEnabled(True)
        if result.get("ok"):
            url = result.get("topic_url", "")
            self.coll_status.setText(f"Posted LB-{lb:05d} to forum.  {url}")
            if url:
                from PyQt6.QtWidgets import QMessageBox
                if QMessageBox.question(
                    self, "Posted",
                    f"Topic posted successfully.\nOpen in browser?\n{url}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes:
                    import webbrowser
                    webbrowser.open(url)
        else:
            self.coll_status.setText(f"Forum post failed: {result.get('error', 'unknown')}")

    # ── Torrent History Panel ─────────────────────────────────────────────────

    def _build_torrent_history_panel(self) -> QGroupBox:
        group = QGroupBox("Torrent History")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self.torrent_history_label = QLabel("Select one entry to view its torrent history.")
        outer.addWidget(self.torrent_history_label)

        self.torrent_history_table = QTableWidget(0, 5)
        self.torrent_history_table.setHorizontalHeaderLabels(
            ["", "Created", "Torrent File", "Source Folder", "Added to qBt"]
        )
        self.torrent_history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.torrent_history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.torrent_history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.torrent_history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.torrent_history_table.customContextMenuRequested.connect(self._on_history_context)
        self.torrent_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.torrent_history_table.setColumnWidth(0, 22)
        self.torrent_history_table.setColumnWidth(1, 138)
        self.torrent_history_table.setColumnWidth(2, 210)
        self.torrent_history_table.setColumnWidth(3, 210)
        self.torrent_history_table.setMaximumHeight(150)
        outer.addWidget(self.torrent_history_table)

        hist_btn_row = QHBoxLayout()
        self.history_add_qbt_btn = QPushButton("Add to qBittorrent")
        self.history_add_qbt_btn.setEnabled(False)
        self.history_add_qbt_btn.clicked.connect(self._on_history_add_to_qbt)
        hist_btn_row.addWidget(self.history_add_qbt_btn)

        self.history_regen_btn = QPushButton("Regenerate")
        self.history_regen_btn.setEnabled(False)
        self.history_regen_btn.setToolTip("Recreate the .torrent file (only when file is missing)")
        self.history_regen_btn.clicked.connect(self._on_history_regenerate)
        hist_btn_row.addWidget(self.history_regen_btn)

        self.history_relocate_btn = QPushButton("Relocate Source…")
        self.history_relocate_btn.setEnabled(False)
        self.history_relocate_btn.setToolTip("Update the stored source folder path for this torrent")
        self.history_relocate_btn.clicked.connect(self._on_history_relocate)
        hist_btn_row.addWidget(self.history_relocate_btn)

        hist_btn_row.addStretch()
        outer.addLayout(hist_btn_row)

        self.torrent_history_status = QLabel("")
        outer.addWidget(self.torrent_history_status)
        return group

    def _on_coll_selection_changed(self, _selected, _deselected) -> None:
        rows = self._selected_rows()
        if len(rows) == 1:
            self._load_torrent_history(rows[0]["lb_number"])
        else:
            msg = (
                "Select one entry to view its torrent history."
                if not rows else
                "Select a single entry to view torrent history."
            )
            self.torrent_history_label.setText(msg)
            self.torrent_history_table.setRowCount(0)
            self._torrent_history_records = []
            self._current_history_lb = None
            self.history_add_qbt_btn.setEnabled(False)
            self.history_regen_btn.setEnabled(False)
            self.history_relocate_btn.setEnabled(False)
            self.torrent_history_status.setText("")

    def _load_torrent_history(self, lb: int) -> None:
        self._current_history_lb = lb
        self.torrent_history_label.setText(f"Loading torrent history for LB-{lb:05d}…")
        flask_port = self.flask_port

        def call():
            return requests.get(
                f"http://127.0.0.1:{flask_port}/api/torrent/{lb}", timeout=10
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(lambda data, _lb=lb: self._populate_torrent_history(data, _lb))
        w.error.connect(lambda e: self.torrent_history_label.setText(f"Error loading history: {e}"))
        self._workers.append(w)
        w.start()

    def _populate_torrent_history(self, records, lb: int) -> None:
        if lb != self._current_history_lb:
            return  # stale response from an earlier selection
        if isinstance(records, dict):
            self.torrent_history_label.setText(f"Error: {records.get('error', 'unknown')}")
            return

        self._torrent_history_records = records
        self.torrent_history_table.setRowCount(0)

        if not records:
            self.torrent_history_label.setText(
                f"LB-{lb:05d} — no torrents yet. Use Create Torrent to make one."
            )
            self.history_add_qbt_btn.setEnabled(False)
            self.history_regen_btn.setEnabled(False)
            self.history_relocate_btn.setEnabled(False)
            self.torrent_history_status.setText("")
            return

        self.torrent_history_label.setText(
            f"LB-{lb:05d} — {len(records)} torrent record(s):"
        )

        for rec in records:
            row = self.torrent_history_table.rowCount()
            self.torrent_history_table.insertRow(row)

            folder_ok = rec.get("source_folder_exists", False)
            torrent_ok = rec.get("torrent_file_exists", False)

            dot = QTableWidgetItem("●")
            dot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if not folder_ok:
                dot.setForeground(QColor("#D32F2F"))
                dot.setToolTip("Source folder not found on disk — use Relocate Source")
            elif not torrent_ok:
                dot.setForeground(QColor("#F57C00"))
                dot.setToolTip("Torrent file missing from data/torrents/ — use Regenerate")
            else:
                dot.setForeground(QColor("#388E3C"))
                dot.setToolTip("Source folder and .torrent file both present")
            self.torrent_history_table.setItem(row, 0, dot)

            created = str(rec.get("created_at") or "")[:19]
            self.torrent_history_table.setItem(row, 1, QTableWidgetItem(created))

            tp = rec.get("torrent_path") or ""
            from pathlib import Path as _Path
            t_name = _Path(tp).name if tp else "MISSING"
            t_item = QTableWidgetItem(t_name)
            t_item.setToolTip(tp)
            if not torrent_ok:
                t_item.setForeground(QColor("#D32F2F"))
            self.torrent_history_table.setItem(row, 2, t_item)

            sf = rec.get("source_folder") or ""
            sf_item = QTableWidgetItem(_Path(sf).name if sf else "—")
            sf_item.setToolTip(sf)
            if not folder_ok:
                sf_item.setForeground(QColor("#D32F2F"))
            self.torrent_history_table.setItem(row, 3, sf_item)

            added = rec.get("added_to_qbt", 0)
            added_at = str(rec.get("added_to_qbt_at") or "")[:10]
            qbt_text = f"Yes ({added_at})" if added and added_at else ("Yes" if added else "No")
            self.torrent_history_table.setItem(row, 4, QTableWidgetItem(qbt_text))

        self.history_add_qbt_btn.setEnabled(True)
        self.history_relocate_btn.setEnabled(True)
        has_missing = any(not r.get("torrent_file_exists") for r in records)
        self.history_regen_btn.setEnabled(has_missing)
        self.torrent_history_status.setText("")

    def _get_selected_history_record(self) -> dict | None:
        row = self.torrent_history_table.currentRow()
        if 0 <= row < len(self._torrent_history_records):
            return self._torrent_history_records[row]
        return None

    def _on_history_context(self, pos) -> None:
        row = self.torrent_history_table.rowAt(pos.y())
        if row < 0 or row >= len(self._torrent_history_records):
            return
        rec = self._torrent_history_records[row]
        # Ensure the clicked row is the current row so button handlers use it
        self.torrent_history_table.setCurrentCell(row, 0)

        menu = QMenu(self)
        add_act = QAction("Add to qBittorrent", self)
        add_act.triggered.connect(lambda: self._history_add_record(rec))
        menu.addAction(add_act)

        if not rec.get("torrent_file_exists"):
            regen_act = QAction("Regenerate Torrent", self)
            regen_act.triggered.connect(lambda: self._history_regen_record(rec))
            menu.addAction(regen_act)

        relocate_act = QAction("Relocate Source Folder…", self)
        relocate_act.triggered.connect(lambda: self._history_relocate_record(rec))
        menu.addAction(relocate_act)

        menu.exec(self.torrent_history_table.mapToGlobal(pos))

    # ── History: Add to qBittorrent ───────────────────────────────────────────

    def _on_history_add_to_qbt(self) -> None:
        rec = self._get_selected_history_record()
        if rec is None and self._torrent_history_records:
            rec = self._torrent_history_records[0]
        if rec is None:
            return
        self._history_add_record(rec)

    def _history_add_record(self, rec: dict) -> None:
        if not rec.get("source_folder_exists"):
            reply = QMessageBox.question(
                self, "Source Folder Missing",
                "The source folder for this torrent no longer exists.\n\n"
                "Would you like to relocate it first?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._history_relocate_record(rec)
                return
            if reply == QMessageBox.StandardButton.Cancel:
                return

        torrent_id = rec["id"]
        flask_port = self.flask_port
        self.torrent_history_status.setText("Adding to qBittorrent…")
        self.history_add_qbt_btn.setEnabled(False)

        def call():
            return requests.post(
                f"http://127.0.0.1:{flask_port}/api/qbt/add",
                json={"torrent_id": torrent_id},
                timeout=30,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(self._on_history_qbt_done)
        w.error.connect(lambda e: (
            self.torrent_history_status.setText(f"Error: {e}"),
            self.history_add_qbt_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_history_qbt_done(self, result: dict) -> None:
        self.history_add_qbt_btn.setEnabled(True)
        if result.get("ok") and result.get("added", 0) > 0:
            self.torrent_history_status.setText("Added to qBittorrent successfully.")
            if self._current_history_lb:
                self._load_torrent_history(self._current_history_lb)
        else:
            errors = result.get("results", [])
            err = next((r.get("error") for r in errors if r.get("error")),
                       result.get("error", "unknown error"))
            self.torrent_history_status.setText(f"Failed: {err}")

    # ── History: Regenerate ───────────────────────────────────────────────────

    def _on_history_regenerate(self) -> None:
        rec = self._get_selected_history_record()
        if rec is None:
            rec = next(
                (r for r in self._torrent_history_records if not r.get("torrent_file_exists")),
                None,
            )
        if rec is None:
            return
        self._history_regen_record(rec)

    def _history_regen_record(self, rec: dict) -> None:
        lb = self._current_history_lb
        source_folder = rec.get("source_folder", "")
        if not source_folder:
            self.torrent_history_status.setText("No source folder recorded.")
            return
        from pathlib import Path as _Path
        if not _Path(source_folder).is_dir():
            self.torrent_history_status.setText(
                "Source folder not found. Relocate it first before regenerating."
            )
            return

        flask_port = self.flask_port
        self.torrent_history_status.setText("Regenerating torrent…")
        self.history_regen_btn.setEnabled(False)

        def call():
            return requests.post(
                f"http://127.0.0.1:{flask_port}/api/torrent/create",
                json={"lb_number": lb, "source_folder": source_folder},
                timeout=300,
            ).json()

        w = _ApiWorker(call)
        w.finished.connect(self._on_history_regen_done)
        w.error.connect(lambda e: (
            self.torrent_history_status.setText(f"Error: {e}"),
            self.history_regen_btn.setEnabled(True),
        ))
        self._workers.append(w)
        w.start()

    def _on_history_regen_done(self, result: dict) -> None:
        self.history_regen_btn.setEnabled(True)
        if result.get("ok"):
            from pathlib import Path as _Path
            fname = _Path(result.get("torrent_path", "")).name
            self.torrent_history_status.setText(f"Torrent regenerated: {fname}")
            if self._current_history_lb:
                self._load_torrent_history(self._current_history_lb)
        else:
            self.torrent_history_status.setText(f"Error: {result.get('error', 'unknown')}")

    # ── History: Path Relocation (TODO-013) ───────────────────────────────────

    def _on_history_relocate(self) -> None:
        rec = self._get_selected_history_record()
        if rec is None and self._torrent_history_records:
            rec = self._torrent_history_records[0]
        if rec is None:
            self.torrent_history_status.setText("No torrent record to relocate.")
            return
        self._history_relocate_record(rec)

    def _history_relocate_record(self, rec: dict) -> None:
        from pathlib import Path as _Path
        import shutil

        lb = self._current_history_lb
        torrent_id = rec["id"]

        new_folder = QFileDialog.getExistingDirectory(
            self, "Select New Source Folder Location"
        )
        if not new_folder:
            return

        new_path = _Path(new_folder)

        # Cross-check files against checksums
        if lb:
            warn_msg = self._cross_check_folder(new_path, lb)
            if warn_msg:
                if QMessageBox.question(
                    self, "File Check Warning",
                    f"LB-{lb:05d} file check:\n{warn_msg}\n\nProceed with relocation anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) != QMessageBox.StandardButton.Yes:
                    return

        # Update source_folder in DB
        try:
            resp = requests.patch(
                f"http://127.0.0.1:{self.flask_port}/api/torrent/{torrent_id}",
                json={"source_folder": str(new_path)},
                timeout=10,
            ).json()
            if not resp.get("ok"):
                self.torrent_history_status.setText(f"Update error: {resp.get('error')}")
                return
        except Exception as e:
            self.torrent_history_status.setText(f"Error: {e}")
            return

        # Log the relocation to rename_log.txt and rename_history
        try:
            from backend.rename import write_rename_log
            write_rename_log(
                folder_path=str(new_path),
                old_name=new_path.name,
                new_name=new_path.name,
                source="collection_tab",
                notes=f"path relocated from: {rec.get('source_folder', '?')}",
                lb_number=lb,
            )
        except Exception:
            pass

        # Check standard name format and offer rename
        std_name = self._get_standard_lb_name(lb) if lb else ""
        if std_name and std_name != new_path.name and _STANDARD_LB_NAME_RE.match(std_name):
            reply = QMessageBox.question(
                self, "Rename Folder?",
                "The folder name does not match the standard format.\n\n"
                f"Current:  {new_path.name}\n"
                f"Standard: {std_name}\n\n"
                "Rename the folder to the standard format?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                new_renamed = new_path.parent / std_name
                try:
                    from backend.rename import write_rename_log as _wrl
                    _wrl(
                        folder_path=str(new_path),
                        old_name=new_path.name,
                        new_name=std_name,
                        source="collection_tab",
                        lb_number=lb,
                    )
                    shutil.move(str(new_path), str(new_renamed))
                    # Update source_folder and collection path to the renamed location
                    requests.patch(
                        f"http://127.0.0.1:{self.flask_port}/api/torrent/{torrent_id}",
                        json={"source_folder": str(new_renamed)},
                        timeout=10,
                    )
                    if lb:
                        requests.patch(
                            f"http://127.0.0.1:{self.flask_port}/api/collection/{lb}",
                            json={"disk_path": str(new_renamed), "folder_name": std_name},
                            timeout=10,
                        )
                    self.torrent_history_status.setText(
                        f"Relocated and renamed to: {std_name}"
                    )
                    self.refresh_collection()
                except Exception as exc:
                    self.torrent_history_status.setText(f"Rename error: {exc}")
            else:
                self.torrent_history_status.setText(f"Relocated to: {new_path.name}")
        else:
            self.torrent_history_status.setText(f"Source folder updated: {new_path.name}")

        if lb:
            self._load_torrent_history(lb)

    def _cross_check_folder(self, folder_path, lb: int) -> str:
        """Return warning string if folder contents don't match expected checksums. Empty = OK."""
        from pathlib import Path as _Path
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{lb}", timeout=10
            ).json()
            expected = {c["filename"] for c in resp.get("checksums", [])}
            if not expected:
                return ""
            actual = {f.name for f in _Path(folder_path).iterdir() if f.is_file()}
            missing = expected - actual
            extra = actual - expected
            parts = []
            if missing:
                parts.append(f"{len(missing)} expected file(s) not found")
            if extra:
                parts.append(f"{len(extra)} unexpected file(s) present")
            return "; ".join(parts)
        except Exception:
            return ""

    def _get_standard_lb_name(self, lb: int) -> str:
        """Return the standard YYYY-MM-DD Location (LB-XXXXX) folder name for an entry."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{lb}", timeout=10
            ).json()
            entry = resp.get("entry", {})
            date_str = entry.get("date_str") or ""
            location = (entry.get("location") or "").strip()
            from backend.torrent_maker import _parse_date
            iso_date = _parse_date(date_str)
            if iso_date and location:
                return f"{iso_date} {location} (LB-{lb:05d})"
        except Exception:
            pass
        return ""

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
