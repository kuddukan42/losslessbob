import os
import subprocess
import sys
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QComboBox, QCheckBox, QSpinBox, QProgressBar,
    QFileDialog, QMessageBox, QLineEdit, QPlainTextEdit,
)


class _ImportThread(QThread):
    progress = pyqtSignal(str)
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
                timeout=300,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


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

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._import_thread = None
        self._reset_thread = None
        self._single_scrape_thread = None
        self._scrape_status_thread = None
        self._build_ui()
        self._load_settings()
        self._refresh_stats()

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

        layout.addWidget(db_group)

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

        scrape_btn_row = QHBoxLayout()
        self.scrape_all_btn = QPushButton("Scrape All Missing Entries")
        self.scrape_all_btn.clicked.connect(self._on_scrape_all)
        scrape_btn_row.addWidget(self.scrape_all_btn)

        self.stop_scrape_btn = QPushButton("Stop Scraper")
        self.stop_scrape_btn.clicked.connect(self._on_stop_scrape)
        self.stop_scrape_btn.setEnabled(False)
        scrape_btn_row.addWidget(self.stop_scrape_btn)
        scrape_btn_row.addStretch()
        scraper_layout.addLayout(scrape_btn_row)

        single_scrape_row = QHBoxLayout()
        single_scrape_row.addWidget(QLabel("Scrape single entry:"))
        self.single_lb_input = QLineEdit()
        self.single_lb_input.setPlaceholderText("LB number...")
        self.single_lb_input.setFixedWidth(100)
        self.single_lb_input.returnPressed.connect(self._on_scrape_single)
        single_scrape_row.addWidget(self.single_lb_input)
        self.scrape_single_btn = QPushButton("Scrape")
        self.scrape_single_btn.clicked.connect(self._on_scrape_single)
        single_scrape_row.addWidget(self.scrape_single_btn)
        self.single_scrape_status_label = QLabel("")
        single_scrape_row.addWidget(self.single_scrape_status_label)
        single_scrape_row.addStretch()
        scraper_layout.addLayout(single_scrape_row)

        range_scrape_row = QHBoxLayout()
        range_scrape_row.addWidget(QLabel("Scrape range:"))
        self.range_start_spin = QSpinBox()
        self.range_start_spin.setRange(1, 99999)
        self.range_start_spin.setValue(1)
        self.range_start_spin.setFixedWidth(80)
        range_scrape_row.addWidget(self.range_start_spin)
        range_scrape_row.addWidget(QLabel("to"))
        self.range_end_spin = QSpinBox()
        self.range_end_spin.setRange(1, 99999)
        self.range_end_spin.setValue(100)
        self.range_end_spin.setFixedWidth(80)
        range_scrape_row.addWidget(self.range_end_spin)
        self.scrape_range_btn = QPushButton("Scrape Range")
        self.scrape_range_btn.clicked.connect(self._on_scrape_range)
        range_scrape_row.addWidget(self.scrape_range_btn)
        self.fill_gaps_cb = QCheckBox("Mark sequential gaps as MISSING")
        self.fill_gaps_cb.setToolTip(
            "For LB numbers in the range not present in the checksum database, "
            "insert a MISSING placeholder entry so they appear in search results."
        )
        range_scrape_row.addWidget(self.fill_gaps_cb)
        range_scrape_row.addStretch()
        scraper_layout.addLayout(range_scrape_row)

        self.scrape_progress = QProgressBar()
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
        layout.addWidget(log_group)

        layout.addStretch()

    def _load_settings(self):
        try:
            resp = requests.get(f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5)
            data = resp.json()
            self.auto_scrape_cb.setChecked(data.get("auto_scrape", "1") != "0")
            self.download_files_cb.setChecked(data.get("scrape_attachments", "1") != "0")
            self.force_scrape_cb.setChecked(data.get("force_scrape", "0") != "0")
            self.delay_spin.setValue(int(data.get("scrape_delay_ms") or 1500))
        except Exception:
            self.auto_scrape_cb.setChecked(True)
            self.download_files_cb.setChecked(True)

    def _save_settings(self):
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={
                    "auto_scrape": "1" if self.auto_scrape_cb.isChecked() else "0",
                    "scrape_attachments": "1" if self.download_files_cb.isChecked() else "0",
                    "force_scrape": "1" if self.force_scrape_cb.isChecked() else "0",
                    "scrape_delay_ms": str(self.delay_spin.value()),
                },
                timeout=5,
            )
        except Exception:
            pass

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
        self.import_status_label.setText("Importing...")

        self._import_thread = _ImportThread(self.flask_port, path)
        self._import_thread.finished.connect(self._on_import_finished)
        self._import_thread.start()

    def _on_import_finished(self, result):
        self.import_btn.setEnabled(True)
        if "error" in result:
            self.import_status_label.setText(f"Error: {result['error']}")
        elif result.get("skipped"):
            self.import_status_label.setText("Import skipped — file already imported.")
        else:
            self.import_status_label.setText(
                f"Import complete. {result.get('new_lb_count', 0)} new LB entries added."
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
        if "error" in result:
            self.import_status_label.setText(f"Reset failed: {result['error']}")
        else:
            self.import_status_label.setText("Database reset. Ready for a fresh import.")
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
        data_dir = Path(__file__).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(data_dir))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(data_dir)])
        else:
            subprocess.run(["xdg-open", str(data_dir)])

    def _log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.scraper_log.appendPlainText(f"[{ts}] {msg}")

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
        running = status.get("running", False)
        skipped = status.get("skipped", 0)
        last_action = status.get("last_action")

        if total > 0:
            self.scrape_progress.setRange(0, total)
            self.scrape_progress.setValue(done)

        if current:
            action_word = "Skipped" if last_action == "skipped" else "Scraping"
            label = f"{action_word} LB-{current} ({done}/{total}"
            if skipped:
                label += f", {skipped} skipped"
            label += ")..."
            self.scrape_status_label.setText(label)
            if current != self._last_logged_lb:
                self._last_logged_lb = current
                if last_action == "skipped":
                    self._log(f"Skipped LB-{current} — already complete ({done}/{total})")
                else:
                    self._log(f"Scraped LB-{current} ({done}/{total})")

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
