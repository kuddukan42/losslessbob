from pathlib import Path

from backend.paths import DATA_DIR as _DATA_DIR

import logging
import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QCheckBox, QSpinBox, QProgressBar,
    QFileDialog, QMessageBox, QLineEdit,
    QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem,
)
from PyQt6.QtGui import QColor

_log = logging.getLogger(__name__)


class _ImportThread(QThread):
    """Fires the async import start request; returns immediately once the backend accepts it."""
    finished = pyqtSignal(dict)

    def __init__(self, flask_port, file_path):
        super().__init__()
        self.flask_port = flask_port
        self.file_path = file_path

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/import",
                json={"file_path": str(self.file_path)},
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


class _ImportStatusThread(QThread):
    """Polls /api/db/import/status every 500 ms while an import is running."""
    status_update = pyqtSignal(dict)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self):
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/db/import/status",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(500)

    def stop(self):
        self._running = False


class _ResetThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/reset",
                timeout=30,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


class _WtrfTestThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port, username, password):
        super().__init__()
        self.flask_port = flask_port
        self.username = username
        self.password = password

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/wtrf/test",
                json={"username": self.username, "password": self.password},
                timeout=20,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"ok": False, "error": str(e)})


class _SingleScrapeThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port, lb_number, force=False):
        super().__init__()
        self.flask_port = flask_port
        self.lb_number = lb_number
        self.force = force

    def run(self):
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{self.lb_number}/scrape",
                json={"force": self.force},
                timeout=30,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


class _ScrapeStatusThread(QThread):
    status_update = pyqtSignal(dict)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self):
        while self._running:
            try:
                resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/scrape/status", timeout=5)
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(1000)

    def stop(self):
        self._running = False


class _DiscoverThread(QThread):
    """Calls GET /api/flat_file/discover in a background thread."""
    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/discover",
                timeout=25,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _GithubReleaseThread(QThread):
    """POST /api/master/github_release in a background thread."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, db_path: str, manifest_path: str,
                 version: str, prev_published_at: str | None) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.db_path = db_path
        self.manifest_path = manifest_path
        self.version = version
        self.prev_published_at = prev_published_at

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/master/github_release",
                json={
                    "db_path": self.db_path,
                    "manifest_path": self.manifest_path,
                    "version": self.version,
                    "prev_published_at": self.prev_published_at,
                },
                timeout=150,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _ExportMasterThread(QThread):
    """GET /api/master/status + POST /api/master/export off the main thread."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            prev_published_at = None
            try:
                st = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/master/status",
                    timeout=10,
                )
                if st.ok:
                    prev_published_at = st.json().get("master_published_at")
            except Exception:
                pass
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/master/export",
                json={"reason": "publish"}, timeout=300,
            )
            data = resp.json()
            data["_prev_published_at"] = prev_published_at
            self.finished.emit(data)
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _InstallMasterThread(QThread):
    """POST /api/master/import off the main thread."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, path: str) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.path = path

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/master/import",
                json={"path": self.path}, timeout=600,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _DownloadThread(QThread):
    """Calls POST /api/flat_file/download/{id} in a background thread."""
    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, release_id: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.release_id = release_id

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/download/{self.release_id}",
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _ApplyThread(QThread):
    """Calls POST /api/flat_file/apply/{id} in a background thread."""
    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, release_id: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.release_id = release_id

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/apply/{self.release_id}",
                timeout=120,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _UpdateAvailableDialog(QDialog):
    """Modal dialog shown when a new flat-file release is detected.

    Shows release metadata and provides Download & Apply, Defer, and Skip actions.
    """

    def __init__(
        self,
        release_info: dict,
        last_applied: dict | None,
        flask_port: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flat File Update Available")
        self.flask_port = flask_port
        self.release_info = release_info
        self._download_thread: _DownloadThread | None = None
        self._apply_thread: _ApplyThread | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Release info label
        info_parts = []
        fn = release_info.get("zip_filename", "Unknown")
        info_parts.append(f"<b>New file:</b> {fn}")
        if release_info.get("page_timestamp"):
            info_parts.append(f"<b>Page updated:</b> {release_info['page_timestamp']}")
        sz = release_info.get("zip_size_bytes", 0)
        if sz:
            info_parts.append(f"<b>Size:</b> {sz / 1024 / 1024:.1f} MB")
        if last_applied:
            prev_fn = last_applied.get("zip_filename", "")
            prev_date = (last_applied.get("applied_at") or "")[:19]
            info_parts.append(f"<b>Last applied:</b> {prev_fn} on {prev_date}")
            # Estimate new LB range
            prev_lb = last_applied.get("last_lb_in_name") or 0
            new_lb = release_info.get("last_lb_in_name") or 0
            if new_lb and prev_lb and new_lb > prev_lb:
                info_parts.append(
                    f"<b>Estimated new LBs:</b> up to {new_lb - prev_lb} (LB-{prev_lb+1} – LB-{new_lb})"
                )
        info_lbl = QLabel("<br>".join(info_parts))
        info_lbl.setTextFormat(Qt.TextFormat.RichText)
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("Download && Apply")
        self._apply_btn.clicked.connect(self._on_download_apply)
        btn_row.addWidget(self._apply_btn)

        self._defer_btn = QPushButton("Defer 1 Day")
        self._defer_btn.clicked.connect(self._on_defer)
        btn_row.addWidget(self._defer_btn)

        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.setMinimumWidth(480)

    def _set_busy(self, busy: bool) -> None:
        self._apply_btn.setEnabled(not busy)
        self._defer_btn.setEnabled(not busy)
        self._progress.setVisible(busy)

    def _on_download_apply(self) -> None:
        release_id = self.release_info.get("id")
        if not release_id:
            QMessageBox.warning(self, "Error", "No release ID available.")
            return
        self._set_busy(True)
        self._status_lbl.setText("Downloading zip…")
        self._download_thread = _DownloadThread(self.flask_port, release_id)
        self._download_thread.finished.connect(self._on_downloaded)
        self._download_thread.start()

    def _on_downloaded(self, result: dict) -> None:
        if "error" in result:
            self._set_busy(False)
            self._status_lbl.setText(f"Download failed: {result['error']}")
            return
        # Fetch diff counts before applying
        release_id = self.release_info.get("id")
        self._status_lbl.setText("Computing diff…")
        try:
            diff_resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/diff/{release_id}",
                timeout=60,
            )
            diff = diff_resp.json()
        except Exception as exc:
            self._set_busy(False)
            self._status_lbl.setText(f"Diff failed: {exc}")
            return

        if "error" in diff:
            self._set_busy(False)
            self._status_lbl.setText(f"Diff error: {diff['error']}")
            return

        msg = (
            f"Ready to apply:\n"
            f"  Added:   {diff.get('rows_added', 0):,}\n"
            f"  Changed: {diff.get('rows_changed', 0):,}\n"
            f"  Removed: {diff.get('rows_removed', 0):,}\n\n"
            "Proceed?"
        )
        ans = QMessageBox.question(
            self, "Confirm Apply", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self._set_busy(False)
            self._status_lbl.setText("Apply cancelled.")
            return

        self._status_lbl.setText("Applying release…")
        self._apply_thread = _ApplyThread(self.flask_port, release_id)
        self._apply_thread.finished.connect(self._on_applied)
        self._apply_thread.start()

    def _on_applied(self, result: dict) -> None:
        self._set_busy(False)
        if "error" in result:
            self._status_lbl.setText(f"Apply failed: {result['error']}")
            return
        added = result.get("rows_added", 0)
        changed = result.get("rows_changed", 0)
        removed = result.get("rows_removed", 0)
        QMessageBox.information(
            self, "Update Applied",
            f"Flat file applied successfully.\n"
            f"Added: {added:,}  Changed: {changed:,}  Removed: {removed:,}",
        )
        self.accept()

    def _on_defer(self) -> None:
        release_id = self.release_info.get("id")
        if not release_id:
            self.reject()
            return
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/defer/{release_id}",
                json={"days": 1},
                timeout=10,
            )
        except Exception:
            pass
        self.reject()


class _GeocodeRunThread(QThread):
    """POST /api/geocode/run in a background thread; never blocks the GUI."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, retry_failed: bool) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.retry_failed = retry_failed

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/run",
                json={"retry_failed": self.retry_failed},
                timeout=15,
            )
            if resp.ok:
                self.finished.emit(resp.json())
            elif resp.status_code == 409:
                self.finished.emit({"error": "already running", "status_code": 409})
            else:
                self.finished.emit({"error": resp.text, "status_code": resp.status_code})
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _GeocodeStatusThread(QThread):
    """Polls GET /api/geocode/status every 2 s while geocoding is running."""

    status_update = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/geocode/status",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(2000)

    def stop(self) -> None:
        """Signal the polling loop to exit on the next iteration."""
        self._running = False


class SetupTab(QWidget):
    stats_changed = pyqtSignal()
    search_page_size_changed = pyqtSignal(int)

    def __init__(self, flask_port, state_store=None, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._state_store = state_store
        self._loading = False
        self._import_thread = None
        self._import_status_thread = None
        self._reset_thread = None
        self._wtrf_test_thread = None
        self._discover_thread: _DiscoverThread | None = None
        self._geocode_run_thread: _GeocodeRunThread | None = None
        self._geocode_status_thread: _GeocodeStatusThread | None = None
        self._github_release_thread: _GithubReleaseThread | None = None
        self._build_ui()
        self._refresh_col_defaults_status()
        self._load_settings()
        self._refresh_stats()
        self._load_curator_status()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._load_flat_file_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Database group: left = archive controls, right = Data Management ──
        db_group = QGroupBox("Database")
        db_inner = QHBoxLayout(db_group)
        db_inner.setSpacing(16)

        # Left panel: archive stats and controls
        left_panel = QWidget()
        db_layout = QVBoxLayout(left_panel)
        db_layout.setContentsMargins(0, 0, 0, 0)

        db_sel_row = QHBoxLayout()
        db_sel_row.addWidget(QLabel("Active database:"))
        self.db_combo = QComboBox()
        self.db_combo.addItems(["LosslessBob", "Grateful Dead etree"])
        self.db_combo.currentIndexChanged.connect(self._on_db_changed)
        db_sel_row.addWidget(self.db_combo)
        db_sel_row.addStretch()
        db_layout.addLayout(db_sel_row)

        self.db_stats_label = QLabel("Loading stats...")
        db_layout.addWidget(self.db_stats_label)

        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("Import Database File...")
        self.import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(self.import_btn)

        self.check_update_btn = QPushButton("Check for Flat File Update")
        self.check_update_btn.clicked.connect(self._on_check_update)
        btn_row.addWidget(self.check_update_btn)

        self.open_folder_btn = QPushButton("Open Data Folder")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addStretch()
        db_layout.addLayout(btn_row)

        reset_row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset Database...")
        self.reset_btn.setStyleSheet(
            "QPushButton { background-color: #8B1A1A; color: #FFFFFF; border-radius: 3px; }"
            "QPushButton:hover { background-color: #B22222; }"
            "QPushButton:disabled { background-color: #888888; }"
        )
        self.reset_btn.setToolTip("Drop all data and reinitialize the database from scratch")
        self.reset_btn.clicked.connect(self._on_reset)
        reset_row.addWidget(self.reset_btn)
        reset_row.addStretch()
        db_layout.addLayout(reset_row)

        # External tool availability indicators
        sox_row = QHBoxLayout()
        sox_row.addWidget(QLabel("SoX:"))
        self.sox_status_label = QLabel("Checking…")
        sox_row.addWidget(self.sox_status_label)
        sox_row.addStretch()
        db_layout.addLayout(sox_row)

        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(QLabel("ffmpeg:"))
        self.ffmpeg_status_label = QLabel("Checking…")
        ffmpeg_row.addWidget(self.ffmpeg_status_label)
        ffmpeg_row.addStretch()
        db_layout.addLayout(ffmpeg_row)

        shntool_row = QHBoxLayout()
        shntool_row.addWidget(QLabel("shntool:"))
        self.shntool_status_label = QLabel("Checking…")
        shntool_row.addWidget(self.shntool_status_label)
        self.sox_check_btn = QPushButton("Re-check")
        self.sox_check_btn.setFixedWidth(80)
        self.sox_check_btn.clicked.connect(self._check_sox)
        shntool_row.addWidget(self.sox_check_btn)
        shntool_row.addStretch()
        db_layout.addLayout(shntool_row)

        self.import_status_label = QLabel("")
        db_layout.addWidget(self.import_status_label)

        self.import_progress = QProgressBar()
        self.import_progress.setObjectName("importProgress")
        self.import_progress.setVisible(False)
        db_layout.addWidget(self.import_progress)

        db_layout.addStretch()
        db_inner.addWidget(left_panel, stretch=3)

        # Vertical divider
        from PyQt6.QtWidgets import QFrame
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFrameShadow(QFrame.Shadow.Sunken)
        db_inner.addWidget(div)

        # Right panel: Data Management
        right_panel = QWidget()
        purge_layout = QVBoxLayout(right_panel)
        purge_layout.setContentsMargins(0, 0, 0, 0)

        purge_layout.addWidget(QLabel(
            "<b>Data Management</b> — purge operations remove user data only; "
            "the checksum archive is never affected."
        ))

        # User-data stats (collection, wishlist, etc.)
        self.coll_stats_label = QLabel("Loading…")
        self.coll_stats_label.setStyleSheet("font-size:11px; color:#666;")
        purge_layout.addWidget(self.coll_stats_label)

        purge_items = [
            ("My Collection (+ ratings, alerts)", "collection"),
            ("Wishlist",                          "wishlist"),
            ("Personal Ratings and Tags only",    "personal_meta"),
            ("Watchdog Alerts",                   "integrity_events"),
            ("Scrape Diff Changelog",             "entry_changes"),
        ]
        purge_grid = QGridLayout()
        purge_grid.setVerticalSpacing(4)
        for i, (label, scope) in enumerate(purge_items):
            lbl = QLabel(label)
            btn = QPushButton("Purge…")
            btn.setFixedWidth(80)
            btn.clicked.connect(
                lambda checked=False, s=scope, l=label: self._on_purge(s, l)
            )
            purge_grid.addWidget(lbl, i, 0)
            purge_grid.addWidget(btn, i, 1)

        purge_layout.addLayout(purge_grid)
        self.purge_status_label = QLabel("")
        purge_layout.addWidget(self.purge_status_label)
        purge_layout.addStretch()
        db_inner.addWidget(right_panel, stretch=2)

        layout.addWidget(db_group)

        # ── Master Data section ─────────────────────────────────────────────
        # Curator publishes master snapshots; end users install them.
        master_group = QGroupBox("Master Data")
        master_layout = QVBoxLayout(master_group)

        curator_row = QHBoxLayout()
        self.curator_cb = QCheckBox("Curator mode (publish-enabled)")
        self.curator_cb.setToolTip(
            "Enable to publish master-data snapshots that ship to other users.\n"
            "Curator status is stored locally and never included in any export."
        )
        self.curator_cb.toggled.connect(self._on_curator_toggled)
        curator_row.addWidget(self.curator_cb)
        curator_row.addStretch()
        master_layout.addLayout(curator_row)

        self.master_status_label = QLabel("Master version: (not yet published)")
        master_layout.addWidget(self.master_status_label)

        master_btn_row = QHBoxLayout()
        self.publish_master_btn = QPushButton("Publish Master Update…")
        self.publish_master_btn.setToolTip(
            "Build a master-only snapshot (.db + .manifest.json) in data/exports/. "
            "Strips all user data, verifies, computes SHA256, writes manifest."
        )
        self.publish_master_btn.clicked.connect(self._on_publish_master)
        self.publish_master_btn.setEnabled(False)  # toggled by curator checkbox
        master_btn_row.addWidget(self.publish_master_btn)

        self.install_master_btn = QPushButton("Install Master Update…")
        self.install_master_btn.setToolTip(
            "Apply a master snapshot from disk. Your collection, wishlist, "
            "credentials, and personal settings are preserved."
        )
        self.install_master_btn.clicked.connect(self._on_install_master)
        master_btn_row.addWidget(self.install_master_btn)
        master_btn_row.addStretch()
        master_layout.addLayout(master_btn_row)

        self._publish_status_label = QLabel("")
        self._publish_status_label.setVisible(False)
        master_layout.addWidget(self._publish_status_label)

        layout.addWidget(master_group)

        # ── Geocode Locations (curator only) ────────────────────────────────
        self._geocode_group = QGroupBox("Geocode Locations")
        geocode_layout = QVBoxLayout(self._geocode_group)

        geocode_layout.addWidget(QLabel(
            "Geocode entries.location → lat/lon via Nominatim (curator only)"
        ))

        geocode_opts_row = QHBoxLayout()
        self._geocode_retry_cb = QCheckBox("Retry Failed")
        self._geocode_retry_cb.setToolTip(
            "Re-attempt entries that previously failed geocoding"
        )
        geocode_opts_row.addWidget(self._geocode_retry_cb)

        self._geocode_run_btn = QPushButton("Run Geocoder")
        self._geocode_run_btn.clicked.connect(self._on_geocode_run)
        geocode_opts_row.addWidget(self._geocode_run_btn)
        geocode_opts_row.addStretch()
        geocode_layout.addLayout(geocode_opts_row)

        self._geocode_status_label = QLabel("Status: idle")
        geocode_layout.addWidget(self._geocode_status_label)

        self._geocode_group.setVisible(False)  # shown only in curator mode
        layout.addWidget(self._geocode_group)

        # Search settings section
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout(search_group)
        page_size_row = QHBoxLayout()
        page_size_row.addWidget(QLabel("Results per page:"))
        self.search_page_spin = QSpinBox()
        self.search_page_spin.setRange(10, 500)
        self.search_page_spin.setValue(50)
        self.search_page_spin.setSingleStep(10)
        self.search_page_spin.setFixedWidth(80)
        self.search_page_spin.valueChanged.connect(self._on_search_page_size_changed)
        page_size_row.addWidget(self.search_page_spin)
        page_size_row.addStretch()
        search_layout.addLayout(page_size_row)
        layout.addWidget(search_group)

        # ── Column Widths ────────────────────────────────────────────────────────
        cw_group = QGroupBox("Column Widths")
        cw_layout = QVBoxLayout(cw_group)

        self._cw_status_label = QLabel("User defaults: none (factory widths will be used)")
        cw_layout.addWidget(self._cw_status_label)

        cw_btn_row = QHBoxLayout()
        self._save_defaults_btn = QPushButton("Save as Defaults")
        self._save_defaults_btn.setToolTip(
            "Snapshot current column widths as your personal defaults"
        )
        self._save_defaults_btn.clicked.connect(self._on_save_col_defaults)
        cw_btn_row.addWidget(self._save_defaults_btn)

        self._restore_defaults_btn = QPushButton("Restore My Defaults")
        self._restore_defaults_btn.setToolTip(
            "Apply your saved column-width defaults to all tables"
        )
        self._restore_defaults_btn.setEnabled(False)
        self._restore_defaults_btn.clicked.connect(self._on_restore_col_defaults)
        cw_btn_row.addWidget(self._restore_defaults_btn)

        self._restore_factory_btn = QPushButton("Restore Factory")
        self._restore_factory_btn.setToolTip(
            "Reset all column widths to factory defaults and clear your saved layout"
        )
        self._restore_factory_btn.clicked.connect(self._on_restore_factory_defaults)
        cw_btn_row.addWidget(self._restore_factory_btn)
        cw_btn_row.addStretch()
        cw_layout.addLayout(cw_btn_row)

        layout.addWidget(cw_group)

        # ── Connection settings (scraper controls moved to Scraper tab) ─────────
        conn_row = QHBoxLayout()
        conn_row.setSpacing(12)

        # ── qBittorrent section ──────────────────────────────────────────────
        qbt_group = QGroupBox("qBittorrent")
        qbt_layout = QGridLayout(qbt_group)
        qbt_layout.setHorizontalSpacing(8)
        qbt_layout.setVerticalSpacing(6)

        qbt_layout.addWidget(QLabel("Host:"), 0, 0)
        self.qbt_host = QLineEdit("localhost")
        self.qbt_host.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_host, 0, 1)

        qbt_layout.addWidget(QLabel("Port:"), 0, 2)
        self.qbt_port = QSpinBox()
        self.qbt_port.setRange(1, 65535)
        self.qbt_port.setValue(8080)
        self.qbt_port.setFixedWidth(80)
        qbt_layout.addWidget(self.qbt_port, 0, 3)

        qbt_layout.addWidget(QLabel("Username:"), 1, 0)
        self.qbt_user = QLineEdit()
        self.qbt_user.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_user, 1, 1)

        qbt_layout.addWidget(QLabel("Password:"), 1, 2)
        self.qbt_pass = QLineEdit()
        self.qbt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.qbt_pass.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_pass, 1, 3)

        qbt_layout.addWidget(QLabel("API Key:"), 2, 0)
        self.qbt_api_key = QLineEdit()
        self.qbt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.qbt_api_key.setPlaceholderText("qBittorrent 5+ — takes priority over username/password")
        self.qbt_api_key.setFixedWidth(380)
        qbt_layout.addWidget(self.qbt_api_key, 2, 1, 1, 3)

        qbt_layout.addWidget(QLabel("Category:"), 3, 0)
        self.qbt_category = QLineEdit()
        self.qbt_category.setPlaceholderText("e.g. losslessbob (optional)")
        self.qbt_category.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_category, 3, 1)

        qbt_layout.addWidget(QLabel("Tags:"), 3, 2)
        self.qbt_tags = QLineEdit()
        self.qbt_tags.setPlaceholderText("comma-separated (optional)")
        self.qbt_tags.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_tags, 3, 3)

        qbt_btn_row = QHBoxLayout()
        self.qbt_save_btn = QPushButton("Save Credentials")
        self.qbt_save_btn.clicked.connect(self._on_qbt_save)
        qbt_btn_row.addWidget(self.qbt_save_btn)
        self.qbt_test_btn = QPushButton("Test Connection")
        self.qbt_test_btn.clicked.connect(self._on_qbt_test)
        qbt_btn_row.addWidget(self.qbt_test_btn)
        self.qbt_clear_btn = QPushButton("Clear Credentials")
        self.qbt_clear_btn.clicked.connect(self._on_qbt_clear)
        qbt_btn_row.addWidget(self.qbt_clear_btn)
        qbt_btn_row.addStretch()
        qbt_layout.addLayout(qbt_btn_row, 4, 0, 1, 5)

        self.qbt_status_label = QLabel("")
        qbt_layout.addWidget(self.qbt_status_label, 5, 0, 1, 5)
        qbt_layout.setColumnStretch(4, 1)
        conn_row.addWidget(qbt_group, stretch=1)

        # ── WTRF Forum section ───────────────────────────────────────────────
        wtrf_group = QGroupBox("Watching the River Flow Forum")
        wtrf_layout = QGridLayout(wtrf_group)
        wtrf_layout.setHorizontalSpacing(8)
        wtrf_layout.setVerticalSpacing(6)

        wtrf_layout.addWidget(QLabel("Username:"), 0, 0)
        self.wtrf_user = QLineEdit()
        self.wtrf_user.setFixedWidth(200)
        wtrf_layout.addWidget(self.wtrf_user, 0, 1)

        wtrf_layout.addWidget(QLabel("Password:"), 1, 0)
        self.wtrf_pass = QLineEdit()
        self.wtrf_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.wtrf_pass.setFixedWidth(200)
        wtrf_layout.addWidget(self.wtrf_pass, 1, 1)

        wtrf_layout.addWidget(QLabel("Board ID:"), 2, 0)
        self.wtrf_board_spin = QSpinBox()
        self.wtrf_board_spin.setRange(1, 9999)
        self.wtrf_board_spin.setFixedWidth(80)
        self.wtrf_board_spin.setToolTip("SMF board number from the forum URL (e.g. ?board=42.0 → 42)")
        self.wtrf_board_spin.valueChanged.connect(self._on_wtrf_board_changed)
        wtrf_layout.addWidget(self.wtrf_board_spin, 2, 1)

        wtrf_btn_row = QHBoxLayout()
        self.wtrf_save_btn = QPushButton("Save Credentials")
        self.wtrf_save_btn.clicked.connect(self._on_wtrf_save)
        wtrf_btn_row.addWidget(self.wtrf_save_btn)
        self.wtrf_test_btn = QPushButton("Test Connection")
        self.wtrf_test_btn.clicked.connect(self._on_wtrf_test)
        wtrf_btn_row.addWidget(self.wtrf_test_btn)
        self.wtrf_clear_btn = QPushButton("Clear Credentials")
        self.wtrf_clear_btn.clicked.connect(self._on_wtrf_clear)
        wtrf_btn_row.addWidget(self.wtrf_clear_btn)
        wtrf_btn_row.addStretch()
        wtrf_layout.addLayout(wtrf_btn_row, 3, 0, 1, 3)

        self.wtrf_status_label = QLabel("")
        wtrf_layout.addWidget(self.wtrf_status_label, 4, 0, 1, 3)
        wtrf_layout.setColumnStretch(2, 1)
        conn_row.addWidget(wtrf_group, stretch=1)

        # ── Torrent section ──────────────────────────────────────────────────
        torrent_group = QGroupBox("Torrent Settings")
        torrent_layout = QHBoxLayout(torrent_group)

        torrent_layout.addWidget(QLabel("Tracker list:"))
        self.tracker_list_combo = QComboBox()
        from backend.torrent_maker import TRACKER_LISTS
        self.tracker_list_combo.addItems(TRACKER_LISTS)
        self.tracker_list_combo.currentTextChanged.connect(self._on_tracker_list_changed)
        torrent_layout.addWidget(self.tracker_list_combo)

        self.refresh_trackers_btn = QPushButton("Refresh Trackers")
        self.refresh_trackers_btn.clicked.connect(self._on_refresh_trackers)
        torrent_layout.addWidget(self.refresh_trackers_btn)

        self.tracker_count_label = QLabel("—")
        torrent_layout.addWidget(self.tracker_count_label)
        torrent_layout.addStretch()
        conn_row.addWidget(torrent_group, stretch=1)

        layout.addLayout(conn_row)

        # ── Flat File History ────────────────────────────────────────────────
        ff_group = QGroupBox("Flat File History")
        ff_layout = QVBoxLayout(ff_group)

        self._ff_history_table = QTableWidget(0, 6)
        self._ff_history_table.setHorizontalHeaderLabels(
            ["Detected", "Filename", "Status", "Added", "Changed", "Removed"]
        )
        self._ff_history_table.horizontalHeader().setStretchLastSection(False)
        self._ff_history_table.horizontalHeader().setSectionResizeMode(
            1, self._ff_history_table.horizontalHeader().ResizeMode.Stretch
        )
        self._ff_history_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._ff_history_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._ff_history_table.setMinimumHeight(100)
        self._ff_history_table.setMaximumHeight(160)
        ff_layout.addWidget(self._ff_history_table)

        layout.addWidget(ff_group)

    # _build_ui end — scraper and bootleg catalog panels moved to ScraperTab

    # ── Column-width defaults ────────────────────────────────────────────────

    def _refresh_col_defaults_status(self) -> None:
        if self._state_store is None:
            return
        has = self._state_store.has_user_defaults
        self._restore_defaults_btn.setEnabled(has)
        self._cw_status_label.setText(
            "User defaults: saved" if has
            else "User defaults: none (factory widths will be used)"
        )

    def _on_save_col_defaults(self) -> None:
        if self._state_store is None:
            return
        self._state_store.save_user_defaults()
        self._cw_status_label.setText("Layout saved as defaults.")
        self._restore_defaults_btn.setEnabled(True)

    def _on_restore_col_defaults(self) -> None:
        if self._state_store is None:
            return
        self._state_store.restore_user_defaults()
        self._cw_status_label.setText("Defaults restored.")

    def _on_restore_factory_defaults(self) -> None:
        if self._state_store is None:
            return
        if QMessageBox.question(
            self, "Restore Factory Defaults",
            "Reset all column widths to factory defaults?\n\nThis will clear your saved layout.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._state_store.restore_factory_defaults()
        self._cw_status_label.setText("User defaults: none (factory widths will be used)")
        self._restore_defaults_btn.setEnabled(False)

    def _load_settings(self):
        self._loading = True
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5)
            data = resp.json()
            self.search_page_spin.setValue(int(data.get("search_page_size") or 50))
        except Exception:
            pass
        finally:
            self._loading = False
        # Load credential-dependent settings after _loading flag is cleared
        self._load_qbt_settings()
        self._load_wtrf_settings()
        self._load_tracker_settings()

    def _save_settings(self):
        if self._loading:
            return
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"search_page_size": str(self.search_page_spin.value())},
                timeout=5,
            )
        except Exception:
            pass

    def _on_search_page_size_changed(self, value: int) -> None:
        self._save_settings()
        self.search_page_size_changed.emit(value)

    def _refresh_stats(self):
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5)
            stats = resp.json()
            self.db_stats_label.setText(
                f"Total checksums: {stats.get('total_checksums', 0):,}  |  "
                f"LB entries: {stats.get('total_lb_numbers', 0):,}  |  "
                f"Latest LB: {stats.get('latest_lb', 'N/A')}  |  "
                f"Last import: {stats.get('last_import', 'Never')}"
            )
        except Exception:
            self.db_stats_label.setText("Could not load database stats.")
        self._refresh_collection_stats()

    def _refresh_collection_stats(self):
        _TABLE_LABELS = {
            "my_collection":   "My Collection",
            "my_wishlist":     "Wishlist",
            "collection_meta": "Personal Ratings",
            "integrity_events":"Watchdog Events",
            "entry_changes":   "Scrape Diff Rows",
        }
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/dbedit/tables", timeout=5
            )
            tables = {t["name"]: t["row_count"] for t in resp.json()}
            parts = []
            for key, label in _TABLE_LABELS.items():
                count = tables.get(key, 0)
                parts.append(f"{label}: {count:,}")
            self.coll_stats_label.setText("  |  ".join(parts))
        except Exception:
            self.coll_stats_label.setText("Could not load collection stats.")

    def _on_db_changed(self, index):
        pass

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select flat file", str(Path.home()),
            "Database files (*.txt);;All files (*)"
        )
        if not path:
            return

        self.import_btn.setEnabled(False)
        self.import_status_label.setText("Starting import…")
        self.import_progress.setRange(0, 0)
        self.import_progress.setVisible(True)

        self._import_thread = _ImportThread(self.flask_port, path)
        self._import_thread.finished.connect(self._on_import_started)
        self._import_thread.start()

    def _on_import_started(self, result):
        """Called once the backend acknowledges the async import has started."""
        if "error" in result:
            self.import_btn.setEnabled(True)
            self.import_progress.setVisible(False)
            self.import_status_label.setText(f"Error: {result['error']}")
            return
        # Backend accepted the request — start polling for progress
        self._import_status_thread = _ImportStatusThread(self.flask_port)
        self._import_status_thread.status_update.connect(self._on_import_status)
        self._import_status_thread.start()

    def _on_import_status(self, status):
        """Handles polling updates from _ImportStatusThread."""
        stage = status.get("stage", "idle")
        msg = status.get("message", "")
        running = status.get("running", False)
        rows_parsed = status.get("rows_parsed", 0)
        rows_total = status.get("rows_total", 0)
        rows_merged = status.get("rows_merged", 0)

        # Update progress bar: determinate during merge, indeterminate otherwise
        if stage == "merging" and rows_total > 0:
            self.import_progress.setRange(0, rows_total)
            self.import_progress.setValue(rows_merged)
        else:
            self.import_progress.setRange(0, 0)

        self.import_status_label.setText(msg)

        if not running:
            if self._import_status_thread:
                self._import_status_thread.stop()
                self._import_status_thread = None

            self.import_btn.setEnabled(True)
            self.import_progress.setVisible(False)

            if stage == "error":
                self.import_status_label.setText(f"Import failed: {status.get('error', 'unknown error')}")
            elif stage == "done":
                if "Already imported" in msg:
                    self.import_status_label.setText("Already imported — file unchanged since last run.")
                else:
                    new_lbs = status.get("new_lb_count", 0)
                    self.import_status_label.setText(
                        f"Import complete — {new_lbs:,} new LB entries added."
                    )
                    self._refresh_stats()
                    self.stats_changed.emit()

    def _on_reset(self):
        confirm = QMessageBox.warning(
            self,
            "Reset Database",
            "This will permanently delete ALL checksums, entries, and scraped data "
            "and reinitialize the database from scratch.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.reset_btn.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.import_status_label.setText("Resetting database...")

        self._reset_thread = _ResetThread(self.flask_port)
        self._reset_thread.finished.connect(self._on_reset_finished)
        self._reset_thread.start()

    def _on_reset_finished(self, result):
        self.reset_btn.setEnabled(True)
        self.import_btn.setEnabled(True)
        self.import_progress.setVisible(False)
        if "error" in result:
            self.import_status_label.setText(f"Reset failed: {result['error']}")
        else:
            self.import_status_label.setText("Database reset. Ready for a fresh import.")
            # Re-persist current UI state so user preferences survive the meta table wipe.
            self._save_settings()
            self._refresh_stats()
            self.stats_changed.emit()

    def _on_check_update(self) -> None:
        """Check for a new flat-file release on the LosslessBob download page."""
        self.check_update_btn.setEnabled(False)
        self._discover_thread = _DiscoverThread(self.flask_port)
        self._discover_thread.finished.connect(self._on_discover_result)
        self._discover_thread.start()

    def _on_discover_result(self, data: dict) -> None:
        self.check_update_btn.setEnabled(True)
        if data.get("error"):
            QMessageBox.warning(
                self, "Check Update",
                f"Discovery failed:\n{data['error']}",
            )
            return
        if not data.get("available"):
            last = data.get("last_applied_release")
            last_info = ""
            if last:
                fn = last.get("zip_filename", "")
                dt = (last.get("applied_at") or "")[:19]
                last_info = f"\n\nLast applied: {fn}\non {dt}"
            QMessageBox.information(
                self, "Up to Date",
                f"Your flat file is up to date.{last_info}",
            )
            return
        dlg = _UpdateAvailableDialog(
            release_info=data["current_release"],
            last_applied=data.get("last_applied_release"),
            flask_port=self.flask_port,
            parent=self,
        )
        dlg.exec()
        # Refresh history panel after dialog closes (update may have been applied)
        self._load_flat_file_history()
        self.stats_changed.emit()

    def _load_flat_file_history(self) -> None:
        """Populate the Flat File History table from the backend."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/releases",
                timeout=5,
            )
            releases = resp.json()
        except Exception:
            return
        if not isinstance(releases, list):
            return

        tbl = self._ff_history_table
        tbl.setRowCount(0)
        status_colors = {
            "applied": QColor("#d4edda"),
            "applied_legacy": QColor("#e2f0d9"),
            "detected": QColor("#fff3cd"),
            "downloaded": QColor("#cce5ff"),
            "deferred": QColor("#e2e3e5"),
            "failed": QColor("#f8d7da"),
        }
        for row_data in releases:
            row = tbl.rowCount()
            tbl.insertRow(row)
            detected = (row_data.get("detected_at") or "")[:16]
            filename = row_data.get("zip_filename", "")
            status = row_data.get("status", "")
            added = str(row_data.get("rows_added") or "")
            changed = str(row_data.get("rows_changed") or "")
            removed = str(row_data.get("rows_removed") or "")
            for col, val in enumerate([detected, filename, status, added, changed, removed]):
                item = QTableWidgetItem(val)
                color = status_colors.get(status)
                if color:
                    item.setBackground(color)
                tbl.setItem(row, col, item)
        tbl.resizeColumnsToContents()
        tbl.horizontalHeader().setSectionResizeMode(
            1, tbl.horizontalHeader().ResizeMode.Stretch
        )

    # ── Master Data: curator flag + publish/install handlers ───────────────────

    def _load_curator_status(self):
        """Read the curator flag from the backend and reflect it in the UI."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/curator", timeout=5
            )
            data = resp.json() if resp.ok else {}
            enabled = bool(data.get("is_curator", False))
        except Exception:
            enabled = False
        # Block signals so loading state doesn't trigger a POST loop
        self.curator_cb.blockSignals(True)
        self.curator_cb.setChecked(enabled)
        self.curator_cb.blockSignals(False)
        self.publish_master_btn.setEnabled(enabled)
        self._geocode_group.setVisible(enabled)
        self._refresh_master_status_label()

    def _refresh_master_status_label(self):
        """Show the current locally-installed master_version on the label."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5
            )
            # master_version is master meta; check via a separate read
            from backend import db as _db
            version = _db.get_meta("master_version") or ""
            published = _db.get_meta("master_published_at") or ""
            if version:
                self.master_status_label.setText(
                    f"Master version: {version}"
                    + (f"  (published {published[:19]})" if published else "")
                )
            else:
                self.master_status_label.setText(
                    "Master version: (not yet published or imported)"
                )
        except Exception as e:
            self.master_status_label.setText(f"Master version: (unknown — {e})")

    def _on_curator_toggled(self, checked: bool):
        """Persist the curator flag and gate the Publish button and geocoder group."""
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/curator",
                json={"enabled": bool(checked)}, timeout=5,
            )
            if not resp.ok:
                raise RuntimeError(resp.text)
            self.publish_master_btn.setEnabled(bool(checked))
            self._geocode_group.setVisible(bool(checked))
        except Exception as e:
            QMessageBox.warning(self, "Curator Mode", f"Could not update flag: {e}")
            # Revert UI to the actual server state
            self._load_curator_status()

    def _on_publish_master(self) -> None:
        """Build a master export then upload to GitHub releases."""
        confirm = QMessageBox.question(
            self, "Publish Master Update?",
            "Build a master-only snapshot and upload it to GitHub releases?\n\n"
            "This writes a .db and .manifest.json to data/exports/, then calls\n"
            "the gh CLI to create a new release on kuddukan42/losslessbob.\n"
            "No data is modified locally; user-only tables are dropped from the copy.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.publish_master_btn.setEnabled(False)
        self._publish_status_label.setText("Exporting master snapshot…")
        self._publish_status_label.setVisible(True)

        self._export_thread = _ExportMasterThread(self.flask_port)
        self._export_thread.finished.connect(self._on_export_done)
        self._export_thread.start()

    def _on_export_done(self, data: dict) -> None:
        """Handle export completion and kick off GitHub upload."""
        if not data.get("ok") or "error" in data:
            msg = data.get("message") or data.get("error") or "Unknown error"
            QMessageBox.warning(self, "Export Failed", msg)
            self._publish_status_label.setText(f"Export failed: {msg}")
            self.publish_master_btn.setEnabled(self.curator_cb.isChecked())
            return

        manifest = data.get("manifest", {})
        counts = manifest.get("lb_status_counts", {})
        rc = manifest.get("row_counts", {})
        version = manifest.get("master_version", "")
        db_path = data.get("path", "")
        manifest_path = data.get("manifest_path", "")
        prev_published_at = data.get("_prev_published_at")

        self._publish_status_label.setText(
            f"Export done ({manifest.get('size_bytes', 0):,} bytes) — uploading to GitHub…"
        )
        self._refresh_master_status_label()

        self._github_release_thread = _GithubReleaseThread(
            self.flask_port, db_path, manifest_path, version, prev_published_at,
        )
        self._github_release_thread.finished.connect(
            lambda result, m=manifest, c=counts, rc_=rc: self._on_github_release_done(result, m, c, rc_)
        )
        self._github_release_thread.start()

    def _on_github_release_done(self, result: dict, manifest: dict,
                                counts: dict, rc: dict) -> None:
        """Handle the GitHub release result and show a summary dialog."""
        self.publish_master_btn.setEnabled(self.curator_cb.isChecked())

        if "error" in result:
            err = result.get("message") or result.get("error")
            self._publish_status_label.setText(f"GitHub upload failed: {err}")
            QMessageBox.warning(
                self, "GitHub Upload Failed",
                f"{err}\n\nThe .db and .manifest.json files were saved to data/exports/.\n"
                "You can upload them manually to GitHub releases.",
            )
            return

        tag = result.get("tag", "?")
        url = result.get("url", "")
        self._publish_status_label.setText(f"Released: {tag}  {url}")

        QMessageBox.information(
            self, "Master Update Published",
            f"Version:     {manifest.get('master_version', '?')}\n"
            f"Tag:         {tag}\n"
            f"Size:        {manifest.get('size_bytes', 0):,} bytes\n"
            f"SHA256:      {(manifest.get('sha256') or '')[:16]}…\n\n"
            f"LB master:   {rc.get('lb_master', 0):,}\n"
            f"  Public:    {counts.get('public', 0):,}\n"
            f"  Private:   {counts.get('private', 0):,}\n"
            f"  Missing:   {counts.get('missing', 0):,}\n"
            f"Overrides:   {manifest.get('manual_override_count', 0)}\n\n"
            f"GitHub release:\n{url}",
        )

    def _on_install_master(self):
        """Pick a master snapshot from disk and apply it locally."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Master Snapshot",
            str(_DATA_DIR / "exports"),
            "Master DB (*.db);;All files (*)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Install Master Update?",
            f"Apply this master snapshot to your local database?\n\n"
            f"{path}\n\n"
            "An automatic backup of your current database will be taken first.\n"
            "Your collection, wishlist, credentials, and personal settings are preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.install_master_btn.setEnabled(False)
        self._install_thread = _InstallMasterThread(self.flask_port, path)
        self._install_thread.finished.connect(self._on_install_done)
        self._install_thread.start()

    def _on_install_done(self, data: dict) -> None:
        """Handle master install completion."""
        self.install_master_btn.setEnabled(True)
        if not data.get("ok") or "error" in data:
            msg = data.get("message") or data.get("error") or "Unknown error"
            QMessageBox.critical(self, "Install Failed", msg)
            return
        rc = data.get("row_counts", {})
        post = data.get("post_status_counts", {})
        QMessageBox.information(
            self, "Master Update Installed",
            f"Version:     {data.get('master_version', '?')}\n"
            f"Imported at: {data.get('imported_at', '?')[:19]}\n"
            f"Backup:      {data.get('backup_path', '?')}\n\n"
            f"Row counts after import:\n"
            f"  lb_master: {rc.get('lb_master', 0):,}\n"
            f"  checksums: {rc.get('checksums', 0):,}\n"
            f"  entries:   {rc.get('entries', 0):,}\n\n"
            f"Status distribution:\n"
            f"  Public:    {post.get('public', 0):,}\n"
            f"  Private:   {post.get('private', 0):,}\n"
            f"  Missing:   {post.get('missing', 0):,}\n\n"
            f"LB status changes vs. previous state: "
            f"{data.get('lb_status_changes', 0):,}"
        )
        self._refresh_master_status_label()
        try:
            self._refresh_stats()
        except Exception:
            pass

    def _on_open_folder(self):
        _DATA_DIR.mkdir(exist_ok=True)
        from gui.platform_utils import open_folder
        try:
            open_folder(_DATA_DIR)
        except Exception:
            pass

    def _on_purge(self, scope: str, label: str) -> None:
        if QMessageBox.question(
            self, "Confirm Purge",
            f"Permanently delete all: {label}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/purge",
                json={"scope": scope}, timeout=15,
            ).json()
            self.purge_status_label.setText(
                f"Purged: {label}" if resp.get("ok") else f"Error: {resp.get('error')}"
            )
            self.stats_changed.emit()
            self._refresh_collection_stats()
        except Exception as e:
            self.purge_status_label.setText(f"Error: {e}")

    def _check_sox(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/spectrogram/check",
                timeout=8,
            ).json()

            if r.get("sox_available"):
                self.sox_status_label.setText(f"OK — {r.get('sox_version', '')}")
                self.sox_status_label.setStyleSheet("color: green;")
            else:
                self.sox_status_label.setText(
                    "Not found — install: sudo apt install sox libsox-fmt-all"
                )
                self.sox_status_label.setStyleSheet("color: red;")

            if r.get("ffmpeg_available"):
                self.ffmpeg_status_label.setText("OK (SHN/APE/WV/M4A supported)")
                self.ffmpeg_status_label.setStyleSheet("color: green;")
            else:
                self.ffmpeg_status_label.setText(
                    "Not found — install: sudo apt install ffmpeg  (needed for SHN/APE/WV spectrograms)"
                )
                self.ffmpeg_status_label.setStyleSheet("color: orange;")

            if r.get("shntool_available"):
                self.shntool_status_label.setText(f"OK — {r.get('shntool_version', '')}")
                self.shntool_status_label.setStyleSheet("color: green;")
            else:
                self.shntool_status_label.setText(
                    "Not found — install: sudo apt install shntool  (needed for SHN verification)"
                )
                self.shntool_status_label.setStyleSheet("color: red;")

        except Exception as e:
            for lbl in (self.sox_status_label, self.ffmpeg_status_label, self.shntool_status_label):
                lbl.setText(f"Error: {e}")

    # ── qBittorrent handlers ─────────────────────────────────────────────────

    def _on_qbt_save(self):
        from backend.credentials import save_credentials, SERVICE_QBT, SERVICE_QBT_KEY
        key = self.qbt_api_key.text().strip()
        u = self.qbt_user.text().strip()
        p = self.qbt_pass.text()
        if not key and not u:
            self.qbt_status_label.setText("API key or username is required.")
            return
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={
                    "qbt_host": self.qbt_host.text().strip() or "localhost",
                    "qbt_port": str(self.qbt_port.value()),
                    "qbt_category": self.qbt_category.text().strip(),
                    "qbt_tags": self.qbt_tags.text().strip(),
                },
                timeout=5,
            )
        except Exception:
            pass
        if key:
            result = save_credentials(SERVICE_QBT_KEY, "api_key", key)
            self.qbt_status_label.setText(f"API key saved — {result.label}")
        else:
            result = save_credentials(SERVICE_QBT, u, p)
            self.qbt_status_label.setText(f"Username/password saved — {result.label}")

    def _on_qbt_test(self):
        self.qbt_test_btn.setEnabled(False)
        self.qbt_status_label.setText("Testing…")
        try:
            payload: dict = {
                "host": self.qbt_host.text().strip() or "localhost",
                "port": self.qbt_port.value(),
            }
            key = self.qbt_api_key.text().strip()
            if key:
                payload["api_key"] = key
            else:
                payload["username"] = self.qbt_user.text().strip()
                payload["password"] = self.qbt_pass.text()
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/qbt/test",
                json=payload,
                timeout=15,
            ).json()
            if resp.get("ok"):
                self.qbt_status_label.setText(f"Connected — qBittorrent {resp.get('version', '')}")
                self.qbt_status_label.setStyleSheet("color: green;")
            else:
                self.qbt_status_label.setText(f"Error: {resp.get('error', 'unknown')}")
                self.qbt_status_label.setStyleSheet("color: red;")
        except Exception as exc:
            self.qbt_status_label.setText(f"Error: {exc}")
            self.qbt_status_label.setStyleSheet("color: red;")
        finally:
            self.qbt_test_btn.setEnabled(True)

    def _on_qbt_clear(self):
        from backend.credentials import delete_credentials, SERVICE_QBT, SERVICE_QBT_KEY
        delete_credentials(SERVICE_QBT)
        delete_credentials(SERVICE_QBT_KEY)
        self.qbt_user.clear()
        self.qbt_pass.clear()
        self.qbt_api_key.clear()
        self.qbt_status_label.setText("Credentials cleared.")
        self.qbt_status_label.setStyleSheet("")

    def _load_qbt_settings(self):
        """Load qBittorrent host/port/category/tags from meta and credential status from keyring."""
        from backend.credentials import credentials_stored, get_credentials, SERVICE_QBT, SERVICE_QBT_KEY
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            ).json()
            self.qbt_host.setText(resp.get("qbt_host") or "localhost")
            self.qbt_port.setValue(int(resp.get("qbt_port") or 8080))
            self.qbt_category.setText(resp.get("qbt_category") or "")
            self.qbt_tags.setText(resp.get("qbt_tags") or "")
        except Exception:
            pass
        if credentials_stored(SERVICE_QBT_KEY):
            _, key = get_credentials(SERVICE_QBT_KEY)
            self.qbt_api_key.setText(key)
            self.qbt_status_label.setText("API key stored in keyring.")
        elif credentials_stored(SERVICE_QBT):
            u, p = get_credentials(SERVICE_QBT)
            self.qbt_user.setText(u)
            self.qbt_pass.setText(p)
            self.qbt_status_label.setText("Username/password stored in keyring.")

    # ── WTRF Forum handlers ──────────────────────────────────────────────────

    def _on_wtrf_save(self):
        from backend.credentials import save_credentials, SERVICE_WTRF
        u = self.wtrf_user.text().strip()
        p = self.wtrf_pass.text()
        if not u:
            self.wtrf_status_label.setText("Username is required.")
            return
        result = save_credentials(SERVICE_WTRF, u, p)
        self.wtrf_status_label.setText(result.label)

    def _on_wtrf_test(self):
        self.wtrf_test_btn.setEnabled(False)
        self.wtrf_status_label.setText("Testing…")
        self.wtrf_status_label.setStyleSheet("")
        self._wtrf_test_thread = _WtrfTestThread(
            self.flask_port,
            self.wtrf_user.text().strip(),
            self.wtrf_pass.text(),
        )
        self._wtrf_test_thread.finished.connect(self._on_wtrf_test_finished)
        self._wtrf_test_thread.start()

    def _on_wtrf_test_finished(self, result: dict) -> None:
        self.wtrf_test_btn.setEnabled(True)
        if result.get("ok"):
            self.wtrf_status_label.setText(f"Logged in as {result.get('username', '')}")
            self.wtrf_status_label.setStyleSheet("color: green;")
        else:
            self.wtrf_status_label.setText(f"Error: {result.get('error', 'unknown')}")
            self.wtrf_status_label.setStyleSheet("color: red;")

    def _on_wtrf_clear(self):
        from backend.credentials import delete_credentials, SERVICE_WTRF
        delete_credentials(SERVICE_WTRF)
        self.wtrf_user.clear()
        self.wtrf_pass.clear()
        self.wtrf_status_label.setText("Credentials cleared.")

    def _on_wtrf_board_changed(self, value: int) -> None:
        if self._loading:
            return
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"wtrf_board_id": str(value)},
                timeout=5,
            )
        except Exception:
            pass

    def _load_wtrf_settings(self):
        from backend.credentials import credentials_stored, get_credentials, SERVICE_WTRF
        if credentials_stored(SERVICE_WTRF):
            u, p = get_credentials(SERVICE_WTRF)
            self.wtrf_user.setText(u)
            self.wtrf_pass.setText(p)
            self.wtrf_status_label.setText("Credentials stored in keyring.")
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5)
            board_id = int(resp.json().get("wtrf_board_id") or 0)
            if board_id:
                self._loading = True
                try:
                    self.wtrf_board_spin.setValue(board_id)
                finally:
                    self._loading = False
        except Exception:
            pass

    # ── Torrent / tracker handlers ───────────────────────────────────────────

    def _on_tracker_list_changed(self, name: str) -> None:
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"tracker_list": name},
                timeout=5,
            )
        except Exception:
            pass

    def _on_refresh_trackers(self) -> None:
        self.refresh_trackers_btn.setEnabled(False)
        self.tracker_count_label.setText("Fetching…")
        try:
            list_name = self.tracker_list_combo.currentText()
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/trackers",
                params={"list_name": list_name, "force_refresh": "1"},
                timeout=20,
            ).json()
            count = resp.get("count", 0)
            self.tracker_count_label.setText(f"{count} trackers loaded")
            self.tracker_count_label.setStyleSheet("color: green;" if count else "color: red;")
        except Exception as exc:
            self.tracker_count_label.setText(f"Error: {exc}")
            self.tracker_count_label.setStyleSheet("color: red;")
        finally:
            self.refresh_trackers_btn.setEnabled(True)

    def _load_tracker_settings(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            ).json()
            name = resp.get("tracker_list") or "best"
            from backend.torrent_maker import TRACKER_LISTS
            if name in TRACKER_LISTS:
                self.tracker_list_combo.blockSignals(True)
                self.tracker_list_combo.setCurrentText(name)
                self.tracker_list_combo.blockSignals(False)
        except Exception:
            pass

    # ── Geocoding (curator only) ─────────────────────────────────────────────

    def _on_geocode_run(self) -> None:
        """Start the Nominatim geocoder in a background thread (curator only).

        POSTs to /api/geocode/run; starts a polling thread on success.
        """
        retry = self._geocode_retry_cb.isChecked()
        self._geocode_run_btn.setEnabled(False)
        self._geocode_status_label.setText("Status: starting…")

        self._geocode_run_thread = _GeocodeRunThread(self.flask_port, retry)
        self._geocode_run_thread.finished.connect(self._on_geocode_started)
        self._geocode_run_thread.start()

    def _on_geocode_started(self, result: dict) -> None:
        """Handle the immediate response from POST /api/geocode/run."""
        if result.get("status_code") == 409 or result.get("already_running"):
            self._geocode_status_label.setText("Status: already running")
            self._geocode_run_btn.setEnabled(True)
            return
        if "error" in result and "status_code" not in result:
            self._geocode_status_label.setText(f"Status: error — {result['error']}")
            self._geocode_run_btn.setEnabled(True)
            return
        # Geocoder started — begin polling
        self._geocode_status_label.setText("Status: running…")
        self._geocode_status_thread = _GeocodeStatusThread(self.flask_port)
        self._geocode_status_thread.status_update.connect(self._on_geocode_status)
        self._geocode_status_thread.start()

    def _on_geocode_status(self, status: dict) -> None:
        """Update the geocode progress label from a polling update.

        Args:
            status: JSON payload from GET /api/geocode/status.
        """
        running = status.get("running", False)
        done = status.get("done", 0)
        total = status.get("total", 0)
        current = status.get("current", "")
        errors = status.get("errors", 0)
        succeeded = status.get("succeeded", 0)
        stage = status.get("stage", "")

        if running:
            pct = int(done / total * 100) if total else 0
            progress_str = f"{done} / {total}  ({pct}%)"

            stage_hint = ""
            if stage == "querying":
                stage_hint = "querying Nominatim…"
            elif stage == "sleeping":
                stage_hint = "waiting (rate limit)…"
            elif stage == "saving":
                stage_hint = "saving…"
            elif stage == "starting":
                stage_hint = "starting…"

            eta_str = ""
            remaining = total - done
            if remaining > 0 and done > 0:
                eta_s = int(remaining * 1.1)
                if eta_s >= 3600:
                    eta_str = f"~{eta_s // 3600}h {(eta_s % 3600) // 60}m left"
                elif eta_s >= 60:
                    eta_str = f"~{eta_s // 60}m {eta_s % 60}s left"
                else:
                    eta_str = f"~{eta_s}s left"

            counts = f"{succeeded} ok  |  {errors} failed" if (succeeded + errors) > 0 else ""

            parts = [progress_str]
            if current:
                parts.append(current)
            if stage_hint:
                parts.append(stage_hint)
            if eta_str:
                parts.append(eta_str)
            if counts:
                parts.append(counts)
            self._geocode_status_label.setText("  ·  ".join(parts))
        else:
            if self._geocode_status_thread is not None:
                self._geocode_status_thread.stop()
                self._geocode_status_thread = None
            self._geocode_run_btn.setEnabled(True)
            self._geocode_status_label.setText(
                f"Done: {succeeded} geocoded, {errors} failed"
            )
            _log.info("Geocoder finished: %d geocoded, %d errors", succeeded, errors)
