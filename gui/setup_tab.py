from pathlib import Path

from backend.paths import LOG_FILE as _LOG_FILE, DATA_DIR as _DATA_DIR

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QCheckBox, QSpinBox, QProgressBar,
    QFileDialog, QMessageBox, QLineEdit, QPlainTextEdit,
)


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


class SetupTab(QWidget):
    stats_changed = pyqtSignal()
    search_page_size_changed = pyqtSignal(int)

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._loading = False
        self._import_thread = None
        self._import_status_thread = None
        self._reset_thread = None
        self._single_scrape_thread = None
        self._scrape_status_thread = None
        self._build_ui()
        self._load_settings()
        self._refresh_stats()
        self._refresh_log_size()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Database section
        db_group = QGroupBox("Database")
        db_layout = QVBoxLayout(db_group)

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

        self.check_update_btn = QPushButton("Check for Update")
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

        self.import_status_label = QLabel("")
        db_layout.addWidget(self.import_status_label)

        self.import_progress = QProgressBar()
        self.import_progress.setObjectName("importProgress")
        self.import_progress.setVisible(False)
        db_layout.addWidget(self.import_progress)

        layout.addWidget(db_group)

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

        # Scraper section
        scraper_group = QGroupBox("Web Scraper")
        scraper_layout = QVBoxLayout(scraper_group)

        self.auto_scrape_cb = QCheckBox("Automatically scrape new entries after import")
        self.auto_scrape_cb.stateChanged.connect(self._save_settings)
        scraper_layout.addWidget(self.auto_scrape_cb)

        self.download_files_cb = QCheckBox("Download attachment files (ffp, txt, html)")
        self.download_files_cb.stateChanged.connect(self._save_settings)
        scraper_layout.addWidget(self.download_files_cb)

        self.force_scrape_cb = QCheckBox("Force re-scrape (ignore already-complete entries)")
        self.force_scrape_cb.stateChanged.connect(self._save_settings)
        scraper_layout.addWidget(self.force_scrape_cb)

        self.local_pages_cb = QCheckBox("Use local pages for metadata (data/pages/)")
        self.local_pages_cb.stateChanged.connect(self._save_settings)
        scraper_layout.addWidget(self.local_pages_cb)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("Delay between requests (ms):"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(500, 10000)
        self.delay_spin.setValue(1500)
        self.delay_spin.setSingleStep(100)
        self.delay_spin.valueChanged.connect(self._save_settings)
        delay_row.addWidget(self.delay_spin)
        delay_row.addStretch()
        scraper_layout.addLayout(delay_row)

        _VC = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        scrape_grid = QGridLayout()
        scrape_grid.setColumnStretch(4, 1)
        scrape_grid.setHorizontalSpacing(8)
        scrape_grid.setVerticalSpacing(10)

        # Row 0: bulk actions — button in col 2 so it lines up with single/range
        _SCRAPE_BTN_W = 180
        self.scrape_all_btn = QPushButton("Scrape All Missing Entries")
        self.scrape_all_btn.setFixedWidth(_SCRAPE_BTN_W)
        self.scrape_all_btn.clicked.connect(self._on_scrape_all)
        scrape_grid.addWidget(self.scrape_all_btn, 0, 2, _VC)

        self.stop_scrape_btn = QPushButton("Stop Scraper")
        self.stop_scrape_btn.setFixedWidth(_SCRAPE_BTN_W)
        self.stop_scrape_btn.clicked.connect(self._on_stop_scrape)
        self.stop_scrape_btn.setEnabled(False)
        scrape_grid.addWidget(self.stop_scrape_btn, 0, 3, _VC)

        # Row 1: single entry
        scrape_grid.addWidget(QLabel("Single entry:"), 1, 0, _VC)
        self.single_lb_input = QLineEdit()
        self.single_lb_input.setPlaceholderText("LB number...")
        self.single_lb_input.setFixedWidth(100)
        self.single_lb_input.returnPressed.connect(self._on_scrape_single)
        scrape_grid.addWidget(self.single_lb_input, 1, 1, _VC)
        self.scrape_single_btn = QPushButton("Scrape")
        self.scrape_single_btn.setFixedWidth(_SCRAPE_BTN_W)
        self.scrape_single_btn.clicked.connect(self._on_scrape_single)
        scrape_grid.addWidget(self.scrape_single_btn, 1, 2, _VC)
        self.single_scrape_status_label = QLabel("")
        scrape_grid.addWidget(self.single_scrape_status_label, 1, 3, 1, 2, _VC)

        # Row 2: range
        scrape_grid.addWidget(QLabel("Range:"), 2, 0, _VC)
        range_inputs_w = QWidget()
        range_inputs = QHBoxLayout(range_inputs_w)
        range_inputs.setContentsMargins(0, 0, 0, 0)
        range_inputs.setSpacing(4)
        self.range_start_spin = QSpinBox()
        self.range_start_spin.setRange(1, 99999)
        self.range_start_spin.setValue(1)
        self.range_start_spin.setFixedWidth(80)
        range_inputs.addWidget(self.range_start_spin)
        range_inputs.addWidget(QLabel("to"))
        self.range_end_spin = QSpinBox()
        self.range_end_spin.setRange(1, 99999)
        self.range_end_spin.setValue(100)
        self.range_end_spin.setFixedWidth(80)
        range_inputs.addWidget(self.range_end_spin)
        scrape_grid.addWidget(range_inputs_w, 2, 1, _VC)
        self.scrape_range_btn = QPushButton("Scrape Range")
        self.scrape_range_btn.setFixedWidth(_SCRAPE_BTN_W)
        self.scrape_range_btn.clicked.connect(self._on_scrape_range)
        scrape_grid.addWidget(self.scrape_range_btn, 2, 2, _VC)
        self.fill_gaps_cb = QCheckBox("Skip LB numbers with no checksum data")
        self.fill_gaps_cb.setToolTip(
            "For LB numbers in the range not present in the checksum database, "
            "insert a MISSING placeholder entry so they appear in search results."
        )
        scrape_grid.addWidget(self.fill_gaps_cb, 2, 3, 1, 2, _VC)

        scraper_layout.addLayout(scrape_grid)

        self.scrape_progress = QProgressBar()
        self.scrape_progress.setObjectName("scrapeProgress")
        self.scrape_progress.setVisible(False)
        scraper_layout.addWidget(self.scrape_progress)

        self.scrape_status_label = QLabel("")
        scraper_layout.addWidget(self.scrape_status_label)

        layout.addWidget(scraper_group)

        log_group = QGroupBox("Scraper Log")
        log_layout = QVBoxLayout(log_group)
        self.scraper_log = QPlainTextEdit()
        self.scraper_log.setReadOnly(True)
        self.scraper_log.setMaximumBlockCount(500)
        self.scraper_log.setFixedHeight(150)
        log_layout.addWidget(self.scraper_log)

        log_file_row = QHBoxLayout()
        self.log_size_label = QLabel("Log file: —")
        log_file_row.addWidget(self.log_size_label)
        log_file_row.addStretch()
        self.open_log_btn = QPushButton("Open Log File")
        self.open_log_btn.clicked.connect(self._on_open_log)
        log_file_row.addWidget(self.open_log_btn)
        self.purge_log_btn = QPushButton("Purge Log")
        self.purge_log_btn.clicked.connect(self._on_purge_log)
        log_file_row.addWidget(self.purge_log_btn)
        log_layout.addLayout(log_file_row)

        layout.addWidget(log_group)

        layout.addStretch()

    def _load_settings(self):
        self._loading = True
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5)
            data = resp.json()
            self.auto_scrape_cb.setChecked(data.get("auto_scrape", "1") != "0")
            self.download_files_cb.setChecked(data.get("scrape_attachments", "1") != "0")
            self.force_scrape_cb.setChecked(data.get("force_scrape", "0") != "0")
            self.local_pages_cb.setChecked(data.get("use_local_pages", "0") == "1")
            self.delay_spin.setValue(int(data.get("scrape_delay_ms") or 1500))
            self.search_page_spin.setValue(int(data.get("search_page_size") or 50))
        except Exception:
            self.auto_scrape_cb.setChecked(True)
            self.download_files_cb.setChecked(True)
        finally:
            self._loading = False

    def _save_settings(self):
        if self._loading:
            return
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={
                    "auto_scrape": "1" if self.auto_scrape_cb.isChecked() else "0",
                    "scrape_attachments": "1" if self.download_files_cb.isChecked() else "0",
                    "force_scrape": "1" if self.force_scrape_cb.isChecked() else "0",
                    "use_local_pages": "1" if self.local_pages_cb.isChecked() else "0",
                    "scrape_delay_ms": str(self.delay_spin.value()),
                    "search_page_size": str(self.search_page_spin.value()),
                },
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

    def _on_check_update(self):
        self.check_update_btn.setEnabled(False)
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/check_update", timeout=30)
            data = resp.json()
            if "error" in data:
                QMessageBox.warning(self, "Check Update", f"Error: {data['error']}")
            elif data.get("update_available"):
                QMessageBox.information(
                    self, "Update Available",
                    f"Local latest: LB-{data['local_latest']}\n"
                    f"Site latest: LB-{data['site_latest']}\n\n"
                    "A newer database is available. Download from the LosslessBob site."
                )
            else:
                QMessageBox.information(
                    self, "Up to Date",
                    f"Your database is up to date (LB-{data.get('local_latest', '?')})."
                )
        except Exception as e:
            QMessageBox.warning(self, "Check Update", f"Could not check for updates: {e}")
        finally:
            self.check_update_btn.setEnabled(True)

    def _on_open_folder(self):
        _DATA_DIR.mkdir(exist_ok=True)
        from gui.platform_utils import open_folder
        try:
            open_folder(_DATA_DIR)
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.scraper_log.appendPlainText(line)
        try:
            _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        self._refresh_log_size()

    def _refresh_log_size(self) -> None:
        try:
            size = _LOG_FILE.stat().st_size
            if size < 1024:
                text = f"{size} B"
            elif size < 1_048_576:
                text = f"{size / 1024:.1f} KB"
            else:
                text = f"{size / 1_048_576:.1f} MB"
            self.log_size_label.setText(f"Log file: {text}")
        except FileNotFoundError:
            self.log_size_label.setText("Log file: not created yet")
        except OSError:
            self.log_size_label.setText("Log file: error reading size")

    def _on_purge_log(self) -> None:
        confirm = QMessageBox.question(
            self, "Purge Log",
            "Clear the scraper log file on disk? The in-app log will also be cleared.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            _LOG_FILE.write_text("", encoding="utf-8")
        except OSError:
            pass
        self.scraper_log.clear()
        self._refresh_log_size()

    def _on_open_log(self) -> None:
        if not _LOG_FILE.exists():
            QMessageBox.information(self, "Open Log", "Log file has not been created yet.")
            return
        from gui.platform_utils import open_file
        try:
            open_file(_LOG_FILE)
        except Exception:
            pass

    def _on_scrape_single(self):
        text = self.single_lb_input.text().strip()
        try:
            lb = int(text)
        except ValueError:
            self.single_scrape_status_label.setText("Invalid number.")
            return
        self.scrape_single_btn.setEnabled(False)
        self.single_scrape_status_label.setText(f"Scraping LB-{lb}...")
        self._log(f"Starting single scrape: LB-{lb}")
        self._single_scrape_thread = _SingleScrapeThread(self.flask_port, lb, force=self.force_scrape_cb.isChecked())
        self._single_scrape_thread.finished.connect(self._on_single_scrape_finished)
        self._single_scrape_thread.start()

    def _on_single_scrape_finished(self, data):
        self.scrape_single_btn.setEnabled(True)
        lb = self.single_lb_input.text().strip()
        if "error" in data:
            msg = f"Error scraping LB-{lb}: {data['error']}"
            self.single_scrape_status_label.setText(f"Error: {data['error']}")
        elif data.get("skipped"):
            msg = f"LB-{lb} already scraped (skipped)."
            self.single_scrape_status_label.setText(msg)
        else:
            n = len(data.get("files_downloaded", []))
            msg = f"LB-{lb} scraped. {n} file(s) downloaded."
            self.single_scrape_status_label.setText(msg)
        self._log(msg)

    def _on_scrape_range(self):
        start = self.range_start_spin.value()
        end = self.range_end_spin.value()
        if end < start:
            self.scrape_status_label.setText("End must be >= start.")
            return
        self.scrape_range_btn.setEnabled(False)
        self.scrape_all_btn.setEnabled(False)
        self.stop_scrape_btn.setEnabled(True)
        self.scrape_progress.setVisible(True)
        self.scrape_progress.setRange(0, 0)
        fill_gaps = self.fill_gaps_cb.isChecked()
        force = self.force_scrape_cb.isChecked()
        self.scrape_status_label.setText(f"Starting range scrape LB-{start} to LB-{end}...")
        self._log(f"Starting range scrape: LB-{start} to LB-{end}{' (fill gaps)' if fill_gaps else ''}{' (force)' if force else ''}")

        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/start",
                json={"start_lb": start, "end_lb": end, "force": force, "fill_gaps": fill_gaps},
                timeout=10,
            )
        except Exception as e:
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start range scrape: {e}")
            self.scrape_range_btn.setEnabled(True)
            self.scrape_all_btn.setEnabled(True)
            self.stop_scrape_btn.setEnabled(False)
            return

        self._scrape_status_thread = _ScrapeStatusThread(self.flask_port)
        self._scrape_status_thread.status_update.connect(self._on_scrape_status)
        self._scrape_status_thread.start()

    def _on_scrape_all(self):
        self.scrape_all_btn.setEnabled(False)
        self.stop_scrape_btn.setEnabled(True)
        self.scrape_progress.setVisible(True)
        self.scrape_progress.setRange(0, 0)
        force = self.force_scrape_cb.isChecked()
        self.scrape_status_label.setText("Starting scraper...")
        self._log(f"Starting bulk scrape of all missing entries{' (force)' if force else ''}...")

        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/start",
                json={"start_lb": 1, "force": force},
                timeout=10,
            )
        except Exception as e:
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start scraper: {e}")
            self.scrape_all_btn.setEnabled(True)
            return

        self._scrape_status_thread = _ScrapeStatusThread(self.flask_port)
        self._scrape_status_thread.status_update.connect(self._on_scrape_status)
        self._scrape_status_thread.start()

    _last_logged_lb = None

    def _on_scrape_status(self, status):
        total = status.get("total", 0)
        done = status.get("done", 0)
        current = status.get("current_lb", "")
        last_lb = status.get("last_lb")
        running = status.get("running", False)
        skipped = status.get("skipped", 0)
        last_action = status.get("last_action")
        last_source = status.get("last_source")

        if total > 0:
            self.scrape_progress.setRange(0, total)
            self.scrape_progress.setValue(done)

        # Status label shows what is currently being processed
        if current:
            label = f"Scraping LB-{current} ({done}/{total}"
            if skipped:
                label += f", {skipped} skipped"
            label += ")..."
            self.scrape_status_label.setText(label)

        # Log the just-completed entry (last_lb) so the source tag is always correct
        if last_lb and last_lb != self._last_logged_lb:
            self._last_logged_lb = last_lb
            if last_action == "skipped":
                self._log(f"Skipped LB-{last_lb} — already complete ({done}/{total})")
            elif last_action == "error":
                self._log(f"Error scraping LB-{last_lb} ({done}/{total})")
            else:
                src = f" [{last_source}]" if last_source else ""
                self._log(f"Scraped LB-{last_lb}{src} ({done}/{total})")

        if not running:
            self._scrape_status_thread.stop()
            self.scrape_all_btn.setEnabled(True)
            self.scrape_range_btn.setEnabled(True)
            self.stop_scrape_btn.setEnabled(False)
            self.scrape_progress.setVisible(False)
            msg = f"Scrape complete. {done} processed"
            if skipped:
                msg += f" ({skipped} already complete)"
            msg += f", {status.get('errors', 0)} errors."
            self.scrape_status_label.setText(msg)
            self._log(msg)
            self._last_logged_lb = None

    def _on_stop_scrape(self):
        try:
            requests.post(f"http://127.0.0.1:{self.flask_port}/api/scrape/stop", timeout=5)
        except Exception:
            pass
        self.stop_scrape_btn.setEnabled(False)
        self.scrape_status_label.setText("Stop requested...")
        self._log("Stop requested by user.")
