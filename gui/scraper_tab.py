"""Scraper tab — site mirror crawler, entry metadata scraper, bootleg catalog.

Sub-panels (top to bottom in a scroll area):
  1. Site Mirror Crawler   — full-domain BFS spider, If-Modified-Since, live status
  2. Crawler Session History — table of past crawl runs
  3. Site Inventory           — filtered/paginated site_inventory table
  4. Entry Pages & Metadata  — per-LB detail scraper (single, range, all, private)
  5. Bootleg Catalog (LBBCD) — bootleg index scraper + history
"""
from __future__ import annotations

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QComboBox,
    QCheckBox, QSpinBox, QProgressBar, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QScrollArea, QMessageBox, QFrame,
)
from PyQt6.QtGui import QColor

from backend.paths import SITE_DETAIL_DIR as _SITE_DETAIL_DIR


# ── Background threads ─────────────────────────────────────────────────────────

class _CrawlerStatusThread(QThread):
    """Polls /api/crawler/status every second."""
    status_update = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/crawler/status",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(1000)

    def stop(self) -> None:
        self._running = False


class _ScrapeStatusThread(QThread):
    """Polls /api/scrape/status every second."""
    status_update = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/scrape/status",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(1000)

    def stop(self) -> None:
        self._running = False


class _SingleScrapeThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, lb_number: int, force: bool = False) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.lb_number = lb_number
        self.force = force

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/entry/{self.lb_number}/scrape",
                json={"force": self.force},
                timeout=30,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.finished.emit({"error": str(e)})


# ── Main tab widget ────────────────────────────────────────────────────────────

class ScraperTab(QWidget):
    """Tab containing all scraping functionality."""

    def __init__(self, flask_port: int, parent=None) -> None:
        super().__init__(parent)
        self.flask_port = flask_port

        # Thread handles
        self._crawler_status_thread: _CrawlerStatusThread | None = None
        self._scrape_status_thread: _ScrapeStatusThread | None = None
        self._single_scrape_thread: _SingleScrapeThread | None = None

        # State flags
        self._page_download_mode = False
        self._private_rescrape_mode = False
        self._private_rescrape_before = 0
        self._last_logged_lb = None

        # Inventory pagination
        self._inv_offset = 0
        self._inv_limit = 100
        self._inv_total = 0

        self._build_ui()
        self._load_crawler_settings()
        self._refresh_pages_count()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._load_bootlegs_history()
        self._load_sessions_history()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(content)

        layout.addWidget(self._build_crawler_group())
        layout.addWidget(self._build_sessions_group())
        layout.addWidget(self._build_inventory_group())
        layout.addWidget(self._build_entry_scraper_group())
        layout.addWidget(self._build_bootlegs_group())
        layout.addStretch()

    # ── Panel 1: Site Mirror Crawler ──────────────────────────────────────────

    def _build_crawler_group(self) -> QGroupBox:
        group = QGroupBox("Site Mirror Crawler")
        layout = QVBoxLayout(group)

        # Controls row
        ctrl_row = QHBoxLayout()

        ctrl_row.addWidget(QLabel("Scope:"))
        self._scope_combo = QComboBox()
        self._scope_combo.addItems(["incremental", "full"])
        self._scope_combo.setFixedWidth(120)
        ctrl_row.addWidget(self._scope_combo)

        self._crawler_force_cb = QCheckBox("Force re-fetch")
        self._crawler_force_cb.setToolTip("Re-download pages even when If-Modified-Since says unchanged")
        ctrl_row.addWidget(self._crawler_force_cb)

        ctrl_row.addWidget(QLabel("Delay (ms):"))
        self._crawler_delay_spin = QSpinBox()
        self._crawler_delay_spin.setRange(500, 10000)
        self._crawler_delay_spin.setValue(1500)
        self._crawler_delay_spin.setSingleStep(100)
        self._crawler_delay_spin.setFixedWidth(80)
        self._crawler_delay_spin.valueChanged.connect(self._save_crawler_settings)
        ctrl_row.addWidget(self._crawler_delay_spin)

        ctrl_row.addWidget(QLabel("Daily cap:"))
        self._crawler_cap_spin = QSpinBox()
        self._crawler_cap_spin.setRange(100, 50000)
        self._crawler_cap_spin.setValue(5000)
        self._crawler_cap_spin.setSingleStep(500)
        self._crawler_cap_spin.setFixedWidth(80)
        self._crawler_cap_spin.valueChanged.connect(self._save_crawler_settings)
        ctrl_row.addWidget(self._crawler_cap_spin)

        ctrl_row.addStretch()

        self._crawler_start_btn = QPushButton("Start Crawl")
        self._crawler_start_btn.setFixedWidth(110)
        self._crawler_start_btn.clicked.connect(self._on_crawler_start)
        ctrl_row.addWidget(self._crawler_start_btn)

        self._crawler_stop_btn = QPushButton("Stop")
        self._crawler_stop_btn.setFixedWidth(80)
        self._crawler_stop_btn.setEnabled(False)
        self._crawler_stop_btn.clicked.connect(self._on_crawler_stop)
        ctrl_row.addWidget(self._crawler_stop_btn)

        layout.addLayout(ctrl_row)

        # Progress bar
        self._crawler_progress = QProgressBar()
        self._crawler_progress.setRange(0, 0)
        self._crawler_progress.setVisible(False)
        layout.addWidget(self._crawler_progress)

        # Status label — shows current URL being processed
        self._crawler_url_label = QLabel("Idle")
        self._crawler_url_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        self._crawler_url_label.setWordWrap(True)
        layout.addWidget(self._crawler_url_label)

        # Count summary label
        self._crawler_counts_label = QLabel("")
        self._crawler_counts_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self._crawler_counts_label)

        return group

    # ── Panel 2: Session History ───────────────────────────────────────────────

    def _build_sessions_group(self) -> QGroupBox:
        group = QGroupBox("Crawler Session History")
        layout = QVBoxLayout(group)

        self._sessions_table = QTableWidget(0, 7)
        self._sessions_table.setHorizontalHeaderLabels(
            ["Started", "Finished", "Scope", "Status", "Fetched", "304", "Failed"]
        )
        hdr = self._sessions_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, 7):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._sessions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._sessions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._sessions_table.setMinimumHeight(90)
        self._sessions_table.setMaximumHeight(160)
        layout.addWidget(self._sessions_table)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self._load_sessions_history)
        refresh_row.addWidget(refresh_btn)
        layout.addLayout(refresh_row)

        return group

    # ── Panel 3: Site Inventory ────────────────────────────────────────────────

    def _build_inventory_group(self) -> QGroupBox:
        group = QGroupBox("Site Inventory")
        layout = QVBoxLayout(group)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Status:"))
        self._inv_status_combo = QComboBox()
        self._inv_status_combo.addItems(["(all)", "downloaded", "pending", "failed", "not_found", "skipped"])
        self._inv_status_combo.setFixedWidth(110)
        self._inv_status_combo.currentIndexChanged.connect(self._inv_refresh)
        filter_row.addWidget(self._inv_status_combo)

        filter_row.addWidget(QLabel("Path prefix:"))
        self._inv_prefix_edit = QLineEdit()
        self._inv_prefix_edit.setPlaceholderText("e.g. detail/")
        self._inv_prefix_edit.setFixedWidth(160)
        self._inv_prefix_edit.returnPressed.connect(self._inv_refresh)
        filter_row.addWidget(self._inv_prefix_edit)

        inv_search_btn = QPushButton("Filter")
        inv_search_btn.setFixedWidth(60)
        inv_search_btn.clicked.connect(self._inv_refresh)
        filter_row.addWidget(inv_search_btn)

        filter_row.addStretch()
        self._inv_count_label = QLabel("")
        self._inv_count_label.setStyleSheet("color: #555; font-size: 11px;")
        filter_row.addWidget(self._inv_count_label)
        layout.addLayout(filter_row)

        # Table
        self._inv_table = QTableWidget(0, 6)
        self._inv_table.setHorizontalHeaderLabels(
            ["URL", "Status", "Size", "HTTP", "Last Fetched", "Last Modified"]
        )
        hdr = self._inv_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._inv_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._inv_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._inv_table.setMinimumHeight(120)
        self._inv_table.setMaximumHeight(220)
        layout.addWidget(self._inv_table)

        # Pagination row
        pg_row = QHBoxLayout()
        self._inv_prev_btn = QPushButton("◀ Prev")
        self._inv_prev_btn.setFixedWidth(80)
        self._inv_prev_btn.clicked.connect(self._inv_prev)
        pg_row.addWidget(self._inv_prev_btn)
        self._inv_page_label = QLabel("—")
        pg_row.addWidget(self._inv_page_label)
        self._inv_next_btn = QPushButton("Next ▶")
        self._inv_next_btn.setFixedWidth(80)
        self._inv_next_btn.clicked.connect(self._inv_next)
        pg_row.addWidget(self._inv_next_btn)
        pg_row.addStretch()
        layout.addLayout(pg_row)

        return group

    # ── Panel 4: Entry Pages & Metadata Scraper ───────────────────────────────

    def _build_entry_scraper_group(self) -> QGroupBox:
        group = QGroupBox("Entry Pages & Metadata Scraper")
        layout = QVBoxLayout(group)

        # Options row
        opts_row = QHBoxLayout()
        self.auto_scrape_cb = QCheckBox("Auto-scrape new entries after import")
        self.auto_scrape_cb.stateChanged.connect(self._save_entry_settings)
        opts_row.addWidget(self.auto_scrape_cb)

        self.download_files_cb = QCheckBox("Download attachments (ffp, txt)")
        self.download_files_cb.stateChanged.connect(self._save_entry_settings)
        opts_row.addWidget(self.download_files_cb)

        self.force_scrape_cb = QCheckBox("Force re-scrape")
        self.force_scrape_cb.stateChanged.connect(self._save_entry_settings)
        opts_row.addWidget(self.force_scrape_cb)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        local_row = QHBoxLayout()
        self.local_pages_cb = QCheckBox("Use local pages for metadata")
        self.local_pages_cb.stateChanged.connect(self._save_entry_settings)
        local_row.addWidget(self.local_pages_cb)
        self._pages_count_label = QLabel("")
        self._pages_count_label.setStyleSheet("color: gray; font-size: 11px;")
        local_row.addWidget(self._pages_count_label)
        local_row.addStretch()

        local_row.addWidget(QLabel("Delay (ms):"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(500, 10000)
        self.delay_spin.setValue(1500)
        self.delay_spin.setSingleStep(100)
        self.delay_spin.setFixedWidth(80)
        self.delay_spin.valueChanged.connect(self._save_entry_settings)
        local_row.addWidget(self.delay_spin)
        layout.addLayout(local_row)

        # Action grid
        _VC = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        _W = 190
        grid = QGridLayout()
        grid.setColumnStretch(4, 1)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Row 0: bulk + stop
        self.scrape_all_btn = QPushButton("Scrape All Missing Entries")
        self.scrape_all_btn.setFixedWidth(_W)
        self.scrape_all_btn.clicked.connect(self._on_scrape_all)
        grid.addWidget(self.scrape_all_btn, 0, 2, _VC)

        self.stop_scrape_btn = QPushButton("Stop Scraper")
        self.stop_scrape_btn.setFixedWidth(_W)
        self.stop_scrape_btn.setEnabled(False)
        self.stop_scrape_btn.clicked.connect(self._on_stop_scrape)
        grid.addWidget(self.stop_scrape_btn, 0, 3, _VC)

        # Row 1: single entry
        grid.addWidget(QLabel("Single entry:"), 1, 0, _VC)
        self.single_lb_input = QLineEdit()
        self.single_lb_input.setPlaceholderText("LB number…")
        self.single_lb_input.setFixedWidth(100)
        self.single_lb_input.returnPressed.connect(self._on_scrape_single)
        grid.addWidget(self.single_lb_input, 1, 1, _VC)
        self.scrape_single_btn = QPushButton("Scrape")
        self.scrape_single_btn.setFixedWidth(_W)
        self.scrape_single_btn.clicked.connect(self._on_scrape_single)
        grid.addWidget(self.scrape_single_btn, 1, 2, _VC)
        self.single_scrape_status_label = QLabel("")
        grid.addWidget(self.single_scrape_status_label, 1, 3, 1, 2, _VC)

        # Row 2: range
        grid.addWidget(QLabel("Range:"), 2, 0, _VC)
        range_w = QWidget()
        range_inner = QHBoxLayout(range_w)
        range_inner.setContentsMargins(0, 0, 0, 0)
        range_inner.setSpacing(4)
        self.range_start_spin = QSpinBox()
        self.range_start_spin.setRange(1, 99999)
        self.range_start_spin.setValue(1)
        self.range_start_spin.setFixedWidth(80)
        range_inner.addWidget(self.range_start_spin)
        range_inner.addWidget(QLabel("to"))
        self.range_end_spin = QSpinBox()
        self.range_end_spin.setRange(1, 99999)
        self.range_end_spin.setValue(100)
        self.range_end_spin.setFixedWidth(80)
        range_inner.addWidget(self.range_end_spin)
        grid.addWidget(range_w, 2, 1, _VC)
        self.scrape_range_btn = QPushButton("Scrape Range")
        self.scrape_range_btn.setFixedWidth(_W)
        self.scrape_range_btn.clicked.connect(self._on_scrape_range)
        grid.addWidget(self.scrape_range_btn, 2, 2, _VC)

        # Row 3: private rescrape
        grid.addWidget(QLabel("Private LBs:"), 3, 0, _VC)
        self.rescrape_private_btn = QPushButton("Re-scrape Private LBs")
        self.rescrape_private_btn.setFixedWidth(_W)
        self.rescrape_private_btn.setToolTip(
            "Force re-scrape all Private LBs to check whether any have been published"
        )
        self.rescrape_private_btn.clicked.connect(self._on_rescrape_private)
        grid.addWidget(self.rescrape_private_btn, 3, 2, _VC)
        self.rescrape_private_label = QLabel("")
        grid.addWidget(self.rescrape_private_label, 3, 3, 1, 2, _VC)

        # Row 4: download pages
        grid.addWidget(QLabel("Page cache:"), 4, 0, _VC)
        self.download_pages_btn = QPushButton("Download Missing Pages")
        self.download_pages_btn.setFixedWidth(_W)
        self.download_pages_btn.setToolTip(
            "Fetch and cache HTML detail pages for every LB number "
            "without parsing metadata or downloading attachments."
        )
        self.download_pages_btn.clicked.connect(self._on_download_pages)
        grid.addWidget(self.download_pages_btn, 4, 2, _VC)
        self.download_pages_label = QLabel("")
        grid.addWidget(self.download_pages_label, 4, 3, 1, 2, _VC)

        layout.addLayout(grid)

        # Progress + status
        self.scrape_progress = QProgressBar()
        self.scrape_progress.setVisible(False)
        layout.addWidget(self.scrape_progress)

        self.scrape_status_label = QLabel("")
        layout.addWidget(self.scrape_status_label)

        # Scraper log
        log_group = QGroupBox("Scraper Log")
        log_layout = QVBoxLayout(log_group)
        self.scraper_log = QPlainTextEdit()
        self.scraper_log.setReadOnly(True)
        self.scraper_log.setMaximumBlockCount(500)
        self.scraper_log.setMinimumHeight(100)
        self.scraper_log.setMaximumHeight(160)
        log_layout.addWidget(self.scraper_log)
        layout.addWidget(log_group)

        return group

    # ── Panel 5: Bootleg Catalog ───────────────────────────────────────────────

    def _build_bootlegs_group(self) -> QGroupBox:
        group = QGroupBox("Bootleg-CD Catalog (LBBCD)")
        layout = QVBoxLayout(group)

        btn_row = QHBoxLayout()
        self._scrape_bootlegs_btn = QPushButton("Scrape Bootleg Catalog")
        self._scrape_bootlegs_btn.setToolTip(
            "Fetch and diff-apply the LosslessBob LBBCD index page. "
            "Skips if unchanged (ETag / Last-Modified). Force-scrape ignores cache."
        )
        self._scrape_bootlegs_btn.clicked.connect(self._on_scrape_bootlegs)
        btn_row.addWidget(self._scrape_bootlegs_btn)

        self._force_bootlegs_cb = QCheckBox("Force")
        self._force_bootlegs_cb.setToolTip("Re-fetch even when ETag/Last-Modified indicate no change")
        btn_row.addWidget(self._force_bootlegs_cb)

        btn_row.addStretch()
        self._bootlegs_status_lbl = QLabel("")
        btn_row.addWidget(self._bootlegs_status_lbl)
        layout.addLayout(btn_row)

        self._bl_history_table = QTableWidget(0, 5)
        self._bl_history_table.setHorizontalHeaderLabels(
            ["Scraped at", "Status", "Total", "Added", "Changed"]
        )
        hdr = self._bl_history_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._bl_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._bl_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bl_history_table.setMinimumHeight(80)
        self._bl_history_table.setMaximumHeight(140)
        layout.addWidget(self._bl_history_table)

        return group

    # ── Settings persistence ───────────────────────────────────────────────────

    def _load_crawler_settings(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            ).json()
            self._crawler_delay_spin.setValue(int(resp.get("crawler_delay_ms") or 1500))
            self._crawler_cap_spin.setValue(int(resp.get("crawler_daily_cap") or 5000))
            # Entry scraper settings
            self.auto_scrape_cb.setChecked(resp.get("auto_scrape", "1") != "0")
            self.download_files_cb.setChecked(resp.get("scrape_attachments", "1") != "0")
            self.force_scrape_cb.setChecked(resp.get("force_scrape", "0") != "0")
            self.local_pages_cb.setChecked(resp.get("use_local_pages", "0") == "1")
            self.delay_spin.setValue(int(resp.get("scrape_delay_ms") or 1500))
        except Exception:
            pass

    def _save_crawler_settings(self) -> None:
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={
                    "crawler_delay_ms": str(self._crawler_delay_spin.value()),
                    "crawler_daily_cap": str(self._crawler_cap_spin.value()),
                },
                timeout=5,
            )
        except Exception:
            pass

    def _save_entry_settings(self) -> None:
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings",
                json={
                    "auto_scrape":        "1" if self.auto_scrape_cb.isChecked() else "0",
                    "scrape_attachments": "1" if self.download_files_cb.isChecked() else "0",
                    "force_scrape":       "1" if self.force_scrape_cb.isChecked() else "0",
                    "use_local_pages":    "1" if self.local_pages_cb.isChecked() else "0",
                    "scrape_delay_ms":    str(self.delay_spin.value()),
                },
                timeout=5,
            )
        except Exception:
            pass

    def _refresh_pages_count(self) -> None:
        try:
            count = sum(1 for _ in _SITE_DETAIL_DIR.glob("*.html"))
            self._pages_count_label.setText(f"({count:,} cached)")
        except Exception:
            self._pages_count_label.setText("")

    # ── Site crawler handlers ──────────────────────────────────────────────────

    def _on_crawler_start(self) -> None:
        scope = self._scope_combo.currentText()
        force = self._crawler_force_cb.isChecked()
        delay_ms = self._crawler_delay_spin.value()
        daily_cap = self._crawler_cap_spin.value()
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/crawler/start",
                json={"scope": scope, "force": force,
                      "delay_ms": delay_ms, "daily_cap": daily_cap},
                timeout=10,
            ).json()
        except Exception as e:
            self._crawler_url_label.setText(f"Error: {e}")
            return
        if not resp.get("ok"):
            self._crawler_url_label.setText(resp.get("error", "Failed to start crawler."))
            return
        self._crawler_start_btn.setEnabled(False)
        self._crawler_stop_btn.setEnabled(True)
        self._crawler_progress.setVisible(True)
        self._crawler_url_label.setText("Starting…")
        self._crawler_counts_label.setText("")
        self._start_crawler_poll()

    def _on_crawler_stop(self) -> None:
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/crawler/stop", timeout=5
            )
        except Exception:
            pass
        self._crawler_stop_btn.setEnabled(False)
        self._crawler_url_label.setText("Stop requested…")

    def _start_crawler_poll(self) -> None:
        if self._crawler_status_thread and self._crawler_status_thread.isRunning():
            return
        self._crawler_status_thread = _CrawlerStatusThread(self.flask_port)
        self._crawler_status_thread.status_update.connect(self._on_crawler_status)
        self._crawler_status_thread.start()

    def _on_crawler_status(self, status: dict) -> None:
        stage   = status.get("stage", "idle")
        running = status.get("running", False)
        url     = status.get("current_url") or ""
        msg     = status.get("message", "")

        fetched      = status.get("fetched", 0)
        not_modified = status.get("not_modified", 0)
        skipped      = status.get("skipped", 0)
        failed       = status.get("failed", 0)
        not_found    = status.get("not_found", 0)
        queue_size   = status.get("queue_size", 0)

        if url:
            self._crawler_url_label.setText(url)
        elif msg:
            self._crawler_url_label.setText(msg)

        counts_text = (
            f"Fetched: {fetched}  |  304 (unchanged): {not_modified}  |  "
            f"Not found: {not_found}  |  Skipped: {skipped}  |  Failed: {failed}  |  "
            f"Queue: {queue_size}"
        )
        self._crawler_counts_label.setText(counts_text)

        if not running:
            if self._crawler_status_thread:
                self._crawler_status_thread.stop()
                self._crawler_status_thread = None
            self._crawler_start_btn.setEnabled(True)
            self._crawler_stop_btn.setEnabled(False)
            self._crawler_progress.setVisible(False)
            final = msg or f"Done — stage: {stage}"
            self._crawler_url_label.setText(final)
            self._load_sessions_history()
            self._inv_refresh()

    # ── Session history ────────────────────────────────────────────────────────

    def _load_sessions_history(self) -> None:
        try:
            rows = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/crawler/sessions",
                params={"limit": 20},
                timeout=5,
            ).json()
        except Exception:
            return
        if not isinstance(rows, list):
            return
        tbl = self._sessions_table
        tbl.setRowCount(0)
        _STATUS_COLORS = {
            "done":    QColor("#d4edda"),
            "stopped": QColor("#fff3cd"),
            "error":   QColor("#f8d7da"),
        }
        for r in rows:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [
                (r.get("started_at") or "")[:16],
                (r.get("finished_at") or "")[:16],
                r.get("scope", ""),
                r.get("status", ""),
                str(r.get("pages_fetched") or 0),
                str(r.get("pages_304") or 0),
                str(r.get("pages_failed") or 0),
            ]
            color = _STATUS_COLORS.get(r.get("status", ""))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if color:
                    item.setBackground(color)
                tbl.setItem(row, col, item)

    # ── Inventory ──────────────────────────────────────────────────────────────

    def _inv_refresh(self) -> None:
        self._inv_offset = 0
        self._inv_load()

    def _inv_prev(self) -> None:
        self._inv_offset = max(0, self._inv_offset - self._inv_limit)
        self._inv_load()

    def _inv_next(self) -> None:
        if self._inv_offset + self._inv_limit < self._inv_total:
            self._inv_offset += self._inv_limit
            self._inv_load()

    def _inv_load(self) -> None:
        status_val = self._inv_status_combo.currentText()
        status_param = None if status_val == "(all)" else status_val
        prefix = self._inv_prefix_edit.text().strip() or None
        params: dict = {"limit": self._inv_limit, "offset": self._inv_offset}
        if status_param:
            params["status"] = status_param
        if prefix:
            params["path_prefix"] = prefix
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/crawler/inventory",
                params=params,
                timeout=10,
            ).json()
        except Exception:
            return
        rows  = resp.get("rows", [])
        total = resp.get("total", 0)
        self._inv_total = total

        tbl = self._inv_table
        tbl.setRowCount(0)
        _STATUS_COLORS = {
            "downloaded": QColor("#d4edda"),
            "pending":    QColor("#fff3cd"),
            "failed":     QColor("#f8d7da"),
            "not_found":  QColor("#e2e3e5"),
            "skipped":    QColor("#e2e3e5"),
        }
        for r in rows:
            row = tbl.rowCount()
            tbl.insertRow(row)
            size_val = r.get("size_bytes") or 0
            size_str = f"{size_val/1024:.1f} KB" if size_val else ""
            vals = [
                r.get("url", ""),
                r.get("status", ""),
                size_str,
                str(r.get("http_status") or ""),
                (r.get("last_fetched_at") or "")[:16],
                (r.get("last_modified") or "")[:29],
            ]
            color = _STATUS_COLORS.get(r.get("status", ""))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if color:
                    item.setBackground(color)
                tbl.setItem(row, col, item)

        page_num = self._inv_offset // self._inv_limit + 1
        page_total = max(1, -(-total // self._inv_limit))
        self._inv_page_label.setText(f"Page {page_num} / {page_total}")
        self._inv_count_label.setText(f"{total:,} rows")
        self._inv_prev_btn.setEnabled(self._inv_offset > 0)
        self._inv_next_btn.setEnabled(self._inv_offset + self._inv_limit < total)

    # ── Entry scraper handlers ─────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self.scraper_log.appendPlainText(msg)

    def _entry_scraper_set_busy(self, busy: bool) -> None:
        self.scrape_all_btn.setEnabled(not busy)
        self.scrape_range_btn.setEnabled(not busy)
        self.rescrape_private_btn.setEnabled(not busy)
        self.download_pages_btn.setEnabled(not busy)
        self.stop_scrape_btn.setEnabled(busy)
        self.scrape_progress.setVisible(busy)
        if busy:
            self.scrape_progress.setRange(0, 0)

    def _on_scrape_single(self) -> None:
        text = self.single_lb_input.text().strip()
        try:
            lb = int(text)
        except ValueError:
            self.single_scrape_status_label.setText("Invalid number.")
            return
        self.scrape_single_btn.setEnabled(False)
        self.single_scrape_status_label.setText(f"Scraping LB-{lb}…")
        self._log(f"Starting single scrape: LB-{lb}")
        self._single_scrape_thread = _SingleScrapeThread(
            self.flask_port, lb, force=self.force_scrape_cb.isChecked()
        )
        self._single_scrape_thread.finished.connect(self._on_single_scrape_finished)
        self._single_scrape_thread.start()

    def _on_single_scrape_finished(self, data: dict) -> None:
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

    def _on_scrape_range(self) -> None:
        start = self.range_start_spin.value()
        end   = self.range_end_spin.value()
        if end < start:
            self.scrape_status_label.setText("End must be >= start.")
            return
        force = self.force_scrape_cb.isChecked()
        self._entry_scraper_set_busy(True)
        self.scrape_status_label.setText(f"Starting range scrape LB-{start} to LB-{end}…")
        self._log(f"Starting range scrape: LB-{start} to LB-{end}{' (force)' if force else ''}")
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/start",
                json={"start_lb": start, "end_lb": end, "force": force},
                timeout=10,
            )
        except Exception as e:
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start range scrape: {e}")
            return
        self._start_scrape_poll()

    def _on_scrape_all(self) -> None:
        force = self.force_scrape_cb.isChecked()
        self._entry_scraper_set_busy(True)
        self.scrape_status_label.setText("Starting scraper…")
        self._log(f"Starting bulk scrape of all missing entries{' (force)' if force else ''}…")
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/start",
                json={"start_lb": 1, "force": force},
                timeout=10,
            )
        except Exception as e:
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start scraper: {e}")
            return
        self._start_scrape_poll()

    def _on_stop_scrape(self) -> None:
        try:
            requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/stop", timeout=5
            )
        except Exception:
            pass
        self.stop_scrape_btn.setEnabled(False)
        self.scrape_status_label.setText("Stop requested…")
        self._log("Stop requested by user.")

    def _on_rescrape_private(self) -> None:
        try:
            stats = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/lb_master/stats", timeout=5
            ).json()
            private_count = stats.get("private", 0)
        except Exception as e:
            QMessageBox.warning(self, "Re-scrape Private LBs", f"Could not fetch stats: {e}")
            return
        if private_count == 0:
            QMessageBox.information(
                self, "Re-scrape Private LBs", "No Private LBs found in the database."
            )
            return
        confirm = QMessageBox.question(
            self, "Re-scrape Private LBs",
            f"Re-scrape {private_count} Private LB(s) to check whether any have been "
            "published?\n\nThis uses force mode and may take a while.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._private_rescrape_mode = True
        self._private_rescrape_before = private_count
        self._entry_scraper_set_busy(True)
        self.scrape_status_label.setText(
            f"Queuing {private_count} private LB(s) for force re-scrape…"
        )
        self._log(f"Starting private LB re-scrape: {private_count} LBs (force=True)")
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/private_rescrape",
                timeout=10,
            ).json()
        except Exception as e:
            self._private_rescrape_mode = False
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start private rescrape: {e}")
            return
        if "error" in resp:
            self._private_rescrape_mode = False
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {resp['error']}")
            self._log(f"Private rescrape error: {resp['error']}")
            return
        self._start_scrape_poll()

    def _on_download_pages(self) -> None:
        force = self.force_scrape_cb.isChecked()
        self._page_download_mode = True
        self._entry_scraper_set_busy(True)
        self.scrape_status_label.setText("Queueing page downloads…")
        self._log(f"Starting page-cache download{' (force)' if force else ''}…")
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/scrape/download_pages",
                json={"force": force},
                timeout=10,
            ).json()
        except Exception as e:
            self._page_download_mode = False
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {e}")
            self._log(f"Failed to start page download: {e}")
            return
        if "error" in resp:
            self._page_download_mode = False
            self._entry_scraper_set_busy(False)
            self.scrape_status_label.setText(f"Error: {resp['error']}")
            self._log(f"Page download error: {resp['error']}")
            return
        total = resp.get("total", 0)
        self._log(f"Downloading up to {total:,} pages…")
        self._start_scrape_poll()

    def _start_scrape_poll(self) -> None:
        if self._scrape_status_thread and self._scrape_status_thread.isRunning():
            return
        self._scrape_status_thread = _ScrapeStatusThread(self.flask_port)
        self._scrape_status_thread.status_update.connect(self._on_scrape_status)
        self._scrape_status_thread.start()

    _last_logged_lb: int | None = None

    def _on_scrape_status(self, status: dict) -> None:
        total       = status.get("total", 0)
        done        = status.get("done", 0)
        current     = status.get("current_lb", "")
        last_lb     = status.get("last_lb")
        running     = status.get("running", False)
        skipped     = status.get("skipped", 0)
        last_action = status.get("last_action")
        last_source = status.get("last_source")

        if total > 0:
            self.scrape_progress.setRange(0, total)
            self.scrape_progress.setValue(done)

        if current:
            verb = "Downloading" if self._page_download_mode else "Scraping"
            label = f"{verb} LB-{current} ({done}/{total}"
            if skipped:
                label += f", {skipped} skipped"
            label += ")…"
            self.scrape_status_label.setText(label)

        if last_lb and last_lb != self._last_logged_lb:
            self._last_logged_lb = last_lb
            if last_action == "skipped":
                already = "already cached" if self._page_download_mode else "already complete"
                self._log(f"Skipped LB-{last_lb} — {already} ({done}/{total})")
            elif last_action == "error":
                verb = "downloading" if self._page_download_mode else "scraping"
                self._log(f"Error {verb} LB-{last_lb} ({done}/{total})")
            elif last_action == "downloaded":
                self._log(f"Downloaded LB-{last_lb} [web] ({done}/{total})")
            else:
                src = f" [{last_source}]" if last_source else ""
                self._log(f"Scraped LB-{last_lb}{src} ({done}/{total})")

        if not running:
            if self._scrape_status_thread:
                self._scrape_status_thread.stop()
                self._scrape_status_thread = None
            self._entry_scraper_set_busy(False)
            if self._page_download_mode:
                self._page_download_mode = False
                downloaded = done - skipped - status.get("errors", 0)
                msg = (f"Page download complete. {downloaded} downloaded, "
                       f"{skipped} already cached, {status.get('errors', 0)} errors.")
                self._refresh_pages_count()
            else:
                msg = f"Scrape complete. {done} processed"
                if skipped:
                    msg += f" ({skipped} already complete)"
                msg += f", {status.get('errors', 0)} errors."
                if self._private_rescrape_mode:
                    self._private_rescrape_mode = False
                    try:
                        stats = requests.get(
                            f"http://127.0.0.1:{self.flask_port}/api/lb_master/stats",
                            timeout=5,
                        ).json()
                        new_private = stats.get("private", 0)
                        promoted = max(0, self._private_rescrape_before - new_private)
                        msg += f" {promoted} promoted to Public, {new_private} private remain."
                    except Exception:
                        pass
            self.scrape_status_label.setText(msg)
            self._log(msg)
            self._last_logged_lb = None

    # ── Bootleg catalog handlers ───────────────────────────────────────────────

    def _on_scrape_bootlegs(self) -> None:
        force = self._force_bootlegs_cb.isChecked()
        self._scrape_bootlegs_btn.setEnabled(False)
        self._bootlegs_status_lbl.setText("Starting scrape…")
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/bootlegs/scrape",
                json={"force": force},
                timeout=10,
            ).json()
        except Exception as e:
            self._bootlegs_status_lbl.setText(f"Error: {e}")
            self._scrape_bootlegs_btn.setEnabled(True)
            return
        if "error" in resp:
            self._bootlegs_status_lbl.setText(f"Error: {resp['error']}")
            self._scrape_bootlegs_btn.setEnabled(True)
            return
        self._bootlegs_status_lbl.setText("Scraping…")
        self._poll_bootlegs_scrape()

    def _poll_bootlegs_scrape(self) -> None:
        try:
            data = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/bootlegs/scrape/status",
                timeout=5,
            ).json()
        except Exception:
            self._scrape_bootlegs_btn.setEnabled(True)
            return
        if data.get("running"):
            QTimer.singleShot(1500, self._poll_bootlegs_scrape)
            self._bootlegs_status_lbl.setText(data.get("message", "Scraping…"))
        else:
            self._scrape_bootlegs_btn.setEnabled(True)
            msg = data.get("message") or data.get("stage", "Done.")
            if data.get("error"):
                msg = f"Error: {data['error']}"
            self._bootlegs_status_lbl.setText(msg)
            self._load_bootlegs_history()

    def _load_bootlegs_history(self) -> None:
        try:
            rows = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/bootlegs/scrapes",
                timeout=5,
            ).json()
        except Exception:
            return
        if not isinstance(rows, list):
            return
        tbl = self._bl_history_table
        tbl.setRowCount(0)
        _STATUS_COLORS = {
            "success":   QColor("#d4edda"),
            "no_change": QColor("#e2e3e5"),
            "failed":    QColor("#f8d7da"),
        }
        for r in rows:
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [
                (r.get("scraped_at") or "")[:16],
                r.get("status", ""),
                str(r.get("rows_total") or ""),
                str(r.get("rows_added") or ""),
                str(r.get("rows_changed") or ""),
            ]
            color = _STATUS_COLORS.get(r.get("status", ""))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if color:
                    item.setBackground(color)
                tbl.setItem(row, col, item)
