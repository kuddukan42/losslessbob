import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHeaderView, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMenu, QProgressBar, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

AUDIO_EXTS = {'.flac', '.shn', '.ape', '.wav'}
LB_DETAIL_URL = "http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"

_C_PASS    = QColor("#C8E6C9")
_C_FAIL    = QColor("#FFCDD2")
_C_MISSING = QColor("#FFE0B2")   # orange — files not on disk
_C_NO_LB   = QColor("#FFFF99")   # yellow — no lbdir but LB# known
_C_GREY    = QColor("#E0E0E0")   # grey   — no LB# known

SUMMARY_HEADERS = [
    "Folder", "LB#", "lbdir File", "Mode",
    "Total", "Pass", "Mismatch", "Missing", "Status",
]
DETAIL_HEADERS = [
    "Filename",
    "MD5 Exp.", "MD5 Act.", "MD5",
    "FFP/Shn Exp.", "FFP/Shn Act.", "FFP/Shn",
    "On Disk", "Overall",
]
INFO_FIELDS = [
    ("length",        "Length:"),
    ("expanded_size", "Expanded Size:"),
    ("cdr",           "CDR:"),
    ("wave_problems", "WAVE Problems:"),
    ("fmt",           "Format:"),
    ("ratio",         "Ratio:"),
]


class _LbdirCheckWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            self.progress.emit(0, 0)
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/check",
                json={"folders": self.folders},
                timeout=600,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _LbdirRetrieveWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/retrieve",
                json={"folders": self.folders},
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _LbdirReconcileWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/reconcile",
                json={"folders": self.folders},
                timeout=300,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _LbdirApplyReconcileWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folder, renames):
        super().__init__()
        self.flask_port = flask_port
        self.folder = folder
        self.renames = renames

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/apply_reconcile",
                json={"folder": self.folder, "renames": self.renames},
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _LbdirFindExtraWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/find_extra",
                json={"folders": self.folders},
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _LbdirDeleteExtraWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folder, files):
        super().__init__()
        self.flask_port = flask_port
        self.folder = folder
        self.files = files

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lbdir/delete_extra",
                json={"folder": self.folder, "files": self.files},
                timeout=60,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class ReconcilePreviewDialog(QDialog):
    """
    Shows proposed file renames from reconcile. User selects which to apply.
    Table columns: [checkbox, From (disk), To (lbdir), MD5]
    """

    def __init__(self, folder: str, proposals: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Reconcile Files — {Path(folder).name}")
        self.setMinimumSize(860, 400)
        self._proposals = proposals

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Folder: {folder}"))
        layout.addWidget(QLabel(
            f"{len(proposals)} file(s) found on disk that match missing lbdir entries by MD5:"
        ))

        self._table = QTableWidget(len(proposals), 4)
        self._table.setHorizontalHeaderLabels(["", "Disk Path (from)", "lbdir Path (to)", "MD5"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 28)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        for row, p in enumerate(proposals):
            chk_item = QTableWidgetItem()
            chk_item.setCheckState(Qt.CheckState.Checked)
            chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, chk_item)
            self._table.setItem(row, 1, QTableWidgetItem(p.get("disk_rel", "")))
            self._table.setItem(row, 2, QTableWidgetItem(p.get("lbdir_rel", "")))
            md5 = p.get("md5", "")
            md5_display = (md5[:16] + "…") if len(md5) > 16 else md5
            md5_item = QTableWidgetItem(md5_display)
            md5_item.setToolTip(md5)
            self._table.setItem(row, 3, md5_item)

        self._table.resizeColumnsToContents()
        self._table.setColumnWidth(0, 28)
        layout.addWidget(self._table)

        sel_layout = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._deselect_all)
        sel_layout.addWidget(sel_all_btn)
        sel_layout.addWidget(desel_all_btn)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply Selected")
        apply_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _select_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def get_selected_renames(self) -> list:
        result = []
        for row in range(self._table.rowCount()):
            if self._table.item(row, 0).checkState() == Qt.CheckState.Checked:
                result.append({
                    "from": self._proposals[row]["disk_rel"],
                    "to": self._proposals[row]["lbdir_rel"],
                })
        return result


class ExtraFilesDialog(QDialog):
    """
    Confirmation dialog for deleting files not listed in the lbdir.
    Shows all extra files with checkboxes; user confirms before any deletion occurs.
    """

    def __init__(self, folder: str, extra_files: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Remove Extra Files — {Path(folder).name}")
        self.setMinimumSize(700, 420)
        self._extra_files = extra_files

        layout = QVBoxLayout(self)

        warn = QLabel(
            f"⚠️  The following {len(extra_files)} file(s) are NOT listed in the lbdir "
            f"and will be permanently deleted from disk. This cannot be undone."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #c0392b; font-weight: bold;")
        layout.addWidget(warn)
        layout.addWidget(QLabel(f"Folder: {folder}"))

        self._table = QTableWidget(len(extra_files), 2)
        self._table.setHorizontalHeaderLabels(["", "File (relative path)"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 28)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        for row, rel in enumerate(extra_files):
            chk_item = QTableWidgetItem()
            chk_item.setCheckState(Qt.CheckState.Checked)
            chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, chk_item)
            path_item = QTableWidgetItem(rel)
            path_item.setToolTip(str(Path(folder) / rel))
            self._table.setItem(row, 1, path_item)

        layout.addWidget(self._table)

        sel_layout = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._deselect_all)
        sel_layout.addWidget(sel_all_btn)
        sel_layout.addWidget(desel_all_btn)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        btn_layout = QHBoxLayout()
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("background-color: #c0392b; color: white;")
        delete_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _select_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def get_selected_files(self) -> list:
        return [
            self._extra_files[row]
            for row in range(self._table.rowCount())
            if self._table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]


class DropFolderListWidget(QListWidget):
    folders_dropped = pyqtSignal(list)

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
        folders = []
        seen = set()
        for url in event.mimeData().urls():
            path = url_to_local_path(url)
            folder = str(path if path.is_dir() else path.parent)
            if folder not in seen:
                seen.add(folder)
                folders.append(folder)
        self.folders_dropped.emit(folders)


class LbdirTab(QWidget):
    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._folders: list[str] = []
        self._check_results: list[dict] = []
        self._current_detail_files: list[dict] = []
        self._check_worker = None
        self._retrieve_worker = None
        self._reconcile_worker = None
        self._apply_reconcile_worker = None
        self._find_extra_worker = None
        self._delete_extra_worker = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # ── Left panel ───────────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        self.list_header = QLabel("Folders: 0")
        left_layout.addWidget(self.list_header)

        self.listbox = DropFolderListWidget()
        self.listbox.folders_dropped.connect(self._on_folders_dropped)
        self.listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.listbox.customContextMenuRequested.connect(self._on_listbox_context)
        left_layout.addWidget(self.listbox)

        btn_layout = QVBoxLayout()

        self.add_folders_btn = QPushButton("Add Folders...")
        self.add_folders_btn.clicked.connect(self._on_add_folders)
        btn_layout.addWidget(self.add_folders_btn)

        self.add_root_btn = QPushButton("Add Root Folder...")
        self.add_root_btn.setToolTip(
            "Pick a parent folder and recursively add all subfolders "
            "containing audio files."
        )
        self.add_root_btn.clicked.connect(self._on_add_root_folder)
        btn_layout.addWidget(self.add_root_btn)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._on_remove_selected)
        btn_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Clear List")
        self.clear_btn.clicked.connect(self._on_clear_list)
        btn_layout.addWidget(self.clear_btn)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #cccccc;")
        btn_layout.addWidget(sep)

        self.check_btn = QPushButton("Check lbdir Files")
        self.check_btn.clicked.connect(self._on_check)
        btn_layout.addWidget(self.check_btn)

        self.retrieve_btn = QPushButton("Retrieve lbdir")
        self.retrieve_btn.setToolTip(
            "Pull lbdir*.txt from the local attachment cache (or scrape)\n"
            "for selected folders (or all if none selected), then check.\n"
            "LB number is read from My Collection or parsed from the folder name."
        )
        self.retrieve_btn.clicked.connect(self._on_retrieve)
        btn_layout.addWidget(self.retrieve_btn)

        self.reconcile_btn = QPushButton("Reconcile Files")
        self.reconcile_btn.setToolTip(
            "Find disk files whose MD5 checksum matches a missing lbdir entry.\n"
            "Proposes renames/moves to recreate the lbdir layout.\n"
            "Preview is shown before any files are moved."
        )
        self.reconcile_btn.clicked.connect(self._on_reconcile)
        btn_layout.addWidget(self.reconcile_btn)

        self.remove_extra_btn = QPushButton("Remove Extra Files")
        self.remove_extra_btn.setToolTip(
            "Find files in each folder that are not listed in the lbdir.\n"
            "A confirmation dialog shows which files will be permanently deleted."
        )
        self.remove_extra_btn.clicked.connect(self._on_remove_extra)
        btn_layout.addWidget(self.remove_extra_btn)

        btn_layout.addStretch()

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        btn_layout.addWidget(self.status_label)

        left_layout.addLayout(btn_layout)
        left_widget.setFixedWidth(200)

        # ── Right panel ──────────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        right_layout.addWidget(self.progress_bar)

        v_splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Summary table (top) ──────────────────────────────────────────────
        self.summary_container = QWidget()
        sc_layout = QVBoxLayout(self.summary_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.addWidget(QLabel("Summary"))

        self.summary_table = QTableWidget(0, len(SUMMARY_HEADERS))
        self.summary_table.setHorizontalHeaderLabels(SUMMARY_HEADERS)
        self.summary_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.summary_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setMinimumHeight(120)
        self.summary_table.itemSelectionChanged.connect(self._on_summary_row_clicked)
        self.summary_table.doubleClicked.connect(self._on_summary_double_click)
        sc_layout.addWidget(self.summary_table)
        v_splitter.addWidget(self.summary_container)

        # ── Bottom: horizontal splitter (detail + info) ──────────────────────
        self.detail_container = QWidget()
        dc_main_layout = QVBoxLayout(self.detail_container)
        dc_main_layout.setContentsMargins(0, 0, 0, 0)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Detail table (left half)
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        detail_header_row = QHBoxLayout()
        detail_header_row.addWidget(QLabel("Detail"))
        detail_header_row.addStretch()
        self.show_all_cb = QCheckBox("Show all files")
        self.show_all_cb.setChecked(True)
        self.show_all_cb.stateChanged.connect(self._on_show_all_changed)
        detail_header_row.addWidget(self.show_all_cb)
        detail_layout.addLayout(detail_header_row)

        self.detail_table = QTableWidget(0, len(DETAIL_HEADERS))
        self.detail_table.setHorizontalHeaderLabels(DETAIL_HEADERS)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.itemSelectionChanged.connect(self._on_detail_row_clicked)
        detail_layout.addWidget(self.detail_table)
        h_splitter.addWidget(detail_widget)

        # Info panel (right half)
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(8, 0, 0, 0)
        info_layout.addWidget(QLabel("Track Info (shntool len)"))

        self._info_fields: dict[str, QLabel] = {}
        for key, label_text in INFO_FIELDS:
            row_layout = QHBoxLayout()
            key_lbl = QLabel(label_text)
            key_lbl.setFixedWidth(100)
            val_lbl = QLabel("")
            val_lbl.setWordWrap(True)
            self._info_fields[key] = val_lbl
            row_layout.addWidget(key_lbl)
            row_layout.addWidget(val_lbl, 1)
            info_layout.addLayout(row_layout)

        info_layout.addStretch()
        info_widget.setMinimumWidth(160)
        h_splitter.addWidget(info_widget)
        h_splitter.setSizes([650, 200])

        dc_main_layout.addWidget(h_splitter)
        v_splitter.addWidget(self.detail_container)

        right_layout.addWidget(v_splitter)
        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget, 1)

    # ── Folder management ─────────────────────────────────────────────────────

    def _add_folder(self, path):
        s = str(Path(path).resolve())
        if s not in self._folders and Path(s).is_dir():
            self._folders.append(s)

    def _refresh_listbox(self):
        self.listbox.clear()
        for folder in self._folders:
            item = QListWidgetItem(Path(folder).name)
            item.setToolTip(folder)
            item.setData(Qt.ItemDataRole.UserRole, folder)
            self.listbox.addItem(item)
        self.list_header.setText(f"Folders: {len(self._folders)}")

    def _on_folders_dropped(self, folders):
        for f in folders:
            self._add_folder(f)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_listbox)

    def _on_add_folders(self):
        path = QFileDialog.getExistingDirectory(self, "Add Folder", str(Path.home()))
        if path:
            self._add_folder(path)
            self._refresh_listbox()

    def _on_add_root_folder(self):
        root = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(Path.home()))
        if not root:
            return
        root_path = Path(root)
        added = 0
        for sub in sorted(root_path.rglob("*")):
            if sub.is_dir():
                try:
                    if any(f.suffix.lower() in AUDIO_EXTS for f in sub.iterdir() if f.is_file()):
                        before = len(self._folders)
                        self._add_folder(str(sub))
                        if len(self._folders) > before:
                            added += 1
                except PermissionError:
                    pass
        self._refresh_listbox()
        self.status_label.setText(f"Added {added} subfolder(s) with audio files.")

    def _on_remove_selected(self):
        for item in self.listbox.selectedItems():
            folder = item.data(Qt.ItemDataRole.UserRole)
            if folder in self._folders:
                self._folders.remove(folder)
        self._refresh_listbox()

    def _on_clear_list(self):
        self._folders.clear()
        self._check_results.clear()
        self._current_detail_files.clear()
        self._refresh_listbox()
        self.summary_table.setRowCount(0)
        self.detail_table.setRowCount(0)
        self._clear_info_panel()
        self.status_label.setText("")

    def _on_listbox_context(self, pos):
        menu = QMenu(self)
        remove_act = QAction("Remove from List", self)
        remove_act.triggered.connect(self._on_remove_selected)
        menu.addAction(remove_act)
        clear_act = QAction("Clear List", self)
        clear_act.triggered.connect(self._on_clear_list)
        menu.addAction(clear_act)
        menu.exec(self.listbox.mapToGlobal(pos))

    # ── Button state helpers ──────────────────────────────────────────────────

    _ALL_BTNS = (
        "add_folders_btn", "add_root_btn", "remove_btn",
        "clear_btn", "check_btn", "retrieve_btn", "reconcile_btn", "remove_extra_btn",
    )

    def _set_buttons_enabled(self, enabled):
        for name in self._ALL_BTNS:
            getattr(self, name).setEnabled(enabled)

    def _show_progress(self, visible):
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

    # ── Check ─────────────────────────────────────────────────────────────────

    def _on_check(self):
        if not self._folders:
            self.status_label.setText("No folders in list.")
            return
        self._start_check(list(self._folders))

    def _start_check(self, folders):
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.detail_table.setRowCount(0)
        self._current_detail_files.clear()
        self._clear_info_panel()
        self.status_label.setText(f"Checking {len(folders)} folder(s)...")
        self._check_worker = _LbdirCheckWorker(self.flask_port, folders)
        self._check_worker.finished.connect(self._on_check_done)
        self._check_worker.error.connect(self._on_worker_error)
        self._check_worker.start()

    def _on_check_done(self, response):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        if "error" in response:
            self.status_label.setText(f"Error: {response['error']}")
            return
        results = response.get("results", [])
        self._check_results = results
        self._populate_summary(results)
        n_pass = sum(
            1 for r in results
            if r.get("lbdir_found") and r.get("status") == "pass"
        )
        n_issue = len(results) - n_pass
        msg = f"Checked {len(results)} folder(s): {n_pass} pass, {n_issue} with issues."
        if any(r.get("status") == "shntool_missing" for r in results):
            msg += "\nshntool not found — install with: sudo apt install shntool"
        self.status_label.setText(msg)

    # ── Retrieve ─────────────────────────────────────────────────────────────

    def _on_retrieve(self):
        selected = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.listbox.selectedItems()
        ]
        folders = selected if selected else list(self._folders)
        if not folders:
            self.status_label.setText("No folders in list.")
            return
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Retrieving lbdir files for {len(folders)} folder(s)...")
        self._retrieve_worker = _LbdirRetrieveWorker(self.flask_port, folders)
        self._retrieve_worker.finished.connect(self._on_retrieve_done)
        self._retrieve_worker.error.connect(self._on_worker_error)
        self._retrieve_worker.start()

    def _on_retrieve_done(self, response):
        self._show_progress(False)
        results = response.get("results", [])
        from_cache = [r for r in results if r.get("status") == "copied"]
        scraped = [r for r in results if r.get("status") == "scraped_and_copied"]
        not_found = [r for r in results if r.get("status") == "not_found"]
        no_lb = [r for r in results if r.get("status") == "no_lb_number"]
        parts = []
        if from_cache:
            parts.append(f"{len(from_cache)} retrieved from local cache")
        if scraped:
            parts.append(f"{len(scraped)} retrieved via scrape")
        if not_found:
            parts.append(f"{len(not_found)} not found in cache")
        if no_lb:
            parts.append(
                f"{len(no_lb)} folder(s) skipped — no LB number found, run Lookup first"
            )
        self.status_label.setText("  |  ".join(parts) if parts else "Done.")
        self._start_check(list(self._folders))

    def _on_worker_error(self, msg):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        self.status_label.setText(f"Error: {msg}")

    # ── Reconcile ─────────────────────────────────────────────────────────────

    def _get_selected_or_all_folders(self) -> list:
        selected = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.listbox.selectedItems()
        ]
        return selected if selected else list(self._folders)

    def _on_reconcile(self):
        folders = self._get_selected_or_all_folders()
        if not folders:
            self.status_label.setText("No folders. Add folders and run Check lbdir Files first.")
            return
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Scanning {len(folders)} folder(s) for reconcilable files...")
        self._reconcile_worker = _LbdirReconcileWorker(self.flask_port, folders)
        self._reconcile_worker.finished.connect(self._on_reconcile_done)
        self._reconcile_worker.error.connect(self._on_worker_error)
        self._reconcile_worker.start()

    def _on_reconcile_done(self, response: dict):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        if "error" in response:
            self.status_label.setText(f"Error: {response['error']}")
            return
        results = response.get("results", [])
        all_proposals = [
            (r["folder"], r["proposals"])
            for r in results
            if r.get("proposals")
        ]
        if not all_proposals:
            self.status_label.setText(
                "No reconcilable files found — no checksum matches for missing files."
            )
            return
        total = sum(len(p) for _, p in all_proposals)
        self.status_label.setText(f"Found {total} reconcilable file(s). Showing preview...")
        for folder, proposals in all_proposals:
            dlg = ReconcilePreviewDialog(folder, proposals, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                selected = dlg.get_selected_renames()
                if selected:
                    self._apply_reconcile(folder, selected)

    def _apply_reconcile(self, folder: str, renames: list):
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Applying {len(renames)} rename(s)...")
        self._apply_reconcile_worker = _LbdirApplyReconcileWorker(
            self.flask_port, folder, renames
        )
        self._apply_reconcile_worker.finished.connect(self._on_apply_reconcile_done)
        self._apply_reconcile_worker.error.connect(self._on_worker_error)
        self._apply_reconcile_worker.start()

    def _on_apply_reconcile_done(self, response: dict):
        self._show_progress(False)
        applied = response.get("applied", 0)
        errors = response.get("errors", [])
        msg = f"Applied {applied} rename(s)."
        if errors:
            msg += f" {len(errors)} error(s): {errors[0]['error']}"
        self.status_label.setText(msg)
        self._start_check(list(self._folders))

    # ── Remove extra files ────────────────────────────────────────────────────

    def _on_remove_extra(self):
        folders = self._get_selected_or_all_folders()
        if not folders:
            self.status_label.setText("No folders. Add folders first.")
            return
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Scanning {len(folders)} folder(s) for extra files...")
        self._find_extra_worker = _LbdirFindExtraWorker(self.flask_port, folders)
        self._find_extra_worker.finished.connect(self._on_find_extra_done)
        self._find_extra_worker.error.connect(self._on_worker_error)
        self._find_extra_worker.start()

    def _on_find_extra_done(self, response: dict):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        if "error" in response:
            self.status_label.setText(f"Error: {response['error']}")
            return
        results = response.get("results", [])
        folders_with_extra = [
            (r["folder"], r["extra"])
            for r in results
            if r.get("extra")
        ]
        errors = [r for r in results if "error" in r]
        if errors:
            self.status_label.setText(
                f"Error in {len(errors)} folder(s): {errors[0]['error']}"
            )
        if not folders_with_extra:
            self.status_label.setText("No extra files found — all disk files are listed in the lbdir.")
            return
        total = sum(len(f) for _, f in folders_with_extra)
        self.status_label.setText(f"Found {total} extra file(s). Showing confirmation...")
        for folder, extra_files in folders_with_extra:
            dlg = ExtraFilesDialog(folder, extra_files, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                selected = dlg.get_selected_files()
                if selected:
                    self._delete_extra(folder, selected)

    def _delete_extra(self, folder: str, files: list):
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Deleting {len(files)} file(s)...")
        self._delete_extra_worker = _LbdirDeleteExtraWorker(self.flask_port, folder, files)
        self._delete_extra_worker.finished.connect(self._on_delete_extra_done)
        self._delete_extra_worker.error.connect(self._on_worker_error)
        self._delete_extra_worker.start()

    def _on_delete_extra_done(self, response: dict):
        self._show_progress(False)
        deleted = response.get("deleted", 0)
        removed_dirs = response.get("removed_dirs", [])
        errors = response.get("errors", [])
        msg = f"Deleted {deleted} file(s)."
        if removed_dirs:
            msg += f" Removed {len(removed_dirs)} empty folder(s)."
        if errors:
            msg += f" {len(errors)} error(s): {errors[0]['error']}"
        self.status_label.setText(msg)
        self._start_check(list(self._folders))

    # ── Summary table ─────────────────────────────────────────────────────────

    @staticmethod
    def _result_display_status(result):
        if not result.get("lbdir_found"):
            if result.get("lb_number") is not None:
                return "NO LBDIR", _C_NO_LB
            return "NO LB#", _C_GREY
        if "error" in result:
            return "PARSE ERROR", _C_FAIL
        status = result.get("status", "")
        if status == "pass":
            return "PASS", _C_PASS
        if result.get("missing", 0) > 0 and result.get("mismatch", 0) == 0:
            return "MISSING FILES", _C_FAIL
        if status == "shntool_missing":
            return "SHNTOOL MISSING", _C_FAIL
        return "FAIL", _C_FAIL

    def _populate_summary(self, results):
        self.summary_table.setRowCount(0)
        for result in results:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)

            folder = result.get("folder", "")
            lb_number = result.get("lb_number")
            lbdir_path = result.get("lbdir_path")
            mode = result.get("mode", "")
            found = result.get("lbdir_found", False)
            status_text, color = self._result_display_status(result)

            lbdir_file = Path(lbdir_path).name if lbdir_path else "NOT FOUND"
            lb_str = str(lb_number) if lb_number is not None else ""

            def _n(key):
                return str(result.get(key, "")) if found and "error" not in result else ""

            cells = [
                Path(folder).name,
                lb_str,
                lbdir_file,
                mode.upper() if mode else "",
                _n("total"), _n("pass"), _n("mismatch"), _n("missing"),
                status_text,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col == 0:
                    item.setToolTip(folder)
                    item.setData(Qt.ItemDataRole.UserRole, lb_number)
                if col >= 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.summary_table.setItem(row, col, item)

        self.summary_table.resizeColumnsToContents()

    def _on_summary_row_clicked(self):
        row = self.summary_table.currentRow()
        if row < 0 or row >= len(self._check_results):
            self.detail_table.setRowCount(0)
            self._current_detail_files.clear()
            self._clear_info_panel()
            return
        files = self._check_results[row].get("files", [])
        self._current_detail_files = files
        self._populate_detail(files)
        self._clear_info_panel()

    def _on_summary_double_click(self, index):
        row = index.row()
        if row < 0 or row >= len(self._check_results):
            return
        item = self.summary_table.item(row, 0)
        if item is None:
            return
        lb_number = item.data(Qt.ItemDataRole.UserRole)
        if lb_number is not None:
            webbrowser.open(LB_DETAIL_URL.format(lb=lb_number))

    # ── Detail table ──────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_hash(h):
        if not h:
            return ""
        return (h[:12] + "…") if len(h) > 12 else h

    @staticmethod
    def _fmt_status(s):
        return {
            "pass": "PASS", "fail": "FAIL", "missing": "MISSING", "na": "N/A",
        }.get(s or "na", (s or "").upper() or "N/A")

    def _on_show_all_changed(self):
        self._populate_detail(self._current_detail_files)

    def _populate_detail(self, files):
        show_all = self.show_all_cb.isChecked()
        self.detail_table.setRowCount(0)

        for file_idx, file_info in enumerate(files):
            overall = file_info.get("overall", "")
            if not show_all and overall == "pass":
                continue

            if overall == "pass":
                color = _C_PASS
            elif overall == "fail":
                color = _C_FAIL
            elif overall == "missing":
                color = _C_MISSING
            else:
                color = _C_GREY

            ffp_st = file_info.get("ffp_status", "na")
            shn_st = file_info.get("shntool_status", "na")
            ffp_exp = file_info.get("ffp_expected") or file_info.get("shntool_expected") or ""
            ffp_act = file_info.get("ffp_actual") or file_info.get("shntool_actual") or ""
            ffp_shn_st = ffp_st if ffp_st != "na" else shn_st

            md5_exp = file_info.get("md5_expected") or ""
            md5_act = file_info.get("md5_actual") or ""

            # (display_text, full_tooltip_or_None)
            cells = [
                (file_info.get("filename", ""), None),
                (self._fmt_hash(md5_exp), md5_exp or None),
                (self._fmt_hash(md5_act), md5_act or None),
                (self._fmt_status(file_info.get("md5_status")), None),
                (self._fmt_hash(ffp_exp), ffp_exp or None),
                (self._fmt_hash(ffp_act), ffp_act or None),
                (self._fmt_status(ffp_shn_st), None),
                ("Yes" if file_info.get("on_disk") else "No", None),
                (overall.upper() if overall else "", None),
            ]
            row = self.detail_table.rowCount()
            self.detail_table.insertRow(row)
            for col, (text, tooltip) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, file_idx)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if tooltip:
                    item.setToolTip(tooltip)
                self.detail_table.setItem(row, col, item)

        self.detail_table.resizeColumnsToContents()

    # ── Info panel ────────────────────────────────────────────────────────────

    def _clear_info_panel(self):
        for lbl in self._info_fields.values():
            lbl.setText("")

    def _populate_info_panel(self, file_info):
        if not file_info.get("length"):
            self._clear_info_panel()
            return
        exp_size = file_info.get("expanded_size", "")
        self._info_fields["length"].setText(file_info.get("length") or "")
        self._info_fields["expanded_size"].setText(f"{exp_size} B" if exp_size else "")
        self._info_fields["cdr"].setText(file_info.get("cdr") or "")
        self._info_fields["wave_problems"].setText(file_info.get("wave_problems") or "")
        self._info_fields["fmt"].setText(file_info.get("fmt") or "")
        self._info_fields["ratio"].setText(file_info.get("ratio") or "")

    def _on_detail_row_clicked(self):
        row = self.detail_table.currentRow()
        if row < 0:
            self._clear_info_panel()
            return
        item = self.detail_table.item(row, 0)
        if item is None:
            self._clear_info_panel()
            return
        file_idx = item.data(Qt.ItemDataRole.UserRole)
        if file_idx is None or file_idx >= len(self._current_detail_files):
            self._clear_info_panel()
            return
        self._populate_info_panel(self._current_detail_files[file_idx])

    def resize_columns_to_font(self) -> None:
        self.summary_table.resizeColumnsToContents()
        self.detail_table.resizeColumnsToContents()
