import re
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QThread, pyqtSignal,
    QItemSelection, QItemSelectionModel,
)
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTableView, QAbstractItemView, QMenu, QApplication,
    QFileDialog, QHeaderView,
)

from gui.styles import ROW_MATCHED, ROW_NOT_FOUND, ROW_MISSING, ROW_DUPLICATE, ROW_XREF


SUMMARY_HEADERS = ["LB Number", "Source", "Given", "Matched", "Not Found", "Missing", "Dups", "Xrefs", "Status"]
DETAIL_HEADERS = ["Checksum", "Filename", "Type", "LB Number", "Xref", "Status", "Source"]


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
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # Left: listbox + buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        self.list_header = QLabel("Files: 0")
        left_layout.addWidget(self.list_header)

        self.listbox = DropListWidget()
        self.listbox.files_dropped.connect(self._on_files_dropped)
        self.listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.listbox.customContextMenuRequested.connect(self._on_listbox_context)
        self.listbox.itemSelectionChanged.connect(self._on_listbox_selection_changed)
        left_layout.addWidget(self.listbox)

        btn_layout = QVBoxLayout()
        self.clipboard_btn = QPushButton("Lookup From Clipboard")
        self.clipboard_btn.clicked.connect(self._on_clipboard_lookup)
        btn_layout.addWidget(self.clipboard_btn)

        self.listbox_btn = QPushButton("Lookup From Listbox")
        self.listbox_btn.clicked.connect(self._on_listbox_lookup)
        btn_layout.addWidget(self.listbox_btn)

        self.add_files_btn = QPushButton("Add Files...")
        self.add_files_btn.clicked.connect(self._on_add_files)
        btn_layout.addWidget(self.add_files_btn)

        self.add_folders_btn = QPushButton("Add Folders...")
        self.add_folders_btn.clicked.connect(self._on_add_folders)
        btn_layout.addWidget(self.add_folders_btn)

        self.clear_list_btn = QPushButton("Clear Listbox")
        self.clear_list_btn.clicked.connect(self._on_clear_list)
        btn_layout.addWidget(self.clear_list_btn)

        self.clear_results_btn = QPushButton("Clear Results")
        self.clear_results_btn.clicked.connect(self._on_clear_results)
        btn_layout.addWidget(self.clear_results_btn)

        self.generate_btn = QPushButton("Generate Missing Checksums")
        self.generate_btn.setToolTip(
            "Generate .md5 and .ffp files for the folder of the selected listbox item,\n"
            "if those files do not already exist."
        )
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_checksums)
        btn_layout.addWidget(self.generate_btn)

        self.select_missing_btn = QPushButton("Select Missing Checksums")
        self.select_missing_btn.setToolTip(
            "Select all listbox entries and summary rows that have no checksum files."
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
        summary_header_row.addWidget(QLabel("Summary"))
        summary_header_row.addStretch()
        self.select_incomplete_btn = QPushButton("Select All Incomplete")
        self.select_incomplete_btn.clicked.connect(self._on_select_all_incomplete)
        summary_header_row.addWidget(self.select_incomplete_btn)
        self.generate_summary_btn = QPushButton("Generate Missing Checksums")
        self.generate_summary_btn.setEnabled(False)
        self.generate_summary_btn.clicked.connect(self._on_generate_for_summary_selected)
        summary_header_row.addWidget(self.generate_summary_btn)
        sc_layout.addLayout(summary_header_row)

        self.summary_model = _TableModel(SUMMARY_HEADERS)
        self.summary_view = QTableView()
        self.summary_view.setModel(self.summary_model)
        self.summary_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.summary_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.summary_view.doubleClicked.connect(self._on_summary_double_click)
        self.summary_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.summary_view.customContextMenuRequested.connect(self._on_summary_context)
        self.summary_view.selectionModel().selectionChanged.connect(self._on_summary_selection_changed)
        self.summary_view.setMinimumHeight(120)
        sc_layout.addWidget(self.summary_view)
        splitter.addWidget(summary_container)

        # Detail grid
        self.detail_container = detail_container = QWidget()
        dc_layout = QVBoxLayout(detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.addWidget(QLabel("Detail"))
        self.detail_model = _TableModel(DETAIL_HEADERS)
        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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
            found_any = False
            candidates = list(p.iterdir())
            for child in candidates:
                if child.is_file() and child.suffix.lower() in self._CHECKSUM_EXTS:
                    found_any = True
                    s = str(child)
                    if s not in self._all_paths:
                        self._all_paths.append(s)
                elif child.is_dir():
                    for grandchild in child.iterdir():
                        if grandchild.is_file() and grandchild.suffix.lower() in self._CHECKSUM_EXTS:
                            found_any = True
                            s = str(grandchild)
                            if s not in self._all_paths:
                                self._all_paths.append(s)
            if found_any:
                self._no_checksum_folders.discard(str(p))
            else:
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
            item = QListWidgetItem(f"⚠ {folder}  [no checksum files]")
            item.setForeground(QColor("#cc4400"))
            item.setData(Qt.ItemDataRole.UserRole, folder)
            item.setData(Qt.ItemDataRole.UserRole + 1, "no_checksums")
            self.listbox.addItem(item)
        self._update_list_header()

    def _update_list_header(self):
        shown = self.listbox.count()
        total = len(self._all_paths)
        filter_str = " [filtered: _mychecksums only]" if self._filter_mychecksums else ""
        self.list_header.setText(f"Files: {shown}/{total}{filter_str}")

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files", str(Path.home()), "All files (*)")
        for p in paths:
            self._all_paths.append(p)
        self._refresh_listbox()

    def _on_add_folders(self):
        path = QFileDialog.getExistingDirectory(self, "Add Folder", str(Path.home()))
        if path:
            self._add_path(path)
            self._refresh_listbox()

    def _on_clear_list(self):
        self._all_paths.clear()
        self._no_checksum_folders.clear()
        self.listbox.clear()
        self._update_list_header()

    def _on_clear_results(self):
        self.summary_model.set_data([], [])
        self.detail_model.set_data([], [])
        self.status_label.setText("")
        self._last_detail.clear()

    def _on_listbox_context(self, pos):
        menu = QMenu(self)
        remove_act = QAction("Remove from List", self)
        remove_act.triggered.connect(self._remove_selected)
        menu.addAction(remove_act)

        clear_act = QAction("Clear List", self)
        clear_act.triggered.connect(self._on_clear_list)
        menu.addAction(clear_act)

        filter_act = QAction(
            "Disable _mychecksums filter" if self._filter_mychecksums else "Filter: _mychecksums only",
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

    # ── Generate checksums ────────────────────────────────────────────────────

    def _on_listbox_selection_changed(self):
        self.generate_btn.setEnabled(bool(self.listbox.selectedItems()))

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
            self.status_label.setText("No valid folders found for selected items.")
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
            parts.append(f"Generated: {', '.join(names)}")
        if result.get("skipped"):
            parts.append(f"Already existed: {', '.join(result['skipped'])}")
        if result.get("errors"):
            parts.append(f"Errors: {'; '.join(result['errors'])}")
        self.status_label.setText("  |  ".join(parts) if parts else "Done.")
        self._on_listbox_selection_changed()

    # ── Summary table: multi-select + generate ────────────────────────────────

    def _on_summary_selection_changed(self):
        folders = self._get_folders_for_selected_summary()
        self.generate_summary_btn.setEnabled(bool(folders))

    def _on_select_all_incomplete(self):
        model = self.summary_model
        selection = QItemSelection()
        for i in range(model.rowCount()):
            row = model.get_row(i)
            is_incomplete = row and row[8] == "INCOMPLETE"
            is_no_checksum = model.data(model.index(i, 0), Qt.ItemDataRole.UserRole + 1) == "no_checksums"
            if is_incomplete or is_no_checksum:
                selection.select(model.index(i, 0), model.index(i, model.columnCount() - 1))
        self.summary_view.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _get_folders_for_selected_summary(self):
        seen = set()
        folders = []
        rows_seen = set()
        for idx in self.summary_view.selectedIndexes():
            row_idx = idx.row()
            if row_idx in rows_seen:
                continue
            rows_seen.add(row_idx)
            col0 = self.summary_model.index(row_idx, 0)
            # No-checksum rows store the folder path directly in UserRole
            if self.summary_model.data(col0, Qt.ItemDataRole.UserRole + 1) == "no_checksums":
                folder = self.summary_model.data(col0, Qt.ItemDataRole.UserRole)
                if folder and folder not in seen:
                    seen.add(folder)
                    folders.append(folder)
                continue
            row = self.summary_model.get_row(row_idx)
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
            self.status_label.setText("No folders found for selected INCOMPLETE entries.")
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
            parts.append(f"Generated: {', '.join(Path(p).name for p in all_generated)}")
        if all_errors:
            parts.append(f"Errors: {'; '.join(all_errors)}")
        self.status_label.setText("  |  ".join(parts) if parts else "Done.")
        self.generate_btn.setEnabled(bool(self.listbox.selectedItems()))
        self._on_summary_selection_changed()

    def _on_summary_context(self, pos):
        menu = QMenu(self)
        folders = self._get_folders_for_selected_summary()
        if folders:
            label = f"Generate Missing Checksums ({len(folders)} folder(s))"
            gen_act = QAction(label, self)
            gen_act.triggered.connect(self._on_generate_for_summary_selected)
            menu.addAction(gen_act)

        index = self.summary_view.indexAt(pos)
        if index.isValid():
            row = self.summary_model.get_row(index.row())
            if row:
                lb_str = str(row[0]).replace("LB-", "")
                try:
                    lb_num = int(lb_str)
                    url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                    open_web = QAction("Go to Web Page", self)
                    open_web.triggered.connect(lambda: webbrowser.open(url))
                    menu.addAction(open_web)
                except ValueError:
                    pass

        if not menu.isEmpty():
            menu.exec(self.summary_view.mapToGlobal(pos))

    # ── Theme refresh ─────────────────────────────────────────────────────────

    def refresh_colors(self):
        from gui import styles
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
            self.status_label.setText("Clipboard is empty.")
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
            self.status_label.setText("No checksum files in listbox.")
            return
        self.clipboard_btn.setEnabled(False)
        self.listbox_btn.setEnabled(False)
        self.status_label.setText("Looking up...")
        self._worker = _LookupWorker(self.flask_port, paths=paths)
        self._worker.finished.connect(lambda data: self._on_lookup_done(data, "listbox"))
        self._worker.error.connect(self._on_lookup_error)
        self._worker.start()

    def _run_lookup(self, text, source=""):
        self.clipboard_btn.setEnabled(False)
        self.listbox_btn.setEnabled(False)
        self.status_label.setText("Looking up...")

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

        # Build LB → folder mapping for "generate missing checksums" feature
        self._lb_to_folders = {}
        for d in detail_list:
            if d.get("lb_number") and d.get("source_file"):
                lb = d["lb_number"]
                folder = str(Path(d["source_file"]).parent)
                self._lb_to_folders.setdefault(lb, set()).add(folder)

        # Build summary rows and colors
        lb_summaries = summary_info.get("lb_summary", [])
        sum_rows = []
        sum_colors = []
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
            sum_rows.append(row)
            if s["status"] == "MATCHED":
                sum_colors.append(ROW_MATCHED)
            elif s["status"] == "INCOMPLETE":
                sum_colors.append(ROW_MISSING)
            elif s["duplicates"] > 0:
                sum_colors.append(ROW_DUPLICATE)
            else:
                sum_colors.append(ROW_NOT_FOUND)

        # Build detail rows and colors
        det_rows = []
        det_colors = []
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
            det_rows.append(row)
            status = d["status"]
            if status == "NOT FOUND":
                det_colors.append(ROW_NOT_FOUND)
            elif status == "DUPLICATE":
                det_colors.append(ROW_DUPLICATE)
            elif "INCOMPLETE" in status:
                det_colors.append(ROW_MISSING)
            elif d.get("xref"):
                det_colors.append(ROW_XREF)
            else:
                det_colors.append(ROW_MATCHED)

        # Unmatched checksums (no LB)
        unmatched = [d for d in detail_list if d["lb_number"] is None]
        for d in unmatched:
            row = [d["checksum"], d["filename"], d["type"], "—", 0, "NOT FOUND", source]
            if row not in det_rows:
                det_rows.append(row)
                det_colors.append(ROW_NOT_FOUND)

        self.summary_model.set_data(sum_rows, sum_colors)
        self.detail_model.set_data(det_rows, det_colors)

        if source == "listbox":
            self._append_no_checksum_summary_rows()

        self.summary_view.resizeColumnsToContents()
        self.detail_view.resizeColumnsToContents()

        matched = summary_info.get("matched", 0)
        given = summary_info.get("given", 0)
        lbs = len(summary_info.get("lb_numbers_found", []))
        self.status_label.setText(
            f"Given: {given}  |  Matched: {matched}  |  LB numbers found: {lbs}"
        )

        folders = list(dict.fromkeys(str(Path(p).parent) for p in self._all_paths))
        self.lookup_completed.emit(detail_list, folders)

    def _append_no_checksum_summary_rows(self):
        if not self._no_checksum_folders:
            return
        _bg = QColor("#fff0e0")
        _fg = QColor("#cc4400")
        rows, colors, user_data = [], [], []
        for folder in sorted(self._no_checksum_folders):
            rows.append([
                Path(folder).name, "", "0", "", "", "", "", "",
                "NO CHECKSUMS — Generate?",
            ])
            colors.append(_bg)
            user_data.append({"path": folder, "type": "no_checksums", "fg": _fg})
        self.summary_model.append_rows(rows, colors, user_data)

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
        self.status_label.setText(f"Error: {msg}")

    # ── Grid interactions ─────────────────────────────────────────────────────

    def _on_summary_double_click(self, index):
        row = self.summary_model.get_row(index.row())
        if row:
            lb_str = str(row[0]).replace("LB-", "")
            try:
                lb_num = int(lb_str)
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                webbrowser.open(url)
            except ValueError:
                pass

    def _on_detail_double_click(self, index):
        row = self.detail_model.get_row(index.row())
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
        row = self.detail_model.get_row(index.row())
        if not row:
            return

        menu = QMenu(self)
        copy_chk = QAction("Copy Checksum", self)
        copy_chk.triggered.connect(lambda: QApplication.clipboard().setText(str(row[0])))
        menu.addAction(copy_chk)

        copy_row = QAction("Copy Row", self)
        copy_row.triggered.connect(lambda: QApplication.clipboard().setText("\t".join(str(c) for c in row)))
        menu.addAction(copy_row)

        lb_str = str(row[3]).replace("LB-", "")
        try:
            lb_num = int(lb_str)
            open_web = QAction("Go to Web Page", self)
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
                self.status_label.setText(f"No checksums found for LB-{lb_number}")
                return
            text_lines = []
            for c in checksums:
                if c["chk_type"] == "f":
                    text_lines.append(f"{c['filename']}:{c['checksum']}")
                else:
                    text_lines.append(f"{c['checksum']}  {c['filename']}")
            self._run_lookup("\n".join(text_lines), source=f"LB-{lb_number}")
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
