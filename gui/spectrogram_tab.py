"""
SpectrogramTab: generate and review per-file spectrograms, plus acoustic fingerprinting.
Inner tabs:
  "Spectrograms"   — existing folder/track/viewer workflow
  "Fingerprinting" — build fingerprint DB, identify unknown files, find duplicate recordings
"""
import csv
import io
import requests
from pathlib import Path

import gui.styles as styles

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent, QPointF
from PyQt6.QtGui import QPixmap, QAction, QWheelEvent
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QPushButton, QLabel, QScrollArea, QProgressBar,
    QFileDialog, QMenu, QCheckBox, QSpinBox, QGroupBox,
    QSizePolicy, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView,
)


# ── Drag-and-drop folder list ─────────────────────────────────────────────────

class _DropFolderList(QListWidget):
    folders_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        event.acceptProposedAction()
        from gui.platform_utils import url_to_local_path
        folders, seen = [], set()
        for url in event.mimeData().urls():
            p    = url_to_local_path(url)
            path = str(p if p.is_dir() else p.parent)
            if path not in seen:
                seen.add(path)
                folders.append(path)
        if folders:
            self.folders_dropped.emit(folders)


# ── Zoomable image viewer ─────────────────────────────────────────────────────

class _ImageViewer(QScrollArea):
    """Scroll area that shows a spectrogram PNG with zoom/pan support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap:       QPixmap | None  = None
        self._scale:        float           = 1.0
        self._fit_mode:     bool            = True
        self._panning:      bool            = False
        self._pan_start:    QPointF | None  = None
        self._pan_remainder: QPointF        = QPointF(0.0, 0.0)

        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setWidgetResizable(False)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._label.installEventFilter(self)
        self.setWidget(self._label)

    def eventFilter(self, obj, event):
        if obj is self._label and self._pixmap:
            t = event.type()
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._panning = True
                self._pan_start = event.globalPosition()
                self._pan_remainder = QPointF(0.0, 0.0)
                self._label.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            elif t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._panning = False
                self._pan_start = None
                self._label.setCursor(
                    Qt.CursorShape.ArrowCursor if self._fit_mode
                    else Qt.CursorShape.OpenHandCursor
                )
                return True
            elif t == QEvent.Type.MouseMove and self._panning and self._pan_start is not None:
                delta = event.globalPosition() - self._pan_start
                self._pan_start = event.globalPosition()
                rx = delta.x() + self._pan_remainder.x()
                ry = delta.y() + self._pan_remainder.y()
                dx, dy = int(rx), int(ry)
                self._pan_remainder = QPointF(rx - dx, ry - dy)
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - dx
                )
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - dy
                )
                return True
            elif t == QEvent.Type.MouseButtonDblClick:
                self._fit_width()
                return True
        return super().eventFilter(obj, event)

    def load(self, png_path: str) -> bool:
        pix = QPixmap(png_path)
        if pix.isNull():
            self._label.setText("Could not load image.")
            self._pixmap = None
            self._label.setCursor(Qt.CursorShape.ArrowCursor)
            return False
        self._pixmap   = pix
        self._fit_mode = True
        self._fit_width()
        return True

    def clear_image(self):
        self._pixmap    = None
        self._fit_mode  = True
        self._panning   = False
        self._pan_start = None
        self._label.clear()
        self._label.setText("")
        self._label.setCursor(Qt.CursorShape.ArrowCursor)

    def zoom_in(self):
        self._fit_mode = False
        self._set_scale(self._scale * 1.25)

    def zoom_out(self):
        self._fit_mode = False
        self._set_scale(self._scale * 0.80)

    def _fit_width(self):
        if not self._pixmap:
            return
        self._fit_mode = True
        vw = self.viewport().width() - 4
        ratio = vw / max(1, self._pixmap.width())
        self._scale = ratio
        self._apply_scale()
        self._label.setCursor(Qt.CursorShape.ArrowCursor)

    def _set_scale(self, scale: float):
        self._scale = max(0.05, min(scale, 8.0))
        self._apply_scale()
        self._label.setCursor(Qt.CursorShape.OpenHandCursor)

    def _apply_scale(self):
        if not self._pixmap:
            return
        w = int(self._pixmap.width()  * self._scale)
        h = int(self._pixmap.height() * self._scale)
        self._label.setPixmap(
            self._pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        )
        self._label.resize(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._pixmap:
            self._fit_width()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)


# ── Generic worker thread ─────────────────────────────────────────────────────

class _Worker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


# ── Fingerprint identify worker ───────────────────────────────────────────────

class _FpIdentifyWorker(QThread):
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, port: int, file_path: str):
        super().__init__()
        self._port      = port
        self._file_path = file_path

    def run(self):
        try:
            r = requests.post(
                f"http://127.0.0.1:{self._port}/api/fingerprint/identify",
                json={"file_path": self._file_path},
                timeout=120,
            ).json()
            if isinstance(r, list):
                self.finished.emit(r)
            else:
                self.error.emit(r.get("error", "Unknown error"))
        except Exception as e:
            self.error.emit(str(e))


# ── Background status-poll threads ───────────────────────────────────────────

class _FpBuildStatusThread(QThread):
    """Polls /api/fingerprint/build/status (+ /queue) every 800 ms."""
    status_update = pyqtSignal(dict)

    def __init__(self, port: int) -> None:
        super().__init__()
        self._port = port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                status = requests.get(
                    f"http://127.0.0.1:{self._port}/api/fingerprint/build/status",
                    timeout=5,
                ).json()
                try:
                    queue = requests.get(
                        f"http://127.0.0.1:{self._port}/api/fingerprint/build/queue",
                        timeout=5,
                    ).json()
                    status["queue_preview"] = queue.get("preview", [])
                    status["queue_pending"] = queue.get("pending", 0)
                except Exception:
                    pass
                self.status_update.emit(status)
            except Exception:
                pass
            self.msleep(800)

    def stop(self) -> None:
        self._running = False


class _FpDupStatusThread(QThread):
    """Polls /api/fingerprint/duplicates every 800 ms in a background thread."""
    status_update = pyqtSignal(dict)

    def __init__(self, port: int) -> None:
        super().__init__()
        self._port = port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self._port}/api/fingerprint/duplicates",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(800)

    def stop(self) -> None:
        self._running = False


# ── File-drop label ───────────────────────────────────────────────────────────

class _FileDrop(QLabel):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Drop an audio file here\nor click Browse…")
        self.setStyleSheet(
            f"border: 2px dashed {styles.FG_MUTED.name()}; border-radius: 6px; "
            f"padding: 16px; color: {styles.FG_MUTED.name()};"
        )
        self.setMinimumHeight(70)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        event.acceptProposedAction()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.setText(Path(path).name)
                self.file_dropped.emit(path)
                break


# ── Main tab ──────────────────────────────────────────────────────────────────

class SpectrogramTab(QWidget):

    def __init__(self, flask_port: int, parent=None):
        super().__init__(parent)
        self.flask_port    = flask_port
        self._folders:     list[str] = []
        self._inventory:   dict      = {}
        self._workers:     list      = []
        self._poll_timer:  QTimer | None = None
        self._current_png: str = ""
        # Fingerprint poll threads / workers
        self._fp_build_thread: _FpBuildStatusThread | None = None
        self._fp_dup_thread:   _FpDupStatusThread   | None = None
        self._fp_id_worker:    _FpIdentifyWorker     | None = None
        self._fp_dup_results: list[dict] = []
        self._build_ui()

    # ── Top-level UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.inner_tabs = QTabWidget()
        outer.addWidget(self.inner_tabs)
        self.inner_tabs.addTab(self._build_spectro_panel(), self.tr("Spectrograms"))
        self.inner_tabs.addTab(self._build_fingerprint_panel(), self.tr("Fingerprinting"))

    # ── Spectrograms panel (extracted from original _build_ui) ────────────────

    def _build_spectro_panel(self) -> QWidget:
        container = QWidget()
        main = QHBoxLayout(container)
        main.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)

        folder_label = QLabel(self.tr("Folders"))
        ll.addWidget(folder_label)
        self.folder_list = _DropFolderList()
        self.folder_list.folders_dropped.connect(self._on_folders_dropped)
        ll.addWidget(self.folder_list)

        folder_btns = QHBoxLayout()
        add_folder_btn = QPushButton(self.tr("Add Folder…"))
        add_folder_btn.clicked.connect(self._on_add_folder)
        folder_btns.addWidget(add_folder_btn)
        clear_btn = QPushButton(self.tr("Clear"))
        clear_btn.clicked.connect(self._on_clear_folders)
        folder_btns.addWidget(clear_btn)
        ll.addLayout(folder_btns)

        track_label = QLabel(self.tr("Tracks"))
        ll.addWidget(track_label)
        self.track_list = QListWidget()
        self.track_list.currentItemChanged.connect(self._on_track_selected)
        ll.addWidget(self.track_list)

        opts_group = QGroupBox(self.tr("Options"))
        opts_layout = QVBoxLayout(opts_group)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel(self.tr("Image width (px):")))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(300, 9000)
        self.width_spin.setValue(1500)
        self.width_spin.setSingleStep(300)
        self.width_spin.setToolTip(self.tr(
            "PNG width in pixels (time axis). Each file is one song (5–10 min).\n"
            "1500px → ~2.5–5px/sec  |  3000px → ~5–10px/sec (more detail)\n"
            "Wider = more time detail, more disk space, slower generation."
        ))
        width_row.addWidget(self.width_spin)
        opts_layout.addLayout(width_row)

        dyn_row = QHBoxLayout()
        dyn_row.addWidget(QLabel(self.tr("Dynamic range (dB):")))
        self.dyn_spin = QSpinBox()
        self.dyn_spin.setRange(20, 180)
        self.dyn_spin.setValue(120)
        self.dyn_spin.setToolTip(self.tr(
            "Colour scale range in dB. 120 is standard for lossless.\n"
            "Lossy artifacts (noise floor plateaus, spectral cutoffs) \n"
            "are most visible at 120dB."
        ))
        dyn_row.addWidget(self.dyn_spin)
        opts_layout.addLayout(dyn_row)

        self.force_cb = QCheckBox(self.tr("Regenerate existing spectrograms"))
        self.force_cb.setToolTip(self.tr(
            "Re-run SoX even if a PNG already exists for this file.\n"
            "Uncheck to skip already-generated files (faster for large batches)."
        ))
        opts_layout.addWidget(self.force_cb)

        ll.addWidget(opts_group)

        self.generate_btn = QPushButton(self.tr("Generate Spectrograms"))
        self.generate_btn.setToolTip(self.tr(
            "Run SoX on all audio files in all listed folders.\n"
            "PNGs are saved to <folder>/spectrograms/<trackname>.png"
        ))
        self.generate_btn.clicked.connect(self._on_generate)
        ll.addWidget(self.generate_btn)

        self.stop_btn = QPushButton(self.tr("Stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        ll.addWidget(self.stop_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        ll.addWidget(self.progress_bar)
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("font-size: 10px;")
        ll.addWidget(self.progress_label)

        left.setFixedWidth(280)
        splitter.addWidget(left)

        # Right panel
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        viewer_toolbar = QHBoxLayout()
        self.image_title = QLabel(self.tr("Select a track to view its spectrogram"))
        self.image_title.setStyleSheet("font-weight: bold;")
        viewer_toolbar.addWidget(self.image_title)
        viewer_toolbar.addStretch()

        zoom_in_btn = QPushButton(self.tr("Zoom In (+)"))
        zoom_in_btn.setMinimumWidth(110)
        zoom_in_btn.clicked.connect(lambda: self.viewer.zoom_in())
        viewer_toolbar.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton(self.tr("Zoom Out (−)"))
        zoom_out_btn.setMinimumWidth(115)
        zoom_out_btn.clicked.connect(lambda: self.viewer.zoom_out())
        viewer_toolbar.addWidget(zoom_out_btn)

        fit_btn = QPushButton(self.tr("Fit Width"))
        fit_btn.setMinimumWidth(95)
        fit_btn.clicked.connect(lambda: self.viewer._fit_width())
        viewer_toolbar.addWidget(fit_btn)

        open_btn = QPushButton(self.tr("Open Folder"))
        open_btn.setMinimumWidth(110)
        open_btn.clicked.connect(self._on_open_folder)
        viewer_toolbar.addWidget(open_btn)

        rl.addLayout(viewer_toolbar)

        self.hint_label = QLabel(self.tr(
            "Tip: Ctrl+scroll to zoom · Click-drag to pan when zoomed · "
            "Double-click image to reset fit · Pink/salmon rows = PNG not yet generated"
        ))
        self.hint_label.setStyleSheet(f"font-size: 10px; color: {styles.FG_MUTED.name()};")
        rl.addWidget(self.hint_label)

        self.viewer = _ImageViewer()
        rl.addWidget(self.viewer)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 10px;")
        rl.addWidget(self.status_label)

        splitter.addWidget(right)
        splitter.setSizes([280, 820])
        main.addWidget(splitter)

        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._on_folder_context)
        self.track_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_list.customContextMenuRequested.connect(self._on_track_context)

        return container

    # ── Fingerprinting panel ──────────────────────────────────────────────────

    def _build_fingerprint_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)

        fp_tabs = QTabWidget()
        layout.addWidget(fp_tabs)

        fp_tabs.addTab(self._build_fp_db_tab(),    self.tr("Fingerprint DB"))
        fp_tabs.addTab(self._build_fp_id_tab(),    self.tr("Identify File"))
        fp_tabs.addTab(self._build_fp_dup_tab(),   self.tr("Find Duplicates"))

        return container

    def _build_fp_db_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)

        # Stats
        stats_group = QGroupBox(self.tr("Database Stats"))
        sl = QHBoxLayout(stats_group)
        self.fp_stats_label = QLabel(self.tr("—"))
        sl.addWidget(self.fp_stats_label)
        sl.addStretch()
        refresh_btn = QPushButton(self.tr("Refresh"))
        refresh_btn.clicked.connect(self._fp_refresh_stats)
        sl.addWidget(refresh_btn)
        vl.addWidget(stats_group)

        # Build
        build_group = QGroupBox(self.tr("Build Fingerprint DB"))
        bl = QVBoxLayout(build_group)

        self.fp_count_label = QLabel("")
        self.fp_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fp_count_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.fp_count_label.setVisible(False)
        bl.addWidget(self.fp_count_label)

        self.fp_build_bar = QProgressBar()
        self.fp_build_bar.setVisible(False)
        bl.addWidget(self.fp_build_bar)

        queue_label = QLabel(self.tr("Up next:"))
        queue_label.setStyleSheet(f"font-size: 10px; color: {styles.FG_MUTED.name()};")
        self.fp_queue_label_header = queue_label
        queue_label.setVisible(False)
        bl.addWidget(queue_label)

        self.fp_queue_list = QListWidget()
        self.fp_queue_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.fp_queue_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fp_queue_list.setMaximumHeight(15 * 18)  # ≤15 rows visible
        self.fp_queue_list.setStyleSheet("font-size: 10px;")
        self.fp_queue_list.setVisible(False)
        bl.addWidget(self.fp_queue_list)

        self.fp_build_label = QLabel("")
        self.fp_build_label.setWordWrap(True)
        self.fp_build_label.setStyleSheet("font-size: 10px;")
        bl.addWidget(self.fp_build_label)

        self.fp_force_cb = QCheckBox(self.tr("Force re-fingerprint all (ignore cache)"))
        bl.addWidget(self.fp_force_cb)

        btn_row = QHBoxLayout()
        self.fp_build_btn = QPushButton(self.tr("Build DB"))
        self.fp_build_btn.clicked.connect(self._fp_start_build)
        btn_row.addWidget(self.fp_build_btn)
        self.fp_build_stop_btn = QPushButton(self.tr("Stop"))
        self.fp_build_stop_btn.setEnabled(False)
        self.fp_build_stop_btn.clicked.connect(self._fp_stop_build)
        btn_row.addWidget(self.fp_build_stop_btn)
        bl.addLayout(btn_row)

        vl.addWidget(build_group)
        vl.addStretch()

        # Load initial stats
        QTimer.singleShot(500, self._fp_refresh_stats)
        return w

    def _build_fp_id_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)

        self.fp_drop = _FileDrop()
        self.fp_drop.file_dropped.connect(self._fp_on_file_dropped)
        vl.addWidget(self.fp_drop)

        browse_btn = QPushButton(self.tr("Browse…"))
        browse_btn.clicked.connect(self._fp_browse_file)
        vl.addWidget(browse_btn)

        self.fp_id_status = QLabel("")
        self.fp_id_status.setStyleSheet("font-size: 10px;")
        vl.addWidget(self.fp_id_status)

        self.fp_id_table = QTableWidget(0, 5)
        self.fp_id_table.setHorizontalHeaderLabels(
            [self.tr("Rank"), self.tr("LB #"), self.tr("File"),
             self.tr("Score"), self.tr("Confident")]
        )
        self.fp_id_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.fp_id_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fp_id_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        vl.addWidget(self.fp_id_table)

        return w

    def _build_fp_dup_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(8, 8, 8, 8)

        desc = QLabel(self.tr(
            "Scan the fingerprint DB for pairs of tracks that share enough "
            "acoustic content to be the same performance. Slow on large collections."
        ))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 10px; color: {styles.FG_MUTED.name()};")
        vl.addWidget(desc)

        ctl_row = QHBoxLayout()
        self.fp_dup_btn = QPushButton(self.tr("Start Scan"))
        self.fp_dup_btn.clicked.connect(self._fp_start_dup_scan)
        ctl_row.addWidget(self.fp_dup_btn)
        self.fp_dup_stop_btn = QPushButton(self.tr("Stop"))
        self.fp_dup_stop_btn.setEnabled(False)
        self.fp_dup_stop_btn.clicked.connect(self._fp_stop_dup_scan)
        ctl_row.addWidget(self.fp_dup_stop_btn)
        ctl_row.addStretch()
        vl.addLayout(ctl_row)

        self.fp_dup_bar = QProgressBar()
        self.fp_dup_bar.setRange(0, 0)  # indeterminate
        self.fp_dup_bar.setVisible(False)
        vl.addWidget(self.fp_dup_bar)

        self.fp_dup_status = QLabel("")
        self.fp_dup_status.setStyleSheet("font-size: 10px;")
        vl.addWidget(self.fp_dup_status)

        self.fp_dup_table = QTableWidget(0, 5)
        self.fp_dup_table.setHorizontalHeaderLabels(
            [self.tr("LB A"), self.tr("LB B"),
             self.tr("File A"), self.tr("File B"), self.tr("Score")]
        )
        self.fp_dup_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.fp_dup_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self.fp_dup_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fp_dup_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        vl.addWidget(self.fp_dup_table)

        self.fp_dup_count_label = QLabel("")
        vl.addWidget(self.fp_dup_count_label)

        self.fp_dup_export_btn = QPushButton(self.tr("Export CSV…"))
        self.fp_dup_export_btn.setEnabled(False)
        self.fp_dup_export_btn.clicked.connect(self._fp_export_dup_csv)
        vl.addWidget(self.fp_dup_export_btn)

        return w

    # ── Spectrogram: folder management ───────────────────────────────────────

    def _on_add_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select Recording Folder"), str(Path.home()))
        if path:
            self._add_folders([path])

    def _on_folders_dropped(self, folders):
        QTimer.singleShot(0, lambda: self._add_folders(folders))

    def _add_folders(self, folders: list[str]):
        for f in folders:
            if f not in self._folders:
                self._folders.append(f)
                item = QListWidgetItem(Path(f).name)
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setToolTip(f)
                self.folder_list.addItem(item)
        self._refresh_inventory()

    def _on_clear_folders(self):
        self._folders.clear()
        self._inventory.clear()
        self.folder_list.clear()
        self.track_list.clear()
        self.viewer.clear_image()
        self.image_title.setText(self.tr("Select a track to view its spectrogram"))

    def _on_folder_context(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole)
        menu   = QMenu(self)

        load_act = QAction(self.tr("Load Tracks"), self)
        load_act.triggered.connect(lambda: self._load_tracks_for(folder))
        menu.addAction(load_act)

        rm_act = QAction(self.tr("Remove Folder"), self)
        rm_act.triggered.connect(lambda: self._remove_folder(folder))
        menu.addAction(rm_act)

        menu.exec(self.folder_list.mapToGlobal(pos))

    def _remove_folder(self, folder: str):
        self._folders = [f for f in self._folders if f != folder]
        self._inventory.pop(folder, None)
        for i in range(self.folder_list.count()):
            if self.folder_list.item(i).data(Qt.ItemDataRole.UserRole) == folder:
                self.folder_list.takeItem(i)
                break
        self.track_list.clear()
        self.viewer.clear_image()

    # ── Spectrogram: inventory ────────────────────────────────────────────────

    def _refresh_inventory(self):
        if not self._folders:
            return
        folders = list(self._folders)
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/list",
            json={"folders": folders}, timeout=15,
        ).json())
        w.finished.connect(self._on_inventory_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_inventory_loaded(self, data):
        if not isinstance(data, dict):
            return
        self._inventory = data
        for i in range(self.folder_list.count()):
            folder = self.folder_list.item(i).data(Qt.ItemDataRole.UserRole)
            entries = data.get(folder, [])
            total  = len(entries)
            has    = sum(1 for e in entries if e["has_png"])
            self.folder_list.item(i).setText(f"{Path(folder).name}  [{has}/{total}]")
        item = self.folder_list.currentItem()
        if item:
            self._load_tracks_for(item.data(Qt.ItemDataRole.UserRole))

    def _load_tracks_for(self, folder: str):
        self.track_list.clear()
        self.viewer.clear_image()
        entries = self._inventory.get(folder, [])
        for e in entries:
            item = QListWidgetItem(e["audio_name"])
            item.setData(Qt.ItemDataRole.UserRole, e)
            if not e["has_png"]:
                item.setBackground(styles.ROW_FAIL)
                item.setToolTip(self.tr("No spectrogram yet — click Generate to create"))
            else:
                item.setToolTip(e["png_path"])
            self.track_list.addItem(item)

    def _on_track_selected(self, current, _previous):
        if not current:
            return
        e = current.data(Qt.ItemDataRole.UserRole)
        if not e:
            return
        if e.get("has_png") and e.get("png_path"):
            self._load_image(e["png_path"], e["audio_name"])
        else:
            self.viewer.clear_image()
            self.image_title.setText(
                self.tr("{} — no spectrogram yet").format(e["audio_name"]))
            self.status_label.setText(
                self.tr("No PNG for this track. Run Generate Spectrograms first."))

    def _load_image(self, png_path: str, name: str):
        self._current_png = png_path
        ok = self.viewer.load(png_path)
        if ok:
            self.image_title.setText(name)
            self.status_label.setText(self.tr("Loaded: {}").format(png_path))
        else:
            self.status_label.setText(self.tr("Failed to load: {}").format(png_path))

    def _on_track_context(self, pos):
        item = self.track_list.itemAt(pos)
        if not item:
            return
        e    = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        if e.get("has_png"):
            view_act = QAction(self.tr("View Spectrogram"), self)
            view_act.triggered.connect(
                lambda: self._load_image(e["png_path"], e["audio_name"]))
            menu.addAction(view_act)

            open_act = QAction(self.tr("Open PNG Externally"), self)
            open_act.triggered.connect(
                lambda: self._open_externally(e["png_path"]))
            menu.addAction(open_act)

        gen_act = QAction(self.tr("Generate This File Only"), self)
        gen_act.triggered.connect(lambda: self._generate_single(e))
        menu.addAction(gen_act)

        menu.exec(self.track_list.mapToGlobal(pos))

    def _open_externally(self, path: str):
        from gui.platform_utils import open_file
        try:
            open_file(path)
        except Exception as e:
            self.status_label.setText(self.tr("Open failed: {}").format(e))

    def _on_open_folder(self):
        item = self.folder_list.currentItem()
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole)
        spectro_dir = Path(folder) / "spectrograms"
        target = spectro_dir if spectro_dir.is_dir() else Path(folder)
        from gui.platform_utils import open_folder
        try:
            open_folder(target)
        except Exception as e:
            self.status_label.setText(self.tr("Open failed: {}").format(e))

    # ── Spectrogram: generation ───────────────────────────────────────────────

    def _on_generate(self):
        if not self._folders:
            self.status_label.setText(self.tr("Add folders first."))
            return
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText(self.tr("Starting…"))

        payload = {
            "folders":   self._folders,
            "width":     self.width_spin.value(),
            "dyn_range": self.dyn_spin.value(),
            "force":     self.force_cb.isChecked(),
        }
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/generate",
            json=payload, timeout=10,
        ).json())
        w.finished.connect(lambda r: (
            self._start_poll() if not r.get("error")
            else self._on_gen_error(r["error"])
        ))
        w.error.connect(self._on_gen_error)
        self._workers.append(w)
        w.start()

    def _generate_single(self, entry: dict):
        folder = str(Path(entry["audio_file"]).parent)
        payload = {
            "folders":   [folder],
            "width":     self.width_spin.value(),
            "dyn_range": self.dyn_spin.value(),
            "force":     True,
        }
        self.status_label.setText(self.tr("Generating: {}…").format(entry["audio_name"]))
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/generate",
            json=payload, timeout=10,
        ).json())
        w.finished.connect(lambda r: (
            self._start_poll() if not r.get("error")
            else self.status_label.setText(self.tr("Error: {}").format(r["error"]))
        ))
        self._workers.append(w)
        w.start()

    def _on_gen_error(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(self.tr("Error: {}").format(msg))

    def _on_stop(self):
        self.stop_btn.setEnabled(False)
        requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/spectrogram/stop",
            timeout=5,
        )

    def _start_poll(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(800)

    def _poll(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/spectrogram/status",
                timeout=5,
            ).json()
        except Exception:
            return

        status = r.get("status", "")
        done   = r.get("done",  0)
        total  = r.get("total", 0)
        errs   = r.get("errors", [])

        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)

        skip_msg = f"  ({r['skipped']} skipped)" if r.get("skipped") else ""
        err_msg  = f"  {len(errs)} error(s)" if errs else ""
        self.progress_label.setText(
            f"{r.get('current', '')}  [{done}/{total}]{skip_msg}{err_msg}"
        )

        if status in ("done", "error"):
            self._poll_timer.stop()
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

            if status == "error":
                self.progress_label.setText(
                    r.get("current", self.tr("Generation failed.")))
                self.status_label.setText(self.tr("Generation stopped with errors."))
            else:
                self.status_label.setText(
                    self.tr("Done. {} file(s) processed, {} skipped, {} error(s).").format(
                        done, r.get("skipped", 0), len(errs)
                    )
                )
                if errs:
                    err_text = "\n".join(f"{e['file']}: {e['error']}" for e in errs)
                    QMessageBox.warning(
                        self, self.tr("Generation Errors"),
                        self.tr("{} file(s) failed:\n\n{}").format(len(errs), err_text)
                    )

            self.progress_bar.setVisible(False)
            self._refresh_inventory()

    # ── Fingerprinting: DB tab ────────────────────────────────────────────────

    def _fp_refresh_stats(self):
        w = _Worker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/fingerprint/stats",
            timeout=10,
        ).json())
        w.finished.connect(self._fp_on_stats)
        w.error.connect(lambda e: self.fp_stats_label.setText(self.tr("Error: {}").format(e)))
        self._workers.append(w)
        w.start()

    def _fp_on_stats(self, data: dict):
        if "error" in data:
            self.fp_stats_label.setText(self.tr("Error: {}").format(data["error"]))
            return
        tc  = data.get("track_count", 0)
        hc  = data.get("hash_count", 0)
        cov = data.get("coverage_pct")
        cov_str = f" · {cov}% of collection" if cov is not None else ""
        self.fp_stats_label.setText(
            self.tr("{} track(s) fingerprinted · {:,} hashes stored{}").format(tc, hc, cov_str)
        )

    def _fp_start_build(self):
        self.fp_build_btn.setEnabled(False)
        self.fp_build_stop_btn.setEnabled(True)
        self.fp_build_bar.setVisible(True)
        self.fp_build_bar.setRange(0, 0)   # indeterminate until total is known
        self.fp_build_label.setText(self.tr("Starting…"))
        self._fp_build_total_set = False

        force = self.fp_force_cb.isChecked()
        port  = self.flask_port
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{port}/api/fingerprint/build",
            json={"force": force},
            timeout=15,
        ).json())
        w.finished.connect(self._fp_on_build_started)
        w.error.connect(self._fp_on_build_error)
        self._workers.append(w)
        w.start()

    def _fp_on_build_started(self, data: dict):
        if data.get("error"):
            self._fp_on_build_error(data["error"])
            return
        self._fp_build_thread = _FpBuildStatusThread(self.flask_port)
        self._fp_build_thread.status_update.connect(self._on_fp_build_status)
        self._fp_build_thread.start()

    def _fp_on_build_error(self, msg: str):
        if self._fp_build_thread:
            self._fp_build_thread.stop()
            self._fp_build_thread = None
        self.fp_build_btn.setEnabled(True)
        self.fp_build_stop_btn.setEnabled(False)
        self.fp_build_bar.setVisible(False)
        self.fp_build_label.setText(self.tr("Error: {}").format(msg))

    def _fp_stop_build(self):
        self.fp_build_stop_btn.setEnabled(False)
        self.fp_build_label.setText(self.tr("Stopping…"))
        port = self.flask_port
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{port}/api/fingerprint/build/stop", timeout=5,
        ))
        self._workers.append(w)
        w.start()

    def _on_fp_build_status(self, r: dict):
        status   = r.get("status", "")
        done     = r.get("done", 0)
        total    = r.get("total", 0)
        errs     = r.get("errors", [])
        stop_req = r.get("stop_requested", False)
        preview  = r.get("queue_preview", [])

        if total > 0 and not getattr(self, "_fp_build_total_set", False):
            self.fp_build_bar.setRange(0, total)
            self._fp_build_total_set = True
        if total > 0:
            self.fp_build_bar.setValue(done)

        if status == "scanning":
            self.fp_build_label.setText(r.get("current", "Scanning…"))
            return

        if status == "done":
            if self._fp_build_thread:
                self._fp_build_thread.stop()
                self._fp_build_thread = None
            self.fp_build_btn.setEnabled(True)
            self.fp_build_stop_btn.setEnabled(False)
            self.fp_build_bar.setVisible(False)
            self.fp_count_label.setVisible(False)
            self.fp_queue_list.setVisible(False)
            self.fp_queue_label_header.setVisible(False)
            label = self.tr("Stopped.") if stop_req else self.tr("Done.")
            self.fp_build_label.setText(
                self.tr("{} {} fingerprinted, {} skipped, {} error(s).").format(
                    label, done, r.get("skipped", 0), len(errs)
                )
            )
            self._fp_refresh_stats()
        elif stop_req:
            self.fp_count_label.setVisible(False)
            self.fp_queue_list.setVisible(False)
            self.fp_queue_label_header.setVisible(False)
            self.fp_build_label.setText(
                self.tr("Stopping… [{}/{}]").format(done, total)
            )
        else:
            # Update prominent count label
            if total > 0:
                self.fp_count_label.setText(
                    self.tr("{} of {}").format(done, total)
                )
                self.fp_count_label.setVisible(True)

            # Populate queue preview list
            self.fp_queue_list.clear()
            for name in preview:
                self.fp_queue_list.addItem(name)
            show_queue = bool(preview)
            self.fp_queue_list.setVisible(show_queue)
            self.fp_queue_label_header.setVisible(show_queue)

            skip_msg = f"  ({r['skipped']} skipped)" if r.get("skipped") else ""
            err_msg  = f"  {len(errs)} error(s)" if errs else ""
            self.fp_build_label.setText(
                f"{r.get('current', '')}  [{done}/{total}]{skip_msg}{err_msg}"
            )

    # ── Fingerprinting: Identify tab ──────────────────────────────────────────

    def _fp_browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select Audio File"), str(Path.home()),
            self.tr("Audio Files (*.flac *.wav *.shn *.ape *.wv *.m4a *.mp3 *.ogg *.aif *.aiff)")
        )
        if path:
            self.fp_drop.setText(Path(path).name)
            self._fp_identify(path)

    def _fp_on_file_dropped(self, path: str):
        self._fp_identify(path)

    def _fp_identify(self, path: str):
        self.fp_id_status.setText(self.tr("Identifying…"))
        self.fp_id_table.setRowCount(0)

        if self._fp_id_worker and self._fp_id_worker.isRunning():
            return

        self._fp_id_worker = _FpIdentifyWorker(self.flask_port, path)
        self._fp_id_worker.finished.connect(self._fp_on_identify_done)
        self._fp_id_worker.error.connect(
            lambda e: self.fp_id_status.setText(self.tr("Error: {}").format(e)))
        self._fp_id_worker.start()

    def _fp_on_identify_done(self, results: list):
        self.fp_id_table.setRowCount(0)
        if not results:
            self.fp_id_status.setText(self.tr("No match found in fingerprint DB."))
            return

        self.fp_id_status.setText(
            self.tr("{} candidate(s) found.").format(len(results)))

        for rank, res in enumerate(results, 1):
            row = self.fp_id_table.rowCount()
            self.fp_id_table.insertRow(row)
            self.fp_id_table.setItem(row, 0, QTableWidgetItem(str(rank)))
            self.fp_id_table.setItem(row, 1, QTableWidgetItem(str(res.get("lb_number", ""))))
            self.fp_id_table.setItem(row, 2, QTableWidgetItem(
                Path(res.get("file_path", "")).name))
            self.fp_id_table.setItem(row, 3, QTableWidgetItem(str(res.get("score", ""))))
            self.fp_id_table.setItem(row, 4, QTableWidgetItem(
                self.tr("Yes") if res.get("confident") else self.tr("No")))

    # ── Fingerprinting: Duplicates tab ────────────────────────────────────────

    def _fp_start_dup_scan(self):
        self.fp_dup_btn.setEnabled(False)
        self.fp_dup_stop_btn.setEnabled(True)
        self.fp_dup_bar.setVisible(True)
        self.fp_dup_status.setText(self.tr("Scanning…"))
        self.fp_dup_table.setRowCount(0)
        self.fp_dup_count_label.setText("")
        self.fp_dup_export_btn.setEnabled(False)
        self._fp_dup_results = []

        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/fingerprint/duplicates/scan",
            timeout=15,
        ).json())
        w.finished.connect(self._fp_on_dup_scan_started)
        w.error.connect(lambda e: self._fp_dup_scan_done(error=e))
        self._workers.append(w)
        w.start()

    def _fp_on_dup_scan_started(self, data: dict):
        if data.get("error"):
            self._fp_dup_scan_done(error=data["error"])
            return
        self._fp_dup_thread = _FpDupStatusThread(self.flask_port)
        self._fp_dup_thread.status_update.connect(self._on_fp_dup_status)
        self._fp_dup_thread.start()

    def _fp_stop_dup_scan(self):
        self.fp_dup_stop_btn.setEnabled(False)
        self.fp_dup_status.setText(self.tr("Stopping…"))
        port = self.flask_port
        w = _Worker(lambda: requests.post(
            f"http://127.0.0.1:{port}/api/fingerprint/duplicates/scan/stop", timeout=5,
        ))
        self._workers.append(w)
        w.start()

    def _on_fp_dup_status(self, r: dict):
        msg      = r.get("message", "")
        stop_req = r.get("stop_requested", False)
        if msg and not stop_req:
            self.fp_dup_status.setText(msg)

        if r.get("status") == "done":
            if self._fp_dup_thread:
                self._fp_dup_thread.stop()
                self._fp_dup_thread = None
            results = r.get("results", [])
            self._fp_dup_scan_done(results=results)

    def _fp_dup_scan_done(self, results: list | None = None, error: str = ""):
        if self._fp_dup_thread:
            self._fp_dup_thread.stop()
            self._fp_dup_thread = None
        self.fp_dup_btn.setEnabled(True)
        self.fp_dup_stop_btn.setEnabled(False)
        self.fp_dup_bar.setVisible(False)

        if error:
            self.fp_dup_status.setText(self.tr("Error: {}").format(error))
            return

        results = results or []
        self._fp_dup_results = results
        self.fp_dup_table.setRowCount(0)

        for res in results:
            row = self.fp_dup_table.rowCount()
            self.fp_dup_table.insertRow(row)
            self.fp_dup_table.setItem(row, 0, QTableWidgetItem(str(res.get("lb_a", ""))))
            self.fp_dup_table.setItem(row, 1, QTableWidgetItem(str(res.get("lb_b", ""))))
            self.fp_dup_table.setItem(row, 2, QTableWidgetItem(
                Path(res.get("file_a", "")).name))
            self.fp_dup_table.setItem(row, 3, QTableWidgetItem(
                Path(res.get("file_b", "")).name))
            self.fp_dup_table.setItem(row, 4, QTableWidgetItem(str(res.get("score", ""))))

        n = len(results)
        self.fp_dup_count_label.setText(
            self.tr("{} duplicate pair(s) found.").format(n))
        self.fp_dup_export_btn.setEnabled(n > 0)

    def _fp_export_dup_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Duplicates CSV"),
            str(Path.home() / "duplicates.csv"),
            self.tr("CSV Files (*.csv)")
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["lb_a", "lb_b", "file_a", "file_b", "score", "confident"]
                )
                writer.writeheader()
                writer.writerows(self._fp_dup_results)
        except Exception as e:
            QMessageBox.warning(self, self.tr("Export Failed"), str(e))
