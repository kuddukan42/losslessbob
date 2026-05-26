import re
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread, pyqtSignal,
    QItemSelection, QItemSelectionModel,
)
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTableView, QAbstractItemView, QMenu, QApplication,
    QFileDialog, QHeaderView, QCheckBox, QDialog, QTableWidget, QTableWidgetItem,
    QDialogButtonBox,
)

import gui.styles as styles
from gui.widgets.sort_keys import sort_key_for


SUMMARY_HEADERS = ["LB Number", "Source", "Given", "Matched", "Not Found", "Missing", "Dups", "Xrefs", "Status"]
DETAIL_HEADERS = ["Checksum", "Filename", "Type", "LB Number", "Xref", "Status", "Source"]

# Per-column sort kind for each table, aligned to the headers above.
_SUMMARY_COL_KINDS = ["lb_number", "text", "int", "int", "int", "int", "int", "int", "lb_status"]
_DETAIL_COL_KINDS  = ["text",      "text", "text", "lb_number", "int", "lb_status", "text"]

_AUDIO_EXTS = {'.flac', '.shn', '.ape', '.wav', '.m4a', '.wv', '.aif', '.aiff', '.mp3'}


class _LookupSortProxy(QSortFilterProxyModel):
    """Proxy that sorts Lookup tab tables using typed sort keys.

    Args:
        col_kinds: List of kind strings (one per column) accepted by
            :func:`~gui.widgets.sort_keys.sort_key_for`.
        parent: Parent QObject.
    """

    def __init__(self, col_kinds: list[str], parent=None) -> None:
        super().__init__(parent)
        self._col_kinds = col_kinds

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """Compare two source-model cells using a typed sort key."""
        col = left.column()
        kind = self._col_kinds[col] if col < len(self._col_kinds) else "text"
        lv = self.sourceModel().data(left,  Qt.ItemDataRole.DisplayRole) or ""
        rv = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole) or ""
        try:
            return sort_key_for(lv, kind) < sort_key_for(rv, kind)
        except TypeError:
            return str(lv).lower() < str(rv).lower()


class _TableModel(QAbstractTableModel):
    def __init__(self, headers, rows=None):
        super().__init__()
        self._headers = headers
        self._rows = rows or []
        self._colors = []
        self._user_data = []  # list of dicts, one per row: {path, type, fg}

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        r = index.row()
        if role == Qt.ItemDataRole.DisplayRole:
            val = self._rows[r][index.column()]
            return str(val) if val is not None else ""
        if role == Qt.ItemDataRole.BackgroundRole:
            if r < len(self._colors):
                return self._colors[r]
        if role == Qt.ItemDataRole.ForegroundRole:
            if r < len(self._user_data):
                return self._user_data[r].get("fg")
        if role == Qt.ItemDataRole.UserRole and index.column() == 0:
            if r < len(self._user_data):
                return self._user_data[r].get("path")
        if role == Qt.ItemDataRole.UserRole + 1 and index.column() == 0:
            if r < len(self._user_data):
                return self._user_data[r].get("type")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

    def set_data(self, rows, colors=None, user_data=None):
        self.beginResetModel()
        self._rows = rows
        self._colors = colors or []
        self._user_data = user_data or [{} for _ in rows]
        self.endResetModel()

    def append_rows(self, rows, colors=None, user_data=None):
        if not rows:
            return
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self._rows.extend(rows)
        self._colors.extend(colors or [None] * len(rows))
        self._user_data.extend(user_data or [{} for _ in rows])
        self.endInsertRows()

    def refresh_colors(self, color_fn):
        self._colors = [color_fn(row) for row in self._rows]
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, len(self._headers) - 1),
            )

    def get_row(self, row_idx):
        if 0 <= row_idx < len(self._rows):
            return self._rows[row_idx]
        return None


_HEX_RE = re.compile(r'\b([0-9a-fA-F]{32,40})\b')


class _LookupWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, text=None, paths=None):
        super().__init__()
        self.flask_port = flask_port
        self.text = text
        self.paths = paths

    def run(self):
        try:
            checksum_to_file = {}
            if self.paths is not None:
                parts = []
                for path in self.paths:
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        parts.append(content)
                        for m in _HEX_RE.finditer(content):
                            checksum_to_file.setdefault(m.group(1).lower(), path)
                    except Exception:
                        pass
                text = "\n".join(parts)
            else:
                text = self.text
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lookup",
                json={"text": text},
                timeout=30,
            )
            data = resp.json()
            if checksum_to_file and "detail" in data:
                for d in data["detail"]:
                    chk = (d.get("checksum") or "").lower()
                    if chk in checksum_to_file:
                        d["source_file"] = checksum_to_file[chk]
            if "error" in data:
                self.error.emit(data["error"])
            else:
                self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class _ScanTreeWorker(QThread):
    """Recursively finds checksum files under a root — runs off the main thread."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    _EXTS = {".ffp", ".md5", ".st5", ".sha1", ".shn"}

    def __init__(self, root: Path, filter_mychecksums: bool):
        super().__init__()
        self._root = root
        self._filter = filter_mychecksums

    def run(self):
        try:
            found = []
            for p in sorted(self._root.rglob("*")):
                if not (p.is_file() and p.suffix.lower() in self._EXTS):
                    continue
                if self._filter and "_mychecksums" not in p.name.lower():
                    continue
                found.append(str(p))
            self.finished.emit(found)
        except Exception as e:
            self.error.emit(str(e))


class _GenerateWorker(QThread):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(str)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            self.progress.emit(f"Generating checksums for {len(self.folders)} folder(s)...")
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/verify/generate",
                json={"folders": self.folders},
                timeout=300,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e), "results": []})


class DropListWidget(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        event.acceptProposedAction()
        from gui.platform_utils import url_to_local_path
        paths = [str(url_to_local_path(url)) for url in event.mimeData().urls()]
        self.files_dropped.emit(paths)


class _ChangeHistoryDialog(QDialog):
    """Modal dialog showing field-level change history for one LB entry.

    Fetches rows from GET /api/entry/<lb_number>/changes and displays them
    in a read-only table sorted newest-first.

    Args:
        lb_number: The LB number whose history to display.
        flask_port: Port the Flask backend is listening on.
        parent: Parent widget.
    """

    _HEADERS = ["Field", "Old value", "New value", "Changed at"]

    def __init__(self, lb_number: int, flask_port: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Change History — LB-{}").format(f"{lb_number:05d}"))
        self.resize(720, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._status = QLabel(self.tr("Loading…"))
        layout.addWidget(self._status)

        self._table = QTableWidget(0, len(self._HEADERS))
        self._table.setHorizontalHeaderLabels([self.tr(h) for h in self._HEADERS])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._worker = _ChangeHistoryWorker(lb_number, flask_port)
        self._worker.finished.connect(self._on_loaded)
        self._worker.start()

    def _on_loaded(self, rows: list) -> None:
        """Populate the table once the background fetch completes."""
        if isinstance(rows, dict) and "error" in rows:
            self._status.setText(self.tr("Error: {}").format(rows['error']))
            return
        self._status.setText(self.tr("{} change record(s)").format(len(rows)))
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("field", "old_value", "new_value", "changed_at")):
                val = row.get(key) or ""
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(r, c, item)


class _ChangeHistoryWorker(QThread):
    """Fetch entry change history in a background thread."""

    finished = pyqtSignal(object)

    def __init__(self, lb_number: int, flask_port: int) -> None:
        super().__init__()
        self.lb_number = lb_number
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{self.lb_number}/changes",
                params={"limit": 200},
                timeout=10,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class LookupTab(QWidget):
    lb_double_clicked = pyqtSignal(int)
    lookup_completed = pyqtSignal(list, list)  # (detail_list, folder_list)

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._filter_mychecksums = False
        self._all_paths = []
        self._no_checksum_folders: set = set()
        self._last_detail = []
        self._lb_to_folders = {}
        self._worker = None
        self._generate_worker = None
        self._multi_generate_worker = None
        self._scan_tree_worker = None

        # Filtering state
        self._folder_filter: str | None = None       # active listbox folder filter
        self._summary_filter_lbs: set = set()        # active summary-row LB filter
        self._lb_status_filter: str = ""             # "public"|"private"|"missing"|""
        self._ignore_summary_selection = False
        self._best_match_only: bool = True           # hide non-MATCHED rows when a MATCHED exists
        self._history_selected_lb: int | None = None

        # Storage for full (unfiltered) rendered data
        self._sum_rows: list = []
        self._sum_colors: list = []
        self._sum_lb_nums: list = []          # int | None per summary row
        self._sum_lb_statuses: list = []      # str | None lb_status per summary row
        self._sum_user_data: list = []        # user_data dicts per summary row
        self._det_rows: list = []
        self._det_colors: list = []
        self._det_source_folders: list = []  # str | None per detail row

        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # Left: listbox + buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        self.list_header = QLabel(self.tr("Files: 0"))
        left_layout.addWidget(self.list_header)

        self.listbox = DropListWidget()
        self.listbox.files_dropped.connect(self._on_files_dropped)
        self.listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.listbox.customContextMenuRequested.connect(self._on_listbox_context)
        self.listbox.itemSelectionChanged.connect(self._on_listbox_selection_changed)
        self.listbox.itemClicked.connect(self._on_listbox_item_clicked)
        left_layout.addWidget(self.listbox)

        btn_layout = QVBoxLayout()
        self.clipboard_btn = QPushButton(self.tr("Lookup From Clipboard"))
        self.clipboard_btn.clicked.connect(self._on_clipboard_lookup)
        btn_layout.addWidget(self.clipboard_btn)

        self.listbox_btn = QPushButton(self.tr("Lookup From Listbox"))
        self.listbox_btn.clicked.connect(self._on_listbox_lookup)
        btn_layout.addWidget(self.listbox_btn)

        self.add_files_btn = QPushButton(self.tr("Add Files..."))
        self.add_files_btn.clicked.connect(self._on_add_files)
        btn_layout.addWidget(self.add_files_btn)

        self.add_folders_btn = QPushButton(self.tr("Add Folders..."))
        self.add_folders_btn.clicked.connect(self._on_add_folders)
        btn_layout.addWidget(self.add_folders_btn)

        self.scan_tree_btn = QPushButton(self.tr("Scan Tree..."))
        self.scan_tree_btn.setToolTip(
            self.tr("Recursively find all checksum files under a root directory and run a combined lookup.")
        )
        self.scan_tree_btn.clicked.connect(self._on_scan_tree)
        btn_layout.addWidget(self.scan_tree_btn)

        self.clear_list_btn = QPushButton(self.tr("Clear Listbox"))
        self.clear_list_btn.clicked.connect(self._on_clear_list)
        btn_layout.addWidget(self.clear_list_btn)

        self.clear_results_btn = QPushButton(self.tr("Clear Results"))
        self.clear_results_btn.clicked.connect(self._on_clear_results)
        btn_layout.addWidget(self.clear_results_btn)

        self.reconcile_audio_btn = QPushButton(self.tr("Reconcile Audio Files"))
        self.reconcile_audio_btn.setToolTip(
            self.tr("Rename audio files on disk to match the canonical filenames in the checksum DB.\n"
                    "Only available when matched results contain filename differences.")
        )
        self.reconcile_audio_btn.setEnabled(False)
        self.reconcile_audio_btn.clicked.connect(self._on_reconcile_audio)
        btn_layout.addWidget(self.reconcile_audio_btn)

        self.generate_btn = QPushButton(self.tr("Generate Missing Checksums"))
        self.generate_btn.setToolTip(
            self.tr("Generate .md5 and .ffp files for the folder of the selected listbox item,\n"
                    "if those files do not already exist.")
        )
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_checksums)
        btn_layout.addWidget(self.generate_btn)

        self.select_missing_btn = QPushButton(self.tr("Select Missing Checksums"))
        self.select_missing_btn.setToolTip(
            self.tr("Select all listbox entries and summary rows that have no checksum files.")
        )
        self.select_missing_btn.clicked.connect(self._select_missing_checksum_folders)
        btn_layout.addWidget(self.select_missing_btn)
        btn_layout.addStretch()

        left_layout.addLayout(btn_layout)
        left_widget.setFixedWidth(200)

        # Right: grids
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Summary grid
        self.summary_container = summary_container = QWidget()
        sc_layout = QVBoxLayout(summary_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)

        summary_header_row = QHBoxLayout()
        self.summary_label = QLabel(self.tr("Summary"))
        summary_header_row.addWidget(self.summary_label)
        self.best_match_chk = QCheckBox(self.tr("Best match only"))
        self.best_match_chk.setChecked(True)
        self.best_match_chk.setToolTip(
            self.tr("When a complete MATCHED result exists, hide secondary DUPLICATE/INCOMPLETE rows.\n"
                    "Uncheck to see all LB entries that share checksums with your files.")
        )
        self.best_match_chk.stateChanged.connect(self._on_best_match_toggled)
        summary_header_row.addWidget(self.best_match_chk)
        from PyQt6.QtWidgets import QComboBox
        self.lb_status_combo = QComboBox()
        self.lb_status_combo.addItem(self.tr("All LB statuses"))
        self.lb_status_combo.addItem(self.tr("Public only"))
        self.lb_status_combo.addItem(self.tr("Private only"))
        self.lb_status_combo.addItem(self.tr("Missing only"))
        self.lb_status_combo.setToolTip(self.tr("Filter summary rows by LB archive status"))
        self.lb_status_combo.currentIndexChanged.connect(self._on_lb_status_filter_changed)
        summary_header_row.addWidget(self.lb_status_combo)
        summary_header_row.addStretch()
        self.select_incomplete_btn = QPushButton(self.tr("Select All Incomplete"))
        self.select_incomplete_btn.clicked.connect(self._on_select_all_incomplete)
        summary_header_row.addWidget(self.select_incomplete_btn)
        self.generate_summary_btn = QPushButton(self.tr("Generate Missing Checksums"))
        self.generate_summary_btn.setEnabled(False)
        self.generate_summary_btn.clicked.connect(self._on_generate_for_summary_selected)
        summary_header_row.addWidget(self.generate_summary_btn)
        sc_layout.addLayout(summary_header_row)

        self.summary_model = _TableModel([self.tr(h) for h in SUMMARY_HEADERS])
        self.summary_proxy = _LookupSortProxy(_SUMMARY_COL_KINDS)
        self.summary_proxy.setSourceModel(self.summary_model)
        self.summary_view = QTableView()
        self.summary_view.setModel(self.summary_proxy)
        self.summary_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.summary_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.summary_view.setSortingEnabled(True)
        self.summary_proxy.sort(0, Qt.SortOrder.AscendingOrder)
        self.summary_view.doubleClicked.connect(self._on_summary_double_click)
        self.summary_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.summary_view.customContextMenuRequested.connect(self._on_summary_context)
        self.summary_view.selectionModel().selectionChanged.connect(self._on_summary_selection_changed)
        self.summary_view.clicked.connect(self._on_summary_clicked)
        self.summary_view.setMinimumHeight(120)
        sc_layout.addWidget(self.summary_view)
        splitter.addWidget(summary_container)

        # Detail grid
        self.detail_container = detail_container = QWidget()
        dc_layout = QVBoxLayout(detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        detail_header = QHBoxLayout()
        self.detail_label = QLabel(self.tr("Detail"))
        detail_header.addWidget(self.detail_label)
        detail_header.addStretch()
        self._history_btn = QPushButton(self.tr("History…"))
        self._history_btn.setToolTip(self.tr("View field-change history for the selected LB"))
        self._history_btn.setEnabled(False)
        self._history_btn.clicked.connect(self._on_show_history)
        detail_header.addWidget(self._history_btn)
        dc_layout.addLayout(detail_header)
        self.detail_model = _TableModel([self.tr(h) for h in DETAIL_HEADERS])
        self.detail_proxy = _LookupSortProxy(_DETAIL_COL_KINDS)
        self.detail_proxy.setSourceModel(self.detail_model)
        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_proxy)
        self.detail_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.detail_view.setSortingEnabled(True)
        self.detail_proxy.sort(1, Qt.SortOrder.AscendingOrder)
        self.detail_view.doubleClicked.connect(self._on_detail_double_click)
        self.detail_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.detail_view.customContextMenuRequested.connect(self._on_detail_context)
        dc_layout.addWidget(self.detail_view)
        splitter.addWidget(detail_container)

        right_layout.addWidget(splitter)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget, 1)

        self.status_label = QLabel("")
        right_layout.addWidget(self.status_label)

    # ── Proxy helpers ─────────────────────────────────────────────────────────

    def _sum_src_row(self, proxy_index: QModelIndex) -> int:
        """Return the source-model row for a summary proxy index."""
        return self.summary_proxy.mapToSource(proxy_index).row()

    def _det_src_row(self, proxy_index: QModelIndex) -> int:
        """Return the source-model row for a detail proxy index."""
        return self.detail_proxy.mapToSource(proxy_index).row()

    # ── Listbox management ────────────────────────────────────────────────────

    def _on_files_dropped(self, paths):
        for p in paths:
            self._add_path(p)
        self._update_list_header()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_listbox)

    _CHECKSUM_EXTS = {".md5", ".ffp", ".txt"}

    def _add_path(self, path):
        p = Path(path)
        if p.is_dir():
            found_checksums = False
            found_audio = False
            candidates = list(p.iterdir())
            for child in candidates:
                if child.is_file():
                    if child.suffix.lower() in self._CHECKSUM_EXTS:
                        found_checksums = True
                        s = str(child)
                        if s not in self._all_paths:
                            self._all_paths.append(s)
                    elif child.suffix.lower() in _AUDIO_EXTS:
                        found_audio = True
                elif child.is_dir():
                    for grandchild in child.iterdir():
                        if grandchild.is_file() and grandchild.suffix.lower() in self._CHECKSUM_EXTS:
                            found_checksums = True
                            s = str(grandchild)
                            if s not in self._all_paths:
                                self._all_paths.append(s)
            if found_checksums:
                self._no_checksum_folders.discard(str(p))
            elif found_audio:
                # Has audio but no checksums — flag for generation prompt
                self._no_checksum_folders.add(str(p))
        else:
            s = str(p)
            if s not in self._all_paths:
                self._all_paths.append(s)

    def _refresh_listbox(self):
        self.listbox.clear()
        for path in self._all_paths:
            name = Path(path).name
            if self._filter_mychecksums and "_mychecksums" not in name.lower():
                continue
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.listbox.addItem(item)
        for folder in sorted(self._no_checksum_folders):
            item = QListWidgetItem(f"⚠ {folder}  {self.tr('[no checksum files]')}")
            item.setForeground(styles.FG_WARNING)
            item.setData(Qt.ItemDataRole.UserRole, folder)
            item.setData(Qt.ItemDataRole.UserRole + 1, "no_checksums")
            self.listbox.addItem(item)
        self._update_list_header()

    def _update_list_header(self):
        shown = self.listbox.count()
        total = len(self._all_paths)
        if self._filter_mychecksums:
            self.list_header.setText(
                self.tr("Files: {}/{} [filtered: _mychecksums only]").format(shown, total)
            )
        else:
            self.list_header.setText(self.tr("Files: {}/{}").format(shown, total))

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr("Add Files"), str(Path.home()), self.tr("All files (*)"))
        for p in paths:
            self._all_paths.append(p)
        self._refresh_listbox()

    def _on_add_folders(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Add Folder"), str(Path.home()))
        if path:
            self._add_path(path)
            self._refresh_listbox()

    def _on_scan_tree(self):
        """Recursively scan a directory tree for checksum files, add to listbox, run lookup."""
        root = QFileDialog.getExistingDirectory(self, self.tr("Select Root Directory"))
        if not root:
            return
        self.status_label.setText(self.tr("Scanning…"))
        self.scan_tree_btn.setEnabled(False)
        self._scan_tree_worker = _ScanTreeWorker(Path(root), self._filter_mychecksums)
        self._scan_tree_worker.finished.connect(self._on_scan_tree_done)
        self._scan_tree_worker.error.connect(self._on_scan_tree_error)
        self._scan_tree_worker.start()

    def _on_scan_tree_done(self, found: list):
        self.scan_tree_btn.setEnabled(True)
        if not found:
            self.status_label.setText(self.tr("No checksum files found under selected folder."))
            return
        for path in found:
            if path not in self._all_paths:
                self._all_paths.append(path)
        self._refresh_listbox()
        self.clipboard_btn.setEnabled(False)
        self.listbox_btn.setEnabled(False)
        self.status_label.setText(self.tr("Looking up {} file(s)…").format(len(found)))
        self._worker = _LookupWorker(self.flask_port, paths=found)
        self._worker.finished.connect(lambda data: self._on_lookup_done(data, "scan-tree"))
        self._worker.error.connect(self._on_lookup_error)
        self._worker.start()

    def _on_scan_tree_error(self, msg: str):
        self.scan_tree_btn.setEnabled(True)
        self.status_label.setText(self.tr("Scan error: {}").format(msg))

    def _on_reconcile_audio(self):
        """Rename audio files on disk to match the canonical filenames stored in the checksum DB."""
        _AUDIO_EXTS = {".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".aiff", ".wv", ".m4a"}
        proposals = []
        seen = set()
        for d in self._last_detail:
            if d.get("status") not in ("MATCHED", "DUPLICATE"):
                continue
            sf = d.get("source_file")
            if not sf:
                continue
            input_fn = d.get("filename", "")
            db_fn = d.get("db_filename", "")
            if not input_fn or not db_fn or input_fn == db_fn:
                continue
            if Path(db_fn).suffix.lower() not in _AUDIO_EXTS:
                continue
            folder = str(Path(sf).parent)
            key = (folder, input_fn, db_fn)
            if key in seen:
                continue
            seen.add(key)
            proposals.append({
                "checksum": d.get("checksum", ""),
                "input_filename": input_fn,
                "db_filename": db_fn,
                "folder": folder,
            })

        if not proposals:
            self.status_label.setText(self.tr("No audio filename mismatches found in matched results."))
            return

        try:
            r = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/checksums/reconcile_audio",
                json={"proposals": proposals}, timeout=15,
            ).json()
        except Exception as e:
            self.status_label.setText(self.tr("Reconcile error: {}").format(e))
            return

        if "error" in r:
            self.status_label.setText(self.tr("Reconcile error: {}").format(r["error"]))
            return

        all_proposals = r.get("proposals", [])
        if not all_proposals:
            self.status_label.setText(
                self.tr("No renameable files found — files may already be correctly named or missing from disk.")
            )
            return

        from gui.widgets.reconcile_dialog import AudioReconcileDialog
        dlg = AudioReconcileDialog(all_proposals, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dlg.get_selected_renames()
        if not selected:
            return

        try:
            result = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/checksums/apply_reconcile_audio",
                json={"renames": selected}, timeout=30,
            ).json()
            applied = result.get("applied", 0)
            errors = result.get("errors", [])
            msg = self.tr("Renamed {} audio file(s).").format(applied)
            if errors:
                msg += self.tr("  {} error(s): {}").format(len(errors), errors[0])
            self.status_label.setText(msg)
        except Exception as e:
            self.status_label.setText(self.tr("Apply error: {}").format(e))

    def _on_clear_list(self):
        self._all_paths.clear()
        self._no_checksum_folders.clear()
        self.listbox.clear()
        self._update_list_header()
        self._folder_filter = None

    def _on_clear_results(self):
        self._sum_rows.clear()
        self._sum_colors.clear()
        self._sum_lb_nums.clear()
        self._sum_lb_statuses.clear()
        self._sum_user_data.clear()
        self._det_rows.clear()
        self._det_colors.clear()
        self._det_source_folders.clear()
        self.summary_model.set_data([], [])
        self.detail_model.set_data([], [])
        self.status_label.setText("")
        self._last_detail.clear()
        self._folder_filter = None
        self._summary_filter_lbs.clear()
        self._update_filter_labels()
        self.reconcile_audio_btn.setEnabled(False)

    def _on_listbox_context(self, pos):
        menu = QMenu(self)
        remove_act = QAction(self.tr("Remove from List"), self)
        remove_act.triggered.connect(self._remove_selected)
        menu.addAction(remove_act)

        clear_act = QAction(self.tr("Clear List"), self)
        clear_act.triggered.connect(self._on_clear_list)
        menu.addAction(clear_act)

        filter_act = QAction(
            self.tr("Disable _mychecksums filter") if self._filter_mychecksums
            else self.tr("Filter: _mychecksums only"),
            self
        )
        filter_act.triggered.connect(self._toggle_filter)
        menu.addAction(filter_act)

        menu.exec(self.listbox.mapToGlobal(pos))

    def _remove_selected(self):
        for item in self.listbox.selectedItems():
            if item.data(Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                self._no_checksum_folders.discard(item.data(Qt.ItemDataRole.UserRole))
            else:
                path = item.data(Qt.ItemDataRole.UserRole) or item.text()
                if path in self._all_paths:
                    self._all_paths.remove(path)
        self._refresh_listbox()

    def _toggle_filter(self):
        self._filter_mychecksums = not self._filter_mychecksums
        self._refresh_listbox()

    # ── Listbox click → folder filter ─────────────────────────────────────────

    def _on_listbox_selection_changed(self):
        """Update generate button state (selection-driven, not click-driven)."""
        self.generate_btn.setEnabled(bool(self.listbox.selectedItems()))

    def _on_listbox_item_clicked(self, item):
        """Toggle folder filter: click to filter, click same item again to clear."""
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if item.data(Qt.ItemDataRole.UserRole + 1) == "no_checksums":
            folder = path
        else:
            folder = str(Path(path).parent) if path else None

        if folder and folder == self._folder_filter:
            # Same folder clicked again → deselect and clear filter
            self._folder_filter = None
            self.listbox.clearSelection()
        else:
            self._folder_filter = folder

        self._apply_filters()

    # ── Summary row click → LB filter ─────────────────────────────────────────

    def _on_summary_selection_changed(self):
        if self._ignore_summary_selection:
            return
        folders = self._get_folders_for_selected_summary()
        self.generate_summary_btn.setEnabled(bool(folders))
        # Enable History button only when exactly one LB row is selected
        lbs = []
        for pidx in self.summary_view.selectionModel().selectedRows():
            row = self.summary_model.get_row(self._sum_src_row(pidx))
            if row:
                lb_str = str(row[0]).replace("LB-", "")
                try:
                    lbs.append(int(lb_str))
                except ValueError:
                    pass
        self._history_btn.setEnabled(len(lbs) == 1)
        self._history_selected_lb = lbs[0] if len(lbs) == 1 else None

    def _on_summary_clicked(self, index):
        """Toggle detail filter: click a summary row to filter detail, click again to clear."""
        lbs = set()
        for pidx in self.summary_view.selectionModel().selectedRows():
            row = self.summary_model.get_row(self._sum_src_row(pidx))
            if row:
                lb_str = str(row[0]).replace("LB-", "")
                try:
                    lbs.add(int(lb_str))
                except ValueError:
                    pass

        if lbs == self._summary_filter_lbs and lbs:
            # Same selection clicked again → clear filter
            self._summary_filter_lbs = set()
            self._ignore_summary_selection = True
            self.summary_view.clearSelection()
            self._ignore_summary_selection = False
        else:
            self._summary_filter_lbs = lbs

        self._update_filter_labels()
        self._apply_filters()

    def _on_best_match_toggled(self, state):
        self._best_match_only = bool(state)
        self._apply_filters()

    def _on_lb_status_filter_changed(self, index):
        mapping = {0: "", 1: "public", 2: "private", 3: "missing"}
        self._lb_status_filter = mapping.get(index, "")
        self._apply_filters()

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _update_filter_labels(self):
        """Update section headers to show when a filter is active."""
        if self._folder_filter:
            folder_name = Path(self._folder_filter).name
            self.summary_label.setText(self.tr("Summary  [folder: {}]").format(folder_name))
        else:
            self.summary_label.setText(self.tr("Summary"))

        if self._summary_filter_lbs:
            lb_str = ", ".join(f"LB-{lb}" for lb in sorted(self._summary_filter_lbs))
            self.detail_label.setText(self.tr("Detail  [filter: {}]").format(lb_str))
        else:
            self.detail_label.setText(self.tr("Detail"))

    def _apply_filters(self):
        """Rebuild summary and detail views applying active folder and LB filters."""
        self._update_filter_labels()

        # Determine which detail row indices to show
        det_indices = list(range(len(self._det_rows)))
        sum_indices = list(range(len(self._sum_rows)))

        if self._folder_filter:
            det_indices = [
                i for i in det_indices
                if self._det_source_folders[i] == self._folder_filter
            ]
            # Show only summary rows whose LB has at least one detail item in this folder
            visible_lbs = set()
            for i in det_indices:
                lb_str = self._det_rows[i][3]
                if lb_str.startswith("LB-"):
                    try:
                        visible_lbs.add(int(lb_str.replace("LB-", "")))
                    except ValueError:
                        pass
            sum_indices = [
                i for i in sum_indices
                if self._sum_lb_nums[i] in visible_lbs
                or self._sum_lb_nums[i] is None  # no-checksum / not-found rows
            ]

        if self._lb_status_filter:
            sum_indices = [
                i for i in sum_indices
                if self._sum_lb_statuses[i] == self._lb_status_filter
            ]

        if self._summary_filter_lbs:
            def _lb_matches(lb_str):
                if not lb_str.startswith("LB-"):
                    return False
                try:
                    return int(lb_str.replace("LB-", "")) in self._summary_filter_lbs
                except ValueError:
                    return False
            det_indices = [i for i in det_indices if _lb_matches(self._det_rows[i][3])]

        # Best-match-only filter: when any summary row in the current view is MATCHED,
        # hide rows that are DUPLICATE or INCOMPLETE so secondary hits don't clutter results.
        if self._best_match_only:
            matched_indices = [i for i in sum_indices if self._sum_rows[i][8] == "MATCHED"]
            if matched_indices:
                matched_lbs = {self._sum_lb_nums[i] for i in matched_indices}

                def _parse_det_lb(lb_str: str) -> int | None:
                    if lb_str.startswith("LB-"):
                        try:
                            return int(lb_str[3:])
                        except ValueError:
                            pass
                    return None

                sum_indices = matched_indices
                det_indices = [
                    i for i in det_indices
                    if _parse_det_lb(self._det_rows[i][3]) in matched_lbs
                ]

        # Apply to models
        det_rows = [self._det_rows[i] for i in det_indices]
        det_colors = [self._det_colors[i] for i in det_indices]
        self.detail_model.set_data(det_rows, det_colors)

        sum_rows = [self._sum_rows[i] for i in sum_indices]
        sum_colors = [self._sum_colors[i] for i in sum_indices]
        sum_user = [self._sum_user_data[i] for i in sum_indices]
        self.summary_model.set_data(sum_rows, sum_colors, sum_user)

    # ── Generate checksums ────────────────────────────────────────────────────

    def _on_generate_checksums(self):
        items = self.listbox.selectedItems()
        if not items:
            return
        folders: set = set()
        for item in items:
            if item.data(Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                folder = item.data(Qt.ItemDataRole.UserRole)
            else:
                raw = item.data(Qt.ItemDataRole.UserRole) or item.text()
                folder = str(Path(raw).parent)
            if folder and Path(folder).is_dir():
                folders.add(folder)
        if not folders:
            self.status_label.setText(self.tr("No valid folders found for selected items."))
            return
        self.generate_btn.setEnabled(False)
        self._multi_generate_worker = _GenerateWorker(self.flask_port, list(folders))
        self._multi_generate_worker.progress.connect(self.status_label.setText)
        self._multi_generate_worker.finished.connect(self._on_multi_generate_done)
        self._multi_generate_worker.start()

    def _on_generate_done(self, result):
        self.generate_btn.setEnabled(True)
        parts = []
        if result.get("generated"):
            # Add newly created files to the listbox
            for path in result["generated"]:
                if path not in self._all_paths:
                    self._all_paths.append(path)
            self._refresh_listbox()
            names = [Path(p).name for p in result["generated"]]
            parts.append(self.tr("Generated: {}").format(', '.join(names)))
        if result.get("skipped"):
            parts.append(self.tr("Already existed: {}").format(', '.join(result['skipped'])))
        if result.get("errors"):
            parts.append(self.tr("Errors: {}").format('; '.join(result['errors'])))
        self.status_label.setText("  |  ".join(parts) if parts else self.tr("Done."))
        self._on_listbox_selection_changed()

    # ── Summary table: multi-select + generate ────────────────────────────────

    def _on_select_all_incomplete(self):
        selection = QItemSelection()
        for pi in range(self.summary_proxy.rowCount()):
            src_row = self._sum_src_row(self.summary_proxy.index(pi, 0))
            row = self.summary_model.get_row(src_row)
            is_incomplete = row and row[8] == "INCOMPLETE"
            is_no_checksum = (
                self.summary_model.data(
                    self.summary_model.index(src_row, 0), Qt.ItemDataRole.UserRole + 1
                ) == "no_checksums"
            )
            if is_incomplete or is_no_checksum:
                selection.select(
                    self.summary_proxy.index(pi, 0),
                    self.summary_proxy.index(pi, self.summary_proxy.columnCount() - 1),
                )
        self.summary_view.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _get_folders_for_selected_summary(self):
        seen = set()
        folders = []
        src_rows_seen = set()
        for pidx in self.summary_view.selectedIndexes():
            src_row = self._sum_src_row(pidx)
            if src_row in src_rows_seen:
                continue
            src_rows_seen.add(src_row)
            col0 = self.summary_model.index(src_row, 0)
            # No-checksum rows store the folder path directly in UserRole
            if self.summary_model.data(col0, Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                folder = self.summary_model.data(col0, Qt.ItemDataRole.UserRole)
                if folder and folder not in seen:
                    seen.add(folder)
                    folders.append(folder)
                continue
            row = self.summary_model.get_row(src_row)
            if not row or row[8] != "INCOMPLETE":
                continue
            lb_str = str(row[0]).replace("LB-", "")
            try:
                lb_num = int(lb_str)
                for folder in self._lb_to_folders.get(lb_num, set()):
                    if folder not in seen:
                        seen.add(folder)
                        folders.append(folder)
            except ValueError:
                pass
        return folders

    def _on_generate_for_summary_selected(self):
        folders = self._get_folders_for_selected_summary()
        if not folders:
            self.status_label.setText(self.tr("No folders found for selected INCOMPLETE entries."))
            return
        self.generate_summary_btn.setEnabled(False)
        self._multi_generate_worker = _GenerateWorker(self.flask_port, folders)
        self._multi_generate_worker.progress.connect(self.status_label.setText)
        self._multi_generate_worker.finished.connect(self._on_multi_generate_done)
        self._multi_generate_worker.start()

    def _on_multi_generate_done(self, response):
        all_generated, all_errors = [], []
        if "error" in response:
            all_errors.append(response["error"])
        for result in response.get("results", []):
            all_generated.extend(result.get("generated", []))
            all_errors.extend(result.get("errors", []))
            if result.get("generated"):
                self._no_checksum_folders.discard(result.get("folder", ""))
        if all_generated:
            for path in all_generated:
                if path not in self._all_paths:
                    self._all_paths.append(path)
        self._refresh_listbox()
        parts = []
        if all_generated:
            parts.append(self.tr("Generated: {}").format(', '.join(Path(p).name for p in all_generated)))
        if all_errors:
            parts.append(self.tr("Errors: {}").format('; '.join(all_errors)))
        self.status_label.setText("  |  ".join(parts) if parts else self.tr("Done."))
        self.generate_btn.setEnabled(bool(self.listbox.selectedItems()))
        self._on_summary_selection_changed()

    def _on_summary_context(self, pos):
        menu = QMenu(self)
        folders = self._get_folders_for_selected_summary()
        if folders:
            label = self.tr("Generate Missing Checksums ({} folder(s))").format(len(folders))
            gen_act = QAction(label, self)
            gen_act.triggered.connect(self._on_generate_for_summary_selected)
            menu.addAction(gen_act)

        index = self.summary_view.indexAt(pos)
        if index.isValid():
            row = self.summary_model.get_row(self._sum_src_row(index))
            if row:
                lb_str = str(row[0]).replace("LB-", "")
                try:
                    lb_num = int(lb_str)
                    url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                    open_web = QAction(self.tr("Go to Web Page"), self)
                    open_web.triggered.connect(lambda: webbrowser.open(url))
                    menu.addAction(open_web)

                    wish_act = QAction(self.tr("Add to Wishlist"), self)
                    wish_act.triggered.connect(lambda: self._add_to_wishlist(lb_num))
                    menu.addAction(wish_act)
                except ValueError:
                    pass

        if not menu.isEmpty():
            menu.exec(self.summary_view.mapToGlobal(pos))

    def _add_to_wishlist(self, lb_num: int):
        try:
            import requests as _req
            resp = _req.post(
                f"http://127.0.0.1:{self.flask_port}/api/wishlist",
                json={"lb_number": lb_num}, timeout=5,
            ).json()
            if resp.get("added"):
                self.status_label.setText(self.tr("LB-{} added to wishlist.").format(f"{lb_num:05d}"))
            else:
                self.status_label.setText(self.tr("LB-{} already on wishlist.").format(f"{lb_num:05d}"))
        except Exception as e:
            self.status_label.setText(self.tr("Wishlist error: {}").format(e))

    # ── Theme refresh ─────────────────────────────────────────────────────────

    def refresh_colors(self):
        self.summary_model.refresh_colors(lambda row:
            styles.ROW_MATCHED if row[8] == "MATCHED" else
            styles.ROW_MISSING if row[8] == "INCOMPLETE" else
            styles.ROW_DUPLICATE if row[6] and int(row[6]) > 0 else
            styles.ROW_NOT_FOUND
        )
        self.detail_model.refresh_colors(lambda row:
            styles.ROW_NOT_FOUND if row[5] == "NOT FOUND" else
            styles.ROW_DUPLICATE if row[5] == "DUPLICATE" else
            styles.ROW_MISSING if "INCOMPLETE" in str(row[5]) else
            styles.ROW_XREF if row[4] else
            styles.ROW_MATCHED
        )

    # ── Lookups ───────────────────────────────────────────────────────────────

    def _on_clipboard_lookup(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text.strip():
            self.status_label.setText(self.tr("Clipboard is empty."))
            return
        self._run_lookup(text, source="clipboard")

    def _on_listbox_lookup(self):
        paths = []
        for i in range(self.listbox.count()):
            item = self.listbox.item(i)
            if item.data(Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                continue
            paths.append(item.data(Qt.ItemDataRole.UserRole) or item.text())
        if not paths:
            self.status_label.setText(self.tr("No checksum files in listbox."))
            return
        self.clipboard_btn.setEnabled(False)
        self.listbox_btn.setEnabled(False)
        self.status_label.setText(self.tr("Looking up..."))
        self._worker = _LookupWorker(self.flask_port, paths=paths)
        self._worker.finished.connect(lambda data: self._on_lookup_done(data, "listbox"))
        self._worker.error.connect(self._on_lookup_error)
        self._worker.start()

    def _run_lookup(self, text, source=""):
        self.clipboard_btn.setEnabled(False)
        self.listbox_btn.setEnabled(False)
        self.status_label.setText(self.tr("Looking up..."))

        self._worker = _LookupWorker(self.flask_port, text)
        self._worker.finished.connect(lambda data: self._on_lookup_done(data, source))
        self._worker.error.connect(self._on_lookup_error)
        self._worker.start()

    def _on_lookup_done(self, data, source):
        self.clipboard_btn.setEnabled(True)
        self.listbox_btn.setEnabled(True)

        summary_info = data.get("summary", {})
        detail_list = data.get("detail", [])
        self._last_detail = detail_list

        # Reset filters on new lookup
        self._folder_filter = None
        self._summary_filter_lbs = set()

        # Build LB → folder mapping for "generate missing checksums" feature
        self._lb_to_folders = {}
        for d in detail_list:
            if d.get("lb_number") and d.get("source_file"):
                lb = d["lb_number"]
                folder = str(Path(d["source_file"]).parent)
                self._lb_to_folders.setdefault(lb, set()).add(folder)

        # LB-status color overrides: Private → light blue, Missing → light gray
        _LB_STATUS_COLOR = {
            "private": styles.ROW_PRIVATE,
            "missing": styles.ROW_GREY,
        }

        # Build summary rows and colors
        lb_summaries = summary_info.get("lb_summary", [])
        sum_rows = []
        sum_colors = []
        sum_lb_nums = []
        sum_lb_statuses = []
        sum_user_data = []
        for s in lb_summaries:
            row = [
                f"LB-{s['lb_number']}",
                source,
                s["given"],
                s["matched"],
                s["not_found"] if "not_found" in s else 0,
                s["missing_from_set"],
                s["duplicates"],
                s["xrefs"],
                s["status"],
            ]
            lb_status = s.get("lb_status")
            sum_rows.append(row)
            sum_lb_nums.append(s["lb_number"])
            sum_lb_statuses.append(lb_status)
            sum_user_data.append({"lb_status": lb_status})
            # lb_status overrides match-quality color for Private/Missing
            if lb_status in _LB_STATUS_COLOR:
                sum_colors.append(_LB_STATUS_COLOR[lb_status])
            elif s["status"] == "MATCHED":
                sum_colors.append(styles.ROW_MATCHED)
            elif s["status"] == "INCOMPLETE":
                sum_colors.append(styles.ROW_MISSING)
            elif s["duplicates"] > 0:
                sum_colors.append(styles.ROW_DUPLICATE)
            else:
                sum_colors.append(styles.ROW_NOT_FOUND)

        # Add summary rows for input folders whose checksums had no DB match at all
        not_found_items = [d for d in detail_list if d["status"] == "NOT FOUND"]
        if not_found_items:
            covered_folders: set = set()
            for d in detail_list:
                if d.get("lb_number") and d.get("source_file"):
                    covered_folders.add(str(Path(d["source_file"]).parent))
            not_found_by_folder: dict = {}
            for d in not_found_items:
                folder_key = (
                    str(Path(d["source_file"]).parent) if d.get("source_file") else ""
                )
                if folder_key not in covered_folders:
                    not_found_by_folder.setdefault(folder_key, 0)
                    not_found_by_folder[folder_key] += 1
            for folder_key, count in sorted(not_found_by_folder.items()):
                label = Path(folder_key).name if folder_key else "NOT FOUND"
                sum_rows.append([label, source, count, 0, count, 0, 0, 0, "NOT FOUND"])
                sum_colors.append(styles.ROW_NOT_FOUND)
                sum_lb_nums.append(None)
                sum_lb_statuses.append(None)
                sum_user_data.append({})

        # No-checksum folders (listbox source or scan-tree)
        if source in ("listbox", "scan-tree"):
            _bg = styles.ROW_MISSING_FILE
            _fg = styles.FG_WARNING
            for folder in sorted(self._no_checksum_folders):
                row = [
                    Path(folder).name, "", "0", "", "", "", "", "",
                    "NO CHECKSUMS — Generate?",
                ]
                sum_rows.append(row)
                sum_colors.append(_bg)
                sum_lb_nums.append(None)
                sum_lb_statuses.append(None)
                sum_user_data.append({"path": folder, "type": "no_checksums", "fg": _fg})

        # Build detail rows and colors; also record source folder per row
        det_rows = []
        det_colors = []
        det_source_folders = []
        seen_det_rows = set()
        for d in detail_list:
            lb_str = f"LB-{d['lb_number']}" if d["lb_number"] else "—"
            row = [
                d["checksum"],
                d["filename"],
                d["type"],
                lb_str,
                d["xref"],
                d["status"],
                source,
            ]
            row_key = (d["checksum"], lb_str)
            if row_key in seen_det_rows:
                continue
            seen_det_rows.add(row_key)
            det_rows.append(row)
            sf = d.get("source_file")
            det_source_folders.append(str(Path(sf).parent) if sf else None)
            status = d["status"]
            if status == "NOT FOUND":
                det_colors.append(styles.ROW_NOT_FOUND)
            elif status == "DUPLICATE":
                det_colors.append(styles.ROW_DUPLICATE)
            elif "INCOMPLETE" in status:
                det_colors.append(styles.ROW_MISSING)
            elif d.get("xref"):
                det_colors.append(styles.ROW_XREF)
            else:
                det_colors.append(styles.ROW_MATCHED)

        # Store full unfiltered data
        self._sum_rows = sum_rows
        self._sum_colors = sum_colors
        self._sum_lb_nums = sum_lb_nums
        self._sum_lb_statuses = sum_lb_statuses
        self._sum_user_data = sum_user_data
        self._det_rows = det_rows
        self._det_colors = det_colors
        self._det_source_folders = det_source_folders

        # Render without any filter active
        self._apply_filters()

        self.summary_view.resizeColumnsToContents()
        self.detail_view.resizeColumnsToContents()

        matched = summary_info.get("matched", 0)
        given = summary_info.get("given", 0)
        lbs = len(summary_info.get("lb_numbers_found", []))
        self.status_label.setText(
            self.tr("Given: {}  |  Matched: {}  |  LB numbers found: {}").format(given, matched, lbs)
        )

        folders = list(dict.fromkeys(str(Path(p).parent) for p in self._all_paths))
        self.lookup_completed.emit(detail_list, folders)

        # Enable reconcile button if any matched row has a filename mismatch and a known source
        _AUDIO_EXTS = {".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".aiff", ".wv", ".m4a"}
        has_mismatch = any(
            d.get("status") in ("MATCHED", "DUPLICATE")
            and d.get("source_file")
            and d.get("db_filename")
            and d.get("filename") != d.get("db_filename")
            and Path(d.get("db_filename", "")).suffix.lower() in _AUDIO_EXTS
            for d in detail_list
        )
        self.reconcile_audio_btn.setEnabled(has_mismatch)

    def _append_no_checksum_summary_rows(self):
        """Legacy method kept for compatibility; rows are now built inside _on_lookup_done."""
        pass

    def _select_missing_checksum_folders(self):
        # Select matching listbox items
        for i in range(self.listbox.count()):
            item = self.listbox.item(i)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole + 1) == "no_checksums")
        # Select matching summary rows
        selection = QItemSelection()
        for i in range(self.summary_model.rowCount()):
            idx = self.summary_model.index(i, 0)
            if self.summary_model.data(idx, Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                selection.select(
                    idx,
                    self.summary_model.index(i, self.summary_model.columnCount() - 1),
                )
        self.summary_view.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _on_lookup_error(self, msg):
        self.clipboard_btn.setEnabled(True)
        self.listbox_btn.setEnabled(True)
        self.status_label.setText(self.tr("Error: {}").format(msg))

    # ── Expose folders for other tabs ─────────────────────────────────────────

    def get_lookup_folders(self) -> list[str]:
        """Return unique parent folders of all loaded checksum files."""
        return list(dict.fromkeys(str(Path(p).parent) for p in self._all_paths))

    # ── Grid interactions ─────────────────────────────────────────────────────

    def _on_summary_double_click(self, index):
        row = self.summary_model.get_row(self._sum_src_row(index))
        if row:
            lb_str = str(row[0]).replace("LB-", "")
            try:
                lb_num = int(lb_str)
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                webbrowser.open(url)
            except ValueError:
                pass

    def _on_show_history(self) -> None:
        """Open the change-history dialog for the currently selected LB."""
        if self._history_selected_lb is None:
            return
        dlg = _ChangeHistoryDialog(self._history_selected_lb, self.flask_port, parent=self)
        dlg.exec()

    def _on_detail_double_click(self, index):
        row = self.detail_model.get_row(self._det_src_row(index))
        if row:
            lb_str = str(row[3]).replace("LB-", "")
            try:
                lb_num = int(lb_str)
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                webbrowser.open(url)
            except ValueError:
                pass

    def _on_detail_context(self, pos):
        index = self.detail_view.indexAt(pos)
        if not index.isValid():
            return
        row = self.detail_model.get_row(self._det_src_row(index))
        if not row:
            return

        menu = QMenu(self)
        copy_chk = QAction(self.tr("Copy Checksum"), self)
        copy_chk.triggered.connect(lambda: QApplication.clipboard().setText(str(row[0])))
        menu.addAction(copy_chk)

        copy_row = QAction(self.tr("Copy Row"), self)
        copy_row.triggered.connect(lambda: QApplication.clipboard().setText("\t".join(str(c) for c in row)))
        menu.addAction(copy_row)

        lb_str = str(row[3]).replace("LB-", "")
        try:
            lb_num = int(lb_str)
            open_web = QAction(self.tr("Go to Web Page"), self)
            url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
            open_web.triggered.connect(lambda: webbrowser.open(url))
            menu.addAction(open_web)
        except ValueError:
            pass

        menu.exec(self.detail_view.mapToGlobal(pos))

    def lookup_lb_number(self, lb_number):
        """Called externally (e.g. from Search tab) to look up a specific LB's checksums."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{lb_number}",
                timeout=10,
            )
            data = resp.json()
            checksums = data.get("checksums", [])
            if not checksums:
                self.status_label.setText(self.tr("No checksums found for LB-{}").format(lb_number))
                return
            text_lines = []
            for c in checksums:
                if c["chk_type"] == "f":
                    text_lines.append(f"{c['filename']}:{c['checksum']}")
                else:
                    text_lines.append(f"{c['checksum']}  {c['filename']}")
            self._run_lookup("\n".join(text_lines), source=f"LB-{lb_number}")
        except Exception as e:
            self.status_label.setText(self.tr("Error: {}").format(e))

    def resize_columns_to_font(self) -> None:
        self.summary_view.resizeColumnsToContents()
        self.detail_view.resizeColumnsToContents()
