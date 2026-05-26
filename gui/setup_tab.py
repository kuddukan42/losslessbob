import sys
from pathlib import Path

from backend.paths import DATA_DIR as _DATA_DIR
from gui.i18n import supported_languages

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
import gui.styles as styles

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


class _GitHubMasterThread(QThread):
    """Download the latest master snapshot from GitHub Releases and apply it.

    Emits progress(str) during download, finished(dict) on completion or error.
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    _GITHUB_API = "https://api.github.com/repos/kuddukan42/losslessbob/releases/latest"

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port

    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:
            self.finished.emit({"error": str(exc)})

    def _run_inner(self) -> None:
        import hashlib
        import json as _json

        # Step 1: fetch release metadata
        self.progress.emit("Checking GitHub for latest release…")
        api_resp = requests.get(
            self._GITHUB_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=15,
        )
        if api_resp.status_code == 404:
            self.finished.emit({"error": "No releases found on GitHub yet."})
            return
        api_resp.raise_for_status()
        release = api_resp.json()

        tag = release.get("tag_name", "?")
        assets = release.get("assets", [])

        db_asset = next(
            (a for a in assets
             if a["name"].endswith(".db") and not a["name"].endswith(".manifest.json.db")),
            None,
        )
        if not db_asset:
            self.finished.emit({"error": f"No .db asset found in release {tag}."})
            return

        manifest_name = db_asset["name"] + ".manifest.json"
        manifest_asset = next((a for a in assets if a["name"] == manifest_name), None)
        if not manifest_asset:
            self.finished.emit(
                {"error": f"Manifest sidecar '{manifest_name}' not found in release {tag}."}
            )
            return

        # Step 2: download manifest (small JSON, no progress needed)
        self.progress.emit(f"Downloading manifest for {tag}…")
        mresp = requests.get(manifest_asset["browser_download_url"], timeout=30)
        mresp.raise_for_status()
        manifest = mresp.json()

        # Step 3: stream-download the .db file with progress reporting
        dest_dir = _DATA_DIR / "imports"
        dest_dir.mkdir(parents=True, exist_ok=True)
        db_dest = dest_dir / db_asset["name"]
        manifest_dest = dest_dir / manifest_name

        total_bytes = db_asset.get("size", 0)
        total_mb = total_bytes / (1024 * 1024)
        self.progress.emit(
            f"Downloading {db_asset['name']} ({total_mb:.0f} MB)…"
        )
        dresp = requests.get(
            db_asset["browser_download_url"], stream=True, timeout=300
        )
        dresp.raise_for_status()

        downloaded = 0
        with open(db_dest, "wb") as fh:
            for chunk in dresp.iter_content(chunk_size=262144):  # 256 KB
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes:
                        pct = downloaded * 100 // total_bytes
                        dl_mb = downloaded / (1024 * 1024)
                        self.progress.emit(
                            f"Downloading… {pct}%  ({dl_mb:.1f} / {total_mb:.0f} MB)"
                        )

        # Step 4: verify SHA256
        self.progress.emit("Verifying checksum…")
        sha = hashlib.sha256()
        with open(db_dest, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
        actual_sha = sha.hexdigest()
        expected_sha = manifest.get("sha256", "")
        if actual_sha != expected_sha:
            db_dest.unlink(missing_ok=True)
            self.finished.emit(
                {"error": "SHA256 mismatch — download may be corrupt. Please try again."}
            )
            return

        # Step 5: save manifest sidecar so import_master_db() can find it
        with open(manifest_dest, "w", encoding="utf-8") as fh:
            _json.dump(manifest, fh, indent=2)

        # Step 6: apply via existing backend route
        self.progress.emit("Applying update to local database…")
        imp_resp = requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/master/import",
            json={"path": str(db_dest)},
            timeout=600,
        )
        self.finished.emit(imp_resp.json())


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
        self.setWindowTitle(self.tr("Flat File Update Available"))
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
        self._apply_btn = QPushButton(self.tr("Download && Apply"))
        self._apply_btn.clicked.connect(self._on_download_apply)
        btn_row.addWidget(self._apply_btn)

        self._defer_btn = QPushButton(self.tr("Defer 1 Day"))
        self._defer_btn.clicked.connect(self._on_defer)
        btn_row.addWidget(self._defer_btn)

        skip_btn = QPushButton(self.tr("Skip"))
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
            QMessageBox.warning(self, self.tr("Error"), self.tr("No release ID available."))
            return
        self._set_busy(True)
        self._status_lbl.setText(self.tr("Downloading zip…"))
        self._download_thread = _DownloadThread(self.flask_port, release_id)
        self._download_thread.finished.connect(self._on_downloaded)
        self._download_thread.start()

    def _on_downloaded(self, result: dict) -> None:
        if "error" in result:
            self._set_busy(False)
            self._status_lbl.setText(self.tr("Download failed: {}").format(result['error']))
            return
        # Fetch diff counts before applying
        release_id = self.release_info.get("id")
        self._status_lbl.setText(self.tr("Computing diff…"))
        try:
            diff_resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/flat_file/diff/{release_id}",
                timeout=60,
            )
            diff = diff_resp.json()
        except Exception as exc:
            self._set_busy(False)
            self._status_lbl.setText(self.tr("Diff failed: {}").format(exc))
            return

        if "error" in diff:
            self._set_busy(False)
            self._status_lbl.setText(self.tr("Diff error: {}").format(diff['error']))
            return

        msg = self.tr(
            "Ready to apply:\n"
            "  Added:   {0:,}\n"
            "  Changed: {1:,}\n"
            "  Removed: {2:,}\n\n"
            "Proceed?"
        ).format(
            diff.get('rows_added', 0),
            diff.get('rows_changed', 0),
            diff.get('rows_removed', 0),
        )
        ans = QMessageBox.question(
            self, self.tr("Confirm Apply"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self._set_busy(False)
            self._status_lbl.setText(self.tr("Apply cancelled."))
            return

        self._status_lbl.setText(self.tr("Applying release…"))
        self._apply_thread = _ApplyThread(self.flask_port, release_id)
        self._apply_thread.finished.connect(self._on_applied)
        self._apply_thread.start()

    def _on_applied(self, result: dict) -> None:
        self._set_busy(False)
        if "error" in result:
            self._status_lbl.setText(self.tr("Apply failed: {}").format(result['error']))
            return
        added = result.get("rows_added", 0)
        changed = result.get("rows_changed", 0)
        removed = result.get("rows_removed", 0)
        QMessageBox.information(
            self, self.tr("Update Applied"),
            self.tr("Flat file applied successfully.\nAdded: {0:,}  Changed: {1:,}  Removed: {2:,}").format(
                added, changed, removed),
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


class SetupTab(QWidget):
    stats_changed = pyqtSignal()
    search_page_size_changed = pyqtSignal(int)
    curator_mode_changed = pyqtSignal(bool)  # emitted when curator mode is toggled

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
        db_group = QGroupBox(self.tr("Database"))
        db_inner = QHBoxLayout(db_group)
        db_inner.setSpacing(16)

        # Left panel: archive stats and controls
        left_panel = QWidget()
        db_layout = QVBoxLayout(left_panel)
        db_layout.setContentsMargins(0, 0, 0, 0)

        db_sel_row = QHBoxLayout()
        db_sel_row.addWidget(QLabel(self.tr("Active database:")))
        self.db_combo = QComboBox()
        self.db_combo.addItems([self.tr("LosslessBob"), self.tr("Grateful Dead etree")])
        self.db_combo.currentIndexChanged.connect(self._on_db_changed)
        db_sel_row.addWidget(self.db_combo)
        db_sel_row.addStretch()
        db_layout.addLayout(db_sel_row)

        self.db_stats_label = QLabel(self.tr("Loading stats..."))
        db_layout.addWidget(self.db_stats_label)

        btn_row = QHBoxLayout()
        self.import_btn = QPushButton(self.tr("Import Database File..."))
        self.import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(self.import_btn)

        self.check_update_btn = QPushButton(self.tr("Check for Flat File Update"))
        self.check_update_btn.clicked.connect(self._on_check_update)
        btn_row.addWidget(self.check_update_btn)

        self.open_folder_btn = QPushButton(self.tr("Open Data Folder"))
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addStretch()
        db_layout.addLayout(btn_row)

        reset_row = QHBoxLayout()
        self.reset_btn = QPushButton(self.tr("Reset Database..."))
        self.reset_btn.setStyleSheet(
            f"QPushButton {{ background-color: {styles.FG_DANGER.name()}; color: {styles.HEADER_FG.name()}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {styles.ROW_FAIL.name()}; }}"
            f"QPushButton:disabled {{ background-color: {styles.FG_MUTED.name()}; }}"
        )
        self.reset_btn.setToolTip(self.tr("Drop all data and reinitialize the database from scratch"))
        self.reset_btn.clicked.connect(self._on_reset)
        reset_row.addWidget(self.reset_btn)
        reset_row.addStretch()
        db_layout.addLayout(reset_row)

        # External tool availability indicators
        sox_row = QHBoxLayout()
        sox_row.addWidget(QLabel(self.tr("SoX:")))
        self.sox_status_label = QLabel(self.tr("Checking…"))
        self.sox_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.sox_status_label.setOpenExternalLinks(True)
        sox_row.addWidget(self.sox_status_label)
        sox_row.addStretch()
        db_layout.addLayout(sox_row)

        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(QLabel(self.tr("ffmpeg:")))
        self.ffmpeg_status_label = QLabel(self.tr("Checking…"))
        self.ffmpeg_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.ffmpeg_status_label.setOpenExternalLinks(True)
        ffmpeg_row.addWidget(self.ffmpeg_status_label)
        ffmpeg_row.addStretch()
        db_layout.addLayout(ffmpeg_row)

        shntool_row = QHBoxLayout()
        shntool_row.addWidget(QLabel(self.tr("shntool:")))
        self.shntool_status_label = QLabel(self.tr("Checking…"))
        self.shntool_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.shntool_status_label.setOpenExternalLinks(True)
        shntool_row.addWidget(self.shntool_status_label)
        self.sox_check_btn = QPushButton(self.tr("Re-check"))
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
            self.tr("<b>Data Management</b> — purge operations remove user data only; "
            "the checksum archive is never affected.")
        ))

        # User-data stats (collection, wishlist, etc.)
        self.coll_stats_label = QLabel("Loading…")
        self.coll_stats_label.setStyleSheet(f"font-size:11px; color:{styles.FG_MUTED.name()};")
        purge_layout.addWidget(self.coll_stats_label)

        purge_items = [
            (self.tr("My Collection (+ ratings, alerts)"), "collection"),
            (self.tr("Wishlist"),                          "wishlist"),
            (self.tr("Personal Ratings and Tags only"),    "personal_meta"),
            (self.tr("Watchdog Alerts"),                   "integrity_events"),
            (self.tr("Scrape Diff Changelog"),             "entry_changes"),
        ]
        purge_grid = QGridLayout()
        purge_grid.setVerticalSpacing(4)
        for i, (label, scope) in enumerate(purge_items):
            lbl = QLabel(label)
            btn = QPushButton(self.tr("Purge…"))
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
        master_group = QGroupBox(self.tr("Master Data"))
        master_layout = QVBoxLayout(master_group)

        curator_row = QHBoxLayout()
        self.curator_cb = QCheckBox(self.tr("Curator mode (publish-enabled)"))
        self.curator_cb.setToolTip(
            self.tr("Enable to publish master-data snapshots that ship to other users.\n"
            "Curator status is stored locally and never included in any export.")
        )
        curator_row.addWidget(self.curator_cb)
        curator_row.addStretch()
        master_layout.addLayout(curator_row)

        self.master_status_label = QLabel(self.tr("Master version: (not yet published)"))
        master_layout.addWidget(self.master_status_label)

        master_btn_row = QHBoxLayout()
        self.publish_master_btn = QPushButton(self.tr("Publish Master Update…"))
        self.publish_master_btn.setToolTip(
            self.tr("Build a master-only snapshot (.db + .manifest.json) in data/exports/. "
            "Strips all user data, verifies, computes SHA256, writes manifest.")
        )
        self.publish_master_btn.clicked.connect(self._on_publish_master)
        self.publish_master_btn.setEnabled(False)  # toggled by curator checkbox
        # Connect after publish_master_btn exists so _on_curator_toggled cannot
        # fire before its dependent widget is ready.
        self.curator_cb.toggled.connect(self._on_curator_toggled)
        master_btn_row.addWidget(self.publish_master_btn)

        self.check_github_btn = QPushButton(self.tr("Check for Updates"))
        self.check_github_btn.setToolTip(
            self.tr("Download and install the latest master snapshot from the "
            "GitHub releases page. Requires an internet connection.")
        )
        self.check_github_btn.clicked.connect(self._on_check_github)
        master_btn_row.addWidget(self.check_github_btn)

        self.install_master_btn = QPushButton(self.tr("Install from File…"))
        self.install_master_btn.setToolTip(
            self.tr("Apply a master snapshot from a local .db file. Your collection, "
            "wishlist, credentials, and personal settings are preserved.")
        )
        self.install_master_btn.clicked.connect(self._on_install_master)
        master_btn_row.addWidget(self.install_master_btn)
        master_btn_row.addStretch()
        master_layout.addLayout(master_btn_row)

        self._gh_progress_label = QLabel("")
        self._gh_progress_label.setVisible(False)
        master_layout.addWidget(self._gh_progress_label)

        self._publish_status_label = QLabel("")
        self._publish_status_label.setVisible(False)
        master_layout.addWidget(self._publish_status_label)

        layout.addWidget(master_group)

        # Search settings section
        search_group = QGroupBox(self.tr("Search"))
        search_layout = QVBoxLayout(search_group)
        page_size_row = QHBoxLayout()
        page_size_row.addWidget(QLabel(self.tr("Results per page:")))
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
        cw_group = QGroupBox(self.tr("Column Widths"))
        cw_layout = QVBoxLayout(cw_group)

        self._cw_status_label = QLabel(self.tr("User defaults: none (factory widths will be used)"))
        cw_layout.addWidget(self._cw_status_label)

        cw_btn_row = QHBoxLayout()
        self._save_defaults_btn = QPushButton(self.tr("Save as Defaults"))
        self._save_defaults_btn.setToolTip(
            self.tr("Snapshot current column widths as your personal defaults")
        )
        self._save_defaults_btn.clicked.connect(self._on_save_col_defaults)
        cw_btn_row.addWidget(self._save_defaults_btn)

        self._restore_defaults_btn = QPushButton(self.tr("Restore My Defaults"))
        self._restore_defaults_btn.setToolTip(
            self.tr("Apply your saved column-width defaults to all tables")
        )
        self._restore_defaults_btn.setEnabled(False)
        self._restore_defaults_btn.clicked.connect(self._on_restore_col_defaults)
        cw_btn_row.addWidget(self._restore_defaults_btn)

        self._restore_factory_btn = QPushButton(self.tr("Restore Factory"))
        self._restore_factory_btn.setToolTip(
            self.tr("Reset all column widths to factory defaults and clear your saved layout")
        )
        self._restore_factory_btn.clicked.connect(self._on_restore_factory_defaults)
        cw_btn_row.addWidget(self._restore_factory_btn)
        cw_btn_row.addStretch()
        cw_layout.addLayout(cw_btn_row)

        layout.addWidget(cw_group)

        # ── Preferences ──────────────────────────────────────────────────────────
        pref_group = QGroupBox(self.tr("Preferences"))
        pref_layout = QVBoxLayout(pref_group)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(self.tr("Interface language:")))
        self._lang_combo = QComboBox()
        self._lang_combo.setFixedWidth(160)
        for code, name in supported_languages():
            self._lang_combo.addItem(name, code)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        pref_layout.addLayout(lang_row)

        self._lang_restart_label = QLabel(self.tr("Restart the app to apply the new language."))
        self._lang_restart_label.setStyleSheet(f"color: {styles.FG_WARNING.name()}; font-size: 11px;")
        self._lang_restart_label.setVisible(False)
        pref_layout.addWidget(self._lang_restart_label)

        layout.addWidget(pref_group)

        # ── Connection settings (scraper controls moved to Scraper tab) ─────────
        conn_row = QHBoxLayout()
        conn_row.setSpacing(12)

        # ── qBittorrent section ──────────────────────────────────────────────
        qbt_group = QGroupBox(self.tr("qBittorrent"))
        qbt_layout = QGridLayout(qbt_group)
        qbt_layout.setHorizontalSpacing(8)
        qbt_layout.setVerticalSpacing(6)

        qbt_layout.addWidget(QLabel(self.tr("Host:")), 0, 0)
        self.qbt_host = QLineEdit("localhost")
        self.qbt_host.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_host, 0, 1)

        qbt_layout.addWidget(QLabel(self.tr("Port:")), 0, 2)
        self.qbt_port = QSpinBox()
        self.qbt_port.setRange(1, 65535)
        self.qbt_port.setValue(8080)
        self.qbt_port.setFixedWidth(80)
        qbt_layout.addWidget(self.qbt_port, 0, 3)

        qbt_layout.addWidget(QLabel(self.tr("Username:")), 1, 0)
        self.qbt_user = QLineEdit()
        self.qbt_user.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_user, 1, 1)

        qbt_layout.addWidget(QLabel(self.tr("Password:")), 1, 2)
        self.qbt_pass = QLineEdit()
        self.qbt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.qbt_pass.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_pass, 1, 3)

        qbt_layout.addWidget(QLabel(self.tr("API Key:")), 2, 0)
        self.qbt_api_key = QLineEdit()
        self.qbt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.qbt_api_key.setPlaceholderText(self.tr("qBittorrent 5+ — takes priority over username/password"))
        self.qbt_api_key.setFixedWidth(380)
        qbt_layout.addWidget(self.qbt_api_key, 2, 1, 1, 3)

        qbt_layout.addWidget(QLabel(self.tr("Category:")), 3, 0)
        self.qbt_category = QLineEdit()
        self.qbt_category.setPlaceholderText(self.tr("e.g. losslessbob (optional)"))
        self.qbt_category.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_category, 3, 1)

        qbt_layout.addWidget(QLabel(self.tr("Tags:")), 3, 2)
        self.qbt_tags = QLineEdit()
        self.qbt_tags.setPlaceholderText(self.tr("comma-separated (optional)"))
        self.qbt_tags.setFixedWidth(180)
        qbt_layout.addWidget(self.qbt_tags, 3, 3)

        qbt_btn_row = QHBoxLayout()
        self.qbt_save_btn = QPushButton(self.tr("Save Credentials"))
        self.qbt_save_btn.clicked.connect(self._on_qbt_save)
        qbt_btn_row.addWidget(self.qbt_save_btn)
        self.qbt_test_btn = QPushButton(self.tr("Test Connection"))
        self.qbt_test_btn.clicked.connect(self._on_qbt_test)
        qbt_btn_row.addWidget(self.qbt_test_btn)
        self.qbt_clear_btn = QPushButton(self.tr("Clear Credentials"))
        self.qbt_clear_btn.clicked.connect(self._on_qbt_clear)
        qbt_btn_row.addWidget(self.qbt_clear_btn)
        qbt_btn_row.addStretch()
        qbt_layout.addLayout(qbt_btn_row, 4, 0, 1, 5)

        self.qbt_status_label = QLabel("")
        qbt_layout.addWidget(self.qbt_status_label, 5, 0, 1, 5)
        qbt_layout.setColumnStretch(4, 1)
        conn_row.addWidget(qbt_group, stretch=1)

        # ── WTRF Forum section ───────────────────────────────────────────────
        wtrf_group = QGroupBox(self.tr("Watching the River Flow Forum"))
        wtrf_layout = QGridLayout(wtrf_group)
        wtrf_layout.setHorizontalSpacing(8)
        wtrf_layout.setVerticalSpacing(6)

        wtrf_layout.addWidget(QLabel(self.tr("Username:")), 0, 0)
        self.wtrf_user = QLineEdit()
        self.wtrf_user.setFixedWidth(200)
        wtrf_layout.addWidget(self.wtrf_user, 0, 1)

        wtrf_layout.addWidget(QLabel(self.tr("Password:")), 1, 0)
        self.wtrf_pass = QLineEdit()
        self.wtrf_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.wtrf_pass.setFixedWidth(200)
        wtrf_layout.addWidget(self.wtrf_pass, 1, 1)

        wtrf_layout.addWidget(QLabel(self.tr("Board ID:")), 2, 0)
        self.wtrf_board_spin = QSpinBox()
        self.wtrf_board_spin.setRange(1, 9999)
        self.wtrf_board_spin.setFixedWidth(80)
        self.wtrf_board_spin.setToolTip(self.tr("SMF board number from the forum URL (e.g. ?board=42.0 → 42)"))
        self.wtrf_board_spin.valueChanged.connect(self._on_wtrf_board_changed)
        wtrf_layout.addWidget(self.wtrf_board_spin, 2, 1)

        wtrf_btn_row = QHBoxLayout()
        self.wtrf_save_btn = QPushButton(self.tr("Save Credentials"))
        self.wtrf_save_btn.clicked.connect(self._on_wtrf_save)
        wtrf_btn_row.addWidget(self.wtrf_save_btn)
        self.wtrf_test_btn = QPushButton(self.tr("Test Connection"))
        self.wtrf_test_btn.clicked.connect(self._on_wtrf_test)
        wtrf_btn_row.addWidget(self.wtrf_test_btn)
        self.wtrf_clear_btn = QPushButton(self.tr("Clear Credentials"))
        self.wtrf_clear_btn.clicked.connect(self._on_wtrf_clear)
        wtrf_btn_row.addWidget(self.wtrf_clear_btn)
        wtrf_btn_row.addStretch()
        wtrf_layout.addLayout(wtrf_btn_row, 3, 0, 1, 3)

        self.wtrf_status_label = QLabel("")
        wtrf_layout.addWidget(self.wtrf_status_label, 4, 0, 1, 3)
        wtrf_layout.setColumnStretch(2, 1)
        conn_row.addWidget(wtrf_group, stretch=1)

        # ── Torrent section ──────────────────────────────────────────────────
        torrent_group = QGroupBox(self.tr("Torrent Settings"))
        torrent_layout = QHBoxLayout(torrent_group)

        torrent_layout.addWidget(QLabel(self.tr("Tracker list:")))
        self.tracker_list_combo = QComboBox()
        from backend.torrent_maker import TRACKER_LISTS
        self.tracker_list_combo.addItems(TRACKER_LISTS)
        self.tracker_list_combo.currentTextChanged.connect(self._on_tracker_list_changed)
        torrent_layout.addWidget(self.tracker_list_combo)

        self.refresh_trackers_btn = QPushButton(self.tr("Refresh Trackers"))
        self.refresh_trackers_btn.clicked.connect(self._on_refresh_trackers)
        torrent_layout.addWidget(self.refresh_trackers_btn)

        self.tracker_count_label = QLabel("—")
        torrent_layout.addWidget(self.tracker_count_label)
        torrent_layout.addStretch()
        conn_row.addWidget(torrent_group, stretch=1)

        # ── Web GUI password section (TODO-065) ──────────────────────────────
        web_pw_group = QGroupBox(self.tr("Web GUI Access"))
        web_pw_layout = QGridLayout(web_pw_group)
        web_pw_layout.setHorizontalSpacing(8)
        web_pw_layout.setVerticalSpacing(6)

        web_pw_layout.addWidget(QLabel(self.tr("Password:")), 0, 0)
        self.web_password_edit = QLineEdit()
        self.web_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.web_password_edit.setPlaceholderText(self.tr("Leave empty to disable auth"))
        self.web_password_edit.setFixedWidth(200)
        web_pw_layout.addWidget(self.web_password_edit, 0, 1)

        web_pw_btn_row = QHBoxLayout()
        self.web_pw_save_btn = QPushButton(self.tr("Save"))
        self.web_pw_save_btn.clicked.connect(self._on_web_password_save)
        web_pw_btn_row.addWidget(self.web_pw_save_btn)
        self.web_pw_clear_btn = QPushButton(self.tr("Clear"))
        self.web_pw_clear_btn.clicked.connect(self._on_web_password_clear)
        web_pw_btn_row.addWidget(self.web_pw_clear_btn)
        web_pw_btn_row.addStretch()
        web_pw_layout.addLayout(web_pw_btn_row, 1, 0, 1, 2)

        self.web_pw_status_label = QLabel("")
        web_pw_layout.addWidget(self.web_pw_status_label, 2, 0, 1, 2)
        web_pw_layout.setColumnStretch(1, 1)
        conn_row.addWidget(web_pw_group, stretch=1)

        layout.addLayout(conn_row)

        # ── Flat File History ────────────────────────────────────────────────
        ff_group = QGroupBox(self.tr("Flat File History"))
        ff_layout = QVBoxLayout(ff_group)

        self._ff_history_table = QTableWidget(0, 6)
        self._ff_history_table.setHorizontalHeaderLabels(
            [self.tr("Detected"), self.tr("Filename"), self.tr("Status"),
             self.tr("Added"), self.tr("Changed"), self.tr("Removed")]
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
            self.tr("User defaults: saved") if has
            else self.tr("User defaults: none (factory widths will be used)")
        )

    def _on_save_col_defaults(self) -> None:
        if self._state_store is None:
            return
        self._state_store.save_user_defaults()
        self._cw_status_label.setText(self.tr("Layout saved as defaults."))
        self._restore_defaults_btn.setEnabled(True)

    def _on_restore_col_defaults(self) -> None:
        if self._state_store is None:
            return
        self._state_store.restore_user_defaults()
        self._cw_status_label.setText(self.tr("Defaults restored."))

    def _on_restore_factory_defaults(self) -> None:
        if self._state_store is None:
            return
        if QMessageBox.question(
            self, self.tr("Restore Factory Defaults"),
            self.tr("Reset all column widths to factory defaults?\n\nThis will clear your saved layout."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._state_store.restore_factory_defaults()
        self._cw_status_label.setText(self.tr("User defaults: none (factory widths will be used)"))
        self._restore_defaults_btn.setEnabled(False)

    def _load_settings(self):
        self._loading = True
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5)
            data = resp.json()
            self.search_page_spin.setValue(int(data.get("search_page_size") or 50))
            self._load_language_setting(data.get("ui_language") or "en")
        except Exception:
            pass
        finally:
            self._loading = False
        # Load credential-dependent settings after _loading flag is cleared
        self._load_qbt_settings()
        self._load_wtrf_settings()
        self._load_tracker_settings()
        self._load_web_password_status()

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

    def _load_language_setting(self, lang_code: str) -> None:
        """Set the language combo to the saved value without triggering a save."""
        codes = [self._lang_combo.itemData(i) for i in range(self._lang_combo.count())]
        idx = codes.index(lang_code) if lang_code in codes else 0
        self._lang_combo.blockSignals(True)
        self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.blockSignals(False)

    def _on_language_changed(self, _index: int) -> None:
        """Persist the selected language and show the restart notice."""
        if self._loading:
            return
        lang_code = self._lang_combo.currentData()
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"ui_language": lang_code},
                timeout=5,
            )
        except Exception:
            pass
        self._lang_restart_label.setVisible(True)

    def _refresh_stats(self):
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5)
            stats = resp.json()
            self.db_stats_label.setText(
                self.tr(
                    "Total checksums: {0:,}  |  LB entries: {1:,}  |  "
                    "Latest LB: {2}  |  Last import: {3}"
                ).format(
                    stats.get('total_checksums', 0),
                    stats.get('total_lb_numbers', 0),
                    stats.get('latest_lb', self.tr('N/A')),
                    stats.get('last_import', self.tr('Never')),
                )
            )
        except Exception:
            self.db_stats_label.setText(self.tr("Could not load database stats."))
        self._refresh_collection_stats()

    def _refresh_collection_stats(self):
        _TABLE_LABELS = {
            "my_collection":   self.tr("My Collection"),
            "my_wishlist":     self.tr("Wishlist"),
            "collection_meta": self.tr("Personal Ratings"),
            "integrity_events": self.tr("Watchdog Events"),
            "entry_changes":   self.tr("Scrape Diff Rows"),
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
            self.coll_stats_label.setText(self.tr("Could not load collection stats."))

    def _on_db_changed(self, index):
        pass

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select flat file"), str(Path.home()),
            self.tr("Database files (*.txt);;All files (*)")
        )
        if not path:
            return

        self.import_btn.setEnabled(False)
        self.import_status_label.setText(self.tr("Starting import…"))
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
            self.import_status_label.setText(self.tr("Error: {}").format(result['error']))
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
                self.import_status_label.setText(
                    self.tr("Import failed: {}").format(status.get('error', self.tr('unknown error')))
                )
            elif stage == "done":
                if "Already imported" in msg:
                    self.import_status_label.setText(self.tr("Already imported — file unchanged since last run."))
                else:
                    new_lbs = status.get("new_lb_count", 0)
                    self.import_status_label.setText(
                        self.tr("Import complete — {} new LB entries added.").format(new_lbs)
                    )
                    self._refresh_stats()
                    self.stats_changed.emit()

    def _on_reset(self):
        confirm = QMessageBox.warning(
            self,
            self.tr("Reset Database"),
            self.tr("This will permanently delete ALL checksums, entries, and scraped data "
            "and reinitialize the database from scratch.\n\n"
            "This cannot be undone. Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.reset_btn.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.import_status_label.setText(self.tr("Resetting database..."))

        self._reset_thread = _ResetThread(self.flask_port)
        self._reset_thread.finished.connect(self._on_reset_finished)
        self._reset_thread.start()

    def _on_reset_finished(self, result):
        self.reset_btn.setEnabled(True)
        self.import_btn.setEnabled(True)
        self.import_progress.setVisible(False)
        if "error" in result:
            self.import_status_label.setText(self.tr("Reset failed: {}").format(result['error']))
        else:
            self.import_status_label.setText(self.tr("Database reset. Ready for a fresh import."))
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
                self, self.tr("Check Update"),
                self.tr("Discovery failed:\n{}").format(data['error']),
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
                self, self.tr("Up to Date"),
                self.tr("Your flat file is up to date.{}").format(last_info),
            )
            return
        dlg = _UpdateAvailableDialog(
            release_info=data["current_release"],
            last_applied=data.get("last_applied_release"),
            flask_port=self.flask_port,
            parent=self,
        )
        dlg.exec()
        # Refresh history panel and stats after dialog closes (update may have been applied)
        self._load_flat_file_history()
        self._refresh_stats()
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
            "applied": styles.STATUS_OK,
            "applied_legacy": styles.STATUS_OK,
            "detected": styles.STATUS_WARN,
            "downloaded": styles.STATUS_NEUTRAL,
            "deferred": styles.STATUS_NEUTRAL,
            "failed": styles.STATUS_ERROR,
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
        self.curator_mode_changed.emit(enabled)
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
                suffix = self.tr("  (published {})").format(published[:19]) if published else ""
                self.master_status_label.setText(
                    self.tr("Master version: {}").format(version) + suffix
                )
            else:
                self.master_status_label.setText(
                    self.tr("Master version: (not yet published or imported)")
                )
        except Exception as e:
            self.master_status_label.setText(self.tr("Master version: (unknown — {})").format(e))

    def _on_curator_toggled(self, checked: bool):
        """Persist the curator flag and gate the Publish button.

        The geocoder group (on the Map tab) is gated indirectly via
        curator_mode_changed → map_tab.set_curator_mode.
        """
        _log = logging.getLogger(__name__)
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/curator",
                json={"enabled": bool(checked)}, timeout=5,
            )
            if not resp.ok:
                try:
                    err_msg = resp.json().get("error", resp.text)
                except Exception:
                    err_msg = resp.text
                raise RuntimeError(err_msg)
            self.publish_master_btn.setEnabled(bool(checked))
            self.curator_mode_changed.emit(bool(checked))
        except Exception as e:
            _log.exception("Curator toggle failed (checked=%s)", checked)
            QMessageBox.warning(self, self.tr("Curator Mode"), self.tr("Could not update flag: {}").format(e))
            # Revert UI to the actual server state
            self._load_curator_status()

    def _on_publish_master(self) -> None:
        """Build a master export then upload to GitHub releases."""
        confirm = QMessageBox.question(
            self, self.tr("Publish Master Update?"),
            self.tr("Build a master-only snapshot and upload it to GitHub releases?\n\n"
            "This writes a .db and .manifest.json to data/exports/, then calls\n"
            "the gh CLI to create a new release on kuddukan42/losslessbob.\n"
            "No data is modified locally; user-only tables are dropped from the copy."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.publish_master_btn.setEnabled(False)
        self._publish_status_label.setText(self.tr("Exporting master snapshot…"))
        self._publish_status_label.setVisible(True)

        self._export_thread = _ExportMasterThread(self.flask_port)
        self._export_thread.finished.connect(self._on_export_done)
        self._export_thread.start()

    def _on_export_done(self, data: dict) -> None:
        """Handle export completion and kick off GitHub upload."""
        if not data.get("ok") or "error" in data:
            msg = data.get("message") or data.get("error") or "Unknown error"
            QMessageBox.warning(self, self.tr("Export Failed"), msg)
            self._publish_status_label.setText(self.tr("Export failed: {}").format(msg))
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
            self.tr("Export done ({} bytes) — uploading to GitHub…").format(f"{manifest.get('size_bytes', 0):,}")
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
            self._publish_status_label.setText(self.tr("GitHub upload failed: {}").format(err))
            QMessageBox.warning(
                self, self.tr("GitHub Upload Failed"),
                self.tr("{}\n\nThe .db and .manifest.json files were saved to data/exports/.\n"
                "You can upload them manually to GitHub releases.").format(err),
            )
            return

        tag = result.get("tag", "?")
        url = result.get("url", "")
        self._publish_status_label.setText(self.tr("Released: {0}  {1}").format(tag, url))

        QMessageBox.information(
            self, self.tr("Master Update Published"),
            self.tr(
                "Version:     {version}\n"
                "Tag:         {tag}\n"
                "Size:        {size:,} bytes\n"
                "SHA256:      {sha256}…\n\n"
                "LB master:   {lb_master:,}\n"
                "  Public:    {public:,}\n"
                "  Private:   {private_:,}\n"
                "  Missing:   {missing:,}\n"
                "Overrides:   {overrides}\n\n"
                "GitHub release:\n{url}"
            ).format(
                version=manifest.get('master_version', '?'),
                tag=tag,
                size=manifest.get('size_bytes', 0),
                sha256=(manifest.get('sha256') or '')[:16],
                lb_master=rc.get('lb_master', 0),
                public=counts.get('public', 0),
                private_=counts.get('private', 0),
                missing=counts.get('missing', 0),
                overrides=manifest.get('manual_override_count', 0),
                url=url,
            ),
        )

    def _on_check_github(self) -> None:
        """Download and install the latest master snapshot from GitHub Releases."""
        confirm = QMessageBox.question(
            self, self.tr("Check for Updates"),
            self.tr("Download the latest master snapshot from GitHub?\n\n"
                    "This will fetch release metadata, download the snapshot (~50–200 MB), "
                    "verify its checksum, and apply it to your local database.\n\n"
                    "Your collection, wishlist, and personal settings are preserved."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.check_github_btn.setEnabled(False)
        self.install_master_btn.setEnabled(False)
        self._gh_progress_label.setText(self.tr("Connecting to GitHub…"))
        self._gh_progress_label.setVisible(True)
        self._gh_thread = _GitHubMasterThread(self.flask_port)
        self._gh_thread.progress.connect(self._on_github_progress)
        self._gh_thread.finished.connect(self._on_github_done)
        self._gh_thread.start()

    def _on_github_progress(self, msg: str) -> None:
        """Update the progress label during a GitHub download."""
        self._gh_progress_label.setText(msg)

    def _on_github_done(self, data: dict) -> None:
        """Handle GitHub download + install completion."""
        self.check_github_btn.setEnabled(True)
        self.install_master_btn.setEnabled(True)
        self._gh_progress_label.setVisible(False)
        self._on_install_done(data)

    def _on_install_master(self):
        """Pick a master snapshot from disk and apply it locally."""
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select Master Snapshot"),
            str(_DATA_DIR / "exports"),
            self.tr("Master DB (*.db);;All files (*)"),
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, self.tr("Install Master Update?"),
            self.tr("Apply this master snapshot to your local database?\n\n"
            "{}\n\n"
            "An automatic backup of your current database will be taken first.\n"
            "Your collection, wishlist, credentials, and personal settings are preserved.").format(path),
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
            msg = data.get("message") or data.get("error") or self.tr("Unknown error")
            QMessageBox.critical(self, self.tr("Install Failed"), msg)
            return
        rc = data.get("row_counts", {})
        post = data.get("post_status_counts", {})
        QMessageBox.information(
            self, self.tr("Master Update Installed"),
            self.tr(
                "Version:     {version}\n"
                "Imported at: {imported_at}\n"
                "Backup:      {backup}\n\n"
                "Row counts after import:\n"
                "  lb_master: {lb_master:,}\n"
                "  checksums: {checksums:,}\n"
                "  entries:   {entries:,}\n\n"
                "Status distribution:\n"
                "  Public:    {public:,}\n"
                "  Private:   {private_:,}\n"
                "  Missing:   {missing:,}\n\n"
                "LB status changes vs. previous state: {lb_changes:,}"
            ).format(
                version=data.get('master_version', '?'),
                imported_at=(data.get('imported_at', '?') or '')[:19],
                backup=data.get('backup_path', '?'),
                lb_master=rc.get('lb_master', 0),
                checksums=rc.get('checksums', 0),
                entries=rc.get('entries', 0),
                public=post.get('public', 0),
                private_=post.get('private', 0),
                missing=post.get('missing', 0),
                lb_changes=data.get('lb_status_changes', 0),
            )
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
        except Exception as exc:
            _log.warning("open_folder failed: %s", exc)

    def _on_purge(self, scope: str, label: str) -> None:
        if QMessageBox.question(
            self, self.tr("Confirm Purge"),
            self.tr("Permanently delete all: {}\n\nThis cannot be undone.").format(label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection/purge",
                json={"scope": scope}, timeout=15,
            ).json()
            self.purge_status_label.setText(
                self.tr("Purged: {}").format(label) if resp.get("ok")
                else self.tr("Error: {}").format(resp.get('error'))
            )
            self.stats_changed.emit()
            self._refresh_collection_stats()
        except Exception as e:
            self.purge_status_label.setText(self.tr("Error: {}").format(e))

    # ── Platform-aware install hints ─────────────────────────────────────────

    @staticmethod
    def _sox_tool_hint(tool: str) -> str:
        """Return an HTML install hint for *tool* tailored to the current OS.

        Args:
            tool: one of ``"sox"``, ``"ffmpeg"``, or ``"shntool"``.

        Returns:
            A short HTML string with a command snippet and a clickable
            download link, ready for a RichText QLabel.
        """
        is_win   = sys.platform == "win32"
        is_mac   = sys.platform == "darwin"

        hints = {
            "sox": {
                "win":   ('winget install SoX.SoX',
                          'https://sox.sourceforge.net',
                          'sox.sourceforge.net'),
                "mac":   ('brew install sox', None, None),
                "linux": ('sudo apt install sox libsox-fmt-all', None, None),
            },
            "ffmpeg": {
                "win":   ('winget install Gyan.FFmpeg',
                          'https://ffmpeg.org/download.html',
                          'ffmpeg.org'),
                "mac":   ('brew install ffmpeg', None, None),
                "linux": ('sudo apt install ffmpeg', None, None),
            },
            "shntool": {
                # shntool has no native Windows package — offer WSL fallback + choco
                "win":   (None,
                          'http://www.etree.org/shnutils/shntool/',
                          'etree.org/shnutils/shntool'),
                "mac":   ('brew install shntool', None, None),
                "linux": ('sudo apt install shntool', None, None),
            },
        }

        key = "win" if is_win else ("mac" if is_mac else "linux")
        cmd, url, link_text = hints[tool][key]

        parts = []
        if tool == "shntool" and is_win:
            # Special-case: no winget/choco package; recommend WSL or Chocolatey
            parts.append("No native Windows package — try "
                         "<code>wsl apt install shntool</code> or "
                         "<code>choco install shntool</code> (Chocolatey).")
        elif cmd:
            parts.append(f"install: <code>{cmd}</code>")
        if url:
            parts.append(f'<a href="{url}">{link_text}</a>')

        return "Not found — " + "  |  ".join(parts) if parts else "Not found"

    def _check_sox(self):
        try:
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/spectrogram/check",
                timeout=8,
            ).json()

            if r.get("sox_available"):
                self.sox_status_label.setText(self.tr("OK — {}").format(r.get('sox_version', '')))
                self.sox_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.sox_status_label.setText(self._sox_tool_hint("sox"))
                self.sox_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")

            if r.get("ffmpeg_available"):
                self.ffmpeg_status_label.setText(self.tr("OK (SHN/APE/WV/M4A supported)"))
                self.ffmpeg_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.ffmpeg_status_label.setText(
                    self._sox_tool_hint("ffmpeg")
                    + self.tr("  (needed for SHN/APE/WV spectrograms)")
                )
                self.ffmpeg_status_label.setStyleSheet(f"color: {styles.FG_WARNING.name()};")

            if r.get("shntool_available"):
                self.shntool_status_label.setText(self.tr("OK — {}").format(r.get('shntool_version', '')))
                self.shntool_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.shntool_status_label.setText(
                    self._sox_tool_hint("shntool")
                    + self.tr("  (needed for SHN verification)")
                )
                self.shntool_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")

        except Exception as e:
            for lbl in (self.sox_status_label, self.ffmpeg_status_label, self.shntool_status_label):
                lbl.setText(self.tr("Error: {}").format(e))

    # ── qBittorrent handlers ─────────────────────────────────────────────────

    def _on_qbt_save(self):
        from backend.credentials import save_credentials, SERVICE_QBT, SERVICE_QBT_KEY
        key = self.qbt_api_key.text().strip()
        u = self.qbt_user.text().strip()
        p = self.qbt_pass.text()
        if not key and not u:
            self.qbt_status_label.setText(self.tr("API key or username is required."))
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
            self.qbt_status_label.setText(self.tr("API key saved — {}").format(result.label))
        else:
            result = save_credentials(SERVICE_QBT, u, p)
            self.qbt_status_label.setText(self.tr("Username/password saved — {}").format(result.label))

    def _on_qbt_test(self):
        self.qbt_test_btn.setEnabled(False)
        self.qbt_status_label.setText(self.tr("Testing…"))
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
                self.qbt_status_label.setText(
                    self.tr("Connected — qBittorrent {}").format(resp.get('version', ''))
                )
                self.qbt_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.qbt_status_label.setText(
                    self.tr("Error: {}").format(resp.get('error', self.tr('unknown')))
                )
                self.qbt_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")
        except Exception as exc:
            self.qbt_status_label.setText(self.tr("Error: {}").format(exc))
            self.qbt_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")
        finally:
            self.qbt_test_btn.setEnabled(True)

    def _on_qbt_clear(self):
        from backend.credentials import delete_credentials, SERVICE_QBT, SERVICE_QBT_KEY
        delete_credentials(SERVICE_QBT)
        delete_credentials(SERVICE_QBT_KEY)
        self.qbt_user.clear()
        self.qbt_pass.clear()
        self.qbt_api_key.clear()
        self.qbt_status_label.setText(self.tr("Credentials cleared."))
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
            self.qbt_status_label.setText(self.tr("API key stored in keyring."))
        elif credentials_stored(SERVICE_QBT):
            u, p = get_credentials(SERVICE_QBT)
            self.qbt_user.setText(u)
            self.qbt_pass.setText(p)
            self.qbt_status_label.setText(self.tr("Username/password stored in keyring."))

    # ── WTRF Forum handlers ──────────────────────────────────────────────────

    def _on_wtrf_save(self):
        from backend.credentials import save_credentials, SERVICE_WTRF
        u = self.wtrf_user.text().strip()
        p = self.wtrf_pass.text()
        if not u:
            self.wtrf_status_label.setText(self.tr("Username is required."))
            return
        result = save_credentials(SERVICE_WTRF, u, p)
        self.wtrf_status_label.setText(result.label)

    def _on_wtrf_test(self):
        self.wtrf_test_btn.setEnabled(False)
        self.wtrf_status_label.setText(self.tr("Testing…"))
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
            self.wtrf_status_label.setText(
                self.tr("Logged in as {}").format(result.get('username', ''))
            )
            self.wtrf_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
        else:
            self.wtrf_status_label.setText(
                self.tr("Error: {}").format(result.get('error', self.tr('unknown')))
            )
            self.wtrf_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")

    def _on_wtrf_clear(self):
        from backend.credentials import delete_credentials, SERVICE_WTRF
        delete_credentials(SERVICE_WTRF)
        self.wtrf_user.clear()
        self.wtrf_pass.clear()
        self.wtrf_status_label.setText(self.tr("Credentials cleared."))

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
            self.wtrf_status_label.setText(self.tr("Credentials stored in keyring."))
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

    # ── Web GUI password handlers (TODO-065) ────────────────────────────────

    def _on_web_password_save(self) -> None:
        pw = self.web_password_edit.text()
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"web_password": pw},
                timeout=5,
            )
            if pw:
                self.web_pw_status_label.setText(self.tr("Password set — web UI requires login."))
                self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.web_pw_status_label.setText(self.tr("Password cleared — web UI is open access."))
                self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_WARNING.name()};")
            self.web_password_edit.clear()
        except Exception as exc:
            self.web_pw_status_label.setText(self.tr("Error: {}").format(exc))
            self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")

    def _on_web_password_clear(self) -> None:
        self.web_password_edit.clear()
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={"web_password": ""},
                timeout=5,
            )
            self.web_pw_status_label.setText(self.tr("Password cleared — web UI is open access."))
            self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_WARNING.name()};")
        except Exception as exc:
            self.web_pw_status_label.setText(self.tr("Error: {}").format(exc))
            self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")

    def _load_web_password_status(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            ).json()
            if resp.get("web_password") == "set":
                self.web_pw_status_label.setText(self.tr("Password set — web UI requires login."))
                self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};")
            else:
                self.web_pw_status_label.setText(self.tr("No password — web UI is open access."))
                self.web_pw_status_label.setStyleSheet(f"color: {styles.FG_WARNING.name()};")
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
        self.tracker_count_label.setText(self.tr("Fetching…"))
        try:
            list_name = self.tracker_list_combo.currentText()
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/trackers",
                params={"list_name": list_name, "force_refresh": "1"},
                timeout=20,
            ).json()
            count = resp.get("count", 0)
            self.tracker_count_label.setText(self.tr("{} trackers loaded").format(count))
            self.tracker_count_label.setStyleSheet(f"color: {styles.FG_SUCCESS.name()};" if count else f"color: {styles.FG_DANGER.name()};")
        except Exception as exc:
            self.tracker_count_label.setText(self.tr("Error: {}").format(exc))
            self.tracker_count_label.setStyleSheet(f"color: {styles.FG_DANGER.name()};")
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

            _log.info("Geocoder finished: %d geocoded, %d errors", succeeded, errors)
