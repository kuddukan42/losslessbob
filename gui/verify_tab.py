from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QHeaderView, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMenu, QProgressBar, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

AUDIO_EXTS = {'.flac', '.shn', '.ape', '.wav'}

_C_PASS         = QColor("#C8E6C9")
_C_FAIL         = QColor("#FFCDD2")
_C_MISSING      = QColor("#FFE0B2")   # orange — files not on disk
_C_INCOMPLETE   = QColor("#FFFF99")   # yellow — missing checksum type
_C_EXTRA        = QColor("#FFFF99")   # yellow — on disk, no checksum
_C_GREY         = QColor("#E0E0E0")   # grey   — N/A
_C_NO_CHECKSUMS = QColor("#FFFF99")   # yellow — audio present but no checksum files

SUMMARY_HEADERS = [
    "Folder", "Mode", "FFP", "MD5", "Shntool",
    "Total", "Pass", "Mismatch", "Missing", "Extra", "Status",
]
DETAIL_HEADERS = ["Filename", "MD5", "FFP/Shntool", "ST5", "On Disk", "Overall"]


class _VerifyWorker(QThread):
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
                f"http://127.0.0.1:{self.flask_port}/api/verify",
                json={"folders": self.folders},
                timeout=600,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _GenerateWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, flask_port, folders):
        super().__init__()
        self.flask_port = flask_port
        self.folders = list(folders)

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/verify/generate",
                json={"folders": self.folders},
                timeout=600,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _RetrieveWorker(QThread):
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


class VerifyTab(QWidget):
    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._folders: list[str] = []
        self._verify_results: list[dict] = []
        self._worker = None
        self._generate_worker = None
        self._retrieve_worker = None
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
            "that contain audio files."
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

        self.verify_btn = QPushButton("Verify Folders")
        self.verify_btn.clicked.connect(self._on_verify)
        btn_layout.addWidget(self.verify_btn)

        self.generate_btn = QPushButton("Generate Checksums")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)

        self.retrieve_btn = QPushButton("Retrieve from LB")
        self.retrieve_btn.setToolTip(
            "Copy lbdir*.txt from the local attachment cache to each folder,\n"
            "scraping from losslessbob.com if not yet cached.\n"
            "LB number is read from My Collection or parsed from the folder name."
        )
        self.retrieve_btn.clicked.connect(self._on_retrieve)
        btn_layout.addWidget(self.retrieve_btn)

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

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Summary table
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
        sc_layout.addWidget(self.summary_table)
        splitter.addWidget(self.summary_container)

        # Detail table
        self.detail_container = QWidget()
        dc_layout = QVBoxLayout(self.detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)

        detail_header_row = QHBoxLayout()
        detail_header_row.addWidget(QLabel("Detail"))
        detail_header_row.addStretch()
        self.show_all_cb = QCheckBox("Show all files")
        self.show_all_cb.setChecked(True)
        self.show_all_cb.stateChanged.connect(self._on_show_all_changed)
        detail_header_row.addWidget(self.show_all_cb)
        dc_layout.addLayout(detail_header_row)

        self.detail_table = QTableWidget(0, len(DETAIL_HEADERS))
        self.detail_table.setHorizontalHeaderLabels(DETAIL_HEADERS)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.detail_table.verticalHeader().setVisible(False)
        dc_layout.addWidget(self.detail_table)
        splitter.addWidget(self.detail_container)

        right_layout.addWidget(splitter)
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
        self._verify_results.clear()
        self._refresh_listbox()
        self.summary_table.setRowCount(0)
        self.detail_table.setRowCount(0)
        self.status_label.setText("")

    def add_folders_from_lookup(self, folders: list[str]) -> None:
        """Pre-populate folder list from the Lookup tab (only if list is currently empty)."""
        if self._folders:
            return
        for f in folders:
            self._add_folder(f)
        if self._folders:
            self._refresh_listbox()

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
        "clear_btn", "verify_btn", "generate_btn", "retrieve_btn",
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

    # ── Verify ────────────────────────────────────────────────────────────────

    def _on_verify(self):
        if not self._folders:
            self.status_label.setText("No folders in list.")
            return
        self._start_verify(list(self._folders))

    def _start_verify(self, folders):
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.detail_table.setRowCount(0)
        self.status_label.setText(f"Verifying {len(folders)} folder(s)...")
        self._worker = _VerifyWorker(self.flask_port, folders)
        self._worker.finished.connect(self._on_verify_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_verify_done(self, response):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        if "error" in response:
            self.status_label.setText(f"Error: {response['error']}")
            return
        results = response.get("results", [])
        self._verify_results = results
        self._populate_summary(results)
        n_pass = sum(1 for r in results if r.get("status") == "pass")
        n_issue = len(results) - n_pass
        msg = f"Verified {len(results)} folder(s): {n_pass} pass, {n_issue} with issues."
        if any(r.get("status") == "shntool_missing" for r in results):
            import sys as _sys
            if _sys.platform == "win32":
                msg += (
                    "\nshntool not found on Windows. Options:\n"
                    "  1. Install WSL: wsl --install (then: wsl sudo apt install shntool)\n"
                    "  2. SHN MD5 checksums can still be verified; "
                    "only shntool hashes require it."
                )
            else:
                msg += "\nshntool not found — install with: sudo apt install shntool"
        self.status_label.setText(msg)

    # ── Generate ─────────────────────────────────────────────────────────────

    def _on_generate(self):
        if not self._folders:
            self.status_label.setText("No folders in list.")
            return
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Generating checksums for {len(self._folders)} folder(s)...")
        self._generate_worker = _GenerateWorker(self.flask_port, list(self._folders))
        self._generate_worker.finished.connect(self._on_generate_done)
        self._generate_worker.error.connect(self._on_worker_error)
        self._generate_worker.start()

    def _on_generate_done(self, response):
        self._show_progress(False)
        all_generated, all_errors = [], []
        for result in response.get("results", []):
            all_generated.extend(result.get("generated", []))
            all_errors.extend(result.get("errors", []))
        parts = []
        if all_generated:
            parts.append(f"Generated: {', '.join(Path(p).name for p in all_generated)}")
        if all_errors:
            parts.append(f"Errors: {'; '.join(all_errors)}")
        self.status_label.setText("  |  ".join(parts) if parts else "No files generated.")
        self._start_verify(list(self._folders))

    # ── Retrieve ─────────────────────────────────────────────────────────────

    def _on_retrieve(self):
        if not self._folders:
            self.status_label.setText("No folders in list.")
            return
        self._set_buttons_enabled(False)
        self._show_progress(True)
        self.status_label.setText(f"Retrieving lbdir files for {len(self._folders)} folder(s)...")
        self._retrieve_worker = _RetrieveWorker(self.flask_port, list(self._folders))
        self._retrieve_worker.finished.connect(self._on_retrieve_done)
        self._retrieve_worker.error.connect(self._on_worker_error)
        self._retrieve_worker.start()

    def _on_retrieve_done(self, response):
        self._show_progress(False)
        results = response.get("results", [])
        copied = [r for r in results if r.get("status") in ("copied", "scraped_and_copied")]
        not_found = [r for r in results if r.get("status") == "not_found"]
        no_lb = [r for r in results if r.get("status") == "no_lb_number"]
        parts = []
        if copied:
            parts.append(f"Retrieved {len(copied)} lbdir file(s)")
        if not_found:
            parts.append(f"{len(not_found)} not found in cache")
        if no_lb:
            parts.append(
                f"{len(no_lb)} folder(s) skipped — no LB number found, run Lookup first"
            )
        self.status_label.setText("  |  ".join(parts) if parts else "Done.")
        if copied:
            # Only auto-trigger verify when at least one lbdir was actually retrieved
            self._start_verify(list(self._folders))
        else:
            self._set_buttons_enabled(True)

    def _on_worker_error(self, msg):
        self._show_progress(False)
        self._set_buttons_enabled(True)
        self.status_label.setText(f"Error: {msg}")

    # ── Summary table ─────────────────────────────────────────────────────────

    @staticmethod
    def _summary_row_color(result):
        status = result.get("status", "")
        if status == "no_checksums":
            return _C_NO_CHECKSUMS
        if status == "pass":
            return _C_PASS
        if status in ("incomplete", "shntool_missing"):
            return _C_INCOMPLETE
        if result.get("missing", 0) > 0 and result.get("mismatch", 0) == 0:
            return _C_MISSING
        return _C_FAIL

    def _populate_summary(self, results):
        self.summary_table.setRowCount(0)
        for result in results:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)

            color = self._summary_row_color(result)
            folder = result.get("folder", "")
            mode = result.get("mode", "flac")
            files = result.get("files", [])

            has_ffp = any(f.get("ffp_expected") is not None for f in files)
            has_md5 = any(f.get("md5_expected") is not None for f in files)
            has_shn = any(f.get("shntool_expected") is not None for f in files)

            if mode in ("flac", "mixed"):
                ffp_sym = "✓" if has_ffp else "✗"
            else:
                ffp_sym = "—"
            md5_sym = "✓" if has_md5 else "✗"
            if mode in ("shn", "mixed"):
                shn_sym = "✓" if has_shn else "✗"
            else:
                shn_sym = "—"

            status_labels = {
                "pass": "PASS", "fail": "FAIL",
                "incomplete": "INCOMPLETE", "shntool_missing": "SHNTOOL MISSING",
                "no_checksums": "NO CHECKSUMS",
            }
            status_text = status_labels.get(result.get("status", ""),
                                            result.get("status", "").upper())

            cells = [
                Path(folder).name,
                mode.upper(),
                ffp_sym, md5_sym, shn_sym,
                str(result.get("total", 0)),
                str(result.get("pass", 0)),
                str(result.get("mismatch", 0)),
                str(result.get("missing", 0)),
                str(result.get("extra", 0)),
                status_text,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col == 0:
                    item.setToolTip(folder)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.summary_table.setItem(row, col, item)

        self.summary_table.resizeColumnsToContents()

    # ── Detail table ──────────────────────────────────────────────────────────

    def _on_summary_row_clicked(self):
        row = self.summary_table.currentRow()
        if row < 0 or row >= len(self._verify_results):
            self.detail_table.setRowCount(0)
            return
        self._populate_detail(self._verify_results[row].get("files", []))

    def _on_show_all_changed(self):
        row = self.summary_table.currentRow()
        if row < 0 or row >= len(self._verify_results):
            return
        self._populate_detail(self._verify_results[row].get("files", []))

    @staticmethod
    def _fmt_status(s):
        return {"pass": "PASS", "fail": "FAIL", "missing": "MISSING", "na": "N/A"}.get(
            s or "na", (s or "").upper() or "N/A"
        )

    def _populate_detail(self, files):
        show_all = self.show_all_cb.isChecked()
        self.detail_table.setRowCount(0)

        for file_info in files:
            overall = file_info.get("overall", "")
            if not show_all and overall == "pass":
                continue

            if overall == "pass":
                color = _C_PASS
            elif overall == "fail":
                color = _C_FAIL
            elif overall == "missing":
                color = _C_MISSING
            elif overall == "extra":
                color = _C_EXTRA
            else:
                color = _C_GREY

            ffp_st = file_info.get("ffp_status", "na")
            shn_st = file_info.get("shntool_status", "na")
            ffp_shn = ffp_st if ffp_st != "na" else shn_st

            cells = [
                file_info.get("filename", ""),
                self._fmt_status(file_info.get("md5_status")),
                self._fmt_status(ffp_shn),
                self._fmt_status(file_info.get("st5_status")),
                "Yes" if file_info.get("on_disk") else "No",
                overall.upper() if overall else "",
            ]
            row = self.detail_table.rowCount()
            self.detail_table.insertRow(row)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.detail_table.setItem(row, col, item)

        self.detail_table.resizeColumnsToContents()

    def resize_columns_to_font(self) -> None:
        self.summary_table.resizeColumnsToContents()
        self.detail_table.resizeColumnsToContents()
